"""GBA Test Suite（``rom/suite.gba``）導航、截圖與結果檢視工具。

以 native backend 執行，透過按鍵時序導航（suite 的按鍵掃描需要「按住 1 frame、
放開 12 frames」，否則會被視為連按）：

1. 開機後停在主選單 ``Select suite``，游標預設在 ``Memory tests``。
2. ``A`` 進入後會先跑完整個 memory 測試組，再列出 26 個項目，
   黑字 = 全部通過、紅字 = 有失敗。
3. ``DOWN`` 移動游標；``A`` 進入該項的細節（failed 行以紅字顯示 actual/expected）。

用法範例（repo root）：

    # 主選單截圖
    python tools/suite_report.py boot --tag boot

    # 進入 Memory tests，游標移到第 2 項（ROM out-of-bounds load）截圖
    python tools/suite_report.py memory --taps 2 --tag mem_rom_oob

    # 同上，再按 A 進入細節、往下捲 3 行
    python tools/suite_report.py memory --taps 2 --enter --scroll 3 --tag mem_rom_oob_detail

    # 主選單 DOWN×9 → DMA tests，跑完後截圖（任何 suite 索引均可）
    python tools/suite_report.py memory --suite 9 --tag dma

所有圖片預設寫到 ``debug/suite_<tag>.png``。
"""

from __future__ import annotations

import argparse
import hashlib
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROBE_HINT = "cargo build --manifest-path crates/gbaemu-core/Cargo.toml"

sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT.parent))

import gbaemu  # noqa: E402

# 避免 import 到 site-packages 的舊安裝副本（否則測到的是舊版模擬器）。
if Path(gbaemu.__file__).resolve().parent != ROOT:
    raise SystemExit(f"載入非 repo 的 gbaemu：{gbaemu.__file__}（預期 {ROOT}）")

from gbaemu import Button, NativeEmulator  # noqa: E402

WIDTH, HEIGHT = 240, 160
RELEASE_FRAMES = 12

# suite ROM 內嵌的 Memory tests 清單順序（見 ROM 0x4CDF0 起的字串表）。
MEMORY_TESTS = [
    "ROM load",
    "ROM store",
    "ROM out-of-bounds load",
    "IWRAM load",
    "IWRAM mirror load",
    "IWRAM store",
    "IWRAM mirror store",
    "EWRAM load",
    "EWRAM mirror load",
    "EWRAM store",
    "EWRAM mirror store",
    "Palette load",
    "Palette mirror load",
    "Palette store",
    "Palette mirror store",
    "VRAM load",
    "VRAM mirror load",
    "VRAM store",
    "VRAM mirror store",
    "OAM load",
    "OAM mirror load",
    "OAM store",
    "OAM mirror store",
    "SRAM load",
    "SRAM mirror load",
    "SRAM store",
    "SRAM mirror store",
]


class Suite:
    """啟動 suite ROM 並提供 frame 推進、按鍵與截圖。"""

    def __init__(self, rom: Path) -> None:
        if not rom.exists():
            raise SystemExit(f"找不到 ROM：{rom}")
        self.rom = rom
        self.emu = NativeEmulator.from_rom(rom)
        self.frames = 0
        self._last_hash: bytes | None = None
        self._still = 0

    # -- frame 推進 ---------------------------------------------------
    def run(self, frames: int) -> None:
        for _ in range(frames):
            self.emu.step_frame()
            self.frames += 1

    def frame_hash(self) -> bytes:
        return hashlib.blake2b(self.emu.framebuffer(), digest_size=16).digest()

    def settle(
        self,
        *,
        limit: int = 40_000,
        stable: int = 60,
        label: str = "settle",
        progress: int = 600,
        must_change: bool = False,
    ) -> bool:
        """跑到畫面連續 ``stable`` 個 frame 不變；回傳是否真的穩定。

        ``must_change=True`` 時先等畫面至少變一次，避免把「Testing...」這種
        長時間靜止的進度畫面誤判成完成。
        """

        started = time.perf_counter()
        if must_change:
            baseline = self.frame_hash()
            for count in range(1, limit + 1):
                self.emu.step_frame()
                self.frames += 1
                if self.frame_hash() != baseline:
                    break
                if progress and count % progress == 0:
                    print(f"  [{label}] 等待畫面變化… {count} frames", file=sys.stderr)
            else:
                print(f"  [{label}] 畫面在 {limit} frames 內沒有變化", file=sys.stderr)
                return False
            self._last_hash = None
            self._still = 0
        for count in range(1, limit + 1):
            self.emu.step_frame()
            self.frames += 1
            digest = self.frame_hash()
            if digest == self._last_hash:
                self._still += 1
                if self._still >= stable:
                    elapsed = time.perf_counter() - started
                    print(
                        f"  [{label}] 畫面穩定於 frame {self.frames}"
                        f"（{count} frames / {elapsed:.2f}s）",
                        file=sys.stderr,
                    )
                    return True
            else:
                self._still = 0
                self._last_hash = digest
            if progress and count % progress == 0:
                print(f"  [{label}] {count} frames…", file=sys.stderr)
        print(f"  [{label}] 未穩定（達 {limit} frames 上限）", file=sys.stderr)
        return False

    # -- 輸入 ---------------------------------------------------------
    def tap(self, button: Button, *, release: int = RELEASE_FRAMES) -> None:
        self.emu.input.press(button)
        self.run(1)
        self.emu.input.release(button)
        self.run(release)

    def taps(self, button: Button, count: int) -> None:
        for _ in range(count):
            self.tap(button)

    # -- 輸出 ---------------------------------------------------------
    def shot(self, path: Path) -> None:
        from PIL import Image

        path.parent.mkdir(parents=True, exist_ok=True)
        image = Image.frombytes("RGB", (WIDTH, HEIGHT), self.emu.framebuffer())
        image.resize((WIDTH * 3, HEIGHT * 3), Image.NEAREST).save(path)
        print(f"  截圖：{path}")

    def red_rows(self) -> list[int]:
        """回傳畫面中含有紅字的文字列索引（由上往下算）。"""
        data = self.emu.framebuffer()
        red = [False] * HEIGHT
        black = [False] * HEIGHT
        for y in range(HEIGHT):
            base = y * WIDTH * 3
            for x in range(WIDTH):
                i = base + x * 3
                r, g, b = data[i], data[i + 1], data[i + 2]
                if r > 128 and g < 96 and b < 96:
                    red[y] = True
                elif r < 96 and g < 96 and b < 96:
                    black[y] = True
        rows: list[int] = []
        band = -1
        for y in range(HEIGHT):
            if red[y] or black[y]:
                if band < 0:
                    band = y
                last = y
            elif band >= 0:
                rows.append(band)
                band = -1
        if band >= 0:
            rows.append(band)
        # 只保留有紅字的列
        red_bands = []
        for start in rows:
            band_red = False
            for y in range(start, min(start + 8, HEIGHT)):
                if red[y]:
                    band_red = True
                    break
            if band_red:
                red_bands.append(start // 8)
        return red_bands

    def close(self) -> None:
        self.emu.close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rom", type=Path, default=ROOT / "rom" / "suite.gba")
    parser.add_argument(
        "phase",
        choices=("boot", "memory"),
        help="boot = 只到主選單；memory = 進入 Memory tests",
    )
    parser.add_argument("--taps", type=int, default=0, help="memory 清單中按 DOWN 的次數")
    parser.add_argument(
        "--suite",
        type=int,
        default=None,
        help="主選單中按 DOWN 的次數（0=Memory tests、9=DMA tests…）；省略則直接進 Memory tests",
    )
    parser.add_argument("--enter", action="store_true", help="在清單中按 A 進入細節")
    parser.add_argument("--scroll", type=int, default=0, help="細節畫面再按 DOWN 的次數")
    parser.add_argument("--tag", default="shot", help="輸出檔名 debug/suite_<tag>.png")
    parser.add_argument("--out", type=Path, default=None, help="直接指定輸出路徑")
    parser.add_argument("--limit", type=int, default=40_000, help="settle 的 frame 上限")
    parser.add_argument("--stable", type=int, default=60, help="settle 判定穩定的 frame 數")
    args = parser.parse_args(argv)

    out = args.out or ROOT / "debug" / f"suite_{args.tag}.png"
    suite = Suite(args.rom)
    try:
        print("[boot] 等待主選單…", file=sys.stderr)
        suite.settle(limit=args.limit, stable=args.stable, label="boot")

        if args.phase == "boot":
            suite.shot(out)
            print(f"  frames={suite.frames} red_rows={suite.red_rows()}")
            return 0

        print("[memory] 進入 Memory tests…", file=sys.stderr)
        if args.suite:
            print(f"[menu] DOWN × {args.suite} → suite {args.suite}…", file=sys.stderr)
            suite.taps(Button.DOWN, args.suite)
            suite.settle(limit=2000, stable=20, label="cursor")
        suite.tap(Button.A)
        # 群組測試會邊跑邊更新列表，中途可能有數十 frame 的靜止；先固定跑一段
        # 再等穩定，避免把「跑到一半」誤判成完成。
        suite.run(500)
        suite.settle(
            limit=args.limit,
            stable=max(args.stable, 180),
            label="memory",
        )

        if args.taps:
            print(f"[memory] DOWN × {args.taps}…", file=sys.stderr)
            suite.taps(Button.DOWN, args.taps)
            suite.settle(limit=2000, stable=20, label="cursor")
        suite.shot(out)
        print(f"  frames={suite.frames} red_rows={suite.red_rows()}")

        if args.enter:
            target = MEMORY_TESTS[args.taps] if 0 <= args.taps < len(MEMORY_TESTS) else "?"
            print(f"[detail] A → {target}…", file=sys.stderr)
            suite.tap(Button.A)
            suite.settle(limit=args.limit, stable=args.stable, label="detail")
            if args.scroll:
                print(f"[detail] DOWN × {args.scroll}…", file=sys.stderr)
                suite.taps(Button.DOWN, args.scroll)
                suite.settle(limit=2000, stable=20, label="scroll")
            detail = out.with_name(out.stem + "_detail.png")
            suite.shot(detail)
            print(f"  frames={suite.frames} red_rows={suite.red_rows()}")
        return 0
    finally:
        suite.close()


if __name__ == "__main__":
    raise SystemExit(main())
