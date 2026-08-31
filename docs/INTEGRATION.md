# Integration and deployment

Two questions a plant will ask before anything else: *what do you need from my
systems*, and *what are you going to change in them*. The answers are "four
tables" and "nothing".

---

## 1. What the twin reads

The twin is a **read-only consumer**. It requires no PLC logic change, no new
tag on the control network, and no modification to any interlock. Everything it
needs already exists in a plant that runs an MES.

| # | Source | Fields | Rate | Already exists because |
|---|---|---|---|---|
| 1 | **MES part-scan log** | `unit_id`, `station_id`, `arrive_ts`, `depart_ts` | per station-visit (~1/min/station) | traceability and takt reporting are mandatory |
| 2 | **PLC handshake / line-control historian** | `blocked_s`, `starved_s` per station-visit | same | the line controller already computes these to sequence conveyors |
| 3 | **Process telemetry, where fitted** | `torque`, `vibration`, `temperature` | per cycle or per second | already historised on modern cells |
| 4 | **Quality system** | `unit_id`, `gate_id`, `result`, `defect_mode`, `ts` | per gate event | rework and warranty already depend on it |
| 5 | **Operator checklist** (manual stations) | `unit_id`, `station_id`, `check_result` | per unit | already recorded on paper or tablet |
| 6 | **ERP / goods inward** | `lot_id`, incoming quality index | per lot | supplier quality management already tracks it |

Tables 1 and 2 are the important ones: **they exist at every station regardless
of age**, and they are what lets the twin score a station with no process
telemetry at all. That is the whole basis of the dark-station claim.

### Transport

OPC-UA subscription or a historian tap into a message bus (Kafka / MQTT),
landing in a time-series store. Where a legacy cell has no OPC-UA server, the MES
scan record alone is sufficient to place the station on the line view with
cycle-time and flow scoring — degraded, and labelled as degraded.

**Nothing is written back.** Recommendations surface in the twin's own UI and, if
the plant wants, as a work-order suggestion in the CMMS. No closed loop to the
line, by design — see §4.

---

## 2. Why nothing is written back to the PLC

A control system that can be commanded by a model is a control system whose
safety case has to be re-argued. The value here does not require it: every
recommendation the twin produces is an action a human already has the authority
to take — raise inspection frequency, pull a unit, move a floater, book a
maintenance slot. Advisory-only keeps the twin outside the safety envelope and
outside the change-control burden that would otherwise dominate the deployment
timeline.

If a plant later wants closed-loop actions, the natural first step is a
supervisory setpoint (inspection sampling rate at a gate), not a control action.

---

## 3. Instrumentation changes

Only during scheduled maintenance windows, and only where the twin has already
earned the case for them. The Business view ranks stations by *measured*
inference load — how often the twin had to infer a condition it could not
measure, weighted by production exposed each time — rather than by equipment age
or by whoever complains loudest. A retrofit is proposed with its own payback
estimate and can simply be declined; the twin keeps working, at lower confidence,
and says so.

---

## 4. Validating this in a real plant

The prototype's metrics come from a simulator. They are evidence that the method
is sound, not evidence that it works on any particular line. A pilot has to
establish the second thing, and it should be designed so that failure is visible.

### Phase 1 — Shadow mode (weeks 1–8)

The twin runs on live data and **shows nobody anything**. It records every alert,
risk score and attribution to a log. At the end:

- Do control limits fitted on the qualification window hold? (Alert rate stable,
  or drifting — which tells you the re-qualification cadence.)
- Of units the twin scored high-risk, how many were rejected downstream?
  Precision at capacity, measured on the plant's own defect rate.
- Is the reliability curve straight? Recalibrate if not.
- **Exit criterion:** PR-AUC lift over base rate ≥ 1.5 with a bootstrap interval
  clearing 1.0, and ≤ 15 actionable alerts per shift. If not met, stop.

### Phase 2 — Advisory on one zone (weeks 9–20)

Body shop only. Supervisors see alerts and accept/dismiss each one; the decision
ledger is the primary instrument. Attribution claims are checked against what
maintenance actually finds when they open the station up — the real-plant version
of the traceback accuracy table, and the only way to know whether the confidence
label transfers.

- **Exit criterion:** ≥ 50% of high-confidence attributions confirmed by
  maintenance, and a supervisor acceptance rate that is neither near 0% (nobody
  believes it) nor near 100% (nobody is reading it).

### Phase 3 — Full line, measured against a baseline (weeks 21–40)

Compare against the *same line's* prior-year performance on first-time-through
quality, escape rate and constraint-related throughput loss, with seasonality and
model-mix as covariates. A clean A/B is not available on a single line; the
honest design is an interrupted time series, and the business case should be
restated with the plant's own measured effect size, replacing every MODELLED
figure in `twin/economics.py`.

### What would falsify the approach

Stated in advance, because a pilot that cannot fail is not a test:

- Alert volume that cannot be brought under ~15/shift without losing the faults
- Attribution accuracy at high confidence no better than an experienced
  supervisor's first guess
- Calibration that will not hold for four weeks without refitting
- Dark-station inference that does not transfer to this plant's equipment mix
  (the held-out-station AUC is the pre-registered metric)

---

## 5. Scaling to more lines and plants

What transfers, and what does not:

| Component | Transfers? |
|---|---|
| Station-level SPC | **Yes.** Limits are per-station and fitted locally; nothing is shared. |
| Virtual sensors | **Partly.** Validated by holding out whole stations precisely because that is the transfer question. A new plant re-fits on its own instrumented population. |
| Defect-risk model | **No, not directly.** Station-to-failure-mode coupling is plant-specific. Re-fit per line; the feature definitions and the pipeline transfer, the weights do not. |
| Economics | **No.** Cost constants are the plant's own. |

The per-line cost in the business case (`platform_cost_per_line`) is an
integration and re-fitting cost, not a licence line — that is what the second and
subsequent lines actually consume.
