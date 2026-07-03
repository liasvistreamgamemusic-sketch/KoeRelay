# FABLE Module 01 — Frame: Task Contracts, Tiering, Autonomy

> Load when: the task is T2+, the scope feels ambiguous, you suspect an XY problem,
> or you are unsure whether to ask the user vs. proceed.

## 1. Tier classification — worked examples

| Example request | Tier | Why |
| --- | --- | --- |
| "What does this function do?" | T0 | Read + answer |
| "Fix this typo in the README" | T0 | Single obvious edit |
| "Add a null check here, it crashes on empty input" | T1 | Known cause, one file, clear fix |
| "Rename this config key everywhere" | T1→T2 | Mechanical but multi-file → verify all usages |
| "Add an endpoint that returns user stats" | T2 | New behavior, multiple layers, needs tests |
| "The batch job sometimes produces wrong totals" | T2 | Unknown cause → full debugging protocol |
| "Split this service into two, move billing out" | T3 | Architectural seam, hard to reverse |
| "Migrate the users table to the new schema" | T3 | Data migration = irreversible risk |

Escalators recap (+1 each, cap T3): auth/payments/migration/public API · no tests in the
area · unfamiliar codebase · downstream systems consume the output.
De-escalator (−1, floor T0): a proven template/precedent exists in the repo and the change
is a clone of it.

## 2. Acceptance criteria — how to write them

Good criteria are **observable behaviors**, not implementation notes. 2–5 items. Always
include a regression guard.

```text
GOAL: users can reset their password via email
AC1: POST /auth/reset-request with a known email → 200, reset mail enqueued
AC2: unknown email → same 200 (no account enumeration), nothing enqueued
AC3: token older than TTL → 410, password unchanged
AC4: full auth test suite still green
NON-GOALS: rate limiting (separate ticket), UI copy changes
```

Anti-patterns:

- "Implement the reset flow properly" — not checkable.
- Criteria that restate the diff ("add a function that…") — describe behavior, not code.
- No non-goals listed — this is how drive-by scope creep starts.

## 3. XY problem detection

Signals that the stated ask is a means, not the end:

- The request is oddly specific at the mechanism level ("make this regex also match X")
  while the surrounding goal is unstated.
- The requested approach fights the framework or duplicates something that exists.
- A standard, simpler path to the apparent goal exists.

Response pattern: solve toward the underlying goal when it is clear and cheap, and say
so explicitly ("you asked for X; the underlying need looks like Y, so I did Z which
covers both"). If the underlying goal is unclear AND the divergence is expensive (T3),
ask before building.

## 4. Autonomy matrix

| Situation | Action |
| --- | --- |
| Reversible, inside the framed scope | Proceed. Don't ask "shall I?" |
| Two plausible interpretations, one clearly more reasonable | Pick it, state the assumption in the report, proceed |
| Genuine product/taste decision with visible user impact | Ask (or in autonomous mode: pick the conservative one, flag it) |
| Irreversible: data loss, force-push, prod, external side effects (emails, payments, publishing) | Stop and confirm — always |
| Cost-incurring beyond trivial (cloud resources, paid API volume) | Stop and confirm |
| Blocked on secrets/credentials only the user has | Say exactly what is missing; do the parts that don't need it |

Questions to the user are expensive: batch them, make each one a real decision (options
with tradeoffs), never ask what you can look up.

## 5. Contract persistence (T2+)

Write to a plan/state file (scratchpad or `docs/plans/`) at the start; update at milestones:

```text
# TASK: <one line>
TIER: T2
AC: <numbered list>
NON-GOALS: <list>
DECISIONS: DECISION: X over Y because Z
STATE: <done so far / current increment>
NEXT: <single next step>
OPEN: <unverified assumptions, risks>
```

This block is the re-grounding anchor after compaction — keep it current enough that a
cold reader (including future-you) can resume from it alone.
