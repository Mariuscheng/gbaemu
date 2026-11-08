"""基本 logger 設定。

模擬核心本身不呼叫 ``print``；所有診斷訊息走 ``logging``。程式庫預設不安裝
handler（交給宿主程式決定），CLI 會呼叫 :func:`configure`。
"""

from __future__ import annotations

import logging

LOGGER_NAME = "gbaemu"
DEFAULT_FORMAT = "%(asctime)s %(levelname)s %(name)s: %(message)s"


def get_logger(name: str) -> logging.Logger:
    """取得 ``gbaemu.*`` 命名空間下的 logger。"""

    if not name:
        return logging.getLogger(LOGGER_NAME)
    return logging.getLogger(f"{LOGGER_NAME}.{name}")


def configure(level: int = logging.INFO, stream=None) -> None:
    """安裝一個具名 handler；重複呼叫不會重複加 handler。"""

    logger = logging.getLogger(LOGGER_NAME)
    logger.setLevel(level)
    for handler in logger.handlers:
        if getattr(handler, "_gbaemu_handler", False):
            handler.setLevel(level)
            return

    handler = logging.StreamHandler(stream)
    handler.setLevel(level)
    handler.setFormatter(logging.Formatter(DEFAULT_FORMAT))
    handler._gbaemu_handler = True  # type: ignore[attr-defined]
    logger.addHandler(handler)
    logger.propagate = False


__all__ = ["LOGGER_NAME", "DEFAULT_FORMAT", "get_logger", "configure"]
