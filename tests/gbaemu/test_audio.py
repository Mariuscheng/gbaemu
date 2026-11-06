"""Phase 4：音訊暫存器、FIFO A/B、FIFO DMA 與 PCM buffer。"""

from __future__ import annotations

import struct

from gbaemu import AudioMode, BootMode, Emulator, EmulatorConfig
from gbaemu.audio.sound import SoundController

from .cpu_helpers import arm_words, program_rom

B_SELF = 0xEAFFFFFE
SOUNDCNT_H = 0x04000082
FIFO_A = 0x040000A0
FIFO_B = 0x040000A4


def _emu(tmp_path, audio: AudioMode = AudioMode.BUFFERED) -> Emulator:
    path = tmp_path / "audio.gba"
    path.write_bytes(program_rom(arm_words(B_SELF)))
    return Emulator.from_rom(
        path,
        config=EmulatorConfig(boot_mode=BootMode.TEST_ROM_ONLY, audio=audio),
    )


def test_sound_register_readback(tmp_path):
    emu = _emu(tmp_path)
    emu.memory.write_u16(0x04000080, 0x117F)  # SOUNDCNT_L
    emu.memory.write_u16(SOUNDCNT_H, 0x0004)
    emu.memory.write_u16(0x04000084, 0x0080)  # SOUNDCNT_X
    emu.memory.write_u16(0x04000088, 0x4000)

    assert emu.memory.read_u16(0x04000080) == 0x117F
    assert emu.memory.read_u16(SOUNDCNT_H) == 0x0004
    assert emu.memory.read_u16(0x04000084) == 0x0080
    assert emu.memory.read_u16(0x04000088) == 0x4000


def test_fifo_pcm_buffer_in_buffered_mode(tmp_path):
    emu = _emu(tmp_path, AudioMode.BUFFERED)
    emu.memory.write_u16(SOUNDCNT_H, (1 << 2) | (1 << 11))  # 100% + FIFO A enable
    emu.memory.write_u32(FIFO_A, 0x80808080)  # 4 個 -128（靜音）

    assert emu.audio.read_buffer() == b""
    emu.step_cycles(512 * 4)
    pcm = emu.audio.read_buffer()
    assert pcm
    assert len(pcm) % 4 == 0  # s16le stereo
    assert emu.audio.read_buffer() == b""  # 讀取後清空
    assert emu.audio.sample_rate == 32768


def test_audio_disabled_produces_no_pcm(tmp_path):
    emu = _emu(tmp_path, AudioMode.DISABLED)
    emu.memory.write_u16(SOUNDCNT_H, (1 << 2) | (1 << 11))
    emu.memory.write_u32(FIFO_A, 0x01020304)
    emu.step_cycles(4096)
    assert emu.audio.read_buffer() == b""


def test_fifo_dma_special_timing(tmp_path):
    emu = _emu(tmp_path)
    bus = emu._bus
    for index in range(4):
        emu.memory.write_u32(0x02000000 + index * 4, 0x11110000 + index)

    # DMA1：SAD→FIFO A、32-bit、Special timing、repeat、enable
    bus.write_u32(0x040000BC, 0x02000000)
    bus.write_u32(0x040000C0, FIFO_A)
    bus.write_u16(0x040000C4, 4)
    bus.write_u16(0x040000C6, 0x8000 | (1 << 10) | (1 << 9) | (3 << 12))

    # FIFO A enable（bit11）＋ DMA A 100%（bit2）
    bus.write_u16(SOUNDCNT_H, (1 << 2) | (1 << 11))
    bus.write_u32(FIFO_A, 0x99999999)  # 觸發 request（FIFO ≤ 16 bytes）

    assert bus.dma.pending == [1]
    cycles = bus.dma.service()
    assert cycles > 0
    assert len(bus.sound.fifo_a) == 20  # 觸發寫入 4 bytes + DMA 16 bytes
    assert bus.dma.channels[1].source == 0x02000010
    assert bytes(bus.sound.fifo_a[4:8]) == (0x11110000).to_bytes(4, "little")


def test_fifo_dma_without_repeat_disables_channel(tmp_path):
    """GBATEK：repeat bit clear → 16 bytes refill 之後清 enable（one-shot SFX）。"""

    emu = _emu(tmp_path)
    bus = emu._bus
    bus.write_u32(0x02000000, 0x11223344)
    bus.write_u32(0x040000BC, 0x02000000)  # DMA1 SAD
    bus.write_u32(0x040000C0, FIFO_A)  # DMA1 DAD
    bus.write_u16(0x040000C4, 4)
    bus.write_u16(0x040000C6, 0x8000 | (1 << 10) | (3 << 12))  # 無 repeat
    bus.write_u16(SOUNDCNT_H, (1 << 2) | (1 << 11))
    bus.write_u32(FIFO_A, 0)  # FIFO 見底 → 排 DMA1

    assert bus.dma.pending == [1]
    bus.dma.service()
    assert len(bus.sound.fifo_a) == 20  # 4 + 16
    channel = bus.dma.channels[1]
    assert not channel.active
    assert channel.word_count == 0
    assert not (bus.dma._latched[1][3] & (1 << 15))
    bus.dma.pending.clear()
    bus.dma.request_fifo(1)  # enable 已清：唔會再排隊
    assert bus.dma.pending == []


def test_fifo_dma_repeat_keeps_channel_enabled(tmp_path):
    emu = _emu(tmp_path)
    bus = emu._bus
    bus.write_u32(0x02000000, 0x11223344)
    bus.write_u32(0x040000BC, 0x02000000)
    bus.write_u32(0x040000C0, FIFO_A)
    bus.write_u16(0x040000C4, 4)
    bus.write_u16(0x040000C6, 0x8000 | (1 << 10) | (1 << 9) | (3 << 12))
    bus.write_u16(SOUNDCNT_H, (1 << 2) | (1 << 11))
    bus.write_u32(FIFO_A, 0)
    bus.dma.service()
    channel = bus.dma.channels[1]
    assert channel.active  # repeat：channel 保持 enable
    assert bus.dma._latched[1][3] & (1 << 15)
    assert channel.source == 0x02000010


def test_emulator_services_fifo_dma(tmp_path):
    emu = _emu(tmp_path)
    bus = emu._bus
    emu.memory.write_u32(0x02000000, 0xCAFEBABE)
    bus.write_u32(0x040000BC, 0x02000000)
    bus.write_u32(0x040000C0, FIFO_A)
    bus.write_u16(0x040000C4, 4)
    bus.write_u16(0x040000C6, 0x8000 | (1 << 10) | (1 << 9) | (3 << 12))
    bus.write_u16(SOUNDCNT_H, (1 << 2) | (1 << 11))
    bus.write_u32(FIFO_A, 0)

    emu.step_cycles(10)  # step loop 會呼叫 _service_dma
    assert len(bus.sound.fifo_a) >= 16


def test_fifo_b_uses_dma2(tmp_path):
    emu = _emu(tmp_path)
    bus = emu._bus
    bus.write_u32(0x040000C8, 0x02000000)  # DMA2 SAD
    bus.write_u32(0x040000CC, FIFO_B)  # DMA2 DAD
    bus.write_u16(0x040000D0, 4)
    bus.write_u16(0x040000D2, 0x8000 | (1 << 10) | (1 << 9) | (3 << 12))
    bus.write_u16(SOUNDCNT_H, (1 << 3) | (1 << 15))  # FIFO B enable

    bus.write_u32(FIFO_B, 0)
    assert bus.dma.pending == [2]
    bus.dma.service()
    assert len(bus.sound.fifo_b) == 20


def _nonzero_samples(pcm: bytes) -> int:
    return sum(1 for index in range(0, len(pcm), 2) if pcm[index : index + 2] != b"\x00\x00")


def test_psg_square_produces_audio(tmp_path):
    """PSG channel 1（50% duty、volume 15）要產生非靜音 PCM。"""

    emu = _emu(tmp_path, AudioMode.BUFFERED)
    emu.memory.write_u16(0x04000062, 0xF080)  # duty 2、volume 15
    emu.memory.write_u16(0x04000064, 0x8700)  # freq 0x700 + trigger
    emu.memory.write_u16(0x04000080, 0x1177)  # master 7/8 + ch1 L/R
    emu.memory.write_u16(SOUNDCNT_H, 0x0002)  # PSG volume 100%
    emu.memory.write_u16(0x04000084, 0x0080)  # master enable

    emu.step_cycles(4096)
    pcm = emu.audio.read_buffer()
    assert pcm
    assert _nonzero_samples(pcm) > 0


def test_direct_sound_uses_timer_overflow(tmp_path):
    """DMA Sound A 每個 timer 0 溢位取一個 FIFO byte（不是每個輸出 sample）。"""

    emu = _emu(tmp_path, AudioMode.BUFFERED)
    bus = emu._bus
    bus.write_u16(SOUNDCNT_H, 0x0304)  # A L/R enable、100%、timer 0
    bus.write_u16(0x04000084, 0x0080)
    bus.write_u32(FIFO_A, 0x80808080)
    bus.write_u16(0x04000100, 0xFFFE)
    bus.write_u16(0x04000102, 0x0080)  # timer0 enable、prescaler 1

    emu.step_cycles(4096)
    assert len(bus.sound.fifo_a) < 4
    pcm = emu.audio.read_buffer()
    assert _nonzero_samples(pcm) > 0


def test_psg_square_pitch_matches_hardware_formula():
    """freq=0x700 → 512 Hz；0.1 秒約 51 個週期。"""

    sound = SoundController()
    sound.enabled = True
    sound.write16(0x04000062, 0xF080)  # volume 15、duty 50%
    sound.write16(0x04000064, 0x8000 | 0x700)  # freq 0x700 + trigger
    sound.write16(0x04000080, 0x1177)
    sound.write16(0x04000082, 0x0002)
    sound.write16(0x04000084, 0x0080)
    sound.tick(1_677_721)
    pcm = sound.take_pcm()
    left = struct.unpack("<%dh" % (len(pcm) // 2), pcm)[0::2]
    rises = sum(1 for a, b in zip(left, left[1:]) if a <= 0 < b)
    assert 49 <= rises <= 53, rises
