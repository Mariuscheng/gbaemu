//! 診斷用：跑真 ROM N 個 frame，印每 frame 的畫面統計 + PPU／window 暫存器。
//!
//! 用法：
//!   cargo run --bin rom_stats -- rom.gba --frames 60,120,180
//!   cargo run --bin rom_stats -- rom.gba --every 60 --frames 600
//!   cargo run --bin rom_stats -- rom.gba --frames 900,1200 --bmp debug/out

use gbaemu_core::{Core, CoreConfig};

fn reg(core: &mut Core, offset: u32) -> u16 {
    core.bus.read16(0x0400_0000 + offset)
}

/// 24-bit BMP（bottom-up），方便直接開圖比對。
fn write_bmp(path: &std::path::Path, fb: &[u8], width: u32, height: u32) -> std::io::Result<()> {
    let row_bytes = width * 3;
    let padding = (4 - row_bytes % 4) % 4;
    let image_size = (row_bytes + padding) * height;
    let file_size = 54 + image_size;
    let mut out = Vec::with_capacity(file_size as usize);
    out.extend_from_slice(b"BM");
    out.extend_from_slice(&file_size.to_le_bytes());
    out.extend_from_slice(&0u32.to_le_bytes());
    out.extend_from_slice(&54u32.to_le_bytes());
    out.extend_from_slice(&40u32.to_le_bytes());
    out.extend_from_slice(&(width as i32).to_le_bytes());
    out.extend_from_slice(&(height as i32).to_le_bytes());
    out.extend_from_slice(&1u16.to_le_bytes());
    out.extend_from_slice(&24u16.to_le_bytes());
    out.extend_from_slice(&0u32.to_le_bytes());
    out.extend_from_slice(&image_size.to_le_bytes());
    out.extend_from_slice(&2835i32.to_le_bytes());
    out.extend_from_slice(&2835i32.to_le_bytes());
    out.extend_from_slice(&0u32.to_le_bytes());
    out.extend_from_slice(&0u32.to_le_bytes());
    for y in (0..height as usize).rev() {
        for x in 0..width as usize {
            let i = (y * width as usize + x) * 3;
            out.extend_from_slice(&[fb[i + 2], fb[i + 1], fb[i]]);
        }
        out.extend(std::iter::repeat(0u8).take(padding as usize));
    }
    std::fs::write(path, out)
}

fn main() {
    let mut args = std::env::args().skip(1);
    let mut path = None;
    let mut every = 60u64;
    let mut max_frame = 600u64;
    let mut explicit: Vec<u64> = Vec::new();
    let mut bmp_dir: Option<std::path::PathBuf> = None;
    let mut scratch_dispcnt: Option<u16> = None;
    while let Some(arg) = args.next() {
        match arg.as_str() {
            "--every" => every = args.next().and_then(|v| v.parse().ok()).unwrap_or(60),
            "--scratch-dispcnt" => {
                scratch_dispcnt = args.next().and_then(|v| u16::from_str_radix(&v, 16).ok())
            }
            "--bmp" => {
                let dir = args.next().unwrap_or_else(|| ".".to_string());
                let dir = std::path::PathBuf::from(dir);
                let _ = std::fs::create_dir_all(&dir);
                bmp_dir = Some(dir);
            }
            "--frames" => {
                let value = args.next().unwrap_or_default();
                explicit = value
                    .split(',')
                    .filter_map(|part| part.trim().parse().ok())
                    .collect();
            }
            other => path = Some(other.to_string()),
        }
    }
    if let Some(last) = explicit.iter().max() {
        max_frame = *last;
    }
    let path = path.expect("需要 ROM 路徑");
    let rom = std::fs::read(&path).expect("read rom");
    let mut core = Core::new(rom, CoreConfig::default()).expect("core");
    let mut targets = explicit.clone();
    if targets.is_empty() {
        let mut frame = every;
        while frame <= max_frame {
            targets.push(frame);
            frame += every;
        }
    }

    let mut frame = 0u64;
    for target in targets {
        while frame < target {
            match core.run_frame() {
                Ok(_) => frame = core.bus.ppu.frame_index,
                Err(error) => {
                    println!("frame={frame} emulation error {error:?}");
                    return;
                }
            }
        }
        if let Some(value) = scratch_dispcnt {
            core.bus.write16(0x0400_0000, value);
            core.render_now();
        }
        let fb = core.framebuffer().to_vec();
        let nonzero = fb.chunks_exact(3).filter(|p| p != &[0, 0, 0]).count();
        let mut colors = [0u32; 0x8000];
        for pixel in fb.chunks_exact(3) {
            let rgb = ((pixel[0] as u32 >> 3) << 10)
                | ((pixel[1] as u32 >> 3) << 5)
                | (pixel[2] as u32 >> 3);
            colors[rgb as usize] += 1;
        }
        let distinct = colors.iter().filter(|c| **c != 0).count();
        let (dispcnt, bldcnt, bldalpha, bldy) = (
            reg(&mut core, 0x00),
            reg(&mut core, 0x50),
            reg(&mut core, 0x52),
            reg(&mut core, 0x54),
        );
        println!(
            "frame={frame} nonzero={nonzero} colors={distinct} \
             DISPCNT={dispcnt:#06x} mode={} BLDCNT={bldcnt:#06x} \
             BLDALPHA={bldalpha:#06x} BLDY={bldy:#06x} \
             WININ={:#06x} WINOUT={:#06x} WIN0H={:#06x} WIN1H={:#06x} \
             WIN0V={:#06x} WIN1V={:#06x} BG0={:#06x} BG1={:#06x} \
             BG2={:#06x} BG3={:#06x} PC={:#010x}",
            dispcnt & 7,
            reg(&mut core, 0x48),
            reg(&mut core, 0x4A),
            reg(&mut core, 0x40),
            reg(&mut core, 0x42),
            reg(&mut core, 0x44),
            reg(&mut core, 0x46),
            reg(&mut core, 0x08),
            reg(&mut core, 0x0A),
            reg(&mut core, 0x0C),
            reg(&mut core, 0x0E),
            core.cpu.regs[15],
        );
        // WIN0H/V、WIN1H/V、BGxHOFS/VOFS、BLDY 在真機是 write-only：read16 只會
        // 拿到 open bus。這裡直接看 Bus 內部 IO 陣列，才是 game 真正寫入的值。
        let io = |offset: usize| u16::from_le_bytes([core.bus.io[offset], core.bus.io[offset + 1]]);
        println!(
            "      raw WIN0H={:#06x} WIN1H={:#06x} WIN0V={:#06x} WIN1V={:#06x} \
             WININ={:#06x} WINOUT={:#06x} BLDY={:#06x} BG0HOFS={:#06x} BG2PA={:#06x}",
            io(0x40),
            io(0x42),
            io(0x44),
            io(0x46),
            io(0x48),
            io(0x4A),
            io(0x54),
            io(0x10),
            io(0x20),
        );
        if let Some(dir) = &bmp_dir {
            let path = dir.join(format!("frame_{frame:05}.bmp"));
            if let Err(error) = write_bmp(&path, &fb, 240, 160) {
                println!("bmp 寫入失敗 {path:?}: {error}");
            }
        }
    }
}
