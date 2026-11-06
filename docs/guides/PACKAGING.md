# Package 形式與安裝（site-packages）

本專案的開發樹是「**專案根目錄 = `gbaemu` 套件根**」。安裝成 wheel 後，
`site-packages/gbaemu/` 只包含模擬器程式碼；ROM、測試、文件等開發資產
不會被安裝。`main.py` 是**主程式**，放在使用者的工作目錄，不屬於套件內容。

> **公開 repo 注意（2026-11-06）**：`rom/`、`test-rom/`、legacy `pygba/`、
> `tests/test_*.py` 與 `debug/repro/` 已移出 repo；wheel 只包含
> `gbaemu/*` 子套件與 `_native.pyd`。

## 安裝

```powershell
# 從專案根目錄（有 pyproject.toml 的位置）
.\venv\Scripts\python.exe -m pip install .

# 需要 RL（numpy + gymnasium）
.\venv\Scripts\python.exe -m pip install ".[rl]"

# 需要 SDL3 視窗（pygame-ce）
.\venv\Scripts\python.exe -m pip install ".[ui]"

# 開發工具（pytest、pillow）
.\venv\Scripts\python.exe -m pip install ".[dev]"
```

或先建 wheel 再安裝：

```powershell
.\venv\Scripts\python.exe -m pip wheel . --no-deps -w dist
.\venv\Scripts\python.exe -m pip install dist\gbaemu-0.1.0-py3-none-any.whl
```

安裝後的入口：

- `python -m gbaemu inspect-rom <rom> --json`（`gbaemu.cli:main`）
- console script：`gbaemu inspect-rom <rom> --json`
- `python -m gbaemu.main`（執行 `gbaemu/main.py`；ROM 路徑相對於目前工作目錄）

## 安裝後的目錄

```text
venv/
  Lib/site-packages/
    gbaemu/
      __init__.py  api_types.py  emulator.py  config.py  timing.py
      cli.py  errors.py  events.py  log.py  main.py
      audio/  bus/  cpu/  debug/  devices/  hle/  memory/  rl/  state/  video/
    gbaemu-0.1.0.dist-info/
```

**不會**安裝：`tests/`、`rom/`、`rom/bios/`、`docs/`、`docs/gbatek-gba-specs/`、
`test-rom/`、legacy `pygba/`、`tests/reference/`、`tools/setup_legacy.py`。
因此 ROM／BIOS 要放在使用者自己的工作目錄，並用參數指定路徑。

## 使用 main.py（PyBoy 風格）

安裝後，在任意工作目錄建立自己的 `main.py`：

```python
from gbaemu import GbaApp

app = GbaApp("roms/game.gba", window="SDL3", sound="100")
while app.tick():
    pass
app.stop()
```

- `window="null"`：headless；`window="SDL3"`：需要 pygame-ce 與可用顯示，失敗自動
  退回 headless。視窗模式會 pump pygame 事件、把 framebuffer blit 到視窗，並在
  按下關閉時讓 `tick()` 回傳 False；方向鍵／Z／X／Enter／Backspace／A／S 對應
  GBA 按鍵。
- `sound="100"`：啟用音訊緩衝（`AudioMode.BUFFERED`）；`None`／`0`：靜音。
- 不需要 `bios=`：預設進階 HLE 是 canonical 啟動路徑；`bios=` 只留給使用者自備的 optional legacy／differential，不進 CI。
- `.sav` 會寫在 ROM 旁（`<rom>.sav`），由 `stop(save=True)` 或
  `cartridge_flush_to_disk()` 觸發。

倉庫根目錄的 `main.py` 是開發用主程式：它偵測到自己在「套件根」（同層有
`__init__.py`）時，會把上一層補進 `sys.path` 最前面，優先使用工作樹而不是
site-packages。

## 使用 GBAEnv（Gymnasium）

```python
from gbaemu.rl import GBAEnv, GBAEnvConfig, ObservationConfig, ActionSpec

env = GBAEnv(
    "roms/game.gba",
    config=GBAEnvConfig(
        observation=ObservationConfig(source="screen", resize=(84, 84)),
        action=ActionSpec(mode="multi_binary"),
        frame_skip=4,
    ),
)
obs, info = env.reset(seed=0)
obs, reward, terminated, truncated, info = env.step([0] * 10)
```

`numpy` 只在 RL 觀測時需要；`gymnasium` 只在 `check_env`／spaces 時需要。

## 匯入順序（開發 vs 安裝）

| 執行位置 | `import gbaemu` 解析 |
|---|---|
| repo root 執行 `main.py` | 偵測套件根，把 `D:\python` 插到 `sys.path` 前 → 工作樹 |
| repo root 執行 `pytest` | pytest 的套件 root 推導把 `D:\python` 放進 `sys.path` → 工作樹 |
| 其他目錄／已安裝環境 | `site-packages/gbaemu` |
| 安裝後又在 repo root 直接 `python -c "import gbaemu"` | 可能失敗（父目錄不在 path）；加入 `PYTHONPATH=D:\python` 或從套件外部使用 |

## 直接複製開發樹（不建議）

若你要的是「把整個專案原封不動放進 site-packages」，可以把 repo 內容複製成
`venv/Lib/site-packages/gbaemu/`：

```powershell
Copy-Item -Recurse -Force .\* venv\Lib\site-packages\gbaemu\
```

這麼做會連 `tests/`、`rom/`、`docs/`、legacy 目錄一起帶進去，且 `main.py`
會變成 `site-packages/gbaemu/main.py`；只建議在離線研究環境使用。正式使用請用
上面的 `pip install .`，讓 wheel 只帶程式碼，ROM／文件留在自己的工作目錄。

## Native backend（規劃）

效能架構見 [`NATIVE_CORE.md`](../architecture/NATIVE_CORE.md)：未來的 wheel 會包含平台專屬的
Rust extension（PyO3／maturin，例如 `gbaemu._native`），預設使用 native
backend；沒有對應 wheel 的 platform 在 production 明確報錯，development 可用
純 Python reference。ROM／BIOS 仍不進 wheel；HLE 不需要真實 BIOS。

## 版本與 snapshot 相容性

- 套件版本在 `pyproject.toml`／`gbaemu.__version__`（目前 `0.1.0`）。
- Snapshot 格式版本在 `state/snapshot.py` 的 `SNAPSHOT_FORMAT_VERSION`；另有
  ROM SHA-256、config SHA-256 與 CRC-32。升級套件後若格式版本不同，
  `SnapshotVersionError` 會拒絕載入；ROM／config 不同則分別觸發
  `SnapshotRomMismatchError`／`SnapshotConfigMismatchError`。
- `.sav` 格式由 `memory/savedata.py` 決定（SRAM 32 KiB、Flash 64/128 KiB、
  EEPROM 512 B/8 KiB），與套件版本無關。

## 建置注意事項

- `pyproject.toml` 用 `package-dir = { gbaemu = "." }` 把專案根映射成安裝後的
  `gbaemu/`；`packages` 明確列出程式子套件，避免把 `tests/`、`rom/`、legacy
  目錄打包。
- 舊 Cython 建置腳本移到 `tools/setup_legacy.py`（只供 legacy `pygba`／`tests/reference/gba_cpu`
  重建 `.pyd`，不參與 `gbaemu` 的 wheel 建置）。
- 建置前若殘留 `build/lib*/gbaemu/`，請先刪除 `build/` 再重建，避免舊模組被
  撿進 wheel。
- wheel 不含 ROM／BIOS；`gbaemu/main.py` 會一併安裝（可用
  `python -m gbaemu.main`），但主要入口仍是使用者工作目錄的 `main.py`。
