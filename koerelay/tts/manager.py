"""TTS高レベル管理: サーバ起動 → ウォームアップ → 合成→再生を直列化。

speak(text) は即時に戻り、ワーカースレッドで合成→仮想マイク再生する。
on_ready はウォームアップ完了(=最初の発話が速く出せる状態)で呼ばれる。
"""
from __future__ import annotations

import logging
import queue
import threading
from typing import Callable

from ..settings import AudioConfig, TTSConfig
from .irodori import IrodoriTTS
from .player import AudioPlayer
from .server import TTSServerProcess

log = logging.getLogger(__name__)


class TTSManager:
    def __init__(self, tts: TTSConfig, audio: AudioConfig) -> None:
        self.cfg = tts
        self.backend = IrodoriTTS(tts)
        self.player = AudioPlayer(audio)
        self.server = TTSServerProcess(tts)
        self._q: "queue.Queue[str | None]" = queue.Queue()
        self._thread: threading.Thread | None = None
        self._running = False
        self.on_ready: Callable[[], None] | None = None   # ウォームアップ完了通知
        self.on_start: Callable[[], None] | None = None    # 再生開始通知(UI表示用)
        self.on_end: Callable[[], None] | None = None      # 再生終了通知

    def health(self) -> bool:
        """TTSサーバに接続できるか。"""
        return self.backend.health()

    def start(self) -> None:
        if not self.cfg.enabled:
            if self.on_ready:
                self.on_ready()
            return
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        threading.Thread(target=self._boot, daemon=True).start()

    def _boot(self) -> None:
        """サーバ起動を待ち、ダミー合成でモデル/カーネルを温める(初回発話の遅延を先に解消)。"""
        try:
            self.server.start()
            if not self.backend.health():
                log.info("TTSサーバに接続できません(合成はスキップされます)")
                return
            if self.cfg.warmup:
                log.info("TTS ウォームアップ中…")
                self.backend.synth("こんにちは。", speed=self.cfg.speed)
                log.info("TTS ウォームアップ完了")
        except Exception as e:
            log.info("TTS ウォームアップ skip: %s", e)
        finally:
            if self.on_ready:
                self.on_ready()  # 成否に関わらず待ちを解除

    def speak(self, text: str) -> None:
        """text を合成・再生(非ブロッキング)。"""
        if not self.cfg.enabled or not self._running or not text:
            return
        self._q.put(text)

    def _loop(self) -> None:
        while self._running:
            text = self._q.get()
            if text is None:
                break
            try:
                audio = self.backend.synth(text, speed=self.cfg.speed)
                if audio:
                    if self.on_start:
                        self.on_start()
                    self.player.play(audio)
            except Exception as e:
                log.warning("TTS再生エラー: %s", e)
            finally:
                if self.on_end:
                    self.on_end()

    def stop(self) -> None:
        self._running = False
        self.player.stop()
        if self._thread:
            self._q.put(None)  # sentinel
        self.server.stop()
