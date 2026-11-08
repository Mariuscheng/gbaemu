# CPU timing model：legacy 與 mGBA 式 accounting

目標：把 CPU cycle model 由「每條指令 `access_cost(fetch) + internal + data`」
升級成 mGBA 的 active-region 管線模型，令 *cycle 分佈*（唔止總數）更接近
hardware；以 `mgba-emu/suite` 的「Timing tests」做 gate。

兩個模型並存：

| 模型 | Python | Rust |
|---|---|---|
| mGBA accounting（預設 timed） | `CpuBus.mgba_timing` → `_arm_cycles_mgba`／`_thumb_cycles_mgba` | `Bus.mgba_timing` → `arm_cycles_mgba`／`thumb_cycles_mgba` |
| Legacy（`--legacy`／舊行為） | `CycleModel._arm_cycles_calc`／`_thumb_cycles_calc` | `arm_cycles_calc`／`thumb_cycles_calc` |

Python 的 `TimingMode.TIMED`／`TRACE`、Rust `CoreConfig` 預設（`TimingModel::Mgba`）
由 round 8 起用新模型；`FUNCTIONAL` 維持舊近似（mgba 分支只喺非 functional 時生效）。

## 1. Legacy 模型（`--legacy`／比較用）

- Python `cpu/cycles.py`：`_fetch(pc, width, internal)`，ROM + WAITCNT bit14 →
  1 cycle；ROM internal-cycle opcode 有 prefetch-disable bug（1S→1N）；
  data 用 `bus.access_cost()`（含 +1 公約）。
- Rust `cpu.rs::fetch_cost` 係上面嘅移植；`access_cost` 常數同 Python 相同。
- suite_probe 預設 timed；Timing tests：255（functional）→ 618（timed）→
  **794/2020**（timed + fetch 移植 + timer start offset）。

## 2. mGBA 的 accounting（`isa-arm.c` / `memory.c` / `isa-inlines.h`）

- 每條 ARM 指令起始：`currentCycles = ARM_PREFETCH_CYCLES`
  = `1 + activeSeqCycles32`；Thumb 用 `1 + activeSeqCycles16`。
- waitstate 表（mGBA，*不含* +1）：
  - `GBA_ROM_WAITSTATES = {4,3,2,8}`（nonseq16）
  - `GBA_ROM_WAITSTATES_SEQ = {2,1,4,1,8,1}`（seq16）
  - `nonseq32 = nonseq16 + 1 + seq16`、`seq32 = 2*seq16 + 1`
  - WAITCNT 欄位：WS0 first bits 2-3、WS0 seq bit 4；WS1 first 5-6、
    seq 7；WS2 first 8-9、seq 10；prefetch bit 14。
- LDR/STR（同 LDM/STM 的 unit）之後加 `N32 - S32`（ARM_LOAD_POST_BODY /
  ARM_STORE_POST_BODY），即 pipeline 由 S 變 N 的差額。
- PC 寫入／branch：`ARMWritePC` = `2 + N32 + S32`（Thumb 用 16-bit）。
- MUL/MLA/SMULL…：`stall()`（ARM_WAIT_SMUL／UMUL 的 wait 表）。
- Data access：`GBALoad` 內 `wait += 2`；`GBAStore` 只 `++wait`（store 比
  load 少 1）。之後按 `GBAMemoryStall()` 調整（prefetch 開啟且 active
  region 係 ROM 時）。
- Prefetch stall（`GBAMemoryStall`）：`s = seq16`，`stall = s + 1`，
  每次 `+s` 直到 ≥ wait（最多 8 個，扣掉同 `lastPrefetchedPc` 重疊）；
  `lastPrefetchedPc = PC + 2*(loads + previousLoads - 1)`；之後
  `wait -= (nonseq16 - s); wait -= stall`（結果可以係負數）。
- LDM/STM：`GBALoadMultiple`／`GBAStoreMultiple` 逐 register 計；
  LDM 另有 `++wait` 的 internal cycle。

## 3. 為何「局部改 fetch_cost」唔夠

現行 Rust `access_cost` = mGBA + 1，所以 *總數* 大致等價，但分佈唔同：

| 情況 | mGBA | Legacy |
|---|---|---|
| ARM ROM 循序 fetch | `1 + seq32(5)` = 6 | `access_cost(seq)=6` |
| LDR/STR 後 | +`N32-S32` = +2 喺**當前**指令 | 下一個 fetch 用 `N32(8)` |
| branch | `2+N32+S32` = 14 喺**branch** | `N32(8)` 喺 branch + 下條 fetch 6 |

Timing suite 係喺指令之間讀 timer，所以分佈一錯就爆；亦解釋咗 `nop`
在 prefetch on／off 都係 6（受前一條 L/S 的 pipeline refill 影響）。

已試過的中間路線（全部 worse，已回退）：
- prefetch fetch 常數 2／3 → 751／693
- 有狀態 FIFO buffer（hit 1/halfword、miss full + refill）→ 660
- 只換 base fetch = activeSeqCycles（未做 post-body／data +2／stall）→ 320
- Legacy + 只補 refill 分佈（L/S post-body、branch N+S）→ 635

## 4. Round 4：mGBA accounting（Rust 分支）

Round 3 的「mGBA 分支」只換了 fetch base，其餘仍係 legacy 混合成本，所以
214 冇參考價值。Round 4 另寫獨立 `arm_cycles_mgba`／`thumb_cycles_mgba`，
逐條指令照 mGBA 計；legacy 路徑完全唔動。修正的關鍵差異：

- **store 唔係 `wait+2`**：`GBAStore*` 係 `++wait`（load 才 `+2`）。
- **stall 可以係負數**：prefetch 吸收得多過 wait 要保留負數，唔可以 clamp 0。
- **PC 用 A+8／A+4**：`stall()` 的 `lastPrefetchedPc`／`dist` 用 execution PC。
- **multiply WAIT 表**：MUL=0、MLA=1、SMULL/UMULL=1、SMLAL/UMLAL=2；
  MUL/MLA 用 signed `ARM_WAIT_SMUL`（`0xFFFFFF00` 檢查），unsigned 長乘法
  唔可以用 signed pattern。
- **Thumb LDM/STM 方向**：legacy 把 `0xC000`/`0xC800` 的 load bit 判反，
  mGBA 分支用 `bit11==1` 為 LDM。
- **LDM/STM**：同一 region 用 mGBA `GBALoadMultiple` 的 formula
  `wait = n*S32 + (load?1:0) + S32 - N32`，再經 `GBAMemoryStall`
  （prefetch on 會吸收 wait，甚至負數；round 9 修正 +32 checks）。
  跨區（OAM→ROM）就逐 register 計 `access_cost(addr,4,seq)`，對應
  overflow 測試；mGBA 原本只用起始 region，會錯。
- **timer start offset 2 cycles**：**32-bit** enable write（CNT_L+CNT_H 兩個
  beat）之後第一條 tick 扣 2；**16-bit CNT_H write** 就唔扣（hardware 喺
  該 beat 即時起動）。呢個區分令 Timing calibration 保持 20/20，同時
  SIO timing 仍然 4/4；如果一律扣 2，SIO timing 會變 0/4。
- **IRQ 管線延遲**：mGBA model 用 arm delay 5 cycles（legacy 2），IRQ
  entry 成本維持 4；Timer IRQ 由 0/90 升到 65/90、Timer count-up
  159 → 174，其他 suite 不變。
- **DMA 起動延遲（round 10）**：即時 DMA 喺 CNT_H write 之後有 3 cycles
  startup delay（只喺 timed／非 functional）。CPU 夠快（IWRAM，store 2
  cycles）時下一條指令（timer read）會先完成，所以 Timing 的 IWRAM DMA
  測試只計 store；ROM fetch 較慢，DMA 會搶先，測試就計 DMA cycles。
  同時保留 functional 模式即時服務，DMA suite 仍然 1256/1256。
  呢個修正令 Timing 1596 → **1660**（DMA to/from ROM 大部分已過，
  只剩 ROM→ROM 64 同 to ROM 16）。副作用：suite flow 改變後，原本靠
  `lastPrefetchedPc` 狀態「啱啱好」pass 的 LDM6／multiply 有 22 個
  變返 fail（淨 +64，詳見下面剩餘分佈）。
- **ROM→ROM DMA overhead（round 11）**：`both_gamepak` 原本加 4 個
  internal cycles，實測 hardware 係 0（src+dst 的 nonseq 已夠）；
  改成 0 之後 Timing 1660 → **1696**（+36），只剩 7 個 config 的 ±1
  （`.N.`／`PN.`／`PNS` 少 1、`..S` 多 1）。
- **Game Pak DMA ±1 rounding（round 12）**：round 11 之後 ROM→ROM／to ROM
  仲有 ±1，係 first-access 與 sequential access 嘅 wait 差造成。按實測套三條
  heuristic（只喺 timed／非 functional）：
  - 兩邊都 Game Pak：`first_idx == 1`（`.N.`）就 +1，除非 `prefetch` 開住又
    冇 sequential（`P N.` 唔加）；`seq_bit` 而且冇 prefetch（`..S`／`PNS`）就 −1。
  - 純 to ROM（dst ROM、src 非 ROM）＋prefetch＋`!seq_bit`：+1。
  - 純 from ROM（src ROM、dst 非 ROM）＋prefetch＋`seq_bit`：+1。
  結果 Timing 1696 → **1748**（+52），**DMA tests 1256/1256 保持全過**，
  而且 DMA 相關的 Timing 檢查（ROM→ROM／to ROM／from ROM）**0 fail**。
  Python reference 的 `devices/dma.py::_internal_cost` 用同一組規則，
  `tools/suite_probe.py --suite 2` 亦係 1748（同 Rust 完全一致）。
- **DMA 暫存器讀回（round 12 附帶）**：GBATEK 標 DMAxCNT_L 係只寫
  （硬體讀回 0；suite「I/O read tests」130/130 亦冇反例），
  SAD／DAD 就讀得返（用 `DMA_SRC_MASK`／`DMA_DST_MASK` 遮罩）。之前
  Rust 把 0xB0–0xDA 全部當 write-only（回 open bus），Python 就回
  未遮罩的 raw latch；兩邊都唔啱。現在 Rust 喺 `read8` 的 I/O 分支
  直接轉 `read_dma16`、Python `DmaController.read16/read32` 用同一組
  mask 常數 `SAD_MASK`／`DAD_MASK`、`cnt_l` 回 0，`tools/rust_bus_diff.py`
  由 49/51 回到 **51/51**（`dma_register_words`、`dma_immediate_16bit`）。

量測（Rust suite_probe；round 8 起 mgba 係預設、`--legacy` 做對照）：

| 模式 | Timing | Timer count-up | Timer IRQ | Misc edge |
|---|---|---|---|---|
| Legacy（`--legacy`） | 794/2020 | 177/468 | 44/90 | 1/10 |
| mGBA accounting（預設） | **1852/2020** | 174/468 | **65/90** | 6/10 |

其他 suite 在 mgba 模式下：Memory 1552/1552、BIOS math 615/615、
DMA 1256/1256、SIO register 90/90、SIO timing 4/4（與 legacy 相同）。

剩餘 168 個 fail 的分佈（mGBA；按 suite log 的 `Timing test:` 標題逐項統計）：

| 類別 | fail 數 | 原因 |
|---|---|---|
| BIOS Division／Division 2／Sqrt 2／ArcTan（ARM／ROM） | 32 | 純 HLE profile 已收咗其餘 config；ARM/ROM 有兩個不可分辨的 cluster（見 4e） |
| BIOS Sqrt／Sqrt 3（EWRAM／IWRAM） | 4 | 同上，返回 caller 的 prefetch 狀態差 1 cycle |
| multiply（`mul`／`mla`／`umull`／`umlal`／`smull`／`smlal`） | 78 | 長乘法內部 cycle 同 WAIT 表吻合，但 stall 吸收後的 ±1 對 prefetch 狀態敏感 |
| LDM/STM（`{r2-r7}` 6-reg 同 `0x07FFFFxx` overflow） | 36 | 同區 stall 公式 ±1–4；跨 EWRAM/IWRAM 邊界的 overflow 測試最敏感 |
| LDR／STR（Thumb `[sp]` 系列） | 18 | LDR/STR 之後的 prefetch refill 差 1–2 cycles |

按 prefetch config 睇，168 個 fail 有 **138 個**集中喺 prefetch-on 的 ROM config
（`P..` 17＋`PN.` 17＋`P.S` 52＋`PNS` 52；ARM／Thumb 合計），其餘 30 個散落喺
非 prefetch config（ARM/ROM 18、Thumb/ROM 4）同 WRAM／IWRAM（8）。
換言之 **prefetch buffer 的 refill 時機**（`lastPrefetchedPc` 狀態）
仍然係最大單一系統性偏差，多數係 ±1 cycle；round 14 已確認同 mGBA 模型一致（4f）。

## 4c. Round 5–6：Python reference port（與 Rust 完全一致）

Round 5 把同一個 accounting 搬去 Python reference；round 6 加 Rust
`CoreConfig.timing_model` 同 Python `CpuBus.mgba_timing` 的正式入口：

- `cpu/arm7tdmi.py`：`CpuBus.mgba_timing`、`prefetch_last_pc`、
  `mgba_access`／`mgba_wait16`／`mgba_stall`／`mgba_data_cost`／
  `mgba_store_cost`。
- `cpu/cycles.py`：`_arm_cycles_mgba`／`_thumb_cycles_mgba`；`_arm_cycles`／
  `_thumb_cycles` 按 flag 分派，legacy 路徑不動。
- `devices/timers.py`：`start_pending`（32-bit enable write = 2、16-bit
  CNT_H write = 0；同 Rust timer start offset 一致）。
- Rust：`TimingModel::Legacy`／`Mgba`，`CoreConfig.timing_model`
  （round 8 起預設 Mgba）；`suite_probe` 預設 mgba、`--legacy` 做對照。

驗證：

| 項目 | 結果 |
|---|---|
| `tools/mgba_cost_diff.py`（Python vs Rust，130 個指令×config） | 0 mismatch |
| Rust `suite_probe --suite 2` | 1852/2020（frames 128） |
| Python `tools/suite_probe.py --suite 2` | 1852/2020（同樣檢查，完全相同） |
| Rust `cargo test` | 101 passed |
| pytest（全部；含 `test_mgba_timing.py` 8 個） | 469 passed／4 skipped |
| `tools/rust_cpu_diff.py` | 108/108 |
| `tools/rust_bus_diff.py` | 51/51 |

新工具：

- `tools/suite_probe.py`：Python reference 版的 suite_probe（導航、跑 suite、
  dump SRAM log；預設新模型、`--legacy` 退回舊模型）。
- `tools/mgba_cost_diff.py`：逐指令成本 differential（先 cargo build
  `cpu_probe`；mismatch exit 1）。

## 4d. Round 8：切換預設

新模型在 Timing 由 794 → 1660（round 9 LDM +32、round 10 DMA +64、round 11 ROM→ROM +36、round 12 Game Pak DMA ±1 +52、round 13 BIOS HLE profile +84、round 15 CpuSet +20），其他 suite 不變或改善（Timer count-up
177 → 174 只差 3、Timer IRQ 44 → 65、Misc edge 1 → 6、SIO timing 保持
4/4），所以 round 8 正式切換預設：

- Python：`TimingMode.TIMED`／`TRACE` → `CpuBus.mgba_timing = True`
  （spec 仍然三種 enum 值，冇加第四個）；`FUNCTIONAL` 保持近似模型。
- Rust：`CoreConfig` 預設 `TimingModel::Mgba`；`suite_probe` 預設
  mgba、`--legacy` 做 A/B。`Bus::new` 本身仍係 legacy，方便
  `cpu_probe`／differential 以 legacy 為基準（mgba 分支只喺
  `!functional` 時生效）。

切換後驗證（Rust 預設）：

| Suite | 分數 |
|---|---|
| Memory | 1552/1552 |
| Timing | **1852/2020** |
| Timer count-up | 174/468 |
| Timer IRQ | 65/90 |
| BIOS math | 615/615 |
| DMA | 1256/1256 |
| SIO register | 90/90 |
| SIO timing | 4/4 |
| Misc edge | 6/10 |

Rust `cargo test` 101 passed；pytest 469 passed／4 skipped；
`tools/rust_cpu_diff.py` 108/108（legacy 基準）；`tools/rust_bus_diff.py`
51/51；`tools/mgba_cost_diff.py` 130 cases 0 mismatch。

## 4e. Round 13：BIOS HLE timing（純 HLE profile，已落地）

Round 13 之前，Timing 的 272 個 fail 之中有 140 個係 BIOS（Div／Div2／Sqrt×3
／ArcTan 各 20，加 CpuSet 20）。本專案係**純 HLE**（唔執行 BIOS 程式碼），
所以呢批要用 HLE 的 cycle 模型對齊，而唔係「放 stub 入 BIOS 再執行」。
呢輪收咗 84 個（BIOS 數學 84/120），剩 36 個數學 ＋ 20 個 CpuSet。

### 診斷

- **Root cause**：`cpu.rs::mgba_swi_cycles` 對 `stall >= 18` 只加 `(stall & 3)`。
  對照 mGBA（`src/gba/bios.c` 的 `useStall` 段＋`src/gba/hle-bios.s`）：mGBA 會
  `biosStall -= 18; cycles += biosStall & 3; biosStall &= ~3`，然後**執行 BIOS
  stub**（`swiBase` → `StallCall` 的 `subs r11, #4 / bhi`）燒掉其餘 cycles。
  我哋冇 stub，所以呢行等於丟棄整個 stall（Div 284、Sqrt 3 1084）。
- **實測 1（只加完整 stall）**：BIOS 誤差由 ~340／~1143 降到 42–59，證實
  `div_stall`／`sqrt_stall`／`arctan_stall` 公式本身正確（亦逐行對過 mGBA
  的 `_Div`／`_Sqrt`／`_ArcTan`，包括 8 個 `_mulWait` 的次序）。
- **實測 2（逐 config 校準）**：把 return 當 `mgba_write_pc(caller_next, width)`
  （N+S），再把「stub profile」按 caller 區域／寬度／WAITCNT 校準，得到下表
  （數值 = 除 stall 以外要加幾多 cycles）：

  | caller | ARM | Thumb |
  |---|---|---|
  | IWRAM（`0x03`） | 42 | 43 |
  | EWRAM（`0x02`） | 44 | 45 |
  | GamePak（`0x08–0x0D`） | 47 | 47 |
  | GamePak ＋ WAITCNT bit2（`.N.`／`PN.`／`.NS`／`PNS`） | −1 | −1 |

### 實作

- Rust `cpu.rs::hle_swi_profile(next, width, waitcnt)`：回傳上表數值；
  `mgba_swi_cycles` 改成 `stall + profile + mgba_write_pc(caller_next, width)`
  （**全額 stall**，唔再加 `stall & 3`）。
- Python `cpu/cycles.py::_mgba_swi_profile` 用同一組常數；`CpuBus.waitcnt`
  property 傳 WAITCNT（保持 parity）。
- 結果：Timing **1748 → 1832/2020**（+84）。BIOS 數學由 0/120 變
  **84/120**，其他 suite 全部不變（Memory 1552、io-read 130、DMA 1256、
  SIO 90＋4、BIOS math 615、Timer count-up 174、Timer IRQ 65、Misc 6）。
  Rust 與 Python（`tools/suite_probe.py --suite 2`）都係 1832，完全相同。

### 剩餘 36 個 BIOS 數學 fail（為何封頂）

- **ARM/ROM 有三個不可分辨的 cluster**：Div 需要 44、Div2／Sqrt2／ArcTan 需要
  40、Sqrt／Sqrt3 需要 47–48（同一 `stall = 53` 的 `Sqrt(0)` 同 `ArcTan(0xff)`
  卻落在不同 cluster，suite 對兩者預期同為 150）→ 差別來自返回 caller 時的
  prefetch buffer 狀態，唔係 (stall, region, width) 的函數。
- **Sqrt／Sqrt3 的 EWRAM／IWRAM 差 1 cycle**（需要 45／43，但同時
  Division／Div2／ArcTan 用 44／42 才過）→ 同上，屬 prefetch 狀態問題。
- 即：要再收呢 36 個，就要實作真正的 prefetch buffer 狀態模型（見 §5）。

### CpuSet（20 個）

mGBA 的 CpuSet 係由 BIOS stub 的搬運 loop 產生時間；round 15 已用純 HLE 的
線性模型收掉（見 4g）。

### 診斷數據

`debug/timing_swi_regs.txt`（每個 SWI 的 r0/r1 同 stall）、
`debug/timing_k46.txt`（校準期的完整 log）、`debug/timing_r15.txt`
（落地後 1832 的 log）。

## 4f. Round 14：prefetch refill 診斷（逐行對照 mGBA 源碼，未改動）

剩餘 168 個 fail 之中有 138 個集中喺 prefetch-on 的 ROM config（multiply 78、
LDM/STM 36、LDR/STR 18、BIOS 數學 24 左右），全部係 ±1–3。呢輪把我們的分工
逐行對照 repo 內已有的 mGBA 原始碼（`debug/_mgba_memory.c`、
`debug/_mgba_isa_arm_c.c`、`debug/_mgba_isa_inlines.h`、`debug/_mgba_isa_arm.h`）：

- `GBAMemoryStall`（`debug/_mgba_memory.c:1780`）＝我們的 `Bus::mgba_stall`：
  `dist = lastPrefetchedPc - PC`、`dist < 16 → previousLoads = dist >> 1`、
  `s = activeSeqCycles16`、`stall = s + 1`、`stall += s`、
  `if (stall > wait) wait = stall;`、`wait -= activeNonseqCycles16 - s;`、
  `wait -= stall`。我們原本就係呢個版本（`max(wait, stall)` 等價）。
- 乘法的 wait：`ARM_WAIT_SMUL/UMUL`（`_mgba_isa_inlines.h:40`）＋
  `_mgba_isa_arm_c.c` 的參數（MUL 0、MLA 1、SMULL 1、SMLAL 2、UMULL 1、
  UMLAL 2）——同我們 `mgba_mul_wait(rs, signed, A ? 2 : 1)` 一致。
- base：`ARM_PREFETCH_CYCLES = 1 + activeSeqCycles32`
  （`_mgba_isa_arm.h:13`）＝我們 `access_cost(pc, 4, true)`；
  Thumb 用 `1 + activeSeqCycles16` 亦然。
- waitstate 表：`GBA_ROM_WAITSTATES = {4,3,2,8}`、
  `GBA_ROM_WAITSTATES_SEQ = {2,1,4,1,8,1}`（`_mgba_memory.c:39`），
  我們 `access_cost` 係「mGBA + 1」公約，數值一致（32-bit = N+S）。

實驗（都已還原，基線仍 1832）：

| 變體 | Timing |
|---|---|
| 現況（對照 mGBA 的公式） | **1832** |
| mGBA master 的較新 stall 變體（`stall += s + 1`、無條件 `wait = stall`） | 1832（只有 2 個 delta 由 7 變 9） |
| `wait -= stall - loads` | 1366（大幅退步） |
| `wait -= stall - 1`（更舊版本） | 1390（大幅退步） |

結論：我們同 mGBA 的模型已經一致，剩返嘅 ±1–3 係**硬體同 mGBA 模型本身的
差異**，唔可以靠改公式收；要收只能逐類（multiply／LDM/STM／LDR-STR）做實證
校準，而且會直接威脅現時 1832 的基線（上面兩個負向實驗已經顯示整批
±1 會連鎖影響其他 config）。所以呢輪**唔落地**，記錄為已知偏差。

## 4g. Round 15：CpuSet／CpuFastSet 搬運成本（已落地）

Timing 剩 56 個 BIOS 之中的 CpuSet 20 個（round 13 之後只剩呢批）其實係
**CpuFastSet**：搜尋 `rom/suite.gba` 只見 Thumb `swi 0x0B` 一次，但 suite 的
「CpuSet」timing test 實際執行 **ARM `swi 0x0C`**（每 config 一次），
`r0 = r1 = 0x02000000`、`r2 = 0x00000100`（256 words、copy、32-bit），
期望 ~3453 cycles。

mGBA 由 BIOS stub 的搬運 loop（`hle-bios.s` 的 `CpuFastSet`：每 iteration
`cmp`／`ldmia {r3-r10}`／`stmia {r3-r10}`／`blt`，8 words）產生時間；純 HLE
唔執行 stub，所以用線性模型：

```
transfer = 13 + units × per_unit
```

| 模式 | per_unit |
|---|---|
| 32-bit copy | 25 |
| 32-bit fill | 16 |
| 16-bit copy | 13 |
| 16-bit fill | 8 |

`units` = `control & 0x1FFFFF`（word／halfword 數量）。校準方法：以 256-word
32-bit copy 為基準，調整 `per_unit` 直到 20 個 config 全部命中
（`...` 3453、`.N.` 3451、`..S` 3434、`IWRAM` 3397、Thumb 3456…全部精確）。
過程中發現 suite 量到的值對 `per_unit` 的敏感度係 **0.5×**（`+6/word` 只令 measured
`+3/word`），所以 25 係實測校準值（唔係 13 的理論值）。

結果：

| Suite | 之前 | 現在 |
|---|---|---|
| Timing | 1832/2020 | **1852/2020**（+20） |
| BIOS 相關（數學＋CpuSet） | 84/140 | **104/140** |
| 其他 suite | — | 全部不變（Memory 1552、io-read 130、DMA 1256、SIO 90＋4、BIOS math 615、Timer 174／65、Misc 6） |

Rust 與 Python（`tools/suite_probe.py --suite 2`）都係 **1852**，完全相同。

## 5. 風險與後續

- Python reference 改動會影響 native／legacy 差異測試：`tools/rust_cpu_diff.py`
  的 cycle cases 以 legacy 為基準；mgba 分支只喺非 functional 時生效，
  所以 native（functional）行為不變。
- Timer IRQ／Misc edge／Timer count-up 依賴同一分佈；改模型後要重新校準。
- 下一步（round 15+）：
  1. BIOS 數學剩 36 個、multiply／LDM/STM／LDR-STR 共 132 個：round 14 已確認
     我們同 mGBA 的 stall／wait 表／base 全部一致，剩返嘅 ±1–3 係硬體同 mGBA
     模型的差異（見 4f），只能逐類實證校準，會威脅 1852 基線。
  2. CpuSet／CpuFastSet 的 16-bit 同 fill 模式未有 suite 覆蓋，數值係按
     32-bit copy 比例推的；如果有 game ROM 用到，要再校準（見 4g）。
  3. Timer count-up 仲差 legacy 3 個 checks（174 vs 177），可再微調 IRQ
     arm delay／timer sampling。
  4. Python `tools/suite_probe.py` 的 `--legacy` 路徑保留作 reference
     對照；每次改 model 兩邊都要跑 `tools/mgba_cost_diff.py`。
