//! G1 CPU interpreter（Rust）。
//!
//! 目前已實作 ARM/THUMB 的常見指令與 pipeline 對齊；exception、banking、
//! 精確 bus wait-state 與 cycle 仍待 G2。未實作的 opcode 回傳
//! `CpuError::Unsupported`，不猜測語意。
//!
//! 這是 migration 的中間狀態：Python `cpu/` 仍是默認 backend 與 oracle。

#![forbid(unsafe_code)]

use crate::bus::Bus;
use crate::{put_u32, put_u64, SnapshotReader};

pub const CPSR_N: u32 = 1 << 31;
pub const CPSR_Z: u32 = 1 << 30;
pub const CPSR_C: u32 = 1 << 29;
pub const CPSR_V: u32 = 1 << 28;
pub const CPSR_T: u32 = 1 << 5;
pub const CPSR_I: u32 = 1 << 7;
pub const CPSR_MODE_MASK: u32 = 0x1F;
pub const MODE_USER: u32 = 0x10;
pub const MODE_FIQ: u32 = 0x11;
pub const MODE_IRQ: u32 = 0x12;
pub const MODE_SVC: u32 = 0x13;
pub const MODE_ABT: u32 = 0x17;
pub const MODE_UND: u32 = 0x1B;
pub const MODE_SYS: u32 = 0x1F;

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum CpuError {
    Unsupported { pc: u32, opcode: u32, thumb: bool },
    Swi { pc: u32, number: u8 },
    HleUnsupported(u8),
    Bus(crate::bus::BusError),
}

impl From<crate::bus::BusError> for CpuError {
    fn from(value: crate::bus::BusError) -> Self {
        Self::Bus(value)
    }
}

fn sintab(index: u32) -> i32 {
    let angle = (index & 0xFF) as f64 * 2.0 * std::f64::consts::PI / 256.0;
    (angle.sin() * 256.0).floor() as i32
}

fn q8(value: i32) -> i32 {
    let quotient = value.div_euclid(256);
    let remainder = value.rem_euclid(256);
    if remainder > 128 {
        quotient + 1
    } else if remainder < 128 {
        quotient
    } else if quotient % 2 == 0 {
        quotient
    } else {
        quotient + 1
    }
}

/// BIOS SWI 0x09：ArcTan 的 0x474 多項式（Q2.14）。
/// 回傳 (r0 結果, r1 中間值, r3 多項式值)；suite 會逐項檢查。
fn biostan_parts(value: u32) -> (u32, u32, u32) {
    let r0 = value as i32;
    let mut r1 = (r0.wrapping_mul(r0) as i32) >> 14;
    r1 = r1.wrapping_neg();
    let mut r3 = 0xA9i32;
    for add in [0x390i32, 0x91C, 0xFB6, 0x16AA, 0x2081, 0x3651, 0xA2F9] {
        r3 = ((r3.wrapping_mul(r1) as i32) >> 14).wrapping_add(add);
    }
    let result = ((r3.wrapping_mul(r0) as i32) >> 16) as u32;
    (result, r1 as u32, r3 as u32)
}

fn biostan(value: u32) -> u32 {
    biostan_parts(value).0
}

/// BIOS 除法的向零截斷；避免 INT_MIN / -1 的 i32 overflow。
fn trunc_div(numerator: i32, denominator: i32) -> i32 {
    (numerator as i64 / denominator as i64) as i32
}

/// BIOS SWI 0x0A：ArcTan2 的象限演算法；回傳 (r0, r1)。
fn biosatan2_parts(x: u32, y: u32) -> (u32, u32) {
    let x = x as i32;
    let y = y as i32;
    if y == 0 {
        return (if x < 0 { 0x8000 } else { 0 }, 0);
    }
    if x == 0 {
        return (if y < 0 { 0xC000 } else { 0x4000 }, y as u32);
    }
    let r2 = (x as u32).wrapping_shl(14);
    let r3 = (y as u32).wrapping_shl(14);
    if y > 0 {
        if x > 0 {
            if x < y {
                let (atan, r1, _) = biostan_parts(trunc_div(r2 as i32, y) as u32);
                return ((0x4000u32).wrapping_sub(atan), r1);
            }
            let (atan, r1, _) = biostan_parts(trunc_div(r3 as i32, x) as u32);
            return (atan, r1);
        }
        if x.wrapping_neg() < y {
            let (atan, r1, _) = biostan_parts(trunc_div(r2 as i32, y) as u32);
            return ((0x4000u32).wrapping_sub(atan), r1);
        }
        let (atan, r1, _) = biostan_parts(trunc_div(r3 as i32, x) as u32);
        return ((0x8000u32).wrapping_add(atan), r1);
    }
    if x > 0 {
        if x < y.wrapping_neg() {
            let (atan, r1, _) = biostan_parts(trunc_div(r2 as i32, y) as u32);
            return ((0xC000u32).wrapping_sub(atan), r1);
        }
        let (atan, r1, _) = biostan_parts(trunc_div(r3 as i32, x) as u32);
        return ((0x10000u32).wrapping_add(atan), r1);
    }
    if x.wrapping_neg() > y.wrapping_neg() {
        let (atan, r1, _) = biostan_parts(trunc_div(r3 as i32, x) as u32);
        return ((0x8000u32).wrapping_add(atan), r1);
    }
    let (atan, r1, _) = biostan_parts(trunc_div(r2 as i32, y) as u32);
    ((0xC000u32).wrapping_sub(atan), r1)
}

fn biosatan2(x: u32, y: u32) -> u32 {
    biosatan2_parts(x, y).0
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Cpu {
    pub regs: [u32; 16],
    pub cpsr: u32,
    pub spsr: u32,
    pub halted: bool,
    /// IntrWait 的等待旗標（0 = 任意 IRQ）。
    pub wait_irq: u16,
    /// IntrWait 期間收到 IRQ：handler 完成後仍要返去 halt 等旗標。
    pub resume_halt_irq: bool,
    pub cycles: u64,
    /// 下一條 fetch 是否 non-sequential（cycle model 用）。
    pub nseq_fetch: bool,
    /// 由 bus／Core 設定的 IRQ line；CPU 在下一個 instruction boundary 檢查。
    pub irq_pending: bool,
    /// Python reference 的 IRQ 管線延遲倒數（snapshot 相容用）。
    pub irq_wait: i32,
    /// Thumb BL 的第一個 halfword 已解碼，等待第二個。
    pub thumb_bl_high: Option<u32>,
    /// Exception mode banks: FIQ/IRQ/SVC/ABT/UND 的 (SP, LR)。
    banked_sp_lr: [[u32; 2]; 5],
    /// Exception mode 的 SPSR。
    banked_spsr: [u32; 5],
    /// FIQ banked r8-r12 與非 FIQ 的 r8-r12。
    fiq_r8_12: [u32; 5],
    usr_r8_12: [u32; 5],
    /// User/System bank 的 SP/LR（S=1 的 LDM/STM 需要）。
    usr_sp: u32,
    usr_lr: u32,
}

impl Default for Cpu {
    fn default() -> Self {
        Self::new()
    }
}

impl Cpu {
    pub fn new() -> Self {
        let mut cpu = Self {
            regs: [0; 16],
            cpsr: MODE_SVC,
            spsr: 0,
            halted: false,
            wait_irq: 0,
            resume_halt_irq: false,
            cycles: 0,
            nseq_fetch: false,
            irq_pending: false,
            irq_wait: -1,
            thumb_bl_high: None,
            banked_sp_lr: [[0; 2]; 5],
            banked_spsr: [0; 5],
            fiq_r8_12: [0; 5],
            usr_r8_12: [0; 5],
            usr_sp: 0,
            usr_lr: 0,
        };
        cpu.regs[13] = 0x0300_7F00;
        cpu.regs[14] = 0;
        cpu.regs[15] = 0x0800_0000;
        cpu
    }

    fn bank_index(mode: u32) -> Option<usize> {
        match mode {
            MODE_FIQ => Some(0),
            MODE_IRQ => Some(1),
            MODE_SVC => Some(2),
            MODE_ABT => Some(3),
            MODE_UND => Some(4),
            _ => None,
        }
    }

    fn is_user_mode(mode: u32) -> bool {
        mode == MODE_SYS || mode == MODE_USER
    }

    fn save_current_bank(&mut self) {
        let mode = self.cpsr & CPSR_MODE_MASK;
        if Self::is_user_mode(mode) {
            self.usr_sp = self.regs[13];
            self.usr_lr = self.regs[14];
            return;
        }
        if let Some(index) = Self::bank_index(mode) {
            self.banked_sp_lr[index] = [self.regs[13], self.regs[14]];
            self.banked_spsr[index] = self.spsr;
        }
    }

    fn restore_bank(&mut self, mode: u32) {
        if Self::is_user_mode(mode) {
            self.regs[13] = self.usr_sp;
            self.regs[14] = self.usr_lr;
            return;
        }
        if let Some(index) = Self::bank_index(mode) {
            self.regs[13] = self.banked_sp_lr[index][0];
            self.regs[14] = self.banked_sp_lr[index][1];
            self.spsr = self.banked_spsr[index];
        }
    }

    fn user_get(&self, reg: usize) -> u32 {
        let mode = self.cpsr & CPSR_MODE_MASK;
        if reg < 8 || reg == 15 {
            return self.regs[reg];
        }
        if (8..=12).contains(&reg) {
            if mode == MODE_FIQ {
                return self.usr_r8_12[reg - 8];
            }
            return self.regs[reg];
        }
        if Self::is_user_mode(mode) {
            return self.regs[reg];
        }
        if reg == 13 { self.usr_sp } else { self.usr_lr }
    }

    fn user_set(&mut self, reg: usize, value: u32) {
        if reg < 8 {
            self.regs[reg] = value;
            return;
        }
        if reg == 15 {
            self.regs[15] = value & if self.cpsr & CPSR_T != 0 { !1 } else { !3 };
            return;
        }
        if (8..=12).contains(&reg) {
            if self.cpsr & CPSR_MODE_MASK == MODE_FIQ {
                self.usr_r8_12[reg - 8] = value;
                // ARM7TDMI「LDM^ glitch」：User bank 寫入同時 OR 進 FIQ 組。
                self.regs[reg] |= value;
            } else {
                self.regs[reg] = value;
            }
            return;
        }
        if Self::is_user_mode(self.cpsr & CPSR_MODE_MASK) {
            self.regs[reg] = value;
        } else if reg == 13 {
            self.usr_sp = value;
        } else {
            self.usr_lr = value;
        }
    }

    fn swap_fiq_regs(&mut self, enter: bool) {
        if enter {
            self.usr_r8_12.copy_from_slice(&self.regs[8..13]);
            self.regs[8..13].copy_from_slice(&self.fiq_r8_12);
        } else {
            self.fiq_r8_12.copy_from_slice(&self.regs[8..13]);
            self.regs[8..13].copy_from_slice(&self.usr_r8_12);
        }
    }

    /// 切換 mode，處理 exception bank 與 FIQ r8-r12。
    pub fn switch_mode(&mut self, new_mode: u32) {
        let old_mode = self.cpsr & CPSR_MODE_MASK;
        if old_mode == new_mode {
            return;
        }
        self.save_current_bank();
        if old_mode == MODE_FIQ && new_mode != MODE_FIQ {
            self.swap_fiq_regs(false);
        }
        self.restore_bank(new_mode);
        if new_mode == MODE_FIQ && old_mode != MODE_FIQ {
            self.swap_fiq_regs(true);
        }
        self.cpsr = (self.cpsr & !CPSR_MODE_MASK) | new_mode;
    }

    /// Exception entry：儲存 SPSR／LR，切 mode，PC = vector。
    pub fn enter_exception(&mut self, mode: u32, vector: u32, return_addr: u32) {
        let old_cpsr = self.cpsr;
        self.save_current_bank();
        let old_mode = old_cpsr & CPSR_MODE_MASK;
        if old_mode == MODE_FIQ && mode != MODE_FIQ {
            self.swap_fiq_regs(false);
        }
        self.restore_bank(mode);
        if mode == MODE_FIQ && old_mode != MODE_FIQ {
            self.swap_fiq_regs(true);
        }
        self.spsr = old_cpsr;
        self.cpsr = (old_cpsr & !CPSR_MODE_MASK & !CPSR_T) | mode | CPSR_I;
        self.regs[14] = return_addr;
        self.regs[15] = vector;
    }

    /// Exception return：CPSR ← SPSR，切 mode，PC = target。
    pub fn exception_return(&mut self, target: u32) {
        let new_cpsr = self.spsr;
        let new_mode = new_cpsr & CPSR_MODE_MASK;
        self.save_current_bank();
        self.switch_mode(new_mode);
        self.cpsr = new_cpsr;
        self.regs[15] = target & if new_cpsr & CPSR_T != 0 { !1 } else { !3 };
    }

    pub fn thumb(&self) -> bool {
        self.cpsr & CPSR_T != 0
    }

    fn set_flag(&mut self, flag: u32, value: bool) {
        if value {
            self.cpsr |= flag;
        } else {
            self.cpsr &= !flag;
        }
    }

    fn nz(&mut self, value: u32) {
        self.set_flag(CPSR_N, value & CPSR_N != 0);
        self.set_flag(CPSR_Z, value == 0);
    }

    fn condition_ok(&self, cond: u32) -> bool {
        let n = self.cpsr & CPSR_N != 0;
        let z = self.cpsr & CPSR_Z != 0;
        let c = self.cpsr & CPSR_C != 0;
        let v = self.cpsr & CPSR_V != 0;
        match cond {
            0x0 => z,
            0x1 => !z,
            0x2 => c,
            0x3 => !c,
            0x4 => n,
            0x5 => !n,
            0x6 => v,
            0x7 => !v,
            0x8 => c && !z,
            0x9 => !c || z,
            0xA => n == v,
            0xB => n != v,
            0xC => !z && n == v,
            0xD => z || n != v,
            0xE => true,
            _ => false,
        }
    }

    fn shift(&self, value: u32, kind: u32, amount: u32, carry_in: bool) -> (u32, bool) {
        let mut amount = amount;
        match kind {
            0 => {
                if amount == 0 {
                    return (value, carry_in);
                }
                if amount < 32 {
                    (value << amount, ((value >> (32 - amount)) & 1) != 0)
                } else if amount == 32 {
                    (0, (value & 1) != 0)
                } else {
                    (0, false)
                }
            }
            1 => {
                if amount == 0 {
                    amount = 32;
                }
                if amount < 32 {
                    (value >> amount, ((value >> (amount - 1)) & 1) != 0)
                } else {
                    (0, if amount == 32 { value >> 31 != 0 } else { false })
                }
            }
            2 => {
                if amount == 0 {
                    amount = 32;
                }
                if amount < 32 {
                    (
                        ((value as i32) >> amount) as u32,
                        ((value >> (amount - 1)) & 1) != 0,
                    )
                } else {
                    (
                        if value & 0x8000_0000 != 0 { 0xFFFF_FFFF } else { 0 },
                        value >> 31 != 0,
                    )
                }
            }
            _ => {
                // 暫存器指定的 ROR #0 / #32 是 no-op，C 不變；
                // RRX 只存在於立即值編碼，由 operand2 另外處理。
                if amount == 0 {
                    return (value, carry_in);
                }
                let amount = amount & 31;
                if amount == 0 {
                    (value, carry_in)
                } else {
                    (
                        value.rotate_right(amount),
                        ((value >> (amount - 1)) & 1) != 0,
                    )
                }
            }
        }
    }

    fn operand2(&mut self, instr: u32, carry_in: bool) -> (u32, bool) {
        if instr & (1 << 25) != 0 {
            let imm = instr & 0xFF;
            let rot = ((instr >> 8) & 0xF) * 2;
            if rot == 0 {
                (imm, carry_in)
            } else {
                let value = imm.rotate_right(rot);
                (value, ((value >> 31) & 1) != 0)
            }
        } else {
            let rm = (instr & 0xF) as usize;
            let mut value = self.regs[rm];
            if instr & (1 << 4) != 0 {
                // 暫存器指定的移位：R15 讀到 PC+12（ARM7TDMI），立即數移位則是 PC+8。
                if rm == 15 {
                    value = value.wrapping_add(4);
                }
                let rs = ((instr >> 8) & 0xF) as usize;
                let amount = self.regs[rs] & 0xFF;
                if amount == 0 {
                    // 移位量 0：值與 C 都不變（只有「立即數編碼 0」才代表 32）。
                    (value, carry_in)
                } else {
                    self.shift(value, (instr >> 5) & 3, amount, carry_in)
                }
            } else {
                let kind = (instr >> 5) & 3;
                let amount = (instr >> 7) & 0x1F;
                if kind == 3 && amount == 0 {
                    // RRX：C 進 bit31，bit0 進 C
                    (((carry_in as u32) << 31) | (value >> 1), value & 1 != 0)
                } else {
                    self.shift(value, kind, amount, carry_in)
                }
            }
        }
    }

    pub fn step(&mut self, bus: &mut Bus) -> Result<u32, CpuError> {
        let start_cycles = self.cycles;
        let result = self.step_inner(bus);
        match result {
            Ok(cost) => {
                self.cycles = start_cycles + cost as u64;
                Ok(cost)
            }
            Err(error) => Err(error),
        }
    }

    fn step_inner(&mut self, bus: &mut Bus) -> Result<u32, CpuError> {
        let pc = self.regs[15];
        // mGBA `activeRegion`：喺 BIOS 區執行時 BIOS 讀取回真實內容，
        // 離開之後只回 biosPrefetch。
        bus.in_bios = pc < 0x4000;
        if self.halted {
            let intr_wait = self.wait_irq != 0;
            let wake = if intr_wait {
                // IntrWait：目標旗標可能喺 handler 入面出現又被 ack，所以同時睇
                // sticky 的 `irq_seen`（Python reference 的 irq_seen 模型）。
                (bus.if_ | bus.irq_seen) & self.wait_irq != 0
            } else {
                bus.ie & bus.if_ != 0
            };
            if wake {
                self.halted = false;
                if intr_wait {
                    let ram = bus.read16(0x0300_7FF8);
                    bus.write16(0x0300_7FF8, ram & !self.wait_irq);
                    bus.irq_seen &= !self.wait_irq;
                }
                self.wait_irq = 0;
                // IntrWait（BIOS SWI 0x04）會等 IRQ handler 行完先返回主程式，
                // 所以喚醒時即刻投遞 IRQ。suite「Timer count-up」靠呢個次序：
                // handler 要先扣 irqCounter，主程式先再寫新值；掉轉就會形成
                // IRQ storm。Halt（SWI 0x02）就維持「先執行 SWI 後一條指令、
                // 再喺 boundary 檢查」嘅模型（suite「SIO timing tests」）。
                if intr_wait && bus.ime && (bus.ie & bus.if_) != 0 && self.cpsr & CPSR_I == 0 {
                    let next_pc = self.regs[15];
                    self.enter_irq(next_pc);
                    self.hle_irq_enter(bus);
                    self.irq_wait = -1;
                    self.irq_pending = false;
                    self.cycles += 3;
                    return Ok(3);
                }
            }
            self.cycles += 1;
            return Ok(1);
        }
        if self.cpsr & CPSR_MODE_MASK == MODE_IRQ && (pc == 0x138 || pc == 0x13C) {
            return Ok(self.hle_irq_return(bus));
        }
        if self.irq_pending && self.cpsr & CPSR_I == 0 {
            // 保留欄位給 adapter／snapshot；實際 IRQ 進場由 `check_irq()` 控制。
            self.irq_pending = false;
        }
        if self.thumb() {
            let aligned_pc = pc & !1;
            let instr = bus.read16(aligned_pc) as u32;
            let cost = self.thumb_cycles(bus, aligned_pc, instr);
            return match self.step_thumb(bus, aligned_pc) {
                Ok(_) => Ok(cost),
                Err(error) => Err(error),
            };
        }
        let aligned_pc = pc & !3;
        let instr = bus.fetch32(aligned_pc);
        let cond = instr >> 28;
        let cost = if cond == 0xF || self.condition_ok(cond) {
            self.arm_cycles(bus, aligned_pc, instr)
        } else {
            self.bubble_cycles(bus, aligned_pc, 4)
        };
        match self.step_arm(bus, aligned_pc) {
            Ok(_) => Ok(cost),
            Err(error) => Err(error),
        }
    }

    fn bubble_cycles(&self, bus: &Bus, pc: u32, width: u32) -> u32 {
        if bus.functional { 1 } else { bus.access_cost(pc, width, true) }
    }

    fn step_arm(&mut self, bus: &mut Bus, pc: u32) -> Result<u32, CpuError> {
        let instr = bus.fetch32(pc);
        self.regs[15] = pc.wrapping_add(8);
        let cond = instr >> 28;
        if cond == 0xF {
            return Err(CpuError::Unsupported { pc, opcode: instr, thumb: false });
        }
        if !self.condition_ok(cond) {
            self.regs[15] = pc.wrapping_add(4);
            self.cycles += 1;
            return Ok(1);
        }

        // B / BL
        if (instr >> 25) & 0x7 == 0x5 {
            let mut off = instr & 0x00FF_FFFF;
            if off & 0x0080_0000 != 0 {
                off |= 0xFF00_0000;
            }
            off <<= 2;
            if instr & (1 << 24) != 0 {
                self.regs[14] = pc.wrapping_add(4);
            }
            self.regs[15] = pc.wrapping_add(8).wrapping_add(off) & !3;
            return Ok(2);
        }

        // BX
        if instr & 0x0FFF_FFF0 == 0x012F_FF10 {
            let target = self.regs[(instr & 0xF) as usize];
            if target & 1 != 0 {
                self.cpsr |= CPSR_T;
                self.regs[15] = target & !1;
            } else {
                self.cpsr &= !CPSR_T;
                self.regs[15] = target & !3;
            }
            self.cycles += 3;
            return Ok(3);
        }

        // MUL / MLA
        if instr & 0x0FC0_00F0 == 0x0000_0090 {
            let rd = ((instr >> 16) & 0xF) as usize;
            let rn = ((instr >> 12) & 0xF) as usize;
            let rs = ((instr >> 8) & 0xF) as usize;
            let rm = (instr & 0xF) as usize;
            let rm_value = self.regs[rm];
            let rs_value = self.regs[rs];
            let accumulate = instr & (1 << 21) != 0;
            let accum = if accumulate { self.regs[rn] } else { 0 };
            let mut result = rm_value.wrapping_mul(rs_value);
            if accumulate {
                result = result.wrapping_add(accum);
            }
            self.regs[rd] = result;
            if instr & (1 << 20) != 0 {
                // ARM7TDMI：N/Z 由 32-bit 結果；C 由 Booth multiplier carry
                // （ARM 文件寫 UNPREDICTABLE，但硬件行為固定；suite 以此為準）。
                let carry = if Self::mul_m(rs_value, true) == 4 {
                    Self::multiply_carry_simple(rs_value)
                } else {
                    Self::multiply_carry_lo(rm_value, rs_value, accum)
                };
                self.nz(result);
                self.set_flag(CPSR_C, carry);
            }
            self.regs[15] = pc.wrapping_add(4);
            self.cycles += 2;
            return Ok(2);
        }

        // MRS / MSR（必須在 data processing 之前：TST/CMP 的 S=0 編碼與此重疊）
        if instr & 0x0FFF_0FFF == 0x010F_0000 || instr & 0x0FFF_0FFF == 0x014F_0000 {
            let rd = ((instr >> 12) & 0xF) as usize;
            self.regs[rd] = if instr & (1 << 22) != 0 { self.spsr } else { self.cpsr };
            self.regs[15] = pc.wrapping_add(4);
            self.cycles += 1;
            return Ok(1);
        }
        if instr & 0x0FB0_F000 == 0x0120_F000 || instr & 0x0FB0_F000 == 0x0320_F000 {
            let value = if instr & (1 << 25) != 0 {
                let imm = instr & 0xFF;
                let rot = ((instr >> 8) & 0xF) * 2;
                if rot == 0 { imm } else { imm.rotate_right(rot) }
            } else {
                self.regs[(instr & 0xF) as usize]
            };
            let mask = (instr >> 16) & 0xF;
            let target_spsr = instr & (1 << 22) != 0;
            let mut new = if target_spsr { self.spsr } else { self.cpsr };
            if mask & 0x8 != 0 {
                new = (new & 0x00FF_FFFF) | (value & 0xFF00_0000);
            }
            if mask & 0x1 != 0 {
                new = (new & 0xFFFF_FF00) | (value & 0xDF) | (new & CPSR_T);
            }
            if target_spsr {
                self.spsr = new;
            } else {
                let old_mode = self.cpsr & CPSR_MODE_MASK;
                let new_mode = new & CPSR_MODE_MASK;
                if new_mode != old_mode {
                    self.switch_mode(new_mode);
                }
                self.cpsr = new;
            }
            self.regs[15] = pc.wrapping_add(4);
            self.cycles += 1;
            return Ok(1);
        }

        // Data processing（bit4=1 僅在 bit7=0 時是 register shift；
        // bit7=1 屬於 halfword/signed transfer、MUL、SWP，交由後面的解碼）
        if (instr >> 26) & 0x3 == 0
            && (instr & (1 << 25) != 0 || instr & (1 << 4) == 0 || instr & (1 << 7) == 0)
        {
            let op = (instr >> 21) & 0xF;
            let s = instr & (1 << 20) != 0;
            let rn = ((instr >> 16) & 0xF) as usize;
            let rd = ((instr >> 12) & 0xF) as usize;
            let carry_in = self.cpsr & CPSR_C != 0;
            let (op2, shifter_carry) = if instr & (1 << 25) != 0 {
                let imm = instr & 0xFF;
                let rot = ((instr >> 8) & 0xF) * 2;
                if rot == 0 {
                    (imm, carry_in)
                } else {
                    let v = imm.rotate_right(rot);
                    (v, (v >> 31) & 1 != 0)
                }
            } else {
                self.operand2(instr, carry_in)
            };
            // ARM7TDMI：data processing 讀 R15 一般係 instr+8；但如果
            // operand2 用咗 register-specified shift（bit25=0、bit4=1），
            // Rn=PC 都讀 instr+12（mGBA 同 suite「Shifter tests」都係咁）。
            let a = if rn == 15 {
                if instr & (1 << 25) == 0 && instr & (1 << 4) != 0 {
                    pc.wrapping_add(12)
                } else {
                    pc.wrapping_add(8)
                }
            } else {
                self.regs[rn]
            };
            let mut result = 0u32;
            let mut write = true;
            let mut logical = false;
            match op {
                0x0 => { result = a & op2; logical = true; }
                0x1 => { result = a ^ op2; logical = true; }
                0x2 => { result = a.wrapping_sub(op2); }
                0x3 => { result = op2.wrapping_sub(a); }
                0x4 => { result = a.wrapping_add(op2); }
                0x5 => { result = a.wrapping_add(op2).wrapping_add(u32::from(carry_in)); }
                0x6 => { result = a.wrapping_sub(op2).wrapping_sub(u32::from(!carry_in)); }
                0x7 => { result = op2.wrapping_sub(a).wrapping_sub(u32::from(!carry_in)); }
                0x8 => { result = a & op2; write = false; logical = true; }
                0x9 => { result = a ^ op2; write = false; logical = true; }
                0xA => { result = a.wrapping_sub(op2); write = false; }
                0xB => { result = a.wrapping_add(op2); write = false; }
                0xC => { result = a | op2; logical = true; }
                0xD => { result = op2; logical = true; }
                0xE => { result = a & !op2; logical = true; }
                0xF => { result = !op2; logical = true; }
                _ => unreachable!(),
            }
            if s || op >= 0x8 && op <= 0xB {
                self.nz(result);
                if logical {
                    self.set_flag(CPSR_C, shifter_carry);
                } else if op == 0x2 || op == 0xA {
                    self.set_flag(CPSR_C, a >= op2);
                    self.set_flag(CPSR_V, ((a ^ op2) & (a ^ result) & 0x8000_0000) != 0);
                } else if op == 0x3 {
                    self.set_flag(CPSR_C, op2 >= a);
                    self.set_flag(CPSR_V, ((op2 ^ a) & (op2 ^ result) & 0x8000_0000) != 0);
                } else if op == 0x4 || op == 0xB {
                    self.set_flag(CPSR_C, result < a);
                    self.set_flag(CPSR_V, ((a ^ result) & (op2 ^ result) & 0x8000_0000) != 0);
                } else if op == 0x5 {
                    let wide = a as u64 + op2 as u64 + u64::from(carry_in);
                    self.set_flag(CPSR_C, wide > 0xFFFF_FFFF);
                    self.set_flag(CPSR_V, ((a ^ result) & (op2 ^ result) & 0x8000_0000) != 0);
                } else if op == 0x6 {
                    let borrow = u32::from(!carry_in);
                    self.set_flag(CPSR_C, (a as u64) >= (op2 as u64 + borrow as u64));
                    self.set_flag(CPSR_V, ((a ^ op2) & (a ^ result) & 0x8000_0000) != 0);
                } else if op == 0x7 {
                    let borrow = u32::from(!carry_in);
                    self.set_flag(CPSR_C, (op2 as u64) >= (a as u64 + borrow as u64));
                    self.set_flag(CPSR_V, ((op2 ^ a) & (op2 ^ result) & 0x8000_0000) != 0);
                }
            }
            if write {
                if rd == 15 {
                    if s {
                        self.exception_return(result);
                    } else {
                        self.regs[15] = result & !3;
                    }
                } else {
                    self.regs[rd] = result;
                    self.regs[15] = pc.wrapping_add(4);
                }
            } else {
                self.regs[15] = pc.wrapping_add(4);
            }
            self.cycles += 1;
            return Ok(1);
        }

        // LDR / STR（bit25=0 immediate offset；bit4 只是 imm12 的一部分）
        if (instr >> 26) & 0x3 == 1 {
            let rd = ((instr >> 12) & 0xF) as usize;
            let rn = ((instr >> 16) & 0xF) as usize;
            let load = instr & (1 << 20) != 0;
            let byte = instr & (1 << 22) != 0;
            let add = instr & (1 << 23) != 0;
            let pre = instr & (1 << 24) != 0;
            let writeback = !pre || instr & (1 << 21) != 0;
            let offset = self.arm_transfer_offset(instr);
            let base = if rn == 15 { pc.wrapping_add(8) } else { self.regs[rn] };
            let addr = if add { base.wrapping_add(offset) } else { base.wrapping_sub(offset) };
            let effective = if pre { addr } else { base };
            if load {
                let value = if byte { self.read_byte(bus, effective) } else { self.read_word(bus, effective) };
                if rd == 15 {
                    self.regs[15] = value & !3;
                } else {
                    self.regs[rd] = value;
                    self.regs[15] = pc.wrapping_add(4);
                }
            } else {
                let value = if rd == 15 { self.regs[15].wrapping_add(4) } else { self.regs[rd] };
                if byte {
                    bus.write8(effective, value as u8);
                } else {
                    bus.write32(effective, value);
                }
                self.regs[15] = pc.wrapping_add(4);
            }
            if writeback && rn != 15 && !(load && rd == rn) {
                self.regs[rn] = addr;
            }
            let cost = if load { 3 } else { 2 };
            return Ok(cost);
        }

        // Halfword / signed transfers
        if instr & 0x0E00_0090 == 0x0000_0090 && matches!((instr >> 4) & 0xF, 0xB | 0xD | 0xF) {
            let rd = ((instr >> 12) & 0xF) as usize;
            let rn = ((instr >> 16) & 0xF) as usize;
            let load = instr & (1 << 20) != 0;
            let add = instr & (1 << 23) != 0;
            let pre = instr & (1 << 24) != 0;
            let writeback = !pre || instr & (1 << 21) != 0;
            let imm = instr & (1 << 22) != 0;
            let offset = if imm {
                ((instr >> 4) & 0xF0) | (instr & 0xF)
            } else {
                self.regs[(instr & 0xF) as usize]
            };
            let base = if rn == 15 { pc.wrapping_add(8) } else { self.regs[rn] };
            let addr = if add { base.wrapping_add(offset) } else { base.wrapping_sub(offset) };
            let effective = if pre { addr } else { base };
            let h = (instr >> 5) & 0x3;
            if load {
                let value = match h {
                    0b01 => self.read_half(bus, effective),
                    0b10 => {
                        let v = self.read_byte(bus, effective);
                        if v & 0x80 != 0 { v | 0xFFFF_FF00 } else { v }
                    }
                    _ => {
                        if effective & 1 != 0 {
                            let v = self.read_byte(bus, effective);
                            if v & 0x80 != 0 { v | 0xFFFF_FF00 } else { v }
                        } else {
                            let v = self.read_half(bus, effective);
                            if v & 0x8000 != 0 { v | 0xFFFF_0000 } else { v }
                        }
                    }
                };
                if rd == 15 { self.regs[15] = value & !3; }
                else { self.regs[rd] = value; self.regs[15] = pc.wrapping_add(4); }
            } else {
                let value = if rd == 15 { self.regs[15].wrapping_add(4) } else { self.regs[rd] };
                self.write_half(bus, effective, value as u16);
                self.regs[15] = pc.wrapping_add(4);
            }
            if writeback && rn != 15 && !(load && rd == rn) {
                self.regs[rn] = addr;
            }
            self.cycles += 3;
            return Ok(3);
        }

        // SWP / SWPB
        if instr & 0x0FB0_0FF0 == 0x0100_0090 || instr & 0x0FB0_0FF0 == 0x0140_0090 {
            let rn = ((instr >> 16) & 0xF) as usize;
            let rd = ((instr >> 12) & 0xF) as usize;
            let rm = (instr & 0xF) as usize;
            let addr = self.regs[rn];
            if instr & (1 << 22) != 0 {
                let old = self.read_byte(bus, addr);
                bus.write8(addr, self.regs[rm] as u8);
                self.regs[rd] = old;
            } else {
                let old = self.read_word(bus, addr);
                bus.write32(addr, self.regs[rm]);
                self.regs[rd] = old;
            }
            self.regs[15] = pc.wrapping_add(4);
            self.cycles += 3;
            return Ok(3);
        }

        // LDM / STM
        if (instr >> 25) & 0x7 == 0x4 {
            let rn = ((instr >> 16) & 0xF) as usize;
            let load = instr & (1 << 20) != 0;
            let add = instr & (1 << 23) != 0;
            let pre = instr & (1 << 24) != 0;
            let writeback = instr & (1 << 21) != 0;
            let s_bit = instr & (1 << 22) != 0;
            let mask = instr & 0xFFFF;
            let n = mask.count_ones();
            let base = if rn == 15 { pc.wrapping_add(8) } else { self.regs[rn] };
            let user_bank = s_bit && !(load && mask & 0x8000 != 0);

            // 空清單（ARMv4 未定義；Python reference 有明確模型）
            if mask == 0 {
                if load {
                    self.regs[15] = bus.read32(base) & !3;
                } else {
                    let addr = if pre {
                        if add { base.wrapping_add(4) } else { base.wrapping_sub(0x40) }
                    } else if add {
                        base
                    } else {
                        base.wrapping_sub(0x3C)
                    };
                    bus.write32(addr, pc.wrapping_add(12));
                }
                if writeback && rn != 15 {
                    self.regs[rn] = if add { base.wrapping_add(0x40) } else { base.wrapping_sub(0x40) };
                }
                if !load {
                    self.regs[15] = pc.wrapping_add(4);
                }
                return Ok(if load { 3 } else { 2 });
            }

            let start = if !pre && add {
                base
            } else if pre && add {
                base.wrapping_add(4)
            } else if pre && !add {
                base.wrapping_sub(4 * n)
            } else {
                base.wrapping_sub(4 * n).wrapping_add(4)
            };
            let new_base = if add { base.wrapping_add(4 * n) } else { base.wrapping_sub(4 * n) };
            let first_reg = mask.trailing_zeros() as usize;
            let mut addr = start;
            for reg in 0..16 {
                if mask & (1 << reg) == 0 { continue; }
                if load {
                    let value = self.read_word(bus, addr);
                    if reg == 15 {
                        self.regs[15] = value & if self.cpsr & CPSR_T != 0 { !1 } else { !3 };
                    } else if user_bank && (8..=14).contains(&reg) {
                        self.user_set(reg, value);
                    } else {
                        self.regs[reg] = value;
                    }
                } else {
                    let value = if reg == rn {
                        if first_reg == rn { base } else { new_base }
                    } else if user_bank && (8..=14).contains(&reg) {
                        self.user_get(reg)
                    } else if reg == 15 {
                        self.regs[15].wrapping_add(4)
                    } else {
                        self.regs[reg]
                    };
                    bus.write32(addr, value);
                }
                addr = addr.wrapping_add(4);
            }
            if writeback && !(load && mask & (1 << rn) != 0) {
                self.regs[rn] = new_base;
            }
            if load && s_bit && mask & 0x8000 != 0 {
                // LDM^：例外返回，CPSR ← SPSR。
                let new_cpsr = self.spsr;
                let new_mode = new_cpsr & CPSR_MODE_MASK;
                self.save_current_bank();
                self.switch_mode(new_mode);
                self.cpsr = new_cpsr;
            } else if !(load && mask & 0x8000 != 0) {
                self.regs[15] = pc.wrapping_add(4);
            }
            return Ok(if load { 3 + n } else { 2 + n });
        }

        // Long multiply
        if instr & 0x0F80_00F0 == 0x0080_0090 {
            let rdhi = ((instr >> 16) & 0xF) as usize;
            let rdlo = ((instr >> 12) & 0xF) as usize;
            let rs = ((instr >> 8) & 0xF) as usize;
            let rm = (instr & 0xF) as usize;
            let signed = instr & (1 << 22) != 0;
            let accumulate = instr & (1 << 21) != 0;
            let rm_value = self.regs[rm];
            let rs_value = self.regs[rs];
            let accum_lo = if accumulate { self.regs[rdlo] } else { 0 };
            let accum_hi = if accumulate { self.regs[rdhi] } else { 0 };
            let mut product: u64 = if signed {
                ((rm_value as i32 as i64) * (rs_value as i32 as i64)) as u64
            } else {
                (rm_value as u64) * (rs_value as u64)
            };
            if accumulate {
                product = product.wrapping_add(((accum_hi as u64) << 32) | accum_lo as u64);
            }
            self.regs[rdlo] = product as u32;
            self.regs[rdhi] = (product >> 32) as u32;
            if instr & (1 << 20) != 0 {
                // N/Z 由完整 64-bit 結果；C 由 Booth multiplier（同 MUL 的算法）。
                let carry = if Self::mul_m(rs_value, signed) == 4 {
                    Self::multiply_carry_hi(rm_value, rs_value, accum_hi, signed)
                } else {
                    Self::multiply_carry_lo(rm_value, rs_value, accum_lo)
                };
                self.set_flag(CPSR_N, product & (1 << 63) != 0);
                self.set_flag(CPSR_Z, product == 0);
                self.set_flag(CPSR_C, carry);
            }
            self.regs[15] = pc.wrapping_add(4);
            self.cycles += 3;
            return Ok(3);
        }

        // SWI
        if (instr >> 24) & 0xF == 0xF {
            let number = ((instr >> 16) & 0xFF) as u8;
            self.regs[15] = pc.wrapping_add(4);
            self.hle_swi(bus, number)?;
            self.cycles += 3;
            return Ok(3);
        }

        Err(CpuError::Unsupported { pc, opcode: instr, thumb: false })
    }

    fn step_thumb(&mut self, bus: &mut Bus, pc: u32) -> Result<u32, CpuError> {
        let instr = bus.read16(pc) as u32;
        self.regs[15] = pc.wrapping_add(4);
        self.cycles += 1;
        // format 1: move shifted register（00000/00001/00010；00011 是 add/sub）
        if (instr >> 11) & 0x1F <= 2 {
            let op = (instr >> 11) & 0x3;
            let offset = (instr >> 6) & 0x1F;
            let rs = ((instr >> 3) & 0x7) as usize;
            let rd = (instr & 0x7) as usize;
            let (value, carry) = self.shift(self.regs[rs], op, offset, self.cpsr & CPSR_C != 0);
            self.regs[rd] = value;
            self.nz(value);
            self.set_flag(CPSR_C, carry);
            self.regs[15] = pc.wrapping_add(2);
            return Ok(1);
        }
        // format 2: add/sub
        if (instr >> 11) == 0x3 {
            let rd = (instr & 0x7) as usize;
            let rs = ((instr >> 3) & 0x7) as usize;
            let rn = ((instr >> 6) & 0x7) as usize;
            let immediate = (instr >> 10) & 1 != 0;
            let sub = (instr >> 9) & 1 != 0;
            let a = self.regs[rs];
            let b = if immediate { rn as u32 } else { self.regs[rn] };
            let result = if sub { a.wrapping_sub(b) } else { a.wrapping_add(b) };
            self.regs[rd] = result;
            self.nz(result);
            self.set_flag(CPSR_C, if sub { a >= b } else { result < a });
            self.set_flag(CPSR_V, if sub { ((a ^ b) & (a ^ result) & 0x8000_0000) != 0 } else { ((a ^ result) & (b ^ result) & 0x8000_0000) != 0 });
            self.regs[15] = pc.wrapping_add(2);
            return Ok(1);
        }
        // format 3: mov/cmp/add/sub immediate
        if (instr >> 13) & 0x7 == 0x1 {
            let op = (instr >> 11) & 0x3;
            let rd = ((instr >> 8) & 0x7) as usize;
            let imm = instr & 0xFF;
            let a = self.regs[rd];
            let (result, write) = match op {
                0 => (imm, true),
                1 => (a.wrapping_sub(imm), false),
                2 => (a.wrapping_add(imm), true),
                _ => (a.wrapping_sub(imm), true),
            };
            if write { self.regs[rd] = result; }
            self.nz(result);
            if op != 0 {
                if op == 1 || op == 3 {
                    self.set_flag(CPSR_C, a >= imm);
                    self.set_flag(CPSR_V, ((a ^ imm) & (a ^ result) & 0x8000_0000) != 0);
                } else {
                    self.set_flag(CPSR_C, result < a);
                    self.set_flag(CPSR_V, ((a ^ result) & (imm ^ result) & 0x8000_0000) != 0);
                }
            }
            self.regs[15] = pc.wrapping_add(2);
            return Ok(1);
        }
        // format 6: PC-relative load
        if (instr >> 11) & 0x1F == 0x09 {
            let rd = ((instr >> 8) & 0x7) as usize;
            let addr = (pc.wrapping_add(4) & !3).wrapping_add((instr & 0xFF) << 2);
            self.regs[rd] = self.read_word(bus, addr);
            self.regs[15] = pc.wrapping_add(2);
            return Ok(3);
        }
        // format 16: conditional branch（cond=0xF 是 SWI，交由 format 17）
        if (instr >> 12) & 0xF == 0xD && (instr >> 8) & 0xF != 0xF {
            let cond = (instr >> 8) & 0xF;
            if self.condition_ok(cond) {
                let mut off = (instr & 0xFF) as i32;
                if off & 0x80 != 0 { off -= 0x100; }
                self.regs[15] = pc.wrapping_add(4).wrapping_add((off as u32) << 1) & !1;
                self.cycles += 1;
                return Ok(2);
            }
            self.regs[15] = pc.wrapping_add(2);
            return Ok(1);
        }
        // format 18: unconditional branch
        if (instr >> 11) & 0x1F == 0x1C {
            let mut off = (instr & 0x7FF) as i32;
            if off & 0x400 != 0 { off -= 0x800; }
            self.regs[15] = pc.wrapping_add(4).wrapping_add((off as u32) << 1) & !1;
            self.cycles += 1;
            return Ok(2);
        }
        // format 4: ALU operations
        if (instr >> 10) & 0x3F == 0x10 {
            let op = (instr >> 6) & 0xF;
            let rs = ((instr >> 3) & 0x7) as usize;
            let rd = (instr & 0x7) as usize;
            let a = self.regs[rd];
            let b = self.regs[rs];
            let carry = self.cpsr & CPSR_C != 0;
            // Thumb 移位：raw=0 完全不動 C；ROR 的 32 倍數則 C=bit31。
            if (2..=4).contains(&op) || op == 0x7 {
                let raw = b & 0xFF;
                let (result, carry_out) = if raw == 0 {
                    (a, None)
                } else if op == 0x7 {
                    let amount = raw & 0x1F;
                    if amount == 0 {
                        (a, Some((a >> 31) & 1 != 0))
                    } else {
                        (a.rotate_right(amount), Some((a >> (amount - 1)) & 1 != 0))
                    }
                } else {
                    let (value, c) = self.shift(a, op - 2, raw, carry);
                    (value, Some(c))
                };
                self.regs[rd] = result;
                self.nz(result);
                if let Some(c) = carry_out { self.set_flag(CPSR_C, c); }
                self.regs[15] = pc.wrapping_add(2);
                return Ok(1);
            }
            let (mut result, write, logical) = match op {
                0x0 => (a & b, true, true),
                0x1 => (a ^ b, true, true),
                0x2 => { let (v,c)=self.shift(a,0,b & 0xFF,carry); self.set_flag(CPSR_C,c); (v,true,false) }
                0x3 => { let (v,c)=self.shift(a,1,b & 0xFF,carry); self.set_flag(CPSR_C,c); (v,true,false) }
                0x4 => { let (v,c)=self.shift(a,2,b & 0xFF,carry); self.set_flag(CPSR_C,c); (v,true,false) }
                0x5 => (a.wrapping_add(b).wrapping_add(u32::from(carry)), true, false),
                0x6 => (a.wrapping_sub(b).wrapping_sub(u32::from(!carry)), true, false),
                0x7 => { let (v,c)=self.shift(a,3,b & 0xFF,carry); self.set_flag(CPSR_C,c); (v,true,false) }
                0x8 => (a & b, false, true),
                0x9 => (0u32.wrapping_sub(b), true, false),
                0xA => (a.wrapping_sub(b), false, false),
                0xB => (a.wrapping_add(b), false, false),
                0xC => (a | b, true, true),
                0xD => (a.wrapping_mul(b), true, false),
                0xE => (a & !b, true, true),
                _ => (!b, true, true),
            };
            if op != 0x2 && op != 0x3 && op != 0x4 && op != 0x7 {
                self.nz(result);
            }
            if logical && op != 0x2 && op != 0x3 && op != 0x4 && op != 0x7 {
                self.set_flag(CPSR_C, carry);
            }
            if op == 0x5 || op == 0x6 || op == 0x9 || op == 0xA || op == 0xB {
                // NEG (0x9) 係 `0 - b`：C = no borrow = (b == 0)。
                // 之前用 `result < a`（a 係 rd 舊值）令 suite 的
                // `rsbs; adcs` 0/1 比較永遠得 0（列表全紅）。
                let carry_out = match op {
                    0x6 | 0xA => a >= b,
                    0x9 => b == 0,
                    _ => result < a,
                };
                self.set_flag(CPSR_C, carry_out);
                let overflow = match op {
                    0x5 | 0xB => ((a ^ result) & (b ^ result) & 0x8000_0000) != 0,
                    0x6 | 0xA => ((a ^ b) & (a ^ result) & 0x8000_0000) != 0,
                    _ => b == 0x8000_0000, // NEG
                };
                self.set_flag(CPSR_V, overflow);
            }
            if write { self.regs[rd] = result; }
            self.regs[15] = pc.wrapping_add(2);
            return Ok(1);
        }
        // format 5: high registers / BX
        if (instr >> 10) & 0x3F == 0x11 {
            let op = (instr >> 8) & 0x3;
            let h1 = (instr >> 7) & 1;
            let h2 = (instr >> 6) & 1;
            let rs = (((instr >> 3) & 0x7) | (h2 << 3)) as usize;
            let rd = ((instr & 0x7) | (h1 << 3)) as usize;
            if op == 3 {
                let target = self.regs[rs];
                if target & 1 != 0 { self.cpsr |= CPSR_T; self.regs[15] = target & !1; }
                else { self.cpsr &= !CPSR_T; self.regs[15] = target & !3; }
                self.cycles += 2;
                return Ok(2);
            }
            let a = self.regs[rd];
            let b = self.regs[rs];
            match op {
                0 => self.regs[rd] = a.wrapping_add(b),
                1 => { let r = a.wrapping_sub(b); self.nz(r); self.set_flag(CPSR_C, a >= b); }
                _ => { self.regs[rd] = b; if rd == 15 { self.regs[15] &= !1; } }
            }
            self.regs[15] = if rd == 15 { self.regs[15] } else { pc.wrapping_add(2) };
            return Ok(1);
        }
        // format 7: load/store register offset（bits 11-9 是 op3，不是 L/B 位）
        if (instr >> 12) & 0xF == 0x5 {
            let rd = (instr & 0x7) as usize;
            let rb = ((instr >> 3) & 0x7) as usize;
            let ro = ((instr >> 6) & 0x7) as usize;
            let addr = self.regs[rb].wrapping_add(self.regs[ro]);
            match (instr >> 9) & 0x7 {
                0 => bus.write32(addr, self.regs[rd]),                     // STR
                1 => self.write_half(bus, addr, self.regs[rd] as u16),     // STRH
                2 => bus.write8(addr, self.regs[rd] as u8),                // STRB
                3 => {                                                     // LDSB
                    let v = self.read_byte(bus, addr);
                    self.regs[rd] = if v & 0x80 != 0 { v | 0xFFFF_FF00 } else { v };
                }
                4 => self.regs[rd] = self.read_word(bus, addr),            // LDR
                5 => self.regs[rd] = self.read_half(bus, addr),            // LDRH
                6 => self.regs[rd] = self.read_byte(bus, addr),            // LDRB
                _ => {                                                     // LDSH
                    let v = if addr & 1 != 0 {
                        let byte = self.read_byte(bus, addr);
                        if byte & 0x80 != 0 { byte | 0xFFFF_FF00 } else { byte }
                    } else {
                        let half = self.read_half(bus, addr);
                        if half & 0x8000 != 0 { half | 0xFFFF_0000 } else { half }
                    };
                    self.regs[rd] = v;
                }
            }
            self.regs[15] = pc.wrapping_add(2);
            return Ok(3);
        }
        // format 9: immediate word/byte
        if (instr >> 13) & 0x7 == 0x3 {
            let rd = (instr & 0x7) as usize;
            let rb = ((instr >> 3) & 0x7) as usize;
            let off = (instr >> 6) & 0x1F;
            let byte = instr & (1 << 12) != 0;
            let addr = self.regs[rb].wrapping_add(if byte { off } else { off << 2 });
            if instr & (1 << 11) != 0 {
                self.regs[rd] = if byte { self.read_byte(bus, addr) } else { self.read_word(bus, addr) };
            } else if byte {
                bus.write8(addr, self.regs[rd] as u8);
            } else {
                bus.write32(addr, self.regs[rd]);
            }
            self.regs[15] = pc.wrapping_add(2);
            return Ok(if instr & (1 << 11) != 0 { 3 } else { 2 });
        }
        // format 10: immediate halfword
        if (instr >> 12) & 0xF == 0x8 {
            let rd = (instr & 0x7) as usize;
            let rb = ((instr >> 3) & 0x7) as usize;
            let addr = self.regs[rb].wrapping_add(((instr >> 6) & 0x1F) << 1);
            if instr & (1 << 11) != 0 { self.regs[rd] = self.read_half(bus, addr); }
            else { self.write_half(bus, addr, self.regs[rd] as u16); }
            self.regs[15] = pc.wrapping_add(2);
            return Ok(if instr & (1 << 11) != 0 { 3 } else { 2 });
        }
        // format 11: SP-relative
        if (instr >> 12) & 0xF == 0x9 {
            let rd = ((instr >> 8) & 0x7) as usize;
            let addr = self.regs[13].wrapping_add((instr & 0xFF) << 2);
            if instr & (1 << 11) != 0 { self.regs[rd] = self.read_word(bus, addr); }
            else { bus.write32(addr, self.regs[rd]); }
            self.regs[15] = pc.wrapping_add(2);
            return Ok(if instr & (1 << 11) != 0 { 3 } else { 2 });
        }
        // format 12: load address
        if (instr >> 12) & 0xF == 0xA {
            let rd = ((instr >> 8) & 0x7) as usize;
            let base = if instr & (1 << 11) != 0 { self.regs[13] } else { pc.wrapping_add(4) & !3 };
            self.regs[rd] = base.wrapping_add((instr & 0xFF) << 2);
            self.regs[15] = pc.wrapping_add(2);
            return Ok(1);
        }
        // format 13: add SP
        if (instr >> 8) & 0xFF == 0xB0 {
            let imm = (instr & 0x7F) << 2;
            if instr & (1 << 7) != 0 { self.regs[13] = self.regs[13].wrapping_sub(imm); }
            else { self.regs[13] = self.regs[13].wrapping_add(imm); }
            self.regs[15] = pc.wrapping_add(2);
            return Ok(1);
        }
        // format 14: push/pop
        if (instr >> 12) & 0xF == 0xB && instr & (1 << 10) != 0 {
            let load = instr & (1 << 11) != 0;
            let mut mask = instr & 0xFF;
            if instr & (1 << 8) != 0 { mask |= if load { 1 << 15 } else { 1 << 14 }; }
            let n = mask.count_ones();
            if load {
                let mut addr = self.regs[13];
                for reg in 0..16 {
                    if mask & (1 << reg) == 0 { continue; }
                    let value = self.read_word(bus, addr);
                    if reg == 15 { self.regs[15] = value & !1; } else { self.regs[reg] = value; }
                    addr = addr.wrapping_add(4);
                }
                self.regs[13] = self.regs[13].wrapping_add(4 * n);
            } else {
                let mut addr = self.regs[13].wrapping_sub(4 * n);
                self.regs[13] = addr;
                for reg in 0..16 {
                    if mask & (1 << reg) == 0 { continue; }
                    bus.write32(addr, self.regs[reg]);
                    addr = addr.wrapping_add(4);
                }
            }
            if !(load && mask & 0x8000 != 0) {
                self.regs[15] = pc.wrapping_add(2);
            }
            return Ok(if load { 5 + n } else { 2 + n });
        }
        // format 15: LDMIA/STMIA
        if (instr >> 12) & 0xF == 0xC {
            let rb = ((instr >> 8) & 0x7) as usize;
            let load = instr & (1 << 11) != 0;
            let list = instr & 0xFF;
            let mut addr = self.regs[rb];
            let start = addr;
            for reg in 0..8 {
                if list & (1 << reg) == 0 { continue; }
                if load { self.regs[reg] = self.read_word(bus, addr); }
                else { bus.write32(addr, self.regs[reg]); }
                addr = addr.wrapping_add(4);
            }
            if load && list & (1 << rb) == 0 {
                self.regs[rb] = addr;
            } else if !load {
                self.regs[rb] = addr;
            }
            let _ = start;
            self.regs[15] = pc.wrapping_add(2);
            return Ok(if load { 3 + list.count_ones() } else { 2 + list.count_ones() });
        }
        // format 17: SWI
        if (instr >> 12) & 0xF == 0xD && (instr >> 8) & 0xF == 0xF {
            self.regs[15] = pc.wrapping_add(2);
            self.hle_swi(bus, (instr & 0xFF) as u8)?;
            self.cycles += 2;
            return Ok(2);
        }
        // format 19: BL（一個 instruction，讀取第二個 halfword）
        if (instr >> 11) & 0x1F == 0x1E {
            let second = bus.read16(pc.wrapping_add(2)) as u32;
            let off = ((instr & 0x7FF) << 12) | ((second & 0x7FF) << 1);
            let signed = if off & 0x0040_0000 != 0 {
                (off | !0x007F_FFFF) as i32
            } else {
                off as i32
            };
            self.regs[14] = pc.wrapping_add(4) | 1;
            self.regs[15] = pc.wrapping_add(4).wrapping_add(signed as u32) & !1;
            return Ok(3);
        }
        Err(CpuError::Unsupported { pc, opcode: instr, thumb: true })
    }

    /// 套用 HLE／BIOS post-boot 的 CPU 狀態（規格 2.1.1）。
    pub fn apply_post_boot(&mut self) {
        *self = Cpu::new();
        self.regs = [0; 16];
        self.regs[13] = 0x0300_7F00;
        self.regs[15] = 0x0800_0000;
        self.cpsr = MODE_SYS;
        self.spsr = 0;
        self.banked_sp_lr[1] = [0x0300_7FA0, 0]; // IRQ
        self.banked_sp_lr[2] = [0x0300_7FE0, 0]; // SVC
        self.usr_sp = 0x0300_7F00;
        self.usr_lr = 0;
        self.halted = false;
        self.cycles = 0;
        self.nseq_fetch = false;
        self.irq_pending = false;
        self.irq_wait = -1;
        self.wait_irq = 0;
        self.resume_halt_irq = false;
        self.thumb_bl_high = None;
    }

    /// IRQ exception：vector 0x18，return address = 下一條 instruction + 4。
    pub fn enter_irq(&mut self, next_pc: u32) {
        self.enter_exception(MODE_IRQ, 0x18, next_pc.wrapping_add(4));
    }

    /// Python `check_irq()` 的 2-cycle pipeline 模型。回傳額外 cycle（0 = 未進場）。
    pub fn check_irq(&mut self, bus: &mut Bus, cycles: u32) -> u32 {
        let line = bus.ime && (bus.ie & bus.if_) != 0;
        self.irq_pending = line;
        if !line || self.cpsr & CPSR_I != 0 {
            self.irq_wait = -1;
            return 0;
        }
        if self.irq_wait < 0 {
            self.irq_wait = if bus.mgba_timing && !bus.functional { 5 } else { 2 };
            return 0;
        }
        self.irq_wait -= cycles.max(1) as i32;
        if self.irq_wait > 0 {
            return 0;
        }
        self.irq_wait = -1;
        let next_pc = self.regs[15];
        // IntrWait（SWI 0x04）期間仍然要服務 IRQ；hardware 會叫醒 CPU 行 handler，
        // handler 完成後若等緊嘅旗標未到就再 halt。之前喺 halt 狀態入面直接
        // enter_irq，但 halted 冇清 → CPU 卡死喺 handler 第一條指令，
        // 直到下一個（例：VBlank）旗標到才意外行返（rates.gba 聲效斷斷續續）。
        let was_halted = self.halted;
        if was_halted {
            self.halted = false;
            self.resume_halt_irq = self.wait_irq != 0;
        }
        self.enter_irq(next_pc);
        self.hle_irq_enter(bus);
        self.cycles += 4;
        4
    }

    /// BIOS 0x128：存 R0-R3/R12/LR、LR=0x138、PC=[03007FFC]。
    fn hle_irq_enter(&mut self, bus: &mut Bus) {
        let sp = self.regs[13].wrapping_sub(24);
        self.regs[13] = sp;
        for (slot, register) in [0usize, 1, 2, 3, 12].into_iter().enumerate() {
            bus.write32(sp + slot as u32 * 4, self.regs[register]);
        }
        bus.write32(sp + 20, self.regs[14]);
        self.regs[14] = 0x138;
        self.regs[15] = bus.read32(0x0300_7FFC) & !3;
    }

    fn hle_irq_return(&mut self, bus: &mut Bus) -> u32 {
        let sp = self.regs[13];
        for (slot, register) in [0usize, 1, 2, 3, 12].into_iter().enumerate() {
            self.regs[register] = bus.read32(sp + slot as u32 * 4);
        }
        let saved_lr = bus.read32(sp + 20);
        self.regs[13] = sp.wrapping_add(24);
        let new_cpsr = self.spsr;
        let new_mode = new_cpsr & CPSR_MODE_MASK;
        self.save_current_bank();
        self.switch_mode(new_mode);
        self.cpsr = new_cpsr;
        self.regs[15] = saved_lr.wrapping_sub(4)
            & if new_cpsr & CPSR_T != 0 { !1 } else { !3 };
        // IntrWait 期間被 IRQ 叫醒：handler 完成後如等緊嘅旗標未到，回復 halt。
        if self.resume_halt_irq {
            self.resume_halt_irq = false;
            if self.wait_irq != 0 {
                if (bus.if_ | bus.irq_seen) & self.wait_irq == 0 {
                    self.halted = true;
                } else {
                    let ram = bus.read16(0x0300_7FF8);
                    bus.write16(0x0300_7FF8, ram & !self.wait_irq);
                    bus.irq_seen &= !self.wait_irq;
                }
            }
        }
        self.cycles += 3;
        3
    }

    /// 指令 fetch 的 cycle（Python `cpu/cycles.py::_fetch` 的移植）：
    /// ROM 且 WAITCNT bit14（prefetch）開啟 → 1 cycle；否則依序性用
    /// `access_cost`。ROM 帶 internal cycle 的 opcode 會觸發 prefetch
    /// disable bug（fetch 由 1S 變 1N）。
    fn fetch_cost(&mut self, bus: &mut Bus, pc: u32, width: u32, internal: bool) -> u32 {
        let mut seq = true;
        if self.nseq_fetch {
            self.nseq_fetch = false;
            seq = false;
        }
        let page = pc >> 24;
        let cost = if (0x08..=0x0D).contains(&page) {
            if bus.prefetch_enabled() {
                1
            } else if internal && seq {
                bus.access_cost(pc, width, false)
            } else {
                bus.access_cost(pc, width, seq)
            }
        } else {
            bus.access_cost(pc, width, true)
        };
        cost
    }

    fn units_cost(&mut self, bus: &mut Bus, base: u32, count: u32, width: u32) -> u32 {
        let mut cost = bus.access_cost(base & !3, width, false);
        for index in 1..count {
            cost += bus.access_cost((base + index * width) & !3, width, true);
        }
        cost
    }

    /// Legacy data access：`access_cost(nonseq)`。
    fn data_cost(&mut self, bus: &mut Bus, _pc: u32, address: u32, width: u32) -> u32 {
        bus.access_cost(address, width, false)
    }

    /// branch／PC 寫入的 pipeline 重填（mGBA `ARMWritePC` 的 `N+S`）。
    /// `refill_timing` 係「Legacy + 分佈」實驗：fetch/data base 照舊，只補
    /// refill 成本，用嚟分辨「總量錯」同「分佈錯」。
    fn refill_seq(&self, bus: &Bus, address: u32, width: u32) -> u32 {
        if bus.mgba_timing || bus.refill_timing {
            bus.access_cost(address, width, true)
        } else {
            0
        }
    }

    /// L/S 之後補 `N-S`（mGBA post-body）；Legacy 模式唔補。
    fn post_delta(&self, bus: &Bus, pc: u32, width: u32) -> u32 {
        if bus.mgba_timing || bus.refill_timing {
            bus.mgba_refill_delta(pc, width)
        } else {
            0
        }
    }

    /// LDM/STM 的每-unit data cost（mGBA 每個 unit `wait+2`）。
    fn units_cost2(&mut self, bus: &mut Bus, pc: u32, base: u32, count: u32, width: u32) -> u32 {
        let mut cost = self.data_cost(bus, pc, base & !3, width);
        for index in 1..count {
            let address = (base + index * width) & !3;
            cost += bus.access_cost(address, width, true)
                + u32::from(bus.mgba_timing);
        }
        cost
    }

    /// ARM7TDMI Booth multiplier 的 C flag（全 4 個內部 cycle 時）。
    fn multiply_carry_simple(multiplier: u32) -> bool {
        (multiplier >> 30) == 2
    }

    /// Booth multiplier 提早終止時，由 low partial result 推出 C flag。
    fn multiply_carry_lo(multiplicand: u32, multiplier: u32, accum: u32) -> bool {
        // 最低位設 1，令 negation 時 upper bits 反轉；呢個 bit 唔會傳到 carry。
        let multiplicand = multiplicand | 1;

        let booth: i32 = ((multiplier as i32) << 31) >> 31;
        let carry = multiplicand.wrapping_mul(booth as u32);
        let sum = carry.wrapping_add(accum);

        let mut current_booth = booth;
        let mut current_carry = carry;
        let mut current_sum = sum;
        let mut current_accum = accum;

        let mut shift: i32 = 29;
        loop {
            for _ in 0..4 {
                let next_booth: i32 = ((multiplier as i32) << shift) >> shift;
                let factor = next_booth.wrapping_sub(current_booth);
                current_booth = next_booth;
                let addend = multiplicand.wrapping_mul(factor as u32);
                current_accum ^= current_carry ^ addend;
                current_sum = current_sum.wrapping_add(addend);
                current_carry = current_sum.wrapping_sub(current_accum);
                shift -= 2;
            }
            if current_booth == multiplier as i32 {
                break;
            }
        }

        (current_carry >> 31) != 0
    }

    /// Long multiply 用全 4 個 Booth cycle 時，由 high partial result 推出 C flag。
    fn multiply_carry_hi(
        multiplicand: u32,
        multiplier: u32,
        accum_hi: u32,
        signed: bool,
    ) -> bool {
        // 只有最後 3 次 Booth iteration（multiplier 高 6 bits）影響 bit63 carry。
        let (md, mp) = if signed {
            (
                (multiplicand as i32 >> 6) as u32,
                (multiplier as i32 >> 26) as u32,
            )
        } else {
            (multiplicand >> 6, multiplier >> 26)
        };
        let md = md | 1;

        let carry = (!accum_hi) & 0x2000_0000;
        let accum = accum_hi.wrapping_sub(0x0800_0000);

        let booth0: i32 = ((mp as i32) << 27) >> 27;
        let booth1: i32 = ((mp as i32) << 29) >> 29;
        let booth2: i32 = ((mp as i32) << 31) >> 31;
        let factor0 = (mp as i32).wrapping_sub(booth0) as u32;
        let factor1 = booth0.wrapping_sub(booth1) as u32;
        let factor2 = booth1.wrapping_sub(booth2) as u32;

        let addend2 = md.wrapping_mul(factor2);
        let accum = accum.wrapping_sub(addend2 & 0x1000_0000);

        let addend1 = md.wrapping_mul(factor1);
        let accum = accum.wrapping_sub(addend1 & 0x4000_0000);

        let sum = accum.wrapping_add(addend1 & 0x2000_0000);
        let accum = accum.wrapping_sub(carry);

        let addend0 = md.wrapping_mul(factor0);
        let sum = sum.wrapping_add(addend0 & 0x4000_0000);

        ((sum ^ accum) >> 31) != 0
    }

    fn mul_m(value: u32, signed: bool) -> u32 {
        let check = |v: u32, bits: u32| -> bool {
            v == 0 || (signed && v == ((1u32 << bits) - 1))
        };
        if check((value >> 8) & 0x00FF_FFFF, 24) { 1 }
        else if check((value >> 16) & 0xFFFF, 16) { 2 }
        else if check((value >> 24) & 0xFF, 8) { 3 }
        else { 4 }
    }

    fn arm_transfer_offset(&self, instr: u32) -> u32 {
        if instr & (1 << 25) != 0 {
            let rm = self.regs[(instr & 0xF) as usize];
            let kind = (instr >> 5) & 3;
            let amount = (instr >> 7) & 0x1F;
            let carry = self.cpsr & CPSR_C != 0;
            if kind == 3 && amount == 0 {
                // 位移量 0 的 ROR 編碼 = RRX（C 進 bit31）
                ((u32::from(carry)) << 31) | (rm >> 1)
            } else {
                self.shift(rm, kind, amount, carry).0
            }
        } else {
            instr & 0xFFF
        }
    }

    fn arm_addr(&mut self, bus: &mut Bus, pc: u32, instr: u32) -> u32 {
        let rn = ((instr >> 16) & 0xF) as usize;
        let mut base = self.regs[rn];
        if rn == 15 { base = base.wrapping_add(8); }
        let offset = self.arm_transfer_offset(instr);
        if instr & (1 << 23) != 0 {
            base = base.wrapping_add(offset);
        } else {
            base = base.wrapping_sub(offset);
        }
        if instr & (1 << 24) == 0 { base = self.regs[rn]; }
        let _ = pc;
        base
    }

    fn arm_addr_h(&mut self, bus: &mut Bus, instr: u32) -> u32 {
        let rn = ((instr >> 16) & 0xF) as usize;
        let mut base = self.regs[rn];
        if rn == 15 { base = base.wrapping_add(8); }
        let offset = if instr & (1 << 22) != 0 {
            (((instr >> 8) & 0xF) << 4) | (instr & 0xF)
        } else {
            self.regs[(instr & 0xF) as usize]
        };
        if instr & (1 << 23) != 0 { base.wrapping_add(offset) } else { base.wrapping_sub(offset) }
    }

    fn set_fetch_seq(&mut self, instr: u32, thumb: bool) {
        let mut sequential = false;
        if thumb {
            let op = (instr >> 11) & 0x1F;
            if op == 0x8 {
                let alu = (instr >> 6) & 0xF;
                sequential = matches!(alu, 0xD | 0x2 | 0x3 | 0x4 | 0x7);
            } else if matches!(op, 0x9 | 0xB | 0xD | 0xF | 0x11 | 0x13 | 0x14 | 0x16 | 0x18 | 0x1A | 0x1B) {
                sequential = true;
            } else if op == 0x17 || (op == 0x16 && instr & 0x400 != 0) {
                sequential = true;
            }
        } else {
            if instr & 0x0FFF_FFF0 == 0x012F_FF10 || instr & 0x0FFF_FFF0 == 0x012F_FF30 {
                self.nseq_fetch = false;
                return;
            }
            if (instr >> 25) & 0x7 == 0x4
                || (instr >> 26) & 0x3 == 0x1
                || instr & 0x0E00_0F90 == 0x0000_0090
                || instr & 0x0FC0_00F0 == 0x0000_0090
                || instr & 0x0F80_00F0 == 0x0080_0090
                || ((instr >> 25) & 0x7 == 0 && matches!((instr >> 4) & 0xF, 0xB | 0xD | 0xF)) {
                sequential = true;
            } else if (instr >> 26) & 0x3 == 0 {
                sequential = (instr >> 25) & 1 == 0 && (instr >> 4) & 1 != 0;
            }
        }
        self.nseq_fetch = sequential;
    }

    fn io_word_extra(address: u32) -> bool {
        (0x0400_0000..0x0400_03FF).contains(&address)
            && !(0x0400_0100..0x0400_0110).contains(&address)
            && !(0x0400_0200..0x0400_0300).contains(&address)
    }

    /// mGBA 式 ARM timing（`--mgba` 分支）。
    /// 每條指令 base = `1 + activeSeqCycles32`（我哋 `access_cost` 已等值）；
    /// L/S 後 `N32-S32`、branch `2+N32+S32`、LDM/STM 逐 register wait、
    /// multiply 走 `stall()`，全部用 `bus.mgba_*` 的 mGBA 公約。
    fn arm_cycles_mgba(&mut self, bus: &mut Bus, pc: u32, instr: u32) -> u32 {
        let pc = pc & !3;
        let base = bus.access_cost(pc, 4, true) as i64;
        // B / BL
        if (instr >> 25) & 0x7 == 0x5 {
            let mut off = (instr & 0x00FF_FFFF) as i32;
            if off & 0x0080_0000 != 0 { off -= 0x0100_0000; }
            let target = pc.wrapping_add(8).wrapping_add((off << 2) as u32);
            return (base + self.mgba_write_pc(bus, target, 4) as i64) as u32;
        }
        // SWI／coprocessor
        if (instr >> 24) & 0xF == 0xF {
            if instr & 0x0F00_0000 == 0x0F00_0000 {
                let number = (instr >> 16) & 0xFF;
                return (base + self.mgba_swi_cycles(bus, pc, number, false)).max(1) as u32;
            }
            return base as u32;
        }
        // BX / BLX（register）
        if instr & 0x0FFF_FFF0 == 0x012F_FF10 {
            let target = self.regs[(instr & 0xF) as usize];
            let width = if target & 1 != 0 { 2 } else { 4 };
            return (base + self.mgba_write_pc(bus, target & !1, width) as i64) as u32;
        }
        // MRS / MSR（register、CPSR/SPSR）
        if instr & 0x0FB0_F000 == 0x0120_F000 || instr & 0x0FB0_F000 == 0x0320_F000 {
            return base as u32;
        }
        if instr & 0x0FFF_0FFF == 0x010F_0000 || instr & 0x0FFF_0FFF == 0x014F_0000 {
            return base as u32;
        }
        // LDM / STM
        if (instr >> 25) & 0x7 == 0x4 {
            let list = instr & 0xFFFF;
            let n = list.count_ones().max(1);
            let address = self.regs[((instr >> 16) & 0xF) as usize] & !3;
            let delta = self.mgba_delta(bus, pc, 4) as i64;
            if instr & (1 << 20) != 0 {
                let mut cost = base + delta + self.mgba_multiple_cost(bus, pc, true, address, n, true);
                if list & 0x8000 != 0 {
                    cost += self.mgba_write_pc(bus, self.regs[15] & !3, 4) as i64;
                }
                return cost.max(1) as u32;
            }
            return (base + delta + self.mgba_multiple_cost(bus, pc, true, address, n, false)).max(1) as u32;
        }
        // LDR / STR（word／byte）
        if (instr >> 26) & 0x3 == 0x1 {
            let rd = (instr >> 12) & 0xF;
            let addr = self.arm_addr(bus, pc, instr);
            let width = if instr & (1 << 22) != 0 { 1 } else { 4 };
            let load = instr & (1 << 20) != 0;
            let data = if load {
                self.mgba_data(bus, pc, true, addr, width) as i64
            } else {
                self.mgba_store(bus, pc, true, addr, width) as i64
            };
            let mut cost = base + data + self.mgba_delta(bus, pc, 4) as i64;
            if load && rd == 15 {
                cost += self.mgba_write_pc(bus, self.regs[15] & !3, 4) as i64;
            }
            return cost.max(1) as u32;
        }
        // MUL / MLA / SMULL / SMLAL / UMULL / UMLAL
        if instr & 0x0F80_00F0 == 0x0080_0090 {
            let rs = self.regs[((instr >> 8) & 0xF) as usize];
            // Multiply long：bit22=S、bit21=A；WAIT = A ? 2 : 1。
            let signed = instr & (1 << 22) != 0;
            let wait = Self::mgba_mul_wait(rs, signed, if instr & (1 << 21) != 0 { 2 } else { 1 }) as i32;
            return (base
                + self.mgba_stall(bus, pc, true, wait) as i64
                + self.mgba_delta(bus, pc, 4) as i64)
                .max(1) as u32;
        }
        if instr & 0x0FC0_00F0 == 0x0000_0090 {
            let rs = self.regs[((instr >> 8) & 0xF) as usize];
            // MUL/MLA：WAIT = A ? 1 : 0。
            let wait = Self::mgba_mul_wait(rs, true, if instr & (1 << 21) != 0 { 1 } else { 0 }) as i32;
            return (base
                + self.mgba_stall(bus, pc, true, wait) as i64
                + self.mgba_delta(bus, pc, 4) as i64)
                .max(1) as u32;
        }
        // LDRH / STRH / LDRSB / LDRSH
        if matches!((instr >> 4) & 0xF, 0xB | 0xD | 0xF) {
            let addr = self.arm_addr_h(bus, instr);
            let width = if (instr >> 4) & 0xF == 0xD { 1 } else { 2 };
            let rd = (instr >> 12) & 0xF;
            let load = instr & (1 << 20) != 0;
            let data = if load {
                self.mgba_data(bus, pc, true, addr, width) as i64
            } else {
                self.mgba_store(bus, pc, true, addr, width) as i64
            };
            let mut cost = base + data + self.mgba_delta(bus, pc, 4) as i64;
            if load && rd == 15 {
                cost += self.mgba_write_pc(bus, self.regs[15] & !3, 4) as i64;
            }
            return cost.max(1) as u32;
        }
        // SWP / SWPB
        if instr & 0x0E00_0F90 == 0x0000_0090 {
            let addr = self.regs[((instr >> 16) & 0xF) as usize];
            let width = if instr & (1 << 22) != 0 { 1 } else { 4 };
            return (base
                + self.mgba_data(bus, pc, true, addr, width) as i64
                + self.mgba_store(bus, pc, true, addr, width) as i64)
                .max(1) as u32;
        }
        // Data processing
        if (instr >> 26) & 0x3 == 0 {
            let rd = (instr >> 12) & 0xF;
            let mut cost = base;
            if (instr >> 25) & 1 == 0 && (instr >> 4) & 1 != 0 {
                cost += 1;
            }
            if rd == 15 {
                cost += self.mgba_write_pc(bus, self.regs[15] & !3, 4) as i64;
            }
            return cost.max(1) as u32;
        }
        base.max(1) as u32
    }

    /// mGBA ARM `ARM_WAIT_SMUL/UMUL` 的 wait 值（未經 stall）。
    fn mgba_mul_wait(value: u32, signed: bool, wait: u32) -> u32 {
        let check = |v: u32, bits: u32| -> bool {
            v == 0 || (signed && v == ((1u32 << bits) - 1))
        };
        if check((value >> 8) & 0x00FF_FFFF, 24) {
            wait + 1
        } else if check((value >> 16) & 0xFFFF, 16) {
            wait + 2
        } else if check((value >> 24) & 0xFF, 8) {
            wait + 3
        } else {
            wait + 4
        }
    }

    /// mGBA `ARMWritePC`／`ThumbWritePC`：`2 + N + S`（我哋公約相加）。
    fn mgba_write_pc(&self, bus: &Bus, target: u32, width: u32) -> u32 {
        bus.access_cost(target, width, false) + bus.access_cost(target, width, true)
    }

    /// mGBA `GBAMemoryStall`；`pc` 係指令位址，mGBA 執行中的 PC 係 A+8（ARM）
    /// 或 A+4（Thumb）。
    fn mgba_stall(&mut self, bus: &mut Bus, pc: u32, arm: bool, wait: i32) -> i32 {
        bus.mgba_stall(pc.wrapping_add(if arm { 8 } else { 4 }), wait)
    }

    /// LDM/STM 成本。
    ///
    /// * 同一 region：照 mGBA `GBALoadMultiple` 的 formula，
    ///   `wait = n*S32 + (load?1:0) + S32 - N32`，再經 `GBAMemoryStall`
    ///   （prefetch on 會吸收部分 wait，甚至變負）。
    /// * 跨區（例如 overflow 測試 OAM→ROM）：mGBA 只用起始 region 會錯，
    ///   所以逐 register 計 nonseq／seq。
    fn mgba_multiple_cost(
        &mut self,
        bus: &mut Bus,
        pc: u32,
        arm: bool,
        start: u32,
        count: u32,
        load: bool,
    ) -> i64 {
        let count = count.max(1);
        let end = start.wrapping_add((count - 1) * 4);
        if (start >> 24) == (end >> 24) {
            let seq = bus.access_cost(start, 4, true) as i64;
            let nonseq = bus.access_cost(start, 4, false) as i64;
            let wait = seq * count as i64 + i64::from(load) + seq - nonseq;
            let stall_pc = pc.wrapping_add(if arm { 8 } else { 4 });
            return bus.mgba_stall(stall_pc, wait as i32) as i64;
        }
        let mut sum = 0i64;
        let mut prev = start;
        for index in 0..count {
            let addr = start.wrapping_add(index * 4);
            let seq = index > 0 && addr == prev.wrapping_add(4) && (addr >> 24) == (prev >> 24);
            sum += bus.access_cost(addr, 4, seq) as i64;
            prev = addr;
        }
        sum + i64::from(load)
    }

    /// mGBA data access，已轉做 mGBA 公約。
    fn mgba_data(&mut self, bus: &mut Bus, pc: u32, arm: bool, address: u32, width: u32) -> i32 {
        let pc = pc.wrapping_add(if arm { 8 } else { 4 });
        bus.mgba_data_cost(pc, address, width)
    }

    /// mGBA store access（region wait + 1 + stall）。
    fn mgba_store(&mut self, bus: &mut Bus, pc: u32, arm: bool, address: u32, width: u32) -> i32 {
        let pc = pc.wrapping_add(if arm { 8 } else { 4 });
        bus.mgba_store_cost(pc, address, width)
    }

    /// code region 的 `N32-S32`（我哋 `access_cost` 同公約，差額相同）。
    fn mgba_delta(&self, bus: &Bus, pc: u32, width: u32) -> u32 {
        bus.access_cost(pc, width, false)
            .saturating_sub(bus.access_cost(pc, width, true))
    }

    /// mGBA `GBASwi16` 的 BIOS stall（Div／Sqrt／ArcTan／ArcTan2）。
    fn mgba_bios_stall(&self, number: u32) -> Option<i64> {
        match number {
            0x06 => {
                let num = self.regs[0] as i32;
                let denom = self.regs[1] as i32;
                Some(Self::div_stall(num, denom))
            }
            0x07 => {
                let num = self.regs[1] as i32;
                let denom = self.regs[0] as i32;
                Some(Self::div_stall(num, denom))
            }
            0x08 => Some(Self::sqrt_stall(self.regs[0])),
            0x09 => Some(Self::arctan_stall(self.regs[0] as i32) as i64),
            0x0A => {
                let x = self.regs[0] as i32;
                let y = self.regs[1] as i32;
                Some(Self::arctan2_stall(x, y) as i64)
            }
            _ => None,
        }
    }

    fn div_stall(num: i32, denom: i32) -> i64 {
        let loops = (denom as u32).leading_zeros() as i64 - (num as u32).leading_zeros() as i64;
        let loops = loops.max(1);
        4 + 13 * loops + 7
    }

    fn mul_wait_signed(r: i32) -> i64 {
        let r = r as u32;
        if (r & 0xFFFF_FF00) == 0xFFFF_FF00 || r & 0xFFFF_FF00 == 0 {
            1
        } else if (r & 0xFFFF_0000) == 0xFFFF_0000 || r & 0xFFFF_0000 == 0 {
            2
        } else if (r & 0xFF00_0000) == 0xFF00_0000 || r & 0xFF00_0000 == 0 {
            3
        } else {
            4
        }
    }

    fn arctan_stall(i: i32) -> i64 {
        let mut cycles = 37i64;
        let i64v = i as i64;
        cycles += Self::mul_wait_signed((i64v * i64v) as i32);
        let mut a = (-((i as i64 * i as i64) >> 14)) as i32;
        cycles += Self::mul_wait_signed((0xA9i64 * a as i64) as i32);
        let mut b = (((0xA9i64 * a as i64) >> 14) + 0x390) as i32;
        for constant in [0x91C, 0xFB6, 0x16AA, 0x2081, 0x3651, 0xA2F9] {
            cycles += Self::mul_wait_signed((b as i64 * a as i64) as i32);
            b = (((b as i64 * a as i64) >> 14) + constant) as i32;
        }
        let _ = &mut a;
        cycles
    }

    fn arctan2_stall(x: i32, y: i32) -> i64 {
        if y == 0 || x == 0 {
            return 11;
        }
        let ax = (x as i64).abs();
        let ay = (y as i64).abs();
        let value = if y >= 0 {
            if x >= 0 {
                if ax >= ay { (y as i64 * 16384) / x as i64 } else { 0 }
            } else if ax >= ay {
                (y as i64 * 16384) / x as i64
            } else {
                (x as i64 * 16384) / y as i64
            }
        } else if x <= 0 {
            if ax > ay { (y as i64 * 16384) / x as i64 } else { 0 }
        } else if ax >= ay {
            (y as i64 * 16384) / x as i64
        } else {
            (x as i64 * 16384) / y as i64
        };
        // 化簡：只有喺真正落入 _ArcTan 的分支才計 cycles；其餘 11。
        if value == 0 {
            11
        } else {
            Self::arctan_stall(value as i32)
        }
    }

    fn sqrt_stall(x: u32) -> i64 {
        if x == 0 {
            return 53;
        }
        let mut cycles = 15i64;
        let mut upper = x;
        let mut bound = 1u32;
        while bound < upper {
            upper >>= 1;
            bound <<= 1;
            cycles += 6;
        }
        loop {
            cycles += 6;
            upper = x;
            let mut accum = 0u32;
            let mut lower = bound;
            loop {
                cycles += 5;
                let old_lower = lower;
                if lower <= upper >> 1 {
                    lower <<= 1;
                }
                if old_lower >= upper >> 1 {
                    break;
                }
            }
            loop {
                cycles += 8;
                accum <<= 1;
                if upper >= lower {
                    accum += 1;
                    upper -= lower;
                }
                if lower == bound {
                    break;
                }
                lower >>= 1;
            }
            let old_bound = bound;
            bound += accum;
            bound >>= 1;
            if bound >= old_bound {
                bound = old_bound;
                break;
            }
        }
        cycles
    }

    /// SWI 的 mGBA cycle：HLE stall 或「非 HLE」固定開銷。
    /// 純 HLE 的 SWI profile：mGBA 會執行 BIOS stub（`hle-bios.s` 的
    /// `swiBase`／`StallCall`）並補償 18 cycles；我哋唔執行 BIOS 程式碼，
    /// 所以喺 HLE 直接加返 entry + stub + exit 的固定成本。數值係實測校準
    /// （見 docs/architecture/TIMING.md 4e／4f）：Thumb 同 ARM 32-bit fetch
    /// 成本唔同，GamePak 同內部 RAM 亦唔同。
    fn hle_swi_profile(next: u32, width: u32, waitcnt: u16) -> i64 {
        let thumb = width == 2;
        let gamepak = matches!(next >> 24, 0x08..=0x0D);
        let mut profile = match next >> 24 {
            0x02 => if thumb { 45 } else { 44 },        // EWRAM
            0x03 => if thumb { 43 } else { 42 },        // IWRAM
            0x08..=0x0D => 47,                          // GamePak／ROM
            _ => if thumb { 45 } else { 44 },
        };
        // WS0 first-access 較短的 config（suite 的 `.N.`／`PN.`／`.NS`／`PNS`，
        // WAITCNT bit2）return refill 少 1 cycle（實測校準，見 TIMING.md 4f）。
        if gamepak && waitcnt & 0x0004 != 0 {
            profile -= 1;
        }
        profile
    }

    /// CpuSet（0x0B）／CpuFastSet（0x0C）的搬運成本。
    ///
    /// mGBA 由 BIOS stub 的搬運 loop 產生時間（`hle-bios.s` 的 `CpuSet`／
    /// `CpuFastSet`）；我哋純 HLE，所以按 element 數量計：32-bit copy 實測
    /// 256 words ≈ 3341 cycles（≈13/word）。fill 模式只寫唔讀，16-bit 模式
    /// 每個 element 成本約一半（見 TIMING.md 4g）。
    fn hle_cpuset_transfer(src: u32, dst: u32, control: u32, fast: bool) -> i64 {
        let _ = (src, dst);
        let count = (control & 0x001F_FFFF) as i64;
        let fill = control & 0x0100_0000 != 0;
        let width32 = control & 0x0400_0000 != 0;
        let units = if fast { count.max(1) } else { count.max(1) };
        let per_unit = match (width32, fill) {
            (true, false) => 25,
            (true, true) => 16,
            (false, false) => 13,
            (false, true) => 8,
        };
        13 + units * per_unit
    }

    fn mgba_swi_cycles(&mut self, bus: &mut Bus, pc: u32, number: u32, thumb: bool) -> i64 {
        if number == 0x0B || number == 0x0C {
            let width = if thumb { 2 } else { 4 };
            let nonseq = bus.access_cost(pc, 2, false) as i64;
            return 45
                + nonseq
                + bus.access_cost(pc, width, false) as i64
                + bus.access_cost(pc, width, true) as i64
                + Self::hle_cpuset_transfer(self.regs[0], self.regs[1], self.regs[2], number == 0x0C);
        }
        if let Some(stall) = self.mgba_bios_stall(number) {
            if stall >= 18 {
                let width = if thumb { 2 } else { 4 };
                let next = pc.wrapping_add(width) & !(width - 1);
                return stall
                    + Self::hle_swi_profile(next, width, bus.waitcnt())
                    + self.mgba_write_pc(bus, next, width) as i64;
            }
            return stall;
        }
        let nonseq = bus.access_cost(pc, 2, false) as i64;
        let base = if thumb { 2 } else { 4 };
        45 + nonseq
            + bus.access_cost(pc, base, false) as i64
            + bus.access_cost(pc, base, true) as i64
    }

    pub fn arm_cycles(&mut self, bus: &mut Bus, pc: u32, instr: u32) -> u32 {
        if bus.mgba_timing && !bus.functional {
            return self.arm_cycles_mgba(bus, pc, instr);
        }
        let cost = self.arm_cycles_calc(bus, pc, instr);
        self.set_fetch_seq(instr, false);
        cost
    }

    fn arm_cycles_calc(&mut self, bus: &mut Bus, pc: u32, instr: u32) -> u32 {
        let pc = pc & !3;
        if (instr >> 25) & 0x7 == 0x5 {
            let mut off = (instr & 0x00FF_FFFF) as i32;
            if off & 0x0080_0000 != 0 { off -= 0x0100_0000; }
            let target = pc.wrapping_add(8).wrapping_add((off << 2) as u32);
            return self.fetch_cost(bus, pc, 4, false) + bus.access_cost(target, 4, false) + self.refill_seq(bus, target, 4);
        }
        if (instr >> 24) & 0xF == 0xF {
            return 2 * self.fetch_cost(bus, pc, 4, false) + 1;
        }
        if instr & 0x0FFF_FFF0 == 0x012F_FF10 {
            let target = self.regs[(instr & 0xF) as usize] & !3;
            return self.fetch_cost(bus, pc, 4, false) + bus.access_cost(target, 4, false) + self.refill_seq(bus, target, 4);
        }
        if instr & 0x0FB0_F000 == 0x0120_F000 || instr & 0x0FB0_F000 == 0x0320_F000 {
            return self.fetch_cost(bus, pc, 4, false);
        }
        if instr & 0x0FFF_0FFF == 0x010F_0000 || instr & 0x0FFF_0FFF == 0x014F_0000 {
            return self.fetch_cost(bus, pc, 4, false);
        }
        if (instr >> 25) & 0x7 == 0x4 {
            let n = (instr & 0xFFFF).count_ones().max(1);
            let rn = self.regs[((instr >> 16) & 0xF) as usize] & !3;
            if instr & (1 << 20) != 0 {
                let mut cost = self.fetch_cost(bus, pc, 4, true) + self.units_cost2(bus, pc, rn, n, 4) + (n - 1);
                if instr & 0x8000 != 0 { cost += 2; }
                else { cost += 1; }
                cost += self.post_delta(bus, pc, 4);
                return cost;
            }
            return self.fetch_cost(bus, pc, 4, true) + self.units_cost2(bus, pc, rn, n, 4) + bus.access_cost(rn, 4, false) + self.post_delta(bus, pc, 4);
        }
        if (instr >> 26) & 0x3 == 0x1 {
            let rd = (instr >> 12) & 0xF;
            let addr = self.arm_addr(bus, pc, instr);
            if instr & (1 << 20) != 0 {
                let width = if instr & (1 << 22) != 0 { 1 } else { 4 };
                let mut cost = self.fetch_cost(bus, pc, 4, true)
                    + self.data_cost(bus, pc, addr, width) + 1 + self.post_delta(bus, pc, 4);
                if rd == 15 {
                    cost += self.fetch_cost(bus, pc, 4, false) + bus.access_cost(pc, 4, false) + self.refill_seq(bus, pc, 4);
                }
                return cost;
            }
            let width = if instr & (1 << 22) != 0 { 1 } else { 4 };
            let mut cost = self.fetch_cost(bus, pc, 4, true)
                + self.data_cost(bus, pc, addr, width) + self.post_delta(bus, pc, 4);
            if width == 4 && Self::io_word_extra(addr) { cost += 1; }
            return cost;
        }
        if instr & 0x0F80_00F0 == 0x0080_0090 {
            let rs = self.regs[((instr >> 8) & 0xF) as usize];
            let signed = instr & (1 << 22) != 0;
            return self.fetch_cost(bus, pc, 4, true) + Self::mul_m(rs, signed)
                + if instr & (1 << 21) != 0 { 2 } else { 1 };
        }
        if instr & 0x0FC0_00F0 == 0x0000_0090 {
            let rs = self.regs[((instr >> 8) & 0xF) as usize];
            return self.fetch_cost(bus, pc, 4, true) + Self::mul_m(rs, false)
                + if instr & (1 << 21) != 0 { 1 } else { 0 };
        }
        if matches!((instr >> 4) & 0xF, 0xB | 0xD | 0xF) {
            let addr = self.arm_addr_h(bus, instr);
            let width = if (instr >> 4) & 0xF == 0xD { 1 } else { 2 };
            if instr & (1 << 20) != 0 {
                let mut cost = self.fetch_cost(bus, pc, 4, true)
                    + self.data_cost(bus, pc, addr, width) + 1 + self.post_delta(bus, pc, 4);
                if (instr >> 12) & 0xF == 15 {
                    cost += self.fetch_cost(bus, pc, 4, false) + bus.access_cost(pc, 4, false) + self.refill_seq(bus, pc, 4);
                }
                return cost;
            }
            return self.fetch_cost(bus, pc, 4, true)
                + self.data_cost(bus, pc, addr, 2) + self.post_delta(bus, pc, 4);
        }
        if instr & 0x0E00_0F90 == 0x0000_0090 {
            let addr = self.regs[((instr >> 16) & 0xF) as usize].wrapping_add(self.regs[(instr & 0xF) as usize]);
            return self.fetch_cost(bus, pc, 4, true) + 2 * self.data_cost(bus, pc, addr, 4) + 1 + self.post_delta(bus, pc, 4);
        }
        if (instr >> 26) & 0x3 == 0 {
            let rd = (instr >> 12) & 0xF;
            let mut cost = if (instr >> 25) & 1 == 0 && (instr >> 4) & 1 != 0 {
                self.fetch_cost(bus, pc, 4, true) + 1
            } else {
                self.fetch_cost(bus, pc, 4, false)
            };
            if rd == 15 {
                cost += self.fetch_cost(bus, pc, 4, false) + bus.access_cost(pc, 4, false) + self.refill_seq(bus, pc, 4);
            }
            return cost;
        }
        self.fetch_cost(bus, pc, 4, false)
    }

    pub fn thumb_cycles(&mut self, bus: &mut Bus, pc: u32, instr: u32) -> u32 {
        if bus.mgba_timing && !bus.functional {
            return self.thumb_cycles_mgba(bus, pc, instr);
        }
        let cost = self.thumb_cycles_calc(bus, pc, instr);
        self.set_fetch_seq(instr, true);
        cost
    }

    /// mGBA 式 Thumb timing（`--mgba` 分支）：base = `1 + activeSeqCycles16`，
    /// L/S 後 `N16-S16`、branch `2+N16+S16`、LDM/STM 逐 register wait、
    /// multiply 走 `stall()`。
    fn thumb_cycles_mgba(&mut self, bus: &mut Bus, pc: u32, instr: u32) -> u32 {
        let pc = pc & !1;
        let base = bus.access_cost(pc, 2, true) as i64;
        let op = (instr >> 11) & 0x1F;
        let delta = self.mgba_delta(bus, pc, 2) as i64;
        if op >= 0x1C {
            if op == 0x1D {
                return (base + self.mgba_write_pc(bus, self.regs[14].wrapping_add((instr & 0x7FF) << 1) & !1, 2) as i64) as u32;
            }
            if op == 0x1E {
                let second = bus.read16(pc.wrapping_add(2)) as u32;
                let boff = ((instr & 0x7FF) << 12) | ((second & 0x7FF) << 1);
                let signed = if boff & 0x0040_0000 != 0 {
                    (boff | !0x007F_FFFF) as i32
                } else {
                    boff as i32
                };
                let target = pc.wrapping_add(4).wrapping_add(signed as u32) & !1;
                return (base + self.mgba_write_pc(bus, target, 2) as i64) as u32;
            }
            if op == 0x1F {
                let target = self.regs[14].wrapping_add((instr & 0x7FF) << 1) & !1;
                return (base + self.mgba_write_pc(bus, target, 2) as i64) as u32;
            }
            let mut off = (instr & 0x7FF) as i32;
            if off & 0x400 != 0 { off -= 0x800; }
            let target = pc.wrapping_add(4).wrapping_add((off << 1) as u32);
            return (base + self.mgba_write_pc(bus, target, 2) as i64) as u32;
        }
        if op == 0x1B && (instr >> 8) & 0xF == 0xF {
            let number = instr & 0xFF;
            return (base + self.mgba_swi_cycles(bus, pc, number, true)).max(1) as u32;
        }
        if instr & 0xFC00 == 0x4400 {
            let op2 = (instr >> 8) & 0x3;
            let rd = (((instr >> 7) & 1) << 3) | (instr & 0x7);
            if op2 == 3 || rd == 15 {
                let target = self.regs[((instr >> 3) & 0xF) as usize];
                let width = if target & 1 != 0 { 2 } else { 4 };
                return (base + self.mgba_write_pc(bus, target & !1, width) as i64) as u32;
            }
            return base as u32;
        }
        if op == 0x1A || op == 0x1B {
            if self.condition_ok((instr >> 8) & 0xF) {
                let mut off = (instr & 0xFF) as i32;
                if off & 0x80 != 0 { off -= 0x100; }
                let target = pc.wrapping_add(4).wrapping_add((off << 1) as u32);
                return (base + self.mgba_write_pc(bus, target, 2) as i64) as u32;
            }
            return base as u32;
        }
        if op == 0x17 || (op == 0x16 && instr & 0x400 != 0) {
            let n = (instr & 0xFF).count_ones() + if (instr >> 8) & 1 != 0 { 1 } else { 0 };
            let sp = self.regs[13];
            if op == 0x16 {
                let base_addr = sp.wrapping_sub(4 * n);
                return (base + delta + self.mgba_multiple_cost(bus, pc, false, base_addr & !3, n, false)).max(1) as u32;
            }
            let mut cost = base + delta + self.mgba_multiple_cost(bus, pc, false, sp & !3, n, true);
            if (instr >> 8) & 1 != 0 {
                cost += self.mgba_write_pc(bus, self.regs[15] & !1, 2) as i64;
            }
            return cost.max(1) as u32;
        }
        if op == 0x18 || op == 0x19 {
            let list = instr & 0xFF;
            let n = list.count_ones().max(1);
            let rb = self.regs[((instr >> 8) & 7) as usize] & !3;
            let load = (instr >> 11) & 1 == 1;
            let mut cost = base + delta + self.mgba_multiple_cost(bus, pc, false, rb, n, load);
            if load && list == 0 {
                cost += self.mgba_write_pc(bus, self.regs[15] & !1, 2) as i64;
            }
            return cost.max(1) as u32;
        }
        if op == 0x08 {
            let alu = (instr >> 6) & 0xF;
            if alu == 0xD {
                let rs = self.regs[(instr & 7) as usize];
                let wait = Self::mgba_mul_wait(rs, true, 0) as i32;
                return (base + self.mgba_stall(bus, pc, false, wait) as i64 + delta).max(1) as u32;
            }
            if matches!(alu, 0x2 | 0x3 | 0x4 | 0x7) {
                return (base + 1) as u32;
            }
            return base as u32;
        }
        if matches!(op, 0x9 | 0xB | 0xD | 0xF | 0x11 | 0x13) {
            let (addr, width) = if op == 0x9 {
                (((pc + 4) & !3) + ((instr & 0xFF) << 2), 4)
            } else if op == 0xB {
                let addr = self.regs[((instr >> 3) & 7) as usize] + self.regs[((instr >> 6) & 7) as usize];
                let width = if (instr >> 10) & 1 != 0 {
                    if (instr >> 9) & 1 != 0 { 2 } else { 1 }
                } else if (instr >> 9) & 1 != 0 { 2 } else { 4 };
                (addr, width)
            } else if op == 0xD {
                (self.regs[((instr >> 3) & 7) as usize] + ((instr >> 6) & 0x1F) * 4, 4)
            } else if op == 0xF {
                (self.regs[((instr >> 3) & 7) as usize] + ((instr >> 6) & 0x1F), 1)
            } else if op == 0x11 {
                (self.regs[((instr >> 3) & 7) as usize] + ((instr >> 6) & 0x1F) * 2, 2)
            } else {
                (self.regs[13] + ((instr & 0xFF) << 2), 4)
            };
            return (base + self.mgba_data(bus, pc, false, addr, width) as i64 + delta).max(1) as u32;
        }
        if matches!(op, 0xA | 0xC | 0xE | 0x10 | 0x12) {
            let (addr, width) = if op == 0xA {
                let addr = self.regs[((instr >> 3) & 7) as usize] + self.regs[((instr >> 6) & 7) as usize];
                (addr, if (instr >> 9) & 1 != 0 { 2 } else { 4 })
            } else if op == 0xC {
                (self.regs[((instr >> 3) & 7) as usize] + ((instr >> 6) & 0x1F) * 4, 4)
            } else if op == 0xE {
                (self.regs[((instr >> 3) & 7) as usize] + ((instr >> 6) & 0x1F), 1)
            } else if op == 0x10 {
                (self.regs[((instr >> 3) & 7) as usize] + ((instr >> 6) & 0x1F) * 2, 2)
            } else {
                (self.regs[13] + ((instr & 0xFF) << 2), 4)
            };
            return (base + self.mgba_store(bus, pc, false, addr, width) as i64 + delta).max(1) as u32;
        }
        base.max(1) as u32
    }

    fn thumb_cycles_calc(&mut self, bus: &mut Bus, pc: u32, instr: u32) -> u32 {
        let pc = pc & !1;
        let op = (instr >> 11) & 0x1F;
        if op >= 0x1C {
            if op == 0x1D {
                return 3 * self.fetch_cost(bus, pc & !3, 2, false) + bus.access_cost(pc, 2, false);
            }
            if op == 0x1E {
                let second = bus.read16(pc.wrapping_add(2)) as u32;
                let mut boff = ((instr & 0x7FF) << 12) | ((second & 0x7FF) << 1);
                let target = {
                    let signed = if boff & 0x0040_0000 != 0 {
                        (boff | !0x007F_FFFF) as i32
                    } else {
                        boff as i32
                    };
                    pc.wrapping_add(4).wrapping_add(signed as u32) & !1
                };
                let _ = boff;
                return 2 * self.fetch_cost(bus, pc, 2, false) + bus.access_cost(target, 2, false)
                    + self.refill_seq(bus, target, 2);
            }
            if op == 0x1F {
                let target = self.regs[14].wrapping_add((instr & 0x7FF) << 1);
                return self.fetch_cost(bus, pc, 2, false) + bus.access_cost(target, 2, false)
                    + self.refill_seq(bus, target, 2);
            }
            let mut off = (instr & 0x7FF) as i32;
            if off & 0x400 != 0 { off -= 0x800; }
            let target = pc.wrapping_add(4).wrapping_add((off << 1) as u32);
            return self.fetch_cost(bus, pc, 2, false) + bus.access_cost(target, 2, false);
        }
        if op == 0x1B && (instr >> 8) & 0xF == 0xF {
            return 2 * self.fetch_cost(bus, pc, 2, false) + 1;
        }
        if instr & 0xFC00 == 0x4400 {
            let op2 = (instr >> 8) & 0x3;
            let rd = (((instr >> 7) & 1) << 3) | (instr & 0x7);
            if op2 == 3 || rd == 15 {
                let target = self.regs[((instr >> 3) & 0xF) as usize] & !1;
                let mut cost = self.fetch_cost(bus, pc, 2, false) + bus.access_cost(target, 2, false);
                let page = target >> 24;
                if (0x08..=0x0D).contains(&page) {
                    cost += bus.access_cost(target.wrapping_add(2) & !1, 2, true);
                }
                return cost;
            }
            return self.fetch_cost(bus, pc, 2, false);
        }
        if op == 0x1A || op == 0x1B {
            if self.condition_ok((instr >> 8) & 0xF) {
                let mut off = (instr & 0xFF) as i32;
                if off & 0x80 != 0 { off -= 0x100; }
                let target = pc.wrapping_add(4).wrapping_add((off << 1) as u32);
                return self.fetch_cost(bus, pc, 2, false) + bus.access_cost(target, 2, false)
                    + self.refill_seq(bus, target, 2);
            }
            return self.fetch_cost(bus, pc, 2, false);
        }
        if op == 0x17 || (op == 0x16 && instr & 0x400 != 0) {
            let n = (instr & 0xFF).count_ones() + if (instr >> 8) & 1 != 0 { 1 } else { 0 };
            let sp = self.regs[13];
            if op == 0x16 {
                let base = sp.wrapping_sub(4 * n);
                if n == 0 { return self.fetch_cost(bus, pc, 2, true) + 3; }
                return self.fetch_cost(bus, pc, 2, true) + self.units_cost2(bus, pc, base, n, 4) + bus.access_cost(base, 4, false);
            }
            if (instr >> 8) & 1 != 0 {
                return self.fetch_cost(bus, pc, 2, true) + self.units_cost2(bus, pc, sp, n, 4) + (n - 1) + 2 + bus.access_cost(sp, 2, false);
            }
            if n == 0 { return self.fetch_cost(bus, pc, 2, true) + 13; }
            return self.fetch_cost(bus, pc, 2, true) + self.units_cost2(bus, pc, sp, n, 4) + (n - 1) + 1;
        }
        if op == 0x18 || op == 0x19 {
            let n = (instr & 0xFF).count_ones().max(1);
            let rb = self.regs[((instr >> 8) & 7) as usize] & !3;
            if (instr >> 11) & 1 == 0 {
                return self.fetch_cost(bus, pc, 2, true) + self.units_cost2(bus, pc, rb, n, 4) + bus.access_cost(rb, 4, false);
            }
            return self.fetch_cost(bus, pc, 2, true) + self.units_cost2(bus, pc, rb, n, 4) + (n - 1) + 1;
        }
        if op == 0x08 {
            let alu = (instr >> 6) & 0xF;
            if alu == 0xD {
                let rs = self.regs[((instr >> 3) & 7) as usize];
                return self.fetch_cost(bus, pc, 2, true) + Self::mul_m(rs, false);
            }
            if matches!(alu, 0x2 | 0x3 | 0x4 | 0x7) {
                return self.fetch_cost(bus, pc, 2, true) + 1;
            }
            return self.fetch_cost(bus, pc, 2, false);
        }
        if matches!(op, 0x9 | 0xB | 0xD | 0xF | 0x11 | 0x13) {
            let (addr, width) = if op == 0x9 {
                (((pc + 4) & !3) + ((instr & 0xFF) << 2), 4)
            } else if op == 0xB {
                let addr = self.regs[((instr >> 3) & 7) as usize] + self.regs[((instr >> 6) & 7) as usize];
                let width = if (instr >> 10) & 1 != 0 {
                    if (instr >> 9) & 1 != 0 { 2 } else { 1 }
                } else if (instr >> 9) & 1 != 0 { 2 } else { 4 };
                (addr, width)
            } else if op == 0xD {
                (self.regs[((instr >> 3) & 7) as usize] + ((instr >> 6) & 0x1F) * 4, 4)
            } else if op == 0xF {
                (self.regs[((instr >> 3) & 7) as usize] + ((instr >> 6) & 0x1F), 1)
            } else if op == 0x11 {
                (self.regs[((instr >> 3) & 7) as usize] + ((instr >> 6) & 0x1F) * 2, 2)
            } else {
                (self.regs[13] + ((instr & 0xFF) << 2), 4)
            };
            return self.fetch_cost(bus, pc, 2, true)
                + self.data_cost(bus, pc, addr & 0xFFFF_FFFF, width) + 1 + self.post_delta(bus, pc, 2);
        }
        if matches!(op, 0xA | 0xC | 0xE | 0x10 | 0x12) {
            let (addr, width) = if op == 0xA {
                let addr = self.regs[((instr >> 3) & 7) as usize] + self.regs[((instr >> 6) & 7) as usize];
                (addr, if (instr >> 9) & 1 != 0 { 2 } else { 4 })
            } else if op == 0xC {
                (self.regs[((instr >> 3) & 7) as usize] + ((instr >> 6) & 0x1F) * 4, 4)
            } else if op == 0xE {
                (self.regs[((instr >> 3) & 7) as usize] + ((instr >> 6) & 0x1F), 1)
            } else if op == 0x10 {
                (self.regs[((instr >> 3) & 7) as usize] + ((instr >> 6) & 0x1F) * 2, 2)
            } else {
                (self.regs[13] + ((instr & 0xFF) << 2), 4)
            };
            let mut cost = self.fetch_cost(bus, pc, 2, true)
                + self.data_cost(bus, pc, addr & 0xFFFF_FFFF, width) + self.post_delta(bus, pc, 2);
            if width == 4 && Self::io_word_extra(addr) { cost += 1; }
            return cost;
        }
        self.fetch_cost(bus, pc, 2, false)
    }

    fn hle_swi(&mut self, bus: &mut Bus, number: u8) -> Result<(), CpuError> {
        match number {
            0x01 => {
                let flags = self.regs[0];
                if flags & 0x01 != 0 { bus.ewram.fill(0); }
                if flags & 0x02 != 0 { bus.iwram[..0x7E00].fill(0); }
                if flags & 0x04 != 0 { bus.palette.fill(0); }
                if flags & 0x08 != 0 { bus.vram.fill(0); }
                if flags & 0x10 != 0 { bus.oam.fill(0); }
                if flags & 0x20 != 0 {
                    for offset in 0x120..0x134 {
                        bus.write8(0x0400_0000 + offset, 0);
                    }
                }
                if flags & 0x40 != 0 {
                    for offset in 0x060..0x0A9 {
                        bus.write8(0x0400_0000 + offset, 0);
                    }
                }
                if flags & 0x80 != 0 {
                    for offset in (0x000u32..0x060).chain(0x0A9u32..0x120).chain(0x200u32..0x20A) {
                        bus.write8(0x0400_0000 + offset, 0);
                    }
                    bus.timer_counter = [0; 4];
                    bus.timer_reload = [0; 4];
                    bus.timer_control = [0; 4];
                    bus.timer_prescaler = [1; 4];
                    bus.timer_cascade = [false; 4];
                    bus.timer_irq = [false; 4];
                    bus.timer_pending = [0; 4];
                    bus.timer_running = [false; 4];
                    bus.dma_sad = [0; 4];
                    bus.dma_dad = [0; 4];
                    bus.dma_cnt_l = [0; 4];
                    bus.dma_cnt_h = [0; 4];
                    bus.dma_source = [0; 4];
                    bus.dma_dest = [0; 4];
                    bus.dma_count = [0; 4];
                    bus.dma_active = [false; 4];
                    bus.dma_pending.clear();
                }
                bus.write16(0x0400_0000, 0x0080);
                Ok(())
            }
            0x06 | 0x07 => {
                let (numerator, denominator) = if number == 0x06 {
                    (self.regs[0] as i32, self.regs[1] as i32)
                } else {
                    (self.regs[1] as i32, self.regs[0] as i32)
                };
                let (quotient, remainder) = if denominator == 0 {
                    (if numerator < 0 { -1i32 } else { 1i32 }, numerator)
                } else {
                    // INT_MIN / -1 在 i32 會 overflow；用 i64 截斷後取低 32 bits。
                    (
                        (numerator as i64 / denominator as i64) as i32,
                        (numerator as i64 % denominator as i64) as i32,
                    )
                };
                self.regs[0] = quotient as u32;
                self.regs[1] = remainder as u32;
                self.regs[3] = quotient.unsigned_abs();
                Ok(())
            }
            0x08 => {
                self.regs[0] = (self.regs[0] as u32).isqrt() & 0xFFFF;
                Ok(())
            }
            0x09 => {
                let (r0, r1, r3) = biostan_parts(self.regs[0]);
                self.regs[0] = r0;
                self.regs[1] = r1;
                self.regs[3] = r3;
                Ok(())
            }
            0x0A => {
                let (r0, r1) = biosatan2_parts(self.regs[0], self.regs[1]);
                self.regs[0] = r0;
                self.regs[1] = r1;
                self.regs[3] = 0x170;
                Ok(())
            }
            0x02 | 0x03 | 0x27 => {
                self.halted = true;
                self.wait_irq = 0;
                Ok(())
            }
            0x04 => {
                let flags = (self.regs[1] & 0x3FFF) as u16;
                self.wait_irq = flags;
                self.halted = true;
                Ok(())
            }
            0x05 => {
                self.regs[0] = 1;
                self.regs[1] = 1;
                self.wait_irq = 1;
                self.halted = true;
                Ok(())
            }
            0x0D => {
                self.regs[0] = 0xBAAE_187F;
                Ok(())
            }
            0x1F => {
                const MIDI_WORD: [u32; 12] = [
                    0x8000_0000, 0x879C_7C97, 0x8FAC_D61E, 0x9837_F052,
                    0xA145_17CC, 0xAADC_0848, 0xB504_F334, 0xBFC8_86BB,
                    0xCB2F_F52A, 0xD744_FCCB, 0xE411_F03A, 0xF1A1_BF39,
                ];
                let mut key = (self.regs[1] & 0xFF) as u32;
                let fraction = self.regs[2] & 0xFF;
                let mut value_fraction = fraction << 24;
                if key > 0xB2 {
                    value_fraction = 0xFF00_0000;
                    key = 0xB2;
                }
                let midi_val = |midi_key: u32| -> u32 {
                    let packed = ((14 - midi_key / 12) << 4) | (midi_key % 12);
                    MIDI_WORD[(packed & 0xF) as usize] >> (packed >> 4)
                };
                let low = midi_val(key);
                let high = midi_val(key + 1);
                let delta = (((high.wrapping_sub(low)) as u64 * value_fraction as u64) >> 32) as u32;
                self.regs[0] = low.wrapping_add(delta);
                Ok(())
            }
            0x0E => {
                let source = self.regs[0];
                let dest = self.regs[1];
                let count = self.regs[2];
                for index in 0..count {
                    let src = source.wrapping_add(index * 20);
                    let x0 = bus.read32(src);
                    let y0 = bus.read32(src.wrapping_add(4));
                    let dx = bus.read16(src.wrapping_add(8)) as i16 as i32;
                    let dy = bus.read16(src.wrapping_add(10)) as i16 as i32;
                    let sx = bus.read16(src.wrapping_add(12)) as i16 as i32;
                    let sy = bus.read16(src.wrapping_add(14)) as i16 as i32;
                    let angle = (bus.read16(src.wrapping_add(16)) >> 8) as u32;
                    let sin = sintab(angle);
                    let cos = sintab(angle.wrapping_add(64));
                    let pa = q8(cos * sx);
                    let pb = q8(-sin * sx);
                    let pc = q8(sin * sy);
                    let pd = q8(cos * sy);
                    let dst = dest.wrapping_add(index * 16);
                    bus.write16(dst, pa as u16);
                    bus.write16(dst.wrapping_add(2), pb as u16);
                    bus.write16(dst.wrapping_add(4), pc as u16);
                    bus.write16(dst.wrapping_add(6), pd as u16);
                    bus.write32(dst.wrapping_add(8), x0.wrapping_sub((pa as u32).wrapping_mul(dx as u32)).wrapping_sub((pb as u32).wrapping_mul(dy as u32)));
                    bus.write32(dst.wrapping_add(12), y0.wrapping_sub((pc as u32).wrapping_mul(dx as u32)).wrapping_sub((pd as u32).wrapping_mul(dy as u32)));
                }
                Ok(())
            }
            0x0F => {
                let source = self.regs[0];
                let dest = self.regs[1];
                let count = self.regs[2];
                let offset = self.regs[3];
                for index in 0..count {
                    let src = source.wrapping_add(index * 6);
                    let sx = bus.read16(src) as i16 as i32;
                    let sy = bus.read16(src.wrapping_add(2)) as i16 as i32;
                    let angle = (bus.read16(src.wrapping_add(4)) >> 8) as u32;
                    let sin = sintab(angle);
                    let cos = sintab(angle.wrapping_add(64));
                    let dst = dest.wrapping_add(index * offset * 4);
                    bus.write16(dst, q8(cos * sx) as u16);
                    bus.write16(dst.wrapping_add(offset), q8(-sin * sx) as u16);
                    bus.write16(dst.wrapping_add(offset * 2), q8(sin * sy) as u16);
                    bus.write16(dst.wrapping_add(offset * 3), q8(cos * sy) as u16);
                }
                Ok(())
            }
            0x13 => {
                let source = self.regs[0] & !3;
                let dest = self.regs[1];
                let header = bus.read32(source);
                let mut size = header & 0xF;
                if size == 0 { size = 8; }
                if size == 1 || 32 % size != 0 {
                    return Ok(());
                }
                let length = (header >> 8) as usize;
                let tree_size = bus.read8(source.wrapping_add(4)) as u32;
                let tree = source.wrapping_add(5);
                let bits = source.wrapping_add(4 + (tree_size + 1) * 2);
                let words = (length + 3) / 4;
                let mask = (1u32 << size) - 1;
                let mut bit_position = 0u32;
                let mut pointer = tree;
                let mut node = bus.read8(pointer);
                let mut out_dest = dest;
                for _ in 0..words {
                    let mut word = 0u32;
                    let mut shift = 0u32;
                    // Huffman code 是變長：填滿 32 output bits 才寫一個 word。
                    while shift < 32 {
                        let bit_word = bus.read32(bits.wrapping_add((bit_position >> 5) * 4));
                        let bit = (bit_word >> (31 - (bit_position & 31))) & 1;
                        bit_position += 1;
                        let is_data = (node >> (7 - bit)) & 1;
                        let child = (pointer & !1) + ((node & 0x3F) as u32) * 2 + 2 + bit;
                        node = bus.read8(child);
                        if is_data != 0 {
                            word |= ((node as u32) & mask) << shift;
                            shift += size;
                            pointer = tree;
                            node = bus.read8(pointer);
                        } else {
                            pointer = child;
                        }
                    }
                    bus.write32(out_dest, word);
                    out_dest = out_dest.wrapping_add(4);
                }
                self.regs[0] = bits.wrapping_add(words as u32 * 4);
                self.regs[1] = out_dest;
                Ok(())
            }
            0x10 => {
                let source = self.regs[0];
                let dest = self.regs[1];
                let info = self.regs[2];
                let length = bus.read16(info) as usize;
                let src_width = bus.read8(info.wrapping_add(2)) as u32;
                let dst_width = bus.read8(info.wrapping_add(3)) as u32;
                let raw_offset = bus.read32(info.wrapping_add(4));
                let zero_flag = raw_offset & 0x8000_0000 != 0;
                let offset = raw_offset & 0x7FFF_FFFF;
                let src_width = src_width.max(1).min(32);
                let dst_width = dst_width.max(1).min(32);
                let per_byte = (8 / src_width).max(1) as usize;
                let src_mask = if src_width == 32 { u32::MAX } else { (1u32 << src_width) - 1 };
                let dst_mask = if dst_width == 32 { u32::MAX } else { (1u32 << dst_width) - 1 };
                let mut units = Vec::new();
                for index in 0..length {
                    let value = bus.read8(source.wrapping_add(index as u32));
                    for slot in 0..per_byte {
                        units.push((value as u32 >> (slot as u32 * src_width)) & src_mask);
                    }
                }
                let mut word: u64 = 0;
                let mut bit_position: u32 = 0;
                let mut words = Vec::new();
                for unit in units {
                    let value = if unit != 0 || zero_flag {
                        unit.wrapping_add(offset) & dst_mask
                    } else {
                        0
                    };
                    word |= (value as u64) << bit_position;
                    bit_position += dst_width;
                    while bit_position >= 32 {
                        words.push(word as u32);
                        word >>= 32;
                        bit_position -= 32;
                    }
                }
                if bit_position > 0 {
                    words.push(word as u32);
                }
                for (index, value) in words.iter().enumerate() {
                    bus.write32(dest.wrapping_add(index as u32 * 4), *value);
                }
                Ok(())
            }
            0x16 | 0x17 => {
                let source = self.regs[0];
                let dest = self.regs[1];
                let length = (bus.read32(source) >> 8) as usize;
                let mut accumulator = 0u8;
                let mut out = Vec::with_capacity(length);
                for index in 0..length {
                    accumulator = accumulator.wrapping_add(bus.read8(source.wrapping_add(4 + index as u32)));
                    out.push(accumulator);
                }
                for (index, pair) in out.chunks(2).enumerate() {
                    let value = pair[0] as u16 | ((pair.get(1).copied().unwrap_or(0) as u16) << 8);
                    bus.write16(dest.wrapping_add(index as u32 * 2), value);
                }
                Ok(())
            }
            0x18 => {
                let source = self.regs[0];
                let dest = self.regs[1];
                let length = (bus.read32(source) >> 8) as usize;
                let mut accumulator = 0u16;
                for index in 0..length / 2 {
                    accumulator = accumulator.wrapping_add(bus.read16(source.wrapping_add(4 + index as u32 * 2)));
                    bus.write16(dest.wrapping_add(index as u32 * 2), accumulator);
                }
                Ok(())
            }
            0x19 => {
                let old = bus.read16(0x0400_0088);
                let level = if self.regs[0] == 0 { 0x000 } else { 0x200 };
                bus.write16(0x0400_0088, (old & !0x3FF) | level);
                Ok(())
            }
            0x11 | 0x12 => {
                let source = self.regs[0];
                let dest = self.regs[1];
                let mut out = Vec::new();
                let length = (bus.read32(source) >> 8) as usize;
                let mut cursor = source.wrapping_add(4);
                while out.len() < length {
                    let mut flags = bus.read8(cursor);
                    cursor = cursor.wrapping_add(1);
                    for _ in 0..8 {
                        if out.len() >= length { break; }
                        if flags & 0x80 != 0 {
                            let first = bus.read8(cursor);
                            let second = bus.read8(cursor.wrapping_add(1));
                            cursor = cursor.wrapping_add(2);
                            let count = ((first >> 4) as usize) + 3;
                            let displacement = (((first & 0x0F) as usize) << 8) | second as usize;
                            for _ in 0..count {
                                let index = out.len().wrapping_sub(displacement + 1);
                                out.push(out[index]);
                            }
                        } else {
                            out.push(bus.read8(cursor));
                            cursor = cursor.wrapping_add(1);
                        }
                        flags = flags.wrapping_shl(1);
                    }
                }
                if number == 0x12 {
                    // VRAM 係 16-bit 匯流排：每兩個解壓 byte 要 pack 成一個
                    // halfword（同 Python `_flush16`；奇數尾 byte 寫低 8 bit）。
                    for (index, pair) in out.chunks(2).enumerate() {
                        let value = pair[0] as u16 | ((pair.get(1).copied().unwrap_or(0) as u16) << 8);
                        bus.write16(dest.wrapping_add(index as u32 * 2), value);
                    }
                } else {
                    for (index, value) in out.iter().enumerate() {
                        bus.write8(dest.wrapping_add(index as u32), *value);
                    }
                }
                Ok(())
            }
            0x14 | 0x15 => {
                let source = self.regs[0];
                let dest = self.regs[1];
                let mut out = Vec::new();
                let length = (bus.read32(source) >> 8) as usize;
                let mut cursor = source.wrapping_add(4);
                while out.len() < length {
                    let flag = bus.read8(cursor);
                    cursor = cursor.wrapping_add(1);
                    if flag & 0x80 != 0 {
                        let count = ((flag & 0x7F) as usize) + 3;
                        let value = bus.read8(cursor);
                        cursor = cursor.wrapping_add(1);
                        for _ in 0..count { out.push(value); }
                    } else {
                        let count = ((flag & 0x7F) as usize) + 1;
                        for _ in 0..count {
                            out.push(bus.read8(cursor));
                            cursor = cursor.wrapping_add(1);
                        }
                    }
                }
                out.truncate(length);
                if number == 0x15 {
                    // 同 0x12：VRAM 每個 halfword 放兩個 byte。
                    for (index, pair) in out.chunks(2).enumerate() {
                        let value = pair[0] as u16 | ((pair.get(1).copied().unwrap_or(0) as u16) << 8);
                        bus.write16(dest.wrapping_add(index as u32 * 2), value);
                    }
                } else {
                    for (index, value) in out.iter().enumerate() {
                        bus.write8(dest.wrapping_add(index as u32), *value);
                    }
                }
                Ok(())
            }
            0x0B => {
                let source = self.regs[0];
                let dest = self.regs[1];
                let control = self.regs[2];
                let count = (control & 0x1F_FFFF) as u32;
                let fill = control & (1 << 24) != 0;
                let word = control & (1 << 26) != 0;
                // Game Pak SRAM 係 8-bit 匯流排：BIOS 嘅 wide access 唔會先對齊，
                // bus 會喺原始位址讀/寫單一 byte（suite SRAM swi rows）。
                let raw = |address: u32| (0x0E00_0000..=0x0FFF_FFFF).contains(&address);
                // 真 BIOS 由 BIOSo/unmapped（< EWRAM）copy 出嚟係 0
                // （suite「BIOS load」/「Out-of-bounds load」swi rows）。
                let bad_source = source < 0x0200_0000;
                if word {
                    if fill {
                        let value = if bad_source {
                            0
                        } else if raw(source) {
                            bus.read32(source)
                        } else {
                            bus.read32(source & !3)
                        };
                        for index in 0..count {
                            let dst = dest.wrapping_add(index * 4);
                            bus.write32(if raw(dst) { dst } else { dst & !3 }, value);
                        }
                    } else {
                        for index in 0..count {
                            let src = source.wrapping_add(index * 4);
                            let value = if bad_source {
                                0
                            } else {
                                bus.read32(if raw(src) { src } else { src & !3 })
                            };
                            let dst = dest.wrapping_add(index * 4);
                            bus.write32(if raw(dst) { dst } else { dst & !3 }, value);
                        }
                    }
                } else if fill {
                    let value = if bad_source {
                        0
                    } else if source & 1 != 0 {
                        bus.read8(source) as u16
                    } else {
                        bus.read16(if raw(source) { source } else { source & !1 })
                    };
                    for index in 0..count {
                        let dst = dest.wrapping_add(index * 2);
                        bus.write16(if raw(dst) { dst } else { dst & !1 }, value);
                    }
                } else {
                    for index in 0..count {
                        let src = source.wrapping_add(index * 2);
                        let value = if bad_source {
                            0
                        } else if src & 1 != 0 {
                            bus.read8(src) as u16
                        } else {
                            bus.read16(if raw(src) { src } else { src & !1 })
                        };
                        let dst = dest.wrapping_add(index * 2);
                        bus.write16(if raw(dst) { dst } else { dst & !1 }, value);
                    }
                }
                Ok(())
            }
            0x25 => Ok(()),
            0x0C => {
                let source = self.regs[0];
                let dest = self.regs[1];
                let control = self.regs[2];
                let mut count = (control & 0x1F_FFFF) as u32;
                if count == 0 {
                    count = 0x10_0000;
                }
                count = (count + 7) & !7;
                let fill = control & (1 << 24) != 0;
                // 同 CpuSet：SRAM 用原始位址（8-bit 匯流排，單 byte 讀寫）；
                // 來源 < EWRAM（BIOS/unmapped）copy 出嚟係 0。
                let raw = |address: u32| (0x0E00_0000..=0x0FFF_FFFF).contains(&address);
                let bad_source = source < 0x0200_0000;
                if fill {
                    let value = if bad_source {
                        0
                    } else if raw(source) {
                        bus.read32(source)
                    } else {
                        bus.read32(source & !3)
                    };
                    for index in 0..count {
                        let dst = dest.wrapping_add(index * 4);
                        bus.write32(if raw(dst) { dst } else { dst & !3 }, value);
                    }
                } else {
                    for index in 0..count {
                        let src = source.wrapping_add(index * 4);
                        let value = if bad_source {
                            0
                        } else {
                            bus.read32(if raw(src) { src } else { src & !3 })
                        };
                        let dst = dest.wrapping_add(index * 4);
                        bus.write32(if raw(dst) { dst } else { dst & !3 }, value);
                    }
                }
                Ok(())
            }
            _ => Err(CpuError::HleUnsupported(number)),
        }
    }

    pub fn snapshot_section(&self) -> Vec<u8> {
        let mut out = Vec::with_capacity(204);
        for value in self.regs {
            put_u32(&mut out, value);
        }
        put_u32(&mut out, self.cpsr);
        put_u32(&mut out, self.spsr);
        for index in 0..5 {
            put_u32(&mut out, self.banked_sp_lr[index][0]);
            put_u32(&mut out, self.banked_sp_lr[index][1]);
        }
        put_u32(&mut out, self.usr_sp);
        put_u32(&mut out, self.usr_lr);
        for value in self.banked_spsr {
            put_u32(&mut out, value);
        }
        put_u32(&mut out, 0); // SYS 沒有 SPSR
        out.push((self.cpsr & CPSR_MODE_MASK) as u8);
        out.push(u8::from(self.halted));
        for value in self.fiq_r8_12 {
            put_u32(&mut out, value);
        }
        for value in self.usr_r8_12 {
            put_u32(&mut out, value);
        }
        put_u64(&mut out, self.cycles);
        put_u32(&mut out, self.wait_irq as u32);
        put_u32(&mut out, self.irq_wait as u32);
        out.push(u8::from(self.nseq_fetch));
        out.push(0); // _t_branch_taken（Rust 尚無此狀態）
        out
    }

    pub fn restore_section(&mut self, data: &[u8]) -> Result<(), String> {
        let mut reader = SnapshotReader::new(data);
        for index in 0..16 {
            self.regs[index] = reader.u32().ok_or("CPU snapshot 被截斷")?;
        }
        self.cpsr = reader.u32().ok_or("CPU snapshot 被截斷")?;
        self.spsr = reader.u32().ok_or("CPU snapshot 被截斷")?;
        for index in 0..5 {
            self.banked_sp_lr[index][0] = reader.u32().ok_or("CPU snapshot 被截斷")?;
            self.banked_sp_lr[index][1] = reader.u32().ok_or("CPU snapshot 被截斷")?;
        }
        self.usr_sp = reader.u32().ok_or("CPU snapshot 被截斷")?;
        self.usr_lr = reader.u32().ok_or("CPU snapshot 被截斷")?;
        for index in 0..5 {
            self.banked_spsr[index] = reader.u32().ok_or("CPU snapshot 被截斷")?;
        }
        let _sys_spsr = reader.u32().ok_or("CPU snapshot 被截斷")?;
        let _bank_mode = reader.u8().ok_or("CPU snapshot 被截斷")?;
        self.halted = reader.u8().ok_or("CPU snapshot 被截斷")? != 0;
        for index in 0..5 {
            self.fiq_r8_12[index] = reader.u32().ok_or("CPU snapshot 被截斷")?;
        }
        for index in 0..5 {
            self.usr_r8_12[index] = reader.u32().ok_or("CPU snapshot 被截斷")?;
        }
        self.cycles = reader.u64().ok_or("CPU snapshot 被截斷")?;
        self.wait_irq = reader.u32().ok_or("CPU snapshot 被截斷")? as u16;
        self.irq_wait = reader.u32().ok_or("CPU snapshot 被截斷")? as i32;
        self.nseq_fetch = reader.u8().ok_or("CPU snapshot 被截斷")? != 0;
        let _t_branch = reader.u8().ok_or("CPU snapshot 被截斷")?;
        self.irq_pending = false;
        self.thumb_bl_high = None;
        if !reader.finish() {
            return Err("CPU snapshot 長度不符".to_string());
        }
        Ok(())
    }

    /// mGBA `GBALoadBad` 的區域判定：BIOS 0x4000 之後、0x01xxxxxx 同
    /// 0x10000000 以上都係冇裝置驅動匯流排（open bus）。
    fn is_bad_load(address: u32) -> bool {
        (0x0000_4000..0x0200_0000).contains(&address) || address >= 0x1000_0000
    }

    /// open bus 值：CPU 管線內已 prefetch 的指令字（mGBA `cpu->prefetch[1]`）。
    /// ARM：PC 暫存器（= 當前指令 + 8）嘅 word；Thumb 依 region 併 halfword。
    fn open_bus_word(&mut self, bus: &mut Bus) -> u32 {
        let pc = self.regs[15];
        if self.thumb() {
            let mut value = bus.read16(pc) as u32;
            let earlier = bus.read16(pc.wrapping_sub(2)) as u32;
            match pc >> 24 {
                0x00 | 0x07 => value = (value << 16) | earlier,
                0x03 => {
                    if pc & 2 != 0 {
                        value = (value << 16) | earlier;
                    } else {
                        value |= earlier << 16;
                    }
                }
                _ => value |= value << 16,
            }
            value
        } else {
            bus.fetch32(pc & !3)
        }
    }

    fn read_half(&mut self, bus: &mut Bus, address: u32) -> u32 {
        // Game Pak SRAM 是 8-bit 匯流排：bus 讀「原始位址」的 byte 再複製；
        // 未對齊仍要 ROR 8（suite SRAM load：0x6161 → 0x61000061）。
        let sram = (0x0E00_0000..=0x0FFF_FFFF).contains(&address);
        let value = if Self::is_bad_load(address) || Bus::io_read_open_bus(address) {
            // mGBA：open bus 的 16-bit load 取 prefetch word 低 16 bits。
            self.open_bus_word(bus) & 0xFFFF
        } else {
            bus.read16(if sram { address } else { address & !1 }) as u32
        };
        if address & 1 != 0 { value.rotate_right(8) } else { value }
    }

    fn write_half(&mut self, bus: &mut Bus, address: u32, value: u16) {
        let sram = (0x0E00_0000..=0x0FFF_FFFF).contains(&address);
        bus.write16(if sram { address } else { address & !1 }, value);
    }

    fn read_byte(&mut self, bus: &mut Bus, address: u32) -> u32 {
        if Self::is_bad_load(address) || Bus::io_read_open_bus(address) {
            return (self.open_bus_word(bus) >> ((address & 3) * 8)) & 0xFF;
        }
        bus.read8(address) as u32
    }

    fn read_word(&mut self, bus: &mut Bus, address: u32) -> u32 {
        // SRAM：讀原始位址的 byte 再複製（mGBA LOAD_SRAM；suite SRAM load）。
        if (0x0E00_0000..=0x0FFF_FFFF).contains(&address) {
            return bus.read32(address);
        }
        let mut value = if Self::is_bad_load(address) || Bus::io_read_open_bus(address) {
            self.open_bus_word(bus)
        } else {
            bus.read32(address & !3)
        };
        let rotation = (address & 3) * 8;
        if rotation != 0 {
            value = value.rotate_right(rotation);
        }
        value
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::bus::Bus;

    fn bus_with(words: &[u32]) -> Bus {
        let mut rom = vec![0u8; 0x100];
        rom[0xB2] = 0x96;
        for (index, word) in words.iter().enumerate() {
            rom[index * 4..index * 4 + 4].copy_from_slice(&word.to_le_bytes());
        }
        Bus::new(rom).unwrap()
    }

    #[test]
    fn arm_mov_immediate_and_branch() {
        let mut bus = bus_with(&[
            0xE3A0_0007, // MOV r0,#7
            0xEA00_0000, // B +0
            0xE3A0_0001,
        ]);
        let mut cpu = Cpu::new();
        assert_eq!(cpu.step(&mut bus), Ok(1));
        assert_eq!(cpu.regs[0], 7);
        assert_eq!(cpu.regs[15], 0x0800_0004);
        assert_eq!(cpu.step(&mut bus), Ok(2));
        assert_eq!(cpu.regs[15], 0x0800_000C);
    }

    #[test]
    fn arm_add_sets_flags() {
        let mut bus = bus_with(&[
            0xE3A0_0001, // MOV r0,#1
            0xE280_0001, // ADD r0,r0,#1
            0xE350_0002, // CMP r0,#2
        ]);
        let mut cpu = Cpu::new();
        cpu.step(&mut bus).unwrap();
        cpu.step(&mut bus).unwrap();
        assert_eq!(cpu.regs[0], 2);
        cpu.step(&mut bus).unwrap();
        assert!(cpu.cpsr & CPSR_Z != 0);
        assert!(cpu.cpsr & CPSR_N == 0);
    }

    #[test]
    fn arm_ldr_str_word() {
        let mut bus = bus_with(&[
            0xE580_1000, // STR r1,[r0]
            0xE590_1000, // LDR r1,[r0]
        ]);
        let mut cpu = Cpu::new();
        cpu.regs[0] = 0x0200_0000;
        cpu.regs[1] = 0x1234_5678;
        cpu.step(&mut bus).unwrap();
        cpu.step(&mut bus).unwrap();
        assert_eq!(cpu.regs[1], 0x1234_5678);
    }

    #[test]
    fn arm_bx_switches_thumb() {
        let mut bus = bus_with(&[
            0xE3A0_0009, // MOV r0,#9
            0xE12F_FF10, // BX r0
            0x0000_0000,
        ]);
        let mut cpu = Cpu::new();
        cpu.step(&mut bus).unwrap();
        cpu.step(&mut bus).unwrap();
        assert!(cpu.thumb());
        assert_eq!(cpu.regs[15], 8);
    }

    #[test]
    fn thumb_mov_add_branch() {
        let mut rom = vec![0u8; 0x100];
        rom[0xB2] = 0x96;
        // MOV r0,#1; ADD r0,#2; B +0
        rom[0..2].copy_from_slice(&0x2001u16.to_le_bytes());
        rom[2..4].copy_from_slice(&0x3002u16.to_le_bytes());
        rom[4..6].copy_from_slice(&0xE000u16.to_le_bytes());
        let mut bus = Bus::new(rom).unwrap();
        let mut cpu = Cpu::new();
        cpu.cpsr |= CPSR_T;
        cpu.step(&mut bus).unwrap();
        cpu.step(&mut bus).unwrap();
        assert_eq!(cpu.regs[0], 3);
        cpu.step(&mut bus).unwrap();
        assert_eq!(cpu.regs[15], 0x0800_0008);
    }

    #[test]
    fn unaligned_ldr_rotates() {
        let mut bus = bus_with(&[0xE590_1001]); // LDR r1,[r0,#1]
        bus.write32(0x0200_0000, 0x1122_3344);
        let mut cpu = Cpu::new();
        cpu.regs[0] = 0x0200_0000;
        cpu.step(&mut bus).unwrap();
        assert_eq!(cpu.regs[1], 0x4411_2233);
    }


    #[test]
    fn arm_halfword_and_signed_loads() {
        let mut bus = bus_with(&[
            0xE1C0_10B0, // STRH r1,[r0]
            0xE1D0_20B0, // LDRH r2,[r0]
            0xE1D0_30D0, // LDRSB r3,[r0]
            0xE1D0_40F0, // LDRSH r4,[r0]
        ]);
        bus.write16(0x0200_0000, 0x80FF);
        let mut cpu = Cpu::new();
        cpu.regs[0] = 0x0200_0000;
        cpu.regs[1] = 0x1234;
        cpu.step(&mut bus).unwrap();
        assert_eq!(bus.read16(0x0200_0000), 0x1234);
        bus.write16(0x0200_0000, 0x80FF);
        cpu.step(&mut bus).unwrap();
        assert_eq!(cpu.regs[2], 0x80FF);
        cpu.step(&mut bus).unwrap();
        assert_eq!(cpu.regs[3], 0xFFFF_FFFF);
        cpu.step(&mut bus).unwrap();
        assert_eq!(cpu.regs[4], 0xFFFF_80FF);
    }

    #[test]
    fn arm_unaligned_halfword_store_aligns() {
        let mut bus = bus_with(&[
            0xE1D0_10B1, // LDRH r1,[r0,#1]
            0xE1C0_20B1, // STRH r2,[r0,#1]
            0xE1D0_30B0, // LDRH r3,[r0]
        ]);
        bus.write16(0x0200_0000, 0xBEEF);
        let mut cpu = Cpu::new();
        cpu.regs[0] = 0x0200_0000;
        cpu.step(&mut bus).unwrap();
        assert_eq!(cpu.regs[1], 0xEF00_00BE);
        cpu.regs[2] = 0x1234;
        cpu.step(&mut bus).unwrap();
        assert_eq!(bus.read16(0x0200_0000), 0x1234);
        cpu.step(&mut bus).unwrap();
        assert_eq!(cpu.regs[3], 0x1234);
    }

    #[test]
    fn arm_ldm_stm_writeback() {
        let mut bus = bus_with(&[
            0xE8A0_0006, // STMIA r0!,{r1,r2}
            0xE8B0_0018, // LDMIA r0!,{r3,r4}
        ]);
        let mut cpu = Cpu::new();
        cpu.regs[0] = 0x0200_0000;
        cpu.regs[1] = 0x1111_1111;
        cpu.regs[2] = 0x2222_2222;
        cpu.step(&mut bus).unwrap();
        assert_eq!(cpu.regs[0], 0x0200_0008);
        cpu.regs[0] = 0x0200_0000;
        cpu.step(&mut bus).unwrap();
        assert_eq!(cpu.regs[3], 0x1111_1111);
        assert_eq!(cpu.regs[4], 0x2222_2222);
    }

    #[test]
    fn arm_ldm_stm_s_bit_user_bank_in_fiq() {
        // STMIA r0,{r8}^
        let mut bus = bus_with(&[0xE8C0_0100]);
        let mut cpu = Cpu::new();
        cpu.regs[8] = 0xABCD_EF00;
        cpu.regs[0] = 0x0200_0000;
        cpu.switch_mode(MODE_FIQ);
        cpu.regs[8] = 0x1111_1111;
        cpu.step(&mut bus).unwrap();
        assert_eq!(bus.read32(0x0200_0000), 0xABCD_EF00);
        assert_eq!(cpu.regs[8], 0x1111_1111);

        // LDMIA r0,{r8}^：User bank 載入，FIQ 組做 ARM7TDMI OR glitch
        let mut bus = bus_with(&[0xE8D0_0100]);
        bus.write32(0x0200_0000, 0x55AA_55AA);
        let mut cpu = Cpu::new();
        cpu.regs[0] = 0x0200_0000;
        cpu.switch_mode(MODE_FIQ);
        cpu.regs[8] = 0xDEAD_BEEF;
        cpu.step(&mut bus).unwrap();
        assert_eq!(cpu.regs[8], 0xDEAD_BEEF | 0x55AA_55AA);
        assert_eq!(cpu.user_get(8), 0x55AA_55AA);
    }

    #[test]
    fn thumb_register_shift_and_add() {
        let mut rom = vec![0u8; 0x100];
        rom[0xB2] = 0x96;
        rom[0..2].copy_from_slice(&0x1840u16.to_le_bytes()); // ADD r0,r1,r0
        let mut bus = Bus::new(rom).unwrap();
        let mut cpu = Cpu::new();
        cpu.cpsr |= CPSR_T;
        cpu.regs[0] = 5;
        cpu.regs[1] = 1;
        cpu.step(&mut bus).unwrap();
        assert_eq!(cpu.regs[0], 6);

        let mut rom = vec![0u8; 0x100];
        rom[0xB2] = 0x96;
        rom[0..2].copy_from_slice(&0x41C8u16.to_le_bytes()); // ROR r0,r1
        let mut bus = Bus::new(rom).unwrap();
        let mut cpu = Cpu::new();
        cpu.cpsr |= CPSR_T;
        cpu.regs[0] = 0x8000_0000;
        cpu.regs[1] = 32;
        cpu.step(&mut bus).unwrap();
        assert_eq!(cpu.regs[0], 0x8000_0000);
        assert!(cpu.cpsr & CPSR_C != 0);
    }

    #[test]
    fn thumb_register_offset_loads_and_stores() {
        // 0101 0op3 Ro Rb Rd：op3 必須依 0..7 分派，不能把 bit9 當 signed 選擇。
        let words = [
            0x5042u16, // STR  r2,[r0,r1]
            0x5843u16, // LDR  r3,[r0,r1]
            0x5244u16, // STRH r4,[r0,r1]
            0x5A45u16, // LDRH r5,[r0,r1]
            0x5446u16, // STRB r6,[r0,r1]
            0x5C47u16, // LDRB r7,[r0,r1]
            0x5642u16, // LDSB r2,[r0,r1]
            0x5E43u16, // LDSH r3,[r0,r1]
        ];
        let mut rom = vec![0u8; 0x100];
        rom[0xB2] = 0x96;
        for (index, instr) in words.iter().enumerate() {
            rom[index * 2..index * 2 + 2].copy_from_slice(&instr.to_le_bytes());
        }
        let mut bus = Bus::new(rom).unwrap();
        let mut cpu = Cpu::new();
        cpu.cpsr |= CPSR_T;
        cpu.regs[0] = 0x0200_0000;
        cpu.regs[1] = 4;
        cpu.regs[2] = 0x89AB_CDEF;
        cpu.regs[4] = 0x1234;
        cpu.regs[6] = 0x5A;

        cpu.step(&mut bus).unwrap();
        assert_eq!(bus.read32(0x0200_0004), 0x89AB_CDEF);
        cpu.step(&mut bus).unwrap();
        assert_eq!(cpu.regs[3], 0x89AB_CDEF);

        cpu.step(&mut bus).unwrap();
        assert_eq!(bus.read16(0x0200_0004), 0x1234);
        cpu.step(&mut bus).unwrap();
        assert_eq!(cpu.regs[5], 0x1234);

        cpu.step(&mut bus).unwrap();
        assert_eq!(bus.read8(0x0200_0004), 0x5A);
        cpu.step(&mut bus).unwrap();
        assert_eq!(cpu.regs[7], 0x5A);

        bus.write8(0x0200_0004, 0x80);
        bus.write16(0x0200_0006, 0x8000);
        cpu.regs[1] = 4;
        cpu.step(&mut bus).unwrap(); // LDSB 0x80
        assert_eq!(cpu.regs[2], 0xFFFF_FF80);
        cpu.regs[1] = 6;
        cpu.step(&mut bus).unwrap(); // LDSH 0x8000
        assert_eq!(cpu.regs[3], 0xFFFF_8000);
    }

    #[test]
    fn arm_ldm_pc_s_bit_exception_return() {
        let mut bus = bus_with(&[0xE8D0_8000]); // LDMIA r0,{pc}^
        bus.write32(0x0200_0000, 0x0800_0101);
        let mut cpu = Cpu::new();
        cpu.regs[0] = 0x0200_0000;
        cpu.cpsr = MODE_IRQ | CPSR_I;
        cpu.spsr = MODE_SVC | CPSR_C;
        cpu.step(&mut bus).unwrap();
        assert_eq!(cpu.cpsr & CPSR_MODE_MASK, MODE_SVC);
        assert!(cpu.cpsr & CPSR_C != 0);
        assert_eq!(cpu.regs[15], 0x0800_0100);
    }

    #[test]
    fn arm_swp_roundtrip() {
        let mut bus = bus_with(&[0xE100_2091]); // SWP r2,r1,[r0]
        bus.write32(0x0200_0000, 0xDEAD_BEEF);
        let mut cpu = Cpu::new();
        cpu.regs[0] = 0x0200_0000;
        cpu.regs[1] = 0x1234_5678;
        cpu.step(&mut bus).unwrap();
        assert_eq!(cpu.regs[2], 0xDEAD_BEEF);
        assert_eq!(bus.read32(0x0200_0000), 0x1234_5678);
    }

    #[test]
    fn arm_mrs_reads_cpsr() {
        let mut bus = bus_with(&[0xE10F_0000]); // MRS r0,CPSR
        let mut cpu = Cpu::new();
        cpu.cpsr = 0x6000_001F;
        cpu.step(&mut bus).unwrap();
        assert_eq!(cpu.regs[0], 0x6000_001F);
    }

    #[test]
    fn functional_mode_uses_cycle_model_for_adds() {
        let mut bus = bus_with(&[
            0xE3E0_0000, // MVN r0,#0
            0xE3A0_1001, // MOV r1,#1
            0xE090_2001, // ADDS r2,r0,r1
        ]);
        bus.functional = true;
        let mut cpu = Cpu::new();
        assert_eq!(cpu.step(&mut bus).unwrap(), 1);
        assert_eq!(cpu.step(&mut bus).unwrap(), 1);
        assert_eq!(cpu.step(&mut bus).unwrap(), 1);
        assert_eq!(cpu.regs[2], 0);
        assert_eq!(cpu.cycles, 3);
    }

    #[test]
    fn arm_register_shift_and_rrx() {
        let mut bus = bus_with(&[0xE080_2311]); // ADD r2,r0,r1,LSL r3
        let mut cpu = Cpu::new();
        cpu.regs[1] = 1;
        cpu.regs[3] = 4;
        cpu.step(&mut bus).unwrap();
        assert_eq!(cpu.regs[2], 16);

        let mut bus = bus_with(&[0xE1A0_2060]); // MOV r2,r0,RRX
        let mut cpu = Cpu::new();
        cpu.cpsr |= CPSR_C;
        cpu.step(&mut bus).unwrap();
        assert_eq!(cpu.regs[2], 0x8000_0000);
    }

    #[test]
    fn arm_str_pc_writes_pc_plus_12() {
        let mut bus = bus_with(&[0xE580_F000]); // STR pc,[r0]
        let mut cpu = Cpu::new();
        cpu.regs[0] = 0x0200_0000;
        cpu.step(&mut bus).unwrap();
        assert_eq!(bus.read32(0x0200_0000), 0x0800_000C);
    }

    #[test]
    fn thumb_alu_and_push_pop() {
        let mut rom = vec![0u8; 0x100];
        rom[0xB2] = 0x96;
        for (i, half) in [0x2105u16, 0x4008, 0xB501, 0xBD01].iter().enumerate() {
            rom[i * 2..i * 2 + 2].copy_from_slice(&half.to_le_bytes());
        }
        let mut bus = Bus::new(rom).unwrap();
        let mut cpu = Cpu::new();
        cpu.cpsr |= CPSR_T;
        cpu.regs[1] = 0x3;
        cpu.regs[13] = 0x0300_7F00;
        cpu.regs[0] = 0x1;
        cpu.step(&mut bus).unwrap(); // MOVS r1,#5
        cpu.step(&mut bus).unwrap(); // ANDS r0,r1
        assert_eq!(cpu.regs[0], 1);
        cpu.step(&mut bus).unwrap(); // PUSH {r0,lr}
        assert_eq!(cpu.regs[13], 0x0300_7EF8);
        cpu.step(&mut bus).unwrap(); // POP {r0,pc}
        assert_eq!(cpu.regs[13], 0x0300_7F00);
    }

    #[test]
    fn thumb_load_store_immediate() {
        let mut rom = vec![0u8; 0x100];
        rom[0xB2] = 0x96;
        for (i, half) in [0x6048u16, 0x684Au16].iter().enumerate() {
            rom[i * 2..i * 2 + 2].copy_from_slice(&half.to_le_bytes());
        }
        let mut bus = Bus::new(rom).unwrap();
        let mut cpu = Cpu::new();
        cpu.cpsr |= CPSR_T;
        cpu.regs[1] = 0x0200_0000;
        cpu.regs[0] = 0xCAFE;
        cpu.step(&mut bus).unwrap();
        cpu.step(&mut bus).unwrap();
        assert_eq!(cpu.regs[2], 0xCAFE);
    }


    #[test]
    fn thumb_sp_relative_str_and_ldr() {
        let code: [u16; 5] = [
            0x2355, // movs r3,#0x55
            0x9304, // str r3,[sp,#0x10]
            0x9A04, // ldr r2,[sp,#0x10]
            0xE7FE, // b .
            0x0000,
        ];
        let mut rom = vec![0u8; 0x100];
        rom[0xB2] = 0x96;
        for (index, half) in code.iter().enumerate() {
            rom[index * 2..index * 2 + 2].copy_from_slice(&half.to_le_bytes());
        }
        let mut bus = Bus::new(rom).unwrap();
        let mut cpu = Cpu::new();
        cpu.cpsr |= CPSR_T;
        cpu.regs[13] = 0x0300_7F00;
        cpu.regs[15] = 0x0800_0000;
        for _ in 0..3 {
            cpu.step(&mut bus).unwrap();
        }
        assert_eq!(bus.read32(0x0300_7F10), 0x55);
        assert_eq!(cpu.regs[2], 0x55);
    }

    #[test]
    fn thumb_subs_rsbs_adcs_equality_trick() {
        // suite 的 `results[i] = (failures_after == failed_before)`：
        //   subs r3,r3,r2 ; rsbs r2,r3,#0 ; adcs r3,r2
        // rd 舊值係 0 嘅情況一定要覆蓋：NEG 的 C 係「b == 0」而唔係
        // `result < rd_old`（後者會令 suite 列表全部變紅）。
        let code: [u16; 9] = [
            0x2305, // movs r3,#5
            0x2205, // movs r2,#5
            0x1A9B, // subs r3,r3,r2
            0x2200, // movs r2,#0
            0x425A, // rsbs r2,r3,#0
            0x4153, // adcs r3,r2
            0xE7FE, // b .
            0x0000,
            0x0000,
        ];
        let mut rom = vec![0u8; 0x100];
        rom[0xB2] = 0x96;
        for (index, half) in code.iter().enumerate() {
            rom[index * 2..index * 2 + 2].copy_from_slice(&half.to_le_bytes());
        }
        let mut bus = Bus::new(rom).unwrap();
        let mut cpu = Cpu::new();
        cpu.cpsr |= CPSR_T;
        cpu.regs[15] = 0x0800_0000;
        for _ in 0..6 {
            cpu.step(&mut bus).unwrap();
        }
        assert_eq!(cpu.regs[3], 1);
    }

    #[test]
    fn thumb_strb_register_offset() {
        // movs r1,#2; lsls x3 → 0x02000000; movs r2,#4; movs r3,#0xAB;
        // strb r3,[r1,r2]; b .
        let code: [u16; 8] = [0x2102, 0x0209, 0x0209, 0x0209, 0x2204, 0x23AB, 0x548B, 0xE7FE];
        let mut rom = vec![0u8; 0x100];
        rom[0xB2] = 0x96;
        for (index, half) in code.iter().enumerate() {
            rom[index * 2..index * 2 + 2].copy_from_slice(&half.to_le_bytes());
        }
        let mut bus = Bus::new(rom).unwrap();
        let mut cpu = Cpu::new();
        cpu.cpsr |= CPSR_T;
        cpu.regs[15] = 0x0800_0000;
        for _ in 0..7 {
            cpu.step(&mut bus).unwrap();
        }
        assert_eq!(bus.read8(0x0200_0004), 0xAB);
    }

    #[test]
    fn arm_ldr_register_offset() {
        let mut bus = bus_with(&[0xE790_1002]); // LDR r1,[r0,r2]
        bus.write32(0x0200_0004, 0x1234_5678);
        let mut cpu = Cpu::new();
        cpu.regs[0] = 0x0200_0000;
        cpu.regs[2] = 4;
        cpu.step(&mut bus).unwrap();
        assert_eq!(cpu.regs[1], 0x1234_5678);
    }

    #[test]
    fn arm_ldr_register_offset_rrx() {
        // LDR r1,[r0,r2,rrx]：ROR #0 編碼是 RRX（C 進 bit31）。
        let mut bus = bus_with(&[0xE790_1062]);
        bus.write32(0x0200_0000, 0x1122_3344);
        let mut cpu = Cpu::new();
        cpu.regs[0] = 0x0200_0004;
        cpu.regs[2] = 0xFFFF_FFFC;
        cpu.cpsr |= CPSR_C;
        cpu.step(&mut bus).unwrap();
        // offset = (1<<31)|(0xFFFFFFFC>>1) = 0xFFFFFFFE → addr = 0x02000002
        // → 對齊字 0x11223344 ROR 16 = 0x33441122
        assert_eq!(cpu.regs[1], 0x3344_1122);
    }

    #[test]
    fn arm_long_multiply_flags_follow_booth_carry() {
        // suite「Multiply long tests」：UMULLS/SMULLS 的 N/Z 用完整 64-bit
        // 結果，C 用 ARM7TDMI Booth multiplier 的 carry（唔係 high word 的 N/Z）。
        // UMULLS r8,r9,r0,r1：0xFFFFFFFF² → 0xFFFFFFFE_00000001，
        // flags N=1 Z=0 C=1。
        let mut bus = bus_with(&[0xE098_9190]);
        let mut cpu = Cpu::new();
        cpu.regs[0] = 0xFFFF_FFFF;
        cpu.regs[1] = 0xFFFF_FFFF;
        cpu.cpsr &= !(CPSR_N | CPSR_Z | CPSR_C | CPSR_V);
        cpu.step(&mut bus).unwrap();
        assert_eq!(cpu.regs[8], 0xFFFF_FFFE);
        assert_eq!(cpu.regs[9], 0x0000_0001);
        assert!(cpu.cpsr & CPSR_N != 0);
        assert_eq!(cpu.cpsr & CPSR_Z, 0);
        assert!(cpu.cpsr & CPSR_C != 0);

        // SMULLS r8,r9,r0,r1：signed (-1)*(-1) = 1，flags N=0 Z=0 C=0。
        let mut bus = bus_with(&[0xE0D8_9190]);
        let mut cpu = Cpu::new();
        cpu.regs[0] = 0xFFFF_FFFF;
        cpu.regs[1] = 0xFFFF_FFFF;
        cpu.cpsr &= !(CPSR_N | CPSR_Z | CPSR_C | CPSR_V);
        cpu.step(&mut bus).unwrap();
        assert_eq!(cpu.regs[8], 0);
        assert_eq!(cpu.regs[9], 1);
        assert_eq!(cpu.cpsr & (CPSR_N | CPSR_Z | CPSR_C), 0);

        // UMULLS r8,r9,r0,r1：0xFFFFFFFF * 1 = 0x00000000_FFFFFFFF，
        // 舊版用 high word 判 Z 會錯設 Z（suite 的 37 個 fail 主因）。
        let mut bus = bus_with(&[0xE098_9190]);
        let mut cpu = Cpu::new();
        cpu.regs[0] = 0xFFFF_FFFF;
        cpu.regs[1] = 1;
        cpu.cpsr &= !(CPSR_N | CPSR_Z | CPSR_C | CPSR_V);
        cpu.step(&mut bus).unwrap();
        assert_eq!(cpu.regs[8], 0);
        assert_eq!(cpu.regs[9], 0xFFFF_FFFF);
        assert_eq!(cpu.cpsr & (CPSR_N | CPSR_Z), 0);
    }

    #[test]
    fn arm_pc_operand_with_register_shift_reads_pc_plus_12() {
        // suite「Shifter tests」：`adds r0, pc, r1, lsl r0`。
        // register-specified shift 時 Rn=PC 要讀 instr+12。
        let mut bus = bus_with(&[0xE09F_0011]);
        let mut cpu = Cpu::new();
        cpu.regs[0] = 0;
        cpu.regs[1] = 1;
        cpu.step(&mut bus).unwrap();
        assert_eq!(cpu.regs[0], 0x0800_000D);

        // 對照：`adds r0, pc, r1, lsl #0`（immediate shift）Rn=PC 讀 instr+8，
        // 再加 r1=1 → 0x08000009。
        let mut bus = bus_with(&[0xE09F_0001]);
        let mut cpu = Cpu::new();
        cpu.regs[1] = 1;
        cpu.step(&mut bus).unwrap();
        assert_eq!(cpu.regs[0], 0x0800_0009);
    }

    #[test]
    fn arm_register_shift_by_zero_is_noop() {
        // MOVS r3,r4,ASR r2（r2=0）：值與 C 都不變。
        let mut bus = bus_with(&[0xE1B0_3254]);
        let mut cpu = Cpu::new();
        cpu.regs[4] = 1;
        cpu.regs[2] = 0;
        cpu.cpsr |= CPSR_C;
        cpu.step(&mut bus).unwrap();
        assert_eq!(cpu.regs[3], 1);
        assert!(cpu.cpsr & CPSR_C != 0);
        assert!(cpu.cpsr & CPSR_Z == 0);
    }

    #[test]
    fn arm_register_shift_reads_pc_plus_12() {
        // MOVS r4,r15,LSL r3（r3=0）→ R15 = 指令位址 + 12。
        let mut bus = bus_with(&[0xE1B0_431F]);
        let mut cpu = Cpu::new();
        cpu.regs[3] = 0;
        cpu.step(&mut bus).unwrap();
        assert_eq!(cpu.regs[4], 0x0800_000C);
    }


    #[test]
    fn irq_exception_banks_and_returns() {
        let mut cpu = Cpu::new();
        cpu.regs[13] = 0x0300_7F00;
        cpu.regs[14] = 0x1111_1111;
        cpu.cpsr = MODE_SVC | CPSR_C;
        cpu.enter_irq(0x0800_0010);
        assert_eq!(cpu.cpsr & CPSR_MODE_MASK, MODE_IRQ);
        assert_eq!(cpu.regs[15], 0x18);
        assert_eq!(cpu.regs[14], 0x0800_0014);
        assert_eq!(cpu.spsr & CPSR_MODE_MASK, MODE_SVC);
        // SVC bank 保留
        assert_eq!(cpu.banked_sp_lr[2][0], 0x0300_7F00);
        cpu.exception_return(0x0800_0010);
        assert_eq!(cpu.cpsr & CPSR_MODE_MASK, MODE_SVC);
        assert_eq!(cpu.regs[13], 0x0300_7F00);
    }

    #[test]
    fn fiq_swaps_r8_r12() {
        let mut cpu = Cpu::new();
        cpu.regs[8] = 0xAAAA_AAAA;
        cpu.regs[13] = 0x0300_7F00;
        cpu.cpsr = MODE_SVC;
        cpu.enter_exception(MODE_FIQ, 0x1C, 0x0800_0020);
        assert_eq!(cpu.regs[8], 0);
        cpu.regs[8] = 0xBBBB_BBBB;
        cpu.exception_return(0x0800_0020);
        assert_eq!(cpu.regs[8], 0xAAAA_AAAA);
    }


    #[test]
    fn msr_cpsr_switches_banked_sp() {
        let mut bus = bus_with(&[0xE129_F000]); // MSR CPSR_c, r9
        let mut cpu = Cpu::new();
        cpu.cpsr = MODE_SYS;
        cpu.regs[13] = 0x1111;
        cpu.usr_sp = 0x1111;
        cpu.banked_sp_lr[2] = [0x0300_7FE0, 0]; // SVC
        cpu.regs[0] = MODE_SVC;
        cpu.step(&mut bus).unwrap();
        assert_eq!(cpu.cpsr & CPSR_MODE_MASK, MODE_SVC);
        assert_eq!(cpu.regs[13], 0x0300_7FE0);
    }

    #[test]
    fn irq_line_enters_exception_at_boundary() {
        let mut bus = bus_with(&[0xE3A0_0001]);
        let mut cpu = Cpu::new();
        cpu.cpsr = MODE_SVC;
        bus.ime = true;
        bus.ie = 1;
        bus.if_ = 1;
        assert_eq!(cpu.check_irq(&mut bus, 1), 0); // arm
        assert_eq!(cpu.check_irq(&mut bus, 1), 0); // countdown
        assert_eq!(cpu.check_irq(&mut bus, 1), 4); // 進場（S+N+I）
        assert_eq!(cpu.cpsr & CPSR_MODE_MASK, MODE_IRQ);
        assert_eq!(cpu.regs[15], 0); // HLE handler pointer = [03007FFC]
        assert_eq!(cpu.regs[14], 0x138);
        assert!(cpu.cpsr & CPSR_I != 0);
    }


    #[test]
    fn cpu_writes_dma_registers_then_transfers() {
        let mut bus = bus_with(&[
            0xE580_1000, // str r1,[r0]      ; DMA0SAD
            0xE580_2004, // str r2,[r0,#4]   ; DMA0DAD
            0xE580_3008, // str r3,[r0,#8]   ; DMA0CNT
        ]);
        bus.write32(0x0200_0000, 0xFEED_FACE);
        let mut cpu = Cpu::new();
        cpu.regs[0] = 0x0400_00B0;
        cpu.regs[1] = 0x0200_0000;
        cpu.regs[2] = 0x0200_0100;
        cpu.regs[3] = 0x8400_0001;
        for _ in 0..3 { cpu.step(&mut bus).unwrap(); }
        bus.service_dma();
        assert_eq!(bus.read32(0x0200_0100), 0xFEED_FACE);
    }

    #[test]
    fn hle_cpuset_unaligned_source() {
        let mut bus = Bus::new(vec![0u8; 0x100]).unwrap();
        for (offset, byte) in [0x0Du8, 0xF0, 0x0D, 0x90].iter().enumerate() {
            bus.write8(0x0200_0000 + offset as u32, *byte);
        }
        let mut cpu = Cpu::new();
        cpu.regs[0] = 0x0200_0001;
        cpu.regs[1] = 0x0200_0100;
        cpu.regs[2] = 4; // 16-bit CpuSet
        cpu.hle_swi(&mut bus, 0x0B).unwrap();
        assert_eq!(bus.read32(0x0200_0100), 0x0090_00F0);

        cpu.regs[0] = 0x0200_0001;
        cpu.regs[1] = 0x0200_0200;
        cpu.regs[2] = 2 | (1 << 26); // 32-bit CpuSet
        cpu.hle_swi(&mut bus, 0x0B).unwrap();
        assert_eq!(bus.read32(0x0200_0200), 0x900D_F00D);
    }

    #[test]
    fn hle_huffman_variable_length_codes() {
        // Codes: 0 -> 0x11, 10 -> 0x22, 11 -> 0x33.
        // 8 symbols = 14 compressed bits, but two 32-bit output words.
        let mut rom = vec![0u8; 0x100];
        rom[0..16].copy_from_slice(&[
            0x08, 0x08, 0x00, 0x00, // header: 8 bytes, 8-bit symbols
            0x03,                   // tree size byte -> 7 tree bytes（bitstream 對齊）
            0x80, 0x11, 0xC0, 0x22, 0x33, 0x00, 0x00,
            0x00, 0x00, 0xD0, 0x5A, // bitstream 0101101011010000（word MSB 起）
        ]);
        let mut bus = Bus::new(rom).unwrap();
        let mut cpu = Cpu::new();
        cpu.regs[0] = 0x0800_0000;
        cpu.regs[1] = 0x0200_0000;
        cpu.hle_swi(&mut bus, 0x13).unwrap();
        assert_eq!(bus.read32(0x0200_0000), 0x1133_2211);
        assert_eq!(bus.read32(0x0200_0004), 0x2211_3322);
        assert_eq!(cpu.regs[1], 0x0200_0008);
    }

    #[test]
    fn hle_arctan_and_arctan2() {
        assert_eq!(biostan(0x1000), 0x9FB);
        assert_eq!(biostan(0x7FFF), 0x16D8);
        let (r0, r1, r3) = biostan_parts(0x3FFF);
        assert_eq!((r0, r1, r3), (0x1FFF, 0xFFFF_C002, 0x8001));
        assert_eq!(biosatan2(0xFFFF_C000, 0), 0x8000);
        assert_eq!(biosatan2(0, 0xFFFF_C000), 0xC000);
        assert_eq!(biosatan2_parts(0, 0x4000), (0x4000, 0x4000));
    }

    #[test]
    fn hle_div_and_sqrt() {
        let mut bus = bus_with(&[0xEF06_0000]); // SWI 06h Div
        let mut cpu = Cpu::new();
        cpu.regs[0] = 0xFFFF_FFF9; // -7
        cpu.regs[1] = 2;
        cpu.step(&mut bus).unwrap();
        assert_eq!(cpu.regs[0], 0xFFFF_FFFD); // -3
        assert_eq!(cpu.regs[1], 0xFFFF_FFFF); // -1
        assert_eq!(cpu.regs[3], 3);

        let mut bus = bus_with(&[0xEF08_0000]); // SWI 08h Sqrt
        let mut cpu = Cpu::new();
        cpu.regs[0] = 81;
        cpu.step(&mut bus).unwrap();
        assert_eq!(cpu.regs[0], 9);
    }

    #[test]
    fn unsupported_opcode_is_reported() {
        let mut bus = bus_with(&[0xF000_0000]);
        let mut cpu = Cpu::new();
        assert!(matches!(cpu.step(&mut bus), Err(CpuError::Unsupported { .. })));
    }
}
