# GBA Timers

> 本檔案整理自 [GBATEK](https://problemkaputt.de/gbatek.htm) 的「GBA Timers」章節。
> 來源採用 [mGBA GBATEK Markdown fork](https://github.com/mgba-emu/gbatek) 的 Markdown 轉存，保留原文的暫存器、位元欄位、程式碼與數值表示法。

# GBA Timers



The GBA includes four incrementing 16bit timers.

Timer 0 and 1 can be used to supply the sample rate for DMA sound channel A
and/or B.



## 4000100h - TM0CNT\_L - Timer 0 Counter/Reload (R/W)



## 4000104h - TM1CNT\_L - Timer 1 Counter/Reload (R/W)



## 4000108h - TM2CNT\_L - Timer 2 Counter/Reload (R/W)



## 400010Ch - TM3CNT\_L - Timer 3 Counter/Reload (R/W)


Writing to these registers initializes the \<reload> value (but does not
directly affect the current counter value). Reading returns the current
\<counter> value (or the recent/frozen counter value if the timer has been
stopped).

The reload value is copied into the counter only upon following two situations:
Automatically upon timer overflows, or when the timer start bit becomes changed
from 0 to 1.

Note: When simultaneously changing the start bit from 0 to 1, and setting the
reload value at the same time (by a single 32bit I/O operation), then the newly
written reload value is recognized as new counter value.



## 4000102h - TM0CNT\_H - Timer 0 Control (R/W)



## 4000106h - TM1CNT\_H - Timer 1 Control (R/W)



## 400010Ah - TM2CNT\_H - Timer 2 Control (R/W)



## 400010Eh - TM3CNT\_H - Timer 3 Control (R/W)


```
  Bit   Expl.
  0-1   Prescaler Selection (0=F/1, 1=F/64, 2=F/256, 3=F/1024)
  2     Count-up Timing   (0=Normal, 1=See below)  ;Not used in TM0CNT_H
  3-5   Not used
  6     Timer IRQ Enable  (0=Disable, 1=IRQ on Timer overflow)
  7     Timer Start/Stop  (0=Stop, 1=Operate)
  8-15  Not used
```

When Count-up Timing is enabled, the prescaler value is ignored, instead the
time is incremented each time when the previous counter overflows. This
function cannot be used for Timer 0 (as it is the first timer).

F = System Clock (16.78MHz).
