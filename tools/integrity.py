"""LDL v0.3 gate, evidence, safety, and verdict integrity checks.

This module intentionally checks structural invariants only. Whether evidence is
true or a recommendation is good remains a separated semantic judgment.
"""
import hashlib
import json
import os
import re
from datetime import datetime, timezone


GATE_COLUMNS = ["Gate", "Verdict", "Contract version", "Approval mode", "Approver", "Approved at", "Evidence"]
EVIDENCE_COLUMNS = ["Claim ID", "Label", "Claim", "Source artifact", "Captured at", "Scope/window", "Transform/reproducer", "Status"]
EVIDENCE_COLUMNS_V041 = ["Claim ID", "Evidence level", "Evidence domain", "Claim", "Source artifact", "Captured at", "Scope/window", "Transform/reproducer", "Claim lifecycle"]
DIMENSION_COLUMNS = ["Dimension ID", "Status", "Evidence"]
ACTION_COLUMNS = ["Action ID", "Impact dimensions", "Preconditions", "Approval tier", "Approval evidence", "Canary", "Rollback", "Ready"]
REQUIREMENT_COLUMNS = ["Requirement ID", "Verdict", "Evidence"]
REQUIREMENTS_LEDGER_COLUMNS = ["Requirement ID", "Type", "Priority", "Requirement", "Verification", "Source"]
PHASE_COLUMNS = ["Phase", "Status", "Date", "Deliverable"]
EVIDENCE_DOMAINS = {"SUPPLY", "DEMAND", "BEHAVIOR", "CAUSAL", "LEGAL", "OPERATIONAL"}


def _json(lint, path, code):
    try:
        with open(path, encoding="utf-8") as handle:
            return json.load(handle)
    except (OSError, json.JSONDecodeError) as exc:
        lint.err(code, f"{lint.rel(path)}: typed artifact unreadable - {exc}")
        return None


def _artifact(lint, proj, value, code, label):
    if not isinstance(value, dict) or set(value) != {"path", "sha256"}:
        lint.err(code, f"{lint.rel(proj)}: {label} must be path+sha256")
        return None
    rel, expected = value.get("path"), value.get("sha256")
    parts = rel.split("/") if isinstance(rel, str) else []
    if (not isinstance(rel, str) or os.path.isabs(rel) or not rel or rel.startswith(".")
            or any(part in {"", ".", ".."} for part in parts)
            or not re.fullmatch(r"[0-9a-f]{64}", str(expected))):
        lint.err(code, f"{lint.rel(proj)}: {label} path/hash invalid")
        return None
    lexical = os.path.abspath(os.path.join(proj, rel))
    target = os.path.realpath(os.path.join(proj, rel))
    raw = os.path.realpath(os.path.join(proj, "raw"))
    if (not _inside(lexical, os.path.join(proj, "raw")) or not _inside(target, raw)
            or not os.path.isfile(target) or os.path.islink(lexical)):
        lint.err(code, f"{lint.rel(proj)}: {label} must resolve under project raw/")
        return None
    digest = hashlib.sha256()
    with open(target, "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    if digest.hexdigest() != expected:
        lint.err(code, f"{lint.rel(proj)}: {label} hash mismatch")
        return None
    return os.path.realpath(target)


def check_v050(lint, proj, through):
    contract = _read(lint, os.path.join(proj, "00_CONTRACT.md"), "L13")
    delivery = lint.scalar_field(lint.section_text(contract, "Delivery profile"), "Delivery mode")
    if delivery != "portfolio-competition":
        return
    paths = {name: os.path.join(proj, name) for name in (
        "02_EVALUATION.json", "03_PORTFOLIO.json", "04_PREFLIGHT.json",
        "06_CAPABILITIES.json", "06_JUDGE_SCORES.json", "06_SUBMISSION.json")}
    docs = {name: _json(lint, path, "L13") for name, path in paths.items()}
    if any(value is None for value in docs.values()):
        return
    malformed_roots = [name for name, value in docs.items() if not isinstance(value, dict)]
    if malformed_roots:
        for name in malformed_roots:
            lint.err("L13", f"{lint.rel(paths[name])}: typed artifact root must be an object")
        return
    contract_version = lint.scalar_field(lint.section_text(contract, "Governance profile"), "Contract version")
    for name, document in docs.items():
        if document.get("contract_version") != contract_version:
            lint.err("L13", f"{lint.rel(paths[name])}: typed artifact contract version does not match active contract")

    portfolio = docs["03_PORTFOLIO.json"]
    preflight = docs["04_PREFLIGHT.json"]
    capabilities = docs["06_CAPABILITIES.json"]
    scores = docs["06_JUDGE_SCORES.json"]
    submission_state = docs["06_SUBMISSION.json"]
    floor = "P0"
    if isinstance(portfolio.get("candidates"), list) and portfolio["candidates"]:
        floor = "P3"
    if isinstance(preflight.get("dependencies"), list) and preflight["dependencies"]:
        floor = "P4"
    if ((isinstance(capabilities.get("capabilities"), list) and capabilities["capabilities"])
            or (isinstance(scores.get("rounds"), list) and scores["rounds"])
            or submission_state.get("secret_scan") != "NOT_RUN"):
        floor = "final"
    ranks = {"P0": 0, "P3": 3, "P4": 4, "final": 6}
    if ranks[through] < ranks[floor]:
        lint.err("L13", f"{lint.rel(proj)}: requested checkpoint {through} precedes current project state {floor}")
        return

    env = docs["02_EVALUATION.json"]
    if set(env) != {"schema", "contract_version", "evaluators", "submission_grammar", "process_trace_required", "secret_policy", "iteration_limits"} or env.get("schema") != "ldl-evaluation-environment-v1":
        lint.err("L13", f"{lint.rel(paths['02_EVALUATION.json'])}: evaluation environment schema invalid")
    evaluators = env.get("evaluators", [])
    evaluator_ids = []
    for item in evaluators if isinstance(evaluators, list) else []:
        required = {"id", "type", "perspective", "journey", "disqualification_rules", "blind_inputs", "cannot_judge", "rubric"}
        if not isinstance(item, dict) or set(item) != required:
            lint.err("L13", f"{lint.rel(paths['02_EVALUATION.json'])}: evaluator keys invalid")
            continue
        evaluator_ids.append(item["id"])
        if item["type"] not in {"deterministic", "ai-structural", "ai-practitioner", "actual-human", "agent-consumer"}:
            lint.err("L13", f"{lint.rel(paths['02_EVALUATION.json'])}: evaluator type invalid - {item['id']}")
        weights = [criterion.get("weight") for criterion in item["rubric"] if isinstance(criterion, dict)]
        if not item["rubric"] or any(not isinstance(weight, int) or weight < 0 for weight in weights) or sum(weights) != 100:
            lint.err("L13", f"{lint.rel(paths['02_EVALUATION.json'])}: evaluator rubric must total 100 - {item['id']}")
    if not evaluators or len(evaluator_ids) != len(set(evaluator_ids)):
        lint.err("L13", f"{lint.rel(paths['02_EVALUATION.json'])}: evaluators missing or duplicate")
    if env.get("secret_policy") != "values-never-enter-logs":
        lint.err("L13", f"{lint.rel(paths['02_EVALUATION.json'])}: secret policy must protect original logs")
    limits = env.get("iteration_limits", {})
    if (set(limits) != {"max_rounds", "minimum_delta", "max_wall_seconds"}
            or not isinstance(limits.get("max_rounds"), int) or not 1 <= limits["max_rounds"] <= 20
            or not isinstance(limits.get("minimum_delta"), (int, float)) or limits["minimum_delta"] < 0
            or not isinstance(limits.get("max_wall_seconds"), int) or limits["max_wall_seconds"] <= 0):
        lint.err("L13", f"{lint.rel(paths['02_EVALUATION.json'])}: bounded iteration limits invalid")
    evaluator_types = {item.get("type") for item in evaluators if isinstance(item, dict)}
    if not {"actual-human", "agent-consumer"}.issubset(evaluator_types):
        lint.err("L13", f"{lint.rel(paths['02_EVALUATION.json'])}: human taste and agent consumer evaluators required")

    if through == "P0":
        return
    if set(portfolio) != {"schema", "contract_version", "selection_status", "candidates"} or portfolio.get("schema") != "ldl-problem-portfolio-v1":
        lint.err("L13", f"{lint.rel(paths['03_PORTFOLIO.json'])}: portfolio schema invalid")
        return
    candidates = portfolio.get("candidates", [])
    ids, used_evidence, used_hashes, selected = [], set(), set(), 0
    if not isinstance(candidates, list) or len(candidates) < 3:
        lint.err("L13", f"{lint.rel(paths['03_PORTFOLIO.json'])}: portfolio requires at least three candidates")
        candidates = []
    for candidate in candidates:
        required = {"id", "problem", "status", "score", "evidence", "rejection_reason", "reopen_conditions"}
        if not isinstance(candidate, dict) or set(candidate) != required:
            lint.err("L13", f"{lint.rel(paths['03_PORTFOLIO.json'])}: candidate keys invalid")
            continue
        ids.append(candidate["id"])
        status = candidate["status"]
        if status not in {"SELECTED", "HOLD", "REJECTED", "REVIVABLE"}:
            lint.err("L13", f"{lint.rel(paths['03_PORTFOLIO.json'])}: candidate status invalid - {candidate['id']}")
        selected += status == "SELECTED"
        if not isinstance(candidate.get("evidence"), list) or not candidate["evidence"]:
            lint.err("L13", f"{lint.rel(paths['03_PORTFOLIO.json'])}: candidate missing evidence - {candidate['id']}")
        if status in {"REJECTED", "REVIVABLE"} and not str(candidate["rejection_reason"]).strip():
            lint.err("L13", f"{lint.rel(paths['03_PORTFOLIO.json'])}: rejected candidate missing reason - {candidate['id']}")
        for index, evidence in enumerate(candidate["evidence"]):
            target = _artifact(lint, proj, evidence, "L13", f"candidate {candidate['id']} evidence {index}")
            if target and target in used_evidence:
                lint.err("L13", f"{lint.rel(paths['03_PORTFOLIO.json'])}: reuses candidate evidence - {candidate['id']}")
            digest = evidence.get("sha256") if isinstance(evidence, dict) else None
            if digest and digest in used_hashes:
                lint.err("L13", f"{lint.rel(paths['03_PORTFOLIO.json'])}: reuses candidate evidence hash - {candidate['id']}")
            target and used_evidence.add(target)
            digest and used_hashes.add(digest)
    if len(ids) != len(set(ids)):
        lint.err("L13", f"{lint.rel(paths['03_PORTFOLIO.json'])}: duplicate candidate ID")
    if portfolio.get("selection_status") == "SELECTED" and selected != 1:
        lint.err("L13", f"{lint.rel(paths['03_PORTFOLIO.json'])}: SELECTED portfolio requires exactly one winner")

    if through == "P3":
        early_verification = _read(lint, os.path.join(proj, "06_VERIFICATION.md"), "L13")
        early_finals = lint.section_text(early_verification, "Final verdicts")
        for field in ("Human taste", "Agent operability"):
            if lint.scalar_field(early_finals, field) != "NOT_RUN":
                lint.err("L13", f"{lint.rel(os.path.join(proj, '06_VERIFICATION.md'))}: premature {field} verdict before final")
        return
    if set(preflight) != {"schema", "contract_version", "blockers", "dependencies"} or preflight.get("schema") != "ldl-preflight-manifest-v1":
        lint.err("L13", f"{lint.rel(paths['04_PREFLIGHT.json'])}: preflight schema invalid")
    if type(preflight.get("blockers")) is not int or preflight.get("blockers") != 0:
        lint.err("L13", f"{lint.rel(paths['04_PREFLIGHT.json'])}: preflight blockers must be zero")
    for dep in preflight.get("dependencies", []):
        dep_keys = {"id", "status", "probe", "limit", "fallback", "credential_required", "runner_id",
                    "executed_at", "exit_code", "expected_exit_code", "checks", "evidence"}
        if not isinstance(dep, dict) or set(dep) != dep_keys:
            lint.err("L13", f"{lint.rel(paths['04_PREFLIGHT.json'])}: dependency schema invalid")
            continue
        if dep.get("status") != "PASS":
            lint.err("L13", f"{lint.rel(paths['04_PREFLIGHT.json'])}: dependency not PASS - {dep.get('id', 'missing')}")
        execution_valid = (isinstance(dep.get("checks"), int) and not isinstance(dep.get("checks"), bool) and dep["checks"] > 0
                           and isinstance(dep.get("exit_code"), int) and not isinstance(dep.get("exit_code"), bool)
                           and dep.get("exit_code") == dep.get("expected_exit_code")
                           and bool(str(dep.get("probe", "")).strip()) and bool(str(dep.get("runner_id", "")).strip())
                           and str(dep.get("runner_id", "")).lower() != "maker")
        try:
            executed = datetime.strptime(dep.get("executed_at", ""), "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
            execution_valid = execution_valid and executed <= datetime.now(timezone.utc)
        except (TypeError, ValueError):
            execution_valid = False
        if not execution_valid:
            lint.err("L13", f"{lint.rel(paths['04_PREFLIGHT.json'])}: dependency has no valid executed probe - {dep.get('id', 'missing')}")
        _artifact(lint, proj, dep.get("evidence"), "L13", f"preflight {dep.get('id', 'missing')} evidence")

    if through == "P4":
        early_verification = _read(lint, os.path.join(proj, "06_VERIFICATION.md"), "L13")
        early_finals = lint.section_text(early_verification, "Final verdicts")
        for field in ("Human taste", "Agent operability"):
            if lint.scalar_field(early_finals, field) != "NOT_RUN":
                lint.err("L13", f"{lint.rel(os.path.join(proj, '06_VERIFICATION.md'))}: premature {field} verdict before final")
        return
    if set(capabilities) != {"schema", "contract_version", "capabilities"} or capabilities.get("schema") != "ldl-capability-proof-v1" or not capabilities.get("capabilities"):
        lint.err("L13", f"{lint.rel(paths['06_CAPABILITIES.json'])}: capability proof missing")
    for cap in capabilities.get("capabilities", []):
        cap_keys = {"id", "promise", "required_level", "status", "demo_evidence", "live_evidence", "limitations"}
        if not isinstance(cap, dict) or set(cap) != cap_keys:
            lint.err("L13", f"{lint.rel(paths['06_CAPABILITIES.json'])}: capability schema invalid")
            continue
        levels = {"NOT_IMPLEMENTED": 0, "BOUNDED_FALLBACK": 1, "CAPTURED_REAL": 2, "LIVE_VERIFIED": 3}
        if (cap.get("required_level") not in levels or cap.get("status") not in levels
                or levels[cap["status"]] < levels[cap["required_level"]]):
            lint.err("L13", f"{lint.rel(paths['06_CAPABILITIES.json'])}: promise is not verified - {cap.get('id', 'missing')}")
        if not str(cap.get("promise", "")).strip() or not str(cap.get("limitations", "")).strip():
            lint.err("L13", f"{lint.rel(paths['06_CAPABILITIES.json'])}: capability promise/limitations missing - {cap.get('id', 'missing')}")
        _artifact(lint, proj, cap.get("demo_evidence"), "L13", f"capability {cap.get('id', 'missing')} demo evidence")
        if cap.get("status") == "LIVE_VERIFIED":
            _artifact(lint, proj, cap.get("live_evidence"), "L13", f"capability {cap.get('id', 'missing')} live evidence")
    if set(scores) != {"schema", "contract_version", "rounds"} or scores.get("schema") != "ldl-judge-score-v1" or not scores.get("rounds"):
        lint.err("L13", f"{lint.rel(paths['06_JUDGE_SCORES.json'])}: judge rounds missing")
    evaluator_types_by_id = {item.get("id"): item.get("type") for item in evaluators if isinstance(item, dict)}
    with open(paths["02_EVALUATION.json"], "rb") as handle:
        evaluator_sha = hashlib.sha256(handle.read()).hexdigest()
    accepted_subject_hashes = set()
    selected_candidates = [candidate for candidate in candidates if candidate.get("status") == "SELECTED"]
    for candidate in selected_candidates:
        accepted_subject_hashes.update(item.get("sha256") for item in candidate.get("evidence", []) if isinstance(item, dict))
    for cap in capabilities.get("capabilities", []):
        for field in ("demo_evidence", "live_evidence"):
            if isinstance(cap.get(field), dict):
                accepted_subject_hashes.add(cap[field].get("sha256"))
    human_pass = False
    agent_pass = False
    for row in scores.get("rounds", []):
        if row.get("judge_id") not in evaluator_ids:
            lint.err("L13", f"{lint.rel(paths['06_JUDGE_SCORES.json'])}: unknown judge - {row.get('judge_id')}")
        if row.get("judge_type") != evaluator_types_by_id.get(row.get("judge_id")):
            lint.err("L13", f"{lint.rel(paths['06_JUDGE_SCORES.json'])}: judge type does not match evaluator profile")
        if row.get("judge_sha256") != evaluator_sha:
            lint.err("L13", f"{lint.rel(paths['06_JUDGE_SCORES.json'])}: stale or forged evaluator profile hash")
        if (not re.fullmatch(r"[0-9a-f]{64}", str(row.get("artifact_sha256", "")))
                or not isinstance(row.get("score"), int) or not 0 <= row["score"] <= 100):
            lint.err("L13", f"{lint.rel(paths['06_JUDGE_SCORES.json'])}: judge score/artifact hash invalid")
        elif row["artifact_sha256"] not in accepted_subject_hashes:
            lint.err("L13", f"{lint.rel(paths['06_JUDGE_SCORES.json'])}: judge subject hash is not bound to an accepted artifact")
        if row.get("judge_type") == "actual-human" and "human_evidence" not in row:
            lint.err("L13", f"{lint.rel(paths['06_JUDGE_SCORES.json'])}: actual-human judge requires human evidence")
        elif row.get("judge_type") == "actual-human":
            human_path = _artifact(lint, proj, row.get("human_evidence"), "L13", f"judge round {row.get('round')} human evidence")
            if human_path:
                review = _json(lint, human_path, "L13")
                required_review = {"schema", "contract_version", "evaluator_id", "approver", "decided_at", "verdict", "subject"}
                valid_review = isinstance(review, dict) and set(review) == required_review
                review_obj = review if isinstance(review, dict) else {}
                valid_review = valid_review and review_obj.get("schema") == "ldl-human-review-v1"
                valid_review = valid_review and review_obj.get("contract_version") == contract_version
                valid_review = valid_review and review_obj.get("evaluator_id") == row.get("judge_id")
                valid_review = valid_review and review_obj.get("verdict") == "PASS" and bool(str(review_obj.get("approver", "")).strip())
                try:
                    decided = datetime.strptime(review_obj.get("decided_at", ""), "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
                    valid_review = valid_review and decided <= datetime.now(timezone.utc)
                except (TypeError, ValueError):
                    valid_review = False
                subject_path = _artifact(lint, proj, review_obj.get("subject"),
                                         "L13", f"judge round {row.get('round')} human subject")
                valid_review = valid_review and bool(subject_path) and review_obj.get("subject", {}).get("sha256") == row.get("artifact_sha256")
                if not valid_review:
                    lint.err("L13", f"{lint.rel(paths['06_JUDGE_SCORES.json'])}: typed human review invalid")
                else:
                    human_pass = True
        if row.get("blocking_defects"):
            lint.err("L13", f"{lint.rel(paths['06_JUDGE_SCORES.json'])}: judge round has blocking defects")
        elif row.get("judge_type") == "agent-consumer":
            agent_pass = True
        _artifact(lint, proj, row.get("evidence"), "L13", f"judge round {row.get('round')} evidence")
    if len(scores.get("rounds", [])) > limits.get("max_rounds", 0) * max(1, len(evaluator_ids)):
        lint.err("L13", f"{lint.rel(paths['06_JUDGE_SCORES.json'])}: judge rounds exceed bounded iteration limit")
    verification = _read(lint, os.path.join(proj, "06_VERIFICATION.md"), "L13")
    finals = lint.section_text(verification, "Final verdicts")
    if lint.scalar_field(finals, "Human taste") != "PASS" or not human_pass:
        lint.err("L13", f"{lint.rel(os.path.join(proj, '06_VERIFICATION.md'))}: Human taste must PASS")
    if lint.scalar_field(finals, "Agent operability") != "PASS" or not agent_pass:
        lint.err("L13", f"{lint.rel(os.path.join(proj, '06_VERIFICATION.md'))}: Agent operability must PASS")
    submission = docs["06_SUBMISSION.json"]
    if set(submission) != {"schema", "contract_version", "required_files", "included_files", "excluded_files", "secret_scan", "link_check", "log_integrity", "archive_structure", "evidence"} or submission.get("schema") != "ldl-submission-manifest-v1":
        lint.err("L13", f"{lint.rel(paths['06_SUBMISSION.json'])}: submission schema invalid")
    for field in ("secret_scan", "link_check", "log_integrity", "archive_structure"):
        if submission.get(field) != "PASS":
            lint.err("L13", f"{lint.rel(paths['06_SUBMISSION.json'])}: {field} must PASS")
    if sorted(submission.get("required_files", [])) != sorted(submission.get("included_files", [])):
        lint.err("L13", f"{lint.rel(paths['06_SUBMISSION.json'])}: required/included files differ")
    _artifact(lint, proj, submission.get("evidence"), "L13", "submission evidence")


def _inside(path, boundary):
    try:
        lexical = os.path.commonpath([os.path.abspath(boundary), os.path.abspath(path)]) == os.path.abspath(boundary)
        resolved = os.path.commonpath([os.path.realpath(boundary), os.path.realpath(path)]) == os.path.realpath(boundary)
        return lexical and resolved
    except ValueError:
        return False


def _read(lint, path, code):
    return lint.read_text(path, code) if os.path.isfile(path) else ""


def check(lint, proj, through="final"):
    if lint.schema_version() == "0.5.0":
        check_v050(lint, proj, through)
    contract_path = os.path.join(proj, "00_CONTRACT.md")
    contract = _read(lint, contract_path, "L8")
    workspace_v3 = os.path.isfile(os.path.join(lint.root, ".ldl-version"))
    if not contract:
        return
    delivery_mode = lint.scalar_field(lint.section_text(contract, "Delivery profile"), "Delivery mode")
    if delivery_mode == "portfolio-competition" and lint.schema_version() != "0.5.0":
        lint.err("L13", f"{lint.rel(contract_path)}: portfolio-competition requires workspace schema 0.5.0")
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
            target = lint.local_link_target(proj, row["Evidence"])
            current_schema = lint.schema_version() in {"0.4.1", "0.4.2", "0.5.0"}
            if current_schema and verdict == "PENDING" and target:
                if not target.endswith(".json") or not _inside(target, os.path.join(proj, "raw")) or not os.path.isfile(target):
                    lint.err("L8", f"{lint.rel(progress_path)}: {name} reopen decision must be immutable under project raw/")
                else:
                    try:
                        decision = json.loads(_read(lint, target, "L8"))
                        import workflow
                        workflow.validate_gate_decision(proj, decision)
                    except (json.JSONDecodeError, ValueError) as exc:
                        lint.err("L8", f"{lint.rel(progress_path)}: {name} reopen decision invalid - {exc}")
                    else:
                        expected = {
                            "gate": name, "contract_version": version, "verdict": "REOPEN",
                            "approval_mode": approval_mode, "approver": row["Approver"],
                            "decided_at": row["Approved at"],
                        }
                        if any(decision[field] != value for field, value in expected.items()):
                            lint.err("L8", f"{lint.rel(progress_path)}: {name} reopen decision does not match gate row")
            if current_schema and verdict in {"HOLD", "FAIL"}:
                if not target or not target.endswith(".json"):
                    lint.err("L8", f"{lint.rel(progress_path)}: {name} {verdict} requires typed decision evidence")
                elif not _inside(target, os.path.join(proj, "raw")):
                    lint.err("L8", f"{lint.rel(progress_path)}: {name} typed decision must be immutable under project raw/")
                elif not os.path.isfile(target):
                    lint.err("L8", f"{lint.rel(progress_path)}: {name} typed decision missing")
                else:
                    try:
                        decision = json.loads(_read(lint, target, "L8"))
                        import workflow
                        workflow.validate_gate_decision(proj, decision)
                    except (json.JSONDecodeError, ValueError) as exc:
                        lint.err("L8", f"{lint.rel(progress_path)}: {name} typed decision invalid - {exc}")
                    else:
                        expected = {
                            "gate": name, "contract_version": version, "verdict": verdict,
                            "approval_mode": approval_mode, "approver": row["Approver"],
                            "decided_at": row["Approved at"],
                        }
                        if any(decision[field] != value for field, value in expected.items()):
                            lint.err("L8", f"{lint.rel(progress_path)}: {name} typed decision does not match gate row")
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
                if target.endswith(".json") and lint.schema_version() in {"0.4.1", "0.4.2", "0.5.0"}:
                    try:
                        decision = json.loads(approval_text)
                        import workflow
                        workflow.validate_gate_decision(proj, decision)
                    except (json.JSONDecodeError, ValueError) as exc:
                        lint.err("L8", f"{lint.rel(progress_path)}: {name} typed approval invalid - {exc}")
                    else:
                        expected = {
                            "gate": name, "contract_version": version, "verdict": verdict,
                            "approval_mode": approval_mode, "approver": row["Approver"],
                            "decided_at": row["Approved at"],
                        }
                        if any(decision[field] != value for field, value in expected.items()):
                            lint.err("L8", f"{lint.rel(progress_path)}: {name} typed approval does not match gate row")
                else:
                    if not lint.substantive_cell(approval_text):
                        lint.err("L8", f"{lint.rel(progress_path)}: {name} approval evidence is empty or placeholder")
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

    future_phase_done = any(phase_status.get(name) == "done" for name in (
        "P1 requirements", "P2 structure", "P3 research", "P4 scoping", "P5+P6 increments"))
    if through == "P0" and lint.schema_version() in {"0.4.1", "0.4.2", "0.5.0"} and not future_phase_done:
        future_tables = (
            ("01_REQUIREMENTS.md", "Requirements ledger", REQUIREMENTS_LEDGER_COLUMNS),
            ("03_EVIDENCE.md", "Evidence ledger", EVIDENCE_COLUMNS_V041 if lint.schema_version() in {"0.4.1", "0.4.2", "0.5.0"} else EVIDENCE_COLUMNS),
            ("04_SCOPE.md", "Impact dimensions", DIMENSION_COLUMNS),
            ("04_SCOPE.md", "Action readiness", ACTION_COLUMNS),
            ("06_VERIFICATION.md", "Requirement verdicts", REQUIREMENT_COLUMNS),
        )
        for filename, title, columns in future_tables:
            path = os.path.join(proj, filename)
            rows = lint.table_rows(_read(lint, path, "L8"), title, columns, "L8", lint.rel(path))
            if rows:
                lint.err("L8", f"{lint.rel(path)}: future phase content present during P0 - {title}")
    if through == "P0":
        return

    evidence_path = os.path.join(proj, "03_EVIDENCE.md")
    if lint.schema_version() in {"0.4.1", "0.4.2", "0.5.0"}:
        raw_rows = lint.table_rows(_read(lint, evidence_path, "L9"), "Evidence ledger", EVIDENCE_COLUMNS_V041, "L9", lint.rel(evidence_path))
        evidence_rows = []
        for row in raw_rows:
            domain = row["Evidence domain"]
            if domain not in EVIDENCE_DOMAINS:
                lint.err("L9", f"{lint.rel(evidence_path)}: invalid evidence domain - {row['Claim ID']} {domain}")
            evidence_rows.append({
                "Claim ID": row["Claim ID"], "Label": row["Evidence level"],
                "Claim": row["Claim"], "Source artifact": row["Source artifact"],
                "Captured at": row["Captured at"], "Scope/window": row["Scope/window"],
                "Transform/reproducer": row["Transform/reproducer"], "Status": row["Claim lifecycle"],
            })
    else:
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

    if through in {"P4", "final"}:
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
    if through in {"P3", "P4"}:
        return
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
