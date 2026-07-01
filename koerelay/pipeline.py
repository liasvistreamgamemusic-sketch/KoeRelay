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
        self.mic = MicRecorder(cfg.stt, cfg.audio, on_audio=self._on_audio,
                               gate=self._vad_gate)
        self.on_state: OnState | None = None
        self.on_text: OnText | None = None
        self.enabled = True  # ON/OFF トグル(トレイから切替)
        self.mode = cfg.stt.mode if cfg.stt.mode in ("ptt", "vad") else "ptt"
        self._speaking = False
        self._stt_lock = threading.Lock()  # 文字起こしの同時実行を防ぐ(VAD連続区間対策)
        # TTS の再生開始/終了で状態表示を切り替える
        self.tts.on_start = self._on_speak_start
        self.tts.on_end = self._on_speak_end

    def available(self) -> bool:
        return self.mic.available() and self.rec.available()

    # ---- モード切替(PTT / 常時VAD)----------------------------------
    def start(self) -> None:
        """現在のモードでリスニングを開始する。"""
        self.set_mode(self.mode)

    def set_mode(self, mode: str) -> None:
        """'ptt' か 'vad' に切替。VAD なら常時リスニングを開始/PTTなら停止。"""
        if mode not in ("ptt", "vad"):
            return
        self.mode = mode
        if mode == "vad":
            if self.enabled and self.available():
                self.mic.start_vad()
        else:
            self.mic.stop_vad()
        self._set_state(State.IDLE)

    def set_enabled(self, on: bool) -> None:
        """ON/OFF。VADモードなら常時リスニングの起動/停止も伴う。"""
        self.enabled = on
        if self.mode == "vad":
            if on and self.available():
                self.mic.start_vad()
            else:
                self.mic.stop_vad()

    def _vad_gate(self) -> bool:
        """VAD が音声を取り込んで良いか(発話中=TTS再生中は取り込まない)。"""
        return self.enabled and not self._speaking

    def _on_speak_start(self) -> None:
        self._speaking = True
        self._set_state(State.SPEAKING)

    def _on_speak_end(self) -> None:
        self._speaking = False
        self._set_state(State.IDLE)

    # ---- ホットキー長押しハンドラ(PTTモード)------------------------
    def begin_recording(self) -> None:
        if self.mode != "ptt" or not self.enabled or not self.available():
            return
        self.mic.start_recording()
        if self.mic.is_recording():
            self._set_state(State.RECORDING)

    def end_recording(self) -> None:
        if self.mode != "ptt":
            return
        # stop_recording() は録音があれば _on_audio を呼ぶ(TRANSCRIBING へ)。
        self.mic.stop_recording()

    # ---- STT → TTS ----------------------------------------------------
    def _on_audio(self, audio: np.ndarray, samplerate: int) -> None:
        self._set_state(State.TRANSCRIBING)
        threading.Thread(
            target=self._process, args=(audio, samplerate), daemon=True
        ).start()

    def _process(self, audio: np.ndarray, samplerate: int) -> None:
        try:
            # マイクが本当に音を拾えているか診断できるよう長さと音量(RMS)を記録。
            dur = len(audio) / samplerate if samplerate else 0.0
            rms = float(np.sqrt(np.mean(audio ** 2))) if audio.size else 0.0
            log.info("録音 %.1f秒 rms=%.4f を文字起こし中…", dur, rms)
            if rms < 0.001:
                log.warning("入力音量がほぼ0です。マイク(入力デバイス)を確認してください。")
            # VADモードでは区間が連続で届きうる。モデルへの同時呼び出しを避けて直列化。
            with self._stt_lock:
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
