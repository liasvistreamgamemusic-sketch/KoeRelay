"""STT(音声→テキスト)サブシステム。"""
from __future__ import annotations

import logging

from ..settings import STTConfig

log = logging.getLogger(__name__)


def build_recognizer(cfg: STTConfig):
    """設定の backend に応じてローカル/リモートの認識器を返す(共通インターフェース)。"""
    if cfg.backend == "remote":
        from .remote import RemoteRecognizer
        log.info("STT backend = remote (%s)", cfg.remote_url)
        return RemoteRecognizer(cfg)
    from .recognizer import Recognizer
    log.info("STT backend = faster-whisper (local)")
    return Recognizer(cfg)
