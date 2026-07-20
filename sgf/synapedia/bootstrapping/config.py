"""config.py — load pipeline_config.json from project root.

Provides a shared configuration for device, model, and pipeline settings
across all scripts (compute_embeddings.py, microgloss.py, setup_vocab.py,
run_microgloss_pipeline.py).

Usage:
    from config import get_config, reload_config

    cfg = get_config()
    device = cfg["device"]["type"]           # "dml", "cuda", "cpu", etc.
    providers = cfg["device"]["providers"]   # ["DmlExecutionProvider", "CPUExecutionProvider"]
    max_length = cfg["pipeline"]["max_length"]
"""

import json
from pathlib import Path

_CONFIG_PATH = Path(__file__).parent / "pipeline_config.json"

_config_cache = None


def get_config():
    """Load pipeline_config.json and return the parsed dict.

    Caches the result so subsequent calls are fast (no re-read from disk).
    Use reload_config() to force a re-read after changing the file.
    """
    global _config_cache
    if _config_cache is None:
        if not _CONFIG_PATH.exists():
            raise FileNotFoundError(
                f"Configuration file not found: {_CONFIG_PATH}\n"
                f"Create pipeline_config.json in the project root directory."
            )
        with open(_CONFIG_PATH, 'r') as f:
            _config_cache = json.load(f)
    return _config_cache


def reload_config():
    """Force re-read of pipeline_config.json on next get_config() call."""
    global _config_cache
    _config_cache = None
    return get_config()