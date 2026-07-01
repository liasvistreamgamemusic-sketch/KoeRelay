"""GPU推論を直列化する共有ロック(PLAN.md §4.4)。

STT を GPU で動かす構成(stt.device=cuda 等)にした場合、TTS(ROCm)と同じ GPU を
同時に叩くと RX 9070 XT + ROCm では不安定になりうる。両者の実推論呼び出しをこの
ロックで排他することで競合を防ぐ。既定では STT は CPU 固定なので通常は影響しない。
"""
from __future__ import annotations

import threading

GPU_LOCK = threading.Lock()
