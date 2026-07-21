# Lumas — Devpost Submission Brief

Use this document as the copy-ready starting point for the OpenAI Build Week
Devpost form. Do not include private API keys or local model files in the
submission archive.

## Project name

Lumas

## One-line description

An offline-first AI study companion that keeps the same learner, memory, and
study workflow available with or without internet access.

## Inspiration

Most AI tutors assume a fast, cheap, continuous connection. That excludes
students in rural areas, classrooms, travel, and homes with metered or unstable
internet. Lumas treats offline access as a primary product requirement while
using online capability as an optional ceiling for harder questions.

## What it does

Lumas runs a local Gemma 3 1B teaching model on the desktop. A student uploads a
PDF, Lumas extracts and chunks it, builds a local retrieval index, and sends
only the most relevant evidence to the tutor. The student can ask grounded
questions, generate a quiz from a selected chunk, answer it, and return later
to the same persisted session.

The connected engine is optional. The interface and learner workflow remain the
same when switching providers.

## How OpenAI technology fits

The application has a provider boundary so connected inference can be enabled
without changing the tutor workflow. The optional online engine uses an
OpenAI-compatible API configuration, while the default demo path remains fully
local and does not require a key or network connection.

## Why it matters

Offline mode solves access, privacy, latency, and cost. Online mode solves the
capability ceiling. Both modes share the same study history and retrieval
workflow, so switching connectivity never resets the student's learning
context.

## Technical implementation

- Python, FastAPI, and pywebview for the desktop application
- Gemma 3 1B GGUF with `llama-cpp-python` for local inference
- In-app model installer that downloads, validates, and caches the GGUF on
  first use
- MiniLM embeddings with lexical fallback for offline retrieval
- Hybrid ranking, exact heading boosts, relevance filtering, and duplicate
  suppression
- Automatic prompt compaction with a 2,048-token local context budget
- SQLite persistence for documents, chunks, vectors, sessions, messages, quizzes,
  and answers
- HTML/CSS/JavaScript text-first interface

## Demo script

1. Launch `Lumas.exe`.
2. If the model is missing, open Settings and click **Install model**; wait for
   the download to complete once, then continue offline.
3. Create a new session.
3. Upload a text-based school PDF.
4. Select the uploaded document.
5. Ask: “Explain the most important topics in chapter 1.”
6. Ask a second question that requires a different section, demonstrating that
   retrieval changes the evidence set instead of sending the whole PDF.
7. Open Quizzes and generate a quiz from the active chunk.
8. Select answers and show the persisted score.
9. Restart the app and show that the session and results remain.
10. Optionally switch to the connected provider only when an API key is
    intentionally configured.

## Submission assets

- Repository: this Lumas repository
- Desktop artifact: `release/Lumas/Lumas.exe`
- Demo screenshots: capture the Chat, Documents, and Quizzes views after the
  final local run
- Demo video: record the flow above, including one offline question and one
  restart/persistence check

## Known limitations to disclose

- The submission supports one active PDF at a time.
- OCR for scanned PDFs is not included.
- The local GGUF model is installed on demand by the desktop app; the optional
  embedding model is loaded from a local cache.
- Android is a documented future target and is not presented as an implemented
  submission platform.