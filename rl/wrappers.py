"""PyBoy 風格 facade（``main.py`` 使用）：``GbaApp``／``Screen``。"""

from __future__ import annotations

import logging
import os
import sys
import time
from dataclasses import replace
from pathlib import Path

from ..api_types import (
    AudioMode,
    BootMode,
    Button,
    EmulatorConfig,
    TimingMode,
    VideoMode,
)
from ..emulator import Emulator
from ..errors import GbaEmuError

logger = logging.getLogger("gbaemu.rl")


class Screen:
    """PyBoy 風格畫面 view：``ndarray`` 係 RGBA，``raw`` 係 RGB888 bytes。"""

    def __init__(self, emulator: Emulator) -> None:
        self._emu = emulator

    @property
    def ndarray(self):
        """回傳 ``(160, 240, 4)`` 的 ``uint8`` RGBA array（同 PyBoy 一致）。"""

        import numpy as np

        rgb = self._emu.video.read_frame_array()  # (160, 240, 3)
        rgba = np.empty((rgb.shape[0], rgb.shape[1], 4), dtype=np.uint8)
        rgba[..., :3] = rgb
        rgba[..., 3] = 0xFF
        return rgba

    @property
    def rgb(self):
        """回傳 ``(160, 240, 3)`` 的 RGB array（需要 numpy）。"""

        return self._emu.video.read_frame_array()

    @property
    def raw(self) -> bytes:
        """回傳 RGB888 bytes（240*160*3，scanline 0 在前）。"""

        return self._emu.video.read_frame()

    @property
    def shape(self) -> tuple[int, int, int]:
        return (160, 240, 4)


class GbaApp:
    """PyBoy 風格應用入口：``GbaApp(rom)`` → ``while app.tick(): ...`` → ``stop()``。"""

    def __init__(
        self,
        path: str | Path | None = None,
        window: str = "null",
        bios: str | None = None,
        verify_logo: bool = True,
        scale: int = 4,
        sound=None,
        throttle: bool = True,
        **kwargs,
    ) -> None:
        del verify_logo, kwargs
        audio = (
            AudioMode.BUFFERED
            if sound not in (None, False, 0, "0", "none")
            else AudioMode.DISABLED
        )
        config = EmulatorConfig(
            boot_mode=BootMode.HLE_ADVANCED,
            video=VideoMode.FRAMEBUFFER,
            audio=audio,
            timing=TimingMode.FUNCTIONAL,
            hle_strict=False,
        )
        if bios and Path(bios).exists():
            config = replace(config, bios_path=Path(bios))
        if path is None:
            from ..cli import find_roms

            candidates = find_roms("rom")
            if len(candidates) != 1:
                raise GbaEmuError("請指定 ROM 路徑（rom/ 入面要有唯一 .gba）")
            path = candidates[0]
        self._emu = self._make_backend(path, config)
        self._audio_enabled = audio is AudioMode.BUFFERED
        self._audio_ok = False
        self._audio_channel = None
        self._audio_rate = 32768
        self._audio_buffer_frames = 512
        self._audio_block_bytes = 512 * 4
        self._audio_pending = bytearray()
        # 實機速度：GBA frame = 59.7275 Hz（280,896 cycles @ 16.78 MHz）。
        self._throttle = throttle
        self._frame_period = 1.0 / 59.7275
        self._next_frame_time = time.perf_counter()

        self.emu = self._emu
        self.screen = Screen(self._emu)
        self.title = self._emu.rom_header.title
        self.game_code = self._emu.rom_header.game_code
        self.maker = self._emu.rom_header.maker_code
        self.software_version = self._emu.rom_header.software_version
        self.entry_point = self._emu.rom_header.entry_point
        self.logo = self._emu.rom_header.logo
        self.frames = 0
        self._stopped = False
        self._closed = False
        self._pressed: set[Button] = set()
        self._pg = None
        self._scale = scale
        self._window = self._init_window(window, scale)
        logger.info("GbaApp started: %s (%s)", self.title or "(no title)", path)

    # -- 低層 view 的 forwarding（PyBoy 風格單一入口） ------------------
    @property
    def frame_count(self) -> int:
        """已 tick 嘅 frame 數（PyBoy 嘅 ``frame_count`` 等價）。"""

        return self.frames

    @property
    def video(self):
        """``app.emu.video`` 的 shortcut。"""

        return self._emu.video

    @property
    def memory(self):
        """``app.emu.memory`` 的 shortcut。"""

        return self._emu.memory

    @property
    def cpu(self):
        """``app.emu.cpu`` 的 shortcut。"""

        return self._emu.cpu

    @property
    def input(self):
        """``app.emu.input`` 的 shortcut。"""

        return self._emu.input

    @property
    def audio(self):
        """``app.emu.audio`` 的 shortcut。"""

        return self._emu.audio

    @property
    def events(self):
        """``app.emu.events`` 的 shortcut（Rust backend 唔支援）。"""

        events = getattr(self._emu, "events", None)
        if events is None:
            raise AttributeError("NativeEmulator 不提供 events；請用 Python backend")
        return events

    # -- backend 選擇 ----------------------------------------------------
    def _make_backend(self, path, config):
        """GUI 預設用 Rust core；沒有 extension 或指定 python 才退回 reference。"""

        backend = os.environ.get("GBAEMU_BACKEND", "auto").lower()
        if backend in ("auto", "rust"):
            try:
                from ..native import NativeEmulator

                return NativeEmulator.from_rom(path, config)
            except ImportError:
                if backend == "rust":
                    raise
                logger.info("gbaemu._native 未 build；GUI 改用 Python backend")
            except Exception as exc:  # native 初始化失敗時仍可回到 reference
                if backend == "rust":
                    raise
                logger.warning("NativeEmulator 初始化失敗（%s）；GUI 改用 Python backend", exc)

        try:
            return Emulator.from_rom(path, config=config)
        except GbaEmuError as exc:
            logger.warning("HLE 開機失敗（%s），改用 bare reset", exc)
            config = replace(config, boot_mode=BootMode.TEST_ROM_ONLY)
            return Emulator.from_rom(path, config=config)

    # -- 視窗（可選） ----------------------------------------------------
    def _init_window(self, window: str, scale: int):
        if window.lower() not in ("sdl3", "pygame", "sdl2", "sdl"):
            return None
        try:
            import pygame

            pygame.init()
            if self._audio_enabled:
                # pygame.init() 會先用預設值開 mixer；先關掉再指定 GBA 取樣率。
                try:
                    pygame.mixer.quit()
                except Exception:  # pragma: no cover
                    pass
            pygame.display.set_caption(f"gbaemu - {self.title}" if self.title else "gbaemu")
            surface = pygame.display.set_mode((240 * scale, 160 * scale))
            self._pg = pygame
            self._init_audio()
            self._keymap = {
                pygame.K_UP: Button.UP,
                pygame.K_DOWN: Button.DOWN,
                pygame.K_LEFT: Button.LEFT,
                pygame.K_RIGHT: Button.RIGHT,
                pygame.K_z: Button.A,
                pygame.K_x: Button.B,
                pygame.K_RETURN: Button.START,
                pygame.K_BACKSPACE: Button.SELECT,
                pygame.K_a: Button.L,
                pygame.K_s: Button.R,
            }
            return surface
        except Exception as exc:  # pragma: no cover - 取決於 host
            if os.environ.get("GBAEMU_ALLOW_HEADLESS") == "1":
                logger.warning("無法開啟視窗（%s），GBAEMU_ALLOW_HEADLESS=1 → headless", exc)
                self._pg = None
                return None
            raise GbaEmuError(
                f"無法開啟視窗：{exc}\n"
                "請在執行 gbaemu 的 Python 環境安裝 pygame-ce：\n"
                f"  {sys.executable} -m pip install pygame-ce\n"
                "或使用 window=\"null\" 以 headless 模式執行。"
            ) from exc

    def _init_audio(self) -> None:
        """開啟 pygame mixer：優先 32.768 kHz／s16le／stereo（跟 GBA 一致）。

        SDL_mixer 以 mixer buffer 為混音單位：一次 play／queue 的 Sound 若不
        是 buffer 的整數倍，邊界就會漏音（實測 549 frames chunk + 1024
        frames buffer 會讓 22% 樣本變成 0，聽起來就是雜音）。因此固定以
        buffer（512 frames ≈ 15.6 ms）為單位切塊，一次可送多個 buffer，
        讓 pygame 單一 queue 也能吸收 60 fps 餵資料的時間抖動。
        """

        if not self._audio_enabled or self._pg is None:
            return
        try:
            self._audio_buffer_frames = 512
            self._pg.mixer.init(
                frequency=32768, size=-16, channels=2, buffer=self._audio_buffer_frames
            )
            init = self._pg.mixer.get_init()
            self._audio_rate = init[0] if init else 32768
            self._audio_channel = self._pg.mixer.Channel(0)
            src_frames = round(self._audio_buffer_frames * 32768 / self._audio_rate)
            self._audio_block_bytes = max(4, src_frames * 4)
            self._audio_pending = bytearray()
            self._audio_ok = True
            logger.info(
                "audio: mixer %s（buffer=%d frames）", init, self._audio_buffer_frames
            )
        except Exception as exc:  # pragma: no cover - 音效裝置缺失時靜音
            logger.warning("無法開啟音效（%s）；繼續靜音", exc)
            self._audio_ok = False

    def _resample_chunk(self, pcm: bytes, frames: int) -> bytes:
        """把 32.768 kHz 的 s16le stereo 一段轉成 mixer 取樣率、固定 frames 長度。"""

        if self._audio_rate == 32768:
            return pcm
        try:
            import numpy as np
        except ImportError:  # pragma: no cover - numpy 是 RL 依賴
            return pcm
        data = np.frombuffer(pcm, dtype="<i2").reshape(-1, 2).astype(np.float32)
        if len(data) < 2:
            return b"\x00" * (frames * 4)
        src = np.arange(len(data), dtype=np.float32)
        dst = np.linspace(0, len(data) - 1, frames).astype(np.float32)
        out = np.empty((frames, 2), dtype=np.int16)
        out[:, 0] = np.interp(dst, src, data[:, 0]).astype(np.int16)
        out[:, 1] = np.interp(dst, src, data[:, 1]).astype(np.int16)
        return out.tobytes()

    def _feed_audio(self) -> None:
        """把 emulator 的 PCM 以 mixer buffer 整數倍為單位餵給 mixer。"""

        if not self._audio_ok or self._pg is None:
            return
        try:
            pcm = self._emu.audio.read_buffer()
        except Exception:  # pragma: no cover - backend 無 audio view
            return
        if pcm:
            self._audio_pending += pcm
        block = self._audio_block_bytes
        # 最多留 8 個 buffer；落後時丟最舊的，避免延遲一直累積。
        if len(self._audio_pending) > block * 8:
            drop = len(self._audio_pending) - block * 8
            drop -= drop % block
            del self._audio_pending[:drop]
        channel = self._audio_channel
        if channel is None or len(self._audio_pending) < block:
            return
        try:
            if channel.get_busy() and channel.get_queue() is not None:
                return  # queue 已滿，下一幀再送
            chunks = min(len(self._audio_pending) // block, 4)
            nbytes = chunks * block
            chunk = bytes(self._audio_pending[:nbytes])
            del self._audio_pending[:nbytes]
            sound = self._pg.mixer.Sound(
                buffer=self._resample_chunk(chunk, chunks * self._audio_buffer_frames)
            )
            if channel.get_busy():
                channel.queue(sound)
            else:
                channel.play(sound)
        except Exception as exc:  # pragma: no cover - 播放失敗就關掉音效
            logger.warning("音效播放失敗（%s）；停用音效", exc)
            self._audio_ok = False

    def _pump_window(self) -> bool:
        """處理 pygame 事件與 QUIT；回傳 False 代表視窗已關閉。"""
        if self._pg is None:
            return True
        for event in self._pg.event.get():
            if event.type == self._pg.QUIT:
                self._stopped = True
                return False
            if event.type == self._pg.KEYDOWN and event.key in self._keymap:
                self.button(self._keymap[event.key].value, True)
            elif event.type == self._pg.KEYUP and event.key in self._keymap:
                self.button(self._keymap[event.key].value, False)
        return True

    def _draw_window(self) -> None:
        if self._pg is None or self._window is None:
            return
        frame = self._emu.video.read_frame_array()
        surface = self._pg.image.frombuffer(frame.tobytes(), (240, 160), "RGB")
        scaled = self._pg.transform.scale(surface, self._window.get_size())
        self._window.blit(scaled, (0, 0))
        self._pg.display.flip()

    # -- 生命週期 --------------------------------------------------------
    def tick(self, count: int = 1, render: bool = True, sound: bool = True) -> bool:
        if self._stopped:
            return False
        if not self._pump_window():
            return False
        frames = max(1, int(count))
        for _ in range(frames):
            self._emu.step_frame(render=render)
            self.frames += 1
        if render:
            self._draw_window()
        if sound:
            self._feed_audio()
        if self._throttle:
            self._next_frame_time += self._frame_period * frames
            now = time.perf_counter()
            if self._next_frame_time > now:
                time.sleep(self._next_frame_time - now)
            else:
                # 落後超過一個 frame：重新對齊，避免之後一直追不上。
                self._next_frame_time = now
        if self.frames % 30 == 0:
            logger.info(
                "frame=%d cpu_cycles=%d pc=0x%08X",
                self.frames,
                self._emu.cycles,
                self._emu.cpu.read_register("r15"),
            )
        return True

    def stop(self, save: bool = True) -> None:
        if self._closed:
            return
        self._stopped = True
        self._closed = True
        # 只有在遊戲真正寫過備份記憶體（存檔）時才寫 .sav；純粹開遊戲、
        # 冇喺遊戲入面手動存檔，唔會改動／建立電池存檔。
        if save and getattr(self._emu, "battery_dirty", True):
            try:
                self._emu.cartridge_flush_to_disk()
            except (GbaEmuError, NotImplementedError):
                pass  # 冇 save 媒體（或舊 backend 未支援）係正常情況
            except OSError as exc:
                logger.warning("備份記憶體寫回失敗（%s）", exc)
        self._emu.close()
        if self._pg is not None:
            try:
                self._pg.mixer.quit()
            except Exception:  # pragma: no cover
                pass
            self._audio_ok = False
            self._pg.quit()
            self._pg = None

    def save_battery(self) -> None:
        """明確寫回電池存檔 ``<rom stem>.sav``（唔理 dirty 狀態）。"""

        self._emu.cartridge_flush_to_disk()

    # -- 輸入 ------------------------------------------------------------
    def button(self, name: str, press: bool = True) -> None:
        button = Button(name.lower())
        if press:
            self._pressed.add(button)
        else:
            self._pressed.discard(button)
        self._emu.input.clear()
        if self._pressed:
            self._emu.input.set_buttons(**{item.value: True for item in self._pressed})

    def button_press(self, name: str) -> None:
        self.button(name, True)

    def button_release(self, name: str) -> None:
        self.button(name, False)

    # -- 存檔 ------------------------------------------------------------
    def save_state(self, path: str | Path) -> None:
        Path(path).write_bytes(self._emu.save_state())

    def load_state(self, path: str | Path) -> None:
        self._emu.load_state(Path(path).read_bytes())


__all__ = ["GbaApp", "Screen"]
