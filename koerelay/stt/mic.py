"""マイク録音(push-to-talk)。

ショートカットキー長押しの間だけ録音する方式。start_recording() で入力ストリームを
開き、stop_recording() で閉じて、録れた音声を on_audio(np.ndarray, samplerate) へ渡す。
文字起こし/合成は呼び出し側(pipeline)が別スレッドで行う。
sounddevice が無ければ no-op(available()=False)。
"""
from __future__ import annotations

import logging
import threading
from typing import Callable

import numpy as np

from ..settings import AudioConfig, STTConfig
from .device import resolve_input_device

log = logging.getLogger(__name__)

OnAudio = Callable[[np.ndarray, int], None]


class MicRecorder:
    def __init__(self, stt: STTConfig, audio: AudioConfig, on_audio: OnAudio) -> None:
        self.stt = stt
        self.audio = audio
        self.on_audio = on_audio
        self._sd = None
        self._stream = None
        self._frames: list[np.ndarray] = []
        self._recording = False
        self._lock = threading.Lock()
        try:
            import sounddevice as sd
            self._sd = sd
        except Exception:
            log.info("sounddevice 不在 → マイク入力無効")

    def available(self) -> bool:
        return self._sd is not None

    def is_recording(self) -> bool:
        return self._recording

    def start_recording(self) -> None:
        if not self.available() or self._recording:
            return
        with self._lock:
            self._frames = []
            self._recording = True
        try:
            device = resolve_input_device(self._sd, self.audio.input_device)
            self._stream = self._sd.InputStream(
                samplerate=self.stt.samplerate, channels=1, dtype="float32",
                device=device, callback=self._on_audio_block,
            )
            self._stream.start()
            log.info("録音開始 (device=%s)", device if device is not None else "既定")
        except Exception as e:
            log.warning("録音開始に失敗: %s", e)
            self._recording = False

    def stop_recording(self) -> None:
        if not self._recording:
            return
        with self._lock:
            self._recording = False
            frames = self._frames
            self._frames = []
        if self._stream:
            try:
                self._stream.stop()
                self._stream.close()
            except Exception:
                pass
            self._stream = None
        audio = np.concatenate(frames) if frames else np.array([], dtype="float32")
        dur = len(audio) / self.stt.samplerate if audio.size else 0.0
        if dur < self.stt.min_record_sec:
            log.info("録音 %.2f秒 は短すぎるため無視", dur)
            return
        log.info("録音停止 %.1f秒", dur)
        self.on_audio(audio, self.stt.samplerate)

    def _on_audio_block(self, indata, frames, time_info, status) -> None:  # noqa: ANN001
        if self._recording:
            self._frames.append(indata[:, 0].copy())

    def stop(self) -> None:
        self._recording = False
        if self._stream:
            try:
                self._stream.stop()
                self._stream.close()
            except Exception:
                pass
            self._stream = None
