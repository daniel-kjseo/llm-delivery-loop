#!/usr/bin/env python3
"""LDL reference scaffolder (stdlib only).

  scaffold.py init [path]                 create the workspace tree once
  scaffold.py new <name> [--date D] [--root path]   create one project skeleton

Rename folders or files here, in the script — never per project.
Rewrites in other languages are fine as long as `lint.py --selftest` still passes.
"""
import argparse, datetime, os, sys

WS_DIRS = ["raw", "wiki", "templates", "logs", "tools", "projects"]

WS_FILES = {
    "CLAUDE.md": "# Workspace constitution\n\n> Engraved at install step 3: identity in one sentence / principles / how we work / permissions and limits / scope constraints / center. Written in the user's own words — not copied from the LDL document.\n",
    "RULES.md": "# RULES — prevention rules (the ratchet)\n\n> One rule per lesson, each with its origin. Every task reads this before starting.\n",
    "index.md": "# index — link-closed catalog\n\n> Edit, never append. Every managed document is reachable from here.\n\n## Protocol\n- [Workspace constitution](CLAUDE.md)\n- [RULES.md](RULES.md)\n- [Shared project protocol](projects/CLAUDE.md)\n- [Outer-loop log](logs/log.md)\n\n## Projects\n\n## Wiki\n\n## Held problems\n",
    "logs/log.md": "# Outer-loop log (append-only)\n",
    "projects/CLAUDE.md": "# Shared project protocol\n\n> Engraved at install step 3: Phase 0-6 gates, naming, document and log standards. Read the active project's contract (00_CONTRACT.md) before starting any work.\n",
}

CONTRACT = """# 00_CONTRACT — {name} (Phase 0 · gate 1)

> Interview first: verbatim answers live in [raw/interview.md](raw/interview.md) with IDs (IV-01, ...).
> Every field cites an IV-ID, or carries [hypothesis] with its Phase 3 research item.
> Evaluation criteria and failure conditions can never be hypotheses.

## 2W1H
- Why:
- What:
- How:

## Constraints

## Evaluation criteria
> One per line. Each names its judge: `judge: code (<instrument>)` or `judge: human (<who>)` or `judge: model (<which>)` or `judge: fresh-context`.
1.

## Failure conditions (three, concrete)
1.
2.
3.

## Execution plan
> Per phase: deliverable path / verification method / gate or not / time budget.

## Exit tests (gate 1 opens only after all five pass)
- T1 can it fail: / T2 stranger: / T3 judge: / T4 constraint collision: / T5 primary source:
"""

PROJ_FILES = {
    "00_CONTRACT.md": CONTRACT,
    "01_REQUIREMENTS.md": "# 01_REQUIREMENTS — {name} (Phase 1)\n\n> ID + type + priority + verification method + source (a: primary file / b: IV-ID / c: inference). If (c) exceeds 30%, stop and open a second interview.\n",
    "03_EVIDENCE.md": "# 03_EVIDENCE — {name} (Phase 3 · gate 2)\n\n> Every claim labelled: [hypothesis] / [measured · YYYY-MM-DD] / [proven].\n",
    "04_SCOPE.md": "# 04_SCOPE — {name} (Phase 4 · gate 3)\n\n> 2-3 candidates compared, MECE decomposition (one scope item per requirement ID), dependencies then importance, and what was cut.\n",
    "06_VERIFICATION.md": "# 06_VERIFICATION — {name} (Phase 6 · gate 4, cumulative per increment)\n\n> Pass/fail per requirement ID. The delivery gate stays shut until every ID has a verdict.\n",
    "CLAUDE.md": "# Project constitution — {name} (written in Phase 2)\n\n> Scope constraint in one sentence / permission boundaries / project-specific rules.\n",
    "PROGRESS.md": "# PROGRESS — {name} (review hub)\n\n| Phase | Status | Date | Deliverable |\n|---|---|---|---|\n| P0 contract | pending | | [00_CONTRACT.md](00_CONTRACT.md) |\n| P1 requirements | pending | | [01_REQUIREMENTS.md](01_REQUIREMENTS.md) |\n| P2 structure | pending | | [CLAUDE.md](CLAUDE.md) |\n| P3 research | pending | | [03_EVIDENCE.md](03_EVIDENCE.md) |\n| P4 scoping | pending | | [04_SCOPE.md](04_SCOPE.md) |\n| P5+P6 increments | pending | | [06_VERIFICATION.md](06_VERIFICATION.md) |\n\nEvents: [logs/log.md](logs/log.md)\n",
    "logs/log.md": "# Event log — {name} (append-only)\n",
}


def write(path, content):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    if not os.path.exists(path):
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)


def init(root):
    for d in WS_DIRS:
        os.makedirs(os.path.join(root, d), exist_ok=True)
    for rel, content in WS_FILES.items():
        write(os.path.join(root, rel), content)
    print(root)


NAME_OK = __import__("re").compile(r"^[A-Za-z0-9가-힣][A-Za-z0-9가-힣._-]*$")


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
    for d in ["05_engineering", "raw", "logs/sessions"]:
        os.makedirs(os.path.join(proj, d), exist_ok=True)
    for rel, content in PROJ_FILES.items():
        write(os.path.join(proj, rel), content.format(name=name))
    print(proj)
    return proj


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    p_init = sub.add_parser("init"); p_init.add_argument("path", nargs="?", default="llm-delivery-loop")
    p_new = sub.add_parser("new"); p_new.add_argument("name")
    p_new.add_argument("--date"); p_new.add_argument("--root", default=".")
    a = ap.parse_args()
    if a.cmd == "init":
        init(a.path)
    else:
        new_project(a.root, a.name, a.date)


if __name__ == "__main__":
    main()
