"""ARM/THUMB 指令週期計算（S／N／I），自 ``gba_cpu/cpu.py`` 移植。

數值模型依規格 §3.6.3／§3.6.4 與 GBATEK「ARM CPU Instruction Cycle Times」：

* fetch 以 ``self._fetch()`` 依 PC 所在區域計價（ROM 有 prefetch 與 128 KiB 邊界）。
* 資料存取使用 ``self.bus.access_cost()``（由 :func:`gbaemu.bus.access.access_cycles`
  提供 S／N 與 WAITCNT）。
* ``_set_fetch_seq()`` 決定下一條指令的抓取是 S 還是 N（load/store 之後為 N）。

本模組是 mixin：使用時需提供 ``self.regs``、``self.bus``、``self._nseq_fetch``、
``self._t_branch_taken``（見 :class:`gbaemu.cpu.arm7tdmi.Arm7Tdmi`）。

# GBATEK: ARM CPU Instruction Cycle Times / N-S-I cycle definitions
"""

from __future__ import annotations

from . import conditions


def _io_word_extra(addr):
    """32-bit store 去 16-bit IO 裝置：多一個 beat（+1 cycle）——

    除 timer（0x100-0x10F）同 IRQ（0x200-0x2FF）寄存器區之外
    （同 core.pyx 完全一致，sync 測試把關）。"""
    return 0x04000000 <= addr < 0x040003FF and \
           not (0x04000100 <= addr < 0x04000110) and \
           not (0x04000200 <= addr < 0x04000300)


class CycleModel:
    """ARM／THUMB 指令週期 mixin（見模組 docstring）。"""

    def _fetch(self, pc, width, internal):
        """單個指令抓取週期（區域感知、旗標驅動；同 core.pyx）
        internal 參數保留但忽略：序性由 _nseq_fetch 旗標（NBAs pipe.access）決定"""
        seq = 1
        if self._nseq_fetch:                    # 前一條 load/store → 本次抓取非循序
            self._nseq_fetch = False
            seq = 0
        if self.bus.after_dma:                  # DMA 後首個 CPU 存取強制非循序
            self.bus.after_dma = False
            seq = 0
        page = pc >> 24
        if 0x08 <= page <= 0x0D:
            if (self.bus.io[0x205] >> 6) & 1:
                return 1
            if internal and seq:
                # Prefetch Disable Bug（GBATEK 11 章）：ROM 中帶 internal cycles
                # 的 opcode，其 fetch 由 1S 變 1N。
                return self.bus.access_cost(pc, width, 0)
            return self.bus.access_cost(pc, width, seq)
        return self.bus.access_cost(pc, width, 1)

    def _arm_addr(self, instr):
        """_arm_cycles 用：LDR/STR（字/位元組）有效位址（唔改狀態）"""
        rn = (instr >> 16) & 0xF
        base = self.regs.r[rn]
        if rn == 15:
            base = (base + 8) & 0xFFFFFFFF
        if (instr >> 25) & 1:
            off = self.regs.r[instr & 0xF]
            st = (instr >> 5) & 3
            sa = (instr >> 7) & 0x1F
            if st == 0:
                off = (off << sa) & 0xFFFFFFFF
            elif st == 1:
                off = (off >> sa) if sa else 0
            elif st == 2:
                if sa:
                    off = (off >> sa) | ((0xFFFFFFFF << (32 - sa)) & 0xFFFFFFFF) \
                          if (off & 0x80000000) else off >> sa
                    off &= 0xFFFFFFFF
                else:
                    off = 0xFFFFFFFF if (off & 0x80000000) else 0
            else:
                off = (((off >> sa) | (off << (32 - sa))) & 0xFFFFFFFF) if sa else (off >> 1)
        else:
            off = instr & 0xFFF
        if (instr >> 23) & 1:
            return (base + off) & 0xFFFFFFFF
        return (base - off) & 0xFFFFFFFF

    def _arm_addr_h(self, instr):
        """_arm_cycles 用：LDRH/STRH/LDRSB/LDRSH 有效位址
        bit22：1 = 立即值、0 = 暫存器偏移"""
        rn = (instr >> 16) & 0xF
        base = self.regs.r[rn]
        if rn == 15:
            base = (base + 8) & 0xFFFFFFFF
        if (instr >> 22) & 1:
            off = ((instr >> 4) & 0xF0) | (instr & 0xF)
        else:
            off = self.regs.r[instr & 0xF]
        if (instr >> 23) & 1:
            return (base + off) & 0xFFFFFFFF
        return (base - off) & 0xFFFFFFFF

    def _units_cost(self, base, n, width):
        """多暫存器資料單元成本：首個非循序、之後循序（128K 邊界喺 access_cost 內）"""
        c = self.bus.access_cost(base, width, 0)
        for k in range(1, n):
            c += self.bus.access_cost(base + k * width, width, 1)
        return c

    def _mul_m(self, rs, signed=True):
        """乘法內部週期 m（GBATEK）：依 Rs 高位是「全 0」（無號）或「全 0/全 1」（有號）決定 1~4"""
        def chk(v, bits):
            return v == 0 or (signed and v == (1 << bits) - 1)
        if chk((rs >> 8) & 0xFFFFFF, 24):
            return 1
        if chk((rs >> 16) & 0xFFFF, 16):
            return 2
        if chk((rs >> 24) & 0xFF, 8):
            return 3
        return 4

    # ------------------------------------------------------------------
    # mGBA 式 active-region accounting（Python reference）
    # 對應 Rust `arm_cycles_mgba`／`thumb_cycles_mgba`；由
    # `CpuBus.mgba_timing` 開啟，其餘路徑保持 legacy。
    # ------------------------------------------------------------------
    @staticmethod
    def _s32(value):
        value &= 0xFFFFFFFF
        return value - 0x100000000 if value & 0x80000000 else value

    @staticmethod
    def _clz32(value):
        value &= 0xFFFFFFFF
        return 32 if value == 0 else 32 - value.bit_length()

    @staticmethod
    def _mgba_mul_wait(value, signed=True):
        value &= 0xFFFFFFFF

        def hit(mask, pattern):
            return (value & mask) == pattern

        if hit(0xFFFFFF00, 0) or (signed and hit(0xFFFFFF00, 0xFFFFFF00)):
            return 1
        if hit(0xFFFF0000, 0) or (signed and hit(0xFFFF0000, 0xFFFF0000)):
            return 2
        if hit(0xFF000000, 0) or (signed and hit(0xFF000000, 0xFF000000)):
            return 3
        return 4

    def _mgba_fetch(self, pc, width):
        return self.bus.mgba_access(pc, width, 1)

    def _mgba_write_pc(self, target, width):
        return self.bus.mgba_access(target, width, 0) + self.bus.mgba_access(target, width, 1)

    def _mgba_delta(self, pc, width):
        return self.bus.mgba_access(pc, width, 0) - self.bus.mgba_access(pc, width, 1)

    def _mgba_stall(self, pc, arm, wait):
        return self.bus.mgba_stall(pc + (8 if arm else 4), wait)

    def _mgba_data(self, pc, arm, address, width):
        return self.bus.mgba_data_cost(pc + (8 if arm else 4), address, width)

    def _mgba_store(self, pc, arm, address, width):
        return self.bus.mgba_store_cost(pc + (8 if arm else 4), address, width)

    def _mgba_multiple_cost(self, pc, arm, start, count, load):
        """LDM/STM：同 region 用 mGBA formula + stall；跨區逐 register 計。"""

        count = max(1, count)
        end = (start + (count - 1) * 4) & 0xFFFFFFFF
        if (start >> 24) == (end >> 24):
            seq = self.bus.mgba_access(start, 4, 1)
            nonseq = self.bus.mgba_access(start, 4, 0)
            wait = seq * count + (1 if load else 0) + seq - nonseq
            return self.bus.mgba_stall(pc + (8 if arm else 4), wait)
        total = 0
        prev = start
        for index in range(count):
            addr = (start + index * 4) & 0xFFFFFFFF
            seq = index > 0 and addr == ((prev + 4) & 0xFFFFFFFF) and (addr >> 24) == (prev >> 24)
            total += self.bus.mgba_access(addr, 4, 1 if seq else 0)
            prev = addr
        return total + (1 if load else 0)

    def _mgba_div_stall(self, num, denom):
        loops = self._clz32(denom) - self._clz32(num)
        return 4 + 13 * max(1, loops) + 7

    def _mgba_arctan_stall(self, i):
        i = self._s32(i)
        cycles = 37
        cycles += self._mgba_mul_wait(self._s32(i * i))
        a = self._s32(-((i * i) >> 14))
        cycles += self._mgba_mul_wait(self._s32(0xA9 * a))
        b = self._s32(((0xA9 * a) >> 14) + 0x390)
        for constant in (0x91C, 0xFB6, 0x16AA, 0x2081, 0x3651, 0xA2F9):
            cycles += self._mgba_mul_wait(self._s32(b * a))
            b = self._s32(((b * a) >> 14) + constant)
        return cycles

    def _mgba_arctan2_stall(self, x, y):
        if x == 0 or y == 0:
            return 11
        ax, ay = abs(x), abs(y)
        if y >= 0:
            if x >= 0:
                value = (y * 16384) // x if ax >= ay else 0
            elif ax >= ay:
                value = (y * 16384) // x
            else:
                value = (x * 16384) // y
        elif x <= 0:
            value = (y * 16384) // x if ax > ay else 0
        elif ax >= ay:
            value = (y * 16384) // x
        else:
            value = (x * 16384) // y
        return 11 if value == 0 else self._mgba_arctan_stall(value)

    def _mgba_sqrt_stall(self, x):
        if x == 0:
            return 53
        cycles = 15
        upper, bound = x, 1
        while bound < upper:
            upper >>= 1
            bound <<= 1
            cycles += 6
        while True:
            cycles += 6
            upper = x
            accum = 0
            lower = bound
            while True:
                cycles += 5
                old_lower = lower
                if lower <= upper >> 1:
                    lower <<= 1
                if old_lower >= upper >> 1:
                    break
            while True:
                cycles += 8
                accum <<= 1
                if upper >= lower:
                    accum += 1
                    upper -= lower
                if lower == bound:
                    break
                lower >>= 1
            old_bound = bound
            bound = (bound + accum) >> 1
            if bound >= old_bound:
                bound = old_bound
                break
        return cycles

    def _mgba_bios_stall(self, number):
        if number == 0x06:
            return self._mgba_div_stall(self.regs.r[0], self.regs.r[1])
        if number == 0x07:
            return self._mgba_div_stall(self.regs.r[1], self.regs.r[0])
        if number == 0x08:
            return self._mgba_sqrt_stall(self.regs.r[0])
        if number == 0x09:
            return self._mgba_arctan_stall(self.regs.r[0])
        if number == 0x0A:
            return self._mgba_arctan2_stall(self._s32(self.regs.r[0]), self._s32(self.regs.r[1]))
        return None

    def _mgba_swi_profile(self, next_pc, width):
        """純 HLE 的 SWI profile（entry + BIOS stub + exit）。

        mGBA 會執行 `hle-bios.s` 的 SWI stub 並補償 18 cycles；我哋唔執行 BIOS
        程式碼，所以喺 HLE 直接加返固定成本。數值由 suite 實測校準，Rust core
        用同一組常數（`cpu.rs::hle_swi_profile`）。
        """
        thumb = width == 2
        page = next_pc >> 24
        if page == 0x02:
            profile = 45 if thumb else 44
        elif page == 0x03:
            profile = 43 if thumb else 42
        elif 0x08 <= page <= 0x0D:
            profile = 47
        else:
            profile = 45 if thumb else 44
        # WS0 first-access 較短（suite `.N.`／`PN.`／`.NS`／`PNS`，WAITCNT bit2）
        # 的 config，return refill 少 1 cycle。
        if 0x08 <= page <= 0x0D and self.bus.waitcnt & 0x0004:
            profile -= 1
        return profile

    def _mgba_cpuset_transfer(self, src, dst, control, fast):
        """CpuSet（0x0B）／CpuFastSet（0x0C）搬運成本。

        mGBA 由 BIOS stub 的搬運 loop 產生時間；純 HLE 按 element 數量計，
        常數同 Rust `hle_cpuset_transfer` 一致（見 TIMING.md 4g）。
        """
        del src, dst
        count = max(1, control & 0x001FFFFF)
        fill = bool(control & 0x01000000)
        width32 = bool(control & 0x04000000)
        per_unit = {(True, False): 25, (True, True): 16,
                    (False, False): 13, (False, True): 8}[(width32, fill)]
        return 13 + count * per_unit

    def _mgba_swi_cycles(self, number, pc, arm):
        if number in (0x0B, 0x0C):
            width = 4 if arm else 2
            return (45 + self.bus.mgba_access(pc, 2, 0)
                    + self.bus.mgba_access(pc, width, 0)
                    + self.bus.mgba_access(pc, width, 1)
                    + self._mgba_cpuset_transfer(self.regs.r[0], self.regs.r[1],
                                                 self.regs.r[2], number == 0x0C))
        stall = self._mgba_bios_stall(number)
        if stall is not None:
            if stall >= 18:
                width = 4 if arm else 2
                next_pc = (pc + width) & ~(width - 1)
                return (stall + self._mgba_swi_profile(next_pc, width)
                        + self._mgba_write_pc(next_pc, width))
            return stall
        base = 4 if arm else 2
        nonseq = self.bus.mgba_access(pc, 2, 0)
        return 45 + nonseq + self.bus.mgba_access(pc, base, 0) \
            + self.bus.mgba_access(pc, base, 1)

    def _arm_cycles_mgba(self, instr):
        pc = self.regs.r[15] & 0xFFFFFFFC
        base = self._mgba_fetch(pc, 4)
        if (instr >> 25) & 0b111 == 0b101:          # B / BL
            off24 = instr & 0xFFFFFF
            if off24 & 0x800000:
                off24 -= 0x1000000
            target = (pc + 8 + (off24 << 2)) & 0xFFFFFFFF
            return base + self._mgba_write_pc(target, 4)
        if (instr >> 24) & 0xF == 0xF:              # SWI／coprocessor
            if (instr & 0x0F000000) == 0x0F000000:
                return base + self._mgba_swi_cycles((instr >> 16) & 0xFF, pc, True)
            return base
        if (instr & 0x0FFFFFF0) == 0x012FFF10:      # BX
            target = self.regs.r[instr & 0xF]
            width = 2 if target & 1 else 4
            return base + self._mgba_write_pc(target & 0xFFFFFFFE, width)
        if (instr & 0x0FB0F000) in (0x0120F000, 0x0320F000):   # MSR
            return base
        if (instr & 0x0FFF0FFF) in (0x010F0000, 0x014F0000):   # MRS
            return base
        if (instr >> 25) & 0b111 == 0b100:          # LDM / STM
            count = bin(instr & 0xFFFF).count("1") or 1
            rn = self.regs.r[(instr >> 16) & 0xF] & 0xFFFFFFFC
            delta = self._mgba_delta(pc, 4)
            if (instr >> 20) & 1:
                cost = base + delta + self._mgba_multiple_cost(pc, True, rn, count, True)
                if instr & 0x8000:
                    cost += self._mgba_write_pc(self.regs.r[15] & 0xFFFFFFFC, 4)
                return max(1, cost)
            return max(1, base + delta + self._mgba_multiple_cost(pc, True, rn, count, False))
        if (instr >> 26) & 0b11 == 0b01:            # LDR / STR（字／位元組）
            rd = (instr >> 12) & 0xF
            addr = self._arm_addr(instr)
            width = 1 if (instr >> 22) & 1 else 4
            load = bool((instr >> 20) & 1)
            data = self._mgba_data(pc, True, addr, width) if load \
                else self._mgba_store(pc, True, addr, width)
            cost = base + data + self._mgba_delta(pc, 4)
            if load and rd == 15:
                cost += self._mgba_write_pc(self.regs.r[15] & 0xFFFFFFFC, 4)
            return max(1, cost)
        if (instr & 0x0F8000F0) == 0x00800090:      # long multiply
            rs = self.regs.r[(instr >> 8) & 0xF]
            signed = bool((instr >> 22) & 1)
            wait = self._mgba_mul_wait(rs, signed) + (2 if (instr >> 21) & 1 else 1)
            return max(1, base + self._mgba_stall(pc, True, wait) + self._mgba_delta(pc, 4))
        if (instr & 0x0FC000F0) == 0x00000090:      # MUL / MLA
            rs = self.regs.r[(instr >> 8) & 0xF]
            wait = self._mgba_mul_wait(rs) + (1 if (instr >> 21) & 1 else 0)
            return max(1, base + self._mgba_stall(pc, True, wait) + self._mgba_delta(pc, 4))
        if (instr >> 4) & 0xF in (0b1011, 0b1101, 0b1111):     # LDRH/STRH/LDRSB/LDRSH
            addr = self._arm_addr_h(instr)
            width = 1 if (instr >> 4) & 0xF == 0b1101 else 2
            rd = (instr >> 12) & 0xF
            load = bool((instr >> 20) & 1)
            data = self._mgba_data(pc, True, addr, width) if load \
                else self._mgba_store(pc, True, addr, width)
            cost = base + data + self._mgba_delta(pc, 4)
            if load and rd == 15:
                cost += self._mgba_write_pc(self.regs.r[15] & 0xFFFFFFFC, 4)
            return max(1, cost)
        if (instr & 0x0E000F90) == 0x00000090:      # SWP / SWPB
            addr = self.regs.r[(instr >> 16) & 0xF]
            width = 1 if (instr >> 22) & 1 else 4
            return max(1, base + self._mgba_data(pc, True, addr, width)
                       + self._mgba_store(pc, True, addr, width))
        if (instr >> 26) & 0b11 == 0:               # data processing
            rd = (instr >> 12) & 0xF
            cost = base
            if not ((instr >> 25) & 1) and (instr >> 4) & 1:
                cost += 1
            if rd == 15:
                cost += self._mgba_write_pc(self.regs.r[15] & 0xFFFFFFFC, 4)
            return max(1, cost)
        return max(1, base)

    def _thumb_cycles_mgba(self, instr):
        pc = self.regs.r[15] & 0xFFFFFFFE
        base = self._mgba_fetch(pc, 2)
        op = (instr >> 11) & 0x1F
        delta = self._mgba_delta(pc, 2)
        if op >= 0b11100:                           # B / BL / BLX
            if op == 0b11101:
                target = (self.regs.r[14] + ((instr & 0x7FF) << 1)) & 0xFFFFFFFE
                return base + self._mgba_write_pc(target, 2)
            if op == 0b11110:
                second = self.bus.read16((pc + 2) & 0xFFFFFFFE)
                boff = ((instr & 0x7FF) << 12) | ((second & 0x7FF) << 1)
                if boff & 0x400000:
                    boff -= 0x800000
                target = (pc + 4 + boff) & 0xFFFFFFFE
                return base + self._mgba_write_pc(target, 2)
            if op == 0b11111:
                target = (self.regs.r[14] + ((instr & 0x7FF) << 1)) & 0xFFFFFFFE
                return base + self._mgba_write_pc(target, 2)
            off11 = instr & 0x7FF
            if off11 & 0x400:
                off11 -= 0x800
            target = (pc + 4 + (off11 << 1)) & 0xFFFFFFFF
            return base + self._mgba_write_pc(target, 2)
        if op == 0b11011 and (instr >> 8) & 0xF == 0xF:   # SWI
            return base + self._mgba_swi_cycles(instr & 0xFF, pc, False)
        if (instr & 0xFC00) == 0x4400:              # hi-reg / BX
            op2 = (instr >> 8) & 0x3
            rd = (((instr >> 7) & 1) << 3) | (instr & 0x7)
            if op2 == 0b11 or rd == 15:
                target = self.regs.r[(instr >> 3) & 0xF]
                width = 2 if target & 1 else 4
                return base + self._mgba_write_pc(target & 0xFFFFFFFE, width)
            return base
        if op in (0b11010, 0b11011):                # 條件分支
            if conditions.passed((instr >> 8) & 0xF, self.regs.cpsr):
                off8 = instr & 0xFF
                if off8 & 0x80:
                    off8 -= 0x100
                target = (pc + 4 + (off8 << 1)) & 0xFFFFFFFF
                return base + self._mgba_write_pc(target, 2)
            return base
        if op == 0b10111 or (op == 0b10110 and (instr & 0x400)):
            count = bin(instr & 0xFF).count("1") + (1 if (instr >> 8) & 1 else 0)
            sp = self.regs.r[13]
            if op == 0b10110:                       # PUSH
                return max(1, base + delta + self._mgba_multiple_cost(
                    pc, False, (sp - 4 * count) & 0xFFFFFFFC, count, False))
            cost = base + delta + self._mgba_multiple_cost(pc, False, sp & 0xFFFFFFFC, count, True)
            if (instr >> 8) & 1:
                cost += self._mgba_write_pc(self.regs.r[15] & 0xFFFFFFFE, 2)
            return max(1, cost)
        if op in (0b11000, 0b11001):                # STMIA / LDMIA
            count = bin(instr & 0xFF).count("1") or 1
            rb = self.regs.r[(instr >> 8) & 7] & 0xFFFFFFFC
            load = bool((instr >> 11) & 1)
            cost = base + delta + self._mgba_multiple_cost(pc, False, rb, count, load)
            if load and (instr & 0xFF) == 0:
                cost += self._mgba_write_pc(self.regs.r[15] & 0xFFFFFFFE, 2)
            return max(1, cost)
        if op == 0b01000:                           # Format 4 ALU
            alu = (instr >> 6) & 0xF
            if alu == 0b1101:
                rs = self.regs.r[instr & 0x7]
                return max(1, base + self._mgba_stall(pc, False, self._mgba_mul_wait(rs)) + delta)
            if alu in (0b0010, 0b0011, 0b0100, 0b0111):
                return max(1, base + 1)
            return base
        if op in (0b01001, 0b01011, 0b01101, 0b01111, 0b10001, 0b10011):
            if op == 0b01001:
                addr = ((pc + 4) & 0xFFFFFFFC) + ((instr & 0xFF) << 2)
                width = 4
            elif op == 0b01011:
                addr = self.regs.r[(instr >> 3) & 7] + self.regs.r[(instr >> 6) & 7]
                if (instr >> 10) & 1:
                    width = 2 if (instr >> 9) & 1 else 1
                else:
                    width = 2 if (instr >> 9) & 1 else 4
            elif op == 0b01101:
                addr = self.regs.r[(instr >> 3) & 7] + ((instr >> 6) & 0x1F) * 4
                width = 4
            elif op == 0b01111:
                addr = self.regs.r[(instr >> 3) & 7] + ((instr >> 6) & 0x1F)
                width = 1
            elif op == 0b10001:
                addr = self.regs.r[(instr >> 3) & 7] + ((instr >> 6) & 0x1F) * 2
                width = 2
            else:
                addr = self.regs.r[13] + ((instr & 0xFF) << 2)
                width = 4
            return max(1, base + self._mgba_data(pc, False, addr & 0xFFFFFFFF, width) + delta)
        if op in (0b01010, 0b01100, 0b01110, 0b10000, 0b10010):
            if op == 0b01010:
                addr = self.regs.r[(instr >> 3) & 7] + self.regs.r[(instr >> 6) & 7]
                width = 2 if (instr >> 9) & 1 else 4
            elif op == 0b01100:
                addr = self.regs.r[(instr >> 3) & 7] + ((instr >> 6) & 0x1F) * 4
                width = 4
            elif op == 0b01110:
                addr = self.regs.r[(instr >> 3) & 7] + ((instr >> 6) & 0x1F)
                width = 1
            elif op == 0b10000:
                addr = self.regs.r[(instr >> 3) & 7] + ((instr >> 6) & 0x1F) * 2
                width = 2
            else:
                addr = self.regs.r[13] + ((instr & 0xFF) << 2)
                width = 4
            return max(1, base + self._mgba_store(pc, False, addr & 0xFFFFFFFF, width) + delta)
        return max(1, base)

    def _arm_cycles(self, instr):
        """對外：計算週期 + 設定下一個抓取嘅循序性（NBAs pipe.access）"""
        if self.bus.mgba_timing and not self.bus.functional:
            return self._arm_cycles_mgba(instr)
        c = self._arm_cycles_calc(instr)
        self._set_fetch_seq(instr, False)
        return c

    def _set_fetch_seq(self, instr, thumb):
        """下一個抓取係非循序？load/store/LDM/STM/MUL/移位 → 係"""
        ls = False
        if thumb:
            if (instr & 0xFC00) == 0x4400:      # 高位暫存器/BX：Sequential
                self._nseq_fetch = False
                return
            op = (instr >> 11) & 0x1F
            if op == 0b01000:
                alu = (instr >> 6) & 0xF
                ls = alu in (0b1101, 0b0010, 0b0011, 0b0100, 0b0111)
            elif op in (0b01001, 0b01011, 0b01101, 0b01111, 0b10001, 0b10011,
                        0b01010, 0b01100, 0b01110, 0b10000, 0b10010,
                        0b11000, 0b11001):
                ls = True
            elif op == 0b10111 or (op == 0b10110 and (instr & 0x400)):
                ls = True
        else:
            if (instr & 0x0FFFFFF0) == 0x012FFF10 or \
               (instr & 0x0FFFFFF0) == 0x012FFF30:  # BX/BLX：Sequential
                self._nseq_fetch = False
                return
            if (instr >> 25) & 0b111 == 0b100:
                ls = True
            elif (instr >> 26) & 0b11 == 0b01:
                ls = True
            elif (instr & 0x0E000F90) == 0x00000090:
                ls = True
            elif (instr & 0x0FC000F0) == 0x00000090 or \
                 (instr & 0x0F8000F0) == 0x00800090:
                ls = True
            elif (instr >> 25) & 0b111 == 0 and \
                 (instr >> 4) & 0xF in (0b1011, 0b1101, 0b1111):
                ls = True
            elif (instr >> 26) & 0b11 == 0:
                ls = bool((not (instr >> 25) & 1) and (instr >> 4) & 1)
        self._nseq_fetch = ls

    def _arm_cycles_calc(self, instr):
        """ARM 指令週期（區域感知）：抓取用 _fetch、資料用 bus.access_cost"""
        pc = self.regs.r[15] & 0xFFFFFFFC
        if (instr >> 25) & 0b111 == 0b101:          # B / BL：fetch + 目標重填（N）
            off24 = instr & 0xFFFFFF
            if off24 & 0x800000:
                off24 -= 0x1000000
            target = (pc + 8 + (off24 << 2)) & 0xFFFFFFFF
            return self._fetch(pc, 4, False) + self.bus.access_cost(target, 4, 0)
        if (instr >> 24) & 0xF == 0xF:              # SWI：2S + 1N（BIOS 向量）
            return 2 * self._fetch(pc, 4, False) + 1
        if (instr & 0x0FFFFFF0) == 0x012FFF10:      # BX：fetch + 目標重填（N）
            return self._fetch(pc, 4, False) + \
                   self.bus.access_cost(self.regs.r[instr & 0xF] & 0xFFFFFFFC, 4, 0)
        if (instr & 0x0FFFFFF0) == 0x012FFF30:      # BLX：ARMv5+，GBA 屬未定義
            return 3 * self._fetch(pc, 4, False) + self.bus.access_cost(pc, 4, 0)
        if (instr & 0x0FB0F000) == 0x0120F000 or \
           (instr & 0x0FB0F000) == 0x0320F000:      # MSR：1S
            return self._fetch(pc, 4, False)
        if (instr & 0x0FFF0FFF) == 0x010F0000 or \
           (instr & 0x0FFF0FFF) == 0x014F0000:      # MRS：1S
            return self._fetch(pc, 4, False)
        if (instr >> 25) & 0b111 == 0b100:          # LDM/STM
            n_regs = bin(instr & 0xFFFF).count("1") or 1
            rn = self.regs.r[(instr >> 16) & 0xF] & 0xFFFFFFFC
            if (instr >> 20) & 1:                   # LDM
                # LDM 每個第 1 個之後嘅 unit +1（同 core.pyx；128kb-boundary 實測）
                if (instr >> 15) & 1:               # LDM pc：(n+1)S + 2N + 1I
                    return self._fetch(pc, 4, True) + self._units_cost(rn, n_regs, 4) \
                           + (n_regs - 1) + 2 + self.bus.access_cost(rn, 4, 0)
                return self._fetch(pc, 4, True) + self._units_cost(rn, n_regs, 4) \
                       + (n_regs - 1) + 1
            return self._fetch(pc, 4, True) + self._units_cost(rn, n_regs, 4) \
                   + self.bus.access_cost(rn, 4, 0)      # STM：(n-1)S + 2N
        if (instr >> 25) & 0b111 == 0b011 and (instr >> 4) & 1:
            return 3 * self._fetch(pc, 4, False) + self.bus.access_cost(pc, 4, 0)
        if (instr >> 26) & 0b11 == 0b01:            # LDR/STR（字/位元組）
            rd = (instr >> 12) & 0xF
            addr = self._arm_addr(instr)
            if (instr >> 20) & 1:                   # LDR：1S + 1N + 1I
                if (instr >> 22) & 1:               # LDRB
                    c = self._fetch(pc, 4, True) + self.bus.access_cost(addr, 1, 0) + 1
                else:
                    c = self._fetch(pc, 4, True) + self.bus.access_cost(addr, 4, 0) + 1
                if rd == 15:
                    c += self._fetch(pc, 4, False) + self.bus.access_cost(pc, 4, 0)
                return c
            if (instr >> 22) & 1:                   # STRB：抓取 + 寫入
                return self._fetch(pc, 4, True) + self.bus.access_cost(addr, 1, 0)
            return self._fetch(pc, 4, True) + self.bus.access_cost(addr, 4, 0) \
                   + (1 if _io_word_extra(addr) else 0)   # STR 字（IO 兩 beat +1）
        if (instr & 0x0F8000F0) == 0x00800090:     # UMULL/MLAL/SMULL/SMLAL
            rs = self.regs.r[(instr >> 8) & 0xF]
            c = self._fetch(pc, 4, True) + self._mul_m(rs, signed=bool((instr >> 22) & 1))
            c += 2 if (instr >> 21) & 1 else 1      # 累加(A)：+2I；無累加：+1I
            return c
        if (instr & 0x0FC000F0) == 0x00000090:      # MUL/MLA：1S + mI
            rs = self.regs.r[(instr >> 8) & 0xF]
            c = self._fetch(pc, 4, True) + self._mul_m(rs)
            if (instr >> 21) & 1:                   # MLA 累加 +1I
                c += 1
            return c
        if (instr >> 4) & 0xF in (0b1011, 0b1101, 0b1111):  # LDRH/STRH/LDRSB/LDRSH
            addr = self._arm_addr_h(instr)
            if (instr >> 20) & 1:
                if (instr >> 4) & 0xF == 0b1101:    # LDRSB
                    c = self._fetch(pc, 4, True) + self.bus.access_cost(addr, 1, 0) + 1
                else:                               # LDRH / LDRSH
                    c = self._fetch(pc, 4, True) + self.bus.access_cost(addr, 2, 0) + 1
                if ((instr >> 12) & 0xF) == 15:
                    c += self._fetch(pc, 4, False) + self.bus.access_cost(pc, 4, 0)
                return c
            return self._fetch(pc, 4, True) + self.bus.access_cost(addr, 2, 0)   # STRH
        if (instr & 0x0E000F90) == 0x00000090:      # SWP：1S + 2N + 1I
            addr = (self.regs.r[(instr >> 16) & 0xF] + self.regs.r[instr & 0xF]) & 0xFFFFFFFF
            return self._fetch(pc, 4, True) + 2 * self.bus.access_cost(addr, 4, 0) + 1
        if (instr >> 26) & 0b11 == 0:               # 資料處理：(1+p)S + rI + pN
            rd = (instr >> 12) & 0xF
            if (not (instr >> 25) & 1) and (instr >> 4) & 1:
                c = self._fetch(pc, 4, True) + 1    # 暫存器移位 +1I
            else:
                c = self._fetch(pc, 4, False)
            if rd == 15:
                c += self._fetch(pc, 4, False) + self.bus.access_cost(pc, 4, 0)
            return c
        if (instr & 0x0F000000) == 0x0E000000 or \
           (instr >> 25) & 0b111 == 0b110:          # 協處理器（GBA 無）→ 未定義
            return 3 * self._fetch(pc, 4, False) + self.bus.access_cost(pc, 4, 0)
        return self._fetch(pc, 4, False)

    def _thumb_cycles(self, instr):
        """對外：計算週期 + 設定下一個抓取嘅循序性（NBAs pipe.access）"""
        if self.bus.mgba_timing and not self.bus.functional:
            return self._thumb_cycles_mgba(instr)
        c = self._thumb_cycles_calc(instr)
        self._set_fetch_seq(instr, True)
        return c

    def _thumb_cycles_calc(self, instr):
        """Thumb 指令週期（區域感知；同 core.pyx）"""
        pc = self.regs.r[15]
        op = (instr >> 11) & 0x1F
        if op >= 0b11100:                           # B / BL
            if op == 0b11101:                       # BLX 區：ARMv4T 未定義
                return 3 * self._fetch(pc, 2, False) + self.bus.access_cost(pc, 2, 0)
            if op == 0b11110:                       # BL 上半（執行器一次過做埋下半）
                second = self.bus.read16((pc + 2) & 0xFFFFFFFE)
                boff = ((instr & 0x7FF) << 12) | ((second & 0x7FF) << 1)
                if boff & 0x400000:
                    boff -= 0x800000
                target = (pc + 4 + boff) & 0xFFFFFFFE
                return 2 * self._fetch(pc, 2, False) + self.bus.access_cost(target, 2, 0)
            if op == 0b11111:                       # BL 下半（劈開獨立執行）：fetch + 重填
                target = (self.regs.r[14] + ((instr & 0x7FF) << 1)) & 0xFFFFFFFF
                return self._fetch(pc, 2, False) + self.bus.access_cost(target, 2, 0)
            off11 = instr & 0x7FF                   # 無條件 B
            if off11 & 0x400:
                off11 -= 0x800
            target = (pc + 4 + (off11 << 1)) & 0xFFFFFFFF
            return self._fetch(pc, 2, False) + self.bus.access_cost(target, 2, 0)
        if op == 0b11011 and (instr >> 8) & 0xF == 0xF:  # SWI：2S + 1N
            return 2 * self._fetch(pc, 2, False) + 1
        if (instr & 0xFC00) == 0x4400:              # 高位暫存器 / BX
            op2 = (instr >> 8) & 0x3
            rd = (((instr >> 7) & 1) << 3) | (instr & 0x7)
            if op2 == 0b11 or rd == 15:             # BX / MOV pc / ADD pc：fetch + 重填
                target = self.regs.r[(instr >> 3) & 0xF] & 0xFFFFFFFE
                c = self._fetch(pc, 2, False) + self.bus.access_cost(target, 2, 0)
                if (target >> 24) >= 0x08 and (target >> 24) <= 0x0D:
                    c += self.bus.access_cost((target + 2) & 0xFFFFFFFE, 2, 1)
                return c
            return self._fetch(pc, 2, False)        # 其餘 hi-reg：1S
        if op in (0b11010, 0b11011):                # 條件分支：成功 fetch+N、失敗 1S
            if conditions.passed((instr >> 8) & 0xF, self.regs.cpsr):
                off8 = instr & 0xFF
                if off8 & 0x80:
                    off8 -= 0x100
                target = (pc + 4 + (off8 << 1)) & 0xFFFFFFFF
                return self._fetch(pc, 2, False) + self.bus.access_cost(target, 2, 0)
            return self._fetch(pc, 2, False)
        if op == 0b10111 or (op == 0b10110 and (instr & 0x400)):   # PUSH/POP（0xB0xx ADD/SUB SP 除外）
            n_regs = bin(instr & 0xFF).count("1") + (1 if (instr >> 8) & 1 else 0)
            sp = self.regs.r[13]
            if op == 0b10110:                       # PUSH：(n-1)S + 2N（寫 sp 之下）
                c = (sp - 4 * n_regs) & 0xFFFFFFFF
                if n_regs == 0:                     # PUSH {}：真機 4 cycles
                    return self._fetch(pc, 2, True) + 3  # （thumb/Push_no_regs）
                return self._fetch(pc, 2, True) + self._units_cost(c, n_regs, 4) \
                       + self.bus.access_cost(c, 4, 0)
            if (instr >> 8) & 1:                    # POP pc：(n+1)S + 2N + 1I
                return self._fetch(pc, 2, True) + self._units_cost(sp, n_regs, 4) \
                       + (n_regs - 1) + 2 + self.bus.access_cost(sp, 2, 0)
            if n_regs == 0:                         # POP {}：真機 14 cycles
                return self._fetch(pc, 2, True) + 13  # （thumb/Pop_no_regs）
            return self._fetch(pc, 2, True) + self._units_cost(sp, n_regs, 4) \
                   + (n_regs - 1) + 1               # POP（同 LDM +1/unit）
        if op in (0b11000, 0b11001):                # STMIA / LDMIA
            n_regs = bin(instr & 0xFF).count("1") or 1
            rb = self.regs.r[(instr >> 8) & 7] & 0xFFFFFFFC
            if (instr >> 11) & 1 == 0:              # STMIA：(n-1)S + 2N
                return self._fetch(pc, 2, True) + self._units_cost(rb, n_regs, 4) \
                       + self.bus.access_cost(rb, 4, 0)
            return self._fetch(pc, 2, True) + self._units_cost(rb, n_regs, 4) \
                   + (n_regs - 1) + 1               # LDMIA（同 LDM +1/unit）
        if op == 0b01000:                           # Format 4 ALU
            alu = (instr >> 6) & 0xF
            if alu == 0b1101:                       # MUL：1S + mI
                rs = self.regs.r[(instr >> 3) & 0x7]
                return self._fetch(pc, 2, True) + self._mul_m(rs)
            if alu in (0b0010, 0b0011, 0b0100, 0b0111):   # 暫存器移位：1S + 1I
                return self._fetch(pc, 2, True) + 1
            return self._fetch(pc, 2, False)        # 其餘 ALU：1S
        if op in (0b01001, 0b01011, 0b01101, 0b01111, 0b10001, 0b10011):
            if op == 0b01001:                       # LDR 字面值：[pc,#imm8*4]
                addr = ((pc + 4) & 0xFFFFFFFC) + ((instr & 0xFF) << 2)
                width = 4
            elif op == 0b01011:                     # [Rb,Ro]：字/LDRH/LDSB/LDSH
                addr = self.regs.r[(instr >> 3) & 7] + self.regs.r[(instr >> 6) & 7]
                if (instr >> 10) & 1:
                    width = 2 if (instr >> 9) & 1 else 1
                else:
                    width = 2 if (instr >> 9) & 1 else 4
            elif op == 0b01101:                     # [Rb,#imm5*4] 字
                addr = self.regs.r[(instr >> 3) & 7] + ((instr >> 6) & 0x1F) * 4
                width = 4
            elif op == 0b01111:                     # [Rb,#imm5] 位元組
                addr = self.regs.r[(instr >> 3) & 7] + ((instr >> 6) & 0x1F)
                width = 1
            elif op == 0b10001:                     # [Rb,#imm5*2] 半字
                addr = self.regs.r[(instr >> 3) & 7] + ((instr >> 6) & 0x1F) * 2
                width = 2
            else:                                   # 0b10011：LDR [SP,#imm8*4]
                addr = self.regs.r[13] + ((instr & 0xFF) << 2)
                width = 4
            addr &= 0xFFFFFFFF
            return self._fetch(pc, 2, True) + self.bus.access_cost(addr, width, 0) + 1
        if op in (0b01010, 0b01100, 0b01110, 0b10000, 0b10010):
            if op == 0b01010:                       # [Rb,Ro]：字/STRH
                addr = self.regs.r[(instr >> 3) & 7] + self.regs.r[(instr >> 6) & 7]
                width = 2 if (instr >> 9) & 1 else 4
            elif op == 0b01100:                     # [Rb,#imm5*4] 字
                addr = self.regs.r[(instr >> 3) & 7] + ((instr >> 6) & 0x1F) * 4
                width = 4
            elif op == 0b01110:                     # [Rb,#imm5] 位元組
                addr = self.regs.r[(instr >> 3) & 7] + ((instr >> 6) & 0x1F)
                width = 1
            elif op == 0b10000:                     # [Rb,#imm5*2] 半字
                addr = self.regs.r[(instr >> 3) & 7] + ((instr >> 6) & 0x1F) * 2
                width = 2
            else:                                   # 0b10010：STR [SP,#imm8*4]
                addr = self.regs.r[13] + ((instr & 0xFF) << 2)
                width = 4
            addr &= 0xFFFFFFFF
            return self._fetch(pc, 2, True) + self.bus.access_cost(addr, width, 0) \
                   + (1 if width == 4 and _io_word_extra(addr) else 0)   # STR 字（IO +1）
        return self._fetch(pc, 2, False)
