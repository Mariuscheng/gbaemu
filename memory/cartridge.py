"""Game Pak ROM 的載入、header 解析與 cartridge 介面。

GBATEK: GBA Cartridges - GBA Cartridge Header。Phase 0 只實作唯讀 ROM 與
header 分析；存檔控制器（SRAM/Flash/EEPROM）在 Phase 3 以本模組的
``Cartridge`` protocol 擴充。
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, runtime_checkable

from ..api_types import SaveType
from ..bus.regions import ROM_BASE, ROM_WINDOW_SIZE
from ..errors import RomInvalidError, UnsupportedSaveTypeError
from .savedata import SaveEEPROM, SaveFlash, SaveSRAM, detect_save

HEADER_SIZE = 0xC0
HEADER_CHECKSUM_OFFSET = 0xBD
FIXED_VALUE_OFFSET = 0xB2
EXPECTED_FIXED_VALUE = 0x96


@dataclass(frozen=True, slots=True)
class RomHeader:
    """GBA cartridge header 的可讀表示（只保存唯讀 values）。"""

    entry_point: int
    logo: bytes
    title: str
    game_code: str
    maker_code: str
    fixed_value: int
    main_unit_code: int
    device_type: int
    software_version: int
    complement_check: int
    complement_check_calculated: int

    @property
    def fixed_value_ok(self) -> bool:
        return self.fixed_value == EXPECTED_FIXED_VALUE

    @property
    def complement_check_ok(self) -> bool:
        return self.complement_check == self.complement_check_calculated


def compute_complement_check(header: bytes) -> int:
    """計算 header 的 complement check（GBATEK: 0BDh - Complement check）。

    公式：``-(sum(header[0xA0:0xBD]) + 0x19) & 0xFF``。
    """

    if len(header) < HEADER_CHECKSUM_OFFSET + 1:
        raise ValueError("header 長度不足以計算 complement check")
    return (-(sum(header[0xA0:HEADER_CHECKSUM_OFFSET]) + 0x19)) & 0xFF


def _decode_ascii(raw: bytes) -> str:
    text = raw.split(b"\x00", 1)[0].decode("ascii", "replace")
    return text.rstrip(" ")


def parse_rom_header(rom: bytes) -> RomHeader:
    """解析 ``rom[0:0xC0]``；ROM 太小 raise :class:`RomInvalidError`。"""

    if len(rom) < HEADER_SIZE:
        raise RomInvalidError(
            f"ROM 太小：需要至少 {HEADER_SIZE} bytes（0xC0）的 header，得到 {len(rom)}"
        )

    header = bytes(rom[:HEADER_SIZE])
    return RomHeader(
        entry_point=int.from_bytes(header[0x00:0x04], "little"),
        logo=header[0x04:0xA0],
        title=_decode_ascii(header[0xA0:0xAC]),
        game_code=_decode_ascii(header[0xAC:0xB0]),
        maker_code=_decode_ascii(header[0xB0:0xB2]),
        fixed_value=header[0xB2],
        main_unit_code=header[0xB3],
        device_type=header[0xB4],
        software_version=header[0xBC],
        complement_check=header[HEADER_CHECKSUM_OFFSET],
        complement_check_calculated=compute_complement_check(header),
    )


def load_rom_file(path: str | Path) -> bytes:
    """讀取 ROM 檔；任何 OS 錯誤轉成 :class:`RomInvalidError`。"""

    rom_path = Path(path)
    try:
        return rom_path.read_bytes()
    except OSError as exc:
        raise RomInvalidError(f"無法讀取 ROM '{rom_path}': {exc}") from exc


@runtime_checkable
class Cartridge(Protocol):
    """特殊硬體與存檔媒體的抽象（規格 3.5）。"""

    def read_rom(self, address: int) -> int: ...

    def read_save(self, address: int) -> int: ...

    def write_save(self, address: int, value: int) -> None: ...

    def save_type(self) -> SaveType: ...

    def snapshot(self) -> bytes: ...

    def restore(self, state: bytes) -> None: ...


class RomCartridge:
    """ROM cartridge＋可選的備份記憶體（SRAM／Flash／EEPROM）。"""

    def __init__(self, rom: bytes, *, save_type: SaveType = SaveType.NONE) -> None:
        if len(rom) < HEADER_SIZE:
            raise RomInvalidError(
                f"ROM 太小：至少需要 {HEADER_SIZE} bytes，得到 {len(rom)}"
            )
        self._rom = bytes(rom)
        self._header = parse_rom_header(self._rom)
        self._save = (
            _make_save(save_type) if save_type is not SaveType.NONE else detect_save(self._rom)
        )
        self._save_type = _save_type_of(self._save) if self._save is not None else SaveType.NONE

    @property
    def header(self) -> RomHeader:
        return self._header

    @property
    def save(self):
        """備份後端（SaveSRAM／SaveFlash／SaveEEPROM）或 None。"""

        return self._save

    @property
    def save_kind(self) -> str | None:
        return None if self._save is None else self._save.kind

    @property
    def rom_size(self) -> int:
        return len(self._rom)

    @property
    def rom_bytes(self) -> bytes:
        return self._rom

    def read_rom(self, address: int) -> int:
        # 三個 32 MiB Game Pak 視窗互為鏡像；小 ROM 在視窗內重複。
        offset = (address - ROM_BASE) % ROM_WINDOW_SIZE
        return self._rom[offset % len(self._rom)]

    def read_save(self, address: int) -> int:
        if self._save is None:
            return 0xFF
        return self._save.read8(address & 0xFFFF)

    def write_save(self, address: int, value: int) -> None:
        if self._save is None:
            return
        self._save.write8(address & 0xFFFF, value & 0xFF)

    def save_type(self) -> SaveType:
        return self._save_type

    def snapshot(self) -> bytes:
        """備份記憶體內容（kind + 原始 bytes；EEPROM 的串流狀態不保存）。"""

        if self._save is None:
            return b""
        return self._save.kind.encode("ascii") + b"\0" + self._save.export()

    def restore(self, state: bytes) -> None:
        if self._save is None:
            return
        kind, _, payload = state.partition(b"\0")
        if kind.decode("ascii") != self._save.kind:
            raise UnsupportedSaveTypeError(
                f"snapshot 的 save 類型 {kind!r} 與 cartridge {self._save.kind} 不符"
            )
        self._save.load(payload)


_SAVE_CLASSES = {
    SaveType.SRAM: lambda: SaveSRAM(),
    SaveType.FLASH_64K: lambda: SaveFlash(0x10000),
    SaveType.FLASH_128K: lambda: SaveFlash(0x20000),
    SaveType.EEPROM_512B: lambda: SaveEEPROM(0x200),
    SaveType.EEPROM_8K: lambda: SaveEEPROM(0x2000),
}


def _make_save(save_type: SaveType):
    factory = _SAVE_CLASSES.get(save_type)
    if factory is None:
        raise UnsupportedSaveTypeError(f"save 類型 {save_type.value} 尚未實作")
    return factory()


def _save_type_of(save) -> SaveType:
    if isinstance(save, SaveSRAM):
        return SaveType.SRAM
    if isinstance(save, SaveFlash):
        return SaveType.FLASH_128K if save.size == 0x20000 else SaveType.FLASH_64K
    if isinstance(save, SaveEEPROM):
        return SaveType.EEPROM_8K if save.size == 0x2000 else SaveType.EEPROM_512B
    return SaveType.NONE


__all__ = [
    "HEADER_SIZE",
    "EXPECTED_FIXED_VALUE",
    "RomHeader",
    "compute_complement_check",
    "parse_rom_header",
    "load_rom_file",
    "Cartridge",
    "RomCartridge",
]
