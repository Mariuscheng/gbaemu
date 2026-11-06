"""BIOS SWI 0x00–0x2A 的 HLE 實作（規格 2.1.2；GBATEK: BIOS Functions）。

自 `pygba/core/bios.py`（真 BIOS 對照過的實作）移植到新 CPU／bus 介面：

* 算術：Div、DivArm、Sqrt、ArcTan、ArcTan2、GetBiosChecksum、MidiKey2Freq
* 記憶體：CpuSet、CpuFastSet、BgAffineSet、ObjAffineSet、BitUnPack
* 解壓：LZ77（Wram/Vram）、Huffman、RL（Wram/Vram）、Diff8/16
* 控制：SoftReset、RegisterRamReset、Halt、Stop、IntrWait、VBlankIntrWait、
  CustomHalt、SoundBias；SoundDriver 系列與 MultiBoot 目前為 no-op（Phase 4）。

# GBATEK: BIOS Function Summary / BIOS Arithmetic Functions /
# BIOS Rotation-Scaling Functions / BIOS Decompression Functions / BIOS Halt Functions
"""

from __future__ import annotations

import logging
import math

from .swi_math import (
    biosatan2,
    biosatan2_parts,
    biostan,
    biostan_parts,
    midi_val,
    s16,
    signed32,
    sdiv,
)

logger = logging.getLogger("gbaemu.hle.swi")

Q8 = 256
SINTAB = tuple(
    round(math.sin(index * math.pi / 128) * 256)
    for index in range(256)
)


def _s16(value: int) -> int:
    return s16(value)


def _signed32(value: int) -> int:
    return signed32(value)


def _q8(value: int) -> int:
    """Q8.8 四捨五入（同真 BIOS 的 `(x + 0x80) >> 8`）。"""

    return (value + 0x80) >> 8


def _flush16(bus, dest: int, data: bytes) -> None:
    """以 16-bit 單位寫出（VRAM 目的地用）。"""

    for index in range(0, len(data) - 1, 2):
        bus.write16((dest + index) & 0xFFFFFFFF, data[index] | (data[index + 1] << 8))
    if len(data) & 1:
        bus.write16((dest + len(data) - 1) & 0xFFFFFFFF, data[-1])


def _read_bytes(bus, address: int, length: int) -> bytes:
    return bytes(bus.read8((address + index) & 0xFFFFFFFF) for index in range(length))


# ---------------------------------------------------------------------------
# SWI handlers
# ---------------------------------------------------------------------------
def _soft_reset(cpu) -> None:
    bus = cpu.bus
    target = 0x08000000 if bus.read8(0x03007FFA) == 0 else 0x02000000
    for address in range(0x7E00, 0x8000):
        bus.write8(0x03000000 + address, 0)
    cpu.regs.state.banked[0x1F] = (0x03007F00, 0)
    cpu.regs.state.banked[0x12] = (0x03007FA0, 0)
    cpu.regs.state.banked[0x13] = (0x03007FE0, 0)
    for index in range(13):
        cpu.regs.r[index] = 0
    cpu.regs.r[13] = 0x03007F00
    cpu.regs.r[14] = target
    cpu.regs.spsr_set(0x1F)  # swi() 返回時切回 System mode、PC=target
    cpu.core.halted = False
    cpu.wait_irq = 0


def _register_ram_reset(cpu) -> None:
    bus = cpu.bus
    flags = cpu.regs.r[0]
    if flags & 0x01:
        bus.ewram.clear()
    if flags & 0x02:  # IWRAM 只清前 0x7E00 bytes（BIOS 保留最後 0x200）
        for offset in range(0x7E00):
            bus.iwram.write_raw_u8(offset, 0)
    if flags & 0x04:
        bus.palette.clear()
    if flags & 0x08:
        bus.vram.clear()
    if flags & 0x10:
        bus.oam.clear()
    if flags & 0x20:
        for offset in range(0x120, 0x134):
            bus.io_registers.write8(offset, 0)
    if flags & 0x40:
        for offset in range(0x60, 0xA9):
            bus.io_registers.write8(offset, 0)
    if flags & 0x80:
        for offset in list(range(0x000, 0x060)) + list(range(0x0A9, 0x120)) + list(
            range(0x200, 0x20A)
        ):
            bus.io_registers.write8(offset, 0)
        bus.timers.reset()
        bus.dma.reset()
    # 真 BIOS 會進 forced blank
    bus.write16(0x04000000, 0x0080)


def _halt(cpu) -> None:
    cpu.bus.write8(0x04000301, 0x00)  # HALTCNT
    cpu.core.halted = True
    cpu.wait_irq = 0


def _intr_wait(cpu, number: int) -> None:
    if number == 0x05:  # VBlankIntrWait = IntrWait(1, 1)
        cpu.regs.r[0] = 1
        cpu.regs.r[1] = 1
    flags = cpu.regs.r[1] & 0x3FFF
    bus = cpu.bus
    bus.io_registers.write16(0x208, bus.io_registers.read16(0x208) | 1)  # IME=1
    old = bus.io_registers.read16(0x202) & flags
    if cpu.regs.r[0] == 0 and old:
        return
    if cpu.regs.r[0] == 1:
        ram = bus.read16(0x03007FF8)
        bus.write16(0x03007FF8, ram & ~flags & 0xFFFF)
    bus.io_registers.clear_irq_seen(flags)
    cpu.core.halted = True
    cpu.wait_irq = flags


def _div(cpu, number: int) -> None:
    if number == 0x06:
        numerator, denominator = signed32(cpu.regs.r[0]), signed32(cpu.regs.r[1])
    else:
        numerator, denominator = signed32(cpu.regs.r[1]), signed32(cpu.regs.r[0])
    quotient, remainder = sdiv(numerator, denominator)
    cpu.regs.r[0] = quotient & 0xFFFFFFFF
    cpu.regs.r[1] = remainder & 0xFFFFFFFF
    cpu.regs.r[3] = abs(quotient) & 0xFFFFFFFF


def _sqrt(cpu) -> None:
    cpu.regs.r[0] = math.isqrt(cpu.regs.r[0] & 0xFFFFFFFF) & 0xFFFF


def _cpu_set(cpu) -> None:
    bus = cpu.bus
    source = cpu.regs.r[0]
    dest = cpu.regs.r[1]
    control = cpu.regs.r[2]
    count = control & 0x1FFFFF
    fill = (control >> 24) & 1
    if (control >> 26) & 1:
        if fill:
            value = bus.read32(source & ~3)
            for index in range(count):
                bus.write32((dest + index * 4) & ~3, value)
        else:
            for index in range(count):
                value = bus.read32((source + index * 4) & ~3)
                bus.write32((dest + index * 4) & ~3, value)
    else:
        if fill:
            value = bus.read8(source) if source & 1 else bus.read16(source & ~1)
            for index in range(count):
                bus.write16((dest + index * 2) & ~1, value)
        else:
            for index in range(count):
                src = source + index * 2
                value = bus.read8(src) if src & 1 else bus.read16(src)
                bus.write16((dest + index * 2) & ~1, value)


def _cpu_fast_set(cpu) -> None:
    bus = cpu.bus
    source = cpu.regs.r[0]
    dest = cpu.regs.r[1]
    control = cpu.regs.r[2]
    count = control & 0x1FFFFF
    if count == 0:
        count = 0x100000
    count = (count + 7) & ~7  # GBA：向上取整到 8 words
    fill = (control >> 24) & 1
    if fill:
        value = bus.read32(source)
        for index in range(count):
            bus.write32(dest + index * 4, value)
    else:
        for index in range(count):
            bus.write32(dest + index * 4, bus.read32(source + index * 4))


def _bg_affine_set(cpu) -> None:
    bus = cpu.bus
    source, dest, count = cpu.regs.r[0], cpu.regs.r[1], cpu.regs.r[2]
    for index in range(count):
        src = source + index * 20
        x0 = signed32(bus.read32(src))
        y0 = signed32(bus.read32(src + 4))
        dx = _s16(bus.read16(src + 8))
        dy = _s16(bus.read16(src + 10))
        sx = _s16(bus.read16(src + 12))
        sy = _s16(bus.read16(src + 14))
        angle = (bus.read16(src + 16) >> 8) & 0xFF
        sin = SINTAB[angle]
        cos = SINTAB[(angle + 64) & 0xFF]
        pa, pb = _q8(cos * sx), _q8(-sin * sx)
        pc, pd = _q8(sin * sy), _q8(cos * sy)
        dst = dest + index * 16
        bus.write16(dst + 0, pa & 0xFFFF)
        bus.write16(dst + 2, pb & 0xFFFF)
        bus.write16(dst + 4, pc & 0xFFFF)
        bus.write16(dst + 6, pd & 0xFFFF)
        bus.write32(dst + 8, (x0 - pa * dx - pb * dy) & 0xFFFFFFFF)
        bus.write32(dst + 12, (y0 - pc * dx - pd * dy) & 0xFFFFFFFF)


def _obj_affine_set(cpu) -> None:
    bus = cpu.bus
    source, dest = cpu.regs.r[0], cpu.regs.r[1]
    count, offset = cpu.regs.r[2], cpu.regs.r[3]
    for index in range(count):
        src = source + index * 6
        sx = _s16(bus.read16(src))
        sy = _s16(bus.read16(src + 2))
        angle = (bus.read16(src + 4) >> 8) & 0xFF
        sin = SINTAB[angle]
        cos = SINTAB[(angle + 64) & 0xFF]
        dst = dest + index * offset * 4
        bus.write16(dst + 0 * offset, _q8(cos * sx) & 0xFFFF)
        bus.write16(dst + 1 * offset, _q8(-sin * sx) & 0xFFFF)
        bus.write16(dst + 2 * offset, _q8(sin * sy) & 0xFFFF)
        bus.write16(dst + 3 * offset, _q8(cos * sy) & 0xFFFF)


def _bit_unpack(cpu) -> None:
    bus = cpu.bus
    source, dest, info = cpu.regs.r[0], cpu.regs.r[1], cpu.regs.r[2]
    length = bus.read16(info)
    src_width = bus.read8(info + 2)
    dst_width = bus.read8(info + 3)
    raw_offset = bus.read32(info + 4)
    zero_flag = (raw_offset >> 31) & 1
    offset = raw_offset & 0x7FFFFFFF
    units = []
    per_byte = max(8 // max(src_width, 1), 1)
    mask = (1 << src_width) - 1
    for index in range(length):
        value = bus.read8(source + index)
        for slot in range(per_byte):
            units.append((value >> (slot * src_width)) & mask)
    word = 0
    bit_position = 0
    words = []
    dst_mask = (1 << dst_width) - 1
    for unit in units:
        value = (unit + offset) if (unit or zero_flag) else 0
        word |= (value & dst_mask) << bit_position
        bit_position += dst_width
        if bit_position >= 32:
            words.append(word & 0xFFFFFFFF)
            word, bit_position = 0, 0
    if bit_position:
        words.append(word & 0xFFFFFFFF)
    for index, value in enumerate(words):
        bus.write32(dest + index * 4, value)


def _lz77(cpu, number: int) -> None:
    bus = cpu.bus
    source, dest = cpu.regs.r[0], cpu.regs.r[1]
    length = bus.read32(source) >> 8
    source += 4
    out = bytearray()
    while len(out) < length:
        flags = bus.read8(source)
        source += 1
        for _ in range(8):
            if len(out) >= length:
                break
            if flags & 0x80:
                first = bus.read8(source)
                second = bus.read8(source + 1)
                source += 2
                count = (first >> 4) + 3
                displacement = ((first & 0x0F) << 8) | second
                for _ in range(count):
                    out.append(out[len(out) - displacement - 1])
            else:
                out.append(bus.read8(source))
                source += 1
            flags = (flags << 1) & 0xFF
    if number == 0x12:
        _flush16(bus, dest, bytes(out))
    else:
        for index, value in enumerate(out):
            bus.write8(dest + index, value)


def _huffman(cpu) -> None:
    bus = cpu.bus
    source = cpu.regs.r[0] & 0xFFFFFFFC
    dest = cpu.regs.r[1]
    header = bus.read32(source)
    size = header & 0xF
    if size == 0:
        size = 8
    if size == 1 or 32 % size:
        # BIOS 對非 4/8/16/32-bit 的 Huffman 不輸出；保持 no-op 讓遊戲自行處理。
        return
    length = header >> 8
    tree_size = bus.read8(source + 4)
    tree = source + 5
    bits = source + 4 + (tree_size + 1) * 2
    words = (length + 3) // 4
    bit_position = 0
    mask = (1 << size) - 1

    def next_bit() -> int:
        nonlocal bit_position
        word = bus.read32(bits + (bit_position >> 5) * 4)
        value = (word >> (31 - (bit_position & 31))) & 1
        bit_position += 1
        return value

    pointer = tree
    node = bus.read8(pointer)
    for _ in range(words):
        word = 0
        shift = 0
        # Huffman code 是變長：一個 output word 可能吃掉遠多於 per_word 個
        # compressed bits，不能固定跑 per_word 次。
        while shift < 32:
            bit = next_bit()
            is_data = (node >> (7 - bit)) & 1
            child = (pointer & ~1) + (node & 0x3F) * 2 + 2 + bit
            node = bus.read8(child)
            if is_data:
                word |= (node & mask) << shift
                shift += size
                pointer = tree
                node = bus.read8(pointer)
            else:
                pointer = child
        bus.write32(dest, word)
        dest += 4

    cpu.regs.r[0] = bits + (bit_position + 31) // 32 * 4
    cpu.regs.r[1] = dest


def _rl(cpu, number: int) -> None:
    bus = cpu.bus
    source, dest = cpu.regs.r[0], cpu.regs.r[1]
    length = bus.read32(source) >> 8
    source += 4
    out = bytearray()
    while len(out) < length:
        flag = bus.read8(source)
        source += 1
        if flag & 0x80:
            count = (flag & 0x7F) + 3
            out += bytes([bus.read8(source)]) * count
            source += 1
        else:
            count = (flag & 0x7F) + 1
            out.extend(bus.read8(source + index) for index in range(count))
            source += count
    if number == 0x15:
        _flush16(bus, dest, bytes(out))
    else:
        for index, value in enumerate(out):
            bus.write8(dest + index, value)


def _diff8(cpu, number: int) -> None:
    bus = cpu.bus
    source, dest = cpu.regs.r[0], cpu.regs.r[1]
    length = bus.read32(source) >> 8
    source += 4
    out = bytearray()
    accumulator = 0
    for index in range(length):
        accumulator = (accumulator + bus.read8(source + index)) & 0xFF
        out.append(accumulator)
    _flush16(bus, dest, bytes(out))


def _diff16(cpu) -> None:
    bus = cpu.bus
    source, dest = cpu.regs.r[0], cpu.regs.r[1]
    length = bus.read32(source) >> 8
    source += 4
    accumulator = 0
    for index in range(length // 2):
        accumulator = (accumulator + bus.read16(source + index * 2)) & 0xFFFF
        bus.write16(dest + index * 2, accumulator)


def _sound_bias(cpu) -> None:
    bus = cpu.bus
    old = bus.read16(0x04000088)
    level = 0x000 if cpu.regs.r[0] == 0 else 0x200
    bus.write16(0x04000088, (old & ~0x3FF) | level)


def _midi_key_to_freq(cpu) -> None:
    wave = cpu.regs.r[0]
    midi_key = cpu.regs.r[1] & 0xFF
    fraction = cpu.regs.r[2] & 0xFF
    del wave
    value_fraction = fraction << 24
    if midi_key > 0xB2:
        value_fraction = 0xFF000000
        midi_key = 0xB2
    low = midi_val(midi_key)
    high = midi_val(midi_key + 1)
    delta = (((high - low) & 0xFFFFFFFF) * value_fraction) >> 32
    cpu.regs.r[0] = (low + delta) & 0xFFFFFFFF


def _no_op(cpu) -> None:
    del cpu


def build_handlers(cpu):
    """建立 SWI 編號 → handler 的 dict（供 :class:`SwiTable` 注入）。"""

    def register(number, function):
        return lambda context=None: function(cpu)

    handlers = {
        0x00: lambda context=None: _soft_reset(cpu),
        0x01: lambda context=None: _register_ram_reset(cpu),
        0x02: lambda context=None: _halt(cpu),
        0x03: lambda context=None: _halt(cpu),
        0x04: lambda context=None: _intr_wait(cpu, 0x04),
        0x05: lambda context=None: _intr_wait(cpu, 0x05),
        0x06: lambda context=None: _div(cpu, 0x06),
        0x07: lambda context=None: _div(cpu, 0x07),
        0x08: lambda context=None: _sqrt(cpu),
        0x09: lambda context=None: _arctan(cpu),
        0x0A: lambda context=None: _arctan2(cpu),
        0x0B: lambda context=None: _cpu_set(cpu),
        0x0C: lambda context=None: _cpu_fast_set(cpu),
        0x0D: lambda context=None: _checksum(cpu),
        0x0E: lambda context=None: _bg_affine_set(cpu),
        0x0F: lambda context=None: _obj_affine_set(cpu),
        0x10: lambda context=None: _bit_unpack(cpu),
        0x11: lambda context=None: _lz77(cpu, 0x11),
        0x12: lambda context=None: _lz77(cpu, 0x12),
        0x13: lambda context=None: _huffman(cpu),
        0x14: lambda context=None: _rl(cpu, 0x14),
        0x15: lambda context=None: _rl(cpu, 0x15),
        0x16: lambda context=None: _diff8(cpu, 0x16),
        0x17: lambda context=None: _diff8(cpu, 0x17),
        0x18: lambda context=None: _diff16(cpu),
        0x19: lambda context=None: _sound_bias(cpu),
        0x1A: lambda context=None: _no_op(cpu),
        0x1B: lambda context=None: _no_op(cpu),
        0x1C: lambda context=None: _no_op(cpu),
        0x1D: lambda context=None: _no_op(cpu),
        0x1E: lambda context=None: _no_op(cpu),
        0x1F: lambda context=None: _midi_key_to_freq(cpu),
        0x25: lambda context=None: _no_op(cpu),
        0x26: lambda context=None: _soft_reset(cpu),
        0x27: lambda context=None: _custom_halt(cpu),
        0x28: lambda context=None: _no_op(cpu),
        0x29: lambda context=None: _no_op(cpu),
        0x2A: lambda context=None: _no_op(cpu),
    }
    return handlers


def _arctan(cpu) -> None:
    result, r1, r3 = biostan_parts(cpu.regs.r[0])
    cpu.regs.r[0] = result
    cpu.regs.r[1] = r1
    cpu.regs.r[3] = r3


def _arctan2(cpu) -> None:
    result, r1 = biosatan2_parts(cpu.regs.r[0], cpu.regs.r[1])
    cpu.regs.r[0] = result
    cpu.regs.r[1] = r1
    cpu.regs.r[3] = 0x170


def _checksum(cpu) -> None:
    cpu.regs.r[0] = 0xBAAE187F


def _custom_halt(cpu) -> None:
    cpu.bus.write8(0x04000301, cpu.regs.r[0] & 0xFF)
    cpu.core.halted = True
    cpu.wait_irq = 0


__all__ = ["build_handlers"]
