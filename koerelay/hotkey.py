"""グローバルショートカットキーの長押し検出(push-to-talk)。

pynput でキーの押下/離しを監視し、設定キーを押している間だけ on_press、
離したら on_release を呼ぶ。単独キー("<f8>")と組み合わせ("<ctrl>+<alt>+k")の
両方に対応。pynput が無ければ no-op(available()=False)。
"""
from __future__ import annotations

import logging
from typing import Callable

log = logging.getLogger(__name__)


class HotkeyListener:
    def __init__(self, key_spec: str,
                 on_press: Callable[[], None],
                 on_release: Callable[[], None]) -> None:
        self.key_spec = key_spec
        self._on_press = on_press
        self._on_release = on_release
        self._listener = None
        self._keyboard = None
        self._required: set = set()   # 押されている必要のあるキー集合
        self._pressed: set = set()    # 現在押されているキー(対象のみ)
        self._active = False          # 長押し発火中か
        try:
            from pynput import keyboard
            self._keyboard = keyboard
        except Exception:
            log.info("pynput 不在 → グローバルホットキー無効")

    def available(self) -> bool:
        return self._keyboard is not None

    def start(self) -> bool:
        if not self.available():
            return False
        # listener を先に作る(canonical() を使うため)。まだ start はしない。
        try:
            self._listener = self._keyboard.Listener(
                on_press=self._handle_press, on_release=self._handle_release
            )
        except Exception as e:
            log.warning("ホットキー監視の作成に失敗: %s", e)
            return False
        try:
            self._required = self._parse(self.key_spec)
        except Exception as e:
            log.warning("ホットキー '%s' の解釈に失敗: %s", self.key_spec, e)
            self._listener = None
            return False
        if not self._required:
            log.warning("ホットキーが空です")
            self._listener = None
            return False
        try:
            self._listener.start()
            log.info("ホットキー監視開始: %s(長押しで録音)", self.key_spec)
            return True
        except Exception as e:
            log.warning("ホットキー監視の開始に失敗: %s", e)
            return False

    def stop(self) -> None:
        if self._listener:
            try:
                self._listener.stop()
            except Exception:
                pass
            self._listener = None

    # ---- 内部 --------------------------------------------------------
    def _parse(self, spec: str) -> set:
        """'<ctrl>+<alt>+k' → 正規化キー集合。pynput の HotKey.parse を利用。"""
        keys = self._keyboard.HotKey.parse(spec)
        return {self._norm(k) for k in keys}

    def _norm(self, key):  # noqa: ANN001
        """修飾状態で変わる文字などを canonical 形に正規化して比較を安定させる。"""
        if self._listener is not None:
            try:
                return self._listener.canonical(key)
            except Exception:
                pass
        return key

    def _handle_press(self, key) -> None:  # noqa: ANN001
        try:
            k = self._norm(key)
        except Exception:
            return
        if k in self._required:
            self._pressed.add(k)
            if not self._active and self._pressed >= self._required:
                self._active = True
                try:
                    self._on_press()
                except Exception as e:
                    log.warning("on_press エラー: %s", e)

    def _handle_release(self, key) -> None:  # noqa: ANN001
        try:
            k = self._norm(key)
        except Exception:
            return
        if k in self._required:
            self._pressed.discard(k)
            if self._active:
                self._active = False
                try:
                    self._on_release()
                except Exception as e:
                    log.warning("on_release エラー: %s", e)
