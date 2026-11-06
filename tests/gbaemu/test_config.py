"""Config canonical serialization（snapshot config hash 的基礎）。"""

from __future__ import annotations

import hashlib

from gbaemu.api_types import AudioMode, BootMode, EmulatorConfig, VideoMode
from gbaemu.config import canonical_config_bytes, config_sha256, validate_config


def test_canonical_bytes_are_stable_and_sorted():
    config = EmulatorConfig()
    first = canonical_config_bytes(config)
    second = canonical_config_bytes(EmulatorConfig())
    assert first == second
    # sort_keys=True：audio 一定排在 boot_mode 之前
    assert first.index(b'"audio"') < first.index(b'"boot_mode"')
    assert b" " not in first


def test_config_hash_changes_with_behavioral_fields():
    base = config_sha256(EmulatorConfig())
    assert len(base) == 32
    assert base == hashlib.sha256(canonical_config_bytes(EmulatorConfig())).digest()

    variants = [
        EmulatorConfig(video=VideoMode.OFF),
        EmulatorConfig(audio=AudioMode.BUFFERED),
        EmulatorConfig(boot_mode=BootMode.TEST_ROM_ONLY),
        EmulatorConfig(hle_strict=False),
        EmulatorConfig(seed=1),
        EmulatorConfig(deterministic=False),
    ]
    for variant in variants:
        assert config_sha256(variant) != base


def test_bios_path_is_not_part_of_config_hash():
    from pathlib import Path

    assert config_sha256(EmulatorConfig(bios_path=Path("a.bin"))) == config_sha256(
        EmulatorConfig(bios_path=Path("b.bin"))
    )


def test_validate_config_accepts_default():
    validate_config(EmulatorConfig())
