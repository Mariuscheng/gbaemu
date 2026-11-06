"""OAM（1 KiB）。

GBATEK: GBA LCD Video Controller - VRAM：OAM 的 8-bit 寫入被忽略，只有
16/32-bit 寫入生效。
"""

from __future__ import annotations

from ..api_types import MemoryRegionKind
from ..bus.regions import OAM_BASE, OAM_SIZE, MemoryRegion


class Oam(MemoryRegion):
    def __init__(self) -> None:
        super().__init__(MemoryRegionKind.OAM, OAM_BASE, OAM_SIZE)

    def write_u8(self, offset: int, value: int) -> None:
        return  # OAM：8-bit 寫入忽略


__all__ = ["Oam"]
