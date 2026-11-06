"""Snapshot header 版面與錯誤路徑（規格 5.7）。"""

from __future__ import annotations

import struct

import pytest

from gbaemu.errors import (
    SnapshotConfigMismatchError,
    SnapshotCorruptError,
    SnapshotRomMismatchError,
    SnapshotVersionError,
)
from gbaemu.state.snapshot import (
    SNAPSHOT_FORMAT_VERSION,
    SNAPSHOT_HEADER,
    SNAPSHOT_HEADER_SIZE,
    SNAPSHOT_MAGIC,
    build_snapshot_header,
    parse_snapshot,
)

ROM_SHA = b"\x01" * 32
CONFIG_SHA = b"\x02" * 32


def _build(payload: bytes = b"payload") -> bytes:
    return build_snapshot_header(
        payload, rom_sha256=ROM_SHA, config_sha256=CONFIG_SHA
    )


def test_header_layout_is_stable():
    assert SNAPSHOT_HEADER.size == 90
    assert SNAPSHOT_HEADER.size == struct.calcsize("<4sI3H32s32sQI")
    assert SNAPSHOT_MAGIC == b"GEMU"
    assert SNAPSHOT_FORMAT_VERSION == 1


def test_roundtrip():
    data = _build(b"abc")
    assert len(data) == SNAPSHOT_HEADER_SIZE + 3
    header = parse_snapshot(data, rom_sha256=ROM_SHA, config_sha256=CONFIG_SHA)
    assert header.magic == b"GEMU"
    assert header.format_version == 1
    assert header.emulator_version == (0, 1, 0)
    assert header.rom_sha256 == ROM_SHA
    assert header.config_sha256 == CONFIG_SHA
    assert header.payload_length == 3
    assert header.payload_crc32 == 0x352441C2  # zlib.crc32(b"abc")


def test_short_and_corrupt_magic():
    with pytest.raises(SnapshotCorruptError):
        parse_snapshot(b"")
    data = bytearray(_build())
    data[0:4] = b"XXXX"
    with pytest.raises(SnapshotCorruptError):
        parse_snapshot(bytes(data))


def test_payload_length_and_crc_checks():
    data = _build(b"abc")
    with pytest.raises(SnapshotCorruptError):
        parse_snapshot(data[:-1])

    corrupted = bytearray(data)
    corrupted[-1] ^= 0xFF
    with pytest.raises(SnapshotCorruptError):
        parse_snapshot(bytes(corrupted))


def test_version_mismatch():
    data = bytearray(_build())
    data[4:8] = struct.pack("<I", 99)
    with pytest.raises(SnapshotVersionError):
        parse_snapshot(bytes(data))


def test_rom_and_config_mismatch():
    data = _build()
    with pytest.raises(SnapshotRomMismatchError):
        parse_snapshot(data, rom_sha256=b"\x03" * 32)
    with pytest.raises(SnapshotConfigMismatchError):
        parse_snapshot(data, config_sha256=b"\x03" * 32)

    # 不提供比對 digest 時只做格式驗證
    parse_snapshot(data)


def test_build_rejects_bad_digests():
    with pytest.raises(ValueError):
        build_snapshot_header(b"", rom_sha256=b"short", config_sha256=CONFIG_SHA)
    with pytest.raises(ValueError):
        build_snapshot_header(b"", rom_sha256=ROM_SHA, config_sha256=b"short")
    with pytest.raises(ValueError):
        build_snapshot_header(
            b"", rom_sha256=ROM_SHA, config_sha256=CONFIG_SHA, emulator_version=(1, 2)
        )
