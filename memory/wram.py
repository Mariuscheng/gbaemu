"""外部 WRAM（256 KiB）與內部 WRAM（32 KiB）。

兩者都是可讀寫 RAM；鏡像由 :class:`gbaemu.bus.regions.MemoryRegion` 的 modulo
offset 處理。GBATEK: GBA Memory Map - General Internal Memory。
"""

from __future__ import annotations

from ..bus.regions import EWRAM_BASE, EWRAM_SIZE, IWRAM_BASE, IWRAM_SIZE, MemoryRegion
from ..api_types import MemoryRegionKind


class Ewram(MemoryRegion):
    def __init__(self) -> None:
        super().__init__(MemoryRegionKind.EWRAM, EWRAM_BASE, EWRAM_SIZE)


class Iwram(MemoryRegion):
    def __init__(self) -> None:
        super().__init__(MemoryRegionKind.IWRAM, IWRAM_BASE, IWRAM_SIZE)


__all__ = ["Ewram", "Iwram"]
