"""gbaemu 的例外類別。

權威定義見 ``docs/GBA 模擬器與 RL 介面設計規格（Struct 完整版）.md`` 第 5.9 節。
所有公開例外都衍生自 :class:`GbaEmuError`，讓呼叫端可以只攔截一個基底類別。
"""

from __future__ import annotations


class GbaEmuError(Exception):
    """所有 gbaemu 例外的基底類別。"""


class InvalidConfigError(GbaEmuError):
    """``EmulatorConfig`` 違反契約（例如 REQUIRE_BIOS 缺少 bios_path）。"""


class RomInvalidError(GbaEmuError):
    """ROM 太小、無法讀取或 header 無效。"""


class BiosMissingError(GbaEmuError):
    """REQUIRE_BIOS 模式下找不到使用者提供的 BIOS 檔案。"""


class BiosChecksumError(GbaEmuError):
    """BIOS 檔案大小或內容檢查失敗。"""


class UnsupportedSaveTypeError(GbaEmuError):
    """要求的 save 類型尚未實作，或無法辨識。"""


class HleUnsupportedSwiError(GbaEmuError):
    """HLE 無法處理的 SWI（未實作或無效編號，見規格 2.1.2）。"""


class ReadOnlyMemoryError(GbaEmuError):
    """除錯寫入嘗試修改 ROM、BIOS 或其他唯讀區域。"""


class BreakpointError(GbaEmuError):
    """breakpoint id 不存在或引數不合法。"""


class SnapshotError(GbaEmuError):
    """snapshot 相關錯誤的基底類別。"""


class SnapshotCorruptError(SnapshotError):
    """長度、magic 或 CRC-32 檢查失敗。"""


class SnapshotVersionError(SnapshotError):
    """snapshot 格式版本不受支援。"""


class SnapshotRomMismatchError(SnapshotError):
    """snapshot 的 ROM SHA-256 與目前載入的 ROM 不符。"""


class SnapshotConfigMismatchError(SnapshotError):
    """snapshot 的 config SHA-256 與目前設定不符。"""


__all__ = [
    "GbaEmuError",
    "InvalidConfigError",
    "RomInvalidError",
    "BiosMissingError",
    "BiosChecksumError",
    "UnsupportedSaveTypeError",
    "HleUnsupportedSwiError",
    "ReadOnlyMemoryError",
    "BreakpointError",
    "SnapshotError",
    "SnapshotCorruptError",
    "SnapshotVersionError",
    "SnapshotRomMismatchError",
    "SnapshotConfigMismatchError",
]
