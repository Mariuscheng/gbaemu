"""``gbaemu`` command line interface（規格第 12 章）。

Phase 0 只提供 ``inspect-rom``；其餘命令在對應 Phase 加入。所有輸出皆可在
headless CI 使用，``--json`` 是單一 JSON 物件且欄位順序固定。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

from .errors import GbaEmuError
from .memory.cartridge import load_rom_file, parse_rom_header


def _headless_emulator(rom: str):
    """建立 headless Emulator（CLI 用；HLE bootstrap、functional timing）。"""

    from .api_types import BootMode, EmulatorConfig, TimingMode, VideoMode
    from .emulator import Emulator

    config = EmulatorConfig(
        boot_mode=BootMode.HLE_ADVANCED,
        timing=TimingMode.FUNCTIONAL,
        video=VideoMode.FRAMEBUFFER,
        hle_strict=False,
    )
    return Emulator.from_rom(rom, config=config)


def _state_hash(emu) -> str:
    return hashlib.sha256(emu.save_state()).hexdigest()


def _parse_int(value: str) -> int:
    return int(value, 0)


def _cmd_run(args: argparse.Namespace) -> int:
    try:
        emu = _headless_emulator(args.rom)
    except (GbaEmuError, OSError) as exc:
        print(f"gbaemu: {exc}", file=sys.stderr)
        return 1
    try:
        for _ in range(args.frames):
            emu.step_frame(render=not args.no_video)
        payload = {
            "rom": str(args.rom),
            "frames": args.frames,
            "cycles": emu.cycles,
            "frame_index": emu.frame_index,
            "halted": emu.cpu.state().halted,
            "state_hash": _state_hash(emu),
        }
    finally:
        emu.close()
    if args.as_json:
        print(json.dumps(payload, ensure_ascii=False))
    else:
        print(
            f"rom={payload['rom']} frames={payload['frames']} "
            f"cycles={payload['cycles']} halted={payload['halted']} "
            f"state_hash={payload['state_hash']}"
        )
    return 0


def _cmd_dump_memory(args: argparse.Namespace) -> int:
    try:
        emu = _headless_emulator(args.rom)
    except (GbaEmuError, OSError) as exc:
        print(f"gbaemu: {exc}", file=sys.stderr)
        return 1
    try:
        for _ in range(args.frames):
            emu.step_frame(render=False)
        data = bytes(
            emu.memory.read_u8(args.address + offset) for offset in range(args.size)
        )
    finally:
        emu.close()

    if args.as_json:
        print(
            json.dumps(
                {
                    "rom": str(args.rom),
                    "address": args.address,
                    "size": args.size,
                    "hex": data.hex(),
                }
            )
        )
        return 0
    for offset in range(0, len(data), 16):
        chunk = data[offset : offset + 16]
        hex_part = " ".join(f"{byte:02x}" for byte in chunk)
        print(f"{args.address + offset:08x}  {hex_part}")
    return 0


def _cmd_trace(args: argparse.Namespace) -> int:
    try:
        emu = _headless_emulator(args.rom)
    except (GbaEmuError, OSError) as exc:
        print(f"gbaemu: {exc}", file=sys.stderr)
        return 1
    try:
        cpu = emu._cpu
        # 先跑到 --from（最多 1,000,000 cycles，避免錯誤位址無限迴圈）。
        skip_budget = 1_000_000
        while cpu.cycles < skip_budget:
            state = emu.cpu.state()
            if state.regs[15] == args.from_addr:
                break
            cpu.step()
        start = cpu.cycles
        while cpu.cycles - start < args.cycles:
            state = emu.cpu.state()
            print(
                json.dumps(
                    {
                        "pc": f"0x{state.regs[15]:08X}",
                        "cpsr": f"0x{state.cpsr:08X}",
                        "cycles": cpu.cycles,
                    }
                )
            )
            cpu.step()
    finally:
        emu.close()
    return 0


def _cmd_replay(args: argparse.Namespace) -> int:
    try:
        events = [
            json.loads(line)
            for line in Path(args.input).read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
    except (OSError, json.JSONDecodeError) as exc:
        print(f"gbaemu: 無法讀取 input trace：{exc}", file=sys.stderr)
        return 1

    schedule: dict[int, list[str]] = {}
    for frame, item in enumerate(events):
        index = int(item.get("frame", frame))
        buttons = item.get("buttons", item.get("keys", []))
        schedule[index] = list(buttons)

    try:
        emu = _headless_emulator(args.rom)
    except (GbaEmuError, OSError) as exc:
        print(f"gbaemu: {exc}", file=sys.stderr)
        return 1
    try:
        frames = max(schedule) + 1 if schedule else 0
        if args.frames is not None:
            frames = args.frames
        for frame in range(frames):
            emu.input.clear()
            pressed = {name: True for name in schedule.get(frame, [])}
            if pressed:
                emu.input.set_buttons(**pressed)
            emu.step_frame(render=False)
        payload = {
            "rom": str(args.rom),
            "frames": frames,
            "state_hash": _state_hash(emu),
        }
    finally:
        emu.close()
    print(json.dumps(payload, ensure_ascii=False))
    return 0


def find_roms(directory: str | Path = "rom") -> list[Path]:
    """列出 ``directory`` 入面的 ``.gba`` 檔（大小寫不拘，按檔名排序）。

    ``python main.py`` 唔再硬編 ``rom/rom.gba``：目錄入面只有一個 ROM 時
    自動用它；多過一個就由 caller 要求用戶指定，避免載錯遊戲／撞存檔。
    """

    folder = Path(directory)
    if not folder.is_dir():
        return []
    return sorted(
        (
            path
            for path in folder.iterdir()
            if path.is_file() and path.suffix.lower() == ".gba"
        ),
        key=lambda path: path.name.lower(),
    )


def _inspect_payload(path: Path, rom: bytes) -> dict:
    header = parse_rom_header(rom)
    # dict 插入順序 = JSON 欄位順序（穩定，供 CI 解析）。
    return {
        "path": str(path),
        "file_size": len(rom),
        "entry_point": f"0x{header.entry_point:08X}",
        "title": header.title,
        "game_code": header.game_code,
        "maker_code": header.maker_code,
        "main_unit_code": header.main_unit_code,
        "device_type": header.device_type,
        "software_version": header.software_version,
        "fixed_value": header.fixed_value,
        "fixed_value_ok": header.fixed_value_ok,
        "header_checksum": header.complement_check,
        "header_checksum_calculated": header.complement_check_calculated,
        "header_checksum_ok": header.complement_check_ok,
    }


def _format_inspect_text(payload: dict) -> str:
    checksum_state = "OK" if payload["header_checksum_ok"] else "FAIL"
    fixed_state = "OK" if payload["fixed_value_ok"] else "FAIL"
    lines = [
        f"ROM:              {payload['path']}",
        f"Size:             {payload['file_size']} bytes",
        f"Title:            {payload['title']}",
        f"Game code:        {payload['game_code']}",
        f"Maker code:       {payload['maker_code']}",
        f"Entry point:      {payload['entry_point']}",
        f"Main unit code:   0x{payload['main_unit_code']:02X}",
        f"Device type:      0x{payload['device_type']:02X}",
        f"Software version: 0x{payload['software_version']:02X}",
        (
            "Header checksum:  0x{stored:02X} (calculated 0x{calculated:02X}, {state})"
        ).format(
            stored=payload["header_checksum"],
            calculated=payload["header_checksum_calculated"],
            state=checksum_state,
        ),
        f"Fixed value:      0x{payload['fixed_value']:02X} ({fixed_state})",
    ]
    return "\n".join(lines)


def _cmd_inspect_rom(args: argparse.Namespace) -> int:
    path = Path(args.rom)
    try:
        rom = load_rom_file(path)
        payload = _inspect_payload(path, rom)
    except (GbaEmuError, OSError) as exc:
        print(f"gbaemu: {exc}", file=sys.stderr)
        return 1

    if args.as_json:
        print(json.dumps(payload, ensure_ascii=False))
    else:
        print(_format_inspect_text(payload))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="gbaemu", description="GBA 模擬器工具")
    subparsers = parser.add_subparsers(dest="command", required=True)

    inspect_rom = subparsers.add_parser("inspect-rom", help="顯示 ROM header 資訊")
    inspect_rom.add_argument("rom", help="ROM 檔案路徑")
    inspect_rom.add_argument(
        "--json",
        action="store_true",
        dest="as_json",
        help="輸出單一 JSON 物件（欄位順序固定）",
    )
    inspect_rom.set_defaults(func=_cmd_inspect_rom)

    run = subparsers.add_parser("run", help="headless 執行指定 frame 數")
    run.add_argument("rom", help="ROM 檔案路徑")
    run.add_argument("--frames", type=int, default=60, help="執行 frame 數（預設 60）")
    run.add_argument("--no-video", action="store_true", help="唔 render framebuffer")
    run.add_argument("--json", action="store_true", dest="as_json")
    run.set_defaults(func=_cmd_run)

    dump_memory = subparsers.add_parser("dump-memory", help="dump 記憶體（hex）")
    dump_memory.add_argument("rom", help="ROM 檔案路徑")
    dump_memory.add_argument(
        "--address", type=_parse_int, default=0x02000000, help="起始位址（可用 0x）"
    )
    dump_memory.add_argument("--size", type=int, default=256, help="bytes 數")
    dump_memory.add_argument("--frames", type=int, default=0, help="dump 前先跑 frame 數")
    dump_memory.add_argument("--json", action="store_true", dest="as_json")
    dump_memory.set_defaults(func=_cmd_dump_memory)

    trace = subparsers.add_parser("trace", help="CPU instruction trace（JSONL）")
    trace.add_argument("rom", help="ROM 檔案路徑")
    trace.add_argument(
        "--from", dest="from_addr", type=_parse_int, default=0x08000000, help="起始 PC"
    )
    trace.add_argument("--cycles", type=int, default=1000, help="trace 的 cycle 預算")
    trace.set_defaults(func=_cmd_trace)

    replay = subparsers.add_parser("replay", help="重播 input trace（JSONL）")
    replay.add_argument("rom", help="ROM 檔案路徑")
    replay.add_argument("--input", required=True, help="input trace JSONL")
    replay.add_argument("--frames", type=int, default=None, help="覆寫 frame 數")
    replay.set_defaults(func=_cmd_replay)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


__all__ = ["build_parser", "find_roms", "main"]