//! 診斷用：量測 `render_now()` 的成本（不同 DISPCNT 組合）。
//!
//! 用法：cargo run --release --bin bench_render -- rom.gba --frames 120

use std::time::Instant;

use gbaemu_core::{Core, CoreConfig};

fn main() {
    let mut args = std::env::args().skip(1);
    let mut path = None;
    let mut frames = 120u64;
    while let Some(arg) = args.next() {
        match arg.as_str() {
            "--frames" => frames = args.next().and_then(|v| v.parse().ok()).unwrap_or(120),
            other => path = Some(other.to_string()),
        }
    }
    let rom = std::fs::read(path.expect("需要 ROM")).expect("read rom");
    let mut core = Core::new(rom, CoreConfig::default()).expect("core");
    for _ in 0..frames {
        core.run_frame().unwrap();
    }
    let dispcnt = core.bus.read16(0x0400_0000);
    println!("dispcnt={dispcnt:04x} frame={}", core.bus.ppu.frame_index);

    bench(&mut core, "full", dispcnt, 200);
    bench(&mut core, "no OBJ", dispcnt & !0x1000, 200);
    bench(&mut core, "OBJ only", (dispcnt & 0x1000) | 0x0040, 200);
    bench(&mut core, "BG0 only", dispcnt & 0x0100, 200);
    bench(&mut core, "blank layers", dispcnt & !0x1F00, 200);
}

fn bench(core: &mut Core, label: &str, dispcnt: u16, iterations: u32) {
    core.bus.write16(0x0400_0000, dispcnt);
    core.render_now(); // warm-up
    let start = Instant::now();
    for _ in 0..iterations {
        core.render_now();
    }
    let elapsed = start.elapsed();
    println!(
        "{label:12}: {:8.3} ms/frame ({dispcnt:04x})",
        elapsed.as_secs_f64() * 1000.0 / iterations as f64
    );
}
