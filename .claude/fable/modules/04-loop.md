# FABLE Module 04 — Loop: Increment Discipline & Deep Debugging

> Load when: a debugging session passes two failed fixes, a task will span many turns
> or risk compaction, tests are flaky, or you notice you are editing without a written
> hypothesis.

## 1. Increment discipline

One increment = one logical concern, small enough to verify immediately:
compiles/lints + relevant tests pass + you can state what changed and why in one line.

- Order work so the system stays green: types/interfaces → core logic → callers → tests
  interleaved (or tests first where the project practices TDD — see `tdd` workflow).
- No drive-by changes inside an increment. Spot something worth fixing? Log it in the
  plan file under `LATER:` and offer it after the task.
- If an increment balloons (touching a 5th file for a "small" change), stop — the tier
  was wrong. Re-frame, re-plan, possibly split the task.

## 2. Debugging — the full protocol

### 2.1 Reproduce

- Run the failing thing yourself before any edit. Capture the exact command + output.
- No local repro? Reproduce the *conditions* (same input shape, same env vars, same
  versions). Still nothing → say it's unreproduced and what access/data would change that.
- Flaky: run 5–10×, record the failure rate. A 3/10 failure that becomes 0/10 after your
  fix is only ~meaningful if you understand *why* (see anti-pattern: sleep-to-fix).

### 2.2 Read the output — all of it

- Full stack trace, not the last line. The first frame in *your* code matters most.
- Warnings printed *before* the error are frequently the actual cause.
- Exit codes, stderr vs stdout, logs one level up (the supervisor often knows more).

### 2.3 Localize

- **Layer bisect:** feed known-good input into each stage; find the first stage whose
  output is wrong. Input → parse → transform → store → render.
- **Time bisect:** `git log --oneline -20` on the touched area; if it worked before,
  `git bisect` (or diff-read) between the last good and first bad commit.
- **Input minimize:** shrink the failing case until removing anything makes it pass.
  The minimal case usually names the bug.
- **Print the actual data.** Not the data you believe flows through — the real value,
  at the boundary in question. Wrong-shape data explains a plurality of "impossible" bugs.

### 2.4 Hypothesis ledger

Keep it in the plan file when debugging goes past one round:

```text
H1: TTL compared in ms vs s → predicts: expiry ~1000x off → EXP: log both at compare → REFUTED (both ms)
H2: cache key missing tenant id → predicts: cross-tenant hits → EXP: log key on hit → CONFIRMED
```

Every edit during debugging must serve a written hypothesis. An edit with no hypothesis
is a guess — guesses corrupt the crime scene and produce accidental "fixes" nobody
understands.

### 2.5 Two-Strike widening moves

Two failed fixes from one hypothesis ⇒ the hypothesis (or its layer) is wrong. Widen:

| Suspect | Quick check |
| --- | --- |
| Stale build/cache | clean build, clear cache dirs, restart the watcher |
| Wrong env/version | print runtime versions *from inside the process*; compare lockfile |
| Test itself wrong | read the test's assertion against the actual spec/intent |
| Data not what you think | dump the real input at the boundary |
| Concurrency/ordering | run serially / with `-race` / repeat 20× |
| Config divergence | diff effective config (the loaded values, not the files) |
| The repro is mistaken | re-derive the repro from the original report; ask: was it ever failing for the reason claimed? |

### 2.6 Exit conditions

- Fixed: failing case passes, you can articulate the root cause, a regression test exists.
- Not fixed after widening: step back to Branch (different approach to the whole change),
  or deliver the hypothesis ledger as the honest result — what was ruled out, what remains,
  what experiment would discriminate. That is a legitimate, useful deliverable.

## 3. Long-horizon survival

- Milestone = update the plan file (`STATE:` / `NEXT:` / `OPEN:`) — 30 seconds that make
  the task compaction-proof.
- After compaction: re-read plan file → `git status` + `git diff --stat` → reconcile with
  `NEXT:` → only then act. Never trust post-compaction memory of file contents; re-grep.
- Drift check every ~10 substantive actions: am I inside the framed scope? has the tier
  changed? is the todo list still true?
- Delegation: hand mechanical sweeps (rename sites, find usages, run-matrix) to subagents
  with a precise contract and required evidence format; spot-check before relying on it.
