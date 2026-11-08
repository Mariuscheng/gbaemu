# GBA Keypad Input

> 本檔案整理自 [GBATEK](https://problemkaputt.de/gbatek.htm) 的「GBA Keypad Input」章節。
> 來源採用 [mGBA GBATEK Markdown fork](https://github.com/mgba-emu/gbatek) 的 Markdown 轉存，保留原文的暫存器、位元欄位、程式碼與數值表示法。

# GBA Keypad Input



The built-in GBA gamepad has 4 direction keys, and 6 buttons.



## 4000130h - KEYINPUT - Key Status (R)


```
  Bit   Expl.
  0     Button A        (0=Pressed, 1=Released)
  1     Button B        (etc.)
  2     Select          (etc.)
  3     Start           (etc.)
  4     Right           (etc.)
  5     Left            (etc.)
  6     Up              (etc.)
  7     Down            (etc.)
  8     Button R        (etc.)
  9     Button L        (etc.)
  10-15 Not used
```

It'd be usually recommended to read-out this register only once per frame, and
to store the current state in memory. As a side effect, this method avoids
problems caused by switch bounce when a key is newly released or pressed.



## 4000132h - KEYCNT - Key Interrupt Control (R/W)


The keypad IRQ function is intended to terminate the very-low-power Stop mode,
it is not suitable for processing normal user input, to do this, most programs
are invoking their keypad handlers from within VBlank IRQ.

```
  Bit   Expl.
  0     Button A        (0=Ignore, 1=Select)
  1     Button B        (etc.)
  2     Select          (etc.)
  3     Start           (etc.)
  4     Right           (etc.)
  5     Left            (etc.)
  6     Up              (etc.)
  7     Down            (etc.)
  8     Button R        (etc.)
  9     Button L        (etc.)
  10-13 Not used
  14    Button IRQ Enable      (0=Disable, 1=Enable)
  15    Button IRQ Condition   (0=Logical OR, 1=Logical AND)
```

In logical OR mode, an interrupt is requested when at least one of the selected
buttons is pressed.

In logical AND mode, an interrupt is requested when ALL of the selected buttons
are pressed.



## Notes


In 8bit gameboy compatibility mode, L and R Buttons are used to toggle the
screen size between normal 160x144 pixels and stretched 240x144 pixels.

The GBA SP is additionally having a \* Button used to toggle the backlight on
and off (controlled by separate hardware logic, there's no way to detect or
change the current backlight state by software).
