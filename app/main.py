"""
SmartFactory Twin — API and dashboard server.

The twin replays a recorded production day against a clock the client controls,
so a demo can move to the moment that matters instead of waiting for it. Every
number served here is computed by the `twin` package from the event record at the
requested timestamp; nothing is precomputed for the screen, and no endpoint can
see past `t`. That constraint is what makes the replay honest: at 07:30 the
dashboard genuinely does not know what happens at 09:00.

    uvicorn app.main:app --reload
"""
from __future__ import annotations


import json
from functools import lru_cache
from pathlib import Path

import numpy as np
import pandas as pd
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from twin import config as C
from twin import flow, recommend, spc, tracing

STATIC = Path(__file__).parent / "static"
app = FastAPI(title="SmartFactory Twin", version="2.0")


# ---------------------------------------------------------------------------
# data, loaded once
# ---------------------------------------------------------------------------
class Store:
    def __init__(self):
        d = C.DATA_DIR
        missing = [f for f in ("events_app.pkl", "units.pkl", "defects.pkl",
                               "episodes.pkl", "risk.pkl") if not (d / f).exists()]
        if missing:
            raise RuntimeError(
                f"missing {missing} in {d}. Run `python -m twin.pipeline` first.")
        self.ev = pd.read_pickle(d / "events_app.pkl")
        self.units = pd.read_pickle(d / "units.pkl")
        self.defects = pd.read_pickle(d / "defects.pkl")
        self.episodes = pd.read_pickle(d / "episodes.pkl")
        self.risk = pd.read_pickle(d / "risk.pkl").set_index("unit_id")
        self.validation = json.loads((C.ARTIFACT_DIR / "validation.json").read_text())
        self.ev = self.ev.sort_values("depart_ts")
        self.by_station = {i: g for i, g in self.ev.groupby("station_idx")}
        self.decisions: list[dict] = []

        t0 = pd.Timestamp(C.DAY_ZERO).value / 1e9
        self.day_start = t0 + C.DEMO_DAY * 24 * 3600
        self.t_min = self.day_start + 6 * 3600
        self.t_max = self.day_start + 22 * 3600


@lru_cache(maxsize=1)
def store() -> Store:
    return Store()


def _clock(t: float | None) -> float:
    s = store()
    if t is None:
        return s.t_min + 2 * 3600
    return float(np.clip(t, s.t_min, s.t_max))


def _jsonable(o):
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, (np.floating,)):
        return None if not np.isfinite(o) else float(o)
    if isinstance(o, (np.bool_,)):
        return bool(o)
    if isinstance(o, dict):
        return {k: _jsonable(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [_jsonable(v) for v in o]
    if isinstance(o, float) and not np.isfinite(o):
        return None
    return o


def ok(payload) -> JSONResponse:
    return JSONResponse(_jsonable(payload))


def _quietest_window(s: Store, before: float | None = None) -> float:
    """The calmest 15 minutes of the demo day: fewest stations in alarm.

    Scoring by mean condition across the line does not work -- one station at
    eight sigma barely moves an average over forty-two, so the "quiet" baseline
    landed on a window that still had a station alarming. Counting stations is
    what the screen shows, so it is what the bookmark should minimise.
    """
    hi = min(before - 900, s.t_min + 5 * 3600) if before else s.t_min + 5 * 3600
    day = s.ev[(s.ev.depart_ts >= s.t_min) & (s.ev.depart_ts <= hi)]
    if day.empty:
        return s.t_min + 45 * 60
    d = day.assign(b=((day.depart_ts - s.t_min) // 900).astype(int))
    # Same peak criterion the station tiles are graded on, so the bookmark and
    # the screen agree about what "quiet" means.
    per = d.groupby(["b", "station_idx"])["station_z_eff"].max().reset_index()
    per["hot"] = per.station_z_eff >= 6
    score = per.groupby("b").agg(alarms=("hot", "sum"), z=("station_z_eff", "mean"))
    n = d.groupby("b").size()
    score = score[n.reindex(score.index).fillna(0) > 300]
    if score.empty:
        return s.t_min + 45 * 60
    best = score.sort_values(["alarms", "z"]).index[0]
    return float(s.t_min + int(best) * 900 + 450)


# ---------------------------------------------------------------------------
# meta
# ---------------------------------------------------------------------------
@app.get("/api/meta")
def meta():
    s = store()
    v = s.validation
    stations = [dict(
        idx=st.idx, code=st.code, name=st.name, zone=st.zone, tier=st.tier,
        manual=st.manual, gate=st.gate, creates=list(st.creates or ()),
        nominal_s=round(st.cycle_s * C.CYCLE_SCALE, 1),
        buffer_out=st.buffer_out, transit_s=st.transit_s, note=st.label,
        channels=spc.available_channels(st),
    ) for st in C.STATIONS]

    # Demo bookmarks, derived from the scripted incidents rather than hand-typed,
    # so they stay correct if the scenario is regenerated with another seed.
    # Pick a genuinely quiet moment rather than a hard-coded hour: with faults
    # seeded across 42 stations, an arbitrary "normal operation" timestamp
    # frequently lands on somebody else's incident.
    lat = {d["station"]: d for d in v["spc"]["detection_latency"]}
    first_onset = min(x["onset_ts"] for x in v["spc"]["detection_latency"])
    quiet = _quietest_window(s, before=first_onset)
    marks = [dict(id="normal", label="Baseline — before the fault", t=quiet,
                  blurb="A 42-station line always has something worth watching. "
                        "This is the quietest the day gets: the state the rest of "
                        "the sequence departs from.")]
    for ep in C.HERO_EPISODES:
        on = lat[ep.station]["onset_ts"]
        det = lat[ep.station]["detected_after_min"]
        marks.append(dict(id=f"{ep.station}-onset", label=f"{ep.station} drift begins",
                          t=on + 120, station=ep.station,
                          blurb=f"{ep.title}. Nothing visible on an MES screen yet."))
        if det:
            marks.append(dict(id=f"{ep.station}-detect", label=f"{ep.station} flagged by the twin",
                              t=on + det * 60 + 300, station=ep.station,
                              blurb=f"Detected {det:.0f} min after onset. It opens as a "
                                    "MONITOR: the evidence is real but not yet strong "
                                    "enough to justify stopping work."))
            # The escalation is worth its own beat. Severity is computed from what
            # has happened by the replay clock, not from the episode's eventual
            # peak, so a card genuinely strengthens as evidence accumulates.
            marks.append(dict(id=f"{ep.station}-escalate", label=f"{ep.station} escalated",
                              t=on + det * 60 + 1200, station=ep.station,
                              blurb="Now the top IMMEDIATE action on the line. Nothing "
                                    "was added but 15 more minutes of evidence."))
    marks.append(dict(id="confirm", label="Failures confirmed at ASSY-27",
                      t=lat["BODY-08"]["onset_ts"] + 5 * 3600, station="ASSY-27",
                      blurb="The torque audit starts rejecting bodies built ~100 min ago."))
    marks.append(dict(id="dark", label="Sensor-poor station drifting",
                      t=lat["BODY-14"]["onset_ts"] + 3.5 * 3600, station="BODY-14",
                      blurb="BODY-14 has no torque or vibration telemetry."))
    marks.sort(key=lambda m: m["t"])

    return ok(dict(
        stations=stations, zones=C.ZONES, takt_s=C.TAKT_S,
        decision_station=C.DECISION_STATION,
        downstream_gates=C.DOWNSTREAM_GATES,
        tier_confidence=C.TIER_CONFIDENCE,
        coverage=v["line"]["coverage"],
        clock=dict(min=s.t_min, max=s.t_max, day=C.DEMO_DAY,
                   date=str(pd.to_datetime(s.day_start, unit="s").date())),
        bookmarks=marks,
        virtual_sensor=v["virtual_sensor"],
        model=dict(name=v["model"]["selected_model"],
                   test=v["model"]["test"], reachable=v["model"]["test_reachable"]),
    ))


# ---------------------------------------------------------------------------
# live line state
# ---------------------------------------------------------------------------
def _station_state(s: Store, now: float) -> list:
    out = []
    for st in C.STATIONS:
        g = s.by_station.get(st.idx)
        if g is None:
            continue
        seen = g[g.depart_ts <= now]
        if seen.empty:
            continue
        recent = seen.tail(40)
        last = seen.iloc[-1]
        z = float(recent["station_z_eff"].mean())
        # Status is graded on the recent *peak*, matching the threshold the
        # recommendation engine uses. Grading the tile on a 40-unit mean while
        # the card is graded on the peak leaves a station painted amber next to
        # an IMMEDIATE action naming it -- two parts of one screen disagreeing.
        peak = float(recent["station_z_eff"].max())
        status = ("alarm" if peak >= 6 and bool(last["drift"])
                  else "warn" if peak >= spc.ACTIONABLE_Z else "ok")
        out.append(dict(
            idx=st.idx, code=st.code, name=st.name, zone=st.zone, tier=st.tier,
            gate=st.gate, manual=st.manual,
            cycle_s=round(float(recent["cycle_time"].median()), 1),
            nominal_s=round(st.cycle_s * C.CYCLE_SCALE, 1),
            station_z=round(z, 2),
            peak_z=round(peak, 2),
            measured_z=round(float(recent["station_z"].mean()), 2),
            virtual_z=round(float(recent["virtual_z"].mean()), 2),
            inferred=bool(float(recent["inference_weight"].mean()) > 0.05),
            flow_z=round(float(recent["flow_z"].mean()), 2),
            drift=bool(last["drift"]),
            data_confidence=round(float(recent["data_confidence"].mean()), 2),
            n_channels=int(last["n_channels"]),
            blocked_s=round(float(recent["blocked_s"].mean()), 1),
            starved_s=round(float(recent["starved_s"].mean()), 1),
            status=status,
            last_unit=str(last["unit_id"]),
        ))
    return out


@app.get("/api/state")
def state(t: float | None = Query(None)):
    s = store()
    now = _clock(t)
    stations = _station_state(s, now)
    pace = flow.station_pace(s.ev, now)
    fc = flow.forecast(pace)

    live_eps = s.episodes[(s.episodes.start_ts <= now)
                          & (s.episodes.end_ts >= now - 1800)]
    recs = recommend.build(s.ev[s.ev.depart_ts <= now], now, live_eps, pace, fc)

    # Units currently in the line, with the risk assigned at body exit.
    inline = s.ev[(s.ev.depart_ts <= now) & (s.ev.depart_ts >= now - 3 * 3600)]
    pos = inline.groupby("unit_id")["station_idx"].max()
    scored_ids = [u for u in pos.index if u in s.risk.index]
    at_risk = []
    if scored_ids:
        r = s.risk.loc[scored_ids, "risk"]
        top = r[pos.loc[scored_ids] < C.N_STATIONS].nlargest(12)
        for uid, risk in top.items():
            at_risk.append(dict(
                unit_id=uid, risk=round(float(risk), 4),
                position=int(pos.loc[uid]),
                station=C.STATION_BY_IDX[int(pos.loc[uid])].code,
                model=str(s.units.set_index("unit_id").loc[uid, "model"]),
                evidence=tracing.unit_evidence(s.ev, uid, top_k=3)))

    alarms = [x for x in stations if x["status"] == "alarm"]
    warns = [x for x in stations if x["status"] == "warn"]
    return ok(dict(
        now=now, iso=str(pd.to_datetime(now, unit="s")),
        stations=stations,
        summary=dict(
            in_alarm=len(alarms), in_warning=len(warns),
            constraint=fc["current"]["station_code"] if fc["current"] else None,
            constraint_capacity=fc["current"]["capacity_uph"] if fc["current"] else None,
            takt_capacity=fc.get("takt_capacity_uph"),
            units_built_today=int((s.ev[(s.ev.station_idx == C.N_STATIONS)
                                        & (s.ev.depart_ts <= now)
                                        & (s.ev.depart_ts >= s.day_start)]).shape[0]),
            mean_risk=round(float(s.risk.loc[scored_ids, "risk"].mean()), 4) if scored_ids else None,
        ),
        forecast=fc,
        recommendations=recs,
        at_risk=at_risk,
        decisions=s.decisions[-30:],
    ))


# ---------------------------------------------------------------------------
# station drill-down
# ---------------------------------------------------------------------------
@app.get("/api/station/{code}")
def station(code: str, t: float | None = Query(None), window_h: float = 6.0):
    s = store()
    now = _clock(t)
    st = C.STATION_BY_CODE.get(code)
    if st is None:
        raise HTTPException(404, f"unknown station {code}")
    g = s.by_station.get(st.idx)
    seen = g[(g.depart_ts <= now) & (g.depart_ts >= now - window_h * 3600)]
    if seen.empty:
        raise HTTPException(404, "no data in window")

    chans = spc.available_channels(st)
    series = dict(
        ts=[float(x) for x in seen.depart_ts.values],
        station_z=[round(float(x), 3) for x in seen.station_z_eff.values],
        measured_z=[round(float(x), 3) for x in seen.station_z.values],
        ewma=[round(float(x), 3) for x in seen.station_ewma.values],
        drift=[bool(x) for x in seen.drift.values],
        cycle_time=[round(float(x), 2) for x in seen.cycle_time.values],
    )
    for ch in ("vibration", "torque", "temperature", "manual_flag"):
        if ch in seen.columns and seen[ch].notna().any():
            series[ch] = [None if not np.isfinite(x) else round(float(x), 3)
                          for x in seen[ch].values]
    for ch in chans:
        col = "z_" + ch
        if col in seen.columns:
            series[col] = [None if not np.isfinite(x) else round(float(x), 3)
                           for x in seen[col].values]

    epis = s.episodes[(s.episodes.station_idx == st.idx)
                      & (s.episodes.start_ts <= now)
                      & (s.episodes.end_ts >= now - window_h * 3600)]
    return ok(dict(
        station=dict(idx=st.idx, code=st.code, name=st.name, zone=st.zone,
                     tier=st.tier, manual=st.manual, gate=st.gate,
                     creates=list(st.creates or ()), note=st.label,
                     nominal_s=round(st.cycle_s * C.CYCLE_SCALE, 1)),
        channels=[dict(key=c, label=spc.CHANNEL_LABEL.get(c, c),
                       weight=spc.CHANNEL_SPEC[c]["weight"],
                       role=spc.CHANNEL_SPEC[c]["score"]) for c in chans],
        missing_channels=[c for c in ("vibration", "torque_scatter", "temp_adj")
                          if c not in chans],
        coverage=dict(tier=st.tier, confidence=C.TIER_CONFIDENCE[st.tier],
                      n_channels=len(chans),
                      inferred=bool(float(seen["inference_weight"].mean()) > 0.05),
                      inference_weight=round(float(seen["inference_weight"].mean()), 3),
                      virtual_p=round(float(seen["virtual_p"].tail(30).mean()), 3),
                      data_confidence=round(float(seen["data_confidence"].mean()), 3)),
        series=series,
        episodes=[dict(start_ts=float(r.start_ts), end_ts=float(r.end_ts),
                       n_units=int(r.n_units), peak_z=round(float(r.peak_z), 2),
                       severity=str(r.severity), actionable=bool(r.actionable))
                  for _, r in epis.iterrows()],
        drift_limit=spc.DRIFT_LIMIT, actionable_z=spc.ACTIONABLE_Z,
        now=now,
    ))


# ---------------------------------------------------------------------------
# traceback
# ---------------------------------------------------------------------------
@app.get("/api/trace")
def trace(gate: int = Query(27), t: float | None = Query(None),
          window_h: float = 5.0):
    s = store()
    now = _clock(t)
    res = tracing.trace(s.ev, gate, now, window_h=window_h)
    top = res["suspects"][0]["station_idx"] if res["suspects"] else None
    cont = tracing.containment(s.ev, top, now) if top else None

    # Recent rejects at this gate, so the list is concrete rather than a count.
    at = s.ev[(s.ev.station_idx == gate) & (s.ev.depart_ts <= now)
              & (s.ev.depart_ts >= now - window_h * 3600)]
    fails = at[at.gate_fail > 0].tail(20)
    rejects = []
    for _, r in fails.iterrows():
        d = s.defects[(s.defects.unit_id == r.unit_id)
                      & (s.defects.detect_idx == gate)]
        rejects.append(dict(
            unit_id=str(r.unit_id), ts=float(r.depart_ts),
            modes=sorted(set(d["mode"].tolist())),
            true_origin=[C.STATION_BY_IDX[int(i)].code for i in d["origin_idx"].unique()],
            lag_min=round(float(d["detect_lag_min"].max()), 1) if len(d) else None,
        ))
    return ok(dict(trace=res, containment=cont, rejects=rejects, now=now,
                   gates=[dict(idx=st.idx, code=st.code, gate=st.gate,
                               catches=list(st.gate_catches))
                          for st in C.STATIONS if st.gate]))


# ---------------------------------------------------------------------------
# plant + business + validation
# ---------------------------------------------------------------------------
@app.get("/api/plant")
def plant(t: float | None = Query(None)):
    s = store()
    now = _clock(t)
    hist = s.ev[s.ev.depart_ts <= now]
    eps = s.episodes[s.episodes.start_ts <= now]

    top_stations = (eps[eps.actionable].groupby("station_code")
                    .agg(alerts=("n_units", "size"), units=("n_units", "sum"),
                         peak=("peak_z", "max"))
                    .sort_values("alerts", ascending=False).head(10).reset_index())
    tiers = {st.code: st.tier for st in C.STATIONS}
    top = [dict(station=r.station_code, tier=tiers[r.station_code],
                alerts=int(r.alerts), units_exposed=int(r.units),
                peak_z=round(float(r.peak), 1)) for _, r in top_stations.iterrows()]

    # Daily trend: gate rejects and mean risk.
    eol = hist[hist.station_idx == C.N_STATIONS].copy()
    eol["day"] = ((eol.depart_ts - pd.Timestamp(C.DAY_ZERO).value / 1e9) // 86400).astype(int)
    gate_trend = (eol.groupby("day")["gate_fail"].agg(["mean", "size"])
                  .reset_index().tail(10))
    risk_by_day = s.risk.copy()
    risk_trend = (risk_by_day.groupby("day")["risk"].mean().reset_index().tail(10))

    cov = {}
    for tier in ("FULL", "PARTIAL", "DARK"):
        idxs = [st.idx for st in C.STATIONS if st.tier == tier]
        sub = hist[hist.station_idx.isin(idxs)]
        cov[tier] = dict(
            stations=len(idxs),
            mean_confidence=round(float(sub["data_confidence"].mean()), 3) if len(sub) else 0,
            alerts=int(eps[eps.station_idx.isin(idxs) & eps.actionable].shape[0]))

    return ok(dict(
        now=now,
        top_stations=top,
        coverage=cov,
        bottleneck_frequency=[
            dict(station=k, minutes=int(v)) for k, v in
            (eps[eps.peak_flow_z >= 3].groupby("station_code")["n_units"].sum()
             .sort_values(ascending=False).head(8).items())],
        gate_trend=[dict(day=int(r.day), reject_rate=round(float(r["mean"]), 4),
                         units=int(r["size"])) for _, r in gate_trend.iterrows()],
        risk_trend=[dict(day=int(r.day), mean_risk=round(float(r.risk), 4))
                    for _, r in risk_trend.iterrows()],
        alerts_per_shift=s.validation["spc"]["actionable_per_shift"],
        detection_latency=s.validation["spc"]["detection_latency"],
    ))


@app.get("/api/business")
def business(lines: int = Query(1, ge=1, le=12)):
    s = store()
    v = s.validation
    from twin import economics
    roi = economics.roi(v["model"], forecasts_hit=v["forecast"]["hits"],
                        window_days=C.TEST_DAYS[1] - C.TEST_DAYS[0],
                        probe_span_days=v["forecast"]["span_days"],
                        units_at_risk_per_event=v["forecast"]["median_units_at_risk"],
                        lead_minutes=v["forecast"]["median_lead_min"] or 45.0,
                        n_lines=lines)
    return ok(dict(roi=roi, instrumentation=v["instrumentation"][:8],
                   forecast=v["forecast"]))


@app.get("/api/validation")
def validation():
    return ok(store().validation)


class Decision(BaseModel):
    rec_id: str
    station: str
    action: str
    verdict: str          # accepted | dismissed
    note: str = ""
    t: float | None = None


@app.post("/api/decision")
def decision(d: Decision):
    """Human-in-the-loop ledger.

    Nothing the twin proposes executes itself. Recording what a supervisor did
    with each recommendation is what turns the false-alarm rate from a claim into
    a measurement, and it is the input a re-tuning pass would need.
    """
    s = store()
    rec = d.model_dump()
    rec["logged_at"] = float(_clock(d.t))
    s.decisions.append(rec)
    accepted = sum(1 for x in s.decisions if x["verdict"] == "accepted")
    return ok(dict(ok=True, total=len(s.decisions), accepted=accepted,
                   acceptance_rate=round(accepted / max(len(s.decisions), 1), 3)))


@app.get("/")
def index():
    """Serve the shell with cache-busted asset URLs.

    Browsers hold on to `app.js` hard enough that an edited dashboard can render
    the previous build with no error and no clue -- which cost real confusion
    during review, and would be worse mid-demo. Stamping the asset URLs with the
    files' modification times makes a stale asset impossible rather than
    unlikely.
    """
    html = (STATIC / "index.html").read_text()
    for asset in ("app.css", "app.js"):
        stamp = int((STATIC / asset).stat().st_mtime)
        html = html.replace(f"/static/{asset}", f"/static/{asset}?v={stamp}")
    return HTMLResponse(html)


app.mount("/static", StaticFiles(directory=STATIC), name="static")
