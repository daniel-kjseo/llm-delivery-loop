#!/usr/bin/env python3
"""LDL v0.4 Ship-First MVP checks and phase-packet validator (stdlib only).

  lean.py verify <packet.json> [--root PROJECT_ROOT]

A packet carries handles, not embedded artifacts. Exit 0 means the packet is
bounded and every local artifact hash matches; exit 1 prints exact violations.
"""
import argparse
import csv
import hashlib
import ipaddress
import json
import os
import re
import sys
from datetime import datetime, timezone
from urllib.parse import urlsplit

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
    "Increment", "Experiment", "User journey", "Status", "Deterministic tests",
    "Rendered/browser", "Independent check", "Evidence",
]
RELEASE_COLUMNS = [
    "Release", "Verdict", "Increment", "Risk", "Instrumentation", "Feedback",
    "Rollback", "Live artifact", "Approver", "Released at", "Evidence",
]
EXPERIMENT_COLUMNS = [
    "Experiment", "Hypothesis", "Change", "Metric", "Status", "Evidence", "Decision",
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


def valid_utc_timestamp(value):
    if not isinstance(value, str) or not UTC_ISO.fullmatch(value):
        return False
    try:
        datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ")
    except ValueError:
        return False
    return True


def utc_datetime(value):
    return datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)


def valid_https_url(value):
    if not isinstance(value, str) or not value or re.search(r"[\s\\\x00-\x1f\x7f]", value):
        return False
    try:
        parsed = urlsplit(value)
        host = parsed.hostname
        port = parsed.port
    except (ValueError, UnicodeError):
        return False
    if parsed.scheme != "https" or not host or parsed.username is not None or parsed.password is not None:
        return False
    if port is not None and not 1 <= port <= 65535:
        return False
    if host.lower() == "localhost" or host.lower().endswith(".local"):
        return False
    ip_shaped = bool(re.fullmatch(r"[0-9.]+", host)) or ":" in host
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        if ip_shaped:
            return False
    else:
        if isinstance(address, ipaddress.IPv6Address) and address.ipv4_mapped:
            address = address.ipv4_mapped
        excluded = (
            address.is_multicast,
            address.is_private,
            address.is_loopback,
            address.is_link_local,
            address.is_unspecified,
            address.is_reserved,
        )
        if isinstance(address, ipaddress.IPv6Address):
            excluded += (address.is_site_local,)
        return address.is_global and not any(excluded)
    try:
        ascii_host = host.encode("idna").decode("ascii")
    except UnicodeError:
        return False
    labels = ascii_host.split(".")
    return (len(ascii_host) <= 253 and len(labels) >= 2
            and all(1 <= len(label) <= 63
                    and re.fullmatch(r"[A-Za-z0-9](?:[A-Za-z0-9-]*[A-Za-z0-9])?", label)
                    for label in labels))


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
    aggregate_limits = {"commands": 2000, "blockers": RELAY_SUMMARY_MAX_CHARS}
    for field, limit in aggregate_limits.items():
        if isinstance(packet.get(field), list):
            total = sum(len(value) for value in packet[field] if isinstance(value, str))
            if total > limit:
                errors.append(f"packet {field} aggregate exceeds {limit} chars")
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
                if not valid_utc_timestamp(row["timestamp"]):
                    return [], f"cost ledger row {number} timestamp must be UTC ISO-8601"
                _, evidence_error = _project_file(project_root, row["evidence"])
                if evidence_error:
                    return [], f"cost ledger row {number} evidence {evidence_error}"
                evidence_path = os.path.realpath(os.path.join(project_root, row["evidence"]))
                if evidence_path == os.path.realpath(path):
                    return [], f"cost ledger row {number} cannot cite the ledger itself"
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
    maker = evidence.get("maker")
    if not isinstance(maker, str) or not re.fullmatch(r"[A-Za-z0-9._-]+", maker):
        errors.append("MVP evidence maker must be a stable ID")
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
    artifact_targets = []
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
        if name == "independent":
            verifier = str(section.get("verifier", ""))
            if (not re.fullmatch(r"[A-Za-z0-9._-]+", verifier)
                    or verifier.lower() == str(maker).lower()
                    or re.search(r"maker|self|author|builder", verifier, re.I)):
                errors.append("MVP evidence independent verifier must be separated from maker")
        artifact = section.get("artifact")
        if not isinstance(artifact, dict) or set(artifact) != {"path", "sha256"}:
            errors.append(f"MVP evidence {name} artifact must be path+sha256")
            continue
        section_root = os.path.join(engineering, "evidence", name)
        target, target_error = _project_file(project_root, artifact["path"], section_root)
        if target_error:
            errors.append(f"MVP evidence {name} artifact {target_error}")
        elif os.path.getsize(target) == 0:
            errors.append(f"MVP evidence {name} artifact is empty")
        elif not re.fullmatch(r"[0-9a-f]{64}", str(artifact["sha256"])) or _sha256(target) != artifact["sha256"]:
            errors.append(f"MVP evidence {name} artifact hash mismatch")
        else:
            artifact_targets.append(target)
    if len(artifact_targets) != len(set(artifact_targets)):
        errors.append("MVP evidence deterministic/rendered/independent artifacts must be distinct")
    return errors


def verify_release_evidence(path, project_root, release_id, increment, live_url, released_at):
    errors = []
    try:
        with open(path, encoding="utf-8") as handle:
            evidence = json.load(handle)
    except (OSError, json.JSONDecodeError) as exc:
        return [f"release evidence is not valid JSON: {exc}"]
    if not isinstance(evidence, dict) or evidence.get("schema") != "ldl-release-evidence-v1":
        return ["release evidence schema must be ldl-release-evidence-v1"]
    if evidence.get("release") != release_id or evidence.get("increment") != increment:
        errors.append("release evidence identity mismatch")
    if evidence.get("live_url") != live_url or evidence.get("released_at") != released_at:
        errors.append("release evidence URL/time does not match release ledger")
    if not valid_https_url(evidence.get("live_url")):
        errors.append("release evidence live_url must be https")
    released_at = str(evidence.get("released_at", ""))
    if not valid_utc_timestamp(released_at):
        errors.append("release evidence released_at must be UTC ISO-8601")
    sections = {
        "smoke": ("PASS", "cases", "console_errors"),
        "telemetry": ("PASS", "event"),
        "rollback": ("READY", "command"),
        "feedback": ("READY", "channel"),
    }
    targets = []
    hashes = []
    release_root = os.path.join(project_root, "05_engineering", "evidence", "release")
    for name, (status, *fields) in sections.items():
        section = evidence.get(name)
        if not isinstance(section, dict) or section.get("status") != status:
            errors.append(f"release evidence {name} status must be {status}")
            continue
        for field in fields:
            value = section.get(field)
            if field == "cases" and (not isinstance(value, int) or value <= 0):
                errors.append("release evidence smoke cases must be positive")
            elif field == "console_errors" and value != 0:
                errors.append("release evidence console_errors must be 0")
            elif field not in {"cases", "console_errors"} and (not isinstance(value, str) or not value.strip()):
                errors.append(f"release evidence {name} missing {field}")
        artifact = section.get("artifact")
        if not isinstance(artifact, dict) or set(artifact) != {"path", "sha256"}:
            errors.append(f"release evidence {name} artifact must be path+sha256")
            continue
        target, target_error = _project_file(project_root, artifact["path"], release_root)
        if target_error:
            errors.append(f"release evidence {name} artifact {target_error}")
        elif os.path.getsize(target) == 0:
            errors.append(f"release evidence {name} artifact is empty")
        elif not re.fullmatch(r"[0-9a-f]{64}", str(artifact["sha256"])) or _sha256(target) != artifact["sha256"]:
            errors.append(f"release evidence {name} artifact hash mismatch")
        else:
            targets.append(target)
            hashes.append(artifact["sha256"])
    if len(targets) != len(set(targets)):
        errors.append("release evidence artifacts must be distinct")
    if len(hashes) != len(set(hashes)):
        errors.append("release evidence artifact hashes must be distinct")
    return errors


def verify_experiment_evidence(path, project_root, experiment_id, metric):
    try:
        with open(path, encoding="utf-8") as handle:
            evidence = json.load(handle)
    except (OSError, json.JSONDecodeError) as exc:
        return [f"experiment evidence is not valid JSON: {exc}"], ""
    errors = []
    if not isinstance(evidence, dict) or evidence.get("schema") != "ldl-experiment-evidence-v1":
        return ["experiment evidence schema must be ldl-experiment-evidence-v1"], ""
    if evidence.get("experiment") != experiment_id or evidence.get("metric") != metric:
        errors.append("experiment evidence identity/metric mismatch")
    if evidence.get("source") not in {"user-feedback", "behavior-telemetry", "user-interview"}:
        errors.append("experiment evidence source invalid")
    if not isinstance(evidence.get("observations"), int) or evidence["observations"] <= 0:
        errors.append("experiment evidence observations must be positive")
    if not isinstance(evidence.get("result"), str) or not evidence["result"].strip():
        errors.append("experiment evidence result missing")
    artifact = evidence.get("artifact")
    if not isinstance(artifact, dict) or set(artifact) != {"path", "sha256"}:
        errors.append("experiment evidence artifact must be path+sha256")
        return errors, ""
    root = os.path.join(project_root, "05_engineering", "evidence", "experiments")
    target, target_error = _project_file(project_root, artifact["path"], root)
    if target_error:
        errors.append(f"experiment evidence artifact {target_error}")
    elif os.path.getsize(target) == 0:
        errors.append("experiment evidence artifact is empty")
    elif not re.fullmatch(r"[0-9a-f]{64}", str(artifact["sha256"])) or _sha256(target) != artifact["sha256"]:
        errors.append("experiment evidence artifact hash mismatch")
    return errors, os.path.realpath(target) if not target_error else ""


def check(lint, proj):
    """L12 — v0.4 Ship-First release, feedback, economy, and MVP invariants."""
    contract_path = os.path.join(proj, "00_CONTRACT.md")
    progress_path = os.path.join(proj, "PROGRESS.md")
    verification_path = os.path.join(proj, "06_VERIFICATION.md")
    contract = _read(lint, contract_path, "L12")
    progress = _read(lint, progress_path, "L12")
    report = _read(lint, verification_path, "L12")
    crel = lint.rel(contract_path)
    prel = lint.rel(progress_path)

    delivery = lint.section_text(contract, "Delivery profile")
    launch = lint.section_text(contract, "Launch brief")
    economy = lint.section_text(contract, "Execution economy")
    delivery_mode = ""
    if not delivery:
        lint.err("L12", f"{crel}: Delivery profile missing")
    else:
        delivery_mode = lint.scalar_field(delivery, "Delivery mode")
        if delivery_mode not in {"startup-reversible", "gated-high-risk"}:
            lint.err("L12", f"{crel}: Delivery mode must be startup-reversible or gated-high-risk")
        if lint.scalar_field(delivery, "First executable increment") != "MVP-1":
            lint.err("L12", f"{crel}: First executable increment must be MVP-1")
        if lint.scalar_field(delivery, "Release strategy") != "ship-first":
            lint.err("L12", f"{crel}: Release strategy must be ship-first")
    launch_fields = ("Target user", "Problem", "Smallest value journey", "Launch metric", "Feedback channel", "Kill criteria", "Timebox", "Risk", "Rollback")
    if not launch:
        lint.err("L12", f"{crel}: Launch brief missing")
    else:
        for field in launch_fields:
            if not lint.substantive_cell(lint.scalar_field(launch, field)):
                lint.err("L12", f"{crel}: Launch brief field missing - {field}")
        risk = lint.scalar_field(launch, "Risk")
        expected_risk = "low-reversible" if delivery_mode == "startup-reversible" else "high-risk"
        if delivery_mode and risk != expected_risk:
            lint.err("L12", f"{crel}: Launch brief Risk must be {expected_risk}")
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

    experiment_rows = lint.table_rows(progress, "Experiment ledger", EXPERIMENT_COLUMNS, "L12", prel)
    experiment_ids = [row["Experiment"] for row in experiment_rows]
    if len(experiment_ids) != len(set(experiment_ids)):
        lint.err("L12", f"{prel}: duplicate experiment ID")
    experiments = {row["Experiment"]: row for row in experiment_rows}
    experiment_artifacts = []
    for row in experiment_rows:
        if row["Status"] not in {"NOT_RUN", "RUNNING", "MEASURED", "HOLD"}:
            lint.err("L12", f"{prel}: invalid experiment status - {row['Experiment']} {row['Status']}")
        if row["Decision"] not in {"PENDING", "ITERATE", "EXPAND", "PIVOT", "STOP"}:
            lint.err("L12", f"{prel}: invalid experiment decision - {row['Experiment']} {row['Decision']}")
        if row["Status"] == "MEASURED":
            for field in ("Hypothesis", "Change", "Metric"):
                if not lint.substantive_cell(row[field]):
                    lint.err("L12", f"{prel}: measured experiment missing {field} - {row['Experiment']}")
            if row["Decision"] == "PENDING":
                lint.err("L12", f"{prel}: measured experiment requires a decision - {row['Experiment']}")
            target = lint.local_link_target(proj, row["Evidence"])
            experiment_root = os.path.realpath(os.path.join(proj, "05_engineering", "evidence", "experiments"))
            if (not target or target.startswith(("http://", "https://", "mailto:")) or not os.path.isfile(target)
                    or os.path.commonpath([experiment_root, os.path.realpath(target)]) != experiment_root
                    or os.path.getsize(target) == 0):
                lint.err("L12", f"{prel}: measured experiment missing primary evidence - {row['Experiment']}")
            else:
                evidence_errors, artifact_target = verify_experiment_evidence(target, proj, row["Experiment"], row["Metric"])
                for error in evidence_errors:
                    lint.err("L12", f"{prel}: {error} - {row['Experiment']}")
                if artifact_target and not evidence_errors:
                    experiment_artifacts.append(artifact_target)
    if len(experiment_artifacts) != len(set(experiment_artifacts)):
        lint.err("L12", f"{prel}: measured experiments must not reuse primary artifacts")

    rows = lint.table_rows(progress, "Increment ledger", INCREMENT_COLUMNS, "L12", prel)
    increment_ids = [row["Increment"] for row in rows]
    if len(increment_ids) != len(set(increment_ids)):
        lint.err("L12", f"{prel}: duplicate increment ID")
    if not rows or rows[0]["Increment"] != "MVP-1":
        lint.err("L12", f"{prel}: first increment must be MVP-1")
    elif rows[0]["Experiment"] != "LAUNCH":
        lint.err("L12", f"{prel}: MVP-1 experiment must be LAUNCH")
    allowed = {"PENDING", "RED", "GREEN", "PASS", "HOLD", "FAIL"}
    consumed_experiments = []
    post_mvp_artifacts = []
    post_mvp_pass_rows = []
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
                if row["Increment"] == "MVP-1":
                    for error in verify_mvp_evidence(target, proj, row["Increment"]):
                        lint.err("L12", f"{prel}: {error} - {row['Increment']}")
                else:
                    post_mvp_pass_rows.append(row)
                    increment_root = os.path.realpath(os.path.join(proj, "05_engineering", "evidence", "increments"))
                    if (os.path.commonpath([increment_root, os.path.realpath(target)]) != increment_root
                            or os.path.getsize(target) == 0):
                        lint.err("L12", f"{prel}: post-MVP increment requires its own primary artifact - {row['Increment']}")
                    else:
                        post_mvp_artifacts.append(os.path.realpath(target))
                    experiment = experiments.get(row["Experiment"])
                    if (not experiment or experiment["Status"] != "MEASURED"
                            or experiment["Decision"] not in {"ITERATE", "EXPAND"}):
                        lint.err("L12", f"{prel}: PASS increment requires measured experiment signal - {row['Increment']}")
                    else:
                        consumed_experiments.append(row["Experiment"])
    if len(post_mvp_artifacts) != len(set(post_mvp_artifacts)):
        lint.err("L12", f"{prel}: post-MVP PASS increments must use distinct primary artifacts")
    if len(consumed_experiments) != len(set(consumed_experiments)):
        lint.err("L12", f"{prel}: each measured experiment can authorize only one PASS increment")

    phase_rows = lint.table_rows(progress, "Phase progress", ["Phase", "Status", "Date", "Deliverable"], "L12", prel)
    phase_status = {row["Phase"]: row["Status"].lower() for row in phase_rows}
    release_rows = lint.table_rows(progress, "Release ledger", RELEASE_COLUMNS, "L12", prel)
    release_ids = [row["Release"] for row in release_rows]
    if len(release_ids) != len(set(release_ids)):
        lint.err("L12", f"{prel}: duplicate release ID")
    gate_columns = ["Gate", "Verdict", "Contract version", "Approval mode", "Approver", "Approved at", "Evidence"]
    gate_rows = lint.table_rows(progress, "Gate ledger", gate_columns, "L12", prel)
    gates = {row["Gate"]: row for row in gate_rows}
    increments = {row["Increment"]: row for row in rows}
    for row in release_rows:
        if row["Verdict"] not in {"PENDING", "PASS", "HOLD", "FAIL"}:
            lint.err("L12", f"{prel}: invalid release verdict - {row['Release']} {row['Verdict']}")
            continue
        if row["Verdict"] != "PASS":
            continue
        if gates.get("G1", {}).get("Verdict") != "PASS":
            lint.err("L12", f"{prel}: release PASS requires G1 PASS")
        required_launch_phases = ("P0 contract", "P1 requirements", "P2 structure", "P4 scoping")
        missing_phases = [phase for phase in required_launch_phases if phase_status.get(phase) != "done"]
        if missing_phases:
            lint.err("L12", f"{prel}: release PASS requires launch documents done - {', '.join(missing_phases)}")
        increment = increments.get(row["Increment"])
        if not increment or increment["Status"] != "PASS":
            lint.err("L12", f"{prel}: release PASS requires increment PASS - {row['Increment']}")
        if any(row[field] != "PASS" for field in ("Instrumentation", "Feedback", "Rollback")):
            lint.err("L12", f"{prel}: release PASS requires instrumentation/feedback/rollback PASS")
        if not valid_https_url(row["Live artifact"]):
            lint.err("L12", f"{prel}: release PASS requires https live artifact")
        g1_approver = gates.get("G1", {}).get("Approver", "")
        if not lint.substantive_cell(row["Approver"]) or row["Approver"] != g1_approver:
            lint.err("L12", f"{prel}: release PASS approver must match G1 approver")
        if not valid_utc_timestamp(row["Released at"]):
            lint.err("L12", f"{prel}: release PASS Released at must be UTC ISO-8601")
        elif utc_datetime(row["Released at"]) > datetime.now(timezone.utc):
            lint.err("L12", f"{prel}: release PASS Released at cannot be in the future")
        expected_risk = "low-reversible" if delivery_mode == "startup-reversible" else "high-risk"
        if row["Risk"] != expected_risk:
            lint.err("L12", f"{prel}: release risk does not match delivery mode")
        if delivery_mode == "gated-high-risk" and gates.get("G4", {}).get("Verdict") != "PASS":
            lint.err("L12", f"{prel}: high-risk release requires G4 PASS")
        target = lint.local_link_target(proj, row["Evidence"])
        release_root = os.path.realpath(os.path.join(proj, "05_engineering", "evidence"))
        if (not target or target.startswith(("http://", "https://", "mailto:")) or not os.path.isfile(target)
                or os.path.commonpath([release_root, os.path.realpath(target)]) != release_root):
            lint.err("L12", f"{prel}: release PASS missing local evidence - {row['Release']}")
        else:
            for error in verify_release_evidence(target, proj, row["Release"], row["Increment"], row["Live artifact"], row["Released at"]):
                lint.err("L12", f"{prel}: {error} - {row['Release']}")

    mvp_released = any(row["Verdict"] == "PASS" and row["Increment"] == "MVP-1" for row in release_rows)
    mvp_pass = increments.get("MVP-1", {}).get("Status") == "PASS"
    for row in post_mvp_pass_rows:
        if not mvp_pass or not mvp_released:
            lint.err("L12", f"{prel}: post-MVP PASS increment requires MVP-1 Release PASS - {row['Increment']}")

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
