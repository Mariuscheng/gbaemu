"""Phase 0 驗收：HLE post-boot 與 SWI dispatch table。"""

from __future__ import annotations

import pytest

from gbaemu.bus.address_bus import AddressBus
from gbaemu.cpu.arm7tdmi import Arm7Tdmi
from gbaemu.cpu.registers import MODE_IRQ, MODE_SVC
from gbaemu.errors import HleUnsupportedSwiError
from gbaemu.hle.bios_read_protect import HLE_BIOS_READ_VALUE, hle_bios_read
from gbaemu.hle.postboot import PostBootState, apply_post_boot
from gbaemu.hle.swi_table import MAX_DOCUMENTED_SWI, SWI_NAMES, SwiTable
from gbaemu.memory.cartridge import RomCartridge

from .helpers import build_rom


def _make(rom_bytes):
    bus = AddressBus(RomCartridge(rom_bytes))
    cpu = Arm7Tdmi()
    return bus, cpu


def test_postboot_state_defaults():
    state = PostBootState()
    assert state.sp_usr == 0x03007F00
    assert state.sp_irq == 0x03007FA0
    assert state.sp_svc == 0x03007FE0
    assert state.mode == 0x1F
    assert state.pc == 0x08000000
    assert state.thumb is False
    assert state.header_src == 0x08000000
    assert state.header_dst == 0x02000000
    assert state.header_size == 0xC0
    assert state.clear_irq_check == 0x03007FF8


def test_apply_post_boot_cpu_state(rom_bytes):
    bus, cpu = _make(rom_bytes)
    assert apply_post_boot(PostBootState(), cpu, bus) is True

    state = cpu.view()
    assert len(state.regs) == 16
    assert state.regs[13] == 0x03007F00
    assert state.regs[15] == 0x08000000
    assert state.mode == 0x1F
    assert state.thumb is False
    assert state.halted is False
    assert state.cycles == 0
    assert cpu.core.banked[MODE_IRQ] == (0x03007FA0, 0)
    assert cpu.core.banked[MODE_SVC] == (0x03007FE0, 0)


def test_apply_post_boot_copies_header_to_ewram(rom_bytes):
    bus, cpu = _make(rom_bytes)
    apply_post_boot(PostBootState(), cpu, bus)
    copied = bus.read_region(bus.ewram.kind)[:0xC0]
    assert copied == rom_bytes[:0xC0]
    assert bus.read_u32(0x03007FF8) == 0
    assert bus.read_u32(0x03007FFC) == 0


def test_apply_post_boot_reports_bad_complement_check():
    rom = build_rom(checksum_delta=1)
    bus, cpu = _make(rom)
    assert apply_post_boot(PostBootState(), cpu, bus) is False
    # 仍必須完成 header copy 與 CPU 狀態（不中止）
    assert bus.read_u8(0x02000000) == rom[0]
    assert cpu.view().regs[15] == 0x08000000


def test_hle_bios_read_approximation():
    assert HLE_BIOS_READ_VALUE == 0
    assert hle_bios_read(0x0000, 1) == 0
    assert hle_bios_read(0x0000, 2) == 0
    assert hle_bios_read(0x0000, 4) == 0
    with pytest.raises(ValueError):
        hle_bios_read(0x0000, 3)


def test_swi_table_covers_all_documented_swis():
    table = SwiTable()
    assert len(table.entries) == MAX_DOCUMENTED_SWI + 1 == 43
    assert [entry.number for entry in table.entries] == list(range(0x2B))
    assert table.lookup(0x00).name == "SoftReset"
    assert table.lookup(0x02).name == "Halt"
    assert table.lookup(0x06).name == "Div"
    assert table.lookup(0x0B).name == "CpuSet"
    assert table.lookup(0x2A).name == "SoundGetJumpList"
    assert set(SWI_NAMES) == set(range(0x2B))
    assert table.implemented_numbers() == ()


def test_invalid_swi_always_raises_even_in_lenient_mode():
    for number in (0x2B, 0x2C, 0xFF):
        with pytest.raises(HleUnsupportedSwiError):
            SwiTable().dispatch(number)
        with pytest.raises(HleUnsupportedSwiError):
            SwiTable(strict=False).dispatch(number)


def test_unimplemented_documented_swi_strict_vs_lenient():
    with pytest.raises(HleUnsupportedSwiError):
        SwiTable(strict=True).dispatch(0x2A)
    SwiTable(strict=False).dispatch(0x2A)  # 不 raise


def test_handler_registration_and_dispatch():
    calls = []
    table = SwiTable(handlers={0x06: calls.append}, strict=True)
    assert table.lookup(0x06).implemented is True
    assert table.implemented_numbers() == (0x06,)
    table.dispatch(0x06, "context")
    assert calls == ["context"]
    # 未註冊的 SWI 在 strict 模式仍 raise
    with pytest.raises(HleUnsupportedSwiError):
        table.dispatch(0x07)


def test_swi_number_validation():
    table = SwiTable(strict=False)
    for bad in (-1, 0x100):
        with pytest.raises(ValueError):
            table.dispatch(bad)
    with pytest.raises(ValueError):
        table.dispatch("0x06")  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        SwiTable(handlers={0x2B: lambda context: None})
