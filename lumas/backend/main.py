"""Main entry point for the Lumas desktop backend.

Serves the FastAPI API and the desktop frontend (HTML/JS/CSS) for pywebview.
"""

from __future__ import annotations

import logging
import os
import threading
from pathlib import Path
from typing import Optional

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from .api.routes import create_router
from .config import Settings
from .engines.manager import EngineManager
from .prompting.builder import PromptBuilder
from .retrieval.service import RetrievalService
from .services.conversation import ConversationService
from .services.quiz import QuizService
from .storage.database import Storage

logger = logging.getLogger(__name__)

# Path to the desktop frontend directory
FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend" / "desktop"
STATIC_DIR = FRONTEND_DIR / "static"


def create_app(settings: Optional[Settings] = None) -> FastAPI:
    """Create and configure the Lumas FastAPI application."""
    settings = settings or Settings.load()

    # Initialize storage
    storage = Storage(db_path=settings.sqlite_path)

    # Initialize engine manager
    engine_manager = EngineManager(settings=settings)

    # Initialize retrieval service
    retrieval = RetrievalService(storage=storage, settings=settings)

    # Initialize prompt builder
    prompt_builder = PromptBuilder()

    # Initialize services
    conversation_service = ConversationService(
        storage=storage,
        engine_manager=engine_manager,
        retrieval=retrieval,
        prompt_builder=prompt_builder,
    )
    quiz_service = QuizService(
        storage=storage,
        engine_manager=engine_manager,
        prompt_builder=prompt_builder,
    )

    # Create FastAPI app
    app = FastAPI(title="Lumas", version="1.0.0")

    # CORS (allow pywebview and any local frontend)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Register API routes
    router = create_router(
        storage=storage,
        conversation_service=conversation_service,
        quiz_service=quiz_service,
        engine_manager=engine_manager,
    )
    app.include_router(router, prefix="/api")

    # Serve static files (JS, CSS) with no-cache headers
    os.makedirs(str(STATIC_DIR), exist_ok=True)

    class NoCacheStaticFiles(StaticFiles):
        """StaticFiles that adds no-cache headers to prevent stale JS/CSS."""
        async def get_response(self, path: str, scope):
            response = await super().get_response(path, scope)
            if path.endswith(".js") or path.endswith(".css"):
                response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
                response.headers["Pragma"] = "no-cache"
                response.headers["Expires"] = "0"
            return response

    app.mount("/static", NoCacheStaticFiles(directory=str(STATIC_DIR)), name="static")

    # Serve index.html for the root and all non-API paths (SPA-like)
    @app.get("/")
    async def serve_index():
        response = FileResponse(str(FRONTEND_DIR / "index.html"))
        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        response.headers["Pragma"] = "no-cache"
        return response

    return app


def run_server(settings: Optional[Settings] = None) -> None:
    """Run the FastAPI server."""
    settings = settings or Settings.load()
    app = create_app(settings)
    logger.info(
        "Starting Lumas server on http://%s:%d",
        settings.host,
        settings.port,
    )
    uvicorn.run(
        app,
        host=settings.host,
        port=settings.port,
        log_level="info",
    )


def run_desktop(settings: Optional[Settings] = None) -> None:
    """Run the Lumas desktop application with pywebview UI."""
    settings = settings or Settings.load()

    # Start server in background thread
    server_thread = threading.Thread(
        target=run_server,
        args=(settings,),
        daemon=True,
    )
    server_thread.start()

    # Give the server a moment to start
    import time
    time.sleep(1.5)

    # Launch pywebview
    try:
        import webview
        window = webview.create_window(
            title="Lumas — Your On-Device Tutor",
            url=f"http://{settings.host}:{settings.port}",
            width=1200,
            height=800,
            resizable=True,
            min_size=(800, 600),
        )
        webview.start()
    except ImportError:
        logger.warning(
            "pywebview not installed. Server is running at http://%s:%s",
            settings.host,
            settings.port,
        )
        # Keep the server running
        server_thread.join()


if __name__ == "__main__":
    import sys

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    settings = Settings.load()

    if "--headless" in sys.argv or "--server" in sys.argv:
        run_server(settings)
    else:
        run_desktop(settings)
