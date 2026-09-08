"""v0.6.1 — the harness must gate what the maker executes, not only what it writes.

Both 2026-08-26 field runs died outside the write path: an orchestrator invoked
runners behind a pending gate, and batch after-the-fact ledgering lost the
started/completed distinction the moment a run was interrupted. Every scenario
here is harness-local — no model call is ever made.
"""
import csv
import hashlib
import json
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tools"))

from lint import Lint  # noqa: E402
import invoke  # noqa: E402
import scaffold  # noqa: E402
import workflow  # noqa: E402
from tests.test_v060 import V060Tests  # noqa: E402

INVOKE = os.path.join(ROOT, "tools", "invoke.py")


class InvokeTests(unittest.TestCase):
    """The runner-invocation wrapper: gate enforcement and split ledgering."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="ldl-v061-")
        self.ws = os.path.join(self.tmp, "ws")
        scaffold.init(self.ws)
        self.proj = scaffold.new_project(self.ws, "gated", "2026-01-01")
        self.ledger = os.path.join(self.proj, "logs", "runner-ledger.csv")
        self.sentinel = os.path.join(self.tmp, "sentinel.txt")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    # -- fixture helpers --------------------------------------------------
    def replace(self, rel, old, new):
        path = os.path.join(self.proj, rel)
        text = open(path, encoding="utf-8").read()
        assert old in text, f"fixture drift: {old!r} not in {rel}"
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(text.replace(old, new))

    def typed_pass(self, gate="G1"):
        """Pass a gate through the real typed-decision path (gate-apply)."""
        if gate == "G1":
            self.replace("PROGRESS.md", "| P0 contract | pending | |", "| P0 contract | done | 2026-01-01 |")
        contract = os.path.join(self.proj, "00_CONTRACT.md")
        digest = hashlib.sha256(open(contract, "rb").read()).hexdigest()
        decision = {
            "schema": "ldl-gate-decision-v1",
            "gate": gate,
            "contract_version": "v1",
            "verdict": "PASS",
            "approval_mode": "human",
            "approver": "Daniel",
            "decided_at": "2026-01-01T00:00:00Z",
            "reason": "criteria are met",
            "evidence": [{"path": "00_CONTRACT.md", "sha256": digest}],
        }
        path = os.path.join(self.tmp, f"decision-{gate.lower()}.json")
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(decision, handle)
        workflow.gate_apply(self.proj, path)

    def dummy_command(self):
        return [sys.executable, "-c",
                f"open({self.sentinel!r}, 'w').write('ok')"]

    def run_invoke(self, phase="P3", runner_id="steve", command=None):
        return invoke.run(self.proj, phase, runner_id, "S-1", command or self.dummy_command())

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
        with self.assertRaises(SystemExit) as caught:
            self.run_invoke(**kwargs)
        self.assertIn(fragment, str(caught.exception))
        self.assertFalse(os.path.exists(self.sentinel), "refused invocation still launched the command")
        self.assertEqual((0, 0, 0), self.counts(), "refused invocation touched the ledger")

    # -- 1. a pending gate is a closed gate -------------------------------
    def test_g1_pending_blocks_runner_without_launching(self):
        self.refused("G1")

    def test_p4_requires_g2_even_after_g1(self):
        """Kept from v0.6.1, retargeted at the profile it was always describing.

        v0.6.1 applied `P4 needs G2` to every project. From v0.7.0 that rule
        belongs to gated-high-risk (and portfolio-competition), where losing it
        would be the actual safety regression; startup-reversible reaches P4
        under G1 plus its launch documents. The assertion itself is unchanged.
        """
        proj = scaffold.new_project(self.ws, "high-risk", "2026-01-02", "gated-high-risk")
        self.proj, self.ledger = proj, os.path.join(proj, "logs", "runner-ledger.csv")
        self.typed_pass("G1")
        self.refused("G2", phase="P4")

    def test_p0_needs_no_predecessor_gate(self):
        rc = self.run_invoke(phase="P0")
        self.assertEqual(0, rc)
        self.assertTrue(os.path.exists(self.sentinel))

    # -- 2. PASS must carry typed evidence --------------------------------
    def test_textual_pass_without_typed_evidence_is_refused(self):
        # v0.7.0 also revalidates the phases a gate owns, and that check speaks
        # first; complete P0 so the refusal is the typed-evidence one under test.
        self.replace("PROGRESS.md", "| P0 contract | pending | |", "| P0 contract | done | 2026-01-01 |")
        self.replace(
            "PROGRESS.md",
            "| G1 | PENDING | v1 | human | | | |",
            "| G1 | PASS | v1 | human | Daniel | 2026-01-01T00:00:00Z | [approval](raw/approval.md) |")
        os.makedirs(os.path.join(self.proj, "raw"), exist_ok=True)
        with open(os.path.join(self.proj, "raw", "approval.md"), "w", encoding="utf-8") as handle:
            handle.write("looks good\n")
        self.refused("typed evidence")

    def test_tampered_evidence_is_refused(self):
        self.typed_pass("G1")
        with open(os.path.join(self.proj, "00_CONTRACT.md"), "a", encoding="utf-8") as handle:
            handle.write("\nedited after the gate passed\n")
        self.refused("G1")

    # -- 3. separation is an identity ------------------------------------
    def test_maker_shaped_runner_id_is_refused(self):
        self.typed_pass("G1")
        self.refused("maker", runner_id="maker-agent")

    # -- 4. G1 PASS permits exactly one harmless dummy invocation ---------
    def test_g1_pass_permits_dummy_invocation_with_split_ledger(self):
        self.typed_pass("G1")
        rc = self.run_invoke()
        self.assertEqual(0, rc)
        self.assertTrue(os.path.exists(self.sentinel))
        self.assertEqual((1, 1, 0), self.counts())
        started, completed = self.ledger_events()
        self.assertEqual("STARTED", started["event"])
        self.assertEqual("", started["exit_code"], "STARTED must be written before the outcome is known")
        self.assertEqual("COMPLETED", completed["event"])
        self.assertEqual("0", completed["exit_code"])
        self.assertEqual(started["invocation_id"], completed["invocation_id"])

    def test_nonzero_exit_is_completed_not_aborted(self):
        self.typed_pass("G1")
        rc = self.run_invoke(command=[sys.executable, "-c", "raise SystemExit(7)"])
        self.assertEqual(7, rc)
        self.assertEqual((1, 1, 0), self.counts())
        self.assertEqual("7", self.ledger_events()[1]["exit_code"])

    # -- 5. interruption leaves STARTED without COMPLETED -----------------
    def test_interrupted_invocation_leaves_started_aborted_mismatch(self):
        self.typed_pass("G1")
        process = subprocess.Popen(
            [sys.executable, INVOKE, "run", self.proj, "--phase", "P3",
             "--runner-id", "steve", "--session", "S-1", "--",
             sys.executable, "-c", "import time; time.sleep(60)"],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline:
            if self.counts()[0] == 1:
                break
            time.sleep(0.05)
        self.assertEqual(1, self.counts()[0], "STARTED row never appeared")
        process.send_signal(signal.SIGTERM)
        process.wait(timeout=20)
        self.assertEqual((1, 0, 1), self.counts())


class MigrationTests(unittest.TestCase):
    """v0.6.1 changes no project file schema, so — unlike every earlier
    migration — sealed or active projects may stay in place: the harness fix
    must be installable under the failed runs it exists to prevent."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="ldl-v061-migrate-")
        self.ws = os.path.join(self.tmp, "ws")
        scaffold.init(self.ws)
        scaffold.new_project(self.ws, "sealed", "2026-01-01")
        with open(os.path.join(self.ws, ".ldl-version"), "w", encoding="utf-8") as handle:
            handle.write("0.6.0\n")
        os.remove(os.path.join(self.ws, "tools", "invoke.py"))

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def marker(self):
        return open(os.path.join(self.ws, ".ldl-version"), encoding="utf-8").read().strip()

    def test_explicit_migration_upgrades_with_projects_in_place(self):
        scaffold.init(self.ws, migrate_v061=True)
        self.assertEqual("0.6.1", self.marker())
        self.assertTrue(os.path.isfile(os.path.join(self.ws, "tools", "invoke.py")))

    def test_without_the_flag_a_v060_workspace_stays_v060(self):
        scaffold.init(self.ws)
        self.assertEqual("0.6.0", self.marker())
        self.assertFalse(os.path.isfile(os.path.join(self.ws, "tools", "invoke.py")))

    def test_migration_requires_a_v060_workspace(self):
        with open(os.path.join(self.ws, ".ldl-version"), "w", encoding="utf-8") as handle:
            handle.write("0.5.0\n")
        with self.assertRaises(SystemExit) as caught:
            scaffold.init(self.ws, migrate_v061=True)
        self.assertIn("v0.6.0 workspace", str(caught.exception))


class V061LedgerLintTests(V060Tests):
    """The runner ledger is append-only and schema-checked like every other log."""

    def ledger_path(self):
        return os.path.join(self.proj, "logs", "runner-ledger.csv")

    def write_ledger(self, text):
        with open(self.ledger_path(), "w", encoding="utf-8") as handle:
            handle.write(text)

    def test_runner_ledger_rewrite_is_caught(self):
        self.valid_artifacts()
        self.write_ledger(
            "timestamp,event,invocation_id,phase,runner_id,session,exit_code,wall_seconds\n"
            "2026-01-01T00:00:00Z,STARTED,INV-0001,P3,steve,S-1,,\n")
        self.assertEqual(0, Lint(self.ws, "final").run())
        self.write_ledger(
            "timestamp,event,invocation_id,phase,runner_id,session,exit_code,wall_seconds\n")
        self.fails_with("log rewritten")

    def test_runner_ledger_invalid_event_is_caught(self):
        self.valid_artifacts()
        self.write_ledger(
            "timestamp,event,invocation_id,phase,runner_id,session,exit_code,wall_seconds\n"
            "2026-01-01T00:00:00Z,FINISHED,INV-0001,P3,steve,S-1,0,1.0\n")
        self.fails_with("runner ledger")

    def test_runner_ledger_completion_needs_a_started_row(self):
        self.valid_artifacts()
        self.write_ledger(
            "timestamp,event,invocation_id,phase,runner_id,session,exit_code,wall_seconds\n"
            "2026-01-01T00:00:00Z,COMPLETED,INV-0001,P3,steve,S-1,0,1.0\n")
        self.fails_with("runner ledger")


if __name__ == "__main__":
    unittest.main(verbosity=1)
