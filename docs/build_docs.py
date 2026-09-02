#!/usr/bin/env python3
"""
Build the submission PDFs.

    python docs/build_docs.py

Renders README.md and the business proposal to print-ready PDFs through headless
Chrome, so the written submission cannot drift from the repository: the README
PDF is generated from the same README.md that GitHub serves, and every figure in
the proposal is read from artifacts/validation.json rather than typed in.
"""
from __future__ import annotations

import base64
import json
import mimetypes
import pathlib
import re
import shutil
import subprocess
import sys

import markdown

ROOT = pathlib.Path(__file__).resolve().parent.parent
DOCS = ROOT / "docs"
OUT = DOCS
CHROME_CANDIDATES = [
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Chromium.app/Contents/MacOS/Chromium",
    shutil.which("google-chrome") or "",
    shutil.which("chromium") or "",
]

# Accenture purple, carried over from the Round 1 deck.
CSS = """
@page { size: A4; margin: 16mm 15mm 18mm; }
:root{ --purple:#a100ff; --deep:#3d0066; --ink:#16171c; --mid:#4a4f5c;
       --soft:#787f8e; --rule:#e2e5ea; --wash:#faf7ff;
       --ok:#0f8a4a; --warn:#b8730a; --bad:#c62334; }
*{ box-sizing:border-box; }
body{ font:10.5pt/1.55 -apple-system,"Segoe UI",Helvetica,Arial,sans-serif;
      color:var(--ink); margin:0; }
h1{ font-size:26pt; line-height:1.12; letter-spacing:-.02em; margin:0 0 4pt;
    color:var(--deep); }
h2{ font-size:15pt; margin:22pt 0 7pt; padding-bottom:4pt; letter-spacing:-.01em;
    border-bottom:2px solid var(--purple); color:var(--deep);
    break-after:avoid; }
h3{ font-size:11.5pt; margin:15pt 0 5pt; color:var(--deep); break-after:avoid; }
h1+h3{ font-size:15pt; color:var(--purple); margin:2pt 0 10pt; font-weight:600; }
p,li{ margin:0 0 7pt; }
ul,ol{ padding-left:16pt; margin:0 0 9pt; }
strong{ color:#000; }
em{ color:var(--mid); }
a{ color:var(--purple); text-decoration:none; }
code{ font:9pt "SF Mono",Menlo,Consolas,monospace; background:var(--wash);
      border:1px solid #ece3f7; border-radius:3px; padding:.5pt 3pt; }
pre{ background:#f7f8fa; border:1px solid var(--rule); border-left:3px solid var(--purple);
     border-radius:4px; padding:8pt 10pt; overflow:hidden; break-inside:avoid; }
pre code{ background:none; border:0; padding:0; font-size:8.4pt; line-height:1.45; }
blockquote{ margin:11pt 0; padding:9pt 13pt; background:var(--wash);
            border-left:3px solid var(--purple); border-radius:0 4px 4px 0;
            font-size:11.5pt; color:var(--deep); font-weight:600; }
blockquote p{ margin:0; }
table{ width:100%; border-collapse:collapse; margin:9pt 0 12pt; font-size:9.2pt;
       break-inside:avoid; }
th{ text-align:left; background:var(--deep); color:#fff; font-weight:600;
    padding:5.5pt 7pt; font-size:8.4pt; letter-spacing:.03em;
    text-transform:uppercase; }
td{ padding:5pt 7pt; border-bottom:1px solid var(--rule); vertical-align:top; }
tbody tr:nth-child(even){ background:#fbfbfd; }
/* Cap image height so a full-width screenshot still fits beside text rather
   than being bumped to the next page and leaving half a page blank. */
img{ max-width:100%; max-height:95mm; width:auto; display:block;
     margin:10pt auto 4pt; border:1px solid var(--rule); border-radius:5px; }
hr{ border:0; border-top:1px solid var(--rule); margin:16pt 0; }
sub{ color:var(--soft); font-size:8.5pt; }
.cover{ background:linear-gradient(135deg,var(--deep),#12002b 62%,#000);
        color:#fff; margin:-16mm -15mm 16pt; padding:24mm 15mm 11mm; }
.cover h1{ color:#fff; font-size:34pt; margin-bottom:6pt; }
.cover .tag{ color:#d9b3ff; font-size:16pt; font-weight:600; margin:0 0 12pt; }
.cover p{ color:#c9c6d4; font-size:10.5pt; max-width:150mm; }
.cover .meta{ margin-top:16pt; padding-top:10pt; border-top:1px solid #4a2a6b;
              color:#a99cbb; font-size:9pt; }
.kpis{ display:flex; gap:8pt; margin:12pt 0; }
.kpi{ flex:1; border:1px solid var(--rule); border-top:3px solid var(--purple);
      border-radius:5px; padding:8pt 10pt; }
.kpi .k{ font-size:7.6pt; text-transform:uppercase; letter-spacing:.06em;
         color:var(--soft); }
.kpi .v{ font-size:17pt; font-weight:700; color:var(--deep); line-height:1.2;
         margin-top:2pt; }
.kpi .s{ font-size:8pt; color:var(--mid); margin-top:1pt; }
.tag-pill{ display:inline-block; font-size:7.4pt; font-weight:700; letter-spacing:.05em;
      padding:1.5pt 5pt; border-radius:3px; text-transform:uppercase; }
.MEASURED{ background:#e6f6ed; color:var(--ok); }
.MODELLED{ background:#fdf3e3; color:var(--warn); }
.ASSUMED{ background:#f0f1f4; color:var(--soft); }
.caption{ font-size:8.4pt; color:var(--soft); text-align:center; margin:0 0 12pt; }
.pagebreak{ break-before:page; }
.note{ background:var(--wash); border:1px solid #ece3f7; border-radius:5px;
       padding:9pt 12pt; margin:11pt 0; font-size:9.4pt; break-inside:avoid; }
.note b{ color:var(--deep); }
"""


def _embed_images(html: str, base: pathlib.Path) -> str:
    """Inline every local image so the PDF is a single self-contained file."""
    def repl(m):
        src = m.group(1)
        if src.startswith(("http:", "https:", "data:")):
            return m.group(0)
        path = (base / src).resolve()
        if not path.exists():
            return m.group(0)
        mime = mimetypes.guess_type(str(path))[0] or "image/png"
        b64 = base64.b64encode(path.read_bytes()).decode()
        return m.group(0).replace(src, f"data:{mime};base64,{b64}")
    return re.sub(r'src="([^"]+)"', repl, html)


def render(html_body: str, out_pdf: pathlib.Path, base: pathlib.Path) -> None:
    doc = (f"<!doctype html><html><head><meta charset='utf-8'>"
           f"<style>{CSS}</style></head><body>{_embed_images(html_body, base)}"
           f"</body></html>")
    tmp = out_pdf.with_suffix(".tmp.html")
    tmp.write_text(doc, encoding="utf-8")
    chrome = next((c for c in CHROME_CANDIDATES if c and pathlib.Path(c).exists()), None)
    if not chrome:
        sys.exit("No Chrome/Chromium found for PDF rendering.")
    subprocess.run(
        [chrome, "--headless", "--disable-gpu", "--no-pdf-header-footer",
         f"--print-to-pdf={out_pdf}", tmp.as_uri()],
        capture_output=True, timeout=180, check=False)
    tmp.unlink(missing_ok=True)
    size = out_pdf.stat().st_size / 1e6 if out_pdf.exists() else 0
    print(f"  {out_pdf.name:32s} {size:5.2f} MB")


def build_readme() -> None:
    md = (ROOT / "README.md").read_text(encoding="utf-8")
    body = markdown.markdown(
        md, extensions=["tables", "fenced_code", "sane_lists", "attr_list"])
    # Drop the markdown front matter entirely -- title, tagline, standfirst and
    # byline all reappear in the cover block below, and leaving them in the body
    # printed the whole opening twice on page one.
    parts = body.split("<hr />", 1)
    if len(parts) == 2:
        body = parts[1]
    cover = """
    <div class="cover">
      <h1>SmartFactory Twin</h1>
      <p class="tag">Don't wait for the defect.</p>
      <p>A flow-level digital twin for a vehicle assembly line that detects a
      station going bad while it is still going bad, and scopes containment to
      the vehicles actually affected.</p>
      <div class="meta">Team PeakBusters &nbsp;·&nbsp; Accenture Innovation
      Challenge 2026 &nbsp;·&nbsp; Problem Track 4, Round 2 &nbsp;·&nbsp;
      Technical README<br><span style="color:#d9b3ff">https://github.com/avinas29/smartfactory-twin</span></div>
    </div>"""
    render(cover + body, OUT / "SmartFactory-Twin-README.pdf", ROOT)


def build_proposal() -> None:
    src = DOCS / "BUSINESS-PROPOSAL.html"
    render(src.read_text(encoding="utf-8"), OUT / "SmartFactory-Twin-Business-Proposal.pdf", DOCS)


if __name__ == "__main__":
    print("Building submission PDFs...")
    build_readme()
    if (DOCS / "BUSINESS-PROPOSAL.html").exists():
        build_proposal()
