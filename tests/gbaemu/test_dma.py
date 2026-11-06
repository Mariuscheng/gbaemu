"""Phase 3：DMA0–3 暫存器、觸發、傳輸與成本（GBATEK: GBA DMA Transfers）。"""

from __future__ import annotations

import pytest

from gbaemu.bus.address_bus import AddressBus
from gbaemu.bus.io import IRQ_DMA0
from gbaemu.devices.dma import (
    ENABLE_BIT,
    REPEAT_BIT,
    SIZE_BIT,
    START_HBLANK,
    START_VBLANK,
)
from gbaemu.memory.cartridge import RomCartridge
from gbaemu.timing import PPU_HBLANK_START, PPU_VBLANK_START

DMA0_SAD = 0x040000B0
DMA0_DAD = 0x040000B4
DMA0_CNT_L = 0x040000B8
DMA0_CNT_H = 0x040000BA


def _bus(rom: bytes = bytes(0x400)) -> AddressBus:
    return AddressBus(RomCartridge(rom))


def _immediate(size32: bool = False, *, dest_control: int = 0, src_control: int = 0) -> int:
    return (
        ENABLE_BIT
        | (dest_control << 5)
        | (src_control << 7)
        | (SIZE_BIT if size32 else 0)
    )


def test_register_mapping_32_and_16bit():
    bus = _bus()
    bus.write_u32(DMA0_SAD, 0x02000100)
    bus.write_u32(DMA0_DAD, 0x02000200)
    bus.write_u16(DMA0_CNT_L, 4)
    bus.write_u16(DMA0_CNT_H, 0x8000)

    assert bus.read_u32(DMA0_SAD) == 0x02000100
    assert bus.read_u32(DMA0_DAD) == 0x02000200
    # DMAxCNT_L 只寫：硬體讀回 0（GBATEK；mgba suite「I/O read tests」）。
    assert bus.read_u16(DMA0_CNT_L) == 0
    assert bus.read_u16(DMA0_CNT_H) & ENABLE_BIT


def test_immediate_16bit_copy_and_cycles():
    bus = _bus()
    for index in range(4):
        bus.write_u16(0x02000000 + index * 2, 0x1000 + index)

    bus.write_u32(DMA0_SAD, 0x02000000)
    bus.write_u32(DMA0_DAD, 0x02000100)
    bus.write_u16(DMA0_CNT_L, 4)
    bus.write_u16(DMA0_CNT_H, _immediate())

    cycles = bus.dma.service()
    for index in range(4):
        assert bus.read_u16(0x02000100 + index * 2) == 0x1000 + index
    assert cycles == 10  # 2N + 2×(4-1)S + 2I（functional 每存取 1）
    assert not bus.dma.channels[0].active
    assert bus.read_u16(DMA0_CNT_H) & ENABLE_BIT == 0


def test_immediate_32bit_fill_fixed_destination():
    bus = _bus()
    bus.write_u32(0x02000000, 0xCAFEBABE)
    bus.write_u32(DMA0_SAD, 0x02000000)
    bus.write_u32(DMA0_DAD, 0x02000200)
    bus.write_u16(DMA0_CNT_L, 2)
    bus.write_u16(DMA0_CNT_H, _immediate(size32=True, dest_control=2, src_control=2))

    bus.dma.service()
    # dest control=2（fixed）：兩次都寫同一地址
    assert bus.read_u32(0x02000200) == 0xCAFEBABE


def test_word_count_zero_means_max():
    bus = _bus()
    bus.write_u16(DMA0_CNT_L, 0)
    bus.write_u16(DMA0_CNT_H, _immediate())
    assert bus.dma.channels[0].word_count == 0x4000

    bus = _bus()
    bus.write_u16(0x040000DE, 0)  # DMA3 CNT_L
    bus.write_u16(0x040000DE, 0)
    bus.write_u32(0x040000D4, 0x02000000)
    bus.write_u32(0x040000D8, 0x02000100)
    bus.write_u16(0x040000DC, 0)
    bus.write_u16(0x040000DE, _immediate())
    assert bus.dma.channels[3].word_count == 0x10000


def test_irq_on_completion():
    bus = _bus()
    bus.write_u16(0x04000208, 1)  # IME
    bus.write_u16(0x04000200, 0x0001)  # IE（bit0 借用作檢查）
    bus.write_u32(DMA0_SAD, 0x02000000)
    bus.write_u32(DMA0_DAD, 0x02000100)
    bus.write_u16(DMA0_CNT_L, 2)
    bus.write_u16(DMA0_CNT_H, _immediate() | (1 << 14))

    bus.dma.service()
    assert bus.read_u16(0x04000202) & IRQ_DMA0


def test_repeat_reloads_count_and_keeps_enabled():
    bus = _bus()
    bus.write_u32(DMA0_SAD, 0x02000000)
    bus.write_u32(DMA0_DAD, 0x02000100)
    bus.write_u16(DMA0_CNT_L, 2)
    bus.write_u16(DMA0_CNT_H, _immediate() | REPEAT_BIT)

    bus.dma.service()
    channel = bus.dma.channels[0]
    assert channel.active
    assert channel.word_count == 2
    assert bus.read_u16(DMA0_CNT_H) & ENABLE_BIT


def test_vblank_triggered_dma():
    bus = _bus()
    bus.write_u16(0x02000000, 0xAA55)
    bus.write_u32(DMA0_SAD, 0x02000000)
    bus.write_u32(DMA0_DAD, 0x02000100)
    bus.write_u16(DMA0_CNT_L, 1)
    bus.write_u16(
        DMA0_CNT_H, _immediate() | (START_VBLANK << 12)
    )

    assert bus.dma.pending == []
    bus.ppu.advance(PPU_VBLANK_START)
    assert bus.dma.pending == [0]
    bus.dma.service()
    assert bus.read_u16(0x02000100) == 0xAA55


def test_hblank_triggered_dma():
    bus = _bus()
    bus.write_u16(0x02000000, 0x1234)
    bus.write_u32(DMA0_SAD, 0x02000000)
    bus.write_u32(DMA0_DAD, 0x02000100)
    bus.write_u16(DMA0_CNT_L, 1)
    bus.write_u16(DMA0_CNT_H, _immediate() | (START_HBLANK << 12))

    bus.ppu.advance(PPU_HBLANK_START)
    assert bus.dma.pending == [0]
    bus.dma.service()
    assert bus.read_u16(0x02000100) == 0x1234


def test_only_dma3_can_access_rom():
    # GBATEK：DMA0-2 不能存取 Game Pak ROM。硬體是整個 transfer 不執行
    # （目的地保留原值），不是拋錯；suite「ROM load」DMA0/1/2 亦如此驗證。
    rom = bytes([0x34, 0x12]) + bytes(0x3FE)
    bus = _bus(rom)
    bus.write_u32(DMA0_SAD, 0x08000000)
    bus.write_u32(DMA0_DAD, 0x02000000)
    bus.write_u16(DMA0_CNT_L, 1)
    bus.write_u16(DMA0_CNT_H, _immediate())

    bus.dma.service()
    assert bus.read_u16(0x02000000) == 0  # 未傳輸

    bus = _bus(rom)
    bus.write_u32(0x040000D4, 0x08000000)  # DMA3 SAD
    bus.write_u32(0x040000D8, 0x02000000)  # DMA3 DAD
    bus.write_u16(0x040000DC, 1)  # DMA3 CNT_L
    bus.write_u16(0x040000DE, _immediate())  # DMA3 CNT_H
    bus.dma.service()
    assert bus.read_u16(0x02000000) == 0x1234


def test_dma_cannot_access_sram():
    # DMA0–2 不能寫入 Game Pak SRAM；寫入被忽略。
    bus = _bus()
    bus.write_u32(DMA0_SAD, 0x02000000)
    bus.write_u32(DMA0_DAD, 0x0E000000)
    bus.write_u16(DMA0_CNT_L, 1)
    bus.write_u16(DMA0_CNT_H, _immediate())

    bus.dma.service()
    assert bus.read_u8(0x0E000000) == 0xFF  # 未寫入（無 save 時 SRAM 讀回 0xFF）


def test_dma0_reads_zero_from_sram_but_dma1_reads_data():
    """mGBA：DMA0 讀 Game Pak SRAM 回 0；DMA1–3 讀到真正的 SRAM 內容。

    suite「SRAM load」的 DMA0 16/32 期待 0，DMA1/2/3 期待 SRAM 內容。
    """

    from gbaemu.memory.cartridge import SaveType

    bus = AddressBus(RomCartridge(bytes(0x400), save_type=SaveType.SRAM))
    bus.write_u8(0x0E000000, 0x47)

    bus.write_u32(DMA0_SAD, 0x0E000000)
    bus.write_u32(DMA0_DAD, 0x02000000)
    bus.write_u16(DMA0_CNT_L, 1)
    bus.write_u16(DMA0_CNT_H, _immediate(True))
    bus.dma.service()
    assert bus.read_u32(0x02000000) == 0

    bus.write_u32(0x040000BC, 0x0E000000)  # DMA1 SAD
    bus.write_u32(0x040000C0, 0x02000100)  # DMA1 DAD
    bus.write_u16(0x040000C4, 1)
    bus.write_u16(0x040000C6, _immediate(True))
    bus.dma.service()
    assert bus.read_u32(0x02000100) == 0x47474747


def test_dma0_reads_rom_from_latch_but_dma1_reads_data():
    """只有 DMA0 不能讀 Game Pak ROM；DMA1–3 讀到真正的 ROM 內容。

    suite「ROM load」：DMA0 16/32 期待 0xFACE／0xFEEDFACE（前一次搬運的
    latch 值），DMA1/2/3 則期待 ROM 的 0xBEEF／0xDEADBEEF。
    """

    rom = bytes([0xEF, 0xBE, 0xAD, 0xDE]) + bytes(0x3FC)
    bus = _bus(rom)

    # 先用 DMA0 從 EWRAM 搬 0xFEEDFACE，建立 latch。
    bus.write_u32(0x02000000, 0xFEEDFACE)
    bus.write_u32(DMA0_SAD, 0x02000000)
    bus.write_u32(DMA0_DAD, 0x02000200)
    bus.write_u16(DMA0_CNT_L, 1)
    bus.write_u16(DMA0_CNT_H, _immediate(True))
    bus.dma.service()
    assert bus.read_u32(0x02000200) == 0xFEEDFACE

    # DMA0 讀 ROM（被阻擋）→ 寫入 latch，而不是 ROM 內容 0xDEADBEEF。
    bus.write_u32(DMA0_SAD, 0x08000000)
    bus.write_u32(DMA0_DAD, 0x02000100)
    bus.write_u16(DMA0_CNT_L, 1)
    bus.write_u16(DMA0_CNT_H, _immediate(True))
    bus.dma.service()
    assert bus.read_u32(0x02000100) == 0xFEEDFACE

    # 16-bit：取 latch 對應 lane 的半字。
    bus.write_u32(DMA0_SAD, 0x08000000)
    bus.write_u32(DMA0_DAD, 0x02000100)
    bus.write_u16(DMA0_CNT_L, 1)
    bus.write_u16(DMA0_CNT_H, _immediate())
    bus.dma.service()
    assert bus.read_u16(0x02000100) == 0xFACE

    # DMA1 讀同一段 ROM → 真正的 ROM 資料。
    bus.write_u32(0x040000BC, 0x08000000)  # DMA1 SAD
    bus.write_u32(0x040000C0, 0x02000300)  # DMA1 DAD
    bus.write_u16(0x040000C4, 1)  # DMA1 CNT_L
    bus.write_u16(0x040000C6, _immediate(True))  # DMA1 CNT_H
    bus.dma.service()
    assert bus.read_u32(0x02000300) == 0xDEADBEEF


def test_disable_cancels_pending():
    bus = _bus()
    bus.write_u16(DMA0_CNT_L, 1)
    bus.write_u16(DMA0_CNT_H, _immediate() | (START_VBLANK << 12))
    bus.ppu.advance(PPU_VBLANK_START)
    assert bus.dma.pending == [0]

    bus.write_u16(DMA0_CNT_H, 0)  # 清除 enable
    assert bus.dma.pending == []
    assert bus.dma.service() == 0

def test_emulator_runs_dma_and_accounts_cycles(tmp_path):
    from gbaemu import BootMode, Emulator, EmulatorConfig

    from .cpu_helpers import arm_words, program_rom

    path = tmp_path / "dma_emu.gba"
    path.write_bytes(program_rom(arm_words(0xE1A00000, 0xEAFFFFFE)))
    emu = Emulator.from_rom(
        path, config=EmulatorConfig(boot_mode=BootMode.TEST_ROM_ONLY)
    )

    emu.memory.write_u16(0x02000000, 0x1234)
    emu.memory.write_u32(0x040000B0, 0x02000000)
    emu.memory.write_u32(0x040000B4, 0x02000100)
    emu.memory.write_u16(0x040000B8, 1)
    emu.memory.write_u16(0x04000200, 0x0100)  # IE: DMA0
    emu.memory.write_u16(0x04000208, 1)  # IME
    emu.memory.write_u16(0x040000BA, 0x8000 | (1 << 14))  # enable + IRQ

    emu.step_cycles(1)
    assert emu.memory.read_u16(0x02000100) == 0x1234
    assert emu.memory.read_u16(0x04000202) & IRQ_DMA0
    # CPU 1 cycle + DMA 2N+2I = 4 cycles
    assert emu.cycles >= 5
