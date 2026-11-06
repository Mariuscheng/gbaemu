//! CPU differential probe：讓 Python reference 用同一組指令／狀態驅動 Rust CPU。
//!
//! 這不是正式 backend；只是 G1 的 test harness。輸出格式刻意保持簡單，
//! 由 `tools/rust_cpu_diff.py` 解析。

use std::io::{self, BufRead, Write};

use gbaemu_core::{Bus, Cpu, CpuError};

fn new_machine() -> (Bus, Cpu) {
    let mut rom = vec![0u8; 0x4000];
    rom[0xB2] = 0x96;
    let bus = Bus::new(rom).expect("synthetic ROM");
    let mut cpu = Cpu::new();
    cpu.cpsr = 0x1F; // SYS mode，ARM
    (bus, cpu)
}

fn format_state(cpu: &Cpu) -> String {
    let regs = cpu
        .regs
        .iter()
        .map(|v| format!("{v:08x}"))
        .collect::<Vec<_>>()
        .join(",");
    format!(
        "ok pc={:08x} cpsr={:08x} spsr={:08x} cycles={} halted={} regs={}",
        cpu.regs[15], cpu.cpsr, cpu.spsr, cpu.cycles, u8::from(cpu.halted), regs
    )
}

fn main() {
    let stdin = io::stdin();
    let mut stdout = io::BufWriter::new(io::stdout());
    let (mut bus, mut cpu) = new_machine();
    for line in stdin.lock().lines() {
        let line = match line {
            Ok(line) => line,
            Err(_) => break,
        };
        let mut parts = line.split_whitespace();
        let Some(command) = parts.next() else { continue };
        let result = match command {
            "reset" => {
                let (new_bus, new_cpu) = new_machine();
                bus = new_bus;
                cpu = new_cpu;
                Ok("ok".to_string())
            }
            "reg" => {
                let index = parts.next().and_then(|v| v.parse::<usize>().ok());
                let value = parts.next().and_then(|v| u32::from_str_radix(v, 16).ok());
                match (index, value) {
                    (Some(index), Some(value)) if index < 16 => {
                        cpu.regs[index] = value;
                        Ok("ok".to_string())
                    }
                    _ => Err("bad reg".to_string()),
                }
            }
            "cpsr" | "spsr" => {
                let value = parts.next().and_then(|v| u32::from_str_radix(v, 16).ok());
                match value {
                    Some(value) if command == "cpsr" => {
                        cpu.cpsr = value;
                        Ok("ok".to_string())
                    }
                    Some(value) => {
                        cpu.spsr = value;
                        Ok("ok".to_string())
                    }
                    None => Err("bad register".to_string()),
                }
            }
            "keyinput" => {
                let value = parts.next().and_then(|v| u16::from_str_radix(v, 16).ok());
                match value {
                    Some(value) => {
                        bus.keyinput = value & 0x03FF;
                        Ok("ok".to_string())
                    }
                    None => Err("bad keyinput".to_string()),
                }
            }
            "romfile" => {
                let path = parts.next();
                match path.and_then(|path| std::fs::read(path).ok()) {
                    Some(rom) => match Bus::new(rom) {
                        Ok(new_bus) => {
                            bus = new_bus;
                            cpu = Cpu::new();
                            Ok("ok".to_string())
                        }
                        Err(error) => Err(format!("rom failed: {error:?}")),
                    },
                    None => Err("bad romfile".to_string()),
                }
            }
            "postboot" => {
                cpu.apply_post_boot();
                bus.apply_post_boot();
                Ok("ok".to_string())
            }
            "pc" => Ok(format!("ok value={:08x}", cpu.regs[15])),
            "soundon" => {
                let value = parts.next().and_then(|v| v.parse::<u8>().ok());
                match value {
                    Some(value) => {
                        bus.sound_enabled = value != 0;
                        Ok("ok".to_string())
                    }
                    None => Err("bad soundon".to_string()),
                }
            }
            "takeaudio" => Ok(format!("ok hex={}", bus.take_pcm().iter().map(|byte| format!("{byte:02x}")).collect::<String>())),
            "fifostate" => Ok(format!(
                "ok a={} b={} src1={:08x} src2={:08x}",
                bus.sound_fifo_a.len(),
                bus.sound_fifo_b.len(),
                bus.dma_source[1],
                bus.dma_source[2]
            )),
            "pollkeys" => {
                bus.poll_keypad();
                Ok("ok".to_string())
            }
            "tick" => {
                let cycles = parts.next().and_then(|v| v.parse::<u32>().ok());
                match cycles {
                    Some(cycles) => {
                        bus.tick(cycles);
                        Ok("ok".to_string())
                    }
                    None => Err("bad tick".to_string()),
                }
            }
            "dmaservice" => {
                let cycles = bus.service_dma();
                Ok(format!("ok cycles={cycles}"))
            }
            "ifset" => {
                let value = parts.next().and_then(|v| u16::from_str_radix(v, 16).ok());
                match value {
                    Some(value) => {
                        bus.if_ |= value & 0x3FFF;
                        Ok("ok".to_string())
                    }
                    None => Err("bad ifset".to_string()),
                }
            }
            "vrammode" => {
                let value = parts.next().and_then(|v| v.parse::<u8>().ok());
                match value {
                    Some(value) => {
                        bus.set_vram_bitmap_mode(value != 0);
                        Ok("ok".to_string())
                    }
                    None => Err("bad vrammode".to_string()),
                }
            }
            "romfill" => {
                for (index, byte) in bus.rom.iter_mut().enumerate() {
                    *byte = (index as u32 * 7 + 3) as u8;
                }
                Ok("ok".to_string())
            }
            "rom32" => {
                let offset = parts.next().and_then(|v| usize::from_str_radix(v, 16).ok());
                let value = parts.next().and_then(|v| u32::from_str_radix(v, 16).ok());
                match (offset, value) {
                    (Some(offset), Some(value)) if offset + 4 <= bus.rom.len() => {
                        bus.rom[offset..offset + 4].copy_from_slice(&value.to_le_bytes());
                        Ok("ok".to_string())
                    }
                    _ => Err("bad rom32".to_string()),
                }
            }
            "rom16" => {
                let offset = parts.next().and_then(|v| usize::from_str_radix(v, 16).ok());
                let value = parts.next().and_then(|v| u16::from_str_radix(v, 16).ok());
                match (offset, value) {
                    (Some(offset), Some(value)) if offset + 2 <= bus.rom.len() => {
                        bus.rom[offset..offset + 2].copy_from_slice(&value.to_le_bytes());
                        Ok("ok".to_string())
                    }
                    _ => Err("bad rom16".to_string()),
                }
            }
            "openbus" => {
                let value = parts.next().and_then(|v| u32::from_str_radix(v, 16).ok());
                match value {
                    Some(value) => {
                        bus.open_bus = value;
                        Ok("ok".to_string())
                    }
                    None => Err("bad openbus".to_string()),
                }
            }
            "mem8" | "mem16" | "mem32" => {
                let address = parts.next().and_then(|v| u32::from_str_radix(v, 16).ok());
                let value = parts.next().and_then(|v| u32::from_str_radix(v, 16).ok());
                match (address, value) {
                    (Some(address), Some(value)) if command == "mem8" => {
                        bus.write8(address, value as u8);
                        Ok("ok".to_string())
                    }
                    (Some(address), Some(value)) if command == "mem16" => {
                        bus.write16(address, value as u16);
                        Ok("ok".to_string())
                    }
                    (Some(address), Some(value)) => {
                        bus.write32(address, value);
                        Ok("ok".to_string())
                    }
                    _ => Err("bad mem".to_string()),
                }
            }
            "peek8" | "peek16" | "peek32" => {
                let address = parts.next().and_then(|v| u32::from_str_radix(v, 16).ok());
                match address {
                    Some(address) if command == "peek8" => {
                        Ok(format!("ok value={:02x}", bus.read8(address)))
                    }
                    Some(address) if command == "peek16" => {
                        Ok(format!("ok value={:04x}", bus.read16(address)))
                    }
                    Some(address) => Ok(format!("ok value={:08x}", bus.read32(address))),
                    None => Err("bad peek".to_string()),
                }
            }
            "exception" => {
                let mode = parts.next().and_then(|v| u32::from_str_radix(v, 16).ok());
                let vector = parts.next().and_then(|v| u32::from_str_radix(v, 16).ok());
                let lr = parts.next().and_then(|v| u32::from_str_radix(v, 16).ok());
                match (mode, vector, lr) {
                    (Some(mode), Some(vector), Some(lr)) => {
                        cpu.enter_exception(mode, vector, lr);
                        Ok(format_state(&cpu))
                    }
                    _ => Err("bad exception".to_string()),
                }
            }
            "irq" => {
                let next = parts.next().and_then(|v| u32::from_str_radix(v, 16).ok());
                match next {
                    Some(next) => {
                        cpu.enter_irq(next);
                        Ok(format_state(&cpu))
                    }
                    None => Err("bad irq".to_string()),
                }
            }
            "waitcnt" => {
                let value = parts.next().and_then(|v| u16::from_str_radix(v, 16).ok());
                match value {
                    Some(value) => {
                        bus.set_waitcnt(value);
                        Ok("ok".to_string())
                    }
                    None => Err("bad waitcnt".to_string()),
                }
            }
            "cost" => {
                let address = parts.next().and_then(|v| u32::from_str_radix(v, 16).ok());
                let width = parts.next().and_then(|v| v.parse::<u32>().ok());
                let sequential = parts.next().map(|v| v == "1");
                match (address, width, sequential) {
                    (Some(address), Some(width), Some(sequential))
                        if width == 1 || width == 2 || width == 4 => Ok(format!(
                            "ok cost={}",
                            bus.access_cost(address, width, sequential)
                        )),
                    _ => Err("bad cost".to_string()),
                }
            }
            "functional" => {
                let value = parts.next().map(|v| v == "1");
                match value {
                    Some(value) => {
                        bus.functional = value;
                        Ok("ok".to_string())
                    }
                    None => Err("bad functional".to_string()),
                }
            }
            "mgba" => {
                bus.mgba_timing = parts.next() == Some("1");
                Ok("ok".to_string())
            }
            "cycles" => {
                let instr = parts.next().and_then(|v| u32::from_str_radix(v, 16).ok());
                match instr {
                    Some(instr) => {
                        let pc = cpu.regs[15];
                        let cost = if cpu.thumb() {
                            cpu.thumb_cycles(&mut bus, pc & !1, instr)
                        } else {
                            cpu.arm_cycles(&mut bus, pc & !3, instr)
                        };
                        Ok(format!("ok cost={cost}"))
                    }
                    None => Err("bad cycles".to_string()),
                }
            }
            "step" => match cpu.step(&mut bus) {
                Ok(_) => Ok(format_state(&cpu)),
                Err(CpuError::Swi { pc, number }) => {
                    Err(format!("swi pc={pc:08x} number={number:02x}"))
                }
                Err(error) => Err(format!("error {error:?}")),
            },
            "dump" => Ok(format_state(&cpu)),
            "quit" => break,
            _ => Err(format!("unknown command {command}")),
        };
        match result {
            Ok(line) => {
                let _ = writeln!(stdout, "{line}");
            }
            Err(line) => {
                let _ = writeln!(stdout, "err {line}");
            }
        }
        let _ = stdout.flush();
    }
}
