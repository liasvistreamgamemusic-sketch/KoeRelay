# Irodori-TTS-Lite を RX 9070 XT (ROCm) で動かした記録

> 記録日: 2026-07-01
> 目的: 別セッションのClaudeが読んで、同じ調査をゼロからやり直さずに再現・継続できるようにする。
> 結論: **動く。ただし3つの障害を順に踏んで、それぞれ対処が必要だった。**

---

## 0. 前提

- 検証環境: `~/github/Irodori-TTS-Server`(AIchan本番)のROCmセットアップ済み`.venv`(torch 2.6.0+rocm6.4.2, pytorch-triton-rocm 3.2.0+rocm6.4.2, GPU: AMD Radeon RX 9070 XT)。詳細は memory の `irodori-tts-rocm-setup` を参照。
- 目標: [kizuna-intelligence/Irodori-TTS-Lite](https://github.com/kizuna-intelligence/Irodori-TTS-Lite)(Int4量子化ランタイム)を、既存のIrodori-TTS-Server用ROCm環境の上で動かす。
- 最終的な検証は本番を汚さないため **`~/github/Irodori-TTS-Server`を`cp -a`で丸ごとコピーした `~/github/KoeRelay/Irodori-TTS-Server`** で行った。本番環境には一切変更なし。

---

## 1. 障害①: ROCm自体は無関係。まずTriton単体で疑いを晴らす

Irodori-TTS-LiteのREADMEは「CUDA対応GPU(compute capability 8.0以上、Tritonカーネルは Ampere系チューニング)」としか書いておらず、AMD/ROCmの動作報告が無かった。最初にTriton単体の動作確認をした。

```python
# triton_smoke.py (inspect.getsourcelines がソースファイルを要求するため、-c ではなく実ファイルで実行すること)
import torch, triton, triton.language as tl

@triton.jit
def add_kernel(x_ptr, y_ptr, out_ptr, n, BLOCK: tl.constexpr):
    pid = tl.program_id(0)
    offs = pid * BLOCK + tl.arange(0, BLOCK)
    mask = offs < n
    x = tl.load(x_ptr + offs, mask=mask)
    y = tl.load(y_ptr + offs, mask=mask)
    tl.store(out_ptr + offs, x + y, mask=mask)

n = 4096
x = torch.randn(n, device="cuda"); y = torch.randn(n, device="cuda")
out = torch.empty_like(x)
add_kernel[(triton.cdiv(n, 1024),)](x, y, out, n, BLOCK=1024)
torch.cuda.synchronize()
print("max_err:", (out - (x + y)).abs().max().item())
```

`.venv/bin/python triton_smoke.py` → **`max_err: 0.0`(PASS)**。この時点のtritonは既存の `pytorch-triton-rocm==3.2.0+rocm6.4.2`。**結論: ROCm/Tritonの組み合わせ自体は問題ない。**

---

## 2. 障害②: `pip install`するとvenvが壊れる(triton名前空間の衝突)

```bash
cd ~/github/Irodori-TTS-Server
uv pip install --python .venv/bin/python "git+https://github.com/kizuna-intelligence/Irodori-TTS-Lite.git"
```

これを普通に実行すると、依存解決で以下が起きる:

- `irodori-tts-lite` は `onecomp-runtime`(`kizuna-intelligence/onecompression-runtime`)に依存している。**READMEには「OneCompressionを実行時依存に持たない」と書いてあるが、実際の`pyproject.toml`には`onecomp-runtime`が必須依存として書かれている(README側が古い/誤り)。**
- `onecomp-runtime`の`pyproject.toml`は`triton>=3.0`を要求。これは**汎用PyPI版triton**として解決され、**3.7.1**がダウンロードされる(188MB)。
- 結果、venv内に `pytorch-triton-rocm`(3.2.0)と `triton`(3.7.1)が**両方**インストールされる。両者は別パッケージ名だが、どちらも同じ `triton/` importディレクトリにファイルを書き込むため、後からインストールされた3.7.1が`import triton`時に優先される。

この状態で先の`triton_smoke.py`を再実行すると:

```
RuntimeError: cannot get address for 'hipDrvLaunchKernelEx' from libamdhip64.so
```

3.7.1は`triton.backends.amd`というAMD向けバックエンドを実際に持っている(README通りではなくAMD対応は入っている)が、**このマシンのROCm HIPランタイム(`libamdhip64.so`)に`hipDrvLaunchKernelEx`という関数が無く**、シンボル解決に失敗する。ROCmのバージョン不一致が原因(torchがバンドルしているROCm6.4.2周辺と、汎用triton 3.7.1が期待するHIP APIのバージョンがズレている)。

### やってはいけない対処

「じゃあ汎用tritonを消せばいい」と`uv pip uninstall triton`すると、**`pytorch-triton-rocm`まで壊れる**:

```
AttributeError: module 'triton' has no attribute 'jit'
```

`ls .venv/lib/python3.12/site-packages/triton/` を見ると `__init__.py` が消えている。2つのパッケージが同じ`triton/`ディレクトリのファイルを共有していたため、後発パッケージのアンインストールが先発パッケージのファイルまで削除してしまった。

復旧するには元のローカルwheelから明示的に再インストールする(通常の`uv pip install <wheel>`は`pyproject.toml`の`[tool.uv.sources]`解決と衝突して `No solution found` になったので `--isolated`(新: `--no-config`)が必要だった):

```bash
uv pip install --python .venv/bin/python --isolated --reinstall --no-deps \
  "/home/tomoya/pytorch-for-rocm/pytorch_triton_rocm-3.2.0+rocm6.4.2.git7e948ebf-cp312-cp312-linux_x86_64.whl"
```

### 正しい対処

最初から `--no-deps` で、triton自体を引き込まないようにインストールする:

```bash
uv pip install --python .venv/bin/python --no-deps --no-config \
  "onecomp-runtime @ git+https://github.com/kizuna-intelligence/onecompression-runtime@main" \
  "irodori-tts-lite @ git+https://github.com/kizuna-intelligence/Irodori-TTS-Lite.git" \
  pyopenjtalk
```

`onecomp-runtime`の制約は`triton>=3.0`という緩いバージョン指定なので、既存の`pytorch-triton-rocm==3.2.0`で**数値上は満たされる**(ただしパッケージ名が違うためuvの依存解決には乗らない=`--no-deps`で明示的に回避する必要がある)。これで`import triton`は`3.2.0+rocm6.4.2`のまま維持される。

---

## 3. 障害③: 合成実行時のエラー(2段階)

`irodori_tts.inference_runtime.InferenceRuntime.from_key()` を呼ぶテストスクリプトを書いて実行(スクリプト全文は§5)。

### 3-1. `model_precision="fp16"` は受け付けられない

```
ValueError: Unsupported precision='fp16'. Expected one of: fp32, bf16.
```

READMEの`force_fp16=True`という設定は「量子化されたレイヤをeager-dequantする際の実dtype」を制御するもので、`RuntimeKey.model_precision`(こちらはupstream `irodori_tts`側の通常の精度指定)とは別物。**`model_precision`は`"fp32"`か`"bf16"`のままでよく、`irodori_tts_lite.configure(force_fp16=True)`が別途、量子化レイヤの実行dtypeをfp16に強制する。** ここを`"fp32"`に直して再実行。

### 3-2. 本命: チェックポイントのメタデータと`ModelConfig`のフィールド不一致

```
[irodori_tts_lite] detected packed AutoBit checkpoint with 235 quantized Linears
[irodori_tts_lite] detected 1 extra-quant embedding tables
TypeError: ModelConfig.__init__() got an unexpected keyword argument 'duration_predictor_uncertainty'
```

**最初に疑った仮説(バージョンが古いから)は間違いだった。** 確認したところ:

```bash
# ロック済みのコミット
grep -A2 'name = "irodori-tts"' uv.lock
# source = { git = "https://github.com/Aratako/Irodori-TTS.git#eaf74d6a19138f743acb5b71a445fd25a57db987" }

# upstreamの最新コミット
git ls-remote https://github.com/Aratako/Irodori-TTS.git HEAD
# eaf74d6a19138f743acb5b71a445fd25a57db987   ← 完全に同じコミット
```

**既にupstreamの最新コミットをロックしていた。**アップグレードでは直らない。実際にチェックポイントのメタデータを見ると:

```python
from safetensors import safe_open
import json
with safe_open(checkpoint_path, framework="pt", device="cpu") as f:
    cfg = json.loads((f.metadata() or {}).get("config_json", "{}"))
    print(list(cfg.keys()))
# ... 'duration_predictor_uncertainty', 'duration_uncertainty_min_log_scale',
#     'duration_uncertainty_max_log_scale', ... ← この3つが現行upstreamのModelConfigに無い
```

つまり **Kizuna Intelligenceが量子化チェックポイントを作った時点のupstream(または派生ブランチ)には`duration_predictor_uncertainty`系の3フィールドがあったが、現在のupstream mainにはもう(あるいはまだ)存在しない**、という上流側同士のズレ。バージョンを上げ下げしても解決しない。

### 対処: ローダー側で未知キーを無視する(直接パッチ)

`.venv/lib/python3.12/site-packages/irodori_tts_lite/checkpoint_loader.py` を編集:

```python
# ファイル冒頭のimportに追加
import dataclasses

# _patched_from_key() 内、元は:
#   model_cfg = _DiTModelConfig(**model_cfg_dict)
# を以下に変更:
_known_fields = {f.name for f in dataclasses.fields(_DiTModelConfig)}
_dropped = {k: v for k, v in model_cfg_dict.items() if k not in _known_fields}
if _dropped:
    print(f"[irodori_tts_lite] ignoring unknown ModelConfig keys: {_dropped}")
model_cfg_dict = {k: v for k, v in model_cfg_dict.items() if k in _known_fields}
model_cfg = _DiTModelConfig(**model_cfg_dict)
```

⚠️ **これは`.venv`内のインストール済みファイルへの直接編集**。`irodori-tts-lite`を再インストール/アップグレードすると消える。恒久化するならフォークしてこの差分をコミットするか、アプリ側から`_DiTModelConfig`相当を外側でモンキーパッチする形に直す必要がある(未対応、TODO)。

---

## 4. 成功時の実測ログ(そのまま)

```
[test] checkpoint = /home/tomoya/.cache/huggingface/hub/models--kizuna-intelligence--Irodori-TTS-500M-v3-int4/snapshots/.../model.safetensors
[irodori_tts_lite] detected packed AutoBit checkpoint with 235 quantized Linears
[irodori_tts_lite] detected 1 extra-quant embedding tables
[irodori_tts_lite] ignoring unknown ModelConfig keys: {'duration_predictor_uncertainty': False, 'duration_uncertainty_min_log_scale': -7.0, 'duration_uncertainty_max_log_scale': 5.0}
[irodori_tts_lite] fused=235 eager_dequant=0 fallback=0
[irodori_tts_lite] embed_quant: packed 1 embedding tables
[irodori_tts_lite] warmup done in 44106 ms (8 unique (K,N,has_bias) signatures)
[codec] dacvae: hf://Aratako/Semantic-DACVAE-Japanese-32dim -> .../weights.pth
[test] runtime loaded in 57.90s
[test] peak VRAM after load: 1039.7 MB
[test] run 0: synthesize in 10.329s, peak VRAM 2516.4 MB   ← 初回は追加JITが乗る
[test] run 1: synthesize in 2.279s, peak VRAM 2518.8 MB
[test] run 2: synthesize in 1.892s, peak VRAM 2517.7 MB
[test] result type: <class 'irodori_tts.inference_runtime.SamplingResult'>
[test] sample_rate: 48000
[test] audio shape: torch.Size([1, 247680]), dtype: torch.float32   ← 5.16秒
[test] wrote lite_out.wav — RESULT: PASS
```

**RTF ≈ 0.4(実時間の約2.2倍速)、モデル単体VRAM ~1GB、DACVAEコーデック込みでpeak ~2.5GB。** 出力を数値チェック(NaN/Inf無し、RMS 0.145、peak_abs 0.89=クリッピング無し)。**聴感の声質はまだ確認していない**(サンプル: `~/github/KoeRelay/samples/lite_sumire_test.wav`)。

---

## 5. 再現用テストスクリプト全文

`ref_wav`のパスは検証先のvoicesディレクトリに合わせて書き換えること。

```python
import time
import torch

import irodori_tts_lite
irodori_tts_lite.configure(use_fused=True, force_fp16=True)
irodori_tts_lite.patch()

from irodori_tts.inference_runtime import InferenceRuntime, RuntimeKey, SamplingRequest

checkpoint = irodori_tts_lite.resolve_checkpoint(
    "hf://kizuna-intelligence/Irodori-TTS-500M-v3-int4/model.safetensors"
)

runtime = InferenceRuntime.from_key(RuntimeKey(
    checkpoint=checkpoint,
    model_device="cuda",
    codec_repo="Aratako/Semantic-DACVAE-Japanese-32dim",
    model_precision="fp32",   # "fp16"は不可。force_fp16が別途effective dtypeを制御する
    codec_device="cuda",
    codec_precision="fp32",
))

req = SamplingRequest(
    text="こんにちは、テスト中です。声の感じ、ちゃんと出てるかな。",
    ref_wav="/path/to/voices/sumire.wav",
    seconds=None,
)
result = runtime.synthesize(req)

import soundfile as sf
audio = result.audio.detach().float().cpu().numpy()
sf.write("/tmp/lite_out.wav", audio.squeeze(), result.sample_rate)
```

実行時は必ずROCmの高速化環境変数を付ける(付けないと`TORCH_BLAS_PREFER_HIPBLASLT`のデフォルトが遅い):

```bash
TORCH_BLAS_PREFER_HIPBLASLT=0 MIOPEN_FIND_MODE=FAST .venv/bin/python this_script.py
```

---

## 6. 今どこに何があるか

| もの | 場所 |
|---|---|
| 検証用の隔離コピー(パッチ適用済み) | `~/github/KoeRelay/Irodori-TTS-Server`(`.venv`に上記パッチが直接当たっている) |
| 出力サンプル | `~/github/KoeRelay/samples/lite_sumire_test.wav` |
| AIchan本番のTTSサーバー | `~/github/Irodori-TTS-Server` — **無傷。今回の作業は一切反映していない。** |
| このドキュメント | `~/github/KoeRelay/docs/irodori-tts-lite-investigation.md` |
| KoeRelayの設計書(サマリのみ反映済み) | `~/github/KoeRelay/PLAN.md` §3/§4.2/§5/§8/§9 |

## 7. 未解決/次にやること

1. ~~パッチの恒久化~~ — **完了(2026-07-01)**。`src/irodori_openai_tts/runtime.py` に
   `_enable_lite()` を追加し、`get()` で `configure(use_fused=True, force_fp16=True)` →
   `patch()` を呼んでから int4 チェックポイント
   (`hf://kizuna-intelligence/Irodori-TTS-500M-v3-int4/model.safetensors`)を読むよう恒久化。
   既定ON、`IRODORI_DISABLE_LITE=true` でフルモデルに戻せる。Lite時は precision を fp32 に固定。
   また checkpoint_loader の未知キー除去は現行 `irodori_tts_lite` パッケージ本体に取り込み済み
   (§3-2 の `.venv` 手当ては不要になった)。
   ⚠️ このKoeRelayコピーの `.venv` は editable install が本番(`~/github/Irodori-TTS-Server/src`)を
   指していたため、`uv pip install --no-deps --no-config -e .` でKoeRelayコピー自身のsrcへ張り替え済み
   (本番venvは無傷)。
   → サーバ経由(`POST /v1/audio/speech`)でのLite合成をHTTPで実動作確認済み: HTTP200 / 48kHz wav /
   `fused=235` / load 15.8s。
2. 出力音声の声質評価 — **tomoya確認済み「いい感じだった」**。
3. 非Lite(Sway Samplingのみ)構成の実測が無い。比較用に取っておくと良い(任意)。
4. マイク入力(STT)からの連携 — **KoeRelay 本体で実装済み**(hotkey/VAD → STT → この Lite サーバ → 仮想マイク)。
