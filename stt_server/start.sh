#!/usr/bin/env bash
# KoeRelay STT サーバ起動(RX 9070 XT / gfx1201 / ROCm 向け)。
# torch(ROCm)入りの Python 環境で実行すること。既存の Irodori-TTS-Server の .venv を
# 再利用するのが手軽(transformers/librosa/soundfile/torch-rocm が既に入っている)。
#   例: KOERELAY_STT_VENV=~/github/KoeRelay/Irodori-TTS-Server/.venv ./start.sh
cd "$(dirname "$0")"

export TORCH_BLAS_PREFER_HIPBLASLT=0   # RDNA4は rocBLAS の方が速い
export MIOPEN_FIND_MODE=FAST
export KOERELAY_STT_MODEL="${KOERELAY_STT_MODEL:-openai/whisper-large-v3-turbo}"
export KOERELAY_STT_PORT="${KOERELAY_STT_PORT:-8099}"

# 実行 Python の解決: KOERELAY_STT_VENV があればその python、無ければ既定の python
PY="python"
if [ -n "$KOERELAY_STT_VENV" ] && [ -x "$KOERELAY_STT_VENV/bin/python" ]; then
  PY="$KOERELAY_STT_VENV/bin/python"
fi

# fastapi / uvicorn / python-multipart が無ければ入れておく(torch等は既存venv前提)。
"$PY" - <<'PYCHK' || "$PY" -m pip install fastapi uvicorn python-multipart
import importlib.util as u, sys
sys.exit(0 if all(u.find_spec(m) for m in ("fastapi","uvicorn","multipart")) else 1)
PYCHK

exec "$PY" -m uvicorn server:app --host 0.0.0.0 --port "$KOERELAY_STT_PORT"
