#!/usr/bin/env python3
"""LDL v0.4 Lean Working-MVP checks and phase-packet validator (stdlib only).

  lean.py verify <packet.json> [--root PROJECT_ROOT]

A packet carries handles, not embedded artifacts. Exit 0 means the packet is
bounded and every local artifact hash matches; exit 1 prints exact violations.
"""
import argparse
import csv
import hashlib
import json
import os
import re
import sys
from datetime import datetime

PACKET_MAX_BYTES = 8192
RELAY_SUMMARY_MAX_CHARS = 1500
CHECKER_SUMMARY_MAX_CHARS = 4000
PACKET_SCHEMA = "ldl-phase-packet-v1"
MVP_EVIDENCE_SCHEMA = "ldl-mvp-evidence-v1"
PACKET_KEYS = {"schema", "phase", "task", "summary", "requirements", "commands", "blockers", "artifacts"}
PACKET_ITEM_MAX_CHARS = 500
REQUIREMENT_ID = re.compile(r"R-[A-Za-z0-9._-]+$")
UTC_ISO = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
INCREMENT_COLUMNS = [
    "Increment", "User journey", "Status", "Deterministic tests",
    "Rendered/browser", "Independent check", "Evidence",
]
COST_COLUMNS = [
    "timestamp", "phase", "role", "model", "input_tokens", "output_tokens",
    "cache_tokens", "llm_calls", "checker_runs", "wall_seconds", "evidence",
]
TOKEN_NUMERIC_COLUMNS = [
    "input_tokens", "output_tokens", "cache_tokens", "llm_calls",
    "checker_runs", "wall_seconds",
]


def _sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify_packet(path, root=None):
    errors = []
    root = os.path.realpath(root or os.path.dirname(os.path.abspath(path)))
    try:
        size = os.path.getsize(path)
    except OSError as exc:
        return [f"packet unreadable: {exc}"]
    if size > PACKET_MAX_BYTES:
        errors.append(f"packet exceeds {PACKET_MAX_BYTES} bytes: {size}")
    try:
        with open(path, encoding="utf-8") as handle:
            packet = json.load(handle)
    except (OSError, json.JSONDecodeError) as exc:
        return errors + [f"packet is not valid JSON: {exc}"]
    if not isinstance(packet, dict):
        return errors + ["packet root must be an object"]
    unexpected = sorted(set(packet) - PACKET_KEYS)
    if unexpected:
        errors.append(f"packet has unexpected/embedded fields: {', '.join(unexpected)}")
    if packet.get("schema") != PACKET_SCHEMA:
        errors.append(f"packet schema must be {PACKET_SCHEMA}")
    for field in ("phase", "task", "summary"):
        if not isinstance(packet.get(field), str) or not packet[field].strip():
            errors.append(f"packet field missing: {field}")
    if isinstance(packet.get("summary"), str) and len(packet["summary"]) > RELAY_SUMMARY_MAX_CHARS:
        errors.append(f"summary exceeds {RELAY_SUMMARY_MAX_CHARS} chars")
    forbidden = {"content", "verbatim", "full_text", "report_text"}
    if forbidden.intersection(packet):
        errors.append("packet embeds verbatim/full content instead of artifact handles")
    for field in ("requirements", "commands", "blockers", "artifacts"):
        if not isinstance(packet.get(field), list):
            errors.append(f"packet field must be a list: {field}")
    for field in ("requirements", "commands", "blockers"):
        if isinstance(packet.get(field), list) and any(not isinstance(value, str) for value in packet[field]):
            errors.append(f"packet list accepts strings only: {field}")
    if isinstance(packet.get("requirements"), list):
        for value in packet["requirements"]:
            if isinstance(value, str) and not REQUIREMENT_ID.fullmatch(value):
                errors.append(f"packet requirement must be an ID, not embedded content: {value[:60]}")
    for field in ("commands", "blockers"):
        if isinstance(packet.get(field), list):
            for value in packet[field]:
                if isinstance(value, str) and len(value) > PACKET_ITEM_MAX_CHARS:
                    errors.append(f"packet {field} item exceeds {PACKET_ITEM_MAX_CHARS} chars")
    artifacts = packet.get("artifacts")
    if not isinstance(artifacts, list):
        artifacts = []
    for index, artifact in enumerate(artifacts):
        if not isinstance(artifact, dict):
            errors.append(f"artifact {index} must be an object")
            continue
        if set(artifact) != {"path", "sha256"}:
            errors.append(f"artifact {index} accepts path+sha256 only")
        rel = artifact.get("path")
        expected = artifact.get("sha256")
        if not isinstance(rel, str) or not rel or os.path.isabs(rel):
            errors.append(f"artifact {index} path must be relative")
            continue
        target = os.path.realpath(os.path.join(root, rel))
        try:
            if os.path.commonpath([root, target]) != root:
                errors.append(f"artifact {index} escapes packet root: {rel}")
                continue
        except ValueError:
            errors.append(f"artifact {index} escapes packet root: {rel}")
            continue
        if not os.path.isfile(target):
            errors.append(f"artifact {index} missing: {rel}")
            continue
        if not isinstance(expected, str) or not re.fullmatch(r"[0-9a-f]{64}", expected):
            errors.append(f"artifact {index} sha256 invalid: {rel}")
        elif _sha256(target) != expected:
            errors.append(f"artifact {index} hash mismatch: {rel}")
    return errors


def _read(lint, path, code):
    return lint.read_text(path, code) if os.path.isfile(path) else ""


def _project_file(root, rel, required_parent=None):
    if not isinstance(rel, str) or not rel or os.path.isabs(rel):
        return "", "path must be relative"
    target = os.path.realpath(os.path.join(root, rel))
    boundary = os.path.realpath(required_parent or root)
    try:
        if os.path.commonpath([boundary, target]) != boundary:
            return "", f"path escapes boundary: {rel}"
    except ValueError:
        return "", f"path escapes boundary: {rel}"
    if not os.path.isfile(target):
        return "", f"file missing: {rel}"
    return target, ""


def valid_cost_rows(path, project_root):
    """Return (valid rows, error). A decorative/garbage row is not telemetry."""
    try:
        with open(path, newline="", encoding="utf-8") as handle:
            reader = csv.DictReader(handle)
            if reader.fieldnames != COST_COLUMNS:
                return [], "cost ledger header invalid"
            rows = []
            for number, row in enumerate(reader, 2):
                if None in row:
                    return [], f"cost ledger row {number} has extra columns"
                if not any((value or "").strip() for value in row.values()):
                    continue
                if any(not (row.get(field) or "").strip() for field in ("timestamp", "phase", "role", "model", "evidence")):
                    return [], f"cost ledger row {number} missing identity/evidence"
                try:
                    values = [int(row[field]) for field in TOKEN_NUMERIC_COLUMNS]
                except (KeyError, TypeError, ValueError):
                    return [], f"cost ledger row {number} has non-integer metrics"
                if any(value < 0 for value in values):
                    return [], f"cost ledger row {number} has negative metrics"
                if not UTC_ISO.fullmatch(row["timestamp"]):
                    return [], f"cost ledger row {number} timestamp must be UTC ISO-8601"
                try:
                    datetime.strptime(row["timestamp"], "%Y-%m-%dT%H:%M:%SZ")
                except ValueError:
                    return [], f"cost ledger row {number} timestamp must be UTC ISO-8601"
                _, evidence_error = _project_file(project_root, row["evidence"])
                if evidence_error:
                    return [], f"cost ledger row {number} evidence {evidence_error}"
                rows.append(row)
            return rows, ""
    except OSError as exc:
        return [], f"cost ledger unreadable: {exc}"


def verify_mvp_evidence(path, project_root, increment):
    errors = []
    try:
        if os.path.getsize(path) == 0:
            return ["MVP evidence is empty"]
        with open(path, encoding="utf-8") as handle:
            evidence = json.load(handle)
    except (OSError, json.JSONDecodeError) as exc:
        return [f"MVP evidence is not valid JSON: {exc}"]
    if not isinstance(evidence, dict) or evidence.get("schema") != MVP_EVIDENCE_SCHEMA:
        return [f"MVP evidence schema must be {MVP_EVIDENCE_SCHEMA}"]
    if evidence.get("increment") != increment:
        errors.append(f"MVP evidence increment mismatch: {evidence.get('increment')}")
    if not isinstance(evidence.get("user_journey"), str) or not evidence["user_journey"].strip():
        errors.append("MVP evidence missing user_journey")
    sections = {
        "deterministic": ("command", "checks"),
        "rendered": ("instrument", "cases", "console_errors"),
        "independent": ("verifier", "target_mutation"),
    }
    engineering = os.path.join(project_root, "05_engineering")
    for name, fields in sections.items():
        section = evidence.get(name)
        if not isinstance(section, dict) or section.get("status") != "PASS":
            errors.append(f"MVP evidence {name} status must be PASS")
            continue
        for field in fields:
            if field not in section:
                errors.append(f"MVP evidence {name} missing {field}")
        for field in ("checks", "cases"):
            if field in fields and (not isinstance(section.get(field), int) or section[field] <= 0):
                errors.append(f"MVP evidence {name} invalid {field}")
        for field in ("console_errors", "target_mutation"):
            if field in fields and section.get(field) != 0:
                errors.append(f"MVP evidence {name} invalid {field}")
        for field in ("command", "instrument", "verifier"):
            if field in fields and (not isinstance(section.get(field), str) or not section[field].strip()):
                errors.append(f"MVP evidence {name} invalid {field}")
        artifact = section.get("artifact")
        if not isinstance(artifact, dict) or set(artifact) != {"path", "sha256"}:
            errors.append(f"MVP evidence {name} artifact must be path+sha256")
            continue
        target, target_error = _project_file(project_root, artifact["path"], engineering)
        if target_error:
            errors.append(f"MVP evidence {name} artifact {target_error}")
        elif not re.fullmatch(r"[0-9a-f]{64}", str(artifact["sha256"])) or _sha256(target) != artifact["sha256"]:
            errors.append(f"MVP evidence {name} artifact hash mismatch")
    return errors


def check(lint, proj):
    """L12 — v0.4 execution-economy and working-MVP invariants."""
    contract_path = os.path.join(proj, "00_CONTRACT.md")
    progress_path = os.path.join(proj, "PROGRESS.md")
    verification_path = os.path.join(proj, "06_VERIFICATION.md")
    contract = _read(lint, contract_path, "L12")
    progress = _read(lint, progress_path, "L12")
    report = _read(lint, verification_path, "L12")
    crel = lint.rel(contract_path)
    prel = lint.rel(progress_path)

    delivery = lint.section_text(contract, "Delivery profile")
    economy = lint.section_text(contract, "Execution economy")
    if not delivery:
        lint.err("L12", f"{crel}: Delivery profile missing")
    else:
        if lint.scalar_field(delivery, "Delivery mode") != "working-mvp":
            lint.err("L12", f"{crel}: Delivery mode must be working-mvp")
        if lint.scalar_field(delivery, "First executable increment") != "MVP-1":
            lint.err("L12", f"{crel}: First executable increment must be MVP-1")
    if not economy:
        lint.err("L12", f"{crel}: Execution economy missing")
    else:
        limits = {
            "Phase packet max bytes": PACKET_MAX_BYTES,
            "Relay summary max chars": RELAY_SUMMARY_MAX_CHARS,
            "Checker summary max chars": CHECKER_SUMMARY_MAX_CHARS,
            "Checker runs per increment": 1,
            "Correction reruns per increment": 1,
        }
        for field, ceiling in limits.items():
            value = lint.scalar_field(economy, field)
            try:
                number = int(value)
            except (TypeError, ValueError):
                lint.err("L12", f"{crel}: Execution economy field invalid - {field}")
                continue
            if number < 1 or number > ceiling:
                lint.err("L12", f"{crel}: Execution economy exceeds lean ceiling - {field} {number}>{ceiling}")
        ledger_rel = lint.scalar_field(economy, "Token/call ledger")
        if not ledger_rel:
            lint.err("L12", f"{crel}: Token/call ledger missing")
            ledger_path = ""
        else:
            ledger_path, ledger_path_error = _project_file(proj, ledger_rel, os.path.join(proj, "logs"))
            if ledger_path_error:
                lint.err("L12", f"{crel}: Token/call ledger {ledger_path_error}")

    rows = lint.table_rows(progress, "Increment ledger", INCREMENT_COLUMNS, "L12", prel)
    if not rows or rows[0]["Increment"] != "MVP-1":
        lint.err("L12", f"{prel}: first increment must be MVP-1")
    allowed = {"PENDING", "RED", "GREEN", "PASS", "HOLD", "FAIL"}
    for row in rows:
        if row["Status"] not in allowed:
            lint.err("L12", f"{prel}: invalid increment status - {row['Increment']} {row['Status']}")
        if row["Status"] == "PASS":
            if any(row[field] != "PASS" for field in ("Deterministic tests", "Rendered/browser", "Independent check")):
                lint.err("L12", f"{prel}: PASS increment requires tests/render/independent PASS - {row['Increment']}")
            if not lint.substantive_cell(row["User journey"]):
                lint.err("L12", f"{prel}: PASS increment missing user journey - {row['Increment']}")
            target = lint.local_link_target(proj, row["Evidence"])
            if not target or target.startswith(("http://", "https://", "mailto:")) or not os.path.isfile(target):
                lint.err("L12", f"{prel}: PASS increment missing local evidence - {row['Increment']}")
            elif os.path.commonpath([
                    os.path.realpath(os.path.join(proj, "05_engineering")),
                    os.path.realpath(target),
                ]) != os.path.realpath(os.path.join(proj, "05_engineering")):
                lint.err("L12", f"{prel}: PASS increment evidence must be under 05_engineering - {row['Increment']}")
            else:
                for error in verify_mvp_evidence(target, proj, row["Increment"]):
                    lint.err("L12", f"{prel}: {error} - {row['Increment']}")

    phase_rows = lint.table_rows(progress, "Phase progress", ["Phase", "Status", "Date", "Deliverable"], "L12", prel)
    completed = any(row["Phase"] == "P5+P6 increments" and row["Status"].lower() == "done" for row in phase_rows)
    finals = lint.section_text(report, "Final verdicts")
    product_pass = lint.scalar_field(finals, "Product") == "PASS"
    if completed or product_pass:
        mvp = next((row for row in rows if row["Increment"] == "MVP-1"), None)
        if not mvp or mvp["Status"] != "PASS":
            lint.err("L12", f"{prel}: Product PASS requires MVP-1 increment PASS")
        ledger_rel = lint.scalar_field(economy, "Token/call ledger") if economy else ""
        ledger_path, ledger_path_error = _project_file(proj, ledger_rel, os.path.join(proj, "logs")) if ledger_rel else ("", "")
        data_rows, ledger_error = valid_cost_rows(ledger_path, proj) if ledger_path else ([], ledger_path_error)
        if ledger_error:
            lint.err("L12", f"{crel}: {ledger_error}")
        if not data_rows:
            lint.err("L12", f"{prel}: completed delivery requires cost ledger data")


def main():
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    verify = sub.add_parser("verify")
    verify.add_argument("packet")
    verify.add_argument("--root")
    args = parser.parse_args()
    errors = verify_packet(args.packet, args.root)
    if errors:
        print(f"PACKET FAIL - {len(errors)} issue(s)")
        for error in errors:
            print("  " + error)
        return 1
    print("PACKET PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
