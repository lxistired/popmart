"""
shared/rate.py — 速率控制与错误重试
提供: sleep_jitter(base, jitter), retry_with_backoff 装饰器
"""

import time
import random
import functools


def sleep_jitter(base: float, jitter: float = 0.5):
    """Sleep base*(1+/-jitter) seconds to mimic human browsing patterns."""
    time.sleep(random.uniform(base * (1 - jitter), base * (1 + jitter)))


def retry_with_backoff(max_attempts: int = 3, base_delay: float = 1.0,
                       exceptions=(Exception,), logger=None):
    """
    Decorator: exponential backoff retry.
    Delays: base_delay * 2^(attempt-1) — i.e. 1s, 2s, 4s for base_delay=1.
    After max_attempts failures, logs warning and returns None (does not raise).
    """
    def decorator(fn):
        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            for attempt in range(1, max_attempts + 1):
                try:
                    return fn(*args, **kwargs)
                except exceptions as e:
                    if attempt == max_attempts:
                        if logger:
                            logger.warning(f'SKIP after {max_attempts} attempts: {e}')
                        return None
                    delay = base_delay * (2 ** (attempt - 1))
                    if logger:
                        logger.warning(f'Attempt {attempt} failed: {e}. Retry in {delay}s')
                    time.sleep(delay)
        return wrapper
    return decorator
