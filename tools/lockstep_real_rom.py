"""逐 frame 比較 Python reference 與 Rust core 的 cycles／state hash。

用法：
    .\\venv\\Scripts\\python.exe tools\\lockstep_real_rom.py --rom rom.gba --frames 10

搵出第一個 diverging frame；divergence 之前嘅 frame 數、cycles 差同
state hash 會印出嚟，方便再收窄到 instruction 級。
"""

from __future__ import annotations

import argparse
import hashlib
from pathlib import Path

from gbaemu import Emulator, EmulatorConfig, NativeEmulator


def _hash_state(emu) -> str:
    return hashlib.sha256(emu.save_state()).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--rom", type=Path, required=True)
    parser.add_argument("--frames", type=int, default=10)
    parser.add_argument("--state", action="store_true", help="每 frame 比較 save_state hash")
    args = parser.parse_args()
    py = Emulator.from_rom(args.rom, config=EmulatorConfig())
    rs = NativeEmulator.from_rom(args.rom)
    try:
        for frame in range(args.frames):
            py.step_frame(render=False)
            rs.step_frame()
            py_cycles, rs_cycles = py.cycles, rs.cycles
            py_hash = _hash_state(py) if args.state else None
            rs_hash = _hash_state(rs) if args.state else None
            state_note = ""
            if args.state:
                state_note = f" state_match={py_hash == rs_hash}"
            print(
                f"frame={frame} py_cycles={py_cycles} rs_cycles={rs_cycles} "
                f"delta={py_cycles - rs_cycles}{state_note}"
            )
            if py_cycles != rs_cycles or (args.state and py_hash != rs_hash):
                print(f"first divergence at frame {frame}")
                return 1
        print(f"{args.frames} frames identical")
        return 0
    finally:
        py.close()
        rs.close()


if __name__ == "__main__":
    raise SystemExit(main())
