"""Phase 0 驗收：``inspect-rom`` 文字與 JSON 輸出。"""

from __future__ import annotations

import json
import os
import subprocess
import sys

from gbaemu.cli import main

from .helpers import ROOT

EXPECTED_JSON_FIELDS = [
    "path",
    "file_size",
    "entry_point",
    "title",
    "game_code",
    "maker_code",
    "main_unit_code",
    "device_type",
    "software_version",
    "fixed_value",
    "fixed_value_ok",
    "header_checksum",
    "header_checksum_calculated",
    "header_checksum_ok",
]

_SUBPROCESS_ENV = {**os.environ, "PYTHONIOENCODING": "utf-8"}


def test_inspect_rom_text(rom_path, capsys):
    assert main(["inspect-rom", str(rom_path)]) == 0
    output = capsys.readouterr().out
    assert "Title:            TESTGAME" in output
    assert "Game code:        TEST" in output
    assert "Maker code:       01" in output
    assert "Entry point:      0x08000000" in output
    assert "Header checksum:" in output
    assert "OK" in output
    assert "Fixed value:      0x96 (OK)" in output


def test_inspect_rom_json_fields_and_order(rom_path, rom_bytes, capsys):
    assert main(["inspect-rom", str(rom_path), "--json"]) == 0
    output = capsys.readouterr().out
    payload = json.loads(output)
    assert list(payload) == EXPECTED_JSON_FIELDS
    assert payload["path"] == str(rom_path)
    assert payload["file_size"] == len(rom_bytes)
    assert payload["entry_point"] == "0x08000000"
    assert payload["title"] == "TESTGAME"
    assert payload["game_code"] == "TEST"
    assert payload["maker_code"] == "01"
    assert payload["software_version"] == 0
    assert payload["fixed_value"] == 0x96
    assert payload["fixed_value_ok"] is True
    assert payload["header_checksum"] == payload["header_checksum_calculated"]
    assert payload["header_checksum_ok"] is True
    # 單一 JSON 物件（不是 JSONL）
    assert output.count("\n") == 1


def test_inspect_rom_bad_checksum(tmp_path, capsys):
    from .helpers import build_rom

    path = tmp_path / "bad.gba"
    path.write_bytes(build_rom(checksum_delta=1))
    assert main(["inspect-rom", str(path), "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["header_checksum_ok"] is False


def test_inspect_rom_invalid_file(tmp_path, capsys):
    path = tmp_path / "bad.gba"
    path.write_bytes(b"\x00" * 8)
    assert main(["inspect-rom", str(path)]) == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "gbaemu:" in captured.err


def test_inspect_rom_missing_file(tmp_path, capsys):
    assert main(["inspect-rom", str(tmp_path / "nope.gba")]) == 1
    assert "gbaemu:" in capsys.readouterr().err


def test_module_entrypoint_subprocess(rom_path):
    completed = subprocess.run(
        [sys.executable, "-m", "gbaemu", "inspect-rom", str(rom_path), "--json"],
        cwd=ROOT.parent,  # 專案根目錄就是套件根，必須從上一層才 import 得到 gbaemu
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=_SUBPROCESS_ENV,
        timeout=60,
    )
    assert completed.returncode == 0, completed.stderr
    payload = json.loads(completed.stdout)
    assert list(payload) == EXPECTED_JSON_FIELDS
    assert payload["title"] == "TESTGAME"


def test_module_help_subprocess():
    completed = subprocess.run(
        [sys.executable, "-m", "gbaemu", "--help"],
        cwd=ROOT.parent,  # 專案根目錄就是套件根，必須從上一層才 import 得到 gbaemu
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=_SUBPROCESS_ENV,
        timeout=60,
    )
    assert completed.returncode == 0
    assert "inspect-rom" in completed.stdout
