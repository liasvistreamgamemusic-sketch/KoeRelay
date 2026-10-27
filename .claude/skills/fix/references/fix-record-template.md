# 記録ファイルのテンプレート — `<repo>/.fix/<slug>.md`

Phase 0 で作り、各 Phase で追記する。FABLE 01-frame §5 のコントラクト (TASK / TIER / AC / NON-GOALS /
DECISIONS / STATE / NEXT / OPEN) を内包し、compaction 後の再接地はこのファイルだけで行う。
`.git/info/exclude` に `.fix/` を追加してリポジトリを汚さない。

機械マーカー: `ROOT_CAUSE_SITE:` 行は Stop hook (`root-cause-first-check.sh`) が読む。
`<path>:<line>` の形で実在する箇所を書く — プレースホルダ (`<` を含む) のままでは未記入扱い。

T1 (原因既知・1 ファイル) は `SYMPTOM / ROOT_CAUSE_SITE / ROOT_CAUSE / 検証` だけでよい。

```markdown
# FIX: <slug>
TASK: <1 行>
TIER: T1 | T2 | T3
SYMPTOM: <観察された挙動。実出力・スタックトレースの要点をそのまま>
EXPECTED: <期待する挙動 (観察可能な形)>
AC:
- AC1: <失敗ケース> → <期待する結果>
- AC2: <周辺の既存テスト/suite が green のまま>
NON-GOALS: <直さないもの (別チケット・仕様変更・リファクタ)>
REPRO: `<コマンド>` → <実出力の要点>   | UNREPRODUCED (<試した条件と、再現に必要なもの>)
FLAKY: <n>/<m> 回失敗 (該当時のみ)

## 原因連鎖
症状        : <実出力>                                     [verified]
← 直接原因  : <file:line — 根拠>                            [verified]
← 中間原因  : <file:line — 根拠>                            [verified | inferred]
← 根本原因  : <不変条件 X が Y で破られる — file:line>        [verified]

## 仮説台帳
H1: <仮説> → predicts: <観察されるはずのこと> → EXP: <実験> → CONFIRMED | REFUTED (<観察>)
H2: …

## 根本原因
ROOT_CAUSE_SITE: <path>:<line>
ROOT_CAUSE: <不変条件 X が Y で破られる (1 行)>
WHY_NOT_CAUGHT: <テスト欠如 | 型が緩い | 境界未検証 | 不変条件が暗黙 | エラーパス無音 | 環境差> — <補足>
SIBLINGS: `<grep パターン>` → <file:line>, <file:line> | なし

## 修正案
A 応急処置 (症状箇所): <内容> — 可逆性 / 残る不正状態 / 必要なラベル・追跡
B 根本箇所 (ROOT_CAUSE_SITE): <内容> — 影響範囲 / 必要なテスト
C 構造的 (このクラスの不具合を排除): <内容> — コスト / 別タスク化の要否
DECISION: <B over A/C because …>

## 検証
regression test: <path>::<name> — 修正前 FAIL (<落ちた理由が期待通りか>) / 修正後 PASS
siblings: <file:line> → <テスト or 観察>
L1: <lint / 型 / build の結果>   L2: <近傍テスト>   L3: <suite>   L4: <実フローの観察 (コマンドと出力)>
再発防止: <回帰テストのみ | +型 | +バリデーション | …>  LATER: <1 増分に収まらなかったもの>

STATE: <どこまで終わったか>
NEXT: <次の 1 手>
OPEN: <未確認の前提・リスク・応急処置の追跡先>
```
