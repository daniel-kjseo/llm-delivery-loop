#!/usr/bin/env python3
"""LDL v0.7.0 execution helpers (stdlib only) — one module, five jobs.

  execution.py job-validate PROJECT JOB.json (--approvals-root DIR | --approved-job-sha256 HEX)
  execution.py reconcile PROJECT EXPECTED.json [--not-before EPOCH|ISO]
  execution.py status PROJECT [--format json|md] [--output PATH]
  execution.py evaluator-validate EVALUATOR.json
  execution.py measure-collect PROJECT --deliverable TEXT [--output PATH]
  execution.py measure-validate MEASUREMENT.json

What these checks are, precisely
--------------------------------
An approved job binds a *declaration* (project, contract, profile, phase, argv,
runner, cwd, output root) to an approval record the maker did not write. That
is all. It is **not an OS sandbox**: nothing here confines a launched process,
and a command that lies about what it writes will still write it. It is **not
human authentication**: an approval file proves a file exists in a directory
outside the project, not that a person made it. Every stronger word is banned
from the output on purpose.

Process COMPLETE, artifact valid, and user acceptance are three different
verdicts and are never merged. A process that exits 0 without producing its
declared outputs is a completed process with an invalid artifact set.
"""
import argparse
import csv
import hashlib
import json
import os
import re
import sys
import time
import unicodedata
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import policy  # noqa: E402
import workflow  # noqa: E402

try:
    import fcntl
    LOCK_PLATFORM = "posix-flock"
except ImportError:      # pragma: no cover - exercised only off POSIX
    fcntl = None
    LOCK_PLATFORM = "unsupported"

JOB_SCHEMA = "ldl-approved-job-v1"
APPROVAL_SCHEMA = "ldl-job-approval-v1"
OUTPUT_SCHEMA = "ldl-expected-output-v1"
RECONCILE_SCHEMA = "ldl-output-reconciliation-v1"
STATUS_SCHEMA = "ldl-status-report-v1"
EVALUATOR_SCHEMA = "ldl-evaluator-contract-v1"
MEASUREMENT_SCHEMA = "ldl-measurement-v1"

JOB_STRING_FIELDS = ("project", "contract_version", "contract_sha256", "profile", "phase",
                     "argv_sha256", "runner_id", "runner_role", "cwd", "output_root")
JOB_KEYS = {"schema"} | set(JOB_STRING_FIELDS)
APPROVAL_KEYS = {"schema", "job_sha256", "approver", "approval_mode", "decided_at"}
RUNNER_ROLES = {"runner", "verifier", "reviewer", "owner-proxy"}
OUTPUT_REQUIRED = {"id", "path", "format", "min_bytes"}
OUTPUT_OPTIONAL = {"sha256", "json_schema", "json_id_field", "json_id"}
OUTPUT_FORMATS = {"markdown", "text", "json", "csv"}
TRUTH_CASES = ("zero", "missing", "partial", "complete")
TRUTH_VERDICTS = {"PASS", "FAIL", "HOLD", "PARTIAL_CREDIT"}
AGGREGATE_METHODS = {"per-item-mean", "per-item-median", "weighted-sum", "unanimous"}
IDENT = re.compile(r"[A-Za-z0-9._-]{1,64}")
HEX64 = re.compile(r"[0-9a-f]{64}")
TARGET_IMPROVEMENT_PCT = 30

DISCLAIMER = "not an OS sandbox, not human authentication"


class ManifestError(Exception):
    """A declared manifest is unusable; the message names the exact field."""


class ApprovalError(Exception):
    """A job is not approved by a trust root outside the maker's own tree."""


# ---------------------------------------------------------------- digests
def file_digest(path):
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def argv_digest(command):
    """A command is its exact argv, not a shell string that could be re-quoted."""
    if not isinstance(command, (list, tuple)) or not command:
        raise ManifestError("argv must be a nonempty list")
    payload = b"\0".join(str(part).encode("utf-8") for part in command)
    return hashlib.sha256(payload).hexdigest()


def canonical_digest(document):
    return hashlib.sha256(
        json.dumps(document, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    ).hexdigest()


def utcnow():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _load_json(path, label):
    try:
        with open(path, encoding="utf-8") as handle:
            return json.load(handle)
    except (OSError, json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise ManifestError(f"{label} unreadable: {exc}")


# ------------------------------------------------------- containment rules
def contained_path(project, rel, field):
    """Resolve `rel` inside `project`, refusing absolutes, escapes and symlinks."""
    if not isinstance(rel, str) or not rel.strip():
        raise ManifestError(f"{field} must be a nonempty relative path")
    if os.path.isabs(rel):
        raise ManifestError(f"{field} must be relative to the project, not absolute: {rel}")
    project = os.path.realpath(project)
    target = os.path.realpath(os.path.join(project, rel))
    if os.path.commonpath([project, target]) != project:
        raise ManifestError(f"{field} escapes the project: {rel}")
    current = project
    for part in os.path.normpath(rel).split(os.sep):
        if part in ("", "."):
            continue
        current = os.path.join(current, part)
        if os.path.islink(current):
            raise ManifestError(f"{field} traverses a symlink: {rel}")
    return target


# ------------------------------------------------------------ approved job
def load_job(path):
    job = _load_json(path, "approved job manifest")
    digest = file_digest(path)
    if not isinstance(job, dict):
        raise ManifestError("approved job manifest must be a JSON object")
    if set(job) != JOB_KEYS:
        extra = sorted(set(job) - JOB_KEYS)
        missing = sorted(JOB_KEYS - set(job))
        raise ManifestError(
            "approved job manifest keys must match the v1 schema exactly"
            + (f"; unexpected {extra}" if extra else "")
            + (f"; missing {missing}" if missing else ""))
    if job["schema"] != JOB_SCHEMA:
        raise ManifestError(f"approved job schema must be {JOB_SCHEMA}")
    for field in JOB_STRING_FIELDS:
        if not isinstance(job[field], str) or not job[field].strip():
            raise ManifestError(f"approved job field {field} must be a nonempty string")
    if not HEX64.fullmatch(job["contract_sha256"]):
        raise ManifestError("approved job field contract_sha256 must be a sha256 hex digest")
    if not HEX64.fullmatch(job["argv_sha256"]):
        raise ManifestError("approved job field argv_sha256 must be a sha256 hex digest")
    return job, digest


def resolve_approval(job_digest, project, approvals_root=None, pinned=None):
    """The trust root is always outside the manifest the maker wrote.

    Two forms are accepted, both supplied by the launcher and never by the job:
      - `pinned`: the digest the owner launcher passes on its own command line;
      - `approvals_root`: a directory outside the project holding
        `<job_sha256>.json` approval records.
    A manifest that tries to attest to its own approval fails the exact-key
    check in load_job() before this function is ever reached.
    """
    if not pinned and not approvals_root:
        raise ApprovalError(
            "approved job requires an external trust root: pass --approved-job-sha256 "
            "or --approvals-root (a directory outside the project)")
    record = None
    if pinned:
        if not HEX64.fullmatch(str(pinned)):
            raise ApprovalError("pinned --approved-job-sha256 must be a sha256 hex digest")
        if pinned != job_digest:
            raise ApprovalError(
                f"job manifest does not match the pinned digest: {job_digest} != {pinned}")
        record = {"trust_root": "pinned-digest", "approver": None, "approval_mode": None,
                  "approval_path": None}
    if approvals_root:
        project = os.path.realpath(project)
        root = os.path.realpath(approvals_root)
        if not os.path.isdir(root):
            raise ApprovalError(f"approvals root is not a directory: {approvals_root}")
        if os.path.commonpath([project, root]) == project:
            raise ApprovalError(
                "approval trust root is inside the maker-controlled project tree; "
                "an approval the maker can write is not an approval")
        path = os.path.join(root, job_digest + ".json")
        if not os.path.isfile(path):
            raise ApprovalError(f"no approval for job digest {job_digest} under {approvals_root}")
        # An approvals directory outside the project proves nothing if the file
        # inside it is a link back into the tree the maker writes: resolve the
        # approval itself, not just its directory (review 1, class 3).
        resolved = os.path.realpath(path)
        if os.path.commonpath([project, resolved]) == project:
            raise ApprovalError(
                f"approval file resolves into the maker-controlled project tree: {resolved}; "
                "an approval the maker can write is not an approval")
        if os.path.commonpath([root, resolved]) != root:
            raise ApprovalError(
                f"approval file resolves outside the declared approvals root: {resolved}")
        approval = _load_json(path, "job approval")
        if not isinstance(approval, dict) or set(approval) != APPROVAL_KEYS:
            raise ApprovalError("job approval keys must match the v1 schema exactly")
        if approval["schema"] != APPROVAL_SCHEMA:
            raise ApprovalError(f"job approval schema must be {APPROVAL_SCHEMA}")
        if approval["job_sha256"] != job_digest:
            raise ApprovalError("job approval binds a different job digest")
        if not isinstance(approval.get("approver"), str) or not approval["approver"].strip():
            raise ApprovalError("job approval names no approver")
        if approval.get("approval_mode") not in {"human", "delegated-agent"}:
            raise ApprovalError("job approval approval_mode must be human or delegated-agent")
        if not workflow.valid_timestamp(approval.get("decided_at", "")):
            raise ApprovalError("job approval decided_at invalid or in the future")
        record = {"trust_root": "external-approvals-root", "approver": approval["approver"],
                  "approval_mode": approval["approval_mode"], "decided_at": approval["decided_at"],
                  "approval_path": resolved}
    return record


def check_job(project, phase, runner_id, command, job_path,
              approvals_root=None, pinned=None, cwd=None, runner_role=None,
              expected_manifest=None):
    """Every mismatch here is refused before any process is started."""
    project = os.path.realpath(project)
    job, digest = load_job(job_path)
    approval = resolve_approval(digest, project, approvals_root, pinned)

    if os.path.realpath(job["project"]) != project:
        raise ManifestError(f"approved job project does not match the target project: {job['project']}")
    contract = os.path.join(project, "00_CONTRACT.md")
    if not os.path.isfile(contract):
        raise ManifestError("approved job cannot be bound: project contract missing")
    if file_digest(contract) != job["contract_sha256"]:
        raise ManifestError("approved job contract_sha256 does not match the current 00_CONTRACT.md")
    if job["contract_version"] != policy.contract_version(project):
        raise ManifestError(
            f"approved job contract_version {job['contract_version']} is not the active contract version")
    actual_profile = policy.delivery_mode(project)
    if job["profile"] != actual_profile:
        raise ManifestError(
            f"approved job profile {job['profile']} is not the contract delivery profile {actual_profile or 'missing'}")
    if job["phase"] != phase:
        raise ManifestError(f"approved job phase {job['phase']} does not match the requested phase {phase}")
    if job["runner_id"] != runner_id:
        raise ManifestError(f"approved job runner_id {job['runner_id']} does not match --runner-id {runner_id}")
    if job["runner_role"] not in RUNNER_ROLES:
        raise ManifestError(
            f"approved job runner_role must be one of {sorted(RUNNER_ROLES)}, not {job['runner_role']}")
    # A declared role that nobody compares to the role actually launching is a
    # label, not a binding (review 1, class 3).
    if runner_role is not None and job["runner_role"] != runner_role:
        raise ManifestError(
            f"approved job runner_role {job['runner_role']} does not match the launching "
            f"--runner-role {runner_role}")
    if argv_digest(command) != job["argv_sha256"]:
        raise ManifestError("approved job argv_sha256 does not match the command actually being launched")
    declared_cwd = os.path.realpath(job["cwd"])
    actual_cwd = os.path.realpath(cwd or os.getcwd())
    if declared_cwd != actual_cwd:
        raise ManifestError(f"approved job cwd {job['cwd']} does not match the launch cwd {actual_cwd}")
    output_root = contained_path(project, job["output_root"], "approved job output_root")
    if expected_manifest is not None:
        declared = contained_path(project, expected_manifest["output_root"],
                                  "expected-output output_root")
        if declared != output_root:
            raise ManifestError(
                f"expected-output output_root {expected_manifest['output_root']} is not the "
                f"approved job output_root {job['output_root']}")
    return {"job_sha256": digest, "job": job, "approval": approval,
            "output_root": output_root, "enforcement": "approved-job",
            "limits": DISCLAIMER}


# -------------------------------------------------- atomic id reservation
LEDGER_REL = os.path.join("logs", "runner-ledger.csv")
LEDGER_COLUMNS = ["timestamp", "event", "invocation_id", "phase", "runner_id",
                  "session", "exit_code", "wall_seconds"]


def require_lock_platform():
    if LOCK_PLATFORM != "posix-flock":
        raise ManifestError(
            "atomic invocation reservation needs POSIX flock (macOS/Linux); "
            "this platform is not supported and no honest single-header guarantee can be made")


def reserve_and_start(project, phase, runner_id, session, timestamp=None):
    """Reserve the next invocation ID and write STARTED as one locked step.

    The header, the ID scan and the append all happen while the ledger file is
    held under an exclusive flock, so N concurrent processes produce N distinct
    IDs and exactly one header row. Platform support is POSIX only, declared
    in LOCK_PLATFORM rather than assumed.
    """
    require_lock_platform()
    path = os.path.join(project, LEDGER_REL)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    descriptor = os.open(path, os.O_RDWR | os.O_CREAT, 0o644)
    try:
        fcntl.flock(descriptor, fcntl.LOCK_EX)
        with os.fdopen(os.dup(descriptor), "r", encoding="utf-8", newline="") as handle:
            handle.seek(0)
            existing = handle.read()
        rows = list(csv.DictReader(existing.splitlines())) if existing.strip() else []
        started = sum(1 for row in rows if row.get("event") == "STARTED")
        invocation_id = f"INV-{started + 1:04d}"
        lines = []
        if not existing.strip():
            lines.append(",".join(LEDGER_COLUMNS))
        lines.append(",".join([timestamp or utcnow(), "STARTED", invocation_id, phase,
                               runner_id, session, "", ""]))
        payload = ("" if (not existing or existing.endswith("\n")) else "\n") + "\n".join(lines) + "\n"
        os.lseek(descriptor, 0, os.SEEK_END)
        os.write(descriptor, payload.encode("utf-8"))
        os.fsync(descriptor)
        return invocation_id
    finally:
        try:
            fcntl.flock(descriptor, fcntl.LOCK_UN)
        finally:
            os.close(descriptor)


def append_event(project, event, invocation_id, phase, runner_id, session,
                 exit_code="", wall_seconds="", timestamp=None):
    """Terminal rows also take the lock so a concurrent STARTED cannot interleave."""
    require_lock_platform()
    path = os.path.join(project, LEDGER_REL)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    descriptor = os.open(path, os.O_RDWR | os.O_CREAT, 0o644)
    try:
        fcntl.flock(descriptor, fcntl.LOCK_EX)
        size = os.lseek(descriptor, 0, os.SEEK_END)
        prefix = ""
        if size == 0:
            prefix = ",".join(LEDGER_COLUMNS) + "\n"
        else:
            os.lseek(descriptor, size - 1, os.SEEK_SET)
            if os.read(descriptor, 1) != b"\n":
                prefix = "\n"
            os.lseek(descriptor, 0, os.SEEK_END)
        row = ",".join([timestamp or utcnow(), event, invocation_id, phase, runner_id,
                        session, str(exit_code), str(wall_seconds)])
        os.write(descriptor, (prefix + row + "\n").encode("utf-8"))
        os.fsync(descriptor)
    finally:
        try:
            fcntl.flock(descriptor, fcntl.LOCK_UN)
        finally:
            os.close(descriptor)


# ------------------------------------------- cross-process output reservation
RESERVATION_REL = os.path.join("logs", "output-reservations.json")


def _alive(pid):
    try:
        os.kill(int(pid), 0)
    except (OSError, TypeError, ValueError):
        return False
    return True


def _reservation_file(project):
    path = os.path.join(project, RESERVATION_REL)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    return path


def _edit_reservations(project, mutate):
    """Read-modify-write the reservation table under one exclusive lock."""
    require_lock_platform()
    descriptor = os.open(_reservation_file(project), os.O_RDWR | os.O_CREAT, 0o644)
    try:
        fcntl.flock(descriptor, fcntl.LOCK_EX)
        with os.fdopen(os.dup(descriptor), "r", encoding="utf-8") as handle:
            handle.seek(0)
            raw = handle.read()
        try:
            table = json.loads(raw) if raw.strip() else {}
        except json.JSONDecodeError:
            table = {}
        if not isinstance(table, dict):
            table = {}
        # A holder whose process is gone never released; do not let it wedge.
        table = {path: entry for path, entry in table.items()
                 if isinstance(entry, dict) and _alive(entry.get("pid"))}
        result = mutate(table)
        payload = json.dumps(table, indent=2, sort_keys=True) + "\n"
        os.ftruncate(descriptor, 0)
        os.lseek(descriptor, 0, os.SEEK_SET)
        os.write(descriptor, payload.encode("utf-8"))
        os.fsync(descriptor)
        return result
    finally:
        try:
            fcntl.flock(descriptor, fcntl.LOCK_UN)
        finally:
            os.close(descriptor)


def read_reservations(project):
    return _edit_reservations(os.path.realpath(project), lambda table: dict(table))


def collision_keys(target):
    """Conservative, portable identity keys for one declared output path.

    A reservation keyed by the spelling of a path is not a claim on a file:
    `shared.txt` and `SHARED.txt` are one file on a case-insensitive volume,
    and a hard link gives one file two equally real names (review 2, F2).

    Two keys are used together, and neither pretends to be an OS sandbox:

    * the NFC-normalised, casefolded path, applied on every platform whether or
      not this volume is case-insensitive — a false collision refuses a launch,
      which is the safe direction;
    * `dev:ino` when the file already exists, which catches links and any other
      alias to the same inode.

    An output that does not exist yet has no inode, so aliasing is additionally
    bounded by refusing multiply linked declared outputs in reserve_outputs().
    """
    keys = ["path:" + unicodedata.normalize("NFC", target).casefold()]
    try:
        info = os.stat(target)
    except OSError:
        return keys
    keys.append(f"inode:{info.st_dev}:{info.st_ino}")
    return keys


def reserve_outputs(project, invocation_id, manifest):
    """Claim every declared output resource for this invocation, or refuse.

    Two live invocations that declare the same file are not two runs of the
    same job: whichever writes last decides what the other one "produced". The
    claim is resource-level, taken before launch and released on every exit
    path (review 1, class 4; alias evasion closed in review 2, F2).
    """
    project = os.path.realpath(project)
    root = contained_path(project, manifest["output_root"], "expected-output output_root")
    targets = []
    for entry in manifest["outputs"]:
        target = os.path.realpath(os.path.join(root, entry["path"]))
        try:
            links = os.stat(target).st_nlink
        except OSError:
            links = 1
        if links > 1:
            raise ManifestError(
                f"declared output {os.path.relpath(target, project)} has {links} hard links; a "
                "multiply linked file is reachable under another name and cannot be reserved as "
                "this invocation's own resource")
        targets.append(target)
    claimed = {key: target for target in targets for key in collision_keys(target)}

    def mutate(table):
        for path, entry in table.items():
            if entry.get("invocation_id") == invocation_id:
                continue
            for key in entry.get("collision_keys") or collision_keys(path):
                if key in claimed:
                    raise ManifestError(
                        f"declared output {os.path.relpath(claimed[key], project)} resolves to the "
                        f"same resource as {os.path.relpath(path, project)}, already reserved by "
                        f"live invocation {entry.get('invocation_id')} (pid {entry.get('pid')}); "
                        "two live invocations may not share an output resource")
        for target in targets:
            table[target] = {"invocation_id": invocation_id, "pid": os.getpid(),
                             "reserved_at": utcnow(), "collision_keys": collision_keys(target)}
        return list(targets)

    return _edit_reservations(project, mutate)


def release_outputs(project, invocation_id):
    project = os.path.realpath(project)

    def mutate(table):
        for path in [path for path, entry in table.items()
                     if entry.get("invocation_id") == invocation_id]:
            del table[path]
        return None

    return _edit_reservations(project, mutate)


def record_job_binding(project, record):
    """Append what the launch relied on, next to the ledger it belongs to."""
    path = os.path.join(project, "logs", "approved-jobs.jsonl")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True,
                                separators=(",", ":")) + "\n")
        handle.flush()
        os.fsync(handle.fileno())


# ------------------------------------------- expected outputs / reconcile
def freeze_expected(path):
    """Validate a manifest once and keep the validated object plus its digest.

    Re-reading the file after the child ran let the child rewrite its own
    success criteria (review 1, class 4). The launcher validates before launch
    and reconciles against this frozen copy, never against the file again.
    """
    return load_expected(path), file_digest(path)


def load_expected(path):
    # A frozen (already-read) manifest object is revalidated on the same rules
    # as a file, so freezing can never widen what is accepted.
    manifest = path if isinstance(path, dict) else _load_json(path, "expected-output manifest")
    if not isinstance(manifest, dict) or set(manifest) != {"schema", "job_id", "output_root", "outputs"}:
        raise ManifestError("expected-output manifest keys must match the v1 schema exactly")
    if manifest["schema"] != OUTPUT_SCHEMA:
        raise ManifestError(f"expected-output schema must be {OUTPUT_SCHEMA}")
    if not isinstance(manifest["job_id"], str) or not IDENT.fullmatch(manifest["job_id"]):
        raise ManifestError("expected-output job_id must be a bounded visible identifier")
    outputs = manifest["outputs"]
    if not isinstance(outputs, list) or not outputs:
        raise ManifestError("expected-output manifest declares no outputs")
    ids, paths = [], []
    for index, entry in enumerate(outputs):
        if not isinstance(entry, dict) or not OUTPUT_REQUIRED <= set(entry) or not set(entry) <= (OUTPUT_REQUIRED | OUTPUT_OPTIONAL):
            raise ManifestError(f"expected-output entry {index} keys invalid")
        if not isinstance(entry["id"], str) or not IDENT.fullmatch(entry["id"]):
            raise ManifestError(f"expected-output entry {index} id invalid")
        if not isinstance(entry["path"], str) or not entry["path"].strip():
            raise ManifestError(f"expected-output entry {index} path invalid")
        if entry["format"] not in OUTPUT_FORMATS:
            raise ManifestError(f"expected-output entry {index} format invalid")
        if not isinstance(entry["min_bytes"], int) or isinstance(entry["min_bytes"], bool) or entry["min_bytes"] < 1:
            raise ManifestError(f"expected-output entry {index} min_bytes must be a positive integer")
        if entry.get("sha256") is not None and not HEX64.fullmatch(str(entry["sha256"])):
            raise ManifestError(f"expected-output entry {index} sha256 invalid")
        ids.append(entry["id"])
        paths.append(os.path.normpath(entry["path"]))
    if len(ids) != len(set(ids)):
        raise ManifestError("expected-output manifest has a duplicate output id")
    if len(paths) != len(set(paths)):
        raise ManifestError("expected-output manifest has a duplicate output path")
    return manifest


def _parse_not_before(value):
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip()
    try:
        return float(text)
    except ValueError:
        pass
    try:
        return datetime.strptime(text, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc).timestamp()
    except ValueError:
        raise ManifestError(f"--not-before must be an epoch or UTC ISO-8601 timestamp: {value}")


def reconcile(project, manifest_path, not_before=None, process_complete=None, exit_code=None,
              manifest_sha256=None):
    """Check declared outputs against what is actually on disk.

    A PASS here means: the declared files exist inside the declared root, are
    nonempty, fresh, and match every declared hash/shape/ID. It says nothing
    about whether the content is any good — that stays NOT_RUN until a reviewer
    and then the actual recipient say otherwise.
    """
    project = os.path.realpath(project)
    manifest = load_expected(manifest_path)
    floor = _parse_not_before(not_before)
    try:
        root = contained_path(project, manifest["output_root"], "expected-output output_root")
    except ManifestError as exc:
        raise ManifestError(str(exc))
    results = []
    for entry in manifest["outputs"]:
        status, detail, digest = "OK", "", None
        try:
            target = contained_path(root, entry["path"], "expected output path")
        except ManifestError as exc:
            results.append({"id": entry["id"], "path": entry["path"], "status": "ESCAPED",
                            "detail": str(exc), "sha256": None})
            continue
        if not os.path.isfile(target):
            status, detail = "MISSING", "declared output does not exist"
        elif os.path.getsize(target) < entry["min_bytes"]:
            status, detail = "EMPTY", f"{os.path.getsize(target)} bytes < min_bytes {entry['min_bytes']}"
        elif floor is not None and os.path.getmtime(target) < floor:
            status, detail = "STALE", "file predates the run; a preexisting output is not this run's output"
        else:
            digest = file_digest(target)
            if entry.get("sha256") and digest != entry["sha256"]:
                status, detail = "HASH_MISMATCH", f"declared {entry['sha256']}, found {digest}"
            elif entry["format"] == "json":
                try:
                    with open(target, encoding="utf-8") as handle:
                        document = json.load(handle)
                except (OSError, json.JSONDecodeError, UnicodeDecodeError) as exc:
                    status, detail = "MALFORMED", f"not parseable JSON: {exc}"
                else:
                    declared_schema = entry.get("json_schema")
                    id_field = entry.get("json_id_field")
                    if not isinstance(document, dict):
                        status, detail = "MALFORMED", "JSON output must be an object"
                    elif declared_schema and document.get("schema") != declared_schema:
                        status, detail = "WRONG_SCHEMA", (
                            f"declared {declared_schema}, found {document.get('schema')!r}")
                    elif id_field and document.get(id_field) != entry.get("json_id"):
                        status, detail = "WRONG_ID", (
                            f"declared {entry.get('json_id')!r}, found {document.get(id_field)!r}")
        results.append({"id": entry["id"], "path": entry["path"], "status": status,
                        "detail": detail, "sha256": digest})

    freshness = "CHECKED" if floor is not None else "NOT_CHECKED"
    all_ok = all(item["status"] == "OK" for item in results)
    artifact_valid = bool(all_ok and floor is not None)
    if not all_ok:
        verdict = "FAIL"
    elif floor is None:
        verdict = "INCOMPLETE"
    else:
        verdict = "PASS"
    return {
        "schema": RECONCILE_SCHEMA,
        "job_id": manifest["job_id"],
        "output_root": manifest["output_root"],
        "expected_manifest_sha256": manifest_sha256,
        "expectation": "frozen-before-launch" if manifest_sha256 else "read-at-check-time",
        "checked_at": utcnow(),
        "freshness": freshness,
        "not_before": floor,
        "outputs": results,
        "artifact_valid": artifact_valid,
        "verdict": verdict,
        "process_complete": process_complete,
        "process_exit_code": exit_code,
        "semantic_acceptance": "NOT_RUN",
        "user_acceptance": "NOT_RUN",
        "note": "artifact validity is file-level only; reviewer and recipient verdicts are separate",
    }


# ------------------------------------------------------------ status report
UNKNOWN = "UNKNOWN"


def _read(path):
    try:
        with open(path, encoding="utf-8") as handle:
            return handle.read()
    except OSError:
        return None


def status(project):
    """Derive a read-only report from the records that already exist.

    This never writes PROGRESS.md, gate rows, verdicts or history, and never
    invents a state from prose. Anything missing or unparsable reports UNKNOWN,
    and UNKNOWN can never roll up to PASS.
    """
    project = os.path.realpath(project)
    blockers = []
    report = {"schema": STATUS_SCHEMA, "project": os.path.basename(project),
              "generated_at": utcnow(), "source": "derived read-only from project records"}

    report["profile"] = policy.delivery_mode(project) or UNKNOWN
    report["contract_version"] = policy.contract_version(project) or UNKNOWN
    contract = os.path.join(project, "00_CONTRACT.md")
    report["contract"] = ({"path": "00_CONTRACT.md", "sha256": file_digest(contract)}
                          if os.path.isfile(contract) else {"path": "00_CONTRACT.md", "sha256": UNKNOWN})
    if report["profile"] == UNKNOWN:
        blockers.append("delivery profile UNKNOWN: contract missing or unreadable")

    progress_text = _read(os.path.join(project, "PROGRESS.md"))
    gates, phases = {}, {}
    if progress_text is None:
        report["gates"], report["phases"] = UNKNOWN, UNKNOWN
        blockers.append("PROGRESS.md missing: gate and phase state UNKNOWN")
    else:
        try:
            gate_rows, phase_rows = policy._tables(progress_text)
            phases = {phase: state or "pending" for phase, state in phase_rows.items()}
            active_version = policy.contract_version(project)
            for gate, row in gate_rows.items():
                stated = row["Verdict"] or "PENDING"
                verified, detail = "NOT_APPLICABLE", ""
                if stated == "PASS":
                    # A PASS row is a claim. Revalidate it against the typed
                    # decision artifact before any report repeats it as fact
                    # (review 1, class 6).
                    try:
                        policy.verify_gate(project, gate, gate_rows, phase_rows, active_version)
                        verified = "PASS"
                    except policy.PolicyError as exc:
                        verified, detail = UNKNOWN, str(exc)
                        blockers.append(f"gate {gate} PASS row is not supported by typed evidence: {exc}")
                gates[gate] = {"stated": stated, "verified": verified, "detail": detail}
        except policy.PolicyError as exc:
            report["gates"], report["phases"] = UNKNOWN, UNKNOWN
            blockers.append(f"PROGRESS.md unparsable: {exc}")
        else:
            report["gates"], report["phases"] = gates, phases
            pending = sorted(phase for phase, state in phases.items() if state != "done")
            if pending:
                blockers.append(f"{len(pending)} phase row(s) not done: {', '.join(pending)}")

    requirements = {"status": UNKNOWN, "total": None, "verdicts": {}}
    req_text = _read(os.path.join(project, "01_REQUIREMENTS.md"))
    ver_text = _read(os.path.join(project, "06_VERIFICATION.md"))
    if req_text is None or ver_text is None:
        blockers.append("requirements or verification document missing: coverage UNKNOWN")
    else:
        try:
            _, req_rows = workflow.markdown_table(req_text, "Requirements ledger", workflow.REQ_COLUMNS)
            _, verdict_rows = workflow.markdown_table(ver_text, "Requirement verdicts", workflow.VERDICT_COLUMNS)
        except SystemExit as exc:
            blockers.append(f"requirement tables unparsable: {exc}")
        else:
            declared = [row["Requirement ID"] for row in req_rows]
            recorded = {row["Requirement ID"]: row["Verdict"] or UNKNOWN for row in verdict_rows}
            tally = {}
            for req_id in declared:
                tally[recorded.get(req_id, UNKNOWN)] = tally.get(recorded.get(req_id, UNKNOWN), 0) + 1
            requirements = {"status": "DERIVED", "total": len(declared), "verdicts": tally}
            missing = [req_id for req_id in declared if req_id not in recorded]
            if missing:
                blockers.append(f"{len(missing)} requirement(s) have no verdict row")
            # A PASS whose evidence link points at a file that is not there is
            # not evidence of anything (review 1, class 6).
            unbacked = []
            for row in verdict_rows:
                if (row["Verdict"] or "").strip() != "PASS":
                    continue
                link = re.search(r"\]\(([^)]+)\)", row.get("Evidence", "") or "")
                try:
                    workflow.project_file(project, link.group(1) if link else "")
                except (ValueError, AttributeError):
                    unbacked.append(row["Requirement ID"])
            if unbacked:
                requirements["unbacked_pass"] = unbacked
                blockers.append(
                    f"{len(unbacked)} requirement PASS row(s) cite missing evidence: {', '.join(unbacked)}")
    report["requirements"] = requirements

    finals = {}
    if ver_text is not None:
        section = policy._section(ver_text, "Final verdicts")
        for name in ("Harness", "Product", "Execution readiness", "Method conformance",
                     "Independent verifier", "Target mutation"):
            finals[name] = policy._field(section, name) or UNKNOWN
    report["final_verdicts"] = finals or UNKNOWN

    runner = {"started": 0, "completed": 0, "aborted": 0, "unterminated": 0, "status": "DERIVED"}
    ledger_path = os.path.join(project, LEDGER_REL)
    ledger_text = _read(ledger_path)
    if ledger_text is None:
        runner["status"] = UNKNOWN
        blockers.append("runner ledger missing: invocation history UNKNOWN")
    else:
        started, terminal = set(), set()
        for row in csv.DictReader(ledger_text.splitlines()):
            event = (row.get("event") or "").strip()
            if event == "STARTED":
                started.add(row.get("invocation_id"))
                runner["started"] += 1
            elif event == "COMPLETED":
                terminal.add(row.get("invocation_id"))
                runner["completed"] += 1
            elif event == "ABORTED":
                terminal.add(row.get("invocation_id"))
                runner["aborted"] += 1
        runner["unterminated"] = len(started - terminal)
        if runner["unterminated"]:
            blockers.append(f"{runner['unterminated']} unterminated invocation(s): "
                            "a STARTED row with no COMPLETED or ABORTED")
    report["runner"] = runner

    artifacts = {"status": "NOT_RUN", "reports": []}
    recon_dir = os.path.join(project, "logs", "reconciliation")
    if os.path.isdir(recon_dir):
        for name in sorted(os.listdir(recon_dir)):
            if not name.endswith(".json"):
                continue
            try:
                document = _load_json(os.path.join(recon_dir, name), "reconciliation report")
            except ManifestError as exc:
                artifacts["reports"].append({"file": name, "verdict": UNKNOWN, "detail": str(exc)})
                blockers.append(f"reconciliation report unreadable: {name}")
                continue
            # Valid JSON of the wrong shape is still not a report: a list has no
            # .get and used to crash the whole status run (review 1, class 6).
            if not isinstance(document, dict):
                artifacts["reports"].append({"file": name, "verdict": UNKNOWN,
                                             "detail": f"report is a JSON {type(document).__name__}, not an object"})
                blockers.append(f"reconciliation report is not an object: {name}")
                continue
            artifacts["reports"].append({"file": name, "verdict": document.get("verdict", UNKNOWN),
                                         "artifact_valid": document.get("artifact_valid"),
                                         "user_acceptance": document.get("user_acceptance", UNKNOWN)})
        if artifacts["reports"]:
            artifacts["status"] = "DERIVED"
    report["artifacts"] = artifacts

    unknown_present = (UNKNOWN in (report["profile"], report["contract_version"])
                       or report["gates"] == UNKNOWN or requirements["status"] == UNKNOWN
                       or runner["status"] == UNKNOWN or report["final_verdicts"] == UNKNOWN
                       or any(item.get("verdict") == UNKNOWN for item in artifacts["reports"])
                       or (isinstance(gates, dict)
                           and any(row["verified"] == UNKNOWN for row in gates.values())))
    # PASS is the one verdict that may not be reached by omission: every gate
    # PASS revalidated, every phase done, every final verdict PASS, and at least
    # one reconciliation report whose artifacts really validated.
    complete = (isinstance(gates, dict) and gates
                and all(row["stated"] == "PASS" and row["verified"] == "PASS"
                        for row in gates.values())
                and isinstance(phases, dict) and phases
                and all(state == "done" for state in phases.values())
                and requirements["total"]
                and set(requirements["verdicts"]) == {"PASS"}
                and not requirements.get("unbacked_pass")
                and finals and all(value == "PASS" for value in finals.values())
                and artifacts["status"] == "DERIVED" and artifacts["reports"]
                and all(item.get("verdict") == "PASS" and item.get("artifact_valid") is True
                        for item in artifacts["reports"]))
    if unknown_present:
        overall = UNKNOWN
    elif blockers:
        overall = "BLOCKED"
    elif complete:
        overall = "PASS"
    else:
        overall = "IN_PROGRESS"
    report["blockers"] = blockers
    report["overall"] = overall
    report["acceptance"] = {"reviewer": "SEPARATE", "actual_human_user": "NOT_RUN",
                            "note": "no AI verdict substitutes for the actual recipient"}
    return report


def render_markdown(report):
    """The relay template: goal / state / delta / blockers / path+hash."""
    gates = report["gates"]
    gate_line = (", ".join(f"{gate}={row['stated']}(verified={row['verified']})"
                           for gate, row in sorted(gates.items()))
                 if isinstance(gates, dict) else str(gates))
    requirements = report["requirements"]
    req_line = (f"{requirements['total']} requirement(s): "
                + ", ".join(f"{verdict}={count}" for verdict, count in sorted(requirements["verdicts"].items()))
                ) if requirements.get("total") else f"requirements {requirements['status']}"
    runner = report["runner"]
    lines = [
        f"# Status relay — {report['project']} ({report['generated_at']})",
        "",
        f"- Goal: deliver the contracted increment under profile "
        f"{report['profile']} / contract {report['contract_version']}",
        f"- State: overall {report['overall']}; gates {gate_line}; {req_line}",
        f"- Delta: invocations started={runner['started']} completed={runner['completed']} "
        f"aborted={runner['aborted']}; artifact reports={len(report['artifacts']['reports'])}",
        "- Blockers: " + ("; ".join(report["blockers"]) if report["blockers"] else "none recorded"),
        f"- Path+hash: {report['contract']['path']} sha256={report['contract']['sha256']}",
        "",
        f"Acceptance: reviewer {report['acceptance']['reviewer']}, "
        f"actual human user {report['acceptance']['actual_human_user']}. "
        "This report is derived read-only; it writes no gate, verdict or history.",
    ]
    return "\n".join(lines) + "\n"


# ------------------------------------------------ frozen evaluator contract
def validate_evaluator_contract(path, expected_sha256=None):
    """Structure only. This validator never decides whether a verdict is right.

    It checks that the zero / missing / partial / complete cases are stated,
    that aggregation, penalty placement and dispute authority are stated, and
    that the document was frozen (version + hash) before it could be used to
    score anything. Whether "0 proposals = FAIL" is a *good* rule is the
    evaluator's business, not the linter's.
    """
    document = _load_json(path, "evaluator contract")
    required = {"schema", "contract_version", "scope", "frozen_at", "frozen_sha256",
                "truth_table", "aggregate", "penalty", "dispute"}
    if not isinstance(document, dict) or set(document) != required:
        raise ManifestError("evaluator contract keys must match the v1 schema exactly")
    if document["schema"] != EVALUATOR_SCHEMA:
        raise ManifestError(f"evaluator contract schema must be {EVALUATOR_SCHEMA}")
    if document["scope"] != "evaluation-only":
        raise ManifestError(
            f"evaluator contract scope must be evaluation-only; {document['scope']!r} would "
            "extend a scoring template over work it was never frozen for")
    if not re.fullmatch(r"v\d+(?:\.\d+)*", str(document["contract_version"])):
        raise ManifestError("evaluator contract contract_version invalid")
    if not workflow.valid_timestamp(document["frozen_at"]):
        raise ManifestError("evaluator contract frozen_at invalid or in the future")

    table = document["truth_table"]
    if not isinstance(table, list) or not table:
        raise ManifestError("evaluator contract truth_table must be a nonempty list")
    seen = {}
    for index, row in enumerate(table):
        if not isinstance(row, dict) or set(row) != {"case", "condition", "verdict"}:
            raise ManifestError(f"evaluator contract truth_table row {index} keys invalid")
        if row["case"] not in TRUTH_CASES:
            raise ManifestError(f"evaluator contract truth_table row {index} case must be one of {list(TRUTH_CASES)}")
        if row["verdict"] not in TRUTH_VERDICTS:
            raise ManifestError(f"evaluator contract truth_table row {index} verdict invalid")
        if not isinstance(row["condition"], str) or not row["condition"].strip():
            raise ManifestError(f"evaluator contract truth_table row {index} condition missing")
        if row["case"] in seen:
            raise ManifestError(f"evaluator contract truth_table states case {row['case']} twice")
        seen[row["case"]] = row["verdict"]
    for case in TRUTH_CASES:
        if case not in seen:
            raise ManifestError(f"evaluator contract truth_table does not state the {case} case")

    aggregate = document["aggregate"]
    if not isinstance(aggregate, dict) or set(aggregate) != {"method", "judges", "tie_break"}:
        raise ManifestError("evaluator contract aggregate keys invalid")
    if aggregate["method"] not in AGGREGATE_METHODS:
        raise ManifestError(f"evaluator contract aggregate method must be one of {sorted(AGGREGATE_METHODS)}")
    if not isinstance(aggregate["judges"], int) or isinstance(aggregate["judges"], bool) or aggregate["judges"] < 1:
        raise ManifestError("evaluator contract aggregate judges must be a positive integer")
    if not isinstance(aggregate["tie_break"], str) or not aggregate["tie_break"].strip():
        raise ManifestError("evaluator contract aggregate tie_break missing")

    penalty = document["penalty"]
    if not isinstance(penalty, dict) or set(penalty) != {"applied_at", "double_count", "max_applications"}:
        raise ManifestError("evaluator contract penalty keys invalid")
    if penalty["applied_at"] not in {"judge-item-score", "aggregate-total"}:
        raise ManifestError("evaluator contract penalty applied_at must be judge-item-score or aggregate-total")
    if penalty["double_count"] not in {"forbidden", "explicitly-allowed"}:
        raise ManifestError(
            "evaluator contract penalty double_count must be forbidden or explicitly-allowed; "
            "an unstated double-penalty policy is how the same fault gets charged twice")
    if not isinstance(penalty["max_applications"], int) or isinstance(penalty["max_applications"], bool) or penalty["max_applications"] < 1:
        raise ManifestError("evaluator contract penalty max_applications must be a positive integer")

    dispute = document["dispute"]
    if not isinstance(dispute, dict) or set(dispute) != {"threshold", "authority", "authority_kind"}:
        raise ManifestError("evaluator contract dispute keys invalid")
    if not isinstance(dispute["threshold"], (int, float)) or isinstance(dispute["threshold"], bool):
        raise ManifestError("evaluator contract dispute threshold must be a number")
    if not isinstance(dispute["authority"], str) or not dispute["authority"].strip():
        raise ManifestError("evaluator contract dispute authority missing: an unowned dispute never resolves")
    if dispute["authority_kind"] not in {"actual-human", "delegated-agent"}:
        raise ManifestError("evaluator contract dispute authority_kind must be actual-human or delegated-agent")
    if dispute["authority_kind"] == "actual-human" and re.search(r"\bAI\b|agent|proxy|model", dispute["authority"], re.I):
        raise ManifestError(
            "evaluator contract names an AI proxy as an actual-human dispute authority; "
            "a delegated agent is declared delegated-agent")

    frozen = dict(document)
    stated = frozen["frozen_sha256"]
    frozen["frozen_sha256"] = ""
    if not HEX64.fullmatch(str(stated)) or canonical_digest(frozen) != stated:
        raise ManifestError(
            "evaluator contract frozen_sha256 does not match its own content; the template must be "
            "frozen (version + hash) before it is used to score anything")
    # Self-consistency is not freezing: anyone who edits the truth table can
    # recompute this hash. Only a digest the caller pinned *before* the edit
    # proves the document is the one that was frozen (review 1, class 9).
    freeze, freeze_verification = "UNBOUND", "NOT_RUN"
    if expected_sha256 is not None:
        if not HEX64.fullmatch(str(expected_sha256)):
            raise ManifestError("evaluator --expected-sha256 must be a sha256 hex digest")
        if stated != expected_sha256:
            raise ManifestError(
                f"evaluator contract does not match the pinned frozen digest: {stated} != "
                f"{expected_sha256}; a rehashed edit is a new template, not the frozen one")
        freeze, freeze_verification = "BOUND", "PASS"
    return {"schema": "ldl-evaluator-validation-v1", "verdict": "PASS", "scope": document["scope"],
            "contract_version": document["contract_version"], "frozen_sha256": stated,
            "cases": sorted(seen), "truth_semantics": "NOT_JUDGED",
            "freeze": freeze, "freeze_verification": freeze_verification,
            "freeze_note": ("self-hash only: pass --expected-sha256 with the digest recorded when the "
                            "template was frozen to check it against anything outside the file"
                            if freeze == "UNBOUND" else
                            "matches the digest the caller pinned; the pin's own provenance is the "
                            "owner's responsibility and is not an identity check"),
            "note": "structure and freezing checked; the correctness of each verdict is the evaluator's call"}


# ---------------------------------------------------------- measurement
def collect_measurement(project, deliverable, comparison_kind="same-model-process"):
    """Read what actually happened; leave everything unobserved as null."""
    project = os.path.realpath(project)
    ledger_text = _read(os.path.join(project, LEDGER_REL))
    invocations, wall, aborted = 0, [], 0
    completed_wall = {}
    if ledger_text:
        for row in csv.DictReader(ledger_text.splitlines()):
            event = row.get("event") or ""
            if event == "STARTED":
                invocations += 1
            elif event in {"COMPLETED", "ABORTED"}:
                if event == "ABORTED":
                    aborted += 1
                try:
                    seconds = float(row.get("wall_seconds") or "")
                except (TypeError, ValueError):
                    continue
                wall.append(seconds)
                if event == "COMPLETED":
                    completed_wall[row.get("invocation_id")] = seconds
    calls = {"llm_calls": None, "input_tokens": None, "output_tokens": None, "checker_runs": None}
    cost_source = "ABSENT"
    cost_text = _read(os.path.join(project, "logs", "cost-ledger.csv"))
    if cost_text and cost_text.strip():
        reader = csv.DictReader(cost_text.splitlines())
        header = reader.fieldnames or []
        # A ledger whose header is not the ledger header used to sum to a
        # confident row of zeros (review 1, class 8). Unknown stays null.
        if not set(calls) <= set(header):
            cost_source = "UNPARSABLE"
        else:
            # A blank or non-numeric cell is a missing observation, not a zero,
            # and a column with one broken cell has no trustworthy total: the
            # whole column stays null rather than reporting a partial sum as a
            # total (review 1 class 8; review 2 report blocker 2).
            totals = {key: 0 for key in calls}
            observed = {key: 0 for key in calls}
            broken = set()
            rows = 0
            for row in reader:
                rows += 1
                for key in calls:
                    cell = row.get(key)
                    cell = "" if cell is None else str(cell).strip()
                    try:
                        number = int(cell)
                    except (TypeError, ValueError):
                        broken.add(key)
                        continue
                    if number < 0:
                        broken.add(key)
                        continue
                    totals[key] += number
                    observed[key] += 1
            if rows:
                calls = {key: (totals[key] if key not in broken and observed[key] else None)
                         for key in calls}
                cost_source = "PARTIAL" if broken else "logs/cost-ledger.csv"

    # An artifact time may only be claimed for invocations whose declared
    # outputs actually reconciled; a 10-second abort that wrote nothing has no
    # time-to-artifact at all (review 1, class 8).
    artifact_seconds, artifact_source = None, None
    recon_dir = os.path.join(project, "logs", "reconciliation")
    validated = []
    if os.path.isdir(recon_dir):
        for name in sorted(os.listdir(recon_dir)):
            if not name.endswith(".json"):
                continue
            try:
                document = _load_json(os.path.join(recon_dir, name), "reconciliation report")
            except ManifestError:
                continue
            if isinstance(document, dict) and document.get("artifact_valid") is True:
                validated.append(os.path.splitext(name)[0])
    if validated:
        seconds = [value for invocation, value in completed_wall.items() if invocation in validated]
        if seconds:
            artifact_seconds = round(sum(seconds), 3)
            artifact_source = ("logs/runner-ledger.csv COMPLETED rows for invocations with a "
                               "validated reconciliation report; measures the launched child "
                               "process only, not the full request-to-acceptance span")
    return {
        "schema": MEASUREMENT_SCHEMA,
        "contract_version": policy.contract_version(project) or None,
        "deliverable": deliverable,
        "collected_at": utcnow(),
        "comparison_kind": comparison_kind,
        "technical": {
            "invocations": invocations,
            "aborted": aborted,
            "wall_seconds_total": round(sum(wall), 3) if wall else None,
            "child_process_wall_seconds_total": round(sum(wall), 3) if wall else None,
            "time_to_artifact_seconds": artifact_seconds,
            "time_to_artifact_source": artifact_source,
            "time_to_artifact_scope": ("launched child process only; the declared start of work, "
                                       "review and acceptance are not included"),
            "source": "logs/runner-ledger.csv",
            "cost_source": cost_source,
            **calls,
        },
        "cost": {"amount": None, "currency": None, "source": None, "billing": "unknown",
                 "note": "no dollar figure is recorded while the billing arrangement is unknown"},
        "product_fit": {
            "time_to_human_acceptance_seconds": None,
            "human_minutes": None,
            "rework_rounds": None,
            "quality_defects": None,
            "acceptance": "NOT_RUN",
            "source": None,
        },
        "baseline": {"status": "ABSENT", "window": None, "unit": None, "value": None, "source": None},
        "target_improvement_pct": TARGET_IMPROVEMENT_PCT,
        "claimed_improvement_pct": None,
    }


def finite_number(value):
    """One rule for "this is a real measured number", used everywhere.

    Rejects bool (True is not 1 observation), NaN, Infinity and -Infinity, and
    anything that is not an int or float. Infinity passed the earlier
    per-field checks in three places and validated as a measurement (review 2,
    report blocker 1); there is now a single helper instead.
    """
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return False
    if value != value:                                   # NaN
        return False
    return value not in (float("inf"), float("-inf"))


def validate_measurement(record):
    """Refuse any gain claim the record cannot support."""
    if isinstance(record, str):
        record = _load_json(record, "measurement record")
    required = {"schema", "contract_version", "deliverable", "collected_at", "comparison_kind",
                "technical", "product_fit", "baseline", "cost", "target_improvement_pct",
                "claimed_improvement_pct"}
    if not isinstance(record, dict) or set(record) != required:
        raise ManifestError("measurement record keys must match the v1 schema exactly")
    if record["schema"] != MEASUREMENT_SCHEMA:
        raise ManifestError(f"measurement schema must be {MEASUREMENT_SCHEMA}")
    if not workflow.valid_timestamp(record.get("collected_at", "")):
        raise ManifestError("measurement collected_at is not a valid past UTC timestamp")
    if not isinstance(record.get("technical"), dict) or not isinstance(record.get("product_fit"), dict):
        raise ManifestError("measurement technical and product_fit must be objects")
    # Every number is typed before anything is derived from it: a count of -1
    # invocations is not a small measurement error (review 1, class 7).
    for field in ("invocations", "aborted", "llm_calls", "input_tokens", "output_tokens",
                  "checker_runs"):
        value = record["technical"].get(field)
        if value is None:
            continue
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise ManifestError(f"measurement technical {field} must be a nonnegative integer or null")
    for field in ("wall_seconds_total", "child_process_wall_seconds_total",
                  "time_to_artifact_seconds"):
        value = record["technical"].get(field)
        if value is None:
            continue
        if not finite_number(value) or value < 0:
            raise ManifestError(f"measurement technical {field} must be a finite nonnegative number or null")
    for field in ("time_to_human_acceptance_seconds", "human_minutes", "rework_rounds",
                  "quality_defects"):
        value = record["product_fit"].get(field)
        if value is None:
            continue
        if not finite_number(value) or value < 0:
            raise ManifestError(f"measurement product_fit {field} must be a finite nonnegative number or null")
    cost = record.get("cost")
    if not isinstance(cost, dict) or cost.get("billing") not in {"unknown", "api", "subscription"}:
        raise ManifestError("measurement cost billing must be unknown, api or subscription")
    amount = cost.get("amount")
    if cost.get("billing") != "api" and amount is not None:
        raise ManifestError("measurement states a cost amount while billing is not metered API usage")
    if amount is not None:
        # A metered amount is a number with a currency and a place it was read
        # from; 'free??' echoed back as a validated cost is not a measurement.
        if not finite_number(amount) or amount < 0:
            raise ManifestError("measurement cost amount must be a finite nonnegative number or null")
        for field in ("currency", "source"):
            if not isinstance(cost.get(field), str) or not cost[field].strip():
                raise ManifestError(
                    f"measurement states a metered cost amount without a {field}; an unattributed "
                    "figure is not a billed cost")
    if record["comparison_kind"] not in {"same-model-process", "cross-model", "unknown"}:
        raise ManifestError("measurement comparison_kind must be same-model-process, cross-model or unknown")
    if record["target_improvement_pct"] != TARGET_IMPROVEMENT_PCT:
        raise ManifestError(f"measurement target_improvement_pct is fixed at {TARGET_IMPROVEMENT_PCT}")
    baseline = record["baseline"]
    fit = record["product_fit"]
    if not isinstance(baseline, dict) or baseline.get("status") not in {"ABSENT", "MEASURED", "ESTIMATED"}:
        raise ManifestError("measurement baseline status must be ABSENT, MEASURED or ESTIMATED")
    if fit.get("acceptance") not in {"NOT_RUN", "PASS", "FAIL", "HOLD"}:
        raise ManifestError("measurement product_fit acceptance must be NOT_RUN, PASS, FAIL or HOLD")
    if baseline["status"] in {"MEASURED", "ESTIMATED"}:
        # A baseline without a window, a unit, a number and a source is a word,
        # and nothing may be divided by a word (review 1, class 7).
        for field in ("window", "unit", "source"):
            if not isinstance(baseline.get(field), str) or not baseline[field].strip():
                raise ManifestError(
                    f"measurement baseline status {baseline['status']} requires a nonempty {field}")
        value = baseline.get("value")
        if not finite_number(value) or value <= 0:
            raise ManifestError("measurement baseline value must be a finite positive number")
    claim = record["claimed_improvement_pct"]
    if claim is not None:
        if not finite_number(claim):
            raise ManifestError("measurement claimed_improvement_pct must be a finite number or null")
        if not 0 < claim <= 100:
            raise ManifestError(
                f"measurement claims {claim}% improvement; a reduction against a measured baseline "
                "is bounded by 100% and a nonpositive claim is not an improvement")
        if baseline["status"] != "MEASURED":
            raise ManifestError(
                f"measurement claims {claim}% improvement with baseline status {baseline['status']}; "
                "a gain against an unmeasured baseline is not a result")
        if fit["acceptance"] != "PASS":
            raise ManifestError(
                f"measurement claims {claim}% improvement while human acceptance is "
                f"{fit['acceptance']}; delivery speed is not product fit")
    caveats = []
    if record["comparison_kind"] == "cross-model":
        caveats.append("comparison_kind is cross-model: a model change is mixed into any delta, "
                       "so this cannot be read as a method effect")
    if baseline["status"] == "ESTIMATED":
        caveats.append("baseline is estimated, not measured")
    if fit["acceptance"] == "PASS":
        caveats.append("product_fit acceptance is a recorded string, not a verified human verdict; "
                       "the actual recipient's acceptance stays NOT_RUN until they say so themselves")
    if record["technical"].get("time_to_artifact_seconds") is None:
        caveats.append("time_to_artifact is null: no invocation has a validated artifact report")
    technical = record["technical"]
    return {
        "schema": "ldl-measurement-validation-v1",
        "verdict": "PASS",
        "comparison_kind": record["comparison_kind"],
        "technical_delivery": "MEASURED" if technical.get("invocations") else "NOT_RUN",
        # A string in a file can record a claim; it cannot verify one.
        "product_fit": {"NOT_RUN": "HOLD", "HOLD": "HOLD",
                        "PASS": "CLAIMED_UNVERIFIED", "FAIL": "FAIL"}[fit["acceptance"]],
        "actual_human_acceptance": "NOT_RUN",
        "cost": {"amount": cost.get("amount"), "billing": cost.get("billing")},
        "improvement": "NOT_MEASURED" if claim is None else f"{claim}% (claimed, not derived here)",
        "target": f"{TARGET_IMPROVEMENT_PCT}% (target, not a result)",
        "caveats": caveats,
    }


# ------------------------------------------------------------------- CLI
def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    # `dest="command"` collided with the job-validate REMAINDER positional of the
    # same name, so the documented invocation crashed on an attribute nobody had
    # set. The runner command is split on `--` before parsing, exactly as
    # invoke.py does, so options after the positionals are still options
    # (review 1, class 5).
    sub = parser.add_subparsers(dest="cmd", required=True)

    job = sub.add_parser("job-validate", description="bind an approved job to a command; "
                                                     "the command follows a literal --")
    job.add_argument("project"); job.add_argument("job")
    job.add_argument("--phase", required=True); job.add_argument("--runner-id", required=True)
    job.add_argument("--runner-role")
    job.add_argument("--approvals-root"); job.add_argument("--approved-job-sha256")
    job.add_argument("--cwd")

    rec = sub.add_parser("reconcile")
    rec.add_argument("project"); rec.add_argument("manifest")
    rec.add_argument("--not-before"); rec.add_argument("--output")

    stat = sub.add_parser("status")
    stat.add_argument("project")
    stat.add_argument("--format", choices=["json", "md"], default="json")
    stat.add_argument("--output")

    ev = sub.add_parser("evaluator-validate"); ev.add_argument("contract")
    ev.add_argument("--expected-sha256",
                    help="the frozen digest recorded by the owner when the template was frozen")

    mc = sub.add_parser("measure-collect")
    mc.add_argument("project"); mc.add_argument("--deliverable", required=True)
    mc.add_argument("--comparison-kind", choices=["same-model-process", "cross-model", "unknown"],
                    default="same-model-process")
    mc.add_argument("--output")

    mv = sub.add_parser("measure-validate"); mv.add_argument("record")

    argv = sys.argv[1:]
    command = []
    if "--" in argv:
        split = argv.index("--")
        argv, command = argv[:split], argv[split + 1:]
    args = parser.parse_args(argv)

    def emit(document, path, text=None):
        payload = text if text is not None else json.dumps(document, indent=2, ensure_ascii=False) + "\n"
        if path:
            with open(path, "w", encoding="utf-8") as handle:
                handle.write(payload)
            print(f"WROTE {path}")
        else:
            sys.stdout.write(payload)

    try:
        if args.cmd == "job-validate":
            if not command:
                raise ManifestError(
                    "job-validate needs the exact command after a literal --, "
                    "because the binding is over argv and nothing else")
            record = check_job(args.project, args.phase, args.runner_id, command, args.job,
                               approvals_root=args.approvals_root, pinned=args.approved_job_sha256,
                               cwd=args.cwd, runner_role=args.runner_role)
            print(f"JOB BOUND - sha256={record['job_sha256']} trust_root={record['approval']['trust_root']} "
                  f"({DISCLAIMER})")
            return 0
        if args.cmd == "reconcile":
            report = reconcile(args.project, args.manifest, not_before=args.not_before)
            emit(report, args.output)
            return 0 if report["verdict"] == "PASS" else 2
        if args.cmd == "status":
            report = status(args.project)
            emit(report, args.output, render_markdown(report) if args.format == "md" else None)
            return 0
        if args.cmd == "evaluator-validate":
            report = validate_evaluator_contract(args.contract, expected_sha256=args.expected_sha256)
            emit(report, None)
            print(f"EVALUATOR FREEZE - {report['freeze']} ({report['freeze_verification']})")
            return 0
        if args.cmd == "measure-collect":
            emit(collect_measurement(args.project, args.deliverable, args.comparison_kind), args.output)
            return 0
        emit(validate_measurement(args.record), None)
        return 0
    except (ManifestError, ApprovalError) as exc:
        print(f"EXECUTION REFUSED - {exc}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
