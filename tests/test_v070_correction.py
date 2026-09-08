"""v0.7.0 correction round — counterexamples from independent review 1.

Every test here is a probe that previously executed an unsafe outcome while the
existing suites stayed green: a phase that could not be reached, a control table
that was not the active one, a binding that bound nothing, a manifest that could
be swapped after the fact, a CLI path nobody ran, a report that rolled missing
evidence up to PASS, a measurement that claimed a number it did not have, and a
freeze that only proved it had hashed itself.

Harness-local: no model call, no network, no write outside a tempfile fixture.
"""
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import time
import unittest

from test_v070 import EXECUTION, ROOT, Workspace, ApprovedJobTests, utc  # noqa: F401

import execution  # noqa: E402
import invoke  # noqa: E402
import policy  # noqa: E402
import workflow  # noqa: E402


# =====================================================================
# class 1 — A2 reachability: P3 research may still be pending
# =====================================================================
class StartupReachabilityTests(Workspace):
    profile = "startup-reversible"

    def test_p4_launches_while_p3_research_is_still_pending(self):
        self.typed_pass("G1")                       # completes P0 contract only
        self.phase_done("P1 requirements", "P2 structure")
        self.assertEqual("pending", policy._tables(self.read("PROGRESS.md"))[1]["P3 research"])
        self.assertEqual(0, self.run_invoke(phase="P4"))

    def test_p5_still_needs_its_own_scoping_document(self):
        self.typed_pass("G1")
        self.phase_done("P1 requirements", "P2 structure")
        self.refused("P4 scoping", phase="P5")


# =====================================================================
# class 2 — A2/A9 the parsed table must be the active one
# =====================================================================
class ActiveControlPlaneTests(Workspace):
    profile = "startup-reversible"

    def fence_gate_table(self):
        """Leave the gate table in place but inside a ``` illustration fence."""
        header = "| Gate | Verdict | Contract version | Approval mode | Approver | Approved at | Evidence |"
        text = self.read("PROGRESS.md")
        start = text.index(header)
        end = text.index("\n\n", start)
        with open(os.path.join(self.proj, "PROGRESS.md"), "w", encoding="utf-8") as handle:
            handle.write(text[:start] + "```\n" + text[start:end] + "\n```" + text[end:])

    def test_a_gate_table_inside_a_code_fence_is_not_the_control_plane(self):
        self.typed_pass("G1")
        self.fence_gate_table()
        self.refused("Gate ledger", phase="P3")

    def test_duplicate_gate_rows_are_refused_before_launch(self):
        self.typed_pass("G1")
        self.replace("PROGRESS.md", "| G2 | PENDING", "| G1 | HOLD | v1 | human | | | |\n| G2 | PENDING")
        self.refused("duplicate", phase="P3")

    def test_duplicate_phase_rows_are_refused_before_launch(self):
        self.typed_pass("G1")
        self.replace("PROGRESS.md", "| P1 requirements | pending | |",
                     "| P1 requirements | done | 2026-01-01 | x |\n| P1 requirements | pending | |")
        self.refused("duplicate", phase="P3")


# =====================================================================
# class 3 — A3 the binding must bind the actual role, outputs and approval
# =====================================================================
class BindingTests(ApprovedJobTests):
    def test_declared_role_must_equal_the_role_actually_launched(self):
        job, digest = self.write_job(runner_role="owner-proxy")
        self.approve(digest)
        with self.assertRaises(SystemExit) as caught:
            self.launch(job, runner_role="runner")
        self.assertIn("runner_role", str(caught.exception))

    def test_expected_output_root_must_equal_the_approved_output_root(self):
        job, digest = self.write_job()
        self.approve(digest)
        manifest = os.path.join(self.tmp, "expect.json")
        with open(manifest, "w", encoding="utf-8") as handle:
            json.dump({"schema": "ldl-expected-output-v1", "job_id": "J-1",
                       "output_root": "05_engineering/evidence",
                       "outputs": [{"id": "a", "path": "increments/a.txt", "format": "text",
                                    "min_bytes": 1}]}, handle)
        with self.assertRaises(SystemExit) as caught:
            self.launch(job, expect=manifest)
        self.assertIn("output_root", str(caught.exception))

    def test_an_approval_file_that_resolves_into_the_project_is_refused(self):
        job, digest = self.write_job()
        inside = os.path.join(self.proj, "self-approval.json")
        with open(inside, "w", encoding="utf-8") as handle:
            json.dump({"schema": "ldl-job-approval-v1", "job_sha256": digest, "approver": "Elon",
                       "approval_mode": "delegated-agent", "decided_at": utc(-60)}, handle)
        os.symlink(inside, os.path.join(self.approvals, digest + ".json"))
        with self.assertRaises(SystemExit) as caught:
            self.launch(job)
        self.assertIn("project", str(caught.exception))

    def test_the_binding_record_names_the_resolved_approval_path(self):
        job, digest = self.write_job()
        self.approve(digest)
        self.assertEqual(0, self.launch(job))
        record = json.loads(open(os.path.join(self.proj, "logs", "approved-jobs.jsonl"),
                                 encoding="utf-8").read().splitlines()[0])
        self.assertEqual(os.path.realpath(os.path.join(self.approvals, digest + ".json")),
                         record["approval_path"])


# =====================================================================
# class 4 — A5 frozen expectation and cross-process output reservation
# =====================================================================
class FrozenExpectationTests(Workspace):
    profile = "startup-reversible"

    def setUp(self):
        super().setUp()
        self.typed_pass("G1")
        self.out = os.path.join(self.proj, "05_engineering", "evidence")
        os.makedirs(self.out, exist_ok=True)
        self.manifest = os.path.join(self.tmp, "expect.json")

    def write_manifest(self, rel):
        payload = {"schema": "ldl-expected-output-v1", "job_id": "J-1",
                   "output_root": "05_engineering/evidence",
                   "outputs": [{"id": "a", "path": rel, "format": "text", "min_bytes": 1}]}
        with open(self.manifest, "w", encoding="utf-8") as handle:
            json.dump(payload, handle)
        return self.manifest

    def test_a_manifest_swapped_by_the_child_cannot_turn_a_miss_into_a_pass(self):
        self.write_manifest("required.txt")
        swap = json.dumps({"schema": "ldl-expected-output-v1", "job_id": "J-1",
                           "output_root": "05_engineering/evidence",
                           "outputs": [{"id": "a", "path": "replacement.txt", "format": "text",
                                        "min_bytes": 1}]})
        script = (f"open({os.path.join(self.out, 'replacement.txt')!r},'w').write('ok');"
                  f"open({self.manifest!r},'w').write({swap!r})")
        code = self.run_invoke(phase="P3", command=[sys.executable, "-c", script],
                               expect=self.manifest)
        self.assertNotEqual(0, code)
        report = json.load(open(os.path.join(self.proj, "logs", "reconciliation", "INV-0001.json"),
                                encoding="utf-8"))
        self.assertEqual("required.txt", report["outputs"][0]["path"])
        self.assertEqual("MISSING", report["outputs"][0]["status"])
        self.assertFalse(report["artifact_valid"])

    def test_a_live_reservation_blocks_a_second_process_on_the_same_output(self):
        self.write_manifest("shared.txt")
        holder = execution.reserve_outputs(self.proj, "INV-9001", execution.load_expected(self.manifest))
        self.assertTrue(holder)
        probe = subprocess.run(
            [sys.executable, "-c",
             "import sys,json;sys.path.insert(0,%r);import execution;"
             "m=execution.load_expected(%r);\n"
             "try:\n execution.reserve_outputs(%r,'INV-9002',m);print('RESERVED')\n"
             "except execution.ManifestError as exc:print('REFUSED',exc)"
             % (os.path.join(ROOT, "tools"), self.manifest, self.proj)],
            text=True, capture_output=True)
        self.assertIn("REFUSED", probe.stdout, probe.stderr)
        execution.release_outputs(self.proj, "INV-9001")
        again = subprocess.run(
            [sys.executable, "-c",
             "import sys;sys.path.insert(0,%r);import execution;"
             "m=execution.load_expected(%r);execution.reserve_outputs(%r,'INV-9003',m);print('RESERVED')"
             % (os.path.join(ROOT, "tools"), self.manifest, self.proj)],
            text=True, capture_output=True)
        self.assertIn("RESERVED", again.stdout, again.stderr)

    def test_a_finished_invocation_releases_its_reservation(self):
        self.write_manifest("kept.txt")
        script = f"open({os.path.join(self.out, 'kept.txt')!r},'w').write('ok')"
        self.assertEqual(0, self.run_invoke(phase="P3", command=[sys.executable, "-c", script],
                                            expect=self.manifest))
        self.assertEqual({}, execution.read_reservations(self.proj))

    def test_a_failed_launch_releases_its_reservation(self):
        self.write_manifest("never.txt")
        self.run_invoke(phase="P3", command=[os.path.join(self.tmp, "no-such-binary")],
                        expect=self.manifest)
        self.assertEqual({}, execution.read_reservations(self.proj))


# =====================================================================
# class 5 — A3/A9 the documented CLI is the CLI that runs
# =====================================================================
class OfficialCliTests(ApprovedJobTests):
    def cli(self, *extra):
        job, digest = self.write_job()
        self.approve(digest)
        return subprocess.run([sys.executable, EXECUTION, "job-validate", self.proj, job,
                               "--phase", "P3", "--runner-id", "steve",
                               "--cwd", os.path.realpath(self.proj),
                               "--approvals-root", self.approvals, *extra,
                               "--", *self.command], text=True, capture_output=True), digest

    def test_job_validate_runs_end_to_end_from_argv(self):
        result, digest = self.cli()
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        self.assertIn("JOB BOUND", result.stdout)
        self.assertIn(digest, result.stdout)

    def test_options_after_the_positionals_are_parsed_not_swallowed(self):
        result, _ = self.cli("--cwd", os.path.realpath(self.proj))
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        self.assertIn("JOB BOUND", result.stdout)

    def test_a_mismatched_command_is_refused_through_the_cli(self):
        job, digest = self.write_job()
        self.approve(digest)
        result = subprocess.run([sys.executable, EXECUTION, "job-validate", self.proj, job,
                                 "--phase", "P3", "--runner-id", "steve",
                                 "--cwd", os.path.realpath(self.proj),
                                 "--approvals-root", self.approvals,
                                 "--", sys.executable, "-c", "print('other')"],
                                text=True, capture_output=True)
        self.assertEqual(1, result.returncode)
        self.assertIn("EXECUTION REFUSED", result.stdout)

    def test_every_documented_subcommand_answers_its_help(self):
        for name in ("job-validate", "reconcile", "status", "evaluator-validate",
                     "measure-collect", "measure-validate"):
            result = subprocess.run([sys.executable, EXECUTION, name, "--help"],
                                    text=True, capture_output=True)
            self.assertEqual(0, result.returncode, name + result.stderr)


# =====================================================================
# class 6 — A6 status may not roll missing evidence up to PASS
# =====================================================================
class StatusTruthTests(Workspace):
    profile = "startup-reversible"

    def fake_all_gates_pass(self):
        for gate in ("G1", "G2", "G3", "G4"):
            self.replace("PROGRESS.md", f"| {gate} | PENDING | v1 | human | | | |",
                         f"| {gate} | PASS | v1 | human | Elon | 2026-01-01 | "
                         f"[raw/gate-decisions/{gate.lower()}.json](raw/gate-decisions/{gate.lower()}.json) |")

    def test_unverifiable_gate_pass_rows_never_read_as_pass(self):
        self.fake_all_gates_pass()
        report = execution.status(self.proj)
        self.assertNotEqual("PASS", report["overall"])
        self.assertTrue(report["blockers"])
        self.assertIn("G1", json.dumps(report["gates"]))
        self.assertNotEqual("PASS", report["gates"]["G1"]["verified"])

    def test_pending_phases_and_not_run_finals_block_a_pass(self):
        self.fake_all_gates_pass()
        report = execution.status(self.proj)
        self.assertIn("phase", " ".join(report["blockers"]).lower())
        self.assertNotEqual("PASS", report["overall"])

    def test_requirement_verdicts_pointing_at_nothing_are_blockers(self):
        self.replace("01_REQUIREMENTS.md", "|---|---|---|---|---|---|",
                     "|---|---|---|---|---|---|\n| R-1 | functional | must | a claim | test | none |")
        self.replace("06_VERIFICATION.md", "| Requirement ID | Verdict | Evidence |\n|---|---|---|",
                     "| Requirement ID | Verdict | Evidence |\n|---|---|---|\n"
                     "| R-1 | PASS | [logs/nope.json](logs/nope.json) |")
        report = execution.status(self.proj)
        self.assertIn("evidence", " ".join(report["blockers"]).lower())
        self.assertNotEqual("PASS", report["overall"])

    def test_a_malformed_reconciliation_document_does_not_crash_the_report(self):
        recon = os.path.join(self.proj, "logs", "reconciliation")
        os.makedirs(recon, exist_ok=True)
        with open(os.path.join(recon, "bad.json"), "w", encoding="utf-8") as handle:
            handle.write("[]")
        report = execution.status(self.proj)
        self.assertEqual("UNKNOWN", report["artifacts"]["reports"][0]["verdict"])
        self.assertNotEqual("PASS", report["overall"])

    def test_no_artifact_evidence_at_all_cannot_be_a_completed_delivery(self):
        report = execution.status(self.proj)
        self.assertEqual("NOT_RUN", report["artifacts"]["status"])
        self.assertNotEqual("PASS", report["overall"])


# =====================================================================
# class 7/8 — A8 measurement may not invent evidence
# =====================================================================
class MeasurementTruthTests(Workspace):
    profile = "startup-reversible"

    def setUp(self):
        super().setUp()
        self.typed_pass("G1")

    def unsupported(self):
        record = execution.collect_measurement(self.proj, deliverable="pilot doc")
        record["technical"]["invocations"] = -1
        record["collected_at"] = "not-a-date"
        record["baseline"] = {"status": "MEASURED", "window": "", "unit": "", "value": None,
                              "source": None}
        record["product_fit"]["acceptance"] = "PASS"
        record["claimed_improvement_pct"] = 999
        return record

    def test_the_unsupported_999_percent_claim_is_refused(self):
        with self.assertRaises(execution.ManifestError):
            execution.validate_measurement(self.unsupported())

    def test_negative_invocation_counts_are_refused(self):
        record = execution.collect_measurement(self.proj, deliverable="d")
        record["technical"]["invocations"] = -1
        with self.assertRaises(execution.ManifestError) as caught:
            execution.validate_measurement(record)
        self.assertIn("invocations", str(caught.exception))

    def test_a_bad_collection_date_is_refused(self):
        record = execution.collect_measurement(self.proj, deliverable="d")
        record["collected_at"] = "2026-13-45"
        with self.assertRaises(execution.ManifestError) as caught:
            execution.validate_measurement(record)
        self.assertIn("collected_at", str(caught.exception))

    def test_a_measured_baseline_must_state_window_unit_value_and_source(self):
        record = execution.collect_measurement(self.proj, deliverable="d")
        record["baseline"] = {"status": "MEASURED", "window": None, "unit": None,
                              "value": None, "source": None}
        with self.assertRaises(execution.ManifestError) as caught:
            execution.validate_measurement(record)
        self.assertIn("baseline", str(caught.exception))

    def test_an_improvement_over_100_percent_is_refused(self):
        record = execution.collect_measurement(self.proj, deliverable="d")
        record["baseline"] = {"status": "MEASURED", "window": "2026-08", "unit": "minutes",
                              "value": 100.0, "source": "logs/runner-ledger.csv"}
        record["product_fit"]["acceptance"] = "PASS"
        record["claimed_improvement_pct"] = 999
        with self.assertRaises(execution.ManifestError) as caught:
            execution.validate_measurement(record)
        self.assertIn("100", str(caught.exception))

    def test_acceptance_from_a_string_is_reported_as_claimed_not_verified(self):
        record = execution.collect_measurement(self.proj, deliverable="d")
        record["product_fit"]["acceptance"] = "PASS"
        report = execution.validate_measurement(record)
        self.assertEqual("CLAIMED_UNVERIFIED", report["product_fit"])
        self.assertEqual("NOT_RUN", report["actual_human_acceptance"])

    def test_an_aborted_run_that_produced_nothing_has_no_time_to_artifact(self):
        with open(self.ledger, "a", encoding="utf-8") as handle:
            handle.write("2026-01-01T00:00:00Z,STARTED,INV-0001,P3,steve,S-1,,\n")
            handle.write("2026-01-01T00:00:10Z,ABORTED,INV-0001,P3,steve,S-1,,10.0\n")
        record = execution.collect_measurement(self.proj, deliverable="d")
        self.assertIsNone(record["technical"]["time_to_artifact_seconds"])
        self.assertEqual(10.0, record["technical"]["child_process_wall_seconds_total"])
        self.assertEqual(1, record["technical"]["aborted"])

    def test_a_cost_ledger_with_the_wrong_header_is_unknown_not_zero(self):
        with open(os.path.join(self.proj, "logs", "cost-ledger.csv"), "w", encoding="utf-8") as handle:
            handle.write("when,what\n2026-01-01,stuff\n")
        record = execution.collect_measurement(self.proj, deliverable="d")
        self.assertIsNone(record["technical"]["llm_calls"])
        self.assertIsNone(record["technical"]["input_tokens"])
        self.assertEqual("UNPARSABLE", record["technical"]["cost_source"])

    def test_cost_amount_is_null_while_billing_is_unknown(self):
        record = execution.collect_measurement(self.proj, deliverable="d")
        self.assertIsNone(record["cost"]["amount"])
        self.assertEqual("unknown", record["cost"]["billing"])
        execution.validate_measurement(record)


# =====================================================================
# class 9 — A7 freezing is a caller-pinned digest, not a self-hash
# =====================================================================
class EvaluatorFreezeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="ldl-v070-freeze-")

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def contract(self, verdict="PARTIAL_CREDIT"):
        doc = {"schema": "ldl-evaluator-contract-v1", "contract_version": "v1",
               "scope": "evaluation-only", "frozen_at": utc(-3600), "frozen_sha256": "",
               "truth_table": [{"case": "zero", "condition": "0 proposals", "verdict": "FAIL"},
                               {"case": "missing", "condition": "field absent", "verdict": "FAIL"},
                               {"case": "partial", "condition": "1 proposal + dependency",
                                "verdict": verdict},
                               {"case": "complete", "condition": "1 proposal, all fields",
                                "verdict": "PASS"}],
               "aggregate": {"method": "per-item-mean", "judges": 2, "tie_break": "owner decides"},
               "penalty": {"applied_at": "judge-item-score", "double_count": "forbidden",
                           "max_applications": 1},
               "dispute": {"threshold": 2, "authority": "Daniel", "authority_kind": "actual-human"}}
        doc["frozen_sha256"] = execution.canonical_digest(doc)
        path = os.path.join(self.tmp, f"evaluator-{verdict}.json")
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(doc, handle)
        return path, doc["frozen_sha256"]

    def test_without_a_caller_pin_the_freeze_is_unbound_not_frozen(self):
        path, _ = self.contract()
        report = execution.validate_evaluator_contract(path)
        self.assertEqual("PASS", report["verdict"])
        self.assertEqual("UNBOUND", report["freeze"])
        self.assertEqual("NOT_RUN", report["freeze_verification"])

    def test_a_mutated_and_rehashed_contract_fails_the_original_pin(self):
        _, original = self.contract()
        mutated, rehashed = self.contract(verdict="PASS")
        self.assertNotEqual(original, rehashed)
        with self.assertRaises(execution.ManifestError) as caught:
            execution.validate_evaluator_contract(mutated, expected_sha256=original)
        self.assertIn("pinned", str(caught.exception))

    def test_the_matching_pin_reports_bound(self):
        path, digest = self.contract()
        report = execution.validate_evaluator_contract(path, expected_sha256=digest)
        self.assertEqual("BOUND", report["freeze"])
        self.assertEqual("PASS", report["freeze_verification"])

    def test_the_cli_exercises_both_directions(self):
        path, digest = self.contract()
        ok = subprocess.run([sys.executable, EXECUTION, "evaluator-validate", path,
                             "--expected-sha256", digest], text=True, capture_output=True)
        self.assertEqual(0, ok.returncode, ok.stderr)
        self.assertIn("BOUND", ok.stdout)
        bad = subprocess.run([sys.executable, EXECUTION, "evaluator-validate", path,
                              "--expected-sha256", "0" * 64], text=True, capture_output=True)
        self.assertEqual(1, bad.returncode)
        self.assertIn("EXECUTION REFUSED", bad.stdout)


# =====================================================================
# class 11 — A1 documentation states the shipped surface
# =====================================================================
class DocumentationTests(unittest.TestCase):
    def readme(self):
        with open(os.path.join(ROOT, "README.md"), encoding="utf-8") as handle:
            return handle.read()

    def test_installation_lists_every_shipped_tool(self):
        text = self.readme()
        for tool in ("scaffold.py", "workflow.py", "lint.py", "lean.py", "integrity.py",
                     "policy.py", "invoke.py", "execution.py"):
            self.assertIn(tool, text, f"README does not list {tool}")

    def test_quickstart_shows_the_runnable_commands(self):
        text = self.readme()
        for fragment in ("invoke.py run", "execution.py status", "execution.py reconcile",
                         "execution.py evaluator-validate", "execution.py measure-collect",
                         "--migrate-v070"):
            self.assertIn(fragment, text, f"README quickstart is missing {fragment}")

    def test_migration_is_documented_as_opt_in(self):
        text = self.readme()
        window = text[text.index("--migrate-v070") - 400:text.index("--migrate-v070") + 400]
        self.assertIn("opt-in", window.lower())

    def test_authority_separates_binding_from_authentication(self):
        with open(os.path.join(ROOT, "AUTHORITY.md"), encoding="utf-8") as handle:
            text = handle.read()
        self.assertIn("not human authentication", text)
        self.assertIn("not an OS sandbox", text)


if __name__ == "__main__":
    unittest.main(verbosity=1)
