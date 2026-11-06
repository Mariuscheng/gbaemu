"""Snapshot 二進位格式（規格 5.7）：header 與分段 payload。

Header 固定 90 bytes（magic／version／emu_version／rom_sha256／config_sha256／
payload 長度／CRC-32）。payload 由數個 `4-byte ID + Q 長度 + data` 的區段串接，
區段 ID 見 `SECTION_*`；還原時依 ID 查找，缺少必要區段視為 corrupt。
"""

from __future__ import annotations

import struct
import zlib
from dataclasses import dataclass

from ..errors import (
    SnapshotConfigMismatchError,
    SnapshotCorruptError,
    SnapshotRomMismatchError,
    SnapshotVersionError,
)

SNAPSHOT_MAGIC = b"GEMU"
SNAPSHOT_FORMAT_VERSION = 1
EMULATOR_VERSION = (0, 1, 0)

# 區段 ID（4 bytes，最後一個 byte 為 0）
SECTION_CPU = b"CPU\0"
SECTION_BUS = b"BUS\0"
SECTION_PPU = b"PPU\0"
SECTION_DMA = b"DMA\0"
SECTION_TMR = b"TMR\0"
SECTION_IRQ = b"IRQ\0"
SECTION_KEY = b"KEY\0"
SECTION_CRT = b"CRT\0"
SECTION_SCH = b"SCH\0"

REQUIRED_SECTIONS = (
    SECTION_CPU,
    SECTION_BUS,
    SECTION_PPU,
    SECTION_DMA,
    SECTION_TMR,
    SECTION_IRQ,
    SECTION_KEY,
    SECTION_CRT,
    SECTION_SCH,
)

SECTION_HEADER = struct.Struct("<4sQ")

# <4s I 3H 32s 32s Q I
#  magic, version, emu_ver[3], rom_sha256, config_sha256, payload_len, payload_crc32
SNAPSHOT_HEADER: struct.Struct = struct.Struct("<4sI3H32s32sQI")
SNAPSHOT_HEADER_SIZE = SNAPSHOT_HEADER.size  # 90 bytes


@dataclass(frozen=True, slots=True)
class SnapshotHeader:
    magic: bytes
    format_version: int
    emulator_version: tuple[int, int, int]
    rom_sha256: bytes
    config_sha256: bytes
    payload_length: int
    payload_crc32: int


def build_snapshot_header(
    payload: bytes,
    *,
    rom_sha256: bytes,
    config_sha256: bytes,
    emulator_version: tuple[int, int, int] = EMULATOR_VERSION,
) -> bytes:
    """回傳 header + payload（尚未實作各子系統 payload 的產生）。"""

    _require_digest(rom_sha256, "rom_sha256")
    _require_digest(config_sha256, "config_sha256")
    if len(emulator_version) != 3:
        raise ValueError("emulator_version 必須是 (major, minor, patch)")
    crc = zlib.crc32(payload) & 0xFFFFFFFF
    header = SNAPSHOT_HEADER.pack(
        SNAPSHOT_MAGIC,
        SNAPSHOT_FORMAT_VERSION,
        *emulator_version,
        rom_sha256,
        config_sha256,
        len(payload),
        crc,
    )
    return header + payload


def parse_snapshot(
    data: bytes,
    *,
    rom_sha256: bytes | None = None,
    config_sha256: bytes | None = None,
) -> SnapshotHeader:
    """驗證並解析 snapshot；驗證順序依規格 5.7。"""

    if len(data) < SNAPSHOT_HEADER_SIZE:
        raise SnapshotCorruptError(
            f"snapshot 長度 {len(data)} 小於 header {SNAPSHOT_HEADER_SIZE}"
        )

    (
        magic,
        format_version,
        version_major,
        version_minor,
        version_patch,
        stored_rom_sha256,
        stored_config_sha256,
        payload_length,
        payload_crc32,
    ) = SNAPSHOT_HEADER.unpack_from(data, 0)

    if magic != SNAPSHOT_MAGIC:
        raise SnapshotCorruptError(f"snapshot magic 不符：{magic!r}")

    payload = data[SNAPSHOT_HEADER_SIZE:]
    if payload_length != len(payload):
        raise SnapshotCorruptError(
            f"payload 長度不符：header={payload_length} actual={len(payload)}"
        )
    actual_crc = zlib.crc32(payload) & 0xFFFFFFFF
    if actual_crc != payload_crc32:
        raise SnapshotCorruptError(
            f"payload CRC-32 不符：header=0x{payload_crc32:08X} actual=0x{actual_crc:08X}"
        )

    if format_version != SNAPSHOT_FORMAT_VERSION:
        raise SnapshotVersionError(
            f"snapshot 格式版本 {format_version} 不受支援（支援 {SNAPSHOT_FORMAT_VERSION}）"
        )

    if rom_sha256 is not None:
        _require_digest(rom_sha256, "rom_sha256")
        if stored_rom_sha256 != rom_sha256:
            raise SnapshotRomMismatchError("snapshot 的 ROM SHA-256 與目前 ROM 不符")

    if config_sha256 is not None:
        _require_digest(config_sha256, "config_sha256")
        if stored_config_sha256 != config_sha256:
            raise SnapshotConfigMismatchError("snapshot 的 config SHA-256 與目前設定不符")

    return SnapshotHeader(
        magic=magic,
        format_version=format_version,
        emulator_version=(version_major, version_minor, version_patch),
        rom_sha256=stored_rom_sha256,
        config_sha256=stored_config_sha256,
        payload_length=payload_length,
        payload_crc32=payload_crc32,
    )


def _require_digest(value: bytes, name: str) -> None:
    if not isinstance(value, (bytes, bytearray)) or len(value) != 32:
        raise ValueError(f"{name} 必須是 32-byte SHA-256 digest")


# ---------------------------------------------------------------------------
# Payload 區段
# ---------------------------------------------------------------------------
def pack_sections(sections: dict[bytes, bytes]) -> bytes:
    """把 ``{4-byte ID: data}`` 打包成 payload（ID + Q 長度 + data）。"""

    parts = []
    for section_id, data in sections.items():
        if len(section_id) != 4:
            raise ValueError(f"區段 ID 必須是 4 bytes：{section_id!r}")
        parts.append(SECTION_HEADER.pack(section_id, len(data)))
        parts.append(data)
    return b"".join(parts)


def unpack_sections(payload: bytes) -> dict[bytes, bytes]:
    """解析 payload；長度不足或重複／未知的區段 → ``SnapshotCorruptError``。"""

    sections: dict[bytes, bytes] = {}
    offset = 0
    total = len(payload)
    while offset < total:
        if offset + SECTION_HEADER.size > total:
            raise SnapshotCorruptError("payload 區段標頭被截斷")
        section_id, length = SECTION_HEADER.unpack_from(payload, offset)
        offset += SECTION_HEADER.size
        if offset + length > total:
            raise SnapshotCorruptError(f"payload 區段 {section_id!r} 長度超出範圍")
        if section_id in sections:
            raise SnapshotCorruptError(f"payload 區段重複：{section_id!r}")
        sections[section_id] = payload[offset : offset + length]
        offset += length
    return sections


def require_sections(sections: dict[bytes, bytes]) -> None:
    missing = [section for section in REQUIRED_SECTIONS if section not in sections]
    if missing:
        raise SnapshotCorruptError(f"payload 缺少必要區段：{missing!r}")


__all__ = [
    "SNAPSHOT_MAGIC",
    "SNAPSHOT_FORMAT_VERSION",
    "EMULATOR_VERSION",
    "SNAPSHOT_HEADER",
    "SNAPSHOT_HEADER_SIZE",
    "SECTION_CPU",
    "SECTION_BUS",
    "SECTION_PPU",
    "SECTION_DMA",
    "SECTION_TMR",
    "SECTION_IRQ",
    "SECTION_KEY",
    "SECTION_CRT",
    "SECTION_SCH",
    "REQUIRED_SECTIONS",
    "SECTION_HEADER",
    "pack_sections",
    "unpack_sections",
    "require_sections",
    "SnapshotHeader",
    "build_snapshot_header",
    "parse_snapshot",
]
