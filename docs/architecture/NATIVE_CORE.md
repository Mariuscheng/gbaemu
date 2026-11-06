# Native core 設計（Rust + PyO3；Cython 只作 legacy）

## 決策

新 native core 用 **Rust**，透過 **PyO3／maturin** 變成 CPython extension。
Python 只負責控制面；Rust 擁有完整硬體狀態與 frame 執行。

**不再把 Cython 當 production core。** Cython 只保留給：

- `tests/reference/gba_cpu`（legacy oracle／differential）
- 現有 `cpu/core.pyx`（opt-in 實驗，不再擴充）
- 遷移期的 A/B 對照

原因：Cython 加速單一 Python 函式，但 CPU 每條 instruction 仍需跨 Python
bus／tick；M1–M4 實測卡在 2–4 fps。Rust 的價值是把 CPU＋bus＋PPU＋timing
放在**同一個 native boundary**；Python 只在 frame 邊界呼叫。

## Rust crate 結構

```text
crates/
  gbaemu-core/
    Cargo.toml
    src/
      lib.rs            # PyO3 入口：NativeCore
      cpu/
        mod.rs          # ARM/THUMB dispatch
        arm.rs
        thumb.rs
        registers.rs
        cycles.rs
      bus/
        mod.rs          # memory map、open bus、wait state
        regions.rs
        io.rs
      video/
        ppu.rs          # timing／DMA／scanline IRQ
        renderer.rs     # BG/OBJ/window/blend
      devices/
        dma.rs
        timers.rs
        irq.rs
        audio.rs
      hle/
        postboot.rs     # HLE 開機後狀態（不讀真 BIOS）
        swi.rs          # SWI 0x00-0x2A dispatch
        irq_stub.rs     # IRQ return／BIOS 讀取保護
      state.rs          # 固定 little-endian snapshot
```

Rust core 內部**不呼叫 Python**；所有硬體狀態在同一個 `Core` struct。FFI 只在
`NativeCore` 的 public methods。

## HLE BIOS（production 必備）

專案不以真實 BIOS 為執行前提。Rust core 必須內建進階 HLE：

- **post-boot**：SP、mode、PC、IRQ 狀態、`0x02000000` header copy 與 GBATEK
  文件化初值一致。
- **SWI 0x00–0x2A**：Div、CpuSet/CpuFastSet、Bg/ObjAffineSet、BitUnPack、
  LZ77/RL/Huffman、SoundDriver 系列（已文件化者）、MultiBoot/HardReset 等；
  未文件化者依 strict／lenient 契約處理。
- **IRQ stub**：HLE IRQ return 與 exception 行為一致。
- **BIOS 讀取保護**：`pc_in_bios` 的可觀測語意；HLE 無真實 BIOS bytes，固定
  近似值要明示，不得假裝等同真 BIOS。
- **無 BIOS 檔案**：`NativeCore::new` 不需要 `bios_path`；`REQUIRE_BIOS` 僅為
  legacy 相容性保留，不是 production 路徑。

HLE 的驗收完全在專案內：post-boot hash、SWI 逐 byte 輸出、IRQ return、無 BIOS
ROM smoke。真 BIOS 只可作使用者自備的 optional differential，不進 CI／wheel。

## Python API 邊界

```python
core = NativeCore(rom_bytes, bios_bytes, config)
core.set_buttons(mask)
frame = core.run_frame(render=True, sound=True)

core.framebuffer()          # memoryview，240*160*3
core.read_memory(addr, n)
core.write_memory(addr, data)
core.save_state()           # bytes（Rust versioned payload）
core.load_state(data)
core.frame_index / core.cycles
```

- `run_frame` 是**唯一**熱邊界；內部跑 280,896 cycles，不逐 instruction 回 Python。
- `framebuffer()` 回傳 memoryview／buffer protocol，避免每 frame 複製。
- 可選 `drain_events()`：frame 結束後回傳 debug／IRQ ring，不當 callback。
- 錯誤用 `PyResult`；panic 在 FFI 邊界 `catch_unwind`，不讓 Rust panic 穿過 Python。

## 執行緒與 GIL

- `NativeCore` 內部狀態 `Send`；每個 `GBAEnv` 擁有自己的 core。
- `run_frame` 用 `py.allow_threads(|| ...)` 放掉 GIL；free-threaded CPython 3.14
  可以真正多 env 並行。
- Python 只在 frame 邊界讀 framebuffer／state；不共享 core。

## Snapshot 格式

- Rust 產生固定 little-endian payload（版本、欄位順序固定）。
- Python 加上外層 magic／version／CRC／ROM hash；`save_state` 回傳完整 bytes。
- 不用會漂移的 `serde` 預設格式；欄位明確編碼，快照可跨版本比對。
- differential：Python reference 與 Rust core 對同 ROM／輸入／cycle 產生相同
  RAM／VRAM／framebuffer hash。

## Renderer（Rust 版）

Renderer 仍然是 `VRAM + Palette + OAM + PPU regs` 的純函式，但用 Rust 實作：

1. **逐 scanline 繪製**：`Ppu::advance()` 在每條可見 line 進入 HBlank 時記錄
   line 編號，`Core::step()` 於 IRQ 進場後（handler 尚未執行）把這些 line 交給
   `render_scanlines(y0, y1)`。這與 Python `ppu.advance()` 的時序一致，所以
   mid-frame 改 `DISPCNT`／`BGxCNT`／OAM 的 raster effect（suite「Layer
   toggle 2」）與實際硬體相同。整個 frame 都沒有 line 事件時（極端防禦路徑）
   才退回 frame 尾端整張重畫。
2. 以 scanline／layer buffer 合成；固定 priority bucket，不在 pixel loop 配置
   `Vec`。
3. **OBJ vs BG 同 priority**：GBATEK Video/OBJ「Priority」規定 OBJ 在上層，
   `render_mode0` 的 OBJ 用 `consider_obj!`（`<=` 比較）搶贏 BG0-3。
4. **OBJ 每條 scanline 只解析一次**：`collect_line_sprites()` 預先篩出覆蓋該
   線的 OBJ（含 affine 邊界、mosaic 後的 y），pixel loop 只走幾個 candidate。
   之前每個 pixel 掃 128 個 OAM entry，Pinball 這類滿畫面 sprite 的遊戲要
   ~20 ms/frame；改完 ~0.4 ms/frame。
5. **BLDCNT 效果模式**：bit6-7 是 2-bit mode（0=none、1=alpha、2=變亮、
   3=變暗），2nd target 在 bit8-13。舊碼當兩個 enable bit 用，`0x00FF`
   會被當成 alpha＋EVA=0 → 全部變黑（Pinball logo 黑白）。
6. **Bitmap modes（3/4/5）** 以 BG2 實作：`render_bitmap_mode()` 疊 OBJ
   （tile 512-1023）、window、alpha/fade；mode 4 的 index 0 透明、mode 5 只有
   左上 160x128，超出範圍顯示 backdrop。
7. framebuffer 直接寫 packed RGB888；RL observation 由 Python 端 numpy 降取樣，
   或 Rust 直接輸出 resize（可選）。
8. 單 text BG、無 OBJ/window 的 fast path 保留（Python renderer 已驗證）。

## Timing model（Rust 版）

- `CoreConfig.functional`（預設 `false`）＝硬體 waitstate 模型：IWRAM 1 cycle、
  EWRAM（16-bit bus）3／6、VRAM/Palette 2、ROM 依 `WAITCNT`（含 prefetch／
  stall）、`mgba_timing` 的 pipeline offset。GUI（native backend）與 suite_probe
  都用這個模式。
- `functional: true` 是舊的近似模式（所有存取 1 cycle），只用於對照測試；
  舊的 Rust core 預設就是這個模式，代價是 **EWRAM 同 IWRAM 一樣快**，RetroRegen
  「BUS TIMING」會把 EWRAM 標成 `FAST?`（實測 834 cycles，同 IWRAM）。
- Python reference 預設仍是 `TimingMode.FUNCTIONAL`（快）；要做硬體 timing 對照
  時兩邊都要明確設成 timed／`functional: false`，否則 cycle 數不可比。

## Build／packaging

目前 adapter 是獨立的 `crates/gbaemu-python`（PyO3 + `gbaemu-core` path dependency），
extension module 名稱為 `gbaemu._native`。最簡單的 build／wheel 流程：

```powershell
.\\venv\\Scripts\\python.exe tools\\build_wheel.py
```

腳本會：

1. `maturin build --release` 產生 PyO3 extension。
2. 從 wheel 取出 `_native.pyd`（或 `.so`／`.dylib`）放到套件根，讓 source-tree
   `import gbaemu._native` 可用。
3. `pip wheel .` 產生含 platform tag 的 `gbaemu-*.whl`（`setup.py` 的
   `has_ext_modules()` 會把 wheel 標成非 pure）。

- 沒有 native extension 的環境仍用 Python reference；`NativeEmulator` 匯入時才
  會要求 `gbaemu._native`。
- CI：Rust fmt/clippy/test＋Python pytest；wheel 上傳前跑 ROM smoke。

## 遷移階段

搬遷的保留／刪除規則見 [`MIGRATION.md`](MIGRATION.md)：舊 Python 實作在新 Rust core 通過 G0–G8 前保持 canonical，不刪除。

1. **Rust skeleton**：`NativeCore` + bus/memory map + CPU ARM/THUMB；先跑 CPU
   differential tests。
2. **PPU/timing**：scanline、IRQ、DMA、timer；framebuffer hash 對 Python reference。
3. **Emulator adapter**：`Emulator` 背後改成 `NativeCore`；Python facade 不變。
4. **Snapshot／RL**：state bytes、`GBAEnv`、process pool。
5. **移除 Cython production 路徑**：`cpu/core.pyx`、`cpu/*.pyd` 只留測試。

## 為何不再用「同源 Cython」

舊設計假設「把 Python 模組原地編譯」就能加速；實測顯示：

- `.pxd` 只 cdef 欄位，無法把 `list[int]` 變成 C array；
- block runner 仍要 Python `_arm_cycles()`／bus read/write；
- 每條 instruction 的 Python 邊界才是成本。

Rust 的邊界是一次 frame，不是一次 instruction。這是質變，不是再優化幾個
Python function。

## 與現有 Python reference 的關係

- Python core／renderer 保留為 reference 與無 native extension 的開發 fallback。
- 測試仍以 Python reference 產生 golden；Rust core 必須通過同一組 differential。
- 不在 Python 與 Rust 各維護一份「正式」邏輯；Rust 是 production，Python 是
  reference／test oracle。

## 與舊 `native/` 的差異

- 這次不是「同一批 Python 模組的 Cython 編譯版」，而是**新的 Rust native core**。
- Python API／RL／UI 完全不變；`Emulator` 是 adapter。
- 只有一個 native 實作（Rust），不再有 Python／Cython／Rust 三套正式 core。
