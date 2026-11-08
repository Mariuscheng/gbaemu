"""ARM7TDMI 內部暫存器狀態與 banking。

規格 3.2／5.5：內部可變狀態（snapshot 用）與對外唯讀 ``CPUState`` 分開建模。

# GBATEK: ARM CPU Register Set - CPSR 的 mode(0x10-0x1F)/T(bit5)/F(bit6)/I(bit7)，
# 各 mode 專屬的 banked r13/r14，以及 FIQ 額外的 r8-r12。

Banking 規則（與 ``gba_cpu/registers.py`` 的實機驗證語意一致）：

* User(0x10) 與 System(0x1F) 共用同一組暫存器。
* 其餘五個例外模式各有自己的 r13/r14/spsr。
* FIQ 額外擁有 r8-r12 的 bank。
* ``bank_mode`` 與 CPSR 分離：``switch_mode()`` 先換 bank，呼叫端再寫 CPSR。
"""

from __future__ import annotations

from dataclasses import dataclass, field

MODE_USR = 0x10
MODE_FIQ = 0x11
MODE_IRQ = 0x12
MODE_SVC = 0x13
MODE_ABT = 0x17
MODE_UND = 0x1B
MODE_SYS = 0x1F
MODE_MASK = 0x1F

CPSR_T = 1 << 5  # Thumb state
CPSR_F = 1 << 6  # FIQ disable
CPSR_I = 1 << 7  # IRQ disable

CPSR_N = 1 << 31
CPSR_Z = 1 << 30
CPSR_C = 1 << 29
CPSR_V = 1 << 28

BANKED_MODES = (MODE_FIQ, MODE_IRQ, MODE_SVC, MODE_ABT, MODE_UND, MODE_SYS)


def canonical_mode(mode: int) -> int:
    """把 CPSR 的 mode 位正規化：0x00/0x10 → System(0x1F)，未知值 → System。"""

    if mode in (0x00, MODE_USR):
        return MODE_SYS
    if mode not in BANKED_MODES:
        return MODE_SYS
    return mode


def mode_of(cpsr: int) -> int:
    """回傳 CPSR 的 mode 位（0x10-0x1F，不做事後正規化）。"""

    return cpsr & MODE_MASK


def is_thumb(cpsr: int) -> bool:
    return bool(cpsr & CPSR_T)


@dataclass(slots=True)
class Arm7CoreState:
    """CPU 核心的可變狀態；每個欄位都必須進入 snapshot payload。"""

    regs: list[int]  # r0-r15，index 0-15
    cpsr: int
    spsr: int
    banked: dict[int, tuple[int, int]]  # mode -> (r13, r14)
    banked_spsr: dict[int, int]
    pipeline: list[int]  # 內部 pipeline 暫存
    halted: bool  # HALT 狀態，等待中斷
    bank_mode: int = MODE_SYS  # 目前 banked 視角（可能領先 CPSR）
    fiq_r8_12: list[int] = field(default_factory=lambda: [0] * 5)
    usr_r8_12: list[int] = field(default_factory=lambda: [0] * 5)


def new_core_state() -> Arm7CoreState:
    """建立 power-on 的空白狀態（不含 BIOS 初始值）。"""

    return Arm7CoreState(
        regs=[0] * 16,
        cpsr=MODE_SYS,
        spsr=0,
        banked={},
        banked_spsr={},
        pipeline=[],
        halted=False,
    )


class RegisterFile:
    """``Arm7CoreState`` 的暫存器視角（banking、旗標、PC 對齊）。

    介面對應 ``gba_cpu.registers.Registers``，讓遷移後的 ARM/THUMB 解碼器可以
    直接沿用；狀態本身仍存在 :class:`Arm7CoreState`，供 snapshot 序列化。
    """

    def __init__(self, state: Arm7CoreState) -> None:
        self.state = state

    # -- 基本欄位 ---------------------------------------------------------
    @property
    def r(self) -> list[int]:
        return self.state.regs

    @property
    def cpsr(self) -> int:
        return self.state.cpsr

    @cpsr.setter
    def cpsr(self, value: int) -> None:
        self.state.cpsr = value & 0xFFFFFFFF

    # -- mode / banking ----------------------------------------------------
    def mode(self) -> int:
        """目前 CPU 模式；USER(0x10) 與 SYS(0x1F) 共用暫存器。"""

        return canonical_mode(self.state.cpsr & MODE_MASK)

    def switch_mode(self, new_mode: int) -> None:
        """切換 banked 暫存器（依 ``bank_mode``，不依賴 CPSR 是否已更新）。"""

        new_mode = canonical_mode(new_mode)
        old_mode = self.state.bank_mode
        if old_mode == new_mode:
            return

        regs = self.state.regs
        self.state.banked[old_mode] = (regs[13], regs[14])

        if old_mode == MODE_FIQ and new_mode != MODE_FIQ:
            self.state.fiq_r8_12 = list(regs[8:13])
            regs[8:13] = list(self.state.usr_r8_12)
        elif old_mode != MODE_FIQ and new_mode == MODE_FIQ:
            self.state.usr_r8_12 = list(regs[8:13])
            regs[8:13] = list(self.state.fiq_r8_12)

        sp, lr = self.state.banked.get(new_mode, (0, 0))
        regs[13] = sp
        regs[14] = lr
        self.state.bank_mode = new_mode
        self.state.spsr = self.state.banked_spsr.get(new_mode, 0)

    def spsr_get(self) -> int:
        """讀目前分組模式的 SPSR。"""

        return self.state.banked_spsr.get(self.state.bank_mode, 0)

    def spsr_set(self, value: int) -> None:
        """寫目前分組模式的 SPSR。"""

        self.state.banked_spsr[self.state.bank_mode] = value & 0xFFFFFFFF
        self.state.spsr = value & 0xFFFFFFFF

    def user_get(self, reg: int) -> int:
        """讀 User/System 分組的暫存器（LDM/STM 的 S=1 用）。"""

        if reg < 8 or reg == 15:
            return self.state.regs[reg]
        if 8 <= reg <= 12:
            if self.state.bank_mode == MODE_FIQ:
                return self.state.usr_r8_12[reg - 8]
            return self.state.regs[reg]
        if self.state.bank_mode == MODE_SYS:
            return self.state.regs[reg]
        return self.state.banked.get(MODE_SYS, (0, 0))[reg - 13]

    def user_set(self, reg: int, value: int) -> None:
        """寫 User/System 分組的暫存器（LDM/STM 的 S=1 用）。"""

        value &= 0xFFFFFFFF
        if reg < 8:
            self.state.regs[reg] = value
            return
        if reg == 15:
            self.pc = value
            return
        if 8 <= reg <= 12:
            if self.state.bank_mode == MODE_FIQ:
                self.state.usr_r8_12[reg - 8] = value
                # ARM7TDMI「LDM^ glitch」（test-rom/LDM 實測）：同時 OR 進 FIQ 組。
                self.state.regs[reg] |= value
            else:
                self.state.regs[reg] = value
            return
        if self.state.bank_mode == MODE_SYS:
            self.state.regs[reg] = value
        else:
            sp, lr = self.state.banked.get(MODE_SYS, (0, 0))
            if reg == 13:
                self.state.banked[MODE_SYS] = (value, lr)
            else:
                self.state.banked[MODE_SYS] = (sp, value)

    # -- 常用別名 ---------------------------------------------------------
    @property
    def bank_mode(self) -> int:
        return self.state.bank_mode

    @bank_mode.setter
    def bank_mode(self, value: int) -> None:
        self.state.bank_mode = canonical_mode(value)

    @property
    def fiq_r8_12(self) -> list[int]:
        return self.state.fiq_r8_12

    @fiq_r8_12.setter
    def fiq_r8_12(self, value: list[int]) -> None:
        self.state.fiq_r8_12 = list(value)

    @property
    def usr_r8_12(self) -> list[int]:
        return self.state.usr_r8_12

    @usr_r8_12.setter
    def usr_r8_12(self, value: list[int]) -> None:
        self.state.usr_r8_12 = list(value)

    @property
    def sp(self) -> int:
        return self.state.regs[13]

    @sp.setter
    def sp(self, value: int) -> None:
        self.state.regs[13] = value & 0xFFFFFFFF

    @property
    def lr(self) -> int:
        return self.state.regs[14]

    @lr.setter
    def lr(self, value: int) -> None:
        self.state.regs[14] = value & 0xFFFFFFFF

    @property
    def pc(self) -> int:
        return self.state.regs[15]

    @pc.setter
    def pc(self, value: int) -> None:
        # R15 永遠強制對齊（GBATEK）：ARM 清低 2 bit、Thumb 清低 1 bit。
        if self.state.cpsr & CPSR_T:
            self.state.regs[15] = value & 0xFFFFFFFE
        else:
            self.state.regs[15] = value & 0xFFFFFFFC

    @property
    def spsr(self) -> int:
        return self.spsr_get()

    @spsr.setter
    def spsr(self, value: int) -> None:
        self.spsr_set(value)

    # -- 旗標 -------------------------------------------------------------
    def flag(self, bit: int) -> int:
        return (self.state.cpsr >> bit) & 1

    def set_flag(self, bit: int, value: int | bool) -> None:
        if value:
            self.state.cpsr |= 1 << bit
        else:
            self.state.cpsr &= ~(1 << bit)

    @property
    def z(self) -> int:
        return (self.state.cpsr >> 30) & 1

    @z.setter
    def z(self, value: int) -> None:
        self.set_flag(30, value)


__all__ = [
    "MODE_USR",
    "MODE_FIQ",
    "MODE_IRQ",
    "MODE_SVC",
    "MODE_ABT",
    "MODE_UND",
    "MODE_SYS",
    "MODE_MASK",
    "CPSR_T",
    "CPSR_F",
    "CPSR_I",
    "CPSR_N",
    "CPSR_Z",
    "CPSR_C",
    "CPSR_V",
    "BANKED_MODES",
    "Arm7CoreState",
    "RegisterFile",
    "canonical_mode",
    "mode_of",
    "is_thumb",
    "new_core_state",
]
