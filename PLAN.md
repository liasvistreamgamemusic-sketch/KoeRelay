# KoeRelay(仮名) — リアルタイム声変換リレー 計画書

> バージョン: 0.1(ドラフト)
> 最終更新: 2026-07-01
> ステータス: 計画フェーズ(実装未着手)
> 前提知識: AIchan プロジェクト(`~/github/AIchan`)で得たSTT/TTS/GPU運用/リリースの知見を流用

マイクに向かって話す → STTで文字起こし → その文字をTTSで別の声として喋らせる → **仮想マイクとして他アプリ(Discord/配信ソフト/ゲーム)に流す**。会話やLLMは介さない、素の「声変換リレー」アプリ。名前は仮なので好きに変えてOK。

---

## 1. ゴールと非ゴール

### ゴール
- マイク入力 → STT(文字起こし) → TTS(別声で再合成) → 出力、をリアルタイムに近い遅延で回す。
- 合成音声を**仮想マイクとして他アプリに認識させる**(Discord等でAIchanと同じ声で話せる)。
- Windows で確実に動作し、`.exe` で配布できる(AIchanと同じPyInstaller + GitHub Actions方式)。
- 会話ログ・記憶・ペルソナ・LLMは持たない(スコープ外)。文字起こし結果はそのままTTSに渡すだけ。

### 非ゴール(v1では扱わない)
- LLMを介した応答生成・翻訳(将来 STT→LLM→TTS に拡張できる構造にはしておくが、v1は素通し)。
- AIchanのような常駐アバター/立ち絵UI(最小限の操作パネルで十分)。
- クラウドTTS/STTへの依存(ローカル完結を維持)。

---

## 2. 全体アーキテクチャ

```
                 ┌─────────────────────────────────────────┐
  実マイク  ───► │ STT (faster-whisper, CPU推奨)             │
                 │  - webrtcvad で発話区間を検出              │
                 │  - 区間終了ごとに文字起こし                 │
                 └───────────────┬───────────────────────────┘
                                  │ text
                                  ▼
                 ┌─────────────────────────────────────────┐
                 │ TTS (Irodori-TTS-Server, ROCm, 既存流用)   │
                 │  - chunking + Lite(Int4,要パッチ)or       │
                 │    Sway Samplingのみ、で低遅延合成         │
                 └───────────────┬───────────────────────────┘
                                  │ wav/pcm
                                  ▼
                 ┌─────────────────────────────────────────┐
                 │ 出力ルーティング (sounddevice)              │
                 │  - モニタ用: 実スピーカー(任意)             │
                 │  - 仮想マイク用: VB-CABLE の "CABLE Input" │
                 └───────────────┬───────────────────────────┘
                                  │
                                  ▼
                 他アプリ(Discord/OBS/ゲーム)が
                 "CABLE Output" をマイクとして選択
```

AIchanとの違い: **LLM層が無い**ので `orchestrator.py` のような対話制御は不要。STT結果を直接TTSへ渡すだけの単純なパイプライン。その分、STT→TTSの往復レイテンシがそのまま体感遅延になるので、v1から低遅延設計を意識する。

---

## 3. 技術スタック(AIchanから流用/新規)

| 領域 | 採用 | 備考 |
|---|---|---|
| 言語 | Python 3.12(`uv run --python 3.12`) | AIchanと同じ。pyenvは`_ctypes`が無いので使わない。 |
| STT | `faster-whisper`(`small`, **CPU / int8 推奨**) | AIchanの`aichan/stt/`をそのまま移植可能。GPU実行も可能だが§4.4参照。 |
| VAD | `webrtcvad` + `sounddevice` | AIchanと同じ発話区間検出。 |
| TTS | **Irodori-TTS-Server**(`~/github/KoeRelay/Irodori-TTS-Server`、本番AIchanから隔離した複製) | OpenAI TTS API互換(`POST /v1/audio/speech`)。AIchanの`aichan/tts/irodori.py`をほぼそのまま流用可。 |
| TTS高速化 | **Irodori-TTS-Lite(Int4量子化)** — パッチ適用で動作確認済み(2026-07-01) | RTF≈0.4(5.16秒音声を1.9〜2.3秒で合成)、VRAM峰値約2.5GB(モデル単体は~1GB)。要パッチ(§4.2/§8参照)。フォールバックとしてSway Samplingのみの非Lite構成も選べる。 |
| 音声出力ルーティング | `sounddevice`(デバイス指定再生) + **VB-CABLE**(ユーザーが別途インストール) | §4.3参照。 |
| UI | PySide6、ただし**常駐トレイ+小さな操作パネル**(アバター無し) | 「話者切替」「マイク/出力デバイス選択」「有効/無効」「字幕オーバーレイ(将来)」程度。 |
| 設定 | `pydantic`風dataclass設定 + `config.yaml` | AIchanの`settings.py`パターンを流用。 |
| パッケージング | PyInstaller + GitHub Actions(タグpushで`.exe`リリース) | §7参照、AIchanの`.github/workflows/release.yml` / `packaging/aichan.spec`をほぼそのまま複製。 |

---

## 4. コンポーネント詳細

### 4.1 STT
- AIchanの `aichan/stt/mic.py` / `recognizer.py` を土台にする。PTTモードは不要(常時ONのVADモードのみで良い、声変換なので手動トリガーは不自然)。
- `faster-whisper` の `small` モデル、`device="cpu"`, `compute_type="int8"` を既定にする(理由は§4.4)。
- 発話区間検出→区間終了→文字起こし、の待ち時間がそのまま遅延に乗るので、`vad_aggressiveness` や無音判定の閾値はAIchanより**遅延優先**でチューニングする(多少誤爆してもいいので区切りを早める)。

### 4.2 TTS
- `aichan/tts/irodori.py` の `IrodoriTTS.synth()` をそのまま移植。
- Irodori-TTS-Serverの `chunking_enabled=true` / `chunk_min_chars=80` を活用し、長い文でも先頭チャンクから喋り始められるようにする(相手の発話が終わる前に返し始めない工夫は不要=会話ではないので、単純に「区切れたら即合成→即再生」で良い)。
- 声(`voice`)はAIchanと共通の`voices/`ディレクトリ(`sumire.wav`等)を再利用できる。別キャラ声にしたい場合は参照音声を追加するだけ。

**Irodori-TTS-Lite(Int4)を使う場合の手順**(2026-07-01に`~/github/KoeRelay/Irodori-TTS-Server`で動作確認済み):
1. `uv pip install --no-deps` で `onecomp-runtime` / `irodori-tts-lite` / `pyopenjtalk` を入れる(`--no-deps`必須。付けないと依存の汎用triton(PyPI版)が既存のROCm版`pytorch-triton-rocm`を壊す)。
2. `.venv/lib/python3.12/site-packages/irodori_tts_lite/checkpoint_loader.py` の `_patched_from_key` 内、`_DiTModelConfig(**model_cfg_dict)` の直前で、`dataclasses.fields(_DiTModelConfig)` に無いキー(`duration_predictor_uncertainty`等)を弾くようフィルタする(公開済み量子化チェックポイントのメタデータに、現行upstream `irodori_tts` の`ModelConfig`が知らないフィールドが3つ入っているため)。
3. `irodori_tts_lite.configure(use_fused=True, force_fp16=True); irodori_tts_lite.patch()` を呼んでから `InferenceRuntime.from_key(...)` を使う。`model_precision`は`"fp32"`か`"bf16"`のまま(`"fp16"`は不可、`force_fp16`が別途effective dtypeを制御する)。
4. チェックポイントは `hf://kizuna-intelligence/Irodori-TTS-500M-v3-int4/model.safetensors` を指定。

⚠️ **手順2のパッチは`.venv`内のインストール済みファイルを直接編集したもの**なので、パッケージ再インストール/アップグレードで消える。恒久化するなら Irodori-TTS-Lite をフォークしてパッチをコミットする、または KoeRelay側のコードから外側でモンキーパッチするどちらかを実装前に決める(§8参照)。

### 4.3 マイク出力(仮想マイク化) — できます
結論: **VB-CABLE(またはVoiceMeeter)などの仮想オーディオデバイスをユーザーに1回インストールしてもらえば可能**。Pythonアプリ側で仮想マイクを自作する必要はない。

仕組み:
1. ユーザーが [VB-CABLE](https://vb-audio.com/Cable/) をインストール(無料/ドネーションウェア)。これで `CABLE Input`(仮想スピーカー)と `CABLE Output`(仮想マイク)のペアがOS上に追加される。
2. 本アプリはTTSで合成した音声を、通常のスピーカーではなく **`sounddevice.play(data, sr, device=<CABLE InputのデバイスID>)`** で「CABLE Input」に向けて再生する。
3. Discord/OBS/ゲーム側の マイク設定 で「CABLE Output」を選択する。
4. これで合成音声がそのアプリには「マイクからの声」として届く。

実装メモ:
- `sounddevice.query_devices()` で出力デバイス一覧を取得し、設定UIで選ばせる(名前に"CABLE"を含むものを自動検出してデフォルト候補にすると親切)。
- モニタリング用に**実スピーカーへも同時出力**したい場合は、`sounddevice`で2デバイスに同時再生するか、VoiceMeeterで内部ルーティングして1本の再生から両方へ分岐させる方法もある(`harusdia.hatenablog.com`の記事が参考になる、Sources参照)。
- VB-CABLEのインストール自体は署名付きドライバのインストーラなので、**アプリからの自動インストールはしない**(ユーザーに手動導入してもらい、初回起動時に「見つかりません、ここからインストールしてください」と案内するだけにする)。

### 4.4 GPU競合対策(AIchanでの学び)
AIchanで実際に踏んだ地雷: LLM(Vulkan)とTTS(ROCm)が同時にGPUへアクセスしてクラッシュした(`aichan/gpu_lock.py`で共有ロックを入れて対策済み)。このアプリはLLMは無いが、**STT(faster-whisper)をGPUで動かすとTTS(ROCm)と同じ地雷を踏む可能性がある**。しかも声変換リレーは「前の発話をTTSが再生中に、次の発話をSTTが処理し始める」という同時実行が構造的に起きやすい(会話のAIchanより頻度が高い)。

対策は2択、**(a)を推奨**:
- **(a) STTはCPU固定にする**(`device="cpu"`, `int8`)。GPUを使うのはTTSだけにして、そもそも競合を起きなくする。`small`モデルなら現実的な速度が出るはず。
- (b) STTもGPUで動かしたい場合は、AIchanの`aichan/gpu_lock.py`と同じ共有ロックをSTT推論呼び出しにも掛ける。ただしこのアプリは同時実行の**頻度が高い**ため、ロック待ちがそのまま遅延に積まれやすい点に注意。

---

## 5. レイテンシ予算(要実測)

現時点では推測値。実装初期に必ず実測してこの表を更新する。

| 区間 | 見積り | 備考 |
|---|---:|---|
| VAD無音判定〜発話区間確定 | 未実測 | 閾値を攻めて短縮する余地あり |
| faster-whisper small(CPU, int8) | 未実測 | 発話長に依存 |
| Irodori-TTS-Lite 合成(Int4, num_steps=40既定) | **実測: 1.9〜2.3秒/5.16秒音声**(RTF≈0.4、ウォームアップ後) | 2026-07-01、`~/github/KoeRelay/Irodori-TTS-Server`で実測。初回のみ+8秒程度JIT分が乗る。num_steps/sway_coeffを詰めればさらに縮む余地あり |
| Irodori-TTS 合成(非Lite, Sway Samplingのみ) | 未実測 | Lite不採用時のフォールバック用に別途実測が必要 |
| 再生開始まで | 未実測 | chunking有効なら先頭チャンク分だけで良い |

「合計で何秒までなら実用的か」をまず決めて(配信/ゲーム用途なら1〜1.5秒程度が目安になりそう)、それを超えたらどこを削るかの優先順位を早めに決めておくと手戻りが少ない。

---

## 6. UI/UX方針
- 常駐トレイアイコン + 小さな操作パネル(AIchanのアバターウィンドウは不要)。
- パネルの内容: ON/OFFトグル、入力マイク選択、出力デバイス選択(実スピーカー/CABLE Input)、声(voice)選択、簡易な遅延インジケータ。
- 将来的に「今喋っている文字起こしをオーバーレイ字幕として出す」機能は配信用途で需要がありそうなので、Phase 2以降で検討(AIchanの字幕吹き出し実装 `aichan/ui/character_window.py` の`SpeechBubble`と、そこで踏んだQtレイアウトの罠がそのまま参考になる)。

---

## 7. パッケージング・リリース(AIchanと同方式)
1. `pyproject.toml` + `<pkg>/__init__.py` に `__version__` を持たせ、両方を同時に更新する運用(AIchanと同じ)。
2. `packaging/<name>.spec` — PyInstaller spec。`faster_whisper` / `ctranslate2` / `onnxruntime`(webrtcvadは純Pythonだが依存先確認) / `sounddevice` / `soundfile` を `collect_all()` で同梱(AIchanの`aichan.spec`をコピーして名前を変えるだけで大部分いける)。
3. `.github/workflows/release.yml` — `v*` タグpushで `windows-latest` 上でビルド→zip→`softprops/action-gh-release@v2` でRelease添付。AIchanのYAMLをそのまま複製可能。
4. 初回リリースの前に、実機(Windows)でPyInstallerビルドが一発で通るか確認する(ネイティブ依存が多いので`hiddenimports`調整が要る可能性が高い、AIchanでもその想定コメントが残っている)。

---

## 8. 既知のリスク・未解決事項
- **Irodori-TTS-Liteのパッチが恒久化されていない**。現状`~/github/KoeRelay/Irodori-TTS-Server`の`.venv`内ファイルを直接編集して動かしている(§4.2)だけなので、パッケージ再インストールで消える。実装に入る前に「フォークしてパッチをコミット」か「アプリ側で外側からモンキーパッチ」のどちらかを決めて恒久化する。
- Irodori-TTS-Liteの声質は**数値的な健全性(NaN無し等)しか確認していない**。聴感評価はtomoya自身の確認待ち(サンプル: `~/github/KoeRelay/samples/lite_sumire_test.wav`)。もし声質がFP32/bf16版より明確に劣化していたら、Lite不採用でSway Samplingのみの非Lite構成に戻す判断が必要。
- 上記2点が固まるまでは、TTSバックエンドを「Lite」に確定させず、非Lite(Sway Samplingのみ)へのフォールバック経路もコード上残しておく。
- VB-CABLE前提のマイク出力は、ユーザー環境に手動インストールが必要 = 配布物だけでは完結しない。README等で導入手順を明記する必要あり。
- レイテンシ予算が未実測。設計変更(chunk_min_charsを下げる、num_stepsを下げる等)の判断は実測後に。
- STTのCPU固定(§4.4)は安全策だが、遅延面で本当に十分か(特に低スペックCPU機)は要検証。

---

## 9. フェーズ計画

- **P0(このドキュメント)**: 計画のみ。
- **P1(MVP)**: マイク→STT(CPU)→TTS→VB-CABLE出力、の一本道パイプラインをCLIかごく簡易なUIで動かす。GPU競合対策は§4.4(a)のCPU固定で回避。TTSはLiteパッチの恒久化(§8)が済めばLite、済まなければ非Lite(Sway Samplingのみ)。
- **P2**: 設定UI(デバイス選択・声選択)、トレイ常駐化、レイテンシ実測とチューニング(non-Lite構成の実測含む、§5の空欄を埋める)。
- **P3(任意)**: 字幕オーバーレイ、複数声プリセット切替、自動アップデート(AIchanの`updater.py`を流用)。

---

## 参考(このセッションで確認済みの情報源)
- VB-CABLE等の仮想オーディオデバイスでPython音声をDiscord等のマイク入力として認識させる方法は2026年現在も標準的な手段([vip-jikkyo.net](https://vip-jikkyo.net/vb-cable-for-obs-discord), [harusdia.hatenablog.com](https://harusdia.hatenablog.com/entry/2025/06/17/190000))。
