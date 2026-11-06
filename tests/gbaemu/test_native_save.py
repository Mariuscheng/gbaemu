"""Native backend 備份記憶體（電池存檔）持久化測試。

Rust core 本身有 SRAM／Flash／序列 EEPROM；這裡驗證：
1. save media 偵測同 Python reference 一致；
2. EEPROM 位元協定（遊戲以 DMA 送出的形式）寫入／讀回正確；
3. ``cartridge_flush_to_disk()`` 會原子寫出 ``<rom>.sav``，重開會載返；
4. ``reset()`` 唔會清掉電池存檔；
5. 同 Python reference 的 ``.sav`` 互通。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from gbaemu import Emulator, EmulatorConfig, GbaEmuError, TimingMode

from .helpers import build_rom

_native = pytest.importorskip("gbaemu._native")
from gbaemu.native import NativeEmulator  # noqa: E402


def _rom(path: Path, signature: bytes | None, size: int = 0x1000) -> Path:
    rom = bytearray(build_rom(size=size))
    if signature is not None:
        rom[0x100 : 0x100 + len(signature)] = signature
    path.write_bytes(rom)
    return path


def _eeprom_write(bus, addr: int, dword: int, n_addr: int = 14) -> None:
    bits = [1, 0]
    bits += [(addr >> (n_addr - 1 - i)) & 1 for i in range(n_addr)]
    bits += [(dword >> (63 - i)) & 1 for i in range(64)]
    bits.append(0)
    for bit in bits:
        bus.write_u16(0x0DFFFF00, bit)


def _eeprom_read(bus, addr: int, n_addr: int = 14) -> int:
    bits = [1, 1]
    bits += [(addr >> (n_addr - 1 - i)) & 1 for i in range(n_addr)]
    bits.append(0)
    for bit in bits:
        bus.write_u16(0x0DFFFF00, bit)
    sample = [bus.read_u16(0x0DFFFF00) & 1 for _ in range(68)]
    value = 0
    for bit in sample[4:]:
        value = (value << 1) | bit
    return value


def test_save_kind_detection(tmp_path):
    cases = {
        b"EEPROM_V124": "eeprom8k",
        b"EEPROM_V111": "eeprom512",
        b"SRAM_V113": "sram",
        b"FLASH_V124": "flash64",
        b"FLASH1M_V102": "flash128",
    }
    for signature, expected in cases.items():
        emu = NativeEmulator.from_rom(_rom(tmp_path / f"{expected}.gba", signature))
        assert emu.save_kind == expected
        emu.close()
    emu = NativeEmulator.from_rom(_rom(tmp_path / "none.gba", None))
    assert emu.save_kind == "none"
    emu.close()


def test_eeprom_write_read_roundtrip(tmp_path):
    emu = NativeEmulator.from_rom(_rom(tmp_path / "eeprom.gba", b"EEPROM_V124"))
    value = 0x0123456789ABCDEF
    _eeprom_write(emu.memory, 0x5A, value)
    assert _eeprom_read(emu.memory, 0x5A) == value
    emu.close()


def test_flush_writes_sav_and_reloads(tmp_path):
    path = _rom(tmp_path / "battery.gba", b"EEPROM_V124")
    emu = NativeEmulator.from_rom(path)
    value = 0xDEADBEEFCAFEF00D
    _eeprom_write(emu.memory, 0x2A, value)
    emu.cartridge_flush_to_disk()
    sav = Path(str(path) + ".sav")
    assert sav.exists()
    assert sav.stat().st_size == 0x2000
    emu.close()

    again = NativeEmulator.from_rom(path)
    data = bytes(again._core.save_ram())
    assert data[0x2A * 8 : 0x2A * 8 + 8] == value.to_bytes(8, "little")
    assert _eeprom_read(again.memory, 0x2A) == value
    again.close()


def test_reset_keeps_battery_save(tmp_path):
    path = _rom(tmp_path / "reset.gba", b"EEPROM_V124")
    emu = NativeEmulator.from_rom(path)
    _eeprom_write(emu.memory, 3, 0x1122334455667788)
    emu.reset()
    assert _eeprom_read(emu.memory, 3) == 0x1122334455667788
    emu.close()


def test_flush_without_save_media_raises(tmp_path):
    emu = NativeEmulator.from_rom(_rom(tmp_path / "nosave.gba", None))
    with pytest.raises(GbaEmuError):
        emu.cartridge_flush_to_disk()
    emu.close()


def test_python_reference_reads_native_sav(tmp_path):
    path = _rom(tmp_path / "cross.gba", b"SRAM_V113")
    native = NativeEmulator.from_rom(path)
    native.memory.write_u8(0x0E000000, 0x99)
    native.memory.write_u8(0x0E000010, 0x42)
    native.cartridge_flush_to_disk()
    native.close()

    python = Emulator.from_rom(path, config=EmulatorConfig(timing=TimingMode.FUNCTIONAL))
    assert python._cartridge.save.export()[0] == 0x99
    assert python._cartridge.save.export()[0x10] == 0x42
    python.close()


def test_python_reference_sav_loads_in_native(tmp_path):
    path = _rom(tmp_path / "cross2.gba", b"SRAM_V113")
    python = Emulator.from_rom(path, config=EmulatorConfig(timing=TimingMode.FUNCTIONAL))
    python._cartridge.save.data[0] = 0x5A
    python._cartridge.save.data[0x20] = 0xA5
    python.cartridge_flush_to_disk()
    python.close()

    native = NativeEmulator.from_rom(path)
    data = bytes(native._core.save_ram())
    assert data[0] == 0x5A
    assert data[0x20] == 0xA5
    native.close()


def test_mismatched_sav_size_is_ignored(tmp_path):
    path = _rom(tmp_path / "bad.gba", b"SRAM_V113")
    Path(str(path) + ".sav").write_bytes(b"\x12\x34")
    emu = NativeEmulator.from_rom(path)
    assert bytes(emu._core.save_ram()) == b"\xFF" * 0x8000
    emu.close()


def test_python_reference_reads_native_eeprom_sav(tmp_path):
    path = _rom(tmp_path / "eeprom_cross.gba", b"EEPROM_V124")
    native = NativeEmulator.from_rom(path)
    value = 0x0123456789ABCDEF
    _eeprom_write(native.memory, 0x10, value)
    native.cartridge_flush_to_disk()
    native.close()

    python = Emulator.from_rom(path, config=EmulatorConfig(timing=TimingMode.FUNCTIONAL))
    data = python._cartridge.save.export()
    assert data[0x10 * 8 : 0x10 * 8 + 8] == value.to_bytes(8, "little")
    python.close()


def test_flash128_bank_switch_matches_reference(tmp_path):
    """Flash 128 KiB：bank 切換、program、sector erase 要同 Python reference 一致。"""

    from gbaemu.memory.savedata import SaveFlash

    ref = SaveFlash(0x20000)
    emu = NativeEmulator.from_rom(_rom(tmp_path / "flash128.gba", b"FLASH1M_V102"))

    def write(offset: int, value: int) -> None:
        emu.memory.write_u8(0x0E000000 + offset, value)
        ref.write8(offset, value)

    def program(offset: int, value: int) -> None:
        write(0x5555, 0xAA)
        write(0x2AAA, 0x55)
        write(0x5555, 0xA0)
        write(offset, value)

    for bank, offset, value in [(0, 0x0123, 0x11), (1, 0x0123, 0x22)]:
        write(0, bank)  # 128K bank 切換
        program(offset, value)
    assert bytes(emu._core.save_ram()) == bytes(ref.data)

    write(0x5555, 0xAA)
    write(0x2AAA, 0x55)
    write(0x5555, 0x80)
    write(0x5555, 0xAA)
    write(0x2AAA, 0x55)
    write(0x0000, 0x30)  # 抹除目前 bank 的 sector 0
    assert bytes(emu._core.save_ram()) == bytes(ref.data)
    emu.close()


def test_gbaapp_stop_flushes_battery_save(tmp_path):
    """GUI 關閉流程（GbaApp.stop）要寫出 .sav，遊戲內存檔先唔會唔見。"""

    from gbaemu.rl import GbaApp

    path = _rom(tmp_path / "app.gba", b"SRAM_V113")
    app = GbaApp(str(path), window="null")
    app.emu.memory.write_u8(0x0E000000, 0x77)
    app.emu.memory.write_u8(0x0E000010, 0x88)
    app.stop()

    sav = Path(str(path) + ".sav")
    assert sav.exists()
    assert sav.stat().st_size == 0x8000
    assert sav.read_bytes()[0] == 0x77
    assert sav.read_bytes()[0x10] == 0x88


def test_gbaapp_stop_skips_sav_when_game_did_not_save(tmp_path):
    """冇喺遊戲入面存檔就唔應該自動改動／建立 .sav。"""

    from gbaemu.rl import GbaApp

    path = _rom(tmp_path / "untouched.gba", b"SRAM_V113")
    app = GbaApp(str(path), window="null")
    assert app.emu.battery_dirty is False
    app.stop()

    assert not Path(str(path) + ".sav").exists()


def test_battery_dirty_tracks_save_writes(tmp_path):
    emu = NativeEmulator.from_rom(_rom(tmp_path / "dirty.gba", b"SRAM_V113"))
    assert emu.battery_dirty is False
    emu.memory.write_u8(0x0E000000, 0x12)
    assert emu.battery_dirty is True
    emu.cartridge_flush_to_disk()
    assert emu.battery_dirty is False
    emu.close()
