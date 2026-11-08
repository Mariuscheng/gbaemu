# TODO

## 目前進度

- **Phase 0：規格索引與可測試骨架 — 實作完成**（驗收測試見下）。
- **Phase 1：CPU 與基本記憶體 — 核心完成**（ARM/THUMB 執行、banking、例外入口、
  `step_cycles()`／`StepResult`、breakpoint；legacy golden 向量與週期模型見
  「Phase 1 後續」）。
- **規格 0.5 — 時序模型已補進 `docs/` §3.6**（2026-10-31）：時鐘／frame 常數、
  S／N／I／C、ARM／THUMB 指令週期表、記憶體存取成本＋WAITCNT、PPU 事件 cycle、
  IRQ／DMA／timer 時序、TimingMode 語意與 Phase 2/3 驗收。Phase 2 的 cycle 數以
  該節為唯一權威。
- **Phase 2 timing 基礎 — 完成**（2026-10-31）：`timing.py` 常數與 frame helpers、
  `bus/access.py::access_cycles`（區塊成本＋WAITCNT＋128 KiB 邊界）、
  `cpu/cycles.py` 指令週期（S/N/I，自 legacy 移植）、`step_cycles()` 預算不超額、
  FUNCTIONAL／TIMED 切換。測試：`tests/gbaemu/test_timing.py`（10 個 case）。
- **Phase 2 I/O＋PPU — 完成**（2026-10-31）：`bus/io.py` 核心暫存器、KEYINPUT／
  KEYCNT IRQ；`video/ppu.py` scanline 事件與 Mode 3；`step_frame()`／`run_frames()`。
  測試：`test_io.py`、`test_ppu.py`、`test_frame.py`。
- **Phase 3 DMA＋Timers — 完成**（2026-10-31）：`devices/dma.py`、`devices/timers.py`；
  pytest 461 passed / 4 skipped（全部，2026-11-03）。
- **Rust core：`suite.gba` Memory tests 1552/1552 全 PASS**（2026-11-03；列表全綠）、
  **I/O read tests 130/130 全 PASS**（2026-11-03）、
  **Multiply long tests 72/72 全 PASS**（2026-11-03；ARM7TDMI Booth multiplier C flag）、
  **Shifter tests 140/140 全 PASS**（2026-11-03；data processing Rn=PC + register shift 讀 PC+12）、
  **DMA tests 1256/1256 全 PASS**（2026-11-03；ROM 區 source 強制遞增，見「Phase 3 DMA」）、
  **SIO register R/W tests 90/90 全 PASS**（2026-11-03；mGBA 模式遮罩＋未連線線路狀態）、
  **SIO timing tests 4/4 全 PASS**（2026-11-03；normal 8/32-bit 傳輸時間，Multi 逾時 SKIP）、
  **Timer count-up tests 177/468（legacy）／174/468（mgba）、Timer IRQ 44/90（legacy）／65/90（mgba）**（2026-11-03；IntrWait 喚醒即刻投遞 IRQ）、
  **Timing tests 794/2020（legacy）／1852/2020（`--mgba` accounting）**（2026-11-04；
  round 4 重寫 mGBA 式 active-region timing：store `++wait`、stall 可負、PC+8/+4、
  multiply WAIT 表、Thumb LDM/STM 方向、LDM/STM 逐 register 跨區；round 5
  Python reference 同步，`tools/mgba_cost_diff.py` 0 mismatch、Python 亦 1852；
  round 10–15 依次係 DMA startup delay、ROM→ROM internal overhead 4→0、Game Pak
  DMA ±1 rounding、BIOS HLE SWI profile（BIOS 數學 84/120）、CpuFastSet 搬運成本（CpuSet 20/20）；
  詳見 [docs/architecture/TIMING.md](docs/architecture/TIMING.md)），
  Carry 93/93、BIOS math 615/615；`cargo test` 100 passed；
  `rust_cpu_diff` 108/108、`rust_bus_diff` 51/51、`rust_frame_diff` 15/15、
  `rust_snapshot_diff` 11/11。本輪修正見「Phase 3 DMA」與 Open Questions 2／5／6
  （SRAM 8-bit 匯流排、DMA 遮罩、open-bus prefetch、biosPrefetch、Thumb NEG carry、
  I/O register read mask／open bus、DMA ROM 區 source 遞增、64-bit multiply flags、
  SIO／JOY 暫存器讀值、32-bit I/O store 拆成兩個 16-bit 寫入、IntrWait IRQ 投遞次序、
  CPU fetch cycle model（ROM prefetch／prefetch-disable bug））。
  Timer IRQ tests 仍然 0/90：需要 exact-cycle timer overflow IRQ dispatch（見 G4）。
- 新公開套件：`gbaemu`（CPython 3.11+；目前以專案 venv 的 Python 3.14 驗證）。
- **套件配置：專案根目錄本身就是 `gbaemu` 套件**（根目錄有 `__init__.py`，沒有內層
  `gbaemu/`）。`python -m gbaemu` 需從上一層（`D:\python`）執行；pytest 仍可在專案
  根目錄執行，`tests/conftest.py` 會把專案根加進 `sys.path` 讓 legacy `pygba`／`tests/reference/gba_cpu`
  的頂層匯入繼續可用。
- 舊 `pygba`／`tests/reference/gba_cpu` 保留為 Phase 1–3 的 reference／differential oracle；
  可獨立的 `savedata` 與 BIOS 數學 helper 已搬到 `gbaemu`，舊檔已刪除。
  其餘依 Phase 逐檔遷移，對照與刪除 gates 見下方「舊碼整併與刪除紀錄」。

## Phase 0 驗收對照

| 規格驗收條件 | 狀態 | 測試 |
|---|---|---|
| `api_types.py` 全部型別可 import 且通過 pytest 型別煙霧測試 | ✅ | `tests/gbaemu/test_api_types.py` |
| `Emulator.from_rom()` 可載入測試 ROM 並完成 reset | ✅ | `tests/gbaemu/test_emulator.py` |
| HLE 啟動後 `CPUState` 符合 2.1.1（SP、mode、PC、header copy） | ✅ | `tests/gbaemu/test_hle.py`、`tests/gbaemu/test_emulator.py` |
| `inspect-rom --json` 輸出正確 header 欄位 | ✅ | `tests/gbaemu/test_cli.py` |
| SWI 0x2B–0xFF 觸發 `HleUnsupportedSwiError` | ✅ | `tests/gbaemu/test_hle.py` |
| GBATEK 對照索引（memory map、I/O、ARM、LCD、DMA、timer、IRQ、keypad、cartridge） | ✅ | `docs/GBATEK_INDEX.md`、`tests/gbaemu/test_gbatek_index.py` |
| ROM 載入、address bus、WRAM、CPU reset、基本 logger、可重現 seed | ✅（seed 目前僅管線，見 Open Questions 13） | `tests/gbaemu/test_bus.py`、`tests/gbaemu/test_emulator.py`、`tests/gbaemu/test_log.py` |
| CLI `inspect-rom` | ✅ | `tests/gbaemu/test_cli.py`（`python -m gbaemu`） |

## Phase 0 驗證結果

以專案 venv（Python 3.14.2、pytest 9.2.0）執行：

```text
python -m pytest tests/gbaemu -q      -> 93 passed
python -m pytest tests -q             -> 278 passed, 4 skipped
python -m compileall -q <套件模組>     -> OK
cd ..; python -m gbaemu inspect-rom gbaemu\test-rom\ppu\hello.gba --json
                                      -> title="GBA Tests", checksum 0x69 OK
```

`4 skipped` 來自舊測試：1 個需 `PYGBA_IT_LONG=1` 的長整合測試，3 個缺少
haltcnt ROM；皆與 `gbaemu` 無關。

## Phase 1 驗收對照

| 規格驗收條件 | 狀態 | 測試／證據 |
|---|---|---|
| 自建 opcode 單元測試全數通過 | ✅ | `tests/gbaemu/test_cpu_arm.py`（10）、`test_cpu_thumb.py`（5）、`test_cpu_differential.py`（200 ARM＋200 THUMB 隨機差動，對照 legacy `gba_cpu`） |
| `step_cycles()` 回傳正確 `StepResult` 欄位 | ✅ | `tests/gbaemu/test_cpu_step.py`（8：欄位、breakpoint、halted、參數驗證、reset） |
| 確定性測試（同 ROM／config 重跑一致） | ✅ | `test_cpu_step.py::test_determinism_same_rom_and_config` |
| IRQ／SWI／UND 例外入口與 banked registers | ✅ | `tests/gbaemu/test_cpu_exceptions.py`（7）、`test_internal_types.py` |
| 公開測試 ROM 可執行 | ⚠️ 初步 | `armwrestler.gba`、`GBAUtilityTools.gba` 各執行 30 萬條指令、0 未定義指令；尚無 PPU 可驗證畫面結果 |

**Phase 1 驗證結果**（2026-10-31）：

```text
python -m pytest tests/gbaemu -q      -> 125 passed
python -m pytest tests -q             -> 310 passed, 4 skipped
```

Phase 1 實作內容：

- `cpu/arm.py`、`cpu/thumb.py`、`cpu/conditions.py`：自 `gba_cpu/` 遷移的
  ARM/THUMB 解碼與執行（含 LDM^ glitch 等實機語意）。
- `cpu/registers.py`：`Arm7CoreState` 擴充 `bank_mode`／`fiq_r8_12`／`usr_r8_12`；
  `RegisterFile` 提供 banking、SPSR、旗標與 PC 對齊（legacy 介面相容）。
- `cpu/arm7tdmi.py`：`step()`、`execute_one()`、`CpuBus`（未對齊旋轉在 CPU 層統一
  實作，Open Question 12 結案）、`enter_exception()`／`swi()`／`check_irq()`。
- `Emulator.step_cycles()`：breakpoint 命中回報 id、事件 poll、`StepResult`。

### Phase 1 後續（未完成）

- ✅ seeded 隨機差動：`tests/gbaemu/test_cpu_differential.py` 以 200 ARM + 200 THUMB
  向量對照 `gba_cpu.arm/thumb.execute`（seed 固定；legacy 套件移除時一併刪除）。
- 移植 legacy golden 向量（`test_core_arm` 26 個固定 opcode、`test_cpu_flags_ldm` 8 個、
  `test_cpu_banks` 2 個）——目前由 30 個自建 opcode 測試 + 隨機差動覆蓋，golden 未逐條搬。
- 週期模型：Phase 1 目前是「每指令 1 cycle」暫行近似；Phase 2 依規格 §3.6.3／
  3.6.4 換成 S/N/I 指令表，並接上 §3.6.5 的 bus wait state。

## 舊碼整併與刪除紀錄

### 已完成（Phase 0 後、Phase 1 前）

| 項目 | 新位置 | 舊位置 | 處置 |
|---|---|---|---|
| 存檔媒體（SRAM/Flash/EEPROM） | `memory/savedata.py` | `pygba/core/savedata.py` | 整檔搬遷；舊檔與 `*.pyd` 已刪除 |
| BIOS 純數學 helper | `hle/swi_math.py` | `pygba/core/bios.py` 內定義 | 抽出成模組；舊檔改 import，重複定義已刪 |
| ROM header 解碼 | `memory/cartridge.py` | `pygba/core/cartridge.py` | 舊檔改為 adapter，只保留舊欄位名稱 |
| stale 編譯產物 | — | `pygba/core/{savedata,cartridge,bios}.*.pyd` | 刪除，避免 `.pyd` 蓋過新 source |

整併後重跑 `pytest tests -q`：275 passed、4 skipped，行為未退化。

### 保留中（有 deletion gate）

| 舊碼 | 為何還不能刪 | 可刪時機 |
|---|---|---|
| `tests/reference/gba_cpu/`（純 Python；`.pyd` 可選） | 純 Python CPU 是 `tests/test_core_cpu.py` 的 differential oracle；Phase 1 要用它對照新 CPU | Phase 1 新 CPU 通過 opcode／ROM 對照後 |
| `pygba/core/bus.pyx` | I/O 暫存器、BIOS 讀取保護、open bus、VRAM 特例的來源 | Phase 2 bus 移植完成後 |
| `pygba/core/bios.py`（SWI dispatch 本體） | 591 行已驗證 SWI 實作；Phase 3 要移植 | Phase 3 SWI 0x00–0x2A 測試通過後 |
| `pygba/core/core.pyx`、`ppu.pyx`、`timer.pyx`、`dma.py`、`sound.pyx`、`pygba.py`、`screen.py` | 舊 emulator 的唯一可運作核心，仍被 275 個測試使用 | 對應 Phase（PPU/DMA/timer/audio）完成後 |
| 舊 `tests/` | 上述 reference 的 regression suite | 每個子系統移植完成、測試搬到 `tests/gbaemu` 後 |
| `tools/setup_legacy.py`（Cython build） | 舊 `.pyd` 重建用；新 `gbaemu` 不需要 | 舊 core 全部刪除後 |

### 已發現但不動的「重複資料」

- `gba-tests-ref/` 已於 2026-11-01 清理：25 個檔案中 21 個與 `test-rom/` 重複，
  4 個 unique 檔（`arm.gba`、`data_processing.asm`、`psr_transfer.asm`、
  `constants.inc`）已併入 `test-rom/arm-ref/`，原目錄刪除。`pytest` 只依賴
  `test-rom/ppu/hello.gba`。
- 根目錄 `rom.gba` 與 `rom/rom.gba` 內容相同；2026-11-01 整理時已刪除根目錄
  重複檔，統一使用 `rom/rom.gba`（`main.py` 與 legacy golden 已同步更新）。

## Open Questions

以下問題在 Phase 0 刻意保留，採「不改變硬體語意、可測試」的保守方案；
請在對應 Phase 開始前確認或改採更精確的行為。

1. **POSTFLG／DISPCNT／r3／r14 是否納入 HLE post-boot？**
   規格 2.1.1 只列 SP、mode、PC、header copy 與 IRQ 指標清零。舊
   `pygba/core/bios.py` 經真 BIOS 對照額外設定 `r3=0xBAAE187F`、
   `r14=0x08000000`、`POSTFLG=1`、`DISPCNT=0x0080`。Phase 0 未設定；
   待 Phase 2 有 I/O 暫存器後，用「HLE vs 真實 BIOS」等價測試（2.1.4）決定
   是否納入，並同步更新 `PostBootState` 或另建 boot extras。
2. **HLE BIOS 讀取** — ✅（Rust core 已實作，Python reference 未同步）
   Rust `Bus` 有 `in_bios`／`bios_prefetch`：非 BIOS 程式讀 0x0000_0000–0x3FFF
   只回最後 prefetch 的 word（HLE 開機 = `0xE3A02004`，即 mGBA hleBios 離開
   BIOS 前最後一條 prefetch）；`Core::load_bios()`／`NativeCore.load_bios()`
   可載入真實 16 KiB dump（`config.bios_path` 有值時 `NativeEmulator` 自動載入，
   HLE 開機流程不變）。Python `hle_bios_read()` 仍固定回 0，待同步。
3. **Nintendo logo 驗證**
   舊 HLE 會比對 header logo 與 BIOS 內建 logo，不符就拒絕開機。規格 2.1.1
   只要求 complement check；Phase 0 不驗證 logo，也不內嵌 logo 常數
   （clean-room／商標考量）。Phase 3 的等價測試再決定 HLE 是否要模擬此拒絕行為。
4. **Snapshot config hash 是否包含 `bios_path`？**
   Phase 0 的 `config_sha256` 排除路徑（可攜性），只納入會改變模擬結果的
   enum／bool／seed。Phase 3 需決定是否改納入 BIOS 內容 SHA-256；若納入，
   snapshot 格式要升版並補測試。
5. **I/O 區域的讀取語意** — ✅（Rust core 已實作，Python reference 部分同步）
   Rust `Bus` 依 mGBA `GBAIORead` 分類：
   - 有實作的暫存器：讀 `io[]`（寫入時套用硬體遮罩，例如 BG0/1CNT `0xDFFF`、
     WININ/WINOUT `0x3F3F`、BLDCNT `0x3FFF`、BLDALPHA `0x1F1F`、音效各暫存器、
     DMA0–2 CNT_HI `0xF7E0`、DMA3 `0xFFE0`）。
   - 只寫暫存器（BG scroll/affine、WIN0/1H/V、MOSAIC、BLDY、FIFO、DMA SAD/DAD）
     與未實作 offset：CPU 讀取回 open bus（prefetch word）。
   - mGBA 明確列出的未使用 offset（0x66/0x6A/…/0x302）與 DMAxCNT_L：讀回 0。
   - 0x04000400 以上：open bus。
   `suite.gba` I/O read tests 130/130 全 PASS。Python `AddressBus` 仍直接回
   `io[]`，未同步此分類（native 為預設 backend）。
6. **SRAM 的 16/32-bit 存取** — ✅（Python 與 Rust 同步）
   SRAM/Flash 匯流排係 8-bit（mGBA `LOAD_SRAM`／`STORE_SRAM`）：
   - wide load 讀「原始位址」的 byte 再複製（16-bit：`b|b<<8`；32-bit：`b*0x01010101`），
     唔會先對齊；CPU 的未對齊 ROR 之後照常套用（LDRH odd → `ROR32`）。
   - wide store 只寫 1 個 byte，byte 由原始位址低 bit 揀：
     16-bit 用 `(addr&1)`、32-bit 用 `(addr&3)`；其餘 bytes 不變。
   - DMA 啟動時依寬度 `nextSource/nextDest &= -width`，所以 DMA32 由 SRAM+2
     讀會讀 SRAM[0]。
   - CpuSet/CpuFastSet 對 SRAM 用原始位址（wide access 單 byte 讀寫）。
   `suite.gba` 的 SRAM load／store／mirror（44/44、42/42）全 PASS。
7. **`TEST_ROM_ONLY` 的起始狀態**
   規格未定義。Phase 0 採：PC=`0x08000000`、System mode、SP=`0x03007F00`、
   IRQ/FIQ disabled、**不**做 header copy、不掛 BIOS。若測試 ROM 需要不同
   entry／stack，應改由 config 明確指定，而不是猜測。
8. **`REQUIRE_BIOS` 的上電狀態**
   Phase 0 採 PC=0、SVC mode、SP_svc=`0x03007FE0`、IRQ/FIQ disabled，讓 Phase 1
   的 CPU 從 BIOS reset vector 開始執行。BIOS 只檢查大小（16 KiB），尚未做
   內容 checksum；Phase 3 等價測試再補。
9. **`reset()` 是否清空所有可寫記憶體？**
   目前清空 EWRAM/IWRAM/Palette/VRAM/OAM/SRAM，讓重跑可重現；真實 power-on
   的 RAM 內容未定義。Phase 3 snapshot/等價測試需確認 reset 應保留哪些區域。
10. **CLI 的安裝形式**
    目前提供 `python -m gbaemu inspect-rom`，尚未加 console script entry point。
    若要 `gbaemu inspect-rom` 直接可用，需新增不與舊 `tools/setup_legacy.py`（Cython build）
    衝突的 packaging 設定（`pyproject.toml` 或獨立 distribution）。
11. **`VideoView.read_frame(copy=False)` 的回傳型別**
    規格寫 `-> bytes`，所以 Phase 0 一律回 immutable `bytes`，`copy` 參數目前
    不改變語意。Phase 2 若要避免每 frame 複製，需重新定義為 `memoryview` 或
    numpy view，並更新 API 契約。
12. **Unaligned bus 存取策略**
    Phase 0 的 hardware `read_u16/u32` 先做寬度對齊（忽略低位址線），
    `bus/access.py` 提供 `unaligned_word_rotate()` 供 CPU 層使用；舊
    `pygba/core/bus.pyx` 則在 bus 層直接 ROR。Phase 1 移植 CPU 時要選定單一
    位置實作，避免雙重旋轉。
13. **`seed` 目前沒有消費者**
    `Emulator` 以 `random.Random(config.seed)` 建立 RNG，`reset(seed=...)` 也會
    重播，但 Phase 0 沒有任何模擬行為用到亂數，seed 對結果尚無影響；
    `test_determinism_same_rom_and_config` 目前是「結構性」通過。Phase 1 起若
    引入測試用 RNG 注入（fuzz 指令、timing jitter 等），必須以 seed 驅動並補
    行為測試；在那之前不要把 seed 視為已驗證的可重現性來源。
14. **提前落地的 Phase 3 模組**
    `hle/swi_math.py`（BIOS 純數學 helper）與 `memory/savedata.py`
    （SRAM/Flash/EEPROM）已在 Phase 0 整併進套件，但目前只有 legacy `pygba`
    路徑使用，`tests/gbaemu` 沒有直接測試。Phase 3 接入 SWI handler 與
    cartridge adapter 時要補逐 byte 測試；在那之前這兩個模組不算 Phase 0
    驗收範圍。
15. **Phase 1 的週期模型是暫行近似（已於 Phase 2 timing 基礎解決）**
    規格 §3.6 已定死時序；Phase 2 已把 `step_cycles()` 換成 S/N/I 成本
    （`cpu/cycles.py`＋`bus/access.py`），並補每條指令類別的 cycle 測試
    （`tests/gbaemu/test_timing.py`）。後續 Phase 3 只需補 DMA/timer 的成本。
16. **IRQ 進場沒有 pipeline 延遲與 HLE BIOS stub**
    `check_irq()` 目前是「條件成立即進場」，缺 legacy 的 2-cycle 延遲、
    IRQ entry 的 `_stall`、以及 HLE 的 0x138 回程 stub（legacy
    `gba_cpu/cpu.py:605-648`）。Phase 3 接 IRQ 時要一併實作並補時序測試。
17. **未定義指令的 HLE retry 行為**
    legacy `gba_cpu/arm.py` 在無真 BIOS 且 ROM[0x9C]≠0xA5 時，會模擬零售卡
    「無限重試同一條指令」；Phase 1 的 `cpu/arm.py::_undefined` 一律進 UND
    例外（架構正確），retry 屬 BIOS handler 行為，Phase 3 再決定是否移植。
18. **SWI 的未驗證/近似部分**
    `HuffUnComp`（0x13）沿用了 legacy 的實作但尚未有獨立向量測試；SoundDriver
    系列（0x1A–0x1E、0x28–0x2A）與 MultiBoot（0x25）目前是 no-op；CpuSet/
    CpuFastSet/affine/BitUnPack 的執行 cycle 尚未計入 `bus.tick`。Phase 4 音訊與
    相容性測試時要補齊。
20. **Prefetch buffer 尚未逐 halfword 模擬**
    Rust 已把 Python `cpu/cycles.py::_fetch` 完整移植（ROM + WAITCNT bit14 →
    fetch 1 cycle；ROM internal-cycle opcode 的 Prefetch Disable Bug 1S→1N），
    suite_probe 預設 timed；legacy 基準 Timing tests 255 → 782/2020（round 8 起預設已切 mGBA）。
    2026-11-03 round 4：照 mGBA 的 active-region accounting 另寫
    `arm_cycles_mgba`／`thumb_cycles_mgba`（`--mgba`），修正 store 只 `++wait`、
    stall 可負、PC+8/+4、multiply WAIT 表、Thumb LDM/STM 方向、LDM/STM
    逐 register 跨區計算之後，Timing 升到 1564/2020（Timer count-up
    159/468、Misc edge 6/10，其他 suite 不變）。round 8 已切預設：Python TIMED／TRACE 同 Rust CoreConfig 預設都用 mGBA model（legacy 保留 `--legacy` 對照）。
    Round 9 → 1596（LDM/STM 同區 stall 公式）；DMA 起動延遲（3 cycles）修好
    to/from ROM 大部分（1660）；ROM→ROM internal overhead 改 0（+36 → 1696）；
    round 12 加 Game Pak DMA ±1 rounding → **1748/2020**，DMA 相關 Timing
    檢查 0 fail、DMA suite 仍 1256/1256。剩餘 272 個 fail 的實際分佈（按 suite
    log 逐項統計）：BIOS Div／Div2／Sqrt 1-3／ArcTan 120、BIOS CpuSet 20、
    multiply（含長乘法）78、LDM/STM 36、LDR/STR（Thumb `[sp]`）18；其中 188
    個集中喺 prefetch-on 的 ROM config（`P..`／`PN.`／`P.S`／`PNS`），
    即 prefetch refill 時機係最大系統性偏差。
    Round 13（已落地）：BIOS 那 140 個的 root cause 係 `mgba_swi_cycles` 只加
    `(stall & 3)`——mGBA 之所以可以咁做，係因為佢真係執行 hle-bios 的
    `StallCall` loop 燒掉其餘 cycles；我哋純 HLE，所以要喺 HLE 加返
    `stall + profile + return refill`。profile 按 caller 的區域（IWRAM 42/43、
    EWRAM 44/45、GamePak 47）同 WAITCNT bit2（−1）校準。結果 Timing
    **1748 → 1832**（+84），BIOS 數學 84/120，其他 suite 全部不變；Rust 與
    Python 完全一致。剩 36 個 BIOS 數學 + 20 個 CpuSet 見
    [docs/architecture/TIMING.md](docs/architecture/TIMING.md) 4e。
    Round 14（診斷，未改動）：剩餘 156 個 prefetch-on fail 逐行對照 repo 內
    vendored 的 mGBA 原始碼（`debug/_mgba_memory.c` 的 `GBAMemoryStall`、
    `_mgba_isa_inlines.h` 的 `ARM_WAIT_SMUL/UMUL`、`_mgba_isa_arm_c.c` 的
    multiply WAIT 參數、`_mgba_isa_arm.h` 的 `ARM_PREFETCH_CYCLES`、ROM
    waitstate 表）→ 我們實作一致。試過 mGBA master 的 stall 變體（1832，無變）、
    `stall - loads`（1366）、`stall - 1`（1390），全部還原。結論：剩返嘅 ±1–3
    係硬體同 mGBA 模型的差異，只能逐類實證校準且會威脅 1832 基線；下一步建議
    先做 CpuSet（20 個、純 HLE、獨立）。詳見 TIMING.md 4f。
    Round 15（已落地）：suite 的「CpuSet」timing test 其實執行 ARM `swi 0x0C`
    （CpuFastSet，256 words copy，期望 ~3453），原本只收「非 HLE」固定開銷。
    新增 `hle_cpuset_transfer`：`13 + units × per_unit`（32-bit copy 25、
    fill 16、16-bit 13／8），20 個 config 全部命中，Timing 1832 → **1852**。
    過程中發現 suite 量測對 per_unit 的敏感度係 0.5×（實測校準值）。
    多 ROM smoke（2026-11-04）：9 支真實 ROM 有 8 支 Python／Rust frame hash 相同
    （rom、song、Tetris、rates、armwrestler、RetroRegen、GBAUtilityTools、suite）；
    LeafGreen 原本由 frame 10 起 diverges；2026-11-04 補完 Rust 的 SRAM／Flash
    save-type（ROM 簽章偵測、SRAM 32 KiB、Flash 64／128 KiB＋bank＋AA/55 命令
    序列）之後 **SRAM 內容已同 Python 完全一致**（128 KiB），但 frame 1 起
    IWRAM stack 同 IO sound 暫存器（0x63／0x69／0x79／0x80–0x84／0x89）仍然
    唔同 → 剩低係 sound 引擎／IRQ 行為差異（同 save、timing 無關）。
    `rom.gba` 係 EEPROM（`EEPROM_V`），Rust 序列 EEPROM 仍未實作，`region_info`
    報 65536（Python 8192），但早期未用到所以 frame hash 仍相同。
    test-rom 的 CPU 測試 ROM 有 4 支不同（frame 1 已分叉），抽樣 360 個隨機編碼
    有 ~3% 成本唔同（coprocessor／未定義／條件指令），亦屬既有 parity 缺口。
    Round 5：同一個 accounting 已搬去 Python reference
    （`CpuBus.mgba_timing`、`_arm_cycles_mgba`／`_thumb_cycles_mgba`、
    timers start offset），`tools/mgba_cost_diff.py` 130 個指令×config
    0 mismatch，Python Timing 亦係 **1748/2020**（同 Rust 一致）。
    Round 11：ROM→ROM DMA internal overhead 4 → 0，Timing 1696。Round 12：Game Pak DMA
    ±1 rounding（ROM→ROM／to ROM／from ROM 三條 heuristic）→ 1748。Round 10：即時 DMA 加 3-cycle startup delay（timed 模式），Timing 1596 → 1660、DMA suite 仍 1256。Round 7：timer start offset 只套用 32-bit enable write（16-bit CNT_H = 0），修好 SIO timing 4/4；mgba model 的 IRQ arm delay 改 5（legacy 2），Timer IRQ 0 → 65、count-up 159 → 174。Round 6：Rust 加 `CoreConfig.timing_model`（`TimingModel::Legacy`／`Mgba`，預設 Legacy）；Python 仍用 `CpuBus.mgba_timing` internal flag（spec 保持三種 TimingMode）。詳細數據、mGBA 公式同 flip 計劃見
    [docs/architecture/TIMING.md](docs/architecture/TIMING.md)。
19. **指令週期與 GBATEK 表的 ±1 差異**
    Phase 2 沿用 legacy 的週期模型（含 prefetch／16-bit ROM bus／128 KiB 邊界），
    部分指令總數與規格 §3.6.3 的通用表不同（例如 B/BL 目前 2 cycles、STM n=2
    為 4 cycles）。這些差異要用硬體測試 ROM（`test-rom`）校準，
    再決定改模型或改規格文字；在那之前以 legacy 模型為準。

## Phase 1 開工清單（CPU 與基本記憶體）— 已完成

1. ✅ 從 `gba_cpu/registers.py`、`gba_cpu/cpu.py`、`gba_cpu/thumb.py` 遷移
   ARM/THUMB 解碼與執行到 `cpu/`（`arm.py`、`thumb.py`、`conditions.py`、
   `registers.py`、`arm7tdmi.py`）。
2. ✅ 實作 `Emulator.step_cycles()`、`StepResult` 欄位。
3. ✅ 把 `BreakpointTable.match()` 接進執行迴圈；命中回報 id。
4. ✅ 對齊 `bus/access.py` 與 CPU 的 unaligned 語意（統一在 `CpuBus` 旋轉）。
5. ⚠️ 新增 `tests/gbaemu/test_cpu_*.py`（32 個 case，含隨機差動）；公開測試 ROM
   只做 30 萬指令 smoke，legacy golden 固定向量待補。
6. ✅ 更新本檔與 `docs/GBATEK_INDEX.md`。

## Phase 2（I/O、timing、PPU、frame boundary）— 已完成

依規格 §3.6 的順序實作，timing 先行：

1. ✅ **Timing 基礎**（2026-10-31）：`timing.py` 常數／frame helpers、
   `bus/access.py::access_cycles`（S/N、WAITCNT、128 KiB 邊界）、
   `cpu/cycles.py` 指令週期（自 legacy 移植）、FUNCTIONAL／TIMED 切換、
   `step_cycles()` 不超額。驗收：`tests/gbaemu/test_timing.py`。**Phase 2 驗證結果：**
   `pytest tests/gbaemu -q` → 135 passed；`pytest tests -q` → 320 passed, 4 skipped。
2. ✅ **I/O 暫存器**（2026-10-31）：`bus/io.py::IoRegisters` 實作 DISPCNT／
   DISPSTAT／VCOUNT／KEYINPUT／KEYCNT／IE／IF／IME／WAITCNT／POSTFLG 的讀寫語意；
   IF 寫 1 清除、KEYINPUT active-low、KEYCNT AND/OR IRQ；`AddressBus` 的 IO 路徑
   改走暫存器（peek／debug 亦同）。測試：`tests/gbaemu/test_io.py`。
3. ✅ **PPU 事件**（2026-10-31）：`video/ppu.py::Ppu` scanline 狀態機、VCOUNT／
   DISPSTAT 即時 flags、HBlank/VBlank/VCount IRQ、事件 cycle 依 §3.6.6；
   `step_frame()`／`run_frames()` 以 280,896 cycles 邊界為準。測試：`test_ppu.py`。
4. ✅ **Mode 3 framebuffer**：frame 邊界由 VRAM（RGB555）繪製到 240×160 RGB888；
   force blank 白畫面；`VideoMode.OFF`／`render=False` 不寫 framebuffer。
   測試：`test_frame.py`。
5. ✅ **KEYINPUT/KEYCNT**：`InputPort.keyinput_mask`（active-low）、KEYCNT AND/OR
   IRQ（`poll_keypad()`）。測試：`test_io.py`。
6. ✅ **VRAM bitmap 模式**：DISPCTL mode 3/4/5 時 `Vram.bitmap_mode` 自動切換
   （BG 80 KiB／OBJ 16 KiB），tile 模式回到 BG 64 KiB／OBJ 32 KiB；8-bit 寫入規則
   回歸測試在 `test_bus.py`、`test_frame.py`。

## Phase 3（DMA、timer、IRQ、SWI、save、snapshot）— 已完成

依 `gbatek-gba-specs/` 的章節順序實作（每項都先讀對應章節再寫）：

1. ✅ **DMA0–3**（`07-dma`，2026-10-31）
   - 暫存器：SAD（0x0B0/0xC8/0xC8…）、DAD、CNT_L、CNT_H（0x0BA/0xC6/0xD2/0xDE）；
     CNT_H bits：dest 5-6、src 7-8、repeat 9、size 10、DRQ 11、start timing 12-13、
     IRQ 14、enable 15。
   - 行為：enable 0→1 時重載內部 SAD/DAD/CNT 並等 **2 cycles**；repeat 只重載
     CNT_L（inc+reload 時 DAD 也重載）；成本 `2N+2(n-1)S+xI`（x=2；src/dst 都在
     GamePak 時 x=4）；OAM/OBJ VRAM 的 HBlank DMA 需要 DISPCNT bit5；完成時清除
     enable、可拉 IF bit8-11。
   - 位址遮罩（mGBA `DMA_SRC_MASK`／`DMA_DST_MASK`）：SAD 用
     `0x07FFFFFE`（DMA0–2）／`0x0FFFFFFE`（DMA3），DAD 用 `0x07FFFFFE`／
     `0x0FFFFFFE`；所以 DMA0–2 的 ROM（0x08xxxxxx）鏡射到 0x00xxxxxx（BIOS/
     open bus）、SRAM（0x0Exxxxxx）鏡射到 0x06xxxxxx（VRAM）。呢個就係 suite
     「DMA0 讀 ROM 得 latch／讀 SRAM 得 VRAM 0x50D0」「DMA0–2 寫 SRAM 其實寫 VRAM」
     的真正原因，唔需要額外封鎖。
   - 啟動時依寬度對齊：`nextSource &= -width; nextDest &= -width`（16-bit `&!1`、
     32-bit `&!3`），所以 DMA32 由 SRAM+2 讀會讀 SRAM[0]。
   - DMA0–2 若原本寫入嘅 DAD >= `0x08000000`（ROM/SRAM，硬體上屬 invalid
     destination）：transfer 照完成，但 masked 位址落喺 VRAM/OAM 嘅副作用唔寫出。
     咁樣 suite「SRAM mirror store」唔會污染 OAM[0]，之后 detail 檢視
     「SRAM mirror load」DMA0 rows 仍然係 0（batch 結果完全一樣）。
   - 讀取：只有 `source >= 0x02000000`（EWRAM 以上）才真正讀；其他（BIOS、open bus）
     沿用該通道上次搬運的 `latch`。16-bit 讀入後 `latch = h | h<<16`；寫出時
     16-bit 用 `latch >> (8*(dest&2))`。
   - **ROM 區 source 強制遞增**（mGBA `GBADMAWriteCNT_HI`）：SAD 落在
     `0x08000000–0x0DFFFFFF` 時 `sourceOffset = width`，即無視 src control 的
     fixed／decrement 一路遞增；搬運途中離開 ROM 區先回復原本控制。呢個就係
     suite「=ROM」Imm H／Imm W 同「-ROM」列期待值（最後一個讀取）的原因：
     `srcR[3]` halfword 依序 BEEF/DEAD/BEF0/DEAD，32-bit 最後讀到 `DEADBEF2`；
     DMA0 因為遮罩 bit27 落 BIOS 區所以仍然用 latch（`BABE`）。
   - 觸發：immediate、VBlank（cycle 197,120）、HBlank（`line*1232+1006`）；
     與 PPU 事件同步，不可 frame 結束補算。
   - 實作：`devices/dma.py::DmaController`；暫存器掛在 `IoRegisters` 的 0xB0–0xDF；
     `Emulator._service_dma()` 把 DMA 佔用的 cycle 計入 CPU/PPU。測試：
     `tests/gbaemu/test_dma.py`（14 個 case；Python reference 仍是舊 latch 模型，
     Rust core 已改用上面的遮罩／對齊／`source < EWRAM` 規則；suite Memory tests
     1552/1552 全 PASS）。
2. ✅ **Timers 0–3**（`06-timers`，2026-10-31）
   - TMxCNT_L：寫入只改 reload、讀取回目前 counter；counter 只在 overflow 或
     start bit 0→1 時重載（單一 32-bit 寫入同時寫 reload+start 時，新 reload 視為
     counter）。
   - TMxCNT_H：prescaler F/1、F/64、F/256、F/1024；bit2 count-up 忽略 prescaler、
     前一級 overflow 才遞增（TM0 不支援）；bit6 overflow IRQ（IF bit3-6）。
   - 實作：`devices/timers.py::Timers`；`AddressBus.tick()` 同時推進 PPU 與 timer；
     `IoRegisters` 委派 0x100–0x10F；32-bit 寫入（reload+start）依 GBATEK 語意。
     測試：`tests/gbaemu/test_timers.py`（8 個 case）。
3. ✅ **IRQ 收尾**（`10-interrupts`，2026-11-01）
   - 2-cycle pipeline 延遲、IF acknowledge、HLE BIOS IRQ stub（0x128 存
     R0-R3/R12/LR、0x138 還原、0x13C `SUBS PC,LR,#4`）。
   - 實作：`Arm7Tdmi.check_irq()`（arm → 倒數 → 進場，回傳 2S+1N）、
     `_hle_irq_enter()`／`_hle_irq_return()`；`CpuBus.bios_present` 由真實
     `AddressBus` 決定。測試：`tests/gbaemu/test_irq_hle.py`（4 個 case）。
   - **IntrWait（SWI 0x04）喚醒即刻投遞 IRQ**（2026-11-03）：BIOS IntrWait 要等
     IRQ handler 行完先返回主程式；之前模型係「先執行 SWI 後一條指令，再喺
     boundary 檢查」，令 suite「Timer count-up」嘅 `irqCounter` 先被寫成新值、
     再被遲到嘅 IRQ 扣到 0，之後 timer 永遠唔會 disable → IRQ storm／hang。
     修正後 suite 由 0/hang 變 177/468。`Halt`（SWI 0x02）維持原本次序，
     suite「SIO timing tests」仍然校準喺 4/4。IRQ 進場成本亦由 3 改 4 cycles
     （S+N+I，同 suite 量測一致）。
4. ✅ **SWI 0x00–0x2A**（`16-bios`，2026-11-01）
   - 呼叫慣例：SPSR/R11/R12/R14 存 SVC stack 後切 System mode，返回等價
     `MOVS PC,R14`。
   - 算術：Div（r0/r1、r3=abs quotient、除零無窮迴圈）、DivArm、Sqrt、ArcTan、
     ArcTan2；GetBiosChecksum=`0xBAAE187F`。
   - 記憶體：CpuSet（16/32-bit、bit24 fill、count bits0-20、BIOS 來源保護）、
     CpuFastSet（32-byte block、wordcount、GBA round-up 8 words）、BgAffineSet、
     ObjAffineSet、BitUnPack（1/2/4/8→1..32 bit、offset、zero flag）。
   - 解壓：LZ77（header type=1、8-bit 輸出）、LZ77→VRAM（16-bit 輸出、disp=000
     特例）、Huffman、RL、Diff8/16；header：bits0-3 reserved、4-7 type、
     8-31 decompressed size；全部逐 byte 測試。
   - 音效/其他：SoundBias、SoundDriver*（依文件實作或明確 no-op）、MultiBoot/
     HardReset/CustomHalt（未文件化者 strict raise）。
   - 實作：`hle/swi_impl.py::build_handlers()`（自 legacy `pygba/core/bios.py` 移植）；
     `Emulator` 建構時注入 `SwiTable`。已實作 0x00–0x1F、0x26、0x27；0x20–0x24
     （SoundWhatever）維持 strict raise；0x25/0x28–0x2A 為 no-op。
     測試：`tests/gbaemu/test_swi.py`（14 個 case，含 LZ77/RL/Diff 逐 byte）。
   - Halt／Stop／IntrWait：`Arm7Tdmi` 新增 `wait_irq` 與 halt 喚醒（IE&IF 或指定
     flag），喚醒後可在指令邊界進 IRQ。
5. ✅ **Save media**（`12-cartridges`，2026-11-01）
   - 由 ROM 內 ID 字串偵測：`EEPROM_V`、`SRAM_V`、`FLASH_V`/`FLASH512_V`/
     `FLASH1M_V`（SRAM 32 KiB、Flash 64/128 KiB、EEPROM 512 B/8 KiB）。
   - SRAM 8-bit；Flash 命令序列（AA/55、erase chip/sector、write byte、bank）；
     EEPROM bit-serial 於 `0x0DFFFF00`，需 8 waitstates。
   - `cartridge_flush_to_disk()` 以暫存檔 + rename 原子寫入；載入 snapshot 不自動
     寫回 `.sav`。
   - 實作：`RomCartridge` 自動 `detect_save()`（SRAM/Flash/EEPROM）＋`save` 後端；
     bus 於 0x0E 視窗走備份後端（wide store 只寫 1 byte）、0x0D 視窗走 EEPROM
     bit-serial；DMA 傳輸前 `begin_stream()`；開機自動載入 `<rom>.sav`（大小相符時）。
     測試：`tests/gbaemu/test_save.py`（11 個 case）。
6. ✅ **Snapshot payload**（`5.7`，2026-11-01）
   - 九段（CPU/BUS/PPU/DMA/TMR/IRQ/KEY/CRT/SCH）序列化＋CRC；`save_state()`／
     `load_state()` 接線；錯誤路徑（magic/version/CRC/ROM/config）維持現有測試。
   - 實作：`state/snapshot.py` 的 `pack_sections()`／`unpack_sections()`；各元件
     `snapshot_state()`／`restore_state()`（CPU/BUS/PPU/DMA/TMR/IO）；
     `Emulator.save_state()`／`load_state()`（還原後 `events.clear()`、不自動寫回
     `.sav`）。測試：`tests/gbaemu/test_snapshot_roundtrip.py`（5 個 case）。
   - ✅ **PPU BG/OBJ/window/blend 暫存器要進 snapshot**（2026-11-02）：這區的
     I/O 寫入只進 `Ppu._regs`、原本不寫 `IoRegisters._bytes`，所以存檔再讀檔後
     `BGxCNT`／`WININ`／`WINOUT`／`BLDCNT`／`BLDALPHA`／`MOSAIC` 全部變 0，
     renderer 會畫空白或錯層。修正：`IoRegisters.write16()` 同步寫 raw bytes；
     `IoRegisters.load_state()` 用 `Ppu.restore_disp_regs()` 回填快取。
7. ✅ **SIO／JOY 暫存器與 normal 模式傳輸**（2026-11-03；suite 對齊）
   - SIOCNT／RCNT 寫入遮罩同讀值跟 mGBA `GBASIOWriteSIOCNT`／`GBASIOWriteRCNT`：
     SIOCNT 寫入 `&0x7FFF`；MULTI 模式 slave=1、id=0、ready=1（寫 0xEFFF 讀回
     0x6F8F）、UART `&0x7FAF`、其餘 `&0x7F8F`。RCNT 寫入 `&0xC1FF`，bits0-3
     係未連線線路狀態（normal 0x5、JOYBUS 0xC、其餘 0xF）。
   - SIODATA32 只在 NORMAL_32 可讀；SIOMLT_SEND／SIODATA8 除 UART 外可寫；
     JOYCNT 只保留 bit6；JOY_TRANS／JOY_RECV／JOYSTAT 讀回 0；0x136／0x142／
     0x15A 讀 0。`suite.gba`「SIO register R/W tests」90/90 全 PASS。
   - 32-bit I/O store 拆成兩個 16-bit 寫入（mGBA `GBAIOWrite32` default）；
     之前逐 byte 寫入會令 SIOCNT 低 byte 的中間遮罩污染 mode bits。
   - Normal 模式傳輸：start bit 0→1 後 `8/32 × 16.78 MHz ÷ clock + 118` cycles
     完成，清 start bit、寫入接收資料、視 bit14 拉 IRQ_SERIAL（IF bit7）；
     「SIO timing tests」4/4（Multi 模式無連線 → 逾時 SKIP）。
8. **驗收**：DMA/timer/IRQ 的 cycle 測試（含 2-cycle 延遲與 transfer 成本）、
   SWI 逐 byte 測試、save 命令序列測試、snapshot round-trip；跑
   `test-rom` 的 DMA/timer/irq/save ROM。

## 測試與驗證指令

```powershell
# Phase 0 測試（pytest 9.2.0；venv Python 3.14.2；在專案根目錄執行）
.\venv\Scripts\python.exe -m pytest tests/gbaemu -q

# 舊 pygba／tests.reference.gba_cpu 回歸（conftest.py 會把專案根加進 sys.path）
.\venv\Scripts\python.exe -m pytest tests -q

# 型別／語法煙霧（根目錄 = 套件根，只編譯套件模組）
.\venv\Scripts\python.exe -m compileall -q __init__.py __main__.py api_types.py cli.py config.py `
    emulator.py errors.py events.py log.py timing.py bus cpu devices debug hle memory state video

# CLI 驗收（JSON 單一物件、欄位順序固定；必須從上一層執行才 import 得到 gbaemu）
Push-Location ..
.\gbaemu\venv\Scripts\python.exe -m gbaemu inspect-rom gbaemu\test-rom\ppu\hello.gba --json
Pop-Location
```

## Phase 4（音訊、PPU 模式、video contention）— 已完成

1. ✅ **音訊 FIFO 路徑**（2026-11-01）：`audio/sound.py::SoundController`
   - SOUND 暫存器 0x060–0x0AF、FIFO A/B（32 bytes）、`SOUNDCNT_H` bit11/15
     分別對應 DMA1/2 的 Special timing（每次 4 words → 0x040000A0/A4）。
   - PCM：BUFFERED 模式以 32768 Hz 近似、8-bit signed → s16le stereo，
     buffer 上限 16 KiB（不阻塞核心）；`Emulator.audio.read_buffer()`。
   - 測試：`tests/gbaemu/test_audio.py`（6 個 case）。
2. ✅ **PSG 四聲道＋DMA Sound 混音**（2026-11-02；Python 與 Rust 同步）
   - 時基：輸出 32.768 kHz（512 cycles／sample）、PSG 262.144 kHz（8 tick／
     sample）、frame sequencer 512 Hz（length 256 Hz、sweep 128 Hz、
     envelope 64 Hz）。
   - Channel 1/2 square（duty、envelope、length、ch1 sweep）、Channel 3 wave
     （WAVE_RAM、bank/dimension 忽略、volume code／force 75%）、Channel 4
     noise（15/7-bit LFSR、r/s 頻率）。
   - 混音：SOUNDCNT_L 左右 master volume＋每聲道 L/R enable、SOUNDCNT_H PSG
     volume（25/50/100%）、DMA Sound A/B 音量與左右開關、SOUNDCNT_X bit7
     master enable（關閉時 PSG 暫存器歸零）。
   - DMA Sound 取樣改由 **timer 0/1 溢位**推動（SOUNDCNT_H bit10/14），不再
     每個輸出 sample 硬拉 FIFO；Python `Timers.bind_sound()`、Rust
     `sound_timer_overflow()`。
   - 修正：square period 是 (2048-n)/4 tick、wave digit (2048-n)/8 tick、
     frequency 是 write-only（要留在 channel state，不能讀 io）。
   - 測試：Rust `sound_pcm_buffer`／`psg_square_pitch_matches_hardware_formula`
     （512 Hz → 0.1 s 51 個週期）／`direct_sound_advances_on_timer_overflow`；
     Python 同名測試。
   - GUI：`GbaApp` 開 pygame mixer（32.768 kHz／s16le／stereo），`tick()` 把
     `audio.read_buffer()` 餵給 Channel（backlog > 200 ms 就丟棄）；同時加上
     59.7275 Hz frame pacing（`throttle=True`）。
   - 待補：SOUNDBIAS 振幅解析度／PWM 細節、wave RAM bank 切換時序、PSG 的
     DC offset／硬體低通（現時直接輸出 s16）。
   - 待補：sound channel 內部狀態未入 snapshot（IO 暫存器有，但 envelope／
     timer／LFSR 唔會還原，載入存檔後音樂會由靜音重新開始）。
3. ✅ **PPU Mode 0/1/2、sprites、affine、blending**（2026-11-01）：`video/renderer.py`
   - Mode 0/1 text BG（4/8bpp、scroll、尺寸 256-512）、Mode 1/2 affine BG
     （PA/PB/PC/PD、ref、wrap）、regular/affine sprites（h/v flip、priority、16/256 色）、
     逐 pixel 優先度合成、alpha blend（EVA/EVB）、brightness fade、force blank、
     Mode 3/4/5 bitmap（Mode 4 用 frame select、Mode 5 160x128）。
   - 測試：`tests/gbaemu/test_ppu_modes.py`（13 個 case）。
   - ✅ Window0/1（WIN0H/V、WININ/WINOUT、layer mask）、BG/OBJ mosaic（MOSAIC、
     BGxCNT bit6、attr0 bit12）。
   - ✅ **HBlank 逐線渲染**（2026-11-02）：`Ppu.advance()` 在每條可見 line 進入
     HBlank（IRQ／DMA 改 register 之前）呼叫 `render_frame(..., y0=line, y1=line+1)`；
     mid-frame raster effect（suite「Layer toggle 2」）與硬體一致。Rust core
     同步改成由 `Ppu::completed_lines` 驅動逐線繪製。
   - ✅ **OBJ vs BG 同 priority**（2026-11-02）：GBATEK Video/OBJ「Priority」規定
     OBJ 在上層；sprite candidate 改用 `order = -1`（Rust `consider_obj!` 用 `<=`）。
     這修好 Dr. Mario 選單文字（OBJ）被同 priority BG 蓋住的問題。
   - ✅ **Bitmap modes 疊 OBJ**（2026-11-02）：`_render_bitmap_composite()` 把
     Mode 3/4/5 的 bitmap 當 BG2，疊 OBJ、window、alpha/fade；Mode 4 的
     palette index 0 透明、Mode 5 只有左上 160x128。suite「Basic Mode 3/4」
     的 Actual／Expected 標籤現在正確顯示在最上層。
   - 待補：OBJ window（WINOUT 路徑已預留）、affine 雙線性取樣、bitmap modes
     的 BG2 affine 參數（BG2PA..PD／BG2X/Y；目前只在 text modes 套用）。
   - 效能備註：逐線渲染令 Python backend 每條 line 都 `_build_state()` 一次，
     單一 text BG 的 `_text_buffer` fast path 亦因 `partial` 而停用（約 4 fps）。
     Rust core 的 pixel loop 是 native，沒有這個問題；若 Python fallback 要提速，
     可以把 `_text_buffer`／`_blit_single_text` 改成接受 y0/y1 的 row range。
4. ✅ **Video contention／prefetch**（2026-11-01）：`AddressBus.video_wait()`
   - 可視掃描線：VRAM/Palette/OAM 存取 +1 waitstate；HBlank：VRAM/Palette 0、
     OAM 需 DISPCNT bit5；VBlank/forced blank 0。
   - `CpuBus.access_cost()`、`DmaController._cost()` 都納入 contention。
   - Prefetch disable bug：ROM 中 internal-cycle opcode 的 fetch 由 1S 變 1N；
     prefetch 啟用時循序 fetch = 1 cycle（8-entry buffer refill 仍為簡化模型）。
   - 測試：`tests/gbaemu/test_video_contention.py`（7 個 case）。

## Phase 5（RL 介面）— 進行中

1. ✅ **GBAEnv（Gymnasium 風格）**（2026-11-01）：`rl/env.py`
   - `MemoryRange`／`ObservationConfig`／`ActionSpec`／`GBAEnvConfig`（規格 5.8）。
   - observation：screen（240x160 RGB888 → grayscale/resize）、memory（白名單
     ranges）、hybrid（螢幕攤平＋memory）；dtype uint8。
   - action：buttons（dict）、multi_binary（10-bit 固定順序）、discrete（sets）；
     每個 action 完整替換按鍵狀態。
   - frame_skip（同一組按鍵保持 N frames、obs 取最後 frame）、truncated 由
     max_episode_steps、reward 固定 0.0、terminated False；info 含 frame_index/
     vcount/irq_pending/halted/buttons/frames_rendered。
   - `save_state()`／`load_state()` 直接代理 snapshot。
   - venv 已安裝 gymnasium 1.4.0；`check_env` 通過（含 `reset(seed/options)`、
     `_np_random`）。
2. ✅ **GbaApp facade（PyBoy 風格）**：`rl/wrappers.py::GbaApp`
   - `GbaApp("rom/rom.gba", window="SDL3", sound="100")`、`tick()`／`stop()`、
     `button()`、`screen.ndarray`、save_state/load_state；SDL 視窗失敗時自動
     headless；新公開入口 `gbaemu.GbaApp`（不再使用 PyGBA 名稱）。
   - legacy 參考實作仍可 `from pygba.pygba import PyGBA`（golden 測試已改走此路徑）。
   - 實測 `main.py`：載入 `rom/rom.gba`（BZPJ），HLE 開機成功並持續 tick。
3. ✅ **實機驗證**（2026-11-01）：`main.py` 可跑（`from gbaemu import GbaApp`）
   - HLE 開機成功：`DRMARIO&PONJ`（BZPJ），60 frames 時 `cpu_cycles=16,853,760`、
     PC=0x0800414C；`tick()` 每 frame 約 0.73 s（含 render）。
   - 301-frame 無 render capture：13.92 s（21.63 fps），畫面為遊戲健康警告頁
     （`docs/images/phase5_frame.png`）。
   - Halt fast-forward：FUNCTIONAL 模式在 IE&IF 未觸發時以 64-cycle chunk 推進，
     避免 halted frame 逐 cycle 卡住（TIMED 模式維持逐 cycle）。
4. **待補**：process pool rollout、trace replay、multi-process 確定性測試、
   no-render benchmark 報告（目前只有單 process 初步數據）。

## 視窗修正（2026-11-01）

- `GbaApp` 的 SDL3 視窗原本只開視窗、沒有 pump 事件／blit framebuffer，迴圈看起來
  「死掉」且關不掉。已補：`_pump_window()`（QUIT／鍵盤）、`_draw_window()`（240x160
  RGB → 視窗 scale + flip）、`stop()` 關閉 pygame，`tick()` 在視窗關閉後回 False。
- 另加 PPU dirty 快取：VRAM／Palette／OAM／BG 暫存器沒變時沿用上一個 framebuffer。
  實機警告畫面仍約 1.6 fps（renderer 是 Python 逐 pixel，遊戲每 frame 仍有寫入）；
  後續若要可互動視窗，需 numpy/scanline 快取或 Cython renderer（見 Phase 5 效能）。

## 專案整理（2026-11-01）

- `rl.py` → `rl/` 子套件（`env.py`／`spaces.py`／`wrappers.py`）；型別統一由
  `api_types.py` 匯出，移除重複定義。
- 根目錄 `rom.gba`（與 `rom/rom.gba` 相同）刪除；`rom.gba.sav` 移到
  `rom/rom.gba.sav`；`gba_bios.bin` 移到 `rom/bios/`；`phase5_frame.png` 移到
  `docs/images/`。
- 重複的 `gbaemu_rl.py` 與 `main.py` 相同，保留 `main.py` 為 RL 主程式。
- 新增 `docs/ARCHITECTURE.md`、`docs/REVERSE_ENGINEERING.md`；改寫 `README.md`；
  `docs/GBATEK_INDEX.md` 更新到 Phase 5 現況。

## Package 形式（2026-11-01）

- 新增 `pyproject.toml`：`package-dir = { gbaemu = "." }`，wheel 只含 `gbaemu/`
  程式碼（不含 tests／rom／docs／legacy），入口 `gbaemu = gbaemu.cli:main`。
- 舊 Cython 建置腳本移至 `tools/setup_legacy.py`（不參與 wheel）；根目錄
  `conftest.py` 移至 `tests/conftest.py`；`build/` 舊產物已清除。
- 新增 `docs/PACKAGING.md`；README 增加安裝章節；`rl/wrappers.py` 的 facade
  更名為 `GbaApp`（公開入口 `from gbaemu import GbaApp`），不再使用已被他人
  使用的 `PyGBA` 名稱；legacy `pygba.PyGBA` 僅保留給舊測試。
- 已建 wheel 並安裝到 venv site-packages，從 repo 外驗證
  `gbaemu.__file__ = ...site-packages\gbaemu\__init__.py` 與 `GbaApp.tick()`。

## 效能（2026-11-01）

- 量測：`rom/rom.gba`、FUNCTIONAL：`step_frame(render=False)` 約 30 fps
  （8.4M cycles/s）、render 約 3 fps；legacy Cython uncapped 約 61 fps／render 58 fps。
- 已做：halt event skip（PPU DISPSTAT IRQ／timer overflow／keypad IRQ 的下一個
  喚醒點，無事件直接到 frame 邊界）、PPU dirty framebuffer、視窗事件／blit。
- 分析與方案見 `docs/PERFORMANCE.md`：CPython 模型級優化（批次 device tick、
  移除 overhead、renderer 快取）→ Cython 熱路徑 → Rust/C 核心；RL 用 process
  pool。`tools/bench.py` 可重跑量測。

## 架構決策：同源 Cython（2026-11-01）

- 結論：不再把全部模擬放在 CPython；但也不再建平行 native 實作。`bus/`、`cpu/`、
  `video/` 是唯一來源，熱路徑以**同模組 Cython 編譯**（`.pxd`／必要時 `.pyx`，
  檔名與 API 不變）；沒有編譯平台自動 fallback 到 `.py`。
- 先前 `native/bus.pyx`、`setup_native.py`、`tools/gen_opcodes.py` 的實驗已移除
  （它們造成兩份 bus／兩套語意）；`native/` 目錄不再存在。
- 文件：`docs/architecture/NATIVE_CORE.md`、`docs/architecture/ARCHITECTURE.md`、
  `docs/architecture/PERFORMANCE.md`。
- 使用者定案約束：Python facade（Emulator/GBAEnv/MemoryView/VideoView）保留；
  Cython 化順序 CPU→bus→PPU→DMA/timer/IRQ；registers 用 C array、RAM/VRAM 用
  `unsigned char[::1]`、Palette `unsigned short[::1]`；opcode table 生成檔放
  `cpu/`；批次 `run_frames(n, ...)`；build flags 只套在已驗證熱模組，另留 debug
  build。不把 300 fps 當現階段 gate。
- 下一步：從 `cpu/` 開始加 `.pxd`／Cython 編譯同名模組，保持同一套 tests＋
  differential；benchmark 用 `tools/bench.py`。

## 繪圖加速（2026-11-01）

- 量測：2 render frames 的 cProfile 顯示 `render_frame` 1.44s、`_text_bg_pixel`
  307,200 calls、`ppu.read_reg16` 614,424 calls、`vram.read_u8` 391,350 calls。
  瓶頸是每個 pixel 回頭呼叫 PPU/VRAM/Palette Python method，以及每 pixel list+sort。
- 架構文件已更新：`docs/architecture/ARCHITECTURE.md`（render pipeline）、
  `docs/architecture/NATIVE_CORE.md`（renderer 同源 Cython 設計）、
  `docs/architecture/PERFORMANCE.md`（A2 renderer 專項）。
- ✅ 已完成（只改 `video/renderer.py`）：`_RenderState` frame cache（BG descriptors／
  palette LUT／active OAM／window/blend）、固定 priority bucket、fade LUT、
  直接索引 bytearray、text BG tile-row buffer（`_text_buffer`）、單一 text BG
  的 palette RGB LUT＋`b"".join` fast path（`_blit_single_text`）。render
  3.3 → 23.2 fps（60 frames），無 render 約 38 fps。
- 待做：
  1. 多層 BG／sprites／window 的一般情況仍未走 fast path。
  2. RL observation 直接輸出 resize 解析度；GUI 每 N frame render。
  3. 仍不足才把 `video/renderer.py` 同模組 Cython 化；Python renderer 保留 differential。
  4. 用 `tools/bench.py --render` 前後比較。
- 已知：GUI 仍可用 dirty framebuffer（靜態畫面不重繪）；RL 只 render frame_skip 最後一格。

## 責任分工決策（2026-11-01）

- Python（CPython）：Emulator/GbaApp/GBAEnv/MemoryView/VideoView、CLI、config、
  input、snapshot header/CRC、HLE rare path、debug、UI、process pool。
- Cython（同模組編譯）：CPU fetch/decode/execute、bus read/write、PPU timing＋
  renderer、DMA/timer/IRQ scheduler、audio FIFO 熱路徑。
- numpy：只做 RL observation（灰階/resize）、測試/benchmark、可選離線 renderer
  實驗；**不進 PPU deterministic core**，理由見 `docs/architecture/ARCHITECTURE.md`
  「責任分工」與 `PERFORMANCE.md` A3。

## PyBoy 對照（2026-11-01）

- PyBoy：`PyBoy.tick()` → `MB.tick()`（Cython 核心）→ `CPU.tick(target)` 在 C
  層跑到 cycle target → timer/LCD/sound tick → plugins post_tick。
- 對應：`GbaApp/GBAEnv` → `Emulator`／Cython core → CPU `run_until` → PPU/
  timers/sound；opcode 生成器對應 `cpu/opcode_tables.pyx`；plugins 對應 RL/UI/debug。
- 關鍵修正：不能只把各模組分別 Cython 化；CPU→bus 必須走 shared `.pxd`／
  `cimport` 的 cdef 方法（或同一個 Cython core），否則每 instruction 仍跨
  Python/C 邊界。
- 文件：`docs/architecture/ARCHITECTURE.md`、`NATIVE_CORE.md`、`PERFORMANCE.md`
  已加入 PyBoy 對照與熱路徑邊界。

## 視窗啟動修正（2026-11-01）

- 問題：以非 venv 的 Python 執行 `main.py`，或 pygame 安裝不完整（No module
  named 'pygame.base'）時，`GbaApp` 靜默 fallback headless，看不到畫面。
- `main.py`：偵測 repo 的 `venv`，若不是用 venv Python 則 `os.execv` 重新以
  venv 執行（`GBAEMU_NO_REEXEC=1` 可關閉）。
- `GbaApp._init_window`：視窗模式失敗時不再靜默 headless，改 raise
  `GbaEmuError`，訊息包含安裝 `pygame-ce` 的指令與 `window="null"` 選項；
  `GBAEMU_ALLOW_HEADLESS=1` 才保留舊 fallback。
- `pyproject.toml` 的 `[ui]` extra 改為 `pygame-ce>=2.5`（free-threaded 3.14
  需要 pygame-ce，不是舊 pygame）。

## 圖形修正：OBJ sprite tiles（2026-11-01）

- 症狀：Dr. Mario 標題畫面中央／底部出現重複方塊、綠色亂碼；BG 單獨渲染正常。
- 原因：sprite 不是單一 8x8 tile；原 renderer 對整個 sprite 只取 tile 0。
  - 一個 sprite 由多個 8x8 tile 組成（`tile + row*(w//8) + col`，1D）。
  - 2D mapping 的 tile 編號列距是 32（4bpp）／16（8bpp）× step，不是 sprite 寬度。
  - 8bpp tile 編號 step=2，位址用 `tile & 0x3FE` 後 `*32`。
- 另外把 sprite 改成 per-sprite 覆蓋範圍的 layer buffer，不再每 pixel 掃 128 OAM。
- 驗證：重跑 Dr. Mario 標題畫面可看到正確的 PRESS START／版權文字；
  `pytest tests -q → 440 passed, 4 skipped`。

## 標題畫面 CPU-bound（2026-11-02）

- 到 Dr. Mario 標題（frame ~1065）：render=False 2.54 fps、render=True 2.45 fps；
  CPU 15,764 instructions/frame、5 個 VBlank IRQ；熱門 PC 在 IWRAM
  `0x03003108–0x03003168` 重複 448 次（軟體混音／動畫迴圈）。
- 結論：這個畫面不是 renderer 瓶頸，而是純 Python CPU 執行遊戲軟體迴圈；
  要可玩速度必須 Cython 化 CPU（需要 `.pyx`／`.pxd` 或編譯既有模組的 build 設定）。
- 已做的純 Python CPU 小優化：IRQ line 快取（`IoRegisters.irq_line`），
  移除 `check_irq` 每 instruction 的 IME/IE/IF peek；title 2.28 → 2.54 fps。

## M1 CPU fast core（2026-11-02）

- 新增 `cpu/core.pyx`：typed ARM fast path（data processing／MUL/MLA／
  LDR-STR word-byte／B/BL），不支援的指令 fallback 到 Python core。
- `Arm7Tdmi` 優先使用 FastCore；沒有 `.pyd` 時仍用純 Python。
- Dr. Mario 標題：2.54 → 約 3.6 fps；畫面正確；440 tests pass。
- M2（2026-11-02）：已加 halfword／signed transfer、LDM/STM、BX、SWI、
  long multiply；block runner 已實作但默認停用（逐指令 sync 比 Python 慢）。
  MRS/MSR、exception/IRQ 仍由 Python core fallback。
- 實測 M2 沒有再提升速度（約 2.4–3.6 fps）；主成本是每條 instruction 都回
  Python step／sync。下一步 M4：FastCore 持久 C 狀態，一次跑 block，只在
  fallback／frame 邊界同步；之後才做 M3 Thumb。

## M4 結果（2026-11-02）

- 實作 FastCore 持久 C 狀態＋block runner；block 版實測約 2.0 fps，
  比純 Python 2.5 fps 更慢。
- 原因：每條 instruction 仍呼叫 Python `_arm_cycles()`、bus read/write；
  block 期間 device tick 延後，狀態成本反而增加。
- FastCore 改為 opt-in（`GBAEMU_FAST_CORE=1`），默認關閉；保留程式碼作後續
  C-level bus 整合的基礎。
- 結論：要可玩速度必須做 C-level bus／timing 的完整 native core，而不是只
  加速 CPU instruction。

## HLE BIOS 完善（2026-11-02）

- 方向：production 不依賴真實 BIOS；HLE 是 canonical 啟動路徑。
- 必須完成：post-boot state、SWI 0x00–0x2A（含 SoundDriver 文件化功能）、
  HLE IRQ return、BIOS 讀取保護、無 BIOS ROM smoke。
- `REQUIRE_BIOS` 僅保留 legacy／optional differential，不進 CI、不進 wheel。
- 測試：post-boot hash、SWI 參數／回傳逐 byte、IRQ return、header copy、
  strict／lenient 未支援 SWI。
- 文件：`docs/spec/SPEC.md` 2.1.4、`docs/guides/REVERSE_ENGINEERING.md`、
  `docs/architecture/NATIVE_CORE.md` 已改為 HLE canonical。

## Rust 搬遷（G0，2026-11-02）

- 保留舊 Python 實作；Rust core 只建立 skeleton，默認仍用 Python backend。
- `crates/gbaemu-core/`：`Core`／`CoreConfig`／`CpuState`／frame 常數／ROM header 驗證；
  `run_frame()` 明確回傳 `NotImplemented`，不假裝可執行。
- `cargo test` 4 passed；沒有改動或刪除任何 Python 模組。
- 規則與 G0–G8 gates：`docs/architecture/MIGRATION.md`。
- G1 進度：Rust `bus.rs` 完成 memory map／mirror／read-write；`cpu.rs` 已覆蓋
  ARM data processing／MUL/MLA／LDR-STR（含 register offset）／halfword／
  SWP／PSR／LDM-STM／long multiply／B-BL-BX／SWI trap，以及 Thumb format
  1–15、17、19；`cargo test` 27 passed。
- 已完成：mode banking、exception entry/return、IRQ boundary、FIQ r8-r12 bank。
- G1 differential：`crates/gbaemu-core/src/bin/cpu_probe.rs`＋
  `tools/rust_cpu_diff.py`；ARM/Thumb/IRQ/FIQ/SVC/SWI Div-Sqrt 共 16 cases 全過。
- Rust HLE 已實作 Div/DivArm、Sqrt、CpuSet、CpuFastSet、Halt/Stop、
  IntrWait/VBlankIntrWait、CustomHalt、SoundBias、LZ77（Wram/Vram）、
  RL（Wram/Vram）、BitUnPack、Diff8／Diff16、SoundBias（0x19）、
  BgAffineSet／ObjAffineSet、Huffman、GetBiosChecksum、MidiKey2Freq；
  其他 SWI 回 `HleUnsupported`。
- Cycle：Rust step 回傳的 cycle 已與 Python reference 對齊（ARM load/store／
  branch／LDM-STM、Thumb load-store／push-pop／BL）；differential 23 CPU cases
  含 cycle／halted 比對全過；另加 BitUnPack／Diff8／Diff16／BgAffineSet
  （Huffman 尚未有 differential case）。
- Bus：Rust `access_cost` 已對齊 Python `bus.access.access_cycles`（WS0/WS1/WS2、
  EWRAM、SRAM、Palette/VRAM、128 KiB boundary）；differential 11 bus checks 全過。
- Bus：`video_wait` 已實作（scanline/HBlank/DISPCNT forced blank/HBlank free），
  有 unit tests；open bus 仍是固定近似。
- Rust 已有 `arm_cycles`（fetch／access／LDM-STM／MUL／LDR-STR／halfword／
  SWP／data processing）與 7 個 cycle-model differential cases，全部對齊 Python
  `_arm_cycles`（functional timing）。
- `Cpu::step` 已在 non-functional bus 時使用 `arm_cycles`／`thumb_cycles`；
  ARM 4 個、Thumb 2 個 timed differential cases 全過。
- `Core::run_frame` 已有 frame-loop 骨架，`Core::step` 會 `bus.tick(cost)`。
- Rust PPU timing 最小模型：VCOUNT／DISPSTAT／HBlank／VBlank／IRQ flags；
  尚未接 renderer／DMA／window。
- Rust framebuffer：`Core::framebuffer()`；已做 Mode 3 bitmap、Mode 0 BG0–3
  text BG（4bpp/8bpp、scroll、tile flips、priority）與 forced blank。
- Rust BG：Mode 0/1/2 text BG 與 affine BG2/3；Mode 3 bitmap。
- Rust sprites：regular／affine OBJ 已與 BG 合成。
- Rust window：WIN0/WIN1/WINOUT mask；alpha/fade blend（BLDCNT/BLDALPHA/BLDY）
  已接；mosaic 尚未接。
- Rust mosaic：BG/affine BG 與 sprite mosaic 已接（MOSAIC 0x04C、BGxCNT bit6、
  OBJ attr0 bit12）。
- Rust open bus：fetch32 更新最後 instruction word；未映射讀取依 byte lane 回傳。
  這是近似，Python reference 仍是固定 0，尚未納入 differential。
- 尚未完成：open bus parity、backend adapter、frame-loop 與 renderer 完整驗收。
- 下一步：backend adapter（PyO3 或 file-based bridge）或先讓 Python reference
  更新成相同 open-bus 語意。
- G1 全綠前不切默認 backend。

## RetroRegen「EWRAM FAST?」修正（2026-11-02）

- **現象**：`rom/RetroRegen-GBA-Test-v1.5.gba` → SYSTEM STATUS 的
  `BUS TIMING CYC/256 READS:` 顯示 IWRAM 834 OK、EWRAM 834 **FAST?**、ROM 834 OK。
- **根因**：Rust `Bus` 的 `functional` 預設是 `true`，而 `Core::new()` 從來沒有
  用 config 覆寫它 → native backend（GUI 預設）所有記憶體存取都是 1 cycle，
  EWRAM（16-bit bus，硬體 32-bit 讀 6 cycles）同 IWRAM 一樣快。
- **修正**：`CoreConfig` 新增 `functional: bool`（預設 `false`），`Core::new()`
  設 `bus.functional = config.functional`。native backend 因此用真 waitstate；
  Python reference 仍是 `TimingMode.FUNCTIONAL`（速度考量），要對照硬體 timing
  時兩邊都要明確設 timed。
- **驗證**（同一支 ROM，native）：
  - 修正前：IWRAM 834 / EWRAM 834 **FAST?** / ROM 834。
  - 修正後：IWRAM 2983 OK / EWRAM 4263 OK / ROM 4775 OK；
    差值剛好是 256×(6−1)=1280（EWRAM）與 256×(8−1)=1792（ROM），
    即 access cost IWRAM 1／EWRAM 6／ROM 8（WAITCNT=0）。
- **回歸**：suite Memory 1552/1552、Timing 1852/2020、DMA 1256/1256（不變）；
  `rust_cpu_diff` 108/108、`rust_bus_diff` 51/51、`rust_frame_diff` 15/15、
  `rust_snapshot_diff` 11/11；`cargo test` 103 passed；pytest 473 passed。
- **相關**：PSG／DMA Sound 混音改成整數運算（Rust `i32`、Python `_trunc_div`），
  兩邊 PCM 逐 byte 相同（`rust_bus_diff` 的 `sound_pcm_psg_square`、
  `sound_pcm_direct_sound_timer` 都 pass）。

## Pinball of the Dead：黑白 logo＋速度（2026-11-02）

- **現象**：`rom/Pinball_of_the_Dead.gba` 開機廠商 logo 變黑白、logo 之後整體很慢。
- **根因 1（黑白）**：`BLDCNT`（0x04000050）bit6-7 是 **2-bit 效果模式**
  （0=none、1=alpha、2=亮度增加、3=亮度減少），舊碼把它當成兩個獨立 enable
  bit（bit6=alpha、bit7=fade），而且 alpha 的 **2nd target** 誤用 bit0-5。
  Pinball 的 logo 用 `BLDCNT=0x00FF`（效果模式 3＝變暗）＋`BLDY` 做 fade；
  舊碼當成 alpha 且 `BLDALPHA=0` → 每個像素 ×0 → 全黑 → logo 黑白。
  修正：`effect = (BLDCNT >> 6) & 3`；`targets = BLDCNT & 0x3F`（1st）、
  `second_targets = (BLDCNT >> 8) & 0x3F`（2nd）；alpha 只在 effect==1，
  effect==2 變亮、effect==3 變暗（`fade_rgb555(value, BLDY, effect==2)`）。
  Python `video/renderer.py` 與 Rust `render_mode0`／`render_bitmap_mode` 同步。
- **根因 2（慢）**：Rust `sprite_pixel()` 每個 pixel 都掃 128 個 OAM entry。
  Pinball logo 畫面（BG0-2＋OBJ）實測 **21 ms/frame**（OBJ 佔 20 ms），
  native 只有 33 fps → GUI 追不上 60 fps。改成每條 scanline 只解析一次 OAM
  （`collect_line_sprites()`），pixel loop 只走幾個 candidate：
  **1.45 ms/frame**、Pinball 1200 frames 由 36 s 降到 8 s（**124 fps**）。
- **驗證**：SEGA logo 由「白底黑方塊」變成正常藍色 SEGA 商標；WOW
  Entertainment 亦為紅色正常畫面；title 合成畫面（frame 1200）正常。
  `pytest` 473 passed；`cargo test` 103 passed；differential 全綠
  （cpu 108/108、bus 51/51、frame 15/15、snapshot 11/11）。
- **測試調整**：`test_alpha_blend_bg_over_backdrop` 的 `BLDCNT` 由 `0x0061`
  改成 `0x2041`（2nd target 在 bit13），符合 GBATEK。

## Pocket Monsters LeafGreen：開場廠商畫面全黑（2026-11-05）

- **現象**：rom/Pocket Monsters_LeafGreen.gba 開場 GAME FREAK 星形 logo
  只剩黑畫面；版權字之後一路黑到 intro，title screen 亦被裁成左邊 120 px。
- **根因**：window 暫存器**次序用錯**。真機／GBATEK 係
  `0x040 WIN0H`、`0x042 WIN1H`、`0x044 WIN0V`、`0x046 WIN1V`
  （H 兩個先、V 兩個後）；舊碼當成 WIN0H/WIN0V/WIN1H/WIN1V。
  LeafGreen 開場寫 `WIN1H(0x042)=0x00F0`（全寬 0..240）、
  `WIN1V(0x046)=0x2080`（y 32..128）、`WININ=0x3F00`、`WINOUT=0`：
  舊碼把 0x042 讀成 WIN0V、0x044（=0）讀成 WIN1H → WIN1 窗變成空 →
  全畫面被 WINOUT=0 遮成黑。
- **同時修正**：`WININ` 低 6 bit 是 WIN0、bit8-13 是 WIN1（舊碼兩個窗共用
  低 6 bit，WIN1 內會拿到 `0x3F00` 這種不可能 mask）；X1/X2 高位/低位
  （X1 在 bit8-15）；GBATEK 的 `X2>240 或 X1>X2 → X2=240`、Y 軸同理。
- **驗證**：用 mGBA 0.10.5 core 做 reference（debug/repro/mgba_ref.c，
  經 GDB／軟體 renderer 直接輸出 BMP）：frame 240 的 GAME FREAK 星形 logo、
  frame 900 的 letterbox intro、frame 1800 的 title screen 都與 mGBA 一致
  （frame 240 只有 463/38400 像素差、frame 1800 只有 836 像素差，其餘為
  fade/scroll 的時間差）。native 與 Rust core 輸出的 frame 240 完全相同。
- **測試**：新增 test_window1_full_width_band（LeafGreen 的 0x042/0x046
  全寬橫帶）、test_window_x1_greater_than_x2_clamps_to_edge；
  rust_frame_diff 的 window case 改用正確的 0x044/0x042，並新增
  mode0_window1_band。pytest 475 passed；cargo test 103 passed；
  differential 全綠（cpu 108/108、bus 51/51、frame 16/16、snapshot 11/11）。
- **工具**：crates/gbaemu-core/src/bin/rom_stats.rs（逐 frame 統計＋BMP）、
  io_trace.rs（逐 instruction 監看 IO 寫入）、debug/repro/mgba_ref.c
  （mGBA reference frame dumper）。

## rates.gba：32768K 音效有雜音（2026-11-05）

- **現象**：rom/rates.gba 播 32768K 測試音（8-BIT 32K Direct Sound）時有斷音／雜音。
- **根因**：CPU 喺 **IntrWait（BIOS SWI 0x04）halt** 期間收到其他 IRQ 時，
  Rust core 的 check_irq() 直接 enter_irq() 但**冇清 halted**：CPU 卡死喺
  handler 第一條指令，直到下一個 VBlank 旗標到才意外行返。結果 timer1 IRQ
  嘅 DMA sound buffer swap 被拖到 VBlank 才做，每約 10 個 frame 就播到
  buffer 尾嘅零資料 → 約 15 ms 的斷音（約 250 Hz 方波／正弦之間有 gaps）。
- **驗證**：用 debug/repro/mgba_audio.c（mGBA 0.10.5 core + blip）做 reference，
  mGBA 的 DMA SAD 每 311,296 cycles（= 608 samples = timer1 週期）swap 一次；
  我哋之前 SAD swap 大約每 2 個 VBlank 才一次。修正後：
  - rates.gba 300 frames 的音效只剩開機最初 876 samples 靜音、2 個 startup
    jump（同 mGBA 一樣 2 個）。
  - Python reference 本身已正確（cpu/arm7tdmi.py 的 halt 分支會先
    wake + check_irq，handler 返回後再判斷 IntrWait 旗標）。
- **修正**：cpu.rs check_irq() 入 IRQ 前若 halted → 清 halted、記
  resume_halt_irq（IntrWait 時）；hle_irq_return() 後若等緊嘅旗標未到就
  恢復 halt。另加 Bus.irq_seen（sticky IRQ 旗標）令 IntrWait 唔會漏掉
  「喺 handler 入面出現又被 ack」嘅目標旗標（對齊 Python irq_seen）。
- **測試**：intr_wait_serves_other_irq_and_resumes_halt（Rust）；
  pytest 475 passed、cargo test 104 passed、differential 全綠
  （cpu 108/108、bus 51/51、frame 16/16、snapshot 11/11）。
- **診斷工具**：crates/gbaemu-core/src/bin/audio_probe.rs（WAV＋FIFO/pop/
  DMA swap 統計）、irq_probe.rs（IF/IME/IRQ 進場逐 step）、
  debug/repro/mgba_audio.c（mGBA reference WAV，96000 Hz）。
- **待補**：run_fifo_dma() 仍未套用 DMA count／repeat（SAD reload）語意
  （呢個 ROM 用 count=0→0x4000 所以未踩到）；日後要補。

## rates.gba：仍然有雜音——GUI 播放切塊漏音（2026-11-05 第二輪）

- **現象**：IntrWait 修正後再用 main.py 播 rates.gba，32768K 測試音仍然有雜音。
- **根因（今次唔係 core）**：
l/wrappers.py 每 frame 把 549 samples 的 Sound
  直接 play／queue，但 SDL_mixer 以 mixer buffer（當時 1024 samples）為混音
  單位；**chunk 唔係 buffer 整數倍時，邊界會漏音**。用 SDL 的 disk audio
  driver 擷取實際送到音效裝置的 stream 證實：32768 Hz 正弦波有 22.5% 樣本
  變成 0、每 1–2 個 buffer 就有一個大跳變（2 秒內 65 個 jump），聽起來就係
  「雜音」。之前只驗證 core PCM 同 dummy driver 的佇列長度，所以漏咗。
- **修正**：mixer 改成 uffer=512（15.6 ms）；餵入前先把 PCM 累積成
  **buffer 整數倍**的 chunk（一次最多 4 個 buffer），只在 queue 空時才送，
  pending 上限 8 個 buffer（滿了丟最舊的，避免延遲累積）。
  _resample_chunk() 改成固定輸出長度，非 32768 Hz 的裝置亦適用。
- **驗證（SDL disk driver 擷取 device stream）**：
  - 修正前：zero_frac=22.5%、jumps>4000=65（2 秒）。
  - 修正後：30 秒 jumps>4000=2（只在開機第一個 buffer 的 startup gap）、
    100–1000 Hz 佔 99.99% 能量、FFT peak 256.0 Hz，其餘頻帶 0.00%。
  - 按 A 切去 956K 模式時，device stream 同 core PCM 的波形一致（該模式
    本身係低取樣率／尖銳波形，屬 ROM 內容，唔係播放漏音）。
- **測試**：新增 tests/gbaemu/test_gui_audio.py（chunk 必為 buffer 整數倍、
  資料不漏不重複、mixer 阻塞時 pending 有上限且對齊）。

## 遊戲內存檔（電池存檔）在 native backend 不會保存（2026-11-06）

- **現象**：GUI（`main.py`）用 Rust core 玩遊戲，遊戲內「存檔」寫入的資料關掉後
  就唔見；`rom/rom.gba.sav`、`RetroRegen-...sav` 只會由 Python backend 產生。
- **根因**：Rust core 本身有 SRAM／Flash／EEPROM 備份媒體，但 PyO3 adapter
  冇匯出 save RAM，`NativeEmulator.cartridge_flush_to_disk()` 直接
  `raise NotImplementedError`，啟動時亦冇讀 `<rom>.sav`。所以存檔只留在
  core 的記憶體，關掉就消失（`GbaApp.stop()` 的 flush 被
  `except NotImplementedError` 靜靜吞掉）。
- **修正**：
  - PyO3 `NativeCore` 新增 `save_kind()`（`none`／`sram`／`flash64`／
    `flash128`／`eeprom512`／`eeprom8k`）、`save_ram()`、`load_save_ram()`；
    大小不符會拋 `ValueError`。`reset()` 會保留 battery save（真機 reset
    唔會清存檔）。
  - `NativeEmulator`：啟動時若 `<rom>.sav` 存在且大小相符就載入（否則
    warning 後忽略）；`cartridge_flush_to_disk()` 以 `.tmp` ＋ `os.replace`
    原子寫回；新增 `save_path`／`save_kind` 屬性。
  - `GbaApp.stop(save=True)` 沿用原本呼叫，現在會真正寫出 `.sav`。
- **驗證**（native vs Python `memory/savedata.py` 逐 byte 對比，全部相同）：
  - EEPROM 8 KiB（14-bit 位址）／512 B（6-bit）：`10`＋addr＋64 data＋`0`
    寫入、`11`＋addr＋`0` 讀 68 bits，來回值正確。
  - EEPROM **DMA 串流**（遊戲真正用的路徑）：DMA3 送 6-bit／14-bit 寫入框、
    68-bit 讀取 burst，core 同 reference 一致（注意 core 係喺 `step()` 開頭
    先 service pending DMA）。
  - Flash 64 KiB／128 KiB：AA/55 解鎖、`A0` program（只可 1→0）、`80`→`30`
    扇區抹除、128K bank 切換，backing store 完全相同。
  - SRAM 32 KiB mirror；`save_kind` 對五種簽章（含 `FLASH1M_V` → `flash128`）
    同 Python 一致。
  - **LeafGreen**（`rom/Pocket Monsters_LeafGreen.gba`）：兩邊都偵測為
    Flash 128 KiB；bank0/bank1 program 後 flush 出 131072 bytes `.sav`，
    重開 NativeEmulator 讀返一樣。
- **測試**：新增 `tests/gbaemu/test_native_save.py`（11 個：
  偵測、EEPROM 來回、flush/reload、reset 保留、無 save 媒體拋錯、
  Python↔native `.sav` 互通、`.sav` 大小不符忽略、Flash128 bank/erase 對比、
  `GbaApp.stop()` 寫檔）。
- **產物**：`_native.pyd` 重 build（sha256 `C9BEF3EE...4557B8`）、wheel
  `dist/gbaemu-0.1.0-cp314-cp314t-win_amd64.whl`（sha256
  `57FA8240...520756`）。
- **待補**：LeafGreen 由 title 玩到 save menu 的全自動流程測試（要大量輸入
  腳本）；現階段硬件協定同持久化已對齊 Python reference。

## 公開 GitHub repo 清理（2026-11-06）

- 移出 repo（保留在 `D:\python\gbaemu-lab\`，唔入版控）：
  `rom/`（54 MB ROM／BIOS／.sav）、`test-rom/`（jsmolka 硬體測試 ROM）、
  `debug/` 證據（mGBA C 源碼、timing log、測試截圖）、`ref_*.bmp`、
  legacy Cython `pygba/`、`tools/setup_legacy.py`、`tests/test_*.py`
  （185 個 legacy 測試）、`.vscode`。
- `gbaemu/debug/` 只保留 `breakpoints.py`（生產用）。
- `tests/reference/gba_cpu/` 改為自帶 `bios_ref.py`，唔再依賴 `pygba`。
- 新增 `rom/README.md`、重寫 `.gitignore`、`.gitattributes`（LF）；
  `main.py` 支援 `python main.py <rom>` 同友善缺 ROM 訊息；Ctrl+C 都會 flush `.sav`。
- `.git` 舊歷史（42.7 MB）備份到 lab；public repo 用新的單一 commit：
  175 files / 2.56 MB（fresh clone 實測 281 passed, 3 skipped）。
- 現行測試：`tests/gbaemu`（303 collected）＋`tests/reference`；
  legacy 測試／`pygba` 已喺 lab。
- 發佈前仍要：補 `LICENSE`、設定 GitHub remote（`git remote add origin ...`）。

## LeafGreen 開場「主角／Professor Oak」不見（BG2 affine，2026-11-06）

- **現象**：LeafGreen 開場 Oak 講解畫面只見到 Bulbasaur 同文字，畫面左邊的
  Professor Oak 完全消失（實機／mGBA 有）。
- **根因**：Oak 係用 **BG2 affine layer** 畫（唔係 OBJ）。遊戲開機執行
  SWI 0x01 RegisterRamReset（flags 0x80）重設 IO，BIOS 的復位值係
  `BG2PA=BG2PD=BG3PA=BG3PD=0x0100`（identity matrix）；我哋 HLE 將
  0x000..0x060 的 IO **全部清零**，affine matrix 變成 0 → BG2 所有 pixel
  取樣同一個 texel（透明）→ Oak 消失。mGBA `GBASwi16` case 0x01 同
  `GBAIOInit` 都係設 identity。
- **修正**：
  - `Cpu::hle_swi` case 0x01（flags 0x80）同 Python
    `hle/swi_impl.py::_register_ram_reset`：清零 IO 之後補回
    BG2/BG3 PA/PD = 0x0100。
  - `Bus::apply_post_boot`（Rust）＋`hle/postboot.py`（Python）：
    HLE 開機亦設 identity，對齊 BIOS／mGBA `GBAIOInit`。
- **驗證**：用 mGBA 0.10.5 core 跑同一輸入腳本（START@1800、之後每 60
  frames 按 A），frame 3304 與我哋輸出 **逐 pixel 相同**（mean diff 0、
  diff>30 像素 0）。修正前同一 frame 有 2286 個 pixel 差（正正係 Oak
  的剪影）。
- **測試**：`test_register_ram_reset_sets_affine_identity`（Rust＋Python，
  用 render 驗證 identity default 真係畫到 affine BG）、
  `post_boot_sets_affine_identity`（Rust）；pytest 306 passed、cargo 106 passed。

## 電池存檔：唔再「自動 save」（2026-11-06）

- **現象／要求**：只係開遊戲、冇喺遊戲入面手動存檔，關掉時都會寫
  `<rom>.sav`（甚至建立新檔）；用戶要求「不要自動 save，因為有些遊戲要
  手動 save」。
- **修正**：`NativeEmulator`／`Emulator` 新增 `battery_dirty`（同載入／上次
  寫回比較 save media bytes）。`GbaApp.stop()` 只在 dirty 時才 flush；純粹
  遊玩唔會改動／建立 `.sav`。另外新增 `GbaApp.save_battery()` 供明確寫回。
- **驗證**：Dr. Mario（EEPROM 8K）跑 60 frames 冇存檔 → `battery_dirty`
  False、`.sav` mtime／hash 完全不變；遊戲寫過 save media 後 dirty True，
  stop 會寫檔。
- **測試**：`test_gbaapp_stop_skips_sav_when_game_did_not_save`、
  `test_battery_dirty_tracks_save_writes`（native）、
  `test_python_battery_dirty_tracks_save_writes`（Python）。

## README「已知缺口」核對：OBJ window、DMA Sound repeat、SOUNDBIAS、wave RAM bank（2026-11-06）

- **背景**：用戶問 README 4 項係咪真未實作；逐項核對 code 之後，今輪補咗
  OBJ window 同 DMA Sound repeat 兩項。
- **核對結果**：
  1. **OBJ window — 之前真係冇，今輪補齊**。`window_mask()`／`_window_mask()`
     只檢查 WIN0（DISPCNT bit13）／WIN1（bit14），完全冇用 bit15 同 WINOUT
     bit8-13；Rust `collect_line_sprites()` 直接 `continue` 跳過 attr0 mode 2
     sprite，Python `_build_state()` 當普通 sprite 畫。
     修正：mode 2 sprite 收集成 window sprite（唔畫），逐 pixel 用同一 tile
     解碼；Rust `sprite_color_at()`／`obj_window_inside()`、Python
     `_obj_window_inside()`；優先次序 WIN0 > WIN1 > OBJ window > 窗外。只計
     非透明 pixel（mGBA `SPRITE_DRAW_PIXEL_*_OBJWIN` 的 `if (tileData)` 語意）。
     測試：`obj_window_uses_winout_layers`（cargo）、`test_obj_window_masks_layers`
     （pytest）、`rust_frame_diff` 新增 `mode0_obj_window_sprite`（17/17）。
  2. **DMA Sound count／repeat — 部分未實作，今輪補 repeat**。`run_fifo_dma()`／
     `_run_fifo()` 每次固定搬 16 bytes 之後無條件繼續 refill，ignore DMAxCNT_H
     bit9；結果 repeat bit clear 的 one-shot SFX 會無限重播。現在 refill 後：
     repeat clear → 清 enable＋DMA IRQ、channel inactive；repeat set → 保持
     enable。count 本身 hardware／mGBA 都係固定 4 words
     （`GBAAudioSampleFIFO` `nextCount = 4`），已對齊。
     測試：Rust `fifo_dma_without_repeat_disables_channel`／
     `fifo_dma_repeat_keeps_channel_enabled`；Python
     `test_fifo_dma_without_repeat_disables_channel`／
     `test_fifo_dma_repeat_keeps_channel_enabled`。
  3. **SOUNDBIAS／PWM — 真未實作**。`sound.rs`／`audio/sound.py` 冇讀
     `0x04000088`（SOUNDBIAS）；輸出固定 32768 Hz、sample 直接 clamp 成 s16，
     冇 9-bit PWM 載波、冇 bias（0x200）加減。影響：resolution 1/2
     （65536／131072 Hz）同 PWM 高頻細節唔跟實機；大部分遊戲用預設值，聽感
     差異細。
  4. **wave RAM bank 時序 — 真未實作**。wave RAM 有兩個 16-byte bank，我們只有
     `io[0x90..0xA0]` 一個；SOUND3CNT_L bit6 bank select、播放中 CPU 存取另一個
     bank、audio off 時的 bank 行為（mGBA `GBAAudioRead/WriteWaveRAM`）都冇。
     影響：會 bank 切換的 wave channel 音樂（少數遊戲）取樣錯誤。
  5. **timer count-up — 其實已實作**（Rust `timer_cascade`、Python
     `Timers.cascade`，有 `timer_prescaler_overflow_and_cascade` 測試）。
     README 原文「部分 timer count-up／IRQ 邊界」應理解為 count-up 已做、
     剩部分 IRQ edge。
  6. **Timing 1852/2020、BIOS/SIO 部分行為、RL process pool／trace replay —
     真未完成**，屬 accuracy／feature 範圍。
- **驗證**：`pytest tests -q` 309 passed / 1 skipped、`cargo test` 109 passed、
  `rust_frame_diff` 17/17、Dr. Mario 120 frames native vs Python hash 相同
  （`03ec38bb3bb491c5`，139.3 fps vs 6.7 fps，20.8×）、rates.gba 180 frames 有
  非靜音 PCM（max 10240）。
- **產物**：`_native.pyd`、`dist/gbaemu-0.1.0-...whl` 重 build。

## 預設 ROM 與存檔命名：唔再硬編 rom.gba、存檔用 ROM stem（2026-11-06）

- **需求**：用戶把不同遊戲輪流改名做 `rom/rom.gba`，`rom.gba.sav` 會撞；
  要求（1）預設唔再指定 `rom.gba`，改為讀 `rom/` 入面唯一的 `.gba`；
  （2）存檔跟 ROM 同名 stem：`Dr_Mario.gba` → `Dr_Mario.sav`。
- **改動**：
  - `cli.find_roms()`：列 `rom/` 入面 `*.gba`（大小寫不拘、排序）；`main.py`
    冇參數時用唯一那個，0 個／多個都給清楚錯誤（多個會列出並要求指定）。
  - `GbaApp()` 冇傳 path 時同樣用 `find_roms()`；`tools/bench.py`、
    `tools/smoke_real_rom.py` 的 `--rom` 預設改為自動偵測。
  - 存檔：`memory/savedata.py` 新增 `save_path_for()`（`<rom stem>.sav`）同
    `legacy_save_path_for()`（舊式 `<rom 全名>.sav`，只讀）。`NativeEmulator`
    ／`Emulator` 寫檔一律用 stem；載入時先試 stem，再 fallback 舊式全名，
    所以現有 `xxx.gba.sav` 唔會唔見。
- **驗證**：`Dr_Mario.gba` 跑 2 frames + flush → 目錄只有 `Dr_Mario.gba`、
  `Dr_Mario.sav`（EEPROM 8K，冇 `Dr_Mario.gba.sav`）；pytest 312 passed /
  1 skipped；`main._default_rom()` 在只有一個 `.gba` 的 rom/ 回傳它。
- **注意**：舊 `rom/rom.gba.sav` 要保留就手動改名做對應 `<game>.sav`；
  只會 fallback 讀 `<rom 全名>.sav`（例如 `Dr_Mario.gba.sav`），唔會把
  `rom.gba.sav` 當成 `Dr_Mario.gba` 的存檔。

## 100% 完成度稽核（2026-11-08）

用戶要求專案 100% 完整；授權選 MIT。以下係逐項實測（Rust core、mGBA
accounting、suite.gba）。

### suite.gba 現況

| Suite | 現況 | 未過 |
|---|---|---|
| Memory tests | 1552/1552 ✅ | 0 |
| DMA tests | 1256/1256 ✅ | 0 |
| BIOS math tests | 615/615 ✅ | 0 |
| Shifter／Carry／Multiply long／I/O read | 全綠 ✅ | 0 |
| SIO register R/W | 90/90 ✅ | 0 |
| SIO timing | 4/4 ✅ | 0 |
| **Timer count-up** | **291/936** | **645**（overflow／cascade／IRQ 的 cycle 邊界） |
| **Timer IRQ** | **65/90** | **25**（IRQ 投遞 cycle） |
| **Timing（prefetch/waitstate）** | **1852/2020** | **168**（ROM P.S／PNS／P..／PN. 等 prefetch 組合） |
| **Misc. edge case** | **6/10** | **4**（Break／Read／Start／Flip 1） |
| Video tests | 互動式（run=NULL），probe 唔跑 | 要另建 deterministic 版本 |

### 其他缺口

- 音訊：SOUNDBIAS／PWM（9-bit）未模擬；wave RAM 雙 bank（SOUND3CNT_L bit6）
  未模擬。DMA Sound FIFO repeat 已補（2026-11-06）。
- API：`Emulator.run_until()`／`NativeEmulator.run_until()` 仍然
  `NotImplementedError`；`NativeEmulator` 冇 `step_cycles()`、冇 breakpoint；
  IO raw region 讀取未支援（MIGRATION G6）。
- RL：process pool、trace replay、multi-process／snapshot／observation
  benchmark 未實作；SPEC §9 Phase 5 要求。
- CLI：SPEC §12 建議的 `run`／`trace`／`dump-memory`／`replay` 未實作
  （目前只有 `inspect-rom`）。
- 發佈：LICENSE 已補 MIT；README 仍寫「約 90%」，要改成完成度矩陣；
  MIGRATION G8（刪除舊檔）實際已完成但表上仍 ⬜。
- 測試：`hello_rom_path` 因外部 `test-rom/ppu/hello.gba` 而 skip 1 項
  （設計如此，唔算缺陷）。

### 完成順序（用戶指定：硬件 → 功能 → 文件）

1. Timer count-up／Timer IRQ：改成 event-accurate overflow／IRQ scheduling
   （overflow 喺 exact cycle、cascade 即刻傳播、IRQ 帶 cyclesLate），再逐個
   config 校準。
2. Timing prefetch model：8 種 P.S／PNS／P..／PN.／.N.／..S 組合。
3. Misc edge case、Video deterministic 測試。
4. SOUNDBIAS／PWM＋wave RAM bank。
5. API（run_until／step_cycles／breakpoint）＋CLI＋RL pool／trace replay／
   benchmarks。
6. README／MIGRATION／packaging 收尾，全測試＋real-ROM smoke。

## 100% 進度 round 1（2026-11-08）：Timer 校準實驗＋BIOS SWI 修正

- **Timer 校準實驗**（Rust core、mGBA accounting）：
  - `irq_wait=4`：Timer count-up 276/936、Timer IRQ 59/90（更差）。
  - `irq_wait=6`：Timer count-up 只跑 468 total／69 passes（測試中途停，大壞）。
  - `irq_wait=5`（保留）：291/936、65/90。
  - Timer 32-bit start offset `0`（原本 2）：count-up 仍然 291、Timer IRQ
    3/90、Timing 1832/2020（大壞）。
  - 結論：現有 `irq_wait=5`＋wide-write offset 2 係局部最優，唔係 timer
    缺口主因。
- **讀 mGBA `src/gba/bios.c::GBASwi16` 發現兩個真 bug（已修 Rust＋Python）**：
  1. `biosStall < 18` 時 mGBA 會先加 `stall`，再行正常「45 + SWI# 讀取 +
     return」路徑；我們之前只加 `stall`（細 stall 的 SWI 少計 ~50 cycles）。
  2. `_ArcTan2` 除 x==0／y==0 之外，所有象限都會經 `_ArcTan` 多項式；
     我們之前一半分支直接回 11。
  - 測試：Rust `arctan2_nonzero_arguments_use_arctan`、Python
    `test_arctan2_stall_uses_arctan_in_all_quadrants`。
- **試過但 revert**：把 `mgba_data_cost`／`mgba_store_cost` 改成所有 data
  load/store 都經 `GBAMemoryStall`（mGBA 原碼係咁），Timing 由 1852 跌到
  1756；証明我哋 `access_cost`（+1 公約）同 prefetch 狀態未同 mGBA 完全
  等價，唔可以逐句硬搬。
- **下一步（round 2）**：Timer 645 項失敗唔係單一常數，係 CPU 指令週期
  （尤其 ROM prefetch 8 種組合）同 timer overflow／IRQ 的 sub-instruction
  對齊。要實作 event-accurate timer／IRQ scheduler（overflow 排喺 exact
  cycle、cascade 同 cycle 傳播、IRQ 帶 cyclesLate）＋prefetch 狀態機，
  唔再調常數。
- **回歸**：pytest 313 passed / 1 skipped、cargo 110 passed；suite 分數
  Memory 1552、DMA 1256、SIO 90+4、Timing 1852、Timer 291+65、Misc 6/10。

## 100% 進度 round 2（2026-11-08）：run_until（Python＋native）＋prefetch 診斷

- **實作 `Emulator.run_until()`**：逐指令執行、每步 poll event stream，支援
  全部 `EventKind`；回傳 `StepResult`（`cycles_executed`／`events`），唔會
  超出 `max_cycles`。
  - 測試：`test_run_until_vblank_start`、`test_run_until_frame_boundary`、
    `test_run_until_validates_arguments`。
- **實作 `NativeEmulator.run_until()`**：
  - Rust core 新增 PyO3 `in_hblank()`、`ppu_cycles()`、`ppu_frame_index()`
    （單步時 core 的 `frame_index` 唔會更新，要用 PPU 自己的 counter）。
  - 以可觀測狀態邊緣偵測：FRAME_BOUNDARY／VBLANK_START／VBLANK_END／
    HBLANK／IRQ／HALT／TIMER_OVERFLOW／DMA_COMPLETE；未支援 kind 明確
    `NotImplementedError`。
  - 測試：`test_native_run_until_vblank_and_frame`、
    `test_native_run_until_rejects_unsupported`。
- **prefetch 診斷（無改 code）**：讀 mGBA `memory.c` 確認 `GBALoad*` 真係
  `if (address < BASE_CART0)` 才叫 `GBAMemoryStall`，同我哋現有 gate 一致；
  之前「所有 load 都 stall」實驗（Timing 1852→1756）證實係錯方向，已 revert。
  Timing 168 項失敗集中喺 prefetch-on 的 multiply／LDM，delta 全負（-1..-7），
  判斷係 `lastPrefetchedPc`／maxLoads 狀態同 mGBA 未完全一致，留待 prefetch
  狀態機重寫。
- **回歸**：pytest **318 passed / 1 skipped**（`test_unimplemented_phases_are_explicit`
  已更新為 run_until 可用）、cargo 110 passed；suite 分數不變。

## 100% 進度 round 3（2026-11-08）：CLI 四個命令＋LDM 診斷

- **實作 SPEC §12 CLI**（`cli.py`）：
  - `run ROM --frames N [--no-video] [--json]`：headless 執行，輸出
    `cycles`／`frame_index`／`halted`／`state_hash`。
  - `dump-memory ROM --address 0x… --size N [--frames] [--json]`：hex 或
    JSON dump（經 `memory.read_u8`，可讀任意位址）。
  - `trace ROM --from ADDR --cycles N`：JSONL，每行 `{"pc","cpsr","cycles"}`。
  - `replay ROM --input inputs.jsonl [--frames]`：讀
    `{"frame": n, "buttons": [...]}`，輸出最終 `state_hash`。
  - 測試：`test_cli_run_frames_json`、`test_cli_dump_memory_json`、
    `test_cli_trace_jsonl`、`test_cli_replay_input`。
- **Timing 診斷**：試過 cross-region LDM 都套 `GBAMemoryStall` →
  Timing 1832/2020（-20），已 revert。確認 168 項失敗集中喺 prefetch-on
  的 `lastPrefetchedPc`／maxLoads 狀態，暫停盲調常數。
- **回歸**：pytest **322 passed / 1 skipped**、cargo 110 passed；suite 分數
  Memory 1552、DMA 1256、SIO 90+4、Timing 1852、Timer 291+65、Misc 6/10。
- **下一步**：prefetch 狀態機重寫（跟 mGBA `lastPrefetchedPc` 更新時序），
  或先做 audio wave RAM bank／SOUNDBIAS。

## 100% 進度 round 4（2026-11-08）：mGBA cycle oracle＋LDM stall gate 真 bug

- **新增兩個診斷工具**（可重現的 mGBA 對照）：
  - `crates/gbaemu-core/src/bin/cycle_probe.rs`：
    `cargo run --release --bin cycle_probe -- ROM STEPS WAITCNT`，逐條
    instruction 印 `pc`／cycle delta。
  - `tools/mgba_cycle.c`：同一支 ROM 用 libmgba 單步，print mGBA 的
    `pc`／`cpu->cycles` delta（build 指令見檔案頂部）。兩邊對同一 WAITCNT
    比對，可以精確定位公式差異。
- **用 harness 找到並修正真 bug（LDM/STM stall gate）**：
  - mGBA `GBALoadMultiple` 的 `GBAMemoryStall` gate 用 **loop 之後的
    address**（`start + count*4`，未減 writeback），唔係 start。
  - 例：`ldmia r0!, {r3-r7}`（r0=0x07FFFFEC）跑完 address = 0x08000000
    → mGBA **唔會** absorb prefetch；我哋舊 code 用 start gate → 錯誤 absorb。
    修正前 cycle_probe LDM = 4，mGBA = 13；修正後兩邊都 13（WAITCNT 0x4010），
    0x0000 兩邊都 14。
  - Rust `mgba_multiple_cost`／Python `_mgba_multiple_cost` 同步修正；
    新增 Rust 測試 `ldm_stall_gate_uses_post_increment_address`。
  - suite 分數今輪未變（1852），但呢個 gate 係概念性錯誤，已由 mGBA oracle
    驗證。
- **微基準對照結果**：LDR／LDM／ADD／branch 喺 WAITCNT 0x0000 與 0x4010
  下同 mGBA 完全一致；boot 後第一條 branch 仍有差異（mGBA HLE BIOS 預熱
  prefetch，我哋冷啟動），但 suite 有 calibration 抵消。
- **回歸**：pytest **322 passed / 1 skipped**、cargo **111 passed**。
- **下一步**：用同一 harness 逐個失敗類別（multiply 不同 Rs、LDM 不同
  count／address、Thumb）對 mGBA 校準，直到 Timing 168 項收窄；再套用到
  Timer suite。

## 100% 進度 round 5（2026-11-08）：Timing 測量機制拆解＋oracle 擴充

- **重要發現（Timing suite 係用 TIMER0 量）**：`include/macros.s` 的
  `START` 係 `str r1,[TM0CNT]`（32-bit，0x00800000 = enable、prescaler 1）、
  `END` 係 `ldrh r2,[TM0CNT_LO]` 再停 timer；最後減 `calibrate` 的同一
  START/END 讀數。即 **Timing 分數同時取決於 timer 啟動／讀取／停止的
  cycle 邊界**，同 Timer suite 共享同一個根因。
- **oracle 擴充**：`tools/mgba_cycle.c` 同 `cycle_probe` 都加咗 optional
  `read_addr`，跑完 steps 用 `GBALoad32`／`bus.read32` 讀回測試 ROM 寫入
  的 timer 值，方便逐個 micro-test 對照。
- **合成 ROM 的 mGBA boot 陷阱**：用 0x20000 bytes、header 首 0x100 自製的
  ROM，mGBA 有時會當成 multiboot（PC 落 0x02000000、讀錯 literal），
  量到嘅 timer 值不可信；要用 suite.gba 級 header（Nintendo logo＋checksum）
  或直接用 suite ROM 的 test harness，先至可比。已記錄，下一輪會用
  `suite.gba` header 或 patch suite ROM 方式做 micro-test。
- **回歸**：pytest 322 passed / 1 skipped、cargo 111 passed；suite 分數不變
  （Timing 1852、Timer 291+65）。
- **下一步**：用 suite 的 `TEST_ALL`／`START`／`END` 精確複製一個失敗
  config 的 micro-test（掛在 suite.gba header 下），量我們同 expected 的
  timer 值差異；再分辨係 CPU 指令週期定 timer start/read/stop 邊界造成。

## 100% 進度 round 6（2026-11-08）：micro-test 重現 suite「Got 4 vs 6」

- **新增 `tools/gen_timing_rom.py`**：直接照 suite `include/macros.s` 的
  START／CODE／END 產生最小 ROM：
  - START：`ldr r0,=TM0CNT`、`ldr r1,=0x00800000`、`str r1,[r0]`
  - CODE：`--code` 指定的 ARM 指令（可重複）
  - END：`ldrh r2,[r0]`、`strh r1,[r0,#2]`、把 r2 寫去 EWRAM 0x02000000
  - 用 `cargo run --release --bin cycle_probe -- build/cal_mul.gba 30 4010 02000000`
    讀返 timer 值。
- **成功重現 suite 的具體失敗**：`mul r3,r2`（Rs=r2=0xFF），WAITCNT 0x4010：
  - 我們：cal_empty = **2**、cal_mul = **6** → delta **4**
  - suite expected：**6**（即 delta 6）→ 同 suite2.txt 入面
    `ARM/ROM P.S: Got 4 vs 6: FAIL` 完全一致。
  - 即係 micro-test 已經可以獨立重現 Timing 失敗，唔需要再跑整個 suite。
- **已試但 revert**：把 MUL/MLA 的 mgba cycle 一律 +2（假設 hardware MUL
  係 6）→ Timing 由 1852 大跌到 **1654**；証明唔係全域 MUL 偏移，差異係
  某啲 config／測量窗口（START 之後的 nonseq refill、post-body delta 落在
  window 內外）造成。
- **下一步**：用同一 generator 做受控實驗：
  1. CODE = `nop` × N，確認 delta 是否等於 N×4；
  2. CODE = `mul` 前後加 `nop`，睇 +2 係出現在 mul 本身定 START/END 邊界；
  3. 比較 P..／P.S／PNS 三種 config 的 delta，判定 post-body delta（N-S）
     在 hardware 係計入 store 還是下一條 fetch。
- **回歸**：pytest 322 / 1 skipped、cargo 111；suite 分數不變。

## 100% 進度 round 7（2026-11-08）：MUL prefetch 吸收差 1 cycle 的實證

- **修正 micro-test 編碼錯誤**：suite 的 `mul r3, r2`（兩 operand）實際係
  `Rd=r3, Rs=r3, Rm=r2`（0xE0030392），即 wait 取決於 **r3 的值**，唔係
  r2=0xFF。之前用 0xE0030293（Rs=r2）令所有 test 都當 wait=1。
- **量到精確 delta 表**（`gen_timing_rom.py --value …` + cycle_probe）：
  | WAITCNT | 我們 delta | suite expected |
  |---|---|---|
  | 0000 | 12 | 12 ✅ |
  | 4000（P..） | 6 | 6 ✅ |
  | 4010（P.S） | 4 | **5** ❌ |
  | 4014（PNS） | 4 | **5** ❌ |
  - P.S／PNS 下 **只有 wait=4**（Rs=0x12345678）差 1；wait=1/2/3
    （0xFF000000／0xFFFF0000／0xFFFFFF00／0x5678）兩邊都係 4。
  - 即 hardware/expected 喺 prefetch + seq16=1 + wait=4 嘅情況，MUL 比
    mGBA 公式多 1 cycle；我哋完全跟 mGBA，所以齊齊少 1。
- **推論**：`GBAMemoryStall` 對 MUL 的 prefetch 吸收喺 `s=1、wait=4` 時
  多扣咗 1（mGBA `n2s`/`stall-1` 組合 vs 硬件行為）；可能需要將 MUL 的
  internal wait 同 memory stall 分開處理（internal cycles 唔應該被
  prefetch buffer 吸收）。
- **下一步**：
  1. 用同一 micro-test 量 long multiply（SMLAL/UMLAL wait=2/1）同 MLA，
     對 expected 表印證「internal vs memory stall 分開」假設；
  2. 計出 internal cycles 公式（暫見 `max(0, wait-3)` 喺 P.S 成立），
     再喺 Rust/Python 兩邊分開 `internal + stall(memory)` 實作；
  3. suite 2/3 驗證，目標把 multiply cluster（約 50 項）清零。

## 100% 進度 round 8（2026-11-08）：multiply internal wait 修正（Timing 1852→1930）

- **根因**：mGBA 將 multiply 的 internal wait 直接餵入 `GBAMemoryStall`；
  prefetch buffer 會錯誤吸收呢啲 internal cycles（唔應該 absorb）。
- **micro-test 反推公式**（只用 prefetch 開啟時）：
  - ARM MUL / MLA / long multiply：
    `extra = max(0, wait - activeSeqCycles32)`
  - Thumb MUL（16-bit 觀測窗）：
    `extra = max(0, wait - activeSeqCycles16)`
- **實作**：
  - Rust：`arm_cycles_mgba` 的 MUL/MLA、long multiply 分支；
    `thumb_cycles_mgba` 的 MUL 分支。
  - Python：`cycles.py` 新增 `_mgba_mul_internal()`／
    `_mgba_mul_internal_thumb()`，三個 multiply 分支同步。
- **結果**：Timing **1852 → 1914（ARM +62）→ 1930（Thumb +16）**；
  `tools/mgba_cost_diff.py` **130 cases 0 mismatch**（Python/Rust 同步）；
  pytest 322/1、cargo 111；Timer suite 不變（291/936、65/90）。
- **餘下 90 項**：
  - BIOS math 32（ArcTan／Division／Division 2／Sqrt 2／Sqrt／Sqrt 3）
  - LDM/STM 約 36（`sp`／IWRAM 同 `0x07FFFFF4-FFEC` overflow）
  - `ldr/ldrh [sp]` 等 12、其他 10。
- **下一步**：用同一 micro-test 方法攻 LDM/STM（sp 同 overflow 兩個 cluster），
  再重新校準 BIOS SWI profile（32 項）。

## 100% 進度 round 9（2026-11-08）：LDM/STM internal cycles（Timing 1930→1944）

- **根因**：同 multiply 一樣，LDM/STM 每 register 的 transfer cycles 被
  prefetch buffer 吸收；`GBAMemoryStall` 只計 memory wait，硬件仍然要
  付 internal cycle。只喺 prefetch 開啟、且 data address < 0x08000000
  （IWRAM/EWRAM）時出現。
- **公式（實測 suite Timing 反推）**：
  - LDM：`extra = max(0, count - 2 * seq16)`
  - STM：`extra = max(0, count - 2 * seq16 - 1)`
  - `seq16 = access_cost(pc, 2, seq) - 1`（code region 的 16-bit seq wait）
- **實作**：Rust `Cpu::mgba_multiple_cost` 同 Python `cycles.py`
  `_mgba_multiple_cost` 同步。
- **結果**：Timing **1930 → 1944**（fail 90 → 76）。
- **已排除**：
  - 曾試 `count-2`／`count-3` 定額：1936，但 `P..`/`PN.` 的
    `ldmia sp,{r2-r7}` 會多 2-4、`0x07FFFFEC` 更差，已棄用。
  - 曾試將 `0x07FFFFEC`（OAM 以外 open bus）當 0 wait：EC 的
    `...`/`.N.` 由 pass 變 fail（expected 14/13 而唔係 7），已棄用。
- **餘下 76 項**（suite 2）：
  - BIOS math 36（Division 8、Division 2 8、Sqrt 2、Sqrt 2 8、
    Sqrt 3 2、ArcTan 8）——全部 ROM config，got 比 expected 多 3-8。
  - overflow LDM/STM 20（`0x07FFFFF4/F8/FC` prefetch-on +1；
    `0x07FFFFEC` prefetch-on 15 vs 7）。
  - Thumb `ldrh/ldr [sp]` 10（P.S/PNS 少 1-2）。
  - `ldmia sp,{r2-r7} x2` P.S/PNS 2（17 vs 16）。
- **下一步**：先攻 BIOS SWI profile（36 項，公式集中），再處理溢位
  cluster；Thumb [sp] 可能同 16-bit delta 有關。

## 100% 進度 round 9b：Timer count-up suite 解碼（291/936）

- **test 結構**（`mgba_suite_src/src/timers.c`）：`timer` u32 = 
  low16 = TM0 reload、high16 = TM0CNT_H；高 byte 0xC0 = enable|IRQ，
  低 2 bits = prescaler（0b=1、6b=64、8b=256、10b=1024），test 名
  的 `0x00xx` 係 reload 差。
- **量度**：timer0 重載後，tight loop（`add; ldr r2,[r4]; tst; bne`）
  同 loose loop（16 個 add）跑到 IRQ handler 將 timer 停為止；
  `1xs`/`16xs` 係 loop iteration 總和，`1xv`/`16xv` 係停機時
  TM0CNT_L 值。
- **判斷**：呢個 suite 其實係 **timer IRQ latency + IO read timing**
  測試，唔係 cascade 邏輯；`irq_wait`、IO read 週期、Halt 行為
  任何一項差少少都會令 loop count 偏移。26 tests × 36 = 936。
- **現況**：291/936；錯法多數係 ±1 或 ×2（16xs 特別明顯），
  表示 IRQ 服務時序同硬件仍有系統性偏差。
- **下一步**：先用 `irq_probe` 量 IRQ latency（timer overflow →
  handler first instruction），再同 mGBA 對照；預期修好後
  Timing 的 `ldr [sp]`/BIOS 亦可能同時受益。

## 100% 進度 round 9c：BIOS SWI／Timer IRQ 診斷（未落地）

### BIOS math（suite 2，36 項）根因排除過程

- 用 `GBAEMU_SWI_DEBUG` 印出 `mgba_swi_cycles` 的 total 後發現：
  - `sqrt(0)`（`...` ARM ROM）total=114，量測 150（pass）；
  - `sqrt(0xFF)`（Sqrt 2）total=229，量測 272（+7）；
  - `arctan(0xFF)` total=114，量測 157（+7）。
- 即 **SWI 本身成本同 mGBA 一致**（stall 53／168 都同 mGBA
  `_Sqrt`／`_ArcTan` 手算相符），+7 係嚟自 window 內其他
  instruction。
- 對照 `mov r0,#0x0`（Sqrt，pass）同 `mov r0,#0xFF`
  （Sqrt 2／ArcTan，+7）：唯一差別係 immediate，但
  `cycle_probe` 對住同一個 block 量到**完全相同**嘅
  per-instruction cost（兩者都係 17/17/17/13/9/6）。
- **結論（假設）**：+7 係 measured window 入口的
  **prefetch state** 差異：兩個 test function 放喺 ROM
  不同 alignment，entry 前的 `push`／`bl` 路徑令
  prefetch buffer 狀態唔同；硬件 prefetch buffer 會蓋過
  6 條 instruction 的 window，所以 expected 兩者同值。
  要修就要令 branch/entry 後的 prefetch state 同硬件一致
  （refill 後 buffer 內容／last PC 模型），屬 timing 底層。
- **下一步**：用 `mgba_cycle.c` 對同一 suite 的 function
  前後做 per-instruction 對照，確認 branch 後 prefetch
  refill 的 first-instruction cost。

### Timer IRQ（suite 4，65/90）讀值 +1

- `timer-irq.c` 流程：32-bit 寫 `0xC0FFFF` 啟動 timer0
  （reload FFFF）→ `strh` 寫 reload 0 → `ldrh` 讀 TM0CNT_L；
  expected 0,1,2,3（每次多 1 個 nop +1），我哋 1,2,3,4。
- 即 **啟動後第一次讀之前，我哋嘅 counter 多行咗 1 cycle**。
- 試 `timer_start_pending` 2→3：兩個 timer suite 分數完全
  不變。原因：`start_pending` 只喺「啟動指令之後嘅第一個
  tick」扣 cycles，而該指令本身 cost ≤ skip，`saturating_sub`
  兩者都變 0，冇分別。
- **下一步**：將「啟動延遲」改成一個 latch（例如
  `started_at_cycle`／`start_skip_next`），跳過**下一條
  instruction 的 tick**，先可以令首讀值 -1；改完要同時看
  suite 3（count-up）同 Timing（timer 無關，應不變）。

## 100% 進度 round 10（2026-11-08）：native step_cycles／breakpoint＋RL rollout／benchmark

- **IRQ latency 實驗（未落地）**：`irq_wait` 5→6 會令 Timer count-up
  suite 中途 hang（只剩 468 項、69 passes）；5→3 變 273/936、52/90；
  5 仍係最好（291/936、65/90）。`timer_start_pending` 2→3 完全冇效
  （啟動指令本身 cost ≤ skip）。→ 要用「instruction 內 overflow 時間戳」
  模型，唔係調常數。
- **Native API（SPEC §6／§9）**：
  - Rust `Cpu::peek_cycles()`（偷看下一條 instruction cost，還原
    `nseq_fetch`／`prefetch_last_pc`）＋ PyO3 `NativeCore.peek_cycles()`。
  - `NativeEmulator.step_cycles()`：先 peek 再 step，守住「不得超出 n」；
    DMA／IRQ 額外 cycle 仍可能輕微超額（已註明，Python reference 精確）。
  - `cpu.set_breakpoint()`／`clear_breakpoint()` 接上 `BreakpointTable`；
    `run_until(EventKind.BREAKPOINT)`、`step_frame()`（有 breakpoint 時
    逐 instruction）會回報 `EventKind.BREAKPOINT` 事件。
  - 測試：`tests/gbaemu/test_native_backend.py` 新增 5 個（budget、
    零／負數、breakpoint 停 step_cycles、run_until、step_frame）。
- **RL rollout（SPEC §9 Phase 4）**：新增 `rl/rollout.py`
  - `run_rollout`：逐 step observation SHA-256＋最終 state hash＋按鍵 trace；
  - `replay_trace`：trace 重放，hash 同 rollout 完全一致；
  - `run_rollouts`：`ProcessPoolExecutor`；workers=1 與 workers=2 結果相同。
  - 測試：`tests/gbaemu/test_rl_rollout.py` 5 個。
- **Benchmark（SPEC §11）**：`tools/bench.py` 加 `--render-every N`
  （0／1／4／15／60）同 `--snapshot`（save/restore per second、MB/s）；
  新增 `tools/bench_rl.py`：screen／memory／hybrid observation 的
  steps/s、frames/s，同 multi-process rollout 的 frames/host-second。
- **下一步**：IRQ latency 時間戳模型（Timer 670 項）；SOUNDBIAS／PWM
  同 wave RAM bank；Misc 4 項；之後 real-ROM smoke＋全測試。

## 100% 進度 round 11（2026-11-08）：IRQ latency 三種模型實驗（全部回退）

目標：Timer count-up 291/936、Timer IRQ 65/90 嘅瓶頸。三個方向都實作過、
量測完、確認更差後回退；baseline 保持 65/90、291/936。

1. **instruction 內 overflow 時間戳**（`bus.timer_irq_remaining`）：
   喺 `tick_timers` 用 prescaler／pending／counter 算出第一次 overflow 距離
   instruction 結尾仲有幾多 cycle，`check_irq` 將呢段 asserted time 計入
   `irq_wait`（D=5）。結果：Timer IRQ 65/90 不變，count-up 中途 hang
   （468 項、78 passes）——即係一啲長 instruction 會即刻入 IRQ，反而令
   suite 卡死。D=4 → 59/90、276/936；D=3 → 44/90、267/936（更差）。
2. **per-source IRQ delay**：timer line（IF bits 3-6）用 2 cycles、其他 5：
   44/90、267/936；timer 用 6：65/90 但 count-up hang（468 項）。
3. **`timer_start_pending` 2→3**：兩個 timer suite 完全不變（啟動指令
   本身 cost ≤ skip，`saturating_sub` 兩者都變 0）。

**結論**：唔可以再靠調 `irq_wait`／start offset 常數。樽頸係我哋嘅
instruction-boundary 模型同「IO read 見到幾多 cycle」嘅互動：
mGBA 喺 IO read 時會 `GBATimerUpdateRegister` 將 timer 推進到讀取一刻，
我哋只見到上一條 instruction 結尾嘅值。要做啱，需要 per-access cycle
計數（CPU 每條 instruction 內嘅 sub-cycle 位置），而唔係再加大延遲。

### Wave RAM 雙 bank 設計（實作過、發現方向錯，已回退）

- 教訓：GBA wave RAM 嘅 **CPU 窗口只有 16 bytes（0x04000090-0x9F）**，
  兩個 16-byte bank 係用 SOUND3CNT_L bit6 切換；唔係 0x90-0xAF 連續
  32 bytes。最初將第二 bank 放喺 io[0xA0..0xAF] 會撞正 **FIFO_A
  （0xA0-0xA3）／FIFO_B（0xA4-0xA7）**，會整壞 DMA Sound。
- 正確設計（下次實作）：
  - `Sound.wave_banks: [[u8;16];2]`；CPU 窗口永遠鏡射「非播放中」bank
    （`1 - selected`；master off 時 selected 當 0）。
  - CPU read/write 0x90-0x9F → `wave_banks[!selected]`，同時更新
    `io[0x90..0xA0]` 俾 snapshot／IO read。
  - 播放：16-byte 模式讀 `wave_banks[selected]`；32-byte 模式（bit5）
    讀兩個 bank，但 mGBA 係用 rotate/shift register（start/end 方向），
    順序唔係簡單 bank0→bank1，要照 `gb/audio.c::ch3` 實作。
  - bit6 改變時要將 `wave_banks[!selected]` 同步返落 io 窗口。
  - snapshot：wave_banks 目前唔喺 BUS/TMR section，要決定加落邊一節
    （會影響 cross-backend snapshot parity 測試）。
- 已試過嘅 Rust unit test（bank 切換、size32 pos wrap）連同實作一齊
  回退，下次可以直接抄返個測試方向。

### SOUNDBIAS PWM 解析度（已落地）

- `Sound::mix()` 讀 SOUNDBIAS（0x88）bit14-15：0 = 9-bit（預設）、1 =
  8-bit、2 = 7-bit、3 = 6-bit。非預設解析度時，左右 sample 量化到
  `step = 40 << (9 - resolution)`（9-bit 每格 ≈ 40 sample units、8-bit
  ≈ 80、7-bit ≈ 160、6-bit ≈ 320），truncate toward zero。
- 預設 9-bit 直接 return 原本 `clamp_s16(raw*20)`，所以現有遊戲／測試
  輸出完全不變（Dr. Mario 等唔會受影響）。
- BIAS level（bit0-9）未有套用做 DC offset：GBA 耳機輸出有 AC coupling，
  BIAS 只影響 PWM duty 中心，唔會令 sample 有 DC；要更精確就要連
  GBATEK 嘅 PWM 波形 high-pass 一齊模擬，暫列近似。
- Python `SoundController._mix()` 同步；Rust `pwm_quantize` + `mix` 有
  2 個 unit test、Python `test_soundbias_resolution_quantises_psg_output`。
- 下一步（如果要更完整）：實作 BIAS level 對 PWM duty 嘅影響，同
  wave RAM 雙 bank（design 見上）。

## 100% 進度 round 12（2026-11-08）：real-ROM smoke matrix＋renderer crash 修正

### 修正：bitmap composite 冇 sprite 時 AttributeError

- Python renderer 喺 Mode 3/4/5 + alpha/fade/window、但畫面冇 sprite 時，
  `_render_bitmap_composite()` 直接讀 `state.sprite_color`，而
  `_build_sprite_buffer()` 因為 `state.sprites` 空而冇行 → 未設定 slot
  → `AttributeError: 'sprite_color'`（跑 real-ROM smoke 時撞到）。
- 修正：`sprite_color` 未設定時 fallback 做全透明 zero buffer
  （`video/renderer.py`）；text-mode composite 本身有 `sprites_enabled`
  guard，唔受影響。
- 測試：`test_video_contention`／`test_audio`／`test_emulator` 39 passed。

### `tools/smoke_real_rom.py` 擴充

- 新增 `--roms-dir`（掃描目錄全部 `*.gba`）、`--json`（單一穩定 JSON
  物件）、`--audio`（比較 PCM 長度／hash）。
- 每支 ROM 同時比較：framebuffer FNV-1a hash、CPU cycles、PCM bytes／hash，
  任何一項唔 match 會 exit code 1。

### 13 支 real ROM × 30 frames 結果（`gbaemu-lab\rom`）

- **framebuffer**：10/13 match；fail = `rates.gba`、`RetroRegen-GBA-Test-v1.5.gba`、
  `Tetris.gba`。
- **CPU cycles**：1/13 match（只有 RetroRegen）；其餘差 1–40 cycles／30 frames
  （eg. rom.gba +40、shades +10、suite +6、Metal Slug +2、armwrestler +1）。
  呢個係 Python reference 同 Rust core 喺 IRQ 進場／frame boundary
  accounting 上嘅細微差異，會令長跑之後畫面有機會分叉。
- **PCM**：長度 13/13；hash 11/13（fail = `rates.gba`、`song.gba`）。
  `song.gba` 畫面 match 但 audio hash 唔同 → 混音器（好可能 wave channel
  bank／DMA Sound 取樣時序）仍有 Python/Rust 行為差異。
- **下一步**：
  1. 用 `song.gba` 做 audio lockstep：逐 sample 對 Python／Rust，搵出
     第一個分歧點（wave channel bank 設計已備）。
  2. `rates.gba`／Tetris 由 cycles 差異入手：搵第一個 diverging
     instruction／IRQ，修正 IRQ 進場或 frame boundary 的 cycle accounting。
  3. 修好後再跑 13 ROM × 120 frames 作 regression gate。

## 100% 進度 round 13（2026-11-08）：lockstep 收窄工具＋frame 0 divergence

- 新增 `tools/lockstep_real_rom.py`：逐 frame 比較 Python reference 同
  Rust core 嘅 cumulative cycles（可選 `--state` 比較 save_state hash），
  一有 divergence 即停並印出 frame／cycles／delta。
- 跑 `armwrestler.gba` 6 frames：**frame 0 已經分歧**
  （py_cycles=280897、rs_cycles=280898、delta=-1）——即唔係長時間累積，
  而係第一個 frame 內嘅 IRQ／frame-boundary accounting 差 1 cycle。
  30-frame matrix 見到嘅 1–40 cycles 差異，源頭應該就喺每一 frame 邊界
  嗰 1–2 cycles 嘅處理（Rust `run_frame` 同 Python `step_frame` 對
  overshoot 嘅定義唔同）。
- 下一步：
  1. 用 `--state` 對 frame 0 前後做 save_state diff，收窄到 IRQ 進場
     （`check_irq` 嘅 `cycles += 4` / return 4）或者 frame event 嘅
     cycle accounting；兩邊 overshoot 量（+1 vs +2）應該可以直接對齊。
  2. 對齊後重跑 13 ROM matrix；cycles 全 match 先再追 frame hash。

## 100% 進度 round 14（2026-11-08）：修正 Python／Rust timing config 唔一致（RL lockstep 主因）

- **根因**：`NativeEmulator` 一直用 `CoreConfig::default()`（`functional=false`、
  `TimingModel::Mgba`），但 `EmulatorConfig` 預設 `TimingMode.FUNCTIONAL`
  （Python reference 用「所有 access 1 cycle」近似模型）。即兩個 backend
  根本行緊唔同 timing model，frame 0 第一條 branch 已經差 1 cycle
  （Python 2 cycles vs Rust 3 cycles）。
- **修正**：
  - PyO3 `NativeCore(rom, config_sha, functional=false)`，並按 `functional`
    選 `TimingModel::Legacy`（functional）／`TimingModel::Mgba`（timed）。
  - `NativeEmulator.__init__` 依 `config.timing is TimingMode.FUNCTIONAL`
    傳 `functional`（TIMED／TRACE → mgba accounting）。
- **結果（armwrestler, chunk=1232）**：第一個 frame 280896 cycles
  **完全 identical**（之前 py 280897／rust 280898）。
- **13 ROM × 3 frames smoke（修正後）**：
  - framebuffer **12/13**（只 `rates.gba` 分歧；之前 30 frames 有 3 支分歧）。
  - CPU cycles **10/13**：`GBAUtilityTools` py +1、`Pinball` py −4，
    其餘 11 支完全相同（包括 armwrestler、LeafGreen、Tetris、song、suite）。
  - 剩餘差異集中喺 IRQ／timer 邊界，唔再係 timing model 錯配。
- **下一步**：用 `lockstep_chunks.py` 對 `GBAUtilityTools`／`Pinball` 收窄
  剩餘 1–4 cycles（多數係 IRQ 進場或 DMA startup 差）；`rates.gba` 另外追
  frame hash（已知有 audio DMA／IRQ 密集行為）。

## 100% 進度 round 15（2026-11-08）：lockstep 根因收窄完成

- **已確認**：`GBAUtilityTools` 第一個 diverging chunk（3 frames）係
  **Python `_halted_chunk()` 嘅 HALT fast-forward**，唔係 DMA／CPU 模型。
  證據：
  - 將 `Emulator._halted_chunk` 暫時 patch 成 `return 0`（逐 instruction
    行 halt），frame 0 cycles **py 280897 == rs 280897**、frame hash 相同。
  - chunk size 1232 → 分歧；chunk size 16 → 前 479248 cycles 完全 identical，
    證明分歧係大 budget fast-forward 造成，而唔係 core 行為。
- **`TimingMode.TIMED` 已經完全 lockstep**（halt 唔用 fast-forward）：
  - `GBAUtilityTools`：py 280898 == rs 280898、frame hash 相同。
  - `Pinball`：py/rs 459077、frame hash 相同（FUNCTIONAL 下差 −4 cycles）。
  - `rates.gba`：cycles 280896 == 280896，但 frame hash 仍唔同 →
    剩低嘅係 **PPU/renderer 層差異**，唔再係 CPU timing。
- **實務建議（RL 手動混用 backend）**：
  - 要 Python reference 同 Rust core 一致，用 `TimingMode.TIMED`；
  - `FUNCTIONAL` 係 Python 特調加速模式（HALT 直接跳事件），cycle 數
    同 Rust 唔保證一致，只適合純 Python 內部使用；
  - 下一步可以考慮為 native 實作同一個 fast-forward，令 FUNCTIONAL 都
    lockstep，但要先確認唔會影響 suite 嘅 halt／IRQ 時序。
- **下一步**：
  1. `rates.gba` frame hash：比較 Python／Rust framebuffer 第一個
     diverging pixel，應該係 renderer（bitmap composite／window）差異。
  2. 將 lockstep 工具 default 改 `--timing timed`，避免再量錯模式。
  3. 重跑 13 ROM × 3 frames（TIMED）做正式 matrix。

## 100% 進度 round 16（2026-11-08）：rates.gba 分歧定位到 renderer 時序模型

- `rates.gba`（TIMED）：cycles 兩邊都係 280896，但 frame hash 唔同。
  （**round 17 更正**：之前「由 scanline 8 開始 152 行全黑」係測試腳本
  用咗 `render=False` 嘅假象；正確係單一條 scanline y=7、240 pixels，
  Python 藍 (123,123,255) vs Rust 黑 (0,0,0)，其餘 159 行完全相同。）
- 判斷：`rates.gba` 喺 frame 中段（大約 line 8）改 display／palette／
  blend 暫存器（raster effect）。**Rust core 係逐條 scanline render**
  （`render_completed_scanlines()`），會用每條線當時嘅 register 狀態；
  **Python renderer 係 frame 末尾一次過 render**，用最終 register 狀態
  畫全部 240 行 → 中段改 register 嘅效果會套用到全畫面（或相反）。
- 呢個係 renderer 架構差異，唔係 CPU／DMA／IRQ timing 問題；cycles
  已完全一致。
- **修正方向（下一步）**：
  1. Python PPU 喺 HBlank／scanline 完成時逐線 render（同 native 一樣），
     或者最少記低每條線動筆時嘅 register snapshot；GUI 預設已用 native，
     Python reference 主要影響 RL screen observation。
  2. 改完用 `rates.gba` 1 frame pixel-diff 做 regression（目標 0 diff）。
  3. 其餘 ROM（GBAUtilityTools／Pinball／armwrestler／LeafGreen／Tetris／
     song／suite…）TIMED 下 cycles + frame 已一致。


### Round 17：rates line 7 實驗（已回退）

- 用 `render=True` 重測 rates（TIMED）：兩邊 cycles 280896 相同，diff 只有
  **240 pixels＝正好一條 scanline（y=7）**：Python 藍 (123,123,255)、
  Rust 黑 (0,0,0)。之前「152 行全黑」係測試腳本用咗 `render=False` 嘅假象。
- 假設：HBlank DMA／IRQ 改 register 嘅時間同逐線 render 次序相關。
  試過喺 Rust `Core::step()` 將 `render_completed_scanlines()` 移前到
  `bus.tick(cost)` 之後、DMA service 之前（同 Python 喺 `ppu.advance`
  內 render 一致）→ diff 仍然係 240 pixels，冇改善，已回退。
- 下一步要對 line 7 做 register trace：比較 Python／Rust 喺 y=6→7 嘅
  HBlank DMA／IRQ 前後，DISPCNT／BGxCNT／BLDCNT／palette 值同 render
  觸發時間，先可以確定邊一邊早咗／遲咗畫。

### Round 18：rates y=7 根因＝BLDY 寫入／讀取路徑唔一致

- register trace（TIMED，逐 scanline 比較）：
  - Python：BLDY（0x04000054）喺 game 寫入後仍然係 **0**。
  - Rust：BLDY 讀到 **0x1111／0x2122／0x0280** 等 game 寫入嘅原始值。
  - 其餘 DISPCNT／BG0-3CNT／BLDCNT／BLDALPHA／palette0 完全一樣。
- 原因：BLDY 係 **write-only** 暫存器（GBATEK 4000054h W），但兩邊實作唔同：
  - Python io 寫入 path 當佢 write-only，寫入被 mask 成 0（讀都係 0）；
  - Rust 嘅 **byte / 32-bit store path 冇 mask 0x54**，會存低原始 16-bit；
    16-bit `write_u16` 反而會變 0（所以之前單獨 roundtrip 測試見到 rs=0）。
  - Renderer 用 `regs(0x054) & 0x1F`：Python 見到 0（無 fade，藍色），
    Rust 見到 0x1111 & 0x1F = 17（clamp 16 = 全黑）→ line 7 一黑一藍。
- **正確修正（下一步）**：BLDY 要「內部存 masked 值（0x1F）、CPU 讀回 0、
  renderer 用內部值」：
  1. Rust：IO write path 0x54 存 `value & 0x1F`（所有寬度一致）、0x55 忽略；
     read path 0x54 回 0；ppu renderer 改讀 internal fade 值。
  2. Python：同樣內部存 masked、`read_reg16(0x54)` 回 0，但 renderer
     改讀 internal 值（唔可以再靠 `regs(0x054)`）。
  3. 完成後 rates y=7 要一致，並且 fade 效果先算真正模擬到（而家 Python
     係完全冇 fade）。
- 注意：console 直接 `write_u16(0x04000054, 0x1111)` 兩個 backend 都應該
  讀回 0，但內部 fade 值係 1（0x1111 & 0x1F = 17 → 16）。

### Round 19：推翻 BLDY 假設；真正係 Rust render 慢一行

- 用 cross-backend snapshot 檢查：Rust 1 frame 後 save_state → Python load_state，
  讀回 Rust 嘅 PPU 內部 BLDY／BLDCNT 都係 **0**。即 round 18 trace 見到嘅
  `0x1111` 等值係 **open bus**（Rust 將 0x054 當 write-only 讀取回 open bus），
  唔係 game 寫入嘅 fade 值 → **BLDY 唔係 rates y=7 嘅原因**。
- 真正證據（1 frame，逐 row 取樣）：
  ```
  y=5,6 : py 黑   rs 黑
  y=7   : py 藍   rs 黑   <-- 只差呢一行
  y=8,9 : py 藍   rs 藍
  ```
  即黑色→藍色嘅轉換：Python 喺 y=7 已經生效，Rust 要 y=8 先生效 →
  **Rust 遲咗一行 render**（或 Python 早咗一行）。
- 判斷：game 喺 line 7 active 期間（約 cycle 8624..9630）改咗 palette／BG
  register。Python 喺 HBlank（cycle 9630）render line 7，見到新值 → 藍；
  Rust 喺 line 7 開始（或 line 6 完成）就 render，見到舊值 → 黑。
  兩邊都係「整行用一個 register 狀態」，只係 render 觸發點差咗一行。
- **下一步**：檢查 Rust `ppu.rs` 幾時 push completed line 同 `take_completed_lines`
  回傳邊條線；目標係同 Python 一樣「line 嘅 HBlank 開始（cycle line*1232+1006）
  才 render 該 line」。修好後 rates y=7 diff 應該變 0。
- 另外：Rust `io_offset_write_only` 包含 0x054，Python 讀 0；CPU 讀行為
  仍然唔一致（但唔影響 renderer，因為 renderer 讀 raw io）。可留待之後統一。

### Round 20：rates y=7 真正根因＝LDM/STM prefetch internal cycle 多 2

- 喺 Rust `render_scanlines()` 同 Python `Ppu._render_scanline()` 加暫存 debug
  （`GBAEMU_DEBUG_LINES=1`，只印 y=5..9 的 BGxCNT／BLDCNT／palette／pixel）。
  量到（fix 前）：
  - Python line 7 render 喺 HBlank 9630 附近，palette 已係 `pal1=0x7def`、
    `pal2=0x5000`，pixel `(123,123,255)`。
  - Rust line 7 render 喺 ppu_cycles 9645，palette 仍然全 0 → 黑；同一個 step
    之後（ppu_cycles 仍 9645）先至執行 palette 32-bit copy。
- 逐 instruction trace 對照（`stmdb sp!, {r3-r10}` @ 0x0800095c）：
  Python cost=7、Rust cost=9。兩邊 `mgba_multiple_cost()` 的 `seq16` 公約不同：
  - Python：`seq16 = mgba_access(pc, 2, 1)`（原值；WAITCNT=0x4317 時 = 2）。
  - Rust：`access_cost(pc, 2, true) - 1`（= 1）。
  `internal = count - 2*seq16 - 1` 因此 Rust 多 2 cycles；之後全部指令 shift
  2 cycles，喺 0x08000100／0x08000110 的分支走咗另一條路，palette copy 由
  line 7 中段推到 HBlank 之後 → y=7 一黑一藍。
- **修正**：Rust `mgba_multiple_cost()` 的 `seq16` 改回
  `bus.access_cost(pc, 2, true)`（唔減 1）。
- 同一公約錯誤亦出現喺 multiply internal cycles：
  - ARM MUL/MLA／long multiply 的 `seq32`
  - Thumb MUL 的 `seq16`
  全部改成 `access_cost()` 原值；full-frame trace 的第一個 cost 分歧由
  0x030001a4 推後到 0x03000494（該處已係 DMA cycle accounting 差異）。
- **驗證**：
  - rates frame 0：Python／Rust hash 都係 `bdff6886f626ff7a`，byte diff = 0；
    y=7 pixel 兩邊都係 `(123,123,255)`。
  - Rust `cargo test`：115 passed。
  - `_native.pyd` 已重 build。
- **仍然存在（下一步；round 21 已修好，保留作記錄）**：rates frame 1 之後未一致
  （frame 1 byte diff 157、frame 2 byte diff 72，集中在 y=139-141／153-158 的
  blend/sprite 色）。Full-frame instruction trace 第一個 PC 分歧喺 IWRAM
  `0x030004d4`：Python 仍留喺 wait loop，Rust 已入 IRQ handler → 屬 IRQ／HALT
  wake 時序，唔再係 renderer 或 palette 計算。下一步由該 PC 的 IE/IF/IME 與
  `check_irq()` 的 2-cycle pipeline 對照。

### Round 21：rates frame 1+ 根因＝HALT／IntrWait 的 halted 與 sticky IRQ flag

- **Frame 0 尾**：Python 喺 HALT SWI 執行期間 IRQ 才 entry，`check_irq()` 入
  exception 後冇清 `core.halted`，Rust 有清 → 兩邊 frame 1 起始 PC 差一條
  instruction。已喺 Python `check_irq()` entry 前清 halted（同 Rust
  `was_halted` 處理一致）。
- **Frame 1 中段**：game 喺 `0x0800084c` 執行 `SWI 0x05`（VBlankIntrWait）後
  HALT 喺 `0x08000850`。Rust HLE 冇清 `irq_seen`，舊 VBlank sticky bit 令
  `wait_irq & irq_seen` 即時成立 → Rust 下一 step 就醒；Python
  `hle.swi_impl._intr_wait()` 會 `clear_irq_seen(flags)` → 兩邊 wake 時間唔同。
- **修正（兩邊對齊 Python reference）**：
  - Python `check_irq()`：例外進場前如果 `halted` 仍係 True 就清咗佢。
  - Python `_halt_wake_requested()`：IntrWait 同時睇 `irq_seen`，就算目標 flag
    已被 handler acknowledge（IF=0）都照樣 wake。
  - Rust `hle_swi()` 0x04／0x05：補齊 Python `_intr_wait()` 語意 ——
    IME=1、`R0=0` 且 flag 已 set 就即刻返回、`R0=1` 清 `[03007FF8]`、
    `irq_seen &= !flags`，然後 HALT。
- **驗證**：
  - rates **frame 0..9**：Python／Rust cycles 全部 280896，frame hash 全部
    相同、byte diff = 0。
  - Rust `cargo test`：116 passed；Python：335 passed, 1 skipped。
  - `_native.pyd` 已重 build。
- **仍然存在（minor）**：自訂 lockstep（逐 `cpu.step()`）喺 frame 1 step
  155295 仍見一個 transient PC 差：VBlank IRQ 喺 line 160 拉起時，Rust
  IntrWait wake path 會即刻 dispatch IRQ（`step_inner` 的 `intr_wait && ...`
  分支），Python 就經 `check_irq()` 的 5-cycle pipeline 遲幾條 instruction
  才入 handler。兩邊 framebuffer 10 frames 已經完全一樣；如果之後要
  instruction-level lockstep，先再統一 IntrWait 的 IRQ dispatch 時機
  （會影響 suite Timer count-up／SIO timing 的既有校準，要單獨驗證）。

### Round 22：force blank 喺 Mode 0 冇畫白（Pinball／RetroRegen frame 0）

- 用 7 支實機 ROM 做 TIMED 3-frame smoke（GBAUtilityTools／Pinball／Tetris／
  song／suite／armwrestler／RetroRegen），發現 Pinball 同 RetroRegen frame 0
  完全唔同：Python 全白、Rust 全黑。
- 兩邊 CPU state 完全一樣（cycles、PC、`DISPCNT=0x0080`，即 force blank），
  所以係 renderer：Python `render_frame()` 喺 mode dispatch 之前處理 bit7，
  Rust 只有 `render_bitmap_mode()` 有 force blank check，Mode 0 會照畫 BG
  （backdrop 黑）。
- **修正**：`Core::render_scanlines()` 喺 mode dispatch 之前檢查
  `DISPCNT & 0x80`，`framebuffer[y0..y1]` 填 `0xFF`。
- **驗證**：
  - 7 支 ROM × 3 frames（TIMED）：cycles 同 framebuffer 全部 match。
  - rates frame 0..9 仍然全部 byte diff = 0。
  - Rust `cargo test`：117 passed。
  - 加咗 `mode0_force_blank_draws_white` regression test。

### Round 23：IntrWait immediate IRQ dispatch 係 suite 必需（實驗後保留）

- 目標：消除 round 21 剩下的 transient PC 差（Rust IntrWait wake 即刻 dispatch
  IRQ，Python 經 `check_irq()` 5-cycle pipeline）。
- 實驗：移除 Rust `Cpu::step_inner()` 的 `intr_wait && ...` 即刻 dispatch
  分支，等 `Core::step()` 的 `check_irq()` 慢慢入 handler。
  - `suite_probe --suite 3`（Timer count-up）即刻由
    `frames=31 passes=174 total=468` 變成 `frames=600 passes=0 total=0`
    → suite 卡死。
  - 原因就係原 comment 講嘅次序：handler 要先扣 irqCounter，主程式先再寫新值；
    延遲投遞會形成 IRQ storm／卡住。
- **結論**：保留 Rust immediate dispatch（已 revert 實驗），接受嗰個 transient
  PC 差。佢唔影響 framebuffer：rates 0..9 frames 同 7 支 ROM × 3 frames 全部
  仍然 byte-identical；`suite_probe` Timer count-up 亦回復正常。
- 如果將來真係要 instruction-level lockstep，方向應該係改 **Python** 的
  IntrWait wake 去即刻 dispatch（同時對齊 Rust 的 3-cycle entry cost），
  而唔係拖慢 Rust；改完一定要重跑 suite 3／11 同 7-ROM smoke。
- **影響量化（rates.gba，10 frames）**：
  - Framebuffer／cycles：10/10 frame hash 相同、cycles 相同；7 支 ROM ×
    3 frames 亦全部 match。
  - Frame-boundary snapshot：PC／cycles 相同，PPU／TMR／IRQ／KEY／SCH
    section 完全相同；但 CPU section 的 SPSR／banked registers 同 DMA
    section 有 byte 差異，所以 `save_state()` hash 仍然唔同。
  - PCM：長度同 RMS level 接近（py 6628 vs rs 6611），但 7850/10972 個
    mono sample 唔同（71.5%），max diff = 10240（31% FS）。最佳對齊 lag
    = 14 stereo samples（約 0.43 ms），對齊後 RMS diff 仍有 1803
    （約 27% signal RMS），即唔止純時間偏移。
  - 注意：`rates.gba` 的 PCM hash 本身已經係 TODO 已知 gap（sound model
    差異），所以以上 audio 差異唔可以全部歸因於 IntrWait dispatch skew；
    要分離就要將 Python 改成 immediate dispatch 再做 A/B。
  - 實務影響：GUI 只用 native，所以用家睇唔到 Python/Rust 差異；影響主要
    係 RL／reference 的 audio observation 同 save-state equality，畫面
    observation 已經完全一致。

### Round 24：Python IntrWait immediate dispatch A/B — audio gap 同 skew 無關

- 跟 round 23 的方向，將 Python `Arm7Tdmi.step()` 的 IntrWait 目標喚醒改成
  同 Rust 一樣：目標 flag 已到、`irq_line` 仍然拉起、CPSR.I=0 就即刻
  `enter_exception(MODE_IRQ)` + HLE stub，cost=3，唔再等 5-cycle pipeline。
  （[cpu/arm7tdmi.py](cpu/arm7tdmi.py) `step()` halted 分支）
- A/B 結果（rates 10 frames）：
  - frame 1 的 lockstep skew：`mismatch_steps=14` → **0**，即係 round 21
    剩低嘅第一個 transient PC 差已消除。
  - Framebuffer／cycles／7-ROM smoke：全部仍然 match；Python 335 passed。
  - **PCM 完全冇變**：仍然 7850/10972 mono samples 唔同、first diff sample
    2998、max diff 10240。即係 round 23 量到嘅 audio gap **唔係** IntrWait
    dispatch skew 造成，係另一個 sound model 差異。
  - CPU snapshot 的 SPSR／banked register 差異 offset 亦完全一樣
    （68,71,92,93,95,128,131），所以 state hash 唔等亦唔係呢個 skew。
  - frame 2／4 仍然有 lockstep skew（另一個 IRQ 路徑），但 framebuffer 不受
    影響。
- 結論：保留 Python immediate dispatch（同 Rust／suite 行為一致，無
  regression），但 audio parity 要另開戰場：由 sound FIFO／DMA／sample
  mixing 的 Python vs Rust 差異入手，唔再郁 IRQ dispatch。

### Round 25：rates audio gap 收窄到 FIFO DMA 重編程時序（16-sample latency）

- 對比 Python `SoundController` 同 Rust `Sound` 後，PSG mixer／DMA Sound
  音量公式本身一致；差異係 **FIFO DMA 幾時 refill**。
- PCM 對齊分析（10 frames）：
  - lag=0：3925/5486 stereo frames 唔同。
  - lag=16 stereo samples：只剩 **614/5486** 唔同（88% exact match）。
  → 大部份 audio 差異係 **固定 16 samples（一個 FIFO chunk）延遲**，唔係
  波形/mixer 計算錯。
- 逐 sample trace：
  - Python 喺 sample 1483 refill DMA1，source = `0x0300458C`（新 buffer），
    所以 sample 1499 已經播 `-128`。
  - Rust 喺 sample 1482 refill，source = `0x030042BC`（舊 buffer，16 bytes
    全 0），之後 game 才寫 DMA1 SAD=`0x0300458C` + control=`0xB640`；
    Rust 播完成個 16-byte stale zero chunk，真 data 要到 sample 1515 才出。
  - DMA source pointer 本身相同（1499 後兩邊都係 `0x0300459C`），所以唔係
    source 資料錯，而係 refill 發生喺 DMA1 disable/reprogram 之前。
- 判斷：Rust 的 FIFO DMA 在同一個 sample 內服務得比 Python 早一 step，
  撞正 game 重寫 DMA1 的次序；呢個同 round 21/24 剩低的 transient CPU
  lockstep skew（frame 2/4）時間吻合。
- 今次只做診斷，**冇改 production code**；`GBAEMU_FIFO_TRACE` 暫存
  instrumentation 已移除。
- 下一步（audio parity）二選一：
  1. 先修剩低 CPU lockstep skew（frame 2/4），睇 audio 係咪自動對齊；
  2. 或喺 Rust FIFO DMA 重編程路徑加「disable 時丟棄 stale refill／
     re-enable 時即刻用新 SAD」規則，但要先對 suite DMA timing 做 A/B。

### Round 26：Python post-tick IRQ arm — CPU lockstep 已對齊，audio 仍然獨立

- 根因：Rust `Core::step()` 喺 `bus.tick()`／DMA 之後才 `check_irq()`，所以
  新拉起的 IRQ line 會喺同一個 step arm；Python 喺 `cpu.step()` 入面
  （tick 之前）check，會遲一個 instruction 才 arm。例子：frame 2 step
  197135，timer1 IF 喺 tick 後拉起，Rust 即刻 arm、Python 下一步才 arm。
- **修正**：Python `Arm7Tdmi.arm_irq()` 喺 `bus.tick()`＋DMA＋poll_keypad
  之後 arm pipeline；`Emulator.step_frame()`、`step_cycles()` 同 halted
  chunk 路徑都有呼叫。
- **結果**：
  - rates lockstep skip=2／3／4／5：以前 frame 2 有 8388、frame 4 有 9443
    個 mismatch steps；而家 **400,000 steps 內完全冇 divergence**。
  - rates 10 frames、7 支 ROM × 3 frames：framebuffer／cycles 仍然全部 match。
  - Python：336 passed（加埋新 `arm_irq` test 變 337 passed）。
- **audio 冇變**：PCM 仍然係 7850/10972 mono samples 唔同、first diff
  sample 2998、max diff 10240；CPU snapshot 差異 offsets 亦一樣
  （68,71,92,93,95,128,131）。
  → 證明 rates audio gap **唔係** CPU/IRQ instruction skew 造成，係
  sound FIFO／DMA 狀態本身（round 25 的 stale zero chunk）。
- 下一步只剩 round 25 的 option 2：Rust FIFO DMA 重編程時序
  （disable 丟棄 stale refill／re-enable 用新 SAD），再對 suite 3／11
  做 A/B。

### Round 27：rates audio parity 修好 — FIFO DMA refill threshold 16 → 15

- 逐 event trace（sample／ppu cycle）顯示 Rust FIFO DMA refill 永久比
  Python 早一個 sample：
  - Rust：sample 93、890、1482…
  - Python：sample 94、891、1483…
- 所以 sample 1482 Rust 用舊 DMA1 SAD `0x030042BC`（16 zero bytes）refill，
  51 cycles 之後 game 才寫 disable + 新 SAD `0x0300458C`；Python 喺 1483
  refill 已經見到新 SAD，冇 stale zero chunk。
- **修正**：Rust `Bus::check_fifo_dma()` 的 threshold
  `len <= 16` → `len < 16`。FIFO 啱啱 16 bytes 時唔 refill，等 15 bytes；
  refill 時間同 Python 的 pop/check 相位一致。
- **驗證**：
  - rates PCM：10 frames 同 30 frames **diff_samples = 0**。
  - song.gba／Pinball 10 frames PCM：**diff_samples = 0**（之前 PCM hash
    fail 的兩支都對齊）。
  - rates framebuffer 0..9、7 支 ROM × 3 frames：全部仍然 match。
  - suite 2／3／11：Timing `1852/2020`、Timer count-up `174/468`、
    SIO timing `4/4`，同改之前完全一樣。
  - Rust `cargo test`：118 passed（加咗
    `fifo_dma_requests_only_below_16_bytes` regression）。
  - Python：337 passed, 1 skipped。
  - `_native.pyd` 已重 build。
- 已知仍存在：`save_state()` 的 CPU SPSR／banked registers 同 DMA section
  仍有 byte 差異（唔影響 framebuffer／audio）；可以之後再查 snapshot 欄位
  語意。

### Round 28：CPU SPSR／banked registers、DMA section 同 BUS raw IO 全部對齊

- HLE SWI 而家真係行一次 SVC exception：`enter_exception(MODE_SVC, 0x08,
  return_addr)` → dispatch → `exception_return(regs[14])`，所以 snapshot 的
  SVC bank LR／SPSR 同 Python `Arm7Tdmi.swi()` 一樣會留低最後一次 SWI 的值。
- **期間發現一個嚴重 regression**：Thumb SWI 的返回位址計錯。Rust
  `step_thumb()` 已經將 `regs[15]` 設成 `pc+2`，wrapper 再減 2 就會返回
  **SWI 自己**；`suite.gba` 的 VBlankIntrWait spinner 因而永遠唔前進，
  7-ROM smoke 的 Pinball／Tetris／RetroRegen 亦出現 cycle／hash 差異。
  修正係 ARM／Thumb 都直接使用 `regs[15]`（ARM 時它已是 `pc+4`）；加咗
  `hle_swi_enters_svc_bank_and_returns_to_next_instruction` 同
  `hle_swi_thumb_returns_to_next_instruction` 兩個 regression test。
- `enter_exception()` 喺進場時即刻寫入目標 bank 的 `banked_spsr`；
  `restore_bank()` 的 User/SYS 分支將 `spsr` 清 0，對齊 Python
  `RegisterFile` 的 bank 行為。
- **BUS snapshot raw IO 對齊**：
  - Python `IoRegisters` 的 sound 寫入仍然委派 `SoundController`，但而家
    同時將 **已遮罩** 的值鏡射入 `_bytes`（`_SOUND_WRITE_MASKS` 同 Rust
    `Bus::write_sound16()` 的 mask table 一致）；CPU 讀取仍然經
    `SoundController`，行為不變。
  - Rust `write8()` 的 IE（0x200／0x201）同 IME（0x208／0x209）而家會將
    原始 byte 寫入 `io[]`，同時繼續用 `ie`／`ime` 欄位做實際語意。
  - `0xA0..0xA7` FIFO 寫入兩邊都唔會出現在 raw IO，保持 0。
- **驗證**：
  - `save_state()` 在 rates 1／10／30 frames **完整 byte-identical**：
    header match，全長 462,556 bytes，CPU／BUS／PPU／DMA／TMR／IRQ／KEY／
    CRT／SCH 每個 section 都相等。
  - rates 0..9 frame：framebuffer hash 同 cycles 全部相同；7 支 ROM ×
    3 frames 全部 match。
  - PCM：rates 10 frames 同 30 frames **diff_samples = 0**。
  - suite 2 Timing `1852/2020`、suite 3 Timer count-up `174/468`、
    suite 11 SIO timing `4/4`，同 baseline 一樣。
  - Rust `cargo test`：120 passed（新增 2 個 SWI regression tests）。
  - Python：337 passed, 1 skipped。
  - `_native.pyd` 已重新 build。

## LeafGreen 戰鬥 crash：MSR SPSR 的 T bit（2026-11-08）

- **現象**：LeafGreen 由 autosave（frame 1590）重播，frame 1604 執行到
  `0x081FDB18` 的資料區，`CpuError::Unsupported`（opcode `0x7E73599F`、
  CPSR=`0x1F` SYS+ARM、SP=`0x03007D1C`、LR=`0x08005B31`）。
- **重現材料**：`build/autosave.state`（每 30 frame 的 snapshot）＋
  `build/frames.log`（逐 frame KEYINPUT mask，frame 1590→1603，mask
  `0x3FE`）；重播 1591→1604 穩定重現。
- **診斷**：`hle_irq_enter()`／`hle_irq_return()` 加 `GBAEMU_IRQ_TRACE=1`
  trace（enter/return 的 depth、IRQ SP、stacked r0-r3/r12/LR、SPSR、
  IE/IME/IF）。trace 顯示 frame 1603 的 VBlank IRQ（depth=1）在
  `0x03007F88` 正確建立 24-byte frame（saved LR=`0x08003356`、
  SPSR=`0x3F` SYS+Thumb）；期間 timer IRQ 以 depth=2 巢狀進出
  `0x03007F74`。HLE 0x128/0x138 的 stack 完全對應真 BIOS，**冇讀錯
  stack**。
- **真 BIOS 對照**（`gba_bios.bin` 反組譯）：
  - 0x128：`push {r0,r1,r2,r3,r12,lr}`；0x12C `mov r0,#0x04000000`；
    0x130 `add lr,pc,#0`（LR=0x138）；0x134 `ldr pc,[r0,#-4]`。
  - 0x138：`pop {r0,r1,r2,r3,r12,lr}`；0x13C `subs pc,lr,#4`
    （CPSR←SPSR，PC=LR-4）。
- **根因**：遊戲 IRQ handler 在 0x030035C0 把 SPSR_irq（`0x3F`）同
  IME/IE 一齊推上 stack，然後開 nested IRQ；nested timer IRQ 將
  SPSR_irq 覆寫成 `0x1F`（SYS+ARM）。外層 handler 最後在 0x0300370C
  用 `msr spsr_fsxc, r0`（r0=`0x3F`）還原。舊 Rust／Python 的
  `_msr_spsr()` 夾硬保留舊 T bit（`value & 0xDF | old & 0x20`），所以
  SPSR 仍然是 `0x1F`；真 BIOS 0x13C 就以 **ARM** 狀態返回
  `0x08003350`（實際是 Thumb code）。`0x08003358` 的 ARM 條件分支
  （C=0 → LS）跳入 `0x081FA2A8` 的 ROM 資料區，最後死在
  `0x081FDB18`。
- **修正**：`MSR SPSR` 的控制欄位寫入完整 8 bits（包括 T）；CPSR 仍依
  GBATEK 保留舊 T（只有 BX 等可切換）。Python reference
  `cpu/arm.py::_msr_spsr()` 同步修改。
- **驗證**：
  - 舊 build：frame 1604 重播到 `0x081FDB18` crash（同使用者回報一致）。
  - 新 build：frame 1604 完成，IRQ return trace 為
    `spsr=0x3F`、`pc=0x08003352`（Thumb 的下一條 `adds r5,#1`）；
    再重播到 frame 1700 冇 exception。
  - frame 1591–1603 的 `save_state()` SHA-256 同舊 build 完全相同
    （fix 唔影響 crash 之前的狀態）。
  - Rust `msr_probe`：`MSR SPSR_fsxc, #0x3F` 後 SPSR=`0x0000003F`
    （T=1）；再寫 `0x1F` 可清 T。
- **測試**（開發樹，公開 repo 唔含 tests）：Python 338 passed, 1 skipped；
  Rust 121 passed（新增 `msr_spsr_control_field_can_set_and_clear_thumb_bit`）。
- **清理**：`main.py` 的每 30-frame autosave／frames.log 臨時診斷已
  revert；CPU `recent` ring buffer／Unsupported dump 診斷已 revert；
  只保留 `GBAEMU_IRQ_TRACE=1` 的 HLE IRQ trace。
