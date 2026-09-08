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


# =====================================================================
# CI fix - a signal after the STARTED row must still leave a terminal row
# (GitHub run 34282452224, Ubuntu / Python 3.11, test_v061)
# =====================================================================
class InterruptDuringSetupRegressionTests(Workspace):
    """The v0.6.1 interruption test was not wrong, it was a race.

    tools/invoke.py installed its SIGTERM/SIGINT handlers only after the
    reservation, the output claim and the job binding, so a signal arriving
    once the STARTED row was already on disk - exactly the window the v0.6.1
    test polls for - was taken by the default handler and killed the wrapper
    with a STARTED row and no terminal row. Python 3.9 won that race often
    enough to stay green; 3.11 lost it in CI.

    These probes deliver a real signal at a fixed point inside the setup
    window instead of polling for it, so the window is exercised on every run.
    The wrapper runs in its own subprocess: the signal goes to the driver, not
    to the test process.
    """

    DRIVER = '''import os
import signal
import sys

sys.path.insert(0, {root!r})
sys.path.insert(0, os.path.join({root!r}, "tools"))
import execution
import invoke

_real = getattr(execution, {target!r})


def _patched(*args, **kwargs):
    result = _real(*args, **kwargs)
    # A real signal at a fixed point: the ledger write has already happened and
    # the wrapper has not been handed the invocation id back yet.
    os.kill(os.getpid(), signal.{signame})
    return result


setattr(execution, {target!r}, _patched)
sys.exit(invoke.run({proj!r}, "P3", "steve", "S-1", {command!r}, expect={expect!r}))
'''

    def interrupt_after(self, target, signame="SIGTERM", expect=None):
        """Run the wrapper in a subprocess and signal it inside `target`."""
        path = os.path.join(self.tmp, "driver.py")
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(self.DRIVER.format(root=ROOT, target=target, signame=signame,
                                            proj=self.proj, command=self.dummy_command(),
                                            expect=expect))
        return subprocess.run([sys.executable, path], capture_output=True, text=True, timeout=60)

    def assert_aborted_without_running(self, result):
        self.assertEqual(130, result.returncode,
                         f"wrapper did not survive the signal: {result.stdout}{result.stderr}")
        self.assertIn("INVOKE ABORTED", result.stdout)
        self.assertEqual((1, 0, 1), self.counts())
        started, aborted = self.ledger_events()
        self.assertEqual("STARTED", started["event"])
        self.assertEqual("ABORTED", aborted["event"])
        self.assertEqual(started["invocation_id"], aborted["invocation_id"])
        self.assertFalse(os.path.exists(self.sentinel),
                         "an invocation interrupted before launch still ran the command")

    def test_sigterm_inside_the_reservation_still_writes_aborted(self):
        self.typed_pass("G1")
        self.assert_aborted_without_running(self.interrupt_after("reserve_and_start"))

    def test_sigint_inside_the_reservation_still_writes_aborted(self):
        self.typed_pass("G1")
        self.assert_aborted_without_running(
            self.interrupt_after("reserve_and_start", signame="SIGINT"))

    def test_sigterm_inside_the_output_claim_releases_the_reservation(self):
        self.typed_pass("G1")
        manifest = os.path.join(self.tmp, "expected-output.json")
        with open(manifest, "w", encoding="utf-8") as handle:
            json.dump({"schema": "ldl-expected-output-v1", "job_id": "JOB-1",
                       "output_root": "05_engineering/evidence/increments",
                       "outputs": [{"id": "OUT-01", "path": "a.md", "format": "markdown",
                                    "min_bytes": 1}]}, handle)
        self.assert_aborted_without_running(
            self.interrupt_after("reserve_outputs", expect=manifest))
        self.assertEqual({}, execution.read_reservations(self.proj),
                         "an interrupted setup left an orphan output claim behind")

    DOUBLE_DRIVER = '''import os
import signal
import sys

sys.path.insert(0, {root!r})
sys.path.insert(0, os.path.join({root!r}, "tools"))
import invoke

_popen = invoke.subprocess.Popen
_terminate = invoke._terminate
_children = []


def popen(*args, **kwargs):
    child = _popen(*args, **kwargs)
    _children.append(child)
    # Recorded while Popen had not returned yet: the wrapper acts on it after.
    os.kill(os.getpid(), signal.SIGTERM)
    return child


def terminate(child):
    _terminate(child)
    # The second signal, delivered inside teardown, must be recorded and never
    # raised - the terminal row is worth more than a prompt exit.
    os.kill(os.getpid(), signal.SIGINT)


invoke.subprocess.Popen = popen
invoke._terminate = terminate
try:
    code = invoke.run({proj!r}, "P3", "steve", "S-1",
                      [sys.executable, "-c", "import time; time.sleep(60)"],
                      expect={expect!r})
finally:
    for child in _children:
        if child.poll() is None:
            _terminate(child)
    print("CHILD-RETURNCODES " + repr([child.returncode for child in _children]))
sys.exit(code)
'''

    def expect_manifest(self):
        path = os.path.join(self.tmp, "expected-output.json")
        with open(path, "w", encoding="utf-8") as handle:
            json.dump({"schema": "ldl-expected-output-v1", "job_id": "JOB-1",
                       "output_root": "05_engineering/evidence/increments",
                       "outputs": [{"id": "OUT-01", "path": "a.md", "format": "markdown",
                                    "min_bytes": 1}]}, handle)
        return path

    def test_a_second_signal_during_teardown_cannot_lose_the_terminal_row(self):
        """Independent review of the first CI fix, reproduced probe.

        A SIGTERM recorded while Popen had not returned was acted on by an
        explicit raise that left the guard armed, so a SIGINT arriving during
        `_terminate` escaped the abort handler: ledger (1, 0, 0) and the output
        claim still held. Both signals are real and both are delivered at fixed
        points, so this covers the repeat-signal path on every run.
        """
        self.typed_pass("G1")
        path = os.path.join(self.tmp, "double-driver.py")
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(self.DOUBLE_DRIVER.format(root=ROOT, proj=self.proj,
                                                   expect=self.expect_manifest()))
        result = subprocess.run([sys.executable, path], capture_output=True, text=True,
                                timeout=120)
        self.assertEqual(130, result.returncode,
                         f"teardown signal escaped the abort path: {result.stdout}{result.stderr}")
        self.assertIn("INVOKE ABORTED", result.stdout)
        self.assertEqual((1, 0, 1), self.counts())
        started, aborted = self.ledger_events()
        self.assertEqual(started["invocation_id"], aborted["invocation_id"])
        self.assertEqual({}, execution.read_reservations(self.proj),
                         "a repeated signal left an orphan output claim behind")
        self.assertNotIn("CHILD-RETURNCODES [None]", result.stdout,
                         "the child was still running when the wrapper aborted")

if __name__ == "__main__":
    unittest.main(verbosity=2)
