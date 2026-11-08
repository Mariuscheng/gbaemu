"""gbaemu 主程式：選擇 ROM 並開啟 SDL3 視窗。

用法：
    python main.py path/to/game.gba      # 直接指定 ROM
    python main.py                       # 自動搜尋／互動輸入
    GBAEMU_ROM=... python main.py        # 用環境變數指定

可以將呢個檔案 copy 到任何資料夾使用（需要先 ``pip install gbaemu``）。
"""

from __future__ import annotations

import os
import sys
import warnings
from pathlib import Path

# pygame-ce 喺 free-threaded Python 會出 GIL RuntimeWarning；普通使用者唔需要。
warnings.filterwarnings("ignore", message=".*GIL.*")

_HERE = Path(__file__).resolve().parent
# 開發環境（repo root 就係 gbaemu package）：令 `import gbaemu` 找到工作樹。
if (_HERE / "__init__.py").exists() and (_HERE / "api_types.py").exists():
    sys.path.insert(0, str(_HERE.parent))


def _find_roms() -> list[Path]:
    """喺目前資料夾、main.py 所在資料夾、同各自嘅 rom/ 搵 *.gba。"""

    roots = [Path.cwd(), _HERE, Path.cwd() / "rom", _HERE / "rom"]
    found: list[Path] = []
    for root in roots:
        try:
            for path in sorted(root.glob("*.gba")):
                resolved = path.resolve()
                if resolved not in found:
                    found.append(resolved)
        except OSError:
            continue
    return found


def _pick_rom() -> Path:
    if len(sys.argv) > 1:
        rom = Path(sys.argv[1])
        if not rom.is_file():
            raise SystemExit(f"找不到 ROM：{rom}")
        return rom

    env_rom = os.environ.get("GBAEMU_ROM")
    if env_rom:
        rom = Path(env_rom)
        if not rom.is_file():
            raise SystemExit(f"GBAEMU_ROM 指定的檔案不存在：{rom}")
        return rom

    candidates = _find_roms()
    if len(candidates) == 1:
        return candidates[0]
    if candidates:
        print("找到多個 ROM：")
        for index, path in enumerate(candidates, start=1):
            print(f"  {index}. {path}")
        answer = input("請輸入編號（Enter 取消）：").strip()
        if not answer:
            raise SystemExit("已取消。")
        try:
            return candidates[int(answer) - 1]
        except (ValueError, IndexError):
            raise SystemExit(f"無效編號：{answer}")

    print("找不到 .gba ROM。")
    answer = input("請輸入 ROM 路徑（Enter 取消）：").strip().strip('"')
    if not answer:
        raise SystemExit("已取消。")
    rom = Path(answer).expanduser()
    if not rom.is_file():
        raise SystemExit(f"找不到 ROM：{rom}")
    return rom


def main() -> None:
    from gbaemu import GbaApp

    rom = _pick_rom()
    app = GbaApp(str(rom), window="SDL3", sound="100")
    try:
        while app.tick():
            pass
    finally:
        # 即使 Ctrl+C／例外結束都要寫回電池存檔（<rom stem>.sav）。
        app.stop()


if __name__ == "__main__":
    main()
