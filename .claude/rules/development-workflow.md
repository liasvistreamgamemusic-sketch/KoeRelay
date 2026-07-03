# Development Workflow

> Tier-aware macro pipeline. Tiers (T0–T3) are defined in `fable-core.md`.
> FABLE governs the cognition inside each step; this file wires the process
> and agents around it. Scale ceremony to the tier — none of this applies to T0/T1.

1. **Research & Reuse** (T2+ when building a new component): search before
   writing — this repo's existing utils first (FABLE A-phase), then package
   registries (npm / PyPI / crates.io) and reference docs (Context7, GitHub
   code search) for nontrivial builds. Prefer adopting a proven implementation
   over net-new code.
2. **Plan** — T2: written plan per FABLE F-phase. T3: **planner** agent
   (+ **architect** for system design) and design docs before any coding.
3. **Implement with TDD** where a test harness exists (**tdd-guide** agent for
   new features and bugfixes): red → green → refactor. Target ~80% coverage on
   new code.
4. **Self-review** the full diff: FABLE §5 hostile self-review, applying the
   `code-quality.md` checklist.
5. **Code review** — T2+: **code-reviewer** agent. Address CRITICAL/HIGH before
   commit; MEDIUM when reasonable.
6. **Commit / PR / MR** — message format per `git-workflow.md`; hosting flow per
   the **github-workflow** / **gitlab-workflow** skill.
