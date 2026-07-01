# KoeRelay — リアルタイム声変換リレー

マイクに向かって話す → STTで文字起こし → その文字をTTSで**別の声**として喋らせる →
**仮想マイクとして他アプリ(Discord/配信ソフト/ゲーム)に流す**アプリです。
会話やLLMは介さない、素の「声変換リレー」。詳しい設計は [PLAN.md](PLAN.md)。

```
実マイク ─► STT(faster-whisper, CPU) ─► TTS(Irodori-TTS-Server) ─► VB-CABLE ─► Discord等
```

## 使い方(基本)

1. **ショートカットキー(既定 `F8`)を長押しする間だけ録音**します。
2. キーを離すと、話した内容を文字起こし → 別の声で合成 → 仮想マイクへ再生します。
3. Discord / OBS / ゲーム側のマイクに **「CABLE Output」** を選ぶと、その声が届きます。

トレイアイコンの色で状態がわかります:

| 色 | 状態 |
|---|---|
| 灰 | 準備中(モデル/サーバ読み込み中) |
| 緑 | **利用可能・待機中**(話せます) |
| 赤 | 録音中(キー長押し中) |
| 橙 | 文字起こし中 |
| 青 | 発話中(仮想マイクへ再生中) |

準備が整うと「KoeRelay 利用可能」の通知が出ます。

## 前提: 仮想オーディオデバイス(VB-CABLE)

他アプリへ声を流すには [VB-CABLE](https://vb-audio.com/Cable/)(無料)を **1回だけ**
インストールしてください。導入すると `CABLE Input`(仮想スピーカー)/ `CABLE Output`
(仮想マイク)が追加されます。KoeRelay は合成音声を `CABLE Input` へ再生し、
受け側アプリは `CABLE Output` をマイクとして選びます。未導入時はトレイで案内します。

## 前提: TTS サーバ

別声合成には [Irodori-TTS-Server](Irodori-TTS-Server/)(OpenAI TTS API 互換、既定
`http://127.0.0.1:8088`)が必要です。手動起動するか、`config.yaml` の
`tts.autostart_server` / `tts.server_cmd` で自動起動できます。

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
