from __future__ import annotations

import pytest

from .helpers import ROOT, build_rom


@pytest.fixture
def rom_bytes() -> bytes:
    return build_rom()


@pytest.fixture
def rom_path(tmp_path, rom_bytes):
    path = tmp_path / "test.gba"
    path.write_bytes(rom_bytes)
    return path


@pytest.fixture
def hello_rom_path():
    path = ROOT / "test-rom" / "ppu" / "hello.gba"
    if not path.exists():
        pytest.skip(
            "需要外部硬體測試 ROM（test-rom/ppu/hello.gba）；"
            "test-rom/ 唔隨 repo 提供，見 README"
        )
    return path
