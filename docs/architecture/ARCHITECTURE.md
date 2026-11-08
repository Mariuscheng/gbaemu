# 架構與資料流（Rust native + Python host）

本文件描述 `gbaemu` 的目標架構：**Python 控制面 + Rust native 資料面**。
目前 Python 實作完整可用，保留為 reference／test oracle；production 的
CPU／bus／PPU／timing 熱路徑將由 Rust core 實作，透過 PyO3 只在 frame 邊界
被呼叫。Cython 只保留作 legacy／遷移對照，不再是 production core。

完整 Rust 介面、狀態擁有權與遷移階段見 [`NATIVE_CORE.md`](NATIVE_CORE.md)；
量測與方案比較見 [`PERFORMANCE.md`](PERFORMANCE.md)。權威需求仍以
[`SPEC.md`](../spec/SPEC.md) 為準。

## 設計原則

1. **Python 不在 hot loop**：模擬 frame 內不得逐 instruction／逐 cycle 回 Python。
   Python 只在 frame 或 cycle 預算邊界被呼叫。
2. **單一公開 API**：`Emulator`／`GbaApp`／`GBAEnv` 不變；內部可切換
   `python`／`native` backend，呼叫端不需知道。
3. **確定性**：整數 cycle、固定狀態 layout、事件排序穩定；native 與 Python
   backend 對同一 ROM／輸入／seed 必須產生相同 state hash。
4. **Python 是 oracle**：現有 Python 引擎不刪除，作為 differential reference；
   native 只追求相同語意，不重新定義規格。
5. **邊界才複製資料**：framebuffer、PCM、event ring 在 frame 邊界一次取出，
   避免逐 pixel／逐事件 Python 物件配置。

## 加速約束（Rust 方向）

詳細規格見 [`NATIVE_CORE.md`](NATIVE_CORE.md)。目前 production 方向是
**Rust core + PyO3**；Cython 只作 legacy。舊「同源 Cython」的嘗試保留在文件
末段作歷史與 fallback 說明。

1. **Python facade 全部保留**：`Emulator`、`GbaApp`、`GBAEnv`、`MemoryView`、
   `VideoView` 不搬；`Emulator` 變成 Rust `NativeCore` 的 adapter。
2. **唯一熱邊界是 frame**：Rust `run_frame()` 內部處理 instruction／scanline／
   IRQ；Python 不得在 frame 內逐 instruction 回呼。
3. **Rust 擁有狀態**：CPU registers、RAM／VRAM、PPU、DMA/timer、snapshot
   payload 都在 Rust；Python 只有 handle。
4. **Cython 不再擴充**：`cpu/core.pyx` 只作 opt-in 實驗；新功能不寫 Cython。
5. **批次 tick／observation**：`Emulator.run_frames(n)`／`GbaApp.tick(count)`；
   RL 一次跑多 frame，只在最後取 observation。
6. **Build**：`maturin` 產生平台 wheel；沒有 native extension 的 production
   安裝明確報錯，development 可用 Python reference。




## 新方向：Rust core + CPython 控制面（建議）

先釐清名詞：

- **CPython**：執行 Python 的 runtime。所有 Python 程式都在 CPython 上跑，不是
  另一種實作。
- **Rust**：native core 的實作語言；透過 PyO3 變成 CPython extension。
- **Cython**：過渡期的 legacy／reference 工具；**新 core 不再使用 Cython**。

### 為什麼不是三種語言都放核心

Cython 能加速單一 Python 函式，但無法消除「CPU → Python bus → Python tick」
的邊界；M1–M4 的實測已經證明：只加速 instruction，遊戲仍然 2–4 fps。
Rust core 的價值是**把整個硬體資料面放在同一個 native boundary 內**，Python
只在 frame 邊界呼叫一次。

### 分工

| 層 | 語言 | 內容 |
|---|---|---|
| 公開 API／RL | Python（CPython） | `GbaApp`、`GBAEnv`、`MemoryView`、`VideoView`、observation、reward、input、CLI、config、process pool |
| 檔案／snapshot envelope | Python | 檔案路徑、magic/version/CRC、`.sav`、匯出／匯入包裝 |
| UI／音訊輸出 | Python | pygame／SDL 視窗、events、host audio device、截圖 |
| 硬體核心 | Rust | CPU ARM/THUMB、bus/memory map、PPU timing＋renderer、DMA、timers、IRQ、audio mixing、save-state payload |
| BIOS／HLE | Rust（production）＋Python（reference） | post-boot state、SWI 0x00–0x2A、IRQ stub、BIOS 讀取保護；**不需要真實 BIOS**；Python reference 只作 differential |
| 測試／reference | Python（可選 Cython legacy） | differential、CPU oracle、舊版 legacy engine；不進 production |
| 綁定 | Rust（PyO3/maturin） | 一次 extension，不需要 Cython |

### 邊界

```text
Python（CPython）
  GbaApp / GBAEnv / Observation / UI / CLI
        │  PyO3：run_frame(render, sound)、framebuffer()、read_memory()
        │        save_state()、load_state()、set_buttons()
        ▼
Rust core（單一 native boundary，release GIL）
  CPU ─ bus ─ PPU ─ DMA/timers/IRQ ─ audio
  framebuffer / snapshot buffer
```

- Python **不持有**硬體狀態，也不在 instruction／scanline 之間回呼。
- Rust 只在 frame 邊界回傳：`FrameResult`、framebuffer view、event ring（可選）。
- Debug／trace 用 Rust ring buffer，frame 結束後一次讀取；不做 per-instruction
  Python callback。

### Cython 的角色

新 core 不需要 Cython。保留 Cython 只為：

1. `tests/reference/gba_cpu` 的 legacy oracle（測試用，不進 wheel）。
2. 現有 `cpu/core.pyx` 實驗（opt-in，不再擴充）。
3. 遷移期間的 A/B 對照；Rust core 穩定後刪除。

若繼續把 Cython 放在 production core，會變成「Python＋Cython＋Rust」三套
語意／三套 build，維護成本大於收益。**新架構是 Rust core + Python host，Cython
只做 legacy。**

## 舊版：Python / Cython / numpy 分工（legacy）

先釐清名詞：

- **CPython**：執行 Python 的直譯器。所有 facade、RL、fallback 都跑在 CPython。
- **Cython**：把同一批模組編譯成 C extension 的工具；不是另一套 Python，也不是
  另開 `native/` 目錄。
- **numpy**：host-side 陣列庫；只用在 observation／測試／可選的實驗 backend，
  不進 deterministic 硬體核心。

### 分工表

| 區域 | Python（CPython） | Cython（同模組編譯） | numpy | 理由 |
|---|---|---|---|---|
| 公開 API facade：`Emulator`、`GbaApp`、`GBAEnv`、`MemoryView`、`VideoView` | ✅ | — | — | API 穩定、呼叫頻率是 frame／step 邊界 |
| CLI、config 驗證、errors、logging | ✅ | — | — | 非 hot path |
| 輸入 mapping／action latch／keyboard | ✅ | — | — | frame 邊界 |
| RL：observation、reward、termination、process pool | ✅ | — | ✅ | 影格降取樣／灰階用 numpy 很合適 |
| snapshot header、CRC、SHA-256、`.sav` 檔案 IO | ✅ | — | — | 低頻、需要 Python 檔案 API |
| HLE SWI（Div/CpuSet/LZ77 等） | ✅（rare path） | 可選 | — | 一般遊戲不會每 frame 呼叫 |
| debug／breakpoints／trace | ✅ | — | — | 預設關閉，不進 hot loop |
| CPU fetch/decode/execute、registers、exceptions | ✅ reference | ✅ 優先 | — | 每 instruction 執行，Cython 收益最大 |
| bus read/write、memory map、WAITCNT、contention | ✅ reference | ✅ 優先 | — | 每存取一次；typed memoryview 直接讀 RAM/ROM |
| PPU timing：scanline 事件、DISPSTAT/VCOUNT/IRQ | ✅ reference | ✅ | — | 每 scanline／事件；與 renderer 分開 |
| PPU renderer：BG／OBJ／window／mosaic／blending | ✅ reference | ✅ | 可選實驗 | pixel loop；Cython 直接寫 framebuffer 最快 |
| DMA／timers／IRQ scheduler | ✅ reference | ✅ | — | 每 frame 多次；C 迴圈＋固定事件表 |
| 音訊 FIFO／PCM | ✅ reference | 可選 | 可選 | host 端播放可 numpy；硬體 FIFO 仍應 deterministic |
| UI（pygame 視窗／鍵盤） | ✅ | — | — | host-side，不影響核心時間 |
| tests／benchmark／reference | ✅ | — | ✅ | numpy 用於比對／統計，不進模擬狀態 |

### PPU 與 numpy 的結論

**PPU 的 deterministic core 不加 numpy。** PPU 暫存器／scanline／IRQ 與 renderer
都用 Python reference＋同源 Cython 實作。

numpy 只用在：

1. **RL observation**：framebuffer RGB888 → 灰階／resize／批次正規化。
2. **測試與 benchmark**：framebuffer hash、影像比對、統計。
3. **可選的離線 renderer 實驗**：只用來驗證演算法，不是預設 backend。

不在 pixel loop 用 numpy 的原因：

- 240×160 的 scanline 很小，numpy 的 per-call／allocation overhead 很容易吃掉
  向量化收益。
- BG/OBJ/window/priority 有大量分支與小範圍索引；numpy 需要多次 fancy
  indexing 與暫存陣列，反而比 Cython 的直接 memoryview 迴圈慢。
- renderer 要輸出 packed RGB888／RGB555；Cython 可直接寫 buffer，numpy 還要
  dtype 轉換。
- 保持 deterministic core 只用整數與固定 layout；numpy 留在 host-side 比較
  容易維持確定性。

若未來真的需要 GPU／向量化 renderer，會是獨立 backend，不影響上述分工。


## PyBoy 對照

PyBoy 是本專案 API 形狀的參考；它的核心架構（[官方文件](https://docs.pyboy.dk/wiki/development/development.html)、[GitHub](https://github.com/Baekalfen/PyBoy)）可以整理成：

```text
PyBoy.tick()
  -> 處理 input／plugin events
  -> MB.tick()                       # motherboard：Cython 編譯核心
       -> cycles = CPU.tick(target)  # CPU 跑到 cycle target
       -> timer.tick(cycles)
       -> LCD.tick(cycles)
       -> sound.tick(cycles)
       -> interrupts / DMA
  -> plugin post_tick()
```

| PyBoy | gbaemu 對應 | 備註 |
|---|---|---|
| `PyBoy` facade | `GbaApp`／`GBAEnv`／`Emulator` | 公開 API 留 Python |
| `MB`（motherboard） | `Emulator`＋native core | 硬體同步點 |
| `CPU.tick(target)` | CPU `run_until(cycle)` | 一個 C 呼叫跑多個 instruction |
| `LCD.tick(cycles)` | `Ppu.advance(cycles)` | 依 CPU 回報的 cycle 推進 |
| `timer.tick`／`sound.tick` | `Timers`／`SoundController` | 同上 |
| `opcodes_gen.py` → `opcodes.py`／`.pxd` | 未來的 `tools/gen_opcodes.py` → `cpu/opcode_tables.pyx` | 生成 opcode handler／dispatch |
| Cython compiled core＋`.pxd` | 同源 Cython extension | 同一份模組，不另開 `native/` |
| pure Python／PyPy backend | `.py` fallback＋differential | 沒有 extension 時仍可跑 |
| plugins（window／debug／rewind） | RL wrappers、GbaApp UI、debug | 不進核心時間 |

### 關鍵教訓

PyBoy 的 `MB.tick()` 本身是編譯後的 Cython 方法；`CPU.tick(target)` 在 C 層跑完
多個 instruction，才回到 `MB` 推進 timer／LCD／sound。也就是說：

- **只把 `cpu/`、`bus/` 各自編成 extension 並不足夠**：如果 CPU 每條 instruction
  都經 Python 呼叫 `bus.read*`，還是會回到 interpreter overhead。
- 正確做法是讓 CPU／bus／PPU 的熱路徑透過 **shared `.pxd`／`cimport`** 互相呼叫
  `cdef` 方法，或把它們放在同一個 Cython `cdef class`（類 PyBoy `MB`）內。
- Python 只在 **frame／cycle target** 邊界被呼叫；plugins（我們的 UI／RL）
  也在邊界處理 events，不進 hot loop。

這一點已補進 [`NATIVE_CORE.md`](NATIVE_CORE.md) 的「熱路徑邊界」一節。

## 目前架構（Python reference）

```text
                 main.py / CLI / 使用者程式
                          │
       ┌──────────────────┴──────────────────┐
       │                                     │
  gbaemu.GbaApp（PyBoy 風格）          gbaemu.rl.GBAEnv（Gymnasium）
       │                                     │
       └───────────────┬─────────────────────┘
                       ▼
                 gbaemu.Emulator
        step_cycles / step_frame / reset / snapshot
                       │
     ┌─────────────────┼──────────────────────────┐
     ▼                 ▼                          ▼
  Arm7Tdmi         AddressBus                  EventStream
  （週期模型）    （記憶體路由＋I/O）          （非遞減、同 cycle 依 emit 順序）
     │                 │
     │      ┌──────────┼───────────┬─────────────┬──────────────┐
     ▼      ▼          ▼           ▼             ▼              ▼
  cpu/   memory/    devices/    video/        audio/         hle/
         cartridge  dma/timers  ppu+renderer  sound          postboot/swi
```

目前限制：每個 instruction 都經過 `cpu.step()` → `bus.tick()` → `ppu.advance()`
／`timers.tick()`，且 renderer 是 Python 逐 pixel。實測 headless 約 30 fps、
render 約 3 fps。

## 目標架構（同源 Cython 加速）

```text
             Python 控制面（frame 邊界才進來）
  main.py / CLI / GbaApp / GBAEnv / process pool
        │  run_frame()、set_input()、read_observation()、snapshot()
        ▼
  Emulator（Python facade；不變）
        │
        ├── cpu/    ← 同名 .pyd/.so 或 .py fallback
        ├── bus/    ← 同名 .pyd/.so 或 .py fallback
        ├── video/  ← 同名 .pyd/.so 或 .py fallback
        └── devices/、audio/、hle/ …
```

- 沒有第二份 `NativeCore`／`native/bus.pyx`；`cpu/`、`bus/`、`video/` 就是唯一
  實作，Cython 只把它們編譯成 extension（同模組名）。
- 沒有 extension 的平台自動使用 `.py`；`Emulator`／views／RL 完全不變。
- 建置與 fallback 的細節見 [`NATIVE_CORE.md`](NATIVE_CORE.md)。

## 加速邊界

| 層 | 位置 | 粒度 |
|---|---|---|
| Python facade | `emulator.py`、`rl/`、views | frame／cycle 預算 |
| 編譯模組 | `cpu/`、`bus/`、`video/`、`devices/` | 函式／方法內 C loop |
| 狀態 | 既有 classes 的 C array／memoryview | snapshot 不變 |
| 資料 | framebuffer／RAM／event ring 在既有模組 | frame 邊界一次取出 |

Cython 熱路徑不得在 instruction 內呼叫 Python；HLE SWI 等 rare path 可在邊界
callback。

## 時間與不變量

1. **整數 cycle**：所有硬體時間為 `int`；音訊取樣率換算只影響 host-side buffer。
2. **確定性**：`EmulatorConfig.seed`、整數週期、穩定事件排序；`save_state()` 的
   payload 可 hash 比較。禁止 `time.sleep()`、背景 thread 推進硬體。
3. **DMA 不超額**：DMA 成本 `2N + 2(n-1)S + xI` 計入 CPU/PPU 時間；CPU 端
   `step_cycles` 不會超過請求預算。
4. **Frame 邊界**：`step_frame()` 允許最後一條指令跨過 boundary（指令粒度），
   `FrameResult.cycles` 是實際執行 cycle。
5. **Halt**：FUNCTIONAL 模式在 `IE & IF == 0` 時依下一個 PPU IRQ／timer
   overflow／keypad IRQ 事件前進，沒有事件時直接跳到 frame 邊界；TIMED 模式
   保留逐 cycle 精度。
6. **Fallback 等價**：同 ROM／輸入／seed 下，`.py` 與 Cython 編譯版的 CPU state、
   RAM hash、framebuffer hash、event log、cycle count 必須相同。

## 模組責任

| 模組 | 責任 | 主要測試 |
|---|---|---|
| `emulator.py` | 生命週期、frame/cycle 推進、backend 選擇、views、InputPort、DMA 服務、halt fast-forward | `test_emulator.py`、`test_frame.py` |
| `cpu/` | ARM7TDMI 解碼／執行、banked registers、例外、週期模型（reference；native 對照） | `test_cpu_*.py` |
| `bus/` | 記憶體路由、I/O 暫存器委派、存取成本／WAITCNT／contention（reference；native 對照） | `test_bus.py`、`test_io.py`、`test_timing.py`、`test_video_contention.py` |
| `memory/` | WRAM／VRAM／Palette／OAM、cartridge header、SRAM/Flash/EEPROM | `test_save.py`、`test_api_types.py` |
| `video/` | PPU scanline 事件、DISPSTAT／IRQ、Mode 0-5 renderer、window/mosaic/blending | `test_ppu*.py`、`test_frame.py` |
| `audio/` | PSG 四聲道（square×2／wave／noise）、SOUND 暫存器、FIFO A/B、DMA Sound（timer 溢位取樣）、32.768 kHz 混音輸出 | `test_audio.py`、`test_timers.py` |
| `devices/` | DMA0-3（含 FIFO special timing）、timers、keypad | `test_dma.py`、`test_timers.py` |
| `hle/` | HLE post-boot、SWI 0x00-0x2A、BIOS 讀取保護 | `test_hle.py`、`test_swi.py`、`test_irq_hle.py` |
| `state/` | snapshot header（magic／version／ROM SHA-256／config SHA-256／CRC）與九段 payload | `test_snapshot*.py` |
| `rl/` | `GBAEnv`、設定型別匯出、`GbaApp` facade | `test_rl.py` |
| `debug/` | breakpoints、trace、watchpoints | `test_log.py` 等 |
| （無 `native/`） | 加速以同名 Cython extension 編譯 `cpu/`／`bus/`／`video/`；不另建平行實作 | 同一套 tests＋differential |


## 繪圖管線（render pipeline）

優化前 renderer 是 pure Python，且每個 pixel 都回頭呼叫 PPU／VRAM／Palette
的 Python method。cProfile（2 frames）顯示：

```text
render_frame      1.44 s（2 frames）
_text_bg_pixel    307,200 calls
ppu.read_reg16    614,424 calls
vram.read_u8      391,350 calls
palette lookup     76,802 calls
layers.sort        76,800 calls
```

**已實作 frame-level cache（2026-11-01，僅修改 `video/renderer.py`）**：

- `_RenderState`：每 frame 快照 BG descriptors、affine 參數、palette LUT、
  active OAM、window／blend／fade 狀態。
- pixel loop 不再呼叫 `ppu.read_reg16()`／`vram.read_u8()`／`palette.read_u16()`，
  改直接索引 bytearray／palette LUT。
- priority 選擇改為固定 bucket（不再每 pixel `list` + `sort`）。
- BLDY fade 用 32K LUT（依 amount／方向快取）。
- text BG 先解成 240×160 palette-index buffer（`_text_buffer`）：每個 scanline
  只讀一次 tile map、每個 tile 只算一次 char base。
- 單一 text BG、無 OBJ/window/alpha 時走 `_blit_single_text`：palette RGB LUT +
  `b"".join` 直接產生 framebuffer，不再逐 pixel shift。
- 實測（`rom/rom.gba`，60 frames）：render 由約 **3.3 → 23.2 fps**；
  cProfile 的 `_text_pixel` 由 307,200 calls 降到 76,800 calls，
  per-pixel 的 `read_reg16`／`vram.read_u8` 呼叫消失。

所以繪圖加速的方向是**frame 開始時一次快照**，之後只做陣列查表；下一步才是多層／一般情況的同模組 Cython renderer。

### 管線階段

```text
PPU/VRAM/Palette/OAM 狀態
        │
        ▼
prepare_frame()          # 每 frame 一次（Python 或 native）
  ├─ BG descriptors      # mode/char base/screen base/size/scroll/priority
  ├─ affine params       # PA/PB/PC/PD/ref
  ├─ palette LUT         # 512 × RGB888（BG/OBJ）
  ├─ active OAM list     # 只保留可見 sprites
  ├─ window ranges       # 每 scanline 的 mask
  └─ blend state         # BLDCNT/BLDALPHA/BLDY
        │
        ▼
render_scanline(y)       # 240 pixels；純陣列運算（Cython/cdef 或 numpy）
        │
        ▼
present()                # RGB888 framebuffer
                         # 或直接 downsample 成 RL observation
```

### 架構決策

1. **Renderer 是 frame 狀態的純函式**：輸入是 RenderState 快照，不直接呼叫
   PPU object。這樣同一個 renderer 可以被 Python reference、Cython、numpy
   三個 backend 使用，且不會在 pixel loop 產生 Python attribute lookup。
2. **Renderer 與 CPU/bus 解耦**：renderer 只讀 VRAM/Palette/OAM；可以先做
   renderer 加速，不必等 CPU/bus Cython 完成。
3. **同源 Cython**：`video/renderer.py` 是 reference；Cython 版是同模組名的
   extension（`video/renderer.pxd`／必要時 `video/renderer.pyx`），不是新
   `native/renderer.pyx`。沒有編譯平台 fallback 到 `.py`。
4. **資料表示**：
   - `const unsigned short[::1] palette`（512 entries RGB555 → LUT）
   - `const unsigned char[::1] vram`、`oam`
   - `unsigned int[::1] framebuffer` 或 `unsigned char[::1] rgb888`
   - BG/OBJ descriptors 用 `cdef struct`／平行陣列，不用 list of dict。
5. **合成順序**：BG 0–3 與 OBJ 最多 5 層；用固定 priority bucket（0–3）合併，
   不要在每個 pixel 建 list + sort。Window mask 以 scanline 區間計算。
6. **視窗與 RL**：
   - GUI：render 每個 frame 或每 N frame；dirty 時才重繪。
   - RL：observation source 含 screen 時，只 render `frame_skip` 的最後一格；
     可直接輸出 resize 後的解析度，避免 240×160 全畫再縮小。
7. **Native renderer 的驗收**：同 ROM／state 下 framebuffer hash 與 Python
   reference 相同；PPU mode 0/1/2/3/4/5、window、mosaic、blending 的現有
   `test_ppu_modes.py` 全部通過。

### 可選的純 Python 加速（Cython 前）

- ✅ frame-level cache：BG 暫存器／palette LUT／active sprite 只讀一次（已完成）。
- BG tile row cache：每個 scanline 只解一次 tile row，pixel 只做 nibble lookup。
- 固定 priority bucket 取代 `layers.sort`。
- 先用 `tools/bench.py --render` 量測，不急著寫 Cython；若 cache 後仍不足，
  再進同源 Cython renderer。

## PPU 模型

- `Ppu` 只負責 scanline 事件、DISPSTAT 旗標、VCOUNT／LYC、IRQ 與 VRAM bitmap
  mode；BG/OBJ/window/blending 的像素合成在 `video/renderer.py`。
- **逐 scanline 合成**：`Ppu.advance()` 在每條可見 line 進入 HBlank 的瞬間
  （IRQ／DMA 改 register 之前）呼叫 `render_frame(..., y0=line, y1=line+1)`，
  所以 mid-frame raster effect（改 `DISPCNT`／`BGxCNT`／scroll／OAM）即時反映，
  與硬體一致。`_rendered_lines` 記錄本 frame 已畫行數；整個 frame 都沒有逐線
  事件時才在 frame 尾端整張重畫（防禦路徑）。
- **OBJ vs BG 同 priority**：GBATEK Video/OBJ「Priority」規定 OBJ 在上層；
  renderer 的 sprite candidate 用 `order = -1` 保證贏過 BG0-3（`order` 0..3）。
- **Bitmap modes（3/4/5）** 以 BG2 實作：`_render_bitmap_composite()` 疊 OBJ、
  window、alpha/fade；mode 4 的 palette index 0 透明、mode 5 只有左上 160x128
  （其餘顯示 backdrop）。無 OBJ/效果時走 `_render_bitmap()` 快速路徑。
- Video contention：可視掃描線對 VRAM/Palette/OAM 存取 +1 waitstate；HBlank
  VRAM/Palette 0、OAM 需 DISPCNT bit5；VBlank／forced blank 0。

## Snapshot

`save_state()` = header（90 bytes）＋九段 payload：

```text
CPU  BUS  PPU  DMA  TMR  IRQ  KEY  CRT  SCH
```

每段為 `4-byte ID + uint64 length + data`；`load_state()` 驗證 magic／版本／
ROM SHA-256／config SHA-256／CRC 後依序還原，還原後 `events.clear()`，且**不**
自動寫回 `.sav`。EEPROM 的 bit-stream 暫態不保存（只保存備份內容）。
Cython 版模組必須產生相同 payload layout，並通過 .py fallback 的互通測試。

## RL 層

- `rl/env.py::GBAEnv`：Gymnasium API；observation（screen／memory／hybrid）、
  action（buttons／multi_binary／discrete）、frame skip、truncation。
- `rl/wrappers.py::GbaApp`：PyBoy 風格 `tick()`／`stop()`／`button()`／
  `screen.ndarray`，失敗時 headless fallback。
- 權威型別在 `api_types.py`；`rl/spaces.py` 只做匯出，避免兩份定義漂移。
- RL 的 scale-out（process pool）在 Python 層；每個 process 一個 Emulator，
  編譯模組內可 release GIL。

## 遷移順序（摘要）

1. **完成 reference 契約**（已完成）：Python 引擎、snapshot、event、benchmark。
2. **`cpu/` 原地 Cython 化**：加 `.pxd`／轉 `.pyx`，extension 名稱不變；先 cover
   常見 THUMB/ARM、例外；以同一套測試＋differential 驗收。
3. **`bus/` 熱路徑 Cython 化**（同一檔案），再 `video/renderer.py`。
4. **devices／排程熱路徑**；snapshot／HLE 等 rare path 可留在 Python。
5. **平台 wheel／fallback／CI benchmark**。

每一步都保留 `.py` fallback；不建立 `native/` 平行目錄。詳細工作見
[`NATIVE_CORE.md`](NATIVE_CORE.md)。
