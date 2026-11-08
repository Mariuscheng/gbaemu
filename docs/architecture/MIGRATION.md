# 搬遷到 Rust core：保留舊實作直到新核心通過驗收

## 原則

**舊 Python 實作是 canonical reference，不是「待刪的舊 code」。** 在新 Rust core
通過所有驗收前：

1. `cpu/`、`bus/`、`video/`、`devices/`、`hle/`、`emulator.py`、`rl/` 保持可運行，
   仍是默認 backend。
2. 不刪除、不改名、不搬移舊檔案；只做必要的 bug fix。
3. 新 Rust core 放在 `crates/gbaemu-core/`，與舊實作並存。
4. 新舊核心用同一組 ROM／輸入／frame 做 differential。
5. 只有「新核心自己跑對，且舊測試全綠」才進入刪除階段；刪除是**最後一步**，
   不是搬遷的第一步。

## 目錄與 ownership

| 路徑 | 狀態 | 用途 |
|---|---|---|
| `cpu/`、`bus/`、`video/`、`devices/`、`hle/` | **保留，reference／default** | 目前可運行實作；Rust 的 oracle |
| `emulator.py`、`api_types.py`、`rl/` | **保留，public API** | facade；之後改成 Rust adapter |
| `tests/` | **保留並擴充** | 同一組測試同時驗 Python／Rust |
| `tests/reference/gba_cpu/`、`pygba/` | **legacy reference** | 不進 wheel；不作為 production |
| `crates/gbaemu-core/` | **新 Rust core** | 逐模組搬遷 |
| `docs/architecture/NATIVE_CORE.md` | 設計 | Rust 介面與範圍 |
| 本文件 | 搬遷規則 | 刪除 gate／順序 |

## Backend 切換

過渡期用環境變數／config 選擇，默認仍然是 Python：

```text
GBAEMU_BACKEND=python   # 默認；舊實作
GBAEMU_BACKEND=rust     # 只有 Rust core 已接上時才有效
```

規則：

- Rust core 未完成前，`rust` backend 必須**明確報錯**（`NotImplementedError`／
  `BackendUnavailable`），不可靜默 fallback 到 Python 後假裝成功。
- 正式 wheel 成熟後才把默認改成 rust；Python 保留為 test reference。
- `Emulator` 公開 API 不變；backend 是內部實作細節。

## 驗收 gates

依序，全部通過才可進下一階段：

| Gate | 內容 | 通過條件 |
|---|---|---|
| G0 | Rust crate build／test | `cargo test` 全綠 |
| G1 | CPU | ARM/THM differential（register／CPSR／cycle）與 Python 一致 |
| G2 | bus／memory | memory map、IO、DMA、open bus、wait state 測試一致 |
| G3 | PPU | framebuffer hash、mode 0–5、OBJ/window/blend 一致 |
| G4 | timer／IRQ | IRQ cycle、cascade、HALT/wake 一致 |
| G5 | snapshot | `save_state()` bytes／state hash 可互相還原 |
| G6 | facade／RL | `main.py`、`GBAEnv`、`check_env`、render/sound 正常 |
| G7 | 效能 | frame throughput 可接受；無 per-instruction Python 邊界 |
| G8 | 刪除 | 舊檔案已無 import／呼叫；文件／測試已更新；rollback 方案確認 |

**G8 之前不得刪除任何舊模組。**

## 搬遷順序（一個模組一個模組）

1. **Rust skeleton**：`Core` struct、config、frame counter、state layout；
   先不接 Python。
2. **bus／memory**：ROM/RAM/IO map、open bus、wait state；用 Python oracle 對照。
3. **CPU**：ARM/Thumb fetch/decode/execute、pipeline alignment、exception、IRQ；
   CPU differential 全綠。
4. **PPU/timing**：scanline、VBlank/HBlank、DMA、timer；framebuffer hash 對照。
5. **HLE**：post-boot、SWI `0x00–0x2A`、IRQ stub、BIOS 讀取保護；無 BIOS smoke。
6. **PyO3 adapter**：`NativeCore`；`Emulator` 可選 backend。
7. **RL／packaging**：`GBAEnv`、process pool、wheel；Python reference 保留。
8. **刪除**：逐檔移除，先移除 leaf（renderer／timer），最後才 CPU／bus。

## 刪除 checklist（每個舊檔案）

- [ ] `rg` 確認沒有 import／呼叫（含 tests、tools、docs）
- [ ] Rust backend 對應功能已通過該檔案的 tests
- [ ] differential／framebuffer／snapshot 仍一致
- [ ] `pytest tests -q` 全綠（Python reference 或 Rust backend）
- [ ] `main.py`、`GBAEnv` smoke 正常
- [ ] 文件已改成 Rust 路徑，沒有死連結
- [ ] git 分支保留舊版；必要時可 revert
- [ ] 最後才 `git rm`；不要一次刪整個 `cpu/`／`bus/`

## 不要做的事

- 不要為了「看起來像 native」而把舊 `bus/` 複製成第二套 Python/Cython。
- 不要讓 Python／Cython／Rust 三套都是「正式」core；Rust 是 production，
  Python 是 reference。
- 不要在 Rust core 尚未 parity 時把默認 backend 切到 rust。
- 不要用「新檔案可跑一個 demo」當成可以刪舊檔的證據；要過 gates。

## Rollback

- 保留 `GBAEMU_BACKEND=python` 與舊目錄，任何 Rust regression 可立即切回。
- 每個 migration PR 只動一個模組；不要 mixed commit。
- Rust core 的 state／snapshot 若尚未穩定，不覆蓋 Python golden。

## 進度

| Gate | 狀態 | 備註 |
|---|---|---|
| G0 | ✅ | `crates/gbaemu-core` skeleton；`cargo test` 通過 |
| G1 | 🚧 differential 含 cycle／halt／WAITCNT／open bus | 101 Rust unit tests＋`tools/rust_cpu_diff.py` 108 checks（86 CPU、11 bus cost、11 cycle）全過；real-ROM lockstep 抓到並修正 LDR/STR bit4 解碼、未成立條件分支 cycle、Thumb MOV flags、Thumb SWI vs conditional branch 碰撞、Thumb 高位暫存器 LDM writeback、Thumb format 7 `op3` 解碼（LDRH 被誤判成 LDSB）、未對齊 LDRH／STRH 的 ROR 語意、暫存器移位量 0（LSR/ASR 不可視為 32）、暫存器移位時 R15=PC+12、LDR/STR 暫存器 offset 的 RRX 編碼；本輪再修 Thumb NEG（`rsbs`）carry（C = `b == 0`，之前誤用 `result < rd_old`，令 suite 的 `subs/rsbs/adcs` 0/1 比較永遠回 0、列表全紅）與 open-bus prefetch 模型；ARM7TDMI Booth multiplier 的長乘法 N/Z（64-bit）與 C flag（suite「Multiply long tests」72/72）；data processing 的 Rn=PC + register-specified shift 讀 instr+12（suite「Shifter tests」140/140）；CPU fetch cycle model 改為 Python `cpu/cycles.py::_fetch` 的移植（ROM + WAITCNT bit14 → 1 cycle、internal opcode 的 prefetch-disable bug），suite_probe 預設 timed → 「Timing tests」255 → 782/2020（legacy）；round 4 另寫 mGBA 式 `--mgba` accounting（store 只 `++wait`、`GBAMemoryStall` 可負、PC+8/+4、multiply WAIT 表、Thumb LDM/STM load bit、LDM/STM 同區 mGBA stall＋跨區逐 register（round 9））→ 1696/2020（round 10–15 再加即時 DMA 3-cycle startup delay、ROM→ROM internal overhead 4→0、Game Pak DMA ±1 rounding、BIOS HLE SWI profile、CpuFastSet 搬運成本 → **1852/2020**，DMA suite 仍 1256/1256）；round 5 同一 accounting 已搬去 Python reference（`CpuBus.mgba_timing`），`tools/mgba_cost_diff.py` 130 個指令×config 0 mismatch、Python `tools/suite_probe.py --suite 2` 亦係 1852/2020；Rust `CoreConfig.timing_model`（TimingModel::Legacy／Mgba）round 8 起預設 Mgba；Python TIMED／TRACE 亦切 mGBA accounting；backend adapter 已完成 |
| G2 | 🚧 bus／IO／DMA／timer／PPU event differential | `tools/rust_bus_diff.py` 51 checks 全過；含 memory mirror／寬度、open bus、VRAM 8-bit 規則、IE/IF/IME、KEYINPUT／KEYCNT 條件 IRQ、DMA0–3（含 VBlank/HBlank trigger）、timer、VBlank/HBlank/VCount IRQ、sound FIFO A/B、DMA special timing 與 PCM buffer hash；`Bus::tick()` 已把 PPU event 接到 IF 與 DMA trigger，`Core::step()` 服務 DMA、更新 IRQ、`run_frame()` 以 PPU frame event 為邊界；suite「I/O read tests」130/130（I/O 讀取分類：register read mask、只寫／未實作→open bus、mGBA 未使用清單→0、0x04000400 以上→open bus；BG0/1CNT 0xDFFF、WININ/WINOUT 0x3F3F、BLDCNT 0x3FFF、BLDALPHA 0x1F1F、音效暫存器遮罩、DMA CNT_HI 0xF7E0/0xFFE0，DMAxCNT_L 讀回 0）；suite「DMA tests」1256/1256（ROM 區 source 強制 `sourceOffset = width`，fixed／decrement 控制都會遞增；DMA0 因 SAD bit27 遮罩落 BIOS 區仍沿用 latch）；suite「SIO register R/W tests」90/90 與「SIO timing tests」4/4（SIOCNT／RCNT 模式遮罩、未連線線路狀態、normal 8/32-bit 傳輸 `bits×16.78MHz÷clock+118` cycles＋IRQ_SERIAL；32-bit I/O store 拆兩個 16-bit 寫入） |
| G3 | 🚧 framebuffer differential | `tools/rust_frame_diff.py` 17 checks 全過（Mode 0–5、text/affine BG、regular/affine OBJ、WIN0/WIN1、OBJ window（含 attr0 mode 2 sprite）、mosaic、alpha blend、fade）；比較整個 RGB888 framebuffer hash 與取樣像素；更多 blend／mosaic 邊界與 renderer/frame 精確同步尚未納入 |
| G4 | 🚧 timer／IRQ 基礎 | timer prescaler／overflow／cascade／IRQ、VBlank/HBlank/VCount IRQ、KEYCNT IRQ、halt 喚醒與 IRQ 2-cycle pipeline 已接上；**IntrWait（SWI 0x04）喚醒即刻投遞 IRQ**（BIOS 要 handler 行完先返回），修好 suite「Timer count-up」嘅 IRQ storm／hang：0 → 177/468；IRQ 進場成本 4 cycles（S+N+I）。`Halt`（SWI 0x02）保持原本 boundary 次序（suite「SIO timing」仍 4/4）。**Timer IRQ tests 44/90（legacy）／65/90（mgba）**：mgba model 用較長 IRQ arm delay（5 cycles；legacy 2），Timer IRQ 由 0 升到 65；Timer count-up 177／174（兩 model 接近）；HALT 指令本身與更精確 pipeline／DMA 互動仍待補 |
| G5 | ✅ snapshot 互通 | `tools/rust_snapshot_diff.py` 11/11 checks：Python `save_state()` → Rust `load_state()` → Rust `save_state()` 後，CPU／BUS／PPU／DMA／TMR／IRQ／KEY／CRT／SCH section bytes 完全相同；Rust 內建 SHA-256，ROM hash 自動計算，config hash 由 adapter 傳入，Python 可直接 `load_state()` Rust snapshot |
| G6 | 🚧 PyO3 adapter | `crates/gbaemu-python` 的 `NativeCore` 已 build 成 `gbaemu._native`（CPython 3.14t）；`NativeEmulator`／`GBAEMU_BACKEND=rust` 支援 frame、framebuffer、snapshot、bus 讀寫、`InputPort`（KEYINPUT／KEYCNT IRQ）、`memory`／`video`／`audio`、`load_bios()`；facade 已補 `config`／`rom_path`／`rom_header`／`is_closed`／`cpu.state()`／`read_register()`／`memory.read_region()`／`region_info()`／`run_frames()`／`pause()`；五支 real ROM 30 frames framebuffer hash 與 Python 完全相同（`rom.gba` 300 frames、`GBAUtilityTools` 60 frames、Tetris Worlds intro／title 亦同）；BIOS math tests 615/615 PASS、DMA tests 1256/1256 PASS、SIO register R/W 90/90 PASS、SIO timing 4/4 PASS、Timer count-up 177/468（IntrWait IRQ 投遞次序；原先 hang）、Timing tests 794/2020（legacy）／1852/2020（mGBA accounting）。**`suite.gba` Memory tests 1552/1552 全 PASS（列表全綠）**：462 → 830 → 1398 → 1552。本輪修正 SRAM 8-bit 匯流排語意（wide load 讀原始位址 byte 再複製、wide store 只寫位址 lane 的 1 個 byte；包含 CPU、DMA、CpuSet/CpuFastSet 與 mirror）、DMA 位址遮罩（DMA0–2 `0x07FFFFFE`、DMA3 `0x0FFFFFFE`；ROM/SRAM 因此鏡射到 BIOS/open bus 與 VRAM）＋啟動時依寬度對齊＋來源 < EWRAM 時沿用 latch（`info->latch`）、open-bus prefetch 模型（mGBA `GBALoadBad`：ARM 用 PC 嘅 word、Thumb 依 region 併 halfword）、BIOS 保護（非 BIOS 程式讀 BIOS 只回 `biosPrefetch`＝`0xE3A02004`，即 mGBA hleBios 離開 BIOS 前最後 prefetch 的 word），以及 Thumb NEG carry（列表 0/1 比較）。breakpoint、`step_cycles()`、IO raw region 仍是缺口；`cartridge_flush_to_disk()` 已接上（2026-11-06，`.sav` 原子寫回＋啟動自動載入）、EEPROM（序列協定，含 DMA 串流）已補；**SRAM／Flash save-type 已補**（2026-11-04）：由 ROM 簽章偵測（同 Python `detect_save` 一致）、SRAM 32 KiB／Flash 64 KiB／Flash 128 KiB（bank 切換＋AA/55 命令序列、ID 模式、扇區／全部抹除），`region_info(SRAM)` 尺寸同 Python 一致（suite／RetroRegen 32768、LeafGreen 131072） |
| G7 | 🚧 效能 baseline | Mode 3 synthetic：Python 0.8 fps vs Rust 120.7 fps（152×）；`rom/rom.gba` 120 frames：15.8 vs 143.7 fps（9.07×）；短 ROM 30 frames：armwrestler 162.7×、rates 76.5×、Tetris 64.6×、RetroRegen 196.3×、GBAUtilityTools 188.7×，framebuffer hash 全部相同；尚未做多 process／長時間 soak |
| G8 | ⬜ | 尚未開始 |

Rust core 現在可透過 opt-in `NativeEmulator`（`GBAEMU_BACKEND=rust`）執行真實
ROM；`Emulator.from_rom()` 仍是 Python reference 默認，但 GUI 的 `GbaApp`
預設 auto 優先使用 native（沒有 extension 或 `GBAEMU_BACKEND=python` 才退回
Python）。G2 已驗 bus／IO／DMA／timer／PPU event／sound FIFO／PCM；G3 已驗
Mode 0–5 與 window／blend／mosaic；G4 已接上 timer／IRQ／KEYCNT 與 2-cycle IRQ
pipeline；G5 已逐 section 互通 snapshot payload；G6 的 PyO3 adapter、`GBAEnv`
screen observation、wheel packaging 與六支 real ROM 的 framebuffer parity 已通過，
facade 亦已補上 CPU／memory／region／run_frames 等常用 API。G7 已有 synthetic
與真實 ROM baseline；breakpoint、`step_cycles()` 與備份媒體 flush 已補（見下），
IO raw region、EEPROM 序列協定、headless／多 process soak 及 G8 舊檔移除仍未完成。
舊 `cpu/`／`bus/`／`video/` 等檔案全部保留。

### Round 10 補充（2026-11-08）

- **Native API**：新增 Rust `Cpu::peek_cycles()`（唔執行、只還原
  `nseq_fetch`／`prefetch_last_pc`）同 PyO3 `NativeCore.peek_cycles()`；
  `NativeEmulator.step_cycles()` 先用 peek 確認預算再 step，所以唔會超額
  （DMA／IRQ 額外 cycle 除外，已在 TODO 註明）。`cpu.set_breakpoint()`／
  `clear_breakpoint()` 接上 `BreakpointTable`；`run_until(EventKind.BREAKPOINT)`、
  `step_frame()`（有 breakpoint 時轉逐 instruction 慢路徑）都會回報
  `EventKind.BREAKPOINT` 事件。
- **RL**：新增 `rl/rollout.py` —— `run_rollout`（逐步 observation hash、
  final state hash、按鍵 trace）、`replay_trace`（trace → 同一結果）、
  `run_rollouts`（`ProcessPoolExecutor`；單 process 與多 process 結果一致）。
  測試：`tests/gbaemu/test_rl_rollout.py` 5 個（含 workers=2 對照）。
- **Benchmark**：`tools/bench.py` 加 `--render-every N`、`--snapshot`
  （save/restore throughput）；新增 `tools/bench_rl.py`（screen／memory／
  hybrid observation steps/s、frames/s，同 multi-process rollout frames/s）。
- **現況**：suite「Timing」1944/2020（LDM/STM internal cycles 修正後）、
  Memory／DMA／BIOS math／SIO／Shifter／Carry／Multiply long 全綠；
  Timer count-up 291/936、Timer IRQ 65/90、Misc 6/10 仍有 IRQ latency 缺口。

### Round 11 補充（2026-11-08）

- **SOUNDBIAS PWM 解析度**：`Sound::mix()`／Python `SoundController._mix()`
  依 SOUNDBIAS bit14-15 做 9／8／7／6-bit 量化（非預設解析度時 sample
  對齊 40／80／160／320）。預設 9-bit 行為不變。BIAS level 未套用（AC
  coupling，見 TODO）。
- **IRQ latency 實驗（回退）**：instruction 內 overflow 時間戳、per-source
  delay、`timer_start_pending` 3 全部量測完都更差（詳見 TODO round 11）；
  確認下一步要 per-access cycle 計數，而唔係再調常數。
- **Wave RAM 雙 bank**：實作過但發現 CPU 窗口只有 16 bytes、第二 bank
  放 io[0xA0..] 會撞 FIFO A/B，已回退；正確設計記錄喺 TODO。

### Round 12 補充（2026-11-08）：real-ROM smoke matrix

- `tools/smoke_real_rom.py` 加 `--roms-dir`／`--json`／`--audio`，逐支
  ROM 比較 framebuffer hash、CPU cycles、PCM length／hash。
- 13 支 ROM × 30 frames：framebuffer 10/13 match（fail：rates、RetroRegen、
  Tetris）；cycles 1/13（Python vs Rust 差 1–40 cycles／30 frames，屬
  IRQ 進場／frame boundary accounting 差異）；PCM length 13/13、hash 11/13
  （fail：rates、song）。
- 同時修正 Python renderer 一個真 bug：Mode 3/4/5 + alpha/fade/window、
  但冇 sprite 時 `_render_bitmap_composite()` 會 AttributeError
  （`state.sprite_color` 未建立）；現在 fallback 全透明 buffer。
- 呢個 matrix 之後應該做 regression gate：修 IRQ/audio lockstep 後要
  全 13 支 match（cycles + frame + audio）。
