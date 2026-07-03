# 修正しやすい UI の作り方 — トークン駆動アーキテクチャ

ui-craft の納品物は「ユーザーが自分で (または軽い指示で) 安全に微調整できる」ことが要件。
そのための構造規則。

## 原則: 変更の 9 割はトークン 1 行で済むようにする

納品後に来る修正リクエストの大半は決まっている:

| よくあるリクエスト | 触る場所 (これ以外を触らせない) |
| --- | --- |
| 「色をもう少し○○に」 | `--color-accent` など color トークン |
| 「もっと詰めて / 余白ほしい」 | `--space-*` (セクション余白は `--space-8`〜`12`) |
| 「角丸をもっと / やめて」 | `--radius-*` |
| 「アニメーション速く / 控えめに」 | `--duration-*` / モーションレベルのクラス |
| 「フォント変えたい」 | `--font-display` / `--font-body` |
| 「ダークモードにしたい」 | トークンの再定義ブロック追加のみ |

逆に言うと、**個別のコンポーネント CSS に生の hex・px 余白・ms を書いた時点でこの表は崩れる**。
実装中に `#`, `px` の余白, `ms` を直書きしそうになったら、それはトークンにすべき値。

## ファイル構成

プレーン CSS / CSS Modules の場合:

```
styles/
  tokens.css        ← 全トークン定義。ユーザーが触るのは原則ここだけ
  base.css          ← reset + タイポグラフィ基礎 (トークン参照のみ)
  components/*.css  ← コンポーネント別 (トークン参照のみ)
```

Tailwind の場合: `@theme` (v4) / `tailwind.config` の `theme.extend` (v3) にトークンを集約し、
任意値 (`mt-[13px]`, `text-[#8b5cf6]`) を使わない。任意値はトークン化の失敗シグナル。

React 系はコンポーネントを「見た目 (トークン参照)」と「データ・ロジック (props)」に分け、
文言・数値・画像 URL はすべて props またはデータ定数ファイル (`content.ts` 等) に出す —
「文言直して」がマークアップを触らず済む。

## ダークモード / テーマ切り替えを見越したトークン設計

色トークンは**役割名**で命名する (`--color-accent`, `--color-surface`)。
`--blue-500` のような値名にすると、テーマ切り替えで名前と実体が乖離する。

```css
:root { --color-bg: #fafaf9; --color-text: #1c1917; /* ... */ }

/* ダーク対応はこのブロックを足すだけで完了する状態を保つ */
@media (prefers-color-scheme: dark) {
  :root { --color-bg: #131110; --color-text: #f5f4f2; /* ... */ }
}
```

初回納品でダークモード不要でも、この構造 (役割名トークン) は必ず守る。

## モーションレベルの一括制御

Phase 1 で合意した「モーション量」を後から変えられるように、動きは data 属性 1 つで畳めるようにする:

```css
html[data-motion="minimal"] .reveal { transition: opacity var(--duration-base) ease; transform: none; }
@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after { animation-duration: 0.01ms !important; transition-duration: 0.01ms !important; }
}
```

## 微調整ガイド (報告テンプレ)

納品報告には、上の「よくあるリクエスト」表を**そのプロジェクトの実ファイルパス・実トークン名**で
具体化して載せる。汎用表のコピペではなく、「`src/styles/tokens.css:12` の `--color-accent: #0d6b5c`」
のように 1 行変更で試せる粒度で書く。

## やってはいけない

- コンポーネント間で微妙に違う値の複製 (`gap: 14px` と `gap: 16px` が意図なく混在) —
  同じ意図の値は同じトークン
- `!important` での上書き合戦 — 詳細度は低くフラットに保つ (BEM か Tailwind か、どちらかに寄せる)
- インラインスタイルへの生値埋め込み (動的値が必要なら CSS variable を inline で渡す:
  `style={{ '--delay': i * 80 + 'ms' }}`)
- 1 ファイル 800 行超の CSS — セクション/コンポーネント単位で割る
