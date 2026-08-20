import os
import shutil
import sys
import tempfile
import unittest
import warnings

warnings.simplefilter("ignore", ResourceWarning)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))

import scaffold  # noqa: E402
from lint import Lint  # noqa: E402


CONTRACT = """# 00_CONTRACT — good

[interview](raw/interview.md)

## Governance profile
- Contract version: v1
- Approval mode: human
- Quantitative claims: no
- Risk level: low

## 2W1H
- Why: real problem [IV-01]
- What: one deliverable [IV-02]
- How: build then verify [IV-03]

## Constraints
- one week [IV-04]

## Evaluation criteria
1. output exists — judge: code (test script) [IV-03]
2. tone approved — judge: human (owner) [IV-05]

## Failure conditions
1. wrong output shipped
2. deadline missed
3. rework exceeds two hours

## Execution plan
| phase | path | verify | gate | budget |
|---|---|---|---|---|
| P5+P6 | 05_engineering/ | test script | yes | one week |

## Verification setup
- Verifier instances: unit test and fresh owner review
- Lint command: python3 tools/lint.py .
- Approver: Daniel
- Verifier workspace: external reviews directory
- Target access: read-only

## Exit tests
- T1 can it fail: three conditions listed
- T2 stranger: fresh-context review passed
- T3 judge: judges named
- T4 constraint collision: scope fits
- T5 primary source: IV-01 through IV-05 cited
"""

PROGRESS = """# PROGRESS — good

## Phase progress
| Phase | Status | Date | Deliverable |
|---|---|---|---|
| P0 contract | done | 2026-01-01 | [00_CONTRACT.md](00_CONTRACT.md) |
| P1 requirements | pending | | [01_REQUIREMENTS.md](01_REQUIREMENTS.md) |
| P2 structure | pending | | [CLAUDE.md](CLAUDE.md) |
| P3 research | pending | | [03_EVIDENCE.md](03_EVIDENCE.md) |
| P4 scoping | pending | | [04_SCOPE.md](04_SCOPE.md) |
| P5+P6 increments | pending | | [06_VERIFICATION.md](06_VERIFICATION.md) |

## Gate ledger
| Gate | Verdict | Contract version | Approval mode | Approver | Approved at | Evidence |
|---|---|---|---|---|---|---|
| G1 | PASS | v1 | human | Daniel | 2026-01-01T10:00:00Z | [approval](raw/approval-g1.md) |
| G2 | PENDING | v1 | human | | | |
| G3 | PENDING | v1 | human | | | |
| G4 | PENDING | v1 | human | | | |

Events: [logs/log.md](logs/log.md)
"""

EVIDENCE = """# 03_EVIDENCE — good

## Evidence ledger
| Claim ID | Label | Claim | Source artifact | Captured at | Scope/window | Transform/reproducer | Status |
|---|---|---|---|---|---|---|---|
| C-01 | [measured] | one observation | [source](raw/source.txt) | 2026-01-01 | one run | direct observation | ACTIVE |
"""

SCOPE = """# 04_SCOPE — good

## Impact dimensions
| Dimension ID | Status | Evidence |
|---|---|---|
| D-01 | PASS | [evidence](03_EVIDENCE.md) |

## Action readiness
| Action ID | Impact dimensions | Preconditions | Approval tier | Approval evidence | Canary | Rollback | Ready |
|---|---|---|---|---|---|---|---|
| A-01 | D-01 | G1 PASS | 1 | [approval](raw/approval-g1.md) | small sample | restore prior version | YES |
"""

VERIFICATION = """# 06_VERIFICATION — good

## Requirement verdicts
| Requirement ID | Verdict | Evidence |
|---|---|---|
| R-01 | NOT_RUN | no execution yet |

## Final verdicts
- Harness: NOT_RUN
- Product: NOT_RUN
- Execution readiness: HOLD
- Method conformance: PASS
- Historical violations: NONE
- Independent verifier: fresh-context (owner)
- Target mutation: 0 files
"""


class V030LintTests(unittest.TestCase):
    def setUp(self):
        warnings.simplefilter("ignore", ResourceWarning)
        self.tmp = tempfile.mkdtemp(prefix="ldl-v030-")
        self.ws = os.path.join(self.tmp, "ws")
        scaffold.init(self.ws)
        # This suite freezes the v0.3 schema while scaffold.init now creates
        # the latest v0.4 workspace. v0.4-specific coverage lives in test_v040.
        with open(os.path.join(self.ws, ".ldl-version"), "w", encoding="utf-8") as handle:
            handle.write("0.3.0\n")
        self.proj = scaffold.new_project(self.ws, "good", "2026-01-01")
        files = {
            "00_CONTRACT.md": CONTRACT,
            "01_REQUIREMENTS.md": "# requirements\n\n## Requirements ledger\n| Requirement ID | Type | Priority | Requirement | Verification | Source |\n|---|---|---|---|---|---|\n| R-01 | functional | must | produce one output | test script | (b) IV-03 |\n",
            "PROGRESS.md": PROGRESS,
            "03_EVIDENCE.md": EVIDENCE,
            "04_SCOPE.md": SCOPE,
            "06_VERIFICATION.md": VERIFICATION,
            "raw/interview.md": "IV-01 .. IV-05",
            "raw/approval-g1.md": "Daniel explicitly approves Gate 1 for contract v1.",
            "raw/source.txt": "measured source",
            "logs/log.md": "# Event log\nGATE-PASS: G1 contract=v1\n",
        }
        for rel, text in files.items():
            path = os.path.join(self.proj, rel)
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                f.write(text)
        for rel, text in {
            "CLAUDE.md": "# Workspace constitution\n\ncontract-first gate protocol\n",
            "projects/CLAUDE.md": "# Shared protocol\n\nread contract; preserve gate order\n",
        }.items():
            with open(os.path.join(self.ws, rel), "w", encoding="utf-8") as f:
                f.write(text)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def errors(self):
        lint = Lint(self.ws)
        lint.run()
        return lint.errors

    def replace(self, rel, old, new):
        path = os.path.join(self.proj, rel)
        with open(path, encoding="utf-8") as handle:
            text = handle.read()
        with open(path, "w", encoding="utf-8") as f:
            f.write(text.replace(old, new))

    def assert_error(self, fragment):
        self.assertTrue(any(fragment in e for e in self.errors()), self.errors())

    def make_full_green(self):
        for phase in ("P1 requirements", "P2 structure", "P3 research", "P4 scoping", "P5+P6 increments"):
            self.replace("PROGRESS.md", f"| {phase} | pending | |", f"| {phase} | done | 2026-01-01 |")
        for n in range(2, 5):
            self.replace("PROGRESS.md", f"| G{n} | PENDING | v1 | human | | | |",
                f"| G{n} | PASS | v1 | human | Daniel | 2026-01-0{n}T10:00:00Z | [approval](raw/approval-g{n}.md) |")
            with open(os.path.join(self.proj, "raw", f"approval-g{n}.md"), "w", encoding="utf-8") as handle:
                handle.write(f"Daniel explicitly approves Gate {n} for contract v1.")
        with open(os.path.join(self.proj, "logs", "log.md"), "w", encoding="utf-8") as handle:
            handle.write("# Event log\n" + "".join(f"GATE-PASS: G{n} contract=v1\n" for n in range(1, 5)))
        self.replace("06_VERIFICATION.md", "| R-01 | NOT_RUN | no execution yet |", "| R-01 | PASS | [evidence](03_EVIDENCE.md) |")
        self.replace("06_VERIFICATION.md", "- Harness: NOT_RUN", "- Harness: PASS")
        self.replace("06_VERIFICATION.md", "- Product: NOT_RUN", "- Product: PASS")
        self.replace("06_VERIFICATION.md", "- Execution readiness: HOLD", "- Execution readiness: READY")

    def test_clean_v030_workspace_passes(self):
        self.assertEqual([], self.errors())

    def test_composed_full_green_passes(self):
        self.make_full_green()
        self.assertEqual([], self.errors())

    def test_gate_verdict_vocabulary(self):
        self.replace("PROGRESS.md", "| G2 | PENDING |", "| G2 | PARTIAL PASS |")
        self.assert_error("invalid gate verdict")

    def test_gate_pass_requires_approval_evidence(self):
        self.replace("PROGRESS.md", "| G2 | PENDING | v1 | human | | | |", "| G2 | PASS | v1 | human | Daniel | 2026-01-02T10:00:00Z | |")
        self.assert_error("PASS missing approval evidence")

    def test_gate_approval_artifact_must_be_substantive_and_gate_specific(self):
        with open(os.path.join(self.proj, "raw", "approval-g1.md"), "w", encoding="utf-8") as handle:
            handle.write("")
        self.assert_error("G1 approval evidence is empty or placeholder")
        with open(os.path.join(self.proj, "raw", "approval-g1.md"), "w", encoding="utf-8") as handle:
            handle.write("Daniel approves Gate 2.")
        self.assert_error("G1 approval evidence does not identify this gate")

    def test_gate_approval_placeholder_is_rejected(self):
        with open(os.path.join(self.proj, "raw", "approval-g1.md"), "w", encoding="utf-8") as handle:
            handle.write("Gate 1 for contract v1: TODO later")
        self.assert_error("approval evidence is empty or placeholder")

    def test_full_green_cannot_reuse_gate_approval_artifact(self):
        self.make_full_green()
        self.replace("PROGRESS.md", "[approval](raw/approval-g2.md)", "[approval](raw/approval-g1.md)")
        self.assert_error("reuses another gate approval artifact")

    def test_omnibus_approval_copies_are_not_gate_specific(self):
        self.make_full_green()
        omnibus = "Daniel approves Gate 1, Gate 2, Gate 3, and Gate 4 for contract v1."
        for n in range(1, 5):
            with open(os.path.join(self.proj, "raw", f"approval-g{n}.md"), "w", encoding="utf-8") as handle:
                handle.write(omnibus)
        self.assert_error("approval evidence does not identify this gate")

    def test_gate_order_is_monotonic(self):
        self.replace("PROGRESS.md", "| G3 | PENDING | v1 | human | | | |", "| G3 | PASS | v1 | human | Daniel | 2026-01-03T10:00:00Z | [approval](raw/approval-g1.md) |")
        self.assert_error("G3 PASS while G2 is not PASS")

    def test_gate_contract_version_matches_current(self):
        self.replace("PROGRESS.md", "| G1 | PASS | v1 |", "| G1 | PASS | v0 |")
        self.assert_error("gate contract version v0 does not match current v1")

    def test_impossible_gate_timestamp_is_rejected(self):
        self.replace("PROGRESS.md", "2026-01-01T10:00:00Z", "2026-99-99T99:99:99Z")
        self.assert_error("valid UTC ISO-8601")

    def test_future_gate_timestamp_is_rejected(self):
        self.replace("PROGRESS.md", "2026-01-01T10:00:00Z", "9999-01-01T10:00:00Z")
        self.assert_error("approval timestamp is in the future")

    def test_v030_marker_prevents_legacy_downgrade(self):
        self.replace("00_CONTRACT.md", "## Governance profile\n- Contract version: v1\n- Approval mode: human\n- Quantitative claims: no\n- Risk level: low\n\n", "")
        self.assert_error("v0.3 project missing Governance profile")

    def test_version_marker_deletion_after_baseline_is_rejected(self):
        self.assertEqual([], self.errors())
        os.remove(os.path.join(self.ws, ".ldl-version"))
        self.assert_error("legacy downgrade refused")

    def test_gate_approval_must_be_project_raw(self):
        self.replace("PROGRESS.md", "[approval](raw/approval-g1.md)", "[approval](https://example.com/approval)")
        self.assert_error("approval evidence must be immutable under project raw/")

    def test_measured_claim_requires_source(self):
        self.replace("03_EVIDENCE.md", "| [source](raw/source.txt) |", "| |")
        self.assert_error("measured/proven claim missing source artifact")

    def test_measured_claim_requires_scope_window(self):
        self.replace("03_EVIDENCE.md", "| one run | direct observation |", "| | direct observation |")
        self.assert_error("measured/proven claim missing scope/window")

    def test_evidence_identity_and_status_are_required(self):
        self.replace("03_EVIDENCE.md", "| C-01 | [measured] | one observation |", "| | [measured] | |")
        self.replace("03_EVIDENCE.md", "| ACTIVE |", "| BANANA |")
        self.assert_error("evidence row missing Claim ID or Claim")
        self.assert_error("invalid evidence status")

    def test_measured_source_must_be_captured_locally(self):
        self.replace("03_EVIDENCE.md", "[source](raw/source.txt)", "[source](https://example.com/live)")
        self.assert_error("source artifact must be captured under project raw/")

    def test_future_evidence_capture_is_rejected(self):
        self.replace("03_EVIDENCE.md", "| 2026-01-01 |", "| 9999-01-01 |")
        self.assert_error("capture date is in the future")

    def test_gate_two_requires_evidence_rows(self):
        self.replace("PROGRESS.md", "| G2 | PENDING | v1 | human | | | |", "| G2 | PASS | v1 | human | Daniel | 2026-01-02T10:00:00Z | [approval](raw/approval-g1.md) |")
        self.replace("03_EVIDENCE.md", "| C-01 | [measured] | one observation | [source](raw/source.txt) | 2026-01-01 | one run | direct observation | ACTIVE |\n", "")
        self.assert_error("G2 PASS requires at least one evidence row")

    def test_product_pass_rejects_not_run_requirement(self):
        self.replace("06_VERIFICATION.md", "- Product: NOT_RUN", "- Product: PASS")
        self.assert_error("Product PASS requires every requirement PASS")

    def test_verdict_ids_must_match_requirement_ids(self):
        self.replace("06_VERIFICATION.md", "| R-01 | NOT_RUN |", "| R-FAKE | NOT_RUN |")
        self.assert_error("requirement verdict IDs do not exactly match")

    def test_pass_requirement_needs_local_evidence_link(self):
        self.replace("06_VERIFICATION.md", "| R-01 | NOT_RUN | no execution yet |", "| R-01 | PASS | self assertion |")
        self.assert_error("PASS requirement missing local evidence")

    def test_ready_rejects_hold_dimension(self):
        self.replace("04_SCOPE.md", "| D-01 | PASS |", "| D-01 | HOLD |")
        self.replace("06_VERIFICATION.md", "- Execution readiness: HOLD", "- Execution readiness: READY")
        self.assert_error("Execution readiness READY with non-PASS impact dimension")

    def test_ready_requires_safety_rows(self):
        self.replace("04_SCOPE.md", "| D-01 | PASS | [evidence](03_EVIDENCE.md) |\n", "")
        self.replace("04_SCOPE.md", "| A-01 | D-01 | G1 PASS | 1 | [approval](raw/approval-g1.md) | small sample | restore prior version | YES |\n", "")
        self.replace("06_VERIFICATION.md", "| R-01 | NOT_RUN | no execution yet |", "| R-01 | PASS | [proof](03_EVIDENCE.md) |")
        self.replace("06_VERIFICATION.md", "- Product: NOT_RUN", "- Product: PASS")
        self.replace("06_VERIFICATION.md", "- Execution readiness: HOLD", "- Execution readiness: READY")
        self.assert_error("Execution readiness READY requires impact dimensions and actions")

    def test_action_ready_rejects_hold_dimension(self):
        self.replace("04_SCOPE.md", "| D-01 | PASS |", "| D-01 | HOLD |")
        self.assert_error("action A-01 is ready while impact dimension D-01 is HOLD")

    def test_ready_action_requires_impact_dimension(self):
        self.replace("04_SCOPE.md", "| A-01 | D-01 |", "| A-01 | |")
        self.assert_error("ready action A-01 has no impact dimensions")

    def test_duplicate_dimension_cannot_shadow_hold(self):
        self.replace("04_SCOPE.md", "| D-01 | PASS | [evidence](03_EVIDENCE.md) |", "| D-01 | HOLD | [evidence](03_EVIDENCE.md) |\n| D-01 | PASS | [evidence](03_EVIDENCE.md) |")
        self.assert_error("duplicate Dimension ID")

    def test_missing_table_separator_cannot_hide_unsafe_action(self):
        self.replace("04_SCOPE.md", "| D-01 | PASS |", "| D-01 | HOLD |")
        self.replace("04_SCOPE.md", "|---|---|---|---|---|---|---|---|\n", "")
        self.assert_error("malformed markdown separator in Action readiness")

    def test_quantitative_project_requires_model(self):
        self.replace("00_CONTRACT.md", "- Quantitative claims: no", "- Quantitative claims: yes")
        self.assert_error("quantitative project missing Quantitative model")

    def test_quantitative_placeholders_are_rejected(self):
        self.replace("00_CONTRACT.md", "- Quantitative claims: no", "- Quantitative claims: yes")
        block = "\n## Quantitative model\n" + "".join(f"- {field}: <TODO>\n" for field in (
            "Baseline window", "Baseline unit", "Candidate window", "Candidate unit",
            "Assumptions", "Formula/reproducer", "Reconciliation"))
        with open(os.path.join(self.proj, "04_SCOPE.md"), "a", encoding="utf-8") as handle:
            handle.write(block)
        self.assert_error("Quantitative model field missing")

    def test_quantitative_placeholder_variants_are_rejected(self):
        self.replace("00_CONTRACT.md", "- Quantitative claims: no", "- Quantitative claims: yes")
        block = "\n## Quantitative model\n" + "".join(f"- {field}: TODO later\n" for field in (
            "Baseline window", "Baseline unit", "Candidate window", "Candidate unit",
            "Assumptions", "Formula/reproducer", "Reconciliation"))
        with open(os.path.join(self.proj, "04_SCOPE.md"), "a", encoding="utf-8") as handle:
            handle.write(block)
        self.assert_error("Quantitative model field missing")

    def test_prefixed_quantitative_placeholder_is_rejected(self):
        self.replace("00_CONTRACT.md", "- Quantitative claims: no", "- Quantitative claims: yes")
        block = "\n## Quantitative model\n" + "".join(f"- {field}: declared TODO later\n" for field in (
            "Baseline window", "Baseline unit", "Candidate window", "Candidate unit",
            "Assumptions", "Formula/reproducer", "Reconciliation"))
        with open(os.path.join(self.proj, "04_SCOPE.md"), "a", encoding="utf-8") as handle:
            handle.write(block)
        self.assert_error("Quantitative model field missing")

    def test_inline_markdown_fragmented_placeholder_is_rejected(self):
        self.replace("00_CONTRACT.md", "- Quantitative claims: no", "- Quantitative claims: yes")
        block = "\n## Quantitative model\n" + "".join(f"- {field}: declared TO**DO** later\n" for field in (
            "Baseline window", "Baseline unit", "Candidate window", "Candidate unit",
            "Assumptions", "Formula/reproducer", "Reconciliation"))
        with open(os.path.join(self.proj, "04_SCOPE.md"), "a", encoding="utf-8") as handle:
            handle.write(block)
        self.assert_error("Quantitative model field missing")

    def test_structural_tables_inside_fences_are_invisible(self):
        path = os.path.join(self.proj, "03_EVIDENCE.md")
        with open(path, encoding="utf-8") as handle:
            text = handle.read()
        with open(path, "w", encoding="utf-8") as handle:
            handle.write("```markdown\n" + text + "\n```\n")
        self.assert_error("required section missing - Evidence ledger")

    def test_unclosed_fence_cannot_define_live_structure(self):
        path = os.path.join(self.proj, "03_EVIDENCE.md")
        with open(path, encoding="utf-8") as handle:
            text = handle.read()
        with open(path, "w", encoding="utf-8") as handle:
            handle.write("```markdown\n" + text)
        self.assert_error("required section missing - Evidence ledger")

    def test_structural_tables_inside_comments_are_invisible(self):
        path = os.path.join(self.proj, "04_SCOPE.md")
        with open(path, encoding="utf-8") as handle:
            text = handle.read()
        with open(path, "w", encoding="utf-8") as handle:
            handle.write("<!--\n" + text + "\n-->\n")
        self.assert_error("required section missing - Impact dimensions")

    def test_governance_inside_fence_is_not_live_structure(self):
        self.replace("00_CONTRACT.md", "## Governance profile\n- Contract version: v1\n- Approval mode: human\n- Quantitative claims: no\n- Risk level: low",
            "```markdown\n## Governance profile\n- Contract version: v1\n- Approval mode: human\n- Quantitative claims: no\n- Risk level: low\n```")
        self.assert_error("v0.3 project missing Governance profile")

    def test_duplicate_final_verdict_scalar_is_rejected(self):
        with open(os.path.join(self.proj, "06_VERIFICATION.md"), "a", encoding="utf-8") as handle:
            handle.write("\n- Product: PASS\n")
        self.assert_error("invalid Product verdict")

    def test_markdown_bold_duplicate_verdict_is_rejected(self):
        with open(os.path.join(self.proj, "06_VERIFICATION.md"), "a", encoding="utf-8") as handle:
            handle.write("\n- **Product**: FAIL\n")
        self.assert_error("invalid Product verdict")

    def test_full_green_requires_gate_event_history(self):
        self.make_full_green()
        path = os.path.join(self.proj, "logs", "log.md")
        with open(path, encoding="utf-8") as handle:
            text = handle.read()
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(text.replace("GATE-PASS: G4 contract=v1\n", ""))
        self.assert_error("G4 PASS missing append-only gate event")

    def test_fenced_or_commented_gate_event_is_not_live(self):
        self.make_full_green()
        path = os.path.join(self.proj, "logs", "log.md")
        with open(path, encoding="utf-8") as handle:
            text = handle.read().replace("GATE-PASS: G4 contract=v1\n", "")
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(text + "```\nGATE-PASS: G4 contract=v1\n```\n<!-- GATE-PASS: G4 contract=v1 -->\n")
        self.assert_error("G4 PASS missing append-only gate event")

    def test_full_green_requires_completed_phase_rows(self):
        self.make_full_green()
        self.replace("PROGRESS.md", "| P4 scoping | done |", "| P4 scoping | pending |")
        self.assert_error("G3 PASS while phase P4 scoping is not done")

    def test_duplicate_phase_cannot_shadow_pending(self):
        self.make_full_green()
        self.replace("PROGRESS.md", "| P4 scoping | done |", "| P4 scoping | pending | 2026-01-01 | [scope](04_SCOPE.md) |\n| P4 scoping | done |")
        self.assert_error("duplicate phase row")

    def test_requirement_source_classification_is_required(self):
        self.replace("01_REQUIREMENTS.md", "| (b) IV-03 |", "| IV-03 |")
        self.assert_error("requirement source must start with")

    def test_verifier_target_must_be_read_only(self):
        self.replace("00_CONTRACT.md", "- Target access: read-only", "- Target access: write")
        self.assert_error("Target access must be read-only")

    def test_high_risk_requires_stronger_independent_verifier(self):
        self.replace("00_CONTRACT.md", "- Risk level: low", "- Risk level: high")
        self.assert_error("high-risk project requires different-model or domain-expert verifier")

    def test_ready_action_requires_raw_approval(self):
        self.replace("04_SCOPE.md", "[approval](raw/approval-g1.md)", "[approval](https://example.com/approval)")
        self.assert_error("ready action A-01 missing approval evidence")

    def test_invalid_approval_tier_is_rejected(self):
        self.replace("04_SCOPE.md", "| A-01 | D-01 | G1 PASS | 1 |", "| A-01 | D-01 | G1 PASS | 9 |")
        self.assert_error("invalid approval tier")

    def test_historical_violation_forces_method_fail(self):
        self.replace("06_VERIFICATION.md", "- Historical violations: NONE", "- Historical violations: PRESENT")
        self.assert_error("historical violations require Method conformance FAIL")

    def test_append_only_violation_record_cannot_be_self_erased(self):
        with open(os.path.join(self.proj, "logs", "log.md"), "a", encoding="utf-8") as handle:
            handle.write("\nLDL-VIOLATION: gate-order\n")
        self.assert_error("append-only violation record requires Historical violations PRESENT")

    def test_init_refuses_silent_legacy_upgrade(self):
        legacy = os.path.join(self.tmp, "legacy")
        os.makedirs(os.path.join(legacy, "projects"))
        with open(os.path.join(legacy, "index.md"), "w", encoding="utf-8") as handle:
            handle.write("# legacy\n")
        with self.assertRaises(SystemExit):
            scaffold.init(legacy)
        self.assertFalse(os.path.exists(os.path.join(legacy, ".ldl-version")))


if __name__ == "__main__":
    unittest.main()
