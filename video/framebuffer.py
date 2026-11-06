"""固定形狀的 RGB888 framebuffer。

規格 5.5：``VideoView.read_frame()`` 固定回傳 ``240 * 160 * 3`` bytes，
row-major、scanline 0 在前。Phase 0 只有零緩衝；Phase 2 由 PPU 写入。
"""

# GBATEK: LCD I/O Display Control - 240x160 LCD；此處固定為 host 端 RGB888
# 輸出格式，PPU 的實際繪製於 Phase 2/4 接上。
from __future__ import annotations

WIDTH = 240
HEIGHT = 160
BYTES_PER_PIXEL = 3
FRAME_SIZE = WIDTH * HEIGHT * BYTES_PER_PIXEL
SCANLINE_SIZE = WIDTH * BYTES_PER_PIXEL


class Framebuffer:
    def __init__(self) -> None:
        self._data = bytearray(FRAME_SIZE)

    def clear(self) -> None:
        self._data[:] = bytes(FRAME_SIZE)

    def read_frame(self, *, copy: bool = True) -> bytes:
        # bytes 本身不可變；copy 參數目前不改變語意（保留 API 相容性）。
        del copy
        return bytes(self._data)

    def read_scanline(self, line: int) -> bytes:
        if not 0 <= line < HEIGHT:
            raise ValueError(f"scanline 必須在 0-{HEIGHT - 1}，得到 {line}")
        start = line * SCANLINE_SIZE
        return bytes(self._data[start : start + SCANLINE_SIZE])

    def write_rgb888(self, data: bytes) -> None:
        if len(data) != FRAME_SIZE:
            raise ValueError(f"framebuffer 必須是 {FRAME_SIZE} bytes，得到 {len(data)}")
        self._data[:] = data


__all__ = [
    "WIDTH",
    "HEIGHT",
    "BYTES_PER_PIXEL",
    "FRAME_SIZE",
    "SCANLINE_SIZE",
    "Framebuffer",
]
