//! 診斷用：跑 suite.gba 其中一個 suite，統計 pass／fail 並 dump SRAM log。
//!
//! 用法：
//!   cargo run --release --bin suite_probe -- rom/suite.gba
//!   cargo run --release --bin suite_probe -- rom/suite.gba --suite 1
//!   cargo run --release --bin suite_probe -- rom/suite.gba --suite 1 --frames 300
//!
//! suite 的 `savprintf()` 會把 "Got 0x.... vs 0x....: FAIL" 追寫到 SRAM，
//! 所以完跑之後直接 dump SRAM 就知每個 case 的實際／期望值。

use gbaemu_core::{Core, CoreConfig};

const BIOS_PATH: &str = "rom/bios/gba_bios.bin";

/// 與 main.c 的 `suites[]` 順序一致。
const SUITE_NAMES: [&str; 14] = [
    "Memory tests",
    "I/O read tests",
    "Timing tests",
    "Timer count-up tests",
    "Timer IRQ tests",
    "Shifter tests",
    "Carry tests",
    "Multiply long tests",
    "BIOS math tests",
    "DMA tests",
    "SIO register R/W tests",
    "SIO timing tests",
    "Misc. edge case tests",
    "Video tests",
];

fn read_u32(rom: &[u8], address: u32) -> u32 {
    let offset = (address - 0x0800_0000) as usize;
    u32::from_le_bytes(rom[offset..offset + 4].try_into().unwrap())
}

/// 由 suite 名稱字串找回 `struct TestSuite` 在 ROM 的位置。
fn find_suite(rom: &[u8], name: &str) -> Option<u32> {
    let needle = format!("{name}\0");
    let position = rom
        .windows(needle.len())
        .position(|window| window == needle.as_bytes())?;
    let name_address = 0x0800_0000 + position as u32;
    let pattern = name_address.to_le_bytes();
    let mut cursor = 0usize;
    while let Some(found) = rom[cursor..]
        .windows(4)
        .position(|window| window == pattern)
    {
        let candidate = 0x0800_0000 + (cursor + found) as u32;
        let run = read_u32(rom, candidate + 0x04);
        let n_tests = read_u32(rom, candidate + 0x10);
        let passes = read_u32(rom, candidate + 0x14);
        let total = read_u32(rom, candidate + 0x18);
        if (1..=5000).contains(&n_tests)
            && passes != 0
            && total != 0
            && (run == 0 || (0x0800_0000..0x0A00_0000).contains(&run))
        {
            return Some(candidate);
        }
        cursor += found + 1;
    }
    None
}

fn press(core: &mut Core, keyinput: u16, frames: u32) {
    core.bus.keyinput = keyinput;
    for _ in 0..frames {
        core.run_frame().unwrap();
    }
    core.bus.keyinput = 0x03FF;
}

fn main() {
    let args: Vec<String> = std::env::args().collect();
    let mut path = "rom/suite.gba".to_string();
    let mut suite_index = 0usize;
    let mut max_frames = 900usize;
    // 預設用 timed（真實 cycle cost）；suite 嘅 timing 測試要有 waitstate／
    // prefetch 才有意義，--functional 可以退回舊嘅近似模式。
    let mut timed = true;
    // 預設 mGBA accounting；--legacy 退回舊 model 做 A/B。
    let mut legacy_timing = false;
    let mut refill_timing = false;
    let mut index = 1;
    while index < args.len() {
        match args[index].as_str() {
            "--suite" => {
                suite_index = args[index + 1].parse().expect("--suite 需要數字");
                index += 2;
            }
            "--frames" => {
                max_frames = args[index + 1].parse().expect("--frames 需要數字");
                index += 2;
            }
            "--timed" => {
                timed = true;
                index += 1;
            }
            "--functional" => {
                timed = false;
                index += 1;
            }
            "--mgba" => {
                legacy_timing = false;
                index += 1;
            }
            "--legacy" => {
                legacy_timing = true;
                index += 1;
            }
            "--refill" => {
                refill_timing = true;
                index += 1;
            }
            other => {
                path = other.to_string();
                index += 1;
            }
        }
    }

    let rom = std::fs::read(&path).expect("read rom");
    let mut config = CoreConfig::default();
    config.timing_model = if legacy_timing {
        gbaemu_core::TimingModel::Legacy
    } else {
        gbaemu_core::TimingModel::Mgba
    };
    let mut core = Core::new(rom.clone(), config).expect("core");
    core.bus.functional = !timed;
    core.bus.refill_timing = refill_timing;
    if let Ok(bios) = std::fs::read(BIOS_PATH) {
        core.load_bios(&bios);
    }

    let name = SUITE_NAMES[suite_index];
    let suite = find_suite(&rom, name).unwrap_or_else(|| panic!("找唔到 suite struct: {name}"));
    let run_pointer = read_u32(&rom, suite + 0x04);
    let n_tests = read_u32(&rom, suite + 0x10) as u32;
    let passes_pointer = read_u32(&rom, suite + 0x14);
    let total_pointer = read_u32(&rom, suite + 0x18);
    if run_pointer == 0 {
        println!("suite={name} 係互動式（run=NULL），probe 唔跑。");
        return;
    }

    eprintln!(
        "debug: suite_struct={suite:#010X} nTests={n_tests} passes_ptr={passes_pointer:#010X} total_ptr={total_pointer:#010X}"
    );

    // 開機 → 主選單 → 選 suite → A 開始跑。
    for _ in 0..120 {
        core.run_frame().unwrap();
    }
    for _ in 0..suite_index {
        press(&mut core, 0x037F, 1); // DOWN（active low）
        press(&mut core, 0x03FF, 12);
    }
    press(&mut core, 0x03FE, 1); // A
    press(&mut core, 0x03FF, 12);

    // `totalResults` 係「檢查數」唔係「test 數」（Memory tests 36 個 test、
    // 但 1552 個檢查）；亦有些 suite 一 frame 內跑完，無機會觀察 testId。
    // 所以用「totalResults 連續幾 frame 唔變」判斷跑完。
    let mut frames = 0;
    let mut last_total = 0u32;
    let mut stable = 0;
    while frames < max_frames {
        core.run_frame().unwrap();
        frames += 1;
        let total = core.bus.read32(total_pointer);
        if total > 0 && total == last_total {
            stable += 1;
            if stable >= 3 {
                break;
            }
        } else {
            stable = 0;
        }
        last_total = total;
    }

    let passes = core.bus.read32(passes_pointer);
    let total = core.bus.read32(total_pointer);
    println!("suite={name} frames={frames} passes={passes} total={total} expected={n_tests}");
    if total < n_tests {
        eprintln!("警告：suite 未跑完（total {total} < {n_tests}）");
    }

    let log: String = core
        .bus
        .sram
        .iter()
        .take_while(|&&byte| byte != 0)
        .map(|&byte| byte as char)
        .collect();
    println!("---- SRAM log ----");
    for line in log.lines() {
        println!("{line}");
    }
}
