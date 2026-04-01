import time
import pytest


# INFRA-02: sleep_jitter() stays within expected range
def test_sleep_jitter_range(monkeypatch):
    """sleep_jitter(base=1.0, jitter=0.5) must sleep between 0.5 and 1.5 seconds."""
    from shared.rate import sleep_jitter
    slept = []
    monkeypatch.setattr(time, "sleep", lambda s: slept.append(s))
    sleep_jitter(1.0, 0.5)
    assert len(slept) == 1
    assert 0.5 <= slept[0] <= 1.5, f"Expected 0.5-1.5s, got {slept[0]}"


# INFRA-04: retry_with_backoff skips target after N failures, does not raise
def test_retry_skip_on_exhaust(monkeypatch):
    """After max_attempts failures, must return None and not raise."""
    from shared.rate import retry_with_backoff
    calls = []
    monkeypatch.setattr(time, "sleep", lambda s: None)  # skip actual sleep

    @retry_with_backoff(max_attempts=3, base_delay=1.0)
    def always_fails():
        calls.append(1)
        raise ValueError("simulated error")

    result = always_fails()
    assert result is None, "Must return None after exhausting retries"
    assert len(calls) == 3, f"Must attempt exactly 3 times, got {len(calls)}"


# INFRA-04: retry_with_backoff succeeds on second attempt
def test_retry_succeeds_eventually(monkeypatch):
    """Function that fails once then succeeds must return the success value."""
    from shared.rate import retry_with_backoff
    attempt = [0]
    monkeypatch.setattr(time, "sleep", lambda s: None)

    @retry_with_backoff(max_attempts=3, base_delay=1.0)
    def fails_once():
        attempt[0] += 1
        if attempt[0] == 1:
            raise RuntimeError("first failure")
        return "ok"

    result = fails_once()
    assert result == "ok"
    assert attempt[0] == 2
