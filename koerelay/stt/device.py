"""sounddevice のデバイスを名前(部分一致)で解決するヘルパ。

VB-CABLE の "CABLE Input"(出力=仮想スピーカー)や特定マイクを、
デバイスID直指定ではなく名前の一部で選べるようにする(PLAN.md §4.3)。
"""
from __future__ import annotations

import logging

log = logging.getLogger(__name__)


def _match(sd, name: str, *, want_output: bool):  # noqa: ANN001
    """name(部分一致・大文字小文字無視)に合う入出力デバイスの index を返す。無ければ None。"""
    if not name:
        return None
    key = name.lower()
    try:
        devices = sd.query_devices()
    except Exception as e:
        log.info("デバイス一覧の取得に失敗: %s", e)
        return None
    for idx, dev in enumerate(devices):
        ch = dev.get("max_output_channels" if want_output else "max_input_channels", 0)
        if ch <= 0:
            continue
        if key in dev.get("name", "").lower():
            return idx
    return None


def resolve_output_device(sd, name: str):  # noqa: ANN001
    """出力デバイスを名前で解決。見つからなければ None(=OS既定)。"""
    idx = _match(sd, name, want_output=True)
    if name and idx is None:
        log.warning("出力デバイス '%s' が見つかりません → OS既定にフォールバック", name)
    return idx


def resolve_input_device(sd, name: str):  # noqa: ANN001
    """入力デバイスを名前で解決。見つからなければ None(=既定マイク)。"""
    idx = _match(sd, name, want_output=False)
    if name and idx is None:
        log.warning("入力デバイス '%s' が見つかりません → 既定マイクにフォールバック", name)
    return idx


def list_devices(sd):  # noqa: ANN001
    """(inputs, outputs) のリストを返す。各要素は (index, name)。UI 用。"""
    inputs, outputs = [], []
    try:
        for idx, dev in enumerate(sd.query_devices()):
            name = dev.get("name", f"device {idx}")
            if dev.get("max_input_channels", 0) > 0:
                inputs.append((idx, name))
            if dev.get("max_output_channels", 0) > 0:
                outputs.append((idx, name))
    except Exception as e:
        log.info("デバイス列挙に失敗: %s", e)
    return inputs, outputs


def has_cable_output(sd) -> bool:  # noqa: ANN001
    """VB-CABLE の 'CABLE Input' 出力が存在するか(初回案内用)。"""
    return _match(sd, "CABLE", want_output=True) is not None
