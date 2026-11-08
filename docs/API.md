# gbaemu Python API 參考

本文件係 `gbaemu` **0.1.0** 嘅 Python API reference，寫法盡量貼近 PyBoy 嘅
API 文件：每個公開類別／方法都有簽名、行為契約同可貼上執行嘅範例。

> 設計權威仍然係 [`docs/spec/SPEC.md`](spec/SPEC.md)（尤其 §5、§6、§7）。
> 本文件描述**目前實作**；如果實作同 SPEC 有出入，以程式碼為準，並應同步
> 更新 SPEC／`TODO.md`。未完成項目見 [`TODO.md`](../TODO.md)。

---

## 目錄

1. [安裝與 backend 選擇](#1-安裝與-backend-選擇)
2. [五分鐘快速開始](#2-五分鐘快速開始)
3. [公開匯出總表](#3-公開匯出總表)
4. [`EmulatorConfig`](#4-emulatorconfig)
5. [`Emulator`](#5-emulator)
6. [觀測 API：CPU／Memory／Video／Audio](#6-觀測-apicpumemoryvideoaudio)
7. [輸入：`InputPort`](#7-輸入inputport)
8. [事件：`EmulatorEvent`／`EventStream`](#8-事件emulatoreventeventstream)
9. [Snapshot：`save_state()`／`load_state()`](#9-snapshotsave_stateload_state)
10. [Rust native backend](#10-rust-native-backend)
11. [RL 層：`GBAEnv` 與 rollout](#11-rl-層gbaenv-與-rollout)
12. [GUI facade：`GbaApp`／`Screen`](#12-gui-facadegbaappscreen)
13. [CLI](#13-cli)
14. [錯誤類別](#14-錯誤類別)
15. [已知限制與 backend 差異](#15-已知限制與-backend-差異)

---

## 1. 安裝與 backend 選擇

需求：**Python 3.11+**。核心模擬器零外部依賴；以下功能先要裝額外套件：

| 功能 | 額外依賴 | 安裝方式 |
|---|---|---|
| RL observation（numpy array） | `numpy` | `pip install "gbaemu[rl]"` |
| Gymnasium `check_env()`／spaces | `gymnasium` | `pip install "gbaemu[rl]"` |
| SDL 視窗、音訊輸出 | `pygame-ce` | `pip install "gbaemu[ui]"` |

`gbaemu` 有兩個 backend，API 大致相同：

| Backend | 類別 | 特性 |
|---|---|---|
| Python reference | `gbaemu.Emulator` | 預設、可讀性優先、行為最完整（events、精確 cycle） |
| Rust native | `gbaemu.NativeEmulator` | 快得多；經 PyO3 `gbaemu._native`，需 native wheel 或自行 build |

選擇方式（環境變數 `GBAEMU_BACKEND`）：

| 值 | `Emulator.from_rom()` | `open_emulator()` | `GbaApp()` |
|---|---|---|---|
| 未設定 | Python | Python | `auto`（有 native 就用 Rust） |
| `python` | Python | Python | Python |
| `rust` | 回傳 `NativeEmulator` | 回傳 `NativeEmulator` | Rust（失敗即報錯） |
| `auto` | 同未設定 | 同未設定 | 有 native 就用 Rust，否則 Python |

```python
import os

os.environ["GBAEMU_BACKEND"] = "rust"   # 想用 Rust core
from gbaemu import Emulator              # from_rom() 會回傳 NativeEmulator

emu = Emulator.from_rom("rom/game.gba")
print(type(emu).__name__)                # NativeEmulator
```

想明確揀 backend，建議直接用 `gbaemu.native.open_emulator()`，或者直接
instantiating `NativeEmulator`（見 [§10](#10-rust-native-backend)）。

---

## 2. 五分鐘快速開始

```python
from gbaemu import Emulator, EmulatorConfig, VideoMode

config = EmulatorConfig(
    video=VideoMode.FRAMEBUFFER,   # 需要 framebuffer 才 render
)

emu = Emulator.from_rom("rom/game.gba", config=config)
try:
    emu.reset()

    # 按住 A 一個 frame
    emu.input.set_buttons(a=True)
    result = emu.step_frame(render=True)
    emu.input.clear()

    print("frame:", result.frame_index)
    print("cycles:", result.cycles)
    print("PC:", hex(emu.cpu.state().regs[15]))

    pixels = emu.video.read_frame()      # 240*160*3 bytes (RGB888)
    assert len(pixels) == 240 * 160 * 3

    for event in emu.events.poll():
        print(event.kind, event.cycle)
finally:
    emu.close()
```

`emu.close()` 之後任何操作都會 raise `GbaEmuError`；`close()` 可以重複呼叫。

---

## 3. 公開匯出總表

```python
import gbaemu
print(gbaemu.__version__)   # "0.1.0"
```

`from gbaemu import ...` 可以直接拿到：

| 名稱 | 類型 | 說明 |
|---|---|---|
| `Emulator` | class | Python reference 模擬器 |
| `NativeEmulator` | class | Rust core facade |
| `open_emulator` | function | 依 `GBAEMU_BACKEND` 建立 backend |
| `GbaApp` | class | PyBoy 風格 GUI／headless facade |
| `EmulatorConfig` | dataclass | 模擬器設定 |
| `TimingMode` / `VideoMode` / `AudioMode` / `BootMode` / `SaveType` | Enum | 設定列舉 |
| `Button` | Enum | 十個 GBA 按鍵 |
| `EventKind` | Enum | 對外事件種類 |
| `MemoryRegionKind` | Enum | 記憶體區域 |
| `StepResult` | dataclass | `step_cycles()`／`run_until()` 結果 |
| `FrameResult` | dataclass | `step_frame()` 結果 |
| `EmulatorEvent` | dataclass | 單一事件 |
| `CPUState` | dataclass | CPU 唯讀快照 |
| `MemoryRegionInfo` | dataclass | 記憶體區域描述 |
| `MemoryRange` / `ObservationConfig` / `ActionSpec` / `GBAEnvConfig` | dataclass | RL 設定 |
| `GbaEmuError` 及一眾子類 | Exception | 見 [§14](#14-錯誤類別) |

`gbaemu.rl` 另外匯出：

```python
from gbaemu.rl import (
    GBAEnv, GbaApp, Screen,
    GBAEnvConfig, ObservationConfig, ActionSpec, MemoryRange,
    RolloutResult, run_rollout, run_rollouts, replay_trace,
    hash_bytes, hash_observation,
)
```

---

## 4. `EmulatorConfig`

```python
from pathlib import Path
from gbaemu import (
    EmulatorConfig, BootMode, TimingMode, VideoMode, AudioMode,
)

config = EmulatorConfig(
    bios_path=None,                  # 可選：Path("gba_bios.bin")
    boot_mode=BootMode.HLE_ADVANCED, # 預設
    timing=TimingMode.FUNCTIONAL,    # 預設；TIMED 較精確但慢
    video=VideoMode.FRAMEBUFFER,     # 預設
    audio=AudioMode.DISABLED,        # 預設
    deterministic=True,              # 預設
    seed=0,                          # 預設
    hle_strict=True,                 # 預設
)
```

| 欄位 | 預設 | 說明 |
|---|---|---|
| `bios_path: Path \| None` | `None` | 真實 BIOS 路徑；只接受 `pathlib.Path`。HLE 模式下仍可提供，BIOS 視窗讀值會用真資料，但開機流程仍用 HLE |
| `boot_mode: BootMode` | `HLE_ADVANCED` | `HLE_ADVANCED`／`TEST_ROM_ONLY`／`REQUIRE_BIOS` |
| `timing: TimingMode` | `FUNCTIONAL` | `FUNCTIONAL`（近似 cycle）／`TIMED`（bus/PPU/DMA/timer 逐 cycle）／`TRACE` |
| `video: VideoMode` | `FRAMEBUFFER` | `FRAMEBUFFER` 才更新 240×160 framebuffer |
| `audio: AudioMode` | `DISABLED` | `BUFFERED` 才產生 PCM |
| `deterministic: bool` | `True` | 跨 TimingMode 的決定性保證；`False` 只供實驗 |
| `seed: int` | `0` | 只影響模擬器內部 RNG；不影響硬體行為 |
| `hle_strict: bool` | `True` | `True`：未支援 SWI raise `HleUnsupportedSwiError`；`False`：記錄後 no-op |

`EmulatorConfig.validate()` 會在建立 `Emulator` 時自動呼叫；違反以下規則
會 raise `InvalidConfigError`：

- `boot_mode`／`timing`／`video`／`audio` 必須是對應 Enum；
- `bios_path` 必須是 `Path` 或 `None`；
- `deterministic`／`hle_strict` 必須是 `bool`；
- `seed` 必須是 `int`（`bool` 不接受）；
- `BootMode.REQUIRE_BIOS` 必須有 `bios_path`。

真實遊戲通常用：

```python
config = EmulatorConfig(
    video=VideoMode.FRAMEBUFFER,
    audio=AudioMode.DISABLED,
    timing=TimingMode.FUNCTIONAL,
    hle_strict=False,   # 唔想因為未支援 SWI 而即刻 raise
)
```

> **Snapshot 注意：** `deterministic`、`seed`、`boot_mode`、`hle_strict`、
> `timing`、`video`、`audio` 會計入 config hash；`bios_path` **不**計入。
> 載入 snapshot 時 config 必須一致，否則 `SnapshotConfigMismatchError`。

---

## 5. `Emulator`

```python
class Emulator:
    def __init__(self, rom: bytes, *, config: EmulatorConfig,
                 rom_path: Path | None = None) -> None: ...

    @classmethod
    def from_rom(cls, rom_path: str | Path, *,
                 config: EmulatorConfig | None = None) -> "Emulator": ...
```

一般用 `from_rom()`；`__init__` 俾測試直接餵 ROM bytes。`from_rom()` 會讀
ROM header／save 檔，並按 `GBAEMU_BACKEND` 決定回傳 Python 定 native 物件。
如果 `<rom stem>.sav` 存在而且大小相符，`from_rom()` 會自動載入；`reset()`
唔會重新讀 `.sav`。

### 5.1 建立與重設

```python
from gbaemu import Emulator

emu = Emulator.from_rom("rom/game.gba")   # 使用預設 config
emu.reset()                                # 重新開機、清輸入
emu.reset(seed=123)                        # 同時重設 RNG seed
```

`reset(seed=None)` 會重新 boot、清空輸入、清除 paused 狀態；唔會自動寫回
`.sav`。

### 5.2 推進模擬

```python
# 以 cycle 為單位：最多行 10,000 cycles
result = emu.step_cycles(10_000)
print(result.cycles_executed, result.cycles_remaining, result.halted)

# 以 frame 為單位：行到下一個 frame boundary（280,896 cycles）
frame = emu.step_frame(render=True)
print(frame.frame_index, frame.cycles, frame.vblank_started)

# 連續行 60 個 frame；默認唔收集 FrameResult（回傳空 list）
emu.run_frames(60)
frames = emu.run_frames(2, render=True, collect_results=True)
assert len(frames) == 2
```

行為契約：

- `step_cycles(n)`：`n` 必須是 `int >= 0`。CPU 指令部分最多執行 `n` 個
  cycle，唔會超出；但 DMA／IRQ 服務嘅額外 cycle 有機會令最後
  `cycles_executed` 略多過請求值（兩個 backend 都有呢個情況，見 §15）。
  遇到 HALT 或 breakpoint 會提前停，並用 `cycles_executed`／
  `cycles_remaining` 回報。
- `step_frame()`：推進到下一個 frame boundary；如果呼叫時已經喺 frame 中段，
  終點仍然係「下一個」boundary。
- `run_frames(count, *, render=False, collect_results=False)`：等價連續呼叫
  `step_frame()`；`collect_results=False` 時回傳 `[]`（rollout 省記憶體）。
- `run_until(event, *, max_cycles)`：行到下一個指定事件或 cycle 上限；
  `max_cycles` 必填、必須為正整數。

```python
from gbaemu import EventKind

result = emu.run_until(EventKind.VBLANK_START, max_cycles=1_000_000)
print(result.cycles_executed)
for event in result.events:
    print(event.kind, event.cycle, event.scanline)
```

### 5.3 暫停與關閉

```python
emu.pause()      # 只設定 paused 旗標；step_* 目前唔會因此停止
print(emu.is_closed)
emu.close()      # 之後操作 raise GbaEmuError；可重複呼叫
```

`pause()` 係留俾 GUI／工具記狀態用；真正停止推進係停止呼叫 `step_*`。

### 5.4 唯讀屬性

| 屬性 | 型別 | 說明 |
|---|---|---|
| `emu.config` | `EmulatorConfig` | 建立時嘅設定 |
| `emu.rom_path` | `Path \| None` | ROM 路徑（bytes 建立時為 `None`） |
| `emu.rom_header` | `RomHeader` | 解析後嘅 cartridge header |
| `emu.cycles` | `int` | 累計 CPU cycle |
| `emu.frame_index` | `int` | PPU frame 編號 |
| `emu.halted` | `bool` | CPU 是否 HALT |
| `emu.irq_pending` | `bool` | `IE & IF` 是否有未處理中斷 |
| `emu.vcount` | `int` | 目前 scanline（0–227） |
| `emu.is_closed` | `bool` | 是否已 `close()` |
| `emu.battery_dirty` | `bool` | save RAM 自載入／上次寫回後有無改動 |
| `emu.cpu` | `CPUView` | 見 [§6.1](#61-cpuview) |
| `emu.memory` | `MemoryView` | 見 [§6.2](#62-memoryview) |
| `emu.video` | `VideoView` | 見 [§6.3](#63-videoview) |
| `emu.audio` | `AudioView` | 見 [§6.4](#64-audioview) |
| `emu.input` | `InputPort` | 見 [§7](#7-輸入inputport) |
| `emu.events` | `EventStream` | Python backend 才有完整事件；見 [§8](#8-事件emulatoreventeventstream) |

```python
print(emu.rom_header.title)
print(emu.rom_header.game_code, emu.rom_header.maker_code)
print(emu.rom_header.complement_check_ok)
```

### 5.5 存檔（電池記憶體）

```python
emu.save_state()                 # 見 §9（snapshot，唔係 .sav）
emu.battery_dirty                # 遊戲有冇寫過 save RAM
emu.cartridge_flush_to_disk()    # 原子寫回 <rom stem>.sav
```

`cartridge_flush_to_disk()` 需要：

1. cartridge 有 save 媒體；
2. `emu.rom_path` 存在（用 bytes 建立就冇）。

否則 raise `GbaEmuError`。寫入方式係先寫 `<name>.sav.tmp` 再 `os.replace()`，
避免半寫入。遊戲正常運行時**唔會**自動寫 `.sav`；要明確呼叫，或者用
`GbaApp.stop(save=True)`／`GbaApp.save_battery()`。

---

## 6. 觀測 API：CPU／Memory／Video／Audio

所有 `read_*` 都係 debugger peek：**唔會**觸發硬體副作用、唔會消耗 cycle、
唔會改 open bus。寫入 API 見 `MemoryView`。

### 6.1 `CPUView`

```python
state = emu.cpu.state()
print(state.regs[15])        # PC
print(state.thumb, hex(state.cpsr), state.mode, state.halted)

print(emu.cpu.read_register("r0"))
print(emu.cpu.read_register("r15"))
print(emu.cpu.read_register("cpsr"))
print(emu.cpu.read_register("spsr"))
```

`read_register(name)` 只接受 `"r0"`…`"r15"`、`"cpsr"`、`"spsr"`；其他
名稱（包括 `"pc"`、`"sp"`、`"lr"`）會 raise `ValueError`。

`CPUState` 欄位：

| 欄位 | 型別 | 說明 |
|---|---|---|
| `regs` | `tuple[int, ...]` | r0–r15，長度 16；r15 係架構上可理解嘅 PC |
| `cpsr` | `int` | 目前 CPSR |
| `spsr` | `int` | 目前 mode 嘅 SPSR |
| `thumb` | `bool` | 是否 Thumb 狀態 |
| `mode` | `int` | CPSR mode 位（0x10–0x1F） |
| `halted` | `bool` | 是否 HALT |
| `cycles` | `int` | 累計 cycle |

Breakpoint：

```python
pc = emu.cpu.state().regs[15]                    # 目前 PC（ARM 位址）
bp = emu.cpu.set_breakpoint(pc)

result = emu.step_cycles(100_000)
if result.breakpoint_hit == bp:
    print("hit at", hex(emu.cpu.state().regs[15]))

emu.cpu.clear_breakpoint(bp)
```

Thumb 狀態可以明確指定（`address` 仍然係指令位址，唔使加 1）：

```python
bp_thumb = emu.cpu.set_breakpoint(pc, thumb=True)  # 只喺 Thumb 狀態命中
emu.cpu.clear_breakpoint(bp_thumb)
```

每次 `set_breakpoint()` 都會配置新 id；`clear_breakpoint()` 只清除指定 id，
id 唔存在會 raise `BreakpointError`。

### 6.2 `MemoryView`

```python
value = emu.memory.read_u8(0x02000000)
value16 = emu.memory.read_u16(0x02000000)
value32 = emu.memory.read_u32(0x02000000)
block = emu.memory.read(0x02000000, 256)        # bytes

emu.memory.write_u8(0x02000000, 0x12)
emu.memory.write_u16(0x02000000, 0x1234)
emu.memory.write_u32(0x02000000, 0x12345678)

from gbaemu import MemoryRegionKind

info = emu.memory.region_info(MemoryRegionKind.EWRAM)
print(info.kind, hex(info.base), info.size, info.read_only)

ewram = emu.memory.read_region(MemoryRegionKind.EWRAM)   # bytes 複本
```

| 方法 | 說明 |
|---|---|
| `read_u8/u16/u32(address)` | 讀取，回傳 `int` |
| `read(address, size)` | 讀取 `size` bytes，回傳 `bytes` |
| `write_u8/u16/u32(address, value)` | debugger 寫入；繞過 8-bit 特殊規則 |
| `read_region(kind)` | 回傳整個區域嘅 `bytes` 複本 |
| `region_info(kind)` | 回傳 `MemoryRegionInfo(kind, base, size, read_only)` |
| `force_write(address, value)` | 8-bit 除錯寫入，並 emit `WATCHPOINT_WRITE` 事件 |

寫入限制：

- ROM（`0x08000000`–`0x0DFFFFFF`）同 BIOS（`0x00000000`–`0x00003FFF`）係唯讀，
  `write_*`／`force_write()` 會 raise `ReadOnlyMemoryError`。
- `force_write()` 只寫 1 byte（value 取低 8 位），而且會留 trace event；
  普通測試改 RAM 用 `write_*` 就已足夠。
- `read_region()` 回傳複本，唔會俾 external code 直接改到模擬器內部。

### 6.3 `VideoView`

```python
frame = emu.video.read_frame()          # bytes, 240*160*3, RGB888
line0 = emu.video.read_scanline(0)      # bytes, 240*3
print(emu.video.width, emu.video.height, len(frame))

# 需要 numpy
array = emu.video.read_frame_array()    # shape (160, 240, 3), dtype uint8
```

- Pixel 格式：RGB888、row-major、scanline 0 喺最前。
- `read_frame(copy=True)` 目前兩種值都回傳獨立 `bytes`（實作保留參數係為
  API 相容）。
- `read_scanline(line)` 接受 `0..159`，否則 `ValueError`。
- `video=VideoMode.OFF` 時 framebuffer **唔會更新**，`read_frame()` 會回傳
  最後一次 render 嘅內容（或者全零）；RL 唔應該依賴 OFF mode 嘅畫面。

```python
from gbaemu import Emulator, EmulatorConfig, VideoMode

emu = Emulator.from_rom(
    "rom/game.gba",
    config=EmulatorConfig(video=VideoMode.FRAMEBUFFER),
)
emu.run_frames(2, render=True)          # 要 render=True 才有新畫面
raw = emu.video.read_frame()

# 自己存成 PPM（唔需要 Pillow）
with open("frame.ppm", "wb") as handle:
    handle.write(b"P6\n240 160\n255\n")
    handle.write(raw)
emu.close()
```

### 6.4 `AudioView`

```python
from gbaemu import AudioMode, Emulator, EmulatorConfig

emu = Emulator.from_rom(
    "rom/game.gba",
    config=EmulatorConfig(audio=AudioMode.BUFFERED),
)
emu.run_frames(1, render=False)
pcm = emu.audio.read_buffer()      # signed 16-bit little-endian stereo
print(emu.audio.sample_rate, len(pcm))
```

- `sample_rate`：GBA 預設 32768 Hz。
- `read_buffer()`：回傳自上次讀取後累積嘅 PCM，格式係 interleaved
  `s16le`（left, right）；讀取後清空。
- `audio=DISABLED` 時 buffer 為空。

---

## 7. 輸入：`InputPort`

```python
from gbaemu import Button

emu.input.set_buttons(a=True, start=False)   # 只改有提及嘅按鍵
emu.input.press(Button.RIGHT, Button.A)
emu.input.release(Button.A)

print(emu.input.is_pressed(Button.RIGHT))
print(emu.input.pressed_buttons)             # frozenset[Button]
print(hex(emu.input.keyinput_mask))          # active-low 10-bit

emu.input.clear()
```

`set_buttons(**buttons)`：

- 只接受 `Button` 嘅十個名稱（`a`、`b`、`select`、`start`、`right`、`left`、
  `up`、`down`、`r`、`l`），其他名稱 raise `ValueError`；
- 值必須係 `bool`；
- 只更新有傳入嘅按鍵，冇提及嘅保持原狀（低階 port 語意）。RL 嘅
  「每個 action 完整替換」由 `GBAEnv.step()` 負責。

輸入會喺下一個硬體取樣點（KEYINPUT 讀取／keypad poll）生效，唔會中途改寫
目前指令。

---

## 8. 事件：`EmulatorEvent`／`EventStream`

Python backend 嘅 `emu.events` 會收集對外事件：

```python
emu.step_frame()

for event in emu.events.poll():
    print(
        event.kind.value,
        event.cycle,
        event.frame_index,
        event.scanline,
        event.address,
    )
```

`poll()` 回傳自上次 poll 以嚟嘅 `tuple[EmulatorEvent, ...]`，依 `cycle`
非遞減排序，並清空已回報事件。`EventStream` 亦有 `clear()`、`len()`。

`EmulatorEvent` 欄位：

| 欄位 | 型別 | 說明 |
|---|---|---|
| `kind` | `EventKind` | 事件種類 |
| `cycle` | `int` | 事件發生時嘅總 cycle |
| `frame_index` | `int` | frame 編號 |
| `scanline` | `int \| None` | PPU 事件（VBLANK／HBLANK）嘅 scanline |
| `channel` | `int \| None` | DMA／timer 通道 |
| `address` | `int \| None` | breakpoint／watchpoint／save 位址 |
| `value` | `int \| None` | write 類事件嘅值 |

`EventKind` 一覽：

| 值 | 說明 |
|---|---|
| `FRAME_BOUNDARY` | frame 边界 |
| `VBLANK_START` / `VBLANK_END` | VBlank 開始／結束 |
| `HBLANK` | 進入 HBlank |
| `IRQ` | IRQ pending |
| `DMA_COMPLETE` | DMA 完成 |
| `TIMER_OVERFLOW` | timer overflow |
| `BREAKPOINT` | 撞到 breakpoint |
| `WATCHPOINT_READ` / `WATCHPOINT_WRITE` | watchpoint（目前 `force_write()` 會 emit write） |
| `HALT` | CPU 進入 HALT |
| `CARTRIDGE_SAVE_WRITE` | 遊戲寫 save RAM |

> **Native backend 注意：** `NativeEmulator` 冇完整 event stream，
> `step_frame()`／`step_cycles()` 回傳嘅 `events` 通常係空 tuple；
> `run_until()` 會用狀態邊緣偵測合成指定事件（見 [§10](#10-rust-native-backend)）。

---

## 9. Snapshot：`save_state()`／`load_state()`

```python
blob = emu.save_state()
print(len(blob), blob[:4])          # b"GEMU"

# 之後（同一個 config、同一個 emulator 或新 instance）
emu.load_state(blob)
```

```python
from gbaemu import Emulator, EmulatorConfig

config = EmulatorConfig(hle_strict=False)
emu = Emulator.from_rom("rom/game.gba", config=config)
try:
    blob = emu.save_state()
finally:
    emu.close()

# 新 process／新 instance：config 必須一致
emu2 = Emulator.from_rom("rom/game.gba", config=config)
emu2.load_state(blob)
```

格式（SPEC §5.7，全部小端序）：

```text
<4s I 3H 32s 32s Q I>  = 90 bytes header
magic="GEMU" | version | emu_version(3H) | rom_sha256 |
config_sha256 | payload_len | payload_crc32 | payload
```

payload 由九段組成：`CPU\0`、`BUS\0`、`PPU\0`、`DMA\0`、`TMR\0`、`IRQ\0`、
`KEY\0`、`CRT\0`、`SCH\0`。

`load_state()` 驗證順序：

1. 長度不足／magic 錯 → `SnapshotCorruptError`
2. CRC32 錯 → `SnapshotCorruptError`
3. format version 不支援 → `SnapshotVersionError`
4. ROM SHA-256 不符 → `SnapshotRomMismatchError`
5. config hash 不符 → `SnapshotConfigMismatchError`

重要契約：

- `load_state()` 還原嘅 save RAM **只存在於記憶體**，唔會自動寫 `.sav`；
  要寫盤請另外呼叫 `emu.cartridge_flush_to_disk()`。
- Snapshot 目前只保證**同一個 backend**產生／載入。Python 同 Rust 嘅
  cartridge save-kind 編碼未完全一致，跨 backend 載入可能 raise
  `SnapshotConfigMismatchError` 或 `UnsupportedSaveTypeError`。
- `bios_path` 唔計入 config hash；如果兩個 instance 用同一設定但唔同 BIOS
  內容，hash 檢查唔會阻止載入，行為唔保證一致。

如果想做 branching／MCTS：

```python
root = emu.save_state()
for action in range(4):
    emu.load_state(root)
    emu.input.set_buttons(**{("a", "b", "right", "left")[action]: True})
    emu.run_frames(4)
    score = emu.memory.read_u32(0x02000000)
    print(action, score)
```

---

## 10. Rust native backend

```python
from gbaemu.native import NativeEmulator

native = NativeEmulator.from_rom("rom/game.gba")   # config 可選
try:
    frame = native.step_frame()
    print(frame.frame_index, frame.cycles)
    print(len(native.video.read_frame()))          # 115200
    print(native.cpu.state().regs[15])
finally:
    native.close()
```

`NativeEmulator` 同 `Emulator` 相同嘅部分：

- `reset()`、`step_cycles()`、`step_frame()`、`run_frames()`、`run_until()`
- `save_state()`／`load_state()`、`cartridge_flush_to_disk()`
- `cpu`、`memory`、`video`、`audio`、`input`
- 屬性 `cycles`、`frame_index`、`halted`、`irq_pending`、`vcount`、`config`、
  `rom_path`、`rom_header`、`battery_dirty`、`is_closed`

差異／限制：

| 項目 | Python `Emulator` | `NativeEmulator` |
|---|---|---|
| `step_frame(render=...)` | 依 `render` 決定是否更新 framebuffer | 參數被忽略，固定 render |
| `events` | 完整 `EventStream` | 冇；`events` 通常係空 tuple |
| `step_cycles()` | CPU 指令部分精確；DMA／IRQ 額外 cycle 同樣可能令總數略超 | 以 `peek_cycles()` 先確認；DMA／IRQ 額外 cycle 可能超額 |
| `run_until()` | 支援所有 `EventKind` | 只支援 `FRAME_BOUNDARY`、`VBLANK_START`、`VBLANK_END`、`HBLANK`、`IRQ`、`HALT`、`TIMER_OVERFLOW`、`DMA_COMPLETE`、`BREAKPOINT`；其他 raise `NotImplementedError` |
| snapshot | Python 格式 | Rust 格式；跨 backend 未保證 |
| `framebuffer()` | 冇（用 `video.read_frame()`） | 有額外 shortcut `native.framebuffer()` |

`NativeEmulator` 亦有直接讀寫 shortcut（等價 `memory` view）：

```python
native.read_u8(0x02000000)
native.write_u8(0x02000000, 0x12)
```

`open_emulator()` 適合同時支援兩個 backend 嘅工具：

```python
from gbaemu.native import open_emulator

emu = open_emulator("rom/game.gba")     # 依 GBAEMU_BACKEND，默認 Python
try:
    emu.run_frames(1)
finally:
    emu.close()
```

`GBAEMU_BACKEND` 只接受 `python`／`rust`；其他值 `open_emulator()` 會
raise `ValueError`。

---

## 11. RL 層：`GBAEnv` 與 rollout

`GBAEnv` 係 Gymnasium 風格 wrapper。默認用 Python `Emulator`；如果設定
`GBAEMU_BACKEND=rust`，`Emulator.from_rom()` 會回傳 `NativeEmulator`，RL
層亦會照用（但 native 冇完整 events）。`step()` 嘅 action 會完整替換按鍵狀態；
reward 目前固定 `0.0`、`terminated` 固定 `False`。

### 11.1 基本用法

```python
from gbaemu.rl import GBAEnv, GBAEnvConfig, ObservationConfig, ActionSpec

env = GBAEnv(
    "rom/game.gba",
    GBAEnvConfig(
        observation=ObservationConfig(
            source="screen",       # "screen" | "memory" | "hybrid"
            grayscale=True,
            resize=(84, 84),       # (height, width)
        ),
        action=ActionSpec(mode="multi_binary"),
        frame_skip=4,
        max_episode_steps=10_000,
    ),
)
try:
    observation, info = env.reset(seed=0)
    print(observation.shape)       # (84, 84)

    # multi_binary：長度 10 的 bool/int 序列，bit 順序固定 A,B,SELECT,...
    action = [False] * 10
    action[0] = True               # 按住 A
    observation, reward, terminated, truncated, info = env.step(action)
    print(reward, terminated, truncated, info["frame_index"])
finally:
    env.close()
```

`GBAEnv` 會強制：

- `observation.source` 係 `screen`／`hybrid` 時，使用
  `VideoMode.FRAMEBUFFER`；
- `hle_strict=False`（真實遊戲友善）。

`frame_skip` 係每個 RL step 執行幾個 frame；screen observation 只會喺最後
一個 frame render。`max_episode_steps` 到咗就 `truncated=True`。

`reset(seed=...)` 回傳 `(observation, info)`；`step()` 回傳 5-tuple。`info`
包含：

```python
{
    "frame_index": int,
    "frames_rendered": int,
    "vcount": int,
    "irq_pending": bool,
    "halted": bool,
    "buttons": tuple[str, ...],   # 已排序的按鍵名稱
}
```

### 11.2 Action 模式

```python
from gbaemu import Button
from gbaemu.rl import GBAEnv, GBAEnvConfig, ActionSpec

# 1) multi_binary：固定 10 個 bit
GBAEnv("rom/game.gba", GBAEnvConfig(action=ActionSpec(mode="multi_binary")))

# 2) buttons：dict[Button, bool]
env = GBAEnv("rom/game.gba", GBAEnvConfig(action=ActionSpec(mode="buttons")))
env.step({Button.A: True, Button.RIGHT: False})
env.close()

# 3) discrete：每個 index 對應一組按鍵
env = GBAEnv(
    "rom/game.gba",
    GBAEnvConfig(
        action=ActionSpec(
            mode="discrete",
            discrete_sets=((), (Button.A,), (Button.B,), (Button.RIGHT,)),
        )
    ),
)
env.step(1)     # 按 A
env.step(0)     # 空 action
env.close()
```

`ActionSpec.button_order` 係固定 `ClassVar`：

```text
A, B, SELECT, START, RIGHT, LEFT, UP, DOWN, R, L
```

### 11.3 Observation 模式

```python
from gbaemu import MemoryRange
from gbaemu.rl import ObservationConfig

# 純畫面（灰階、84x84）
ObservationConfig(source="screen", grayscale=True, resize=(84, 84))

# 純 RAM（需要白名單）
ObservationConfig(
    source="memory",
    memory_ranges=(
        MemoryRange("player", 0x02000000, 16),
        MemoryRange("flags", 0x02001000, 4),
    ),
)

# 畫面 + RAM（flatten 後 concat）
ObservationConfig(
    source="hybrid",
    grayscale=False,
    resize=(120, 160),
    memory_ranges=(MemoryRange("ram", 0x02000000, 64),),
)
```

- `source="memory"`／`"hybrid"` 必須有 `memory_ranges`，否則 `ValueError`。
- `resize` 順序係 `(height, width)`；`None` 表示保持 160×240。
- `grayscale=True` 時 screen observation 係 2-D `(H, W)`；`False` 係
  `(H, W, 3)`。
- `hybrid` 會將畫面 flatten 再 concat RAM bytes，所以 observation 係 1-D。

### 11.4 Gymnasium spaces

```python
import gymnasium
from gbaemu.rl import GBAEnv

env = GBAEnv("rom/game.gba")
gymnasium.utils.env_checker.check_env(env)   # 需要 gymnasium + numpy
print(env.action_space)
print(env.observation_space)
env.close()
```

冇裝 `gymnasium` 時，`GBAEnv` 仍然可用（`_ENV_BASE = object`），
`action_space`／`observation_space` 回傳 `None`。

### 11.5 Rollout 與 trace replay

```python
from gbaemu.rl import run_rollout, run_rollouts, replay_trace

actions = [[False] * 10 for _ in range(20)]
result = run_rollout("rom/game.gba", actions, seed=123)
print(result.steps)
print(result.final_state_hash)
print(result.observation_hashes[:3])

# 多 process 平行 rollout
results = run_rollouts(
    "rom/game.gba",
    [(actions, 0), (actions, 1), (actions, 2)],
    workers=3,
)
print([item.final_state_hash for item in results])

# 用按鍵名稱重播（trace[i] = 第 i 個 step 按住的鍵）
result = replay_trace(
    "rom/game.gba",
    [(), ("a",), ("right", "a"), ("a",)],
    seed=0,
)
print(result.trace)
# ((), ('a',), ('a', 'right'), ('a',))
# 注意：trace 會按 ActionSpec.button_order 正規化順序（A 喺 RIGHT 之前）。
```

`RolloutResult` 欄位：

| 欄位 | 型別 | 說明 |
|---|---|---|
| `seed` | `int` | 使用嘅 seed |
| `steps` | `int` | 實際執行步數（可能因 terminated／truncated 提早停） |
| `observation_hashes` | `tuple[str, ...]` | reset + 每一步 observation 嘅 SHA-256 |
| `final_state_hash` | `str` | 最後 `save_state()` 嘅 SHA-256 |
| `total_reward` | `float` | reward 總和（目前通常 0.0） |
| `truncated` | `bool` | 有冇因 `max_episode_steps` 截斷 |
| `trace` | `tuple[tuple[str, ...], ...]` | 每步按鍵名稱（排序固定） |

`hash_bytes(data)`／`hash_observation(obs)` 係輔助函式；後者支援 bytes、
numpy array（用 `.tobytes()`）同其他物件（fallback `repr()`）。

---

## 12. GUI facade：`GbaApp`／`Screen`

`GbaApp` 係 PyBoy 風格入口，內部默認用 Rust native（`auto`），冇 native
就 fallback Python。需要 SDL 視窗時要裝 `pygame-ce`。

```python
from gbaemu import GbaApp

app = GbaApp(
    "rom/game.gba",
    window="SDL3",     # "SDL3"／"pygame"／"null"；其他值 = headless
    scale=4,           # 視窗放大倍率（240*scale x 160*scale）
    sound=None,        # None/False/0/"none" = 靜音；其他 = BUFFERED
    throttle=True,     # 依 59.7275 Hz 實時節流
)
try:
    while app.tick():  # 視窗關閉時回傳 False
        pass
finally:
    app.stop()         # 有 dirty 才寫 .sav
```

Headless（冇 pygame 都得）：

```python
from gbaemu import GbaApp

app = GbaApp("rom/game.gba", window="null")
try:
    for _ in range(60):
        app.tick(count=1, render=False, sound=False)
    print("frames:", app.frames)
    print("title:", app.title)
    print("screen shape:", app.screen.shape)
    print("pixels:", len(app.emu.video.read_frame()))   # 115200
finally:
    app.stop(save=False)   # 唔寫 .sav
```

> `GbaApp` 係 facade，**冇** `app.video`／`app.memory`／`app.cpu`。
> 要直接讀畫面／記憶體，用 `app.emu.video`、`app.emu.memory`，
> 或者 `app.screen.raw`／`app.screen.ndarray`。另外 `GbaApp` 建構時
> 唔會自動行 frame，要呼叫 `app.tick()` 先會有新畫面。

建構參數：

| 參數 | 預設 | 說明 |
|---|---|---|
| `path` | `None` | ROM 路徑；`None` 時要求 `rom/` 入面只有一個 `.gba` |
| `window` | `"null"` | `sdl3`／`pygame`／`sdl2`／`sdl`（大小寫不拘）；其他 = headless |
| `bios` | `None` | BIOS 路徑；檔案存在才加入 config |
| `verify_logo` | `True` | 目前忽略（保留相容） |
| `scale` | `4` | 視窗倍率 |
| `sound` | `None` | 非 false 值 → `AudioMode.BUFFERED`；只係開關，`"100"` 唔代表音量 |
| `throttle` | `True` | 實時節流 |
| `**kwargs` | — | 目前忽略 |

> `window="null"` 時唔會初始化 pygame mixer，所以`sound` 冇實際聲音輸出；
> 但 config 仍然係 `BUFFERED`，可以經 `app.emu.audio.read_buffer()` 拿 PCM。
> 要聽到聲，用 `window="SDL3"` 並安裝 `pygame-ce`。

方法：

```python
app.tick(count=1, render=True, sound=True) -> bool
app.stop(save=True) -> None
app.save_battery() -> None            # 強制寫 .sav

app.button("a", True)                 # 按
app.button_press("start")
app.button_release("start")

app.save_state("slot1.state")         # 寫檔案
app.load_state("slot1.state")

print(app.emu)                        # 底層 Emulator／NativeEmulator
print(app.screen.raw)                 # bytes
print(app.screen.ndarray)             # numpy (160,240,3)
print(app.screen.shape)               # (160, 240, 3)
```

鍵盤映射（SDL 視窗）：

| 鍵 | GBA |
|---|---|
| 方向鍵 | 對應方向 |
| `Z` | A |
| `X` | B |
| `Enter` | START |
| `Backspace` | SELECT |
| `A` | L |
| `S` | R |

`app.stop(save=True)` 只會喺 `battery_dirty` 為真時寫 `.sav`；純粹開遊戲、
冇存檔就唔會建立／改動 `.sav`。`save_battery()` 就唔理 dirty 直接寫。

---

## 13. CLI

安裝後有 `gbaemu` console script，亦可以用 `python -m gbaemu`：

```bash
gbaemu inspect-rom rom/game.gba
gbaemu inspect-rom rom/game.gba --json

gbaemu run rom/game.gba --frames 60
gbaemu run rom/game.gba --frames 60 --no-video --json

gbaemu dump-memory rom/game.gba --address 0x02000000 --size 64
gbaemu dump-memory rom/game.gba --address 0x03000000 --size 32 --frames 60 --json

gbaemu trace rom/game.gba --from 0x08000000 --cycles 1000
gbaemu replay rom/game.gba --input input.jsonl --frames 120
```

| 子命令 | 主要 options | 輸出 |
|---|---|---|
| `inspect-rom` | `--json` | ROM header（title、game code、checksum 等） |
| `run` | `--frames`（預設 60）、`--no-video`、`--json` | cycles、frame_index、halted、state hash |
| `dump-memory` | `--address`（預設 `0x02000000`）、`--size`、`--frames`、`--json` | hex dump 或 JSON hex |
| `trace` | `--from`（起始 PC）、`--cycles` | 每行一個 JSON：`pc`、`cpsr`、`cycles` |
| `replay` | `--input`（JSONL）、`--frames` | `rom`、`frames`、`state_hash` |

`replay` 嘅 input JSONL 每行一個 object：

```json
{"frame": 0, "buttons": ["start"]}
{"frame": 30, "buttons": ["a"]}
{"frame": 60, "buttons": []}
```

`trace` 會由 boot 開始單步，直到 PC 等於 `--from` 或者行咗 1,000,000 cycles
（防止錯誤位址無限迴圈），然後先開始輸出。

---

## 14. 錯誤類別

```python
from gbaemu import (
    GbaEmuError,
    InvalidConfigError,
    RomInvalidError,
    BiosMissingError,
    BiosChecksumError,
    UnsupportedSaveTypeError,
    HleUnsupportedSwiError,
    ReadOnlyMemoryError,
    BreakpointError,
    SnapshotError,
    SnapshotCorruptError,
    SnapshotVersionError,
    SnapshotRomMismatchError,
    SnapshotConfigMismatchError,
)
```

| 類別 | 何時 raise |
|---|---|
| `GbaEmuError` | 所有模擬器錯誤嘅 base；已關閉嘅 emulator 操作亦係呢個 |
| `InvalidConfigError` | `EmulatorConfig` 型別／組合錯誤（例如 `REQUIRE_BIOS` 冇 `bios_path`） |
| `RomInvalidError` | ROM 太細／header 無效 |
| `BiosMissingError`／`BiosChecksumError` | BIOS 缺失／checksum 錯 |
| `UnsupportedSaveTypeError` | 不支援嘅 save 類型／save 資料格式 |
| `HleUnsupportedSwiError` | `hle_strict=True` 遇到未支援 SWI |
| `ReadOnlyMemoryError` | 寫 ROM／BIOS |
| `BreakpointError` | breakpoint 操作錯誤 |
| `SnapshotError` | snapshot 錯誤 base |
| `SnapshotCorruptError` | magic／長度／CRC 錯 |
| `SnapshotVersionError` | format version 不支援 |
| `SnapshotRomMismatchError` | ROM SHA-256 不符 |
| `SnapshotConfigMismatchError` | config hash 不符 |

```python
from gbaemu import SnapshotConfigMismatchError

try:
    emu.load_state(blob)
except SnapshotConfigMismatchError:
    print("snapshot 係用另一個 config 產生，請用相同 config 重建 emulator")
```

---

## 15. 已知限制與 backend 差異

以下係 API 層面要留意嘅現況（詳細清單見 [`TODO.md`](../TODO.md)）：

1. **Native events**：`NativeEmulator` 未有完整 event stream；
   `step_frame()`／`step_cycles()` 嘅 `events` 通常係空。要靠
   `run_until()` 嘅邊緣偵測，而且只支援部分 `EventKind`。
2. **Cycle 精度**：`step_cycles()` 嘅 CPU 指令部分唔會超額，但 DMA／IRQ
   服務嘅額外 cycle 有機會令 `cycles_executed` 略多過請求；Python 同 Rust
   backend 都有呢個邊界情況。
3. **Snapshot 跨 backend**：Python 同 Rust 嘅 cartridge save-kind 編碼未完全
   一致，暫時只保證同 backend 載入。
4. **Video**：`VideoMode.OFF` 唔會更新 framebuffer；RL screen observation
   會強制 render。`read_frame()` 永遠回傳 RGB888（唔係 GBA 原生 BGR555）。
5. **Audio**：`AudioMode.BUFFERED` 先有 PCM；wave RAM bank 時序、
   SOUNDBIAS BIAS level 等仍未完全模擬（見 TODO）。
6. **Timing 精度**：`TimingMode.FUNCTIONAL` 係近似 cycle；需要精確 timing
   用 `TIMED`，但慢好多。部分 timer count-up／IRQ 邊界仍有已知差異。
7. **RL**：`GBAEnv` 默認 Python backend；`GBAEMU_BACKEND=rust` 時會用
   native，但 reward 固定 `0.0`、`terminated` 固定 `False`，遊戲-specific
   reward 要自己包 wrapper。
8. **GUI**：`GbaApp` 需要 `pygame-ce` 才有視窗／音訊；`window="null"` 係
   headless。`verify_logo` 同 `**kwargs` 目前接受但忽略。
9. **公開 repo**：唔包含 ROM、BIOS、`.sav`、tests 同 debug evidence；呢啲
   要自行準備，詳見 [`README.md`](../README.md) 同 [`rom/README.md`](../rom/README.md)。

---

## 版本

- 文件對應：`gbaemu 0.1.0`（`gbaemu.__version__`）
- 規格： [`docs/spec/SPEC.md`](spec/SPEC.md)
- 架構／遷移： [`docs/architecture/ARCHITECTURE.md`](architecture/ARCHITECTURE.md)、
  [`docs/architecture/MIGRATION.md`](architecture/MIGRATION.md)
- 未完成事項： [`TODO.md`](../TODO.md)
