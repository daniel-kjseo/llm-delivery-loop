#!/usr/bin/env python3
"""LDL v0.6.0 deterministic workflow operations (stdlib only).

Commands:
  workflow.py scratch-init TARGET SCRATCH
  workflow.py promote SCRATCH TARGET [--through P0|P3|P4|final]
  workflow.py raw-put PROJECT RELATIVE_PATH SOURCE_FILE
  workflow.py sync-verdicts PROJECT
  workflow.py gate-validate PROJECT DECISION.json
  workflow.py gate-apply PROJECT DECISION.json
  workflow.py gate-reopen PROJECT REVISED_CONTRACT DECISION.json
  workflow.py prompt-log PROJECT SESSION SOURCE_FILE [--actor human|agent]
"""
import argparse
import csv
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone

BASELINE_FILE = ".ldl-scratch-baseline.json"
SKIP_DIRS = {".git", "node_modules", "__pycache__"}
GATE_SCHEMA = "ldl-gate-decision-v1"
GATES = ("G1", "G2", "G3", "G4")
GATE_PHASES = {
    "G1": ("P0 contract",),
    "G2": ("P1 requirements", "P2 structure", "P3 research"),
    "G3": ("P4 scoping",),
    "G4": ("P5+P6 increments",),
}
STAGE_RANK = {"P0": 0, "P3": 3, "P4": 4, "final": 6}
PHASE_OWNED_FILES = {
    "02_EVALUATION.json": "P0",
    "01_REQUIREMENTS.md": "P3",
    "CLAUDE.md": "P3",
    "03_EVIDENCE.md": "P3",
    "03_PORTFOLIO.json": "P3",
    "06_VERIFICATION.md": "P3",
    "04_SCOPE.md": "P4",
    "04_PREFLIGHT.json": "P4",
    "06_CAPABILITIES.json": "final",
    "06_JUDGE_SCORES.json": "final",
    "06_SUBMISSION.json": "final",
}
GATE_COLUMNS = ["Gate", "Verdict", "Contract version", "Approval mode", "Approver", "Approved at", "Evidence"]
REQ_COLUMNS = ["Requirement ID", "Type", "Priority", "Requirement", "Verification", "Source"]
VERDICT_COLUMNS = ["Requirement ID", "Verdict", "Evidence"]


def sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def atomic_write(path, data, binary=False, exclusive=False):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    if exclusive:
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
        descriptor = os.open(path, flags, 0o644)
        if binary:
            with os.fdopen(descriptor, "wb") as handle:
                handle.write(data)
        else:
            with os.fdopen(descriptor, "w", encoding="utf-8", newline="") as handle:
                handle.write(data)
        return
    descriptor, temporary = tempfile.mkstemp(prefix=".ldl-write-", dir=os.path.dirname(path))
    os.close(descriptor)
    try:
        if binary:
            with open(temporary, "wb") as handle:
                handle.write(data)
        else:
            with open(temporary, "w", encoding="utf-8", newline="") as handle:
                handle.write(data)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def inventory(root):
    root = os.path.realpath(root)
    result = {}
    for current, dirs, files in os.walk(root):
        for name in list(dirs):
            path = os.path.join(current, name)
            if os.path.islink(path):
                raise SystemExit(f"unsupported directory symlink in workflow tree: {os.path.relpath(path, root)}")
        dirs[:] = sorted(d for d in dirs if d not in SKIP_DIRS)
        for name in sorted(files):
            path = os.path.join(current, name)
            rel = os.path.relpath(path, root)
            if rel == BASELINE_FILE:
                continue
            if not os.path.isfile(path) or os.path.islink(path):
                raise SystemExit(f"unsupported non-regular file in workflow tree: {rel}")
            result[rel] = {"sha256": sha256(path), "size": os.path.getsize(path)}
    return result


def inside_raw(rel):
    return "raw" in rel.split(os.sep)


def is_append_log(rel):
    parts = rel.split(os.sep)
    return "logs" in parts and parts[-1] in {
        "log.md", "cost-ledger.csv", "prompts.jsonl", "intervention-ledger.csv"}


def is_root_tool(rel):
    parts = rel.split(os.sep)
    return len(parts) > 1 and parts[0] == "tools"


def is_control_plane(rel):
    return rel.split(os.sep)[-1] == "PROGRESS.md"


def required_stage(rel):
    parts = rel.split(os.sep)
    if "05_engineering" in parts:
        return "final"
    return PHASE_OWNED_FILES.get(parts[-1], "P0")


def evaluation_frozen(target, rel):
    if rel.split(os.sep)[-1] != "02_EVALUATION.json":
        return False
    parts = rel.split(os.sep)
    if "projects" in parts:
        index = parts.index("projects")
        project = os.path.join(target, *parts[:index + 2])
    else:
        project = target
    progress = os.path.join(project, "PROGRESS.md")
    if not os.path.isfile(progress):
        return False
    with open(progress, encoding="utf-8") as handle:
        text = handle.read()
    match = re.search(r"^\|\s*G1\s*\|\s*([^|]+)\|", text, re.M)
    return bool(match and match.group(1).strip() != "PENDING")


def scratch_init(target, scratch):
    target = os.path.realpath(target)
    scratch = os.path.realpath(scratch)
    if not os.path.isdir(target):
        raise SystemExit(f"target workspace missing: {target}")
    try:
        if os.path.commonpath([target, scratch]) == target:
            raise SystemExit("scratch must be outside the target workspace")
    except ValueError:
        pass
    if os.path.exists(scratch):
        raise SystemExit(f"scratch already exists: {scratch}")
    target_inventory = inventory(target)  # reject symlinks/devices before copytree can follow them
    shutil.copytree(target, scratch, symlinks=False)
    baseline = {"schema": "ldl-scratch-baseline-v1", "target": target, "files": target_inventory}
    atomic_write(os.path.join(scratch, BASELINE_FILE), json.dumps(baseline, indent=2) + "\n")
    print(f"SCRATCH INIT PASS - files={len(baseline['files'])} scratch={scratch}")


def run_scratch_lint(target, scratch, through):
    lint = os.path.join(target, "tools", "lint.py")
    command = [sys.executable, lint]
    if through != "final":
        command += ["--through", through]
    command.append(scratch)
    result = subprocess.run(command, text=True, capture_output=True)
    if result.returncode:
        print(result.stdout + result.stderr, end="")
        raise SystemExit("scratch lint failed; promotion refused")


def promote(scratch, target, through):
    scratch = os.path.realpath(scratch)
    target = os.path.realpath(target)
    baseline_path = os.path.join(scratch, BASELINE_FILE)
    with open(baseline_path, encoding="utf-8") as handle:
        baseline = json.load(handle)
    if baseline.get("schema") != "ldl-scratch-baseline-v1" or baseline.get("target") != target:
        raise SystemExit("scratch baseline target/schema mismatch")
    expected = baseline.get("files")
    current = inventory(target)
    if current != expected:
        changed = sorted(rel for rel in set(current) | set(expected) if current.get(rel) != expected.get(rel))
        raise SystemExit("target changed since scratch-init; promotion refused: " + ", ".join(changed[:20]))
    candidate = inventory(scratch)
    missing = sorted(set(expected) - set(candidate))
    if missing:
        raise SystemExit("scratch deleted existing files; promotion refused: " + ", ".join(missing[:20]))
    changed = [rel for rel in sorted(candidate) if expected.get(rel) != candidate.get(rel)]
    tool_changes = [rel for rel in changed if is_root_tool(rel)]
    if tool_changes:
        raise SystemExit("scratch changed protected tool; promotion refused: " + ", ".join(tool_changes[:20]))
    control_changes = [rel for rel in changed if is_control_plane(rel)]
    if control_changes:
        raise SystemExit("scratch changed protected control plane; promotion refused: " + ", ".join(control_changes[:20]))
    frozen_evaluators = [rel for rel in changed if evaluation_frozen(target, rel)]
    if frozen_evaluators:
        raise SystemExit("scratch changed G1-frozen evaluator profile; promotion refused: " + ", ".join(frozen_evaluators[:20]))
    premature = [rel for rel in changed if STAGE_RANK[required_stage(rel)] > STAGE_RANK[through]]
    if premature:
        needed = required_stage(premature[0])
        raise SystemExit(f"scratch changed future phase file; {premature[0]} requires {needed}")
    for rel in expected:
        if inside_raw(rel) and candidate[rel]["sha256"] != expected[rel]["sha256"]:
            raise SystemExit(f"scratch mutated existing raw file; promotion refused: {rel}")
        if is_append_log(rel):
            with open(os.path.join(target, rel), "rb") as handle:
                original = handle.read()
            with open(os.path.join(scratch, rel), "rb") as handle:
                proposed = handle.read()
            if not proposed.startswith(original):
                kind = "ledger" if rel.endswith("cost-ledger.csv") else "log"
                raise SystemExit(f"scratch rewrote append-only {kind}; promotion refused: {rel}")
    run_scratch_lint(target, scratch, through)
    staged = []
    backups = {}
    replaced = []
    try:
        for rel in changed:
            destination = os.path.join(target, rel)
            os.makedirs(os.path.dirname(destination), exist_ok=True)
            if os.path.exists(destination):
                with open(destination, "rb") as handle:
                    backups[destination] = handle.read()
            else:
                backups[destination] = None
            descriptor, temporary = tempfile.mkstemp(prefix=".ldl-promote-", dir=os.path.dirname(destination))
            os.close(descriptor)
            shutil.copyfile(os.path.join(scratch, rel), temporary)
            staged.append((temporary, destination))
        for temporary, destination in staged:
            os.replace(temporary, destination)
            replaced.append(destination)
    except Exception:
        for destination in reversed(replaced):
            original = backups[destination]
            if original is None:
                os.path.exists(destination) and os.unlink(destination)
            else:
                atomic_write(destination, original, binary=True)
        raise
    finally:
        for temporary, _ in staged:
            if os.path.exists(temporary):
                os.unlink(temporary)
    print(f"PROMOTION PASS - changed_files={len(changed)} through={through}")


def safe_raw_destination(project, rel):
    if os.path.isabs(rel) or not rel or rel.startswith("."):
        raise SystemExit("raw destination must be a visible relative path")
    raw = os.path.realpath(os.path.join(project, "raw"))
    target = os.path.realpath(os.path.join(raw, rel))
    if os.path.commonpath([raw, target]) != raw:
        raise SystemExit("raw destination escapes project raw/")
    current = raw
    for part in os.path.relpath(os.path.dirname(target), raw).split(os.sep):
        if part == ".":
            continue
        current = os.path.join(current, part)
        if os.path.islink(current):
            raise SystemExit("raw destination traverses a symlink")
    return target


def raw_put(project, rel, source):
    project = os.path.realpath(project)
    if not os.path.isfile(source):
        raise SystemExit(f"source file missing: {source}")
    target = safe_raw_destination(project, rel)
    with open(source, "rb") as handle:
        data = handle.read()
    atomic_write(target, data, binary=True, exclusive=True)
    print(f"RAW PUT PASS - path={os.path.relpath(target, project)} bytes={len(data)} sha256={sha256(target)}")


SECRET_PATTERNS = (
    re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    re.compile(r"\b(?:sk|rk|pk)-[A-Za-z0-9_-]{20,}\b"),
    re.compile(r"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b"),
    re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}\b"),
    re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{20,}\b"),
    re.compile(r"\b(?:API[_-]?KEY|TOKEN|PASSWORD|SECRET)\s*[:=]\s*[^\s]{8,}", re.I),
    re.compile(r"\bBearer\s+[A-Za-z0-9._~+/-]{16,}", re.I),
)


def prompt_log(project, session, source, actor="human", timestamp=None):
    project = os.path.realpath(project)
    if actor not in {"human", "agent"}:
        raise SystemExit("prompt actor must be human or agent")
    if not re.fullmatch(r"[A-Za-z0-9._-]{1,128}", str(session)):
        raise SystemExit("prompt session must be a bounded visible identifier")
    if not os.path.isfile(source):
        raise SystemExit("prompt source file missing")
    with open(source, encoding="utf-8") as handle:
        prompt = handle.read()
    if not prompt.strip():
        raise SystemExit("prompt source is empty")
    if any(pattern.search(prompt) for pattern in SECRET_PATTERNS):
        raise SystemExit("prompt contains a secret-like value; nothing was logged")
    timestamp = timestamp or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    if not valid_timestamp(timestamp):
        raise SystemExit("prompt timestamp invalid or in the future")
    record = {
        "schema": "ldl-prompt-log-v1", "timestamp": timestamp, "session": session,
        "actor": actor, "prompt_sha256": hashlib.sha256(prompt.encode("utf-8")).hexdigest(),
        "prompt": prompt,
    }
    target = os.path.join(project, "logs", "prompts.jsonl")
    os.makedirs(os.path.dirname(target), exist_ok=True)
    with open(target, "a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n")
    print(f"PROMPT LOG PASS - session={session} actor={actor} bytes={len(prompt.encode('utf-8'))}")


def markdown_table(text, title, columns):
    match = re.search(rf"^##\s+{re.escape(title)}\s*$([\s\S]*?)(?=^##\s+|\Z)", text, re.M | re.I)
    if not match:
        raise SystemExit(f"required section missing: {title}")
    lines = [line.strip() for line in match.group(1).splitlines() if line.strip().startswith("|")]
    if len(lines) < 2:
        raise SystemExit(f"table missing: {title}")
    split = lambda line: [cell.strip() for cell in line.strip("|").split("|")]
    if split(lines[0]) != columns:
        raise SystemExit(f"wrong columns in {title}")
    rows = []
    for line in lines[2:]:
        cells = split(line)
        if len(cells) != len(columns):
            raise SystemExit(f"malformed row in {title}")
        rows.append(dict(zip(columns, cells)))
    return match, rows


def sync_verdicts(project):
    project = os.path.realpath(project)
    req_path = os.path.join(project, "01_REQUIREMENTS.md")
    ver_path = os.path.join(project, "06_VERIFICATION.md")
    with open(req_path, encoding="utf-8") as handle:
        requirements = handle.read()
    with open(ver_path, encoding="utf-8") as handle:
        verification = handle.read()
    _, req_rows = markdown_table(requirements, "Requirements ledger", REQ_COLUMNS)
    req_ids = [row["Requirement ID"] for row in req_rows]
    if not req_ids or len(req_ids) != len(set(req_ids)) or any(not re.fullmatch(r"R(?:EQ)?-[A-Za-z0-9._-]+", item) for item in req_ids):
        raise SystemExit("requirements contain missing, duplicate, or invalid IDs")
    match, verdict_rows = markdown_table(verification, "Requirement verdicts", VERDICT_COLUMNS)
    existing = {row["Requirement ID"]: row for row in verdict_rows}
    if len(existing) != len(verdict_rows):
        raise SystemExit("verification contains duplicate requirement IDs")
    table = ["| " + " | ".join(VERDICT_COLUMNS) + " |", "|---|---|---|"]
    for req_id in req_ids:
        row = existing.get(req_id, {"Requirement ID": req_id, "Verdict": "NOT_RUN", "Evidence": "not executed"})
        table.append("| " + " | ".join(row[column] for column in VERDICT_COLUMNS) + " |")
    body = verification[match.start(1):match.end(1)]
    body_lines = body.splitlines()
    prefix = []
    for line in body_lines:
        if line.strip().startswith("|"):
            break
        prefix.append(line)
    replacement = "\n" + "\n".join(prefix + table) + "\n"
    verification = verification[:match.start(1)] + replacement + verification[match.end(1):]
    atomic_write(ver_path, verification)
    print(f"SYNC VERDICTS PASS - requirements={len(req_ids)}")


def valid_timestamp(value):
    try:
        parsed = datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except (TypeError, ValueError):
        return False
    return parsed <= datetime.now(timezone.utc)


def version_tuple(value):
    if not re.fullmatch(r"v\d+(?:\.\d+)*", str(value)):
        return ()
    return tuple(int(part) for part in value[1:].split("."))


def project_file(project, rel):
    project = os.path.realpath(project)
    if not isinstance(rel, str) or not rel or os.path.isabs(rel):
        raise ValueError("evidence path must be relative")
    target = os.path.realpath(os.path.join(project, rel))
    if os.path.commonpath([project, target]) != project or not os.path.isfile(target):
        raise ValueError(f"evidence path missing or escapes project: {rel}")
    return target


def validate_gate_decision(project, decision, verify_evidence=True, contract_candidate=None):
    required = {"schema", "gate", "contract_version", "verdict", "approval_mode", "approver", "decided_at", "reason", "evidence"}
    if not isinstance(decision, dict) or set(decision) != required:
        raise ValueError("gate decision keys must exactly match the v1 schema")
    if decision["schema"] != GATE_SCHEMA or decision["gate"] not in GATES:
        raise ValueError("gate decision schema/gate invalid")
    if not re.fullmatch(r"v\d+(?:\.\d+)*", str(decision["contract_version"])):
        raise ValueError("gate decision contract_version invalid")
    if decision["verdict"] not in {"PASS", "HOLD", "FAIL", "REOPEN"}:
        raise ValueError("gate decision verdict invalid")
    if decision["approval_mode"] not in {"human", "delegated-agent"}:
        raise ValueError("gate decision approval_mode invalid")
    if not all(isinstance(decision[field], str) and decision[field].strip() for field in ("approver", "reason")):
        raise ValueError("gate decision approver/reason missing")
    if not valid_timestamp(decision["decided_at"]):
        raise ValueError("gate decision decided_at invalid or in the future")
    if not isinstance(decision["evidence"], list) or not decision["evidence"]:
        raise ValueError("gate decision evidence must be a nonempty list")
    for index, item in enumerate(decision["evidence"]):
        if not isinstance(item, dict) or set(item) != {"path", "sha256"}:
            raise ValueError(f"gate decision evidence {index} must be path+sha256")
        if not re.fullmatch(r"[0-9a-f]{64}", str(item["sha256"])):
            raise ValueError(f"gate decision evidence hash invalid: {item['path']}")
        if verify_evidence:
            target = contract_candidate if item["path"] == "00_CONTRACT.md" and contract_candidate else project_file(project, item["path"])
            if sha256(target) != item["sha256"]:
                raise ValueError(f"gate decision evidence hash mismatch: {item['path']}")
    if decision["verdict"] == "REOPEN":
        paths = [item["path"] for item in decision["evidence"]]
        if len(paths) != 2 or paths.count("00_CONTRACT.md") != 1:
            raise ValueError("REOPEN requires exactly new contract and prior FAIL decision evidence")
        prior_rel = next(path for path in paths if path != "00_CONTRACT.md")
        prior_path = project_file(project, prior_rel)
        raw_root = os.path.realpath(os.path.join(project, "raw"))
        if (not prior_rel.endswith(".json")
                or os.path.commonpath([raw_root, os.path.realpath(prior_path)]) != raw_root):
            raise ValueError("REOPEN prior FAIL decision must be immutable under project raw/")
        try:
            with open(prior_path, encoding="utf-8") as handle:
                prior = json.load(handle)
        except (OSError, json.JSONDecodeError) as exc:
            raise ValueError(f"REOPEN prior FAIL decision unreadable: {exc}")
        if (not isinstance(prior, dict) or prior.get("verdict") != "FAIL"
                or prior.get("gate") != decision["gate"]
                or version_tuple(prior.get("contract_version", "")) >= version_tuple(decision["contract_version"])):
            raise ValueError("REOPEN prior decision must be lower-version FAIL for the same gate")
        validate_gate_decision(project, prior, verify_evidence=bool(contract_candidate))
    return True


def load_decision(project, decision_path, contract_candidate=None):
    try:
        with open(decision_path, encoding="utf-8") as handle:
            decision = json.load(handle)
    except (OSError, json.JSONDecodeError) as exc:
        raise SystemExit(f"gate decision unreadable: {exc}")
    try:
        validate_gate_decision(project, decision, contract_candidate=contract_candidate)
    except ValueError as exc:
        raise SystemExit(f"GATE DECISION FAIL - {exc}")
    return decision


def gate_validate(project, decision_path):
    decision = load_decision(os.path.realpath(project), decision_path)
    print(f"GATE DECISION PASS - gate={decision['gate']} verdict={decision['verdict']} contract={decision['contract_version']}")


def workspace_root(project):
    current = os.path.realpath(project)
    while True:
        if os.path.isfile(os.path.join(current, ".ldl-version")):
            return current
        parent = os.path.dirname(current)
        if parent == current:
            raise SystemExit("project is not inside an LDL workspace")
        current = parent


def validate_reopen_poststate(project, revised_contract, raw_rel, payload, progress, log):
    root = workspace_root(project)
    parent = tempfile.mkdtemp(prefix="ldl-reopen-poststate-")
    proposed = os.path.join(parent, "workspace")
    try:
        shutil.copytree(root, proposed, ignore=shutil.ignore_patterns(*SKIP_DIRS))
        proposed_project = os.path.join(proposed, os.path.relpath(project, root))
        with open(revised_contract, "rb") as handle:
            atomic_write(os.path.join(proposed_project, "00_CONTRACT.md"), handle.read(), binary=True)
        atomic_write(os.path.join(proposed_project, raw_rel), payload, exclusive=True)
        atomic_write(os.path.join(proposed_project, "PROGRESS.md"), progress)
        atomic_write(os.path.join(proposed_project, "logs", "log.md"), log)
        run_scratch_lint(root, proposed, "P0")
    finally:
        shutil.rmtree(parent, ignore_errors=True)


def gate_apply(project, decision_path, revised_contract=None):
    project = os.path.realpath(project)
    if not revised_contract:
        try:
            with open(decision_path, encoding="utf-8") as handle:
                unvalidated = json.load(handle)
        except (OSError, json.JSONDecodeError):
            unvalidated = {}
        if isinstance(unvalidated, dict) and unvalidated.get("verdict") == "REOPEN":
            raise SystemExit("REOPEN requires gate-reopen with a revised contract file")
    if revised_contract:
        revised_contract = os.path.realpath(revised_contract)
        if not os.path.isfile(revised_contract):
            raise SystemExit("revised contract file missing")
    decision = load_decision(project, decision_path, revised_contract)
    reopening = decision["verdict"] == "REOPEN"
    if revised_contract and not reopening:
        raise SystemExit("revised contract file is valid only for REOPEN")
    progress_path = os.path.join(project, "PROGRESS.md")
    log_path = os.path.join(project, "logs", "log.md")
    contract_path = os.path.join(project, "00_CONTRACT.md")
    with open(progress_path, encoding="utf-8") as handle:
        progress = handle.read()
    with open(log_path, encoding="utf-8") as handle:
        log = handle.read()
    with open(revised_contract or contract_path, encoding="utf-8") as handle:
        contract = handle.read()
    version_match = re.search(r"^-\s*Contract version:\s*(\S+)\s*$", contract, re.M)
    mode_match = re.search(r"^-\s*Approval mode:\s*(\S+)\s*$", contract, re.M)
    if not version_match or version_match.group(1) != decision["contract_version"]:
        raise SystemExit("gate decision contract version does not match active contract")
    if not mode_match or mode_match.group(1) != decision["approval_mode"]:
        raise SystemExit("gate decision approval mode does not match active contract")
    phase_match, phase_rows = markdown_table(progress, "Phase progress", ["Phase", "Status", "Date", "Deliverable"])
    phases = {row["Phase"]: row["Status"].lower() for row in phase_rows}
    if decision["verdict"] == "PASS":
        missing = [phase for phase in GATE_PHASES[decision["gate"]] if phases.get(phase) != "done"]
        if missing:
            raise SystemExit("gate PASS blocked by incomplete phases: " + ", ".join(missing))
        for prior in GATES[:GATES.index(decision["gate"])]:
            if not re.search(rf"^\|\s*{prior}\s*\|\s*PASS\s*\|", progress, re.M):
                raise SystemExit(f"gate PASS blocked by prior gate: {prior}")
    timestamp = decision["decided_at"].replace(":", "").replace("-", "")
    filename = f"{decision['gate'].lower()}-{decision['contract_version']}-{timestamp}.json"
    raw_rel = os.path.join("raw", "gate-decisions", filename)
    raw_path = safe_raw_destination(project, os.path.join("gate-decisions", filename))
    if os.path.exists(raw_path):
        raise SystemExit("gate decision artifact already exists")
    gate_match, gate_rows = markdown_table(progress, "Gate ledger", GATE_COLUMNS)
    rows = []
    found = False
    if reopening:
        failed_row = next((row for row in gate_rows if row["Gate"] == decision["gate"]), None)
        if not failed_row or failed_row["Verdict"] != "FAIL":
            state = failed_row["Verdict"] if failed_row else "missing"
            raise SystemExit(f"gate REOPEN requires FAIL state, got {state}")
        if version_tuple(decision["contract_version"]) <= version_tuple(failed_row["Contract version"]):
            raise SystemExit("gate REOPEN requires a higher contract version")
        match = re.search(r"\]\(([^)]+)\)", failed_row["Evidence"])
        prior_rel = match.group(1) if match else ""
        evidence_paths = {item["path"] for item in decision["evidence"]}
        if "00_CONTRACT.md" not in evidence_paths or not prior_rel or prior_rel not in evidence_paths:
            raise SystemExit("gate REOPEN requires new contract and prior FAIL decision evidence")
        try:
            with open(project_file(project, prior_rel), encoding="utf-8") as handle:
                prior = json.load(handle)
        except (OSError, json.JSONDecodeError, ValueError) as exc:
            raise SystemExit(f"gate REOPEN prior FAIL decision invalid: {exc}")
        expected_prior = {
            "gate": failed_row["Gate"], "contract_version": failed_row["Contract version"],
            "verdict": "FAIL", "approval_mode": failed_row["Approval mode"],
            "approver": failed_row["Approver"], "decided_at": failed_row["Approved at"],
        }
        if any(prior.get(field) != value for field, value in expected_prior.items()):
            raise SystemExit("gate REOPEN prior FAIL decision does not match failed gate row")
    for row in gate_rows:
        if reopening:
            row = dict(row)
            row.update({
                "Verdict": "PENDING",
                "Contract version": decision["contract_version"],
                "Approval mode": decision["approval_mode"],
                "Approver": decision["approver"] if row["Gate"] == decision["gate"] else "",
                "Approved at": decision["decided_at"] if row["Gate"] == decision["gate"] else "",
                "Evidence": f"[decision]({raw_rel})" if row["Gate"] == decision["gate"] else "",
            })
            found = found or row["Gate"] == decision["gate"]
            rows.append(row)
            continue
        if row["Gate"] == decision["gate"]:
            if row["Verdict"] not in {"PENDING", "HOLD"}:
                raise SystemExit(f"gate is not applicable from state {row['Verdict']}")
            row = dict(row)
            row.update({
                "Verdict": "PENDING" if reopening else decision["verdict"],
                "Contract version": decision["contract_version"],
                "Approval mode": decision["approval_mode"],
                "Approver": decision["approver"],
                "Approved at": decision["decided_at"],
                "Evidence": f"[decision]({raw_rel})",
            })
            found = True
        rows.append(row)
    if not found:
        raise SystemExit("gate row missing")
    table = ["| " + " | ".join(GATE_COLUMNS) + " |", "|---|---|---|---|---|---|---|"]
    table += ["| " + " | ".join(row[column] for column in GATE_COLUMNS) + " |" for row in rows]
    body = progress[gate_match.start(1):gate_match.end(1)]
    body_lines = body.splitlines()
    first = next((index for index, line in enumerate(body_lines) if line.strip().startswith("|")), len(body_lines))
    last = first
    while last < len(body_lines) and body_lines[last].strip().startswith("|"):
        last += 1
    prefix = body_lines[:first]
    suffix = body_lines[last:]
    replacement = "\n" + "\n".join(prefix + table + suffix) + "\n"
    progress = progress[:gate_match.start(1)] + replacement + progress[gate_match.end(1):]
    event = f"GATE-{decision['verdict']}: {decision['gate']} contract={decision['contract_version']}"
    if re.search(rf"^{re.escape(event)}$", log, re.M):
        raise SystemExit("duplicate gate event refused")
    log += event + "\n"
    payload = json.dumps(decision, indent=2, ensure_ascii=False) + "\n"
    if reopening and revised_contract:
        validate_reopen_poststate(project, revised_contract, raw_rel, payload, progress, log)
    with open(progress_path, "rb") as handle:
        original_progress = handle.read()
    with open(log_path, "rb") as handle:
        original_log = handle.read()
    with open(contract_path, "rb") as handle:
        original_contract = handle.read()
    raw_created = False
    try:
        atomic_write(raw_path, payload, exclusive=True)
        raw_created = True
        if reopening and revised_contract:
            with open(revised_contract, "rb") as handle:
                atomic_write(contract_path, handle.read(), binary=True)
        atomic_write(progress_path, progress)
        atomic_write(log_path, log)
    except Exception:
        if raw_created and os.path.exists(raw_path):
            os.unlink(raw_path)
        atomic_write(progress_path, original_progress, binary=True)
        atomic_write(log_path, original_log, binary=True)
        atomic_write(contract_path, original_contract, binary=True)
        raise
    print(f"GATE APPLY PASS - gate={decision['gate']} verdict={decision['verdict']} artifact={raw_rel}")


def gate_reopen(project, revised_contract, decision_path):
    gate_apply(project, decision_path, revised_contract)


def main():
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("scratch-init"); p.add_argument("target"); p.add_argument("scratch")
    p = sub.add_parser("promote"); p.add_argument("scratch"); p.add_argument("target"); p.add_argument("--through", choices=["P0", "P3", "P4", "final"], default="final")
    p = sub.add_parser("raw-put"); p.add_argument("project"); p.add_argument("relative_path"); p.add_argument("source_file")
    p = sub.add_parser("sync-verdicts"); p.add_argument("project")
    p = sub.add_parser("gate-validate"); p.add_argument("project"); p.add_argument("decision")
    p = sub.add_parser("gate-apply"); p.add_argument("project"); p.add_argument("decision")
    p = sub.add_parser("gate-reopen"); p.add_argument("project"); p.add_argument("revised_contract"); p.add_argument("decision")
    p = sub.add_parser("prompt-log"); p.add_argument("project"); p.add_argument("session"); p.add_argument("source_file"); p.add_argument("--actor", choices=["human", "agent"], default="human")
    args = parser.parse_args()
    if args.command == "scratch-init": scratch_init(args.target, args.scratch)
    elif args.command == "promote": promote(args.scratch, args.target, args.through)
    elif args.command == "raw-put": raw_put(args.project, args.relative_path, args.source_file)
    elif args.command == "sync-verdicts": sync_verdicts(args.project)
    elif args.command == "gate-validate": gate_validate(args.project, args.decision)
    elif args.command == "gate-apply": gate_apply(args.project, args.decision)
    elif args.command == "gate-reopen": gate_reopen(args.project, args.revised_contract, args.decision)
    else: prompt_log(args.project, args.session, args.source_file, args.actor)


if __name__ == "__main__":
    main()
