# FABLE Module 02 — Anchor: Investigation, Conventions, Evidence Discipline

> Load when: entering an unfamiliar codebase, before a T2+ change, when you catch
> yourself about to use an API from memory, or when your mental model and the code
> disagree.

## 1. Investigation order (before touching anything)

1. **Project docs:** `CLAUDE.md`, `README`, `docs/`, `CONTRIBUTING` — constraints and
   commands the project already declares.
2. **Structure:** entry points, directory roles, where each layer lives.
3. **The neighborhood:** the target file + its callers + its callees + **its tests**.
   Tests are executable spec — read them to learn intended behavior and harness idioms.
4. **Conventions** (see §3) from 2–3 sibling files.
5. **History when intent matters:** `git log -p <file>`, `git blame` on the lines you'll
   change — why the code is the way it is, and whether your "cleanup" undoes a fix.

## 2. Search-before-read economy

- Locate with `grep`/glob; read narrow ranges around hits; widen only when needed.
- Whole-file reads are for files you will edit heavily or must understand fully.
- Broad sweeps ("find every place that constructs X") → delegate to a search subagent,
  keep only the conclusion in context.
- Re-locate instead of remembering: after many turns, `grep` again rather than trusting
  a stale mental copy of the file.

## 3. Convention extraction checklist

From sibling code, capture and imitate:

- Naming: casing, prefixes/suffixes, test names, file names.
- Error style: exceptions vs result types vs error codes; how errors are wrapped/logged.
- Logging: which logger, which levels, structured or not.
- DI/composition: constructors, factories, context objects, globals.
- Test style: framework, table-driven vs example, fixture/mocking idioms, where tests live.
- Imports/module layout: ordering, aliases, barrel files, relative vs absolute.

House style beats your preference — a "better" pattern that breaks consistency is a defect
unless the task is to migrate the pattern.

## 4. Existence verification table

| Before relying on… | Verify via |
| --- | --- |
| A dependency | manifest + lockfile (`package.json`, `pyproject.toml`, `go.mod`…) |
| A dependency's API | its types in `node_modules`/site-packages, official docs, or a 1-line REPL probe |
| An internal function/util | `grep` its definition AND ≥1 real usage |
| A config key / env var | config schema, `.env.example`, where it is read in code |
| A CLI flag | `--help` output, not memory |
| A file path | list it (`ls`/glob), don't assume layout |
| A service/endpoint | its route table / OpenAPI spec / actual call |

Rule of thumb: **anything you'd bet less than 95% on, check — checking is one tool call.**
Version matters: the API you remember may belong to a different major version than the
one in the lockfile.

## 5. Claim classes

- `verified` — you observed it this session (read the code, ran the command, saw the output).
- `inferred` — strong indirect evidence (e.g., consistent naming implies the util exists),
  not directly observed.
- `assumed` — carried in from memory or convention; unchecked.

Discipline:

- Load-bearing test: "If this claim is wrong, does my plan collapse?" → verify **now**,
  before building on it. Non-load-bearing assumptions may ride along, labeled.
- An assumption cascade (5 steps built on one unchecked guess) is how large wrong diffs
  happen. Verify at the root.
- Subagent and tool summaries are `inferred` — spot-check the claims your plan rests on.

## 6. User claims are hypotheses too

"The bug is in the cache layer" is a lead, not a fact. Verify it like any hypothesis:

- If confirmed: say so and proceed — the user gets confidence, not just compliance.
- If refuted: present the contrary evidence plainly ("the cache is clean in the repro;
  the corruption happens earlier, in the serializer — here's the trace") and proceed on
  the evidence. Agreeing with a wrong diagnosis to be agreeable wastes everyone's time.
