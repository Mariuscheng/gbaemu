"""PPU：scanline 狀態機、VCOUNT／DISPSTAT、事件與 Mode 3 繪製。

時序依規格 §3.6.6（GBATEK: LCD Dimensions and Timings）：

* 每條 scanline 1232 cycles；0..159 可見、160..227 VBlank。
* HBlank flag 在 `line*1232+1006` 設起；繪製只佔前 960 cycles。
* 進入 line 160 → ``VBLANK_START``；line 227 結束（280,896 cycles）→
  ``VBLANK_END``＋``FRAME_BOUNDARY``，frame_index +1、VCOUNT 回 0。
* DISPSTAT：bit0 VBlank flag（160..226）、bit1 HBlank flag、bit2 VCount match；
  bit3-5 IRQ enable；bit8-15 LYC。

# GBATEK: LCD I/O Display Control - DISPSTAT/VCOUNT/DISPCNT
# GBATEK: GBA LCD Video Controller - VRAM
"""

from __future__ import annotations

import struct
from dataclasses import dataclass

from ..api_types import EmulatorEvent, EventKind
from ..bus.io import IRQ_HBLANK, IRQ_VBLANK, IRQ_VCOUNT
from .renderer import render_frame
from ..timing import (
    PPU_FRAME_CYCLES,
    PPU_HBLANK_START,
    PPU_LINE_CYCLES,
    PPU_TOTAL_LINES,
    PPU_TOTAL_LINES,
    PPU_VBLANK_START,
    PPU_VISIBLE_LINES,
)


@dataclass(slots=True)
class PpuState:
    dispstat: int
    vcount: int
    dispcnt: int
    scanline: int  # 0-227
    in_vblank: bool
    in_hblank: bool
    frame: int  # 已完成 frame 數


class Ppu:
    """scanline/event 驅動的 PPU（Phase 2：Mode 3）。"""

    def __init__(self) -> None:
        self.state = PpuState(
            dispstat=0,
            vcount=0,
            dispcnt=0,
            scanline=0,
            in_vblank=False,
            in_hblank=False,
            frame=0,
        )
        self.total_cycles = 0  # 開機以來的絕對 cycle
        self.dispcnt = 0  # 包含 mode bits 與 force blank（bit7）
        self._enables = 0  # DISPSTAT bits 3-5
        self._lyc = 0
        self._events = None
        self._irq = None
        self._dma = None
        self._vram = None
        self._framebuffer = None
        self._palette = None
        self._oam = None
        self._regs = bytearray(0x58)  # 0x008-0x05F
        self.dirty = True  # VRAM/regs 有變才重繪
        self.render_enabled = True
        self._rendered_lines = 0

    # ------------------------------------------------------------------
    # 接線
    # ------------------------------------------------------------------
    def bind_events(self, events) -> None:
        self._events = events

    def bind_irq(self, callback) -> None:
        self._irq = callback

    def bind_dma(self, callback) -> None:
        self._dma = callback

    def bind_output(self, vram, framebuffer, palette=None, oam=None) -> None:
        self._vram = vram
        self._framebuffer = framebuffer
        self._palette = palette
        self._oam = oam

    # ------------------------------------------------------------------
    # BG/OBJ/window/blend 暫存器（0x008-0x05F；IoRegisters 委派）
    # ------------------------------------------------------------------
    def read_reg16(self, offset: int) -> int:
        relative = offset - 0x008
        if not 0 <= relative < len(self._regs) - 1:
            return 0
        return self._regs[relative] | (self._regs[relative + 1] << 8)

    def read_reg32(self, offset: int) -> int:
        return self.read_reg16(offset) | (self.read_reg16(offset + 2) << 16)

    def write_reg16(self, offset: int, value: int) -> None:
        relative = offset - 0x008
        if not 0 <= relative < len(self._regs) - 1:
            return
        self._regs[relative] = value & 0xFF
        self._regs[relative + 1] = (value >> 8) & 0xFF
        self.dirty = True

    # ------------------------------------------------------------------
    # 暫存器視角（IoRegisters 委派）
    # ------------------------------------------------------------------
    @property
    def vcount(self) -> int:
        return self.state.scanline

    @property
    def frame_index(self) -> int:
        return self.state.frame

    def dispstat(self) -> int:
        value = self._enables & 0x38
        line = self.state.scanline
        if PPU_VISIBLE_LINES <= line < PPU_TOTAL_LINES - 1:  # 160..226（227 為 0）
            value |= 0x0001
        if self.state.in_hblank:
            value |= 0x0002
        if line == self._lyc:
            value |= 0x0004
        value |= (self._lyc & 0xFF) << 8
        return value

    def dispstat_flags(self) -> int:
        return self.dispstat() & 0x0007

    def write_dispcnt(self, value: int) -> None:
        self.dirty = True
        self.dispcnt = value & 0xFFFF
        if self._vram is not None:
            # GBATEK: Mode 3/4/5 是 bitmap（BG 80 KiB、OBJ 16 KiB），其餘 tile。
            self._vram.bitmap_mode = (self.dispcnt & 0x7) in (3, 4, 5)

    def write_dispstat(self, value: int) -> None:
        self._enables = value & 0x38
        self._lyc = (value >> 8) & 0xFF

    def restore_disp_regs(self, io_bytes: bytes) -> None:
        """snapshot 還原後把 I/O raw bytes 同步回 PPU 的 BG/OBJ/window 快取。

        `_regs` 就是 0x008-0x05F 的原始 bytes；載入 snapshot 時 `IoRegisters`
        只還原 byte array，若不回填這裡，renderer 會用到全 0 的 BGxCNT／
        WININ／BLDCNT，畫面會空白或錯層。
        """

        self._regs[:] = bytes(io_bytes[0x008:0x060])
        self.dirty = True

    def reset(self) -> None:
        self.state = PpuState(
            dispstat=0,
            vcount=0,
            dispcnt=0,
            scanline=0,
            in_vblank=False,
            in_hblank=False,
            frame=0,
        )
        self.total_cycles = 0
        self.dispcnt = 0
        self._enables = 0
        self._lyc = 0
        self.render_enabled = True
        self._rendered_lines = 0

    # ------------------------------------------------------------------
    # 時間推進
    # ------------------------------------------------------------------
    def advance(self, cycles: int) -> None:
        """推進 ``cycles`` 個 cycle，於邊界發出事件／IRQ。"""

        if cycles < 0:
            raise ValueError("cycles 不可為負")
        remaining = cycles
        while remaining > 0:
            position = self.total_cycles % PPU_LINE_CYCLES
            line = (self.total_cycles % PPU_FRAME_CYCLES) // PPU_LINE_CYCLES
            limit = PPU_HBLANK_START if position < PPU_HBLANK_START else PPU_LINE_CYCLES
            step = min(remaining, limit - position)
            if step <= 0:  # pragma: no cover - 防禦性
                step = 1
            self.total_cycles += step
            remaining -= step

            new_position = self.total_cycles % PPU_LINE_CYCLES
            if position < PPU_HBLANK_START <= new_position:
                # 逐掃描線 render：喺 HBlank 開始、IRQ／DMA 改 register 之前畫，
                # 咁本行用嘅係本行開始時的 register 狀態（raster effects）。
                if line < PPU_VISIBLE_LINES:
                    self._render_scanline(line)
                self.state.in_hblank = True
                self._emit(EventKind.HBLANK)
                if line < PPU_VISIBLE_LINES and (self._enables & 0x10):
                    self._request_irq(IRQ_HBLANK)
                if self._dma is not None:
                    self._dma("hblank")

            if new_position == 0:
                if self.total_cycles % PPU_FRAME_CYCLES == 0:
                    self._end_frame()
                else:
                    self._begin_line((self.total_cycles % PPU_FRAME_CYCLES) // PPU_LINE_CYCLES)

    def _begin_line(self, line: int) -> None:
        self.state.scanline = line
        self.state.vcount = line
        self.state.in_hblank = False
        self.state.in_vblank = line >= PPU_VISIBLE_LINES

        if line == self._lyc and (self._enables & 0x20):
            self._request_irq(IRQ_VCOUNT)

        if line == PPU_VISIBLE_LINES:
            self._emit(EventKind.VBLANK_START)
            if self._enables & 0x08:
                self._request_irq(IRQ_VBLANK)
            if self._dma is not None:
                self._dma("vblank")

    def _render_scanline(self, line: int) -> None:
        """用目前 register 狀態畫單一 visible line（HBlank 前呼叫）。"""

        if not self.render_enabled:
            return
        if self._vram is None or self._framebuffer is None:
            return
        if getattr(self._framebuffer, "_data", None) is None:
            return  # 冇可寫緩衝：留返 frame 尾整幅畫（舊行為）
        render_frame(self, self._vram, self._framebuffer, self._palette, self._oam, line, line + 1)
        self._rendered_lines += 1

    def _end_frame(self) -> None:
        # 逐行 render 已經畫完；只有喺「冇逐行畫過」（例如 render 中途關閉、
        # 或 framebuffer 冇 _data）時才退回整幅 render。
        if self._rendered_lines == 0 and self._vram is not None and self._framebuffer is not None:
            self.render(self._vram, self._framebuffer)
        self._rendered_lines = 0
        self.state.frame += 1
        self.state.scanline = 0
        self.state.vcount = 0
        self.state.in_vblank = False
        self.state.in_hblank = False
        self._emit(EventKind.VBLANK_END)
        self._emit(EventKind.FRAME_BOUNDARY)
        if self._lyc == 0 and (self._enables & 0x20):
            self._request_irq(IRQ_VCOUNT)

    # ------------------------------------------------------------------
    # Mode 3 繪製（240x160，RGB555 → RGB888）
    # ------------------------------------------------------------------
    def render(self, vram, framebuffer) -> None:
        if not self.render_enabled:
            return
        if not self.dirty:
            return  # 畫面內容沒變：沿用上一個 framebuffer
        render_frame(self, vram, framebuffer, self._palette, self._oam)
        self.dirty = False

    # ------------------------------------------------------------------
    # 內部
    # ------------------------------------------------------------------
    # ------------------------------------------------------------------
    # Snapshot（規格 5.7 PPU 區段）
    # ------------------------------------------------------------------
    _SNAPSHOT = struct.Struct("<QIIIIIIBB")

    def snapshot_state(self) -> bytes:
        state = self.state
        return self._SNAPSHOT.pack(
            self.total_cycles,
            state.frame,
            state.scanline,
            state.vcount,
            self.dispcnt,
            self._enables,
            self._lyc,
            1 if state.in_vblank else 0,
            1 if state.in_hblank else 0,
        )

    def restore_state(self, data: bytes) -> None:
        (
            total_cycles,
            frame,
            scanline,
            vcount,
            dispcnt,
            enables,
            lyc,
            in_vblank,
            in_hblank,
        ) = self._SNAPSHOT.unpack(data)
        self.total_cycles = total_cycles
        self.dispcnt = dispcnt
        self._enables = enables
        self._lyc = lyc
        self.state.frame = frame
        self.state.scanline = scanline
        self.state.vcount = vcount
        self.state.in_vblank = bool(in_vblank)
        self.state.in_hblank = bool(in_hblank)
        self.dirty = True
        if self._vram is not None:
            self._vram.bitmap_mode = (self.dispcnt & 0x7) in (3, 4, 5)

    def next_irq_cycle(self) -> int:
        """回傳下一個可能拉起 IF 的 PPU 事件絕對 cycle（含 frame 邊界）。

        只有 DISPSTAT 開啟的 IRQ（VBlank bit3、HBlank bit4、VCount bit5）才需要
        停下來；沒有開啟時回傳下一個 frame 邊界，讓 halt 可以一次跳過整個 frame。
        """

        total = self.total_cycles
        frame_pos = total % PPU_FRAME_CYCLES
        line = frame_pos // PPU_LINE_CYCLES
        pos = frame_pos % PPU_LINE_CYCLES
        delta = PPU_FRAME_CYCLES - frame_pos  # 無 enabled IRQ：到下一個 frame 邊界

        if self._enables & 0x08:  # VBlank IRQ
            if frame_pos < PPU_VBLANK_START:
                delta = min(delta, PPU_VBLANK_START - frame_pos)
            else:
                delta = min(delta, PPU_FRAME_CYCLES - frame_pos + PPU_VBLANK_START)
        if self._enables & 0x10:  # HBlank IRQ（只有 visible lines）
            if line < PPU_VISIBLE_LINES and pos < PPU_HBLANK_START:
                delta = min(delta, PPU_HBLANK_START - pos)
            elif line + 1 < PPU_VISIBLE_LINES:
                delta = min(delta, PPU_LINE_CYCLES - pos + PPU_HBLANK_START)
            else:
                delta = min(delta, PPU_FRAME_CYCLES - frame_pos + PPU_HBLANK_START)
        if self._enables & 0x20:  # VCount IRQ
            delta_lines = (self._lyc - (line + 1)) % PPU_TOTAL_LINES + 1
            delta = min(delta, delta_lines * PPU_LINE_CYCLES - pos)
        return total + max(1, delta)

    def _emit(self, kind: EventKind) -> None:
        if self._events is None:
            return
        self._events.emit(
            EmulatorEvent(
                kind=kind,
                cycle=self.total_cycles,
                frame_index=self.state.frame,
                scanline=self.state.scanline,
                channel=None,
                address=None,
                value=None,
            )
        )

    def _request_irq(self, mask: int) -> None:
        if self._irq is not None:
            self._irq(mask)


__all__ = ["Ppu", "PpuState"]
