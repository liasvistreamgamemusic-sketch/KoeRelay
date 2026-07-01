"""音声→テキスト。faster-whisper を既定、無ければ graceful に無効。

PLAN.md §4.1 / §4.4: 既定は device="cpu", compute_type="int8"(TTS[ROCm]との
GPU競合を避けるため)。GPU で動かす場合は gpu_lock.GPU_LOCK で TTS と排他する。
"""
from __future__ import annotations

import logging

import numpy as np

from ..gpu_lock import GPU_LOCK
from ..settings import STTConfig

log = logging.getLogger(__name__)


class Recognizer:
    def __init__(self, cfg: STTConfig) -> None:
        self.cfg = cfg
        self._model = None
        self._on_gpu = False
        if not cfg.enabled:
            return
        try:
            from faster_whisper import WhisperModel
        except Exception as e:
            log.warning("faster-whisper 未導入(%s)→ STT無効", e)
            return

        device = (cfg.device or "auto").lower()
        compute = cfg.compute_type
        if device == "auto":
            device, compute = "cuda", "float16"  # まず GPU を試す

        # GPU優先で初期化。失敗したら CPU/int8 へ自動フォールバック(STTを止めない)。
        # 注意: faster-whisper(CTranslate2)の GPU は NVIDIA CUDA のみ対応。
        # AMD(ROCm)GPU では初期化に失敗し CPU にフォールバックする。
        attempts = [(device, compute)]
        if device != "cpu":
            attempts.append(("cpu", "int8"))
        for dev, comp in attempts:
            if dev == "cpu" and comp in ("float16", "float32"):
                comp = "int8"  # CPU で float16 は不可
            try:
                self._model = WhisperModel(cfg.model, device=dev, compute_type=comp)
                self._on_gpu = dev == "cuda"
                log.info("faster-whisper ready (model=%s, device=%s, compute=%s)",
                         cfg.model, dev, comp)
                break
            except Exception as e:
                log.warning("STT初期化失敗 (device=%s, compute=%s): %s", dev, comp, e)
        if self._model is None:
            log.warning("STT を初期化できませんでした → STT無効")

    def available(self) -> bool:
        return self._model is not None

    def warmup(self) -> None:
        """無音を1回流してモデルの初回実行コスト(JIT/初期化)を先に消化する。"""
        if self._model is None:
            return
        try:
            silence = np.zeros(16000, dtype="float32")  # 1秒の無音
            self._run(silence)
            log.info("STT ウォームアップ完了")
        except Exception as e:
            log.info("STT ウォームアップ skip: %s", e)

    def transcribe(self, audio: np.ndarray, samplerate: int) -> str:
        """float32 mono [-1,1] の音声を文字起こし。失敗/空なら ""。"""
        if self._model is None or audio.size == 0:
            return ""
        try:
            if samplerate != 16000:
                audio = _resample(audio, samplerate, 16000)
            # GPU実行時のみ TTS(ROCm)と直列化。CPU実行時はロック不要(遅延を積まない)。
            if self._on_gpu:
                with GPU_LOCK:
                    return self._run(audio)
            return self._run(audio)
        except Exception as e:
            log.warning("文字起こし失敗: %s", e)
            return ""

    def _run(self, audio: np.ndarray) -> str:
        segments, _ = self._model.transcribe(
            audio, language=self.cfg.language, vad_filter=True
        )
        return "".join(s.text for s in segments).strip()


def _resample(audio: np.ndarray, src: int, dst: int) -> np.ndarray:
    if src == dst:
        return audio
    n = int(round(len(audio) * dst / src))
    if n <= 0:
        return audio
    x_old = np.linspace(0, 1, len(audio), endpoint=False)
    x_new = np.linspace(0, 1, n, endpoint=False)
    return np.interp(x_new, x_old, audio).astype(np.float32)
