import hashlib
import json
import os
import shutil
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tools"))

from lint import Lint  # noqa: E402
import scaffold  # noqa: E402
import workflow  # noqa: E402
import tests.test_v040 as v040  # noqa: E402


class V050Tests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="ldl-v050-")
        self.ws = os.path.join(self.tmp, "ws")
        scaffold.init(self.ws)
        self.proj = scaffold.new_project(
            self.ws, "portfolio", "2026-01-01", "portfolio-competition")
        baseline = {
            "00_CONTRACT.md": v040.CONTRACT.replace(
                "- Delivery mode: startup-reversible", "- Delivery mode: portfolio-competition"),
            "PROGRESS.md": v040.PROGRESS,
            "01_REQUIREMENTS.md": "# requirements\n\n## Requirements ledger\n| Requirement ID | Type | Priority | Requirement | Verification | Source |\n|---|---|---|---|---|---|\n| R-01 | functional | must | working journey | browser test | (b) IV-02 |\n",
            "03_EVIDENCE.md": "# evidence\n\n## Evidence ledger\n| Claim ID | Evidence level | Evidence domain | Claim | Source artifact | Captured at | Scope/window | Transform/reproducer | Claim lifecycle |\n|---|---|---|---|---|---|---|---|---|\n",
            "04_SCOPE.md": "# scope\n\n## Impact dimensions\n| Dimension ID | Status | Evidence |\n|---|---|---|\n| D-01 | NOT_RUN | [evidence](03_EVIDENCE.md) |\n\n## Action readiness\n| Action ID | Impact dimensions | Preconditions | Approval tier | Approval evidence | Canary | Rollback | Ready |\n|---|---|---|---|---|---|---|---|\n| A-01 | D-01 | G3 PASS | 1 | pending | one journey | restore | NO |\n",
            "06_VERIFICATION.md": "# verification\n\n## Requirement verdicts\n| Requirement ID | Verdict | Evidence |\n|---|---|---|\n| R-01 | NOT_RUN | pending |\n\n## Final verdicts\n- Harness: NOT_RUN\n- Product: NOT_RUN\n- Human taste: PASS\n- Agent operability: PASS\n- Execution readiness: HOLD\n- Method conformance: PASS\n- Historical violations: NONE\n- Independent verifier: fresh-context (owner)\n- Target mutation: 0 files\n",
            "raw/interview.md": "IV-01 through IV-05\n",
        }
        for rel, text in baseline.items():
            path = os.path.join(self.proj, rel)
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w", encoding="utf-8") as handle:
                handle.write(text)
        for rel, text in {
            "CLAUDE.md": "# Workspace constitution\n\nContract first; protect raw and logs.\n",
            "projects/CLAUDE.md": "# Shared project protocol\n\nRead the active contract and use typed gates.\n",
        }.items():
            with open(os.path.join(self.ws, rel), "w", encoding="utf-8") as handle:
                handle.write(text)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def raw(self, rel, text):
        path = os.path.join(self.proj, "raw", rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(text)
        return {"path": "raw/" + rel, "sha256": hashlib.sha256(text.encode()).hexdigest()}

    def write_json(self, rel, obj):
        with open(os.path.join(self.proj, rel), "w", encoding="utf-8") as handle:
            json.dump(obj, handle, ensure_ascii=False, indent=2)

    def valid_artifacts(self):
        source = self.raw("portfolio/source.txt", "primary evidence\n")
        source2 = self.raw("portfolio/source-2.txt", "second evidence\n")
        source3 = self.raw("portfolio/source-3.txt", "third evidence\n")
        evaluator = {
            "schema": "ldl-evaluation-environment-v1",
            "contract_version": "v1",
            "evaluators": [{
                "id": "EVAL-1", "type": "ai-structural", "perspective": "fresh evaluator",
                "journey": ["inspect artifact"], "disqualification_rules": ["secret exposure"],
                "blind_inputs": ["maker prose"], "cannot_judge": ["human taste"],
                "rubric": [{"id": "CRIT-1", "weight": 100, "criterion": "evidence is reproducible"}],
            }, {
                "id": "HUMAN-1", "type": "actual-human", "perspective": "owner taste",
                "journey": ["inspect rendered result"], "disqualification_rules": ["broken journey"],
                "blind_inputs": ["internal score"], "cannot_judge": ["hidden implementation"],
                "rubric": [{"id": "TASTE-1", "weight": 100, "criterion": "decision is clear"}],
            }, {
                "id": "AGENT-1", "type": "agent-consumer", "perspective": "downstream agent",
                "journey": ["parse result"], "disqualification_rules": ["ambiguous grammar"],
                "blind_inputs": ["maker intent"], "cannot_judge": ["human emotion"],
                "rubric": [{"id": "AGENT-1", "weight": 100, "criterion": "grammar is deterministic"}],
            }],
            "submission_grammar": ["artifact", "logs"],
            "process_trace_required": True,
            "secret_policy": "values-never-enter-logs",
            "iteration_limits": {"max_rounds": 5, "minimum_delta": 2, "max_wall_seconds": 7200},
        }
        portfolio = {
            "schema": "ldl-problem-portfolio-v1",
            "contract_version": "v1",
            "selection_status": "SELECTED",
            "candidates": [
                {"id": "P-1", "problem": "first", "status": "SELECTED", "score": 90,
                 "evidence": [source], "rejection_reason": "", "reopen_conditions": []},
                {"id": "P-2", "problem": "second", "status": "REJECTED", "score": 70,
                 "evidence": [source2], "rejection_reason": "lower evaluator fit", "reopen_conditions": []},
                {"id": "P-3", "problem": "third", "status": "REVIVABLE", "score": 60,
                 "evidence": [source3], "rejection_reason": "dependency unavailable", "reopen_conditions": ["dependency available"]},
            ],
        }
        probe = self.raw("preflight/probe.txt", "probe pass\n")
        preflight = {"schema": "ldl-preflight-manifest-v1", "contract_version": "v1", "blockers": 0, "dependencies": [
            {"id": "DEP-1", "status": "PASS", "probe": "real endpoint", "limit": "bounded",
             "fallback": "captured-real", "credential_required": False, "runner_id": "checker-1",
             "executed_at": "2026-01-01T00:00:00Z", "exit_code": 0, "expected_exit_code": 0,
             "checks": 1, "evidence": probe}]}
        capability = {"schema": "ldl-capability-proof-v1", "contract_version": "v1", "capabilities": [
            {"id": "CAP-1", "promise": "one result", "required_level": "LIVE_VERIFIED", "status": "LIVE_VERIFIED",
             "demo_evidence": probe, "live_evidence": probe, "limitations": "bounded fixture"}]}
        evaluator_bytes = json.dumps(evaluator, ensure_ascii=False, indent=2).encode("utf-8")
        evaluator_sha = hashlib.sha256(evaluator_bytes).hexdigest()
        human_review = {
            "schema": "ldl-human-review-v1", "contract_version": "v1", "evaluator_id": "HUMAN-1",
            "approver": "Daniel", "decided_at": "2026-01-01T00:00:00Z", "verdict": "PASS",
            "subject": source,
        }
        human_path = os.path.join(self.proj, "raw", "human-review.json")
        with open(human_path, "w", encoding="utf-8") as handle:
            json.dump(human_review, handle, ensure_ascii=False, indent=2)
        human_evidence = {"path": "raw/human-review.json", "sha256": hashlib.sha256(open(human_path, "rb").read()).hexdigest()}
        judge = {"schema": "ldl-judge-score-v1", "contract_version": "v1", "rounds": [
            {"round": 1, "judge_id": "EVAL-1", "judge_type": "ai-structural",
             "judge_sha256": evaluator_sha, "artifact_sha256": source["sha256"], "score": 91,
             "blocking_defects": [], "unjudgeable": ["human taste"], "evidence": probe},
            {"round": 1, "judge_id": "HUMAN-1", "judge_type": "actual-human",
             "judge_sha256": evaluator_sha, "artifact_sha256": source["sha256"], "score": 90,
             "blocking_defects": [], "unjudgeable": ["hidden implementation"], "evidence": probe,
             "human_evidence": human_evidence},
            {"round": 1, "judge_id": "AGENT-1", "judge_type": "agent-consumer",
             "judge_sha256": evaluator_sha, "artifact_sha256": source["sha256"], "score": 92,
             "blocking_defects": [], "unjudgeable": ["human emotion"], "evidence": probe}]}
        submission = {"schema": "ldl-submission-manifest-v1", "contract_version": "v1", "required_files": ["artifact"],
                      "included_files": ["artifact"], "excluded_files": [],
                      "secret_scan": "PASS", "link_check": "PASS", "log_integrity": "PASS",
                      "archive_structure": "PASS", "evidence": probe}
        for rel, obj in (("02_EVALUATION.json", evaluator), ("03_PORTFOLIO.json", portfolio),
                         ("04_PREFLIGHT.json", preflight), ("06_CAPABILITIES.json", capability),
                         ("06_JUDGE_SCORES.json", judge), ("06_SUBMISSION.json", submission)):
            self.write_json(rel, obj)

    def test_latest_scaffold_has_portfolio_profile_and_project_prompt_log(self):
        self.assertEqual("0.5.0", open(os.path.join(self.ws, ".ldl-version"), encoding="utf-8").read().strip())
        for rel in ("02_EVALUATION.json", "03_PORTFOLIO.json", "04_PREFLIGHT.json",
                    "06_CAPABILITIES.json", "06_JUDGE_SCORES.json", "06_SUBMISSION.json",
                    "logs/prompts.jsonl", "logs/intervention-ledger.csv"):
            self.assertTrue(os.path.isfile(os.path.join(self.proj, rel)), rel)

    def test_prompt_log_is_project_local_append_only_and_rejects_secrets(self):
        self.valid_artifacts()
        source = os.path.join(self.tmp, "prompt.txt")
        with open(source, "w", encoding="utf-8") as handle:
            handle.write("review the selected problem")
        workflow.prompt_log(self.proj, "session-a", source, "human", "2026-01-01T00:00:00Z")
        path = os.path.join(self.proj, "logs", "prompts.jsonl")
        rows = [json.loads(line) for line in open(path, encoding="utf-8") if line.strip()]
        self.assertEqual("session-a", rows[-1]["session"])
        self.assertEqual("review the selected problem", rows[-1]["prompt"])
        self.assertRegex(rows[-1]["prompt_sha256"], r"^[0-9a-f]{64}$")
        self.assertEqual(0, Lint(self.ws, "final").run())
        with open(path, "w", encoding="utf-8") as handle:
            handle.write("")
        lint = Lint(self.ws, "final")
        self.assertEqual(1, lint.run())
        self.assertTrue(any("prompts.jsonl" in error and "rewritten" in error for error in lint.errors))
        with open(source, "w", encoding="utf-8") as handle:
            handle.write("OPENAI_API_KEY=sk-abcdefghijklmnopqrstuvwxyz123456")
        with self.assertRaisesRegex(SystemExit, "secret-like value"):
            workflow.prompt_log(self.proj, "session-b", source, "human", "2026-01-01T00:00:01Z")

    def test_portfolio_typed_artifacts_pass_and_candidate_evidence_reuse_fails(self):
        self.valid_artifacts()
        lint = Lint(self.ws, "final")
        self.assertEqual(0, lint.run(), lint.errors)
        path = os.path.join(self.proj, "03_PORTFOLIO.json")
        data = json.load(open(path, encoding="utf-8"))
        data["candidates"][1]["evidence"] = data["candidates"][0]["evidence"]
        self.write_json("03_PORTFOLIO.json", data)
        lint = Lint(self.ws, "final")
        self.assertEqual(1, lint.run())
        self.assertTrue(any("reuses candidate evidence" in error for error in lint.errors), lint.errors)

    def test_ai_practitioner_score_cannot_claim_actual_human_taste(self):
        self.valid_artifacts()
        path = os.path.join(self.proj, "06_JUDGE_SCORES.json")
        data = json.load(open(path, encoding="utf-8"))
        data["rounds"][0]["judge_type"] = "actual-human"
        self.write_json("06_JUDGE_SCORES.json", data)
        lint = Lint(self.ws, "final")
        self.assertEqual(1, lint.run())
        self.assertTrue(any("actual-human judge requires human evidence" in error for error in lint.errors), lint.errors)

    def test_preflight_blocker_and_unimplemented_promise_block_final(self):
        self.valid_artifacts()
        preflight = json.load(open(os.path.join(self.proj, "04_PREFLIGHT.json"), encoding="utf-8"))
        preflight["blockers"] = 1
        preflight["dependencies"][0]["status"] = "FAIL"
        self.write_json("04_PREFLIGHT.json", preflight)
        capabilities = json.load(open(os.path.join(self.proj, "06_CAPABILITIES.json"), encoding="utf-8"))
        capabilities["capabilities"][0]["status"] = "NOT_IMPLEMENTED"
        self.write_json("06_CAPABILITIES.json", capabilities)
        lint = Lint(self.ws, "final")
        self.assertEqual(1, lint.run())
        self.assertTrue(any("preflight blockers must be zero" in error for error in lint.errors), lint.errors)
        self.assertTrue(any("promise is not verified" in error for error in lint.errors), lint.errors)

    def test_v050_refuses_checkpoint_regression(self):
        self.valid_artifacts()
        lint = Lint(self.ws, "P0")
        self.assertEqual(1, lint.run())
        self.assertTrue(any("requested checkpoint P0 precedes current project state" in error for error in lint.errors), lint.errors)

    def test_target_lint_rejects_direct_secret_or_hash_forgery_in_prompt_log(self):
        self.valid_artifacts()
        path = os.path.join(self.proj, "logs", "prompts.jsonl")
        prompt = "API_KEY=sk-abcdefghijklmnopqrstuvwxyz123456"
        forged = {"schema": "ldl-prompt-log-v1", "timestamp": "2026-01-01T00:00:00Z",
                  "session": "bad/session", "actor": "root", "prompt_sha256": "0" * 64,
                  "prompt": prompt}
        with open(path, "a", encoding="utf-8") as handle:
            handle.write(json.dumps(forged) + "\n")
        lint = Lint(self.ws, "final")
        self.assertEqual(1, lint.run())
        self.assertTrue(any("content hash mismatch" in error for error in lint.errors), lint.errors)
        self.assertTrue(any("secret-like value" in error for error in lint.errors), lint.errors)
        self.assertTrue(any("actor invalid" in error for error in lint.errors), lint.errors)
        self.assertTrue(any("session invalid" in error for error in lint.errors), lint.errors)

    def test_artifact_handles_reject_normalization_escape(self):
        self.valid_artifacts()
        portfolio = json.load(open(os.path.join(self.proj, "03_PORTFOLIO.json"), encoding="utf-8"))
        portfolio["candidates"][0]["evidence"][0]["path"] = "raw/../raw/portfolio/source.txt"
        self.write_json("03_PORTFOLIO.json", portfolio)
        lint = Lint(self.ws, "final")
        self.assertEqual(1, lint.run())
        self.assertTrue(any("path/hash invalid" in error for error in lint.errors), lint.errors)

    def test_typed_artifacts_bind_contract_and_evaluator_hash(self):
        self.valid_artifacts()
        submission_path = os.path.join(self.proj, "06_SUBMISSION.json")
        submission = json.load(open(submission_path, encoding="utf-8"))
        submission["contract_version"] = "v2"
        self.write_json("06_SUBMISSION.json", submission)
        scores = json.load(open(os.path.join(self.proj, "06_JUDGE_SCORES.json"), encoding="utf-8"))
        scores["rounds"][0]["judge_sha256"] = "0" * 64
        self.write_json("06_JUDGE_SCORES.json", scores)
        lint = Lint(self.ws, "final")
        self.assertEqual(1, lint.run())
        self.assertTrue(any("contract version does not match" in error for error in lint.errors), lint.errors)
        self.assertTrue(any("forged evaluator profile hash" in error for error in lint.errors), lint.errors)

    def test_g1_freezes_evaluator_profile_from_maker_promotion(self):
        progress = os.path.join(self.proj, "PROGRESS.md")
        with open(progress, encoding="utf-8") as handle:
            text = handle.read()
        text = text.replace("| G1 | PENDING | v1 | human | | | |",
                            "| G1 | PASS | v1 | human | Daniel | 2026-01-01T00:00:00Z | frozen |")
        with open(progress, "w", encoding="utf-8") as handle:
            handle.write(text)
        scratch = os.path.join(self.tmp, "evaluator-attack")
        workflow.scratch_init(self.ws, scratch)
        rel = os.path.relpath(os.path.realpath(self.proj), os.path.realpath(self.ws))
        with open(os.path.join(scratch, rel, "02_EVALUATION.json"), "w", encoding="utf-8") as handle:
            json.dump({"hijacked": True}, handle)
        with self.assertRaisesRegex(SystemExit, "G1-frozen evaluator"):
            workflow.promote(scratch, self.ws, "P0")

    def test_v042_marker_cannot_launder_portfolio_profile(self):
        with open(os.path.join(self.ws, ".ldl-version"), "w", encoding="utf-8") as handle:
            handle.write("0.4.2\n")
        self.write_json("03_PORTFOLIO.json", {"invalid": True})
        lint = Lint(self.ws, "final")
        self.assertEqual(1, lint.run())
        self.assertTrue(any("portfolio-competition requires workspace schema 0.5.0" in error for error in lint.errors), lint.errors)

    def test_plain_text_cannot_become_actual_human_review(self):
        self.valid_artifacts()
        scores = json.load(open(os.path.join(self.proj, "06_JUDGE_SCORES.json"), encoding="utf-8"))
        probe = json.load(open(os.path.join(self.proj, "04_PREFLIGHT.json"), encoding="utf-8"))["dependencies"][0]["evidence"]
        scores["rounds"][1]["human_evidence"] = probe
        self.write_json("06_JUDGE_SCORES.json", scores)
        lint = Lint(self.ws, "final")
        self.assertEqual(1, lint.run())
        self.assertTrue(any("typed human review invalid" in error for error in lint.errors), lint.errors)

    def test_bool_zero_preflight_and_underpowered_fallback_fail(self):
        self.valid_artifacts()
        preflight = json.load(open(os.path.join(self.proj, "04_PREFLIGHT.json"), encoding="utf-8"))
        preflight["blockers"] = False
        self.write_json("04_PREFLIGHT.json", preflight)
        capabilities = json.load(open(os.path.join(self.proj, "06_CAPABILITIES.json"), encoding="utf-8"))
        capabilities["capabilities"][0]["status"] = "BOUNDED_FALLBACK"
        self.write_json("06_CAPABILITIES.json", capabilities)
        lint = Lint(self.ws, "final")
        self.assertEqual(1, lint.run())
        self.assertTrue(any("preflight blockers must be zero" in error for error in lint.errors), lint.errors)
        self.assertTrue(any("promise is not verified" in error for error in lint.errors), lint.errors)

    def test_judge_subject_hash_must_resolve_to_accepted_artifact(self):
        self.valid_artifacts()
        scores = json.load(open(os.path.join(self.proj, "06_JUDGE_SCORES.json"), encoding="utf-8"))
        for row in scores["rounds"]:
            row["artifact_sha256"] = "f" * 64
        self.write_json("06_JUDGE_SCORES.json", scores)
        lint = Lint(self.ws, "final")
        self.assertEqual(1, lint.run())
        self.assertTrue(any("not bound to an accepted artifact" in error for error in lint.errors), lint.errors)

    def test_non_object_typed_artifacts_fail_without_traceback(self):
        for rel in ("02_EVALUATION.json", "03_PORTFOLIO.json", "04_PREFLIGHT.json",
                    "06_CAPABILITIES.json", "06_JUDGE_SCORES.json", "06_SUBMISSION.json"):
            self.write_json(rel, [])
        lint = Lint(self.ws, "final")
        self.assertEqual(1, lint.run())
        self.assertEqual(6, sum("root must be an object" in error for error in lint.errors), lint.errors)

    def test_p3_cannot_publish_human_or_agent_final_verdicts(self):
        self.valid_artifacts()
        for rel, template in (("04_PREFLIGHT.json", "04_PREFLIGHT.json"),
                              ("06_CAPABILITIES.json", "06_CAPABILITIES.json"),
                              ("06_JUDGE_SCORES.json", "06_JUDGE_SCORES.json"),
                              ("06_SUBMISSION.json", "06_SUBMISSION.json")):
            self.write_json(rel, json.loads(scaffold.PORTFOLIO_FILES[template]))
        lint = Lint(self.ws, "P3")
        self.assertEqual(1, lint.run())
        self.assertTrue(any("premature Human taste verdict" in error for error in lint.errors), lint.errors)
        self.assertTrue(any("premature Agent operability verdict" in error for error in lint.errors), lint.errors)

    def test_explicit_v050_migration_requires_empty_v042_workspace(self):
        too_old = os.path.join(self.tmp, "too-old")
        scaffold.init(too_old)
        with open(os.path.join(too_old, ".ldl-version"), "w", encoding="utf-8") as handle:
            handle.write("0.4.1\n")
        with self.assertRaisesRegex(SystemExit, "requires a v0.4.2 workspace"):
            scaffold.init(too_old, migrate_v050=True)
        old = os.path.join(self.tmp, "old")
        scaffold.init(old)
        with open(os.path.join(old, ".ldl-version"), "w", encoding="utf-8") as handle:
            handle.write("0.4.2\n")
        scaffold.init(old, migrate_v050=True)
        self.assertEqual("0.5.0", open(os.path.join(old, ".ldl-version"), encoding="utf-8").read().strip())
        active = os.path.join(self.tmp, "active")
        scaffold.init(active)
        with open(os.path.join(active, ".ldl-version"), "w", encoding="utf-8") as handle:
            handle.write("0.4.2\n")
        scaffold.new_project(active, "existing", "2026-01-02")
        with self.assertRaisesRegex(SystemExit, "requires no active projects"):
            scaffold.init(active, migrate_v050=True)


if __name__ == "__main__":
    unittest.main()
