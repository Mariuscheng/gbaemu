import logging

from .registers import Registers
from . import arm, thumb, conditions
from .bios_ref import BIOS

log = logging.getLogger("pygba")   # 診斷訊息預設靜音；logging.basicConfig(level=logging.INFO) 可開啟

def _io_word_extra(addr):
    """32-bit store 去 16-bit IO 裝置：多一個 beat（+1 cycle）——

    除 timer（0x100-0x10F）同 IRQ（0x200-0x2FF）寄存器區之外
    （同 core.pyx 完全一致，sync 測試把關）。"""
    return 0x04000000 <= addr < 0x040003FF and \
           not (0x04000100 <= addr < 0x04000110) and \
           not (0x04000200 <= addr < 0x04000300)

class CPU:
    def __init__(self, bus):
        self.bus = bus
        bus.cpu = self                     # 反向參考（HALTCNT 寫入觸發 Halt 用）
        self.bios = BIOS(bus)
        self.regs = Registers()
        self.halted = False                # Halt 狀態（SWI 04/05/06）
        self.wait_irq = 0                  # 等待的中斷旗標（0 = 任意中斷）
        self._irq_entered = False          # 本步是否進入了 IRQ（喚醒用）
        self._irq_wait = -1                # IRQ 線管線延遲（-1 = 未 arm；同 core.pyx）
        self._t_branch_taken = False       # Thumb 條件分支是否成功（週期用）
        self._nseq_fetch = False           # 下一個抓取非循序？（load/store 之後）

    def _open_bus_boundary(self, pc):
        """open bus 區下一個「真實記憶體」邊界（None = 不在 open bus 區）"""
        if 0x00004000 <= pc < 0x02000000:   return 0x02000000
        if 0x04000400 <= pc < 0x05000000:   return 0x05000000
        if 0x08800000 <= pc < 0x0A000000:   return 0x0A000000   # ROM 鏡像
        if 0x0E000000 <= pc < 0x10000000:   return 0x10000000   # SRAM 區（讀 0xFF=skip）
        if 0x10000000 <= pc <= 0xFFFFFFFF:  return 0x100000000  # 溢位 = 暖開機
        return None

    def _halt_batch(self):
        """halted 快轉批長度（同 core.pyx 完全一致，sync 測試把關）

        安全邊界：① PPU 線邊界（1006／1232）② 已預約 PPU IRQ 到點位
        ③ IRQ take 倒數（_irq_wait ≥ 0）；其他事件上限 64 cycles。
        """
        cyc = self.bus.ppu.cycle
        pos = cyc % 1232
        n = (1006 - pos) if pos < 1006 else (1232 - pos)
        for at in (self.bus._irqhb_at, self.bus._irqvb_at, self.bus._irqvc_at):
            if at:
                d = at - cyc
                if d < n:
                    n = 1 if d <= 0 else d
        w = self._irq_wait
        if w >= 0:
            ww = 1 if w == 0 else w
            if ww < n:
                n = ww
        # ④ timer 溢出邊界（近似：忽略 prescaler 相位，寧小勿大）——
        #    溢出會設 IF 並可能喚醒 halt；唔可以衝過溢出點（否則喚醒遲批次）
        tctl = self.bus.timers.control
        tcnt = self.bus.timers.counter
        for i in range(4):
            cv = tctl[i]
            if cv & 0x80 and not (cv & 0x04 and i > 0):
                m = cv & 0x03
                p = 1 if m == 0 else (64 if m == 1 else (256 if m == 2 else 1024))
                d2 = (0x10000 - tcnt[i]) * p
                if d2 < n:
                    n = 1 if d2 == 0 else d2
        if n > 64:
            n = 64
        return n

    def step(self):
        # 音效 FIFO DMA 成本：tick 內不可嵌套 _stall → 喺 CPU 邊界補扣
        # （fifo.gba t002：溢位請求 DMA 後 CPU 實際被停住；唔扣 → timer 讀值偏細）
        if self.bus.fifo_stall:
            fsc = self.bus.fifo_stall
            self.bus.fifo_stall = 0
            self.bus._stall(fsc)
        # HLE BIOS IRQ 回程 stub（真 BIOS 0x13C：LDMFD SP!,{R0-R3,R12,LR} + SUBS PC,LR,#4）
        # handler 以 bx lr 回到 0x13C（或直接 subs pc,lr,#4 到 0x138）→ 這裡完成收尾
        if (not self.bus.bios_present) and (self.regs.cpsr & 0x1F) == 0x12 \
           and self.regs.r[15] in (0x00000138, 0x0000013C):
            sp = self.regs.r[13]                 # 目前 IRQ 模式的活 SP
            for i, r in enumerate((0, 1, 2, 3, 12)):
                self.regs.r[r] = self.bus.read32(sp + i * 4)
            lr = self.bus.read32(sp + 20)
            self.regs.r[13] = sp + 24
            # 等價 SUBS PC,LR,#4：先還原 SPSR→CPSR（含分組），再設 PC
            new_cpsr = self.regs.spsr_get()
            self.regs.switch_mode(new_cpsr & 0x1F)
            self.regs.cpsr = new_cpsr
            self.regs.pc = lr - 4
            return
        if self.halted:
            # 立即喚醒快速路徑（同 core.pyx 一致）：進入 halt 時條件已滿足
            # （例如寫 HALTCNT 的一刻 IE&IF 已有交集——hw-test TIME 實測）
            # → 唔可以白等一個批次先檢查。次序同批次末端一致：不可服務
            # → 純喚醒；可服務 → 交 _check_irq 兩拍後 take。
            if not self.wait_irq:
                ie0 = self.bus.io[0x200] | (self.bus.io[0x201] << 8)
                if ie0 & (self.bus.io[0x202] | (self.bus.io[0x203] << 8)):
                    if not ((self.bus.io[0x208] & 1)
                            and not (self.regs.cpsr & 0x80)):
                        self.halted = False
                        self._irq_wait = -1
                        return
                    self.bus.tick(1)
                    self._check_irq(1)
                    if self._irq_entered:
                        self._irq_entered = False
                        self.halted = False
                        self._irq_wait = -1
                    return
            nb = self._halt_batch()        # 批次快轉（同 core.pyx 完全一致）
            self.bus.tick(nb)
            self._check_irq(nb)
            if self._irq_entered:          # HLE IRQ 進場 → 喚醒執行 handler
                self._irq_entered = False
                self.halted = False
                self._irq_wait = -1        # wake 後 IRQ 管線延遲重新 arm
                if self.wait_irq:          # IntrWait 的 BIOS RAM 旗標副本同步清除
                    self.bus.iwram[0x7FF8] &= ~(self.wait_irq & 0xFF)
                    self.bus.iwram[0x7FF9] &= ~((self.wait_irq >> 8) & 0xFF)
                return
            ram = self.bus.iwram[0x7FF8] | (self.bus.iwram[0x7FF9] << 8)
            if self.wait_irq:
                if ram & self.wait_irq:    # IntrWait：RAM 旗標到齊 → 喚醒並清除
                    self.halted = False
                    self._irq_wait = -1
                    self.bus.iwram[0x7FF8] &= ~(self.wait_irq & 0xFF)
                    self.bus.iwram[0x7FF9] &= ~((self.wait_irq >> 8) & 0xFF)
            else:
                ie = self.bus.io[0x200] | (self.bus.io[0x201] << 8)
                ifreg = self.bus.io[0x202] | (self.bus.io[0x203] << 8)
                # GBATEK Halt：IE & IF 有交集即喚醒（不看 IME 與 I 旗標）。
                # 真機次序：可服務（IME=1 且非 I 遮罩）時中斷係喺 halt
                # 入面即場進場（handler 先跑），唔可以純喚醒搶先跑後續碼
                # ——留返俾 _check_irq 兩拍後 take（同 core.pyx 一致）。
                if ie & ifreg:
                    if not ((self.bus.io[0x208] & 1)
                            and not (self.regs.cpsr & 0x80)):
                        self.halted = False
                        self._irq_wait = -1
            return
        # open bus 直線快轉：條件失敗的 skip 每條只前進 4 bytes
        if not (self.regs.cpsr & 0x20):
            pc0 = self.regs.r[15] & 0xFFFFFFFC
            bnd = self._open_bus_boundary(pc0)
            if bnd is not None:
                w = self.bus.read32(pc0)
                cond = (w >> 28) & 0xF
                if cond == 0xF or (cond != 0xE and not conditions.passed(cond, self.regs.cpsr)):
                    n = min(1024, (bnd - pc0) // 4)   # <1 條掃描線，不跨事件
                    if n > 0:
                        self.regs.pc = (pc0 + 4 * n) & 0xFFFFFFFF
                        # open bus 抓取 = 單次存取週期（區域感知）
                        self.bus.tick(n * self.bus.access_cost(pc0, 4, 0))
                        self._check_irq()
                        return
        if self.regs.r[15] == 0x00000000:   # 跳到 BIOS reset vector = 暖開機！
            # HLE（像 mGBA 跳過 BIOS）：直接回遊戲入口，不執行真 BIOS 開機碼
            log.info("!!! 暖開機（BX 0）→ HLE 直接回遊戲入口 0x08000000")
            self.regs.pc = 0x08000000
            self.regs.r[13] = 0x03007F00    # BIOS 會重置 sp
            self.regs.cpsr = 0x1F           # ARM 模式、system 模式、IRQ 關閉
        if self.regs.cpsr & 0x20:            # T bit = 1：Thumb 模式
            pc = self.regs.r[15]
            self.bus.cur_pc = pc             # DMA 匯流排視窗用（當前指令位址）
            if pc != self.bus.dma_window_pc:
                self.bus.dma_window_pc = -1  # 視窗只對緊接 DMA 觸發嘅下一條有效
            self.bus.pc_in_bios = pc < 0x4000
            d = self.bus.cartridge.data
            if 0x08000000 <= pc < 0x0A000000 and pc - 0x08000000 + 2 <= len(d):
                off = pc - 0x08000000
                instr = d[off] | (d[off + 1] << 8)   # ROM 快取（免呼叫 read16）
            else:
                instr = self.bus.read16(pc)
            a = (pc + 4) & 0xFFFFFFFC
            if 0x08000000 <= a < 0x0A000000 and a - 0x08000000 + 4 <= len(d):
                off = a - 0x08000000
                self.bus.open_bus = (d[off] | (d[off + 1] << 8)
                                     | (d[off + 2] << 16) | (d[off + 3] << 24))
            else:
                self.bus.open_bus = self.bus.read32(a)  # 管線預抓
            if pc < 0x4000:
                self.bus.bios_prefetch = self.bus.read32((pc + 4) & 0xFFFFFFFC)
            cycles = self._thumb_cycles(instr)   # 要先算（LDM 基底、SP 等未改先）
            thumb.execute(self, instr)
        else:
            pc = self.regs.r[15] & 0xFFFFFFFC  # ARM 抓取永遠對齊 4 bytes
            self.regs.pc = pc
            self.bus.cur_pc = pc                 # DMA 匯流排視窗用（當前指令位址）
            if pc != self.bus.dma_window_pc:
                self.bus.dma_window_pc = -1      # 視窗只對緊接 DMA 觸發嘅下一條有效
            self.bus.pc_in_bios = pc < 0x4000
            d = self.bus.cartridge.data
            if 0x08000000 <= pc < 0x0A000000 and pc - 0x08000000 + 4 <= len(d):
                off = pc - 0x08000000
                instr = (d[off] | (d[off + 1] << 8)
                         | (d[off + 2] << 16) | (d[off + 3] << 24))
            else:
                instr = self.bus.read32(pc)
            a = pc + 4
            if 0x08000000 <= a < 0x0A000000 and a - 0x08000000 + 4 <= len(d):
                off = a - 0x08000000
                self.bus.open_bus = (d[off] | (d[off + 1] << 8)
                                     | (d[off + 2] << 16) | (d[off + 3] << 24))
            else:
                self.bus.open_bus = self.bus.read32(a)   # 管線預抓下一字
            if pc < 0x4000:
                self.bus.bios_prefetch = self.bus.read32(pc + 8)  # BIOS 讀取保護用
            cond = (instr >> 28) & 0xF
            if cond == 0xF:                     # NV：ARM7TDMI 上永不執行（SWI 例外，見下）
                if (instr >> 24) & 0xF == 0xF:  # SWI
                    # 相容模式：cond=F 的 SWI 照常執行（嚴格 ARM7TDMI 應永不執行——
                    # 真 BIOS 亦不做條件檢查，此處維持現狀；若要嚴格模式可改回跳過）
                    cycles = self._arm_cycles(instr)
                    arm.execute(self, instr)
                else:                           # 其餘 cond=F：當 NOP 跳過（1S）
                    self.regs.pc = pc + 4
                    cycles = 1
            elif conditions.passed(cond, self.regs.cpsr):
                cycles = self._arm_cycles(instr)   # 週期要先算（乘法要讀原始 Rs）
                arm.execute(self, instr)
            else:
                self.regs.pc = pc + 4
                cycles = 1                     # 條件失敗 = 1S
        self.bus.tick(cycles)                 # 推進 PPU / 計時器 / DMA
        self._check_irq(cycles)

    # ── 指令週期（區域感知：抓取同資料都用 bus.access_cost；GBATEK S/N/I 結構）──

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

    def _arm_cycles(self, instr):
        """對外：計算週期 + 設定下一個抓取嘅循序性（NBAs pipe.access）"""
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
                 (instr >> 23) & 0x1F == 0b00001:
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
        if (instr >> 23) & 0x1F == 0b00001:         # UMULL/MLAL/SMULL/SMLAL
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

    def enter_exception(self, mode, vector, lr_offset, set_f=False):
        """GBATEK：進入例外——存 CPSR→SPSR、切模式、LR=PC+lr_offset、
        T=0（ARM）、I=1、可選 F=1，再跳向量。"""
        old_cpsr = self.regs.cpsr
        self.regs.switch_mode(mode)
        self.regs.banks[mode][2] = old_cpsr          # SPSR_<mode>
        self.regs.r[14] = (self.regs.pc + lr_offset) & 0xFFFFFFFF
        new = (old_cpsr & ~(0x1F | 0x20 | 0x80)) | 0x80 | mode
        if set_f:
            new |= 0x40
        else:
            new |= (old_cpsr & 0x40)                 # F 保留（除非 Reset/FIQ）
        self.regs.cpsr = new
        self.regs.pc = vector

    def swi(self, comment):
        """SWI：先進 SVC 例外；有真 BIOS 走向量 0x08，否則 HLE 派發後返回。
        LR = 下條指令：ARM 為 PC+4，Thumb 為 PC+2（進場時 PC 仍指向 SWI）。"""
        lr_off = 2 if (self.regs.cpsr & 0x20) else 4
        self.enter_exception(0x13, 0x00000008, lr_offset=lr_off)
        if self.bus.bios_present:
            return                                   # 真 BIOS 從 0x08 執行
        # HLE：在 SVC 狀態派發，再等價 MOVS PC,R14
        self.bios.call(self, comment)
        new_cpsr = self.regs.banks[0x13][2]
        lr = self.regs.r[14]
        self.regs.switch_mode(new_cpsr & 0x1F)
        self.regs.cpsr = new_cpsr
        self.regs.pc = lr

    def _check_irq(self, cycles=1):
        """檢查中斷：IME=1 且 IE&IF 有交集且 I 旗標未遮罩 → 進 IRQ 模式

        IRQ 線有管線延遲（NBAs：Raise → +1 IF 暫存器 → +2 irq_line）：
        可用後要 +2 cycles 先到 CPU，而且要等到「下一條指令完結」才進場
        （同 core.pyx 完全一致，sync 測試把關）。"""
        self._irq_entered = False
        if not (self.bus.io[0x208] & 1):     # IME
            self._irq_wait = -1
            return
        ie = self.bus.io[0x200] | (self.bus.io[0x201] << 8)
        ifreg = self.bus.io[0x202] | (self.bus.io[0x203] << 8)
        if not (ie & ifreg):
            self._irq_wait = -1
            return
        if self.regs.cpsr & 0x80:            # I 旗標已遮罩中斷
            self._irq_wait = -1
            return
        if self._irq_wait < 0:
            self._irq_wait = 2               # 剛可用：arm 管線延遲
            return
        self._irq_wait -= cycles
        if self._irq_wait > 0:
            return                           # 未到 → 下一條指令再試
        self._irq_wait = -1
        # IRQ：R14_irq = PC+4（PC 已是下一條指令位址）
        # NBAs SignalIRQ：對被中斷嘅下一條指令做一次丟棄式抓取（真機時序）
        self.bus._stall(self.bus.access_cost(self.regs.r[15],
                                             2 if (self.regs.cpsr & 0x20) else 4, 0))
        self.enter_exception(0x12, 0x00000018, lr_offset=4)
        self._irq_entered = True
        if not self.bus.bios_present:
            # HLE 真 BIOS 的 IRQ stub（0x128~0x134）：
            #   STMFD SP!,{R0-R3,R12,LR} → 存 6 個暫存器
            #   ADD LR,PC,#0 → LR = 0x138（handler 的 bx lr 回到 BIOS return stub）
            #   LDR PC,[03007FFC]  → 跳遊戲自己的 handler
            sp = self.regs.r[13] - 24
            self.regs.r[13] = sp
            self.regs.banks[0x12][0] = sp
            for i, r in enumerate((0, 1, 2, 3, 12)):
                self.bus.write32(sp + i * 4, self.regs.r[r])
            self.bus.write32(sp + 20, self.regs.r[14])   # 原 lr（pc+4）
            self.regs.r[14] = 0x00000138                  # BIOS 回程 stub 位址（GBATEK）
            self.regs.pc = self.bus.read32(0x03007FFC)   # 遊戲 IRQ handler

    def reset(self):
        self.regs = Registers()               # RL 每局都靠它
        self.halted = False
        self.wait_irq = 0