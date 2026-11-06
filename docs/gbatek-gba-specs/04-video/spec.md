# GBA LCD Video Controller

> 本檔案整理自 [GBATEK](https://problemkaputt.de/gbatek.htm) 的「GBA LCD Video Controller」章節。
> 來源採用 [mGBA GBATEK Markdown fork](https://github.com/mgba-emu/gbatek) 的 Markdown 轉存，保留原文的暫存器、位元欄位、程式碼與數值表示法。

# GBA LCD Video Controller




## Registers


- [LCD I/O Display Control](#lcdiodisplaycontrol)
- [LCD I/O Interrupts and Status](#lcdiointerruptsandstatus)
- [LCD I/O BG Control](#lcdiobgcontrol)
- [LCD I/O BG Scrolling](#lcdiobgscrolling)
- [LCD I/O BG Rotation/Scaling](#lcdiobgrotationscaling)
- [LCD I/O Window Feature](#lcdiowindowfeature)
- [LCD I/O Mosaic Function](#lcdiomosaicfunction)
- [LCD I/O Color Special Effects](#lcdiocolorspecialeffects)


## VRAM


- [LCD VRAM Overview](#lcdvramoverview)
- [LCD VRAM Character Data](#lcdvramcharacterdata)
- [LCD VRAM BG Screen Data Format (BG Map)](#lcdvrambgscreendataformatbgmap)
- [LCD VRAM Bitmap BG Modes](#lcdvrambitmapbgmodes)


## Sprites


- [LCD OBJ - Overview](#lcdobjoverview)
- [LCD OBJ - OAM Attributes](#lcdobjoamattributes)
- [LCD OBJ - OAM Rotation/Scaling Parameters](#lcdobjoamrotationscalingparameters)
- [LCD OBJ - VRAM Character (Tile) Mapping](#lcdobjvramcharactertilemapping)


## Other


- [LCD Color Palettes](#lcdcolorpalettes)
- [LCD Dimensions and Timings](#lcddimensionsandtimings)



# LCD I/O Display Control




## 4000000h - DISPCNT - LCD Control (Read/Write)


```
  Bit   Expl.
  0-2   BG Mode                (0-5=Video Mode 0-5, 6-7=Prohibited)
  3     Reserved / CGB Mode    (0=GBA, 1=CGB; can be set only by BIOS opcodes)
  4     Display Frame Select   (0-1=Frame 0-1) (for BG Modes 4,5 only)
  5     H-Blank Interval Free  (1=Allow access to OAM during H-Blank)
  6     OBJ Character VRAM Mapping (0=Two dimensional, 1=One dimensional)
  7     Forced Blank           (1=Allow FAST access to VRAM,Palette,OAM)
  8     Screen Display BG0  (0=Off, 1=On)
  9     Screen Display BG1  (0=Off, 1=On)
  10    Screen Display BG2  (0=Off, 1=On)
  11    Screen Display BG3  (0=Off, 1=On)
  12    Screen Display OBJ  (0=Off, 1=On)
  13    Window 0 Display Flag   (0=Off, 1=On)
  14    Window 1 Display Flag   (0=Off, 1=On)
  15    OBJ Window Display Flag (0=Off, 1=On)
```


The table summarizes the facilities of the separate BG modes (video modes).

```
  Mode  Rot/Scal Layers Size               Tiles Colors       Features
  0     No       0123   256x256..512x515   1024  16/16..256/1 SFMABP
  1     Mixed    012-   (BG0,BG1 as above Mode 0, BG2 as below Mode 2)
  2     Yes      --23   128x128..1024x1024 256   256/1        S-MABP
  3     Yes      --2-   240x160            1     32768        --MABP
  4     Yes      --2-   240x160            2     256/1        --MABP
  5     Yes      --2-   160x128            2     32768        --MABP
```

Features: S)crolling, F)lip, M)osaic, A)lphaBlending, B)rightness, P)riority.


BG Modes 0-2 are Tile/Map-based. BG Modes 3-5 are Bitmap-based, in these modes
1 or 2 Frames (ie. bitmaps, or 'full screen tiles') exists, if two frames
exist, either one can be displayed, and the other one can be redrawn in
background.



## Blanking Bits


Setting Forced Blank (Bit 7) causes the video controller to display white
lines, and all VRAM, Palette RAM, and OAM may be accessed.

"When the internal HV synchronous counter cancels a forced blank during a
display period, the display begins from the beginning, following the display of
two vertical lines." What ?

Setting H-Blank Interval Free (Bit 5) allows to access OAM during H-Blank time
- using this feature reduces the number of sprites that can be displayed per
line.



## Display Enable Bits


By default, BG0-3 and OBJ Display Flags (Bit 8-12) are used to enable/disable
BGs and OBJ. When enabling Window 0 and/or 1 (Bit 13-14), color special effects
may be used, and BG0-3 and OBJ are controlled by the window(s).



## Frame Selection


In BG Modes 4 and 5 (Bitmap modes), either one of the two bitmaps/frames may be
displayed (Bit 4), allowing the user to update the other (invisible) frame in
background. In BG Mode 3, only one frame exists.

In BG Modes 0-2 (Tile/Map based modes), a similar effect may be gained by
altering the base address(es) of BG Map and/or BG Character data.



## 4000002h - Undocumented - Green Swap (R/W)


Normally, red green blue intensities for a group of two pixels is output as
BGRbgr (uppercase for left pixel at even xloc, lowercase for right pixel at odd
xloc). When the Green Swap bit is set, each pixel group is output as BgRbGr
(ie. green intensity of each two pixels exchanged).

```
  Bit   Expl.
  0     Green Swap  (0=Normal, 1=Swap)
  1-15  Not used
```

This feature appears to be applied to the final picture (ie. after mixing the
separate BG and OBJ layers). Eventually intended for other display types (with
other pin-outs). With normal GBA hardware it is just producing an interesting
dirt effect.

The NDS DISPCNT registers are 32bit (4000000h..4000003h), so Green Swap doesn't
exist in NDS mode, however, the NDS does support Green Swap in GBA mode.




# LCD I/O Interrupts and Status




## 4000004h - DISPSTAT - General LCD Status (Read/Write)


Display status and Interrupt control. The H-Blank conditions are generated once
per scanline, including for the 'hidden' scanlines during V-Blank.

```
  Bit   Expl.
  0     V-Blank flag   (Read only) (1=VBlank) (set in line 160..226; not 227)
  1     H-Blank flag   (Read only) (1=HBlank) (toggled in all lines, 0..227)
  2     V-Counter flag (Read only) (1=Match)  (set in selected line)     (R)
  3     V-Blank IRQ Enable         (1=Enable)                          (R/W)
  4     H-Blank IRQ Enable         (1=Enable)                          (R/W)
  5     V-Counter IRQ Enable       (1=Enable)                          (R/W)
  6     Not used (0) / DSi: LCD Initialization Ready (0=Busy, 1=Ready)   (R)
  7     Not used (0) / NDS: MSB of V-Vcount Setting (LYC.Bit8) (0..262)(R/W)
  8-15  V-Count Setting (LYC)      (0..227)                            (R/W)
```

The V-Count-Setting value is much the same as LYC of older gameboys, when its
value is identical to the content of the VCOUNT register then the V-Counter
flag is set (Bit 2), and (if enabled in Bit 5) an interrupt is requested.

Although the drawing time is only 960 cycles (240\*4), the H-Blank flag is "0"
for a total of 1006 cycles.



## 4000006h - VCOUNT - Vertical Counter (Read only)


Indicates the currently drawn scanline, values in range from 160..227 indicate
'hidden' scanlines within VBlank area.

```
  Bit   Expl.
  0-7   Current Scanline (LY)      (0..227)                              (R)
  8     Not used (0) / NDS: MSB of Current Scanline (LY.Bit8) (0..262)   (R)
  9-15  Not Used (0)
```

Note: This is much the same than the 'LY' register of older gameboys.




# LCD I/O BG Control




## 4000008h - BG0CNT - BG0 Control (R/W) (BG Modes 0,1 only)



## 400000Ah - BG1CNT - BG1 Control (R/W) (BG Modes 0,1 only)



## 400000Ch - BG2CNT - BG2 Control (R/W) (BG Modes 0,1,2 only)



## 400000Eh - BG3CNT - BG3 Control (R/W) (BG Modes 0,2 only)


```
  Bit   Expl.
  0-1   BG Priority           (0-3, 0=Highest)
  2-3   Character Base Block  (0-3, in units of 16 KBytes) (=BG Tile Data)
  4-5   Not used (must be zero) (except in NDS mode: MSBs of char base)
  6     Mosaic                (0=Disable, 1=Enable)
  7     Colors/Palettes       (0=16/16, 1=256/1)
  8-12  Screen Base Block     (0-31, in units of 2 KBytes) (=BG Map Data)
  13    BG0/BG1: Not used (except in NDS mode: Ext Palette Slot for BG0/BG1)
  13    BG2/BG3: Display Area Overflow (0=Transparent, 1=Wraparound)
  14-15 Screen Size (0-3)
```

Internal Screen Size (dots) and size of BG Map (bytes):

```
  Value  Text Mode      Rotation/Scaling Mode
  0      256x256 (2K)   128x128   (256 bytes)
  1      512x256 (4K)   256x256   (1K)
  2      256x512 (4K)   512x512   (4K)
  3      512x512 (8K)   1024x1024 (16K)
```

In case that some or all BGs are set to same priority then BG0 is having the
highest, and BG3 the lowest priority.


In 'Text Modes', the screen size is organized as follows: The screen consists
of one or more 256x256 pixel (32x32 tiles) areas. When Size=0: only 1 area
(SC0), when Size=1 or Size=2: two areas (SC0,SC1 either horizontally or
vertically arranged next to each other), when Size=3: four areas (SC0,SC1 in
upper row, SC2,SC3 in lower row). Whereas SC0 is defined by the normal BG Map
base address (Bit 8-12 of BGxCNT), SC1 uses same address +2K, SC2 address +4K,
SC3 address +6K. When the screen is scrolled it'll always wraparound.


In 'Rotation/Scaling Modes', the screen size is organized as follows, only one
area (SC0) of variable size 128x128..1024x1024 pixels (16x16..128x128 tiles)
exists. When the screen is rotated/scaled (or scrolled?) so that the LCD
viewport reaches outside of the background/screen area, then BG may be either
displayed as transparent or wraparound (Bit 13 of BGxCNT).




# LCD I/O BG Scrolling




## 4000010h - BG0HOFS - BG0 X-Offset (W)



## 4000012h - BG0VOFS - BG0 Y-Offset (W)


```
  Bit   Expl.
  0-8   Offset (0-511)
  9-15  Not used
```

Specifies the coordinate of the upperleft first visible dot of BG0 background
layer, ie. used to scroll the BG0 area.



## 4000014h - BG1HOFS - BG1 X-Offset (W)



## 4000016h - BG1VOFS - BG1 Y-Offset (W)


Same as above BG0HOFS and BG0VOFS for BG1 respectively.



## 4000018h - BG2HOFS - BG2 X-Offset (W)



## 400001Ah - BG2VOFS - BG2 Y-Offset (W)


Same as above BG0HOFS and BG0VOFS for BG2 respectively.



## 400001Ch - BG3HOFS - BG3 X-Offset (W)



## 400001Eh - BG3VOFS - BG3 Y-Offset (W)


Same as above BG0HOFS and BG0VOFS for BG3 respectively.


The above BG scrolling registers are exclusively used in Text modes, ie. for
all layers in BG Mode 0, and for the first two layers in BG mode 1.

In other BG modes (Rotation/Scaling and Bitmap modes) above registers are
ignored. Instead, the screen may be scrolled by modifying the BG
Rotation/Scaling Reference Point registers.




# LCD I/O BG Rotation/Scaling




## 4000028h - BG2X\_L - BG2 Reference Point X-Coordinate, lower 16 bit (W)



## 400002Ah - BG2X\_H - BG2 Reference Point X-Coordinate, upper 12 bit (W)



## 400002Ch - BG2Y\_L - BG2 Reference Point Y-Coordinate, lower 16 bit (W)



## 400002Eh - BG2Y\_H - BG2 Reference Point Y-Coordinate, upper 12 bit (W)


These registers are replacing the BG scrolling registers which are used for
Text mode, ie. the X/Y coordinates specify the source position from inside of
the BG Map/Bitmap of the pixel to be displayed at upper left of the GBA
display. The normal BG scrolling registers are ignored in Rotation/Scaling and
Bitmap modes.

```
  Bit   Expl.
  0-7   Fractional portion (8 bits)
  8-26  Integer portion    (19 bits)
  27    Sign               (1 bit)
  28-31 Not used
```

Because values are shifted left by eight, fractional portions may be specified
in steps of 1/256 pixels (this would be relevant only if the screen is actually
rotated or scaled). Normal signed 32bit values may be written to above
registers (the most significant bits will be ignored and the value will be
cut-down to 28bits, but this is no actual problem because signed values have
set all MSBs to the same value).



## Internal Reference Point Registers


The above reference points are automatically copied to internal registers
during each vblank, specifying the origin for the first scanline. The internal
registers are then incremented by dmx and dmy after each scanline.

Caution: Writing to a reference point register by software outside of the
Vblank period does immediately copy the new value to the corresponding internal
register, that means: in the current frame, the new value specifies the origin
of the \<current> scanline (instead of the topmost scanline).



## 4000020h - BG2PA - BG2 Rotation/Scaling Parameter A (alias dx) (W)



## 4000022h - BG2PB - BG2 Rotation/Scaling Parameter B (alias dmx) (W)



## 4000024h - BG2PC - BG2 Rotation/Scaling Parameter C (alias dy)  (W)



## 4000026h - BG2PD - BG2 Rotation/Scaling Parameter D (alias dmy) (W)


```
  Bit   Expl.
  0-7   Fractional portion (8 bits)
  8-14  Integer portion    (7 bits)
  15    Sign               (1 bit)
```

See below for details.



## 400003Xh - BG3X\_L/H, BG3Y\_L/H, BG3PA-D - BG3 Rotation/Scaling Parameters


Same as above BG2 Reference Point, and Rotation/Scaling Parameters, for BG3
respectively.



## dx (PA) and dy (PC)


When transforming a horizontal line, dx and dy specify the resulting gradient
and magnification for that line. For example:

Horizontal line, length=100, dx=1, and dy=1. The resulting line would be drawn
at 45 degrees, f(y)=1/1\*x. Note that this would involve that line is magnified,
the new length is SQR(100^2+100^2)=141.42. Yup, exactly - that's the old a^2 +
b^2 = c^2 formula.



## dmx (PB) and dmy (PD)


These values define the resulting gradient and magnification for transformation
of vertical lines. However, when rotating a square area (which is surrounded by
horizontal and vertical lines), then the desired result should be usually a
rotated \<square> area (ie. not a parallelogram, for example).

Thus, dmx and dmy must be defined in direct relationship to dx and dy, taking
the example above, we'd have to set dmx=-1, and dmy=1, f(x)=-1/1\*y.



## Area Overflow


In result of rotation/scaling it may often happen that areas outside of the
actual BG area become moved into the LCD viewport. Depending of the Area
Overflow bit (BG2CNT and BG3CNT, Bit 13) these areas may be either displayed
(by wrapping the BG area), or may be displayed transparent.

This works only in BG modes 1 and 2. The area overflow is ignored in Bitmap
modes (BG modes 3-5), the outside of the Bitmaps is always transparent.


--- more details and confusing or helpful formulas ---



## The following parameters are required for Rotation/Scaling


```
  Rotation Center X and Y Coordinates (x0,y0)
  Rotation Angle                      (alpha)
  Magnification X and Y Values        (xMag,yMag)
```

The display is rotated by 'alpha' degrees around the center.

The displayed picture is magnified by 'xMag' along x-Axis (Y=y0) and 'yMag'
along y-Axis (X=x0).



## Calculating Rotation/Scaling Parameters A-D


```
  A = Cos (alpha) / xMag    ;distance moved in direction x, same line
  B = Sin (alpha) / xMag    ;distance moved in direction x, next line
  C = Sin (alpha) / yMag    ;distance moved in direction y, same line
  D = Cos (alpha) / yMag    ;distance moved in direction y, next line
```



## Calculating the position of a rotated/scaled dot


Using the following expressions,

```
  x0,y0    Rotation Center
  x1,y1    Old Position of a pixel (before rotation/scaling)
  x2,y2    New position of above pixel (after rotation scaling)
  A,B,C,D  BG2PA-BG2PD Parameters (as calculated above)
```

the following formula can be used to calculate x2,y2:

```
  x2 = A(x1-x0) + B(y1-y0) + x0
  y2 = C(x1-x0) + D(y1-y0) + y0
```




# LCD I/O Window Feature



The Window Feature may be used to split the screen into four regions. The
BG0-3,OBJ layers and Color Special Effects can be separately enabled or
disabled in each of these regions.



## The DISPCNT Register


DISPCNT Bits 13-15 are used to enable Window 0, Window 1, and/or OBJ Window
regions, if any of these regions is enabled then the "Outside of Windows"
region is automatically enabled, too.

DISPCNT Bits 8-12 are kept used as master enable bits for the BG0-3,OBJ layers,
a layer is displayed only if both DISPCNT and WININ/OUT enable bits are set.



## 4000040h - WIN0H - Window 0 Horizontal Dimensions (W)



## 4000042h - WIN1H - Window 1 Horizontal Dimensions (W)


```
  Bit   Expl.
  0-7   X2, Rightmost coordinate of window, plus 1
  8-15  X1, Leftmost coordinate of window
```

Garbage values of X2>240 or X1>X2 are interpreted as X2=240.



## 4000044h - WIN0V - Window 0 Vertical Dimensions (W)



## 4000046h - WIN1V - Window 1 Vertical Dimensions (W)


```
  Bit   Expl.
  0-7   Y2, Bottom-most coordinate of window, plus 1
  8-15  Y1, Top-most coordinate of window
```

Garbage values of Y2>160 or Y1>Y2 are interpreted as Y2=160.



## 4000048h - WININ - Control of Inside of Window(s) (R/W)


```
  Bit   Expl.
  0-3   Window 0 BG0-BG3 Enable Bits     (0=No Display, 1=Display)
  4     Window 0 OBJ Enable Bit          (0=No Display, 1=Display)
  5     Window 0 Color Special Effect    (0=Disable, 1=Enable)
  6-7   Not used
  8-11  Window 1 BG0-BG3 Enable Bits     (0=No Display, 1=Display)
  12    Window 1 OBJ Enable Bit          (0=No Display, 1=Display)
  13    Window 1 Color Special Effect    (0=Disable, 1=Enable)
  14-15 Not used
```



## 400004Ah - WINOUT - Control of Outside of Windows & Inside of OBJ Window (R/W)


```
  Bit   Expl.
  0-3   Outside BG0-BG3 Enable Bits      (0=No Display, 1=Display)
  4     Outside OBJ Enable Bit           (0=No Display, 1=Display)
  5     Outside Color Special Effect     (0=Disable, 1=Enable)
  6-7   Not used
  8-11  OBJ Window BG0-BG3 Enable Bits   (0=No Display, 1=Display)
  12    OBJ Window OBJ Enable Bit        (0=No Display, 1=Display)
  13    OBJ Window Color Special Effect  (0=Disable, 1=Enable)
  14-15 Not used
```



## The OBJ Window


The dimension of the OBJ Window is specified by OBJs which are having the "OBJ
Mode" attribute being set to "OBJ Window". Any non-transparent dots of any such
OBJs are marked as OBJ Window area. The OBJ itself is not displayed.

The color, palette, and display priority of these OBJs are ignored. Both
DISPCNT Bits 12 and 15 must be set when defining OBJ Window region(s).



## Window Priority


In case that more than one window is enabled, and that these windows do
overlap, Window 0 is having highest priority, Window 1 medium, and Obj Window
lowest priority. Outside of Window is having zero priority, it is used for all
dots which are not inside of any window region.




# LCD I/O Mosaic Function




## 400004Ch - MOSAIC - Mosaic Size (W)


The Mosaic function can be separately enabled/disabled for BG0-BG3 by
BG0CNT-BG3CNT Registers, as well as for each OBJ0-127 by OBJ attributes in OAM
memory. Also, setting all of the bits below to zero effectively disables the
mosaic function.

```
  Bit   Expl.
  0-3   BG Mosaic H-Size  (minus 1)
  4-7   BG Mosaic V-Size  (minus 1)
  8-11  OBJ Mosaic H-Size (minus 1)
  12-15 OBJ Mosaic V-Size (minus 1)
  16-31 Not used
```

Example: When setting H-Size to 5, then pixels 0-5 of each display row are
colorized as pixel 0, pixels 6-11 as pixel 6, pixels 12-17 as pixel 12, and so
on.


Normally, a 'mosaic-pixel' is colorized by the color of the upperleft covered
pixel. In many cases it might be more desireful to use the color of the pixel
in the center of the covered area - this effect may be gained by scrolling the
background (or by adjusting the OBJ position, as far as upper/left rows/columns
of OBJ are transparent).




# LCD I/O Color Special Effects



Two types of Special Effects are supported: Alpha Blending (Semi-Transparency)
allows to combine colors of two selected surfaces. Brightness Increase/Decrease
adjust the brightness of the selected surface.



## 4000050h - BLDCNT - Color Special Effects Selection (R/W)


```
  Bit   Expl.
  0     BG0 1st Target Pixel (Background 0)
  1     BG1 1st Target Pixel (Background 1)
  2     BG2 1st Target Pixel (Background 2)
  3     BG3 1st Target Pixel (Background 3)
  4     OBJ 1st Target Pixel (Top-most OBJ pixel)
  5     BD  1st Target Pixel (Backdrop)
  6-7   Color Special Effect (0-3, see below)
         0 = None                (Special effects disabled)
         1 = Alpha Blending      (1st+2nd Target mixed)
         2 = Brightness Increase (1st Target becomes whiter)
         3 = Brightness Decrease (1st Target becomes blacker)
  8     BG0 2nd Target Pixel (Background 0)
  9     BG1 2nd Target Pixel (Background 1)
  10    BG2 2nd Target Pixel (Background 2)
  11    BG3 2nd Target Pixel (Background 3)
  12    OBJ 2nd Target Pixel (Top-most OBJ pixel)
  13    BD  2nd Target Pixel (Backdrop)
  14-15 Not used
```

Selects the 1st Target layer(s) for special effects. For Alpha
Blending/Semi-Transparency, it does also select the 2nd Target layer(s), which
should have next lower display priority as the 1st Target.

However, any combinations are possible, including that all layers may be
selected as both 1st+2nd target, in that case the top-most pixel will be used
as 1st target, and the next lower pixel as 2nd target.



## 4000052h - BLDALPHA - Alpha Blending Coefficients (R/W) (not W)


Used for Color Special Effects Mode 1, and for Semi-Transparent OBJs.

```
  Bit   Expl.
  0-4   EVA Coefficient (1st Target) (0..16 = 0/16..16/16, 17..31=16/16)
  5-7   Not used
  8-12  EVB Coefficient (2nd Target) (0..16 = 0/16..16/16, 17..31=16/16)
  13-15 Not used
```

For this effect, the top-most non-transparent pixel must be selected as 1st
Target, and the next-lower non-transparent pixel must be selected as 2nd
Target, if so - and only if so, then color intensities of 1st and 2nd Target
are mixed together by using the parameters in BLDALPHA register, for each pixel
each R, G, B intensities are calculated separately:

```
  I = MIN ( 31, I1st*EVA + I2nd*EVB )
```

Otherwise - for example, if only one target exists, or if a non-transparent
non-2nd-target pixel is moved between the two targets, or if 2nd target has
higher display priority than 1st target - then only the top-most pixel is
displayed (at normal intensity, regardless of BLDALPHA).



## 4000054h - BLDY - Brightness (Fade-In/Out) Coefficient (W) (not R/W)


Used for Color Special Effects Modes 2 and 3.

```
  Bit   Expl.
  0-4   EVY Coefficient (Brightness) (0..16 = 0/16..16/16, 17..31=16/16)
  5-31  Not used
```

For each pixel each R, G, B intensities are calculated separately:

```
  I = I1st + (31-I1st)*EVY   ;For Brightness Increase
  I = I1st - (I1st)*EVY      ;For Brightness Decrease
```

The color intensities of any selected 1st target surface(s) are increased or
decreased by using the parameter in BLDY register.



## Semi-Transparent OBJs


OBJs that are defined as 'Semi-Transparent' in OAM memory are always selected
as 1st Target (regardless of BLDCNT Bit 4), and are always using Alpha Blending
mode (regardless of BLDCNT Bit 6-7).

The BLDCNT register may be used to perform Brightness effects on the OBJ
(and/or other BG/BD layers). However, if a semi-transparent OBJ pixel does
overlap a 2nd target pixel, then semi-transparency becomes priority, and the
brightness effect will not take place (neither on 1st, nor 2nd target).



## The OBJ Layer


Before special effects are applied, the display controller computes the OBJ
priority ordering, and isolates the top-most OBJ pixel. In result, only the
top-most OBJ pixel is recursed at the time when processing special effects. Ie.
alpha blending and semi-transparency can be used for OBJ-to-BG or BG-to-OBJ ,
but not for OBJ-to-OBJ.




# LCD VRAM Overview



The GBA contains 96 Kbytes VRAM built-in, located at address 06000000-06017FFF,
depending on the BG Mode used as follows:



## BG Mode 0,1,2 (Tile/Map based Modes)


```
  06000000-0600FFFF  64 KBytes shared for BG Map and Tiles
  06010000-06017FFF  32 KBytes OBJ Tiles
```

The shared 64K area can be split into BG Map area(s), and BG Tiles area(s), the
respective addresses for Map and Tile areas are set up by BG0CNT-BG3CNT
registers. The Map address may be specified in units of 2K (steps of 800h), the
Tile address in units of 16K (steps of 4000h).



## BG Mode 0,1 (Tile/Map based Text mode)


The tiles may have 4bit or 8bit color depth, minimum map size is 32x32 tiles,
maximum is 64x64 tiles, up to 1024 tiles can be used per map.

```
  Item        Depth     Required Memory
  One Tile    4bit      20h bytes
  One Tile    8bit      40h bytes
  1024 Tiles  4bit      8000h (32K)
  1024 Tiles  8bit      10000h (64K) - excluding some bytes for BG map
  BG Map      32x32     800h (2K)
  BG Map      64x64     2000h (8K)
```



## BG Mode 1,2 (Tile/Map based Rotation/Scaling mode)


The tiles may have 8bit color depth only, minimum map size is 16x16 tiles,
maximum is 128x128 tiles, up to 256 tiles can be used per map.

```
  Item        Depth     Required Memory
  One Tile    8bit      40h bytes
  256  Tiles  8bit      4000h (16K)
  BG Map      16x16     100h bytes
  BG Map      128x128   4000h (16K)
```



## BG Mode 3 (Bitmap based Mode for still images)


```
  06000000-06013FFF  80 KBytes Frame 0 buffer (only 75K actually used)
  06014000-06017FFF  16 KBytes OBJ Tiles
```



## BG Mode 4,5 (Bitmap based Modes)


```
  06000000-06009FFF  40 KBytes Frame 0 buffer (only 37.5K used in Mode 4)
  0600A000-06013FFF  40 KBytes Frame 1 buffer (only 37.5K used in Mode 4)
  06014000-06017FFF  16 KBytes OBJ Tiles
```



## Note


Additionally to the above VRAM, the GBA also contains 1 KByte Palette RAM (at
05000000h) and 1 KByte OAM (at 07000000h) which are both used by the display
controller as well.




# LCD VRAM Character Data



Each character (tile) consists of 8x8 dots (64 dots in total). The color depth
may be either 4bit or 8bit (see BG0CNT-BG3CNT).



## 4bit depth (16 colors, 16 palettes)


Each tile occupies 32 bytes of memory, the first 4 bytes for the topmost row of
the tile, and so on. Each byte representing two dots, the lower 4 bits define
the color for the left (!) dot, the upper 4 bits the color for the right dot.



## 8bit depth (256 colors, 1 palette)


Each tile occupies 64 bytes of memory, the first 8 bytes for the topmost row of
the tile, and so on. Each byte selects the palette entry for each dot.




# LCD VRAM BG Screen Data Format (BG Map)



The display background consists of 8x8 dot tiles, the arrangement of these
tiles is specified by the BG Screen Data (BG Map). The separate entries in this
map are as follows:



## Text BG Screen (2 bytes per entry)


Specifies the tile number and attributes. Note that BG tile numbers are always
specified in steps of 1 (unlike OBJ tile numbers which are using steps of two
in 256 color/1 palette mode).

```
  Bit   Expl.
  0-9   Tile Number     (0-1023) (a bit less in 256 color mode, because
                           there'd be otherwise no room for the bg map)
  10    Horizontal Flip (0=Normal, 1=Mirrored)
  11    Vertical Flip   (0=Normal, 1=Mirrored)
  12-15 Palette Number  (0-15)    (Not used in 256 color/1 palette mode)
```

A Text BG Map always consists of 32x32 entries (256x256 pixels), 400h entries =
800h bytes. However, depending on the BG Size, one, two, or four of these Maps
may be used together, allowing to create backgrounds of 256x256, 512x256,
256x512, or 512x512 pixels, if so, the first map (SC0) is located at base+0,
the next map (SC1) at base+800h, and so on.



## Rotation/Scaling BG Screen (1 byte per entry)


In this mode, only 256 tiles can be used. There are no x/y-flip attributes, the
color depth is always 256 colors/1 palette.

```
  Bit   Expl.
  0-7   Tile Number     (0-255)
```

The dimensions of Rotation/Scaling BG Maps depend on the BG size. For size 0-3
that are: 16x16 tiles (128x128 pixels), 32x32 tiles (256x256 pixels), 64x64
tiles (512x512 pixels), or 128x128 tiles (1024x1024 pixels).


The size and VRAM base address of the separate BG maps for BG0-3 are set up by
BG0CNT-BG3CNT registers.




# LCD VRAM Bitmap BG Modes



In BG Modes 3-5 the background is defined in form of a bitmap (unlike as for
Tile/Map based BG modes). Bitmaps are implemented as BG2, with Rotation/Scaling
support. As bitmap modes are occupying 80KBytes of BG memory, only 16KBytes of
VRAM can be used for OBJ tiles.



## BG Mode 3 - 240x160 pixels, 32768 colors


Two bytes are associated to each pixel, directly defining one of the 32768
colors (without using palette data, and thus not supporting a 'transparent' BG
color).

```
  Bit   Expl.
  0-4   Red Intensity   (0-31)
  5-9   Green Intensity (0-31)
  10-14 Blue Intensity  (0-31)
  15    Not used in GBA Mode (in NDS Mode: Alpha=0=Transparent, Alpha=1=Normal)
```

The first 480 bytes define the topmost line, the next 480 the next line, and so
on. The background occupies 75 KBytes (06000000-06012BFF), most of the 80
Kbytes BG area, not allowing to redraw an invisible second frame in background,
so this mode is mostly recommended for still images only.



## BG Mode 4 - 240x160 pixels, 256 colors (out of 32768 colors)


One byte is associated to each pixel, selecting one of the 256 palette entries.
Color 0 (backdrop) is transparent, and OBJs may be displayed behind the bitmap.

The first 240 bytes define the topmost line, the next 240 the next line, and so
on. The background occupies 37.5 KBytes, allowing two frames to be used
(06000000-060095FF for Frame 0, and 0600A000-060135FF for Frame 1).



## BG Mode 5 - 160x128 pixels, 32768 colors


Colors are defined as for Mode 3 (see above), but horizontal and vertical size
are cut down to 160x128 pixels only - smaller than the physical dimensions of
the LCD screen.

The background occupies exactly 40 KBytes, so that BG VRAM may be split into
two frames (06000000-06009FFF for Frame 0, and 0600A000-06013FFF for Frame 1).


In BG modes 4,5, one Frame may be displayed (selected by DISPCNT Bit 4), the
other Frame is invisible and may be redrawn in background.




# LCD OBJ - Overview




## General


Objects (OBJs) are moveable sprites. Up to 128 OBJs (of any size, up to 64x64
dots each) can be displayed per screen, and under best circumstances up to 128
OBJs (of small 8x8 dots size) can be displayed per horizontal display line.



## Maximum Number of Sprites per Line


The total available OBJ rendering cycles per line are

```
  1210  (=304*4-6)   If "H-Blank Interval Free" bit in DISPCNT register is 0
  954   (=240*4-6)   If "H-Blank Interval Free" bit in DISPCNT register is 1
```

The required rendering cycles are (depending on horizontal OBJ size)

```
  Cycles per <n> Pixels    OBJ Type              OBJ Type Screen Pixel Range
  n*1 cycles               Normal OBJs           8..64 pixels
  10+n*2 cycles            Rotation/Scaling OBJs 8..64 pixels   (area clipped)
  10+n*2 cycles            Rotation/Scaling OBJs 16..128 pixels (double size)
```

Caution:

The maximum number of OBJs per line is also affected by undisplayed (offscreen)
OBJs which are having higher priority than displayed OBJs.

To avoid this, move displayed OBJs to the begin of OAM memory (ie. OBJ0 has
highest priority, OBJ127 lowest).

Otherwise (in case that the program logic expects OBJs at fixed positions in
OAM) at least take care to set the OBJ size of undisplayed OBJs to 8x8 with
Rotation/Scaling disabled (this reduces the overload).

Does the above also apply for VERTICALLY OFFSCREEN (or VERTICALLY not on
CURRENT LINE) sprites ?



## VRAM - Character Data


OBJs are always combined of one or more 8x8 pixel Tiles (much like BG Tiles in
BG Modes 0-2). However, OBJ Tiles are stored in a separate area in VRAM:
06010000-06017FFF (32 KBytes) in BG Mode 0-2, or 06014000-06017FFF (16 KBytes)
in BG Mode 3-5.

Depending on the size of the above area (16K or 32K), and on the OBJ color
depth (4bit or 8bit), 256-1024 8x8 dots OBJ Tiles can be defined.



## OAM - Object Attribute Memory


This memory area contains Attributes which specify position, size, color depth,
etc. appearance for each of the 128 OBJs. Additionally, it contains 32 OBJ
Rotation/Scaling Parameter groups. OAM is located at 07000000-070003FF (sized 1
KByte).




# LCD OBJ - OAM Attributes




## OBJ Attributes


There are 128 entries in OAM for each OBJ0-OBJ127. Each entry consists of 6
bytes (three 16bit Attributes). Attributes for OBJ0 are located at 07000000,
for OBJ1 at 07000008, OBJ2 at 07000010, and so on.


As you can see, there are blank spaces at 07000006, 0700000E, 07000016, etc. -
these 16bit values are used for OBJ Rotation/Scaling (as described in the next
chapter) - they are not directly related to the separate OBJs.



## OBJ Attribute 0 (R/W)


```
  Bit   Expl.
  0-7   Y-Coordinate           (0-255)
  8     Rotation/Scaling Flag  (0=Off, 1=On)
  When Rotation/Scaling used (Attribute 0, bit 8 set):
    9     Double-Size Flag     (0=Normal, 1=Double)
  When Rotation/Scaling not used (Attribute 0, bit 8 cleared):
    9     OBJ Disable          (0=Normal, 1=Not displayed)
  10-11 OBJ Mode  (0=Normal, 1=Semi-Transparent, 2=OBJ Window, 3=Prohibited)
  12    OBJ Mosaic             (0=Off, 1=On)
  13    Colors/Palettes        (0=16/16, 1=256/1)
  14-15 OBJ Shape              (0=Square,1=Horizontal,2=Vertical,3=Prohibited)
```

Caution: A very large OBJ (of 128 pixels vertically, ie. a 64 pixels OBJ in a
Double Size area) located at Y>128 will be treated as at Y>-128, the OBJ
is then displayed parts offscreen at the TOP of the display, it is then NOT
displayed at the bottom.



## OBJ Attribute 1 (R/W)


```
  Bit   Expl.
  0-8   X-Coordinate           (0-511)
  When Rotation/Scaling used (Attribute 0, bit 8 set):
    9-13  Rotation/Scaling Parameter Selection (0-31)
          (Selects one of the 32 Rotation/Scaling Parameters that
          can be defined in OAM, for details read next chapter.)
  When Rotation/Scaling not used (Attribute 0, bit 8 cleared):
    9-11  Not used
    12    Horizontal Flip      (0=Normal, 1=Mirrored)
    13    Vertical Flip        (0=Normal, 1=Mirrored)
  14-15 OBJ Size               (0..3, depends on OBJ Shape, see Attr 0)
          Size  Square   Horizontal  Vertical
          0     8x8      16x8        8x16
          1     16x16    32x8        8x32
          2     32x32    32x16       16x32
          3     64x64    64x32       32x64
```



## OBJ Attribute 2 (R/W)


```
  Bit   Expl.
  0-9   Character Name          (0-1023=Tile Number)
  10-11 Priority relative to BG (0-3; 0=Highest)
  12-15 Palette Number   (0-15) (Not used in 256 color/1 palette mode)
```



## Notes:




## OBJ Mode


The OBJ Mode may be Normal, Semi-Transparent, or OBJ Window.

Semi-Transparent means that the OBJ is used as 'Alpha Blending 1st Target'
(regardless of BLDCNT register, for details see chapter about Color Special
Effects).

OBJ Window means that the OBJ is not displayed, instead, dots with non-zero
color are used as mask for the OBJ Window, see DISPCNT and WINOUT for details.



## OBJ Tile Number


There are two situations which may divide the amount of available tiles by two
(by four if both situations apply):


1. When using the 256 Colors/1 Palette mode, only each second tile may be used,
the lower bit of the tile number should be zero (in 2-dimensional mapping mode,
the bit is completely ignored).


2. When using BG Mode 3-5 (Bitmap Modes), only tile numbers 512-1023 may be
used. That is because lower 16K of OBJ memory are used for BG. Attempts to use
tiles 0-511 are ignored (not displayed).



## Priority


In case that the 'Priority relative to BG' is the same than the priority of one
of the background layers, then the OBJ becomes higher priority and is displayed
on top of that BG layer.

Caution: Take care not to mess up BG Priority and OBJ priority. For example,
the following would cause garbage to be displayed:

```
  OBJ No. 0 with Priority relative to BG=1   ;hi OBJ prio, lo BG prio
  OBJ No. 1 with Priority relative to BG=0   ;lo OBJ prio, hi BG prio
```

That is, OBJ0 is always having priority above OBJ1-127, so assigning a lower BG
Priority to OBJ0 than for OBJ1-127 would be a bad idea.




# LCD OBJ - OAM Rotation/Scaling Parameters



As described in the previous chapter, there are blank spaces between each of
the 128 OBJ Attribute Fields in OAM memory. These 128 16bit gaps are used to
store OBJ Rotation/Scaling Parameters.



## Location of Rotation/Scaling Parameters in OAM


Four 16bit parameters (PA,PB,PC,PD) are required to define a complete group of
Rotation/Scaling data. These are spread across OAM as such:

```
  1st Group - PA=07000006, PB=0700000E, PC=07000016, PD=0700001E
  2nd Group - PA=07000026, PB=0700002E, PC=07000036, PD=0700003E
  etc.
```

By using all blank space (128 x 16bit), up to 32 of these groups (4 x 16bit
each) can be defined in OAM.



## OBJ Rotation/Scaling PA,PB,PC,PD Parameters (R/W)


Each OBJ that uses Rotation/Scaling may select between any of the above 32
parameter groups. For details, refer to the previous chapter about OBJ
Attributes.

The meaning of the separate PA,PB,PC,PD values is identical as for BG, for
details read the chapter about BG Rotation/Scaling.



## OBJ Reference Point & Rotation Center


The OBJ Reference Point is the upper left of the OBJ, ie. OBJ X/Y coordinates:
X+0, Y+0.

The OBJ Rotation Center is always (or should be usually?) in the middle of the
object, ie. for a 8x32 pixel OBJ, this would be at the OBJ X/Y coordinates:
X+4, and Y+16.



## OBJ Double-Size Bit (for OBJs that use Rotation/Scaling)


When Double-Size is zero: The sprite is rotated, and then display inside of the
normal-sized (not rotated) rectangular area - the edges of the rotated sprite
will become invisible if they reach outside of that area.

When Double-Size is set: The sprite is rotated, and then display inside of the
double-sized (not rotated) rectangular area - this ensures that the edges of
the rotated sprite remain visible even if they would reach outside of the
normal-sized area. (Except that, for example, rotating a 8x32 pixel sprite by
90 degrees would still cut off parts of the sprite as the double-size area
isn't large enough.)




# LCD OBJ - VRAM Character (Tile) Mapping



Each OBJ tile consists of 8x8 dots, however, bigger OBJs can be displayed by
combining several 8x8 tiles. The horizontal and vertical size for each OBJ may
be separately defined in OAM, possible H/V sizes are 8,16,32,64 dots - allowing
'square' OBJs to be used (such like 8x8, 16x16, etc) as well as 'rectangular'
OBJs (such like 8x32, 64x16, etc.)


When displaying an OBJ that contains of more than one 8x8 tile, one of the
following two mapping modes can be used. In either case, the tile number of the
upperleft tile must be specified in OAM memory.



## Two Dimensional Character Mapping (DISPCNT Bit 6 cleared)


This mapping mode assumes that the 1024 OBJ tiles are arranged as a matrix of
32x32 tiles / 256x256 pixels (In 256 color mode: 16x32 tiles / 128x256 pixels).
Ie. the upper row of this matrix contains tiles 00h-1Fh, the next row tiles
20h-3Fh, and so on.

For example, when displaying a 16x16 pixel OBJ, with tile number set to 04h;
The upper row of the OBJ will consist of tile 04h and 05h, the next row of 24h
and 25h. (In 256 color mode: 04h and 06h, 24h and 26h.)



## One Dimensional Character Mapping (DISPCNT Bit 6 set)


In this mode, tiles are mapped each after each other from 00h-3FFh.

Using the same example as above, the upper row of the OBJ will consist of tile
04h and 05h, the next row of tile 06h and 07h. (In 256 color mode: 04h and 06h,
08h and 0Ah.)




# LCD Color Palettes




## Color Palette RAM


BG and OBJ palettes are using separate memory regions:

```
  05000000-050001FF - BG Palette RAM (512 bytes, 256 colors)
  05000200-050003FF - OBJ Palette RAM (512 bytes, 256 colors)
```

Each BG and OBJ palette RAM may be either split into 16 palettes with 16 colors
each, or may be used as a single palette with 256 colors.

Note that some OBJs may access palette RAM in 16 color mode, while other OBJs
may use 256 color mode at the same time. Same for BG0-BG3 layers.



## Transparent Colors


Color 0 of all BG and OBJ palettes is transparent. Even though palettes are
described as 16 (256) color palettes, only 15 (255) colors are actually
visible.



## Backdrop Color


Color 0 of BG Palette 0 is used as backdrop color. This color is displayed if
an area of the screen is not covered by any non-transparent BG or OBJ dots.



## Color Definitions


Each color occupies two bytes (same as for 32768 color BG modes):

```
  Bit   Expl.
  0-4   Red Intensity   (0-31)
  5-9   Green Intensity (0-31)
  10-14 Blue Intensity  (0-31)
  15    Not used
```



## Intensities


Under normal circumstances (light source/viewing angle), the intensities 0-14
are practically all black, and only intensities 15-31 are resulting in visible
medium..bright colors.


Note: The intensity problem appears in the 8bit CGB "compatibility" mode
either. The original CGB display produced the opposite effect: Intensities 0-14
resulted in dark..medium colors, and intensities 15-31 resulted in bright
colors. Any "medium" colors of CGB games will appear invisible/black on GBA
hardware, and only very bright colors will be visible.




# LCD Dimensions and Timings




## Horizontal Dimensions


The drawing time for each dot is 4 CPU cycles.

```
  Visible     240 dots,  57.221 us,    960 cycles - 78% of h-time
  H-Blanking   68 dots,  16.212 us,    272 cycles - 22% of h-time
  Total       308 dots,  73.433 us,   1232 cycles - ca. 13.620 kHz
```

VRAM and Palette RAM may be accessed during H-Blanking. OAM can accessed only
if "H-Blank Interval Free" bit in DISPCNT register is set.



## Vertical Dimensions


```
  Visible (*) 160 lines, 11.749 ms, 197120 cycles - 70% of v-time
  V-Blanking   68 lines,  4.994 ms,  83776 cycles - 30% of v-time
  Total       228 lines, 16.743 ms, 280896 cycles - ca. 59.737 Hz
```

All VRAM, OAM, and Palette RAM may be accessed during V-Blanking.

Note that no H-Blank interrupts are generated within V-Blank period.



## System Clock


The system clock is 16.78MHz (16\*1024\*1024 Hz), one cycle is thus approx.
59.59ns.


(\*) Even though vertical screen size is 160 lines, the upper 8 lines are not
\<really> visible, these lines are covered by a shadow when holding the
GBA orientated towards a light source, the lines are effectively black - and
should not be used to display important information.



## Interlace


The LCD display is using some sort of interlace in which even scanlines are
dimmed in each second frame, and odd scanlines are dimmed in each other frame
(it does always render ALL lines in ALL frames, but half of them are dimmed).

The effect can be seen when displaying some horizontal lines in each second
frame, and hiding them in each other frame: the hardware will randomly show the
lines in dimmed or non-dimmed form (depending on whether the test was started
in an even or odd frame).

Unknown if it's possible to determine the even/off frame state by software (or
possibly to reset the hardware to this or that state by software).

Note: The NDS is applying some sort of frameskip to GBA games, about every 3
seconds there will by a missing (or maybe: inserted) frame, ie. a GBA game that
is updating the display in sync with GBA interlace will get offsync on NDS
consoles.
