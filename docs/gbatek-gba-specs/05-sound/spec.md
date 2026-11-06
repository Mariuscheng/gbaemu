# GBA Sound Controller

> 本檔案整理自 [GBATEK](https://problemkaputt.de/gbatek.htm) 的「GBA Sound Controller」章節。
> 來源採用 [mGBA GBATEK Markdown fork](https://github.com/mgba-emu/gbatek) 的 Markdown 轉存，保留原文的暫存器、位元欄位、程式碼與數值表示法。

# GBA Sound Controller



The GBA supplies four 'analogue' sound channels for Tone and Noise (mostly
compatible to CGB sound), as well as two 'digital' sound channels (which can be
used to replay 8bit DMA sample data).


- [GBA Sound Channel 1 - Tone & Sweep](#gbasoundchannel1tonesweep)
- [GBA Sound Channel 2 - Tone](#gbasoundchannel2tone)
- [GBA Sound Channel 3 - Wave Output](#gbasoundchannel3waveoutput)
- [GBA Sound Channel 4 - Noise](#gbasoundchannel4noise)
- [GBA Sound Channel A and B - DMA Sound](#gbasoundchannelaandbdmasound)

- [GBA Sound Control Registers](#gbasoundcontrolregisters)
- [GBA Comparison of CGB and GBA Sound](#gbacomparisonofcgbandgbasound)

The GBA includes only a single (mono) speaker built-in, each channel may be
output to either left and/or right channels by using the external line-out
connector (for stereo headphones, etc).




# GBA Sound Channel 1 - Tone & Sweep




## 4000060h - SOUND1CNT\_L (NR10) - Channel 1 Sweep register (R/W)


```
  Bit        Expl.
  0-2   R/W  Number of sweep shift      (n=0-7)
  3     R/W  Sweep Frequency Direction  (0=Increase, 1=Decrease)
  4-6   R/W  Sweep Time; units of 7.8ms (0-7, min=7.8ms, max=54.7ms)
  7-15  -    Not used
```

Sweep is disabled by setting Sweep Time to zero, if so, the direction bit
should be set.

The change of frequency (NR13,NR14) at each shift is calculated by the
following formula where X(0) is initial freq & X(t-1) is last freq:

```
  X(t) = X(t-1) +/- X(t-1)/2^n
```



## 4000062h - SOUND1CNT\_H (NR11, NR12) - Channel 1 Duty/Len/Envelope (R/W)


```
  Bit        Expl.
  0-5   W    Sound length; units of (64-n)/256s  (0-63)
  6-7   R/W  Wave Pattern Duty                   (0-3, see below)
  8-10  R/W  Envelope Step-Time; units of n/64s  (1-7, 0=No Envelope)
  11    R/W  Envelope Direction                  (0=Decrease, 1=Increase)
  12-15 R/W  Initial Volume of envelope          (1-15, 0=No Sound)
```

Wave Duty:

```
  0: 12.5% ( -_______-_______-_______ )
  1: 25%   ( --______--______--______ )
  2: 50%   ( ----____----____----____ ) (normal)
  3: 75%   ( ------__------__------__ )
```

The Length value is used only if Bit 6 in NR14 is set.



## 4000064h - SOUND1CNT\_X (NR13, NR14) - Channel 1 Frequency/Control (R/W)


```
  Bit        Expl.
  0-10  W    Frequency; 131072/(2048-n)Hz  (0-2047)
  11-13 -    Not used
  14    R/W  Length Flag  (1=Stop output when length in NR11 expires)
  15    W    Initial      (1=Restart Sound)
  16-31 -    Not used
```




# GBA Sound Channel 2 - Tone



This sound channel works exactly as channel 1, except that it doesn't have a
Tone Envelope/Sweep Register.



## 4000068h - SOUND2CNT\_L (NR21, NR22) - Channel 2 Duty/Length/Envelope (R/W)



## 400006Ah - Not used



## 400006Ch - SOUND2CNT\_H (NR23, NR24) - Channel 2 Frequency/Control (R/W)


For details, refer to channel 1 description.




# GBA Sound Channel 3 - Wave Output



This channel can be used to output digital sound, the length of the sample
buffer (Wave RAM) can be either 32 or 64 digits (4bit samples). This sound
channel can be also used to output normal tones when initializing the Wave RAM
by a square wave. This channel doesn't have a volume envelope register.



## 4000070h - SOUND3CNT\_L (NR30) - Channel 3 Stop/Wave RAM select (R/W)


```
  Bit        Expl.
  0-4   -    Not used
  5     R/W  Wave RAM Dimension   (0=One bank/32 digits, 1=Two banks/64 digits)
  6     R/W  Wave RAM Bank Number (0-1, see below)
  7     R/W  Sound Channel 3 Off  (0=Stop, 1=Playback)
  8-15  -    Not used
```

The currently selected Bank Number (Bit 6) will be played back, while
reading/writing to/from wave RAM will address the other (not selected) bank.
When dimension is set to two banks, output will start by replaying the
currently selected bank.



## 4000072h - SOUND3CNT\_H (NR31, NR32) - Channel 3 Length/Volume (R/W)


```
  Bit        Expl.
  0-7   W    Sound length; units of (256-n)/256s  (0-255)
  8-12  -    Not used.
  13-14 R/W  Sound Volume  (0=Mute/Zero, 1=100%, 2=50%, 3=25%)
  15    R/W  Force Volume  (0=Use above, 1=Force 75% regardless of above)
```

The Length value is used only if Bit 6 in NR34 is set.



## 4000074h - SOUND3CNT\_X (NR33, NR34) - Channel 3 Frequency/Control (R/W)


```
  Bit        Expl.
  0-10  W    Sample Rate; 2097152/(2048-n) Hz   (0-2047)
  11-13 -    Not used
  14    R/W  Length Flag  (1=Stop output when length in NR31 expires)
  15    W    Initial      (1=Restart Sound)
  16-31 -    Not used
```

The above sample rate specifies the number of wave RAM digits per second, the
actual tone frequency depends on the wave RAM content, for example:

```
  Wave RAM, single bank 32 digits   Tone Frequency
  FFFFFFFFFFFFFFFF0000000000000000  65536/(2048-n) Hz
  FFFFFFFF00000000FFFFFFFF00000000  131072/(2048-n) Hz
  FFFF0000FFFF0000FFFF0000FFFF0000  262144/(2048-n) Hz
  FF00FF00FF00FF00FF00FF00FF00FF00  524288/(2048-n) Hz
  F0F0F0F0F0F0F0F0F0F0F0F0F0F0F0F0  1048576/(2048-n) Hz
```



## 4000090h - WAVE\_RAM0\_L - Channel 3 Wave Pattern RAM (W/R)



## 4000092h - WAVE\_RAM0\_H - Channel 3 Wave Pattern RAM (W/R)



## 4000094h - WAVE\_RAM1\_L - Channel 3 Wave Pattern RAM (W/R)



## 4000096h - WAVE\_RAM1\_H - Channel 3 Wave Pattern RAM (W/R)



## 4000098h - WAVE\_RAM2\_L - Channel 3 Wave Pattern RAM (W/R)



## 400009Ah - WAVE\_RAM2\_H - Channel 3 Wave Pattern RAM (W/R)



## 400009Ch - WAVE\_RAM3\_L - Channel 3 Wave Pattern RAM (W/R)



## 400009Eh - WAVE\_RAM3\_H - Channel 3 Wave Pattern RAM (W/R)


This area contains 16 bytes (32 x 4bits) Wave Pattern data which is output by
channel 3. Data is played back ordered as follows: MSBs of 1st byte, followed
by LSBs of 1st byte, followed by MSBs of 2nd byte, and so on - this results in
a confusing ordering when filling Wave RAM in units of 16bit data - ie. samples
would be then located in Bits 4-7, 0-3, 12-15, 8-11.


In the GBA, two Wave Patterns exists (each 32 x 4bits), either one may be
played (as selected in NR30 register), the other bank may be accessed by the
users. After all 32 samples have been played, output of the same bank (or other
bank, as specified in NR30) will be automatically restarted.


Internally, Wave RAM is a giant shift-register, there is no pointer which is
addressing the currently played digit. Instead, the entire 128 bits are
shifted, and the 4 least significant bits are output.

Thus, when reading from Wave RAM, data might have changed its position. And,
when writing to Wave RAM all data should be updated (it'd be no good idea to
assume that old data is still located at the same position where it has been
written to previously).




# GBA Sound Channel 4 - Noise



This channel is used to output white noise. This is done by randomly switching
the amplitude between high and low at a given frequency. Depending on the
frequency the noise will appear 'harder' or 'softer'.


It is also possible to influence the function of the random generator, so the
that the output becomes more regular, resulting in a limited ability to output
Tone instead of Noise.



## 4000078h - SOUND4CNT\_L (NR41, NR42) - Channel 4 Length/Envelope (R/W)


```
  Bit        Expl.
  0-5   W    Sound length; units of (64-n)/256s  (0-63)
  6-7   -    Not used
  8-10  R/W  Envelope Step-Time; units of n/64s  (1-7, 0=No Envelope)
  11    R/W  Envelope Direction                  (0=Decrease, 1=Increase)
  12-15 R/W  Initial Volume of envelope          (1-15, 0=No Sound)
  16-31 -    Not used
```

The Length value is used only if Bit 6 in NR44 is set.



## 400007Ch - SOUND4CNT\_H (NR43, NR44) - Channel 4 Frequency/Control (R/W)


The amplitude is randomly switched between high and low at the given frequency.
A higher frequency will make the noise to appear 'softer'.

When Bit 3 is set, the output will become more regular, and some frequencies
will sound more like Tone than Noise.

```
  Bit        Expl.
  0-2   R/W  Dividing Ratio of Frequencies (r)
  3     R/W  Counter Step/Width (0=15 bits, 1=7 bits)
  4-7   R/W  Shift Clock Frequency (s)
  8-13  -    Not used
  14    R/W  Length Flag  (1=Stop output when length in NR41 expires)
  15    W    Initial      (1=Restart Sound)
  16-31 -    Not used
```

Frequency = 524288 Hz / r / 2^(s+1)     ;For r=0 assume r=0.5 instead



## Noise Random Generator (aka Polynomial Counter)


Noise randomly switches between HIGH and LOW levels, the output levels are
calculated by a shift register (X), at the selected frequency, as such:

```
  7bit:  X=X SHR 1, IF carry THEN Out=HIGH, X=X XOR 60h ELSE Out=LOW
  15bit: X=X SHR 1, IF carry THEN Out=HIGH, X=X XOR 6000h ELSE Out=LOW
```

The initial value when (re-)starting the sound is X=40h (7bit) or X=4000h
(15bit). The data stream repeats after 7Fh (7bit) or 7FFFh (15bit) steps.




# GBA Sound Channel A and B - DMA Sound



The GBA contains two DMA sound channels (A and B), each allowing to replay
digital sound (signed 8bit data, ie. -128..+127). Data can be transferred from
INTERNAL memory (not sure if EXTERNAL memory works also ?) to FIFO by using DMA
channel 1 or 2, the sample rate is generated by using one of the Timers.



## 40000A0h - FIFO\_A\_L - Sound A FIFO, Data 0 and Data 1 (W)



## 40000A2h - FIFO\_A\_H - Sound A FIFO, Data 2 and Data 3 (W)


These two registers may receive 32bit (4 bytes) of audio data (Data 0-3, Data 0
being located in least significant byte which is replayed first).

Internally, the capacity of the FIFO is 8 x 32bit (32 bytes), allowing to
buffer a small amount of samples. As the name says (First In First Out), oldest
data is replayed first.



## 40000A4h - FIFO\_B\_L - Sound B FIFO, Data 0 and Data 1 (W)



## 40000A6h - FIFO\_B\_H - Sound B FIFO, Data 2 and Data 3 (W)


Same as above, for Sound B.



## Initializing DMA-Sound Playback


- Select Timer 0 or 1 in SOUNDCNT\_H control register.

- Clear the FIFO.

- Manually write a sample byte to the FIFO.

- Initialize transfer mode for DMA 1 or 2.

- Initialize DMA Sound settings in sound control register.

- Start the timer.



## DMA-Sound Playback Procedure


The pseudo-procedure below is automatically repeated.

```
  If Timer overflows then
    Move 8bit data from FIFO to sound circuit.
    If FIFO contains only 4 x 32bits (16 bytes) then
      Request more data per DMA
      Receive 4 x 32bit (16 bytes) per DMA
    Endif
  Endif
```

This playback mechanism will be repeated forever, regardless of the actual
length of the sample buffer.



## Synchronizing Sample Buffers


The buffer-end may be determined by counting sound Timer IRQs (each sample
byte), or sound DMA IRQs (each 16th sample byte). Both methods would require a
lot of CPU time (IRQ processing), and both would fail if interrupts are
disabled for a longer period.

Better solutions would be to synchronize the sample rate/buffer length with
V-blanks, or to use a second timer (in count up/slave mode) which produces an
IRQ after the desired number of samples.



## The Sample Rate


The GBA hardware does internally re-sample all sound output to 32.768kHz
(default SOUNDBIAS setting). It'd thus do not make much sense to use higher
DMA/Timer rates. Best re-sampling accuracy can be gained by using DMA/Timer
rates of 32.768kHz, 16.384kHz, or 8.192kHz (ie. fragments of the physical
output rate).




# GBA Sound Control Registers




## 4000080h - SOUNDCNT\_L (NR50, NR51) - Channel L/R Volume/Enable (R/W)


```
  Bit        Expl.
  0-2   R/W  Sound 1-4 Master Volume RIGHT (0-7)
  3     -    Not used
  4-6   R/W  Sound 1-4 Master Volume LEFT (0-7)
  7     -    Not used
  8-11  R/W  Sound 1-4 Enable Flags RIGHT (each Bit 8-11, 0=Disable, 1=Enable)
  12-15 R/W  Sound 1-4 Enable Flags LEFT (each Bit 12-15, 0=Disable, 1=Enable)
```



## 4000082h - SOUNDCNT\_H (GBA only) - DMA Sound Control/Mixing (R/W)


```
  Bit        Expl.
  0-1   R/W  Sound # 1-4 Volume   (0=25%, 1=50%, 2=100%, 3=Prohibited)
  2     R/W  DMA Sound A Volume   (0=50%, 1=100%)
  3     R/W  DMA Sound B Volume   (0=50%, 1=100%)
  4-7   -    Not used
  8     R/W  DMA Sound A Enable RIGHT (0=Disable, 1=Enable)
  9     R/W  DMA Sound A Enable LEFT  (0=Disable, 1=Enable)
  10    R/W  DMA Sound A Timer Select (0=Timer 0, 1=Timer 1)
  11    W?   DMA Sound A Reset FIFO   (1=Reset)
  12    R/W  DMA Sound B Enable RIGHT (0=Disable, 1=Enable)
  13    R/W  DMA Sound B Enable LEFT  (0=Disable, 1=Enable)
  14    R/W  DMA Sound B Timer Select (0=Timer 0, 1=Timer 1)
  15    W?   DMA Sound B Reset FIFO   (1=Reset)
```



## 4000084h - SOUNDCNT\_X (NR52) - Sound on/off (R/W)


Bits 0-3 are automatically set when starting sound output, and are
automatically cleared when a sound ends. (Ie. when the length expires, as far
as length is enabled. The bits are NOT reset when an volume envelope ends.)

```
  Bit        Expl.
  0     R    Sound 1 ON flag (Read Only)
  1     R    Sound 2 ON flag (Read Only)
  2     R    Sound 3 ON flag (Read Only)
  3     R    Sound 4 ON flag (Read Only)
  4-6   -    Not used
  7     R/W  PSG/FIFO Master Enable (0=Disable, 1=Enable) (Read/Write)
  8-31  -    Not used
```

While Bit 7 is cleared, both PSG and FIFO sounds are disabled, and all PSG
registers at 4000060h..4000081h are reset to zero (and must be re-initialized
after re-enabling sound). However, registers 4000082h and 4000088h are kept
read/write-able (of which, 4000082h has no function when sound is off, whilst
4000088h does work even when sound is off).



## 4000088h - SOUNDBIAS - Sound PWM Control (R/W, see below)


This register controls the final sound output. The default setting is 0200h, it
is normally not required to change this value.

```
  Bit        Expl.
  0     -    Not used
  1-9   R/W  Bias Level (Default=100h, converting signed samples into unsigned)
  10-13 -    Not used
  14-15 R/W  Amplitude Resolution/Sampling Cycle (Default=0, see below)
  16-31 -    Not used
```

Amplitude Resolution/Sampling Cycle (0-3):

```
  0  9bit / 32.768kHz   (Default, best for DMA channels A,B)
  1  8bit / 65.536kHz
  2  7bit / 131.072kHz
  3  6bit / 262.144kHz  (Best for PSG channels 1-4)
```

The Bias Level has no audible effect on 3DS in GBA mode.

For more information on this register, read the descriptions below.



## 400008Ch - Not used



## 400008Eh - Not used




## Max Output Levels (with max volume settings)


Each of the two FIFOs can span the FULL output range (+/-200h).

Each of the four PSGs can span one QUARTER of the output range (+/-80h).

The current output levels of all six channels are added together by hardware.

So together, the FIFOs and PSGs, could reach THRICE the range (+/-600h).

The BIAS value is added to that signed value. With default BIAS (200h), the
possible range becomes -400h..+800h, however, values that exceed the unsigned
10bit output range of 0..3FFh are clipped to MinMax(0,3FFh).



## Resampling to 32.768kHz / 9bit (default)


The PSG channels 1-4 are internally generated at 262.144kHz, and DMA sound A-B
could be theoretically generated at timer rates up to 16.78MHz. However, the
final sound output is resampled to a rate of 32.768kHz, at 9bit depth (the
above 10bit value, divided by two). If necessary, rates higher than 32.768kHz
can be selected in the SOUNDBIAS register, that would result in a depth smaller
than 9bit though.



## PWM (Pulse Width Modulation) Output 16.78MHz / 1bit


Okay, now comes the actual output. The GBA can output only two voltages (low
and high), these 'bits' are output at system clock speed (16.78MHz). If using
the default 32.768kHz sampling rate, then 512 bits are output per sample
(512\*32K=16M). Each sample value (9bit range, N=0..511), would be then output
as N low bits, followed by 512-N high bits. The resulting 'noise' is smoothed
down by capacitors, by the speaker, and by human hearing, so that it will
effectively sound like clean D/A converted 9bit voltages at 32kHz sampling
rate.



## Changing the BIAS Level


Normally use 200h for clean sound output. A value of 000h might make sense
during periods when no sound is output (causing the PWM circuit to output
low-bits only, which is eventually reducing the power consumption, and/or
preventing 32KHz noise). Note: Using the SoundBias function (SWI 19h) allows to
change the level by slowly incrementing or decrementing it (without hard
scratch noise).



## Low Power Mode


When not using sound output, power consumption can be reduced by setting both
4000084h (PSG/FIFO) and 4000088h (BIAS) to zero.




# GBA Comparison of CGB and GBA Sound



The GBA sound controller is mostly the same than that of older monochrome
gameboy and CGB. The following changes have been done:



## New Sound Channels


Two new sound channels have been added that may be used to replay 8bit digital
sound. Sample rate and sample data must be supplied by using a Timer and a DMA
channel.



## New Control Registers


The SOUNDCNT\_H register controls the new DMA channels - as well as mixing with
the four old channels. The SOUNDBIAS register controls the final sound output.



## Sound Channel 3 Changes


The length of the Wave RAM is doubled by dividing it into two banks of 32
digits each, either one or both banks may be replayed (one after each other),
for details check NR30 Bit 5-6. Optionally, the sound may be output at 75%
volume, for details check NR32 Bit 7.



## Changed Control Registers


NR50 is not supporting Vin signals (that's been an external sound input from
cartridge).



## Changed I/O Addresses


The GBAs sound register are located at 04000060-040000AE instead of at
FF10-FF3F as in CGB and monochrome gameboy. However, note that there have been
new blank spaces inserted between some of the separate registers - therefore it
is NOT possible to port CGB software to GBA just by changing the sound base
address.



## Accessing I/O Registers


In some cases two of the old 8bit registers are packed into a 16bit register
and may be accessed as such.
