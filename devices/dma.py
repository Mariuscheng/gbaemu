"""DMA0–3（規格 §3.4；GBATEK: GBA DMA Transfers）。

暫存器佈局（0x040000B0 起，每通道 0x0C bytes）：

| 通道 | SAD（32） | DAD（32） | CNT_L（16） | CNT_H（16） |
|---|---|---|---|---|
| DMA0 | 0x0B0 | 0x0B4 | 0x0B8 | 0x0BA |
| DMA1 | 0x0BC | 0x0C0 | 0x0C4 | 0x0C6 |
| DMA2 | 0x0C8 | 0x0CC | 0x0D0 | 0x0D2 |
| DMA3 | 0x0D4 | 0x0D8 | 0x0DC | 0x0DE |

CNT_H：dest 5-6、src 7-8、repeat 9、size 10（0=16bit、1=32bit）、DRQ 11、
start timing 12-13、IRQ 14、enable 15。

成本（GBATEK Transfer Rate/Timing）：`2N + 2(n-1)S + xI`，x 通常 2、
src 與 dst 都在 GamePak 時 4。enable 0→1 後有 2-cycle 延遲才可再存取 DMA 暫存器。

# GBATEK: GBA DMA Transfers - Transfer Rate/Timing；DMA Repeat；Game Pak DMA
"""

from __future__ import annotations

import struct
from dataclasses import dataclass

from ..bus.access import access_cycles
from ..bus.io import IRQ_DMA0

DMA_BASE = 0x040000B0
CHANNEL_STRIDE = 0x0C

# CNT_H bits
DEST_CONTROL_SHIFT = 5
SRC_CONTROL_SHIFT = 7
REPEAT_BIT = 1 << 9
SIZE_BIT = 1 << 10
DRQ_BIT = 1 << 11
START_TIMING_SHIFT = 12
IRQ_BIT = 1 << 14
ENABLE_BIT = 1 << 15

START_IMMEDIATE = 0
START_VBLANK = 1
START_HBLANK = 2
START_SPECIAL = 3

# 位址遮罩（mGBA `DMA_SRC_MASK` / `DMA_DST_MASK`）：DMA0–2 讀唔到 bit27 以上，
# DMA3 就 28-bit。Rust core 用同一組常數，I/O 讀回值必須一致；傳輸本身喺啟動時
# 另做寬度對齊，所以呢度保留 bit0。
SAD_MASK = (0x07FF_FFFF, 0x0FFF_FFFF, 0x0FFF_FFFF, 0x0FFF_FFFF)
DAD_MASK = (0x07FF_FFFF, 0x07FF_FFFF, 0x07FF_FFFF, 0x0FFF_FFFF)


@dataclass(slots=True)
class DmaChannelState:
    channel: int  # 0-3
    source: int  # 32-bit 來源位址（內部目前值）
    dest: int  # 32-bit 目的位址（內部遞增值）
    word_count: int  # 剩餘傳輸數
    control: int  # DMA_CNT_H 原始值
    active: bool
    irq_enable: bool


class DmaController:
    """DMA0–3 的暫存器、觸發與傳輸。"""

    def __init__(self, *, irq=None) -> None:
        self._latched: list[list[int]] = [[0, 0, 0, 0] for _ in range(4)]  # SAD/DAD/CNT_L/CNT_H
        self.channels = [
            DmaChannelState(
                channel=index,
                source=0,
                dest=0,
                word_count=0,
                control=0,
                active=False,
                irq_enable=False,
            )
            for index in range(4)
        ]
        self.pending: list[int] = []
        # 即時 DMA 起動延遲（timed 模式；hardware 喺 CNT_H write 後幾個
        # cycle 才搶 bus）。
        self.startup = 0
        # mGBA 的 DMA latch：非法來源（DMA0-2 讀 ROM、任何 DMA 讀 SRAM）會沿用
        # 該通道最後一次成功搬運的值（suite「ROM load」DMA 測試）。
        self._latch = [0, 0, 0, 0]
        self._irq = irq
        self._bus = None
        self.functional = True

    # ------------------------------------------------------------------
    # 接線
    # ------------------------------------------------------------------
    def attach_bus(self, bus) -> None:
        self._bus = bus

    def bind_irq(self, callback) -> None:
        self._irq = callback

    @property
    def active_count(self) -> int:
        return sum(1 for channel in self.channels if channel.active)

    # ------------------------------------------------------------------
    # 暫存器存取（IoRegisters 委派）
    # ------------------------------------------------------------------
    def read16(self, offset: int) -> int:
        index, field = self._decode(offset)
        if index is None:
            return 0
        if field == "sad":
            value = self._latched[index][0] & SAD_MASK[index]
            return (value >> ((offset & 2) * 8)) & 0xFFFF
        if field == "dad":
            value = self._latched[index][1] & DAD_MASK[index]
            return (value >> ((offset & 2) * 8)) & 0xFFFF
        if field == "cnt_l":
            # GBATEK：DMAxCNT_L 只寫，硬體讀回 0（mgba suite「I/O read tests」）。
            return 0
        return self._latched[index][3] & 0xFFFF

    def read32(self, offset: int) -> int:
        index, field = self._decode(offset)
        if index is None:
            return 0
        if field in ("sad", "dad"):
            slot = 0 if field == "sad" else 1
            mask = SAD_MASK[index] if field == "sad" else DAD_MASK[index]
            return self._latched[index][slot] & mask
        return self.read16(offset) | (self.read16(offset + 2) << 16)

    def write16(self, offset: int, value: int) -> None:
        index, field = self._decode(offset)
        if index is None:
            return
        value &= 0xFFFF
        if field == "sad":
            shift = (offset & 2) * 8
            mask = 0xFFFF << shift
            self._latched[index][0] = (self._latched[index][0] & ~mask & 0xFFFFFFFF) | (value << shift)
        elif field == "dad":
            shift = (offset & 2) * 8
            mask = 0xFFFF << shift
            self._latched[index][1] = (self._latched[index][1] & ~mask & 0xFFFFFFFF) | (value << shift)
        elif field == "cnt_l":
            self._latched[index][2] = value
        elif field == "cnt_h":
            self._write_control(index, value)

    def write32(self, offset: int, value: int) -> None:
        index, field = self._decode(offset)
        if index is None:
            return
        value &= 0xFFFFFFFF
        if field == "sad":
            self._latched[index][0] = value
        elif field == "dad":
            self._latched[index][1] = value
        else:
            self.write16(offset, value & 0xFFFF)
            self.write16(offset + 2, (value >> 16) & 0xFFFF)

    # ------------------------------------------------------------------
    # 控制與觸發
    # ------------------------------------------------------------------
    def _write_control(self, index: int, value: int) -> None:
        previous = self._latched[index][3]
        self._latched[index][3] = value
        channel = self.channels[index]
        channel.control = value
        channel.irq_enable = bool(value & IRQ_BIT)

        if not (value & ENABLE_BIT):
            channel.active = False
            if index in self.pending:
                self.pending.remove(index)
            return

        if not (previous & ENABLE_BIT):  # 0 → 1：重載內部指標
            self._reload(index)
            timing = (value >> START_TIMING_SHIFT) & 0x3
            if timing == START_IMMEDIATE:
                self._queue(index)
                if not self.functional:
                    self.startup = 3
            # VBlank/HBlank 由 PPU 事件觸發；Special 於 Phase 4/5（音效 FIFO）。

    def _reload(self, index: int) -> None:
        channel = self.channels[index]
        sad, dad, cnt_l, _control = self._latched[index]
        channel.source = sad
        channel.dest = dad
        channel.word_count = self._count_from_register(index, cnt_l)
        channel.active = True

    def _count_from_register(self, index: int, value: int) -> int:
        maximum = 0x10000 if index == 3 else 0x4000
        return maximum if value == 0 else value

    def _queue(self, index: int) -> None:
        if index not in self.pending:
            self.pending.append(index)

    def request_fifo(self, channel: int) -> None:
        """FIFO starvation → 對應 DMA1/2 的 Special timing 請求（GBATEK）。"""

        if channel not in (1, 2):
            return
        control = self._latched[channel][3]
        if not (control & ENABLE_BIT):
            return
        if (control >> START_TIMING_SHIFT) & 0x3 != START_SPECIAL:
            return
        self._queue(channel)

    def on_ppu_event(self, kind: str) -> None:
        """PPU 事件 → 對應 start timing 的 DMA。kind: 'vblank' / 'hblank'。"""

        timing = START_VBLANK if kind == "vblank" else START_HBLANK
        for index in range(4):
            control = self._latched[index][3]
            if not (control & ENABLE_BIT):
                continue
            if (control >> START_TIMING_SHIFT) & 0x3 != timing:
                continue
            self._queue(index)

    # ------------------------------------------------------------------
    # 傳輸
    # ------------------------------------------------------------------
    def service(self) -> int:
        """執行所有待處理的 DMA，回傳消耗的 cycle 數。"""

        total = 0
        while self.pending:
            index = self.pending.pop(0)
            total += self._run(index)
        return total

    def _run(self, index: int) -> int:
        channel = self.channels[index]
        control = channel.control
        if not channel.active:
            return 0
        timing = (control >> START_TIMING_SHIFT) & 0x3
        if timing == START_SPECIAL and index in (1, 2):
            return self._run_fifo(index)

        width = 4 if (control & SIZE_BIT) else 2
        count = channel.word_count
        if count == 0:
            channel.active = False
            return 0

        # GBATEK: 只有 DMA3（與 CPU）能存取 Game Pak ROM，任何 DMA 都不能存取
        # Game Pak SRAM。違規的「讀」回 open bus（硬體上沒有裝置驅動匯流排），
        # 「寫」則被忽略；transfer 本身仍會完成（suite「ROM load」DMA 測試）。
        src_control = (control >> SRC_CONTROL_SHIFT) & 0x3
        if src_control == 3:  # GBATEK: source control 3 = prohibited
            raise ValueError("DMA source address control 3 是 prohibited")
        dst_control = (control >> DEST_CONTROL_SHIFT) & 0x3
        src_step = self._step(src_control) * width
        dst_step = self._step(dst_control) * width
        bus = self._bus
        if bus is None:
            raise RuntimeError("DMA 尚未接上 bus")

        save = getattr(getattr(self._bus, "cartridge", None), "save", None)
        if save is not None and save.kind == "EEPROM":
            if 0x0D000000 <= channel.dest < 0x0E000000:
                save.begin_stream(count)

        src_start = channel.source
        dst_start = channel.dest
        for _ in range(count):
            source = channel.source
            if index == 0 and (source >> 24) in (0x0E, 0x0F):
                # mGBA：DMA0 讀 Game Pak SRAM 時 byte 讀取直接回 0
                # （suite「SRAM load」DMA0 期待 0；DMA1–3 才讀到 SRAM 內容）。
                self._latch[index] = 0
                value = 0
            elif self._blocked(index, source):
                # DMA0 讀 Game Pak ROM 被阻擋：沿用此通道最後一次搬運的值。
                value = self._latch[index]
            else:
                value = self._read(bus, source, width)
                if width == 4:
                    self._latch[index] = value & 0xFFFFFFFF
                else:
                    half = value & 0xFFFF
                    self._latch[index] = half | (half << 16)
            dest = channel.dest
            if not self._blocked_dest(index, dest):
                if width == 4:
                    self._write(bus, dest, width, value)
                else:
                    # mGBA：16-bit DMA 以 latch 依 dest bit1 選 lane。
                    shift = 8 * (dest & 2)
                    self._write(bus, dest, width, (self._latch[index] >> shift) & 0xFFFF)
            channel.source = (channel.source + src_step) & 0xFFFFFFFF
            channel.dest = (channel.dest + dst_step) & 0xFFFFFFFF

        # 成本：2N + 2(n-1)S + xI（read 與 write 各一次 N；其餘 S）
        cycles = self._cost(src_start, width, False) + self._cost(dst_start, width, False)
        if count > 1:
            cycles += (count - 1) * (
                self._cost(src_start, width, True) + self._cost(dst_start, width, True)
            )
        cycles += self._internal_cost(index)

        channel.word_count = 0
        if control & REPEAT_BIT:
            channel.word_count = self._count_from_register(index, self._latched[index][2])
            channel.source = self._latched[index][0]
            if dst_control == 0x3:  # increment/reload
                channel.dest = self._latched[index][1]
        else:
            channel.active = False
            self._latched[index][3] = control & ~ENABLE_BIT

        if channel.irq_enable and self._irq is not None:
            self._irq(IRQ_DMA0 << index)
        return cycles

    def _run_fifo(self, index: int) -> int:
        """Sound FIFO：固定搬 4 words（16 bytes）到 0x040000A0/A4，dest 不遞增。

        GBATEK：每次 refill 固定 4 words；DMA repeat bit（bit9）clear 時，
        呢次 transfer 之後要清 enable，FIFO 播完 16 bytes 就停（one-shot
        SFX）；set 時保持 enable，等下一個 FIFO request 再 refill。
        """

        channel = self.channels[index]
        dest = self._latched[index][1] & 0xFFFFFFFF
        source = channel.source
        bus = self._bus
        if bus is None:
            raise RuntimeError("DMA 尚未接上 bus")
        sound = getattr(bus, "sound", None)
        if sound is not None:
            sound.begin_refill()
        for _ in range(4):
            value = bus.read_u32(source)
            bus.write_u32(dest, value)
            source = (source + 4) & 0xFFFFFFFF
        if sound is not None:
            sound.end_refill()
        channel.source = source
        if not (channel.control & REPEAT_BIT):
            channel.active = False
            channel.word_count = 0
            self._latched[index][3] = channel.control & ~ENABLE_BIT
            if channel.irq_enable and self._irq is not None:
                self._irq(IRQ_DMA0 << index)
        cost = 4 * self._cost(source, 4, False) + 4 * self._cost(dest, 4, False)
        return cost + 2

    def _internal_cost(self, index: int) -> int:
        sad = self._latched[index][0]
        dad = self._latched[index][1]
        src_rom = 0x08 <= (sad >> 24) <= 0x0D
        dst_rom = 0x08 <= (dad >> 24) <= 0x0D
        both_gamepak = src_rom and dst_rom
        cost = 0 if both_gamepak else 2
        if self.functional or self._bus is None:
            return cost
        # Game Pak DMA first-access rounding（同 Rust `run_dma` 的 ±1 校正；
        # suite Timing DMA ROM 測試校準）。
        waitcnt = self._bus.waitcnt
        first_idx = (waitcnt >> 2) & 0x3
        seq_bit = bool((waitcnt >> 4) & 1)
        prefetch = bool(waitcnt & 0x4000)
        if both_gamepak:
            if first_idx == 1:
                if not (seq_bit and not prefetch):
                    cost += 1
            elif seq_bit and not prefetch:
                cost -= 1
        elif dst_rom and not src_rom and prefetch and not seq_bit:
            cost += 1
        elif src_rom and not dst_rom and prefetch and seq_bit:
            cost += 1
        return cost

    def _cost(self, address: int, width: int, sequential: bool) -> int:
        if self.functional:
            return 1
        if self._bus is None:
            return 1
        return access_cycles(address, width, sequential, self._bus.waitcnt) + self._bus.video_wait(
            address, width
        )

    def _step(self, control: int) -> int:
        if control == 0:
            return 1
        if control == 1:
            return -1
        if control == 2:
            return 0
        return 1  # 0x3：dest increment/reload；src 的 0x3 為 prohibited

    @staticmethod
    def _blocked(index: int, address: int) -> bool:
        """DMA 不可存取的來源（GBATEK + suite 實測）。

        只有 DMA0 不能讀 Game Pak ROM；DMA1–3 可以（suite「ROM load」的
        DMA1/2/3 期待 ROM 內容）。DMA0–2 不能寫入 Game Pak SRAM，DMA3 可以。
        """

        page = (address & 0xFFFFFFFF) >> 24
        return index == 0 and 0x08 <= page <= 0x0D

    @staticmethod
    def _blocked_dest(index: int, address: int) -> bool:
        page = (address & 0xFFFFFFFF) >> 24
        return index != 3 and 0x0E <= page <= 0x0F

    @staticmethod
    def _read(bus, address: int, width: int) -> int:
        if width == 4:
            return bus.read_u32(address)
        return bus.read_u16(address)

    @staticmethod
    def _write(bus, address: int, width: int, value: int) -> None:
        if width == 4:
            bus.write_u32(address, value)
        else:
            bus.write_u16(address, value)

    # ------------------------------------------------------------------
    # Snapshot（規格 5.7 DMA 區段）
    # ------------------------------------------------------------------
    _CHANNEL = struct.Struct("<8I2B")
    _TAIL = struct.Struct("<B4B")

    def snapshot_state(self) -> bytes:
        parts = []
        for index, channel in enumerate(self.channels):
            sad, dad, cnt_l, cnt_h = self._latched[index]
            parts.append(
                self._CHANNEL.pack(
                    sad & 0xFFFFFFFF,
                    dad & 0xFFFFFFFF,
                    cnt_l & 0x1FFFF,
                    cnt_h & 0xFFFF,
                    channel.source & 0xFFFFFFFF,
                    channel.dest & 0xFFFFFFFF,
                    channel.word_count & 0x1FFFF,
                    channel.control & 0xFFFF,
                    1 if channel.active else 0,
                    1 if channel.irq_enable else 0,
                )
            )
        pending = self.pending[:4] + [0] * (4 - len(self.pending[:4]))
        parts.append(self._TAIL.pack(len(self.pending[:4]), *pending))
        return b"".join(parts)

    def restore_state(self, data: bytes) -> None:
        offset = 0
        for index in range(4):
            values = self._CHANNEL.unpack_from(data, offset)
            offset += self._CHANNEL.size
            self._latched[index] = list(values[:4])
            channel = self.channels[index]
            (
                channel.source,
                channel.dest,
                channel.word_count,
                channel.control,
                active,
                irq_enable,
            ) = values[4:]
            channel.active = bool(active)
            channel.irq_enable = bool(irq_enable)
        count, *pending = self._TAIL.unpack_from(data, offset)
        self.pending = list(pending[:count])

    # ------------------------------------------------------------------
    # 解碼
    # ------------------------------------------------------------------
    @staticmethod
    def _decode(offset: int) -> tuple[int | None, str | None]:
        # IoRegisters 傳入相對 0x04000000 的 offset；也接受絕對位址。
        relative = offset - DMA_BASE if offset >= DMA_BASE else offset - 0xB0
        if relative < 0 or relative >= 4 * CHANNEL_STRIDE:
            return None, None
        index = relative // CHANNEL_STRIDE
        field_offset = relative % CHANNEL_STRIDE
        if field_offset < 4:
            return index, "sad"
        if field_offset < 8:
            return index, "dad"
        if field_offset < 10:
            return index, "cnt_l"
        return index, "cnt_h"

    # ------------------------------------------------------------------
    # 生命週期
    # ------------------------------------------------------------------
    def reset(self) -> None:
        self._latched = [[0, 0, 0, 0] for _ in range(4)]
        self.pending.clear()
        for channel in self.channels:
            channel.source = 0
            channel.dest = 0
            channel.word_count = 0
            channel.control = 0
            channel.active = False
            channel.irq_enable = False


__all__ = [
    "DMA_BASE",
    "CHANNEL_STRIDE",
    "ENABLE_BIT",
    "REPEAT_BIT",
    "SIZE_BIT",
    "IRQ_BIT",
    "START_IMMEDIATE",
    "START_VBLANK",
    "START_HBLANK",
    "START_SPECIAL",
    "DmaChannelState",
    "DmaController",
]
