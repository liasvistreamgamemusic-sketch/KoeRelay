"""Irodori-TTS-Server の subprocess ライフサイクル管理(任意・autostart時)。

アプリ起動時に起動 → /health 待ち、終了時に停止。既に起動済みなら何もしない
(既存の常駐サーバは殺さない)。AIchan の server.py を移植。
"""
from __future__ import annotations

import logging
import subprocess
import time

from ..settings import TTSConfig
from .irodori import IrodoriTTS

log = logging.getLogger(__name__)

_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


class TTSServerProcess:
    def __init__(self, cfg: TTSConfig) -> None:
        self.cfg = cfg
        self.proc: subprocess.Popen | None = None
        self._started = False  # 自分で起動した時だけ停止する

    def start(self, wait_sec: float = 60.0) -> bool:
        if not self.cfg.autostart_server or not self.cfg.server_cmd:
            return False
        client = IrodoriTTS(self.cfg)
        if client.health():
            log.info("TTSサーバは既に起動済み(自動起動スキップ)")
            return True
        log.info("TTSサーバ起動: %s", " ".join(self.cfg.server_cmd))
        try:
            self.proc = subprocess.Popen(self.cfg.server_cmd, creationflags=_NO_WINDOW)
            self._started = True
        except Exception as e:
            log.warning("TTSサーバ起動失敗: %s", e)
            return False
        deadline = wait_sec
        while deadline > 0:
            if client.health():
                log.info("TTSサーバ ready")
                return True
            time.sleep(1.0)
            deadline -= 1.0
        log.warning("TTSサーバ ready 待ちタイムアウト")
        return False

    def stop(self) -> None:
        if not self._started:
            return  # 既存の常駐サーバは殺さない
        cmd = list(self.cfg.stop_cmd)
        if not cmd and self.cfg.server_cmd[:1] == ["wsl"]:
            prefix = self.cfg.server_cmd[:3]  # ["wsl","-d","<distro>"]
            cmd = prefix + ["--", "bash", "-lc", "pkill -f irodori_openai_tts"]
        if cmd:
            log.info("TTSサーバ停止コマンド: %s", " ".join(cmd))
            try:
                subprocess.run(cmd, timeout=15, creationflags=_NO_WINDOW)
            except Exception as e:
                log.warning("TTS停止コマンド失敗: %s", e)
        if self.proc and self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.proc.kill()
        self.proc = None
