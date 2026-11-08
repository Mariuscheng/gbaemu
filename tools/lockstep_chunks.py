"""用固定 cycle chunk 比較 Python reference 同 Rust core，收窄第一個分歧點。

用法：
    .\\venv\\Scripts\\python.exe tools/lockstep_chunks.py --rom rom.gba --cycles 280896 --chunk 1232
"""

from __future__ import annotations

import argparse
from pathlib import Path

from gbaemu import Emulator, EmulatorConfig, NativeEmulator


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--rom", type=Path, required=True)
    parser.add_argument("--cycles", type=int, default=280896)
    parser.add_argument("--chunk", type=int, default=1232)
    args = parser.parse_args()
    py = Emulator.from_rom(args.rom, config=EmulatorConfig())
    rs = NativeEmulator.from_rom(args.rom)
    try:
        done = 0
        while done < args.cycles:
            budget = min(args.chunk, args.cycles - done)
            py.step_cycles(budget)
            rs.step_cycles(budget)
            done += budget
            if py.cycles != rs.cycles:
                print(
                    f"first divergence in chunk ending at {done}: "
                    f"py={py.cycles} rust={rs.cycles} delta={py.cycles - rs.cycles}"
                )
                print(f"chunk_start={done - budget} chunk={budget}")
                return 1
        print(f"{args.cycles} cycles identical (chunk={args.chunk})")
        return 0
    finally:
        py.close()
        rs.close()


if __name__ == "__main__":
    raise SystemExit(main())
