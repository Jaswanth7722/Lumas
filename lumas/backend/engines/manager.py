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

logger = logging.getLogger(__name__)


class EngineManager:
    """Manages engine selection and lifecycle."""

    def __init__(self, settings: Optional[Settings] = None):
        self.settings = settings or Settings.load()
        self._local: Optional[LocalEngine] = None
        self._online: Optional[OnlineEngine] = None

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

    @property
    def engine_name(self) -> str:
        """Name of the currently selected engine."""
        try:
            return self.get_engine().name
        except Exception:
            return "unavailable"
