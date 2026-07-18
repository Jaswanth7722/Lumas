"""FastAPI routes for the Lumas backend API.

Provides endpoints for:
  - Documents: upload, list, delete
  - Sessions: create, list, get
  - Chat: send message, get history
  - Quizzes: generate, answer, get results
"""

from __future__ import annotations

import logging
import os
from typing import Optional

from fastapi import APIRouter, HTTPException, UploadFile, File
from pydantic import BaseModel

from ..services.conversation import ConversationService
from ..services.quiz import QuizService
from ..storage.database import Storage
from ..retrieval.chunker import process_document

logger = logging.getLogger(__name__)


# ── Request / Response Models (module-level for FastAPI inspection) ──

class ChatRequest(BaseModel):
    session_id: str
    query: str
    document_id: Optional[str] = None
    temperature: Optional[float] = None


class ChatResponse(BaseModel):
    response: str
    session_id: str


class CreateSessionRequest(BaseModel):
    engine_used: str = "local"


class SessionResponse(BaseModel):
    id: str
    engine_used: str
    created_at: float
    last_activity_at: float


class QuizGenerateRequest(BaseModel):
    session_id: str
    chunk_id: str
    num_questions: int = 5


class QuizAnswerRequest(BaseModel):
    quiz_id: str
    question_index: int
    student_answer: str
    correct_index: int


class SettingUpdate(BaseModel):
    value: str


class DocumentResponse(BaseModel):
    id: str
    title: str
    source_filename: str
    created_at: float
    chunks: list[dict] = []


def create_router(
    storage: Storage,
    conversation_service: ConversationService,
    quiz_service: QuizService,
) -> APIRouter:
    """Create the FastAPI router with all endpoints."""
    router = APIRouter()

    # ── Health ─────────────────────────────────────────────────

    @router.get("/health")
    async def health():
        return {"status": "ok"}

    # ── Documents ─────────────────────────────────────────────

    @router.post("/documents/upload", response_model=DocumentResponse)
    async def upload_document(file: UploadFile = File(...)):
        """Upload a PDF, extract text, chunk it, embed it, and store."""
        if not file.filename or not file.filename.lower().endswith(".pdf"):
            raise HTTPException(status_code=400, detail="Only PDF files are supported")

        import tempfile
        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf")
        try:
            content = await file.read()
            tmp.write(content)
            tmp.close()

            title = os.path.splitext(file.filename)[0]
            doc_id = storage.add_document(title=title, source_filename=file.filename)

            chunks = process_document(tmp.name, doc_id)
            storage.add_chunks(chunks)

            try:
                from ..retrieval.embeddings import MiniLMEmbedding
                embedder = MiniLMEmbedding()
                texts = [c["content"] for c in chunks]
                embeddings = embedder.embed_batch(texts)
                import struct
                emb_tuples = []
                for chunk, emb in zip(chunks, embeddings):
                    blob = struct.pack(f"{len(emb)}f", *emb)
                    emb_tuples.append((chunk["id"], blob))
                storage.add_embeddings(emb_tuples)
                logger.info("Stored %d embeddings", len(emb_tuples))
            except Exception as e:
                logger.warning("Embedding generation skipped: %s", e)

            doc = storage.get_document(doc_id)
            doc_chunks = storage.get_chunks_for_document(doc_id)
            return DocumentResponse(
                id=doc_id,
                title=title,
                source_filename=file.filename,
                created_at=doc["created_at"],
                chunks=[{"id": c["id"], "position": c["position"], "content_preview": c["content"][:200]} for c in doc_chunks],
            )
        finally:
            try:
                os.unlink(tmp.name)
            except Exception:
                pass

    @router.get("/documents", response_model=list[DocumentResponse])
    async def list_documents():
        docs = storage.list_documents()
        result = []
        for doc in docs:
            chunks = storage.get_chunks_for_document(doc["id"])
            result.append(DocumentResponse(
                id=doc["id"],
                title=doc["title"],
                source_filename=doc["source_filename"],
                created_at=doc["created_at"],
                chunks=[{"id": c["id"], "position": c["position"], "content_preview": c["content"][:200]} for c in chunks],
            ))
        return result

    @router.get("/documents/{doc_id}", response_model=DocumentResponse)
    async def get_document(doc_id: str):
        doc = storage.get_document(doc_id)
        if not doc:
            raise HTTPException(status_code=404, detail="Document not found")
        chunks = storage.get_chunks_for_document(doc_id)
        return DocumentResponse(
            id=doc["id"],
            title=doc["title"],
            source_filename=doc["source_filename"],
            created_at=doc["created_at"],
            chunks=[{"id": c["id"], "position": c["position"], "content_preview": c["content"][:200]} for c in chunks],
        )

    @router.delete("/documents/{doc_id}")
    async def delete_document(doc_id: str):
        doc = storage.get_document(doc_id)
        if not doc:
            raise HTTPException(status_code=404, detail="Document not found")
        storage.delete_document(doc_id)
        return {"status": "deleted", "id": doc_id}

    # ── Sessions ──────────────────────────────────────────────

    @router.post("/sessions", response_model=SessionResponse)
    async def create_session(body: CreateSessionRequest):
        session_id = storage.create_session(engine_used=body.engine_used)
        session = storage.get_session(session_id)
        if not session:
            raise HTTPException(status_code=500, detail="Failed to create session")
        return SessionResponse(
            id=session["id"],
            engine_used=session["engine_used"],
            created_at=session["created_at"],
            last_activity_at=session["last_activity_at"],
        )

    @router.get("/sessions", response_model=list[SessionResponse])
    async def list_sessions():
        sessions = storage.list_sessions()
        return [
            SessionResponse(
                id=s["id"],
                engine_used=s["engine_used"],
                created_at=s["created_at"],
                last_activity_at=s["last_activity_at"],
            )
            for s in sessions
        ]

    @router.get("/sessions/{session_id}", response_model=SessionResponse)
    async def get_session(session_id: str):
        session = storage.get_session(session_id)
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")
        return SessionResponse(
            id=session["id"],
            engine_used=session["engine_used"],
            created_at=session["created_at"],
            last_activity_at=session["last_activity_at"],
        )

    @router.delete("/sessions/{session_id}")
    async def delete_session(session_id: str):
        session = storage.get_session(session_id)
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")
        storage.delete_session(session_id)
        return {"status": "deleted", "id": session_id}

    # ── Chat ──────────────────────────────────────────────────

    @router.post("/chat", response_model=ChatResponse)
    async def chat(body: ChatRequest):
        """Send a message in a session and get the assistant's response."""
        session = storage.get_session(body.session_id)
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")

        try:
            response = conversation_service.ask(
                session_id=body.session_id,
                query=body.query,
                document_id=body.document_id,
                temperature=body.temperature,
            )
            return ChatResponse(response=response, session_id=body.session_id)
        except Exception as e:
            logger.error("Chat error: %s", e)
            raise HTTPException(status_code=500, detail=str(e))

    @router.get("/sessions/{session_id}/messages")
    async def get_messages(session_id: str):
        """Get all messages in a session."""
        session = storage.get_session(session_id)
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")
        return storage.get_messages(session_id)

    # ── Quizzes ───────────────────────────────────────────────

    @router.post("/quizzes/generate")
    async def generate_quiz(body: QuizGenerateRequest):
        """Generate a quiz from a document chunk."""
        quiz = quiz_service.generate_quiz(
            session_id=body.session_id,
            chunk_id=body.chunk_id,
            num_questions=body.num_questions,
        )
        if not quiz:
            raise HTTPException(status_code=500, detail="Quiz generation failed")
        return quiz

    @router.post("/quizzes/answer")
    async def answer_quiz(body: QuizAnswerRequest):
        """Submit an answer to a quiz question."""
        result = quiz_service.answer_question(
            quiz_id=body.quiz_id,
            question_index=body.question_index,
            student_answer=body.student_answer,
            correct_index=body.correct_index,
        )
        return result

    @router.get("/sessions/{session_id}/quiz-results")
    async def get_quiz_results(session_id: str):
        """Get all quiz results for a session."""
        return quiz_service.get_quiz_results(session_id)

    # ── Chunks ────────────────────────────────────────────────

    @router.get("/chunks/{chunk_id}")
    async def get_chunk(chunk_id: str):
        chunk = storage.get_chunk(chunk_id)
        if not chunk:
            raise HTTPException(status_code=404, detail="Chunk not found")
        return chunk

    # ── Settings ──────────────────────────────────────────────

    @router.get("/settings/{key}")
    async def get_setting(key: str):
        value = storage.get_setting(key)
        if value is None:
            raise HTTPException(status_code=404, detail="Setting not found")
        return {"key": key, "value": value}

    @router.put("/settings/{key}")
    async def set_setting(key: str, body: SettingUpdate):
        storage.set_setting(key, body.value)
        return {"key": key, "value": body.value}

    return router
