# モーション設計 — 少なく、意味のある動きを、正しい物理で

原則: **モーションは意味 (空間の連続性・因果・状態変化) を伝えるためにある**。
装飾だけの動きは AI っぽさのシグナル。1 回の練られたロード演出 >> 散らばったマイクロアニメ。

## Duration スケール (トークン化して使う)

| 用途 | 値 |
| --- | --- |
| マイクロインタラクション (hover, press, toggle) | **150–250ms** (`--duration-fast: 150ms`) |
| 標準トランジション (モーダル, パネル, コンテンツ出現) | **200–350ms** (`--duration-base: 250ms`) |
| オーケストレーション全体 (ページロード, 複数要素) | **400–600ms** (`--duration-slow: 450ms`) |

- **退場は入場より速く** (入場 300ms なら退場 200ms)
- hover は即時 ON (0ms)、OFF を 150ms でイーズ
- インタラクションのフィードバックは 200ms 以内・80–150ms で見え始めること
- **1s を超えるアニメーションは書かない**

## Easing (トークン化して使う)

```css
:root {
  --ease-out: cubic-bezier(0.22, 1, 0.36, 1);      /* 入場・出現の既定 (ease-out-quint 系) */
  --ease-in-out: cubic-bezier(0.65, 0, 0.35, 1);   /* 画面内 A→B の移動 */
  --ease-snappy: cubic-bezier(0.16, 1, 0.3, 1);    /* 小さい UI 部品のキビキビした反応 */
}
```

- 入場 = ease-out、退場 = ease-in、画面内移動 = ease-in-out、`linear` はプログレスバーのみ
- **bounce / elastic (`cubic-bezier(0.34, 1.56, ...)` 等のオーバーシュート) を UI 部品に使わない**
  — 古臭く安っぽい。遊び心が要件のときだけ、主役 1 箇所に限定
- 本物のスプリングが欲しいとき (ドロワー、モーダル等の主役モーション) は CSS `linear()`:
  ポイントは **40 点以上**必要 (生成ツール: Linear() Easing Generator)。
  duration は自分で選ばずスプリングの静定時間から導く。フォールバック必須:

```css
:root { --spring: cubic-bezier(0.22, 1, 0.36, 1); }
@supports (animation-timing-function: linear(0, 1)) {
  :root { --spring: linear(0, 0.007, 0.028 2.1%, 0.112 4.6%, 0.529 12.2%, 0.789 17.3%, 0.919 20.8%, 1.006 24.7%, 1.049 29.2%, 1.054 32.5%, 1.02 41.2%, 1.001 48.4%, 0.996 58.5%, 1); }
}
```

React + Motion (Framer Motion) が使える場合はそちらの spring を使う
(基準値: `stiffness: 400, damping: 25`)。中断時に慣性が保たれるのは JS 物理のみ。

## 動かしてよいプロパティ

**transform と opacity だけ** (コンポジタ処理)。width / height / top / left / margin / padding は禁止。
高さの開閉は `grid-template-rows: 0fr → 1fr` で行う。

移動距離: マイクロ = **4–16px**、大きめの出現 = 20–40px。画面の端から飛んでこさせない。

## 定番レシピ

### ロード時オーケストレーション (最も費用対効果が高い)

```css
.reveal {
  opacity: 0; transform: translateY(8px);
  animation: reveal var(--duration-base) var(--ease-out) forwards;
  animation-delay: var(--delay, 0ms);
}
@keyframes reveal { to { opacity: 1; transform: none; } }
```

- stagger は **30–60ms 間隔** (0 / 40 / 80 / 120 / 160ms)。HTML 側で
  `style="--delay: 40ms"` を振る (JS 不要)
- 動かすのはファーストビューの主要素 4–6 個まで。全要素に付けない

### 状態フィードバック

- press: `transform: scale(0.98)` (レイアウトをずらさない)
- モーダル入場: `opacity 0 → 1` + `scale(0.96) → 1`
- ローディング: スケルトンの微細なシマー or パルス。スピナー乱用しない
- disabled は動かさない

### スクロール連動 (モーション量「リッチ」のときだけ)

- 出現: IntersectionObserver で `.reveal` 付与、または CSS `animation-timeline: view()`
- `animation-timeline: view()/scroll()` を使うときは **easing を linear に**
  (進行がジェスチャに紐づくため時間ベースのカーブは不自然)。非対応ブラウザへの
  フォールバック (そのまま表示) を必ず用意
- 視差・sticky シーケンスは 1 ページ 1 箇所の主役演出に限定

### ページ / 要素間遷移

View Transitions API が使える環境なら要素の連続性 (サムネ→詳細等) に使う。
ルールは同じ: 短く・ease-out・reduced-motion で無効化。

## Reduced motion (必須・例外なし)

```css
@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after {
    animation-duration: 0.01ms !important;
    animation-iteration-count: 1 !important;
    transition-duration: 0.01ms !important;
    scroll-behavior: auto !important;
  }
}
```

または移動を伴う動きだけを opacity フェードに置換する、より丁寧な実装でもよい。
