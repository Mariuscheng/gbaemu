# GBATEK GBA 規格整理

本目錄將 [GBATEK](https://problemkaputt.de/gbatek.htm) 中與 Game Boy Advance（GBA）相關的內容，依主題拆分到不同資料夾；每個資料夾內都有一份 `spec.md`。

## 目錄

| 資料夾 | 主題 |
|---|---|
| `01-technical-data/` | [GBA Technical Data](01-technical-data/spec.md) |
| `02-memory-map/` | [GBA Memory Map](02-memory-map/spec.md) |
| `03-io-map/` | [GBA I/O Map](03-io-map/spec.md) |
| `04-video/` | [GBA LCD Video Controller](04-video/spec.md) |
| `05-sound/` | [GBA Sound Controller](05-sound/spec.md) |
| `06-timers/` | [GBA Timers](06-timers/spec.md) |
| `07-dma/` | [GBA DMA Transfers](07-dma/spec.md) |
| `08-communication/` | [GBA Communication Ports](08-communication/spec.md) |
| `09-keypad/` | [GBA Keypad Input](09-keypad/spec.md) |
| `10-interrupts/` | [GBA Interrupt Control](10-interrupts/spec.md) |
| `11-system-control/` | [GBA System Control](11-system-control/spec.md) |
| `12-cartridges/` | [GBA Cartridges](12-cartridges/spec.md) |
| `13-cgb-compatibility/` | [GBA Backwards Compatibility CGB Mode](13-cgb-compatibility/spec.md) |
| `14-unpredictable/` | [GBA Unpredictable Things](14-unpredictable/spec.md) |
| `15-arm-cpu/` | [ARM CPU Reference](15-arm-cpu/spec.md) |
| `16-bios/` | [BIOS Functions](16-bios/spec.md) |
| `17-connectors/` | [External Connectors](17-connectors/spec.md) |

## 來源與範圍

- 主要來源：[GBATEK - GBA/NDS Technical Info](https://problemkaputt.de/gbatek.htm)
- 作者／文件說明：Martin Korth（no$gba technical information）
- `ARM CPU Reference`、`BIOS Functions`、`External Connectors` 是 GBATEK 中被 GBA 章節引用的共用參考，因此一併保留。
- 原始抓取檔 `gbatek.htm` 與拆分腳本僅供整理用；實際閱讀請從各資料夾的 `spec.md` 開始。
