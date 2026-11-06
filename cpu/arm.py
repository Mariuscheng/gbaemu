"""ARM 32-bit 指令集解碼與執行（ARM7TDMI）。

由 ``gba_cpu/arm.py``（以 test-rom 驗證過的純 Python 參考實作）遷移而來。
CPU 核心只透過 ``cpu.regs``（banked registers）與 ``cpu.bus``
（``read8/16/32``、``write8/16/32``）存取狀態，不依賴 PPU／DMA／timer 實作；
週期計數由 :mod:`gbaemu.cpu.arm7tdmi` 負責。

# GBATEK: ARM 32bit Instruction Set (ARM Code)
"""

import logging

log = logging.getLogger("gbaemu.cpu.arm")


def ror32(value, n):
    if n == 0:
        return value
    return ((value >> n) | (value << (32 - n))) & 0xFFFFFFFF


def read_reg(cpu, n):
    if n == 15:
        return cpu.regs.pc + 8     # pipeline：PC 讀到的是 指令位址+8
    return cpu.regs.r[n]


def _signed32(x):
    """把 32-bit 無符號值轉成有號數（算溢位用）"""
    return x if x < 0x80000000 else x - 0x100000000


def _undefined(cpu, instr=None, lr_off=4):
    """未定義指令例外（GBATEK: ARM CPU - Undefined Instruction）。

    進入 UND 模式：PC = 0x04、LR = pc + ``lr_off``、SPSR_und = CPSR、I=1、T=0。
    零售卡在 HLE BIOS 下「重試同一條指令」的行為屬於 BIOS handler（Phase 3），
    不在 CPU 核心模擬。

    每種 (pc, 指令) 只記錄一次（``cpu._undef_seen``），方便找欠缺的指令。
    """
    pc = cpu.regs.pc
    seen = getattr(cpu, "_undef_seen", None)
    if seen is None:
        seen = cpu._undef_seen = set()
    key = (pc, instr)
    if key not in seen:
        seen.add(key)
        if instr is None:
            op = "?"
        elif cpu.regs.cpsr & 0x20:             # Thumb：16-bit opcode
            op = "%04X" % instr
        else:                                  # ARM：32-bit opcode
            op = "%08X" % instr
        log.info("未定義指令 @ %08X opcode=%s → UND 例外（PC=0x04）", pc, op)
    cpu.enter_exception(0x1B, 0x00000004, lr_offset=lr_off)


def shift_operand(value, stype, amount, c_in):
    """移位：回 (結果, C 旗標)，C=None 表示 C 不變。
    立即數移位 amount=0：LSL=不變、LSR/ASR=32、ROR=RRX"""
    if stype == 0b00:                              # LSL
        if amount == 0:  return value, None
        if amount < 32:  return (value << amount) & 0xFFFFFFFF, (value >> (32 - amount)) & 1
        if amount == 32: return 0, value & 1
        return 0, 0
    elif stype == 0b01:                            # LSR
        if amount == 0:  amount = 32
        if amount < 32:  return (value & 0xFFFFFFFF) >> amount, (value >> (amount - 1)) & 1
        if amount == 32: return 0, (value >> 31) & 1
        return 0, 0
    elif stype == 0b10:                            # ASR
        if amount == 0:  amount = 32
        sgn = value if value < 0x80000000 else value - 0x100000000
        if amount < 32:  return (sgn >> amount) & 0xFFFFFFFF, (value >> (amount - 1)) & 1
        return (0 if sgn >= 0 else 0xFFFFFFFF), (value >> 31) & 1
    else:                                          # ROR / RRX
        if amount == 0:                            # RRX：帶 C 一起轉
            return ((c_in << 31) | (value >> 1)) & 0xFFFFFFFF, value & 1
        r = amount & 0x1F                          # register 版可 > 32：真機 mod 32
        if r == 0:
            return value, (value >> 31) & 1        # mod 0：不轉、C = bit31
        return ror32(value, r), (value >> (r - 1)) & 1


def _operand2(cpu, instr, pc_off=8):
    """資料處理的運算元 2：回 (值, 移位產生的 C 或 None)
    pc_off：R15 當運算元時的管線偏移（I=0 且 R=1 → +12，其餘 +8）"""
    c = (cpu.regs.cpsr >> 29) & 1
    if (instr >> 25) & 1:                          # I=1：立即數（ROR 移位）
        imm8 = instr & 0xFF
        rot  = ((instr >> 8) & 0xF) * 2
        if rot == 0:
            return imm8, None                      # 不移位，C 不變
        return ror32(imm8, rot), (imm8 >> (rot - 1)) & 1
    rm    = instr & 0xF
    value = cpu.regs.r[rm] + pc_off if rm == 15 else cpu.regs.r[rm]
    stype = (instr >> 5) & 0b11
    if (instr >> 4) & 1:                           # bit4=1：移位量來自 Rs
        amt = cpu.regs.r[(instr >> 8) & 0xF] & 0xFF
        if amt == 0:
            return value, None                     # 移位 0 → 不變、C 不變
        return shift_operand(value, stype, amt, c)
    return shift_operand(value, stype, (instr >> 7) & 0x1F, c)   # 立即數移位量


def _data_processing(cpu, instr):
    """16 種資料處理運算（op = bits 24-21）"""
    op = (instr >> 21) & 0xF
    s  = (instr >> 20) & 1
    rn = (instr >> 16) & 0xF
    rd = (instr >> 12) & 0xF
    # R15 當運算元：I=0 且 R=1（暫存器移位）→ PC+12，其餘 PC+8
    pc_off = 12 if ((instr >> 25) & 1) == 0 and (instr >> 4) & 1 else 8
    a  = cpu.regs.r[rn] + pc_off if rn == 15 else cpu.regs.r[rn]
    op2, carry = _operand2(cpu, instr, pc_off)
    c  = (cpu.regs.cpsr >> 29) & 1

    if   op == 0b0000: result = a & op2                    # AND
    elif op == 0b0001: result = a ^ op2                    # EOR
    elif op == 0b0010: result = (a - op2) & 0xFFFFFFFF     # SUB
    elif op == 0b0011: result = (op2 - a) & 0xFFFFFFFF     # RSB
    elif op == 0b0100: result = (a + op2) & 0xFFFFFFFF     # ADD
    elif op == 0b0101: result = (a + op2 + c) & 0xFFFFFFFF # ADC
    elif op == 0b0110: result = (a - op2 - (1 - c)) & 0xFFFFFFFF   # SBC
    elif op == 0b0111: result = (op2 - a - (1 - c)) & 0xFFFFFFFF   # RSC
    elif op == 0b1000: result = a & op2                    # TST（不寫回）
    elif op == 0b1001: result = a ^ op2                    # TEQ（不寫回）
    elif op == 0b1010: result = (a - op2) & 0xFFFFFFFF     # CMP（不寫回）
    elif op == 0b1011: result = (a + op2) & 0xFFFFFFFF     # CMN（不寫回）
    elif op == 0b1100: result = a | op2                    # ORR
    elif op == 0b1101: result = op2                        # MOV
    elif op == 0b1110: result = a & (~op2 & 0xFFFFFFFF)    # BIC
    else:             result = ~op2 & 0xFFFFFFFF           # MVN

    is_test = op in (0b1000, 0b1001, 0b1010, 0b1011)
    is_arith = op in (0b0010, 0b0011, 0b0100, 0b0101, 0b0110, 0b0111, 0b1010, 0b1011)
    if s or is_test:                              # 設定旗標
        cpu.regs.set_flag(31, (result >> 31) & 1)          # N
        cpu.regs.set_flag(30, result == 0)                 # Z
        if is_arith:                                      # 算術：C = 運算結果
            if op in (0b0100, 0b0101, 0b1011):               # ADD / ADC / CMN
                cpu.regs.set_flag(29, 1 if a + op2 + (c if op == 0b0101 else 0) > 0xFFFFFFFF else 0)
            elif op in (0b0010, 0b1010):                    # SUB / CMP：C = 無借位
                cpu.regs.set_flag(29, 1 if a >= op2 else 0)
            elif op == 0b0110:                              # SBC
                cpu.regs.set_flag(29, 1 if a >= op2 + (1 - c) else 0)
            else:                                           # RSB / RSC
                cpu.regs.set_flag(29, 1 if op2 >= a + (0 if op == 0b0011 else 1 - c) else 0)
        elif carry is not None:                              # 邏輯：C = 移位 carry
            cpu.regs.set_flag(29, carry)
        # V：有號溢位（把運算元當有號數算）
        if op in (0b0100, 0b0101, 0b1011):
            t = _signed32(a) + _signed32(op2) + (c if op == 0b0101 else 0)
        elif op in (0b0010, 0b0110, 0b1010):
            # SUB/CMP 無進位項；只有 SBC 減 (1-C)
            t = _signed32(a) - _signed32(op2) - (1 - c if op == 0b0110 else 0)
        elif op in (0b0011, 0b0111):
            t = _signed32(op2) - _signed32(a) - (0 if op == 0b0011 else 1 - c)
        else:
            t = None
        if t is not None:
            cpu.regs.set_flag(28, 1 if t > 0x7FFFFFFF or t < -0x80000000 else 0)

    if not is_test:                               # 測試類不寫回
        if rd == 15:                              # 寫到 PC = 直接跳
            if s:
                # 例外返回：CPSR = SPSR + 切換分組暫存器
                _psr_restore(cpu)
            # USR/SYS 沒有 SPSR：ARMv4 的 MOV/ALU pc 不改 T bit，setter 清低 2 bit
            cpu.regs.pc = result
        else:
            cpu.regs.r[rd] = result
            cpu.regs.pc = cpu.regs.pc + 4
    else:
        if rd == 15:
            # CMP/CMN/TST/TEQ + Rd=R15：真機係「寫 PSR bits in R15」
            # （GBATEK 15「Writing to R15」）——例外返回式 restore，
            # 但唔寫 PC、唔 flush pipeline（jsmolka t234／t235 實測）
            _psr_restore(cpu)
        cpu.regs.pc = cpu.regs.pc + 4


def _psr_restore(cpu):
    """例外返回式 PSR 還原：CPSR ← SPSR ＋切換分組（USR/SYS 冇 SPSR，唔做）

    兩個地方共用：① S=1 寫 PC；② Rd=R15 嘅 CMP/CMN/TST/TEQ
    （真機當「寫 PSR bits in R15」——GBATEK 15；jsmolka t234）。
    """
    if cpu.regs.mode() not in (0x10, 0x1F):
        new_cpsr = cpu.regs.spsr_get()
        cpu.regs.switch_mode(new_cpsr & 0x1F)
        cpu.regs.cpsr = new_cpsr


def _block_transfer(cpu, instr):
    """LDM/STM：IA/IB/DA/DB；清單一律以遞增位址處理（GBATEK）

    S=1：pc 在清單 → 例外返回（CPSR=SPSR）；否則 User bank 傳輸
    """
    p = (instr >> 24) & 1
    u = (instr >> 23) & 1
    s = (instr >> 22) & 1
    w = (instr >> 21) & 1
    l = (instr >> 20) & 1
    rn = (instr >> 16) & 0xF
    regs = [i for i in range(16) if instr & (1 << i)]
    base_raw = (cpu.regs.r[rn] + (8 if rn == 15 else 0)) & 0xFFFFFFFF
    base = base_raw & 0xFFFFFFFC                # 訪問地址：強制對齊（PC+8）
    n = len(regs)
    # writeback／「新 base」用未對齊原值計（jsmolka t508「Memory alignment」）
    new_base = (base_raw + (4 * n if u else -4 * n)) & 0xFFFFFFFF

    # 空清單（ARMv4）：R15 傳輸、基底 ±40h
    if n == 0:
        if l:
            cpu.regs.pc = cpu.bus.read32(base)   # LDM 空清單：pc=[base]（不再 +4）
        else:
            # STM 空清單：R15 寫喺「n=16 起始位址」（jsmolka t530/531/532）：
            # IA→base、IB→base+4、DA→base-0x3C、DB→base-0x40
            # 位址一律 32-bit wrap（真機語義）：base±offset 可以越界或變負，
            # Python int 唔識繞回——BZPJ 開機 STMDA r0=0 寫到 0xFFFFFFEC 後
            # 第 6 個位址 0x100000000 就爆 OverflowError（Cython 版 C wrap 冇事）
            if p:
                addr = (base + 4) if u else (base - 0x40)
            else:
                addr = base if u else (base - 0x3C)
            cpu.bus.write32(addr & 0xFFFFFFFF, (cpu.regs.r[15] + 12) & 0xFFFFFFFF)
        if w:
            cpu.regs.r[rn] = (base_raw + (0x40 if u else -0x40)) & 0xFFFFFFFF
        if not l:
            cpu.regs.pc = cpu.regs.pc + 4
        return

    # 起始位址：最低暫存器 → 最低位址，一律遞增
    if p == 0 and u == 1:      addr = base          # IA
    elif p == 1 and u == 1:    addr = (base + 4) & 0xFFFFFFFF      # IB
    elif p == 1 and u == 0:    addr = (base - 4 * n) & 0xFFFFFFFF  # DB
    else:                      addr = (base - 4 * n + 4) & 0xFFFFFFFF   # DA

    # S=1 且非例外返回：User bank 傳輸（R8–R14；FIQ 下尤重要）
    user_bank = s and not (l and 15 in regs)

    for reg in regs:
        if l:
            val = cpu.bus.read32(addr & 0xFFFFFFFF)   # 32-bit wrap（真機語義）
            if reg == 15:                        # LDM pc：ARMv4 T 不變、清低 2 bit
                cpu.regs.pc = val
            elif user_bank and 8 <= reg <= 14:
                cpu.regs.user_set(reg, val)
            else:
                cpu.regs.r[reg] = val
        else:
            if reg == rn:
                # ARMv4：rn 是清單第一個 → 存舊 base（原值）；否則存新 base
                val = base_raw if regs[0] == rn else new_base
            elif user_bank and 8 <= reg <= 14:
                val = cpu.regs.user_get(reg)
            else:
                val = cpu.regs.r[reg]
                if reg == 15:                    # STM 存的 pc = PC+12
                    val = (val + 12) & 0xFFFFFFFF
            cpu.bus.write32(addr & 0xFFFFFFFF, val)   # 32-bit wrap（真機語義）
        addr += 4

    # LDM 且 S=1 且 pc 在清單：例外返回（CPSR = SPSR，切換分組）
    if l and s and 15 in regs:
        new_cpsr = cpu.regs.spsr_get()
        cpu.regs.switch_mode(new_cpsr & 0x1F)
        cpu.regs.cpsr = new_cpsr

    # 寫回
    if w and not (l and rn in regs):
        # STM：writeback 一定會做（base 係清單第一個都一樣——
        # 存「舊 base」只影響寫入內存嘅值）
        # LDM：base 喺清單 → 載入值贏、writeback 唔做（t516/517/518）
        cpu.regs.r[rn] = new_base

    if not (l and 15 in regs):
        cpu.regs.pc = cpu.regs.pc + 4


def _misc(cpu, instr):
    """乘除法（MUL/MLA/SWP）與半字/有號傳輸（STRH/LDRH/LDRSB/LDRSH）"""
    h = (instr >> 4) & 0xF
    if h in (0b1011, 0b1101, 0b1111):           # 半字/有號傳輸
        p = (instr >> 24) & 1
        u = (instr >> 23) & 1
        i = (instr >> 22) & 1
        w = (instr >> 21) & 1
        l = (instr >> 20) & 1
        rn = (instr >> 16) & 0xF
        rd = (instr >> 12) & 0xF
        base = (cpu.regs.r[rn] + (8 if rn == 15 else 0)) & 0xFFFFFFFF
        if i:                                    # 立即數 offset
            offset = ((instr >> 8) & 0xF) << 4 | (instr & 0xF)
        else:                                    # 暫存器 offset
            offset = cpu.regs.r[instr & 0xF]
        addr = ((base + offset) & 0xFFFFFFFF if u
                else (base - offset) & 0xFFFFFFFF)   # 32-bit wrap（真機語義）
        if not p:                                # post-index：位址 = 原 base
            addr = base
        if l:
            if h == 0b1011:
                val = cpu.bus.read16(addr)                     # LDRH
            elif h == 0b1101:
                v = cpu.bus.read8(addr)                        # LDRSB（有號擴展）
                val = (v | 0xFFFFFF00) if v & 0x80 else v
            else:
                if addr & 1:                     # LDRSH [odd] = LDRSB [odd]（GBATEK）
                    v = cpu.bus.read8(addr)
                    val = (v | 0xFFFFFF00) if v & 0x80 else v
                else:
                    v = cpu.bus.read16(addr)     # LDRSH（有號擴展）
                    val = (v | 0xFFFF0000) if v & 0x8000 else v
            if rd == 15:                         # LDRH pc：ARMv4 T 不變，pc 強制對齊
                cpu.regs.pc = val
            else:
                cpu.regs.r[rd] = val
        else:
            val = cpu.regs.r[rd]
            if rd == 15:                         # STRH pc：存的資料 = PC+12
                val = (val + 12) & 0xFFFFFFFF
            cpu.bus.write16(addr, val & 0xFFFF)                # STRH
        if (not p) or w:                         # 寫回（rn=15 不寫回；rd=15 照常寫回）
            if rn != 15:
                # ARM7：load 嘅 writeback 同 Rd 同一寄存器 → 放棄（同 LDR）
                if not (l and rd == rn):
                    cpu.regs.r[rn] = ((base + offset) & 0xFFFFFFFF if u
                                      else (base - offset) & 0xFFFFFFFF)
        if not (l and rd == 15):                 # LDR pc：pc 已載入（ARMv4：T 不變）
            cpu.regs.pc = cpu.regs.pc + 4
        return

    # SWP / SWPB：bits 27-23 = 00010、bits 21-20 = 00、bits 11-4 = 1001
    if ((instr & 0x0FB00FF0) == 0x01000090) or ((instr & 0x0FB00FF0) == 0x01400090):
        b    = (instr >> 22) & 1
        rn   = (instr >> 16) & 0xF
        rd   = (instr >> 12) & 0xF
        rm   = instr & 0xF
        addr = cpu.regs.r[rn]
        if b:
            tmp = cpu.bus.read8(addr)
            cpu.bus.write8(addr, cpu.regs.r[rm] & 0xFF)
        else:
            tmp = cpu.bus.read32(addr)
            cpu.bus.write32(addr, cpu.regs.r[rm])
        cpu.regs.r[rd] = tmp
        cpu.regs.pc = cpu.regs.pc + 4
        return

    # 其餘必須 bits[7:4]=1001；否則屬未定義
    if h != 0b1001:
        _undefined(cpu, instr)
        return

    # MULL/MLAL（bits 27-23 = 00001）：64-bit 乘法（ARM7TDMI 支援）
    if (instr >> 23) & 0x1F == 0b00001:
        u = (instr >> 22) & 1          # 0=無號、1=有號
        a = (instr >> 21) & 1          # 累加
        s = (instr >> 20) & 1
        rdhi = (instr >> 16) & 0xF
        rdlo = (instr >> 12) & 0xF
        rs = (instr >> 8) & 0xF
        rm = instr & 0xF
        if u:
            r = _signed32(cpu.regs.r[rm]) * _signed32(cpu.regs.r[rs])
        else:
            r = cpu.regs.r[rm] * cpu.regs.r[rs]
        if a:
            r += (cpu.regs.r[rdhi] << 32) | cpu.regs.r[rdlo]
        r &= 0xFFFFFFFFFFFFFFFF
        cpu.regs.r[rdlo] = r & 0xFFFFFFFF
        cpu.regs.r[rdhi] = (r >> 32) & 0xFFFFFFFF
        if s:
            cpu.regs.set_flag(31, (r >> 63) & 1)   # N
            cpu.regs.set_flag(30, r == 0)          # Z（C/V 摧毀，不動）
        cpu.regs.pc = cpu.regs.pc + 4
        return

    # MUL / MLA（bits 27-22 = 000000、bits[7:4]=1001）
    if (instr & 0x0FC000F0) != 0x00000090:
        _undefined(cpu, instr)
        return
    a = (instr >> 21) & 1
    s = (instr >> 20) & 1
    rm = instr & 0xF
    rs = (instr >> 8) & 0xF
    rn = (instr >> 12) & 0xF
    rd = (instr >> 16) & 0xF
    result = (cpu.regs.r[rm] * cpu.regs.r[rs]) & 0xFFFFFFFF
    if a:
        result = (result + cpu.regs.r[rn]) & 0xFFFFFFFF
    cpu.regs.r[rd] = result
    if s:
        cpu.regs.set_flag(31, (result >> 31) & 1)   # N
        cpu.regs.set_flag(30, result == 0)          # Z
    cpu.regs.pc = cpu.regs.pc + 4


def execute(cpu, instr):
    if (instr & 0x0FFFFFF0) == 0x012FFF30:      # BLX Rn：ARMv5+；GBA（ARMv4T）屬未定義
        _undefined(cpu, instr)
        return
    if (instr & 0x0FFFFFF0) == 0x012FFF10:      # BX Rn（切換 ARM/Thumb）
        target = read_reg(cpu, instr & 0xF)
        if target & 1:                           # 先定 T，pc setter 依新狀態對齊
            cpu.regs.cpsr |= 0x20
        else:
            cpu.regs.cpsr &= ~0x20
        cpu.regs.pc = target
        return

    if (instr & 0x0FB0F000) == 0x0120F000:     # MSR CPSR/SPSR, Rm
        value = read_reg(cpu, instr & 0xF)
        if instr & 0x00400000:                 # bit22=1 → 寫 SPSR
            _msr_spsr(cpu, (instr >> 16) & 0xF, value)
        else:
            _msr(cpu, (instr >> 16) & 0xF, value)
        cpu.regs.pc = cpu.regs.pc + 4
        return
    if (instr & 0x0FB0F000) == 0x0320F000:     # MSR CPSR/SPSR, #imm
        imm8 = instr & 0xFF
        rot  = ((instr >> 8) & 0xF) * 2
        value = ror32(imm8, rot)
        if instr & 0x00400000:                 # 寫 SPSR
            _msr_spsr(cpu, (instr >> 16) & 0xF, value)
        else:
            _msr(cpu, (instr >> 16) & 0xF, value)
        cpu.regs.pc = cpu.regs.pc + 4
        return
    if (instr & 0x0FFF0FFF) == 0x010F0000:     # MRS Rd, CPSR（bit22=0）
        cpu.regs.r[(instr >> 12) & 0xF] = cpu.regs.cpsr
        cpu.regs.pc = cpu.regs.pc + 4
        return
    if (instr & 0x0FFF0FFF) == 0x014F0000:     # MRS Rd, SPSR（bit22=1）
        cpu.regs.r[(instr >> 12) & 0xF] = cpu.regs.spsr_get()
        cpu.regs.pc = cpu.regs.pc + 4
        return

    cls = (instr >> 26) & 0b11
    if cls == 0b00:                             # 資料處理
        if (instr >> 25) & 1 == 0:
            is_swp  = ((instr & 0x0FB00FF0) == 0x01000090) or \
                      ((instr & 0x0FB00FF0) == 0x01400090)     # SWP/SWPB
            is_half = (instr >> 7) & 1 and (instr >> 4) & 1    # 半字/乘除
            if is_swp or is_half:
                _misc(cpu, instr)               # SWP/半字/乘除
                return
        _data_processing(cpu, instr)
        return

    if cls == 0b01:                             # LDR/STR（支援暫存器 offset）
        if (instr >> 25) & 1 and (instr >> 4) & 1:  # I=1 且 bit4=1：ARMv4 未定義
            _undefined(cpu, instr)
            return
        l  = (instr >> 20) & 1
        b  = (instr >> 22) & 1                  # byte 模式
        rn = (instr >> 16) & 0xF
        rd = (instr >> 12) & 0xF
        base = (cpu.regs.r[rn] + (8 if rn == 15 else 0)) & 0xFFFFFFFF
        if (instr >> 25) & 1:                   # offset = 暫存器（可移位）
            v = cpu.regs.r[instr & 0xF]
            offset, _ = shift_operand(v, (instr >> 5) & 0b11, (instr >> 7) & 0x1F,
                                      (cpu.regs.cpsr >> 29) & 1)
        else:
            offset = instr & 0xFFF
        addr = ((base + offset) & 0xFFFFFFFF if (instr >> 23) & 1
                else (base - offset) & 0xFFFFFFFF)   # 32-bit wrap（真機語義）
        if not (instr >> 24) & 1:               # post-index：位址 = 原 base
            addr = base
        if l:
            val = cpu.bus.read8(addr) if b else cpu.bus.read32(addr)
            if rd == 15:                     # LDR pc：ARMv4 T 不變，pc 強制對齊
                cpu.regs.pc = val
            else:
                cpu.regs.r[rd] = val
        else:
            val = cpu.regs.r[rd]
            if rd == 15:                         # STR pc：存的資料 = PC+12
                val = (val + 12) & 0xFFFFFFFF
            if b:  cpu.bus.write8(addr, val & 0xFF)
            else:  cpu.bus.write32(addr, val)
        if (not (instr >> 24) & 1) or (instr >> 21) & 1:    # 寫回（rn=15 不寫回）
            if rn != 15:
                # ARM7：load 嘅 writeback 同 Rd 係同一寄存器 → 放棄 writeback
                # （loaded value 贏；jsmolka t360/t361 實測）
                if not (l and rd == rn):
                    cpu.regs.r[rn] = ((base + offset) & 0xFFFFFFFF
                                      if (instr >> 23) & 1
                                      else (base - offset) & 0xFFFFFFFF)
        if not (l and rd == 15):                 # LDR pc：pc 已載入（ARMv4：T 不變）
            cpu.regs.pc = cpu.regs.pc + 4
        return

    if (instr >> 25) & 0b111 == 0b100:          # LDM/STM
        _block_transfer(cpu, instr)
        return

    if (instr >> 25) & 0b111 == 0b101:          # B / BL
        offset = instr & 0x00FFFFFF
        if offset & 0x800000:
            offset -= 0x1000000
        if (instr >> 24) & 1:                   # BL：lr = 回傳位址
            cpu.regs.r[14] = cpu.regs.pc + 4
        cpu.regs.pc = cpu.regs.pc + (offset << 2) + 8
        return

    if (instr >> 24) & 0xF == 0xF:              # SWI
        # 註解 byte：真 BIOS 讀 [LR-2]=指令+2 → ARM 是 bit16-23
        # （即組語 `SWI nnnnnn` 的 nn<<16 編碼；已用真 BIOS 實測驗證）
        cpu.swi((instr >> 16) & 0xFF)
        return

    # 未定義 / 協處理器（GBA 無協處理器）：進 Undefined 例外（GBATEK：PC=0x04）
    _undefined(cpu, instr)


def _msr(cpu, mask, value):
    """MSR：mask 的 bit19 = 旗標(f)、bit16 = 控制(c)"""
    if mask & 0x8:
        cpu.regs.set_flag(31, (value >> 31) & 1)   # N
        cpu.regs.set_flag(30, (value >> 30) & 1)   # Z
        cpu.regs.set_flag(29, (value >> 29) & 1)   # C
        cpu.regs.set_flag(28, (value >> 28) & 1)   # V
    if mask & 0x1:
        if (cpu.regs.cpsr & 0x1F) in (0x00, 0x10):   # User 模式：控制欄位唯讀（GBATEK）
            return
        new_mode = value & 0x1F
        if new_mode != cpu.regs.mode():            # 模式改變 → 切換分組暫存器
            canon = 0x1F if new_mode in (0x00, 0x10) else new_mode  # 0x00=User
            if canon in (0x11, 0x12, 0x13, 0x17, 0x1B, 0x1F):
                cpu.regs.switch_mode(canon)
            # 其餘非法模式：真機 UNPREDICTABLE，不動分組避免崩潰
        # T bit 不能由 MSR 改變（GBATEK：只能用 BX 切換 THUMB/ARM）
        cpu.regs.cpsr = (cpu.regs.cpsr & 0xFFFFFF00) | (value & 0xDF) | (cpu.regs.cpsr & 0x20)


def _msr_spsr(cpu, mask, value):
    """MSR 寫 SPSR：套欄位遮罩（f/s/x/c），T bit 無法由 MSR 改變（ARMv4T）"""
    old = cpu.regs.spsr_get()
    new = old
    if mask & 0x8:   # f：旗標 bits 31-24
        new = (new & 0x00FFFFFF) | (value & 0xFF000000)
    if mask & 0x4:   # s：bits 23-16
        new = (new & 0xFF00FFFF) | (value & 0x00FF0000)
    if mask & 0x2:   # x：bits 15-8
        new = (new & 0xFFFF00FF) | (value & 0x0000FF00)
    if mask & 0x1:   # c：控制 bits 7-0（T bit 除外——只有 BX 能改）
        new = (new & 0xFFFFFF00) | (value & 0xDF) | (old & 0x20)
    cpu.regs.spsr_set(new)