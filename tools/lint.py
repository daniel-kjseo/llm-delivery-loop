#!/usr/bin/env python3
"""LDL reference lint (stdlib only). Verdict by exit code: 0 = pass, 1 = fail.

  lint.py [workspace_root]     lint a workspace (default: current directory)
  lint.py --selftest           conformance check: plants the three negative
                               fixtures from installation step 4 in a temp
                               workspace and fails unless all are caught

Checks
  L1 broken links      every relative link reachable from index.md resolves
  L2 orphans           every managed .md is reachable from index.md
                       (raw/ is tracked by the manifest, not link-crawled)
  L3 naming            projects/ folders are YYYY-MM-DD_<name>
  L4 contract gate     required sections present and non-empty; >=3 failure
                       conditions; every criterion names a judge; criteria and
                       failure conditions carry no [hypothesis]; the contract
                       cites at least one interview ID (IV-nn)
  L5 raw immutability  hash manifest of raw/ files; a changed hash fails
  L6 log append-only   logs/**/log.md may only grow; rewritten history fails
State for L5/L6 lives in logs/.lint-state.json (created on first run).
"""
import hashlib, json, os, re, sys

LINK = re.compile(r"\]\(([^)]+)\)")
NAME_RULE = re.compile(r"^\d{4}-\d{2}-\d{2}_.+")
SKIP_DIRS = {".git", "node_modules", "tools", "__pycache__"}


class Lint:
    def __init__(self, root):
        self.root = os.path.abspath(root)
        self.errors = []

    def err(self, code, msg):
        self.errors.append(f"[{code}] {msg}")

    def rel(self, p):
        return os.path.relpath(p, self.root)

    # -- helpers ----------------------------------------------------------
    def links_of(self, path):
        try:
            text = open(path, encoding="utf-8").read()
        except OSError:
            return []
        out = []
        for m in LINK.finditer(text):
            t = m.group(1).strip().split("#")[0]
            if not t or t.startswith(("http://", "https://", "mailto:")):
                continue  # external links: warning-level only, never a failure
            out.append(os.path.normpath(os.path.join(os.path.dirname(path), t)))
        return out

    def managed_md(self):
        out = []
        for r, dirs, files in os.walk(self.root):
            dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
            for f in files:
                if f.endswith(".md"):
                    p = os.path.join(r, f)
                    if os.sep + "raw" + os.sep not in p[len(self.root):]:
                        out.append(p)
        return out

    # -- L1 + L2 ----------------------------------------------------------
    def check_links(self):
        index = os.path.join(self.root, "index.md")
        reachable = set()
        if not os.path.exists(index):
            self.err("L1", "index.md missing")
            return
        stack = [index]
        while stack:
            cur = stack.pop()
            if cur in reachable:
                continue
            reachable.add(cur)
            for t in self.links_of(cur):
                if not os.path.exists(t):
                    self.err("L1", f"broken link: {self.rel(cur)} -> {self.rel(t)}")
                elif t.endswith(".md"):
                    stack.append(t)
        for f in self.managed_md():
            if f not in reachable:
                self.err("L2", f"orphan (unreachable from index.md): {self.rel(f)}")

    # -- L3 + L4 ----------------------------------------------------------
    def check_projects(self):
        projdir = os.path.join(self.root, "projects")
        if not os.path.isdir(projdir):
            return
        for d in sorted(os.listdir(projdir)):
            full = os.path.join(projdir, d)
            if not os.path.isdir(full):
                continue
            if not NAME_RULE.match(d):
                self.err("L3", f"project folder naming (YYYY-MM-DD_<name>): projects/{d}")
            self.check_contract(full)

    def check_contract(self, proj):
        c = os.path.join(proj, "00_CONTRACT.md")
        rel = self.rel(c)
        if not os.path.exists(c):
            self.err("L4", f"contract missing: {rel}")
            return
        text = open(c, encoding="utf-8").read()
        for sec in ["2W1H", "Constraints", "Evaluation criteria", "Failure conditions", "Execution plan"]:
            if not re.search(rf"^#+ .*{re.escape(sec)}", text, re.M | re.I):
                self.err("L4", f"{rel}: required section missing - {sec}")
        for field in ["Why", "What", "How"]:
            m = re.search(rf"^- ?\*{{0,2}}{field}\*{{0,2}}[ \t]*:[ \t]*(.*)$", text, re.M)
            if m is None or not m.group(1).strip():
                self.err("L4", f"{rel}: {field} is empty")
        body = "\n".join(l for l in text.splitlines() if not l.lstrip().startswith(">"))
        if not re.search(r"IV-\d{2}", body):
            self.err("L4", f"{rel}: no interview ID (IV-nn) cited - a contract written from inference")

        def section(title):
            m = re.search(rf"^#+ .*{title}.*?$(.*?)(?=^#+ |\Z)", text, re.M | re.S | re.I)
            return m.group(1) if m else ""

        crit = section("Evaluation criteria")
        items = [l for l in crit.splitlines() if re.match(r"^\s*(\d+\.|[-*])\s+\S", l) and not l.strip().startswith(">")]
        for l in items:
            if not re.search(r"judge:\s*(code|human|model|fresh-context)", l, re.I):
                self.err("L4", f"{rel}: criterion without a named judge - {l.strip()[:50]}")
        fail = section("Failure conditions")
        fails = [l for l in fail.splitlines() if re.match(r"^\s*(\d+\.|[-*])\s+\S", l)]
        if len(fails) < 3:
            self.err("L4", f"{rel}: fewer than three failure conditions")
        for name, body in (("Evaluation criteria", crit), ("Failure conditions", fail)):
            if "[hypothesis]" in body:
                self.err("L4", f"{rel}: [hypothesis] inside {name} - an undecidable pass line is pre-contract research")

    # -- L5 + L6 ----------------------------------------------------------
    def check_state(self):
        state_path = os.path.join(self.root, "logs", ".lint-state.json")
        state = {"raw": {}, "logs": {}}
        if os.path.exists(state_path):
            try:
                state = json.load(open(state_path, encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                self.err("L5", "lint state unreadable - delete logs/.lint-state.json to re-baseline")
                return
        # L5: raw/ hash manifest (root and per-project raw/)
        for r, dirs, files in os.walk(self.root):
            dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
            if os.path.basename(r) != "raw":
                continue
            for f in files:
                p = os.path.join(r, f)
                key = self.rel(p)
                h = hashlib.sha256(open(p, "rb").read()).hexdigest()
                if key in state["raw"] and state["raw"][key] != h:
                    self.err("L5", f"raw file changed (immutable): {key}")
                state["raw"][key] = state["raw"].get(key, h)
        # L6: append-only logs
        for r, dirs, files in os.walk(self.root):
            dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
            for f in files:
                if f != "log.md" or os.path.basename(r) != "logs" and "logs" not in self.rel(os.path.join(r, f)).split(os.sep):
                    continue
                p = os.path.join(r, f)
                key = self.rel(p)
                data = open(p, "rb").read()
                prev = state["logs"].get(key)
                if prev:
                    if len(data) < prev["len"] or hashlib.sha256(data[: prev["len"]]).hexdigest() != prev["sha"]:
                        self.err("L6", f"log rewritten (append-only): {key}")
                        continue
                state["logs"][key] = {"len": len(data), "sha": hashlib.sha256(data).hexdigest()}
        if not self.errors:
            os.makedirs(os.path.dirname(state_path), exist_ok=True)
            json.dump(state, open(state_path, "w", encoding="utf-8"), indent=1)

    # -- run --------------------------------------------------------------
    def run(self):
        self.check_links()
        self.check_projects()
        self.check_state()
        if self.errors:
            print(f"LINT FAIL - {len(self.errors)} issue(s)")
            for e in self.errors:
                print("  " + e)
            return 1
        print("LINT PASS")
        return 0


# -- conformance selftest -------------------------------------------------
def selftest():
    import shutil, tempfile
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import scaffold

    tmp = tempfile.mkdtemp(prefix="ldl-selftest-")
    ws = os.path.join(tmp, "ws")
    try:
        scaffold.init(ws)
        proj = scaffold.new_project(ws, "good", "2026-01-01")
        # make the good project pass: fill the contract honestly
        with open(os.path.join(proj, "00_CONTRACT.md"), "w", encoding="utf-8") as f:
            f.write("# 00_CONTRACT — good\n\n[interview](raw/interview.md)\n\n## 2W1H\n- Why: real problem [IV-01]\n- What: one deliverable [IV-02]\n- How: build then verify [IV-03]\n\n## Constraints\n- one week [IV-04]\n\n## Evaluation criteria\n1. output exists — judge: code (test script) [IV-03]\n2. tone approved — judge: human (owner) [IV-05]\n\n## Failure conditions (three, concrete)\n1. wrong output shipped\n2. deadline missed\n3. rework exceeds two hours\n\n## Execution plan\n| phase | path | verify | gate | budget |\n")
        open(os.path.join(proj, "raw", "interview.md"), "w").write("IV-01 ...")
        idx = os.path.join(ws, "index.md")
        with open(idx, "a", encoding="utf-8") as f:
            f.write("- [good](projects/2026-01-01_good/PROGRESS.md)\n")
        base = Lint(ws)
        ok = base.run() == 0
        if not ok:
            print("SELFTEST FAIL: clean workspace should pass")
            return 1
        # fixture 1: below-criteria contract (empty fields, no IV, 2 failures, judge-less criterion)
        bad = scaffold.new_project(ws, "bad", "2026-01-02")
        with open(idx, "a", encoding="utf-8") as f:
            f.write("- [bad](projects/2026-01-02_bad/PROGRESS.md)\n")
        # fixture 2: orphan document
        open(os.path.join(ws, "wiki", "orphan.md"), "w").write("# orphan\n")
        # fixture 3: wrongly named project folder
        os.makedirs(os.path.join(ws, "projects", "Bad Project"))
        lint = Lint(ws)
        lint.run()
        got = "".join(lint.errors)
        need = {"L4": "below-criteria contract", "L2": "orphan document", "L3": "wrong project name"}
        missing = [f"{k} ({v})" for k, v in need.items() if f"[{k}]" not in got]
        if missing:
            print("SELFTEST FAIL: not caught -> " + ", ".join(missing))
            return 1
        print("SELFTEST PASS - clean workspace passes; all three negative fixtures caught")
        return 0
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        sys.exit(selftest())
    root = sys.argv[1] if len(sys.argv) > 1 else "."
    sys.exit(Lint(root).run())
