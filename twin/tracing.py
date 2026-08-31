"""
Delayed-defect traceback and containment.

The hard case in this problem statement: a fault appears at one station, ninety
vehicles are built, and the consequence surfaces an hour and a half later at a
station nineteen positions downstream. By the time the gate rejects a body, the
station that caused it has been running normally on the MES screen for the whole
shift.

The twin can answer this because it keeps unit genealogy: for every vehicle, the
station-by-station record of *what condition each station was in at the moment
that vehicle was there*. Attribution is then a contrast, not an inference engine.

    Among the units that just failed at this gate, how abnormal was station S
    when they passed through it -- compared with the units that passed the same
    gate in the same window?

A station that was drifting for everyone contributes nothing to that contrast; a
station that was drifting specifically for the failed units stands out. The
result is a ranked list of suspects with an explicit lift statistic, and then the
containment list: the units built through the suspect while it was drifting, split
by where they are now, because a body still in the paint shop is a very different
problem from one that has already shipped.

This is deliberately not causal inference. It is a difference in means with the
station-to-failure-mode map from the plant's FMEA used as a prior, and it is
presented to an engineer as evidence to check rather than a verdict.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from twin import config as C

MIN_FAILED = 4           # below this the contrast is noise
ALARM_Z = 3.0
MIN_EVIDENCE_Z = 1.2     # a suspect must be genuinely abnormal, not just relatively so
BASELINE_BACK_H = 24.0   # how far back the "this station used to be fine" contrast looks
SUFFICIENT = 1.0


def _mode_prior(station: C.Station, gate_id: str) -> float:
    """Can this station produce a mode that this gate catches? From the FMEA."""
    catches = set(C.GATE_SENSITIVITY.get(gate_id, {}))
    creates = set(station.creates or ())
    return 1.0 if creates & catches else 0.35


def trace(ev: pd.DataFrame, gate_idx: int, now_ts: float,
          window_h: float = 6.0, top_n: int = 6) -> dict:
    """Rank upstream suspects for failures seen at `gate_idx` in the recent window."""
    gate_station = C.STATION_BY_IDX[gate_idx]
    gate_id = gate_station.gate
    at_gate = ev[(ev.station_idx == gate_idx)
                 & (ev.depart_ts <= now_ts)
                 & (ev.depart_ts >= now_ts - window_h * 3600)]
    failed = at_gate[at_gate.gate_fail > 0]
    passed = at_gate[at_gate.gate_fail == 0]

    result = dict(gate=gate_id, gate_station=gate_station.code,
                  gate_name=gate_station.name,
                  window_h=window_h, n_failed=int(len(failed)),
                  n_passed=int(len(passed)), suspects=[], sufficient=False)
    if len(failed) < MIN_FAILED or len(passed) < MIN_FAILED:
        return result

    fail_rows = ev[ev.unit_id.isin(set(failed.unit_id)) & (ev.station_idx < gate_idx)]
    pass_rows = ev[ev.unit_id.isin(set(passed.unit_id)) & (ev.station_idx < gate_idx)]

    fz = fail_rows.groupby("station_idx")["station_z_eff"]
    pz = pass_rows.groupby("station_idx")["station_z_eff"]
    f_alarm = fail_rows.assign(a=fail_rows.station_z_eff > ALARM_Z).groupby("station_idx")["a"].mean()
    p_alarm = pass_rows.assign(a=pass_rows.station_z_eff > ALARM_Z).groupby("station_idx")["a"].mean()
    conf = fail_rows.groupby("station_idx")["data_confidence"].mean()

    # Second contrast, against the same station a day earlier. The within-window
    # comparison alone is not enough: when a station is drifting badly it is
    # drifting for the units that passed the gate too, so the failed-vs-passed
    # gap compresses exactly when the station is most guilty. On the demo
    # incident BODY-08 was in alarm for 88% of failed units and 62% of passed
    # ones -- obviously the culprit, but only a 1.4x lift. Asking "was this
    # station like this yesterday" separates a station that changed from one
    # that is always noisy.
    base_rows = ev[(ev.depart_ts <= now_ts - BASELINE_BACK_H * 3600)
                   & (ev.depart_ts >= now_ts - (BASELINE_BACK_H + 12) * 3600)
                   & (ev.station_idx < gate_idx)]
    bz = base_rows.groupby("station_idx")["station_z_eff"].agg(["mean", "std"])

    rows = []
    for idx in sorted(set(fz.groups) & set(pz.groups)):
        st = C.STATION_BY_IDX[int(idx)]
        mf, mp = float(fz.mean()[idx]), float(pz.mean()[idx])
        sd = float(pass_rows[pass_rows.station_idx == idx]["station_z_eff"].std())
        # (a) did the failed units meet this station in a worse state than the
        #     units that passed
        effect = (mf - mp) / max(sd, 0.6)
        # (b) is this station in a worse state than it was a day ago
        b_mean = float(bz["mean"].get(idx, 0.0))
        b_sd = float(bz["std"].get(idx, np.nan))
        shift = (mf - b_mean) / max(b_sd if np.isfinite(b_sd) else 0.6, 0.6)

        af, ap = float(f_alarm.get(idx, 0.0)), float(p_alarm.get(idx, 0.0))
        lift = af / max(ap, 1e-3)
        prior = _mode_prior(st, gate_id)
        # A suspect has to be abnormal in absolute terms, not merely more
        # abnormal than its neighbours. Without this floor, stations sitting at
        # z = 0.8 against z = 0.3 produce large standardised effects out of
        # nothing and crowd out the real cause.
        credible = mf >= MIN_EVIDENCE_Z
        score = 0.0
        if credible:
            # The temporal shift says the station changed. The within-window
            # effect says it changed *for the units that failed* -- which is what
            # separates a cause from a coincidence, since on any given shift more
            # than one station may be drifting. A station equally abnormal for
            # the bodies that passed the gate is discounted, not promoted.
            specificity = float(np.clip(1.0 + effect, 0.45, 2.0))
            score = max(0.0, shift) * prior * specificity \
                * (0.7 + 0.3 * min(lift / 3.0, 1.0))
        rows.append(dict(
            station_idx=int(idx), station_code=st.code, name=st.name,
            zone=st.zone, tier=st.tier,
            mean_z_failed=round(mf, 2), mean_z_passed=round(mp, 2),
            mean_z_yesterday=round(b_mean, 2),
            share_alarm_failed=round(af, 3), share_alarm_passed=round(ap, 3),
            alarm_lift=round(min(lift, 99.0), 1),
            effect_size=round(effect, 2), temporal_shift=round(shift, 2),
            fmea_prior=prior, credible=bool(credible),
            data_confidence=round(float(conf.get(idx, 0.5)), 2),
            score=round(score, 3)))

    rows.sort(key=lambda r: -r["score"])
    top = [r for r in rows if r["score"] > 0][:top_n]
    if top:
        total = sum(r["score"] for r in top) or 1.0
        for r in top:
            r["share"] = round(r["score"] / total, 3)
    # How much the evidence actually singles anyone out. A mode-specific gate
    # such as the ASSY-27 torque audit usually produces one dominant suspect. The
    # end-of-line gate catches five failure modes from twenty-five stations, and
    # on a shift where several stations are drifting it genuinely cannot tell
    # them apart -- the top scores come out flat and the composite score
    # saturates, so the contrast between failed and passed units vanishes.
    #
    # The twin says so rather than promoting whichever candidate won by a nose.
    # An attribution engine that always names a station will eventually send a
    # maintenance crew to a healthy one, and that is how a plant learns to stop
    # believing it.
    if top:
        shares = [r["share"] for r in top]
        lead = shares[0]
        gap = lead - (shares[1] if len(shares) > 1 else 0.0)
        n_modes = len(C.GATE_SENSITIVITY.get(gate_id, {}))
        if lead >= 0.45 and gap >= 0.15:
            conf, verdict = "high", "single dominant suspect"
        elif lead >= 0.30 and gap >= 0.08:
            conf, verdict = "medium", "leading suspect, worth checking first"
        else:
            conf, verdict = "low", (
                f"no dominant suspect - {len(top)} candidates, and this gate "
                f"catches {n_modes} failure modes from across the line")
        result.update(confidence=conf, verdict=verdict,
                      lead_share=round(lead, 3), lead_gap=round(gap, 3),
                      gate_modes=n_modes)
    result["suspects"] = top
    result["sufficient"] = bool(top and top[0]["score"] >= SUFFICIENT
                                and result.get("confidence") in ("high", "medium"))
    return result


def containment(ev: pd.DataFrame, station_idx: int, now_ts: float,
                lookback_h: float = 10.0) -> dict:
    """Which units passed this station while it was drifting, and where they are.

    Round 1 promised containment scoped to units rather than batches. This is
    that list: bounded by the drift window rather than by the shift, and split by
    current location, because what you can still do about a body depends entirely
    on whether it is in front of you.
    """
    st = C.STATION_BY_IDX[station_idx]
    hist = ev[(ev.station_idx == station_idx)
              & (ev.depart_ts <= now_ts)
              & (ev.depart_ts >= now_ts - lookback_h * 3600)].sort_values("depart_ts")
    if hist.empty:
        return dict(station_code=st.code, n_units=0, units=[], drift_start=None)

    drifting = hist[hist.drift]
    if drifting.empty:
        return dict(station_code=st.code, n_units=0, units=[], drift_start=None)

    start_ts = float(drifting.depart_ts.iloc[0])
    affected = hist[hist.depart_ts >= start_ts]
    ids = list(affected.unit_id.values)

    # Where is each of those units now? The furthest station it has cleared.
    latest = (ev[ev.unit_id.isin(ids) & (ev.depart_ts <= now_ts)]
              .groupby("unit_id")["station_idx"].max())
    pos = latest.reindex(ids).fillna(station_idx).astype(int)

    def bucket(p: int) -> str:
        if p >= C.N_STATIONS:
            return "shipped"
        if p >= 25:
            return "final assembly"
        if p >= 15:
            return "paint / painted-body store"
        return "body shop"

    buckets = pd.Series([bucket(p) for p in pos]).value_counts().to_dict()
    inspected = int(sum(1 for p in pos if p >= 42))

    units = [dict(unit_id=uid, position=int(p), location=bucket(int(p)),
                  station_z=round(float(z), 2))
             for uid, p, z in zip(ids, pos.values, affected.station_z_eff.values)]
    return dict(
        station_code=st.code, station_name=st.name,
        drift_start=start_ts, now=now_ts,
        drift_minutes=round((now_ts - start_ts) / 60.0, 1),
        n_units=len(ids), by_location=buckets,
        already_past_eol=inspected,
        still_recoverable=len(ids) - inspected,
        units=units[:400])


def unit_evidence(ev: pd.DataFrame, unit_id: str, top_k: int = 4) -> list:
    """Why is *this* unit risky: the upstream stations it met in a bad state.

    Sourced from the genealogy rather than from model internals, so the same
    explanation holds whichever model family the validation window selected --
    and so it names a station an engineer can walk to, rather than a feature.
    """
    rows = ev[(ev.unit_id == unit_id) & (ev.station_idx <= C.DECISION_STATION)]
    rows = rows.sort_values("station_z_eff", ascending=False).head(top_k)
    out = []
    for _, r in rows.iterrows():
        st = C.STATION_BY_IDX[int(r.station_idx)]
        out.append(dict(
            station_code=st.code, name=st.name, tier=st.tier,
            station_z=round(float(r.station_z_eff), 2),
            measured_z=round(float(r.station_z), 2),
            inferred=bool(r.get("inference_weight", 0) > 0.05),
            data_confidence=round(float(r.data_confidence), 2),
            creates=list(st.creates or ())))
    return out


# ---------------------------------------------------------------------------
# validation
# ---------------------------------------------------------------------------
def validate(ev: pd.DataFrame, defects: pd.DataFrame, units: pd.DataFrame,
             n_probes: int = 90, window_h: float = 5.0,
             test_days: tuple | None = None) -> dict:
    """Score the traceback against the simulator's recorded true origin.

    This is the answer to "how do you know that is causation and not
    correlation?", and the honest answer is that we do not know it from the
    contrast alone -- so we measure it. The generator records which station
    actually created every defect. The twin never sees that column. Sweeping
    probe times across the held-out window and comparing the twin's leading
    suspect against the true modal origin of the rejects it was looking at gives
    a hit rate rather than an argument.

    The number that matters is not the overall hit rate but the hit rate *split
    by the confidence the twin reported at the time*. An attribution engine is
    only useful if it knows when it is guessing. If HIGH-confidence traces are
    accurate and LOW-confidence ones are not, then the confidence label is
    earned and a supervisor can act on it; if they are the same, the label is
    decoration and should be removed.
    """
    day = units.set_index("unit_id")["day"]
    ev = ev.copy()
    if "day" not in ev.columns:
        ev["day"] = ev["unit_id"].map(day).values

    lo_day, hi_day = test_days or (int(ev["day"].min()), int(ev["day"].max()) + 1)
    span = ev[(ev.day >= lo_day) & (ev.day < hi_day)]
    if span.empty:
        return dict(probes=0)
    t_lo = float(span.depart_ts.quantile(0.05))
    t_hi = float(span.depart_ts.max())

    gates = [s.idx for s in C.STATIONS if s.gate and s.idx > 13]
    # true origin of each detected defect, by (unit, detecting gate)
    det = defects[defects.detect_idx.notna()].copy()
    det["detect_idx"] = det["detect_idx"].astype(int)

    rows = []
    rng = np.random.default_rng(0)
    for t in np.linspace(t_lo, t_hi, n_probes):
        for g in gates:
            res = trace(ev, g, float(t), window_h=window_h)
            if not res["suspects"]:
                continue
            at = ev[(ev.station_idx == g) & (ev.depart_ts <= t)
                    & (ev.depart_ts >= t - window_h * 3600)]
            failed_ids = set(at[at.gate_fail > 0].unit_id)
            truth = det[(det.detect_idx == g) & (det.unit_id.isin(failed_ids))]
            if len(truth) < MIN_FAILED:
                continue
            # the station that actually caused most of the rejects in this window
            counts = truth.origin_idx.value_counts()
            true_origin = int(counts.index[0])
            true_share = float(counts.iloc[0] / counts.sum())

            ranked = [s["station_idx"] for s in res["suspects"]]
            upstream = [s.idx for s in C.STATIONS if s.idx < g]
            rows.append(dict(
                t=float(t), gate=g,
                confidence=res.get("confidence", "low"),
                n_failed=res["n_failed"],
                true_origin=true_origin, true_origin_share=round(true_share, 3),
                top1=bool(ranked[0] == true_origin),
                top3=bool(true_origin in ranked[:3]),
                rank=(ranked.index(true_origin) + 1) if true_origin in ranked else None,
                random_top1=bool(int(rng.choice(upstream)) == true_origin),
            ))

    df = pd.DataFrame(rows)
    if df.empty:
        return dict(probes=0)

    def block(sub: pd.DataFrame) -> dict:
        return dict(n=int(len(sub)),
                    top1=round(float(sub.top1.mean()), 3),
                    top3=round(float(sub.top3.mean()), 3),
                    mean_true_origin_share=round(float(sub.true_origin_share.mean()), 3))

    by_conf = {c: block(df[df.confidence == c]) for c in ("high", "medium", "low")
               if (df.confidence == c).any()}
    return dict(
        probes=int(len(df)),
        overall=block(df),
        random_baseline_top1=round(float(df.random_top1.mean()), 3),
        by_confidence=by_conf,
        note="A 'hit' is the twin's leading suspect matching the station that "
             "actually created most of the rejects in that window. The true "
             "origin is recorded by the simulator and never exposed to the twin. "
             "The random baseline picks uniformly among upstream stations.",
    )
