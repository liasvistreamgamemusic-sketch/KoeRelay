"""エントリポイント。トレイ常駐 → 更新確認 → サービス起動、を組み立てる。

    uv run --python 3.12 python -m koerelay.main

重要な起動順序(ユーザー要望):
1. トレイを先に出す(起動していることが分かる)。
2. **モデル/TTSサーバを読み込む前に**アップデートを確認する。
3. 更新があり auto_install=True(既定)かつ .exe 実行なら、サービスを起動せずに
   ダウンロード→入れ替え→自動再起動する(無駄なモデルロードをしない)。
4. 更新しない/失敗/開発実行なら start_services() でモデルとサーバを読み込み、
   ウォームアップ完了後にトレイが「利用可能」を通知する。

各サブシステムは依存やサービスが無くても graceful に無効化される。
"""
from __future__ import annotations

import logging
import signal
import sys
import threading

from PySide6.QtCore import QTimer
from PySide6.QtNetwork import QLocalServer, QLocalSocket
from PySide6.QtWidgets import QApplication

from . import __version__, config
from .settings import AppConfig
from .ui.tray import TrayApp

log = logging.getLogger(__name__)

_INSTANCE_KEY = "KoeRelay-single-instance"


def _setup_logging() -> None:
    fmt = "%(asctime)s %(levelname)s %(name)s: %(message)s"
    handlers: list[logging.Handler] = [logging.StreamHandler()]
    try:
        from logging.handlers import RotatingFileHandler
        config.DATA_DIR.mkdir(parents=True, exist_ok=True)
        fh = RotatingFileHandler(
            config.DATA_DIR / "koerelay.log", maxBytes=1_000_000,
            backupCount=2, encoding="utf-8",
        )
        handlers.append(fh)
    except Exception:
        pass
    logging.basicConfig(level=logging.INFO, format=fmt, handlers=handlers)


def _install_sigint(app: QApplication) -> None:
    """Ctrl+C(SIGINT)で終了できるように(QtのC++ループ対策)。"""
    signal.signal(signal.SIGINT, lambda *_: app.quit())
    keepalive = QTimer(app)
    keepalive.start(200)
    keepalive.timeout.connect(lambda: None)


def _acquire_single_instance() -> QLocalServer | None:
    """多重起動防止。既に起動中なら None。"""
    probe = QLocalSocket()
    probe.connectToServer(_INSTANCE_KEY)
    if probe.waitForConnected(300):
        probe.disconnectFromServer()
        return None
    QLocalServer.removeServer(_INSTANCE_KEY)
    server = QLocalServer()
    server.listen(_INSTANCE_KEY)
    return server


def main() -> int:
    _setup_logging()
    cfg = AppConfig.load()
    log.info("KoeRelay %s 起動 (frozen=%s, data=%s)",
             __version__, config.is_frozen(), config.DATA_DIR)

    app = QApplication(sys.argv)
    app.setApplicationName("KoeRelay")
    app.setQuitOnLastWindowClosed(False)
    _install_sigint(app)

    instance = _acquire_single_instance()
    if instance is None:
        log.info("すでに起動しています。二重起動を中止しました。")
        return 0

    tray = TrayApp(cfg)
    tray.act_quit.triggered.connect(app.quit)

    # start_services はクロージャで cfg/tray/app を掴む。
    # ここで生成した参照を shutdown で片付けられるよう外側に保持する。
    holder: dict = {}

    def start_services() -> None:
        """モデル/サーバの読み込みは「更新しないと決まってから」実行する。"""
        from .pipeline import RelayPipeline
        from .stt.recognizer import Recognizer
        from .tts.manager import TTSManager

        tray.prepare("音声")
        tray.prepare("STT")

        tts = TTSManager(cfg.tts, cfg.audio)
        tts.on_ready = lambda: tray.mark_ready("音声")

        # Whisper モデルのロード(重い)は別スレッドで。完了後に STT を ready に。
        def load_stt() -> None:
            recognizer = Recognizer(cfg.stt)
            pipeline = RelayPipeline(cfg, recognizer, tts)
            pipeline.on_state = tray.set_state
            pipeline.enabled = tray._enabled
            holder["pipeline"] = pipeline

            tray.on_toggle = lambda on: setattr(pipeline, "enabled", on)

            # ホットキー長押しで録音 → 離すと STT→TTS
            if cfg.hotkey.enabled:
                from .hotkey import HotkeyListener
                hk = HotkeyListener(
                    cfg.hotkey.key,
                    on_press=pipeline.begin_recording,
                    on_release=pipeline.end_recording,
                )
                if hk.start():
                    holder["hotkey"] = hk
                else:
                    log.warning("ホットキーを開始できませんでした(pynput未導入?)")

            _warn_if_no_cable(pipeline, tray)
            _log_status(cfg, recognizer, pipeline)
            tray.mark_ready("STT")

        tts.start()  # サーバ起動 + ウォームアップ(別スレッド)
        threading.Thread(target=load_stt, daemon=True).start()

    tray.on_stay_running = start_services

    # --- 更新を先に確認 → 更新しない/失敗なら start_services が呼ばれる ---
    if cfg.update.auto_check:
        QTimer.singleShot(400, lambda: tray.check_updates(manual=False))
    else:
        tray.begin_running()

    def shutdown() -> None:
        log.info("終了処理中…")
        hk = holder.get("hotkey")
        if hk:
            hk.stop()
        pipeline = holder.get("pipeline")
        if pipeline:
            pipeline.stop()
            pipeline.tts.stop()

    app.aboutToQuit.connect(shutdown)
    return app.exec()


def _warn_if_no_cable(pipeline, tray) -> None:  # noqa: ANN001
    """VB-CABLE が見つからなければトレイで案内(PLAN.md §4.3: 自動インストールはしない)。"""
    from PySide6.QtWidgets import QSystemTrayIcon
    sd = pipeline.tts.player._sd
    if sd is None:
        return
    from .stt.device import has_cable_output
    if not has_cable_output(sd):
        tray.tray.showMessage(
            "仮想マイクが見つかりません",
            "VB-CABLE をインストールすると Discord 等に声を流せます。"
            "https://vb-audio.com/Cable/ から導入してください。",
            QSystemTrayIcon.Warning, 8000,
        )


def _log_status(cfg: AppConfig, recognizer, pipeline) -> None:  # noqa: ANN001
    log.info("STT: %s", "有効" if recognizer.available() else "無効")
    log.info("録音デバイス: %s", "OK" if pipeline.mic.available() else "無効")
    out = pipeline.tts.player.output_device_index()
    log.info("出力(仮想マイク): device=%s (設定名=%r)",
             out if out is not None else "OS既定", cfg.audio.output_device)
    log.info("TTS: %s", "有効" if cfg.tts.enabled else "無効")


if __name__ == "__main__":
    raise SystemExit(main())
