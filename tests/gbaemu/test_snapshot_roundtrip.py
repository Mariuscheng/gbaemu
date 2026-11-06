"""Phase 3：完整 snapshot round-trip（規格 5.7 九段 payload）。"""

from __future__ import annotations

from gbaemu import BootMode, Emulator, EmulatorConfig, MemoryRegionKind
from gbaemu.errors import SnapshotCorruptError, SnapshotRomMismatchError

from .cpu_helpers import arm_words
from .helpers import build_rom

NOP = 0xE1A00000
B_SELF = 0xEAFFFFFE
SRAM_ID = b"SRAM_V123\0\0\0\0"

REGIONS = (
    MemoryRegionKind.EWRAM,
    MemoryRegionKind.IWRAM,
    MemoryRegionKind.PALETTE,
    MemoryRegionKind.VRAM,
    MemoryRegionKind.OAM,
    MemoryRegionKind.SRAM,
)


def _emu(tmp_path, *, save: bool = False) -> Emulator:
    rom = bytearray(build_rom(size=0x1000))
    rom[:8] = arm_words(NOP, B_SELF)
    if save:
        rom[0x300 : 0x300 + len(SRAM_ID)] = SRAM_ID
    path = tmp_path / "snap.gba"
    path.write_bytes(bytes(rom))
    return Emulator.from_rom(
        path, config=EmulatorConfig(boot_mode=BootMode.TEST_ROM_ONLY)
    )


def _state(emu: Emulator):
    return (
        emu.cpu.state(),
        emu.frame_index,
        emu.cycles,
        tuple(emu.memory.read_region(kind) for kind in REGIONS),
        emu._bus.timers.states[0].counter,
        emu._bus.io_registers.interrupts,
    )


def test_save_state_roundtrip(tmp_path):
    emu = _emu(tmp_path)
    emu.step_cycles(80)

    emu.memory.write_u8(0x02000100, 0x5A)
    emu.memory.write_u16(0x04000100, 0x1234)
    emu._bus.write_u16(0x04000102, 0x80)  # 啟動 timer
    emu.memory.write_u16(0x04000200, 0x0003)
    emu.memory.write_u16(0x04000208, 1)
    emu.memory.write_u16(0x04000202, 0x0001)

    data = emu.save_state()
    before = _state(emu)

    emu.step_cycles(300)
    emu.memory.write_u8(0x02000100, 0)
    emu.memory.write_u16(0x04000202, 0x0000)
    assert _state(emu) != before

    emu.load_state(data)
    assert _state(emu) == before


def test_restored_snapshot_steps_identically(tmp_path):
    emu = _emu(tmp_path)
    emu.step_cycles(40)
    data = emu.save_state()

    other = _emu(tmp_path)
    other.load_state(data)

    emu.step_cycles(200)
    other.step_cycles(200)
    assert emu.cpu.state() == other.cpu.state()
    assert emu.frame_index == other.frame_index
    assert emu.cycles == other.cycles
    for kind in REGIONS:
        assert emu.memory.read_region(kind) == other.memory.read_region(kind)


def test_snapshot_keeps_ppu_bg_registers(tmp_path):
    """BGxCNT／WININ／BLDCNT 只存在 PPU 快取，snapshot 必須一併保存。

    這區的 I/O 寫入原本只進 `Ppu._regs`、不進 `IoRegisters._bytes`，所以
    存檔／讀檔後 renderer 會拿到全 0（畫面空白或錯層）。
    """

    emu = _emu(tmp_path)
    emu.step_cycles(40)
    emu.memory.write_u16(0x04000008, 0x1F08)  # BG0CNT
    emu.memory.write_u16(0x0400000A, 0x1D04)  # BG1CNT
    emu.memory.write_u16(0x04000048, 0x1F3F)  # WININ
    emu.memory.write_u16(0x04000050, 0x20C0)  # BLDCNT
    emu.memory.write_u16(0x04000052, 0x0810)  # BLDALPHA
    data = emu.save_state()

    other = _emu(tmp_path)
    other.load_state(data)
    for address, expected in (
        (0x04000008, 0x1F08),
        (0x0400000A, 0x1D04),
        (0x04000048, 0x1F3F),
        (0x04000050, 0x20C0),
        (0x04000052, 0x0810),
    ):
        assert other.memory.read_u16(address) == expected


def test_snapshot_includes_cartridge_save(tmp_path):
    emu = _emu(tmp_path, save=True)
    emu.memory.write_u8(0x0E000010, 0x77)
    data = emu.save_state()

    emu.memory.write_u8(0x0E000010, 0x00)
    assert emu.memory.read_u8(0x0E000010) == 0x00

    emu.load_state(data)
    assert emu.memory.read_u8(0x0E000010) == 0x77


def test_snapshot_rejects_wrong_rom_and_corruption(tmp_path):
    emu = _emu(tmp_path)
    data = emu.save_state()

    other_path = tmp_path / "other.gba"
    other = bytearray(build_rom(size=0x1000))
    other[:4] = arm_words(0xEAFFFFFE)
    other[0x20] = 0x42
    other_path.write_bytes(bytes(other))
    foreign = Emulator.from_rom(
        other_path, config=EmulatorConfig(boot_mode=BootMode.TEST_ROM_ONLY)
    )
    try:
        foreign.load_state(data)
    except SnapshotRomMismatchError:
        pass
    else:
        raise AssertionError("SnapshotRomMismatchError 未觸發")

    corrupted = bytearray(data)
    corrupted[-1] ^= 0xFF
    try:
        emu.load_state(bytes(corrupted))
    except SnapshotCorruptError:
        pass
    else:
        raise AssertionError("SnapshotCorruptError 未觸發")
