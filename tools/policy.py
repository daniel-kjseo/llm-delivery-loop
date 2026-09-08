#!/usr/bin/env python3
"""LDL v0.7.0 profile-aware launch policy (stdlib only).

v0.6.1 held one hardcoded predecessor table — P4 needed G2, P5/P6 needed G3 —
and never read the delivery profile. That table is right for gated-high-risk
and portfolio-competition, and wrong for startup-reversible, whose whole point
is that a reversible MVP is engineered under G1 and shipped under the release
controls rather than behind two more approval gates. This module is the single
place where "may this phase launch under this profile" is decided, so the
wrapper, the reports and the tests cannot drift apart.

What a launch decision is *not*: it is not a release decision, not a claim that
an artifact is good, and not a human approval. It answers one question only —
is the declared phase reachable in this project right now.
"""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import workflow  # noqa: E402

PHASES = ("P0", "P1", "P2", "P3", "P4", "P5", "P6")
PROFILES = ("startup-reversible", "gated-high-risk", "pre-engineering-decision", "portfolio-competition")
# The documents a startup-reversible launch actually depends on. P3 research is
# deliberately absent: research continues alongside a reversible MVP, and
# demanding it `done` made P4/P5/P6 unreachable for the profile whose whole
# point is reaching them under G1 (independent review 1, class 1).
LAUNCH_PHASES = ("P0 contract", "P1 requirements", "P2 structure")

# Gates that must already be PASS before a phase may launch, per profile.
# startup-reversible replaces G2/G3 for P4+ with the document/scope/risk
# prerequisites below; it never replaces G1, and never touches release control.
REQUIRED_GATES = {
    "startup-reversible": {"P0": (), "P1": ("G1",), "P2": ("G1",), "P3": ("G1",),
                           "P4": ("G1",), "P5": ("G1",), "P6": ("G1",)},
    "gated-high-risk": {"P0": (), "P1": ("G1",), "P2": ("G1",), "P3": ("G1",),
                        "P4": ("G1", "G2"), "P5": ("G1", "G2", "G3"), "P6": ("G1", "G2", "G3")},
    "portfolio-competition": {"P0": (), "P1": ("G1",), "P2": ("G1",), "P3": ("G1",),
                              "P4": ("G1", "G2"), "P5": ("G1", "G2", "G3"), "P6": ("G1", "G2", "G3")},
    "pre-engineering-decision": {"P0": (), "P1": ("G1",), "P2": ("G1",), "P3": ("G1",),
                                 "P4": ("G1", "G2"), "P5": None, "P6": None},
}

# Phase-progress rows that must read `done`. Only startup-reversible carries
# these: for the other profiles the same documents are already a precondition
# of the G2/G3 PASS the phase requires, and repeating them would double-gate.
REQUIRED_PHASES = {
    "startup-reversible": {"P4": LAUNCH_PHASES, "P5": LAUNCH_PHASES + ("P4 scoping",),
                           "P6": LAUNCH_PHASES + ("P4 scoping",)},
}

# The reversible shortcut is only sound while the contract still declares a
# reversible launch. A startup contract that raises its own risk loses it.
LOW_RISK_PHASES = {"startup-reversible": ("P4", "P5", "P6")}


class PolicyError(Exception):
    """A launch is not permitted; the message is the reason a human will read."""


def _section(text, title):
    match = re.search(rf"^##\s+{re.escape(title)}\s*$([\s\S]*?)(?=^##\s+|\Z)", text, re.M)
    return match.group(1) if match else ""


def _field(section, name):
    match = re.search(rf"^-\s*{re.escape(name)}:\s*(.*)$", section, re.M)
    return match.group(1).strip() if match else ""


def read_contract(project):
    path = os.path.join(project, "00_CONTRACT.md")
    try:
        with open(path, encoding="utf-8") as handle:
            return handle.read()
    except OSError as exc:
        raise PolicyError(f"contract unreadable: {exc}")


def delivery_mode(project):
    """The declared delivery profile, or "" when the contract does not say."""
    try:
        return _field(_section(read_contract(project), "Delivery profile"), "Delivery mode")
    except PolicyError:
        return ""


def contract_version(project):
    try:
        return _field(_section(read_contract(project), "Governance profile"), "Contract version")
    except PolicyError:
        return ""


def launch_risk(project):
    contract = read_contract(project)
    return _field(_section(contract, "Launch brief"), "Risk")


def required_gates(profile, phase):
    if phase not in PHASES:
        raise PolicyError(f"unknown phase: {phase}")
    if profile not in REQUIRED_GATES:
        raise PolicyError(f"unknown delivery profile: {profile or 'missing'}")
    gates = REQUIRED_GATES[profile][phase]
    if gates is None:
        raise PolicyError(f"{profile} has no engineering phase; {phase} is outside the profile")
    return gates


def required_phases(profile, phase):
    return REQUIRED_PHASES.get(profile, {}).get(phase, ())


def read_progress(project):
    path = os.path.join(project, "PROGRESS.md")
    if not os.path.isfile(path):
        raise PolicyError(f"gate ledger missing: {path}")
    with open(path, encoding="utf-8") as handle:
        return handle.read()


def _tables(progress):
    try:
        _, gate_rows = workflow.markdown_table(progress, "Gate ledger", workflow.GATE_COLUMNS)
        _, phase_rows = workflow.markdown_table(
            progress, "Phase progress", ["Phase", "Status", "Date", "Deliverable"])
    except SystemExit as exc:
        raise PolicyError(f"PROGRESS.md is not readable as a control plane: {exc}")
    # A dict comprehension silently keeps the last of two rows for the same key,
    # so a ledger holding both `G1 HOLD` and `G1 PASS` used to launch. Ambiguity
    # in the control plane is refused, not resolved (independent review 1, class 2).
    for label, rows, key in (("Gate ledger", gate_rows, "Gate"),
                             ("Phase progress", phase_rows, "Phase")):
        names = [row[key] for row in rows]
        duplicates = sorted({name for name in names if names.count(name) > 1})
        if duplicates:
            raise PolicyError(
                f"PROGRESS.md {label} states duplicate {key} row(s) {duplicates}; "
                "an ambiguous control plane is not a control plane")
    return ({row["Gate"]: row for row in gate_rows},
            {row["Phase"]: row["Status"].strip().lower() for row in phase_rows})


def verify_gate(project, gate, gates, phases, active_version):
    """Revalidate one PASS row against the active contract, its own phases,
    its predecessors, and its typed decision artifact.

    Historical semantics are preserved: only this decision is held to the
    active contract version. A REOPEN chain keeps validating its lower-version
    prior FAIL through workflow.validate_gate_decision, exactly as before.
    """
    row = gates.get(gate)
    if row is None:
        raise PolicyError(f"predecessor gate {gate} has no ledger row")
    if row["Verdict"] != "PASS":
        raise PolicyError(f"predecessor gate {gate} is {row['Verdict'] or 'PENDING'}, not PASS")
    if row["Contract version"] != active_version:
        raise PolicyError(
            f"predecessor gate {gate} PASS was decided under contract "
            f"{row['Contract version'] or 'unknown'} but the active contract is {active_version or 'unknown'}")
    for prior in workflow.GATES[:workflow.GATES.index(gate)]:
        prior_row = gates.get(prior)
        if not prior_row or prior_row["Verdict"] != "PASS":
            state = prior_row["Verdict"] if prior_row else "missing"
            raise PolicyError(f"predecessor gate {gate} PASS rests on {prior}, which is {state or 'PENDING'}")
    for owned in workflow.GATE_PHASES[gate]:
        if phases.get(owned) != "done":
            raise PolicyError(
                f"predecessor gate {gate} PASS requires phase {owned} done, not {phases.get(owned) or 'missing'}")

    link = re.search(r"\]\(([^)]+)\)", row["Evidence"])
    rel = link.group(1) if link else ""
    decisions_root = os.path.realpath(os.path.join(project, "raw", "gate-decisions"))
    try:
        decision_path = workflow.project_file(project, rel)
    except ValueError:
        decision_path = ""
    if (not rel.endswith(".json") or not decision_path
            or os.path.commonpath([decisions_root, decision_path]) != decisions_root):
        raise PolicyError(f"predecessor gate {gate} PASS lacks typed evidence under raw/gate-decisions/")
    import json
    try:
        with open(decision_path, encoding="utf-8") as handle:
            decision = json.load(handle)
        workflow.validate_gate_decision(project, decision)
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        raise PolicyError(f"predecessor gate {gate} typed evidence invalid: {exc}")
    for field, expected in (("gate", gate), ("verdict", "PASS"),
                            ("contract_version", row["Contract version"]),
                            ("approver", row["Approver"])):
        if decision.get(field) != expected:
            raise PolicyError(f"predecessor gate {gate} typed evidence mismatch: {field}")
    return decision


def evaluate(project, phase):
    """Decide whether `phase` may launch. Raises PolicyError with the reason.

    Returns the decision record so callers can log what they relied on.
    """
    project = os.path.realpath(project)
    profile = delivery_mode(project)
    if profile not in PROFILES:
        raise PolicyError(
            f"contract declares no supported delivery profile: {profile or 'missing'} "
            f"(one of {', '.join(PROFILES)})")
    gates_needed = required_gates(profile, phase)
    phases_needed = required_phases(profile, phase)
    active_version = contract_version(project)
    if not re.fullmatch(r"v\d+(?:\.\d+)*", active_version or ""):
        raise PolicyError(f"contract declares no usable Contract version: {active_version or 'missing'}")

    progress = read_progress(project)
    gates, phase_status = _tables(progress)
    for gate in gates_needed:
        verify_gate(project, gate, gates, phase_status, active_version)
    for owned in phases_needed:
        if phase_status.get(owned) != "done":
            raise PolicyError(
                f"{profile} {phase} requires launch document {owned} done, "
                f"not {phase_status.get(owned) or 'missing'}")
    if phase in LOW_RISK_PHASES.get(profile, ()):
        risk = launch_risk(project)
        if risk != "low-reversible":
            raise PolicyError(
                f"{profile} {phase} runs without a G2/G3 gate only while the Launch brief "
                f"Risk stays low-reversible; it reads {risk or 'missing'}")
    return {"profile": profile, "phase": phase, "contract_version": active_version,
            "required_gates": list(gates_needed), "required_phases": list(phases_needed),
            "decided_by": "tools/policy.py"}


def describe(profile):
    """The whole table for one profile, for reports and documentation."""
    if profile not in REQUIRED_GATES:
        raise PolicyError(f"unknown delivery profile: {profile or 'missing'}")
    rows = []
    for phase in PHASES:
        gates = REQUIRED_GATES[profile][phase]
        rows.append({"phase": phase,
                     "gates": "DENIED" if gates is None else list(gates),
                     "phases_done": list(required_phases(profile, phase))})
    return rows


def main():
    import argparse
    import json
    parser = argparse.ArgumentParser(description="show or evaluate the launch policy")
    sub = parser.add_subparsers(dest="command", required=True)
    show = sub.add_parser("show"); show.add_argument("profile", choices=PROFILES)
    check = sub.add_parser("check"); check.add_argument("project"); check.add_argument("--phase", required=True)
    args = parser.parse_args()
    if args.command == "show":
        print(json.dumps({"profile": args.profile, "policy": describe(args.profile)}, indent=2))
        return 0
    try:
        print(json.dumps(evaluate(args.project, args.phase), indent=2))
    except PolicyError as exc:
        print(f"POLICY DENIED - {exc}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
