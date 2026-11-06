from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_DIR = REPO_ROOT / "backend"
PACKAGE_DIR = BACKEND_DIR / "package"


def configure_import_paths() -> tuple[Path, Path]:
    """Make the source checkout importable without copying the old virtualenv."""
    for path in (BACKEND_DIR, PACKAGE_DIR):
        value = str(path)
        if value in sys.path:
            sys.path.remove(value)
        sys.path.insert(0, value)
    return BACKEND_DIR, PACKAGE_DIR


def main() -> None:
    configure_import_paths()

    import uvicorn

    host = os.environ.get("XIAOZHI_HOST", "127.0.0.1")
    port = int(os.environ.get("XIAOZHI_PORT", "5050"))
    server = uvicorn.Server(
        uvicorn.Config(
            "server.main:app",
            host=host,
            port=port,
            loop="asyncio",
        )
    )

    if sys.platform == "win32":
        asyncio.run(server.serve(), loop_factory=asyncio.SelectorEventLoop)
    else:
        asyncio.run(server.serve())


if __name__ == "__main__":
    main()
