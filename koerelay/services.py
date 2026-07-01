"""外部サービス(WSL上のSTT/TTSサーバ等)の自動起動・停止。

readiness 確認は依存を増やさないよう urllib(標準ライブラリ)で行う。
自分で起動した時だけ停止する(既存の常駐サーバは殺さない)。
"""
from __future__ import annotations

import logging
import subprocess
import time
import urllib.request

log = logging.getLogger(__name__)

_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


class ManagedProcess:
    def __init__(self, cmd: list[str], ready_url: str | None = None,
                 name: str = "service", stop_cmd: list[str] | None = None) -> None:
        self.cmd = cmd
        self.ready_url = ready_url
        self.name = name
        self.stop_cmd = stop_cmd or []
        self.proc: subprocess.Popen | None = None
        self._started = False

    def _ready(self) -> bool:
        if not self.ready_url:
            return True
        try:
            with urllib.request.urlopen(self.ready_url, timeout=2) as r:
                return r.status < 500
        except Exception:
            return False

    def start(self, wait_sec: float = 90.0) -> bool:
        if not self.cmd:
            return False
        if self._ready():
            log.info("%s は既に起動済み(自動起動スキップ)", self.name)
            return True
        log.info("%s を自動起動: %s", self.name, " ".join(self.cmd))
        try:
            self.proc = subprocess.Popen(self.cmd, creationflags=_NO_WINDOW)
            self._started = True
        except Exception as e:
            log.warning("%s の起動に失敗: %s", self.name, e)
            return False
        deadline = wait_sec
        while deadline > 0:
            if self._ready():
                log.info("%s ready", self.name)
                return True
            time.sleep(1.0)
            deadline -= 1.0
        log.warning("%s の ready 待ちタイムアウト(起動はしている可能性)", self.name)
        return False

    def stop(self) -> None:
        if not self._started:
            return  # 既存の常駐サーバは殺さない
        cmd = list(self.stop_cmd)
        if not cmd and self.cmd[:1] == ["wsl"]:
            prefix = self.cmd[:3]  # ["wsl","-d","<distro>"]
            cmd = prefix + ["--", "bash", "-lc", "pkill -f 'uvicorn server:app'"]
        if cmd:
            log.info("%s 停止コマンド: %s", self.name, " ".join(cmd))
            try:
                subprocess.run(cmd, timeout=15, creationflags=_NO_WINDOW)
            except Exception as e:
                log.warning("%s 停止コマンド失敗: %s", self.name, e)
        if self.proc and self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.proc.kill()
        self.proc = None
