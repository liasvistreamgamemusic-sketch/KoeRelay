"""Irodori-TTS-Server(OpenAI TTS API 互換)クライアント。

POST /v1/audio/speech に { model, voice, input, speed, response_format, irodori:{...} }
を投げて音声バイト列を得る(PLAN.md §4.2)。AIchan の irodori.py を移植。
"""
from __future__ import annotations

import logging

from ..gpu_lock import GPU_LOCK
from ..settings import TTSConfig

log = logging.getLogger(__name__)


class IrodoriTTS:
    def __init__(self, cfg: TTSConfig) -> None:
        self.cfg = cfg

    def health(self) -> bool:
        try:
            import requests
            base = self.cfg.base_url.rsplit("/v1", 1)[0]
            r = requests.get(base + "/health", timeout=2)
            return r.ok
        except Exception:
            return False

    def synth(self, text: str, *, speed: float | None = None) -> bytes | None:
        """テキスト → 音声バイト列(response_format 形式)。失敗時 None。"""
        if not text:
            return None
        try:
            import requests
        except ImportError:
            log.warning("requests 未インストール → TTS無効")
            return None

        irodori: dict = {}
        if self.cfg.cfg_scale_text is not None:
            irodori["cfg_scale_text"] = self.cfg.cfg_scale_text
        if self.cfg.cfg_scale_speaker is not None:
            irodori["cfg_scale_speaker"] = self.cfg.cfg_scale_speaker

        payload = {
            "model": self.cfg.model,
            "voice": self.cfg.voice,
            "input": text,
            "speed": speed if speed is not None else self.cfg.speed,
            "response_format": self.cfg.response_format,
        }
        if irodori:
            payload["irodori"] = irodori

        try:
            with GPU_LOCK:  # GPU実行のSTTと同時にGPUを叩かないよう直列化(§4.4)
                r = requests.post(
                    self.cfg.base_url.rstrip("/") + "/audio/speech",
                    json=payload,
                    headers={"Authorization": f"Bearer {self.cfg.api_key}"},
                    timeout=self.cfg.request_timeout,
                )
            if not r.ok:
                log.warning("TTS合成失敗 HTTP %s: %s", r.status_code, r.text[:200])
                return None
            return r.content
        except Exception as e:
            log.warning("TTS接続失敗: %s", e)
            return None
