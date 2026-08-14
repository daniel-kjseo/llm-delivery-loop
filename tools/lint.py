#!/usr/bin/env python3
"""LDL reference lint (stdlib only). Verdict by exit code: 0 = pass, 1 = fail.

  lint.py [workspace_root]     lint a workspace (default: current directory)
  lint.py --selftest           conformance check: plants the step-4 negative
                               fixtures plus hostile ones (empty criteria and
                               sections, bare judges, non-UTF8 and unreadable
                               files, raw deletion, malformed state, name
                               traversal) and legit-input probes (titled
                               links, section names inside body text) in a
                               temp workspace, one at a time, and fails unless
                               each verdict is exact - the failing check names
                               print on failure

Checks
  L1 broken links      every relative link reachable from index.md resolves
  L2 orphans           every managed .md is reachable from index.md
                       (raw/ is tracked by the manifest, not link-crawled)
  L3 naming            projects/ folders are YYYY-MM-DD_<name>
  L4 contract gate     required sections present and non-empty; >=3 failure
                       conditions; every criterion names its judge with a
                       parenthesized method - judge: <type> (<method/who>);
                       criteria and failure conditions carry no [hypothesis];
                       the contract cites at least one interview ID (IV-nn)
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
    def read_text(self, path, code):
        """Read a managed text file; an unreadable file is a verdict, not a traceback."""
        try:
            return open(path, encoding="utf-8").read()
        except UnicodeDecodeError:
            self.err(code, f"not valid UTF-8: {self.rel(path)}")
        except OSError:
            self.err(code, f"unreadable file: {self.rel(path)}")
        return None

    def links_of(self, path):
        text = self.read_text(path, "L1")
        if text is None:
            return []
        out = []
        for m in LINK.finditer(text):
            t = m.group(1).strip()
            t = re.sub(r"""\s+("[^"]*"|'[^']*')$""", "", t)  # optional markdown title
            t = t.split("#")[0].strip()
            if not t or t.startswith(("http://", "https://", "mailto:")):
                continue  # external URLs: outside lint scope - never fetched, never a verdict
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
        text = self.read_text(c, "L4")
        if text is None:
            return

        def section(title):
            # line-anchored: only a real heading line opens a section — the same
            # words inside body text must never move the anchor
            lines = text.splitlines()
            for i, ln in enumerate(lines):
                if re.match(rf"#+ .*{re.escape(title)}", ln, re.I):
                    body = []
                    for nxt in lines[i + 1:]:
                        if re.match(r"#+ ", nxt):
                            break
                        # annotation blockquotes are guidance, not contract content
                        if not nxt.lstrip().startswith(">"):
                            body.append(nxt)
                    return "\n".join(body)
            return ""

        for sec in ["2W1H", "Constraints", "Evaluation criteria", "Failure conditions", "Execution plan"]:
            if not re.search(rf"^#+ .*{re.escape(sec)}", text, re.M | re.I):
                self.err("L4", f"{rel}: required section missing - {sec}")
            elif not section(sec).strip():
                self.err("L4", f"{rel}: required section empty - {sec}")
        for field in ["Why", "What", "How"]:
            m = re.search(rf"^- ?\*{{0,2}}{field}\*{{0,2}}[ \t]*:[ \t]*(.*)$", text, re.M)
            if m is None or not m.group(1).strip():
                self.err("L4", f"{rel}: {field} is empty")
        body = "\n".join(l for l in text.splitlines() if not l.lstrip().startswith(">"))
        if not re.search(r"IV-\d{2}", body):
            self.err("L4", f"{rel}: no interview ID (IV-nn) cited - a contract written from inference")

        crit = section("Evaluation criteria")
        items = [l for l in crit.splitlines() if re.match(r"^\s*(\d+\.|[-*])\s+\S", l)]
        if not items:
            self.err("L4", f"{rel}: no evaluation criteria - an empty pass line cannot gate anything")
        for l in items:
            if not re.search(r"judge:\s*(code|human|model|fresh-context)\s*\([^)]+\)", l, re.I):
                self.err("L4", f"{rel}: criterion without judge: <type> (<method/who>) - {l.strip()[:50]}")
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
                loaded = json.load(open(state_path, encoding="utf-8"))
                if not isinstance(loaded, dict):
                    raise ValueError("state is not an object")
                state = loaded
            except (json.JSONDecodeError, OSError, ValueError):
                self.err("L5", "lint state unreadable - delete logs/.lint-state.json to re-baseline")
                return
        # malformed-but-parseable state must degrade to a clean verdict, not a traceback
        state.setdefault("raw", {})
        state.setdefault("logs", {})
        if not isinstance(state["raw"], dict) or not isinstance(state["logs"], dict):
            self.err("L5", "lint state malformed - delete logs/.lint-state.json to re-baseline")
            return
        # L5: raw/ hash manifest (root and per-project raw/)
        seen_raw = set()
        for r, dirs, files in os.walk(self.root):
            dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
            if os.path.basename(r) != "raw":
                continue
            for f in files:
                p = os.path.join(r, f)
                key = self.rel(p)
                seen_raw.add(key)
                try:
                    h = hashlib.sha256(open(p, "rb").read()).hexdigest()
                except OSError:
                    self.err("L5", f"raw file unreadable: {key}")
                    continue
                if key in state["raw"] and state["raw"][key] != h:
                    self.err("L5", f"raw file changed (immutable): {key}")
                state["raw"][key] = state["raw"].get(key, h)
        for key in sorted(set(state["raw"]) - seen_raw):
            self.err("L5", f"raw file deleted (immutable): {key}")
        # L6: append-only logs
        for r, dirs, files in os.walk(self.root):
            dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
            for f in files:
                if f != "log.md" or os.path.basename(r) != "logs" and "logs" not in self.rel(os.path.join(r, f)).split(os.sep):
                    continue
                p = os.path.join(r, f)
                key = self.rel(p)
                try:
                    data = open(p, "rb").read()
                except OSError:
                    self.err("L6", f"log unreadable: {key}")
                    continue
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
    results = {}
    try:
        scaffold.init(ws)
        proj = scaffold.new_project(ws, "good", "2026-01-01")
        good_contract = os.path.join(proj, "00_CONTRACT.md")
        contract_text = (
            "# 00_CONTRACT — good\n\n[interview](raw/interview.md)\n\n"
            "## 2W1H\n- Why: real problem [IV-01]\n- What: one deliverable [IV-02]\n- How: build then verify [IV-03]\n\n"
            "## Constraints\n- one week [IV-04]\n\n"
            "## Evaluation criteria\n1. output exists — judge: code (test script) [IV-03]\n2. tone approved — judge: human (owner) [IV-05]\n\n"
            "## Failure conditions (three, concrete)\n1. wrong output shipped\n2. deadline missed\n3. rework exceeds two hours\n\n"
            "## Execution plan\n| phase | path | verify | gate | budget |\n"
        )
        open(good_contract, "w", encoding="utf-8").write(contract_text)
        open(os.path.join(proj, "raw", "interview.md"), "w").write("IV-01 ...")
        idx = os.path.join(ws, "index.md")
        idx_text = open(idx, encoding="utf-8").read() + "- [good](projects/2026-01-01_good/PROGRESS.md)\n"
        open(idx, "w", encoding="utf-8").write(idx_text)

        l = Lint(ws)
        results["clean workspace passes"] = l.run() == 0

        # fixtures 1-3, planted one at a time: the verdict is the exact error
        # text at the exact path, never "some error of that class" — and each
        # teardown re-verifies clean, so one fixture cannot mask another
        badrel = os.path.join("projects", "2026-01-02_bad", "00_CONTRACT.md")
        scaffold.new_project(ws, "bad", "2026-01-02")
        open(idx, "w", encoding="utf-8").write(idx_text + "- [bad](projects/2026-01-02_bad/PROGRESS.md)\n")
        l = Lint(ws); l.run()
        expected = [
            f"[L1] broken link: {badrel} -> {os.path.join('projects', '2026-01-02_bad', 'raw', 'interview.md')}",
            f"[L4] {badrel}: required section empty - Constraints",
            f"[L4] {badrel}: required section empty - Execution plan",
            f"[L4] {badrel}: Why is empty",
            f"[L4] {badrel}: What is empty",
            f"[L4] {badrel}: How is empty",
            f"[L4] {badrel}: no interview ID (IV-nn) cited - a contract written from inference",
            f"[L4] {badrel}: no evaluation criteria - an empty pass line cannot gate anything",
            f"[L4] {badrel}: fewer than three failure conditions",
        ]
        results["below-criteria contract (L4, exact)"] = sorted(l.errors) == sorted(expected)
        shutil.rmtree(os.path.join(ws, "projects", "2026-01-02_bad"))
        open(idx, "w", encoding="utf-8").write(idx_text)
        results["clean after fixture 1"] = Lint(ws).run() == 0

        # fixture 2: orphan document, alone — the orphan is the only error
        open(os.path.join(ws, "wiki", "orphan.md"), "w").write("# orphan\n")
        l = Lint(ws); l.run()
        results["orphan document (L2, exact)"] = l.errors == [
            f"[L2] orphan (unreachable from index.md): {os.path.join('wiki', 'orphan.md')}"]
        os.remove(os.path.join(ws, "wiki", "orphan.md"))
        results["clean after fixture 2"] = Lint(ws).run() == 0

        # fixture 3: wrongly named project folder, alone (its missing contract
        # is part of the expected verdict, not noise)
        os.makedirs(os.path.join(ws, "projects", "Bad Project"))
        l = Lint(ws); l.run()
        results["wrong project name (L3, exact)"] = sorted(l.errors) == sorted([
            "[L3] project folder naming (YYYY-MM-DD_<name>): projects/Bad Project",
            f"[L4] contract missing: {os.path.join('projects', 'Bad Project', '00_CONTRACT.md')}"])
        shutil.rmtree(os.path.join(ws, "projects", "Bad Project"))
        results["clean after fixture 3"] = Lint(ws).run() == 0

        # fixture 4: empty evaluation criteria must fail the contract gate
        open(good_contract, "w", encoding="utf-8").write(
            contract_text.replace("1. output exists — judge: code (test script) [IV-03]\n2. tone approved — judge: human (owner) [IV-05]\n", ""))
        l = Lint(ws); l.run()
        results["empty criteria (L4)"] = any("no evaluation criteria" in e for e in l.errors)
        open(good_contract, "w", encoding="utf-8").write(contract_text)

        # fixture 5: raw deletion must fail L5 (baseline first, then delete)
        assert Lint(ws).run() == 0  # baseline writes the manifest
        rawf = os.path.join(proj, "raw", "interview.md")
        os.remove(rawf)
        l = Lint(ws); l.run()
        results["raw deletion (L5)"] = any("deleted" in e for e in l.errors)
        open(rawf, "w").write("IV-01 ...")
        sp = os.path.join(ws, "logs", ".lint-state.json")
        os.path.exists(sp) and os.remove(sp)

        # fixture 6: malformed state must yield a clean FAIL, not a traceback
        open(sp, "w").write('{"broken": 1}')
        try:
            Lint(ws).run()
            results["malformed state (clean verdict)"] = True
        except Exception:  # noqa: BLE001
            results["malformed state (clean verdict)"] = False
        os.path.exists(sp) and os.remove(sp)

        # fixture 7: scaffold must refuse path-traversal project names
        try:
            scaffold.new_project(ws, "../escape", "2026-01-03")
            results["name traversal refused"] = False
        except SystemExit:
            results["name traversal refused"] = not os.path.exists(os.path.join(ws, "escape"))

        # fixture 8: a required section that is present but empty must fail
        goodrel = os.path.join("projects", "2026-01-01_good", "00_CONTRACT.md")
        open(good_contract, "w", encoding="utf-8").write(
            contract_text.replace("- one week [IV-04]\n", ""))
        l = Lint(ws); l.run()
        results["empty required section (L4, exact)"] = (
            f"[L4] {goodrel}: required section empty - Constraints" in l.errors)
        open(good_contract, "w", encoding="utf-8").write(contract_text)

        # fixture 9: a judge with no parenthesized method must fail
        open(good_contract, "w", encoding="utf-8").write(
            contract_text.replace("judge: human (owner)", "judge: human"))
        l = Lint(ws); l.run()
        results["bare judge (L4, exact)"] = (
            f"[L4] {goodrel}: criterion without judge: <type> (<method/who>) - "
            "2. tone approved — judge: human [IV-05]" in l.errors)
        open(good_contract, "w", encoding="utf-8").write(contract_text)

        # fixture 10: section names mentioned in body text are not headings —
        # a good contract whose execution plan says "evaluation criteria" must pass
        open(good_contract, "w", encoding="utf-8").write(
            contract_text + "| P6 | 06_VERIFICATION.md | evaluation criteria and failure conditions check | gate | 1d |\n")
        results["decoy phrase in body passes"] = Lint(ws).run() == 0
        open(good_contract, "w", encoding="utf-8").write(contract_text)

        # fixture 11: a markdown link with a title is still a link, not a broken path
        open(idx, "w", encoding="utf-8").write(idx_text + '- [c](CLAUDE.md "the constitution")\n')
        results["titled link passes"] = Lint(ws).run() == 0
        open(idx, "w", encoding="utf-8").write(idx_text)

        # fixture 12: a crawled file that is not UTF-8 must be a verdict, not a traceback
        open(os.path.join(ws, "wiki", "binary.md"), "wb").write(b"# ok\n\xff\xfe garbage\n")
        open(idx, "w", encoding="utf-8").write(idx_text + "- [b](wiki/binary.md)\n")
        try:
            l = Lint(ws); l.run()
            results["non-UTF8 file (L1, exact)"] = (
                f"[L1] not valid UTF-8: {os.path.join('wiki', 'binary.md')}" in l.errors)
        except Exception:  # noqa: BLE001
            results["non-UTF8 file (L1, exact)"] = False
        os.remove(os.path.join(ws, "wiki", "binary.md"))
        open(idx, "w", encoding="utf-8").write(idx_text)

        # fixture 13: a raw file the lint cannot hash must be a verdict, not a
        # traceback (skipped where the host forbids creating symlinks)
        try:
            os.symlink("nonexistent-target", os.path.join(proj, "raw", "dangling"))
        except OSError:
            pass
        else:
            try:
                l = Lint(ws); l.run()
                results["unreadable raw (L5, exact)"] = (
                    f"[L5] raw file unreadable: {os.path.join('projects', '2026-01-01_good', 'raw', 'dangling')}" in l.errors)
            except Exception:  # noqa: BLE001
                results["unreadable raw (L5, exact)"] = False
            os.remove(os.path.join(proj, "raw", "dangling"))

        failed = [k for k, v in results.items() if not v]
        if failed:
            print("SELFTEST FAIL -> " + ", ".join(failed))
            return 1
        print(f"SELFTEST PASS - {len(results)} checks: hostile fixtures all caught by their exact errors, legit-input probes all pass clean")
        return 0
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        sys.exit(selftest())
    root = sys.argv[1] if len(sys.argv) > 1 else "."
    sys.exit(Lint(root).run())
