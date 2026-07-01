"""音声再生(sounddevice)。VB-CABLE 等の指定出力へ流す + 任意でモニタ同時出力。

PLAN §4.3: 合成音声を「CABLE Input」へ再生 → 他アプリが「CABLE Output」を
マイクとして拾える。モニタ有効時は実スピーカーへも「同時に」流す。

重要: sounddevice のモジュール関数 sd.play()/sd.wait() は単一のグローバル
ストリームを使うため、2デバイスへ同時再生できない(後の呼び出しが前を止める)。
そこでデバイスごとに専用 OutputStream を開いて並行 write する。
"""
from __future__ import annotations

import io
import logging
import threading

import numpy as np

from ..settings import AudioConfig
from ..stt.device import resolve_output_device

log = logging.getLogger(__name__)


class AudioPlayer:
    def __init__(self, cfg: AudioConfig) -> None:
        self.cfg = cfg
        self._sd = None
        self._sf = None
        self._stop = threading.Event()
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
        """設定の output_device(既定 'CABLE')を解決した index。無ければ None(=OS既定)。"""
        if self._sd is None:
            return None
        return resolve_output_device(self._sd, self.cfg.output_device)

    def _default_output_index(self):
        """OS 既定の出力デバイス index。取得できなければ None。"""
        try:
            dev = self._sd.default.device
            return dev[1] if dev else None
        except Exception:
            return None

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
            data = (data * max(0.0, self.cfg.volume)).astype("float32")
        if data.ndim == 1:
            data = data.reshape(-1, 1)

        self._stop.clear()
        out_idx = resolve_output_device(self._sd, self.cfg.output_device)
        targets = [("出力", out_idx)]
        if self.cfg.monitor_enabled:
            if self.cfg.monitor_device:
                mon_idx = resolve_output_device(self._sd, self.cfg.monitor_device)
            else:
                mon_idx = self._default_output_index()
                # 既定出力が CABLE(=出力先と同じ)だとスピーカーから鳴らない典型ケース。
                if mon_idx is not None and mon_idx == out_idx:
                    log.warning("モニタ先がOS既定=CABLEと同じです。スピーカーから鳴りません。"
                                "config の audio.monitor_device に実スピーカー名を指定してください")
            targets.append(("モニタ", mon_idx))

        dur = len(data) / sr if sr else 0.0
        log.info("再生: %.1f秒 → %s", dur,
                 ", ".join(f"{lbl}(device={dev if dev is not None else 'OS既定'})"
                           for lbl, dev in targets))

        # モニタ側は別スレッドで並行。仮想マイク側は呼び出しスレッドで待つ。
        threads = []
        for label, dev in targets[1:]:
            t = threading.Thread(target=self._play_on, args=(data, sr, dev, label),
                                 daemon=True)
            t.start()
            threads.append(t)
        self._play_on(data, sr, targets[0][1], targets[0][0])
        for t in threads:
            t.join(timeout=dur + 2.0)

    def _play_on(self, data: np.ndarray, sr: int, device, label: str) -> None:  # noqa: ANN001
        try:
            channels = data.shape[1] if data.ndim > 1 else 1
            with self._sd.OutputStream(samplerate=sr, channels=channels,
                                       device=device, dtype="float32") as stream:
                block = 2048
                for i in range(0, len(data), block):
                    if self._stop.is_set():
                        break
                    stream.write(data[i:i + block])
        except Exception as e:
            log.warning("再生失敗 [%s] (device=%s): %s", label, device, e)

    def stop(self) -> None:
        self._stop.set()
        if self._sd is not None:
            try:
                self._sd.stop()
            except Exception:
                pass
