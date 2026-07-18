"""LocalEngine — uses llama-cpp-python for local inference via llama.cpp.

Designed for both desktop (llama-cpp-python Python bindings) and Android
(HTTP endpoint exposed by llama.cpp on-device). On desktop, Python bindings
are used directly. On Android, it calls the local HTTP server instead.
"""

from __future__ import annotations

import json
import logging
import time
from typing import Optional

from .base import Engine

logger = logging.getLogger(__name__)


class LocalEngine(Engine):
    """Engine that runs a local model via llama-cpp-python."""

    def __init__(
        self,
        model_path: str,
        context_size: int = 2048,
        temperature: float = 0.7,
        use_http: bool = False,
        http_url: str = "http://localhost:8080",
    ):
        self.model_path = model_path
        self.context_size = context_size
        self._temperature = temperature
        self.use_http = use_http
        self.http_url = http_url.rstrip("/")
        self._model = None

    def _lazy_load(self):
        if self._model is not None or self.use_http:
            return
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

    def _call_http(self, prompt: str, temperature: float, max_tokens: int) -> str:
        """Call llama.cpp's HTTP completion endpoint (Android)."""
        import urllib.request
        data = json.dumps({
            "prompt": prompt,
            "temperature": temperature,
            "n_predict": max_tokens,
            "stop": ["</s>", "<|im_end|>"],
        }).encode()
        req = urllib.request.Request(
            f"{self.http_url}/completion",
            data=data,
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=60) as resp:
            result = json.loads(resp.read().decode())
        return result.get("content", "")

    def generate(
        self,
        messages: list[dict],
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ) -> str:
        temp = temperature if temperature is not None else self._temperature
        tokens = max_tokens or 1024

        if self.use_http:
            # Convert messages to a single prompt (simplified chat format)
            prompt_parts = []
            for msg in messages:
                role = msg.get("role", "user")
                content = msg.get("content", "")
                prompt_parts.append(f"<|im_start|>{role}\n{content}<|im_end|>")
            prompt_parts.append("<|im_start|>assistant\n")
            full_prompt = "\n".join(prompt_parts)
            return self._call_http(full_prompt, temp, tokens)

        self._lazy_load()
        start = time.time()
        response = self._model.create_chat_completion(
            messages=messages,
            temperature=temp,
            max_tokens=tokens,
        )
        elapsed = time.time() - start
        text = response.get("choices", [{}])[0].get("message", {}).get("content", "")
        logger.info("Local generation: %d chars in %.2fs", len(text), elapsed)
        return text

    def generate_text(
        self,
        prompt: str,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ) -> str:
        temp = temperature if temperature is not None else self._temperature
        tokens = max_tokens or 1024

        if self.use_http:
            return self._call_http(prompt, temp, tokens)

        self._lazy_load()
        start = time.time()
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
            if self.use_http:
                import urllib.request
                with urllib.request.urlopen(f"{self.http_url}/health", timeout=5) as resp:
                    return resp.status == 200
            self._lazy_load()
            return self._model is not None
        except Exception:
            return False
