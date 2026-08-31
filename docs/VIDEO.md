# Prototype video — script, narration and recording plan

**Target length: 3:00.** Hard cap 3:30.
**Story: detection + containment.** Not "we built an ML model."

The spine is one sentence: **a station goes bad, the twin says so while it is
still going bad, and then tells you exactly which cars went through it.**

---

## 0 · Before you record

```bash
cd smartfactory-twin
python run.py --no-browser
```

Wait for `SmartFactory Twin -> http://localhost:8077`, then:

| Setting | Value |
|---|---|
| Browser | Chrome, **new window**, no other tabs, no bookmarks bar |
| Zoom | 100% (`Cmd-0`) |
| Window | 1600 × 1000 or larger; full-screen the browser (`Cmd-Ctrl-F`) |
| Recording | 1080p or higher, 30 fps, **capture the browser window only** |
| Audio | Record narration separately if you can — cleaner than live |
| Speed control | Leave on **5 min/s** throughout |

**Warm the cache first.** Click through every bookmark once before recording so
no panel renders slowly on camera. Then reload.

**Every shot below has a deep link.** Paste the URL instead of hunting for the
moment — it lands on the exact frame every time. If you prefer clicking, the
bookmark chip name is given too.

---

## 1 · Shot list

| # | Time | Shot | Deep link (paste into the address bar) |
|---|---|---|---|
| 1 | 0:00–0:18 | Baseline line view | `localhost:8077/?t=1774766250&view=line` |
| 2 | 0:18–0:34 | Drift begins — nothing showing | `localhost:8077/?t=1774768332&view=line&station=BODY-08` |
| 3 | 0:34–0:52 | Flagged: MONITOR | `localhost:8077/?t=1774770222&view=line` |
| 4 | 0:52–1:16 | Escalated: IMMEDIATE + station detail | `localhost:8077/?t=1774771122&view=line&station=BODY-08` |
| 5 | 1:16–1:52 | Traceback + containment | `localhost:8077/?t=1774786212&view=trace&gate=27` |
| 6 | 1:52–2:22 | Sensor-poor station stays MONITOR | `localhost:8077/?t=1774797462&view=line&station=BODY-14` |
| 7 | 2:22–2:42 | Validation — the honest numbers | `localhost:8077/?t=1774786212&view=validation` |
| 8 | 2:42–3:00 | Business case + close | `localhost:8077/?t=1774786212&view=business` |

---

## 2 · Screen-by-screen, with exact narration

Read the **bold** words a little harder. Everything in `[brackets]` is a stage
direction, not spoken.

---

### Shot 1 — Baseline · 0:00–0:18

`localhost:8077/?t=1774766250&view=line`

> *[Wide on the line view. Don't touch anything for the first three seconds.]*

**"This is a vehicle assembly line. Forty-two stations — body construction, paint,
final assembly — and this is a digital twin of it, replaying a real production
day.**

*[Slowly move the cursor along the body shop row, left to right.]*

**Each tile is a station, scored against its own qualified baseline. Green is
nominal. And the dashed tiles — these ones — have no process sensors at all.
Fourteen percent of this line is dark. We'll come back to that."**

---

### Shot 2 — Drift begins · 0:18–0:34

`localhost:8077/?t=1774768332&view=line&station=BODY-08`

> *[Station BODY-08 detail panel is open. Point at the vibration trace.]*

**"07:12. A nutrunner spindle at station eight has just started to wear.**

*[Point at the clock, then at the tile — still green.]*

**Nothing is showing. Mean torque is still inside the PLC acceptance window —
only the *scatter* is growing. Every limit check on this line is green, and will
stay green.**

**On a conventional line, the first thing anyone learns about this is a rejected
car, ninety minutes from now."**

---

### Shot 3 — Flagged · 0:34–0:52

`localhost:8077/?t=1774770222&view=line`

> *[Right rail. Point at the BODY-08 card.]*

**"07:43 — twenty-eight minutes in. The twin raises BODY-08.**

*[Point at the MONITOR tag.]*

**But look at what it raises: **monitor**, not stop. The evidence is real and it
isn't strong enough yet to justify stopping work. That distinction is the whole
product."**

---

### Shot 4 — Escalated · 0:52–1:16

`localhost:8077/?t=1774771122&view=line&station=BODY-08`

> *[The BODY-08 card is now the top IMMEDIATE. Point at it.]*

**"Fifteen minutes later, it escalates to **immediate**. Nothing was added but
more evidence.**

*[Scroll to the station detail. Point at the vibration chart and the shaded alarm band.]*

**Eight sigma above baseline, led by vibration at six-point-two. And the
recommendation isn't a risk percentage — it names the station, the evidence, the
action, and where this fault will surface if we ignore it: the torque audit at
station twenty-seven.**

*[Point at Accept / Dismiss.]*

**A human decides. Every decision is logged — which is how the false-alarm rate
becomes something we measure rather than something we claim."**

---

### Shot 5 — Traceback and containment · 1:16–1:52 ← **the money shot**

`localhost:8077/?t=1774786212&view=trace&gate=27`

> *[Traceback view. Let it sit for two seconds before speaking.]*

**"Now jump forward. 12:10. The torque audit at station twenty-seven has started
rejecting bodies — the cars built while station eight was drifting.**

*[Point at the verdict bar.]*

**Fourteen rejects. And the twin already knows where to look.**

*[Point at the BODY-08 bar.]*

**Eighty-four percent of the evidence points at BODY-08, at **high** confidence.
It gets there by contrasting what the rejected cars experienced upstream against
the cars that passed the same gate — and against the same station yesterday.**

*[Move to the containment panel on the right.]*

**And this is the part that matters on the floor. **Two hundred and thirty-eight
cars** went through that station while it was out of control. **Eighty-six are
still inside the plant.** That's the inspection list. Not the shift's build —
those eighty-six cars.**

**We call this ranked attribution, not root-cause prediction. It's evidence for
an engineer to check."**

---

### Shot 6 — The sensor-poor station · 1:52–2:22

`localhost:8077/?t=1774797462&view=line&station=BODY-14`

> *[BODY-14 detail open. Point at the "Sensor-poor station" banner.]*

**"Now the harder case. BODY-14 is a manual station. No vibration sensor. No
torque telemetry.**

*[Point at the banner text.]*

**It's drifting too — and the twin catches it, from cycle-time creep, the
operator's checklist, and a virtual sensor trained on the line's *instrumented*
stations. No new hardware.**

*[Point at the confidence figure.]*

**But it takes eighty-two minutes instead of twenty-eight, and confidence is
forty-three percent — and the twin says so.**

*[Point at the right rail — BODY-14 is a MONITOR card.]*

**So it stays a **monitor**. A sensor-poor station is structurally barred from
telling you to stop work, because its evidence can't carry that cost. It gets a
watch item and a business case for instrumenting it.**

**Strong evidence, act. Weak evidence, don't overreact."**

---

### Shot 7 — Validation · 2:22–2:42

`localhost:8077/?t=1774786212&view=validation`

> *[Scroll to the traceback accuracy panel.]*

**"We measured all of this on a held-out window the models never trained on.**

*[Point at the confidence table.]*

**Attribution: sixty-nine percent top-one when the twin reports high confidence,
twenty-two percent when it reports low, against five percent for a random guess.
Accuracy tracks the confidence it reported — that's what makes the label worth
anything.**

*[Point at the defect-risk table.]*

**And where we're weak, we say so. The per-car risk model is modest —
point-six-five. Half of downstream failures start after the point where we score,
so no model can reach them. We report that ceiling instead of hiding it."**

---

### Shot 8 — Business case and close · 2:42–3:00

`localhost:8077/?t=1774786212&view=business`

> *[Business view. Point at the three KPI tiles, then at the arithmetic table.]*

**"One-point-eight million a year on a single line, with a three-and-a-half-month
payback — and every line of that arithmetic is on screen, including the
conservatism haircuts and the interval on our weakest number.**

*[Sit on the line view or the KPI row for the final line.]*

**Forty-two stations. No new sensors. Nothing written back to the PLC.**

**Don't wait for the defect."**

---

## 3 · Timing discipline

| Segment | Budget | Cumulative |
|---|---|---|
| Setup (shots 1–2) | 0:34 | 0:34 |
| Detection (shots 3–4) | 0:42 | 1:16 |
| **Traceback (shot 5)** | **0:36** | 1:52 |
| **Trust (shot 6)** | **0:30** | 2:22 |
| Validation (shot 7) | 0:20 | 2:42 |
| Business + close (shot 8) | 0:18 | 3:00 |

**If you overrun, cut from shots 1, 7 and 8 — never from 5 or 6.** Those two are
the differentiators. Shot 1 can lose its second half; shot 7 can drop the
defect-risk sentence; shot 8 can drop the arithmetic sentence.

---

## 4 · Delivery notes

- **Slow down on numbers.** "Two hundred and thirty-eight" lands; "238" doesn't.
- **Pause after "…and the twin already knows where to look."** One full beat
  before the 84% reveal. It's the turn of the whole video.
- **Don't say "machine learning", "model", "AUC" or "algorithm" before 2:22.**
  The first two minutes are about a plant problem, not a technique.
- **Never say "predicts the root cause."** Say *"points at"*, *"ranks"*, or
  *"the evidence points at"*.
- **Never say "prevents defects."** Say *"catches it earlier"* or *"scopes the
  containment"*.
- Mouse movement should be slow and deliberate. Park the cursor off to the side
  when you aren't pointing at anything.

## 5 · If something goes wrong on the day

| Problem | Fix |
|---|---|
| A panel renders slowly | You skipped the cache warm-up. Reload and click every bookmark once. |
| Numbers differ slightly from this script | You rebuilt with a different seed. Either re-read `artifacts/validation.json` and adjust, or `git checkout` the committed artifacts. |
| Port 8077 busy | `python run.py --port 8099` and adjust the URLs. |
| Deep link doesn't land | Check the server is running; the app clamps `t` to the recorded day. |
| You need a still instead of a take | `python docs/capture.py` regenerates every screenshot in `docs/assets/`. |
