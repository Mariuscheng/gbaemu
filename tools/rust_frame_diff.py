"""G3 framebuffer differential：Python renderer vs Rust ``frame_probe``。

用法（repo root）：

    cargo build --manifest-path crates/gbaemu-core/Cargo.toml --bin frame_probe
    .\\venv\\Scripts\\python.exe tools/rust_frame_diff.py

目前只比固定 VRAM／IO 狀態下的 RGB888 framebuffer hash 與取樣像素。
"""

from __future__ import annotations

import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROBE = ROOT / "crates" / "gbaemu-core" / "target" / "debug" / "frame_probe.exe"

sys.path.insert(0, str(ROOT.parent))

import gbaemu  # noqa: E402

if Path(gbaemu.__file__).resolve().parent != ROOT:
    raise SystemExit(f"載入非 repo 的 gbaemu：{gbaemu.__file__}（預期 {ROOT}）")

from gbaemu import BootMode, Emulator, EmulatorConfig  # noqa: E402


def make_rom() -> bytes:
    rom = bytearray(0x4000)
    rom[0xB2] = 0x96
    return bytes(rom)


def pattern(size: int) -> bytes:
    return bytes((index * 37 + 11) & 0xFF for index in range(size))


def fnv1a(data: bytes) -> int:
    value = 0xCBF29CE484222325
    for byte in data:
        value ^= byte
        value = (value * 0x100000001B3) & 0xFFFFFFFFFFFFFFFF
    return value


@dataclass
class FrameCase:
    name: str
    fills: list[str] = field(default_factory=list)  # vram / palette / oam
    writes: list[tuple[int, int, int]] = field(default_factory=list)  # width, addr, value
    pixels: list[tuple[int, int]] = field(default_factory=list)


class Probe:
    def __init__(self) -> None:
        self.proc = subprocess.Popen(
            [str(PROBE)],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
        )

    def command(self, line: str) -> str:
        assert self.proc.stdin is not None
        self.proc.stdin.write(line + "\n")
        self.proc.stdin.flush()
        assert self.proc.stdout is not None
        output = self.proc.stdout.readline().strip()
        if not output:
            raise RuntimeError(f"probe closed after {line!r}")
        return output

    def close(self) -> None:
        try:
            self.command("quit")
        except Exception:
            pass
        self.proc.kill()


def _apply_python(case: FrameCase) -> tuple[int, dict[tuple[int, int], tuple[int, int, int]]]:
    with tempfile.TemporaryDirectory() as temp:
        path = Path(temp) / "frame.gba"
        path.write_bytes(make_rom())
        emu = Emulator.from_rom(path, config=EmulatorConfig(boot_mode=BootMode.TEST_ROM_ONLY))
        try:
            bus = emu._bus
            for fill in case.fills:
                if fill == "vram":
                    bus.vram.load(pattern(0x18000))
                elif fill == "palette":
                    bus.palette.load(pattern(0x400))
                elif fill == "oam":
                    bus.oam.load(pattern(0x400))
            for width, address, value in case.writes:
                if width == 8:
                    bus.write_u8(address, value)
                elif width == 16:
                    bus.write_u16(address, value)
                else:
                    bus.write_u32(address, value)
            emu.step_frame(render=True)
            frame = emu._framebuffer.read_frame()
            pixels = {}
            for x, y in case.pixels:
                index = (y * 240 + x) * 3
                pixels[(x, y)] = tuple(frame[index : index + 3])
            return fnv1a(frame), pixels
        finally:
            emu.close()


def _apply_rust(probe: Probe, case: FrameCase) -> tuple[int, dict[tuple[int, int], tuple[int, int, int]]]:
    assert probe.command("reset") == "ok"
    for fill in case.fills:
        assert probe.command(f"fill{fill}") == "ok"
    for width, address, value in case.writes:
        assert probe.command(f"write{width} {address:08x} {value:x}") == "ok"
    result = probe.command("render")
    if result.startswith("err"):
        raise RuntimeError(result)
    hash_value = int(probe.command("hash").split("value=")[1], 16)
    pixels = {}
    for x, y in case.pixels:
        value = probe.command(f"pixel {x} {y}").split("value=")[1]
        pixels[(x, y)] = (int(value[0:2], 16), int(value[2:4], 16), int(value[4:6], 16))
    return hash_value, pixels


def main() -> int:
    if not PROBE.exists():
        print(f"missing probe: {PROBE}")
        print("run: cargo build --manifest-path crates/gbaemu-core/Cargo.toml --bin frame_probe")
        return 2

    cases = [
        FrameCase(
            "mode3_gradient",
            fills=["vram"],
            writes=[(16, 0x0400_0000, 3)],
            pixels=[(0, 0), (1, 0), (120, 80), (239, 159)],
        ),
        FrameCase(
            "mode3_solid_red",
            writes=[(16, 0x0400_0000, 3), (16, 0x0600_0000, 0x001F)],
            pixels=[(0, 0), (239, 159)],
        ),
        FrameCase(
            "mode0_text_bg0",
            fills=["palette"],
            writes=[
                (16, 0x0400_0000, 0x0100),
                (16, 0x0400_0008, 0x0004),
                (16, 0x0500_0002, 0x001F),
                (16, 0x0600_0000, 0x0000),
                *[(16, 0x0600_4000 + index * 2, 0x1111) for index in range(16)],
            ],
            pixels=[(0, 0), (7, 7), (8, 8), (239, 159)],
        ),
        FrameCase(
            "mode0_sprite",
            fills=["vram"],
            writes=[
                (16, 0x0400_0000, 0x1000),
                (16, 0x0700_0000, 0x0000),
                (16, 0x0700_0002, 0x0000),
                (16, 0x0700_0004, 0x0000),
            ],
            pixels=[(0, 0), (7, 7), (8, 8)],
        ),
        FrameCase(
            "mode3_forced_blank",
            writes=[(16, 0x0400_0000, 0x0083)],
            pixels=[(0, 0), (239, 159)],
        ),
        FrameCase(
            "mode0_window0_bg0",
            writes=[
                (16, 0x0400_0000, 0x2100),
                (16, 0x0400_0008, 0x0004),
                # WIN0H：X1=0x50、X2=0 → GBATEK 當成 X2=240（畫面右半）。
                (16, 0x0400_0040, 0x5000),
                # WIN0V：Y1=0、Y2=160。
                (16, 0x0400_0044, 0x00A0),
                (16, 0x0400_0048, 0x003F),
                (16, 0x0400_004A, 0x0000),
                (16, 0x0500_0002, 0x001F),
                (16, 0x0600_0000, 0x0000),
                *[(16, 0x0600_4000 + index * 2, 0x1111) for index in range(16)],
            ],
            pixels=[(0, 0), (79, 0), (80, 0), (239, 159)],
        ),
        FrameCase(
            "mode0_window1_band",
            writes=[
                (16, 0x0400_0000, 0x4100),  # Mode 0 + BG0 + WIN1
                (16, 0x0400_0008, 0x0004),
                (16, 0x0400_0042, 0x00F0),  # WIN1H：X1=0、X2=240（全寬）
                (16, 0x0400_0046, 0x2080),  # WIN1V：Y1=32、Y2=128
                (16, 0x0400_0048, 0x3F00),  # WININ：WIN1 內全部 layer
                (16, 0x0400_004A, 0x0000),  # 窗外全部隱藏
                (16, 0x0500_0002, 0x001F),
                (16, 0x0600_0000, 0x0000),
                *[(16, 0x0600_4000 + index * 2, 0x1111) for index in range(16)],
            ],
            pixels=[(0, 0), (120, 31), (120, 32), (120, 127), (120, 128), (239, 159)],
        ),
        FrameCase(
            "mode2_affine_bg2",
            writes=[
                (16, 0x0400_0000, 0x0402),
                (16, 0x0400_000C, 0x0004),
                (16, 0x0400_0020, 0x0100),
                (16, 0x0400_0022, 0x0000),
                (16, 0x0400_0024, 0x0000),
                (16, 0x0400_0026, 0x0100),
                (16, 0x0400_0028, 0x0000),
                (16, 0x0400_002A, 0x0000),
                (16, 0x0500_0002, 0x001F),
                (16, 0x0600_0000, 0x0000),
                *[(16, 0x0600_4000 + index * 2, 0x1111) for index in range(16)],
            ],
            pixels=[(0, 0), (120, 80), (239, 159)],
        ),
        FrameCase(
            "mode0_bg_mosaic",
            writes=[
                (16, 0x0400_0000, 0x0100),
                (16, 0x0400_0008, 0x0044),
                (16, 0x0400_004C, 0x0077),
                (16, 0x0500_0002, 0x001F),
                (16, 0x0500_0004, 0x7C00),
                (16, 0x0600_0000, 0x0000),
                *[(16, 0x0600_4000 + index * 2, 0x1212) for index in range(16)],
            ],
            pixels=[(0, 0), (7, 7), (8, 8), (239, 159)],
        ),
        FrameCase(
            "mode0_alpha_blend",
            writes=[
                (16, 0x0400_0000, 0x0300),
                (16, 0x0400_0008, 0x0004),
                (16, 0x0400_000A, 0x0007),
                (16, 0x0400_0050, 0x0241),
                (16, 0x0400_0052, 0x0808),
                (16, 0x0500_0002, 0x001F),
                (16, 0x0500_0004, 0x7C00),
                (16, 0x0600_0000, 0x0000),
                *[(16, 0x0600_4000 + index * 2, 0x1111) for index in range(16)],
                *[(16, 0x0600_6000 + index * 2, 0x2222) for index in range(16)],
            ],
            pixels=[(0, 0), (120, 80), (239, 159)],
        ),
        FrameCase(
            "mode0_fade_darken",
            writes=[
                (16, 0x0400_0000, 0x0100),
                (16, 0x0400_0008, 0x0004),
                (16, 0x0400_0050, 0x00C1),
                (16, 0x0400_0054, 0x0010),
                (16, 0x0500_0002, 0x001F),
                (16, 0x0600_0000, 0x0000),
                *[(16, 0x0600_4000 + index * 2, 0x1111) for index in range(16)],
            ],
            pixels=[(0, 0), (120, 80)],
        ),
        FrameCase(
            "mode0_affine_sprite",
            fills=["vram"],
            writes=[
                (16, 0x0400_0000, 0x1000),
                (16, 0x0700_0000, 0x0100),
                (16, 0x0700_0002, 0x0000),
                (16, 0x0700_0004, 0x0000),
                (16, 0x0700_0006, 0x0100),
                (16, 0x0700_001E, 0x0100),
            ],
            pixels=[(0, 0), (7, 7), (8, 8)],
        ),
        FrameCase(
            "mode4_bitmap8",
            fills=["vram", "palette"],
            writes=[(16, 0x0400_0000, 4)],
            pixels=[(0, 0), (120, 80), (239, 159)],
        ),
        FrameCase(
            "mode5_bitmap16",
            fills=["vram"],
            writes=[(16, 0x0400_0000, 5)],
            pixels=[(0, 0), (120, 80), (159, 127), (239, 159)],
        ),
        FrameCase(
            "mode1_text_and_affine",
            writes=[
                (16, 0x0400_0000, 0x0401),
                (16, 0x0400_000C, 0x0004),
                (16, 0x0400_0020, 0x0100),
                (16, 0x0400_0022, 0x0000),
                (16, 0x0400_0024, 0x0000),
                (16, 0x0400_0026, 0x0100),
                (16, 0x0400_0028, 0x0000),
                (16, 0x0400_002A, 0x0000),
                (16, 0x0500_0002, 0x001F),
                (16, 0x0600_0000, 0x0000),
                *[(16, 0x0600_4000 + index * 2, 0x1111) for index in range(16)],
            ],
            pixels=[(0, 0), (120, 80), (239, 159)],
        ),
        FrameCase(
            "mode0_obj_window",
            writes=[
                (16, 0x0400_0000, 0x9100),
                (16, 0x0400_0008, 0x0004),
                (16, 0x0400_004A, 0x0100),
                (16, 0x0500_0002, 0x001F),
                (16, 0x0600_0000, 0x0000),
                (16, 0x0700_0000, 0x0000),
                (16, 0x0700_0002, 0x0000),
                (16, 0x0700_0004, 0x0000),
                *[(16, 0x0600_4000 + index * 2, 0x1111) for index in range(16)],
                *[(16, 0x0601_0000 + index * 2, 0x1111) for index in range(16)],
            ],
            pixels=[(0, 0), (7, 7), (8, 8), (239, 159)],
        ),
        FrameCase(
            "mode0_obj_window_sprite",
            writes=[
                (16, 0x0400_0000, 0x9100),  # OBJ + OBJ window + BG0
                (16, 0x0400_0008, 0x0004),  # BG0 char base 0x4000
                (16, 0x0400_004A, 0x0100),  # WINOUT: OBJ window 內 = BG0
                (16, 0x0500_0000, 0x03E0),  # backdrop 綠
                (16, 0x0500_0002, 0x001F),  # BG palette 1 紅
                (16, 0x0600_0000, 0x0000),  # BG0 map tile 0
                (16, 0x0700_0000, 0x0800),  # attr0: OBJ window mode、y=0
                (16, 0x0700_0002, 0x0000),  # attr1: x=0、8x8
                (16, 0x0700_0004, 0x0000),  # attr2: tile 0、4bpp
                *[(16, 0x0600_4000 + index * 2, 0x1111) for index in range(16)],
                *[(16, 0x0601_0000 + index * 2, 0x1111) for index in range(16)],
            ],
            pixels=[(0, 0), (7, 7), (8, 8), (239, 159)],
        ),
    ]

    probe = Probe()
    failed = 0
    try:
        for case in cases:
            py_hash, py_pixels = _apply_python(case)
            rs_hash, rs_pixels = _apply_rust(probe, case)
            errors = []
            if py_hash != rs_hash:
                errors.append(f"hash: py={py_hash:016x} rust={rs_hash:016x}")
            for key, value in py_pixels.items():
                if rs_pixels.get(key) != value:
                    errors.append(f"pixel{key}: py={value} rust={rs_pixels.get(key)}")
            if errors:
                failed += 1
                print(f"[FAIL] {case.name}")
                for error in errors:
                    print(f"  {error}")
            else:
                print(f"[ ok ] {case.name}")
    finally:
        probe.close()

    total = len(cases)
    print(f"{total - failed}/{total} frame checks passed")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
