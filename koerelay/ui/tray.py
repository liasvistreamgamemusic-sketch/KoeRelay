"""常駐トレイUI — 稼働状態と「利用可能」がひと目で分かる表示 + 更新フロー。

PLAN.md §6: アバター無し、常駐トレイ + 最小操作。
- アイコン色で状態を可視化: 準備中(灰)/ 利用可能・待機(緑)/ 録音中(赤)/
  文字起こし中(橙)/ 発話中(青)。
- ツールチップと右クリックメニューに現在状態・ホットキー・ON/OFF を表示。
- 起動時にまず更新確認 → 更新するなら「サービス起動前に」入れ替え再起動、
  更新しない/失敗なら on_stay_running() でサービスを起動する(main.py が接続)。
"""
from __future__ import annotations

import logging
from typing import Callable

from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtGui import QAction, QColor, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import QMenu, QMessageBox, QSystemTrayIcon

from ..pipeline import State
from ..settings import AppConfig

log = logging.getLogger(__name__)

_STATE_COLOR = {
    "preparing": "#9aa0a6",   # 準備中(灰)
    State.IDLE: "#2ecc71",     # 利用可能・待機(緑)
    State.RECORDING: "#e74c3c",  # 録音中(赤)
    State.TRANSCRIBING: "#f39c12",  # 文字起こし中(橙)
    State.SPEAKING: "#3498db",  # 発話中(青)
    "disabled": "#7f8c8d",     # OFF(暗い灰)
}


class TrayApp(QObject):
    # 別スレッド(更新確認/適用)から UI を触らないためのシグナル
    sigUpdate = Signal(object, bool)     # (info|None, manual)
    sigUpdateDone = Signal(bool)
    sigState = Signal(object)            # State
    sigReady = Signal(str)               # 準備完了したコンポーネント名

    def __init__(self, cfg: AppConfig) -> None:
        super().__init__()
        self.cfg = cfg
        self.on_stay_running: Callable[[], None] | None = None  # 通常起動でサービス開始
        self.on_toggle: Callable[[bool], None] | None = None    # ON/OFF 切替
        self.on_mode: Callable[[str], None] | None = None       # 'ptt' / 'vad' 切替
        self.on_monitor: Callable[[bool], None] | None = None   # モニタ出力 ON/OFF
        self.on_test: Callable[[], None] | None = None          # テスト発話
        self.on_settings: Callable[[], None] | None = None      # 設定画面を開く
        self._pending = set()   # 準備待ちのコンポーネント("音声"等)
        self._ready = False     # 全コンポーネント準備完了 = 利用可能
        self._enabled = True
        self._state: object = "preparing"

        self.tray = QSystemTrayIcon()
        self.tray.setIcon(self._make_icon(_STATE_COLOR["preparing"]))
        self._menu = QMenu()
        self._build_menu()
        self.tray.setContextMenu(self._menu)
        self.tray.setToolTip("KoeRelay — 準備中…")
        self.tray.show()

        self.sigUpdate.connect(self._on_update)
        self.sigUpdateDone.connect(self._on_update_done)
        self.sigState.connect(self._apply_state)
        self.sigReady.connect(self._mark_ready)

    # ---- アイコン描画(アセット不要で色を動的に) --------------------
    def _make_icon(self, color: str) -> QIcon:
        pm = QPixmap(64, 64)
        pm.fill(Qt.transparent)
        p = QPainter(pm)
        p.setRenderHint(QPainter.Antialiasing)
        p.setBrush(QColor(color))
        p.setPen(Qt.NoPen)
        p.drawEllipse(8, 8, 48, 48)
        # マイクを想起させる白い縦棒
        p.setBrush(QColor("#ffffff"))
        p.drawRoundedRect(28, 18, 8, 20, 4, 4)
        p.drawRect(30, 38, 4, 8)
        p.drawRect(24, 44, 16, 4)
        p.end()
        return QIcon(pm)

    # ---- メニュー ----------------------------------------------------
    def _build_menu(self) -> None:
        self.act_status = QAction("状態: 準備中…", self._menu)
        self.act_status.setEnabled(False)
        self._menu.addAction(self.act_status)

        self.act_hotkey = QAction(f"ホットキー: {self.cfg.hotkey.key}(長押しで録音)", self._menu)
        self.act_hotkey.setEnabled(False)
        self._menu.addAction(self.act_hotkey)
        self._menu.addSeparator()

        # モード切替(PTT / 常時VAD)。排他選択。
        from PySide6.QtGui import QActionGroup
        mode_menu = self._menu.addMenu("モード")
        self._mode_group = QActionGroup(self._menu)
        self._mode_group.setExclusive(True)
        self.act_mode_ptt = QAction("長押し(PTT)", self._menu, checkable=True)
        self.act_mode_vad = QAction("常時(VAD)", self._menu, checkable=True)
        self.act_mode_ptt.triggered.connect(lambda: self._select_mode("ptt"))
        self.act_mode_vad.triggered.connect(lambda: self._select_mode("vad"))
        for a in (self.act_mode_ptt, self.act_mode_vad):
            self._mode_group.addAction(a)
            mode_menu.addAction(a)
        self.act_mode_ptt.setChecked(True)

        # モニタ出力(実スピーカーへも同時再生)ON/OFF。既定は config の値。
        self.act_monitor = QAction("モニター出力(スピーカー)", self._menu, checkable=True)
        self.act_monitor.setChecked(bool(self.cfg.audio.monitor_enabled))
        self.act_monitor.triggered.connect(self._toggle_monitor)
        self._menu.addAction(self.act_monitor)

        self.act_toggle = QAction("有効", self._menu, checkable=True)
        self.act_toggle.setChecked(True)
        self.act_toggle.triggered.connect(self._toggle)
        self._menu.addAction(self.act_toggle)
        self._menu.addSeparator()

        self.act_test = QAction("テスト発話(動作確認)", self._menu)
        self.act_test.triggered.connect(lambda: self.on_test and self.on_test())
        self._menu.addAction(self.act_test)

        self.act_settings = QAction("設定…", self._menu)
        self.act_settings.triggered.connect(lambda: self.on_settings and self.on_settings())
        self._menu.addAction(self.act_settings)

        self.act_check = QAction("アップデートを確認…", self._menu)
        self.act_check.triggered.connect(lambda: self.check_updates(manual=True))
        self._menu.addAction(self.act_check)
        self._menu.addSeparator()

        self.act_quit = QAction("終了", self._menu)
        self._menu.addAction(self.act_quit)  # 終了は main.py 側で app.quit に接続

    def _toggle(self, checked: bool) -> None:
        self._enabled = checked
        self.act_toggle.setText("有効" if checked else "無効")
        if self.on_toggle:
            self.on_toggle(checked)
        self._refresh_icon()

    def _select_mode(self, mode: str) -> None:
        if self.on_mode:
            self.on_mode(mode)
        label = "長押し(PTT)" if mode == "ptt" else "常時(VAD)"
        self.tray.showMessage("モード変更", f"{label} に切り替えました",
                              QSystemTrayIcon.Information, 2500)

    def _toggle_monitor(self, checked: bool) -> None:
        if self.on_monitor:
            self.on_monitor(checked)
        self.notify("モニター出力", "スピーカーへも同時再生します" if checked
                    else "スピーカーへの再生を止めました")

    def set_mode_ui(self, mode: str) -> None:
        """外部(pipeline)の現在モードにメニューのチェックを合わせる。"""
        self.act_mode_ptt.setChecked(mode == "ptt")
        self.act_mode_vad.setChecked(mode == "vad")

    def notify(self, title: str, msg: str, warn: bool = False) -> None:
        icon = QSystemTrayIcon.Warning if warn else QSystemTrayIcon.Information
        self.tray.showMessage(title, msg, icon, 4000)

    def set_tts_status(self, ok: bool) -> None:
        """TTSサーバ接続状態を通知(未接続なら警告)。"""
        if not ok:
            self.notify(
                "TTSサーバ未接続",
                "音声合成サーバ(既定 127.0.0.1:8088)に接続できません。"
                "Irodori-TTS-Server を起動してください。",
                warn=True,
            )

    # ---- 準備状況(いつ話せるか) ------------------------------------
    def prepare(self, component: str) -> None:
        """component の準備開始を登録(準備完了まで「準備中」表示)。"""
        self._pending.add(component)
        self._ready = False

    def mark_ready(self, component: str) -> None:
        self.sigReady.emit(component)  # スレッド安全に UI スレッドへ

    def _mark_ready(self, component: str) -> None:
        self._pending.discard(component)
        if not self._pending and not self._ready:
            self._ready = True
            self._state = State.IDLE
            self._refresh_icon()
            if self.act_mode_vad.isChecked():
                hint = "常時リスニング中。話すと別の声で仮想マイクに流します。"
            else:
                hint = f"{self.cfg.hotkey.key} を長押しして話すと、別の声で仮想マイクに流します。"
            self.tray.showMessage("KoeRelay 利用可能", hint,
                                  QSystemTrayIcon.Information, 5000)
            log.info("KoeRelay 利用可能")

    # ---- 状態表示 ----------------------------------------------------
    def set_state(self, state: State) -> None:
        self.sigState.emit(state)

    def _apply_state(self, state: State) -> None:
        if self._ready:
            self._state = state
        self._refresh_icon()

    def _refresh_icon(self) -> None:
        if not self._enabled:
            color = _STATE_COLOR["disabled"]
            label = "無効(ホットキーを無視)"
        elif not self._ready:
            color = _STATE_COLOR["preparing"]
            label = "準備中…"
        else:
            color = _STATE_COLOR.get(self._state, _STATE_COLOR[State.IDLE])
            label = self._state.value if isinstance(self._state, State) else "待機中"
        self.tray.setIcon(self._make_icon(color))
        self.tray.setToolTip(f"KoeRelay — {label}")
        self.act_status.setText(f"状態: {label}")

    def set_status_text(self, text: str) -> None:
        self.act_status.setText(f"状態: {text}")
        self.tray.setToolTip(f"KoeRelay — {text}")

    # ---- 更新フロー(main.py と同じ「サービス起動前に確認」) ---------
    def check_updates(self, manual: bool = False) -> None:
        import threading
        repo = self.cfg.update.repo

        def work() -> None:
            from .. import updater
            info = updater.check(repo) if repo else None
            self.sigUpdate.emit(info, manual)

        threading.Thread(target=work, daemon=True).start()

    def _on_update(self, info, manual: bool) -> None:
        from .. import updater
        if not info:
            if manual:
                QMessageBox.information(None, "アップデート", "最新版を使用しています。")
            else:
                self.begin_running()  # 更新なし → 通常起動
            return
        tag = info.get("tag", "")
        can_apply = updater.is_frozen() and bool(info.get("asset_url"))
        auto = self.cfg.update.auto_install
        if auto and can_apply and not manual:
            self.tray.showMessage(
                "アップデート", f"{tag} をダウンロードして自動更新します(再起動します)",
                QSystemTrayIcon.Information, 4000,
            )
            self._begin_update(info)  # サービスは起動せず、更新→再起動
            return
        notes = (info.get("notes") or "")[:400]
        ret = QMessageBox.question(
            None, "アップデートがあります",
            f"新しいバージョン {tag} があります。更新しますか?\n\n{notes}",
            QMessageBox.Yes | QMessageBox.No,
        )
        if ret != QMessageBox.Yes:
            if not manual:
                self.begin_running()
            return
        if can_apply:
            self._begin_update(info)
        else:
            import webbrowser
            webbrowser.open(info.get("html_url") or "")
            if not manual:
                self.begin_running()

    def _begin_update(self, info) -> None:
        import threading
        self.set_status_text("更新をダウンロード中…そのままお待ちください")

        def work() -> None:
            ok = False
            try:
                from .. import updater
                ok = updater.apply(info.get("asset_url", ""))
            finally:
                self.sigUpdateDone.emit(bool(ok))

        threading.Thread(target=work, daemon=True).start()

    def _on_update_done(self, ok: bool) -> None:
        from PySide6.QtWidgets import QApplication
        if ok:
            QApplication.quit()  # 入れ替えバッチが終了を待って再起動する
        else:
            QMessageBox.warning(
                None, "アップデート",
                "更新の適用に失敗しました。リリースページから手動で更新してください。\n"
                "(詳細ログ: data フォルダの update.log)",
            )
            self.begin_running()  # 失敗時はそのまま通常起動

    # ---- 通常起動(サービス開始) ------------------------------------
    def begin_running(self) -> None:
        if self.on_stay_running:
            self.on_stay_running()
