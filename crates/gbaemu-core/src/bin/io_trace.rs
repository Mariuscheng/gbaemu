//! 診斷用：逐 instruction 監看 IO 暫存器變化（看 game 幾時寫 window／DISPCNT）。
//!
//! 用法：cargo run --bin io_trace -- rom.gba --frames 950 --offsets 00,40,42,44,46,48,4A
//!       --timers 會同時監看 timer reload（timer 暫存器唔在 io array 內）。

use gbaemu_core::{Core, CoreConfig};

fn main() {
    let mut args = std::env::args().skip(1);
    let mut path = None;
    let mut max_frames = 200u64;
    let mut offsets: Vec<usize> = vec![0x00, 0x01, 0x40, 0x42, 0x44, 0x46, 0x48, 0x4A, 0x50, 0x52];
    let mut start_frame = 0u64;
    let mut trace_timers = false;
    let mut trace_dma = false;
    while let Some(arg) = args.next() {
        match arg.as_str() {
            "--frames" => max_frames = args.next().and_then(|v| v.parse().ok()).unwrap_or(200),
            "--start" => start_frame = args.next().and_then(|v| v.parse().ok()).unwrap_or(0),
            "--timers" => trace_timers = true,
            "--dma" => trace_dma = true,
            "--offsets" => {
                let value = args.next().unwrap_or_default();
                offsets = value
                    .split(',')
                    .filter_map(|part| usize::from_str_radix(part.trim(), 16).ok())
                    .collect();
            }
            other => path = Some(other.to_string()),
        }
    }
    let path = path.expect("需要 ROM 路徑");
    let rom = std::fs::read(&path).expect("read rom");
    let mut core = Core::new(rom, CoreConfig::default()).expect("core");
    if start_frame > 0 {
        while core.bus.ppu.frame_index < start_frame {
            core.run_frame().expect("run frame");
        }
    }
    let mut prev: Vec<u8> = offsets.iter().map(|offset| core.bus.io[*offset]).collect();
    let mut prev_reload = core.bus.timer_reload;
    let mut prev_control = core.bus.timer_control;
    let mut prev_dma: [(u32, u32, u16, u16, u32, u32, u32); 4] = std::array::from_fn(|index| {
        (
            core.bus.dma_sad[index],
            core.bus.dma_dad[index],
            core.bus.dma_cnt_l[index],
            core.bus.dma_cnt_h[index],
            core.bus.dma_count[index],
            core.bus.dma_source[index],
            core.bus.dma_dest[index],
        )
    });
    let mut prev_frame = core.bus.ppu.frame_index;
    let mut steps = 0u64;
    while core.bus.ppu.frame_index < max_frames {
        let pc = core.cpu.regs[15];
        if let Err(error) = core.step() {
            println!("emulation error {error:?} pc={pc:08x}");
            break;
        }
        steps += 1;
        for (index, offset) in offsets.iter().enumerate() {
            let value = core.bus.io[*offset];
            if value != prev[index] {
                println!(
                    "frame={} step={steps} pc={pc:08x} io[{:02X}]={value:02x}",
                    core.bus.ppu.frame_index, offset
                );
                prev[index] = value;
                prev_frame = core.bus.ppu.frame_index;
            }
        }
        if trace_timers {
            for index in 0..4 {
                let reload = core.bus.timer_reload[index];
                if reload != prev_reload[index] {
                    println!(
                        "frame={} step={steps} pc={pc:08x} timer{index}_reload={reload:04x}",
                        core.bus.ppu.frame_index
                    );
                    prev_reload[index] = reload;
                }
                let control = core.bus.timer_control[index];
                if control != prev_control[index] {
                    println!(
                        "frame={} step={steps} pc={pc:08x} timer{index}_control={control:04x}",
                        core.bus.ppu.frame_index
                    );
                    prev_control[index] = control;
                }
            }
        }
        if trace_dma {
            for index in 0..4 {
                let state = (
                    core.bus.dma_sad[index],
                    core.bus.dma_dad[index],
                    core.bus.dma_cnt_l[index],
                    core.bus.dma_cnt_h[index],
                    core.bus.dma_count[index],
                    core.bus.dma_source[index],
                    core.bus.dma_dest[index],
                );
                if state != prev_dma[index] {
                    println!(
                        "frame={} step={steps} pc={pc:08x} dma{index} sad={:08x} dad={:08x} cnt_l={:04x} cnt_h={:04x} count={} src={:08x} dst={:08x}",
                        core.bus.ppu.frame_index,
                        state.0, state.1, state.2, state.3, state.4, state.5, state.6
                    );
                    prev_dma[index] = state;
                }
            }
        }
        let _ = prev_frame;
    }
    println!("done frames={} steps={steps}", core.bus.ppu.frame_index);
}
