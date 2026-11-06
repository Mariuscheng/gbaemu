//! 診斷用：逐步跑 Core，追蹤 IRQ 進場／CPSR I 變化／指定 memory watch。
//!
//! 用法：
//!   cargo run --bin trace_probe -- rom.gba --frames 120
//!   cargo run --bin trace_probe -- rom.gba --steps 2000000 --watch 02006654

use gbaemu_core::{Core, CoreConfig};

fn main() {
    let mut args = std::env::args().skip(1);
    let mut path = None;
    let mut max_frames = 120u64;
    let mut max_steps = u64::MAX;
    let mut watch = 0x0200_6654u32;
    let mut render = true;
    while let Some(arg) = args.next() {
        match arg.as_str() {
            "--frames" => max_frames = args.next().and_then(|v| v.parse().ok()).unwrap_or(120),
            "--steps" => max_steps = args.next().and_then(|v| v.parse().ok()).unwrap_or(u64::MAX),
            "--norender" => render = false,
            "--watch" => {
                watch = args
                    .next()
                    .and_then(|v| u32::from_str_radix(&v, 16).ok())
                    .unwrap_or(0x0200_6654)
            }
            other => path = Some(other.to_string()),
        }
    }
    let path = path.expect("需要 ROM 路徑");
    let rom = std::fs::read(&path).expect("read rom");
    let mut core = Core::new(
        rom,
        CoreConfig {
            render,
            ..CoreConfig::default()
        },
    )
    .expect("core");

    let mut steps = 0u64;
    let mut last_mode = core.cpu.cpsr & 0x1F;
    let mut last_i = core.cpu.cpsr & 0x80 != 0;
    let mut last_if = core.bus.if_;
    let mut last_watch = read16(&mut core, watch);
    let mut irq_entries = 0u32;
    let mut ring: Vec<(u64, u32, u32, u16)> = Vec::new();

    while steps < max_steps {
        let pc = core.cpu.regs[15];
        let cpsr = core.cpu.cpsr;
        let if_before = core.bus.if_;
        if let Err(error) = core.step() {
            eprintln!("step {steps} 停止：{error:?} pc={pc:08x} cpsr={cpsr:08x}");
            break;
        }
        steps += 1;
        let mode = core.cpu.cpsr & 0x1F;
        let i_bit = core.cpu.cpsr & 0x80 != 0;
        if mode == 0x12 && last_mode != 0x12 {
            irq_entries += 1;
            if irq_entries <= 12 {
                println!(
                    "IRQ #{irq_entries} enter: step={steps} pc={pc:08x} if={if_before:04x} -> {:#06x} lr={:08x}",
                    core.bus.if_, core.cpu.regs[14]
                );
            }
        }
        if i_bit != last_i {
            println!(
                "I bit {last_i} -> {i_bit}: step={steps} pc={pc:08x} cpsr={:08x} mode={mode:02x}",
                core.cpu.cpsr
            );
        }
        if core.bus.if_ != last_if {
            println!(
                "IF {last_if:04x} -> {:04x}: step={steps} pc={pc:08x} mode={mode:02x}",
                core.bus.if_
            );
            last_if = core.bus.if_;
        }
        let watch_value = read16(&mut core, watch);
        if watch_value != last_watch {
            println!(
                "watch[{watch:08x}] {last_watch:04x} -> {watch_value:04x}: step={steps} pc={pc:08x} mode={mode:02x}"
            );
            last_watch = watch_value;
        }
        last_mode = mode;
        last_i = i_bit;
        ring.push((steps, pc, core.cpu.cpsr, core.bus.if_));
        if ring.len() > 40 {
            ring.remove(0);
        }
        if steps % 1_000_000 == 0 {
            eprintln!(
                "step={steps} frames={} cycles={} pc={:08x} pal_writes={} pal_last={:08x}",
                core.bus.ppu.frame_index,
                core.cycles,
                core.cpu.regs[15],
                core.bus.pal_writes,
                core.bus.pal_last
            );
        }
        if core.bus.ppu.frame_index >= max_frames {
            break;
        }
    }
    println!("steps={steps} frames={} irq_entries={irq_entries}", core.bus.ppu.frame_index);
    println!("last 40 instructions:");
    for (step, pc, cpsr, if_) in ring {
        println!("  step={step:8} pc={pc:08x} cpsr={cpsr:08x} if={if_:04x}");
    }
}

fn read16(core: &mut Core, address: u32) -> u16 {
    core.bus.read16(address)
}
