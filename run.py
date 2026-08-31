#!/usr/bin/env python3
"""
One command to run the whole thing.

    python run.py

Builds the plant record and fits every model if the artifacts are missing
(about two minutes, once), then serves the dashboard on http://localhost:8077.
"""
from __future__ import annotations

import argparse
import os
import sys
import webbrowser
from pathlib import Path
from threading import Timer

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from twin import config as C  # noqa: E402

REQUIRED = ["events_app.pkl", "units.pkl", "defects.pkl", "episodes.pkl", "risk.pkl"]

# Nothing here is tied to a particular port -- no OAuth callback, no webhook, no
# CORS allow-list -- so honour PORT when a supervisor assigns one and fall back
# to 8077 for a plain `python run.py`.
DEFAULT_PORT = int(os.environ.get("PORT") or 8077)


def artifacts_present() -> bool:
    return (all((C.DATA_DIR / f).exists() for f in REQUIRED)
            and (C.ARTIFACT_DIR / "validation.json").exists())


def main() -> None:
    ap = argparse.ArgumentParser(description="Run the SmartFactory Twin dashboard.")
    ap.add_argument("--port", type=int, default=DEFAULT_PORT)
    ap.add_argument("--rebuild", action="store_true",
                    help="regenerate the plant record and refit every model first")
    ap.add_argument("--no-browser", action="store_true")
    args = ap.parse_args()

    if args.rebuild or not artifacts_present():
        print("Building the plant record and fitting models (about two minutes).\n"
              "This runs once; later starts reuse the artifacts.\n")
        from twin.pipeline import build
        build()
        print()

    import uvicorn
    url = f"http://localhost:{args.port}"
    print(f"\n  SmartFactory Twin  ->  {url}\n")
    if not args.no_browser:
        Timer(1.5, lambda: webbrowser.open(url)).start()
    uvicorn.run("app.main:app", host="127.0.0.1", port=args.port, log_level="warning")


if __name__ == "__main__":
    main()
