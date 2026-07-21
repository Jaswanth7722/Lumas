# Lumas

Lumas is an offline-first AI study companion for students who need useful
learning support even when connectivity is unreliable. The hackathon
submission target is the **Windows desktop MVP**: a local Gemma 3 1B tutor that
reads a PDF, retrieves only the relevant evidence, answers questions, creates
quizzes, and persists the learner session in SQLite.

## Hackathon status

- **Production target:** Desktop
- **Future target:** Android (documentation and placeholders only; no runnable
  Android code is part of this submission)
- **Default mode:** Offline local inference with Gemma 3 1B
- **Optional mode:** Connected OpenAI-compatible inference when explicitly
  configured by the user

## What the demo proves

1. Launch Lumas and create a study session.
2. Upload a text-based PDF.
3. Extract and chunk the document locally.
4. Build a local retrieval index with MiniLM embeddings when available.
5. Ask a grounded question and receive an answer from the selected evidence.
6. Generate a quiz from a document chunk.
7. Answer quiz questions and persist the result.
8. Restart Lumas and restore the session, messages, and quiz history.

Lumas never sends the whole PDF to the tutor prompt. Retrieval combines exact
keyword coverage with semantic similarity, filters weak matches, removes
near-duplicate chunks, and forwards only the strongest evidence that fits the
2,048-token local context window.

## Features

- Offline Gemma 3 1B GGUF inference through `llama-cpp-python`
- PDF text extraction with deterministic structure-aware chunking
- Hybrid retrieval: local MiniLM embeddings plus lexical fallback
- Relevance filtering and diversity selection for grounded context
- Automatic prompt compaction for small context windows
- Persistent sessions, messages, documents, chunks, embeddings, quizzes, and
  answers in SQLite
- Text-first desktop UI with loading, error, and recovery states
- Optional OpenAI-compatible online engine behind the same tutor interface

## Architecture

```text
Desktop Web UI (pywebview)
          |
       FastAPI
          |
  ConversationService
      /          \
 RetrievalService  EngineManager
      |             |
 SQLite index   Local Gemma 3 1B
      |
 MiniLM vectors + keyword fallback
```

The provider boundary is `Engine`; the learning workflow lives in services;
persistence is handled by `Storage`; and Android is intentionally outside the
runtime and build for this submission.

## Installation

Requirements:

- Windows 10/11
- Python 3.10+
- `llama-cpp-python` compatible with the local Python installation

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

The repository `config.json` selects the local model path and stores SQLite data
in `lumas_data/lumas.db`. If the GGUF is missing, open Settings and click
**Install model**. Lumas downloads the pinned Gemma 3 1B Q4_K_M file into the
local `models/` directory, validates the GGUF header, and reuses it offline on
future launches.

The optional `all-MiniLM-L6-v2` embedding model is loaded from the local
Hugging Face cache only. If it is unavailable, Lumas immediately uses its
keyword retriever instead of making a network request.

## Run locally

From the repository root:

```powershell
python -m lumas.backend.main
```

For browser-based development instead of the pywebview window:

```powershell
python -m lumas.backend.main --server
```

Then open <http://127.0.0.1:8765/>.

## Windows release

Build the portable desktop bundle from PowerShell:

```powershell
./build_release.ps1
```

The executable is written to:

```text
release/Lumas/Lumas.exe
```

The standard release bundles the 800 MB GGUF beside the executable, so it can
run without firewall or network access. Open Settings → Install model to repair
or replace the local model. Use `./build_release.ps1 -ModelFree` only when you
want a smaller download-on-demand build. Run `Lumas.exe --server` for a headless
API smoke test.

## Project structure

```text
lumas/
  backend/                 FastAPI app, engines, retrieval, services, storage
  frontend/desktop/       Text-first desktop HTML/CSS/JavaScript UI
  tests/                  Unit and API-level tests
android/                   Future-target documentation and placeholders only
models/                   Local GGUF model files (ignored by Git)
lumas_data/               Runtime SQLite data (ignored by Git)
config.json               Local runtime configuration
build_release.ps1         Windows release packaging
DEVPOST_SUBMISSION.md     Copy-ready hackathon submission brief
```

## Verification

```powershell
python -m pytest -q
python -m compileall -q lumas
node --check lumas/frontend/desktop/static/app.js
```

The test suite covers chunking, hybrid retrieval, irrelevant-chunk filtering,
2,048-token prompt compaction, SQLite persistence, and the API chat/quiz flow.
The local model is intentionally not loaded during unit tests.

## Known limitations

- One active PDF is supported in the current chat context.
- Scanned or image-only PDFs need OCR, which is not included.
- First-time local model loading depends on CPU and available RAM.
- MiniLM embeddings require a local model cache; lexical retrieval remains
  available without it.
- Android has no runnable source, Gradle project, NDK, JNI, or APK by design.
