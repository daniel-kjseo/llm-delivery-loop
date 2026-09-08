"""v0.7.0 — the harness must compose policy with the profile, bind what it
launches to an approval it did not write, and separate process from artifact.

v0.6.1 gated invocation with one hardcoded table: P4 always demanded G2 and
P5/P6 always demanded G3, whatever the delivery profile said. A startup
reversible project could therefore never reach its own MVP work, while the
"gate is closed" message looked correct. Everything here is harness-local: no
model call, no network, no write outside a tempfile fixture.
"""
import csv
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from datetime import datetime, timedelta, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tools"))

import execution  # noqa: E402
import invoke  # noqa: E402
import policy  # noqa: E402
import scaffold  # noqa: E402
import workflow  # noqa: E402

INVOKE = os.path.join(ROOT, "tools", "invoke.py")
EXECUTION = os.path.join(ROOT, "tools", "execution.py")


def utc(offset_seconds=0):
    stamp = datetime.now(timezone.utc) + timedelta(seconds=offset_seconds)
    return stamp.strftime("%Y-%m-%dT%H:%M:%SZ")


class Workspace(unittest.TestCase):
    """One scaffolded workspace per test, with the real gate-apply path."""

    profile = "startup-reversible"

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="ldl-v070-")
        self.ws = os.path.join(self.tmp, "ws")
        scaffold.init(self.ws)
        self.proj = scaffold.new_project(self.ws, "pilot", "2026-01-01", self.profile)
        self.ledger = os.path.join(self.proj, "logs", "runner-ledger.csv")
        self.sentinel = os.path.join(self.tmp, "sentinel.txt")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    # -- fixture helpers --------------------------------------------------
    def read(self, rel):
        with open(os.path.join(self.proj, rel), encoding="utf-8") as handle:
            return handle.read()

    def replace(self, rel, old, new):
        text = self.read(rel)
        assert old in text, f"fixture drift: {old!r} not in {rel}"
        with open(os.path.join(self.proj, rel), "w", encoding="utf-8") as handle:
            handle.write(text.replace(old, new))

    def phase_done(self, *phases):
        for phase in phases:
            self.replace("PROGRESS.md", f"| {phase} | pending | |", f"| {phase} | done | 2026-01-01 |")

    def typed_pass(self, gate):
        """Pass one gate through gate-apply, completing the phases it owns."""
        pending = {"P0 contract": "G1", "P1 requirements": "G2", "P2 structure": "G2",
                   "P3 research": "G2", "P4 scoping": "G3"}
        todo = [phase for phase, owner in pending.items() if owner == gate
                and f"| {phase} | pending | |" in self.read("PROGRESS.md")]
        self.phase_done(*todo)
        contract = os.path.join(self.proj, "00_CONTRACT.md")
        with open(contract, "rb") as handle:
            digest = hashlib.sha256(handle.read()).hexdigest()
        decision = {
            "schema": "ldl-gate-decision-v1", "gate": gate, "contract_version": "v1",
            "verdict": "PASS", "approval_mode": "human", "approver": "Daniel",
            "decided_at": "2026-01-01T00:00:00Z", "reason": "criteria are met",
            "evidence": [{"path": "00_CONTRACT.md", "sha256": digest}],
        }
        path = os.path.join(self.tmp, f"decision-{gate.lower()}.json")
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(decision, handle)
        workflow.gate_apply(self.proj, path)

    def dummy_command(self, target=None):
        target = target or self.sentinel
        return [sys.executable, "-c", f"open({target!r}, 'w').write('ok')"]

    def run_invoke(self, phase="P3", runner_id="steve", command=None, **kwargs):
        return invoke.run(self.proj, phase, runner_id, "S-1", command or self.dummy_command(), **kwargs)

    def ledger_events(self):
        if not os.path.isfile(self.ledger):
            return []
        with open(self.ledger, encoding="utf-8") as handle:
            return list(csv.DictReader(handle))

    def counts(self):
        events = self.ledger_events()
        return tuple(sum(1 for row in events if row["event"] == kind)
                     for kind in ("STARTED", "COMPLETED", "ABORTED"))

    def refused(self, fragment, **kwargs):
        before = self.counts()
        with self.assertRaises(SystemExit) as caught:
            self.run_invoke(**kwargs)
        self.assertIn(fragment, str(caught.exception))
        self.assertFalse(os.path.exists(self.sentinel), "refused invocation still launched the command")
        self.assertEqual(before, self.counts(), "refused invocation touched the ledger")


# =====================================================================
# 1. profile-aware launch policy
# =====================================================================
class StartupPolicyTests(Workspace):
    """startup-reversible: typed G1 opens its own MVP engineering."""

    profile = "startup-reversible"

    def test_profile_is_read_from_the_contract_not_assumed(self):
        self.assertEqual("startup-reversible", policy.delivery_mode(self.proj))

    def test_p4_after_typed_g1_and_launch_documents_is_allowed(self):
        self.typed_pass("G1")
        self.phase_done("P1 requirements", "P2 structure", "P3 research")
        self.assertEqual(0, self.run_invoke(phase="P4"))
        self.assertTrue(os.path.exists(self.sentinel))
        self.assertEqual((1, 1, 0), self.counts())

    def test_p4_without_g1_is_still_refused(self):
        self.phase_done("P1 requirements", "P2 structure", "P3 research")
        self.refused("G1", phase="P4")

    def test_p4_with_g1_but_incomplete_launch_documents_is_refused(self):
        self.typed_pass("G1")
        self.phase_done("P1 requirements")
        self.refused("P2 structure", phase="P4")

    def test_p5_needs_scope_done_and_then_runs_without_g2_or_g3(self):
        self.typed_pass("G1")
        self.phase_done("P1 requirements", "P2 structure", "P3 research")
        self.refused("P4 scoping", phase="P5")
        self.phase_done("P4 scoping")
        self.assertEqual(0, self.run_invoke(phase="P5"))
        gates = {row["Gate"]: row["Verdict"] for row in
                 workflow.markdown_table(self.read("PROGRESS.md"), "Gate ledger", workflow.GATE_COLUMNS)[1]}
        self.assertEqual("PENDING", gates["G2"])
        self.assertEqual("PENDING", gates["G3"])

    def test_startup_declaring_high_risk_loses_the_reversible_shortcut(self):
        self.replace("00_CONTRACT.md", "- Risk: low-reversible", "- Risk: high-risk")
        self.typed_pass("G1")   # the gate is honest; the launch brief is not reversible
        self.phase_done("P1 requirements", "P2 structure", "P3 research", "P4 scoping")
        self.refused("low-reversible", phase="P5")

    def test_p0_initial_preparation_stays_open(self):
        self.assertEqual(0, self.run_invoke(phase="P0"))
        self.assertTrue(os.path.exists(self.sentinel))

    def test_reachability_start_to_result_is_composable(self):
        """One project walks P0 -> P3 -> P4 -> P5 -> P6 through official ops."""
        reached = []
        for phase, prepare in (("P0", lambda: None),
                               ("P3", lambda: self.typed_pass("G1")),
                               ("P4", lambda: self.phase_done("P1 requirements", "P2 structure", "P3 research")),
                               ("P5", lambda: self.phase_done("P4 scoping")),
                               ("P6", lambda: None)):
            prepare()
            target = os.path.join(self.tmp, f"out-{phase}.txt")
            self.assertEqual(0, self.run_invoke(phase=phase, command=self.dummy_command(target)),
                             f"{phase} unreachable for {self.profile}")
            reached.append(phase)
        self.assertEqual(["P0", "P3", "P4", "P5", "P6"], reached)
        self.assertEqual((5, 5, 0), self.counts())

    def test_release_controls_are_not_relaxed_by_the_runner_policy(self):
        """Reaching P6 never writes a release verdict; lean.py still owns it."""
        self.typed_pass("G1")
        self.phase_done("P1 requirements", "P2 structure", "P3 research", "P4 scoping")
        self.run_invoke(phase="P6")
        releases = workflow.markdown_table(self.read("PROGRESS.md"), "Release ledger",
                                           ["Release", "Verdict", "Increment", "Risk", "Instrumentation",
                                            "Feedback", "Rollback", "Live artifact", "Approver",
                                            "Released at", "Evidence"])[1]
        self.assertEqual("PENDING", releases[0]["Verdict"])


class HighRiskPolicyTests(Workspace):
    """gated-high-risk keeps every predecessor gate it had in v0.6.1."""

    profile = "gated-high-risk"

    def test_p4_requires_g2_even_after_g1(self):
        """v0.6.1's safety test, now aimed at the profile that actually means it."""
        self.typed_pass("G1")
        self.refused("G2", phase="P4")

    def test_p5_requires_g3_even_after_g1_and_g2(self):
        self.typed_pass("G1")
        self.typed_pass("G2")
        self.refused("G3", phase="P5")

    def test_full_predecessor_chain_reaches_p5(self):
        self.typed_pass("G1")
        self.typed_pass("G2")
        self.typed_pass("G3")
        self.assertEqual(0, self.run_invoke(phase="P5"))

    def test_high_risk_cannot_borrow_the_startup_shortcut_by_editing_risk_line(self):
        self.replace("00_CONTRACT.md", "- Risk: high-risk", "- Risk: low-reversible")
        self.typed_pass("G1")
        self.refused("G2", phase="P4")


class PortfolioPolicyTests(Workspace):
    profile = "portfolio-competition"

    def test_portfolio_p4_still_requires_g2(self):
        self.typed_pass("G1")
        self.refused("G2", phase="P4")

    def test_portfolio_p5_still_requires_g3(self):
        self.typed_pass("G1")
        self.typed_pass("G2")
        self.refused("G3", phase="P5")


class PreEngineeringPolicyTests(Workspace):
    profile = "pre-engineering-decision"

    def test_engineering_phases_are_denied_by_the_profile_itself(self):
        self.typed_pass("G1")
        self.typed_pass("G2")
        self.refused("pre-engineering-decision", phase="P5")

    def test_p4_decision_work_is_reachable_through_g2(self):
        self.typed_pass("G1")
        self.typed_pass("G2")
        self.assertEqual(0, self.run_invoke(phase="P4"))


class GateRevalidationTests(Workspace):
    """A PASS row is evidence about a contract, a phase and its predecessors."""

    profile = "startup-reversible"

    def test_gate_decided_under_a_stale_contract_version_is_refused(self):
        self.typed_pass("G1")
        self.replace("00_CONTRACT.md", "- Contract version: v1", "- Contract version: v2")
        self.refused("contract", phase="P3")

    def test_gate_pass_whose_owned_phase_regressed_is_refused(self):
        self.typed_pass("G1")
        self.replace("PROGRESS.md", "| P0 contract | done | 2026-01-01 |", "| P0 contract | pending | |")
        self.refused("P0 contract", phase="P3")

    def test_later_gate_pass_without_its_predecessor_pass_is_refused(self):
        self.typed_pass("G1")
        self.typed_pass("G2")
        self.replace("PROGRESS.md", "| G1 | PASS |", "| G1 | HOLD |")
        self.refused("G1", phase="P4")

    def test_tampered_gate_evidence_is_still_refused(self):
        self.typed_pass("G1")
        with open(os.path.join(self.proj, "00_CONTRACT.md"), "a", encoding="utf-8") as handle:
            handle.write("\nedited after the gate passed\n")
        self.refused("G1", phase="P3")

    def test_unknown_delivery_mode_denies_rather_than_defaults(self):
        self.typed_pass("G1")
        self.replace("00_CONTRACT.md", "- Delivery mode: startup-reversible", "- Delivery mode: freestyle")
        self.refused("delivery profile", phase="P3")


# =====================================================================
# 2. approved-job interface
# =====================================================================
class ApprovedJobTests(Workspace):
    profile = "startup-reversible"

    def setUp(self):
        super().setUp()
        self.typed_pass("G1")
        self.approvals = os.path.join(self.tmp, "owner-approvals")   # outside the project
        os.makedirs(self.approvals)
        self.out_root = "05_engineering/evidence/increments"
        self.command = self.dummy_command(os.path.join(self.proj, self.out_root, "a.txt"))

    def job_dict(self, **overrides):
        with open(os.path.join(self.proj, "00_CONTRACT.md"), "rb") as handle:
            contract_sha = hashlib.sha256(handle.read()).hexdigest()
        job = {
            "schema": "ldl-approved-job-v1",
            "project": os.path.realpath(self.proj),
            "contract_version": "v1",
            "contract_sha256": contract_sha,
            "profile": "startup-reversible",
            "phase": "P3",
            "argv_sha256": execution.argv_digest(self.command),
            "runner_id": "steve",
            "runner_role": "runner",
            "cwd": os.path.realpath(self.proj),
            "output_root": self.out_root,
        }
        job.update(overrides)
        return job

    def write_job(self, **overrides):
        path = os.path.join(self.tmp, "job.json")
        payload = json.dumps(self.job_dict(**overrides), indent=2, sort_keys=True) + "\n"
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(payload)
        return path, hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def approve(self, digest, approver="Elon (AI owner proxy)"):
        record = {"schema": "ldl-job-approval-v1", "job_sha256": digest, "approver": approver,
                  "approval_mode": "delegated-agent", "decided_at": utc(-60)}
        with open(os.path.join(self.approvals, digest + ".json"), "w", encoding="utf-8") as handle:
            json.dump(record, handle)

    def run_invoke(self, phase="P3", runner_id="steve", command=None, **kwargs):
        """Every job in this class declares the project as its cwd."""
        if kwargs.get("job") and "cwd" not in kwargs:
            kwargs["cwd"] = os.path.realpath(self.proj)
        return super().run_invoke(phase=phase, runner_id=runner_id, command=command, **kwargs)

    def launch(self, job, **kwargs):
        kwargs.setdefault("approvals_root", self.approvals)
        kwargs.setdefault("command", self.command)
        return self.run_invoke(phase="P3", job=job, **kwargs)

    # -- the happy path actually launches ---------------------------------
    def test_approved_job_launches_and_is_recorded(self):
        job, digest = self.write_job()
        self.approve(digest)
        self.assertEqual(0, self.launch(job))
        self.assertEqual((1, 1, 0), self.counts())
        records = [json.loads(line) for line in
                   open(os.path.join(self.proj, "logs", "approved-jobs.jsonl"), encoding="utf-8")]
        self.assertEqual(1, len(records))
        self.assertEqual(digest, records[0]["job_sha256"])
        self.assertEqual("approved-job", records[0]["enforcement"])

    def test_pinned_digest_from_the_launcher_is_an_accepted_trust_root(self):
        job, digest = self.write_job()
        self.assertEqual(0, self.launch(job, approvals_root=None, pinned=digest))

    # -- the trust root is never the manifest itself ----------------------
    def test_self_attested_approval_key_is_rejected(self):
        job, digest = self.write_job(approved=True)
        self.approve(digest)
        self.refused("schema", job=job, command=self.command, approvals_root=self.approvals)

    def test_job_without_any_external_trust_root_is_refused(self):
        job, _ = self.write_job()
        self.refused("trust root", job=job, command=self.command)

    def test_approvals_root_inside_the_project_is_refused(self):
        inside = os.path.join(self.proj, "raw", "approvals")
        os.makedirs(inside)
        job, digest = self.write_job()
        self.approvals = inside
        self.approve(digest)
        self.refused("trust root", job=job, command=self.command, approvals_root=inside)

    def test_unapproved_job_is_refused(self):
        job, _ = self.write_job()
        self.refused("no approval", job=job, command=self.command, approvals_root=self.approvals)

    # -- tamper / mismatch / escape ---------------------------------------
    def test_manifest_edited_after_approval_is_refused(self):
        job, digest = self.write_job()
        self.approve(digest)
        with open(job, "a", encoding="utf-8") as handle:
            handle.write("\n")
        self.refused("no approval", job=job, command=self.command, approvals_root=self.approvals)

    def test_argv_that_differs_from_the_approved_command_is_refused(self):
        job, digest = self.write_job()
        self.approve(digest)
        other = self.dummy_command(os.path.join(self.tmp, "elsewhere.txt"))
        self.refused("argv", job=job, command=other, approvals_root=self.approvals)

    def test_phase_mismatch_is_refused(self):
        job, digest = self.write_job(phase="P0")
        self.approve(digest)
        self.refused("phase", job=job, command=self.command, approvals_root=self.approvals)

    def test_runner_id_mismatch_is_refused(self):
        job, digest = self.write_job(runner_id="someone-else")
        self.approve(digest)
        self.refused("runner_id", job=job, command=self.command, approvals_root=self.approvals)

    def test_maker_runner_role_is_refused(self):
        job, digest = self.write_job(runner_role="maker")
        self.approve(digest)
        self.refused("runner_role", job=job, command=self.command, approvals_root=self.approvals)

    def test_job_bound_to_a_different_contract_is_refused(self):
        job, digest = self.write_job(contract_sha256="0" * 64)
        self.approve(digest)
        self.refused("contract_sha256", job=job, command=self.command, approvals_root=self.approvals)

    def test_contract_edited_after_approval_is_refused_by_something(self):
        """Two independent checks cover this; the gate happens to speak first."""
        job, digest = self.write_job()
        self.approve(digest)
        with open(os.path.join(self.proj, "00_CONTRACT.md"), "a", encoding="utf-8") as handle:
            handle.write("\nlate edit\n")
        self.refused("00_CONTRACT.md", job=job, command=self.command, approvals_root=self.approvals)
        with self.assertRaises(execution.ManifestError) as caught:
            execution.check_job(self.proj, "P3", "steve", self.command, job,
                                approvals_root=self.approvals, cwd=os.path.realpath(self.proj))
        self.assertIn("contract_sha256", str(caught.exception))

    def test_profile_mismatch_is_refused(self):
        job, digest = self.write_job(profile="gated-high-risk")
        self.approve(digest)
        self.refused("profile", job=job, command=self.command, approvals_root=self.approvals)

    def test_project_mismatch_is_refused(self):
        job, digest = self.write_job(project=os.path.realpath(self.tmp))
        self.approve(digest)
        self.refused("project", job=job, command=self.command, approvals_root=self.approvals)

    def test_cwd_mismatch_is_refused(self):
        job, digest = self.write_job(cwd=os.path.realpath(self.tmp))
        self.approve(digest)
        self.refused("cwd", job=job, command=self.command, approvals_root=self.approvals)

    def test_output_root_escaping_the_project_is_refused(self):
        job, digest = self.write_job(output_root="../escape")
        self.approve(digest)
        self.refused("output_root", job=job, command=self.command, approvals_root=self.approvals)

    def test_absolute_output_root_is_refused(self):
        job, digest = self.write_job(output_root=self.tmp)
        self.approve(digest)
        self.refused("output_root", job=job, command=self.command, approvals_root=self.approvals)

    def test_symlinked_output_root_is_refused(self):
        link = os.path.join(self.proj, "raw", "sneak")
        os.symlink(self.tmp, link)
        job, digest = self.write_job(output_root="raw/sneak")
        self.approve(digest)
        self.refused("output_root", job=job, command=self.command, approvals_root=self.approvals)

    # -- type confusion and empties ---------------------------------------
    def test_type_confused_fields_are_refused(self):
        for field, value in (("phase", ["P3"]), ("runner_id", 7), ("output_root", None),
                             ("argv_sha256", {"x": 1}), ("contract_version", 1)):
            job, digest = self.write_job(**{field: value})
            self.approve(digest)
            with self.subTest(field=field):
                self.refused(field, job=job, command=self.command, approvals_root=self.approvals)

    def test_empty_and_missing_manifest_are_refused(self):
        empty = os.path.join(self.tmp, "empty.json")
        open(empty, "w").close()
        self.refused("unreadable", job=empty, command=self.command, approvals_root=self.approvals)
        self.refused("unreadable", job=os.path.join(self.tmp, "nope.json"),
                     command=self.command, approvals_root=self.approvals)

    def test_gate_policy_still_applies_to_an_approved_job(self):
        """An approval never buys a gate it does not have."""
        job, digest = self.write_job(phase="P4")
        self.approve(digest)
        self.refused("P1 requirements", phase="P4", job=job, command=self.command,
                     approvals_root=self.approvals)

    # -- honesty about what this is ---------------------------------------
    def test_legacy_invocation_is_labelled_limited(self):
        stdout = self.capture(lambda: self.run_invoke(phase="P3"))
        self.assertIn("ENFORCEMENT", stdout)
        self.assertIn("legacy", stdout)
        self.assertIn("limited", stdout)

    def test_approved_invocation_disclaims_sandbox_and_authentication(self):
        job, digest = self.write_job()
        self.approve(digest)
        stdout = self.capture(lambda: self.launch(job))
        self.assertIn("approved-job", stdout)
        self.assertNotIn("sandboxed", stdout.lower())
        self.assertIn("not an OS sandbox", stdout)
        self.assertIn("not human authentication", stdout)

    def capture(self, call):
        import io
        import contextlib
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            call()
        return buffer.getvalue()


# =====================================================================
# 3. atomic reservation under a project lock
# =====================================================================
class ConcurrencyTests(Workspace):
    profile = "startup-reversible"

    def setUp(self):
        super().setUp()
        self.typed_pass("G1")

    def test_platform_support_is_declared_not_implied(self):
        self.assertIn(execution.LOCK_PLATFORM, {"posix-flock", "unsupported"})
        if os.name != "posix":
            self.assertEqual("unsupported", execution.LOCK_PLATFORM)

    @unittest.skipUnless(os.name == "posix", "project lock requires POSIX flock")
    def test_eight_real_processes_reserve_eight_unique_ids_and_one_header(self):
        os.remove(self.ledger)  # force the header race too
        workers = []
        for index in range(8):
            workers.append(subprocess.Popen(
                [sys.executable, INVOKE, "run", self.proj, "--phase", "P3",
                 "--runner-id", f"steve{index}", "--session", "S-1", "--",
                 sys.executable, "-c", "import time; time.sleep(0.25)"],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE))
        for worker in workers:
            self.assertEqual(0, worker.wait(timeout=120), worker.communicate()[1].decode())
        with open(self.ledger, encoding="utf-8") as handle:
            lines = [line for line in handle.read().splitlines() if line.strip()]
        header = "timestamp,event,invocation_id,phase,runner_id,session,exit_code,wall_seconds"
        self.assertEqual(1, lines.count(header), "header written more than once")
        self.assertEqual(header, lines[0])
        rows = list(csv.DictReader(lines))
        started = [row["invocation_id"] for row in rows if row["event"] == "STARTED"]
        completed = [row["invocation_id"] for row in rows if row["event"] == "COMPLETED"]
        self.assertEqual(8, len(started))
        self.assertEqual(8, len(set(started)), f"duplicate invocation IDs: {sorted(started)}")
        self.assertEqual(sorted(started), sorted(completed))

    def test_launch_failure_is_never_recorded_as_a_completion(self):
        missing = os.path.join(self.tmp, "definitely-not-a-program")
        code = self.run_invoke(command=[missing])
        self.assertNotEqual(0, code)
        self.assertEqual((1, 0, 1), self.counts())
        self.assertEqual("", self.ledger_events()[1]["exit_code"])

    def test_nonzero_exit_is_a_completion_not_an_abort(self):
        self.assertEqual(7, self.run_invoke(command=[sys.executable, "-c", "raise SystemExit(7)"]))
        self.assertEqual((1, 1, 0), self.counts())
        self.assertEqual("7", self.ledger_events()[1]["exit_code"])

    @unittest.skipUnless(os.name == "posix", "process groups require POSIX")
    def test_abort_kills_the_whole_process_tree(self):
        marker = os.path.join(self.tmp, "orphan.txt")
        child = (f"import subprocess,sys,time;"
                 f"subprocess.Popen([sys.executable,'-c',"
                 f"\"import time;time.sleep(30);open({marker!r},'w').write('orphan')\"]);"
                 f"time.sleep(30)")
        process = subprocess.Popen(
            [sys.executable, INVOKE, "run", self.proj, "--phase", "P3", "--runner-id", "steve",
             "--session", "S-1", "--", sys.executable, "-c", child],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline and self.counts()[0] != 1:
            time.sleep(0.05)
        self.assertEqual(1, self.counts()[0], "STARTED row never appeared")
        time.sleep(0.5)
        process.terminate()
        process.wait(timeout=30)
        self.assertEqual((1, 0, 1), self.counts())
        time.sleep(1.0)
        self.assertFalse(os.path.exists(marker), "grandchild survived the abort")


# =====================================================================
# 4. expected-output manifest and reconciliation
# =====================================================================
class ReconciliationTests(Workspace):
    profile = "startup-reversible"

    def setUp(self):
        super().setUp()
        self.out_dir = os.path.join(self.proj, "05_engineering", "evidence", "increments")
        self.manifest_path = os.path.join(self.tmp, "expected.json")

    def manifest(self, outputs, job_id="JOB-1", output_root="05_engineering/evidence/increments"):
        payload = {"schema": "ldl-expected-output-v1", "job_id": job_id,
                   "output_root": output_root, "outputs": outputs}
        with open(self.manifest_path, "w", encoding="utf-8") as handle:
            json.dump(payload, handle)
        return self.manifest_path

    def write_output(self, name, text):
        path = os.path.join(self.out_dir, name)
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(text)
        return path

    def entry(self, **kwargs):
        base = {"id": "OUT-01", "path": "a.md", "format": "markdown", "min_bytes": 1}
        base.update(kwargs)
        return base

    def reconcile(self, manifest, not_before=None):
        return execution.reconcile(self.proj, manifest, not_before=not_before)

    def test_valid_fresh_outputs_pass_but_stay_separate_from_acceptance(self):
        self.write_output("a.md", "# candidate\n")
        report = self.reconcile(self.manifest([self.entry()]), not_before=time.time() - 60)
        self.assertTrue(report["artifact_valid"])
        self.assertEqual("CHECKED", report["freshness"])
        self.assertEqual("NOT_RUN", report["semantic_acceptance"])
        self.assertEqual("NOT_RUN", report["user_acceptance"])
        self.assertIsNone(report["process_complete"], "process state is the caller's, not the manifest's")

    def test_missing_output_fails(self):
        report = self.reconcile(self.manifest([self.entry()]), not_before=time.time() - 60)
        self.assertFalse(report["artifact_valid"])
        self.assertEqual("MISSING", report["outputs"][0]["status"])

    def test_empty_output_fails(self):
        self.write_output("a.md", "")
        report = self.reconcile(self.manifest([self.entry()]), not_before=time.time() - 60)
        self.assertEqual("EMPTY", report["outputs"][0]["status"])

    def test_stale_preexisting_output_is_not_reused(self):
        path = self.write_output("a.md", "# older than the run\n")
        old = time.time() - 3600
        os.utime(path, (old, old))
        report = self.reconcile(self.manifest([self.entry()]), not_before=time.time() - 60)
        self.assertFalse(report["artifact_valid"])
        self.assertEqual("STALE", report["outputs"][0]["status"])

    def test_freshness_unknown_can_never_read_as_pass(self):
        self.write_output("a.md", "# candidate\n")
        report = self.reconcile(self.manifest([self.entry()]))
        self.assertEqual("NOT_CHECKED", report["freshness"])
        self.assertEqual("INCOMPLETE", report["verdict"])
        self.assertFalse(report["artifact_valid"])

    def test_collided_ids_and_paths_fail(self):
        self.write_output("a.md", "x\n")
        duplicate_id = self.manifest([self.entry(), self.entry(path="b.md")])
        with self.assertRaises(execution.ManifestError) as caught:
            self.reconcile(duplicate_id, not_before=time.time() - 60)
        self.assertIn("duplicate output id", str(caught.exception))
        duplicate_path = self.manifest([self.entry(), self.entry(id="OUT-02")])
        with self.assertRaises(execution.ManifestError) as caught:
            self.reconcile(duplicate_path, not_before=time.time() - 60)
        self.assertIn("duplicate output path", str(caught.exception))

    def test_output_escaping_the_declared_root_fails(self):
        manifest = self.manifest([self.entry(path="../../../../escape.md")])
        report = self.reconcile(manifest, not_before=time.time() - 60)
        self.assertEqual("ESCAPED", report["outputs"][0]["status"])

    def test_malformed_json_output_fails(self):
        self.write_output("a.json", "{not json")
        manifest = self.manifest([self.entry(path="a.json", format="json")])
        report = self.reconcile(manifest, not_before=time.time() - 60)
        self.assertEqual("MALFORMED", report["outputs"][0]["status"])

    def test_wrong_declared_schema_or_id_fails(self):
        self.write_output("a.json", json.dumps({"schema": "other-v1", "id": "OUT-01"}))
        manifest = self.manifest([self.entry(path="a.json", format="json", json_schema="mine-v1")])
        self.assertEqual("WRONG_SCHEMA", self.reconcile(manifest, not_before=time.time() - 60)["outputs"][0]["status"])
        self.write_output("a.json", json.dumps({"schema": "mine-v1", "id": "OUT-99"}))
        manifest = self.manifest([self.entry(path="a.json", format="json", json_schema="mine-v1",
                                             json_id_field="id", json_id="OUT-01")])
        self.assertEqual("WRONG_ID", self.reconcile(manifest, not_before=time.time() - 60)["outputs"][0]["status"])

    def test_declared_hash_mismatch_fails(self):
        self.write_output("a.md", "# candidate\n")
        manifest = self.manifest([self.entry(sha256="0" * 64)])
        self.assertEqual("HASH_MISMATCH",
                         self.reconcile(manifest, not_before=time.time() - 60)["outputs"][0]["status"])

    def test_invoke_expect_separates_process_exit_from_artifact_verdict(self):
        self.typed_pass("G1")
        manifest = self.manifest([self.entry()])
        target = os.path.join(self.out_dir, "a.md")
        code = self.run_invoke(command=[sys.executable, "-c", f"open({target!r},'w').write('# ok\\n')"],
                               expect=manifest)
        self.assertEqual(0, code)
        report_path = os.path.join(self.proj, "logs", "reconciliation", "INV-0001.json")
        with open(report_path, encoding="utf-8") as handle:
            report = json.load(handle)
        self.assertTrue(report["process_complete"])
        self.assertTrue(report["artifact_valid"])
        self.assertEqual("NOT_RUN", report["user_acceptance"])

    def test_a_process_that_exits_zero_without_writing_is_not_artifact_valid(self):
        self.typed_pass("G1")
        manifest = self.manifest([self.entry()])
        code = self.run_invoke(command=[sys.executable, "-c", "pass"], expect=manifest)
        self.assertNotEqual(0, code, "artifact failure must not be reported as success")
        with open(os.path.join(self.proj, "logs", "reconciliation", "INV-0001.json"), encoding="utf-8") as handle:
            report = json.load(handle)
        self.assertTrue(report["process_complete"])
        self.assertFalse(report["artifact_valid"])
        self.assertEqual((1, 1, 0), self.counts())


# =====================================================================
# 5. read-only status report
# =====================================================================
class StatusReportTests(Workspace):
    profile = "startup-reversible"

    def before(self):
        with open(os.path.join(self.proj, "PROGRESS.md"), "rb") as handle:
            return hashlib.sha256(handle.read()).hexdigest()

    def test_status_is_derived_and_writes_nothing(self):
        digest = self.before()
        report = execution.status(self.proj)
        self.assertEqual(digest, self.before(), "status rewrote the control plane")
        self.assertEqual("startup-reversible", report["profile"])
        # Correction round: a gate row now reports what it states *and* whether
        # that claim was revalidated against typed evidence (review 1, class 6;
        # counterexamples in tests/test_v070_correction.py StatusTruthTests).
        self.assertEqual("PENDING", report["gates"]["G1"]["stated"])
        self.assertNotEqual("PASS", report["overall"])

    def test_unknown_sources_never_render_as_pass(self):
        os.remove(os.path.join(self.proj, "06_VERIFICATION.md"))
        report = execution.status(self.proj)
        self.assertEqual("UNKNOWN", report["requirements"]["status"])
        self.assertEqual("UNKNOWN", report["overall"])
        self.assertNotIn("PASS", json.dumps(report["overall"]))

    def test_unterminated_invocation_blocks_a_clean_report(self):
        self.typed_pass("G1")
        with open(self.ledger, "a", encoding="utf-8") as handle:
            handle.write("2026-01-01T00:00:00Z,STARTED,INV-9999,P3,steve,S-1,,\n")
        report = execution.status(self.proj)
        self.assertEqual(1, report["runner"]["unterminated"])
        self.assertIn("unterminated invocation", " ".join(report["blockers"]))
        self.assertNotEqual("PASS", report["overall"])

    def test_markdown_relay_carries_goal_state_delta_blockers_and_path_hash(self):
        text = execution.render_markdown(execution.status(self.proj))
        for field in ("Goal", "State", "Delta", "Blockers", "Path+hash"):
            self.assertIn(field, text)

    def test_cli_writes_only_where_explicitly_told(self):
        out = os.path.join(self.tmp, "status.json")
        result = subprocess.run([sys.executable, EXECUTION, "status", self.proj, "--format", "json"],
                                text=True, capture_output=True)
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual("startup-reversible", json.loads(result.stdout)["profile"])
        self.assertFalse(os.path.exists(out))
        result = subprocess.run([sys.executable, EXECUTION, "status", self.proj, "--output", out],
                                text=True, capture_output=True)
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertTrue(os.path.isfile(out))


# =====================================================================
# 6. frozen evaluator contract (evaluation tasks only)
# =====================================================================
class EvaluatorContractTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="ldl-v070-eval-")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def contract(self, **overrides):
        doc = {
            "schema": "ldl-evaluator-contract-v1",
            "contract_version": "v1",
            "scope": "evaluation-only",
            "frozen_at": utc(-3600),
            "frozen_sha256": "",
            "truth_table": [
                {"case": "zero", "condition": "proposals == 0", "verdict": "FAIL"},
                {"case": "missing", "condition": "required field absent", "verdict": "FAIL"},
                {"case": "partial", "condition": "1 proposal with dependency", "verdict": "PARTIAL_CREDIT"},
                {"case": "complete", "condition": "1 proposal, all fields", "verdict": "PASS"},
            ],
            "aggregate": {"method": "per-item-mean", "judges": 2, "tie_break": "dispute"},
            "penalty": {"applied_at": "judge-item-score", "double_count": "forbidden", "max_applications": 1},
            "dispute": {"threshold": 5, "authority": "Daniel", "authority_kind": "actual-human"},
        }
        doc.update(overrides)
        return doc

    def freeze(self, doc):
        doc = dict(doc)
        doc["frozen_sha256"] = ""
        doc["frozen_sha256"] = execution.canonical_digest(doc)
        path = os.path.join(self.tmp, "evaluator.json")
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(doc, handle, indent=2, sort_keys=True)
        return path

    def test_a_complete_frozen_contract_validates(self):
        report = execution.validate_evaluator_contract(self.freeze(self.contract()))
        self.assertEqual("PASS", report["verdict"])
        self.assertEqual("evaluation-only", report["scope"])

    def test_missing_truth_table_case_fails(self):
        table = [row for row in self.contract()["truth_table"] if row["case"] != "partial"]
        with self.assertRaises(execution.ManifestError) as caught:
            execution.validate_evaluator_contract(self.freeze(self.contract(truth_table=table)))
        self.assertIn("partial", str(caught.exception))

    def test_unfrozen_or_restated_hash_fails(self):
        path = self.freeze(self.contract())
        with open(path, encoding="utf-8") as handle:
            doc = json.load(handle)
        doc["aggregate"]["judges"] = 3          # edited after freezing
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(doc, handle, indent=2, sort_keys=True)
        with self.assertRaises(execution.ManifestError) as caught:
            execution.validate_evaluator_contract(path)
        self.assertIn("frozen_sha256", str(caught.exception))

    def test_double_penalty_policy_must_be_explicit(self):
        with self.assertRaises(execution.ManifestError) as caught:
            execution.validate_evaluator_contract(
                self.freeze(self.contract(penalty={"applied_at": "aggregate-total",
                                                   "double_count": "maybe", "max_applications": 1})))
        self.assertIn("double_count", str(caught.exception))

    def test_dispute_authority_is_required_and_typed(self):
        with self.assertRaises(execution.ManifestError) as caught:
            execution.validate_evaluator_contract(
                self.freeze(self.contract(dispute={"threshold": 5, "authority": "",
                                                   "authority_kind": "actual-human"})))
        self.assertIn("authority", str(caught.exception))

    def test_ai_may_not_be_declared_an_actual_human_authority(self):
        with self.assertRaises(execution.ManifestError) as caught:
            execution.validate_evaluator_contract(
                self.freeze(self.contract(dispute={"threshold": 5, "authority": "Elon (AI owner proxy)",
                                                   "authority_kind": "actual-human"})))
        self.assertIn("actual-human", str(caught.exception))

    def test_scope_beyond_evaluation_is_refused(self):
        with self.assertRaises(execution.ManifestError) as caught:
            execution.validate_evaluator_contract(self.freeze(self.contract(scope="all-delivery")))
        self.assertIn("scope", str(caught.exception))

    def test_validator_never_judges_whether_a_verdict_is_correct(self):
        """An implausible but complete truth table still validates: lint is not a judge."""
        table = [dict(row) for row in self.contract()["truth_table"]]
        table[0]["verdict"] = "PASS"           # zero proposals -> PASS: wrong, but stated
        report = execution.validate_evaluator_contract(self.freeze(self.contract(truth_table=table)))
        self.assertEqual("PASS", report["verdict"])
        self.assertEqual("NOT_JUDGED", report["truth_semantics"])


# =====================================================================
# 7. measurement interface
# =====================================================================
class MeasurementTests(Workspace):
    profile = "startup-reversible"

    def setUp(self):
        super().setUp()
        self.typed_pass("G1")

    def test_collect_reads_real_operations_and_leaves_human_fields_null(self):
        self.run_invoke(command=[sys.executable, "-c", "pass"])
        record = execution.collect_measurement(self.proj, deliverable="pilot doc")
        self.assertEqual(1, record["technical"]["invocations"])
        self.assertIsInstance(record["technical"]["wall_seconds_total"], float)
        self.assertEqual("logs/runner-ledger.csv", record["technical"]["source"])
        self.assertIsNone(record["product_fit"]["human_minutes"])
        self.assertIsNone(record["product_fit"]["time_to_human_acceptance_seconds"])
        self.assertEqual("NOT_RUN", record["product_fit"]["acceptance"])
        self.assertEqual("ABSENT", record["baseline"]["status"])
        self.assertIsNone(record["claimed_improvement_pct"])

    def test_empty_ledger_yields_null_not_zero_dressed_as_a_result(self):
        os.remove(self.ledger)
        record = execution.collect_measurement(self.proj, deliverable="nothing yet")
        self.assertEqual(0, record["technical"]["invocations"])
        self.assertIsNone(record["technical"]["wall_seconds_total"])

    def test_a_gain_claim_without_a_baseline_is_refused(self):
        record = execution.collect_measurement(self.proj, deliverable="pilot doc")
        record["claimed_improvement_pct"] = 30
        with self.assertRaises(execution.ManifestError) as caught:
            execution.validate_measurement(record)
        self.assertIn("baseline", str(caught.exception))

    def test_a_gain_claim_without_human_acceptance_is_refused(self):
        record = execution.collect_measurement(self.proj, deliverable="pilot doc")
        record["baseline"] = {"status": "MEASURED", "window": "2026-08", "unit": "minutes",
                              "value": 100.0, "source": "logs/runner-ledger.csv"}
        record["claimed_improvement_pct"] = 30
        with self.assertRaises(execution.ManifestError) as caught:
            execution.validate_measurement(record)
        self.assertIn("acceptance", str(caught.exception))

    def test_the_30_percent_target_is_recorded_as_a_target_not_a_result(self):
        record = execution.collect_measurement(self.proj, deliverable="pilot doc")
        report = execution.validate_measurement(record)
        self.assertEqual("PASS", report["verdict"])
        self.assertEqual(30, record["target_improvement_pct"])
        self.assertEqual("NOT_MEASURED", report["improvement"])

    def test_technical_delivery_and_product_fit_never_share_a_verdict(self):
        record = execution.collect_measurement(self.proj, deliverable="pilot doc")
        report = execution.validate_measurement(record)
        self.assertIn("technical_delivery", report)
        self.assertIn("product_fit", report)
        self.assertNotEqual(report["technical_delivery"], report["product_fit"])
        self.assertEqual("HOLD", report["product_fit"])

    def test_same_model_comparison_is_labelled_distinctly_from_model_comparison(self):
        record = execution.collect_measurement(self.proj, deliverable="pilot doc")
        self.assertEqual("same-model-process", record["comparison_kind"])
        record["comparison_kind"] = "cross-model"
        record["baseline"] = {"status": "MEASURED", "window": "2026-08", "unit": "minutes",
                              "value": 100.0, "source": "logs/runner-ledger.csv"}
        record["product_fit"]["acceptance"] = "PASS"
        record["claimed_improvement_pct"] = 30
        report = execution.validate_measurement(record)
        self.assertEqual("cross-model", report["comparison_kind"])
        self.assertIn("model change", " ".join(report["caveats"]))


# =====================================================================
# 8. v0.7.0 workspace: opt-in migration, compatibility, install
# =====================================================================
class MigrationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="ldl-v070-migrate-")
        self.ws = os.path.join(self.tmp, "ws")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def marker(self):
        with open(os.path.join(self.ws, ".ldl-version"), encoding="utf-8") as handle:
            return handle.read().strip()

    def make_v061(self):
        scaffold.init(self.ws)
        scaffold.new_project(self.ws, "sealed", "2026-01-01")
        with open(os.path.join(self.ws, ".ldl-version"), "w", encoding="utf-8") as handle:
            handle.write("0.6.1\n")
        for name in ("execution.py", "policy.py"):
            path = os.path.join(self.ws, "tools", name)
            if os.path.exists(path):
                os.remove(path)

    def test_fresh_install_is_v070_with_the_new_tools(self):
        scaffold.init(self.ws)
        self.assertEqual("0.7.0", self.marker())
        for name in ("execution.py", "policy.py", "invoke.py"):
            self.assertTrue(os.path.isfile(os.path.join(self.ws, "tools", name)), name)

    def test_a_v061_workspace_stays_v061_without_the_flag(self):
        self.make_v061()
        scaffold.init(self.ws)
        self.assertEqual("0.6.1", self.marker())
        self.assertFalse(os.path.isfile(os.path.join(self.ws, "tools", "execution.py")))

    def test_explicit_migration_upgrades_in_place(self):
        self.make_v061()
        scaffold.init(self.ws, migrate_v070=True)
        self.assertEqual("0.7.0", self.marker())
        self.assertTrue(os.path.isfile(os.path.join(self.ws, "tools", "execution.py")))
        self.assertTrue(os.path.isdir(os.path.join(self.ws, "projects", "2026-01-01_sealed")))

    def test_migration_requires_a_v061_workspace(self):
        self.make_v061()
        with open(os.path.join(self.ws, ".ldl-version"), "w", encoding="utf-8") as handle:
            handle.write("0.6.0\n")
        with self.assertRaises(SystemExit) as caught:
            scaffold.init(self.ws, migrate_v070=True)
        self.assertIn("v0.6.1 workspace", str(caught.exception))

    def schema_and_link_errors(self):
        """Only the failures this version could have introduced.

        A freshly scaffolded contract is a stub on purpose, so it never lints
        clean; what must hold is that the new marker and the new template links
        are accepted.
        """
        from lint import Lint
        linter = Lint(self.ws, "P0")
        linter.run()
        return [error for error in linter.errors
                if "workspace schema" in error or "broken link: index.md" in error
                or error.startswith("[L1] broken link: index.md")]

    def test_a_v070_marker_and_its_new_templates_are_accepted(self):
        scaffold.init(self.ws)
        for profile in sorted(scaffold.PROFILES):
            scaffold.new_project(self.ws, profile.replace("-", ""), "2026-01-01", profile)
        self.assertEqual([], self.schema_and_link_errors())
        for template in ("approved-job.json", "expected-output.json", "evaluator-contract.json",
                         "measurement.json", "status-relay.md", "roles.md"):
            self.assertTrue(os.path.isfile(os.path.join(self.ws, "templates", template)), template)

    def test_a_v061_marker_is_still_accepted(self):
        self.make_v061()
        self.assertEqual([], self.schema_and_link_errors())


class VersionTruthTests(unittest.TestCase):
    """One authority for what is public and what is only a candidate."""

    def read(self, *parts):
        with open(os.path.join(ROOT, *parts), encoding="utf-8") as handle:
            return handle.read()

    def test_authority_document_exists_and_names_both_versions(self):
        text = self.read("AUTHORITY.md")
        self.assertIn("0.6.1", text)
        self.assertIn("0.7.0", text)
        self.assertIn("candidate", text.lower())

    def test_review_log_records_prevention_rules(self):
        text = self.read("REVIEW_LOG.md")
        for rule in ("R-COMPOSE", "R-TRUST", "R-OUTCOME", "R-MODEL"):
            self.assertIn(rule, text)

    def test_readme_marks_v070_as_candidate_and_keeps_v061_public(self):
        text = self.read("README.md")
        self.assertIn("v0.6.1", text)
        self.assertIn("v0.7.0", text)
        head = text[:4000]
        self.assertIn("candidate", head.lower())

    def test_scaffold_and_documents_agree_on_the_latest_version(self):
        self.assertEqual("0.7.0", scaffold.LATEST_VERSION)
        self.assertIn("0.7.0", self.read("AUTHORITY.md"))


if __name__ == "__main__":
    unittest.main(verbosity=1)
