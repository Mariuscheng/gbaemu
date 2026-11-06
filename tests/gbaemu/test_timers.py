"""Phase 3：Timers 0–3 的 reload／prescaler／cascade／IRQ（GBATEK: GBA Timers）。"""

from __future__ import annotations

from gbaemu.bus.address_bus import AddressBus
from gbaemu.bus.io import IRQ_TIMER0
from gbaemu.memory.cartridge import RomCartridge

TM0_CNT_L = 0x04000100
TM0_CNT_H = 0x04000102
TM1_CNT_L = 0x04000104
TM1_CNT_H = 0x04000106


def _bus() -> AddressBus:
    return AddressBus(RomCartridge(bytes(0x400)))


def _start(value: int) -> int:
    return 0x80 | value


def test_reload_write_does_not_change_counter():
    bus = _bus()
    bus.write_u16(TM0_CNT_L, 0x1234)
    assert bus.read_u16(TM0_CNT_L) == 0  # counter 尚未啟動
    bus.write_u16(TM0_CNT_H, _start(0))
    assert bus.read_u16(TM0_CNT_L) == 0x1234  # start 0→1 時載入 reload


def test_free_running_counter():
    bus = _bus()
    bus.write_u16(TM0_CNT_L, 0x0010)
    bus.write_u16(TM0_CNT_H, _start(0))
    bus.timers.tick(5)
    assert bus.read_u16(TM0_CNT_L) == 0x0015


def test_prescaler_f64():
    bus = _bus()
    bus.write_u16(TM0_CNT_L, 0)
    bus.write_u16(TM0_CNT_H, _start(1))  # prescaler F/64
    bus.timers.tick(63)
    assert bus.read_u16(TM0_CNT_L) == 0
    bus.timers.tick(1)
    assert bus.read_u16(TM0_CNT_L) == 1
    bus.timers.tick(128)
    assert bus.read_u16(TM0_CNT_L) == 3


def test_overflow_reloads_and_irq():
    bus = _bus()
    bus.write_u16(0x04000208, 1)  # IME
    bus.write_u16(0x04000200, IRQ_TIMER0)  # IE
    bus.write_u16(TM0_CNT_L, 0xFFFE)
    bus.write_u16(TM0_CNT_H, _start(0x40))  # IRQ on overflow

    bus.timers.tick(1)
    assert bus.read_u16(TM0_CNT_L) == 0xFFFF
    assert not (bus.read_u16(0x04000202) & IRQ_TIMER0)

    bus.timers.tick(1)
    assert bus.read_u16(TM0_CNT_L) == 0xFFFE  # reload
    assert bus.read_u16(0x04000202) & IRQ_TIMER0


def test_stop_freezes_counter():
    bus = _bus()
    bus.write_u16(TM0_CNT_L, 0)
    bus.write_u16(TM0_CNT_H, _start(0))
    bus.timers.tick(10)
    bus.write_u16(TM0_CNT_H, 0)  # stop
    bus.timers.tick(10)
    assert bus.read_u16(TM0_CNT_L) == 10


def test_cascade_ignores_prescaler():
    bus = _bus()
    bus.write_u16(TM0_CNT_L, 0xFFFF)
    bus.write_u16(TM0_CNT_H, _start(0))
    bus.write_u16(TM1_CNT_L, 0)
    bus.write_u16(TM1_CNT_H, _start(0x04 | 1))  # cascade + prescaler（被忽略）

    bus.timers.tick(1)  # TM0 overflow → TM1 +1
    assert bus.read_u16(TM1_CNT_L) == 1

    bus.timers.tick(1)  # TM0 再溢位一次；TM1 的 prescaler 被忽略
    assert bus.read_u16(TM1_CNT_L) == 2


def test_32bit_write_loads_reload_and_starts():
    bus = _bus()
    # 低半 word = CNT_L(reload)=0x0005；高半 word = CNT_H=0x0080（start）
    bus.write_u32(TM0_CNT_L, 0x00800005)
    assert bus.read_u16(TM0_CNT_L) == 5
    assert bus.read_u16(TM0_CNT_H) == 0x0080


def test_timer_irq_reaches_cpu(tmp_path):
    from gbaemu import BootMode, Emulator, EmulatorConfig

    from .cpu_helpers import arm_words, program_rom

    path = tmp_path / "timer_irq.gba"
    path.write_bytes(program_rom(arm_words(0xE1A00000, 0xE1A00000, 0xEAFFFFFE)))
    emu = Emulator.from_rom(
        path, config=EmulatorConfig(boot_mode=BootMode.TEST_ROM_ONLY)
    )

    emu._cpu.regs.cpsr &= ~0x80  # TEST_ROM_ONLY 預設遮罩 IRQ；本測試要能進場
    emu.memory.write_u16(0x04000200, IRQ_TIMER0)  # IE
    emu.memory.write_u16(0x04000208, 1)  # IME
    emu.memory.write_u16(TM0_CNT_L, 0xFFFE)
    emu.memory.write_u16(TM0_CNT_H, _start(0x40))

    emu.step_cycles(2)  # 兩條 NOP → 2 cycles → timer overflow（IF 拉起）
    assert emu.memory.read_u16(0x04000202) & IRQ_TIMER0
    emu.step_cycles(2)  # IRQ pipeline 延遲
    emu.step_cycles(2)  # 延遲到點
    assert emu.cpu.state().mode == 0x12  # IRQ mode
