//! GBA PPU timing 最小模型（G1）。
//!
//! 只實作 VCOUNT／DISPSTAT／HBlank／VBlank／IRQ flags；renderer、DMA、
//! window/blend 尚未搬遷。Python `video/ppu.py` 仍是 reference。

#![forbid(unsafe_code)]

use crate::{put_u32, put_u64, SnapshotReader};

pub const LINE_CYCLES: u64 = 1_232;
pub const TOTAL_LINES: u16 = 228;
pub const VISIBLE_LINES: u16 = 160;
pub const FRAME_CYCLES: u64 = LINE_CYCLES * TOTAL_LINES as u64;
pub const HBLANK_START: u64 = 1_006;

#[derive(Debug, Clone, PartialEq, Eq, Default)]
pub struct Ppu {
    pub total_cycles: u64,
    pub scanline: u16,
    pub frame_index: u64,
    pub in_hblank: bool,
    pub in_vblank: bool,
    pub dispcnt: u16,
    pub dispstat_enables: u16,
    pub lyc: u16,
    pub irq_vblank: bool,
    pub irq_hblank: bool,
    pub irq_vcount: bool,
    /// 自上次取用以來的事件序列（1 = VBlank、2 = HBlank；依時間順序）。
    pub events: Vec<u8>,
    /// 自上次取用以來進入 HBlank 的可見 scanline（renderer 逐線繪製用）。
    pub completed_lines: Vec<u16>,
}

impl Ppu {
    pub fn new() -> Self {
        Self::default()
    }

    pub fn vcount(&self) -> u16 {
        self.scanline
    }

    pub fn dispstat(&self) -> u16 {
        let mut value = self.dispstat_enables & 0x38;
        if (VISIBLE_LINES..TOTAL_LINES - 1).contains(&self.scanline) {
            value |= 0x0001;
        }
        if self.in_hblank {
            value |= 0x0002;
        }
        if self.scanline == self.lyc {
            value |= 0x0004;
        }
        value | ((self.lyc & 0xFF) << 8)
    }

    pub fn write_dispcnt(&mut self, value: u16) {
        self.dispcnt = value;
    }

    pub fn write_dispstat(&mut self, value: u16) {
        self.dispstat_enables = value & 0x38;
        self.lyc = (value >> 8) & 0xFF;
        if self.scanline == self.lyc && self.dispstat_enables & 0x20 != 0 {
            self.irq_vcount = true;
        }
    }

    pub fn snapshot_section(&self) -> Vec<u8> {
        let mut out = Vec::new();
        put_u64(&mut out, self.total_cycles);
        put_u32(&mut out, self.frame_index as u32);
        put_u32(&mut out, self.scanline as u32);
        put_u32(&mut out, self.scanline as u32);
        put_u32(&mut out, self.dispcnt as u32);
        put_u32(&mut out, self.dispstat_enables as u32);
        put_u32(&mut out, self.lyc as u32);
        out.push(u8::from(self.in_vblank));
        out.push(u8::from(self.in_hblank));
        out
    }

    pub fn restore_section(&mut self, data: &[u8]) -> Result<(), String> {
        let mut reader = SnapshotReader::new(data);
        self.total_cycles = reader.u64().ok_or("PPU snapshot 被截斷")?;
        self.frame_index = reader.u32().ok_or("PPU snapshot 被截斷")? as u64;
        self.scanline = reader.u32().ok_or("PPU snapshot 被截斷")? as u16;
        let _vcount = reader.u32().ok_or("PPU snapshot 被截斷")?;
        self.dispcnt = reader.u32().ok_or("PPU snapshot 被截斷")? as u16;
        self.dispstat_enables = reader.u32().ok_or("PPU snapshot 被截斷")? as u16;
        self.lyc = reader.u32().ok_or("PPU snapshot 被截斷")? as u16;
        self.in_vblank = reader.u8().ok_or("PPU snapshot 被截斷")? != 0;
        self.in_hblank = reader.u8().ok_or("PPU snapshot 被截斷")? != 0;
        self.irq_vblank = false;
        self.irq_hblank = false;
        self.irq_vcount = false;
        self.events.clear();
        self.completed_lines.clear();
        if !reader.finish() {
            return Err("PPU snapshot 長度不符".to_string());
        }
        Ok(())
    }

    pub fn advance(&mut self, cycles: u32) {
        for _ in 0..cycles {
            self.total_cycles = self.total_cycles.wrapping_add(1);
            let position = self.total_cycles % LINE_CYCLES;
            if position == HBLANK_START {
                self.in_hblank = true;
                let line = self.scanline;
                if line < VISIBLE_LINES {
                    self.events.push(2);
                    self.completed_lines.push(line);
                }
                if line < VISIBLE_LINES && self.dispstat_enables & 0x10 != 0 {
                    self.irq_hblank = true;
                }
            }
            if position == 0 {
                let frame_pos = self.total_cycles % FRAME_CYCLES;
                if frame_pos == 0 {
                    self.frame_index = self.frame_index.wrapping_add(1);
                    self.scanline = 0;
                    self.in_vblank = false;
                    self.in_hblank = false;
                    if self.lyc == 0 && self.dispstat_enables & 0x20 != 0 {
                        self.irq_vcount = true;
                    }
                } else {
                    let line = (frame_pos / LINE_CYCLES) as u16;
                    self.scanline = line;
                    self.in_hblank = false;
                    self.in_vblank = line >= VISIBLE_LINES;
                    if line == self.lyc && self.dispstat_enables & 0x20 != 0 {
                        self.irq_vcount = true;
                    }
                    if line == VISIBLE_LINES && self.dispstat_enables & 0x08 != 0 {
                        self.irq_vblank = true;
                    }
                    if line == VISIBLE_LINES {
                        self.events.push(1);
                    }
                }
            }
        }
    }

    /// 取走依時間排序的 VBlank／HBlank 事件。
    pub fn take_events(&mut self) -> Vec<u8> {
        std::mem::take(&mut self.events)
    }

    /// 取走已完成（進入 HBlank）的可見 scanline，供 renderer 逐線繪製。
    pub fn take_completed_lines(&mut self) -> Vec<u16> {
        std::mem::take(&mut self.completed_lines)
    }

    /// 取走 IRQ flags（IF 的簡化模型；之後接 IE/IME）。
    pub fn take_irq(&mut self) -> u16 {
        let mut mask = 0u16;
        if self.irq_vblank {
            mask |= 0x0001;
            self.irq_vblank = false;
        }
        if self.irq_hblank {
            mask |= 0x0002;
            self.irq_hblank = false;
        }
        if self.irq_vcount {
            mask |= 0x0004;
            self.irq_vcount = false;
        }
        mask
    }
}
