"""音声再生(sounddevice)。VB-CABLE 等の指定出力デバイスへ流す。

PLAN.md §4.3: 合成音声を「CABLE Input」へ再生することで、他アプリ(Discord/OBS/
ゲーム)が「CABLE Output」をマイクとして拾える。モニタ用に実スピーカーへも
同時再生できる(monitor_enabled)。sounddevice が無ければ no-op。
"""
from __future__ import annotations

import io
import logging
import threading

from ..settings import AudioConfig
from ..stt.device import resolve_output_device

log = logging.getLogger(__name__)


class AudioPlayer:
    def __init__(self, cfg: AudioConfig) -> None:
        self.cfg = cfg
        self._sd = None
        self._sf = None
        try:
            import sounddevice as sd
            import soundfile as sf
            self._sd = sd
            self._sf = sf
        except Exception:
            log.info("sounddevice/soundfile 不在 → 再生無効")

    def available(self) -> bool:
        return self._sd is not None and self._sf is not None

    def output_device_index(self):
        """設定の output_device(既定 'CABLE')を解決した index。無ければ None。"""
        if self._sd is None:
            return None
        return resolve_output_device(self._sd, self.cfg.output_device)

    def play(self, audio: bytes) -> None:
        """音声バイト列を仮想マイク(+任意でモニタ)へ再生。完了までブロック。"""
        if not audio or not self.available():
            return
        try:
            data, sr = self._sf.read(io.BytesIO(audio), dtype="float32")
        except Exception as e:
            log.warning("音声デコード失敗: %s", e)
            return
        if self.cfg.volume != 1.0:
            data = data * max(0.0, self.cfg.volume)

        out_idx = resolve_output_device(self._sd, self.cfg.output_device)

        # モニタ(実スピーカー)へは別スレッドで同時再生(ブロックせず並行)。
        monitor_thread = None
        if self.cfg.monitor_enabled:
            mon_idx = resolve_output_device(self._sd, self.cfg.monitor_device) \
                if self.cfg.monitor_device else None
            monitor_thread = threading.Thread(
                target=self._play_on, args=(data, sr, mon_idx), daemon=True
            )
            monitor_thread.start()

        self._play_on(data, sr, out_idx)  # 仮想マイク側(完了まで待つ)
        if monitor_thread:
            monitor_thread.join(timeout=0.1)

    def _play_on(self, data, sr, device) -> None:  # noqa: ANN001
        try:
            self._sd.play(data, sr, device=device)
            self._sd.wait()
        except Exception as e:
            log.warning("再生失敗 (device=%s): %s", device, e)

    def stop(self) -> None:
        if self._sd is not None:
            try:
                self._sd.stop()
            except Exception:
                pass
