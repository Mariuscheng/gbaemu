"""CPU opcode 測試的共用工具：以最小 ROM 驅動 ``Emulator.step_cycles()``。"""

from __future__ import annotations

import struct
from pathlib import Path

from gbaemu import BootMode, Emulator, EmulatorConfig

from .helpers import build_rom

CODE_BASE = 0x08000000


def arm_words(*words: int) -> bytes:
    return b"".join(struct.pack("<I", word & 0xFFFFFFFF) for word in words)


def thumb_words(*words: int) -> bytes:
    return b"".join(struct.pack("<H", word & 0xFFFF) for word in words)


def program_rom(code: bytes, *, size: int = 0x400) -> bytes:
    rom = bytearray(build_rom(size=size))
    rom[: len(code)] = code
    return bytes(rom)


def make_emu(tmp_path: Path, code: bytes, *, thumb: bool = False) -> Emulator:
    """建立以 ``CODE_BASE`` 為起點的 TEST_ROM_ONLY emulator。"""

    path = tmp_path / "program.gba"
    path.write_bytes(program_rom(code))
    emu = Emulator.from_rom(
        path, config=EmulatorConfig(boot_mode=BootMode.TEST_ROM_ONLY)
    )
    if thumb:
        emu._cpu.regs.cpsr |= 0x20  # CPSR.T
        emu._cpu.regs.pc = CODE_BASE
    return emu
