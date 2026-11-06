"""Phase 0 測試共用工具：合成 GBA ROM header。"""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HEADER_SIZE = 0xC0


def _pad(raw: bytes, size: int) -> bytes:
    return raw[:size].ljust(size, b"\x00")


def build_rom(
    *,
    size: int = 0x200,
    title: bytes = b"TESTGAME",
    game_code: bytes = b"TEST",
    maker_code: bytes = b"01",
    entry_point: int = 0x08000000,
    fixed_value: int = 0x96,
    checksum_delta: int = 0,
    payload: bytes = b"",
) -> bytes:
    """建立帶合法 complement check 的最小 ROM。"""

    if size < HEADER_SIZE:
        raise ValueError(f"size 至少 {HEADER_SIZE}")
    rom = bytearray(size)
    rom[0x00:0x04] = (entry_point & 0xFFFFFFFF).to_bytes(4, "little")
    rom[0xA0:0xAC] = _pad(title, 12)
    rom[0xAC:0xB0] = _pad(game_code, 4)
    rom[0xB0:0xB2] = _pad(maker_code, 2)
    rom[0xB2] = fixed_value & 0xFF
    rom[0xB3] = 0x00
    rom[0xB4] = 0x00
    rom[0xBC] = 0x00
    rom[0xBD] = 0x00
    calculated = (-(sum(rom[0xA0:0xBD]) + 0x19)) & 0xFF
    rom[0xBD] = (calculated + checksum_delta) & 0xFF
    if payload:
        end = min(size, HEADER_SIZE + len(payload))
        rom[HEADER_SIZE:end] = payload[: end - HEADER_SIZE]
    return bytes(rom)


def write_rom(path: Path, rom: bytes) -> Path:
    path.write_bytes(rom)
    return path
