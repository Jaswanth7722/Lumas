"""Configuration for Lumas backend.

Loads from config.json (desktop) or environment variables.
Provides a single source of truth for all settings.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal, Optional

EngineType = Literal["local", "online"]


@dataclass
class Settings:
    """All configuration values for Lumas."""

    # Engine
    engine: EngineType = "local"

    # Model
    model_path: str = ""
    context_size: int = 2048
    temperature: float = 0.7

    # Embedding
    embedding_model: str = "all-MiniLM-L6-v2"

    # Storage
    sqlite_path: str = "lumas_data/lumas.db"

    # API
    openai_api_key: str = ""
    openai_model: str = "gpt-5.6"
    openai_base_url: str = "https://api.openai.com/v1"

    # Server
    host: str = "127.0.0.1"
    port: int = 8765

    # Internal
    _config_path: str = ""

    @classmethod
    def load(cls, config_path: Optional[str] = None) -> "Settings":
        """Load configuration from a JSON file and environment overrides.

        Priority (highest wins):
          1. Environment variables (LUMAS_*)
          2. Config file
          3. Defaults
        """
        cfg_path = config_path or os.environ.get("LUMAS_CONFIG", "config.json")

        # Start with defaults
        settings = cls()

        # Try loading from config file
        if cfg_path and Path(cfg_path).exists():
            try:
                with open(cfg_path) as f:
                    data = json.load(f)
                for key, value in data.items():
                    if hasattr(settings, key):
                        setattr(settings, key, value)
                settings._config_path = cfg_path
            except (json.JSONDecodeError, IOError) as e:
                import logging
                logging.warning("Failed to load config from %s: %s", cfg_path, e)

        # Environment variable overrides (LUMAS_<KEY>)
        env_prefix = "LUMAS_"
        for env_key, env_value in os.environ.items():
            if env_key.startswith(env_prefix):
                attr_name = env_key[len(env_prefix):].lower()
                if hasattr(settings, attr_name):
                    # Cast to the right type
                    current = getattr(settings, attr_name)
                    if isinstance(current, bool):
                        setattr(settings, attr_name, env_value.lower() in ("1", "true", "yes"))
                    elif isinstance(current, int):
                        setattr(settings, attr_name, int(env_value))
                    elif isinstance(current, float):
                        setattr(settings, attr_name, float(env_value))
                    else:
                        setattr(settings, attr_name, env_value)

        # If engine is "online", require API key from env
        if settings.engine == "online":
            settings.openai_api_key = settings.openai_api_key or os.environ.get("OPENAI_API_KEY", "")

        return settings

    def save(self, path: Optional[str] = None) -> None:
        """Save current settings to a JSON file."""
        save_path = path or self._config_path or "config.json"
        data = {
            "engine": self.engine,
            "model_path": self.model_path,
            "context_size": self.context_size,
            "temperature": self.temperature,
            "embedding_model": self.embedding_model,
            "sqlite_path": self.sqlite_path,
            "openai_model": self.openai_model,
            "openai_base_url": self.openai_base_url,
            "host": self.host,
            "port": self.port,
        }
        os.makedirs(os.path.dirname(save_path) or ".", exist_ok=True)
        with open(save_path, "w") as f:
            json.dump(data, f, indent=2)
