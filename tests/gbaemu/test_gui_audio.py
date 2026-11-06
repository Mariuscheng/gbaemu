"""GUI 音訊餵入：SDL_mixer 只吃 mixer buffer 整數倍的 chunk（回歸測試）。

背景：pygame/SDL_mixer 以 mixer buffer 為混音單位，若一次 play/queue 的
Sound 長度不是 buffer 的整數倍，邊界會漏音（實測 549 frames chunk +
1024 frames buffer 會讓 22% 樣本變成 0），聽起來就是雜音。這些測試用假
mixer 驗證餵入邏輯永遠送出 buffer 整數倍的 chunk，且不遺失資料。
"""

from __future__ import annotations

import types

from gbaemu.rl import GbaApp

from .cpu_helpers import arm_words, program_rom

NOP = 0xE1A00000
B_SELF = 0xEAFFFFFE
BUFFER_FRAMES = 512
BLOCK = BUFFER_FRAMES * 4  # s16le stereo


def _app(tmp_path) -> GbaApp:
    path = tmp_path / "audio.gba"
    path.write_bytes(program_rom(arm_words(NOP, NOP, B_SELF)))
    return GbaApp(str(path), window="null")


class _FakeSound:
    def __init__(self, buffer: bytes) -> None:
        self.buffer = buffer


class _FakeChannel:
    def __init__(self) -> None:
        self.busy = False
        self.queued: bytes | None = None
        self.sounds: list[bytes] = []

    def get_busy(self) -> bool:
        return self.busy

    def get_queue(self):
        return self.queued

    def play(self, sound) -> None:
        self.sounds.append(sound.buffer)
        self.busy = True
        self.queued = None

    def queue(self, sound) -> None:
        self.sounds.append(sound.buffer)
        self.queued = sound.buffer


class _StubAudio:
    def __init__(self) -> None:
        self.chunk = b""

    def read_buffer(self) -> bytes:
        return self.chunk


def _wire(app: GbaApp, channel: _FakeChannel) -> _StubAudio:
    audio = _StubAudio()
    app._audio_ok = True
    app._audio_rate = 32768
    app._audio_buffer_frames = BUFFER_FRAMES
    app._audio_block_bytes = BLOCK
    app._audio_pending = bytearray()
    app._audio_channel = channel
    app._pg = types.SimpleNamespace(mixer=types.SimpleNamespace(Sound=_FakeSound))
    app._orig_emu = app._emu
    app._emu = types.SimpleNamespace(audio=audio)
    return audio


def _restore(app: GbaApp) -> None:
    app._emu = app._orig_emu
    app._pg = None  # 測試用的假 pygame 沒有 quit()
    app.stop()


def test_feed_audio_sends_whole_mixer_buffers(tmp_path):
    app = _app(tmp_path)
    channel = _FakeChannel()
    audio = _wire(app, channel)
    chunks = [bytes([(i * 7) & 0xFF]) * (2192) for i in range(200)]
    stream = b"".join(chunks)

    for chunk in chunks:
        audio.chunk = chunk
        if channel.queued is not None:
            channel.queued = None  # 佇列中的聲音開始播放，queue 空出來
        app._feed_audio()

    assert channel.sounds, "應該有送出音訊"
    for sound in channel.sounds:
        assert len(sound) % BLOCK == 0
        assert BLOCK <= len(sound) <= 4 * BLOCK
    delivered = b"".join(channel.sounds)
    assert stream.startswith(delivered)
    # 送出的 + 還留在 pending 的必須剛好等於產生過的 PCM，不能漏也不能重複。
    assert delivered + bytes(app._audio_pending) == stream
    _restore(app)


def test_feed_audio_bounds_pending_when_mixer_is_blocked(tmp_path):
    app = _app(tmp_path)
    channel = _FakeChannel()
    channel.busy = True
    channel.queued = b"occupied"  # queue 一直被佔用，模擬 mixer 落後
    audio = _wire(app, channel)
    audio.chunk = bytes(BLOCK)

    for _ in range(100):
        app._feed_audio()

    assert not channel.sounds
    assert len(app._audio_pending) == 8 * BLOCK
    assert len(app._audio_pending) % BLOCK == 0
    _restore(app)
