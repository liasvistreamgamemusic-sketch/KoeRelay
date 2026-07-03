# Git Workflow

## Commit Message Format

```text
<type>: <description>

<optional body — why, not what>
```

Types: feat, fix, refactor, docs, test, chore, perf, ci

Attribution is disabled globally — no Co-Authored-By / "Generated with" footers.

## Hosting flows

- GitHub リポジトリ (PR, `gh`) → **github-workflow** スキルを使う
- GitLab リポジトリ (MR, `glab` / push options) → **gitlab-workflow** スキルを使う

Destructive git operations (force-push, history rewrite, deleting branches with
unmerged work) always require explicit user confirmation.
