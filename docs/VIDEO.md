# Prototype video — 5-minute script

**Target 5:00.** Hard cap 5:30.
**Story: detection and containment.** Not "we built an ML model."

The spine is one sentence: **a station goes bad, the twin says so while it is
still going bad, and then tells you exactly which cars went through it.**

---

## 0 · Before you record

Start the server and leave it running:

```bash
cd smartfactory-twin && python run.py --no-browser
```

Wait for `SmartFactory Twin -> http://localhost:8077`.

| Setting | Value |
|---|---|
| Browser | Chrome, **new window**, no other tabs, no bookmarks bar |
| Zoom | 100% (`Cmd-0`) |
| Window | 1600 × 1000 or larger; full-screen the browser (`Cmd-Ctrl-F`) |
| Recording | 1080p or higher, 30 fps, **capture the browser window only** |
| Audio | Record narration separately if you can — it is far cleaner than live |
| Speed control | Leave on **5 min/s** throughout. Never press play on camera. |

**Warm the cache.** Paste all eleven deep links below once, in order, before you
record. Then reload and start. Nothing should ever render slowly on camera.

**Use the deep links, not the bookmark chips.** Each URL lands on the exact frame
every time. Clicking chips is fine in rehearsal; on the take, paste the URL.

**Word count:** ~700 spoken words over 5:00 ≈ 140 wpm. That is a calm,
deliberate pace with room to breathe. If you are rushing, you have drifted off
script.

---

## 1 · Shot list

| # | Time | Length | Shot | Deep link |
|---|---|---|---|---|
| 1 | 0:00 | 0:22 | Baseline — what this is | `localhost:8077/?t=1774766250&view=line` |
| 2 | 0:22 | 0:33 | Sensor coverage — the dark stations | *same URL, no reload* |
| 3 | 0:55 | 0:25 | 07:12 drift begins, nothing showing | `localhost:8077/?t=1774768332&view=line&station=BODY-08` |
| 4 | 1:20 | 0:25 | 07:43 flagged — MONITOR | `localhost:8077/?t=1774770222&view=line` |
| 5 | 1:45 | 0:25 | 07:58 escalated — IMMEDIATE | `localhost:8077/?t=1774771122&view=line&station=BODY-08` |
| **6** | **2:10** | **0:55** | **12:10 traceback + containment** | `localhost:8077/?t=1774786212&view=trace&gate=27` |
| **7** | **3:05** | **0:50** | **Sensor-poor station stays MONITOR** | `localhost:8077/?t=1774797462&view=line&station=BODY-14` |
| 8 | 3:55 | 0:15 | Bottleneck forecast | `localhost:8077/?t=1774776480&view=line` |
| 9 | 4:10 | 0:15 | Plant view — the manager | `localhost:8077/?t=1774786212&view=plant` |
| 10 | 4:25 | 0:22 | Validation — the honest numbers | `localhost:8077/?t=1774786212&view=validation` |
| 11 | 4:47 | 0:13 | Business case + close | `localhost:8077/?t=1774786212&view=business` |

Shots **6 and 7** are the differentiators. Everything else is setup or support.

---

## 2 · Screen-by-screen, with exact narration

Read the **bold** words a little harder. Everything in `[brackets]` is a stage
direction — do not read it aloud.

---

### Shot 1 — Baseline · 0:00 → 0:22

`localhost:8077/?t=1774766250&view=line`

> *[Wide on the line view. Hold completely still for three seconds before you speak.]*

> "This is a vehicle assembly line — **forty-two stations**, across body
> construction, paint, and final assembly.
>
> *[Move the cursor slowly along the body shop row, left to right.]*
>
> And this is a digital twin of it, replaying a recorded production day. Every
> tile is a station, scored against **its own qualified baseline**. Green means
> it is behaving the way it was commissioned to behave."

---

### Shot 2 — The dark stations · 0:22 → 0:55

*Same screen — do not reload.*

> *[Hover over station 12, then 14, then 18 — the dashed tiles. Let the tooltip show.]*

> "Now look at the dashed tiles. **These stations have no process sensors at
> all.** No vibration. No torque telemetry. On this line that is six stations out
> of forty-two — and in a real brownfield plant, those are usually the manual
> ones, which is exactly where errors get made.
>
> *[Point at the small dots on the right edge of a couple of tiles.]*
>
> Most digital twins assume full instrumentation. This one does not. It reads
> what every station already emits — **part-scan timestamps and the conveyor
> handshake** — which exist even on nineteen-nineties equipment. No new sensors.
> Nothing written back to the PLC."

---

### Shot 3 — Drift begins · 0:55 → 1:20

`localhost:8077/?t=1774768332&view=line&station=BODY-08`

> *[BODY-08 detail panel is open. Point at the clock first.]*

> "07:12. A nutrunner spindle at **station eight** has just started to wear.
>
> *[Point at the station tile — still green — then at the vibration trace below.]*
>
> And nothing is showing. Mean torque is still inside the PLC acceptance window
> — it is only the **scatter** that is growing. Every limit check on this line is
> green right now, and will stay green.
>
> On a conventional line, the first thing anybody learns about this is a rejected
> car, **ninety minutes from now**."

---

### Shot 4 — Flagged · 1:20 → 1:45

`localhost:8077/?t=1774770222&view=line`

> *[Right-hand rail. Point at the BODY-08 card.]*

> "07:43. **Twenty-eight minutes in**, the twin raises BODY-08.
>
> *[Point directly at the MONITOR tag.]*
>
> But look carefully at *what* it raises. **Monitor** — not stop. The evidence is
> real, and it is not yet strong enough to justify stopping work at that station.
>
> That distinction is the entire product, and I will come back to it."

---

### Shot 5 — Escalated · 1:45 → 2:10

`localhost:8077/?t=1774771122&view=line&station=BODY-08`

> *[BODY-08 is now the top IMMEDIATE card. Point at the red tag.]*

> "Fifteen minutes later it escalates to **immediate**. Nothing was added but
> more evidence.
>
> *[Point at the vibration chart in the detail panel, then the shaded alarm band.]*
>
> Eight sigma above baseline, led by **vibration at six-point-two**. And the
> recommendation is not a risk percentage — it names the station, the evidence,
> the action, and where this fault will surface if it is ignored: **the torque
> audit at station twenty-seven**.
>
> *[Point at Accept / Dismiss.]*
>
> A human decides. Every decision is logged."

---

### Shot 6 — Traceback and containment · 2:10 → 3:05 ← **the money shot**

`localhost:8077/?t=1774786212&view=trace&gate=27`

> *[Traceback view. Let it sit for a full two seconds in silence before speaking.]*

> "Now jump forward to **12:10**. The torque audit at station twenty-seven has
> started rejecting bodies — the cars that were built while station eight was
> drifting.
>
> *[Point at the verdict bar at the top.]*
>
> Fourteen rejects.
>
> *[PAUSE. One full beat. Then point at the BODY-08 bar.]*
>
> And the twin already knows where to look. **Eighty-four percent of the evidence
> points at BODY-08**, at **high** confidence.
>
> It gets there by contrasting what the rejected cars experienced upstream
> against the cars that **passed** the same gate — and against the same station a
> day earlier.
>
> *[Move to the containment panel on the right. Slow down here.]*
>
> And this is what actually matters on the floor. **Two hundred and thirty cars**
> went through that station while it was out of control.
>
> *[Point at the location breakdown.]*
>
> **Eighty-six of them are still inside the plant.** That is the inspection list.
> Not the shift's build. Not a batch. Those eighty-six cars.
>
> We call this **ranked attribution**, not root-cause prediction — it is evidence
> for an engineer to go and check."

---

### Shot 7 — The sensor-poor station · 3:05 → 3:55

`localhost:8077/?t=1774797462&view=line&station=BODY-14`

> *[BODY-14 detail open. Point at the "Sensor-poor station" banner.]*

> "Now the harder case, and the one I care most about.
>
> **BODY-14 is a manual station.** No vibration sensor. No torque telemetry. A
> torque wrench and a paper checklist.
>
> *[Point along the banner text as you read.]*
>
> It is drifting too — and the twin does catch it. From **cycle-time creep**, the
> **operator's checklist**, and a **virtual sensor** trained on this line's
> instrumented stations to infer what the missing channels would be saying. No
> new hardware.
>
> *[Point at the detection figure, then the confidence figure.]*
>
> But it takes **eighty-two minutes** instead of twenty-eight. And the confidence
> is **forty-three percent** — and the twin **says so**, right here on screen.
>
> *[Scroll the right rail down past the five IMMEDIATE cards to the MONITOR block.
> BODY-14 is seventh in the list. Rest on it.]*
>
> So it stays a **monitor** — below five instrumented stations that did earn an
> immediate, even though this one is drifting harder than most of them. A
> sensor-poor station cannot raise an immediate **quality** action here, because
> its condition is inferred, and inference does not carry the cost of stopping
> work.
>
> *[Scroll a little further to the purple INSTRUMENTATION card.]*
>
> Instead it gets a watch item — and a **costed case for instrumenting it**.
>
> *[Beat.]*
>
> **Strong evidence, act. Weak evidence, don't overreact.** That asymmetry is the
> difference between a tool a supervisor keeps using and one they learn to
> ignore."

---

### Shot 8 — Bottleneck forecast · 3:55 → 4:10

`localhost:8077/?t=1774776480&view=line`

> *[Point at the Line Constraint panel on the right.]*

> "The twin also runs the line forward. Here it is calling the constraint
> **twenty minutes before it moves** — station thirty-one takes over from
> forty-two.
>
> On this particular day the line stays above takt, so the throughput at stake is
> small. I am showing you the mechanism, not a headline."

---

### Shot 9 — Plant view · 4:10 → 4:25

`localhost:8077/?t=1774786212&view=plant`

> *[Point at the detection-latency table.]*

> "Different people need different views. The plant manager gets alert load,
> problem stations, and this — **detection latency split by sensor coverage**.
>
> Instrumented stations, twenty-eight and fifty minutes. The sensor-poor one,
> eighty-two. We do not claim parity, we report the gap."

---

### Shot 10 — Validation · 4:25 → 4:47

`localhost:8077/?t=1774786212&view=validation`

> *[Scroll to the traceback accuracy panel.]*

> "All of this is measured on a **held-out window** the models never trained on.
>
> *[Point at the confidence-stratified table.]*
>
> Attribution: **sixty-nine percent** top-one when the twin reports high
> confidence, **twenty-two percent** when it reports low, against **five percent**
> for a random guess. Accuracy tracks the confidence it reported — that is what
> makes the label worth anything.
>
> *[Point at the defect-risk table.]*
>
> And where we are weak, we say so. The per-car risk model is modest, and it is
> on this screen at full strength, next to a shuffled-label null model."

---

### Shot 11 — Business case and close · 4:47 → 5:00

`localhost:8077/?t=1774786212&view=business`

> *[Point at the three KPI tiles, then sweep down the arithmetic table.]*

> "One-point-eight million a year on a single line — and **every line of that
> arithmetic is on screen**, including the conservatism haircuts and the interval
> on our weakest number.
>
> *[Sit still on the KPI row for the final line. Do not move the mouse.]*
>
> Forty-two stations. No new sensors. Nothing written back to the PLC.
>
> **Don't wait for the defect.**"

---

## 3 · Timing discipline

| Act | Shots | Budget | Cumulative |
|---|---|---|---|
| Set up the problem | 1–2 | 0:55 | 0:55 |
| Detection | 3–5 | 1:15 | 2:10 |
| **Containment** | **6** | **0:55** | 3:05 |
| **Trust** | **7** | **0:50** | 3:55 |
| Breadth | 8–9 | 0:30 | 4:25 |
| Evidence + close | 10–11 | 0:35 | 5:00 |

**If you overrun, cut in this order:** shot 8 entirely (−15s), then shot 9
entirely (−15s), then the second half of shot 2 (−15s), then shot 10's last
sentence (−8s).

**Never cut shots 6 or 7.** They are the two things this submission has that a
generic monitoring dashboard does not.

---

## 4 · Delivery notes

- **Slow down on numbers.** "Two hundred and thirty" lands; "230" does not.
- **The pause in shot 6 is the most important half-second in the video.** After
  "Fourteen rejects", stop completely. Let it hang. Then "And the twin already
  knows where to look." That is the turn of the whole piece.
- **Do not say "machine learning", "model", "AUC" or "algorithm" before 4:25.**
  The first four minutes are about a plant problem, not a technique.
- **Never say "predicts the root cause."** Say *"points at"*, *"ranks"*, or *"the
  evidence points at"*.
- **Never say "prevents defects"** or *"guarantees"*. Say *"catches it earlier"*
  or *"scopes the containment"*.
- **Never say "real-time" about the replay.** Say *"replaying a recorded
  production day"* — you say this once in shot 1 and it covers you for the rest.
- Move the mouse slowly and deliberately. Park the cursor off to the side when
  you are not pointing at anything. A drifting cursor reads as nervousness.
- Let each screen breathe for a beat after it loads before you start talking.

---

## 5 · If something goes wrong on the day

| Problem | Fix |
|---|---|
| A panel renders slowly | You skipped the cache warm-up. Reload, paste all eleven links once, start again. |
| `localhost:8077` refuses to connect | The server is not running. `python run.py --no-browser` from the repo root. |
| Server starts then exits | Artifacts missing. `python -m twin.pipeline` (~100 s), then start again. |
| Port 8077 already in use | `python run.py --port 8099 --no-browser` and change the port in every URL. |
| Numbers differ from this script | You rebuilt with a different seed. Re-read `artifacts/validation.json` and adjust, or `git checkout` the committed docs. |
| A deep link does not land | The app clamps `t` to the recorded day — check you copied the full URL including `&view=`. |
| You need a still instead of a take | `python docs/capture.py` regenerates every screenshot into `docs/assets/`. |

---

## 6 · One-line summary to have ready

If a judge asks you to describe it in a sentence:

> "It watches every station against its own qualified normal, tells you which one
> went bad while it is still going bad, and then hands you the exact list of cars
> that went through it — including the ones still inside the plant."
