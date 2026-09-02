# Submission — repository structure and checklist

Everything the Round 2 submission needs, and how to regenerate any of it.

---

## 1 · The five required deliverables

| # | Requirement | File | Status |
|---|---|---|---|
| 1 | Public GitHub link | **https://github.com/avinas29/smartfactory-twin** | live |
| 2 | Prototype video (.mp4/.mov) | script: `docs/VIDEO.md` / `SmartFactory-Twin-Video-Script.pdf` (5:00, 11 shots) | **to record** |
| 3 | README as PDF, ≤ 20 MB | `docs/SmartFactory-Twin-README.pdf` — **1.2 MB** | ready |
| 4 | Business Proposal PDF | `docs/SmartFactory-Twin-Business-Proposal.pdf` — 1.5 MB, 13 pp | ready |
| 5 | Business Proposal PPTX | `docs/SmartFactory-Twin-Business-Proposal.pptx` — 1.1 MB, 15 slides | ready |

---

## 2 · Repository structure

```
smartfactory-twin/
├── README.md                     ← the GitHub landing page; source for the README PDF
├── requirements.txt
├── Makefile                      install · build · run · test
├── run.py                        one command: build if needed, then serve
├── .gitignore                    excludes data/ and artifacts/
│
├── twin/                         the engine — everything below is real implementation
│   ├── config.py                 line layout, sensor tiers, gates, economics constants
│   ├── generate.py               the synthetic plant (the only simulated component)
│   ├── spc.py                    frozen-baseline control charts, drift episodes
│   ├── virtual_sensor.py         thin → rich evidence transfer for dark stations
│   ├── features.py               per-unit features at the decision point
│   ├── model.py                  training, calibration, model selection, metrics
│   ├── flow.py                   queueing roll-forward, bottleneck forecast
│   ├── tracing.py                traceback, containment, accuracy validation
│   ├── recommend.py              four-class recommendation engine
│   ├── economics.py              business case: MEASURED / MODELLED / ASSUMED
│   └── pipeline.py               build everything, write artifacts, print the report
│
├── app/
│   ├── main.py                   FastAPI — replays the record against a client clock
│   └── static/                   index.html · app.css · app.js (no build step, no CDN)
│
├── tests/
│   └── test_twin.py              21 tests: leakage guarantees + named regressions
│
├── docs/
│   ├── INTEGRATION.md            what the twin reads; shadow-mode validation plan
│   ├── LIMITATIONS.md            expected challenges, answered or acknowledged
│   ├── VIDEO.md                  5-minute script, narration, 11 shots with deep links
│   ├── SUBMISSION.md             this file
│   ├── FACTS.json                canonical figures, written by the pipeline
│   ├── assets/                   six screenshots used across all documents
│   ├── capture.py                regenerate the screenshots
│   ├── build_proposal.py         proposal HTML from FACTS.json
│   ├── build_docs.py             README + proposal → PDF
│   ├── build_deck.js             the PPTX
│   ├── SmartFactory-Twin-README.pdf
│   ├── SmartFactory-Twin-Business-Proposal.pdf
│   └── SmartFactory-Twin-Business-Proposal.pptx
│
├── data/                         gitignored — regenerates from the seed
└── artifacts/                    gitignored — models + validation.json
```

**`data/` and `artifacts/` are deliberately not committed.** They are ~90 MB and
regenerate deterministically in about 100 seconds from a fixed seed. A judge
cloning the repo runs one command and gets byte-identical results.

---

## 3 · Regenerating everything

```bash
python -m twin.pipeline          # data + models + artifacts/validation.json  (~100 s)
python -m pytest tests -q        # 21 tests
python run.py --no-browser &     # serve on :8077
python docs/capture.py           # screenshots  -> docs/assets/
python docs/build_proposal.py    # proposal HTML from FACTS.json
python docs/build_docs.py        # all three PDFs (README, proposal, video script)
node docs/build_deck.js          # the PPTX
```

Every document reads its figures from `docs/FACTS.json`, which the pipeline
writes. Change the model and re-run — the README, the proposal and the deck all
re-state themselves. Nothing is typed in by hand.

---

## 4 · Pre-submission checklist

### Repository
- [x] `git init && git add . && git commit` — `data/` and `artifacts/` excluded
- [x] Pushed to a **public** GitHub repository
- [ ] Clone it fresh into a clean directory and run `pip install -r requirements.txt && python run.py` — confirm the dashboard comes up
- [x] `python -m pytest tests -q` → **21 passed**
- [x] Deck closing slide carries the live URL — `github.com/avinas29/smartfactory-twin`
- [ ] README renders correctly on GitHub (check the four inline images resolve)

### Video
- [ ] Recorded at 1080p+, browser window only, no other tabs visible
- [ ] Length ≤ 5:30 (target 5:00)
- [ ] Cache warmed before recording — no visible loading states
- [ ] Traceback shot (2:10–3:05) and sensor-poor shot (3:05–3:55) are intact and unhurried
- [ ] Audio levels consistent; the full beat of silence before the 84% reveal is intact
- [ ] Exported as `.mp4` or `.mov`
- [ ] Watched end to end once, muted, to check nothing on screen looks broken

### Documents
- [ ] README PDF opens, 7 pages, under 20 MB ✔ (1.2 MB)
- [ ] Proposal PDF opens, 13 pages, images render
- [ ] PPTX opens **in PowerPoint** (not just a preview) — check slides 8 and 13
- [ ] Figures in all three agree with `artifacts/validation.json`
- [ ] Team names and college details correct on the title slide

### Claims audit — read each document once looking only for these
- [ ] No "predicts root cause" → must read "ranked attribution" / "the evidence points at"
- [ ] No "prevents defects" or "guarantees" → must read "catches earlier" / "scopes containment"
- [ ] Every ROI figure carries MEASURED, MODELLED or ASSUMED
- [ ] The weak numbers are still present and not quietly softened: defect-model
      ROC-AUC 0.65, the 11-call forecast sample, the 12-escape ROI interval
- [ ] The implemented / simulated / proposed table appears in README, proposal and deck

---

## 5 · The three sentences to have ready

Judges will ask. These are the answers, and each is backed by a number in the
submission.

**"Is this really a digital twin, or a dashboard?"**
> It keeps unit genealogy — for every car, which stations it passed and what
> condition each was in at that moment — and rolls the flow model forward two
> hours. That's what makes the traceback and the containment list possible; you
> cannot reconstruct either from a state display.

**"How do you know the attribution isn't just correlation?"**
> We don't know it from the contrast alone, so we measured it against the
> simulator's recorded true origin, which the twin never sees. Sixty-nine percent
> top-one when it reports high confidence, twenty-two percent when it reports
> low, five percent for a random guess. The confidence label is earned.

**"AUC 0.65 isn't very impressive."**
> Agreed, and it's the weakest of our three components — we don't lead with it.
> The null model with shuffled labels lands at 0.40, so the signal is real; on
> the half of failures a body-exit model can actually reach it's 0.77 with 2.5×
> lift. The strong evidence in this submission is detection latency and
> attribution accuracy, not the per-car classifier.
