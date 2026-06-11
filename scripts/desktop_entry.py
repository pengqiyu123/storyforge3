"""PyInstaller entry point for the StoryForge3 desktop backend."""

from __future__ import annotations

import sys

import uvicorn


def main() -> None:
    """Start the FastAPI app directly for frozen desktop builds."""
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8000
    uvicorn.run(
        "storyforge3.api.app:app",
        host="127.0.0.1",
        port=port,
        log_level="info",
        access_log=False,
    )


if __name__ == "__main__":
    main()
