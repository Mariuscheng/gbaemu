# GBA DMA Transfers

> 本檔案整理自 [GBATEK](https://problemkaputt.de/gbatek.htm) 的「GBA DMA Transfers」章節。
> 來源採用 [mGBA GBATEK Markdown fork](https://github.com/mgba-emu/gbatek) 的 Markdown 轉存，保留原文的暫存器、位元欄位、程式碼與數值表示法。

# GBA DMA Transfers




## Overview


The GBA includes four DMA channels, the highest priority is assigned to DMA0,
followed by DMA1, DMA2, and DMA3. DMA Channels with lower priority are paused
until channels with higher priority have completed.

The CPU is paused when DMA transfers are active, however, the CPU is operating
during the periods when Sound/Blanking DMA transfers are paused.



## Special features of the separate DMA channels


DMA0 - highest priority, best for timing critical transfers (eg. HBlank DMA).

DMA1 and DMA2 - can be used to feed digital sample data to the Sound FIFOs.

DMA3 - can be used to write to Game Pak ROM/FlashROM (but not GamePak SRAM).

Aside from that, each DMA 0-3 may be used for whatever general purposes.



## 40000B0h,0B2h - DMA0SAD - DMA 0 Source Address (W) (internal memory)



## 40000BCh,0BEh - DMA1SAD - DMA 1 Source Address (W) (any memory)



## 40000C8h,0CAh - DMA2SAD - DMA 2 Source Address (W) (any memory)



## 40000D4h,0D6h - DMA3SAD - DMA 3 Source Address (W) (any memory)


The most significant address bits are ignored, only the least significant 27 or
28 bits are used (max 07FFFFFFh internal memory, or max 0FFFFFFFh any memory -
except SRAM ?!).



## 40000B4h,0B6h - DMA0DAD - DMA 0 Destination Address (W) (internal memory)



## 40000C0h,0C2h - DMA1DAD - DMA 1 Destination Address (W) (internal memory)



## 40000CCh,0CEh - DMA2DAD - DMA 2 Destination Address (W) (internal memory)



## 40000D8h,0DAh - DMA3DAD - DMA 3 Destination Address (W) (any memory)


The most significant address bits are ignored, only the least significant 27 or
28 bits are used (max. 07FFFFFFh internal memory or 0FFFFFFFh any memory -
except SRAM ?!).



## 40000B8h - DMA0CNT\_L - DMA 0 Word Count (W) (14 bit, 1..4000h)



## 40000C4h - DMA1CNT\_L - DMA 1 Word Count (W) (14 bit, 1..4000h)



## 40000D0h - DMA2CNT\_L - DMA 2 Word Count (W) (14 bit, 1..4000h)



## 40000DCh - DMA3CNT\_L - DMA 3 Word Count (W) (16 bit, 1..10000h)


Specifies the number of data units to be transferred, each unit is 16bit or
32bit depending on the transfer type, a value of zero is treated as max length
(ie. 4000h, or 10000h for DMA3).



## 40000BAh - DMA0CNT\_H - DMA 0 Control (R/W)



## 40000C6h - DMA1CNT\_H - DMA 1 Control (R/W)



## 40000D2h - DMA2CNT\_H - DMA 2 Control (R/W)



## 40000DEh - DMA3CNT\_H - DMA 3 Control (R/W)


```
  Bit   Expl.
  0-4   Not used
  5-6   Dest Addr Control  (0=Increment,1=Decrement,2=Fixed,3=Increment/Reload)
  7-8   Source Adr Control (0=Increment,1=Decrement,2=Fixed,3=Prohibited)
  9     DMA Repeat                   (0=Off, 1=On) (Must be zero if Bit 11 set)
  10    DMA Transfer Type            (0=16bit, 1=32bit)
  11    Game Pak DRQ  - DMA3 only -  (0=Normal, 1=DRQ <from> Game Pak, DMA3)
  12-13 DMA Start Timing  (0=Immediately, 1=VBlank, 2=HBlank, 3=Special)
          The 'Special' setting (Start Timing=3) depends on the DMA channel:
          DMA0=Prohibited, DMA1/DMA2=Sound FIFO, DMA3=Video Capture
  14    IRQ upon end of Word Count   (0=Disable, 1=Enable)
  15    DMA Enable                   (0=Off, 1=On)
```

After changing the Enable bit from 0 to 1, wait 2 clock cycles before accessing
any DMA related registers.


When accessing OAM (7000000h) or OBJ VRAM (6010000h) by HBlank Timing, then the
"H-Blank Interval Free" bit in DISPCNT register must be set.



## Source and Destination Address and Word Count Registers


The SAD, DAD, and CNT\_L registers are holding the initial start addresses, and
initial length. The hardware does NOT change the content of these registers
during or after the transfer.

The actual transfer takes place by using internal pointer/counter registers.
The initial values are copied into internal regs under the following
circumstances:

Upon DMA Enable (Bit 15) changing from 0 to 1: Reloads SAD, DAD, CNT\_L.

Upon Repeat: Reloads CNT\_L, and optionally DAD (Increment+Reload).



## DMA Repeat bit


If the Repeat bit is cleared: The Enable bit is automatically cleared after the
specified number of data units has been transferred.

If the Repeat bit is set: The Enable bit remains set after the transfer, and
the transfer will be restarted each time when the Start condition (eg. HBlank,
Fifo) becomes true. The specified number of data units is transferred
\<each> time when the transfer is (re-)started. The transfer will be
repeated forever, until it gets stopped by software.



## Sound DMA (FIFO Timing Mode) (DMA1 and DMA2 only)


In this mode, the DMA Repeat bit must be set, and the destination address must
be FIFO\_A (040000A0h) or FIFO\_B (040000A4h).

Upon DMA request from sound controller, 4 units of 32bits (16 bytes) are
transferred (both Word Count register and DMA Transfer Type bit are ignored).
The destination address will not be incremented in FIFO mode.

Keep in mind that DMA channels of higher priority may offhold sound DMA. For
example, when using a 64 kHz sample rate, 16 bytes of sound DMA data are
requested each 0.25ms (4 kHz), at this time another 16 bytes are still in the
FIFO so that there's still 0.25ms time to satisfy the DMA request. Thus DMAs
with higher priority should not be operated for longer than 0.25ms. (This
problem does not arise for HBlank transfers as HBlank time is limited to
16.212us.)



## Game Pak DMA


Only DMA 3 may be used to transfer data to/from Game Pak ROM or Flash ROM - it
cannot access Game Pak SRAM though (as SRAM data bus is limited to 8bit units).
In normal mode, DMA is requested as long until Word Count becomes zero. When
setting the 'Game Pack DRQ' bit, then the cartridge must contain an external
circuit which outputs a /DREQ signal. Note that there is only one pin for /DREQ
and /IREQ, thus the cartridge may not supply /IREQs while using DRQ mode.



## Video Capture Mode (DMA3 only)


Intended to copy a bitmap from memory (or from external hardware/camera) to
VRAM. When using this transfer mode, set the repeat bit, and write the number
of data units (per scanline) to the word count register. Capture works similar
like HBlank DMA, however, the transfer is started when VCOUNT=2, it is then
repeated each scanline, and it gets stopped when VCOUNT=162.



## Transfer End


The DMA Enable flag (Bit 15) is automatically cleared upon completion of the
transfer. The user may also clear this bit manually in order to stop the
transfer (obviously this is possible for Sound/Blanking DMAs only, in all other
cases the CPU is stopped until the transfer completes by itself).



## Transfer Rate/Timing


Except for the first data unit, all units are transferred by sequential reads
and writes. For n data units, the DMA transfer time is:

```
  2N+2(n-1)S+xI
```

Of which, 1N+(n-1)S are read cycles, and the other 1N+(n-1)S are write cycles,
actual number of cycles depends on the waitstates and bus-width of the source
and destination areas (as described in CPU Instruction Cycle Times chapter).
Internal time for DMA processing is 2I (normally), or 4I (if both source and
destination are in gamepak memory area).


DMA lockup when stopping while starting ???

Capture delayed, Capture Enable=AutoCleared ???
