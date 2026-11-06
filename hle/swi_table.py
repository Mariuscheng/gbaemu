"""HLE SWI dispatch table 骨架（規格 2.1.2）。

Phase 0 只建立完整編號表、名稱、handler 註冊機制與 strict/lenient 行為；
真正的 SWI 行為（Div、CpuSet、LZ77/RL 解壓縮等）於 Phase 3 從既有
``pygba/core/bios.py`` 遷移（該檔已有 591 行、以真 BIOS 輸出對照過的實作）。

重要契約：

* ``0x2B``–``0xFF``：一律 raise ``HleUnsupportedSwiError``，lenient 模式也不例外。
* ``0x00``–``0x2A`` 尚未實作者：strict raise；lenient 記錄 warning 後 no-op。
* handler 以 ``handlers={swi_number: callable}`` 注入，callable 收一個 context。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from ..errors import HleUnsupportedSwiError
from ..log import get_logger

logger = get_logger("hle.swi_table")

MAX_DOCUMENTED_SWI = 0x2A

# GBATEK: BIOS Function Summary / BIOS Arithmetic Functions 等章節
SWI_NAMES: dict[int, str] = {
    0x00: "SoftReset",
    0x01: "RegisterRamReset",
    0x02: "Halt",
    0x03: "Stop",
    0x04: "IntrWait",
    0x05: "VBlankIntrWait",
    0x06: "Div",
    0x07: "DivArm",
    0x08: "Sqrt",
    0x09: "ArcTan",
    0x0A: "ArcTan2",
    0x0B: "CpuSet",
    0x0C: "CpuFastSet",
    0x0D: "GetBiosChecksum",
    0x0E: "BgAffineSet",
    0x0F: "ObjAffineSet",
    0x10: "BitUnPack",
    0x11: "LZ77UnCompWram",
    0x12: "LZ77UnCompVram",
    0x13: "HuffUnComp",
    0x14: "RLUnCompWram",
    0x15: "RLUnCompVram",
    0x16: "Diff8bitUnFilterWram",
    0x17: "Diff8bitUnFilterVram",
    0x18: "Diff16bitUnFilter",
    0x19: "SoundBias",
    0x1A: "SoundDriverInit",
    0x1B: "SoundDriverMode",
    0x1C: "SoundDriverMain",
    0x1D: "SoundDriverVSync",
    0x1E: "SoundChannelClear",
    0x1F: "MidiKey2Freq",
    0x20: "SoundWhatever0",
    0x21: "SoundWhatever1",
    0x22: "SoundWhatever2",
    0x23: "SoundWhatever3",
    0x24: "SoundWhatever4",
    0x25: "MultiBoot",
    0x26: "HardReset",
    0x27: "CustomHalt",
    0x28: "SoundDriverVSyncOff",
    0x29: "SoundDriverVSyncOn",
    0x2A: "SoundGetJumpList",
}

SwiHandler = Callable[[object | None], None]


@dataclass(frozen=True, slots=True)
class SwiEntry:
    number: int
    name: str
    implemented: bool


class SwiTable:
    """SWI 編號 → handler 的 dispatch table（Phase 0 骨架）。"""

    def __init__(
        self,
        *,
        strict: bool = True,
        handlers: dict[int, SwiHandler] | None = None,
    ) -> None:
        self.strict = bool(strict)
        self._handlers = dict(handlers or {})
        unknown = set(self._handlers) - set(SWI_NAMES)
        if unknown:
            raise ValueError(f"handler 指向未定義的 SWI：{sorted(unknown)}")
        self._entries = tuple(
            SwiEntry(number, name, number in self._handlers)
            for number, name in sorted(SWI_NAMES.items())
        )

    @property
    def entries(self) -> tuple[SwiEntry, ...]:
        return self._entries

    def lookup(self, number: int) -> SwiEntry | None:
        return next((entry for entry in self._entries if entry.number == number), None)

    def dispatch(self, number: int, context: object | None = None) -> None:
        if not isinstance(number, int) or not 0 <= number <= 0xFF:
            raise ValueError(f"SWI 編號必須是 0x00-0xFF 的整數，得到 {number!r}")

        if number > MAX_DOCUMENTED_SWI:
            # 真硬體會跳到 garbage address；HLE 一律明確報錯，不模擬 crash。
            raise HleUnsupportedSwiError(
                f"無效的 SWI 0x{number:02X}（GBATEK 只定義 0x00-0x2A）"
            )

        entry = self.lookup(number)
        assert entry is not None  # SWI_NAMES 已覆蓋 0x00-0x2A
        handler = self._handlers.get(number)
        if handler is not None:
            handler(context)
            return

        if self.strict:
            raise HleUnsupportedSwiError(
                f"SWI 0x{number:02X} ({entry.name}) 尚未實作（Phase 3）"
            )
        logger.warning("SWI 0x%02X (%s) 尚未實作；lenient 模式以 no-op 繼續", number, entry.name)

    def implemented_numbers(self) -> tuple[int, ...]:
        return tuple(entry.number for entry in self._entries if entry.implemented)


__all__ = [
    "MAX_DOCUMENTED_SWI",
    "SWI_NAMES",
    "SwiEntry",
    "SwiHandler",
    "SwiTable",
]
