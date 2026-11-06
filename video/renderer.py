"""PPU 畫面合成（Phase 4）：Mode 0/1/2/3/4/5、BG、OBJ、alpha/brightness。

座標系：240x160、RGB888 framebuffer。優先度數字越小越前面；同優先度時
BG 索引小者在前、OAM 索引小者在前（GBATEK: GBA LCD Dimensions / BG Priority）。

Phase 4 效能版：每 frame 先把 BG 描述、palette LUT、active OAM、window/blend
狀態快照成 RenderState；pixel loop 只做陣列查表，不再逐 pixel 呼叫
``ppu.read_reg16()`` / ``vram.read_u8()`` / ``palette.read_u16()``。

# GBATEK: GBA Video - BG Control、BG Affine、OBJ Attributes、Window、Blending
"""

from __future__ import annotations

WIDTH = 240
HEIGHT = 160

# text BG 尺寸（tiles）
_TEXT_SIZES = {
    0: (32, 32),
    1: (64, 32),
    2: (32, 64),
    3: (64, 64),
}
_AFFINE_SIZES = {0: 128, 1: 256, 2: 512, 3: 1024}

# shape, size → (w, h)
_OBJ_SIZES = {
    0: {0: (8, 8), 1: (16, 16), 2: (32, 32), 3: (64, 64)},
    1: {0: (16, 8), 1: (32, 8), 2: (32, 16), 3: (64, 32)},
    2: {0: (8, 16), 1: (8, 32), 2: (16, 32), 3: (32, 64)},
}


def _s16(value: int) -> int:
    return value - 0x10000 if value & 0x8000 else value


def _s32(value: int) -> int:
    value &= 0xFFFFFFFF
    return value - 0x100000000 if value & 0x80000000 else value


_FADE_LUTS: dict[tuple[int, bool], tuple[int, ...]] = {}


def _fade_lut(amount: int, fade_in: bool) -> tuple[int, ...]:
    """BLDY fade 只依 value／amount／方向；每 frame 快取成 32K LUT。"""

    key = (amount, fade_in)
    cached = _FADE_LUTS.get(key)
    if cached is None:
        cached = tuple(_fade(value, amount, fade_in) for value in range(0x8000))
        _FADE_LUTS[key] = cached
    return cached


def rgb555_to_rgb888(value: int) -> tuple[int, int, int]:
    r = value & 0x1F
    g = (value >> 5) & 0x1F
    b = (value >> 10) & 0x1F
    return (r << 3) | (r >> 2), (g << 3) | (g >> 2), (b << 3) | (b >> 2)


class _TextBg:
    __slots__ = (
        "bg",
        "priority",
        "char_base",
        "screen_base",
        "tiles_x",
        "width_px",
        "height_px",
        "hofs",
        "vofs",
        "color_256",
        "mosaic",
        "blocks",
    )


class _AffineBg:
    __slots__ = (
        "bg",
        "priority",
        "char_base",
        "screen_base",
        "size",
        "pa",
        "pb",
        "pc",
        "pd",
        "ref_x",
        "ref_y",
        "wrap",
        "mosaic",
    )


class _Sprite:
    __slots__ = (
        "index",
        "x",
        "y",
        "w",
        "h",
        "priority",
        "palette",
        "color_256",
        "affine",
        "pa",
        "pb",
        "pc",
        "pd",
        "tile",
        "hflip",
        "vflip",
        "mosaic",
    )


class _RenderState:
    __slots__ = (
        "vram",
        "oam",
        "bg_palette",
        "obj_palette",
        "text_layers",
        "affine_layers",
        "sprites",
        "alpha_enabled",
        "fade_enabled",
        "eva",
        "evb",
        "fade",
        "fade_lut",
        "bld_targets",
        "bld_second",
        "fade_in",
        "winin",
        "winout",
        "win0h",
        "win0v",
        "win1h",
        "win1v",
        "win0_on",
        "win1_on",
        "windows_enabled",
        "obj_1d",
        "sprite_color",
        "sprite_priority",
        "sprite_index",
    )


def _build_state(ppu, vram, palette, oam) -> _RenderState:
    regs = ppu.read_reg16
    state = _RenderState()
    state.vram = vram._data
    state.oam = oam._data if oam is not None else b""
    palette_data = palette._data
    state.bg_palette = [
        palette_data[index * 2] | (palette_data[index * 2 + 1] << 8)
        for index in range(256)
    ]
    state.obj_palette = [
        palette_data[0x200 + index * 2] | (palette_data[0x200 + index * 2 + 1] << 8)
        for index in range(256)
    ]
    dispcnt = ppu.dispcnt
    mode = dispcnt & 0x7
    mosaic = regs(0x04C)
    state.text_layers = []
    state.affine_layers = []
    if mode in (0, 1):
        for bg in range(4):
            if mode == 1 and bg >= 2:
                continue
            if not (dispcnt & (1 << (8 + bg))):
                continue
            cnt = regs(0x008 + bg * 2)
            layer = _TextBg()
            layer.bg = bg
            layer.priority = cnt & 0x3
            layer.char_base = ((cnt >> 2) & 0x3) * 0x4000
            layer.screen_base = ((cnt >> 8) & 0x1F) * 0x800
            size = (cnt >> 14) & 0x3
            layer.tiles_x, tiles_y = _TEXT_SIZES[size]
            layer.width_px, layer.height_px = layer.tiles_x * 8, tiles_y * 8
            layer.hofs = regs(0x010 + bg * 4)
            layer.vofs = regs(0x012 + bg * 4)
            layer.color_256 = bool(cnt & 0x0080)
            layer.mosaic = ((mosaic & 0xF) + 1) if (cnt & 0x40) else 1
            layer.blocks = layer.tiles_x // 32
            state.text_layers.append(layer)
    if mode in (1, 2):
        for bg in ((2,) if mode == 1 else (2, 3)):
            if not (dispcnt & (1 << (8 + bg))):
                continue
            cnt = regs(0x008 + bg * 2)
            layer = _AffineBg()
            layer.bg = bg
            layer.priority = cnt & 0x3
            layer.char_base = ((cnt >> 2) & 0x3) * 0x4000
            layer.screen_base = ((cnt >> 8) & 0x1F) * 0x800
            layer.size = _AFFINE_SIZES[(cnt >> 14) & 0x3]
            base = 0x020 + (bg - 2) * 0x10
            layer.pa = _s16(regs(base + 0x0))
            layer.pb = _s16(regs(base + 0x2))
            layer.pc = _s16(regs(base + 0x4))
            layer.pd = _s16(regs(base + 0x6))
            layer.ref_x = _s32(regs(base + 0x8))
            layer.ref_y = _s32(regs(base + 0xC))
            layer.wrap = bool(cnt & 0x2000)
            layer.mosaic = ((mosaic & 0xF) + 1) if (cnt & 0x40) else 1
            state.affine_layers.append(layer)

    state.sprites = []
    state.obj_1d = bool(dispcnt & 0x0040)
    if (dispcnt & 0x1000) and oam is not None:
        oam_data = state.oam
        for index in range(128):
            attr0 = oam_data[index * 8] | (oam_data[index * 8 + 1] << 8)
            if (attr0 & 0x0200) and not (attr0 & 0x0100):
                continue
            shape = (attr0 >> 14) & 0x3
            if shape == 3:
                continue
            attr1 = oam_data[index * 8 + 2] | (oam_data[index * 8 + 3] << 8)
            attr2 = oam_data[index * 8 + 4] | (oam_data[index * 8 + 5] << 8)
            size = (attr1 >> 14) & 0x3
            width, height = _OBJ_SIZES[shape][size]
            sprite = _Sprite()
            sprite.index = index
            sprite.x = attr1 & 0x1FF
            if sprite.x >= 256:
                sprite.x -= 512
            sprite.y = attr0 & 0xFF
            if sprite.y >= 160:
                sprite.y -= 256
            sprite.affine = bool(attr0 & 0x0100)
            double_size = bool(attr0 & 0x0200)
            if double_size:
                width *= 2
                height *= 2
            sprite.w = width
            sprite.h = height
            if (
                sprite.x >= WIDTH
                or sprite.x + width <= 0
                or sprite.y >= HEIGHT
                or sprite.y + height <= 0
            ):
                continue
            sprite.priority = (attr2 >> 10) & 0x3
            sprite.palette = (attr2 >> 12) & 0xF
            sprite.color_256 = bool(attr0 & 0x2000)
            sprite.tile = attr2 & 0x3FF
            sprite.hflip = bool(attr1 & 0x1000)
            sprite.vflip = bool(attr1 & 0x2000)
            sprite.mosaic = ((mosaic >> 4) + 1) if (attr0 & 0x1000) else 1
            if sprite.affine:
                group = (attr1 >> 9) & 0x1F
                # OAM affine params: PA/PB/PC/PD interleaved, 32 bytes per group.
                param = 6 + group * 32
                sprite.pa = _s16(oam_data[param] | (oam_data[param + 1] << 8))
                sprite.pb = _s16(oam_data[param + 8] | (oam_data[param + 9] << 8))
                sprite.pc = _s16(oam_data[param + 16] | (oam_data[param + 17] << 8))
                sprite.pd = _s16(oam_data[param + 24] | (oam_data[param + 25] << 8))
            state.sprites.append(sprite)

    control = regs(0x050)
    alpha = regs(0x052)
    # GBATEK BLDCNT：bit6-7 是 2-bit 效果模式（0=none、1=alpha、2=變亮、3=變暗），
    # 不是兩個獨立 enable bit。BLDCNT=0x00FF 是「變暗」，不是 alpha+EVA=0。
    effect = (control >> 6) & 0x3
    state.alpha_enabled = effect == 1
    state.fade_enabled = effect in (2, 3)
    state.eva = min(alpha & 0x1F, 16)
    state.evb = min((alpha >> 8) & 0x1F, 16)
    state.fade = min(regs(0x054) & 0x1F, 16)
    state.fade_in = effect == 2
    state.fade_lut = _fade_lut(state.fade, state.fade_in) if state.fade_enabled else None
    state.bld_targets = control & 0x3F
    state.bld_second = (control >> 8) & 0x3F
    state.winin = regs(0x048)
    state.winout = regs(0x04A)
    state.win0h = regs(0x040)
    state.win1h = regs(0x042)
    state.win0v = regs(0x044)
    state.win1v = regs(0x046)
    state.windows_enabled = dispcnt & 0xE000
    state.win0_on = bool(state.windows_enabled & 0x2000)
    state.win1_on = bool(state.windows_enabled & 0x4000)
    return state



def _text_buffer(state: _RenderState, layer: _TextBg) -> bytearray:
    """把一個 text BG 先解成 240x160 palette-index buffer。

    以 tile 為單位解碼：每個 scanline 只讀一次 tile map、每個 tile 只算一次
    char base；pixel 只做 nibble/byte lookup。mosaic 由 caller fallback 到
    _text_pixel。
    """

    vram = state.vram
    width, height = WIDTH, HEIGHT
    out = bytearray(width * height)
    width_px, height_px = layer.width_px, layer.height_px
    blocks = layer.blocks
    color_256 = layer.color_256
    char_base = layer.char_base
    screen_base = layer.screen_base
    hofs, vofs = layer.hofs, layer.vofs

    for y in range(height):
        sy = (y + vofs) % height_px
        py = sy & 7
        ty = sy >> 3
        row_base = (ty // 32) * blocks * 0x800 + (ty % 32) * 64
        src_x = hofs % width_px
        x = 0
        while x < width:
            tx = src_x >> 3
            address = screen_base + row_base + (tx // 32) * 0x800 + (tx % 32) * 2
            tile = vram[address] | (vram[address + 1] << 8)
            tile_index = tile & 0x3FF
            px_start = src_x & 7
            run = 8 - px_start
            if x + run > width:
                run = width - x
            row_py = 7 - py if (tile & 0x0800) else py
            if color_256:
                base = char_base + tile_index * 64 + row_py * 8
                if tile & 0x0400:
                    for k in range(run):
                        value = vram[base + 7 - (px_start + k)]
                        if value:
                            out[y * width + x + k] = value
                else:
                    for k in range(run):
                        value = vram[base + px_start + k]
                        if value:
                            out[y * width + x + k] = value
            else:
                base = char_base + tile_index * 32 + row_py * 4
                bank = (tile >> 12) << 4
                if tile & 0x0400:  # hflip
                    for k in range(run):
                        px = 7 - (px_start + k)
                        byte = vram[base + (px >> 1)]
                        value = (byte >> ((px & 1) * 4)) & 0x0F
                        if value:
                            out[y * width + x + k] = bank + value
                else:
                    for k in range(run):
                        px = px_start + k
                        byte = vram[base + (px >> 1)]
                        value = (byte >> ((px & 1) * 4)) & 0x0F
                        if value:
                            out[y * width + x + k] = bank + value
            x += run
            src_x += run
            if src_x >= width_px:
                src_x -= width_px
    return out


def _blit_single_text(state: _RenderState, layer: _TextBg, buffer: bytearray,
                      pixels: bytearray, backdrop: int,
                      y0: int = 0, y1: int = HEIGHT) -> None:
    """單一 text BG、無 window/OBJ/alpha 的快速輸出（可只畫 y0..y1 行）。"""

    palette = state.bg_palette
    fade_lut = state.fade_lut if state.fade_enabled else None
    rgb_lut = []
    if fade_lut is None:
        for value in palette:
            r, g, b = value & 0x1F, (value >> 5) & 0x1F, (value >> 10) & 0x1F
            rgb_lut.append(bytes(((r << 3) | (r >> 2), (g << 3) | (g >> 2), (b << 3) | (b >> 2))))
    else:
        for value in palette:
            value = fade_lut[value & 0x7FFF]
            r, g, b = value & 0x1F, (value >> 5) & 0x1F, (value >> 10) & 0x1F
            rgb_lut.append(bytes(((r << 3) | (r >> 2), (g << 3) | (g >> 2), (b << 3) | (b >> 2))))
    start = y0 * WIDTH
    end = y1 * WIDTH
    pixels[start * 3:end * 3] = b"".join(rgb_lut[color] for color in buffer[start:end])


def _text_pixel(state: _RenderState, layer: _TextBg, x: int, y: int):
    mosaic = layer.mosaic
    if mosaic > 1:
        x -= x % mosaic
        y -= y % mosaic
    sx = (x + layer.hofs) % layer.width_px
    sy = (y + layer.vofs) % layer.height_px
    tx, ty = sx // 8, sy // 8
    block = (tx // 32) + (ty // 32) * layer.blocks
    map_offset = block * 0x800 + ((ty % 32) * 32 + (tx % 32)) * 2
    vram = state.vram
    address = layer.screen_base + map_offset
    tile = vram[address] | (vram[address + 1] << 8)
    px, py = sx % 8, sy % 8
    tile_index = tile & 0x3FF
    if layer.color_256:
        if tile & 0x0400:
            px = 7 - px
        if tile & 0x0800:
            py = 7 - py
        value = vram[layer.char_base + tile_index * 64 + py * 8 + px]
        return value or None
    if tile & 0x0400:
        px = 7 - px
    if tile & 0x0800:
        py = 7 - py
    byte = vram[layer.char_base + tile_index * 32 + py * 4 + px // 2]
    value = (byte >> ((px & 1) * 4)) & 0x0F
    if value == 0:
        return None
    return (tile >> 12) * 16 + value


def _affine_pixel(state: _RenderState, layer: _AffineBg, x: int, y: int):
    mosaic = layer.mosaic
    if mosaic > 1:
        x -= x % mosaic
        y -= y % mosaic
    size = layer.size
    tex_x = (layer.ref_x + x * layer.pa + y * layer.pb) >> 8
    tex_y = (layer.ref_y + x * layer.pc + y * layer.pd) >> 8
    if layer.wrap:
        sx = tex_x & (size - 1)
        sy = tex_y & (size - 1)
    else:
        if not (0 <= tex_x < size and 0 <= tex_y < size):
            return None
        sx, sy = tex_x, tex_y
    vram = state.vram
    map_offset = (sy // 8) * (size // 8) + (sx // 8)
    tile = vram[layer.screen_base + map_offset]
    value = vram[layer.char_base + tile * 64 + (sy % 8) * 8 + (sx % 8)]
    return value or None



def _build_sprite_buffer(state: _RenderState) -> None:
    """只掃 sprite 覆蓋的 pixel，建立 per-pixel sprite layer。"""

    width, height = WIDTH, HEIGHT
    color = bytearray(width * height)
    priority = bytearray(b"\xFF" * (width * height))
    order = bytearray(b"\xFF" * (width * height))
    for sprite in state.sprites:
        y0 = max(0, sprite.y)
        y1 = min(height, sprite.y + sprite.h)
        x0 = max(0, sprite.x)
        x1 = min(width, sprite.x + sprite.w)
        for y in range(y0, y1):
            row = y * width
            for x in range(x0, x1):
                value = _sprite_pixel(state, sprite, x, y)
                if value is None:
                    continue
                index = row + x
                current_priority = priority[index]
                if sprite.priority > current_priority:
                    continue
                if sprite.priority == current_priority and sprite.index >= order[index]:
                    continue
                priority[index] = sprite.priority
                order[index] = sprite.index
                color[index] = value
    state.sprite_color = color
    state.sprite_priority = priority
    state.sprite_index = order


def _sprite_pixel(state: _RenderState, sprite: _Sprite, x: int, y: int):
    mosaic = sprite.mosaic
    if mosaic > 1:
        x -= x % mosaic
        y -= y % mosaic
    dx = x - sprite.x
    dy = y - sprite.y
    width, height = sprite.w, sprite.h
    if not (0 <= dx < width and 0 <= dy < height):
        return None
    if sprite.affine:
        cx = dx - width // 2
        cy = dy - height // 2
        tex_x = (sprite.pa * cx + sprite.pb * cy) >> 8
        tex_y = (sprite.pc * cx + sprite.pd * cy) >> 8
        tex_x += width // 2
        tex_y += height // 2
        if not (0 <= tex_x < width and 0 <= tex_y < height):
            return None
        px, py = tex_x, tex_y
    else:
        px, py = dx, dy
        if sprite.hflip:
            px = width - 1 - px
        if sprite.vflip:
            py = height - 1 - py
    vram = state.vram
    step = 2 if sprite.color_256 else 1
    if state.obj_1d:
        tile_index = (
            sprite.tile
            + (py // 8) * (sprite.w // 8) * step
            + (px // 8) * step
        )
    else:
        # 2D mapping：tile 號以 32 個 4bpp tile（16 個 8bpp）為一列。
        tile_index = sprite.tile + (py // 8) * 32 + (px // 8) * step
    if sprite.color_256:
        tile_index &= 0x3FE
        address = 0x10000 + tile_index * 32 + (py % 8) * 8 + (px % 8)
        value = vram[address]
        return value or None
    tile_index &= 0x3FF
    address = 0x10000 + tile_index * 32 + (py % 8) * 4 + (px % 8) // 2
    byte = vram[address]
    value = (byte >> (((px % 8) & 1) * 4)) & 0x0F
    return value or None


def _pick_sprite(state: _RenderState, x: int, y: int):
    best_priority = 5
    best_index = 256
    best_color = 0
    for sprite in state.sprites:
        value = _sprite_pixel(state, sprite, x, y)
        if value is None:
            continue
        if (sprite.priority, sprite.index) >= (best_priority, best_index):
            continue
        best_priority = sprite.priority
        best_index = sprite.index
        if sprite.color_256:
            best_color = state.obj_palette[value]
        else:
            best_color = state.obj_palette[sprite.palette * 16 + value]
    if best_index == 256:
        return None
    return best_priority, best_index, best_color


def _window_inside(h: int, v: int, x: int, y: int) -> bool:
    """真機 window 範圍：高位 byte = X1/Y1、低位 byte = X2/Y2。

    GBATEK：「X2>240 或 X1>X2 都當成 X2=240」，Y 軸同理（Y2=160）。
    """
    x1 = min((h >> 8) & 0xFF, WIDTH)
    x2 = min(h & 0xFF, WIDTH)
    if x1 > x2:
        x2 = WIDTH
    y1 = min((v >> 8) & 0xFF, HEIGHT)
    y2 = min(v & 0xFF, HEIGHT)
    if y1 > y2:
        y2 = HEIGHT
    return x1 <= x < x2 and y1 <= y < y2


def _window_mask(state: _RenderState, x: int, y: int) -> int:
    if not state.windows_enabled:
        return 0x3F
    # 暫存器順序：0x040 WIN0H、0x042 WIN1H、0x044 WIN0V、0x046 WIN1V。
    # WININ 低 6 bit 是 WIN0、bit8-13 是 WIN1；WINOUT 低 6 bit 係窗外、
    # bit8-13 係 OBJ window 內。
    if state.win0_on and _window_inside(state.win0h, state.win0v, x, y):
        return state.winin & 0x3F
    if state.win1_on and _window_inside(state.win1h, state.win1v, x, y):
        return (state.winin >> 8) & 0x3F
    return state.winout & 0x3F


def render_frame(ppu, vram, framebuffer, palette, oam,
                 y0: int = 0, y1: int = HEIGHT) -> None:
    if not ppu.render_enabled:
        return
    width, height = WIDTH, HEIGHT
    pixels = getattr(framebuffer, "_data", None)
    commit = pixels is None
    if pixels is None:
        pixels = bytearray(width * height * 3)
    dispcnt = ppu.dispcnt

    if dispcnt & 0x80:  # force blank
        pixels[y0 * width * 3:y1 * width * 3] = b"\xFF" * ((y1 - y0) * width * 3)
        if commit:
            framebuffer.write_rgb888(bytes(pixels))
        return

    mode = dispcnt & 0x7
    if mode in (3, 4, 5):
        bmp_state = _build_state(ppu, vram, palette, oam)
        if bmp_state.sprites:
            _build_sprite_buffer(bmp_state)
        if (
            bmp_state.sprites
            or bmp_state.alpha_enabled
            or bmp_state.fade_enabled
            or bmp_state.windows_enabled
        ):
            _render_bitmap_composite(ppu, bmp_state, dispcnt, mode, pixels, y0, y1)
        else:
            _render_bitmap(ppu, vram, palette, dispcnt, mode, pixels, y0, y1)
        if commit:
            framebuffer.write_rgb888(bytes(pixels))
        return

    state = _build_state(ppu, vram, palette, oam)
    backdrop = state.bg_palette[0]
    if mode in (0, 1, 2) and not (dispcnt & 0x1F00):
        r, g, b = backdrop & 0x1F, (backdrop >> 5) & 0x1F, (backdrop >> 10) & 0x1F
        pixel = bytes((((r << 3) | (r >> 2)), ((g << 3) | (g >> 2)), ((b << 3) | (b >> 2))))
        pixels[y0 * width * 3:y1 * width * 3] = pixel * ((y1 - y0) * width)
        if commit:
            framebuffer.write_rgb888(bytes(pixels))
        return

    text_layers = state.text_layers
    affine_layers = state.affine_layers
    sprites_enabled = bool(dispcnt & 0x1000) and state.sprites
    alpha_enabled = state.alpha_enabled
    fade_enabled = state.fade_enabled
    bld_targets = state.bld_targets
    bld_second = state.bld_second
    eva, evb, fade = state.eva, state.evb, state.fade
    fade_in = state.fade_in
    windows_enabled = state.windows_enabled

    partial = y0 != 0 or y1 != HEIGHT

    # 最常見的 GUI／RL 畫面：單一 text BG、無 OBJ/window/alpha。
    if (
        not partial
        and len(text_layers) == 1
        and not affine_layers
        and not state.sprites
        and not windows_enabled
        and not state.alpha_enabled
        and text_layers[0].mosaic <= 1
    ):
        buffer = _text_buffer(state, text_layers[0])
        _blit_single_text(state, text_layers[0], buffer, pixels, backdrop, y0, y1)
        if commit:
            framebuffer.write_rgb888(bytes(pixels))
        return

    text_buffers = [
        None if partial else (_text_buffer(state, layer) if layer.mosaic <= 1 else None)
        for layer in text_layers
    ]
    if sprites_enabled:
        _build_sprite_buffer(state)

    for y in range(y0, y1):
        for x in range(width):
            mask = _window_mask(state, x, y) if windows_enabled else 0x3F
            best_priority = 5
            best_order = 5
            best_value = 0
            best_is_sprite = False
            second_priority = 5
            second_order = 5
            second_value = 0
            second_is_sprite = False
            for layer, buffer in zip(text_layers, text_buffers):
                if not (mask & (1 << layer.bg)):
                    continue
                if buffer is None:
                    color = _text_pixel(state, layer, x, y)
                else:
                    color = buffer[y * width + x]
                if not color:
                    continue
                priority = layer.priority
                value = state.bg_palette[color]
                if (priority, layer.bg) < (best_priority, best_order):
                    second_priority, second_order = best_priority, best_order
                    second_value, second_is_sprite = best_value, best_is_sprite
                    best_priority, best_order = priority, layer.bg
                    best_value, best_is_sprite = value, False
                elif (priority, layer.bg) < (second_priority, second_order):
                    second_priority, second_order = priority, layer.bg
                    second_value, second_is_sprite = value, False
            for layer in affine_layers:
                if not (mask & (1 << layer.bg)):
                    continue
                color = _affine_pixel(state, layer, x, y)
                if color is None:
                    continue
                priority = layer.priority
                value = state.bg_palette[color]
                if (priority, layer.bg) < (best_priority, best_order):
                    second_priority, second_order = best_priority, best_order
                    second_value, second_is_sprite = best_value, best_is_sprite
                    best_priority, best_order = priority, layer.bg
                    best_value, best_is_sprite = value, False
                elif (priority, layer.bg) < (second_priority, second_order):
                    second_priority, second_order = priority, layer.bg
                    second_value, second_is_sprite = value, False
            if sprites_enabled and (mask & 0x10):
                index = y * width + x
                if state.sprite_color[index]:
                    priority = state.sprite_priority[index]
                    value = state.obj_palette[state.sprite_color[index]]
                    # GBATEK Video/OBJ "Priority"：OBJ 與 BG 同 priority 時 OBJ
                    # 在上層；sprite 用 -1 保證贏過 BG0-3（order 0..3）。
                    order = -1
                    if (priority, order) < (best_priority, best_order):
                        second_priority, second_order = best_priority, best_order
                        second_value, second_is_sprite = best_value, best_is_sprite
                        best_priority, best_order = priority, order
                        best_value, best_is_sprite = value, True
                    elif (priority, order) < (second_priority, second_order):
                        second_priority, second_order = priority, order
                        second_value, second_is_sprite = value, True

            if best_priority == 5:
                value = backdrop
            else:
                value = best_value
                if not (mask & 0x20):
                    pass
                elif alpha_enabled and (bld_targets & (0x10 if best_is_sprite else (1 << best_order))):
                    if second_priority != 5 and (
                        bld_second & (0x10 if second_is_sprite else (1 << second_order))
                    ):
                        value = _mix(second_value, value, eva, evb)
                    elif bld_second & 0x20:
                        value = _mix(backdrop, value, eva, evb)
                elif fade_enabled and (bld_targets & (0x10 if best_is_sprite else (1 << best_order))):
                    value = state.fade_lut[value & 0x7FFF]
            r, g, b = value & 0x1F, (value >> 5) & 0x1F, (value >> 10) & 0x1F
            out = (y * width + x) * 3
            pixels[out] = (r << 3) | (r >> 2)
            pixels[out + 1] = (g << 3) | (g >> 2)
            pixels[out + 2] = (b << 3) | (b >> 2)
    if commit:
        framebuffer.write_rgb888(bytes(pixels))


def _mix(bottom: int, top: int, eva: int, evb: int) -> int:
    br, bg, bb = bottom & 0x1F, (bottom >> 5) & 0x1F, (bottom >> 10) & 0x1F
    tr, tg, tb = top & 0x1F, (top >> 5) & 0x1F, (top >> 10) & 0x1F
    r = min(31, (tr * eva + br * evb) >> 4)
    g = min(31, (tg * eva + bg * evb) >> 4)
    b = min(31, (tb * eva + bb * evb) >> 4)
    return r | (g << 5) | (b << 10)


def _fade(value: int, amount: int, fade_in: bool) -> int:
    r, g, b = value & 0x1F, (value >> 5) & 0x1F, (value >> 10) & 0x1F
    if fade_in:
        r = min(31, r + amount)
        g = min(31, g + amount)
        b = min(31, b + amount)
    else:
        r = max(0, r - amount)
        g = max(0, g - amount)
        b = max(0, b - amount)
    return r | (g << 5) | (b << 10)


def _render_bitmap(ppu, vram, palette, dispcnt, mode: int, pixels: bytearray,
                   y0: int = 0, y1: int = HEIGHT) -> None:
    """Mode 3/4/5 的快速路徑（無 OBJ/alpha/fade/window）。

    GBATEK: bitmap 以 BG2 實作；mode 4 的 index 0 是透明（顯示 backdrop），
    mode 5 只有左上 160x128，超出範圍一律透明。
    """

    frame_select = 1 if dispcnt & 0x10 else 0
    data = vram._data
    palette_data = palette._data
    backdrop = palette_data[0] | (palette_data[1] << 8)
    br, bg, bb = backdrop & 0x1F, (backdrop >> 5) & 0x1F, (backdrop >> 10) & 0x1F
    backdrop_rgb = bytes((((br << 3) | (br >> 2)), ((bg << 3) | (bg >> 2)), ((bb << 3) | (bb >> 2))))
    for y in range(y0, y1):
        for x in range(WIDTH):
            out = (y * WIDTH + x) * 3
            if mode == 4:
                index = data[frame_select * 0xA000 + y * WIDTH + x]
                if index == 0:
                    pixels[out:out + 3] = backdrop_rgb
                    continue
                value = palette_data[index * 2] | (palette_data[index * 2 + 1] << 8)
            elif mode == 5:
                if x >= 160 or y >= 128:
                    pixels[out:out + 3] = backdrop_rgb
                    continue
                base = frame_select * 0xA000 + (y * 160 + x) * 2
                value = data[base] | (data[base + 1] << 8)
            else:  # mode 3
                base = (y * WIDTH + x) * 2
                value = data[base] | (data[base + 1] << 8)
            r, g, b = value & 0x1F, (value >> 5) & 0x1F, (value >> 10) & 0x1F
            pixels[out] = (r << 3) | (r >> 2)
            pixels[out + 1] = (g << 3) | (g >> 2)
            pixels[out + 2] = (b << 3) | (b >> 2)


def _render_bitmap_composite(ppu, state: _RenderState, dispcnt, mode: int,
                             pixels: bytearray, y0: int = 0, y1: int = HEIGHT) -> None:
    """Mode 3/4/5：bitmap（BG2）加上 OBJ 與 alpha/fade/window 合成。

    GBATEK Video/OBJ "Priority"：OBJ 與 BG2 同 priority 時 OBJ 在上層；
    mode 4 的 index 0 透明，OBJ 可以出現在 bitmap 後面。
    """

    data = state.vram
    bg_palette = state.bg_palette
    obj_palette = state.obj_palette
    frame_select = 1 if dispcnt & 0x10 else 0
    bg_priority = ppu.read_reg16(0x00A) & 3  # BG2CNT: bitmap 的 BG2 控制
    targets = state.bld_targets
    alpha_enabled = state.alpha_enabled
    fade_lut = state.fade_lut if state.fade_enabled else None
    eva, evb = state.eva, state.evb
    windows_enabled = state.windows_enabled
    backdrop = bg_palette[0]
    sprite_color = state.sprite_color
    sprite_priority = state.sprite_priority
    bg_target = 1 << 2  # BLDCNT bit 2 = BG2
    obj_target = 0x10

    for y in range(y0, y1):
        row = y * WIDTH
        for x in range(WIDTH):
            index = row + x
            mask = _window_mask(state, x, y) if windows_enabled else 0x3F
            if mode == 4:
                color = data[frame_select * 0xA000 + index]
                bg_value = bg_palette[color] if color else None
            elif mode == 5:
                if x >= 160 or y >= 128:
                    bg_value = None
                else:
                    base = frame_select * 0xA000 + (y * 160 + x) * 2
                    bg_value = data[base] | (data[base + 1] << 8)
            else:  # mode 3
                base = index * 2
                bg_value = data[base] | (data[base + 1] << 8)
            if not (mask & bg_target):
                bg_value = None
            sprite_value = None
            if (mask & obj_target) and sprite_color[index]:
                if sprite_priority[index] <= bg_priority:
                    sprite_value = obj_palette[sprite_color[index]]
                elif bg_value is None:
                    # bitmap 該點透明（mode 4 index 0 / mode 5 範圍外），OBJ 仍可見。
                    sprite_value = obj_palette[sprite_color[index]]
            if sprite_value is not None:
                value = sprite_value
                top_target = obj_target
                bottom = bg_value
                bottom_target = bg_target
            elif bg_value is not None:
                value = bg_value
                top_target = bg_target
                bottom = None
                bottom_target = 0
            else:
                value = backdrop
                top_target = 0
                bottom = None
                bottom_target = 0

            if value != backdrop or top_target:
                if alpha_enabled and (targets & top_target):
                    if bottom is not None and (targets & bottom_target):
                        value = _mix(bottom, value, eva, evb)
                    elif targets & 0x20:
                        value = _mix(backdrop, value, eva, evb)
                elif fade_lut is not None and (targets & top_target):
                    value = fade_lut[value & 0x7FFF]

            r, g, b = value & 0x1F, (value >> 5) & 0x1F, (value >> 10) & 0x1F
            out = index * 3
            pixels[out] = (r << 3) | (r >> 2)
            pixels[out + 1] = (g << 3) | (g >> 2)
            pixels[out + 2] = (b << 3) | (b >> 2)



__all__ = ["render_frame", "rgb555_to_rgb888"]
