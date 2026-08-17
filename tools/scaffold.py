#!/usr/bin/env python3
"""LDL reference scaffolder (stdlib only).

  scaffold.py init [path]                 create the workspace tree once
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

WS_DIRS = ["raw", "wiki", "templates", "logs", "tools", "projects"]

WS_FILES = {
    ".ldl-version": "0.3.0\n",
    "CLAUDE.md": "# Workspace constitution\n\n> Engraved at install step 3: identity in one sentence / principles / how we work / permissions and limits / scope constraints / center. Written in the user's own words — not copied from the LDL document.\n",
    "RULES.md": "# RULES — prevention rules (the ratchet)\n\n> One rule per lesson, each with its origin. Every task reads this before starting.\n",
    "index.md": "# index — link-closed catalog\n\n> Edit, never append. Every managed document is reachable from here.\n\n## Protocol\n- [Workspace constitution](CLAUDE.md)\n- [RULES.md](RULES.md)\n- [Shared project protocol](projects/CLAUDE.md)\n- [Verifier brief](templates/verifier-brief.md)\n- [Quantitative model](templates/quantitative-model.md)\n- [Outer-loop log](logs/log.md)\n\n## Projects\n\n## Wiki\n\n## Held problems\n",
    "logs/log.md": "# Outer-loop log (append-only)\n",
    "projects/CLAUDE.md": "# Shared project protocol\n\n> Engraved at install step 3: Phase 0-6 gates, naming, document and log standards. Read the active project's contract (00_CONTRACT.md) before starting any work.\n",
    "templates/verifier-brief.md": "# Read-only verifier brief\n\n- Read the contract and primary evidence before the maker verdict.\n- Target access: read-only. Run mutating tools only on a clone or scratch workspace.\n- Record target tree diff before/after; target mutation must be 0 files.\n- Report Harness / Product / Execution readiness / Method conformance separately.\n",
    "templates/quantitative-model.md": "# Quantitative model\n\n- Baseline window:\n- Baseline unit:\n- Candidate window:\n- Candidate unit:\n- Assumptions:\n- Formula/reproducer:\n- Reconciliation:\n\nUse scenarios for conditional outcomes. A confirmation or request is not a successful outcome.\n",
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
    "PROGRESS.md": "# PROGRESS — {name} (review hub)\n\n## Phase progress\n| Phase | Status | Date | Deliverable |\n|---|---|---|---|\n| P0 contract | pending | | [00_CONTRACT.md](00_CONTRACT.md) |\n| P1 requirements | pending | | [01_REQUIREMENTS.md](01_REQUIREMENTS.md) |\n| P2 structure | pending | | [CLAUDE.md](CLAUDE.md) |\n| P3 research | pending | | [03_EVIDENCE.md](03_EVIDENCE.md) |\n| P4 scoping | pending | | [04_SCOPE.md](04_SCOPE.md) |\n| P5+P6 increments | pending | | [06_VERIFICATION.md](06_VERIFICATION.md) |\n\n## Gate ledger\n| Gate | Verdict | Contract version | Approval mode | Approver | Approved at | Evidence |\n|---|---|---|---|---|---|---|\n| G1 | PENDING | v1 | human | | | |\n| G2 | PENDING | v1 | human | | | |\n| G3 | PENDING | v1 | human | | | |\n| G4 | PENDING | v1 | human | | | |\n\nEvents: [logs/log.md](logs/log.md)\n",
    "logs/log.md": "# Event log — {name} (append-only)\n\n> On each Gate PASS append exactly: `GATE-PASS: G1 contract=v1`. On a method violation append: `LDL-VIOLATION: <id>`.\n",
}


def write(path, content):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    if not os.path.exists(path):
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(content)


def init(root, migrate_v03=False):
    existed = os.path.isdir(root) and bool(os.listdir(root))
    marker = os.path.join(root, ".ldl-version")
    if existed and not os.path.isfile(marker) and not migrate_v03:
        sys.exit("existing marker-free workspace: explicit migration required (--migrate-v03)")
    for directory in WS_DIRS:
        os.makedirs(os.path.join(root, directory), exist_ok=True)
    for rel, content in WS_FILES.items():
        write(os.path.join(root, rel), content)
    source_dir = os.path.dirname(os.path.abspath(__file__))
    for name in ("scaffold.py", "lint.py", "integrity.py"):
        source = os.path.join(source_dir, name)
        target = os.path.join(root, "tools", name)
        if os.path.isfile(source) and not os.path.exists(target):
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
    for directory in ["05_engineering", "raw", "logs/sessions"]:
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
    p_new = sub.add_parser("new")
    p_new.add_argument("name")
    p_new.add_argument("--date")
    p_new.add_argument("--root", default=".")
    args = parser.parse_args()
    if args.cmd == "init":
        init(args.path, args.migrate_v03)
    else:
        new_project(args.root, args.name, args.date)


if __name__ == "__main__":
    main()
