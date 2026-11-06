# GBA 逆向工程實務（以 gbaemu 為工具）

本文件整理「用這個模擬器理解一個 GBA ROM」的工作流、可重現的除錯步驟，以及
本專案實際遇過的案例。目標是**理解行為、建立最小測試**，不是重製或散布商業
ROM／BIOS。

> 法規與倫理：只使用自己合法 dump 的 ROM；不要把 ROM、BIOS、遊戲圖像
> 資產提交到公開版控。本專案不以真實 BIOS 為執行前提：預設使用內建進階
> HLE（clean-room，依 GBATEK 文件化行為實作）。

## 1. 先準備什麼

| 工具／資產 | 用途 |
|---|---|
| `rom/rom.gba` | 本機測試 ROM（目前為 BZPJ：Dr. Mario & Panel de Pon） |
| **進階 HLE BIOS（內建）** | 預設執行路徑；不需要真實 BIOS。涵蓋 post-boot state、SWI 0x00–0x2A、IRQ/BIOS 讀取保護近似 |
| `hle/` 測試與 oracle | 驗證 HLE 的 SWI／post-boot／header copy 行為 |
| `docs/spec/GBATEK_INDEX.md` | 硬體章節索引 |
| `docs/gbatek-gba-specs/` | GBATEK 本地鏡像（優先於網路版本） |
| `docs/spec/SPEC.md` | 本模擬器的權威 API／時序規格 |
| Ghidra／IDA／`arm-none-eabi-objdump` | 靜態反組譯（可選） |
| mGBA／硬體 | 行為對照（可選；模擬器 bug 不是硬體真相） |

### 反組譯起點

GBA ROM 的 CPU 視角基底是 `0x08000000`。用 binutils 快速看：

```powershell
arm-none-eabi-objdump -D -b binary -m arm `
  --adjust-vma=0x08000000 rom/rom.gba > rom.dis
```

CPU 是 ARM7TDMI（ARMv4T）；Ghidra 可用 `ARM:LE:32:v4t`、base `0x08000000`；Thumb 區段要手動切換
（或讓 Ghidra 的自動分析處理 `BX`／literal pool）。ROM header 在檔案 offset
`0x000-0x0BF`，entry point 在 `0x080000C0` 附近；`Emulator.from_rom()` 預設
用進階 HLE 建立等價的 post-boot state，不執行、也不需要真實 BIOS。

## 2. 模擬器提供的觀測介面

```python
from gbaemu import Emulator, EventKind, MemoryRegionKind

emu = Emulator.from_rom("rom/rom.gba")

# 跑到指定 frame；render=False 只跑硬體，不看畫面
emu.run_frames(360, render=False)

# 輸入（frame 邊界）
emu.input.set_buttons(a=True)
emu.run_frames(4, render=False)
emu.input.clear()

# 單 frame，取得 FrameResult（events、vblank、irq、halted）
result = emu.step_frame(render=True)
print(result.frame_index, result.cycles, result.vblank_started, result.halted)
for event in result.events:
    print(event.kind, hex(event.address) if event.address is not None else None)

# 畫面（240x160x3 RGB888）
image = emu.video.read_frame_array()

# 記憶體（debug peek；不消耗 cycle、不觸發硬體副作用）
print(hex(emu.memory.read_u32(0x04000000)))      # DISPCNT
vram = emu.memory.read_region(MemoryRegionKind.VRAM)
oam = emu.memory.read_region(MemoryRegionKind.OAM)
palette = emu.memory.read_region(MemoryRegionKind.PALETTE)

# CPU 狀態
print(hex(emu.cpu.read_register("r15")))
print(hex(emu.cpu.read_register("cpsr")))

# snapshot（含 CPU／bus／PPU／RAM／VRAM／IO）
data = emu.save_state()
emu.load_state(data)
emu.close()
```

### Breakpoint

```python
bp = emu.cpu.set_breakpoint(0x08000100, thumb=False)
result = emu.step_frame(render=False)
if result.events:
    ...
emu.cpu.clear_breakpoint(bp)
```

目前 breakpoint 在 frame 執行迴圈中比對 PC；適合定位「哪個 frame 跑到這段
code」。若要 instruction 級追蹤，開發時可暫時包住 `emu._cpu.step()`（私有
API，僅供除錯）：

```python
orig = emu._cpu.step
trace = []
def step():
    trace.append((emu._cpu.regs.r[15], emu._cpu.regs.cpsr))
    return orig()
emu._cpu.step = step
```

生產程式不要依賴私有 API。


## 3. Rust／Python／Cython 在逆向工程中的分工

逆向工程不是「全部用 Python」或「全部用 Rust」，而是依目的分工：

| 工作 | 建議語言 | 原因 |
|---|---|---|
| 跑 ROM、暫停、截圖、dump memory／VRAM／OAM／palette | **Python** | `Emulator`／`MemoryView`／`VideoView` 已在 Python；改腳本最快 |
| 寫自動化探索、批次比對、framebuffer golden | **Python** | pytest／numpy／PIL 生態；不用重編譯 |
| 讀寫 snapshot 外層（magic／version／CRC） | **Python** | 檔案格式與版本檢查屬 host 邏輯 |
| 觀察 CPU／PPU 行為、單步除錯 | **Python** | `CPUView`、breakpoint、`step_frame`；私有 API 可短暫使用 |
| 正式 CPU／bus／PPU／timing 執行 | **Rust** | 一次 frame 的 native boundary；不在 instruction 回 Python |
| Renderer／DMA／timer／IRQ 的正式路徑 | **Rust** | 與 CPU 同一個 core，避免跨語言呼叫 |
| Snapshot payload 的正式編碼／解碼 | **Rust** | 固定 layout、可與 core 狀態一起版本化 |
| Python extension／FFI | **Rust（PyO3）** | 不需要 Cython；一次 frame 邊界呼叫 |
| HLE BIOS（post-boot／SWI／IRQ／BIOS 讀取保護） | **Rust（production）**；Python reference 只作 differential | 不需要真實 BIOS；HLE 是 canonical 啟動路徑 |
| Legacy oracle／differential | **Python（Cython legacy 可選）** | 只作測試；不進 production wheel |

原則：

1. **探索用 Python，production 用 Rust。** 不要把逆向腳本寫進 Rust core。
2. **不要用 Cython 寫新的 RE 工具。** Cython 只在 legacy test／遷移對照。
3. 如果某個行為需要修改 timing，先寫 Python 假設／測試，再在 Rust core 實作；
   Python reference 是最後比對的 oracle。

## 4. Struct／二進位 layout

逆向時最重要的是「資料的實際 bytes」，不是語言裡的物件。以下 struct 是文件
用的參考 layout；正式 Rust 不要用 `#[repr(C)]` struct 直接 `transmute` 檔案
（padding／endianness 會漂移），要用明確的 little-endian 讀寫。

### 4.1 ROM header（0x000-0x0BF，192 bytes）

| Offset | Size | 欄位 |
|---|---|---|
| `0x00` | 4 | entry point（ARM branch） |
| `0x04` | 156 | Nintendo logo |
| `0xA0` | 12 | title |
| `0xAC` | 4 | game code |
| `0xB0` | 2 | maker code |
| `0xB2` | 1 | fixed `0x96` |
| `0xB3` | 1 | main unit |
| `0xB4` | 1 | device type |
| `0xB5` | 7 | reserved |
| `0xBC` | 1 | software version |
| `0xBD` | 1 | complement check |
| `0xBE` | 2 | checksum（little-endian） |

Rust 參考（FFI／overlay 用，不用於檔案 I/O）：

```rust
#[repr(C)]
pub struct RomHeader {
    pub entry: [u8; 4],
    pub logo: [u8; 156],
    pub title: [u8; 12],
    pub game_code: [u8; 4],
    pub maker: [u8; 2],
    pub fixed: u8,
    pub main_unit: u8,
    pub device: u8,
    pub reserved: [u8; 7],
    pub version: u8,
    pub complement: u8,
    pub checksum: u16,
}
```

Python 解析：

```python
import struct

ROM_HEADER = struct.Struct("<4s156s12s4s2sBBB7sBBH")
entry, logo, title, game_code, maker, fixed, main_unit, device, \
    reserved, version, complement, checksum = ROM_HEADER.unpack(data[:0xC0])
```

### 4.2 OAM：OBJ attributes 與 affine params 是交錯的

每個 OBJ 的 attributes 是 8 bytes：

```rust
#[repr(C)]
pub struct ObjAttr {
    pub attr0: u16,
    pub attr1: u16,
    pub attr2: u16,
    pub _pad: u16,   // 不是 attr；OAM 的 affine params 交錯在這段空間
}
```

`attr0`：

| Bits | 欄位 |
|---|---|
| 0-7 | Y |
| 8 | affine enable |
| 9 | double-size／disable（regular 時） |
| 10-11 | OBJ mode（0 normal／1 semi-transparent／2 OBJ window） |
| 12 | mosaic |
| 13 | 8bpp |
| 14-15 | shape（0 square／1 horizontal／2 vertical） |

`attr1`：

| Bits | 欄位 |
|---|---|
| 0-8 | X |
| 9-13 | affine parameter group（affine 時） |
| 12 | H flip（regular 時） |
| 13 | V flip（regular 時） |
| 14-15 | size |

`attr2`：

| Bits | 欄位 |
|---|---|
| 0-9 | tile number |
| 10-11 | priority |
| 12-15 | palette bank（4bpp） |

**Affine params 不是接在 attr2 後面。** 32 組參數交錯在 OAM 中：

```text
PA(group g) = OAM[0x006 + g*0x20]
PB(group g) = OAM[0x00E + g*0x20]
PC(group g) = OAM[0x016 + g*0x20]
PD(group g) = OAM[0x01E + g*0x20]
```

Rust 參考：

```rust
#[inline]
pub fn affine_params(oam: &[u8], group: usize) -> (i16, i16, i16, i16) {
    let base = 0x06 + (group & 0x1F) * 0x20;
    let read = |off: usize| i16::from_le_bytes([oam[base + off], oam[base + off + 1]]);
    (read(0), read(8), read(16), read(24))
}
```

Python 等價：

```python
def affine_params(oam: bytes, group: int):
    base = 0x06 + (group & 0x1F) * 0x20
    return tuple(struct.unpack_from("<h", oam, base + off)[0]
                 for off in (0, 8, 16, 24))
```

> 注意：OAM 只能做 16/32-bit 存取；8-bit 寫入會把值複製到同一個 16-bit
> 欄位的上下半部。這也是為什麼用 `struct` 的 `u16` 欄位而不是逐 byte 模型。
> affine interleave 的參考：<https://docs.rs/gba-addresses/latest/src/gba_addresses/oam.rs.html>。

### 4.3 DISPCNT／BGxCNT 的 bitfield

不要用 `#[repr(C)]` 直接疊 bitfield；用 raw `u16`＋accessor 最清楚、可攜。

```rust
#[derive(Clone, Copy)]
pub struct DispCnt(pub u16);

impl DispCnt {
    pub fn mode(self) -> u16 { self.0 & 0x7 }
    pub fn bg_enabled(self, bg: usize) -> bool { self.0 & (1 << (8 + bg)) != 0 }
    pub fn obj_enabled(self) -> bool { self.0 & 0x1000 != 0 }
    pub fn obj_1d(self) -> bool { self.0 & 0x0040 != 0 }
    pub fn force_blank(self) -> bool { self.0 & 0x0080 != 0 }
}

#[derive(Clone, Copy)]
pub struct BgCnt(pub u16);

impl BgCnt {
    pub fn priority(self) -> u16 { self.0 & 0x3 }
    pub fn char_base(self) -> u32 { ((self.0 >> 2) & 0x3) as u32 * 0x4000 }
    pub fn screen_base(self) -> u32 { ((self.0 >> 8) & 0x1F) as u32 * 0x800 }
    pub fn color_256(self) -> bool { self.0 & 0x0080 != 0 }
    pub fn mosaic(self) -> bool { self.0 & 0x0040 != 0 }
    pub fn size(self) -> u16 { (self.0 >> 14) & 0x3 }
}
```

Python 對照：

```python
def bg_cnt(raw: int):
    return {
        "priority": raw & 0x3,
        "char_base": ((raw >> 2) & 0x3) * 0x4000,
        "screen_base": ((raw >> 8) & 0x1F) * 0x800,
        "color_256": bool(raw & 0x80),
        "mosaic": bool(raw & 0x40),
        "size": (raw >> 14) & 0x3,
    }
```

### 4.4 Snapshot／CPU state struct

正式 snapshot 不要直接 dump Rust struct（padding／欄位順序會變）。用固定
little-endian encoder；Python 外層加 magic／version／CRC。

```rust
// 只是概念 layout；實際 encode 用欄位逐一寫入
pub struct CpuState {
    pub regs: [u32; 16],
    pub cpsr: u32,
    pub spsr: u32,
    pub mode: u8,
    pub halted: bool,
    pub wait_irq: u16,
}
```

Python 解析外層：

```python
SNAP_HEADER = struct.Struct("<4sHHII")  # magic, version, flags, cycles, rom_crc
magic, version, flags, cycles, rom_crc = SNAP_HEADER.unpack(data[:16])
payload = data[16:]
```

原則：

- `#[repr(C)]` 只用於 FFI／overlay；snapshot 用 `to_le_bytes()` 逐欄位編碼。
- 每個 snapshot 版本都要有 `version`；不要用「Rust struct 大小」當版本。
- OAM affine params 用 `i16`；palette 用 `u16`（15-bit 有效）。
- Python `struct.Struct("<...")` 是無 padding 的；不要用 native `@` 格式讀檔。

## 5. 記憶體地圖與常用暫存器

| 區域 | 位址 | 用途 |
|---|---|---|
| BIOS | `0x00000000-0x00003FFF` | 開機、SWI、IRQ stub |
| EWRAM | `0x02000000-0x0203FFFF` | 256 KiB 工作 RAM |
| IWRAM | `0x03000000-0x03007FFF` | 32 KiB 快速 RAM／stack |
| I/O | `0x04000000-0x040003FF` | 硬體暫存器 |
| Palette | `0x05000000-0x050003FF` | BG/OBJ 15-bit 色 |
| VRAM | `0x06000000-0x06017FFF` | BG／OBJ tile／map、bitmap |
| OAM | `0x07000000-0x070003FF` | 128 個 sprite |
| ROM | `0x08000000-0x0DFFFFFF` | 卡匣；鏡像依大小 |
| SRAM/Flash | `0x0E000000-0x0E00FFFF` | 存檔（8-bit） |

常用 I/O：

| 位址 | 名稱 | 看什麼 |
|---|---|---|
| `0x04000000` | DISPCNT | mode（0-5）、BG/OBJ enable、force blank、1D/2D OBJ |
| `0x04000004` | DISPSTAT | VBlank/HBlank/VCount IRQ、目前旗標 |
| `0x04000006` | VCOUNT | 目前 scanline（0-227） |
| `0x04000008+` | BG0-3CNT | priority、char base、screen base、size、8bpp、mosaic |
| `0x04000010+` | BG0-3HOFS/VOFS | scroll |
| `0x04000020+` | BG2/3 affine | PA/PB/PC/PD、ref |
| `0x04000040-0x4A` | WIN0/1、WININ/OUT | window 範圍與遮罩 |
| `0x04000050-0x54` | BLDCNT/ALPHA/Y | alpha、brighten/darken |
| `0x040000B0+` | DMA | source/dest/control |
| `0x04000100+` | Timers | reload/control |
| `0x04000130` | KEYINPUT | active-low 按鍵 |
| `0x04000200-0x208` | IE/IF/IME | 中斷 |

## 6. 畫面逆向流程

### Step 1：先確定 PPU mode 與 layer

```python
ppu = emu._bus.ppu
dispcnt = ppu.dispcnt
print("mode", dispcnt & 7, "DISPCNT", hex(dispcnt))
for bg in range(4):
    cnt = ppu.read_reg16(0x008 + bg * 2)
    print("BG", bg, "cnt", hex(cnt),
          "enabled", bool(dispcnt & (1 << (8 + bg))),
          "priority", cnt & 3,
          "8bpp", bool(cnt & 0x80),
          "size", (cnt >> 14) & 3)
```

- `mode 0/1/2`：text／affine BG＋OBJ。
- `mode 3/4/5`：bitmap；不需要 tile map。
- `DISPCNT bit 12`：OBJ enable；`bit 6`：OBJ 1D mapping（0=2D）。
- `DISPCNT bit 7`：force blank；先排除。

### Step 2：把 BG 與 OBJ 分開看

先只渲染 BG（暫時把 OAM 當空，或把 DISPCNT 的 OBJ bit 清掉），再看只渲染
OBJ。若 BG 乾淨、合成後才壞，問題在 sprite／window／blend，不是 tile map。

本專案案例：Dr. Mario 標題的 BG2 單獨渲染完全正常，壞的是 OBJ 文字。

### Step 3：tile／map 的常見錯誤

| 症狀 | 先檢查 |
|---|---|
| 整片同一個圖案 | sprite 多 tile 只取 tile 0；或 tile number 沒加 row/col |
| 圖案上下錯位 | text BG／OBJ 的 vertical flip（`tile bit 11`） |
| 圖案左右錯位 | horizontal flip（`tile bit 10`） |
| 顏色整組錯 | palette bank（4bpp `tile>>12`）、OBJ palette base `0x05000200` |
| 8bpp 圖錯 | tile number bit0 忽略、`tile & 0x3FE`、address `tile*32` |
| 2D OBJ 錯 | tile 編號列距是 32（4bpp）／16（8bpp），不是 sprite 寬度 |
| BG 位置錯 | screen base、map block（32×32 tile 一塊，0x800 bytes） |

### Step 4：OBJ 的兩個 mapping

```text
1D：tile = tnum + (py//8)*(w//8)*step + (px//8)*step
2D：tile = tnum + (py//8)*32 + (px//8)*step
step = 2 if 8bpp else 1
```

- 2D 是 32×32 tile 的 grid；sprite 的下一列不是 `tile + w/8`，而是
  `tile + 32`。
- 一個 32×16 sprite 由 4×2 個 8×8 tile 組成；只取 `tnum` 會得到重複方塊。
- 8bpp：`tile &= 0x3FE`，資料位址 `0x10000 + tile*32`。
- affine sprite 的 tile layout 以 double-size bounding box 為準。

### Step 5：最小重現

把觀察到的 register／VRAM／OAM 寫成 unit test，不要只靠截圖：

```python
# tests/gbaemu/test_ppu_modes.py 風格
# 1. 建最小 PPU/OAM/VRAM state
# 2. 設定 DISPCNT、BGxCNT、tile map、tile data
# 3. 呼叫 render_frame
# 4. 比對 framebuffer 的關鍵 pixel
```

## 7. 程式碼逆向流程

1. **定位畫面寫入者**：先用 breakpoint 找 VBlank handler／main loop；再看
   DISPCNT/BGxCNT 的寫入。
2. **找資料來源**：VRAM 位址、DMA source、ROM 壓縮資料（LZ77／RLE／Huffman
   BIOS SWI 或自訂格式）。
3. **找邏輯**：輸入讀取（KEYINPUT）、狀態機、計時器／VBlank 遞增。
4. **建立假設→改 memory→看畫面**：`emu.memory.force_write()` 可在下一個
   frame 前改值；適合驗證「這個 byte 是不是 sprite tile」。
5. **回到靜態分析**：把 PC／位址記下來，用 Ghidra 對照；不要只靠動態猜測。

### 讀寫追蹤

目前 API 的 watchpoint 事件型別已存在（`WATCHPOINT_READ/WRITE`），但完整
watchpoint 介面不是 Phase 1 的保證；除錯時可在 `MemoryView` 外層包一層
Python wrapper，記錄呼叫位址。效能會下降，只用於短區間。

## 8. 案例：Dr. Mario 標題畫面 corruption

### 症狀

- 警告畫面正常。
- 過了 Intelligent Systems logo 後，標題畫面底部版權文字變成重複方塊，
  中央出現綠色亂碼。
- 使用者提供截圖，懷疑 BG tile 錯。

### 診斷

1. 跑到標題（frame ~789/1065），讀 DISPCNT：

   ```text
   DISPCNT = 0x1400  → mode 0、BG2 enable、OBJ enable、2D OBJ mapping
   BG2CNT  = 0x1c02  → text BG、priority 2、256×256、4bpp
   ```

2. 只渲染 BG2：畫面乾淨（logo／背景／`&` 正常）→ 不是 BG tile map。
3. 只渲染 OBJ：底部文字重複同一組方塊 → sprite tile 解碼錯。
4. OAM 0-3 是 `32×16` 文字 sprite，tile 0/4/8/12；只取 tile 0 會重複。

### 根因

- **多 tile sprite**：32×16 由 4×2 tiles 組成，renderer 只取 `sprite.tile`。
- **2D mapping**：sprite 下一列的 tile 編號要 `+32`，不是 `+w/8`。
- **8bpp**：tile number step 2、`tile & 0x3FE`。
- **text BG vertical flip**：fast tile buffer 漏了 `tile bit 11`。

### 修正

- `_sprite_pixel()`：依 1D/2D 算 `tile_index`，再取 `(py%8, px%8)`。
- `_text_buffer()`：`row_py = 7-py if tile & 0x800 else py`。
- sprite 改成 per-sprite bounding box 的 layer buffer，避免每 pixel 掃 128 OAM。
- 修正後標題可看到正確的 `PRESS START`／`© 2005 Nintendo`。

### 回歸測試

```powershell
pytest tests/gbaemu/test_ppu.py tests/gbaemu/test_ppu_modes.py -q
pytest tests -q
```

## 9. 時序與 CPU 逆向

- 一個 frame = `280,896` cycles；一條 scanline = `1,232`；共 `228` 條。
- VBlank 從 line 160 開始（cycle `197,120`）。
- `DISPCNT`、`BGxCNT` 可能在 HBlank/VBlank 被改；frame-end renderer 只看
  最後狀態。若畫面需要 mid-frame 效果，必須用 scanline renderer 或 event。
- HALT 時 CPU 等 `IE & IF`；IntrWait 只看指定 flags。若遊戲「慢」先分辨是
  CPU-bound 還是 renderer-bound：`render=False` 仍慢 → CPU／bus，不是繪圖。

### 本專案量測案例

```text
Dr. Mario 標題、frame ~1065：
  render=False 約 2–5 fps
  render=True  約 2–5 fps
  CPU instructions/frame 約 15,764
  熱門 PC 在 IWRAM 0x03003108-0x03003168（軟體混音／動畫迴圈）
```

結論：這個畫面是 CPU-bound，不是 renderer；只優化繪圖不會讓遊戲變順。


## 10. CPU 指令對齊

GBA 的 ARM7TDMI 沒有 cache，但 **pipeline 與 PC 對齊** 會直接影響 branch、
literal pool、exception return 與 unaligned access。逆向時若 PC 差 2／4 bytes，
通常不是「遊戲 bug」，而是 pipeline 值算錯。

### 10.1 PC 的可見值

| 狀態 | 讀 R15 得到的值 | 備註 |
|---|---|---|
| ARM | 目前 instruction 位址 + 8 | 兩級 pipeline |
| Thumb | 目前 instruction 位址 + 4 | 兩級 pipeline |
| ARM `STR pc` | 目前位址 + 12 | store 用 pipeline 後的值 |
| ARM `BL` | `LR = 目前位址 + 4` | 回傳位址 |
| Thumb `BL/BLX` | `LR = 回傳位址 \| 1`（Thumb） | 由 instruction 決定 |

- ARM 的資料處理 operand 讀到 `R15` 時，是 `pc+8`；不要用「目前 PC」。
- Thumb 的 literal load（`LDR Rd, [pc, #imm]`）以 `(pc+4) & ~3` 為 base。
- `R15` 被寫入（`MOV pc`／`LDR pc`／`BX`）代表 pipeline flush；不要把下一條
  instruction 當成已 prefetch。

### 10.2 alignment 規則

```text
ARM fetch：       pc & ~3
Thumb fetch：     pc & ~1
ARM B/BL target： (pc + 8 + sign_extend(imm24 << 2)) & ~3
Thumb B target：  (pc + 4 + sign_extend(imm11 << 1)) & ~1
BX：              target bit0 選 ARM/Thumb；進入 ARM 時 target & ~3，
                  進入 Thumb 時 target & ~1
```

- `LDR pc`／`MOV pc` 在 ARMv4T 不改變 T bit；PC 低位依 CPU state 對齊。
- `LDR` word 的 unaligned address：ARMv4T 會 rotate（`addr & 3`），不是 fault。
- `LDRH/STRH` unaligned 行為依硬體；不要用一般 `u16` 讀寫直接假設，應用手上
  的 test ROM／硬體實測。
- SRAM／Flash 只支援 8-bit；對 SRAM 做 32-bit `LDR` 是錯的。
- VRAM／Palette／OAM 有 16/32-bit 存取限制；8-bit 寫入 OAM 會複製到同一個
  16-bit 欄位的上下半部。

### 10.3 除錯方法

1. 在 branch／`BX`／`LDR pc` 設 breakpoint，記錄 **instruction 位址**、`R15`、
   CPSR T bit。
2. 用 `emu.memory.read_u32(pc)` 確認實際 fetch 的 word；Thumb 用 `read_u16`。
3. 若 PC 每次差固定值，先檢查 pipeline offset（ARM +8／Thumb +4）與
   `pc & ~3`／`& ~1`。
4. 若只有某條 branch 錯，檢查 sign extension 與 target alignment。
5. 寫最小 test：放一條 `B`／`BL`／`BX`，比對 `R15`、`LR`、CPSR.T。

Rust 參考：

```rust
#[inline]
pub fn arm_pc(instr_addr: u32) -> u32 { instr_addr.wrapping_add(8) }

#[inline]
pub fn thumb_pc(instr_addr: u32) -> u32 { instr_addr.wrapping_add(4) }

#[inline]
pub fn arm_fetch(addr: u32) -> u32 { addr & !3 }

#[inline]
pub fn thumb_fetch(addr: u32) -> u32 { addr & !1 }

#[inline]
pub fn arm_branch_target(instr_addr: u32, imm24: u32) -> u32 {
    let off = ((imm24 << 8) as i32) >> 6; // sign extend 24 -> 26
    instr_addr.wrapping_add(8).wrapping_add(off as u32) & !3
}
```

### 10.4 解碼陷阱（Rust／Python differential 抓到）

- **MRS/MSR 與 data processing 重疊**：`MRS r0,CPSR`（`0xE10F0000`）的 bits
  24-21 看起來像 `TST`；必須在 data-processing 之前解碼，否則會變成改旗標。
- **bit4 不代表一定是 register shift**：data processing 的 bit4=1 只有在 bit7=0
  時才是暫存器移位；bit7=1 屬於 halfword/signed transfer、MUL、SWP。
- **乘加長指令的週期遮罩**：`UMULL/MLA` 的判定必須包含 bits 7-4 = `1001`，
  只比 `(instr >> 23) & 0x1F == 1` 會把 `ADDS` 誤認成乘加長。
- **Thumb `00011` 是 ADD/SUB**：format 1 只涵蓋 `00000/00001/00010`；
  用 `(instr >> 13) == 0` 會把 register ADD 當成 ROR。
- **Thumb 移位量 0**：LSL/LSR/ASR/ROR raw=0 完全不動 C；ROR 的 32 倍數
  則是值不變、C=bit31，兩者不同。
- **ARM RRX vs ROR #0**：立即值 `ROR #0` 是 RRX（C 進 bit31）；暫存器
  `ROR #0`／`#32` 是 no-op 且保留 C。

## 11. Timer 準確度

Timer 是最容易被「chunk tick」弄不準的地方：如果每次只呼叫
`timers.tick(chunk_cycles)` 並在 chunk 結尾才處理 overflow，IRQ 會晚幾個
cycle，prescaler 餘數也會漂移。

### 11.1 暫存器與語意

```rust
#[repr(C)]
pub struct TimerRegs {
    pub cnt_l: u16,   // reload（寫入）／目前 counter（讀取）
    pub cnt_h: u16,   // prescaler、cascade、IRQ、start
}
```

`TMxCNT_H`：

| Bits | 欄位 |
|---|---|
| 0-1 | prescaler：0=F/1、1=F/64、2=F/256、3=F/1024 |
| 2 | cascade（count-up；timer 0 不支援） |
| 6 | overflow IRQ enable |
| 7 | start |

基本語意（以 GBATEK 與 test ROM 驗證為準）：

- start 0→1：counter 從 reload 載入，之後開始計數。
- counter 到 `0xFFFF` 後，下一個 prescaler tick 溢位 → reload、可發 IRQ。
- cascade：前一級 overflow 時，下一級 counter +1；cascade timer 忽略自己的
  prescaler。
- 寫 `TMxCNT_L` 只改 reload，不改目前 counter；讀 `TMxCNT_L` 回目前 counter。
- stop：counter 保留；重新 start 0→1 才 reload。
- HALT 不會停止 timer；timer 可在 CPU halted 時發 IRQ 喚醒。

### 11.2 準確的 event-driven 模型

不要讓 timer 自己「按 chunk 累加」；用**絕對 cycle**排程：

```rust
pub struct Timer {
    counter: u16,
    reload: u16,
    control: u16,
    prescaler: u32,
    phase: u32,            // 已經過但未滿一個 prescaler tick 的 cycle
    next_overflow: u64,    // 絕對 cycle；None 表示停止
    running: bool,
    cascade: bool,
    irq_enable: bool,
}
```

```text
advance_to(target_cycle):
  while running and next_overflow <= target_cycle:
      now = next_overflow
      counter = reload
      if irq_enable: raise IRQ at now
      cascade_to_next(now)
      next_overflow = now + (0x10000 - reload) * prescaler
  phase = target_cycle - last_update
  // 或直接用 next_overflow 反推 counter，不每 cycle 更新
```

要點：

1. **保留 prescaler 餘數**：`phase` 或 `next_overflow` 必須跨 stop/start、reload、
   control 寫入一致；不要每次 `tick()` 重新 divmod 後丟掉誤差。
2. **同 cycle 的 cascade 順序固定**：timer0→1、timer2→3；前一級 overflow 與
   下一級 increment 視為同一 cycle，順序寫進 scheduler，不要用 dict 迭代。
3. **IRQ 在 overflow cycle 發生**，不是 chunk 結尾；IF bit 設定後，CPU 的
   IRQ pipeline delay 另計。
4. **CPU／PPU／DMA／timer 共用同一個 cycle domain**：用 `u64` absolute cycle，
   不用 float 或 wall clock。
5. **寫入時重算 next event**：control/reload 改變後，從當前 cycle 重算
   `next_overflow`，不要保留舊排程。
6. **讀 counter 在當前 cycle 取值**：先 `advance_to(now)` 再回傳，避免 stale。

### 11.3 驗證方法

- 用 `test-rom/timer/`（若存在）或自寫最小 ROM：固定 reload／prescaler，
  量測兩個 timer IRQ 之間的 cycle 數。
- 測 edge cases：
  - start 0→1 的第一次 reload
  - reload 設 0xFFFF（每個 prescaler tick 溢位）
  - prescaler 64／256／1024 的除數餘數
  - cascade timer0→timer1
  - stop 後再 start
  - 寫 reload 時 counter 正在倒數
  - HALT 中 timer IRQ 喚醒
- 用 frame cycle 對帳：一個 frame `280,896` cycles；VBlank 從 cycle
  `197,120` 開始。若 timer IRQ 數量在 N frame 內與硬體差 1，先查 chunk
  rounding，不要先改 prescaler 表。

目前 Python reference 的 `Timers.tick(cycles)` 是 chunk 級模型；正式 Rust
core 應使用上述 absolute-cycle scheduler，Python 只負責驗證與 oracle。

## 12. 逆向檢查清單

- [ ] 確認 ROM header／entry point、HLE post-boot state（SP／mode／PC／header copy）
- [ ] 記錄 frame、DISPCNT、mode、BG/OBJ enable
- [ ] 分别隔離 BG 與 OBJ
- [ ] 檢查 palette／VRAM／OAM 的實際 bytes
- [ ] 確認 1D/2D mapping、4bpp/8bpp、flip、palette bank
- [ ] 檢查 PC pipeline offset（ARM +8／Thumb +4）與 branch target alignment
- [ ] 測 unaligned `LDR` rotation、`LDRH`／SRAM 寬度
- [ ] timer：prescaler 餘數、cascade、overflow IRQ 是否在同一個 cycle
- [ ] 用 `force_write` 做最小假設驗證
- [ ] 把假設寫成 unit test／framebuffer golden
- [ ] 用 mGBA／硬體對照（避免把模擬器 bug 當規格）
- [ ] 更新 `docs/spec/GBATEK_INDEX.md` 或 `TODO.md` 的未解問題

## 13. 常見陷阱

1. **把模擬器 bug 當硬體行為**：先用 test ROM／硬體對照。
2. **只看截圖**：要 dump VRAM/OAM/palette 與 register。
3. **忽略 palette bank**：4bpp tile 的 `tile>>12` 是 palette bank。
4. **忽略 OBJ 2D mapping**：`tile+1` 只對同一列有效。
5. **忽略 vertical flip**：text BG 與 OBJ 都有。
6. **frame-end 只看最後狀態**：mid-frame 寫入會被忽略。
7. **HLE 是正式路徑，不是捷徑**：SWI／IRQ return／BIOS 讀取保護必須以 HLE
   實作並用測試驗證；不要把「沒有真 BIOS」當成可以跳過行為的理由。真 BIOS
   只可作使用者自備的 optional differential，不進 CI、不進 production。
8. **SRAM 寬度**：SRAM 只支援 8-bit；32-bit 存取會錯。
9. **ROM 鏡像**：大於實體大小的位址會鏡像，不要假設 linear。

## 14. 相關文件

- [硬體規格索引](../spec/GBATEK_INDEX.md)
- [模擬器規格](../spec/SPEC.md)
- [開發與測試流程](DEVELOPMENT.md)
- [架構文件](../architecture/ARCHITECTURE.md)
- [Native core 設計](../architecture/NATIVE_CORE.md)
