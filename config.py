"""``EmulatorConfig`` 的驗證與正規化。

型別本身定義在 :mod:`gbaemu.api_types`（規格 5.2）；本模組只放驗證與
snapshot 用的 canonical serialization，避免型別定義與規則分散。
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from .errors import InvalidConfigError


def validate_config(config) -> None:
    """驗證 ``EmulatorConfig``；違反契約 raise :class:`InvalidConfigError`。"""

    # 延遲匯入，避免 api_types <-> config 的模組載入循環。
    from .api_types import AudioMode, BootMode, TimingMode, VideoMode

    for field_name, enum_type in (
        ("boot_mode", BootMode),
        ("timing", TimingMode),
        ("video", VideoMode),
        ("audio", AudioMode),
    ):
        value = getattr(config, field_name)
        if not isinstance(value, enum_type):
            raise InvalidConfigError(
                f"{field_name} 必須是 {enum_type.__name__}，得到 {type(value).__name__}"
            )

    if config.bios_path is not None and not isinstance(config.bios_path, Path):
        raise InvalidConfigError("bios_path 必須是 pathlib.Path 或 None")

    for field_name in ("deterministic", "hle_strict"):
        if not isinstance(getattr(config, field_name), bool):
            raise InvalidConfigError(f"{field_name} 必須是 bool")

    if isinstance(config.seed, bool) or not isinstance(config.seed, int):
        raise InvalidConfigError("seed 必須是 int")

    if config.boot_mode is BootMode.REQUIRE_BIOS and config.bios_path is None:
        raise InvalidConfigError("REQUIRE_BIOS 需要 bios_path")

    # 規格 5.2：HLE_ADVANCED 同時提供 bios_path 是允許的（供等價測試），
    # HLE 不會用它執行啟動流程。


def canonical_config_bytes(config) -> bytes:
    """產生穩定、可跨行程比較的 config 序列化（供 snapshot 的 config hash）。

    只納入會改變模擬結果的欄位：``boot_mode``、``hle_strict``、``timing``、
    ``video``、``audio``，以及規格允許影響 RNG 注入的 ``deterministic``/``seed``。

    ``bios_path`` 刻意不納入：路徑本身不是模擬語意的一部分，且 snapshot 需要可攜。
    BIOS 內容的等價性應由「HLE vs 真實 BIOS」測試處理，而不是靠路徑字串。
    """

    payload = {
        "audio": config.audio.value,
        "boot_mode": config.boot_mode.value,
        "deterministic": bool(config.deterministic),
        "hle_strict": bool(config.hle_strict),
        "seed": int(config.seed),
        "timing": config.timing.value,
        "video": config.video.value,
    }
    text = json.dumps(payload, ensure_ascii=True, separators=(",", ":"), sort_keys=True)
    return text.encode("ascii")


def config_sha256(config) -> bytes:
    """回傳 ``canonical_config_bytes()`` 的 SHA-256（32 bytes）。"""

    return hashlib.sha256(canonical_config_bytes(config)).digest()


__all__ = ["validate_config", "canonical_config_bytes", "config_sha256"]
