"""卡匣備份記憶體（GBATEK 12 章）：SRAM / Flash / EEPROM

由 ROM 內字串自動偵測：
  EEPROM_Vnnn     EEPROM 512B（V111/V120）或 8KB（V121/V122/V124）
  SRAM_Vnnn / SRAM_F_Vnnn   SRAM 32KB
  FLASH_Vnnn / FLASH512_Vnnn  Flash 64KB
  FLASH1M_Vnnn    Flash 128KB

存取方式：
  SRAM / Flash  → 0x0E000000-0x0E00FFFF（byte 存取；128K Flash 用 bank 切換）
  EEPROM        → 0x0D000000 區；每個 8/16/32-bit 存取 = 一條序列位元
                  （寫：bit0 為資料位；讀：回傳 0 或 1）
"""


class SaveSRAM:
    """SRAM 32KB：直接 byte 存取（資料匯流排 8-bit，16/32-bit 存取重複 byte）"""
    kind = "SRAM"

    def __init__(self):
        self.data = bytearray(b"\xFF" * 0x8000)

    def read8(self, off):
        return self.data[off & 0x7FFF]

    def read16(self, off):
        b = self.read8(off)
        return b | (b << 8)

    def read32(self, off):
        b = self.read8(off)
        return b | (b << 8) | (b << 16) | (b << 24)

    def write8(self, off, value):
        self.data[off & 0x7FFF] = value & 0xFF

    def write16(self, off, value):
        """16-bit store 落 8-bit 匯流排：只寫 1 個 byte——odd 位址係 high byte
        （jsmolka save/sram t006/t007 真機實測；mGBA GBAStore16 同款）"""
        self.write8(off, (value >> (8 * (off & 1))) & 0xFF)

    def write32(self, off, value):
        """32-bit store：只寫 1 個 byte，byte 由位址低 2 bit 揀（jsmolka t008/t009）"""
        self.write8(off, (value >> (8 * (off & 3))) & 0xFF)

    def export(self):
        return bytes(self.data)

    def load(self, buf):
        self.data[:] = buf


class SaveFlash:
    """Flash 64KB / 128KB：命令序列驅動

    命令：AA@5555 → 55@2AAA → 指令@5555
      90h = ID 模式（+0=man、+1=dev；F0h 離開）
      80h → 10h = 全部抹除、80h → 30h = 4KB 扇區抹除
      A0h = 寫入單 byte（下一個 byte 寫入即生效）
    128K 版：bank 切換 = 寫 0x0E000000（offset 0）
    """
    kind = "Flash"

    def __init__(self, size):
        self.size = size                    # 0x10000 或 0x20000
        self.data = bytearray(b"\xFF" * size)
        self.bank = 0
        self.seq = 0                        # 0=idle 1=收到 AA 2=收到 55 3=erase 5=write
        self.id_mode = False

    def _offset(self, off):
        return (self.bank * 0x10000 + (off & 0xFFFF)) % self.size

    def read8(self, off):
        if self.id_mode:
            o = off & 1
            if o == 0:
                return 0x62 if self.size > 0x10000 else 0xBF   # manufacturer
            return 0x13 if self.size > 0x10000 else 0xD4       # device
        return self.data[self._offset(off)]

    def read16(self, off):
        b = self.read8(off)
        return b | (b << 8)

    def read32(self, off):
        b = self.read8(off)
        return b | (b << 8) | (b << 16) | (b << 24)

    def write8(self, off, value):
        value &= 0xFF
        o = off & 0xFFFF
        if self.id_mode:
            if self.seq == 0 and o == 0x5555 and value == 0xAA:
                self.seq = 1
            elif self.seq == 1 and o == 0x2AAA and value == 0x55:
                self.seq = 2
            elif self.seq == 2 and o == 0x5555 and value == 0xF0:
                self.id_mode = False
                self.seq = 0
            return
        if self.seq == 0:
            if o == 0x5555 and value == 0xAA:
                self.seq = 1
                return
            if self.size > 0x10000 and o == 0:      # 128K：bank 切換
                self.bank = value & 1
                return
            return
        if self.seq == 1:
            self.seq = 2 if (o == 0x2AAA and value == 0x55) else 0
            return
        if self.seq == 2:
            if o == 0x5555 and value == 0x90:
                self.id_mode = True
                self.seq = 0
            elif o == 0x5555 and value == 0x80:
                self.seq = 3
            elif o == 0x5555 and value == 0xA0:
                self.seq = 5
            else:
                self.seq = 0
            return
        if self.seq == 3:                           # erase 指令中
            if o == 0x5555 and value == 0xAA:
                self.seq = 4
            else:
                self.seq = 0
            return
        if self.seq == 4:
            if o == 0x2AAA and value == 0x55:
                self.seq = 6                       # 等 10h/30h
            else:
                self.seq = 0
            return
        if self.seq == 6:
            if o == 0x5555 and value == 0x10:      # 全部抹除
                self.data[:] = b"\xFF" * self.size
            elif value == 0x30:                    # 4KB 扇區抹除
                base = self._offset(off) & ~0xFFF
                self.data[base:base + 0x1000] = b"\xFF" * 0x1000
            self.seq = 0
            return
        if self.seq == 5:                          # 寫入模式：下一個 byte
            self.data[self._offset(off)] = value & self.data[self._offset(off)]
            # Flash 只能把 1 變 0（抹除後才能回復 1）
            self.seq = 0
            return

    def write16(self, off, value):
        """16-bit store 落 8-bit 匯流排：只寫 1 個 byte——odd 位址係 high byte
        （jsmolka save/flash t006/t007 真機實測；mGBA GBAStore16 同款）"""
        self.write8(off, (value >> (8 * (off & 1))) & 0xFF)

    def write32(self, off, value):
        """32-bit store：只寫 1 個 byte，byte 由位址低 2 bit 揀（jsmolka t008/t009）"""
        self.write8(off, (value >> (8 * (off & 3))) & 0xFF)

    def export(self):
        return bytes(self.data)

    def load(self, buf):
        self.data[:] = buf


class SaveEEPROM:
    """EEPROM：序列位元協定（bit0 進出），頁面 8 bytes

    讀取：'11' + 位址(n bit) + '0' → 讀 68 bits（前 4 個忽略 + 64 data MSB first）
    寫入：'10' + 位址 + 64 data + '0'(stop) → 寫入 8 bytes
    閒置時讀取回傳 1（Ready）
    """
    kind = "EEPROM"

    def __init__(self, size):
        self.size = size                    # 0x200 或 0x2000
        self.n_addr = 6 if size == 0x200 else 14
        self.data = bytearray(b"\xFF" * size)
        self.bits = 0                       # 已收到的指令位元數
        self.mode = None                    # None / "read" / "write"
        self.addr = 0
        self.buf = 0                        # 64-bit 資料累積（MSB first）
        self.reading = False                # 讀取輸出階段
        self.read_count = 0
        self.read_page = 0
        self._left = None                   # DMA 串流剩餘位元數（位址寬度判斷用）

    def begin_stream(self, n):
        """DMA 串流開始：告知今次 transfer 總位元數

        位址寬度唔再跟芯片寫死（6 定 14 bit），而係動態判斷：
        寫入框：除最後 65 位（64 資料 + 停止位）外全部係位址；
        讀取框：除最後 1 位（'0' 終止位）外全部係位址。
        （與 mGBA 用 writeSize 判斷位址寬度嘅做法一致）
        """
        self._left = n

    def _commit_page(self):
        page = self.addr & (self.size // 8 - 1)
        for k in range(8):
            self.data[page * 8 + k] = (self.buf >> (8 * k)) & 0xFF
        self._reset_cmd()

    def _reset_cmd(self):
        self.bits = 0
        self.mode = None
        self.addr = 0
        self.buf = 0

    def read_bit(self):
        """每個讀取存取回傳一個 bit（0/1）"""
        if not self.reading:
            return 1                        # 閒置：Ready
        c = self.read_count
        self.read_count += 1
        if c < 4:                           # 4 個忽略位
            return 0
        if c < 68:                          # 64 個資料位（MSB first）
            page = self.read_page
            word = 0
            for k in range(8):
                word |= self.data[page * 8 + k] << (8 * k)
            return (word >> (63 - (c - 4))) & 1
        self.reading = False                # 讀完 → 回 Ready
        return 1

    def write_bit(self, bit):
        """每個寫入存取送進一個 bit（DMA 串流：位址寬度動態；否則固定寬度）"""
        bit &= 1
        left = self._left                   # 剩餘位元數（含當前位）
        if left is not None and left > 0:
            self._left = left - 1
        if self.reading:                    # 讀取中寫入 → 結束讀取
            self.reading = False
        if left is None or left <= 0:       # 單一存取：固定寬度（向後相容）
            self._write_bit_fixed(bit)
            return
        # ── DMA 串流：動態位址寬度 ──
        if self.bits == 0:                  # 第 1 個指令位
            self._cmd = bit
            self.bits = 1
            return
        if self.bits == 1:                  # 第 2 個指令位
            if self._cmd == 1 and bit == 1:
                self.mode = "read"
            elif self._cmd == 1 and bit == 0:
                self.mode = "write"
            else:
                self._reset_cmd()           # '0x' 開頭：非協定 → 重同步
                return
            self.bits = 2
            self.addr = 0
            self.buf = 0
            return
        if self.mode == "write":
            if left > 65:                   # 位址位（總長 − 65 之前）
                self.addr = (self.addr << 1) | bit
                self.bits += 1
                return
            if left > 1:                    # 64 個資料位
                self.buf = ((self.buf << 1) | bit) & 0xFFFFFFFFFFFFFFFF
                return
            if left == 1:                   # 停止位 → 寫入頁面
                self._commit_page()
            return
        if self.mode == "read":
            if left > 1:                    # 位址位（最後一位 = '0' 終止）
                self.addr = (self.addr << 1) | bit
                self.bits += 1
                return
            # left == 1：'0' 終止位 → 進入讀取輸出
            self.reading = True
            self.read_count = 0
            self.read_page = self.addr & (self.size // 8 - 1)
            self._reset_cmd()
            return
        self._reset_cmd()                   # 其他狀態：重同步

    def _write_bit_fixed(self, bit):
        """固定寬度解析（CPU 單一存取／無串流提示時）"""
        if self.bits == 0:                  # 第 1 個指令位
            self._cmd = bit
            self.bits = 1
            return
        if self.bits == 1:                  # 第 2 個指令位
            if self._cmd == 1 and bit == 1:
                self.mode = "read"
            elif self._cmd == 1 and bit == 0:
                self.mode = "write"
            else:
                self._reset_cmd()           # '0x' 開頭：非協定 → 重同步
                return
            self.bits = 2
            self.addr = 0
            self.buf = 0
            return
        if self.mode == "read":
            if self.bits < 2 + self.n_addr:     # 收位址（MSB first）
                self.addr = (self.addr << 1) | bit
                self.bits += 1
                return
            # 位址後的 don't-care 位 → 進入讀取輸出
            self.reading = True
            self.read_count = 0
            self.read_page = self.addr & (self.size // 8 - 1)
            self._reset_cmd()
            return
        if self.mode == "write":
            if self.bits < 2 + self.n_addr:     # 收位址（MSB first）
                self.addr = (self.addr << 1) | bit
                self.bits += 1
                return
            if self.bits < 2 + self.n_addr + 64:    # 收 64 data bits
                self.buf = ((self.buf << 1) | bit) & 0xFFFFFFFFFFFFFFFF
                self.bits += 1
                return
            # stop bit → 寫入頁面
            self._commit_page()
            return
        self._reset_cmd()                   # 其他狀態：重同步

    def export(self):
        return bytes(self.data)

    def load(self, buf):
        self.data[:] = buf


def detect_save(rom):
    """由 ROM 內容偵測存檔類型；回傳實例或 None"""
    i = rom.find(b"EEPROM_V")
    if i != -1:
        tail = rom[i + 8:i + 12]
        size = 0x200 if tail[:2] in (b"11",) or tail[:3] == b"120" else 0x2000
        return SaveEEPROM(size)
    if rom.find(b"SRAM_V") != -1 or rom.find(b"SRAM_F_V") != -1:
        return SaveSRAM()
    if rom.find(b"FLASH1M_V") != -1:
        return SaveFlash(0x20000)
    if rom.find(b"FLASH512_V") != -1 or rom.find(b"FLASH_V") != -1:
        return SaveFlash(0x10000)
    return None
