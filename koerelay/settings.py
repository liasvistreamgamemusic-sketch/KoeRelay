"""アプリ設定(config.yaml 読み込み)。

サブシステムごとに入れ子の dataclass。config.yaml が無ければ既定値で動く。
pyyaml が無ければ JSON フォールバック(DATA_DIR/config.json)を使う。
AIchan の settings.py パターンを KoeRelay 向けに整理したもの。
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field, fields, is_dataclass
from pathlib import Path
from typing import Any

from .config import APP_DIR, DATA_DIR

CONFIG_FILE = APP_DIR / "config.yaml"
CONFIG_JSON_FALLBACK = DATA_DIR / "config.json"


@dataclass
class STTConfig:
    """音声→テキスト(faster-whisper)。PLAN.md §4.1 / §4.4。"""
    enabled: bool = True
    # faster-whisper: ローカル(CPU/NVIDIA)。remote: WSL等のSTTサーバ(GPU/ROCm可)にHTTP送信。
    backend: str = "faster-whisper"    # faster-whisper | remote
    # remote バックエンド時のSTTサーバ(OpenAI互換 /v1/audio/transcriptions)。
    remote_url: str = "http://127.0.0.1:8099/v1"
    # STTサーバの自動起動(remote時、任意)。WSL上のサーバを起動する例は config.yaml.example 参照。
    autostart_server: bool = False
    server_cmd: list[str] = field(default_factory=list)
    stop_cmd: list[str] = field(default_factory=list)
    model: str = "small"
    # LLMが無い構成なので STT も GPU 可(PLAN §4.4のCPU固定は撤回)。
    # auto = GPU優先で初期化し、失敗したら自動でCPUへ。
    # 注意: faster-whisper(CTranslate2)のGPUは NVIDIA CUDA のみ。AMD(ROCm)は不可でCPUになる。
    device: str = "auto"           # auto | cuda | cpu
    compute_type: str = "float16"  # cuda: float16 / cpu: 自動で int8 に補正
    language: str = "ja"
    samplerate: int = 16000
    min_record_sec: float = 0.3    # これ未満の押下/発話は誤爆として無視
    # トリガー方式: ptt(ホットキー長押し) | vad(常時リスニング、無音で自動区切り)
    mode: str = "ptt"
    vad_aggressiveness: int = 2    # webrtcvad の攻めどころ 0-3(大きいほど発話判定が厳しい)
    vad_silence_ms: int = 600      # この長さの無音で発話区間を確定(短いほど低遅延)
    vad_ignore_while_speaking: bool = True  # 発話中(TTS再生中)は取り込まない(エコー防止)


@dataclass
class TTSConfig:
    """テキスト→音声(Irodori-TTS-Server, OpenAI TTS API 互換)。PLAN.md §4.2。"""
    enabled: bool = True
    base_url: str = "http://127.0.0.1:8088/v1"
    api_key: str = "irodori"
    model: str = "irodori-tts"
    voice: str = "sumire"
    speed: float = 1.0
    response_format: str = "wav"
    cfg_scale_text: float | None = None
    cfg_scale_speaker: float | None = None
    request_timeout: float = 60.0
    # サーバ自動起動(任意)。WSL上のサーバを起動する例:
    #   ["wsl","-d","<distro>","--","bash","-lc","cd ~/github/KoeRelay/Irodori-TTS-Server && ./start.sh"]
    autostart_server: bool = False
    server_cmd: list[str] = field(default_factory=list)
    stop_cmd: list[str] = field(default_factory=list)
    warmup: bool = True            # 起動時にダミー合成で温めて初回発話を速くする


@dataclass
class AudioConfig:
    """出力ルーティング(sounddevice + VB-CABLE)。PLAN.md §4.3。"""
    # 仮想マイク側の出力デバイス。名前の部分一致で解決(既定は "CABLE Input" を自動検出)。
    output_device: str = "CABLE"   # 空文字なら既定の出力デバイス
    # モニタ用に実スピーカーへも同時再生するか(True なら monitor_device へも流す)
    monitor_enabled: bool = False
    monitor_device: str = ""       # 空なら OS 既定の出力
    # 録音に使う入力デバイス(空なら既定マイク)。名前の部分一致。
    input_device: str = ""
    volume: float = 1.0            # 再生音量倍率(1.0=そのまま)


@dataclass
class HotkeyConfig:
    """ショートカットキー長押しで録音(push-to-talk)。"""
    enabled: bool = True
    # pynput 形式のキー指定。単独キー("<f8>")か組み合わせ("<ctrl>+<alt>+k")。
    # 長押し = 押している間だけ録音、離すと文字起こし→合成→再生。
    key: str = "<f8>"


@dataclass
class UpdateConfig:
    """自動アップデート(GitHub Releases を確認)。PLAN.md §9 P3。"""
    auto_check: bool = True      # 起動時に新版を確認
    auto_install: bool = True    # True: モデル/サーバ読込前に自動DL+適用+再起動
    repo: str = "liasvistreamgamemusic-sketch/KoeRelay"


@dataclass
class AppConfig:
    stt: STTConfig = field(default_factory=STTConfig)
    tts: TTSConfig = field(default_factory=TTSConfig)
    audio: AudioConfig = field(default_factory=AudioConfig)
    hotkey: HotkeyConfig = field(default_factory=HotkeyConfig)
    update: UpdateConfig = field(default_factory=UpdateConfig)

    @classmethod
    def load(cls, path: Path | None = None) -> "AppConfig":
        path = path or CONFIG_FILE
        data: dict[str, Any] = {}
        loaded = False
        if path.exists():
            try:
                import yaml
                data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
                loaded = True
            except ImportError:
                pass
            except Exception:
                loaded = True  # 壊れている: 既定で続行
        if not loaded and CONFIG_JSON_FALLBACK.exists():
            try:
                data = json.loads(CONFIG_JSON_FALLBACK.read_text(encoding="utf-8")) or {}
            except (json.JSONDecodeError, OSError):
                pass
        return _from_dict(cls, data)

    def save(self, path: Path | None = None) -> bool:
        """pyyaml があれば config.yaml、無ければ JSON フォールバックへ保存。常に True。"""
        from dataclasses import asdict
        path = path or CONFIG_FILE
        d = asdict(self)
        try:
            import yaml
            path.write_text(
                yaml.safe_dump(d, allow_unicode=True, sort_keys=False),
                encoding="utf-8",
            )
        except ImportError:
            CONFIG_JSON_FALLBACK.parent.mkdir(parents=True, exist_ok=True)
            CONFIG_JSON_FALLBACK.write_text(
                json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8"
            )
        return True


def _from_dict(cls: type, data: dict[str, Any]) -> Any:
    """ネストした dataclass に dict を流し込む(未知キーは無視)。"""
    from typing import get_type_hints

    hints = get_type_hints(cls)
    kwargs: dict[str, Any] = {}
    for f in fields(cls):
        if f.name not in data:
            continue
        val = data[f.name]
        ftype = hints.get(f.name, f.type)
        if is_dataclass(ftype) and isinstance(val, dict):
            kwargs[f.name] = _from_dict(ftype, val)
        else:
            kwargs[f.name] = val
    return cls(**kwargs)
