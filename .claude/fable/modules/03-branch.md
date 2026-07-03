# FABLE Module 03 — Branch: Design Alternatives & Decisions

> Load when: a T2+ design choice is on the table, you're about to add a dependency,
> define a schema/API, or you notice you've been elaborating your first idea for a
> while without having considered a second one.

## 1. Branch triggers (any of these ⇒ generate alternatives)

- New architectural seam (service split, layer boundary, module API).
- Data model / schema / wire format / public API shape — one-way doors.
- Adding a dependency.
- Algorithm choice with real performance or memory implications.
- Security-relevant flow (authn/z, secrets, input handling).
- Anything whose reversal would cost more than an hour.

Skip branching for: choices with a house precedent (follow it), trivially reversible
internals, anything the project docs already decide.

## 2. Generating real alternatives (no strawmen)

Force diversity — three standard lenses:

- **The boring way:** what the average senior dev on this team would do; maximum
  consistency with the existing codebase; stdlib/framework built-ins.
- **The minimal way:** smallest diff that meets the acceptance criteria; fewest new
  concepts; possibly "don't build it — reuse/configure X".
- **The robust way** (only when the risk profile warrants): handles the failure modes
  and scale the task actually forecasts — not hypothetical ones.

Steelman each: one sentence on why a reasonable person would choose it. If you can't
steelman an option, it isn't an option — find a real one or admit there's only one path.

## 3. Choosing — evaluation order

1. **Correctness:** fully meets every acceptance criterion (a 90% option is not an option).
2. **Simplicity:** fewest new concepts for the next reader. Test: can you explain the
   design in two sentences? Does maintaining it require knowing a trick?
3. **Reversibility:** prefer two-way doors. Isolate unavoidable one-way doors behind a
   seam (adapter, interface, versioned format) so the blast radius is one file, not the
   codebase.
4. **Consistency:** matches how this codebase already solves similar problems.
5. **Performance:** only at measured or clearly forecast need — never speculative.

Tie-breaker: the option you'd rather debug at 2am.

## 4. Decision log

One line per decision, in the plan file or commit body:

```text
DECISION: pg advisory lock over redis lock because we already run pg and need no new infra
DECISION: denormalize count on write over count-on-read because read path is 100:1 hot
```

Cheap to write, and prevents the next session (or the next model) from re-litigating or
accidentally reversing a settled choice.

## 5. Dependency addition checklist

Adding a dependency is a decision, not a default. Before adding:

1. Stdlib or an existing dependency covers it? → use that.
2. Is the need ~30 lines of code? → write it (with tests) instead of importing 30k lines.
3. Health: maintained? typed? reasonable transitive tree? license compatible?
4. Supply-chain surface: does it run code at install time? how deep is its tree?
5. Wrap nontrivial third-party APIs behind a thin adapter — keeps the door two-way.

## 6. When to bring the choice to the user

- Genuine product/UX tradeoffs (visible behavior differs between options).
- Cost tradeoffs (infra, paid APIs) and security-posture tradeoffs.
- Both finalists are defensible and the reversal cost is high.

Present as: 2–3 options, one line of tradeoff each, your recommendation first with the
reason. Never present options you haven't actually evaluated.
