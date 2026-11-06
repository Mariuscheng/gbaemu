"""Phase 3：備份媒體 SRAM／Flash／EEPROM 與磁碟 persist（GBATEK 12 章）。"""

from __future__ import annotations

from pathlib import Path

from gbaemu import BootMode, Emulator, EmulatorConfig, MemoryRegionKind
from gbaemu.api_types import SaveType as SaveTypeEnum
from gbaemu.bus.address_bus import AddressBus
from gbaemu.memory.cartridge import RomCartridge

from .cpu_helpers import arm_words
from .helpers import build_rom

SRAM_ID = b"SRAM_V123\0\0\0\0"
FLASH_ID = b"FLASH_V123\0\0\0\0"
EEPROM_ID = b"EEPROM_V122\0"


def _save_bus(identifier: bytes) -> AddressBus:
    rom = bytearray(0x1000)
    rom[0x100 : 0x100 + len(identifier)] = identifier
    return AddressBus(RomCartridge(bytes(rom)))


def _program_rom(identifier: bytes, code: bytes = b"") -> bytes:
    rom = bytearray(build_rom(size=0x1000))
    if code:
        rom[: len(code)] = code
    rom[0x300 : 0x300 + len(identifier)] = identifier
    return bytes(rom)


# ---------------------------------------------------------------------------
# SRAM
# ---------------------------------------------------------------------------
def test_sram_detect_and_roundtrip():
    bus = _save_bus(SRAM_ID)
    assert bus.cartridge.save_kind == "SRAM"
    assert bus.cartridge.save_type() is SaveTypeEnum.SRAM

    bus.write_u8(0x0E000000, 0x42)
    assert bus.read_u8(0x0E000000) == 0x42
    assert bus.read_u8(0x0E008000) == 0x42  # 32K 鏡像


def test_sram_wide_store_writes_single_byte():
    bus = _save_bus(SRAM_ID)

    bus.write_u16(0x0E000010, 0xAABB)  # 只寫低 byte
    assert bus.read_u8(0x0E000010) == 0xBB
    assert bus.read_u8(0x0E000011) == 0xFF

    bus.write_u16(0x0E000011, 0xAABB)  # odd：只寫 high byte
    assert bus.read_u8(0x0E000011) == 0xAA

    bus.write_u32(0x0E000020, 0xAABBCCDD)
    assert [bus.read_u8(0x0E000020 + k) for k in range(4)] == [0xDD, 0xFF, 0xFF, 0xFF]


def test_sram_region_bytes_from_backend():
    bus = _save_bus(SRAM_ID)
    bus.write_u8(0x0E000000, 0x5A)
    data = bus.read_region(MemoryRegionKind.SRAM)
    assert len(data) == 0x8000
    assert data[0] == 0x5A


# ---------------------------------------------------------------------------
# Flash
# ---------------------------------------------------------------------------
def _flash_cmd(bus: AddressBus, command: int) -> None:
    bus.write_u8(0x0E005555, 0xAA)
    bus.write_u8(0x0E002AAA, 0x55)
    bus.write_u8(0x0E005555, command)


def _flash_program(bus: AddressBus, address: int, value: int) -> None:
    _flash_cmd(bus, 0xA0)
    bus.write_u8(address, value)


def test_flash_program_and_read():
    bus = _save_bus(FLASH_ID)
    assert bus.cartridge.save_type() is SaveTypeEnum.FLASH_64K
    _flash_program(bus, 0x0E000100, 0x37)
    assert bus.read_u8(0x0E000100) == 0x37


def test_flash_bits_only_clear():
    bus = _save_bus(FLASH_ID)
    _flash_program(bus, 0x0E000100, 0x37)
    _flash_program(bus, 0x0E000100, 0xF0)
    assert bus.read_u8(0x0E000100) == 0x30


def test_flash_id_mode_and_exit():
    bus = _save_bus(FLASH_ID)
    _flash_cmd(bus, 0x90)
    assert bus.read_u8(0x0E000000) == 0xBF
    assert bus.read_u8(0x0E000001) == 0xD4
    _flash_cmd(bus, 0xF0)
    assert bus.read_u8(0x0E000000) == 0xFF


def test_flash_sector_erase():
    bus = _save_bus(FLASH_ID)
    _flash_program(bus, 0x0E000100, 0x12)
    bus.write_u8(0x0E005555, 0xAA)
    bus.write_u8(0x0E002AAA, 0x55)
    bus.write_u8(0x0E005555, 0x80)
    bus.write_u8(0x0E005555, 0xAA)
    bus.write_u8(0x0E002AAA, 0x55)
    bus.write_u8(0x0E000000, 0x30)
    assert bus.read_u8(0x0E000100) == 0xFF


# ---------------------------------------------------------------------------
# EEPROM（bit-serial）
# ---------------------------------------------------------------------------
def _eeprom_send(bus: AddressBus, bits) -> None:
    for bit in bits:
        bus.write_u16(0x0DFFFF00, bit)


def _eeprom_write(bus: AddressBus, address: int, block: int, *, n_addr: int = 14) -> None:
    bits = [1, 0]
    bits += [(address >> (n_addr - 1 - i)) & 1 for i in range(n_addr)]
    bits += [(block >> (63 - i)) & 1 for i in range(64)]
    bits.append(0)
    _eeprom_send(bus, bits)


def _eeprom_read(bus: AddressBus, address: int, *, n_addr: int = 14) -> int:
    bits = [1, 1]
    bits += [(address >> (n_addr - 1 - i)) & 1 for i in range(n_addr)]
    bits.append(0)
    _eeprom_send(bus, bits)
    sample = [bus.read_u16(0x0DFFFF00) & 1 for _ in range(68)]
    value = 0
    for bit in sample[4:]:
        value = (value << 1) | bit
    return value


def test_eeprom_roundtrip_and_idle_ready():
    bus = _save_bus(EEPROM_ID)
    assert bus.cartridge.save_type() is SaveTypeEnum.EEPROM_8K
    assert bus.read_u16(0x0DFFFF00) == 1  # 閒置時 Ready

    value = 0x0123456789ABCDEF
    _eeprom_write(bus, 0x5A, value)
    assert _eeprom_read(bus, 0x5A) == value


def test_eeprom_pages_are_isolated():
    bus = _save_bus(EEPROM_ID)
    _eeprom_write(bus, 0, 0xFFFFFFFFFFFFFFFF)
    _eeprom_write(bus, 1, 0)
    assert _eeprom_read(bus, 0) == 0xFFFFFFFFFFFFFFFF
    assert _eeprom_read(bus, 1) == 0


# ---------------------------------------------------------------------------
# 磁碟 persist 與 auto-load
# ---------------------------------------------------------------------------
def test_flush_and_autoload_save_file(tmp_path):
    path = tmp_path / "game.gba"
    path.write_bytes(_program_rom(SRAM_ID, arm_words(0xEAFFFFFE)))
    emu = Emulator.from_rom(
        path, config=EmulatorConfig(boot_mode=BootMode.TEST_ROM_ONLY)
    )
    assert emu._cartridge.save_type() is SaveTypeEnum.SRAM
    emu.memory.write_u8(0x0E000000, 0x99)
    emu.cartridge_flush_to_disk()

    save_path = path.with_suffix(".sav")
    assert save_path.exists()
    assert save_path.read_bytes()[0] == 0x99

    emu2 = Emulator.from_rom(
        path, config=EmulatorConfig(boot_mode=BootMode.TEST_ROM_ONLY)
    )
    assert emu2.memory.read_u8(0x0E000000) == 0x99


def test_save_path_uses_rom_stem_and_reads_legacy(tmp_path):
    """``Dr_Mario.gba`` → ``Dr_Mario.sav``；舊式 ``Dr_Mario.gba.sav`` 仍可讀。"""

    path = tmp_path / "Dr_Mario.gba"
    path.write_bytes(_program_rom(SRAM_ID, arm_words(0xEAFFFFFE)))
    emu = Emulator.from_rom(
        path, config=EmulatorConfig(boot_mode=BootMode.TEST_ROM_ONLY)
    )
    emu.memory.write_u8(0x0E000000, 0x5A)
    emu.cartridge_flush_to_disk()
    assert path.with_suffix(".sav").exists()
    assert not Path(str(path) + ".sav").exists()
    emu.close()

    legacy = tmp_path / "Legacy.gba"
    legacy.write_bytes(_program_rom(SRAM_ID, arm_words(0xEAFFFFFE)))
    Path(str(legacy) + ".sav").write_bytes(b"\x77" + b"\xFF" * 0x7FFF)
    old = Emulator.from_rom(
        legacy, config=EmulatorConfig(boot_mode=BootMode.TEST_ROM_ONLY)
    )
    assert old.memory.read_u8(0x0E000000) == 0x77
    old.close()


def test_python_battery_dirty_tracks_save_writes(tmp_path):
    path = tmp_path / "dirty.gba"
    path.write_bytes(_program_rom(SRAM_ID, arm_words(0xEAFFFFFE)))
    emu = Emulator.from_rom(
        path, config=EmulatorConfig(boot_mode=BootMode.TEST_ROM_ONLY)
    )
    assert emu.battery_dirty is False
    emu.memory.write_u8(0x0E000000, 0x12)
    assert emu.battery_dirty is True
    emu.cartridge_flush_to_disk()
    assert emu.battery_dirty is False


def test_save_snapshot_roundtrip():
    bus = _save_bus(SRAM_ID)
    bus.write_u8(0x0E000010, 0xAB)
    snapshot = bus.cartridge.snapshot()
    assert snapshot.startswith(b"SRAM\0")

    bus.write_u8(0x0E000010, 0x00)
    bus.cartridge.restore(snapshot)
    assert bus.read_u8(0x0E000010) == 0xAB
