"""Phase 1 差動驗收：gbaemu CPU vs legacy `gba_cpu` 純 Python 參考實作。

參考側直接呼叫 ``gba_cpu.arm.execute``／``gba_cpu.thumb.execute``（不經
``pygba.core.CPU``，避開 Cython 硬轉型 crash）。指令由受限模板產生，seed 固定；
legacy 套件未來移除時，本檔可一併刪除。
"""

from __future__ import annotations

import random

import pytest

pytest.importorskip("tests.reference.gba_cpu")

from tests.reference.gba_cpu import arm as legacy_arm  # noqa: E402
from tests.reference.gba_cpu import thumb as legacy_thumb  # noqa: E402
from tests.reference.gba_cpu.registers import Registers as LegacyRegisters  # noqa: E402

from gbaemu.bus.address_bus import AddressBus  # noqa: E402
from gbaemu.cpu import arm as new_arm  # noqa: E402
from gbaemu.cpu import thumb as new_thumb  # noqa: E402
from gbaemu.cpu.arm7tdmi import Arm7Tdmi  # noqa: E402
from gbaemu.memory.cartridge import RomCartridge  # noqa: E402

SEED = 20261031
ARM_VECTORS = 200
THUMB_VECTORS = 200


class _LegacyBus:
    """把新 AddressBus 包成 legacy CPU 需要的 read32/write32/... 介面。"""

    bios_present = False

    def __init__(self, bus: AddressBus) -> None:
        self._bus = bus

    def read8(self, address: int) -> int:
        return self._bus.read_u8(address)

    def read16(self, address: int) -> int:
        return self._bus.read_u16(address)

    def read32(self, address: int) -> int:
        return self._bus.read_u32(address)

    def write8(self, address: int, value: int) -> None:
        self._bus.write_u8(address, value)

    def write16(self, address: int, value: int) -> None:
        self._bus.write_u16(address, value)

    def write32(self, address: int, value: int) -> None:
        self._bus.write_u32(address, value)

    def _stall(self, cycles: int) -> None:
        del cycles


class _LegacyCpu:
    def __init__(self, bus: AddressBus) -> None:
        self.regs = LegacyRegisters()
        self.bus = _LegacyBus(bus)
        self._undef_seen: set = set()
        self._t_branch_taken = False
        self.exceptions: list = []

    def swi(self, comment: int) -> None:
        self.exceptions.append(("swi", comment))

    def enter_exception(self, mode, vector, lr_offset=4, set_f=False):
        self.exceptions.append((mode, vector, lr_offset, set_f))


def _new_bus() -> AddressBus:
    return AddressBus(RomCartridge(bytes(0x400)))


def _state(rng: random.Random, *, thumb: bool) -> tuple[list[int], int]:
    regs = [rng.getrandbits(32) for _ in range(13)]
    regs += [0x03007F00, 0x08000000, 0x08000000]
    cpsr = (0x3F if thumb else 0x1F) | (rng.getrandbits(1) << 31) | (rng.getrandbits(1) << 30)
    return regs, cpsr


def _gen_arm(rng: random.Random) -> list[int]:
    out = []
    for _ in range(ARM_VECTORS):
        kind = rng.randrange(8)
        if kind == 0:  # data processing
            op = rng.choice([0, 1, 2, 3, 4, 10, 11, 12, 13, 14, 15])
            rn, rd = rng.randrange(1, 13), rng.randrange(1, 13)
            if rng.random() < 0.5:
                out.append(
                    0xE0000000 | (op << 21) | (1 << 25) | (rn << 16) | (rd << 12)
                    | (rng.randrange(16) << 8) | rng.randrange(256)
                )
            else:
                out.append(
                    0xE0000000 | (op << 21) | (rn << 16) | (rd << 12)
                    | (rng.randrange(1, 32) << 7) | (rng.randrange(3) << 5) | rng.randrange(1, 13)
                )
        elif kind == 1:  # LDR/STR word（r3 base = EWRAM）
            out.append(
                (0xE5900000 if rng.random() < 0.5 else 0xE5800000)
                | (3 << 16) | (rng.randrange(1, 13) << 12) | rng.randrange(0, 0x100, 4)
            )
        elif kind == 2:  # LDM/STM
            load = rng.random() < 0.5
            out.append(
                (0xE8900000 if load else 0xE8800000)
                | (3 << 16) | (rng.randrange(1, 0x1000) & ~(1 << 3))
            )
        elif kind == 3:  # B / BL
            imm = rng.randrange(1 << 20)
            if imm & 0x80000:
                imm -= 1 << 20
            out.append(0xEA000000 | (rng.randrange(2) << 24) | (imm & 0xFFFFFF))
        elif kind == 4:  # MUL
            out.append(
                0xE0000090 | (rng.randrange(1, 13) << 16) | (rng.randrange(1, 13) << 8) | rng.randrange(1, 13)
            )
        elif kind == 5:  # MOV/MVN 立即數
            out.append(
                0xE0000000 | (rng.choice([13, 15]) << 21) | (1 << 25)
                | (rng.randrange(1, 13) << 12) | (rng.randrange(16) << 8) | rng.randrange(256)
            )
        elif kind == 6:  # 移位
            out.append(
                0xE0000000 | (13 << 21) | (rng.randrange(1, 13) << 12)
                | (rng.randrange(1, 32) << 7) | (rng.randrange(3) << 5) | rng.randrange(1, 13)
            )
        else:  # CMP/TST 立即數
            out.append(
                0xE0000000 | (rng.choice([8, 10]) << 21) | (1 << 25)
                | (rng.randrange(1, 13) << 16) | (rng.randrange(16) << 8) | rng.randrange(256)
            )
    return out


def _gen_thumb(rng: random.Random) -> list[int]:
    out = []
    for _ in range(THUMB_VECTORS):
        kind = rng.randrange(7)
        if kind == 0:
            out.append(0x2000 | (rng.randrange(8) << 8) | rng.randrange(256))
        elif kind == 1:
            out.append(0x4000 | (rng.randrange(8) << 6) | (rng.randrange(8) << 3) | rng.randrange(8))
        elif kind == 2:
            out.append(
                (0x6800 if rng.random() < 0.5 else 0x6000)
                | (rng.randrange(1, 32) << 6) | (3 << 3) | rng.randrange(8)
            )
        elif kind == 3:
            out.append(0x1800 | (rng.randrange(8) << 6) | (rng.randrange(8) << 3) | rng.randrange(8))
        elif kind == 4:
            out.append((0xB400 if rng.random() < 0.5 else 0xBC00) | rng.randrange(1, 256))
        elif kind == 5:
            out.append(0xD000 | (rng.randrange(14) << 8) | rng.randrange(256))
        else:
            out.append(0xB000 | (rng.randrange(2) << 7) | rng.randrange(128))
    return out


def _assert_same(label: str, index: int, instr: int, legacy, new, *, thumb: bool) -> None:
    legacy_regs = [legacy.regs.r[i] & 0xFFFFFFFF for i in range(16)]
    new_regs = [new.core.regs[i] & 0xFFFFFFFF for i in range(16)]
    width = 4 if thumb else 8
    assert legacy_regs == new_regs, f"{label} #{index} instr=0x{instr:0{width}X} regs 不符"
    assert legacy.regs.cpsr == new.core.cpsr, f"{label} #{index} instr=0x{instr:0{width}X} cpsr 不符"


def test_arm_random_differential():
    rng = random.Random(SEED)
    for index, instr in enumerate(_gen_arm(rng)):
        bus_legacy, bus_new = _new_bus(), _new_bus()
        legacy, new = _LegacyCpu(bus_legacy), Arm7Tdmi(bus_new)
        regs, cpsr = _state(rng, thumb=False)
        for cpu, value in ((legacy, regs), (new, regs)):
            for r_index, r_value in enumerate(value):
                cpu.regs.r[r_index] = r_value
            cpu.regs.cpsr = cpsr
        legacy.regs.r[3] = new.core.regs[3] = 0x02000000

        legacy_arm.execute(legacy, instr)
        new_arm.execute(new, instr)
        _assert_same("ARM", index, instr, legacy, new, thumb=False)


def test_thumb_random_differential():
    rng = random.Random(SEED + 1)
    for index, instr in enumerate(_gen_thumb(rng)):
        bus_legacy, bus_new = _new_bus(), _new_bus()
        legacy, new = _LegacyCpu(bus_legacy), Arm7Tdmi(bus_new)
        regs, cpsr = _state(rng, thumb=True)
        for cpu, value in ((legacy, regs), (new, regs)):
            for r_index, r_value in enumerate(value):
                cpu.regs.r[r_index] = r_value
            cpu.regs.cpsr = cpsr
        legacy.regs.r[3] = new.core.regs[3] = 0x02000000

        legacy_thumb.execute(legacy, instr)
        new_thumb.execute(new, instr)
        _assert_same("THUMB", index, instr, legacy, new, thumb=True)
