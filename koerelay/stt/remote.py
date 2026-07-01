"""リモートSTT: 音声を WSL 等の STT サーバへ送って文字起こしする。

faster-whisper(CTranslate2)は AMD ROCm 非対応なので、GPU で STT したい場合は
torch(ROCm)で動く STT サーバ(stt_server/)に音声を HTTP POST して結果を得る。
Recognizer と同じインターフェース(available/warmup/transcribe)を持つ。
"""
from __future__ import annotations

import io
import logging

import numpy as np

from ..settings import STTConfig

log = logging.getLogger(__name__)


class RemoteRecognizer:
    def __init__(self, cfg: STTConfig) -> None:
        self.cfg = cfg
        self._base = cfg.remote_url.rstrip("/")
        self._ok_libs = True
        try:
            import requests  # noqa: F401
            import soundfile  # noqa: F401
        except Exception as e:
            self._ok_libs = False
            log.warning("remote STT に必要な requests/soundfile が無い(%s)→ STT無効", e)

    def _health_url(self) -> str:
        return self._base.rsplit("/v1", 1)[0] + "/health"

    def available(self) -> bool:
        if not self._ok_libs:
            return False
        try:
            import requests
            r = requests.get(self._health_url(), timeout=3)
            return r.ok
        except Exception:
            # 起動直後などで未応答でも「使う設定」なら有効扱い(実送信時に再試行)。
            return True

    def warmup(self) -> None:
        # サーバ側が preload するので、ここでは疎通確認のみ(失敗しても無害)。
        try:
            import requests
            requests.get(self._health_url(), timeout=3)
        except Exception:
            pass

    def transcribe(self, audio: np.ndarray, samplerate: int) -> str:
        if not self._ok_libs or audio.size == 0:
            return ""
        try:
            import requests
            import soundfile as sf

            buf = io.BytesIO()
            sf.write(buf, audio, samplerate, format="WAV", subtype="PCM_16")
            buf.seek(0)
            files = {"file": ("audio.wav", buf, "audio/wav")}
            data = {"language": self.cfg.language, "model": self.cfg.model}
            r = requests.post(
                self._base + "/audio/transcriptions",
                files=files, data=data, timeout=60,
            )
            if not r.ok:
                log.warning("remote STT 失敗 HTTP %s: %s", r.status_code, r.text[:200])
                return ""
            return (r.json().get("text") or "").strip()
        except Exception as e:
            log.warning("remote STT 接続失敗: %s", e)
            return ""
