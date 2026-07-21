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
        context_window = getattr(self.engine_manager.settings, "context_size", 2048)
        messages = self.prompt_builder.build_quiz_messages(
            content=chunk["content"],
            num_questions=num_questions,
            context_window=context_window,
        )

        # Attempt generation with one retry
        for attempt in range(2):
            try:
                if attempt == 1:
                    # Retry with stricter reminder
                    retry_messages = messages + [
                        {"role": "user", "content": "IMPORTANT: Return ONLY valid JSON. No other text."}
                    ]
                    raw = engine.generate(messages=retry_messages, max_tokens=768)
                else:
                    raw = engine.generate(messages=messages, max_tokens=768)

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
        quiz = self.storage.get_quiz(quiz_id)
        if not quiz:
            raise ValueError("Quiz not found")
        if question_index < 0 or question_index >= len(quiz["questions"]):
            raise ValueError("Question index is out of range")
        if any(a["question_index"] == question_index for a in self.storage.get_answers_for_quiz(quiz_id)):
            raise ValueError("This question has already been answered")

        question = quiz["questions"][question_index]
        actual_correct_index = int(question["correct_index"])
        if not 0 <= int(student_answer) < len(question["options"]):
            raise ValueError("Answer must identify one of the quiz options")
        is_correct = int(student_answer) == actual_correct_index
        answer_id = self.storage.add_quiz_answer(
            quiz_id=quiz_id,
            question_index=question_index,
            is_correct=is_correct,
            student_answer=str(student_answer),
        )

        correct_answer = question["options"][actual_correct_index]

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
        """Parse JSON from model output, handling common wrapping and quality issues.

        Small local models (including Gemma 3 1B) often produce:
        - Markdown code fences around JSON
        - Missing outer {"questions": [...]} wrapper
        - Only 3 options instead of 4
        - Missing correct_index field
        - Extra non-JSON text before/after
        """
        raw = raw.strip()

        # Remove markdown code fences
        if raw.startswith("```"):
            rest = raw.split("\n", 1)[-1] if "\n" in raw else raw[3:]
            raw = rest.rsplit("```", 1)[0]

        # Strategy 1: Try parsing as a direct array of questions
        arr_start = raw.find("[{")
        arr_end = raw.rfind("]") + 1
        if arr_start >= 0 and arr_end > arr_start:
            try:
                questions = json.loads(raw[arr_start:arr_end])
                questions = _normalize_questions(questions)
                if questions:
                    return questions
            except json.JSONDecodeError:
                pass

        # Strategy 2: Try parsing as wrapped {"questions": [...]}
        start = raw.find("{")
        end = raw.rfind("}") + 1
        if start >= 0 and end > start:
            json_str = raw[start:end]
            try:
                data = json.loads(json_str)
                questions = data.get("questions", [])
                questions = _normalize_questions(questions)
                if questions:
                    return questions
            except json.JSONDecodeError:
                pass

            # Strategy 3: Extract individual question objects from partial JSON
            try:
                import re
                # Match brace-enclosed content that looks like JSON objects
                obj_pattern = r'\{[^{}]*\}'
                matches = re.findall(obj_pattern, json_str)
                candidates = []
                for m in matches:
                    try:
                        q = json.loads(m)
                        if isinstance(q, dict) and "question" in q:
                            candidates.append(q)
                    except Exception:
                        pass
                if candidates:
                    questions = _normalize_questions(candidates)
                    if questions:
                        return questions
            except Exception:
                pass

        logger.warning("Failed to parse quiz JSON from output")
        return None


def _normalize_questions(questions: list[dict]) -> Optional[list[dict]]:
    """Validate and normalize quiz questions, filling in missing fields.

    Handles:
    - Fewer than 4 options (pads up to 4)
    - Missing correct_index (infers from letter/text answer or skips)
    - Non-integer correct_index (converts from letter like A=0, B=1)
    - Out-of-range correct_index (clamps to 0-3)
    """
    normalized = []
    for q in questions:
        if not isinstance(q, dict):
            continue
        if "question" not in q or "options" not in q:
            continue
        if not q["question"] or not q.get("options"):
            continue

        options = list(q["options"])
        if len(options) < 3:
            continue
        # Normalize to exactly 4 options
        while len(options) < 4:
            options.append("D) None of the above")
        options = options[:4]

        # Infer correct_index from multiple possible fields
        raw_correct = q.get("correct_index", q.get("answer", None))
        correct = _infer_correct_index(raw_correct, options)
        if correct is None:
            # Can't determine correct answer - skip this question
            # rather than assigning a wrong answer
            continue

        normalized.append({
            "question": q["question"],
            "options": options,
            "correct_index": correct,
        })

    return normalized if normalized else None


def _infer_correct_index(raw, options) -> Optional[int]:
    """Try to determine the correct answer index from various formats."""
    if raw is None:
        return None

    # If already an int in valid range
    if isinstance(raw, int):
        return max(0, min(3, raw)) if 0 <= raw <= 3 else None

    if isinstance(raw, str):
        raw = raw.strip()

        # Try parsing as integer string: "0", "1", "2", "3"
        if raw in ("0", "1", "2", "3"):
            return int(raw)

        # Try letter format: "A", "B", "C", "D" (case-insensitive)
        letter_map = {"a": 0, "b": 1, "c": 2, "d": 3}
        letter = raw.strip().rstrip(")").lower()
        if letter in letter_map:
            return letter_map[letter]

        # Try matching answer text to one of the options
        if options:
            for i, opt in enumerate(options):
                # Strip prefixes like "A) ", "A. " for matching
                opt_clean = opt.split(") ", 1)[-1] if ") " in opt else opt
                opt_clean = opt_clean.split(". ", 1)[-1] if ". " in opt_clean else opt_clean
                if raw.lower() == opt_clean.lower():
                    return i
                if raw.lower() in opt_clean.lower() or opt_clean.lower() in raw.lower():
                    return i

    return None
