"""Setuptools hook。

預設 build **純 Python wheel**（py3-none-any），冇 ``_native.pyd``，任何
Python 3.11+ 都裝到，會自動 fallback 去 Python reference backend。

要 build platform-specific native wheel（每個 Python 版本一個），先由
``tools/build_wheel.py`` 設定 ``GBAEMU_NATIVE_WHEEL=1``，setuptools 就會
將 ``_native.pyd/.so/.dylib`` 包入 wheel 並加上 platform tag。
"""

from __future__ import annotations

import os
from pathlib import Path

from setuptools import setup
from setuptools.dist import Distribution

_ROOT = Path(__file__).resolve().parent
_NATIVE_ENV = "GBAEMU_NATIVE_WHEEL"
_HAS_NATIVE = os.environ.get(_NATIVE_ENV) == "1"


class GbaemuDistribution(Distribution):
    def has_ext_modules(self) -> bool:
        return _HAS_NATIVE


setup(
    distclass=GbaemuDistribution,
    package_data={"gbaemu": ["_native.pyd", "_native.so", "_native.dylib"]}
    if _HAS_NATIVE
    else {},
    exclude_package_data={}
    if _HAS_NATIVE
    else {"gbaemu": ["_native.pyd", "_native.so", "_native.dylib"]},
)
