"""BG tile map 讀取（PyBoy ``game_area()`` 風格）。

直接經 ``emulator.memory`` 讀 DISPCNT／BGxCNT／BGxHOFS／BGxVOFS／VRAM，
唔依賴 Python renderer 內部狀態，所以 Python reference 同 Rust native 都用得。

回傳嘅 array 係整個 BG tile map（32x32、64x32、32x64、64x64，或者 affine
BG 嘅 16x16…128x128），每格係 tile 編號（0-1023；affine 係 0-255）。
"""

from __future__ import annotations

import numpy as np

VRAM_BASE = 0x06000000
_DISPCNT = 0x04000000
_BG_CNT = 0x04000008

_TEXT_SIZES = {
    0: (32, 32),
    1: (64, 32),
    2: (32, 64),
    3: (64, 64),
}
_AFFINE_SIZES = {0: 128, 1: 256, 2: 512, 3: 1024}


def _mode(dispcnt: int) -> int:
    return dispcnt & 0x7


def _enabled(dispcnt: int, layer: int) -> bool:
    return bool(dispcnt & (1 << (8 + layer)))


def _supported_layers(mode: int) -> tuple[int, ...]:
    if mode == 0:
        return (0, 1, 2, 3)
    if mode == 1:
        return (0, 1, 2)
    if mode == 2:
        return (2, 3)
    return ()


def _choose_layer(emulator, layer: int | None) -> int:
    mem = emulator.memory
    dispcnt = mem.read_u16(_DISPCNT)
    mode = _mode(dispcnt)
    supported = _supported_layers(mode)
    if not supported:
        raise ValueError(
            f"BG mode {mode} 係 bitmap mode，冇 tile map；請用 app.screen.ndarray"
        )
    if layer is None:
        for candidate in supported:
            if _enabled(dispcnt, candidate):
                return candidate
        raise ValueError("而家冇任何 BG layer 開啟")
    if not isinstance(layer, int) or isinstance(layer, bool):
        raise ValueError("layer 必須是整數")
    if layer not in supported:
        raise ValueError(f"BG mode {mode} 唔支援 BG{layer}（支援：{supported}）")
    if not _enabled(dispcnt, layer):
        raise ValueError(f"BG{layer} 而家冇開啟")
    return layer


def read_game_area(
    emulator,
    layer: int | None = None,
    *,
    include_attributes: bool = False,
) -> np.ndarray:
    """回傳 BG tile map，shape ``(tiles_y, tiles_x)``、dtype ``uint16``。

    Args:
        emulator: ``Emulator`` 或 ``NativeEmulator``。
        layer: BG0–BG3；``None`` 會揀第一個 enabled 嘅 BG。
        include_attributes: text BG 先有意義；``True`` 回傳完整 16-bit map
            entry（tile 編號＋palette／hflip／vflip），``False`` 只回 tile
            編號（``entry & 0x3FF``）。

    Raises:
        ValueError: bitmap mode、layer 唔存在／未開啟。
        ImportError: 冇安裝 numpy。
    """

    chosen = _choose_layer(emulator, layer)
    mem = emulator.memory
    dispcnt = mem.read_u16(_DISPCNT)
    mode = _mode(dispcnt)
    cnt = mem.read_u16(_BG_CNT + chosen * 2)
    screen_base = ((cnt >> 8) & 0x1F) * 0x800
    size_code = (cnt >> 14) & 0x3

    if (mode == 0 and chosen < 4) or (mode == 1 and chosen < 2):
        tiles_x, tiles_y = _TEXT_SIZES[size_code]
        blocks = tiles_x // 32
        out = np.empty((tiles_y, tiles_x), dtype=np.uint16)
        for ty in range(tiles_y):
            for tx in range(tiles_x):
                block = (tx // 32) + (ty // 32) * blocks
                offset = (
                    screen_base
                    + block * 0x800
                    + ((ty % 32) * 32 + (tx % 32)) * 2
                )
                entry = mem.read_u16(VRAM_BASE + offset)
                out[ty, tx] = entry if include_attributes else (entry & 0x3FF)
        return out

    # Affine BG（mode 1 的 BG2、mode 2 的 BG2/BG3）：map entry 係 1 byte。
    size = _AFFINE_SIZES[size_code]
    map_tiles = size // 8
    out = np.empty((map_tiles, map_tiles), dtype=np.uint16)
    for ty in range(map_tiles):
        for tx in range(map_tiles):
            out[ty, tx] = mem.read_u8(
                VRAM_BASE + screen_base + ty * map_tiles + tx
            )
    return out


__all__ = ["read_game_area"]
