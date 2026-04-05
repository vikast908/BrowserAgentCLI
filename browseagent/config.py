"""Application settings loaded from ~/.browseagent/config.yaml."""

from __future__ import annotations

import os
from dataclasses import dataclass, field, fields
from pathlib import Path
from typing import Any

import yaml


DEFAULT_CONFIG_DIR = Path.home() / ".browseagent"
DEFAULT_CONFIG_FILE = DEFAULT_CONFIG_DIR / "config.yaml"


@dataclass
class Settings:
    """Runtime configuration for BrowseAgent."""

    default_provider: str = "lm_studio"
    lm_studio_url: str = "http://localhost:1234"
    default_model: str = "qwen3-8b"
    headless: bool = True
    max_steps: int = 40
    screenshot: bool = False
    browser: str = "chromium"  # chromium | firefox | webkit
    data_dir: str = str(DEFAULT_CONFIG_DIR / "runs")

    # Cloud provider API keys (loaded from env if not in config)
    anthropic_api_key: str = ""
    openai_api_key: str = ""

    def __post_init__(self) -> None:
        if not self.anthropic_api_key:
            self.anthropic_api_key = os.environ.get("ANTHROPIC_API_KEY", "")
        if not self.openai_api_key:
            self.openai_api_key = os.environ.get("OPENAI_API_KEY", "")

    @property
    def runs_dir(self) -> Path:
        path = Path(self.data_dir)
        path.mkdir(parents=True, exist_ok=True)
        return path

    @property
    def config_dir(self) -> Path:
        DEFAULT_CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        return DEFAULT_CONFIG_DIR


def load_settings(config_path: Path | None = None) -> Settings:
    """Load settings from YAML config file, falling back to defaults."""
    path = config_path or DEFAULT_CONFIG_FILE
    if not path.exists():
        return Settings()

    with open(path) as f:
        data: dict[str, Any] = yaml.safe_load(f) or {}

    # Only pass keys that match Settings fields
    valid_keys = {f.name for f in fields(Settings)}
    filtered = {k: v for k, v in data.items() if k in valid_keys}
    return Settings(**filtered)


def save_settings(settings: Settings, config_path: Path | None = None) -> None:
    """Persist current settings to YAML config file."""
    path = config_path or DEFAULT_CONFIG_FILE
    path.parent.mkdir(parents=True, exist_ok=True)

    data = {f.name: getattr(settings, f.name) for f in fields(Settings)}
    # Don't persist API keys to disk
    data.pop("anthropic_api_key", None)
    data.pop("openai_api_key", None)

    with open(path, "w") as f:
        yaml.dump(data, f, default_flow_style=False, sort_keys=False)
