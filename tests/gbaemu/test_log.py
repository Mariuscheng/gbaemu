"""Phase 0 驗收：基本 logger（規格 Phase 0 交付項「基本 logger」）。"""

from __future__ import annotations

import io
import logging

import pytest

from gbaemu import log


@pytest.fixture
def isolated_gbaemu_logger():
    """隔離全域 logging 狀態；測試結束後還原 handler、等級與 propagate。"""

    logger = logging.getLogger(log.LOGGER_NAME)
    saved_handlers = list(logger.handlers)
    saved_level = logger.level
    saved_propagate = logger.propagate
    try:
        yield logger
    finally:
        for handler in list(logger.handlers):
            if handler not in saved_handlers:
                logger.removeHandler(handler)
        for handler in saved_handlers:
            if handler not in logger.handlers:
                logger.addHandler(handler)
        logger.setLevel(saved_level)
        logger.propagate = saved_propagate


def test_get_logger_uses_gbaemu_namespace():
    assert log.get_logger("") is logging.getLogger(log.LOGGER_NAME)
    nested = log.get_logger("hle.postboot")
    assert isinstance(nested, logging.Logger)
    assert nested.name == "gbaemu.hle.postboot"


def test_configure_adds_one_handler_and_is_idempotent(isolated_gbaemu_logger):
    logger = isolated_gbaemu_logger
    before = len(logger.handlers)

    log.configure(logging.WARNING)
    handlers = [h for h in logger.handlers if getattr(h, "_gbaemu_handler", False)]
    assert len(handlers) == 1
    assert len(logger.handlers) == before + 1

    handler = handlers[0]
    assert handler.level == logging.WARNING
    assert handler.formatter is not None
    assert handler.formatter._fmt == log.DEFAULT_FORMAT
    assert logger.level == logging.WARNING
    assert logger.propagate is False

    # 重複呼叫只調整等級，不新增 handler。
    log.configure(logging.DEBUG)
    assert [h for h in logger.handlers if getattr(h, "_gbaemu_handler", False)] == [handler]
    assert handler.level == logging.DEBUG
    assert logger.level == logging.DEBUG


def test_configure_stream_receives_records(isolated_gbaemu_logger):
    stream = io.StringIO()
    log.configure(logging.INFO, stream=stream)

    log.get_logger("audit").info("hello")
    output = stream.getvalue()
    assert "hello" in output
    assert "gbaemu.audit" in output
