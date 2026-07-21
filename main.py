"""PyInstaller entry point for the Lumas desktop release."""

from __future__ import annotations

import logging
import sys

from lumas.backend.config import Settings
from lumas.backend.main import run_desktop, run_server


def main() -> None:
    """Launch the desktop UI, or the local server for diagnostics."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    settings = Settings.load()
    if "--server" in sys.argv or "--headless" in sys.argv:
        run_server(settings)
    else:
        run_desktop(settings)


if __name__ == "__main__":
    main()
