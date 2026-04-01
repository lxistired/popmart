import os
import tempfile
import pytest


# INFRA-05: get_logger() creates a timestamped log file
def test_logger_creates_file(tmp_path):
    """get_logger() must create a *_ts_*_log.txt file in the logs directory."""
    import logging
    from shared.log import get_logger
    # Temporarily patch the LOG_DIR to tmp_path
    import shared.log as log_mod
    original_log_dir = log_mod.LOG_DIR
    log_mod.LOG_DIR = str(tmp_path)
    try:
        logger = get_logger("test_platform")
        logger.info("test message")
        # Force flush
        for h in logger.handlers:
            h.flush()
        log_files = list(tmp_path.glob("test_platform_ts_*_log.txt"))
        assert len(log_files) == 1, f"Expected 1 log file, got {log_files}"
        content = log_files[0].read_text(encoding='utf-8')
        assert "test message" in content
    finally:
        log_mod.LOG_DIR = original_log_dir
        # Clean up handlers to avoid test pollution
        for h in list(logger.handlers):
            h.close()
            logger.removeHandler(h)
