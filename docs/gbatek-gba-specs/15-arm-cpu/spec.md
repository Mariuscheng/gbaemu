# ARM CPU Reference

> 本檔案整理自 [GBATEK](https://problemkaputt.de/gbatek.htm) 的「ARM CPU Reference」章節。
> 來源採用 [mGBA GBATEK Markdown fork](https://github.com/mgba-emu/gbatek) 的 Markdown 轉存，保留原文的暫存器、位元欄位、程式碼與數值表示法。

# ARM CPU Reference




## General ARM7TDMI Information


- [ARM CPU Overview](#armcpuoverview)
- [ARM CPU Register Set](#armcpuregisterset)
- [ARM CPU Flags & Condition Field (cond)](#armcpuflagsconditionfieldcond)
- [ARM CPU 26bit Memory Interface](#armcpu26bitmemoryinterface)
- [ARM CPU Exceptions](#armcpuexceptions)
- [ARM CPU Memory Alignments](#armcpumemoryalignments)


## ARM 32bit Instruction Set (ARM Code)


- [ARM Instruction Summary](#arminstructionsummary)
- [ARM Opcodes: Branch and Branch with Link (B, BL, BX, BLX, SWI, BKPT)](#armopcodesbranchandbranchwithlinkbblbxblxswibkpt)
- [ARM Opcodes: Data Processing (ALU)](#armopcodesdataprocessingalu)
- [ARM Opcodes: Multiply and Multiply-Accumulate (MUL, MLA)](#armopcodesmultiplyandmultiplyaccumulatemulmla)
- [ARM Opcodes: Special ARM9 Instructions (CLZ, QADD/QSUB)](#armopcodesspecialarm9instructionsclzqaddqsub)
- [ARM Opcodes: Special ARM11 Instructions (Misc)](#armopcodesspecialarm11instructionsmisc)
- [ARM Opcodes: Special ARM11 Instructions (SIMD)](#armopcodesspecialarm11instructionssimd)
- [ARM Opcodes: PSR Transfer (MRS, MSR)](#armopcodespsrtransfermrsmsr)
- [ARM Opcodes: Memory: Single Data Transfer (LDR, STR, PLD)](#armopcodesmemorysingledatatransferldrstrpld)
- [ARM Opcodes: Memory: Halfword, Doubleword, and Signed Data Transfer](#armopcodesmemoryhalfworddoublewordandsigneddatatransfer)
- [ARM Opcodes: Memory: Block Data Transfer (LDM, STM)](#armopcodesmemoryblockdatatransferldmstm)
- [ARM Opcodes: Memory: Single Data Swap (SWP)](#armopcodesmemorysingledataswapswp)
- [ARM Opcodes: Coprocessor Instructions (MRC/MCR, LDC/STC, CDP, MCRR/MRRC)](#armopcodescoprocessorinstructionsmrcmcrldcstccdpmcrrmrrc)


## ARM 16bit Instruction Set (THUMB Code)


When operating in THUMB state, cut-down 16bit opcodes are used.

THUMB is supported on T-variants of ARMv4 and up, ie. ARMv4T, ARMv5T, etc.

- [THUMB Instruction Summary](#thumbinstructionsummary)
- [THUMB Opcodes: Register Operations (ALU, BX)](#thumbopcodesregisteroperationsalubx)
- [THUMB Opcodes: Memory Load/Store (LDR/STR)](#thumbopcodesmemoryloadstoreldrstr)
- [THUMB Opcodes: Memory Addressing (ADD PC/SP)](#thumbopcodesmemoryaddressingaddpcsp)
- [THUMB Opcodes: Memory Multiple Load/Store (PUSH/POP and LDM/STM)](#thumbopcodesmemorymultipleloadstorepushpopandldmstm)
- [THUMB Opcodes: Jumps and Calls](#thumbopcodesjumpsandcalls)
- [THUMB Opcodes: New THUMB Opcodes in ARM11](#thumbopcodesnewthumbopcodesinarm11)


## Note


Switching between ARM and THUMB state can be done by using the Branch and
Exchange (BX) instruction.



## Further Information


- [ARM Classic vs UAL Syntax (Unified Assembler Language)](#armclassicvsualsyntaxunifiedassemblerlanguage)
- [ARM Pseudo Instructions and Directives](#armpseudoinstructionsanddirectives)
- [ARM CP15 System Control Coprocessor](#armcp15systemcontrolcoprocessor)
- [ARM Vector Floating-point Unit (VFP)](#armvectorfloatingpointunitvfp)
- [ARM CPU Instruction Cycle Times](#armcpuinstructioncycletimes)
- [ARM CPU Versions](#armcpuversions)
- [ARM CPU Data Sheet](#armcpudatasheet)



# ARM CPU Overview



The ARM7TDMI is a 32bit RISC (Reduced Instruction Set Computer) CPU, designed
by ARM (Advanced RISC Machines), and designed for both high performance and low
power consumption.



## Fast Execution


Depending on the CPU state, all opcodes are sized 32bit or 16bit (that's
counting both the opcode bits and its parameters bits) providing fast decoding
and execution. Additionally, pipelining allows - (a) one instruction to be
executed while (b) the next instruction is decoded and (c) the next instruction
is fetched from memory - all at the same time.



## Data Formats


The CPU manages to deal with 8bit, 16bit, and 32bit data, that are called:

```
   8bit - Byte
  16bit - Halfword
  32bit - Word
```



## The two CPU states


As mentioned above, two CPU states exist:

- ARM state: Uses the full 32bit instruction set (32bit opcodes)

- THUMB state: Uses a cutdown 16bit instruction set (16bit opcodes)

Regardless of the opcode-width, both states are using 32bit registers, allowing
32bit memory addressing as well as 32bit arithmetic/logical operations.



## When to use ARM state


Basically, there are two advantages in ARM state:

- - Each single opcode provides more functionality, resulting
    - in faster execution when using a 32bit bus memory system
    - (such like opcodes stored in GBA Work RAM).
- - All registers R0-R15 can be accessed directly.

The downsides are:

- - Not so fast when using 16bit memory system
    - (but it still works though).
- - Program code occupies more memory space.



## When to use THUMB state


There are two major advantages in THUMB state:

- - Faster execution up to approx 160% when using a 16bit bus
    - memory system (such like opcodes stored in GBA GamePak ROM).
- - Reduces code size, decreases memory overload down to approx 65%.

The disadvantages are:

- - Not as multi-functional opcodes as in ARM state, so it will
    - be sometimes required use more than one opcode to gain a
    - similar result as for a single opcode in ARM state.
- - Most opcodes allow only registers R0-R7 to be used directly.



## Combining ARM and THUMB state


Switching between ARM and THUMB state is done by a normal branch (BX)
instruction which takes only a handful of cycles to execute (allowing to change
states as often as desired - with almost no overload).


Also, as both ARM and THUMB are using the same register set, it is possible to
pass data between ARM and THUMB mode very easily.


The best memory & execution performance can be gained by combining both
states: THUMB for normal program code, and ARM code for timing critical
subroutines (such like interrupt handlers, or complicated algorithms).


Note: ARM and THUMB code cannot be executed simultaneously.



## Automatic state changes


Beside for the above manual state switching by using BX instructions, the
following situations involve automatic state changes:

- CPU switches to ARM state when executing an exception

- User switches back to old state when leaving an exception




# ARM CPU Register Set




## Overview


The following table shows the ARM7TDMI register set which is available in each
mode. There's a total of 37 registers (32bit each), 31 general registers (Rxx)
and 6 status registers (xPSR).

Note that only some registers are 'banked', for example, each mode has it's own
R14 register: called R14, R14\_fiq, R14\_svc, etc. for each mode respectively.

However, other registers are not banked, for example, each mode is using the
same R0 register, so writing to R0 will always affect the content of R0 in
other modes also.


```
  System/User FIQ       Supervisor Abort     IRQ       Undefined
  --------------------------------------------------------------
  R0          R0        R0         R0        R0        R0
  R1          R1        R1         R1        R1        R1
  R2          R2        R2         R2        R2        R2
  R3          R3        R3         R3        R3        R3
  R4          R4        R4         R4        R4        R4
  R5          R5        R5         R5        R5        R5
  R6          R6        R6         R6        R6        R6
  R7          R7        R7         R7        R7        R7
  --------------------------------------------------------------
  R8          R8_fiq    R8         R8        R8        R8
  R9          R9_fiq    R9         R9        R9        R9
  R10         R10_fiq   R10        R10       R10       R10
  R11         R11_fiq   R11        R11       R11       R11
  R12         R12_fiq   R12        R12       R12       R12
  R13 (SP)    R13_fiq   R13_svc    R13_abt   R13_irq   R13_und
  R14 (LR)    R14_fiq   R14_svc    R14_abt   R14_irq   R14_und
  R15 (PC)    R15       R15        R15       R15       R15
  --------------------------------------------------------------
  CPSR        CPSR      CPSR       CPSR      CPSR      CPSR
  --          SPSR_fiq  SPSR_svc   SPSR_abt  SPSR_irq  SPSR_und
  --------------------------------------------------------------
```



## R0-R12 Registers (General Purpose Registers)


These thirteen registers may be used for whatever general purposes. Basically,
each is having same functionality and performance, ie. there is no 'fast
accumulator' for arithmetic operations, and no 'special pointer register' for
memory addressing.

However, in THUMB mode only R0-R7 (Lo registers) may be accessed freely, while
R8-R12 and up (Hi registers) can be accessed only by some instructions.



## R13 Register (SP)


This register is used as Stack Pointer (SP) in THUMB state. While in ARM state
the user may decided to use R13 and/or other register(s) as stack pointer(s),
or as general purpose register.

As shown in the table above, there's a separate R13 register in each mode, and
(when used as SP) each exception handler may (and MUST!) use its own stack.



## R14 Register (LR)


This register is used as Link Register (LR). That is, when calling to a
sub-routine by a Branch with Link (BL) instruction, then the return address
(ie. old value of PC) is saved in this register.

Storing the return address in the LR register is obviously faster than pushing
it into memory, however, as there's only one LR register for each mode, the
user must manually push its content before issuing 'nested' subroutines.

Same happens when an exception is called, PC is saved in LR of new mode.

Note: In ARM mode, R14 may be used as general purpose register also, provided
that above usage as LR register isn't required.



## R15 Register (PC)


R15 is always used as program counter (PC). Note that when reading R15, this
will usually return a value of PC+nn because of read-ahead (pipelining),
whereas 'nn' depends on the instruction and on the CPU state (ARM or THUMB).



## CPSR and SPSR (Program Status Registers) (ARMv3 and up)


The current condition codes (flags) and CPU control bits are stored in the CPSR
register. When an exception arises, the old CPSR is saved in the SPSR of the
respective exception-mode (much like PC is saved in LR).

For details refer to chapter about CPU Flags.




# ARM CPU Flags & Condition Field (cond)




## ARM Condition Field {cond}


The opcode {cond} suffixes can be used for conditionally executed code based on
the C,N,Z,V flags in CPSR register. For example: BEQ = Branch if Equal, MOVMI =
Move if Signed.

In ARM mode, {cond} can be used with all opcodes (except for a few newer ARMv5
instructions: BKPT, PLD, CDP2, LDC2, MCR2, MRC2, STC2, and BLX\_imm are
nonconditional; however BLX\_reg can be conditional).

In THUMB mode, {cond} can be used only for branch opcodes.

```
  Code Suffix Flags         Meaning
  0:   EQ     Z=1           equal (zero) (same)
  1:   NE     Z=0           not equal (nonzero) (not same)
  2:   CS/HS  C=1           unsigned higher or same (carry set)
  3:   CC/LO  C=0           unsigned lower (carry cleared)
  4:   MI     N=1           signed negative (minus)
  5:   PL     N=0           signed positive or zero (plus)
  6:   VS     V=1           signed overflow (V set)
  7:   VC     V=0           signed no overflow (V cleared)
  8:   HI     C=1 and Z=0   unsigned higher
  9:   LS     C=0 or Z=1    unsigned lower or same
  A:   GE     N=V           signed greater or equal
  B:   LT     N<>V          signed less than
  C:   GT     Z=0 and N=V   signed greater than
  D:   LE     Z=1 or N<>V   signed less or equal
  E:   AL     -             always (the "AL" suffix can be omitted)
  F:   NV     -             never (ARMv1,v2 only) (Reserved ARMv3 and up)
```

Execution Time: If condition=false: 1S cycle. Otherwise: as specified for the
respective opcode.



## Current Program Status Register (CPSR)


```
  Bit   Expl.
  31    N - Sign Flag       (0=Not Signed, 1=Signed)               ;\
  30    Z - Zero Flag       (0=Not Zero, 1=Zero)                   ; Condition
  29    C - Carry Flag      (0=Borrow/No Carry, 1=Carry/No Borrow) ; Code Flags
  28    V - Overflow Flag   (0=No Overflow, 1=Overflow)            ;/
  27    Q - Sticky Overflow (1=Sticky Overflow, ARMv5TE and up only)
  26-25 Reserved            (For future use) - Do not change manually!
  24    J - Jazelle Mode    (1=Jazelle Bytecode instructions) (if supported)
  23-10 Reserved            (For future use) - Do not change manually!
  9     E - Endian          (... Big endian)                  (ARM11 ?)
  8     A - Abort disable   (1=Disable Imprecise Data Aborts) (ARM11 only)
  7     I - IRQ disable     (0=Enable, 1=Disable)                     ;\
  6     F - FIQ disable     (0=Enable, 1=Disable)                     ; Control
  5     T - State Bit       (0=ARM, 1=THUMB) - Do not change manually!; Bits
  4-0   M4-M0 - Mode Bits   (See below)                               ;/
```



## Bit 31-28: Condition Code Flags (N,Z,C,V)


These bits reflect results of logical or arithmetic instructions. In ARM mode,
it is often optionally whether an instruction should modify flags or not, for
example, it is possible to execute a SUB instruction that does NOT modify the
condition flags.

In ARM state, all instructions can be executed conditionally depending on the
settings of the flags, such like MOVEQ (Move if Z=1). While In THUMB state,
only Branch instructions (jumps) can be made conditionally.



## Bit 27: Sticky Overflow Flag (Q) - ARMv5TE and ARMv5TExP and up only


Used by QADD, QSUB, QDADD, QDSUB, SMLAxy, and SMLAWy only. These opcodes set
the Q-flag in case of overflows, but leave it unchanged otherwise. The Q-flag
can be tested/reset by MSR/MRS opcodes only.



## Bit 27-8: Reserved Bits (except Bit 27 on ARMv5TE and up, see above)


These bits are reserved for possible future implementations. For best forwards
compatibility, the user should never change the state of these bits, and should
not expect these bits to be set to a specific value.



## Bit 7-0: Control Bits (I,F,T,M4-M0)


These bits may change when an exception occurs. In privileged modes (non-user
modes) they may be also changed manually.

The interrupt bits I and F are used to disable IRQ and FIQ interrupts
respectively (a setting of "1" means disabled).

The T Bit signalizes the current state of the CPU (0=ARM, 1=THUMB), this bit
should never be changed manually - instead, changing between ARM and THUMB
state must be done by BX instructions.

The Mode Bits M4-M0 contain the current operating mode.

```
  Binary Hex Dec  Expl.
  0xx00b 00h 0  - Old User       ;\26bit Backward Compatibility modes
  0xx01b 01h 1  - Old FIQ        ; (supported only on ARMv3, except ARMv3G,
  0xx10b 02h 2  - Old IRQ        ; and on some non-T variants of ARMv4)
  0xx11b 03h 3  - Old Supervisor ;/
  10000b 10h 16 - User (non-privileged)
  10001b 11h 17 - FIQ
  10010b 12h 18 - IRQ
  10011b 13h 19 - Supervisor (SWI)
  10111b 17h 23 - Abort
  11011b 1Bh 27 - Undefined
  11111b 1Fh 31 - System (privileged 'User' mode) (ARMv4 and up)
```

Writing any other values into the Mode bits is not allowed.



## Saved Program Status Registers (SPSR\_\<mode>)


Additionally to above CPSR, five Saved Program Status Registers exist:

SPSR\_fiq, SPSR\_svc, SPSR\_abt, SPSR\_irq, SPSR\_und

Whenever the CPU enters an exception, the current status register (CPSR) is
copied to the respective SPSR\_\<mode> register. Note that there is only
one SPSR for each mode, so nested exceptions inside of the same mode are
allowed only if the exception handler saves the content of SPSR in memory.

For example, for an IRQ exception: IRQ-mode is entered, and CPSR is copied to
SPSR\_irq. If the interrupt handler wants to enable nested IRQs, then it must
first push SPSR\_irq before doing so.




# ARM CPU 26bit Memory Interface



The 26bit Memory Interface was used by ARMv1 and ARMv2. The 32bit interface is
used by ARMv3 and newer, however, 26bit backward compatibility was included in
all ARMv3 (except ARMv3G), and optionally in some non-T variants of ARMv4.



## Format of R15 in 26bit Mode (Program Counter Register)


```
  Bit   Name     Expl.
  31-28 N,Z,C,V  Flags (Sign, Zero, Carry, Overflow)
  27-26 I,F      Interrupt Disable bits (IRQ, FIQ) (1=Disable)
  25-2  PC       Program Counter, 24bit, Step 4 (64M range)
  1-0   M1,M0    Mode (0=User, 1=FIQ, 2=IRQ, 3=Supervisor)
```

Branches with +/-32M range wrap the PC register, and can reach all 64M memory.



## Reading from R15


If R15 is specified in bit16-19 of an opcode, then NZCVIF and M0,1 are masked
(zero), otherwise the full 32bits are used.



## Writing to R15


ALU opcodes with S=1, and LDM opcodes with PSR=1 can write to all 32bits in R15
(in 26bit mode, that is allowed even in user mode, though it does then affect
only NZCF, not the write protected IFMM bits ???), other opcodes which write to
R15 will modify only the program counter bits. Also, special CMP/CMN/TST/TEQ{P}
opcodes can be used to write to the PSR bits in R15 without modifying the PC
bits.



## Exceptions


SWIs, Reset, Data/Prefetch Aborts and Undefined instructions enter Supervisor
mode. Interrupts enter IRQ and FIQ mode. Additionally, a special 26bit Address
Exception exists, which enters Supervisor mode on accesses to memory
addresses>=64M as follows:

```
  R14_svc = PC ($+8, including old PSR bits)
  M1,M0 = 11b = supervisor mode, F=same, I=1, PC=14h,
  to continue at the fault location, return by SUBS PC,LR,8.
```

32bit CPUs with 26bit compatibility mode can be configured to switch into 32bit
mode when encountering exceptions.




# ARM CPU Exceptions




## Exception Vectors


The following are the exception vectors in memory. That is, when an exception
arises, CPU is switched into ARM state, and the program counter (PC) is loaded
by the respective address.

```
  Address  Prio  Exception                  Mode on Entry      Interrupt Flags
  BASE+00h 1     Reset                      Supervisor (_svc)  I=1, F=1
  BASE+04h 7     Undefined Instruction      Undefined  (_und)  I=1, F=unchanged
  BASE+08h 6     Software Interrupt (SWI)   Supervisor (_svc)  I=1, F=unchanged
  BASE+0Ch 5     Prefetch Abort             Abort      (_abt)  I=1, F=unchanged
  BASE+10h 2     Data Abort                 Abort      (_abt)  I=1, F=unchanged
  BASE+14h ??    Address Exceeds 26bit      Supervisor (_svc)  I=1, F=unchanged
  BASE+18h 4     Normal Interrupt (IRQ)     IRQ        (_irq)  I=1, F=unchanged
  BASE+1Ch 3     Fast Interrupt (FIQ)       FIQ        (_fiq)  I=1, F=1
```

BASE is normally 00000000h, but may be optionally FFFF0000h in some ARM CPUs.
Priority for simultaneously occuring exceptions ranges from Prio=1=Highest to
Prio=7=Lowest.

As there's only space for one ARM opcode at each of the above addresses, it'd
be usually recommended to deposit a Branch opcode into each vector, which'd
then redirect to the actual exception handlers address.



## Actions performed by CPU when entering an exception


```
  - R14_<new mode>=PC+nn   ;save old PC, ie. return address
  - SPSR_<new mode>=CPSR   ;save old flags
  - CPSR new T,M bits      ;set to T=0 (ARM state), and M4-0=new mode
  - CPSR new I bit         ;IRQs disabled (I=1), done by ALL exceptions
  - CPSR new F bit         ;FIQs disabled (F=1), done by Reset and FIQ only
  - PC=exception_vector    ;see table above
```

Above "PC+nn" depends on the type of exception. Basically, in ARM state that
nn-offset is caused by pipelining, and in THUMB state an identical ARM-style
'offset' is generated (even though the 'base address' may be only
halfword-aligned).



## Required user-handler actions when returning from an exception


Restore any general registers (R0-R14) which might have been modified by the
exception handler. Use return-instruction as listed in the respective
descriptions below, this will both restore PC and CPSR - that automatically
involves that the old CPU state (THUMB or ARM) as well as old state of FIQ and
IRQ disable flags are restored.

As mentioned above (see action on entering...), the return address is always
saved in ARM-style format, so that exception handler may use the same
return-instruction, regardless of whether the exception has been generated from
inside of ARM or THUMB state.



## FIQ (Fast Interrupt Request)


This interrupt is generated by a LOW level on the nFIQ input. It is supposed to
process timing critical interrupts at a high priority, as fast as possible.

Additionally to the common banked registers (R13\_fiq,R14\_fiq), five extra
banked registers (R8\_fiq-R12\_fiq) are available in FIQ mode. The exception
handler may freely access these registers without modifying the main programs
R8-R12 registers (and without having to save that registers on stack).

In privileged (non-user) modes, FIQs may be also manually disabled by setting
the F Bit in CPSR.



## IRQ (Normal Interrupt Request)


This interrupt is generated by a LOW level on the nIRQ input. Unlike FIQ, the
IRQ mode is not having its own banked R8-R12 registers.

IRQ is having lower priority than FIQ, and IRQs are automatically disabled when
a FIQ exception becomes executed. In privileged (non-user) modes, IRQs may be
also manually disabled by setting the I Bit in CPSR.

To return from IRQ Mode (continuing at following opcode):

```
  SUBS PC,R14,4   ;both PC=R14_irq-4, and CPSR=SPSR_irq
```



## Software Interrupt


Generated by a software interrupt instruction (SWI). Recommended to request a
supervisor (operating system) function. The SWI instruction may also contain a
parameter in the 'comment field' of the opcode:

In case that your main program issues SWIs from both inside of THUMB and ARM
states, then your exception handler must separate between 24bit comment fields
in ARM opcodes, and 8bit comment fields in THUMB opcodes (if necessary
determine old state by examining T Bit in SPSR\_svc); However, in Little Endian
mode, you could use only the most significant 8bits of the 24bit ARM comment
field (as done in the GBA, for example) - the exception handler could then
process the BYTE at [R14-2], regardless of whether it's been called from ARM or
THUMB state.

To return from Supervisor Mode (continuing at following opcode):

```
  MOVS PC,R14   ;both PC=R14_svc, and CPSR=SPSR_svc
```

Note: Like all other exceptions, SWIs are always executed in ARM state, no
matter whether it's been caused by an ARM or THUMB state SWI instruction.



## Undefined Instruction Exception (supported by ARMv3 and up)


This exception is generated when the CPU comes across an instruction which it
cannot handle. Most likely signalizing that the program has locked up, and that
an errormessage should be displayed.

However, it might be also used to emulate custom functions, ie. as an
additional 'SWI' instruction (which'd use R14\_und and SPSR\_und though, and it'd
thus allow to execute the Undefined Instruction handler from inside of
Supervisor mode without having to save R14\_svc and SPSR\_svc).

To return from Undefined Mode (continuing at following opcode):

```
  MOVS PC,R14   ;both PC=R14_und, and CPSR=SPSR_und
```

Note that not all unused opcodes are necessarily producing an exception, for
example, an ARM state Multiply instruction with Bit6=1 would be blindly
accepted as 'legal' opcode.



## Abort (supported by ARMv3 and up)


Aborts (page faults) are mostly supposed for virtual memory systems (ie. not
used in GBA, as far as I know), otherwise they might be used just to display an
error message. Two types of aborts exists:

- Prefetch Abort (occurs during an instruction prefetch)

- Prefetch Abort (also occurs on BKPT opcodes, ARMv5 and up)

- Data Abort (occurs during a data access)

A virtual memory systems abort handler would then most likely determine the
fault address: For prefetch abort that's just "R14\_abt-4". For Data abort, the
THUMB or ARM instruction at "R14\_abt-8" needs to be 'disassembled' in order to
determine the addressed data in memory.

The handler would then fix the error by loading the respective memory page into
physical memory, and then retry to execute the SAME instruction again, by
returning as follows:

```
  prefetch abort: SUBS PC,R14,#4   ;PC=R14_abt-4, and CPSR=SPSR_abt
  data abort:     SUBS PC,R14,#8   ;PC=R14_abt-8, and CPSR=SPSR_abt
```

Separate exception vectors for prefetch/data abort exists, each should use the
respective return instruction as shown above.



## Address Exceeds 26bit


This exception can occur only on old ARM CPUs with 26bit address scheme (or in
26bit backwards compatibility mode).



## Reset


Forces PC=VVVV0000h, and forces control bits of CPSR to T=0 (ARM state), F=1
and I=1 (disable FIQ and IRQ), and M4-0=10011b (Supervisor mode).




# ARM CPU Memory Alignments



The CPU does NOT support accessing mis-aligned addresses (which would be rather
slow because it'd have to merge/split that data into two accesses).

When reading/writing code/data to/from memory, Words and Halfwords must be
located at well-aligned memory address, ie. 32bit words aligned by 4, and 16bit
halfwords aligned by 2.



## Mis-aligned STR,STRH,STM,LDM,LDRD,STRD,PUSH,POP (forced align)


The mis-aligned low bit(s) are ignored, the memory access goes to a forcibly
aligned (rounded-down) memory address.

For LDRD/STRD, it isn't clearly defined if the address must be aligned by 8 (on
the NDS, align-4 seems to be okay) (align-8 may be required on other CPUs with
64bit databus).



## Mis-aligned LDR,SWP (rotated read)


Reads from forcibly aligned address "addr AND (NOT 3)", and does then rotate
the data as "ROR (addr AND 3)\*8". That effect is internally used by LDRB and
LDRH opcodes (which do then mask-out the unused bits).

The SWP opcode works like a combination of LDR and STR, that means, it does
read-rotated, but does write-unrotated.



## Mis-aligned LDRH,LDRSH (does or does not do strange things)


On ARM9 aka ARMv5 aka NDS9:

```
  LDRH Rd,[odd]   -->  LDRH Rd,[odd-1]        ;forced align
  LDRSH Rd,[odd]  -->  LDRSH Rd,[odd-1]       ;forced align
```

On ARM7 aka ARMv4 aka NDS7/GBA:

```
  LDRH Rd,[odd]   -->  LDRH Rd,[odd-1] ROR 8  ;read to bit0-7 and bit24-31
  LDRSH Rd,[odd]  -->  LDRSB Rd,[odd]         ;sign-expand BYTE value
```



## Mis-aligned PC/R15 (branch opcodes, or MOV/ALU/LDR with Rd=R15)


For ARM code, the low bits of the target address should be usually zero,
otherwise, R15 is forcibly aligned by clearing the lower two bits.

For THUMB code, the low bit of the target address may/should/must be set, the
bit is (or is not) interpreted as thumb-bit (depending on the opcode), and R15
is then forcibly aligned by clearing the lower bit.

In short, R15 will be always forcibly aligned, so mis-aligned branches won't
have effect on subsequent opcodes that use R15, or [R15+disp] as operand.




# ARM Instruction Summary



Modification of CPSR flags is optional for all {S} instructions.



## Logical ALU Operations


```
  Instruction                      Cycles   Flags  Expl.
  MOV{cond}{S} Rd,Op2              1S+x+y    NZc-  Rd = Op2
  MVN{cond}{S} Rd,Op2              1S+x+y    NZc-  Rd = NOT Op2
  ORR{cond}{S} Rd,Rn,Op2           1S+x+y    NZc-  Rd = Rn OR Op2
  EOR{cond}{S} Rd,Rn,Op2           1S+x+y    NZc-  Rd = Rn XOR Op2
  AND{cond}{S} Rd,Rn,Op2           1S+x+y    NZc-  Rd = Rn AND Op2
  BIC{cond}{S} Rd,Rn,Op2           1S+x+y    NZc-  Rd = Rn AND NOT Op2
  TST{cond}{P}    Rn,Op2           1S+x      NZc-  Void = Rn AND Op2
  TEQ{cond}{P}    Rn,Op2           1S+x      NZc-  Void = Rn XOR Op2
```

Add x=1I cycles if Op2 shifted-by-register. Add y=1S+1N cycles if Rd=R15.

Carry flag affected only if Op2 contains a non-zero shift amount.



## Arithmetic ALU Operations


```
  Instruction                      Cycles   Flags  Expl.
  ADD{cond}{S} Rd,Rn,Op2           1S+x+y    NZCV  Rd = Rn+Op2
  ADC{cond}{S} Rd,Rn,Op2           1S+x+y    NZCV  Rd = Rn+Op2+Cy
  SUB{cond}{S} Rd,Rn,Op2           1S+x+y    NZCV  Rd = Rn-Op2
  SBC{cond}{S} Rd,Rn,Op2           1S+x+y    NZCV  Rd = Rn-Op2+Cy-1
  RSB{cond}{S} Rd,Rn,Op2           1S+x+y    NZCV  Rd = Op2-Rn
  RSC{cond}{S} Rd,Rn,Op2           1S+x+y    NZCV  Rd = Op2-Rn+Cy-1
  CMP{cond}{P}    Rn,Op2           1S+x      NZCV  Void = Rn-Op2
  CMN{cond}{P}    Rn,Op2           1S+x      NZCV  Void = Rn+Op2
```

Add x=1I cycles if Op2 shifted-by-register. Add y=1S+1N cycles if Rd=R15.



## Multiply


```
  Instruction                      Cycles   Flags  Expl.
  MUL{cond}{S} Rd,Rm,Rs            1S+mI     NZx-  Rd = Rm*Rs
  MLA{cond}{S} Rd,Rm,Rs,Rn         1S+mI+1I  NZx-  Rd = Rm*Rs+Rn
  UMULL{cond}{S} RdLo,RdHi,Rm,Rs   1S+mI+1I  NZx-  RdHiLo = Rm*Rs
  UMLAL{cond}{S} RdLo,RdHi,Rm,Rs   1S+mI+2I  NZx-  RdHiLo = Rm*Rs+RdHiLo
  SMULL{cond}{S} RdLo,RdHi,Rm,Rs   1S+mI+1I  NZx-  RdHiLo = Rm*Rs
  SMLAL{cond}{S} RdLo,RdHi,Rm,Rs   1S+mI+2I  NZx-  RdHiLo = Rm*Rs+RdHiLo
  SMLAxy{cond}  Rd,Rm,Rs,Rn     ARMv5TE(xP)  ----q Rd=HalfRm*HalfRs+Rn
  SMLAWy{cond}  Rd,Rm,Rs,Rn     ARMv5TE(xP)  ----q Rd=(Rm*HalfRs)/10000h+Rn
  SMULWy{cond}  Rd,Rm,Rs        ARMv5TE(xP)  ----  Rd=(Rm*HalfRs)/10000h
  SMLALxy{cond} RdLo,RdHi,Rm,Rs ARMv5TE(xP)  ----  RdHiLo=RdHiLo+HalfRm*HalfRs
  SMULxy{cond}  Rd,Rm,Rs        ARMv5TE(xP)  ----  Rd=HalfRm*HalfRs
```



## Memory Load/Store


```
  Instruction                      Cycles    Flags  Expl.
  LDR{cond}{B}{T} Rd,<Address>     1S+1N+1I+y ----  Rd=[Rn+/-<offset>]
  LDR{cond}H      Rd,<Address>     1S+1N+1I+y ----  Load Unsigned halfword
  LDR{cond}D      Rd,<Address>                ----  Load Dword ARMv5TE
  LDR{cond}SB     Rd,<Address>     1S+1N+1I+y ----  Load Signed byte
  LDR{cond}SH     Rd,<Address>     1S+1N+1I+y ----  Load Signed halfword
  LDM{cond}{amod} Rn{!},<Rlist>{^} nS+1N+1I+y ----  Load Multiple
  STR{cond}{B}{T} Rd,<Address>     2N         ----  [Rn+/-<offset>]=Rd
  STR{cond}H      Rd,<Address>     2N         ----  Store halfword
  STR{cond}D      Rd,<Address>                ----  Store Dword ARMv5TE
  STM{cond}{amod} Rn{!},<Rlist>{^} (n-1)S+2N  ----  Store Multiple
  SWP{cond}{B}    Rd,Rm,[Rn]       1S+2N+1I   ----  Rd=[Rn], [Rn]=Rm
  PLD             <Address>        1S         ----  Prepare Cache ARMv5TE
```

For LDR/LDM, add y=1S+1N if Rd=R15, or if R15 in Rlist.



## Jumps, Calls, CPSR Mode, and others


```
  Instruction                  Cycles  Flags  Expl.
  B{cond}   label              2S+1N    ----  PC=$+8+/-32M
  BL{cond}  label              2S+1N    ----  PC=$+8+/-32M, LR=$+4
  BX{cond}  Rn                 2S+1N    ----  PC=Rn, T=Rn.0 (THUMB/ARM)
  BLX{cond} Rn                 2S+1N    ----  PC=Rn, T=Rn.0, LR=PC+4, ARM9
  BLX       label              2S+1N    ----  PC=PC+$+/-32M, LR=$+4, T=1, ARM9
  MRS{cond} Rd,Psr             1S       ----  Rd=Psr
  MSR{cond} Psr{_field},Op     1S      (psr)  Psr[field]=Op
  SWI{cond} Imm24bit           2S+1N    ----  PC=8, ARM Svc mode, LR=$+4
  BKPT      Imm16bit           ???      ----  PC=C, ARM Abt mode, LR=$+4 ARM9
  The Undefined Instruction    2S+1I+1N ----  PC=4, ARM Und mode, LR=$+4
  cond=false                   1S       ----  Any opcode with condition=false
  NOP                          1S       ----  R0=R0
```


```
  CLZ{cond} Rd,Rm              ???      ----    Count Leading Zeros ARMv5
  QADD{cond} Rd,Rm,Rn                   ----q   Rd=Rm+Rn       ARMv5TE(xP)
  QSUB{cond} Rd,Rm,Rn                   ----q   Rd=Rm-Rn       ARMv5TE(xP)
  QDADD{cond} Rd,Rm,Rn                  ----q   Rd=Rm+Rn*2     ARMv5TE(xP)
  QDSUB{cond} Rd,Rm,Rn                  ----q   Rd=Rm-Rn*2     ARMv5TE(xP)
```



## Coprocessor Functions (if any)


```
  Instruction                         Cycles  Flags  Expl.
  CDP{cond} Pn,<cpopc>,Cd,Cn,Cm{,<cp>} 1S+bI   ----  Coprocessor specific
  STC{cond}{L} Pn,Cd,<Address>         (n-1)S+2N+bI  [address] = CRd
  LDC{cond}{L} Pn,Cd,<Address>         (n-1)S+2N+bI  CRd = [address]
  MCR{cond} Pn,<cpopc>,Rd,Cn,Cm{,<cp>} 1S+bI+1C      CRn = Rn {<op> CRm}
  MRC{cond} Pn,<cpopc>,Rd,Cn,Cm{,<cp>} 1S+(b+1)I+1C  Rn = CRn {<op> CRm}
  CDP2,STC2,LDC2,MCR2,MRC2 - ARMv5 Extensions similar above, without {cond}
  MCRR{cond} Pn,<cpopc>,Rd,Rn,Cm  ;write Rd,Rn to coproc ARMv5TE
  MRRC{cond} Pn,<cpopc>,Rd,Rn,Cm  ;read Rd,Rn from coproc ARMv5TE
```



## ARM Binary Opcode Format


```
  |..3 ..................2 ..................1 ..................0|
  |1_0_9_8_7_6_5_4_3_2_1_0_9_8_7_6_5_4_3_2_1_0_9_8_7_6_5_4_3_2_1_0|
  |_Cond__|0_0_0|___Op__|S|__Rn___|__Rd___|__Shift__|Typ|0|__Rm___| DataProc
  |_Cond__|0_0_0|___Op__|S|__Rn___|__Rd___|__Rs___|0|Typ|1|__Rm___| DataProc
  |_Cond__|0_0_1|___Op__|S|__Rn___|__Rd___|_Shift_|___Immediate___| DataProc
  |_Cond__|0_0_1_1_0_0_1_0_0_0_0_0_1_1_1_1_0_0_0_0|_____Hint______| ARM11:Hint
  |_Cond__|0_0_1_1_0|P|1|0|_Field_|__Rd___|_Shift_|___Immediate___| PSR Imm
  |_Cond__|0_0_0_1_0|P|L|0|_Field_|__Rd___|0_0_0_0|0_0_0_0|__Rm___| PSR Reg
  |_Cond__|0_0_0_1_0_0_1_0_1_1_1_1_1_1_1_1_1_1_1_1|0_0|L|1|__Rn___| BX,BLX
  |1_1_1_0|0_0_0_1_0_0_1_0|_____immediate_________|0_1_1_1|_immed_| ARM9:BKPT
  |_Cond__|0_0_0_1_0_1_1_0_1_1_1_1|__Rd___|1_1_1_1|0_0_0_1|__Rm___| ARM9:CLZ
  |_Cond__|0_0_0_1_0|Op_|0|__Rn___|__Rd___|0_0_0_0|0_1_0_1|__Rm___| ARM9:QALU
  |_Cond__|0_0_0_0_0_0|A|S|__Rd___|__Rn___|__Rs___|1_0_0_1|__Rm___| Multiply
  |_Cond__|0_0_0_0_0_1_0_0|_RdHi__|_RdLo__|__Rs___|1_0_0_1|__Rm___| ARM11:UMAAL
  |_Cond__|0_0_0_0_1|U|A|S|_RdHi__|_RdLo__|__Rs___|1_0_0_1|__Rm___| MulLong
  |_Cond__|0_0_0_1_0|Op_|0|Rd/RdHi|Rn/RdLo|__Rs___|1|y|x|0|__Rm___| MulHalfARM9
  |_Cond__|0_0_0_1_0|B|0_0|__Rn___|__Rd___|0_0_0_0|1_0_0_1|__Rm___| TransSwp12
  |_Cond__|0_0_0_1_1|_Op__|__Rn___|__Rd___|1_1_1_1|1_0_0_1|__Rm___| ARM11:LDREX
  |_Cond__|0_0_0|P|U|0|W|L|__Rn___|__Rd___|0_0_0_0|1|S|H|1|__Rm___| TransReg10
  |_Cond__|0_0_0|P|U|1|W|L|__Rn___|__Rd___|OffsetH|1|S|H|1|OffsetL| TransImm10
  |_Cond__|0_1_0|P|U|B|W|L|__Rn___|__Rd___|_________Offset________| TransImm9
  |_Cond__|0_1_1|P|U|B|W|L|__Rn___|__Rd___|__Shift__|Typ|0|__Rm___| TransReg9
  |_Cond__|0_1_1|________________xxx____________________|1|__xxx__| Undefined
  |_Cond__|0_1_1|Op_|x_x_x_x_x_x_x_x_x_x_x_x_x_x_x_x_x_x|1|x_x_x_x| ARM11:Media
  |1_1_1_1_0_1_0_1_0_1_1_1_1_1_1_1_1_1_1_1_0_0_0_0_0_0_0_1_1_1_1_1| ARM11:CLREX
  |_Cond__|1_0_0|P|U|S|W|L|__Rn___|__________Register_List________| BlockTrans
  |_Cond__|1_0_1|L|___________________Offset______________________| B,BL,BLX
  |_Cond__|1_1_0|P|U|N|W|L|__Rn___|__CRd__|__CP#__|____Offset_____| CoDataTrans
  |_Cond__|1_1_0_0_0_1_0|L|__Rn___|__Rd___|__CP#__|_CPopc_|__CRm__| CoRR ARM9
  |_Cond__|1_1_1_0|_CPopc_|__CRn__|__CRd__|__CP#__|_CP__|0|__CRm__| CoDataOp
  |_Cond__|1_1_1_0|CPopc|L|__CRn__|__Rd___|__CP#__|_CP__|1|__CRm__| CoRegTrans
  |_Cond__|1_1_1_1|_____________Ignored_by_Processor______________| SWI
```



## ARM11 SIMD Media instructions (ARM11/ARMv6) (formerly Undef opcode space)


```
  |..3 ..................2 ..................1 ..................0|
  |1_0_9_8_7_6_5_4_3_2_1_0_9_8_7_6_5_4_3_2_1_0_9_8_7_6_5_4_3_2_1_0|
  |_Cond__|0_1_1|0_0|_Op__|__Rn___|__Rd___|1_1_1_1|_Op__|1|__Rm___| ParaAddSub
  |_Cond__|0_1_1|0_1|0_0_0|__Rn___|__Rd___|_shift___|x|0_1|__Rm___| HalfPack
  |_Cond__|0_1_1|0_1|U|1|____sat__|__Rd___|_shift___|x|0_1|__Rm___| WordSat
  |_Cond__|0_1_1|0_1|U|1_0|__sat__|__Rd___|1_1_1_1|0_0_1_1|__Rm___| ParaHalfSat
  |_Cond__|0_1_1|0_1|0_1_1|1_1_1_1|__Rd___|1_1_1_1|0_0_1_1|__Rm___| RevWord
  |_Cond__|0_1_1|0_1|0_1_1|1_1_1_1|__Rd___|1_1_1_1|1_0_1_1|__Rm___| RevPackHalf
  |_Cond__|0_1_1|0_1|1_1_1|1_1_1_1|__Rd___|1_1_1_1|1_0_1_1|__Rm___| RevSignHalf
  |_Cond__|0_1_1|0_1|0_0_0|__Rn___|__Rd___|1_1_1_1|1_0_1_1|__Rm___| SelectBytes
  |_Cond__|0_1_1|0_1|_Op__|__Rn___|__Rd___|rot|0_0|0_1_1_1|__Rm___| Extend U/S
  |_Cond__|0_1_1|1_0|_Op__|Rd/RdHi|Rn/RdLo|__Rs___|_Op__|1|__Rm___| Multiplies
  |_Cond__|0_1_1|1_1|0_0_0|__Rd___|__Rn___|__Rs___|0_0_0_1|__Rm___| DiffSum
  |_Cond__|0_1_1|1_1|0_0_0|__Rd___|1_1_1_1|__Rs___|0_0_0_1|__Rm___| DiffSumAcc
  |_Cond__|0_1_1_1_1_1_1_1|x_x_x_x_x_x_x_x_x_x_x_x|1_1_1_1|x_x_x_x| Undef
```




# ARM Opcodes: Branch and Branch with Link (B, BL, BX, BLX, SWI, BKPT)




## Branch and Branch with Link (B, BL, BLX\_imm)


Branch (B) is supposed to jump to a subroutine. Branch with Link is meant to be
used to call to a subroutine, return address is then saved in R14.

```
  Bit    Expl.
  31-28  Condition (must be 1111b for BLX)
  27-25  Must be "101" for this instruction
  24     Opcode (0-1) (or Halfword Offset for BLX)
          0: B{cond} label    ;branch            PC=PC+8+nn*4
          1: BL{cond} label   ;branch/link       PC=PC+8+nn*4, LR=PC+4
          H: BLX label ;ARM9  ;branch/link/thumb PC=PC+8+nn*4+H*2, LR=PC+4, T=1
  23-0   nn - Signed Offset, step 4      (-32M..+32M in steps of 4)
```

Branch with Link can be used to 'call' to a sub-routine, which may then
'return' by MOV PC,R14 for example.

Execution Time: 2S + 1N

Return: No flags affected.



## Branch and Exchange (BX, BLX\_reg)


```
  Bit    Expl.
  31-28  Condition
  27-8   Must be "0001.0010.1111.1111.1111" for this instruction
  7-4    Opcode
          0001b: BX{cond}  Rn    ;PC=Rn, T=Rn.0   (ARMv4T and ARMv5 and up)
          0010b: BXJ{cond} Rn    ;Change to Jazelle bytecode (ARMv5TEJ and up)
          0011b: BLX{cond} Rn    ;PC=Rn, T=Rn.0, LR=PC+4     (ARMv5 and up)
  3-0    Rn - Operand Register  (R0-R14)
```

Switching to THUMB Mode: Set Bit 0 of the value in Rn to 1, program continues
then at Rn-1 in THUMB mode.

Using BLX R14 is possible (sets PC=Old\_LR, and New\_LR=retadr).

Using BX R15 acts as BX $+8 (tested and working on ARM7/ARM9, although it isn't
officially defined as predictable behaviour).

Execution Time: 2S + 1N

Return: No flags affected.



## Notes on BXJ (Branch or change to Jazelle bytecode state):


If Jazelle is suppored/enabled: Executes Java bytecode at address R14

If Jazelle is NOT suppored/enabled: Behaves exactly same as BX Rn

That is, R14 is the byte code address, and Rn is an ARM/THUMB error handler.

Supported on ARMv5TEJ and ARMv6 and up.



## Branch via ALU, LDR, LDM


Most ALU, LDR, LDM opcodes can also change PC/R15.



## Software Interrupt (SWI/BKPT) (svc/abt exceptions)


SWI supposed for calls to the operating system - Enter Supervisor mode (SVC) in
ARM state. BKPT intended for debugging - enters Abort mode in ARM state via
Prefetch Abort vector.

```
  Bit    Expl.
  31-28  Condition (must be 1110b for BKPT, ie. Condition=always)
  27-24  Opcode
          1111b: SWI{cond} nn   ;software interrupt
          0001b: BKPT      nn   ;breakpoint (ARMv5 and up)
  For SWI:
   23-0   nn - Comment Field, ignored by processor (24bit value)
  For BKPT:
   23-20  Must be 0010b for BKPT
   19-8   nn - upper 12bits of comment field, ignored by processor
   7-4    Must be 0111b for BKPT
   3-0    nn - lower 4bits of comment field, ignored by processor
```

Execution Time: 2S+1N

The exception handler may interprete the SWI Comment Field by examining the
lower 24bit of the 32bit opcode opcode at [R14\_svc-4]. If your are also using
SWI's from inside of THUMB, then the SWI handler must examine the T Bit
SPSR\_svc in order to determine whether it's been a THUMB SWI - and if so,
examine the lower 8bit of the 16bit opcode opcode at [R14\_svc-2].

For Returning from SWI use "MOVS PC,R14", that instruction does restore both PC
and CPSR, ie. PC=R14\_svc, and CPSR=SPSR\_svc.

Nesting SWIs: SPSR\_svc and R14\_svc should be saved on stack before either
invoking nested SWIs, or (if the IRQ handler uses SWIs) before enabling IRQs.

Execution SWI/BKPT:

```
  R14_svc=PC+4     R14_abt=PC+4   ;save return address
  SPSR_svc=CPSR    SPSR_abt=CPSR  ;save CPSR flags
  CPSR=<changed>   CPSR=<changed> ;Enter svc/abt, ARM state, IRQs disabled
  PC=VVVV0008h     PC=VVVV000Ch   ;jump to SWI/PrefetchAbort vector address
```



## Undefined Instruction (und exception)


```
  Bit    Expl.
  31-28  Condition
  27-25  Must be 011b for this instruction
  24-5   Reserved for future use
  4      Must be 1b for this instruction
  3-0    Reserved for future use
```

No assembler mnemonic exists, following bitstreams are (not) reserved.

```
  cond011xxxxxxxxxxxxxxxxxxxx1xxxx - reserved for future use (except below).
  cond01111111xxxxxxxxxxxx1111xxxx - free for user.
```

Note: ARMv6 does use the "reserved for future" space for the new SIMD opcodes
(but still has the "free for user" space available as "undefined").

Execution time: 2S+1I+1N.




# ARM Opcodes: Data Processing (ALU)




## Opcode Format


```
  Bit    Expl.
  31-28  Condition
  27-26  Must be 00b for this instruction
  25     I - Immediate 2nd Operand Flag (0=Register, 1=Immediate)
  24-21  Opcode (0-Fh)               ;*=Arithmetic, otherwise Logical
           0: AND{cond}{S} Rd,Rn,Op2    ;AND logical       Rd = Rn AND Op2
           1: EOR{cond}{S} Rd,Rn,Op2    ;XOR logical       Rd = Rn XOR Op2
           2: SUB{cond}{S} Rd,Rn,Op2 ;* ;subtract          Rd = Rn-Op2
           3: RSB{cond}{S} Rd,Rn,Op2 ;* ;subtract reversed Rd = Op2-Rn
           4: ADD{cond}{S} Rd,Rn,Op2 ;* ;add               Rd = Rn+Op2
           5: ADC{cond}{S} Rd,Rn,Op2 ;* ;add with carry    Rd = Rn+Op2+Cy
           6: SBC{cond}{S} Rd,Rn,Op2 ;* ;sub with carry    Rd = Rn-Op2+Cy-1
           7: RSC{cond}{S} Rd,Rn,Op2 ;* ;sub cy. reversed  Rd = Op2-Rn+Cy-1
           8: TST{cond}{P}    Rn,Op2    ;test            Void = Rn AND Op2
           9: TEQ{cond}{P}    Rn,Op2    ;test exclusive  Void = Rn XOR Op2
           A: CMP{cond}{P}    Rn,Op2 ;* ;compare         Void = Rn-Op2
           B: CMN{cond}{P}    Rn,Op2 ;* ;compare neg.    Void = Rn+Op2
           C: ORR{cond}{S} Rd,Rn,Op2    ;OR logical        Rd = Rn OR Op2
           D: MOV{cond}{S} Rd,Op2       ;move              Rd = Op2
           E: BIC{cond}{S} Rd,Rn,Op2    ;bit clear         Rd = Rn AND NOT Op2
           F: MVN{cond}{S} Rd,Op2       ;not               Rd = NOT Op2
  20     S - Set Condition Codes (0=No, 1=Yes) (Must be 1 for opcode 8-B)
  19-16  Rn - 1st Operand Register (R0..R15) (including PC=R15)
              Must be 0000b for MOV/MVN.
  15-12  Rd - Destination Register (R0..R15) (including PC=R15)
              Must be 0000b (or 1111b) for CMP/CMN/TST/TEQ{P}.
  When above Bit 25 I=0 (Register as 2nd Operand)
    When below Bit 4 R=0 - Shift by Immediate
      11-7   Is - Shift amount   (1-31, 0=Special/See below)
    When below Bit 4 R=1 - Shift by Register
      11-8   Rs - Shift register (R0-R14) - only lower 8bit 0-255 used
      7      Reserved, must be zero  (otherwise multiply or LDREX or undefined)
    6-5    Shift Type (0=LSL, 1=LSR, 2=ASR, 3=ROR)
    4      R - Shift by Register Flag (0=Immediate, 1=Register)
    3-0    Rm - 2nd Operand Register (R0..R15) (including PC=R15)
  When above Bit 25 I=1 (Immediate as 2nd Operand)
    11-8   Is - ROR-Shift applied to nn (0-30, in steps of 2)
    7-0    nn - 2nd Operand Unsigned 8bit Immediate
```



## Second Operand (Op2)


This may be a shifted register, or a shifted immediate. See Bit 25 and 11-0.

Unshifted Register: Specify Op2 as "Rm", assembler converts to "Rm,LSL#0".

Shifted Register: Specify as "Rm,SSS#Is" or "Rm,SSS Rs" (SSS=LSL/LSR/ASR/ROR).

Immediate: Specify as 32bit value, for example: "#000NN000h", assembler should
automatically convert into "#0NNh,ROR#0ssh" as far as possible (ie. as far as a
section of not more than 8bits of the immediate is non-zero).



## Zero Shift Amount (Shift Register by Immediate, with Immediate=0)


```
  LSL#0: No shift performed, ie. directly Op2=Rm, the C flag is NOT affected.
  LSR#0: Interpreted as LSR#32, ie. Op2 becomes zero, C becomes Bit 31 of Rm.
  ASR#0: Interpreted as ASR#32, ie. Op2 and C are filled by Bit 31 of Rm.
  ROR#0: Interpreted as RRX#1 (RCR), like ROR#1, but Op2 Bit 31 set to old C.
```

In source code, LSR#32, ASR#32, and RRX#1 should be specified as such -
attempts to specify LSR#0, ASR#0, or ROR#0 will be internally converted to
LSL#0 by the assembler.



## Using R15 (PC)


When using R15 as Destination (Rd), note below CPSR description and Execution
time description.

When using R15 as operand (Rm or Rn), the returned value depends on the
instruction: PC+12 if I=0,R=1 (shift by register), otherwise PC+8 (shift by
immediate).



## Returned CPSR Flags


If S=1, Rd\<>R15, logical operations (AND,EOR,TST,TEQ,ORR,MOV,BIC,MVN):

```
  V=not affected
  C=carryflag of shift operation (not affected if LSL#0 or Rs=00h)
  Z=zeroflag of result
  N=signflag of result (result bit 31)
```

If S=1, Rd\<>R15, arithmetic operations (SUB,RSB,ADD,ADC,SBC,RSC,CMP,CMN):

```
  V=overflowflag of result
  C=carryflag of result
  Z=zeroflag of result
  N=signflag of result (result bit 31)
```

IF S=1, with unused Rd bits=1111b, {P} opcodes (CMPP/CMNP/TSTP/TEQP):

```
  R15=result  ;modify PSR bits in R15, ARMv2 and below only.
  In user mode only N,Z,C,V bits of R15 can be changed.
  In other modes additionally I,F,M1,M0 can be changed.
  The PC bits in R15 are left unchanged in all modes.
```

If S=1, Rd=R15; should not be used in user mode:

```
  CPSR = SPSR_<current mode>
  PC = result
  For example: MOVS PC,R14  ;return from SWI (PC=R14_svc, CPSR=SPSR_svc).
```

If S=0: Flags are not affected (not allowed for CMP,CMN,TEQ,TST).


The instruction "MOV R0,R0" is used as "NOP" opcode in 32bit ARM state.

Execution Time: (1+p)S+rI+pN. Whereas r=1 if I=0 and R=1 (ie. shift by
register); otherwise r=0. And p=1 if Rd=R15; otherwise p=0.




# ARM Opcodes: Multiply and Multiply-Accumulate (MUL, MLA)




## Opcode Format


```
  Bit    Expl.
  31-28  Condition
  27-25  Must be 000b for this instruction
  24-21  Opcode
          0000b: MUL{cond}{S}   Rd,Rm,Rs        ;Rd=Rm*Rs     ;\works as both
          0001b: MLA{cond}{S}   Rd,Rm,Rs,Rn     ;Rd=Rm*Rs+Rn  ;/signed+unsigned
          0010b: UMAAL{cond}    RdLo,RdHi,Rm Rs ;RdHiLo=Rm*Rs+RdHi+RdLo;\un-
          0100b: UMULL{cond}{S} RdLo,RdHi,Rm,Rs ;RdHiLo=Rm*Rs          ; signed
          0101b: UMLAL{cond}{S} RdLo,RdHi,Rm,Rs ;RdHiLo=Rm*Rs+RdHiLo   ;/
          0110b: SMULL{cond}{S} RdLo,RdHi,Rm,Rs ;RdHiLo=Rm*Rs
          0111b: SMLAL{cond}{S} RdLo,RdHi,Rm,Rs ;RdHiLo=Rm*Rs+RdHiLo
          1000b: SMLAxy{cond}   Rd,Rm,Rs,Rn     ;Rd=HalfRm*HalfRs+Rn
          1001b: SMLAWy{cond}   Rd,Rm,Rs,Rn     ;Rd=(Rm*HalfRs)/10000h+Rn
          1001b: SMULWy{cond}   Rd,Rm,Rs        ;Rd=(Rm*HalfRs)/10000h
          1010b: SMLALxy{cond}  RdLo,RdHi,Rm,Rs ;RdHiLo=RdHiLo+HalfRm*HalfRs
          1011b: SMULxy{cond}   Rd,Rm,Rs        ;Rd=HalfRm*HalfRs
  20     S - Set Condition Codes (0=No, 1=Yes) (Must be 0 for Halfword & UMAAL)
  19-16  Rd (or RdHi) - Destination Register (R0-R14)
  15-12  Rn (or RdLo) - Accumulate Register  (R0-R14) (Set to 0000b if unused)
  11-8   Rs - Operand Register               (R0-R14)
  For Non-Halfword Multiplies
    7-4  Must be 1001b for these instructions
  For Halfword Multiplies
    7    Must be 1 for these instructions
    6    y - Rs Top/Bottom flag (0=B=Lower 16bit, 1=T=Upper 16bit)
    5    x - Rm Top/Bottom flag (as above), or 0 for SMLAW, or 1 for SMULW
    4    Must be 0 for these instructions
  3-0    Rm - Operand Register               (R0-R14)
```



## Multiply and Multiply-Accumulate (MUL, MLA)


Restrictions: Rd may not be same as Rm. Rd,Rn,Rs,Rm may not be R15.

Note: Only the lower 32bit of the internal 64bit result are stored in Rd, thus
no sign/zero extension is required and MUL and MLA can be used for both signed
and unsigned calculations!

Execution Time: 1S+mI for MUL, and 1S+(m+1)I for MLA. Whereas 'm' depends on
whether/how many most significant bits of Rs are all zero or all one. That is
m=1 for Bit 31-8, m=2 for Bit 31-16, m=3 for Bit 31-24, and m=4 otherwise.

Flags (if S=1): Z=zeroflag, N=signflag, C=destroyed (ARMv4 and below) or C=not
affected (ARMv5 and up), V=not affected. MUL/MLA supported by ARMv2 and up.



## Multiply Long and Multiply-Accumulate Long (MULL, MLAL)


Optionally supported, INCLUDED in ARMv3M, EXCLUDED in ARMv4xM/ARMv5xM.

Restrictions: RdHi,RdLo,Rm must be different registers. R15 may not be used.

Execution Time: 1S+(m+1)I for MULL, and 1S+(m+2)I for MLAL. Whereas 'm' depends
on whether/how many most significant bits of Rs are "all zero" (UMULL/UMLAL) or
"all zero or all one" (SMULL,SMLAL). That is m=1 for Bit31-8, m=2 for Bit31-16,
m=3 for Bit31-24, and m=4 otherwise.

Flags (if S=1): Z=zeroflag, N=signflag, C=destroyed (ARMv4 and below) or C=not
affected (ARMv5 and up), V=destroyed??? (ARMv4 and below???) or V=not affected
(ARMv5 and up).



## Signed Halfword Multiply (SMLAxy,SMLAWy,SMLALxy,SMULxy,SMULWy)


Supported by E variants of ARMv5 and up, ie. ARMv5TE(xP).

Q-flag gets set on 32bit SMLAxy/SMLAWy addition overflows, however, the result
is NOT truncated (as it'd be done with QADD opcodes).

Q-flag is NOT affected on (rare) 64bit SMLALxy addition overflows.

SMULxy/SMULWy cannot overflow, and thus leave Q-flag unchanged as well.

NZCV-flags are not affected by Halfword multiplies.

Execution Time: 1S+Interlock (SMULxy,SMLAxy,SMULWx,SMLAWx)

Execution Time: 1S+1I+Interlock (SMLALxy)



## Unsigned Multiply Accumulate Accumulate Long (UMAAL)


Multiply with two 32bit additions, supposed to be used for cryptography.

Flags are not affected.

ARMv6 and above.




# ARM Opcodes: Special ARM9 Instructions (CLZ, QADD/QSUB)




## Count Leading Zeros (CLZ)


```
  Bit    Expl.
  31-28  Condition
  27-16  Must be 0001.0110.1111b for this instruction
         Opcode (fixed)
           CLZ{cond} Rd,Rm  ;Rd=Number of leading zeros in Rm
  15-12  Rd - Destination Register              (R0-R14)
  11-4   Must be 1111.0001b for this instruction
  3-0    Rm - Source Register                   (R0-R14)
```

CLZ supported by ARMv5 and up. Execution time: 1S.

Return: No Flags affected. Rd=0..32.



## Opcode Format (QADD/QSUB)


```
  Bit    Expl.
  31-28  Condition
  27-24  Must be 0001b for this instruction
  23-20  Opcode
          0000b: QADD{cond}  Rd,Rm,Rn    ;Rd=Rm+Rn
          0010b: QSUB{cond}  Rd,Rm,Rn    ;Rd=Rm-Rn
          0100b: QDADD{cond} Rd,Rm,Rn    ;Rd=Rm+Rn*2 (doubled)
          0110b: QDSUB{cond} Rd,Rm,Rn    ;Rd=Rm-Rn*2 (doubled)
  19-16  Rn - Second Source Register            (R0-R14)
  15-12  Rd - Destination Register              (R0-R14)
  11-4   Must be 00000101b for this instruction
  3-0    Rm - First Source Register             (R0-R14)
```

Supported by E variants of ARMv5 and up, ie. ARMv5TE(xP).

Execution time: 1S+Interlock.

Results truncated to signed 32bit range in case of overflows, with the Q-flag
being set (and being left unchanged otherwise). NZCV flags are not affected.

Note: Rn\*2 is internally processed first, and may get truncated - even if the
final result would fit into range.




# ARM Opcodes: Special ARM11 Instructions (Misc)




## Load/Store Byte/Halfword/Doubleword Exclusive (LDREX/STREX)


```
  Bit    Expl.
  31-28  Condition
  27-23  Must be 00011b for this instruction
  22-20  Opcode
           0: STREX{cond}  Rd, Rm, [Rn]  ;[Rn]=Rm, Rd=flag       ;32bit
           1: LDREX{cond}  Rd, [Rn]      ;Rd=[Rm]                ;32bit
           2: STREXD{cond} Rd, Rm, [Rn]  ;[Rn]=Rm,Rm+1, Rd=flag  ;64bit
           3: LDREXD{cond} Rd, [Rn]      ;Rd,Rd+1=[Rm]           ;64bit
           4: STREXB{cond} Rd, Rm, [Rn]  ;[Rn]=Rm, Rd=flag       ;8bit
           5: LDREXB{cond} Rd, [Rn]      ;Rd=[Rm]                ;8bit
           6: STREXH{cond} Rd, Rm, [Rn]  ;[Rn]=Rm, Rd=flag       ;16bit
           7: LDREXH{cond} Rd, [Rn]      ;Rd=[Rm]                ;16bit
  19-16  Rn - Base Register                      (R0-R14)
  15-12  Rd - Destination Register               (R0-R14)
  11-4   Must be 1111.1001b for this instruction
  3-0    Rm - Source Register (1111b for LDREX)  (R0-R14)
```

For exclusive access to shared memory regions (ie. in dual-core CPUs?)

Unknown what "exclusive" means?

Return: No Flags affected.

ARMv6 and up supports LDREX/STREX (with 32bit operand).

ARMv6K and up supports LDREX/STREX{B|H|D} (with 8/16/64bit operand).



## Clear Exclusive (CLREX)


```
  Bit    Expl.
  31-0   Opcode 1111.0101.0111.1111.1111.0000.0001.1111b for CLREX
```

Supported on ARMv6K and up.



## Hint (TrueNOP, YIELD, WFE, WFI, SEV)


```
  Bit    Expl.
  31-28  Condition (should be always 0Eh=Always for NOP)
  27-8   Must be 0011.0010.0000.1111.0000b
  7-0    Opcode/Hint
           00h: TrueNOP      ;no operation
           01h: YIELD{cond}
           02h: WFE{cond}    ;wait for event
           03h: WFI{cond}    ;wait for interrupt
           04h: SEV{cond}    ;send event
```

Supported on ARMv6K and up.



## Change Processor State aka CPSR Mode/Flags (CPS, CPSID, CPSIE)


```
  31-20  Must be 1111.0001.0000b
  19-17  Opcode
          001b: CPS   #<mode>           ;change mode
          100b: CPSIE {A}{I}{F}         ;interrupt bit(s) enable
          101b: CPSIE {A}{I}{F},#<mode> ;interrupt bit(s) enable & change mode
          110b: CPSID {A}{I}{F}         ;interrupt bit(s) disable
          111b: CPSID {A}{I}{F},#<mode> ;interrupt bit(s) disable & change mode
  16-9   Must be 0000.0000b
  8      Change A flag (what?) (0=No, 1=Yes)  ;\must be all zero for CPS,
  7      Change I flag         (0=No, 1=Yes)  ; must be at least one flag set
  6      Change F flag         (0=No, 1=Yes)  ;/for CPSID/CPSIE
  5      Must be 0
  4-0    Mode (00h..1Fh) (must be 00h if bit17=0)
```



## Set Endianness for Data Access (SETEND)


```
  31-10  Fixed, 1111000100000001000000b
  9      Opcode/operand
          0: SETEND LE  ;clears the CPSR E bit
          1: SETEND BE  ;sets the CPSR E bit
  8-0    Fixed, 000000000b
```

Changes the byte order for data access to Big/Little endian. Does probably not
affect opcode fetches, but probably affect all other memory including push/pop?
Or affects "LDR" only?

Supported on ARMv6 and above.



## Store Return State (SRS) (stores the R14 and SPSR of the current mode)


to the word at the specified address and the following word respectively. The
address is determined from the banked version of R13 belonging to a specified
mode.

```
  Syntax
  SRS<addressing_mode> #<mode>{!}   ;<-- original (pre-UAL)
  SRS<addressing_mode> sp!,#<mode>  ;<-- more common (UAL)
```

\<addressing\_mode>: Is similar to the \<addressing\_mode> in LDM and
STM instructions, see Addressing Mode 4 - Load and Store Multiple on page
A5-41, but with the following differences:

- The base register, Rn, is the banked version of R13 for the mode specified by
\<mode>, rather than the current mode.

- The number of registers to store is 2.

- The register list is {R14, SPSR}, with both R14 and the SPSR being the
versions belonging to the current mode.

\<mode> Specifies the number of the mode whose banked register is used as
the base register for \<addressing\_mode>. The mode number is the 5-bit
encoding of the chosen mode in a PSR, as described in The mode bits on page
A2-14.

! If present, sets the W bit. This causes the instruction to write a modified
value back to its base register, in a manner similar to that specified for
Addressing Mode 4 - Load and Store Multiple on page A5-41. If ! is omitted, the
W bit is 0 and the instruction does not change the base register.

```
  31-25  Fixed, 1111100b
  24     P
  23     U
  22     Fixed, 1
  21     W
  20     Fixed, 0 (store)
  19-5   Fixed, 110100000101000b
  4-0    mode
```

Supported on ARMv6 and above.



## Return From Exception (RFE) (RFEDA, RFEDB, RFEIA, RFEIB)


loads the PC and the CPSR from the word at the specified address and the

following word respectively.

```
  Syntax
  RFE<addressing_mode> Rn{!}
```

\<addressing\_mode>: Is similar to the \<addressing\_mode> in LDM and
STM instructions, see Addressing Mode 4 - Load and Store Multiple on page
A5-41, but with the following differences:

- The number of registers to load is 2.

- The register list is {PC, CPSR}.

\<Rn> Specifies the base register to be used by \<addressing\_mode>.
If R15 is specified as the base register, the result is UNPREDICTABLE.

! If present, sets the W bit. This causes the instruction to write a modified
value back to its base register, in a manner similar to that specified for
Addressing Mode 4 - Load and Store Multiple on page A5-41. If ! is omitted, the
W bit is 0 and the instruction does not change the base register.

While RFE supports different base registers, a general usage case is where Rn
== sp (the stack pointer), held in R13. The instruction can then be used as the
return method associated with instructions SRS and CPS. See New instructions to
improve exception handling on page A2-28 for more details.

```
  31-25  Fixed, 1111100b
  24     P
  23     U
  22     Fixed, 0
  21     W
  20     Fixed, 1 (load)
  19-16  Rn
  15-0   Fixed, 0000101000000000b
```

Supported on ARMv6 and above.



## SVC (formerly SWI)


SWI was renamed to SVC in new UAL syntax.



## CPY


CPY Rd,Rm is an alias for MOV Rd,Rm (without flags affected).

```
  31-28  Condition
  27-16  Fixed, 000110100000
  15-12  Rd - Destination Register
  11-4   Fixed, 00000000
  3-0    Rm
```

The alias was invented in ARMv6 for THUMB and ARM code (apparently because
pre-UAL THUMB syntax couldn't distinguish between MOV and MOVS) (ie. in ARM
it's useless, but in THUMB it does allow using a formerly undocumented opcode).

ARMv6 and above.




# ARM Opcodes: Special ARM11 Instructions (SIMD)




## Sign Extend / Zero Extend, with optional Addition (SXT, UXT)


```
  31-28  Condition
  27-23  Fixed, 01101b
  22-20  Opcode:
          0: SXTAB16{cond} Rd, Rn, Rm{,ROR #imm} ;\
          2: SXTAB{cond}   Rd, Rn, Rm{,ROR #imm} ;
          3: SXTAH{cond}   Rd, Rn, Rm{,ROR #imm} ; with add
          4: UXTAB16{cond} Rd, Rn, Rm{,ROR #imm} ;
          6: UXTAB{cond}   Rd, Rn, Rm{,ROR #imm} ;
          7: UXTAH{cond}   Rd, Rn, Rm{,ROR #imm} ;/
          0: SXTB16{cond}  Rd,     Rm{,ROR #imm} ;\
          2: SXTB{cond}    Rd,     Rm{,ROR #imm} ;
          3: SXTH{cond}    Rd,     Rm{,ROR #imm} ; without add
          4: UXTB16{cond}  Rd,     Rm{,ROR #imm} ;
          6: UXTB{cond}    Rd,     Rm{,ROR #imm} ;
          7: UXTH{cond}    Rd,     Rm{,ROR #imm} ;/
  19-16  Rn - Addition Register (or 1111b when no addition)            (R0-R14)
  15-12  Rd - Destination Register                                     (R0-R14)
  11-10  Rotation (0=None/ROR#0, 1=ROR#8, 2=ROR#16, 3=ROR#24)
  9-4    Fixed, 000111b
  3-0    Rm - Source register (to be rotated/extracted from)           (R0-R14)
```

Supported on ARMv6 and above.



## Select Bytes from 1st/2nd operand, depending on GE flags (SEL)


Syntax

```
  SEL{cond} Rd, Rn, Rm
```

Operation

if ConditionPassed(cond) then

Rd[7:0] = if GE[0] == 1 then Rn[7:0] else Rm[7:0]

Rd[15:8] = if GE[1] == 1 then Rn[15:8] else Rm[15:8]

Rd[23:16] = if GE[2] == 1 then Rn[23:16] else Rm[23:16]

Rd[31:24] = if GE[3] == 1 then Rn[31:24] else Rm[31:24]

Usage

Use SEL after instructions such as SADD8, SADD16, SSUB8, SSUB16, UADD8, UADD16,
USUB8, USUB16, SADDSUBX, SSUBADDX, UADDSUBX and USUBADDX, that set the GE
flags. For example, the following sequence of instructions sets each byte of Rd
equal to the unsigned minimum of the corresponding bytes of Ra and Rb:

```
  USUB8 Rd, Ra, Rb
  SEL Rd, Rb, Ra
```

Notes

Specifying R15 for register Rd, Rm, or Rn has UNPREDICTABLE results.

```
  31-28  Condition
  27-20  Fixed, 01101000b
  19-16  Rn - First Source Register (8bit snippets used when GE bits = 1)
  15-12  Rd - Destination Register
  11-4   Fixed, 11111011b
  3-0    Rm - Second Source Register (8bit snippets used when GE bits = 0)
```

ARMv6 and above.



## SADD16


SADD16 (Signed Add) performs two 16-bit signed integer additions. It sets the
GE bits in the CPSR according to the results of the additions.

ARMv6 and above.

Operation

sum = Rn[15:0] + Rm[15:0] /\* Signed addition \*/

Rd[15:0] = sum[15:0]

GE[1:0] = if sum >= 0 then 0b11 else 0

sum = Rn[31:16] + Rm[31:16] /\* Signed addition \*/

Rd[31:16] = sum[15:0]

GE[3:2] = if sum >= 0 then 0b11 else 0

```
  31-28  Condition
  27-23  Fixed, 01100b
  22-20  Opcode, part 1:
          001b: for Sxx           (signed, with GE flags)
          010b: for Qxx           (signed, with saturation)
          011b: for SHxx          (signed, with halving)
          101b: for Uxx           (unsigned, with GE flags)
          110b: for UQxx          (unsigned, with saturation)
          111b: for UHxx          (unsigned, with halving)
  19-16  Rn - First Source Register                                    (R0-R14)
  15-12  Rd - Destination Register                                     (R0-R14)
  11-8   Fixed, 1111b
  7-5    Opcode, part 2:
          000b: xxADD16{cond}   Rd, Rn, Rm
          001b: xxADDSUBX{cond} Rd, Rn, Rm
          010b: xxSUBADDX{cond} Rd, Rn, Rm
          011b: xxSUB16{cond}   Rd, Rn, Rm
          100b: xxADD8{cond}    Rd, Rn, Rm
          111b: xxSUB8{cond}    Rd, Rn, Rm
  4      Fixed, 1
  3-0    Rm - Second Source register                                   (R0-R14)
```



## SMLAD


SMLAD (Signed Multiply Accumulate Dual) performs two signed 16 x 16-bit
multiplications. It adds the products to a 32-bit accumulate operand.

Optionally, you can exchange the halfwords of the second operand before
performing the arithmetic. This produces top x bottom and bottom x top
multiplication.

This instruction sets the Q flag if the accumulate operation overflows.
Overflow cannot occur during the multiplications.

X Sets the X bit of the instruction to 1, and the multiplications are bottom x
top and top x bottom.

If the X is omitted, sets the X bit to 0, and the multiplications are bottom x
bottom and top x top.

\<Rm> Specifies the register that contains the first operand.

\<Rs> Specifies the register that contains the second operand.

\<Rn> Specifies the register that contains the accumulate operand.

```
  31-28  Condition
  27-23  Fixed, 01110
  22-20  Opcode part 1 (part2 in bit7-6)
         Merged part1.part2:
           000.00: SMUAD{X}{cond}  Rd,Rm,Rs
           000.00: SMLAD{X}{cond}  Rd,Rm,Rs,Rn
           000.01: SMUSD{X}{cond}  Rd,Rm,Rs
           000.01: SMLSD{X}{cond}  Rd,Rm,Rs,Rn
           100.00: SMLALD{X}{cond} RdLo,RdHi,Rm,Rs
           100.01: SMLSLD{X}{cond} RdLo,RdHi,Rm,Rs
           101.00: SMMUL{R}{cond}  Rd,Rm,Rs        ;Rd=(Rm*Rs)/100000000h
           101.00: SMMLA{R}{cond}  Rd,Rm,Rs,Rn     ;Rd=(Rm*Rs)/100000000h+Rz
           101.11: SMMLS{R}{cond}  Rd,Rm,Rs,Rn     ;Rd=(Rm*Rs)/100000000h-Rz
  19-16  Rd or RdHi - Destination Register
  15-12  Rn or RdLo or unused (must be 0Fh for SMUAD/SMUSD/SMMUL)
  11-8   Rs
  7-6    Opcode part 2 (part1 in bit22-20, see there)
  5      X or R flag   (X=Exchange, R=Rounded)
  4      Fixed, 1
  3-0    Rm
```

ARMv6 and above.


## Most significant word multiply


There are three signed 32-bit x 32-bit Multiply instructions that produce top
32-bit results:

```
  SMMUL Multiplies the 32-bit values of two registers together, and stores
        the top 32 bits of the signed 64-bit result in a third register.
  SMMLA Multiplies the 32-bit values of two registers together, extracts the
        top 32 bits, adds the 32-bit value from a third register, and stores
        the signed 32-bit result in a fourth register.
  SMMLS Multiplies the 32-bit value of two registers together, extracts the
        top 32 bits, subtracts this from a 32-bit value from a third
        register, and stores the signed 32-bit result in a fourth register.
```

The above three instructions do not affect any flags.


## Dual halfword multiply


There are six dual, signed 16-bit x 16-bit Multiply instructions:

```
  SMUAD Multiplies the values of the top halfwords of two registers together,
        multiplies the values of the bottom halfwords of the same two
        registers together, adds the products, and stores the 32-bit result
        in a third register.
  SMUSD Multiplies the values of the top halfwords of two registers together,
        multiplies the values of the bottom halfwords of the same two
        registers together, subtracts one product from the other, and stores
        the 32-bit result in a third register.
  ---(descriptions below seem to be bugged, seem to describe 32bit SMMxx)---
  SMLAD Multiplies the 32-bit value of two registers together, extracts the
        top 32 bits, subtracts this from a 32-bit value from a third
        register, and stores the signed 32-bit result in a fourth register.
  SMLSD Multiplies the 32-bit values of two registers together, extracts the
        top 32 bits, adds the 32-bit value from a third register, and stores
        the signed 32-bit result in a fourth register.
  SMLALD Multiplies the 32-bit value of two registers together, extracts the
         top 32 bits, subtracts this from a 32-bit value from a third
         register, and stores the signed 32-bit result in a fourth register.
  SMLSLD Multiplies the 32-bit value of two registers together, extracts the
         top 32 bits, subtracts this from a 32-bit value from a third
         register, and stores the signed 32-bit result in a fourth register.
```

SMUAD, SMLAD, and SMLSLD can set the Q flag if overflow occurs in the
operation. All other instructions do not affect any flags.



## Signed/Unsigned Saturate (SSAT, USAT)


Saturates a 32bit value (with optional shift) to the specified range (of 1..32
bits).

```
  31-28  Condition
  27-21  Fixed, 0110101b: SSAT{cond} Rd, #<range>, Rm {,LSL/ASR #imm}
                0110111b: USAT{cond} Rd, #<range>, Rm {,LSL/ASR #imm}
  20-16  Immediate: range-1 (0..31 = Saturate to 1..32 bits range)
  15-12  Rd - Destination Register
  11-7   shift_imm (1..31 for LSL/ASR#1..31, or 0 for LSL#0, or 0 for ASR#32)
  6      Shift type (0=LSL, 1=ASR) (note: really ASR, even "unsigned" USAT)
  5-4    Fixed, 01b
  3-0    Rm - Source Register
```

The Q flag is set if the operation saturates.

ARMv6 and above.



## Signed/Unsigned Saturate on Halfwords (SSAT16, USAT16)


Saturates two 16bit values to the specified range (of 1..16 bits).

```
  31-28  Condition
  27-21  Fixed, 0110101b: SSAT16{cond} Rd, #<range>, Rm
                0110111b: USAT16{cond} Rd, #<range>, Rm
  20     Fixed, 0
  19-16  Immediate: range-1 (0..15 = Saturate to 1..16 bits range)
  15-12  Rd - Destination Register
  11-4   Fixed, 11110011b
  3-0    Rm - Source Register
```

The Q flag is set if either halfword operation saturates.

ARMv6 and above.



## Unsigned Sum of Absolute Differences, optional Accumulate (USAD8, USADA8)


Performs four unsigned 8bit subtractions, and adds the absolute values of the
differences together.

```
  31-28  Condition
  27-20  Fixed, 01111000b
  19-16  Rd - Destination Register
  15-12  Rn (if any) (otherwise fixed, 1111)
           USAD8{cond}  Rd, Rm, Rs        ;without Rn   ;Rd=sum
           USADA8{cond} Rd, Rm, Rs, Rn    ;with Rn      ;Rd=sum + Rn
  11-8   Rs
  7-4    Fixed, 0001b
  3-0    Rm
```

ARMv6 and above.



## Pack Halfword, Bottom-Top or Top-Bottom (PKHBT, PKHTB)


PKHBT (Pack Halfword Bottom Top) combines the bottom (least significant)
halfword of its first operand with the top (most significant) halfword of its
shifted second operand. The shift is a left shift, by any amount from 0 to 31.

\<Rn> Specifies the register that contains the first operand. Bits[15:0]
of this operand become bits[15:0] of the result of the operation.

\<Rm> Specifies the register that contains the second operand. This is
shifted left by the specified amount, then bits[31:16] of this operand become
bits[31:16] of the result of the operation.

\<shift\_imm> Specifies the amount by which Rm is to be shifted left. This
is a value from 0 to 31.

If the shift specifier is omitted, a left shift by 0 is used.

Operation

if ConditionPassed(cond) then

Rd[15:0] = Rn[15:0]

Rd[31:16] = (Rm Logical\_Shift\_Left shift\_imm)[31:16]

```
  31-28  Condition
  27-20  Fixed, 01101000b
  19-16  Rn
  15-12  Rd - Destination Register
  11-7   shift_imm (0..31)
  6-4    Fixed, 001  PKHBT {cond} Rd, Rn, Rm {, LSL #<shift_imm>}
                101  PKHTB {cond} Rd, Rn, Rm {, ASR #<shift_imm>}
  3-0    Rm
```

ARMv6 and above.



## Reverse Byte Order for Big/Little-Endian Conversion (REV, REV16, REVSH)


Specifying R15 for register Rd or Rm has UNPREDICTABLE results.

```
  31-28  Condition
  27-23  Fixed, 01101b
  22     Opcode (with bit7)
          Bit22=0, Bit7=0: REV{cond}   Rd, Rm   ;reverse 32bit
          Bit22=0, Bit7=1: REV16{cond} Rd, Rm
          Bit22=1, Bit7=1: REVSH{cond} Rd, Rm
  21-16  Fixed, 111111b
  15-12  Rd - Destination Register
  11-8   Fixed, 1111b
  7      Opcode (with bit22, see there)
  6-4    Fixed, 011b
  3-0    Rm - Source Register
```

ARMv6 and above.




# ARM Opcodes: PSR Transfer (MRS, MSR)




## Opcode Format


These instructions occupy an unused area (TEQ,TST,CMP,CMN with S=0) of ALU
opcodes.

```
  Bit    Expl.
  31-28  Condition
  27-26  Must be 00b for this instruction
  25     I - Immediate Operand Flag  (0=Register, 1=Immediate) (Zero for MRS)
  24-23  Must be 10b for this instruction
  22     Psr - Source/Destination PSR  (0=CPSR, 1=SPSR_<current mode>)
  21     Opcode
           0: MRS{cond} Rd,Psr          ;Rd = Psr
           1: MSR{cond} Psr{_field},Op  ;Psr[field] = Op
  20     Must be 0b for this instruction (otherwise TST,TEQ,CMP,CMN)
  For MRS:
    19-16   Must be 1111b for this instruction (otherwise SWP)
    15-12   Rd - Destination Register  (R0-R14)
    11-0    Not used, must be zero.
  For MSR:
    19      f  write to flags field     Bit 31-24 (aka _flg)
    18      s  write to status field    Bit 23-16 (reserved, don't change)
    17      x  write to extension field Bit 15-8  (reserved, don't change)
    16      c  write to control field   Bit 7-0   (aka _ctl)
    15-12   Not used, must be 1111b.
  For MSR Psr,Rm (I=0)
    11-4    Not used, must be zero. (otherwise BX)
    3-0     Rm - Source Register <op>  (R0-R14)
  For MSR Psr,Imm (I=1)
    11-8    Shift applied to Imm   (ROR in steps of two 0-30)
    7-0     Imm - Unsigned 8bit Immediate
    In source code, a 32bit immediate should be specified as operand.
    The assembler should then convert that into a shifted 8bit value.
```

MSR/MRS and CPSR/SPSR supported by ARMv3 and up.

ARMv2 and below contained PSR flags in R15, accessed by CMP/CMN/TST/TEQ{P}.

The field mask bits specify which bits of the destination Psr are write-able
(or write-protected), one or more of these bits should be set, for example,
CPSR\_fsxc (aka CPSR aka CPSR\_all) unlocks all bits (see below user mode
restriction though).

Restrictions:

In non-privileged mode (user mode): only condition code bits of CPSR can be
changed, control bits can't.

Only the SPSR of the current mode can be accessed; In User and System modes no
SPSR exists.

The T-bit may not be changed; for THUMB/ARM switching use BX instruction.

Unused Bits in CPSR are reserved for future use and should never be changed
(except for unused bits in the flags field).

Execution Time: 1S.


Note: The A22i assembler recognizes MOV as alias for both MSR and MRS because
it is practically not possible to remember whether MSR or MRS was the load or
store opcode, and/or whether it does load to or from the Psr register.




# ARM Opcodes: Memory: Single Data Transfer (LDR, STR, PLD)




## Opcode Format


```
  Bit    Expl.
  31-28  Condition (Must be 1111b for PLD)
  27-26  Must be 01b for this instruction
  25     I - Immediate Offset Flag (0=Immediate, 1=Shifted Register)
  24     P - Pre/Post (0=post; add offset after transfer, 1=pre; before trans.)
  23     U - Up/Down Bit (0=down; subtract offset from base, 1=up; add to base)
  22     B - Byte/Word bit (0=transfer 32bit/word, 1=transfer 8bit/byte)
  When above Bit 24 P=0 (Post-indexing, write-back is ALWAYS enabled):
    21     T - Memory Management (0=Normal, 1=Force non-privileged access)
  When above Bit 24 P=1 (Pre-indexing, write-back is optional):
    21     W - Write-back bit (0=no write-back, 1=write address into base)
  20     L - Load/Store bit (0=Store to memory, 1=Load from memory)
          0: STR{cond}{B}{T} Rd,<Address>   ;[Rn+/-<offset>]=Rd
          1: LDR{cond}{B}{T} Rd,<Address>   ;Rd=[Rn+/-<offset>]
         (1: PLD <Address> ;Prepare Cache for Load, see notes below)
          Whereas, B=Byte, T=Force User Mode (only for POST-Indexing)
  19-16  Rn - Base register               (R0..R15) (including R15=PC+8)
  15-12  Rd - Source/Destination Register (R0..R15) (including R15=PC+12)
  When above I=0 (Immediate as Offset)
    11-0   Unsigned 12bit Immediate Offset (0-4095, steps of 1)
  When above I=1 (Register shifted by Immediate as Offset)
    11-7   Is - Shift amount      (1-31, 0=Special/See below)
    6-5    Shift Type             (0=LSL, 1=LSR, 2=ASR, 3=ROR)
    4      Must be 0 (Reserved, see The Undefined Instruction)
    3-0    Rm - Offset Register   (R0..R14) (not including PC=R15)
```



## Instruction Formats for \<Address>


An expression which generates an address:

```
  <expression>                  ;an immediate used as address
  ;*** restriction: must be located in range PC+/-4095+8, if so,
  ;*** assembler will calculate offset and use PC (R15) as base.
```

Pre-indexed addressing specification:

```
  [Rn]                          ;offset = zero
  [Rn, <#{+/-}expression>]{!}   ;offset = immediate
  [Rn, {+/-}Rm{,<shift>} ]{!}   ;offset = register shifted by immediate
```

Post-indexed addressing specification:

```
  [Rn], <#{+/-}expression>      ;offset = immediate
  [Rn], {+/-}Rm{,<shift>}       ;offset = register shifted by immediate
```

Whereas...

```
  <shift>  immediate shift such like LSL#4, ROR#2, etc. (see ALU opcodes).
  {!}      exclamation mark ("!") indicates write-back (Rn will be updated).
```



## Notes


Shift amount 0 has special meaning, as described for ALU opcodes.

When writing a word (32bit) to memory, the address should be word-aligned.

When reading a byte from memory, upper 24 bits of Rd are zero-extended.

LDR PC,\<op> on ARMv4 leaves CPSR.T unchanged.

LDR PC,\<op> on ARMv5 sets CPSR.T to \<op> Bit0, (1=Switch to Thumb).


When reading a word from a halfword-aligned address (which is located in the
middle between two word-aligned addresses), the lower 16bit of Rd will contain
[address] ie. the addressed halfword, and the upper 16bit of Rd will contain
[Rd-2] ie. more or less unwanted garbage. However, by isolating lower bits this
may be used to read a halfword from memory. (Above applies to little endian
mode, as used in GBA.)


In a virtual memory based environment (ie. not in the GBA), aborts (ie. page
faults) may take place during execution, if so, Rm and Rn should not specify
the same register when post-indexing is used, as the abort-handler might have
problems to reconstruct the original value of the register.


Return: CPSR flags are not affected.

Execution Time: For normal LDR: 1S+1N+1I. For LDR PC: 2S+2N+1I. For STR: 2N.



## PLD \<Address> ;Prepare Cache for Load


PLD must use following settings cond=1111b, P=1, B=1, W=0, L=1, Rd=1111b, the
address may not use post-indexing, and may not use writeback, the opcode is
encoded identical as LDRNVB R15,\<Address>.

PLD signalizes to the memory system that a specific memory address will be soon
accessed, the memory system may use this hint to prepare caching/pipelining,
aside from that, PLD does not have any affect to the program logic, and behaves
identical as NOP.

PLD supported by ARMv5TE and up only, not ARMv5, not ARMv5TExP.




# ARM Opcodes: Memory: Halfword, Doubleword, and Signed Data Transfer




## Opcode Format


```
  Bit    Expl.
  31-28  Condition
  27-25  Must be 000b for this instruction
  24     P - Pre/Post (0=post; add offset after transfer, 1=pre; before trans.)
  23     U - Up/Down Bit (0=down; subtract offset from base, 1=up; add to base)
  22     I - Immediate Offset Flag (0=Register Offset, 1=Immediate Offset)
  When above Bit 24 P=0 (Post-indexing, write-back is ALWAYS enabled):
    21     Not used, must be zero (0)
  When above Bit 24 P=1 (Pre-indexing, write-back is optional):
    21     W - Write-back bit (0=no write-back, 1=write address into base)
  20     L - Load/Store bit (0=Store to memory, 1=Load from memory)
  19-16  Rn - Base register                (R0-R15) (Including R15=PC+8)
  15-12  Rd - Source/Destination Register  (R0-R15) (Including R15=PC+12)
  11-8   When above Bit 22 I=0 (Register as Offset):
           Not used. Must be 0000b
         When above Bit 22 I=1 (immediate as Offset):
           Immediate Offset (upper 4bits)
  7      Reserved, must be set (1)
  6-5    Opcode (0-3)
         When Bit 20 L=0 (Store) (and Doubleword Load/Store):
          0: Reserved for SWP instruction
          1: STR{cond}H  Rd,<Address>  ;Store halfword   [a]=Rd
          2: LDR{cond}D  Rd,<Address>  ;Load Doubleword  R(d)=[a], R(d+1)=[a+4]
          3: STR{cond}D  Rd,<Address>  ;Store Doubleword [a]=R(d), [a+4]=R(d+1)
         When Bit 20 L=1 (Load):
          0: Reserved.
          1: LDR{cond}H  Rd,<Address>  ;Load Unsigned halfword (zero-extended)
          2: LDR{cond}SB Rd,<Address>  ;Load Signed byte (sign extended)
          3: LDR{cond}SH Rd,<Address>  ;Load Signed halfword (sign extended)
  4      Reserved, must be set (1)
  3-0    When above Bit 22 I=0:
           Rm - Offset Register            (R0-R14) (not including R15)
         When above Bit 22 I=1:
           Immediate Offset (lower 4bits)  (0-255, together with upper bits)
```

STRH,LDRH,LDRSB,LDRSH supported on ARMv4 and up.

STRD/LDRD supported on ARMv5TE and up only, not ARMv5, not ARMv5TExP.

STRD/LDRD: base writeback: Rn should not be same as R(d) or R(d+1).

STRD: index register: Rm should not be same as R(d) or R(d+1).

STRD/LDRD: Rd must be an even numbered register (R0,R2,R4,R6,R8,R10,R12).

STRD/LDRD: Address must be double-word aligned (multiple of eight).



## Instruction Formats for \<Address>


An expression which generates an address:

```
  <expression>                  ;an immediate used as address
  ;*** restriction: must be located in range PC+/-255+8, if so,
  ;*** assembler will calculate offset and use PC (R15) as base.
```

Pre-indexed addressing specification:

```
  [Rn]                          ;offset = zero
  [Rn, <#{+/-}expression>]{!}   ;offset = immediate
  [Rn, {+/-}Rm]{!}              ;offset = register
```

Post-indexed addressing specification:

```
  [Rn], <#{+/-}expression>      ;offset = immediate
  [Rn], {+/-}Rm                 ;offset = register
```

Whereas...

```
  {!}      exclamation mark ("!") indicates write-back (Rn will be updated).
```


Return: No Flags affected.

Execution Time: For Normal LDR, 1S+1N+1I. For LDR PC, 2S+2N+1I. For STRH 2N.




# ARM Opcodes: Memory: Block Data Transfer (LDM, STM)




## Opcode Format


```
  Bit    Expl.
  31-28  Condition
  27-25  Must be 100b for this instruction
  24     P - Pre/Post (0=post; add offset after transfer, 1=pre; before trans.)
  23     U - Up/Down Bit (0=down; subtract offset from base, 1=up; add to base)
  22     S - PSR & force user bit (0=No, 1=load PSR or force user mode)
  21     W - Write-back bit (0=no write-back, 1=write address into base)
  20     L - Load/Store bit (0=Store to memory, 1=Load from memory)
          0: STM{cond}{amod} Rn{!},<Rlist>{^}  ;Store (Push)
          1: LDM{cond}{amod} Rn{!},<Rlist>{^}  ;Load  (Pop)
          Whereas, {!}=Write-Back (W), and {^}=PSR/User Mode (S)
  19-16  Rn - Base register                (R0-R14) (not including R15)
  15-0   Rlist - Register List
  (Above 'offset' is meant to be the number of words specified in Rlist.)
```

Return: No Flags affected.

Execution Time: For normal LDM, nS+1N+1I. For LDM PC, (n+1)S+2N+1I. For STM
(n-1)S+2N. Where n is the number of words transferred.



## Addressing Modes {amod}


The IB,IA,DB,DA suffixes directly specify the desired U and P bits:

```
  IB  increment before          ;P=1, U=1
  IA  increment after           ;P=0, U=1
  DB  decrement before          ;P=1, U=0
  DA  decrement after           ;P=0, U=0
```

Alternately, FD,ED,FA,EA could be used, mostly to simplify mnemonics for stack
transfers.

```
  ED  empty stack, descending   ;LDM: P=1, U=1  ;STM: P=0, U=0
  FD  full stack,  descending   ;     P=0, U=1  ;     P=1, U=0
  EA  empty stack, ascending    ;     P=1, U=0  ;     P=0, U=1
  FA  full stack,  ascending    ;     P=0, U=0  ;     P=1, U=1
```

Ie. the following expressions are aliases for each other:

```
  STMFD=STMDB=PUSH   STMED=STMDA   STMFA=STMIB   STMEA=STMIA
  LDMFD=LDMIA=POP    LDMED=LDMIB   LDMFA=LDMDA   LDMEA=LDMDB
```

Note: The equivalent THUMB functions use fixed organization:

```
  PUSH/POP: full descending     ;base register SP (R13)
  LDM/STM:  increment after     ;base register R0..R7
```

Descending is common stack organization as used in 80x86 and Z80 CPUs, SP is
decremented when pushing/storing data, and incremented when popping/loading
data.



## When S Bit is set (S=1)


If instruction is LDM and R15 is in the list: (Mode Changes)

```
  While R15 loaded, additionally: CPSR=SPSR_<current mode>
```

Otherwise: (User bank transfer)

```
  Rlist is referring to User Bank Registers, R0-R15 (rather than
  register related to the current mode, such like R14_svc etc.)
  Base write-back should not be used for User bank transfer.
  Caution - When instruction is LDM:
  If the following instruction reads from a banked register (eg. R14_svc),
  then CPU might still read R14 instead; if necessary insert a dummy NOP.
```



## Notes


The base address should be usually word-aligned.

LDM Rn,...,PC on ARMv4 leaves CPSR.T unchanged.

LDR Rn,...,PC on ARMv5 sets CPSR.T to \<op> Bit0, (1=Switch to Thumb).



## Transfer Order


The lowest Register in Rlist (R0 if its in the list) will be loaded/stored
to/from the lowest memory address.

Internally, the rlist register are always processed with INCREASING addresses
(ie. for DECREASING addressing modes, the CPU does first calculate the lowest
address, and does then process rlist with increasing addresses; this detail can
be important when accessing memory mapped I/O ports).



## Strange Effects on Invalid Rlist's


Empty Rlist: R15 loaded/stored (ARMv4 only), and Rb=Rb+/-40h (ARMv4-v5).

Writeback with Rb included in Rlist: Store OLD base if Rb is FIRST entry in
Rlist, otherwise store NEW base (STM/ARMv4), always store OLD base (STM/ARMv5),
no writeback (LDM/ARMv4), writeback if Rb is "the ONLY register, or NOT the
LAST register" in Rlist (LDM/ARMv5).




# ARM Opcodes: Memory: Single Data Swap (SWP)




## Opcode Format


```
  Bit    Expl.
  31-28  Condition
  27-23  Must be 00010b for this instruction
         Opcode (fixed)
           SWP{cond}{B} Rd,Rm,[Rn]      ;Rd=[Rn], [Rn]=Rm
  22     B - Byte/Word bit (0=swap 32bit/word, 1=swap 8bit/byte)
  21-20  Must be 00b for this instruction
  19-16  Rn - Base register                     (R0-R14)
  15-12  Rd - Destination Register              (R0-R14)
  11-4   Must be 00001001b for this instruction
  3-0    Rm - Source Register                   (R0-R14)
```

SWP/SWPB supported by ARMv2a and up. SWP/SWPB has been deprecated in ARMv6,
made optional in ARMv7 (with the possibility of disabling it if still
available), and removed in ARMv8.

Swap works properly including if Rm and Rn specify the same register.

R15 may not be used for either Rn,Rd,Rm. (Rn=R15 would be MRS opcode).

Upper bits of Rd are zero-expanded when using Byte quantity. For info about
byte and word data memory addressing, read LDR and STR opcode description.

Execution Time: 1S+2N+1I. That is, 2N data cycles, 1S code cycle, plus 1I.




# ARM Opcodes: Coprocessor Instructions (MRC/MCR, LDC/STC, CDP, MCRR/MRRC)




## Coprocessor Register Transfers (MRC, MCR) (with ARM Register read/write)


```
  Bit    Expl.
  31-28  Condition (or 1111b for MRC2/MCR2 opcodes on ARMv5 and up)
  27-24  Must be 1110b for this instruction
  23-21  CP Opc - Coprocessor operation code         (0-7)
  20     ARM-Opcode (0-1)
          0: MCR{cond} Pn,<cpopc>,Rd,Cn,Cm{,<cp>}   ;move from ARM to CoPro
          0: MCR2      Pn,<cpopc>,Rd,Cn,Cm{,<cp>}   ;move from ARM to CoPro
          1: MRC{cond} Pn,<cpopc>,Rd,Cn,Cm{,<cp>}   ;move from CoPro to ARM
          1: MRC2      Pn,<cpopc>,Rd,Cn,Cm{,<cp>}   ;move from CoPro to ARM
  19-16  Cn     - Coprocessor source/dest. Register  (C0-C15)
  15-12  Rd     - ARM source/destination Register    (R0-R15)
  11-8   Pn     - Coprocessor number                 (P0-P15)
  7-5    CP     - Coprocessor information            (0-7)
  4      Reserved, must be one (1) (otherwise CDP opcode)
  3-0    Cm     - Coprocessor operand Register       (C0-C15)
```

MCR/MRC supported by ARMv2 and up, MCR2/MRC2 by ARMv5 and up.

A22i syntax allows to use MOV with Rd specified as first (dest), or last
(source) operand. Native MCR/MRC syntax uses Rd as middle operand, \<cp>
can be ommited if \<cp> is zero.

When using MCR with R15: Coprocessor will receive a data value of PC+12.

When using MRC with R15: Bit 31-28 of data are copied to Bit 31-28 of CPSR (ie.
N,Z,C,V flags), other data bits are ignored, CPSR Bit 27-0 are not affected,
R15 (PC) is not affected.

Execution time: 1S+bI+1C for MCR, 1S+(b+1)I+1C for MRC.

Return: For MRC only: Either R0-R14 modified, or flags affected (see above).

For details refer to original ARM docs. The opcodes are irrelevant for GBA/NDS7
because no coprocessor exists (except for a dummy CP14 unit). However, NDS9
includes a working CP15 unit. And, 3DS ARM11 uses CP10/CP11 as VFP floating
point unit.

- [ARM CP14 ICEbreaker Debug Communications Channel](#armcp14icebreakerdebugcommunicationschannel)
- [ARM CP15 System Control Coprocessor](#armcp15systemcontrolcoprocessor)
- [ARM Vector Floating-point Unit (VFP)](#armvectorfloatingpointunitvfp)


## Coprocessor Data Transfers (LDC, STC) (with Memory read/write)


```
  Bit    Expl.
  31-28  Condition (or 1111b for LDC2/STC2 opcodes on ARMv5 and up)
  27-25  Must be 110b for this instruction
  24     P - Pre/Post (0=post; add offset after transfer, 1=pre; before trans.)
  23     U - Up/Down Bit (0=down; subtract offset from base, 1=up; add to base)
  22     N - Transfer length (0-1, interpretation depends on co-processor)
  21     W - Write-back bit (0=no write-back, 1=write address into base)
  20     Opcode (0-1)
          0: STC{cond}{L} Pn,Cd,<Address>  ;Store to memory (from coprocessor)
          0: STC2{L}      Pn,Cd,<Address>  ;Store to memory (from coprocessor)
          1: LDC{cond}{L} Pn,Cd,<Address>  ;Read from memory (to coprocessor)
          1: LDC2{L}      Pn,Cd,<Address>  ;Read from memory (to coprocessor)
          whereas {L} indicates long transfer (Bit 22: N=1)
  19-16  Rn     - ARM Base Register              (R0-R15)     (R15=PC+8)
  15-12  Cd     - Coprocessor src/dest Register  (C0-C15)
  11-8   Pn     - Coprocessor number             (P0-P15)
  7-0    Offset - Unsigned Immediate, step 4     (0-1020, in steps of 4)
```

LDC/STC supported by ARMv2 and up, LDC2/STC2 by ARMv5 and up.

Execution time: (n-1)S+2N+bI, n=number of words transferred.

For details refer to original ARM docs, irrelevant in GBA because no
coprocessor exists.



## Coprocessor Data Operations (CDP) (without Memory or ARM Register operand)


```
  Bit    Expl.
  31-28  Condition (or 1111b for CDP2 opcode on ARMv5 and up)
  27-24  Must be 1110b for this instruction
         ARM-Opcode (fixed)
           CDP{cond} Pn,<cpopc>,Cd,Cn,Cm{,<cp>}
           CDP2      Pn,<cpopc>,Cd,Cn,Cm{,<cp>}
  23-20  CP Opc - Coprocessor operation code       (0-15)
  19-16  Cn     - Coprocessor operand Register     (C0-C15)
  15-12  Cd     - Coprocessor destination Register (C0-C15)
  11-8   Pn     - Coprocessor number               (P0-P15)
  7-5    CP     - Coprocessor information          (0-7)
  4      Reserved, must be zero (otherwise MCR/MRC opcode)
  3-0    Cm     - Coprocessor operand Register     (C0-C15)
```

CDP supported by ARMv2 and up, CDP2 by ARMv5 and up.

Execution time: 1S+bI, b=number of cycles in coprocessor busy-wait loop.

Return: No flags affected, no ARM-registers used/modified.

For details refer to original ARM docs, irrelevant in GBA because no
coprocessor exists.



## Coprocessor Double-Register Transfer (MCRR, MRRC) - ARMv5TE and up only


```
  Bit    Expl.
  31-28  Condition
  27-21  Must be 1100010b for this instruction
  20     L - Opcode (Load/Store)
          0: MCRR{cond} Pn,opcode,Rd,Rn,Cm  ;write Rd,Rn to coproc
          0: MCRR2      Pn,opcode,Rd,Rn,Cm  ;write Rd,Rn to coproc
          1: MRRC{cond} Pn,opcode,Rd,Rn,Cm  ;read Rd,Rn from coproc
          1: MRRC2      Pn,opcode,Rd,Rn,Cm  ;read Rd,Rn from coproc
  19-16  Rn - Second source/dest register      (R0-R14)
  15-12  Rd - First source/dest register       (R0-R14)
  11-8   Pn     - Coprocessor number           (P0-P15)
  7-4    CP Opc - Coprocessor operation code   (0-15)
  3-0    Cm     - Coprocessor operand Register (C0-C15)
```

MCRR/MRRC are supported by ARMv5TE and up (not ARMv5, not ARMv5TExP).

MCRR2/MRRC2 are supported by ARMv6 and up.




# THUMB Instruction Summary



The table below lists all THUMB mode instructions with clock cycles, affected
CPSR flags, Format/chapter number, and description.

Only register R0..R7 can be used in thumb mode (unless R8-15,SP,PC are
explicitly mentioned).



## Logical Operations


```
  Instruction           Cycles Flags Format Expl.
  MOV{S} Rd,Imm8bit      1S     NZ--  3   Rd=nn
  MOV{S} Rd,Rs           1S     NZ00  2   Rd=Rs+0       (Pre-UAL)
  CPY    Rd,Rs           1S     ----  5   Rd=Rs         (Pre-UAL, ARMv6)
  MOV    Rd,Rs           1S     ----  5   Rd=Rs         (UAL)
  MOV{S} Rd,Rs           1S     NZ--  2   Rd=Rs SHL 0   (UAL)
  MOV    R0..14,R8..15   1S     ----  5   Rd=Rs
  MOV    R8..14,R0..15   1S     ----  5   Rd=Rs
  MOV    R15,R0..15      2S+1N  ----  5   PC=Rs
  MVN{S} Rd,Rs           1S     NZ--  4   Rd=NOT Rs
  AND{S} Rd,Rs           1S     NZ--  4   Rd=Rd AND Rs
  TST    Rd,Rs           1S     NZ--  4 Void=Rd AND Rs
  BIC{S} Rd,Rs           1S     NZ--  4   Rd=Rd AND NOT Rs
  ORR{S} Rd,Rs           1S     NZ--  4   Rd=Rd OR Rs
  EOR{S} Rd,Rs           1S     NZ--  4   Rd=Rd XOR Rs
  LSL{S} Rd,Rs,Imm5bit   1S     NZc-  1   Rd=Rs SHL nn
  LSL{S} Rd,Rs           1S+1I  NZc-  4   Rd=Rd SHL (Rs AND 0FFh)
  LSR{S} Rd,Rs,Imm5bit   1S     NZc-  1   Rd=Rs SHR nn
  LSR{S} Rd,Rs           1S+1I  NZc-  4   Rd=Rd SHR (Rs AND 0FFh)
  ASR{S} Rd,Rs,Imm5bit   1S     NZc-  1   Rd=Rs SAR nn
  ASR{S} Rd,Rs           1S+1I  NZc-  4   Rd=Rd SAR (Rs AND 0FFh)
  ROR{S} Rd,Rs           1S+1I  NZc-  4   Rd=Rd ROR (Rs AND 0FFh)
  NOP                    1S     ----  5   R8=R8
```

Carry flag affected only if shift amount is non-zero.



## Arithmetic Operations and Multiply


```
  Instruction           Cycles Flags Format Expl.
  ADD{S} Rd,Rs,Imm3bit   1S     NZCV  2   Rd=Rs+nn
  ADD{S} Rd,Imm8bit      1S     NZCV  3   Rd=Rd+nn
  ADD{S} Rd,Rs,Rn        1S     NZCV  2   Rd=Rs+Rn
  ADD    Rd,Rs           1S     ----  5   Rd=Rd+Rs (UAL only)
  ADD    R0..14,R8..15   1S     ----  5   Rd=Rd+Rs
  ADD    R8..14,R0..15   1S     ----  5   Rd=Rd+Rs
  ADD    R15,R0..15      2S+1N  ----  5   PC=Rd+Rs
  ADD    Rd,PC,Imm8bit*4 1S     ---- 12   Rd=(($+4) AND NOT 2)+nn
  ADD    Rd,SP,Imm8bit*4 1S     ---- 12   Rd=SP+nn
  ADD    SP,Imm7bit*4    1S     ---- 13   SP=SP+nn
  ADD    SP,-Imm7bit*4   1S     ---- 13   SP=SP-nn
  ADC{S} Rd,Rs           1S     NZCV  4   Rd=Rd+Rs+Cy
  SUB{S} Rd,Rs,Imm3Bit   1S     NZCV  2   Rd=Rs-nn
  SUB{S} Rd,Imm8bit      1S     NZCV  3   Rd=Rd-nn
  SUB{S} Rd,Rs,Rn        1S     NZCV  2   Rd=Rs-Rn
  SUB    SP,Imm7bit*4    1S     ---- 13   SP=SP-nn  ;\alias for ADD
  SUB    SP,-Imm7bit*4   1S     ---- 13   SP=SP+nn  ;/with flipped sign
  SBC{S} Rd,Rs           1S     NZCV  4   Rd=Rd-Rs-NOT Cy
  NEG{S} Rd,Rs           1S     NZCV  4   Rd=0-Rs
  CMP    Rd,Imm8bit      1S     NZCV  3 Void=Rd-nn
  CMP    Rd,Rs           1S     NZCV  4 Void=Rd-Rs
  CMP    R0-15,R8-15     1S     NZCV  5 Void=Rd-Rs
  CMP    R8-15,R0-15     1S     NZCV  5 Void=Rd-Rs
  CMN    Rd,Rs           1S     NZCV  4 Void=Rd+Rs
  MUL{S} Rd,Rs           1S+mI  NZx-  4   Rd=Rd*Rs
```



## Jumps and Calls


```
  Instruction        Cycles    Flags Format Expl.
  B disp              2S+1N     ---- 18  PC=$+/-2048
  BL disp             3S+1N     ---- 19  PC=$+/-4M, LR=$+5
  B{cond=true} disp   2S+1N     ---- 16  PC=$+/-0..256
  B{cond=false} disp  1S        ---- 16  N/A
  BX R0..15           2S+1N     ----  5  PC=Rs, ARM/THUMB (Rs bit0)
  SWI Imm8bit         2S+1N     ---- 17  PC=8, ARM SVC mode, LR=$+2
  BKPT Imm8bit        ???       ---- 17  ??? ARM9 Prefetch Abort
  BLX disp            ???       ---- ??? ??? ARM9
  BLX R0..R14         ???       ---- ??? ??? ARM9
  POP {Rlist,}PC   (n+1)S+2N+1I ---- 14
  MOV R15,R0..15      2S+1N     ----  5  PC=Rs
  ADD R15,R0..15      2S+1N     ----  5  PC=Rd+Rs
```

The thumb BL instruction occupies two 16bit opcodes, 32bit in total.



## Memory Load/Store


```
  Instruction        Cycles    Flags Format Expl.
  LDR  Rd,[Rb,5bit*4] 1S+1N+1I  ----  9  Rd = WORD[Rb+nn]
  LDR  Rd,[PC,8bit*4] 1S+1N+1I  ----  6  Rd = WORD[PC+nn]
  LDR  Rd,[SP,8bit*4] 1S+1N+1I  ---- 11  Rd = WORD[SP+nn]
  LDR  Rd,[Rb,Ro]     1S+1N+1I  ----  7  Rd = WORD[Rb+Ro]
  LDRB Rd,[Rb,5bit*1] 1S+1N+1I  ----  9  Rd = BYTE[Rb+nn]
  LDRB Rd,[Rb,Ro]     1S+1N+1I  ----  7  Rd = BYTE[Rb+Ro]
  LDRH Rd,[Rb,5bit*2] 1S+1N+1I  ---- 10  Rd = HALFWORD[Rb+nn]
  LDRH Rd,[Rb,Ro]     1S+1N+1I  ----  8  Rd = HALFWORD[Rb+Ro]
  LDSB Rd,[Rb,Ro]     1S+1N+1I  ----  8  Rd = SIGNED_BYTE[Rb+Ro]
  LDSH Rd,[Rb,Ro]     1S+1N+1I  ----  8  Rd = SIGNED_HALFWORD[Rb+Ro]
  STR  Rd,[Rb,5bit*4] 2N        ----  9  WORD[Rb+nn] = Rd
  STR  Rd,[SP,8bit*4] 2N        ---- 11  WORD[SP+nn] = Rd
  STR  Rd,[Rb,Ro]     2N        ----  7  WORD[Rb+Ro] = Rd
  STRB Rd,[Rb,5bit*1] 2N        ----  9  BYTE[Rb+nn] = Rd
  STRB Rd,[Rb,Ro]     2N        ----  7  BYTE[Rb+Ro] = Rd
  STRH Rd,[Rb,5bit*2] 2N        ---- 10  HALFWORD[Rb+nn] = Rd
  STRH Rd,[Rb,Ro]     2N        ----  8  HALFWORD[Rb+Ro]=Rd
  PUSH {Rlist}{LR}    (n-1)S+2N ---- 14
  POP  {Rlist}{PC}              ---- 14  (ARM9: with mode switch)
  STMIA Rb!,{Rlist}   (n-1)S+2N ---- 15
  LDMIA Rb!,{Rlist}   nS+1N+1I  ---- 15
```



## THUMB Binary Opcode Format


This table summarizes the position of opcode/parameter bits for THUMB mode
instructions, Format 1-19.


```
 Form|_15|_14|_13|_12|_11|_10|_9_|_8_|_7_|_6_|_5_|_4_|_3_|_2_|_1_|_0_|
 __1_|_0___0___0_|__Op___|_______Offset______|____Rs_____|____Rd_____|Shifted
 __2_|_0___0___0___1___1_|_I,_Op_|___Rn/nn___|____Rs_____|____Rd_____|ADD/SUB
 __3_|_0___0___1_|__Op___|____Rd_____|_____________Offset____________|Immedi.
 __4_|_0___1___0___0___0___0_|______Op_______|____Rs_____|____Rd_____|AluOp
 __5_|_0___1___0___0___0___1_|__Op___|Hd_|Hs_|____Rs_____|____Rd_____|HiReg/BX
 __6_|_0___1___0___0___1_|____Rd_____|_____________Word______________|LDR PC
 __7_|_0___1___0___1_|__Op___|_0_|___Ro______|____Rb_____|____Rd_____|LDR/STR
 __8_|_0___1___0___1_|__Op___|_1_|___Ro______|____Rb_____|____Rd_____|""H/SB/SH
 __9_|_0___1___1_|__Op___|_______Offset______|____Rb_____|____Rd_____|""{B}
 _10_|_1___0___0___0_|Op_|_______Offset______|____Rb_____|____Rd_____|""H
 _11_|_1___0___0___1_|Op_|____Rd_____|_____________Word______________|"" SP
 _12_|_1___0___1___0_|Op_|____Rd_____|_____________Word______________|ADD PC/SP
 _13_|_1___0___1___1___0___0___0___0_|_S_|___________Word____________|ADD SP,nn
 _14_|_1___0___1___1_|Op_|_1___0_|_R_|____________Rlist______________|PUSH/POP
 _17_|_1___0___1___1___1___1___1___0_|___________User_Data___________|ARM9:BKPT
 _X__|_1___0___1___1___   ..............................             |ARM11...
  0110 011 Change Processor State        CPS on page B4-2
  0001 xxx Compare and Branch on Zero    CBNZ, CBZ on page A6-52
  1011 xxx Compare and Branch on Nonzero CBNZ, CBZ on page A6-52
  0011 xxx Compare and Branch on Zero    CBNZ, CBZ on page A6-52
  1001 xxx Compare and Branch on Nonzero CBNZ, CBZ on page A6-52
  0010 00x Signed Extend Halfword        SXTH on page A6-256
  0010 01x Signed Extend Byte            SXTB on page A6-254
  0010 10x Unsigned Extend Halfword      UXTH on page A6-274
  0010 11x Unsigned Extend Byte          UXTB on page A6-272
  1010 00x Byte-Reverse Word             REV on page A6-191
  1010 01x Byte-Reverse Packed Halfword  REV16 on page A6-192
  1010 11x Byte-Reverse Signed Halfword  REVSH on page A6-193
  1111 xxx If-Then, and hints If-Then, and hints on page A5-11
 _15_|_1___1___0___0_|Op_|____Rb_____|____________Rlist______________|STM/LDM
 _16_|_1___1___0___1_|_____Cond______|_________Signed_Offset_________|B{cond}
 _U__|_1___1___0___1___1___1___1___0_|_____________var_______________|UndefARM9
 _17_|_1___1___0___1___1___1___1___1_|___________User_Data___________|SWI
 _18_|_1___1___1___0___0_|________________Offset_____________________|B
 _19_|_1___1___1___0___1_|_________________________var___________|_0_|BLX.ARM9
 _U__|_1___1___1___0___1_|_________________________var___________|_1_|UndefARM9
 _19_|_1___1___1___1_|_H_|______________Offset_Low/High______________|BL,BLX
```


Further UNDEFS ??? ARM9?

- 1011 0001 xxxxxxxx (reserved)
- 1011 0x1x xxxxxxxx (reserved)
- 1011 10xx xxxxxxxx (reserved)
- 1011 1111 xxxxxxxx (reserved)
- 1101 1110 xxxxxxxx (free for user)




# THUMB Opcodes: Register Operations (ALU, BX)




## THUMB.1: move shifted register


```
  15-13  Must be 000b for 'move shifted register' instructions
  12-11  Opcode
           00b: LSL{S} Rd,Rs,#Offset   (logical/arithmetic shift left)
           01b: LSR{S} Rd,Rs,#Offset   (logical    shift right)
           10b: ASR{S} Rd,Rs,#Offset   (arithmetic shift right)
           11b: Reserved (used for add/subtract instructions)
  10-6   Offset                     (0-31)
  5-3    Rs - Source register       (R0..R7)
  2-0    Rd - Destination register  (R0..R7)
```

Example: LSL Rd,Rs,#nn ; Rd = Rs \<\< nn ; ARM equivalent: MOVS Rd,Rs,LSL
#nn

Zero shift amount is having special meaning (same as for ARM shifts), LSL#0
performs no shift (the carry flag remains unchanged), LSR/ASR#0 are interpreted
as LSR/ASR#32. Attempts to specify LSR/ASR#0 in source code are automatically
redirected as LSL#0, and source LSR/ASR#32 is redirected as opcode LSR/ASR#0.

Execution Time: 1S

Flags: Z=zeroflag, N=sign, C=carry (except LSL#0: C=unchanged), V=unchanged.



## THUMB.2: add/subtract


```
  15-11  Must be 00011b for 'add/subtract' instructions
  10-9   Opcode (0-3)
           0: ADD{S} Rd,Rs,Rn   ;add register        Rd=Rs+Rn
           1: SUB{S} Rd,Rs,Rn   ;subtract register   Rd=Rs-Rn
           2: ADD{S} Rd,Rs,#nn  ;add immediate       Rd=Rs+nn
           3: SUB{S} Rd,Rs,#nn  ;subtract immediate  Rd=Rs-nn
         Pseudo/alias opcode with Imm=0:
           2: MOV{ADDS} Rd,Rs   ;move (affects cpsr) Rd=Rs+0
  8-6    For Register Operand:
           Rn - Register Operand (R0..R7)
         For Immediate Operand:
           nn - Immediate Value  (0-7)
  5-3    Rs - Source register       (R0..R7)
  2-0    Rd - Destination register  (R0..R7)
```

Return: Rd contains result, N,Z,C,V affected (including MOV).

Execution Time: 1S



## THUMB.3: move/compare/add/subtract immediate


```
  15-13  Must be 001b for this type of instructions
  12-11  Opcode
           00b: MOV{S} Rd,#nn      ;move     Rd   = #nn
           01b: CMP    Rd,#nn      ;compare  Void = Rd - #nn
           10b: ADD{S} Rd,#nn      ;add      Rd   = Rd + #nn
           11b: SUB{S} Rd,#nn      ;subtract Rd   = Rd - #nn
  10-8   Rd - Destination Register  (R0..R7)
  7-0    nn - Unsigned Immediate    (0-255)
```

ARM equivalents for MOV/CMP/ADD/SUB are MOVS/CMP/ADDS/SUBS same format.

Execution Time: 1S

Return: Rd contains result (except CMP), N,Z,C,V affected (for MOV only N,Z).



## THUMB.4: ALU operations


```
  15-10  Must be 010000b for this type of instructions
  9-6    Opcode (0-Fh)
           0: AND{S} Rd,Rs     ;AND logical       Rd = Rd AND Rs
           1: EOR{S} Rd,Rs     ;XOR logical       Rd = Rd XOR Rs
           2: LSL{S} Rd,Rs     ;log. shift left   Rd = Rd << (Rs AND 0FFh)
           3: LSR{S} Rd,Rs     ;log. shift right  Rd = Rd >> (Rs AND 0FFh)
           4: ASR{S} Rd,Rs     ;arit shift right  Rd = Rd SAR (Rs AND 0FFh)
           5: ADC{S} Rd,Rs     ;add with carry    Rd = Rd + Rs + Cy
           6: SBC{S} Rd,Rs     ;sub with carry    Rd = Rd - Rs - NOT Cy
           7: ROR{S} Rd,Rs     ;rotate right      Rd = Rd ROR (Rs AND 0FFh)
           8: TST    Rd,Rs     ;test            Void = Rd AND Rs
           9: NEG{S} Rd,Rs     ;negate            Rd = 0 - Rs
           A: CMP    Rd,Rs     ;compare         Void = Rd - Rs
           B: CMN    Rd,Rs     ;neg.compare     Void = Rd + Rs
           C: ORR{S} Rd,Rs     ;OR logical        Rd = Rd OR Rs
           D: MUL{S} Rd,Rs     ;multiply          Rd = Rd * Rs
           E: BIC{S} Rd,Rs     ;bit clear         Rd = Rd AND NOT Rs
           F: MVN{S} Rd,Rs     ;not               Rd = NOT Rs
  5-3    Rs - Source Register       (R0..R7)
  2-0    Rd - Destination Register  (R0..R7)
```

ARM equivalent for NEG would be RSBS.

Return: Rd contains result (except TST,CMP,CMN),

Affected Flags:

```
  N,Z,C,V for  ADC,SBC,NEG,CMP,CMN
  N,Z,C   for  LSL,LSR,ASR,ROR (carry flag unchanged if zero shift amount)
  N,Z,C   for  MUL on ARMv4 and below: carry flag destroyed
  N,Z     for  MUL on ARMv5 and above: carry flag unchanged
  N,Z     for  AND,EOR,TST,ORR,BIC,MVN
```

Execution Time:

```
  1S      for  AND,EOR,ADC,SBC,TST,NEG,CMP,CMN,ORR,BIC,MVN
  1S+1I   for  LSL,LSR,ASR,ROR
  1S+mI   for  MUL on ARMv4 (m=1..4; depending on MSBs of incoming Rd value)
  1S+mI   for  MUL on ARMv5 (m=3; fucking slow, no matter of MSBs of Rd value)
```



## THUMB.5: Hi register operations/branch exchange


```
  15-10  Must be 010001b for this type of instructions
  9-8    Opcode (0-3)
           0: ADD Rd,Rs   ;add        Rd = Rd+Rs
           1: CMP Rd,Rs   ;compare  Void = Rd-Rs  ;CPSR affected
           2: MOV Rd,Rs   ;move       Rd = Rs
           2: NOP         ;nop        R8 = R8
           3: BX  Rs      ;jump       PC = Rs     ;may switch THUMB/ARM
           3: BLX Rs      ;call       PC = Rs     ;may switch THUMB/ARM (ARM9)
  7      MSBd - Destination Register most significant bit (or BL/BLX flag)
  6      MSBs - Source Register most significant bit
  5-3    Rs - Source Register        (together with MSBs: R0..R15)
  2-0    Rd - Destination Register   (together with MSBd: R0..R15)
```

Restrictions: For ADD/CMP/MOV, MSBs and/or MSBd must be set, ie. it is not
allowed that both are cleared.

When using R15 (PC) as operand, the value will be the address of the
instruction plus 4 (ie. $+4). Except for BX R15: CPU switches to ARM state, and
PC is auto-aligned as (($+4) AND NOT 2).

For BX, MSBs may be 0 or 1, MSBd must be zero, Rd is not used/zero.

For BLX, MSBs may be 0 or 1, MSBd must be set, Rd is not used/zero.

For BX/BLX, when Bit 0 of the value in Rs is zero:

```
  Processor will be switched into ARM mode!
  If so, Bit 1 of Rs must be cleared (32bit word aligned).
  Thus, BX PC (switch to ARM) may be issued from word-aligned address
  only, the destination is PC+4 (ie. the following halfword is skipped).
```

BLX may not use R15. BLX saves the return address as LR=PC+3 (with thumb bit).

Using BLX R14 is possible (sets PC=Old\_LR, and New\_LR=retadr).

Assemblers/Disassemblers should use MOV R8,R8 as NOP (in THUMB mode).

Return: Only CMP affects CPSR condition flags!

Execution Time:

```
 1S     for ADD/MOV/CMP
 2S+1N  for ADD/MOV with Rd=R15, and for BX
```




# THUMB Opcodes: Memory Load/Store (LDR/STR)




## THUMB.6: load PC-relative (for loading immediates from literal pool)


```
  15-11  Must be 01001b for this type of instructions
  N/A    Opcode (fixed)
           LDR Rd,[PC,#nn]      ;load 32bit    Rd = WORD[PC+nn]
  10-8   Rd - Destination Register   (R0..R7)
  7-0    nn - Unsigned offset        (0-1020 in steps of 4)
```

The value of PC will be interpreted as (($+4) AND NOT 2).

Return: No flags affected, data loaded into Rd.

Execution Time: 1S+1N+1I



## THUMB.7: load/store with register offset


```
  15-12  Must be 0101b for this type of instructions
  11-10  Opcode (0-3)
          0: STR  Rd,[Rb,Ro]   ;store 32bit data  WORD[Rb+Ro] = Rd
          1: STRB Rd,[Rb,Ro]   ;store  8bit data  BYTE[Rb+Ro] = Rd
          2: LDR  Rd,[Rb,Ro]   ;load  32bit data  Rd = WORD[Rb+Ro]
          3: LDRB Rd,[Rb,Ro]   ;load   8bit data  Rd = BYTE[Rb+Ro]
  9      Must be zero (0) for this type of instructions
  8-6    Ro - Offset Register              (R0..R7)
  5-3    Rb - Base Register                (R0..R7)
  2-0    Rd - Source/Destination Register  (R0..R7)
```

Return: No flags affected, data loaded either into Rd or into memory.

Execution Time: 1S+1N+1I for LDR, or 2N for STR



## THUMB.8: load/store sign-extended byte/halfword


```
  15-12  Must be 0101b for this type of instructions
  11-10  Opcode (0-3)
          0: STRH Rd,[Rb,Ro]  ;store 16bit data          HALFWORD[Rb+Ro] = Rd
          1: LDSB Rd,[Rb,Ro]  ;load sign-extended 8bit   Rd = BYTE[Rb+Ro]
          2: LDRH Rd,[Rb,Ro]  ;load zero-extended 16bit  Rd = HALFWORD[Rb+Ro]
          3: LDSH Rd,[Rb,Ro]  ;load sign-extended 16bit  Rd = HALFWORD[Rb+Ro]
  9      Must be set (1) for this type of instructions
  8-6    Ro - Offset Register              (R0..R7)
  5-3    Rb - Base Register                (R0..R7)
  2-0    Rd - Source/Destination Register  (R0..R7)
```

Return: No flags affected, data loaded either into Rd or into memory.

Execution Time: 1S+1N+1I for LDR, or 2N for STR



## THUMB.9: load/store with immediate offset


```
  15-13  Must be 011b for this type of instructions
  12-11  Opcode (0-3)
          0: STR  Rd,[Rb,#nn]  ;store 32bit data   WORD[Rb+nn] = Rd
          1: LDR  Rd,[Rb,#nn]  ;load  32bit data   Rd = WORD[Rb+nn]
          2: STRB Rd,[Rb,#nn]  ;store  8bit data   BYTE[Rb+nn] = Rd
          3: LDRB Rd,[Rb,#nn]  ;load   8bit data   Rd = BYTE[Rb+nn]
  10-6   nn - Unsigned Offset              (0-31 for BYTE, 0-124 for WORD)
  5-3    Rb - Base Register                (R0..R7)
  2-0    Rd - Source/Destination Register  (R0..R7)
```

Return: No flags affected, data loaded either into Rd or into memory.

Execution Time: 1S+1N+1I for LDR, or 2N for STR



## THUMB.10: load/store halfword


```
  15-12  Must be 1000b for this type of instructions
  11     Opcode (0-1)
          0: STRH Rd,[Rb,#nn]  ;store 16bit data   HALFWORD[Rb+nn] = Rd
          1: LDRH Rd,[Rb,#nn]  ;load  16bit data   Rd = HALFWORD[Rb+nn]
  10-6   nn - Unsigned Offset              (0-62, step 2)
  5-3    Rb - Base Register                (R0..R7)
  2-0    Rd - Source/Destination Register  (R0..R7)
```

Return: No flags affected, data loaded either into Rd or into memory.

Execution Time: 1S+1N+1I for LDR, or 2N for STR



## THUMB.11: load/store SP-relative


```
  15-12  Must be 1001b for this type of instructions
  11     Opcode (0-1)
          0: STR  Rd,[SP,#nn]  ;store 32bit data   WORD[SP+nn] = Rd
          1: LDR  Rd,[SP,#nn]  ;load  32bit data   Rd = WORD[SP+nn]
  10-8   Rd - Source/Destination Register  (R0..R7)
  7-0    nn - Unsigned Offset              (0-1020, step 4)
```

Return: No flags affected, data loaded either into Rd or into memory.

Execution Time: 1S+1N+1I for LDR, or 2N for STR




# THUMB Opcodes: Memory Addressing (ADD PC/SP)




## THUMB.12: get relative address


```
  15-12  Must be 1010b for this type of instructions
  11     Opcode/Source Register (0-1)
          0: ADD  Rd,PC,#nn    ;Rd = (($+4) AND NOT 2) + nn
          1: ADD  Rd,SP,#nn    ;Rd = SP + nn
  10-8   Rd - Destination Register         (R0..R7)
  7-0    nn - Unsigned Offset              (0-1020, step 4)
```

Return: No flags affected, result in Rd.

Execution Time: 1S



## THUMB.13: add offset to stack pointer


```
  15-8   Must be 10110000b for this type of instructions
  7      Opcode/Sign
          0: ADD  SP,#nn       ;SP = SP + nn
          1: ADD  SP,#-nn      ;SP = SP - nn
          1: SUB  SP,#nn       ;SP = SP - nn  ;\alias for ADD
          0: SUB  SP,#-nn      ;SP = SP + nn  ;/with flipped sign
  6-0    nn - Unsigned Offset    (0-508, step 4)
```

Return: No flags affected, SP adjusted.

Execution Time: 1S




# THUMB Opcodes: Memory Multiple Load/Store (PUSH/POP and LDM/STM)




## THUMB.14: push/pop registers


```
  15-12  Must be 1011b for this type of instructions
  11     Opcode (0-1)
          0: PUSH {Rlist}{LR}   ;store in memory, decrements SP (R13)
          1: POP  {Rlist}{PC}   ;load from memory, increments SP (R13)
  10-9   Must be 10b for this type of instructions
  8      PC/LR Bit (0-1)
          0: No
          1: PUSH LR (R14), or POP PC (R15)
  7-0    Rlist - List of Registers (R7..R0)
```

In THUMB mode stack is always meant to be 'full descending', ie. PUSH is
equivalent to 'STMFD/STMDB' and POP to 'LDMFD/LDMIA' in ARM mode.

Examples:

```
 PUSH {R0-R3}     ;push R0,R1,R2,R3
 PUSH {R0,R2,LR}  ;push R0,R2,LR
 POP  {R4,R7}     ;pop R4,R7
 POP  {R2-R4,PC}  ;pop R2,R3,R4,PC
```

Note: When calling to a sub-routine, the return address is stored in LR
register, when calling further sub-routines, PUSH {LR} must be used to save
higher return address on stack. If so, POP {PC} can be later used to return
from the sub-routine.

POP {PC} ignores the least significant bit of the return address (processor
remains in thumb state even if bit0 was cleared), when intending to return with
optional mode switch, use a POP/BX combination (eg. POP {R3} / BX R3).

ARM9: POP {PC} copies the LSB to thumb bit (switches to ARM if bit0=0).

Return: No flags affected, SP adjusted, registers loaded/stored.

Execution Time: nS+1N+1I (POP), (n+1)S+2N+1I (POP PC), or (n-1)S+2N (PUSH).



## THUMB.15: multiple load/store


```
  15-12  Must be 1100b for this type of instructions
  11     Opcode (0-1)
          0: STMIA Rb!,{Rlist}   ;store in memory, increments Rb
          1: LDMIA Rb!,{Rlist}   ;load from memory, increments Rb
  10-8   Rb - Base register (modified) (R0-R7)
  7-0    Rlist - List of Registers     (R7..R0)
```

Both STM and LDM are incrementing the Base Register.

The lowest register in the list (ie. R0, if it's in the list) is stored/loaded
at the lowest memory address.

Examples:

```
 STMIA R7!,{R0-R2}  ;store R0,R1,R2
 LDMIA R0!,{R1,R5}  ;store R1,R5
```

Return: No flags affected, Rb adjusted, registers loaded/stored.

Execution Time: nS+1N+1I for LDM, or (n-1)S+2N for STM.



## Strange Effects on Invalid Rlist's


Empty Rlist: R15 loaded/stored (ARMv4 only), and Rb=Rb+40h (ARMv4-v5).

Writeback with Rb included in Rlist: Store OLD base if Rb is FIRST entry in
Rlist, otherwise store NEW base (STM/ARMv4), always store OLD base (STM/ARMv5),
no writeback (LDM/ARMv4/ARMv5; at this point, THUMB opcodes work different than
ARM opcodes).




# THUMB Opcodes: Jumps and Calls




## THUMB.16: conditional branch


```
  15-12  Must be 1101b for this type of instructions
  11-8   Opcode/Condition (0-Fh)
          0: BEQ label        ;Z=1         ;equal (zero) (same)
          1: BNE label        ;Z=0         ;not equal (nonzero) (not same)
          2: BCS/BHS label    ;C=1         ;unsigned higher or same (carry set)
          3: BCC/BLO label    ;C=0         ;unsigned lower (carry cleared)
          4: BMI label        ;N=1         ;signed  negative (minus)
          5: BPL label        ;N=0         ;signed  positive or zero (plus)
          6: BVS label        ;V=1         ;signed  overflow (V set)
          7: BVC label        ;V=0         ;signed  no overflow (V cleared)
          8: BHI label        ;C=1 and Z=0 ;unsigned higher
          9: BLS label        ;C=0 or Z=1  ;unsigned lower or same
          A: BGE label        ;N=V         ;signed greater or equal
          B: BLT label        ;N<>V        ;signed less than
          C: BGT label        ;Z=0 and N=V ;signed greater than
          D: BLE label        ;Z=1 or N<>V ;signed less or equal
          E: Undefined, should not be used
          F: Reserved for SWI instruction (see SWI opcode)
  7-0    Signed Offset, step 2 ($+4-256..$+4+254)
```

Destination address must by halfword aligned (ie. bit 0 cleared)

Return: No flags affected, PC adjusted if condition true

Execution Time:

```
  2S+1N   if condition true (jump executed)
  1S      if condition false
```



## BX and ADD/MOV PC


See also THUMB.5: BX Rs, and ADD/MOV PC,Rs.



## THUMB.18: unconditional branch


```
  15-11  Must be 11100b for this type of instructions
  N/A    Opcode (fixed)
          B label   ;branch (jump)
  10-0   Signed Offset, step 2 ($+4-2048..$+4+2046)
```

Return: No flags affected, PC adjusted.

Execution Time: 2S+1N



## THUMB.19: long branch with link


This may be used to call (or jump) to a subroutine, return address is saved in
LR (R14).

Unlike all other THUMB mode instructions, this instruction occupies 32bit of
memory which are split into two 16bit THUMB opcodes.

- First Instruction - LR = PC+4+(nn SHL 12)
  - 15-11  Must be 11110b for BL/BLX type of instructions
  - 10-0   nn - Upper 11 bits of Target Address
- Second Instruction - PC = LR + (nn SHL 1), and LR = PC+2 OR 1 (and BLX: T=0)
  - 15-11  Opcode
                  - 11111b: BL label   ;branch long with link
                  - 11101b: BLX label  ;branch long with link switch to ARM mode (ARM9)
  - 10-0   nn - Lower 11 bits of Target Address (BLX: Bit0 Must be zero)

The destination address range is (PC+4)-400000h..+3FFFFEh, ie. PC+/-4M.

Target must be halfword-aligned. As Bit 0 in LR is set, it may be used to
return by a BX LR instruction (keeping CPU in THUMB mode).

Return: No flags affected, PC adjusted, return address in LR.

Execution Time: 3S+1N (first opcode 1S, second opcode 2S+1N).

Note: Exceptions may or may not occur between first and second opcode, this is
"implementation defined" (unknown how this is implemented in GBA and NDS).

Using only the 2nd half of BL as "BL LR+imm" is possible (for example, Mario
Golf Advance Tour for GBA uses opcode F800h as "BL LR+0").



## THUMB.17: software interrupt and breakpoint


SWI supposed for calls to the operating system - Enter Supervisor mode (SVC) in
ARM state. BKPT intended for debugging - enters Abort mode in ARM state via
Prefetch Abort vector.

```
  15-8   Opcode
          11011111b: SWI nn   ;software interrupt
          10111110b: BKPT nn  ;software breakpoint (ARMv5 and up)
  7-0    nn - Comment Field, ignored by processor (8bit value) (0-255)
```

Execution Time: 2S+1N

The exception handler may interprete the SWI Comment Field by examining the
lower 8bit of the 16bit opcode opcode at [R14\_svc-2].

If your are also using SWI's from inside of ARM mode, then the SWI handler must
examine the T Bit SPSR\_svc in order to determine whether it's been a ARM SWI -
and if so, examine the lower 24bit of the 32bit opcode opcode at [R14\_svc-4].

For Returning from SWI use "MOVS PC,R14", that instruction does restore both PC
and CPSR, ie. PC=R14\_svc, and CPSR=SPSR\_svc, and (as called from THUMB mode),
it'll also restore THUMB mode.

Nesting SWIs: SPSR\_svc and R14\_svc should be saved on stack before either
invoking nested SWIs, or (if the IRQ handler uses SWIs) before enabling IRQs.

Execution SWI/BKPT:

```
  R14_svc=PC+2     R14_abt=PC+4   ;save return address
  SPSR_svc=CPSR    SPSR_abt=CPSR  ;save CPSR flags
  CPSR=<changed>   CPSR=<changed> ;Enter svc/abt, ARM state, IRQs disabled
  PC=VVVV0008h     PC=VVVV000Ch   ;jump to SWI/PrefetchAbort vector address
```




# THUMB Opcodes: New THUMB Opcodes in ARM11




## THUMB.X: signed/unsigned extend byte/halfword (ARMv6)


These unneccessary opcodes are apparently meant to reduce typical compiler
overload (eg. for ensuring that "for i=0 to 7" won't end up with i>255).

```
  15-8   Must be 1011.0010b for this type of instructions
  7-6    Opcode
          00b  SXTH  Rd,Rm      ;sign-extend halfword
          01b  SXTB  Rd,Rm      ;sign-extend byte
          10b  UXTH  Rd,Rm      ;zero-extend halfword
          11b  UXTB  Rd,Rm      ;zero-extend byte
  5-3    Rm Source Register                    (R0-R7)
  2-0    Rd Destination Register               (R0-R7)
```

Return: No flags affected (though unspecified?).

Execution Time: ?



## THUMB.X: byte-reverse word/halfword(s) (ARMv6)


```
  15-8   Must be 1011.1010b for this type of instructions
  7-6    Opcode
          00b  REV   Rd,Rm      ;swap byte3/byte0 and byte2/byte1  ;word
          01b  REV16 Rd,Rm      ;swap byte3/byte2 and byte1/byte0  ;packed half
          11b  REVSH Rd,Rm      ;swap byte1/byte0 and sign-extend  ;signed half
  5-3    Rm Source Register                    (R0-R7)
  2-0    Rd Destination Register               (R0-R7)
```

Return: No flags affected (though unspecified?).

Execution Time: ?



## SETEND (ARMv6)


```
  15-4   Must be 101101100101b
  3      Opcode:
           0: SETEND LE   ;clear CPSR.E bit (little endian data access)
           1: SETEND BE   ;set CPSR.E bit (big endian data access)
  2-0    Should be 000b
```



## THUMB.X: change processor state (ARMv6)


```
  15-5   Must be 10110110011b
  4      Opcode:
           0: CPSIE {A}{I}{F}   ;Interrupt Enable
           1: CPSID {A}{I}{F}   ;Interrupt Disable
  3      Must be 0b
  2      A  Affect CPSR.A (?)    (0=No, 1=Yes)
  1      I  Affect CPSR.I (IRQ)  (0=No, 1=Yes)
  0      F  Affect CPSR.F (FIQ)  (0=No, 1=Yes)
```



## CPY


```
  15-8   Must be 01000110b for CPY Rd,Rm
  7      MSB of Rd
  6      MSB of Rm
  5-3    Rm Source Register
  2-0    Rd Destination Register
```

Move without changing flags. It's called CPY because THUMB syntax didn't
distinguish between MOV and MOVS (until UAL syntax was invented, which makes
the name CPY irrelevant).

CPY is officially supported in "T variants of ARMv6 and above" (in practice, it
should work on ARMv4T and up, but wasn't officially documented until ARMv6).





# ARM Classic vs UAL Syntax (Unified Assembler Language)



ARM has changed the ARM/THUMB syntax (apparently at some point between ARMv6
and ARMv6K). The new UAL syntax contains some cosmetic changes, and fixes some
serious flaws in the old THUMB syntax.

GBA/NDS software did traditionally use old syntax. DSi software probably, too.
3DS software uses ARMv6K, so it's more likely to use the new UAL syntax.



## THUMB code with {S} suffix


Most ALU opcodes do always affect flags in THUMB mode, although they were
written without {S} suffix in Pre-UAL syntax, which is problematic because the
same source code can behave differently for ARM and THUMB.

MOV/ADD/SUB don't affect flags when using SP, PC, or R8..R15 as source/dest
operands.

MOV/ADD have variants that don't affect flags for operands R0..R7 (these
variants were originally undocumented/reserved; the flag-less CPY variant was
officially allowed in ARMv6, the flag-less ADD seems to be allowed (?) in UAL).

MOV is a total mess because it relies on poorly defined pseudo opcodes (in the
Pre-UAL syntax it was common to encode it as ADD{S} opcode, which destroyed the
C,V flags).

```
  Pre-UAL               UAL
  MOV Rd,Imm            MOVS Rd,Imm                ;\
  LSL with R0..R7,0     MOVS with R0..R7           ;
  MOV with R0..R7       ADDS Rd,Rs,0               ; move
  MOV with R8..R15      MOV  with R8..R15          ;
  CPY with R0..R7       MOV  with R0..R7           ;
  SHIFT Rd,..,s         MOVS Rd,..,SHIFT s         ;/
  ADD with R0..R7       ADDS with R0..R7           ;\
  ADD with R8..R15      ADD  with R8..R15          ; add
  N/A (reserved)        ADD  with R0..R7           ;/
  SUB with R0..R7       SUBS with R0..R7           ;\subtract
  SUB SP,Imm            SUB SP,Imm  (aka ADD -Imm) ;/
  ADC/SBC/NEG/RSB/MUL   ADCS/SBCS/NEGS/RSBS/MULS   ;\
  AND/ORR/EOR/BIC/MVN   ANDS/ORRS/EORS/BICS/MVNS   ; always affects flags
  LSL/LSR/ASR/ROR       LSLS/LSRS/ASRS/RORS        ;/
```

These changes are solving compatibility issues between ARM and THUMB code.
However, in case of MOV and ADD they do bring up compatibility issues between
old and new THUMB code.



## Renamed Opcodes


```
  Pre-UAL               UAL
  LDR{cond}{xx}         LDR{xx}{cond}              ;\
  ADD{cond}{S}          ADD{S}{cond}               ; cond suffix moved to end
  xxx{cond}{xx}         xxx{xx}{cond}              ;/
  LDMIA                 LDM                        ;\amod IA can be ommited
  STMIA                 STM                        ;/
  LDRD Rd,[addr]        LDRD Rd,Rd+1,[addr]        ;\double word load/store
  STRD Rd,[addr]        STRD Rd,Rd+1,[addr]        ;/
  SWI (software irq)    SVC (supervisior)          ;-renamed SWI to SVC
```



## Alternate Opcode Names


Some opcodes had different names in classic ARM/THUMB syntax, UAL syntax allows
to use either one in both ARM and THUMB mode.

```
  THUMB-style           ARM-style
  PUSH rlist            STMFD r13!,rlist           ;\PUSH/POP
  POP rlist             LDMFD r13!,rlist           ;/
  NEG{S} Rd,Rs          RSB{S} Rd,Rs,0             ;-NEG/RSB
  LSL{S} Rd,Rn,shift    MOV{S} Rd,Rn,LSL shift     ;\
  LSR{S} Rd,Rn,shift    MOV{S} Rd,Rn,LSR shift     ;
  ASR{S} Rd,Rn,shift    MOV{S} Rd,Rn,ASR shift     ; MOV/SHIFT
  ROR{S} Rd,Rn,shift    MOV{S} Rd,Rn,ROR shift     ;
  RRX{S} Rd,Rn          MOV{S} Rd,Rn,RRX           ;/
  CMD{S} Rd,Op2         CMD{S} Rd,Rd,Op2           ;-long/short forms
```



## Further UAL changes


```
  NOP: uses new dedicated NOP opcodes (instead of MOV Rd,Rd pseudo opcodes)
  LDMIA: should omit "!" if Rn in rlist
  LDR Rd,[pc,#offset]: should be somehow written as LDR Rd,label
  Newer opcodes (for ARMv6K and up) seem to exist only in UAL syntax
```

Moreover, unrelated to UAL syntax, the 4-letter LDSB/LDSH/STSB/STSH THUMB
opcodes seem have been renamed to LDRSB/LDRSH/STRSB/STRSH at some point. And,
SUB SP,imm seems to have been added as an official THUMB alias for ADD SP,-imm.




# ARM Pseudo Instructions and Directives




## ARM Pseudo Instructions


```
  nop              mov r0,r0
  ldr Rd,=Imm      ldr Rd,[r15,disp] ;use .pool as parameter field
  add Rd,=addr     add/sub Rd,r15,disp
  adr Rd,addr      add/sub Rd,r15,disp
  adrl Rd,addr     two add/sub opcodes with disp=xx00h+00yyh
  mov Rd,Imm       mvn Rd,NOT Imm    ;or vice-versa
  and Rd,Rn,Imm    bic Rd,Rn,NOT Imm ;or vice-versa
  cmp Rd,Rn,Imm    cmn Rd,Rn,-Imm    ;or vice-versa
  add Rd,Rn,Imm    sub Rd,Rn,-Imm    ;or vice-versa
```

All above opcodes may be made conditional by specifying a {cond} field.



## THUMB Pseudo Instructions


```
  nop              mov r8,r8
  ldr Rd,=Imm      ldr Rd,[r15,disp] ;use .pool as parameter field
  add Rd,=addr     add Rd,r15,disp
  adr Rd,addr      add Rd,r15,disp
  mov Rd,Rs        add Rd,Rs,0       ;with Rd,Rs in range r0-r7 each
```



## A22i Directives


```
  org  adr     assume following code from this address on
  .gba         indicate GBA program
  .nds         indicate NDS program
  .dsi         indicate DSi program
  .firm3ds     indicate 3DS program (.firm format)
  .fix         fix GBA/NDS/DSi header checksum
  .ual         select newer ARM syntax (UAL)
  .pre_ual     select older ARM syntax (classic)
  .ereader_create_bmp      create GBA e-Reader dotcode .BMP file(s) (bitmaps)
  .ereader_create_raw      create GBA e-Reader dotcode .RAW file (useless)
  .ereader_create_bin      create GBA e-Reader dotcode .BIN file (smallest)
  .ereader_japan_plus      japanese/plus     (default is non-japanese)
  .ereader_japan_original  japanese/original (with Z80-stub for GBA-code)
  .title 'Txt' defines a title (used for e-Reader dotcodes)
  .teak        select TeakLiteII instruction set (for DSi DSP)
  .xtensa      select Xtensa instruction set (for DSi Atheros Wifi)
  .78k0        select 78K/0 instruction set  (for DSi MCU)
  .78k0r       select 78K0R/ instruction set (for 3DS MCU)
  .rl78        alias for .78k0r
  .norewrite   do not delete existing output file (keep following data in file)
  .no_auto_run do not autostart binary after assembling
  .data?       following defines RAM data structure (assembled to nowhere)
  .code        following is normal ROM code/data (assembled to ROM image)
  .include     includes specified source code file (no nesting/error handling)
  .import      imports specified binary file (optional parameters: ,begin,len)
  .radix nn    changes default numeric format (nn=2,8,10,16 = bin/oct/dec/hex)
  .errif expr  generates an error message if expression is nonzero
  .if expr     assembles following code only if expression is nonzero
  .else        invert previous .if condition
  .endif       terminate .if/.ifdef/.ifndef
  .ifdef sym   assemble following only if symbol is defined
  .ifndef sym  assemble following only if symbol is not defined
  .align nn    aligns to an address divisible-by-nn, inserts 00's
  .msg         defines a no$gba debugmessage string, such like .msg 'Init Okay'
  .brk         defines a no$gba source code break opcode
  l equ n      l=n   (symbol)
  l:   [cmd]   l=$   (global label)
  @@l: [cmd]   @@l=$ (local label, all locals are reset at next global label)
  end          end of source code
  db ...       define 8bit data (bytes)
  dw ...       define 16bit data (halfwords)
  dd ...       define 32bit data (words)
  defs nn      define nn bytes space (zero-filled)
  ;...         defines a comment (ignored by the assembler)
  //           alias for CRLF, eg. allows <db 'Text',0 // dw addr> in one line
  .rept nn     repeat nn times, terminate by .endm
  .macro name  define a macro, terminate by .endm (see notes)
  .endm        end of .rept or .macro
  .undef sym   forget label or symbol name
```



## A22i macros


The macro feature is a bit quirky and unusual: It doesn't support macros with
parameters, but one can define parameters as "param equ 1" before calling the
macro.

The downside is that the assembler will complain about "param" being already
defined when doing multiple macro calls that way. The workaround is to use
".undef param" (either inside of the macro or after the macro call).

```
  Examples:
  .macro add_something
    add r1,@@x*4+2
    .undef @@x
  .endm
  @@x=1 // add_something
  @@x=2 // add_something
  @@x=3 // add_something
  .rept 10h
    nop
  .endm
```



## A22i Alias Directives (for compatibility with other assemblers)


```
  align        .align 4          code16    .thumb
  align nn     .align nn         .code 16  .thumb
  % nn         defs nn           code32    .arm
  .space nn    defs nn           .code 32  .arm
  ..ds nn      defs nn           ltorg     .pool
  x=n          x equ n           .ltorg    .pool
  .equ x,n     x equ n           ..ltorg   .pool
  .define x n  x equ n           dcb       db (8bit data)
  incbin       .import           defb      db (8bit data)
  @@@...       ;comment          .byte     db (8bit data)
  @ ...        ;comment          .ascii    db (8bit string)
  @*...        ;comment          dcw       dw (16bit data)
  @...         ;comment          defw      dw (16bit data)
  .text        .code             .hword    dw (16bit data)
  .bss         .data?            dcd       dd (32bit data)
  .global      (ignored)         defd      dd (32bit data)
  .extern      (ignored)         .long     dd (32bit data)
  .thumb_func  (ignored)         .word     dw/dd, don't use
  #directive   .directive        .end      end
  .fill nn,1,0 defs nn
```



## Alias Conditions, Opcodes, Operands


```
  hs   cs   ;condition higher or same = carry set
  lo   cc   ;condition lower = carry cleared
  asl  lsl  ;arithmetic shift left = logical shift left
```



## A22i Numeric Formats & Dialects


```
  Type          Normal       Alias
  Decimal       85           #85  &d85
  Hexadecimal   55h          #55h  0x55  #0x55  $55  &h55
  Octal         125o         0o125  &o125
  Ascii         'U'          "U"
  Binary        01010101b    %01010101  0b01010101  &b01010101
  Roman         &rLXXXV      (very useful for arrays of kings and chapters)
```

Note: The default numeric format can be changed by the .radix directive
(usually 10=decimal). For example, with radix 16, values like "85" and "0101b"
are treated as hexadecimal numbers (in that case, decimal and binary numbers
can be still defined with prefixes &d and &b).



## A22i Numeric Operators Priority


```
  Prio  Operator           Aliases
  8     (,) brackets
  7     +,- sign
  6     *,/,MOD,SHL,SHR    MUL,DIV,<<,>>
  5     +,- operation
  4     EQ,GE,GT,LE,LT,NE  =,>=,>,<=,<,<>,==,!=
  3     NOT
  2     AND
  1     OR,XOR             EOR
```

Operators of same priority are processed from left to right.

Boolean operators (priority 4) return 1=TRUE, 0=FALSE.



## A22i Nocash Syntax


Even though A22i does recognize the official ARM syntax, it's also allowing to
use friendly code:

```
  mov   r0,0ffh         ;no C64-style "#", and no C-style "0x" required
  stmia [r7]!,r0,r4-r5  ;square [base] brackets, no fancy {rlist} brackets
  mov   r0,cpsr         ;no confusing MSR and MRS (whatever which is which)
  mov   r0,p0,0,c0,c0,0 ;no confusing MCR and MRC (whatever which is which)
  ldr   r0,[score]      ;allows to use clean brackets for relative addresses
  push  rlist           ;alias for stmfd [r13]!,rlist (and same for pop/ldmfd)
  label:                ;label definitions recommended to use ":" colons
  xor   rd,..           ;alias for eor
  not   rd,..           ;alias for mvn
```


[A22i is the no$gba debug version's built-in source code assembler.]




# ARM CP14 ICEbreaker Debug Communications Channel



The ICEbreaker aka EmbeddedICE module may be found in ARM7TDMI and possibly
also in other ARM processors. The main functionality of the module relies on
external inputs (BREAKPT signal, etc.) being controlled by external debugging
hardware. At software side, ICEbreaker contains a Debug Communications Channel
(again to access external hardware), which can be accessed as coprocessor 14
via following opcodes:

```
  MRC{cond} P14,0,Rd,C0,C0,0  ;Read Debug Comms Control Register
  MRC{cond} P14,0,Rd,C1,C0,0  ;Read Debug Comms Data Register
  MRC{cond} P14,0,Rd,C2,C0,0  ;Read Debug Comms Status Register
  MCR{cond} P14,0,Rd,C1,C0,0  ;Write Debug Comms Data Register
  MCR{cond} P14,0,Rd,C2,C0,0  ;Write Debug Comms Status Register
```

The Control register consists of Bit31-28=ICEbreaker version (0001b for
ARM7TDMI), Bit27-2=Not specified, Bit0/Bit1=Data Read/Write Status Flags.


The NDS7 and GBA allow to access CP14 (unlike as for CP0..CP13 & CP15,
access to CP14 doesn't generate any exceptions), however, the ICEbreaker module
appears to be disabled (or completely unimplemented), any reads from
P14,0,Rd,C0,C0,0 through P14,7,Rd,C15,C15,7 are simply returning the prefetched
opcode value from [$+8]. ICEbreaker might be eventually used and enabled in
Nintendo's hardware debuggers, although external breakpoints are reportedly
implemented via /FIQ input rather than via ICEbreaker hardware.

The NDS9 doesn't include a CP14 unit (or it is fully disabled), any attempts to
access it are causing invalid instruction exceptions.




# ARM CP15 System Control Coprocessor



- [ARM CP15 Overview](#armcp15overview)
- [ARM CP15 ID Codes](#armcp15idcodes)
- [ARM CP15 Control Register](#armcp15controlregister)
- [ARM CP15 Memory Managment Unit (MMU)](#armcp15memorymanagmentunitmmu)
- [ARM CP15 Protection Unit (PU)](#armcp15protectionunitpu)
- [ARM CP15 Cache Control](#armcp15cachecontrol)
- [ARM CP15 Tightly Coupled Memory (TCM)](#armcp15tightlycoupledmemorytcm)
- [ARM CP15 Misc](#armcp15misc)



# ARM CP15 Overview




## CP15


In many ARM CPUs, particulary such with memory control facilities, coprocessor
number 15 (CP15) is used as built-in System Control Coprocessor.

CPUs without memory control functions typically don't include a CP15 at all, in
that case even an attempt to read the Main ID register will cause an Undefined
Instruction exception.



## CP15 Opcodes


CP15 can be accessed via MCR and MRC opcodes, with Pn=P15, and \<cpopc>=0.

```
  MCR{cond} P15,<cpopc>,Rd,Cn,Cm,<cp>   ;move from ARM to CP15
  MRC{cond} P15,<cpopc>,Rd,Cn,Cm,<cp>   ;move from CP15 to ARM
```

Rd can be any ARM register in range R0-R14, R15 should not be used with P15.

\<cpopc>,Cn,Cm,\<cp> are used to select a CP15 register, eg.
0,C0,C0,0 = Main ID Register.

Other coprocessor opcodes (CDP, LDC, STC) cannot be used with P15.



## CP15 Register List


```
  Register       Expl.
  0,C0,C0,0      Main ID Register (R)
  0,C0,C0,1      Cache Type and Size (R)
  0,C0,C0,2      TCM Physical Size (R)
  0,C0,C0,3      ARM11: TLB Type Register
  0,C0,C1,0      ARM11: Processor Feature Register 0
  0,C0,C1,1      ARM11: Processor Feature Register 1
  0,C0,C1,2      ARM11: Debug Feature Register 0
  0,C0,C1,3      ARM11: Auxiliary Feature Register 0
  0,C0,C1,4      ARM11: Memory Model Feature Register 0
  0,C0,C1,5      ARM11: Memory Model Feature Register 1
  0,C0,C1,6      ARM11: Memory Model Feature Register 2
  0,C0,C1,7      ARM11: Memory Model Feature Register 3
  0,C0,C2,0      ARM11: Set Attributes Register 0
  0,C0,C2,1      ARM11: Set Attributes Register 1
  0,C0,C2,2      ARM11: Set Attributes Register 2
  0,C0,C2,3      ARM11: Set Attributes Register 3
  0,C0,C2,4      ARM11: Set Attributes Register 4
  0,C0,C2,5      ARM11: Set Attributes Register 5
```


```
  0,C1,C0,0      Control Register (R/W, or R=Fixed)
  0,C1,C0,1      ARM11: Auxiliary Control Register
  0,C1,C0,2      ARM11: Coprocessor Access Control Register
  0,C2,C0,0      ARM11: Translation Table Base Register 0
  0,C2,C0,1      ARM11: Translation Table Base Register 1
  0,C2,C0,2      ARM11: Translation Table Base Control Register
  0,C3,C0,0      ARM11: Domain Access Control Register
  0,C5,C0,0      ARM11: Data Fault Status Register
  0,C5,C0,1      ARM11: Instruction Fault Status Register
  0,C6,C0,0      ARM11: Fault Address Register (FAR)
  0,C6,C0,1      ARM11: Watchpoint Fault Address Register (WFAR)
  0,C2,C0,0      PU Cachability Bits for Data/Unified Protection Region
  0,C2,C0,1      PU Cachability Bits for Instruction Protection Region
  0,C3,C0,0      PU Cache Write-Bufferability Bits for Data Protection Regions
  0,C5,C0,0      PU Access Permission Data/Unified Protection Region
  0,C5,C0,1      PU Access Permission Instruction Protection Region
  0,C5,C0,2      PU Extended Access Permission Data/Unified Protection Region
  0,C5,C0,3      PU Extended Access Permission Instruction Protection Region
  0,C6,C0..C7,0  PU Protection Unit Data/Unified Region 0..7
  0,C6,C0..C7,1  PU Protection Unit Instruction Region 0..7
  0,C7,Cm,Op2    Cache Commands and Halt Function (W)
  0,C9,C0,0      Cache Data Lockdown
  0,C9,C0,1      Cache Instruction Lockdown
  0,C9,C1,0      TCM Data TCM Base and Virtual Size
  0,C9,C1,1      TCM Instruction TCM Base and Virtual Size
  0,C13,Cm,Op2   Misc Process ID registers
  0,C15,Cm,Op2   Misc Implementation Defined and Test/Debug registers
```



## Data/Unified Registers


Some Cache/PU/TCM registers are declared as "Data/Unified".

That registers are used for Data accesses in case that the CPU contains
separate Data and Instruction registers, otherwise the registers are used for
both (unified) Data and Instruction accesses.




# ARM CP15 ID Codes




## C0,C0,0 - Main ID Register (R)


```
  12-15 ARM Era (0=Pre-ARM7, 7=ARM7, other=Post-ARM7)
```

Post-ARM7 Processors

```
  0-3   Revision Number
  4-15  Primary Part Number (Bit12-15 must be other than 0 or 7)
        (eg. 946h for ARM946)
  16-19 Architecture        (1=v4, 2=v4T, 3=v5, 4=v5T, 5=v5TE, 6=v6, ?=v7)
  20-23 Variant Number
  24-31 Implementor         (41h=ARM, 44h=Digital Equipment Corp, 69h=Intel)
```

ARM7 Processors

```
  0-3   Revision Number
  4-15  Primary Part Number (Bit12-15 must be 7)
  16-22 Variant Number
  23    Architecture        (0=v3, 1=v4T)
  24-31 Implementor         (41h=ARM, 44h=Digital Equipment Corp, 69h=Intel)
```

Pre-ARM7 Processors

```
  0-3   Revision Number
  4-11  Processor ID LSBs (30h=ARM3/v2, 60h,61h,62=ARM600,610,620/v3)
  12-31 Processor ID MSBs (fixed, 41560h)
```

Note: On the NDS9, this register is 41059461h (ARMv5TE, ARM946, rev1). NDS7 and
GBA don't have CP15s.



## C0,C0,1 - Cache Type Register (R)


```
  0-11  Instruction Cache (bits 0-1=len, 2=m, 3-5=assoc, 6-8=size, 9-11=zero)
  12-23 Data Cache        (bits 0-1=len, 2=m, 3-5=assoc, 6-8=size, 9-11=zero)
  24    Separate Cache Flag (0=Unified, 1=Separate Data/Instruction Caches)
  25-28 Cache Type (0,1,2,6,7=see below, other=reserved)
         Type Method         Cache cleaning         Cache lock-down
         0    Write-through  Not needed             Not supported
         1    Write-back     Read data block        Not supported
         2    Write-back     Register 7 operations  Not supported
         6    Write-back     Register 7 operations  Format A
         7    Write-back     Register 7 operations  Format B      ;<-- NDS9
  29-31 Reserved (zero)
```

The 12bit Instruction/Data values are decoded as shown below,

```
  Cache Absent  = (ASSOC=0 and M=1)       ;in that case overriding below
  Cache Size    = 200h+(100h*M) shl SIZE  ;min 0.5Kbytes, max 96Kbytes
  Associativity = (1+(0.5*M)) shl ASSOC   ;min 1-way,     max 192-way
  Line Length   = 8 shl LEN               ;min 8 bytes,   max 64 bytes
```

For Unified cache (Bit 24=0), Instruction and Data values are identical.

Note: On the NDS9, this register is 0F0D2112h (Code=2000h bytes, Data=1000h
bytes, assoc=whatever, and line size 32 bytes each). NDS7 and GBA don't have
CP15s (nor any code/data cache).



## C0,C0,2 - Tightly Coupled Memory (TCM) Size Register (R)


```
  0-1   Reserved    (0)
  2     ITCM Absent (0=Present, 1=Absent)
  3-5   Reserved    (0)
  6-9   ITCM Size   (Size = 512 SHL N) (or 0=None)
  10-13 Reserved    (0)
  14    DTCM Absent (0=Present, 1=Absent)
  15-17 Reserved    (0)
  18-21 DTCM Size   (Size = 512 SHL N) (or 0=None)
  22-31 Reserved    (0)
```

Note: On the NDS9, this register is 00140180h (ITCM=8000h bytes, DTCM=4000h
bytes)). NDS7 and GBA don't have CP15s (nor any ITCM/DTCM).



## C0,C0,3..7 - Reserved (R)


Unused/Reserved registers, containing the same value as C0,C0,0.




# ARM CP15 Control Register




## C1,C0,0 - Control Register (R/W, or R=Fixed)


```
  0  MMU/PU Enable         (0=Disable, 1=Enable) (Fixed 0 if none)
  1  Alignment Fault Check (0=Disable, 1=Enable) (Fixed 0/1 if none/always on)
  2  Data/Unified Cache    (0=Disable, 1=Enable) (Fixed 0/1 if none/always on)
  3  Write Buffer          (0=Disable, 1=Enable) (Fixed 0/1 if none/always on)
  4  Exception Handling    (0=26bit, 1=32bit)    (Fixed 1 if always 32bit)
  5  26bit-address faults  (0=Enable, 1=Disable) (Fixed 1 if always 32bit)
  6  Abort Model (pre v4)  (0=Early, 1=Late Abort) (Fixed 1 if ARMv4 and up)
  7  Endian                (0=Little, 1=Big)     (Fixed 0/1 if fixed)
  8  System Protection bit (MMU-only)
  9  ROM Protection bit    (MMU-only)
  10 Implementation defined
  11 Branch Prediction     (0=Disable, 1=Enable)
  12 Instruction Cache     (0=Disable, 1=Enable) (ignored if Unified cache)
  13 Exception Vectors     (0=00000000h, 1=FFFF0000h)
  14 Cache Replacement     (0=Normal/PseudoRandom, 1=Predictable/RoundRobin)
  15 Pre-ARMv5 Mode        (0=Normal, 1=Pre ARMv5; LDM/LDR/POP_PC.Bit0/Thumb)
  16 DTCM Enable           (0=Disable, 1=Enable)
  17 DTCM Load Mode        (0=R/W, 1=DTCM Write-only)
  18 ITCM Enable           (0=Disable, 1=Enable)
  19 ITCM Load Mode        (0=R/W, 1=ITCM Write-only)
  20 Reserved              (0)
  21 Reserved              (0)
  22 Unaligned Access      (?=Enable unaligned access and mixed endian)
  23 Extended Page Table   (0=Subpage AP Bits Enabled, 1=Disabled)
  24 Reserved              (0)
  25 CPSR E on exceptions  (0=Clear E bit, 1=Set E bit)
  26 Reserved              (0)
  27 FIQ Behaviour         (0=Normal FIQ behaviour, 1=FIQs behave as NMFI)
  28 TEX Remap bit         (0=No remapping, 1=Remap registers used)
  29 Force AP              (0=Access Bit not used, 1=AP[0] used as Access bit)
  30 Reserved              (0)
  31 Reserved              (0)
```

Various bits in this register may be read-only (fixed 0 if unsupported, or
fixed 1 if always activated).

On NDS ARM9, bit0,2,7,12..19 are R/W, bit3..6 are always set, all other bits
are always zero.

On 3DS ARM11, bit0..2,8..9,11..13,15,22..23,25,28..29 are R/W, bit3..6,14,16,18
are always set, all other bits are always zero.




# ARM CP15 Memory Managment Unit (MMU)



Nintendo consoles have a MMU on the ARM11 processor (in 3DS).


The MMU allows to assign virtual memory addresses, and to disable the data
cache in sensitive memory areas (eg. I/O area, and memory that is shared for
ARM9/ARM11). Additionally, it can trigger page fault exceptions (eg. for error
handling or memory mapped files).



## Related CP15 registers used in 3DS bootrom MMU init


```
  p15,0,c8,c5,0 ;Invalidate Instruction TLB               (=0)
  p15,0,c8,c6,0 ;Invalidate Data TLB                      (=0)
  p15,0,c2,c0,0 ;Translation Table Base 0 (for process)   (=1FFF4000h+2)
  p15,0,c2,c0,1 ;Translation Table Base 1 (for OS and I/O)(=1FFF4000h+2)
  p15,0,c2,c0,2 ;Translation Table Base Control           (=0)
  p15,0,c3,c0,0 ;Domain Access Control                    (=55555555h)
  p15,0,c1,c0,2 ;Coprocessor Access Control (unrelated?)  (=0F00000h)
```



## MMU Tables


1st Level table (size 4000h) divides 4Gbyte address space into 1Mbyte sections

2nd Level table(s) (size 400h each) divides a 1Mbyte section into 4Kbyte pages


```
 ________________________________ ARMv6 Tables ________________________________
```



## ARMv6 First-Level Page Table entries


```
   3 3 2 2 2 2 2 2 2 2 2 2 1 1 1 1 1 1 1 1 1 1
   1_0_9_8_7_6_5_4_3_2_1_0_9_8_7_6_5_4_3_2_1_0_9_8_7_6_5_4_3_2_1_0
  |__Ignored__________________________________________________|0_0| Fault
  |__Second-Level-Table-Address_______________|P|Domain_|_SBZ_|0_1| Coarse
  |__Address______________|0|0|n_S_A|_TEX_|AP_|P|Domain_|X_C_B|1_0| Section 1MB
  |__Address______|___SBZ___|1|_SBZ_|_TEX_|AP_|P|Ignored|X_C_B|1_0| Super 16MB
  |___________________________________________________________|1_1| Reserved
```

BUG: The Supersections do probably also have "n,S,A" flags, probably in
bit17-15, too (the 3DS bootrom seems to set those bits as so).



## ARMv6 Second-Level Page Table entries


```
   3 3 2 2 2 2 2 2 2 2 2 2 1 1 1 1 1 1 1 1 1 1
   1_0_9_8_7_6_5_4_3_2_1_0_9_8_7_6_5_4_3_2_1_0_9_8_7_6_5_4_3_2_1_0
  |__Ignored__________________________________________________|0_0| Fault
  |__Address______________________|X|_TEX_|n_S_A|_SBZ_|AP_|C_B|0_1| Large 64K
  |__Address______________________________|n_S_A|_TEX_|AP_|C_B|1_X| Small 4K
```


```
 ______________________________ Pre-ARMv6 Tables ______________________________
```


This is an older format, similar to the newer ARMv6 tables, but without the
"n,S,A,X" bits, and, instead, somehow allowing to divide 4K pages into smaller
1K snippets (with separate access privileges in AP0/AP1/AP2/AP3 bits, but
without TEX bits).



## Backwards-compatible First-Level Page Table entries


```
   3 3 2 2 2 2 2 2 2 2 2 2 1 1 1 1 1 1 1 1 1 1
   1_0_9_8_7_6_5_4_3_2_1_0_9_8_7_6_5_4_3_2_1_0_9_8_7_6_5_4_3_2_1_0
  |__Ignored__________________________________________________|0_0| Fault
  |__Second-Level-Table-Address_______________|P|Domain_|_SBZ_|0_1| Coarse
  |__Address______________|0|0|_SBZ_|_TEX_|AP_|P|Domain_|0_C_B|1_0| Section 1MB
  |__Address______|___SBZ___|1|_SBZ_|_TEX_|AP_|P|Ignored|0_C_B|1_0| Super 16MB
  |___________________________________________________________|1_1| Reserved
```



## Backwards-compatible Second-Level Page Table entries


```
   3 3 2 2 2 2 2 2 2 2 2 2 1 1 1 1 1 1 1 1 1 1
   1_0_9_8_7_6_5_4_3_2_1_0_9_8_7_6_5_4_3_2_1_0_9_8_7_6_5_4_3_2_1_0
  |__Ignored__________________________________________________|0_0| Fault
  |__Address______________________|_?TEX?_|AP3|AP2|AP1|AP0|C_B|0_1| Large 4x16K
  |__Address______________________________|AP3|AP2|AP1|AP0|C_B|1_0| Small 4x1K
  |__Address______________________________|_SBZ_|_TEX_|AP_|C_B|1_1| Extended 4K
```

BUG: The 4bit ?TEX? value is probably meant to be a 3bit TEX value, probably
with an unused/zero bit; in bit15 or so.


```
 ___________________________________ Notes ___________________________________
```



## Supersections and Large Pages


16Mbyte Supersections and 64Kbyte Large pages consist of 16 identical table
entries. Which is basically same as 16 Sections or 16 Pages with continously
increasing entries.

The advantage is internal caching: If one table entry is cached, then the
hardware knows that the other 15 nearby entries are supposed to be same; and
that they won't need to be loaded into internal cache.




# ARM CP15 Protection Unit (PU)



Nintendo consoles have a PU on the ARM9 processor (in NDS, DSi, 3DS).


Protection Unit can be enabled in Bit0 of C1,C0,0 (Control Register).



## C2,C0,0 - Cachability Bits for Data/Unified Protection Region (R/W)



## C2,C0,1 - Cachability Bits for Instruction Protection Region (if any) (R/W)


```
  0-7  Cachable (C) bits for region 0-7
  8-31 Reserved/zero
```



## C3,C0,0 - Cache Write-Bufferability Bits for Data Protection Regions (R/W)


Allows to select what to do when writing to a cached memory snippet:

Write-Through stores the data in the cache line (so subsequent cache reads
return correct data), and additionally writes the data to underlaying memory.

Write-Back stores the data in the cache line only, and marks the line as dirty,
but doesn't update the underlaying memory (underlaying memory is updated only
when the CPU decides to use the cache line for other purposes, or when the user
is manually "Cleaning" the cache line).

```
  0-7  Bufferable (B) bits for region 0-7  (0=Write-Through, 1=Write-Back)
  8-31 Reserved/zero
```

Instruction fetches are, obviously, always read-operations. So, there are no
write-bufferability bits for Instruction Protection Regions.

Note: Unrelated to the "Cache Write-Bufferability", the ARM does also have a
"Write Buffer" (a small FIFO that can queue only a few writes).



## C5,C0,0 - Access Permission Data/Unified Protection Region (R/W)



## C5,C0,1 - Access Permission Instruction Protection Region (if any) (R/W)



## C5,C0,2 - Extended Access Permission Data/Unified Protection Region (R/W)



## C5,C0,3 - Extended Access Permission Instruction Protection Region (if any) (R/W)


For C5,C0,0 and C5,C0,1:

```
  0-15  Access Permission (AP) bits for region 0-7 (Bits 0-1=AP0, 2-3=AP1, etc)
  16-31 Reserved/zero
```

For C5,C0,2 and C5,C0,3 (Extended):

```
  0-31  Access Permission (AP) bits for region 0-7 (Bits 0-3=AP0, 4-7=AP1, etc)
```

The possible AP settings (0-3 for C5,C0,0..1, or 0-15 for C5,C0,2..3) are:

```
  AP  Privileged User
  0   -          -
  1   R/W        -
  2   R/W        R
  3   R/W        R/W
  5   R          -
  6   R          R
```

Settings 5,6 only for Extended Registers, settings 4,7..15 are Reserved.



## C6,C0..C7,0 - Protection Unit Data/Unified Region 0..7 (R/W)



## C6,C0..C7,1 - Protection Unit Instruction Region 0..7 (R/W) if any


```
  0     Protection Region Enable (0=Disable, 1=Enable)
  1-5   Protection Region Size   (2 SHL X) ;min=(X=11)=4KB, max=(X=31)=4GB
  6-11  Reserved/zero
  12-31 Protection Region Base address (Addr = Y*4K; must be SIZE-aligned)
```

Overlapping Regions are allowed, Region 7 is having highest priority, region 0
lowest priority.



## Background Region


Additionally, any memory areas outside of the eight Protection Regions are
handled as Background Region, this region has neither Read nor Write access.



## Unified Region Note


On the NDS, the Region registers are unified (C6,C0..C7,1 are read/write-able
mirrors of C6,C0..C7,0). Nethertheless, the Cachabilty and Permission registers
are NOT unified (separate registers exists for code and data settings).




# ARM CP15 Cache Control



Cache is enabled/controlled by Bit 2,3,12,14 in Control Register.

Cache regions are controlled via Protection Unit (PU).

Cache type can be detected via Cache Type Register.



## C7,C0..C15,0..7 - Cache Commands (W)


Write-only Cache Command Register. Cm,Op2 operands used to select a specific
command, with parameter value in Rd.

```
  Cn,Cm,Op2 Rd   ARM9 Command
  C7,C0,4   0    Yes  Wait For Interrupt (Halt)
  C7,C5,0   0    Yes  Invalidate Entire Instruction Cache
  C7,C5,1   VA   Yes  Invalidate Instruction Cache Line
  C7,C5,2   S/I  -    Invalidate Instruction Cache Line
  C7,C5,4   0    -    Flush Prefetch Buffer
  C7,C5,6   0    -    Flush Entire Branch Target Cache
  C7,C5,7   IMP? -    Flush Branch Target Cache Entry
  C7,C6,0   0    Yes  Invalidate Entire Data Cache
  C7,C6,1   VA   Yes  Invalidate Data Cache Line
  C7,C6,2   S/I  -    Invalidate Data Cache Line
  C7,C7,0   0    -    Invalidate Entire Unified Cache
  C7,C7,1   VA   -    Invalidate Unified Cache Line
  C7,C7,2   S/I  -    Invalidate Unified Cache Line
  C7,C8,2   0    Yes  Wait For Interrupt (Halt), alternately to C7,C0,4
  C7,C10,1  VA   Yes  Clean Data Cache Line
  C7,C10,2  S/I  Yes  Clean Data Cache Line
  C7,C10,4  0    -    Drain Write Buffer
  C7,C11,1  VA   -    Clean Unified Cache Line
  C7,C11,2  S/I  -    Clean Unified Cache Line
  C7,C13,1  VA   Yes  Prefetch Instruction Cache Line
  C7,C14,1  VA   Yes  Clean and Invalidate Data Cache Line
  C7,C14,2  S/I  Yes  Clean and Invalidate Data Cache Line
  C7,C15,1  VA   -    Clean and Invalidate Unified Cache Line
  C7,C15,2  S/I  -    Clean and Invalidate Unified Cache Line
```

Parameter values (Rd) formats:

```
  0    Not used, should be zero
  VA   Virtual Address
  S/I  Set/index; Bit 31..(32-A) = Index, Bit (L+S-1)..L = Set ?
```

Note:

```
  Invalidate means to forget all data
  Clean means to write-back dirty cache lines to underlaying memory
  (Clean is important when having "Cache Write-Bufferability" enabled in PU)
```



## C9,C0,0 - Data Cache Lockdown



## C9,C0,1 - Instruction Cache Lockdown


(Width (W) of index field depends on cache ASSOCIATIVETY.)

Format A:

```
  0..(31-W)  Reserved/zero
  (32-W)..31 Lockdown Block Index
```

Format B:

```
  0..(W-1)   Lockdown Block Index
  W..30      Reserved/zero
  31         L
```


Cache/Write-buffer should not be enabled for the whole 4GB memory area,
high-speed TCM memory doesn't require caching, and caching would have fatal
results on I/O ports. So, cache can be used only in combination with the
Protection Unit, which allows to enable/disable caching in specified regions.



## Note


ARMv5 instruction set supports a Cache Prepare for Load opcode (PLD), see

- [ARM Opcodes: Memory: Single Data Transfer (LDR, STR, PLD)](#armopcodesmemorysingledatatransferldrstrpld)


## Note


Data cache always requires PU/MMU. Code cache requires PU/MMU on ARM9, but also
works without PU/MMU on ARM11.




# ARM CP15 Tightly Coupled Memory (TCM)



TCM is high-speed memory, directly contained in the ARM CPU core.



## TCM and DMA


TCM doesn't use the ARM bus. A minor disadvantage is that TCM cannot be
accessed by DMA. However, the main advantage is that, when using TCM, the CPU
can be kept running without any waitstates even while the bus is used for DMA
transfers. Operation during DMA works only if all code/data is located in TCM,
waitstates are generated if any code/data outside TCM is accessed; in worst
case (if there are no gaps in the DMA) then the CPU is halted until the DMA
finishes.



## TCM and DMA and IRQ


No idea if/how IRQs are handled during DMA? Eventually (unlikely) code in TCM
is kept executed until DMA finishes (ie. until the IRQ vector can be accessed.
Eventually the IRQ vector is instantly accessed (causing to halt the CPU until
DMA finishes). In both cases: Assuming that IRQs are enabled, and that the IRQ
vector and/or IRQ handler are located outside TCM.



## Separate Instruction (ITCM) and Data (DTCM) Memory


DTCM can be used only for Data accesses, typically used for stacks and other
frequently accessed data.

ITCM is primarily intended for instruction accesses, but it can be also used
for Data accesses (among others allowing to copy code to ITCM), however,
performance isn't optimal when simultaneously accessing ITCM for code and data
(such like opcodes in ITCM that use literal pool values in ITCM).



## TCM Enable, TCM Load Mode


CP15 Control Register allows to enable ITCM and DTCM, and to switch ITCM/DTCM
into Load Mode. In Load Mode (when TCM is enabled), TCM becomes write-only;
this allows to read data from source addresses in main memory, and to write
data to destination addresses in TCM by using the same addresses; useful for
initializing TCM with overlapping source/dest addresses; Load mode works with
all Load/Store opcodes, it does NOT work with SWP/SWPB opcodes.


TCM Physical Size can be detected in 3rd ID Code Register. (C0,C0,2)



## C9,C1,0 - Data TCM Size/Base (R/W)



## C9,C1,1 - Instruction TCM Size/Base (R/W)


```
  0     Reserved     (0)
  1-5   Virtual Size (Size = 512 SHL N) ;min=(N=3)=4KB, max=(N=23)=4GB
  6-11  Reserved     (0)
  12-31 Region Base  (Base = X SHL 12)  ;Base must be Size-aligned
```

The Virtual size settings should be normally same as the Physical sizes (see
C0,C0,2). However, smaller sizes are allowed (using only the 1st some KB), as
well as bigger sizes (TCM area is then filled with mirrors of physical TCM).

The ITCM region base may be fixed (read-only), for example, on the NDS, ITCM
base is always 00000000h, nethertheless the virtual size may be changed
(allowing to mirror ITCM to higher addresses).

If DTCM and ITCM do overlap, then ITCM appears to have priority.



## TCM and PU


TCM can be used without Protection Unit.

When the protection unit is enabled, TCM is controlled by the PU just like
normal memory, the PU should provide R/W Access Permission for TCM regions;
cache and write-buffer are not required for high-speed TCM (so both should be
disabled for TCM regions).




# ARM CP15 Misc




## C13,C0,0 - Process ID for Fast Context Switch Extension (FCSE) (R/W)


```
  0-24  Reserved/zero
  25-31 Process ID (PID) (0-127) (0=Disable)
```

The FCSE allows different processes (each assembled with ORG 0) to be located
at virtual addresses in the 1st 32MB area. The FCSE splits the total 4GB
address space into blocks of 32MB, accesses to Block(0) are redirected to
Block(PID):

```
  IF addr<32M then addr=addr+PID*32M
  Respectively, with PID=0, the address remains unchanged (FCSE disabled).
```

The CPU-to-Memory address handling is shown below:

```
  1. CPU outputs a virtual address (VA)
  2. FCSE adjusts the VA to a modified virtual address (MVA)
  3. Cache hits determined by examining the MVA, continue below if no hit
  4. MMU translates MVA to physical address (PA) (if no MMU present: PA=MVA)
  5. Memory access occurs at PA
```

The FCSE allows limited virtual addressing even if no MMU is present.

If the MMU is present, then either the FCSE and/or the MMU can be used for
virtual addressing; the advantage of using the FCSE (a single write to
C13,C0,0) is less overload; using the MMU for the same purpose would require to
change virtual address translation table in memory, and to flush the cache.

The NDS doesn't have a FCSE (the FCSE register is read-only, always zero).



## C13,C0,1 - Trace Process ID (R/W)



## C13,C1,1 - Trace Process ID (Mirror) (R/W)


This value is output to ETMPROCID pins (if any), allowing to notify external
hardware about the currently executed process within multi-tasking programs.

```
  0-31  Process ID
```

C13,C1,1 is a mirror of C13,C0,1 (for compatibility with other ARM processors).

Both registers are read/write-able on NDS9, but there are no external pin-outs.



## \<cpopc>


Unlike for all other CP15 registers, the \<cpopc> operand of the MRC/MCR
opcodes isn't always zero for below registers, so below registers are using
"cpopc,Cn,Cm,op2" notation (instead of the normal "Cn,Cm,op2" notation).



## Built-In-Self-Test (BIST)


Allows to test internal memory (ie. TCM, Cache Memory, and Cache TAGs). The
tests are filling (and verifying) the selected memory region thrice (once with
the fillvalue, then with the inverted fillvalue, and then again with the
fillvalue). The BIST functions are intended for diagnostics purposes only, not
for use in normal program code (ARM doesn't guarantee future processors to have
backwards compatible BIST functions).



## 0,C15,C0,1 - BIST TAG Control Register (R/W)



## 1,C15,C0,1 - BIST TCM Control Register (R/W)



## 2,C15,C0,1 - BIST Cache Control Register (R/W)


```
  0-15  Data Control (see below)
  16-31 Instruction Control (see below)
```

The above 16bit control values are:

```
  0     Start bit     (Write: 1=Start) (Read: 1=Busy)
  1     Pause bit     (1=Pause)
  2     Enable bit    (1=Enable)
  3     Fail Flag     (1=Error) (Read Only)
  4     Complete Flag (1=Ready) (Read Only)
  5-15  Size (2^(N+2) bytes) (min=N=1=8bytes, max=N=24=64MB)
```

Size and Pause are not supported in all implementations.

Caution: While and as long as the Enable bit is set, the corresponding memory
region(s) will be disabled. Eg. when testing \<either> DTCM \<and/or>
ITCM, \<both> DTCM \<and> ITCM are forcefully disabled in C1,C0,0
(Control Register), after the test the software must first clear the BIST
enable bit, and then restore DTCM/ITCM bits in C1,C0,0. And of course, the
content of the tested memory region must be restored when needed.



## 0,C15,C0,2 - BIST Instruction TAG Address (R/W)



## 1,C15,C0,2 - BIST Instruction TCM Address (R/W)



## 2,C15,C0,2 - BIST Instruction Cache Address (R/W)



## 0,C15,C0,6 - BIST Data TAG Address (R/W)



## 1,C15,C0,6 - BIST Data TCM Address (R/W)



## 2,C15,C0,6 - BIST Data Cache Address (R/W)


```
  0-31  Word-aligned Destination Address within Memory Block (eg. within ITCM)
```

On the NDS9, bit0-1, and bit21-31 are always zero.



## 0,C15,C0,3 - BIST Instruction TAG Fillvalue (R/W)



## 1,C15,C0,3 - BIST Instruction TCM Fillvalue (R/W)



## 2,C15,C0,3 - BIST Instruction Cache Fillvalue (R/W)



## 0,C15,C0,7 - BIST Data TAG Fillvalue (R/W)



## 1,C15,C0,7 - BIST Data TCM Fillvalue (R/W)



## 2,C15,C0,7 - BIST Data Cache Fillvalue (R/W)


```
  0-31  Fillvalue for BIST
```

After BIST, the selected memory region is filled by that value. That is, on the
NDS9 at least, all words will be filled with the SAME value (ie. NOT with
increasing or randomly generated numbers).



## 0,C15,C0,0 - Cache Debug Test State Register (R/W)


```
  0-8    Reserved (zero)
  9      Disable Instruction Cache Linefill
  10     Disable Data Cache Linefill
  11     Disable Instruction Cache Streaming
  12     Disable Data Cache Streaming
  13-31  Reserved (zero/unpredictable)
```



## 3,C15,C0,0 - Cache Debug Index Register (R/W)


```
  0..1    Reserved (zero)
  2..4    Word Address
  5..N    Index
  N+1..29 Reserved (zero)
  30..31  Segment
```



## 3,C15,C1,0 - Cache Debug Instruction TAG (R/W)



## 3,C15,C2,0 - Cache Debug Data TAG (R/W)



## 3,C15,C3,0 - Cache Debug Instruction Cache (R/W)



## 3,C15,C4,0 - Cache Debug Data Cache (R/W)


```
  0..1    Set
  2..3    Dirty Bits
  4       Valid
  5..N    Index
  N+1..31 TAG Address
```




# ARM CPU Instruction Cycle Times



Instruction Cycle Summary


```
  Instruction      Cycles      Additional
  ---------------------------------------------------------------------
  ALU              1S          +1S+1N if R15 loaded, +1I if SHIFT(Rs)
  MSR,MRS          1S
  LDR              1S+1N+1I    +1S+1N if R15 loaded
  STR              2N
  LDM              nS+1N+1I    +1S+1N if R15 loaded
  STM              (n-1)S+2N
  SWP              1S+2N+1I
  BL (THUMB)       3S+1N
  B,BL             2S+1N
  SWI,trap         2S+1N
  MUL              1S+ml
  MLA              1S+(m+1)I
  MULL             1S+(m+1)I
  MLAL             1S+(m+2)I
  CDP              1S+bI
  LDC,STC          (n-1)S+2N+bI
  MCR              1N+bI+1C
  MRC              1S+(b+1)I+1C
  {cond} false     1S
```



ARM9:

```
  Q{D}ADD/SUB      1S+Interlock.
  CLZ              1S.
  LDR              1S+1N+1L
  LDRB,LDRH,LDRmis 1S+1N+2L
  LDR PC ...
  STR              1S+1N        (not 2N, and both in parallel)
```

Execution Time: 1S+Interlock    (SMULxy,SMLAxy,SMULWx,SMLAWx)

Execution Time: 1S+1I+Interlock (SMLALxy)


ARM11:

```
  Observe that Branch Prediction (enabled in CP15 Control register) can affect
  timings for conditional jumps (and presumably non-conditional ones, too).
  Without prediction: A waitloop made of "SUBS+BNE" takes 4 clks per loop cycle
  With prediction: A waitloop made of "SUBS+BNE" takes 2.5 clks per loop cycle
  (apparently the prediction assumes 75% of the jumps to be taken)
```


Whereas,

```
  n = number of words transferred
  b = number of cycles spent in coprocessor busy-wait loop
  m = depends on most significant byte(s) of multiplier operand
```

Above 'trap' is meant to be the execution time for exceptions. And '{cond}
false' is meant to be the execution time for conditional instructions which
haven't been actually executed because the condition has been false.


The separate meaning of the N,S,I,C cycles is:



## N - Non-sequential cycle


Requests a transfer to/from an address which is NOT related to the address used
in the previous cycle. (Called 1st Access in GBA language).

The execution time for 1N is 1 clock cycle (plus non-sequential access
waitstates).



## S - Sequential cycle


Requests a transfer to/from an address which is located directly after the
address used in the previous cycle. Ie. for 16bit or 32bit accesses at
incrementing addresses, the first access is Non-sequential, the following
accesses are sequential. (Called 2nd Access in GBA language).

The execution time for 1S is 1 clock cycle (plus sequential access waitstates).



## I - Internal Cycle


CPU is just too busy, not even requesting a memory transfer for now.

The execution time for 1I is 1 clock cycle (without any waitstates).



## C - Coprocessor Cycle


The CPU uses the data bus to communicate with the coprocessor (if any), but no
memory transfers are requested.



## Memory Waitstates


Ideally, memory may be accessed free of waitstates (1N and 1S are then equal to
1 clock cycle each). However, a memory system may generate waitstates for
several reasons: The memory may be just too slow. Memory is currently accessed
by DMA, eg. sound, video, memory transfers, etc. Or when data is squeezed
through a 16bit data bus (in that special case, 32bit access may have more
waitstates than 8bit and 16bit accesses). Also, the memory system may separate
between S and N cycles (if so, S cycles would be typically faster than N
cycles).



## Memory Waitstates for Different Memory Areas


Different memory areas (eg. ROM and RAM) may have different waitstates. When
executing code in one area which accesses data in another area, then the S+N
cycles must be split into code and data accesses: 1N is used for data access,
plus (n-1)S for LDM/STM, the remaining S+N are code access. If an instruction
jumps to a different memory area, then all code cycles for that opcode are
having waitstate characteristics of the NEW memory area (except Thumb BL which
still executes 1S in OLD area).




# ARM CPU Versions




## Version Numbers


ARM CPUs are distributed by name ARM#, and are described as ARMv# in
specifications, whereas "#" is NOT the same than "v#", for example, ARM7TDMI is
ARMv4TM. That is so confusing, that ARM didn't even attempt to clarify the
relationship between the various "#" and "v#" values.



## Version Variants


Suffixes like "M" (long multiply), "T" (Thumb support), "E" (Enhanced DSP)
indicate presence of special features, additionally to the standard instruction
set of a given version, or, when preceded by an "x", indicate the absence of
that features.



## ARMv1 aka ARM1


Some sort of a beta version, according to ARM never been used in any commercial
products.



## ARMv2 and up


MUL,MLA

CDP,LDC,MCR,MRC,STC

SWP/SWPB (ARMv2a and up only)

Two new FIQ registers



## ARMv3 and up


MRS,MSR opcodes (instead CMP/CMN/TST/TEQ{P} opcodes)

CPSR,SPSR registers (instead PSR bits in R15)

Removed never condition, cond=NV no longer valid

32bit addressing (instead 26bit addressing in older versions)

26bit addressing backwards comptibility mode (except v3G)

Abt and Und modes (instead handling aborts/undefined in Svc mode)

SMLAL,SMULL,UMLAL,UMULL (optionally, INCLUDED in v3M, EXCLUDED in v4xM/v5xM)



## ARMv4 aka ARM7 and up


LDRH,LDRSB,LDRSH,STRH

Sys mode (privileged user mode)

BX (only ARMv4T, and any ARMv5 or ARMv5T and up)

THUMB code (only T variants, ie. ARMv4T, ARMv5T)



## ARMv5 aka ARM9 and up


BKPT,BLX,CLZ (BKPT,BLX also in THUMB mode)

LDM/LDR/POP PC with mode switch (POP PC also in THUMB mode)

CDP2,LDC2,MCR2,MRC2,STC2 (new coprocessor opcodes)

C-flag unchanged by MUL (instead undefined flag value)

changed instruction cycle timings / interlock ??? or not ???

QADD,QDADD,QDSUB,QSUB opcodes, CPSR.Q flag (v5TE and V5TExP only)

SMLAxy,SMLALxy,SMLAWy,SMULxy,SMULWy (v5TE and V5TExP only)

LDRD,STRD,PLD,MCRR,MRRC (v5TE only, not v5, not v5TExP)

BXJ (jump to Jazelle bytecode) (v5TEJ only)



## ARMv6 aka ARM11 and up (see ARM DDI 0100I)


Supports all ARMv5TEJ features (=including Jazelle?).

The following ARM instructions are added:

- CPS, SRS and RFE instructions for improved exception handling

- REV, REV16 and REVSH byte reversal instructions

- SETEND for a revised endian (memory) model

- LDREX and STREX exclusive access instructions

- SXTB, SXTH, UXTB, UXTH byte/halfword extend instructions

- A set of Single Instruction Multiple Data (SIMD) media instructions

- Additional forms of multiply with accumulation into a 64-bit result

The following Thumb instructions are added:

- CPS, CPY (a form of MOV), REV, REV16, REVSH, SETEND, SXTB, SXTH, UXTB, UXTH

SWP/SWPB has been deprecated in ARMv6, made optional in ARMv7 (with the
possibility of disabling it if still available), and removed in ARMv8.



## ARMv6K aka "ARM11 MPCore" (see ARM DDI 0360F) (used in 3DS)


Unknown how this is abbreviated (ARMv6-M would be something else: Cortex-M).

The MPCore processor provides support for extensions to ARMv6 that include:

- LDREX/STREX{B|H|D} for 8bit/16bit/64bit and CLREX

- HINT (TrueNOP, YIELD, WFI, WFE, SEV)

- Architectural remap registers.

- Revised use of TEX remap bits. The ARMv6 MMU page table descriptors use a
large number of bits to describe all of the options for inner and outer
cachability. In reality, no application requires all of these options
simultaneously. Therefore it is possible to use the TEX remap mechanism to
configure the MP11 CPUs to support only a small number of options. This implies
a level of indirection in the page table mappings.

The TEX CB encoding table provides two OS managed page table bits. For binary
compatibility with existing ARMv6 ports of OSs, this gives a separate mode of
operation of the MMU. This is called the TEX Remap configuration and is
controlled by bit [28] TR in CP15 Register 1.

- Revised use of AP bits. In the MP11 CPUs the APX and AP[1:0] encoding b111 is
Privileged or User mode read-only access. AP[0] indicates an abort type, Access
Bit fault, when CP15 c1[29] is 1.

For more information see the ARM Architecture Reference Manual.



## ARMv6T2 aka THUMB-2


This doesn't seem to be supported in 3DS. THUMB-2 adds more 2x16bit opcodes in
THUMB mode, ie. THUMB code can contain classic 16bit opcodes, mixed with new
2x16bit opcodes. As far as I understand, the old 2x16bit "BL" and "BLX" do no
longer exists, or are replaced by differently encode THUMB-2 opcodes?



## ARMv6Z


ARMv6K with Security Extensions. Aka TrustZone, see Processor Feature Register
1.



## A Milestone in Computer History


Original ARMv2 has been used in the relative rare and expensive Archimedes
deluxe home computers in the late eighties, the Archimedes has caught a lot of
attention, particularly for being the first home computer that used a BIOS
being programmed in BASIC language - which has been a absolutely revolutionary
decadency at that time.

Inspired, programmers all over the world have successfully developed even
slower and much more inefficient programming languages, which are nowadays
consequently used by nearly all ARM programmers, and by most non-ARM
programmers as well.




# ARM CPU Data Sheet



This present document is an attempt to supply a brief ARM7TDMI reference,
hopefully including all information which is relevant for programmers.


Some details that I have treated as meaningless for GBA programming aren't
included - such like Big Endian format, and Virtual Memory data aborts, and
most of the chapters listed below.


Have a look at the complete data sheet (URL see below) for more detailed
verbose information about ARM7TDMI instructions. That document also includes:

- - Signal Description
    - Pins of the original CPU, probably other for GBA.
- - Memory Interface
    - Optional virtual memory circuits, etc. not for GBA.
- - Coprocessor Interface
    - As far as I know, none such in GBA.
- - Debug Interface
    - For external hardware-based debugging.
- - ICEBreaker Module
    - For external hardware-based debugging also.
- - Instruction Cycle Operations
    - Detailed: What happens during each cycle of each instruction.
- - DC Parameters (Power supply)
- - AC Parameters (Signal timings)

The official ARM7TDMI data sheet can be downloaded from ARMs webpage,

- [http://www.arm.com/Documentation/UserMans/PDF/ARM7TDMI.html](http://www.arm.com/Documentation/UserMans/PDF/ARM7TDMI.html)

Be prepared for bloated PDF Format, approx 1.3 MB, about 200 pages.
