"""Konfigurations-Helfer: Env-File, Verzeichnisse, Domain-Seed, Limits, API-Key."""

from __future__ import annotations

import logging
import os

logger = logging.getLogger(__name__)


def load_env_file(path: str = "~/.config/vault_watcher/env") -> None:
    """Populate os.environ from a simple KEY=VALUE config file.

    Existing environment variables are not overridden, so systemd's
    EnvironmentFile (or a real shell export) always wins over the file.
    """
    env_path = os.path.expanduser(path)
    if not os.path.exists(env_path):
        return
    try:
        with open(env_path, encoding="utf-8") as f:
            for raw in f:
                line = raw.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, _, value = line.partition("=")
                os.environ.setdefault(key.strip(), value.strip())
    except OSError as e:
        logger.error("Failed to read env file %s: %s", env_path, e)


def resolve_dir(env_var: str, default: str) -> str:
    """Resolve a directory from an env var, falling back to a default (expands ~)."""
    return os.path.expanduser(os.environ.get(env_var) or default)


# Existing Titan domains to steer classification toward a consistent graph.
# Gemini may still invent a new domain when none of these fit.
_DEFAULT_DOMAINS = ("business", "lernen", "projekte", "system")


def get_known_domains() -> list[str]:
    """Return the seed list of Titan domains (comma-separated env override)."""
    raw = os.environ.get("VAULT_WATCHER_DOMAINS", "")
    domains = [d.strip() for d in raw.split(",") if d.strip()]
    return domains or list(_DEFAULT_DOMAINS)


# Maximum characters of extracted text sent to Gemini. Longer inputs are
# truncated: the prompt budget is finite and the most relevant signal in a
# captured document is almost always near the top.
_DEFAULT_MAX_CHARS = 200_000


def get_max_chars() -> int:
    """Return the prompt char limit (``VAULT_WATCHER_MAX_CHARS``, positive int)."""
    raw = os.environ.get("VAULT_WATCHER_MAX_CHARS", "")
    try:
        value = int(raw)
    except ValueError:
        return _DEFAULT_MAX_CHARS
    return value if value > 0 else _DEFAULT_MAX_CHARS


def load_api_key() -> str | None:
    """Load the Gemini API key from environment or config file."""
    # 1. Try environment
    api_key = os.environ.get("GEMINI_API_KEY")
    if api_key and api_key != "YOUR_GEMINI_API_KEY_HERE":
        return api_key
    # 2. Try configuration env file
    env_path = os.path.expanduser("~/.config/vault_watcher/env")
    if os.path.exists(env_path):
        try:
            with open(env_path, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line.startswith("GEMINI_API_KEY="):
                        val = line.split("GEMINI_API_KEY=", 1)[1].strip()
                        if val and val != "YOUR_GEMINI_API_KEY_HERE":
                            return val
        except Exception as e:
            logger.error("Failed to read env file: %s", e)
    return None
