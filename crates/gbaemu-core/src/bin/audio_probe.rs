//! 診斷用：跑 ROM、輸出 WAV、逐 frame 印 DMA Sound FIFO 統計與爆音位置。
//!
//! 用法：
//!   cargo run --release --bin audio_probe -- rom.gba --frames 300 --wav out.wav
//!   cargo run --release --bin audio_probe -- rom.gba --frames 300 --detail 1450,1520

use gbaemu_core::{Core, CoreConfig};

fn main() {
    let mut args = std::env::args().skip(1);
    let mut path = None;
    let mut frames = 300u64;
    let mut wav_path: Option<String> = None;
    let mut detail: Vec<usize> = Vec::new();
    let mut functional = false;
    while let Some(arg) = args.next() {
        match arg.as_str() {
            "--frames" => frames = args.next().and_then(|v| v.parse().ok()).unwrap_or(300),
            "--functional" => functional = true,
            "--wav" => wav_path = args.next(),
            "--detail" => {
                let value = args.next().unwrap_or_default();
                detail = value
                    .split(',')
                    .filter_map(|part| part.trim().parse().ok())
                    .collect();
            }
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
            functional,
            ..CoreConfig::default()
        },
    )
    .expect("core");
    core.bus.sound_debug = true;
    core.bus.sound.debug = true;

    let mut pcm: Vec<u8> = Vec::new();
    let mut all: Vec<(i16, i16)> = Vec::new();
    let mut last_pops = 0u64;
    let mut last_empty = 0u64;
    for frame in 0..frames {
        match core.run_frame() {
            Ok(_) => {}
            Err(error) => {
                println!("frame={frame} emulation error {error:?}");
                break;
            }
        }
        let chunk = core.bus.take_pcm();
        pcm.extend_from_slice(&chunk);
        for pair in chunk.chunks_exact(4) {
            let left = i16::from_le_bytes([pair[0], pair[1]]);
            let right = i16::from_le_bytes([pair[2], pair[3]]);
            all.push((left, right));
        }
        let pops = core.bus.sound.fifo_pops;
        let empty = core.bus.sound.fifo_empty;
        println!(
            "frame={frame} pcm_bytes={} samples={} pops={} (+{}) empty={} (+{}) ds_a={} ds_b={}",
            chunk.len(),
            all.len(),
            pops,
            pops - last_pops,
            empty,
            empty - last_empty,
            core.bus.sound.ds_a,
            core.bus.sound.ds_b,
        );
        last_pops = pops;
        last_empty = empty;
    }

    // 爆音偵測：相鄰 sample 跳動 > 4000（滿刻度 10240）。
    let mut jumps = 0u32;
    for index in 1..all.len() {
        let delta = (all[index].0 as i32 - all[index - 1].0 as i32).abs();
        if delta > 4000 {
            jumps += 1;
            if jumps <= 20 {
                println!("jump at sample {index} delta={delta} prev={} now={}", all[index - 1].0, all[index].0);
            }
        }
    }
    println!("total samples={} jumps={jumps}", all.len());
    {
        let log = &core.bus.dma_write_log;
        let from = log.partition_point(|entry| entry.0 < 1800u64).min(log.len());
        let to = (from + 40).min(log.len());
        println!("  dma writes count={}", log.len());
        for entry in log.iter().take(60) {
            println!("    sample={} offset={:#05x} value={:#010x}", entry.0, entry.1, entry.2);
        }
    }

    for &start in &detail {
        let end = (start + 40).min(all.len());
        if start < all.len() {
            println!(
                "detail {start}..{end}: {:?}",
                all[start..end].iter().map(|pair| pair.0).collect::<Vec<_>>()
            );
            let log = &core.bus.sound_debug_log;
            let from = log.partition_point(|entry| entry.0 < start as u64).saturating_sub(4);
            let to = log.partition_point(|entry| entry.0 < end as u64).max(from + 1).min(log.len());
            println!("  bus debug (samples, master, fifo_a, ds_a, ds_b): {:?}", &log[from..to]);
            let pops = &core.bus.pop_debug;
            let pf = pops.partition_point(|entry| entry.0 < start as u64).saturating_sub(2);
            let pt = pops.partition_point(|entry| entry.0 < end as u64).max(pf + 1).min(pops.len());
            println!(
                "  pops (samples, ds_a, dma1_src, fifo, dma1_sad): {:?}",
                &pops[pf..pt.min(pf + 12)]
            );
        }
    }

    if let Some(wav_path) = wav_path {
        write_wav(&wav_path, &pcm);
        println!("wav={wav_path} bytes={}", pcm.len());
    }
}

fn write_wav(path: &str, pcm: &[u8]) {
    let mut out = Vec::with_capacity(44 + pcm.len());
    out.extend_from_slice(b"RIFF");
    out.extend_from_slice(&((36 + pcm.len()) as u32).to_le_bytes());
    out.extend_from_slice(b"WAVEfmt ");
    out.extend_from_slice(&16u32.to_le_bytes());
    out.extend_from_slice(&1u16.to_le_bytes());
    out.extend_from_slice(&2u16.to_le_bytes());
    out.extend_from_slice(&32768u32.to_le_bytes());
    out.extend_from_slice(&(32768u32 * 4).to_le_bytes());
    out.extend_from_slice(&4u16.to_le_bytes());
    out.extend_from_slice(&16u16.to_le_bytes());
    out.extend_from_slice(b"data");
    out.extend_from_slice(&(pcm.len() as u32).to_le_bytes());
    out.extend_from_slice(pcm);
    std::fs::write(path, out).expect("write wav");
}
