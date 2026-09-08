"""v0.7.0 final correction — counterexamples from independent review 2.

Three classes stayed open after the first correction round and are pinned here:

* the active control plane was decided by a fence toggle and one regex, so an
  HTML-commented ledger, a mismatched fence, a second appended ledger and a
  shadowed separator row all still launched a child (review 2, F1);
* output reservations were keyed by resolved path strings, so a case alias or a
  hard link to the same file let two live invocations claim one resource and
  each report the other's bytes as its own (review 2, F2);
* measurement accepted Infinity and a non-numeric cost amount, and turned a
  malformed telemetry row into a confident row of zeros (review 2, report
  blockers 1-2).

Harness-local: no model call, no network, no write outside a tempfile fixture.
"""
import json
import os
import subprocess
import sys
import unittest

from test_v070 import EXECUTION, ROOT, Workspace, utc  # noqa: F401

import execution  # noqa: E402
import workflow  # noqa: E402

GATE_HEADER = ("| Gate | Verdict | Contract version | Approval mode | Approver | "
               "Approved at | Evidence |")


# =====================================================================
# review 2 F1 — the parsed table must be the active one, every variant
# =====================================================================
class ActiveControlPlaneRegressionTests(Workspace):
    profile = "startup-reversible"

    def progress_path(self):
        return os.path.join(self.proj, "PROGRESS.md")

    def write_progress(self, text):
        with open(self.progress_path(), "w", encoding="utf-8") as handle:
            handle.write(text)

    def gate_table_span(self, text):
        start = text.index(GATE_HEADER)
        return start, text.index("\n\n", start)

    def wrap_gate_table(self, opener, closer, inner_prefix=""):
        text = self.read("PROGRESS.md")
        start, end = self.gate_table_span(text)
        self.write_progress(text[:start] + opener + "\n" + inner_prefix
                            + text[start:end] + "\n" + closer + text[end:])

    # -- the four reviewer probes -----------------------------------------
    def test_an_html_commented_ledger_is_not_the_control_plane(self):
        self.typed_pass("G1")
        text = self.read("PROGRESS.md")
        self.write_progress("<!--\n" + text + "\n-->\n")
        self.refused("Gate ledger", phase="P3")

    def test_a_tilde_line_cannot_close_a_backtick_fence(self):
        self.typed_pass("G1")
        self.wrap_gate_table("````", "````", inner_prefix="~~~\n")
        self.refused("Gate ledger", phase="P3")

    def test_a_second_appended_gate_ledger_is_refused(self):
        self.typed_pass("G1")
        text = self.read("PROGRESS.md")
        self.write_progress(text + "\n## Gate ledger\n\n" + GATE_HEADER
                            + "\n|---|---|---|---|---|---|---|\n"
                            + "| G1 | HOLD | v1 | human | | | |\n")
        self.refused("duplicate", phase="P3")

    def test_a_row_standing_in_for_the_separator_is_refused(self):
        self.typed_pass("G1")
        self.replace("PROGRESS.md", GATE_HEADER + "\n|---|---|---|---|---|---|---|",
                     GATE_HEADER + "\n| G1 | HOLD | v1 | human | | | |")
        self.refused("separator", phase="P3")

    # -- fence length / delimiter type / comment placement ----------------
    def test_a_three_backtick_fence_may_be_closed_by_four(self):
        self.typed_pass("G1")
        self.wrap_gate_table("```", "````")
        self.refused("Gate ledger", phase="P3")

    def test_a_four_backtick_fence_is_not_closed_by_three(self):
        self.typed_pass("G1")
        self.wrap_gate_table("````", "```")
        self.refused("Gate ledger", phase="P3")

    def test_a_tilde_fence_is_closed_by_tildes(self):
        self.typed_pass("G1")
        self.wrap_gate_table("~~~", "~~~")
        self.refused("Gate ledger", phase="P3")

    def test_a_comment_opener_inside_a_fence_does_not_mask_live_tables(self):
        self.typed_pass("G1")
        text = self.read("PROGRESS.md")
        self.write_progress("```\n<!-- an illustration, never closed\n```\n\n" + text)
        self.assertEqual(0, self.run_invoke(phase="P3"))

    def test_an_unclosed_comment_leaves_the_rest_inactive(self):
        self.typed_pass("G1")
        text = self.read("PROGRESS.md")
        self.write_progress("<!-- opened and never closed\n" + text)
        self.refused("Gate ledger", phase="P3")

    def test_a_closed_comment_before_the_ledger_keeps_it_live(self):
        self.typed_pass("G1")
        text = self.read("PROGRESS.md")
        self.write_progress("<!-- a note about the ledger below -->\n" + text)
        self.assertEqual(0, self.run_invoke(phase="P3"))

    def test_an_ordinary_scaffolded_workspace_still_launches(self):
        self.typed_pass("G1")
        self.assertEqual(0, self.run_invoke(phase="P3"))

    def test_a_fenced_example_beside_a_live_table_is_ignored_not_fatal(self):
        self.typed_pass("G1")
        text = self.read("PROGRESS.md")
        example = ("~~~markdown\n" + GATE_HEADER + "\n|---|---|---|---|---|---|---|\n"
                   "| G1 | HOLD | v1 | human | | | |\n~~~\n\n")
        self.write_progress(example + text)
        self.assertEqual(0, self.run_invoke(phase="P3"))

    def test_the_masker_keeps_every_byte_offset(self):
        text = "a\n```\nhidden\n```\n<!-- x -->\nb\n"
        masked = workflow.mask_inactive_regions(text)
        self.assertEqual(len(text), len(masked))
        self.assertNotIn("hidden", masked)
        self.assertNotIn("x", masked)
        self.assertIn("a", masked)
        self.assertIn("b", masked)


# =====================================================================
# review 2 F2 — a reserved output is a resource, not a spelling
# =====================================================================
class OutputAliasTests(Workspace):
    profile = "startup-reversible"

    def setUp(self):
        super().setUp()
        self.typed_pass("G1")
        self.out = os.path.join(self.proj, "05_engineering", "evidence")
        os.makedirs(self.out, exist_ok=True)

    def manifest(self, name, rel):
        path = os.path.join(self.tmp, name)
        with open(path, "w", encoding="utf-8") as handle:
            json.dump({"schema": "ldl-expected-output-v1", "job_id": "J-1",
                       "output_root": "05_engineering/evidence",
                       "outputs": [{"id": "a", "path": rel, "format": "text",
                                    "min_bytes": 1}]}, handle)
        return path

    def reserve_in_another_process(self, manifest, invocation_id):
        return subprocess.run(
            [sys.executable, "-c",
             "import sys;sys.path.insert(0,%r);import execution\n"
             "m=execution.load_expected(%r)\n"
             "try:\n execution.reserve_outputs(%r,%r,m);print('RESERVED')\n"
             "except execution.ManifestError as exc:print('REFUSED',exc)"
             % (os.path.join(ROOT, "tools"), manifest, self.proj, invocation_id)],
            text=True, capture_output=True)

    def test_a_case_alias_does_not_evade_a_live_reservation(self):
        shared = os.path.join(self.out, "shared.txt")
        with open(shared, "w", encoding="utf-8") as handle:
            handle.write("stale")
        if os.path.exists(os.path.join(self.out, "SHARED.txt")) is False:
            self.skipTest("case-insensitive alias not available on this filesystem")
        first = self.manifest("a.json", "shared.txt")
        second = self.manifest("b.json", "SHARED.txt")
        execution.reserve_outputs(self.proj, "INV-8001", execution.load_expected(first))
        probe = self.reserve_in_another_process(second, "INV-8002")
        self.assertIn("REFUSED", probe.stdout, probe.stderr)
        execution.release_outputs(self.proj, "INV-8001")
        self.assertEqual({}, execution.read_reservations(self.proj))

    def test_a_hard_link_alias_does_not_evade_a_live_reservation(self):
        shared = os.path.join(self.out, "shared.txt")
        with open(shared, "w", encoding="utf-8") as handle:
            handle.write("stale")
        os.link(shared, os.path.join(self.out, "alias.txt"))
        first = self.manifest("a.json", "shared.txt")
        second = self.manifest("b.json", "alias.txt")
        with self.assertRaises(execution.ManifestError) as caught:
            execution.reserve_outputs(self.proj, "INV-8003", execution.load_expected(first))
        self.assertIn("link", str(caught.exception))
        probe = self.reserve_in_another_process(second, "INV-8004")
        self.assertIn("REFUSED", probe.stdout, probe.stderr)
        self.assertEqual({}, execution.read_reservations(self.proj))

    def test_two_overlapping_runs_with_a_case_alias_do_not_both_pass(self):
        shared = os.path.join(self.out, "shared.txt")
        with open(shared, "w", encoding="utf-8") as handle:
            handle.write("stale")
        first = self.manifest("a.json", "shared.txt")
        second = self.manifest("b.json", "SHARED.txt")
        script = f"open({shared!r},'w').write('B wrote this')"
        code_a = self.run_invoke(phase="P3", command=[sys.executable, "-c", "pass"],
                                 expect=first)
        code_b = self.run_invoke(phase="P3", command=[sys.executable, "-c", script],
                                 expect=second)
        self.assertNotEqual((0, 0), (code_a, code_b))

    def test_distinct_outputs_still_run_and_release(self):
        first = self.manifest("a.json", "one.txt")
        script = f"open({os.path.join(self.out, 'one.txt')!r},'w').write('ok')"
        self.assertEqual(0, self.run_invoke(phase="P3", command=[sys.executable, "-c", script],
                                            expect=first))
        self.assertEqual({}, execution.read_reservations(self.proj))


# =====================================================================
# review 2 report blockers 1-2 — a number is finite or it is not a number
# =====================================================================
class MeasurementFiniteTests(Workspace):
    profile = "startup-reversible"

    def setUp(self):
        super().setUp()
        self.typed_pass("G1")

    def record(self):
        return execution.collect_measurement(self.proj, deliverable="d")

    def cost_ledger(self, text):
        with open(os.path.join(self.proj, "logs", "cost-ledger.csv"), "w",
                  encoding="utf-8") as handle:
            handle.write(text)

    def test_infinite_human_minutes_are_refused(self):
        record = self.record()
        record["product_fit"]["human_minutes"] = float("inf")
        with self.assertRaises(execution.ManifestError) as caught:
            execution.validate_measurement(record)
        self.assertIn("human_minutes", str(caught.exception))

    def test_infinite_baseline_value_is_refused(self):
        record = self.record()
        record["baseline"] = {"status": "MEASURED", "window": "2026-08", "unit": "minutes",
                              "value": float("inf"), "source": "logs/runner-ledger.csv"}
        with self.assertRaises(execution.ManifestError) as caught:
            execution.validate_measurement(record)
        self.assertIn("baseline", str(caught.exception))

    def test_a_non_numeric_cost_amount_is_refused(self):
        record = self.record()
        record["cost"] = {"billing": "api", "amount": "free??", "currency": None,
                          "source": None, "note": "n"}
        with self.assertRaises(execution.ManifestError) as caught:
            execution.validate_measurement(record)
        self.assertIn("amount", str(caught.exception))

    def test_a_metered_amount_needs_a_currency_and_a_source(self):
        record = self.record()
        record["cost"] = {"billing": "api", "amount": 1.5, "currency": None,
                          "source": None, "note": "n"}
        with self.assertRaises(execution.ManifestError):
            execution.validate_measurement(record)
        record["cost"] = {"billing": "api", "amount": 1.5, "currency": "USD",
                          "source": "provider console", "note": "n"}
        execution.validate_measurement(record)

    def test_a_negative_cost_amount_is_refused(self):
        record = self.record()
        record["cost"] = {"billing": "api", "amount": -1, "currency": "USD",
                          "source": "console", "note": "n"}
        with self.assertRaises(execution.ManifestError):
            execution.validate_measurement(record)

    def test_unknown_billing_keeps_the_amount_null(self):
        record = self.record()
        self.assertIsNone(record["cost"]["amount"])
        self.assertEqual("unknown", record["cost"]["billing"])
        execution.validate_measurement(record)

    def test_a_malformed_cost_row_does_not_become_zero(self):
        self.cost_ledger("llm_calls,input_tokens,output_tokens,checker_runs\nbogus,,,\n")
        record = self.record()["technical"]
        for field in ("llm_calls", "input_tokens", "output_tokens", "checker_runs"):
            self.assertIsNone(record[field], field)
        self.assertEqual("PARTIAL", record["cost_source"])

    def test_a_mixed_ledger_keeps_valid_columns_and_nulls_the_broken_one(self):
        self.cost_ledger("llm_calls,input_tokens,output_tokens,checker_runs\n"
                         "2,10,10,1\n3,oops,20,1\n")
        record = self.record()["technical"]
        self.assertEqual(5, record["llm_calls"])
        self.assertIsNone(record["input_tokens"])
        self.assertEqual(30, record["output_tokens"])
        self.assertEqual("PARTIAL", record["cost_source"])

    def test_an_observed_zero_is_still_reported_as_zero(self):
        self.cost_ledger("llm_calls,input_tokens,output_tokens,checker_runs\n0,0,0,0\n")
        record = self.record()["technical"]
        self.assertEqual(0, record["llm_calls"])
        self.assertEqual("logs/cost-ledger.csv", record["cost_source"])

    def test_a_negative_count_in_the_ledger_is_not_a_measurement(self):
        self.cost_ledger("llm_calls,input_tokens,output_tokens,checker_runs\n-4,1,1,1\n")
        record = self.record()["technical"]
        self.assertIsNone(record["llm_calls"])
        self.assertEqual(1, record["input_tokens"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
