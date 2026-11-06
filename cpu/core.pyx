# cython: language_level=3, boundscheck=False, wraparound=False
# cython: cdivision=True, initializedcheck=False, nonecheck=False
"""CPU 的 typed ARM fast core（Phase 5 / M1）。

只處理最常見、且能保持精確語意的 ARM 指令：

- data processing（含 S flag、immediate/register shift）
- MUL / MLA
- LDR/STR word/byte，immediate offset
- B / BL

其餘（Thumb、halfword、LDM/STM、SWI、exception、PSR、coprocessor）回傳
``None``，由 ``cpu/arm7tdmi.py`` 的 Python core 處理。這樣 fast path 不會
改變未支援指令的語意。
"""

from libc.stdint cimport uint32_t, uint64_t, int64_t

cdef unsigned int _CPSR_N = 0x80000000
cdef unsigned int _CPSR_Z = 0x40000000
cdef unsigned int _CPSR_C = 0x20000000
cdef unsigned int _CPSR_V = 0x10000000
cdef unsigned int _CPSR_T = 0x00000020
cdef unsigned int _CPSR_I = 0x00000080


cdef inline unsigned int _ror(unsigned int value, unsigned int n):
    n &= 31
    if n == 0:
        return value
    return (value >> n) | (value << (32 - n))


cdef inline bint _cond(unsigned int cond, unsigned int cpsr):
    cdef unsigned int n = (cpsr >> 31) & 1
    cdef unsigned int z = (cpsr >> 30) & 1
    cdef unsigned int c = (cpsr >> 29) & 1
    cdef unsigned int v = (cpsr >> 28) & 1
    if cond == 0:
        return z == 1
    if cond == 1:
        return z == 0
    if cond == 2:
        return c == 1
    if cond == 3:
        return c == 0
    if cond == 4:
        return n == 1
    if cond == 5:
        return n == 0
    if cond == 6:
        return v == 1
    if cond == 7:
        return v == 0
    if cond == 8:
        return c == 1 and z == 0
    if cond == 9:
        return c == 0 or z == 1
    if cond == 10:
        return n == v
    if cond == 11:
        return n != v
    if cond == 12:
        return z == 0 and n == v
    if cond == 13:
        return z == 1 or n != v
    if cond == 14:
        return True
    return False


cdef class FastCore:
    """M1 ARM fast core；不保存狀態，每次呼叫與 ``Arm7Tdmi`` 同步暫存器。"""

    cdef object _cpu
    cdef unsigned int _regs[16]
    cdef unsigned int _cpsr
    cdef bint _loaded

    def __cinit__(self):
        self._cpu = None
        self._loaded = False

    cdef void _sync_in(self):
        cdef int i
        for i in range(16):
            self._regs[i] = self._cpu.regs.r[i]
        self._cpsr = self._cpu.regs.cpsr

    cdef void _sync_out(self):
        cdef int i
        for i in range(16):
            self._cpu.regs.r[i] = self._regs[i]
        self._cpu.regs.cpsr = self._cpsr

    # ------------------------------------------------------------------
    # flags / helpers
    # ------------------------------------------------------------------
    cdef inline void _nz(self, unsigned int result):
        self._cpsr = (self._cpsr & 0x3FFFFFFF) | (result & _CPSR_N)
        if result == 0:
            self._cpsr |= _CPSR_Z

    cdef inline void _flag(self, unsigned int flag, bint value):
        if value:
            self._cpsr |= flag
        else:
            self._cpsr &= ~flag

    cdef inline unsigned int _cpsr_value(self):
        return self._cpsr

    cdef inline unsigned int _r(self, unsigned int index):
        return self._regs[index]

    cdef inline void _set_r(self, unsigned int index, unsigned int value):
        self._regs[index] = value

    cdef inline unsigned int _shifter_carry(self, unsigned int value,
                                            unsigned int stype,
                                            unsigned int amount,
                                            unsigned int carry_in):
        cdef unsigned int carry = carry_in
        cdef unsigned int n
        if amount == 0:
            if stype == 0:       # LSL #0
                return carry
            if stype == 1:       # LSR #0 = LSR #32
                amount = 32
            elif stype == 2:     # ASR #0 = ASR #32
                amount = 32
            else:                # ROR #0 = RRX
                return value & 1
        if stype == 0:
            if amount < 32:
                return (value >> (32 - amount)) & 1
            return 0
        if stype == 1:
            if amount < 32:
                return (value >> (amount - 1)) & 1
            return 0
        if stype == 2:
            if amount < 32:
                return (value >> (amount - 1)) & 1
            return (value >> 31) & 1
        # ROR
        n = amount & 31
        if n == 0:
            return (value >> 31) & 1
        return (value >> (n - 1)) & 1

    cdef unsigned int _operand2(self, unsigned int instr, bint *is_reg,
                                unsigned int *carry):
        cdef unsigned int value
        cdef unsigned int stype
        cdef unsigned int amount
        cdef unsigned int rm
        cdef unsigned int rn
        cdef unsigned int rd
        cdef unsigned int cpsr = self._cpsr
        if (instr >> 25) & 1:       # immediate
            value = instr & 0xFF
            amount = ((instr >> 8) & 0xF) * 2
            if amount:
                carry[0] = (value >> (amount - 1)) & 1
                value = _ror(value, amount)
            is_reg[0] = False
            return value
        rm = instr & 0xF
        if rm == 15:
            is_reg[0] = False
            return 0
        value = self._r(rm)
        stype = (instr >> 5) & 3
        amount = (instr >> 7) & 0x1F
        if (instr >> 4) & 1:
            # register-specified shift：M1 只支援 < 32，其餘 fallback
            if self._r((instr >> 8) & 0xF) >= 32:
                is_reg[0] = False
                return 0
            amount = self._r((instr >> 8) & 0xF) & 0xFF
        if amount > 32:
            is_reg[0] = False
            return 0
        is_reg[0] = True
        if amount == 0 and stype == 3:
            carry[0] = cpsr & _CPSR_C
            return _ror(value, 0)
        carry[0] = self._shifter_carry(value, stype, amount, cpsr & _CPSR_C)
        if stype == 0:
            return value << amount if amount < 32 else 0
        if stype == 1:
            return value >> amount if amount < 32 else 0
        if stype == 2:
            if amount >= 32:
                return 0xFFFFFFFF if (value & 0x80000000) else 0
            if amount == 0:
                return value
            if value & 0x80000000:
                return (value >> amount) | (<uint32_t>0xFFFFFFFF << (32 - amount))
            return value >> amount
        return _ror(value, amount)


    cdef int _halfword(self, unsigned int instr, unsigned int pc):
        cdef unsigned int h = (instr >> 4) & 0xF
        cdef unsigned int p = (instr >> 24) & 1
        cdef unsigned int u = (instr >> 23) & 1
        cdef unsigned int i = (instr >> 22) & 1
        cdef unsigned int w = (instr >> 21) & 1
        cdef unsigned int l = (instr >> 20) & 1
        cdef unsigned int rn = (instr >> 16) & 0xF
        cdef unsigned int rd = (instr >> 12) & 0xF
        cdef unsigned int base
        cdef unsigned int offset
        cdef unsigned int addr
        cdef unsigned int val
        cdef unsigned int v
        cdef int cycles

        if h not in (0xB, 0xD, 0xF):
            return -1
        if rn == 15:
            base = (self._r(15) + 8) & 0xFFFFFFFF
        else:
            base = self._r(rn)
        if i:
            offset = (((instr >> 8) & 0xF) << 4) | (instr & 0xF)
        else:
            offset = self._r(instr & 0xF)
        addr = (base + offset) & 0xFFFFFFFF if u else (base - offset) & 0xFFFFFFFF
        if not p:
            addr = base
        cycles = self._cpu._arm_cycles(instr)
        if l:
            if h == 0xB:
                val = self._cpu.bus.read16(addr)
            elif h == 0xD:
                v = self._cpu.bus.read8(addr)
                val = (v | 0xFFFFFF00) if v & 0x80 else v
            else:
                if addr & 1:
                    v = self._cpu.bus.read8(addr)
                    val = (v | 0xFFFFFF00) if v & 0x80 else v
                else:
                    v = self._cpu.bus.read16(addr)
                    val = (v | 0xFFFF0000) if v & 0x8000 else v
            if rd == 15:
                self._set_r(15, val)
            else:
                self._set_r(rd, val)
        else:
            val = self._r(rd)
            if rd == 15:
                val = (val + 12) & 0xFFFFFFFF
            self._cpu.bus.write16(addr, val & 0xFFFF)
        if (not p) or w:
            if rn != 15 and not (l and rd == rn):
                self._set_r(rn, (base + offset) & 0xFFFFFFFF if u else (base - offset) & 0xFFFFFFFF)
        if not (l and rd == 15):
            self._set_r(15, (pc + 4) & 0xFFFFFFFF)
        return cycles

    cdef int _block_transfer(self, unsigned int instr, unsigned int pc):
        cdef unsigned int p = (instr >> 24) & 1
        cdef unsigned int u = (instr >> 23) & 1
        cdef unsigned int s = (instr >> 22) & 1
        cdef unsigned int w = (instr >> 21) & 1
        cdef unsigned int l = (instr >> 20) & 1
        cdef unsigned int rn = (instr >> 16) & 0xF
        cdef unsigned int mask = instr & 0xFFFF
        cdef unsigned int n = 0
        cdef unsigned int i
        cdef unsigned int reg
        cdef unsigned int base_raw
        cdef unsigned int base
        cdef unsigned int addr
        cdef unsigned int val
        cdef unsigned int new_base
        cdef bint user_bank
        cdef bint first
        cdef int cycles

        for i in range(16):
            if mask & (1 << i):
                n += 1
        base_raw = (self._r(rn) + (8 if rn == 15 else 0)) & 0xFFFFFFFF
        base = base_raw & 0xFFFFFFFC
        new_base = (base_raw + (4 * n if u else -4 * n)) & 0xFFFFFFFF
        cycles = self._cpu._arm_cycles(instr)

        if n == 0:
            if l:
                self._set_r(15, self._cpu.bus.read32(base))
            else:
                if p:
                    addr = (base + 4) if u else (base - 0x40)
                else:
                    addr = base if u else (base - 0x3C)
                self._cpu.bus.write32(addr & 0xFFFFFFFF, (self._r(15) + 12) & 0xFFFFFFFF)
            if w:
                self._set_r(rn, (base_raw + (0x40 if u else -0x40)) & 0xFFFFFFFF)
            if not l:
                self._set_r(15, (pc + 4) & 0xFFFFFFFF)
            return cycles

        if p == 0 and u == 1:
            addr = base
        elif p == 1 and u == 1:
            addr = (base + 4) & 0xFFFFFFFF
        elif p == 1 and u == 0:
            addr = (base - 4 * n) & 0xFFFFFFFF
        else:
            addr = (base - 4 * n + 4) & 0xFFFFFFFF

        user_bank = bool(s and not (l and (mask & 0x8000)))
        first = True
        for reg in range(16):
            if not (mask & (1 << reg)):
                continue
            if l:
                val = self._cpu.bus.read32(addr & 0xFFFFFFFF)
                if reg == 15:
                    self._set_r(15, val)
                elif user_bank and 8 <= reg <= 14:
                    self._cpu.regs.user_set(reg, val)
                else:
                    self._set_r(reg, val)
            else:
                if reg == rn:
                    val = base_raw if first else new_base
                elif user_bank and 8 <= reg <= 14:
                    val = self._cpu.regs.user_get(reg)
                else:
                    val = self._r(reg)
                    if reg == 15:
                        val = (val + 12) & 0xFFFFFFFF
                self._cpu.bus.write32(addr & 0xFFFFFFFF, val)
            first = False
            addr += 4

        if l and s and (mask & 0x8000):
            newcpsr = self._cpu.regs.spsr_get()
            self._cpu.regs.switch_mode(newcpsr & 0x1F)
            self._cpsr = newcpsr

        if w and not (l and (mask & (1 << rn))):
            self._set_r(rn, new_base)

        if not (l and (mask & 0x8000)):
            self._set_r(15, (pc + 4) & 0xFFFFFFFF)
        return cycles

    cpdef void flush(self, object cpu):
        if self._loaded:
            self._sync_out()
            self._loaded = False

    cpdef object run_block(self, object cpu, int budget):
        """連續執行支援的 ARM 指令，回傳 cycle 總數（0 = 交給 Python core）。"""

        cdef int total = 0
        cdef object result
        self._cpu = cpu
        if cpu.core.halted or (cpu.regs.cpsr & _CPSR_T):
            return 0
        if cpu.bus is None or cpu.bus.irq_line:
            return 0
        while total < budget:
            result = self.try_step(cpu, False)
            if result is None:
                break
            if result <= 0:
                break
            total += result
            if cpu.core.halted or cpu.bus.irq_line:
                break
        self.flush(cpu)
        return total

    # ------------------------------------------------------------------
    # step
    # ------------------------------------------------------------------
    cpdef object try_step(self, object cpu, bint flush=True):
        """回傳 cycle 數；回傳 None 代表未處理（fallback）。"""

        cdef unsigned int instr
        cdef unsigned int pc
        cdef unsigned int cond
        cdef unsigned int op
        cdef unsigned int rn
        cdef unsigned int rd
        cdef unsigned int rm
        cdef unsigned int a
        cdef unsigned int b
        cdef uint64_t wide
        cdef unsigned int result
        cdef unsigned int carry
        cdef unsigned int old_carry
        cdef unsigned int cpsr
        cdef bint is_reg
        cdef bint sflag
        cdef int cycles
        cdef unsigned int address
        cdef unsigned int offset
        cdef unsigned int value
        cdef unsigned int target
        cdef unsigned int rnval
        cdef unsigned int rdval
        cdef bint pre
        cdef bint up
        cdef bint byte
        cdef bint load
        cdef bint writeback
        cdef unsigned int h
        cdef unsigned int off
        cdef uint64_t product
        cdef unsigned int reglist
        cdef unsigned int n
        cdef unsigned int base_raw
        cdef unsigned int new_base
        cdef unsigned int spsr
        cdef unsigned int newcpsr
        cdef unsigned int i
        cdef unsigned int reg
        cdef bint p
        cdef bint u
        cdef bint s
        cdef bint w
        cdef bint l
        cdef bint user_bank
        cdef bint empty

        self._cpu = cpu
        if not self._loaded:
            self._sync_in()
            self._loaded = True
        cpsr = self._cpsr
        if cpsr & _CPSR_T:
            return None
        if cpu.bus is None:
            return None
        if cpu.bus.irq_line and not (cpsr & _CPSR_I):
            return None
        pc = self._r(15) & 0xFFFFFFFC
        instr = cpu.bus.read32(pc)
        cond = (instr >> 28) & 0xF
        if cond == 0xF:
            return None
        if not _cond(cond, cpsr):
            return None

        # ---- B / BL ----
        if (instr >> 25) & 0x7 == 0x5:
            if (instr >> 28) & 0xF == 0xF:
                return None
            target = (instr & 0x00FFFFFF) << 2
            if target & 0x02000000:
                target |= 0xFC000000
            cycles = cpu._arm_cycles(instr)
            if (instr >> 24) & 1:
                self._set_r(14, (pc + 4) & 0xFFFFFFFF)
            self._set_r(15, (pc + 8 + target) & 0xFFFFFFFF)
            if flush:
                self._sync_out()
                self._loaded = False
            return cycles


        # ---- BX ----
        if False and (instr & 0x0FFFFFF0) == 0x012FFF10:
            rm = instr & 0xF
            if rm == 15:
                return None
            cycles = cpu._arm_cycles(instr)
            target = self._r(rm)
            if target & 1:
                self._cpsr |= _CPSR_T
                target &= 0xFFFFFFFE
            else:
                self._cpsr &= ~_CPSR_T
                target &= 0xFFFFFFFC
            self._set_r(15, target & 0xFFFFFFFF)
            if flush:
                self._sync_out()
                self._loaded = False
            return cycles

        # ---- SWI ----
        if False and (instr >> 24) & 0xF == 0xF:
            cycles = cpu._arm_cycles(instr)
            self._sync_out()
            self._loaded = False
            cpu.swi((instr >> 16) & 0xFF)
            return cycles

        # ---- halfword / signed transfer ----
        if False and (instr & 0x0E000090) == 0x00000090 and ((instr >> 5) & 1):
            result = self._halfword(instr, pc)
            if result >= 0:
                if flush:
                    self._sync_out()
                    self._loaded = False
                return result
            return None

        # ---- LDM / STM ----
        if False and (instr >> 25) & 0x7 == 0x4:
            result = self._block_transfer(instr, pc)
            if result >= 0:
                if flush:
                    self._sync_out()
                    self._loaded = False
                return result
            return None

        # ---- long multiply ----
        if False and (instr & 0x0F8000F0) == 0x00800090:
            rdhi = (instr >> 16) & 0xF
            rdlo = (instr >> 12) & 0xF
            rs = (instr >> 8) & 0xF
            rm = instr & 0xF
            if 15 in (rdhi, rdlo, rs, rm):
                return None
            cycles = cpu._arm_cycles(instr)
            if (instr >> 22) & 1:
                product = <uint64_t><int64_t><int>self._r(rm) * <int64_t><int>self._r(rs)
            else:
                product = <uint64_t>self._r(rm) * self._r(rs)
            if (instr >> 21) & 1:
                product += (<uint64_t>self._r(rdhi) << 32) | self._r(rdlo)
            product &= 0xFFFFFFFFFFFFFFFF
            self._set_r(rdlo, <uint32_t>product)
            self._set_r(rdhi, <uint32_t>(product >> 32))
            if (instr >> 20) & 1:
                self._cpsr = (self._cpsr & 0x3FFFFFFF) | ((<uint32_t>(product >> 32)) & _CPSR_N)
                if product == 0:
                    self._cpsr |= _CPSR_Z
            self._set_r(15, (pc + 4) & 0xFFFFFFFF)
            if flush:
                self._sync_out()
                self._loaded = False
            return cycles

        # ---- MUL / MLA ----
        if ((instr & 0x0FC000F0) == 0x00000090):
            rd = (instr >> 16) & 0xF
            rn = (instr >> 12) & 0xF
            rm = instr & 0xF
            if rd == 15 or rm == 15 or rn == 15:
                return None
            cycles = cpu._arm_cycles(instr)
            result = (self._r(rm) * self._r((instr >> 8) & 0xF)) & 0xFFFFFFFF
            if (instr >> 21) & 1:
                result = (result + self._r(rn)) & 0xFFFFFFFF
            self._set_r(rd, result)
            if (instr >> 20) & 1:
                self._nz(result)
            self._set_r(15, (pc + 4) & 0xFFFFFFFF)
            if flush:
                self._sync_out()
                self._loaded = False
            return cycles

        # ---- misc / BX / MSR / MRS / SWP：交由 Python core ----
        if (instr & 0x0FFFFFF0) in (0x012FFF10, 0x012FFF30):
            return None
        if (instr & 0x0FB00FF0) in (0x01000090, 0x01400090):
            return None
        if (instr & 0x0FB0F000) in (0x0120F000, 0x0320F000, 0x010F0000, 0x014F0000):
            return None

        # ---- data processing ----
        if (instr >> 26) & 3 == 0 and ((instr >> 25) & 1 or not ((instr >> 4) & 1)):
            op = (instr >> 21) & 0xF
            sflag = bool((instr >> 20) & 1)
            rn = (instr >> 16) & 0xF
            rd = (instr >> 12) & 0xF
            if rd == 15 or (rn == 15 and op not in (13, 15)):
                return None
            if ((instr >> 25) & 1) == 0:
                rm = instr & 0xF
                if rm == 15:
                    return None
                if (instr >> 4) & 1:
                    if self._r((instr >> 8) & 0xF) >= 32:
                        return None
            old_carry = cpsr & _CPSR_C
            carry = old_carry
            value = self._operand2(instr, &is_reg, &carry)
            if not is_reg and ((instr >> 25) & 1) == 0:
                return None
            a = self._r(rn) if rn != 15 else (pc + 8) & 0xFFFFFFFF
            cycles = cpu._arm_cycles(instr)
            if op == 0 or op == 1 or op == 8 or op == 9 or op == 12 or op == 13 or op == 14 or op == 15:
                if op == 0 or op == 8:
                    result = a & value
                elif op == 1 or op == 9:
                    result = a ^ value
                elif op == 12:
                    result = a | value
                elif op == 13:
                    result = value
                elif op == 14:
                    result = a & ~value
                else:
                    result = ~value
                if op in (8, 9) or sflag:
                    self._nz(result)
                    self._flag(_CPSR_C, carry & 1)
                if op not in (8, 9):
                    if rd != 15:
                        self._set_r(rd, result)
            else:
                b = value
                if op == 2 or op == 10:
                    wide = <uint64_t>a - b
                    result = <uint32_t>wide
                    self._flag(_CPSR_C, a >= b)
                    self._flag(_CPSR_V, ((a ^ b) & (a ^ result) & 0x80000000) != 0)
                elif op == 3 or op == 7:
                    wide = <uint64_t>b - a
                    result = <uint32_t>wide
                    self._flag(_CPSR_C, b >= a)
                    self._flag(_CPSR_V, ((b ^ a) & (b ^ result) & 0x80000000) != 0)
                elif op == 4 or op == 11:
                    wide = <uint64_t>a + b
                    result = <uint32_t>wide
                    self._flag(_CPSR_C, wide > 0xFFFFFFFF)
                    self._flag(_CPSR_V, ((a ^ result) & (b ^ result) & 0x80000000) != 0)
                elif op == 5:
                    wide = <uint64_t>a + b + (old_carry >> 29)
                    result = <uint32_t>wide
                    self._flag(_CPSR_C, wide > 0xFFFFFFFF)
                    self._flag(_CPSR_V, ((a ^ result) & (b ^ result) & 0x80000000) != 0)
                elif op == 6:
                    wide = <uint64_t>a - b - ((old_carry >> 29) ^ 1)
                    result = <uint32_t>wide
                    self._flag(_CPSR_C, a >= b + ((old_carry >> 29) ^ 1))
                    self._flag(_CPSR_V, ((a ^ b) & (a ^ result) & 0x80000000) != 0)
                else:  # op 7 RSC
                    wide = <uint64_t>b - a - ((old_carry >> 29) ^ 1)
                    result = <uint32_t>wide
                    self._flag(_CPSR_C, b >= a + ((old_carry >> 29) ^ 1))
                    self._flag(_CPSR_V, ((b ^ a) & (b ^ result) & 0x80000000) != 0)
                if op in (2, 3, 4, 5, 6, 7):
                    if op not in (10, 11):
                        if sflag:
                            self._nz(result)
                    else:
                        self._nz(result)
                if op in (10, 11):
                    self._nz(result)
                else:
                    self._set_r(rd, result)
            self._set_r(15, (pc + 4) & 0xFFFFFFFF)
            if flush:
                self._sync_out()
                self._loaded = False
            return cycles

        # ---- LDR / STR immediate offset ----
        if (instr >> 26) & 3 == 1:
            if (instr >> 25) & 1:
                return None
            if (instr >> 4) & 1:       # halfword/signed/halfword-misc：fallback
                return None
            rn = (instr >> 16) & 0xF
            rd = (instr >> 12) & 0xF
            if rn == 15 or rd == 15:
                return None
            load = bool((instr >> 20) & 1)
            byte = bool((instr >> 22) & 1)
            pre = bool((instr >> 24) & 1)
            up = bool((instr >> 23) & 1)
            writeback = bool((instr >> 21) & 1) or not pre
            offset = instr & 0xFFF
            rnval = self._r(rn)
            address = (rnval + offset) & 0xFFFFFFFF if up else (rnval - offset) & 0xFFFFFFFF
            if not pre:
                address = rnval
            cycles = cpu._arm_cycles(instr)
            if load:
                value = cpu.bus.read8(address) if byte else cpu.bus.read32(address)
                self._set_r(rd, value)
            else:
                value = self._r(rd)
                if byte:
                    cpu.bus.write8(address, value & 0xFF)
                else:
                    cpu.bus.write32(address, value)
            if writeback and not (load and rd == rn):
                self._set_r(rn, (rnval + offset) & 0xFFFFFFFF if up else (rnval - offset) & 0xFFFFFFFF)
            self._set_r(15, (pc + 4) & 0xFFFFFFFF)
            if flush:
                self._sync_out()
                self._loaded = False
            return cycles

        return None


__all__ = ["FastCore"]
