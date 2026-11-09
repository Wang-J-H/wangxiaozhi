from __future__ import annotations

import asyncio
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

    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
        asyncio.set_event_loop(asyncio.SelectorEventLoop())

    from arq import run_worker
    from server.worker_main import WorkerSettings

    run_worker(WorkerSettings)


if __name__ == "__main__":
    main()
