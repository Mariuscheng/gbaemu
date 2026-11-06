# External Connectors

> 本檔案整理自 [GBATEK](https://problemkaputt.de/gbatek.htm) 的「External Connectors」章節。
> 來源採用 [mGBA GBATEK Markdown fork](https://github.com/mgba-emu/gbatek) 的 Markdown 轉存，保留原文的暫存器、位元欄位、程式碼與數值表示法。

# External Connectors




## External Connectors


- [AUX GBA Game Pak Bus](#auxgbagamepakbus)
- [AUX DS Game Card Slot](#auxdsgamecardslot)
- [AUX Link Port](#auxlinkport)
- [AUX Sound/Headphone Socket and Battery/Power Supply](#auxsoundheadphonesocketandbatterypowersupply)
- [AUX DSi SD/MMC Pin-Outs](#auxdsisdmmcpinouts)


## Getting access to Internal Pins


- [AUX Opening the GBA](#auxopeningthegba)
- [AUX Mainboard](#auxmainboard)
- [AUX DSi Component Lists](#auxdsicomponentlists)
- [AUX DSi Signals/Testpoints](#auxdsisignalstestpoints)
- [AUX DSi Internal Connectors](#auxdsiinternalconnectors)
- [AUX DSi Chipset Pinouts](#auxdsichipsetpinouts)


## More Internal Stuff


- [Pinouts - CPU - Signal Summary](#pinoutscpusignalsummary)
- [Pinouts - CPU - Pinouts](#pinoutscpupinouts)
- [Pinouts - Audio Amplifiers](#pinoutsaudioamplifiers)
- [Pinouts - LCD Cables](#pinoutslcdcables)
- [Pinouts - Power Switches, DC/DC Converters, Reset Generators](#pinoutspowerswitchesdcdcconvertersresetgenerators)
- [Pinouts - Wifi](#pinoutswifi)
- [Pinouts - Various](#pinoutsvarious)


## Xboo Multiboot Cable


- [AUX Xboo PC-to-GBA Multiboot Cable](#auxxboopctogbamultibootcable)
- [AUX Xboo Flashcard Upload](#auxxbooflashcardupload)
- [AUX Xboo Burst Boot Backdoor](#auxxbooburstbootbackdoor)
- [DS Xboo](ds.html#dsxboo)



# AUX GBA Game Pak Bus




## Game Pak Bus - 32pin cartridge slot


The cartridge bus may be used for both CGB and GBA game paks. In GBA mode, it
is used as follows:

```
 Pin    Name    Dir  Expl.
 1      VDD     O    Power Supply 3.3V DC
 2      PHI     O    System Clock (selectable none, 4.19MHz, 8.38MHz, 16.78MHz)
 3      /WR     O    Write Select    ;\latched address to be incremented on
 4      /RD     O    Read Select     ;/rising edges of /RD or /WR signals
 5      /CS     O    ROM Chip Select ;-A0..A15 to be latched on falling edge
 6-21   AD0-15  I/O  lower 16bit Address    and/or  16bit ROM-data (see below)
 22-29  A16-23  I/O  upper 8bit ROM-Address   or    8bit SRAM-data (see below)
 30     /CS2    O    SRAM Chip Select
 31     /REQ    I    Interrupt request (/IREQ) or DMA request (/DREQ)
 32     GND     O    Ground 0V
```

When accessing game pak SRAM, a 16bit address is output through AD0-AD15, then
8bit of data are transferred through A16-A23.

When accessing game pak ROM, a 24bit address is output through AD0-AD15 and
A16-A23, then 16bit of data are transferred through AD0-AD15.

The 24bit address is formed from the actual 25bit memory address (byte-steps),
divided by two (halfword-steps).

Pin Pitch is 1.5mm.



## 8bit-Gamepak-Switch (GBA, GBA SP only) (not DS)


A small switch is located inside of the cartridge slot, the switch is pushed
down when an 8bit cartridge is inserted, it is released when a GBA cartridge is
inserted (or if no cartridge is inserted).

The switch mechanically controls whether VDD3 or VDD5 are output at VDD35; ie.
in GBA mode 3V power supply/signals are used for the cartridge slot and link
port, while in 8bit mode 5V are used.

The switch additionally drags IN35 to 3V when an 8bit cart is inserted, the
current state of IN35 can be determined in GBA mode via Port 4000204h
(WAITCNT), if the switch is pushed, then CGB mode can be activated via Port
4000000h (DISPCNT.3), this bit can be set ONLY by opcodes in BIOS region (eg.
via CpuSet SWI function).

In 8bit mode, the cartridge bus works much like for GBA SRAM, however, the 8bit
/CS signal is expected at Pin 5, while GBA SRAM /CS2 at Pin 30 is interpreted
as /RESET signal by the 8bit MBC chip (if any). In practice, this appears to
result in 00h being received as data when attempting to read-out 8bit
cartridges from inside of GBA mode.




# AUX DS Game Card Slot



```
  Pin    Dir  Name  Connection in cartridge
  1   >  -    GND   (ROM all unused Pins, EEPROM Pin 4 = VSS)
  2      Out  CLK   (4MB/s, ROM Pin 5, EEPROM Pin 6 = CLK)
  3   N  -    ?     (ROM Pin 17) (Seems to be not connected in console)
  4   i  Out  /CS1  (ROM Pin 44) ROM Chipselect
  5   n  Out  /RES  (ROM Pin 42) Reset, switches ROM to unencrypted mode
  6   t  Out  /CS2  (EEPROM Pin 1) EEPROM Chipselect
  7   e  In   IRQ   (GND)
  8   n  -    3.3V  (ROM Pins 2, 23, EEPROM Pins 3,7,8 = /W,/HOLD,VCC)
  9   d  I/O  D0    (ROM Pin 18)
  10  o  I/O  D1    (ROM Pin 19)
  11     I/O  D2    (ROM Pin 20)
  12  C  I/O  D3    (ROM Pin 21)
  13  0  I/O  D4    (ROM Pin 24)
  14  1  I/O  D5    (ROM Pin 25)
  15  -  I/O  D6    (ROM Pin 26, EEPROM Pin 2 = Q = Data EEPROM to NDS)
  16  0  I/O  D7    (ROM Pin 27, EEPROM Pin 5 = D = Data NDS to EEPROM)
  17  1  -    GND   (ROM all unused Pins, EEPROM Pin 4 = VSS)
```


Chipselect High-to-Low transitions are invoking commands, which are transmitted
through data lines during next following eight CLK pulses, after the command
transmission, further CLK pulses are used to transfer data, the data transfer
ends at chipselect Low-to-High transition.

Data should be stable during CLK=LOW period throughout CLK rising edge.

Note: Supply Pins (1,8,17) are slightly longer than other pins. Pin pitch is
1.5mm.


The DS does also have a 32pin cartridge slot, that slot is used to run GBA
carts in GBA mode, it can be also used as expansion port in DS mode.




# AUX Link Port




## Serial Link Port Pin-Out (GBA:"EXT" - GBA SP:"EXT.1")


```
  Pin  Name  Cable
  1    VDD35 N/A       GBA Socket     GBA Plug   Old "8bit" Plug
  2    SO    Red       ___________    _________    ___________
  3    SI    Orange   |  2  4  6  |  / 2  4  6 \  |  2  4  6  |
  4    SD    Brown     \_1_ 3 _5_/   \_1_ 3 _5_/   \_1__3__5_/
  5    SC    Green         '-'           '-'
  6    GND   Blue      Socket Outside View / Plug Inside View
  Shield     Shield
```

Note: The pin numbers and names are printed on the GBA mainboard, colors as
used in Nintendo's AGB-005 and older 8bit cables.



## Serial Link/Power Supply Port (GBA-Micro: "EXT.")


```
  1  In  DC (Supply 5.2VDC)  ___________________
  2  Out V3 (SIO 3.3VDC)    |  1 2 3 4 5 6 7 8  |
  3  I/O SO (SIO RCNT.3)    | ================= |
  4  I/O SI (SIO RCNT.2)     \_________________/
  5  I/O SD (SIO RCNT.1)
  6  I/O SC (SIO RCNT.0)
  7  OUT DG (SIO GROUND)
  8  In  DG (Supply GROUND)
  -  -   -  (Shield not connected)
```



## Cable Diagrams (Left: GBA Cable, Right: 8bit Gameboy Cable)


```
  Big Plug  Middle Socket  Small Plug    Plug 1         Plug 2
   SI _________________     ____ SI       SI ______  ______SI
   SO ____________SO   |__ | ___ SO       SO ______><______SO
   GND____________GND______|____GND       GND_____________GND
   SD ____________SD____________ SD       SD               SD
   SC ____________SC____________ SC       SC _____________ SC
   Shield_______Shield_______Shield       Shield_______Shield
```



## Normal Connection


Just connect the plugs to the two GBAs and leave the Middle Socket
disconnected, in this mode both GBAs may behave as master or slave, regardless
of whether using big or small plugs.

The GBA is (NOT ???) able to communicate in Normal mode with MultiPlay cables
which do not have crossed SI/SO lines.



## Multi-Play Connection


Connect two GBAs as normal, for each further GBAs connect an additional cable
to the Middle socket of the first (or further) cable(s), up to four GBAs may be
connected by using up to three cables.

The GBA which is connected to a Small Plug is master, the slaves are all
connected to Large Plugs. (Only small plugs fit into the Middle Socket, so it's
not possible to mess up something here).



## Multi-Boot Connection


MultiBoot (SingleGamepak) is typically using Multi-Play communication, in this
case it is important that the Small plug is connected to the master/sender (ie.
to the GBA that contains the cartridge).



## Non-GBA Mode Connection


First of all, it is not possible to link between 32bit GBA games and 8bit
games, parts because of different cable protocol, and parts because of
different signal voltages.

However, when a 8bit cartridge is inserted (the GBA is switched into 8bit
compatibility mode) it may be connected to other 8bit games (monochrome
gameboys, CGBs, or to other GBAs which are in 8bit mode also, but not to GBAs
in 32bit mode).

When using 8bit link mode, an 8bit link cable must be used. The GBA link cables
won't work, see below modification though.



## Using a GBA 32bit cable for 8bit communication


Open the middle socket, and disconnect Small Plugs SI from GND, and connect SI
to Large Plugs SO instead. You may also want to install a switch that allows to
switch between SO and GND, the GND signal should be required for MultiPlay
communication only though.

Also, cut off the plastic ledge from the plugs so that they fit into 8bit
gameboy sockets.



## Using a GBA 8bit cable for 32bit communication


The cable should theoretically work as is, as the grounded SI would be required
for MultiPlay communication only. However, software that uses SD for
Slave-Ready detection won't work unless when adding a SD-to-SD connection (the
8bit plugs probably do not even contain SD pins though).




# AUX Sound/Headphone Socket and Battery/Power Supply




## GBA, GBA-Micro, NDS, and NDS-Lite: Stereo Sound Connector (3.5mm, female)


```
  Tip     Audio Left         ___ ___ _____.-----------.
  Middle  Audio Right       (___|___|_____|           |
  Base    Ground              L   R   GND '-----------'
```

The NDS socket doesn't fully match regular 3.5mm plugs, one needs to cut-off a
portion of the DS case to be able to fully insert the plug, which still
requires a lot of pressure, furthermore, when fully inserted, left/right become
shortcut to mono, so one needs to pull-back the plug a bit to gain stereo
output.



## GBA SP and NDS - Power/Headphone Socket (EXT.2)


```
  Pin SP   NDS  Expl.
  1   P31  SL   Audio LOUT                          _____________
  2   P32  VIN  Supply Input (DC 5.2V)           SW| 5   ___   1 |SL
  3   P33  SR   Audio ROUT                         | ----   ---- |
  4   P34  SG   Audio GND (via 100uF to GND)       |_6__4   3__2_|
  5   P35  SW   Audio Speaker Disable (GND=Dis)    GND SG\_/SR VIN
  6        GND  Supply GND
  Shield        GND
```

External power input is used to charge the built-in battery, it cannot be used
to run the SP without that battery.



## NDS-Lite - Power Socket


```
  Pin  Expl.                                          __________
  1    Supply Input (DC 5.2V)                        /  ======  \
  2    Supply GND                                GND |___2__1___| VIN
```



## GBA-Micro - Power Socket


Uses an 8pin socket (which combines SIO and Power), for pin-outs, see

- [AUX Link Port](#auxlinkport)


## External Power Supply


GBA: DC 3.3V (no separate power socket, requires 2xAA-battery-shaped adapter)

GBA-SP/NDS: DC 5.2V (or DC 5V) (special connector on power/headphone socket)

NDS-Lite: DC 5.2V (or DC 5V) (another special connector on power socket)



## Internal Battery Supply


GBA: 2xAA (3V)

GBA-SP: Li-ion 3.7V, 600mAh (built-in, recharge-able)

GBA-Micro: Li-ion 3.8V, 460mAh (built-in, recharge-able)

NDS: Li-ion 3.7V, 850mAh (built-in, recharge-able)

NDS-Lite: Li-ion 3.7V, 1000mAh (built-in, recharge-able)



## Using PC +5V DC as Power Supply


Developers whom are using a PC for GBA programming will probably want to use
the PC power supply (gained from disk drive power supply cable) for the GBA as
well rather than dealing with batteries or external power supplies.

GBA: To lower the voltage to approximately 3 Volts use two diodes, type 1N 4004
or similar, the ring printed onto the diodes points towards the GBA side,
connected as such:

```
  PC +5V (red)   --------|>|---|>|--------  GBA BT+
  PC GND (black) -------------------------  GBA BT-
```

GBA SP, GBA Micro, NDS, and NDS-Lite: Works directly at +5V connected to EXT.2
socket (not to the internal battery pins), without any diodes.




# AUX DSi SD/MMC Pin-Outs




## SD/MMC Transfer Modes


```
  Transfer Modes        SPI-Mode    1-bit-Bus  4-bit-Bus   SDIO
  MMC Cards             Optional    Yes        MMCplus     No
  SD Cards              Yes         Yes        Optional??  Optional
```

Note: SDIO is an extension to the SD protocol, allowing to access other
non-memory-card hardware (such like cameras or network adaptors) via SD
connectors.

Note: Original MMC cards don't support 4-bit bus, but there are revisions like
MMCplus and MMCmobile (with extra pin rows) which do support 4-bit and 8bit
bus.



## SD/MMC Pin-Outs


```
  MMC  MMCplus SD  miniSD microSD SPI-Mode    1-bit-Bus   4-bit/8bit-Bus
  1    1       1   1      2       /CS         CardDetect  Data3
  2    2       2   2      3       DataIn      CMD/REPLY   CMD/REPLY
  3    3       3   3      --      GND         GND         GND
  4    4       4   4      4       VDD         VDD         VDD
  5    5       5   5      5       CLK         CLK         CLK
  6    6       6   6      6       GND         GND         GND
  7    7       7   7      7       DataOut     Data        Data0
  --   8       8   8      8       /IRQ (SDIO) /IRQ (SDIO) Data1 or /IRQ (SDIO)
  --   9       9   9      1       NC          NC          Data2
  --   10      --  --     --      NC          NC          Data4  ;\
  --   11      --  --     --      NC          NC          Data5  ; MMCplus
  --   12      --  --     --      NC          NC          Data6  ; 8bit
  --   13      --  --     --      NC          NC          Data7  ;/
  --   --      --  10     --      Reserved    Reserved    Reserved
  --   --      --  11     --      Reserved    Reserved    Reserved
```

Moreover, the card sockets (not the cards themselves) are usually containing a
Card Detect switch, and, for SD card sockets, also a write protect switch:

```
  --   --      CD  CD     CD      Card Detect (senses if card is inserted)
  --   ---     WP  --     --      Write Protect (senses position of LOCK tab)
```

Note that the LOCK tab on SD cards is just a small piece of plastic without any
electronics attached to it, the actual switch/sensor is located in the SD card
socket (ie. the LOCK works much like the write-protect tabs on audio tapes,
video tapes, and floppy discs).

Card detect can be an actual switch (however, some sockets are simply having
dual contacts for Pin 3 (GND), one being GND, and the other becoming GNDed when
a cartridge is inserted).



## SD/MMC Card Shapes


```
     ______________________________
    /    __ __ __ __ __ __ __      |
   /    |  |  |  |  |  |  |  |     |
  |     | 1| 2| 3| 4| 5| 6| 7|     |
  | MMC |__|__|__|__|__|__|__|     |
  |    ______________________________
  |   /    __ __ __ __ __ __ __ _    |
  |  /  __|  |  |  |  |  |  |  | |   |
  | |  |  | 1| 2| 3| 4| 5| 6| 7|8|   | MMCplus:
  | |  | 9|__|__|__|__|__|__|__| |   | pinout is same as 9pin SD cards,
  | |  |_ |_ __ __       __ __ | |   | with extra DAT4-7 on pin10-13
  | |    |  | 1| 1|     | 1| 1|  |   |
  | |MMC | 9| 0| 1|     | 2| 3| 8|   |
  | |plus|__|__|__|     |__|__|__|   |
  | |    ______________________________
  | |   /    __ __ __ __ __ __ __ _    |
  | |  /  __|  |  |  |  |  |  |  | |   |
  | | |  |  | 1| 2| 3| 4| 5| 6| 7|8|   |
  | | |  | 9|__|__|__|__|__|__|__|_|   |
  | | '. |__| SD                      .'      SD Write Protect Tab
  | |  |  _________________________   |   <-- Unlock position
  | | .' |  _ _ _ _ _ _ _ _ _ _ _  |  |#  <-- LOCK position
  | | |  | | | | | |1|1| | | | | | |  '.
  | | |  | |9|1|2|3|0|1|4|5|6|7|8| |   |
  |_| |  | |_|_|_|_|_|_|_|_|_|_|_| |   |
    | |  |   miniSD                 \  |
    | |  |     _________________     | |
    | |  |    | _ _ _ _ _ _ _ _ |    | |
    | |  |    || | | | | | | | ||    | |
    |_|  |    ||1|2|3|4|5|6|7|8||    | |
      |  |    ||_|_|_|_|_|_|_|_||    | |
      |  |   /                  |    | |
      |  |  |_  microSD         |    | |
      |  |    |                 |    | |
      |  |   /                  |    | |
      |  |  |                   |    | |
      |  |  |                   |    | |
      |  |_ |                   | ___| |
      |____ |___________________| _____|
```



## SD/MMC Signals for on-board eMMC chip on DSi Mainboard "C/TWL-CPU-01"


Below are the required eMMC signals. Low-end hardware may get away with using
Data0 as single data line (eg. small microprocessors with few I/O pins), but
higher quality hardware should support 4bit data mode (eg. off-the-shelve SD
card interfaces may insist on all four data lines being connected). Data3 (aka
CardDetect) might be also needed even in 1bit data mode.

```
                         _______ CLK (SPI: CLK)    _______ Data3 (SPI: /CS)
                        |                         | ______ Data0 (SPI: DataOut)
                 <#>  <#>  <#>                    || _____ Data1
                EM14  R113 C130                   ||| ____ Data2
        .------------------------.                ||||
        |                        |          <#>  <####> #  #
        |                        |     U5   C57   RA4  C54 C55
        |  Shielding-plate       '---.  o .------------------.
        |                            |    |o                 |
        |                            |    |                  |
        |                            |    |  Samsung     834 |
        |                            |    |  KMAPF0000M-S998 |
        |  CPU              RAM      |    |                  |
        |                            |    |                  |
        |                            |    '------------------'
        '----------------------------'     R94 R54  C50 C51
             |                             <#> <#>  <#> <#>
             |                               |
             |___ shield = GND               |___ CMD/REPLY (SPI: DataIn)
```

For other DSi mainboards, see:

- [http://www.dsibrew.org/wiki/Hardware](http://www.dsibrew.org/wiki/Hardware)

The KMAPF0000M chip does probably NOT support SPI mode, and it does probably
support only MMC protocol (not SD protocol). That, assuming that the chip does
have similar capabilities as in KMCEN0000M datasheet (there's no KMAPF0000M
datasheet online).



## SD/MMC Signals and 3DS Hardmodding


Pictures with eMMC solder pads for 3DS mainboards boards can be found at:

- [https://www.3dbrew.org/wiki/Hardware](https://www.3dbrew.org/wiki/Hardware)

However, hardmodding is much more difficult for 3DS as than for DSi. Three
3DS-specific problems:


## CLK resistor

  - The 3DS tends to hold CLK low, and there is no resistor installed between
  - 3DS CPU and eMMC chip, so the card reader may be unable to pull CLK high.
  - As workaround, install a resistor in the CLK line (the mainboard has square
  - solder pads just for that purpose) (330..660 ohms have worked for me, I am
  - currently using 470 ohms; smaller resistors like 0..120 ohm won't work with
  - the card reader, and much larger resistors won't work with the 3DS itself).

## Incompatible Card readers

  - Newer 3DS/New3DS models seem to contain eMMC chips that are incompatible with
  - older card readers, maybe because their firmware/driver treats the CSD
  - version number as unknown, despite of the eMMC chip being nothing special.
  - As workaround, try to use some newer card readers, or use a DSi console as
  - card reader (ie. write you software that can happily ignore CSD version).

## Mechanical problems

  - Most solder points are on the wrong PCB side (unlike as on DSi, you will
  - need to remove the 3DS mainboard). Whereas, the connector for the top screen
  - backlight is rated to survive max 10 mating cycles (mine died after 5-7).
  - Part of the problem was that I wasn't aware of the other problems mentioned
  - above (so I had removed the mainboard several times to check my soldering),
  - and, the connector is 'underneath' of the PCB, making it difficult to insert
  - the cable straight and smoothly, causing pins in the connector may get bent,
  - making it impossible to insert the ribbon cable (maybe it will help if you
  - take time, and don't impatiently try to push the cable into the socket).



## Soldering Notes


Connect CLK/CMD to the pins on right side of R113/R94 (as shown in the
drawing). Connect Data3/0/1/2 to the LOWER pins of RA4 (unlike as shown in the
drawing, ie. NOT to the upper pins), or alternately, connect them to the four
vias below of RA4. Connect GND somewhere to shielding plate, for example.

My own setup is: A 8pin ribbon cable soldered to a spare SD-to-SDmicro adapter
(used as connector for SD/MMC slots), the ribbon cable is wired to a small
circuit board, which is soldered to the shielding of the DSi's game cartridge
slot (just for mechanical stability). Next, some fragile wires are forwarded
from the circuit board to the actual mainboard pins.



## Software Notes


Remove the DSi wifiboard (not absolutely required, but doing so will hang the
DSi before accessing the eMMC, which ensures that the eMMC won't be accessed
simultaneously by the DSi and PC). Switch on the DSi. Connect it to SD/MMC card
reader. Under Windows, the eMMC should show up as MMC-storagedevice in Windows
Explorer (alongsides with your HDD drives), due to the encryption it isn't
possible to access the filesystem or logical partitions of the chip. However,
the physical sectors can be accessed.

For example, using HxD hex editor: Click Extras, Open Disk, and select the MMC
(in HxD it shows up under Physical Discs: as Removeable Disk). Click Edit,
Select All, Copy. Click File, New. Then Edit, Paste. And finally File, Save As
for saving an image of the whole 240MByte FLASH chip.

I've tried accessing the eMMC on two PCs, one worked, the other didn't:

```
  Win98 with External Card reader: Windows didn't recognize the MMC chip
  Win7  with External Card reader: Okay (recognized as "unformatted" disk)
  Win7  with Internal Card reader: Okay (recognized as "unformatted" disk)
```

For testing the Operating System/Card Reader side: Connect a normal SD card to
the card reader. If HxD is showing it as both Logical Disc and Physical Disc,
then you are fine. If it shows up as Logical Disc only, then your setup won't
work for accessing the eMMC chip.




# AUX Opening the GBA



Since Nintendo uses special screws with Y-shaped heads to seal the GBA (as well
as older 8bit gameboys), it's always a bit difficult to loosen these screws.



## Using Screwdrivers


One possible method is to use a small flat screwdriver, which might work, even
though it'll most likely damage the screwdriver.

Reportedly, special Y-shaped screwdrivers for gameboys are available for sale
somewhere (probably not at your local dealer, but you might find some in the
internet or elsewhere).



## Destroying the Screws


A more violent method is to take an electric drill, and drill-off the screw
heads, this might also slightly damage the GBA plastic chase, also take care
that the metal spoons from the destroyed screws don't produce shortcuts on the
GBA mainboard.



## Using a selfmade Screwdriver


A possible method is to take a larger screw (with a normal I-shaped, or
X-shaped head), and to cut the screw-tip into Y-shape, you'll then end up with
an "adapter" which can be placed in the middle between a normal screwdriver and
gameboy screws.

Preferably, first cut the screw-tip into a shape like a "sharp three sided
pyramid", next cut notches into each side. Access to a grinding-machine will be
a great benefit, but you might get it working by using a normal metal-file as
well.



## Opening the GBA Micro


- open the case with appropriate screwdriver or drilling machine or whatever

- remove the plastic front-plate (there are two snap-ins inside at ONE side)

- remove the mainboard and screen and plastic skeleton from the metal case

- remove the start/select daughter-board from the plastic skeleton

- remove the plastic skeleton (move the screen through the skeleton)

- remove the screen (lift lcd socket front-side, backlight socket rear-side)



## Opening the NDS-Lite


- open the case with appropriate screwdriver or drilling machine or whatever

- remove the RFU unit, and the 4-pin touch-screen cable (under the RFU unit)

- remove the mainboard together with the lower screen

- remove the upper/lower screen cables (on the rear-side of the mainboard)




# AUX Mainboard



Other possibly useful signals on the mainboard...



## FIQ Signal


The FIQ (Fast Interrupt) signal (labeled FIQ on the mainboard) could be used as
external interrupt (or debugging break) signal.

Caution: By default, the FIQ input is directly shortcut to VDD35 (+3V or +5V
power supply voltage), this can be healed by scratching off the CL1 connection
located close to the FIQ pin (FIQ still appears to have an internal pull-up, so
that an external resistor is not required).

The GBA BIOS rejects FIQs if using normal ROM cartridge headers (or when no
cartridge is inserted). When using a FIQ-compatible ROM header, Fast Interrupts
can be then requested by pulling FIQ to ground, either by a push button, or by
remote controlled signals.



## RESET Signal


The RESET signal (found on the mainboard) could be used to reset the GBA by
pulling the signal to ground for a few microseconds (or longer). The signal can
be directly used (it is not shortcut to VDD35, unlike FIQ).

Note: A reset always launches Nintendo's time-consuming and annoying boot/logo
procedure, so that it'd be recommend to avoid this "feature" when possible.



## Joypad Signals


The 10 direction/button signals are each directly shortcut to ground when
pressed, and pulled up high otherwise (unlike 8bit gameboys which used a 2x4
keyboard matrix), it'd be thus easy to connect a remote keyboard, keypad,
joypad, or read-only 12bit parallel port.




# AUX DSi Component Lists




## DSi Mainboard "C/TWL-CPU-01" Components


```
  U1 352pin   CPU TWL       (under shielding plate)                    ;\under
  U2   ?pin   RAM 8Mx16, Fujitsu MB82DBS08164D-70L, NEC uPD46128512AF1 ;/shield
  U3  56pin   "TexasIns 72071B0" or "Mitsumi 3317A" (Powerman) (right of NAND)
  U4  48pin   "AIC3000D, TI 89K, EXDK G4" (PAIC3 codec? above headphone socket)
  U5   ?pin   Samsung KMAPF0000M-S998 (eMMC, 256Mbyte NAND FLASH)
  U6  36pin   "BPTWL, K007K, 0902KM00D" (small/square, left of cartridge slot)
  U7   8pin   "AOK, S8BXS" (ISL95810, I2C potentiometer)         ;\on PCB
  U8   8pin   "7BDS" (PCA9306, I2C voltage translator)           ;/backside
  U9  12pin   "199A, 01IU" (Seiko S-35199A01) (RTC) ;under shielding plate (A)
  U10  4pin   "6800" or "688F" Hinge Magnet Sensor (PCB backside, near A/B/X/Y)
  U11 10pin   ",\\ 908, 335A" or "2005D, 8350" (right of cartridge slot)
  U12  5pin   "L8NX" or "C7JHN" (upper-right of PCB back-side) ;text layer (B)
  U13  5pin   Backlight 1, "U01" or "KER"  ;\lower-right board edge
  U14  5pin   Backlight 2, "U01" or "KER"  ;/see text-layer (B)
  U15  4pin   VIN to EXB+ control via Q1, ",\\ T34" (near external power input)
  U16     -   N/A
  U17  6pin   Headphone Mute, "VY" or "Z198" (in lower-right, on PCB backside)
  U18  6pin   Mic Bias, "YJ" (above headphone socket, not always installed)
  U19  5pin   "E30H6" or "L2SX" (at lower right of cartridge slot)
  U20  3pin   Whatever, DSi XL only (maybe magnet Sensor instead of U10?)
  Q1   6pin   external power supply related (VIN to EXTB+) (controlled by U15)
  Q2    pin   N/A ?
  Q3   6pin   ... above battery plug
  Q4   3pin   Headphone MUTE for SR  ;\old TWL-CPU-01 mainboard only
  Q5   3pin   Headphone MUTE for SL  ;/(replaced by Q17/Q18 on newer boards)
  Q6   6pin   MC1_VDD power ON (supply)
  Q7   3pin   MC1_VDD power OFF (pulldown)
  Q8    pin   N/A ?
  Q9    pin   N/A ?
  Q10   pin   N/A ?
  Q11  3pin   BLUE (LED)   ;\LEDs (note: the other LEDs, ORANGE
  Q12  3pin   YELLOW (LED) ;      and YELLOW, are driven directly)
  Q13  3pin   CAM_LED      ;/
  Q14  3pin   not installed (above powerman chip)
  Q15  3pin   not installed (above powerman chip)
  Q16  3pin   VDD-5 related, near DPAD socket (P15)
  Q17  6pin   Headphone MUTE for ..?  ;\new TWL-CPU-10 mainboard only
  Q18  6pin   Headphone MUTE for ..?  ;/(formerly Q4/Q5 on older boards)
  X1   4pin   16.756  (rectangular oscillator)        ;\under shielding plate
  X2   4pin   CB837 or CB822 (long slim osc) for RTC? ;/text layer: see (A)
  F1   2pin   Fuse for external power input
  SW1  2pin   Button A (right)
  SW2  2pin   Button B (lower)
  SW3  2pin   Button X (upper)
  SW4  2pin   Button Y (left)
  SW5  2pin   Button Select (lower)
  SW6  2pin   Button Start  (upper)
  P1  19pin   NDS/DSi cartridge slot (17pin slot + 2pin switch at right side)
  P2      -   N/A
  P3      -   N/A
  P4   8pin   External microphone/headphone combo socket
  P5  50pin   Wifi-Daughterboard
  P6      -   N/A
  P7  47pin   To UPPER lcd screen (video+backlight+speakers) (on PCB backside)
  P8  37pin   To LOWER lcd screen (video signals)
  P9  25pin   To UPPER lcd screen (signals for both cameras, and camera led)
  P10  4pin   To LOWER lcd screen (touchpad X-,Y-,X+,Y+)
  P11  2pin   External Power Supply input (4.6V DC IN)
  P12     -   N/A
  P13     -   N/A
  P14     -   N/A
  P15 15pin   To battery/DPAD/PowerButton board (and onwards to 3xLEDs)
  P16 26pin   To bottom cover (SD Slot and L/R/VOL+/- buttons)
  P17  2pin   Battery cable (lower-right) ;see text-layer (B)
  P18  4pin   To LOWER lcd screen (backlight cathode/anode)
  P19  1pin   Shielding-Plate for CPU (lower clip)
  P20  1pin   Shielding-Plate for CPU (upper clip)
  P21  1pin   Shielding-Plate for CPU (right clip)
  P22     -   N/A
  P23  2pin   To Internal Microphone (via orange shielded wire)
  P24 14pin   DSi XL only (L/VOL+/-, which were formerly on P16 in old DSi)
```

DSi Front/bottom-Side Text Layer sections (in upper left of mainboard)

```
  (A)  For components underneath of shielding plate
  (B)  For components in lower-right board edge (near battery connector)
  (C)  For components at middle/right of cartridge slot
  (D)  For components left of U4 (left board edge)
  (E)  For components right of U4 (above headphone socket)
  (F)  For components at lower/right of cartridge slot
```

DSi Back/top-Side Text Layer sections (at various places)

```
  (A)  at top/middle,  for components at upper right edge
  (B)  at middle/left, for components near upper right edge
  (C)  at lower/left,  for components left of Y-button
  (D)  at lower/righz, for components at right edge
```



## DSi Wifi Daughterboard (DWM-W015) (older DSi version)


PCB Text: "RU (S)-717V 01 ,\\" or "RU (S)-717V 03 ,\\" or "FK RU 06 ,\\"

```
  U   56pin "Mitsumi, Japan, 844L, MM3218" (same as in DS Lite)
  U  132pin "ROCm, Atheros, AR6002G-AC1B, E19077.1B, 0844, Taiwan"
  U    8pin I2C EEPROM "408F, B837" (HN58X2408F; 1Kx8 for atheros calibration)
  U    8pin SPI FLASH big chip "45PE10V6, HPASC VS, KOR 8364, ST"  ;\either one
  U    8pin SPI FLASH tiny chip "5A32, 8936?"                      ;/installed
  U    8pin "4P, K" or "S6, K" (odd 3+1+3+1 pin package, near antenna)
  U    4pin "3VP, OT" or "3VB, OS" (at board edge, near 50pin connector)
  X    4pin "26.000, 9848" (bigger oscillator, for atheros chip)
  X    4pin "22.000, xxxx" (smaller oscillator, for mitsumi chip)
  P   50pin Connector to Mainboard
  P    2pin Connector for Antenna (shielded white cable)
```

The "3VP/3VP" thing is some 1.2V voltage regulator (sth like LP3983 or TPS799xx
or similar).

White PCB sticker (underneath of the black isolation sticker): "DWM-W015,
IC:4250A-DWMW015, FCC ID:EW4DWMW015, [R]003WWA080444, [T]D080261003, MADE IN
PHILIPINES, MITSUMI ELEC. CO., LTD."



## DSi Wifi Daughterboard (DWM-W024) (newer DSi version)


PCB Text: "FB RU 06 ,\\"

```
  U   76pin "ROCm, Atheros, AR6013G-AL1C" (or 80pin, with 4pins at edges?)
  U    8pin I2C EEPROM? "4DA?, D940?"   ;maybe I2C eeprom for atheros
  U    8pin SPI FLASH "5A32, 8937?"   ;FLASH (small solder pads)
  U    8pin SPI FLASH not installed (alternate bigger solder pads for FLASH?)
  U    4pin "?" (at board edge, near 50pin connector)
  X    4pin "??" (oscillator, near ROCm chip)
  P   50pin Connector to Mainboard
  P    2pin Connector for Antenna (shielded white cable)
```



## DSi Wifi Daughterboard (J27H020) (alternate newer DSi version)


This seems to be functionally same as DWM-W024, but the PCB is different, and
the circuit seems to use a different voltage regulator, and includes solder
pads for some additional uninstalled components. And the shielding is difficult
to remove because it's soldered all way round (rather than just at some solder
points).

- Sticker 1:
  - HON HAI PRECISION IND.CO.,LTD.        ;aka Foxconn
  - MODEL: J27H020
  - [R] 003WWA100195
  - [T] D100196003
  - FCC ID: MCLJ27H020
  - IC: 2878D-27H020
- Sticker 2:
  - (barcode)
  - \<mac.address> J27H020.00 LF, 4xxxxxx-xxx
- Board:
  - U1   76pin atheros ... "ATHEROS, AR6013G-AL1C, N2U586.00C, 1035, KOREA"
  - U2    -    -
  - U3    -    -
  - U4    8pin I2C EEPROM "G80, 8, G02"
  - U5    8pin SPI FLASH big chip "26FV032T, OGK01"  (installed)
  - U6    -    -
  - U7    8pin SPI FLASH small chip (not installed)
  - U?    5pin voltage regulator or so "IG19P"
  - U?    6pin whatever near antenna (not installed)
  - Y1    4pin crystal "H400K"
  - J3    2pin Connector for Antenna (shielded white cable)
  - J6   50pin Connector to Mainboard



## 3DS Wifi Daughterboard (DWM-W028, or J27H023, or J27H023.01)


Component list is unknown. The thing is said to use a "Atheros AR6014" chip.

Later 3DS models have the Wifi unit (with AR6014G chip) on the mainboard
(instead of using a removeable DWM board).



## DSi Battery/DPAD Daughterboard "C/TWL-SUB-01"


```
  TH1  2pin  Battery Thermistor Thermal Sensor (ca. 10kOhm at room temperature)
  F1   2pin  Battery Fuse
  SW1  2pin  DPAD Up Button
  SW2  2pin  DPAD Down Button
  SW3  2pin  DPAD Left Button
  SW4  2pin  DPAD Right Button
  SW5  2pin  Power/Reset Button
  P1  15pin  To Mainboard (P15) (button/led signals) (wire "15P-01")
  P2   6pin  To 3xLEDs
  P3   3pin  To battery (TWL-003 3.6V 840mAh 3Wh C/TWL-A-BP, Li-ion 00"
  Wire 2pin  To Mainboard (P17) (battery supply) (red=vcc, black=gnd)
```



## DSi LED Board/Foil "LED-01, (DF)"


```
  D    2pin  Left LED      ;-wifi
  D    2pin  Middle LED    ;-charge
  D    2pin  Right LED 1   ;\power "two-color-LED"
  D    2pin  Right LED 2   ;/composed of 2 single LEDs
  Wire 6pin  To Battery/DPAD Daughterboard
```



## DSi Lower Screen with Touchpad


```
  Wire 4pin  Touchpad
  Wire 4pin  Backlight (actually 2pins, each 2 pins are same)
  Wire xxpin Video Signals
  LCD  "LS033A1DG48R, 8X16Q U0003986"
```



## DSi Upper Screen with Speakers & Cameras & LED & Microphone


```
  Orange Ribbon Cable: Video Signals, Backlight, and Speakers
  Black Ribbon Cable: Cameras and Camera LED
  Shielded Orange 2pin Wire: Microphone
  Shielded White 2pin Wire: Wifi PCB Antenna
  LCD  "LS033A1DG38R, BX16Q L0005532"
  The speakers use red/black wires, which connect to the orange ribbon cable
```



## DSi Upper Screen Area Extra Components: Speakers & Cameras & LED & Microphone




## DSi Lower Case (SD Slot, L/R and VOL+/- Buttons, and screen calibration)


```
  Whatever, not checked yet
```



## DSi Disassembly Notes


Bottom Cover Screws:

```
  7 screws (two are under battery cover)
```

Remove bottom cover, and:

```
  P16: To bottom cover (SD Slot and L/R/VOL+/-) --> pull (away from board)
```

Remove Wifi Daughterboard:

```
  P5:  Wifi-board (without cable)               --> pull (away from board)
  WHITE: Wifi-Antenna (shielded 2pin)           --> pull (away from wifi-board)
```

Remove mainboard:

```
  ORANGE P24 (shielded 2pin)  --> pull (away from board)
  WHITE SUPPLY                --> lift (use screwdriver & push away from board)
  3x bigger white/black connectors --> lift black lid (at cable-side)
  2x smaller black connectors      --> lift black lid (at cable-end) (!!!)
```

Turn mainboard over, then unlock the connector at back side:

```
  1x bigger white/black connector  --> lift black lid (at cable-side)
```

Remove Battery board:

```
  1x smaller black connector       --> lift black lid (at cable-end) (!!!)
  1x bigger white/black connectors --> lift black lid (at cable-side)
  (don't disconnect bigger connector if the other cable end is already
  disconnected from mainboard) (or if you did do, reassemble as follows:
  longer cable end to battery board, short cable end to mainboard)
  1x battery cable (disconnect at mainboard side, see there)
```

Top Cover Disassembly:

```
  Disconnect upper LCD and mic/antenna from mainboard (see above)
  Remove 4 screws (all hidden under square rubber pieces)
  slide rear bezel upwards by two millimeters?
  push metal hinge inwards by three millimeters (under LED unit)
```




# AUX DSi Signals/Testpoints



The DSi has testpoints with friendly names. The DSi XL has "nameless"
testpoints (numbered TP1 thru TP194, as described on 
- [https://www.dsibrew.org/wiki/DSi\_XL\_testpoints](https://www.dsibrew.org/wiki/DSi_XL_testpoints) which may include some bugs for the Supply and BGA pins though).


```
  ADPO       TP... U3,U6        Charger connected? (Low=Connected, High=No)
  AOUT       TP... U3,U6        Analog battery level? (max=2.35V?)
  PM_SLP     TP... U1,U3,U6     Sleep or so? (Low=Normal, High=Sleep?)
  PMOFF      TP... U1,U3,U6,U17 Powerman/Headphone off? (Low=Normal)
  PWSWO      TP... U3,U6        Power? (Low=Off, or Reset-tapping, High=On)
  VCNT5      TP... U1,U3,U4,U19 Control for VSHD for Both Screens ?
  mFE        TP... U6          BPTWL Flash Enable (aka FLMD0)    (Low=Normal)
  /mRST      TP... U6          BPTWL Flash Invoke transfer?      (High=Normal)
  /IRQ_O     TP... U1,U6       BPTWL Interrupt (eg. Power Button)
  GPIO330    TP... U1          General Purpose GPIO bit (?)
  RESET      TP... P5,U1,U3..  Reset WifiFlash,MainCpu,PowerMan,TSC from BPTWL
  P00        TP... U1,SW1      Button A
  P01        TP... U1,SW2      Button B
  P02        TP... U1,SW5,U6   Button SELECT (also SELECT+VOLP/VOLN=Backlight)
  P03        TP... U1,SW6      Button START
  P04        TP... U1,P15      Button DPAD right
  P05        TP... U1,P15      Button DPAD left
  P06        TP... U1,P15      Button DPAD up
  P07        TP... U1,P15      Button DPAD down
  P08        TP... U1,P16      Button Shoulder R
  P09        TP... U1,P16      Button Shoulder L
  R00        TP... U1,SW3      Button X
  R01        TP... U1,SW4      Button Y
   -?-       TP... -           Button Debug aka R03 (if any exists)
  VOLP       TP... P16,U6      Button Volume Plus  (Backlight when SELECT+VOLP)
  VOLN       TP... P16,U6      Button Volume Minus (Backlight when SELECT+VOLN)
  PWSW       TP... P15,U3      Button Power (High=Released)
  PENIRQ     TP... U1,U4       Touchscreen Pen Down
  R7         TP... U1,U10      Shell Open Magnet Sensor (HINGE)
  RTC_INT    TP... U9,U1       RTC Real-Time Clock Interrupt
  -          TP... U9,U1       RTC Real-Time Clock CS
  -          TP... U9,U1       RTC Real-Time Clock /SCK
  -          TP... U9,U1       RTC Real-Time Clock SIO
  SCL        TP... P9,U1,..    Primary I2C Bus Clock (Both Cameras,etc.)
  SDA        TP... P9,U1,..    Primary I2C Bus Data  (Both Cameras,etc.)
  -          TP... U8,U6       Primary I2C Bus Clock (for BPTWL xlated to 3.3V)
  -          TP... U8,U6       Primary I2C Bus Data  (for BPTWL xlated to 3.3V)
  SCL1       TP... U3,U6,U7    Secondary IC2 bus Clock (BPTWL/Wiper/Powerman)
  SDA1       TP... U3,U6,U7    Secondary IC2 bus Data  (BPTWL/Wiper/Powerman)
  SD10_CLK   TP... U1,P16      SD/MMC SD Slot Clock (typ 16MHz)
  SD10_CMD   TP... U1,P16      SD/MMC SD Slot Cmd
  SD10_DATA0 TP... U1,P16      SD/MMC SD Slot Data0
  SD10_DATA1 TP... U1,P16      SD/MMC SD Slot Data1
  SD10_DATA2 TP... U1,P16      SD/MMC SD Slot Data2
  SD10_DATA3 TP... U1,P16      SD/MMC SD Slot Data3
  SD10_WP    TP... U1,P16      SD/MMC SD Slot Write Protect Switch
  SD10_CD    TP... U1,P16      SD/MMC SD Slot Card Detect Switch
  SD10_VDD   TP... P16         SD/MMC SD Slot Supply (aka VDD33)
  SD11_CLK   TP... U1,U5       SD/MMC eMMC Clock (typ 16MHz)
  -          TP... U1,U5       SD/MMC eMMC Cmd/Data0..3/CD/WP/VDDI
  SPI_CS1    TP... U1,U3,U4    SPI Chip Select Powerman
  SPI_CS2    TP... U1,P5       SPI Chip Select Wifi FLASH chip select
  SPI_CS3    TP... U1,U4       SPI Chip Select Touchscreen/Sound TSC
  -          TP... P5,R122     SPI Wifi FLASH_WP (R122)
  SPI_SCK    TP... U1,P5,U3,U4 SPI Wifi/Pow/TSC Clock
  SPI_MISO   TP... U1,P5,U3,U4 SPI Wifi/Pow/TSC Master In Slave Out (Reply)
  SPI_MOSI   TP... U1,P5,U3,U4 SPI Wifi/Pow/TSC Master Out Slave In (Command)
  MC1_CLK    TP... U1,P1       NDS/DSi cartridge slot
  MC1_CS     TP... U1,P1       NDS/DSi cartridge slot
  MC1_RES    TP... U1,P1       NDS/DSi cartridge slot
  MC1_CS2    TP... U1,P1       NDS/DSi cartridge slot
  MC1_IREQ   TP... U1,P1       NDS/DSi cartridge slot
  MC1_VDD    TP... P1,Q6/Q7    NDS/DSi cartridge slot Power Supply (when on)
  -          TP... U1,R28,Q7   NDS/DSi cartridge slot Power Enable
  MC1_IO0    TP... U1,P1       NDS/DSi cartridge slot Data
  MC1_IO1    TP... U1,P1       NDS/DSi cartridge slot Data
  MC1_IO2    TP... U1,P1       NDS/DSi cartridge slot Data
  MC1_IO3    TP... U1,P1       NDS/DSi cartridge slot Data
  MC1_IO4    TP... U1,P1       NDS/DSi cartridge slot Data
  MC1_IO5    TP... U1,P1       NDS/DSi cartridge slot Data
  MC1_IO6    TP... U1,P1       NDS/DSi cartridge slot Data
  MC1_IO7    TP... U1,P1       NDS/DSi cartridge slot Data
  MC1_DET    TP... U1,P1       NDS/DSi cartridge slot Cart Insert Switch
  -          TP... U1          NDS/DSi 2nd cart slot (NC in retail console)
  -          TP... U1,U2       Main RAM Address A0..A22
  -          TP... U1,U2       Main RAM Data DQ0..DQ15
  -          TP... U1,U2       Main RAM /OE
  -          TP... U1,U2       Main RAM /WE
  -          TP... U1,U2       Main RAM CE1
  -          TP... U1,U2       Main RAM CE2
  -          TP... U1,U2       Main RAM CLK
  -          TP... U1,U2       Main RAM /ADV
  -          TP... U1,U2       Main RAM /LB
  -          TP... U1,U2       Main RAM /UB
  -          TP... U1          Main RAM A23 or Chipsel for debug ver 32Mbyte
  -          TP... P5,U1       Wifi Atheros SDIO Clock (typ 16MHz?)
  -          TP... P5,U1       Wifi Atheros SDIO Command
  -          TP... P5,U1       Wifi Atheros SDIO Data 1
  -          TP... P5,U1       Wifi Atheros SDIO Data 2
  -          TP... P5,U1       Wifi Atheros SDIO Data 3
  -          TP... P5,U1       Wifi Atheros SDIO Data 3
  -          TP... P5,U9       Wifi Atheros 32kHz (from RTC_FOUT to Wifi)
  /WIFI_RST  TP... P5,U6       Wifi Atheros Reset?
  ATH_TX_H   TP... P5,U6       Wifi Atheros TX (for Wifi LED?)
  -          TP... P5,U1       Wifi SEL_ATH_L (near PENIRQ pin)
  WL_RXPE    TP... P5,U1,U6    Wifi RX something (for CPU and Wifi LED)
  WL_TXPE    TP... P5,U1,U6    Wifi TX something (for CPU and Wifi LED)
  -          TP... P5,U1       Wifi Mitsumi BBP_SLEEP
  -          TP... P5,U1       Wifi Mitsumi RF_SLEEP
  -          TP... P5,U1       Wifi Mitsumi BBP_SCS
  -          TP... P5,U1       Wifi Mitsumi RF_SCS
  -          TP... P5,U1       Wifi Mitsumi RB_RF_SDO
  -          TP... P5,U1       Wifi Mitsumi RB_RF_SDI
  -          TP... P5,U1       Wifi Mitsumi RB_RF_SCLK
  -          TP... P5,U1       Wifi Mitsumi CCA
  -          TP... P5,U1       Wifi Mitsumi MCLK
  -          TP... P5,U1       Wifi Mitsumi TRDATA
  -          TP... P5,U1       Wifi Mitsumi TRCLK
  -          TP... P5,U1       Wifi Mitsumi TRRDY
  -          TP... P5          Wifi JTAG_TDO    (NC in console)
  -          TP... P5          Wifi JTAG_TDI    (NC in console)
  -          TP... P5          Wifi JTAG_TMS    (NC in console)
  -          TP... P5          Wifi JTAG_TCK    (NC in console)
  -          TP... P5          Wifi JTAG_TRST_L (NC in console)
  -          TP... P5          Wifi to MM3218.pin47 (0ohm)     (NC in console)
  .          TP... P5          Wifi to MM3218.pin28 (0ohm+cap) (NC in console)
  SND_SDI    TP... U1,U4       Audio I2S Data In   (Microphone)
  SND_SDO    TP... U1,U4       Audio I2S Data Out  (Speaker/Headphone)
  SND_WS     TP... U1,U4       Audio I2S LR Clock  (typ 32kHz)
  SND_SCLK   TP... U1,U4       Audio I2S Bit Clock (typ 1MHz, aka SND_WS*2*16)
  SND_MCLK   TP... U1,U4       Audio TSC Master Clock (typ 8MHz)
  -          TP... U4,U7       Audio Volume Wiper (from I2C potentiometer)
  SPLN       TP... P7,U4       Audio Speaker Left Minus
  SPLP       TP... P7,U4       Audio Speaker Left Plus
  SPRN       TP... P7,U4       Audio Speaker Right Minus
  SPRP       TP... P7,U4       Audio Speaker Right Plus
  HP#SP      TP... P4,U1,U4    Audio Headphone/Speaker switch
  SL         TP... P4,Q5,U4    Audio Headphone Left
  SR         TP... P4,Q4,U4    Audio Headphone Right
  -          TP... U1,U17      Audio Headphone Mute (from Main CPU GPIO)
  -          TP... U4,U17,Q..  Audio Headphone Mute (via Q4/Q5 to SR/SL)
  MIC        TP... P4,P23      Audio Microphone (via .. to LIN)
  LIN        TP... U4,U18      Audio Microphone Input
  -          TP... U4,U18      Audio Microphone Bias (to U18)
  BLA2       TP... P7,U3,U14   LCD Upper Screen Backlight Anode (ca. 15V)
  BLC2       TP... P7,U3       LCD Upper Screen Backlight Cathode
  LDB20      TP... P7,U1       LCD Upper Screen Blue Bit0
  LDB21      TP... P7,U1       LCD Upper Screen Blue Bit1
  LDB22      TP... P7,U1       LCD Upper Screen Blue Bit2
  LDB23      TP... P7,U1       LCD Upper Screen Blue Bit3
  LDB24      TP... P7,U1       LCD Upper Screen Blue Bit4
  LDB25      TP... P7,U1       LCD Upper Screen Blue Bit5
  LDR20      TP... P7,U1       LCD Upper Screen Red Bit0
  LDR21      TP... P7,U1       LCD Upper Screen Red Bit1
  LDR22      TP... P7,U1       LCD Upper Screen Red Bit2
  LDR23      TP... P7,U1       LCD Upper Screen Red Bit3
  LDR24      TP... P7,U1       LCD Upper Screen Red Bit4
  LDR25      TP... P7,U1       LCD Upper Screen Red Bit5
  LDG20      TP... P7,U1       LCD Upper Screen Green Bit0
  LDG21      TP... P7,U1       LCD Upper Screen Green Bit1
  LDG22      TP... P7,U1       LCD Upper Screen Green Bit2
  LDG23      TP... P7,U1       LCD Upper Screen Green Bit3
  LDG24      TP... P7,U1       LCD Upper Screen Green Bit4
  LDG25      TP... P7,U1       LCD Upper Screen Green Bit5
  COM2       TP... P7,P16      LCD Upper Screen VCOM Calibration
  DCLK       TP... P7,P8,U1    LCD Both Screens Dot Clock  ;2.8MHz
  LS         TP... P7,P8,U1    LCD Both Screens Latch Pulse;15.6kHz, 0.3us high
  SPL        TP... P7,P8,U1    LCD Both Screens Start Pulse;15.6kHz, 0.3us high
  GCK        TP... P7,P8,U1    LCD Both Screens Gate Clock ;15.6kHz, 9us low
  REV        TP... P7,P8,U1    LCD Both Screens VcomFlicker;7kHz, toggle@15kHz
  GSP        TP... P7,P8,U1    LCD Both Screens Gate Start ;60Hz, short low
  INI        TP... P7,P8,U1    LCD Both Screens Init? MOD? ;usually high?
  VSHD       TP... P7,P8,U19   LCD Both Screens Supply 3.3V
  VDD5       TP... P7,P8,P16   LCD Both Screens Supply 5.0V
  VDD-5      TP... P7,P8       LCD Both Screens Supply -5.0V
  VDD10      TP... P7,P8       LCD Both Screens Supply 10.0V
  BLA1       TP... P18,U3,U13  LCD Lower Screen Backlight Anode (ca. 14V)
  BLC1       TP... P18,U3      LCD Lower Screen Backlight Cathode (ca. 0V)
  LDB10      TP... P8,U1       LCD Lower Screen Blue Bit0
  LDB11      TP... P8,U1       LCD Lower Screen Blue Bit1
  LDB12      TP... P8,U1       LCD Lower Screen Blue Bit2
  LDB13      TP... P8,U1       LCD Lower Screen Blue Bit3
  LDB14      TP... P8,U1       LCD Lower Screen Blue Bit4
  LDB15      TP... P8,U1       LCD Lower Screen Blue Bit5
  LDR10      TP... P8,U1       LCD Lower Screen Red Bit0
  LDR11      TP... P8,U1       LCD Lower Screen Red Bit1
  LDR12      TP... P8,U1       LCD Lower Screen Red Bit2
  LDR13      TP... P8,U1       LCD Lower Screen Red Bit3
  LDR14      TP... P8,U1       LCD Lower Screen Red Bit4
  LDR15      TP... P8,U1       LCD Lower Screen Red Bit5
  LDG10      TP... P8,U1       LCD Lower Screen Green Bit0
  LDG11      TP... P8,U1       LCD Lower Screen Green Bit1
  LDG12      TP... P8,U1       LCD Lower Screen Green Bit2
  LDG13      TP... P8,U1       LCD Lower Screen Green Bit3
  LDG14      TP... P8,U1       LCD Lower Screen Green Bit4
  LDG15      TP... P8,U1       LCD Lower Screen Green Bit5
  COM1       TP... P8,P16      LCD Lower Screen VCOM Calibration
  X-         TP... P10,U4      LCD Lower Screen Touchpad X-
  Y-         TP... P10,U4      LCD Lower Screen Touchpad Y-
  X+         TP... P10,U4      LCD Lower Screen Touchpad X+
  Y+         TP... P10,U4      LCD Lower Screen Touchpad Y+
  VIN        TP2   P11         Supply 4.6V External Power Supply Input (DC IN)
  VGND       TP5   P11         Supply 0.0V External Power Supply Ground
  VDET-      TP... U3,Q3       Supply 4.xV Shortcut with BT+ (via 0 ohm R71)
  BT+        TP... P17,U3,U11  Supply 4.xV Battery Plus (red wire) 3.6V 800mAh
  BT-        TP... P17         Supply 0.0V Battery GND  (black wire)
  DET        TP... P15,U3      Supply Battery Middle Pin  (Low=Normal)
  TH         TP... P15,U11     Supply Battery Thermal Sensor (on DPAD board)
  PVDD       TP... U3,U9       Supply 4.xV Permanent Power for RTC
  VDD12      TP... U3,U1       Supply 1.2V (Main CPU)
  VDD18      TP... P9,U3,U1,.. Supply 1.8V (Main CPU and many things)
  VDD28      TP... P9,U12,U6   Supply 2.8V (for Cameras and BPTWL)
  VDD33      TP... U3,U1,..    Supply 3.3V (Main CPU and many things)
  VDD42      TP... P15,P9,U3.. Supply 4.2V (for LEDs) (and U19)
  B+         TP... U3,U4,U19.. Supply 4.xV (for Speakers, or everything?) U11
  SG         TP... U3          Supply 0.0V Ground or Audio GND or so
  GND1       TP... ..          Supply 0.0V Ground (near COM1/COM2 testpoints)
  GND2       TP... ..          Supply 0.0V Ground (near wifi connector)
  EXTB+      TP... U3,U11,Q1   Charger 4.xV or 0V (EXTB+ comes from VIN via Q1)
  Rosc       TP... U3,U11      Charger 1.0V ?
  RICHG      TP... U3,U11      Charger 0.4V ?
  ORANGE     TP... P15,U11     LED Battery Charge
  BLUE       TP... P15,U6,Q11  LED Power On/Good
  YELLOW     TP... P15,U6,Q12  LED Wifi
  RED        TP... P15,U6      LED Power On/Low
  CAM_LED    TP... P9,U6,Q13   LED Camera
  CAM_D0     TP... P9,U1       Both Cameras Data Bit0
  CAM_D1     TP... P9,U1       Both Cameras Data Bit1
  CAM_D2     TP... P9,U1       Both Cameras Data Bit2
  CAM_D3     TP... P9,U1       Both Cameras Data Bit3
  CAM_D4     TP... P9,U1       Both Cameras Data Bit4
  CAM_D5     TP... P9,U1       Both Cameras Data Bit5
  CAM_D6     TP... P9,U1       Both Cameras Data Bit6
  CAM_D7     TP... P9,U1       Both Cameras Data Bit7
  CAM_RST    TP... P9,U1       Both Cameras Reset?
  HSYNC      TP... P9,U1       Both Cameras Hsync
  VSYNC      TP... P9,U1       Both Cameras Vsync
  RCLK       TP... P9,U1       Both Cameras Data Clock (8MHz, unless blanking)
  CKI        TP... P9,U1       Both Cameras Master Clock (8MHz) (or off)
```



## Cut-Links


```
  CL1   VDD12    to/near Powerman
  CL2
  CL3   VDD18    to/near Powerman
  CL4    ?       near Powerman (above L3)
  CL5   VDD33    PCB top side (near Powerman)
  CL6   VDD5     near lower screen connector (F)
  CL7   BLC1     near lower screen connector
  CL8
  CL9   GNDed     to/near Powerman (near ADPO pin)
  CL10  GNDed     to/near Powerman (near VDD5 pin)
  CL11
  CL12
  CL13
  CL14  SDIO CLK   to/near wifi connector
  CL15  BB RF CLK  to/near wifi connector
  CL16  Wifi MCLK  to/near wifi connector
  CL17
  CL18
  CL19
  CL20
  CL21  VDD42    to/near Powerman
  CL22  VDD10    to DA1 and C5, near DPAD board connector
  CL23  VDD-5    near lower screen connector
  CL24
  CL25  ?        PCB top side (near Button B)
  CL26
  CL27  ?        PCB top side (near Button B) (D)
  CL28  ?        PCB top side (near Button B) (D)
  CL29
  CL30
  CL31
  CL32
  CL33
  CL34  SND_SDI   near TSC chip
  CL35  SND_SDO   near TSC chip
  CL36  SND_WS    near TSC chip
  CL37  SND_SCLK  near TSC chip
  CL38  SND_MCLK  near TSC chip
  CL39
```



## Short-Links


```
  R122  FLASH_WP to VDD33 (not installed)
```




# AUX DSi Internal Connectors




## P1 - 19pin - NDS/DSi cartridge slot (17pin slot + 2pin switch at right side)


```
  1   GND
  2   MC1_CLK
  3   -
  4   MC1_CS
  5   MC1_RES
  6   MC1_CS2
  7   MC1_IREQ
  8   MC1_VDD via Q6 to VDD33 (cpu signal preamplified from Q7)
  9   MC1_IO0
  10  MC1_IO1
  11  MC1_IO2
  12  MC1_IO3
  13  MC1_IO4
  14  MC1_IO5
  15  MC1_IO6
  16  MC1_IO7
  17  GND
  18  MC1_DET           ;\switch closed when cart inserted
  19  GND               ;/
  Shield GND
```



## P4 - 8pin - External microphone/headphone combo socket


```
  1  GND    ;\      ;\
  2  SL     ; head- ; headphone gnd/left/right
  3  SR     ; phone ;/
  4  GND    ;       ;\headphone/speaker switch (pin 4+5 shortcut with each
  5  HP#SP  ;/      ;/other when no headphone connected)
  6  MIC    ;\    ;\microphone switch (pin6+7 shortcut when no mic connected)
  7  Switch ; mic ;/(internal mic from P23 is then passed from pin7 to pin6)
  8  GND    ;/
```



## P5 - 50pin - DSi Wifi-Daughterboard (DWM-W015, DWM-W024, or J27H020)


```
                           GND   2  1   SDIO.CLK       ;\
                         VDD18   4  3   GND            ; SDIO for
                         VDD18   6  5   SDIO.DAT0      ; Atheros Wifi
                           GND   8  7   SDIO.DAT3      ; (CLK, CMD, DATA0-3)
                         VDD33  10  9   SDIO.DAT1      ;
                         VDD33  12  11  SDIO.CMD       ;
                           GND  14  13  SDIO.DAT2      ;/
                      ATH_TX_H  16  15  DSi: NC (DWM: JTAG_TDO)
                     /WIFI_RST  18  17  DSi: NC (DWM: JTAG_TMS)
     (DWM:JTAG_TDI)    DSi: NC  20  19  GND
     (DWM:JTAG_TCK)    DSi: NC  22  21  RTC_FOUT (or RTC_F32K?)  ;for Atheros?
     (DWM:JTAG_TRST_L) DSi: NC  24  23  GND
 (near CPU irq pins) SEL_ATH_L  26  25  DSi: NC (wifi: via 0 ohm MM3218.pin47)
               /FLASH_WP (R122) 28  27  SPI_CS2 (wifi FLASH memory)
                       SPI_SCK  30  29  BBP_SLEEP    to MM3218.pin42
                      SPI_MISO  32  31  RF_SLEEP     to MM3218.pin41
                      SPI_MOSI  34  33  RF_SCS       to MM3218.pin38
       to MM3218.pin15     CCA  36  35  BBP_SCS      to MM3218.pin37
                       WL_RXPE  38  37  BB_RF_SDO    to MM3218.pin36
       to MM3218.pin19  TRDATA  40  39  BB_RF_SDI    to MM3218.pin35
                           GND  42  41  BB_RF_SCLK   to MM3218.pin34
       to MM3218.pin21   TRCLK  44  43  NC(VDD18_TP) to MM3218.pin28 (0ohm+cap)
       to MM3218.pin18   TRRDY  46  45  GND
                       WL_TXPE  48  47  MCLK    to MM3218.pin23 (via XX & CLxx)
                         RESET  50  49  GND
```

- [https://fccid.io/EW4DWMW024/Label/Label-format-and-location-1137926.pdf](https://fccid.io/EW4DWMW024/Label/Label-format-and-location-1137926.pdf)
- [https://fccid.io/EW4DWMW015/Label/Label-Location-1031953.pdf](https://fccid.io/EW4DWMW015/Label/Label-Location-1031953.pdf)
Pin 25 and 43 are VDD test points on DWM-W015 wifiboard (but are NC on DSi
mainboard & DWM-W024 wifiboard).



## P7 - 47pin - To UPPER lcd screen (video+backlight+speakers) (on PCB backside)


```
                          BLA2   1  2   BLC2    ;-backlight
                          SPLN   3  4   SPLN    ;\left speaker
                          SPLP   5  6   SPLP    ;/
                          SPRN   7  8   SPRN    ;\right speaker
                          SPRP   9  10  SPRP    ;/
                         VDD-5  11  12  VDD10
                          VDD5  13  14  GND
                          VSHD  15  16  VSHD
                           INI  17  18  GSP
                           GCK  19  20  LDB20
                         LDB21  21  22  LDB22
                         LDB23  23  24  LDB24
                         LDB25  25  26  LDG20
                         LDG21  27  28  LDG22
                           GND  29  30  LDG23
                         LDG24  31  32  LDG25
                         LDR20  33  34  LDR21
                         LDR22  35  36  LDR23
                         LDR24  37  38  LDR25
                           GND  39  40  DCLK
                           SPL  41  42  LS
                           GND  43  44  via C79 to COM2
                           REV  45  46  GND
                          COM2  47
```



## P8 - 37pin - To LOWER lcd screen (video signals)


```
                         VDD-5   1  2   VDD10
                          VDD5   3  4   GND
                          VSHD   5  6   VSHD
                           INI   7  8   GSP
                           GCK   9  10  LDB10
                         LDB11  11  12  LDB12
                         LDB13  13  14  LDB14
                         LDB15  15  16  LDG10
                         LDG11  17  18  LDG12
                           GND  19  20  LDG13
                         LDG14  21  22  LDG15
                         LDR10  23  24  LDR11
                         LDR12  25  26  LDR13
                         LDR14  27  28  LDR15
                           GND  29  30  DCLK
                           SPL  31  32  LS
                           GND  33  34  via C93 to COM1
                           REV  35  36  GND
                          COM1  37
```



## P9 - 25pin - To UPPER lcd screen (signals for both cameras, and camera led)


```
                           GND   1  2   CAM_LED
                         VDD42   3  4   GND
                  R100    RCLK   5  6   GND
                           GND   7  8   HSYNC
                         VSYNC   9  10  CAM_D5  RA7
                   RA7  CAM_D6  11  12  CAM_D4  RA7
                       CAM_RST  13  14  SCL
                           SDA  15  16  CAM_D7  RA7
                   RA6  CAM_D0  17  18  CAM_D3  RA6
                   RA6  CAM_D1  19  20  CAM_D2  RA6
                         VDD28  21  22  GND
                           CKI  23  24  GND
                         VDD18  25
```



## P10 - 4pin - To LOWER lcd screen (touchpad X-,Y-,X+,Y+)


```
  1 X-
  2 Y-
  3 X+
  4 Y+
```



## P11  2pin   External Power Supply input (4.6V DC IN)


```
  1 VIN  (+4.6V)
  2 VGND (GND)
  Shield (GND)
```



## P15 - 15pin - To battery/DPAD/PowerButton board (and onwards to 3xLEDs)


```
  dpad up button      P06  1  2  ORANGE (LED) Battery Charge
  dpad right button   P04  3  4  BLUE   (LED) Power On/Good
  dpad left button    P05  5  6  YELLOW (LED) Wifi
  dpad down button    P07  7  8  RED    (LED) Power On/Low
                      GND  9  10 VDD42 (to LEDs)
                      GND 11  12 TH on DPAD board (via R102 to TH on main)
  middle battery pin  DET 13  14 GND
  power button       PWSW 15
```

Note: On Daughterboard, pins are mirrored (eg. PWSW=Pin1 instead Pin15)



## P16 - 26pin - To bottom cover (SD Slot and L/R/VOL+/- buttons)


On original DSi:

```
                      GND  2  1  SD10_CLK                   ;\
               SD10_DATA0  4  3  SD10_VDD (aka VDD33)       ;
               SD10_DATA1  6  5  SD10_VDD (aka VDD33)       ; pin 1..18
                  SD10_WP  8  7  GND                        ; to RIGHT side:
                      GND 10  9  SD10_CMD                   ; R-button, and
  shoulder button R   P08 12  11 GND                        ; SD-card slot
                      GND 14  13 SD10_DATA3                 ;
                  SD10_CD 16  15 SD10_DATA2                 ;
                      GND 18  17 GND                        ;/
                      GND 20  19 GND                        ;\pin 19..20
  maybe display ;\   VDD5 22  21 VOLP  volume plus          ; to LEFT side:
  calibration?  ;    COM1 24  23 VOLN  volume minus         ; L-button, VOL +/-
  (at battery)  ;/   COM2 26  25 P09   shoulder button L    ;/and calibration
```

On DSi XL (changed pins, COM1/COM2 removed, and L/VOL+- moved to P24):

```
       GND  1  2  GND
       GND  3  4  GND
       GND  5  6  GND
  SD10_CLK  7  8  GND
     VDD33  9  10 SD10_D0
     VDD33 11  12 SD10_D1
       GND 13  14 SD10_WP
  SD10_CMD 15  16 VDD33
       GND 17  18 P08 (should button R)
   SD10_D3 19  20 VDD33
   SD10_D2 21  22 SD10_CD
       GND 23  24 GND
       GND 25  26 GND
```



## P17 - 2pin - Battery cable (lower-right) ;see text-layer (B)


```
  + BT+ (plus) (red wire)
  - BT- (GND)  (black wire)
```



## P18 - 4pin - To LOWER lcd screen (backlight cathode/anode)


```
  1 BLC1  ;\both same
  2 BLC1  ;/
  3 BLA1  ;\both same
  4 BLA1  ;/
```



## P19 - 1pin - Shielding-Plate for CPU (lower clip)



## P20 - 1pin - Shielding-Plate for CPU (upper clip)



## P21 - 1pin - Shielding-Plate for CPU (right clip)


```
  Shield GND
```



## P23 - 2pin - To Internal Microphone (via orange shielded wire)


```
  Pin  MIC (from P4.Pin7, disconnected when external microphone connected)
  Shield GND
```



## P24 - 14pin - DSi XL only (L/VOL+/- were formerly on P16 in old DSi)


```
               GND 1  2  GND
               N/C 3  4  VOLP
  P09 (shoulder-L) 5  6  VOLN
            GND 7-13  8-14 GND
```



## DPAD-BOARD - P2 - 6pin - To LEDs


```
  1  YELLOW  Wifi
  2  BLUE    Power On/Good
  3  ORANGE  Battery Charge
  4  GND   (for red+orange)
  5  RED     Power On/Low
  6  VDD42 (for yellow+blue)
```




# AUX DSi Chipset Pinouts



A photo of the DSi mainboard (with extra text layer on vias and solderpads) can
be found at:

- [http://problemkaputt.de/twl-core.jpg](http://problemkaputt.de/twl-core.jpg)



## DSi U1 - TWL-CPU (19x19 pin grid) (352 pins, aka 19x19 minus middle 3x3 pins)


```
      Wifi    MC2 maybe      MC1           SD/MMC  eMMC  SPI     RTC   IRQs
  .---.---.---------------.---------------.-------.---.-------.-------.---.---.
  |NC |CSB|NC  NC  NC  NC |D7  D3  IRQ CLK|D0  CLK|CLK|CS3 SCK|CS  SCK|R7 |NC |
  +---'   |               |               |       |   |       |   .---'   '---+
  |SDI CSR|NC  NC  NC  NC |D6  D2  DET CS |D1  CMD|D0 |CS2 MIS|SIO|PEN NC  WIF|
  |       |               |               |       |   |       +---+---.   .---+
  |SCK SDO|NC  NC  NC  NC |D5  D1  PWR CS2|D2  CD |D1 |CS1 MOS|R00 R01|RTC|P09|
  |       '---.       .---+           .---'   .---'   '---.---+       '---'   |
  |TCK TDA RDY|NC  NC |V33|D4  D0  RES|D3  WP |D3  D2  CMD| ? |P08 P07 P06 P05|
  |           '---+---'   '-----------'-------'-----------'---+               |
  |MCK CCA RXP TXP|GND V12 V33 GND V12 V33 G?  V12 V33 GND V33|P04 P03 P02 P01|
  | . .           |                                           +-----------.   |
  |DT3|SLR SLB ?  |GND V33 V12 GND GND GND V33 G?  GND V33 V12| ?  RES NC |P00|
  |   '. . . . . .|                                           |           '---+
  |CLK DT2 DT1 DT0|V33 GND V12 V33 GND V12 G?  V12 GND GND V33|PMO VC5 PMS X  |
  +-----------.   |                                           '-----------.   |
  |V33 NC  GND|CMD|V12 GND V33 GND V12 V33 GND V33 V12 V12 V33 GND GND GND|X  |
  |           '---'               .-----------.               .-----------'   |
  |V33 NC  V33 V33 GND V33 GND V33|-   -   -  |GND GND GND GND|HP# IRQ mut GND|
  +---.   .---.                   |           |               |               |
  |B15|V33|NC |V33 V12 GND V12 V12|-   -   -  |V12 V18 GND V12|NC  NC  NC  GP |
  |   '---'---'---.               |           |               +---------------+
  |B14 B13 B12 B11|V33 GND V33 GND|-   -   -  |V18 GND V18 GND|A1  D1  A0  D0 |
  |               |               '-----------'               |               |
  |B10 G15 G14 G13|GND V33 V12 GND V18 V12 V18 GND V18 V12 V18|A3  D3  A2  D2 |
  |               |                                           |               |
  |G12 G11 G10 R15|V33 V12 GND V12 GND V18 GND V12 GND V18 GND|A5  D5  A4  D4 |
  |               |                                           |               |
  |R14 R13 R12 R11|GND V33 V18 GND V18 V12 V18 GND V18 V12 V18|A7  D7  A6  D6 |
  +-----------.   |                                           |               |
  |DCK GSP SPL|R10|V33 V12 GND V18 GND V18 GND V12 GND V18 GND|A9  D9  A8  D8 |
  |       .---'---'-------.-------.---.---.-------.-----------'               |
  |LS  REV|B22 G24 G20 R22|D7  D3 |NC |RST|SCK WS |CE1 /OE A20 A11 D11 A10 D10|
  |   .---'               |       |   |   |       |                           |
  |GCK|B25 B21 G23 R25 R21|D6  D2 |NC |VSY|MCK SDO|NC  CE2 A19 A13 D13 A12 D12|
  |   |                   |       |   |   +---.   |                           |
  |INI|B24 B20 G22 R24 R20|D5  D1 |NC |HSY|SDA|SDI|/LB CLK A18 A21 A14 D15 D14|
  +---+               .---+       '---'   |   +---'                       .---+
  |NC |B23 G25 G21 R23|NC |D4  D0  CKI RCK|SCL|/UB ADV /WE A15 A17 A22 A16|NC |
  '---'---------------'---'---------------'---'---------------------------'---'
          LCD                  CAM         I2C SND          RAM               o
```



## DSi U2 - Main RAM (8Mx16) (Fujitsu MB82DBS08164, or NEC uPD46128512)


DSi mainboard solder pads (12x8 grid, within 14x10 grid):

```
       A    B    C    D    E    F    G    H    J    K    L    M    N    P
  10   -    -    -    -    -    -    -    -    -    -    -    -    -    -
  9    -    NC   NC   -    A15  A21  A22  A16  NC   VSS  -    NC   NC   -
  8    -    NC   NC   A11  A12  A13  A14  NC   DQ15 DQ7  DQ14 NC   NC   -
  7    -    -    -    A8   A19  A9   A10  DQ6  DQ13 DQ12 DQ5  -    -    -
  6    -    -    -    /WE  CE2  A20  -    -    DQ4  VDD  NC   -    -    -
  5    -    -    -    CLK  /ADV (W)  -    -    DQ3  VDD  DQ11 -    -    -
  4    -    -    -    /LB  /UB  A18  A17  DQ1  DQ9  DQ10 DQ2  -    -    -
  3    -    NC   -    A7   A6   A5   A4   VSS  /OE  DQ0  DQ8  NC   NC   -
  2    -    NC   NC   -    A3   A2   A1   A0   NC   /CE1 -    NC   NC   -
  1 o  -    -    -    -    -    -    -    -    -    -    -    -    -    -
```

DSi RAM - Fujitsu MB82DBS08164 (14x10 grid):

```
       A    B    C    D    E    F    G    H    J    K    L    M    N    P
  10   NC   NC   NC   NC   NC   NC   VDD  VSS  NC   NC   NC   NC   NC   NC
  9    NC   NC   NC   NC   A15  A21  A22  A16  NC   VSS  NC   NC   NC   NC
  8    -    -    NC   A11  A12  A13  A14  NC   DQ15 DQ7  DQ14 NC   -    -
  7    -    -    NC   A8   A19  A9   A10  DQ6  DQ13 DQ12 DQ5  NC   -    -
  6    -    -    NC   /WE  CE2  A20  NC   NC   DQ4  VDD  NC   NC   -    -
  5    -    -    NC   CLK  /ADV /WAI NC   VDD  DQ3  VDD  DQ11 VDD  -    -
  4    -    -    NC   /LB  /UB  A18  A17  DQ1  DQ9  DQ10 DQ2  VSS  -    -
  3    -    -    VSS  A7   A6   A5   A4   VSS  /OE  DQ0  DQ8  NC   -    -
  2    NC   NC   NC   NC   A3   A2   A1   A0   NC   /CE1 NC   NC   NC   NC
  1 o  NC   NC   -    NC   NC   NC   VDD  VSS  NC   NC   NC   NC   NC   NC
```

DSi RAM - NEC uPD46128512 (14x10 grid):

```
       A    B    C    D    E    F    G    H    J    K    L    M    N    P
  10   NC   NC   NC   -    -    -    NC   NC   -    -    -    NC   NC   NC
  9    -    NC   NC   -    A15  A21  A22  A16  NC   VSS  -    NC   NC   -
  8    -    -    NC   A11  A12  A13  A14  NC   DQ15 DQ7  DQ14 NC   -    -
  7    -    -    -    A8   A19  A9   A10  DQ6  DQ13 DQ12 DQ5  -    -    -
  6    -    -    NC   /WE  CE2  A20  NC   NC   DQ4  VCC  NC   NC   -    -
  5    -    -    NC   CLK  /ADV /WAI NC   NC   DQ3  VCC  DQ11 NC   -    -
  4    -    -    -    /LB  /UB  A18  A17  DQ1  DQ9  DQ10 DQ2  -    -    -
  3    -    -    NC   A7   A6   A5   A4   GND  /OE  DQ0  DQ8  NC   -    -
  2    -    NC   NC   NC   A3   A2   A1   A0   NC   /CE1 -    NC   NC   -
  1 o  NC   NC   NC   -    -    -    NC   NC   -    -    -    NC   NC   NC
```

The Fujitsu & NEC datasheets are specifing 14x10 grid (the chips are
essentially pin-compatible, except that: NEC has removed some NC pins, changed
some supply pins to NC, and (attempted to) rename VSS to GND).

However, the DSi mainboard has 12x8 grid solder pads (and the installed
NEC/Fujitsu chip/packages are actually only 12x8, too).

The DSi debug version is said to have 32Mbyte RAM, there is no provision for
that feature on DSi retail boards; dev boards are probably somewhere having an
extra address line (or an extra chip select for a 2nd RAM chip).



## DSi U3 - Power Managment (Texas Instruments 72071B0, or Mitsumi 3317A)


```
  1   GND (via CL9)
  2   ADPO
  3   EXTB+
  4   VDD33
  5   RESET         ;\
  6   SPI_SCK       ; main cpu bus
  7   SPI_MOSI      ; (reset and spi)
  8   SPI_MISO      ;
  9   SPI_CS1       ;/  <-- powerman (this does ALSO connect to U4)
  10  GND
  11  PMOFF
  12  PWSWO
  13  VCNT5
  14  PM_SLP
  ---
  15  B+
  16  VDD12 via L1
  17  VDD12
  18  GND
  19  BLC1          ;\
  20  BLA1 via U13  ; backlight 1+2
  21  BLA2 via U14  ; anode/cathode
  22  BLC2          ;/
  23  GND
  24  B+
  25  B+
  26  VDD18 via L2
  27  VDD18 via L2
  28  VDD18
  ---
  29  DET     ;\battery contacts
  30  BT+     ;/    ;\these are almost shortcut
  31  VDET-         ;/with each other (via 0 ohm R71)
  32  PVDD
  33  PWSW (when off: very few ohms to PVDD ???)
  34        ... via R104 (100K) to Q3 (B+ enable or so?)
  35  B+
  36        ... via to C18 to GND (seems to have no other connection)
  37  GND
  38  AOUT  ;\to U6
  39  GND   ;
  40  SCL1  ;   ;\secondary IC2 bus (to U6)
  41  SDA1  ;/  ;/
  42  VDD33
  ---
  43  GND via CL10
  44  VDD5 input (sense if VDD5/C16 has reached voltage)
  45  charge-pump for VDD5 (L7 and via DA3 to VDD5/C16)
  46  charge-pump for VDD5 (L5 and C14)
  47  VDD33 (via CL5)
  48  VDD33 (via L3)
  49  VDD33
  50  VDD33
  51  B+
  52  B+
  53  B+
  54  charge-pump for VDD42 (L7 and C23)
  55  charge-pump for VDD42 (L7 and via D3 to VDD42/C22)
  56  VDD42 input (sense if VDD42/C22 has reached voltage)
```



## DSi U4 - Sound and Touchscreen controller (AIC3000D)


AIC3000D pinout is same as in TSC2117 datasheet (aside from GPIx/GPIOx pins).

```
  Pin TSC2117 AIC3000D
  1   MISO    SPI_MISO
  2   MOSI    SPI_MOSI
  3   /SS     SPI_CS1 (powerman, this does ALSO connect to U3)
  4   SCLK    SPI_SCLK
  5   GPIO1   SPI_CS3 (touchscreen)
  6   GPIO2   PENIRQ
  7   IOVSS   GND
  8   IOVDD   VDD33
  9   DVDD    VDD18
  10  SDOUT   SND_SDI              ;\
  11  SDIN    SND_SDO              ;
  12  WCLK    SND_WS               ; serial sound input from main cpu
  ---                              ; (and serial output? microphone maybe?)
  13  BCLK    SND_SCLK             ;
  14  MCLK    SND_MCLK             ;/
  15  SDA       ... via R107 to VDD18  ;\unused I2C bus (?)
  16  SCL       ... via R106 to VDD18  ;/
  17  VOL/M   wiper (sound volume, from I2C potentiometer) "VOL/MICDET?"
  18  MICBIAS micbias (to U18)                  ;\
  19  MIC     LIN (to U18) (and to MIC via C31) ; microphone related
  20  AUX1    aux  ;\via 0ohm R108 to U18       ;
  21  AUX2    aux  ;/(that is almost GND)       ;/
  22  AVSS    GND
  23  AVDD    VDD33
  24  VBAT    GND
  ---
  25  VREF    VDD33
  26  TSVSS   GND
  27  YN      Y-                   ;\
  28  XN      X-                   ;
  29  DVSS    GND                  ; touchscreen input
  30  YP      Y+                   ;
  31  XP      X+                   ;/
  32  TSVDD   VDD33
  33  SPLN    SPLN                 ;\
  34  SLVSS   GND                  ;
  35  SLVDD   B+                   ; speaker output
  36  SPLP    SPLP                 ;
  ---                              ;
  37  SPRN    SPRN                 ;
  38  SRVDD   B+                   ;
  39  SRVSS   GND                  ;
  40  SPRP    SPRP                 ;/
  41  HPL     SL via CP2 and R88      ;\
  42  HVDD    VDD33                   ;
  43  HVSS    GND                     ; headphone output
  44  HPR     SR via CP3 and R89      ;
  45  GPI3    MUTE via Q4/Q5 to SR/SL ;
  46  GPI2    HP#SP switch            ;/
  47  GPI1    VCNT5
  48  /RESET  RESET
```



## DSi U5 - 256Mbyte eMMC NAND (14x14 grid)


```
       1    2    3    4    5    6    7    8    9    10   11   12   13   14
  o A  NC   NC   DAT0 DAT1 DAT2 NC   NC   NC   NC   NC   NC   NC   NC   NC
    B  NC   DAT3 DAT4 DAT5 DAT6 DAT7 NC   NC   NC   NC   NC   NC   NC   NC
    C  NC   VDDI NC   VSSQ NC   VCCQ NC   NC   NC   NC   NC   NC   NC   NC
    D  NC   NC   NC   NC   -    -    -    -    -    -    -    NC   NC   NC
    E  NC   NC   NC   -    NC   VCC  VSS  NC   NC   NC   -    NC   NC   NC
    F  NC   NC   NC   -    VCC  -    -    -    -    NC   -    NC   NC   NC
    G  NC   NC   NC   -    VSS  -    -    -    -    NC   -    NC   NC   NC
    H  NC   NC   NC   -    NC   -    -    -    -    VSS  -    NC   NC   NC
    J  NC   NC   NC   -    NC   -    -    -    -    VCC  -    NC   NC   NC
    K  NC   NC   NC   -    NC   NC   NC   VSS  VCC  NC   -    NC   NC   NC
    L  NC   NC   NC   -    -    -    -    -    -    -    -    NC   NC   NC
    M  NC   NC   NC   VCCQ CMD  CLK  NC   NC   NC   NC   NC   NC   NC   NC
    N  NC   VSSQ NC   VCCQ VSSQ NC   NC   NC   NC   NC   NC   NC   NC   NC
    P  NC   NC   VCCQ VSSQ VCCQ VSSQ NC   NC   NC   NC   NC   NC   NC   NC
```

Note: The pinout follows JEDEC's eMMC standard. The "NC" pins are GNDed in DSi,
the "DAT4..DAT7" pins are not connected in DSi. The "VDDI" pin isn't wired to
VDD, instead it goes to a capacitor (0.1uF min) "for internal power stability".



## DSi U6 - "BPTWL" - I2C bus(ses), LEDs, volume, power, wifi (6x6 grid)


```
       1           2           3            4           5           6
  o A  GND         WL_TXPE     P02 button   SDA'33      ADPO        GND
    B  ATH_TX_H    BLUE(LED)   RED(LED)     SCL'33      V33         GND
    C  YELLOW(LED) VOLP button VOLN button  PM_SLP      V33'        /WIFI_RST
    D  SDA1        RESET       SCL1         to C46      GND         PMOFF
    E  VDD28       GND         CAM_LED      PWSWO       mFE         /mRST
    F  GND         AOUT        mFE'(R79)    WL_RXPE     /IRQ_O      GND
```

Aka from 78K0/KB2 datasheet...

```
       1           2           3            4           5           6
  o A  NC          P32/INT3    P30/INT1     P61/SDA     P33/INT4/T  NC
    B  P31/INT2    P16/INT5/T  P15/TOH0     P60/SCL0    EVDD        EVSS
    C  P17/T'50    P14/RxD6    P13/TxD6     P00/TI000   VDD         P121/X1
    D  P11/SI10/Rx P12/SO10    P10/SCK10/Tx REGC        VSS      P122/X2/EXCLK
    E  AVREF       AVSS        P22/ANI2     P21/ANI1    FLMD0       RESET
    F  NC          P23/ANI3    P20/ANI0  P01/TI010/TO00 P120/INT0/EXLVI  NC
```



## DSi U7 - I2C bus potentiometer (ISL95810) (Device 50h)


```
  1  /WP (DSi: VDD33)  writeprotect
  2  SCL (DSi: SCL1)   i2c bus   ;\from U6
  3  SDA (DSi: SDA1)   i2c bus   ;/
  4  GND (DSi: GND)    ground
  5  RW  (DSi: wiper)  pot.wiper ;-to U4
  6  RL  (DSi: VDD18)  pot.L
  7  RH  (DSi: GND)    pot.H
  8  VCC (DSi: VDD33)  supply
```



## DSi U8 - bidirectional I2C voltage translator (PCA9306)


```
  1  GND   (DSi: GND)
  2  VREF1 (DSi: VDD18)
  3  SCL1  (DSi: SCL)     ;\to U1 (CPU)
  4  SDA1  (DSi: SDA)     ;/
  5  SDA2  (DSi: SDA'33)  ;\to U6 (BPTWL)
  6  SCL2  (DSi: SCL'33)  ;/
  7  VREF2 (DSi: VDD33)
  8  EN    (DSi: VDD33)
```



## DSi U9 - RTC - Seiko S-35199A01 (4x3 grid)


```
       A    B    C    D
  3    CS   /SCK VDD  F32K
  2    SIO  CTRL /INT FOUT
  1 o  VSS  XIN  XOUT VDDL
```



## DSi U10 - Magnet Sensor (for hinge, aka shell opened/closed)


```
  1  VDD33
  2  R7 (HINGE)  ;to U1
  3  GND
  4  GND
```



## DSi U11 - Charge


```
  1  EXTB+
  2  Rosc
  3  ORANGE (via R2)              ;-charge LED
  4  GND
  5  TH' (via R76 to TH)          ;\thermal sensor
  6  TH  (via R102 to DPAD board) ;/for battery?
  7  B+
  8  RICHG
  9  BT+
  10 BT+
```

Note: Seems to resemble Mitsumi MM3358 datasheet.



## DSi U12 - 5pin, VDD33 to VDD28 converter? (near upper screen socket)


```
  1  VDD28
  2  GND
  3  VDD33
  4  VDD33
  5  (no pin)
  6  ... to DA6/DA7
```



## DSi U13 - 5pin, Backlight 1 (Lower Screen), near power managment chip



## DSi U14 - 5pin, Backlight 2 (Upper Screen), near power managment chip


```
  1  from U3 (wanted backlight pulse/level or so?)
  2  GND
  3  B+
  4  BLA1/BLA2 backlight anode output
  5  (no pin)
  6  B+
```



## DSi U15 - 4pin, near external power input


```
  1  via R4 to C100,Q1 (controls Q1 for forwarding VIN to EXTB+)
  2  VIN'' (from VIN via EM1 and F1)
  3  ?
  4  via C132,R14 to GND, and via D1 to VIN''
```

VIN power-input related.



## DSi U16 - N/A


None such.



## DSi U17 - Headphone Mute logic, near headphone socket


```
  1  mute (from main CPU GPIO)
  2  GND
  3  PMOFF
  4  MUTE (to Q4/Q5/TSC)
  5  VDD33
  6  ?
```



## DSi U18 - Microphone Bias, near headphone socket (not always installed)


```
  1  NC
  2  GND
  3  LIN (via C31/EM5 to MIC)
  4  aux (via 0 ohm to TSC AUX1/AUX2)
  5  VDD33
  6  micbias (from TSC micbias)
```



## DSi U19 - 5pin, something near dpad socket


```
  1  via D5/D6 from B+/VDD42
  2  GND
  3  VCNT5
  4  ?
  5  (no pin)
  6  VSHD
```

Note: Pin-numbering is unclear, here is no Pin 1 marker.



## DSi U20 - Whatever, DSi XL only (maybe magnet Sensor instead of U10?)


```
  1  ?
  2  ?
  3  ?
```



## DSi LEDs:


```
  CAM_LED (via R68 and Q13) ;Camera LED    ;\
  BLUE    (via R21 and Q11) ;Power On/Good ; from U6
  YELLOW  (via R22 and Q12) ;Wifi LED      ;/
  RED     (via R20)         ;Power On/Low  ;-from U6 (or to U6 ?)
  ORANGE  (via R2)          ;Charge LED    ;-from U11
```



## MM3218 chip (same chip as in DS Lite) (on DSi Wifi Daughterboard)


```
  1  VDD18
  2  GND
  3  VDD18
  4  Antenna signal
  5  Antenna shield
  6  VDD18
  7  VDD18
  8  GND
  9  NC
  10 GND
  11 GND
  12 GND
  13 NC
  14 /RESET
  ---
  15 CCA    ... to DSi mainboard connector pin 36
  16 WL_TXPE
  17 WL_RXPE
  18 TRRDY  ... to DSi mainboard connector pin 46 !!!
  19 TRDATA ... to DSi mainboard connector pin 40
  20 VDD33
  21 TRCLK  ... to DSi mainboard connector pin 44
  22 GND
  23 MCLK   ... via nearby big component ... to DSi mainboard connector pin 47
  24 VDD18
  25 NC
  26 22MHz
  27 22MHz'
  28 ... to DSi mainboard connector pin 43 NC? (with cap to GND and via 0 ohm)
  ---
  29 VDD33
  30 via capacitor to VDD33
  31 via 1K2 + 120K to GND (aka via 121.2K to GND)
  32 VDD18
  33 VDD18
  34 BB_RF_SCLK   ... to DSi mainboard connector pin 41
  35 BB_RF_SDI    ... to DSi mainboard connector pin 39
  36 BB_RF_SDO    ... to DSi mainboard connector pin 37
  37 BBP_SCS      ... to DSi mainboard connector pin 35
  38 RF_SCS       ... to DSi mainboard connector pin 33
  39 GND
  40 VDD33
  41 RF_SLEEP     ... to DSi mainboard connector pin 31
  42 BBP_SLEEP    ... to DSi mainboard connector pin 29
  ---
  43 VDD18
  44 ... shortcut to MM3218.pin50, and via resistor to MM3218.pin46
  45 VDD33
  46 ... via resistor to MM3218.pin44+50
  47 ... to DSi mainboard connector pin 25 (via 0 ohm) (+cap) (NC in DSi)
  48 VDD33
  49 GND
  50 ... shortcut to MM3218.pin44, and via resistor to MM3218.pin46
  51 ... via resistor to GND
  52 VDD18
  53 NC
  54 NC
  55 NC
  56 NC
```



## ROCm Atheros AR6002G-AC1B chip (on DSi DWM-W015 Wifi Daughterboard)


```
   1     2     3     4     5     6     7    8    9     10    11    12    13
 A AGND  RF2   RF2   RF2   RF2   PDET  NC   NC   VDD18 VDD12 XTAL  XTAL  BT_CLK
         OUTN  OUTP  INP   INN                   BIAS  XTAL  I     O     OUT
 B RF5   AGND  VDD18 VDD12 VDD12 BIAS  NC   NC   VDD12 VDD12 VDD18 BT_   DVDD12
   INP         FE    LNA   BIAS  REF             D_SYN BB    XTAL  CLKEN
 C RF5   VDD12 -     -     AGND  AGND  AGND AGND AGND  -     -     GPIO  GPIO
   INN   FE                                                        17    16
 D PA5   NC    -     -     -     -     -    -    -     -     -     GPIO  GPIO
   BIAS                                                            14    15
 E RF5   VDD18 AGND  -     AGND  AGND  AGND AGND DVSS  -     -     DVDD  DVDD
   OUT   VCO                                                       GPIO1 GPIO0
 F VDD12 VDD12 AGND  -     AGND  AGND  AGND AGND DVSS  -     DVSS  GPIO  GPIO
   TX5   SYNTH                                                     12    13
 G XPA   XPA   AGND  -     AGND  AGND  AGND AGND DVSS  -     DVSS  GPIO  GPIIO
   BIAS2 BIAS5                                                     10    11
 H VCCFE LDO_  AGND  -     AGND  AGND  AGND AGND DVSS  -     DVSS  GPIO  DVDD
   M     OUT                                                       9     12
 J ANTA  VDDIO AGND  -     DVSS  DVSS  DVSS DVSS DVSS  -     DVSS  CLK_  DVDD
         ANT                                                       REQ   12
 K ANTC  ANTB  -     -     -     -     -    -    -     -     -     SYS_  CHIP_
                                                                   RST_L PWD_L
 L ANTD  ANTE  -     -     DVSS  DVSS  DVSS  DVSS DVSS -     -     DVDD  DVDD_
                                                                   12    SDIO
 M AGND  GPIO0 GPIO2 DVDD  GPIO4 GPIO6 GPIO8 JTAG JTAG JTAG  SDIO_ SDIO_ SDIO_
                     12                      TMS  TCK  TDO   DATA3 DATA2 CLK
 N DVDD  GPIO1 GPIO3 DVDD_ GPIO5 GPIO7 DVDD_ DVDD JTAG DVDD_ SDIO_ SDIO_ SDIO_
   12                BT                SDIO  12   TDI  SDIO  CMD   DATA1 DATA0
```



## Atheros AR6013 chip (on DSi DWM-W024 Wifi Daughterboard)


```
  1  1.2V
  2  VDD18
  3  NC
  4  NC
  5  VDD18
  6  NC
  7  1.2V
  8  VDD18
  9  1.2V
  10 NC
  11 NC (except, wired to testpoint)
  12 VDD33
  13 via 0 ohm to ATH_TX_H  ;<--with 0 ohm connection
  14 via (N/A) to ATH_TX_H  ;<--connection not installed
  15 to a dead-end-via
  16 to a dead-end-via
  17 1.2V
  18 P5.pin24       JTAG_TRST_L     (plus testpoint)
  19 NC (except, wired to testpoint)
  ---
  20 VDD18
  21 1.2V
  22 I2C.SCL
  23 I2C.SDA
  24 P5.pin21 RTC 32KHZ via 0 ohm
  25 /WIFI_RST
  26 ATH_TX_H
  27 SDKI.CMD
  28 SDIO.CLK
  29 VDD33
  30 SDIO.DAT0
  31 SDIO.DAT2
  32 SDIO.DAT1
  33 SDIO.DAT3
  34 P5.pin22       JTAG_TCK
  35 P5.pin20       JTAG_TDI
  36 P5.pin17       JTAG_TMS
  37 1.2V
  38 P5.pin15       JTAG_TDO
  ---
  39 P5.pin36       CCA
  40 VDD33
  41 1.2V
  42 P5.pin46       TRRDY
  43 P5.pin44       TRCLK
  44 P5.pin40       TRDATA
  45 WL_TXPE
  46 WL_RXPE
  47 P5.pin47       MCLK
  48 P5.pin33       RF_SCS      ... and 6.9ohm to P5.47 ?
  49 P5.pin35       BBP_SCS
  50 P5.pin39       BB_RF_SDI
  51 VDD33
  52 P5.pin37       BB_RF_SDO
  53 P5.pin41       BB_RF_SCLK
  54 P5.pin29       BBP_SLEEP
  55 P5.pin31       RF_SLEEP
  56 P5.pin26       SEL_ATH_L   ... IRQ?
  57 1.2V
  ---
  58 VDD18
  59 XTALx
  60 XTALx
  61 1.2V
  62 1.2V
  63 VDD18
  64 NC (except, wired to testpoint)
  65 NC (except, wired to testpoint)
  66 NC (except, wired to testpoint)
  67 NC (except, wired to testpoint)
  68 NC
  69 via 6.1K to GND
  70 1.2V
  71 NC
  72 NC
  73 VDD18
  74 RF2.OUTx
  75 RF2.OUTx
  76 VDD18
  ---
  GND center plates
```

Note: /RESET connects to Wifi FLASH only, ie. NOT to the MM3218 clone within
AR6013G (that's unlike as real MM3218).



## Atheros AR6014 chip (on 3DS DWM-W028 Wifi Daughterboard) (and J27H023?)


Pinouts unknown.


There is a 3rd part number, J27H020, made by hon hai (Foxconn) instead of
Mitsumi.




# Pinouts - CPU - Signal Summary




## Advance Gameboy CPU Signal Summary


Cart Bus: D0-D7, A0-A15, /CS, /RD, /WR (different usage in GBA/DMG mode)

WRAM Bus: WA0-WA16, WD0-WD15, /WLB, /WUB, /WWE, /WOE (used in GBA mode only)

LCD Bus : LDR1-5, LDG1-5, LDB1-5, DCK, LP, PS, SPL, CLS, SPS, MOD, REVC

Joypad: TP0-3 (Buttons), TP4-7 (Directions), TP8-9 (L/R-Buttons, via R43/R44)

Serial Link: SC, SD (aka P14?), SI, SO - Audio: SO1-2, Vin

Other: CK1-2, PHI, IN35, VCNT5, /FIQ (via CL1 to VDD3), /RESET (IN), /RES (OUT)

Supply: VDD35, VDD3, VDD2, GND (some are probably undoc inputs)

GBA SP: Same as GBA, plus VDD1, plus duplicated supply pins, plus pin 152.




# Pinouts - CPU - Pinouts




## Advance Gameboy CPU Pinouts (CPU AGB)


```
  1 VDD3  17 D0   33 A0    49 WA4   65 VDD2  81 WD9   97 LDB5   113 CK1
  2 IN35  18 A15  34 /CS   50 WA5   66 WD5   82 WD1   98 LDB4   114 CK2
  3 TP8   19 A14  35 /RD   51 WA6   67 WD13  83 /WOE  99 LDB3   115 VDD2
  4 TP0   20 A13  36 /WR   52 WA7   68 WD6   84 DCK   100 LDB2  116 GND
  5 TP1   21 A12  37 PHI   53 /WLB  69 WD14  85 LP    101 LDB1  117 VDD2
  6 SO1   22 A11  38 VDD35 54 /WUB  70 WD7   86 PS    102 GND   118 VCNT5
  7 SO2   23 A10  39 GND   55 /WWE  71 WD15  87 LDR5  103 VDD3  119 TP9
  8 Vin   24 A9   40 SC    56 WA8   72 WD8   88 LDR4  104 SPL   120 TP6
  9 /RES  25 A8   41 SD    57 WA9   73 WD16  89 LDR3  105 CLS   121 TP5
  10 D7   26 A7   42 SI    58 WA10  74 WA16  90 LDR2  106 SPS   122 TP7
  11 D6   27 A6   43 SO    59 WA11  75 WD12  91 LDR1  107 MOD   123 TP4
  12 D5   28 A5   44 VDD2  60 WA12  76 WD4   92 LDG5  108 REVC  124 /FIQ
  13 D4   29 A4   45 WA0   61 WA13  77 WD11  93 LDG4  109 GNDed 125 /RESET
  14 D3   30 A3   46 WA1   62 WA14  78 WD3   94 LDG3  110 GNDed 126 TP2
  15 D2   31 A2   47 WA2   63 WA15  79 WD10  95 LDG2  111 GNDed 127 TP3
  16 D1   32 A1   48 WA3   64 GND   80 WD2   96 LDG1  112 GNDed 128 GND
```



## GBA SP CPU Pinouts (CPU AGB B)


```
  1 IN35   21 D0    41 A0    61 WA4   81 WD13  101 GND   121 LDB4  141 GND
  2 TP8    22 A15   42 /CS   62 WA5   82 WD6   102 VDD1  122 LDB3  142 VDD3
  3 TP0    23 A14   43 /RD   63 WA6   83 WD14  103 GND   123 LDB2  143 GND
  4 TP1    24 A13   44 /WR   64 WA7   84 WD7   104 VDD3  124 LDB1  144 VCNT5
  5 SO1    25 A12   45 PHI   65 /WLB  85 WD15  105 DCK   125 GND   145 TP9
  6 SO2    26 A11   46 VDD35 66 /WUB  86 WD8   106 LP    126 VDD3  146 TP6
  7 Vin    27 GND   47 GND   67 GND   87 WD16  107 PS    127 SPL   147 TP5
  8 VDD1   28 VDD35 48 SC    68 VDD2  88 WA16  108 LDR5  128 CLS   148 TP7
  9 GND    29 A10   49 SD    69 /WWE  89 VDD2  109 LDR4  129 SPS   149 TP4
  10 VDD35 30 A9    50 SI    70 WA8   90 GND   110 LDR3  130 MOD   150 /FIQ
  11 /RES  31 A8    51 SO    71 WA9   91 WD12  111 LDR2  131 REVC  151 /RESET
  12 D7    32 A7    52 VDD35 72 WA10  92 WD4   112 LDR1  132 GND   152 ?
  13 D6    33 A6    53 GND   73 WA11  93 WD11  113 LDG5  133 GND   153 TP3
  14 D5    34 A5    54 VDD1  74 WA12  94 WD3   114 LDG4  134 GND   154 TP2
  15 D4    35 A4    55 GND   75 WA13  95 WD10  115 LDG3  135 GND   155 VDD3
  16 D3    36 GND   56 VDD2  76 WA14  96 WD2   116 LDG2  136 VDD1  156 GND
  17 D2    37 VDD35 57 WA0   77 WA15  97 WD9   117 LDG1  137 GND
  18 GND   38 A3    58 WA1   78 GND   98 WD1   118 GND   138 CK1
  19 VDD35 39 A2    59 WA2   79 VDD2  99 /WOE  119 VDD3  139 CK2
  20 D1    40 A1    60 WA3   80 WD5   100 VDD2 120 LDB5  140 VDD2
```

Pin 152 seems to be not connected on the mainboard, maybe an undoc output.



## GBA-Micro, NDS, NDS-Lite Pinouts


Unknown. The CPU BGA Pins are hidden underneath of the CPU. And, in NDS and
NDS-Lite, the CPU itself hides underneath of the DS Cartridge Slot.




# Pinouts - Audio Amplifiers




## Advance Gameboy Audio Amplifier (AMP AGB IR3R60N) (U6)


```
  1   2   3   4   5   6   7   8   9   10  11  12   13   14   15   16   17  18
  C38 FR1 FR2 FL1 FL2 GND RIN LIN C39 VOL SW  VDD5 LOUT VCC3 ROUT VCC3 SP  GND
```

SW=Headphone Switch (grounded when none connected).



## GBA SP Audio Amplifier (uses AMB AGB IR3R60N, too) (U3)


Same connection as in GBA, except that pin14/16 connect to VR21 (instead VCC3),
and pin1/9 connect to different capacitors.



## NDS - National Semiconductor LM4880M Dual 250mW Audio Power Amplifier (U12)


```
  1-OUT A  2-IN A  3-BYPASS  4-GND  5-SHUTDOWN  6-IN B  7-OUT A  8-VDD.VQ5
```

NDS-Lite: No external amplifier (Mitsumi 3205B Powermanagment Device contains
internal amplifier).




# Pinouts - LCD Cables




## Advance Gameboy Display Socket


```
  1 ?     6 GND    11 LDR2   16 LDG2   21 LDB3   26 SPS     31 P2-VSS  36 V4
  2 VSHD  7 VSHD   12 LDR1   17 LDG1   22 LDB2   27 ?       32 P2-VCC  37 V3
  3 DCK   8 LDR5   13 LDG5   18 GND    23 LDB1   28 MOD     33 ?       38 V2
  4 LP    9 LDR4   14 LDG4   19 LDB5   24 SPL    29 VCOM    34 VDD5    39 V1
  5 PS    10 LDR3  15 LDG3   20 LDB4   25 CLS    30 P2-VEE  35 GND     40 V0
```



## GBA SP Display Socket


```
  1 VSHD 5 VSHD  9 LDR3   13 LDG4  17 GND   21 LDB2  25 SPS   29 P2VSS 33 U83
  2 DCK  6 GND   10 LDR2  14 LDG3  18 LDB5  22 LDB1  26 MOD   30 COM   34 VDD5
  3 LP   7 LDR5  11 LDR1  15 LDG2  19 LDB4  23 SPL   27 REVC  31 VDD5
  4 PS   8 LDR4  12 LDG5  16 LDG1  20 LDB3  24 CLS   28 P2VDD 32 GND
```



## GBA Micro Display Sockets


```
  __GBA Mirco display socket (P1)____________________________________
  1-PS    6-5bit  11-MD    16-5bit  21-5bit  26-CL             31-GND
  2-RV    7-5bit  12-SL    17-5bit  22-5bit  27-SS             32-GND
  3-GND   8-5bit  13-CK    18-5bit  23-5bit  28-via C5 to VR1  33-V10
  4-5bit  9-LP    14-GND   19-5bit  24-5bit  29-V5             34-V-5
  5-5bit  10-VD   15-5bit  20-GND   25-5bit  30-to VR1
  __GBA Mirco backlight socket (P3)__________________________________
  1-LC  2-LC  3-LA  4-LA
```



## NDS Upper/Lower Display Sockets


```
  ___NDS upper screen/upper backlight/speakers socket (P3)_____________________
  1-SPLO 7-PS2   13-LDR2  19-GND   25-LDG2  31-LDB2  37-MOD2  43-VDD15  49-SPRO
  2-SPLO 8-REV2  14-LDR1  20-DCLK2 26-LDG1  32-LDB1  38-GND   44-VDD-5  50-GND
  3-SSC2 9-GND   15-LDR0  21-GND   27-LDG0  33-LDB0  39-VDD5  45-VDD-10 51-GND
  4-ASC2 10-LDR5 16-LS2   22-LDG5  28-LDB5  34-GCK2  40-VDD10 46-LEDC2
  5-GND  11-LDR4 17-VSHD  23-LDG4  29-LDB4  35-GSP2  41-COM2  47-LEDA2
  6-SPL2 12-LDR3 18-DISP1 24-LDG3  30-LDB3  36-GND   42-GND   48-SPRO
  ___NDS lower screen socket (P4)______________________________________________
  1-SSC1 6-REV1  11-LDR2  16-DISP0 21-LDG4  26-LDB5  31-LDB0  36-GND  41-VDD15
  2-ASC1 7-GND   12-LDR1  17-SPL1  22-LDG3  27-LDB4  32-GCK1  37-?    42-VDD10
  3-GND  8-LDR5  13-LDR0  18-DCLK1 23-LDG2  28-LDB3  33-GSP1  38-VDD5 43-GND
  4-?    9-LDR4  14-LS1   19-GND   24-LDG1  29-LDB2  34-VSHD  39-COM1 44-VDD-5
  5-PS1  10-LDR3 15-VSHD  20-LDG5  25-LDG0  30-LDB1  35-MOD1  40-GND  45-VDD-10
  ___NDS lower backlight socket (P5)____   ___NDS touchscreen socket (P6)______
  1:LEDA1  2:LEDA1  3:LEDC1  4:LEDC1       1:Y-    2:X-    3:Y+    4:X+
```



## NDS-Lite Upper/Lower Display Sockets


```
  ___NDS-Lite upper screen/upper backlight/speakers socket (P3)________________
  1-VDD-5 6-MOD    11-LD2xx 16-LD2xx 21-LD2xx 26-LD2xx 31-LS   36-GND   41-SPRO
  2-VDD10 7-GSP    12-LD2xx 17-LD2xx 22-LD2xx 27-LD2xx 32-VSHD 37-COM2  42-SG
  3-VDD5  8-GCK    13-LD2xx 18-GND   23-LD2xx 28-GND   33-GND  38-LEDA2 43-SG
  4-GND   9-LD2xx  14-LD2xx 19-LD2xx 24-LD2xx 29-DCLK  34-xx2? 39-LEDC2 44-SPLO
  5-VSHD  10-LD2xx 15-LD2xx 20-LD2xx 25-LD2xx 30-SPL   35-REV  40-SPRO  45-SPLO
  ___NDS-Lite lower screen/lower backlight (P4)________________________________
  1-VDD-5 6-MOD    11-LD1xx 16-LD1xx 21-LD1xx 26-LD1xx 31-LS   36-GND
  2-VDD10 7-GSP    12-LD1xx 17-LD1xx 22-LD1xx 27-LD1xx 32-VSHD 37-COM1
  3-VDD5  8-GCK    13-LD1xx 18-GND   23-LD1xx 28-GND   33-GND  38-LEDA1
  4-GND   9-LD1xx  14-LD1xx 19-LD1xx 24-LD1xx 29-DCLK  34-xx1? 39-LEDC1
  5-VSHD  10-LD1xx 15-LD1xx 20-LD1xx 25-LD1xx 30-SPL   35-REV
  ___NDS-Lite touchscreen socket (P6)______   ___NDS-Lite white coax (P12)_____
  1:X-  2:Y-  3:X+  4:Y+                      Center:MICIN  Shield:GND
```




# Pinouts - Power Switches, DC/DC Converters, Reset Generators




## Advance Gameboy Power Switch (2-position slider, with two common pins)



## GBA SP Power Switch (same as GBA)


```
  1 via resistor to GND (OFF)
  2 VS (BT+) (ON)
  C VCC (to board)
```



## GBA Micro Power Switch


Same as GBA and GBA SP, but Pin 1 and 2 exchanged.



## Advance Gameboy Cartridge Slot Switch (integrated 4pin micro switch)



## GBA SP Cartridge Slot Switch (separate 4pin micro switch)


```
  C1 VDD35  (to S2 when PRESSED, to S1 when RELEASED)
  S1 VDD3   (to C2 when PRESSED, to C1 when RELEASED)
  C2 IN35   (to S1 when PRESSED)
  S2 VDD5   (to C1 when PRESSED)
```

Pressed=8bit DMG/MGB/CGB cart, Released=32bit GBA cart (or no cart inserted)

GBA: switch integrated in cart socket, GBA-SP: separate switch next to socket.



## Advance Gameboy Power Controller (M 121 514X) (U4)


```
  1-VIN    2-VOUT5  3-CSS5    4-VDRV5  5-GND    6-VDRV3    7-CSS3    8-VOUT3
  9-VCNT5  10-CSCP  11-REGEXT 12-VDD3  13-VDD2  14-/RESET  15-LOWBAT 16-VDD13
```

/RESET is passed to the CPU, and then forwarded to /RES pin on cart slot.



## Advance Gameboy LCD Regulator (AGB-REG IR3E09N) (U3)


```
  1  2  3    4      5   6   7   8   9   10   11  12  13  14  15  16   17     18
  ?  ?  REVC U3-COM V0  V1  ?   ?   ?   GND  ?   V2  ?   V3  V4  VDD5 U3-VDD ?
```



## GBA SP Power Controller 1 (S6403 AU227 9276) (U4)


```
  1-VCC    2-SCP1   3-SCP2 4-VDRV3 5-VOUT3/VDD3 6-VDD2  7-VOUT1/VDD1  8-VDRV1
  9-LOWBAT 10-VCNT5 11-LS5 12-?    13-GND       14-?    15-VOUT5/VDD5 16-VDRV5
```



## GBA SP Power Controller 2 (2253B 2808) (U5)


```
  1-TIN     2-U5C3     3-ADJ  4-U5VDD  5-VIN   6-?    7-U57  8-?
  9-to-C29  10-to-C30  11-?   12-GND   13-VS   14-S-  15-S+  16-U5OUT
```



## GBA Micro - Power Managment Device (U2)


- 1 via C43 to GND
- 2 via R24 to C34 to R25 back to U2.2
- 3 via C35 to GND
- 4 via C36 to GND
- 5
- 6 audio.in ? (see BP)
- 7   via C48 to GND
- 8   via R21 to C46 to C47 to C38 to R23 to phones
- 9  VL (to U4)
- 10  via R27 to C33 to C44 to C49 to R22 to phones
- 11  via C45 to GND
- 12 audio.in ? (see BP)
- 13  via C41 to GND
- 14 phones (switch)
- 15 phones (tip via R22)
- 16 phones (mid via R23)
- 17 VCS
- 18 SP
- 19 GND
- 20 LB
- 21 via C52 to GND
- 22 via C53 to GND
- 23 RS         (looks like RESET output)
- 24 to R37/C56 (looks like RESET input)
- 25
- 26
- 27 via C54 to V3
- 28 V3
- 29 GND
- 30 V3
- 31 VC
- 32 to C58
- 33 to R41/C58
- 34 GND
- 35
- 36 VC
- 37 VC
- 38
- 39 V5
- 40 GND
- 41 GND
- 42
- 43
- 44
- 45 B+
- 46 S-
- 47 S+
- 48



## GBA Micro - Volume/Backlight Level Up/Down Controller (U5)


```
  1-     5-GND  9-      13-XD      17-     21-     25-    29-
  2-     6-GND  10-     14-to U4.7 18-XR   22-CN   26-    30-
  3-     7-     11-XC   15-        19-V+   23-CNS  27-    31-BP
  4-LN   8-     12-GND  16-        20-V-   24-     28-V3  32-
```



## NDS Powermanagment Device (Mitsumi 3152A) (U3)


```
  1 R50-EXTB+        17               33 LEDC1           49 VCNT5
  2 R39-ORANGE       18               34 GND             50
  3 GND              19 VQ5           35 LEDC2           51 RST
  4                  20               36                 52
  5 Rxx-Q4           21               37 U10-LEDA2       53
  6 INS+             22 GND           38                 54
  7 INS-             23 VQ5           39 MIC.C53-AIN     55 VQ5
  8                  24               40 MIC.TSC.AUX     56 R24-SR
  9 VDET             25 VDD3.3        41 GND             57
  10 PVDD            26 GND           42 R38-RED         58 R22-SL
  11                 27 CL60-VDD3.3   43 R37-GREEN       59 GND
  12 PWSW            28 VSHD          44 VDD3.3          60 VR3.PIN2
  13                 29               45 PWM.SPI.CLK     61
  14 GND             30 VDD5          46 PWM.SPI.D       62
  15 GND             31 U9-LEDA1      47 PWM.SPI.Q       63
  16 VQ5             32               48 PWM.SPI.SEL     64 GND
```



## NDS-LITE Powermanagment Device (Mitsumi 3205B) (U3)


```
  1 SW               17               33 LEDC1           49 VCNT5
  2 R50-EXTB+        18               34 GND             50
  3 R39-ORANGE       19 VQ5           35 LEDC2           51 RST
  4 GND              20               36                 52
  5                  21               37 U10-LEDA2       53
  6 R30-Q4           22 GND           38                 54
  7 INS+             23 VQ5           39 MIC.C53-AIN     55 CL63-VQ5
  8 INS-             24               40 MIC.TSC.AUX     56 R24-SR
  9 VDET             25 VDD3.3        41 GND             57 SPRO
  10 PVDD            26 GND           42 R38-RED         58 SPLO
  11                 27 CL60-VDD3.3   43 R37-GREEN       59 R22-SL
  12 PWSW            28 VSHD          44 VDD3.3          60 GND
  13 GND             29               45 PWM.SPI.CLK     61 R79-VR3.PIN2
  14 GND             30 VDD5          46 PWM.SPI.D       62
  15 GND             31 U9-LEDA1      47 PWM.SPI.Q       63
  16 VQ5             32               48 PWM.SPI.SEL     64
```



## NDS-LITE Power Switch


```
  1 PWSW (grounded when switch is pulled)
  2 GND
  3 GND
  4 NC? (grounded when switch is not pulled)
```




# Pinouts - Wifi




## NDS RFU Daughter Board (Firmware FLASH, Wifi BB/RF Chips)


```
  1 N/A      6 FMW.CLK    11 ENABLE 16 RX.DTA? 21 BB./CS     26 22MHz   31 GND
  2 GND      7 FMW./SEL   12 GND    17 TX.MAIN 22 RF./CS     27 GND     32 GND
  3 high?    8 FMW.DTA.Q  13 GND    18 GND     23 BB.RF.CLK  28 VDD3.3  33 GND
  4 RXTX.ON  9 FMW.DTA.D  14 TX.ON  19 TX.CLK  24 BB.RF.RD   29 VDD1.8
  5 FMW./WP  10 FMW./RES  15 RX.ON  20 TX.DTA  25 BB.RF.WR   30 GND
```



## NDS-Lite RFU Daughter Board DWM-W006 (Firmware FLASH, Wifi BB/RF Chip)


```
  1 GND      6 GND       11 BB.RF.WR  16 VDD3.3   21 RF.SLEEP  26 FMW.Q
  2 TXPE     7 TRCLK     12 BB.RF.CLK 17 GND      22 FMW./RES  27 FMW./WP
  3 RXPE     8 TRDATA    13 GND       18 RF./CS   23 GND       28 FMW./CS
  4 CCA      9 GND       14 MCLK      19 BB.SLEEP 24 FMW.CLK   29 LD  ;hi?
  5 TRRDY    10 BB.RF.RD 15 GND       20 BB./CS   25 FMW.D     30 GND
```

- [https://fccid.io/EW4DWMW006/Label/ID-label-format-and-location-706511.pdf](https://fccid.io/EW4DWMW006/Label/ID-label-format-and-location-706511.pdf)


## Wifi RF Chip: RF9008, 0441, E0121Q (32 pin)


```
  1       5       9       13      17         21 RF.CLK  25        29
  2       6       10      14 GND  18         22         26        30
  3       7       11      15      19 RF.RD   23         27        31
  4       8       12      16      20 RF./CS  24         28        32
```

Pin19 RF.RD (oops, should be WR, maybe I've exchanged RD-WR?)

Pin20 RF./CS (via 10ohm)

Pin21 RF.CLK (via 10ohm)

Resembles RF2958 datasheet...?



## Wifi BB Chip: Mitsumi, Japan, 4418, MM3155 (48 pins)


```
  1 GND   7       13 GND     19      25       31         37 TX.MAIN 43
  2       8       14         20      26       32 BB./CS  38 RX.DTA? 44
  3       9       15 BB.CLK  21      27       33 TX.DTA  39 RX.ON   45 GND
  4       10      16 BB.WR   22      28 RST   34 RXTX.ON 40 TX.ON   46
  5       11      17 BB.RD   23      29       35 TX.CLK  41         47
  6       12      18 22MHz   24      30       36         42         48
```

Pin15 BB.CLK (via 10ohm to RFU.23)

Pin16 BB.WR (RFU.25)

Pin17 BB.RD (RFU.24)

Pin18 22MHz (via 50ohm)

Pin28 RST (same as FMW./RES)

Pin32 BB./CS (RFU.21)

The chip is roughly resembling HSP3824/HFA3824A/HFA3860A/HFA3860B (though
pinout and registers aren't compatible).



## NDS-LITE BB/RF-Chip Mitsumi MM3218 (56 pins)


```
  1-VDD18 8-GND   15-CCA    22-GND   29-VDD33     36-BBRF_SDO 43-VDD18 50-
  2-GND   9-NC    16-TXPE   23-MCLK  30-          37-BB_SCS   44-...   51-
  3-VDD18 10-GND  17-RXPE   24-VDD18 31-          38-RF_SCS   45-VDD33 52-VDD18
  4-Ant   11-GND  18-TRRDY  25-NC    32-VDD18     39-GND      46-...   53-NC
  5-Ant'  12-GND  19-TRDATA 26-22MHz 33-VDD18     40-VDD33    47-...   54-NC
  6-VDD18 13-NC   20-VDD33  27-22MHz 34-BBRF_SCLK 41-RF_SLEEP 48-VDD33 55-NC
  7-VDD18 14-/RES 21-TRCLK  28-      35-BBRF_SDI  42-BB_SLEEP 49-GND   56-NC
```

Note: Pinout should be same as in DSi (see DSi pinout for details).



## TX Signal/Timing Chart (Host Game)


```
  RX.DTA?  __________________________________________________________
  RXTX.ON  __-----------------------_________________________________
  RX.ON    __---_______-------------_________________________________
  TX.ON    _____-------______________________________________________
  TX.MAIN  ________----______________________________________________
  TX.CLK   _____#__####______________________________________________
  TX.DTA   _____#__####______________________________________________
```

This example shows a host sending beacons. The pre-beacon receive period is
probably to sense conflicts with other transmitters. The post-beacon receive
period is to get responses from other players. The two transmit parts are: The
hardware header, followed by inactivity on the tx pins during the rest of the
preamble period, then followed by the actual IEEE frame. The rest of the time
is spent in idle mode to reduce power consumption.



## RX Signal/Timing Chart (Join Game)


```
  RX.DTA?  __________________________________________________________
  RXTX.ON  -----------------------------------------------______-----
  RX.ON    -----------------------------------------------_________--
  TX.ON    __________________________________________________________
  TX.MAIN  __________________________________________________________
  TX.CLK   __________________________________________________________
  TX.DTA   _______________________________________________---________
```

This example shows a client trying to receive beacons, so most of the time is
spent in receive mode (the short idle periods are probably occuring when it is
switching to another channel). Once when it has associated with a host, the
client may spend more time in idle mode, and needs to be in receive mode only
when expecting to receive beacons or other data.




# Pinouts - Various




## Advance Gameboy 256Kbytes RAM 128Kx16bit (NEC D442012LGY-B85x-MJH) (wide)



## GBA SP 256Kbytes RAM 128Kx16bit (F 82D12160-10FN) (square)


```
  1 A15   7 A9    13 IC    19 A6   25 A0   31 D2   37 VCC  43 D15
  2 A14   8 A8    14 /UB   20 A5   26 /CE1 32 D10  38 D5   44 D8
  3 A13   9 NC    15 /LB   21 A4   27 GND  33 D3   39 D13  45 D16
  4 A12   10 NC   16 NC    22 A3   28 /OE  34 D11  40 D6   46 GND
  5 A11   11 /WE  17 NC    23 A2   29 D1   35 D4   41 D14  47 NC
  6 A10   12 CE2  18 A7    24 A1   30 D9   36 D12  42 D7   48 A16
```

Connection in GBA and GBA SP: IC-GND, /CE1-GND, CE2-VDD2, VCC-VDD2, Pin16-VDD2,
the other NC pins seem to be actually not connected, all other pins connect to
the corresponding Wxx CPU pins. Note: Both GBA and GBA SP have soldering points
for wide (12x18mm) and square (12x14mm) RAMs, so either could be used.

The GBA additionally contains 32K built-in WRAM, and built-in VRAM, so the
above 256K RAM chip is probably not used in 8bit classic/color gameboy mode.

Note: In the GBA Micro, the 256K RAM are contained on-chip in the CPU.



## Advance Gameboy Schematic Fragments


P2-VSS = VDD-15

VIN = VCC3 via R33

REGEXT (on my modified board, REGEXT underneath of my diodes)

/RES (OUT) (via R40)

/CS (via R39)

/WR (via R38)

SC (via Rxx)

SD (via Rxx)

SI (via Rxx)

SO (via Rxx)

DCK (via R36)

A-GND via CP4 (100uF) to GND (used speaker, and on headphone socket)



## GBA SP Schematic Fragments


P2VDD = VDD13

P2VSS = VDD15

/RES via R46

/CS via R45

/WR via R44

DCK via R20

VS=BT+

In my repaired GBA-SP: CK1 test-point is disconnected (instead GND'ed).

In my repaired GBA-SP: broken oscillator replaced

In my repaired GBA-SP: broken r1 1mOhm replaced (near oscillator)

In my repaired GBA-SP: broken EXT2 socket metal-spring/snapper removed

CL1 FIQ (near SW4)

CL2 ?

CL3 ?

CL4 VOUT1/VDD1 (near U4)

CL5 VOUT3/VDD3 (near U4)

CL6 VOUT5/VDD5 (near U4)

DL1-red (power low) ---R32--Q4--R6--

DL2-green (power good) ---Q6--LOWBAT/R34-VDD3

DL3-orange (charge) --R24--Q2--VIN/U57

P2VDD--VDD13

P2VSS--VDD15

S+ and S- are (almost) shortcut by R23 (1.0 ohm)

S+ via Q1 to VIN

VS via D1 to S-

A-GND via CP1 (100uF) to GND

U4 pin 12 to r6 (towards red led)

U4 pin 14 to D6---to U7

SC (CPU pin48) with R7 100K ohm pullup to VDD35

P35 via Q11 to SW (speaker disable)



## GBA SP Backlight-Button Schematic (U6,U8,Q12)


```
        ______                _____
  GND--|1 U8 6|-- U85        |     |--VDD5
  U82--|2    5|-- U85    U61-| Q12 |         U83  ------> to display
  U83--|3____4|-- U82        |_____|--Q12B   Q12B <------ from button
  U61--|1 U6 8|--VDD5    (X)---R51--VDD5    (X)---C70--GND
  U62--|2    7|--VDD5    U62---R49--VDD5    U61---R40--GND
  U62--|3    6|--(X)     Q12B--R39--VDD5    U82---R38--GND
  GND--|4____5|--NC?     Q12B--C69--VDD5    U85---R50--U62
```




# AUX Xboo PC-to-GBA Multiboot Cable



Below describes how to connect a PC parallel port to the GBA link port,
allowing to upload small programs (max 256 KBytes) from no$gba's Utility menu
into real GBAs.


This is possible because the GBA BIOS includes a built-in function for
downloading & executing program code even when no cartridge is inserted.
The program is loaded to 2000000h and up in GBA memory, and must contain
cartridge header information just as for normal ROM cartridges (nintendo logo,
checksum, etc., plus some additional multiboot info).



## Basic Cable Connection


The general connection is very simple (only needs four wires), the only problem
is that you need a special GBA plug or otherwise need to solder wires directly
to the GBA mainboard (see Examples below).

```
  GBA  Name  Color                 SUBD CNTR Name
  2    SO    Red     ------------- 10   10   /ACK
  3    SI    Orange  ------------- 14   14   /AUTOLF
  5    SC    Green   ------------- 1    1    /STROBE
  6    GND   Blue    ------------- 19   19   GND
```

Optionally, also connect the following signals (see notes below):

```
  4    SD    Brown   ------------- 17   36   /SELECT  (double speed burst)
  3    SI    Orange  ----[===]---- 2..9 2..9 D0..7    (pull-up, 560 Ohm)
  5    SC    Green   ----[===]---- 2..9 2..9 D0..7    (pull-up, 560 Ohm)
  4    SD    Brown   ----[===]---- 2..9 2..9 D0..7    (pull-up, 560 Ohm)
  START  (mainboard) -----|>|----- 16   31   /INIT    (auto-reset, 1N4148)
  SELECT (mainboard) -----|>|----- 16   31   /INIT    (auto-reset, 1N4148)
  RESET  (mainboard) -----||------ 16   31   /INIT    (auto-reset, 300nF)
```

Notes: The GBA Pins are arranged from left to right as 2,4,6 in upper row, and
1,3,5 in lower row; outside view of GBA socket; flat side of socket upside. The
above "Colors" are as used in most or all standard Nintendo link cables, note
that Red/Orange will be exchanged at one end in cables with crossed SO/SI
lines. At the PC side, use the SUBD pin numbers when connecting to a 25-pin
SUBD plug, or CNTR pin numbers for 36-pin Centronics plug.



## Optional SD Connection (Double Speed Burst)


The SD line is used for Double Speed Burst transfers only, in case that you are
using a gameboy link plug for the connection, and if that plug does not have a
SD-pin (such like from older 8bit gameboy cables), then you may leave out this
connection. Burst Boot will then only work half as fast though.



## Optional Pull-Ups (Improves Low-to-High Transition Speed)


If your parallel port works only with medium or slow delay settings, try to
connect 560 Ohm resistors to SI/SC/SD inputs each, and the other resistor pin
to any or all of the parallel port data lines (no$gba outputs high to pins
2..9).



## Optional Reset Connection (CAUTION: Connection changed September 2004)


The Reset connection allows to automatically reset & upload data even if a
program in the GBA has locked up (or if you've loaded a program that does not
support nocash burst boot), without having to reset the GBA manually by
switching it off and on (and without having to press Start+Select if a
cartridge is inserted).

The two diodes should be 1N4148 or similar, the capacitor should be 300nF (eg.
three 100nF capacitors in parallel). The signals are labeled on the mainboard,
and can be found at following names / CPU pin numbers: RESET/CPU.125,
SELECT/TP2/CPU.126, START/TP3/CPU.127.



## Optional Power Supply Connection


Also, you may want to connect the power supply to parallel port data lines, see
chapter Power Supply for details.



## Transmission Speed


The first transfer will be very slow, and the GBA BIOS will display the boot
logo for at least 4 seconds, even if the transfer has completed in less time.
Once when you have uploaded a program with burst boot backdoor, further
transfers will be ways faster. The table below shows transfer times for 0KByte
- 256KByte files:

```
  Boot Mode_____Delay 0_______Delay 1_______Delay 2_____
  Double Burst  0.1s - 1.8s   0.1s - 3.7s   0.1s - 5.3s
  Single Burst  0.1s - 3.6s   0.1s - 7.1s   0.1s - 10.6s
  Normal Bios   4.0s - 9.0s   4.0s - 12.7s  4.0s - 16.3s
```

All timings measured on a 66MHz computer, best possible transmission speed
should be 150KBytes/second. Timings might slightly vary depending on the CPU
speed and/or operating system. Synchronization is done by I/O waitstates, that
should work even on faster computers. Non-zero delays are eventually required
for cables without pull-ups.



## Requirements


Beside for the cable and plugs, no special requirements.

The cable should work with all parallel ports, including old-fashioned
one-directional printer ports, as well as modern bi-directional EPP ports.
Transfer timings should work stable regardless of the PCs CPU speed (see above
though), and regardless of multitasking interruptions.

Both no$gba and the actual transmission procedure are using some 32bit code, so
that either one currently requires 80386SX CPUs or above.



## Connection Examples


As far as I can imagine, there are four possible methods how to connect the
cable to the GBA. The first two methods don't require to open the GBA, and the
other methods also allow to connect optional power supply and reset signal.

```
  1) Connect it to the GBA link port. Advantage: No need to
     open/modify the GBA. Disadvantage: You need a special plug,
     (typically gained by removing it from a gameboy link cable).
  2) Solder the cable directly to the GBA link port pins. Advantages:
     No plug required & no need to open the GBA. Disadvantages:
     You can't remove the cable, and the link port becomes unusable.
  3) Solder the cable directly to the GBA mainboard. Advantage: No
     plug required at the GBA side. Disadvantage: You'll always
     have a cable leaping out of the GBA even when not using it,
     unless you put a small standard plug between GBA and cable.
  4) Install a Centronics socket in the GBA (between power switch
     and headphone socket). Advantage: You can use a standard
     printer cable. Disadvantages: You need to cut a big hole into
     the GBAs battery box (which cannot be used anymore), the big
     cable might be a bit uncomfortable when holding the GBA.
```

Personally, I've decided to use the lastmost method as I don't like ending up
with hundreds of special cables for different purposes, and asides, it's been
fun to damage the GAB as much as possible.



## Note


The above used PC parallel port signals are typically using 5V=HIGH while GBA
link ports deal with 3V=HIGH. From my experiences, the different voltages do
not cause communication problems (and do not damage the GBA and/or PC
hardware), and after all real men don't care about a handful of volts, however,
use at own risk.




# AUX Xboo Flashcard Upload




## Flashcard Upload


Allows to write data to flashcards which are plugged into GBA cartridge slot,
cartridge is automatically started after writing. On initial power-up, hold
down START+SELECT to prevent the GBA from booting the old program in the
flashcard.

The Upload function in Utility menu uses flashcard mode for files bigger than
256KB (otherwise uses multiboot mode automatically). Also, there's a separate
Upload to Flashcard function in Remote Access submenu, allowing to write files
of 256KB or less to flashcard if that should be desired.



## Supported Flashcards


Function currently tested with Visoly Flash Advance (FA) 256Mbit (32MB) Turbo
cartridge. Should also work with older FA versions. Please let me know if you
are using other flashcards which aren't yet supported.



## Flashcard Performance


Writing to flashcards may become potentially slow because of chip erase/write
times, cable transmission time, and the sheer size of larger ROM-images.
However, developers whom are testing different builts of their project usually
won't need to rewrite the complete flashcard, Xboo uses a highspeed checksum
mechanism (16MB/sec) to determine which flashcard sector(s) have changed, and
does then re-write only these sector(s).

To eliminate transmission time, data transfer takes place in the erase phases.
Erase/write time depends on the flashcard type, should be circa 1-2 seconds per
256KB sector. Because the cartridge is programmed directly in the GBA there's
no need to remove it from the GBA when writing to it.



## Developers Advice


Locate your program fragments at fixed addresses, for example, code and data
blocks each aligned to 64K memory boundaries, so that data remains at the same
location even when the size of code changes. Fill any blank spaces by value FFh
for faster write time. Reduce the size of your ROM-image by efficient memory
use (except for above alignment trick). Include the burst boot backdoor in your
program, allowing to re-write the flashcard directly without resetting the GBA.



## Lamers Advice


Xboo Flashcard support does not mean to get lame & to drop normal multiboot
support, if your program fits into 256KB then make it \<both> flashcard
\<and> multiboot compatible - multiboot reduces upload time, increases
your flashcard lifetime, and will also work for people whom don't own
flashcards.




# AUX Xboo Burst Boot Backdoor



When writing Xboo compatible programs, always include a burst boot "backdoor",
this will allow yourself (and other people) to upload programs much faster as
when using the normal GBA BIOS multiboot function. Aside from the improved
transmission speed, there's no need to reset the GBA each time (eventually
manually if you do not have reset connect), without having to press
Start+Select (if cartridge inserted), and, most important, the time-consuming
nintendo-logo intro is bypassed.



## The Burst Boot Protocol


In your programs IRQ handler, add some code that watches out for burst boot IRQ
requests. When sensing a burst boot request, download the actual boot
procedure, and pass control to that procedure.

```
  Send (PC)    Reply (GBA)
  "BRST"       "BOOT"        ;request burst, and reply <prepared> for boot
  <wait 1/16s> <process IRQ> ;long delay, allow slave to enter IRQ handler
  llllllll     "OKAY"        ;send length in bytes, reply <ready> to boot
  dddddddd     --------      ;send data in 32bit units, reply don't care
  cccccccc     cccccccc      ;exchange crc (all data units added together)
```

Use normal mode, 32bit, external clock for all transfers. The received
highspeed loader (currently approx. 180h bytes) is to be loaded to and started
at 3000000h, which will then handle the actual download operation.


Below is an example program which works with multiboot, burstboot, and as
normal rom/flashcard. The source can be assembled with a22i (the no$gba
built-in assembler, see no$gba utility menu). When using other/mainstream
assemblers, you'll eventually have to change some directives, convert numbers
from NNNh into 0xNNN format, and define the origin somewhere in linker/makefile
instead of in source code.


```
 .arm            ;select 32bit ARM instruction set
 .gba            ;indicate that it's a gameboy advance program
 .fix            ;automatically fix the cartridge header checksum
 org 2000000h    ;origin in RAM for multiboot-cable/no$gba-cutdown programs
 ;------------------
 ;cartridge header/multiboot header
  b     rom_start                ;-rom entry point
  dcb   ...insert logo here...   ;-nintento logo (156 bytes)
  dcb   'XBOO SAMPLE '           ;-title (12 bytes)
  dcb   0,0,0,0,  0,0            ;-game code (4 bytes), maker code (2 bytes)
  dcb   96h,0,0                  ;-fixed value 96h, main unit code, device type
  dcb   0,0,0,0,0,0,0            ;-reserved (7 bytes)
  dcb   0                        ;-software version number
  dcb   0                        ;-header checksum (set by .fix)
  dcb   0,0                      ;-reserved (2 bytes)
  b     ram_start                ;-multiboot ram entry point
  dcb   0,0                      ;-multiboot reserved bytes (destroyed by BIOS)
  dcb   0,0                      ;-blank padded (32bit alignment)
 ;------------------
 irq_handler:  ;interrupt handler (note: r0-r3 are pushed by BIOS)
  mov    r1,4000000h             ;\get I/O base address,
  ldr    r0,[r1,200h] ;IE/IF     ; read IE and IF,
  and    r0,r0,r0,lsr 16         ; isolate occurred AND enabled irqs,
  add    r3,r1,200h   ;IF        ; and acknowledge these in IF
  strh   r0,[r3,2]               ;/
  ldrh   r3,[r1,-8]              ;\mix up with BIOS irq flags at 3007FF8h,
  orr    r3,r3,r0                ; aka mirrored at 3FFFFF8h, this is required
  strh   r3,[r1,-8]              ;/when using the (VBlank-)IntrWait functions
  and    r3,r0,80h ;IE/IF.7 SIO  ;\
  cmp    r3,80h                  ; check if it's a burst boot interrupt
  ldreq  r2,[r1,120h] ;SIODATA32 ; (if interrupt caused by serial transfer,
  ldreq  r3,[msg_brst]           ; and if received data is "BRST",
  cmpeq  r2,r3                   ; then jump to burst boot)
  beq    burst_boot              ;/
  ;... insert your own interrupt handler code here ...
  bx     lr                      ;-return to the BIOS interrupt handler
 ;------------------
 burst_boot:     ;requires incoming r1=4000000h
  ;... if your program uses DMA, disable any active DMA transfers here ...
  ldr   r4,[msg_okay]            ;\
  bl    sio_transfer             ; receive transfer length/bytes & reply "OKAY"
  mov   r2,r0 ;len               ;/
  mov   r3,3000000h   ;dst       ;\
  mov   r4,0  ;crc               ;
 @@lop:                          ;
  bl    sio_transfer             ; download burst loader to 3000000h and up
  stmia [r3]!,r0      ;dst       ;
  add   r4,r4,r0      ;crc       ;
  subs  r2,r2,4       ;len       ;
  bhi   @@lop                    ;/
  bl    sio_transfer             ;-send crc value to master
  b     3000000h  ;ARM state!    ;-launch actual transfer / start the loader
 ;------------------
 sio_transfer:  ;serial transfer subroutine, 32bit normal mode, external clock
  str   r4,[r1,120h]  ;siodata32 ;-set reply/send data
  ldr   r0,[r1,128h]  ;siocnt    ;\
  orr   r0,r0,80h                ; activate slave transfer
  str   r0,[r1,128h]  ;siocnt    ;/
 @@wait:                         ;\
  ldr   r0,[r1,128h]  ;siocnt    ; wait until transfer completed
  tst   r0,80h                   ;
  bne   @@wait                   ;/
  ldr   r0,[r1,120h]  ;siodata32 ;-get received data
  bx    lr
 ;---
 msg_boot dcb 'BOOT'     ;\
 msg_okay dcb "OKAY"     ; ID codes for the burstboot protocol
 msg_brst dcb "BRST"     ;/
 ;------------------
 download_rom_to_ram:
  mov  r0,8000000h  ;src/rom     ;\
  mov  r1,2000000h  ;dst/ram     ;
  mov  r2,40000h/16 ;length      ; transfer the ROM content
 @@lop:                          ; into RAM (done in units of 4 words/16 bytes)
  ldmia [r0]!,r4,r5,r6,r7        ; currently fills whole 256K of RAM,
  stmia [r1]!,r4,r5,r6,r7        ; even though the proggy is smaller
  subs  r2,r2,1                  ;
  bne   @@lop                    ;/
  sub   r15,lr,8000000h-2000000h ;-return (retadr rom/8000XXXh -> ram/2000XXXh)
 ;------------------
 init_interrupts:
  mov  r4,4000000h               ;-base address for below I/O registers
  ldr  r0,=irq_handler           ;\install IRQ handler address
  str  r0,[r4,-4]   ;IRQ HANDLER ;/at 3FFFFFC aka 3007FFC
  mov  r0,0008h                  ;\enable generating vblank irqs
  strh r0,[r4,4h]   ;DISPSTAT    ;/
  mrs  r0,cpsr                   ;\
  bic  r0,r0,80h                 ; cpu interrupt enable (clear i-flag)
  msr  cpsr,r0                   ;/
  mov  r0,0                      ;\
  str  r0,[r4,134h] ;RCNT        ; init SIO normal mode, external clock,
  ldr  r0,=5080h                 ; 32bit, IRQ enable, transfer started
  str  r0,[r4,128h] ;SIOCNT      ; output "BOOT" (indicate burst boot prepared)
  ldr  r0,[msg_boot]             ;
  str  r0,[r4,120h] ;SIODATA32   ;/
  mov  r0,1                      ;\interrupt master enable
  str  r0,[r4,208h] ;IME=1       ;/
  mov  r0,81h                    ;\enable execution of vblank IRQs,
  str  r0,[r4,200h] ;IE=81h      ;/and of SIO IRQs (burst boot)
  bx   lr
 ;------------------
 rom_start:   ;entry point when booted from flashcart/rom
  bl   download_rom_to_ram       ;-download ROM to RAM (returns to ram_start)
 ram_start:   ;entry point for multiboot/burstboot
  mov  r0,0feh                   ;\reset all registers, and clear all memory
  swi  10000h ;RegisterRamReset  ;/(except program code in wram at 2000000h)
  bl   init_interrupts           ;-install burst boot irq handler
  mov  r4,4000000h               ;\enable video,
  strh r4,[r4,000h] ;DISPCNT     ;/by clearing the forced blank bit
 @@mainloop:
  swi  50000h ;VBlankIntrWait    ;-wait one frame (cpu in low power mode)
  mov  r5,5000000h               ;\increment the backdrop palette color
  str  r8,[r5]                   ; (ie. display a blinking screen)
  add  r8,r8,1                   ;/
  b    @@mainloop
 ;------------------
 .pool
 end
```




# About this Document




## About


GBATEK written 2001-2014 by Martin Korth, programming specs for the GBA and NDS
hardware, I've been trying to keep the specs both as short as possible, and as
complete as possible. The document is part of the no$gba debuggers built-in
help text.



## Updates


The standalone docs in TXT and HTM format are updated when having added any
major changes to the document. The no$gba built-in version will be updated more
regularly, including for minor changes, along with all no$gba updates.



## Homepage


- [http://problemkaputt.de/gba.htm](http://problemkaputt.de/gba.htm) - no$gba emulator homepage (freeware)

- [http://problemkaputt.de/gba-dev.htm](http://problemkaputt.de/gba-dev.htm) - no$gba debugger homepage

- [http://problemkaputt.de/gbapics.htm](http://problemkaputt.de/gbapics.htm) - no$gba debugger screenshots

- [http://problemkaputt.de/gbatek.htm](http://problemkaputt.de/gbatek.htm) - gbatek html version

- [http://problemkaputt.de/gbatek.txt](http://problemkaputt.de/gbatek.txt) - gbatek text version



## Feedback


If you find any information in this document to be misleading, incomplete, or
incorrect, please say something! My spam-shielded email address is found at:

- [http://problemkaputt.de/email.htm](http://problemkaputt.de/email.htm) - contact

Mail from programmers only, please. No gaming questions, thanks.



## Credits


Thanks for GBATEK fixes, and for info about GBA and NDS hardware,

- Jasper Vijn

- Remi Veilleux (DS video details)

- Randy Linden

- Sebastian Rasmussen

- Stephen Stair (DS Wifi)

- Cue (DS Firmware bits and bytes)

- Tim Seidel (DS Wifi RF2958 datasheet)

- Damien Good (DS Bios Dumping, and lots of e-Reader info)

- Kenobi and Dualscreenman (lots of ARDS/CBDS cheat info)

- Flubba (GBA X/Y-Axis tilt sensor, and GBA Gameboy Player info)

- DarkFader (DS Key2)

- Dstek by neimod (DS Sound)

- Christian Auby

- Jeff Frohwein

- NDSTech Wiki, 
- [http://www.bottledlight.com/ds/](http://www.bottledlight.com/ds/) (lots of DS info)

- wwylele (xpertteak cpu and mmio findings)



## Formatting


TXT is 80 columns, TXT is 80 columns, TXT is 80 columns.

Don't trust anything else. Never.
