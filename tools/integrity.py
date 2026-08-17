"""LDL v0.3 gate, evidence, safety, and verdict integrity checks.

This module intentionally checks structural invariants only. Whether evidence is
true or a recommendation is good remains a separated semantic judgment.
"""
import os
import re
from datetime import datetime, timezone


GATE_COLUMNS = ["Gate", "Verdict", "Contract version", "Approval mode", "Approver", "Approved at", "Evidence"]
EVIDENCE_COLUMNS = ["Claim ID", "Label", "Claim", "Source artifact", "Captured at", "Scope/window", "Transform/reproducer", "Status"]
DIMENSION_COLUMNS = ["Dimension ID", "Status", "Evidence"]
ACTION_COLUMNS = ["Action ID", "Impact dimensions", "Preconditions", "Approval tier", "Approval evidence", "Canary", "Rollback", "Ready"]
REQUIREMENT_COLUMNS = ["Requirement ID", "Verdict", "Evidence"]
REQUIREMENTS_LEDGER_COLUMNS = ["Requirement ID", "Type", "Priority", "Requirement", "Verification", "Source"]
PHASE_COLUMNS = ["Phase", "Status", "Date", "Deliverable"]


def _read(lint, path, code):
    return lint.read_text(path, code) if os.path.isfile(path) else ""


def check(lint, proj):
    contract_path = os.path.join(proj, "00_CONTRACT.md")
    contract = _read(lint, contract_path, "L8")
    workspace_v3 = os.path.isfile(os.path.join(lint.root, ".ldl-version"))
    if not contract:
        return
    if not lint.section_text(contract, "Governance profile"):
        if workspace_v3:
            lint.err("L8", f"{lint.rel(contract_path)}: v0.3 project missing Governance profile")
        return  # marker-free pre-v0.3 workspace remains readable

    profile = lint.section_text(contract, "Governance profile")
    version = lint.scalar_field(profile, "Contract version")
    approval_mode = lint.scalar_field(profile, "Approval mode").lower()
    quantitative = lint.scalar_field(profile, "Quantitative claims").lower()
    risk = lint.scalar_field(profile, "Risk level").lower()
    crel = lint.rel(contract_path)
    if not re.fullmatch(r"v\d+(?:\.\d+)*", version):
        lint.err("L8", f"{crel}: invalid Contract version")
    if approval_mode not in {"human", "delegated-agent"}:
        lint.err("L8", f"{crel}: Approval mode must be human or delegated-agent")
    if quantitative not in {"yes", "no"}:
        lint.err("L9", f"{crel}: Quantitative claims must be yes or no")
    if risk not in {"low", "medium", "high"}:
        lint.err("L10", f"{crel}: Risk level must be low, medium, or high")

    setup = lint.section_text(contract, "Verification setup")
    if lint.scalar_field(setup, "Target access").lower() != "read-only":
        lint.err("L11", f"{crel}: Target access must be read-only")
    if not lint.scalar_field(setup, "Verifier workspace"):
        lint.err("L11", f"{crel}: Verifier workspace missing")

    progress_path = os.path.join(proj, "PROGRESS.md")
    progress = _read(lint, progress_path, "L8")
    phase_rows = lint.table_rows(progress, "Phase progress", PHASE_COLUMNS, "L8", lint.rel(progress_path))
    phase_names = [row["Phase"] for row in phase_rows]
    if len(phase_names) != len(set(phase_names)):
        lint.err("L8", f"{lint.rel(progress_path)}: duplicate phase row")
    phase_status = {row["Phase"]: row["Status"].lower() for row in phase_rows}
    gate_rows = lint.table_rows(progress, "Gate ledger", GATE_COLUMNS, "L8", lint.rel(progress_path))
    gate_names = [row["Gate"] for row in gate_rows]
    if len(gate_names) != len(set(gate_names)):
        lint.err("L8", f"{lint.rel(progress_path)}: duplicate gate row")
    unexpected_gates = sorted(set(gate_names) - {"G1", "G2", "G3", "G4"})
    if unexpected_gates:
        lint.err("L8", f"{lint.rel(progress_path)}: unexpected gate row - {', '.join(unexpected_gates)}")
    gates = {row["Gate"]: row for row in gate_rows}
    allowed = {"PENDING", "HOLD", "PASS", "FAIL", "SUPERSEDED"}
    previous_time = None
    used_gate_evidence = set()
    used_approval_content = set()
    for number in range(1, 5):
        name = f"G{number}"
        row = gates.get(name)
        if row is None:
            lint.err("L8", f"{lint.rel(progress_path)}: gate row missing - {name}")
            continue
        verdict = row["Verdict"]
        if verdict not in allowed:
            lint.err("L8", f"{lint.rel(progress_path)}: invalid gate verdict - {name} {verdict}")
            continue
        if verdict != "SUPERSEDED" and row["Contract version"] != version:
            lint.err("L8", f"{lint.rel(progress_path)}: gate contract version {row['Contract version']} does not match current {version}")
        if row["Approval mode"].lower() != approval_mode:
            lint.err("L8", f"{lint.rel(progress_path)}: gate approval mode does not match contract - {name}")
        if verdict != "PASS":
            continue
        for prior in range(1, number):
            prior_row = gates.get(f"G{prior}")
            if prior_row and prior_row["Verdict"] != "PASS":
                lint.err("L8", f"{lint.rel(progress_path)}: {name} PASS while G{prior} is not PASS")
                break
        missing = [field for field in ("Approver", "Approved at", "Evidence") if not row[field]]
        if missing:
            lint.err("L8", f"{lint.rel(progress_path)}: {name} PASS missing approval evidence fields - {', '.join(missing)}")
        approved_dt = None
        if row["Approved at"]:
            try:
                approved_dt = datetime.strptime(row["Approved at"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
            except ValueError:
                lint.err("L8", f"{lint.rel(progress_path)}: {name} Approved at must be valid UTC ISO-8601")
        if approved_dt and approved_dt > datetime.now(timezone.utc):
            lint.err("L8", f"{lint.rel(progress_path)}: {name} approval timestamp is in the future")
        if previous_time and row["Approved at"] and row["Approved at"] < previous_time:
            lint.err("L8", f"{lint.rel(progress_path)}: {name} approval predates previous gate")
        if row["Approved at"]:
            previous_time = row["Approved at"]
        target = lint.local_link_target(proj, row["Evidence"])
        if not target:
            lint.err("L8", f"{lint.rel(progress_path)}: {name} PASS missing approval evidence link")
        elif target.startswith(("http://", "https://", "mailto:")):
            lint.err("L8", f"{lint.rel(progress_path)}: {name} approval evidence must be immutable under project raw/")
        else:
            raw_root = os.path.realpath(os.path.join(proj, "raw"))
            if not os.path.isfile(target):
                lint.err("L8", f"{lint.rel(progress_path)}: {name} approval evidence missing - {lint.rel(target)}")
            elif os.path.commonpath([raw_root, os.path.realpath(target)]) != raw_root:
                lint.err("L8", f"{lint.rel(progress_path)}: {name} approval evidence must be immutable under project raw/")
            else:
                approval_text = _read(lint, target, "L8")
                if not lint.substantive_cell(approval_text):
                    lint.err("L8", f"{lint.rel(progress_path)}: {name} approval evidence is empty or placeholder")
                gate_number = name[1:]
                mentioned = set()
                for match in re.finditer(r"\b(?:G([1-4])|Gate\s+([1-4]))\b", approval_text, re.I):
                    mentioned.add("G" + (match.group(1) or match.group(2)))
                if mentioned != {name}:
                    lint.err("L8", f"{lint.rel(progress_path)}: {name} approval evidence does not identify this gate")
                if not re.search(rf"\b{re.escape(version)}\b", approval_text, re.I):
                    lint.err("L8", f"{lint.rel(progress_path)}: {name} approval evidence does not identify contract {version}")
                real_target = os.path.realpath(target)
                if real_target in used_gate_evidence:
                    lint.err("L8", f"{lint.rel(progress_path)}: {name} reuses another gate approval artifact")
                used_gate_evidence.add(real_target)
                normalized_approval = " ".join(lint.structural_text(approval_text).split()).lower()
                if normalized_approval in used_approval_content:
                    lint.err("L8", f"{lint.rel(progress_path)}: {name} duplicates another gate approval content")
                used_approval_content.add(normalized_approval)

    required_phases = {
        "G1": ("P0 contract",),
        "G2": ("P1 requirements", "P2 structure", "P3 research"),
        "G3": ("P4 scoping",),
        "G4": ("P5+P6 increments",),
    }
    log_path = os.path.join(proj, "logs", "log.md")
    gate_log = lint.structural_text(_read(lint, log_path, "L8"))
    for gate, phases in required_phases.items():
        if gates.get(gate, {}).get("Verdict") != "PASS":
            continue
        for phase in phases:
            if phase_status.get(phase) != "done":
                lint.err("L8", f"{lint.rel(progress_path)}: {gate} PASS while phase {phase} is not done")
        if not re.search(rf"^GATE-PASS:\s*{gate}\s+contract={re.escape(version)}\s*$", gate_log, re.M):
            lint.err("L8", f"{lint.rel(log_path)}: {gate} PASS missing append-only gate event for contract {version}")

    evidence_path = os.path.join(proj, "03_EVIDENCE.md")
    evidence_rows = lint.table_rows(_read(lint, evidence_path, "L9"), "Evidence ledger", EVIDENCE_COLUMNS, "L9", lint.rel(evidence_path))
    claim_ids = [row["Claim ID"] for row in evidence_rows]
    if len(claim_ids) != len(set(claim_ids)):
        lint.err("L9", f"{lint.rel(evidence_path)}: duplicate Claim ID")
    for row in evidence_rows:
        if not lint.substantive_cell(row["Claim ID"]) or not lint.substantive_cell(row["Claim"]):
            lint.err("L9", f"{lint.rel(evidence_path)}: evidence row missing Claim ID or Claim")
        if row["Status"] not in {"ACTIVE", "DISPUTED", "SUPERSEDED"}:
            lint.err("L9", f"{lint.rel(evidence_path)}: invalid evidence status - {row['Status'] or 'empty'}")
        label = row["Label"].lower()
        if label not in {"[hypothesis]", "[measured]", "[proven]"}:
            lint.err("L9", f"{lint.rel(evidence_path)}: invalid evidence label - {row['Claim ID']}")
            continue
        if label not in {"[measured]", "[proven]"}:
            continue
        target = lint.local_link_target(proj, row["Source artifact"])
        if not target:
            lint.err("L9", f"{lint.rel(evidence_path)}: {row['Claim ID']} measured/proven claim missing source artifact")
        elif target.startswith(("http://", "https://", "mailto:")):
            lint.err("L9", f"{lint.rel(evidence_path)}: {row['Claim ID']} source artifact must be captured under project raw/")
        elif not os.path.isfile(target):
            lint.err("L9", f"{lint.rel(evidence_path)}: {row['Claim ID']} source artifact missing - {lint.rel(target)}")
        elif os.path.commonpath([os.path.realpath(os.path.join(proj, "raw")), os.path.realpath(target)]) != os.path.realpath(os.path.join(proj, "raw")):
            lint.err("L9", f"{lint.rel(evidence_path)}: {row['Claim ID']} source artifact must be captured under project raw/")
        try:
            captured_dt = datetime.strptime(row["Captured at"], "%Y-%m-%d").replace(tzinfo=timezone.utc)
        except ValueError:
            lint.err("L9", f"{lint.rel(evidence_path)}: {row['Claim ID']} measured/proven claim missing capture date")
        else:
            if captured_dt > datetime.now(timezone.utc):
                lint.err("L9", f"{lint.rel(evidence_path)}: {row['Claim ID']} capture date is in the future")
        if not lint.substantive_cell(row["Scope/window"]):
            lint.err("L9", f"{lint.rel(evidence_path)}: {row['Claim ID']} measured/proven claim missing scope/window")
        if not lint.substantive_cell(row["Transform/reproducer"]):
            lint.err("L9", f"{lint.rel(evidence_path)}: {row['Claim ID']} measured/proven claim missing transform/reproducer")
    if gates.get("G2", {}).get("Verdict") == "PASS" and not evidence_rows:
        lint.err("L9", f"{lint.rel(progress_path)}: G2 PASS requires at least one evidence row")

    scope_path = os.path.join(proj, "04_SCOPE.md")
    scope = _read(lint, scope_path, "L10")
    dimensions = lint.table_rows(scope, "Impact dimensions", DIMENSION_COLUMNS, "L10", lint.rel(scope_path))
    dimension_ids = [row["Dimension ID"] for row in dimensions]
    if len(dimension_ids) != len(set(dimension_ids)):
        lint.err("L10", f"{lint.rel(scope_path)}: duplicate Dimension ID")
    dimension_status = {row["Dimension ID"]: row["Status"] for row in dimensions}
    for dim, status in dimension_status.items():
        if status not in {"PASS", "HOLD", "FAIL", "NOT_RUN"}:
            lint.err("L10", f"{lint.rel(scope_path)}: invalid impact status - {dim} {status}")
    for row in dimensions:
        target = lint.local_link_target(proj, row["Evidence"])
        if not lint.substantive_cell(row["Dimension ID"]) or not target or target.startswith(("http://", "https://", "mailto:")) or not os.path.isfile(target):
            lint.err("L10", f"{lint.rel(scope_path)}: impact dimension {row['Dimension ID']} missing evidence")
    actions = lint.table_rows(scope, "Action readiness", ACTION_COLUMNS, "L10", lint.rel(scope_path))
    action_ids = [row["Action ID"] for row in actions]
    if len(action_ids) != len(set(action_ids)):
        lint.err("L10", f"{lint.rel(scope_path)}: duplicate Action ID")
    for row in actions:
        if not lint.substantive_cell(row["Action ID"]):
            lint.err("L10", f"{lint.rel(scope_path)}: action missing substantive Action ID")
        if row["Approval tier"] not in {"0", "1", "2"}:
            lint.err("L10", f"{lint.rel(scope_path)}: invalid approval tier - {row['Action ID']} {row['Approval tier']}")
        if row["Ready"] not in {"YES", "NO"}:
            lint.err("L10", f"{lint.rel(scope_path)}: invalid Ready verdict - {row['Action ID']}")
        impacted = [item.strip() for item in row["Impact dimensions"].split(",") if item.strip()]
        if row["Ready"] == "YES" and not impacted:
            lint.err("L10", f"{lint.rel(scope_path)}: ready action {row['Action ID']} has no impact dimensions")
        for dim in impacted:
            status = dimension_status.get(dim)
            if status is None:
                lint.err("L10", f"{lint.rel(scope_path)}: action {row['Action ID']} references unknown impact dimension {dim}")
            elif row["Ready"] == "YES" and status != "PASS":
                lint.err("L10", f"{lint.rel(scope_path)}: action {row['Action ID']} is ready while impact dimension {dim} is {status}")
        if row["Ready"] == "YES" and row["Approval tier"] in {"1", "2"}:
            target = lint.local_link_target(proj, row["Approval evidence"])
            raw_root = os.path.realpath(os.path.join(proj, "raw"))
            if (not target or target.startswith(("http://", "https://", "mailto:"))
                    or not os.path.isfile(target)
                    or os.path.commonpath([raw_root, os.path.realpath(target)]) != raw_root):
                lint.err("L10", f"{lint.rel(scope_path)}: ready action {row['Action ID']} missing approval evidence")
        if row["Ready"] == "YES" and any(not lint.substantive_cell(row[field]) for field in ("Preconditions", "Canary", "Rollback")):
            lint.err("L10", f"{lint.rel(scope_path)}: ready action {row['Action ID']} missing precondition/canary/rollback")
    if gates.get("G3", {}).get("Verdict") == "PASS" and (not dimensions or not actions):
        lint.err("L10", f"{lint.rel(progress_path)}: G3 PASS requires impact dimensions and action readiness rows")

    if quantitative == "yes":
        model = lint.section_text(scope, "Quantitative model")
        if not model:
            lint.err("L9", f"{lint.rel(scope_path)}: quantitative project missing Quantitative model")
        else:
            fields = ("Baseline window", "Baseline unit", "Candidate window", "Candidate unit", "Assumptions", "Formula/reproducer", "Reconciliation")
            for field in fields:
                if not lint.substantive_cell(lint.scalar_field(model, field)):
                    lint.err("L9", f"{lint.rel(scope_path)}: Quantitative model field missing - {field}")

    requirements_path = os.path.join(proj, "01_REQUIREMENTS.md")
    requirement_definitions = lint.table_rows(_read(lint, requirements_path, "L11"), "Requirements ledger",
        REQUIREMENTS_LEDGER_COLUMNS, "L11", lint.rel(requirements_path))
    defined_ids = [row["Requirement ID"] for row in requirement_definitions]
    if not defined_ids or any(not lint.substantive_cell(value) for value in defined_ids):
        lint.err("L11", f"{lint.rel(requirements_path)}: at least one substantive requirement ID required")
    if len(defined_ids) != len(set(defined_ids)):
        lint.err("L11", f"{lint.rel(requirements_path)}: duplicate Requirement ID")
    for row in requirement_definitions:
        if any(not lint.substantive_cell(row[field]) for field in REQUIREMENTS_LEDGER_COLUMNS):
            lint.err("L11", f"{lint.rel(requirements_path)}: incomplete requirement row - {row['Requirement ID'] or 'missing ID'}")
        if not re.match(r"^\((?:a|b|c)\)\s+", row["Source"], re.I):
            lint.err("L11", f"{lint.rel(requirements_path)}: requirement source must start with (a), (b), or (c) - {row['Requirement ID']}")

    verification_path = os.path.join(proj, "06_VERIFICATION.md")
    report = _read(lint, verification_path, "L11")
    requirements = lint.table_rows(report, "Requirement verdicts", REQUIREMENT_COLUMNS, "L11", lint.rel(verification_path))
    for row in requirements:
        if row["Verdict"] not in {"PASS", "FAIL", "HOLD", "NOT_RUN"}:
            lint.err("L11", f"{lint.rel(verification_path)}: invalid requirement verdict - {row['Requirement ID']} {row['Verdict']}")
        if row["Verdict"] == "PASS":
            target = lint.local_link_target(proj, row["Evidence"])
            if not target or target.startswith(("http://", "https://", "mailto:")) or not os.path.isfile(target):
                lint.err("L11", f"{lint.rel(verification_path)}: PASS requirement missing local evidence - {row['Requirement ID']}")
    verified_ids = [row["Requirement ID"] for row in requirements]
    if len(verified_ids) != len(set(verified_ids)):
        lint.err("L11", f"{lint.rel(verification_path)}: duplicate Requirement ID verdict")
    if set(verified_ids) != set(defined_ids):
        lint.err("L11", f"{lint.rel(verification_path)}: requirement verdict IDs do not exactly match requirements ledger")
    finals = lint.section_text(report, "Final verdicts")
    harness = lint.scalar_field(finals, "Harness")
    product = lint.scalar_field(finals, "Product")
    readiness = lint.scalar_field(finals, "Execution readiness")
    method = lint.scalar_field(finals, "Method conformance")
    history = lint.scalar_field(finals, "Historical violations")
    mutation = lint.scalar_field(finals, "Target mutation")
    independent = lint.scalar_field(finals, "Independent verifier")
    vocab = (
        (harness, {"PASS", "FAIL", "NOT_RUN"}, "Harness"),
        (product, {"PASS", "FAIL", "HOLD", "NOT_RUN"}, "Product"),
        (readiness, {"READY", "HOLD", "BLOCKED"}, "Execution readiness"),
        (method, {"PASS", "FAIL"}, "Method conformance"),
        (history, {"NONE", "PRESENT"}, "Historical violations"),
    )
    for value, values, name in vocab:
        if value not in values:
            lint.err("L11", f"{lint.rel(verification_path)}: invalid {name} verdict - {value or 'missing'}")
    if product == "PASS" and (not requirements or any(row["Verdict"] != "PASS" for row in requirements)):
        lint.err("L11", f"{lint.rel(verification_path)}: Product PASS requires every requirement PASS")
    nonpass_dimensions = [dim for dim, status in dimension_status.items() if status != "PASS"]
    if readiness == "READY" and nonpass_dimensions:
        lint.err("L10", f"{lint.rel(verification_path)}: Execution readiness READY with non-PASS impact dimension - {', '.join(nonpass_dimensions)}")
    if readiness == "READY" and (not dimensions or not actions):
        lint.err("L10", f"{lint.rel(verification_path)}: Execution readiness READY requires impact dimensions and actions")
    if readiness == "READY" and product != "PASS":
        lint.err("L11", f"{lint.rel(verification_path)}: Execution readiness READY requires Product PASS")
    log_text = _read(lint, os.path.join(proj, "logs", "log.md"), "L11")
    recorded_violation = bool(re.search(r"^LDL-VIOLATION:\s*\S+", log_text, re.M))
    if recorded_violation and history != "PRESENT":
        lint.err("L11", f"{lint.rel(verification_path)}: append-only violation record requires Historical violations PRESENT")
    if (history == "PRESENT" or recorded_violation) and method != "FAIL":
        lint.err("L11", f"{lint.rel(verification_path)}: historical violations require Method conformance FAIL")
    if mutation != "0 files":
        lint.err("L11", f"{lint.rel(verification_path)}: Target mutation must be 0 files")
    if not independent or "(" not in independent or ")" not in independent:
        lint.err("L11", f"{lint.rel(verification_path)}: Independent verifier missing identity/method")
    if risk == "high" and not re.match(r"^(different-model|domain-expert)\s*\(", independent, re.I):
        lint.err("L11", f"{lint.rel(verification_path)}: high-risk project requires different-model or domain-expert verifier")

    g4 = gates.get("G4")
    if g4 and g4["Verdict"] == "PASS" and (harness, product, readiness, method) != ("PASS", "PASS", "READY", "PASS"):
        lint.err("L11", f"{lint.rel(progress_path)}: G4 PASS requires Harness/Product/Readiness/Method all PASS/READY")
