"""
shared/checkpoint.py — 断点续采状态管理
提供: load_checkpoint(platform), save_checkpoint(platform, state), CHECKPOINTS_DIR 常量
"""

import json
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CHECKPOINTS_DIR = os.path.join(BASE_DIR, '..', 'checkpoints')


def _checkpoint_path(platform: str) -> str:
    return os.path.join(CHECKPOINTS_DIR, f'{platform}_checkpoint.json')


def load_checkpoint(platform: str) -> dict:
    """
    Load checkpoint state for a platform.
    Returns {"completed_targets": [], "in_progress": None} if file not found.
    """
    path = _checkpoint_path(platform)
    if os.path.exists(path):
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {"completed_targets": [], "in_progress": None}


def save_checkpoint(platform: str, state: dict):
    """Save checkpoint state for a platform to CHECKPOINTS_DIR/{platform}_checkpoint.json."""
    os.makedirs(CHECKPOINTS_DIR, exist_ok=True)
    path = _checkpoint_path(platform)
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(state, f, indent=2)
