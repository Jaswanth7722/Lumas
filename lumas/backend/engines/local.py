"""Desktop local inference through llama-cpp-python and a GGUF model."""

from __future__ import annotations

import logging
import sys
import time
from pathlib import Path
from typing import Optional

from .base import Engine
from ..models.manager import ModelManager

logger = logging.getLogger(__name__)


class LocalEngine(Engine):
    """Engine that runs a local model via llama-cpp-python."""

    def __init__(
        self,
        model_path: str,
        context_size: int = 2048,
        temperature: float = 0.7,
        model_manager: Optional[ModelManager] = None,
    ):
        path = Path(model_path).expanduser()
        if not path.is_absolute():
            if getattr(sys, "frozen", False):
                project_path = Path(sys.executable).resolve().parent / path
            else:
                project_path = Path(__file__).resolve().parents[3] / path
            if project_path.exists():
                path = project_path
        self.model_path = str(path)
        self.context_size = context_size
        self._temperature = temperature
        self.model_manager = model_manager
        self._model = None

    def _lazy_load(self):
        if self._model is not None:
            return
        if not self.model_path:
            raise FileNotFoundError("Local model path is not configured")
        if not Path(self.model_path).is_file() and self.model_manager is not None:
            logger.info("Local model is missing; starting in-app installation")
            self.model_manager.download_blocking()
            self.model_path = str(self.model_manager.path)
        if not Path(self.model_path).is_file():
            raise FileNotFoundError(f"Local model not found: {self.model_path}")
        try:
            from llama_cpp import Llama
            logger.info("Loading local model from %s", self.model_path)
            self._model = Llama(
                model_path=self.model_path,
                n_ctx=self.context_size,
                verbose=False,
            )
        except ImportError:
            logger.error(
                "llama-cpp-python not installed. "
                "Install with: pip install llama-cpp-python"
            )
            raise

    def _fit_generation_tokens(self, prompt: str, requested: int) -> int:
        """Clamp output tokens so prompt plus output always fits ``n_ctx``."""
        prompt_tokens = len(self._model.tokenize(prompt.encode("utf-8"), add_bos=True))
        available = max(1, self.context_size - prompt_tokens)
        fitted = max(1, min(int(requested), available))
        if fitted < requested:
            logger.warning(
                "Compacted generation budget from %d to %d tokens "
                "(prompt=%d, context=%d)",
                requested,
                fitted,
                prompt_tokens,
                self.context_size,
            )
        return fitted

    def generate(
        self,
        messages: list[dict],
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ) -> str:
        temp = temperature if temperature is not None else self._temperature
        requested_tokens = max_tokens or 1024

        self._lazy_load()
        start = time.time()

        # Build prompt manually using Gemma 3 chat template
        prompt_parts = []
        for msg in messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            if role == "system":
                prompt_parts.append(f"<start_of_turn>user\n{content}<end_of_turn>")
            else:
                prompt_parts.append(f"<start_of_turn>{role}\n{content}<end_of_turn>")
        prompt_parts.append("<start_of_turn>model\n")
        full_prompt = "\n".join(prompt_parts)

        tokens = self._fit_generation_tokens(full_prompt, requested_tokens)
        response = self._model.create_completion(
            prompt=full_prompt,
            temperature=temp,
            max_tokens=tokens,
            stop=["<end_of_turn>", "<start_of_turn>", "</s>", "<|im_end|>"],
        )
        elapsed = time.time() - start
        text = response.get("choices", [{}])[0].get("text", "").strip()
        logger.info("Local generation: %d chars in %.2fs", len(text), elapsed)
        return text

    def generate_text(
        self,
        prompt: str,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ) -> str:
        temp = temperature if temperature is not None else self._temperature
        requested_tokens = max_tokens or 1024

        self._lazy_load()
        start = time.time()
        tokens = self._fit_generation_tokens(prompt, requested_tokens)
        response = self._model.create_completion(
            prompt=prompt,
            temperature=temp,
            max_tokens=tokens,
        )
        elapsed = time.time() - start
        text = response.get("choices", [{}])[0].get("text", "")
        logger.info("Local text generation: %d chars in %.2fs", len(text), elapsed)
        return text

    @property
    def name(self) -> str:
        return f"local ({self.model_path})"

    @property
    def is_online(self) -> bool:
        return False

    def health_check(self) -> bool:
        try:
            self._lazy_load()
            return self._model is not None
        except Exception:
            return False
