"""進階 HLE 啟動：PostBootState 與 BIOS 完成後的機器狀態。

規格 2.1.1。實作只依 GBATEK 文件化行為（BIOS Default Settings／Interrupt
default memory usage），不反組譯或內嵌 Nintendo BIOS。

Phase 0 刻意不套用下列「真 BIOS 也會留下」的狀態，因為規格 2.1.1 未列出且
需要 Phase 1/2 的 CPU／I/O 基礎設施；已記錄於 ``TODO.md`` 的 Open Questions：

* r3 = BIOS checksum ``0xBAAE187F``（既有 ``pygba/core/bios.py`` 經真 BIOS 對照）
* r14 = ``0x08000000``
* POSTFLG（``0x04000300``）= 1
* DISPCNT forced blank（``0x04000000`` = 0x0080）
"""

from __future__ import annotations

from dataclasses import dataclass

from ..log import get_logger
from ..memory.cartridge import HEADER_SIZE, compute_complement_check

logger = get_logger("hle.postboot")


@dataclass(frozen=True, slots=True)
class PostBootState:
    """HLE 啟動完成時應達到的狀態（規格 2.1.1）。"""

    sp_usr: int = 0x03007F00
    sp_irq: int = 0x03007FA0
    sp_svc: int = 0x03007FE0
    mode: int = 0x1F  # System mode
    pc: int = 0x08000000
    thumb: bool = False
    header_src: int = 0x08000000
    header_dst: int = 0x02000000
    header_size: int = 0xC0
    clear_irq_check: int = 0x03007FF8  # 與 0x03007FFC 一併清零


def apply_post_boot(state: PostBootState, cpu, bus) -> bool:
    """套用 post-boot 狀態並回傳 header complement check 是否通過。

    * CPU：SP、mode、PC、banked SP。
    * BIOS 會把 ROM header（0xC0 bytes）複製到 EWRAM ``0x02000000``。
    * ``0x03007FF8``（Interrupt Check Flag）與 ``0x03007FFC``（user IRQ handler
      pointer）清零。
    * complement check 失敗只記錄 warning，不中止（真硬體寬鬆行為；測試 ROM）。
    """

    cpu.apply_post_boot(state)

    # BIOS 開機 default：BG2/BG3 affine matrix = identity（PA=PD=0x0100）。
    # 冇寫呢兩個 register 的遊戲（例如 LeafGreen 用 BG2 畫 Oak）靠 BIOS
    # 留低嘅預設；mGBA GBAIOInit 同款。
    for offset in (0x20, 0x26, 0x30, 0x36):
        bus.write_u16(0x04000000 + offset, 0x0100)

    header = bytearray()
    for index in range(state.header_size):
        value = bus.peek_u8(state.header_src + index) & 0xFF
        header.append(value)
        bus.write_u8(state.header_dst + index, value)

    checksum_ok = False
    if len(header) >= HEADER_SIZE:
        calculated = compute_complement_check(bytes(header))
        stored = header[0xBD]
        checksum_ok = calculated == stored
        if not checksum_ok:
            logger.warning(
                "ROM header complement check 失敗：stored=0x%02X calculated=0x%02X "
                "（HLE 繼續啟動，供測試 ROM 使用）",
                stored,
                calculated,
            )
    else:
        logger.warning(
            "header_size=%d 小於 0xC0，無法驗證 complement check",
            state.header_size,
        )

    bus.write_u32(state.clear_irq_check, 0)
    bus.write_u32(state.clear_irq_check + 4, 0)
    return checksum_ok


__all__ = ["PostBootState", "apply_post_boot"]
