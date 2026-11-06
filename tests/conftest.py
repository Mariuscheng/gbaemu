"""pytest 根 conftest。

本專案把**專案根目錄本身**當成 ``gbaemu`` 套件（根目錄有 ``__init__.py``，
沒有內層 ``gbaemu/``）。測試以頂層名稱匯入 ``tests.*``（例如
``tests.reference.gba_cpu``），所以要把專案根目錄加進 ``sys.path``；同時
把上一層也加進去，讓未 ``pip install`` 的 clone 都直接 ``import gbaemu``。
"""

from __future__ import annotations

import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_ROOT = _HERE.parent  # repo root（= gbaemu 套件根）
_PARENT = _ROOT.parent  # 讓 `import gbaemu` 找到工作樹

for _path in (_ROOT, _PARENT):
    if str(_path) not in sys.path:
        sys.path.append(str(_path))
