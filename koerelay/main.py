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
        from .stt import build_recognizer
        from .tts.manager import TTSManager

        tray.prepare("音声")
        tray.prepare("STT")

        tts = TTSManager(cfg.tts, cfg.audio)
        holder["tts"] = tts

        def on_tts_ready() -> None:
            # ウォームアップ後: 準備完了 + サーバ接続状態を通知(未接続なら警告)。
            tray.set_tts_status(tts.health())
            tray.mark_ready("音声")

        tts.on_ready = on_tts_ready

        # Whisper モデルのロード(重い)は別スレッドで。完了後に STT を ready に。
        def load_stt() -> None:
            # remote バックエンドなら STT サーバを自動起動(任意)してから接続。
            if cfg.stt.backend == "remote" and cfg.stt.autostart_server and cfg.stt.server_cmd:
                from .services import ManagedProcess
                stt_proc = ManagedProcess(
                    cfg.stt.server_cmd,
                    ready_url=cfg.stt.remote_url.rstrip("/").rsplit("/v1", 1)[0] + "/health",
                    name="STTServer", stop_cmd=list(cfg.stt.stop_cmd),
                )
                holder["stt_proc"] = stt_proc
                stt_proc.start()

            recognizer = build_recognizer(cfg.stt)
            recognizer.warmup()  # 初回の文字起こし遅延を起動時に先取り
            pipeline = RelayPipeline(cfg, recognizer, tts)
            pipeline.on_state = tray.set_state
            pipeline.on_text = lambda t: _on_transcribed(tray, t)
            pipeline.enabled = tray._enabled
            holder["pipeline"] = pipeline

            tray.on_toggle = pipeline.set_enabled
            tray.on_mode = pipeline.set_mode
            tray.set_mode_ui(pipeline.mode)
            # モニタ出力トグル: cfg.audio は player と共有オブジェクトなので即反映される。
            tray.on_monitor = lambda on: setattr(cfg.audio, "monitor_enabled", on)
            tray.on_test = lambda: _test_speak(tts, tray)

            # ホットキー(PTT用)を(再)起動する関数。設定変更時に付け替えられる。
            def restart_hotkey() -> None:
                old = holder.pop("hotkey", None)
                if old:
                    old.stop()
                if not cfg.hotkey.enabled:
                    return
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

            restart_hotkey()

            # 設定画面: 保存時に即時反映(モード/モニタUI/ホットキー付け替え)。
            tray.on_settings = lambda: _open_settings(cfg, pipeline, tray, restart_hotkey)

            pipeline.start()  # 設定モード(既定PTT / vadなら常時リスニング)で開始
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
        # TTS(サーバ自動起動していれば pkill 等で停止)。pipeline 未完成でも確実に止める。
        tts = holder.get("tts")
        if tts:
            tts.stop()
        # STTサーバ(自動起動していれば停止)。
        stt_proc = holder.get("stt_proc")
        if stt_proc:
            stt_proc.stop()

    app.aboutToQuit.connect(shutdown)
    return app.exec()


def _on_transcribed(tray, text: str) -> None:  # noqa: ANN001
    """文字起こし結果をトレイに反映。空なら「認識できず」を通知(動作確認しやすく)。"""
    if text:
        tray.set_status_text(f"認識: {text[:30]}")
    else:
        tray.notify("音声を認識できませんでした",
                    "もう一度ゆっくり話すか、入力マイクを確認してください。")


def _open_settings(cfg, pipeline, tray, restart_hotkey) -> None:  # noqa: ANN001
    """設定ダイアログを開き、保存時に可能な項目を即時反映する。"""
    from .ui.settings_dialog import SettingsDialog

    prev_backend = cfg.stt.backend
    sd = pipeline.tts.player._sd  # デバイス一覧用(None可)

    def apply(c) -> None:  # noqa: ANN001
        pipeline.set_mode(c.stt.mode)          # トリガー方式を即反映
        tray.set_mode_ui(c.stt.mode)
        tray.act_monitor.setChecked(bool(c.audio.monitor_enabled))
        restart_hotkey()                        # 新しいキーで付け替え
        if c.stt.backend != prev_backend:
            tray.notify("設定", "STTバックエンドの変更は再起動後に有効です。")
        else:
            tray.notify("設定", "設定を保存しました(即時反映)。")

    dlg = SettingsDialog(cfg, sd, apply)
    dlg.exec()


def _test_speak(tts, tray) -> None:  # noqa: ANN001
    """テスト発話。サーバ未接続なら警告、接続していれば固定文を合成・再生。"""
    import threading

    def work() -> None:
        if not tts.health():
            tray.set_tts_status(False)
            return
        tray.notify("テスト発話", "「テストです」を今の声で再生します。"
                    "聞こえない場合はモニター出力をONにするか出力デバイスを確認してください。")
        tts.speak("テストです。この声が聞こえていますか。")

    threading.Thread(target=work, daemon=True).start()


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
    _log_output_devices(pipeline)


def _log_output_devices(pipeline) -> None:  # noqa: ANN001
    """出力デバイス一覧をログへ。monitor_device 設定名の手掛かりにする。"""
    sd = pipeline.tts.player._sd
    if sd is None:
        return
    try:
        default_out = sd.default.device[1] if sd.default.device else None
    except Exception:
        default_out = None
    from .stt.device import list_devices
    _, outputs = list_devices(sd)
    log.info("=== 出力デバイス一覧(monitor_device にこの名前の一部を指定)===")
    for idx, name in outputs:
        marks = []
        if idx == default_out:
            marks.append("既定")
        if "cable" in name.lower():
            marks.append("CABLE=仮想マイク")
        suffix = f"  [{'/'.join(marks)}]" if marks else ""
        log.info("  [%s] %s%s", idx, name, suffix)
    log.info("=== ここまで ===")


if __name__ == "__main__":
    raise SystemExit(main())
