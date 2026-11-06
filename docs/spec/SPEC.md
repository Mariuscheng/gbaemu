# GBA 模擬器與 RL 介面設計規格（Struct 完整版）

**文件狀態：** Draft 0.5
**目標語言：** CPython 3.11+
**硬體資料來源：** GBATEK
**API 設計參考：** PyBoy 的公開 Python 介面概念；不使用 PyBoy 原始碼、內部實作、文件原文或其程式碼片段
**預期用途：** 可測試的 GBA 相容性研究、除錯、工具開發，以及未來的強化學習（RL）環境
**本版變更（0.5）：** 新增 3.6 節「時序模型」：時鐘／frame 常數（1232 cycles/line、280,896 cycles/frame）、S／N／I／C 定義、ARM／THUMB 指令週期表、記憶體存取成本與 WAITCNT、PPU／DISPSTAT 事件 cycle、IRQ／DMA／timer 時序、TimingMode 語意與 Phase 2/3 驗收條件
**前版變更（0.4）：** 套件結構改為「專案根目錄 = `gbaemu` 套件根」，移除內層 `gbaemu/`；第 4 章樹狀圖、範例路徑與 `TODO.md` 的執行指令同步調整；5.4 的 `EventStream.poll()` 排序語意改為「非遞減、同 cycle 依 emit 順序」
**前版變更（0.3）：** 啟動策略改為進階 HLE 為預設（`BootMode.HLE_ADVANCED`）；新增 2.1 節 HLE 契約（post-boot state、SWI 0x00–0x2A 功能表、BIOS 讀取保護、HLE 自我驗證；REQUIRE_BIOS 僅 legacy）；套件結構加入 `hle/` 模組
**前版變更（0.2）：** 新增第 5 章「公共資料結構（struct 定義）」；補完 API 契約；修正 Game Pak 視窗、VRAM 分界、8-bit 寫入與 EEPROM 位址等硬體細節；加入 Harness 執行規則與各 Phase 驗收條件

---

## 0. 給 Harness 的執行規則

本文件是交給 coding agent（DeepSeek Harness / DeepSeek 4.1 Flash）逐 Phase 實作的規格。實作時必須遵守：

1. **範圍紀律。** 只實作本文件明確要求的內容。文件未定義的行為，不要自行擴充；將疑問記錄到 `TODO.md` 的 "Open Questions" 段落，並選擇最保守（不改變硬體語意）的方案。
2. **每項改動要有測試。** 新增任何 struct、方法或硬體行為時，必須同時新增最小單元測試。禁止只改實作不加測試。
3. **型別契約不可漂移。** 第 5 章的公共型別是唯一權威定義（single source of truth）。其他章節引用這些名稱，不得重複定義或私下改名。
4. **Phase 順序。** 按第 9 章順序實作。每完成一個 Phase，執行全部測試、更新 `TODO.md`、回報已完成與未完成項目，才開始下一個 Phase。
5. **原始碼註解必須標記 GBATEK 章節** 對應每個非直觀硬體行為，以註解形式引用（如 `# GBATEK: LCD Registers - DISPSTAT`），不得複製 GBATEK 原文段落。
6. **clean-room。** 不得複製 PyBoy 或任何第三方模擬器的程式碼、測試資產、文件段落。所有程式自行撰寫。

---

## 1. 設計目標與非目標

本專案是一個以 Python 為主的 GBA 模擬器。它的第一目標不是立即做到所有遊戲都能完美執行，而是建立清楚的硬體模型、可重現的時間系統、可觀測的除錯介面，以及適合批量 RL rollout 的低開銷控制層。

實作應遵守下列原則：

- **硬體行為與上層 API 分離。** CPU、匯流排、記憶體、PPU、DMA、計時器、音訊和輸入都是模擬核心；Python API 只是控制與觀測層。
- **以 GBATEK 的規格描述為實作依據。** 記憶體區段、I/O 暫存器、ARM7TDMI 指令、顯示時序、DMA 和中斷都應在程式碼中留下來源註記。[1]
- **採用 clean-room 實作。** 不複製 PyBoy 的程式碼、類別內部結構、文件段落或測試資料。可以借鑑「一個 Python 物件控制模擬器」這種一般性 API 思路，但名稱、型別、行為契約和實作均自行設計。
- **確定性優先。** 相同 ROM、BIOS 設定、輸入序列和初始狀態，必須得到相同 CPU 狀態、記憶體、畫面和事件序列。
- **RL 友善。** 支援無畫面執行、frame skip、batch instance、狀態 snapshot/restore、固定 action space，以及不依賴 GUI 的觀測介面。

下列內容不屬於第一階段範圍：真實硬體 link cable、**完整 BIOS 二進位逆向**（進階 HLE 以 GBATEK 文件化行為為準，不反組譯 Nintendo BIOS 二進位）、所有未公開 cartridge 特殊晶片、RTC（先在 cartridge 介面保留擴充點，見 3.5）、GBA SP 的實體背光行為，以及以商業 ROM 或 BIOS 作為專案附帶檔案。

## 2. 授權、資料與 clean-room 邊界

GBATEK 是本專案的硬體研究參考資料，不等於可以把其整份內容直接嵌入程式碼或文件。實作只應保留必要的數值規格、暫存器語意、時序規則和來源連結，並以自己的文字和測試描述重新表達。

PyBoy 只作為公開 API 形狀的參考。不得從 PyBoy 儲存庫複製程式碼、類別階層、私有屬性、測試 ROM、截圖、文件原文或實作細節。新專案使用套件名稱 `gbaemu`，並自行定義類別、例外和方法命名。

本專案不分發 Nintendo BIOS、商業遊戲 ROM、遊戲素材或任何需要使用者另行取得的檔案。BIOS 可以在本機由使用者明確提供；啟動行為由 `BootMode`（見 5.1）控制，**預設採用進階 HLE**：

1. `HLE_ADVANCED`（預設）：不依賴 BIOS 檔案，以 Python 原生實作 BIOS 啟動後狀態與 SWI 功能，完整契約見 2.1。
2. `TEST_ROM_ONLY`：只執行不需要 BIOS 啟動流程的測試 ROM（最小驗證路徑）。
3. `REQUIRE_BIOS`（legacy／僅相容性測試）：保留給舊測試與 optional differential；
   **不是 production 路徑**，專案與 CI 不得依賴真實 BIOS。

### 2.1 進階 HLE 啟動路徑（預設）

進階 HLE 的目標是：**在沒有 BIOS 檔案的情況下，令機器狀態等同真實 BIOS 完成啟動的狀態**，而不只是「跳過 BIOS」。實作依據是 GBATEK 對 BIOS 行為的文件化描述（暫存器初值、SWI 功能語意），clean-room 原則同樣適用：不得反組譯、複製或內嵌 Nintendo BIOS 二進位，只可依文件化行為自行實作。

#### 2.1.1 Post-boot state

HLE 啟動完成時，模擬器必須達到以下狀態（GBATEK：BIOS Default Settings）：[1][2]

- CPU 進入 System mode，PC = `0x08000000`（ROM entry），ARM state。
- Stack pointer 初值：`SP_usr/sp_sys = 0x03007F00`、`SP_irq = 0x03007FA0`、`SP_svc = 0x03007FE0`。
- `0x03007FF8`（IRQ check flags）與 `0x03007FFC`（使用者 IRQ handler 指標）清為 0。
- BIOS 會把 ROM header（`0x08000000` 起 `0xC0` bytes）複製到 `0x02000000`，HLE 必須同樣執行此複製。
- 執行 header checksum 驗證語意（complement check）；HLE 模式下檢查失敗行為應記錄事件而非中止（與真實硬體寬鬆行為一致，供測試 ROM 使用）。

以 struct 表達（定義於 `hle/postboot.py`）：

```python
@dataclass(frozen=True, slots=True)
class PostBootState:
    sp_usr: int = 0x03007F00
    sp_irq: int = 0x03007FA0
    sp_svc: int = 0x03007FE0
    mode: int = 0x1F              # System mode
    pc: int = 0x08000000
    thumb: bool = False
    header_src: int = 0x08000000
    header_dst: int = 0x02000000
    header_size: int = 0xC0
    clear_irq_check: int = 0x03007FF8   # 與 0x03007FFC 一併清零
```

#### 2.1.2 SWI dispatch table

HLE 必須以 dispatch table 攔截並原生實作 GBATEK 文件化的 BIOS SWI 功能（`0x00`–`0x2A`）：[1][2]

| 範圍 | 功能 | 實作要求 |
|---|---|---|
| `0x00`–`0x0A` | SoftReset、RegisterRamReset、Halt、Stop、IntrWait、VBlankIntrWait、Div、DivArm、Sqrt、ArcTan、ArcTan2 | 全部完整實作；`IntrWait`/`VBlankIntrWait` 對接事件排程器，不得使用 wall-clock |
| `0x0B`–`0x10` | CpuSet、CpuFastSet、GetBiosChecksum、BgAffineSet、ObjAffineSet、BitUnPack | 全部完整實作 |
| `0x11`–`0x18` | LZ77／Huffman／RL／Diff 解壓縮（Wram/Vram 變體） | 全部完整實作；RL 的壓縮/解壓行為是相容性高風險區，必須有逐 byte 測試 |
| `0x19` | SoundBias | 完整實作 |
| `0x1A`–`0x2A` | Sound driver 系列（SoundDriverInit 等）、MultiBoot、HardReset、CustomHalt | 已文件化者按文件實作；未文件化者（SoundWhatever0–4、HardReset 等）預設 raise `HleUnsupportedSwiError`（strict 模式），lenient 模式記錄事件後以 no-op 繼續 |
| `0x2B`–`0xFF` | 無效 SWI | 真實硬體會跳至 garbage address（crash）；HLE 一律 raise `HleUnsupportedSwiError`，不模擬 crash 本身 |

SWI 呼叫慣例依 GBATEK：ARM state 用 `SWI NN*10000h`、THUMB state 用 `SWI NN`，參數以暫存器傳遞；dispatch 實作不得影響 cycle 計算的確定性。

#### 2.1.3 BIOS 讀取保護

真實 BIOS 有讀取保護：只有 PC 位於 BIOS 區域內才能讀取其內容；PC 在 BIOS 外時，讀取回傳「最近一次成功取出的 BIOS opcode」。HLE 沒有真實 BIOS 內容，但仍必須實作此語意的可觀測部分：HLE 模式下 BIOS 區域讀取回傳一個固定近似值（記錄於 `PostBootState` 相關文件），並在 timed mode 文件中標明此為已知近似，不得靜默假裝等同真實 BIOS。

#### 2.1.4 HLE 自我驗證（不需要真實 BIOS）

**HLE 是 production 的 canonical 啟動路徑**，不是「沒有 BIOS 時的替代品」。驗收
必須完全在專案內完成，不依賴使用者提供 Nintendo BIOS：

1. **post-boot state**：SP、mode、PC、`0x02000000`–`0x020000BF` header copy、
   IRQ 狀態與 GBATEK 文件化值一致。
2. **SWI 功能表**：`0x00`–`0x2A` 的 dispatch、參數／回傳值、Div／CpuSet／
   LZ77／RL 等逐 byte 驗證；未文件化／無效 SWI 的 strict／lenient 行為。
3. **IRQ／BIOS 讀取保護**：HLE IRQ stub 的 return、`pc_in_bios` 可觀測行為、
   BIOS 區域讀取的固定近似；不得靜默假裝等同真實 BIOS。
4. **ROM smoke**：至少一個商業 ROM／測試 ROM 在無 BIOS 檔案下可完成開機、
   進入 VBlank IRQ 並穩定跑 frame。

真實 BIOS 等價測試**不是專案需求**：若使用者自行提供 BIOS，可作本機 optional
differential，但不進 CI、不進 wheel、不作為 release gate。`REQUIRE_BIOS` 僅為
legacy 相容性保留，後續版本可移除；新的 HLE 功能不得以「真 BIOS 有做」為
理由跳過測試。

## 3. GBA 硬體模型範圍

### 3.1 位址空間與匯流排

第一版應建立 32-bit 位址解碼器，並把各區段映射為獨立的 `MemoryRegion`。GBATEK 列出的主要 GBA 區段如下：[1][2]

- `0x00000000–0x00003FFF`：BIOS，16 KiB，唯讀。
- `0x02000000–0x0203FFFF`：外部 WRAM，256 KiB。
- `0x03000000–0x03007FFF`：內部 WRAM，32 KiB。
- `0x04000000–0x040003FE`：I/O 暫存器（區域按 1 KiB 解碼；未定義位址的讀寫行為須明確實作，不得 silently 成功）。
- `0x05000000–0x050003FF`：Palette RAM，1 KiB。
- `0x06000000–0x06017FFF`：VRAM，96 KiB。
- `0x07000000–0x070003FF`：OAM，1 KiB。
- Game Pak ROM：三個互為鏡像的 32 MiB 視窗，分別對應 WAITCNT 的 WS0/WS1/WS2 設定：[2]
  - `0x08000000–0x09FFFFFF`（WS0）
  - `0x0A000000–0x0BFFFFFF`（WS1）
  - `0x0C000000–0x0DFFFFFF`（WS2）
- `0x0E000000–0x0E00FFFF`：Game Pak SRAM／Flash，最多 64 KiB，8-bit 存取模型。

**VRAM 的 BG/OBJ 分界隨顯示模式改變**，不得寫死為固定分割：[2]

| 顯示模式 | BG 區域 | OBJ 區域 | 分界位址 |
|---|---|---|---|
| Mode 0/1/2（tile） | 64 KiB | 32 KiB | `0x06010000` |
| Mode 3/4/5（bitmap） | 80 KiB | 16 KiB | `0x06014000` |

**8-bit 寫入行為**（GBATEK：Memory Control / VRAM）：[2]

- BG VRAM 與 Palette RAM：8-bit 寫入會把該值同時複製到對應半字的高低 8 位（等同 `[addr & ~1] = data * 0x101`）。
- OBJ VRAM 與 OAM：8-bit 寫入被忽略，記憶體不變。
- Game Pak SRAM／Flash：匯流排限制為 8-bit，CPU 只能以 `LDRB`/`LDRSB`/`STRB` 存取，且 **DMA 不能存取 SRAM 區域**。

實作不能只把所有區段放進一個 Python `bytearray`。需要由匯流排處理：

- 8/16/32-bit 存取寬度與上述特殊寬度規則。
- 小端序。
- 對齊與非對齊存取策略。
- 不同區段的唯讀、唯寫和受限寬度規則。
- ROM wait state（WS0/WS1/WS2 各自的 non-sequential/sequential 週期）。
- VRAM、Palette RAM 和 OAM 在顯示期間的存取限制。

早期功能版可以先採「功能正確、週期近似」模式；CPU timing、DMA 競爭和 PPU 影響則放入第二階段的 cycle-aware bus。兩種模式必須共享相同的 API，不能讓上層 RL 程式依賴某一種內部時序實作。

### 3.2 CPU：ARM7TDMI

CPU 核心必須支援 ARM state 與 THUMB state，並實作：

- 通用暫存器 `r0–r15`。
- CPSR 與必要的 banked registers（含各 exception mode 的 `r13`/`r14`、`spsr`）。
- N、Z、C、V 條件旗標。
- ARM data processing、load/store、block transfer、branch、multiply、PSR transfer 等指令群。
- THUMB 的 ALU、load/store、stack、branch、multiple-transfer 等指令群。
- IRQ、SWI 和 reset 等例外入口。
- PC pipeline 可觀測的行為，至少在除錯器中提供架構上可理解的 PC 值。

建議把解碼和執行分開：

```text
fetch -> decode -> execute -> memory access -> writeback -> exception check
```

Python 的第一版可以用清楚的 interpreter 完成功能；效能版再將熱點替換成 Cython、C extension 或 vectorized host-side code。不要在第一版就把核心寫成難以驗證的巨型 opcode switch。

每個 opcode 應可透過單元測試驗證：輸入暫存器、記憶體、CPSR、執行後狀態、記憶體副作用和週期數。測試向量應自行產生或使用可合法使用的公開測試 ROM，不要把第三方模擬器的私有測試資產直接拷貝進來。

CPU 的**內部可變狀態**（snapshot 用）與**對外唯讀觀測** `CPUState`（見 5.5）分開建模：

```python
# cpu/registers.py — 內部可變狀態（此為示意，欄位以實作為準）
@dataclass(slots=True)
class Arm7CoreState:
    regs: list[int]                 # r0-r15，index 0-15
    cpsr: int
    spsr: int
    banked: dict[int, tuple[int, int]]  # mode -> (r13, r14)
    banked_spsr: dict[int, int]
    pipeline: list[int]             # 內部 pipeline 暫存
    halted: bool                    # HALT 狀態，等待中斷
```

### 3.3 PPU、顯示模式與時序

PPU 第一階段應依序支援：

1. Mode 3：bitmap 240×160、16-bit 色彩。
2. Mode 4：bitmap 240×160、8-bit palette、page flipping。
3. Mode 0：tile-based BG，支援基本文字背景。
4. Mode 1/2：多背景與 affine 背景。
5. OAM sprite、優先順序、透明色和基本 blending。

畫面輸出應是固定形狀的 framebuffer（見 5.5 `VideoView`），不直接依賴 Pillow、SDL 或 GUI。GUI 只消費 framebuffer。這樣 RL 可以關閉繪製，或只每 N 個 frame 取一次畫面。

PPU 應採 scanline/event 驅動模型：

```text
visible scanlines -> HBlank -> next scanline -> VBlank -> frame boundary
```

在硬體模型中，DISPSTAT、VCOUNT、VBlank/HBlank IRQ、HBlank/VBlank DMA 和可存取區段限制必須與 PPU 事件連動，而不是在 frame 結束時一次補算。具體要求：

- 每條 scanline 依序產生 HBlank 起始／結束事件；`VCOUNT` 在每條 scanline 邊界更新。
- 進入 scanline 160 時產生 `VBLANK_START`；離開 scanline 227 時產生 `FRAME_BOUNDARY`。
- `DISPSTAT` 的 VBlank/HBlank/VCOUNT match 旗標與 IRQ enable 位必須即時反映目前 PPU 位置。
- HBlank DMA 與 VBlank DMA 由 PPU 事件觸發，不是 frame 結束補算。

### 3.4 DMA、計時器與中斷

GBA 有四個 DMA 通道，通道優先序由 DMA0 到 DMA3；DMA 可使用立即、VBlank、HBlank 或特殊時機，並可選 16-bit/32-bit 傳輸、位址遞增/遞減/固定和完成 IRQ。[1]

Timer 模組需支援四個 16-bit 計時器、reload value、prescaler、cascade/count-up、overflow IRQ，以及與音訊取樣的連動。中斷控制器至少需支援 `IME`、`IE`、`IF`、IRQ source latch 和中斷 acknowledge 行為。KEYINPUT、KEYCNT 和十個按鍵的 active-low 語意也應正確實作。[1]

所有這些周邊都應透過事件排程器協作，而非各自擁有無法排序的 Python thread。模擬器內部禁止使用真實時間或背景執行緒決定硬體事件；硬體時間只能由 CPU cycle 或明確的 event queue 推進。內部排程器型別見 5.6；注意 `ScheduledEvent` 是內部排程用，與對外 `EmulatorEvent`（見 5.4）不同，`poll()` 不得消耗或暴露硬體排程內部事件。

各裝置的內部狀態 struct（snapshot 必須完整保存這些欄位）：

```python
# devices/dma.py
@dataclass(slots=True)
class DmaChannelState:
    channel: int              # 0-3
    source: int               # 32-bit 來源位址
    dest: int                 # 32-bit 目的位址（內部遞增後的目前值）
    word_count: int           # 剩餘傳輸數
    control: int              # DMA_CNT_H 原始值
    active: bool
    irq_enable: bool

# devices/timers.py
@dataclass(slots=True)
class TimerState:
    index: int                # 0-3
    counter: int              # 目前計數（0-65535）
    reload: int               # reload value（0-65535）
    control: int              # TMxCNT 原始值
    prescaler: int
    cascade: bool
    irq_enable: bool
    ticks_pending: int         # 週期累積（套用 prescaler 前）

# devices/interrupts.py
@dataclass(slots=True)
class InterruptState:
    ime: int
    ie: int
    _if: int                  # IF latch
    irqs_pending_mask: int     # 裝置已拉起、尚未被 CPU acknowledge 的位元

# devices/keypad.py
@dataclass(slots=True)
class KeypadState:
    keyinput: int             # 反映目前按鍵（active-low）
    keycnt: int
    keycnt_irq_enable: bool
    keycnt_condition_all: bool  # True = AND 邏輯，False = OR 邏輯

# video/ppu.py
@dataclass(slots=True)
class PpuState:
    dispstat: int
    vcount: int
    dispcnt: int
    scanline: int             # 0-227
    in_vblank: bool
    in_hblank: bool
    frame: int                # 已完成 frame 數
```

### 3.5 音訊、輸入與 cartridge

音訊先提供兩種模式（`AudioMode`，見 5.1）：

- `DISABLED`：RL 高速訓練的預設模式。
- `BUFFERED`：產生可取出的 PCM buffer，不直接播放。

第一階段可以先實作 legacy sound channels 與 FIFO DMA 的基本時序，再逐步補足混音、bias 和取樣率。音訊輸出不應阻塞模擬核心。

Cartridge layer 使用介面抽象特殊硬體：

```python
# memory/cartridge.py
class Cartridge(Protocol):
    def read_rom(self, address: int) -> int: ...
    def read_save(self, address: int) -> int: ...
    def write_save(self, address: int, value: int) -> None: ...
    def save_type(self) -> SaveType: ...
    def snapshot(self) -> bytes: ...
    def restore(self, state: bytes) -> None: ...
```

save 類型（`SaveType`，見 5.1）分為獨立模組：`NONE`、`SRAM`、`FLASH_64K`、`FLASH_128K`、`EEPROM_512B`、`EEPROM_8K`。不要把 save 類型判斷散落在 bus、CPU 和 API 各處；由 cartridge 模組統一負責偵測（`DETECT` 模式）與回報。

**EEPROM 位置注意：** 依 GBATEK，EEPROM 以 bit-serial 方式映射在 ROM 區域頂端（典型 `0x0DFFFF00–0x0DFFFFFF`；ROM ≤ 16 MB 時可出現在 `0x0D000000` 以上任意位置），並非位於 `0x0E000000` 的 SRAM 視窗。[2] 實作 EEPROM 時應在 cartridge 模組內處理此位址判定，不得讓 bus 直接猜測。

**RTC 預留：** `Cartridge` protocol 第一階段不包含 RTC，但實作時應將 cartridge 控制器狀態（含 save 記憶體與控制器內部狀態）集中在 `snapshot()`/`restore()`，令未來加入 RTC 時不必改變 snapshot 格式以外的介面。

ROM header 分析只負責辨識和報告，不應自動下載任何內容。

### 3.6 時序模型（Timing）

本節是**週期數的唯一權威定義**。CPU、bus、PPU、DMA、timer 的實作與測試數值一律以此為準；各模組不得自行發明近似值，實作時以 `# GBATEK: <章節名>` 標記來源（規格 0.5）。

數值來源：GBATEK「ARM CPU Instruction Cycle Times」、「GBA Memory Map」、「4000204h - WAITCNT」、「LCD Dimensions and Timings」、「GBA DMA Transfers - Transfer Rate/Timing」、「GBA Timers」。

#### 3.6.1 時鐘與 frame 常數

| 項目 | 數值 |
|---|---|
| 系統時鐘 | 16.78 MHz（16×1024×1024 = 16,777,216 Hz；1 cycle ≈ 59.59 ns） |
| 每條 scanline | visible 240 dots（960 cycles）＋ H-Blank 68 dots（272 cycles）＝ **1232 cycles** |
| 每 frame | visible 160 lines（197,120 cycles）＋ V-Blank 68 lines（83,776 cycles）＝ **280,896 cycles**（≈59.737 Hz） |

這些數字只在一個模組定義（`timing.py`／`video/ppu.py`）並由其他模組引用；建議常數名：`SYSTEM_CLOCK`、`PPU_LINE_CYCLES`、`PPU_FRAME_CYCLES`、`PPU_VISIBLE_LINES`、`PPU_TOTAL_LINES`、`PPU_HBLANK_START`。

#### 3.6.2 Cycle 種類（S／N／I／C）

| 種類 | 意義 | 執行時間 |
|---|---|---|
| S | Sequential：位址緊接上一次存取（GBA 稱 2nd access） | 1 + 該區 S wait state |
| N | Non-sequential：位址與上次無關（GBA 稱 1st access） | 1 + 該區 N wait state |
| I | Internal：CPU 忙於運算、不存取匯流排 | 1（無 wait state） |
| C | Coprocessor：GBA 無協處理器，實際不出現 | — |

#### 3.6.3 指令週期（ARM）

| 指令 | Cycles | 備註 |
|---|---|---|
| ALU（data processing） | 1S | 載入 R15：+1S+1N；以暫存器移位：+1I |
| MRS／MSR | 1S | |
| LDR | 1S+1N+1I | 載入 R15：+1S+1N |
| STR | 2N | |
| LDM | nS+1N+1I | 載入 R15：+1S+1N |
| STM | (n-1)S+2N | |
| SWP | 1S+2N+1I | |
| B／BL | 2S+1N | |
| SWI／例外進場 | 2S+1N | |
| MUL | 1S+mI | m 由乘數最高有效 byte 決定（1..4） |
| MLA | 1S+(m+1)I | |
| MULL | 1S+(m+1)I | |
| MLAL | 1S+(m+2)I | |
| 條件不成立（{cond} false） | 1S | |
| CDP／LDC／STC／MCR／MRC | — | GBA 無協處理器，視為未定義指令（UND 例外） |

`n` = 傳輸字數；上表為 ARM 模式。

> 注意：上表是 ARM7TDMI 的基準值；GBA 的 GamePak 是 16-bit bus，且有 prefetch
> 與 128 KiB 邊界規則，實際 totals 會與上表不同。實作以 §3.6.5 的 bus 成本逐項
> 加總（fetch＋資料存取＋internal），與上表的差異用硬體測試 ROM 校準，並記錄於
> `TODO.md` 的 Open Questions。

#### 3.6.4 指令週期（THUMB）

THUMB 沿用相同的 S／N／I 分類，換算如下：

| THUMB 指令群 | Cycles |
|---|---|
| data processing／MOV／CMP／ADD／SUB（立即數或暫存器） | 1S（以暫存器移位 +1I） |
| LDR／LDRH／LDRB | 1S+1N+1I（載入 PC：+1S+1N） |
| STR／STRH／STRB | 2N |
| PUSH（含 LR） | (n-1)S+2N |
| POP（含 PC） | nS+1N+1I |
| B | 2S+1N |
| BL（兩個 halfword） | 3S+1N |
| SWI | 2S+1N |
| 條件分支未成立 | 1S |

#### 3.6.5 記憶體存取成本

基礎 cycles（GBATEK「GBA Memory Map - Address Bus Width and CPU Read/Write Access Widths」）：

| 區域 | 讀（8/16/32） | 寫（8/16/32） | 備註 |
|---|---|---|---|
| BIOS | 1/1/1 | 唯讀 | |
| IWRAM（32 KiB） | 1/1/1 | 1/1/1 | |
| I/O | 1/1/1 | 1/1/1 | |
| OAM | 1/1/1 | 1/1/1 | 8-bit 寫入被忽略 |
| EWRAM（256 KiB） | 3/3/6 | 3/3/6 | 16-bit bus |
| Palette RAM | 1/1/2 | 1/1/2 | |
| VRAM | 1/1/2 | 1/1/2 | |
| Game Pak ROM | 5/5/8 | 唯讀 | WAITCNT 預設值；可由 WAITCNT 調整 |
| Game Pak SRAM | 5 | 5 | 只支援 8-bit |

規則：

1. 表列值 = 1 + wait states；ROM／SRAM 的 N／S wait 由 WAITCNT 決定（見下）。
2. GamePak 是 16-bit bus：32-bit 存取拆成兩次 16-bit，第二次必為 S。
3. 每個 128 KiB ROM 區塊邊界的第一個存取強制 N（即使位址連續）。
4. PPU 同時存取 video memory（VRAM／Palette／OAM）時 +1 cycle（Phase 4 實作）。
5. SRAM 只能 8-bit 存取（DMA 亦不可存取 SRAM）。

WAITCNT（`0x04000204`）欄位：

| Bits | 意義 | 值 |
|---|---|---|
| 0-1 | SRAM wait | 0..3 = 4／3／2／8 cycles |
| 2-3 | WS0 first access（N） | 0..3 = 4／3／2／8 cycles |
| 4 | WS0 second access（S） | 0..1 = 2／1 cycles |
| 5-6 | WS1 first access（N） | 0..3 = 4／3／2／8 cycles |
| 7 | WS1 second access（S） | 0..1 = 4／1 cycles |
| 8-9 | WS2 first access（N） | 0..3 = 4／3／2／8 cycles |
| 10 | WS2 second access（S） | 0..1 = 8／1 cycles |
| 14 | Game Pak prefetch buffer | 0=停用、1=啟用 |

- 預設 WAITCNT = `0000h`；零售卡常見 `4317h`（prefetch 啟用）。
- Phase 2 的 prefetch 簡化模型：啟用時 ROM 的 sequential fetch 成本視為 1 cycle；完整 prefetch buffer 行為於 Phase 4。

#### 3.6.6 PPU 事件與 DISPSTAT

每一條 scanline（`line` 0..227）內的 cycle 位置：

| 事件 | Cycle | 說明 |
|---|---|---|
| scanline 開始 | `line * 1232` | VCOUNT = line；VCount match 於此線起算 |
| 繪製 | `line*1232` .. `+960` | 240 dots × 4 cycles |
| HBlank 開始 | `line*1232 + 1006` | DISPSTAT bit1 變 1（繪製 960 cycles 後 flag 仍為 0 直到 1006） |
| scanline 結束 | `(line+1) * 1232` | HBlank 結束 |
| VBlank 開始 | `160 * 1232 = 197,120` | DISPSTAT bit0=1、`VBLANK_START`、VBlank IRQ |
| VBlank 結束／frame 邊界 | `228 * 1232 = 280,896` | `VBLANK_END`＋`FRAME_BOUNDARY`、VCOUNT 回 0、frame_index +1 |

DISPSTAT（`0x04000004`）欄位：

| Bits | 意義 | 方向 |
|---|---|---|
| 0 | VBlank flag（160..226 為 1，227 為 0） | 唯讀 |
| 1 | HBlank flag（每條線切換，0..227） | 唯讀 |
| 2 | VCount match（VCOUNT == LYC） | 唯讀 |
| 3 | VBlank IRQ enable | R/W |
| 4 | HBlank IRQ enable | R/W |
| 5 | VCount IRQ enable | R/W |
| 8-15 | VCount setting（LYC，0..227） | R/W |

- 寫 DISPSTAT 只能改 bits 3-5 與 8-15；讀回 bits 0-2 是即時狀態。
- VCount match 在該線內維持為 1；IRQ 於該線開始時拉起（enable bit5）。
- HBlank IRQ 範圍：GBATEK 的 DISPSTAT 章節稱 hidden lines 也產生 HBlank 條件，LCD timing 章節則註明 VBlank 期間不產生 HBlank IRQ。本規格暫採「flag 每條線切換、IRQ 只在可見線 0-159 產生」，Phase 2 以硬體測試 ROM 驗證；若不符再更新本節並記錄於 `TODO.md`。

#### 3.6.7 IRQ 時序

- 中斷源在其事件 cycle 拉起 IF 對應位；IF 為 latch，寫入 1 清除。
- CPU 在每條指令結束後檢查（與規格 8 的確定性一致）：`IME=1`、`IE & IF ≠ 0`、`CPSR.I=0`。
- IRQ 進場：SPSR←CPSR、mode=IRQ、LR=下一條指令+4、PC=`0x18`、I=1、T=0；成本 2S+1N。
- 本規格要求 **2-cycle pipeline 延遲**（中斷線可用後兩個 cycle 才進場）；Phase 3 實作並以測試驗證。
- SWI／UND 同為例外進場，成本 2S+1N；LR 依 ARM／THUMB 為 +4／+2。

#### 3.6.8 DMA 與 timer（Phase 3）

DMA：

- 寫入 enable bit 後 **2 cycles** 才開始傳輸。
- 每次 transfer：read `1N+(n-1)S`、write `1N+(n-1)S`，各自套用來源／目的區的 wait state 與 bus 寬度。
- HBlank 觸發點 = HBlank 開始 cycle；VBlank 觸發點 = 197,120；不得在 frame 結束時補算。
- OAM／OBJ VRAM 的 HBlank DMA 只能在 HBlank 內執行。

Timer：

- prescaler：F/1、F/64、F/256、F/1024；cascade 模式忽略 prescaler，前一級溢位即遞增。
- 16-bit counter，溢位時 reload 並拉起 IRQ（enable bit6）；溢位 cycle 必須可被測試斷言。

#### 3.6.9 TimingMode 的語意

| 模式 | CPU 週期 | Bus | PPU | 用途 |
|---|---|---|---|---|
| FUNCTIONAL | §3.6.3／3.6.4 指令表 | 每次存取固定 1 cycle（忽略 wait state 與 prefetch） | 事件照 §3.6.6，可關閉 rendering | RL 訓練 |
| TIMED | 同上 | 完整 §3.6.5（WAITCNT、128 KiB、prefetch 簡化） | 完整 §3.6.6 | 相容性測試 |
| TRACE | TIMED | TIMED | TIMED＋事件流 | 差異除錯 |

三種模式共用同一 API；上層不得依賴某一模式的內部時序實作（規格 3.1 結尾）。

#### 3.6.10 分階段實作與驗收

| Phase | 範圍 | 驗收條件 |
|---|---|---|
| Phase 1（已完成） | 指令語意；週期暫用「每指令 1 cycle」 | opcode 單元測試＋legacy 差動 |
| Phase 2 | §3.6.1–3.6.6；FUNCTIONAL／TIMED 切換 | 每個指令類別的 cycle 單元測試；各記憶體區存取成本測試；`step_frame()` 停在下一個 frame 邊界（280,896 的倍數；指令粒度，回報 cycles 最多超出單條指令成本）；VCOUNT 0..227、VBlank flag 160..226；事件 cycle 精確（HBLANK=`line*1232+1006`、VBLANK_START=197,120、FRAME_BOUNDARY=280,896）；DISPSTAT 即時反映 PPU 位置 |
| Phase 3 | §3.6.7–3.6.8 | IRQ 2-cycle 延遲、DMA transfer 成本、timer 溢位 cycle 的單元測試 |
| Phase 4 | video memory contention、完整 prefetch、音訊時序 | 對照硬體測試 ROM |

Phase 1 的「每指令 1 cycle」是暫行近似；Phase 2 必須換成 §3.6.3／3.6.4 的表。任何 cycle 數字只能出現在 `timing.py`／`video/ppu.py` 的常數與本節。

## 4. 建議的 Python 套件結構

```text
專案根目錄（= gbaemu 套件根；沒有內層 gbaemu/）
  __init__.py
  api_types.py         # 第 5 章全部公共型別（唯一權威定義）
  emulator.py          # 對外高階控制器
  config.py            # EmulatorConfig 驗證邏輯（型別定義在 api_types.py）
  timing.py            # clock、event queue、frame boundary
  cpu/
    arm7tdmi.py
    arm_decode.py
    arm_execute.py
    thumb_decode.py
    registers.py       # Arm7CoreState（內部）
  bus/
    address_bus.py
    regions.py
    access.py
  memory/
    wram.py
    vram.py
    palette.py
    oam.py
    cartridge.py
  video/
    ppu.py             # PpuState（內部）
    framebuffer.py
    render_modes.py
  audio/
    sound.py
    fifo.py
  devices/
    dma.py             # DmaChannelState（內部）
    timers.py          # TimerState（內部）
    interrupts.py      # InterruptState（內部）
    keypad.py          # KeypadState（內部）
  debug/
    breakpoints.py
    trace.py
    watchpoints.py
  hle/
    postboot.py            # PostBootState 與 header copy
    swi_table.py           # SWI 0x00-0x2A dispatch
    bios_read_protect.py   # BIOS 讀取保護近似
  rl/
    env.py
    spaces.py
    wrappers.py
  state/
    snapshot.py        # SnapshotHeader 版面配置與驗證
  errors.py            # 全部例外類別
```

專案根目錄本身就是 `gbaemu` 套件（沒有內層 `gbaemu/`），因此 `import gbaemu`
需要把專案根目錄的**上一層**放進 `sys.path`，`python -m gbaemu` 也要從上一層
啟動。`tests/`、`docs/`、`test-rom/`、`docs/gbatek-gba-specs/` 等開發資產與套件共用
同一目錄，但不屬於公開 API；`tests/gbaemu/` 的測試以 `gbaemu.tests.gbaemu.*`
匯入，`tests/conftest.py` 讓舊 `pygba` 與 `tests/reference/gba_cpu` 匯入並存。

發布成 wheel 時，`pyproject.toml` 以 `package-dir = { gbaemu = "." }` 把專案根
映射成 `site-packages/gbaemu/`，只打包程式碼；ROM／BIOS／測試／文件留在開發樹。
`main.py` 是使用者工作目錄的主程式（`from gbaemu import GbaApp`），不屬於套件
必要內容；安裝與 import 優先序詳見 `docs/guides/PACKAGING.md`。

`Emulator` 不應直接暴露所有內部物件的可變引用。需要觀測時，回傳不可變 view、複製的 scalar，或明確標示為低階 unsafe view。這能避免 RL wrapper 在不知情下改寫模擬器狀態。

## 5. 公共資料結構（struct 定義）

本章是所有對外資料型別的唯一權威定義，集中於 `api_types.py`。其他章節引用這裡的名稱。公共型別一律 `@dataclass(frozen=True, slots=True)`；注意 `frozen=True` 不會令內含的 `list`/`dict` 不可變，所以欄位使用 `tuple`、`bytes` 等真正不可變容器。內部可變狀態 struct（`Arm7CoreState`、`PpuState` 等）見第 3 章各節，不在此重複定義。

### 5.1 列舉（Enum）

```python
from enum import Enum

class TimingMode(Enum):
    FUNCTIONAL = "functional"   # instruction/block 為單位，週期近似
    TIMED = "timed"            # 依 bus、DMA、PPU、timer 事件計算 cycle
    TRACE = "trace"             # timed + 可重播事件流（差異測試用）

class VideoMode(Enum):
    OFF = "off"                # 不產生 framebuffer，RL 高速模式
    FRAMEBUFFER = "framebuffer"  # 產生 240x160 framebuffer

class AudioMode(Enum):
    DISABLED = "disabled"
    BUFFERED = "buffered"

class BootMode(Enum):
    HLE_ADVANCED = "hle_advanced"    # 進階 HLE：預設，完整 SWI 功能表（見 2.1）
    TEST_ROM_ONLY = "test_rom_only"  # 最小驗證路徑，不進 BIOS 流程
    REQUIRE_BIOS = "require_bios"    # legacy／optional differential；production 不使用

class SaveType(Enum):
    NONE = "none"
    SRAM = "sram"             # 32 KiB（最大 64 KiB）
    FLASH_64K = "flash_64k"    # 64 KiB SST/Macronix
    FLASH_128K = "flash_128k"  # 128 KiB
    EEPROM_512B = "eeprom_512b"
    EEPROM_8K = "eeprom_8k"
    DETECT = "detect"          # 由 cartridge 模組自動偵測

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
```

### 5.2 EmulatorConfig

```python
from dataclasses import dataclass, field
from pathlib import Path

@dataclass(frozen=True, slots=True)
class EmulatorConfig:
    bios_path: Path | None = None
    boot_mode: BootMode = BootMode.HLE_ADVANCED
    timing: TimingMode = TimingMode.FUNCTIONAL
    video: VideoMode = VideoMode.FRAMEBUFFER
    audio: AudioMode = AudioMode.DISABLED
    deterministic: bool = True   # 預設開啟；False 僅供實驗
    seed: int = 0
    hle_strict: bool = True     # True：未支援 SWI raise；False：記錄事件後 no-op（見 2.1.2）

    def validate(self) -> None:
        """在 Emulator 建構時呼叫；違反契約 raise InvalidConfigError。"""
        if self.boot_mode is BootMode.REQUIRE_BIOS and self.bios_path is None:
            raise InvalidConfigError("REQUIRE_BIOS 需要 bios_path")
        if self.bios_path is not None and self.boot_mode is BootMode.HLE_ADVANCED:
            # 允許同時提供（供等價測試），但必須明確理解 HLE 不會使用它執行啟動流程。
            pass
```

契約說明：

- `deterministic` 是橫跨所有 `TimingMode` 的保證，不是 timing 的其中一個值。任何模式下 `deterministic=True` 都必須滿足第 8 章的可重現要求。
- `hle_strict` 只影響未支援 SWI 的處理（見 2.1.2）：嚴格模式 raise `HleUnsupportedSwiError`，寬鬆模式記錄事件後 no-op。
- `seed` 只影響模擬器自身有隨機成分的部分（例如測試用 RNG 注入），不得影響硬體行為。
- `EmulatorConfig` 參與 snapshot 的 config hash（見 5.7）：`boot_mode`（含 HLE vs 真實 BIOS）、`hle_strict`、`timing`、`video`、`audio` 的變化會令 snapshot 拒絕載入，避免同一 snapshot 在不同設定下還原出不同結果（HLE 啟動與真實 BIOS 啟動的 snapshot 互不相容）。

### 5.3 StepResult 與 FrameResult

```python
@dataclass(frozen=True, slots=True)
class StepResult:
    cycles_executed: int                # 實際執行的 cycle 數（<= 請求值）
    cycles_remaining: int               # 因 halt/breakpoint 提前停止而未執行的部分
    halted: bool                        # CPU 進入 HALT（等待中斷）
    breakpoint_hit: int | None           # 觸發的 breakpoint id，無則 None
    events: tuple["EmulatorEvent", ...] # 本次執行期間發生的對外事件

@dataclass(frozen=True, slots=True)
class FrameResult:
    frame_index: int
    cycles: int                         # 本 frame 消耗的 cycle 數
    vblank_started: bool
    irq_pending: int                    # 執行結束時 IF 內未處理位元
    halted: bool
    events: tuple["EmulatorEvent", ...]
```

行為契約：

- `step_cycles(n)`：執行至多 `n` 個 cycle。遇到 HALT 或 breakpoint 可提前停止，並以 `cycles_executed`/`cycles_remaining` 回報實際執行量；不得超出 `n`。
- `step_frame()`：推進至下一個 frame boundary（`VBLANK_END`／scanline 0）。若呼叫時 PPU 已在 frame 中段，仍以「下一個 boundary」為終點，不是目前的 frame 結尾。
- `run_frames(count)`：等價於連續呼叫 `count` 次 `step_frame()`。實作可提供 `collect_results: bool = False` 參數，`False` 時回傳空 list 以降低 rollout 負擔（此為允許的最佳化，不得改變事件順序）。
- `run_until(event_kind, *, max_cycles)`：推進至下一個指定事件或 cycle 上限，回傳 `StepResult`。`max_cycles` 必填，防止無限迴圈。

### 5.4 EmulatorEvent

```python
@dataclass(frozen=True, slots=True)
class EmulatorEvent:
    kind: EventKind
    cycle: int                     # 事件發生時的總 cycle 數
    frame_index: int
    scanline: int | None           # PPU 相關事件必填，其他為 None
    channel: int | None            # DMA/timer 事件：通道編號
    address: int | None            # breakpoint/watchpoint/save 事件：觸發位址
    value: int | None              # write 類事件：寫入值
```

契約說明：

- `EventStream.poll()` 回傳自上次 poll 以來的事件 tuple，依 `cycle` **非遞減**排序；同一 cycle 的多個事件保留 emit（插入）順序，poll 會清空已回報事件。
- `EmulatorEvent` 只描述對外可觀測事件。內部排程器事件（見 5.6 `ScheduledEvent`）不會出現在 `poll()` 結果。

### 5.5 唯讀觀測型別（Views）

```python
@dataclass(frozen=True, slots=True)
class CPUState:
    """對外唯讀 CPU 快照。regs 為 r0-r15，r15 為架構上可理解的 PC。"""
    regs: tuple[int, ...]      # 長度 16
    cpsr: int
    spsr: int
    thumb: bool
    mode: int                  # CPSR mode 位（0x10-0x1F）
    halted: bool
    cycles: int                # 總執行 cycle 數

@dataclass(frozen=True, slots=True)
class MemoryRegionInfo:
    kind: MemoryRegionKind
    base: int
    size: int
    read_only: bool
```

對應的 view 介面（方法簽名見第 6 章）：

- `CPUView.state()` 回傳 `CPUState`；`read_register()` 只接受 `"r0"`…`"r15"`、`"cpsr"`、`"spsr"`，非法名稱 raise `ValueError`。
- `MemoryView` 的讀取是**無副作用的 debugger peek**：不觸發硬體 bus 行為、不消耗 cycle、不影響 open bus 值；除錯寫入必須走明確的 `force_write()` 並記錄 trace event。
- `VideoView.read_frame()` 回傳 `bytes`，長度固定 `240 * 160 * 3`（RGB888，row-major，scanline 0 在前）。`VideoView.read_frame_array()`（需要 numpy，定義在 `gbaemu.rl`）回傳 `numpy.ndarray`，shape `(160, 240, 3)`、dtype `uint8`。兩者讀取同一份 framebuffer。
- `video_mode=OFF` 時 framebuffer 不再更新，`read_frame()` 回傳最後一次 render 的內容或全零 buffer；RL 的 pixel observation 依賴 `gbaemu.rl` 內部強制 render（見 7.1），不得依賴 OFF 模式的 framebuffer。

### 5.6 內部排程器型別

```python
# timing.py — 內部使用，不對外暴露
@dataclass(frozen=True, slots=True)
class ScheduledEvent:
    cycle: int      # 觸發的絕對 cycle 數
    sequence: int    # 同 cycle 的穩定排序用序號
    action: str     # 內部事件識別碼（由 scheduler 解析）

    def __lt__(self, other: "ScheduledEvent") -> bool:
        return (self.cycle, self.sequence) < (other.cycle, other.sequence)
```

同 cycle 的事件以 `sequence`（插入順序）打破平手，保證排序穩定且可重現。scheduler 只允許 `cycle` 嚴格遞增的時間推進。

### 5.7 Snapshot 二進位格式

`save_state()` 回傳的 `bytes` 必須是自訂二進位格式，禁止 `pickle`。格式以 Python 標準庫 `struct.Struct` 描述，全部小端序：

```python
import struct

SNAPSHOT_MAGIC = b"GEMU"
SNAPSHOT_FORMAT_VERSION = 1

# <4s I 3H 32s 32s Q I  ->  magic, version, emu_ver[3], rom_sha256,
#                            config_sha256, payload_len, payload_crc32
SNAPSHOT_HEADER: struct.Struct = struct.Struct("<4sI3H32s32sQI")
```

版面配置（offset 由 `SNAPSHOT_HEADER.offset` 提供，欄位順序即計算順序）：

| 欄位 | 類型 | 大小 | 說明 |
|---|---|---|---|
| magic | `4s` | 4 | `b"GEMU"` |
| format_version | `I` | 4 | 本文件定義為 1 |
| emulator_version | `3H` | 6 | major/minor/patch |
| rom_sha256 | `32s` | 32 | ROM 內容 SHA-256 |
| config_sha256 | `32s` | 32 | `EmulatorConfig` 標準序列化後的 SHA-256 |
| payload_length | `Q` | 8 | payload 位元組數 |
| payload_crc32 | `I` | 4 | payload 的 CRC-32 |
| payload | bytes | 變動 | 各子系統快照串接 |

payload 內容（`SnapshotState`，各子系統依次序列化，每段前綴 `4s` 區段識別碼與 `Q` 長度）：

```python
# 概念上等同（實際以 struct.Struct 逐段編碼）：
# ("CPU\0", Arm7CoreState)      — regs、cpsr、banked、pipeline、halted
# ("BUS\0", all regions)       — EWRAM、IWRAM、VRAM、Palette、OAM、SRAM
# ("PPU\0", PpuState)
# ("DMA\0", DmaChannelState x4)
# ("TMR\0", TimerState x4)
# ("IRQ\0", InterruptState)
# ("KEY\0", KeypadState)
# ("CRT\0", Cartridge.snapshot())  — 含 save memory 與控制器狀態
# ("SCH\0", scheduler + counters) — 事件佇列、cycle counter、frame counter、input latch
```

載入規則（`load_state(data: bytes)`）：

1. 長度不足 header → raise `SnapshotCorruptError`。
2. `magic` 不符 → `SnapshotCorruptError`。
3. `payload_crc32` 不符 → `SnapshotCorruptError`。
4. `format_version` 不等於支援版本 → `SnapshotVersionError`（只保證偵測，不保證跨版本還原）。
5. `rom_sha256` 不符 → `SnapshotRomMismatchError`。
6. `config_sha256` 不符 → `SnapshotConfigMismatchError`。

**重要：** `load_state()` 還原的 cartridge save memory 只存在於記憶體內，**不得**自動寫回磁碟 `.sav` 檔。磁碟持久化由獨立的 `emu.cartridge_flush_to_disk()` API 明確觸發（以暫存檔 + rename 原子寫入）。

### 5.8 RL 層型別

```python
from typing import ClassVar, Literal

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
    resize: tuple[int, int] | None = (84, 84)   # (height, width)
    memory_ranges: tuple[MemoryRange, ...] = ()

@dataclass(frozen=True, slots=True)
class ActionSpec:
    mode: Literal["buttons", "discrete", "multi_binary"]
    # multi_binary / buttons 的固定 bit 順序（bit 0 = A）：
    button_order: ClassVar[tuple[Button, ...]] = (
        Button.A, Button.B, Button.SELECT, Button.START,
        Button.RIGHT, Button.LEFT, Button.UP, Button.DOWN,
        Button.R, Button.L,
    )
    # discrete 模式：每個動作對應一組按鍵（互斥）。
    discrete_sets: tuple[tuple[Button, ...], ...] = ()

@dataclass(frozen=True, slots=True)
class GBAEnvConfig:
    observation: ObservationConfig = ObservationConfig()
    action: ActionSpec = ActionSpec(mode="multi_binary")
    frame_skip: int = 4
    max_episode_steps: int = 10_000
```

### 5.9 錯誤類別

```python
# errors.py
class GbaEmuError(Exception): ...
class InvalidConfigError(GbaEmuError): ...
class RomInvalidError(GbaEmuError): ...          # 太小、header 無效
class BiosMissingError(GbaEmuError): ...
class BiosChecksumError(GbaEmuError): ...
class UnsupportedSaveTypeError(GbaEmuError): ...
class HleUnsupportedSwiError(GbaEmuError): ...   # SWI 0x1A-0x2A 未文件化 / 0x2B+ 無效（見 2.1.2）
class ReadOnlyMemoryError(GbaEmuError): ...
class BreakpointError(GbaEmuError): ...
class SnapshotError(GbaEmuError): ...
class SnapshotCorruptError(SnapshotError): ...
class SnapshotVersionError(SnapshotError): ...
class SnapshotRomMismatchError(SnapshotError): ...
class SnapshotConfigMismatchError(SnapshotError): ...
```

## 6. 對外 API 草案

以下 API 是新專案自行設計的契約。它只借鑑 PyBoy 所展示的「建立實例、推進模擬、讀取狀態、提交輸入」使用方式，不共用 PyBoy 的程式碼或內部名稱。所有回傳型別以第 5 章定義為準。

```python
from gbaemu import Emulator, EmulatorConfig

config = EmulatorConfig(
    bios_path=None,
    boot_mode=BootMode.HLE_ADVANCED,
    video=VideoMode.FRAMEBUFFER,
    audio=AudioMode.DISABLED,
    timing=TimingMode.FUNCTIONAL,
    seed=0,
)

emu = Emulator.from_rom("game.gba", config=config)

try:
    emu.reset()
    emu.input.set_buttons(a=True, start=False)

    result = emu.step_frame(render=False)
    frame = result.frame_index
    pixels = emu.video.read_frame(copy=True)      # bytes, 240*160*3
    ram_value = emu.memory.read_u8(0x02000000)
    cpu = emu.cpu.state()                          # CPUState
    events = emu.events.poll()
finally:
    emu.close()
```

### 6.1 模擬生命週期

```python
class Emulator:
    @classmethod
    def from_rom(
        cls, rom_path: str | Path, *, config: EmulatorConfig | None = None
    ) -> "Emulator": ...

    def reset(self, *, seed: int | None = None) -> None: ...
    def step_cycles(self, cycles: int) -> StepResult: ...
    def step_frame(self, *, render: bool = True) -> FrameResult: ...
    def run_frames(
        self, count: int, *, render: bool = False, collect_results: bool = False
    ) -> list[FrameResult]: ...
    def run_until(self, event: EventKind, *, max_cycles: int) -> StepResult: ...
    def pause(self) -> None: ...
    def close(self) -> None: ...

    def save_state(self) -> bytes: ...
    def load_state(self, data: bytes) -> None: ...
    def cartridge_flush_to_disk(self) -> None: ...
```

`step_frame()` 是 RL 和一般腳本的主要單位，但不能假設每一個遊戲邏輯事件都只在 frame 邊界發生。除錯和相容性測試使用 `step_cycles()` 或更低階的 `run_until()`。

### 6.2 記憶體與暫存器觀測

```python
class MemoryView:
    def read_u8(self, address: int) -> int: ...
    def read_u16(self, address: int) -> int: ...
    def read_u32(self, address: int) -> int: ...
    def read(self, address: int, size: int) -> bytes: ...
    def write_u8(self, address: int, value: int) -> None: ...
    def write_u16(self, address: int, value: int) -> None: ...
    def write_u32(self, address: int, value: int) -> None: ...
    def read_region(self, name: MemoryRegionKind) -> bytes: ...
    def region_info(self, name: MemoryRegionKind) -> MemoryRegionInfo: ...
    def force_write(self, address: int, value: int) -> None: ...  # 除錯用
```

契約說明：

- 所有 `read_*`／`write_*` 是 debugger peek：無硬體副作用、不消耗 cycle（`force_write` 除外，它會記錄 trace event）。
- 預設禁止透過 `write_*`／`force_write` 修改 ROM、BIOS 或硬體唯讀欄位（raise `ReadOnlyMemoryError`）；`force_write` 僅用於測試，並記錄 `WATCHPOINT_WRITE` 類 trace event 以區分正常執行。
- `read_region()` 回傳 `bytes`（複本），不回傳可寫 `memoryview`，避免外部在不經同意下改寫模擬器狀態。

```python
class CPUView:
    def state(self) -> CPUState: ...
    def read_register(self, name: str) -> int: ...
    def set_breakpoint(self, address: int, *, thumb: bool | None = None) -> int: ...
    def clear_breakpoint(self, breakpoint_id: int) -> None: ...
```

### 6.3 輸入、畫面與事件

```python
class InputPort:
    def set_buttons(self, **buttons: bool) -> None: ...
    def press(self, *buttons: Button) -> None: ...
    def release(self, *buttons: Button) -> None: ...
    def clear(self) -> None: ...

class VideoView:
    width: int = 240
    height: int = 160
    def read_frame(self, *, copy: bool = True) -> bytes: ...
    def read_scanline(self, line: int) -> bytes: ...   # 240*3 bytes
    def read_frame_array(self) -> "numpy.ndarray": ... # (160,240,3) uint8

class EventStream:
    def poll(self) -> tuple[EmulatorEvent, ...]: ...
```

按鍵集合固定為 `Button` enum 的十個值。`set_buttons` 只接受合法按鍵名，未知按鍵 raise `ValueError`。輸入在下一個硬體取樣點生效，不能由 Python 呼叫時間直接改寫當前指令的中間狀態。

## 7. RL 環境設計

RL 層不要把原始 `Emulator` 直接當成 Gymnasium environment。應使用一個明確的 wrapper（`gbaemu.rl.GBAEnv`），將 action、observation、reward、termination 和 truncation 分離。

```python
from gbaemu.rl import GBAEnv, GBAEnvConfig, ObservationConfig, ActionSpec

env = GBAEnv(
    rom="game.gba",
    config=GBAEnvConfig(
        observation=ObservationConfig(
            source="screen",
            grayscale=True,
            resize=(84, 84),
            memory_ranges=(),
        ),
        action=ActionSpec(mode="multi_binary"),
        frame_skip=4,
    ),
)

obs, info = env.reset(seed=0)
obs, reward, terminated, truncated, info = env.step(action)
```

### 7.1 Action space 與 frame skip 語意

三種模式的語意：

- `buttons`：semantic API，`step()` 接受 `dict[Button, bool]` 或 `**kwargs`，等價於完整替換當前按鍵狀態。
- `multi_binary`：固定順序的 10-bit vector（`ActionSpec.button_order`，bit 0 = A），對應 Gymnasium `MultiBinary(10)`。
- `discrete`：互斥動作集合（`discrete_sets`），對應 `Discrete(n)`。

關鍵契約：

1. **每個 action 是完整替換**（full replacement），不是增量修改：`step()` 收到的按鍵狀態會完全取代上一步的狀態。
2. **`frame_skip=4` 的精確語意：** 一個 `env.step(action)` 執行 4 個 GBA frame，期間按鍵狀態不變；observation 取自第 4 個 frame 結束時的畫面（只回傳最後一個 frame，中間 frame 不收集）；`info` 可選提供 `frames_rendered` 診斷欄位。
3. `frame_skip` 只控制模擬推進次數，不改變按鍵語意（即永遠是「同一組按鍵保持 4 個 frame」）。
4. pixel observation 依賴的 frame 必須有產生：`gbaemu.rl` 內部在 `source` 含 `screen` 時強制 render，不受 `EmulatorConfig.video=OFF` 影響（env 建立時覆寫為 framebuffer 模式）。

### 7.2 Observation space

可觀測資料分成三層：

1. **Pixel observation：** 240×160 RGB888 → 經 `ObservationConfig` 處理（灰階、resize）後輸出。`resize` 後 shape 為 `(resize[0], resize[1])`（灰階）或 `(h, w, 3)`（彩色），dtype `uint8`。
2. **RAM observation：** 只讀取 `memory_ranges` 白名單內的位址，輸出 `uint8` 1-D array（各 range 依宣告順序串接）。不得預設把整個記憶體暴露給 agent。
3. **Diagnostic observation：** `info` dict 內提供 `vcount`、`irq_pending`、`buttons`、`halted`、`frame_index`，僅研究模式開啟。

RAM 觀測必須以設定檔（`MemoryRange` tuple）保存位址與 endian。不要把根據特定遊戲逆向出的位址直接硬編碼在通用模擬器；那些內容應放在獨立的 game adapter。

### 7.3 Reward、termination 與 truncation

- 通用 `GBAEnv` **預設 reward 恆為 0**：模擬器不內建任何 game-specific reward。game-specific reward 由外部 wrapper 或 game adapter 提供（例如讀取特定 RAM 位址）。
- `terminated` 預設恆為 `False`（GBA 沒有通用「遊戲結束」訊號）；`truncated` 由 `max_episode_steps` 觸發，符合 Gymnasium 慣例。

### 7.4 Snapshot 與平行 rollout

每個 environment 的 `save_state()` 必須保存（見 5.7 payload 內容）：

- CPU register、CPSR、banked registers。
- 所有 RAM、VRAM、Palette RAM、OAM。
- PPU scanline/state、DMA、timer、interrupt latch。
- cartridge save memory 與其控制器 state。
- event queue、frame/cycle counter、input latch。

`save_state()` 的二進位格式（5.7）有 magic bytes、版本號、ROM SHA-256、config SHA-256 和 CRC-32 checksum。RL 大量分支時需要可驗證、可移植、可快速複製的二進位格式。

平行執行優先採多個獨立 process，而不是共用一個 emulator instance。每個 instance 使用獨立 ROM file descriptor、seed 和 snapshot buffer。只有在 profiler 證明必要時，才考慮 C extension 或 shared-memory framebuffer。

## 8. 時序與確定性契約

模擬時間必須是整數 cycle。禁止使用 `time.sleep()`、wall clock 或背景 thread 推進硬體。所有輸入、DMA、timer、PPU 和 IRQ 事件都由同一個 scheduler 決定先後。

三種 `TimingMode`（`functional`／`timed`／`trace`，見 5.1）控制**精確度**；`deterministic=True` 控制**可重現性**，兩者正交。任何模式搭配 `deterministic=True` 時，以下資料必須可雜湊比較：CPU state、選定記憶體區段、framebuffer、pending IRQ、event queue 和 cycle counter。浮點運算只允許出現在音訊或 host-side rendering，不能影響 CPU、PPU 或輸入決策。

確定性驗收測試：固定 seed 跑 N frames，對比 state hash、frame hash、event trace 和 cycle count，任何差異即為失敗。

## 9. 逆向工程與實作流程

### Phase 0：規格索引與可測試骨架

建立 GBATEK 對照索引，包含 memory map、I/O map、ARM CPU、LCD、DMA、timer、interrupt、keypad 和 cartridge。每個模組先寫介面與最小測試，不先追求完整遊戲相容性。

完成：ROM 載入、address bus、WRAM、CPU reset、基本 logger、可重現 seed、**進階 HLE 啟動路徑（PostBootState、header copy、SWI dispatch table 骨架）**和 CLI `inspect-rom`。

**驗收條件：** `api_types.py` 全部型別可 import 且通過 `pytest` 型別煙霧測試；`Emulator.from_rom()` 可載入測試 ROM 並完成 reset；HLE 啟動後 `CPUState` 符合 2.1.1 的 PostBootState（SP、mode、PC、header copy）；`inspect-rom --json` 輸出正確 header 欄位；SWI 0x2B–0xFF 觸發 `HleUnsupportedSwiError` 有測試。

### Phase 1：CPU 與基本記憶體

先完成 ARM/THUMB 解碼、暫存器、條件旗標、load/store、branch、IRQ 基礎，並讓測試程式可進入主迴圈。建立每條指令的 reference test 和 cycle test。

**驗收條件：** 自建 opcode 單元測試全數通過；`step_cycles()` 回傳正確的 `StepResult` 欄位；確定性測試（同 seed 重跑 hash 一致）通過。

### Phase 2：I/O、PPU 與 frame boundary

完成 I/O register read/write、Mode 3、KEYINPUT、VBlank/HBlank、VCOUNT、基本 IRQ。此階段開始支援 `step_frame()` 和 framebuffer API。

**驗收條件：** Mode 3 測試 ROM 產生正確 framebuffer；`VideoView.read_frame()` 回傳 240×160×3 bytes；`EmulatorEvent` 序列按 cycle 排序；VRAM 8-bit 寫入規則（BG 複製／OBJ 忽略）有單元測試。

### Phase 3：DMA、timer、save memory

完成 DMA0–3、四個 timer、timer IRQ、SRAM/Flash/EEPROM adapter 和 state snapshot。此階段才能可靠支援大量測試 ROM 與早期 RL wrapper。

**驗收條件：** snapshot save/load 後 state hash 一致；`SnapshotVersionError`／`SnapshotRomMismatchError` 觸發路徑有測試；DMA 不存取 SRAM 的規則有測試；`cartridge_flush_to_disk()` 原子寫入有測試。

### Phase 4：音訊與完整顯示功能

補足 Mode 0/1/2、sprites、affine、blending、sound FIFO、取樣輸出和較完整 wait state。GUI 與音訊播放都是外部 consumer，不得反向決定核心時間。

**驗收條件：** 各 PPU mode 依 GBATEK 的 BG/OBJ 分界存取 VRAM；音訊 `BUFFERED` 模式可取出 PCM buffer 且不阻塞核心。

### Phase 5：相容性、效能與 RL scale-out

加入差異測試、trace replay、process pool、no-render benchmark、observation pipeline、frame skip 和 snapshot branching。以 profiler 驗證瓶頸，再決定 Cython 或 C extension 的範圍。

**驗收條件：** `GBAEnv` 通過 Gymnasium `check_env`；`frame_skip` 語意測試（4 frame、按鍵不變、obs 為最後 frame）通過；多 process rollout 確定性測試通過；benchmark 報告包含「模擬 GBA frame / host second」。

## 10. 測試策略

測試分為五層：

1. **純函式測試：** opcode decode、flags、address masking、色彩轉換、FIFO 和 save-controller 狀態機。
2. **裝置測試：** timer overflow、DMA copy、IRQ acknowledge、KEYCNT 條件、PPU register side effects。
3. **整合測試：** CPU 寫入 I/O 後觸發 PPU/DMA/timer，驗證事件排序。
4. **ROM smoke test：** 自建小型 ROM 或合法公開測試 ROM，驗證 boot、記憶體、畫面和輸入。
5. **回歸與確定性測試：** 固定 seed 跑 N frames，對比 state hash、frame hash、event trace 和 cycle count。

每次修正硬體行為時，應新增最小重現測試，而不是只更新一個大型遊戲的截圖。截圖差異只能顯示結果變了，不能說明 CPU、bus 或 PPU 的哪個規則錯誤。

## 11. 效能基準

至少建立以下 benchmark：

- CPU-only，關閉 PPU/audio。
- no-render，保留 PPU timing。
- render every frame。
- render every 4/15/60 frames。
- 單 instance 與多 process rollout。
- snapshot save/restore throughput。
- RAM-only、pixel-only、hybrid observation throughput。

報告應使用「模擬 GBA frame / host second」和「每個 environment step 的平均延遲」，而不是只報 wall-clock 總時間。RL 專用模式可以略過 framebuffer rasterization，但不可略過會影響遊戲邏輯的 PPU、DMA、timer 或 IRQ 事件。

## 12. CLI 與除錯工具

建議提供：

```text
gbaemu inspect-rom game.gba [--json]
gbaemu run game.gba --frames 600 --no-video
gbaemu trace game.gba --from 0x08000000 --cycles 10000
gbaemu dump-memory game.gba --address 0x02000000 --size 256
gbaemu replay game.gba --input inputs.jsonl --state-hash
```

CLI 不應與 GUI 綁定。所有命令都可在 headless CI 執行，並以 JSONL 或二進位 trace 輸出機器可讀結果；`--json` 輸出必須是穩定欄位順序的單一 JSON 物件，供 CI 解析。

## 13. 完成條件

第一個可用版本至少要滿足：

- 可載入一個 GBA ROM，完成 reset，並以 deterministic mode 執行。
- **進階 HLE 啟動可令標準測試 ROM 正確到達 entry point；SWI 功能表（0x00–0x2A）通過單元測試，其中 Div、CpuSet、LZ77／RL 解壓縮必須有逐 byte 驗證。**
- ARM 與 THUMB 基本指令通過自建單元測試。
- WRAM、VRAM、I/O、KEYINPUT、VBlank、DMA 和 timer 有可重現測試。
- `step_frame()`、記憶體 read/write、輸入、framebuffer read、save/load state API 可用。
- 關閉 rendering 和 audio 後可執行 headless benchmark。
- RL environment 能 reset、step、skip frames、回傳固定 shape observation。
- 專案不包含 PyBoy 原始碼、Nintendo BIOS、商業 ROM 或未授權素材。
- 文件與原始碼對硬體規格有 GBATEK 章節/URL 引用，並清楚區分實作事實與尚未完成的近似行為。

## 14. 建議的第一個實作切片

不要一開始實作完整 GBA。建議第一個 vertical slice 是：

1. `Emulator.from_rom()` 載入 ROM header。
2. 32-bit bus 映射 BIOS、WRAM、I/O、VRAM、ROM。
3. CPU reset 後支援足以執行簡單 THUMB loop 的指令。
4. KEYINPUT 回讀與外部按鍵 latch。
5. Mode 3 framebuffer。
6. VBlank event 與 `step_frame()`。
7. JSON state hash 和一個最小 `GBAEnv`。

這個切片能同時驗證 API、記憶體模型、時間模型、畫面觀測和 RL 介面。等它通過確定性與 snapshot 測試後，再擴展 DMA、timer、IRQ 和其他 PPU mode，能避免把錯誤同時埋在 CPU、bus 和 rendering 三層。

## References

[1]: https://problemkaputt.de/gbatek.htm "GBATEK: Game Boy Advance / Nintendo DS / DSi / 3DS Technical Info"

[2]: https://rust-console.github.io/gbatek-gbaonly/ "GBATEK GBA-only Markdown mirror"

[3]: https://docs.pyboy.dk/api/index.html "PyBoy API reference"

[4]: https://github.com/Baekalfen/PyBoy "PyBoy project repository and public API examples"
