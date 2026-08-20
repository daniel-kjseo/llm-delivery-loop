# LDL — LLM Delivery Loop

**A delivery methodology for AI agents: contract first, gated delivery loop, compounding second brain.**

**LDL** (LLM Delivery Loop) is a pattern for delivering real results with AI agents. In one sentence — **humans govern through contracts and gates, agents execute through loops, and every project compounds into a second brain.** Three elements: (1) contract & gates (governance) (2) loop execution (delivery) (3) compounding assets. If the [LLM Wiki](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f) compounds knowledge, LDL compounds delivery.

> **Quick start** — paste this document into your agent and ask: *"Install this into my workspace."*
> Works with Claude Code, Codex, Cursor, Gemini CLI, or any agent that can read and write files. Nothing to install, no dependencies — in LDL the methodology **is** the folder structure.

**What's inside**: the double loop (inner delivery loop + outer knowledge loop) · seven phases from contract to verification · four evidence-backed approval gates · the v0.3.0 Evidence & Safety Model · the v0.4.0 Lean Working-MVP Model · the Ingest / Query / Lint protocol for a compounding wiki · a folder tree you can install today.

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

## v0.3.0 — Evidence & Safety Model

v0.2 made the contract structurally testable. v0.3.0 closes the next failure mode: a workspace can be structurally green while its gates, evidence, calculations, or execution readiness are not. It strengthens the existing documents rather than adding another phase.

1. **Gates are a state machine, not prose.** `PROGRESS.md` carries G1–G4 with one verdict from `PENDING | HOLD | PASS | FAIL | SUPERSEDED`. A PASS names the contract version, approval mode, approver, non-future UTC time, and a unique substantive approval artifact under project `raw/` that identifies that gate and contract version. The matching phase rows must be done and the append-only log must contain `GATE-PASS: G<n> contract=<version>`. A later gate cannot pass while an earlier gate is not PASS. A new contract version requires new gate evidence; old decisions remain history.
2. **Evidence is a chain.** Every `[measured]` or `[proven]` claim has a unique Claim ID, substantive claim, `ACTIVE | DISPUTED | SUPERSEDED` status, source artifact captured under project `raw/`, real capture date, scope/window, and transform or reproducer. A hand-copied summary or live external URL is not immutable primary evidence. The lint checks the chain exists; a separated verifier judges whether it is true.
3. **Safety propagates by impact, not by document section.** `04_SCOPE.md` maps each ready action to one or more uniquely identified impact dimensions, preconditions, an approval tier, canary, rollback, and readiness. If any linked dimension is `HOLD`, `FAIL`, or `NOT_RUN`, that action cannot be ready — an empty map, duplicate ID, or changed group name does not create an escape hatch.
4. **Quantitative work is reproducible.** The contract declares whether quantitative claims exist. If yes, the scope records baseline/candidate windows and units, assumptions, formula or executable reproducer, and reconciliation. Conditional outcomes stay as scenarios; “asked”, “confirmed”, and “succeeded” are different states.
5. **Four verdicts stay separate.** Harness, Product, Execution readiness, and Method conformance are reported independently. `NOT_RUN` never rolls up to PASS. A historical gate-order violation can coexist with a repaired Product PASS, but Method conformance for that run remains FAIL.
6. **Verification is read-only by default.** The verifier works in an external review/scratch workspace, reconstructs the verdict from contract and primary evidence, and reports target mutation. A checker that rewrites target logs has contaminated its own audit.

The reference lint implements only deterministic boundaries (schema, links, vocabulary, ordering, propagation). Structural headings, tables, and verdicts inside fenced code or HTML comments are examples/hidden content and do not count. Each required scalar appears exactly once. The lint does **not** pretend to decide whether evidence supports a claim or whether a solution is good. That remains a separated semantic gate.

New v0.3 workspaces carry a root `.ldl-version` marker. Removing a project's Governance profile does not downgrade it into a permissive legacy project. Marker-free pre-v0.3 workspaces remain readable; `init` refuses to mark a nonempty legacy workspace unless the operator explicitly passes `--migrate-v03`.

## v0.4.0 — Lean Working-MVP Model

v0.3 prevented structurally green work from laundering bad evidence. A field run then exposed the opposite failure: the method could be correct yet consume more context, gates, and checker turns than the product. v0.4 keeps independent judgment and deletes repeated narration.

1. **The first executable increment is `MVP-1`.** A core library or unit-test green is not a working MVP. `PROGRESS.md` carries an Increment ledger. An increment reaches PASS only when one substantive user journey has deterministic tests, rendered/browser evidence, an independent check, and a typed `ldl-mvp-evidence-v1` manifest under `05_engineering/` whose three artifact hashes match. Empty files and final-report self-attestation fail. Product PASS and P5/P6 completion require `MVP-1` PASS.
2. **Context travels as handles.** A phase packet is at most 8KB and contains artifact `path + SHA-256`, relevant requirement IDs, exact commands, blockers, and a ≤1,500-character summary. Full owner/checker reports stay on disk. `tools/lean.py verify` rejects oversized packets, embedded verbatim content, path traversal, missing artifacts, and stale hashes.
3. **Execution economy is contractual.** Every v0.4 contract sets ceilings for packet bytes, relay/checker summary characters, checker runs, correction reruns, and a token/call ledger path. Completed delivery must contain valid non-negative integer model/token/call/checker/wall-time rows with identity and evidence; a decorative or malformed row does not count as telemetry.
4. **One batch, one rerun.** Each increment gets one consolidated checker. Failure opens one root-class correction batch and at most one rerun. Serial one-symptom checker loops stop at HOLD instead of growing without bound.
5. **Delta gates, deterministic first.** Tests, hashes, diffs, packet validation, generated sweeps, and browser traces run before an LLM. A budget-only amendment rechecks the contract delta and feasibility; unchanged evidence hashes carry prior proof. Whole-gate replay is reserved for changed product/evidence/scope identity.
6. **Owner/maker writes are physically separated.** The workspace has `owner/inbox.md` and `owner/outbox.md`. Owner writes there; maker preserves an accepted decision exactly once under project `raw/`. Reviews point to the canonical artifact instead of copying it.
7. **Raw evidence is recursive.** Files below nested raw directories — including names such as `tools`, `.git`, `node_modules`, and `__pycache__` — remain immutable. Raw/project directory symlinks are rejected. Contract archives are immutable byte snapshots: L5 still hashes them, while L1 treats only `raw/contract-archive/` as link-opaque.
8. **Verdicts stay separate.** Harness green, core-prototype green, working-MVP PASS, readiness, method conformance, and final delivery are different claims. `NOT_RUN` remains visible; reducing the pass line must be called a contract change, never token optimization.

The reference v0.4 regression suite proves both sides: a completed working MVP fixture passes, while missing rendered evidence, missing independent checks, absent cost telemetry, oversized/stale packets, nested-raw mutation, archive deletion, and directory-symlink bypasses fail deterministically.

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
- **T3 The judge** — every criterion names its judge and its method, in one grammar the lint enforces: `judge: <type> (<method/who>)` — `judge: code (test script)`, `judge: human (the owner)`. A bare `judge: human` names a species, not a judge. Every criterion that *can* be decided deterministically *is* decided by code, and **at least one criterion uses a separated non-code judge** (an independent human, a different model, or a fresh context — the Phase 6 ladder). Two independent project runs found defects only after their automatic suites were green; automation cannot be the only view of work produced by an agent. The lint enforces the judge grammar and this minimum separation. Whether a criterion itself should be code-decidable remains a judgment call held by T2 and the human at the gate.
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
- **Gate ① contract approval: no contract (2W1H + constraints + evaluation criteria + failure conditions + execution plan + verification setup + five exit-test results), no Phase 1.** `Verification setup` names the verifier instances, exact lint command, and approver; each T1–T5 result is written separately. Empty fields and template placeholders fail the lint. Every field either cites an interview ID or carries `[hypothesis]` with its Phase 3 research item — **except the evaluation criteria and failure conditions, which can never be hypotheses** (an undecidable pass line is pre-contract research, not a contract). Run the lint once before this gate — it is the gate's deterministic pre-check. And write the approval line only after all five exit tests have passed; approving first and testing after is how the author's blind spots ship.
- **Governance profile (v0.3):** write the contract version, approval mode (`human` or pre-authorized `delegated-agent`), whether quantitative claims exist, and risk level. `Verification setup` also fixes an external verifier workspace and `Target access: read-only`. These fields bind every later gate row to the contract that was actually approved.

## Phase 1 — Requirements definition

Deliverable: `01_REQUIREMENTS.md`

- **Requirements definition = problem definition.** Clients cannot define requirements well. Listen and define them on their behalf.
- Elicitation: primary utterances (interviews, meeting notes, the original request) get the highest weight. Preserve verbatim; separate source from interpretation.
- Specification: record every requirement in the Requirements ledger with a **unique ID + type + priority + requirement + verification method + source**. One requirement, one sentence. No ambiguous words. Phase 6 verdict IDs must exactly equal this ledger's IDs: no missing IDs, no invented `R-FAKE`, no duplicate verdicts.
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
- Research the background of the requirements and finalize the problem. Every material claim enters the evidence ledger as `Claim ID | Label | Claim | Source artifact | Captured at | Scope/window | Transform/reproducer | Status`. Labels are `[hypothesis]` / `[measured]` / `[proven]`. A measured/proven row without its primary artifact, date, measurement window, and reproduction path is incomplete, no matter how polished the summary looks.
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
- **Evidence & Safety table (v0.3):** list impact dimensions (`PASS | HOLD | FAIL | NOT_RUN`) and map every proposed action to those dimensions, preconditions, approval tier, approval evidence, canary, rollback, and `Ready: YES | NO`. `YES` is legal only when every linked dimension is PASS and required approval evidence exists.
- **Quantitative model (when declared in the contract):** record baseline/candidate window and unit, assumptions, formula/reproducer, and reconciliation. Compare like periods and units. Show conditional outcomes as separate scenarios instead of compressing them into one optimistic range.
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
- Write the verification report (`06_VERIFICATION.md`) with exactly one verdict for every Requirements-ledger ID from `PASS | FAIL | HOLD | NOT_RUN`, then report **Harness / Product / Execution readiness / Method conformance** separately. A requirement PASS requires a resolvable local evidence link. Product PASS requires every requirement PASS; READY requires Product PASS, at least one impact dimension and action, and every impact dimension PASS. Harness PASS implies neither. Historical violations are `NONE | PRESENT`; PRESENT forces Method conformance FAIL for that run.
- The independent verifier starts from the contract and primary evidence, not the maker's final prose. It works outside the target, leaves target mutation at `0 files`, and identifies its method in the report. **The official lint writes `logs/.lint-state.json`; therefore running lint directly on the target is an operational check, not a read-only independent audit.** For independent verification, run the copied toolset on a clone/scratch workspace and compare the target tree before/after.
- Historical failures are not self-attested only in the current report. Append a machine-readable `LDL-VIOLATION: <id>` line to the append-only project event log when a gate-order, contract-version, or verifier-contamination violation occurs. Once present, the lint requires `Historical violations: PRESENT` and `Method conformance: FAIL` for that run.
- On completion, feed back: promote units of meaning (decisions, lessons, improved templates) to the workspace root, curated through the five verdicts, and run one lint pass — see the outer loop.
- **Gate ④ final delivery: the human gives final confirmation against the contract's evaluation criteria. Rejection is voiced in the language of the criteria — and the loop resumes.**

## Four human gates

Contract approval (Phase 0) / problem finalized (Phase 3) / solution finalized (Phase 4) / final delivery (Phase 6). At each gate, the head of the phase document carries a **four-line review summary** (what was done / key conclusion / the judgment being requested / where the detailed evidence lives), so the human opens one file and judges in minutes. Everything else belongs to the loop. Record every gate pass in the append-only event log and the `PROGRESS.md` Gate ledger; a generic “go ahead” is not silently promoted into approval unless it explicitly identifies the gate decision.

## Outer loop — Ingest · Query · Lint

The operation of the workspace root (`raw/` · `wiki/` · `index.md` · `RULES.md` · `templates/` · `logs/`). **As the wiki accumulates, it becomes a second brain.**

- **Ingest** — two entrances, both behind an approval gate. Curate with the five verdicts: ingest / merge / already covered / exclude / hold. When unsure, hold — don't guess. The most important number is not what you added but what you kept out.
  - **Source intake** (root `raw/` → `wiki/`): every source needs **one line of collection purpose (why)** — recorded in the root `logs/` at collection time. No purpose, no ingest — hold it. The agent reads the content, judges it against the purpose, and generates relation links seeded by that purpose.
  - **Project promotion** (Phase 6 feedback): promote **units of meaning**, not whole files — decisions, gate passes, and contract changes from the event log; verification verdicts; failures and lessons. Decisions → judgment pages, gates/milestones → event pages, lessons → `RULES.md` (with their origin — every task reads the rules before starting), improved templates → `templates/`.
- **Query**: consult the workspace index (root `index.md` — the catalog of wiki pages, projects, and held problems) first, then answer. Reusable answers don't stay in chat — file them back into the wiki as new pages, so queries compound too. **The index must be link-closed: every document in the workspace is reachable from `index.md` by following links.** An index you cannot navigate is a folder listing with extra steps. And an index is a catalog, not a log — **edit it, never append**, or you end up with the same table twice.
- **Lint**: once per project feedback cycle, plus once before every gate ① — **and make it a script, not a habit.** What it decides by exit code: broken links; orphan documents; naming; the Phase 0 contract; raw immutability; append-only logs; installation completion; and, for v0.3 projects, Gate-ledger integrity, evidence-chain completeness, quantitative-model fields, safety propagation, and verdict roll-up. What it does **not** decide: whether evidence is true, a model is defensible, or a recommendation is good. Those remain separated semantic judgments. Whether a discovered defect became a meaningful `RULES.md` entry is also a Gate ④ call; the lint must not accept filler merely because starter text changed. **A rule you have to remember is a rule you will eventually break — promote deterministic boundaries to checks, but never make regex pretend to be expertise.**
  Scope, so two lints agree on what they judge: link-closure applies to the markdown the workspace manages; binaries and raw sources are tracked by the manifest, not link-crawled; and external URLs are outside the lint entirely — it never touches the network, so they neither pass nor fail. The reference lint ships exit codes for none of the semantic checks.
- **Wiki page standard**: head each page with a type (concept / procedure / insight / event / judgment) · tags · date · source (external / own thinking) · evidence label (`[hypothesis]`/`[measured]`/`[proven]`). Body links to at least one related page, with the relation marked (supports / extends / refutes). **Typed pages plus typed links are what a second brain actually is.**
- **Compound the interview too**: answers that repeat across projects (constraints, evaluators, permission boundaries) promote to a **standing conditions** page. The next project's interview opens with *"same as last time?"* and asks only what changed. The outer loop is supposed to compound knowledge — it should compound the cost of asking as well. The third project's interview is half the length of the first.
- **Taste into files**: record recurring judgment patterns, measured failures, and the reasons for every rejection.

## Logs and progress

- **There are two kinds of logs**: root `logs/` = outer loop (collection purposes, ingest verdicts, lint results) / project `logs/` = inner loop (the event log and session records below). The format standard is the same.
- **Event log** (project `logs/log.md`, append-only): record decisions, gate passes, contract changes, phase completions, project source collections (with one line of purpose), and errors. Format standard: `## [YYYY-MM-DD HH:MM] type | title` + body. Keep the prefix and the log stays parseable with simple tools (grep etc.).
- **Session records** (`logs/sessions/`, one file per session): write at session end — a summary + decisions made + the user's instructions verbatim + next steps.
- **Progress file** (`PROGRESS.md`): one phase-progress table plus a Gate ledger. The Gate ledger columns are `Gate | Verdict | Contract version | Approval mode | Approver | Approved at | Evidence`; PASS evidence links to an immutable record under project `raw/`. Update immediately on transitions — saving state comes before reporting.
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
   ├── .ldl-version               # schema marker; prevents silent legacy downgrade
   ├── CLAUDE.md                  # workspace constitution — identity/principles + outer-loop (wiki) protocol
   ├── RULES.md                   # prevention rules (the ratchet) — each with its origin
   ├── index.md                   # workspace index — link-closed catalog (query entry point)
   ├── raw/                       # second-brain source layer — project-independent collections (read-only)
   ├── wiki/                      # knowledge layer — the cross-project second brain
   ├── templates/                 # task prompt & document templates
   ├── logs/                      # outer-loop log — collection purposes, ingest verdicts, lint (log.md)
   ├── owner/                     # owner inbox/outbox — owner never writes project evidence directly
   ├── tools/                     # scaffold.py + lint.py + integrity.py + v0.4 lean.py
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
           └── logs/              # log.md + cost-ledger.csv + sessions/
   ```

   Generate this with a script, not by hand. The reference toolset is [`tools/scaffold.py`](tools/scaffold.py), [`tools/lint.py`](tools/lint.py), [`tools/integrity.py`](tools/integrity.py), and [`tools/lean.py`](tools/lean.py). `scaffold.py init` creates a new v0.4 workspace; it refuses a nonempty marker-free workspace unless `--migrate-v03` is explicit. A marked v0.3 workspace upgrades only with `--migrate-v04` and only when `projects/` contains no project directories; move closed projects out or start a fresh v0.4 workspace. The tool never rewrites live v0.3 contracts. `scaffold.py new` registers the project in `index.md`. A rewrite must keep the same verdicts: `lint.py --selftest`, `tests/test_v030.py`, and `tests/test_v040.py` cover the legacy harness, composed v0.3 false-green paths, and v0.4 token/MVP/raw boundaries. Two installers that disagree on what passes are two different methodologies wearing one version number.

   The scaffolder pre-creates every numbered document as a headed skeleton — an empty `03_EVIDENCE.md` in a fresh project is a to-do, not litter, and link-closure still applies to it: every phase document is reachable from the project's `PROGRESS.md`.

**Step 2 — Interview → contract.** See **Phase 0** above for the full question set, the triggers, and the five exit tests. Preserve the answers verbatim with IDs in the new project's `raw/`, then organize them into the contract and confirm with the user. **Do not skip this and write the contract from inference** — that is the single most expensive shortcut in this document.

   Additionally: set the three permission tiers (unattended = read-only, always; reversible = backup first; irreversible = explicit re-confirmation) and a measurement baseline (measure the current value once, now).

**Step 3 — Engrave the constitutions.** In the **workspace constitution** (skeleton of six parts — identity in one sentence / principles / how we work / permissions and limits / scope constraints / center), write the outer-loop protocol (Ingest·Query·Lint, wiki standards). In the **shared project protocol** (`projects/CLAUDE.md`), write the Phase 0–6 gate, document, and log standards, plus the instruction: **"Read the active project's contract (`00_CONTRACT.md`) before starting any work. Work outside the contract only after contract-change approval."** Transfer only the rules needed, rewritten in the user's own language — never copy this document wholesale. Purpose: a future session's agent behaves by the methodology without ever seeing this file. The reference lint fails while either installation sentinel remains; deleting the sentence without replacing the protocol is not engraving.
**Step 4 — Verify the installation.** Confirm `tools/scaffold.py`, `tools/lint.py`, `tools/integrity.py`, and `tools/lean.py` exist and execute inside the new workspace. Run `python3 tools/lint.py --selftest`; validate one packet with `python3 tools/lean.py verify <packet.json> --root <project>`; then create the first project, confirm index registration, and complete Phase 0 with the Governance profile, Delivery profile, Execution economy, and read-only verifier setup. In a disposable fixture, demonstrate at least one failure from each class: below-criteria contract, orphan document, Gate-order violation, source-less measured claim, HOLD action marked ready, NOT_RUN rolled into Product PASS, MVP-1 without rendered/independent proof, and stale artifact hash. Report executed verdicts, not intentions.

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
