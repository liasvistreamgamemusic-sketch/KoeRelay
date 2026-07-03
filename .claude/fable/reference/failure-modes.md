# FABLE Reference — Failure-Mode Catalog

> Why each FABLE rule exists. Each entry: the failure as observed in real agent sessions
> (most common in mid-tier models under agentic load; top-tier models suppress these
> implicitly), its root cause, and the FABLE countermeasure. Load for calibration,
> retrospectives, or when designing new rules.

| # | Failure mode | Symptom | Root cause | Countermeasure |
| --- | --- | --- | --- | --- |
| 1 | **Phantom API** | Calls a method/flag/config key that doesn't exist (or belongs to another version) | Pattern-completion from training memory presented as fact | A: verify-before-rely; Iron 3 |
| 2 | **Unread neighborhood** | Reimplements an existing util; violates house conventions; edits break callers | Acting before reading; no convention extraction | A: never modify unread code; grep-before-write |
| 3 | **First-idea lock-in** | Elaborates the initial design ever deeper; sunk cost prevents switching | No forced alternative generation | B: ≥2 real options, boring option mandatory |
| 4 | **Happy-path implementation** | Works in the demo, breaks on empty/unicode/concurrent input | Edge cases never enumerated | E: edge list with explicit disposition (05 §3) |
| 5 | **Symptom patching** | Fix applied where the error *appears*, not where it originates; bug returns wearing a different hat | No localization step; theorizing before evidence | §3 Debugging: localize before theorize; Iron 5 |
| 6 | **Doom loop** | Same fix retried with cosmetic variations, 5+ times, context burning | No hypothesis accounting; retry reflex | Two-Strike Rule; hypothesis ledger |
| 7 | **Test weakening** | Assertion loosened / test skipped / input special-cased — CI green, behavior wrong | Optimizing the *signal* (green) instead of the *target* (correct) | Iron 1; forbidden-moves list (05 §4) |
| 8 | **Fabricated success** | "All tests pass" — tests were never run; invented numbers | Reporting the expected world instead of the observed one | Iron 2; evidence-first reporting |
| 9 | **Scope drift** | Drive-by refactors, bonus features, churned formatting in the diff | No non-goals; enthusiasm | F: non-goals; L: one concern per increment |
| 10 | **Scope miss** | Solves an adjacent, easier problem than the one asked | Task never restated as checkable criteria | F: acceptance criteria; E: item-by-item check |
| 11 | **Instruction decay** | Constraints from turn 3 violated at turn 40; post-compaction amnesia | Contract lived only in volatile context | §7: persisted contract + re-grounding ritual |
| 12 | **Overconfident inference** | "X is configured in Y" stated as fact; it was a guess | No epistemic bookkeeping | A: verified/inferred/assumed tags |
| 13 | **Sycophantic diagnosis** | User says "bug is in X"; agent "finds" it in X regardless of evidence | Agreement optimized over accuracy | A §6: user claims are hypotheses; Iron 10 |
| 14 | **Premature completion** | Stops at 80%, lists remaining work in a tone implying done | Turn-end pressure; no criteria check | E: unmet = reported unmet; harness turn-end check |
| 15 | **Context flooding** | Whole files cat'ed repeatedly; the thread of the task drowns | No search-before-read economy | A §2; delegate sweeps; narrow reads |
| 16 | **Verification theater** | Ran the linter, declared the feature works | Ladder confused: L1 treated as L4 | §4 ladder minimums per tier |
| 17 | **Error blindness** | The decisive warning was in the output, three lines above where reading stopped | Skimming; reading for confirmation, not information | §3.2: read the entire output |
| 18 | **Assumption cascade** | Five-step plan built on one unchecked guess at step 1; all five collapse | Load-bearing assumptions never triaged | A: verify load-bearing assumptions first |
| 19 | **Silent fallback** | `catch {}` / default-on-error hides the failure until it's a data-corruption ticket | Error path treated as noise | Iron 8 |
| 20 | **Command invention** | Runs `npm run test:all` because it "usually exists" | Repo's actual verify commands never discovered | §4: discover via scripts/Makefile/CI config |

## Design notes

- **The gap being closed:** on one-shot, well-specified problems, model capability
  dominates. On long agentic tasks, *discipline* dominates — most catastrophic session
  failures above are process failures, reachable by procedure. That is why external
  scaffolding can move a mid-tier model a class upward in practical reliability, while
  raw reasoning ceiling stays where it is.
- **Trigger-conditioned rules** ("when X happens, do Y") are followed far more reliably
  by mid-tier models than virtue statements ("be careful"). Every FABLE rule is written
  as a checkable action bound to a trigger.
- **Ceremony must scale** (tiering) or the framework itself becomes a failure mode:
  a contract ritual on a typo fix erodes trust in the whole system and wastes tokens.
- **Identity framing is load-bearing:** "this is how a top-tier model works, follow it
  mechanically" outperforms a bare rule list on instruction retention.
- Rules conflict occasionally; precedence: project docs > user rules > FABLE taste.
  When two FABLE rules collide, Iron Rules win over the loop, honesty wins over
  everything.
