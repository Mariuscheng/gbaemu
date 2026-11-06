class Registers:
    def __init__(self):
        self.r = [0] * 16
        self.cpsr = 0x1F          # 開機後 System 模式

        # 跳過 BIOS 的初始值
        self.r[13] = 0x03007F00   # SP
        self.r[14] = 0x08000000   # LR
        self.r[15] = 0x08000000   # PC

        # 分組暫存器：每個模式有獨立的 [sp, lr, spsr]
        # 模式代碼：0x11 FIQ、0x12 IRQ、0x13 SVC、0x17 ABT、0x1B UND、0x1F SYS/USR
        self.banks = {m: [0, 0, 0] for m in (0x11, 0x12, 0x13, 0x17, 0x1B, 0x1F)}

        # FIQ 額外分組 R8–R12（GBATEK Register Set）
        # 非 FIQ：r[8:13] = User；fiq_r8_12 = FIQ bank
        # 進入 FIQ：把 User 存進 usr_r8_12，載入 fiq_r8_12
        self.fiq_r8_12 = [0, 0, 0, 0, 0]
        self.usr_r8_12 = [0, 0, 0, 0, 0]

        # 目前「分組視角」的模式（與 CPSR 分離：
        # switch_mode 先換 bank，呼叫端再寫 CPSR）
        self.bank_mode = 0x1F

    def mode(self):
        """目前 CPU 模式（CPSR 低 5 bit）；USER(0x10) 與 SYS(0x1F) 共享暫存器
        ARM7TDMI 的 mode 0x00 等同 User mode（非特權、共享分組）"""
        m = self.cpsr & 0x1F
        return 0x1F if m in (0x00, 0x10) else m

    def _canon_mode(self, mode):
        if mode in (0x00, 0x10):
            return 0x1F
        if mode not in (0x11, 0x12, 0x13, 0x17, 0x1B, 0x1F):
            return 0x1F
        return mode

    def switch_mode(self, new_mode):
        """切換分組暫存器（依 bank_mode，不依賴 CPSR 是否已更新）。"""
        new_mode = self._canon_mode(new_mode)
        old = self.bank_mode
        if old == new_mode:
            return

        self.banks[old] = [self.r[13], self.r[14], self.banks[old][2]]

        if old == 0x11 and new_mode != 0x11:
            self.fiq_r8_12 = list(self.r[8:13])
            self.r[8:13] = list(self.usr_r8_12)
        elif old != 0x11 and new_mode == 0x11:
            self.usr_r8_12 = list(self.r[8:13])
            self.r[8:13] = list(self.fiq_r8_12)

        self.r[13] = self.banks[new_mode][0]
        self.r[14] = self.banks[new_mode][1]
        self.bank_mode = new_mode

    def spsr_get(self):
        """讀目前分組模式的 SPSR"""
        return self.banks[self.bank_mode][2]

    def spsr_set(self, v):
        """寫目前分組模式的 SPSR"""
        self.banks[self.bank_mode][2] = v

    def user_get(self, reg):
        """讀 User/System 分組的暫存器（LDM/STM S=1 用）"""
        if reg < 8 or reg == 15:
            return self.r[reg]
        if 8 <= reg <= 12:
            if self.bank_mode == 0x11:
                return self.usr_r8_12[reg - 8]
            return self.r[reg]
        if self.bank_mode == 0x1F:
            return self.r[reg]
        return self.banks[0x1F][reg - 13]

    def user_set(self, reg, value):
        """寫 User/System 分組的暫存器（LDM/STM S=1 用）"""
        value &= 0xFFFFFFFF
        if reg < 8:
            self.r[reg] = value
            return
        if reg == 15:
            self.pc = value
            return
        if 8 <= reg <= 12:
            if self.bank_mode == 0x11:
                self.usr_r8_12[reg - 8] = value
                # ARM7TDMI「LDM^ glitch」（test-rom/LDM ReadMe + LDM_ALU 實測）：
                # 寫 user 組時，值同時 OR 進當前 FIQ 組（永久性——所有 case 自洽）
                self.r[reg] |= value
            else:
                self.r[reg] = value
            return
        if self.bank_mode == 0x1F:
            self.r[reg] = value
        else:
            self.banks[0x1F][reg - 13] = value

    # 方便取用
    @property
    def sp(self): return self.r[13]

    @sp.setter
    def sp(self, v): self.r[13] = v

    @property
    def lr(self): return self.r[14]

    @lr.setter
    def lr(self, v): self.r[14] = v

    @property
    def pc(self): return self.r[15]

    @pc.setter
    def pc(self, v):
        # R15 永遠強制對齊（GBATEK）：ARM 清低 2 bit、Thumb 清低 1 bit
        self.r[15] = (v & 0xFFFFFFFE) if (self.cpsr & 0x20) else (v & 0xFFFFFFFC)

    # 旗標：放在 CPSR 的最高 4 個 bit（N=31, Z=30, C=29, V=28）
    def flag(self, n):
        return (self.cpsr >> n) & 1

    def set_flag(self, n, v):
        if v:
            self.cpsr |= (1 << n)
        else:
            self.cpsr &= ~(1 << n)

    @property
    def z(self): return (self.cpsr >> 30) & 1

    @z.setter
    def z(self, v):
        if v: self.cpsr |= (1 << 30)
        else: self.cpsr &= ~(1 << 30)
