"""Document chunker — structure-based chunking with stable content-hash IDs.

Pipeline: extract text → clean artifacts → chunk by heading/paragraph → hash IDs.
"""

from __future__ import annotations

import hashlib
import logging
import re
from typing import Optional

logger = logging.getLogger(__name__)


def extract_text_from_pdf(path: str) -> str:
    """Extract text from a PDF file.

    Tries pypdf first, falls back to pdfplumber.
    """
    try:
        import pypdf
        reader = pypdf.PdfReader(path)
        text = "\n".join(page.extract_text() or "" for page in reader.pages)
        if text.strip():
            logger.info("Extracted text via pypdf (%d chars)", len(text))
            return text
    except Exception as e:
        logger.warning("pypdf failed: %s", e)

    try:
        import pdfplumber
        with pdfplumber.open(path) as pdf:
            text = "\n".join(page.extract_text() or "" for page in pdf.pages)
        logger.info("Extracted text via pdfplumber (%d chars)", len(text))
        return text
    except Exception as e:
        logger.warning("pdfplumber also failed: %s", e)
        raise ValueError(f"Could not extract text from {path}")


def clean_text(text: str) -> str:
    """Clean extraction artifacts: page numbers, repeated headers/footers, etc."""
    # Remove standalone page numbers (lines that are just a number)
    text = re.sub(r'\n\d+\n', '\n', text)
    # Remove repeated header/footer patterns (same line appearing on every page)
    lines = text.split('\n')
    seen = {}
    cleaned = []
    for line in lines:
        stripped = line.strip()
        if not stripped:
            cleaned.append(line)
            continue
        # Skip lines that appear 3+ times (likely headers/footers)
        seen[stripped] = seen.get(stripped, 0) + 1
        if seen[stripped] < 3:
            cleaned.append(line)
    return '\n'.join(cleaned)


def chunk_text(text: str, max_chars: int = 2000, overlap: int = 100) -> list[dict]:
    """Split text into chunks based on structure (headings/paragraphs).

    Args:
        text: The cleaned text to chunk.
        max_chars: Maximum characters per chunk.
        overlap: Character overlap between consecutive chunks.

    Returns:
        List of dicts with keys: id, position, content, metadata.
    """
    # Detect headings (common patterns like ##, __, ALL CAPS lines)
    heading_pattern = re.compile(r'^(#{1,6}\s+|___.+___$|[A-Z][A-Z\s]+$)', re.MULTILINE)
    sections = []

    # Split by headings first
    parts = re.split(heading_pattern, text, maxsplit=0)

    current_section = ""
    current_heading = ""

    for part in parts:
        if re.match(heading_pattern, part):
            if current_section.strip():
                sections.append({
                    "heading": current_heading,
                    "content": current_section.strip(),
                })
            current_heading = part.strip()
            current_section = ""
        else:
            current_section += part

    if current_section.strip():
        sections.append({
            "heading": current_heading,
            "content": current_section.strip(),
        })

    # If no headings found, treat whole text as one section
    if not sections and text.strip():
        sections.append({"heading": "", "content": text.strip()})

    # Chunk each section
    chunks = []
    chunk_position = 0

    for section in sections:
        content = section["content"]
        heading = section["heading"]

        if len(content) <= max_chars:
            # Small enough for one chunk
            chunk_id = _content_hash(f"{heading}\n{content}")
            heading_prefix = f"## {heading}\n\n" if heading else ""
            chunks.append({
                "id": chunk_id,
                "position": chunk_position,
                "content": f"{heading_prefix}{content}",
                "metadata": {"heading": heading, "section": True},
            })
            chunk_position += 1
        else:
            # Split long sections into paragraphs
            paragraphs = content.split('\n\n')
            current_chunk = ""
            for para in paragraphs:
                if len(current_chunk) + len(para) + 2 > max_chars and current_chunk:
                    chunk_id = _content_hash(current_chunk)
                    heading_prefix = f"## {heading}\n\n" if heading else ""
                    chunks.append({
                        "id": chunk_id,
                        "position": chunk_position,
                        "content": f"{heading_prefix}{current_chunk.strip()}",
                        "metadata": {"heading": heading, "section": False},
                    })
                    chunk_position += 1
                    # Overlap: keep the last `overlap` chars
                    current_chunk = current_chunk[-overlap:] if len(current_chunk) > overlap else ""
                current_chunk += para + "\n\n"

            if current_chunk.strip():
                chunk_id = _content_hash(current_chunk)
                heading_prefix = f"## {heading}\n\n" if heading else ""
                chunks.append({
                    "id": chunk_id,
                    "position": chunk_position,
                    "content": f"{heading_prefix}{current_chunk.strip()}",
                    "metadata": {"heading": heading, "section": False},
                })
                chunk_position += 1

    logger.info("Text chunked into %d chunks", len(chunks))
    return chunks


def process_document(path: str, document_id: str, max_chars: int = 2000) -> list[dict]:
    """Full document processing pipeline: extract → clean → chunk.

    Returns chunks ready for storage with document_id set.
    """
    text = extract_text_from_pdf(path)
    text = clean_text(text)
    chunks = chunk_text(text, max_chars=max_chars)

    for chunk in chunks:
        chunk["document_id"] = document_id

    return chunks


def _content_hash(text: str) -> str:
    """Generate a stable content-hash ID for a chunk."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:32]
