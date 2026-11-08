"""THUMB 16-bit 指令集解碼與執行（ARM7TDMI）。

由 ``gba_cpu/thumb.py`` 遷移而來；對 ``cpu`` 的介面契約與 :mod:`gbaemu.cpu.arm`
相同。

# GBATEK: ARM 16bit Instruction Set (THUMB Code)
"""

from . import conditions
from .arm import _undefined


# ═══════════════════════════════════════════════════════════════
#  Thumb 指令集（GBA ARM7TDMI）—— 全部家族已實作
#
#  結構：execute() 只負責「分派」，每個家族一個小函式。
#
#  家族索引（照 op 排序）：
#    F000~F7FF  BL                 DF00~DFFF  SWI
#    4400~47FF  高位暫存器          B000~B0FF  ADD/SUB sp
#    000xx      移位 imm5          00011      ADD/SUB（兩形式）
#    00100      MOV imm8          0010x      CMP/ADD/SUB imm8
#    01000      16 種 ALU         01001      LDR pc-rel
#    0101x      LDR/STR 暫存器偏移 011xx      LDR/STR 立即偏移
#    1000x      STRH/LDRH         1001x      LDR/STR sp-rel
#    1010x      ADD pc/sp         1011x      PUSH/POP
#    1100x      STMIA/LDMIA       1101x      條件分支
#    11100      B                 11101      未定義（真機亦如此）
#
#  三條鐵則：
#   1. 暫存器永遠存 0~0xFFFFFFFF 的無符號值（負數會弄壞 CMP 的 C 旗標！）
#   2. Thumb 的 pc 相對運算一律用 (pc + 4) & 0xFFFFFFFC
#   3. 每個處理函式自己負責更新 pc
# ═══════════════════════════════════════════════════════════════


# ── 旗標小工具 ──────────────────────────────────────────────

def _nz(cpu, result):
    """依 32-bit 結果更新 N / Z（直接改 CPSR，省兩次 set_flag 呼叫）"""
    cpsr = cpu.regs.cpsr & 0x3FFFFFFF
    if result & 0x80000000:
        cpsr |= 0x80000000
    if not result:
        cpsr |= 0x40000000
    cpu.regs.cpsr = cpsr


def _sub_flags(cpu, a, b):
    """CMP 用：a - b 的 N/Z/C/V（C = 無借位，a/b 須為無符號）"""
    result = (a - b) & 0xFFFFFFFF
    cpsr = cpu.regs.cpsr & 0x0FFFFFFF
    if result & 0x80000000:
        cpsr |= 0x80000000
    if not result:
        cpsr |= 0x40000000
    if a >= b:
        cpsr |= 0x20000000
    if ((a ^ b) & (a ^ result)) & 0x80000000:
        cpsr |= 0x10000000
    cpu.regs.cpsr = cpsr

def _add_flags(cpu, a, b):
    """ADD 用：a + b 的 N/Z/C/V（a/b 須為無符號）"""
    s = a + b
    result = s & 0xFFFFFFFF
    cpsr = cpu.regs.cpsr & 0x0FFFFFFF
    if result & 0x80000000:
        cpsr |= 0x80000000
    if not result:
        cpsr |= 0x40000000
    if s > 0xFFFFFFFF:
        cpsr |= 0x20000000
    if ((a ^ result) & ~(a ^ b)) & 0x80000000:
        cpsr |= 0x10000000
    cpu.regs.cpsr = cpsr

def _cv_from_unbounded(cpu, s, is_sub, a, b, result):
    """ADC/SBC/CMP/CMN 用：s = 未截斷結果；V 用 signed overflow 公式。"""
    if is_sub:
        cpu.regs.set_flag(29, 1 if s >= 0 else 0)                    # C：無借位
        overflow = (a ^ b) & (a ^ result)
    else:
        cpu.regs.set_flag(29, 1 if s > 0xFFFFFFFF else 0)            # C：進位
        overflow = (a ^ result) & (b ^ result)
    cpu.regs.set_flag(28, 1 if overflow & 0x80000000 else 0)          # V


# ── 特殊編碼 ────────────────────────────────────────────────

def _bl(cpu, instr):
    """BL：22-bit 欄位 S:imm10:imm11 有號擴展後 ×2（ARM ARM A4.1.4）

    上半：F000 型式（S=bit10 + imm10）；下半：imm11（bits 10-0）
    offset = SignExtend22(S:imm10:imm11) << 1
    """
    second = cpu.bus.read16(cpu.regs.pc + 2)          # 下半部
    offset = ((instr & 0x7FF) << 12) | ((second & 0x7FF) << 1)
    if offset & 0x400000:
        offset -= 0x800000
    cpu.regs.lr = (cpu.regs.pc + 4) | 1               # bit0=1 表示返回 Thumb
    cpu.regs.pc = (cpu.regs.pc + 4 + offset) & 0xFFFFFFFE


def _bl2(cpu, instr):
    """BL 下半部被「獨立執行」（BIOS 劈開指令技巧）：PC = LR + off，LR = PC+3"""
    off = (instr & 0x7FF) << 1
    new_pc = (cpu.regs.lr + off) & 0xFFFFFFFF
    cpu.regs.lr = cpu.regs.pc + 3                     # 指向下一半字 | bit0
    cpu.regs.pc = new_pc & 0xFFFFFFFE


def _hi_reg(cpu, instr):
    """44xx/46xx/47xx：ADD / CMP / MOV / BX 高位暫存器"""
    op2 = (instr >> 8) & 0x3
    # pc 當來源：讀「指令位址 + 4」且 bit0 清 0（GBATEK）
    pcread = (cpu.regs.pc + 4) & 0xFFFFFFFE

    if op2 == 0b11:                                # BX：Rm = bits 6-3（4 bit）
        rm = (instr >> 3) & 0xF
        target = pcread if rm == 15 else cpu.regs.r[rm]
        if target & 1:                             # 先定 T，pc setter 依新狀態對齊
            cpu.regs.cpsr |= 0x20
        else:
            cpu.regs.cpsr &= ~0x20
        cpu.regs.pc = target
        return

    # 注意：bit7 延伸「目的」(Rd)、bit6 延伸「來源」(Rs)（mGBA 驗證）
    rd = (((instr >> 7) & 1) << 3) | (instr & 0x7)          # H1(bit7):Rd(3)
    rs = (((instr >> 6) & 1) << 3) | ((instr >> 3) & 0x7)   # H2(bit6):Rs(3)

    if op2 == 0b00:                                # ADD Rd, Rs
        a = pcread if rd == 15 else cpu.regs.r[rd]
        b = pcread if rs == 15 else cpu.regs.r[rs]
        if rd == 15:
            cpu.regs.pc = (a + b) & 0xFFFFFFFE
            return
        cpu.regs.r[rd] = (a + b) & 0xFFFFFFFF
    elif op2 == 0b01:                              # CMP Rd, Rs
        a = pcread if rd == 15 else cpu.regs.r[rd]
        b = pcread if rs == 15 else cpu.regs.r[rs]
        _sub_flags(cpu, a, b)
    else:                                          # MOV Rd, Rs
        if rd == 15:
            cpu.regs.pc = (pcread if rs == 15 else cpu.regs.r[rs]) & 0xFFFFFFFE
            return
        cpu.regs.r[rd] = pcread if rs == 15 else cpu.regs.r[rs]
    cpu.regs.pc += 2


def _add_sub_sp(cpu, instr):
    """B0xx：ADD/SUB SP, #imm7*4（32-bit wrap，真機語義）"""
    amount = (instr & 0x7F) << 2
    if (instr >> 7) & 1:
        cpu.regs.sp = (cpu.regs.sp - amount) & 0xFFFFFFFF
    else:
        cpu.regs.sp = (cpu.regs.sp + amount) & 0xFFFFFFFF
    cpu.regs.pc += 2


# ── 運算類 ──────────────────────────────────────────────────

def _shift_imm(cpu, instr):
    """00000~00010：LSL / LSR / ASR 立即數移位（00011 是別人家族！）"""
    op2  = (instr >> 11) & 0x3                     # bits 12-11
    imm5 = (instr >> 6) & 0x1F
    rm   = (instr >> 3) & 0x7
    rd   = instr & 0x7
    value = cpu.regs.r[rm]

    if op2 == 0b00:                                # LSL（#0 就是 #0，C 不變）
        if imm5:
            result, carry = (value << imm5) & 0xFFFFFFFF, (value >> (32 - imm5)) & 1
        else:
            result, carry = value, None
    elif op2 == 0b01:                              # LSR（#0 = #32）
        amt = imm5 if imm5 else 32
        result, carry = (value & 0xFFFFFFFF) >> amt, (value >> (amt - 1)) & 1
    else:                                          # ASR（#0 = #32）
        amt = imm5 if imm5 else 32
        sgn = value if value < 0x80000000 else value - 0x100000000
        result, carry = (sgn >> amt) & 0xFFFFFFFF, (value >> (amt - 1)) & 1

    cpu.regs.r[rd] = result
    _nz(cpu, result)
    if carry is not None:
        cpu.regs.set_flag(29, carry)
    cpu.regs.pc += 2


def _add_sub(cpu, instr):
    """00011：ADD/SUB（兩種形式都會設 NZCV！）"""
    if (instr >> 10) & 1 == 0:                     # 三暫存器形式
        rm, rs = (instr >> 6) & 7, (instr >> 3) & 7
        a, b = cpu.regs.r[rs], cpu.regs.r[rm]
    else:                                          # 立即數形式（Rs 在 bits5-3，Rd 在 bits2-0）
        imm, rn = (instr >> 6) & 7, (instr >> 3) & 7
        a, b = cpu.regs.r[rn], imm
    rd = instr & 7
    if (instr >> 9) & 1:                           # SUB
        cpu.regs.r[rd] = (a - b) & 0xFFFFFFFF
        _sub_flags(cpu, a, b)
    else:                                          # ADD
        cpu.regs.r[rd] = (a + b) & 0xFFFFFFFF
        _add_flags(cpu, a, b)
    cpu.regs.pc += 2


def _mov_imm(cpu, instr):
    """00100：MOV Rd, #imm8——Thumb 一定更新 N/Z（= MOVS；唔碰 C/V）

    （jsmolka thumb.gba t1「Zero flag」：mov r0, 0 之後 Z 必定 = 1）
    """
    v = instr & 0xFF
    cpu.regs.r[(instr >> 8) & 7] = v
    _nz(cpu, v)
    cpu.regs.pc += 2


def _cmp_add_sub_imm(cpu, instr):
    """00101/00110/00111：CMP / ADD / SUB 立即數（三種都設旗標！）"""
    op  = (instr >> 11) & 0x1F
    rd  = (instr >> 8) & 0x7
    imm = instr & 0xFF
    a   = cpu.regs.r[rd]
    if op == 0b00101:                              # CMP：只設旗標
        _sub_flags(cpu, a, imm)
    elif op == 0b00110:                            # ADD：也設旗標
        cpu.regs.r[rd] = (a + imm) & 0xFFFFFFFF
        _add_flags(cpu, a, imm)
    else:                                          # SUB：也設旗標
        cpu.regs.r[rd] = (a - imm) & 0xFFFFFFFF
        _sub_flags(cpu, a, imm)
    cpu.regs.pc += 2


def _alu(cpu, instr):
    """01000：16 種暫存器間運算（bits 9-6 選擇）"""
    op2 = (instr >> 6) & 0xF
    rm  = (instr >> 3) & 0x7
    rd  = instr & 0x7
    a, b = cpu.regs.r[rd], cpu.regs.r[rm]
    c = (cpu.regs.cpsr >> 29) & 1                   # 目前的 C 旗標

    # 移位（暫存器版）：位移量在 b（原始量取 8 bit）
    if op2 in (0b0010, 0b0011, 0b0100, 0b0111):
        raw = b & 0xFF
        if raw == 0:                               # 位移量 0 → 不變、C 不變
            result, carry = a, None
        elif op2 == 0b0010:                        # LSL
            if raw < 32:   result, carry = (a << raw) & 0xFFFFFFFF, (a >> (32 - raw)) & 1
            elif raw == 32: result, carry = 0, a & 1
            else:          result, carry = 0, 0
        elif op2 == 0b0011:                        # LSR
            if raw < 32:   result, carry = (a & 0xFFFFFFFF) >> raw, (a >> (raw - 1)) & 1
            elif raw == 32: result, carry = 0, (a >> 31) & 1
            else:          result, carry = 0, 0
        elif op2 == 0b0100:                        # ASR
            sgn = a if a < 0x80000000 else a - 0x100000000
            if raw < 32:   result, carry = (sgn >> raw) & 0xFFFFFFFF, (a >> (raw - 1)) & 1
            else:          result, carry = (0 if sgn >= 0 else 0xFFFFFFFF), (a >> 31) & 1
        else:                                      # ROR
            amt = raw & 0x1F
            if amt == 0:                           # 32 的倍數：值不變，C = bit31
                result, carry = a, (a >> 31) & 1
            else:
                result = ((a >> amt) | (a << (32 - amt))) & 0xFFFFFFFF
                carry = (a >> (amt - 1)) & 1
        cpu.regs.r[rd] = result
        _nz(cpu, result)
        if carry is not None:
            cpu.regs.set_flag(29, carry)
        cpu.regs.pc += 2
        return

    # TST：AND 但不寫回
    if op2 == 0b1000:
        _nz(cpu, a & b)
        cpu.regs.pc += 2
        return

    # CMP / CMN：不寫回
    if op2 in (0b1010, 0b1011):
        s = (a - b) if op2 == 0b1010 else (a + b)
        result = s & 0xFFFFFFFF
        _nz(cpu, result)
        _cv_from_unbounded(cpu, s, op2 == 0b1010, a, b, result)
        cpu.regs.pc += 2
        return

    # 加減 / 邏輯
    if op2 == 0b1001:                              # NEG（V 的規則特殊，單獨算）
        s = -b
        cpu.regs.set_flag(29, 1 if b == 0 else 0)      # ✅ C = 無借位（b=0 才有）
        cpu.regs.set_flag(28, 1 if b == 0x80000000 else 0)
        result = s & 0xFFFFFFFF
    elif op2 == 0b0101:                            # ADC
        s = a + b + c
        _cv_from_unbounded(cpu, s, False, a, b, s & 0xFFFFFFFF)
        result = s & 0xFFFFFFFF
    elif op2 == 0b0110:                            # SBC
        s = a - b - (1 - c)
        _cv_from_unbounded(cpu, s, True, a, b, s & 0xFFFFFFFF)
        result = s & 0xFFFFFFFF
    elif op2 == 0b1101:                            # MUL（只設 N/Z）
        result = (a * b) & 0xFFFFFFFF
        cpu.regs.r[rd] = result
        _nz(cpu, result)
        cpu.regs.pc += 2
        return
    elif op2 == 0b0000:  result = (a & b) & 0xFFFFFFFF      # AND
    elif op2 == 0b0001:  result = a ^ b                    # EOR
    elif op2 == 0b1100:  result = (a | b) & 0xFFFFFFFF    # ORR
    elif op2 == 0b1110:  result = a & (~b & 0xFFFFFFFF)    # BIC
    else:                result = ~b & 0xFFFFFFFF          # MVN

    cpu.regs.r[rd] = result
    _nz(cpu, result)
    cpu.regs.pc += 2


# ── 存取類 ──────────────────────────────────────────────────

def _ldr_pc(cpu, instr):
    """01001：LDR Rd, [pc, #imm8*4]（讀常數池）"""
    rd = (instr >> 8) & 0x7
    addr = (((cpu.regs.pc + 4) & 0xFFFFFFFC) + (instr & 0xFF) * 4) & 0xFFFFFFFF
    cpu.regs.r[rd] = cpu.bus.read32(addr)
    cpu.regs.pc += 2


def _ldr_str_reg(cpu, instr):
    """0101x：LDR/STR 暫存器偏移（bits 11-9 是 3-bit 選擇器，沒有獨立 L bit！）"""
    op3 = (instr >> 9) & 0x7
    ro  = (instr >> 6) & 0x7
    rb  = (instr >> 3) & 0x7
    rd  = instr & 0x7
    addr = (cpu.regs.r[rb] + cpu.regs.r[ro]) & 0xFFFFFFFF

    if op3 == 0b000:      cpu.bus.write32(addr, cpu.regs.r[rd])           # STR
    elif op3 == 0b001:    cpu.bus.write16(addr, cpu.regs.r[rd] & 0xFFFF)  # STRH
    elif op3 == 0b010:    cpu.bus.write8(addr, cpu.regs.r[rd] & 0xFF)     # STRB
    elif op3 == 0b011:                                                    # LDSB
        v = cpu.bus.read8(addr)
        cpu.regs.r[rd] = v if v < 0x80 else v | 0xFFFFFF00
    elif op3 == 0b100:    cpu.regs.r[rd] = cpu.bus.read32(addr)           # LDR
    elif op3 == 0b101:    cpu.regs.r[rd] = cpu.bus.read16(addr)           # LDRH
    elif op3 == 0b110:    cpu.regs.r[rd] = cpu.bus.read8(addr)            # LDRB
    else:                                                                 # LDSH
        if addr & 1:                         # LDSH [odd] = LDSB [odd]（GBATEK）
            v = cpu.bus.read8(addr)
            cpu.regs.r[rd] = v if v < 0x80 else v | 0xFFFFFF00
        else:
            v = cpu.bus.read16(addr)
            cpu.regs.r[rd] = v if v < 0x8000 else v | 0xFFFF0000
    cpu.regs.pc += 2


def _ldr_str_imm(cpu, instr):
    """011xx：LDR/STR 立即偏移（bit12 選 B、bit11 選 L）"""
    b, l = (instr >> 12) & 1, (instr >> 11) & 1
    imm = (instr >> 6) & 0x1F
    rn, rd = (instr >> 3) & 7, instr & 7
    addr = (cpu.regs.r[rn] + (imm if b else imm * 4)) & 0xFFFFFFFF

    if l:
        cpu.regs.r[rd] = cpu.bus.read8(addr) if b else cpu.bus.read32(addr)
    elif b:
        cpu.bus.write8(addr, cpu.regs.r[rd] & 0xFF)
    else:
        cpu.bus.write32(addr, cpu.regs.r[rd])
    cpu.regs.pc += 2


def _ldrh_strh(cpu, instr):
    """1000x：STRH / LDRH 立即偏移"""
    l = (instr >> 11) & 1
    imm = ((instr >> 6) & 0x1F) * 2
    rn, rd = (instr >> 3) & 7, instr & 7
    addr = (cpu.regs.r[rn] + imm) & 0xFFFFFFFF
    if l:
        cpu.regs.r[rd] = cpu.bus.read16(addr)
    else:
        cpu.bus.write16(addr, cpu.regs.r[rd] & 0xFFFF)
    cpu.regs.pc += 2


def _ldr_str_sp(cpu, instr):
    """1001x：STR / LDR Rd, [sp, #imm8*4]"""
    l = (instr >> 11) & 1
    rd = (instr >> 8) & 7
    addr = (cpu.regs.sp + (instr & 0xFF) * 4) & 0xFFFFFFFF
    if l:
        cpu.regs.r[rd] = cpu.bus.read32(addr)
    else:
        cpu.bus.write32(addr, cpu.regs.r[rd])
    cpu.regs.pc += 2


def _add_pc_sp(cpu, instr):
    """1010x：ADD Rd, PC/SP, #imm8*4"""
    op = (instr >> 11) & 0x1F
    rd = (instr >> 8) & 7
    base = ((cpu.regs.pc + 4) & 0xFFFFFFFC) if op == 0b10100 else cpu.regs.sp
    cpu.regs.r[rd] = (base + (instr & 0xFF) * 4) & 0xFFFFFFFF
    cpu.regs.pc += 2


def _push_pop(cpu, instr):
    """1011x：PUSH / POP

    sp 加減用**未對齊原值**（真機唔對齊；jsmolka t225 實測）；
    只有訪問基址先對齊。
    """
    l = (instr >> 11) & 1
    regs = [i for i in range(8) if instr & (1 << i)]
    if (instr >> 8) & 1:
        regs.append(14 if l == 0 else 15)         # PUSH 加 LR，POP 加 PC

    raw_sp = cpu.regs.sp
    sp = raw_sp & ~3                              # 訪問基址對齊

    if not regs:                                  # 空清單（ARMv4 怪癖；thumb/*_no_regs）
        if l == 0:                                # PUSH {}：STMDB 空
            a = (sp - 0x40) & 0xFFFFFFFF
            cpu.bus.write32(a, (cpu.regs.pc + 6) & 0xFFFFFFFF)
            cpu.regs.sp = (raw_sp - 0x40) & 0xFFFFFFFF
            cpu.regs.pc += 2
        else:                                     # POP {}：LDM 空
            cpu.regs.pc = cpu.bus.read32(sp)      # 不 +2
            cpu.regs.sp = (raw_sp + 0x40) & 0xFFFFFFFF
        return

    if l == 0:                                    # PUSH
        sp = (sp - 4 * len(regs)) & 0xFFFFFFFF    # 32-bit wrap（真機語義）
        for i, reg in enumerate(regs):
            cpu.bus.write32((sp + 4 * i) & 0xFFFFFFFF, cpu.regs.r[reg])
        cpu.regs.sp = (raw_sp - 4 * len(regs)) & 0xFFFFFFFF
    else:                                         # POP
        for i, reg in enumerate(regs):
            v = cpu.bus.read32((sp + 4 * i) & 0xFFFFFFFF)
            if reg == 15:                        # POP pc：ARMv4 忽略 bit0、T 不變
                cpu.regs.pc = v
            else:
                cpu.regs.r[reg] = v
        cpu.regs.sp = (raw_sp + 4 * len(regs)) & 0xFFFFFFFF
    if l == 0 or 15 not in regs:                  # POP {..,pc}：pc 已是彈出值，不再 +2
        cpu.regs.pc += 2


def _stm_ldm(cpu, instr):
    """1100x：STMIA / LDMIA"""
    l = (instr >> 11) & 1
    rb = (instr >> 8) & 0x7
    regs = [i for i in range(8) if instr & (1 << i)]
    base_raw = cpu.regs.r[rb]
    addr = base_raw & ~3                          # 訪問基址對齊

    # 空清單（ARMv4）：LDM → pc=[base]；STM → 寫 R15；基底寫回 +0x40
    if not regs:
        if l:
            cpu.regs.pc = cpu.bus.read32(addr)    # t227
        else:
            # STM 空：pc 慣例 = 「下一條嘅 pc 讀值」= 指令+6（jsmolka t229）
            cpu.bus.write32(addr, (cpu.regs.r[15] + 6) & 0xFFFFFFFF)
            cpu.regs.pc += 2
        cpu.regs.r[rb] = (base_raw + 0x40) & 0xFFFFFFFF
        return

    if l == 0:                                    # STMIA：先存再寫回
        new_base = (base_raw + len(regs) * 4) & 0xFFFFFFFF
        for i, reg in enumerate(regs):
            if reg == rb:
                # ARMv4 規則：rb 係 list 第一個 → 存舊 base；
                # 唔係第一個 → 存新 base（jsmolka t230 實測）
                v = base_raw if reg == regs[0] else new_base
            else:
                v = cpu.regs.r[reg]
            cpu.bus.write32((addr + i * 4) & 0xFFFFFFFF, v)
        cpu.regs.r[rb] = new_base                 # writeback 一定做
    else:                                         # LDMIA
        for i, reg in enumerate(regs):
            cpu.regs.r[reg] = cpu.bus.read32((addr + i * 4) & 0xFFFFFFFF)
        if rb not in regs:                        # Rb 在清單內 → 不寫回
            # writeback 用未對齊原值（jsmolka t233）
            cpu.regs.r[rb] = (base_raw + len(regs) * 4) & 0xFFFFFFFF
    cpu.regs.pc += 2


# ── 分支類 ──────────────────────────────────────────────────

def _cond_branch(cpu, instr):
    """1101x：條件分支（cond = bits 11-8，off = 8-bit 有號 ×2）"""
    cond = (instr >> 8) & 0xF
    off = instr & 0xFF
    if off & 0x80:
        off -= 0x100
    if conditions.passed(cond, cpu.regs.cpsr):
        cpu._t_branch_taken = True             # 週期計算要看成功/失敗
        cpu.regs.pc = cpu.regs.pc + 4 + off * 2
    else:
        cpu._t_branch_taken = False
        cpu.regs.pc += 2


def _branch(cpu, instr):
    """11100：B（11-bit 有號 offset ×2）"""
    off = instr & 0x7FF
    if off & 0x400:
        off -= 0x800
    cpu.regs.pc = cpu.regs.pc + 4 + off * 2


# ═══════════════════════════════════════════════════════════════
#  分派器
# ═══════════════════════════════════════════════════════════════

def execute(cpu, instr):
    op = (instr >> 11) & 0x1F          # 通用的「高 5 bit」

    # ── 特殊編碼（完整 mask 判斷，必須排在 op 判斷之前）──
    if (instr & 0xF800) == 0xF000:
        _bl(cpu, instr)                          # F000~F7FF（含 F800 下半部）
    elif (instr & 0xF800) == 0xF800:
        _bl2(cpu, instr)                         # BL 下半部被單獨執行（劈開技巧）
    elif (instr & 0xFF00) == 0xDF00:
        cpu.swi(instr & 0xFF)                    # SWI（進 SVC；HLE 內含返回）
    elif (instr & 0xFC00) == 0x4400:
        _hi_reg(cpu, instr)                      # 高位暫存器（op 也是 01000，要先攔！）
    elif (instr & 0xFF00) == 0xB000:
        _add_sub_sp(cpu, instr)                  # ADD/SUB sp（op 也是 10110，要先攔！）

    # ── 一般家族（op 判斷，家族寬度要數對）──
    elif op in (0b00000, 0b00001, 0b00010):
        _shift_imm(cpu, instr)                   # 000xx（00011 屬於別人家族！）
    elif op == 0b00011:
        _add_sub(cpu, instr)
    elif op == 0b00100:
        _mov_imm(cpu, instr)
    elif op in (0b00101, 0b00110, 0b00111):
        _cmp_add_sub_imm(cpu, instr)
    elif op == 0b01000:
        _alu(cpu, instr)
    elif op == 0b01001:
        _ldr_pc(cpu, instr)
    elif op in (0b01010, 0b01011):
        _ldr_str_reg(cpu, instr)
    elif (op >> 2) == 0b011:
        _ldr_str_imm(cpu, instr)                 # 011xx（op 12~15）
    elif op in (0b10000, 0b10001):
        _ldrh_strh(cpu, instr)
    elif op in (0b10010, 0b10011):
        _ldr_str_sp(cpu, instr)
    elif op in (0b10100, 0b10101):
        _add_pc_sp(cpu, instr)
    elif op in (0b10110, 0b10111):
        _push_pop(cpu, instr)
    elif op in (0b11000, 0b11001):
        _stm_ldm(cpu, instr)
    elif (op >> 1) == 0b1101:
        _cond_branch(cpu, instr)                 # 1101x（op 26~27）
    elif op == 0b11100:
        _branch(cpu, instr)
    else:
        # 11101 = 未定義（BLX 區，ARMv4T 沒有）：真機走 UND 例外
        _undefined(cpu, instr, lr_off=2)