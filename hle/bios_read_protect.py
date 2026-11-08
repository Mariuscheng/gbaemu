"""HLE 模式下 BIOS 讀取的可觀測近似。

規格 2.1.3：真實 BIOS 有讀取保護（PC 在 BIOS 外時回傳最近一次取出的 BIOS
opcode）。HLE 沒有真實 BIOS 內容，因此回傳固定近似值，並在文件中標明這是已知
近似，不假裝等同真實 BIOS。

Phase 0 沒有 CPU 指令執行，因此無法追蹤「最近一次 BIOS fetch」；此處的常數是
刻意選擇的最小近似。HLE/真實 BIOS 等價測試（規格 2.1.4）在 Phase 3 建立。
"""

# GBATEK: BIOS Functions - 讀取保護：只有 PC 位於 BIOS 區域時才能讀出內容，
# PC 在 BIOS 外時回傳最近一次取出的 BIOS opcode（HLE 以固定近似值替代）。
from __future__ import annotations

# 0 是明確、可重現的近似值；不宣稱對應任何真實 BIOS opcode。
HLE_BIOS_READ_VALUE = 0x00000000


def hle_bios_read(address: int, width: int) -> int:  # noqa: ARG001 - 介面保留位址
    """回傳 HLE BIOS 區域的固定近似讀值。"""

    if width not in (1, 2, 4):
        raise ValueError(f"不支援的存取寬度：{width}")
    return HLE_BIOS_READ_VALUE & ((1 << (width * 8)) - 1)


__all__ = ["HLE_BIOS_READ_VALUE", "hle_bios_read"]
