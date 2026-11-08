# GBA Backwards Compatibility CGB Mode

> 本檔案整理自 [GBATEK](https://problemkaputt.de/gbatek.htm) 的「GBA Backwards Compatibility CGB Mode」章節。
> 來源採用 [mGBA GBATEK Markdown fork](https://github.com/mgba-emu/gbatek) 的 Markdown 轉存，保留原文的暫存器、位元欄位、程式碼與數值表示法。

# GBA Backwards Compatibility CGB Mode




## Related GBA Registers


```
  4000000h.bit14 (DISPCNT) - enable BG2 aka CGB screen
  4000000h.bit3  (DISPCNT) - prepare switch to CGB mode
  4000301h       (HALTCNT) - apply switch to CGB mode (and stop ARM forever?)
  4000204h.bit15 (WAITCNT) - detect GBA/CGB cart type (and supply voltage)
  4000800h.bit3  (UNDOC)   - disable CGB bootrom
  5000000h.bit0-15         - Palette Backdrop (screen border color)
  BG2X/BG2Y registers      - CGB screen position within GBA screen
  BLDCNT/BLDY              - can be used to tweak better CGB brightness
  sound BIAS and vol?      - sound
```



## Normal CGB Boot


The GBA does always boot in GBA mode, but the GBA BIOS does almost immediately
switch to CGB mode when detecting gameboy cart via Port 4000204h; that
detection relies on a mechanical switch in the cartridge slot, which does also
toggle the system voltage from 3.3V (GBA) to 5V (CGB).



## GBA, GBA SP, and GBA micro


CGB mode is supported on GBA and GBA SP. The GBA micro does lack the cartridge
switch (and thus cannot detect 8bit carts, and cannot switch the system
voltage, nethertheless it does contain semi-functional CGB hardware: it can be
manually switched to CGB mode and execute the CGB intro).



## CGB Bootrom Disable


The CGB Bootrom can be disabled via 4000800h, that allows to skip the CGB intro
(but requires booting custom GBA code with GBA intro and then hot plugging a
gameboy cartridge, which must contain a valid entrypoint at address 0000h, and
which must select CGB or DMG mode and initialize the DMG color scheme).

The Bootrom Disable works same as ROMDIS pin on real CGBs (and also includes
unlocking port FF60h, FF61h, FF63h, see no$gmb/pandocs for details).

Unknown if it's possible to keep the ARM CPU running after entering CGB mode
(so one could re-disable ROMDIS some cycles after booting).



## Palette Issues


The GBA vs CGB palettes have different intensities ramps (CGB colors with
medium brightness will appear black on GBA), that's making CGB games mostly
unplayable on GBA (and only monochrome DMG games are actually working on GBA).
As a workaroud, one could tweak BLDCNT/BLDY to increase the brightness.



## GBA Memory Usage in CGB Mode


```
  2000000h-200FFFFh.bit0-15  unused                    ;\
  2010000h-2011FFEh.bit0-7   mapped to C000h-CFFFh     ;
  2012000h-2013FFEh.bit0-7   mapped to 1:D000h-DFFFh   ; GBA Main RAM halfwords
  2014000h-2015FFEh.bit0-7   mapped to 2:D000h-DFFFh   ; used as 32K CGB WRAM
  2016000h-2017FFEh.bit0-7   mapped to 3:D000h-DFFFh   ;
  2018000h-2019FFEh.bit0-7   mapped to 4:D000h-DFFFh   ;
  201A000h-201BFFEh.bit0-7   mapped to 5:D000h-DFFFh   ;
  201C000h-201DFFEh.bit0-7   mapped to 6:D000h-DFFFh   ;
  201E000h-201FFFEh.bit0-7   mapped to 7:D000h-DFFFh   ;
  2010001h-201FFFFh.bit8-15  unused (halfword.msbs)    ;
  2020000h-203FFFFh.bit0-15  unused                    ;/
  3000000h-3003FFFh.bit0-7   mapped to 0:8000h-8FFFh   ;\
  3000000h-3003FFFh.bit8-15  mapped to 0:9000h-9FFFh   ; GBA Fast WRAM words
  3000000h-3003FFFh.bit16-23 mapped to 1:8000h-8FFFh   ; used as 16K CGB VRAM
  3000000h-3003FFFh.bit24-31 mapped to 1:9000h-9FFFh   ;
  3004000h-3007FFFh.bit0-31  unused                    ;/
```
