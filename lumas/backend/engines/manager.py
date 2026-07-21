"""EngineManager — selects and provides access to the active engine.

Per spec: no automatic fallback or capability detection for the demo.
Engine choice is fixed per device via settings.
"""

from __future__ import annotations

import logging
from typing import Optional

from .base import Engine
from .local import LocalEngine
from .online import OnlineEngine
from ..config import Settings
from ..models.manager import ModelManager

logger = logging.getLogger(__name__)


class EngineManager:
    """Manages engine selection and lifecycle."""

    def __init__(self, settings: Optional[Settings] = None):
        self.settings = settings or Settings.load()
        self._local: Optional[LocalEngine] = None
        self._online: Optional[OnlineEngine] = None
        self.model_manager = ModelManager(
            model_path=self.settings.model_path,
            model_url=self.settings.model_url,
        )

    def get_engine(self) -> Engine:
        """Get the currently configured engine based on settings."""
        if self.settings.engine == "local":
            return self._get_local()
        else:
            return self._get_online()

    def _get_local(self) -> LocalEngine:
        if self._local is None:
            self._local = LocalEngine(
                model_path=self.settings.model_path,
                context_size=self.settings.context_size,
                temperature=self.settings.temperature,
                model_manager=self.model_manager,
            )
        return self._local

    def _get_online(self) -> OnlineEngine:
        if self._online is None:
            self._online = OnlineEngine(
                api_key=self.settings.openai_api_key,
                model=self.settings.openai_model,
                base_url=self.settings.openai_base_url,
                temperature=self.settings.temperature,
            )
        return self._online

    def switch_engine(self, engine_type: str) -> Engine:
        """Switch the active engine type and return it."""
        if engine_type not in ("local", "online"):
            raise ValueError(f"Unknown engine type: {engine_type}")
        self.settings.engine = engine_type  # type: ignore
        return self.get_engine()

    def update_setting(self, key: str, value: str) -> None:
        """Apply a persisted UI setting to the active engine configuration.

        Rebuilding the cached engine after a model-affecting change keeps the
        settings screen and the next chat request in sync.
        """
        if key == "engine":
            if value not in ("local", "online"):
                raise ValueError("engine must be 'local' or 'online'")
            self.settings.engine = value  # type: ignore
        elif key == "temperature":
            temperature = float(value)
            if not 0 <= temperature <= 2:
                raise ValueError("temperature must be between 0 and 2")
            self.settings.temperature = temperature
        elif key == "context_size":
            context_size = int(value)
            if context_size not in (1024, 2048, 4096, 8192):
                raise ValueError("context_size must be one of 1024, 2048, 4096, or 8192")
            self.settings.context_size = context_size
        elif key == "model_path":
            self.settings.model_path = value
            self.model_manager = ModelManager(
                model_path=self.settings.model_path,
                model_url=self.settings.model_url,
            )
        else:
            return

        self._local = None
        self._online = None
        self.settings.save()

    @property
    def engine_name(self) -> str:
        """Name of the currently selected engine."""
        try:
            return self.get_engine().name
        except Exception:
            return "unavailable"
