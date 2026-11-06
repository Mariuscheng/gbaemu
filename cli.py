"""``gbaemu`` command line interface（規格第 12 章）。

Phase 0 只提供 ``inspect-rom``；其餘命令在對應 Phase 加入。所有輸出皆可在
headless CI 使用，``--json`` 是單一 JSON 物件且欄位順序固定。
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .errors import GbaEmuError
from .memory.cartridge import load_rom_file, parse_rom_header


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
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


__all__ = ["build_parser", "main"]
