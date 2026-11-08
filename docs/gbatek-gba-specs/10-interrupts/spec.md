# GBA Interrupt Control

> 本檔案整理自 [GBATEK](https://problemkaputt.de/gbatek.htm) 的「GBA Interrupt Control」章節。
> 來源採用 [mGBA GBATEK Markdown fork](https://github.com/mgba-emu/gbatek) 的 Markdown 轉存，保留原文的暫存器、位元欄位、程式碼與數值表示法。

# GBA Interrupt Control




## 4000208h - IME - Interrupt Master Enable Register (R/W)


```
  Bit   Expl.
  0     Disable all interrupts         (0=Disable All, 1=See IE register)
  1-31  Not used
```



## 4000200h - IE - Interrupt Enable Register (R/W)


```
  Bit   Expl.
  0     LCD V-Blank                    (0=Disable)
  1     LCD H-Blank                    (etc.)
  2     LCD V-Counter Match            (etc.)
  3     Timer 0 Overflow               (etc.)
  4     Timer 1 Overflow               (etc.)
  5     Timer 2 Overflow               (etc.)
  6     Timer 3 Overflow               (etc.)
  7     Serial Communication           (etc.)
  8     DMA 0                          (etc.)
  9     DMA 1                          (etc.)
  10    DMA 2                          (etc.)
  11    DMA 3                          (etc.)
  12    Keypad                         (etc.)
  13    Game Pak (external IRQ source) (etc.)
  14-15 Not used
```

Note that there is another 'master enable flag' directly in the CPUs Status
Register (CPSR) accessible in privileged modes, see CPU reference for details.



## 4000202h - IF - Interrupt Request Flags / IRQ Acknowledge (R/W, see below)


```
  Bit   Expl.
  0     LCD V-Blank                    (1=Request Interrupt)
  1     LCD H-Blank                    (etc.)
  2     LCD V-Counter Match            (etc.)
  3     Timer 0 Overflow               (etc.)
  4     Timer 1 Overflow               (etc.)
  5     Timer 2 Overflow               (etc.)
  6     Timer 3 Overflow               (etc.)
  7     Serial Communication           (etc.)
  8     DMA 0                          (etc.)
  9     DMA 1                          (etc.)
  10    DMA 2                          (etc.)
  11    DMA 3                          (etc.)
  12    Keypad                         (etc.)
  13    Game Pak (external IRQ source) (etc.)
  14-15 Not used
```

Interrupts must be manually acknowledged by writing a "1" to one of the IRQ
bits, the IRQ bit will then be cleared.


"[Cautions regarding clearing IME and IE]

A corresponding interrupt could occur even while a command to clear IME or each
flag of the IE register is being executed. When clearing a flag of IE, you need
to clear IME in advance so that mismatching of interrupt checks will not
occur." ?


"[When multiple interrupts are used]

When the timing of clearing of IME and the timing of an interrupt agree,
multiple interrupts will not occur during that interrupt. Therefore, set
(enable) IME after saving IME during the interrupt routine." ?



## BIOS Interrupt handling


Upon interrupt execution, the CPU is switched into IRQ mode, and the physical
interrupt vector is called - as this address is located in BIOS ROM, the BIOS
will always execute the following code before it forwards control to the user
handler:

```
  00000018  b      128h                ;IRQ vector: jump to actual BIOS handler
  00000128  stmfd  r13!,r0-r3,r12,r14  ;save registers to SP_irq
  0000012C  mov    r0,4000000h         ;ptr+4 to 03FFFFFC (mirror of 03007FFC)
  00000130  add    r14,r15,0h          ;retadr for USER handler $+8=138h
  00000134  ldr    r15,[r0,-4h]        ;jump to [03FFFFFC] USER handler
  00000138  ldmfd  r13!,r0-r3,r12,r14  ;restore registers from SP_irq
  0000013C  subs   r15,r14,4h          ;return from IRQ (PC=LR-4, CPSR=SPSR)
```

As shown above, a pointer to the 32bit/ARM-code user handler must be setup in
[03007FFCh]. By default, 160 bytes of memory are reserved for interrupt stack
at 03007F00h-03007F9Fh.



## Recommended User Interrupt handling


- If necessary switch to THUMB state manually (handler is called in ARM state)

- Determine reason(s) of interrupt by examining IF register

- User program may freely assign priority to each reason by own logic

- Process the most important reason of your choice

- User MUST manually acknowledge by writing to IF register

- If user wants to allow nested interrupts, save SPSR\_irq, then enable IRQs.

- If using other registers than BIOS-pushed R0-R3, manually save R4-R11 also.

- Note that Interrupt Stack is used (which may have limited size)

- So, for memory consuming stack operations use system mode (=user stack).

- When calling subroutines in system mode, save LSR\_usr also.

- Restore SPSR\_irq and/or R4-R11 if you've saved them above.

- Finally, return to BIOS handler by BX LR (R14\_irq) instruction.



## Default memory usage at 03007FXX (and mirrored to 03FFFFXX)


```
  Addr.    Size Expl.
  3007FFCh 4    Pointer to user IRQ handler (32bit ARM code)
  3007FF8h 2    Interrupt Check Flag (for IntrWait/VBlankIntrWait functions)
  3007FF4h 4    Allocated Area
  3007FF0h 4    Pointer to Sound Buffer
  3007FE0h 16   Allocated Area
  3007FA0h 64   Default area for SP_svc Supervisor Stack (4 words/time)
  3007F00h 160  Default area for SP_irq Interrupt Stack (6 words/time)
```

Memory below 7F00h is free for User Stack and user data. The three stack
pointers are initially initialized at the TOP of the respective areas:

```
  SP_svc=03007FE0h
  SP_irq=03007FA0h
  SP_usr=03007F00h
```

The user may redefine these addresses and move stacks into other locations,
however, the addresses for system data at 7FE0h-7FFFh are fixed.



## Not sure, is following free for user ?


Registers R8-R12\_fiq, R13\_fiq, R14\_fiq, SPSR\_fiq

Registers R13-R14\_abt, SPSR\_abt

Registers R13-R14\_und, SPSR\_und



## Fast Interrupt (FIQ)


The ARM CPU provides two interrupt sources, IRQ and FIQ. In the GBA only IRQ is
used. In normal GBAs, the FIQ signal is shortcut to VDD35, ie. the signal is
always high, and there is no way to generate a FIQ by hardware. The registers
R8..12\_fiq could be used by software (when switching into FIQ mode by writing
to CPSR) - however, this might make the game incompatible with hardware
debuggers (which are reportedly using FIQs for debugging purposes).
