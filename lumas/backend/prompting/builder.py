"""PromptBuilder — assembles system prompts for both engines.

This is the single source of truth for prompt assembly on both platforms.
Keeps prompt logic in one place so desktop (Python) and Android (JS) produce
the same prompt shapes.
"""

from __future__ import annotations

from typing import Optional


class PromptBuilder:
    """Builds prompts for the local and online engines."""

    SYSTEM_TEMPLATE = (
        "You are Lumas, a helpful tutor guiding a student through their learning material. "
        "You have access to the following context from their document to answer accurately.\n\n"
        "Rules:\n"
        "- Answer based on the provided context. If the context doesn't contain enough information, say so.\n"
        "- Be concise but thorough — explain concepts clearly.\n"
        "- Use examples when helpful.\n"
        "- Do not make up facts or cite sources not present in the context.\n"
        "- When the student answers a quiz question incorrectly, explain the correct answer patiently."
    )

    QUIZ_TEMPLATE = (
        "You are Lumas, a quiz generator. Based on the following content from a study document, "
        "generate {num_questions} multiple-choice questions to test understanding of the key concepts.\n\n"
        "Content:\n{content}\n\n"
        "Respond with ONLY valid JSON in the following format — no other text:\n"
        '{{\n'
        '  "questions": [\n'
        '    {{\n'
        '      "question": "What is ...?",\n'
        '      "options": ["A) ...", "B) ...", "C) ...", "D) ..."],\n'
        '      "correct_index": 0\n'
        '    }}\n'
        '  ]\n'
        '}}\n\n'
        "Generate exactly {num_questions} questions. Each must have exactly 4 options. "
        "correct_index must be 0-3 indicating the correct option."
    )

    def __init__(self, system_prompt: Optional[str] = None):
        self.system_prompt = system_prompt or self.SYSTEM_TEMPLATE

    def build_conversation_prompt(
        self,
        query: str,
        context_chunks: list[str],
        conversation_history: Optional[list[dict]] = None,
    ) -> list[dict]:
        """Build a message list for chat-style models (OpenAI, llama.cpp).

        Returns a list of dicts with 'role' and 'content' keys.
        """
        messages = [{"role": "system", "content": self.system_prompt}]

        # Inject retrieved context
        if context_chunks:
            context_block = "\n\n---\n".join(context_chunks)
            messages.append({
                "role": "system",
                "content": f"Relevant document context:\n{context_block}",
            })

        # Add conversation history
        if conversation_history:
            for msg in conversation_history[-20:]:  # Keep last 20 for context window
                messages.append({
                    "role": msg.get("role", "user"),
                    "content": msg.get("content", ""),
                })

        # Add the current query
        messages.append({"role": "user", "content": query})
        return messages

    def build_continuation_prompt(
        self,
        context_chunks: list[str],
        conversation_history: list[dict],
    ) -> list[dict]:
        """Build a prompt for the model to continue the conversation."""
        messages = [{"role": "system", "content": self.system_prompt}]

        if context_chunks:
            context_block = "\n\n---\n".join(context_chunks)
            messages.append({
                "role": "system",
                "content": f"Relevant document context:\n{context_block}",
            })

        for msg in conversation_history:
            messages.append({
                "role": msg.get("role", "user"),
                "content": msg.get("content", ""),
            })

        return messages

    def build_quiz_prompt(self, content: str, num_questions: int = 5) -> str:
        """Build a prompt for quiz generation.

        Returns a single string prompt suitable for any text-completion model.
        """
        return self.QUIZ_TEMPLATE.format(
            content=content,
            num_questions=num_questions,
        )

    def build_quiz_messages(self, content: str, num_questions: int = 5) -> list[dict]:
        """Build message list for quiz generation (chat API)."""
        return [
            {
                "role": "system",
                "content": self.QUIZ_TEMPLATE.format(
                    content=content,
                    num_questions=num_questions,
                ),
            },
            {
                "role": "user",
                "content": f"Generate {num_questions} questions based on the above content.",
            },
        ]

    @staticmethod
    def strip_special_tokens(text: str) -> str:
        """Remove any special/control tokens that might leak from the model."""
        import re
        # Remove common special tokens
        text = re.sub(r'<\|.*?\|>', '', text)
        text = re.sub(r'\[INST\].*?\[/INST\]', '', text, flags=re.DOTALL)
        text = re.sub(r'<s>|</s>', '', text)
        return text.strip()
