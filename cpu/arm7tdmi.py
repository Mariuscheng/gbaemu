"""ARM7TDMI 核心：fetch / decode / execute / exception（Phase 2：真實週期）。

架構：``step()`` 抓取一條指令 → 計算週期（:class:`gbaemu.cpu.cycles.CycleModel`）
→ 交給 :mod:`gbaemu.cpu.arm` 或 :mod:`gbaemu.cpu.thumb` 執行 → 累加 cycle。
banked registers 由 :class:`gbaemu.cpu.registers.RegisterFile` 管理，狀態存在
:class:`~gbaemu.cpu.registers.Arm7CoreState`（snapshot 用）。

# GBATEK: ARM CPU Reference - ARM 32bit Instruction Set / ARM 16bit Instruction Set
# GBATEK: ARM CPU Register Set - CPSR T 位決定 ARM/THUMB、例外入口的 SPSR/LR
# GBATEK: ARM CPU Instruction Cycle Times - S/N/I 與 fetch/資料存取成本

週期語意依規格 §3.6：FUNCTIONAL 模式的每次存取固定 1 cycle；TIMED／TRACE
模式套用 §3.6.5 的 WAITCNT 與區塊成本。
"""

from __future__ import annotations

import os

import logging
import struct

from ..api_types import CPUState
from ..bus.access import (
    access_cycles,
    align_address,
    rotate_right_32,
    unaligned_word_rotate,
)
from ..hle.swi_table import SwiTable
from . import arm, conditions, thumb
from .cycles import CycleModel
from .registers import (
    CPSR_F,
    CPSR_I,
    CPSR_T,
    MODE_IRQ,
    MODE_MASK,
    MODE_SVC,
    MODE_SYS,
    Arm7CoreState,
    RegisterFile,
    is_thumb,
    mode_of,
    new_core_state,
)

logger = logging.getLogger("gbaemu.cpu.arm7tdmi")

_REGISTER_NAMES = {f"r{index}": index for index in range(16)}

# GBATEK: GBA I/O Map - IME/IE/IF（Phase 1 只讀 raw I/O；Phase 2 換成暫存器語意）
_REG_IME = 0x04000208
_REG_IE = 0x04000200
_REG_IF = 0x04000202


class CpuBus:
    """CPU 視角的匯流排：讀寫 + 未對齊語意。

    GBATEK: GBA Memory Map - Address Bus Width and CPU Read/Write Access Widths。
    匯流排本身先依寬度對齊（忽略 A1:A0／A0），旋轉與寫入位移統一在這一層完成，
    避免 bus 與 CPU 雙重旋轉（``TODO.md`` Open Question 12）。
    """

    def __init__(self, bus, *, functional: bool = True) -> None:
        self._bus = bus
        self.functional = functional  # FUNCTIONAL：每次存取固定 1 cycle
        self.after_dma = False  # DMA 後首個 CPU 存取強制 N（Phase 3）
        self.accesses = 0  # 本條指令的資料存取次數（週期模型用）
        # mGBA 式 active-region accounting（Python reference 對照 Rust `--mgba`）。
        self.mgba_timing = False
        self.prefetch_last_pc = 0

    @property
    def irq_line(self) -> bool:
        return self._bus.io_registers.irq_line

    @property
    def io_registers(self):
        """底層 :class:`bus.io.IoRegisters`（SWI handler 需要直接操作暫存器）。"""

        return self._bus.io_registers

    @property
    def ewram(self):
        return self._bus.ewram

    @property
    def iwram(self):
        return self._bus.iwram

    @property
    def palette(self):
        return self._bus.palette

    @property
    def vram(self):
        return self._bus.vram

    @property
    def oam(self):
        return self._bus.oam

    @property
    def timers(self):
        return self._bus.timers

    @property
    def dma(self):
        return self._bus.dma

    @property
    def bios_present(self) -> bool:
        """是否載入真 BIOS（由 AddressBus 決定；HLE 模式為 False）。"""

        return self._bus.bios_present

    # -- 週期模型 ---------------------------------------------------------
    @property
    def io(self) -> bytearray:
        """I/O raw bytes（WAITCNT／prefetch 位；由 :class:`bus.io.IoRegisters` 持有）。"""

        return self._bus.io_registers.raw

    def access_cost(self, address: int, width: int, sequential: bool) -> int:
        """單次存取的 cycle 數（規格 §3.6.5）。"""

        if self.functional:
            return 1
        return access_cycles(address, width, sequential, self._bus.waitcnt) + self._bus.video_wait(
            address, width
        )

    # -- mGBA 式 accounting（Python reference；對應 Rust `mgba_*`） -----------
    def mgba_access(self, address: int, width: int, sequential: bool) -> int:
        """mGBA 公約的原始存取 cycle（唔加 video wait、唔加 +1）。"""

        if self.functional:
            return 1
        return access_cycles(address, width, sequential, self._bus.waitcnt)

    def mgba_wait16(self, address: int, sequential: bool) -> int:
        value = self.mgba_access(address, 2, sequential)
        return value - 1 if value > 0 else 0

    def mgba_stall(self, pc: int, wait: int) -> int:
        """mGBA `GBAMemoryStall`（回傳值可以係負數）。"""

        if not self.prefetch_enabled() or not 0x08000000 <= pc <= 0x0DFFFFFF:
            return wait
        s = max(1, self.mgba_wait16(pc, True))
        nonseq = self.mgba_wait16(pc, False)
        dist = (self.prefetch_last_pc - pc) & 0xFFFFFFFF
        previous = (dist >> 1) if dist < 16 else 0
        max_loads = max(1, 8 - previous)
        stall = s + 1
        loads = 1
        while stall < wait and loads < max_loads:
            stall += s
            loads += 1
        self.prefetch_last_pc = (pc + 2 * (loads + previous - 1)) & 0xFFFFFFFF
        adjusted = max(wait, stall)
        adjusted -= nonseq - s
        adjusted -= stall
        return adjusted

    def mgba_data_cost(self, pc: int, address: int, width: int) -> int:
        wait = self.mgba_access(address, width, False) - 1
        total = wait + 2
        if address < 0x08000000:
            total = self.mgba_stall(pc, total)
        return total

    def mgba_store_cost(self, pc: int, address: int, width: int) -> int:
        wait = self.mgba_access(address, width, False)
        if address < 0x08000000:
            wait = self.mgba_stall(pc, wait)
        return wait

    def prefetch_enabled(self) -> bool:
        return bool((self.io[0x205] >> 6) & 1)

    @property
    def waitcnt(self) -> int:
        """0x04000204（WAITCNT）目前值（給 `cycles.py` 的 HLE profile 用）。"""
        return self._bus.waitcnt

    # -- 除錯 peek（不計數、無副作用） ------------------------------------
    def peek8(self, address: int) -> int:
        return self._bus.peek_u8(address)

    def peek16(self, address: int) -> int:
        return self._bus.peek_u16(align_address(address, 2))

    def peek32(self, address: int) -> int:
        return self._bus.peek_u32(align_address(address, 4))

    # -- 硬體路徑 ---------------------------------------------------------
    def read8(self, address: int) -> int:
        self.accesses += 1
        return self._bus.read_u8(address)

    def read16(self, address: int) -> int:
        self.accesses += 1
        value = self._bus.read_u16(address)
        if address & 1:
            value = rotate_right_32(value, 8)  # ARM7TDMI LDRH 未對齊 → ROR 8
        return value

    def fetch32(self, address: int) -> int:
        self.accesses += 1
        return self._bus.fetch32(address)

    def read32(self, address: int) -> int:
        self.accesses += 1
        value = self._bus.read_u32(address)
        if address & 3:
            value = unaligned_word_rotate(value, address)  # LDR 未對齊 → ROR
        return value

    def write8(self, address: int, value: int) -> None:
        self.accesses += 1
        self._bus.write_u8(address, value)

    def write16(self, address: int, value: int) -> None:
        self.accesses += 1
        # Game Pak SRAM 是 8-bit 匯流排：wide store 只寫 1 個 byte，
        # byte 由原始位址低 bit 揀（mGBA GBAStore16；suite SRAM store）。
        if 0x0E000000 <= address <= 0x0FFFFFFF:
            self._bus.write_u16(address, value)
            return
        address &= ~1
        self._bus.write_u16(address, value)

    def write32(self, address: int, value: int) -> None:
        self.accesses += 1
        if 0x0E000000 <= address <= 0x0FFFFFFF:
            self._bus.write_u32(address, value)
            return
        address &= ~3
        self._bus.write_u32(address, value)

    def _stall(self, cycles: int) -> None:
        """保留給 HLE handler 的週期停頓；Phase 1 尚無 wait-state 模型。"""

        del cycles


class Arm7Tdmi(CycleModel):
    """ARM7TDMI 核心狀態 + 單指令執行。"""

    def __init__(
        self,
        bus=None,
        *,
        swi_table: SwiTable | None = None,
        functional: bool = True,
    ) -> None:
        self.core: Arm7CoreState = new_core_state()
        self.regs = RegisterFile(self.core)
        self.bus: CpuBus | None = (
            CpuBus(bus, functional=functional) if bus is not None else None
        )
        self.swi_table = swi_table if swi_table is not None else SwiTable(strict=True)
        self.cycles = 0
        self._undef_seen: set[tuple[int, int | None]] = set()
        self._t_branch_taken = False
        self._nseq_fetch = False  # 下一條抓取是否非循序（load/store 之後）
        self._irq_wait = -1  # IRQ 管線延遲（-1 = 未 arm）
        self.wait_irq = 0  # IntrWait 的等待旗標（0 = 任意 IRQ）
        self._fast_core = None
        if os.environ.get("GBAEMU_FAST_CORE") == "1":
            try:
                from .core import FastCore
                self._fast_core = FastCore()
            except ImportError:
                self._fast_core = None

    # ------------------------------------------------------------------
    # 生命週期
    # ------------------------------------------------------------------
    def bind_bus(self, bus, *, swi_table: SwiTable | None = None) -> None:
        """接上 AddressBus（Emulator 建構時呼叫）。"""

        functional = self.bus.functional if self.bus is not None else True
        self.bus = CpuBus(bus, functional=functional)
        if swi_table is not None:
            self.swi_table = swi_table

    @property
    def halted(self) -> bool:
        return self.core.halted

    @halted.setter
    def halted(self, value: bool) -> None:
        self.core.halted = bool(value)

    def reset(self) -> None:
        self.core = new_core_state()
        self.regs = RegisterFile(self.core)
        self.cycles = 0
        self._undef_seen.clear()
        self._t_branch_taken = False
        self._nseq_fetch = False
        self._irq_wait = -1
        self.wait_irq = 0

    def apply_post_boot(self, postboot) -> None:
        """套用 HLE／BIOS 完成後的 CPU 狀態（規格 2.1.1）。"""

        self.core = new_core_state()
        self.regs = RegisterFile(self.core)
        self.core.regs[13] = postboot.sp_usr & 0xFFFFFFFF
        self.core.regs[15] = postboot.pc & 0xFFFFFFFF
        self.core.cpsr = (postboot.mode & MODE_MASK) | (CPSR_T if postboot.thumb else 0)
        self.core.spsr = 0
        self.core.banked = {
            MODE_IRQ: (postboot.sp_irq & 0xFFFFFFFF, 0),
            MODE_SVC: (postboot.sp_svc & 0xFFFFFFFF, 0),
        }
        self.core.banked_spsr = {MODE_IRQ: 0, MODE_SVC: 0}
        self.core.bank_mode = MODE_SYS
        self.core.pipeline = []
        self.core.halted = False
        self.cycles = 0
        self._undef_seen.clear()
        self._nseq_fetch = False
        self._irq_wait = -1
        self.wait_irq = 0

    def apply_bare_reset(
        self,
        pc: int,
        *,
        mode: int = MODE_SYS,
        sp: int = 0x03007F00,
        flags: int = CPSR_I | CPSR_F,
    ) -> None:
        """Phase 0/1 的 TEST_ROM_ONLY／REQUIRE_BIOS 起始狀態（非 BIOS post-boot）。"""

        self.reset()
        self.core.regs[13] = sp & 0xFFFFFFFF
        self.core.regs[15] = pc & 0xFFFFFFFC
        self.core.cpsr = (mode & MODE_MASK) | flags
        if mode != MODE_SYS:
            self.core.banked = {mode & MODE_MASK: (sp & 0xFFFFFFFF, 0)}
            self.core.bank_mode = mode & MODE_MASK
        else:
            self.core.banked = {}

    # ------------------------------------------------------------------
    # 執行
    # ------------------------------------------------------------------
    def step(self) -> int:
        """執行一條指令，回傳消耗的 cycle 數（規格 §3.6）。"""

        self._t_branch_taken = False
        if self.core.halted:
            if self._halt_wake_requested():
                self.core.halted = False
                if self.wait_irq:
                    seen = self.bus.io_registers.irq_seen | self.bus.peek16(_REG_IF)
                    if seen & self.wait_irq:
                        flags = self.wait_irq
                        ram = self.bus.read16(0x03007FF8)
                        self.bus.write16(0x03007FF8, ram & ~flags & 0xFFFF)
                        self.bus.io_registers.clear_irq_seen(flags)
                        self.wait_irq = 0
                        # 同 Rust `Cpu::step_inner()` 一樣：IntrWait 目標已到
                        # 而 IRQ line 仍然拉起，就即刻入 handler（handler 要
                        # 先於主程式執行；suite Timer count-up 靠呢個次序）。
                        if self.bus.irq_line and not (self.regs.cpsr & CPSR_I):
                            pc = self.regs.r[15]
                            self.enter_exception(MODE_IRQ, 0x00000018, lr_offset=4)
                            if not self.bus.bios_present:
                                self._hle_irq_enter()
                            self._irq_wait = -1
                            self.cycles += 3
                            return 3
                extra = self.check_irq(1)
                if self.wait_irq and extra == 0:
                    # 目標 IRQ 出現過（曾經拉起，或而家仍然 pending）就返回；
                    # 否則（例如只得 HBlank）繼續等。
                    seen = self.bus.io_registers.irq_seen | self.bus.peek16(_REG_IF)
                    if seen & self.wait_irq:
                        self.bus.io_registers.clear_irq_seen(self.wait_irq)
                        self.wait_irq = 0
                    else:
                        self.core.halted = True
                self.cycles += 1 + extra
                return 1 + extra
            extra = self.check_irq(1)
            self.cycles += 1 + extra
            return 1 + extra

        regs = self.regs
        if self.bus is None:
            raise RuntimeError("CPU 尚未接上 bus（先呼叫 bind_bus()）")

        if self._hle_irq_return_pending():
            cycles = self._hle_irq_return()
            self.cycles += cycles
            # IntrWait：IRQ handler 返回後才判斷目標 flag 有冇被 acknowledge；
            # 未到就再 halt，一次 IRQ（例如 HBlank）唔會令 IntrWait 提早返回。
            if self.wait_irq:
                seen = self.bus.io_registers.irq_seen | self.bus.peek16(_REG_IF)
                if seen & self.wait_irq:
                    self.bus.io_registers.clear_irq_seen(self.wait_irq)
                    self.wait_irq = 0
                else:
                    self.core.halted = True
            self.check_irq(cycles)
            return cycles

        fast = self._fast_core
        if fast is not None:
            result = fast.try_step(self)
            if result is not None:
                extra = self.check_irq(result)
                self.cycles += result + extra
                return result + extra

        if regs.cpsr & CPSR_T:
            pc = regs.r[15] & 0xFFFFFFFE
            regs.r[15] = pc
            instr = self.bus.read16(pc)
            cycles = self._thumb_cycles(instr)
            thumb.execute(self, instr)
        else:
            pc = regs.r[15] & 0xFFFFFFFC
            regs.r[15] = pc
            instr = self.bus.fetch32(pc)
            cond = (instr >> 28) & 0xF
            if cond == 0xF:
                # NV：ARM7TDMI 上除 SWI 外永不執行。SWI 依相容性照常執行。
                if (instr >> 24) & 0xF == 0xF:
                    cycles = self._arm_cycles(instr)
                    arm.execute(self, instr)
                else:
                    regs.pc = pc + 4
                    cycles = self._bubble_cycles(pc, 4)
            elif conditions.passed(cond, regs.cpsr):
                cycles = self._arm_cycles(instr)
                arm.execute(self, instr)
            else:
                regs.pc = pc + 4
                cycles = self._bubble_cycles(pc, 4)

        extra = self.check_irq(cycles)
        self.cycles += cycles + extra
        return cycles + extra

    def run_block(self, budget: int) -> int:
        """M2/M4：快速跑一小段支援的 ARM 指令；0 = fallback。"""

        fast = self._fast_core
        if fast is None:
            return 0
        return fast.run_block(self, budget)

    def peek_cycles(self) -> int:
        """不改變狀態地回傳下一條指令的 cycle 數（供 step_cycles 預算檢查）。"""

        if self.core.halted:
            return 1
        if self.bus is None:
            raise RuntimeError("CPU 尚未接上 bus（先呼叫 bind_bus()）")

        regs = self.regs
        saved_seq = self._nseq_fetch
        try:
            if regs.cpsr & CPSR_T:
                pc = regs.r[15] & 0xFFFFFFFE
                return self._thumb_cycles(self.bus.read16(pc))
            pc = regs.r[15] & 0xFFFFFFFC
            instr = self.bus.read32(pc)
            cond = (instr >> 28) & 0xF
            if cond == 0xF:
                if (instr >> 24) & 0xF == 0xF:
                    return self._arm_cycles(instr)
                return self._bubble_cycles(pc, 4)
            if conditions.passed(cond, regs.cpsr):
                return self._arm_cycles(instr)
            return self._bubble_cycles(pc, 4)
        finally:
            self._nseq_fetch = saved_seq

    def _bubble_cycles(self, pc: int, width: int) -> int:
        """條件不成立／cond=F 非 SWI 的 1S 成本（不消耗 fetch 循序旗標）。"""

        if self.bus is None or self.bus.functional:
            return 1
        return self.bus.access_cost(pc, width, True)

    # ------------------------------------------------------------------
    # Snapshot（規格 5.7 CPU 區段）
    # ------------------------------------------------------------------
    _BANK_MODES = (0x11, 0x12, 0x13, 0x17, 0x1B, 0x1F)
    _SNAPSHOT = struct.Struct("<16I2I12I6IBB5I5IQIiBB")

    def snapshot_state(self) -> bytes:
        core = self.core
        banked = []
        banked_spsr = []
        for mode in self._BANK_MODES:
            sp, lr = core.banked.get(mode, (0, 0))
            banked.extend((sp & 0xFFFFFFFF, lr & 0xFFFFFFFF))
            banked_spsr.append(core.banked_spsr.get(mode, 0) & 0xFFFFFFFF)
        return self._SNAPSHOT.pack(
            *[value & 0xFFFFFFFF for value in core.regs],
            core.cpsr & 0xFFFFFFFF,
            core.spsr & 0xFFFFFFFF,
            *banked,
            *banked_spsr,
            core.bank_mode & 0xFF,
            1 if core.halted else 0,
            *[value & 0xFFFFFFFF for value in core.fiq_r8_12],
            *[value & 0xFFFFFFFF for value in core.usr_r8_12],
            self.cycles & 0xFFFFFFFFFFFFFFFF,
            self.wait_irq & 0xFFFFFFFF,
            self._irq_wait,
            1 if self._nseq_fetch else 0,
            1 if self._t_branch_taken else 0,
        )

    def restore_state(self, data: bytes) -> None:
        values = self._SNAPSHOT.unpack(data)
        index = 0
        regs = list(values[index : index + 16])
        index += 16
        cpsr, spsr = values[index], values[index + 1]
        index += 2
        banked = {}
        for mode in self._BANK_MODES:
            sp, lr = values[index], values[index + 1]
            banked[mode] = (sp, lr)
            index += 2
        banked_spsr = {}
        for mode in self._BANK_MODES:
            banked_spsr[mode] = values[index]
            index += 1
        bank_mode = values[index]
        halted = bool(values[index + 1])
        index += 2
        fiq = list(values[index : index + 5])
        usr = list(values[index + 5 : index + 10])
        index += 10
        cycles = values[index]
        wait_irq = values[index + 1]
        irq_wait = values[index + 2]
        nseq = values[index + 3]
        tbranch = values[index + 4]
        state = self.core
        state.regs = [value & 0xFFFFFFFF for value in regs]
        state.cpsr = cpsr & 0xFFFFFFFF
        state.spsr = spsr & 0xFFFFFFFF
        state.banked = banked
        state.banked_spsr = banked_spsr
        state.bank_mode = bank_mode
        state.halted = halted
        state.fiq_r8_12 = fiq
        state.usr_r8_12 = usr
        self.regs = RegisterFile(state)
        self.cycles = cycles
        self.wait_irq = wait_irq
        self._irq_wait = irq_wait
        self._nseq_fetch = bool(nseq)
        self._t_branch_taken = bool(tbranch)

    def execute_one(self, instr: int, *, thumb: bool = False) -> None:
        """直接執行一條已抓取的指令（測試／除錯用）。

        不檢查條件碼、不 fetch、不計 cycle；PC 應先指向指令位址
        （handler 內部讀 R15 時為 PC+8／PC+4），結束時由 handler 更新 PC。
        供 opcode 單元測試與 legacy golden 向量共用。
        """

        if thumb:
            thumb.execute(self, instr & 0xFFFF)
        else:
            arm.execute(self, instr & 0xFFFFFFFF)

    # ------------------------------------------------------------------
    # 例外入口（GBATEK: ARM CPU Exceptions）
    # ------------------------------------------------------------------
    def enter_exception(
        self, mode: int, vector: int, lr_offset: int = 4, *, set_f: bool = False
    ) -> None:
        """存 CPSR→SPSR、切 mode、LR=PC+offset、T=0、I=1（Reset/FIQ 可設 F）。"""

        regs = self.regs
        old_cpsr = regs.cpsr
        regs.switch_mode(mode)
        regs.spsr_set(old_cpsr)
        regs.r[14] = (regs.r[15] + lr_offset) & 0xFFFFFFFF
        new_cpsr = (old_cpsr & ~(MODE_MASK | CPSR_T | CPSR_I)) | CPSR_I | (mode & MODE_MASK)
        if set_f:
            new_cpsr |= CPSR_F
        else:
            new_cpsr |= old_cpsr & CPSR_F
        regs.cpsr = new_cpsr
        regs.pc = vector

    def swi(self, comment: int) -> None:
        """SWI：進 SVC 例外；HLE 模式派發 SWI table 後返回（Phase 3 才有 handler）。"""

        lr_offset = 2 if (self.regs.cpsr & CPSR_T) else 4
        self.enter_exception(MODE_SVC, 0x00000008, lr_offset=lr_offset)
        if self.bus is not None and self.bus.bios_present:
            return  # 真 BIOS 從 0x08 執行

        # HLE：在 SVC 狀態派發；strict 模式下未實作的 SWI 會直接 raise。
        self.swi_table.dispatch(comment)

        # 等價 MOVS PC,R14：還原 CPSR 並返回。
        new_cpsr = self.regs.spsr_get()
        lr = self.regs.r[14]
        self.regs.switch_mode(new_cpsr & MODE_MASK)
        self.regs.cpsr = new_cpsr
        self.regs.pc = lr

    def arm_irq(self) -> None:
        """喺 `bus.tick()` 之後 arm IRQ pipeline。

        Rust `Core::step()` 喺 `bus.tick()`／DMA 之後才 `check_irq()`，所以
        新拉起嘅 IRQ line 會喺同一個 step arm；Python 原本喺 `cpu.step()`
        入面（tick 之前）check，會遲一個 instruction 才 arm。呢個方法補返
        post-tick arm，令兩邊 IRQ entry 對齊。
        """

        if self.bus is None or self._irq_wait >= 0:
            return
        if self.regs.cpsr & CPSR_I:
            return
        if not self.bus.irq_line:
            return
        self._irq_wait = 5 if (self.bus.mgba_timing and not self.bus.functional) else 2

    def check_irq(self, cycles: int = 1) -> int:
        """IME=1、IE&IF≠0、CPSR.I=0 時進 IRQ；回傳額外 cycle（0 = 未進場）。

        IRQ 線有 2-cycle 管線延遲（GBATEK: GBA Interrupt Control；
        與 legacy core 一致）：剛可用時 arm，倒數到 0 才進場。
        """

        if self.bus is None:
            return 0
        if not self.bus.irq_line:
            self._irq_wait = -1
            return 0
        if self.regs.cpsr & CPSR_I:
            self._irq_wait = -1
            return 0
        if self._irq_wait < 0:
            # mGBA accounting 用較長的管線延遲（配合新 model 的 timer／IRQ
            # 時序；suite Timer IRQ 65/90、Timer count-up 174/468）。
            self._irq_wait = 5 if (self.bus.mgba_timing and not self.bus.functional) else 2
            return 0
        self._irq_wait -= cycles
        if self._irq_wait > 0:
            return 0
        self._irq_wait = -1
        # IRQ 可以喺 HALT SWI 執行期間先拉起：嗰條 SWI 會將 halted 設返 True，
        # 但例外進場之後 CPU 一定要行 handler，唔可以停留喺 halted 狀態
        # （同 Rust `Cpu::check_irq()` 的 was_halted 處理一致）。
        if self.core.halted:
            self.core.halted = False
        pc = self.regs.r[15]
        self.enter_exception(MODE_IRQ, 0x00000018, lr_offset=4)
        if self.bus is not None and not self.bus.bios_present:
            self._hle_irq_enter()
        return self._exception_cost(pc)

    def _halt_wake_requested(self) -> bool:
        """GBATEK Halt：IE & IF 有交集即喚醒（不看 IME 與 I）。

        IntrWait 都一樣：硬體會服務任何已啟用 IRQ，然後 IntrWait 再判斷目標 flag
        有冇被 acknowledge，未到就再 halt（見 `step`）。
        """

        if self.bus is None:
            return False
        flags = self.bus.peek16(_REG_IF)
        if self.wait_irq:
            # IntrWait：目標 flag 拉起或者任何已啟用 IRQ（例如 HBlank）都要醒。
            # 目標 flag 可能已經被 handler acknowledge（IF=0），但 BIOS 的
            # IntrWait 仍然要返回，所以同時睇 sticky 的 `irq_seen`。
            seen = flags | self.bus.io_registers.irq_seen
            return bool((seen & self.wait_irq) or (self.bus.peek16(_REG_IE) & flags))
        return bool(self.bus.peek16(_REG_IE) & flags)

    def _exception_cost(self, pc: int) -> int:
        """例外進場 2S+1N（規格 §3.6.7）；mGBA accounting 用固定 4 cycles。"""

        if self.bus is None:
            return 3
        if self.bus.mgba_timing and not self.bus.functional:
            return 4
        if self.bus.functional:
            return 3
        return 2 * self.bus.access_cost(pc, 4, True) + self.bus.access_cost(pc, 4, False)

    # -- HLE BIOS IRQ stub（GBATEK: BIOS Interrupt handling 0x128/0x138/0x13C） --
    _HLE_IRQ_RETURN = 0x00000138

    def _hle_irq_return_pending(self) -> bool:
        return (
            self.bus is not None
            and not self.bus.bios_present
            and (self.regs.cpsr & MODE_MASK) == MODE_IRQ
            and self.regs.r[15] in (0x00000138, 0x0000013C)
        )

    def _hle_irq_enter(self) -> None:
        """BIOS 0x128：存 R0-R3/R12/LR、LR=0x138、PC=[03007FFC]。"""

        assert self.bus is not None
        sp = (self.regs.r[13] - 24) & 0xFFFFFFFF
        self.regs.r[13] = sp
        for slot, register in enumerate((0, 1, 2, 3, 12)):
            self.bus.write32(sp + slot * 4, self.regs.r[register])
        self.bus.write32(sp + 20, self.regs.r[14])
        self.regs.r[14] = self._HLE_IRQ_RETURN
        self.regs.pc = self.bus.read32(0x03007FFC)

    def _hle_irq_return(self) -> int:
        """BIOS 0x138/0x13C：還原暫存器、CPSR=SPSR、PC=LR-4。"""

        assert self.bus is not None
        sp = self.regs.r[13]
        for slot, register in enumerate((0, 1, 2, 3, 12)):
            self.regs.r[register] = self.bus.read32(sp + slot * 4)
        saved_lr = self.bus.read32(sp + 20)
        self.regs.r[13] = (sp + 24) & 0xFFFFFFFF
        new_cpsr = self.regs.spsr_get()
        self.regs.switch_mode(new_cpsr & MODE_MASK)
        self.regs.cpsr = new_cpsr
        self.regs.pc = (saved_lr - 4) & 0xFFFFFFFF
        return 3

    # ------------------------------------------------------------------
    # 觀測
    # ------------------------------------------------------------------
    def view(self) -> CPUState:
        """建立對外唯讀快照（CPUState）。"""

        regs = tuple(value & 0xFFFFFFFF for value in self.core.regs)
        return CPUState(
            regs=regs,
            cpsr=self.core.cpsr & 0xFFFFFFFF,
            spsr=self.regs.spsr_get(),
            thumb=is_thumb(self.core.cpsr),
            mode=mode_of(self.core.cpsr),
            halted=self.core.halted,
            cycles=self.cycles,
        )

    def read_register(self, name: str) -> int:
        if name in _REGISTER_NAMES:
            return self.core.regs[_REGISTER_NAMES[name]] & 0xFFFFFFFF
        if name == "cpsr":
            return self.core.cpsr & 0xFFFFFFFF
        if name == "spsr":
            return self.regs.spsr_get()
        raise ValueError(f"未知的暫存器名稱：{name!r}")


__all__ = ["Arm7Tdmi", "CpuBus"]
