"""Build the platform wheel with ``gbaemu._native``.

用法（repo root）：

    .\\venv\\Scripts\\python.exe tools\\build_wheel.py

流程：
1. maturin build 產生 PyO3 extension wheel。
2. 從 wheel 取出 ``_native.pyd``（或 .so/.dylib）放到套件根。
3. setuptools 打包成 ``gbaemu-...whl``（含 platform tag）。
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
NATIVE_DIST = ROOT / "dist_native"
WHEEL_DIST = ROOT / "dist"


def main() -> int:
    # 每次都用乾淨的 build/egg-info，避免上一個 Python 版本的產物混入。
    for stale in [ROOT / "build", *ROOT.glob("*.egg-info")]:
        if stale.is_dir():
            shutil.rmtree(stale)
        elif stale.exists():
            stale.unlink()
    if NATIVE_DIST.exists():
        shutil.rmtree(NATIVE_DIST)
    subprocess.run(
        [
            sys.executable,
            "-m",
            "maturin",
            "build",
            "--release",
            "--manifest-path",
            str(ROOT / "crates" / "gbaemu-python" / "Cargo.toml"),
            "--interpreter",
            sys.executable,
            "-o",
            str(NATIVE_DIST),
        ],
        check=True,
    )

    native_wheel = sorted(NATIVE_DIST.glob("*.whl"))[-1]
    with zipfile.ZipFile(native_wheel) as archive:
        candidates = [
            name
            for name in archive.namelist()
            if name.endswith((".pyd", ".so", ".dylib")) and "__init__" not in name
        ]
        if not candidates:
            raise SystemExit(f"{native_wheel} 內沒有 native extension")
        member = candidates[0]
        suffix = Path(member).suffix
        target = ROOT / f"_native{suffix}"
        target.write_bytes(archive.read(member))
        print(f"native extension: {target.name}")

    WHEEL_DIST.mkdir(exist_ok=True)
    env = os.environ.copy()
    env["GBAEMU_NATIVE_WHEEL"] = "1"
    subprocess.run(
        [sys.executable, "-m", "pip", "wheel", ".", "--no-deps", "-w", str(WHEEL_DIST)],
        cwd=ROOT,
        env=env,
        check=True,
    )
    wheel = sorted(WHEEL_DIST.glob("gbaemu-*.whl"))[-1]
    print(f"wheel: {wheel}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
