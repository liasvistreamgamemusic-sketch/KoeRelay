"""設定画面(トレイの「設定…」から開く)。

デバイス(入力/出力/モニター先)・音量・声・話速・トリガー方式・ホットキー・自動更新などを
GUIで編集して config.yaml に保存する。音量/出力先/モニター/声/話速/モードは即時反映。
STTバックエンドやホットキーの変更は再起動後に有効(ダイアログで案内)。
"""
from __future__ import annotations

import logging
from typing import Callable

from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QDialogButtonBox, QDoubleSpinBox,
    QFormLayout, QLabel, QLineEdit, QVBoxLayout,
)

from ..settings import AppConfig
from ..stt.device import list_devices

log = logging.getLogger(__name__)

_DEFAULT_LABEL = "(既定)"


class SettingsDialog(QDialog):
    def __init__(self, cfg: AppConfig, sd, on_apply: Callable[[AppConfig], None],
                 parent=None) -> None:  # noqa: ANN001
        super().__init__(parent)
        self.cfg = cfg
        self._on_apply = on_apply
        self.setWindowTitle("KoeRelay 設定")
        self.setMinimumWidth(460)

        inputs, outputs = ([], [])
        if sd is not None:
            inputs, outputs = list_devices(sd)
        self._in_names = [n for _, n in inputs]
        self._out_names = [n for _, n in outputs]

        form = QFormLayout()

        # --- 音声デバイス ---
        self.cmb_input = self._device_combo(self._in_names, cfg.audio.input_device)
        form.addRow("入力マイク", self.cmb_input)

        self.cmb_output = self._device_combo(self._out_names, cfg.audio.output_device,
                                             allow_default=False)
        form.addRow("出力(仮想マイク/CABLE Input)", self.cmb_output)

        self.chk_monitor = QCheckBox("スピーカーへも同時に鳴らす")
        self.chk_monitor.setChecked(bool(cfg.audio.monitor_enabled))
        form.addRow("モニター出力", self.chk_monitor)

        self.cmb_monitor = self._device_combo(self._out_names, cfg.audio.monitor_device)
        form.addRow("モニター先(スピーカー)", self.cmb_monitor)

        self.spin_vol = QDoubleSpinBox()
        self.spin_vol.setRange(0.0, 3.0)
        self.spin_vol.setSingleStep(0.1)
        self.spin_vol.setValue(float(cfg.audio.volume))
        form.addRow("音量(倍率)", self.spin_vol)

        # --- 声(TTS) ---
        self.edit_voice = QLineEdit(cfg.tts.voice)
        form.addRow("声(voice)", self.edit_voice)

        self.spin_speed = QDoubleSpinBox()
        self.spin_speed.setRange(0.5, 2.0)
        self.spin_speed.setSingleStep(0.05)
        self.spin_speed.setValue(float(cfg.tts.speed))
        form.addRow("話速", self.spin_speed)

        # --- 入力方式(STT) ---
        self.cmb_mode = QComboBox()
        self.cmb_mode.addItems(["ptt", "vad"])
        self.cmb_mode.setCurrentText(cfg.stt.mode if cfg.stt.mode in ("ptt", "vad") else "ptt")
        form.addRow("トリガー(ptt=長押し / vad=常時)", self.cmb_mode)

        self.edit_hotkey = QLineEdit(cfg.hotkey.key)
        self.edit_hotkey.setPlaceholderText("例: <f8> / <ctrl>+<alt>+k")
        form.addRow("ホットキー(長押しで録音)", self.edit_hotkey)

        self.cmb_backend = QComboBox()
        self.cmb_backend.addItems(["faster-whisper", "remote"])
        self.cmb_backend.setCurrentText(cfg.stt.backend if cfg.stt.backend in
                                        ("faster-whisper", "remote") else "faster-whisper")
        form.addRow("STTバックエンド(再起動後に反映)", self.cmb_backend)

        # --- 更新 ---
        self.chk_update = QCheckBox("新版を自動でDL・適用する")
        self.chk_update.setChecked(bool(cfg.update.auto_install))
        form.addRow("自動アップデート", self.chk_update)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        note = QLabel("音量/出力先/モニター/声/話速/モード/ホットキーは即時反映。"
                      "STTバックエンドの変更のみ再起動後に有効です。")
        note.setWordWrap(True)
        note.setStyleSheet("color: #888; font-size: 11px;")
        layout.addWidget(note)

        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self._save)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _device_combo(self, names: list[str], current: str,
                      allow_default: bool = True) -> QComboBox:
        cmb = QComboBox()
        cmb.setEditable(True)  # 一覧に無い名前(部分一致)も手入力できる
        if allow_default:
            cmb.addItem(_DEFAULT_LABEL)
        cmb.addItems(names)
        if current:
            cmb.setCurrentText(current)
        elif allow_default:
            cmb.setCurrentText(_DEFAULT_LABEL)
        return cmb

    def _combo_value(self, cmb: QComboBox) -> str:
        text = cmb.currentText().strip()
        return "" if text == _DEFAULT_LABEL else text

    def _save(self) -> None:
        c = self.cfg
        c.audio.input_device = self._combo_value(self.cmb_input)
        c.audio.output_device = self._combo_value(self.cmb_output)
        c.audio.monitor_enabled = self.chk_monitor.isChecked()
        c.audio.monitor_device = self._combo_value(self.cmb_monitor)
        c.audio.volume = float(self.spin_vol.value())
        c.tts.voice = self.edit_voice.text().strip() or c.tts.voice
        c.tts.speed = float(self.spin_speed.value())
        c.stt.mode = self.cmb_mode.currentText()
        c.hotkey.key = self.edit_hotkey.text().strip() or c.hotkey.key
        c.stt.backend = self.cmb_backend.currentText()
        c.update.auto_install = self.chk_update.isChecked()
        try:
            c.save()
        except Exception as e:
            log.warning("設定の保存に失敗: %s", e)
        try:
            self._on_apply(c)
        except Exception as e:
            log.warning("設定の反映に失敗: %s", e)
        self.accept()
