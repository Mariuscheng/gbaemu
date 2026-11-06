//! `gbaemu-core` migration skeleton.
//!
//! **Status: G1–G3 進行中。** CPU／bus／DMA／timer／PPU timing 與基礎 renderer 已
//! 有 Rust 實作與 differential；Python reference 仍是默認且唯一可完整執行的
//! backend。在 `docs/architecture/MIGRATION.md` 的 G1–G8 gates 通過前，不要刪除
//! 任何 Python 模組。
//!
//! 設計原則：
//! - 所有硬體狀態在同一個 `Core`，不從 Rust 回呼 Python。
//! - 整數 cycle；不使用 wall clock 或 float 做 timing。
//! - snapshot 用明確 little-endian 編碼，不直接 dump struct。
//! - 沒有 native extension 時，Python 明確使用 reference backend，不假裝成功。

#![forbid(unsafe_code)]
#![deny(missing_debug_implementations)]

pub const CORE_VERSION: &str = env!("CARGO_PKG_VERSION");
pub const FRAME_CYCLES: u64 = 280_896; // 228 scanlines * 1232
pub const SCANLINE_CYCLES: u64 = 1_232;
pub const SCANLINES: u16 = 228;


pub const SNAPSHOT_HEADER_SIZE: usize = 90;

pub(crate) fn put_u16(out: &mut Vec<u8>, value: u16) {
    out.extend_from_slice(&value.to_le_bytes());
}

pub(crate) fn put_u32(out: &mut Vec<u8>, value: u32) {
    out.extend_from_slice(&value.to_le_bytes());
}

pub(crate) fn put_u64(out: &mut Vec<u8>, value: u64) {
    out.extend_from_slice(&value.to_le_bytes());
}

pub(crate) struct SnapshotReader<'a> {
    data: &'a [u8],
    pos: usize,
}

impl<'a> SnapshotReader<'a> {
    pub(crate) fn new(data: &'a [u8]) -> Self {
        Self { data, pos: 0 }
    }

    pub(crate) fn u8(&mut self) -> Option<u8> {
        let value = *self.data.get(self.pos)?;
        self.pos += 1;
        Some(value)
    }

    pub(crate) fn u16(&mut self) -> Option<u16> {
        let bytes = self.data.get(self.pos..self.pos + 2)?;
        self.pos += 2;
        Some(u16::from_le_bytes([bytes[0], bytes[1]]))
    }

    pub(crate) fn u32(&mut self) -> Option<u32> {
        let bytes = self.data.get(self.pos..self.pos + 4)?;
        self.pos += 4;
        Some(u32::from_le_bytes([bytes[0], bytes[1], bytes[2], bytes[3]]))
    }

    pub(crate) fn u64(&mut self) -> Option<u64> {
        let bytes = self.data.get(self.pos..self.pos + 8)?;
        self.pos += 8;
        let mut array = [0u8; 8];
        array.copy_from_slice(bytes);
        Some(u64::from_le_bytes(array))
    }

    pub(crate) fn bytes(&mut self, len: usize) -> Option<&'a [u8]> {
        let value = self.data.get(self.pos..self.pos + len)?;
        self.pos += len;
        Some(value)
    }

    pub(crate) fn finish(&self) -> bool {
        self.pos == self.data.len()
    }
}

pub(crate) fn crc32(data: &[u8]) -> u32 {
    let mut crc = 0xFFFF_FFFFu32;
    for byte in data {
        crc ^= *byte as u32;
        for _ in 0..8 {
            crc = if crc & 1 != 0 {
                (crc >> 1) ^ 0xEDB8_8320
            } else {
                crc >> 1
            };
        }
    }
    !crc
}
pub const VBLANK_START_CYCLE: u64 = 197_120; // scanline 160 * 1232

mod bus;
mod cpu;
mod ppu;
mod sha256;
mod sound;
pub use bus::{Bus, BusError, Region, SaveKind};
pub use cpu::{Cpu, CpuError};
pub use ppu::Ppu;
pub use sha256::sha256;

/// CPU cycle model 選擇；對應 Python `TimingMode`（timed／timed-mgba）。
#[derive(Debug, Clone, Copy, PartialEq, Eq, Default)]
pub enum TimingModel {
    /// 舊模型（每條指令 access_cost 相加；Python `TimingMode.TIMED`）。
    #[default]
    Legacy,
    /// mGBA 式 active-region accounting（Python `TimingMode.TIMED_MGBA`）。
    Mgba,
}

/// 與 `api_types.EmulatorConfig` 對應的 Rust 設定；目前只放入 migration 需要的欄位。
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct CoreConfig {
    /// 正式路徑固定是 HLE；真實 BIOS 不是 production 需求。
    pub hle_bios: bool,
    /// 是否在 frame 邊界產生 RGB888 framebuffer。
    pub render: bool,
    /// 是否啟用音訊 FIFO／PCM 輸出。
    pub sound: bool,
    /// timed 模式下用邊個 CPU cycle model。
    pub timing_model: TimingModel,
    /// `true` = 近似模式：所有記憶體存取都當 1 cycle（Python FUNCTIONAL）。
    /// GUI／production 用 `false`（真 waitstate、prefetch、stall）。
    pub functional: bool,
}

impl Default for CoreConfig {
    fn default() -> Self {
        Self {
            hle_bios: true,
            render: true,
            sound: true,
            timing_model: TimingModel::Mgba,
            functional: false,
        }
    }
}

/// CPU 狀態的 Rust 邊界；snapshot 之後用明確 little-endian 編碼。


/// 一條 scanline 上可能命中的 OBJ（每條線只解析 OAM 一次）。
#[derive(Clone, Copy)]
struct LineSprite {
    x: i32,
    y: i32,
    w: u32,
    h: u32,
    affine: bool,
    double_size: bool,
    pa: i32,
    pb: i32,
    pc: i32,
    pd: i32,
    bpp8: bool,
    tile: u32,
    hflip: bool,
    vflip: bool,
    priority: u16,
    index: u16,
    palette_bank: usize,
    mosaic: u32,
    /// OBJ window（attr0 mode 2）：只參與 window mask，不當普通 sprite 畫。
    window: bool,
}

const SPRITE_SIZES: [[(u32, u32); 4]; 3] = [
    [(8, 8), (16, 16), (32, 32), (64, 64)],
    [(16, 8), (32, 8), (32, 16), (64, 32)],
    [(8, 16), (8, 32), (16, 32), (32, 64)],
];

/// 收集 `y` 這條 scanline 上覆蓋到的 OBJ。
///
/// 舊版 `sprite_pixel()` 每個 pixel 都掃 128 個 OAM entry（Pinball 這類
/// 滿畫面 sprite 的遊戲要 ~20 ms/frame）；改成每條線只掃一次，pixel loop
/// 只見幾個 candidate。
fn collect_line_sprites(bus: &Bus, y: u32, dispcnt: u16) -> Vec<LineSprite> {
    if dispcnt & 0x1000 == 0 {
        return Vec::new();
    }
    let obj_1d = dispcnt & 0x0040 != 0;
    let mut out: Vec<LineSprite> = Vec::with_capacity(16);
    for index in 0..128usize {
        let o = index * 8;
        let attr0 = u16::from_le_bytes([bus.oam[o], bus.oam[o + 1]]);
        let affine = attr0 & 0x0100 != 0;
        if !affine && attr0 & 0x0200 != 0 {
            continue;
        }
        let shape = (attr0 >> 14) & 0x3;
        if shape == 3 {
            continue;
        }
        // OBJ window（mode 2）照樣收集，之後由 `window_mask` 當 window 用。
        let window = (attr0 >> 10) & 3 == 2;
        let attr1 = u16::from_le_bytes([bus.oam[o + 2], bus.oam[o + 3]]);
        let attr2 = u16::from_le_bytes([bus.oam[o + 4], bus.oam[o + 5]]);
        let size = ((attr1 >> 14) & 0x3) as usize;
        let (w, h) = SPRITE_SIZES[shape as usize][size];
        let double_size = affine && attr0 & 0x0200 != 0;
        let mut sx = (attr1 & 0x1FF) as i32;
        if sx >= 256 {
            sx -= 512;
        }
        let mut sy = (attr0 & 0xFF) as i32;
        if sy >= 160 {
            sy -= 256;
        }
        let mosaic = if attr0 & 0x1000 != 0 {
            (((io_u16(bus, 0x4C) >> 4) & 0xF) + 1) as u32
        } else {
            1
        };
        let my = y - y % mosaic;
        let (x0, y0, disp_w, disp_h) = if double_size {
            (sx - (w as i32) / 2, sy - (h as i32) / 2, w * 2, h * 2)
        } else {
            (sx, sy, w, h)
        };
        if (my as i32) < y0 || (my as i32) >= y0 + disp_h as i32 {
            continue;
        }
        if x0 >= 240 || x0 + disp_w as i32 <= 0 {
            continue;
        }
        let (pa, pb, pc, pd) = if affine {
            let group = ((attr1 >> 9) & 0x1F) as usize;
            let param = 0x06 + group * 0x20;
            let read16 = |offset: usize| -> i32 {
                i16::from_le_bytes([bus.oam[offset], bus.oam[offset + 1]]) as i32
            };
            (read16(param), read16(param + 8), read16(param + 16), read16(param + 24))
        } else {
            (0, 0, 0, 0)
        };
        out.push(LineSprite {
            x: sx,
            y: sy,
            w,
            h,
            affine,
            double_size,
            pa,
            pb,
            pc,
            pd,
            bpp8: attr0 & 0x2000 != 0,
            tile: (attr2 & 0x3FF) as u32,
            hflip: attr1 & 0x1000 != 0,
            vflip: attr1 & 0x2000 != 0,
            priority: (attr2 >> 10) & 0x3,
            index: index as u16,
            palette_bank: ((attr2 >> 12) & 0xF) as usize,
            mosaic,
            window,
        });
    }
    let _ = obj_1d;
    out
}

fn sprite_pixel(bus: &Bus, x: u32, y: u32, dispcnt: u16) -> Option<(u16, u16)> {
    let sprites = collect_line_sprites(bus, y, dispcnt);
    sprite_pixel_in(bus, x, y, dispcnt, &sprites)
}

/// 單一 OBJ 在 (x,y) 的顏色；透明 pixel 回 `None`。
///
/// OBJ window sprite 同普通 sprite 用同一個 pixel 解碼，只係前者唔計
/// priority、只當「呢個 pixel 有冇著色」用（mGBA `SPRITE_DRAW_PIXEL_*_OBJWIN`
/// 只在 `tileData != 0` 時設 FLAG_OBJWIN）。
fn sprite_color_at(bus: &Bus, sprite: &LineSprite, obj_1d: bool, x: u32, y: u32) -> Option<u16> {
    let w = sprite.w;
    let h = sprite.h;
    let mosaic = sprite.mosaic;
    let mx = x - x % mosaic;
    let my = y - y % mosaic;
    let (px, py);
    if sprite.affine {
        let disp_w = if sprite.double_size { w * 2 } else { w };
        let disp_h = if sprite.double_size { h * 2 } else { h };
        let sx0 = if sprite.double_size { sprite.x - (w as i32) / 2 } else { sprite.x };
        let sy0 = if sprite.double_size { sprite.y - (h as i32) / 2 } else { sprite.y };
        let cx = sx0 + disp_w as i32 / 2;
        let cy = sy0 + disp_h as i32 / 2;
        let dx = mx as i32 - cx;
        let dy = my as i32 - cy;
        let tex_x = ((sprite.pa * dx + sprite.pb * dy) >> 8) + (w as i32) / 2;
        let tex_y = ((sprite.pc * dx + sprite.pd * dy) >> 8) + (h as i32) / 2;
        if tex_x < 0 || tex_y < 0 || tex_x as u32 >= w || tex_y as u32 >= h {
            return None;
        }
        px = tex_x as u32;
        py = tex_y as u32;
    } else {
        let dx = mx as i32 - sprite.x;
        let dy = my as i32 - sprite.y;
        if dx < 0 || dy < 0 || dx as u32 >= w || dy as u32 >= h {
            return None;
        }
        let mut fx = dx as u32;
        let mut fy = dy as u32;
        if sprite.hflip {
            fx = w - 1 - fx;
        }
        if sprite.vflip {
            fy = h - 1 - fy;
        }
        px = fx;
        py = fy;
    }
    let step = if sprite.bpp8 { 2u32 } else { 1u32 };
    let tile_index = if obj_1d {
        sprite.tile + (py / 8) * (w / 8) * step + (px / 8) * step
    } else {
        sprite.tile + (py / 8) * 32 + (px / 8) * step
    };
    let color_index = if sprite.bpp8 {
        let address = 0x10000 + (tile_index & 0x3FE) * 32 + (py % 8) * 8 + (px % 8);
        bus.vram[address as usize]
    } else {
        let address = 0x10000 + (tile_index & 0x3FF) * 32 + (py % 8) * 4 + (px % 8) / 2;
        let byte = bus.vram[address as usize];
        ((byte >> (((px % 8) & 1) * 4)) & 0x0F) as u8
    };
    if color_index == 0 {
        return None;
    }
    let palette_index = if sprite.bpp8 {
        0x100 + color_index as usize
    } else {
        0x100 + sprite.palette_bank * 16 + color_index as usize
    };
    Some(u16::from_le_bytes([
        bus.palette[palette_index * 2],
        bus.palette[palette_index * 2 + 1],
    ]))
}

fn sprite_pixel_in(
    bus: &Bus,
    x: u32,
    y: u32,
    dispcnt: u16,
    sprites: &[LineSprite],
) -> Option<(u16, u16)> {
    let obj_1d = dispcnt & 0x0040 != 0;
    let mut best_priority = 5u16;
    let mut best_index = 256u16;
    let mut best_color = 0u16;
    for sprite in sprites {
        if sprite.window {
            continue;
        }
        if let Some(color) = sprite_color_at(bus, sprite, obj_1d, x, y) {
            if (sprite.priority, sprite.index) < (best_priority, best_index) {
                best_priority = sprite.priority;
                best_index = sprite.index;
                best_color = color;
            }
        }
    }
    if best_index == 256 {
        None
    } else {
        Some((best_priority, best_color))
    }
}

/// (x, y) 是否在任何 OBJ window sprite 的不透明 pixel 內。
fn obj_window_inside(bus: &Bus, x: u32, y: u32, dispcnt: u16, sprites: &[LineSprite]) -> bool {
    if sprites.is_empty() {
        return false;
    }
    let obj_1d = dispcnt & 0x0040 != 0;
    sprites
        .iter()
        .any(|sprite| sprite_color_at(bus, sprite, obj_1d, x, y).is_some())
}


fn io_u16(bus: &Bus, offset: usize) -> u16 {
    u16::from_le_bytes([bus.io[offset], bus.io[offset + 1]])
}

/// 真機 window 範圍判斷。高位 byte = X1/Y1（左上）、低位 byte = X2/Y2（右下）。
/// GBATEK：「X2>240 或 X1>X2 都當成 X2=240」，Y 軸同理（Y2=160）。
fn window_inside(h: u16, v: u16, x: u32, y: u32) -> bool {
    let mut x1 = ((h >> 8) & 0xFF) as u32;
    let mut x2 = (h & 0xFF) as u32;
    if x2 > 240 {
        x2 = 240;
    }
    if x1 > x2 {
        x2 = 240;
    }
    let mut y1 = ((v >> 8) & 0xFF) as u32;
    let mut y2 = (v & 0xFF) as u32;
    if y2 > 160 {
        y2 = 160;
    }
    if y1 > y2 {
        y2 = 160;
    }
    x1 = x1.min(240);
    y1 = y1.min(160);
    x1 <= x && x < x2 && y1 <= y && y < y2
}

fn window_mask(bus: &Bus, x: u32, y: u32, dispcnt: u16, window_sprites: &[LineSprite]) -> u16 {
    if dispcnt & 0xE000 == 0 {
        return 0x3F;
    }
    let winin = io_u16(bus, 0x48);
    let winout = io_u16(bus, 0x4A);
    // 暫存器順序：0x040 WIN0H、0x042 WIN1H、0x044 WIN0V、0x046 WIN1V。
    // WININ 低 6 bit = WIN0 內可見 layers、bit8-13 = WIN1 內；
    // WINOUT 低 6 bit = 兩個 window 外、bit8-13 = OBJ window 內。
    // 優先順序固定 WIN0 > WIN1 > OBJ window > 窗外（GBATEK Video/Windows；
    // mGBA 以 window priority 0/1/2/3 實作）。
    if dispcnt & 0x2000 != 0 && window_inside(io_u16(bus, 0x40), io_u16(bus, 0x44), x, y) {
        return winin & 0x3F;
    }
    if dispcnt & 0x4000 != 0 && window_inside(io_u16(bus, 0x42), io_u16(bus, 0x46), x, y) {
        return (winin >> 8) & 0x3F;
    }
    if dispcnt & 0x8000 != 0 && obj_window_inside(bus, x, y, dispcnt, window_sprites) {
        return (winout >> 8) & 0x3F;
    }
    winout & 0x3F
}

fn mix_rgb555(bottom: u16, top: u16, eva: u16, evb: u16) -> u16 {
    let br = (bottom & 0x1F) as u32;
    let bg = ((bottom >> 5) & 0x1F) as u32;
    let bb = ((bottom >> 10) & 0x1F) as u32;
    let tr = (top & 0x1F) as u32;
    let tg = ((top >> 5) & 0x1F) as u32;
    let tb = ((top >> 10) & 0x1F) as u32;
    let r = ((tr * eva as u32 + br * evb as u32) >> 4).min(31);
    let g = ((tg * eva as u32 + bg * evb as u32) >> 4).min(31);
    let b = ((tb * eva as u32 + bb * evb as u32) >> 4).min(31);
    (r | (g << 5) | (b << 10)) as u16
}

fn fade_rgb555(value: u16, amount: u16, fade_in: bool) -> u16 {
    let r = (value & 0x1F) as u32;
    let g = ((value >> 5) & 0x1F) as u32;
    let b = ((value >> 10) & 0x1F) as u32;
    let amount = amount as u32;
    let (r, g, b) = if fade_in {
        ((r + amount).min(31), (g + amount).min(31), (b + amount).min(31))
    } else {
        (r.saturating_sub(amount), g.saturating_sub(amount), b.saturating_sub(amount))
    };
    (r | (g << 5) | (b << 10)) as u16
}

fn render_mode0(bus: &Bus, framebuffer: &mut [u8], y0: u32, y1: u32) {
    const TEXT_SIZES: [(u32, u32); 4] = [(32, 32), (64, 32), (32, 64), (64, 64)];
    const AFFINE_SIZES: [u32; 4] = [128, 256, 512, 1024];
    let dispcnt = bus.ppu.dispcnt;
    let mode = dispcnt & 0x7;
    let backdrop = u16::from_le_bytes([bus.palette[0], bus.palette[1]]);
    let blend_control = io_u16(bus, 0x50);
    // GBATEK BLDCNT：bit6-7 是 2-bit 效果模式（0=none、1=alpha、2=變亮、3=變暗）。
    let effect = (blend_control >> 6) & 0x3;
    let second_targets = (blend_control >> 8) & 0x3F;
    let alpha = io_u16(bus, 0x52);
    let eva = (alpha & 0x1F).min(16);
    let evb = ((alpha >> 8) & 0x1F).min(16);
    let fade_amount = io_u16(bus, 0x54) & 0x1F;
    let windows_enabled = dispcnt & 0xE000 != 0;
    for y in y0..y1 {
        let mut line_sprites = collect_line_sprites(bus, y, dispcnt);
        let window_sprites: Vec<LineSprite> = line_sprites.iter().copied().filter(|s| s.window).collect();
        line_sprites.retain(|s| !s.window);
        for x in 0..240u32 {
            let mask = if windows_enabled { window_mask(bus, x, y, dispcnt, &window_sprites) } else { 0x3F };
            let mut best_priority = 5u16;
            let mut best_order = 4u16;
            let mut best_color = backdrop;
            let mut best_sprite = false;
            let mut second_priority = 5u16;
            let mut second_order = 5u16;
            let mut second_color = backdrop;
            let mut second_sprite = false;
            macro_rules! consider {
                ($priority:expr, $order:expr, $color:expr, $sprite:expr) => {{
                    let priority: u16 = $priority;
                    let order: u16 = $order;
                    let color: u16 = $color;
                    let sprite: bool = $sprite;
                    if (priority, order) < (best_priority, best_order) {
                        second_priority = best_priority;
                        second_order = best_order;
                        second_color = best_color;
                        second_sprite = best_sprite;
                        best_priority = priority;
                        best_order = order;
                        best_color = color;
                        best_sprite = sprite;
                    } else if (priority, order) < (second_priority, second_order) {
                        second_priority = priority;
                        second_order = order;
                        second_color = color;
                        second_sprite = sprite;
                    }
                }};
            }
            // GBATEK Video/OBJ "Priority"：OBJ 與 BG 同 priority 時 OBJ 在上層，
            // 所以 OBJ 用 <= 比較（同 priority 直接搶贏 BG0-3）。
            macro_rules! consider_obj {
                ($priority:expr, $color:expr) => {{
                    let priority: u16 = $priority;
                    let color: u16 = $color;
                    if (priority, 0u16) <= (best_priority, best_order) {
                        second_priority = best_priority;
                        second_order = best_order;
                        second_color = best_color;
                        second_sprite = best_sprite;
                        best_priority = priority;
                        best_order = 0;
                        best_color = color;
                        best_sprite = true;
                    } else if (priority, 0u16) < (second_priority, second_order) {
                        second_priority = priority;
                        second_order = 0;
                        second_color = color;
                        second_sprite = true;
                    }
                }};
            }
            for bg in 0..4u16 {
                if dispcnt & (1 << (8 + bg)) == 0 || mask & (1 << bg) == 0 {
                    continue;
                }
                let cnt = io_u16(bus, 0x008 + bg as usize * 2);
                let priority = cnt & 0x3;
                let mosaic = if cnt & 0x40 != 0 { ((io_u16(bus, 0x4C) & 0xF) + 1) as u32 } else { 1 };
                let mx = x - x % mosaic;
                let my = y - y % mosaic;
                let affine = (mode == 1 && bg == 2) || (mode == 2 && bg >= 2);
                if affine {
                    let char_base = ((cnt >> 2) & 0x3) as u32 * 0x4000;
                    let screen_base = ((cnt >> 8) & 0x1F) as u32 * 0x800;
                    let size = AFFINE_SIZES[((cnt >> 14) & 0x3) as usize];
                    let wrap = cnt & 0x2000 != 0;
                    let base = 0x020 + (bg as usize - 2) * 0x10;
                    let read_s16 = |offset: usize| -> i32 {
                        i16::from_le_bytes([bus.io[offset], bus.io[offset + 1]]) as i32
                    };
                    let pa = read_s16(base) as i64;
                    let pb = read_s16(base + 2) as i64;
                    let pc = read_s16(base + 4) as i64;
                    let pd = read_s16(base + 6) as i64;
                    let ref_x = i32::from_le_bytes([
                        bus.io[base + 8], bus.io[base + 9], bus.io[base + 10], bus.io[base + 11],
                    ]) as i64;
                    let ref_y = i32::from_le_bytes([
                        bus.io[base + 12], bus.io[base + 13], bus.io[base + 14], bus.io[base + 15],
                    ]) as i64;
                    let tex_x = (ref_x + mx as i64 * pa + my as i64 * pb) >> 8;
                    let tex_y = (ref_y + mx as i64 * pc + my as i64 * pd) >> 8;
                    let (sx, sy) = if wrap {
                        (tex_x.rem_euclid(size as i64) as u32, tex_y.rem_euclid(size as i64) as u32)
                    } else {
                        if tex_x < 0 || tex_y < 0 || tex_x >= size as i64 || tex_y >= size as i64 {
                            continue;
                        }
                        (tex_x as u32, tex_y as u32)
                    };
                    let map = screen_base as usize + ((sy / 8) * (size / 8) + (sx / 8)) as usize;
                    let tile = bus.vram[map] as usize;
                    let color_index = bus.vram[char_base as usize + tile * 64 + ((sy % 8) * 8 + (sx % 8)) as usize] as usize;
                    if color_index == 0 {
                        continue;
                    }
                    let color = u16::from_le_bytes([bus.palette[color_index * 2], bus.palette[color_index * 2 + 1]]);
                    consider!(priority, bg, color, false);
                    continue;
                }
                let char_base = ((cnt >> 2) & 0x3) as u32 * 0x4000;
                let screen_base = ((cnt >> 8) & 0x1F) as u32 * 0x800;
                let size = ((cnt >> 14) & 0x3) as usize;
                let (tiles_x, tiles_y) = TEXT_SIZES[size];
                let width_px = tiles_x * 8;
                let height_px = tiles_y * 8;
                let hofs = io_u16(bus, 0x010 + bg as usize * 4) as u32;
                let vofs = io_u16(bus, 0x012 + bg as usize * 4) as u32;
                let sx = (mx + hofs) % width_px;
                let sy = (my + vofs) % height_px;
                let tx = sx / 8;
                let ty = sy / 8;
                let blocks = tiles_x / 32;
                let block = (tx / 32) + (ty / 32) * blocks;
                let map_offset = block * 0x800 + ((ty % 32) * 32 + (tx % 32)) * 2;
                let map = screen_base as usize + map_offset as usize;
                let tile = u16::from_le_bytes([bus.vram[map], bus.vram[map + 1]]);
                let mut px = sx % 8;
                let mut py = sy % 8;
                let tile_index = (tile & 0x3FF) as usize;
                let color_index = if cnt & 0x0080 != 0 {
                    if tile & 0x0400 != 0 { px = 7 - px; }
                    if tile & 0x0800 != 0 { py = 7 - py; }
                    let address = char_base as usize + tile_index * 64 + (py * 8 + px) as usize;
                    bus.vram[address]
                } else {
                    if tile & 0x0400 != 0 { px = 7 - px; }
                    if tile & 0x0800 != 0 { py = 7 - py; }
                    let address = char_base as usize + tile_index * 32 + (py * 4 + px / 2) as usize;
                    let byte = bus.vram[address];
                    ((byte >> ((px & 1) * 4)) & 0x0F) as u8
                };
                if color_index == 0 {
                    continue;
                }
                let palette_index = if cnt & 0x0080 != 0 {
                    color_index as usize
                } else {
                    (((tile >> 12) & 0xF) as usize) * 16 + color_index as usize
                };
                let color = u16::from_le_bytes([bus.palette[palette_index * 2], bus.palette[palette_index * 2 + 1]]);
                consider!(priority, bg, color, false);
            }
            if mask & 0x10 != 0 {
                if let Some((sprite_priority, sprite_color)) =
                    sprite_pixel_in(bus, x, y, dispcnt, &line_sprites)
                {
                    consider_obj!(sprite_priority, sprite_color);
                }
            }
            let mut value = if best_priority == 5 { backdrop } else { best_color };
            if mask & 0x20 != 0 && best_priority != 5 {
                let target = if best_sprite { 0x10 } else { 1u16 << best_order };
                if effect == 1 && blend_control & target != 0 {
                    if second_priority != 5 {
                        let second_target = if second_sprite { 0x10 } else { 1u16 << second_order };
                        if second_targets & second_target != 0 {
                            value = mix_rgb555(second_color, value, eva, evb);
                        } else if second_targets & 0x20 != 0 {
                            value = mix_rgb555(backdrop, value, eva, evb);
                        }
                    } else if second_targets & 0x20 != 0 {
                        value = mix_rgb555(backdrop, value, eva, evb);
                    }
                } else if (effect == 2 || effect == 3) && blend_control & target != 0 {
                    value = fade_rgb555(value, fade_amount, effect == 2);
                }
            }
            let r = (value & 0x1F) as u8;
            let g = ((value >> 5) & 0x1F) as u8;
            let b = ((value >> 10) & 0x1F) as u8;
            let out = ((y * 240 + x) * 3) as usize;
            framebuffer[out] = (r << 3) | (r >> 2);
            framebuffer[out + 1] = (g << 3) | (g >> 2);
            framebuffer[out + 2] = (b << 3) | (b >> 2);
        }
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Default)]
pub struct CpuState {
    pub regs: [u32; 16],
    pub cpsr: u32,
    pub spsr: u32,
    pub halted: bool,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct FrameResult {
    pub frame_index: u64,
    pub cycles: u64,
    pub halted: bool,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum BootMode {
    /// 內建進階 HLE；不需要真實 BIOS。
    HleAdvanced,
    /// 只跑不需要 BIOS 的測試 ROM。
    TestRomOnly,
    /// Legacy／optional differential；不是 production 路徑。
    RequireBios,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum CoreError {
    RomTooSmall { size: usize },
    BadHeader { offset: usize, expected: u8, actual: u8 },
    Bus(BusError),
    Cpu(CpuError),
    SnapshotCorrupt(String),
    /// G1 以前的預期狀態：Rust core 尚未接上執行。
    NotImplemented(&'static str),
}

impl From<BusError> for CoreError {
    fn from(value: BusError) -> Self {
        CoreError::Bus(value)
    }
}

impl From<CpuError> for CoreError {
    fn from(value: CpuError) -> Self {
        CoreError::Cpu(value)
    }
}

/// Rust core 的單一 frame 邊界。
#[derive(Debug)]
pub struct Core {
    pub bus: Bus,
    pub cpu: Cpu,
    config: CoreConfig,
    boot_mode: BootMode,
    pub state: CpuState,
    pub cycles: u64,
    pub frame_index: u64,
    framebuffer: Vec<u8>,
    /// 本 frame 已逐線繪製的行數（HBlank 驅動）。
    rendered_lines: u32,
}

impl Core {
    /// 建立 core；目前只驗證 ROM header，尚未執行 CPU。
    pub fn new(rom: Vec<u8>, config: CoreConfig) -> Result<Self, CoreError> {
        if rom.len() < 0xC0 {
            return Err(CoreError::RomTooSmall { size: rom.len() });
        }
        // GBATEK: ROM header fixed byte at 0xB2 is 0x96.
        if rom[0xB2] != 0x96 {
            return Err(CoreError::BadHeader {
                offset: 0xB2,
                expected: 0x96,
                actual: rom[0xB2],
            });
        }
        let mut bus = Bus::new(rom)?;
        bus.mgba_timing = config.timing_model == TimingModel::Mgba;
        // `functional` = 所有存取 1 cycle 的近似模式（Python `TimingMode.FUNCTIONAL`）。
        // production／GUI 用真 waitstate，否則 EWRAM／ROM 會同 IWRAM 一樣快。
        bus.functional = config.functional;
        let mut cpu = Cpu::new();
        if config.hle_bios {
            cpu.apply_post_boot();
            bus.apply_post_boot();
        }
        Ok(Self {
            bus,
            cpu,
            config,
            boot_mode: if config.hle_bios {
                BootMode::HleAdvanced
            } else {
                BootMode::RequireBios
            },
            state: CpuState::default(),
            cycles: 0,
            frame_index: 0,
            framebuffer: vec![0; 240 * 160 * 3],
            rendered_lines: 0,
        })
    }

    pub fn config(&self) -> CoreConfig {
        self.config
    }

    /// 載入真實 BIOS dump（最多 16 KiB）。只供應 BIOS 讀取內容；
    /// HLE 開機流程不變，所以 suite「BIOS load」可以直接讀到真資料。
    pub fn load_bios(&mut self, data: &[u8]) {
        self.bus.load_bios(data);
    }

    pub fn boot_mode(&self) -> BootMode {
        self.boot_mode
    }

    pub fn rom(&self) -> &[u8] {
        &self.bus.rom
    }

    pub fn framebuffer(&self) -> &[u8] {
        &self.framebuffer
    }

    /// 直接用目前 VRAM／IO／OAM 狀態重畫整個 frame。
    ///
    /// Production 路徑是 HBlank 逐線繪製；這個入口給 framebuffer differential
    /// 與 snapshot 後的整張重畫使用（不推進 CPU）。
    pub fn render_now(&mut self) {
        self.render_current_mode();
    }

    fn render_current_mode(&mut self) {
        self.render_scanlines(0, 160);
    }

    /// 繪製 scanline `y0..y1`；每次 frame 的 HBlank 事件逐線呼叫，
    /// 讓 mid-frame 的 DISPCNT/BGxCNT/OAM 變更即時反映（同 Python 行為）。
    fn render_scanlines(&mut self, y0: u32, y1: u32) {
        let mode = self.bus.ppu.dispcnt & 0x7;
        if (3..=5).contains(&mode) {
            self.render_bitmap_mode(mode as u32, y0, y1);
        } else if mode <= 2 {
            render_mode0(&self.bus, &mut self.framebuffer, y0, y1);
        } else {
            let start = (y0 * 240 * 3) as usize;
            let end = (y1 * 240 * 3) as usize;
            self.framebuffer[start..end].fill(0);
        }
    }

    fn write_rgb555(&mut self, pixel: usize, value: u16) {
        let r = (value & 0x1F) as u8;
        let g = ((value >> 5) & 0x1F) as u8;
        let b = ((value >> 10) & 0x1F) as u8;
        let out = pixel * 3;
        self.framebuffer[out] = (r << 3) | (r >> 2);
        self.framebuffer[out + 1] = (g << 3) | (g >> 2);
        self.framebuffer[out + 2] = (b << 3) | (b >> 2);
    }

    /// BG Mode 3/4/5：bitmap 以 BG2 實作，再疊 OBJ 與 alpha/fade/window。
    ///
    /// GBATEK: mode 4 的 index 0 透明；mode 5 只有 160x128；OBJ 與 BG 同
    /// priority 時 OBJ 在上層（Video/OBJ "Priority"）。
    fn render_bitmap_mode(&mut self, mode: u32, y0: u32, y1: u32) {
        let dispcnt = self.bus.ppu.dispcnt;
        if dispcnt & 0x80 != 0 {
            let start = (y0 * 240 * 3) as usize;
            let end = (y1 * 240 * 3) as usize;
            self.framebuffer[start..end].fill(0xFF);
            return;
        }
        let page = if dispcnt & 0x10 != 0 { 0xA000 } else { 0 };
        let bg_priority = io_u16(&self.bus, 0x00A) & 0x3;
        let blend_control = io_u16(&self.bus, 0x050);
        let effect = (blend_control >> 6) & 0x3;
        let second_targets = (blend_control >> 8) & 0x3F;
        let alpha = io_u16(&self.bus, 0x052);
        let eva = (alpha & 0x1F).min(16);
        let evb = ((alpha >> 8) & 0x1F).min(16);
        let fade_amount = io_u16(&self.bus, 0x054) & 0x1F;
        let backdrop = u16::from_le_bytes([self.bus.palette[0], self.bus.palette[1]]);
        let targets = blend_control & 0x3F;
        let obj_on = dispcnt & 0x1000 != 0;
        let windows_enabled = dispcnt & 0xE000 != 0;
        let bg_target = 1u16 << 2;
        let obj_target = 0x10u16;
        for y in y0..y1 {
            let mut line_sprites = if obj_on {
                collect_line_sprites(&self.bus, y, dispcnt)
            } else {
                Vec::new()
            };
            let window_sprites: Vec<LineSprite> = line_sprites.iter().copied().filter(|s| s.window).collect();
            line_sprites.retain(|s| !s.window);
            for x in 0..240u32 {
                let mask = if windows_enabled {
                    window_mask(&self.bus, x, y, dispcnt, &window_sprites)
                } else {
                    0x3F
                };
                let bg_value: Option<u16> = if mask & 0x04 == 0 {
                    None
                } else if mode == 4 {
                    let index = self.bus.vram[(page + y * 240 + x) as usize] as usize;
                    if index == 0 {
                        None
                    } else {
                        Some(u16::from_le_bytes([
                            self.bus.palette[index * 2],
                            self.bus.palette[index * 2 + 1],
                        ]))
                    }
                } else if mode == 5 {
                    if x >= 160 || y >= 128 {
                        None
                    } else {
                        let address = (page + (y * 160 + x) * 2) as usize;
                        Some(u16::from_le_bytes([
                            self.bus.vram[address],
                            self.bus.vram[address + 1],
                        ]))
                    }
                } else {
                    let address = ((y * 240 + x) * 2) as usize;
                    Some(u16::from_le_bytes([
                        self.bus.vram[address],
                        self.bus.vram[address + 1],
                    ]))
                };
                let sprite = if mask & 0x10 != 0 {
                    sprite_pixel_in(&self.bus, x, y, dispcnt, &line_sprites)
                } else {
                    None
                };
                let (value, top_target, bottom, bottom_target) = match (sprite, bg_value) {
                    (Some((priority, color)), Some(bg)) if priority <= bg_priority => {
                        (color, obj_target, Some(bg), bg_target)
                    }
                    (Some((_priority, color)), Some(bg)) => (bg, bg_target, Some(color), obj_target),
                    (Some((_priority, color)), None) => (color, obj_target, None, 0),
                    (None, Some(bg)) => (bg, bg_target, None, 0),
                    (None, None) => (backdrop, 0, None, 0),
                };
                let mut value = value;
                if top_target != 0 && targets & top_target != 0 {
                    if effect == 1 {
                        if let Some(bottom) = bottom {
                            if second_targets & bottom_target != 0 {
                                value = mix_rgb555(bottom, value, eva, evb);
                            } else if second_targets & 0x20 != 0 {
                                value = mix_rgb555(backdrop, value, eva, evb);
                            }
                        } else if second_targets & 0x20 != 0 {
                            value = mix_rgb555(backdrop, value, eva, evb);
                        }
                    } else if effect == 2 || effect == 3 {
                        value = fade_rgb555(value, fade_amount, effect == 2);
                    }
                }
                self.write_rgb555((y * 240 + x) as usize, value);
            }
        }
    }

    /// 單步 CPU；tick PPU/timer，服務 DMA，再做 2-cycle IRQ pipeline 檢查。
    pub fn step(&mut self) -> Result<u32, CpuError> {
        let cost = self.cpu.step(&mut self.bus)?;
        self.bus.tick(cost);
        // 即時 DMA 有起動延遲：CPU 夠快（IWRAM）時，下一條指令（timer read）
        // 會先完成；慢 fetch（ROM）就 DMA 搶先。
        if self.bus.dma_startup > 0 {
            self.bus.dma_startup = self.bus.dma_startup.saturating_sub(cost);
        }
        let dma = if self.bus.dma_startup == 0 {
            self.bus.service_dma()
        } else {
            0
        };
        if dma != 0 {
            self.cpu.cycles += dma as u64;
            self.bus.tick(dma);
        }
        self.bus.poll_keypad();
        let base = cost + dma;
        let irq = self.cpu.check_irq(&mut self.bus, base);
        if irq != 0 {
            self.bus.tick(irq);
        }
        self.render_completed_scanlines();
        Ok(base + irq)
    }

    /// 序列化完整機器狀態（ROM SHA 自動計算；config hash 由 adapter 提供）。
    pub fn save_state(&self) -> Vec<u8> {
        self.save_state_with_hashes(sha256(&self.bus.rom), [0u8; 32])
    }

    /// 序列化完整機器狀態，並寫入指定的 ROM／config SHA-256。
    pub fn save_state_with_hashes(&self, rom_sha: [u8; 32], config_sha: [u8; 32]) -> Vec<u8> {
        const CPU: [u8; 4] = *b"CPU\0";
        const BUS: [u8; 4] = *b"BUS\0";
        const PPU: [u8; 4] = *b"PPU\0";
        const DMA: [u8; 4] = *b"DMA\0";
        const TMR: [u8; 4] = *b"TMR\0";
        const IRQ: [u8; 4] = *b"IRQ\0";
        const KEY: [u8; 4] = *b"KEY\0";
        const CRT: [u8; 4] = *b"CRT\0";
        const SCH: [u8; 4] = *b"SCH\0";

        let mut irq = Vec::new();
        put_u32(&mut irq, u32::from(self.bus.ime));
        put_u32(&mut irq, self.bus.ie as u32);
        put_u32(&mut irq, self.bus.if_ as u32);

        let mut key = Vec::new();
        put_u32(
            &mut key,
            u16::from_le_bytes([self.bus.io[0x132], self.bus.io[0x133]]) as u32,
        );
        put_u16(&mut key, self.bus.keyinput);

        let mut sch = Vec::new();
        put_u64(&mut sch, self.cpu.cycles);
        put_u32(&mut sch, self.bus.ppu.frame_index as u32);

        let sections: [(&[u8; 4], Vec<u8>); 9] = [
            (&CPU, self.cpu.snapshot_section()),
            (&BUS, self.bus.snapshot_section()),
            (&PPU, self.bus.ppu.snapshot_section()),
            (&DMA, self.bus.snapshot_dma()),
            (&TMR, self.bus.snapshot_timers()),
            (&IRQ, irq),
            (&KEY, key),
            (&CRT, Vec::new()),
            (&SCH, sch),
        ];
        let mut payload = Vec::new();
        for (id, data) in sections {
            payload.extend_from_slice(id);
            put_u64(&mut payload, data.len() as u64);
            payload.extend_from_slice(&data);
        }

        let mut out = Vec::with_capacity(SNAPSHOT_HEADER_SIZE + payload.len());
        out.extend_from_slice(b"GEMU");
        put_u32(&mut out, 1);
        out.extend_from_slice(&[0, 0, 1, 0, 0, 0]); // emulator version (0,1,0)
        out.extend_from_slice(&rom_sha);
        out.extend_from_slice(&config_sha);
        put_u64(&mut out, payload.len() as u64);
        put_u32(&mut out, crc32(&payload));
        out.extend_from_slice(&payload);
        out
    }

    /// 還原 `save_state()` 產生的 snapshot。
    pub fn load_state(&mut self, data: &[u8]) -> Result<(), CoreError> {
        if data.len() < SNAPSHOT_HEADER_SIZE || &data[0..4] != b"GEMU" {
            return Err(CoreError::SnapshotCorrupt("header magic／長度不符".to_string()));
        }
        let version = u32::from_le_bytes([data[4], data[5], data[6], data[7]]);
        if version != 1 {
            return Err(CoreError::SnapshotCorrupt(format!("不支援的 snapshot version {version}")));
        }
        let payload_len = u64::from_le_bytes([
            data[78], data[79], data[80], data[81], data[82], data[83], data[84], data[85],
        ]) as usize;
        let payload = &data[SNAPSHOT_HEADER_SIZE..];
        if payload_len != payload.len() {
            return Err(CoreError::SnapshotCorrupt("payload 長度不符".to_string()));
        }
        let expected_crc = u32::from_le_bytes([data[86], data[87], data[88], data[89]]);
        if crc32(payload) != expected_crc {
            return Err(CoreError::SnapshotCorrupt("payload CRC-32 不符".to_string()));
        }

        let mut sections: [Option<&[u8]>; 9] = [None; 9];
        let mut offset = 0usize;
        while offset < payload.len() {
            let header = payload.get(offset..offset + 12).ok_or_else(|| {
                CoreError::SnapshotCorrupt("section header 被截斷".to_string())
            })?;
            let id = &header[0..4];
            let length = u64::from_le_bytes([
                header[4], header[5], header[6], header[7],
                header[8], header[9], header[10], header[11],
            ]) as usize;
            offset += 12;
            let body = payload.get(offset..offset + length).ok_or_else(|| {
                CoreError::SnapshotCorrupt("section body 被截斷".to_string())
            })?;
            offset += length;
            let slot = match id {
                b"CPU\0" => 0,
                b"BUS\0" => 1,
                b"PPU\0" => 2,
                b"DMA\0" => 3,
                b"TMR\0" => 4,
                b"IRQ\0" => 5,
                b"KEY\0" => 6,
                b"CRT\0" => 7,
                b"SCH\0" => 8,
                _ => continue,
            };
            sections[slot] = Some(body);
        }
        let bad = |name: &str| CoreError::SnapshotCorrupt(format!("缺少必要 section {name}"));
        let cpu = sections[0].ok_or_else(|| bad("CPU"))?;
        let bus = sections[1].ok_or_else(|| bad("BUS"))?;
        let ppu = sections[2].ok_or_else(|| bad("PPU"))?;
        let dma = sections[3].ok_or_else(|| bad("DMA"))?;
        let timers = sections[4].ok_or_else(|| bad("TMR"))?;
        let irq = sections[5].ok_or_else(|| bad("IRQ"))?;
        let key = sections[6].ok_or_else(|| bad("KEY"))?;
        let _crt = sections[7].ok_or_else(|| bad("CRT"))?;
        let sch = sections[8].ok_or_else(|| bad("SCH"))?;

        self.cpu.restore_section(cpu).map_err(CoreError::SnapshotCorrupt)?;
        self.bus.restore_section(bus).map_err(CoreError::SnapshotCorrupt)?;
        self.bus.ppu.restore_section(ppu).map_err(CoreError::SnapshotCorrupt)?;
        self.bus.restore_dma(dma).map_err(CoreError::SnapshotCorrupt)?;
        self.bus.restore_timers(timers).map_err(CoreError::SnapshotCorrupt)?;

        let mut reader = SnapshotReader::new(irq);
        self.bus.ime = reader.u32().ok_or_else(|| bad("IRQ"))? != 0;
        self.bus.ie = reader.u32().ok_or_else(|| bad("IRQ"))? as u16;
        self.bus.if_ = reader.u32().ok_or_else(|| bad("IRQ"))? as u16;
        let mut reader = SnapshotReader::new(key);
        let keycnt = reader.u32().ok_or_else(|| bad("KEY"))?;
        self.bus.io[0x132..0x134].copy_from_slice(&(keycnt as u16).to_le_bytes());
        self.bus.keyinput = reader.u16().ok_or_else(|| bad("KEY"))?;
        let mut reader = SnapshotReader::new(sch);
        self.cpu.cycles = reader.u64().ok_or_else(|| bad("SCH"))?;
        self.bus.ppu.frame_index = reader.u32().ok_or_else(|| bad("SCH"))? as u64;
        self.cycles = self.cpu.cycles;
        self.frame_index = self.bus.ppu.frame_index;
        self.cpu.irq_pending = self.bus.ime && (self.bus.ie & self.bus.if_) != 0;
        Ok(())
    }

    /// Frame loop：跑到 PPU frame boundary（與 Python `step_frame()` 一致）。
    ///
    /// Renderer 由 HBlank 事件逐線驅動（mid-frame 變更即時反映）；若整個
    /// frame 沒有任何可見 scanline 事件，才退回 frame 尾端整張重畫。
    pub fn run_frame(&mut self) -> Result<FrameResult, CoreError> {
        let start = self.cycles;
        let start_frame = self.bus.ppu.frame_index;
        self.rendered_lines = 0;
        while self.bus.ppu.frame_index == start_frame {
            let cost = self.step()?;
            if cost == 0 {
                return Err(CoreError::NotImplemented("CPU returned zero cycles"));
            }
            self.cycles = self.cpu.cycles;
        }
        self.frame_index = self.bus.ppu.frame_index;
        if self.config.render && self.rendered_lines == 0 {
            self.render_current_mode();
        }
        Ok(FrameResult {
            frame_index: self.frame_index - 1,
            cycles: self.cycles - start,
            halted: self.cpu.halted,
        })
    }

    /// 依 PPU 已完成的 HBlank 逐線繪製；`config.render` 關閉時只清掉事件。
    fn render_completed_scanlines(&mut self) {
        let lines = self.bus.ppu.take_completed_lines();
        if lines.is_empty() || !self.config.render {
            return;
        }
        for line in lines {
            if line < 160 {
                self.render_scanlines(line as u32, line as u32 + 1);
                self.rendered_lines += 1;
            }
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    /// 近似 cycle 模型（所有存取 1 cycle）：舊測試用它斷言精確 cycle 數。
    fn functional_config() -> CoreConfig {
        CoreConfig {
            functional: true,
            ..CoreConfig::default()
        }
    }

    fn minimal_rom() -> Vec<u8> {
        let mut rom = vec![0u8; 0xC0];
        rom[0xB2] = 0x96;
        rom
    }

    /// 供需要跑完整 frame 的測試使用：第一條指令是 `B .`，不會跑出 ROM。
    fn looping_rom() -> Vec<u8> {
        let mut rom = vec![0u8; 0x200];
        rom[0xB2] = 0x96;
        rom[0..4].copy_from_slice(&0xEAFF_FFFEu32.to_le_bytes());
        rom
    }

    #[test]
    fn timing_model_config_sets_bus_flag() {
        let default = Core::new(minimal_rom(), functional_config()).unwrap();
        assert!(default.bus.mgba_timing);
        assert_eq!(default.config().timing_model, TimingModel::Mgba);
        let legacy = Core::new(
            minimal_rom(),
            CoreConfig {
                timing_model: TimingModel::Legacy,
                ..CoreConfig::default()
            },
        )
        .unwrap();
        assert!(!legacy.bus.mgba_timing);
        assert_eq!(legacy.config().timing_model, TimingModel::Legacy);
    }

    #[test]
    fn step_services_immediate_dma() {
        let mut core = Core::new(minimal_rom(), functional_config()).unwrap();
        core.bus.write16(0x0200_0000, 0x1234);
        core.bus.write32(0x0400_00B0, 0x0200_0000);
        core.bus.write32(0x0400_00B4, 0x0200_0100);
        core.bus.write16(0x0400_00B8, 1);
        core.bus.write16(0x0400_00BA, 0x8000);
        let cost = core.step().unwrap();
        assert_eq!(core.bus.read16(0x0200_0100), 0x1234);
        assert_eq!(cost, 5); // CPU 1 + DMA (2N + 2I)
    }

    #[test]
    fn step_ticks_timer() {
        let mut core = Core::new(minimal_rom(), functional_config()).unwrap();
        core.bus.write16(0x0400_0100, 0);
        core.bus.write16(0x0400_0102, 0x0080);
        let cost = core.step().unwrap();
        assert_eq!(cost, 1);
        assert_eq!(core.bus.read16(0x0400_0100), 1);
    }

    #[test]
    fn step_enters_irq_when_ime_ie_if_set() {
        let mut core = Core::new(minimal_rom(), functional_config()).unwrap();
        core.bus.write16(0x0400_0208, 1); // IME
        core.bus.write16(0x0400_0200, 1); // IE VBlank
        core.bus.write32(0x0300_7FFC, 0x0800_0100); // user IRQ handler
        core.bus.if_ = 1;
        core.step().unwrap(); // arm IRQ pipeline
        core.step().unwrap(); // countdown
        core.step().unwrap(); // 進入 IRQ handler
        assert_eq!(core.cpu.cpsr & 0x1F, 0x12);
        assert_eq!(core.cpu.regs[15], 0x0800_0100);
    }

    #[test]
    fn halted_cpu_wakes_on_ie_if() {
        let mut core = Core::new(minimal_rom(), functional_config()).unwrap();
        core.cpu.halted = true;
        core.bus.write16(0x0400_0200, 1); // IE VBlank
        core.bus.write16(0x0400_0208, 1); // IME
        core.bus.write32(0x0300_7FFC, 0x0800_0100);
        core.bus.if_ = 1;
        core.step().unwrap();
        assert!(!core.cpu.halted);
        // Halt（SWI 0x02）：喚醒後先返回主程式，IRQ 喺 boundary 投遞。
        core.step().unwrap();
        core.step().unwrap();
        assert_eq!(core.cpu.cpsr & 0x1F, 0x12);
        assert_eq!(core.cpu.regs[15], 0x0800_0100);
    }

    #[test]
    fn intr_wait_wakes_and_dispatches_irq_immediately() {
        let mut core = Core::new(minimal_rom(), functional_config()).unwrap();
        core.cpu.halted = true;
        core.cpu.wait_irq = 1;
        core.bus.write16(0x0400_0200, 1); // IE VBlank
        core.bus.write16(0x0400_0208, 1); // IME
        core.bus.write32(0x0300_7FFC, 0x0800_0100);
        core.bus.if_ = 1;
        core.step().unwrap();
        assert!(!core.cpu.halted);
        // IntrWait（SWI 0x04）：BIOS 要 handler 行完先返回，所以即刻投遞。
        assert_eq!(core.cpu.cpsr & 0x1F, 0x12);
        assert_eq!(core.cpu.regs[15], 0x0800_0100);
    }

    #[test]
    fn intr_wait_serves_other_irq_and_resumes_halt() {
        // rates.gba 的聲效引擎用 IntrWait 等 VBlank；timer1 IRQ 期間要照樣入
        // handler，唔可以留喺 halted 卡死（否则 DMA sound buffer swap 遲到，
        // 32768K 測試會斷斷續續）。
        let mut core = Core::new(minimal_rom(), functional_config()).unwrap();
        core.cpu.halted = true;
        core.cpu.wait_irq = 1; // 等 VBlank
        core.bus.write16(0x0400_0200, 0x0011); // IE：VBlank + Timer1
        core.bus.write16(0x0400_0208, 1); // IME
        core.bus.write32(0x0300_7FFC, 0x0800_0100);
        core.bus.if_ = 0x0010; // 嚟的是 Timer1，唔係等緊嘅 VBlank
        for _ in 0..3 {
            core.step().unwrap();
        }
        assert!(!core.cpu.halted, "IntrWait 期間收到其他 IRQ 要叫醒 CPU");
        assert_eq!(core.cpu.cpsr & 0x1F, 0x12);
        assert_eq!(core.cpu.regs[15], 0x0800_0100);
        assert!(core.cpu.resume_halt_irq, "handler 完成後要回復 halt");
    }

    #[test]
    fn run_frame_completes_while_halted() {
        let mut core = Core::new(minimal_rom(), functional_config()).unwrap();
        core.cpu.halted = true;
        let frame = core.run_frame().unwrap();
        assert_eq!(frame.cycles, FRAME_CYCLES);
        assert!(core.cpu.halted);
    }

    fn read_io16(core: &Core, offset: usize) -> u16 {
        u16::from_le_bytes([core.bus.io[offset], core.bus.io[offset + 1]])
    }

    #[test]
    fn post_boot_sets_affine_identity() {
        // BIOS 開機 default：BG2/BG3 affine matrix = identity（PA=PD=0x0100）。
        let core = Core::new(minimal_rom(), CoreConfig::default()).unwrap();
        for offset in [0x20usize, 0x26, 0x30, 0x36] {
            assert_eq!(read_io16(&core, offset), 0x0100, "offset {offset:#x}");
        }
    }

    #[test]
    fn register_ram_reset_sets_affine_identity() {
        // LeafGreen 開機用 SWI 0x01（flags 0x80）重設 IO，之後靠 BIOS 的
        // identity default 用 BG2 畫 Professor Oak。
        let mut rom = vec![0u8; 0x200];
        rom[0xB2] = 0x96;
        rom[0..4].copy_from_slice(&0xE3A0_0080u32.to_le_bytes()); // mov r0, #0x80
        rom[4..8].copy_from_slice(&0xEF01_0000u32.to_le_bytes()); // swi 0x01（comment 在 bit16-23）
        rom[8..12].copy_from_slice(&0xEAFF_FFFEu32.to_le_bytes()); // b .
        let mut core = Core::new(rom, functional_config()).unwrap();
        for offset in [0x20usize, 0x26, 0x30, 0x36] {
            core.bus.write16(0x0400_0000 + offset as u32, 0);
        }
        core.step().unwrap(); // mov r0, #0x80
        core.step().unwrap(); // swi 0x01
        for offset in [0x20usize, 0x26, 0x30, 0x36] {
            assert_eq!(read_io16(&core, offset), 0x0100, "offset {offset:#x}");
        }
    }

    #[test]
    fn snapshot_roundtrip_is_byte_identical() {
        let mut core = Core::new(looping_rom(), functional_config()).unwrap();
        core.bus.write16(0x0400_0000, 3);
        core.bus.write16(0x0600_0000, 0x001F);
        core.bus.write16(0x0400_0100, 0);
        core.bus.write16(0x0400_0102, 0x0080);
        core.run_frame().unwrap();
        core.bus.write32(0x0200_0000, 0x1122_3344);
        let saved = core.save_state();

        core.cpu.regs[0] = 0xDEAD_BEEF;
        core.bus.write32(0x0200_0000, 0);
        core.cpu.cycles = 123;
        core.load_state(&saved).unwrap();
        assert_eq!(core.save_state(), saved);
        assert_eq!(core.bus.read32(0x0200_0000), 0x1122_3344);
    }

    #[test]
    fn rejects_short_rom() {
        assert_eq!(
            Core::new(vec![0u8; 0x10], CoreConfig::default()).unwrap_err(),
            CoreError::RomTooSmall { size: 0x10 }
        );
    }

    #[test]
    fn rejects_bad_header_fixed_byte() {
        let mut rom = minimal_rom();
        rom[0xB2] = 0x00;
        assert_eq!(
            Core::new(rom, CoreConfig::default()).unwrap_err(),
            CoreError::BadHeader {
                offset: 0xB2,
                expected: 0x96,
                actual: 0x00
            }
        );
    }

    #[test]
    fn creates_core_and_keeps_reference_status() {
        let mut core = Core::new(minimal_rom(), functional_config()).unwrap();
        assert_eq!(core.boot_mode(), BootMode::HleAdvanced);
        assert_eq!(core.frame_index, 0);
        assert_eq!(core.cycles, 0);
    }


    #[test]
    fn frame_loop_reaches_frame_boundary() {
        let mut rom = vec![0u8; 0x100];
        rom[0xB2] = 0x96;
        rom[0..4].copy_from_slice(&0xEAFF_FFFEu32.to_le_bytes()); // B .
        let mut core = Core::new(rom, CoreConfig::default()).unwrap();
        let frame = core.run_frame().unwrap();
        assert_eq!(frame.frame_index, 0);
        assert!(frame.cycles >= FRAME_CYCLES);
        assert_eq!(core.frame_index, 1);
    }


    #[test]
    fn mode4_bitmap8_pixel() {
        let mut rom = vec![0u8; 0x100];
        rom[0xB2] = 0x96;
        rom[0..4].copy_from_slice(&0xEAFF_FFFEu32.to_le_bytes());
        let mut core = Core::new(rom, CoreConfig::default()).unwrap();
        core.bus.write16(0x0400_0000, 4);
        core.bus.write16(0x0500_0002, 0x001F);
        core.bus.write8(0x0600_0000, 1);
        core.run_frame().unwrap();
        assert_eq!(&core.framebuffer()[0..3], &[0xFF, 0x00, 0x00]);
    }

    #[test]
    fn mode5_bitmap16_pixel() {
        let mut rom = vec![0u8; 0x100];
        rom[0xB2] = 0x96;
        rom[0..4].copy_from_slice(&0xEAFF_FFFEu32.to_le_bytes());
        let mut core = Core::new(rom, CoreConfig::default()).unwrap();
        core.bus.write16(0x0400_0000, 5);
        core.bus.write16(0x0600_0000, 0x001F);
        core.run_frame().unwrap();
        assert_eq!(&core.framebuffer()[0..3], &[0xFF, 0x00, 0x00]);
    }

    #[test]
    fn mode3_framebuffer() {
        let mut rom = vec![0u8; 0x100];
        rom[0xB2] = 0x96;
        rom[0..4].copy_from_slice(&0xEAFF_FFFEu32.to_le_bytes());
        let mut core = Core::new(rom, CoreConfig::default()).unwrap();
        core.bus.write16(0x0400_0000, 3); // Mode 3
        core.bus.write16(0x0600_0000, 0x001F); // red
        core.run_frame().unwrap();
        assert_eq!(&core.framebuffer()[0..3], &[0xFF, 0x00, 0x00]);
    }


    #[test]
    fn mode0_text_bg_pixel() {
        let mut rom = vec![0u8; 0x100];
        rom[0xB2] = 0x96;
        rom[0..4].copy_from_slice(&0xEAFF_FFFEu32.to_le_bytes());
        let mut core = Core::new(rom, CoreConfig::default()).unwrap();
        core.bus.write16(0x0400_0000, 0x0100); // Mode 0 + BG0
        core.bus.write16(0x0400_0008, 0x0004); // BG0: char base 0x4000
        core.bus.write16(0x0500_0002, 0x001F); // palette index 1 = red
        core.bus.write16(0x0600_0000, 0x0000); // map tile 0
        for i in 0..32 {
            core.bus.write8(0x0600_4000 + i, 0x11); // 4bpp color 1
        }
        core.run_frame().unwrap();
        assert_eq!(&core.framebuffer()[0..3], &[0xFF, 0x00, 0x00]);
    }


    #[test]
    fn obj_window_uses_winout_layers() {
        let mut rom = vec![0u8; 0x100];
        rom[0xB2] = 0x96;
        rom[0..4].copy_from_slice(&0xEAFF_FFFEu32.to_le_bytes());
        let mut core = Core::new(rom, CoreConfig::default()).unwrap();
        // Mode 0：BG0 全畫面紅；窗外 hide BG0，OBJ window 內 show BG0。
        core.bus.write16(0x0400_0000, 0x9100); // OBJ + OBJ window + BG0
        core.bus.write16(0x0400_0008, 0x0004); // BG0 char base 0x4000
        core.bus.write16(0x0400_004A, 0x0100); // WINOUT: OBJ window 內 = BG0
        core.bus.write16(0x0500_0002, 0x001F); // BG palette 1 = 紅
        core.bus.write16(0x0600_0000, 0x0000); // BG0 map tile 0
        for i in 0..32 {
            core.bus.write8(0x0600_4000 + i, 0x11);
        }
        // OAM 0：OBJ window sprite（attr0 mode 2）(0,0) 8x8、tile 0、4bpp；
        // 全部 pixel 都唔透明，所以 window 範圍 = 0..8。
        core.bus.write16(0x0700_0000, 0x0800);
        for i in 0..8 {
            core.bus.write32(0x0601_0000 + i * 4, 0x1111_1111);
        }
        core.run_frame().unwrap();
        // window 內 (0,0) 見到 BG0 紅；窗外 (100,0) 冇 layer → backdrop 黑。
        assert_eq!(&core.framebuffer()[0..3], &[0xFF, 0x00, 0x00]);
        let out = (100 * 3) as usize;
        assert_eq!(&core.framebuffer()[out..out + 3], &[0, 0, 0]);
    }

    #[test]
    fn mode0_sprite_pixel() {
        let mut rom = vec![0u8; 0x100];
        rom[0xB2] = 0x96;
        rom[0..4].copy_from_slice(&0xEAFF_FFFEu32.to_le_bytes());
        let mut core = Core::new(rom, CoreConfig::default()).unwrap();
        core.bus.write16(0x0400_0000, 0x1000); // Mode 0 + OBJ
        core.bus.write16(0x0700_0000, 0x0000); // OAM attr0
        core.bus.write16(0x0700_0002, 0x0000); // attr1
        core.bus.write16(0x0700_0004, 0x0000); // attr2
        core.bus.write16(0x0500_0202, 0x001F); // OBJ palette index 1 red
        for i in 0..8 {
            core.bus.write32(0x0601_0000 + i * 4, 0x1111_1111); // OBJ tile 0, 4bpp color 1
        }
        core.run_frame().unwrap();
        assert_eq!(&core.framebuffer()[0..3], &[0xFF, 0x00, 0x00]);
    }


    #[test]
    fn affine_obj_identity() {
        let mut rom = vec![0u8; 0x100];
        rom[0xB2] = 0x96;
        rom[0..4].copy_from_slice(&0xEAFF_FFFEu32.to_le_bytes());
        let mut core = Core::new(rom, CoreConfig::default()).unwrap();
        core.bus.write16(0x0400_0000, 0x1000); // Mode 0 + OBJ
        core.bus.write16(0x0700_0000, 0x0104); // affine, y=4
        core.bus.write16(0x0700_0002, 0x0004); // x=4, group 0
        core.bus.write16(0x0700_0004, 0x0000); // tile 0
        core.bus.write16(0x0700_0006, 256);    // PA
        core.bus.write16(0x0700_001E, 256);    // PD
        core.bus.write16(0x0500_0202, 0x001F); // OBJ palette 1 red
        for i in 0..8 {
            core.bus.write32(0x0601_0000 + i * 4, 0x1111_1111);
        }
        core.run_frame().unwrap();
        assert_eq!(&core.framebuffer()[(4 * 240 + 4) * 3..(4 * 240 + 4) * 3 + 3], &[0xFF, 0x00, 0x00]);
    }


    #[test]
    fn mode2_affine_bg_pixel() {
        let mut rom = vec![0u8; 0x100];
        rom[0xB2] = 0x96;
        rom[0..4].copy_from_slice(&0xEAFF_FFFEu32.to_le_bytes());
        let mut core = Core::new(rom, CoreConfig::default()).unwrap();
        core.bus.write16(0x0400_0000, 0x0402); // Mode 2 + BG2
        core.bus.write16(0x0400_000C, 0x0004); // BG2 char base 0x4000, size 128
        core.bus.write16(0x0400_0020, 256);    // PA
        core.bus.write16(0x0400_0026, 256);    // PD
        core.bus.write16(0x0500_0002, 0x001F); // palette 1 red
        core.bus.write8(0x0600_0000, 0);       // map tile 0
        for i in 0..64 {
            core.bus.write8(0x0600_4000 + i, 1);
        }
        core.run_frame().unwrap();
        assert_eq!(&core.framebuffer()[0..3], &[0xFF, 0x00, 0x00]);
    }


    #[test]
    fn window_masks_bg() {
        let mut rom = vec![0u8; 0x100];
        rom[0xB2] = 0x96;
        rom[0..4].copy_from_slice(&0xEAFF_FFFEu32.to_le_bytes());
        let mut core = Core::new(rom, CoreConfig::default()).unwrap();
        core.bus.write16(0x0400_0000, 0x2100); // Mode 0 + BG0 + WIN0
        core.bus.write16(0x0400_0008, 0x0004); // BG0 char base 0x4000
        core.bus.write16(0x0400_0040, 0x000A); // WIN0H x 0..10 (X1<<8 | X2)
        core.bus.write16(0x0400_0044, 0x00A0); // WIN0V y 0..160 (Y1<<8 | Y2)
        core.bus.write16(0x0400_0048, 0x0000); // WININ: all off
        core.bus.write16(0x0400_004A, 0x003F); // WINOUT: all on
        core.bus.write16(0x0500_0002, 0x001F);
        core.bus.write16(0x0600_0000, 0);
        for i in 0..32 {
            core.bus.write8(0x0600_4000 + i, 0x11);
        }
        core.run_frame().unwrap();
        assert_eq!(&core.framebuffer()[0..3], &[0, 0, 0]);
        assert_eq!(&core.framebuffer()[(20 * 3)..(20 * 3 + 3)], &[0xFF, 0, 0]);
    }


    #[test]
    fn blend_helpers() {
        let mixed = mix_rgb555(0x7C00, 0x001F, 8, 8); // blue bottom, red top
        assert_eq!(mixed & 0x1F, 15);
        assert_eq!((mixed >> 10) & 0x1F, 15);
        assert_eq!(fade_rgb555(0x001F, 16, true), 0x421F);
        assert_eq!(fade_rgb555(0x7FFF, 16, false), 0x3DEF);
    }


    #[test]
    fn bg_mosaic_samples_lower_pixel() {
        let mut rom = vec![0u8; 0x100];
        rom[0xB2] = 0x96;
        rom[0..4].copy_from_slice(&0xEAFF_FFFEu32.to_le_bytes());
        let mut core = Core::new(rom, CoreConfig::default()).unwrap();
        core.bus.write16(0x0400_0000, 0x0100); // Mode 0 + BG0
        core.bus.write16(0x0400_004C, 0x0001); // mosaic size 2
        core.bus.write16(0x0400_0008, 0x0044); // BG0 char base 0x4000 + mosaic
        core.bus.write16(0x0500_0002, 0x001F); // palette 1 red
        core.bus.write16(0x0500_0004, 0x03E0); // palette 2 green
        core.bus.write16(0x0600_0000, 0);
        core.bus.write8(0x0600_4000, 0x21); // pixel0=1(red), pixel1=2(green)
        for i in 1..32 {
            core.bus.write8(0x0600_4000 + i, 0x11);
        }
        core.run_frame().unwrap();
        assert_eq!(&core.framebuffer()[3..6], &[0xFF, 0, 0]);
    }

    #[test]
    fn frame_constants_match_python_reference() {
        assert_eq!(FRAME_CYCLES, 280_896);
        assert_eq!(SCANLINE_CYCLES, 1_232);
        assert_eq!(VBLANK_START_CYCLE, 160 * SCANLINE_CYCLES);
    }
}
