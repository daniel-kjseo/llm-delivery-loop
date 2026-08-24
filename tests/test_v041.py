import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
import warnings
from unittest import mock

warnings.simplefilter("ignore", ResourceWarning)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))

import scaffold  # noqa: E402
from lint import Lint  # noqa: E402
import workflow  # noqa: E402


CONTRACT = """# 00_CONTRACT — decision (Phase 0 · gate 1)

[interview](raw/interview.md)

## Governance profile
- Contract version: v1
- Approval mode: human
- Quantitative claims: no
- Risk level: medium

## Delivery profile
- Delivery mode: pre-engineering-decision
- Decision endpoint: G3

## Decision brief
- Decision owner: Daniel [IV-01]
- Problem space: choose one evidenced problem [IV-02]
- Decision deliverable: one engineering-start decision packet [IV-03]
- Decision metric: stranger reconstructs problem evidence solution and cuts [IV-04]
- Evidence boundary: captured primary evidence only [IV-05]
- Kill criteria: no demand or behavior evidence for a user problem
- Timebox: three bounded phases
- Risk: medium-risk
- Rollback: supersede the decision document and preserve history

## 2W1H
- Why: prevent feature-first work [IV-01]
- What: one approved decision packet [IV-02]
- How: evidence then scope [IV-03]

## Constraints
- no implementation before G3 [IV-04]

## Evaluation criteria
1. contract is structurally valid — judge: code (stage lint) [IV-03]
2. problem is supported — judge: fresh-context (independent reviewer) [IV-05]

## Failure conditions (three, concrete)
1. solution selected before one problem is approved
2. supply evidence is called user demand
3. source roots are mutated

## Execution plan
| phase | path | verify | gate | budget |
|---|---|---|---|---|
| P0 | 00_CONTRACT.md | stage lint and stranger | G1 | one run |
| P1-P3 | 01_REQUIREMENTS.md and 03_EVIDENCE.md | stage lint | G2 | one run |
| P4 | 04_SCOPE.md | stage lint | G3 | one run |

## Execution economy
- Phase packet max bytes: 8192
- Relay summary max chars: 1500
- Checker summary max chars: 4000
- Checker runs per increment: 1
- Correction reruns per increment: 1
- Token/call ledger: logs/cost-ledger.csv

## Verification setup
- Verifier instances: stage lint and different context
- Lint command: python3 tools/lint.py --through P0 .
- Approver: Daniel
- Verifier workspace: external reviews
- Target access: read-only

## Exit tests
- T1 can it fail: three failures are listed
- T2 stranger: external reconstruction succeeds
- T3 judge: every criterion names its judge
- T4 constraint collision: no release schema is required
- T5 primary source: IV-01 through IV-05 cited
"""


class V041Tests(unittest.TestCase):
    def setUp(self):
        warnings.simplefilter("ignore", ResourceWarning)
        self.tmp = tempfile.mkdtemp(prefix="ldl-v041-")
        self.ws = os.path.join(self.tmp, "ws")
        scaffold.init(self.ws)
        self.proj = scaffold.new_project(
            self.ws, "decision", "2026-01-01", "pre-engineering-decision")
        for rel, text in {
            "CLAUDE.md": "# Workspace constitution\n\ncontract first; scratch writes only; preserve evidence\n",
            "projects/CLAUDE.md": "# Shared protocol\n\nread contract; gates are closed until typed decisions apply\n",
        }.items():
            with open(os.path.join(self.ws, rel), "w", encoding="utf-8") as handle:
                handle.write(text)
        with open(os.path.join(self.proj, "00_CONTRACT.md"), "w", encoding="utf-8") as handle:
            handle.write(CONTRACT)
        with open(os.path.join(self.proj, "raw", "interview.md"), "w", encoding="utf-8") as handle:
            handle.write("IV-01 IV-02 IV-03 IV-04 IV-05\n")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def errors(self, through="final"):
        lint = Lint(self.ws, through)
        lint.run()
        return lint.errors

    def replace(self, rel, old, new):
        path = os.path.join(self.proj, rel)
        text = open(path, encoding="utf-8").read()
        self.assertEqual(1, text.count(old), (rel, old))
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(text.replace(old, new))

    def test_latest_scaffold_and_preengineering_profile(self):
        self.assertEqual("0.4.1", open(os.path.join(self.ws, ".ldl-version")).read().strip())
        self.assertTrue(os.path.isfile(os.path.join(self.ws, "tools", "workflow.py")))
        progress = open(os.path.join(self.proj, "PROGRESS.md")).read()
        self.assertNotIn("## Increment ledger", progress)
        self.assertNotIn("## Release ledger", progress)
        self.assertIn("| P5+P6 increments | NOT_RUN |", progress)
        evidence = open(os.path.join(self.proj, "03_EVIDENCE.md")).read()
        self.assertIn("Evidence level", evidence)
        self.assertIn("Evidence domain", evidence)
        self.assertIn("Claim lifecycle", evidence)

    def test_p0_stage_ignores_future_phase_content(self):
        self.assertEqual([], self.errors("P0"))
        final = self.errors("final")
        self.assertTrue(any("substantive requirement ID" in value for value in final), final)

    def test_p0_stage_keeps_contract_governance_errors(self):
        self.replace("00_CONTRACT.md", "- Risk level: medium", "- Risk level: BANANA")
        self.replace("00_CONTRACT.md", "- Target access: read-only", "- Target access: read-write")
        errors = self.errors("P0")
        self.assertTrue(any("Risk level must be" in value for value in errors), errors)
        self.assertTrue(any("Target access must be read-only" in value for value in errors), errors)

    def test_explicit_final_cli_is_supported(self):
        result = subprocess.run(
            [sys.executable, os.path.join(ROOT, "tools", "lint.py"), "--final", self.ws],
            text=True, capture_output=True)
        self.assertEqual(1, result.returncode)
        self.assertIn("substantive requirement ID", result.stdout)

    def test_contract_8192_byte_ceiling(self):
        path = os.path.join(self.proj, "00_CONTRACT.md")
        with open(path, "a", encoding="utf-8") as handle:
            handle.write("\n" + "x" * 9000)
        self.assertTrue(any("contract exceeds 8192 bytes" in value for value in self.errors("P0")))

    def test_p3_hides_p4_quantitative_fields_but_p4_exposes_them(self):
        self.replace("00_CONTRACT.md", "- Quantitative claims: no", "- Quantitative claims: yes")
        self.add_requirements()
        workflow.sync_verdicts(self.proj)
        p3 = self.errors("P3")
        self.assertFalse(any("Quantitative model field missing" in value for value in p3), p3)
        p4 = self.errors("P4")
        self.assertEqual(7, sum("Quantitative model field missing" in value for value in p4), p4)

    def add_requirements(self):
        path = os.path.join(self.proj, "01_REQUIREMENTS.md")
        with open(path, "a", encoding="utf-8") as handle:
            handle.write("| R-01 | product | must | one decision | owner check | (b) IV-02 |\n")
            handle.write("| R-02 | quality | must | one evidence row | lint | (a) raw source |\n")

    def test_sync_verdicts_adds_and_preserves_ids(self):
        self.add_requirements()
        workflow.sync_verdicts(self.proj)
        verification = open(os.path.join(self.proj, "06_VERIFICATION.md")).read()
        self.assertIn("| R-01 | NOT_RUN | not executed |", verification)
        self.assertIn("| R-02 | NOT_RUN | not executed |", verification)
        workflow.sync_verdicts(self.proj)
        self.assertEqual(1, open(os.path.join(self.proj, "06_VERIFICATION.md")).read().count("| R-01 |"))

    def test_raw_put_is_create_only(self):
        source = os.path.join(self.tmp, "source.txt")
        with open(source, "w", encoding="utf-8") as handle:
            handle.write("immutable")
        workflow.raw_put(self.proj, "captures/source.txt", source)
        target = os.path.join(self.proj, "raw", "captures", "source.txt")
        self.assertEqual("immutable", open(target).read())
        with self.assertRaises(FileExistsError):
            workflow.raw_put(self.proj, "captures/source.txt", source)
        with self.assertRaises(SystemExit):
            workflow.raw_put(self.proj, "../escape.txt", source)

    def test_new_evidence_schema_and_domain(self):
        capture = os.path.join(self.proj, "raw", "capture.md")
        with open(capture, "w", encoding="utf-8") as handle:
            handle.write("captured")
        path = os.path.join(self.proj, "03_EVIDENCE.md")
        text = open(path, encoding="utf-8").read()
        marker = "|---|---|---|---|---|---|---|---|---|\n"
        row = "| C-01 | [measured] | SUPPLY | observed | [capture](raw/capture.md) | 2026-01-01 | one crawl | direct | ACTIVE |\n"
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(text.replace(marker, marker + row, 1))
        self.assertFalse(any("invalid evidence" in value for value in self.errors("P3")))
        self.replace(
            "03_EVIDENCE.md",
            "| C-01 | [measured] | SUPPLY | observed |",
            "| C-01 | [measured] | BANANA | observed |",
        )
        self.assertTrue(any("invalid evidence domain" in value for value in self.errors("P3")))

    def new_scratch(self):
        scratch = os.path.join(self.tmp, "scratch")
        workflow.scratch_init(self.ws, scratch)
        return scratch

    def test_scratch_must_be_outside_target(self):
        with self.assertRaises(SystemExit):
            workflow.scratch_init(self.ws, os.path.join(self.ws, "scratch"))

    def test_scratch_rejects_target_symlink_before_copy(self):
        outside = os.path.join(self.tmp, "outside.txt")
        with open(outside, "w", encoding="utf-8") as handle:
            handle.write("outside")
        link = os.path.join(self.ws, "wiki", "linked.txt")
        try:
            os.symlink(outside, link)
        except OSError:
            self.skipTest("symlinks unavailable")
        scratch = os.path.join(self.tmp, "symlink-scratch")
        with self.assertRaises(SystemExit):
            workflow.scratch_init(self.ws, scratch)
        self.assertFalse(os.path.exists(scratch))

    def test_scratch_rejects_target_directory_symlink_before_copy(self):
        outside = os.path.join(self.tmp, "outside-dir")
        os.makedirs(outside)
        with open(os.path.join(outside, "payload.txt"), "w", encoding="utf-8") as handle:
            handle.write("outside")
        link = os.path.join(self.ws, "wiki", "linked-dir")
        try:
            os.symlink(outside, link, target_is_directory=True)
        except OSError:
            self.skipTest("directory symlinks unavailable")
        scratch = os.path.join(self.tmp, "dir-symlink-scratch")
        with self.assertRaises(SystemExit):
            workflow.scratch_init(self.ws, scratch)
        self.assertFalse(os.path.exists(scratch))

    def test_scratch_promotion_refuses_target_drift(self):
        scratch = self.new_scratch()
        with open(os.path.join(self.ws, "RULES.md"), "a") as handle:
            handle.write("target drift\n")
        with self.assertRaises(SystemExit):
            workflow.promote(scratch, self.ws, "P0")

    def test_scratch_promotion_refuses_existing_raw_mutation(self):
        scratch = self.new_scratch()
        with open(os.path.join(scratch, "projects", "2026-01-01_decision", "raw", "interview.md"), "w") as handle:
            handle.write("mutated")
        with self.assertRaises(SystemExit):
            workflow.promote(scratch, self.ws, "P0")

    def test_scratch_promotion_refuses_log_rewrite(self):
        scratch = self.new_scratch()
        path = os.path.join(scratch, "projects", "2026-01-01_decision", "logs", "log.md")
        with open(path, "w", encoding="utf-8") as handle:
            handle.write("rewritten history\n")
        with self.assertRaises(SystemExit):
            workflow.promote(scratch, self.ws, "P0")

    def test_scratch_promotion_accepts_valid_change(self):
        scratch = self.new_scratch()
        rules = os.path.join(scratch, "RULES.md")
        with open(rules, "a", encoding="utf-8") as handle:
            handle.write("\nRule: scratch only.\n")
        workflow.promote(scratch, self.ws, "P0")
        self.assertIn("scratch only", open(os.path.join(self.ws, "RULES.md")).read())

    def test_scratch_promotion_accepts_new_linked_file(self):
        scratch = self.new_scratch()
        page = os.path.join(scratch, "wiki", "new.md")
        with open(page, "w", encoding="utf-8") as handle:
            handle.write("# new\n")
        with open(os.path.join(scratch, "index.md"), "a", encoding="utf-8") as handle:
            handle.write("\n- [new](wiki/new.md)\n")
        workflow.promote(scratch, self.ws, "P0")
        self.assertTrue(os.path.isfile(os.path.join(self.ws, "wiki", "new.md")))

    def gate_manifest(self, bad_hash=False):
        self.replace(
            "PROGRESS.md",
            "| P0 contract | pending | |",
            "| P0 contract | done | 2026-01-01 |",
        )
        contract = os.path.join(self.proj, "00_CONTRACT.md")
        digest = hashlib.sha256(open(contract, "rb").read()).hexdigest()
        decision = {
            "schema": "ldl-gate-decision-v1",
            "gate": "G1",
            "contract_version": "v1",
            "verdict": "PASS",
            "approval_mode": "human",
            "approver": "Daniel",
            "decided_at": "2026-01-01T00:00:00Z",
            "reason": "contract criteria are met",
            "evidence": [{"path": "00_CONTRACT.md", "sha256": "0" * 64 if bad_hash else digest}],
        }
        path = os.path.join(self.tmp, "decision.json")
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(decision, handle)
        return path

    def test_typed_gate_decision_validates_and_applies(self):
        decision = self.gate_manifest()
        workflow.gate_validate(self.proj, decision)
        workflow.gate_apply(self.proj, decision)
        progress = open(os.path.join(self.proj, "PROGRESS.md")).read()
        self.assertRegex(progress, r"\| G1 \| PASS \| v1 \| human \| Daniel \|")
        self.assertIn("raw/gate-decisions/", progress)
        self.assertIn("GATE-PASS: G1 contract=v1", open(os.path.join(self.proj, "logs", "log.md")).read())
        self.assertEqual([], self.errors("P0"))

    def test_typed_gate_decision_rejects_stale_hash(self):
        decision = self.gate_manifest(bad_hash=True)
        with self.assertRaises(SystemExit):
            workflow.gate_validate(self.proj, decision)

    def test_gate_apply_rolls_back_partial_write_and_can_retry(self):
        decision = self.gate_manifest()
        progress_path = os.path.join(self.proj, "PROGRESS.md")
        log_path = os.path.join(self.proj, "logs", "log.md")
        original_progress = open(progress_path, "rb").read()
        original_log = open(log_path, "rb").read()
        real_write = workflow.atomic_write
        failed = {"done": False}

        def flaky(path, data, binary=False, exclusive=False):
            if path == progress_path and not failed["done"]:
                failed["done"] = True
                raise OSError("injected progress write failure")
            return real_write(path, data, binary, exclusive)

        with mock.patch.object(workflow, "atomic_write", side_effect=flaky):
            with self.assertRaises(OSError):
                workflow.gate_apply(self.proj, decision)
        self.assertEqual(original_progress, open(progress_path, "rb").read())
        self.assertEqual(original_log, open(log_path, "rb").read())
        decisions = os.path.join(self.proj, "raw", "gate-decisions")
        self.assertFalse(os.path.isdir(decisions) and os.listdir(decisions))
        workflow.gate_apply(self.proj, decision)
        self.assertIn("| G1 | PASS |", open(progress_path, encoding="utf-8").read())

    def test_typed_hold_decision_must_match_gate_row(self):
        decision_path = self.gate_manifest()
        decision = json.load(open(decision_path, encoding="utf-8"))
        decision["verdict"] = "HOLD"
        with open(decision_path, "w", encoding="utf-8") as handle:
            json.dump(decision, handle)
        workflow.gate_apply(self.proj, decision_path)
        self.replace("PROGRESS.md", "| G1 | HOLD | v1 | human | Daniel |", "| G1 | HOLD | v1 | human | Mallory |")
        self.assertTrue(any("typed decision does not match gate row" in value for value in self.errors("P0")))

    def test_typed_hold_requires_decision_link(self):
        decision_path = self.gate_manifest()
        decision = json.load(open(decision_path, encoding="utf-8"))
        decision["verdict"] = "HOLD"
        with open(decision_path, "w", encoding="utf-8") as handle:
            json.dump(decision, handle)
        workflow.gate_apply(self.proj, decision_path)
        progress = os.path.join(self.proj, "PROGRESS.md")
        text = open(progress, encoding="utf-8").read()
        text = re.sub(r"(\| G1 \| HOLD \|[^\n]*\| )\[[^]]+\]\([^)]+\.json\)( \|)", r"\1\2", text)
        with open(progress, "w", encoding="utf-8") as handle:
            handle.write(text)
        self.assertTrue(any("HOLD requires typed decision evidence" in value for value in self.errors("P0")))

    def test_typed_hold_decision_must_stay_under_raw(self):
        decision_path = self.gate_manifest()
        decision = json.load(open(decision_path, encoding="utf-8"))
        decision["verdict"] = "HOLD"
        with open(decision_path, "w", encoding="utf-8") as handle:
            json.dump(decision, handle)
        workflow.gate_apply(self.proj, decision_path)
        raw_path = os.path.join(self.proj, "raw", "gate-decisions", "g1-v1-20260101T000000Z.json")
        mutable_path = os.path.join(self.proj, "decision.json")
        shutil.copyfile(raw_path, mutable_path)
        os.unlink(raw_path)
        progress = os.path.join(self.proj, "PROGRESS.md")
        text = open(progress, encoding="utf-8").read().replace(
            "[decision](raw/gate-decisions/g1-v1-20260101T000000Z.json)",
            "[decision.json](decision.json)",
        )
        with open(progress, "w", encoding="utf-8") as handle:
            handle.write(text)
        self.assertTrue(any("typed decision must be immutable under project raw/" in value for value in self.errors("P0")))

    def test_gate_apply_does_not_delete_competing_artifact(self):
        decision_path = self.gate_manifest()
        raw_path = os.path.join(self.proj, "raw", "gate-decisions", "g1-v1-20260101T000000Z.json")
        real_write = workflow.atomic_write

        def competing(path, data, binary=False, exclusive=False):
            if path == raw_path and exclusive:
                os.makedirs(os.path.dirname(path), exist_ok=True)
                with open(path, "w", encoding="utf-8") as handle:
                    handle.write("COMPETING\n")
                raise FileExistsError(path)
            return real_write(path, data, binary, exclusive)

        with mock.patch.object(workflow, "atomic_write", side_effect=competing):
            with self.assertRaises(FileExistsError):
                workflow.gate_apply(self.proj, decision_path)
        self.assertEqual("COMPETING\n", open(raw_path, encoding="utf-8").read())

    def test_preengineering_profile_has_no_release_obligation(self):
        self.assertFalse(any("Launch brief" in value or "MVP-1" in value for value in self.errors("P0")))

    def test_explicit_v041_migration_requires_empty_v040_workspace(self):
        old = os.path.join(self.tmp, "old")
        os.makedirs(os.path.join(old, "projects"))
        with open(os.path.join(old, ".ldl-version"), "w", encoding="utf-8") as handle:
            handle.write("0.4.0\n")
        scaffold.init(old)
        self.assertEqual("0.4.0", open(os.path.join(old, ".ldl-version")).read().strip())
        scaffold.init(old, migrate_v041=True)
        self.assertEqual("0.4.1", open(os.path.join(old, ".ldl-version")).read().strip())
        self.assertTrue(os.path.isfile(os.path.join(old, "tools", "workflow.py")))

    def test_v040_workspace_gets_legacy_project_schema(self):
        old = os.path.join(self.tmp, "v040")
        scaffold.init(old)
        with open(os.path.join(old, ".ldl-version"), "w", encoding="utf-8") as handle:
            handle.write("0.4.0\n")
        project = scaffold.new_project(old, "legacy", "2026-01-02")
        evidence = open(os.path.join(project, "03_EVIDENCE.md"), encoding="utf-8").read()
        self.assertIn("| Claim ID | Label | Claim |", evidence)
        self.assertNotIn("Evidence domain", evidence)
        with self.assertRaises(SystemExit):
            scaffold.new_project(old, "decision", "2026-01-03", "pre-engineering-decision")


if __name__ == "__main__":
    unittest.main()
