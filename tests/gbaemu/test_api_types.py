"""Phase 0 驗收：``api_types.py`` 全部型別可 import 且契約正確。"""

from __future__ import annotations

import dataclasses
from pathlib import Path

import pytest

from gbaemu import api_types
from gbaemu.api_types import (
    ActionSpec,
    AudioMode,
    BootMode,
    Button,
    CPUState,
    EmulatorConfig,
    EmulatorEvent,
    EventKind,
    FrameResult,
    GBAEnvConfig,
    MemoryRange,
    MemoryRegionInfo,
    MemoryRegionKind,
    ObservationConfig,
    SaveType,
    StepResult,
    TimingMode,
    VideoMode,
)
from gbaemu.errors import (
    BiosMissingError,
    GbaEmuError,
    HleUnsupportedSwiError,
    InvalidConfigError,
    SnapshotConfigMismatchError,
    SnapshotCorruptError,
    SnapshotError,
    SnapshotRomMismatchError,
    SnapshotVersionError,
)


def test_public_names_are_importable():
    for name in api_types.__all__:
        assert hasattr(api_types, name), name


def test_enum_values_match_spec():
    assert TimingMode.FUNCTIONAL.value == "functional"
    assert TimingMode.TIMED.value == "timed"
    assert TimingMode.TRACE.value == "trace"
    assert VideoMode.OFF.value == "off"
    assert VideoMode.FRAMEBUFFER.value == "framebuffer"
    assert AudioMode.DISABLED.value == "disabled"
    assert AudioMode.BUFFERED.value == "buffered"
    assert BootMode.HLE_ADVANCED.value == "hle_advanced"
    assert BootMode.TEST_ROM_ONLY.value == "test_rom_only"
    assert BootMode.REQUIRE_BIOS.value == "require_bios"
    assert [member.value for member in SaveType] == [
        "none",
        "sram",
        "flash_64k",
        "flash_128k",
        "eeprom_512b",
        "eeprom_8k",
        "detect",
    ]
    assert [member.value for member in Button] == [
        "a",
        "b",
        "select",
        "start",
        "right",
        "left",
        "up",
        "down",
        "r",
        "l",
    ]
    assert EventKind.FRAME_BOUNDARY.value == "frame_boundary"
    assert MemoryRegionKind.OPEN_BUS.value == "open_bus"


def test_config_field_order_and_defaults():
    fields = [field.name for field in dataclasses.fields(EmulatorConfig)]
    assert fields == [
        "bios_path",
        "boot_mode",
        "timing",
        "video",
        "audio",
        "deterministic",
        "seed",
        "hle_strict",
    ]
    config = EmulatorConfig()
    assert config.bios_path is None
    assert config.boot_mode is BootMode.HLE_ADVANCED
    assert config.timing is TimingMode.FUNCTIONAL
    assert config.video is VideoMode.FRAMEBUFFER
    assert config.audio is AudioMode.DISABLED
    assert config.deterministic is True
    assert config.seed == 0
    assert config.hle_strict is True
    config.validate()


def test_config_is_frozen():
    config = EmulatorConfig()
    with pytest.raises(dataclasses.FrozenInstanceError):
        config.seed = 1  # type: ignore[misc]


def test_require_bios_without_path_is_invalid():
    config = EmulatorConfig(boot_mode=BootMode.REQUIRE_BIOS)
    with pytest.raises(InvalidConfigError):
        config.validate()


def test_hle_with_bios_path_is_allowed():
    EmulatorConfig(bios_path=Path("bios.bin")).validate()


def test_config_rejects_wrong_types():
    with pytest.raises(InvalidConfigError):
        EmulatorConfig(boot_mode="hle_advanced").validate()  # type: ignore[arg-type]
    with pytest.raises(InvalidConfigError):
        EmulatorConfig(bios_path="bios.bin").validate()  # type: ignore[arg-type]
    with pytest.raises(InvalidConfigError):
        EmulatorConfig(deterministic=1).validate()  # type: ignore[arg-type]
    with pytest.raises(InvalidConfigError):
        EmulatorConfig(seed=True).validate()  # type: ignore[arg-type]


def test_result_types_are_frozen_and_fields_match():
    assert [field.name for field in dataclasses.fields(StepResult)] == [
        "cycles_executed",
        "cycles_remaining",
        "halted",
        "breakpoint_hit",
        "events",
    ]
    assert [field.name for field in dataclasses.fields(FrameResult)] == [
        "frame_index",
        "cycles",
        "vblank_started",
        "irq_pending",
        "halted",
        "events",
    ]
    event = EmulatorEvent(
        kind=EventKind.VBLANK_START,
        cycle=123,
        frame_index=0,
        scanline=160,
        channel=None,
        address=None,
        value=None,
    )
    result = StepResult(
        cycles_executed=123,
        cycles_remaining=0,
        halted=False,
        breakpoint_hit=None,
        events=(event,),
    )
    with pytest.raises(dataclasses.FrozenInstanceError):
        result.cycles_executed = 0  # type: ignore[misc]


def test_cpu_and_memory_views_are_immutable():
    state = CPUState(
        regs=tuple(range(16)),
        cpsr=0x1F,
        spsr=0,
        thumb=False,
        mode=0x1F,
        halted=False,
        cycles=0,
    )
    assert len(state.regs) == 16
    with pytest.raises(dataclasses.FrozenInstanceError):
        state.mode = 0x13  # type: ignore[misc]

    info = MemoryRegionInfo(MemoryRegionKind.EWRAM, 0x02000000, 0x40000, False)
    assert info.read_only is False


def test_action_spec_button_order_is_fixed():
    assert len(ActionSpec.button_order) == 10
    assert ActionSpec.button_order[0] is Button.A
    assert ActionSpec.button_order[-1] is Button.L
    fields = [field.name for field in dataclasses.fields(ActionSpec)]
    assert fields == ["mode", "discrete_sets"]


def test_observation_and_env_defaults():
    observation = ObservationConfig()
    assert observation.source == "screen"
    assert observation.grayscale is True
    assert observation.resize == (84, 84)
    assert observation.memory_ranges == ()
    env = GBAEnvConfig()
    assert env.frame_skip == 4
    assert env.max_episode_steps == 10_000
    assert env.action.mode == "multi_binary"
    assert MemoryRange("hp", 0x03000000, 2).size == 2


def test_error_hierarchy():
    assert issubclass(InvalidConfigError, GbaEmuError)
    assert issubclass(BiosMissingError, GbaEmuError)
    assert issubclass(HleUnsupportedSwiError, GbaEmuError)
    for error in (
        SnapshotCorruptError,
        SnapshotVersionError,
        SnapshotRomMismatchError,
        SnapshotConfigMismatchError,
    ):
        assert issubclass(error, SnapshotError)
    assert issubclass(SnapshotError, GbaEmuError)
