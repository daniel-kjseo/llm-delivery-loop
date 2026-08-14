# LDL — LLM Delivery Loop

**A delivery methodology for AI agents: contract first, gated delivery loop, compounding second brain.**

**LDL** (LLM Delivery Loop) is a pattern for delivering real results with AI agents. In one sentence — **humans govern through contracts and gates, agents execute through loops, and every project compounds into a second brain.** Three elements: (1) contract & gates (governance) (2) loop execution (delivery) (3) compounding assets. If the [LLM Wiki](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f) compounds knowledge, LDL compounds delivery.

> **Quick start** — paste this document into your agent and ask: *"Install this into my workspace."*
> Works with Claude Code, Codex, Cursor, Gemini CLI, or any agent that can read and write files. Nothing to install, no dependencies — in LDL the methodology **is** the folder structure.

**What's inside**: the double loop (inner delivery loop + outer knowledge loop) · seven phases from contract to verification · four human approval gates · the Ingest / Query / Lint protocol for a compounding wiki · a folder tree you can install today.

**If you are looking for** an AI agent workflow that survives real projects, a way to stop re-explaining context to your agent every session, contract-first prompting, human-in-the-loop quality gates, or a second brain that agents actually maintain — that is what LDL is for.

## Core

> **Agree the goal and criteria first, as a contract → enforce them through structure → delegate → humans verify at the gates → feed the results back into criteria and rules.**

Contract = Phase 0–1 (goal, requirements) / structure = Phase 2 / delegation = Phase 3–5 (research, scoping, execution) / verification = the four gates + the Phase 6 loop / feedback = at Phase 6 completion → the outer loop.

## Structure — double loop

```
┌─ Outer loop: compounding assets ──────────────────┐
│  Ingest · Query · Lint — wiki · rules · templates    │
│  ┌─ Inner loop: delivery ──────────────────┐       │
│  │ Phase 0  goal setting (the contract)     │       │
│  │ Phase 1  requirements definition         │       │
│  │ Phase 2  scaffolding structure design    │       │
│  │ Phase 3  problem research                │       │
│  │ Phase 4  solution scoping & priorities   │       │
│  │ Phase 5  engineering execution           │       │
│  │ Phase 6  the loop (verify·iterate·feed back) │   │
│  └─────────────────────────────────────────┘       │
│  at project end, promote lessons/rules/templates out │
└─────────────────────────────────────────────────────┘
```

- The inner loop completes one project.
- The outer loop promotes lessons into assets. **Project complete = deliverable shipped + at least one lesson promoted.**
- **The double loop is physical — it is the folder structure.** The workspace root (constitution · `RULES.md` · `index.md` · `raw/` · `wiki/` · `templates/` · `logs/` — persistent, cross-project) is the outer loop; each project folder under `projects/` (contract · phase documents · `raw/` · `05_engineering/` · `logs/` · `PROGRESS.md`) is the inner loop. Promotion = copying from a project folder up to the root. The default tree is in installation step 1.
- There are two source layers: **root `raw/`** = second-brain collections (project-independent — articles, papers, clippings), **project `raw/`** = that project's sources (RFP, meeting notes, survey materials). Both immutable — the agent only reads.
- Per-layer permissions: `raw/` (immutable sources) / `wiki/` (created/updated with approval) / `05_engineering/` (working results — delivered versions point-in-time frozen) / constitution · `RULES.md` (changed only with human approval) / `logs/` (append-only).
- **Apply all of Phase 0–6 to every piece of work, leaving one document per phase.** One page max per phase document. The phase documents sit flat at the project folder root — five one-page documents do not need a folder, they need an order.
- **Number the phase documents by phase, not by sequence**: `00_CONTRACT.md` · `01_REQUIREMENTS.md` · `03_EVIDENCE.md` · `04_SCOPE.md` · `06_VERIFICATION.md`. `02` and `05` are missing on purpose — Phase 2's deliverable is the project constitution and Phase 5's is the `05_engineering/` folder. **The gaps are information.** Phase numbers never change, so a document added later never forces a renumber, and the filename alone tells you which gate you are standing at. **Numbered = a phase document: it belongs to one phase, and its number *is* that phase. Unnumbered (`PROGRESS.md`, `CLAUDE.md`) = a standing document that spans every phase.** (Numbering says which phase owns a file, not how often it changes — `06_VERIFICATION.md` is numbered and still grows with every increment.) Project folders are `YYYY-MM-DD_<name>` — the start date, never renamed, because renaming breaks every link into it.

## Phase 0 — Goal setting (the contract)

**This phase's deliverable is a contract between the user and the AI.** Agree on what problem to solve, why, how, and how the whole flow will run; every later phase is execution of the contract. Scope changes are handled as contract changes. Keep the contract as a separate file from the constitution (`00_CONTRACT.md`) — the constitution holds immutable principles; the contract is a project document updated through contract changes.

Deliverable: `00_CONTRACT.md` — preceded by the interview record in `raw/`.

### The interview comes first

**The contract is not what the agent inferred — it is what the human said.** Before writing the contract, interview the user and preserve the answers verbatim in the project's `raw/` (one file, IDs `IV-01`, `IV-02`, …). The contract then **cites those IDs**, and any field with no citation is agent inference and carries a `[hypothesis]` label. This applies Phase 1's primary-utterance rule at Phase 0, where it decides everything downstream.

Ask three or four at a time. Offer choices — including your own guess — and allow free text; a wrong guess is itself information.

| Question | The contract field it fills |
|---|---|
| What is the real problem behind this request? | Why |
| What exactly is in your hands when this is done? | What |
| How will you check that it was done? | How · evaluation criteria |
| By when, at what cost, with how many people? | Constraints |
| Who decides pass or fail — a person, or code? | Criteria judge |
| Is there work here that cannot be undone? | Permission tiers |
| Do you know this domain? Where are the primary sources? | Phase 3 depth · `raw/` |
| Verified once at a deadline, or continuously? | Scope mode |
| What would you look at and call this a failure? | Failure conditions |

**A question that fills no field is not asked** — it only spends the user's attention.

Go deeper only on a trigger: a vague word ("fast", "properly") → ask for the number and the instrument; Why and What don't connect → "how does that deliverable remove that problem?"; a criterion can't decide pass or fail → "what would you look at and call it failure?"; irreversible work exists → approval path and rollback; no domain expertise → who to ask, which document is primary; the constraints make the What impossible → "what do you drop first?"; `raw/` is empty → **ask for the material before asking more questions** — one document can remove five of them.

**"I don't know" is a valid answer.** If the unknown does not move the pass line (a tool, a method, a nice-to-have), it enters the contract as `[hypothesis]` and becomes a Phase 3 research item. If the unknown *is* the pass line (a missing law, policy, or primary source that decides what counts as done), no contract can honestly form yet — that is what pre-contract research below is for. An interview that stalls on unknowns is a bad interview.

**Cost ceiling: three rounds.** If the exit tests still fail after three, this is not a problem an interview can solve. Two legal exits — "hand it to Phase 3" is not one of them, because Phase 3 sits behind gate ① and gate ① is exactly what you cannot pass:

- **Hold** the project, with a resumption condition, as at any gate.
- **Pre-contract research** — a bounded branch, not Phase 3: read-only actions only, its own cost ceiling, one required evidence artifact filed into the project's `raw/`, then **return to the Phase 0 interview** with what it found. It exists to resolve the one unknown that blocks the pass line, nothing more — scope creep here is just Phase 3 without a contract.

### The five exit tests — the interview ends when all five pass

- **T1 Can it fail** — three concrete failure situations are written down.
- **T2 The stranger** — a **fresh context** reads only the contract and answers *what is this work · what is the pass line · what stops you from starting*. Wherever it misreads, that is your next question. **This is the Phase 6 verifier-separation ladder pulled back to Phase 0: the author of a contract cannot see its own contradictions.** Run it every time, not only on large projects — **once per contract version**: fold the misreads into the next revision, and re-run only if a misread that blocks the work remains, always inside the three-round ceiling. Whatever stays ambiguous after that is written down as `[hypothesis]`, not argued about.
- **T3 The judge** — every criterion names its judge and its method, in one grammar the lint enforces: `judge: <type> (<method/who>)` — `judge: code (test script)`, `judge: human (the owner)`. A bare `judge: human` names a species, not a judge. Every criterion that *can* be decided deterministically *is* decided by code — no quota beyond that. Qualitative criteria are legitimate: each one names a separated verifier (an independent human, a different model, or a fresh context — the Phase 6 ladder) instead of pretending to be code-judged. A contract fails T3 only when a criterion has no judge, or when a code-decidable criterion is left to opinion — and that second clause is held by T2 and the human at the gate, not by the lint: deciding whether a criterion is code-decidable is itself a judgment call, so the lint enforces only the grammar.
- **T4 Constraint collision** — the What is actually reachable within the schedule, cost and staffing. If not, cut the scope now; discovering it in Phase 4 is late.
- **T5 Primary source** — Why and What come from the user's words, not the agent's. Whatever is inference is labelled as inference.

Each failed test is the next question. The interview is a loop, not a form — so give it what every loop needs: a verifier (the tests), a cost ceiling (three rounds), and a termination condition (all five pass).


- Define the goal in **2W1H**:
  - **Why**: the fundamental problem being solved, in one sentence. Write the problem behind the request, not the surface request.
  - **What**: the final deliverable, in one sentence.
  - **How**: the approach and the verification method.
- **State the constraints**: cost, schedule, staffing, technology, policy. Constraints are first-class variables in every later judgment.
- **Write the evaluation criteria**: define what verifies goal achievement, and how. Write them concretely enough to decide pass or fail — name the instrument, not just the target ("first page of Google" is not a criterion; "inside the top ten results in an incognito window" is).
- **Write three failure conditions**: concrete situations in which you would call this project a failure. **A contract that cannot fail cannot succeed either** — if nothing counts as failure, the evaluation criteria are empty.
- **Write the execution plan together with the AI**: how Phase 1–6 will run — for each phase, state the **deliverable path / verification method (which file the human opens, judged against what criteria) / whether it ends in a gate**, plus milestones and a time budget per phase. A plan without a time budget is not a plan. The contract governs the folder structure and the verification method.
- **Gate ① contract approval: no contract (2W1H + constraints + evaluation criteria + failure conditions + execution plan), no Phase 1.** Every field either cites an interview ID or carries `[hypothesis]` with its Phase 3 research item — **except the evaluation criteria and failure conditions, which can never be hypotheses** (an undecidable pass line is pre-contract research, not a contract). Run the lint once before this gate — it is the gate's deterministic pre-check. And write the approval line only after all five exit tests have passed; approving first and testing after is how the author's blind spots ship.

## Phase 1 — Requirements definition

Deliverable: `01_REQUIREMENTS.md`

- **Requirements definition = problem definition.** Clients cannot define requirements well. Listen and define them on their behalf.
- Elicitation: primary utterances (interviews, meeting notes, the original request) get the highest weight. Preserve verbatim; separate source from interpretation.
- Specification: record each requirement with a **unique ID + type (functional/non-functional) + priority + verification method + source (link to the primary utterance)**. One requirement, one sentence. No ambiguous words ("fast", "appropriately"). Write it so pass or fail can be decided.
- **Source coverage**: label every requirement's source as `(a)` a primary file, `(b)` an interview ID, or `(c)` agent inference. **If `(c)` exceeds 30%, stop Phase 1 and open a second interview.** Asking only "is `raw/` empty?" misses the case where material exists but is not the right material. And in that second interview, **ask for documents before asking questions.**
- Management: **the requirement ID is the axis of traceability** — the solution (Phase 4), the deliverables (Phase 5), and the verification (Phase 6) all link back by ID. Requirement changes go through contract change.

## Phase 2 — Scaffolding structure design

The workspace harness (constitution, rules, wiki, templates) was installed once; the project skeleton (the project part of the default tree) was created at project start. Phase 2 designs not folders but **this project's enforcement devices**. Build the harness before delegating research and execution — delegating without structure scatters evidence and outputs.

Deliverable: the project constitution + the delegation and permission structure

- **Project constitution** (`CLAUDE.md` in the project folder — sits on top of the shared project protocol `projects/CLAUDE.md`): write this project's scope constraint ("we build [deliverable] within [period]; anything beyond is a contract change"), its permission boundaries, and its project-specific rules.
- **A prompt is a request; structure is enforcement.** Promote repeated, important, or risky items from requests to enforcement (always-loaded files, deterministic gates, permission boundaries).
- Delegation structure: let the model choose the topology (single/multi, worker count and division) to fit the task. What you enforce are the invariants — coordination responsibility in one place (never two orchestrators) / workers in isolated contexts / no direct writes to shared truth.
- The pass/fail test for the structure: **at any phase, is "the file the human opens" fixed to exactly one?** If you can't answer, the scaffolding has failed.

## Phase 3 — Problem research

Deliverable: `03_EVIDENCE.md` (the evidence ledger)

- Research starts by consulting the workspace index (root `index.md`) — check what is already known (wiki, past projects, held problems) before going external.
- Research the background of the requirements and finalize the problem. Force an evidence label on every claim: `[hypothesis]` / `[measured · 2026-08-14]` (date required, **inside** the brackets) / `[proven]`. No unlabeled assertions. Write the date inside the brackets — `[measured](2026-08-14)` is markdown link syntax and renders as a broken link everywhere.
- Research is fact-based, along two axes: **official documents and primary sources** (the axis of fact) and **real user feedback and VOC** (the axis of reality). The two axes cross-verify each other — what the docs promise but users complain about, and what users want but is officially impossible, is often the heart of the problem. Speculative sources enter only as `[hypothesis]`.
- For site visits and interviews: write the checklist first, then fill each item with evidence (photos, documents, records).
- A solution may not emerge. **"No solution found" is also a result** — record it with what was searched and how far (the coverage). Without that record, the next attempt starts from zero.
- If the finalized problem differs from what the client first said, persuade with the primary records and formally change the contract scope.
- **Gate ② problem finalized — the human's verdict is one of three.** Do not move on before the verdict:
  - **Proceed**: the problem and a solution direction stand → Phase 4.
  - **Hold**: no viable approach for now → promote to the wiki with an explicit **resumption condition** ("what has to appear for us to retry"). A hold outlives the project — later projects' queries rediscover it. A hold without a resumption condition is just an alarm switched off.
  - **Contract change**: no solution can satisfy the requirement → renegotiate the scope (return to gate ①).

## Phase 4 — Solution scoping & priorities

Deliverable: `04_SCOPE.md`

- Build 2–3 solution candidates and compare them: requirement coverage (by ID) / cost and schedule (against the contract's constraints) / risk. Never go straight to a single candidate.
- Define the output first, in one sentence. If the name alone doesn't paint the picture, the scope is wrong.
- **Decompose the scope MECE** — no overlaps, no gaps. The test: does every requirement ID map to **exactly one scope item**? An ID with zero mappings is a gap — handle it as a contract change or a hold, never a silent omission. Two or more mappings is an overlap — rework the decomposition. Only when the whole equals the sum of its parts do parallel delegation (worker assignment), progress (done/total), and verification roll-up (all IDs pass = the whole passes) hold — **MECE is not a style; it is the precondition for every calculation that follows.**
- **Priority has two layers**: ① dependencies (predecessor → successor) are **constraints** — state and enforce which items must complete before others can start; this is the law of ordering, not a preference. ② Within what the dependencies allow, **most important first** — when the core is built first, whatever remains unbuilt when time or budget runs out is the least important part.
- You cannot build everything — **state what was cut.** What you decided not to do is the scope document's key information.
- Derive the scope mode from the Phase 0 contract:
  - **Ship-and-compete** (verified once, at the deadline — hackathons, proposals, demos): maximum ambition.
  - **Operate-and-serve** (verified continuously — services, automation): no expansion before validation. Expansion is maintenance debt.
  - The quality bar never drops in either mode.
- **Gate ③ solution finalized — the human's verdict is one of three.** Do not move to execution before the verdict:
  - **Proceed**: the solution and scope stand → Phase 5.
  - **Reject**: re-scope — and **reject in the language of the criteria** (say what falls short, measured against the evaluation criteria). Feedback that fixes one candidate fixes only that candidate; feedback that fixes the criteria fixes every candidate after it.
  - **Contract change**: no solution is compatible with the contract's constraints (schedule, cost, scope) → renegotiate (return to gate ①).

## Phase 5 — Engineering execution

Deliverable: the results accumulating in `05_engineering/` (delivered versions point-in-time frozen)

- Build the deliverables according to the execution plan. Scope changes discovered during execution are not applied unilaterally — they go through contract-change approval.
- **Never build everything and then verify.** Complete the top one or two priority items first, pass them through Phase 6 verification, then move to the next increment — Phase 5↔6 alternate per increment. Fast verification beats late completion, and the first increment is the shakedown run of the verification system itself.
- **When code is involved, enforce TDD through structure**: a failing test first → the minimum implementation to pass → full regression check. Enforce with hooks/CI so changes that fail tests cannot land. Automate unit test runs.
- Let the model choose the delegation topology (single/multi, worker count and division) to fit the task — over-enforcing structure degrades performance as models improve. What you enforce are the **invariants**: coordination responsibility in one place / workers in isolated contexts / no direct writes to shared truth, state recorded immediately per unit of work.
- The maker never grades its own work. Verification belongs to Phase 6.

## Phase 6 — The loop (verify · iterate · feed back)

Deliverable: `06_VERIFICATION.md` (the verification report — updated cumulatively per increment)

- **Phase 6 runs per increment** (alternating with Phase 5). The verification loop runs every increment; feedback and lint run once, at project completion.
- Loop preconditions: a verifiable goal + a verifier. Missing either, no loop. Three loop requirements: verifier / cost ceiling / termination condition.
- **Split verification in two, per requirement ID**: where the verdict is deterministic (tests/scripts decide pass/fail), run an **automatic loop** — iterate unattended until achieved (within the three requirements). Where judgment is needed, route to the human gate. Phase 1's "verification method" field determines the split.
- **The ladder of verifier separation** — use the highest rung available (strong guidance, not enforcement):
  - ① **Deterministic checker** (tests, scripts) — code, not a model, gives the verdict. No bias to share.
  - ② **A different model** — verify with a model other than the one that built it (e.g., built with Claude → verified with Codex or Gemini). The same model cannot see the flaws in its own grain.
  - ③ **At minimum**: a fresh context of the same model, instructed to "find the flaws."
- Feedback fixes the criteria, not the deliverable: instead of "do it again," say **"from now on, judge by this criterion and do it again."** Iterate until the contract's evaluation criteria are met.
- **If the loop hits its cost ceiling or termination condition while still short of the criteria**, stop and escalate to the human — the verdict is one of three: add budget / contract change (adjust criteria or scope) / hold that ID.
- Write the verification report (`06_VERIFICATION.md`) as **pass/fail per requirement ID**. Do not open the delivery gate until every ID has a verdict.
- On completion, feed back: promote units of meaning (decisions, lessons, improved templates) to the workspace root, curated through the five verdicts, and run one lint pass — see the outer loop.
- **Gate ④ final delivery: the human gives final confirmation against the contract's evaluation criteria. Rejection is voiced in the language of the criteria — and the loop resumes.**

## Four human gates

Contract approval (Phase 0) / problem finalized (Phase 3) / solution finalized (Phase 4) / final delivery (Phase 6). At each gate, the head of the phase document carries a **four-line review summary** (what was done / key conclusion / the judgment being requested / where the detailed evidence lives), so the human opens one file and judges in minutes. Everything else belongs to the loop. Record every gate pass in the event log and `PROGRESS.md`.

## Outer loop — Ingest · Query · Lint

The operation of the workspace root (`raw/` · `wiki/` · `index.md` · `RULES.md` · `templates/` · `logs/`). **As the wiki accumulates, it becomes a second brain.**

- **Ingest** — two entrances, both behind an approval gate. Curate with the five verdicts: ingest / merge / already covered / exclude / hold. When unsure, hold — don't guess. The most important number is not what you added but what you kept out.
  - **Source intake** (root `raw/` → `wiki/`): every source needs **one line of collection purpose (why)** — recorded in the root `logs/` at collection time. No purpose, no ingest — hold it. The agent reads the content, judges it against the purpose, and generates relation links seeded by that purpose.
  - **Project promotion** (Phase 6 feedback): promote **units of meaning**, not whole files — decisions, gate passes, and contract changes from the event log; verification verdicts; failures and lessons. Decisions → judgment pages, gates/milestones → event pages, lessons → `RULES.md` (with their origin — every task reads the rules before starting), improved templates → `templates/`.
- **Query**: consult the workspace index (root `index.md` — the catalog of wiki pages, projects, and held problems) first, then answer. Reusable answers don't stay in chat — file them back into the wiki as new pages, so queries compound too. **The index must be link-closed: every document in the workspace is reachable from `index.md` by following links.** An index you cannot navigate is a folder listing with extra steps. And an index is a catalog, not a log — **edit it, never append**, or you end up with the same table twice.
- **Lint**: once per project feedback cycle, plus once before every gate ① — **and make it a script, not a habit.** What it decides by exit code: broken links; orphan documents (unreachable from `index.md`); folder and file naming rules; stale paths left behind by a rename; and the Phase 0 contract checks. What it *reports* without judging — contradictions between pages, stale rules, unsourced claims — stays advisory: those are semantic calls, and a workspace makes one deterministic only by promoting its own rule for it (a typed `refutes` edge convention, say) — until then they are reports for the human, not exit codes. Two of the standing rules need teeth, not policy: **`raw/` immutability** (keep a hash manifest at intake; the lint fails when a recorded hash changes) and **log append-only** (the lint remembers each log's last-seen state and fails when history shrinks or rewrites). **A rule you have to remember is a rule you will eventually break — promote it to a check that fails the build.**
  Scope, so two lints agree on what they judge: link-closure applies to the markdown the workspace manages; binaries and raw sources are tracked by the manifest, not link-crawled; and external URLs are outside the lint entirely — it never touches the network, so they neither pass nor fail. The reference lint ships exit codes for none of the semantic checks.
- **Wiki page standard**: head each page with a type (concept / procedure / insight / event / judgment) · tags · date · source (external / own thinking) · evidence label (`[hypothesis]`/`[measured]`/`[proven]`). Body links to at least one related page, with the relation marked (supports / extends / refutes). **Typed pages plus typed links are what a second brain actually is.**
- **Compound the interview too**: answers that repeat across projects (constraints, evaluators, permission boundaries) promote to a **standing conditions** page. The next project's interview opens with *"same as last time?"* and asks only what changed. The outer loop is supposed to compound knowledge — it should compound the cost of asking as well. The third project's interview is half the length of the first.
- **Taste into files**: record recurring judgment patterns, measured failures, and the reasons for every rejection.

## Logs and progress

- **There are two kinds of logs**: root `logs/` = outer loop (collection purposes, ingest verdicts, lint results) / project `logs/` = inner loop (the event log and session records below). The format standard is the same.
- **Event log** (project `logs/log.md`, append-only): record decisions, gate passes, contract changes, phase completions, project source collections (with one line of purpose), and errors. Format standard: `## [YYYY-MM-DD HH:MM] type | title` + body. Keep the prefix and the log stays parseable with simple tools (grep etc.).
- **Session records** (`logs/sessions/`, one file per session): write at session end — a summary + decisions made + the user's instructions verbatim + next steps.
- **Progress file** (`PROGRESS.md`): one row per phase/milestone from the execution plan, each with status (pending / in progress / awaiting gate / done) + date + deliverable link. Progress = completed phases / total. Update immediately on phase transitions and gate passes — saving state comes before reporting.
- **`PROGRESS.md` is the review hub**: rows awaiting a gate link to the file the human should open and the criteria to judge by (the contract's evaluation criteria, requirement IDs). The human starts at `PROGRESS.md` and moves only by links — never by digging through folders.

## The three-sentence pattern — the basic language of delegation

① "Don't do X — go only as far as Y" (scope first)
② "Attach a source to every claim" (demand evidence)
③ Instead of "do it again": "from now on, judge by this criterion and do it again" (feedback via criteria)

## Installation procedure — executed by the agent

**Install only what is listed below. Add further devices only when the need is proven.**

**Step 0 — Preflight, then the global constitution.** First, probe the host: can the agent write agent-instruction files (`CLAUDE.md` and its kin) unattended? Some hosts protect them behind per-file live approval, and an unattended install will stall there. If they are protected, either present the human **one approval packet up front** listing every instruction file the install will write, or fall back to plain filenames (`CONSTITUTION.md`, `PROJECT_PROTOCOL.md`) — and state explicitly that fallback files are **not auto-loaded**: the agent must be told to read them at each session start.

Then the global constitution (first-time users): if there is no user-level global config file (`~/.claude/CLAUDE.md` or your tool's equivalent), create it first. Five base principles:
   - ① Think before coding — state assumptions explicitly; when uncertain, ask instead of guessing.
   - ② Simplicity first — the minimum implementation of what was asked. No speculative features, no abstractions for single-use code.
   - ③ Surgical changes — modify only what is strictly necessary; never "improve" adjacent code uninvited.
   - ④ Goal-driven execution — define the success criteria first, then iterate until verified.
   - ⑤ Plan first — for multi-step work, present a plan and get approval before executing.

   Add your own situational rules on top (response language, frequently used commands, recurring-task rules). **The constitution has four layers**: global → workspace constitution (outer-loop protocol) → shared project protocol `projects/CLAUDE.md` (inner-loop protocol) → the individual project constitution (Phase 2). Each layer stacks on the one above it, and in tools that load nested CLAUDE.md files hierarchically, this structure enforces itself.
**Step 1 — Scaffold first, then interview.** The interview record has to land somewhere immutable, so the folders come first. Ask the user where to install (default: a folder in the current directory), create the workspace once, then create the first project skeleton under `projects/`. Afterwards every new project gets the same skeleton and starts from Phase 0. The default tree — these are the names the scaffolder writes; rename them if you like, but rename them **in the script**, not per project:

   ```
   llm-delivery-loop/             ← workspace = outer loop (installed once)
   ├── CLAUDE.md                  # workspace constitution — identity/principles + outer-loop (wiki) protocol
   ├── RULES.md                   # prevention rules (the ratchet) — each with its origin
   ├── index.md                   # workspace index — link-closed catalog (query entry point)
   ├── raw/                       # second-brain source layer — project-independent collections (read-only)
   ├── wiki/                      # knowledge layer — the cross-project second brain
   ├── templates/                 # task prompt & document templates
   ├── logs/                      # outer-loop log — collection purposes, ingest verdicts, lint (log.md)
   ├── tools/                     # reference scaffolder + lint (shipped with this repo)
   └── projects/                  ← inner loop = one folder per project
       ├── CLAUDE.md              # shared project protocol — Phase 0–6 gates, naming, document & log standards
       └── YYYY-MM-DD_<name>/     ← start date, never renamed
           ├── 00_CONTRACT.md     # Phase 0 · gate ①
           ├── 01_REQUIREMENTS.md # Phase 1
           ├── 03_EVIDENCE.md     # Phase 3 · gate ②
           ├── 04_SCOPE.md        # Phase 4 · gate ③
           ├── 05_engineering/    # Phase 5 deliverables (delivered versions frozen)
           ├── 06_VERIFICATION.md # Phase 6 · gate ④
           ├── CLAUDE.md          # project constitution (Phase 2 — scope constraint, project-specific rules)
           ├── PROGRESS.md        # progress — the review hub
           ├── raw/               # this project's sources + the interview record (immutable)
           └── logs/              # log.md (events) + sessions/ (session records)
   ```

   Generate this with a script, not by hand — the naming convention is the first thing to drift. **Naming is not cosmetics here: it is what makes the phase order survive a file explorer.** Two scripts live in `tools/`: the scaffolder above, and the lint from the outer loop. **Reference implementations ship in this repository ([`tools/scaffold.py`](tools/scaffold.py) and [`tools/lint.py`](tools/lint.py)) — copy them in and start from them.** Your agent may rewrite them in any language, but a rewrite must keep the same verdicts: `lint.py --selftest` plants the step-4 negative fixtures plus empty-criteria, empty-section, bare-judge, raw-deletion, malformed-state and name-traversal fixtures — one at a time — and fails unless each is caught by its exact error at its exact path; run it against any rewrite. Two installers that disagree on what passes are two different methodologies wearing one version number. And in every case the lint decides by **exit code**, not by prose.

   The scaffolder pre-creates every numbered document as a headed skeleton — an empty `03_EVIDENCE.md` in a fresh project is a to-do, not litter, and link-closure still applies to it: every phase document is reachable from the project's `PROGRESS.md`.

**Step 2 — Interview → contract.** See **Phase 0** above for the full question set, the triggers, and the five exit tests. Preserve the answers verbatim with IDs in the new project's `raw/`, then organize them into the contract and confirm with the user. **Do not skip this and write the contract from inference** — that is the single most expensive shortcut in this document.

   Additionally: set the three permission tiers (unattended = read-only, always; reversible = backup first; irreversible = explicit re-confirmation) and a measurement baseline (measure the current value once, now).

**Step 3 — Engrave the constitutions.** In the **workspace constitution** (skeleton of six parts — identity in one sentence / principles / how we work / permissions and limits / scope constraints / center), write the outer-loop protocol (Ingest·Query·Lint, wiki standards). In the **shared project protocol** (`projects/CLAUDE.md`), write the Phase 0–6 gate, document, and log standards, plus the instruction: **"Read the active project's contract (`00_CONTRACT.md`) before starting any work. Work outside the contract only after contract-change approval."** Transfer only the rules needed, rewritten in the user's own language — never copy this document wholesale. Purpose: a future session's agent behaves by the methodology without ever seeing this file.
**Step 4 — Verify the installation.** Create the first project folder under `projects/` and run Phase 0 once — the interview first, then a one-page contract (2W1H + constraints + evaluation criteria + failure conditions + execution plan), then **T2 on that contract**. Negative tests, all three: feed a below-criteria contract to the gate and confirm FAIL; create a document that no link reaches and confirm the lint catches it as an orphan; create a wrongly-named project folder and confirm the lint catches it. Report completion with this demonstrated behavior, not with words.

## Principles

- The human's job: set the criteria, judge at the gates. The agent's job: everything else.
- This document is a pattern. Instantiate folder names, formats, and concrete gate shapes with your agent to fit the project — **but instantiate them once, in a script.** Every convention in here that is only written down is a convention that will drift.
- The rules in this document came from things that broke. If something breaks for you, open an issue — that is how the ratchet turns.

---

## About LDL

**LDL — LLM Delivery Loop.** Maintained by [@daniel-kjseo](https://github.com/daniel-kjseo). MIT licensed — use it, fork it, rename it to fit your team.

- Site: <https://daniel-kjseo.github.io/llm-delivery-loop/>
- Source: <https://github.com/daniel-kjseo/llm-delivery-loop>
- Related reading: [LLM Wiki](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f) by Andrej Karpathy — LDL is the delivery-side counterpart.

Found this useful, or ran it on a real project? Open an issue with what broke — every failure becomes a rule in `RULES.md`, which is the whole point.
