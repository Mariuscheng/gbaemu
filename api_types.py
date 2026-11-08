"""對外公共資料型別。

本模組是規格第 5 章的單一權威定義（single source of truth）。其他章節與其他模組
只可引用這裡的名稱，不得重複定義或私下改名。

設計約束（規格 5 開頭）：

* 公共型別一律 ``@dataclass(frozen=True, slots=True)``。
* ``frozen=True`` 不會令內含的 ``list``/``dict`` 不可變，因此欄位只使用
  ``tuple``、``bytes`` 等真正不可變的容器。
* 內部可變狀態（``Arm7CoreState``、``PpuState`` 等）定義在各自模組，不在這裡。
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import ClassVar, Literal

from .errors import InvalidConfigError


class TimingMode(Enum):
    """模擬時間精確度；與 ``deterministic`` 正交（規格第 8 章）。"""

    FUNCTIONAL = "functional"  # instruction/block 為單位，週期近似
    TIMED = "timed"  # 依 bus、DMA、PPU、timer 事件計算 cycle
    TRACE = "trace"  # timed + 可重播事件流（差異測試用）


class VideoMode(Enum):
    OFF = "off"  # 不產生 framebuffer，RL 高速模式
    FRAMEBUFFER = "framebuffer"  # 產生 240x160 framebuffer


class AudioMode(Enum):
    DISABLED = "disabled"
    BUFFERED = "buffered"


class BootMode(Enum):
    HLE_ADVANCED = "hle_advanced"  # 進階 HLE：預設，完整 SWI 功能表（見 2.1）
    TEST_ROM_ONLY = "test_rom_only"  # 最小驗證路徑，不進 BIOS 流程
    REQUIRE_BIOS = "require_bios"  # 要求真實 BIOS（等價測試用）


class SaveType(Enum):
    NONE = "none"
    SRAM = "sram"  # 32 KiB（最大 64 KiB）
    FLASH_64K = "flash_64k"  # 64 KiB SST/Macronix
    FLASH_128K = "flash_128k"  # 128 KiB
    EEPROM_512B = "eeprom_512b"
    EEPROM_8K = "eeprom_8k"
    DETECT = "detect"  # 由 cartridge 模組自動偵測


class Button(Enum):
    A = "a"
    B = "b"
    SELECT = "select"
    START = "start"
    RIGHT = "right"
    LEFT = "left"
    UP = "up"
    DOWN = "down"
    R = "r"
    L = "l"


class EventKind(Enum):
    FRAME_BOUNDARY = "frame_boundary"
    VBLANK_START = "vblank_start"
    VBLANK_END = "vblank_end"
    HBLANK = "hblank"
    IRQ = "irq"
    DMA_COMPLETE = "dma_complete"
    TIMER_OVERFLOW = "timer_overflow"
    BREAKPOINT = "breakpoint"
    WATCHPOINT_READ = "watchpoint_read"
    WATCHPOINT_WRITE = "watchpoint_write"
    HALT = "halt"
    CARTRIDGE_SAVE_WRITE = "cartridge_save_write"


class MemoryRegionKind(Enum):
    BIOS = "bios"
    EWRAM = "ewram"
    IWRAM = "iwram"
    IO = "io"
    PALETTE = "palette"
    VRAM = "vram"
    OAM = "oam"
    ROM = "rom"
    SRAM = "sram"
    OPEN_BUS = "open_bus"


@dataclass(frozen=True, slots=True)
class EmulatorConfig:
    """建立 ``Emulator`` 時使用的不可變設定。"""

    bios_path: Path | None = None
    boot_mode: BootMode = BootMode.HLE_ADVANCED
    timing: TimingMode = TimingMode.FUNCTIONAL
    video: VideoMode = VideoMode.FRAMEBUFFER
    audio: AudioMode = AudioMode.DISABLED
    deterministic: bool = True  # 預設開啟；False 僅供實驗
    seed: int = 0
    hle_strict: bool = True  # True：未支援 SWI raise；False：記錄事件後 no-op（見 2.1.2）

    def validate(self) -> None:
        """在 ``Emulator`` 建構時呼叫；違反契約 raise ``InvalidConfigError``。"""

        # 延遲匯入：config.py 需要 EmulatorConfig，模組載入期匯入會形成循環。
        from .config import validate_config

        validate_config(self)


@dataclass(frozen=True, slots=True)
class EmulatorEvent:
    """對外可觀測事件；內部排程事件（``ScheduledEvent``）不會出現在這裡。"""

    kind: EventKind
    cycle: int  # 事件發生時的總 cycle 數
    frame_index: int
    scanline: int | None  # PPU 相關事件必填，其他為 None
    channel: int | None  # DMA/timer 事件：通道編號
    address: int | None  # breakpoint/watchpoint/save 事件：觸發位址
    value: int | None  # write 類事件：寫入值


@dataclass(frozen=True, slots=True)
class StepResult:
    """``step_cycles()`` 的結果（規格 5.3）。"""

    cycles_executed: int  # 實際執行的 cycle 數（<= 請求值）
    cycles_remaining: int  # 因 halt/breakpoint 提前停止而未執行的部分
    halted: bool  # CPU 進入 HALT（等待中斷）
    breakpoint_hit: int | None  # 觸發的 breakpoint id，無則 None
    events: tuple[EmulatorEvent, ...]  # 本次執行期間發生的對外事件


@dataclass(frozen=True, slots=True)
class FrameResult:
    """``step_frame()`` 的結果（規格 5.3）。"""

    frame_index: int
    cycles: int  # 本 frame 消耗的 cycle 數
    vblank_started: bool
    irq_pending: int  # 執行結束時 IF 內未處理位元
    halted: bool
    events: tuple[EmulatorEvent, ...]


@dataclass(frozen=True, slots=True)
class CPUState:
    """對外唯讀 CPU 快照。``regs`` 為 r0-r15，r15 為架構上可理解的 PC。"""

    regs: tuple[int, ...]  # 長度 16
    cpsr: int
    spsr: int
    thumb: bool
    mode: int  # CPSR mode 位（0x10-0x1F）
    halted: bool
    cycles: int  # 總執行 cycle 數


@dataclass(frozen=True, slots=True)
class MemoryRegionInfo:
    """``MemoryView.region_info()`` 回傳的區域描述。"""

    kind: MemoryRegionKind
    base: int
    size: int
    read_only: bool


@dataclass(frozen=True, slots=True)
class MemoryRange:
    """RAM observation 白名單條目。"""

    name: str
    address: int
    size: int


@dataclass(frozen=True, slots=True)
class ObservationConfig:
    source: Literal["screen", "memory", "hybrid"] = "screen"
    grayscale: bool = True
    resize: tuple[int, int] | None = (84, 84)  # (height, width)
    memory_ranges: tuple[MemoryRange, ...] = ()


@dataclass(frozen=True, slots=True)
class ActionSpec:
    """RL action space 描述（規格 5.8 / 7.1）。"""

    mode: Literal["buttons", "discrete", "multi_binary"]

    # multi_binary / buttons 的固定 bit 順序（bit 0 = A）：
    button_order: ClassVar[tuple[Button, ...]] = (
        Button.A,
        Button.B,
        Button.SELECT,
        Button.START,
        Button.RIGHT,
        Button.LEFT,
        Button.UP,
        Button.DOWN,
        Button.R,
        Button.L,
    )

    # discrete 模式：每個動作對應一組按鍵（互斥）。
    discrete_sets: tuple[tuple[Button, ...], ...] = ()


@dataclass(frozen=True, slots=True)
class GBAEnvConfig:
    """``gbaemu.rl.GBAEnv`` 的設定（RL 層於 Phase 5 實作）。"""

    observation: ObservationConfig = ObservationConfig()
    action: ActionSpec = ActionSpec(mode="multi_binary")
    frame_skip: int = 4
    max_episode_steps: int = 10_000


__all__ = [
    "TimingMode",
    "VideoMode",
    "AudioMode",
    "BootMode",
    "SaveType",
    "Button",
    "EventKind",
    "MemoryRegionKind",
    "EmulatorConfig",
    "EmulatorEvent",
    "StepResult",
    "FrameResult",
    "CPUState",
    "MemoryRegionInfo",
    "MemoryRange",
    "ObservationConfig",
    "ActionSpec",
    "GBAEnvConfig",
    "InvalidConfigError",
]
