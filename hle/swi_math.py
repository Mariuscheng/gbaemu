"""BIOS SWI 的純數學／查表 helper（GBATEK 第 16 章）。

這些函式原本定義在 ``pygba/core/bios.py``，已由真 BIOS 輸出對照驗證：

* ``sdiv``：Div 的向零截斷、餘數符號同被除數。
* ``biostan``／``biosatan2``：ArcTan／ArcTan2 的真 BIOS 多項式與象限演算法。
* ``q8``／``SINTAB``：BgAffineSet／ObjAffineSet 的 Q8 正弦表與四捨六入。
* ``midi_val``：MidiKey2Freq 的 BIOS 查表。

新 ``gbaemu`` 的 HLE SWI 實作（Phase 3）直接使用此模組；舊 ``pygba`` 的
``bios.py`` 也改成 import 這裡，避免同一套數值邏輯存在兩份。
"""

from __future__ import annotations

import math

# MidiKey2Freq 用的 BIOS 資料表（BIOS 0x3104 起）：
# byte 表 = (shifts<<4)|index 編碼；word 表 = 2^(i/12) 的 Q31（i=0..11）
_MIDI_BYTE = bytes(((14 - i // 12) << 4) | (i % 12) for i in range(0xB4))
_MIDI_WORD = (
    0x80000000,
    0x879C7C97,
    0x8FACD61E,
    0x9837F052,
    0xA14517CC,
    0xAADC0848,
    0xB504F334,
    0xBFC886BB,
    0xCB2FF52A,
    0xD744FCCB,
    0xE411F03A,
    0xF1A1BF39,
)


def signed32(value: int) -> int:
    """無符號 32-bit → 有號整數（除法用）。"""

    return value - 0x100000000 if value >= 0x80000000 else value


def s16(value: int) -> int:
    """無符號 16-bit → 有號整數。"""

    return value - 0x10000 if value >= 0x8000 else value


def _build_sintab() -> tuple[int, ...]:
    """BIOS 用正弦表（Q8：sin×256，256 項）。

    已用真 BIOS 的 Bg/ObjAffineSet 輸出反推驗證：
    SINTAB[16]=97、[32]=181、[64]=256、[80]=236、[224]=-182（floor 語意）。
    """

    return tuple(
        int(math.floor(math.sin(i * 2.0 * math.pi / 256.0) * 256.0))
        for i in range(256)
    )


SINTAB = _build_sintab()


def q8(value: int) -> int:
    """Affine 用：v/256，四捨六入（0.5 取偶數）。

    已對照真 BIOS 的 16 組 Bg/ObjAffineSet 實測值（含 -145.5→-146、
    -90.5→-90 的判別案例）驗證此圓整行為。
    """

    quotient, remainder = divmod(value, 256)  # Python divmod 向 -∞ 取整
    if remainder > 128:
        return quotient + 1
    if remainder < 128:
        return quotient
    return quotient if quotient % 2 == 0 else quotient + 1


def sdiv(numerator: int, denominator: int) -> tuple[int, int]:
    """BIOS Div 語意（真 BIOS 0x3B4 演算法）：向零截斷、餘數符號同被除數。

    ``denominator == 0`` 時真機卡死；HLE 回傳 BIOS 的保護值：商 ±1、餘數同被除數。
    """

    if denominator == 0:
        return (1 if numerator >= 0 else -1), numerator
    quotient = abs(numerator) // abs(denominator)
    if (numerator < 0) != (denominator < 0):
        quotient = -quotient
    remainder = abs(numerator) % abs(denominator)
    if numerator < 0:
        remainder = -remainder
    return quotient, remainder


def biostan_parts(r0: int) -> tuple[int, int, int]:
    """ArcTan 的完整 BIOS register 輸出：(r0 結果, r1 中間值, r3 多項式)。"""

    r0 = signed32(r0)
    r1 = signed32((r0 * r0) & 0xFFFFFFFF) >> 14
    r1 = -r1
    r3 = 0xA9
    for add in (0x390, 0x91C, 0xFB6, 0x16AA, 0x2081, 0x3651, 0xA2F9):
        r3 = (signed32((r3 * r1) & 0xFFFFFFFF) >> 14) + add
    result = (signed32((r3 * r0) & 0xFFFFFFFF) >> 16) & 0xFFFFFFFF
    return result, r1 & 0xFFFFFFFF, r3 & 0xFFFFFFFF


def biostan(r0: int) -> int:
    """ArcTan（SWI 09h）——真 BIOS 0x474 多項式精確移植。

    輸入／輸出皆為 32-bit 原值（Q2.14 語意，1.0 = 0x4000）。
    已驗證：atan(0x1000)=0x9FB、atan(0x7FFF)=0x16D8。
    """

    return biostan_parts(r0)[0]


def biosatan2_parts(x: int, y: int) -> tuple[int, int]:
    """ArcTan2 的完整 BIOS 輸出：(r0 角度, r1 中間值)。"""

    x = signed32(x)
    y = signed32(y)
    if y == 0:
        return (0x8000 if x < 0 else 0), 0
    if x == 0:
        return (0xC000 if y < 0 else 0x4000), y & 0xFFFFFFFF
    r2 = (x << 14) & 0xFFFFFFFF  # x<<14（Thumb LSLS 32-bit）
    r3 = (y << 14) & 0xFFFFFFFF

    def atan(numerator: int, denominator: int) -> tuple[int, int]:
        quotient = sdiv(signed32(numerator), denominator)[0]
        result, r1, _ = biostan_parts(quotient)
        return result, r1

    if y > 0:
        if x > 0:
            if x < y:  # 0x550：0x4000 - atan(x/y)
                result, r1 = atan(r2, y)
                return (0x4000 - result) & 0xFFFFFFFF, r1
            return atan(r3, x)  # 0x542：atan(y/x)
        # y>0, x<0
        if -x < y:  # 0x550 路徑（r1 仍為 y）
            result, r1 = atan(r2, y)
            return (0x4000 - result) & 0xFFFFFFFF, r1
        result, r1 = atan(r3, x)  # 0x562：0x8000 + atan(y/x)
        return (0x8000 + result) & 0xFFFFFFFF, r1
    # y < 0
    if x > 0:
        if x < -y:  # 0x57a：0xC000 - atan(x/y)
            result, r1 = atan(r2, y)
            return (0xC000 - result) & 0xFFFFFFFF, r1
        result, r1 = atan(r3, x)  # 0x58e：0x10000 + atan(y/x)
        return (0x10000 + result) & 0xFFFFFFFF, r1
    # y<0, x<=0
    if -x > -y:  # 0x562 路徑
        result, r1 = atan(r3, x)
        return (0x8000 + result) & 0xFFFFFFFF, r1
    result, r1 = atan(r2, y)  # 0x57a：0xC000 - atan(x/y)
    return (0xC000 - result) & 0xFFFFFFFF, r1


def biosatan2(x: int, y: int) -> int:
    """ArcTan2（SWI 0Ah）——真 BIOS 0x4FC 象限演算法精確移植。

    輸入 x/y 為 32-bit（負值須已符號擴展，如 -1.0 = 0xFFFFC000）。
    輸出 0..0xFFFF 為 0..360°（例如 (-1,0)→0x8000、(0,-1)→0xC000）。
    """

    return biosatan2_parts(x, y)[0]


def midi_val(midi_key: int) -> int:
    """2^(midi_key/12) 的 BIOS 查表值（Q17，mk=0 → 0x20000）。"""

    packed = _MIDI_BYTE[midi_key]
    return _MIDI_WORD[packed & 0xF] >> (packed >> 4)


__all__ = [
    "SINTAB",
    "signed32",
    "s16",
    "q8",
    "sdiv",
    "biostan",
    "biosatan2",
    "midi_val",
]
