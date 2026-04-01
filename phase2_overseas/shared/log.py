"""
shared/log.py — 共享日志模块
提供: get_logger(platform) -> logging.Logger; LOG_DIR 常量
"""

import logging
import os
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
LOG_DIR = os.path.join(BASE_DIR, '..')


def get_logger(platform: str) -> logging.Logger:
    """
    Create and return a logger for the given platform.
    Log file: {LOG_DIR}/{platform}_ts_{YYYYMMDD_HHMMSS}_log.txt
    Logger name: popmart.{platform}
    Handlers: FileHandler (utf-8) + StreamHandler
    Guard: if not logger.handlers (safe to call multiple times)
    """
    ts = datetime.now().strftime('%Y%m%d_%H%M%S')
    log_file = os.path.join(LOG_DIR, f'{platform}_ts_{ts}_log.txt')
    logger = logging.getLogger(f'popmart.{platform}')
    logger.setLevel(logging.DEBUG)
    if not logger.handlers:
        fh = logging.FileHandler(log_file, encoding='utf-8')
        fh.setFormatter(logging.Formatter('[%(asctime)s][%(levelname)s] %(message)s'))
        ch = logging.StreamHandler()
        ch.setFormatter(logging.Formatter('[%(asctime)s][%(levelname)s] %(message)s'))
        logger.addHandler(fh)
        logger.addHandler(ch)
    return logger
