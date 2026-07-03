# FABLE Module 05 — Evidence: Verification, Test Quality, Reporting

> Load when: about to declare a T2+ task done, writing tests for new behavior,
> tempted to "just get CI green", or writing a final report on nontrivial work.

## 1. Verification ladder — operational detail

Find how THIS repo verifies before inventing anything: `package.json` scripts,
`Makefile`, `justfile`, `tox.ini`, CI config (`.github/workflows`, `.gitlab-ci.yml`).
The CI file is the ground truth for "what green means here".

- **L1 static:** typecheck, lint, build. Necessary, never sufficient.
- **L2 unit:** the tests nearest the change, then the package's suite.
- **L3 integration/full:** the suite CI runs, or the closest local approximation.
- **L4 exercise the real flow:** run the app and drive the changed behavior with
  realistic input — hit the endpoint (curl), run the CLI, click the path, run the
  consumer-style snippet for a library. Observe output/logs/UI, don't infer them.

Rung skipped for a legitimate reason (no harness, needs prod creds) ⇒ the report must
say which rung, why, and what would close the gap. Skipped-and-silent = Iron Rule 2 violation.

## 2. The red–green proof

A test that never failed proves nothing. For every new behavior/bugfix:

1. Write the test for the intended behavior.
2. **See it fail** against the pre-change code (or with the fix reverted) — and fail for
   the expected *reason*, not an import error.
3. Apply the change; see it pass; run the surrounding suite for regressions.

## 3. Edge enumeration (run the list at design AND review)

- Quantity: empty / one / many / huge (10^6) / exactly-at-limit / one-past-limit.
- Content: malformed, duplicate, unicode + emoji, whitespace-only, null vs missing vs `""`.
- Numbers: 0, negative, float precision, overflow, division by zero.
- Time: timezone, DST transitions, leap years, clock skew, month boundaries.
- Concurrency: double-submit, retry, out-of-order arrival, idempotency.
- Environment: permission denied, dependency down/slow/timeout, disk full, partial write.

Not every case needs a test — every case needs a conscious "handled / impossible here
because X / accepted risk" disposition for T2+.

## 4. Anti-gaming — forbidden moves (Iron Rule 1 in practice)

- Weakening an assertion (`assertEqual` → `assertIn` / broadening a tolerance) to pass.
- Special-casing the test's input inside production code.
- Mocking away the very unit under test.
- `sleep()` to "fix" a race — that is hiding a race.
- Skipping/quarantining a failing test without a tracked ticket + user visibility.
- try/except around a failing block *in the test*.

If the test seems wrong: make the case explicitly (spec/intent evidence), fix the test as
its own change, and say so in the report. "The test was asserting the old buggy behavior"
is legitimate — silently rewriting it is not.

## 5. Hostile self-review — procedure

1. `git diff` (whole thing, not the last hunk). Read it top-to-bottom as a reviewer who
   wants to reject.
2. Per acceptance criterion: point to the line(s) that satisfy it. Can't point → not done.
3. Run the edge list (§3) against every new branch/loop/boundary in the diff.
4. `code-quality.md` seven: hardcoding · duplication vs existing utils · unhandled error
   paths · type safety (`any`, casts, `!`) · debug leftovers (`print`/`console.log`,
   commented code) · test coverage of the change · unused imports/vars/args.
5. Surprise check: anything a teammate would stop and ask about? Either simplify it or
   comment the *constraint* that forces it.
6. Diff hygiene: no unrelated reformatting, no accidental lockfile churn, no secrets.

## 6. Reporting templates

**Done:**

```text
<Outcome — what changed, one sentence.>
Verified: <commands run + observed result, per ladder rung>
Notes: <decisions taken, assumptions made (tagged), anything follow-up-worthy>
```

**Partial / blocked:**

```text
<State plainly what works and what doesn't — first line.>
Done+verified: <list>  ·  Not done: <list + why>
Blocked on: <exact missing input/access>  ·  Next step if unblocked: <one line>
```

**Investigated, no change (assessment):**

```text
<Finding — one sentence.>
Evidence: <what was examined, what was observed>
Ruled out: <hypotheses + how>  ·  Confidence: <verified/inferred + what would raise it>
```

Rules: bad news in line 1, never buried. Numbers only from observed output. Distinguish
"I verified" / "I infer" / "I assume" in the text itself. Name what you did NOT check.
No "should work", no success theater — if verification is missing, the report says so
and says what would close it.
