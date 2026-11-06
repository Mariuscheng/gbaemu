"""gbaemu 的 PyBoy 風格主程式。

安裝成 site-packages 後：``python main.py``（或從任意目錄執行）。
開發環境（repo root）第一次 import 失敗時，會把專案父目錄補進 sys.path，
讓 ``import gbaemu`` 找到工作樹而不是 site-packages。
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

# 若 main.py 位於「套件根」（repo root 有 __init__.py），優先使用工作樹：
# gbaemu package 的父目錄是這個根目錄的上一層。
_HERE = Path(__file__).resolve().parent
if (_HERE / "__init__.py").exists():
    sys.path.insert(0, str(_HERE.parent))

# 開發環境：若直接用到不是 venv 的 python，重新以專案 venv 執行，避免
# pygame/gbaemu 只裝在 venv、系統 Python 卻找不到。可用 GBAEMU_NO_REEXEC=1 關閉。
_VENV_PYTHON = _HERE / ("venv/Scripts/python.exe" if os.name == "nt" else "venv/bin/python")
if (
    _VENV_PYTHON.exists()
    and Path(sys.executable).resolve() != _VENV_PYTHON.resolve()
    and os.environ.get("GBAEMU_NO_REEXEC") != "1"
    and os.environ.get("GBAEMU_REEXEC") != "1"
):
    os.environ["GBAEMU_REEXEC"] = "1"
    try:
        os.execv(str(_VENV_PYTHON), [str(_VENV_PYTHON), str(_HERE / "main.py"), *sys.argv[1:]])
    except OSError:
        pass  # 無法 re-exec 時照原 interpreter 繼續，讓後續給出清楚的錯誤

from gbaemu import GbaApp  # noqa: E402

def main() -> None:
    rom = sys.argv[1] if len(sys.argv) > 1 else "rom/rom.gba"
    if not Path(rom).exists():
        raise SystemExit(
            f"找不到 ROM：{rom}\n"
            "本專案唔會分發 ROM／BIOS；請自行準備，例如：\n"
            "  python main.py path/to/game.gba\n"
            "或將 ROM 放在 rom/rom.gba（見 rom/README.md）。"
        )
    app = GbaApp(rom, window="SDL3", sound="100")
    try:
        while app.tick():
            pass
    finally:
        # 即使 Ctrl+C／例外結束都要寫回電池存檔（<rom>.sav）。
        app.stop()


if __name__ == "__main__":
    main()
