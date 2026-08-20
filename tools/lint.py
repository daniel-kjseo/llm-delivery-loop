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
  L4 contract gate     required sections and verification fields present, with real content judged
                       as it renders (tags/comments dropped, character
                       references decoded) - bare dashes or underscores and
                       a lone table header do not count; >=3 failure
                       conditions; every criterion names its judge with a
                       parenthesized method that renders alphanumeric text -
                       judge: <type> (<method/who>); criteria and failure
                       conditions carry no [hypothesis]; at least one criterion
                       has a separated non-code judge; the contract cites
                       at least one interview ID (IV-nn)
  L5 raw immutability  hash manifest of raw/ files; a changed hash fails
  L6 log append-only   logs/**/log.md may only grow; rewritten history fails
State for L5/L6 lives in logs/.lint-state.json (created on first run).
  L7 installation      workspace/shared-protocol template sentinels are gone
  L8 gate integrity    v0.3 gate ledger vocabulary, approval evidence,
                       contract version and monotonic order
  L9 evidence chain    measured/proven claims retain source, date, window and
                       reproducer; quantitative projects retain a model
  L10 safety model     impact HOLD propagates to action/readiness verdicts
  L11 verdict split    harness/product/readiness/method verdicts cannot imply
                       one another or erase historical violations
  L12 lean MVP         execution-economy ceilings, MVP-1 rendered/independent
                       proof, packet/cost telemetry completion boundary
"""
import hashlib, json, os, re, stat, sys
from html.parser import HTMLParser

LINK = re.compile(r"\]\(([^)]+)\)")
NAME_RULE = re.compile(r"^\d{4}-\d{2}-\d{2}_.+")
SKIP_DIRS = {".git", "node_modules", "tools", "__pycache__"}


class _Visible(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []

    def handle_data(self, data):
        self.parts.append(data)


def visible_text(markup):
    """Markup as it renders: tags and comments dropped, character references
    decoded, text nodes kept - one normalization shared by every content check,
    instead of a regex per discovered bypass."""
    p = _Visible()
    p.feed(markup)
    p.close()
    return "".join(p.parts)


def structural_text(markup):
    """Markdown content eligible to define LDL structure.

    Fenced code and HTML comments are examples/hidden content, never live
    headings, ledgers, or verdicts. Normalize once before every parser.
    """
    markup = re.sub(r"<!--.*?-->", "", markup, flags=re.S)
    kept, fence_char, fence_len = [], None, 0
    for line in markup.splitlines():
        marker = re.match(r"^\s*(`{3,}|~{3,})", line)
        if fence_char is None and marker:
            fence_char, fence_len = marker.group(1)[0], len(marker.group(1))
            continue
        if fence_char is not None:
            if re.match(rf"^\s*{re.escape(fence_char)}{{{fence_len},}}\s*$", line):
                fence_char, fence_len = None, 0
            continue
        kept.append(line)
    return visible_text("\n".join(kept))


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
            with open(path, encoding="utf-8") as handle:
                return handle.read()
        except UnicodeDecodeError:
            self.err(code, f"not valid UTF-8: {self.rel(path)}")
        except OSError:
            self.err(code, f"unreadable file: {self.rel(path)}")
        return None

    def links_of(self, path):
        # v0.4 contract archives are byte snapshots, not live navigable docs.
        # Their bytes remain under L5; only link traversal is opaque.
        parts = self.rel(path).split(os.sep)
        if "raw" in parts and "contract-archive" in parts:
            return []
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

    def section_text(self, text, title):
        """Return the body under an exact markdown heading."""
        lines = structural_text(text).splitlines()
        for i, line in enumerate(lines):
            if re.match(rf"^#+\s+{re.escape(title)}\s*$", line.strip(), re.I):
                body = []
                for nxt in lines[i + 1:]:
                    if re.match(r"^#+\s+", nxt):
                        break
                    body.append(nxt)
                return "\n".join(body)
        return ""

    def table_rows(self, text, title, columns, code, rel):
        body = self.section_text(text, title)
        if not body:
            self.err(code, f"{rel}: required section missing - {title}")
            return []
        lines = [line.strip() for line in body.splitlines() if line.strip().startswith("|")]
        if len(lines) < 2:
            self.err(code, f"{rel}: table missing - {title}")
            return []
        header = [cell.strip() for cell in lines[0].strip("|").split("|")]
        if header != columns:
            self.err(code, f"{rel}: wrong columns in {title} - expected {' / '.join(columns)}")
            return []
        separator = [cell.strip() for cell in lines[1].strip("|").split("|")]
        if len(separator) != len(columns) or any(not re.fullmatch(r":?-{3,}:?", cell) for cell in separator):
            self.err(code, f"{rel}: malformed markdown separator in {title}")
            return []
        rows = []
        for line in lines[2:]:
            cells = [cell.strip() for cell in line.strip("|").split("|")]
            if len(cells) != len(columns):
                self.err(code, f"{rel}: malformed row in {title}")
                continue
            rows.append(dict(zip(columns, cells)))
        return rows

    def scalar_field(self, text, name):
        wanted = re.sub(r"[\W_]+", "", name).lower()
        matches = []
        for line in structural_text(text).splitlines():
            match = re.match(r"^-\s*(.*?)\s*:\s*(.*?)\s*$", line)
            if not match:
                continue
            rendered_label = re.sub(r"[\W_]+", "", match.group(1)).lower()
            if rendered_label == wanted:
                matches.append(match.group(2).strip())
        return matches[0] if len(matches) == 1 else ""

    def substantive_cell(self, value):
        value = visible_text(value).strip()
        if not re.search(r"[^\W_]", value):
            return False
        if re.fullmatch(r"<[^>]+>|N/?A", value, re.I):
            return False
        rendered = re.sub(r"[*_`~\[\]()]+", "", value)
        return not re.search(r"\b(?:TODO|TBD|placeholder|pending|fill(?: this)?(?: in)?)\b", rendered, re.I)

    def structural_text(self, text):
        return structural_text(text)

    def local_link_target(self, base, value):
        match = LINK.search(value)
        if not match:
            return None
        target = match.group(1).split("#", 1)[0].strip()
        target = re.sub(r"""\s+("[^"]*"|'[^']*')$""", "", target)
        if target.startswith(("http://", "https://", "mailto:")):
            return target
        return os.path.normpath(os.path.join(base, target))

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
            if os.path.islink(full):
                self.err("L5", f"project directory symlink (project must be a real directory): {self.rel(full)}")
                continue
            if not NAME_RULE.match(d):
                self.err("L3", f"project folder naming (YYYY-MM-DD_<name>): projects/{d}")
            self.check_contract(full)
            self.check_integrity_model(full)
            marker = os.path.join(self.root, ".ldl-version")
            marker_value = ""
            if os.path.isfile(marker):
                with open(marker, encoding="utf-8") as handle:
                    marker_value = handle.read().strip()
            if marker_value == "0.4.0":
                import lean
                lean.check(self, full)

    def check_contract(self, proj):
        c = os.path.join(proj, "00_CONTRACT.md")
        rel = self.rel(c)
        if not os.path.exists(c):
            self.err("L4", f"contract missing: {rel}")
            return
        text = self.read_text(c, "L4")
        if text is None:
            return
        text = re.sub(r"<!--.*?-->", "", text, flags=re.S)  # HTML comments are not contract content

        def substantive(body):
            # content = what the body renders as (visible_text), then at least
            # one line carrying an alphanumeric character; underscores render
            # as a horizontal rule and a lone table header is scaffolding
            lines = [ln for ln in visible_text(body).splitlines() if re.search(r"[^\W_]", ln)]
            table = [ln for ln in lines if ln.lstrip().startswith("|")]
            return len(lines) - (1 if table else 0) >= 1

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

        def concrete(value):
            value = visible_text(value).strip()
            return bool(re.search(r"[^\W_]", value)) and not re.fullmatch(r"<[^>]+>", value)

        for sec in ["2W1H", "Constraints", "Evaluation criteria", "Failure conditions", "Execution plan",
                    "Verification setup", "Exit tests"]:
            if not re.search(rf"^#+ .*{re.escape(sec)}", text, re.M | re.I):
                self.err("L4", f"{rel}: required section missing - {sec}")
            elif not substantive(section(sec)):
                self.err("L4", f"{rel}: required section empty - {sec}")
        for field in ["Why", "What", "How"]:
            m = re.search(rf"^- ?\*{{0,2}}{field}\*{{0,2}}[ \t]*:[ \t]*(.*)$", text, re.M)
            if m is None or not m.group(1).strip():
                self.err("L4", f"{rel}: {field} is empty")
        if re.search(r"^#+ .*Verification setup", text, re.M | re.I):
            verification = section("Verification setup")
            for field in ["Verifier instances", "Lint command", "Approver"]:
                m = re.search(rf"^- ?\*{{0,2}}{re.escape(field)}\*{{0,2}}[ \t]*:[ \t]*(.*)$",
                              verification, re.M | re.I)
                if m is None or not concrete(m.group(1)):
                    self.err("L4", f"{rel}: Verification setup field empty or placeholder - {field}")
        if re.search(r"^#+ .*Exit tests", text, re.M | re.I):
            exits = section("Exit tests")
            for test in range(1, 6):
                m = re.search(rf"^-\s*T{test}\b[^:]*:[ \t]*(.*)$", exits, re.M | re.I)
                if m is None or not concrete(m.group(1)):
                    self.err("L4", f"{rel}: Exit test missing or empty - T{test}")
        body = "\n".join(l for l in text.splitlines() if not l.lstrip().startswith(">"))
        if not re.search(r"IV-\d{2}", body):
            self.err("L4", f"{rel}: no interview ID (IV-nn) cited - a contract written from inference")

        crit = section("Evaluation criteria")
        items = [l for l in crit.splitlines() if re.match(r"^\s*(\d+\.|[-*])\s+\S", l)]
        if not items:
            self.err("L4", f"{rel}: no evaluation criteria - an empty pass line cannot gate anything")
        for l in items:
            m = re.search(r"judge:\s*(code|human|model|fresh-context)\s*\(([^)]*)\)", l, re.I)
            if not m or not re.search(r"[^\W_]", visible_text(m.group(2))):
                self.err("L4", f"{rel}: criterion without judge: <type> (<method/who>) - {l.strip()[:50]}")
        if items and not any(re.search(r"judge:\s*(human|model|fresh-context)\s*\(", l, re.I)
                             for l in items):
            self.err("L4", f"{rel}: at least one criterion must use a non-code judge")
        fail = section("Failure conditions")
        fails = [l for l in fail.splitlines() if re.match(r"^\s*(\d+\.|[-*])\s+\S", l)]
        if len(fails) < 3:
            self.err("L4", f"{rel}: fewer than three failure conditions")
        for name, body in (("Evaluation criteria", crit), ("Failure conditions", fail)):
            if "[hypothesis]" in body:
                self.err("L4", f"{rel}: [hypothesis] inside {name} - an undecidable pass line is pre-contract research")

    def check_integrity_model(self, proj):
        # Kept in a small module so the v0.3 schema can evolve without turning
        # the original reference lint into one giant parser.
        import integrity
        integrity.check(self, proj)

    # -- L5 + L6 ----------------------------------------------------------
    def check_state(self):
        state_path = os.path.join(self.root, "logs", ".lint-state.json")
        state = {"raw": {}, "logs": {}, "schema": None}
        if os.path.exists(state_path):
            try:
                with open(state_path, encoding="utf-8") as handle:
                    loaded = json.load(handle)
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
        marker = os.path.join(self.root, ".ldl-version")
        marker_value = None
        if os.path.isfile(marker):
            marker_value = self.read_text(marker, "L7")
            marker_value = marker_value.strip() if marker_value is not None else None
            if marker_value not in {"0.3.0", "0.4.0"}:
                self.err("L7", f"unsupported or malformed .ldl-version: {marker_value or 'empty'}")
        if state.get("schema") and marker_value is None:
            self.err("L7", ".ldl-version deleted after v0.3 baseline - legacy downgrade refused")
        if marker_value is not None:
            prior_schema = state.get("schema")
            if prior_schema in {None, marker_value}:
                state["schema"] = marker_value
            elif prior_schema == "0.3.0" and marker_value == "0.4.0":
                state["schema"] = "0.4.0"
            else:
                self.err("L7", f"lint schema {prior_schema} does not match marker {marker_value}")
        # L5: recursive raw/ hash manifest (root and per-project raw/).
        # Outside raw, ordinary skip dirs stay pruned. Inside raw, no name can
        # escape immutability; directory symlinks are rejected, never followed.
        seen_raw = set()
        for r, dirs, files in os.walk(self.root):
            parts = self.rel(r).split(os.sep)
            inside_raw = "raw" in parts
            for name in list(dirs):
                target = os.path.join(r, name)
                if (inside_raw or name == "raw") and os.path.islink(target):
                    self.err("L5", f"raw directory symlink (evidence must be a real directory): {self.rel(target)}")
                    dirs.remove(name)
            if not inside_raw:
                dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
                continue
            for f in files:
                p = os.path.join(r, f)
                key = self.rel(p)
                seen_raw.add(key)
                try:
                    mode = os.stat(p).st_mode
                    if not stat.S_ISREG(mode):
                        raise OSError("not a regular file")
                    digest = hashlib.sha256()
                    with open(p, "rb") as handle:
                        while True:
                            chunk = handle.read(1024 * 1024)
                            if not chunk:
                                break
                            digest.update(chunk)
                    h = digest.hexdigest()
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
                    with open(p, "rb") as handle:
                        data = handle.read()
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
            with open(state_path, "w", encoding="utf-8") as handle:
                json.dump(state, handle, indent=1)

    # -- L7 ---------------------------------------------------------------
    def check_installation(self):
        sentinels = {
            "CLAUDE.md": "Engraved at install step 3: identity in one sentence",
            os.path.join("projects", "CLAUDE.md"): "Engraved at install step 3: Phase 0-6 gates",
        }
        for rel, sentinel in sentinels.items():
            path = os.path.join(self.root, rel)
            if os.path.isfile(path):
                text = self.read_text(path, "L7")
                if text is not None and sentinel in text:
                    self.err("L7", f"installation stub remains: {rel}")

    # -- run --------------------------------------------------------------
    def run(self):
        self.check_links()
        self.check_projects()
        self.check_installation()
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
    import shutil, subprocess, tempfile
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import scaffold

    tmp = tempfile.mkdtemp(prefix="ldl-selftest-")
    ws = os.path.join(tmp, "ws")
    results = {}
    try:
        scaffold.init(ws)
        results["init copies v0.4 tools"] = all(
            os.path.isfile(os.path.join(ws, "tools", name))
            for name in ("scaffold.py", "lint.py", "integrity.py", "lean.py"))
        version_marker = os.path.join(ws, ".ldl-version")
        os.remove(version_marker)  # fixtures 1-28 prove legacy compatibility
        proj = scaffold.new_project(ws, "good", "2026-01-01")
        results["new project is indexed"] = (
            "projects/2026-01-01_good/PROGRESS.md"
            in open(os.path.join(ws, "index.md"), encoding="utf-8").read())
        good_contract = os.path.join(proj, "00_CONTRACT.md")
        contract_text = (
            "# 00_CONTRACT — good\n\n[interview](raw/interview.md)\n\n"
            "## 2W1H\n- Why: real problem [IV-01]\n- What: one deliverable [IV-02]\n- How: build then verify [IV-03]\n\n"
            "## Constraints\n- one week [IV-04]\n\n"
            "## Evaluation criteria\n1. output exists — judge: code (test script) [IV-03]\n2. tone approved — judge: human (owner) [IV-05]\n\n"
            "## Failure conditions (three, concrete)\n1. wrong output shipped\n2. deadline missed\n3. rework exceeds two hours\n\n"
            "## Execution plan\n| phase | path | verify | gate | budget |\n"
            "| P5+P6 | 05_engineering/ | test script | yes | one week |\n"
            "\n## Verification setup\n"
            "- Verifier instances: unit test and owner review\n"
            "- Lint command: python3 tools/lint.py .\n"
            "- Approver: project owner\n"
            "\n## Exit tests\n"
            "- T1 can it fail: three failure conditions are listed\n"
            "- T2 stranger: fresh-context review passed\n"
            "- T3 judge: every criterion names its judge\n"
            "- T4 constraint collision: scope fits one week\n"
            "- T5 primary source: IV-01 through IV-05 cited\n"
        )
        open(good_contract, "w", encoding="utf-8").write(contract_text)
        open(os.path.join(proj, "raw", "interview.md"), "w").write("IV-01 ...")
        idx = os.path.join(ws, "index.md")
        idx_text = open(idx, encoding="utf-8").read()
        for rel, content in {
            "CLAUDE.md": "# Workspace constitution\n\nLDL workspace: contract first; query index; preserve raw; lint gates.\n",
            "projects/CLAUDE.md": "# Shared project protocol\n\nRead the active contract; follow Phase 0-6 gates; append event logs.\n",
        }.items():
            open(os.path.join(ws, rel), "w", encoding="utf-8").write(content)

        l = Lint(ws)
        results["clean workspace passes"] = l.run() == 0
        goodrel = os.path.join("projects", "2026-01-01_good", "00_CONTRACT.md")

        # fixtures 1-3, planted one at a time: the verdict is the exact error
        # text at the exact path, never "some error of that class" — and each
        # teardown re-verifies clean, so one fixture cannot mask another
        badrel = os.path.join("projects", "2026-01-02_bad", "00_CONTRACT.md")
        scaffold.new_project(ws, "bad", "2026-01-02")
        with open(os.path.join(ws, badrel), encoding="utf-8") as handle:
            bad_contract_text = handle.read()
        bad_contract_text = re.sub(r"\n## Governance profile\n.*?(?=\n## 2W1H)", "", bad_contract_text, flags=re.S)
        open(os.path.join(ws, badrel), "w", encoding="utf-8").write(bad_contract_text)
        open(idx, "w", encoding="utf-8").write(idx_text + "- [bad](projects/2026-01-02_bad/PROGRESS.md)\n")
        l = Lint(ws); l.run()
        expected = [
            f"[L1] broken link: {badrel} -> {os.path.join('projects', '2026-01-02_bad', 'raw', 'interview.md')}",
            f"[L4] {badrel}: required section empty - Constraints",
            f"[L4] {badrel}: required section empty - Execution plan",
            f"[L4] {badrel}: Why is empty",
            f"[L4] {badrel}: What is empty",
            f"[L4] {badrel}: How is empty",
            f"[L4] {badrel}: Verification setup field empty or placeholder - Verifier instances",
            f"[L4] {badrel}: Verification setup field empty or placeholder - Lint command",
            f"[L4] {badrel}: Verification setup field empty or placeholder - Approver",
            f"[L4] {badrel}: Exit test missing or empty - T1",
            f"[L4] {badrel}: Exit test missing or empty - T2",
            f"[L4] {badrel}: Exit test missing or empty - T3",
            f"[L4] {badrel}: Exit test missing or empty - T4",
            f"[L4] {badrel}: Exit test missing or empty - T5",
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

        # fixture 4: the two procedural gate sections are part of the contract,
        # not optional template advice
        stripped = contract_text.split("\n## Verification setup\n", 1)[0]
        open(good_contract, "w", encoding="utf-8").write(stripped)
        l = Lint(ws); l.run()
        results["missing verification and exit sections (L4, exact)"] = sorted(l.errors) == sorted([
            f"[L4] {goodrel}: required section missing - Verification setup",
            f"[L4] {goodrel}: required section missing - Exit tests",
        ])
        open(good_contract, "w", encoding="utf-8").write(contract_text)

        # fixture 5: syntax-green automation alone is not verifier separation
        open(good_contract, "w", encoding="utf-8").write(
            contract_text.replace("judge: human (owner)", "judge: code (tone script)"))
        l = Lint(ws); l.run()
        results["all-code criteria refused (L4, exact)"] = (
            f"[L4] {goodrel}: at least one criterion must use a non-code judge" in l.errors)
        open(good_contract, "w", encoding="utf-8").write(contract_text)

        # fixture 6: an untouched installation sentinel is not an engraved protocol
        stub = scaffold.WS_FILES["CLAUDE.md"]
        engraved = open(os.path.join(ws, "CLAUDE.md"), encoding="utf-8").read()
        open(os.path.join(ws, "CLAUDE.md"), "w", encoding="utf-8").write(stub)
        l = Lint(ws); l.run()
        results["protocol stub refused (L7, exact)"] = l.errors == [
            "[L7] installation stub remains: CLAUDE.md"]
        open(os.path.join(ws, "CLAUDE.md"), "w", encoding="utf-8").write(engraved)

        # CLI contract: selftest is a complete mode, not a substring that
        # silently swallows a requested workspace lint
        p = subprocess.run(
            [sys.executable, os.path.abspath(__file__), "--selftest", "."],
            text=True, capture_output=True)
        results["selftest mixed args refused"] = p.returncode == 2

        # fixture 7: empty evaluation criteria must fail the contract gate
        open(good_contract, "w", encoding="utf-8").write(
            contract_text.replace("1. output exists — judge: code (test script) [IV-03]\n2. tone approved — judge: human (owner) [IV-05]\n", ""))
        l = Lint(ws); l.run()
        results["empty criteria (L4)"] = any("no evaluation criteria" in e for e in l.errors)
        open(good_contract, "w", encoding="utf-8").write(contract_text)

        # fixture 8: raw deletion must fail L5 (baseline first, then delete)
        assert Lint(ws).run() == 0  # baseline writes the manifest
        rawf = os.path.join(proj, "raw", "interview.md")
        os.remove(rawf)
        l = Lint(ws); l.run()
        results["raw deletion (L5)"] = any("deleted" in e for e in l.errors)
        open(rawf, "w").write("IV-01 ...")
        sp = os.path.join(ws, "logs", ".lint-state.json")
        os.path.exists(sp) and os.remove(sp)

        # fixture 9: malformed state must yield a clean FAIL, not a traceback
        open(sp, "w").write('{"broken": 1}')
        try:
            Lint(ws).run()
            results["malformed state (clean verdict)"] = True
        except Exception:  # noqa: BLE001
            results["malformed state (clean verdict)"] = False
        os.path.exists(sp) and os.remove(sp)

        # fixture 10: scaffold must refuse path-traversal project names
        try:
            scaffold.new_project(ws, "../escape", "2026-01-03")
            results["name traversal refused"] = False
        except SystemExit:
            results["name traversal refused"] = not os.path.exists(os.path.join(ws, "escape"))

        # fixture 11: a required section that is present but empty must fail
        open(good_contract, "w", encoding="utf-8").write(
            contract_text.replace("- one week [IV-04]\n", ""))
        l = Lint(ws); l.run()
        results["empty required section (L4, exact)"] = (
            f"[L4] {goodrel}: required section empty - Constraints" in l.errors)
        open(good_contract, "w", encoding="utf-8").write(contract_text)

        # fixture 12: a judge with no parenthesized method must fail
        open(good_contract, "w", encoding="utf-8").write(
            contract_text.replace("judge: human (owner)", "judge: human"))
        l = Lint(ws); l.run()
        results["bare judge (L4, exact)"] = (
            f"[L4] {goodrel}: criterion without judge: <type> (<method/who>) - "
            "2. tone approved — judge: human [IV-05]" in l.errors)
        open(good_contract, "w", encoding="utf-8").write(contract_text)

        # fixture 13: section names mentioned in body text are not headings —
        # a good contract whose execution plan says "evaluation criteria" must pass
        open(good_contract, "w", encoding="utf-8").write(
            contract_text + "| P6 | 06_VERIFICATION.md | evaluation criteria and failure conditions check | gate | 1d |\n")
        results["decoy phrase in body passes"] = Lint(ws).run() == 0
        open(good_contract, "w", encoding="utf-8").write(contract_text)

        # fixture 14: a markdown link with a title is still a link, not a broken path
        open(idx, "w", encoding="utf-8").write(idx_text + '- [c](CLAUDE.md "the constitution")\n')
        results["titled link passes"] = Lint(ws).run() == 0
        open(idx, "w", encoding="utf-8").write(idx_text)

        # fixture 15: a crawled file that is not UTF-8 must be a verdict, not a traceback
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

        # fixture 16: a raw file the lint cannot hash must be a verdict, not a
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

        # fixture 17: whitespace inside the judge parentheses is not a method
        open(good_contract, "w", encoding="utf-8").write(
            contract_text.replace("judge: human (owner)", "judge: human (   )"))
        l = Lint(ws); l.run()
        results["whitespace judge (L4, exact)"] = (
            f"[L4] {goodrel}: criterion without judge: <type> (<method/who>) - "
            "2. tone approved — judge: human (   ) [IV-05]" in l.errors)
        open(good_contract, "w", encoding="utf-8").write(contract_text)

        # fixture 18: a dash-only section is a placeholder, not content
        open(good_contract, "w", encoding="utf-8").write(
            contract_text.replace("- one week [IV-04]\n", "-\n"))
        l = Lint(ws); l.run()
        results["dash-only section (L4, exact)"] = (
            f"[L4] {goodrel}: required section empty - Constraints" in l.errors)
        open(good_contract, "w", encoding="utf-8").write(contract_text)

        # fixture 19: a table header with no phase row is not an execution plan
        open(good_contract, "w", encoding="utf-8").write(
            contract_text.replace("| P5+P6 | 05_engineering/ | test script | yes | one week |\n", ""))
        l = Lint(ws); l.run()
        results["header-only plan (L4, exact)"] = (
            f"[L4] {goodrel}: required section empty - Execution plan" in l.errors)
        open(good_contract, "w", encoding="utf-8").write(contract_text)

        # fixture 20: an HTML comment is not contract content
        open(good_contract, "w", encoding="utf-8").write(
            contract_text.replace("- one week [IV-04]\n", "<!-- TODO fill in -->\n"))
        l = Lint(ws); l.run()
        results["comment-only section (L4, exact)"] = (
            f"[L4] {goodrel}: required section empty - Constraints" in l.errors)
        open(good_contract, "w", encoding="utf-8").write(contract_text)

        # fixtures 21-22: markup that renders as nothing is not content either
        for markup, tag in (("<br>", "br-only"), ("&nbsp;", "nbsp-only")):
            open(good_contract, "w", encoding="utf-8").write(
                contract_text.replace("- one week [IV-04]\n", markup + "\n"))
            l = Lint(ws); l.run()
            results[f"{tag} section (L4, exact)"] = (
                f"[L4] {goodrel}: required section empty - Constraints" in l.errors)
        open(good_contract, "w", encoding="utf-8").write(contract_text)

        # fixture 23: underscores are not a judge identity
        open(good_contract, "w", encoding="utf-8").write(
            contract_text.replace("judge: human (owner)", "judge: human (___)"))
        l = Lint(ws); l.run()
        results["underscore judge (L4, exact)"] = (
            f"[L4] {goodrel}: criterion without judge: <type> (<method/who>) - "
            "2. tone approved — judge: human (___) [IV-05]" in l.errors)
        open(good_contract, "w", encoding="utf-8").write(contract_text)

        # fixture 24: an underscore horizontal rule is as empty as a dashed one
        open(good_contract, "w", encoding="utf-8").write(
            contract_text.replace("- one week [IV-04]\n", "___\n"))
        l = Lint(ws); l.run()
        results["underscore-rule section (L4, exact)"] = (
            f"[L4] {goodrel}: required section empty - Constraints" in l.errors)
        open(good_contract, "w", encoding="utf-8").write(contract_text)

        # fixtures 25-26: markup is not a judge identity either
        for markup, tag in (("<br>", "br judge"), ("&nbsp;", "nbsp judge")):
            open(good_contract, "w", encoding="utf-8").write(
                contract_text.replace("judge: human (owner)", f"judge: human ({markup})"))
            l = Lint(ws); l.run()
            results[f"{tag} (L4, exact)"] = (
                f"[L4] {goodrel}: criterion without judge: <type> (<method/who>) - "
                f"2. tone approved — judge: human ({markup}) [IV-05]" in l.errors)
        open(good_contract, "w", encoding="utf-8").write(contract_text)

        # fixture 27: a tag with '>' inside a quoted attribute still renders as nothing
        open(good_contract, "w", encoding="utf-8").write(
            contract_text.replace("- one week [IV-04]\n", '<span title="x>y"></span>\n'))
        l = Lint(ws); l.run()
        results["quoted-attr span section (L4, exact)"] = (
            f"[L4] {goodrel}: required section empty - Constraints" in l.errors)
        open(good_contract, "w", encoding="utf-8").write(contract_text)

        # fixture 28 (positive): character references that render visible text ARE content
        open(good_contract, "w", encoding="utf-8").write(
            contract_text.replace("- one week [IV-04]\n", "&#49;&#50;&#51;\n"))
        results["visible entity passes"] = Lint(ws).run() == 0
        open(good_contract, "w", encoding="utf-8").write(contract_text)

        # v0.3 integrity model: activate the schema on the same clean project,
        # then plant one defect at a time. Legacy projects remain readable but
        # cannot claim these stronger verdicts without a Governance profile.
        open(version_marker, "w", encoding="utf-8").write("0.3.0\n")
        v3_contract = contract_text.replace(
            "## 2W1H\n", "## Governance profile\n- Contract version: v1\n- Approval mode: human\n- Quantitative claims: no\n- Risk level: low\n\n## 2W1H\n").replace(
            "- Approver: project owner\n", "- Approver: project owner\n- Verifier workspace: external reviews\n- Target access: read-only\n")
        progress_path = os.path.join(proj, "PROGRESS.md")
        progress_v3 = """# PROGRESS — good\n\n## Phase progress\n| Phase | Status | Date | Deliverable |\n|---|---|---|---|\n| P0 contract | done | 2026-01-01 | [contract](00_CONTRACT.md) |\n| P1 requirements | pending | | [requirements](01_REQUIREMENTS.md) |\n| P2 structure | pending | | [constitution](CLAUDE.md) |\n| P3 research | pending | | [evidence](03_EVIDENCE.md) |\n| P4 scoping | pending | | [scope](04_SCOPE.md) |\n| P5+P6 increments | pending | | [verification](06_VERIFICATION.md) |\n\n## Gate ledger\n| Gate | Verdict | Contract version | Approval mode | Approver | Approved at | Evidence |\n|---|---|---|---|---|---|---|\n| G1 | PASS | v1 | human | owner | 2026-01-01T10:00:00Z | [approval](raw/approval.md) |\n| G2 | PENDING | v1 | human | | | |\n| G3 | PENDING | v1 | human | | | |\n| G4 | PENDING | v1 | human | | | |\n\n[contract](00_CONTRACT.md) [requirements](01_REQUIREMENTS.md) [evidence](03_EVIDENCE.md) [scope](04_SCOPE.md) [verification](06_VERIFICATION.md) [constitution](CLAUDE.md) [events](logs/log.md)\n"""
        evidence_v3 = """# evidence\n\n## Evidence ledger\n| Claim ID | Label | Claim | Source artifact | Captured at | Scope/window | Transform/reproducer | Status |\n|---|---|---|---|---|---|---|---|\n| C-01 | [measured] | observed | [source](raw/source.txt) | 2026-01-01 | one run | direct | ACTIVE |\n"""
        scope_v3 = """# scope\n\n## Impact dimensions\n| Dimension ID | Status | Evidence |\n|---|---|---|\n| D-01 | PASS | [evidence](03_EVIDENCE.md) |\n\n## Action readiness\n| Action ID | Impact dimensions | Preconditions | Approval tier | Approval evidence | Canary | Rollback | Ready |\n|---|---|---|---|---|---|---|---|\n| A-01 | D-01 | G1 PASS | 1 | [approval](raw/approval.md) | sample | restore | YES |\n"""
        verification_v3 = """# verification\n\n## Requirement verdicts\n| Requirement ID | Verdict | Evidence |\n|---|---|---|\n| R-01 | NOT_RUN | pending |\n\n## Final verdicts\n- Harness: NOT_RUN\n- Product: NOT_RUN\n- Execution readiness: HOLD\n- Method conformance: PASS\n- Historical violations: NONE\n- Independent verifier: fresh-context (owner)\n- Target mutation: 0 files\n"""
        open(good_contract, "w", encoding="utf-8").write(v3_contract)
        requirements_v3 = """# requirements\n\n## Requirements ledger\n| Requirement ID | Type | Priority | Requirement | Verification | Source |\n|---|---|---|---|---|---|\n| R-01 | functional | must | produce output | test script | (b) IV-03 |\n"""
        open(os.path.join(proj, "01_REQUIREMENTS.md"), "w", encoding="utf-8").write(requirements_v3)
        open(progress_path, "w", encoding="utf-8").write(progress_v3)
        open(os.path.join(proj, "03_EVIDENCE.md"), "w", encoding="utf-8").write(evidence_v3)
        open(os.path.join(proj, "04_SCOPE.md"), "w", encoding="utf-8").write(scope_v3)
        open(os.path.join(proj, "06_VERIFICATION.md"), "w", encoding="utf-8").write(verification_v3)
        open(os.path.join(proj, "raw", "approval.md"), "w").write("owner approves Gate 1 for contract v1")
        open(os.path.join(proj, "raw", "source.txt"), "w").write("source")
        open(os.path.join(proj, "logs", "log.md"), "w").write("# events\nGATE-PASS: G1 contract=v1\n")
        os.path.exists(sp) and os.remove(sp)
        results["v0.3 clean integrity model passes"] = Lint(ws).run() == 0

        open(progress_path, "w", encoding="utf-8").write(progress_v3.replace("| G2 | PENDING |", "| G2 | PARTIAL PASS |"))
        results["v0.3 partial gate verdict refused"] = any("invalid gate verdict" in e for e in (lambda x: (x.run(), x.errors)[1])(Lint(ws)))
        open(progress_path, "w", encoding="utf-8").write(progress_v3.replace("| G3 | PENDING | v1 | human | | | |", "| G3 | PASS | v1 | human | owner | 2026-01-03T10:00:00Z | [approval](raw/approval.md) |"))
        results["v0.3 gate order refused"] = any("G3 PASS while G2 is not PASS" in e for e in (lambda x: (x.run(), x.errors)[1])(Lint(ws)))
        open(progress_path, "w", encoding="utf-8").write(progress_v3)

        ep = os.path.join(proj, "03_EVIDENCE.md")
        open(ep, "w", encoding="utf-8").write(evidence_v3.replace("[source](raw/source.txt)", ""))
        results["v0.3 source-less measured claim refused"] = any("missing source artifact" in e for e in (lambda x: (x.run(), x.errors)[1])(Lint(ws)))
        open(ep, "w", encoding="utf-8").write(evidence_v3)

        scp = os.path.join(proj, "04_SCOPE.md")
        open(scp, "w", encoding="utf-8").write(scope_v3.replace("| D-01 | PASS |", "| D-01 | HOLD |"))
        results["v0.3 HOLD propagates to actions"] = any("ready while impact dimension" in e for e in (lambda x: (x.run(), x.errors)[1])(Lint(ws)))
        open(scp, "w", encoding="utf-8").write(scope_v3)

        vp = os.path.join(proj, "06_VERIFICATION.md")
        open(vp, "w", encoding="utf-8").write(verification_v3.replace("- Product: NOT_RUN", "- Product: PASS"))
        results["v0.3 NOT_RUN blocks Product PASS"] = any("Product PASS requires every requirement PASS" in e for e in (lambda x: (x.run(), x.errors)[1])(Lint(ws)))
        open(vp, "w", encoding="utf-8").write(verification_v3.replace("Historical violations: NONE", "Historical violations: PRESENT"))
        results["v0.3 history cannot be retroactively passed"] = any("historical violations require" in e for e in (lambda x: (x.run(), x.errors)[1])(Lint(ws)))
        open(vp, "w", encoding="utf-8").write(verification_v3)
        os.path.exists(sp) and os.remove(sp)

        failed = [k for k, v in results.items() if not v]
        if failed:
            print("SELFTEST FAIL -> " + ", ".join(failed))
            return 1
        print(f"SELFTEST PASS - {len(results)} checks: hostile fixtures all caught by their exact errors, legit-input probes all pass clean")
        return 0
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    if sys.argv[1:] == ["--selftest"]:
        sys.exit(selftest())
    if "--selftest" in sys.argv:
        print("usage: lint.py --selftest  OR  lint.py [workspace_root]", file=sys.stderr)
        sys.exit(2)
    if len(sys.argv) > 2:
        print("usage: lint.py --selftest  OR  lint.py [workspace_root]", file=sys.stderr)
        sys.exit(2)
    root = sys.argv[1] if len(sys.argv) > 1 else "."
    sys.exit(Lint(root).run())
