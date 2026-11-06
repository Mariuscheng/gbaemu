//! 診斷用：逐 step 監看 IF/IE/IME 與 IRQ 進場，找出「timer IRQ 被吃掉」。
//!
//! 用法：cargo run --release --bin irq_probe -- rom.gba --frames 20

use gbaemu_core::{Core, CoreConfig};

fn main() {
    let mut args = std::env::args().skip(1);
    let mut path = None;
    let mut frames = 20u64;
    while let Some(arg) = args.next() {
        match arg.as_str() {
            "--frames" => frames = args.next().and_then(|v| v.parse().ok()).unwrap_or(20),
            other => path = Some(other.to_string()),
        }
    }
    let path = path.expect("需要 ROM 路徑");
    let rom = std::fs::read(&path).expect("read rom");
    let mut core = Core::new(
        rom,
        CoreConfig {
            render: false,
            sound: true,
            ..CoreConfig::default()
        },
    )
    .expect("core");

    let mut last_if = core.bus.if_;
    let mut last_ime = core.bus.ime;
    let mut steps = 0u64;
    let mut follow = 0;
    while core.bus.ppu.frame_index < frames {
        let pc = core.cpu.regs[15];
        let mode_before = core.cpu.cpsr & 0x1F;
        let samples = core.bus.sound.samples;
        if let Err(error) = core.step() {
            println!("error {error:?}");
            break;
        }
        steps += 1;
        let mode_after = core.cpu.cpsr & 0x1F;
        if core.bus.if_ != last_if {
            println!(
                "frame={} samples={} step={steps} IF {:04x} -> {:04x} pc={pc:08x} ie={:04x} ime={}",
                core.bus.ppu.frame_index,
                samples,
                last_if,
                core.bus.if_,
                core.bus.ie,
                core.bus.ime as u8
            );
            last_if = core.bus.if_;
        }
        if core.bus.ime != last_ime {
            println!(
                "frame={} samples={} step={steps} IME {} -> {} pc={pc:08x}",
                core.bus.ppu.frame_index,
                samples,
                last_ime as u8,
                core.bus.ime as u8
            );
            last_ime = core.bus.ime;
        }
        if mode_after == 0x12 && mode_before != 0x12 {
            println!(
                "frame={} samples={} step={steps} IRQ enter pc={pc:08x} if={:04x} ie={:04x} lr={:08x}",
                core.bus.ppu.frame_index,
                samples,
                core.bus.if_,
                core.bus.ie,
                core.cpu.regs[14]
            );
            if follow < 2 && samples > 1900 {
                follow += 1;
                println!("  follow #{} from if={:04x}", follow, core.bus.if_);
                let mut pcs = Vec::new();
                for _ in 0..80 {
                    if core.step().is_err() { break; }
                    pcs.push(core.cpu.regs[15]);
                    if pcs.len() <= 10 {
                        println!("    pc={:08x} cpsr={:08x} halted={} r0={:08x} r2={:08x} ip={:08x} ie={:04x} if={:04x}",
                            core.cpu.regs[15], core.cpu.cpsr, core.cpu.halted as u8, core.cpu.regs[0],
                            core.cpu.regs[2], core.cpu.regs[12], core.bus.ie, core.bus.if_);
                    }
                }
                println!("  pcs: {:?}", pcs.iter().map(|p| format!("{p:08x}")).collect::<Vec<_>>());
            }
        }
    }
    println!("done frames={} steps={steps}", core.bus.ppu.frame_index);
}
