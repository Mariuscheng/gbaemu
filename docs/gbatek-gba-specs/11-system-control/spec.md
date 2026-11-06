# GBA System Control

> 本檔案整理自 [GBATEK](https://problemkaputt.de/gbatek.htm) 的「GBA System Control」章節。
> 來源採用 [mGBA GBATEK Markdown fork](https://github.com/mgba-emu/gbatek) 的 Markdown 轉存，保留原文的暫存器、位元欄位、程式碼與數值表示法。

# GBA System Control




## 4000204h - WAITCNT - Waitstate Control (R/W)


This register is used to configure game pak access timings. The game pak ROM is
mirrored to three address regions at 08000000h, 0A000000h, and 0C000000h, these
areas are called Wait State 0-2. Different access timings may be assigned to
each area (this might be useful in case that a game pak contains several ROM
chips with different access times each).

```
  Bit   Expl.
  0-1   SRAM Wait Control          (0..3 = 4,3,2,8 cycles)
  2-3   Wait State 0 First Access  (0..3 = 4,3,2,8 cycles)
  4     Wait State 0 Second Access (0..1 = 2,1 cycles)
  5-6   Wait State 1 First Access  (0..3 = 4,3,2,8 cycles)
  7     Wait State 1 Second Access (0..1 = 4,1 cycles; unlike above WS0)
  8-9   Wait State 2 First Access  (0..3 = 4,3,2,8 cycles)
  10    Wait State 2 Second Access (0..1 = 8,1 cycles; unlike above WS0,WS1)
  11-12 PHI Terminal Output        (0..3 = Disable, 4.19MHz, 8.38MHz, 16.78MHz)
  13    Not used
  14    Game Pak Prefetch Buffer (Pipe) (0=Disable, 1=Enable)
  15    Game Pak Type Flag  (Read Only) (0=GBA, 1=CGB) (IN35 signal)
  16-31 Not used
```

At startup, the default setting is 0000h. Currently manufactured cartridges are
using the following settings: WS0/ROM=3,1 clks; SRAM=8 clks; WS2/EEPROM: 8,8
clks; prefetch enabled; that is, WAITCNT=4317h, for more info see "GBA
Cartridges" chapter.


First Access (Non-sequential) and Second Access (Sequential) define the
waitstates for N and S cycles, the actual access time is 1 clock cycle PLUS the
number of waitstates.

GamePak uses 16bit data bus, so that a 32bit access is split into TWO 16bit
accesses (of which, the second fragment is always sequential, even if the first
fragment was non-sequential).


- [GBA GamePak Prefetch](#gbagamepakprefetch)

NOTES:

The GBA forcefully uses non-sequential timing at the beginning of each
128K-block of gamepak ROM, eg. "LDMIA [801fff8h],r0-r7" will have
non-sequential timing at 8020000h.

The PHI Terminal output (PHI Pin of Gamepak Bus) should be disabled.



## 4000300h - POSTFLG - BYTE - Undocumented - Post Boot / Debug Control (R/W)


After initial reset, the GBA BIOS initializes the register to 01h, and any
further execution of the Reset vector (00000000h) will pass control to the
Debug vector (0000001Ch) when sensing the register to be still set to 01h.

```
  Bit   Expl.
  0     Undocumented. First Boot Flag  (0=First, 1=Further)
  1-7   Undocumented. Not used.
```

Normally the debug handler rejects control unless it detects Debug flags in
cartridge header, in that case it may redirect to a cut-down boot procedure
(bypassing Nintendo logo and boot delays, much like nocash burst boot for
multiboot software). I am not sure if it is possible to reset the GBA
externally without automatically resetting register 300h though.



## 4000301h - HALTCNT - BYTE - Undocumented - Low Power Mode Control (W)


Writing to this register switches the GBA into battery saving mode.

In Halt mode, the CPU is paused as long as (IE AND IF)=0, this should be used
to reduce power-consumption during periods when the CPU is waiting for
interrupt events.

In Stop mode, most of the hardware including sound and video are paused, this
very-low-power mode could be used much like a screensaver.

```
  Bit   Expl.
  0-6   Undocumented. Not used.
  7     Undocumented. Power Down Mode  (0=Halt, 1=Stop)
```

The current GBA BIOS addresses only the upper eight bits of this register (by
writing 00h or 80h to address 04000301h), however, as the register isn't
officially documented, some or all of the bits might have different meanings in
future GBA models.

For best forwards compatibility, it'd generally be more recommended to use the
BIOS Functions SWI 2 (Halt) or SWI 3 (Stop) rather than writing to this
register directly.



## 4000410h - Undocumented - Purpose Unknown ? 8bit (W)


The BIOS writes the 8bit value 0FFh to this address. Purpose Unknown.

Probably just another bug in the BIOS.



## 4000800h - 32bit - Undocumented - Internal Memory Control (R/W)


Supported by GBA and GBA SP only - NOT supported by DS (even in GBA mode).

Also supported by GBA Micro - but crashes on "overclocked" WRAM setting.

Initialized to 0D000020h (by hardware). Unlike all other I/O registers, this
register is mirrored across the whole I/O area (in increments of 64K, ie. at
4000800h, 4010800h, 4020800h, ..., 4FF0800h)

```
  Bit   Expl.
  0     Disable 32K+256K WRAM (0=Normal, 1=Disable) (when off: empty/prefetch)
         From endrift: bit0 swaps 00000000h-01FFFFFFh and 02000000h-03FFFFFFh
         in GBA mode (but keeps BIOS protection)
  1     Unknown          (Read/Write-able)
  2     Unknown          (Read/Write-able)
  3     Disable CGB Bootrom (0=Normal, 1=Disable, start cart at 0000h)
  4     Unused (0)
  5     Enable 256K WRAM (0=Disable, 1=Normal) (when off: mirror of 32K WRAM)
  6-23  Unused (0)
  24-27 Wait Control WRAM 256K (0-14 = 15..1 Waitstates, 15=Lockup)
  28-31 Unknown          (Read/Write-able)
```

The default value 0Dh in Bits 24-27 selects 2 waitstates for 256K WRAM (ie.
3/3/6 cycles 8/16/32bit accesses). The fastest possible setting would be 0Eh (1
waitstate, 2/2/4 cycles for 8/16/32bit), that works on GBA and GBA SP only, the
GBA Micro locks up with that setting (it's on-chip RAM is too slow, and works
only with 2 or more waitstates).


Note: One cycle equals approx. 59.59ns (ie. 16.78MHz clock).




# GBA GamePak Prefetch



GamePak Prefetch can be enabled in WAITCNT register. When prefetch buffer is
enabled, the GBA attempts to read opcodes from Game Pak ROM during periods when
the CPU is not using the bus (if any). Memory access is then performed with 0
Waits if the CPU requests data which is already stored in the buffer. The
prefetch buffer stores up to eight 16bit values.



## GamePak ROM Opcodes


The prefetch feature works only with \<opcodes> fetched from GamePak ROM.
Opcodes executed in RAM or BIOS are not affected by the prefetch feature (even
if that opcodes read \<data> from GamePak ROM).



## Prefetch Enable


For GamePak ROM opcodes, prefetch may occur in two situations:

```
  1) opcodes with internal cycles (I) which do not change R15, shift/rotate
     register-by-register, load opcodes (ldr,ldm,pop,swp), multiply opcodes
  2) opcodes that load/store memory (ldr,str,ldm,stm,etc.)
```



## Prefetch Disable Bug


When Prefetch is disabled, the Prefetch Disable Bug will occur for all

```
  "Opcodes in GamePak ROM with Internal Cycles which do not change R15"
```

for those opcodes, the bug changes the opcode fetch time from 1S to 1N.

Note: Affected opcodes (with I cycles) are: Shift/rotate register-by-register
opcodes, multiply opcodes, and load opcodes (ldr,ldm,pop,swp).
