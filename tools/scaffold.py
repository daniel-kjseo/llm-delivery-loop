#!/usr/bin/env python3
"""LDL reference scaffolder (stdlib only).

  scaffold.py init [path] [--migrate-v04] create or explicitly upgrade the workspace
  scaffold.py new <name> [--date D] [--root path]   create one project skeleton

Rename folders or files here, in the script — never per project.
Rewrites in other languages are fine as long as `lint.py --selftest` still passes.
"""
import argparse
import datetime
import os
import re
import shutil
import sys

WS_DIRS = ["raw", "wiki", "templates", "logs", "tools", "projects", "owner"]

WS_FILES = {
    ".ldl-version": "0.4.0\n",
    "CLAUDE.md": "# Workspace constitution\n\n> Engraved at install step 3: identity in one sentence / principles / how we work / permissions and limits / scope constraints / center. Written in the user's own words — not copied from the LDL document.\n",
    "RULES.md": "# RULES — prevention rules (the ratchet)\n\n> One rule per lesson, each with its origin. Every task reads this before starting.\n",
    "index.md": "# index — link-closed catalog\n\n> Edit, never append. Every managed document is reachable from here.\n\n## Protocol\n- [Workspace constitution](CLAUDE.md)\n- [RULES.md](RULES.md)\n- [Shared project protocol](projects/CLAUDE.md)\n- [Verifier brief](templates/verifier-brief.md)\n- [Quantitative model](templates/quantitative-model.md)\n- [Lean phase packet](templates/phase-packet.json)\n- [MVP evidence manifest](templates/mvp-evidence.json)\n- [Release evidence manifest](templates/release-evidence.json)\n- [Owner inbox](owner/inbox.md)\n- [Owner outbox](owner/outbox.md)\n- [Outer-loop log](logs/log.md)\n\n## Projects\n\n## Wiki\n\n## Held problems\n",
    "logs/log.md": "# Outer-loop log (append-only)\n",
    "projects/CLAUDE.md": "# Shared project protocol\n\n> Engraved at install step 3: Phase 0-6 gates, naming, document and log standards. Read the active project's contract (00_CONTRACT.md) before starting any work.\n",
    "templates/verifier-brief.md": "# Read-only verifier brief\n\n- Read the contract and primary evidence before the maker verdict.\n- Target access: read-only. Run mutating tools only on a clone or scratch workspace.\n- Record target tree diff before/after; target mutation must be 0 files.\n- Report Harness / Product / Execution readiness / Method conformance separately.\n",
    "templates/quantitative-model.md": "# Quantitative model\n\n- Baseline window:\n- Baseline unit:\n- Candidate window:\n- Candidate unit:\n- Assumptions:\n- Formula/reproducer:\n- Reconciliation:\n\nUse scenarios for conditional outcomes. A confirmation or request is not a successful outcome.\n",
    "templates/phase-packet.json": "{\n  \"schema\": \"ldl-phase-packet-v1\",\n  \"phase\": \"P5\",\n  \"task\": \"one bounded increment\",\n  \"summary\": \"path+hash handles only; no verbatim reports\",\n  \"requirements\": [],\n  \"commands\": [],\n  \"blockers\": [],\n  \"artifacts\": []\n}\n",
    "templates/mvp-evidence.json": "{\n  \"schema\": \"ldl-mvp-evidence-v1\",\n  \"increment\": \"MVP-1\",\n  \"user_journey\": \"one real end-to-end user journey\",\n  \"deterministic\": {\"status\": \"NOT_RUN\", \"command\": \"\", \"checks\": 0, \"artifact\": {\"path\": \"05_engineering/evidence/deterministic/tests.txt\", \"sha256\": \"\"}},\n  \"rendered\": {\"status\": \"NOT_RUN\", \"instrument\": \"\", \"cases\": 0, \"console_errors\": 0, \"artifact\": {\"path\": \"05_engineering/evidence/rendered/render.txt\", \"sha256\": \"\"}},\n  \"independent\": {\"status\": \"NOT_RUN\", \"verifier\": \"\", \"target_mutation\": 0, \"artifact\": {\"path\": \"05_engineering/evidence/independent/report.txt\", \"sha256\": \"\"}}\n}\n",
    "templates/release-evidence.json": "{\n  \"schema\": \"ldl-release-evidence-v1\",\n  \"release\": \"RELEASE-1\",\n  \"increment\": \"MVP-1\",\n  \"live_url\": \"https://example.com\",\n  \"released_at\": \"YYYY-MM-DDTHH:MM:SSZ\",\n  \"smoke\": {\"status\": \"NOT_RUN\", \"cases\": 0, \"console_errors\": 0, \"artifact\": {\"path\": \"05_engineering/evidence/release/smoke.txt\", \"sha256\": \"\"}},\n  \"telemetry\": {\"status\": \"NOT_RUN\", \"event\": \"\", \"artifact\": {\"path\": \"05_engineering/evidence/release/telemetry.txt\", \"sha256\": \"\"}},\n  \"rollback\": {\"status\": \"NOT_RUN\", \"command\": \"\", \"artifact\": {\"path\": \"05_engineering/evidence/release/rollback.txt\", \"sha256\": \"\"}},\n  \"feedback\": {\"status\": \"NOT_RUN\", \"channel\": \"\", \"artifact\": {\"path\": \"05_engineering/evidence/release/feedback.txt\", \"sha256\": \"\"}}\n}\n",
    "owner/inbox.md": "# Owner inbox\n\n> Maker writes requests here. Owner does not edit project trees.\n",
    "owner/outbox.md": "# Owner outbox\n\n> Owner writes decisions here. Maker preserves accepted decisions once under project raw/.\n",
}

CONTRACT = """# 00_CONTRACT — {name} (Phase 0 · gate 1)

> Interview first: verbatim answers live in [raw/interview.md](raw/interview.md) with IDs (IV-01, ...).
> Every field cites an IV-ID, or carries [hypothesis] with its Phase 3 research item.
> Evaluation criteria and failure conditions can never be hypotheses.

## Governance profile
- Contract version: v1
- Approval mode: human
- Quantitative claims: no
- Risk level: low

## Delivery profile
- Delivery mode: startup-reversible
- First executable increment: MVP-1
- Release strategy: ship-first

## Launch brief
- Target user:
- Problem:
- Smallest value journey:
- Launch metric:
- Feedback channel:
- Kill criteria:
- Timebox:
- Risk: low-reversible
- Rollback:

## 2W1H
- Why:
- What:
- How:

## Constraints

## Evaluation criteria
> One per line: `judge: code (<instrument>)` / `judge: human (<who>)` / `judge: model (<which>)` / `judge: fresh-context (<of what>)`.
1.

## Failure conditions (three, concrete)
1.
2.
3.

## Execution plan
> Per phase: deliverable path / verification method / gate or not / time budget.

## Execution economy
- Phase packet max bytes: 8192
- Relay summary max chars: 1500
- Checker summary max chars: 4000
- Checker runs per increment: 1
- Correction reruns per increment: 1
- Token/call ledger: logs/cost-ledger.csv

## Verification setup
> Named at contract time. The verifier works outside the target and leaves it unchanged.
- Verifier instances: <who or what judges each criterion>
- Lint command: <exact command and cwd>
- Approver: <the human or pre-authorized delegated agent>
- Verifier workspace: <external reviews or scratch path>
- Target access: read-only

## Exit tests (gate 1 opens only after all five pass)
- T1 can it fail:
- T2 stranger:
- T3 judge:
- T4 constraint collision:
- T5 primary source:
"""

PROJ_FILES = {
    "00_CONTRACT.md": CONTRACT,
    "01_REQUIREMENTS.md": "# 01_REQUIREMENTS — {name} (Phase 1)\n\n> Source starts with `(a)` primary file, `(b)` interview ID, or `(c)` inference. If inference exceeds 30%, stop and open a second interview.\n\n## Requirements ledger\n| Requirement ID | Type | Priority | Requirement | Verification | Source |\n|---|---|---|---|---|---|\n",
    "03_EVIDENCE.md": "# 03_EVIDENCE — {name} (Phase 3 · gate 2)\n\n## Evidence ledger\n| Claim ID | Label | Claim | Source artifact | Captured at | Scope/window | Transform/reproducer | Status |\n|---|---|---|---|---|---|---|---|\n",
    "04_SCOPE.md": "# 04_SCOPE — {name} (Phase 4 · gate 3)\n\n> Compare 2-3 candidates, map every requirement once, and state what was cut.\n\n## Impact dimensions\n| Dimension ID | Status | Evidence |\n|---|---|---|\n\n## Action readiness\n| Action ID | Impact dimensions | Preconditions | Approval tier | Approval evidence | Canary | Rollback | Ready |\n|---|---|---|---|---|---|---|---|\n\n## Quantitative model\n> Required only when `Quantitative claims: yes`. Keep periods and units comparable; use scenarios instead of one blended range.\n- Baseline window:\n- Baseline unit:\n- Candidate window:\n- Candidate unit:\n- Assumptions:\n- Formula/reproducer:\n- Reconciliation:\n",
    "06_VERIFICATION.md": "# 06_VERIFICATION — {name} (Phase 6 · gate 4)\n\n## Requirement verdicts\n| Requirement ID | Verdict | Evidence |\n|---|---|---|\n\n## Final verdicts\n- Harness: NOT_RUN\n- Product: NOT_RUN\n- Execution readiness: HOLD\n- Method conformance: PASS\n- Historical violations: NONE\n- Independent verifier: fresh-context (unassigned)\n- Target mutation: 0 files\n",
    "CLAUDE.md": "# Project constitution — {name} (written in Phase 2)\n\n> Scope constraint / permission boundaries / project-specific rules. Any impacted dimension on HOLD blocks every linked action.\n",
    "PROGRESS.md": "# PROGRESS — {name} (review hub)\n\n## Phase progress\n| Phase | Status | Date | Deliverable |\n|---|---|---|---|\n| P0 contract | pending | | [00_CONTRACT.md](00_CONTRACT.md) |\n| P1 requirements | pending | | [01_REQUIREMENTS.md](01_REQUIREMENTS.md) |\n| P2 structure | pending | | [CLAUDE.md](CLAUDE.md) |\n| P3 research | pending | | [03_EVIDENCE.md](03_EVIDENCE.md) |\n| P4 scoping | pending | | [04_SCOPE.md](04_SCOPE.md) |\n| P5+P6 increments | pending | | [06_VERIFICATION.md](06_VERIFICATION.md) |\n\n## Gate ledger\n| Gate | Verdict | Contract version | Approval mode | Approver | Approved at | Evidence |\n|---|---|---|---|---|---|---|\n| G1 | PENDING | v1 | human | | | |\n| G2 | PENDING | v1 | human | | | |\n| G3 | PENDING | v1 | human | | | |\n| G4 | PENDING | v1 | human | | | |\n\n## Increment ledger\n| Increment | Experiment | User journey | Status | Deterministic tests | Rendered/browser | Independent check | Evidence |\n|---|---|---|---|---|---|---|---|\n| MVP-1 | LAUNCH | one real user completes the smallest end-to-end journey | PENDING | NOT_RUN | NOT_RUN | NOT_RUN | pending |\n\n## Release ledger\n| Release | Verdict | Increment | Risk | Instrumentation | Feedback | Rollback | Live artifact | Approver | Released at | Evidence |\n|---|---|---|---|---|---|---|---|---|---|---|\n| RELEASE-1 | PENDING | MVP-1 | low-reversible | NOT_RUN | NOT_RUN | NOT_RUN | pending | | | pending |\n\n## Experiment ledger\n| Experiment | Hypothesis | Change | Metric | Status | Evidence | Decision |\n|---|---|---|---|---|---|---|\n| EXP-1 | real users complete the core journey | next smallest change | completion rate | NOT_RUN | pending | PENDING |\n\nEvents: [logs/log.md](logs/log.md)\n",
    "logs/log.md": "# Event log — {name} (append-only)\n\n> On each Gate PASS append exactly: `GATE-PASS: G1 contract=v1`. On a method violation append: `LDL-VIOLATION: <id>`.\n",
    "logs/cost-ledger.csv": "timestamp,phase,role,model,input_tokens,output_tokens,cache_tokens,llm_calls,checker_runs,wall_seconds,evidence\n",
}


def write(path, content):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    if not os.path.exists(path):
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(content)


def init(root, migrate_v03=False, migrate_v04=False):
    existed = os.path.isdir(root) and bool(os.listdir(root))
    marker = os.path.join(root, ".ldl-version")
    if existed and not os.path.isfile(marker) and not migrate_v03:
        sys.exit("existing marker-free workspace: explicit migration required (--migrate-v03)")
    if os.path.isfile(marker):
        with open(marker, encoding="utf-8") as handle:
            current = handle.read().strip()
        if current not in {"0.3.0", "0.4.0"}:
            sys.exit(f"unsupported workspace schema: {current or 'empty'}")
        if current == "0.3.0" and not migrate_v04:
            print(root)
            return
        if current == "0.3.0" and migrate_v04:
            projects = os.path.join(root, "projects")
            active = []
            if os.path.isdir(projects):
                active = [name for name in os.listdir(projects)
                          if os.path.isdir(os.path.join(projects, name))]
            if active:
                sys.exit("v0.4 migration requires no active projects; close/archive or migrate each contract explicitly first")
            index = os.path.join(root, "index.md")
            if os.path.isfile(index):
                with open(index, encoding="utf-8") as handle:
                    index_text = handle.read()
                if "## Protocol\n" not in index_text:
                    sys.exit("workspace index has no Protocol section for v0.4 migration")
    for directory in WS_DIRS:
        os.makedirs(os.path.join(root, directory), exist_ok=True)
    for rel, content in WS_FILES.items():
        write(os.path.join(root, rel), content)
    if migrate_v04 and os.path.isfile(marker):
        with open(marker, encoding="utf-8") as handle:
            current = handle.read().strip()
        if current not in {"0.3.0", "0.4.0"}:
            sys.exit(f"cannot migrate unsupported schema to v0.4: {current or 'empty'}")
        with open(marker, "w", encoding="utf-8") as handle:
            handle.write("0.4.0\n")
        index = os.path.join(root, "index.md")
        if os.path.isfile(index):
            with open(index, encoding="utf-8") as handle:
                text = handle.read()
            additions = [
                "- [Lean phase packet](templates/phase-packet.json)",
                "- [MVP evidence manifest](templates/mvp-evidence.json)",
                "- [Release evidence manifest](templates/release-evidence.json)",
                "- [Owner inbox](owner/inbox.md)",
                "- [Owner outbox](owner/outbox.md)",
            ]
            missing = [line for line in additions if line not in text]
            if missing:
                marker_line = "## Protocol\n"
                text = text.replace(marker_line, marker_line + "\n".join(missing) + "\n", 1)
                with open(index, "w", encoding="utf-8") as handle:
                    handle.write(text)
    source_dir = os.path.dirname(os.path.abspath(__file__))
    for name in ("scaffold.py", "lint.py", "integrity.py", "lean.py"):
        source = os.path.join(source_dir, name)
        target = os.path.join(root, "tools", name)
        if os.path.isfile(source) and (migrate_v04 or not os.path.exists(target)):
            shutil.copy2(source, target)
    print(root)


NAME_OK = re.compile(r"^[A-Za-z0-9가-힣][A-Za-z0-9가-힣._-]*$")


def new_project(root, name, date=None):
    if not NAME_OK.match(name):
        sys.exit(f"invalid project name (letters, digits, . _ - only; no path separators): {name!r}")
    date = date or datetime.date.today().isoformat()
    projects = os.path.realpath(os.path.join(root, "projects"))
    proj = os.path.realpath(os.path.join(projects, f"{date}_{name}"))
    if os.path.dirname(proj) != projects:
        sys.exit(f"refusing to write outside projects/: {proj}")
    if os.path.exists(proj):
        sys.exit(f"already exists: {proj}")
    for directory in ["05_engineering/evidence/deterministic", "05_engineering/evidence/rendered", "05_engineering/evidence/independent", "05_engineering/evidence/release", "05_engineering/evidence/experiments", "05_engineering/evidence/increments", "raw", "logs/sessions"]:
        os.makedirs(os.path.join(proj, directory), exist_ok=True)
    for rel, content in PROJ_FILES.items():
        write(os.path.join(proj, rel), content.format(name=name))
    index = os.path.join(root, "index.md")
    if not os.path.isfile(index):
        sys.exit(f"workspace index missing (run init first): {index}")
    entry = f"- [{name}](projects/{date}_{name}/PROGRESS.md)\n"
    with open(index, encoding="utf-8") as handle:
        text = handle.read()
    marker = "## Projects\n"
    if marker not in text:
        sys.exit(f"workspace index has no Projects section: {index}")
    if entry not in text:
        with open(index, "w", encoding="utf-8") as handle:
            handle.write(text.replace(marker, marker + entry, 1))
    print(proj)
    return proj


def main():
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="cmd", required=True)
    p_init = sub.add_parser("init")
    p_init.add_argument("path", nargs="?", default="llm-delivery-loop")
    p_init.add_argument("--migrate-v03", action="store_true")
    p_init.add_argument("--migrate-v04", action="store_true")
    p_new = sub.add_parser("new")
    p_new.add_argument("name")
    p_new.add_argument("--date")
    p_new.add_argument("--root", default=".")
    args = parser.parse_args()
    if args.cmd == "init":
        init(args.path, args.migrate_v03, args.migrate_v04)
    else:
        new_project(args.root, args.name, args.date)


if __name__ == "__main__":
    main()
