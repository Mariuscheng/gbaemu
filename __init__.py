"""gbaemu —— CPython 的 GBA 模擬器與 RL 介面。

Phase 0 骨架：ROM 載入、address bus、HLE post-boot、SWI dispatch table、
memory/CPU/video/input 的唯讀觀測，以及 ``inspect-rom`` CLI。

權威規格：``docs/GBA 模擬器與 RL 介面設計規格（Struct 完整版）.md``。
"""

from __future__ import annotations

from .api_types import (
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
from .emulator import Emulator
from .native import NativeEmulator, open_emulator
from .rl.wrappers import GbaApp
from .errors import (
    BiosChecksumError,
    BiosMissingError,
    BreakpointError,
    GbaEmuError,
    HleUnsupportedSwiError,
    InvalidConfigError,
    ReadOnlyMemoryError,
    RomInvalidError,
    SnapshotConfigMismatchError,
    SnapshotCorruptError,
    SnapshotError,
    SnapshotRomMismatchError,
    SnapshotVersionError,
    UnsupportedSaveTypeError,
)

__version__ = "0.1.0"
__version_info__ = (0, 1, 0)

__all__ = [
    "__version__",
    "__version_info__",
    "Emulator",
    "NativeEmulator",
    "open_emulator",
    "GbaApp",
    "EmulatorConfig",
    "StepResult",
    "FrameResult",
    "EmulatorEvent",
    "EventKind",
    "CPUState",
    "MemoryRegionInfo",
    "MemoryRegionKind",
    "MemoryRange",
    "ObservationConfig",
    "ActionSpec",
    "GBAEnvConfig",
    "TimingMode",
    "VideoMode",
    "AudioMode",
    "BootMode",
    "SaveType",
    "Button",
    "GbaEmuError",
    "InvalidConfigError",
    "RomInvalidError",
    "BiosMissingError",
    "BiosChecksumError",
    "UnsupportedSaveTypeError",
    "HleUnsupportedSwiError",
    "ReadOnlyMemoryError",
    "BreakpointError",
    "SnapshotError",
    "SnapshotCorruptError",
    "SnapshotVersionError",
    "SnapshotRomMismatchError",
    "SnapshotConfigMismatchError",
]
