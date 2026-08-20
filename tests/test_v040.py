import csv
import hashlib
import json
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
import lean  # noqa: E402


CONTRACT = """# 00_CONTRACT — lean

[interview](raw/interview.md)

## Governance profile
- Contract version: v1
- Approval mode: human
- Quantitative claims: no
- Risk level: low

## Delivery profile
- Delivery mode: startup-reversible
- First executable increment: MVP-1
- Release strategy: ship-first

## Launch brief
- Target user: one early adopter
- Problem: one painful repeated task
- Smallest value journey: submit one input and receive one useful result
- Launch metric: one completed journey
- Feedback channel: in-product feedback link
- Kill criteria: zero completed journeys in the timebox
- Timebox: one week
- Risk: low-reversible
- Rollback: restore the previous static artifact

## 2W1H
- Why: solve a real user problem [IV-01]
- What: one working MVP [IV-02]
- How: incremental delivery and independent verification [IV-03]

## Constraints
- one week [IV-04]

## Evaluation criteria
1. deterministic behavior passes — judge: code (test script) [IV-03]
2. user journey renders and completes — judge: fresh-context (independent browser review) [IV-05]

## Failure conditions
1. core test fails
2. no executable user journey
3. independent check is not run

## Execution plan
| phase | path | verify | gate | budget |
|---|---|---|---|---|
| P5+P6 | 05_engineering/ | increment ledger | yes | one week |

## Execution economy
- Phase packet max bytes: 8192
- Relay summary max chars: 1500
- Checker summary max chars: 4000
- Checker runs per increment: 1
- Correction reruns per increment: 1
- Token/call ledger: logs/cost-ledger.csv

## Verification setup
- Verifier instances: tests and independent browser review
- Lint command: python3 tools/lint.py .
- Approver: Daniel
- Verifier workspace: external scratch
- Target access: read-only

## Exit tests
- T1 can it fail: three conditions listed
- T2 stranger: fresh review passed
- T3 judge: judges named
- T4 constraint collision: scope fits
- T5 primary source: IV-01 through IV-05 cited
"""

PROGRESS = """# PROGRESS — lean

## Phase progress
| Phase | Status | Date | Deliverable |
|---|---|---|---|
| P0 contract | done | 2026-01-01 | [contract](00_CONTRACT.md) |
| P1 requirements | pending | | [requirements](01_REQUIREMENTS.md) |
| P2 structure | pending | | [constitution](CLAUDE.md) |
| P3 research | pending | | [evidence](03_EVIDENCE.md) |
| P4 scoping | pending | | [scope](04_SCOPE.md) |
| P5+P6 increments | pending | | [verification](06_VERIFICATION.md) |

## Gate ledger
| Gate | Verdict | Contract version | Approval mode | Approver | Approved at | Evidence |
|---|---|---|---|---|---|---|
| G1 | PENDING | v1 | human | | | |
| G2 | PENDING | v1 | human | | | |
| G3 | PENDING | v1 | human | | | |
| G4 | PENDING | v1 | human | | | |

## Increment ledger
| Increment | Experiment | User journey | Status | Deterministic tests | Rendered/browser | Independent check | Evidence |
|---|---|---|---|---|---|---|---|
| MVP-1 | LAUNCH | user submits one input and receives one verified result | PENDING | NOT_RUN | NOT_RUN | NOT_RUN | [verification](06_VERIFICATION.md) |

## Release ledger
| Release | Verdict | Increment | Risk | Instrumentation | Feedback | Rollback | Live artifact | Approver | Released at | Evidence |
|---|---|---|---|---|---|---|---|---|---|---|
| RELEASE-1 | PENDING | MVP-1 | low-reversible | NOT_RUN | NOT_RUN | NOT_RUN | pending | | | pending |

## Experiment ledger
| Experiment | Hypothesis | Change | Metric | Status | Evidence | Decision |
|---|---|---|---|---|---|---|
| EXP-1 | real users complete the core journey | next smallest change | completion rate | NOT_RUN | pending | PENDING |

Events: [events](logs/log.md)
"""


class V040Tests(unittest.TestCase):
    def setUp(self):
        warnings.simplefilter("ignore", ResourceWarning)
        self.tmp = tempfile.mkdtemp(prefix="ldl-v040-")
        self.ws = os.path.join(self.tmp, "ws")
        scaffold.init(self.ws)
        self.proj = scaffold.new_project(self.ws, "lean", "2026-01-01")
        files = {
            "00_CONTRACT.md": CONTRACT,
            "PROGRESS.md": PROGRESS,
            "01_REQUIREMENTS.md": "# requirements\n\n## Requirements ledger\n| Requirement ID | Type | Priority | Requirement | Verification | Source |\n|---|---|---|---|---|---|\n| R-01 | functional | must | working journey | browser test | (b) IV-02 |\n",
            "03_EVIDENCE.md": "# evidence\n\n## Evidence ledger\n| Claim ID | Label | Claim | Source artifact | Captured at | Scope/window | Transform/reproducer | Status |\n|---|---|---|---|---|---|---|---|\n",
            "04_SCOPE.md": "# scope\n\n## Impact dimensions\n| Dimension ID | Status | Evidence |\n|---|---|---|\n| D-01 | NOT_RUN | [evidence](03_EVIDENCE.md) |\n\n## Action readiness\n| Action ID | Impact dimensions | Preconditions | Approval tier | Approval evidence | Canary | Rollback | Ready |\n|---|---|---|---|---|---|---|---|\n| A-01 | D-01 | G3 PASS | 1 | pending | one journey | restore | NO |\n",
            "06_VERIFICATION.md": "# verification\n\n## Requirement verdicts\n| Requirement ID | Verdict | Evidence |\n|---|---|---|\n| R-01 | NOT_RUN | pending |\n\n## Final verdicts\n- Harness: NOT_RUN\n- Product: NOT_RUN\n- Execution readiness: HOLD\n- Method conformance: PASS\n- Historical violations: NONE\n- Independent verifier: fresh-context (owner)\n- Target mutation: 0 files\n",
            "raw/interview.md": "IV-01 .. IV-05",
            "logs/log.md": "# events\n",
            "logs/cost-ledger.csv": "timestamp,phase,role,model,input_tokens,output_tokens,cache_tokens,llm_calls,checker_runs,wall_seconds,evidence\n",
            "05_engineering/evidence/deterministic/tests.txt": "17 tests PASS\n",
            "05_engineering/evidence/rendered/render.txt": "2 browser cases; console errors 0\n",
            "05_engineering/evidence/independent/report.txt": "fresh verifier PASS; target mutation 0\n",
            "05_engineering/evidence/release/smoke.txt": "live smoke PASS; console errors 0\n",
            "05_engineering/evidence/release/telemetry.txt": "completion event observed\n",
            "05_engineering/evidence/release/rollback.txt": "rollback command verified\n",
            "05_engineering/evidence/release/feedback.txt": "feedback channel reachable\n",
            "05_engineering/evidence/experiments/exp1.txt": "5 users; 4 completed\n",
            "05_engineering/evidence/increments/f1.txt": "export journey tests and browser trace PASS\n",
        }
        for rel, text in files.items():
            path = os.path.join(self.proj, rel)
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w", encoding="utf-8", newline="") as handle:
                handle.write(text)
        def artifact(rel):
            path = os.path.join(self.proj, rel)
            return {"path": rel, "sha256": hashlib.sha256(open(path, "rb").read()).hexdigest()}
        manifest = {
            "schema": "ldl-mvp-evidence-v1",
            "maker": "maker-agent",
            "increment": "MVP-1",
            "user_journey": "user submits one input and receives one verified result",
            "deterministic": {"status": "PASS", "command": "python tests.py", "checks": 17,
                              "artifact": artifact("05_engineering/evidence/deterministic/tests.txt")},
            "rendered": {"status": "PASS", "instrument": "browser", "cases": 2, "console_errors": 0,
                         "artifact": artifact("05_engineering/evidence/rendered/render.txt")},
            "independent": {"status": "PASS", "verifier": "fresh-context", "target_mutation": 0,
                            "artifact": artifact("05_engineering/evidence/independent/report.txt")},
        }
        with open(os.path.join(self.proj, "05_engineering", "evidence", "mvp1.json"), "w", encoding="utf-8") as handle:
            json.dump(manifest, handle)
        experiment_manifest = {
            "schema": "ldl-experiment-evidence-v1", "experiment": "EXP-1",
            "source": "behavior-telemetry", "observations": 5,
            "metric": "request rate", "result": "4 of 5 users requested export",
            "artifact": artifact("05_engineering/evidence/experiments/exp1.txt"),
        }
        with open(os.path.join(self.proj, "05_engineering", "evidence", "experiments", "exp1.json"), "w", encoding="utf-8") as handle:
            json.dump(experiment_manifest, handle)
        release_manifest = {
            "schema": "ldl-release-evidence-v1", "release": "RELEASE-1", "increment": "MVP-1",
            "live_url": "https://example.test/mvp", "released_at": "2026-01-02T00:00:00Z",
            "smoke": {"status": "PASS", "cases": 2, "console_errors": 0, "artifact": artifact("05_engineering/evidence/release/smoke.txt")},
            "telemetry": {"status": "PASS", "event": "journey_completed", "artifact": artifact("05_engineering/evidence/release/telemetry.txt")},
            "rollback": {"status": "READY", "command": "restore previous", "artifact": artifact("05_engineering/evidence/release/rollback.txt")},
            "feedback": {"status": "READY", "channel": "https://example.test/feedback", "artifact": artifact("05_engineering/evidence/release/feedback.txt")},
        }
        with open(os.path.join(self.proj, "05_engineering", "evidence", "release.json"), "w", encoding="utf-8") as handle:
            json.dump(release_manifest, handle)
        for rel, text in {
            "CLAUDE.md": "# Workspace constitution\n\ncontract first; preserve evidence\n",
            "projects/CLAUDE.md": "# Shared protocol\n\nread contract; preserve gate order\n",
        }.items():
            with open(os.path.join(self.ws, rel), "w", encoding="utf-8") as handle:
                handle.write(text)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def errors(self):
        lint = Lint(self.ws)
        lint.run()
        return lint.errors

    def replace(self, rel, old, new):
        path = os.path.join(self.proj, rel)
        text = open(path, encoding="utf-8").read()
        open(path, "w", encoding="utf-8").write(text.replace(old, new))

    def pass_mvp1(self):
        self.replace("PROGRESS.md", "| MVP-1 | LAUNCH | user submits one input and receives one verified result | PENDING | NOT_RUN | NOT_RUN | NOT_RUN |", "| MVP-1 | LAUNCH | user submits one input and receives one verified result | PASS | PASS | PASS | PASS |")
        self.replace("PROGRESS.md", "| PASS | PASS | PASS | PASS | [verification](06_VERIFICATION.md) |", "| PASS | PASS | PASS | PASS | [proof](05_engineering/evidence/mvp1.json) |")

    def pass_g1(self):
        self.replace("PROGRESS.md", "| G1 | PENDING | v1 | human | | | |", "| G1 | PASS | v1 | human | Daniel | 2026-01-01T00:00:00Z | [approval](raw/approval-g1.md) |")
        with open(os.path.join(self.proj, "raw", "approval-g1.md"), "w", encoding="utf-8") as handle:
            handle.write("Daniel approves Gate 1 for contract v1.")
        with open(os.path.join(self.proj, "logs", "log.md"), "a", encoding="utf-8") as handle:
            handle.write("GATE-PASS: G1 contract=v1\n")

    def prepare_launch_docs(self):
        for phase in ("P1 requirements", "P2 structure", "P4 scoping"):
            self.replace("PROGRESS.md", f"| {phase} | pending | |", f"| {phase} | done | 2026-01-01 |")

    def pass_release1(self):
        self.pass_g1()
        self.prepare_launch_docs()
        self.pass_mvp1()
        self.replace("PROGRESS.md", "| RELEASE-1 | PENDING | MVP-1 | low-reversible | NOT_RUN | NOT_RUN | NOT_RUN | pending | | | pending |", "| RELEASE-1 | PASS | MVP-1 | low-reversible | PASS | PASS | PASS | https://example.test/mvp | Daniel | 2026-01-02T00:00:00Z | [release](05_engineering/evidence/release.json) |")

    def assert_error(self, fragment):
        errors = self.errors()
        self.assertTrue(any(fragment in value for value in errors), errors)

    def test_scaffold_is_v040_and_installs_lean_tool(self):
        self.assertEqual("0.4.0", open(os.path.join(self.ws, ".ldl-version")).read().strip())
        self.assertTrue(os.path.isfile(os.path.join(self.ws, "tools", "lean.py")))
        self.assertTrue(os.path.isfile(os.path.join(self.ws, "templates", "phase-packet.json")))
        self.assertTrue(os.path.isfile(os.path.join(self.ws, "owner", "inbox.md")))

    def test_clean_v040_workspace_passes(self):
        self.assertEqual([], self.errors())

    def test_startup_release_can_pass_with_g2_to_g4_pending(self):
        self.pass_g1()
        self.prepare_launch_docs()
        self.pass_mvp1()
        self.replace("PROGRESS.md", "| RELEASE-1 | PENDING | MVP-1 | low-reversible | NOT_RUN | NOT_RUN | NOT_RUN | pending | | | pending |", "| RELEASE-1 | PASS | MVP-1 | low-reversible | PASS | PASS | PASS | https://example.test/mvp | Daniel | 2026-01-02T00:00:00Z | [release](05_engineering/evidence/release.json) |")
        self.assertEqual([], self.errors())

    def test_release_pass_requires_launch_controls(self):
        self.pass_g1()
        self.prepare_launch_docs()
        self.pass_mvp1()
        self.replace("PROGRESS.md", "| RELEASE-1 | PENDING |", "| RELEASE-1 | PASS |")
        self.assert_error("release PASS requires instrumentation/feedback/rollback PASS")

    def test_release_pass_requires_launch_documents(self):
        self.pass_g1()
        self.pass_mvp1()
        self.replace("PROGRESS.md", "| RELEASE-1 | PENDING | MVP-1 | low-reversible | NOT_RUN | NOT_RUN | NOT_RUN | pending | | | pending |", "| RELEASE-1 | PASS | MVP-1 | low-reversible | PASS | PASS | PASS | https://example.test/mvp | Daniel | 2026-01-02T00:00:00Z | [release](05_engineering/evidence/release.json) |")
        self.assert_error("release PASS requires launch documents done")

    def test_high_risk_release_requires_g4(self):
        self.replace("00_CONTRACT.md", "- Delivery mode: startup-reversible", "- Delivery mode: gated-high-risk")
        self.replace("00_CONTRACT.md", "- Risk: low-reversible", "- Risk: high-risk")
        self.pass_g1()
        self.prepare_launch_docs()
        self.pass_mvp1()
        self.replace("PROGRESS.md", "| RELEASE-1 | PENDING | MVP-1 | low-reversible | NOT_RUN | NOT_RUN | NOT_RUN | pending | | | pending |", "| RELEASE-1 | PASS | MVP-1 | high-risk | PASS | PASS | PASS | https://example.test/mvp | Daniel | 2026-01-02T00:00:00Z | [release](05_engineering/evidence/release.json) |")
        self.assert_error("high-risk release requires G4 PASS")

    def test_post_launch_increment_requires_measured_experiment(self):
        path = os.path.join(self.proj, "PROGRESS.md")
        text = open(path, encoding="utf-8").read()
        anchor = "| MVP-1 | LAUNCH | user submits one input and receives one verified result | PENDING | NOT_RUN | NOT_RUN | NOT_RUN | [verification](06_VERIFICATION.md) |"
        extra = anchor + "\n| F-1 | EXP-1 | add requested export | PASS | PASS | PASS | PASS | [proof](05_engineering/evidence/increments/f1.txt) |"
        open(path, "w", encoding="utf-8").write(text.replace(anchor, extra))
        self.assert_error("PASS increment requires measured experiment signal")

    def test_measured_experiment_allows_feedback_driven_increment(self):
        self.pass_release1()
        path = os.path.join(self.proj, "PROGRESS.md")
        text = open(path, encoding="utf-8").read()
        anchor = "| MVP-1 | LAUNCH | user submits one input and receives one verified result | PASS | PASS | PASS | PASS | [proof](05_engineering/evidence/mvp1.json) |"
        extra = anchor + "\n| F-1 | EXP-1 | add requested export | PASS | PASS | PASS | PASS | [proof](05_engineering/evidence/increments/f1.txt) |"
        text = text.replace(anchor, extra)
        text = text.replace("| EXP-1 | real users complete the core journey | next smallest change | completion rate | NOT_RUN | pending | PENDING |", "| EXP-1 | real users request export | add export | request rate | MEASURED | [signal](05_engineering/evidence/experiments/exp1.json) | EXPAND |")
        open(path, "w", encoding="utf-8").write(text)
        self.assertEqual([], self.errors())

    def test_complete_working_mvp_passes(self):
        self.replace("PROGRESS.md", "| P5+P6 increments | pending | |", "| P5+P6 increments | done | 2026-01-01 |")
        self.replace("PROGRESS.md", "| MVP-1 | LAUNCH | user submits one input and receives one verified result | PENDING | NOT_RUN | NOT_RUN | NOT_RUN |", "| MVP-1 | LAUNCH | user submits one input and receives one verified result | PASS | PASS | PASS | PASS |")
        self.replace("PROGRESS.md", "| PASS | PASS | PASS | PASS | [verification](06_VERIFICATION.md) |", "| PASS | PASS | PASS | PASS | [proof](05_engineering/evidence/mvp1.json) |")
        self.replace("06_VERIFICATION.md", "| R-01 | NOT_RUN | pending |", "| R-01 | PASS | [proof](03_EVIDENCE.md) |")
        self.replace("06_VERIFICATION.md", "- Harness: NOT_RUN", "- Harness: PASS")
        self.replace("06_VERIFICATION.md", "- Product: NOT_RUN", "- Product: PASS")
        ledger = os.path.join(self.proj, "logs", "cost-ledger.csv")
        with open(ledger, "a", encoding="utf-8") as handle:
            handle.write("2026-01-01T00:00:00Z,P5,maker,test-model,100,20,0,1,0,60,logs/log.md\n")
        self.assertEqual([], self.errors())

    def test_missing_execution_economy_fails(self):
        path = os.path.join(self.proj, "00_CONTRACT.md")
        text = open(path).read()
        start = text.index("## Execution economy")
        end = text.index("## Verification setup")
        open(path, "w").write(text[:start] + text[end:])
        self.assert_error("Execution economy missing")

    def test_packet_caps_and_hash_are_enforced(self):
        artifact = os.path.join(self.proj, "raw", "interview.md")
        digest = hashlib.sha256(open(artifact, "rb").read()).hexdigest()
        packet = {
            "schema": "ldl-phase-packet-v1",
            "phase": "P5",
            "task": "build MVP-1",
            "summary": "bounded packet",
            "requirements": ["R-01"],
            "commands": ["python -m unittest"],
            "blockers": [],
            "artifacts": [{"path": "raw/interview.md", "sha256": digest}],
        }
        path = os.path.join(self.proj, "logs", "packet.json")
        open(path, "w").write(json.dumps(packet))
        self.assertEqual([], lean.verify_packet(path, self.proj))
        packet["summary"] = "x" * 1501
        open(path, "w").write(json.dumps(packet))
        self.assertTrue(any("summary exceeds" in value for value in lean.verify_packet(path, self.proj)))
        packet["summary"] = "ok"
        packet["artifacts"][0]["sha256"] = "0" * 64
        open(path, "w").write(json.dumps(packet))
        self.assertTrue(any("hash mismatch" in value for value in lean.verify_packet(path, self.proj)))

    def test_packet_size_and_path_escape_are_rejected(self):
        packet = {
            "schema": "ldl-phase-packet-v1", "phase": "P5", "task": "x", "summary": "ok",
            "requirements": [], "commands": [], "blockers": ["x" * 9000],
            "artifacts": [{"path": "../outside", "sha256": "0" * 64}],
        }
        path = os.path.join(self.proj, "logs", "oversized.json")
        open(path, "w").write(json.dumps(packet))
        errors = lean.verify_packet(path, self.proj)
        self.assertTrue(any("packet exceeds" in value for value in errors), errors)
        self.assertTrue(any("escapes packet root" in value for value in errors), errors)

    def test_packet_nested_verbatim_payload_is_rejected(self):
        packet = {
            "schema": "ldl-phase-packet-v1", "phase": "P5", "task": "x", "summary": "ok",
            "requirements": [], "commands": [], "blockers": [], "artifacts": [],
            "payload": {"content": "VERBATIM REPORT"},
        }
        path = os.path.join(self.proj, "logs", "nested.json")
        open(path, "w").write(json.dumps(packet))
        self.assertTrue(any("unexpected/embedded fields" in value for value in lean.verify_packet(path, self.proj)))

    def test_packet_allowed_lists_cannot_carry_full_reports(self):
        packet = {
            "schema": "ldl-phase-packet-v1", "phase": "P5", "task": "x", "summary": "ok",
            "requirements": ["FULL VERBATIM REPORT: hidden prose"],
            "commands": [], "blockers": ["FULL VERBATIM REPORT " + "x" * 380] * 12, "artifacts": [],
        }
        path = os.path.join(self.proj, "logs", "verbatim-list.json")
        open(path, "w").write(json.dumps(packet))
        errors = lean.verify_packet(path, self.proj)
        self.assertTrue(any("requirement must be an ID" in value for value in errors), errors)
        self.assertTrue(any("blockers aggregate exceeds" in value for value in errors), errors)

    def test_product_pass_requires_working_mvp_increment(self):
        self.replace("06_VERIFICATION.md", "| R-01 | NOT_RUN | pending |", "| R-01 | PASS | [proof](03_EVIDENCE.md) |")
        self.replace("06_VERIFICATION.md", "- Harness: NOT_RUN", "- Harness: PASS")
        self.replace("06_VERIFICATION.md", "- Product: NOT_RUN", "- Product: PASS")
        self.assert_error("Product PASS requires MVP-1 increment PASS")

    def test_increment_pass_requires_render_and_independent_check(self):
        self.replace("PROGRESS.md", "| MVP-1 | LAUNCH | user submits one input and receives one verified result | PENDING | NOT_RUN | NOT_RUN | NOT_RUN |", "| MVP-1 | LAUNCH | user submits one input and receives one verified result | PASS | PASS | NOT_RUN | NOT_RUN |")
        self.assert_error("PASS increment requires tests/render/independent PASS")

    def test_increment_pass_rejects_report_self_attestation(self):
        self.replace("PROGRESS.md", "| MVP-1 | LAUNCH | user submits one input and receives one verified result | PENDING | NOT_RUN | NOT_RUN | NOT_RUN |", "| MVP-1 | LAUNCH | user submits one input and receives one verified result | PASS | PASS | PASS | PASS |")
        self.assert_error("evidence must be under 05_engineering")

    def test_increment_pass_rejects_empty_arbitrary_engineering_file(self):
        empty = os.path.join(self.proj, "05_engineering", "evidence", "empty.json")
        open(empty, "w").write("")
        self.replace("PROGRESS.md", "| MVP-1 | LAUNCH | user submits one input and receives one verified result | PENDING | NOT_RUN | NOT_RUN | NOT_RUN | [verification](06_VERIFICATION.md) |", "| MVP-1 | LAUNCH | user submits one input and receives one verified result | PASS | PASS | PASS | PASS | [proof](05_engineering/evidence/empty.json) |")
        self.assert_error("MVP evidence is empty")

    def test_mvp_manifest_rejects_maker_self_attestation_and_reused_artifact(self):
        manifest_path = os.path.join(self.proj, "05_engineering", "evidence", "mvp1.json")
        manifest = json.load(open(manifest_path, encoding="utf-8"))
        shared = manifest["deterministic"]["artifact"]
        manifest["rendered"]["artifact"] = shared
        manifest["independent"]["artifact"] = shared
        manifest["independent"]["verifier"] = "maker"
        with open(manifest_path, "w", encoding="utf-8") as handle:
            json.dump(manifest, handle)
        self.replace("PROGRESS.md", "| MVP-1 | LAUNCH | user submits one input and receives one verified result | PENDING | NOT_RUN | NOT_RUN | NOT_RUN |", "| MVP-1 | LAUNCH | user submits one input and receives one verified result | PASS | PASS | PASS | PASS |")
        self.replace("PROGRESS.md", "| PASS | PASS | PASS | PASS | [verification](06_VERIFICATION.md) |", "| PASS | PASS | PASS | PASS | [proof](05_engineering/evidence/mvp1.json) |")
        self.assert_error("independent verifier must be separated from maker")
        self.assert_error("artifact path escapes boundary")

    def test_fresh_context_maker_is_not_independent(self):
        manifest_path = os.path.join(self.proj, "05_engineering", "evidence", "mvp1.json")
        manifest = json.load(open(manifest_path, encoding="utf-8"))
        manifest["independent"]["verifier"] = "fresh-context-maker"
        with open(manifest_path, "w", encoding="utf-8") as handle:
            json.dump(manifest, handle)
        self.pass_mvp1()
        self.assert_error("independent verifier must be separated from maker")

    def test_measured_feature_cannot_precede_mvp_release(self):
        self.pass_mvp1()
        path = os.path.join(self.proj, "PROGRESS.md")
        text = open(path, encoding="utf-8").read()
        anchor = "| MVP-1 | LAUNCH | user submits one input and receives one verified result | PASS | PASS | PASS | PASS | [proof](05_engineering/evidence/mvp1.json) |"
        text = text.replace(anchor, anchor + "\n| F-1 | EXP-1 | export requested by users | PASS | PASS | PASS | PASS | [proof](05_engineering/evidence/increments/f1.txt) |")
        text = text.replace("| EXP-1 | real users complete the core journey | next smallest change | completion rate | NOT_RUN | pending | PENDING |", "| EXP-1 | real users request export | add export | request rate | MEASURED | [signal](05_engineering/evidence/experiments/exp1.json) | EXPAND |")
        open(path, "w", encoding="utf-8").write(text)
        self.assert_error("post-MVP PASS increment requires MVP-1 Release PASS")

    def test_measured_experiment_requires_substantive_typed_evidence(self):
        self.replace("PROGRESS.md", "| EXP-1 | real users complete the core journey | next smallest change | completion rate | NOT_RUN | pending | PENDING |", "| EXP-1 | | | | MEASURED | [signal](05_engineering/evidence/experiments/exp1.json) | ITERATE |")
        self.assert_error("measured experiment missing Hypothesis")
        self.assert_error("experiment evidence identity/metric mismatch")

    def test_one_experiment_and_artifact_cannot_authorize_two_features(self):
        self.pass_release1()
        path = os.path.join(self.proj, "PROGRESS.md")
        text = open(path, encoding="utf-8").read()
        anchor = "| MVP-1 | LAUNCH | user submits one input and receives one verified result | PASS | PASS | PASS | PASS | [proof](05_engineering/evidence/mvp1.json) |"
        additions = (
            "\n| F-1 | EXP-1 | export requested by users | PASS | PASS | PASS | PASS | [proof](05_engineering/evidence/increments/f1.txt) |"
            "\n| F-2 | EXP-1 | second export variant | PASS | PASS | PASS | PASS | [proof](05_engineering/evidence/increments/f1.txt) |"
        )
        text = text.replace(anchor, anchor + additions)
        text = text.replace("| EXP-1 | real users complete the core journey | next smallest change | completion rate | NOT_RUN | pending | PENDING |", "| EXP-1 | real users request export | add export | request rate | MEASURED | [signal](05_engineering/evidence/experiments/exp1.json) | EXPAND |")
        open(path, "w", encoding="utf-8").write(text)
        self.assert_error("PASS increments must use distinct primary artifacts")
        self.assert_error("each measured experiment can authorize only one PASS increment")

    def test_release_rejects_empty_host_wrong_approver_future_and_copied_evidence(self):
        self.pass_g1()
        self.prepare_launch_docs()
        self.pass_mvp1()
        same = b"omnibus copied claim\n"
        manifest_path = os.path.join(self.proj, "05_engineering", "evidence", "release.json")
        manifest = json.load(open(manifest_path, encoding="utf-8"))
        for section in ("smoke", "telemetry", "rollback", "feedback"):
            artifact_path = os.path.join(self.proj, manifest[section]["artifact"]["path"])
            open(artifact_path, "wb").write(same)
            manifest[section]["artifact"]["sha256"] = hashlib.sha256(same).hexdigest()
        manifest["live_url"] = "https://"
        manifest["released_at"] = "2999-01-02T00:00:00Z"
        with open(manifest_path, "w", encoding="utf-8") as handle:
            json.dump(manifest, handle)
        self.replace("PROGRESS.md", "| RELEASE-1 | PENDING | MVP-1 | low-reversible | NOT_RUN | NOT_RUN | NOT_RUN | pending | | | pending |", "| RELEASE-1 | PASS | MVP-1 | low-reversible | PASS | PASS | PASS | https:// | maker-agent | 2999-01-02T00:00:00Z | [release](05_engineering/evidence/release.json) |")
        self.assert_error("requires https live artifact")
        self.assert_error("approver must match G1 approver")
        self.assert_error("Released at cannot be in the future")
        self.assert_error("artifact hashes must be distinct")

    def test_live_url_parser_rejects_invalid_public_urls(self):
        invalid = (
            "https://.",
            "https://exa mple.com/path",
            "https://example.com:bad/path",
            "https://example.com/has space",
            "https://localhost/path",
            "https://singlelabel/path",
            "https://999.999.999.999/path",
            "https://127.0.0.01/path",
            "https://127.0.0.1/path",
            "https://10.0.0.1/path",
            "https://169.254.1.1/path",
            "https://0.0.0.0/path",
            "https://[::1]/path",
            "https://[::ffff:127.0.0.1]/path",
        )
        for value in invalid:
            self.assertFalse(lean.valid_https_url(value), value)
        self.assertTrue(lean.valid_https_url("https://product.pages.dev/mvp"))
        self.assertTrue(lean.valid_https_url("https://8.8.8.8/mvp"))
        self.assertTrue(lean.valid_https_url("https://[2606:4700:4700::1111]/mvp"))

    def test_release_integration_rejects_malformed_and_nonpublic_ip_hosts(self):
        self.pass_g1()
        self.prepare_launch_docs()
        self.pass_mvp1()
        manifest_path = os.path.join(self.proj, "05_engineering", "evidence", "release.json")
        manifest = json.load(open(manifest_path, encoding="utf-8"))
        manifest["live_url"] = "https://999.999.999.999/mvp"
        with open(manifest_path, "w", encoding="utf-8") as handle:
            json.dump(manifest, handle)
        self.replace("PROGRESS.md", "| RELEASE-1 | PENDING | MVP-1 | low-reversible | NOT_RUN | NOT_RUN | NOT_RUN | pending | | | pending |", "| RELEASE-1 | PASS | MVP-1 | low-reversible | PASS | PASS | PASS | https://999.999.999.999/mvp | Daniel | 2026-01-02T00:00:00Z | [release](05_engineering/evidence/release.json) |")
        self.assert_error("requires https live artifact")
        self.replace("PROGRESS.md", "https://999.999.999.999/mvp", "https://127.0.0.1/mvp")
        manifest["live_url"] = "https://127.0.0.1/mvp"
        with open(manifest_path, "w", encoding="utf-8") as handle:
            json.dump(manifest, handle)
        self.assert_error("requires https live artifact")

    def test_completion_requires_cost_ledger_data(self):
        self.replace("PROGRESS.md", "| P5+P6 increments | pending | |", "| P5+P6 increments | done | 2026-01-01 |")
        self.replace("PROGRESS.md", "| MVP-1 | LAUNCH | user submits one input and receives one verified result | PENDING | NOT_RUN | NOT_RUN | NOT_RUN |", "| MVP-1 | LAUNCH | user submits one input and receives one verified result | PASS | PASS | PASS | PASS |")
        self.assert_error("completed delivery requires cost ledger data")

    def test_garbage_cost_row_does_not_satisfy_telemetry(self):
        self.replace("PROGRESS.md", "| P5+P6 increments | pending | |", "| P5+P6 increments | done | 2026-01-01 |")
        self.replace("PROGRESS.md", "| MVP-1 | LAUNCH | user submits one input and receives one verified result | PENDING | NOT_RUN | NOT_RUN | NOT_RUN |", "| MVP-1 | LAUNCH | user submits one input and receives one verified result | PASS | PASS | PASS | PASS |")
        ledger = os.path.join(self.proj, "logs", "cost-ledger.csv")
        with open(ledger, "a", encoding="utf-8") as handle:
            handle.write("now,P5,maker,model,NaN,0,0,1,1,10,logs/log.md\n")
        self.assert_error("non-integer metrics")

    def test_cost_ledger_path_escape_is_rejected(self):
        outside = os.path.join(self.tmp, "outside.csv")
        with open(outside, "w", encoding="utf-8") as handle:
            handle.write("timestamp,phase,role,model,input_tokens,output_tokens,cache_tokens,llm_calls,checker_runs,wall_seconds,evidence\n")
        self.replace("00_CONTRACT.md", "- Token/call ledger: logs/cost-ledger.csv", "- Token/call ledger: ../../outside.csv")
        self.assert_error("Token/call ledger path escapes boundary")

    def test_cost_row_requires_valid_timestamp_and_existing_evidence(self):
        self.replace("PROGRESS.md", "| P5+P6 increments | pending | |", "| P5+P6 increments | done | 2026-01-01 |")
        self.replace("PROGRESS.md", "| MVP-1 | LAUNCH | user submits one input and receives one verified result | PENDING | NOT_RUN | NOT_RUN | NOT_RUN |", "| MVP-1 | LAUNCH | user submits one input and receives one verified result | PASS | PASS | PASS | PASS |")
        self.replace("PROGRESS.md", "| PASS | PASS | PASS | PASS | [verification](06_VERIFICATION.md) |", "| PASS | PASS | PASS | PASS | [proof](05_engineering/evidence/mvp1.json) |")
        ledger = os.path.join(self.proj, "logs", "cost-ledger.csv")
        with open(ledger, "a", encoding="utf-8") as handle:
            handle.write("2026-1-1T0:0:0Z,P5,maker,model,1,1,0,1,1,10,missing.txt\n")
        self.assert_error("timestamp must be UTC ISO-8601")

    def test_cost_row_cannot_cite_ledger_itself(self):
        self.replace("PROGRESS.md", "| P5+P6 increments | pending | |", "| P5+P6 increments | done | 2026-01-01 |")
        self.replace("PROGRESS.md", "| MVP-1 | LAUNCH | user submits one input and receives one verified result | PENDING | NOT_RUN | NOT_RUN | NOT_RUN |", "| MVP-1 | LAUNCH | user submits one input and receives one verified result | PASS | PASS | PASS | PASS |")
        self.replace("PROGRESS.md", "| PASS | PASS | PASS | PASS | [verification](06_VERIFICATION.md) |", "| PASS | PASS | PASS | PASS | [proof](05_engineering/evidence/mvp1.json) |")
        ledger = os.path.join(self.proj, "logs", "cost-ledger.csv")
        with open(ledger, "a", encoding="utf-8") as handle:
            handle.write("2026-01-01T00:00:00Z,P5,maker,model,1,1,0,1,1,10,logs/cost-ledger.csv\n")
        self.assert_error("cannot cite the ledger itself")

    def test_raw_is_recursive_and_skip_names_do_not_escape(self):
        nested = os.path.join(self.proj, "raw", "tools", "deep", "source.txt")
        os.makedirs(os.path.dirname(nested), exist_ok=True)
        open(nested, "w").write("original")
        self.assertEqual([], self.errors())
        open(nested, "w").write("changed")
        self.assert_error("raw file changed")

    def test_raw_directory_symlink_is_rejected(self):
        target = os.path.join(self.tmp, "external")
        os.makedirs(target)
        link = os.path.join(self.proj, "raw", "linked")
        try:
            os.symlink(target, link, target_is_directory=True)
        except OSError:
            self.skipTest("symlinks unavailable")
        self.assert_error("raw directory symlink")

    def test_contract_archive_is_opaque_to_links_but_immutable(self):
        archive = os.path.join(self.proj, "raw", "contract-archive", "snapshot.md")
        os.makedirs(os.path.dirname(archive), exist_ok=True)
        open(archive, "w").write("[old link](missing.md)\n")
        # reach the archive: L1 must still treat the byte snapshot as opaque
        self.replace("PROGRESS.md", "Events: [events](logs/log.md)", "[snapshot](raw/contract-archive/snapshot.md)\n\nEvents: [events](logs/log.md)")
        self.assertEqual([], self.errors())
        open(archive, "w").write("mutated")
        self.assert_error("raw file changed")
        open(archive, "w").write("[old link](missing.md)\n")
        self.assertEqual([], self.errors())
        os.remove(archive)
        self.assert_error("raw file deleted")

    def test_live_broken_link_still_fails(self):
        self.replace("PROGRESS.md", "Events: [events](logs/log.md)", "[broken](missing.md)\n\nEvents: [events](logs/log.md)")
        self.assert_error("broken link")

    def test_project_directory_symlink_is_rejected(self):
        real = os.path.join(self.tmp, "real-project")
        os.makedirs(real)
        link = os.path.join(self.ws, "projects", "2026-01-02_linked")
        try:
            os.symlink(real, link, target_is_directory=True)
        except OSError:
            self.skipTest("symlinks unavailable")
        self.assert_error("project directory symlink")

    def test_explicit_v04_migration_only(self):
        legacy = os.path.join(self.tmp, "legacy-v03")
        os.makedirs(os.path.join(legacy, "tools"))
        with open(os.path.join(legacy, "index.md"), "w", encoding="utf-8") as handle:
            handle.write("# index\n\n## Protocol\n\n## Projects\n")
        with open(os.path.join(legacy, ".ldl-version"), "w", encoding="utf-8") as handle:
            handle.write("0.3.0\n")
        with open(os.path.join(legacy, "tools", "lint.py"), "w", encoding="utf-8") as handle:
            handle.write("# old v0.3 tool\n")
        scaffold.init(legacy)
        self.assertEqual("0.3.0", open(os.path.join(legacy, ".ldl-version")).read().strip())
        self.assertEqual("# old v0.3 tool\n", open(os.path.join(legacy, "tools", "lint.py")).read())
        self.assertFalse(os.path.exists(os.path.join(legacy, "tools", "lean.py")))
        scaffold.init(legacy, migrate_v04=True)
        self.assertEqual("0.4.0", open(os.path.join(legacy, ".ldl-version")).read().strip())
        self.assertTrue(os.path.isfile(os.path.join(legacy, "tools", "lean.py")))
        self.assertIn("LDL reference lint", open(os.path.join(legacy, "tools", "lint.py")).read())
        index = open(os.path.join(legacy, "index.md")).read()
        self.assertIn("owner/inbox.md", index)
        self.assertIn("templates/phase-packet.json", index)

    def test_v04_migration_refuses_active_projects(self):
        legacy = os.path.join(self.tmp, "active-v03")
        os.makedirs(os.path.join(legacy, "projects", "2026-01-01_live"))
        with open(os.path.join(legacy, ".ldl-version"), "w", encoding="utf-8") as handle:
            handle.write("0.3.0\n")
        with self.assertRaises(SystemExit):
            scaffold.init(legacy, migrate_v04=True)
        self.assertEqual("0.3.0", open(os.path.join(legacy, ".ldl-version")).read().strip())

    def test_init_refuses_unsupported_marker_before_writes(self):
        mixed = os.path.join(self.tmp, "unsupported")
        os.makedirs(mixed)
        with open(os.path.join(mixed, ".ldl-version"), "w", encoding="utf-8") as handle:
            handle.write("9.9.9\n")
        before = set(os.listdir(mixed))
        with self.assertRaises(SystemExit):
            scaffold.init(mixed)
        self.assertEqual(before, set(os.listdir(mixed)))
        self.assertFalse(os.path.exists(os.path.join(mixed, "tools")))


if __name__ == "__main__":
    unittest.main()
