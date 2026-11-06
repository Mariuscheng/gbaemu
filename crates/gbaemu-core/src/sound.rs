//! GBA 音訊：PSG 四聲道（square×2／wave／noise）＋ DMA Sound A/B 混音。
//!
//! 時基：輸出 32.768 kHz（每個 sample 512 CPU cycles）；PSG 內部 262.144 kHz
//! （每個 sample 8 個 PSG tick）；frame sequencer 512 Hz（每 512 個 PSG tick
//! 一步，除頻後 length 256 Hz、sweep 128 Hz、envelope 64 Hz）。
//!
//! 混音單位跟 GBATEK「Max Output Levels」：每個 PSG 聲道 ±0x80、每個 FIFO
//! ±0x200；相加後再換成 s16（×20）。實際輸出會被 clamp。
//!
//! # GBATEK: GBA Sound Controller - SOUND1-4、SOUNDCNT_L/H/X、WAVE_RAM

/// 每個 PSG tick 對應的 CPU cycles：16777216 / 262144 = 64。
const CYCLES_PER_PSG_TICK: u32 = 64;
/// 每個輸出 sample 的 PSG tick 數：262144 / 32768 = 8。
const PSG_TICKS_PER_SAMPLE: u32 = 8;
/// Frame sequencer 除頻：262144 / 512 = 512 ticks。
const SEQ_TICKS: u32 = 512;

#[derive(Debug, Clone, Copy, Default, PartialEq, Eq)]
pub struct Square {
    pub enabled: bool,
    pub timer: i32,
    pub pos: u32,
    pub volume: u8,
    pub env_timer: u32,
    pub length: u32,
    /// SOUNDxCNT_X bit0-10（write-only，唔會留在 io）。
    pub freq: u16,
}

#[derive(Debug, Clone, Copy, Default, PartialEq, Eq)]
pub struct Wave {
    pub enabled: bool,
    pub timer: i64,
    pub pos: u32,
    pub length: u32,
    pub sample: u8,
    pub freq: u16,
}

#[derive(Debug, Clone, Copy, Default, PartialEq, Eq)]
pub struct Noise {
    pub enabled: bool,
    pub timer: i32,
    pub lfsr: u16,
    pub volume: u8,
    pub env_timer: u32,
    pub length: u32,
    pub out: bool,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Sound {
    pub sample_rate: u32,
    /// 未滿一個 sample 的 cycle 累加器。
    pub cycles: u32,
    /// frame sequencer：目前 tick（0..SEQ_TICKS）與 step（0..8）。
    pub seq_tick: u32,
    pub seq_step: u32,
    pub ch1: Square,
    pub ch2: Square,
    pub ch3: Wave,
    pub ch4: Noise,
    /// 目前 DMA Sound A／B 的取樣值（已展開到 ±0x200 之前，signed 8-bit）。
    pub ds_a: i32,
    pub ds_b: i32,
    /// 診斷用：FIFO 成功 pop 次數／空 FIFO 次數（timer overflow 時）。
    pub fifo_pops: u64,
    pub fifo_empty: u64,
    /// 診斷用：逐 sample 記錄 (sample_index, ds_a, ds_b, left)。
    pub debug: bool,
    pub debug_log: Vec<(u64, i32, i32, i16)>,
    /// 已輸出的 sample 總數（診斷用 index）。
    pub samples: u64,
    /// 診斷用：每次 FIFO pop 記錄 (sample_index, byte, 是否 B)。
    pub pop_log: Vec<(u64, u8, bool)>,
}

fn s8(value: u8) -> i32 {
    if value & 0x80 != 0 {
        value as i32 - 0x100
    } else {
        value as i32
    }
}

impl Default for Sound {
    fn default() -> Self {
        Self::new(32768)
    }
}

impl Sound {
    pub fn new(sample_rate: u32) -> Self {
        Self {
            sample_rate: sample_rate.max(1),
            cycles: 0,
            seq_tick: 0,
            seq_step: 0,
            ch1: Square::default(),
            ch2: Square::default(),
            ch3: Wave::default(),
            ch4: Noise::default(),
            ds_a: 0,
            ds_b: 0,
            fifo_pops: 0,
            fifo_empty: 0,
            debug: false,
            debug_log: Vec::new(),
            samples: 0,
            pop_log: Vec::new(),
        }
    }

    pub fn reset(&mut self) {
        let rate = self.sample_rate;
        *self = Sound::new(rate);
    }

    fn reg16(io: &[u8], offset: usize) -> u16 {
        u16::from_le_bytes([io[offset], io[offset + 1]])
    }

    /// SOUNDCNT_X bit7（PSG/FIFO master enable）。
    fn master(io: &[u8]) -> bool {
        Self::reg16(io, 0x84) & 0x80 != 0
    }

    /// 寫入 SOUND 暫存器後的狀態更新（由 `Bus::write_sound16` 呼叫）。
    pub fn write_reg(&mut self, io: &[u8], offset: u32, value: u16) {
        if offset == 0x84 {
            if value & 0x80 == 0 {
                // Master off：GBATEK 說 PSG 暫存器全部歸零，且聲道停止。
                self.reset_channels();
            }
            return;
        }
        let triggered = value & 0x8000 != 0;
        match offset {
            0x64 if triggered => {
                let cnt_h = Self::reg16(io, 0x62);
                self.ch1.enabled = cnt_h >> 12 != 0;
                self.ch1.volume = (cnt_h >> 12) as u8;
                self.ch1.env_timer = 0;
                self.ch1.pos = 0;
                self.ch1.length = 64 - (cnt_h & 0x3F) as u32;
                // frequency／trigger 是 write-only，值要留在 channel state。
                self.ch1.freq = value & 0x7FF;
                self.ch1.timer = 0;
            }
            0x6C if triggered => {
                let cnt_l = Self::reg16(io, 0x68);
                self.ch2.enabled = cnt_l >> 12 != 0;
                self.ch2.volume = (cnt_l >> 12) as u8;
                self.ch2.env_timer = 0;
                self.ch2.pos = 0;
                self.ch2.length = 64 - (cnt_l & 0x3F) as u32;
                self.ch2.freq = value & 0x7FF;
                self.ch2.timer = 0;
            }
            0x74 if triggered => {
                let cnt_l = Self::reg16(io, 0x70);
                let cnt_h = Self::reg16(io, 0x72);
                self.ch3.enabled = cnt_l & 0x80 != 0;
                self.ch3.pos = 0;
                self.ch3.timer = 0;
                self.ch3.length = 256 - (cnt_h & 0xFF) as u32;
                self.ch3.sample = 0;
                self.ch3.freq = value & 0x7FF;
            }
            0x7C if triggered => {
                let cnt_l = Self::reg16(io, 0x78);
                let cnt_h = Self::reg16(io, 0x7C);
                self.ch4.enabled = cnt_l >> 12 != 0;
                self.ch4.volume = (cnt_l >> 12) as u8;
                self.ch4.env_timer = 0;
                self.ch4.length = 64 - (cnt_l & 0x3F) as u32;
                self.ch4.lfsr = if cnt_h & 0x08 != 0 { 0x40 } else { 0x4000 };
                self.ch4.timer = 0;
                self.ch4.out = false;
            }
            _ => {}
        }
    }

    fn reset_channels(&mut self) {
        self.ch1 = Square::default();
        self.ch2 = Square::default();
        self.ch3 = Wave::default();
        self.ch4 = Noise::default();
        self.seq_tick = 0;
        self.seq_step = 0;
        self.ds_a = 0;
        self.ds_b = 0;
    }

    fn square_period(freq: u16) -> i32 {
        // duty step = (2048-n)/4 個 PSG tick；用 1/4 tick 累加器避免浮點。
        (2048 - (freq & 0x7FF) as i32).max(1)
    }

    fn wave_period(freq: u16) -> i64 {
        // 每個 wave digit = (2048-n)/8 個 PSG tick；累加器每次 +8。
        (2048 - (freq & 0x7FF) as i64).max(1)
    }

    fn noise_threshold(cnt_h: u16) -> i32 {
        // 半 tick 累加器：r>0 時 period = r*2^s tick；r=0 時 2^(s-1) tick。
        let r = (cnt_h & 0x7) as i32;
        let s = ((cnt_h >> 4) & 0xF) as i32;
        let threshold = if r != 0 { r << (s + 1) } else { 1 << s };
        threshold.max(1)
    }

    /// 推進 `cycles` 個 CPU cycle，必要時輸出 sample 到 `pcm`。
    pub fn tick(&mut self, io: &[u8], cycles: u32, pcm: &mut Vec<u8>) {
        if cycles == 0 {
            return;
        }
        self.cycles = self.cycles.wrapping_add(cycles);
        while self.cycles >= CYCLES_PER_PSG_TICK * PSG_TICKS_PER_SAMPLE {
            self.cycles -= CYCLES_PER_PSG_TICK * PSG_TICKS_PER_SAMPLE;
            for _ in 0..PSG_TICKS_PER_SAMPLE {
                self.step_psg(io);
            }
            let (left, right) = self.mix(io);
            if self.debug && self.debug_log.len() < 4_000_000 {
                self.debug_log.push((self.samples, self.ds_a, self.ds_b, left));
            }
            self.samples += 1;
            pcm.extend_from_slice(&left.to_le_bytes());
            pcm.extend_from_slice(&right.to_le_bytes());
        }
    }

    /// 一個 PSG tick（262.144 kHz）。
    fn step_psg(&mut self, io: &[u8]) {
        if !Self::master(io) {
            return;
        }
        self.seq_tick += 1;
        if self.seq_tick >= SEQ_TICKS {
            self.seq_tick = 0;
            let step = self.seq_step;
            self.seq_step = (self.seq_step + 1) & 7;
            self.frame_sequencer(io, step);
        }

        // ---- Channel 1／2：square ----
        let cnt1_h = Self::reg16(io, 0x62);
        let cnt2_l = Self::reg16(io, 0x68);
        Self::step_square(&mut self.ch1, cnt1_h);
        Self::step_square(&mut self.ch2, cnt2_l);

        // ---- Channel 3：wave ----
        if self.ch3.enabled {
            let period = Self::wave_period(self.ch3.freq);
            self.ch3.timer += 8;
            while self.ch3.timer >= period {
                self.ch3.timer -= period;
                self.ch3.pos = (self.ch3.pos + 1) & 63;
                let index = 0x90 + (self.ch3.pos as usize / 2);
                let byte = io[index];
                self.ch3.sample = if self.ch3.pos & 1 == 0 {
                    byte >> 4
                } else {
                    byte & 0x0F
                };
            }
        }

        // ---- Channel 4：noise ----
        if self.ch4.enabled {
            let cnt_h = Self::reg16(io, 0x7C);
            let threshold = Self::noise_threshold(cnt_h);
            self.ch4.timer += 2;
            while self.ch4.timer >= threshold {
                self.ch4.timer -= threshold;
                let short = cnt_h & 0x08 != 0;
                let bit = self.ch4.lfsr & 1;
                self.ch4.lfsr >>= 1;
                if bit != 0 {
                    self.ch4.lfsr ^= if short { 0x60 } else { 0x6000 };
                    self.ch4.out = true;
                } else {
                    self.ch4.out = false;
                }
            }
        }
    }

    fn step_square(ch: &mut Square, cnt_h: u16) {
        if !ch.enabled {
            return;
        }
        if cnt_h >> 12 == 0 && ch.volume == 0 {
            ch.enabled = false;
            return;
        }
        ch.timer += 4;
        let period = Self::square_period(ch.freq);
        while ch.timer >= period {
            ch.timer -= period;
            ch.pos = (ch.pos + 1) & 7;
        }
    }

    fn frame_sequencer(&mut self, io: &[u8], step: u32) {
        // Length：256 Hz（每 2 個 step）。ch1/ch2 的 length enable 在 CNT_X
        // bit14（同 bit12-15 音量共用 register，唔可以讀 CNT_H）。
        if step & 1 == 0 {
            let cnt1_x = Self::reg16(io, 0x64);
            let cnt2_x = Self::reg16(io, 0x6C);
            let cnt3_x = Self::reg16(io, 0x74);
            let cnt4_h = Self::reg16(io, 0x7C);
            Self::clock_length(&mut self.ch1, cnt1_x & 0x4000 != 0);
            Self::clock_length(&mut self.ch2, cnt2_x & 0x4000 != 0);
            if self.ch3.enabled && cnt3_x & 0x4000 != 0 {
                self.ch3.length = self.ch3.length.saturating_sub(1);
                if self.ch3.length == 0 {
                    self.ch3.enabled = false;
                }
            }
            if self.ch4.enabled && cnt4_h & 0x4000 != 0 {
                self.ch4.length = self.ch4.length.saturating_sub(1);
                if self.ch4.length == 0 {
                    self.ch4.enabled = false;
                }
            }
        }
        // Sweep：128 Hz（step 2、6）。
        if step == 2 || step == 6 {
            let cnt1_l = Self::reg16(io, 0x60);
            let time = (cnt1_l >> 4) & 7;
            let shift = cnt1_l & 7;
            if time != 0 && self.ch1.enabled && shift != 0 {
                let freq = self.ch1.freq as i32;
                let delta = freq >> shift;
                let next = if cnt1_l & 0x08 != 0 {
                    freq - delta
                } else {
                    freq + delta
                };
                if next > 2047 || next < 0 {
                    self.ch1.enabled = false;
                }
            }
        }
        // Envelope：64 Hz（step 7）。
        if step == 7 {
            let cnt1_h = Self::reg16(io, 0x62);
            let cnt2_l = Self::reg16(io, 0x68);
            let cnt4_l = Self::reg16(io, 0x78);
            Self::clock_envelope(&mut self.ch1, cnt1_h);
            Self::clock_envelope(&mut self.ch2, cnt2_l);
            clock_envelope_generic(
                &mut self.ch4.enabled,
                &mut self.ch4.volume,
                &mut self.ch4.env_timer,
                cnt4_l,
            );
        }
    }

    fn clock_length(ch: &mut Square, length_enable: bool) {
        if ch.enabled && length_enable {
            ch.length = ch.length.saturating_sub(1);
            if ch.length == 0 {
                ch.enabled = false;
            }
        }
    }

    fn clock_envelope(ch: &mut Square, cnt_h: u16) {
        clock_envelope_generic(&mut ch.enabled, &mut ch.volume, &mut ch.env_timer, cnt_h);
    }

    fn duty_high(duty: u16, pos: u32) -> bool {
        match duty & 3 {
            0 => pos == 0,
            1 => pos < 2,
            2 => pos < 4,
            _ => pos < 6,
        }
    }

    /// 混音：回傳 (left, right) s16（整數運算，同 Python reference 逐 bit 一致）。
    fn mix(&self, io: &[u8]) -> (i16, i16) {
        let soundcnt_l = Self::reg16(io, 0x80);
        let soundcnt_h = Self::reg16(io, 0x82);
        // PSG 音量比（SOUNDCNT_H bit0-1）：25%／50%／100%／未定義當 100%。
        let (volume_num, volume_den) = match soundcnt_h & 3 {
            0 => (1i32, 4i32),
            1 => (1, 2),
            _ => (1, 1),
        };
        let master_right = (((soundcnt_l >> 0) & 7) + 1) as i32;
        let master_left = (((soundcnt_l >> 4) & 7) + 1) as i32;
        let enable_right = ((soundcnt_l >> 8) & 0xF) as i32;
        let enable_left = ((soundcnt_l >> 12) & 0xF) as i32;

        let master = Self::master(io);
        let mut psg_right = 0i32;
        let mut psg_left = 0i32;
        if master {
            for (index, value) in self.channel_outputs(io).into_iter().enumerate() {
                let bit = 1 << index;
                if enable_right & bit != 0 {
                    psg_right += value;
                }
                if enable_left & bit != 0 {
                    psg_left += value;
                }
            }
        }
        let scale = 8 * volume_den;
        psg_right = psg_right * master_right * volume_num / scale;
        psg_left = psg_left * master_left * volume_num / scale;

        let mut ds_right = 0i32;
        let mut ds_left = 0i32;
        if master {
            let vol_a = if soundcnt_h & 0x4 != 0 { 4 } else { 2 };
            let vol_b = if soundcnt_h & 0x8 != 0 { 4 } else { 2 };
            let a = self.ds_a * vol_a;
            let b = self.ds_b * vol_b;
            if soundcnt_h & 0x0100 != 0 {
                ds_right += a;
            }
            if soundcnt_h & 0x0200 != 0 {
                ds_left += a;
            }
            if soundcnt_h & 0x1000 != 0 {
                ds_right += b;
            }
            if soundcnt_h & 0x2000 != 0 {
                ds_left += b;
            }
        }

        let left = clamp_s16((psg_left + ds_left) * 20);
        let right = clamp_s16((psg_right + ds_right) * 20);
        (left, right)
    }

    /// 四個 PSG 聲道目前的 signed 輸出（±0x80；整數）。
    fn channel_outputs(&self, io: &[u8]) -> [i32; 4] {
        let cnt1_h = Self::reg16(io, 0x62);
        let cnt2_l = Self::reg16(io, 0x68);
        let cnt3_h = Self::reg16(io, 0x72);
        let cnt4_l = Self::reg16(io, 0x78);

        let mut out = [0i32; 4];
        if self.ch1.enabled && cnt1_h >> 12 != 0 {
            let high = Self::duty_high((cnt1_h >> 6) & 3, self.ch1.pos);
            out[0] = psg_level(self.ch1.volume, high);
        }
        if self.ch2.enabled && cnt2_l >> 12 != 0 {
            let high = Self::duty_high((cnt2_l >> 6) & 3, self.ch2.pos);
            out[1] = psg_level(self.ch2.volume, high);
        }
        if self.ch3.enabled {
            let volume_code = (cnt3_h >> 13) & 3;
            let force75 = cnt3_h & 0x8000 != 0;
            // 1.0 → ×16、0.5 → ×8、0.25 → ×4、force 75% → ×12。
            let scale = if force75 {
                12
            } else {
                match volume_code {
                    0 => 0,
                    1 => 16,
                    2 => 8,
                    _ => 4,
                }
            };
            out[2] = (self.ch3.sample as i32 - 8) * scale;
        }
        if self.ch4.enabled && cnt4_l >> 12 != 0 {
            out[3] = psg_level(self.ch4.volume, self.ch4.out);
        }
        out
    }

    /// Timer 溢位時推進 DMA Sound 取樣（SOUNDCNT_H bit10/14 選擇 timer 0/1）。
    pub fn timer_overflow(&mut self, io: &[u8], timer: usize, fifo_a: &mut Vec<u8>, fifo_b: &mut Vec<u8>) {
        if !Self::master(io) {
            return;
        }
        let control = Self::reg16(io, 0x82);
        let mut a = false;
        let mut b = false;
        if timer == 0 {
            a = control & 0x0400 == 0;
            b = control & 0x4000 == 0;
        } else if timer == 1 {
            a = control & 0x0400 != 0;
            b = control & 0x4000 != 0;
        } else {
            return;
        }
        if a {
            if let Some(byte) = fifo_a.first().copied() {
                fifo_a.remove(0);
                self.ds_a = s8(byte);
                self.fifo_pops += 1;
                if self.debug && self.pop_log.len() < 4_000_000 {
                    self.pop_log.push((self.samples, byte, false));
                }
            } else {
                self.fifo_empty += 1;
            }
        }
        if b {
            if let Some(byte) = fifo_b.first().copied() {
                fifo_b.remove(0);
                self.ds_b = s8(byte);
                self.fifo_pops += 1;
                if self.debug && self.pop_log.len() < 4_000_000 {
                    self.pop_log.push((self.samples, byte, true));
                }
            } else {
                self.fifo_empty += 1;
            }
        }
    }
}

fn clock_envelope_generic(enabled: &mut bool, volume: &mut u8, timer: &mut u32, cnt_h: u16) {
    let period = ((cnt_h >> 8) & 0x7) as u32;
    if !*enabled || period == 0 {
        return;
    }
    *timer += 1;
    if *timer < period {
        return;
    }
    *timer = 0;
    let increase = cnt_h & 0x0800 != 0;
    if increase {
        if *volume < 15 {
            *volume += 1;
        }
    } else if *volume > 0 {
        *volume -= 1;
    }
}

fn psg_level(volume: u8, high: bool) -> i32 {
    let dac = if high { volume as i32 } else { 0 };
    // 4-bit DAC → ±0x80：Rust `/` 向零截斷，Python 用 `_trunc_div` 對齊。
    (dac * 2 - 15) * 0x80 / 15
}

fn clamp_s16(value: i32) -> i16 {
    value.clamp(i16::MIN as i32, i16::MAX as i32) as i16
}
