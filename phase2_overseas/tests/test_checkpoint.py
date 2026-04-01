import json
import os
import pytest


# INFRA-07: save/load checkpoint roundtrip; completed_targets persists across loads
def test_checkpoint_roundtrip(tmp_path, monkeypatch):
    """save_checkpoint then load_checkpoint must return identical state."""
    from shared.checkpoint import load_checkpoint, save_checkpoint
    import shared.checkpoint as cp_mod
    monkeypatch.setattr(cp_mod, "CHECKPOINTS_DIR", str(tmp_path))

    state = {
        "run_started": "2026-03-28T10:00:00",
        "completed_targets": ["B0DT44TSM2", "B0FJFV4PQN"],
        "in_progress": {"asin": "B0DWXDYD7X", "last_page": 3}
    }
    save_checkpoint("amazon", state)

    loaded = load_checkpoint("amazon")
    assert loaded["completed_targets"] == ["B0DT44TSM2", "B0FJFV4PQN"]
    assert loaded["in_progress"]["last_page"] == 3


def test_checkpoint_missing_returns_empty(tmp_path, monkeypatch):
    """load_checkpoint for unknown platform must return empty state (not raise)."""
    from shared.checkpoint import load_checkpoint, save_checkpoint
    import shared.checkpoint as cp_mod
    monkeypatch.setattr(cp_mod, "CHECKPOINTS_DIR", str(tmp_path))

    result = load_checkpoint("nonexistent_platform")
    assert result["completed_targets"] == []
    assert result["in_progress"] is None
