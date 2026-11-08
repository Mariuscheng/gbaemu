# GBA Cartridges

> 本檔案整理自 [GBATEK](https://problemkaputt.de/gbatek.htm) 的「GBA Cartridges」章節。
> 來源採用 [mGBA GBATEK Markdown fork](https://github.com/mgba-emu/gbatek) 的 Markdown 轉存，保留原文的暫存器、位元欄位、程式碼與數值表示法。

# GBA Cartridges




## ROM


- [GBA Cartridge Header](#gbacartridgeheader)
- [GBA Cartridge ROM](#gbacartridgerom)


## Backup Media


Aside from ROM, cartridges may also include one of the following backup medias,
used to store game positions, highscore tables, options, or other data.

- [GBA Cart Backup IDs](#gbacartbackupids)
- [GBA Cart Backup SRAM/FRAM](#gbacartbackupsramfram)
- [GBA Cart Backup EEPROM](#gbacartbackupeeprom)
- [GBA Cart Backup Flash ROM](#gbacartbackupflashrom)
- [GBA Cart Backup DACS](#gbacartbackupdacs)


## Add-Ons


- [GBA Cart I/O Port (GPIO)](#gbacartioportgpio)
- [GBA Cart Real-Time Clock (RTC)](#gbacartrealtimeclockrtc)
- [GBA Cart Solar Sensor](#gbacartsolarsensor)
- [GBA Cart Tilt Sensor](#gbacarttiltsensor)
- [GBA Cart Gyro Sensor](#gbacartgyrosensor)
- [GBA Cart Rumble](#gbacartrumble)
- [GBA Cart e-Reader](#gbacartereader)
- [GBA Cart Unknown Devices](#gbacartunknowndevices)
- [GBA Cart Protections](#gbacartprotections)


## Other Accessoires


- [GBA Flashcards](#gbaflashcards)
- [GBA Cheat Devices](#gbacheatdevices)



# GBA Cartridge Header



The first 192 bytes at 8000000h-80000BFh in ROM are used as cartridge header.
The same header is also used for Multiboot images at 2000000h-20000BFh (plus
some additional multiboot entries at 20000C0h and up).



## Header Overview


```
  Address Bytes Expl.
  000h    4     ROM Entry Point  (32bit ARM branch opcode, eg. "B rom_start")
  004h    156   Nintendo Logo    (compressed bitmap, required!)
  0A0h    12    Game Title       (uppercase ascii, max 12 characters)
  0ACh    4     Game Code        (uppercase ascii, 4 characters)
  0B0h    2     Maker Code       (uppercase ascii, 2 characters)
  0B2h    1     Fixed value      (must be 96h, required!)
  0B3h    1     Main unit code   (00h for current GBA models)
  0B4h    1     Device type      (usually 00h) (bit7=DACS/debug related)
  0B5h    7     Reserved Area    (should be zero filled)
  0BCh    1     Software version (usually 00h)
  0BDh    1     Complement check (header checksum, required!)
  0BEh    2     Reserved Area    (should be zero filled)
  --- Additional Multiboot Header Entries ---
  0C0h    4     RAM Entry Point  (32bit ARM branch opcode, eg. "B ram_start")
  0C4h    1     Boot mode        (init as 00h - BIOS overwrites this value!)
  0C5h    1     Slave ID Number  (init as 00h - BIOS overwrites this value!)
  0C6h    26    Not used         (seems to be unused)
  0E0h    4     JOYBUS Entry Pt. (32bit ARM branch opcode, eg. "B joy_start")
```

Note: With all entry points, the CPU is initially set into system mode.



## 000h - Entry Point, 4 Bytes


Space for a single 32bit ARM opcode that redirects to the actual startaddress
of the cartridge, this should be usually a "B \<start>" instruction.

Note: This entry is ignored by Multiboot slave GBAs (in fact, the entry is then
overwritten and redirected to a separate Multiboot Entry Point, as described
below).



## 004h..09Fh - Nintendo Logo, 156 Bytes


Contains the Nintendo logo which is displayed during the boot procedure.
Cartridge won't work if this data is missing or modified.

In detail: This area contains Huffman compression data (but excluding the
compression header which is hardcoded in the BIOS, so that it'd be probably not
possible to hack the GBA by producing de-compression buffer overflows).

A copy of the compression data is stored in the BIOS, the GBA will compare this
data and lock-up itself if the BIOS data isn't exactly the same as in the
cartridge (or multiboot header). The only exception are the two entries below
which are allowed to have variable settings in some bits.



## 09Ch Bit 2,7 - Debugging Enable


This is part of the above Nintendo Logo area, and must be commonly set to 21h,
however, Bit 2 and Bit 7 may be set to other values.

When both bits are set (ie. A5h), the FIQ/Undefined Instruction handler in the
BIOS becomes unlocked, the handler then forwards these exceptions to the user
handler in cartridge ROM (entry point defined in 80000B4h, see below).

Other bit combinations currently do not seem to have special functions.



## 09Eh Bit 0,1 - Cartridge Key Number MSBs


This is part of the above Nintendo Logo area, and must be commonly set to F8h,
however, Bit 0-1 may be set to other values.

During startup, the BIOS performs some dummy-reads from a stream of pre-defined
addresses, even though these reads seem to be meaningless, they might be
intended to unlock a read-protection inside of commercial cartridge. There are
16 pre-defined address streams - selected by a 4bit key number - of which the
upper two bits are gained from 800009Eh Bit 0-1, and the lower two bits from a
checksum across header bytes 09Dh..0B7h (bytewise XORed, divided by 40h).



## 0A0h - Game Title, Uppercase Ascii, max 12 characters


Space for the game title, padded with 00h (if less than 12 chars).



## 0ACh - Game Code, Uppercase Ascii, 4 characters


This is the same code as the AGB-UTTD code which is printed on the package and
sticker on (commercial) cartridges (excluding the leading "AGB-" part).

```
  U  Unique Code          (usually "A" or "B" or special meaning)
  TT Short Title          (eg. "PM" for Pac Man)
  D  Destination/Language (usually "J" or "E" or "P" or specific language)
```

The first character (U) is usually "A" or "B", in detail:

```
  A  Normal game; Older titles (mainly 2001..2003)
  B  Normal game; Newer titles (2003..)
  C  Normal game; Not used yet, but might be used for even newer titles
  F  Famicom/Classic NES Series (software emulated NES games)
  K  Yoshi and Koro Koro Puzzle (acceleration sensor)
  P  e-Reader (dot-code scanner) (or NDS PassMe image when gamecode="PASS")
  R  Warioware Twisted (cartridge with rumble and z-axis gyro sensor)
  U  Boktai 1 and 2 (cartridge with RTC and solar sensor)
  V  Drill Dozer (cartridge with rumble)
```

The second/third characters (TT) are:

```
  Usually an abbreviation of the game title (eg. "PM" for "Pac Man") (unless
  that gamecode was already used for another game, then TT is just random)
```

The fourth character (D) indicates Destination/Language:

```
  J  Japan             P  Europe/Elsewhere   F  French          S  Spanish
  E  USA/English       D  German             I  Italian
```



## 0B0h - Maker code, Uppercase Ascii, 2 characters


Identifies the (commercial) developer. For example, "01"=Nintendo.



## 0B2h - Fixed value, 1 Byte


Must be 96h.



## 0B3h - Main unit code, 1 Byte


Identifies the required hardware. Should be 00h for current GBA models.



## 0B4h - Device type, 1 Byte


Normally, this entry should be zero. With Nintendo's hardware debugger Bit 7
identifies the debugging handlers entry point and size of DACS (Debugging And
Communication System) memory: Bit7=0: 9FFC000h/8MBIT DACS, Bit7=1:
9FE2000h/1MBIT DACS. The debugging handler can be enabled in 800009Ch (see
above), normal cartridges do not have any memory (nor any mirrors) at these
addresses though.



## 0B5h - Reserved Area, 7 Bytes


Reserved, zero filled.



## 0BCh - Software version number


Version number of the game. Usually zero.



## 0BDh - Complement check, 1 Byte


Header checksum, cartridge won't work if incorrect. Calculate as such:

chk=0:for i=0A0h to 0BCh:chk=chk-[i]:next:chk=(chk-19h) and 0FFh



## 0BEh - Reserved Area, 2 Bytes


Reserved, zero filled.


Below required for Multiboot/slave programs only. For Multiboot, the above 192
bytes are required to be transferred as header-block (loaded to
2000000h-20000BFh), and some additional header-information must be located at
the beginning of the actual program/data-block (loaded to 20000C0h and up).
This extended header consists of Multiboot Entry point(s) which must be set up
correctly, and of two reserved bytes which are overwritten by the boot
procedure:



## 0C0h - Normal/Multiplay mode Entry Point


This entry is used only if the GBA has been booted by using Normal or Multiplay
transfer mode (but not by Joybus mode).

Typically deposit a ARM-32bit "B \<start>" branch opcode at this location,
which is pointing to your actual initialization procedure.



## 0C4h (BYTE) - Boot mode


The slave GBA download procedure overwrites this byte by a value which is
indicating the used multiboot transfer mode.

```
  Value  Expl.
  01h    Joybus mode
  02h    Normal mode
  03h    Multiplay mode
```

Typically set this byte to zero by inserting DCB 00h in your source.

Be sure that your uploaded program does not contain important program code or
data at this location, or at the ID-byte location below.



## 0C5h (BYTE) - Slave ID Number


If the GBA has been booted in Normal or Multiplay mode, this byte becomes
overwritten by the slave ID number of the local GBA (that'd be always 01h for
normal mode).

```
  Value  Expl.
  01h    Slave #1
  02h    Slave #2
  03h    Slave #3
```

Typically set this byte to zero by inserting DCB 00h in your source.

When booted in Joybus mode, the value is NOT changed and remains the same as
uploaded from the master GBA.



## 0C6h..0DFh - Not used


Appears to be unused.



## 0E0h - Joybus mode Entry Point


If the GBA has been booted by using Joybus transfer mode, then the entry point
is located at this address rather than at 20000C0h. Either put your
initialization procedure directly at this address, or redirect to the actual
boot procedure by depositing a "B \<start>" opcode here (either one using
32bit ARM code). Or, if you are not intending to support joybus mode (which is
probably rarely used), ignore this entry.




# GBA Cartridge ROM




## ROM Size


The games F-ZERO and Super Mario Advance use ROMs of 4 MBytes each. Zelda uses
8 MBytes. Not sure if other sizes are manufactured.



## ROM Waitstates


The GBA starts the cartridge with 4,2 waitstates (N,S) and prefetch disabled.
The program may change these settings by writing to WAITCNT, the games F-ZERO
and Super Mario Advance use 3,1 waitstates (N,S) each, with prefetch enabled.

Third-party flashcards are reportedly running unstable with these settings.
Also, prefetch and shorter waitstates are allowing to read more data and
opcodes from ROM is less time, the downside is that it increases the power
consumption.



## ROM Chip


Because of how 24bit addresses are squeezed through the Gampak bus, the
cartridge must include a circuit that latches the lower 16 address bits on
non-sequential access, and that increments these bits on sequential access.
Nintendo includes this circuit directly in the ROM chip.

Also, the ROM must have 16bit data bus (or a circuit which converts two 8bit
data units into one 16bit unit - by not exceeding the waitstate timings).




# GBA Cart Backup IDs



Nintendo didn't include a backup-type entry in the ROM header, however, the
required type can be detected by ID strings in the ROM-image. Nintendo's tools
are automatically inserting these strings (as part of their library headers).
When using other tools, you may insert ID strings by hand.



## ID Strings


The ID string must be located at a word-aligned memory location, the string
length should be a multiple of 4 bytes (padded with zero's).

```
  EEPROM_Vnnn    EEPROM 512 bytes or 8 Kbytes (4Kbit or 64Kbit)
  SRAM_Vnnn      SRAM 32 Kbytes (256Kbit)
  FLASH_Vnnn     FLASH 64 Kbytes (512Kbit) (ID used in older files)
  FLASH512_Vnnn  FLASH 64 Kbytes (512Kbit) (ID used in newer files)
  FLASH1M_Vnnn   FLASH 128 Kbytes (1Mbit)
```

For Nintendo's tools, "nnn" is a 3-digit library version number. When using
other tools, best keep it set to "nnn" rather than inserting numeric digits.



## Notes


No$gba does auto-detect most backup types, even without ID strings, except for
128K FLASH (without ID "FLASH1M\_Vnnn", the FLASH size defaults to 64K).
Ideally, for faster detection, the ID should be put into the first some bytes
of the ROM-image (ie. somewhere right after the ROM header).




# GBA Cart Backup SRAM/FRAM



SRAM - 32 KBytes (256Kbit) Lifetime: Depends on back-up battery

FRAM - 32 KBytes (256Kbit) Lifetime: 10,000,000,000 read/write per bit


Hyundai GM76V256CLLFW10 SRAM (Static RAM) (eg. F-Zero)

Fujitsu MB85R256 FRAM (Ferroelectric RAM) (eg. Warioware Twisted)



## Addressing and Waitstates


SRAM/FRAM is mapped to E000000h-E007FFFh, it should be accessed with 8
waitstates (write a value of 3 into Bit0-1 of WAITCNT).



## Databus Width


The SRAM/FRAM databus is restricted to 8 bits, it should be accessed by LDRB,
LDRSB, and STRB opcodes only.



## Reading and Writing


Reading from SRAM/FRAM should be performed by code executed in WRAM only (but
not by code executed in ROM). There is no such restriction for writing.



## Preventing Data Loss


The GBA SRAM/FRAM carts do not include a write-protect function (unlike older
8bit gameboy carts). This seems to be a problem and may cause data loss when a
cartridge is removed or inserted while the GBA is still turned on. As far as I
understand, this is not so much a hardware problem, but rather a software
problem, ie. theoretically you could remove/insert the cartridge as many times
as you want, but you should take care that your program does not crash (and
write blindly into memory).



## Recommended Workaround


Enable the Gamepak Interrupt (it'll most likely get triggered when removing the
cartridge), and hang-up the GBA in an endless loop when your interrupt handler
senses a Gamepak IRQ. For obvious reason, your interrupt handler should be
located in WRAM, ie. not in the (removed) ROM cartridge. The handler should
process Gamepak IRQs at highest priority. Periods during which interrupts are
disabled should be kept as short as possible, if necessary allow nested
interrupts.



## When to use the above Workaround


A program that relies wholly on code and data in WRAM, and that does not crash
even when ROM is removed, may keep operating without having to use the above
mechanism.

Do NOT use the workaround for programs that run without a cartridge inserted
(ie. single gamepak/multiboot slaves), or for programs that use Gamepak IRQ/DMA
for other purposes.

All other programs should use it. It'd be eventually a good idea to include it
even in programs that do not use SRAM/FRAM themselves (eg. otherwise removing a
SRAM/FRAM-less cartridge may lock up the GBA, and may cause it to destroy
backup data when inserting a SRAM/FRAM cartridge).



## SRAM vs FRAM


FRAM (Ferroelectric RAM) is a newer technology, used in newer GBA carts, unlike
SRAM (Static RAM), it doesn't require a battery to hold the data. At software
side, it is accessed exactly like SRAM, ie. unlike EEPROM/FLASH, it doesn't
require any Write/Erase commands/delays.



## Note


In SRAM/FRAM cartridges, the /REQ pin (Pin 31 of Gamepak bus) should be a
little bit shorter as than the other pins; when removing the cartridge, this
causes the gamepak IRQ signal to get triggered before the other pins are
disconnected.




# GBA Cart Backup EEPROM



9853 - EEPROM 512 Bytes (0200h) (4Kbit) (eg. used by Super Mario Advance)

9854 - EEPROM 8 KBytes (2000h) (64Kbit) (eg. used by Boktai)

Lifetime: 100,000 writes per address



## Addressing and Waitstates


The eeprom is connected to Bit0 of the data bus, and to the upper 1 bit (or
upper 17 bits in case of large 32MB ROM) of the cartridge ROM address bus,
communication with the chip takes place serially.

The eeprom must be used with 8 waitstates (set WAITCNT=X3XXh; 8,8 clks in WS2
area), the eeprom can be then addressed at DFFFF00h..DFFFFFFh.

Respectively, with eeprom, ROM is restricted to 8000000h-9FFFeFFh (max.
1FFFF00h bytes = 32MB minus 256 bytes). On carts with 16MB or smaller ROM,
eeprom can be alternately accessed anywhere at D000000h-DFFFFFFh.



## Data and Address Width


Data can be read from (or written to) the EEPROM in units of 64bits (8 bytes).
Writing automatically erases the old 64bits of data. Addressing works in units
of 64bits respectively, that is, for 512 Bytes EEPROMS: an address range of
0-3Fh, 6bit bus width; and for 8KByte EEPROMs: a range of 0-3FFh, 14bit bus
width (only the lower 10 address bits are used, upper 4 bits should be zero).



## Set Address (For Reading)


Prepare the following bitstream in memory:

```
  2 bits "11" (Read Request)
  n bits eeprom address (MSB first, 6 or 14 bits, depending on EEPROM)
  1 bit "0"
```

Then transfer the stream to eeprom by using DMA.



## Read Data


Read a stream of 68 bits from EEPROM by using DMA,

then decipher the received data as follows:

```
  4 bits - ignore these
 64 bits - data (conventionally MSB first)
```



## Write Data to Address


Prepare the following bitstream in memory, then transfer the stream to eeprom
by using DMA, it'll take ca. 108368 clock cycles (ca. 6.5ms) until the old data
is erased and new data is programmed.

```
  2 bits "10" (Write Request)
  n bits eeprom address (MSB first, 6 or 14 bits, depending on EEPROM)
 64 bits data (conventionally MSB first)
  1 bit "0"
```

After the DMA, keep reading from the chip, by normal LDRH [DFFFF00h], until Bit
0 of the returned data becomes "1" (Ready). To prevent your program from
locking up in case of malfunction, generate a timeout if the chip does not
reply after 10ms or longer.



## Using DMA


Transferring a bitstreams to/from the EEPROM must be done via DMA3 (manual
transfers via LDRH/STRH won't work; probably because they don't keep /CS=LOW
and A23=HIGH throughout the transfer).

For using DMA, a buffer in memory must be used (that buffer would be typically
allocated temporarily on stack, one halfword for each bit, bit1-15 of the
halfwords are don't care, only bit0 is used).

The buffer must be transfered as a whole to/from EEPROM by using DMA3 (DMA0-2
can't access external memory), use 16bit transfer mode, both source and
destination address incrementing (ie. DMA3CNT=80000000h+length).

DMA channels of higher priority should be disabled during the transfer (ie.
H/V-Blank or Sound FIFO DMAs). And, of course any interrupts that might mess
with DMA registers should be disabled.



## Pin-Outs


The EEPROM chips are having only 8 pins, these are connected, Pin 1..8, to
ROMCS, RD, WR, AD0, GND, GND, A23, VDD of the GamePak bus. Carts with 32MB ROM
must have A7..A22 logically ANDed with A23.

The chips seem to be some custom design, the pinout, transfer protocol and
8-byte pages don't resemble any standard serial EEPROMs.

The chips have no other markings than 9853 or 9854 (plus some datecode),
without any manufacturer info (
- [https://gbhwdb.gekkio.fi/](https://gbhwdb.gekkio.fi/) declares them as Rohm chips).



## Notes


There seems to be no autodection mechanism, so that a hardcoded bus width must
be used.




# GBA Cart Backup Flash ROM



64 KBytes - 512Kbits Flash ROM - Lifetime: 10,000 writes per sector

128 KBytes - 1Mbit Flash ROM - Lifetime: ??? writes per sector



## Chip Identification (all device types)


```
  [E005555h]=AAh, [E002AAAh]=55h, [E005555h]=90h  (enter ID mode)
  dev=[E000001h], man=[E000000h]                  (get device & manufacturer)
  [E005555h]=AAh, [E002AAAh]=55h, [E005555h]=F0h  (terminate ID mode)
```

Used to detect the type (and presence) of FLASH chips. See Device Types below.



## Reading Data Bytes (all device types)


```
  dat=[E00xxxxh]                                  (read byte from address xxxx)
```



## Erase Entire Chip (all device types)


```
  [E005555h]=AAh, [E002AAAh]=55h, [E005555h]=80h  (erase command)
  [E005555h]=AAh, [E002AAAh]=55h, [E005555h]=10h  (erase entire chip)
  wait until [E000000h]=FFh (or timeout)
```

Erases all memory in chip, erased memory is FFh-filled.



## Erase 4Kbyte Sector (all device types, except Atmel)


```
  [E005555h]=AAh, [E002AAAh]=55h, [E005555h]=80h  (erase command)
  [E005555h]=AAh, [E002AAAh]=55h, [E00n000h]=30h  (erase sector n)
  wait until [E00n000h]=FFh (or timeout)
```

Erases memory at E00n000h..E00nFFFh, erased memory is FFh-filled.



## Erase-and-Write 128 Bytes Sector (only Atmel devices)


```
  old=IME, IME=0                                  (disable interrupts)
  [E005555h]=AAh, [E002AAAh]=55h, [E005555h]=A0h  (erase/write sector command)
  [E00xxxxh+00h..7Fh]=dat[00h..7Fh]               (write 128 bytes)
  IME=old                                         (restore old IME state)
  wait until [E00xxxxh+7Fh]=dat[7Fh] (or timeout)
```

Interrupts (and DMAs) should be disabled during command/write phase. Target
address must be a multiple of 80h.



## Write Single Data Byte (all device types, except Atmel)


```
  [E005555h]=AAh, [E002AAAh]=55h, [E005555h]=A0h  (write byte command)
  [E00xxxxh]=dat                                  (write byte to address xxxx)
  wait until [E00xxxxh]=dat (or timeout)
```

The target memory location must have been previously erased.



## Terminate Command after Timeout (only Macronix devices, ID=1CC2h)


```
  [E005555h]=F0h                            (force end of write/erase command)
```

Use if timeout occurred during "wait until" periods, for Macronix devices only.



## Bank Switching (devices bigger than 64K only)


```
  [E005555h]=AAh, [E002AAAh]=55h, [E005555h]=B0h  (select bank command)
  [E000000h]=bnk                                  (write bank number 0..1)
```

Specifies 64K bank number for read/write/erase operations.

Required because gamepak flash/sram addressbus is limited to 16bit width.



## Device Types


Nintendo puts different FLASH chips in commercial game cartridges. Developers
should thus detect & support all chip types. For Atmel chips it'd be
recommended to simulate 4K sectors by software, though reportedly Nintendo
doesn't use Atmel chips in newer games anymore. Also mind that different
timings should not disturb compatibility and performance.

```
  ID     Name       Size  Sectors  AverageTimings  Timeouts/ms   Waits
  D4BFh  SST        64K   16x4K    20us?,?,?       10,  40, 200  3,2
  1CC2h  Macronix   64K   16x4K    ?,?,?           10,2000,2000  8,3
  1B32h  Panasonic  64K   16x4K    ?,?,?           10, 500, 500  4,2
  3D1Fh  Atmel      64K   512x128  ?,?,?           ...40..,  40  8,8
  1362h  Sanyo      128K  ?        ?,?,?           ?    ?    ?    ?
  09C2h  Macronix   128K  ?        ?,?,?           ?    ?    ?    ?
```

Identification Codes MSB=Device Type, LSB=Manufacturer.

Size in bytes, and numbers of sectors \* sector size in bytes.

Average medium Write, Erase Sector, Erase Chips timings are unknown?

Timeouts in milliseconds for Write, Erase Sector, Erase Chips.

Waitstates for Writes, and Reads in clock cycles.



## Accessing FLASH Memory


FLASH memory is located in the "SRAM" area at E000000h..E00FFFFh, which is
restricted to 16bit address and 8bit data buswidths. Respectively, the memory
can be accessed \<only> by 8bit read/write LDRB/STRB opcodes.

Also, reading anything (data or status/busy information) can be done
\<only> by opcodes executed in WRAM (not from opcodes in ROM) (there's no
such restriction for writing).



## FLASH Waitstates


Use 8 clk waitstates for initial detection (WAITCNT Bits 0,1 both set). After
detection of certain device types smaller wait values may be used for
write/erase, and even smaller wait values for raw reading, see Device Types
table.

In practice, games seem to use smaller values only for write/erase (even though
those operations are slow anyways), whilst raw reads are always done at 8 clk
waits (even though reads could actually benefit slightly from smaller wait
values).



## Verify Write/Erase and Retry


Even though device signalizes the completion of write/erase operations, it'd be
recommended to read/confirm the content of the changed memory area by software.
In practice, Nintendo's "erase-write-verify-retry" function typically repeats
the operation up to three times in case of errors.

Also, for SST devices only, the "erase-write" and "erase-write-verify-retry"
functions repeat the erase command up to 80 times, additionally followed by one
further erase command if no retries were needed, otherwise followed by six
further erase commands.



## Note


FLASH (64Kbytes) is used by the game Sonic Advance, and possibly others.




# GBA Cart Backup DACS



128 KBytes - 1Mbit DACS - Lifetime: 100,000 writes.

1024 KBytes - 8Mbit DACS - Lifetime: 100,000 writes.


DACS (Debugging And Communication System) is used in Nintendo's hardware
debugger only, DACS is NOT used in normal game cartridges.


Parts of DACS memory is used to store the debugging exception handlers (entry
point/size defined in cartridge header), the remaining memory could be used to
store game positions or other data. The address space is the upper end of the
32MB ROM area, the memory can be read directly by the CPU, including for
ability to execute program code in this area.




# GBA Cart I/O Port (GPIO)



4bit General Purpose I/O Port (GPIO) - contained in the ROM-chip


Used by Boktai for RTC and Solar Sensor:

- [GBA Cart Real-Time Clock (RTC)](#gbacartrealtimeclockrtc)
- [GBA Cart Solar Sensor](#gbacartsolarsensor)
And by Warioware Twisted for Rumble and Z-Axis Sensor:

- [GBA Cart Rumble](#gbacartrumble)
- [GBA Cart Gyro Sensor](#gbacartgyrosensor)
Might be also used by other games for other purposes, such like other sensors,
or SRAM bank switching, etc.


The I/O registers are mapped to a 6-byte region in the ROM-area at 80000C4h,
the 6-byte region should be zero-filled in the ROM-image. In Boktai, the size
of the zero-filled region is 0E0h bytes - that probably due to an incorrect
definition (the additional bytes do not contain any extra ports, nor mirrors of
the ports in the 6-byte region). Observe that ROM-bus writes are limited to
16bit/32bit access (STRB opcodes are ignored; that, only in DS mode?).



## 80000C4h - I/O Port Data (selectable W or R/W)


```
  bit0-3  Data Bits 0..3 (0=Low, 1=High)
  bit4-15 not used (0)
```



## 80000C6h - I/O Port Direction (for above Data Port) (selectable W or R/W)


```
  bit0-3  Direction for Data Port Bits 0..3 (0=In, 1=Out)
  bit4-15 not used (0)
```



## 80000C8h - I/O Port Control (selectable W or R/W)


```
  bit0    Register 80000C4h..80000C8h Control (0=Write-Only, 1=Read/Write)
  bit1-15 not used (0)
```

In write-only mode, reads return 00h (or possible other data, if the rom
contains non-zero data at that location).



## Connection Examples


```
  GPIO       | Boktai  | Wario
  Bit Pin    | RTC SOL | GYR RBL
  -----------+---------+---------
  0   ROM.1  | SCK CLK | RES -
  1   ROM.2  | SIO RST | CLK -
  2   ROM.21 | CS  -   | DTA -
  3   ROM.22 | -   FLG | -   MOT
  -----------+---------+---------
  IRQ ROM.43 | IRQ -   | -   -
```


Aside from the I/O Port, the ROM-chip also includes an inverter (used for
inverting the RTC /IRQ signal), and some sort of an (unused) address decoder
output (which appears to be equal or related to A23 signal) (ie. reacting on
ROM A23, or SRAM D7, which share the same pin on GBA slot).




# GBA Cart Real-Time Clock (RTC)



S3511 - 8pin RTC with 3-wire serial bus (used in Boktai)


The RTC chip is (almost) the same as used in NDS consoles:

- [DS Real-Time Clock (RTC)](ds.html#dsrealtimeclockrtc)
The chip is accessed via 4bit I/O port (only 3bits are used for RTC):

- [GBA Cart I/O Port (GPIO)](#gbacartioportgpio)


## Comparision of RTC Registers


```
  NDS_________GBA_________GBA/Params___
  stat2       control     (1-byte)
  datetime    datetime    (7-byte)
  time        time        (3-byte)
  stat1       force reset (0-byte)
  clkadjust   force irq   (0-byte)
  alarm1/int1 always FFh  (boktai contains code for writing 1-byte to it)
  alarm2      always FFh  (unused)
  free        always FFh  (unused)
```



## Control Register


```
  Bit Dir Expl.
  0   -   Not used
  1   R/W IRQ duty/hold related?
  2   -   Not used
  3   R/W Per Minute IRQ (30s duty)        (0=Disable, 1=Enable)
  4   -   Not used
  5   R/W Unknown?
  6   R/W 12/24-hour Mode                  (0=12h, 1=24h) (usually 1)
  7   R   Power-Off (auto cleared on read) (0=Normal, 1=Failure, time lost)
```

Setting after Battery-Shortcut is 82h. Setting after Force-Reset is 00h.

Unused bits seem to be always zero, but might be read-only or write-only?



## Datetime and Time Registers


Same as NDS, except AM/PM flag moved from hour.bit6 (NDS) to hour.bit7 (GBA).



## Force Reset/Irq Registers


Used to reset all RTC registers (all used registers become 00h, except
day/month which become 01h), or to drag the IRQ output LOW for a short moment.
These registers are strobed by ANY access to them, ie. by both writing to, as
well as reading from these registers.



## RTC Games


```
  Boktai series     ;which/how many titles?
  P-Letter series   ;which/how many titles?
  Rockman EXE 4.5 Real Operation
```



## Pin-Outs / IRQ Signal


The package has identical pin-outs as in NDS, although it is slightly larger
than the miniature chip in the DS.

For whatever reason, the RTC's /IRQ output is passed through an inverter
(contained in the ROM-chip), the inverted signal is then passed to the /IRQ pin
on the cartridge slot. So, IRQ's will be triggered on the "wrong" edge -
possible somehow in relation with detecting cartridge-removal IRQs?




# GBA Cart Solar Sensor



Uses a Photo Diode as Solar Sensor (used in Boktai, allowing to defeat vampires
when the cartridge is exposed to sunlight). The cartridge comes in transparent
case, and it's slightly longer than normal carts, so the sensor reaches out of
the cartridge slot. According to the manual, the sensor works only with
sunlight, but actually it works with any strong light source (eg. a 100 Watt
bulb at 1-2 centimeters distance). The sensor is accessed via 4bit I/O port
(only 3bits used), which is contained in the ROM-chip.

- [GBA Cart I/O Port (GPIO)](#gbacartioportgpio)


## A/D Conversion


The cartridge uses a self-made digital-ramp converter A/D converter, which is
(maybe) better than measuring a capacitor charge-up time, and/or less expensive
than a real ADC-chip:

It contains a 74LV4040 12bit binary counter (clocked by CPU via the I/O port),
of which only the lower 8bit are used, which are passed to a resistor
ladder-type D/A converter, which is generating a linear increasing voltage,
which is passed to a TLV272 voltage comparator, which is passing a signal to
the I/O port when the counter voltage becomes greater than the sensor voltage.



## Example Code


```
  strh  0001h,[80000c8h] ;-enable R/W mode
  strh  0007h,[80000c6h] ;-init I/O direction
  strh  0002h,[80000c4h] ;-reset counter to zero (high=reset) (I/O bit0)
  strh  0000h,[80000c4h] ;-clear reset (low=normal)
  mov   r0,0             ;-initial level
 @@lop:
  strh  0001h,[80000c4h] ;-clock high ;\increase counter      (I/O bit1)
  strh  0000h,[80000c4h] ;-clock low  ;/
  ldrh  r1,[80000c4h]    ;-read port                          (I/O bit3)
  tst   r1,08h           ;\
  addeq r0,1             ; loop until voltage match (exit with r0=00h..FFh),
  tsteq r0,100h          ; or until failure/timeout (exit with r0=100h)
  beq   @@lop            ;/
```

The results vary depending on the clock rate used. In above example, ensure
that IRQs or DMAs do not interrupt the function. Alternately, use a super-slow
clock rate (eg. like 666Hz used in Boktai) so that additional small IRQ/DMA
delays have little effect on the overall timing. Results should be somewhat:

```
  E8h  total darkness (including LED light, or daylight on rainy days)
  Dxh  close to a 100 Watt Bulb
  5xh  reaches max level in boktai's solar gauge
  00h  close to a tactical nuclear bomb dropped on your city
```

The exact values may change from cartridge to cartridge, so it'd be recommened
to include a darkness calibration function, prompting the user to cover the
sensor for a moment (in Boktai, access Options by pressing left/right in title
screen) (alternately, auto-calibration could theoretically memorize the darkest
in-game level ever seen).




# GBA Cart Tilt Sensor



Yoshi's Universal Gravitation / Yoshi Topsy Turvy (X/Y-Axis)

Koro Koro Puzzle (probably same as Yoshi, X/Y-Axis, too) (?)



## Yoshi-Type (X/Y-Axis)


All of the registers are one byte wide, mapped into the top "half" of the SRAM
memory range.

```
  E008000h (W) Write 55h to start sampling
  E008100h (W) Write AAh to start sampling
  E008200h (R) Lower 8 bits of X axis
  E008300h (R) Upper 4 bits of X axis, and Bit7: ADC Status (0=Busy, 1=Ready)
  E008400h (R) Lower 8 bits of Y axis
  E008500h (R) Upper 4 bits of Y axis
```

You must set SRAM wait control to 8 clocks to access it correctly.

You must also set the cartridge PHI terminal to 4 MHz to make it work.

Sampling routine (typically executed once a frame during VBlank):

```
  wait until [E008300h].Bit7=1 or until timeout ;wait ready
  x = ([E008300h] AND 0Fh)*100h + [E008200h]    ;get x
  y = ([E008500h] AND 0Fh)*100h + [E008400h]    ;get y
  [E008000h]=55h, [E008100h]=AAh                ;start next conversion
```

Example values (may vary on different carts and on temperature, etc):

```
  X ranged between 0x2AF to 0x477, center at 0x392.    Huh?
  Y ranged between 0x2C3 to 0x480, center at 0x3A0.    Huh?
```

Thanks to Flubba for Yoshi-Type information.

Unknown if the Yoshi-Type sensors are sensing rotation, or orientation, or
motion, or something else? In case of rotation, rotation around X-axis would
result in motion in Y-direction, so not too sure whether X and Y have which
meaning?

Most probably, the sensors are measuring (both) static acceleration (gravity),
and dynamic acceleration (eg. shaking the device left/right).

The X/Y values are likely to be mirrored depending on using a back-loading
cartridge slot (original GBA), or front-loading cartridge slot (newer GBA SP,
and NDS, and NDS-Lite).




# GBA Cart Gyro Sensor



Warioware Twisted (Z-Axis Gyro Sensor, plus Rumble)



## Wario-Type (Z-Axis)


Uses a single-axis sensor, which senses rotation around the Z-axis. The sensor
is connected to an analogue-in, serial-out ADC chip, which is accessed via
lower 3 bits of the GPIO,

- [GBA Cart I/O Port (GPIO)](#gbacartioportgpio)
The four I/O Lines are connected like so,

```
  GPIO.Bit0 (W) Start Conversion
  GPIO.Bit1 (W) Serial Clock
  GPIO.Bit2 (R) Serial Data
  GPIO.Bit3 (W) Used for Rumble (not gyro related)
```

There should be at least \<three sequential 32bit ARM opcodes executed in WS0
region> between the STRH opcodes which toggle the CLK signal. Wario uses
WAITCNT=45B7h (SRAM=8clks, WS0/WS1/WS2=3,1clks, Prefetch=On, PHI=Off).

The data stream consists of: 4 dummy bits (usually zero), followed by 12 data
bits, followed by endless unused bits (usually zero).

```
 read_gyro:
  mov  r1,8000000h      ;-cartridge base address
  mov  r0,01h           ;\enable R/W access
  strh r0,[r1,0c8h]     ;/
  mov  r0,0bh           ;\init direction (gpio2=input, others=output)
  strh r0,[r1,0c6h]     ;/
  ldrh r2,[r1,0c4h]     ;-get current state (for keeping gpio3=rumble)
  orr  r2,3                     ;\
  strh r2,[r1,0c4h] ;gpio0=1    ; start ADC conversion
  bic  r2,1                     ;
  strh r2,[r1,0c4h] ;gpio0=0    ;/
  mov  r0,00010000h ;stop-bit           ;\
  bic  r2,2                             ;
 @@lop:                                 ;
  ldrh r3,[r1,0c4h] ;get gpio2=data     ; read 16 bits
  strh r2,[r1,0c4h] ;gpio1=0=clk=low    ; (4 dummy bits, plus 12 data bits)
  movs r3,r3,lsr 3  ;gpio2 to cy=data   ;
  adcs r0,r0,r0     ;merge data, cy=done;
  orr  r3,r2,2      ;set bit1 and delay ;
  strh r3,[r1,0c4h] ;gpio1=1=clk=high   ;
  bcc  @@lop                            ;/
  bic  r0,0f000h                 ;-strip upper 4 dummy bits (isolate 12bit adc)
  bx   lr
```

Example values (may vary on different carts, battery charge, temperature, etc):

```
  354h  rotated in anti-clockwise direction (shock-speed)
  64Dh  rotated in anti-clockwise direction (normal fast)
  6A3h  rotated in anti-clockwise direction (slow)
  6C0h  no rotation                         (stopped)
  6DAh  rotation in clockwise direction     (slow)
  73Ah  rotation in clockwise direction     (normal fast)
  9E3h  rotation in clockwise direction     (shock-speed)
```

For detection, values 000h and FFFh would indicate that there's no sensor.

The Z-axis always points into same direction; no matter of frontloading or
backloading cartridge slots.

Thanks to Momo Vampire for contributing a Wario cartridge.



## X/Y/Z-Axes


X-Axis and Y-Axis are meant to be following the screens X and Y coordinates, so
the Z-Axis would point into the screens depth direction.



## DSi Cameras


DSi consoles can mis-use the built-in cameras as Gyro sensor (as done by the
System Flaw DSi game).




# GBA Cart Rumble



Warioware Twisted (Rumble, plus Z-Axis Gyro Sensor)

Drill Dozer (Rumble only) \<-- and ALSO supports Gameboy Player rumble?


GBA Rumble Carts are containing a small motor, which is causing some vibration
when/while it is switched on (that, unlike DS Rumble, which must be repeatedly
toggled on/off).


In Warioware Twisted, rumble is controlled via GPIO.Bit3 (Data 0=Low=Off,
1=High=On) (and Direction 1=Output), the other GPIO Bits are used for the gyro
sensor.

- [GBA Cart I/O Port (GPIO)](#gbacartioportgpio)
Note: GPIO3 is connected to an external pulldown resistor (so the HighZ level
gets dragged to Low=Off when direction is set to Input).


Unknown if Drill Dozer is controlled via GPIO.Bit3, too?



## DS Rumble Pak


Additionally, there's a Rumble Pak for the NDS, which connects to the GBA slot,
so it can be used also for GBA games (provided that the game doesn't require
the GBA slot, eg. GBA multiboot games).

- [DS Cart Rumble Pak](ds.html#dscartrumblepak)


## Gamecube Rumble


Moreover, GBA games that are running on a Gameboy Player are having access to
the Rumble function of Gamecube joypads.

- [GBA Gameboy Player](#gbagameboyplayer)



# GBA Cart e-Reader



- [GBA Cart e-Reader Overview](#gbacartereaderoverview)
- [GBA Cart e-Reader I/O Ports](#gbacartereaderioports)
- [GBA Cart e-Reader Dotcode Format](#gbacartereaderdotcodeformat)
- [GBA Cart e-Reader Data Format](#gbacartereaderdataformat)
- [GBA Cart e-Reader Program Code](#gbacartereaderprogramcode)
- [GBA Cart e-Reader API Functions](#gbacartereaderapifunctions)
- [GBA Cart e-Reader VPK Decompression](#gbacartereadervpkdecompression)
- [GBA Cart e-Reader Error Correction](#gbacartereadererrorcorrection)
- [GBA Cart e-Reader File Formats](#gbacartereaderfileformats)

```
   ________________
  |   ShortStrip   |
  |L              L|
  |o    Center    o|
  |n    Region    n|
  |g              g|
  |  may contain   |
  |S   pictures,  S|
  |t instructions t|
  |r     etc.     r|
  |i              i|
  |p              p|
  |___ShortStrip___|
```




# GBA Cart e-Reader Overview



The e-Reader is a large GBA cartridge (about as big as the GBA console), with
built-in dotcode scanning hardware. Dotcodes are tiny strips of black and white
pixels printed on the edges of cardboard cards. The cards have to be pulled
through a slot on the e-Reader, which is giving it a feeling like using a
magnet card reader. The binary data on the dotcodes contains small games,
either in native GBA code (ARM/THUMB), or in software emulated 8bit Z80 or
NES/Famicom (6502) code.



## The e-Reader Hardware


The hardware consists of regular 8MByte ROM and 128KByte FLASH chips, two link
ports, a custom PGA chip, the camera module (with two red LEDs, used as light
source), and some analogue components for generating the LED voltages, etc. The
camera supports 402x302 pixels with 7bit monochrome color depth, but the PGA
clips it to max 320 pixels per scanline with 1bit color depth.



## Link Port Plug/Socket


The e-Reader's two link ports are simply interconnected with each other;
without connection to the rest of the e-Reader hardware. These ports are used
only on the original GBA (where the large e-Reader cartridge would be covering
the GBA's link socket). When trying to insert the e-Reader into an original NDS
(or GBA-Micro), then the e-Reader's link plug will hit against the case of the
NDS, so it works only with some minor modification to the hardware. There's no
such problem with GBA-SP and NDS-Lite.



## Region/Version


There are 3 different e-Reader's: Japanese/Original, Japanese/Plus, and
Non-Japanese. The Original version has only 64K FLASH, no Link Port, and
reportedly supports only Z80 code, but no NES/GBA code. The Plus and
Non-Japanese versions should be almost identical, except that they reject cards
from the wrong region, and that the title strings aren't ASCII in Japan, the
Plus version should be backwards compatible to the Original one.



## The Problem


Nintendo's current programmers are definetly unable to squeeze a Pac-Man style
game into less than 4MBytes. Their solution has been: MORE memory. That is,
they've put a whopping 8MByte BIOS ROM into the e-Reader, which contains the
User Interface, and software emulation for running some of their 20 years old
8bit NES and Game&Watch titles, which do fit on a few dotcode strips.




# GBA Cart e-Reader I/O Ports




## DF80000h Useless Register (R/W)


```
  0     Output to PGA.Pin93 (which seems to be not connected to anything)
  1-3   Unknown, read/write-able (not used by e-Reader BIOS)
  4-15  Always zero (0)
```



## DFA0000h Reset Register (R/W)


```
  0    Always zero              (0)
  1    Reset Something?         (0=Normal, 1=Reset)
  2    Unknown, always set      (1)
  3    Unknown, read/write-able (not used by e-Reader BIOS)
  4-7  Always zero              (0)
  8    Unknown, read/write-able (not used by e-Reader BIOS)
  9-15 Always zero              (0)
```



## DFC0000h..DFC0027h Scanline Data (R)


Scanline data (40 bytes, for 320 pixels, 1bit per pixel, 0=black, 1=white).

The first (leftmost) pixel is located in the LSB of the LAST byte.

Port E00FFB1h.Bit1 (and [4000202h].Bit13) indicates when a new scanline is
present, the data should be then transferred to RAM via DMA3 (SAD=DFC0000h,
DAD=buf+y\*28h, CNT=80000014h; a slower non-DMA transfer method would result in
missed scanlines). After the DMA, software must reset E00FFB1h.Bit1.

Note: The scanning resolution is 1000 DPI.



## DFC0028h+(0..2Fh\*2) Brightest Pixels of 8x6 Blocks (R)


```
  0-6  Max Brightness (00h..7Fh; 00h=All black, 7Fh=One or more white)
  7-15 Always zero
```

Can be used to adjust the Port E00FF80h..E00FFAFh settings.



## DFC0088h Darkest Pixel of whole Image (R)


```
  0-7  Max Darkness   (00h..7Fh; 00h=One or more black, 7Fh=All white)
  8-15 Always zero
```

Can be used to adjust the Port E00FF80h..E00FFAFh settings.



## E00FF80h..E00FFAFh Intensity Boundaries for 8x6 Blocks (R/W)


The 320x246 pixel camera input is split into 8x6 blocks (40x41 pixels each),
with Block00h=Upper-right, Block07h=Upper-left, ..., Block27h=Lower-left. The
boundary values for the separate blocks are used for 128-grayscale to 2-color
conversion, probably done like "IF Pixel>Boundary THEN white ELSE black".

```
  0-6  Block Intensity Boundaries (0..7Fh; 7Fh=Whole block gets black)
  7    Always zero
```

The default boundary values are stored in FLASH memory, the values are
typically ranging from 28h (outer edges) to 34h (center image), that in respect
to the light source (the two LEDs are emitting more light to the center
region).



## E00FFB0h Control Register 0 (R/W)


```
  0    Serial Data       (Low/High)
  1    Serial Clock      (Low/High)
  2    Serial Direction  (0=Input, 1=Output)
  3    Led/Irq Enable    (0=Off, 1=On; Enable LED and Gamepak IRQ)
  4    Start Scan        (0=Off, 1=Start) (0-to-1 --> Resync line 0)
  5    Phi 16MHz Output  (0=Off, 1=On; Enable Clock for Camera, and for LED)
  6    Power 3V Enable   (0=Off, 1=On; Enable 3V Supply for Camera)
  7    Not used          (always 0) (sometimes 1) (Read only)
```



## E00FFB1h Control Register 1 (R/W)


```
  0    Not used          (always 0)
  1    Scanline Flag     (1=Scanline Received, 0=Acknowledge)
  2-3  Not used          (always 0)
  4    Strange Bit       (0=Normal, 1=Force Resync/Line0 on certain interval?)
  5    LED Anode Voltage (0=3.0V, 1=5.1V; requires E00FFB0h.Bit3+5 to be set)
  6    Not used          (always 0)
  7    Input from PGA.Pin22, always high (not used by e-Reader) (Read Only)
```

Bit1 can be SET by hardware only, software can only RESET that bit, the Gamepak
IRQ flag (Port 4000202h.Bit13) becomes set on 0-to-1 transitions.



## E00FFB2h Light Source LED Kathode Duration (LSB) (R/W)



## E00FFB3h Light Source LED Kathode Duration (MSB) (R/W)


Selects the LED Kathode=LOW Duration, aka the LED=ON Duration. That does act as
pulse width modulated LED brightness selection (the camera seems to react
slowly enough to view the light as being dimmed to medium, rather than seeing
the actual light ON and OFF states). The PWM timer seems to be clocked at 8MHz.
The hardware clips timer values 2000h..FFFFh to max 2000h (=1ms). Additionally,
the e-Reader BIOS clips values to max 11B3h. Default setting is found in FLASH
calibration data. A value of 0000h disables the LED.



## Serial Port Registers (Camera Type 1) (DV488800) (calib\_data[3Ch]=1)


All 16bit values are ordered MSB,LSB. All registers are whole 8bit
Read/Write-able, except 00h,57h-5Ah (read only), and 53h-55h (2bit only).

```
  Port     Expl.               (e-Reader Setting)
  00h      Maybe Chip ID (12h) (not used by e-Reader BIOS) (Read Only)
  01h                          (05h)    ;-Bit0: 1=auto-repeat scanning?
  02h                          (0Eh)
  10h-11h  Vertical Scroll     (calib_data[30h]+7)
  12h-13h  Horizontal Scroll   (0030h)
  14h-15h  Vertical Size       (00F6h=246)
  16h-17h  Horizontal Size     (0140h=320)
  20h-21h  H-Blank Duration    (00C4h)
  22h-23h                      (0400h)  ;-Upper-Blanking in dot-clock units?
  25h                          (var)    ;-bit1: 0=enable [57h..5Ah] ?
  26h                          (var)    ;\maybe a 16bit value
  27h                          (var)    ;/
  28h                          (00h)
  30h      Brightness/contrast (calib_data[31h]+/-nn)
  31h-33h                      (014h,014h,014h)
  34h      Brightness/contrast (02h)
  50h-52h  8bit Read/Write     (not used by e-Reader BIOS)
  53h-55h  2bit Read/Write     (not used by e-Reader BIOS)
  56h      8bit Read/Write     (not used by e-Reader BIOS)
  57h-58h  16bit value, used to autodetect/adjust register[30h] (Read Only)
  59h-5Ah  16bit value, used to autodetect/adjust register[30h] (Read Only)
  80h-FFh  Mirrors of 00h..7Fh (not used by e-Reader BIOS)
```

All other ports are unused, writes to those ports are ignored, and reads are
returning data mirrored from other ports; that is typically data from 2 or more
ports, ORed together.



## Serial Port Registers (Camera Type 2) (calib\_data[3Ch]=2)


All 16bit values are using more conventional LSB,MSB ordering, and port numbers
are arranged in a more reasonable way. The e-Reader BIOS doesn't support (or
doesn't require) brightness adjustment for this camera module.

```
  Port     Expl.             (e-Reader Setting)
  00h                        (22h)
  01h                        (50h)
  02h-03h  Vertical Scroll   (calib_data[30h]+28h)
  04h-05h  Horizontal Scroll (001Eh)
  06h-07h  Vertical Size     (00F6h)    ;=246
  08h-09h  Horizontal Size   (0140h)    ;=320
  0Ah-0Ch                    (not used by e-Reader BIOS)
  0Dh                        (01h)
  0Eh-0Fh                    (01EAh)    ;=245*2
  10h-11h                    (00F5h)    ;=245
  12h-13h                    (20h,F0h)  ;maybe min/max values?
  14h-15h                    (31h,C0h)  ;maybe min/max values?
  16h                        (00h)
  17h-18h                    (77h,77h)
  19h-1Ch                    (30h,30h,30h,30h)
  1Dh-20h                    (80h,80h,80h,80h)
  21h-FFh                    (not used by e-Reader BIOS)
```

This appears to be a Micron (aka Aptina) camera (resembling the DSi cameras).

My own e-Reader uses a Type 1 camera module. Not sure if Nintendo has ever
manufactured any e-Readers with Type 2 cameras?



## Calibration Data in FLASH Memory (Bank 0, Sector 0Dh)


```
  E00D000 14h  ID String ('Card-E Reader 2001',0,0)
  E00D014 2    Sector Checksum (NOT(x+x/10000h); x=sum of all other halfwords)
```

Begin of actual data (40h bytes)

```
  E00D016 8x6  [00h] Intensity Boundaries for 8x6 blocks ;see E00FF80h..AFh
  E00D046 1    [30h] Vertical scroll (0..36h)  ;see type1.reg10h/type2.reg02h
  E00D047 1    [31h] Brightness or contrast    ;see type1.reg30h
  E00D048 2    [32h] LED Duration              ;see E00FFB2h..B3h
  E00D04A 2    [34h] Not used?   (0000h)
  E00D04C 2    [36h] Signed value, related to adjusting the 8x6 blocks
  E00D04E 4    [38h] Not used?   (00000077h)
  E00D052 4    [3Ch] Camera Type (0=none,1=DV488800,2=Whatever?)
```

Remaining bytes in this Sector...

```
  E00D056 FAAh Not used (zerofilled) (included in above checksum)
```



## Flowchart for Overall Camera Access


ereader\_scan\_camera:

```
 call ereader_power_on
 call ereader_initialize
 for z=1 to number_of_frames
  for y=0 to 245
   Wait until E00FFB1h.Bit1 gets set by hardware (can be handled by IRQ)
   Copy 14h halfwords from DFC0000h to buf+y*28h via DMA3
   Reset E00FFB1h.Bit1 by software
  next y
  ;(could now check DFC0028h..DFC0086h/DFC0088h for adjusting E00FF00h..2Fh)
  ;(could now show image on screen, that may require to stop/pause scanning)
 next z
 call ereader_power_off
 Ret
```

ereader\_power\_on:

```
 [4000204h]=5803h   ;Init waitstates, and enable Phi 16MHz
 [DFA0000h].Bit1=1
 Wait(10ms)
 [E00FFB0h]=40h     ;Enable Power3V and reset other bits
 [DFA0000h].Bit1=0
 [E00FFB1h]=20h     ;Enable Power5V and reset other bits
 Wait(40ms)
 [E00FFB1h].Bit4=0  ;...should be already 0 ?
 [E00FFB0h]=40h+27h ;Phi16MHz=On, SioDtaClkDir=HighHighOut
 Ret
```

ereader\_power\_off:

```
 [E00FFB0h]=04h    ;Power3V=Off, Disable Everything, SioDtaClkDir=LowLowOut
 [DFA0000h].Bit1=0 ;...should be already 0
 [E00FFB1h].Bit5=0 ;Power5V=Off
 Ret
```

ereader\_initialize:

```
 IF calib_data[3Ch] AND 03h = 1 THEN init_camera_type1
 [E00FFB0h].Bit4=1 ;ScanStart
 IF calib_data[3Ch] AND 03h = 2 THEN init_camera_type2
 Copy calib_data[00h..2Fh] to [E00FF80h+00h..2Fh]  ;Intensity Boundaries
 Copy calib_data[32h..33h] to [E00FFB2h+00h..01h]  ;LED Duration LSB,MSB
 [E00FFB0h].Bit3=1                                 ;LedIrqOn
 Ret
```

init\_camera\_type1:

```
 x=MIN(0,calib_data[31h]-0Bh)
 Set Sio Registers (as shown for Camera Type 1, except below values...)
 Set Sio Registers [30h]=x [25h]=04h, [26h]=58h, [27h]=6Ch
 ;(could now detect/adjust <x> based on Sio Registers [57h..5Ah])
 Set Sio Registers [30h]=x [25h]=06h, [26h]=E8h, [27h]=6Ch
 Ret
```

init\_camera\_type2:

- Wait(0.5ms)
- Set Sio Registers (as shown for Camera Type 2)
- Ret



## Accessing Serial Registers via E00FFB0h


```
      Begin   Write(A) Write(B) Read(C) Read(D) End     Idle    PwrOff
  Dir ooooooo ooooooo  ooooooo  iiiiiii iiiiiii ooooooo ooooooo ooooooo
  Dta ---____ AAAAAAA  BBBBBBB  xxxxxCx xxxxxDx ______- ------- _______
  Clk ------_ ___---_  ___---_  ___---_ ___---_ ___---- ------- _______
```



## Flowchart for accessing Serial Registers via E00FFB0h (looks like I2C bus)


- Delay:
  - Wait circa 2.5us, Ret
- SioBegin:
  - SioDta=1, SioDir=Out, SioClk=1, Delay, SioDta=0, Delay, SioClk=0, Ret
- SioEnd:
  - SioDta=0, SioDir=Out, Delay, SioClk=1, Delay, SioDta=1, Ret
- SioRead1bit:   ;out: databit
  - SioDir=In, Delay, SioClk=1, Delay, databit=SioDta, SioClk=0, Ret
- SioWrite1bit:  ;in: databit
  - SioDta=databit, SioDir=Out, Delay, SioClk=1, Delay, SioClk=0, Ret
- SioReadByte:   ;in: endflag - out: data
  - for i=7 to 0, data.bit\<i>=SioRead1bit, next i, SioWrite1bit(endflag), Ret
- SioWriteByte:  ;in: data - out: errorflag
  - for i=7 to 0, Delay(huh/why?), SioWrite1bit(data.bit\<i>), next i
  - errorflag=SioRead1bit, SioDir=Out(huh/why?), Ret
- SioWriteRegisters:  ;in: index, len, buffer
  - SioBegin
  - SioWriteByte(22h)        ;command (set\_index) (and write\_data)
  - SioWriteByte(index)      ;index
  - for i=0 to len-1
    - SioWriteByte(buffer[i]) ;write data (and auto-increment index)
  - next
  - SioEnd
  - ret
- SioReadRegisters:   ;in: index, len - out: buffer
  - SioBegin
  - SioWriteByte(22h)        ;command (set\_index) (without any write\_data here)
  - SioWriteByte(index)      ;index
  - SioBegin
  - SioWriteByte(23h)        ;command (read\_data) (using above index)
  - for i=0 to len-1
    - if i=len-1 then endflag=1 else endflag=0
    - buffer[i]=SioReadByte(endflag)  ;read data (and auto-increment index)
  - next
  - SioEnd
  - Ret

Caution: Accessing the SIO registers appears highly unstable, and seems to
require error handling with retries. Not sure what is causing that problem,
possibly the registers cannot be accessed during camera-data-scans...?



## WAITCNT


The e-Reader BIOS uses WAITCNT [4000204h]=5803h when accessing the PGA, that
is, gamepak 16.78MHz phi output (bit11-12=3), 8 waits for SRAM region
(bit0-1=3), gamepak prefetch enabled (bit14=1), also sets WS0 to 4,2 waits
(bit2-4=0), and sets WS2 to odd 4,8 waits (bit8-10=0). The WS2 (probably WS0
too) settings are nonsense, and should work with faster timings (the e-Reader
can be accessed in NDS mode, which doesn't support that slow timings).



## e-Reader Memory and I/O Map (with all used/unused/mirrored regions)


```
  C000000h-C7FFFFFh  ROM (8MB)
  C800000h-DF7FFFFh  Open Bus
  DF80000h-DF80001h  Useless Register (R/W)
  DF80002h-DF9FFFFh  Mirrors of DF80000h-DF80001h
  DFA0000h-DFA0001h  Reset Register (R/W)
  DFA0002h-DFBFFFFh  Mirrors of DFA0000h-DFA0001h
  DFC0000h-DFC0027h  Scanline Data (320 Pixels) (R)
  DFC0028h-DFC0087h  Brightest Pixels of 8x6 Blocks (R)
  DFC0088h           Darkest Pixel of whole Image (R)
  DFC0089h-DFC00FFh  Always zero
  DFC0100h-DFDFFFFh  Mirrors of DFC0000h-DFC00FFh
  DFE0000h-DFFFFFFh  Open Bus
  E000000h-E00CFFFh  FLASH Bank 0 - Data
  E00D000h-E00DFFFh  FLASH Bank 0 - Calibration Data
  E00E000h-E00EFFFh  FLASH Bank 0 - Copy of Calibration Data
  E00F000h-E00FF7Fh  FLASH Bank 0 - Unused region
  E000000h-E00EFFFh  FLASH Bank 1 - Data
  E00F000h-E00FF7Fh  FLASH Bank 1 - Unused region
  E00FF80h-E00FFAFh  Intensity Boundaries for 8x6 Blocks (R/W)
  E00FFB0h           Control Register 0 (R/W)
  E00FFB1h           Control Register 1 (R/W)
  E00FFB2h-E00FFB3h  LED Duration (16bit) (R/W)
  E00FFB4h-E00FFBFh  Always zero
  E00FFC0h-E00FFFFh  Mirror of E00FF80h-E00FFBFh
```

Mind that WS2 should be accessed by LDRH/STRH, and SRAM region by LDRB/STRB.

Additionally about 32 serial bus registers are contained in the camera module.



## Camera Module Notes


The Type 1 initial setting on power-on is 402x302 pixels, the e-Reader uses
only 320x246 pixels. The full vertical resolution could be probably used
without problems. Port DFC0000h-DFC0027h are restricted to 320 pixels, so
larger horizontal resolutions could be probably obtained only by changing the
horizontal scroll offset on each 2nd scan.

The camera output is 128 grayscales (via parallel 7bit databus), but the PGA
converts it to 2 colors (1bit depth). For still images, it might be possible to
get 4 grayshades via 3 scans with different block intensity boundary settings.

No idea if the camera supports serial commands other than 22h and 23h. Namely,
it \<would> be a quite obvious and basic feature to allow to receive the
bitmap via the 2-wire serial bus (alternately to the 7bit databus), if
supported, it'd allow to get 7bit images, bypassing 1bit PGA conversion.

When used as actual camera (by cutting an opening in the case), the main
problem is the 1bit color depth, which allows only black and white schemes,
when/if solving that problem, focusing might be also a problem.


Either the camera or the PGA seem to have a problem on white-to-black
transitions in vertical direction, the upper some black pixels are sorts of
getting striped or dithered. For example, scanning the large sync marks appears
as:

```
  Actual Shape    Scanned Shape
     XXXXX            X  X
    XXXXXXX           X  X X
   XXXXXXXXX        X X  X XX
   XXXXXXXXX        X X  X XX
    XXXXXXX          XXXXXXX
     XXXXX            XXXXX
```

That appears only on large black shapes (the smaller data dots look better).
Probably the image is scanned from bottom upwards (and the camera senses only
the initial transition at the bottom, and then looses track of what it is
doing).




# GBA Cart e-Reader Dotcode Format



Resolution is 342.39 DPI (almost 10 blocks per inch).

Resolution is 134.8 dots/cm (almost 4 blocks per centimeter).

The width and height of each block, and the spacing to the bottom edge of the
card is ca. 1/10 inch, or ca. 4 millimeters.


```
   XXX            BLOCK 1             XXX            BLOCK 2             XXX
  XXXXX                              XXXXX                              XXXXX
  XXXXX   X X X X X X  X X X X X X   XXXXX   X X X X X X  X X X X X X   XXXXX
  XXXXX                              XXXXX                              XXXXX
   XXX   HHHHHHHHHHHHHHHHHHHH......   XXX   HHHHHHHHHHHHHHHHHHHH......   XXX
         ..........................         ..........................
         ...... 3 short lines .....         ..........................
    A..................................A..................................A..
    A....      26 long lines       ....A........ X = Sync Marks   ........A..
    A....  (each 34 data dots)     ....A........ H = Block Header ........A..
    A....(not all lines shown here)....A........ . = Data Bits    ........A..
    A..................................A........ A = Address Bits ........A..
         ...... 3 short lines .....         ..........................
         ...(each 26 data dots)....         ..........................
   XXX   ..........................   XXX   ..........................   XXX
  XXXXX                              XXXXX                              XXXXX
  XXXXX   X X X X X X  X X X X X X   XXXXX   X X X X X X  X X X X X X   XXXXX
  XXXXX                              XXXXX                              XXXXX
   XXX                                XXX                                XXX
             <ca. 35 blank lines>
  ___Snip____________________________________________________________________
```



## Address Columns


Each Column consists of 26 dots. From top to bottom: 1 black dot, 8 blank dots,
16 address dots (MSB topmost), and 1 blank dot. The 16bit address values can be
calculated as:

```
  addr[0] = 03FFh
  for i = 1 to 53
    addr[i] = addr[i-1] xor ((i and (-i)) * 769h)
    if (i and 07h)=0 then addr[i] = addr[i] xor (769h)
    if (i and 0Fh)=0 then addr[i] = addr[i] xor (769h*2)
    if (i and 1Fh)=0 then addr[i] = addr[i] xor (769h*4) xor (769h)
  next i
```

Short strips use addr[1..19], long strips use addr[25..53], left to right.



## Block Header


The 18h-byte Block Header is taken from the 1st two bytes (20 dots) of the 1st
0Ch blocks (and is then repeated in the 1st two bytes of further blocks).

```
  00h      Unknown              (00h)
  01h      Dotcode type         (02h=Short, 03h=Long)
  02h      Unknown              (00h)
  03h      Address of 1st Block (01h=Short, 19h=Long)
  04h      Total Fragment Size  (40h) ;64 bytes per fragment, of which,
                                      ;48 bytes are actual data, the remaining
  05h      Error-Info Size      (10h) ;16 bytes are error-info
  06h      Unknown              (00h)
  07h      Interleave Value     (1Ch=Short, 2Ch=Long)
  08h..17h 16 bytes Reed-solomon error correction info for Block Header
```



## Data 4-Bit to 5-bit Conversion


In the Block Header (HHHHH), and Data Region (.....), each 4bit are expanded to
5bit, so one byte occupies 10 dots, and each block (1040 data dots) contains
104 bytes.

```
  4bit  00h 01h 02h 03h 04h 05h 06h 07h 08h 09h 0Ah 0Bh 0Ch 0Dh 0Eh 0Fh
  5bit  00h 01h 02h 12h 04h 05h 06h 16h 08h 09h 0Ah 14h 0Ch 0Dh 11h 10h
```

That formatting ensures that there are no more than two continous black dots
(in horizontal direction), neither inside of a 5bit value, nor between two 5bit
values, however, the address bars are violating that rule, and up to 5
continous black dots can appear at the (..A..) block boundaries.



## Data Order


Data starts with the upper bit of the 5bit value for the upper 4bit of the
first byte, which is located at the leftmost dot of the upper line of the
leftmost block, it does then extend towards rightmost dot of that block, and
does then continue in the next line, until reaching the bottom of the block,
and does then continue in the next block. The 1st two bytes of each block
contain a portion of the Block Header, the remaining 102 bytes in each block
contain data.



## Data Size


A long strip consists of 28 blocks (28\*104 = 2912 bytes), a short strip of 18
blocks (18\*104 = 1872 bytes). Of which, less than 75% can be actually used for
program code, the remaining data contains error correction info, and various
headers. See Data Format for more info.



## Interleaved Fragments


The Interleave Value (I) specifies the number of fragments, and does also
specify the step to the next byte inside of a fragment; except that, at the
block boundaries (every 104 bytes), the step is 2 bigger (for skipping the next
two Block Header bytes).

```
  RAW Offset  Content
  000h..001h  1st 2 bytes of RAW Header
  002h        1st byte of 1st fragment
  003h        1st byte of 2nd fragment
  ...         ...
  002h+I-1    1st byte of last fragment
  002h+I      2nd byte of 1st fragment
  003h+I      2nd byte of 2nd fragment
  ...         ...
  002h+I*2-1  2nd byte of last fragment
  ...         ...
```

Each fragment consists of 48 actual data bytes, followed by 16 error correction
bytes, followed by 0..2 unused bytes (since I\*40h doesn't exactly match
num\_blocks\*102).




# GBA Cart e-Reader Data Format




## Data Strip Format


The size of the data region is I\*48 bytes (I=Interleave Value, see Dotcode
Format), the first 48-byte fragment contains the Data Header, the remaining
(I-1) fragments are Data Fragments (which contain title(s), and VPK compressed
program code).



## First Strip


```
  Data Header  (48 bytes)
  Main-Title   (17 bytes, or 33 bytes)
  Sub-Title(s) (3+18 bytes, or 33 bytes) (for each strip) (optional)
  VPK Size     (2 byte value, total length of VPK Data in ALL strips)
  NULL Value   (4 bytes, contained ONLY in 1st strip of GBA strips)
  VPK Data     (length as defined in VPK Size entry, see above)
```



## Further Strip(s)


```
  Data Header  (48 bytes)
  Main-Title   (17 bytes, or 33 bytes)
  Sub-Title(s) (3+18 bytes, or 33 bytes) (for each strip) (optional)
  VPK Data     (continued from previous strip)
```



## Data Header (30h bytes) (1st fragment)


```
  00h-01h  Fixed         (00h,30h)
  02h      Fixed         (01h)     ;01h="Do not calculate Global Checksum" ?
  03h      Primary Type  (see below)
  04h-05h  Fixed         (00h,01h) (don't care)
  06h-07h  Strip Size    (0510h=Short, 0810h=Long Strip) ((I-1)*30h) (MSB,LSB)
  08h-0Bh  Fixed         (00h,00h,10h,12h)
  0Ch-0Dh  Region/Type   (see below)
  0Eh      Strip Type    (02h=Short Strip, 01h=Long Strip) (don't care)
  0Fh      Fixed         (00h) (don't care)
  10h-11h  Unknown       (whatever) (don't care)
  12h      Fixed         (10h)     ;10h="Do calculate Data Checksum" ?
  13h-14h  Data Checksum (see below) (MSB,LSB)
  15h-19h  Fixed         (19h,00h,00h,00h,08h)
  1Ah-21h  ID String     ('NINTENDO')
  22h-25h  Fixed         (00h,22h,00h,09h)
  26h-29h  Size Info     (see below)
  2Ah-2Dh  Flags         (see below)
  2Eh      Header Checksum (entries [0Ch-0Dh,10h-11h,26h-2Dh] XORed together)
  2Fh      Global Checksum (see below)
```

Primary Type [03h] is 8bit,

```
  0      Card Type (upper bit) (see below)
  1      Unknown (usually opposite of Bit0) (don't care)
  2-7    Unknown (usually zero)
```

Region/Type [0Ch..0Dh] is 16bit,

```
  0-3    Unknown (don't care)
  4-7    Card Type (lower bits) (see below)
  8-11   Region/Version (0=Japan/Original, 1=Non-japan, 2=Japan/Plus)
  12-15  Unknown (don't care)
```

Size Info [26h-29h] is 32bit,

```
  0      Unknown            (don't care)
  1-4    Strip Number       (01h..Number of strips)
  5-8    Number of Strips   (01h..0Ch) (01h..08h for Japan/Original version)
  9-23   Size of all Strips (excluding Headers and Main/Sub-Titles)
         (same as "VPK Size", but also including the 2-byte "VPK Size" value,
         plus the 4-byte NULL value; if it is present)
  24-31  Fixed              (02h) (don't care)
```

Flags [2Ah-2Dh] is 32bit,

```
  0      Permission to save (0=Start Immediately, 1=Prompt for FLASH Saving)
  1      Sub-Title Flag     (0=Yes, 1=None)    (Japan/Original: always 0=Yes)
  2      Application Type   (0=GBA/Z80, 1=NES) (Japan/Original: always 0=Z80)
  3-31   Zero (0) (don't care)
```

Data Checksum [13h-14h] is the complement (NOT) of the sum of all halfwords in
all Data Fragments, however, it's all done in reversed byte order: checksum is
calculated with halfwords that are read in MSB,LSB order, and the resulting
checksum is stored in MSB,LSB order in the Header Fragment.

Global Checksum [2Fh] is the complement (NOT) of the sum of the first 2Fh bytes
in the Data Header plus the sum of all Data Fragment checksums; the Data
Fragment checksums are all 30h bytes in a fragment XORed with each other.



## Titles (3+N bytes, or N bytes)


Titles can be 33 bytes for both Main and Sub (Format 0Eh), or Main=17 bytes and
Sub=3+18 bytes (Formats 02h..05h). In the 3+N bytes form, the first 3 bytes
(24bit) are are used to display "stats" information in form of "HP: h1 ID:
i1-i2-i3", defined as:

```
  Bit    Expl.
  0-3    h1, values 1..15 shown as "10..150", value 0 is not displayed
  4-6    i3, values 0..7 shown as "A..G,#"
  7-13   i2, values 0..98 shown as "01..99" values 99..127 as "A0..C8"
  14-18  i1, values 0..31 shown as "A..Z,-,_,{HP},.,{ID?},:"
  19-22  Unknown
  23     Disable stats (0=Show as "HP: h1 ID: i1-i2-i3", 1=Don't show it)
```

The N bytes portion contains the actual title, which must be terminated by 00h
(so the max length is N-1 characters, if it is shorter than N-1, then the
unused bytes are padded by further 00h's). The character set is normal ASCII
for non-Japan (see Region/Version entry in header), and 2-byte SHIFT-JIS for
Japanese long-titles (=max 16 2-byte chars) with values as so:

```
  00h          --> end-byte
  81h,40h      --> SPC
  81h,43h..97h --> punctuation marks
  82h,4Fh..58h --> "0..9"
  82h,60h..79h --> "A..Z"
  82h,81h..9Ah --> "a..z"
```

And 1-byte chars for Japanese short-titles,

```
  00     = end-byte
  01     = spc
  02..0B = 0..9
  0C..AF = japanese
  B0..B4 = dash, male, female, comma, round-dot
  B5..C0 = !"%&~?/+-:.'
  C1..DA = A..Z
  DB..DF = unused (blank)
  E0..E5 = japanese
  E6..FF = a..z
  N/A    = #$()*;<=>@[\]^_`{|}
```

Additionally to the Main-Title, optional Sub-Titles for each strip can be
included (see Sub-Title Flag in header). If enabled, then ALL strip titles are
included in each strip (allowing to show a preview of which strips have/haven't
been scanned yet).

The e-Reader can display maximum of 8 sub-titles, if the data consists of more
than 8 strips, then sub-titles aren't displayed (so it'd be waste of space to
include them in the dotcodes).

The Main Title gets clipped to 128 pixels width (that are, circa 22
characters), and, the e-Reader BIOS acts confused on multi-strip games with
Main Titles longer than 26 characters (so the full 33 bytes may be used only in
Japan; with 16bit charset).

If the title is empty (00h-filled), and there is only one card in the
application, then the application is started immediately. That, without
allowing the user to save it in FLASH memory.

Caution: Although shorter Titles do save memory, they do act unpleasant: the
text "(C) P-Letter" will be displayed at the bottom of the loading screen.

On Japanese/Original, 8bit sub-titles can be up to 18 characters (without any
end-byte) (or less when stats are enabled, due to limited screen width).



## Card Types (Primary Type.Bit0 and Region/Type.Bit12-15)


```
  00h..01h  Blank Screen (?)
  02h..03h  Dotcode Application with 17byte-title, with stats, load music A
  04h..05h  Dotcode Application with 17byte-title, with stats, load music B
  06h..07h  P-Letter Attacks
  08h..09h  Construction Escape
  0Ah..0Bh  Construction Action
  0Ch..0Dh  Construction Melody Box
  0Eh       Dotcode Application with 33byte-title, without stats, load music A
  0Fh       Game specific cards
  10h..1Dh  P-Letter Viewer
  1Eh..1Fh  Same as 0Eh and 0Fh (see above)
```

The 'Application' types are meant to be executable GBA/Z80/NES programs.




# GBA Cart e-Reader Program Code



The GBA/Z80/NES program code is stored in the VPK compressed area.

NES-type is indicated by header [2Ah].Bit2, GBA-type is indicated by the NULL
value inserted between VPK Size and VPK Data, otherwise Z80-type is used.



## GBA Format


Load Address and Entrypoint are at 2000000h (in ARM state). The 32bit word at
2000008h is eventually destroyed by the e-Reader. Namely,

```
  IF e-Reader is Non-Japanese,
  AND [2000008h] is outside of range of 2000000h..20000E3h,
  AND only if booted from camera (not when booted from FLASH?),
  THEN [2000008h]=[2000008h]-0001610Ch ELSE [2000008h] kept intact
```

Existing multiboot-able GBA binaries can be converted to e-Reader format by,

```
  Store "B 20000C0h" at 2000000h   ;redirect to RAM-entrypoint
  Zerofill 2000004h..20000BFh      ;erase header (for better compression rate)
  Store 01h,01h at 20000C4h        ;indicate RAM boot
```

The GBA code has full access to the GBA hardware, and may additionally use
whatever API functions contained in the e-Reader BIOS. With the incoming LR
register value, "mov r0,N, bx lr" returns to the e-Reader BIOS (with N being
0=Restart, or 2=To\_Menu). No idea if it's necessary to preserve portions of RAM
when returning to the e-Reader BIOS?

Caution: Unlike for normal GBA cartridges/multiboot files, the hardware is left
uninitialized when booting dotcodes (among others: sound DMA is active, and
brightness is set to zero), use "mov r0,0feh, swi 010000h" to get the normal
settings.



## NES Format


Emulates a NES (Nintendo Entertainment System) console (aka Family Computer).

The visible 240x224 pixel NES/NTSC screen resolution is resampled to 240x160 to
match the smaller vertical resolution of the GBA hardware. So, writing e-Reader
games in NES format will result in blurred screen output. The
screen/sound/joypad is accessed via emulated NES I/O ports, program code is
running on an emulated 6502 8bit CPU, for more info on the NES hardware, see
no$nes debugger specifications, or

- [http://problemkaputt.de/everynes.htm](http://problemkaputt.de/everynes.htm)

The e-Reader's NES emulator supports only 16K PRG ROM, followed by 8K VROM. The
emulation accuracy is very low, barely working with some of Nintendo's own NES
titles; running the no$nes diagnostics program on it has successfully failed on
ALL hardware tests ;-)

The load address for the 16K PRG-ROM is C000h, the 16bit NMI vector at [FFFAh]
is encrypted like so:

```
  for i=17h to 0
   for j=07h to 0, nmi = nmi shr 1, if carry then nmi = nmi xor 8646h, next j
   nmi = nmi xor (byte[dmca_data+i] shl 8)
  next i
  dmca_data: db 0,0,'DMCA NINTENDO E-READER'
```

The 16bit reset vector at [FFFCh] contains:

```
  Bit0-14  Lower bits of Entrypoint (0..7FFFh = Address 8000h..FFFFh)
  Bit15    Nametable Mode (0=Vertical Mirroring, 1=Horizontal Mirroring)
```

reportedly,

```
   (NES limitations, 1 16K program rom + 1-2 8K CHR rom, mapper 0 and 1)
   ines mapper 1 would be MMC1, rather than CNROM (ines mapper 3)?
   but, there are more or less NONE games that have 16K PRG ROM + 16K VROM?
```

The L+R Button key-combination allows to reset the NES, however, there seems to
be no way to return to the e-Reader BIOS.



## Z80/8080 Format


The e-Reader doesn't support the following Z80 opcodes:

```
  CB [Prefix]     E0 RET PO   E2 JP PO,nn   E4 CALL PO,nn   27 DAA    76 HALT
  ED [Prefix]     E8 RET PE   EA JP PE,nn   EC CALL PE,nn   D3 OUT (n),A
  DD [IX Prefix]  F3 DI       08 EX AF,AF'  F4 CALL P,nn    DB IN A,(n)
  FD [IY Prefix]  FB EI       D9 EXX        FC CALL M,nn    xx RST 00h..38h
```

That is leaving not more than six supported Z80 opcodes (DJNZ, JR, JR
c/nc/z/nz), everything else are 8080 opcodes. Custom opcodes are:

```
  76 WAIT A frames, D3 WAIT n frames, and C7/CF RST 0/8 used for API calls.
```

The load address and entrypoint are at 0100h in the emulated Z80 address space.
The Z80 doesn't have direct access to the GBA hardware, instead
video/sound/joypad are accessed via API functions, invoked via RST 0 and RST 8
opcodes, followed by an 8bit data byte, and with parameters in the Z80 CPU
registers. For example, "ld a,02h, rst 8, db 00h" does return to the e-Reader
BIOS.

The Z80/8080 emulation is incredibly inefficient, written in HLL code,
developed by somebody whom knew nothing about emulation nor about ARM nor about
Z80/8080 processors.



## Running GBA-code on Japanese/Original e-Reader


Original e-Reader supports Z80 code only, but can be tweaked to run GBA-code:

```
  retry:
   ld bc,data // ld hl,00c8h      ;src/dst
  lop:
   ld a,[bc] // inc bc // ld e,a  ;lsb
   ld a,[bc] // inc bc // ld d,a  ;msb
   dw 0bcfh ;aka rst 8 // db 0bh  ;[4000000h+hl]=de (DMA registers)
   inc hl // inc  hl // ld a,l
   cp a,0dch // jr nz,lop
  mod1 equ $+1
   dw 37cfh ;aka rst 8 // db 37h  ;bx 3E700F0h
  ;below executed only on jap/plus... on jap/plus, above 37cfh is hl=[400010Ch]
   ld a,3Ah // ld [mod1],a                  ;bx 3E700F0h (3Ah instead 37h)
   ld hl,1 // ld [mod2],hl // ld [mod3],hl  ;base (0200010Ch instead 0201610Ch)
   jr retry
  data:
  mod2 equ $+1
   dd loader         ;40000C8h dma2sad (loader)            ;\
   dd 030000F0h      ;40000CCh dma2dad (mirrored 3E700F0h) ; relocate loader
   dd 8000000ah      ;40000D0h dma2cnt (copy 0Ah x 16bit)  ;/
  mod3 equ $+1
   dd main           ;40000D4h dma3sad (main)              ;\prepare main reloc
   dd 02000000h      ;40000D8h dma3dad (2000000h)          ;/dma3cnt see loader
   .align 2          ;alignment for 16bit-halfword
  org $+201600ch     ;jap/plus: adjusted to org $+200000ch
  loader:
   mov r0,80000000h  ;(dma3cnt, copy 10000h x 16bit)
   mov r1,04000000h  ;i/o base
   strb r1,[r1,208h] ;ime=0 (better disable ime before moving ram)
   str r0,[r1,0DCh]  ;dma3cnt (relocate to 2000000h)
   mov r15,2000000h  ;start relocated code at 2000000h in ARM state
  main:
   ;...insert/append whatever ARM code here...
   end
```




# GBA Cart e-Reader API Functions




## Z80 Interface (Special Opcodes)


```
  db 76h       ;Wait8bit A
  db D3h,xxh   ;Wait8bit xxh
  db C7h,xxh   ;RST0_xxh
  db CFh,xxh   ;RST8_xxh
  ld r,[00xxh]       ;get system values (addresses differ on jap/ori)
  ld r,[00C2h..C3h]  ;GetKeyStateSticky (jap/ori: 9F02h..9F03h)
  ld r,[00C4h..C5h]  ;GetKeyStateRaw    (jap/ori: 9F04h..9F05h)
  ld r,[00C0h..C1h]  ;see Exit and ExitRestart
  ld r,[00D0h..D3h]  ;see Mul16bit
```

For jap/ori, 9Fxxh isn't forwards compatible with jap/plus, so it'd be better
to check joypad via IoRead.



## GBA Interface


```
  bx [30075FCh] ;ApiVector ;in: r0=func_no,r1,r2,r3,[sp+0],[sp+4],[sp+8]=params
  bx lr         ;Exit      ;in: r0 (0=Restart, 2=To_Menu)
```



## Wait8bit/Wait16bit


The various Wait opcodes and functions are waiting as many frames as specified.
Many API functions have no effect until the next Wait occurs.



## Z80 RST0\_xxh Functions / GBA Functions 02xxh


```
  RST0_00h FadeIn, A speed, number of frames (0..x)
  RST0_01h FadeOut
  RST0_02h BlinkWhite
  RST0_03h  (?)
  RST0_04h  (?) blend_func_unk1
  RST0_05h  (?)
  RST0_06h  (?)
  RST0_07h  (?)
  RST0_08h  (?)
  RST0_09h  (?) _020264CC_check
  RST0_0Ah  (?) _020264CC_free
  RST0_0Bh N/A (bx 0)
  RST0_0Ch N/A (bx 0)
  RST0_0Dh N/A (bx 0)
  RST0_0Eh N/A (bx 0)
  RST0_0Fh N/A (bx 0)
  RST0_10h LoadSystemBackground, A number of background (1..101), E bg# (0..3)
  RST0_11h SetBackgroundOffset, A=bg# (0..3), DE=X, BC=Y
  RST0_12h SetBackgroundAutoScroll
  RST0_13h SetBackgroundMirrorToggle
  RST0_14h  (?)
  RST0_15h  (?)
  RST0_16h  (?) write_000000FF_to_02029494_
  RST0_17h  (?)
  RST0_18h  (?)
  RST0_19h SetBackgroundMode, A=mode (0..2)
  RST0_1Ah  (?)
  RST0_1Bh  (?)
  RST0_1Ch  (?)
  RST0_1Dh  (?)
  RST0_1Eh  (?)
  RST0_1Fh  (?)
  RST0_20h LayerShow
  RST0_21h LayerHide
  RST0_22h  (?)
  RST0_23h  (?)
  RST0_24h ... [20264DCh+A*20h+1Ah]=DE, [20264DCh+A*20h+1Ch]=BC
  RST0_25h  (?)
  RST0_26h  (?)
  RST0_27h  (?)
  RST0_28h  (?)
  RST0_29h  (?)
  RST0_2Ah  (?)
  RST0_2Bh  (?)
  RST0_2Ch  (?)
  RST0_2Dh LoadCustomBackground, A bg# (0..3), DE pointer to struct_background,
           max. tile data size = 3000h bytes, max. map data size = 1000h bytes
  RST0_2Eh GBA: N/A - Z80: (?)
  RST0_2Fh  (?)
  RST0_30h CreateSystemSprite, - -   (what "- -" ???)
  RST0_31h SpriteFree, HL sprite handle
  RST0_32h SetSpritePos, HL=sprite handle, DE=X, BC=Y
  RST0_33h  (?) sprite_unk2
  RST0_34h SpriteFrameNext
  RST0_35h SpriteFramePrev
  RST0_36h SetSpriteFrame, HL=sprite handle, E=frame number (0..x)
  RST0_37h  (?) sprite_unk3
  RST0_38h  (?) sprite_unk4
  RST0_39h SetSpriteAutoMove, HL=sprite handle, DE=X, BC=Y
  RST0_3Ah  (?) sprite_unk5
  RST0_3Bh  (?) sprite_unk6
  RST0_3Ch SpriteAutoAnimate
  RST0_3Dh  (?) sprite_unk7
  RST0_3Eh SpriteAutoRotateUntilAngle
  RST0_3Fh SpriteAutoRotateByAngle
  RST0_40h SpriteAutoRotateByTime
  RST0_41h  (?) sprite_unk8
  RST0_42h SetSpriteAutoMoveHorizontal
  RST0_43h SetSpriteAutoMoveVertical
  RST0_44h  (?) sprite_unk9
  RST0_45h SpriteDrawOnBackground
  RST0_46h SpriteShow, HL=sprite handle
  RST0_47h SpriteHide, HL=sprite handle
  RST0_48h SpriteMirrorToggle
  RST0_49h  (?) sprite_unk10
  RST0_4Ah  (?) sprite_unk11
  RST0_4Bh  (?) sprite_unk12
  RST0_4Ch GetSpritePos
  RST0_4Dh CreateCustomSprite
  RST0_4Eh  (?)
  RST0_4Fh  (?) sprite_unk14
  RST0_50h  (?) sprite_unk15
  RST0_51h  (?) sprite_unk16
  RST0_52h  (?) sprite_unk17
  RST0_53h  (?) sprite_unk18
  RST0_54h  (?)
  RST0_55h  (?) sprite_unk20
  RST0_56h  (?)
  RST0_57h SpriteMove
  RST0_58h  (?) sprite_unk22
  RST0_59h  (?) sprite_unk23
  RST0_5Ah  (?) sprite_unk24
  RST0_5Bh SpriteAutoScaleUntilSize, C=speed (higher value is slower),
           HL=sprite handle, DE=size (0100h = normal size,
           lower value = larger, higher value = smaller)
  RST0_5Ch SpriteAutoScaleBySize
  RST0_5Dh SpriteAutoScaleWidthUntilSize
  RST0_5Eh SpriteAutoScaleHeightBySize
  RST0_5Fh  (?)
  RST0_60h  (?)
  RST0_61h  (?)
  RST0_62h  (?)
  RST0_63h  (?)
  RST0_64h hl=[[2024D28h+a*4]+12h]
  RST0_65h  (?) sprite_unk25
  RST0_66h SetSpriteVisible, HL=sprite handle, E=(0=not visible, 1=visible)
  RST0_67h  (?) sprite_unk26
  RST0_68h  (?) set_sprite_unk27
  RST0_69h  (?) get_sprite_unk27
  RST0_6Ah  (?)
  RST0_6Bh  (?)
  RST0_6Ch  (?)
  RST0_6Dh  (?)
  RST0_6Eh hl=[hl+000Ah]  ;r0=[r1+0Ah]
  RST0_6Fh  (?)
  RST0_70h  (?)
  RST0_71h  (?)
  RST0_72h  (?)
  RST0_73h  (?)
  RST0_74h  (?)
  RST0_75h  (?)
  RST0_76h  (?)
  RST0_77h  (?)
  RST0_78h  (?)
  RST0_79h  (?)
  RST0_7Ah  (?)
  RST0_7Bh  (?)
  RST0_7Ch  (?) _0202FD2C_unk12
  RST0_7Dh Wait16bit ;HL=num_frames (16bit variant of Wait8bit opcode/function)
  RST0_7Eh SetBackgroundPalette, HL=src_addr, DE=offset, C=num_colors (1..x)
  RST0_7Fh GetBackgroundPalette(a,b,c)
  RST0_80h SetSpritePalette, HL=src_addr, DE=offset, C=num_colors (1..x)
  RST0_81h GetSpritePalette(a,b,c)
  RST0_82h ClearPalette
  RST0_83h  (?) _0202FD2C_unk11
  RST0_84h  (?)
  RST0_85h  (?)
  RST0_86h  (?)
  RST0_87h  (?) _0202FD2C_unk8
  RST0_88h  (?) _0202FD2C_unk7
  RST0_89h  (?)
  RST0_8Ah  (?) _0202FD2C_unk6
  RST0_8Bh  (?) _0202FD2C_unk5
  RST0_8Ch GBA: N/A - Z80: (?)
  RST0_8Dh GBA: N/A - Z80: (?)
  RST0_8Eh  (?)
  RST0_8Fh WindowHide
  RST0_90h CreateRegion, H=bg# (0..3), L=palbank# (0..15),
           D,E,B,C=x1,y1,cx,cy (in tiles), return: n/a (no$note: n/a ???)
  RST0_91h SetRegionColor
  RST0_92h ClearRegion
  RST0_93h SetPixel
  RST0_94h GetPixel
  RST0_95h DrawLine
  RST0_96h DrawRect
  RST0_97h  (?) _0202FD2C_unk4
  RST0_98h SetTextColor, A=region handle, D=color foreground (0..15),
           E=color background (0..15)
  RST0_99h DrawText, A=region handle, BC=pointer to text, D=X, E=Y
           (non-japan uses ASCII text, but japanese e-reader's use STH ELSE?)
  RST0_9Ah SetTextSize
  RST0_9Bh  (?) RegionUnk7
  RST0_9Ch  (?) _0202FD2C_unk3
  RST0_9Dh  (?) _0202FD2C_unk2
  RST0_9Eh  (?) _0202FD2C_unk1
  RST0_9Fh Z80: (?) - GBA: SetBackgroundModeRaw
  RST0_A0h  (?)
  RST0_A1h  (?)
  RST0_A2h  (?) RegionUnk6
  RST0_A3h GBA: N/A - Z80: (?)
  RST0_A4h GBA: N/A - Z80: (?)
  RST0_A5h  (?)
  RST0_A6h  (?)
  RST0_A7h  (?)
  RST0_A8h  (?)
  RST0_A9h  (?)
  RST0_AAh  (?)
  RST0_ABh  (?)
  RST0_ACh  (?)
  RST0_ADh  (?) RegionUnk5
  RST0_AEh [202FD2Ch+122h]=A
  RST0_AFh [202FD2Ch+123h]=A
  RST0_B0h [202FD2Ch+124h]=A
  RST0_B1h  (?)
  RST0_B2h  (?)
  RST0_B3h GBA: N/A - Z80: Sqrt   ;hl=sqrt(hl)
  RST0_B4h GBA: N/A - Z80: ArcTan ;hl=ArcTan2(hl,de)
  RST0_B5h Sine                   ;hl=sin(a)*de
  RST0_B6h Cosine                 ;hl=cos(a)*de
  RST0_B7h  (?)
  RST0_B8h  (?)
  RST0_B9h N/A (bx 0)
  RST0_BAh N/A (bx 0)
  RST0_BBh N/A (bx 0)
  RST0_BCh N/A (bx 0)
  RST0_BDh N/A (bx 0)
  RST0_BEh N/A (bx 0)
  RST0_BFh N/A (bx 0)
  Below Non-Japan and Japan/Plus only (not Japan/Ori)
  RST0_C0h GetTextWidth(a,b)
  RST0_C1h GetTextWidthEx(a,b,c)
  RST0_C2h  (?)
  RST0_C3h Z80: N/A (bx 0) - GBA: (?)
  RST0_C4h  (?)
  RST0_C5h  (?)
  RST0_C6h  (?)
  RST0_C7h  (?)
  RST0_C8h  (?)
  RST0_C9h  (?)
  RST0_CAh  (?)
  RST0_CBh  (?)
  RST0_CCh  (?)
  RST0_CDh N/A (bx lr)
  RST0_CEh ;same as RST0_3Bh, but with 16bit mask
  RST0_CFh ;same as RST0_3Eh, but with 16bit de
  RST0_D0h ;same as RST0_3Fh, but with 16bit de
  RST0_D1h ;same as RST0_5Bh, but with 16bit de
  RST0_D2h ;same as RST0_5Ch, but with 16bit de
  RST0_D3h ;same as RST0_5Dh, but with 16bit de
  RST0_D4h ;same as RST0_5Eh, but with 16bit de
  RST0_D5h  (?)
  RST0_D6h  (?)
  RST0_D7h ;[202FD2Ch+125h]=A
  RST0_D8h  (?)
  RST0_D9h  (?)
  RST0_DAh  (?)
  RST0_DBh ;A=[3003E51h]
  RST0_DCh ;[3004658h]=01h
  RST0_DDh DecompressVPKorNonVPK
  RST0_DEh FlashWriteSectorSingle(a,b)
  RST0_DFh FlashReadSectorSingle(a,b)
  RST0_E0h SoftReset
  RST0_E1h GetCartridgeHeader     ;[hl+0..BFh]=[8000000h..80000BFh]
  RST0_E2h GBA: N/A - Z80: bx hl  ;in: hl=addr, af,bc,de,sp=param, out: a
  RST0_E3h Z80: N/A (bx 0) - GBA: (?)
  RST0_E4h  (?)
  RST0_E5h  (?)
  RST0_E6h  (?)
  RST0_E7h  (?)
  RST0_E8h  (?)
  RST0_E9h ;[2029498h]=0000h
  RST0_EAh Z80: N/A (bx 0) - GBA: InitMemory(a)
  RST0_EBh  (?) BL_irq_sio_dma3
  RST0_ECh ;hl = [3003E30h]*100h + [3003E34h]
  RST0_EDh FlashWriteSectorMulti(a,b,c)
  RST0_EEh FlashReadPart(a,b,c)
  RST0_EFh ;A=((-([2029416h] xor 1)) OR (+([2029416h] xor 1))) SHR 31
  RST0_F0h  (?) _unk1
  RST0_F1h RandomInit     ;in: hl=random_seed
  RST0_F2h                         (?)
  Below Japan/Plus only
  RST0_F3h  (?)
  RST0_F4h  (?)
  RST0_F5h  (?)
  RST0_F6h  (?)
  RST0_F7h GBA: N/A - Z80: (?)
  Below is undefined/garbage (values as so in Z80 mode)
  Jap/Ori: RST0_C0h      N/A (bx 0)
  Jap/Ori: RST0_C1h..FFh Overlaps RST8 jump list
  Non-Jap: RST0_F3h..FFh Overlaps RST8 jump list
  Jap/Pls: RST0_F8h..FFh Overlaps RST8 jump list
```



## Z80 RST8\_xxh Functions / GBA Functions 01xxh


```
  RST8_00h GBA: N/A - Z80: Exit       ;[00C0h]=a ;(1=restart, 2=exit)
  RST8_01h GBA: N/A - Z80: Mul8bit    ;hl=a*e
  RST8_02h GBA: N/A - Z80: Mul16bit   ;hl=hl*de, s32[00D0h]=hl*de
  RST8_03h Div                        ;hl=hl/de
  RST8_04h DivRem                     ;hl=hl mod de
  RST8_05h PlaySystemSound            ;in: hl=sound_number
  RST8_06h  (?) sound_unk1
  RST8_07h Random8bit                 ;a=random(0..FFh)
  RST8_08h SetSoundVolume
  RST8_09h BcdTime                    ;[de+0..5]=hhmmss(hl*bc)
  RST8_0Ah BcdNumber                  ;[de+0..4]=BCD(hl), [de+5]=00h
  RST8_0Bh IoWrite                    ;[4000000h+hl]=de
  RST8_0Ch IoRead                     ;de=[4000000h+hl]
  RST8_0Dh GBA: N/A - Z80:  (?)
  RST8_0Eh GBA: N/A - Z80:  (?)
  RST8_0Fh GBA: N/A - Z80:  (?)
  RST8_10h GBA: N/A - Z80:  (?)
  RST8_11h DivSigned                  ;hl=hl/de, signed
  RST8_12h RandomMax                  ;a=random(0..a-1)
  RST8_13h SetSoundSpeed
  RST8_14h  hl=[202FD20h]=[2024CACh]
  RST8_15h  hl=[2024CACh]-[202FD20h]
  RST8_16h SoundPause
  RST8_17h SoundResume
  RST8_18h PlaySystemSoundEx
  RST8_19h IsSoundPlaying
  RST8_1Ah  (?)
  RST8_1Bh  (?)
  RST8_1Ch  (?)
  RST8_1Dh GetExitCount               ;a=[2032D34h]
  RST8_1Eh Permille                   ;hl=de*1000/hl
  RST8_1Fh GBA: N/A - Z80: ExitRestart;[2032D38h]=a, [00C0h]=0001h  ;a=?
  RST8_20h GBA: N/A - Z80: WaitJoypad ;wait until joypad<>0, set hl=joypad
  RST8_21h GBA: N/A - Z80:  (?)
  RST8_22h  (?) _sound_unk7
  RST8_23h  (?) _sound_unk8
  RST8_24h  (?) _sound_unk9
  RST8_25h  (?) _sound_unk10
  RST8_26h Mosaic     ;bg<n>cnt.bit6=a.bit<n>, [400004Ch]=de
  RST8_27h  (?)
  RST8_28h  (?)
  RST8_29h  (?)
  RST8_2Ah  (?) get_8bit_from_2030110h
  RST8_2Bh  (?)
  RST8_2Ch  (?) get_16bit_from_2030112h ;jap/ori: hl=[20077B2h]
  RST8_2Dh  (?) get_16bit_from_2030114h ;jap/ori: hl=[20077B4h]
  RST8_2Eh  (?)
  RST8_2Fh PlayCustomSound(a,b)
  Below not for Japanese/Original
  (the renumbered functions can be theoretically used on japanese/original)
  (but, doing so would blow forwards compatibility with japanese/plus)
  RST8_30h (ori: none)      GBA: N/A - Z80: (?)
  RST8_31h (ori: none)      PlayCustomSoundEx(a,b,c)
  RST8_32h (ori: RST8_30h)  BrightnessHalf   ;[4000050h]=00FFh,[4000054h]=0008h
  RST8_33h (ori: RST8_31h)  BrightnessNormal ;[4000050h]=0000h
  RST8_34h (ori: RST8_32h)  N/A (bx lr)
  RST8_35h (ori: RST8_33h)   (?)
  RST8_36h (ori: RST8_34h)  ResetTimer ;[400010Ch]=00000000h, [400010Eh]=A+80h
  RST8_37h (ori: RST8_35h)  GetTimer   ;hl=[400010Ch]
  RST8_38h (ori: none)      GBA: N/A - Z80:  (?)
  Below is undefined/reserved/garbage (values as so in Z80 mode)
  (can be used to tweak jap/ori to start GBA-code from inside of Z80-code)
  (that, after relocating code to 3000xxxh via DMA via IoWrite function)
  RST8_39h (ori: RST8_36h)  bx 0140014h
  RST8_3Ah (ori: RST8_37h)  bx 3E700F0h
  RST8_3Bh (ori: RST8_38h)  bx 3E70000h+1
  RST8_3Ch (ori: RST8_39h)  bx 3E703E6h+1
  RST8_3Dh (ori: RST8_3Ah)  bx 3E703E6h+1
  RST8_3Eh (ori: RST8_3Bh)  bx 3E703E6h+1
  RST8_3Fh (ori: RST8_3Ch)  bx 3E703E6h+1
  40h-FFh  (ori: 3Dh-FFh)   bx ...
```



## GBA Functions 03xxh (none such in Z80 mode)


```
  RSTX_00h Wait8bit  ;for 16bit: RST0_7Dh
  RSTX_01h GetKeyStateSticky()
  RSTX_02h GetKeyStateRaw()
  RSTX_03h  (?)
  RSTX_04h  (?)
```




# GBA Cart e-Reader VPK Decompression




## vpk\_decompress(src,dest)


```
  collected32bit=80000000h  ;initially empty (endflag in bit31)
  for i=0 to 3, id[i]=read_bits(8), next i, if id[0..3]<>'vpk0' then error
  dest_end=dest+read_bits(32)     ;size of decompressed data (of all strips)
  method=read_bits(8), if method>1 then error
  tree_index=0, load_huffman_tree, disproot=tree_index
  tree_index=tree_index+1, load_huffman_tree, lenroot=tree_index
  ;above stuff is contained only in the first strip. below loop starts at
  ;current location in first strip, and does then continue in further strips.
 decompress_loop:
  if read_bits(1)=0 then                   ;copy one uncompressed data byte,
    [dest]=read_bits(8), dest=dest+1       ;does work without huffman trees
  else
    if disproot=-1 or lenroot=-1 then error  ;compression does require trees
    disp=read_tree(disproot)
    if method=1   ;disp*4 is good for 32bit ARM opcodes
      if disp>2 then disp=disp*4-8 else disp=disp+4*read_tree(disproot)-7
    len=read_tree(lenroot)
    if len=0 or disp<=0 or dest+len-1>dest_end then error ;whoops
    for j=1 to len, [dest]=[dest-disp], dest=dest+1, next j
  if dest<dest_end then decompress_loop
  ret
```



## read\_bits(num)


```
  mov  data=0
  for i=1 to num
    shl collected32bit,1   ;move next bit to carry, or set zeroflag if empty
    if zeroflag
      collected32bit=[src+0]*1000000h+[src+1]*10000h+[src+2]*100h+[src+3]
      src=src+4            ;read data in 32bit units, in reversed byte-order
      carryflag=1          ;endbit
      rcl collected32bit,1 ;move bit31 to carry (and endbit to bit0)
    rcl data,1             ;move carry to data
  next i
  ret(data)
```



## read\_tree(root\_index)


```
  i=root_index
  while node[i].right<>-1  ;loop until reaching data node
    if read_bits(1)=1 then i=node[i].right else i=node[i].left
  i=node[i].left           ;get number of bits
  i=read_bits(i)           ;read that number of bits
  ret(i)                   ;return that value
```



## load\_huffman\_tree


```
  stacktop=sp
  if read_bits(1)=1 then tree_index=-1, ret  ;exit (empty)
  node[tree_index].right=-1                  ;indicate data node
  node[tree_index].left=read_bits(8)         ;store data value
  if read_bits(1)=1 then ret                 ;exit (only 1 data node at root)
  push tree_index                     ;save previous (child) node
  tree_index=tree_index+1
  jmp data_injump
 load_loop:
  push tree_index                     ;save previous (child) node
  tree_index=tree_index+1
  if read_bits(1)=1 then parent_node
 data_injump:
  node[tree_index].right=-1           ;indicate data node
  node[tree_index].left=read_bits(8)  ;store data value
  jmp load_loop
 parent_node:
  pop node[tree_index].right          ;store 1st child
  pop node[tree_index].left           ;store 2nd child
  if sp<>stacktop then jmp load_loop
  if read_bits(1)=0 then error        ;end bit (must be 1)
  ret
```

The best values for the huffman trees that I've found are 6,9,12-bit
displacements for method 0 (best for NES/Z80 code), and two less for method 1,
ie. 4,7,10-bit (best for GBA code). And 2,4,10-bit for the length values. The
smallest value in node 0, and the other values in node 10 and 11.



## Notes


The decompression works similar to the GBA BIOS'es LZ77 decompression function,
but without using fixed bit-widths of length=4bit and displacement=12bit,
instead, the bit-widths are read from huffman trees (which can also define
fixed bit-widths; if data is located directly in the root node).

Unlike the GBA BIOS'es Huffman decompression function, the trees are starting
with data entries, end are ending with the root entry. The above load function
deciphers the data, and returns the root index.

With the variable bit-widths, the VPK compression rate is quite good, only,
it's a pity that the length/disp values are zero-based, eg. for 2bit and 4bit
lengths, it'd be much better to assign 2bit as 2..5, and 4bit as 6..21.



## Non-VPK


The e-Reader additionally supports an alternate decompression function,
indicated by the absence of the "vpk0" ID, which supports compression of
increasing byte-values, which isn't useful for program code.

Bit15 of the VPK Size value seems to disable (de-)compression, the VPK Data
field is then containing plain uncompressed data.




# GBA Cart e-Reader Error Correction



The Error Correction Information that is appended at the end of the Block
Header & Data Fragments consists of standard Reed-Solomon codes, which are
also used for CD/DVD disks, DSL modems, and digital DVB television signals.
That info allows to locate and repair a number of invalid data bytes.


Below code shows how to create and verify error-info (but not how to do the
actual error correction). The dtalen,errlen values should be 18h,10h for the
Block Header, and 40h,10h for Data Fragments; the latter settings might be
possible to get changed to other values though?



## append\_error\_info(data,dtalen,errlen)


```
  reverse_byte_order(data,dtalen)
  zerofill_error_bytes(data,errlen)
  for i=dtalen-1 to errlen  ;loop across data portion
    z = rev[ data[i] xor data[errlen-1] ] ;
    for j=errlen-1 to 0     ;loop across error-info portion
    if j=0 then x=00h else x=data[j-1]
      if z<>FFh then
        y=gg[j], if y<>FFh then
          y=y+z, if y>=FFh then y=y-FFh
          x=x xor pow[y]
      data[j]=x
    next j
  next i
  invert_error_bytes(data,errlen)
  reverse_byte_order(data,dtalen)
```



## verify\_error\_info(data,dtalen,errlen)


```
  reverse_byte_order(data,dtalen)
  invert_error_bytes(data,errlen)
  make_rev(data,dtalen)
  for i=78h to 78h+errlen-1
    x=0, z=0
    for j=0 to dtalen-1
      y=data[j]
      if y<>FFh then
        y=y+z, if y>=FFh then y=y-FFh
        x=x xor pow[y]
      z=z+i, if z>=FFh then z=z-FFh
    next j
    if x<>0 then error
  next i
  ;(if errors occured, could correct them now)
  make_pow(data,dtalen)
  invert_error_bytes(data,errlen)
  reverse_byte_order(data,dtalen)
```



## make\_rev(data,len)


```
  for i=0 to len-1, data[i]=rev[data[i]], next i
```



## make\_pow(data,len)


```
  for i=0 to len-1, data[i]=pow[data[i]], next i
```



## invert\_error\_bytes(data,len)


```
  for i=0 to len-1, data[i]=data[i] xor FFh, next i
```



## zerofill\_error\_bytes(data,len)


```
  for i=0 to len-1, data[i]=00h, next i
```



## reverse\_byte\_order(data,len)


```
  for i=0 to (len-1)/2, x=data[i], data[i]=data[len-i], data[len-i]=x, next i
```



## create\_pow\_and\_rev\_tables


```
  x=01h, pow[FFh]=00h, rev[00h]=FFh
  for i=00h to FEh
    pow[i]=x, rev[x]=i, x=x*2, if x>=100h then x=x xor 187h
  next i
```



## create\_gg\_table


```
  gg[0]=pow[78h]
  for i=1 to errlen-1
    gg[i]=01h
    for j=i downto 0
      if j=0 then y=00h else y=gg[j-1]
      x=gg[j], if x<>00h then
        x=rev[x]+78h+i, if x>=FFh then x=x-FFh
        y=y xor pow[x]
      gg[j]=y
    next j
  next i
  make_rev(gg,errlen)
```

With above value of 78h, and errlen=10h, gg[00h..0Fh] will be always:

```
  00h,4Bh,EBh,D5h,EFh,4Ch,71h,00h,F4h,00h,71h,4Ch,EFh,D5h,EBh,4Bh
```

So using a hardcoded table should take up less memory than calculating it.



## Notes


The actual error correction should be able to fix up to "errlen" errors at
known locations (eg. data from blocks that haven't been scanned, or whose
5bit-to-4bit conversion had failed due to an invalid 5bit value), or up to
"errlen/2" errors at unknown locations. The corrected data isn't guaranteed to
be correct (even if it looks okay to the "verify" function), so the Data Header
checksums should be checked, too.



## More Info


For more info, I've found Reed-Solomon source code from Simon Rockliff, and an
updated version from Robert Morelos-Zaragoza and Hari Thirumoorthy to be
useful. For getting started with that source, some important relationships
& differences are:

```
  pow = alpha_to, but generated as shown above
  rev = index_of, dito
  b0  = 78h
  nn  = dtalen
  kk  = dtalen-errlen
  %nn = MOD FFh (for the ereader that isn't MOD dtalen)
  -1  = FFh
```

And, the ereader processes data/errinfo backwards, starting at the last byte.




# GBA Cart e-Reader File Formats




## .BMP Files (homebrew 300 DPI strips)


Contains a picture of the whole dotcode strip with address bars and sync marks
(see Dotcode chapter) in Microsoft's Bitmap format. The image is conventionally
surrounded by a blank 2-pixel border, resulting in a size of 989x44 pixels for
long strips. The file should should have 1bit color depth. The pixels per meter
entry should match the desired printing resolution, either 300 DPI or 360 DPI.
But, resolution of printer hardware is typically specified in inch rather than
in meters, so an exact match isn't supported by Microsoft. Most homebrew .BMP
files contain nonsense resolutions like 200 DPI, or 300 dots per meter (ca. 8
DPI).



## .JPG Files (scanned 1200 DPI strips)


Same as BMP, but should contain a dotcode scanned at 1200 DPI, with correct
orientation (the card-edge side at the bottom of the image), and containing
only the dotcode (not the whole card), so the JPG size should be about 3450x155
pixels for long strips.

No$gba currently doesn't work with progressive JPGs. Scans with white
background can be saved as monochrome JPG. Scans with red/yellow background
should contain a correct RED layer (due to the red LED light source) (the
brightness of the green/blue layers can be set to zero for better compression).



## .RAW Files


Contains the "raw" information from the BMP format, that is, 2-byte block
header, 102-byte data, 2-byte block header, 102-byte data, etc. The data
portion is interleaved, and includes the full 48-byte data header, titles, vpk
compressed data, error-info, and unused bytes. RAW files are excluding Address
Bars, Sync Marks, and 4bit-to-5bit encoding.

Each RAW file contains one or more strip(s), so the RAW filesize is either
18\*104 bytes (short strip), or 28\*104 bytes (long strip), or a multiple thereof
(if it contains more than one strip) (although multi-strip games are often
stored in separate files for each strip; named file1.raw, file2.raw, etc).



## .BIN Files


Filesize should be I\*30h, with I=1Ch for short strips, and I=2Ch for long
strips, or a multiple thereof (if it contains more than one strip). Each strip
consists of the 48-byte Data Header, followed by title(s), and vpk compressed
data. Unlike .RAW files, .BIN files aren't interleaved, and do not contain
Block Headers, nor error-info, nor unused bytes (in last block). The files do
contain padding bytes to match a full strip-size of I\*30h.

Caution: Older .BIN files have been using a size-reduced 12-byte header (taken
from entries 0Dh, 0Ch, 10h-11h, 26h-2Dh of the 48-byte Data Header; in that
order), that files have never contained more than one strip per file, so the
filesize should be exactly I\*30h-36, the size-reduced header doesn't contain a
Primary Type entry, so it's everyone's bet which Card Type is to be used (hint:
the 12-byte headers were based on the assumption that Primary Type would be
always 01h on Short Strips, and 02h on Long Strips).



## .SAV Files


Contains a copy of the e-Reader's 128Kbyte FLASH memory. With the saved
e-Reader application being located in the 2nd 64K-bank, the data consists of a
header with title and gba/nes/z80 format info, followed by the vpk compressed
data. The FLASH memory does also contain e-Reader calibration settings, the
remaining 100Kbytes are typically FFh-filled.




# GBA Cart Unknown Devices




## GBA Infra-Red Port (AGB-006)


No info?




# GBA Cart Protections




## Classic NES Series


These are some NES/Famicom games ported or emulated to work on GBA. The games
are doing some uncommon stuff that can cause compatibility problems when not
using original GBA consoles or cartridges.

- CPU pipeline (selfmodifying code that shall NOT affect prefetched opcodes)

- STMDA write to I/O ports (writes in INCREASING order, not DECREASING order)

- SRAM detection (refuses to run if SRAM exists; the games do contain EEPROM)

- ROM mirrors (instead of the usual increasing numbers in unused ROM area)

- RAM mirrors (eg. main RAM accessed at 2F00000h instead of 2000000h)

Note: These games can be detected by checking [80000ACh]="F" (ie. game
code="Fxxx").




# GBA Flashcards



Flashcards are re-writable cartridges using FLASH memory, allowing to test even
multiboot-incompatible GBA software on real hardware, providing a good
development environment when used in combination with a reasonable software
debugger.


The carts can be written to from external tools, or directly from GBA programs.

Below are pseudo code flowcharts for detect, erase, and write operations.

All flash reads/writes are meant to be 16bit (ldrh/strh) memory accesses.



## detect\_flashcard:


```
 configure_flashcard(9E2468Ah,9413h)    ;unlock flash advance cards
 turbo=1, send_command(8000000h,90h)    ;enter ID mode (both chips, if any)
 maker=[8000000h], device=[8000000h+2]
 IF maker=device THEN device=[8000000h+4] ELSE turbo=0
 flashcard_read_mode                    ;exit ID mode
 search (maker+device*10000h) in device_list
 total/erase/write_block_size = list_entry SHL turbo
```



## flashcard\_erase(dest,len):


```
 FOR x=1 to len/erase_block_size
  send_command(dest,20h)        ;erase sector command
  send_command(dest,D0h)        ;confirm erase sector
  dest=dest+erase_block_size
 IF wait_busy=okay THEN NEXT x
 enter_read_mode                ;exit erase/status mode
```



## flashcard\_write(src,dest,len):


```
 siz=write_block_size
 FOR x=1 to len/siz
  IF siz=2 THEN send_command(dest,10h)  ;write halfword command
  IF siz>2 THEN send_command(dest,E8h)  ;write to buffer command
  IF siz>2 THEN send_command(dest,16-1) ;buffer size 16 halfwords (per chip)
  FOR y=1 TO siz/2
   [dest]=[src], dest=dest+2, src=src+2 ;write data to buffer
  NEXT y
  IF siz>2 THEN send_command(dest,D0h)  ;confirm write to buffer
 IF wait_busy=okay THEN NEXT x
 enter_read_mode                        ;exit write/status mode
```



## send\_command(adr,val):


- [adr]=val
- IF turbo THEN [adr+2]=val



## enter\_read\_mode:


```
 send_command(8000000h,FFh)     ;exit status mode
 send_command(8000000h,FFh)     ;again maybe more stable (as in jeff's source)
```



## flashcard\_wait\_busy:


- start=time
- REPEAT
  - stat=[8000000h] XOR 80h
  - IF turbo THEN stat=stat OR ([8000000h+2] XOR 80h)
  - IF (stat AND 7Fh)>0 THEN error
  - IF (stat AND 80h)=0 THEN ready
  - IF time-start>5secs THEN timeout
- UNTIL ready OR error OR timeout
- IF error OR timeout THEN send\_command(8000000h,50h)    ;clear status



## configure\_flashcard(adr,val):   ;required for Flash Advance cards only


- [930ECA8h]=5354h
- [802468Ah]=1234h, repeated 500 times
- [800ECA8h]=5354h
- [802468Ah]=5354h
- [802468Ah]=5678h, repeated 500 times
- [930ECA8h]=5354h
- [802468Ah]=5354h
- [8ECA800h]=5678h
- [80268A0h]=1234h
- [802468Ah]=ABCDh, repeated 500 times
- [930ECA8h]=5354h
- [adr]=val



## init\_backup:  ;no info how to use that exactly


```
 configure_flashcard(942468Ah,???)
```



## device\_list:  (id code, total/erase/write sizes in bytes)


```
  ID Code    Total   Erase  Write  Name
  -??-00DCh      ?       ?      ?  Hudson Cart (???)
  00160089h     4M    128K     32  Intel i28F320J3A (Flash Advance)
  00170089h     8M    128K     32  Intel i28F640J3A (Flash Advance)
  00180089h    16M    128K     32  Intel i28F128J3A (Flash Advance)
  00E200B0h      ?     64K      2  Sharp LH28F320BJE ? (Nintendo)
```



## Notes


All flashcards should work at 4,2 waitstates (power on default), most
commercial games change waits to 3,1 which may work unstable with some/older FA
flashcards. Intel FLASH specified to have a lifetime of 100,000 erases, and
average block erase time 1 second (up to 5 second in worst cases).

Aside from the main FLASH memory, Flash Advance (FA) (aka Visoly) cards
additionally contain battery buffered SRAM backup, and FLASH backup, and in
some cases also EEPROM backup.

Turbo FA cards are containing two chips interlaced (at odd/even halfword
addresses), allowing to write/erase both chips simultaneously, resulting in
twice as fast programming time.

Standard Nintendo flash carts have to be modified before you can actually write
to them. This is done by removing resistor R7 and putting it at empty location
R8.

Mind that write/erase/detect modes output status information in ROM area, so
that in that modes all GBA program code (and any interrupt handlers) must be
executed in WRAM, not in ROM.


Thanks to Jeff Frohwein for his FAQ and CARTLIB sample in FLGBA at devrs.com




# GBA Cheat Devices



Codebreaker (US) aka Xploder (EUR).

Gameshark (US) aka Action Replay (EUR).


- [GBA Cheat Codes - General Info](#gbacheatcodesgeneralinfo)
- [GBA Cheat Codes - Codebreaker/Xploder](#gbacheatcodescodebreakerxploder)
- [GBA Cheat Codes - Gameshark/Action Replay V1/V2](#gbacheatcodesgamesharkactionreplayv1v2)
- [GBA Cheat Codes - Pro Action Replay V3](#gbacheatcodesproactionreplayv3)



# GBA Cheat Codes - General Info



Cheat devices are external adapters, connected between the GBA and the game
cartridge. The devices include a BIOS ROM which is, among others, used to
prompt the user to enter cheat codes.

These codes are used to patch specified memory locations for a certain GBA
game, allowing the user to gain goodies such like Infinite sex, 255 Cigarettes,
etc.



## ROM and RAM Patches


For ROM Patches, the device watches the address bus, if it matches a specified
address then it outputs a patched value to the data bus, that mechanism is
implemented by hardware, aside from the Hook Enable Code some devices also
allow a limited number of cheats to use ROM patches.

Most cheat codes are RAM patches, each time when the hook procedure is executed
it will process all codes and overwrite the specified addresses in RAM (or VRAM
or I/O area) by the desired values.



## Enable Codes (Must Be On)


Enable codes usually consist of the Game ID, Hook Address, and eventually a
third code used to encrypt all following codes. The Game ID is used to confirm
that the correct cartridge is inserted, just a verification, though the device
may insist on the ID code.

The Hook Address specifies an address in cartridge ROM, and should point to an
opcode which is executed several times per second (eg. once per frame, many
codes place the hook in the joypad handler). At the hook address, the device
redirects to its own BIOS, processes the RAM patches, and does then return
control to the game cartridge.

Note: The hook address should not point to opcodes with relative addressing
(eg. B, BL, LDR Rd,=Imm, ADD Rd,=Imm opcodes - which are all relative to PC
program counter register).



## Alignment


Addresses for 16bit or 32bit values should be properly aligned.




# GBA Cheat Codes - Codebreaker/Xploder




## Codebreaker Codes


```
  0000xxxx 000y  Enable Code 1 - Game ID
  1aaaaaaa 000z  Enable Code 2 - Hook Address
  2aaaaaaa yyyy  [aaaaaaa]=[aaaaaaa] OR yyyy
  3aaaaaaa 00yy  [aaaaaaa]=yy
  4aaaaaaa yyyy  [aaaaaaa+0..(cccc-1)*ssss]=yyyy+0..(cccc-1)*ssss
  iiiicccc ssss  parameters for above code
  5aaaaaaa cccc  [aaaaaaa+0..(cccc-1)]=11,22,33,44,etc.
  11223344 5566  parameter bytes 1..6 for above code (example)
  77880000 0000  parameter bytes 7..8 for above code (padded with zero)
  6aaaaaaa yyyy  [aaaaaaa]=[aaaaaaa] AND yyyy
  7aaaaaaa yyyy  IF [aaaaaaa]=yyyy THEN (next code)
  8aaaaaaa yyyy  [aaaaaaa]=yyyy
  9xyyxxxx xxxx  Enable Code 0 - Encrypt all following codes (optional)
  Aaaaaaaa yyyy  IF [aaaaaaa]<>yyyy THEN (next code)
  Baaaaaaa yyyy  IF [aaaaaaa]>yyyy THEN (next code) (signed comparison)
  Caaaaaaa yyyy  IF [aaaaaaa]<yyyy THEN (next code) (signed comparison)
  D0000020 yyyy  IF [joypad] AND yyyy = 0 THEN (next code)
  Eaaaaaaa yyyy  [aaaaaaa]=[aaaaaaa]+yyyy
  Faaaaaaa yyyy  IF [aaaaaaa] AND yyyy THEN (next code)
```



## Codebreaker Enable Codes


Hook Address 'aaaaaaa' is a 25bit offset in ROM-image (0-1FFFFFFh).

Flag byte 'y' (usually 0Ah), Bit1=Disable IRQs, Bit3=CRC Exists.

Code Handler Store Address 'z' (0-7, usually 7) (8000100h+z\*400000h).

Checksum 'xxxx' for first 64Kbytes of cartridge (no$gba pads by FFh if ROM is
smaller than 64K). Calculated, by using unsigned 16bit values, as such:

```
  crc=FFFFh
  for i=0 to FFFFh
   x=byte[i] xor (crc/100h)
   x=x xor (x/10h)
   crc=(crc*100h) xor (x*1001h) xor (x*20h)
  next i
```



## Codebreaker Encryption


codebreaker\_change\_encryption:

Encryption can be (optionally) activated by code "9xyyxxxx xxxx",

```
  for i=0 to 2Fh, swaplist[i]=i, next i
  randomizer = 1111h xor byte[code+4]                              ;LSB value
  for i=0 to 4Fh
    exchange swaplist[random MOD 30h] with swaplist[random MOD 30h]
  next i
  halfword[seedlist+0] = halfword[code+0]                          ;LSW address
  randomizer = 4EFAD1C3h
  for i=0 to byte[code+3]-91h, randomizer=random, next i           ;MSB address
  word[seedlist+2]=random, halfword[seedlist+6]=random
  randomizer = F254h xor byte[code+5]                              ;MSB value
  for i=0 to byte[code+5]-01h, randomizer=random, next i           ;MSB value
  word[seedlist+8]=random, halfword[seedlist+12]=random
  ;note: byte[code+2] = don't care
  ret
```

The above random function works like so:

```
  randomizer=randomizer*41C64E6Dh+3039h, x=(randomizer SHL 14 AND C0000000h)
  randomizer=randomizer*41C64E6Dh+3039h, x=(randomizer SHR 1  AND 3FFF8000h)+x
  randomizer=randomizer*41C64E6Dh+3039h, x=(randomizer SHR 16 AND 00007FFFh)+x
  return(x)
```

Once when encryption is activated, all following codes are decrypted like so:

```
  for i=2Fh to 0
    j=swaplist[i]
    bitno1=(i AND 7), index1=xlatlist[i/8]
    bitno2=(j AND 7), index2=xlatlist[j/8]
    exchange [code+index1].bitno1 with [code+index2].bitno2
  next i
  word[code+0] = word[code+0] xor word[seedlist+8]
  i = (byte[code+3]*1010000h + byte[code+0]*100h + byte[code+5])
  i = (halfword[code+1]*10001h) xor (word[seedlist+2]) xor i
  i = (byte[seedlist+0]*1010101h) xor (byte[seedlist+1]*1000000h) xor i
  j = (byte[code+5] + (byte[code+0] xor byte[code+4])*100h)
  j = (byte[seedlist+0]*101h) xor halfword[seedlist+6] xor j
  word[code+0] = i, halfword[code+4] = j
```

The above xlatlist is fixed: xlatlist[0..5] = 3,2,1,0,5,4




# GBA Cheat Codes - Gameshark/Action Replay V1/V2




## Gameshark RAW Codes (These codes must be encrypted before using them)


```
  0aaaaaaa 000000xx  [aaaaaaa]=xx
  1aaaaaaa 0000xxxx  [aaaaaaa]=xxxx
  2aaaaaaa xxxxxxxx  [aaaaaaa]=xxxxxxxx
  3000cccc xxxxxxxx  write xxxxxxxx to (cccc-1) addresses (list in next codes)
  aaaaaaaa aaaaaaaa  parameter for above code, containing two addresses each
  aaaaaaaa 00000000  last parameter for above, zero-padded if only one address
  60aaaaaa y000xxxx  [8000000h+aaaaaa*2]=xxxx (ROM Patch)
  8a1aaaaa 000000xx  IF GS_Button_Down THEN [a0aaaaa]=xx
  8a2aaaaa 0000xxxx  IF GS_Button_Down THEN [a0aaaaa]=xxxx
  80F00000 0000xxxx  IF GS_Button_Down THEN slowdown xxxx * ? cycles per hook
  Daaaaaaa 0000xxxx  IF [aaaaaaa]=xxxx THEN (next code)
  E0zzxxxx 0aaaaaaa  IF [aaaaaaa]=xxxx THEN (next 'zz' codes)
  Faaaaaaa 00000x0y  Enable Code - Hook Routine
  xxxxxxxx 001DC0DE  Enable Code - Game Code ID (value at [0ACh] in cartridge)
  DEADFACE 0000xxyy  Change Encryption Seeds
```



## Enable Code - Hook Routine


Hook Address 'aaaaaaa' is a 28bit ROM address (8FFFFFFh-9FFFFFFh).

Used to insert the GS code handler routine where it will be executed at

least 20 times per second. Without this code, GSA can not write to RAM.

- y=1 - Executes code handler without backing up the LR register.
- y=2 - Executes code handler and backs up the LR register.
- y=3 - Replaces a 32-bit pointer used for long-branches.
- x=0 - Must turn GSA off before loading game.
- x=1 - Must not do that.



## ROM Patch


This type allows GSA to intercept ROM reads and returns the value xxxx.

- y=0 wait for the code handler to enable the patch
- y=1 patch is enabled before the game starts
- y=2 unknown ?

Note: V1/V2 hardware can only have up to 1 user-defined rom patch max. V3 can
have up to 4. Some enable code types can shorten the amount of user-defined rom
patches available.



## Gameshark Encryption


A=Left half, and V=Right half of code.

```
  FOR I=1 TO 32
    A=A + (V*16+S0) XOR (V+I*9E3779B9h) XOR (V/32+S1)
    V=V + (A*16+S2) XOR (A+I*9E3779B9h) XOR (A/32+S3)
  NEXT I
```

Upon startup, the initial encryption seeds are:

```
  S0=09F4FBBDh S1=9681884Ah S2=352027E9h S3=F3DEE5A7h
```

Upon DEADFACE 0000xxyy, the S0..S3 seeds are changed like so:

```
  FOR y=0 TO 3
   FOR x=0 TO 3
    z = T1[(xx+x) AND FFh] + T2[(yy+y) AND FFh]
    Sy = Sy*100h + (z AND FFh)
   NEXT x
  NEXT y
```

All calculations truncated to unsigned 32bit integer values.

T1 and T2 are translation tables contained in the gameshark cartridge.




# GBA Cheat Codes - Pro Action Replay V3




## Pro Action Replay V3 - RAW Codes


```
  C4aaaaaa 0000yyyy  Enable Code - Hook Routine at [8aaaaaa]
  xxxxxxxx 001DC0DE  Enable Code - ID Code [080000AC]
  DEADFACE 0000xxxx  Enable Code - Change Encryption Seeds
  00aaaaaa xxxxxxyy  [a0aaaaa..a0aaaaa+xxxxxx]=yy
  02aaaaaa xxxxyyyy  [a0aaaaa..a0aaaaa+xxxx*2]=yyyy
  04aaaaaa yyyyyyyy  [a0aaaaa]=yyyyyyyy
  40aaaaaa xxxxxxyy  [ [a0aaaaa] + xxxxxx ]=yy   (Indirect)
  42aaaaaa xxxxyyyy  [ [a0aaaaa] + xxxx*2 ]=yyyy (Indirect)
  44aaaaaa yyyyyyyy  [ [a0aaaaa] ]=yyyyyyyy      (Indirect)
  80aaaaaa 000000yy  [a0aaaaa]=[a0aaaaa]+yy
  82aaaaaa 0000yyyy  [a0aaaaa]=[a0aaaaa]+yyyy
  84aaaaaa yyyyyyyy  [a0aaaaa]=[a0aaaaa]+yyyyyyyy
  C6aaaaaa 0000yyyy  [4aaaaaa]=yyyy              (I/O Area)
  C7aaaaaa yyyyyyyy  [4aaaaaa]=yyyyyyyy          (I/O Area)
  iiaaaaaa yyyyyyyy  IF [a0aaaaa] <cond> <value> THEN <action>
  00000000 60000000  ELSE (?)
  00000000 40000000  ENDIF (?)
  00000000 0800xx00  AR Slowdown : loops the AR xx times
  00000000 00000000  End of the code list
  00000000 10aaaaaa 000000zz 00000000  IF AR_BUTTON THEN [a0aaaaa]=zz
  00000000 12aaaaaa 0000zzzz 00000000  IF AR_BUTTON THEN [a0aaaaa]=zzzz
  00000000 14aaaaaa zzzzzzzz 00000000  IF AR_BUTTON THEN [a0aaaaa]=zzzzzzzz
  00000000 18aaaaaa 0000zzzz 00000000  [8000000+aaaaaa*2]=zzzz  (ROM Patch 1)
  00000000 1Aaaaaaa 0000zzzz 00000000  [8000000+aaaaaa*2]=zzzz  (ROM Patch 2)
  00000000 1Caaaaaa 0000zzzz 00000000  [8000000+aaaaaa*2]=zzzz  (ROM Patch 3)
  00000000 1Eaaaaaa 0000zzzz 00000000  [8000000+aaaaaa*2]=zzzz  (ROM Patch 4)
```


```
  00000000 80aaaaaa 000000yy ssccssss  repeat cc times [a0aaaaa]=yy
   (with yy=yy+ss, a0aaaaa=a0aaaaa+ssss after each step)
```


```
  00000000 82aaaaaa 0000yyyy ssccssss  repeat cc times [a0aaaaa]=yyyy
   (with yyyy=yyyy+ss, a0aaaaa=a0aaaaa+ssss*2 after each step)
```


```
  00000000 84aaaaaa yyyyyyyy ssccssss  repeat cc times [a0aaaaa]=yyyyyyyy
   (with yyyy=yyyy+ss, a0aaaaa=a0aaaaa+ssss*4 after each step)
```


Warning: There is a bug on the real AR (v2 upgraded to v3, and maybe on real
v3) with the 32bit Increment Slide code. You HAVE to add a code (best choice is
80000000 00000000 : add 0 to value at address 0) right after it, else the AR
will erase the 2 last 8 digits lines of the 32 Bits Inc. Slide code when you
enter it !!!


Final Notes

The 'turn off all codes' makes an infinite loop (that can't be broken, unless
the condition becomes True). - How? By Interrupt? Huh?

ROM Patch1 works on real V3 and, on V1/V2 upgraded to V3.

ROM Patch2,3,4 work on real V3 hardware only.



## Pro Action Replay V3 Conditional Codes - iiaaaaaa yyyyyyyy


The 'ii' is composed of \<cond> + \<value> + \<action>.

```
  <cond>           <value>            <action>
  08 Equal =       00 8bit zz         00 execute next code
  10 Not equal <>  02 16bit zzzz      40 execute next two codes
  18 Signed <      04 32bit zzzzzzzz  80 execute all following
  20 Signed >      06 (always false)     codes until ELSE or ENDIF
  28 Unsigned <                       C0 normal ELSE turn off all codes
  30 Unsigned >
  38 Logical AND
```

For example, ii=18h+02h+40h=5Ah, produces IF [a0aaaaa]\<zzzz THEN next 2
codes.


Always... Codes

```
  For the "Always..." codes:
  - XXXXXXXX can be any authorised address except 00000000 (eg. use 02000000).
  - ZZZZZZZZ can be anything.
  - The "y" in the code data must be in the [1-7] range (which means not 0).
  typ=y,sub=0,siz=3   Always skip next line.
  typ=y,sub=1,siz=3   Always skip next 2 lines.
  typ=y,sub=2,siz=3   Always Stops executing all the codes below.
  typ=y,sub=3,siz=3   Always turn off all codes.
```



## Code Format (ttaaaaaa xxxxyyzz)


- adr mask = 003FFFFF
- n/a mask = 00C00000 ;not used
- xtr mask = 01000000 ;used only by I/O write, and MSB of Hook
- siz mask = 06000000
- typ mask = 38000000 ;0=normal, other=conditional
- sub mask = C0000000



## Pro Action Replay V3 Encryption


Works exactly as for Gameshark Encryption, but with different initial seeds,

```
  S0=7AA9648Fh S1=7FAE6994h S2=C0EFAAD5h S3=42712C57h
```

And, the T1 and T2 translation tables are different, too.




# GBA Gameboy Player



The Gameboy Player is an "adapter" for the Gamecube console. It's basicly is a
GBA in a black box without LCD screen and without buttons, connected to an
expansion port at the bottom of the Gamecube. The Gamecube is then capturing
the GBA video output (and passing it to the television set), and in the other
direction, passing the Gamecube joypad input to the GBA inputs.



## Unlocking and Detecting Gameboy Player Functions


Both unlocking and detection requires to display the 240x160 pixel Gameboy
Player logo (44 colors) for a number of frames... maybe at least 3-4 frames?
not sure if it checks the color of the logo... so maybe it can be hidden by
using dark gray on black background?

While displaying this logo, the joypad data will switch between values 03FFh (2
frames duration) and 030Fh (1 frame duration). The latter value (left, right,
up, down all pressed) indicates that it's a Gameboy Player.



## Palette


Knowing Nintendo, they've probably not reproduced the blurred GBA colors (?),
so the games won't look as desired on the TV screen. Unless the game does
detect the Gameboy Player, and adjust the colors accordingly by software.



## Rumble


The only known existing special function is the joypad rumble function,
controlled by sending data through the serial port (the normal GBA port, even
though it also has the connectors).


The Game Boy Player added a rumble feature to certain Game Boy Advance games
when played with a GameCube controller. Those games included:

- Drill Dozer (supports BOTH handheld-rumble and GBP-rumble?)
- Mario & Luigi: Superstar Saga
- Pokemon Pinball: Ruby & Sapphire
- Shikakui Atama wo Marukusuru Advance: Kokugo Sansu Rika Shakai
- Shikakui Atama wo Marukusuru Advance: Kanji Keisan
- Summon Night Craft Sword Monogatari: Hajimari no Ishi
- Super Mario Advance 4: Super Mario Bros. 3


Fredrik Olsson (aka Flubba) has implemented rumble in 3 applications now
RumblePong (FluBBA) (homebrew)

```
  Remudvance (FluBBA) (homebrew)
  Goomba (FluBBA) (8bit Gameboy Color Emulator for 32bit GBA) (homebrew)
  and, supposedly in "Tetanus on Drugs" (Tepples) (homebrew)
```


The GBP can also use some of the extra controllers for the GC like the Bongas

from Donkey Konga.


The logo requires at least 256 colors, it doesn't matter if you use a tiled

screen mode or a bitmapped one, the logo can be ripped from either

"Pokemon Pinball" or "Super Mario Advance 4".



## Rumble


After detecting/unlocking the Gameboy Player, init RCNT and SIOCNT to 32bit
normal mode, external clock, SO=high, with IRQ enabled, and set the transfer
start bit. You should then receive the following sequence (about once per
frame), and your serial IRQ handler should send responses accordingly:

```
  Receive  Response
  0000494E 494EB6B1
  xxxx494E 494EB6B1
  B6B1494E 544EB6B1
  B6B1544E 544EABB1
  ABB1544E 4E45ABB1
  ABB14E45 4E45B1BA
  B1BA4E45 4F44B1BA
  B1BA4F44 4F44B0BB
  B0BB4F44 8000B0BB
  B0BB8002 10000010
  10000010 20000013
  20000013 40000004
  30000003 40000004
  30000003 40000004
  30000003 40000004
  30000003 400000yy
  30000003 40000004
```

The first part of the transfer just contains the string "NINTENDO" split into
16bit fragments, and bitwise inversions thereof (eg. 494Eh="NI", and B6B1h=NOT
494Eh). In the second part, \<yy> should be 04h=RumbleOff, or
26h=RumbleOn.



## Note


If it's having a similar range of functions as the 8bit Super Gameboy, then the
Gameboy Player might be also able to access analogue joypad input, and to
access other features of the Gamecube hardware, up to possibly executing code
on the Gamecube CPU...?
