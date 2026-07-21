"""Tests for the document chunker."""

from lumas.backend.retrieval.chunker import clean_text, chunk_text, _content_hash
from lumas.backend.prompting.builder import PromptBuilder


def test_clean_text_removes_page_numbers():
    text = "Some content\n42\nMore content"
    cleaned = clean_text(text)
    assert "42" not in cleaned.split("\n"), "Standalone page numbers should be removed"
    assert "Some content" in cleaned
    assert "More content" in cleaned


def test_clean_text_removes_duplicate_headers():
    text = "Header!\n" * 5 + "Actual content"
    cleaned = clean_text(text)
    # The duplicate header should appear at most twice
    assert cleaned.count("Header!") < 3, "Repeated headers should be removed"


def test_chunk_text_produces_stable_ids():
    text = "This is a single paragraph of text without headings.\n" * 50
    chunks1 = chunk_text(text, max_chars=500)
    chunks2 = chunk_text(text, max_chars=500)
    assert len(chunks1) == len(chunks2)
    for c1, c2 in zip(chunks1, chunks2):
        assert c1["id"] == c2["id"], "Chunk IDs should be stable (content-hash based)"


def test_chunk_respects_max_chars():
    # Many small paragraphs separated by blank lines
    text = "\n\n".join([
        "word " * 20,   # ~100 chars
        "word " * 20,   # ~100 chars
        "word " * 20,   # ~100 chars
        "word " * 20,   # ~100 chars
        "word " * 20,   # ~100 chars
    ])
    chunks = chunk_text(text, max_chars=120)
    for c in chunks:
        assert len(c["content"]) <= 200, f"Chunk exceeds max_chars: {len(c['content'])}"
    assert len(chunks) >= 2, "Should be split into multiple chunks"


def test_chunk_has_required_fields():
    text = "## Heading 1\nSome content here.\n\n## Heading 2\nMore content here."
    chunks = chunk_text(text)
    for c in chunks:
        assert "id" in c, f"Chunk missing 'id'"
        assert "position" in c, f"Chunk missing 'position'"
        assert "content" in c, f"Chunk missing 'content'"
        assert "metadata" in c, f"Chunk missing 'metadata'"
        assert "heading" in c["metadata"], f"Chunk metadata missing 'heading'"


def test_content_hash_is_stable():
    text = "Hello, world!"
    h1 = _content_hash(text)
    h2 = _content_hash(text)
    assert h1 == h2
    assert len(h1) == 32  # SHA256 truncated to 32 hex chars


def test_prompt_builder_creates_message_list():
    builder = PromptBuilder()
    messages = builder.build_chat_messages(
        query="What is calculus?",
        context_chunks=["Calculus is the study of change."],
        history=[],
    )
    assert len(messages) == 4  # system + context injection + assistant ack + user
    assert messages[-1]["role"] == "user"
    assert messages[-1]["content"] == "What is calculus?"


def test_prompt_builder_includes_history():
    builder = PromptBuilder()
    history = [
        {"role": "user", "content": "What is math?"},
        {"role": "assistant", "content": "Math is the study of numbers."},
    ]
    messages = builder.build_chat_messages(
        query="Tell me more",
        context_chunks=[],
        history=history,
    )
    assert len(messages) == 4  # system + 2 history + user


def test_prompt_builder_quiz_messages():
    builder = PromptBuilder()
    messages = builder.build_quiz_messages(content="Some study content.", num_questions=3)
    assert len(messages) == 2
    assert "3" in messages[0]["content"]  # num_questions in prompt
