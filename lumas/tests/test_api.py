"""API-level tests for the desktop learning loop."""

import json
import os
import tempfile

from fastapi import FastAPI
from fastapi.testclient import TestClient

from lumas.backend.api.routes import create_router
from lumas.backend.config import Settings
from lumas.backend.prompting.builder import PromptBuilder
from lumas.backend.retrieval.service import RetrievalService
from lumas.backend.services.conversation import ConversationService
from lumas.backend.services.quiz import QuizService
from lumas.backend.storage.database import Storage


class FakeEngine:
    name = "fake-local"
    is_online = False

    def generate(self, messages, temperature=None, max_tokens=None):
        if any("Quiz Generator" in m.get("content", "") for m in messages):
            return json.dumps({"questions": [{
                "question": "Which subject is being studied?",
                "options": ["A) Science", "B) Music", "C) Art", "D) Sport"],
                "correct_index": 0,
            }]})
        return "The study material explains the topic clearly."


class FakeEngineManager:
    def __init__(self):
        self.settings = Settings(engine="local")
        self.engine = FakeEngine()

    def get_engine(self):
        return self.engine

    def update_setting(self, key, value):
        if key == "engine" and value not in ("local", "online"):
            raise ValueError("invalid engine")


def build_client(db_path):
    storage = Storage(db_path)
    manager = FakeEngineManager()
    retrieval = RetrievalService(storage=storage, settings=manager.settings)
    conversation = ConversationService(storage, manager, retrieval, PromptBuilder())
    quizzes = QuizService(storage, manager, PromptBuilder())
    app = FastAPI()
    app.include_router(create_router(storage, conversation, quizzes, manager), prefix="/api")
    return TestClient(app), storage


def test_desktop_chat_quiz_and_persistence_flow():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as db_file:
        db_path = db_file.name
    try:
        client, storage = build_client(db_path)
        document_id = storage.add_document("Lesson", "lesson.pdf")
        storage.add_chunk(
            "chunk-1",
            document_id,
            0,
            "Science explains the study topic.",
            {"heading": "Introduction"},
        )

        session = client.post("/api/sessions", json={})
        assert session.status_code == 200
        session_id = session.json()["id"]
        assert session.json()["engine_used"] == "local"

        chat = client.post("/api/chat", json={
            "session_id": session_id,
            "query": "What does the lesson explain?",
            "document_id": document_id,
        })
        assert chat.status_code == 200
        assert "study material" in chat.json()["response"]

        generated = client.post("/api/quizzes/generate", json={
            "session_id": session_id,
            "chunk_id": "chunk-1",
            "num_questions": 1,
        })
        assert generated.status_code == 200
        quiz_id = generated.json()["id"]

        answer = client.post("/api/quizzes/answer", json={
            "quiz_id": quiz_id,
            "question_index": 0,
            "student_answer": "0",
            "correct_index": 0,
        })
        assert answer.status_code == 200
        assert answer.json()["is_correct"] is True

        results = client.get(f"/api/sessions/{session_id}/quiz-results")
        assert results.status_code == 200
        assert results.json()[0]["score"] == "1/1"

        restored = Storage(db_path)
        assert len(restored.get_messages(session_id)) == 2
        assert restored.get_quiz(quiz_id) is not None
    finally:
        os.unlink(db_path)


def test_invalid_runtime_setting_is_rejected():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as db_file:
        db_path = db_file.name
    try:
        client, _ = build_client(db_path)
        response = client.put("/api/settings/engine", json={"value": "unsupported"})
        assert response.status_code == 400
    finally:
        os.unlink(db_path)
