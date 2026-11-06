"""Phase 0 驗收：GBATEK 對照索引存在且引用的路徑有效。

專案根目錄本身就是 ``gbaemu`` 套件（沒有內層 ``gbaemu/`` 目錄），所以索引
裡的程式路徑一律相對於專案根，例如 ``bus/address_bus.py``。
"""

from __future__ import annotations

import re

from .helpers import ROOT

INDEX_PATH = ROOT / "docs" / "spec" / "GBATEK_INDEX.md"


def _is_checked_path(reference: str) -> bool:
    """索引中需要驗證存在的路徑：GBATEK 章節或專案內的 ``.py`` 檔。"""

    if reference.startswith("docs/gbatek-gba-specs/"):
        return True
    return "/" in reference and reference.endswith(".py")


def test_index_exists_and_covers_required_subsystems():
    assert INDEX_PATH.exists(), INDEX_PATH
    text = INDEX_PATH.read_text(encoding="utf-8")
    for keyword in (
        "Memory Map",
        "I/O Map",
        "ARM CPU",
        "LCD",
        "DMA",
        "Timer",
        "Interrupt",
        "Keypad",
        "Cartridge",
    ):
        assert keyword.lower() in text.lower(), keyword


def test_index_referenced_paths_exist():
    text = INDEX_PATH.read_text(encoding="utf-8")
    references = set(re.findall(r"`([^`]+)`", text))
    checked = 0
    for reference in references:
        if not _is_checked_path(reference):
            continue
        path = ROOT / reference
        assert path.exists(), f"索引引用了不存在的路徑：{reference}"
        checked += 1
    assert checked >= 20
