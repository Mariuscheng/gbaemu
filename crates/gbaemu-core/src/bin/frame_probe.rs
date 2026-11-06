//! Framebuffer differential probe：Python reference vs Rust `Core` renderer。
//!
//! 這不是 production backend；只用固定 VRAM／IO 狀態比較 RGB888 framebuffer。

use std::io::{self, BufRead, Write};

use gbaemu_core::{sha256, Core, CoreConfig};

fn parse_digest(text: &str) -> Option<[u8; 32]> {
    if text.len() != 64 {
        return None;
    }
    let mut digest = [0u8; 32];
    for (index, byte) in digest.iter_mut().enumerate() {
        *byte = u8::from_str_radix(&text[index * 2..index * 2 + 2], 16).ok()?;
    }
    Some(digest)
}

fn new_core() -> Core {
    let mut rom = vec![0u8; 0x4000];
    rom[0xB2] = 0x96;
    Core::new(rom, CoreConfig::default()).expect("synthetic ROM")
}

fn hash_bytes(data: &[u8]) -> u64 {
    let mut hash = 0xcbf2_9ce4_8422_2325u64;
    for byte in data {
        hash ^= *byte as u64;
        hash = hash.wrapping_mul(0x0000_0100_0000_01B3);
    }
    hash
}

fn main() {
    let stdin = io::stdin();
    let mut stdout = io::BufWriter::new(io::stdout());
    let mut core = new_core();
    let mut config_sha = [0u8; 32];
    for line in stdin.lock().lines() {
        let line = match line {
            Ok(line) => line,
            Err(_) => break,
        };
        let mut parts = line.split_whitespace();
        let Some(command) = parts.next() else { continue };
        let result = match command {
            "reset" => {
                core = new_core();
                Ok("ok".to_string())
            }
            "write8" | "write16" | "write32" => {
                let address = parts.next().and_then(|v| u32::from_str_radix(v, 16).ok());
                let value = parts.next().and_then(|v| u32::from_str_radix(v, 16).ok());
                match (address, value) {
                    (Some(address), Some(value)) if command == "write8" => {
                        core.bus.write8(address, value as u8);
                        Ok("ok".to_string())
                    }
                    (Some(address), Some(value)) if command == "write16" => {
                        core.bus.write16(address, value as u16);
                        Ok("ok".to_string())
                    }
                    (Some(address), Some(value)) => {
                        core.bus.write32(address, value);
                        Ok("ok".to_string())
                    }
                    _ => Err("bad write".to_string()),
                }
            }
            "fillvram" | "fillpalette" | "filloam" => {
                let target: &mut [u8] = match command {
                    "fillvram" => &mut core.bus.vram,
                    "fillpalette" => &mut core.bus.palette,
                    _ => &mut core.bus.oam,
                };
                for (index, byte) in target.iter_mut().enumerate() {
                    *byte = (index as u32 * 37 + 11) as u8;
                }
                Ok("ok".to_string())
            }
            "romfile" => {
                let path = parts.next();
                match path.and_then(|path| std::fs::read(path).ok()) {
                    Some(rom) => {
                        let config = core.config();
                        match Core::new(rom, config) {
                            Ok(new_core) => {
                                core = new_core;
                                Ok("ok".to_string())
                            }
                            Err(error) => Err(format!("rom failed: {error:?}")),
                        }
                    }
                    None => Err("bad romfile".to_string()),
                }
            }
            "configsha" => match parts.next().and_then(parse_digest) {
                Some(digest) => {
                    config_sha = digest;
                    Ok("ok".to_string())
                }
                None => Err("bad configsha".to_string()),
            },
            "savestate" => {
                let path = parts.next();
                match path {
                    Some(path) => {
                        let snapshot = core.save_state_with_hashes(sha256(&core.bus.rom), config_sha);
                        match std::fs::write(path, snapshot) {
                            Ok(()) => Ok("ok".to_string()),
                            Err(error) => Err(format!("write failed: {error}")),
                        }
                    }
                    None => Err("bad savestate".to_string()),
                }
            }
            "loadstate" => {
                let path = parts.next();
                match path.and_then(|path| std::fs::read(path).ok()) {
                    Some(data) => match core.load_state(&data) {
                        Ok(()) => Ok("ok".to_string()),
                        Err(error) => Err(format!("load failed: {error:?}")),
                    },
                    None => Err("bad loadstate".to_string()),
                }
            }
            "runframe" => match core.run_frame() {
                Ok(frame) => Ok(format!("ok cycles={}", frame.cycles)),
                Err(error) => Err(format!("err {error:?}")),
            },
            // 不推進 CPU，用目前 VRAM／IO／OAM 直接重畫整張 frame。
            "render" => {
                core.render_now();
                Ok("ok".to_string())
            }
            "hash" => Ok(format!("ok value={:016x}", hash_bytes(core.framebuffer()))),
            "pixel" => {
                let x = parts.next().and_then(|v| v.parse::<u32>().ok());
                let y = parts.next().and_then(|v| v.parse::<u32>().ok());
                match (x, y) {
                    (Some(x), Some(y)) if x < 240 && y < 160 => {
                        let index = ((y * 240 + x) * 3) as usize;
                        let frame = core.framebuffer();
                        Ok(format!(
                            "ok value={:02x}{:02x}{:02x}",
                            frame[index], frame[index + 1], frame[index + 2]
                        ))
                    }
                    _ => Err("bad pixel".to_string()),
                }
            }
            "quit" => {
                let _ = writeln!(stdout, "ok");
                break;
            }
            _ => Err(format!("unknown command {command}")),
        };
        match result {
            Ok(output) => {
                let _ = writeln!(stdout, "{output}");
            }
            Err(error) => {
                let _ = writeln!(stdout, "err {error}");
            }
        }
        let _ = stdout.flush();
    }
}
