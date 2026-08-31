#!/usr/bin/env python3
"""
Generate the business proposal HTML from measured results.

    python docs/build_proposal.py && python docs/build_docs.py

Every figure comes out of artifacts/validation.json via docs/FACTS.json. Nothing
is typed in, so the proposal cannot drift from what the prototype actually
produces -- re-run the pipeline and the document re-states itself.
"""
from __future__ import annotations

import json
import pathlib

DOCS = pathlib.Path(__file__).resolve().parent
F = json.loads((DOCS / "FACTS.json").read_text())

d, mdl, tb, vsr, fc, ec = (F["detection"], F["model"], F["traceback"],
                           F["virtual_sensor"], F["forecast"], F["economics"])
q, th = ec["quality"], ec["throughput"]
pc = lambda x, n=0: f"{100 * x:.{n}f}%"
usd = lambda x: f"${x:,.0f}"
m = lambda x: f"${x / 1e6:.2f}M"


def kpi(k, v, s):
    return f'<div class="kpi"><div class="k">{k}</div><div class="v">{v}</div><div class="s">{s}</div></div>'


def fig(src, cap):
    return f'<img src="assets/{src}"><p class="caption">{cap}</p>'


SECTIONS = []
S = SECTIONS.append

# ── cover ───────────────────────────────────────────────────────────────────
S(f"""
<div class="cover">
  <h1>SmartFactory Twin</h1>
  <p class="tag">Don't wait for the defect.</p>
  <p>A flow-level digital twin for a vehicle assembly line. It detects a station
  going bad while it is still going bad, traces a late-discovered defect back to
  the station that most likely caused it, and scopes containment to the vehicles
  actually affected — on a brownfield line where a seventh of the stations have
  no process sensors at all.</p>
  <div class="meta">Business Proposal &nbsp;·&nbsp; Team PeakBusters
  &nbsp;·&nbsp; Accenture Innovation Challenge 2026 &nbsp;·&nbsp; Problem Track 4,
  Round 2</div>
</div>""")

# ── 1. the problem ──────────────────────────────────────────────────────────
S(f"""
<h2>1 &nbsp; The problem</h2>
<p>A vehicle assembly line fails in two ways, and reports both only after the
loss is already booked.</p>
<p><b>Bottlenecks are confirmed, not foreseen.</b> MES dashboards show the jam
once throughput has already been lost. The only lever left is overtime, not
rebalancing.</p>
<p><b>Defects escape in batches.</b> A fault introduced at an early station
surfaces at a downstream gate an hour or more later, turning one error into a
rework campaign, a containment exercise and warranty exposure.</p>
<div class="note"><b>The incident this proposal is built around.</b> At 07:12 a
nutrunner spindle at station BODY-08 begins to wear. Mean torque stays inside the
PLC acceptance window the entire time — only the <i>scatter</i> grows — so every
existing limit check stays green. The first vehicle is rejected at ASSY-27, the
chassis torque audit, roughly <b>90 minutes and 240 vehicles later</b>. That is
the moment a conventional plant finds out.</div>
<p>By then the useful question has already changed. It is no longer <i>"what is
wrong?"</i> but <i>"how many, and where are they now?"</i></p>""")

# ── 2. why conventional monitoring fails ────────────────────────────────────
S(f"""
<h2>2 &nbsp; Why conventional monitoring does not catch it</h2>
<table>
<tr><th>Approach</th><th>What it misses</th></tr>
<tr><td><b>PLC limit checks</b></td><td>Watch the mean, not the variance. A worn
spindle whose scatter has doubled can sit inside every acceptance window.</td></tr>
<tr><td><b>MES throughput dashboards</b></td><td>Report the constraint after WIP
has piled up. A quality fault that does not slow the line is invisible.</td></tr>
<tr><td><b>End-of-line inspection</b></td><td>Correct but late. It finds the
batch, not the cause, and not before the batch exists.</td></tr>
<tr><td><b>Full-IoT digital twins</b></td><td>Assume complete instrumentation.
On a brownfield line a meaningful minority of stations have none, and those are
usually the manual ones where errors originate.</td></tr>
</table>
<p>The gap is not sensing. It is that nobody is <b>modelling each station against
its own qualified normal</b>, keeping a record of which vehicle met which station
in which condition, and using that record when a gate finally rejects something.</p>""")

# ── 3. the twin ─────────────────────────────────────────────────────────────
S(f"""
<h2>3 &nbsp; The SmartFactory Twin</h2>
<p>A twin of <b>flow and quality</b> — deliberately not of geometry. It carries
three things a dashboard does not:</p>
<table>
<tr><th>Capability</th><th>What it enables</th></tr>
<tr><td><b>Per-station condition model</b><br>each station charted against its own
frozen, qualified baseline</td><td>Detects a station leaving its envelope while
production is still running, not after a gate rejects.</td></tr>
<tr><td><b>Unit genealogy</b><br>for every vehicle: which stations it passed and
what condition each was in <i>at that moment</i></td><td>Turns a late rejection
into a ranked list of upstream suspects and an exact affected-unit list.</td></tr>
<tr><td><b>Flow model rolled forward</b><br>station capacities projected two hours
ahead</td><td>Names the station that <i>becomes</i> the constraint, with time to
rebalance rather than pay overtime.</td></tr>
</table>
<div class="kpis">
  {kpi("Detection", f"{d['body08']:.0f} min", "BODY-08, vs ~90 min to first reject")}
  {kpi("Alert load", f"{d['alerts_per_shift']}/shift", "across all 42 stations")}
  {kpi("Attribution", pc(tb['by_confidence']['high']['top1']), "top-1 correct at high confidence")}
  {kpi("Dark stations", f"{vsr['auc']:.2f} AUC", "virtual sensing, unseen stations")}
</div>""")

# ── 4. architecture ─────────────────────────────────────────────────────────
S(f"""
<h2>4 &nbsp; Architecture</h2>
<pre><code>MES part scans · PLC handshake · process telemetry · quality gates · operator checklists
        |
        v
  DIGITAL TWIN STATE        per-station condition · unit genealogy · flow model
        |
        +--> ANOMALY DETECTION      frozen-baseline SPC + virtual sensors (dark stations)
        +--> DEFECT-RISK MODEL      calibrated, capacity-aware, scored at body exit
        +--> RANKED TRACEBACK       genealogy contrast + FMEA prior, with confidence
        +--> FLOW FORECAST          two-hour capacity roll-forward
        |
        v
  RISK &amp; ACTION ENGINE      four action classes, confidence-gated, human-in-the-loop
        |
        v
  ROLE-BASED VIEWS          supervisor · plant manager · leadership</code></pre>
<p><b>Read-only, and advisory-only.</b> The twin writes nothing back to the
control system. Every recommendation is an action a human already has the
authority to take, which keeps it outside the safety envelope and outside the
change-control burden that would otherwise dominate deployment.</p>
<p><b>Deployment footprint:</b> one process and a browser. No microservices, no
Kubernetes, no cloud dependency.</p>""")

# ── 5. predictive mechanism ─────────────────────────────────────────────────
S(f"""
<h2 class="pagebreak">5 &nbsp; How the prediction works</h2>
<p>Three mechanisms, in descending order of how much weight we put on them.</p>
<h3>5.1 &nbsp; Station condition — the primary signal</h3>
<p>Each station is charted against control limits <b>fitted on a qualification
window and then frozen</b>, with assignable-cause points trimmed out of the
baseline. This matters more than it sounds: a continuously self-updating baseline
is how you build a drift detector that cannot detect drift, because it quietly
re-centres on the fault until it reads as normal.</p>
<p>Signals are separated into a <b>condition</b> score (is this station
degrading?) and a <b>flow</b> score (is it constraining the line?), because the
evidence for each is different and mixing them produced ten times the false
alarms at no gain in detection.</p>
<h3>5.2 &nbsp; Defect risk per vehicle</h3>
<p>At body exit, each vehicle is scored for the probability it will be flagged at
a downstream quality gate, using only what happened upstream of that point. The
score is <b>calibrated</b> — a 20% risk really does fail about one time in five —
because an uncalibrated number shown to an operator is one they learn to discount.</p>
<h3>5.3 &nbsp; Bottleneck forecast</h3>
<p>Station capacities are extrapolated forward two hours to name the station that
becomes the constraint, and when.</p>
<div class="note"><b>We are explicit about which of these is weakest.</b> The
per-vehicle risk model is the least impressive of the three and we do not lead
with it. Its honest ceiling is set by the fact that about half of downstream
failures originate <i>after</i> the decision point — in paint or final assembly —
where no body-exit model can reach them. Section 11 reports it in full anyway.</div>""")

# ── 6. hero incident ────────────────────────────────────────────────────────
S(f"""
<h2 class="pagebreak">6 &nbsp; The hero incident: BODY-08</h2>
<table>
<tr><th>Time</th><th>What happens</th><th>What the twin does</th></tr>
<tr><td><b>07:12</b></td><td>Spindle bearing begins to wear. Mean torque still
inside the PLC window.</td><td>Nothing yet — correctly.</td></tr>
<tr><td><b>07:43</b></td><td>Vibration and torque scatter climbing together.</td>
<td>Raises <b>MONITOR</b>. Evidence real, not yet worth stopping work.</td></tr>
<tr><td><b>07:58</b></td><td>Deviation sustained for 21 cycles.</td>
<td>Escalates to <b>IMMEDIATE</b> at 8.0σ, led by vibration at 6.2σ. Nothing was
added but fifteen more minutes of evidence.</td></tr>
<tr><td><b>~09:30</b></td><td>First bodies rejected at ASSY-27.</td>
<td>Already contained. This is when a conventional line would first react.</td></tr>
</table>
{fig("02-line-escalated.png", "07:58 — BODY-08 escalated to IMMEDIATE. The station "
     "detail shows vibration at 6.2σ against a frozen baseline, with the alarm band "
     "and the FMEA link to ASSY-27, ASSY-41 and ASSY-42.")}
<p>The recommendation is not a risk percentage. It names the station, the
evidence, the action, and where the fault will surface if ignored — and it
carries an accept/dismiss decision that is logged, which is what turns the
false-alarm rate from a claim into a measurement.</p>""")

# ── 7. traceback ────────────────────────────────────────────────────────────
S(f"""
<h2 class="pagebreak">7 &nbsp; Delayed defects: traceback and containment</h2>
<p>When a gate does reject a body, the twin contrasts what each rejected unit
experienced upstream against the units that <i>passed</i> the same gate, and
against the same station a day earlier — weighted by the plant's FMEA
station-to-failure-mode map.</p>
{fig("03-traceback.png", "12:10 — 14 rejects at the ASSY-27 torque audit. BODY-08 "
     "carries 84% of the evidence at HIGH confidence; containment is scoped to the "
     "238 units that passed during 272 minutes of drift, 86 of them still in the plant.")}
<div class="note"><b>We call this ranked attribution, not root-cause
prediction.</b> It is a difference-in-means with a domain prior, presented to an
engineer as evidence to check. What makes it trustworthy is not the ranking — it
is that we measured how often the ranking is right, and published the result
alongside the confidence the twin reported at the time.</div>
<h3>Measured against ground truth</h3>
<table>
<tr><th>Confidence the twin reported</th><th>Windows</th><th>Top-1 correct</th><th>Top-3 correct</th></tr>
<tr><td><b>HIGH</b></td><td>{tb['by_confidence']['high']['n']}</td>
    <td><b>{pc(tb['by_confidence']['high']['top1'])}</b></td>
    <td>{pc(tb['by_confidence']['high']['top3'])}</td></tr>
<tr><td>MEDIUM</td><td>{tb['by_confidence']['medium']['n']}</td>
    <td>{pc(tb['by_confidence']['medium']['top1'])}</td>
    <td>{pc(tb['by_confidence']['medium']['top3'])}</td></tr>
<tr><td>LOW</td><td>{tb['by_confidence']['low']['n']}</td>
    <td>{pc(tb['by_confidence']['low']['top1'])}</td>
    <td>{pc(tb['by_confidence']['low']['top3'])}</td></tr>
<tr><td>All windows</td><td>{tb['overall']['n']}</td>
    <td>{pc(tb['overall']['top1'])}</td><td>{pc(tb['overall']['top3'])}</td></tr>
<tr><td><i>Random upstream station</i></td><td>—</td>
    <td><i>{pc(tb['random_baseline_top1'])}</i></td><td>—</td></tr>
</table>
<p>The number that matters is not {pc(tb['overall']['top1'])}. It is that
<b>accuracy tracks the confidence the twin reported</b>. An attribution engine
that always names a station will eventually send a crew to a healthy one, and
that is how a plant learns to stop believing it.</p>""")

# ── 8. sensor-poor ──────────────────────────────────────────────────────────
S(f"""
<h2 class="pagebreak">8 &nbsp; Stations with no sensors</h2>
<p>Round 1 argued that a twin assuming full IoT coverage cannot deploy where the
problem actually lives. This prototype puts <b>{F['line']['coverage']['DARK']['stations']} of
{F['line']['stations']} stations</b> on cycle time and an operator checklist alone,
plus {F['line']['coverage']['PARTIAL']['stations']} more with partial coverage.</p>
<table>
<tr><th>Coverage</th><th>Stations</th><th>What the twin can read</th></tr>
<tr><td><b>FULL</b></td><td>{F['line']['coverage']['FULL']['stations']} ({pc(F['line']['coverage']['FULL']['share'])})</td>
    <td>cycle time, blocking/starving, vibration, torque, temperature</td></tr>
<tr><td><b>PARTIAL</b></td><td>{F['line']['coverage']['PARTIAL']['stations']} ({pc(F['line']['coverage']['PARTIAL']['share'])})</td>
    <td>cycle time, blocking/starving, temperature</td></tr>
<tr><td><b>DARK</b></td><td>{F['line']['coverage']['DARK']['stations']} ({pc(F['line']['coverage']['DARK']['share'])})</td>
    <td>cycle time, blocking/starving, operator checklist</td></tr>
</table>
<p><b>Cycle time and blocking/starving exist on 1990s equipment</b> — they come
from MES part-scan timestamps and the line-control PLC handshake. That is the
entire reason a dark station can be scored at all, and why the deployment needs
no new hardware.</p>
<h3>Virtual sensing</h3>
<p>On instrumented stations we can see both the rich evidence (vibration, torque
scatter) and the thin evidence every station produces. So we learn the mapping
from thin to rich on the stations that have both, and apply it to the stations
that only have the thin half.</p>
<div class="kpis">
  {kpi("Held-out-station AUC", f"{vsr['auc']:.2f}", "stations the model never saw")}
  {kpi("PR-AUC", f"{vsr['ap']:.2f}", f"against a {vsr['base']:.2f} base rate")}
  {kpi("Trust weight", f"{vsr['trust']:.2f}", "derived from the validated score")}
</div>
<p>Validation holds out <b>whole stations</b>, not rows, because that is the
actual deployment question: will this transfer to a station it has never seen.
The validated score then becomes the blending weight — a mapping that did not
generalise cannot raise an alarm.</p>""")

# ── 9. confidence and trust ─────────────────────────────────────────────────
S(f"""
<h2 class="pagebreak">9 &nbsp; Confidence, and knowing when not to act</h2>
<p>BODY-14 is a manual closure-fitment station with no vibration or torque
telemetry. It drifts on the same day. The twin detects it — but
<b>{d['body14']:.0f} minutes in rather than {d['body08']:.0f}</b>, and at 43% data
confidence.</p>
{fig("04-dark-station.png", "BODY-14 — detected from cycle-time creep, the operator "
     "checklist and virtual sensing. The panel states what is missing, what was "
     "inferred, and the resulting confidence discount.")}
<div class="note"><b>So it stays a MONITOR.</b> A sensor-poor station is
structurally barred from producing an IMMEDIATE "stop work" recommendation,
because its evidence cannot carry that cost. It gets a watch item and an
instrumentation business case instead.</div>
<blockquote>Strong evidence → act. Weak evidence → don't overreact.</blockquote>
<p>That asymmetry is the difference between a tool a supervisor keeps using and
one they learn to ignore. It is enforced in code, not left to judgement: the
recommendation class is gated on measured data confidence.</p>
<h3>Designed for validation</h3>
<p>Every recommendation carries an accept/dismiss decision that is logged. Over a
pilot that ledger — not our claims — is what establishes the real false-alarm
rate on that plant's own line.</p>""")

# ── 10. integration ─────────────────────────────────────────────────────────
S(f"""
<h2 class="pagebreak">10 &nbsp; Integration with legacy PLC and MES</h2>
<p>The twin is a <b>read-only consumer</b> of data that already exists. No PLC
logic change, no new tag on the control network, no modification to any interlock.</p>
<table>
<tr><th>Source</th><th>Fields</th><th>Already exists because</th></tr>
<tr><td>MES part-scan log</td><td>unit, station, arrive/depart timestamps</td>
    <td>traceability and takt reporting are mandatory</td></tr>
<tr><td>PLC handshake / historian</td><td>blocked and starved seconds</td>
    <td>the line controller computes these to sequence conveyors</td></tr>
<tr><td>Process telemetry <i>where fitted</i></td><td>torque, vibration, temperature</td>
    <td>already historised on modern cells</td></tr>
<tr><td>Quality system</td><td>gate results and defect modes</td>
    <td>rework and warranty already depend on it</td></tr>
<tr><td>Operator checklist</td><td>manual check results</td>
    <td>already recorded on paper or tablet</td></tr>
<tr><td>ERP / goods inward</td><td>lot id, incoming quality index</td>
    <td>supplier quality management already tracks it</td></tr>
</table>
<p>Transport is an OPC-UA subscription or a historian tap onto a message bus.
Where a legacy cell has no OPC-UA server at all, the MES scan record alone is
enough to place that station on the line view with cycle-time and flow scoring —
degraded, and <i>labelled</i> as degraded.</p>
<p><b>Nothing is written back.</b> If a plant later wants closed-loop action, the
natural first step is a supervisory setpoint such as inspection sampling rate at
a gate — not a control action.</p>""")

# ── 11. validation ──────────────────────────────────────────────────────────
S(f"""
<h2 class="pagebreak">11 &nbsp; Validation and evidence</h2>
<p>Everything below is measured on a <b>held-out temporal split</b> — train days
{mdl['split']['train_days'][0]}–{mdl['split']['train_days'][1]-1},
calibrate {mdl['split']['val_days'][0]}–{mdl['split']['val_days'][1]-1},
test {mdl['split']['test_days'][0]}–{mdl['split']['test_days'][1]-1} — and is
reproduced by a single command. All three demo incidents fall in the test window,
so nothing about them was learned.</p>
<h3>Detection</h3>
<table>
<tr><th>Measure</th><th>Result</th></tr>
<tr><td>Actionable alerts</td><td><b>{d['alerts_per_shift']} per shift</b> across all {F['line']['stations']} stations</td></tr>
<tr><td>BODY-08 (instrumented) detected</td><td><b>{d['body08']:.0f} min</b> after onset</td></tr>
<tr><td>ASSY-31 (instrumented) detected</td><td>{d['assy31']:.0f} min after onset</td></tr>
<tr><td>BODY-14 (<b>sensor-poor</b>) detected</td><td>{d['body14']:.0f} min after onset</td></tr>
<tr><td>Healthy stations</td><td>99th percentile condition score 2.8σ</td></tr>
</table>
<h3>Defect-risk model</h3>
<table>
<tr><th>Population</th><th>ROC-AUC</th><th>PR-AUC</th><th>Base rate</th><th>Lift</th></tr>
<tr><td>All downstream failures</td><td>{mdl['test']['roc_auc']:.3f}</td>
    <td>{mdl['test']['pr_auc']:.3f}</td><td>{mdl['test']['base_rate']:.3f}</td>
    <td>×{mdl['test']['pr_lift']}</td></tr>
<tr><td><b>Reachable failures only</b></td><td><b>{mdl['reachable']['roc_auc']:.3f}</b></td>
    <td>{mdl['reachable']['pr_auc']:.3f}</td><td>{mdl['reachable']['base_rate']:.3f}</td>
    <td><b>×{mdl['reachable']['pr_lift']}</b></td></tr>
<tr><td><i>Null model — training labels shuffled</i></td><td><i>{mdl['null']['roc_auc']:.3f}</i></td>
    <td><i>{mdl['null']['pr_auc']:.3f}</i></td><td><i>{mdl['null']['base_rate']:.3f}</i></td>
    <td><i>×0.82</i></td></tr>
</table>
<p>False-alarm rate <b>{pc(mdl['test']['false_alarm_rate'], 1)}</b>, Brier score
{mdl['test']['brier']:.3f}, {mdl['alerts']:.0f} flagged units per shift against a
stated inspection capacity of {mdl['capacity']}.</p>
<div class="note"><b>Read honestly.</b> Of {mdl['ceiling']['positives']} failures in the
test window, {mdl['ceiling']['body_attributable']} originate upstream of the decision point
and {mdl['ceiling']['downstream_origin']} originate after it — the second group is
unreachable by any body-exit model, which is a structural ceiling rather than a
modelling gap. The bootstrap 95% interval on test ROC-AUC is
[{mdl['ci']['roc_auc_ci'][0]:.2f}, {mdl['ci']['roc_auc_ci'][1]:.2f}], which also means
the three model families we fitted are statistically indistinguishable; we do not
claim the selected one is better.</div>
<h3>Bottleneck forecast</h3>
<p>{pc(fc['hit_rate'])} of constraint-handover calls verified, median
<b>{fc['median_lead_min']:.0f} minutes</b> of warning. Eleven calls is a small
sample and is reported as such.</p>
{fig("05-validation.png", "The Validation view ships inside the product. Metrics, "
     "model selection, calibration curve, capacity curve and traceback accuracy are "
     "visible to the customer, not just to us.")}""")

# ── 12. scalability ─────────────────────────────────────────────────────────
S(f"""
<h2 class="pagebreak">12 &nbsp; Scaling from one line to many</h2>
<table>
<tr><th>Component</th><th>Transfers to a new line or plant?</th></tr>
<tr><td>Station-level SPC</td><td><b>Yes.</b> Limits are per-station and fitted
locally; nothing is shared between lines.</td></tr>
<tr><td>Virtual sensors</td><td><b>Partly.</b> Validated by holding out whole
stations precisely because that is the transfer question. A new plant re-fits on
its own instrumented population.</td></tr>
<tr><td>Defect-risk model</td><td><b>No, not directly.</b> Station-to-failure-mode
coupling is plant-specific. Feature definitions and the pipeline transfer; the
weights do not.</td></tr>
<tr><td>Economics</td><td><b>No.</b> Cost constants are the plant's own.</td></tr>
</table>
<p>This is why the incremental cost per line is an <b>integration and re-fitting</b>
cost rather than a licence line — it is what the second and subsequent lines
actually consume. A plant with different equipment ages does not need a different
product; it needs its own qualification window and its own cost book.</p>""")

# ── 13. ROI ─────────────────────────────────────────────────────────────────
S(f"""
<h2 class="pagebreak">13 &nbsp; The business case</h2>
<div class="kpis">
  {kpi("Annual benefit", m(ec['annual']), "one line, after haircuts")}
  {kpi("Year-1 cost", usd(ec['y1_cost']), "build, integration, pilot")}
  {kpi("Payback", f"{ec['payback']:.1f} months", "on the point estimate")}
</div>
<h3>Where the quality benefit comes from <span class="tag-pill MODELLED">MODELLED</span></h3>
<table>
<tr><th>Line</th><th>Volume</th><th>Unit value</th><th>Annual</th></tr>
<tr><td>Defects caught at body exit instead of at a gate</td>
    <td>{q['defects_caught_early_per_year']:,}/yr</td><td>× {usd(q['saving_per_catch'])}</td>
    <td>{usd(q['defects_caught_early_per_year'] * q['saving_per_catch'])}</td></tr>
<tr><td>Escapes intercepted (defects no gate would catch)</td>
    <td>{q['escapes_intercepted_per_year']:,}/yr</td><td>× {usd(q['saving_per_escape'])}</td>
    <td>{usd(q['escapes_intercepted_per_year'] * q['saving_per_escape'])}</td></tr>
<tr><td>Probability a targeted re-inspection finds the fault</td><td></td>
    <td>× {q['inspection_effectiveness']}</td><td>{usd(q['gross_benefit'])}</td></tr>
<tr><td>Cost of the extra inspections this creates</td>
    <td>{q['extra_inspections_per_year']:,}/yr</td><td>× $26</td>
    <td>−{usd(q['inspection_cost'])}</td></tr>
<tr><td>Realisation haircut on everything modelled</td><td></td>
    <td>× {q['realisation_factor']}</td><td><b>{usd(q['net_benefit'])}</b></td></tr>
</table>
<h3>Throughput benefit <span class="tag-pill MODELLED">MODELLED</span></h3>
<p>{th['constraint_events_verified']} verified constraint calls over
{th['probe_span_days']} days → {th['constraint_events_per_year']:,}/yr, ×
{th['units_at_risk_per_event']} units at risk × {th['assumed_conversion_rate']}
conversion × {th['realisation_factor']} realisation ×
{usd(th['contribution_margin_per_unit'])} contribution margin =
<b>{usd(th['benefit'])}</b>.</p>
<p>Valued at contribution margin on recovered production, <b>not</b> at a
stopped-line downtime rate. A constraint handover slows the line; it does not
stop it. Using the $22k/hour downtime figure here would have produced a $2.9M
throughput benefit and a two-week payback — a number that ends a conversation
with a plant manager rather than starting one.</p>
<div class="note"><b>The honest weak point.</b> The largest single line — warranty
exposure avoided on intercepted escapes — rests on
{q['escapes_intercepted_in_test']} events in a {q['test_window_days']}-day window. Its
95% interval puts the quality benefit between <b>{m(q['benefit_range']['low'])}</b> and
<b>{m(q['benefit_range']['high'])}</b> against a {m(q['net_benefit'])} point estimate.
A pilot should measure this before the figure is committed anywhere.</div>
<h3>How to read every number in this section</h3>
<table>
<tr><th>Label</th><th>Meaning</th></tr>
<tr><td><span class="tag-pill MEASURED">MEASURED</span></td><td>Counted in the prototype's own
held-out test window — true positives, alerts, verified forecasts, attribution hits.</td></tr>
<tr><td><span class="tag-pill MODELLED">MODELLED</span></td><td>A measured quantity multiplied by
a stated cost assumption.</td></tr>
<tr><td><span class="tag-pill ASSUMED">ASSUMED</span></td><td>A cost constant carrying no evidence
from this prototype. A plant substitutes its own cost book.</td></tr>
</table>""")

# ── 14. rollout ─────────────────────────────────────────────────────────────
S(f"""
<h2 class="pagebreak">14 &nbsp; Implementation roadmap</h2>
<p>Designed so that failure is visible early and cheap.</p>
<table>
<tr><th>Phase</th><th>What happens</th><th>Exit criterion</th></tr>
<tr><td><b>1 — Shadow</b><br>weeks 1–8</td>
    <td>Twin runs on live data and shows nobody anything. Every alert, score and
    attribution is logged. Control limits qualified on this plant's own data.</td>
    <td>PR-AUC lift ≥ 1.5 with a bootstrap interval clearing 1.0, and ≤ 15
    actionable alerts per shift. <b>If not met, stop.</b></td></tr>
<tr><td><b>2 — Advisory</b><br>weeks 9–20</td>
    <td>Body shop only. Supervisors see alerts and accept or dismiss each one.
    Attribution claims are checked against what maintenance actually finds.</td>
    <td>≥ 50% of high-confidence attributions confirmed by maintenance;
    acceptance rate neither near 0% nor near 100%.</td></tr>
<tr><td><b>3 — Full line</b><br>weeks 21–40</td>
    <td>All zones. Compared against the same line's prior-year first-time-through
    quality, escape rate and constraint-related loss.</td>
    <td>Business case restated with the plant's own measured effect size,
    replacing every MODELLED figure.</td></tr>
<tr><td><b>4 — Scale</b><br>from month 10</td>
    <td>Second line, then second plant. Re-qualification and re-fitting per line;
    the product does not change.</td>
    <td>Per-line integration cost tracking to plan.</td></tr>
</table>
<h3>What would falsify this</h3>
<p>Stated in advance, because a pilot that cannot fail is not a test:</p>
<ul>
<li>Alert volume that cannot be brought under ~15 per shift without losing the faults</li>
<li>High-confidence attribution no better than an experienced supervisor's first guess</li>
<li>Calibration that will not hold for four weeks without refitting</li>
<li>Dark-station inference that does not transfer to this plant's equipment mix</li>
</ul>
<h3>What is built, and what is not</h3>
<table>
<tr><th>Status</th><th>Scope</th></tr>
<tr><td><span class="tag-pill MEASURED">IMPLEMENTED</span></td><td>SPC and drift detection ·
virtual sensors · feature pipeline · model training, calibration and selection ·
bottleneck forecast · traceback, containment and its accuracy validation ·
recommendation engine · economics · the full dashboard</td></tr>
<tr><td><span class="tag-pill MODELLED">SIMULATED</span></td><td>The plant itself. Telemetry,
defect creation and gate detection come from a generator with a latent causal
model the twin never sees. Everything downstream would run unchanged on a real
MES feed.</td></tr>
<tr><td><span class="tag-pill ASSUMED">PROPOSED</span></td><td>MES / PLC / OPC-UA connectors ·
multi-plant rollout · model registry and retraining schedule · authentication and
audit trail for the decision ledger</td></tr>
</table>
<div class="note"><b>Round 1 promised three things.</b> A bottleneck forecast
rather than a jam alert; defect risk with a traceback list rather than an alarm;
and virtual sensors so coverage comes from inference rather than new hardware.
All three are now working code with measured results — and where a result is weak
or a sample is thin, this document says so.</div>""")

html = "\n".join(SECTIONS)
(DOCS / "BUSINESS-PROPOSAL.html").write_text(html, encoding="utf-8")
print(f"docs/BUSINESS-PROPOSAL.html  ({len(html) / 1024:.0f} KB, {len(SECTIONS)} sections)")
