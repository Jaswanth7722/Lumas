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
from pydantic import BaseModel, Field

from ..services.conversation import ConversationService
from ..services.quiz import QuizService
from ..storage.database import Storage
from ..retrieval.chunker import process_document

logger = logging.getLogger(__name__)


# ── Request / Response Models (module-level for FastAPI inspection) ──

class ChatRequest(BaseModel):
    session_id: str
    query: str = Field(min_length=1, max_length=12000)
    document_id: Optional[str] = None
    temperature: Optional[float] = None


class ChatResponse(BaseModel):
    response: str
    session_id: str


class CreateSessionRequest(BaseModel):
    engine_used: Optional[str] = None


class SessionResponse(BaseModel):
    id: str
    engine_used: str
    created_at: float
    last_activity_at: float


class QuizGenerateRequest(BaseModel):
    session_id: str
    chunk_id: str
    num_questions: int = Field(default=5, ge=1, le=10)


class QuizAnswerRequest(BaseModel):
    quiz_id: str
    question_index: int = Field(ge=0)
    student_answer: str
    correct_index: int = Field(ge=0, le=3)


class SettingUpdate(BaseModel):
    value: str


class DocumentResponse(BaseModel):
    id: str
    title: str
    source_filename: str
    created_at: float
    chunks: list[dict] = Field(default_factory=list)


def create_router(
    storage: Storage,
    conversation_service: ConversationService,
    quiz_service: QuizService,
    engine_manager=None,
    model_manager=None,
) -> APIRouter:
    """Create the FastAPI router with all endpoints."""
    router = APIRouter()
    model_manager = model_manager or getattr(engine_manager, "model_manager", None)

    # ── Health ─────────────────────────────────────────────────

    @router.get("/health")
    async def health():
        result = {"status": "ok"}
        if engine_manager is not None:
            result.update({
                "engine": engine_manager.settings.engine,
                "model_path": engine_manager.settings.model_path,
                "model_configured": bool(engine_manager.settings.model_path),
            })
        return result

    @router.get("/models/status")
    async def model_status():
        if model_manager is None:
            raise HTTPException(status_code=503, detail="Model installer is unavailable")
        return model_manager.status()

    @router.post("/models/download", status_code=202)
    async def download_model():
        if model_manager is None:
            raise HTTPException(status_code=503, detail="Model installer is unavailable")
        return model_manager.start_download()

    # ── Documents ─────────────────────────────────────────────

    @router.post("/documents/upload", response_model=DocumentResponse)
    async def upload_document(file: UploadFile = File(...)):
        """Upload a PDF, extract text, chunk it, embed it, and store."""
        if not file.filename or not file.filename.lower().endswith(".pdf"):
            raise HTTPException(status_code=400, detail="Only PDF files are supported")

        import tempfile
        max_upload_bytes = 25 * 1024 * 1024
        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf")
        tmp_path = tmp.name
        tmp.close()
        try:
            content = await file.read()
            if len(content) > max_upload_bytes:
                raise HTTPException(status_code=413, detail="PDF must be smaller than 25 MB")
            with open(tmp_path, "wb") as output:
                output.write(content)

            title = os.path.splitext(file.filename)[0]
            doc_id = storage.add_document(title=title, source_filename=file.filename)

            try:
                chunks = process_document(tmp.name, doc_id)
            except Exception as exc:
                storage.delete_document(doc_id)
                logger.warning("PDF processing failed for %s: %s", file.filename, exc)
                raise HTTPException(status_code=422, detail="Could not extract readable text from this PDF") from exc
            if not chunks:
                storage.delete_document(doc_id)
                raise HTTPException(status_code=422, detail="The PDF did not contain extractable text")
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
                # Reuse the already-loaded indexer for the next query.  This
                # avoids loading MiniLM a second time in RetrievalService.
                if hasattr(conversation_service, "retrieval"):
                    conversation_service.retrieval.embedding_provider = embedder
                    conversation_service.retrieval._embedding_failed = False
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
                os.unlink(tmp_path)
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
        engine_used = body.engine_used
        if not engine_used:
            engine_used = engine_manager.settings.engine if engine_manager is not None else "local"
        session_id = storage.create_session(engine_used=engine_used)
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
        if not storage.get_session(body.session_id):
            raise HTTPException(status_code=404, detail="Session not found")
        if not storage.get_chunk(body.chunk_id):
            raise HTTPException(status_code=404, detail="Chunk not found")
        quiz = quiz_service.generate_quiz(
            session_id=body.session_id,
            chunk_id=body.chunk_id,
            num_questions=body.num_questions,
        )
        if not quiz:
            raise HTTPException(status_code=400, detail="Quiz generation failed - model could not produce valid questions. Try again or use a different chunk.")
        return quiz

    @router.post("/quizzes/answer")
    async def answer_quiz(body: QuizAnswerRequest):
        """Submit an answer to a quiz question."""
        try:
            result = quiz_service.answer_question(
                quiz_id=body.quiz_id,
                question_index=body.question_index,
                student_answer=body.student_answer,
                correct_index=body.correct_index,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return result

    @router.get("/sessions/{session_id}/quiz-results")
    async def get_quiz_results(session_id: str):
        """Get all quiz results for a session."""
        if not storage.get_session(session_id):
            raise HTTPException(status_code=404, detail="Session not found")
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
        # Runtime settings are owned by EngineManager.  The database is kept
        # as a compatibility fallback for older installations that persisted
        # a setting before the runtime configuration was introduced.
        public_runtime_settings = {"engine", "temperature", "context_size", "model_path"}
        if engine_manager is not None and key in public_runtime_settings:
            settings = engine_manager.settings
            return {"key": key, "value": getattr(settings, key)}
        value = storage.get_setting(key)
        if value is None:
            raise HTTPException(status_code=404, detail="Setting not found")
        return {"key": key, "value": value}

    @router.put("/settings/{key}")
    async def set_setting(key: str, body: SettingUpdate):
        if engine_manager is not None:
            try:
                engine_manager.update_setting(key, body.value)
            except (TypeError, ValueError) as exc:
                raise HTTPException(status_code=400, detail=f"Invalid setting {key}: {exc}") from exc
        storage.set_setting(key, body.value)
        return {"key": key, "value": body.value}

    return router
