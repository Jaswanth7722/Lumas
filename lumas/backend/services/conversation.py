"""ConversationService — handles chat messages between user and engine."""

from __future__ import annotations

import logging
from typing import Optional

from ..engines.manager import EngineManager
from ..prompting.builder import PromptBuilder
from ..retrieval.service import RetrievalService
from ..storage.database import Storage

logger = logging.getLogger(__name__)


class ConversationService:
    """Manages the conversation loop: get context → build prompt → generate → store."""

    def __init__(
        self,
        storage: Storage,
        engine_manager: EngineManager,
        retrieval: RetrievalService,
        prompt_builder: Optional[PromptBuilder] = None,
    ):
        self.storage = storage
        self.engine_manager = engine_manager
        self.retrieval = retrieval
        self.prompt_builder = prompt_builder or PromptBuilder()

    def ask(
        self,
        session_id: str,
        query: str,
        document_id: Optional[str] = None,
        temperature: Optional[float] = None,
    ) -> str:
        """Process a user query and return the assistant's response.

        Flow:
          1. Store the user message
          2. Retrieve relevant context chunks
          3. Build the prompt with context + history
          4. Generate response via the active engine
          5. Store the assistant response
          6. Return the response text
        """
        # 1. Store user message
        self.storage.add_message(session_id, "user", query)

        # 2. Retrieve relevant context
        chunks = self.retrieval.retrieve(
            query=query,
            top_k=4,
            document_id=document_id,
        )
        context_chunks = [c["content"] for c in chunks]

        # 3. Get conversation history
        history = self.storage.get_recent_messages(session_id, limit=20)

        # 4. Build prompt
        engine = self.engine_manager.get_engine()
        messages = self.prompt_builder.build_chat_messages(
            query=query,
            context_chunks=context_chunks,
            history=history[:-1],  # Exclude the current query
            context_window=getattr(self.engine_manager.settings, "context_size", 2048),
            max_response_tokens=512,
        )

        # 5. Generate response
        response = engine.generate(
            messages=messages,
            temperature=temperature,
        )

        # 6. Strip any leaked special tokens from response
        response = PromptBuilder.strip_special_tokens(response)

        # 7. Store assistant response
        self.storage.add_message(session_id, "assistant", response)

        logger.info(
            "Session %s: answered query (%d chars, engine=%s, chunks=%d)",
            session_id,
            len(query),
            engine.name,
            len(context_chunks),
        )
        return response
