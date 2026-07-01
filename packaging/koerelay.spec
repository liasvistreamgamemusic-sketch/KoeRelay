# PyInstaller spec — 単体 .exe 化(Windows実機でビルド)。
# 使い方(Windows):
#   uv run --extra full --with pyinstaller pyinstaller packaging/koerelay.spec
#
# 注意: faster-whisper(ctranslate2)/ sounddevice(portaudio)/ PySide6 はネイティブ
# バイナリを含むため、環境により hiddenimports / binaries の追加調整が要ることがある。

from pathlib import Path
from PyInstaller.utils.hooks import collect_submodules, collect_all

root = Path(SPECPATH).parent

datas = []
# 同梱の参照音声(あれば)。無くても動く。
voices = root / "voices"
if voices.is_dir():
    datas.append((str(voices), "voices"))
cfg_example = root / "config.yaml.example"
if cfg_example.exists():
    datas.append((str(cfg_example), "."))

binaries = []
hiddenimports = collect_submodules("koerelay")

# ネイティブ依存はまるごと収集(datas+binaries+hiddenimports)。
for mod in ("faster_whisper", "ctranslate2", "onnxruntime", "av",
            "tokenizers", "sounddevice", "soundfile", "pynput", "webrtcvad"):
    try:
        d, b, h = collect_all(mod)
        datas += d
        binaries += b
        hiddenimports += h
    except Exception:
        pass

a = Analysis(
    [str(root / "packaging" / "launcher.py")],
    pathex=[str(root)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz, a.scripts, [], exclude_binaries=True,
    name="KoeRelay",
    console=False,   # GUI(トレイ)アプリ。コンソール非表示
)
coll = COLLECT(
    exe, a.binaries, a.datas,
    name="KoeRelay",
)
