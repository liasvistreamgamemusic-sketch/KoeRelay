---
name: git-pr
description: >-
  GitHub の Pull Request を作成するスキル。ユーザーが「PR 作って」「プルリク出して」
  「pull request」等と言ったら、またはスラッシュコマンドで呼ばれたら必ず使用。
  タイトル/本文の自動生成・ターゲットブランチ・ドラフトか否かをボタン質問 1 回で
  確認してから gh CLI で作成する。remote が GitLab のリポジトリでは代わりに git-mr を使う。
---

# git-pr — ボタンで完結する Pull Request 作成

## 手順

### 0. ホスト判定

```bash
git remote get-url origin    # github.com を含まない (= GitLab 等) → git-mr スキルへ切り替え
gh auth status               # 未認証なら中断して報告 (認証はユーザー操作)
```

### 1. 状態把握と分析 (質問の前に必ず)

```bash
git status                                    # 未コミット変更があれば先に git-commit を提案
BASE=$(gh repo view --json defaultBranchRef -q .defaultBranchRef.name)
git log $BASE..HEAD --oneline                 # PR に入る全コミット (最新だけ見ない)
git diff $BASE...HEAD --stat                  # 変更全体
```

- 全コミットと diff から **タイトル案と本文案** (## Summary / ## Changes / ## Test plan) を作っておく
- 現在ブランチが main/master のままなら、先にブランチ作成が必要な旨を報告して git-branch へ

### 2. AskUserQuestion で 1 回だけ質問

| # | 質問 | 選択肢 (先頭=推奨) | 備考 |
| --- | --- | --- | --- |
| 1 | タイトル/本文 | 「この案で作成 (推奨)」(preview にタイトル+本文全文) / 「修正したい」 | 修正は「その他」に入力 |
| 2 | ターゲット | 「<デフォルトブランチ> (推奨)」 / 他の主要ブランチ | `gh repo view` で取得した実際の値を使う |
| 3 | 種類 | 「通常 (推奨)」 / 「ドラフト」 | 作業途中と分かる文脈ならドラフトを推奨側に |
| 4 | レビュアー | 「指定しない (推奨)」 / 「指定する」 | 指定は「その他」に GitHub ユーザー名 |

### 3. 実行

```bash
git push -u origin HEAD
gh pr create --base <target> --title "<type>: <タイトル>" --body "$(cat <<'EOF'
<確定した本文>
EOF
)"                            # ドラフトなら --draft、レビュアーは --reviewer <user>
```

- 関連 Issue が文脈にあれば本文に `Closes #<番号>` を入れる (マージ時に自動クローズ)

### 4. 報告

- 例: 「PR #12 を作成しました → <URL>(target: main・レビュー待ち)」
- `gh pr checks` で CI が走っていれば状態を 1 行添える。push や作成の失敗は隠さず先頭で
