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
| Phase 3 | DMA（含 DMA Sound FIFO／repeat 語意）、timers、IRQ／Halt／IntrWait、SWI、save media、snapshot | ✅ |
| Phase 4 | 音訊 PSG 4 聲道＋DMA Sound（FIFO repeat 語意）、Mode 0/1/2＋sprites／WIN0／WIN1／OBJ window／mosaic／blending、video contention | ✅ |
| Phase 5 | `GBAEnv`、`GbaApp` facade、frame skip、snapshot branching、Gymnasium `check_env`、multi-process rollout／trace replay（`rl/rollout.py`） | ✅ |
| Rust core | `crates/gbaemu-core`（CPU／bus／PPU／DMA／timer／IRQ／audio／save media）＋PyO3 `gbaemu._native`；GUI 預設後端 | ✅ |
| GUI | pygame-ce SDL 視窗（4×）、32.768 kHz mixer、鍵盤輸入、`.sav`（ROM stem 命名）自動載入／原子寫回 | ✅ |

已驗證（開發樹；**測試程式碼唔包含喺公開 repo**）：`pytest tests -q` →
338 passed, 1 skipped；`cargo test` → 121 passed；硬體測試
ROM（外部 `test-rom/`）Memory 1552/1552、DMA 1256/1256、BIOS math 615/615 等
（見 [`docs/architecture/MIGRATION.md`](docs/architecture/MIGRATION.md)）。
公開 clone 冇 `tests/` 同 `src/*_tests.rs`，`cargo test` 會係 0 tests。

已知缺口（詳見 [`TODO.md`](TODO.md)）：

- SOUNDBIAS PWM 解析度（9／8／7／6-bit）已模擬（預設 9-bit 時輸出同之前一致）；
  BIAS level 因耳機輸出 AC coupling、唔會變 DC offset，所以未套用
- wave RAM bank 時序未模擬（設計已記錄喺 TODO：CPU 窗口只有 16 bytes，
  兩個 bank 要用 Sound state 存）；timer count-up 已實作，剩部分 IRQ 邊界
- Timing 測試 1944/2020（mGBA accounting）；Timer count-up 291/936、
  Timer IRQ 65/90（IRQ latency 模型）；BIOS 精確度與 SIO 部分行為
- native `step_cycles()` 對 DMA／IRQ 額外 cycle 仍可能超額（Python reference 精確）

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
  rl/                # env.py（GBAEnv）、rollout.py（multi-process／trace replay）、spaces.py、wrappers.py
  state/             # snapshot header／payload
  breakpoints.py     # breakpoint 表（公開 API）
  crates/            # Rust workspace：gbaemu-core、gbaemu-python（PyO3）
  tools/             # 開發工具（build_wheel、differential probes、bench）
  docs/              # 規格、GBATEK 索引、架構與逆向工程文件
  rom/               # 只放 README；使用者自備 ROM（gitignore）
```

## 安裝

需要 Python 3.11+（開發用 3.14 free-threaded）。核心模擬器零外部依賴；
RL 需要 numpy，GUI 需要 pygame-ce。套件本身唔含 ROM／BIOS，亦唔含 tests。

**安裝成 site-packages（推荐畀普通使用者）**

```powershell
# 由原始碼安裝（純 Python reference）
pip install ".[rl,ui]"

# 或者裝已經 build 好的 wheel（native core 已包含）
pip install dist\gbaemu-0.1.0-cp314-cp314t-win_amd64.whl
```

> wheel 檔名含 `cp314-cp314t`，只適用於 **CPython 3.14 free-threaded**。
> 用其他 Python 版本（3.11／3.12／3.13）要喺該版本重新 `pip install .`；
> 純 Python 安裝冇 `_native.pyd`，會自動 fallback 去 Python reference（較慢）。

**開發環境**

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
# main.py 可以 copy 到任何資料夾；ROM 由使用者提供
python main.py "D:\games\some_game.gba"

# 或用環境變數
$env:GBAEMU_ROM="D:\games\some_game.gba"; python main.py

# 乜都唔指定：自動搜尋 cwd／main.py 所在資料夾（同各自 rom/）嘅 .gba，
# 多過一個就列編號揀，搵唔到就互動輸入路徑
python main.py
```

`main.py` 本身唔會寫死任何 ROM 路徑；複製去其他資料夾之前，先
`pip install gbaemu`（或將 repo 加入 `PYTHONPATH`）。

`main.py` 使用 PyBoy 風格 API：

```python
from gbaemu import GbaApp

rom = r"D:\games\some_game.gba"  # 由使用者提供，唔好 hardcode 喺套件入面
app = GbaApp(rom, window="SDL3", sound="100")
try:
    while app.tick():
        pass
finally:
    app.stop()  # 寫回 <rom stem>.sav
```

`window="null"` 為 headless；SDL3 視窗需要 pygame-ce 與可用的顯示環境，失敗會
退回 headless。視窗接受方向鍵／Z／X／Enter／Backspace／A／S，關閉視窗會讓
`tick()` 回傳 False。

### ROM 與存檔命名

- **ROM 選擇**：`python main.py "路徑.gba"` 直接指定；亦可用環境變數
  `GBAEMU_ROM`；乜都唔指定時會搜尋目前資料夾、`main.py` 所在資料夾同各自
  嘅 `rom/` 子資料夾，多過一個會列編號俾你揀，搵唔到就互動輸入路徑。
- **存檔**：寫在 ROM 旁邊、跟 ROM 同一個 stem 的 `.sav`
  （`Dr_Mario.gba` → `Dr_Mario.sav`；SRAM 32 KiB／Flash 64 KiB／128 KiB／
  EEPROM 512 B／8 KiB 自動偵測），下次開啟自動載入。
- 舊式 `<rom 全名>.sav`（例如 `Dr_Mario.gba.sav`）仍然會讀取；之前用
  `rom.gba` 留下的 `rom.gba.sav` 要保留就自己改名做 `Dr_Mario.sav`。
- **只有遊戲真正寫入備份記憶體（手動存檔）時才會更新 `.sav`**；純粹開遊戲
  唔會改動現有存檔。需要強制寫回可呼叫 `app.save_battery()`。

### CLI

```powershell
# ROM header
.\venv\Scripts\python.exe -m gbaemu inspect-rom "D:\games\some_game.gba" --json

# headless 執行、dump 記憶體、CPU trace、重播 input trace
.\venv\Scripts\python.exe -m gbaemu run "D:\games\some_game.gba" --frames 600 --no-video --json
.\venv\Scripts\python.exe -m gbaemu dump-memory "D:\games\some_game.gba" --address 0x02000000 --size 256
.\venv\Scripts\python.exe -m gbaemu trace "D:\games\some_game.gba" --from 0x08000000 --cycles 10000
.\venv\Scripts\python.exe -m gbaemu replay "D:\games\some_game.gba" --input inputs.jsonl
```

`trace` 輸出 JSONL（每行 `{"pc", "cpsr", "cycles"}`）；`replay` 讀
`{"frame": n, "buttons": [...]}` 的 JSONL，輸出最終 `state_hash`。

### RL

```python
from gbaemu.rl import GBAEnv, GBAEnvConfig, ObservationConfig, ActionSpec

env = GBAEnv(
    "rom/Dr_Mario.gba",
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

Multi-process rollout 與 trace replay：

```python
from gbaemu.rl import replay_trace, run_rollout, run_rollouts

actions = [[0] * 10, [1] + [0] * 9, [0] * 10]
result = run_rollout("rom/Dr_Mario.gba", actions, seed=7)
same = replay_trace("rom/Dr_Mario.gba", result.trace, seed=7)
assert same.final_state_hash == result.final_state_hash

results = run_rollouts(
    "rom/Dr_Mario.gba",
    [(actions, 1), (actions, 2)],
    workers=2,  # ProcessPoolExecutor；1 = 單 process
)
```

`RolloutResult` 有逐 step observation hash、最終 state hash、trace（按鍵名稱），
所以同一 seed／actions 必定重現同一結果（對應測試只喺開發樹提供，唔隨公開
repo 上載）。

Native backend 同樣有 `step_cycles()`、`run_until()`（含 `EventKind.BREAKPOINT`）
同 `cpu.set_breakpoint()`；`step_cycles()` 會先用 Rust `peek_cycles()` 確認
預算，唔會超額（DMA／IRQ 額外 cycle 例外，見 TODO）。

Benchmark：

```powershell
.\venv\Scripts\python.exe tools\bench.py --rom rom/Dr_Mario.gba --frames 120 --render-every 4 --snapshot
.\venv\Scripts\python.exe tools\bench_rl.py --rom rom/Dr_Mario.gba --steps 30 --workers 4
```

## 開發

公開 repo **唔包含測試程式碼**（`tests/` 同 Rust `src/*_tests.rs` 都喺 repo
外嘅開發樹保存）。開發時要跑測試，先由開發樹將 `tests/` 同
`crates/gbaemu-core/src/*_tests.rs` 放返入 repo，再執行：

```powershell
# Python 測試（唔需要 ROM）
.\venv\Scripts\python.exe -m pytest tests -q

# Rust core 測試
cargo test --manifest-path crates/gbaemu-core/Cargo.toml
```

部分開發工具（`tools/rust_*_diff.py`、`tools/suite_report.py`、`tools/bench.py`）
需要自備 `rom/` 與外部硬體測試 ROM `test-rom/`；兩者都唔會提交到 repo。
`crates/gbaemu-core/src/bin/*`（suite／cycle／trace probe 同 benchmark binaries）
係本機開發工具，唔喺公開 repo 提供；需要時由開發樹另行保存。

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
`rom/` 只有說明文件，`test-rom/`（硬體測試 ROM）同其他證據檔都放在 repo 之外。使用前請自行確認你手上 ROM 的授權。

程式碼授權：**MIT**（見 [`LICENSE`](LICENSE)）。
