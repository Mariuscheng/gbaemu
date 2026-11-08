"""GBA I/O 暫存器（規格 §3.4；GBATEK: GBA I/O Map）。

Phase 2 先實作 CPU／PPU／輸入需要的核心暫存器：

* ``DISPCNT``（0x000）、``DISPSTAT``（0x004）、``VCOUNT``（0x006）
* ``KEYINPUT``（0x130，active-low）、``KEYCNT``（0x132）
* ``IE``（0x200）、``IF``（0x202）、``IME``（0x208）、``WAITCNT``（0x204）
* ``POSTFLG``（0x300）、``HALTCNT``（0x301；Phase 3 才處理 halt）

其餘位址以 raw storage 保存（Phase 2/3 逐項補語意，不會 silently 消失）。

# GBATEK: GBA I/O Map - 4000000h-40003FFh 區域；LCD I/O Registers；
# GBA Keypad Input - KEYINPUT active-low；GBA Interrupt Control - IME/IE/IF
"""

from __future__ import annotations

import struct

IO_SIZE = 0x400

# Sound 暫存器寫入遮罩（同 Rust `Bus::write_sound16`）。Python 的 SoundController
# 保留未遮罩的原始值，但 BUS snapshot 的 raw IO 要同 Rust 一致，所以另外鏡射
# 一份已遮罩的 bytes；CPU 讀取仍然經 SoundController（行為不變）。
_SOUND_WRITE_MASKS = {
    0x60: 0x007F,
    0x62: 0xFFC0,
    0x64: 0x4000,
    0x68: 0xFFC0,
    0x6C: 0x4000,
    0x70: 0x00E0,
    0x72: 0xE000,
    0x74: 0x4000,
    0x7C: 0x40FF,
    0x80: 0xFF77,
    0x82: 0x770F,
    0x84: 0x0080,
    0x88: 0xC3FE,
}

# 中斷位元（GBATEK: GBA Interrupt Control - IE/IF）
IRQ_VBLANK = 1 << 0
IRQ_HBLANK = 1 << 1
IRQ_VCOUNT = 1 << 2
IRQ_TIMER0 = 1 << 3
IRQ_DMA0 = 1 << 8
IRQ_KEYPAD = 1 << 12


class IoRegisters:
    """0x04000000 起 1 KiB 的暫存器檔案。"""

    def __init__(self, *, keypad=None, ppu=None, dma=None, timers=None, sound=None) -> None:
        self._bytes = bytearray(IO_SIZE)
        self._ie = 0
        self._if = 0
        self._irq_seen = 0
        self._ime = 0
        self._irq_line = False
        self._irq_line = False
        self.keypad = keypad  # 需提供 ``keyinput_mask`` property
        self.ppu = ppu
        self.dma = dma
        self.timers = timers
        self.sound = sound
        self.halt_requested = False
        self._keypad_irq_active = False

    # ------------------------------------------------------------------
    # 讀取
    # ------------------------------------------------------------------
    def read8(self, offset: int) -> int:
        offset &= 0x3FF
        return (self.read16(offset & ~1) >> ((offset & 1) * 8)) & 0xFF

    def read16(self, offset: int) -> int:
        offset &= 0x3FE
        if offset == 0x000:
            return self.ppu.dispcnt if self.ppu is not None else self._get16(0x000)
        if offset == 0x004:
            return self.ppu.dispstat() if self.ppu is not None else self._dispstat()
        if offset == 0x006:
            return self.ppu.vcount if self.ppu is not None else 0
        if 0x008 <= offset < 0x060 and self.ppu is not None:
            return self.ppu.read_reg16(offset)
        if offset == 0x130:
            return self._keyinput()
        if offset == 0x200:
            return self._ie
        if offset == 0x202:
            return self._if
        if offset == 0x208:
            return self._ime
        if 0xB0 <= offset < 0xE0 and self.dma is not None:
            return self.dma.read16(offset)
        if 0x100 <= offset < 0x110 and self.timers is not None:
            return self.timers.read16(offset)
        if self.sound is not None and 0x060 <= offset < 0x0B0:
            return self.sound.read16(offset)
        return self._get16(offset)

    def read32(self, offset: int) -> int:
        offset &= 0x3FC
        return self.read16(offset) | (self.read16(offset + 2) << 16)

    def read(self, offset: int, width: int = 1) -> int:
        if width not in (1, 2, 4):
            raise ValueError(f"不支援的存取寬度：{width}")
        if width == 1:
            return self.read8(offset)
        if width == 2:
            return self.read16(offset)
        return self.read32(offset)

    # ------------------------------------------------------------------
    # 寫入
    # ------------------------------------------------------------------
    def write8(self, offset: int, value: int) -> None:
        value &= 0xFF
        offset &= 0x3FF
        if self.sound is not None and 0x060 <= offset < 0x0B0:
            self.sound.write8(offset, value)
            if not 0x0A0 <= offset <= 0x0A7:
                aligned = offset & ~1
                shift = (offset & 1) * 8
                current = self._get16(aligned)
                self._store_sound16(aligned, (current & ~(0xFF << shift)) | (value << shift))
            return
        if offset in (0x202, 0x203):  # IF：寫 1 清除
            self._if &= ~(value << ((offset & 1) * 8)) & 0x3FFF
            return
        if offset == 0x301 and value & 0x80:  # HALTCNT
            self.halt_requested = True
        aligned = offset & ~1
        shift = (offset & 1) * 8
        current = self.read16(aligned)
        self.write16(aligned, (current & ~(0xFF << shift)) | (value << shift))

    def write16(self, offset: int, value: int) -> None:
        value &= 0xFFFF
        offset &= 0x3FE
        if offset == 0x202:  # IF：寫 1 清除（acknowledge）
            self._if &= ~value & 0x3FFF
            self._refresh_irq_line()
            return
        if offset == 0x006:  # VCOUNT：唯讀
            return
        if 0xB0 <= offset < 0xE0 and self.dma is not None:
            self.dma.write16(offset, value)
            return
        if 0x100 <= offset < 0x110 and self.timers is not None:
            self.timers.write16(offset, value)
            return
        if 0x008 <= offset < 0x060 and self.ppu is not None:
            self.ppu.write_reg16(offset, value)
            # 同步存一份 raw bytes：snapshot 的 I/O section 只存 `_bytes`，
            # 這區若不寫入就會在存檔／讀檔後全部變 0（BGxCNT／WININ／BLDCNT…），
            # renderer 會畫空白或錯層。
            self._write16(offset, value)
            return
        if self.sound is not None and 0x060 <= offset < 0x0B0:
            self.sound.write16(offset, value)
            if not 0x0A0 <= offset <= 0x0A7:
                self._store_sound16(offset, value)
            return
        if offset == 0x000 and self.ppu is not None:
            self.ppu.write_dispcnt(value)
        elif offset == 0x004 and self.ppu is not None:
            self.ppu.write_dispstat(value)
        self._write16(offset, value)

    def write32(self, offset: int, value: int) -> None:
        value &= 0xFFFFFFFF
        offset &= 0x3FC
        if self.sound is not None and 0x060 <= offset < 0x0B0:
            self.sound.write32(offset, value)
            if not 0x0A0 <= offset <= 0x0A7:
                self._store_sound16(offset, value & 0xFFFF)
                self._store_sound16(offset + 2, (value >> 16) & 0xFFFF)
            return
        if 0x100 <= offset < 0x110 and self.timers is not None:
            self.timers.write32(offset, value)
            return
        self.write16(offset, value & 0xFFFF)
        self.write16(offset + 2, (value >> 16) & 0xFFFF)

    def write(self, offset: int, width: int, value: int) -> None:
        if width not in (1, 2, 4):
            raise ValueError(f"不支援的存取寬度：{width}")
        if width == 1:
            self.write8(offset, value)
        elif width == 2:
            self.write16(offset, value)
        else:
            self.write32(offset, value)

    def debug_write(self, offset: int, width: int, value: int) -> None:
        """除錯寫入：IF 的 1 代表「設起」而不是清除（測試／工具用）。"""

        offset &= 0x3FF
        if offset in (0x202, 0x203):
            shift = (offset & 1) * 8
            self._if |= ((value << shift) & 0xFFFF) & 0x3FFF
            self._refresh_irq_line()
            return
        if width == 1:
            self.write8(offset, value)
        elif width == 2:
            self.write16(offset, value)
        else:
            self.write32(offset, value)

    # ------------------------------------------------------------------
    # 中斷
    # ------------------------------------------------------------------
    def _refresh_irq_line(self) -> None:
        self._irq_line = bool(self._ime and (self._ie & self._if))

    @property
    def irq_line(self) -> bool:
        """IME=1 且 IE&IF≠0；CPU check_irq 的快取 IRQ 線。"""

        return self._irq_line

    def request_irq(self, mask: int) -> None:
        """拉起 IF 位元（latch；由 CPU 以寫 1 清除）。"""

        self._if |= mask & 0x3FFF
        # IntrWait 用：記住「出現過」的 IRQ（就算 handler 之後 ack 了）。
        self._irq_seen |= mask & 0x3FFF
        self._refresh_irq_line()

    @property
    def irq_seen(self) -> int:
        return self._irq_seen

    def clear_irq_seen(self, mask: int) -> None:
        self._irq_seen &= ~mask & 0x3FFF

    def acknowledge_irq(self, mask: int) -> None:
        self._if &= ~mask & 0x3FFF
        self._refresh_irq_line()

    @property
    def interrupts(self) -> tuple[int, int, int]:
        """(IME, IE, IF)。"""

        return self._ime, self._ie, self._if

    def load_interrupts(self, ime: int, ie: int, interrupts: int) -> None:
        self._ime = ime & 1
        self._ie = ie & 0x3FFF
        self._if = interrupts & 0x3FFF
        self._irq_seen = 0

    # ------------------------------------------------------------------
    # 個別暫存器
    # ------------------------------------------------------------------
    @property
    def waitcnt(self) -> int:
        return self._get16(0x204)

    @property
    def dispcnt(self) -> int:
        return self._get16(0x000)

    @property
    def keycnt(self) -> int:
        return self._get16(0x132)

    def _dispstat(self) -> int:
        # 低 3 位是唯讀旗標（Phase 2 第 3 步由 PPU 提供）；其餘為 R/W。
        value = self._get16(0x004) & ~0x0007
        if self.ppu is not None:
            value |= self.ppu.dispstat_flags() & 0x0007
        return value

    def _vcount(self) -> int:
        return self.ppu.vcount if self.ppu is not None else 0

    def _keyinput(self) -> int:
        if self.keypad is None:
            return 0x03FF
        return self.keypad.keyinput_mask & 0x03FF

    def poll_keypad(self) -> None:
        """KEYCNT 條件成立時拉起 keypad IRQ（GBATEK: GBA Keypad Input）。

        bit15=1 表示 AND（所有選定鍵都按）、0 表示 OR（任一鍵）；bit14=IRQ enable。
        """

        keycnt = self._get16(0x132)
        condition = keycnt & 0x03FF
        if not (keycnt & (1 << 14)) or condition == 0:
            self._keypad_irq_active = False
            return
        pressed = (~self._keyinput()) & 0x03FF
        and_mode = bool(keycnt & (1 << 15))
        matched = (pressed & condition) == condition if and_mode else bool(pressed & condition)
        if matched and not self._keypad_irq_active:
            self.request_irq(IRQ_KEYPAD)
            self._keypad_irq_active = True
        elif not matched:
            self._keypad_irq_active = False

    # ------------------------------------------------------------------
    # 內部
    # ------------------------------------------------------------------
    def _store_sound16(self, offset: int, value: int) -> None:
        """將 sound 暫存器已遮罩的值鏡射到 raw IO bytes（snapshot 用）。"""

        stored = value & _SOUND_WRITE_MASKS.get(offset, 0xFFFF)
        self._bytes[offset] = stored & 0xFF
        self._bytes[offset + 1] = (stored >> 8) & 0xFF

    def _get16(self, offset: int) -> int:
        return self._bytes[offset] | (self._bytes[offset + 1] << 8)

    def _write16(self, offset: int, value: int) -> None:
        value &= 0xFFFF
        self._bytes[offset] = value & 0xFF
        self._bytes[offset + 1] = (value >> 8) & 0xFF
        if offset == 0x200:
            self._ie = value & 0x3FFF
            self._refresh_irq_line()
        elif offset == 0x208:
            self._ime = value & 1
            self._refresh_irq_line()

    # ------------------------------------------------------------------
    # Snapshot（規格 5.7：I/O 原始 bytes 與 IE/IF/IME）
    # ------------------------------------------------------------------
    _STATE = struct.Struct("<IIIB")

    def export_state(self) -> bytes:
        return bytes(self._bytes) + self._STATE.pack(self._ie, self._if, self._ime, 1 if self.halt_requested else 0)

    def load_state(self, data: bytes) -> None:
        if len(data) != IO_SIZE + self._STATE.size:
            raise ValueError("I/O snapshot 長度不符")
        self._bytes[:] = data[:IO_SIZE]
        self._ie, self._if, self._ime, halt = self._STATE.unpack_from(data, IO_SIZE)
        self.halt_requested = bool(halt)
        self._refresh_irq_line()
        # PPU 的 BGxCNT／WININ／BLDCNT 等快取也要由 raw bytes 回填，否則
        # 載入 snapshot 後 renderer 會用到全 0（畫面空白／錯層）。
        if self.ppu is not None:
            self.ppu.restore_disp_regs(self._bytes)

    # ------------------------------------------------------------------
    # 生命週期
    # ------------------------------------------------------------------
    @property
    def raw(self) -> bytearray:
        """原始 bytes（週期模型讀 WAITCNT／prefetch 用；不得直接改）。"""

        return self._bytes

    def reset(self) -> None:
        self._bytes[:] = bytes(IO_SIZE)
        self._ie = 0
        self._if = 0
        self._irq_seen = 0
        self._ime = 0
        self._irq_line = False
        self.halt_requested = False
        self._keypad_irq_active = False


__all__ = [
    "IO_SIZE",
    "IRQ_VBLANK",
    "IRQ_HBLANK",
    "IRQ_VCOUNT",
    "IRQ_TIMER0",
    "IRQ_DMA0",
    "IRQ_KEYPAD",
    "IoRegisters",
]
