# GBATEK 對照索引（Phase 5）

本檔把 `gbaemu` 的每個子系統連到 GBATEK 章節，並記錄目前實作狀態。目的不是
複製 GBATEK 原文，而是讓「硬體語意 → 模組 → 測試」可追溯；實作時直接查本地
鏡像，不憑記憶寫數值。

- 本地鏡像：`docs/gbatek-gba-specs/`（17 章，逐章 `spec.md`）
- 上游：<https://problemkaputt.de/gbatek.htm>
- GBA-only Markdown 鏡像：<https://rust-console.github.io/gbatek-gbaonly/>
- 路徑均相對於專案根目錄（根目錄本身就是 `gbaemu` 套件，沒有內層 `gbaemu/`）

## 使用規則

1. 每個非直觀硬體行為，原始碼註解以 `# GBATEK: <章節名>` 標記（規格 0.5）。
2. 新增／修改硬體行為時，同步更新本表、`TODO.md` 的 Phase 驗收與 Open Questions。
3. 本地鏡像與上游衝突時，以本地鏡像為研究依據；實際硬體行為仍以測試 ROM 實測
   為最終判準，差異記錄在 `TODO.md`。
4. 逆向工程流程、資產用途與 golden 重取規則見
   [`DEVELOPMENT.md`](../guides/DEVELOPMENT.md)。

## 子系統對照表

| 子系統 | gbaemu 模組 | 本地 GBATEK | 關鍵章節 | 實作狀態 |
|---|---|---|---|---|
| Memory map、bus 寬度、鏡像 | `bus/address_bus.py`、`bus/regions.py`、`bus/access.py`、`memory/wram.py` | `02-memory-map` | GBA Memory Map；Address Bus Width and CPU Read/Write Access Widths；VRAM, OAM, and Palette RAM Access | Phase 0–2 ✅ |
| 時序（clock、S/N/I、wait state、prefetch、contention） | `timing.py`、`bus/access.py`、`cpu/cycles.py`、`video/ppu.py` | `15-arm-cpu`、`02-memory-map`、`11-system-control`、`04-video` | ARM CPU Instruction Cycle Times；WAITCNT；GBA GamePak Prefetch；VRAM/OAM/Palette access | Phase 2 ✅ 基礎；Phase 4 ✅ contention／prefetch bug（8-entry buffer refill 近似） |
| I/O map 與暫存器語意 | `bus/io.py`、`bus/address_bus.py` | `03-io-map` | GBA I/O Map；LCD I/O Registers | Phase 2–3 ✅（DMA/timer/sound 委派） |
| LCD／PPU／顯示模式 | `video/ppu.py`、`video/renderer.py`、`video/framebuffer.py`、`memory/vram.py` | `04-video` | LCD I/O Display Control；LCD I/O Interrupts and Status；GBA LCD Video Controller - VRAM；BG Control；BG Affine；OBJ Attributes；Window；Blending | Phase 4 ✅ Mode 0/1/2/3/4/5、sprites、affine、window、mosaic、alpha/fade；frame-end 合成（HBlank 逐線待補） |
| 音訊／Sound FIFO | `audio/sound.py`、`devices/dma.py` | `05-sound` | GBA Sound Controller；Sound Channel 1-4；Sound FIFO | Phase 4 ✅ 暫存器／FIFO A/B／PCM；PSG 混音、timer 取樣率待補 |
| Timers／prescaler／cascade | `devices/timers.py`、`timing.py` | `06-timers` | GBA Timers；TM0CNT_L；TM0CNT_H | Phase 3 ✅ |
| DMA0-3／時機／FIFO DMA | `devices/dma.py`、`bus/io.py` | `07-dma` | GBA DMA Transfers；Special features of the separate DMA channels；Sound DMA | Phase 3 ✅ 一般 DMA／VBlank/HBlank；Phase 4 ✅ FIFO special timing |
| Serial／link cable | （不支援） | `08-communication` | GBA Communication | 非 Phase 0–5 範圍（規格 1） |
| Keypad／KEYINPUT／KEYCNT | `bus/io.py`、`emulator.py` | `09-keypad` | GBA Keypad Input；KEYINPUT；KEYCNT | Phase 2 ✅ |
| Interrupts／IME／IE／IF／stack | `cpu/arm7tdmi.py`、`hle/postboot.py`、`bus/io.py` | `10-interrupts` | GBA Interrupt Control；BIOS Interrupt handling；Default memory usage at 03007FXX | Phase 3 ✅ 2-cycle 延遲、HLE stub |
| System control／WAITCNT／POSTFLG／prefetch | `bus/address_bus.py`、`cpu/cycles.py` | `11-system-control` | WAITCNT；POSTFLG；GBA GamePak Prefetch | Phase 2 ✅ WAITCNT；Phase 4 ✅ prefetch bug／prefetch-on |
| Cartridge header／save media | `memory/cartridge.py`、`memory/savedata.py` | `12-cartridges` | GBA Cartridge Header；Backup Media；Complement check；Entry Point | Phase 3 ✅ SRAM/Flash/EEPROM、`<rom stem>.sav` 原子寫回 |
| CGB compatibility | （不支援） | `13-cgb-compatibility` | CGB Compatibility | 非範圍（規格 1） |
| Unpredictable behavior | （研究參考） | `14-unpredictable` | Unpredictable Things | 參考；不主動模擬 |
| ARM7TDMI／ARM/THUMB 指令 | `cpu/registers.py`、`cpu/arm7tdmi.py`、`cpu/arm.py`、`cpu/thumb.py`、`cpu/conditions.py` | `15-arm-cpu` | ARM CPU Register Set；ARM 32bit／16bit Instruction Set | Phase 1 ✅ |
| BIOS／SWI／HLE | `hle/postboot.py`、`hle/swi_table.py`、`hle/swi_impl.py`、`hle/swi_math.py`、`hle/bios_read_protect.py` | `16-bios` | BIOS Function Summary；Arithmetic Functions；Decompression Functions；How BIOS Processes SWIs | Phase 3 ✅ 0x00–0x1F／0x26／0x27；SoundDriver no-op、Huffman 待驗 |
| Connectors／周邊 | （不支援） | `17-connectors` | GBA Connectors | 非範圍 |

## RL 層對照（非 GBATEK）

| 項目 | 模組 | 規格 | 測試 |
|---|---|---|---|
| `GBAEnv`、observation／action／frame skip／truncation | `rl/env.py`、`rl/spaces.py` | §5.8、§7 | `tests/gbaemu/test_rl.py` |
| PyBoy 風格 `GbaApp` facade | `rl/wrappers.py`、`main.py` | §6 使用方式 | 同上；`main.py` smoke |
| 公共型別（唯一權威） | `api_types.py` | §5 | `test_api_types.py` |
| snapshot／branching | `state/snapshot.py`、`emulator.py` | §5.7、§7.4 | `test_snapshot*.py` |

## 開發資產

| 路徑 | 內容 | 用途 |
|---|---|---|
| `rom/` | 本機 ROM（`rom.gba`＝BZPJ、armwrestler、GBAUtilityTools、RetroRegen、Tetris、song 等） | 真遊戲 smoke／畫面 |
| **進階 HLE BIOS（內建）** | 不需真實 BIOS；clean-room 依 GBATEK | post-boot／SWI／IRQ 測試 |
| `test-rom/` | 硬體測試 ROM＋原始碼（DMA／IRQ／PPU／timer／memory／bus…） | 週期／暫存器驗證 |
| `docs/gbatek-gba-specs/` | GBATEK 17 章鏡像 | 規格查詢 |
| `docs/images/` | 實機截圖 | Phase 5 驗證留存 |

## 目前實作狀態與已知近似

| 行為 | 狀態 | 說明 |
|---|---|---|
| Memory map／EWRAM/IWRAM 鏡像 | ✅ | 256 KiB／32 KiB，modulo 鏡像 |
| ROM 三個 32 MiB 視窗 | ✅ | 0x08000000／0x0A000000／0x0C000000 互為鏡像 |
| Palette／OAM／VRAM 8-bit 寫入 | ✅ | Palette/BG VRAM 複製；OBJ VRAM／OAM 忽略 |
| BIOS 讀取 | ✅ | HLE 固定近似＋`pc_in_bios` 讀取保護；production 不依賴真 BIOS |
| I/O 暫存器 | ✅ | PPU／DMA／timer／sound 委派；其餘 raw storage |
| SRAM／Flash／EEPROM | ✅ | 8-bit bus；wide store 只寫 1 byte；`<rom stem>.sav` auto-load／flush |
| ROM header | ✅ | complement check＋fixed value；不驗證 Nintendo logo（clean-room） |
| HLE post-boot | ✅ | SP／mode／PC／banked SP／header copy／IRQ 指標清零 |
| SWI dispatch | ✅ | 0x00–0x1F／0x26／0x27 handler；0x2B+ `HleUnsupportedSwiError` |
| Snapshot | ✅ | header＋九段 payload、CRC、ROM/config SHA-256 |
| PPU／DMA／Timer／IRQ／Keypad | ✅ | 行為見 Phase 2–4 |
| Video contention | ✅ 近似 | 可視期間固定 +1 waitstate（硬體為同時存取才插入） |
| Prefetch | ✅ 近似 | prefetch-on 循序 fetch 1 cycle；off 的 1S→1N bug；8-entry refill 未逐 halfword |
| 音訊 | ✅ FIFO | PCM 32768 Hz 近似；PSG／SOUNDBIAS 待補 |
| Huffman | ⚠ | 沿用 legacy 實作，尚無獨立向量測試 |
| PPU 合成時機 | ⚠ | frame 結束一次合成；HBlank 期間 VRAM 寫入下一 frame 才反映 |
| 指令週期 ±1 | ⚠ | B/BL、STM n=2 等需硬體 ROM 校準（見 TODO Open Questions） |

## Phase 驗收對照

| Phase | 驗收重點 | 測試 |
|---|---|---|
| 0 | api_types、HLE post-boot、inspect-rom、SWI 0x2B+ | `test_api_types.py`、`test_hle.py`、`test_cli.py`、`test_emulator.py` |
| 1 | 指令語意／flags、step_cycles 欄位、確定性 | `test_cpu_*.py`、`test_cpu_differential.py` |
| 2 | Mode 3 framebuffer、事件排序、VRAM 8-bit 規則 | `test_ppu.py`、`test_frame.py`、`test_timing_events.py` |
| 3 | DMA/timer/SWI/save、snapshot hash、flush 原子性 | `test_dma.py`、`test_timers.py`、`test_swi.py`、`test_save.py`、`test_snapshot_roundtrip.py` |
| 4 | PPU 各模式、sprites/window、FIFO PCM、contention | `test_ppu_modes.py`、`test_audio.py`、`test_video_contention.py` |
| 5 | `GBAEnv`、frame_skip、snapshot branching、Gymnasium `check_env` | `test_rl.py` |

## 參考資料

- GBATEK：<https://problemkaputt.de/gbatek.htm>
- GBA-only Markdown mirror：<https://rust-console.github.io/gbatek-gbaonly/>
- PyBoy 公開 API 形狀（只參考使用方式，不複製程式碼）：<https://docs.pyboy.dk/api/index.html>
