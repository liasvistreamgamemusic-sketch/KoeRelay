"""PyInstaller 用エントリ。パッケージとして起動して相対 import を成立させる。"""
from koerelay.main import main

if __name__ == "__main__":
    raise SystemExit(main())
