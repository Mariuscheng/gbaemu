"""Real-ROM smoke：Python reference vs Rust native parity + throughput。

用法（repo root）：

    .\\venv\\Scripts\\python.exe tools\\smoke_real_rom.py --rom rom/Dr_Mario.gba --frames 120
    .\\venv\\Scripts\\python.exe tools\\smoke_real_rom.py --roms-dir "D:\\python\\gbaemu-lab\\rom" --frames 30
    .\\venv\\Scripts\\python.exe tools\\smoke_real_rom.py --roms-dir ... --frames 30 --json

`--roms-dir` 會掃描目錄下所有 `*.gba`，逐支比較 framebuffer、CPU cycles
同（可選）音訊長度；任何一支唔 match 都會以 exit code 1 結束，方便 CI。
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

from gbaemu import AudioMode, Emulator, EmulatorConfig, NativeEmulator


def fnv1a(data: bytes) -> int:
    value = 0xCBF29CE484222325
    for byte in data:
        value ^= byte
        value = (value * 0x100000001B3) & 0xFFFFFFFFFFFFFFFF
    return value


def run_python(rom: Path, frames: int, *, audio: bool) -> tuple[bytes, float, int, bytes]:
    config = EmulatorConfig(audio=AudioMode.BUFFERED if audio else AudioMode.DISABLED)
    emu = Emulator.from_rom(rom, config=config)
    try:
        start = time.perf_counter()
        for _ in range(frames):
            emu.step_frame(render=True)
        elapsed = time.perf_counter() - start
        frame = emu._framebuffer.read_frame()
        pcm = emu.audio.read_buffer() if audio else b""
        return frame, elapsed, emu.cycles, pcm
    finally:
        emu.close()


def run_native(rom: Path, frames: int, *, audio: bool) -> tuple[bytes, float, int, bytes]:
    config = EmulatorConfig(audio=AudioMode.BUFFERED if audio else AudioMode.DISABLED)
    emu = NativeEmulator.from_rom(rom, config=config)
    try:
        start = time.perf_counter()
        for _ in range(frames):
            emu.step_frame()
        elapsed = time.perf_counter() - start
        pcm = emu.audio.read_buffer() if audio else b""
        return emu.framebuffer(), elapsed, emu.cycles, pcm
    finally:
        emu.close()


def _smoke_one(rom: Path, frames: int, *, audio: bool) -> dict:
    py_frame, py_seconds, py_cycles, py_pcm = run_python(rom, frames, audio=audio)
    rs_frame, rs_seconds, rs_cycles, rs_pcm = run_native(rom, frames, audio=audio)
    result = {
        "rom": str(rom),
        "frames": frames,
        "python_seconds": round(py_seconds, 3),
        "rust_seconds": round(rs_seconds, 3),
        "python_fps": round(frames / py_seconds, 1) if py_seconds > 0 else 0.0,
        "rust_fps": round(frames / rs_seconds, 1) if rs_seconds > 0 else 0.0,
        "python_hash": f"{fnv1a(py_frame):016x}",
        "rust_hash": f"{fnv1a(rs_frame):016x}",
        "frame_match": py_frame == rs_frame,
        "cycles": py_cycles,
        "cycles_match": py_cycles == rs_cycles,
        "rust_cycles": rs_cycles,
        "audio_bytes": len(py_pcm),
        "audio_bytes_match": len(py_pcm) == len(rs_pcm),
    }
    if audio:
        result["python_audio_hash"] = f"{fnv1a(py_pcm):016x}"
        result["rust_audio_hash"] = f"{fnv1a(rs_pcm):016x}"
        result["audio_match"] = py_pcm == rs_pcm
    result["match"] = result["frame_match"] and result["cycles_match"]
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--rom", type=Path, default=None)
    parser.add_argument(
        "--roms-dir",
        type=Path,
        default=None,
        help="掃描目錄下全部 *.gba（與 --rom 二選一）",
    )
    parser.add_argument("--frames", type=int, default=120)
    parser.add_argument("--json", action="store_true", help="輸出單一 JSON 物件")
    parser.add_argument("--audio", action="store_true", help="同時比較 PCM 長度／hash")
    args = parser.parse_args()
    if args.frames < 1:
        parser.error("--frames 必須 >= 1")
    if (args.rom is None) == (args.roms_dir is None):
        parser.error("--rom 與 --roms-dir 要二選一")
    if args.rom is not None:
        roms = [args.rom]
    else:
        roms = sorted(args.roms_dir.glob("*.gba"))
        if not roms:
            parser.error(f"{args.roms_dir} 入面冇 *.gba")
    for rom in roms:
        if not rom.exists():
            raise SystemExit(f"missing ROM: {rom}")

    results = [_smoke_one(rom, args.frames, audio=args.audio) for rom in roms]
    if args.json:
        print(
            json.dumps(
                {
                    "frames": args.frames,
                    "audio": args.audio,
                    "all_match": all(item["match"] for item in results),
                    "roms": results,
                },
                ensure_ascii=False,
                sort_keys=True,
            )
        )
    else:
        for item in results:
            print(f"rom={item['rom']} frames={item['frames']}")
            print(
                f"python : {item['python_seconds']:.3f}s {item['python_fps']:7.1f} fps "
                f"hash={item['python_hash']} cycles={item['cycles']}"
            )
            print(
                f"rust   : {item['rust_seconds']:.3f}s {item['rust_fps']:7.1f} fps "
                f"hash={item['rust_hash']} cycles={item['rust_cycles']}"
            )
            print(
                f"match  : {item['match']} "
                f"(frame={item['frame_match']} cycles={item['cycles_match']}) "
                f"speedup={item['rust_fps'] / item['python_fps']:.2f}x"
                if item["python_fps"]
                else f"match  : {item['match']}"
            )
            if args.audio:
                print(
                    f"audio  : bytes={item['audio_bytes']} "
                    f"py={item.get('python_audio_hash')} rs={item.get('rust_audio_hash')} "
                    f"match={item.get('audio_match')}"
                )
        matches = sum(1 for item in results if item["match"])
        print(f"summary: {matches}/{len(results)} ROMs match")
    return 0 if all(item["match"] for item in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
