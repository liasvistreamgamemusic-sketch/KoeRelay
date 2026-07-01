# KoeRelay — リアルタイム声変換リレー

マイクに向かって話す → STTで文字起こし → その文字をTTSで**別の声**として喋らせる →
**仮想マイクとして他アプリ(Discord/配信ソフト/ゲーム)に流す**アプリです。
会話やLLMは介さない、素の「声変換リレー」。詳しい設計は [PLAN.md](PLAN.md)。

```
実マイク ─► STT(faster-whisper, CPU) ─► TTS(Irodori-TTS-Server) ─► VB-CABLE ─► Discord等
```

## 使い方(基本)

2つのトリガー方式があり、トレイメニューの「モード」でいつでも切り替えられます。

- **長押し(PTT, 既定)**: ショートカットキー(既定 `F8`)を**押している間だけ録音**。
  離すと文字起こし → 別の声で合成 → 仮想マイクへ再生。
- **常時(VAD)**: キー操作なしで**常にマイクを聞き**、発話の切れ目(無音)で自動的に
  区切って合成・再生。TTS再生中は取り込まないのでエコーになりません。

いずれも Discord / OBS / ゲーム側のマイクに **「CABLE Output」** を選ぶと、その声が届きます。

トレイアイコンの色で状態がわかります:

| 色 | 状態 |
|---|---|
| 灰 | 準備中(モデル/サーバ読み込み中) |
| 緑 | **利用可能・待機中**(話せます) |
| 赤 | 録音中(キー長押し中) |
| 橙 | 文字起こし中 |
| 青 | 発話中(仮想マイクへ再生中) |

準備が整うと「KoeRelay 利用可能」の通知が出ます。

### 設定画面

トレイメニューの **「設定…」** から、入力マイク / 出力(仮想マイク)/ モニター出力先 /
音量 / 声 / 話速 / トリガー方式(PTT・VAD)/ ホットキー / STTバックエンド / 自動更新を
GUIで変更できます。デバイスは一覧から選べます。音量・出力先・モニター・声・話速・モード・
ホットキーは**即時反映**(STTバックエンドのみ再起動後)。設定は `config.yaml` に保存されます。

## 前提: 仮想オーディオデバイス(VB-CABLE)

他アプリへ声を流すには [VB-CABLE](https://vb-audio.com/Cable/)(無料)を **1回だけ**
インストールしてください。導入すると `CABLE Input`(仮想スピーカー)/ `CABLE Output`
(仮想マイク)が追加されます。KoeRelay は合成音声を `CABLE Input` へ再生し、
受け側アプリは `CABLE Output` をマイクとして選びます。未導入時はトレイで案内します。

## 前提: TTS サーバ

別声合成には [Irodori-TTS-Server](Irodori-TTS-Server/)(OpenAI TTS API 互換、既定
`http://127.0.0.1:8088`)が必要です。

- **自動起動/自動停止**: `config.yaml` の `tts.autostart_server: true` と `tts.server_cmd`
  を設定すると、KoeRelay 起動時にサーバを立ち上げ、**終了時に自動停止**します
  (自分で起動したときのみ停止。既存の常駐サーバは使い回し・停止しません)。
  WSL上のサーバを起動する例は `config.yaml.example` を参照。
- 手動起動でも構いません。接続できない場合はトレイで警告します。

## STT を AMD GPU で動かす(任意, remote バックエンド)

既定の faster-whisper は CTranslate2 依存で **AMD(ROCm)GPU 非対応**(NVIDIA CUDA か CPU)。
AMD GPU で文字起こししたい場合は、WSL 上に STT サーバ([stt_server/](stt_server/))を立て、
`config.yaml` で `stt.backend: remote` にします。サーバは transformers の Whisper を
PyTorch(ROCm)で動かし、OpenAI 互換の `POST /v1/audio/transcriptions` を提供します。

- 既存の Irodori-TTS-Server の `.venv`(torch-rocm/transformers 入り)を再利用できます:
  `KOERELAY_STT_VENV=~/github/KoeRelay/Irodori-TTS-Server/.venv ./stt_server/start.sh`
- KoeRelay 側で `stt.autostart_server: true` にすると、起動時に自動でこのサーバを立て、
  終了時に停止します(設定例は `config.yaml.example`)。
- 実測(RX 9070 XT / whisper-small): 5.2秒の音声を **0.9秒**で文字起こし。サーバは起動時に
  モデルを preload するので初回から待ちなし。

## 起動〜終了の自動化(まとめ)

`config.yaml`(例を同梱)で TTS/STT ともに `autostart_server: true` にすると:

1. **起動時**: KoeRelay が TTS サーバ・STT サーバ(WSL)を自動起動。
2. **準備**: 両サーバがモデルを preload + KoeRelay が TTS ウォームアップ。準備完了で
   トレイが「利用可能」を通知(=1回目から待ちが出にくい)。
3. **終了時**: KoeRelay が自動起動したサーバを停止(pkill)。
   ※既に自分で起動していた常駐サーバは停止しません(勝手に殺さない設計)。

## 動作確認・トラブルシュート

- **テスト発話**: トレイメニュー「テスト発話(動作確認)」で固定文を合成・再生します。
  合成できるか/どのデバイスから鳴るかをすぐ確認できます。
- **声が聞こえない**: 出力は既定で仮想マイク(`CABLE Input`)へ流れるため、自分の
  スピーカーからは鳴りません。**「モニター出力(スピーカー)」をON**にすると実スピーカーへも
  同時再生して確認できます。
- **初回の待ち**: 起動時に STT/TTS を裏でウォームアップするので、「利用可能」通知の後は
  1回目から待たされにくくなっています。
- 詳しいログは `%LOCALAPPDATA%\KoeRelay\koerelay.log`(録音の長さ・音量RMS・文字起こし
  結果・再生先デバイスを記録)。

## 起動方法

### 開発実行(uv)

```bash
uv run --extra full python -m koerelay.main
```

Windows では `run.bat` をダブルクリックでも起動できます(uv が必要)。

### 配布(.exe)

タグ(`v0.1.0` 等)を push すると GitHub Actions が Windows 用 `.exe` をビルドして
[Releases](../../releases) に添付します。zip を展開して `KoeRelay.exe` を実行してください。

## 自動アップデート

`.exe` 起動時、**モデルや TTS サーバを読み込む前に** GitHub Releases を確認します。
新しい版があれば(既定 `update.auto_install: true`)自動でダウンロード → 入れ替え →
**自動再起動**します。無駄なモデルロードをせずに最新版へ上がります。手動確認は
トレイメニューの「アップデートを確認…」から。

## 設定

`config.yaml.example` を `config.yaml` にコピーして編集します(全項目任意)。
主な項目: STT モデル/デバイス、TTS の声・サーバURL、出力デバイス名、ホットキー、更新設定。

## 依存の入れ方(手動)

```bash
uv sync --extra full          # まとめて
# もしくは機能別: --extra stt / --extra tts
```

各サブシステムは依存やサービスが無くても graceful に無効化され、トレイは起動します。
