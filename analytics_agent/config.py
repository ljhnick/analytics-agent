"""Persistent configuration and token storage in ~/.analytics-agent/."""

import json
import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)

CONFIG_DIR = Path.home() / ".analytics-agent"
CONFIG_FILE = CONFIG_DIR / "config.json"
TOKEN_FILE = CONFIG_DIR / "tokens.json"


def _ensure_dir():
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)


# ── Config (selected GA4 property, Firebase project, DB connection) ──────

def load_config() -> dict:
    if CONFIG_FILE.exists():
        return json.loads(CONFIG_FILE.read_text())
    return {}


def save_config(cfg: dict):
    _ensure_dir()
    CONFIG_FILE.write_text(json.dumps(cfg, indent=2))
    logger.info(f"Config saved to {CONFIG_FILE}")


def update_config(section: str, data: dict):
    cfg = load_config()
    cfg[section] = data
    save_config(cfg)


def get_config_value(*keys, default=None):
    """Drill into nested config. e.g. get_config_value('ga4', 'property_id')."""
    cfg = load_config()
    for k in keys:
        if isinstance(cfg, dict):
            cfg = cfg.get(k)
        else:
            return default
        if cfg is None:
            return default
    return cfg


# ── OAuth2 Tokens ────────────────────────────────────────────────────────

def load_tokens() -> dict | None:
    if TOKEN_FILE.exists():
        return json.loads(TOKEN_FILE.read_text())
    return None


def save_tokens(token_data: dict):
    _ensure_dir()
    TOKEN_FILE.write_text(json.dumps(token_data, indent=2))
    os.chmod(TOKEN_FILE, 0o600)
    logger.info(f"OAuth2 tokens saved to {TOKEN_FILE}")


def clear_tokens():
    if TOKEN_FILE.exists():
        TOKEN_FILE.unlink()
        logger.info("OAuth2 tokens cleared")


def clear_config():
    if CONFIG_FILE.exists():
        CONFIG_FILE.unlink()
        logger.info("Config cleared")


def clean_all():
    """Remove all stored config and tokens."""
    clear_tokens()
    clear_config()
    if CONFIG_DIR.exists() and not any(CONFIG_DIR.iterdir()):
        CONFIG_DIR.rmdir()
        logger.info(f"Removed empty config directory {CONFIG_DIR}")
