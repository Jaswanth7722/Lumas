"""QuizService — generates quizzes from document chunks and tracks student answers.

Quizzes are generated content distinct from conversational turns.
Results are stored keyed to chunk and question so progress is visible across sessions.
"""

from __future__ import annotations

import json
import logging
from typing import Optional

from ..engines.manager import EngineManager
from ..prompting.builder import PromptBuilder
from ..storage.database import Storage

logger = logging.getLogger(__name__)


class QuizService:
    """Generates quizzes from document content and tracks student answers."""

    def __init__(
        self,
        storage: Storage,
        engine_manager: EngineManager,
        prompt_builder: Optional[PromptBuilder] = None,
    ):
        self.storage = storage
        self.engine_manager = engine_manager
        self.prompt_builder = prompt_builder or PromptBuilder()

    def generate_quiz(
        self,
        session_id: str,
        chunk_id: str,
        num_questions: int = 5,
    ) -> Optional[dict]:
        """Generate a quiz from a document chunk.

        Returns the quiz dict with id, questions list, or None on failure.
        Has one retry with "valid JSON only" reminder on parse failure.
        """
        chunk = self.storage.get_chunk(chunk_id)
        if not chunk:
            logger.warning("Chunk %s not found", chunk_id)
            return None

        engine = self.engine_manager.get_engine()
        prompt = self.prompt_builder.build_quiz_prompt(
            content=chunk["content"],
            num_questions=num_questions,
        )

        # Attempt generation with one retry
        for attempt in range(2):
            try:
                if attempt == 1:
                    # Retry with stricter reminder
                    retry_prompt = prompt + "\n\nIMPORTANT: Return ONLY valid JSON. No other text."
                    raw = engine.generate_text(prompt=retry_prompt, max_tokens=2048)
                else:
                    raw = engine.generate_text(prompt=prompt, max_tokens=2048)

                # Try to parse JSON
                questions = self._parse_quiz_json(raw)
                if questions:
                    quiz_id = self.storage.create_quiz(
                        session_id=session_id,
                        chunk_id=chunk_id,
                        questions=questions,
                    )
                    quiz = self.storage.get_quiz(quiz_id)
                    logger.info(
                        "Quiz %s generated (%d questions from chunk %s)",
                        quiz_id,
                        len(questions),
                        chunk_id,
                    )
                    return quiz
            except Exception as e:
                logger.warning("Quiz generation attempt %d failed: %s", attempt + 1, e)

        logger.error("Quiz generation failed after 2 attempts for chunk %s", chunk_id)
        return None

    def answer_question(
        self,
        quiz_id: str,
        question_index: int,
        student_answer: str,
        correct_index: int,
    ) -> dict:
        """Record a student's answer to a quiz question.

        Returns the answer record dict.
        """
        is_correct = str(student_answer).strip() == str(correct_index).strip()
        answer_id = self.storage.add_quiz_answer(
            quiz_id=quiz_id,
            question_index=question_index,
            is_correct=is_correct,
            student_answer=str(student_answer),
        )

        # Fetch the quiz to provide feedback
        quiz = self.storage.get_quiz(quiz_id)
        correct_answer = None
        if quiz and question_index < len(quiz["questions"]):
            q = quiz["questions"][question_index]
            correct_answer = q["options"][q["correct_index"]]

        return {
            "id": answer_id,
            "quiz_id": quiz_id,
            "question_index": question_index,
            "is_correct": is_correct,
            "student_answer": student_answer,
            "correct_answer": correct_answer,
        }

    def get_quiz_results(self, session_id: str) -> list[dict]:
        """Get all quiz results for a session with answer details."""
        quizzes = self.storage.get_quizzes_for_session(session_id)
        results = []
        for quiz in quizzes:
            answers = self.storage.get_answers_for_quiz(quiz["id"])
            correct_count = sum(1 for a in answers if a["is_correct"])
            results.append({
                "quiz_id": quiz["id"],
                "chunk_id": quiz["chunk_id"],
                "questions": quiz["questions"],
                "answers": answers,
                "score": f"{correct_count}/{len(quiz['questions'])}",
                "created_at": quiz["created_at"],
            })
        return results

    @staticmethod
    def _parse_quiz_json(raw: str) -> Optional[list[dict]]:
        """Parse JSON from model output, handling common wrapping."""
        # Try direct parse
        raw = raw.strip()
        # Remove code fences if present
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[-1]
            raw = raw.rsplit("```", 1)[0]

        # Find JSON object boundaries
        start = raw.find("{")
        end = raw.rfind("}") + 1
        if start >= 0 and end > start:
            raw = raw[start:end]

        try:
            data = json.loads(raw)
            questions = data.get("questions", [])
            # Validate structure
            for q in questions:
                if not all(k in q for k in ("question", "options", "correct_index")):
                    raise ValueError(f"Missing required keys in question: {q}")
                if len(q["options"]) != 4:
                    raise ValueError(f"Question must have 4 options, got {len(q['options'])}")
                if not 0 <= q["correct_index"] <= 3:
                    raise ValueError(f"correct_index must be 0-3, got {q['correct_index']}")
            return questions
        except (json.JSONDecodeError, ValueError, KeyError) as e:
            logger.warning("Failed to parse quiz JSON: %s", e)
            return None
