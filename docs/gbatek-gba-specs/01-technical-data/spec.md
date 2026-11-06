# GBA Technical Data

> 本檔案整理自 [GBATEK](https://problemkaputt.de/gbatek.htm) 的「GBA Technical Data」章節。
> 來源採用 [mGBA GBATEK Markdown fork](https://github.com/mgba-emu/gbatek) 的 Markdown 轉存，保留原文的暫存器、位元欄位、程式碼與數值表示法。

# GBA Technical Data




## CPU Modes


```
  ARM Mode     ARM7TDMI 32bit RISC CPU, 16.78MHz, 32bit opcodes (GBA)
  THUMB Mode   ARM7TDMI 32bit RISC CPU, 16.78MHz, 16bit opcodes (GBA)
  CGB Mode     Z80/8080-style 8bit CPU, 4.2MHz or 8.4MHz  (CGB compatibility)
  DMG Mode     Z80/8080-style 8bit CPU, 4.2MHz (monochrome gameboy compatib.)
```


## Internal Memory


```
  BIOS ROM     16 KBytes
  Work RAM     288 KBytes (Fast 32K on-chip, plus Slow 256K on-board)
  VRAM         96 KBytes
  OAM          1 KByte (128 OBJs 3x16bit, 32 OBJ-Rotation/Scalings 4x16bit)
  Palette RAM  1 KByte (256 BG colors, 256 OBJ colors)
```


## Video


```
  Display      240x160 pixels (2.9 inch TFT color LCD display)
  BG layers    4 background layers
  BG types     Tile/map based, or Bitmap based
  BG colors    256 colors, or 16 colors/16 palettes, or 32768 colors
  OBJ colors   256 colors, or 16 colors/16 palettes
  OBJ size     12 types (in range 8x8 up to 64x64 dots)
  OBJs/Screen  max. 128 OBJs of any size (up to 64x64 dots each)
  OBJs/Line    max. 128 OBJs of 8x8 dots size (under best circumstances)
  Priorities   OBJ/OBJ: 0-127, OBJ/BG: 0-3, BG/BG: 0-3
  Effects      Rotation/Scaling, alpha blending, fade-in/out, mosaic, window
  Backlight    GBA SP only (optionally by light on/off toggle button)
```


## Sound


```
  Analogue     4 channel CGB compatible (3x square wave, 1x noise)
  Digital      2 DMA sound channels
  Output       Built-in speaker (mono), or headphones socket (stereo)
```


## Controls


```
  Gamepad      4 Direction Keys, 6 Buttons
```


## Communication Ports


```
  Serial Port  Various transfer modes, 4-Player Link, Single Game Pak play
```


## External Memory


```
  GBA Game Pak max. 32MB ROM or flash ROM + max 64K SRAM
  CGB Game Pak max. 32KB ROM + 8KB SRAM (more memory requires banking)
```


## Case Dimensions


```
  Size (mm)    GBA: 145x81x25 - GBA SP: 82x82x24 (closed), 155x82x24 (stretch)
```


## Power Supply


```
  Battery GBA  GBA: 2x1.5V DC (AA), Life-time approx. 15 hours
  Battery SP   GBA SP: Built-in rechargeable Lithium ion battery, 3.7V 600mAh
  External     GBA: 3.3V DC 350mA - GBA SP: 5.2V DC 320mA
```


- ----------------------------------------------------------------------------



## Original Gameboy Advance (GBA)


```
        ____._____________...___.____
   ____/    :  CARTRIDGE  SIO   :    \____
  | L       _____________________  LED  R |
  |        |                     |        |
  |  _||_  |   2.9" TFT SCREEN   |    (A) |
  | |_  _| | 240x160pix  61x40mm | (B)    |
  |   ||   |    NO BACKLIGHT     |  ::::  |
  |        |                     | SPEAKR |
  | STRT() |_____________________|  ::::  |
  | SLCT()     GAME BOY ADVANCE    VOLUME |
  |____  OFF-ON  BATTERY 2xAA PHONES  _==_|
       \__.##.__________________,,___/
```



## GBA SP (GBA SP)


```
   _______________________                                 _
  | _____________________ |                               / /
  ||                     ||                              / /
  ||   2.9" TFT SCREEN   ||                             / /
  || 240x160pix  61x40mm ||                            / /
  ||   WITH BACKLIGHT    ||                           / /
  ||                     ||     GBA SP SIDE VIEWS    / /
  ||_____________________||                         / /
  |  GAME BOY ADVANCE SP  |   _____________________(_)
  |_______________________|  |. . . . . . . .'.'.   _|
  |_|________|________|_|_|  |_CARTRIDGE_:_BATT._:_|_| <-- EXT1/EXT2
  |L    EXT1     EXT2    R|
  |          (*)      LEDSo   _____________________ _
  (VOL_||_           (A)  o  |_____________________(_)
  |  |_  _| ,,,,,(B)      |  |. . . . . . . .'.'.   _|
  |    ||   ;SPK;         |  |_CARTRIDGE_:_BATT._:_|_| <-- EXT1/EXT2
  |         '''''      ON #                         _ _____________________
  |       SLCT STRT    OFF#   _____________________(_)_____________________|
  | CART.  ()   ()        |  |. . . . . . . .'.'.   _|
  |_:___________________:_|  |_CARTRIDGE_:_BATT._:_|_| <-- EXT1/EXT2
```



## Gameboy Micro (GBA Micro)


```
      ________________SIO_______________
     | L      __________________      R |
     |       |     GBA-MICRO    |       |
     | _||_  |  2.0" TFT SCREEN |    (A)| +
     ||_  _| |240x160pix 42x28mm| (B)   |VOL
     |  ||   |     BACKLIGHT    |       | -
     |       |__________________|  ...  |
     |___________SELECT__START__________|
       PWR   <--- CARTRIDGE SLOT ---> PHONES
```



## Nintendo DS (NDS)


```
     _____________________________________
    |        _____________________        |
    |       |                     |       |
    |       |    3" TFT SCREEN    |       |
    |       | 256x192pix  61x46mm |       |
    |       |      BACKLIGHT      |       |
    | ::::: |    Original NDS     | ::::: |
    | ::::: |_____________________| ::::: |
   _|        _          ______   _        |_  <-- gap between screens: 22mm
  |L|_______| |________|      |_| |_______|R|     (equivalent to 90 pixels)
  |_______   _____________________   _______|
  |  PWR  | |                     | |SEL STA|
  |   _   | |    3" TFT SCREEN    | |       |
  | _| |_ | | 256x192pix  61x46mm | |   X   |
  ||_   _|| |      BACKLIGHT      | | Y   A |
  |  |_|  | |    TOUCH SCREEN     | |   B   |
  |       | |_____________________| |       |
  |_______|             NintendoDS  |_______|
  |         MIC                LEDS         |
  |_________________________________________|
       VOL        SLOT2(GBA)     MIC/PHONES
```



## Nintendo DS Lite (NDS-Lite)


```
     _____________________________________
    |        _____________________        |
    |       |                     |       |
    |       |    3" TFT SCREEN    |       |
    |  ...  | 256x192pix  61x46mm |  ...  |
    |  ...  |      BACKLIGHT      |  ...  |
    |       |      NDS-LITE       |       |
    |       |_____________________|       |
    |___  _ _ _ _ _ _ _ _ _ _ _ _ _ _ ____|   <-- gap between screens: 23mm
   L| _ |_____________MIC____________|LEDS|R
    |   _    _____________________        |
    | _| |_ |                     |   X   |
    ||_   _||    3" TFT SCREEN    | Y   A |PWR
    |  |_|  | 256x192pix  61x46mm |   B   |
    |       |      BACKLIGHT      |       |
    |       |    TOUCH SCREEN     |oSTART |
    |       |_____________________|oSELECT|
    |_____________________________________|
       VOL        SLOT2(GBA)     MIC/PHONES
```



## Nintendo DSi (DSi)


```
     _____________________________________
    |        _____________________        |
    |       |                     |   O o | <-- CAM (O) and LED (o)
    |       |   3.25" TFT SCREEN  |       |     (on backside)
    |       | 256x192pix  66x50mm |       |
    |       |      BACKLIGHT      |       |
    |  __   |         DSi         |   __  |
    | (__)  |_____________________|  (__) |
    |___  _ _ _ _ _ _ _ _ _ _ _ _ _ _ ____|  <-- gap between screens: 23mm
   L|LEDS|__________CAM__MIC_________| __ |R                   (88 pixels)
  + |   _    _____________________        |
 VOL| _| |_ |                     |   X   | <-- SD Card Slot
  - ||_   _||   3.25" TFT SCREEN  | Y   A |
    |  |_|  | 256x192pix  66x50mm |   B   |
    |       |      BACKLIGHT      |       |
    |       |    TOUCH SCREEN     |oSTART |
    | POWERo|_____________________|oSELECT|
    |_____________________________________|
                                 MIC/PHONES
```



## Nintendo DSi XL


```
  As DSi, but bigger case, and bigger 4.2" screens
```



## Nintendo 3DS (Old3DS)


```
     _____________________________________
    |      __________CAM____________      | <-- internal camera
    |  .  |                         |  .  |     (and two back cameras and LED
    |. . .|     x.xx" TFT SCREEN    |. . .|     on backside)
    |  .  |   800x240pix  XXxXXmm   |  .  |
    |     |        BACKLIGHT        |    .|
    |     |     STEREOSCOPIC 3D     |    || <-- 3D slider
    |     |_________________________|    '|
    |___  _ _ _ _ _ _ _ _ _ _ _ _ _ _ ____|  <-- gap between screens: XXmm
   L| __ |___________________________| __o|R   <-- Notify RGB LED    (XX pix)
    |  .-.   _____________________        |
 VOL| (   ) |                     |   X   |  <-- wifi LED
    |  '-'  |   x.xx" TFT SCREEN  | Y   A |  <-- wifi Button
    |   _   | 320x240pix  XXxXXmm |   B   |
    | _| |_ |      BACKLIGHT      |       |
  SD||_   _||    TOUCH SCREEN     |       |
    |  |_|  |_____________________|       |
    |         SELECT  HOME  START  oPOWER |
    |_____________________________________|
                     PHONES       LEDs (power/charge)
```



## Gameboy Player (Gamecube Joypad) (GBA Player)


```
                   _________
       L____-------         -------____R
       /   ___   \           /   (Y)   \Z
      /   / O \   | (START) |        (X)\   Z      = Gameboy Player Menu
     |    \___/    \_______/      (A)    |  X or Y = Select button
     |\         _   \     /    (B)      /|
     | \___   _| |_  \   /   ___    ___/ |  optionally X/Y can be
     |    |\ |_   _| /   \  / C \  /|    |  swapped with L/R (?)
     |    | \  |_|  /     \ \___/ / |    |
     |    |  \_____/       \_____/  |    |  analogue sticks = ?
      \__/                           \__/
```



## Gameboy Player (Gamecube Bongos) (GBA Player)


```
       _______     _______
      /   Y   \   /   X   \   Y/B = left bongo rear/front side
     | . . . . |_| . . . . |  X/A = right bongo rear/front side
     |    B    |R|    A    |  S   = start/pause button
     |\_______/|_|\_______/|  R   = microphone (triggers R button)
     |\_______/|S|\_______/|
     |         |_|         |  (the X/Y inputs can be assigned to
     |\_______/| |\_______/|  GBA R/L inputs in GBA player setup)
      \_______/   \_______/
```


The GBA's separate 8bit/32bit CPU modes cannot be operated simultaneously.
Switching is allowed between ARM and THUMB modes only (that are the two GBA
modes).

This manual does not describe CGB and DMG modes, both are completely different
than GBA modes, and both cannot be accessed from inside of GBA modes anyways.



## Gameboy Player


An GBA Adapter for the Gamecube console; allowing to play GBA games on a
television set.

- [GBA Gameboy Player](#gbagameboyplayer)


## GBA SP Notes


Deluxe version of the original GBA. With backlight, new folded laptop-style
case, and built-in rechargeable battery. Appears to be 100% compatible with
GBA, there seems to be no way to detect SPs by software.



## Gameboy Micro (GBA Micro)


Minituarized GBA. Supports 32bit GBA games only (no 8bit DMG/CGB games). The
256K Main RAM is a bit slower than usually (cannot be "overclocked via port
4000800h).



## Nintendo DS (Dual Screen) Notes


New handheld with two screens, backwards compatible with GBA games, it is NOT
backwards compatible with older 8bit games (mono/color gameboys) though..

Also, the DS has no link port, so that GBA games will thus work only in single
player mode, link-port accessoires like printers cannot be used, and most
unfortunately multiboot won't work (trying to press Select+Start at powerup
will just lock up the DS).



## iQue Notes


iQue is a brand name used by Nintendo in China, iQue GBA and iQue DS are
essentially same as Nintendo GBA and Nintendo DS.

The iQue DS contains a larger firmware chip (the charset additionally contains
about 6700 simplified chinese characters), the bootmenu still allows to select
(only) six languages (japanese has been replaced by chinese). The iQue DS can
play normal international NDS games, plus chinese dedicated games. The latter
ones won't work on normal NDS consoles (that, reportedly simply due to a
firmware-version check contained in chinese dedicated games, aside from that
check, the games should be fully compatible with NDS consoles).
