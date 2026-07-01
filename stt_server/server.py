"""KoeRelay STT サーバ(WSL / PyTorch ROCm で GPU 推論)。

transformers の Whisper を AMD GPU(ROCm)で動かし、OpenAI 互換の
`POST /v1/audio/transcriptions`(multipart: file=wav)で文字起こしを返す。
faster-whisper(CTranslate2)は ROCm 非対応なので、こちらは torch ベースで GPU を使う。

起動:
    KOERELAY_STT_MODEL=openai/whisper-large-v3-turbo \\
    TORCH_BLAS_PREFER_HIPBLASLT=0 MIOPEN_FIND_MODE=FAST \\
    python -m uvicorn server:app --host 0.0.0.0 --port 8099
(通常は同ディレクトリの start.sh を使う)

依存: fastapi, uvicorn, python-multipart, transformers, torch(ROCm), soundfile, librosa, numpy
"""
from __future__ import annotations

import io
import logging
import os
import time

import numpy as np
import soundfile as sf
from fastapi import FastAPI, File, Form, UploadFile
from fastapi.responses import JSONResponse

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")
log = logging.getLogger("koerelay-stt")

MODEL_ID = os.environ.get("KOERELAY_STT_MODEL", "openai/whisper-large-v3-turbo")
DEFAULT_LANG = os.environ.get("KOERELAY_STT_LANGUAGE", "ja")
SR = 16000

app = FastAPI(title="KoeRelay STT")
_model = None
_proc = None
_device = "cpu"
_dtype = None


def _load():
    """Whisper(processor+model)を一度だけ構築(GPUがあればROCm/CUDAで)。

    transformers の pipeline は音声デコードに torchcodec(ffmpeg)を要求して
    WSLで libav が無いと失敗するため、processor+model を直接使う(numpy→torchのみ)。
    """
    global _model, _proc, _device, _dtype
    if _model is not None:
        return
    import torch
    from transformers import AutoModelForSpeechSeq2Seq, AutoProcessor

    use_gpu = torch.cuda.is_available()
    _device = "cuda" if use_gpu else "cpu"
    _dtype = torch.float16 if use_gpu else torch.float32
    log.info("loading %s on %s (%s)…", MODEL_ID, _device,
             torch.cuda.get_device_name(0) if use_gpu else "CPU")
    t0 = time.perf_counter()
    _proc = AutoProcessor.from_pretrained(MODEL_ID)
    _model = AutoModelForSpeechSeq2Seq.from_pretrained(
        MODEL_ID, torch_dtype=_dtype
    ).to(_device)
    _model.eval()
    log.info("model loaded in %.1fs", time.perf_counter() - t0)


def _transcribe(audio: np.ndarray, language: str) -> str:
    import torch
    _load()
    # PTT/VAD の1発話は基本30秒以内。Whisper processor は30秒に整形する。
    inputs = _proc(audio, sampling_rate=SR, return_tensors="pt")
    feat = inputs.input_features.to(_device, _dtype)
    with torch.no_grad():
        gen = _model.generate(feat, language=language, task="transcribe")
    return _proc.batch_decode(gen, skip_special_tokens=True)[0].strip()


def _read_wav(data: bytes) -> np.ndarray:
    """アップロードされた音声を float32 mono @16kHz に整える。"""
    audio, sr = sf.read(io.BytesIO(data), dtype="float32")
    if audio.ndim > 1:
        audio = audio.mean(axis=1)
    if sr != SR:
        import librosa
        audio = librosa.resample(audio, orig_sr=sr, target_sr=SR)
    return np.ascontiguousarray(audio, dtype=np.float32)


@app.get("/health")
def health():
    return {"status": "ok", "model": MODEL_ID, "device": _device,
            "loaded": _model is not None}


@app.post("/v1/audio/transcriptions")
async def transcriptions(
    file: UploadFile = File(...),
    language: str = Form(default=DEFAULT_LANG),
    model: str = Form(default=MODEL_ID),  # OpenAI 互換のため受けるが未使用
):
    try:
        raw = await file.read()
        audio = _read_wav(raw)
        if audio.size == 0:
            return {"text": ""}
        t0 = time.perf_counter()
        text = _transcribe(audio, language or DEFAULT_LANG)
        dur = len(audio) / SR
        log.info("transcribed %.1fs audio in %.2fs: %r", dur,
                 time.perf_counter() - t0, text[:60])
        return {"text": text}
    except Exception as e:
        log.warning("transcription failed: %s", e)
        return JSONResponse(status_code=500, content={"error": str(e)})


@app.on_event("startup")
def _startup():
    if os.environ.get("KOERELAY_STT_PRELOAD", "1").lower() in ("1", "true", "yes"):
        try:
            _load()  # 起動時にモデルを読み、初回リクエストの待ちを無くす
        except Exception as e:
            log.warning("preload failed (will load on first request): %s", e)
