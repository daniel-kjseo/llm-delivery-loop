# Authority and release policy

## One authority for "what version is this"

| Question | Answer | Where it is decided |
|---|---|---|
| What is the public stable release? | **v0.7.0** | the published tag `v0.7.0` in the GitHub repository |
| Which commit is that? | the commit the published tag points to | read it from the tag and its GitHub Release, never from a copy pasted into a document |
| What is in this working tree? | **v0.7.0**, the same version as the published tag | `tools/scaffold.py` `LATEST_VERSION` and `.ldl-version` in a new workspace |
| Which one may be cited as shipped? | v0.7.0 | this document |

`LATEST_VERSION` is the scaffold's answer to "what do I create today". For
v0.7.0 it now agrees with the published tag, so a claim about what LDL does in
production refers to v0.7.0.

There is one version again, which is the point: the tag is the authority, and a
reader who wants the exact commit resolves the tag rather than trusting a
transcribed hash. v0.6.1 and every earlier release stay in the history below and
in the version sections of the README as the record of what shipped when.

## Roles

| Role | Who | May do | May never do |
|---|---|---|---|
| Owner | the actual human | set the contract, approve gates, accept delivery, publish | be simulated by any agent |
| Owner proxy | an explicitly delegated agent | record decisions, run harness commands, promote mechanically | claim to be the human owner, or invent the human's acceptance |
| Maker | the implementing agent | write product sources, tests and documents | approve its own work, write gate rows, decide its own promotion |
| Verifier | a read-only reviewer | rerun commands, read diffs, report findings | edit product sources or the target workspace |

An AI owner proxy is a delegated agent, always labelled `delegated-agent`. No
agent verdict is recorded as `human`, and no agent verdict substitutes for the
actual recipient's acceptance.

## Release policy

1. Tests passing is a *harness* result. It licenses a candidate, not a release.
2. A feature branch or PR may be published after the deterministic suites and
   an independent read-only review pass.
3. Promotion to stable additionally needs recorded evidence that the change was
   exercised on real work, and the owner's decision. It is never automatic from
   a green suite.
4. Efficacy claims (time saved, review burden reduced) need a measured
   baseline *and* recorded human acceptance. Without both, the measurement
   record keeps `claimed_improvement_pct: null`; `tools/execution.py
   measure-validate` refuses anything else.
5. Historical version notes stay where they are. Superseding a claim means
   adding the new state, not deleting the old record.

## What the v0.7.0 mechanisms are, and are not

- The approved-job manifest binds declarations (project, contract hash,
  profile, phase, argv hash, runner, cwd, output root) to an approval written
  outside the project. It is **not an OS sandbox** — nothing confines a
  launched process — and it is **not human authentication** — an approval file
  proves a file exists, not that a person wrote it.
- The invocation lock is POSIX `flock` (macOS/Linux). Windows is not supported;
  `tools/execution.py` reports `LOCK_PLATFORM = "unsupported"` there rather
  than pretending the reservation is atomic.
- A legacy invocation (no `--job`) still works and prints
  `ENFORCEMENT - legacy (limited: ...)`. That label is the accurate description
  of it; do not describe legacy invocation as secured.
- `tools/execution.py status` derives a report and writes nothing. It never
  generates PROGRESS.md or a gate decision, and anything missing or unparsable
  reports UNKNOWN, which can never roll up to PASS.

## Trust and measurement boundary (v0.7.0)

An approved job binds a declaration — project, contract hash, profile, phase, argv hash, runner id and role, cwd, output root — to an approval record stored outside the project. That is the whole claim. It is **not an OS sandbox**: no launched process is confined, and a command that lies about what it writes still writes it. It is **not human authentication**: an approval file proves a file exists outside the maker's tree, not that a person created it, and the owner/launcher alone is responsible for the provenance of the digests it pins. Legacy invocation without `--job` is labelled *limited* and must never be described as secured.

Freezing is the same kind of claim. A contract's `frozen_sha256` only shows the document hashes itself; anyone who edits a truth table can recompute it. Only a digest a caller pinned before the edit (`--expected-sha256`) reports `BOUND`; without it the report reads `UNBOUND`/`NOT_RUN`, never "frozen".

Measurement separates four things that are routinely merged: process completion, artifact validity, reviewer judgement, and the actual recipient's acceptance. `time_to_artifact` is null unless some invocation has a validated reconciliation report, and it measures the launched child process only — not the request-to-acceptance span. Acceptance recorded as a string is `CLAIMED_UNVERIFIED`; `actual_human_acceptance` stays `NOT_RUN` until the actual recipient says otherwise, and no AI proxy substitutes for them. Cost amounts stay null while the billing arrangement is unknown; the 30% improvement figure is a target, not a result.
