# rom/（不進版控）

本專案**不會**分發任何 GBA ROM 或 Nintendo BIOS。請自行準備你合法擁有的檔案：

```text
rom/
  rom.gba            # 任何 GBA ROM（`python main.py` 的預設路徑）
  bios/gba_bios.bin  # 選用：真實 BIOS（16 KiB）；冇就用內建 HLE
```

用法：

```powershell
# 預設讀 rom/rom.gba
python main.py

# 或直接指定任何路徑
python main.py "D:\games\some_game.gba"
```

電池存檔會寫在 ROM 旁邊的 `<rom>.sav`（SRAM 32 KiB／Flash 64 KiB／
Flash 128 KiB／EEPROM 512 B／8 KiB，由 ROM 簽章自動偵測），下次開啟自動載入。
