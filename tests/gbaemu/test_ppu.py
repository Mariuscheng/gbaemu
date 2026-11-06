"""Phase 2：PPU scanline 時序、DISPSTAT 與事件（規格 §3.6.6）。"""

from __future__ import annotations

from gbaemu.bus.address_bus import AddressBus
from gbaemu.bus.io import IRQ_HBLANK, IRQ_VBLANK, IRQ_VCOUNT
from gbaemu.events import EventStream
from gbaemu.memory.cartridge import RomCartridge
from gbaemu.timing import PPU_FRAME_CYCLES, PPU_HBLANK_START, PPU_LINE_CYCLES, PPU_VBLANK_START
from gbaemu.video.ppu import Ppu


def _ppu_with_events():
    ppu = Ppu()
    stream = EventStream()
    ppu.bind_events(stream)
    return ppu, stream


def test_vcount_and_hblank_boundaries():
    ppu, stream = _ppu_with_events()

    ppu.advance(PPU_HBLANK_START)
    assert ppu.vcount == 0
    assert ppu.dispstat() & 0x0002  # HBlank flag
    events = stream.poll()
    assert [event.kind.value for event in events] == ["hblank"]
    assert events[0].cycle == PPU_HBLANK_START
    assert events[0].scanline == 0

    ppu.advance(PPU_LINE_CYCLES - PPU_HBLANK_START)  # 走到 line 1
    assert ppu.vcount == 1
    assert not (ppu.dispstat() & 0x0002)


def test_vblank_start_at_197120():
    ppu, stream = _ppu_with_events()
    ppu.advance(PPU_VBLANK_START - 1)
    assert ppu.vcount == 159
    assert not (ppu.dispstat() & 0x0001)

    ppu.advance(1)
    assert ppu.vcount == 160
    assert ppu.dispstat() & 0x0001  # VBlank flag
    events = stream.poll()
    assert any(event.kind.value == "vblank_start" for event in events)
    vblank = next(event for event in events if event.kind.value == "vblank_start")
    assert vblank.cycle == PPU_VBLANK_START
    assert vblank.scanline == 160


def test_vblank_flag_not_set_on_line_227():
    ppu, _ = _ppu_with_events()
    ppu.advance(227 * PPU_LINE_CYCLES + 1)
    assert ppu.vcount == 227
    assert not (ppu.dispstat() & 0x0001)


def test_frame_boundary_events_and_wrap():
    ppu, stream = _ppu_with_events()
    ppu.advance(PPU_FRAME_CYCLES - 1)
    assert ppu.vcount == 227

    ppu.advance(1)
    assert ppu.vcount == 0
    assert ppu.frame_index == 1
    assert ppu.total_cycles == PPU_FRAME_CYCLES
    kinds = [event.kind.value for event in stream.poll()]
    assert kinds[-2:] == ["vblank_end", "frame_boundary"]
    assert kinds.count("hblank") == 228  # HBlank flag 每條線都切換（含 VBlank）
    assert stream.poll() == ()


def test_dispstat_irq_enables_and_flags():
    ppu, _ = _ppu_with_events()
    ppu.write_dispstat(0x0008 | 0x0010 | 0x0020 | (160 << 8))
    value = ppu.dispstat()
    assert value & 0x0038 == 0x0038
    assert (value >> 8) & 0xFF == 160

    # LYC=160：走到 line 160 時 VCount match flag 要設起
    ppu.advance(PPU_VBLANK_START)
    assert ppu.dispstat() & 0x0004


def test_pipeline_irq_bits_through_io():
    ppu = Ppu()
    bus = AddressBus(RomCartridge(bytes(0x400)), ppu=ppu)
    busy = bus.io_registers
    busy.write16(0x004, 0x0018)  # VBlank + HBlank IRQ enable
    busy.write16(0x200, 0x0003)
    busy.write16(0x208, 1)

    ppu.advance(PPU_HBLANK_START)
    assert busy.read16(0x202) & IRQ_HBLANK

    ppu.advance(PPU_VBLANK_START - PPU_HBLANK_START)
    assert busy.read16(0x202) & IRQ_VBLANK


def test_vcount_irq_on_lyc_line():
    ppu = Ppu()
    bus = AddressBus(RomCartridge(bytes(0x400)), ppu=ppu)
    io = bus.io_registers
    io.write16(0x004, 0x0020 | (5 << 8))  # VCount IRQ、LYC=5
    io.write16(0x200, 0x0004)
    io.write16(0x208, 1)

    ppu.advance(5 * PPU_LINE_CYCLES + 1)
    assert io.read16(0x202) & IRQ_VCOUNT


def test_dispstat_and_vcount_read_through_bus():
    ppu = Ppu()
    bus = AddressBus(RomCartridge(bytes(0x400)), ppu=ppu)
    ppu.advance(PPU_VBLANK_START)
    assert bus.read_u16(0x04000006) == 160
    assert bus.read_u16(0x04000004) & 0x0001
