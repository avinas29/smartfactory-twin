# Limitations, and the challenges we expect

Written before anyone asked, because the fastest way to lose a technical audience
is to have them find something you did not mention.

---

## Answered by measurement

### "This is not really a digital twin, it's a dashboard with alerts."

Fair challenge, and the distinction is real. A dashboard reports state. This
holds three things a dashboard does not:

1. **Unit genealogy** — for every vehicle, which stations it passed and *what
   condition each station was in at that moment*. This is what makes the
   traceback possible at all; you cannot reconstruct it from a state display.
2. **A flow model that is rolled forward** — station capacities are projected
   two hours ahead to find which station becomes the constraint and when. The
   forecast is validated against what actually happened (36% of handover calls
   verified, 95 min median lead), not just displayed.
3. **Counterfactual scoping** — the containment list answers "which units are
   affected if this station has been bad since 07:12", which is a query against
   modelled state, not a filter over readings.

What it is **not**: no CAD geometry, no robot kinematics, no physics rendering.
That was scoped out in Round 1 deliberately. It is a *flow and quality* twin.

### "Your synthetic data makes the prediction too easy."

The evidence points the other way. Test ROC-AUC is **0.63–0.66** with a bootstrap
95% interval of roughly ±0.03 — if the data were easy this would be 0.95. About a
third of defects are drawn from causes with no upstream signature at all, and
roughly half of downstream failures originate *after* the decision point. Both
are deliberate ceilings.

The stronger version of the challenge is fair though: **we chose the causal
structure, so the model is looking for something we know is there.** True. What
the prototype demonstrates is that the *pipeline* recovers a known structure
without leaking, at a realistic effect size. Whether a real line's structure is
recoverable is a Phase-1 shadow-mode question, not something this can settle.

### "AUC 0.66 is not impressive."

Three responses, all measured:

- **Null model:** same family, same features, same split, training labels
  shuffled → ROC-AUC **0.40–0.44**. The pipeline finds nothing when there is
  nothing, so 0.66 is signal rather than bookkeeping.
- **The ceiling is structural.** On the reachable population — failures whose
  cause is upstream of the decision point, the only ones any body-exit model can
  see — ROC-AUC is **0.74–0.78** with PR lift ×2.4–2.7 over base rate.
- **AUC is not the operational metric.** The line has fixed inspection capacity,
  so what matters is precision at that capacity, reported with a full
  capacity curve.

And the honest concession: **the unit-level classifier is the weakest of the
three predictive components.** The strongest evidence in this prototype is
station-level detection (28 min warning at 8.4 alerts/shift across 42 stations)
and traceback with containment. We would not lead a pitch with the classifier.

### "How do you know the root cause is not just correlation?"

We do not know it from the contrast alone — so we measured it against the
simulator's recorded true origin, which the twin never sees:

| Reported confidence | Windows | Top-1 correct | Top-3 correct |
|---|---|---|---|
| HIGH | 32 | **68.8%** | 84.4% |
| MEDIUM | 15 | 46.7% | 86.7% |
| LOW | 32 | 21.9% | 71.9% |
| All | 79 | 45.6% | 79.7% |
| Random upstream station | — | 5.1% | — |

The point is not the 45.6%. It is that accuracy **tracks the confidence the twin
reported at the time**. An attribution engine that always names a station will
eventually send a crew to a healthy one; this one says "no dominant suspect" when
the evidence does not separate, and that label is earned rather than decorative.

It is still a difference-in-means with an FMEA prior, not causal inference. It is
presented to an engineer as evidence to check.

### "How do you prevent future information leaking into the features?"

Structurally, not by inspection:

- The decision point (station 14) puts **every feature at or before it and every
  label after it**. There is no window where a feature could see its own outcome.
- Control limits are fitted on days 0–2 and frozen; a test asserts that
  truncating all later data does not move a single limit.
- Temporal split, calibration on a window the classifier never trained on.
- Ground truth is named `oracle_*`, **stripped from the file the dashboard
  loads**, and a test fails if any module outside the generator references it.

One real leak was found and fixed during review: the virtual sensor took the
*next* station's reading for the same unit, which is ~50 seconds ahead (an hour
across the painted-body store). It is now a backward time join. Cost: 0.0001 AUC.

### "What happens when sensors are missing?"

Measured rather than asserted. Three coverage tiers with 14% of stations having
no process telemetry at all, plus random dropouts and multi-hour outages.

- Dark stations are still detected — but **later** (82 min vs 28 min on a
  comparable instrumented fault), which is the honest cost.
- Virtual sensors recover the missing-channel signal at **0.94 ROC-AUC on
  held-out stations**, and that validated score becomes the blending weight: a
  mapping that did not generalise cannot raise an alarm.
- Data confidence is discounted everywhere a dark station appears, and a
  sensor-poor station **can never produce an IMMEDIATE recommendation** — its
  confidence (0.43) is below the bar. It gets MONITOR plus an instrumentation
  case with a payback estimate.

---

## Acknowledged limitations

### The business case rests on a thin count

The largest single line — warranty exposure avoided on intercepted escapes —
rests on **11 events in a 4-day test window**. The 95% interval on the
interception rate is 3.3%–10.0%, which moves the quality benefit between roughly
$0.88M and $2.29M against a $1.40M point estimate. The interval is shown in the
UI. A pilot should measure this before the number is committed to anywhere.

Cost constants are ASSUMED and carry no evidence from this prototype.

### The forecast sample is small

36% hit rate on 11 verified calls. The direction is right and the lead time (95
min median) is useful, but 11 is not enough to quote a hit rate with confidence.

### Model selection is not statistically resolvable here

All three families land within the bootstrap interval of each other
(0.663 / 0.667 / 0.678 against a CI of [0.62, 0.68]). The selection rule runs on
validation so the test window is read once, but we do not claim the chosen family
is genuinely better — only that the choice was made without touching test.

### Not built

- MES/PLC/OPC-UA connectors — specified in `docs/INTEGRATION.md`, not implemented
- Multi-plant deployment, model registry, retraining schedule
- Authentication, RBAC, audit trail for the decision ledger (currently in-memory)
- Incremental/streaming computation — the app replays a recorded window; a live
  deployment would compute episodes incrementally rather than filtering a table

### Simulated

The plant. Telemetry, defect creation and gate detection come from a generator
with a latent causal model. Everything downstream — SPC, virtual sensors,
features, model, forecast, traceback, recommendations, economics — is
implementation that would run unchanged against a real MES feed.
