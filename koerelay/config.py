"""パス解決(開発実行 / PyInstaller 凍結の両対応)。

- APP_DIR:  ユーザーが編集する config.yaml の場所(凍結時は exe と同じフォルダ)。
- DATA_DIR: 書き込みデータ(ログ・JSON設定フォールバック)の保存先(ユーザーローカル)。
- BUNDLE_ROOT: 同梱リソース(voices 等)の読み取り基準。
"""
from __future__ import annotations

import os
import sys
from pathlib import Path


def _is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def _bundle_root() -> Path:
    """読み取り専用リソースの基準。凍結時は PyInstaller の展開先。"""
    if _is_frozen():
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    return Path(__file__).resolve().parent.parent


def _app_dir() -> Path:
    """config.yaml の場所。凍結時は exe と同じフォルダ、開発時はリポジトリ直下。"""
    if _is_frozen():
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent


def _default_data_dir() -> Path:
    """ログ・設定フォールバックの書き込み先。KOERELAY_DATA_DIR で上書き可能。

    リポジトリが WSL共有(\\wsl.localhost)上だとファイルロックが不安定になりうるため、
    既定では OS のユーザーローカル領域に置く。
    """
    override = os.environ.get("KOERELAY_DATA_DIR")
    if override:
        return Path(override)
    if sys.platform == "win32":
        base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
        return Path(base) / "KoeRelay"
    xdg = os.environ.get("XDG_DATA_HOME")
    base = Path(xdg) if xdg else Path(os.path.expanduser("~")) / ".local" / "share"
    return base / "koerelay"


BUNDLE_ROOT = _bundle_root()
APP_DIR = _app_dir()
DATA_DIR = _default_data_dir()

# 同梱の参照音声(voice)ディレクトリ。ユーザー追加分は DATA_DIR/voices を優先。
BUNDLED_VOICES = BUNDLE_ROOT / "voices"
USER_VOICES = DATA_DIR / "voices"


def is_frozen() -> bool:
    return _is_frozen()
