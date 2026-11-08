"""GBA 音訊（Phase 4／6）：PSG 四聲道、DMA Sound A/B、混音輸出。

時基跟 Rust `crates/gbaemu-core/src/sound.rs` 一致：

* 輸出 32.768 kHz：每個 sample 512 CPU cycles。
* PSG 內部 262.144 kHz：每個 sample 8 個 PSG tick。
* Frame sequencer 512 Hz（每 512 tick 一步）：length 256 Hz、sweep 128 Hz、
  envelope 64 Hz。
* 混音單位跟 GBATEK「Max Output Levels」：每個 PSG 聲道 ±0x80、每個 FIFO
  ±0x200，相加後 ×20 轉 s16 並 clamp。

DMA Sound 的取樣由 timer 0/1 溢位推動（SOUNDCNT_H bit10/14 選擇），所以
`Timers` 要 `bind_sound(sound.timer_overflow)`。

# GBATEK: GBA Sound Controller - SOUND1-4、SOUNDCNT_L/H/X、WAVE_RAM
"""

from __future__ import annotations

import struct

SOUND_BASE = 0x04000060
SOUND_SIZE = 0x50  # 0x060..0x0AF

FIFO_A_OFFSET = 0x40  # 0x0A0 - 0x060
FIFO_B_OFFSET = 0x44  # 0x0A4 - 0x060

CYCLE_HZ = 16 * 1024 * 1024
DEFAULT_SAMPLE_RATE = 32768

# 每個 sample 512 cycles（32.768 kHz）、每個 sample 8 個 PSG tick（262.144 kHz）。
CYCLES_PER_SAMPLE = 512
PSG_TICKS_PER_SAMPLE = 8
SEQ_TICKS = 512  # 262144 / 512 Hz

_DUTY = (
    (True, False, False, False, False, False, False, False),
    (True, True, False, False, False, False, False, False),
    (True, True, True, True, False, False, False, False),
    (True, True, True, True, True, True, False, False),
)


class _Square:
    __slots__ = ("enabled", "timer", "pos", "volume", "env_timer", "length")

    def __init__(self) -> None:
        self.enabled = False
        self.timer = 0
        self.pos = 0
        self.volume = 0
        self.env_timer = 0
        self.length = 0


class _Wave:
    __slots__ = ("enabled", "timer", "pos", "length", "sample")

    def __init__(self) -> None:
        self.enabled = False
        self.timer = 0
        self.pos = 0
        self.length = 0
        self.sample = 0


class _Noise:
    __slots__ = ("enabled", "timer", "lfsr", "volume", "env_timer", "length", "out")

    def __init__(self) -> None:
        self.enabled = False
        self.timer = 0
        self.lfsr = 0x4000
        self.volume = 0
        self.env_timer = 0
        self.length = 0
        self.out = False


class SoundController:
    """SOUND 暫存器＋PSG 四聲道＋FIFO＋PCM buffer。"""

    def __init__(self, *, sample_rate: int = DEFAULT_SAMPLE_RATE) -> None:
        self._regs = bytearray(SOUND_SIZE)
        self.fifo_a = bytearray()
        self.fifo_b = bytearray()
        self.sample_rate = sample_rate
        self._cycle_accumulator = 0
        self._pcm = bytearray()
        self.enabled = False  # AudioMode.BUFFERED 時由 Emulator 開啟
        self.fifo_dma_request = None  # callback(channel)
        self._suppress_dma = False
        self.ch1 = _Square()
        self.ch2 = _Square()
        self.ch3 = _Wave()
        self.ch4 = _Noise()
        self._seq_tick = 0
        self._seq_step = 0
        self._ds_a = 0
        self._ds_b = 0

    # ------------------------------------------------------------------
    # 暫存器存取（IoRegisters 委派；offset 相對 0x04000000）
    # ------------------------------------------------------------------
    @staticmethod
    def _relative(offset: int) -> int:
        return offset - SOUND_BASE if offset >= SOUND_BASE else offset - 0x60

    def read8(self, offset: int) -> int:
        return (self.read16(offset & ~1) >> ((offset & 1) * 8)) & 0xFF

    def read16(self, offset: int) -> int:
        relative = self._relative(offset)
        if not 0 <= relative < SOUND_SIZE - 1:
            return 0
        return self._get16(relative)

    def read32(self, offset: int) -> int:
        return self.read16(offset) | (self.read16(offset + 2) << 16)

    def write8(self, offset: int, value: int) -> None:
        relative = self._relative(offset)
        if not 0 <= relative < SOUND_SIZE:
            return
        if relative in (FIFO_A_OFFSET, FIFO_B_OFFSET):
            self._push_fifo(relative, bytes([value & 0xFF]))
            return
        aligned = relative & ~1
        shift = (relative & 1) * 8
        current = self._get16(aligned)
        self.write16(SOUND_BASE + aligned, (current & ~(0xFF << shift)) | ((value & 0xFF) << shift))

    def write16(self, offset: int, value: int) -> None:
        relative = self._relative(offset)
        if not 0 <= relative < SOUND_SIZE - 1:
            return
        raw = value & 0xFFFF
        if relative == FIFO_A_OFFSET:
            self._push_fifo(0, raw.to_bytes(2, "little"))
            return
        if relative == FIFO_B_OFFSET:
            self._push_fifo(1, raw.to_bytes(2, "little"))
            return
        self._set16(relative, raw)
        if relative == 0x22:  # SOUNDCNT_H
            if raw & (1 << 10):
                self.fifo_a.clear()
            if raw & (1 << 14):
                self.fifo_b.clear()
            self._check_fifo_dma()
            return
        self._write_psg(relative, raw)

    def write32(self, offset: int, value: int) -> None:
        relative = self._relative(offset)
        if relative in (FIFO_A_OFFSET, FIFO_B_OFFSET):
            channel = 0 if relative == FIFO_A_OFFSET else 1
            self._push_fifo(channel, (value & 0xFFFFFFFF).to_bytes(4, "little"))
            return
        self.write16(offset, value & 0xFFFF)
        self.write16(offset + 2, (value >> 16) & 0xFFFF)

    # ------------------------------------------------------------------
    # PSG 狀態更新
    # ------------------------------------------------------------------
    def _write_psg(self, relative: int, value: int) -> None:
        if relative == 0x24:  # SOUNDCNT_X
            if not value & 0x80:
                self._reset_channels()
            return
        triggered = bool(value & 0x8000)
        if not triggered:
            return
        if relative == 0x04:  # SOUND1CNT_X
            cnt_h = self._get16(0x02)
            self.ch1.enabled = (cnt_h >> 12) != 0
            self.ch1.volume = (cnt_h >> 12) & 0xF
            self.ch1.env_timer = 0
            self.ch1.pos = 0
            self.ch1.length = 64 - (cnt_h & 0x3F)
            self.ch1.timer = 0
        elif relative == 0x0C:  # SOUND2CNT_H
            cnt_l = self._get16(0x08)
            self.ch2.enabled = (cnt_l >> 12) != 0
            self.ch2.volume = (cnt_l >> 12) & 0xF
            self.ch2.env_timer = 0
            self.ch2.pos = 0
            self.ch2.length = 64 - (cnt_l & 0x3F)
            self.ch2.timer = 0
        elif relative == 0x14:  # SOUND3CNT_X
            cnt_l = self._get16(0x10)
            cnt_h = self._get16(0x12)
            self.ch3.enabled = bool(cnt_l & 0x80)
            self.ch3.pos = 0
            self.ch3.timer = 0
            self.ch3.length = 256 - (cnt_h & 0xFF)
            self.ch3.sample = 0
        elif relative == 0x1C:  # SOUND4CNT_H
            cnt_l = self._get16(0x18)
            self.ch4.enabled = (cnt_l >> 12) != 0
            self.ch4.volume = (cnt_l >> 12) & 0xF
            self.ch4.env_timer = 0
            self.ch4.length = 64 - (cnt_l & 0x3F)
            self.ch4.lfsr = 0x40 if value & 0x08 else 0x4000
            self.ch4.timer = 0
            self.ch4.out = False

    def _reset_channels(self) -> None:
        self.ch1 = _Square()
        self.ch2 = _Square()
        self.ch3 = _Wave()
        self.ch4 = _Noise()
        self._seq_tick = 0
        self._seq_step = 0
        self._ds_a = 0
        self._ds_b = 0

    @staticmethod
    def _square_period(cnt_x: int) -> int:
        # 一個 duty step = (2048-n)/4 個 PSG tick；用 1/4 tick 累加器避免浮點。
        return max(1, 2048 - (cnt_x & 0x7FF))

    @staticmethod
    def _wave_period(cnt_x: int) -> int:
        # 每個 wave digit = (2048-n)/8 個 PSG tick；累加器每次 +8。
        return max(1, 2048 - (cnt_x & 0x7FF))

    @staticmethod
    def _noise_threshold(cnt_h: int) -> int:
        # 半 tick 累加器：r>0 時 period = r*2^s tick；r=0 時 2^(s-1) tick。
        r = cnt_h & 0x7
        s = (cnt_h >> 4) & 0xF
        threshold = (r << (s + 1)) if r else (1 << s)
        return max(1, threshold)

    def master_enabled(self) -> bool:
        return bool(self._get16(0x24) & 0x80)

    # ------------------------------------------------------------------
    # FIFO
    # ------------------------------------------------------------------
    def _push_fifo(self, channel: int, data: bytes) -> None:
        fifo = self.fifo_a if channel == 0 else self.fifo_b
        fifo.extend(data)
        if len(fifo) > 32:
            del fifo[: len(fifo) - 32]
        self._check_fifo_dma()

    def _fifo_enabled(self, channel: int) -> bool:
        """FIFO 是否需要 refill。

        bit11/15 是 reset 位（舊模型用它當 enable）；實際遊戲用 SOUNDCNT_H
        bit8/9（A 右／左）、bit12/13（B 右／左）開啟播放，兩者都接受。
        """

        control = self._get16(0x22)
        if channel == 0:
            enabled = bool(control & (1 << 11)) or bool(control & 0x0300)
        else:
            enabled = bool(control & (1 << 15)) or bool(control & 0x3000)
        return enabled and self.fifo_dma_request is not None

    def begin_refill(self) -> None:
        """DMA 正在 refill FIFO：暫停新的 request（避免 service loop 重複搬）。"""

        self._suppress_dma = True

    def end_refill(self) -> None:
        self._suppress_dma = False
        self._check_fifo_dma()

    def _check_fifo_dma(self) -> None:
        if self._suppress_dma:
            return
        for channel in (0, 1):
            if not self._fifo_enabled(channel):
                continue
            fifo = self.fifo_a if channel == 0 else self.fifo_b
            if len(fifo) <= 16:
                self.fifo_dma_request(channel + 1)  # FIFO A → DMA1、B → DMA2

    # ------------------------------------------------------------------
    # 取樣 / 混音
    # ------------------------------------------------------------------
    def timer_overflow(self, index: int) -> None:
        """Timer 0/1 溢位 → DMA Sound A/B 取樣（SOUNDCNT_H bit10/14 選擇）。"""

        if not self.master_enabled():
            return
        control = self._get16(0x22)
        use_a = False
        use_b = False
        if index == 0:
            use_a = control & 0x0400 == 0
            use_b = control & 0x4000 == 0
        elif index == 1:
            use_a = control & 0x0400 != 0
            use_b = control & 0x4000 != 0
        else:
            return
        if use_a and self.fifo_a:
            value = self.fifo_a[0]
            del self.fifo_a[0]
            self._ds_a = value - 0x100 if value & 0x80 else value
        if use_b and self.fifo_b:
            value = self.fifo_b[0]
            del self.fifo_b[0]
            self._ds_b = value - 0x100 if value & 0x80 else value

    def tick(self, cycles: int) -> None:
        if not self.enabled or cycles <= 0:
            return
        self._cycle_accumulator += cycles
        samples = self._cycle_accumulator // CYCLES_PER_SAMPLE
        if samples <= 0:
            return
        self._cycle_accumulator -= samples * CYCLES_PER_SAMPLE
        if samples > 32768:  # 一次最多補 1 秒，避免異常 chunk 拖慢核心
            samples = 32768
        for _ in range(samples):
            for _ in range(PSG_TICKS_PER_SAMPLE):
                self._step_psg()
            left, right = self._mix()
            self._pcm += struct.pack("<hh", left, right)
        if len(self._pcm) > 32768:
            del self._pcm[: len(self._pcm) - 32768]
        self._check_fifo_dma()

    def _step_psg(self) -> None:
        if not self.master_enabled():
            return
        self._seq_tick += 1
        if self._seq_tick >= SEQ_TICKS:
            self._seq_tick = 0
            step = self._seq_step
            self._seq_step = (self._seq_step + 1) & 7
            self._frame_sequencer(step)

        cnt1_h = self._get16(0x02)
        cnt1_x = self._get16(0x04)
        self._step_square(self.ch1, cnt1_h, cnt1_x)
        cnt2_l = self._get16(0x08)
        cnt2_x = self._get16(0x0C)
        self._step_square(self.ch2, cnt2_l, cnt2_x)

        if self.ch3.enabled:
            period = self._wave_period(self._get16(0x14))
            self.ch3.timer += 8
            while self.ch3.timer >= period:
                self.ch3.timer -= period
                self.ch3.pos = (self.ch3.pos + 1) & 63
                byte = self._regs[0x30 + self.ch3.pos // 2]
                self.ch3.sample = (byte >> 4) if self.ch3.pos & 1 == 0 else (byte & 0x0F)

        if self.ch4.enabled:
            cnt_h = self._get16(0x1C)
            self.ch4.timer += 2
            threshold = self._noise_threshold(cnt_h)
            while self.ch4.timer >= threshold:
                self.ch4.timer -= threshold
                short = bool(cnt_h & 0x08)
                bit = self.ch4.lfsr & 1
                self.ch4.lfsr >>= 1
                if bit:
                    self.ch4.lfsr ^= 0x60 if short else 0x6000
                    self.ch4.out = True
                else:
                    self.ch4.out = False

    def _step_square(self, channel: _Square, cnt_h: int, cnt_x: int) -> None:
        if not channel.enabled:
            return
        if (cnt_h >> 12) == 0 and channel.volume == 0:
            channel.enabled = False
            return
        channel.timer += 4
        period = self._square_period(cnt_x)
        while channel.timer >= period:
            channel.timer -= period
            channel.pos = (channel.pos + 1) & 7

    def _frame_sequencer(self, step: int) -> None:
        if step & 1 == 0:
            cnt1_h = self._get16(0x02)
            cnt2_l = self._get16(0x08)
            cnt3_x = self._get16(0x14)
            cnt4_l = self._get16(0x18)
            for channel, enable in (
                (self.ch1, bool(cnt1_h & 0x4000)),
                (self.ch2, bool(cnt2_l & 0x4000)),
                (self.ch3, bool(cnt3_x & 0x4000)),
                (self.ch4, bool(cnt4_l & 0x4000)),
            ):
                if channel.enabled and enable:
                    channel.length -= 1
                    if channel.length <= 0:
                        channel.enabled = False
        if step in (2, 6):
            cnt1_l = self._get16(0x00)
            time = (cnt1_l >> 4) & 7
            shift = cnt1_l & 7
            if time != 0 and shift != 0 and self.ch1.enabled:
                freq = self._get16(0x04) & 0x7FF
                delta = freq >> shift
                nxt = freq - delta if cnt1_l & 0x08 else freq + delta
                if nxt > 2047 or nxt < 0:
                    self.ch1.enabled = False
        if step == 7:
            self._clock_envelope(self.ch1, self._get16(0x02))
            self._clock_envelope(self.ch2, self._get16(0x08))
            self._clock_envelope(self.ch4, self._get16(0x18))

    @staticmethod
    def _clock_envelope(channel, cnt_h: int) -> None:
        period = (cnt_h >> 8) & 0x7
        if not channel.enabled or period == 0:
            return
        channel.env_timer += 1
        if channel.env_timer < period:
            return
        channel.env_timer = 0
        if cnt_h & 0x0800:
            channel.volume = min(15, channel.volume + 1)
        else:
            channel.volume = max(0, channel.volume - 1)

    def _channel_outputs(self) -> list[int]:
        cnt1_h = self._get16(0x02)
        cnt2_l = self._get16(0x08)
        cnt3_h = self._get16(0x12)
        cnt4_l = self._get16(0x18)
        out = [0, 0, 0, 0]
        if self.ch1.enabled and (cnt1_h >> 12):
            out[0] = self._psg_level(self.ch1.volume, _DUTY[(cnt1_h >> 6) & 3][self.ch1.pos])
        if self.ch2.enabled and (cnt2_l >> 12):
            out[1] = self._psg_level(self.ch2.volume, _DUTY[(cnt2_l >> 6) & 3][self.ch2.pos])
        if self.ch3.enabled:
            code = (cnt3_h >> 13) & 3
            # 1.0 → ×16、0.5 → ×8、0.25 → ×4、force 75% → ×12。
            scale = 12 if cnt3_h & 0x8000 else (0, 16, 8, 4)[code]
            out[2] = (self.ch3.sample - 8) * scale
        if self.ch4.enabled and (cnt4_l >> 12):
            out[3] = self._psg_level(self.ch4.volume, self.ch4.out)
        return out

    @staticmethod
    def _trunc_div(value: int, divisor: int) -> int:
        """向零截斷的整數除法（同 Rust `/`；Python `//` 會向下取整）。"""

        if value < 0:
            return -((-value) // divisor)
        return value // divisor

    @classmethod
    def _psg_level(cls, volume: int, high: bool) -> int:
        dac = volume if high else 0
        return cls._trunc_div((dac * 2 - 15) * 0x80, 15)

    def _mix(self) -> tuple[int, int]:
        soundcnt_l = self._get16(0x20)
        soundcnt_h = self._get16(0x22)
        volume_num, volume_den = {0: (1, 4), 1: (1, 2)}.get(soundcnt_h & 3, (1, 1))
        master_right = (((soundcnt_l >> 0) & 7) + 1)
        master_left = (((soundcnt_l >> 4) & 7) + 1)
        enable_right = (soundcnt_l >> 8) & 0xF
        enable_left = (soundcnt_l >> 12) & 0xF
        master = self.master_enabled()

        psg_right = 0
        psg_left = 0
        if master:
            for index, value in enumerate(self._channel_outputs()):
                bit = 1 << index
                if enable_right & bit:
                    psg_right += value
                if enable_left & bit:
                    psg_left += value
        scale = 8 * volume_den
        psg_right = self._trunc_div(psg_right * master_right * volume_num, scale)
        psg_left = self._trunc_div(psg_left * master_left * volume_num, scale)

        ds_right = 0
        ds_left = 0
        if master:
            vol_a = 4 if soundcnt_h & 0x4 else 2
            vol_b = 4 if soundcnt_h & 0x8 else 2
            a = self._ds_a * vol_a
            b = self._ds_b * vol_b
            if soundcnt_h & 0x0100:
                ds_right += a
            if soundcnt_h & 0x0200:
                ds_left += a
            if soundcnt_h & 0x1000:
                ds_right += b
            if soundcnt_h & 0x2000:
                ds_left += b

        left = self._clamp((psg_left + ds_left) * 20)
        right = self._clamp((psg_right + ds_right) * 20)
        # SOUNDBIAS（0x04000088）bit14-15 選 PWM 解析度；BIAS level 經
        # AC coupling 後唔會變 DC offset，所以只模擬量化 step。
        bias = self._get16(0x28)
        resolution = {0: 9, 1: 8, 2: 7}.get(bias >> 14, 6)
        if resolution == 9:
            return left, right
        step = 40 << (9 - resolution)
        return self._pwm_quantize(left, step), self._pwm_quantize(right, step)

    @staticmethod
    def _pwm_quantize(sample: int, step: int) -> int:
        quotient = sample // step if sample >= 0 else -((-sample) // step)
        return max(-0x8000, min(0x7FFF, quotient * step))

    @staticmethod
    def _clamp(value: int) -> int:
        return max(-0x8000, min(0x7FFF, value))

    def take_pcm(self) -> bytes:
        data = bytes(self._pcm)
        self._pcm.clear()
        return data

    # ------------------------------------------------------------------
    # 內部 / 生命週期
    # ------------------------------------------------------------------
    def _get16(self, relative: int) -> int:
        return self._regs[relative] | (self._regs[relative + 1] << 8)

    def _set16(self, relative: int, value: int) -> None:
        self._regs[relative] = value & 0xFF
        self._regs[relative + 1] = (value >> 8) & 0xFF

    def reset(self) -> None:
        self._regs[:] = bytes(SOUND_SIZE)
        self.fifo_a.clear()
        self.fifo_b.clear()
        self._pcm.clear()
        self._cycle_accumulator = 0
        self.enabled = False
        self._reset_channels()


__all__ = [
    "SOUND_BASE",
    "SOUND_SIZE",
    "FIFO_A_OFFSET",
    "FIFO_B_OFFSET",
    "DEFAULT_SAMPLE_RATE",
    "SoundController",
]
