"""Phase 5：GBAEnv（observation/action/frame skip/truncation）與 GbaApp facade。"""

from __future__ import annotations

import numpy as np

from gbaemu import Button, EmulatorConfig, TimingMode
from gbaemu.rl import (
    ActionSpec,
    GBAEnv,
    GBAEnvConfig,
    MemoryRange,
    ObservationConfig,
    GbaApp,
)

from .cpu_helpers import arm_words, program_rom

NOP = 0xE1A00000
B_SELF = 0xEAFFFFFE


def _rom(tmp_path) -> str:
    path = tmp_path / "rl.gba"
    path.write_bytes(program_rom(arm_words(NOP, NOP, B_SELF)))
    return str(path)


def _env(tmp_path, *, observation=None, action=None, frame_skip=2, max_steps=10):
    return GBAEnv(
        _rom(tmp_path),
        config=GBAEnvConfig(
            observation=observation or ObservationConfig(resize=(8, 8)),
            action=action or ActionSpec(mode="multi_binary"),
            frame_skip=frame_skip,
            max_episode_steps=max_steps,
        ),
        emulator_config=EmulatorConfig(timing=TimingMode.FUNCTIONAL),
    )


def test_screen_observation_shape_and_reset(tmp_path):
    env = _env(tmp_path)
    obs, info = env.reset(seed=0)
    assert obs.shape == (8, 8)
    assert obs.dtype == np.uint8
    assert info["frames_rendered"] == 0
    assert info["frame_index"] == 0


def test_frame_skip_runs_fixed_frames(tmp_path):
    env = _env(tmp_path, frame_skip=3)
    env.reset(seed=0)
    obs, reward, terminated, truncated, info = env.step([0] * 10)
    assert info["frames_rendered"] == 3
    assert env.emu.frame_index == 3
    assert reward == 0.0
    assert terminated is False
    assert truncated is False


def test_action_is_full_replacement(tmp_path):
    env = _env(tmp_path)
    env.reset(seed=0)
    env.step([1, 0, 0, 0, 0, 0, 0, 0, 0, 0])  # A
    assert env.emu.input.keyinput_mask & 0x1 == 0  # A 按下（active-low）
    env.step([0, 1, 0, 0, 0, 0, 0, 0, 0, 0])  # 只剩 B
    assert env.emu.input.keyinput_mask & 0x1 == 1
    assert env.emu.input.keyinput_mask & 0x2 == 0


def test_truncation_after_max_episode_steps(tmp_path):
    env = _env(tmp_path, max_steps=2)
    env.reset(seed=0)
    _, _, _, truncated, _ = env.step([0] * 10)
    assert truncated is False
    _, _, _, truncated, _ = env.step([0] * 10)
    assert truncated is True


def test_memory_observation_whitelist(tmp_path):
    env = _env(
        tmp_path,
        observation=ObservationConfig(
            source="memory",
            memory_ranges=(MemoryRange("ewram", 0x02000000, 4),),
        ),
    )
    obs, _ = env.reset(seed=0)
    assert obs.shape == (4,)
    assert obs.dtype == np.uint8
    env.emu.memory.write_u8(0x02000000, 0x5A)
    obs, *_ = env.step([0] * 10)
    assert obs[0] == 0x5A


def test_hybrid_observation_is_flat_uint8(tmp_path):
    env = _env(
        tmp_path,
        observation=ObservationConfig(
            source="hybrid",
            resize=(8, 8),
            memory_ranges=(MemoryRange("ewram", 0x02000000, 2),),
        ),
    )
    obs, _ = env.reset(seed=0)
    assert obs.shape == (8 * 8 + 2,)
    assert obs.dtype == np.uint8


def test_discrete_action_sets(tmp_path):
    env = _env(
        tmp_path,
        action=ActionSpec(mode="discrete", discrete_sets=((Button.A,), (Button.B,))),
    )
    env.reset(seed=0)
    env.step(0)  # A
    assert env.emu.input.keyinput_mask & 0x1 == 0
    assert env.emu.input.keyinput_mask & 0x2 == 2
    env.step(1)  # B
    assert env.emu.input.keyinput_mask & 0x1 == 1
    assert env.emu.input.keyinput_mask & 0x2 == 0


def test_env_snapshot_roundtrip(tmp_path):
    env = _env(tmp_path)
    env.reset(seed=0)
    before, *_ = env.step([0] * 10)
    state = env.save_state()
    env.step([1, 0, 0, 0, 0, 0, 0, 0, 0, 0])
    env.load_state(state)
    after, *_ = env.step([0] * 10)
    np.testing.assert_array_equal(before, after)


def test_gbaapp_facade_tick_stop_and_input(tmp_path):
    app = GbaApp(_rom(tmp_path), window="null")
    assert isinstance(app.title, str)
    assert app.tick() is True
    assert app.frames == 1
    assert app.screen.ndarray.shape == (160, 240, 3)

    app.button("A", True)
    assert app.emu.input.keyinput_mask & 0x1 == 0
    app.button("A", False)
    assert app.emu.input.keyinput_mask & 0x1 == 1

    app.stop()
    assert app.tick() is False


def test_gymnasium_check_env(tmp_path):
    gym = __import__("pytest").importorskip("gymnasium")
    from gymnasium.utils.env_checker import check_env

    env = _env(tmp_path, frame_skip=1, max_steps=5)
    check_env(env, skip_render_check=True)
    env.close()
