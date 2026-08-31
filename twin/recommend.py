"""
Recommendation engine.

"Defect risk 82%" is not an output anyone can act on. Every recommendation here
carries four things: what to do, the evidence that produced it, how confident the
twin is given the instrumentation behind it, and who owns it.

Recommendations are graded by how much they cost to be wrong about, which is what
decides where the confidence bar sits:

  IMMEDIATE       stop or divert now -- expensive if wrong, so it needs strong
                  evidence from a well-instrumented station
  MONITOR         watch, no intervention -- cheap if wrong, so a sensor-poor
                  station with weaker evidence still earns one
  MAINTENANCE     schedule into the next planned window -- no production impact
  INSTRUMENTATION close a sensor gap the twin keeps hitting, with the payback
                  computed from how often that gap actually cost something

Nothing here fires automatically. Every card is a proposal with an accept/dismiss
decision attached, and those decisions feed the trust ledger, which is what makes
the false-alarm rate a measured quantity rather than a claim.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from twin import config as C
from twin import spc

ACTION_CLASSES = ["IMMEDIATE", "MONITOR", "MAINTENANCE", "INSTRUMENTATION"]

CHANNEL_PHRASE = {
    "z_vibration": "vibration",
    "z_torque_scatter": "torque scatter",
    "z_cycle_norm": "cycle time",
    "z_temp_adj": "temperature",
    "z_manual_rate": "operator checklist flag rate",
}


def _dominant_channel(rows: pd.DataFrame) -> tuple[str, float]:
    """Which channel is actually driving the alarm, over the drift window.

    Averaged over a four-hour window this named temperature at 1.7 sigma while
    the composite sat at 8.0 -- the mean over a long window is dominated by the
    healthy stretch before onset, and the quiet channels dilute the loud one.
    Taking the recent 90th percentile per channel names the one an engineer
    should actually go and look at.
    """
    best, val = None, 0.0
    recent = rows.tail(90)
    for ch in CHANNEL_PHRASE:
        if ch in recent.columns and recent[ch].notna().any():
            v = float(recent[ch].quantile(0.9))
            if np.isfinite(v) and v > val:
                best, val = ch, v
    return best, val


def _downstream_gates_for(st: C.Station) -> list[str]:
    """Where a fault at this station would eventually surface."""
    out = []
    for g in C.STATIONS:
        if g.gate and g.idx > st.idx and (set(st.creates or ()) & set(g.gate_catches)):
            out.append(f"{g.code} ({g.gate})")
    return out


def build(ev: pd.DataFrame, now_ts: float, episodes: pd.DataFrame,
          pace: pd.DataFrame, forecast: dict, containments: dict | None = None,
          horizon_h: float = 4.0) -> list:
    """Produce the ranked action list a supervisor sees."""
    recs = []
    recent = ev[(ev.depart_ts <= now_ts) & (ev.depart_ts >= now_ts - horizon_h * 3600)]
    live = episodes[(episodes.end_ts >= now_ts - 1800) & (episodes.start_ts <= now_ts)] \
        if len(episodes) else episodes

    for _, epi in live.iterrows():
        st = C.STATION_BY_IDX[int(epi.station_idx)]
        # Only the part of the episode that has already happened. The episode
        # table is built over the whole record, so `epi.n_units` and `epi.peak_z`
        # describe the incident's eventual extent -- reading them at replay time
        # would let the panel quote a unit count and a severity from the future.
        rows = ev[(ev.station_idx == st.idx)
                  & (ev.depart_ts >= epi.start_ts)
                  & (ev.depart_ts <= now_ts)]
        if rows.empty:
            continue
        ch, ch_z = _dominant_channel(rows)
        conf = float(rows["data_confidence"].mean())
        n_units = int(len(rows))
        mins = round((now_ts - epi.start_ts) / 60.0)
        peak_so_far = float(rows["station_z_eff"].max())
        gates = _downstream_gates_for(st)
        inferred = float(rows.get("inference_weight", pd.Series([0])).mean()) > 0.05

        peak = peak_so_far
        if ch and ch_z >= 1.0:
            phrase = (f"{st.code} is running {peak:.1f}σ above its qualified "
                      f"baseline, led by {CHANNEL_PHRASE[ch]} at {ch_z:.1f}σ, "
                      f"and has been outside its control limits for the last "
                      f"{n_units} cycles ({mins} min).")
        else:
            phrase = (f"{st.code} is running {peak:.1f}σ above its qualified "
                      f"baseline and has been outside its control limits for the "
                      f"last {n_units} cycles ({mins} min).")
        if inferred:
            phrase += (" This station has no vibration or torque telemetry; the "
                       "reading is inferred from cycle time, the operator "
                       "checklist and neighbouring-station behaviour.")

        severe = peak_so_far >= 6 and conf >= 0.6
        moderate = peak_so_far >= spc.ACTIONABLE_Z

        if severe and gates:
            recs.append(dict(
                cls="IMMEDIATE", station=st.code, station_name=st.name,
                title=f"Raise inspection on units passing {st.code}",
                evidence=phrase,
                action=(f"Hold and re-inspect the units built through {st.code} since "
                        f"drift began. Until it is cleared, inspect every unit at "
                        f"{gates[0].split(' ')[0]} rather than sampling."),
                why_now=(f"A fault here surfaces at {', '.join(gates)} - "
                         f"downstream of where it can still be fixed cheaply."),
                confidence=round(conf, 2), severity=round(peak_so_far, 1),
                units_affected=n_units, owner="Floor supervisor"))
            recs.append(dict(
                cls="MAINTENANCE", station=st.code, station_name=st.name,
                title=f"Book {st.code} into the next maintenance window",
                evidence=phrase,
                action=("Inspect spindle, tooling and fixture datum. The signature is "
                        "wear, not a step change, so it will keep degrading."
                        if ch in ("z_vibration", "z_torque_scatter") else
                        "Inspect the station for a mechanical or process cause."),
                why_now="Degradation is monotonic; the next window is cheaper than the one after.",
                confidence=round(conf, 2), severity=round(peak_so_far, 1),
                units_affected=n_units, owner="Maintenance planner"))
        elif moderate:
            recs.append(dict(
                cls="MONITOR", station=st.code, station_name=st.name,
                title=f"Watch {st.code}",
                evidence=phrase,
                action=("No intervention yet. The twin will escalate if the deviation "
                        "persists for another 25 cycles or crosses 6σ."),
                why_now=("Evidence is real but not yet strong enough to justify "
                         "stopping work at this station."),
                confidence=round(conf, 2), severity=round(peak_so_far, 1),
                units_affected=n_units, owner="Floor supervisor"))

        # A dark station that keeps needing inference is an instrumentation case,
        # and the payback is computable rather than asserted.
        if st.tier in ("DARK", "PARTIAL") and moderate:
            hist = episodes[(episodes.station_idx == st.idx) & (episodes.actionable)]
            per_year = len(hist) / max(C.N_DAYS, 1) * C.ECONOMICS["production_days_per_year"]
            avoided = per_year * 0.35 * n_units * 0.06 * C.ECONOMICS["rework_cost_at_gate"]
            cost = C.ECONOMICS["sensor_retrofit_cost"]
            recs.append(dict(
                cls="INSTRUMENTATION", station=st.code, station_name=st.name,
                title=f"Retrofit vibration and torque telemetry at {st.code}",
                evidence=(f"{st.code} raised {len(hist)} actionable alerts over "
                          f"{C.N_DAYS} days, each carrying only "
                          f"{round(conf * 100)}% data confidence because the "
                          "condition has to be inferred rather than measured."),
                action=(f"Add a nutrunner torque trace and an accelerometer during a "
                        f"scheduled maintenance window. Estimated "
                        f"${cost:,.0f} installed."),
                why_now=(f"Detection here currently lags a comparable instrumented "
                         f"station. Modelled avoided rework "
                         f"${avoided:,.0f}/yr against ${cost:,.0f} one-off "
                         f"({'under' if avoided > cost else 'over'} "
                         f"{max(0.1, cost / max(avoided, 1)):.1f} year payback)."),
                confidence=round(conf, 2), severity=round(peak_so_far, 1),
                units_affected=n_units, owner="Plant engineering",
                economics=dict(retrofit_cost=cost, modelled_annual_benefit=round(avoided),
                               payback_years=round(cost / max(avoided, 1), 2))))

    # Flow: the constraint the line is about to hand over to. Only worth raising
    # when the handover actually costs throughput -- a constraint moving between
    # two stations that both clear takt is a curiosity, not an action, and
    # putting it on an IMMEDIATE card next to a real one devalues both.
    ch = forecast.get("change")
    takt_cap = forecast.get("takt_capacity_uph", 0)
    if ch and (ch["capacity_uph"] < takt_cap or forecast.get("units_at_risk", 0) > 0):
        opts = []
        row = pace[pace.station_code == ch["station_code"]]
        if not row.empty:
            from twin.flow import rebalance_options
            opts = rebalance_options(pace, ch["station_code"])
        recs.append(dict(
            cls="IMMEDIATE", station=ch["station_code"],
            station_name=C.STATION_BY_CODE[ch["station_code"]].name,
            title=f"{ch['station_code']} becomes the line constraint in ~{ch['in_minutes']} min",
            evidence=(f"Projected capacity {ch['capacity_uph']:.0f} units/h against a "
                      f"takt of {forecast['takt_capacity_uph']:.0f}. "
                      f"{forecast['units_at_risk']:.0f} units at risk over the "
                      f"{forecast['horizon_min']}-minute horizon."),
            action=opts[0]["action"] if opts else "Rebalance work content at this station.",
            why_now=("The constraint has not moved yet. Acting before it does is a "
                     "rebalance; acting after it does is overtime."),
            confidence=0.8, severity=5.0,
            units_affected=int(forecast["units_at_risk"]),
            owner="Floor supervisor", options=opts))

    order = {"IMMEDIATE": 0, "MONITOR": 1, "MAINTENANCE": 2, "INSTRUMENTATION": 3}
    recs.sort(key=lambda r: (order[r["cls"]], -r["severity"] * r["confidence"]))
    for i, r in enumerate(recs):
        r["id"] = f"REC-{i:03d}"
    return recs
