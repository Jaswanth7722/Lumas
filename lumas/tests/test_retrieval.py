"""Tests for the retrieval service."""

import os
import tempfile

from lumas.backend.retrieval.service import RetrievalService
from lumas.backend.storage.database import Storage


def test_keyword_retrieval_returns_relevant_chunks():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    try:
        storage = Storage(db_path=db_path)
        doc_id = storage.add_document("Test", "test.pdf")

        chunks = [
            {"id": "c1", "document_id": doc_id, "position": 0, "content": "Photosynthesis is the process plants use to convert sunlight into energy.", "metadata": {}},
            {"id": "c2", "document_id": doc_id, "position": 1, "content": "Mitosis is cell division that produces two identical daughter cells.", "metadata": {}},
            {"id": "c3", "document_id": doc_id, "position": 2, "content": "Gravity is a force that attracts objects with mass toward each other.", "metadata": {}},
        ]
        storage.add_chunks(chunks)

        retrieval = RetrievalService(storage=storage)

        # Search for photosynthesis content
        results = retrieval.retrieve("sunlight energy plants", top_k=2)
        assert len(results) > 0
        assert results[0]["id"] == "c1"  # Most relevant

        # Search for cell division
        results = retrieval.retrieve("cell division identical", top_k=2)
        assert len(results) > 0
        assert results[0]["id"] == "c2"

        # Search for gravity
        results = retrieval.retrieve("force mass attraction", top_k=2)
        assert len(results) > 0
        assert results[0]["id"] == "c3"
    finally:
        os.unlink(db_path)


def test_retrieval_with_document_filter():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    try:
        storage = Storage(db_path=db_path)
        doc1 = storage.add_document("Doc1", "d1.pdf")
        doc2 = storage.add_document("Doc2", "d2.pdf")

        chunks = [
            {"id": "c1", "document_id": doc1, "position": 0, "content": "Python is a programming language.", "metadata": {}},
            {"id": "c2", "document_id": doc2, "position": 0, "content": "Python is also a type of snake.", "metadata": {}},
        ]
        storage.add_chunks(chunks)

        retrieval = RetrievalService(storage=storage)

        # Should only return from doc1
        results = retrieval.retrieve("programming language", top_k=5, document_id=doc1)
        assert len(results) == 1
        assert results[0]["id"] == "c1"

        # Should only return from doc2
        results = retrieval.retrieve("snake", top_k=5, document_id=doc2)
        assert len(results) == 1
        assert results[0]["id"] == "c2"
    finally:
        os.unlink(db_path)


def test_empty_retrieval():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    try:
        storage = Storage(db_path=db_path)
        retrieval = RetrievalService(storage=storage)
        results = retrieval.retrieve("anything", top_k=5)
        assert results == []
    finally:
        os.unlink(db_path)
