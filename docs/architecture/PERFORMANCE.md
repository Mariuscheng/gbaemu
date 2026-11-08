# 效能分析與加速路線

GBA 每 frame 280,896 cycles、每 scanline 1,232 cycles。用 CPython 逐 instruction／
逐 event 模擬時，真正的成本不是算術，而是 **interpreter dispatch、函式呼叫、
attribute 存取與物件配置**。本文件記錄目前量測、已做的優化與可選方案。

## 目前量測（2026-11-01，`rom/rom.gba`，FUNCTIONAL、dev tree）

| 模式 | 速度 | 換算 |
|---|---|---|
| `step_frame(render=False)` | **約 30 fps** | 約 8.4M cycles/s |
| `step_frame(render=True)` | **約 3 fps** | renderer 是瓶頸 |
| legacy Cython `pygba.core`（無 render、uncapped） | 約 61 fps | 約 17M cycles/s |
| legacy Cython（render） | 約 58 fps | Cython renderer 完整很多 |

60 fps 需要 16.8M cycles/s；目前無 render 還差約 2 倍，render 差 20 倍。
若要 RL 吞吐（例如 1000 fps）則需要 281M cycles/s，純 CPython 不可能。

### cProfile（30 frames、無 render）

```text
55,862  cpu.arm7tdmi.step
55,922  bus.address_bus.tick
55,922  video.ppu.advance
55,922  devices.timers.tick
167,646 cpu.arm7tdmi.peek16
167,646 bus.address_bus.peek_u16
82,107  bus.address_bus._read
```

- 約 **1,860 個 CPU instruction／frame**，但裝置 tick 也是約 1,860 次／frame：
  每個 instruction 都呼叫 `bus.tick()` → PPU／timer／sound，函式呼叫成本被放大。
- 此 ROM 開了 **HBlank IRQ**，halt 每個 scanline 都會被喚醒（228 次／frame），
  所以「halt 跳到下一個事件」只能省掉部分 chunk；HBlank 本身就是高頻事件。
- 每次記憶體存取都經過 `peek16`／`align_address`／`_read` 多層 Python 呼叫。

## 已做的優化

1. **Halt event skip**（`Emulator._halted_chunk`）：原本固定 64-cycle chunk；
   現在依 DISPSTAT IRQ／timer overflow／keypad IRQ 計算下一個喚醒點，沒有事件時
   直接跳到 frame 邊界。無 render 由約 27.6 → 30.6 fps。
2. **PPU dirty framebuffer**：VRAM／Palette／OAM／BG 暫存器沒變時不重繪；
   render 由約 1.6 → 3 fps（靜態畫面可再快，但此 ROM 每 frame 仍有寫入）。
3. **Halt fast path 只在 FUNCTIONAL**：TIMED 保留逐 cycle 精度。

## 可選方案

### A. 純 Python 的模型級優化（1.5–3x）

- **批次 device tick**：不要每個 instruction 都 `bus.tick()`；在同一個 scanline
  內累積 cycle，遇到 event 邊界才推進 PPU／timer／sound。CPU 仍逐 instruction，
  但呼叫次數可降一個數量級。
- **事件堆（event heap）**：把 PPU HBlank/VBlank、timer overflow、DMA 完成放進
  同一個 sorted event queue，CPU 跑到下一個 event 才處理裝置。
- **移除常態 overhead**：
  - breakpoints 為空時跳過 `match()`；
  - keypad IRQ 未啟用時不 `poll_keypad()`；
  - `peek()` 路徑用 `__slots__`／local binding，避免 dataclass 與 Event 配置。
- **Renderer**：
  - 已做 dirty；再加 scanline/tile 快取、numpy 向量化 BG/OBJ 合成；
  - RL observation 直接輸出 84×84（而不是先畫 240×160 再 resize）；
  - 視窗模式每 N frame 才 render（模擬照跑）。
- **快速指令路徑**：THUMB 常見指令（MOV/CMP/ADD/B）用查表＋inline，避免多層
  `execute()` dispatch。

預期：無 render 60–100 fps；render 10–20 fps。仍不足以大量 RL。

### A2. Renderer 專項（目前最大單一熱點）

優化前 cProfile（2 render frames）顯示 renderer 佔絕大多數時間：

```text
render_frame      1.44 s
_text_bg_pixel    307,200 calls
ppu.read_reg16    614,424 calls
vram.read_u8      391,350 calls
palette lookup     76,802 calls
layers.sort        76,800 calls
```

問題不是算術，而是 **每個 pixel 都回頭呼叫 PPU／VRAM／Palette 的 Python
method**，以及每 pixel 配置 list + sort。

**已實作（2026-11-01，`video/renderer.py`）**：

1. `_RenderState`：每 frame 一次抓 BG 暫存器、palette LUT、active OAM、
   window/blend 狀態；pixel loop 只查表。
2. 固定 priority bucket（BG0-3＋OBJ）取代每 pixel `list` + `sort`。
3. BLDY fade 32K LUT；palette LUT；直接索引 VRAM bytearray。
4. `_text_pixel` calls 由 307,200 降到 76,800；per-pixel PPU/VRAM method calls 消失。
5. text BG 先解成 palette-index buffer（`_text_buffer`），每個 tile 只解一次 row。
6. 單一 text BG fast path：palette RGB LUT＋`b"".join` 直接輸出 framebuffer。
7. 實測（60 render frames）：**3.3 → 23.2 fps**；無 render 約 38 fps。

仍待做：

- 多層 BG／sprites／window 的一般情況仍未走 fast path。
- RL observation 直接輸出 resize 解析度；GUI 每 N frame render。
- 上述 cache 仍不足才進同模組 Cython renderer（typed memoryviews）；
  Python renderer 保留作 differential。
- 量測一律用 `tools/bench.py --render`，不把固定 fps 當 gate。

### A3. numpy 的角色（不要放進 PPU core）

numpy 適合 host-side observation（灰階、resize、batch 統計）與測試比對；不適合
PPU pixel loop：

- 240px scanline 太小，numpy 呼叫／暫存陣列 overhead 高。
- BG/OBJ/window/priority 大量分支與 fancy indexing。
- 需要 packed RGB888／RGB555；Cython 可直接寫 buffer。
- deterministic core 保持整數／固定 layout。

因此 PPU renderer 走 Python reference → 同源 Cython；numpy 只作為 observation
pipeline 與 benchmark 工具。

### B. 同源 Cython／C extension（建議，10–50x）

把熱路徑編譯成 C：

1. `cpu/cycles.py`、`cpu/arm.py`／`thumb.py` 的 decode/execute
2. `bus/access.py`、`bus/address_bus.py` 的讀寫與對齊
3. `video/renderer.py` 的 BG/OBJ compositing
4. 可選：`devices/timers.py`、`devices/dma.py`

做法：

- 直接編譯現有 `cpu/`、`bus/`、`video/` 模組（同名 extension）；加 `.pxd`／
  typed memoryview，不建立平行 `native/` 樹。legacy `pygba.core` 證明 Cython 可到
  60 fps render、uncapped 61 fps headless。
- 保留目前的 Python reference 作為 differential oracle；以相同 ROM／state hash
  對照，避免 Cython 版語意漂移。
- 注意 free-threaded 3.14：標記 `freethreading_compatible`，每個 process 一個
  emulator（process pool 比 thread pool 安全）。

預期：headless 數百到 1000+ fps、render 60 fps；RL 才真正可用。

### C. 原生 C/C++/Rust 核心（最大，100x+）

- 把 CPU／bus／PPU 寫成 C/Rust，用 pyo3／CFFI 暴露 `run_frames(n, render=False)`、
  snapshot、observation buffer。
- Python 只做 action／reward／observation pipeline；核心完全不進 Python interpreter。
- 成本最高，但可達數千到數萬 fps（依核心最佳化與 frame skip）。

### D. RL scale-out（不改單核心也能增加吞吐）

- **多 process**：每個 process 一個 Emulator／GBAEnv；線性擴 CPU 核數。
- **headless + no render**：`GBAEnv` 只在 observation source 含 screen 時 render，
  且 frame_skip 只 render 最後一格。
- **snapshot branching**：同一 state fork 多條 rollout，省去重跑。
- **低解析度 observation**：直接輸出 resize 後的畫面，減少 renderer 像素數。

## 實機案例：標題畫面是 CPU-bound（2026-11-02）

`rom.gba` 到 Dr. Mario 標題（frame ~1065）後：

```text
render=False：2.54 fps
render=True ：2.45 fps
CPU instructions/frame：15,764
IRQ/frame：5（VBlank）
熱門 PC：0x03003108–0x03003168（IWRAM 內重複 448 次的軟體迴圈）
```

render 幾乎不影響速度，表示瓶頸是 **CPU 執行遊戲自己的 IWRAM 軟體迴圈**
（典型是 M4A 軟體混音／動畫），不是 PPU。純 Python 的 renderer 快取已經不是
這個畫面的主要成本；要讓遊戲跑到可玩速度，必須加速 CPU（Cython），而不是再
優化繪圖。

## PyBoy 的參考數據

PyBoy 是 Game Boy 模擬器，核心（`MB`／CPU／LCD／timer／sound）以 Cython 編譯，
`PyBoy.tick()` 只做 input／plugin 與 frame 邊界；CPU 在 C 層跑到 cycle target，
才回到 Python。它同時保留 pure Python（PyPy）路徑做測試。這與本專案「Python
facade＋同源 Cython core」一致；差別是 GBA 硬體更複雜，且我們必須用 `.pxd`／
`cimport` 讓 CPU→bus 的呼叫留在 C 層，而不是每 instruction 回 Python。

## Rust core 的效能邊界

目前 Python core 的 CPU-bound 案例（標題 15,764 instructions/frame、2–5 fps）
證明：只加速 instruction 沒有用，因為每條 instruction 都跨 Python bus／tick。

Rust core 的目標不是「CPU 快幾倍」，而是把邊界從 **per-instruction** 移到
**per-frame**：

```text
Python: run_frame(render, sound)
Rust:   280,896 cycles（CPU + bus + PPU + IRQ + DMA + timers）
Python: framebuffer / observation / reward
```

驗收方式：

- 同一 ROM／輸入／frame 的 framebuffer hash、RAM/VRAM hash 與 Python reference 相同；
- `tools/bench.py` 量 frame throughput；
- `GBAEnv` 多 process／free-threaded 平行時，Rust 在 `allow_threads` 內執行；
- 不在文件寫死未量測的 fps gate。

## 實測：Rust native vs Python（2026-11-02）

`tools/bench_native.py` 用同一個 Mode 3 test ROM，render=True，量 60 frames：

```text
frames=60
python : 75.618s      0.8 fps  cycles/frame=280896
rust   :  0.497s    120.7 fps  cycles/frame=280896
speedup: 152.17x
```

量測方式：

```powershell
.\venv\Scripts\python.exe tools\bench_native.py --frames 60
```

注意：

- 這是 **frame-level** 比較：Rust 只在 `step_frame()` 邊界回到 Python，framebuffer
  仍是複製成 bytes 給 Python；若直接取用 Rust buffer 可再省 copy。
- Python 這裡包含整張 240×160 renderer；Rust renderer 也在 native 內。
- 0.8 fps 與先前 `rom.gba` CPU-bound 的 2.45 fps 不是同一 workload；這支 test ROM
  是固定 Mode 3 pattern，主要成本在 Python per-pixel renderer。
- 不在文件寫死 production fps gate；每次改動 Rust PPU／CPU 後重跑。

## 實測：真實 ROM（rom/rom.gba）

同一支 ROM、相同 120 frames、render=True：

```text
python : 7.572s    15.8 fps hash=03ec38bb3bb491c5
rust   : 0.835s   143.7 fps hash=03ec38bb3bb491c5
match  : True
speedup: 9.07x
```

300 frames 也做過 framebuffer hash 對照，兩邊完全相同。量測方式：

```powershell
.\venv\Scripts\python.exe tools\smoke_real_rom.py --rom rom/rom.gba --frames 120
```

這支 ROM 早期畫面主要還是 CPU／初始化路徑，native speedup 約 9×；比 synthetic
Mode 3 的 152×低，因為 Python 這支 ROM 的 renderer 比重較小，且 Rust 這裡仍會
每 frame 產生完整 framebuffer。

## 實測：其他真實 ROM（30 frames）

同一支 `tools/smoke_real_rom.py`，render=True；每支都比對 framebuffer hash：

| ROM | Python | Rust | 加速 | hash |
|---|---:|---:|---:|---|
| `armwrestler.gba` | 0.4 fps | 66.9 fps | 162.7× | 相同 |
| `rates.gba` | 1.5 fps | 114.7 fps | 76.5× | 相同 |
| `Tetris.gba` | 1.3 fps | 83.3 fps | 64.6× | 相同 |
| `RetroRegen-GBA-Test-v1.5.gba` | 0.6 fps | 122.5 fps | 196.3× | 相同 |
| `GBAUtilityTools.gba` | 0.6 fps | 115.1 fps | 188.7× | 相同 |

`GBAUtilityTools` 60 frames 亦完全相同（Python 0.6 fps vs Rust 120.6 fps，
200.5×）。這些短 ROM 的 Python 路徑以 boot／初始化與高頻 per-instruction
boundary 為主，因此加速比高；`rom.gba` 的 9× 較能代表進入遊戲迴圈後的比例。
真正長跑、多 process 與 RL rollout 的 throughput 仍待 G7 soak。

## 多 ROM smoke（2026-11-04，round 13–15 之後）

同一支 `tools/smoke_real_rom.py`（Python `render=True` vs Rust native frame hash）：

| ROM | frames | hash 相同 | Rust | 加速 |
|---|---|---:|---:|---:|
| `rom.gba` | 60 | ✅ | 121.7 fps | 12.2× |
| `song.gba` | 30 | ✅ | 103.9 fps | 70.3× |
| `Tetris.gba` | 30 | ✅ | 79.4 fps | 69.0× |
| `rates.gba` | 30 | ✅ | 122.5 fps | 81.8× |
| `armwrestler.gba` | 60 | ✅ | 69.5 fps | 168.0× |
| `RetroRegen-GBA-Test-v1.5.gba` | 60 | ✅ | 129.2 fps | 224.2× |
| `GBAUtilityTools.gba` | 60 | ✅ | 91.1 fps | 180.3× |
| `suite.gba`（主選單） | 30 | ✅ | 130.8 fps | 64.9× |
| `Pocket Monsters_LeafGreen.gba` | 20 | ❌ | 104.7 fps | 215.7× |

- **LeafGreen**：2026-11-04 補完 SRAM／Flash save-type 之後，SRAM 內容已完全
  相同（128 KiB flash、bank／命令序列都對），但 frame 1 起 IWRAM（stack）
  同 **IO 的 sound 暫存器**（0x63／0x69／0x79／0x80–0x84／0x89）已經唔同 →
  framebuffer 到 frame 10 才分叉。即係話 LeafGreen 剩低嘅差異係 **sound 引擎
  同 IRQ／DISPSTAT 行為**（Python 有完整 PSG／FIFO 模型，Rust 較簡），同
  save／timing 都無關。
- `test-rom` 細 ROM（10 frames）：12 支之中 7 支相同、4 支不同（`arm.gba`、
  `arm-ref/arm.gba`、`DMA_Outside_Bios_Bus.gba`、`DMA_Mode_Change.gba`）、
  1 支冇輸出（`Coprocessor_14.gba`）。呢批 CPU 測試 ROM 唔喺原有驗證清單；
  抽樣 360 個隨機編碼比較 Python／Rust 成本，有 11 個（~3%）唔同（coprocessor／
  未定義／條件指令路徑），屬既有 parity 缺口，同本輪 timing 改動無關。
- `rom.gba` 係 EEPROM（`EEPROM_V`）：Rust 未實作序列 EEPROM，`region_info`
  仍然報 65536（Python 8192）；因為早期未用到 EEPROM，30 frames framebuffer
  仍然相同。

## GUI 實測：Tetris Worlds 開頭載入

`GbaApp` 現在預設優先使用 native。同一支 `rom/Tetris.gba`：

```text
GbaApp 前 30 frames（native）：0.319s → 94 fps
3000 frames 平均（native）  ：35.6 fps
Python reference            ：0.6–1.5 fps
```

Tetris Worlds 的開頭不是即時標題畫面：約 frame 600 前 VRAM 只有一個
透明 BG tile，畫面是黑底＋左上白格；約 frame 1200 才出現 Saturn logo，
frame 2400 出現 `PRESS START`，按 START 後進主選單。也就是說白格是 boot
期真實 tilemap 內容，不是 renderer 把 tile 畫錯。用 Python backend 時
1200 frames 要十幾分鐘，看起來就像永久黑屏；native 則約 15–35 秒。
BIOS Huffman／ArcTan／Div HLE 修正後，frame 360 的 `SUCCESS` 廠商 logo
與 frame 1200 的 `TETRIS WORLDS` title 都已完整顯示。

## 建議順序（與架構文件一致）

目標架構是 **Python 控制面 + native 資料面**，不是繼續在 CPython 裡微調。
完整設計見 [`NATIVE_CORE.md`](NATIVE_CORE.md)。

1. **已完成（reference）**：Python 引擎、snapshot、event 契約、`tools/bench.py`、
   differential 測試；halt event skip 與 dirty framebuffer 先作為 stopgap。
2. **同源 Cython Stage 1**：`cpu/` 加 `.pxd`／編譯同名模組，再 `bus/`；renderer
   暫留 Python；以同一套 tests＋differential 驗收。
3. **Renderer 專項（可先做）**：`video/renderer.py` 的 frame-level cache →
   Cython scanline compositor；畫面與 Python reference 相同。
4. **Stage 3**：native save media／HLE rare callback／snapshot 互通。
5. **Stage 4**：平台 wheel、process pool、CI benchmark gate。
6. **長期**：若 RL 需要 >1000 fps 或大規模 rollout，再評估 Rust/C 核心；
   不要一開始就寫 JIT。

純 Python 的批次 device tick、renderer 快取仍值得做（成本低、可立即量測），
但它們是 stopgap，不改變同源 Cython 的長期方向。

Native 實作細節（facade 保留、cdef class／typed memoryviews、opcode table
預生成、`run_frames(n)` 批次 API、build flags 只套用熱路徑）見
[`NATIVE_CORE.md`](NATIVE_CORE.md)。

## 量測方式

```powershell
# no-render / render 速度
.\venv\Scripts\python.exe tools\bench_native.py --frames 60

# cProfile
python -m cProfile -s tottime -m pytest tests/gbaemu/test_frame.py
```

建議把「模擬 GBA frame / host second」納入 CI 的 benchmark report（規格 Phase 5
驗收），每次改動 CPU／bus／renderer 後比較。
