#!/usr/bin/env python3
"""LDL v0.7.0 runner-invocation wrapper (stdlib only).

Commands:
  invoke.py run PROJECT --phase P0..P6 --runner-id ID --session SESSION
      [--runner-role runner|verifier|reviewer|owner-proxy]
      [--job JOB.json (--approvals-root DIR | --approved-job-sha256 HEX)]
      [--expect EXPECTED_OUTPUTS.json]
      -- COMMAND [ARG...]

The wrapper is the only sanctioned way to launch a runner. It refuses the
launch unless tools/policy.py says the phase is reachable for the project's own
delivery profile, reserves the invocation ID and writes STARTED under an
exclusive project lock before the process exists, and writes COMPLETED/ABORTED
after it exits — so a started/completed mismatch survives any interruption as
evidence.

Two enforcement levels, named honestly in the output:

  legacy        gate policy only. Nothing binds the command, the cwd or the
                outputs. Use it for exploration; do not describe it as secured.
  approved-job  the above plus a manifest bound to an approval written outside
                this project. Still not an OS sandbox and still not human
                authentication — see tools/execution.py.
"""
import argparse
import json
import os
import signal
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import execution  # noqa: E402
import policy  # noqa: E402

LEDGER_REL = execution.LEDGER_REL
LEDGER_COLUMNS = execution.LEDGER_COLUMNS
IDENT = execution.IDENT

# Kept for callers and tests that still read the v0.6.1 constant. It is no
# longer the policy: profile-aware requirements live in tools/policy.py.
PREDECESSOR_GATE = {"P0": None, "P1": "G1", "P2": "G1", "P3": "G1", "P4": "G2", "P5": "G3", "P6": "G3"}


def refuse(reason):
    raise SystemExit(f"INVOKE REFUSED - {reason}")


def utcnow():
    return execution.utcnow()


def append_event(project, event, invocation_id, phase, runner_id, session,
                 exit_code="", wall_seconds=""):
    execution.append_event(project, event, invocation_id, phase, runner_id, session,
                           exit_code=exit_code, wall_seconds=wall_seconds)


def gate_check(project, phase):
    """Profile-aware launch policy. Raises SystemExit with the refusal reason."""
    try:
        return policy.evaluate(project, phase)
    except policy.PolicyError as exc:
        refuse(str(exc))


def _terminate(process):
    """Take the whole process group down so a runner cannot leave orphans."""
    if process is None or process.poll() is not None:
        return
    try:
        os.killpg(os.getpgid(process.pid), signal.SIGTERM)
    except (OSError, AttributeError):
        process.terminate()
    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(os.getpgid(process.pid), signal.SIGKILL)
        except (OSError, AttributeError):
            process.kill()
        process.wait()


def run(project, phase, runner_id, session, command, job=None, approvals_root=None,
        pinned=None, runner_role="runner", expect=None, cwd=None):
    project = os.path.realpath(project)
    if phase not in policy.PHASES:
        refuse(f"unknown phase: {phase}")
    for label, value in (("runner-id", runner_id), ("session", session)):
        if not IDENT.fullmatch(str(value)):
            refuse(f"invalid {label}: {value!r}")
    if "maker" in str(runner_id).strip().lower():
        refuse(f"runner is the maker: {runner_id}")
    if "maker" in str(runner_role).strip().lower():
        refuse(f"invalid runner_role: {runner_role}")
    if not command:
        refuse("empty runner command")

    decision = gate_check(project, phase)

    # The expectation is read, validated and frozen once, before anything runs.
    # Reconciliation uses this copy, so a child that rewrites the manifest is
    # still judged against what was approved (review 1, class 4).
    frozen_expect, expect_digest = None, None
    if expect:
        try:
            frozen_expect, expect_digest = execution.freeze_expected(expect)
        except execution.ManifestError as exc:
            refuse(str(exc))

    binding = None
    if job:
        try:
            binding = execution.check_job(project, phase, runner_id, command, job,
                                          approvals_root=approvals_root, pinned=pinned, cwd=cwd,
                                          runner_role=runner_role, expected_manifest=frozen_expect)
        except (execution.ManifestError, execution.ApprovalError) as exc:
            refuse(str(exc))
    elif approvals_root or pinned:
        refuse("an approval was supplied without --job; there is nothing to bind it to")

    if binding:
        print(f"INVOKE ENFORCEMENT - approved-job "
              f"(declaration binding via {binding['approval']['trust_root']}; {execution.DISCLAIMER})")
    else:
        print("INVOKE ENFORCEMENT - legacy (limited: launch policy only; no job binding, "
              "no command binding, no output containment)")

    try:
        invocation_id = execution.reserve_and_start(project, phase, runner_id, session)
    except execution.ManifestError as exc:
        refuse(str(exc))
    if frozen_expect:
        # Claim the declared output paths against every other live invocation,
        # and record the honest terminal row if the claim cannot be granted.
        try:
            execution.reserve_outputs(project, invocation_id, frozen_expect)
        except execution.ManifestError as exc:
            append_event(project, "ABORTED", invocation_id, phase, runner_id, session,
                         wall_seconds="0.000")
            refuse(str(exc))
    if binding:
        execution.record_job_binding(project, {
            "schema": "ldl-approved-job-binding-v1", "timestamp": utcnow(),
            "invocation_id": invocation_id, "job_sha256": binding["job_sha256"],
            "enforcement": binding["enforcement"], "trust_root": binding["approval"]["trust_root"],
            "approver": binding["approval"].get("approver"),
            "approval_mode": binding["approval"].get("approval_mode"),
            "approval_path": binding["approval"].get("approval_path"),
            "expected_manifest_sha256": expect_digest,
            "phase": phase, "runner_id": runner_id, "runner_role": binding["job"]["runner_role"],
            "output_root": binding["job"]["output_root"], "profile": decision["profile"],
            "limits": binding["limits"],
        })

    interrupted = type("Interrupted", (Exception,), {})

    def trap(signum, frame):
        raise interrupted()

    previous = [(sig, signal.signal(sig, trap)) for sig in (signal.SIGTERM, signal.SIGINT)]
    started_at = time.monotonic()
    started_wall = time.time()
    process = None
    try:
        try:
            process = subprocess.Popen(command, cwd=cwd, start_new_session=True)
        except OSError as exc:
            wall = f"{time.monotonic() - started_at:.3f}"
            append_event(project, "ABORTED", invocation_id, phase, runner_id, session, wall_seconds=wall)
            execution.release_outputs(project, invocation_id)
            print(f"INVOKE LAUNCH FAILED - id={invocation_id} phase={phase} runner={runner_id} error={exc}")
            return 127
        exit_code = process.wait()
    except (interrupted, KeyboardInterrupt):
        _terminate(process)
        wall = f"{time.monotonic() - started_at:.3f}"
        append_event(project, "ABORTED", invocation_id, phase, runner_id, session, wall_seconds=wall)
        execution.release_outputs(project, invocation_id)
        print(f"INVOKE ABORTED - id={invocation_id} phase={phase} runner={runner_id}")
        return 130
    finally:
        for sig, handler in previous:
            signal.signal(sig, handler)
    wall = f"{time.monotonic() - started_at:.3f}"
    append_event(project, "COMPLETED", invocation_id, phase, runner_id, session,
                 exit_code=str(exit_code), wall_seconds=wall)
    print(f"INVOKE COMPLETED - id={invocation_id} phase={phase} runner={runner_id} exit={exit_code}")

    if not frozen_expect:
        return exit_code

    # A completed process is not a delivered artifact. Reconcile separately and
    # report both, then fail the command if the declared outputs are not there.
    report = execution.reconcile(project, frozen_expect, not_before=started_wall,
                                 process_complete=True, exit_code=exit_code,
                                 manifest_sha256=expect_digest)
    execution.release_outputs(project, invocation_id)
    report_dir = os.path.join(project, "logs", "reconciliation")
    os.makedirs(report_dir, exist_ok=True)
    report_path = os.path.join(report_dir, f"{invocation_id}.json")
    with open(report_path, "w", encoding="utf-8") as handle:
        json.dump(report, handle, indent=2, ensure_ascii=False)
        handle.write("\n")
    failures = [item for item in report["outputs"] if item["status"] != "OK"]
    print(f"INVOKE ARTIFACTS - id={invocation_id} verdict={report['verdict']} "
          f"outputs={len(report['outputs'])} failing={len(failures)} "
          f"user_acceptance={report['user_acceptance']} report={os.path.relpath(report_path, project)}")
    for item in failures:
        print(f"  {item['id']} {item['status']} {item['path']} {item['detail']}")
    if report["verdict"] != "PASS":
        return exit_code or 65
    return exit_code


def main():
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("run")
    p.add_argument("project")
    p.add_argument("--phase", required=True, choices=sorted(policy.PHASES))
    p.add_argument("--runner-id", required=True)
    p.add_argument("--session", required=True)
    p.add_argument("--runner-role", default="runner")
    p.add_argument("--job")
    p.add_argument("--approvals-root")
    p.add_argument("--approved-job-sha256")
    p.add_argument("--expect")
    p.add_argument("--cwd")
    argv = sys.argv[1:]
    command = []
    if "--" in argv:
        split = argv.index("--")
        argv, command = argv[:split], argv[split + 1:]
    args = parser.parse_args(argv)
    sys.exit(run(args.project, args.phase, args.runner_id, args.session, command,
                 job=args.job, approvals_root=args.approvals_root,
                 pinned=args.approved_job_sha256, runner_role=args.runner_role,
                 expect=args.expect, cwd=args.cwd))


if __name__ == "__main__":
    main()
