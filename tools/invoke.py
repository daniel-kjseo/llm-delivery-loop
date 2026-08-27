#!/usr/bin/env python3
"""LDL v0.6.1 runner-invocation wrapper (stdlib only).

Commands:
  invoke.py run PROJECT --phase P0..P6 --runner-id ID --session SESSION -- COMMAND [ARG...]

The wrapper is the only sanctioned way to launch a runner. It refuses the
launch unless the phase's predecessor gate is PASS with typed evidence, and it
ledgers STARTED before the process exists and COMPLETED/ABORTED after it exits,
so a started/completed mismatch survives any interruption as evidence.
"""
import argparse
import csv
import json
import os
import re
import signal
import subprocess
import sys
import time
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import workflow  # noqa: E402

LEDGER_REL = os.path.join("logs", "runner-ledger.csv")
LEDGER_COLUMNS = ["timestamp", "event", "invocation_id", "phase", "runner_id", "session", "exit_code", "wall_seconds"]
PREDECESSOR_GATE = {"P0": None, "P1": "G1", "P2": "G1", "P3": "G1", "P4": "G2", "P5": "G3", "P6": "G3"}
IDENT = re.compile(r"[A-Za-z0-9._-]{1,64}")


def refuse(reason):
    raise SystemExit(f"INVOKE REFUSED - {reason}")


def utcnow():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def gate_check(project, phase):
    gate = PREDECESSOR_GATE[phase]
    if gate is None:
        return
    progress_path = os.path.join(project, "PROGRESS.md")
    if not os.path.isfile(progress_path):
        refuse(f"gate ledger missing: {progress_path}")
    with open(progress_path, encoding="utf-8") as handle:
        progress = handle.read()
    _, rows = workflow.markdown_table(progress, "Gate ledger", workflow.GATE_COLUMNS)
    row = next((item for item in rows if item["Gate"] == gate), None)
    if row is None:
        refuse(f"predecessor gate {gate} has no ledger row")
    if row["Verdict"] != "PASS":
        refuse(f"predecessor gate {gate} is {row['Verdict'] or 'PENDING'}, not PASS")
    link = re.search(r"\]\(([^)]+)\)", row["Evidence"])
    rel = link.group(1) if link else ""
    decisions_root = os.path.realpath(os.path.join(project, "raw", "gate-decisions"))
    try:
        decision_path = workflow.project_file(project, rel)
    except ValueError:
        decision_path = ""
    if (not rel.endswith(".json") or not decision_path
            or os.path.commonpath([decisions_root, decision_path]) != decisions_root):
        refuse(f"predecessor gate {gate} PASS lacks typed evidence under raw/gate-decisions/")
    try:
        with open(decision_path, encoding="utf-8") as handle:
            decision = json.load(handle)
        workflow.validate_gate_decision(project, decision)
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        refuse(f"predecessor gate {gate} typed evidence invalid: {exc}")
    for field, expected in (("gate", gate), ("verdict", "PASS"),
                            ("contract_version", row["Contract version"]),
                            ("approver", row["Approver"])):
        if decision.get(field) != expected:
            refuse(f"predecessor gate {gate} typed evidence mismatch: {field}")


def append_event(project, event, invocation_id, phase, runner_id, session, exit_code="", wall_seconds=""):
    path = os.path.join(project, LEDGER_REL)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    fresh = not os.path.isfile(path)
    with open(path, "a", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        if fresh:
            writer.writerow(LEDGER_COLUMNS)
        writer.writerow([utcnow(), event, invocation_id, phase, runner_id, session,
                         exit_code, wall_seconds])
        handle.flush()
        os.fsync(handle.fileno())


def next_invocation_id(project):
    path = os.path.join(project, LEDGER_REL)
    started = 0
    if os.path.isfile(path):
        with open(path, encoding="utf-8") as handle:
            started = sum(1 for row in csv.DictReader(handle) if row.get("event") == "STARTED")
    return f"INV-{started + 1:04d}"


def run(project, phase, runner_id, session, command):
    project = os.path.realpath(project)
    if phase not in PREDECESSOR_GATE:
        refuse(f"unknown phase: {phase}")
    for label, value in (("runner-id", runner_id), ("session", session)):
        if not IDENT.fullmatch(str(value)):
            refuse(f"invalid {label}: {value!r}")
    if "maker" in runner_id.strip().lower():
        refuse(f"runner is the maker: {runner_id}")
    if not command:
        refuse("empty runner command")
    gate_check(project, phase)
    invocation_id = next_invocation_id(project)
    append_event(project, "STARTED", invocation_id, phase, runner_id, session)
    interrupted = type("Interrupted", (Exception,), {})
    def trap(signum, frame):
        raise interrupted()
    previous = [(sig, signal.signal(sig, trap)) for sig in (signal.SIGTERM, signal.SIGINT)]
    started_at = time.monotonic()
    process = None
    try:
        process = subprocess.Popen(command)
        exit_code = process.wait()
    except (interrupted, KeyboardInterrupt):
        if process is not None:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
        wall = f"{time.monotonic() - started_at:.3f}"
        append_event(project, "ABORTED", invocation_id, phase, runner_id, session,
                     wall_seconds=wall)
        print(f"INVOKE ABORTED - id={invocation_id} phase={phase} runner={runner_id}")
        return 130
    finally:
        for sig, handler in previous:
            signal.signal(sig, handler)
    wall = f"{time.monotonic() - started_at:.3f}"
    append_event(project, "COMPLETED", invocation_id, phase, runner_id, session,
                 exit_code=str(exit_code), wall_seconds=wall)
    print(f"INVOKE COMPLETED - id={invocation_id} phase={phase} runner={runner_id} exit={exit_code}")
    return exit_code


def main():
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("run")
    p.add_argument("project")
    p.add_argument("--phase", required=True, choices=sorted(PREDECESSOR_GATE))
    p.add_argument("--runner-id", required=True)
    p.add_argument("--session", required=True)
    argv = sys.argv[1:]
    command = []
    if "--" in argv:
        split = argv.index("--")
        argv, command = argv[:split], argv[split + 1:]
    args = parser.parse_args(argv)
    sys.exit(run(args.project, args.phase, args.runner_id, args.session, command))


if __name__ == "__main__":
    main()
