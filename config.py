"""Settings persistence for ClaudeWatch (~/.claudewatch/config.json)."""

import json
import os

CONFIG_DIR = os.path.expanduser("~/.claudewatch")
CONFIG_PATH = os.path.join(CONFIG_DIR, "config.json")

DEFAULTS = {
    "sound_enabled": True,
    "flash_enabled": True,
    "muted": False,
    "volume": "loud",  # loud, medium, low
}

VOLUME_LEVELS = {
    "loud": 1.0,
    "medium": 0.5,
    "low": 0.2,
}


def load():
    """Load config from disk, returning defaults for missing keys."""
    cfg = dict(DEFAULTS)
    try:
        with open(CONFIG_PATH, "r") as f:
            saved = json.load(f)
        cfg.update(saved)
    except (FileNotFoundError, json.JSONDecodeError):
        pass
    return cfg


def save(cfg):
    """Persist config to disk."""
    os.makedirs(CONFIG_DIR, exist_ok=True)
    with open(CONFIG_PATH, "w") as f:
        json.dump(cfg, f, indent=2)


def get_volume_float(cfg):
    """Return the numeric volume (0.0–1.0) for the current setting."""
    return VOLUME_LEVELS.get(cfg.get("volume", "loud"), 1.0)
