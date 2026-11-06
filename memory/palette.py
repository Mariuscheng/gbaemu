"""Palette RAM（1 KiB）。

GBATEK: GBA LCD Video Controller - VRAM：Palette RAM 的 8-bit 寫入會複製到
對應半字的高低位元組（``[addr & ~1] = data * 0x101``）。
"""

from __future__ import annotations

from ..api_types import MemoryRegionKind
from ..bus.regions import PALETTE_BASE, PALETTE_SIZE, MemoryRegion


class PaletteRam(MemoryRegion):
    def __init__(self) -> None:
        super().__init__(MemoryRegionKind.PALETTE, PALETTE_BASE, PALETTE_SIZE)

    def write_u8(self, offset: int, value: int) -> None:
        aligned = offset & ~1
        value &= 0xFF
        self.write_raw_u8(aligned, value)
        self.write_raw_u8(aligned + 1, value)


__all__ = ["PaletteRam"]
