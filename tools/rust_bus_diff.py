"""G2 bus/memory differential：Python ``AddressBus`` vs Rust ``cpu_probe``。

用法（repo root）：

    cargo build --manifest-path crates/gbaemu-core/Cargo.toml --bin cpu_probe
    .\\venv\\Scripts\\python.exe tools/rust_bus_diff.py

只驗證 memory map／mirror／寬度／open bus 等 bus 層語意；IO device、DMA、
timer 與 PPU 仍由 Python reference 作 oracle，尚未納入此腳本。
"""

from __future__ import annotations

import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROBE = ROOT / "crates" / "gbaemu-core" / "target" / "debug" / "cpu_probe.exe"

sys.path.insert(0, str(ROOT.parent))

import gbaemu  # noqa: E402

# 若 repo 根目錄不是 sys.path 首位，import 會落到 site-packages 的舊安裝副本，
# diff 就變成「舊 Python vs 新 Rust」，因此在此硬性檢查來源。
if Path(gbaemu.__file__).resolve().parent != ROOT:
    raise SystemExit(f"載入非 repo 的 gbaemu：{gbaemu.__file__}（預期 {ROOT}）")

from gbaemu.bus.address_bus import AddressBus  # noqa: E402
from gbaemu.memory.cartridge import RomCartridge  # noqa: E402


def make_rom() -> bytes:
    return bytes((index * 7 + 3) & 0xFF for index in range(0x4000))


@dataclass
class BusCase:
    name: str
    writes: list[tuple[int, int, int]] = field(default_factory=list)  # width, addr, value
    reads: list[tuple[int, int]] = field(default_factory=list)  # width, addr
    open_bus: int | None = None
    vram_bitmap: bool = False
    if_set: int = 0
    dma_service: bool = False
    ticks: int = 0
    keyinput: int | None = None
    poll_keys: bool = False
    fifo_check: bool = False
    sound: bool = False
    pcm_check: bool = False


class Probe:
    def __init__(self) -> None:
        self.proc = subprocess.Popen(
            [str(PROBE)],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
        )

    def command(self, line: str) -> str:
        assert self.proc.stdin is not None
        self.proc.stdin.write(line + "\n")
        self.proc.stdin.flush()
        assert self.proc.stdout is not None
        output = self.proc.stdout.readline().strip()
        if not output:
            raise RuntimeError(f"probe closed after {line!r}")
        return output

    def close(self) -> None:
        try:
            self.command("quit")
        except Exception:
            pass
        self.proc.kill()


def fnv1a64(data: bytes) -> int:
    value = 0xCBF29CE484222325
    for byte in data:
        value ^= byte
        value = (value * 0x100000001B3) & 0xFFFFFFFFFFFFFFFF
    return value


def _python_run(case: BusCase) -> dict[tuple[int, int], int]:
    bus = AddressBus(RomCartridge(make_rom()))
    if case.open_bus is not None:
        bus.open_bus = case.open_bus
    if case.keyinput is not None:
        class Keypad:
            keyinput_mask = case.keyinput

        bus.io_registers.keypad = Keypad()
    if case.sound:
        bus.sound.enabled = True
    if case.vram_bitmap:
        bus.set_vram_bitmap_mode(True)
    if case.if_set:
        bus.io_registers.request_irq(case.if_set)
    for width, address, value in case.writes:
        if width == 8:
            bus.write_u8(address, value)
        elif width == 16:
            bus.write_u16(address, value)
        else:
            bus.write_u32(address, value)
    if case.ticks:
        bus.tick(case.ticks)
    if case.dma_service:
        bus.dma.service()
    if case.poll_keys:
        bus.io_registers.poll_keypad()
    result = {}
    for width, address in case.reads:
        if width == 8:
            value = bus.read_u8(address)
        elif width == 16:
            value = bus.read_u16(address)
        else:
            value = bus.read_u32(address)
        result[(width, address)] = value
    if case.fifo_check:
        result[(-1, 0)] = len(bus.sound.fifo_a)
        result[(-1, 1)] = len(bus.sound.fifo_b)
        result[(-1, 2)] = bus.dma.channels[1].source & 0xFFFFFFFF
        result[(-1, 3)] = bus.dma.channels[2].source & 0xFFFFFFFF
    if case.pcm_check:
        result[(-2, 0)] = fnv1a64(bus.sound.take_pcm())
    return result


def _rust_run(probe: Probe, case: BusCase) -> dict[tuple[int, int], int]:
    assert probe.command("reset") == "ok"
    assert probe.command("romfill") == "ok"
    if case.sound:
        assert probe.command("soundon 1") == "ok"
    if case.open_bus is not None:
        assert probe.command(f"openbus {case.open_bus:08x}") == "ok"
    if case.vram_bitmap:
        assert probe.command("vrammode 1") == "ok"
    if case.if_set:
        assert probe.command(f"ifset {case.if_set:04x}") == "ok"
    if case.keyinput is not None:
        assert probe.command(f"keyinput {case.keyinput & 0x3FF:04x}") == "ok"
    for width, address, value in case.writes:
        assert probe.command(f"mem{width} {address:08x} {value:x}") == "ok"
    if case.ticks:
        assert probe.command(f"tick {case.ticks}") == "ok"
    if case.dma_service:
        assert probe.command("dmaservice").startswith("ok")
    if case.poll_keys:
        assert probe.command("pollkeys") == "ok"
    result = {}
    for width, address in case.reads:
        output = probe.command(f"peek{width} {address:08x}")
        result[(width, address)] = int(output.split("value=")[1], 16)
    if case.fifo_check:
        fields = dict(part.split("=", 1) for part in probe.command("fifostate").split()[1:])
        result[(-1, 0)] = int(fields["a"])
        result[(-1, 1)] = int(fields["b"])
        result[(-1, 2)] = int(fields["src1"], 16)
        result[(-1, 3)] = int(fields["src2"], 16)
    if case.pcm_check:
        hex_data = probe.command("takeaudio").split("hex=")[1]
        result[(-2, 0)] = fnv1a64(bytes.fromhex(hex_data))
    return result


def main() -> int:
    if not PROBE.exists():
        print(f"missing probe: {PROBE}")
        print("run: cargo build --manifest-path crates/gbaemu-core/Cargo.toml --bin cpu_probe")
        return 2

    cases = [
        BusCase(
            "ewram_widths",
            writes=[
                (32, 0x0200_0000, 0x1122_3344),
                (16, 0x0200_0100, 0xAABB),
                (8, 0x0200_0200, 0xCC),
            ],
            reads=[
                (32, 0x0200_0000),
                (16, 0x0200_0100),
                (8, 0x0200_0200),
            ],
        ),
        BusCase(
            "ewram_mirror",
            writes=[(32, 0x0200_0004, 0xDEAD_BEEF)],
            reads=[(32, 0x0200_0004), (32, 0x0204_0004), (32, 0x02FF_FF04)],
        ),
        BusCase(
            "iwram_mirror",
            writes=[(32, 0x0300_0010, 0xCAFE_F00D)],
            reads=[(32, 0x0300_0010), (32, 0x0300_8010), (32, 0x03FF_FF10)],
        ),
        BusCase(
            "palette",
            writes=[(16, 0x0500_0000, 0x7FFF)],
            reads=[(16, 0x0500_0000), (8, 0x0500_0000), (8, 0x0500_0001)],
        ),
        BusCase(
            "vram_and_tail_mirror",
            writes=[(16, 0x0600_0000, 0xBEEF)],
            reads=[(16, 0x0600_0000), (16, 0x0601_8000), (16, 0x0601_7FFE)],
        ),
        BusCase(
            "vram_8bit_bg_duplicate",
            writes=[(8, 0x0600_0000, 0xAB)],
            reads=[
                (8, 0x0600_0000),
                (8, 0x0600_0001),
                (16, 0x0600_0000),
            ],
        ),
        BusCase(
            "vram_8bit_obj_ignored",
            writes=[(8, 0x0601_0000, 0xCD)],
            reads=[(8, 0x0601_0000), (8, 0x0601_0001)],
        ),
        BusCase(
            "vram_bitmap_8bit_bg_extends",
            writes=[(8, 0x0601_0000, 0x5A)],
            reads=[(8, 0x0601_0000), (8, 0x0601_0001)],
            vram_bitmap=True,
        ),
        BusCase(
            "vram_16bit_does_not_duplicate",
            writes=[(16, 0x0600_0000, 0x1234)],
            reads=[(16, 0x0600_0000), (8, 0x0600_0001)],
        ),
        BusCase(
            "oam",
            writes=[(16, 0x0700_0000, 0x1234)],
            reads=[(16, 0x0700_0000), (8, 0x0700_0001)],
        ),
        BusCase(
            "rom_mirror_and_write_protect",
            writes=[(8, 0x0800_0000, 0xAA)],
            reads=[
                (32, 0x0800_0000),
                (32, 0x0800_0010),
                (32, 0x0A00_0010),
                (32, 0x0C00_0010),
            ],
        ),
        BusCase(
            "sram",
            writes=[(8, 0x0E00_0000, 0x5A)],
            reads=[(8, 0x0E00_0000), (8, 0x0E00_0001)],
        ),
        BusCase(
            "open_bus_widths",
            open_bus=0x1122_3344,
            reads=[
                (8, 0x1000_0000),
                (8, 0x1000_0001),
                (8, 0x1000_0002),
                (8, 0x1000_0003),
                (16, 0x1000_0002),
                (32, 0x1000_0000),
            ],
        ),
        BusCase(
            "unmapped_write_ignored",
            writes=[(32, 0x1000_0000, 0xFFFF_FFFF)],
            reads=[(32, 0x1000_0000)],
            open_bus=0,
        ),
        BusCase(
            "io_interrupt_defaults",
            reads=[
                (16, 0x0400_0200),
                (16, 0x0400_0202),
                (16, 0x0400_0208),
                (16, 0x0400_0130),
            ],
        ),
        BusCase(
            "io_ie_mask",
            writes=[(16, 0x0400_0200, 0xFFFF)],
            reads=[
                (16, 0x0400_0200),
                (8, 0x0400_0200),
                (8, 0x0400_0201),
            ],
        ),
        BusCase(
            "io_if_write_one_clear",
            writes=[(16, 0x0400_0202, 0x0003)],
            reads=[(16, 0x0400_0202), (8, 0x0400_0202)],
            if_set=0x0005,
        ),
        BusCase(
            "io_if_byte_clear",
            writes=[(8, 0x0400_0203, 0x03)],
            reads=[(16, 0x0400_0202)],
            if_set=0x0303,
        ),
        BusCase(
            "io_ime_bit0",
            writes=[(16, 0x0400_0208, 0xFFFF), (8, 0x0400_0209, 0x01)],
            reads=[(16, 0x0400_0208), (8, 0x0400_0208), (8, 0x0400_0209)],
        ),
        BusCase(
            "io_keyinput_readonly",
            writes=[(16, 0x0400_0130, 0x0000)],
            reads=[(16, 0x0400_0130), (8, 0x0400_0131)],
        ),
        BusCase(
            "io_waitcnt_and_keycnt",
            writes=[(16, 0x0400_0204, 0x4317), (16, 0x0400_0132, 0xC3FF)],
            reads=[(16, 0x0400_0204), (16, 0x0400_0132)],
        ),
        BusCase(
            "io_vcount_readonly",
            writes=[(16, 0x0400_0006, 0x1234)],
            reads=[(16, 0x0400_0006)],
        ),
        BusCase(
            "io_dispcnt_raw",
            writes=[(16, 0x0400_0000, 0x1234)],
            reads=[(16, 0x0400_0000), (8, 0x0400_0001)],
        ),
        BusCase(
            "io_dispstat_enables",
            writes=[(16, 0x0400_0004, 0x0038)],
            reads=[(16, 0x0400_0004)],
        ),
        BusCase(
            "dma_register_words",
            writes=[
                (32, 0x0400_00B0, 0x1234_5678),
                (32, 0x0400_00B4, 0x9ABC_DEF0),
                (16, 0x0400_00B8, 0x0010),
                (16, 0x0400_00BA, 0x8540),
            ],
            reads=[
                (32, 0x0400_00B0),
                (32, 0x0400_00B4),
                (16, 0x0400_00B8),
                (16, 0x0400_00BA),
            ],
        ),
        BusCase(
            "dma_immediate_16bit",
            writes=[
                (16, 0x0200_0000, 0x1000),
                (16, 0x0200_0002, 0x1001),
                (16, 0x0200_0004, 0x1002),
                (16, 0x0200_0006, 0x1003),
                (32, 0x0400_00B0, 0x0200_0000),
                (32, 0x0400_00B4, 0x0200_0100),
                (16, 0x0400_00B8, 4),
                (16, 0x0400_00BA, 0x8000),
            ],
            reads=[
                (16, 0x0200_0100),
                (16, 0x0200_0102),
                (16, 0x0200_0104),
                (16, 0x0200_0106),
                (16, 0x0400_00BA),
                (32, 0x0400_00B0),
                (32, 0x0400_00B4),
            ],
            dma_service=True,
        ),
        BusCase(
            "dma_32bit_fixed_destination",
            writes=[
                (32, 0x0200_0000, 0xCAFE_BABE),
                (32, 0x0400_00B0, 0x0200_0000),
                (32, 0x0400_00B4, 0x0200_0200),
                (16, 0x0400_00B8, 2),
                (16, 0x0400_00BA, 0x8540),
            ],
            reads=[(32, 0x0200_0200), (16, 0x0400_00BA)],
            dma_service=True,
        ),
        BusCase(
            "dma_irq_on_completion",
            writes=[
                (32, 0x0200_0000, 0x1111_1111),
                (32, 0x0200_0004, 0x2222_2222),
                (32, 0x0400_00B0, 0x0200_0000),
                (32, 0x0400_00B4, 0x0200_0100),
                (16, 0x0400_00B8, 2),
                (16, 0x0400_00BA, 0xC000),
            ],
            reads=[(16, 0x0400_0202), (16, 0x0400_00BA)],
            dma_service=True,
        ),
        BusCase(
            "dma_repeat",
            writes=[
                (16, 0x0200_0000, 0xAAAA),
                (16, 0x0200_0002, 0xBBBB),
                (32, 0x0400_00B0, 0x0200_0000),
                (32, 0x0400_00B4, 0x0200_0100),
                (16, 0x0400_00B8, 2),
                (16, 0x0400_00BA, 0x8200),
            ],
            reads=[
                (16, 0x0200_0100),
                (16, 0x0200_0102),
                (16, 0x0400_00BA),
            ],
            dma_service=True,
        ),
        BusCase(
            "dma_disable_before_service",
            writes=[
                (16, 0x0200_0000, 0x1234),
                (32, 0x0400_00B0, 0x0200_0000),
                (32, 0x0400_00B4, 0x0200_0100),
                (16, 0x0400_00B8, 4),
                (16, 0x0400_00BA, 0x8000),
                (16, 0x0400_00BA, 0x0000),
            ],
            reads=[(16, 0x0200_0100), (16, 0x0400_00BA)],
            dma_service=True,
        ),
        BusCase(
            "timer_reload_and_control_read",
            writes=[
                (16, 0x0400_0100, 0x1234),
                (16, 0x0400_0102, 0x0000),
            ],
            reads=[(16, 0x0400_0100), (16, 0x0400_0102)],
        ),
        BusCase(
            "timer_start_counts",
            writes=[
                (16, 0x0400_0100, 0x1000),
                (16, 0x0400_0102, 0x0080),
            ],
            reads=[(16, 0x0400_0100), (8, 0x0400_0101)],
            ticks=10,
        ),
        BusCase(
            "timer_prescaler_64",
            writes=[
                (16, 0x0400_0100, 0x0000),
                (16, 0x0400_0102, 0x0081),
            ],
            reads=[(16, 0x0400_0100)],
            ticks=128,
        ),
        BusCase(
            "timer_overflow_irq",
            writes=[
                (16, 0x0400_0100, 0xFFFE),
                (16, 0x0400_0102, 0x00C0),
            ],
            reads=[(16, 0x0400_0100), (16, 0x0400_0202)],
            ticks=2,
        ),
        BusCase(
            "timer_cascade",
            writes=[
                (16, 0x0400_0100, 0xFFFF),
                (16, 0x0400_0102, 0x0080),
                (16, 0x0400_0104, 0x0000),
                (16, 0x0400_0106, 0x0084),
            ],
            reads=[(16, 0x0400_0100), (16, 0x0400_0104)],
            ticks=1,
        ),
        BusCase(
            "timer_stop_before_tick",
            writes=[
                (16, 0x0400_0100, 0x1000),
                (16, 0x0400_0102, 0x0080),
                (16, 0x0400_0102, 0x0000),
            ],
            reads=[(16, 0x0400_0100)],
            ticks=100,
        ),
        BusCase(
            "timer_write32_read32",
            writes=[(32, 0x0400_0100, 0x0081_2000)],
            reads=[(32, 0x0400_0100)],
        ),
        BusCase(
            "timer_counter_high_byte",
            writes=[
                (16, 0x0400_0100, 0xFF00),
                (16, 0x0400_0102, 0x0080),
            ],
            reads=[(8, 0x0400_0101)],
            ticks=0x10,
        ),
        BusCase(
            "vblank_irq_and_dma",
            writes=[
                (16, 0x0200_0000, 0x1234),
                (32, 0x0400_00BC, 0x0200_0000),
                (32, 0x0400_00C0, 0x0200_0100),
                (16, 0x0400_00C4, 1),
                (16, 0x0400_00C6, 0x9000),
                (16, 0x0400_0004, 0x0008),
            ],
            reads=[
                (16, 0x0400_0202),
                (16, 0x0400_0006),
                (16, 0x0200_0100),
            ],
            ticks=160 * 1_232,
            dma_service=True,
        ),
        BusCase(
            "hblank_irq_and_dma",
            writes=[
                (16, 0x0200_0000, 0x5678),
                (32, 0x0400_00C8, 0x0200_0000),
                (32, 0x0400_00CC, 0x0200_0100),
                (16, 0x0400_00D0, 1),
                (16, 0x0400_00D2, 0xA000),
                (16, 0x0400_0004, 0x0010),
            ],
            reads=[
                (16, 0x0400_0202),
                (16, 0x0200_0100),
            ],
            ticks=1_006,
            dma_service=True,
        ),
        BusCase(
            "vcount_irq",
            writes=[(16, 0x0400_0004, 0x0520)],
            reads=[(16, 0x0400_0202), (16, 0x0400_0004)],
            ticks=5 * 1_232,
        ),
        BusCase(
            "keypad_irq_or_match",
            writes=[(16, 0x0400_0132, 0x4001)],
            reads=[(16, 0x0400_0202), (16, 0x0400_0132)],
            keyinput=0x03FE,
            poll_keys=True,
        ),
        BusCase(
            "keypad_irq_and_match",
            writes=[(16, 0x0400_0132, 0xC003)],
            reads=[(16, 0x0400_0202)],
            keyinput=0x03FC,
            poll_keys=True,
        ),
        BusCase(
            "keypad_irq_and_no_match",
            writes=[(16, 0x0400_0132, 0xC003)],
            reads=[(16, 0x0400_0202)],
            keyinput=0x03FE,
            poll_keys=True,
        ),
        BusCase(
            "keypad_irq_disabled",
            writes=[(16, 0x0400_0132, 0x0001)],
            reads=[(16, 0x0400_0202)],
            keyinput=0x03FE,
            poll_keys=True,
        ),
        BusCase(
            "keypad_irq_condition_zero",
            writes=[(16, 0x0400_0132, 0x4000)],
            reads=[(16, 0x0400_0202)],
            keyinput=0x03FE,
            poll_keys=True,
        ),
        BusCase(
            "sound_fifo_dma_a",
            writes=[
                (32, 0x0200_0000, 0x1111_0000),
                (32, 0x0200_0004, 0x1111_0001),
                (32, 0x0200_0008, 0x1111_0002),
                (32, 0x0200_000C, 0x1111_0003),
                (32, 0x0400_00BC, 0x0200_0000),
                (32, 0x0400_00C0, 0x0400_00A0),
                (16, 0x0400_00C4, 4),
                (16, 0x0400_00C6, 0xB600),
                (16, 0x0400_0082, 0x0804),
                (32, 0x0400_00A0, 0x9999_9999),
            ],
            dma_service=True,
            fifo_check=True,
        ),
        BusCase(
            "sound_fifo_dma_b",
            writes=[
                (32, 0x0200_0000, 0x2222_0000),
                (32, 0x0200_0004, 0x2222_0001),
                (32, 0x0200_0008, 0x2222_0002),
                (32, 0x0200_000C, 0x2222_0003),
                (32, 0x0400_00C8, 0x0200_0000),
                (32, 0x0400_00CC, 0x0400_00A4),
                (16, 0x0400_00D0, 4),
                (16, 0x0400_00D2, 0xB600),
                (16, 0x0400_0082, 0x8008),
                (32, 0x0400_00A4, 0x9999_9999),
            ],
            dma_service=True,
            fifo_check=True,
        ),
        BusCase(
            "sound_pcm_psg_square",
            writes=[
                (16, 0x0400_0062, 0xF080),  # ch1 volume 15、duty 50%
                (16, 0x0400_0064, 0x8700),  # freq 0x700 + trigger
                (16, 0x0400_0080, 0x1177),  # master volume + ch1 L/R
                (16, 0x0400_0082, 0x0002),  # PSG volume 100%
                (16, 0x0400_0084, 0x0080),  # master enable
            ],
            ticks=4096,
            sound=True,
            pcm_check=True,
        ),
        BusCase(
            "sound_pcm_direct_sound_timer",
            writes=[
                (16, 0x0400_0082, 0x0304),  # A L/R、100%、timer 0
                (16, 0x0400_0084, 0x0080),  # master enable
                (16, 0x0400_00A0, 0x8040),  # FIFO A：兩個 sample
                (16, 0x0400_0100, 0xFFFE),  # timer 0 reload
                (16, 0x0400_0102, 0x0080),  # timer 0 enable
            ],
            ticks=4096,
            sound=True,
            pcm_check=True,
        ),
        BusCase(
            "bios_write_ignored",
            writes=[(8, 0x0000_0000, 0xAA)],
            reads=[(8, 0x0000_0000)],
        ),
    ]

    probe = Probe()
    failed = 0
    try:
        for case in cases:
            python = _python_run(case)
            rust = _rust_run(probe, case)
            errors = []
            for key, value in python.items():
                if rust.get(key) != value:
                    errors.append(f"mem{key[0]}[{key[1]:08x}]: py={value:x} rust={rust.get(key, -1):x}")
            if errors:
                failed += 1
                print(f"[FAIL] {case.name}")
                for error in errors:
                    print(f"  {error}")
            else:
                print(f"[ ok ] {case.name}")
    finally:
        probe.close()

    total = len(cases)
    print(f"{total - failed}/{total} bus checks passed")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())

