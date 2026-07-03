# Agent Delegation

The live agent list (with descriptions) is injected by the harness every
session — pick from it; don't rely on a memorized table.

Standing delegation policy:

- Complex feature/refactor request → **planner** agent before coding (T3: + **architect**)
- Nontrivial code just written/modified → **code-reviewer** agent
- New feature/bugfix with a test harness → **tdd-guide** agent
- Build failures → **build-error-resolver** agent
- Security-sensitive changes → **security-reviewer** agent before commit
- Broad searches/sweeps → search agents (Explore); keep only conclusions in main context

Run independent agents in parallel (one message, multiple tool calls).
A subagent's report is `inferred` until its load-bearing claims are
spot-checked (FABLE §7).
