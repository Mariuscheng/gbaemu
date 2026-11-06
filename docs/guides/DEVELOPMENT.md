# 逆向工程與硬體驗證流程

本專案是 clean-room GBA 模擬器：行為以 GBATEK 與公開硬體測試 ROM 為依據，
不重製 Nintendo BIOS／商業 ROM。這份文件說明「從文件到程式碼、再到驗證」的
工作流，以及各測試資產的用途。

完整的逆向工程方法論、除錯 API、Dr. Mario 標題案例與檢查清單，見
[`REVERSE_ENGINEERING.md`](REVERSE_ENGINEERING.md)。

> **公開 repo 注意（2026-11-06）**：`rom/`、`test-rom/`（硬體測試 ROM）、
> legacy Cython `pygba/` 與 `tests/test_*.py` 已移出 repo。本文提到的
> `test-rom/...`、`debug/repro/...` 路徑屬本機開發資產，clone 返嚟唔會有；
> 現行測試只包含 `tests/gbaemu/` 與 `tests/reference/`（純 Python 參考 CPU）。

## 依據優先序

1. **`docs/spec/SPEC.md`**：API、時序模型、
   驗收條件的權威來源。
2. **`docs/gbatek-gba-specs/`**：硬體語意、暫存器位元、時序表。本地鏡像優先於上游。
3. **硬體測試 ROM**：`test-rom/`（DMA／IRQ／timer／PPU／bus…；`test-rom/arm-ref/`
   保留 ARM/THUMB 參考測試）。實測結果高於 GBATEK 文字。
4. **legacy `pygba/`／`tests/reference/gba_cpu/` golden**：僅作回歸對照；若新模型與 legacy 不同，
   以規格＋硬體測試為準，並在 `TODO.md` 記錄差異。

## 新增／修改硬體行為的流程

1. 找到 `docs/spec/GBATEK_INDEX.md` 對應的 GBATEK 章節與模組。
2. 在程式碼加上 `# GBATEK: <章節名>` 註解，說明數值來源。
3. 先寫單元測試（`tests/gbaemu/`），用最小 state 驗證旗標／位址／cycle。
4. 跑相關硬體測試 ROM（`test-rom/`）；若通過，補 integration 測試或 golden。
5. 更新 `docs/spec/GBATEK_INDEX.md` 的實作狀態與 `TODO.md` 的 Phase／Open Questions。
6. 執行 `pytest tests/gbaemu -q` 與 `pytest tests -q`，確認 legacy golden 沒有意外
   漂移；若有預期差異，記錄原因並重取 golden。

## 測試資產

| 路徑 | 內容 | 用途 |
|---|---|---|
| `rom/` | 本機 ROM：`rom.gba`（BZPJ Dr. Mario & Panel de Pon）、`armwrestler.gba`、`GBAUtilityTools.gba`、`RetroRegen-GBA-Test-v1.5.gba`、`Tetris.gba`、`song.gba` 等 | 真遊戲 smoke／畫面／相容性 |
| **進階 HLE BIOS（內建）** | 預設；不需真實 BIOS | post-boot／SWI／IRQ／header copy 測試 |
| `test-rom/` | 硬體測試 ROM 與原始碼（DMA、IRQ、PPU、timer、memory…） | **部分測試依賴**（例：`test-rom/ppu/hello.gba`）；其餘為手動驗證資產 |
| `docs/gbatek-gba-specs/` | GBATEK 17 章本地鏡像 | 規格查詢 |
| `docs/images/` | 實機截圖（`phase5_frame.png`） | Phase 5 驗證留存 |

ROM 不應提交到公開版控；`rom/` 是本機開發資產。專案不使用真實 BIOS 作為執行或 CI 前提；HLE 是正式路徑。

## 測試層次

1. **單元**：`tests/gbaemu/test_*.py`，不依賴外部 ROM，CI 必跑。
2. **Legacy golden**：`tests/test_*.py`，用 `pygba.pygba.PyGBA` 的舊引擎輸出做
   回歸；新引擎不直接重用其內部物件。
3. **真 ROM smoke**：`main.py`、`GBAEnv`、bounded capture；Phase 5 範例：
   `python main.py`（`window="null"`）可跑到健康警告畫面。
4. **硬體 test ROM**：需要時手動跑 `test-rom/` 並對照 GBATEK 數值。

## 已知近似與待驗證項目

以下項目已記錄在 `TODO.md` Open Questions，修改前先確認沒有破壞既有測試：

- Video contention 採「可視期間固定 +1」的 deterministic 模型；硬體只在控制器
  同時存取時插入 waitstate。
- Prefetch 只實作 prefetch-on（循序 fetch 1 cycle）與 prefetch-off 的
  Prefetch Disable Bug（1S→1N）；8-entry buffer 的 refill 尚未逐 halfword 模擬。
- 音訊取樣率固定 32768 Hz、只混 FIFO A/B；PSG 四聲道與 SOUNDBIAS 尚未套用。
- `HuffUnComp` 沿用 legacy 實作，尚無獨立向量測試。
- PPU 是 frame 結束一次合成，HBlank 期間的 VRAM 寫入下一 frame 才反映。
- 指令週期與 GBATEK 表可能有 ±1 cycle 差異（B/BL、STM n=2 等），需硬體 ROM 校準。

## 記錄新發現

- 行為差異 → `TODO.md` 的 Open Questions（附編號、觀測、影響）。
- 硬體數值 → `docs/spec/GBATEK_INDEX.md` 對應列，並在程式碼加 `# GBATEK:` 註解。
- 新的測試 ROM → 放 `test-rom/`，在 `docs/spec/GBATEK_INDEX.md` 的資產表補一列。
- Golden 重取 → 說明是時序／排程變更的預期結果，並在 commit message／TODO 記錄。
