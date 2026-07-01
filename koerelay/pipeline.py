"""声変換リレーの中核: 録音 → STT → TTS → 仮想マイク出力。

ホットキー長押し中は録音、離すと MicRecorder が音声を渡してくる → 文字起こし →
TTSManager.speak() で合成・再生。状態(待機/録音中/文字起こし中/発話中)を
on_state コールバックで UI(トレイ)へ通知する。
"""
from __future__ import annotations

import logging
import threading
from enum import Enum
from typing import Callable

import numpy as np

from .settings import AppConfig
from .stt.mic import MicRecorder
from .stt.recognizer import Recognizer
from .tts.manager import TTSManager

log = logging.getLogger(__name__)


class State(str, Enum):
    IDLE = "待機中"
    RECORDING = "録音中"
    TRANSCRIBING = "文字起こし中"
    SPEAKING = "発話中"


OnState = Callable[[State], None]
OnText = Callable[[str], None]


class RelayPipeline:
    def __init__(self, cfg: AppConfig, recognizer: Recognizer, tts: TTSManager) -> None:
        self.cfg = cfg
        self.rec = recognizer
        self.tts = tts
        self.mic = MicRecorder(cfg.stt, cfg.audio, on_audio=self._on_audio)
        self.on_state: OnState | None = None
        self.on_text: OnText | None = None
        self.enabled = True  # ON/OFF トグル(トレイから切替)
        # TTS の再生開始/終了で状態表示を切り替える
        self.tts.on_start = lambda: self._set_state(State.SPEAKING)
        self.tts.on_end = lambda: self._set_state(State.IDLE)

    def available(self) -> bool:
        return self.mic.available() and self.rec.available()

    # ---- ホットキー長押しハンドラ ------------------------------------
    def begin_recording(self) -> None:
        if not self.enabled or not self.available():
            return
        self.mic.start_recording()
        if self.mic.is_recording():
            self._set_state(State.RECORDING)

    def end_recording(self) -> None:
        # stop_recording() は録音があれば _on_audio を呼ぶ。無ければ IDLE に戻す。
        was = self.mic.is_recording()
        self.mic.stop_recording()
        if was and not self.mic.is_recording():
            # _on_audio が呼ばれていれば TRANSCRIBING に入る。短すぎた等なら IDLE へ。
            pass

    # ---- STT → TTS ----------------------------------------------------
    def _on_audio(self, audio: np.ndarray, samplerate: int) -> None:
        self._set_state(State.TRANSCRIBING)
        threading.Thread(
            target=self._process, args=(audio, samplerate), daemon=True
        ).start()

    def _process(self, audio: np.ndarray, samplerate: int) -> None:
        try:
            text = self.rec.transcribe(audio, samplerate)
            log.info("文字起こし: %r", text)
            if self.on_text:
                self.on_text(text)
            if text:
                self.tts.speak(text)  # 再生開始で SPEAKING、終了で IDLE(コールバック)
            else:
                self._set_state(State.IDLE)
        except Exception as e:
            log.warning("パイプライン処理エラー: %s", e)
            self._set_state(State.IDLE)

    def _set_state(self, state: State) -> None:
        if self.on_state:
            try:
                self.on_state(state)
            except Exception:
                pass

    def stop(self) -> None:
        self.mic.stop()
