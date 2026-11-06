"""G6 opt-in Rust backend smoke tests（extension 未 build 時 skip）。"""

from __future__ import annotations

import pytest

pytest.importorskip("gbaemu._native")

from gbaemu import NativeEmulator  # noqa: E402


def _rom(path):
    rom = bytearray(0x4000)
    rom[0xB2] = 0x96
    rom[0:4] = (0xEAFFFFFE).to_bytes(4, "little")
    path.write_bytes(rom)
    return path


def test_native_frame_and_snapshot(tmp_path):
    emu = NativeEmulator.from_rom(_rom(tmp_path / "frame.gba"))
    try:
        frame = emu.step_frame()
        assert frame.cycles == 280896
        assert len(emu.framebuffer()) == 240 * 160 * 3

        saved = emu.save_state()
        assert saved[:4] == b"GEMU"
        emu.load_state(saved)
        assert emu.frame_index == frame.frame_index
    finally:
        emu.close()


def test_native_mode3_framebuffer(tmp_path):
    emu = NativeEmulator.from_rom(_rom(tmp_path / "mode3.gba"))
    try:
        emu.write_u16(0x0400_0000, 3)
        emu.write_u16(0x0600_0000, 0x001F)
        emu.step_frame()
        assert emu.framebuffer()[:3] == b"\xff\x00\x00"
    finally:
        emu.close()


def test_native_snapshot_cross_backend(tmp_path):
    from gbaemu import BootMode, Emulator, EmulatorConfig

    path = _rom(tmp_path / "cross.gba")
    config = EmulatorConfig(boot_mode=BootMode.TEST_ROM_ONLY)
    native = NativeEmulator.from_rom(path, config)
    python = Emulator.from_rom(path, config=config)
    try:
        native.step_frame()
        python.load_state(native.save_state())
        assert python.cycles == native.cycles

        python.step_frame()
        native.load_state(python.save_state())
        assert native.frame_index == python.frame_index
    finally:
        native.close()
        python.close()


def test_native_facade_matches_python(tmp_path):
    from gbaemu import Emulator

    path = _rom(tmp_path / "facade.gba")
    native = NativeEmulator.from_rom(path)
    python = Emulator.from_rom(path)
    try:
        assert native.config == python.config
        assert native.rom_path == python.rom_path
        assert native.rom_header == python.rom_header
        assert native.is_closed is False

        for _ in range(2):
            assert native.step_frame().cycles == python.step_frame().cycles
            assert native.cpu.state() == python.cpu.state()
            assert native.video.read_frame() == python.video.read_frame()
            for name in ("r0", "r15", "cpsr", "spsr"):
                assert native.cpu.read_register(name) == python.cpu.read_register(name)
            for address in (0x0200_0000, 0x0300_0000, 0x0500_0000, 0x0600_0000):
                assert native.memory.read(address, 16) == python.memory.read(address, 16)

        from gbaemu.api_types import MemoryRegionKind

        for kind in (
            MemoryRegionKind.EWRAM,
            MemoryRegionKind.IWRAM,
            MemoryRegionKind.PALETTE,
            MemoryRegionKind.VRAM,
            MemoryRegionKind.OAM,
            MemoryRegionKind.ROM,
        ):
            assert native.memory.read_region(kind) == python.memory.read_region(kind)
            assert native.memory.region_info(kind) == python.memory.region_info(kind)
        assert native.memory.region_info(MemoryRegionKind.OPEN_BUS).size == 0

        native.pause()
        results = native.run_frames(2, collect_results=True)
        python.run_frames(2)
        assert len(results) == 2
        assert native.frame_index == python.frame_index
    finally:
        native.close()
        python.close()
    assert native.is_closed is True


def test_native_input_keyinput(tmp_path):
    from gbaemu import Button

    emu = NativeEmulator.from_rom(_rom(tmp_path / "input.gba"))
    try:
        emu.input.press(Button.A)
        emu.step_frame()
        assert emu.read_u16(0x0400_0130) & 0x1 == 0
        emu.input.release(Button.A)
        emu.step_frame()
        assert emu.read_u16(0x0400_0130) & 0x1 == 1
    finally:
        emu.close()


def test_native_keypad_irq(tmp_path):
    from gbaemu import Button

    emu = NativeEmulator.from_rom(_rom(tmp_path / "keyirq.gba"))
    try:
        emu.write_u16(0x0400_0132, 0x4001)  # IRQ enable, OR, A
        emu.input.press(Button.A)
        emu.step_frame()
        assert emu.read_u16(0x0400_0202) & 0x1000
    finally:
        emu.close()


def test_native_audio_pcm_buffer(tmp_path):
    from gbaemu import AudioMode, BootMode, EmulatorConfig

    config = EmulatorConfig(boot_mode=BootMode.TEST_ROM_ONLY, audio=AudioMode.BUFFERED)
    emu = NativeEmulator.from_rom(_rom(tmp_path / "audio.gba"), config)
    try:
        assert emu.audio.read_buffer() == b""
        emu.write_u16(0x0400_0082, 0x0804)  # FIFO A enable + 100%
        emu.write_u32(0x0400_00A0, 0x8080_8080)
        emu.step_frame()
        pcm = emu.audio.read_buffer()
        assert pcm
        assert len(pcm) % 4 == 0
        assert emu.audio.sample_rate == 32768
        assert emu.audio.read_buffer() == b""
    finally:
        emu.close()


def test_native_gbaenv_smoke(tmp_path, monkeypatch):
    from gbaemu.api_types import GBAEnvConfig
    from gbaemu.rl.env import GBAEnv

    monkeypatch.setenv("GBAEMU_BACKEND", "rust")
    env = GBAEnv(
        _rom(tmp_path / "env.gba"),
        GBAEnvConfig(frame_skip=1, max_episode_steps=1),
    )
    try:
        observation, info = env.reset()
        assert observation.shape == (84, 84)
        assert info["halted"] is False
        observation, reward, terminated, truncated, info = env.step([0] * 10)
        assert observation.shape == (84, 84)
        assert reward == 0.0
        assert terminated is False
        assert truncated is True
    finally:
        env.close()


def test_gbaapp_prefers_native_backend(tmp_path, monkeypatch):
    from gbaemu import GbaApp

    monkeypatch.delenv("GBAEMU_BACKEND", raising=False)
    app = GbaApp(_rom(tmp_path / "gui.gba"), window="null")
    try:
        assert isinstance(app.emu, NativeEmulator)
        assert app.tick() is True
        assert app.frames == 1
    finally:
        app.stop()


def test_emulator_from_rom_honours_backend_env(tmp_path, monkeypatch):
    from gbaemu import Emulator

    monkeypatch.setenv("GBAEMU_BACKEND", "rust")
    emu = Emulator.from_rom(_rom(tmp_path / "backend.gba"))
    try:
        assert isinstance(emu, NativeEmulator)
        assert emu.step_frame().cycles == 280896
    finally:
        emu.close()
