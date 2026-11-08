"""GBA 記憶體區域與儲存後端。

位址與大小依 GBATEK「GBA Memory Map」與規格 3.1。這個模組只提供
「位元組容器 + 寬度存取」的 primitive；匯流排解碼、唯讀規則、8-bit
特殊寫入語意分別由 :mod:`gbaemu.bus.address_bus` 與各記憶體模組負責。
"""

from __future__ import annotations

from ..api_types import MemoryRegionInfo, MemoryRegionKind

# ---------------------------------------------------------------------------
# 位址常數（GBATEK: GBA Memory Map）
# ---------------------------------------------------------------------------

BIOS_BASE = 0x00000000
BIOS_SIZE = 0x00004000

EWRAM_BASE = 0x02000000
EWRAM_SIZE = 0x00040000

IWRAM_BASE = 0x03000000
IWRAM_SIZE = 0x00008000

IO_BASE = 0x04000000
IO_SIZE = 0x00000400

PALETTE_BASE = 0x05000000
PALETTE_SIZE = 0x00000400

VRAM_BASE = 0x06000000
VRAM_SIZE = 0x00018000  # 96 KiB
VRAM_WINDOW_SIZE = 0x00020000  # 128 KiB 位址視窗（尾端 32 KiB 鏡像）

OAM_BASE = 0x07000000
OAM_SIZE = 0x00000400

ROM_BASE = 0x08000000
ROM_WINDOW_SIZE = 0x02000000  # 每個 Game Pak 視窗 32 MiB
ROM_END = 0x0E000000  # 三個 32 MiB 視窗的排他上限

SRAM_BASE = 0x0E000000
SRAM_SIZE = 0x00010000  # 64 KiB

# VRAM 的 BG/OBJ 分界（GBATEK: GBA LCD Video Controller - VRAM）
VRAM_TILE_BG_END = 0x00010000  # Mode 0/1/2：BG 64 KiB、OBJ 32 KiB
VRAM_BITMAP_BG_END = 0x00014000  # Mode 3/4/5：BG 80 KiB、OBJ 16 KiB


class MemoryRegion:
    """一段可定址的記憶體，內部以 ``bytearray`` 保存。

    寬度存取採小端序，且允許跨越區域尾端回繞（GBA 各 RAM 區段都是鏡像）。
    子類別可覆寫 :meth:`normalize_offset` 或 :meth:`write_u8` 來描述硬體規則。
    """

    def __init__(
        self,
        kind: MemoryRegionKind,
        base: int,
        size: int,
        *,
        read_only: bool = False,
    ) -> None:
        if size <= 0:
            raise ValueError("記憶體區域大小必須為正整數")
        if base < 0:
            raise ValueError("記憶體區域基底位址不可為負")
        self.kind = kind
        self.base = base
        self.size = size
        self.read_only = read_only
        self._data = bytearray(size)

    def normalize_offset(self, offset: int) -> int:
        """把區域內 offset 映射到實際儲存位置；預設為 modulo 鏡像。"""

        return offset % self.size

    # -- 讀取 ---------------------------------------------------------------
    def read_u8(self, offset: int) -> int:
        return self._data[self.normalize_offset(offset)]

    def read_u16(self, offset: int) -> int:
        return self.read_u8(offset) | (self.read_u8(offset + 1) << 8)

    def read_u32(self, offset: int) -> int:
        return (
            self.read_u8(offset)
            | (self.read_u8(offset + 1) << 8)
            | (self.read_u8(offset + 2) << 16)
            | (self.read_u8(offset + 3) << 24)
        )

    def read_block(self, offset: int, size: int) -> bytes:
        if size < 0:
            raise ValueError("size 不可為負")
        return bytes(self.read_u8(offset + index) for index in range(size))

    # -- 寫入（硬體路徑） ---------------------------------------------------
    def write_u8(self, offset: int, value: int) -> None:
        self._data[self.normalize_offset(offset)] = value & 0xFF

    def write_u16(self, offset: int, value: int) -> None:
        # 多 byte 寫入必須繞過子類別的 8-bit 特殊規則（Palette 複製、OAM 忽略），
        # 否則 write_u16 會被拆成兩次 8-bit 寫入而語意錯誤。
        self.write_raw_u8(offset, value)
        self.write_raw_u8(offset + 1, value >> 8)

    def write_u32(self, offset: int, value: int) -> None:
        self.write_raw_u8(offset, value)
        self.write_raw_u8(offset + 1, value >> 8)
        self.write_raw_u8(offset + 2, value >> 16)
        self.write_raw_u8(offset + 3, value >> 24)

    def write_block(self, offset: int, data: bytes) -> None:
        for index, value in enumerate(data):
            self.write_u8(offset + index, value)

    # -- 除錯路徑（繞過硬體特殊寫入規則，但仍受區域邊界/鏡像限制） ----------
    def read_raw_u8(self, offset: int) -> int:
        return self._data[self.normalize_offset(offset)]

    def write_raw_u8(self, offset: int, value: int) -> None:
        self._data[self.normalize_offset(offset)] = value & 0xFF

    # -- 其他 ---------------------------------------------------------------
    def clear(self) -> None:
        self._data[:] = bytes(len(self._data))

    def to_bytes(self) -> bytes:
        return bytes(self._data)

    def load(self, data: bytes) -> None:
        if len(data) != self.size:
            raise ValueError(f"{self.kind} 需要 {self.size} bytes，得到 {len(data)}")
        self._data[:] = data

    def info(self) -> MemoryRegionInfo:
        return MemoryRegionInfo(
            kind=self.kind,
            base=self.base,
            size=self.size,
            read_only=self.read_only,
        )


__all__ = [
    "BIOS_BASE",
    "BIOS_SIZE",
    "EWRAM_BASE",
    "EWRAM_SIZE",
    "IWRAM_BASE",
    "IWRAM_SIZE",
    "IO_BASE",
    "IO_SIZE",
    "PALETTE_BASE",
    "PALETTE_SIZE",
    "VRAM_BASE",
    "VRAM_SIZE",
    "VRAM_WINDOW_SIZE",
    "OAM_BASE",
    "OAM_SIZE",
    "ROM_BASE",
    "ROM_WINDOW_SIZE",
    "ROM_END",
    "SRAM_BASE",
    "SRAM_SIZE",
    "VRAM_TILE_BG_END",
    "VRAM_BITMAP_BG_END",
    "MemoryRegion",
]
