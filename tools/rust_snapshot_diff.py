"""G5 snapshot differential：Python reference 與 Rust ``frame_probe``。

用法（repo root）：

    cargo build --manifest-path crates/gbaemu-core/Cargo.toml --bin frame_probe
    .\\venv\\Scripts\\python.exe tools/rust_snapshot_diff.py

流程：
1. Python 產生 snapshot。
2. 交給 Rust `load_state()`，Rust 再 `save_state()`。
3. 逐 section 比對 payload bytes。
4. 把 Rust snapshot 的 ROM/config hash 換成 Python 的，再讓 Python `load_state()`。
"""

from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROBE = ROOT / "crates" / "gbaemu-core" / "target" / "debug" / "frame_probe.exe"

sys.path.insert(0, str(ROOT.parent))

import gbaemu  # noqa: E402

if Path(gbaemu.__file__).resolve().parent != ROOT:
    raise SystemExit(f"載入非 repo 的 gbaemu：{gbaemu.__file__}（預期 {ROOT}）")

from gbaemu import BootMode, Emulator, EmulatorConfig  # noqa: E402
from gbaemu.config import config_sha256  # noqa: E402
from gbaemu.state.snapshot import (  # noqa: E402
    REQUIRED_SECTIONS,
    SNAPSHOT_HEADER_SIZE,
    unpack_sections,
)


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


def make_emu() -> Emulator:
    temp = tempfile.TemporaryDirectory()
    path = Path(temp.name) / "snapshot.gba"
    rom = bytearray(0x4000)
    rom[0xB2] = 0x96
    rom[0:4] = bytes.fromhex("feffffea")  # B .
    path.write_bytes(bytes(rom))
    emu = Emulator.from_rom(path, config=EmulatorConfig(boot_mode=BootMode.TEST_ROM_ONLY))
    emu._tempdir = temp  # type: ignore[attr-defined]
    return emu


def first_diff(left: bytes, right: bytes) -> str:
    limit = min(len(left), len(right))
    for index in range(limit):
        if left[index] != right[index]:
            return f"offset {index}: py={left[index]:02x} rust={right[index]:02x}"
    if len(left) != len(right):
        return f"length py={len(left)} rust={len(right)}"
    return "equal"


def main() -> int:
    if not PROBE.exists():
        print(f"missing probe: {PROBE}")
        print("run: cargo build --manifest-path crates/gbaemu-core/Cargo.toml --bin frame_probe")
        return 2

    emu = make_emu()
    try:
        emu._bus.write_u16(0x0400_0000, 3)
        emu._bus.write_u16(0x0600_0000, 0x001F)
        emu.step_cycles(5_000)
        py_snapshot = emu.save_state()
        py_sections = unpack_sections(py_snapshot[SNAPSHOT_HEADER_SIZE:])

        with tempfile.TemporaryDirectory() as temp:
            py_path = Path(temp) / "python.snap"
            rs_path = Path(temp) / "rust.snap"
            py_path.write_bytes(py_snapshot)

            probe = Probe()
            try:
                assert probe.command("reset") == "ok"
                assert probe.command(f"romfile {emu._rom_path}") == "ok"
                assert probe.command(f"loadstate {py_path}") == "ok"
                config_digest = config_sha256(emu._config).hex()
                assert probe.command(f"configsha {config_digest}") == "ok"
                assert probe.command(f"savestate {rs_path}") == "ok"
            finally:
                probe.close()

            rs_snapshot = rs_path.read_bytes()
            rs_sections = unpack_sections(rs_snapshot[SNAPSHOT_HEADER_SIZE:])

            failed = 0
            for section in REQUIRED_SECTIONS:
                py_data = py_sections.get(section, b"<missing>")
                rs_data = rs_sections.get(section, b"<missing>")
                if py_data != rs_data:
                    failed += 1
                    print(f"[FAIL] section {section!r}: {first_diff(py_data, rs_data)}")
                else:
                    print(f"[ ok ] section {section!r} ({len(py_data)} bytes)")

            # Rust snapshot header 應可直接通過 Python 的 ROM／config 驗證。
            if rs_snapshot[14:78] != py_snapshot[14:78]:
                failed += 1
                print("[FAIL] header ROM/config hash 與 Python 不同")
            else:
                print("[ ok ] header ROM/config hash")
            try:
                emu.load_state(rs_snapshot)
                print("[ ok ] python load_state(rust snapshot)")
            except Exception as error:
                failed += 1
                print(f"[FAIL] python load_state: {error!r}")

            total = len(REQUIRED_SECTIONS) + 2
            print(f"{total - failed}/{total} snapshot checks passed")
            return 0 if failed == 0 else 1
    finally:
        emu.close()


if __name__ == "__main__":
    raise SystemExit(main())
