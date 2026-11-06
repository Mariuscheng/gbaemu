"""VRAM（96 KiB）與 BG/OBJ 分界。

GBATEK: GBA LCD Video Controller - VRAM：

* Mode 0/1/2（tile）：BG 64 KiB、OBJ 32 KiB，分界 ``0x06010000``。
* Mode 3/4/5（bitmap）：BG 80 KiB、OBJ 16 KiB，分界 ``0x06014000``。
* BG VRAM 的 8-bit 寫入會把值複製到該半字的的高低兩位元組。
* OBJ VRAM 的 8-bit 寫入被忽略。
* ``0x06018000`` 之後的 32 KiB 鏡像回 ``0x06010000``。
"""

from __future__ import annotations

from ..api_types import MemoryRegionKind
from ..bus.regions import (
    VRAM_BASE,
    VRAM_BITMAP_BG_END,
    VRAM_SIZE,
    VRAM_TILE_BG_END,
    VRAM_WINDOW_SIZE,
    MemoryRegion,
)


class Vram(MemoryRegion):
    def __init__(self) -> None:
        super().__init__(MemoryRegionKind.VRAM, VRAM_BASE, VRAM_SIZE)
        self.bitmap_mode = False

    @property
    def bg_end(self) -> int:
        return VRAM_BITMAP_BG_END if self.bitmap_mode else VRAM_TILE_BG_END

    def normalize_offset(self, offset: int) -> int:
        offset &= VRAM_WINDOW_SIZE - 1
        if offset >= VRAM_SIZE:
            offset -= VRAM_WINDOW_SIZE - VRAM_SIZE  # 0x8000：尾端 32 KiB 鏡像
        return offset

    def write_u8(self, offset: int, value: int) -> None:
        offset = self.normalize_offset(offset)
        if offset >= self.bg_end:
            return  # OBJ VRAM：8-bit 寫入忽略
        aligned = offset & ~1
        value &= 0xFF
        # 等同 [addr & ~1] = data * 0x101
        self.write_raw_u8(aligned, value)
        self.write_raw_u8(aligned + 1, value)


__all__ = ["Vram"]
