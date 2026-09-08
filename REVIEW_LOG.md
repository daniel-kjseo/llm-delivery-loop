# REVIEW_LOG — findings that became rules

Every rule here exists because something failed. The rule is short; the reason
is the part that stops it happening again.

## Prevention rules

- **R-COMPOSE** — validate a whole start-to-result path per profile, not a
  table of individually correct checks. v0.6.1 had a correct-looking
  predecessor table (`P4 → G2`, `P5/P6 → G3`) that no `startup-reversible`
  project could ever satisfy, because that profile is designed to reach MVP
  under G1. Every check passed its own test; the composition was unreachable.
  Tests must walk P0 → operations → run → result for each supported profile.
- **R-TRUST** — a declared phase, ID or hash is a declaration. It is not
  authority, not human approval, and not proof that a thing happened. Where a
  mechanism binds strings, say so, and name what it does not do (OS sandbox,
  authentication) in the same sentence.
- **R-OUTCOME** — process COMPLETE, artifact valid, reviewer verdict and actual
  user acceptance are four verdicts. A process that exits 0 without writing its
  declared outputs is a completed process with an invalid artifact set. An
  approved artifact is still NOT_RUN for user acceptance.
- **R-MODEL** — never mix a model change into a method-change measurement.
  `comparison_kind` is recorded on every measurement, and `cross-model` carries
  a caveat that no method effect can be read from it.
- **R-TRANSACTION** — one maker at a time, in an isolated tree, with target
  drift checked before promotion. Promotion is mechanical and owner-decided,
  never a side effect of a green suite.
- **R-UNKNOWN** — missing, unparsable or unobserved data reports UNKNOWN or
  null. UNKNOWN never aggregates into PASS, and a null baseline never supports
  a percentage.

## Changes and failures

- 2026-09-08 — v0.6.1 review (`03_LDL/reviews/ldl-review_2026-09-08.md`)
  registered findings D1–D4 as acceptance criteria A1–A9.
- 2026-09-08 — v0.7.0 candidate. New failure-regression classes now covered by
  `tests/test_v070.py`: profile-blind gate composition (R-COMPOSE);
  self-attested approval and maker-writable trust roots (R-TRUST); non-atomic
  invocation-ID reservation under concurrent processes; launch failure recorded
  as completion; stale/missing/collided declared outputs (R-OUTCOME);
  gain claims without a baseline or human acceptance (R-MODEL, R-UNKNOWN);
  evaluator truth tables with an unstated zero/missing/partial case.
- The v0.6.1 safety test `test_p4_requires_g2_even_after_g1` was **kept, not
  deleted**. It moved to `HighRiskPolicyTests`, which is the profile it was
  always describing, and a positive startup-profile test was added beside it.

## Independent review 1 (v0.7.0 candidate) — prevention rules

Existing suites were green while adversarial probes still executed unsafe outcomes. New rules, each with a counterexample in `tests/test_v070_correction.py`:

1. A profile's launch prerequisites must be reachable: startup-reversible P4/P5/P6 depend on P0/P1/P2 (and P4 scoping for P5/P6), never on P3 research staying open.
2. The parsed control plane must be the active one: tables inside ``` fences are illustrations, and a duplicate gate or phase row is refused, not resolved by last-write-wins.
2b. **Independent review 2, F1** — one fence toggle plus one `re.search` was not a Markdown reader. An HTML-commented ledger, a four-backtick fence "closed" by `~~~`, a second appended ledger and a verdict row standing in for the separator each launched a child. **Rule R-ACTIVE-TEXT**: mask inactive regions with the reader's own rules (matching delimiter char and length, comments, unclosed block stays inactive) before any control table is read; refuse duplicate active sections and validate the separator row instead of skipping line 2. One parser, not one regex per fixture.
3. A binding binds the *actual* role and output declaration, and resolves the approval file itself — an approvals directory outside the project is worthless if the file inside links back in.
4. An expected-output manifest is frozen before launch and reconciled from that copy; declared output paths are reserved across live processes and released on completion, abort and launch failure.
4b. **Independent review 2, F2** — reservations keyed by resolved *path strings* let `shared.txt` and `SHARED.txt`, and a hard link to the same inode, be claimed by two live invocations; each reported the other's bytes as its own artifact. **Rule R-RESOURCE-ID**: a reservation claims a resource, not a spelling. Collision keys are NFC + casefold on every platform plus `dev:ino` when the file exists, and a multiply hard-linked declared output is refused. Conservative and portable; still not an OS sandbox.
5. Documented CLI paths are executed end-to-end in tests; a subcommand nobody runs from argv is not shipped.
6. Status may not reach PASS by omission: gate PASS rows are revalidated against typed evidence, pending phases and non-PASS final verdicts block, requirement PASS rows citing missing evidence block, and malformed report JSON reports UNKNOWN instead of crashing.
7. Gain claims require typed finite metrics, a valid date and a measured baseline with unit, window, source and a positive value; >100% or nonpositive claims are refused.
8. Unknown stays null: a wrong-header cost ledger is UNPARSABLE, an abort with no artifact has no time_to_artifact, child wall time is named separately, cost amounts stay null while billing is unknown.
8b. **Independent review 2, report blockers 1-2** — `Infinity` validated as a human metric, a baseline value and a claim; `amount:'free??'` validated as a metered cost; a correct header followed by `bogus,,,` became four confident zeros. **Rule R-FINITE**: one `finite_number()` helper decides every numeric field (bool, NaN, ±Infinity, wrong type, negative are refused), a metered amount needs currency and source, and a telemetry column with any blank or invalid cell stays **null** — a partial sum is never reported as a total, and zero is only reported where zero was observed.
9. Freezing requires a caller-pinned digest; a self-recomputed hash reports UNBOUND. **Review 2, blocker 3**: the delivered rubric companion and the staged governance reference must teach that too — the pin is `--expected-sha256`, held *outside* the document and recorded at the real freeze time; without it the result is `UNBOUND`/`NOT_RUN`; structure consistency is not freezing and nothing here proves who froze it. A generated `frozen_at` is the candidate's declaration time, never a stand-in for an owner's freeze.
9b. **Review 2, blocker 4** — the VOC companion replaced the pinned source's step 4 ("전체 판독, 정밀도 표(테마별 매치→판독)") with `매치 × 표본 정밀도` and an unsupported 0.5 cutoff. **Rule R-SOURCE-STEP**: an "executable form" of a source procedure keeps that procedure. Sampling calibrates and corrects the dictionary; the matched set is then read in full, and unknown data stays blank/NOT_RUN rather than estimated.
10. A frozen source rubric is preserved verbatim (GNTC 1개+종속 = PASS); changing a truth table needs its own approval, never a companion document quietly disagreeing.
11. Docs state the shipped surface: eight tools, runnable commands, opt-in `--migrate-v070`, and the stable v0.6.1 / unpublished v0.7.0 candidate distinction.
12. **CI run 34282452224 (Ubuntu, Python 3.11), release blocker** — `tools/invoke.py` installed its SIGTERM/SIGINT handlers only after `reserve_and_start`, `reserve_outputs` and `record_job_binding`, so a signal arriving once the STARTED row was already on disk was taken by the default handler: the wrapper died with a STARTED row and no terminal row (ledger 1/0/0 instead of 1/0/1), and a SIGINT could unwind out of `reserve_and_start` before it returned the id nobody then held. Python 3.9 won that race often enough to stay green. **Rule R-TERMINAL-ROW**: the interrupt guard is installed before the ledger write, not before the child wait, and it stays deferred - recording the signal instead of raising - for as long as there is no child to kill, so a signal can never unwind a reservation or strand a claimed output; the recorded signal is acted on at the first point where the ABORTED row can still be written, and a second signal during teardown is recorded, never raised. **Rule R-DETERMINISTIC-RACE**: a regression for a race delivers the signal at a fixed point (`tests/test_v070_review2.py`, `InterruptDuringSetupRegressionTests`), it does not poll for the window and hope; a test that passes by timing is evidence about the runner, not about the harness.

    **Independent review of that fix — one path was still open.** The pending SIGTERM recorded while `Popen` had not returned was acted on by an explicit `raise _Interrupted()` after `guard.arm()`, so the guard was still armed when the abort handler called `_terminate`: a SIGINT delivered during teardown raised out of the handler, leaving the ledger at 1/0/0 with the output claim still held - the exact outcome R-TERMINAL-ROW forbids. The lesson is that the rule has to be a property of every abort entry path, not of one of them. `defer()` and `raise_pending()` are now the only ways in: the trap, the pending-signal raise and the `KeyboardInterrupt` catch all re-enter deferred mode before any cleanup runs, so teardown is unconditionally raise-free. A guarantee stated once in a comment and implemented in one branch is not a guarantee; the deterministic repeat-signal probe (`test_a_second_signal_during_teardown_cannot_lose_the_terminal_row`) is what makes it one.
