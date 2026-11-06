# rom/（不進版控）

本專案**不會**分發任何 GBA ROM 或 Nintendo BIOS。請自行準備你合法擁有的檔案：

```text
rom/
  Dr_Mario.gba       # 任何 .gba（`python main.py` 會自動讀唯一的 .gba）
  bios/gba_bios.bin  # 選用：真實 BIOS（16 KiB）；冇就用內建 HLE
```

用法：

```powershell
# 預設讀 rom/ 入面唯一的 .gba；有多個就報錯，要你指定
python main.py

# 或直接指定任何路徑
python main.py "D:\games\some_game.gba"
```

電池存檔會寫在 ROM 旁邊、跟 ROM **同一個 stem** 的 `.sav`：
`Dr_Mario.gba` → `Dr_Mario.sav`（SRAM 32 KiB／Flash 64 KiB／Flash 128 KiB／
EEPROM 512 B／8 KiB，由 ROM 簽章自動偵測），下次開啟自動載入。
舊式 `<rom 全名>.sav`（例如 `Dr_Mario.gba.sav`）仍然會讀取，但新存檔一律用
stem 命名，所以不同 ROM 唔會撞存檔。
