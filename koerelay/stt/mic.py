"""マイク録音(push-to-talk / 常時VAD の2モード)。

- PTT: start_recording()/stop_recording() で囲んだ区間を録音。
- VAD: start_vad() で常時リスニング。webrtcvad(無ければ音量しきい値)で無音区切りし、
  発話区間ごとに音声を渡す。
どちらも録れた音声を on_audio(np.ndarray, samplerate) へ渡す。文字起こし/合成は
呼び出し側(pipeline)が別スレッドで行う。sounddevice が無ければ no-op。
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
Gate = Callable[[], bool]  # True を返す間だけ VAD で音声を取り込む(エコー防止)


class MicRecorder:
    def __init__(self, stt: STTConfig, audio: AudioConfig, on_audio: OnAudio,
                 gate: Gate | None = None) -> None:
        self.stt = stt
        self.audio = audio
        self.on_audio = on_audio
        self.gate = gate           # None なら常に取り込む
        self._sd = None
        self._stream = None
        self._frames: list[np.ndarray] = []
        self._recording = False
        self._vad_running = False
        self._vad_thread: threading.Thread | None = None
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

    # ---- VAD(常時) --------------------------------------------------
    def start_vad(self) -> bool:
        """常時リスニングを開始。webrtcvad があれば発話区間で区切る。"""
        if not self.available() or self._vad_running:
            return False
        self._vad_running = True
        self._vad_thread = threading.Thread(target=self._vad_loop, daemon=True)
        self._vad_thread.start()
        return True

    def stop_vad(self) -> None:
        self._vad_running = False
        t = self._vad_thread
        if t and t.is_alive() and t is not threading.current_thread():
            t.join(timeout=1.0)
        self._vad_thread = None

    def _vad_loop(self) -> None:
        try:
            import webrtcvad
            vad = webrtcvad.Vad(self.stt.vad_aggressiveness)
        except Exception:
            vad = None
            log.info("webrtcvad 不在 → 音量しきい値で区切ります")
        sr = 16000  # webrtcvad は 8/16/32/48kHz のみ対応
        frame_ms = 30
        frame_len = int(sr * frame_ms / 1000)
        silence_limit = max(1, int(self.stt.vad_silence_ms / frame_ms))
        min_frames = int(self.stt.min_record_sec * 1000 / frame_ms)
        min_voiced_frames = max(1, int(self.stt.vad_min_speech_ms / frame_ms))
        buf: list[np.ndarray] = []
        silence = 0
        voiced = 0        # 実際に発話と判定されたフレーム数(幻聴対策)
        speaking = False
        try:
            device = resolve_input_device(self._sd, self.audio.input_device)
            with self._sd.InputStream(samplerate=sr, channels=1, dtype="float32",
                                      device=device) as stream:
                log.info("常時リスニング開始 (VAD, device=%s)",
                         device if device is not None else "既定")
                while self._vad_running:
                    block, _ = stream.read(frame_len)
                    mono = block[:, 0]
                    # 発話中(TTS再生中)は取り込まない(モニタ再生のエコー混入を防ぐ)
                    if self.stt.vad_ignore_while_speaking and self.gate and not self.gate():
                        buf, speaking, silence = [], False, 0
                        continue
                    if _is_speech(mono, vad, sr):
                        buf.append(mono.copy())
                        speaking = True
                        voiced += 1
                        silence = 0
                    elif speaking:
                        buf.append(mono.copy())
                        silence += 1
                        if silence >= silence_limit:
                            audio = np.concatenate(buf) if buf else None
                            v = voiced
                            buf, speaking, silence, voiced = [], False, 0, 0
                            self._maybe_emit(audio, sr, v, min_voiced_frames,
                                             min_frames * frame_len)
        except Exception as e:
            log.warning("VAD ループ終了: %s", e)
        finally:
            self._vad_running = False

    def _maybe_emit(self, audio, sr, voiced_frames, min_voiced_frames, min_len) -> None:  # noqa: ANN001
        """幻聴対策のゲート: 十分な発話量と音量がある区間だけ STT へ渡す。"""
        if audio is None or len(audio) < min_len:
            return
        if voiced_frames < min_voiced_frames:
            log.info("VAD: 発話量不足(voiced=%d < %d)→ 破棄(環境音とみなす)",
                     voiced_frames, min_voiced_frames)
            return
        rms = float(np.sqrt(np.mean(audio ** 2))) if audio.size else 0.0
        if rms < self.stt.vad_min_rms:
            log.info("VAD: 音量不足(rms=%.4f < %.4f)→ 破棄", rms, self.stt.vad_min_rms)
            return
        self.on_audio(audio, sr)

    def stop(self) -> None:
        self._recording = False
        self.stop_vad()
        if self._stream:
            try:
                self._stream.stop()
                self._stream.close()
            except Exception:
                pass
            self._stream = None


def _is_speech(mono: np.ndarray, vad, sr: int) -> bool:  # noqa: ANN001
    if vad is not None:
        pcm16 = (np.clip(mono, -1, 1) * 32767).astype(np.int16).tobytes()
        try:
            return vad.is_speech(pcm16, sr)
        except Exception:
            pass
    # フォールバック: 音量しきい値(RMS)
    return float(np.sqrt(np.mean(mono ** 2))) > 0.015
