import hashlib
import json
import os
import shutil
import sys
import tempfile
import unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tools"))

from lint import Lint  # noqa: E402
import workflow  # noqa: E402
import scaffold  # noqa: E402
import tests.test_v040 as v040  # noqa: E402
import tests.test_v041 as v041  # noqa: E402
import tests.test_v030 as v030  # noqa: E402


class V042SafetyTests(unittest.TestCase):
    def test_latest_scaffold_and_explicit_v042_migration(self):
        tmp = tempfile.mkdtemp(prefix="ldl-v042-marker-")
        shutil.rmtree(tmp)
        try:
            scaffold.init(tmp)
            self.assertEqual("0.6.0", open(os.path.join(tmp, ".ldl-version"), encoding="utf-8").read().strip())
            with open(os.path.join(tmp, ".ldl-version"), "w", encoding="utf-8") as handle:
                handle.write("0.4.1\n")
            scaffold.init(tmp, migrate_v042=True)
            self.assertEqual("0.4.2", open(os.path.join(tmp, ".ldl-version"), encoding="utf-8").read().strip())
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def decision_fixture(self):
        fixture = v041.V041Tests(methodName="test_contract_8192_byte_ceiling")
        fixture.setUp()
        return fixture

    def startup_fixture(self):
        fixture = v040.V040Tests(methodName="test_clean_v040_workspace_passes")
        fixture.setUp()
        return fixture

    def test_promotion_uses_target_validator_and_refuses_tool_changes(self):
        fixture = self.decision_fixture()
        try:
            scratch = os.path.join(fixture.tmp, "attack")
            workflow.scratch_init(fixture.ws, scratch)
            rel = os.path.relpath(os.path.realpath(fixture.proj), os.path.realpath(fixture.ws))
            with open(os.path.join(scratch, rel, "00_CONTRACT.md"), "w", encoding="utf-8") as handle:
                handle.write("hijacked - no gates, no evidence\n")
            with open(os.path.join(scratch, "tools", "lint.py"), "w", encoding="utf-8") as handle:
                handle.write("raise SystemExit(0)\n")
            with self.assertRaisesRegex(SystemExit, "tool.*promotion refused"):
                workflow.promote(scratch, fixture.ws, "P0")
            self.assertIn("Governance profile", open(os.path.join(fixture.proj, "00_CONTRACT.md"), encoding="utf-8").read())
        finally:
            fixture.tearDown()

    def test_target_validator_rejects_invalid_scratch_even_when_scratch_lint_exits_zero(self):
        fixture = self.decision_fixture()
        try:
            scratch = os.path.join(fixture.tmp, "checker-boundary")
            workflow.scratch_init(fixture.ws, scratch)
            rel = os.path.relpath(os.path.realpath(fixture.proj), os.path.realpath(fixture.ws))
            with open(os.path.join(scratch, rel, "00_CONTRACT.md"), "w", encoding="utf-8") as handle:
                handle.write("hijacked\n")
            with open(os.path.join(scratch, "tools", "lint.py"), "w", encoding="utf-8") as handle:
                handle.write("raise SystemExit(0)\n")
            with self.assertRaisesRegex(SystemExit, "scratch lint failed"):
                workflow.run_scratch_lint(fixture.ws, scratch, "P0")
        finally:
            fixture.tearDown()

    def test_p0_rejects_future_evidence_content_and_promotion(self):
        fixture = self.decision_fixture()
        row = "| C-99 | [proven] | TOTALLY_MADE_UP | users demand this | nowhere.md | 1999-99-99 | all | none | ACTIVE |\n"
        try:
            evidence = os.path.join(fixture.proj, "03_EVIDENCE.md")
            with open(evidence, "a", encoding="utf-8") as handle:
                handle.write(row)
            lint = Lint(fixture.ws, "P0")
            self.assertEqual(1, lint.run())
            self.assertTrue(any("future phase content" in item for item in lint.errors), lint.errors)
        finally:
            fixture.tearDown()

        fixture = self.decision_fixture()
        try:
            scratch = os.path.join(fixture.tmp, "future")
            workflow.scratch_init(fixture.ws, scratch)
            rel = os.path.relpath(os.path.realpath(fixture.proj), os.path.realpath(fixture.ws))
            with open(os.path.join(scratch, rel, "03_EVIDENCE.md"), "a", encoding="utf-8") as handle:
                handle.write(row)
            with self.assertRaisesRegex(SystemExit, "requires P3"):
                workflow.promote(scratch, fixture.ws, "P0")
        finally:
            fixture.tearDown()

    def test_p4_skips_final_only_ship_first_checks(self):
        fixture = self.startup_fixture()
        try:
            progress = os.path.join(fixture.proj, "PROGRESS.md")
            text = open(progress, encoding="utf-8").read().replace(
                "| EXP-1 | real users complete the core journey | next smallest change | completion rate | NOT_RUN | pending | PENDING |",
                "| EXP-1 | real users complete the core journey | next smallest change | completion rate | BANANA | pending | PENDING |",
            )
            with open(progress, "w", encoding="utf-8") as handle:
                handle.write(text)
            p4 = Lint(fixture.ws, "P4")
            final = Lint(fixture.ws, "final")
            self.assertEqual(0, p4.run())
            self.assertEqual(1, final.run())
            self.assertTrue(any("invalid experiment status" in item for item in final.errors), final.errors)
        finally:
            fixture.tearDown()

    def test_cost_ledger_is_append_only_during_promotion(self):
        fixture = self.decision_fixture()
        try:
            scratch = os.path.join(fixture.tmp, "cost")
            workflow.scratch_init(fixture.ws, scratch)
            rel = os.path.relpath(os.path.realpath(fixture.proj), os.path.realpath(fixture.ws))
            cost = os.path.join(scratch, rel, "logs", "cost-ledger.csv")
            with open(cost, "w", encoding="utf-8") as handle:
                handle.write("rewritten,arbitrary\n")
            with self.assertRaisesRegex(SystemExit, "rewrote append-only ledger"):
                workflow.promote(scratch, fixture.ws, "P0")
        finally:
            fixture.tearDown()

        fixture = self.decision_fixture()
        try:
            scratch = os.path.join(fixture.tmp, "cost-append")
            workflow.scratch_init(fixture.ws, scratch)
            rel = os.path.relpath(os.path.realpath(fixture.proj), os.path.realpath(fixture.ws))
            cost = os.path.join(scratch, rel, "logs", "cost-ledger.csv")
            with open(cost, "a", encoding="utf-8") as handle:
                handle.write("2026-01-01T00:00:00Z,P0,maker,test,1,1,0,1,1,1,00_CONTRACT.md\n")
            workflow.promote(scratch, fixture.ws, "P0")
            self.assertIn("2026-01-01T00:00:00Z", open(os.path.join(fixture.proj, "logs", "cost-ledger.csv"), encoding="utf-8").read())
        finally:
            fixture.tearDown()

    def test_fail_can_reopen_only_on_new_contract_with_prior_evidence(self):
        fixture = self.decision_fixture()
        try:
            first_path = fixture.gate_manifest()
            first = json.load(open(first_path, encoding="utf-8"))
            first["verdict"] = "FAIL"
            with open(first_path, "w", encoding="utf-8") as handle:
                json.dump(first, handle)
            workflow.gate_apply(fixture.proj, first_path)

            contract = os.path.join(fixture.proj, "00_CONTRACT.md")
            revised_contract = os.path.join(fixture.tmp, "00_CONTRACT-v2.md")
            text = open(contract, encoding="utf-8").read().replace("- Contract version: v1", "- Contract version: v2")
            with open(revised_contract, "w", encoding="utf-8") as handle:
                handle.write(text)
            prior_rel = "raw/gate-decisions/g1-v1-20260101T000000Z.json"
            prior = os.path.join(fixture.proj, prior_rel)
            reopen = {
                "schema": "ldl-gate-decision-v1",
                "gate": "G1",
                "contract_version": "v2",
                "verdict": "REOPEN",
                "approval_mode": "human",
                "approver": "Daniel",
                "decided_at": "2026-01-02T00:00:00Z",
                "reason": "contract revised to address failed criteria",
                "evidence": [
                    {"path": "00_CONTRACT.md", "sha256": hashlib.sha256(open(revised_contract, "rb").read()).hexdigest()},
                    {"path": prior_rel, "sha256": hashlib.sha256(open(prior, "rb").read()).hexdigest()},
                ],
            }
            reopen_path = os.path.join(fixture.tmp, "reopen.json")
            with open(reopen_path, "w", encoding="utf-8") as handle:
                json.dump(reopen, handle)
            with self.assertRaisesRegex(SystemExit, "gate-reopen"):
                workflow.gate_apply(fixture.proj, reopen_path)
            self.assertIn("- Contract version: v1", open(contract, encoding="utf-8").read())
            workflow.gate_reopen(fixture.proj, revised_contract, reopen_path)
            self.assertIn("- Contract version: v2", open(contract, encoding="utf-8").read())
            progress = open(os.path.join(fixture.proj, "PROGRESS.md"), encoding="utf-8").read()
            self.assertRegex(progress, r"\| G1 \| PENDING \| v2 \| human \| Daniel \|")
            self.assertRegex(progress, r"\| G2 \| PENDING \| v2 \| human \|\s*\|\s*\|\s*\|")
            self.assertIn("GATE-REOPEN: G1 contract=v2", open(os.path.join(fixture.proj, "logs", "log.md"), encoding="utf-8").read())
            self.assertEqual(0, Lint(fixture.ws, "P0").run())
        finally:
            fixture.tearDown()

    def test_reopen_rejects_same_contract_version(self):
        fixture = self.decision_fixture()
        try:
            first_path = fixture.gate_manifest()
            first = json.load(open(first_path, encoding="utf-8"))
            first["verdict"] = "FAIL"
            with open(first_path, "w", encoding="utf-8") as handle:
                json.dump(first, handle)
            workflow.gate_apply(fixture.proj, first_path)
            prior_rel = "raw/gate-decisions/g1-v1-20260101T000000Z.json"
            prior = os.path.join(fixture.proj, prior_rel)
            contract = os.path.join(fixture.proj, "00_CONTRACT.md")
            revised_contract = os.path.join(fixture.tmp, "00_CONTRACT-same-v1.md")
            shutil.copyfile(contract, revised_contract)
            reopen = dict(first)
            reopen.update({"verdict": "REOPEN", "decided_at": "2026-01-02T00:00:00Z"})
            reopen["evidence"] = [
                {"path": "00_CONTRACT.md", "sha256": hashlib.sha256(open(revised_contract, "rb").read()).hexdigest()},
                {"path": prior_rel, "sha256": hashlib.sha256(open(prior, "rb").read()).hexdigest()},
            ]
            path = os.path.join(fixture.tmp, "same-version-reopen.json")
            with open(path, "w", encoding="utf-8") as handle:
                json.dump(reopen, handle)
            with self.assertRaisesRegex(SystemExit, "lower-version FAIL"):
                workflow.gate_reopen(fixture.proj, revised_contract, path)
        finally:
            fixture.tearDown()


    def test_p4_skips_final_verdict_vocabulary(self):
        fixture = self.startup_fixture()
        try:
            verification = os.path.join(fixture.proj, "06_VERIFICATION.md")
            text = open(verification, encoding="utf-8").read().replace("- Product: NOT_RUN", "- Product: BANANA")
            with open(verification, "w", encoding="utf-8") as handle:
                handle.write(text)
            self.assertEqual(0, Lint(fixture.ws, "P4").run())
            final = Lint(fixture.ws, "final")
            self.assertEqual(1, final.run())
            self.assertTrue(any("invalid Product verdict" in item for item in final.errors), final.errors)
        finally:
            fixture.tearDown()

    def test_completed_legacy_workspaces_can_run_p0(self):
        old = v030.V030LintTests(methodName="test_clean_v030_workspace_passes")
        old.setUp()
        try:
            self.assertEqual(0, Lint(old.ws, "P0").run())
        finally:
            old.tearDown()
        old = self.startup_fixture()
        try:
            self.assertEqual(0, Lint(old.ws, "P0").run())
        finally:
            old.tearDown()

    def test_native_lint_rejects_cost_ledger_history_rewrite(self):
        fixture = self.decision_fixture()
        try:
            self.assertEqual(0, Lint(fixture.ws, "P0").run())
            cost = os.path.join(fixture.proj, "logs", "cost-ledger.csv")
            with open(cost, "w", encoding="utf-8") as handle:
                handle.write("rewritten,history\n")
            lint = Lint(fixture.ws, "P0")
            self.assertEqual(1, lint.run())
            self.assertTrue(any("log rewritten" in item and "cost-ledger.csv" in item for item in lint.errors), lint.errors)
        finally:
            fixture.tearDown()

    def test_reopen_rejects_forged_prior_fail_artifact(self):
        fixture = self.decision_fixture()
        try:
            first_path = fixture.gate_manifest()
            first = json.load(open(first_path, encoding="utf-8"))
            first["verdict"] = "FAIL"
            with open(first_path, "w", encoding="utf-8") as handle:
                json.dump(first, handle)
            workflow.gate_apply(fixture.proj, first_path)
            forged_rel = "raw/not-a-fail.json"
            forged = os.path.join(fixture.proj, forged_rel)
            with open(forged, "w", encoding="utf-8") as handle:
                json.dump({"note": "not a gate decision"}, handle)
            progress = os.path.join(fixture.proj, "PROGRESS.md")
            text = open(progress, encoding="utf-8").read().replace(
                "raw/gate-decisions/g1-v1-20260101T000000Z.json", forged_rel)
            with open(progress, "w", encoding="utf-8") as handle:
                handle.write(text)
            contract = os.path.join(fixture.proj, "00_CONTRACT.md")
            revised_contract = os.path.join(fixture.tmp, "00_CONTRACT-forged-v2.md")
            text = open(contract, encoding="utf-8").read().replace("- Contract version: v1", "- Contract version: v2")
            with open(revised_contract, "w", encoding="utf-8") as handle:
                handle.write(text)
            reopen = dict(first)
            reopen.update({"verdict": "REOPEN", "contract_version": "v2", "decided_at": "2026-01-02T00:00:00Z"})
            reopen["evidence"] = [
                {"path": "00_CONTRACT.md", "sha256": hashlib.sha256(open(revised_contract, "rb").read()).hexdigest()},
                {"path": forged_rel, "sha256": hashlib.sha256(open(forged, "rb").read()).hexdigest()},
            ]
            path = os.path.join(fixture.tmp, "forged-reopen.json")
            with open(path, "w", encoding="utf-8") as handle:
                json.dump(reopen, handle)
            with self.assertRaisesRegex(SystemExit, "GATE DECISION FAIL"):
                workflow.gate_reopen(fixture.proj, revised_contract, path)
        finally:
            fixture.tearDown()

    def test_progress_control_plane_cannot_promote(self):
        fixture = self.decision_fixture()
        try:
            scratch = os.path.join(fixture.tmp, "control-plane")
            workflow.scratch_init(fixture.ws, scratch)
            rel = os.path.relpath(os.path.realpath(fixture.proj), os.path.realpath(fixture.ws))
            progress = os.path.join(scratch, rel, "PROGRESS.md")
            with open(progress, "a", encoding="utf-8") as handle:
                handle.write("\nmanual gate reset\n")
            with self.assertRaisesRegex(SystemExit, "protected control plane"):
                workflow.promote(scratch, fixture.ws, "P0")
        finally:
            fixture.tearDown()


    def test_gate_reopen_rolls_back_contract_progress_log_and_raw(self):
        fixture = self.decision_fixture()
        try:
            first_path = fixture.gate_manifest()
            first = json.load(open(first_path, encoding="utf-8"))
            first["verdict"] = "FAIL"
            with open(first_path, "w", encoding="utf-8") as handle:
                json.dump(first, handle)
            workflow.gate_apply(fixture.proj, first_path)
            contract = os.path.join(fixture.proj, "00_CONTRACT.md")
            progress = os.path.join(fixture.proj, "PROGRESS.md")
            log = os.path.join(fixture.proj, "logs", "log.md")
            originals = {path: open(path, "rb").read() for path in (contract, progress, log)}
            revised = os.path.join(fixture.tmp, "00_CONTRACT-v2-rollback.md")
            with open(revised, "w", encoding="utf-8") as handle:
                handle.write(originals[contract].decode().replace("- Contract version: v1", "- Contract version: v2"))
            prior_rel = "raw/gate-decisions/g1-v1-20260101T000000Z.json"
            prior = os.path.join(fixture.proj, prior_rel)
            decision = dict(first)
            decision.update({"verdict": "REOPEN", "contract_version": "v2", "decided_at": "2026-01-02T00:00:00Z"})
            decision["evidence"] = [
                {"path": "00_CONTRACT.md", "sha256": hashlib.sha256(open(revised, "rb").read()).hexdigest()},
                {"path": prior_rel, "sha256": hashlib.sha256(open(prior, "rb").read()).hexdigest()},
            ]
            decision_path = os.path.join(fixture.tmp, "reopen-rollback.json")
            with open(decision_path, "w", encoding="utf-8") as handle:
                json.dump(decision, handle)
            real_write = workflow.atomic_write
            failed = {"done": False}

            def flaky(path, data, binary=False, exclusive=False):
                if path == progress and not failed["done"]:
                    failed["done"] = True
                    raise OSError("injected reopen progress failure")
                return real_write(path, data, binary, exclusive)

            with mock.patch.object(workflow, "atomic_write", side_effect=flaky):
                with self.assertRaises(OSError):
                    workflow.gate_reopen(fixture.proj, revised, decision_path)
            for path, content in originals.items():
                self.assertEqual(content, open(path, "rb").read())
            reopen_raw = os.path.join(fixture.proj, "raw", "gate-decisions", "g1-v2-20260102T000000Z.json")
            self.assertFalse(os.path.exists(reopen_raw))
            workflow.gate_reopen(fixture.proj, revised, decision_path)
            self.assertIn("- Contract version: v2", open(contract, encoding="utf-8").read())
        finally:
            fixture.tearDown()


    def test_gate_reopen_rejects_invalid_revised_contract_before_writes(self):
        fixture = self.decision_fixture()
        try:
            first_path = fixture.gate_manifest()
            first = json.load(open(first_path, encoding="utf-8"))
            first["verdict"] = "FAIL"
            with open(first_path, "w", encoding="utf-8") as handle:
                json.dump(first, handle)
            workflow.gate_apply(fixture.proj, first_path)
            contract = os.path.join(fixture.proj, "00_CONTRACT.md")
            original = open(contract, "rb").read()
            revised = os.path.join(fixture.tmp, "00_CONTRACT-invalid-v2.md")
            text = original.decode().replace("- Contract version: v1", "- Contract version: v2")
            text = text.replace("- Approval mode: human", "- Contract version: v2\n- Approval mode: human")
            with open(revised, "w", encoding="utf-8") as handle:
                handle.write(text)
            prior_rel = "raw/gate-decisions/g1-v1-20260101T000000Z.json"
            prior = os.path.join(fixture.proj, prior_rel)
            decision = dict(first)
            decision.update({"verdict": "REOPEN", "contract_version": "v2", "decided_at": "2026-01-02T00:00:00Z"})
            decision["evidence"] = [
                {"path": "00_CONTRACT.md", "sha256": hashlib.sha256(open(revised, "rb").read()).hexdigest()},
                {"path": prior_rel, "sha256": hashlib.sha256(open(prior, "rb").read()).hexdigest()},
            ]
            decision_path = os.path.join(fixture.tmp, "invalid-contract-reopen.json")
            with open(decision_path, "w", encoding="utf-8") as handle:
                json.dump(decision, handle)
            with self.assertRaisesRegex(SystemExit, "scratch lint failed"):
                workflow.gate_reopen(fixture.proj, revised, decision_path)
            self.assertEqual(original, open(contract, "rb").read())
            self.assertFalse(os.path.exists(os.path.join(
                fixture.proj, "raw", "gate-decisions", "g1-v2-20260102T000000Z.json")))
        finally:
            fixture.tearDown()

    def test_gate_reopen_rejects_prior_fail_with_forged_evidence_hash(self):
        fixture = self.decision_fixture()
        try:
            first_path = fixture.gate_manifest()
            first = json.load(open(first_path, encoding="utf-8"))
            first["verdict"] = "FAIL"
            with open(first_path, "w", encoding="utf-8") as handle:
                json.dump(first, handle)
            workflow.gate_apply(fixture.proj, first_path)
            contract = os.path.join(fixture.proj, "00_CONTRACT.md")
            revised = os.path.join(fixture.tmp, "00_CONTRACT-forged-prior-v2.md")
            with open(revised, "w", encoding="utf-8") as handle:
                handle.write(open(contract, encoding="utf-8").read().replace("- Contract version: v1", "- Contract version: v2"))
            prior_rel = "raw/gate-decisions/g1-v1-20260101T000000Z.json"
            prior = os.path.join(fixture.proj, prior_rel)
            prior_json = json.load(open(prior, encoding="utf-8"))
            prior_json["evidence"][0]["sha256"] = "0" * 64
            with open(prior, "w", encoding="utf-8") as handle:
                json.dump(prior_json, handle)
            decision = dict(first)
            decision.update({"verdict": "REOPEN", "contract_version": "v2", "decided_at": "2026-01-02T00:00:00Z"})
            decision["evidence"] = [
                {"path": "00_CONTRACT.md", "sha256": hashlib.sha256(open(revised, "rb").read()).hexdigest()},
                {"path": prior_rel, "sha256": hashlib.sha256(open(prior, "rb").read()).hexdigest()},
            ]
            path = os.path.join(fixture.tmp, "forged-prior-hash-reopen.json")
            with open(path, "w", encoding="utf-8") as handle:
                json.dump(decision, handle)
            with self.assertRaisesRegex(SystemExit, "evidence hash mismatch"):
                workflow.gate_reopen(fixture.proj, revised, path)
            self.assertIn("- Contract version: v1", open(contract, encoding="utf-8").read())
        finally:
            fixture.tearDown()


if __name__ == "__main__":
    unittest.main()
