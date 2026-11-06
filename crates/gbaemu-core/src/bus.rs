//! GBA memory map 與基礎 bus。
//!
//! G1 的範圍：先把 CPU 會用到的記憶體區域、寬度與 mirror 行為固定下來。
//! PPU／DMA／timer 等 device 仍由 Python reference 提供 oracle；此模組尚未接
//! 上 interrupt／wait-state／open-bus 的完整硬體語意。
//!
//! 位址与 GBATEK 的 GBA memory map 一致：
//! - BIOS 0x0000_0000..0x0000_3FFF（read-only）
//! - EWRAM 0x0200_0000..0x0203_FFFF，256 KiB mirror
//! - IWRAM 0x0300_0000..0x0300_7FFF，32 KiB mirror
//! - IO 0x0400_0000..0x0400_03FF
//! - Palette 0x0500_0000..0x0500_03FF
//! - VRAM 0x0600_0000..0x0601_7FFF
//! - OAM 0x0700_0000..0x0700_03FF
//! - ROM 0x0800_0000..0x0DFF_FFFF（mirror）
//! - SRAM/Flash 0x0E00_0000..0x0E00_FFFF（8-bit）

#![forbid(unsafe_code)]

use crate::ppu::Ppu;
use crate::sound::Sound;
use crate::{put_u32, put_u64, SnapshotReader};

pub const EWRAM_SIZE: usize = 0x40000;
pub const IWRAM_SIZE: usize = 0x8000;
pub const IO_SIZE: usize = 0x400;
pub const PALETTE_SIZE: usize = 0x400;
pub const VRAM_SIZE: usize = 0x18000;
pub const OAM_SIZE: usize = 0x400;
pub const SRAM_SIZE: usize = 0x10000;

/// 卡匣備份記憶體類型（由 ROM 簽章偵測，順序同 Python
/// `memory/savedata.py::detect_save` 一致）。
#[derive(Clone, Copy, PartialEq, Eq, Debug)]
pub enum SaveKind {
    None,
    Sram,
    Flash64,
    Flash128,
    Eeprom512,
    Eeprom8k,
}

impl SaveKind {
    pub fn is_eeprom(self) -> bool {
        matches!(self, SaveKind::Eeprom512 | SaveKind::Eeprom8k)
    }
}

fn rom_contains(haystack: &[u8], needle: &[u8]) -> bool {
    find_bytes(haystack, needle).is_some()
}

fn find_bytes(haystack: &[u8], needle: &[u8]) -> Option<usize> {
    if needle.is_empty() || haystack.len() < needle.len() {
        return None;
    }
    haystack.windows(needle.len()).position(|window| window == needle)
}

/// 由 ROM 內容偵測存檔類型。序列 EEPROM 仲未實作（0x0D000000 協定），
/// 所以含 `EEPROM_V` 的 ROM 暫時當冇 save（讀 0xFF、寫入忽略）。
pub fn detect_save_kind(rom: &[u8]) -> SaveKind {
    if let Some(index) = find_bytes(rom, b"EEPROM_V") {
        let tail = rom.get(index + 8..index + 12).unwrap_or(&[]);
        let small = tail.starts_with(b"11") || tail.starts_with(b"120");
        return if small { SaveKind::Eeprom512 } else { SaveKind::Eeprom8k };
    }
    if rom_contains(rom, b"SRAM_V") || rom_contains(rom, b"SRAM_F_V") {
        return SaveKind::Sram;
    }
    if rom_contains(rom, b"FLASH1M_V") {
        return SaveKind::Flash128;
    }
    if rom_contains(rom, b"FLASH512_V") || rom_contains(rom, b"FLASH_V") {
        return SaveKind::Flash64;
    }
    SaveKind::None
}

const BIOS_END: u32 = 0x0000_3FFF;
const EWRAM_START: u32 = 0x0200_0000;
const EWRAM_END: u32 = 0x02FF_FFFF; // 256 KiB mirrored through 0x02FF_FFFF
const IWRAM_START: u32 = 0x0300_0000;
const IWRAM_END: u32 = 0x03FF_FFFF;
const IO_START: u32 = 0x0400_0000;
const IO_END: u32 = 0x0400_03FF;
const IO_REGION_END: u32 = 0x04FF_FFFF;
const PALETTE_START: u32 = 0x0500_0000;
const PALETTE_END: u32 = 0x0500_07FF; // 1 KiB palette mirrored twice
const VRAM_START: u32 = 0x0600_0000;
const VRAM_END: u32 = 0x0603_FFFF; // 128 KiB window mirrored twice
const VRAM_WINDOW_SIZE: usize = 0x20000;
const OAM_START: u32 = 0x0700_0000;
const OAM_END: u32 = 0x0700_07FF; // 1 KiB OAM mirrored twice
const ROM_START: u32 = 0x0800_0000;
const ROM_END: u32 = 0x0DFF_FFFF;
const ROM_WINDOW_SIZE: usize = 0x0200_0000; // 三個 32 MiB Game Pak 視窗互為鏡像
const SRAM_START: u32 = 0x0E00_0000;
const SRAM_END: u32 = 0x0FFF_FFFF; // 32 KiB SRAM mirrored through 0x0FFFFFFF

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum BusError {
    RomTooSmall { size: usize },
    RomTooLarge { size: usize },
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Bus {
    pub bios: Vec<u8>,
    pub ewram: Vec<u8>,
    pub iwram: Vec<u8>,
    pub io: Vec<u8>,
    /// 診斷：palette 寫入次數與最後位址（trace_probe 用）。
    pub pal_writes: u64,
    pub pal_last: u32,
    pub palette: Vec<u8>,
    pub vram: Vec<u8>,
    pub oam: Vec<u8>,
    pub rom: Vec<u8>,
    pub sram: Vec<u8>,
    /// 備份記憶體類型（由 ROM 簽章偵測）。
    pub save_kind: SaveKind,
    /// Flash 128 KiB 的 bank（0 或 1）同命令序列狀態。
    flash_bank: u8,
    flash_seq: u8,
    flash_id_mode: bool,
    /// EEPROM 序列位元協定狀態（同 Python `SaveEEPROM` 一致）。
    eeprom_bits: u8,
    eeprom_cmd: u8,
    eeprom_mode: u8,
    eeprom_addr: u32,
    eeprom_buf: u64,
    eeprom_reading: bool,
    eeprom_read_count: u32,
    eeprom_read_page: u32,
    eeprom_left: Option<u32>,
    /// GBA 的 open-bus 近似：最後一次 instruction fetch 的 word。
    pub open_bus: u32,
    /// 離開 BIOS 前最後 prefetch 的 word（mGBA `biosPrefetch`）。非 BIOS 程式
    /// 讀 0x0000_0000..0x3FFF 時硬體回傳呢個值，唔係 BIOS 內容。
    pub bios_prefetch: u32,
    /// 目前 CPU 是否喺 BIOS 區執行（決定 BIOS 讀取回真實內容定 prefetch）。
    pub in_bios: bool,
    /// PPU state 的最小快照，給 video_wait 使用；完整 PPU 尚未搬遷。
    pub ppu_scanline: u16,
    pub ppu_in_hblank: bool,
    /// functional timing：所有 access cost = 1（Python `CpuBus.functional`）。
    pub functional: bool,
    pub ppu: Ppu,
    /// DISPCNT mode 3/4/5：BG VRAM 擴張到 80 KiB。
    pub vram_bitmap_mode: bool,
    /// 中斷控制（0x0400_0200／0202／0208；Python IoRegisters 的獨立欄位）。
    pub ie: u16,
    pub if_: u16,
    /// IntrWait 用：自上次檢查以來「出現過」的 IRQ 旗標（就算已被 ack 都記得）。
    pub irq_seen: u16,
    pub ime: bool,
    /// KEYINPUT 目前值（active-low；未接 keypad 時為 0x03FF）。
    pub keyinput: u16,
    /// HALTCNT 寫入 bit7 後的中斷等待旗標（snapshot 用）。
    pub halt_requested: bool,
    /// KEYCNT 條件是否已觸發（避免重複拉 IRQ）。
    pub keypad_irq_active: bool,
    /// Sound FIFO A/B（32 bytes ring；低位元組先播放）。
    pub sound_fifo_a: Vec<u8>,
    pub sound_fifo_b: Vec<u8>,
    pub fifo_refilling: bool,
    /// 診斷用：逐 tick 記錄 sound 狀態（master、FIFO 長度、ds_a/ds_b）。
    pub sound_debug: bool,
    pub sound_debug_log: Vec<(u64, u8, usize, i32, i32)>,
    /// 診斷用：每次 timer0 FIFO pop 記錄 (samples, ds_a, dma1_source, fifo_len, dma1_sad)。
    pub pop_debug: Vec<(u64, u8, u32, i32, u32)>,
    /// 診斷用：DMA 暫存器寫入記錄 (samples, offset, value)。
    pub dma_write_log: Vec<(u64, u32, u32)>,
    /// PCM 輸出（s16le stereo；NativeCore 取用）。
    pub sound_enabled: bool,
    pub sound_pcm: Vec<u8>,
    pub sound_cycles: u32,
    pub sound_sample_rate: u32,
    /// PSG 四聲道＋DMA Sound 混音器（`crate::sound`）。
    pub sound: Sound,
    /// DMA0–3 的 latched 暫存器（SAD／DAD／CNT_L／CNT_H）。
    pub dma_sad: [u32; 4],
    pub dma_dad: [u32; 4],
    pub dma_cnt_l: [u16; 4],
    pub dma_cnt_h: [u16; 4],
    /// DMA 內部目前位址與剩餘 count。
    pub dma_source: [u32; 4],
    pub dma_dest: [u32; 4],
    /// DMA0–2 原本寫入嘅 DAD 係 0x08000000 以上（ROM/SRAM；硬體上係
    /// invalid destination）：transfer 照樣完成，但唔會將 masked 位址嘅
    /// VRAM/OAM 副作用寫出去。呢個保留 suite「SRAM mirror load」detail
    /// 檢視嘅 OAM[0] 狀態（batch 結果不受影響）。
    pub dma_dest_invalid: [bool; 4],
    pub dma_count: [u32; 4],
    pub dma_active: [bool; 4],
    /// 每通道的 DMA latch：非法來源（DMA0-2 讀 ROM、任何 DMA 讀 SRAM）
    /// 沿用最後一次成功搬運的值（mGBA；suite「ROM load」DMA 測試）。
    pub dma_latch: [u32; 4],
    /// SOUNDCNT_H 原始寫入值（bit11/15 FIFO 重置位唔會存入 io[]）。
    pub sound_fifo_control: u16,
    /// SIO／JOY 暫存器（suite「SIO register R/W tests」）。mGBA 將呢啲值
    /// 放喺 `memory.io[]`，但寫入時會按模式遮罩，所以唔可以直接用 io bytes。
    pub sio_siocnt: u16,
    pub sio_rcnt: u16,
    pub sio_joycnt: u16,
    pub sio_joy_recv: [u16; 2],
    pub sio_joy_trans: [u16; 2],
    pub sio_joystat: u16,
    /// NORMAL_32 模式的 SIODATA32；其他模式寫入忽略、讀回 0。
    pub sio_data32: [u16; 2],
    /// SIOMLT_SEND（multi）／SIODATA8（normal 8/32、GPIO、JOYBUS）。
    pub sio_data8: u16,
    /// Normal 模式傳輸剩餘 cycle（0 = 無傳輸）；完成時清 start bit、
    /// 寫入接收資料並視 SIOCNT bit14 拉 IRQ_SERIAL（suite「SIO timing tests」）。
    pub sio_countdown: u32,
    /// CPU timing model：false = Legacy（Python `cycles.py` 的近似）；
    /// true = mGBA active-region accounting（base fetch + post-body + stall）。
    /// 兩者並存做 A/B；預設 Legacy，唔會影響現有行為。
    pub mgba_timing: bool,
    /// Legacy 模型 + mGBA 的 refill 分佈（L/S post-body、branch N+S），
    /// 唔改 fetch base／data cost，用嚟測試「分佈」假設。
    pub refill_timing: bool,
    /// mGBA `GBAMemoryStall` 的 `lastPrefetchedPc`。
    pub prefetch_last_pc: u32,
    pub dma_pending: Vec<u8>,
    /// 即時 DMA 起動延遲（hardware 喺 CNT_H write 後幾個 cycle 才搶 bus；
    /// 用嚟分開「CPU 快過 DMA」同「DMA 先完成」兩種時序）。
    pub dma_startup: u32,
    /// Timer 0–3：counter／reload／control 與 prescaler 狀態。
    pub timer_counter: [u16; 4],
    pub timer_reload: [u16; 4],
    pub timer_control: [u16; 4],
    pub timer_prescaler: [u32; 4],
    pub timer_cascade: [bool; 4],
    pub timer_irq: [bool; 4],
    pub timer_pending: [u32; 4],
    pub timer_running: [bool; 4],
    /// Timer 剛 enable：本條指令最後 2 cycles 唔計（hardware 喺 write data
    /// phase 完成後才起動；suite Calibration 全部 +2 就是呢個 offset）。
    pub timer_start_pending: [u32; 4],
    /// 32-bit IO write 期間為 true（CNT_L+CNT_H 兩個 beat；timer 喺第二
    /// 個 beat 才起動，所以 start offset 係 2；16-bit CNT_H write 就係 0）。
    pub timer_wide_write: bool,
}

impl Bus {
    pub fn new(rom: Vec<u8>) -> Result<Self, BusError> {
        if rom.len() < 0xC0 {
            return Err(BusError::RomTooSmall { size: rom.len() });
        }
        if rom.len() > 0x0200_0000 {
            return Err(BusError::RomTooLarge { size: rom.len() });
        }
        let save_kind = detect_save_kind(&rom);
        let save_size = match save_kind {
            SaveKind::Sram => 0x8000,
            SaveKind::Flash128 => 0x20000,
            SaveKind::Eeprom512 => 0x200,
            SaveKind::Eeprom8k => 0x2000,
            _ => SRAM_SIZE,
        };
        Ok(Self {
            bios: vec![0; BIOS_END as usize + 1],
            ewram: vec![0; EWRAM_SIZE],
            iwram: vec![0; IWRAM_SIZE],
            io: vec![0; IO_SIZE],
            pal_writes: 0,
            pal_last: 0,
            palette: vec![0; PALETTE_SIZE],
            vram: vec![0; VRAM_SIZE],
            oam: vec![0; OAM_SIZE],
            rom,
            sram: vec![0xFF; save_size],
            save_kind,
            flash_bank: 0,
            flash_seq: 0,
            flash_id_mode: false,
            eeprom_bits: 0,
            eeprom_cmd: 0,
            eeprom_mode: 0,
            eeprom_addr: 0,
            eeprom_buf: 0,
            eeprom_reading: false,
            eeprom_read_count: 0,
            eeprom_read_page: 0,
            eeprom_left: None,
            open_bus: 0,
            bios_prefetch: 0,
            in_bios: false,
            ppu_scanline: 0,
            ppu_in_hblank: false,
            functional: true,
            ppu: Ppu::new(),
            vram_bitmap_mode: false,
            ie: 0,
            if_: 0,
        irq_seen: 0,
            ime: false,
            keyinput: 0x03FF,
            halt_requested: false,
            keypad_irq_active: false,
            sound_fifo_a: Vec::new(),
            sound_fifo_b: Vec::new(),
            fifo_refilling: false,
            sound_debug: false,
            sound_debug_log: Vec::new(),
            pop_debug: Vec::new(),
            dma_write_log: Vec::new(),
            sound_enabled: true,
            sound_pcm: Vec::new(),
            sound_cycles: 0,
            sound_sample_rate: 32768,
            sound: Sound::new(32768),
            dma_sad: [0; 4],
            dma_dad: [0; 4],
            dma_cnt_l: [0; 4],
            dma_cnt_h: [0; 4],
            dma_source: [0; 4],
            dma_dest: [0; 4],
            dma_dest_invalid: [false; 4],
            dma_count: [0; 4],
            dma_active: [false; 4],
            dma_latch: [0; 4],
            sound_fifo_control: 0,
            sio_siocnt: 0,
            sio_rcnt: 0,
            sio_joycnt: 0,
            sio_joy_recv: [0; 2],
            sio_joy_trans: [0; 2],
            sio_joystat: 0,
            sio_data32: [0; 2],
            sio_data8: 0,
            sio_countdown: 0,
            mgba_timing: false,
            refill_timing: false,
            prefetch_last_pc: 0,
            dma_pending: Vec::new(),
            dma_startup: 0,
            timer_counter: [0; 4],
            timer_reload: [0; 4],
            timer_control: [0; 4],
            timer_prescaler: [1; 4],
            timer_cascade: [false; 4],
            timer_irq: [false; 4],
            timer_pending: [0; 4],
            timer_running: [false; 4],
            timer_start_pending: [0; 4],
            timer_wide_write: false,
        })
    }

    /// VRAM 的 128 KiB 位址視窗；尾端 32 KiB 鏡像回 OBJ VRAM。
    fn vram_index(address: u32) -> usize {
        let mut offset = (address - VRAM_START) as usize & (VRAM_WINDOW_SIZE - 1);
        if offset >= VRAM_SIZE {
            offset -= VRAM_WINDOW_SIZE - VRAM_SIZE;
        }
        offset
    }

    fn vram_bg_end(&self) -> usize {
        if self.vram_bitmap_mode { 0x14000 } else { 0x10000 }
    }

    /// VRAM 8-bit 寫入：BG 區複製到整個 halfword，OBJ 區忽略。
    fn write_vram8(&mut self, index: usize, value: u8) {
        if index >= self.vram_bg_end() {
            return;
        }
        let aligned = index & !1;
        self.vram[aligned] = value;
        self.vram[aligned + 1] = value;
    }

    pub fn set_vram_bitmap_mode(&mut self, bitmap_mode: bool) {
        self.vram_bitmap_mode = bitmap_mode;
    }

    /// KEYCNT 條件成立時拉起 keypad IRQ（GBATEK: GBA Keypad Input）。
    pub fn poll_keypad(&mut self) {
        let keycnt = u16::from_le_bytes([self.io[0x132], self.io[0x133]]);
        let condition = keycnt & 0x03FF;
        if keycnt & (1 << 14) == 0 || condition == 0 {
            self.keypad_irq_active = false;
            return;
        }
        let pressed = (!self.keyinput) & 0x03FF;
        let and_mode = keycnt & (1 << 15) != 0;
        let matched = if and_mode {
            (pressed & condition) == condition
        } else {
            pressed & condition != 0
        };
        if matched && !self.keypad_irq_active {
            self.if_ |= 1 << 12;
        self.irq_seen |= 1 << 12;
            self.keypad_irq_active = true;
        } else if !matched {
            self.keypad_irq_active = false;
        }
    }

    /// FIFO A/B 是否要 refill：bit11/15 是 reset 位（舊模型），真實遊戲用
    /// SOUNDCNT_H bit8/9（A 右／左）與 bit12/13（B 右／左）開啟播放。
    fn fifo_enabled(&self, channel: usize) -> bool {
        let bits = self.sound_fifo_control;
        if channel == 0 {
            bits & (1 << 11) != 0 || bits & 0x0300 != 0
        } else {
            bits & (1 << 15) != 0 || bits & 0x3000 != 0
        }
    }

    fn push_fifo(&mut self, channel: usize, data: &[u8]) {
        let fifo = if channel == 0 {
            &mut self.sound_fifo_a
        } else {
            &mut self.sound_fifo_b
        };
        fifo.extend_from_slice(data);
        if fifo.len() > 32 {
            let excess = fifo.len() - 32;
            fifo.drain(..excess);
        }
        self.check_fifo_dma();
    }

    fn check_fifo_dma(&mut self) {
        if self.fifo_refilling {
            return;
        }
        for channel in 0..2 {
            if !self.fifo_enabled(channel) {
                continue;
            }
            let len = if channel == 0 {
                self.sound_fifo_a.len()
            } else {
                self.sound_fifo_b.len()
            };
            if len <= 16 {
                self.trigger_fifo_dma(channel + 1);
            }
        }
    }

    fn trigger_fifo_dma(&mut self, index: usize) {
        let control = self.dma_cnt_h[index];
        if control & 0x8000 == 0 || (control >> 12) & 3 != 3 {
            return;
        }
        if !self.dma_pending.contains(&(index as u8)) {
            self.dma_pending.push(index as u8);
        }
    }

    fn write_sound16(&mut self, offset: u32, value: u16) {
        // 音效暫存器寫入遮罩（mGBA `GBAIOWrite`；suite「I/O read tests」）。
        let mask: u16 = match offset {
            0x60 => 0x007F,
            0x62 => 0xFFC0,
            0x64 => 0x4000,
            0x68 => 0xFFC0,
            0x6C => 0x4000,
            0x70 => 0x00E0,
            0x72 => 0xE000,
            0x74 => 0x4000,
            0x78 => 0xFF00,
            0x7C => 0x40FF,
            0x80 => 0xFF77,
            0x82 => 0x770F,
            0x84 => 0x0080,
            0x88 => 0xC3FE,
            _ => 0xFFFF,
        };
        if offset == 0x82 {
            // FIFO 重置位（bit11/15）係 write-only：先處理再遮罩儲存值，
            // 內部另外記住原始寫入值，俾 `fifo_enabled()` 用。
            self.sound_fifo_control = value;
            if value & (1 << 11) != 0 {
                self.sound_fifo_a.clear();
            }
            if value & (1 << 15) != 0 {
                self.sound_fifo_b.clear();
            }
            let stored = value & mask;
            self.io[0x82..0x84].copy_from_slice(&stored.to_le_bytes());
            self.check_fifo_dma();
            return;
        }
        let raw = value;
        let value = value & mask;
        let index = offset as usize;
        if index + 1 < self.io.len() {
            self.io[index..index + 2].copy_from_slice(&value.to_le_bytes());
        }
        // PSG 狀態跟隨 register 更新（trigger、master enable、wave RAM）。
        // frequency／trigger 是 write-only（唔會存入 io），所以要用原始寫入值。
        let mut regs = [0u8; 0x90];
        regs[0x60..0x90].copy_from_slice(&self.io[0x60..0x90]);
        if index + 1 < 0x90 {
            regs[index] = raw as u8;
            regs[index + 1] = (raw >> 8) as u8;
        }
        self.sound.write_reg(&regs, offset, raw);
    }

    pub fn tick_sound(&mut self, cycles: u32) {
        if !self.sound_enabled || cycles == 0 {
            return;
        }
        // `Sound::tick` 內部以 512 cycles／sample（32.768 kHz）推進 PSG，
        // 每 8 個 PSG tick 產生一個立體聲 s16 sample。DMA Sound 的取樣由
        // timer 溢位推動（`sound_timer_overflow`）。
        self.sound.tick(&self.io, cycles, &mut self.sound_pcm);
        if self.sound_debug && self.sound_debug_log.len() < 4_000_000 {
            self.sound_debug_log.push((
                self.sound.samples,
                ((self.io[0x85] >> 7) & 1) as u8,
                self.sound_fifo_a.len(),
                self.sound.ds_a,
                self.sound.ds_b,
            ));
        }
        if self.sound_pcm.len() > 32768 {
            let excess = self.sound_pcm.len() - 32768;
            self.sound_pcm.drain(..excess);
        }
        self.check_fifo_dma();
    }

    /// Timer 溢位 → DMA Sound A/B 取樣（SOUNDCNT_H bit10/14 選 timer 0/1）。
    fn sound_timer_overflow(&mut self, index: usize) {
        if !self.sound_enabled || index > 1 {
            return;
        }
        self.sound.timer_overflow(
            &self.io,
            index,
            &mut self.sound_fifo_a,
            &mut self.sound_fifo_b,
        );
        if self.sound_debug && index == 0 && self.pop_debug.len() < 4_000_000 {
            self.pop_debug.push((
                self.sound.samples,
                self.sound.ds_a as u8,
                self.dma_source[1],
                self.sound_fifo_a.len() as i32,
                self.dma_sad[1],
            ));
        }
    }

    pub fn take_pcm(&mut self) -> Vec<u8> {
        std::mem::take(&mut self.sound_pcm)
    }

    // ------------------------------------------------------------------
    // 備份記憶體（SRAM／Flash；語意同 Python `memory/savedata.py`）
    // ------------------------------------------------------------------
    fn save_offset(address: u32) -> usize {
        ((address - SRAM_START) as usize) & 0xFFFF
    }

    fn flash_offset(&self, offset: usize) -> usize {
        ((self.flash_bank as usize) * 0x10000 + (offset & 0xFFFF)) % self.sram.len()
    }

    fn read_save8(&self, offset: usize) -> u8 {
        match self.save_kind {
            // Python reference：冇 save backend 時 bus 自己有一個 64 KiB SRAM
            // buffer（寫入會保留），所以 None 要照舊 mirror。
            SaveKind::None => self.sram[offset & 0xFFFF],
            SaveKind::Sram => self.sram[offset & 0x7FFF],
            SaveKind::Eeprom512 | SaveKind::Eeprom8k => 0xFF,
            SaveKind::Flash64 | SaveKind::Flash128 => {
                if self.flash_id_mode {
                    if offset & 1 == 0 {
                        if self.sram.len() > 0x10000 { 0x62 } else { 0xBF }
                    } else if self.sram.len() > 0x10000 {
                        0x13
                    } else {
                        0xD4
                    }
                } else {
                    self.sram[self.flash_offset(offset)]
                }
            }
        }
    }

    fn write_save8(&mut self, offset: usize, value: u8) {
        match self.save_kind {
            SaveKind::None => {
                let index = offset & 0xFFFF;
                self.sram[index] = value;
            }
            SaveKind::Sram => {
                let index = offset & 0x7FFF;
                self.sram[index] = value;
            }
            SaveKind::Flash64 | SaveKind::Flash128 => self.flash_write8(offset, value),
            SaveKind::Eeprom512 | SaveKind::Eeprom8k => {}
        }
    }

    /// Flash 命令序列（同 Python `SaveFlash.write8` 一致）。
    fn flash_write8(&mut self, offset: usize, value: u8) {
        let o = offset & 0xFFFF;
        if self.flash_id_mode {
            if self.flash_seq == 0 && o == 0x5555 && value == 0xAA {
                self.flash_seq = 1;
            } else if self.flash_seq == 1 && o == 0x2AAA && value == 0x55 {
                self.flash_seq = 2;
            } else if self.flash_seq == 2 && o == 0x5555 && value == 0xF0 {
                self.flash_id_mode = false;
                self.flash_seq = 0;
            }
            return;
        }
        if self.flash_seq == 0 {
            if o == 0x5555 && value == 0xAA {
                self.flash_seq = 1;
            } else if self.sram.len() > 0x10000 && o == 0 {
                self.flash_bank = value & 1;
            }
            return;
        }
        if self.flash_seq == 1 {
            self.flash_seq = if o == 0x2AAA && value == 0x55 { 2 } else { 0 };
            return;
        }
        if self.flash_seq == 2 {
            if o == 0x5555 && value == 0x90 {
                self.flash_id_mode = true;
                self.flash_seq = 0;
            } else if o == 0x5555 && value == 0x80 {
                self.flash_seq = 3;
            } else if o == 0x5555 && value == 0xA0 {
                self.flash_seq = 5;
            } else {
                self.flash_seq = 0;
            }
            return;
        }
        if self.flash_seq == 3 {
            self.flash_seq = if o == 0x5555 && value == 0xAA { 4 } else { 0 };
            return;
        }
        if self.flash_seq == 4 {
            self.flash_seq = if o == 0x2AAA && value == 0x55 { 6 } else { 0 };
            return;
        }
        if self.flash_seq == 6 {
            if o == 0x5555 && value == 0x10 {
                self.sram.fill(0xFF);
            } else if value == 0x30 {
                let base = self.flash_offset(offset) & !0xFFF;
                let end = (base + 0x1000).min(self.sram.len());
                self.sram[base..end].fill(0xFF);
            }
            self.flash_seq = 0;
            return;
        }
        if self.flash_seq == 5 {
            let index = self.flash_offset(offset);
            self.sram[index] &= value;
            self.flash_seq = 0;
        }
    }

    // ------------------------------------------------------------------
    // EEPROM（序列位元協定；同 Python `memory/savedata.py::SaveEEPROM`）
    // ------------------------------------------------------------------
    fn eeprom_covers(address: u32) -> bool {
        (0x0D00_0000..0x0E00_0000).contains(&address)
    }

    fn eeprom_n_addr(&self) -> u32 {
        if self.sram.len() == 0x200 { 6 } else { 14 }
    }

    fn eeprom_reset_cmd(&mut self) {
        self.eeprom_bits = 0;
        self.eeprom_mode = 0;
        self.eeprom_addr = 0;
        self.eeprom_buf = 0;
    }

    fn eeprom_commit_page(&mut self) {
        let pages = self.sram.len() / 8;
        let page = (self.eeprom_addr & (pages as u32 - 1)) as usize;
        for k in 0..8 {
            self.sram[page * 8 + k] = ((self.eeprom_buf >> (8 * k)) & 0xFF) as u8;
        }
        self.eeprom_reset_cmd();
    }

    /// 每個 EEPROM 讀取回傳一個 bit（0／1）；閒置時回 1（Ready）。
    fn eeprom_read_bit(&mut self) -> u8 {
        if !self.eeprom_reading {
            return 1;
        }
        let c = self.eeprom_read_count;
        self.eeprom_read_count += 1;
        if c < 4 {
            return 0;
        }
        if c < 68 {
            let page = self.eeprom_read_page as usize;
            let mut word = 0u64;
            for k in 0..8 {
                word |= (self.sram[page * 8 + k] as u64) << (8 * k);
            }
            return ((word >> (63 - (c - 4))) & 1) as u8;
        }
        self.eeprom_reading = false;
        1
    }

    fn eeprom_write_bit(&mut self, bit: u8) {
        let bit = bit & 1;
        let left = self.eeprom_left;
        if let Some(value) = left {
            if value > 0 {
                self.eeprom_left = Some(value - 1);
            }
        }
        if self.eeprom_reading {
            self.eeprom_reading = false;
        }
        match left {
            Some(value) if value > 0 => self.eeprom_write_bit_stream(bit, value),
            _ => self.eeprom_write_bit_fixed(bit),
        }
    }

    /// DMA 串流：位址寬度動態（同 Python `write_bit` 的 `_left` 分支）。
    fn eeprom_write_bit_stream(&mut self, bit: u8, left: u32) {
        if self.eeprom_bits == 0 {
            self.eeprom_cmd = bit;
            self.eeprom_bits = 1;
            return;
        }
        if self.eeprom_bits == 1 {
            if self.eeprom_cmd == 1 && bit == 1 {
                self.eeprom_mode = 1;
            } else if self.eeprom_cmd == 1 && bit == 0 {
                self.eeprom_mode = 2;
            } else {
                self.eeprom_reset_cmd();
                return;
            }
            self.eeprom_bits = 2;
            self.eeprom_addr = 0;
            self.eeprom_buf = 0;
            return;
        }
        if self.eeprom_mode == 2 {
            if left > 65 {
                self.eeprom_addr = (self.eeprom_addr << 1) | bit as u32;
                self.eeprom_bits = self.eeprom_bits.saturating_add(1);
                return;
            }
            if left > 1 {
                self.eeprom_buf = (self.eeprom_buf << 1) | bit as u64;
                return;
            }
            if left == 1 {
                self.eeprom_commit_page();
            }
            return;
        }
        if self.eeprom_mode == 1 {
            if left > 1 {
                self.eeprom_addr = (self.eeprom_addr << 1) | bit as u32;
                self.eeprom_bits = self.eeprom_bits.saturating_add(1);
                return;
            }
            // left == 1：'0' 終止位 → 進入讀取輸出
            self.eeprom_reading = true;
            self.eeprom_read_count = 0;
            let pages = self.sram.len() / 8;
            self.eeprom_read_page = self.eeprom_addr & (pages as u32 - 1);
            self.eeprom_reset_cmd();
            return;
        }
        self.eeprom_reset_cmd();
    }

    /// 單一存取（CPU 直寫）：固定位址寬度（512B = 6 bit、8KB = 14 bit）。
    fn eeprom_write_bit_fixed(&mut self, bit: u8) {
        if self.eeprom_bits == 0 {
            self.eeprom_cmd = bit;
            self.eeprom_bits = 1;
            return;
        }
        if self.eeprom_bits == 1 {
            if self.eeprom_cmd == 1 && bit == 1 {
                self.eeprom_mode = 1;
            } else if self.eeprom_cmd == 1 && bit == 0 {
                self.eeprom_mode = 2;
            } else {
                self.eeprom_reset_cmd();
                return;
            }
            self.eeprom_bits = 2;
            self.eeprom_addr = 0;
            self.eeprom_buf = 0;
            return;
        }
        if self.eeprom_mode == 1 {
            if (self.eeprom_bits as u32) < 2 + self.eeprom_n_addr() {
                self.eeprom_addr = (self.eeprom_addr << 1) | bit as u32;
                self.eeprom_bits += 1;
                return;
            }
            self.eeprom_reading = true;
            self.eeprom_read_count = 0;
            let pages = self.sram.len() / 8;
            self.eeprom_read_page = self.eeprom_addr & (pages as u32 - 1);
            self.eeprom_reset_cmd();
            return;
        }
        if self.eeprom_mode == 2 {
            if (self.eeprom_bits as u32) < 2 + self.eeprom_n_addr() {
                self.eeprom_addr = (self.eeprom_addr << 1) | bit as u32;
                self.eeprom_bits += 1;
                return;
            }
            if (self.eeprom_bits as u32) < 2 + self.eeprom_n_addr() + 64 {
                self.eeprom_buf = (self.eeprom_buf << 1) | bit as u64;
                self.eeprom_bits += 1;
                return;
            }
            self.eeprom_commit_page();
            return;
        }
        self.eeprom_reset_cmd();
    }

    // ------------------------------------------------------------------
    // DMA0–3：暫存器、reload、immediate transfer
    // ------------------------------------------------------------------
    fn dma_decode(offset: u32) -> Option<(usize, u8)> {
        if !(0xB0..=0xDF).contains(&offset) {
            return None;
        }
        let relative = offset - 0xB0;
        let index = (relative / 0x0C) as usize;
        if index > 3 {
            return None;
        }
        let field = match relative % 0x0C {
            0..=3 => 0,  // SAD
            4..=7 => 1,  // DAD
            8 | 9 => 2,  // CNT_L
            10 | 11 => 3, // CNT_H
            _ => return None,
        };
        Some((index, field))
    }

    fn dma_count_value(index: usize, value: u16) -> u32 {
        if value == 0 {
            if index == 3 { 0x10000 } else { 0x4000 }
        } else {
            value as u32
        }
    }

    fn read_dma16(&self, offset: u32) -> u16 {
        let Some((index, field)) = Self::dma_decode(offset) else { return 0 };
        match field {
            0 => (self.dma_sad[index] >> ((offset & 2) * 8)) as u16,
            1 => (self.dma_dad[index] >> ((offset & 2) * 8)) as u16,
            2 => self.dma_cnt_l[index],
            _ => self.dma_cnt_h[index],
        }
    }

    fn write_dma16(&mut self, offset: u32, value: u16) {
        let Some((index, field)) = Self::dma_decode(offset) else { return };
        if self.sound_debug && self.dma_write_log.len() < 200_000 {
            self.dma_write_log.push((self.sound.samples, offset, value as u32));
        }
        match field {
            0 => {
                let shift = (offset & 2) * 8;
                self.dma_sad[index] = ((self.dma_sad[index] & !(0xFFFF << shift))
                    | ((value as u32) << shift))
                    & Self::DMA_SRC_MASK[index];
            }
            1 => {
                let shift = (offset & 2) * 8;
                let merged = (self.dma_dad[index] & !(0xFFFF << shift))
                    | ((value as u32) << shift);
                self.dma_dest_invalid[index] = index < 3 && merged >= 0x0800_0000;
                self.dma_dad[index] = merged & Self::DMA_DST_MASK[index];
            }
            2 => self.dma_cnt_l[index] = value,
            _ => {
                // mGBA `GBADMAWriteCNT_HI`：DMA0–2 只保留 0xF7E0、DMA3 0xFFE0
                // （suite「I/O read tests」DMAxCNT_HI 的讀回值）。
                let value = value
                    & if index < 3 {
                        0xF7E0
                    } else {
                        0xFFE0
                    };
                let previous = self.dma_cnt_h[index];
                self.dma_cnt_h[index] = value;
                if value & 0x8000 == 0 {
                    self.dma_active[index] = false;
                    self.dma_pending.retain(|&pending| pending != index as u8);
                    return;
                }
                if previous & 0x8000 == 0 {
                    self.dma_source[index] = self.dma_sad[index];
                    self.dma_dest[index] = self.dma_dad[index];
                    self.dma_count[index] = Self::dma_count_value(index, self.dma_cnt_l[index]);
                    self.dma_active[index] = true;
                    if (value >> 12) & 3 == 0 && !self.dma_pending.contains(&(index as u8)) {
                        self.dma_pending.push(index as u8);
                        if !self.functional {
                            self.dma_startup = 3;
                        }
                    }
                }
            }
        }
    }

    fn write_dma32(&mut self, offset: u32, value: u32) {
        let Some((_, field)) = Self::dma_decode(offset) else { return };
        if self.sound_debug && self.dma_write_log.len() < 200_000 {
            self.dma_write_log.push((self.sound.samples, offset, value));
        }
        if field == 0 {
            let index = (offset - 0xB0) as usize / 0x0C;
            self.dma_sad[index] = value & Self::DMA_SRC_MASK[index];
            return;
        }
        if field == 1 {
            let index = (offset - 0xB0) as usize / 0x0C;
            self.dma_dest_invalid[index] = index < 3 && value >= 0x0800_0000;
            self.dma_dad[index] = value & Self::DMA_DST_MASK[index];
            return;
        }
        self.write_dma16(offset, value as u16);
        self.write_dma16(offset.wrapping_add(2), (value >> 16) as u16);
    }

    /// DMA 位址遮罩（mGBA `DMA_SRC_MASK` / `DMA_DST_MASK`）：DMA0–2 的
    /// bit27 被清掉，所以 0x08xxxxxx（ROM）同 0x0Exxxxxx（SRAM）會鏡射到
    /// 0x00xxxxxx（BIOS/open bus）同 0x06xxxxxx（VRAM）——呢個就係 suite
    /// 「DMA0 讀 ROM/SRAM」實際行為，唔需要額外封鎖。
    /// bit0 保留（寫入值原樣讀返，同硬體／mGBA 一致）；傳輸本身喺啟動時另做
    /// 寬度對齊（`width_mask`）。
    const DMA_SRC_MASK: [u32; 4] = [0x07FF_FFFF, 0x0FFF_FFFF, 0x0FFF_FFFF, 0x0FFF_FFFF];
    const DMA_DST_MASK: [u32; 4] = [0x07FF_FFFF, 0x07FF_FFFF, 0x07FF_FFFF, 0x0FFF_FFFF];

    fn dma_step(control: u8) -> i32 {
        match control {
            0 => 1,
            1 => -1,
            2 => 0,
            _ => 1,
        }
    }

    /// 執行所有 pending DMA；回傳 Python reference 的 cycle 成本。
    pub fn service_dma(&mut self) -> u32 {
        let mut total = 0;
        while !self.dma_pending.is_empty() {
            let index = self.dma_pending.remove(0) as usize;
            total += self.run_dma(index);
        }
        total
    }

    fn run_fifo_dma(&mut self, index: usize) -> u32 {
        let dest = self.dma_dad[index];
        self.fifo_refilling = true;
        for _ in 0..4 {
            let source = self.dma_source[index];
            let value = self.read32(source);
            self.write32(dest, value);
            self.dma_source[index] = source.wrapping_add(4);
        }
        self.fifo_refilling = false;
        self.check_fifo_dma();
        10
    }

    fn run_dma(&mut self, index: usize) -> u32 {
        if !self.dma_active[index] {
            return 0;
        }
        let control = self.dma_cnt_h[index];
        if (control >> 12) & 3 == 3 && (index == 1 || index == 2) {
            return self.run_fifo_dma(index);
        }
        let width = if control & (1 << 10) != 0 { 4 } else { 2 };
        let count = self.dma_count[index];
        if count == 0 {
            self.dma_active[index] = false;
            return 0;
        }
        // mGBA 在 DMA 啟動時 `nextSource &= -width; nextDest &= -width;`
        // （GBADMAWriteCNT_HI）；SRAM 都一樣，所以 DMA 由 SRAM+2 讀 32-bit
        // 會讀 SRAM[0]（suite SRAM load DMA 未對齊列）。
        let width_mask = if width == 4 { !3 } else { !1 };
        self.dma_source[index] &= width_mask;
        self.dma_dest[index] &= width_mask;
        let src_control = ((control >> 7) & 3) as u8;
        // mGBA `GBADMAWriteCNT_HI`：source 一旦落喺 ROM 區（0x08xxxxxx–0x0Dxxxxxx）
        // 就強制 `sourceOffset = width`，即無視 fixed／decrement 控制一路遞增
        // （suite「=ROM」嘅 Imm H／Imm W 同「-ROM」測試）。
        let src_rom_forced = (0x0800_0000..0x0E00_0000).contains(&self.dma_source[index]);
        if src_control == 3 && !src_rom_forced {
            self.dma_active[index] = false;
            return 0;
        }
        // mGBA `GBADMAService`：只有 source >= EWRAM（0x02000000）先會真正讀取；
        // 其他（BIOS、open bus）沿用該通道上一次搬運值 `info->latch`。
        // 16-bit 讀入後複製成 32-bit latch；寫出時再一次過由 latch 取 lane。
        let dst_control = ((control >> 5) & 3) as u8;
        let src_step = (Self::dma_step(src_control) as i64) * (width as i64);
        let dst_step = (Self::dma_step(dst_control) as i64) * (width as i64);
        // EEPROM 寫入串流：DMA 去 0x0D000000 時，位址寬度要按 transfer 長度判斷
        // （同 Python `devices/dma.py` 的 `begin_stream(count)`）。
        if self.save_kind.is_eeprom() && Self::eeprom_covers(self.dma_dest[index]) {
            self.eeprom_left = Some(count);
        }
        let src_start = self.dma_source[index];
        let dst_start = self.dma_dest[index];
        for _ in 0..count {
            let source = self.dma_source[index];
            let dest = self.dma_dest[index];
            if width == 4 {
                if source >= 0x0200_0000 {
                    let address = if (0x0E00_0000..=0x0FFF_FFFF).contains(&source) {
                        source // SRAM：8-bit 匯流排讀原始位址
                    } else {
                        source & !3
                    };
                    self.dma_latch[index] = self.read32(address);
                }
                if !self.dma_dest_invalid[index] {
                    self.write32(dest, self.dma_latch[index]);
                }
            } else {
                if source >= 0x0200_0000 {
                    let address = if (0x0E00_0000..=0x0FFF_FFFF).contains(&source) {
                        source // SRAM：8-bit 匯流排讀原始位址
                    } else {
                        source & !1
                    };
                    let half = self.read16(address) as u32;
                    self.dma_latch[index] = half | (half << 16);
                }
                let shift = (dest & 2) * 8;
                if !self.dma_dest_invalid[index] {
                    self.write16(dest, (self.dma_latch[index] >> shift) as u16);
                }
            }
            // ROM 區強制遞增（見上面 `src_rom_forced` 註解）：一旦搬運途中
            // 離開 ROM 區就回復原本的 src control。
            let src_in_rom = (0x0800_0000..0x0E00_0000).contains(&source);
            let step = if src_in_rom { width as i64 } else { src_step };
            self.dma_source[index] = (self.dma_source[index] as i64 + step) as u32;
            self.dma_dest[index] = (self.dma_dest[index] as i64 + dst_step) as u32;
        }

        let (src_cost, dst_cost) = if self.functional {
            (1, 1)
        } else {
            (
                self.access_cost(src_start, width, false) + self.video_wait(src_start, width),
                self.access_cost(dst_start, width, false) + self.video_wait(dst_start, width),
            )
        };
        let mut cycles = src_cost + dst_cost;
        if count > 1 {
            let (src_seq, dst_seq) = if self.functional {
                (1, 1)
            } else {
                (
                    self.access_cost(src_start, width, true) + self.video_wait(src_start, width),
                    self.access_cost(dst_start, width, true) + self.video_wait(dst_start, width),
                )
            };
            cycles += (count - 1) * (src_seq + dst_seq);
        }
        let both_gamepak = (0x08..=0x0D).contains(&(src_start >> 24))
            && (0x08..=0x0D).contains(&(dst_start >> 24));
        cycles += if both_gamepak { 0 } else { 2 };
        // Game Pak DMA 的 first-access rounding：WAITCNT 的 WS0 first (bits 2-3)
        // 係 0 時 hardware 有效 wait 會少 1（seq=1、prefetch off），first=1 時
        // 則視乎 seq／prefetch 多 1。呢個係 suite Timing DMA ROM 測試
        // 校準出嚟的 ±1（只影響 timed 模式）。
        if !self.functional {
            let waitcnt = self.waitcnt();
            let first_idx = (waitcnt >> 2) & 0x3;
            let seq_bit = (waitcnt >> 4) & 1 != 0;
            let prefetch = self.prefetch_enabled();
            let src_rom = (0x08..=0x0D).contains(&(src_start >> 24));
            let dst_rom = (0x08..=0x0D).contains(&(dst_start >> 24));
            if both_gamepak {
                if first_idx == 1 {
                    if !(seq_bit && !prefetch) {
                        cycles += 1;
                    }
                } else if seq_bit && !prefetch {
                    cycles -= 1;
                }
            } else if dst_rom && !src_rom && prefetch && !seq_bit {
                cycles += 1;
            } else if src_rom && !dst_rom && prefetch && seq_bit {
                // 對稱的 from-ROM rounding（P.S／PNS 兩個 config）。
                cycles += 1;
            }
        }

        self.dma_count[index] = 0;
        if control & 0x0200 != 0 {
            self.dma_count[index] = Self::dma_count_value(index, self.dma_cnt_l[index]);
            self.dma_source[index] = self.dma_sad[index];
            if dst_control == 3 {
                self.dma_dest[index] = self.dma_dad[index];
            }
        } else {
            self.dma_active[index] = false;
            self.dma_cnt_h[index] = control & !0x8000;
            if control & 0x4000 != 0 {
                self.if_ |= 1 << (8 + index);
        self.irq_seen |= 1 << (8 + index);
            }
        }
        cycles
    }

    /// 套用 HLE post-boot 的 memory 狀態：ROM header → EWRAM、清除 IRQ check。
    pub fn apply_post_boot(&mut self) {
        let header_len = self.rom.len().min(0xC0);
        self.ewram[..header_len].copy_from_slice(&self.rom[..header_len]);
        self.write32(0x0300_7FF8, 0);
        self.write32(0x0300_7FFC, 0);
        // HLE 開機等價於 mGBA hleBios 跑完之後離開 BIOS：biosPrefetch 係
        // 最後 prefetch 嘅 word 0xE3A02004（mov r2,#4）。非 BIOS 程式讀
        // BIOS 視窗時會見到呢個值（suite「BIOS load」）。
        self.bios_prefetch = 0xE3A0_2004;
    }

    /// WAITCNT（0x04000204）目前值。
    pub fn waitcnt(&self) -> u16 {
        u16::from_le_bytes([self.io[0x204], self.io[0x205]])
    }

    pub fn set_waitcnt(&mut self, value: u16) {
        self.io[0x204..0x206].copy_from_slice(&value.to_le_bytes());
    }

    /// WAITCNT bit14：Game Pak prefetch buffer 開啟（Python `cycles._fetch` 用）。
    pub fn prefetch_enabled(&self) -> bool {
        self.waitcnt() & 0x4000 != 0
    }

    /// mGBA 公約的 16-bit wait（世界觀：我哋 `access_cost` 係 mGBA + 1）。
    fn mgba_wait16(&self, address: u32, sequential: bool) -> u32 {
        self.access_cost(address, 2, sequential).saturating_sub(1)
    }

    /// mGBA `GBAMemoryStall` 的移植：prefetch 開啟、active region（pc）係
    /// ROM 時，buffer 會喺等待期間 prefetch 最多 8 個 halfword，從而吸收
    /// 部分 wait。`wait` 用 mGBA 公約（唔含 +1）；回傳值可以係負數
    /// （mGBA 會用「吸收」扣多過 wait），由 caller 加埋一齊先 clamp。
    pub fn mgba_stall(&mut self, pc: u32, wait: i32) -> i32 {
        if !self.prefetch_enabled() || !(0x0800_0000..=0x0DFF_FFFF).contains(&pc) {
            return wait;
        }
        let s = self.mgba_wait16(pc, true).max(1) as i64;
        let nonseq = self.mgba_wait16(pc, false) as i64;
        let dist = self.prefetch_last_pc.wrapping_sub(pc) as i64;
        let previous = if dist < 16 { dist >> 1 } else { 0 };
        let max_loads = (8 - previous).max(1);
        let mut stall = s + 1;
        let mut loads = 1i64;
        while stall < wait as i64 && loads < max_loads {
            stall += s;
            loads += 1;
        }
        self.prefetch_last_pc = pc.wrapping_add((2 * (loads + previous - 1)) as u32);

        let mut adjusted = (wait as i64).max(stall);
        adjusted -= nonseq - s;
        adjusted -= stall;
        adjusted as i32
    }

    /// mGBA 式 data access（`GBALoad/Store` 內 `wait += 2` + stall），
    /// 回傳 mGBA 公約的 cycle 數（可以因 prefetch 吸收而 < 2）。
    pub fn mgba_data_cost(&mut self, pc: u32, address: u32, width: u32) -> i32 {
        let wait = self.access_cost(address, width, false).saturating_sub(1) as i32;
        let mut total = wait + 2;
        if address < 0x0800_0000 {
            total = self.mgba_stall(pc, total);
        }
        total
    }

    /// mGBA `GBAStore*`：region waitstates 之後只 `++wait`（load 係 `+2`），
    /// 再做 `GBAMemoryStall`。
    pub fn mgba_store_cost(&mut self, pc: u32, address: u32, width: u32) -> i32 {
        let wait = self.access_cost(address, width, false) as i32;
        if address < 0x0800_0000 {
            self.mgba_stall(pc, wait)
        } else {
            wait
        }
    }

    /// mGBA `ARM_LOAD_POST_BODY`／`ARM_STORE_POST_BODY`：L/S 之後 pipeline
    /// 由 S 變 N 的差額（我哋 +1 公約下相減會抵消，所以直接用差值）。
    pub fn mgba_refill_delta(&self, pc: u32, width: u32) -> u32 {
        self.access_cost(pc, width, false)
            .saturating_sub(self.access_cost(pc, width, true))
    }

    /// 單次存取的基礎 cycle（不含 PPU video wait）。
    /// 對應 GBATEK WAITCNT 與 Python `bus.access.access_cycles`。
    pub fn access_cost(&self, address: u32, width: u32, sequential: bool) -> u32 {
        if self.functional {
            return 1;
        }
        const FIRST: [u32; 4] = [5, 4, 3, 9];
        const WS0_SECOND: [u32; 2] = [3, 2];
        const WS1_SECOND: [u32; 2] = [5, 2];
        const WS2_SECOND: [u32; 2] = [9, 2];
        let address = if width > 1 { address & !(width - 1) } else { address };
        let page = address >> 24;
        let waitcnt = self.waitcnt() as u32;
        if (0x08..=0x0D).contains(&page) {
            let sequential = if (address & 0x1FFFF) == 0 { false } else { sequential };
            let (first, second) = if (0x0A..=0x0B).contains(&page) {
                (FIRST[((waitcnt >> 5) & 0x3) as usize], WS1_SECOND[((waitcnt >> 7) & 0x1) as usize])
            } else if (0x0C..=0x0D).contains(&page) {
                (FIRST[((waitcnt >> 8) & 0x3) as usize], WS2_SECOND[((waitcnt >> 10) & 0x1) as usize])
            } else {
                (FIRST[((waitcnt >> 2) & 0x3) as usize], WS0_SECOND[((waitcnt >> 4) & 0x1) as usize])
            };
            return if width == 4 {
                if sequential { second + second } else { first + second }
            } else if sequential { second } else { first };
        }
        if page == 0x0E || page == 0x0F {
            return FIRST[(waitcnt & 0x3) as usize];
        }
        if page == 0x02 {
            return if width == 4 { 6 } else { 3 };
        }
        if page == 0x05 || page == 0x06 {
            return if width == 4 { 2 } else { 1 };
        }
        1
    }

    /// CPU 存取 VRAM/OAM/Palette 時的 video contention。
    /// 對應 Python `AddressBus.video_wait`。
    pub fn video_wait(&self, address: u32, _width: u32) -> u32 {
        let palette = (0x0500_0000..0x0500_0400).contains(&address);
        let vram = (0x0600_0000..0x0601_8000).contains(&address);
        let oam = (0x0700_0000..0x0700_0400).contains(&address);
        if !(palette || vram || oam) {
            return 0;
        }
        let dispcnt = u16::from_le_bytes([self.io[0], self.io[1]]);
        if dispcnt & 0x80 != 0 || self.ppu_scanline >= 160 {
            return 0;
        }
        if self.ppu_in_hblank {
            if oam && dispcnt & 0x20 == 0 {
                return 1;
            }
            return 0;
        }
        1
    }

    fn trigger_dma_for_timing(&mut self, timing: u16) {
        for index in 0..4 {
            let control = self.dma_cnt_h[index];
            if control & 0x8000 == 0 || (control >> 12) & 3 != timing {
                continue;
            }
            if !self.dma_pending.contains(&(index as u8)) {
                self.dma_pending.push(index as u8);
            }
        }
    }

    pub fn tick(&mut self, cycles: u32) {
        self.ppu.advance(cycles);
        let irq = self.ppu.take_irq();
        if irq != 0 {
            self.if_ |= irq & 0x0007;
        self.irq_seen |= irq & 0x0007;
        }
        let events = self.ppu.take_events();
        for event in events {
            if event == 1 {
                self.trigger_dma_for_timing(1);
            } else if event == 2 {
                self.trigger_dma_for_timing(2);
            }
        }
        self.ppu_scanline = self.ppu.scanline;
        self.ppu_in_hblank = self.ppu.in_hblank;
        self.tick_timers(cycles);
        self.tick_sound(cycles);
        if self.sio_countdown > 0 {
            if cycles >= self.sio_countdown {
                self.sio_countdown = 0;
                self.sio_complete();
            } else {
                self.sio_countdown -= cycles;
            }
        }
    }

    // ------------------------------------------------------------------
    // Timer 0–3
    // ------------------------------------------------------------------
    fn timer_decode(offset: u32) -> Option<(usize, bool)> {
        if !(0x100..=0x10F).contains(&offset) {
            return None;
        }
        let relative = offset - 0x100;
        Some(((relative / 4) as usize, relative % 4 >= 2))
    }

    fn read_timer16(&self, offset: u32) -> u16 {
        let Some((index, control)) = Self::timer_decode(offset) else { return 0 };
        if control {
            self.timer_control[index]
        } else {
            (self.timer_counter[index] >> ((offset & 2) * 8)) as u16
        }
    }

    fn write_timer16(&mut self, offset: u32, value: u16) {
        let Some((index, control)) = Self::timer_decode(offset) else { return };
        if !control {
            self.timer_reload[index] = value;
            return;
        }
        let was_running = self.timer_running[index];
        self.timer_control[index] = value;
        self.timer_prescaler[index] = [1, 64, 256, 1024][(value & 3) as usize];
        self.timer_cascade[index] = value & 0x04 != 0 && index > 0;
        self.timer_irq[index] = value & 0x40 != 0;
        self.timer_pending[index] = 0;
        let running = value & 0x80 != 0;
        self.timer_running[index] = running;
        if running && !was_running {
            self.timer_counter[index] = self.timer_reload[index];
            self.timer_start_pending[index] = if self.timer_wide_write { 2 } else { 0 };
        } else if !running {
            self.timer_start_pending[index] = 0;
        }
    }

    fn write_timer32(&mut self, offset: u32, value: u32) {
        self.timer_wide_write = true;
        self.write_timer16(offset, value as u16);
        self.write_timer16(offset.wrapping_add(2), (value >> 16) as u16);
        self.timer_wide_write = false;
    }

    fn add_timer(&mut self, index: usize, increments: u32) {
        let mut value = self.timer_counter[index] as u32 + increments;
        let mut overflows = 0u32;
        while value > 0xFFFF {
            value = self.timer_reload[index] as u32 + (value - 0x10000);
            overflows += 1;
        }
        self.timer_counter[index] = value as u16;
        for _ in 0..overflows {
            if self.timer_irq[index] {
                self.if_ |= 1 << (3 + index);
        self.irq_seen |= 1 << (3 + index);
            }
            self.sound_timer_overflow(index);
            if index + 1 < 4 && self.timer_running[index + 1] && self.timer_cascade[index + 1] {
                self.add_timer(index + 1, 1);
            }
        }
    }

    pub fn tick_timers(&mut self, cycles: u32) {
        for index in 0..4 {
            // 起動中的 timer 只計本條指令扣掉 offset 之後的 cycles。
            let cycles = if self.timer_start_pending[index] != 0 {
                let skip = self.timer_start_pending[index];
                self.timer_start_pending[index] = 0;
                cycles.saturating_sub(skip)
            } else {
                cycles
            };
            if !self.timer_running[index] || self.timer_cascade[index] {
                continue;
            }
            self.timer_pending[index] = self.timer_pending[index].wrapping_add(cycles);
            let prescaler = self.timer_prescaler[index].max(1);
            let increments = self.timer_pending[index] / prescaler;
            self.timer_pending[index] %= prescaler;
            if increments != 0 {
                self.add_timer(index, increments);
            }
        }
    }

    pub fn snapshot_section(&self) -> Vec<u8> {
        let mut out = Vec::new();
        put_u32(&mut out, self.sram.len() as u32);
        out.extend_from_slice(&self.ewram);
        out.extend_from_slice(&self.iwram);
        out.extend_from_slice(&self.palette);
        out.extend_from_slice(&self.vram);
        out.extend_from_slice(&self.oam);
        out.extend_from_slice(&self.sram);
        out.extend_from_slice(&self.io);
        put_u32(&mut out, self.ie as u32);
        put_u32(&mut out, self.if_ as u32);
        put_u32(&mut out, u32::from(self.ime));
        out.push(u8::from(self.halt_requested));
        out
    }

    pub fn restore_section(&mut self, data: &[u8]) -> Result<(), String> {
        let mut reader = SnapshotReader::new(data);
        let sram_len = reader.u32().ok_or("BUS snapshot 被截斷")? as usize;
        for target in [
            &mut self.ewram,
            &mut self.iwram,
            &mut self.palette,
            &mut self.vram,
            &mut self.oam,
        ] {
            let len = target.len();
            target.copy_from_slice(reader.bytes(len).ok_or("BUS snapshot 區域被截斷")?);
        }
        let sram = reader.bytes(sram_len).ok_or("BUS snapshot SRAM 被截斷")?;
        self.sram.fill(0xFF);
        let copy_len = sram_len.min(self.sram.len());
        self.sram[..copy_len].copy_from_slice(&sram[..copy_len]);
        self.io.copy_from_slice(reader.bytes(0x400).ok_or("BUS snapshot IO 被截斷")?);
        self.ie = reader.u32().ok_or("BUS snapshot 被截斷")? as u16;
        self.if_ = reader.u32().ok_or("BUS snapshot 被截斷")? as u16;
        self.ime = reader.u32().ok_or("BUS snapshot 被截斷")? != 0;
        self.halt_requested = reader.u8().ok_or("BUS snapshot 被截斷")? != 0;
        self.vram_bitmap_mode = matches!(self.io[0] & 7, 3 | 4 | 5);
        if !reader.finish() {
            return Err("BUS snapshot 長度不符".to_string());
        }
        Ok(())
    }

    pub fn snapshot_dma(&self) -> Vec<u8> {
        let mut out = Vec::new();
        for index in 0..4 {
            put_u32(&mut out, self.dma_sad[index]);
            put_u32(&mut out, self.dma_dad[index]);
            put_u32(&mut out, self.dma_cnt_l[index] as u32);
            put_u32(&mut out, self.dma_cnt_h[index] as u32);
            put_u32(&mut out, self.dma_source[index]);
            put_u32(&mut out, self.dma_dest[index]);
            put_u32(&mut out, self.dma_count[index]);
            put_u32(&mut out, self.dma_cnt_h[index] as u32);
            out.push(u8::from(self.dma_active[index]));
            out.push(((self.dma_cnt_h[index] >> 14) & 1) as u8);
        }
        out.push(self.dma_pending.len().min(4) as u8);
        for index in 0..4 {
            out.push(*self.dma_pending.get(index).unwrap_or(&0));
        }
        out
    }

    pub fn restore_dma(&mut self, data: &[u8]) -> Result<(), String> {
        let mut reader = SnapshotReader::new(data);
        for index in 0..4 {
            self.dma_sad[index] = reader.u32().ok_or("DMA snapshot 被截斷")?;
            self.dma_dad[index] = reader.u32().ok_or("DMA snapshot 被截斷")?;
            self.dma_cnt_l[index] = reader.u32().ok_or("DMA snapshot 被截斷")? as u16;
            self.dma_cnt_h[index] = reader.u32().ok_or("DMA snapshot 被截斷")? as u16;
            self.dma_source[index] = reader.u32().ok_or("DMA snapshot 被截斷")?;
            self.dma_dest[index] = reader.u32().ok_or("DMA snapshot 被截斷")?;
            self.dma_count[index] = reader.u32().ok_or("DMA snapshot 被截斷")?;
            let control = reader.u32().ok_or("DMA snapshot 被截斷")?;
            self.dma_cnt_h[index] = control as u16;
            self.dma_active[index] = reader.u8().ok_or("DMA snapshot 被截斷")? != 0;
            let _irq = reader.u8().ok_or("DMA snapshot 被截斷")?;
        }
        let pending_len = reader.u8().ok_or("DMA snapshot 被截斷")? as usize;
        let mut pending = Vec::new();
        for index in 0..4u8 {
            let value = reader.u8().ok_or("DMA snapshot 被截斷")?;
            if index < pending_len as u8 && value < 4 {
                pending.push(value);
            }
        }
        self.dma_pending = pending;
        if !reader.finish() {
            return Err("DMA snapshot 長度不符".to_string());
        }
        Ok(())
    }

    pub fn snapshot_timers(&self) -> Vec<u8> {
        let mut out = Vec::new();
        for index in 0..4 {
            put_u32(&mut out, self.timer_counter[index] as u32);
            put_u32(&mut out, self.timer_reload[index] as u32);
            put_u32(&mut out, self.timer_control[index] as u32);
            put_u64(&mut out, self.timer_pending[index] as u64);
            put_u32(&mut out, self.timer_prescaler[index]);
            out.push(u8::from(self.timer_cascade[index]));
            out.push(u8::from(self.timer_irq[index]));
            out.push(u8::from(self.timer_running[index]));
        }
        out
    }

    pub fn restore_timers(&mut self, data: &[u8]) -> Result<(), String> {
        let mut reader = SnapshotReader::new(data);
        for index in 0..4 {
            self.timer_counter[index] = reader.u32().ok_or("TMR snapshot 被截斷")? as u16;
            self.timer_reload[index] = reader.u32().ok_or("TMR snapshot 被截斷")? as u16;
            self.timer_control[index] = reader.u32().ok_or("TMR snapshot 被截斷")? as u16;
            self.timer_pending[index] = reader.u64().ok_or("TMR snapshot 被截斷")? as u32;
            self.timer_prescaler[index] = reader.u32().ok_or("TMR snapshot 被截斷")?;
            self.timer_cascade[index] = reader.u8().ok_or("TMR snapshot 被截斷")? != 0;
            self.timer_irq[index] = reader.u8().ok_or("TMR snapshot 被截斷")? != 0;
            self.timer_running[index] = reader.u8().ok_or("TMR snapshot 被截斷")? != 0;
        }
        if !reader.finish() {
            return Err("TMR snapshot 長度不符".to_string());
        }
        Ok(())
    }

    /// 載入真實 BIOS 內容（最多 16 KiB），只影響 BIOS 視窗讀值。
    pub fn load_bios(&mut self, data: &[u8]) {
        let length = data.len().min(self.bios.len());
        self.bios[..length].copy_from_slice(&data[..length]);
        self.bios[length..].fill(0);
    }

    /// 未實作／未使用但硬體讀回 0 的 I/O（mGBA 明確列出；suite「I/O read tests」）。
    fn io_offset_reads_zero(offset: u32) -> bool {
        matches!(
            offset,
            0x066
                | 0x06A
                | 0x06E
                | 0x076
                | 0x07A
                | 0x07E
                | 0x086
                | 0x08A
                | 0x0B8
                | 0x0C4
                | 0x0D0
                | 0x0DC
                | 0x136
                | 0x142
                | 0x15A
                | 0x154 // JOY_TRANS：只寫，硬體讀回 0
                | 0x156
                | 0x206
                | 0x20A
                | 0x302
        )
    }

    /// 只寫暫存器：讀取回 open bus（mGBA 用 `GBALoadBad`）。
    fn io_offset_write_only(offset: u32) -> bool {
        matches!(
            offset,
            0x010..=0x01E
                | 0x020..=0x03E
                | 0x040..=0x046
                | 0x04C
                | 0x054
                | 0x0A0..=0x0A6
                | 0x0B0..=0x0B6
                | 0x0BC..=0x0C2
                | 0x0C8..=0x0CE
                | 0x0D4..=0x0DA
        )
    }

    /// 有實作、可讀的 I/O 暫存器（16-bit 對齊位址）。
    fn io_offset_readable(offset: u32) -> bool {
        matches!(
            offset,
            0x000 | 0x004 | 0x006 | 0x008..=0x00E | 0x048 | 0x04A | 0x050 | 0x052
        ) || (0x060..=0x08A).contains(&offset)
            || (0x090..=0x09E).contains(&offset)
            || matches!(offset, 0x0BA | 0x0C6 | 0x0D2 | 0x0DE)
            || (0x100..=0x10F).contains(&offset)
            || (0x120..=0x12B).contains(&offset)
            || matches!(
                offset,
                0x130
                    | 0x132
                    | 0x134
                    | 0x140
                    | 0x150
                    | 0x152
                    | 0x158
                    | 0x200
                    | 0x202
                    | 0x204
                    | 0x208
                    | 0x300
                    | 0x301
            )
    }

    /// SIO／JOY 16-bit 暫存器（對齊位址；0x130 KEYINPUT、0x132 KEYCNT 唔計）。
    fn is_sio_register(offset: u32) -> bool {
        matches!(
            offset,
            0x120 | 0x122 | 0x124 | 0x126 | 0x128 | 0x12A | 0x134 | 0x140 | 0x150..=0x156 | 0x15A
        )
    }

    /// SIO 模式：`(RCNT bits15-14 | SIOCNT bits13-12)`，mGBA `_switchMode`
    /// 將 0–7 收斂成 0–3，8–15 收斂成 GPIO(8)／JOYBUS(12)。
    fn sio_mode(&self) -> u16 {
        let bits = ((self.sio_rcnt & 0xC000) | (self.sio_siocnt & 0x3000)) >> 12;
        if bits < 8 {
            bits & 0x3
        } else {
            bits & 0xC
        }
    }

    /// SIO／JOY 16-bit 讀值（suite「SIO register R/W tests」）。
    fn read_sio16(&self, offset: u32) -> u16 {
        let mode = self.sio_mode();
        match offset {
            // SIODATA32 只在 NORMAL_32 可讀；其餘模式寫入忽略、讀回 0。
            0x120 => {
                if mode == 1 {
                    self.sio_data32[0]
                } else {
                    0
                }
            }
            0x122 => {
                if mode == 1 {
                    self.sio_data32[1]
                } else {
                    0
                }
            }
            // SIOMULTI2/3：未連線時接收緩衝為 0（寫入忽略）。
            0x124 | 0x126 => 0,
            0x128 => self.sio_siocnt,
            // SIOMLT_SEND（multi）／SIODATA8；UART 模式讀回 0。
            0x12A => {
                if mode == 3 {
                    0
                } else {
                    self.sio_data8
                }
            }
            0x134 => {
                // 未連線時 SC/SD/SI/SO 線路狀態：multi／UART／GPIO 全部
                // 拉高，normal 模式只有 SC/SI，JOYBUS 只有 SI/SO。
                let lines = match mode {
                    0 | 1 => 0x0005,
                    12 => 0x000C,
                    _ => 0x000F,
                };
                (self.sio_rcnt & 0xC1F0) | lines
            }
            0x140 => self.sio_joycnt,
            0x150 => self.sio_joy_recv[0],
            0x152 => self.sio_joy_recv[1],
            _ => 0,
        }
    }

    /// SIO／JOY 16-bit 寫入（對照 mGBA `GBASIOWriteSIOCNT`／`GBASIOWriteRCNT`）。
    fn write_sio16(&mut self, offset: u32, value: u16) {
        match offset {
            0x120 => {
                if self.sio_mode() == 1 {
                    self.sio_data32[0] = value;
                }
            }
            0x122 => {
                if self.sio_mode() == 1 {
                    self.sio_data32[1] = value;
                }
            }
            0x124 | 0x126 => {} // 接收緩衝：寫入忽略
            0x128 => { let mut value = value & 0x7FFF;
                let old = self.sio_siocnt;
                let mode_changed = (value ^ old) & 0x3000 != 0;
                if mode_changed {
                    self.sio_siocnt = value & 0x3000;
                    // mGBA 在模式切換時只保留 mode bits，之後才計 mode。
                }
                let base = if mode_changed { value & 0x3000 } else { old };
                match self.sio_mode() {
                    2 => {
                        // MULTI：保留 baud/SC，slave=1（無連線）、id=0、
                        // ready=1；舊值 bits2-7 依 mGBA 保留。
                        value &= 0xFF83;
                        value |= 0x0004;
                        value &= !0x0030;
                        value |= base & 0x00FC;
                        value |= 0x0008;
                    }
                    3 => value &= 0x7FAF, // UART
                    _ => value &= 0x7F8F, // NORMAL_8/32、GPIO、JOYBUS
                }
                self.sio_siocnt = value;
                let started = value & 0x0080 != 0 && old & 0x0080 == 0;
                if started && matches!(self.sio_mode(), 0 | 1) {
                    self.sio_countdown = self.sio_transfer_cycles();
                }
            }
            0x12A => {
                if self.sio_mode() != 3 {
                    self.sio_data8 = value;
                }
            }
            0x134 => {
                let value = value & 0xC1FF;
                let old = self.sio_rcnt;
                self.sio_rcnt = (old & 0x01FF) | (value & 0xC000);
                let mode = self.sio_mode();
                if mode == 2 {
                    // MULTI：id=0 → SI（bit2）拉低。
                    self.sio_rcnt &= !0x0004;
                }
                if mode == 8 {
                    // GPIO：bits0-8 全部由寫入值提供。
                    self.sio_rcnt = (self.sio_rcnt & 0xC000) | (value & 0x01FF);
                } else {
                    // 其他模式：bits4-8 可寫，bits0-3 係線路狀態。
                    self.sio_rcnt = (self.sio_rcnt & 0xC00F) | (value & 0x01F0);
                }
            }
            0x140 => {
                // JOYCNT：bit6 可寫；bits0-2 只能清除（write 1 to clear）。
                let old = self.sio_joycnt;
                self.sio_joycnt =
                    (value & 0x0040) | (old & !(value & 0x0007) & !0x0040);
            }
            0x150 | 0x152 => {} // JOY_RECV：接收緩衝，寫入忽略
            0x154 => self.sio_joy_trans[0] = value,
            0x156 => self.sio_joy_trans[1] = value,
            0x15A => {
                self.sio_joystat = (value & 0x0030) | (self.sio_joystat & !0x0030);
            }
            _ => {}
        }
    }

    /// Normal 模式 SIO 傳輸時間（mGBA `GBASIOTransferCycles`）：
    /// 8／32 bits × 16.78 MHz ÷（256 KiB 或 2 MiB 內部 clock）。
    /// 另外加固定開銷：suite「SIO timing tests」量到硬體比純 bit 時間多
    /// 118 cycles（4 個 normal case 都係同一個差），加埋 IRQ pipeline 嘅
    /// 3 cycles 量測差異後同 0x279／0xB9／0x879／0x179 完全吻合。
    fn sio_transfer_cycles(&self) -> u32 {
        const OVERHEAD: u32 = 118;
        let divisor = if self.sio_siocnt & 0x0002 != 0 {
            2048
        } else {
            256
        } * 1024;
        let bits = if self.sio_mode() == 1 { 32 } else { 8 };
        bits * 16_777_216 / divisor + OVERHEAD
    }

    fn sio_complete(&mut self) {
        let mode = self.sio_mode();
        self.sio_siocnt &= !0x0080;
        // 無連線：SI 線路被拉高，接收資料全 1。
        match mode {
            0 => self.sio_data8 = 0xFFFF,
            1 => self.sio_data32 = [0xFFFF; 2],
            _ => {}
        }
        if self.sio_siocnt & 0x4000 != 0 {
            self.if_ |= 1 << 7; // IRQ_SERIAL
        self.irq_seen |= 1 << 7;
        }
    }

    /// 這次 I/O 讀取是否回 open bus。CPU load 要據此改用 prefetch word；
    /// bus 層（DMA 等）就用 `open_bus` 做近似。
    pub fn io_read_open_bus(address: u32) -> bool {
        if !(IO_START..=IO_REGION_END).contains(&address) {
            return false;
        }
        let offset = address - IO_START;
        if offset >= IO_SIZE as u32 {
            return true;
        }
        let register = offset & !1;
        !Self::io_offset_reads_zero(register) && !Self::io_offset_readable(register)
    }

    fn io_open_bus_byte(&self, address: u32) -> u8 {
        (self.open_bus >> ((address & 3) * 8)) as u8
    }

    pub fn read8(&mut self, address: u32) -> u8 {
        if address <= BIOS_END {
            if self.in_bios {
                return self.bios[address as usize];
            }
            // 非 BIOS 程式讀 BIOS：硬體只回最後 prefetch 的 word
            // （mGBA `biosPrefetch`；suite「BIOS load」）。
            return (self.bios_prefetch >> ((address & 3) * 8)) as u8;
        }
        if (EWRAM_START..=EWRAM_END).contains(&address) {
            return self.ewram[((address - EWRAM_START) as usize) % EWRAM_SIZE];
        }
        if (IWRAM_START..=IWRAM_END).contains(&address) {
            return self.iwram[((address - IWRAM_START) as usize) % IWRAM_SIZE];
        }
        if (IO_START..=IO_REGION_END).contains(&address) {
            let raw_offset = address - IO_START;
            if raw_offset >= IO_SIZE as u32 {
                // 0x04000400 以上：冇任何 I/O 暫存器 → open bus。
                return self.io_open_bus_byte(address);
            }
            let offset = raw_offset as usize;
            let register = raw_offset & !1;
            if Self::io_offset_reads_zero(register) {
                return 0;
            }
            // DMA0–3：SAD／DAD（遮罩後）同 CNT_H 都讀得返，CNT_L 只寫
            // （喺上面 `io_offset_reads_zero` 已經回 0，同 suite「I/O read」一致）。
            if (0xB0..=0xDF).contains(&offset) {
                let aligned = offset as u32 & !1;
                return (self.read_dma16(aligned) >> ((offset & 1) * 8)) as u8;
            }
            if Self::io_offset_write_only(register) || !Self::io_offset_readable(register) {
                return self.io_open_bus_byte(address);
            }
            if (0x100..=0x10F).contains(&offset) {
                let aligned = offset as u32 & !1;
                return (self.read_timer16(aligned) >> ((offset & 1) * 8)) as u8;
            }
            if Self::is_sio_register(offset as u32 & !1) {
                let aligned = offset as u32 & !1;
                return (self.read_sio16(aligned) >> ((offset & 1) * 8)) as u8;
            }
            if offset == 0x4 {
                return self.ppu.dispstat() as u8;
            }
            if offset == 0x5 {
                return (self.ppu.dispstat() >> 8) as u8;
            }
            if offset == 0x6 {
                return self.ppu.vcount() as u8;
            }
            if offset == 0x7 {
                return (self.ppu.vcount() >> 8) as u8;
            }
            if offset == 0x130 {
                return self.keyinput as u8;
            }
            if offset == 0x131 {
                return (self.keyinput >> 8) as u8;
            }
            if offset == 0x200 {
                return self.ie as u8;
            }
            if offset == 0x201 {
                return (self.ie >> 8) as u8;
            }
            if offset == 0x202 {
                return self.if_ as u8;
            }
            if offset == 0x203 {
                return (self.if_ >> 8) as u8;
            }
            if offset == 0x208 {
                return u8::from(self.ime);
            }
            if offset == 0x209 {
                return 0;
            }
            return self.io[offset];
        }
        if (PALETTE_START..=PALETTE_END).contains(&address) {
            return self.palette[((address - PALETTE_START) as usize) % PALETTE_SIZE];
        }
        if (VRAM_START..=VRAM_END).contains(&address) {
            return self.vram[Self::vram_index(address)];
        }
        if (OAM_START..=OAM_END).contains(&address) {
            return self.oam[((address - OAM_START) as usize) % OAM_SIZE];
        }
        if self.save_kind.is_eeprom() && Self::eeprom_covers(address) {
            return self.eeprom_read_bit();
        }
        if (ROM_START..=ROM_END).contains(&address) {
            let offset = (address - ROM_START) as usize % ROM_WINDOW_SIZE;
            if offset < self.rom.len() {
                return self.rom[offset];
            }
            // 超出卡匣大小的 ROM 讀取：硬體回傳位址衍生的固定樣式
            // （mGBA: Out of bounds ROM Load；suite「ROM out-of-bounds load」）。
            return (((address >> 1) >> ((address & 1) * 8)) & 0xFF) as u8;
        }
        if (SRAM_START..=SRAM_END).contains(&address) {
            return self.read_save8(Self::save_offset(address));
        }
        (self.open_bus >> ((address & 3) * 8)) as u8
    }

    pub fn read16(&mut self, address: u32) -> u16 {
        if self.save_kind.is_eeprom() && Self::eeprom_covers(address) {
            return self.eeprom_read_bit() as u16;
        }
        if (SRAM_START..=SRAM_END).contains(&address) {
            let byte = self.read8(address) as u16;
            return byte | (byte << 8);
        }
        let lo = self.read8(address);
        let hi = self.read8(address.wrapping_add(1));
        u16::from_le_bytes([lo, hi])
    }

    pub fn read32(&mut self, address: u32) -> u32 {
        let value = self.read32_raw(address);
        // 資料匯流排保留最後一次 32-bit 讀出的值，供 open bus 讀取使用
        // （GBATEK: Unmapped Memory；suite「ROM out-of-bounds load」）。
        self.open_bus = value;
        value
    }

    fn read32_raw(&mut self, address: u32) -> u32 {
        if self.save_kind.is_eeprom() && Self::eeprom_covers(address) {
            return self.eeprom_read_bit() as u32;
        }
        if (SRAM_START..=SRAM_END).contains(&address) {
            let byte = self.read8(address) as u32;
            return byte | (byte << 8) | (byte << 16) | (byte << 24);
        }
        let b0 = self.read8(address);
        let b1 = self.read8(address.wrapping_add(1));
        let b2 = self.read8(address.wrapping_add(2));
        let b3 = self.read8(address.wrapping_add(3));
        u32::from_le_bytes([b0, b1, b2, b3])
    }

    pub fn write8(&mut self, address: u32, value: u8) {
        if address <= BIOS_END {
            return; // BIOS read-only
        }
        if (EWRAM_START..=EWRAM_END).contains(&address) {
            self.ewram[((address - EWRAM_START) as usize) % EWRAM_SIZE] = value;
            return;
        }
        if (IWRAM_START..=IWRAM_END).contains(&address) {
            self.iwram[((address - IWRAM_START) as usize) % IWRAM_SIZE] = value;
            return;
        }
        if (IO_START..=IO_END).contains(&address) {
            let offset = (address - IO_START) as usize;
            if (0x100..=0x10F).contains(&offset) {
                let aligned = offset as u32 & !1;
                let shift = (offset & 1) * 8;
                let current = self.read_timer16(aligned) as u32;
                let merged = (current & !(0xFFu32 << shift)) | ((value as u32) << shift);
                self.write_timer16(aligned, merged as u16);
                return;
            }
            if (0x60..=0xAF).contains(&offset) {
                if (0xA0..=0xA3).contains(&offset) {
                    self.push_fifo(0, &[value]);
                    return;
                }
                if (0xA4..=0xA7).contains(&offset) {
                    self.push_fifo(1, &[value]);
                    return;
                }
                let aligned = offset as u32 & !1;
                let shift = (offset & 1) * 8;
                let current = u16::from_le_bytes([
                    self.io[aligned as usize],
                    self.io[aligned as usize + 1],
                ]) as u32;
                let merged = (current & !(0xFFu32 << shift)) | ((value as u32) << shift);
                self.write_sound16(aligned, merged as u16);
                return;
            }
            if (0xB0..=0xDF).contains(&offset) {
                let aligned = offset as u32 & !1;
                let shift = (offset & 1) * 8;
                let current = self.read_dma16(aligned) as u32;
                let merged = (current & !(0xFFu32 << shift)) | ((value as u32) << shift);
                self.write_dma16(aligned, merged as u16);
                return;
            }
            if Self::is_sio_register(offset as u32 & !1) {
                let aligned = offset as u32 & !1;
                let shift = (offset & 1) * 8;
                let current = self.read_sio16(aligned) as u32;
                let merged = (current & !(0xFFu32 << shift)) | ((value as u32) << shift);
                self.write_sio16(aligned, merged as u16);
                return;
            }
            match offset {
                0x0 => {
                    self.io[0x0] = value;
                    self.ppu.write_dispcnt(u16::from_le_bytes([self.io[0], self.io[1]]));
                    self.vram_bitmap_mode = matches!(self.io[0] & 7, 3 | 4 | 5);
                }
                0x1 => {
                    self.io[0x1] = value;
                    self.ppu.write_dispcnt(u16::from_le_bytes([self.io[0], self.io[1]]));
                    self.vram_bitmap_mode = matches!(self.io[0] & 7, 3 | 4 | 5);
                }
                0x4 => {
                    self.io[0x4] = value;
                    self.ppu.write_dispstat(u16::from_le_bytes([self.io[4], self.io[5]]));
                }
                0x5 => {
                    self.io[0x5] = value;
                    self.ppu.write_dispstat(u16::from_le_bytes([self.io[4], self.io[5]]));
                }
                0x6 | 0x7 => {} // VCOUNT read-only
                // 影片暫存器寫入遮罩（mGBA renderer writeVideoRegister；
                // suite「I/O read tests」）。
                0x8 | 0xA | 0xC | 0xE => self.io[offset] = value,
                0x9 | 0xB => self.io[offset] = value & 0xDF, // BG0/1CNT bit13
                0xD | 0xF => self.io[offset] = value, // BG2/3CNT
                0x48..=0x4B => self.io[offset] = value & 0x3F, // WININ／WINOUT
                0x50 => self.io[offset] = value,
                0x51 => self.io[offset] = value & 0x3F, // BLDCNT
                0x52 | 0x53 => self.io[offset] = value & 0x1F, // BLDALPHA
                0x130 | 0x131 => {} // KEYINPUT read-only
                0x200 => self.ie = (self.ie & 0xFF00) | value as u16,
                0x201 => self.ie = (self.ie & 0x00FF) | (((value as u16) << 8) & 0x3F00),
                0x202 => self.if_ &= !(value as u16) & 0x3FFF,
                0x203 => self.if_ &= !((value as u16) << 8) & 0x3FFF,
                0x208 => self.ime = value & 1 != 0,
                0x209 => {} // IME 只有 bit0
                0x301 => {
                    if value & 0x80 != 0 {
                        self.halt_requested = true;
                    }
                    self.io[offset] = value;
                }
                _ => self.io[offset] = value,
            }
            return;
        }
        if (PALETTE_START..=PALETTE_END).contains(&address) {
            let offset = ((address - PALETTE_START) as usize) % PALETTE_SIZE;
            let aligned = offset & !1;
            self.palette[aligned] = value;
            self.palette[aligned + 1] = value;
            self.pal_writes += 1;
            self.pal_last = address;
            return;
        }
        if (VRAM_START..=VRAM_END).contains(&address) {
            self.write_vram8(Self::vram_index(address), value);
            return;
        }
        if (OAM_START..=OAM_END).contains(&address) {
            return; // OAM 8-bit 寫入忽略
        }
        if self.save_kind.is_eeprom() && Self::eeprom_covers(address) {
            self.eeprom_write_bit(value & 1);
            return;
        }
        if (ROM_START..=ROM_END).contains(&address) {
            return; // ROM read-only
        }
        if (SRAM_START..=SRAM_END).contains(&address) {
            self.write_save8(Self::save_offset(address), value);
        }
    }

    pub fn write16(&mut self, address: u32, value: u16) {
        if self.save_kind.is_eeprom() && Self::eeprom_covers(address) {
            self.eeprom_write_bit((value & 1) as u8);
            return;
        }
        let bytes = value.to_le_bytes();
        if address == IO_START + 0x300 {
            self.io[0x300..0x302].copy_from_slice(&bytes);
            return;
        }
        if (IO_START + 0x60..=IO_START + 0xAF).contains(&address) {
            let offset = address - IO_START;
            let data = value.to_le_bytes();
            if offset == 0xA0 {
                self.push_fifo(0, &data);
            } else if offset == 0xA4 {
                self.push_fifo(1, &data);
            } else {
                self.write_sound16(offset, value);
            }
            return;
        }
        if (IO_START + 0x100..=IO_START + 0x10F).contains(&address) {
            self.write_timer16(address - IO_START, value);
            return;
        }
        if (IO_START + 0xB0..=IO_START + 0xDF).contains(&address) {
            self.write_dma16(address - IO_START, value);
            return;
        }
        if (IO_START + 0x120..=IO_START + 0x15A).contains(&address) {
            let offset = address - IO_START;
            let aligned = offset & !1;
            if Self::is_sio_register(aligned) {
                self.write_sio16(aligned, value);
                return;
            }
        }
        if (SRAM_START..=SRAM_END).contains(&address) {
            // 8-bit 匯流排：wide store 只寫原始位址的 1 個 byte，
            // byte 由位址低 bit 揀（mGBA STORE_SRAM；suite SRAM store）。
            let lane = (address & 1) * 8;
            self.write_save8(Self::save_offset(address), (value >> lane) as u8);
            return;
        }
        if (PALETTE_START..=PALETTE_END).contains(&address) {
            let offset = ((address - PALETTE_START) as usize) % PALETTE_SIZE;
            let aligned = offset & !1;
            self.palette[aligned] = bytes[0];
            self.palette[aligned + 1] = bytes[1];
            self.pal_writes += 1;
            self.pal_last = address;
            return;
        }
        if (OAM_START..=OAM_END).contains(&address) {
            let offset = ((address - OAM_START) as usize) % OAM_SIZE;
            let aligned = offset & !1;
            self.oam[aligned] = bytes[0];
            self.oam[aligned + 1] = bytes[1];
            return;
        }
        if (VRAM_START..=VRAM_END).contains(&address) {
            let address = address & !1;
            let first = Self::vram_index(address);
            let second = Self::vram_index(address.wrapping_add(1));
            self.vram[first] = bytes[0];
            self.vram[second] = bytes[1];
            return;
        }
        self.write8(address, bytes[0]);
        self.write8(address.wrapping_add(1), bytes[1]);
    }

    pub fn write32(&mut self, address: u32, value: u32) {
        if self.save_kind.is_eeprom() && Self::eeprom_covers(address) {
            self.eeprom_write_bit((value & 1) as u8);
            return;
        }
        let bytes = value.to_le_bytes();
        if (IO_START + 0x80..=IO_START + 0xAF).contains(&address) {
            let offset = address - IO_START;
            if offset == 0xA0 {
                self.push_fifo(0, &bytes);
            } else if offset == 0xA4 {
                self.push_fifo(1, &bytes);
            } else {
                self.write16(address, value as u16);
                self.write16(address.wrapping_add(2), (value >> 16) as u16);
            }
            return;
        }
        if (IO_START + 0x100..=IO_START + 0x10F).contains(&address) {
            self.write_timer32(address - IO_START, value);
            return;
        }
        if (IO_START + 0xB0..=IO_START + 0xDF).contains(&address) {
            self.write_dma32(address - IO_START, value);
            return;
        }
        if (IO_START..=IO_END).contains(&address) {
            // 32-bit I/O store 等同兩個 16-bit 寫入（mGBA `GBAIOWrite32` 的
            // default）；否則 SIOCNT 之類有寫入遮罩的暫存器會被低 byte 的
            // 中間值破壞（suite「SIO timing tests」Normal8/256k）。
            self.write16(address, value as u16);
            self.write16(address.wrapping_add(2), (value >> 16) as u16);
            return;
        }
        if (SRAM_START..=SRAM_END).contains(&address) {
            // 8-bit 匯流排：wide store 只寫原始位址的 1 個 byte，
            // byte 由位址低 2 bit 揀（mGBA STORE_SRAM；suite SRAM store）。
            let lane = (address & 3) * 8;
            self.write_save8(Self::save_offset(address), (value >> lane) as u8);
            return;
        }
        if (PALETTE_START..=PALETTE_END).contains(&address) {
            let offset = ((address - PALETTE_START) as usize) % PALETTE_SIZE;
            let aligned = offset & !3;
            self.palette[aligned..aligned + 4].copy_from_slice(&bytes);
            self.pal_writes += 1;
            self.pal_last = address;
            return;
        }
        if (OAM_START..=OAM_END).contains(&address) {
            let offset = ((address - OAM_START) as usize) % OAM_SIZE;
            let aligned = offset & !3;
            self.oam[aligned..aligned + 4].copy_from_slice(&bytes);
            return;
        }
        if (VRAM_START..=VRAM_END).contains(&address) {
            let address = address & !3;
            for (offset, byte) in bytes.iter().enumerate() {
                let index = Self::vram_index(address.wrapping_add(offset as u32));
                self.vram[index] = *byte;
            }
            return;
        }
        let address = if (EWRAM_START..=IWRAM_END).contains(&address) {
            address & !3
        } else {
            address
        };
        for (offset, byte) in bytes.iter().enumerate() {
            self.write8(address.wrapping_add(offset as u32), *byte);
        }
    }

    /// CPU fetch 用的快速路徑。指令 prefetch 不更新 open bus：硬體 open bus
    /// 保留的是最後一次「資料」讀取的值（suite「ROM out-of-bounds load」）。
    pub fn fetch32(&mut self, address: u32) -> u32 {
        self.read32_raw(address)
    }

    /// 讀取一個 region 的 raw bytes（debug／differential 用）。
    pub fn region(&self, name: Region) -> &[u8] {
        match name {
            Region::Bios => &self.bios,
            Region::Ewram => &self.ewram,
            Region::Iwram => &self.iwram,
            Region::Io => &self.io,
            Region::Palette => &self.palette,
            Region::Vram => &self.vram,
            Region::Oam => &self.oam,
            Region::Rom => &self.rom,
            Region::Sram => &self.sram,
        }
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Region {
    Bios,
    Ewram,
    Iwram,
    Io,
    Palette,
    Vram,
    Oam,
    Rom,
    Sram,
}

#[cfg(test)]
mod tests {
    use super::*;

    fn rom() -> Vec<u8> {
        let mut rom = vec![0u8; 0x100];
        rom[0xB2] = 0x96;
        rom
    }

    fn bus() -> Bus {
        Bus::new(rom()).unwrap()
    }

    #[test]
    fn ewram_roundtrip_and_mirror() {
        let mut bus = bus();
        bus.write32(0x0200_0000, 0x1234_5678);
        assert_eq!(bus.read32(0x0200_0000), 0x1234_5678);
        assert_eq!(bus.read32(0x0204_0000), 0x1234_5678); // 256 KiB mirror
    }

    #[test]
    fn iwram_roundtrip_and_mirror() {
        let mut bus = bus();
        bus.write16(0x0300_7FFE, 0xBEEF);
        assert_eq!(bus.read16(0x0300_7FFE), 0xBEEF);
        assert_eq!(bus.read16(0x0300_FFFE), 0xBEEF); // 32 KiB mirror
    }

    #[test]
    fn io_palette_vram_oam_are_separate() {
        let mut bus = bus();
        bus.write8(0x0400_0000, 0x11);
        bus.write16(0x0500_0000, 0x2233);
        bus.write32(0x0600_0000, 0x4455_6677);
        bus.write16(0x0700_0000, 0x8899);
        assert_eq!(bus.read8(0x0400_0000), 0x11);
        assert_eq!(bus.read16(0x0500_0000), 0x2233);
        assert_eq!(bus.read32(0x0600_0000), 0x4455_6677);
        assert_eq!(bus.read16(0x0700_0000), 0x8899);
    }

    #[test]
    fn rom_is_read_only_and_mirrors() {
        let mut bus = bus();
        let original = bus.read32(0x0800_0000);
        bus.write32(0x0800_0000, 0xFFFF_FFFF);
        assert_eq!(bus.read32(0x0800_0000), original);
        assert_eq!(
            bus.read8(0x0800_0000 + 0xC0),
            bus.read8(0x0800_0000)
        ); // 0x100-byte ROM mirrors
    }

    #[test]
    fn sram_is_8bit_and_initialized_to_ff() {
        let mut bus = bus();
        assert_eq!(bus.read8(0x0E00_0000), 0xFF);
        bus.write8(0x0E00_0000, 0x5A);
        assert_eq!(bus.read8(0x0E00_0000), 0x5A);
    }

    #[test]
    fn sound_pcm_buffer() {
        let mut bus = Bus::new(rom()).unwrap();
        // PSG ch1：50% duty、volume 15、freq 0x700，trigger；左右都開。
        bus.write16(0x0400_0062, 0xF080);
        bus.write16(0x0400_0064, 0x8700);
        bus.write16(0x0400_0080, 0x1177); // 左右 master 7/8 + ch1 左右 enable
        bus.write16(0x0400_0082, 0x0002); // PSG volume 100%
        bus.write16(0x0400_0084, 0x0080); // master enable
        bus.tick(4096);
        let pcm = bus.take_pcm();
        assert!(pcm.len() >= 8, "預期有 PCM 輸出，實際 {} bytes", pcm.len());
        assert!(
            pcm.chunks(2).any(|sample| sample != [0, 0]),
            "PSG 應該產生非靜音 sample"
        );
        assert!(bus.take_pcm().is_empty());
    }

    #[test]
    fn psg_square_pitch_matches_hardware_formula() {
        let mut bus = Bus::new(rom()).unwrap();
        bus.write16(0x0400_0062, 0xF080); // volume 15、duty 50%
        bus.write16(0x0400_0064, 0x8000 | 0x700); // freq 0x700（512 Hz）＋trigger
        bus.write16(0x0400_0080, 0x1177);
        bus.write16(0x0400_0082, 0x0002);
        bus.write16(0x0400_0084, 0x0080);
        bus.tick(1_677_721); // 0.1 s
        let pcm = bus.take_pcm();
        let left: Vec<i16> = pcm
            .chunks(4)
            .map(|c| i16::from_le_bytes([c[0], c[1]]))
            .collect();
        let rises = left
            .windows(2)
            .filter(|w| w[0] <= 0 && w[1] > 0)
            .count();
        // 512 Hz × 0.1 s ≈ 51 個週期。
        assert!((49..=53).contains(&rises), "rises={rises}");
    }

    #[test]
    fn direct_sound_advances_on_timer_overflow() {
        let mut bus = Bus::new(rom()).unwrap();
        bus.write16(0x0400_0082, 0x0304); // A 左右 enable、100%、timer0
        bus.write16(0x0400_0084, 0x0080);
        bus.write32(0x0400_00A0, 0x8080_8080); // 四個 -128
        bus.write16(0x0400_0100, 0xFFFE);
        bus.write16(0x0400_0102, 0x0080); // timer0 enable、prescaler 1
        bus.tick(4096);
        assert!(bus.sound_fifo_a.len() < 4, "timer 溢位應消耗 FIFO");
        let pcm = bus.take_pcm();
        assert!(pcm.chunks(2).any(|sample| sample != [0, 0]));
    }

    #[test]
    fn sound_fifo_dma_special_timing() {
        let mut bus = Bus::new(rom()).unwrap();
        for index in 0..4u32 {
            bus.write32(0x0200_0000 + index * 4, 0x1111_0000 + index);
        }
        bus.write32(0x0400_00BC, 0x0200_0000); // DMA1 SAD
        bus.write32(0x0400_00C0, 0x0400_00A0); // FIFO A
        bus.write16(0x0400_00C4, 4);
        bus.write16(0x0400_00C6, 0xB600); // enable + 32-bit + special timing
        bus.write16(0x0400_0082, 0x0804); // FIFO A enable + 100%
        bus.write32(0x0400_00A0, 0x9999_9999);
        assert!(bus.dma_pending.contains(&1));
        bus.service_dma();
        assert_eq!(bus.sound_fifo_a.len(), 20);
        assert_eq!(bus.dma_source[1], 0x0200_0010);
        assert_eq!(&bus.sound_fifo_a[4..8], &0x1111_0000u32.to_le_bytes());
    }

    #[test]
    fn keypad_irq_or_and_conditions() {
        let mut bus = Bus::new(rom()).unwrap();
        bus.keyinput = 0x03FE; // A pressed
        bus.write16(0x0400_0132, 0x4001); // IRQ enable, OR, A
        bus.poll_keypad();
        assert_eq!(bus.if_ & 0x1000, 0x1000);

        bus.if_ = 0;
        bus.keyinput = 0x03FE; // 只有 A
        bus.write16(0x0400_0132, 0xC003); // AND, A+B
        bus.poll_keypad();
        assert_eq!(bus.if_ & 0x1000, 0);

        bus.keyinput = 0x03FC; // A+B
        bus.poll_keypad();
        assert_eq!(bus.if_ & 0x1000, 0x1000);
    }

    #[test]
    fn timer_prescaler_overflow_and_cascade() {
        let mut bus = Bus::new(rom()).unwrap();
        bus.write16(0x0400_0100, 0xFFFE);
        bus.write16(0x0400_0102, 0x00C0); // IRQ + start, /1
        bus.write16(0x0400_0104, 0);
        bus.write16(0x0400_0106, 0x0084); // start + cascade
        bus.tick(2);
        assert_eq!(bus.read16(0x0400_0100), 0xFFFE);
        assert_eq!(bus.read16(0x0400_0104), 1);
        assert_eq!(bus.read16(0x0400_0202) & 0x0008, 0x0008);

        bus.write16(0x0400_0102, 0x0000); // stop
        bus.write16(0x0400_0100, 0);
        bus.write16(0x0400_0102, 0x0081); // restart /64
        bus.tick(128);
        assert_eq!(bus.read16(0x0400_0100), 2);
    }

    #[test]
    fn dma_immediate_copy_and_cycles() {
        let mut bus = Bus::new(rom()).unwrap();
        for index in 0..4u32 {
            bus.write16(0x0200_0000 + index * 2, 0x1000 + index as u16);
        }
        bus.write32(0x0400_00B0, 0x0200_0000);
        bus.write32(0x0400_00B4, 0x0200_0100);
        bus.write16(0x0400_00B8, 4);
        bus.write16(0x0400_00BA, 0x8000);
        assert_eq!(bus.service_dma(), 10);
        for index in 0..4u32 {
            assert_eq!(bus.read16(0x0200_0100 + index * 2), 0x1000 + index as u16);
        }
        assert_eq!(bus.read16(0x0400_00BA) & 0x8000, 0);
        assert!(!bus.dma_active[0]);
    }

    #[test]
    fn dma_consecutive_transfers_reload_source() {
        let mut rom = rom();
        rom[0..4].copy_from_slice(&0xFEED_FACEu32.to_le_bytes());
        let mut bus = Bus::new(rom).unwrap();
        bus.write32(0x0200_0000, 0xFEED_FACE);
        bus.write32(0x0400_00B0, 0x0200_0000);
        bus.write32(0x0400_00B4, 0x0200_0100);
        bus.write32(0x0400_00B8, 0x8400_0001);
        bus.service_dma();
        assert_eq!(bus.read32(0x0200_0100), 0xFEED_FACE);

        // Game Pak ROM 只有 DMA3 能讀。
        bus.write32(0x0400_00D4, 0x0800_0000);
        bus.write32(0x0400_00D8, 0x0200_0200);
        bus.write32(0x0400_00DC, 0x8400_0001);
        bus.service_dma();
        assert_eq!(bus.read32(0x0200_0200), 0xFEED_FACE);
    }

    #[test]
    fn dma0_reads_rom_from_latch_but_dma1_reads_data() {
        let mut rom = rom();
        rom[0..4].copy_from_slice(&0xDEAD_BEEFu32.to_le_bytes());
        let mut bus = Bus::new(rom).unwrap();
        // 先用 DMA0 從 EWRAM 搬 32-bit 值，建立該通道的 latch。
        bus.write32(0x0200_0000, 0xFEED_FACE);
        bus.write32(0x0400_00B0, 0x0200_0000);
        bus.write32(0x0400_00B4, 0x0200_0200);
        bus.write32(0x0400_00B8, 0x8400_0001);
        bus.service_dma();

        // DMA0 讀 ROM 被阻擋 → 沿用 latch，而非 ROM 內容。
        bus.write32(0x0400_00B0, 0x0800_0000);
        bus.write32(0x0400_00B4, 0x0200_0100);
        bus.write32(0x0400_00B8, 0x8400_0001);
        bus.service_dma();
        assert_eq!(bus.read32(0x0200_0100), 0xFEED_FACE);

        // DMA1 可以正常讀 ROM（suite「ROM load」的 DMA1 期待 ROM 內容）。
        bus.write32(0x0400_00BC, 0x0800_0000);
        bus.write32(0x0400_00C0, 0x0200_0300);
        bus.write32(0x0400_00C4, 0x8400_0001);
        bus.service_dma();
        assert_eq!(bus.read32(0x0200_0300), 0xDEAD_BEEF);
    }

    #[test]
    fn dma0_reads_zero_from_sram() {
        let mut bus = Bus::new(rom()).unwrap();
        // DMA0 讀 SRAM → 0（mGBA 的 performingDMA == 1 行為）。
        bus.write32(0x0400_00B0, 0x0E00_0000);
        bus.write32(0x0400_00B4, 0x0200_0000);
        bus.write32(0x0400_00B8, 0x8400_0001);
        bus.service_dma();
        assert_eq!(bus.read32(0x0200_0000), 0);

        // DMA1 讀 SRAM → 真正的內容（未插卡時 0xFF 複製）。
        bus.write32(0x0400_00BC, 0x0E00_0000);
        bus.write32(0x0400_00C0, 0x0200_0100);
        bus.write32(0x0400_00C4, 0x8400_0001);
        bus.service_dma();
        assert_eq!(bus.read32(0x0200_0100), 0xFFFF_FFFF);
    }

    #[test]
    fn dma_cannot_access_sram() {
        let mut bus = Bus::new(rom()).unwrap();
        bus.write32(0x0200_0000, 0x1122_3344);
        bus.write32(0x0400_00B0, 0x0200_0000);
        bus.write32(0x0400_00B4, 0x0E00_0000);
        bus.write32(0x0400_00B8, 0x8400_0001);
        bus.service_dma();
        assert_eq!(bus.read8(0x0E00_0000), 0xFF); // 未寫入（未插卡時讀回 0xFF）
    }

    #[test]
    fn dma_unaligned_source_aligns_down() {
        let mut bus = Bus::new(rom()).unwrap();
        bus.write32(0x0200_0000, 0xFEED_FACE);
        bus.write32(0x0400_00B0, 0x0200_0001);
        bus.write32(0x0400_00B4, 0x0200_0100);
        bus.write32(0x0400_00B8, 0x8400_0001);
        bus.service_dma();
        assert_eq!(bus.read32(0x0200_0100), 0xFEED_FACE);

        bus.write32(0x0400_00B0, 0x0200_0001);
        bus.write32(0x0400_00B4, 0x0200_0200);
        bus.write32(0x0400_00B8, 0x8000_0001); // 16-bit
        bus.service_dma();
        assert_eq!(bus.read16(0x0200_0200), 0xFACE);
    }

    #[test]
    fn dma_rom_source_ignores_fixed_and_decrement_control() {
        // mGBA `GBADMAWriteCNT_HI`：source 喺 ROM 區時強制 sourceOffset = width，
        // 所以「fixed」／「decrement」控制都會變成遞增（suite「=ROM」/「-ROM」）。
        let mut rom = rom();
        for (i, word) in [0xDEAD_BEEFu32, 0xDEAD_BEF0, 0xDEAD_BEF1, 0xDEAD_BEF2]
            .into_iter()
            .enumerate()
        {
            rom[12 + i * 4..16 + i * 4].copy_from_slice(&word.to_le_bytes());
        }

        // 16-bit、src fixed：讀 0x0800000C 遞增 → BEEF, DEAD, BEF0, DEAD。
        let mut bus = Bus::new(rom.clone()).unwrap();
        bus.write32(0x0400_00BC, 0x0800_000C); // DMA1 SAD
        bus.write32(0x0400_00C0, 0x0200_0000); // DAD
        bus.write32(0x0400_00C4, 0x8140_0004); // src/dest fixed, 16-bit, count 4
        bus.service_dma();
        assert_eq!(bus.read16(0x0200_0000), 0xDEAD);

        // 32-bit、src decrement：ROM 區同樣強制遞增 → 最後一個 word 0xDEADBEF2。
        let mut bus = Bus::new(rom).unwrap();
        bus.write32(0x0400_00BC, 0x0800_000C);
        bus.write32(0x0400_00C0, 0x0200_0000);
        bus.write32(0x0400_00C4, 0x85C0_0004); // src decrement, dest fixed, 32-bit
        bus.service_dma();
        assert_eq!(bus.read32(0x0200_0000), 0xDEAD_BEF2);
    }

    #[test]
    fn sio_register_read_masks_follow_mode() {
        // suite「SIO register R/W tests」：寫 0xFFFF 之後的讀回遮罩。
        // MULTI：SIOCNT 0x6F8F、RCNT 0x01FF。
        let mut bus = Bus::new(rom()).unwrap();
        bus.write16(0x0400_0128, 0x2000);
        bus.write16(0x0400_0128, 0xEFFF);
        assert_eq!(bus.read16(0x0400_0128), 0x6F8F);
        bus.write16(0x0400_0134, 0x3FFF);
        assert_eq!(bus.read16(0x0400_0134), 0x01FF);

        // NORMAL_8：0x4F8F／0x01F5。
        let mut bus = Bus::new(rom()).unwrap();
        bus.write16(0x0400_0128, 0xCFFF);
        assert_eq!(bus.read16(0x0400_0128), 0x4F8F);
        bus.write16(0x0400_0134, 0x3FFF);
        assert_eq!(bus.read16(0x0400_0134), 0x01F5);

        // Normal8 傳輸時間：256k = 8×64 + 118 overhead = 630，2M = 8×8 + 118 = 182。
        let mut bus = Bus::new(rom()).unwrap();
        bus.write16(0x0400_0128, 0x4001);
        bus.write16(0x0400_0128, 0x4081);
        assert_eq!(bus.sio_countdown, 630);
        let mut bus = Bus::new(rom()).unwrap();
        bus.write16(0x0400_0128, 0x4003);
        bus.write16(0x0400_0128, 0x4083);
        assert_eq!(bus.sio_countdown, 182);

        // NORMAL_32：SIODATA32 可讀，SIOCNT 0x5F8F。
        let mut bus = Bus::new(rom()).unwrap();
        bus.write16(0x0400_0128, 0x1000);
        bus.write16(0x0400_0120, 0xFFFF);
        assert_eq!(bus.read16(0x0400_0120), 0xFFFF);
        bus.write16(0x0400_0128, 0xDFFF);
        assert_eq!(bus.read16(0x0400_0128), 0x5F8F);

        // UART：SIOCNT 0x7FAF，SIODATA8 寫入忽略。
        let mut bus = Bus::new(rom()).unwrap();
        bus.write16(0x0400_0128, 0x3000);
        bus.write16(0x0400_0128, 0xFFFF);
        assert_eq!(bus.read16(0x0400_0128), 0x7FAF);
        bus.write16(0x0400_012A, 0xFFFF);
        assert_eq!(bus.read16(0x0400_012A), 0);

        // GPIO：RCNT 0x81FF；JOYBUS：RCNT 0xC1FC。
        let mut bus = Bus::new(rom()).unwrap();
        bus.write16(0x0400_0134, 0x8000);
        bus.write16(0x0400_0134, 0xBFFF);
        assert_eq!(bus.read16(0x0400_0134), 0x81FF);
        let mut bus = Bus::new(rom()).unwrap();
        bus.write16(0x0400_0134, 0xC000);
        bus.write16(0x0400_0134, 0xFFFF);
        assert_eq!(bus.read16(0x0400_0134), 0xC1FC);

        // JOYCNT 只保留 bit6；JOY_TRANS／JOY_RECV／JOYSTAT 讀回 0。
        let mut bus = Bus::new(rom()).unwrap();
        bus.write16(0x0400_0140, 0xFFFF);
        assert_eq!(bus.read16(0x0400_0140), 0x0040);
        bus.write16(0x0400_0154, 0xFFFF);
        assert_eq!(bus.read16(0x0400_0154), 0);
        bus.write16(0x0400_0150, 0xFFFF);
        assert_eq!(bus.read16(0x0400_0150), 0);
        bus.write16(0x0400_015A, 0xFFFF);
        assert_eq!(bus.read16(0x0400_015A), 0);
    }

    #[test]
    fn mgba_prefetch_stall_and_data_cost() {
        let mut bus = Bus::new(rom()).unwrap();
        bus.functional = false;
        let pc = 0x0800_0004;
        // prefetch off：stall 唔會改變 wait；IO 32-bit 存取 = wait(0)+2。
        assert_eq!(bus.mgba_stall(pc, 7), 7);
        assert_eq!(bus.mgba_data_cost(pc, 0x0400_0100, 4), 2);
        // ROM L/S 的 pipeline refill 差額（N-S）。
        assert_eq!(bus.mgba_refill_delta(pc, 4), 2);
        // prefetch on：buffer 吸收 IO wait，mGBA 會扣多過 wait（可以負數）。
        bus.set_waitcnt(0x4000);
        bus.prefetch_last_pc = 0;
        assert_eq!(bus.mgba_stall(pc, 7), -2);
        bus.prefetch_last_pc = 0;
        assert_eq!(bus.mgba_data_cost(pc, 0x0400_0100, 4), -2);
    }

    #[test]
    fn timer_start_loads_reload_and_overflows_to_new_reload() {
        let mut bus = Bus::new(rom()).unwrap();
        // 32-bit 寫：CNT_L=0xFFFF（reload）、CNT_H=0x00C0（enable＋IRQ）。
        bus.write32(0x0400_0100, 0xC0_FFFF);
        assert_eq!(bus.timer_counter[0], 0xFFFF);
        // 執行中寫 CNT_L 只改 reload，counter 不變（suite「Timer IRQ」前提）。
        bus.write16(0x0400_0100, 0x0000);
        assert_eq!(bus.timer_counter[0], 0xFFFF);
        bus.tick(3);
        assert_eq!(bus.timer_counter[0], 0x0000);
        assert_eq!(bus.if_ & 0x0008, 0x0008); // IRQ_TIMER0
        assert_eq!(bus.read16(0x0400_0100), 0x0000);
    }

    #[test]
    fn io_read_masks_and_open_bus_classification() {
        // suite「I/O read tests」：寫 0xFFFF 之後讀回硬體遮罩值。
        let mut bus = Bus::new(rom()).unwrap();
        for (address, expected) in [
            (0x0400_0008u32, 0xDFFFu16), // BG0CNT
            (0x0400_000A, 0xDFFF),       // BG1CNT
            (0x0400_000C, 0xFFFF),       // BG2CNT
            (0x0400_0048, 0x3F3F),       // WININ
            (0x0400_004A, 0x3F3F),       // WINOUT
            (0x0400_0050, 0x3FFF),       // BLDCNT
            (0x0400_0052, 0x1F1F),       // BLDALPHA
            (0x0400_0060, 0x007F),       // SOUND1CNT_LO
            (0x0400_0062, 0xFFC0),       // SOUND1CNT_HI
            (0x0400_0064, 0x4000),       // SOUND1CNT_X
            (0x0400_0070, 0x00E0),       // SOUND3CNT_LO
            (0x0400_0080, 0xFF77),       // SOUNDCNT_LO
            (0x0400_0082, 0x770F),       // SOUNDCNT_HI
            (0x0400_0090, 0xFFFF),       // WAVE_RAM
            (0x0400_00BA, 0xF7E0),       // DMA0CNT_HI
            (0x0400_00DE, 0xFFE0),       // DMA3CNT_HI
            (0x0400_00B8, 0),            // DMA0CNT_LO 讀回 0
        ] {
            bus.write16(address, 0xFFFF);
            assert_eq!(bus.read16(address), expected, "offset {:#05X}", address - 0x0400_0000);
        }

        // 只寫／未實作：CPU load 要當 open bus（mGBA GBALoadBad）。
        for address in [
            0x0400_0010u32, // BG0HOFS（只寫）
            0x0400_0020,    // BG2PA
            0x0400_0040,    // WIN0H
            0x0400_00A0,    // FIFO_A
            0x0400_00B0,    // DMA0SAD
            0x0400_004E,    // invalid
            0x0400_100C,   // IO 範圍外
        ] {
            assert!(Bus::io_read_open_bus(address), "{address:#010X}");
        }
        for address in [
            0x0400_0008u32, // BG0CNT
            0x0400_0066,    // unused 但讀 0
            0x0400_0130,    // KEYINPUT
            0x0400_0200,    // IE
        ] {
            assert!(!Bus::io_read_open_bus(address), "{address:#010X}");
        }
    }

    #[test]
    fn sram_width_and_alignment_rules() {
        let mut bus = Bus::new(rom()).unwrap();
        bus.write8(0x0E00_0000, 0x66);
        bus.write8(0x0E00_0001, 0xBB);
        bus.write8(0x0E00_0002, 0x55);
        bus.write8(0x0E00_0003, 0xAA);
        // 8-bit 匯流排：wide load 讀原始位址的 byte 再複製（mGBA LOAD_SRAM）。
        assert_eq!(bus.read16(0x0E00_0000), 0x6666);
        assert_eq!(bus.read16(0x0E00_0001), 0xBBBB);
        assert_eq!(bus.read32(0x0E00_0002), 0x5555_5555);
        assert_eq!(bus.read32(0x0E00_0003), 0xAAAA_AAAA);

        // wide store 只寫原始位址的 1 個 byte，byte 由位址低 bit 揀。
        bus.write16(0x0E00_0000, 0xD8C7);
        assert_eq!(bus.read8(0x0E00_0000), 0xC7);
        assert_eq!(bus.read8(0x0E00_0001), 0xBB);
        bus.write16(0x0E00_0001, 0x1234);
        assert_eq!(bus.read8(0x0E00_0001), 0x12);
        bus.write32(0x0E00_0002, 0xA5B6_C7D8);
        assert_eq!(bus.read8(0x0E00_0002), 0xB6);
        bus.write32(0x0E00_0003, 0xA5B6_C7D8);
        assert_eq!(bus.read8(0x0E00_0003), 0xA5);
        assert_eq!(
            [0u32, 1, 2, 3].map(|offset| bus.read8(0x0E00_0000 + offset)),
            [0xC7, 0x12, 0xB6, 0xA5]
        );
    }

    #[test]
    fn vram_unaligned_stores_align() {
        let mut bus = Bus::new(rom()).unwrap();
        bus.write16(0x0600_0001, 0xC7D8);
        assert_eq!(bus.read16(0x0600_0000), 0xC7D8);
        bus.write32(0x0600_0001, 0xA5B6_C7D8);
        assert_eq!(bus.read32(0x0600_0000), 0xA5B6_C7D8);
    }

    #[test]
    fn palette_and_oam_store_rules() {
        let mut bus = Bus::new(rom()).unwrap();
        bus.write8(0x0500_0000, 0xD8);
        assert_eq!(bus.read16(0x0500_0000), 0xD8D8);
        bus.write16(0x0500_0001, 0xC7D8);
        assert_eq!(bus.read16(0x0500_0000), 0xC7D8);
        bus.write32(0x0500_0001, 0xA5B6_C7D8);
        assert_eq!(bus.read32(0x0500_0000), 0xA5B6_C7D8);

        bus.write8(0x0700_0000, 0xFF);
        assert_eq!(bus.read8(0x0700_0000), 0);
        bus.write16(0x0700_0000, 0x1234);
        assert_eq!(bus.read16(0x0700_0000), 0x1234);
    }

    #[test]
    fn io_interrupt_and_keyinput_semantics() {
        let mut bus = Bus::new(rom()).unwrap();
        assert_eq!(bus.read16(0x0400_0130), 0x03FF);
        bus.write16(0x0400_0130, 0);
        assert_eq!(bus.read16(0x0400_0130), 0x03FF);

        bus.write16(0x0400_0200, 0xFFFF);
        assert_eq!(bus.read16(0x0400_0200), 0x3FFF);

        bus.if_ = 0x0005;
        bus.write16(0x0400_0202, 0x0003);
        assert_eq!(bus.read16(0x0400_0202), 0x0004);
        bus.write8(0x0400_0202, 0x04);
        assert_eq!(bus.read16(0x0400_0202), 0);

        bus.write16(0x0400_0208, 0xFFFF);
        assert_eq!(bus.read16(0x0400_0208), 1);
    }

    #[test]
    fn vcount_is_read_only() {
        let mut bus = Bus::new(rom()).unwrap();
        bus.write16(0x0400_0006, 0x1234);
        assert_eq!(bus.read16(0x0400_0006), 0);
    }

    #[test]
    fn vram_8bit_write_rules() {
        let mut bus = Bus::new(rom()).unwrap();
        bus.write8(0x0600_0000, 0xAB);
        assert_eq!(bus.read8(0x0600_0000), 0xAB);
        assert_eq!(bus.read8(0x0600_0001), 0xAB);
        assert_eq!(bus.read16(0x0600_0000), 0xABAB);

        bus.write8(0x0601_0000, 0xCD);
        assert_eq!(bus.read8(0x0601_0000), 0);
        assert_eq!(bus.read8(0x0601_0001), 0);

        bus.set_vram_bitmap_mode(true);
        bus.write8(0x0601_0000, 0x5A);
        assert_eq!(bus.read8(0x0601_0001), 0x5A);
    }

    #[test]
    fn vram_tail_mirrors_obj_region() {
        let mut bus = Bus::new(rom()).unwrap();
        bus.write32(0x0601_0000, 0x1122_3344);
        assert_eq!(bus.read16(0x0601_8000), 0x3344);
        assert_eq!(bus.read16(0x0601_8002), 0x1122);
    }

    #[test]
    fn unmapped_reads_return_open_bus() {
        let mut bus = bus();
        bus.open_bus = 0x1122_3344;
        assert_eq!(bus.read8(0x0100_0000), 0x44);
        assert_eq!(bus.read8(0x0100_0001), 0x33);
        assert_eq!(bus.read16(0x0100_0000), 0x3344);
        assert_eq!(bus.read32(0x0100_0000), 0x1122_3344);
    }

    #[test]
    fn data_read_updates_open_bus_but_fetch_does_not() {
        let mut bus = bus();
        bus.rom[0..4].copy_from_slice(&0xDEAD_BEEFu32.to_le_bytes());
        bus.open_bus = 0x1122_3344;
        assert_eq!(bus.fetch32(0x0800_0000), 0xDEAD_BEEF);
        assert_eq!(bus.open_bus, 0x1122_3344); // 指令 prefetch 不更新
        assert_eq!(bus.read32(0x0800_0000), 0xDEAD_BEEF);
        assert_eq!(bus.open_bus, 0xDEAD_BEEF); // 資料讀取才更新
        assert_eq!(bus.read8(0x0100_0000), 0xEF); // 未映射讀回 open bus lane
    }

    #[test]
    fn rom_out_of_bounds_returns_address_pattern() {
        let mut bus = bus(); // ROM 只有 0x100 bytes
        assert_eq!(bus.read8(0x0800_0100), 0x80);
        assert_eq!(bus.read16(0x0800_0100), 0x0080);
        assert_eq!(bus.read32(0x0800_0100), 0x0081_0080);
        // 三個 Game Pak 視窗的位址樣式一致。
        assert_eq!(bus.read32(0x0A00_0100), 0x0081_0080);
    }


    #[test]
    fn waitcnt_access_costs() {
        let mut bus = bus();
        bus.functional = false;
        // WAITCNT=0: WS0 first=5, second=3; 32-bit nonseq = 5+3.
        assert_eq!(bus.access_cost(0x0800_0000, 4, false), 8);
        assert_eq!(bus.access_cost(0x0800_0002, 2, true), 3);
        assert_eq!(bus.access_cost(0x0200_0000, 4, false), 6);
        assert_eq!(bus.access_cost(0x0200_0000, 2, false), 3);
        assert_eq!(bus.access_cost(0x0300_0000, 4, false), 1);
        assert_eq!(bus.access_cost(0x0500_0000, 4, false), 2);
        assert_eq!(bus.access_cost(0x0600_0000, 2, false), 1);
        assert_eq!(bus.access_cost(0x0E00_0000, 1, false), 5);
        // WS0: first=4, second=2
        bus.set_waitcnt(0x0014);
        assert_eq!(bus.access_cost(0x0800_0000, 4, false), 6);
        assert_eq!(bus.access_cost(0x0800_0002, 1, true), 2);
    }


    #[test]
    fn video_wait_matches_ppu_state() {
        let mut bus = bus();
        bus.ppu_scanline = 100;
        bus.ppu_in_hblank = false;
        assert_eq!(bus.video_wait(0x0600_0000, 4), 1);
        assert_eq!(bus.video_wait(0x0500_0000, 2), 1);
        assert_eq!(bus.video_wait(0x0700_0000, 2), 1);
        assert_eq!(bus.video_wait(0x0300_0000, 4), 0);
        bus.ppu_in_hblank = true;
        assert_eq!(bus.video_wait(0x0600_0000, 4), 0);
        assert_eq!(bus.video_wait(0x0700_0000, 2), 1);
        bus.io[0x00] |= 0x20;
        assert_eq!(bus.video_wait(0x0700_0000, 2), 0);
        bus.ppu_scanline = 160;
        assert_eq!(bus.video_wait(0x0600_0000, 4), 0);
        bus.ppu_scanline = 100;
        bus.io[0x00] |= 0x80;
        assert_eq!(bus.video_wait(0x0600_0000, 4), 0);
    }


    #[test]
    fn ppu_io_and_tick() {
        let mut bus = bus();
        bus.write16(0x0400_0004, 0x0008); // VBlank IRQ enable
        bus.tick((160 * 1_232) as u32);
        assert_eq!(bus.read16(0x0400_0006), 160);
        assert_eq!(bus.read16(0x0400_0004) & 0x1, 0x1);
        assert_eq!(bus.if_ & 0x1, 0x1);
        bus.tick(1_232);
        assert_eq!(bus.read16(0x0400_0006), 161);
    }

    #[test]
    fn vblank_event_triggers_dma1() {
        let mut bus = bus();
        bus.write16(0x0200_0000, 0x1234);
        bus.write32(0x0400_00BC, 0x0200_0000);
        bus.write32(0x0400_00C0, 0x0200_0100);
        bus.write16(0x0400_00C4, 1);
        bus.write16(0x0400_00C6, 0x9000); // enable + VBlank timing
        bus.write16(0x0400_0004, 0x0008);
        bus.tick((160 * 1_232) as u32);
        assert_eq!(bus.if_ & 0x1, 0x1);
        assert!(bus.dma_pending.contains(&1));
        bus.service_dma();
        assert_eq!(bus.read16(0x0200_0100), 0x1234);
    }

    #[test]
    fn hblank_event_triggers_dma2() {
        let mut bus = bus();
        bus.write16(0x0200_0000, 0x5678);
        bus.write32(0x0400_00C8, 0x0200_0000);
        bus.write32(0x0400_00CC, 0x0200_0100);
        bus.write16(0x0400_00D0, 1);
        bus.write16(0x0400_00D2, 0xA000); // enable + HBlank timing
        bus.tick(1_006);
        assert!(bus.dma_pending.contains(&2));
        bus.service_dma();
        assert_eq!(bus.read16(0x0200_0100), 0x5678);
    }

    #[test]
    fn rejects_short_rom() {
        assert_eq!(
            Bus::new(vec![0; 0x10]),
            Err(BusError::RomTooSmall { size: 0x10 })
        );
    }
}
