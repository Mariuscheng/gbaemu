# gbaemu

GBA 模擬器：Python 參考實作 + Rust 原生核心（production backend），附
PyBoy 風格 GUI 與 Gymnasium 風格 RL 介面。專案根目錄**就是** `gbaemu`
套件根（沒有內層 `gbaemu/`）；權威設計文件是
[`docs/spec/SPEC.md`](docs/spec/SPEC.md)。

> 本 repo **不包含**任何 GBA ROM 或 Nintendo BIOS。請自行準備你合法擁有的
> 檔案，見 [`rom/README.md`](rom/README.md)。

## 目前狀態（約 90%）

| 範圍 | 內容 | 狀態 |
|---|---|---|
| Phase 0–2 | 套件骨架、ROM header、HLE boot、ARM7TDMI ARM/THUMB、bus／例外、PPU、Mode 3/4/5、frame boundary | ✅ |
| Phase 3 | DMA（含 DMA Sound FIFO）、timers、IRQ／Halt／IntrWait、SWI、save media、snapshot | ✅ |
| Phase 4 | 音訊 PSG 4 聲道＋DMA Sound、Mode 0/1/2＋sprites／window／mosaic／blending、video contention | ✅ |
| Phase 5 | `GBAEnv`、`GbaApp` facade、frame skip、snapshot branching、Gymnasium `check_env` | ✅ |
| Rust core | `crates/gbaemu-core`（CPU／bus／PPU／DMA／timer／IRQ／audio／save media）＋PyO3 `gbaemu._native`；GUI 預設後端 | ✅ |
| GUI | pygame-ce SDL 視窗（4×）、32.768 kHz mixer、鍵盤輸入、`.sav` 自動載入／原子寫回 | ✅ |

已驗證：`pytest tests -q` → **302 passed, 1 skipped**；
`cargo test` → **104 passed**；硬體測試 ROM（外部 `test-rom/`）Memory 1552/1552、
DMA 1256/1256、BIOS math 615/615 等（見 [`docs/architecture/MIGRATION.md`](docs/architecture/MIGRATION.md)）。

已知缺口（詳見 [`TODO.md`](TODO.md)）：

- SOUNDBIAS／PWM（9-bit）輸出未模擬；DMA Sound 的 count／repeat 語意未完整
- OBJ window 未實作；wave RAM bank 時序、部分 timer count-up／IRQ 邊界
- Timing 測試 1852/2020（mGBA accounting）；BIOS 精確度與 SIO 部分行為
- RL process pool／trace replay 未實作

## 目錄結構

```text
（專案根目錄 = gbaemu 套件根）
  __init__.py        # 公開匯出
  api_types.py       # 公共型別（唯一權威定義）
  emulator.py        # Emulator／views／InputPort
  native.py          # NativeEmulator（Rust core facade）
  config.py          # 設定驗證與 config hash
  timing.py          # clock／PPU 常數／ScheduledEvent
  events.py / errors.py / log.py
  cli.py             # python -m gbaemu inspect-rom
  main.py            # PyBoy 風格主程式
  pyproject.toml / setup.py
  cpu/               # ARM7TDMI、解碼／執行、cycle 模型
  bus/               # address bus、region、I/O、存取成本
  memory/            # WRAM／VRAM／Palette／OAM／cartridge／save media
  video/             # PPU 時序＋renderer（BG/OBJ/window/mosaic/blending）
  audio/             # PSG＋DMA Sound（FIFO A/B、PCM）
  devices/           # DMA、timers、keypad
  hle/               # post-boot、SWI table／實作、BIOS 讀取保護
  rl/                # env.py（GBAEnv）、spaces.py、wrappers.py（GbaApp）
  state/             # snapshot header／payload
  debug/             # breakpoints（trace／watchpoint 為 Python 層）
  crates/            # Rust workspace：gbaemu-core、gbaemu-python（PyO3）
  tools/             # 開發工具（build_wheel、differential probes、bench）
  tests/             # pytest：tests/gbaemu（現行）＋tests/reference（legacy 參考 CPU）
  docs/              # 規格、GBATEK 索引、架構與逆向工程文件
  rom/               # 只放 README；使用者自備 ROM（gitignore）
```

## 安裝

需要 Python 3.11+（開發用 3.14 free-threaded）。核心模擬器零外部依賴；
RL 需要 numpy，GUI 需要 pygame-ce。

```powershell
python -m venv venv
.\venv\Scripts\python.exe -m pip install -e ".[rl,ui,dev]"
```

### Rust core（可選，但 GUI 建議）

GUI 預設用 Rust `NativeEmulator`，比 Python reference 快幾十倍。build 方法：

```powershell
.\venv\Scripts\python.exe -m pip install maturin
.\venv\Scripts\python.exe tools\build_wheel.py
```

完成後 `_native.pyd` 會放在專案根；`from gbaemu import GbaApp` 會自動使用它。
沒有 extension 時 GUI 會退回 Python reference（很慢），亦可用
`$env:GBAEMU_BACKEND="python"` 強制。詳見
[`docs/architecture/NATIVE_CORE.md`](docs/architecture/NATIVE_CORE.md)。

## 快速開始

```powershell
# 預設讀 rom/rom.gba；亦可直接指定路徑
.\venv\Scripts\python.exe main.py
.\venv\Scripts\python.exe main.py "D:\games\some_game.gba"
```

`main.py` 使用 PyBoy 風格 API：

```python
from gbaemu import GbaApp

app = GbaApp("rom/rom.gba", window="SDL3", sound="100")
try:
    while app.tick():
        pass
finally:
    app.stop()  # 寫回 <rom>.sav
```

`window="null"` 為 headless；SDL3 視窗需要 pygame-ce 與可用的顯示環境，失敗會
退回 headless。視窗接受方向鍵／Z／X／Enter／Backspace／A／S，關閉視窗會讓
`tick()` 回傳 False。電池存檔寫在 ROM 旁邊的 `<rom>.sav`（SRAM 32 KiB／
Flash 64 KiB／128 KiB／EEPROM 512 B／8 KiB 自動偵測），下次開啟自動載入。

### CLI

```powershell
.\venv\Scripts\python.exe -m gbaemu inspect-rom "D:\games\some_game.gba" --json
```

### RL

```python
from gbaemu.rl import GBAEnv, GBAEnvConfig, ObservationConfig, ActionSpec

env = GBAEnv(
    "rom/rom.gba",
    config=GBAEnvConfig(
        observation=ObservationConfig(source="screen", grayscale=True, resize=(84, 84)),
        action=ActionSpec(mode="multi_binary"),
        frame_skip=4,
    ),
)
obs, info = env.reset(seed=0)
obs, reward, terminated, truncated, info = env.step([0] * 10)
```

`GBAEnv` 預設 reward 0、terminated False；truncated 由 `max_episode_steps` 控制。
`save_state()`／`load_state()` 可直接做 snapshot branching。

## 開發

```powershell
# Python 測試（唔需要 ROM）
.\venv\Scripts\python.exe -m pytest tests -q

# Rust core 測試
cargo test --manifest-path crates/gbaemu-core/Cargo.toml
```

部分開發工具（`tools/rust_*_diff.py`、`tools/suite_report.py`、`tools/bench.py`）
需要自備 `rom/` 與外部硬體測試 ROM `test-rom/`；兩者都唔會提交到 repo。

- 規格：[`docs/spec/SPEC.md`](docs/spec/SPEC.md)
- Package 形式與安裝：[`docs/guides/PACKAGING.md`](docs/guides/PACKAGING.md)
- Native 加速設計：[`docs/architecture/NATIVE_CORE.md`](docs/architecture/NATIVE_CORE.md)
- 效能分析與加速路線：[`docs/architecture/PERFORMANCE.md`](docs/architecture/PERFORMANCE.md)
- 架構與資料流：[`docs/architecture/ARCHITECTURE.md`](docs/architecture/ARCHITECTURE.md)
- GBATEK 對照與實作狀態：[`docs/spec/GBATEK_INDEX.md`](docs/spec/GBATEK_INDEX.md)
- 開發／硬體驗證流程：[`docs/guides/DEVELOPMENT.md`](docs/guides/DEVELOPMENT.md)
- 逆向工程實務與案例：[`docs/guides/REVERSE_ENGINEERING.md`](docs/guides/REVERSE_ENGINEERING.md)
- 待辦與已知近似：[`TODO.md`](TODO.md)

## ROM／BIOS 與授權

本專案為 clean-room 實作，**不包含** Nintendo BIOS 或任何商業 ROM；
`rom/` 只有說明文件，`test-rom/`（硬體測試 ROM）與 `debug/` 證據檔
都放在 repo 之外。使用前請自行確認你手上 ROM 的授權。

程式碼授權尚未指定；發佈到 GitHub 前請補上 `LICENSE`（例如 MIT）。
