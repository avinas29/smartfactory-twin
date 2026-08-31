#!/usr/bin/env python3
"""
Regenerate the screenshots used in the README, the proposal and the deck.

    python run.py --no-browser     # in another shell
    python docs/capture.py

Shots are addressed by deep link rather than by driving the UI, so every capture
lands on the same frame each time and the written submission stays in step with
whatever the pipeline last produced.
"""
from __future__ import annotations

import json
import pathlib
import shutil
import subprocess
import sys
import urllib.error
import urllib.request

DOCS = pathlib.Path(__file__).resolve().parent
OUT = DOCS / "assets"
BASE = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8077"

CHROME_CANDIDATES = [
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Chromium.app/Contents/MacOS/Chromium",
    shutil.which("google-chrome") or "",
    shutil.which("chromium") or "",
]

# name -> (bookmark label, extra query, window size)
SHOTS = [
    ("01-line-baseline",  "Baseline — before the fault",   "view=line",                        "1700,1150"),
    ("02-line-escalated", "BODY-08 escalated",             "view=line&station=BODY-08",        "1700,1500"),
    ("03-traceback",      "Failures confirmed at ASSY-27", "view=trace&gate=27",               "1700,1150"),
    ("04-dark-station",   "BODY-14 escalated",             "view=line&station=BODY-14",        "1700,1500"),
    ("05-validation",     "Failures confirmed at ASSY-27", "view=validation",                  "1700,1800"),
    ("06-business",       "Failures confirmed at ASSY-27", "view=business",                    "1700,1500"),
]


def main() -> None:
    chrome = next((c for c in CHROME_CANDIDATES if c and pathlib.Path(c).exists()), None)
    if not chrome:
        sys.exit("No Chrome/Chromium found.")
    try:
        meta = json.load(urllib.request.urlopen(f"{BASE}/api/meta", timeout=10))
    except (urllib.error.URLError, TimeoutError):
        sys.exit(f"No server at {BASE}. Start it with `python run.py --no-browser`.")

    marks = {b["label"]: int(b["t"]) for b in meta["bookmarks"]}
    OUT.mkdir(parents=True, exist_ok=True)

    for name, label, query, size in SHOTS:
        if label not in marks:
            print(f"  {name:22s} SKIPPED (no bookmark {label!r})")
            continue
        url = f"{BASE}/?t={marks[label]}&{query}"
        target = OUT / f"{name}.png"
        subprocess.run(
            [chrome, "--headless", "--disable-gpu", "--hide-scrollbars",
             f"--window-size={size}", "--virtual-time-budget=9000",
             f"--screenshot={target}", url],
            capture_output=True, timeout=120)
        kb = target.stat().st_size // 1024 if target.exists() else 0
        print(f"  {name:22s} {'OK' if kb else 'FAILED':7s} {kb:>5d} KB   {url}")


if __name__ == "__main__":
    print(f"Capturing from {BASE} -> {OUT}")
    main()
