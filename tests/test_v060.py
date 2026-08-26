"""v0.6.0 — the evaluative layer must be enforced, not merely declared.

Every scenario here passed lint under v0.5.0. Each one is a way for the maker
to grade its own work: an unfrozen evaluator, an empty check, a self-set bar,
a self-reported number, or a judge wearing the maker's name.
"""
import hashlib
import json
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tools"))

from lint import Lint  # noqa: E402
from tests.test_v050 import V050Tests  # noqa: E402


class V060Tests(V050Tests):
    def load(self, rel):
        return json.load(open(os.path.join(self.proj, rel), encoding="utf-8"))

    def rehash_evaluator(self):
        path = os.path.join(self.proj, "02_EVALUATION.json")
        digest = hashlib.sha256(open(path, "rb").read()).hexdigest()
        judge = self.load("06_JUDGE_SCORES.json")
        for row in judge["rounds"]:
            row["judge_sha256"] = digest
        self.write_json("06_JUDGE_SCORES.json", judge)

    def fails_with(self, fragment, through="final"):
        lint = Lint(self.ws, through)
        self.assertEqual(1, lint.run(), "expected FAIL but lint passed")
        self.assertTrue(any(fragment in error for error in lint.errors),
                        f"{fragment!r} not in {lint.errors}")

    def test_reference_fixture_still_passes(self):
        self.valid_artifacts()
        lint = Lint(self.ws, "final")
        self.assertEqual(0, lint.run(), lint.errors)

    # ---- 1. the gate the freeze depends on ----
    def test_final_requires_g1_pass_so_the_evaluator_freeze_can_engage(self):
        self.valid_artifacts()
        path = os.path.join(self.proj, "PROGRESS.md")
        text = open(path, encoding="utf-8").read().replace(
            "| G1 | PASS | v1 | human | Daniel | 2026-01-01T00:00:00Z | [approval](raw/approval-g1.md) |",
            "| G1 | PENDING | v1 | human | | | |")
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(text)
        self.fails_with("submission requires G1 PASS")

    # ---- 2. an empty check is not a passed check ----
    def test_empty_collections_are_not_satisfied_checks(self):
        cases = [
            ("04_PREFLIGHT.json", lambda d: d.update(dependencies=[]), "preflight declares no dependency"),
            ("06_SUBMISSION.json", lambda d: (d.update(required_files=[]), d.update(included_files=[])),
             "submission declares no required file"),
            ("02_EVALUATION.json", lambda d: d.update(submission_grammar=[]), "submission grammar is empty"),
        ]
        for rel, mutate, fragment in cases:
            with self.subTest(rel=rel, fragment=fragment):
                self.setUp()
                self.valid_artifacts()
                data = self.load(rel)
                mutate(data)
                self.write_json(rel, data)
                if rel == "02_EVALUATION.json":
                    self.rehash_evaluator()
                self.fails_with(fragment)

    def test_evaluator_blind_to_nothing_is_not_a_blind_evaluator(self):
        for field, fragment in (("blind_inputs", "evaluator blind inputs are empty"),
                                ("cannot_judge", "evaluator declares nothing it cannot judge"),
                                ("disqualification_rules", "evaluator has no disqualification rule"),
                                ("journey", "evaluator has no journey")):
            with self.subTest(field=field):
                self.setUp()
                self.valid_artifacts()
                data = self.load("02_EVALUATION.json")
                for evaluator in data["evaluators"]:
                    evaluator[field] = []
                self.write_json("02_EVALUATION.json", data)
                self.rehash_evaluator()
                self.fails_with(fragment)

    # ---- 3. the composed false-green ----
    def test_composed_false_green_cannot_pass(self):
        self.valid_artifacts()
        env = self.load("02_EVALUATION.json")
        for evaluator in env["evaluators"]:
            evaluator["blind_inputs"] = []
            evaluator["cannot_judge"] = []
            evaluator["disqualification_rules"] = []
            evaluator["rubric"] = [{"id": "X", "weight": 100, "criterion": "the maker says it is good"}]
        env["submission_grammar"] = []
        self.write_json("02_EVALUATION.json", env)
        self.rehash_evaluator()
        preflight = self.load("04_PREFLIGHT.json")
        preflight["dependencies"] = []
        self.write_json("04_PREFLIGHT.json", preflight)
        capabilities = self.load("06_CAPABILITIES.json")
        capabilities["capabilities"][0].update(
            promise="real-time translation into 40 languages, live in production",
            required_level="NOT_IMPLEMENTED", status="NOT_IMPLEMENTED", live_evidence=None)
        self.write_json("06_CAPABILITIES.json", capabilities)
        submission = self.load("06_SUBMISSION.json")
        submission["required_files"] = []
        submission["included_files"] = []
        self.write_json("06_SUBMISSION.json", submission)
        lint = Lint(self.ws, "final")
        self.assertEqual(1, lint.run())
        self.assertGreaterEqual(len(lint.errors), 4, lint.errors)

    # ---- 4. the maker does not set its own bar ----
    def test_maker_cannot_set_its_own_required_level(self):
        self.valid_artifacts()
        capabilities = self.load("06_CAPABILITIES.json")
        capabilities["capabilities"][0].update(
            promise="real-time translation into 40 languages for every viewer",
            required_level="NOT_IMPLEMENTED", status="NOT_IMPLEMENTED", live_evidence=None)
        self.write_json("06_CAPABILITIES.json", capabilities)
        self.fails_with("capability required level below CAPTURED_REAL")

    def test_capability_must_cite_a_real_requirement(self):
        self.valid_artifacts()
        capabilities = self.load("06_CAPABILITIES.json")
        capabilities["capabilities"][0]["requirement_id"] = "R-99"
        self.write_json("06_CAPABILITIES.json", capabilities)
        self.fails_with("capability requirement ID not in the requirements ledger")

    # ---- 5. numbers come from execution output ----
    def test_preflight_check_count_must_be_supported_by_its_evidence(self):
        self.valid_artifacts()
        preflight = self.load("04_PREFLIGHT.json")
        preflight["dependencies"][0]["checks"] = 999999
        self.write_json("04_PREFLIGHT.json", preflight)
        self.fails_with("dependency check count exceeds its evidence")

    def test_preflight_exit_code_must_appear_in_its_evidence(self):
        self.valid_artifacts()
        preflight = self.load("04_PREFLIGHT.json")
        preflight["dependencies"][0]["exit_code"] = 7
        preflight["dependencies"][0]["expected_exit_code"] = 7
        self.write_json("04_PREFLIGHT.json", preflight)
        self.fails_with("dependency exit code is not recorded in its evidence")

    def test_judge_score_must_appear_in_its_evidence(self):
        self.valid_artifacts()
        judge = self.load("06_JUDGE_SCORES.json")
        for row in judge["rounds"]:
            row["score"] = 100
        self.write_json("06_JUDGE_SCORES.json", judge)
        self.fails_with("judge score is not recorded in its evidence")

    # ---- 6. separation is an identity, not a forbidden word ----
    def test_maker_shaped_runner_ids_are_refused(self):
        for name in ("maker-agent", "MAKER ", "the-maker"):
            with self.subTest(name=name):
                self.setUp()
                self.valid_artifacts()
                preflight = self.load("04_PREFLIGHT.json")
                preflight["dependencies"][0]["runner_id"] = name
                self.write_json("04_PREFLIGHT.json", preflight)
                self.fails_with("dependency runner is the maker")

    def test_human_review_approver_must_match_the_gate_approver(self):
        self.valid_artifacts()
        path = os.path.join(self.proj, "raw", "human-review.json")
        review = json.load(open(path, encoding="utf-8"))
        review["approver"] = "maker-agent"
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(review, handle, ensure_ascii=False, indent=2)
        digest = hashlib.sha256(open(path, "rb").read()).hexdigest()
        judge = self.load("06_JUDGE_SCORES.json")
        for row in judge["rounds"]:
            if row.get("judge_type") == "actual-human":
                row["human_evidence"] = {"path": "raw/human-review.json", "sha256": digest}
        self.write_json("06_JUDGE_SCORES.json", judge)
        self.fails_with("human review approver does not match the G1 approver")

    # ---- 7. a verdict for every input (the v0.2.4 ratchet, restored) ----
    def test_nested_type_confusion_yields_a_verdict_not_a_traceback(self):
        cases = [("02_EVALUATION.json", "iteration_limits"), ("02_EVALUATION.json", "evaluators"),
                 ("04_PREFLIGHT.json", "dependencies"), ("06_CAPABILITIES.json", "capabilities"),
                 ("06_JUDGE_SCORES.json", "rounds"), ("06_SUBMISSION.json", "required_files")]
        for rel, key in cases:
            with self.subTest(rel=rel, key=key):
                self.setUp()
                self.valid_artifacts()
                data = self.load(rel)
                data[key] = 4
                self.write_json(rel, data)
                lint = Lint(self.ws, "final")
                self.assertEqual(1, lint.run())
                self.assertTrue(any("L13" in error for error in lint.errors), lint.errors)


if __name__ == "__main__":
    unittest.main(verbosity=1)
