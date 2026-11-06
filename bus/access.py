"""匯流排存取寬度與對齊輔助。

GBATEK「GBA Memory Map - Address Bus Width and CPU Read/Write Access Widths」：
16-bit 存取忽略 A0、32-bit 存取忽略 A1:A0；未對齊的 32-bit LDR 由 CPU 將讀出的
word 向右旋轉。匯流排本身先做寬度對齊，CPU 層（Phase 1）再套用旋轉。
"""

from __future__ import annotations

from enum import IntEnum


class AccessWidth(IntEnum):
    BYTE = 1
    HALFWORD = 2
    WORD = 4

    @property
    def size(self) -> int:
        return int(self)


def align_address(address: int, width: int) -> int:
    """依存取寬度遮蔽低位元（硬體忽略未對齊的位址線）。"""

    if width not in (1, 2, 4):
        raise ValueError(f"不支援的存取寬度：{width}")
    if width == 1:
        return address
    return address & ~(width - 1)


def rotate_right_32(value: int, shift: int) -> int:
    """32-bit rotate right；``shift`` 會被正規化到 0..31。"""

    value &= 0xFFFFFFFF
    shift &= 31
    if shift == 0:
        return value
    return ((value >> shift) | (value << (32 - shift))) & 0xFFFFFFFF


def unaligned_word_rotate(value: int, address: int) -> int:
    """模擬 GBA 未對齊 ``LDR`` 的讀值旋轉（rotation = (address & 3) * 8）。"""

    return rotate_right_32(value, (address & 0x3) * 8)


# ---------------------------------------------------------------------------
# 存取成本（規格 §3.6.5；GBATEK: GBA Memory Map - Address Bus Width and
# CPU Read/Write Access Widths；4000204h - WAITCNT）
# ---------------------------------------------------------------------------

WAITCNT_OFFSET = 0x204  # 0x04000204 在 I/O raw bytes 中的 offset

# WAITCNT 欄位對應的 wait state 數（GBATEK：欄位值 0..3 = 4,3,2,8 wait）
_FIRST_CYCLES = (5, 4, 3, 9)
_WS0_SECOND = (3, 2)
_WS1_SECOND = (5, 2)
_WS2_SECOND = (9, 2)


def waitcnt_from_io(io: bytes | bytearray) -> int:
    """從 I/O raw bytes 取出 16-bit WAITCNT（little-endian）。"""

    return io[WAITCNT_OFFSET] | (io[WAITCNT_OFFSET + 1] << 8)


def access_cycles(
    address: int,
    width: int,
    sequential: bool,
    waitcnt: int = 0,
    *,
    enforce_128k_boundary: bool = True,
) -> int:
    """回傳單次存取的 cycle 數（含基本 cycle 與 WAITCNT 的 N／S wait）。

    * GamePak ROM：N = 首次存取、S = 循序；32-bit 拆成兩次 16-bit（N+S 或 S+S）。
    * 每個 128 KiB ROM 區塊的第一個存取強制 N。
    * SRAM／Flash 一律 N 週期（只支援 8-bit）。
    * EWRAM 3/3/6、Palette／VRAM 1/1/2、其他 1。

    ``width`` 為 1／2／4 bytes；``waitcnt`` 為 0x04000204 的 16-bit 值。
    """

    if width not in (1, 2, 4):
        raise ValueError(f"不支援的存取寬度：{width}")
    if width > 1:
        address &= ~(width - 1)
    address &= 0xFFFFFFFF
    page = address >> 24

    if 0x08 <= page <= 0x0D:  # GamePak ROM（WS0／WS1／WS2 鏡像）
        if enforce_128k_boundary and (address & 0x1FFFF) == 0:
            sequential = False
        if page in (0x0A, 0x0B):  # WS1
            first = _FIRST_CYCLES[(waitcnt >> 5) & 0x3]
            second = _WS1_SECOND[(waitcnt >> 7) & 0x1]
        elif page in (0x0C, 0x0D):  # WS2
            first = _FIRST_CYCLES[(waitcnt >> 8) & 0x3]
            second = _WS2_SECOND[(waitcnt >> 10) & 0x1]
        else:  # WS0（0x08／0x09）
            first = _FIRST_CYCLES[(waitcnt >> 2) & 0x3]
            second = _WS0_SECOND[(waitcnt >> 4) & 0x1]
        if width == 4:
            return (second + second) if sequential else (first + second)
        return second if sequential else first

    if page in (0x0E, 0x0F):  # GamePak SRAM／Flash：一律 N 週期
        return _FIRST_CYCLES[waitcnt & 0x3]

    if page == 0x02:  # EWRAM（16-bit bus）
        return 6 if width == 4 else 3

    if page in (0x05, 0x06):  # Palette／VRAM
        return 2 if width == 4 else 1

    return 1  # BIOS／IWRAM／I/O／OAM／未映射


__all__ = [
    "AccessWidth",
    "align_address",
    "rotate_right_32",
    "unaligned_word_rotate",
    "WAITCNT_OFFSET",
    "waitcnt_from_io",
    "access_cycles",
]
