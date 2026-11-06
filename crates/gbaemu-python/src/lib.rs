//! PyO3 adapter：把 Rust `Core` 包成 Python `NativeCore`。
//!
//! 這是 opt-in backend；Python reference 仍是默認。

use gbaemu_core::{sha256, Core, CoreConfig, SaveKind};
use pyo3::exceptions::PyValueError;
use pyo3::prelude::*;

#[pyclass]
struct NativeCore {
    core: Core,
    rom_sha: [u8; 32],
    config_sha: [u8; 32],
    bios: Vec<u8>,
}

#[pymethods]
impl NativeCore {
    #[new]
    fn new(rom: Vec<u8>, config_sha: Vec<u8>) -> PyResult<Self> {
        let core = Core::new(rom, CoreConfig::default())
            .map_err(|error| PyValueError::new_err(format!("{error:?}")))?;
        let rom_sha = sha256(&core.bus.rom);
        let config_sha: [u8; 32] = config_sha
            .as_slice()
            .try_into()
            .map_err(|_| PyValueError::new_err("config_sha 必須是 32 bytes"))?;
        Ok(Self {
            core,
            rom_sha,
            config_sha,
            bios: Vec::new(),
        })
    }

    /// 載入真實 BIOS（16 KiB）；HLE 開機流程不變，只供應 BIOS 讀值。
    fn load_bios(&mut self, data: Vec<u8>) -> PyResult<()> {
        if data.len() > 0x4000 {
            return Err(PyValueError::new_err(format!(
                "BIOS 必須是 16384 bytes（16 KiB），得到 {}",
                data.len()
            )));
        }
        self.core.load_bios(&data);
        self.bios = data;
        Ok(())
    }

    fn step(&mut self) -> PyResult<u32> {
        self.core
            .step()
            .map_err(|error| PyValueError::new_err(format!("{error:?}")))
    }

    fn reset(&mut self) -> PyResult<()> {
        let rom = self.core.bus.rom.clone();
        let config = self.core.config();
        // 真機 reset 唔會清 battery-backed save；重建 Core 之後要放返。
        let save = self.core.bus.sram.clone();
        self.core = Core::new(rom, config)
            .map_err(|error| PyValueError::new_err(format!("{error:?}")))?;
        if save.len() == self.core.bus.sram.len() {
            self.core.bus.sram.copy_from_slice(&save);
        }
        if !self.bios.is_empty() {
            self.core.load_bios(&self.bios);
        }
        Ok(())
    }

    fn run_frame(&mut self) -> PyResult<(u32, u64, bool, u16)> {
        self.core
            .run_frame()
            .map(|frame| {
                (
                    frame.cycles as u32,
                    self.core.frame_index,
                    self.core.cpu.halted,
                    self.core.bus.if_,
                )
            })
            .map_err(|error| PyValueError::new_err(format!("{error:?}")))
    }

    fn halted(&self) -> bool {
        self.core.cpu.halted
    }

    fn vcount(&self) -> u16 {
        self.core.bus.ppu.vcount()
    }

    fn irq_pending(&self) -> bool {
        self.core.bus.ime && (self.core.bus.ie & self.core.bus.if_) != 0
    }

    fn pc(&self) -> u32 {
        self.core.cpu.regs[15]
    }

    fn cpsr(&self) -> u32 {
        self.core.cpu.cpsr
    }

    fn spsr(&self) -> u32 {
        self.core.cpu.spsr
    }

    fn reg(&self, index: usize) -> u32 {
        self.core.cpu.regs.get(index).copied().unwrap_or(0)
    }

    fn if_flags(&self) -> u16 {
        self.core.bus.if_
    }

    fn set_keyinput(&mut self, value: u16) {
        self.core.bus.keyinput = value & 0x03FF;
    }

    fn keyinput(&self) -> u16 {
        self.core.bus.keyinput
    }

    fn set_sound_enabled(&mut self, enabled: bool) {
        self.core.bus.sound_enabled = enabled;
    }

    fn take_audio(&mut self) -> Vec<u8> {
        self.core.bus.take_pcm()
    }

    fn audio_sample_rate(&self) -> u32 {
        self.core.bus.sound_sample_rate
    }

    fn framebuffer(&self) -> Vec<u8> {
        self.core.framebuffer().to_vec()
    }

    /// 用目前 VRAM／IO／OAM 狀態重畫整個 frame（snapshot 還原後或診斷用）。
    fn render_now(&mut self) {
        self.core.render_now();
    }

    fn save_state(&self) -> Vec<u8> {
        self.core.save_state_with_hashes(self.rom_sha, self.config_sha)
    }

    fn load_state(&mut self, data: &[u8]) -> PyResult<()> {
        self.core
            .load_state(data)
            .map_err(|error| PyValueError::new_err(format!("{error:?}")))
    }

    fn cycles(&self) -> u64 {
        self.core.cycles
    }

    fn cpu_cycles(&self) -> u64 {
        self.core.cpu.cycles
    }

    fn frame_index(&self) -> u64 {
        self.core.frame_index
    }

    fn read8(&mut self, address: u32) -> u8 {
        self.core.bus.read8(address)
    }

    fn read16(&mut self, address: u32) -> u16 {
        self.core.bus.read16(address)
    }

    fn read32(&mut self, address: u32) -> u32 {
        self.core.bus.read32(address)
    }

    fn write8(&mut self, address: u32, value: u8) {
        self.core.bus.write8(address, value);
    }

    fn write16(&mut self, address: u32, value: u16) {
        self.core.bus.write16(address, value);
    }

    fn write32(&mut self, address: u32, value: u32) {
        self.core.bus.write32(address, value);
    }

    fn region(&self, name: &str) -> PyResult<Vec<u8>> {
        let bytes = match name {
            "bios" => &self.core.bus.bios,
            "ewram" => &self.core.bus.ewram,
            "iwram" => &self.core.bus.iwram,
            "io" => &self.core.bus.io,
            "palette" => &self.core.bus.palette,
            "vram" => &self.core.bus.vram,
            "oam" => &self.core.bus.oam,
            "rom" => &self.core.bus.rom,
            "sram" => &self.core.bus.sram,
            _ => return Err(PyValueError::new_err(format!("未知的記憶體區域：{name}"))),
        };
        Ok(bytes.clone())
    }

    /// 卡匣備份媒體類型（`"none"`、`"sram"`、`"flash64"`、`"flash128"`、
    /// `"eeprom512"`、`"eeprom8k"`），由 ROM 簽章偵測。
    fn save_kind(&self) -> &'static str {
        match self.core.bus.save_kind {
            SaveKind::None => "none",
            SaveKind::Sram => "sram",
            SaveKind::Flash64 => "flash64",
            SaveKind::Flash128 => "flash128",
            SaveKind::Eeprom512 => "eeprom512",
            SaveKind::Eeprom8k => "eeprom8k",
        }
    }

    /// 備份記憶體內容（長度＝實際 save 大小；`None` 類型時是 64 KiB 暫存）。
    fn save_ram(&self) -> Vec<u8> {
        self.core.bus.sram.clone()
    }

    /// 匯入 `<rom>.sav`；大小必須同核心的 save media 完全一致。
    fn load_save_ram(&mut self, data: Vec<u8>) -> PyResult<()> {
        let expected = self.core.bus.sram.len();
        if data.len() != expected {
            return Err(PyValueError::new_err(format!(
                "save 檔大小不符（{} != {}）",
                data.len(),
                expected
            )));
        }
        self.core.bus.sram.copy_from_slice(&data);
        Ok(())
    }
}

#[pymodule]
fn _native(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_class::<NativeCore>()?;
    Ok(())
}
