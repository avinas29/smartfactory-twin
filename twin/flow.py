"""
Flow model — the bottleneck forecast.

Round 1's first promise was that the twin runs the line forward rather than
reporting it. This module is that: a deterministic capacity roll-forward over the
next two hours, using each station's recent pace and the direction it is moving.

The model is deliberately thin. A full discrete-event simulation of 42 stations
would be more faithful and considerably less useful here -- the forecast that
matters is "which station becomes the constraint, and when", and that is decided
by capacity trends, not by queueing subtleties. What the twin adds over an MES
throughput screen is the derivative: an MES tells you the line is slow once WIP
has already piled up, which is the point at which the only remaining lever is
overtime.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from twin import config as C

RECENT_UNITS = 90        # window used for the current pace estimate
TREND_UNITS = 220        # window used for the trend
HORIZON_MIN = 120        # how far forward the twin projects
STEP_MIN = 10


def _robust_trend(y: np.ndarray) -> float:
    """Cycle-time drift per unit, via Theil-Sen. Median of pairwise slopes.

    Least squares would be pulled around by micro-stops, which are common and
    uninformative; a station is not becoming a constraint because one body
    jammed. Theil-Sen ignores them.
    """
    n = len(y)
    if n < 20:
        return 0.0
    idx = np.linspace(0, n - 1, min(n, 40)).astype(int)
    ys, xs = y[idx], idx.astype(float)
    slopes = []
    for i in range(len(xs) - 1):
        dx = xs[i + 1:] - xs[i]
        slopes.append((ys[i + 1:] - ys[i]) / np.where(dx == 0, 1, dx))
    return float(np.median(np.concatenate(slopes))) if slopes else 0.0


def station_pace(ev: pd.DataFrame, now_ts: float) -> pd.DataFrame:
    """Current cycle time, utilisation and trend for every station."""
    hist = ev[ev.depart_ts <= now_ts]
    rows = []
    for s in C.STATIONS:
        g = hist[hist.station_idx == s.idx].sort_values("depart_ts")
        if len(g) < 12:
            continue
        recent = g.tail(RECENT_UNITS)
        trend_win = g.tail(TREND_UNITS)
        cyc = float(recent["cycle_time"].median())
        slope = _robust_trend(trend_win["cycle_time"].rolling(15, min_periods=5)
                              .median().dropna().values)
        blocked = float(recent["blocked_s"].mean())
        starved = float(recent["starved_s"].mean())
        # Utilisation as busy-fraction of the time the station could have been
        # working. Dividing by wall-clock span instead looks reasonable and is
        # not: the window straddles shift breaks, so a station reads 18% busy
        # purely because the line was stopped for half an hour.
        # Clamp starvation before summing. A window that straddles a shift break
        # carries a single 30-minute idle gap that swamps everything else and
        # reports a busy station as 16% utilised.
        idle = float(recent["starved_s"].clip(upper=180).sum())
        busy = float(recent["cycle_time"].sum())
        span = busy + idle
        rows.append(dict(
            station_idx=s.idx, station_code=s.code, name=s.name, zone=s.zone,
            tier=s.tier, cycle_s=round(cyc, 2),
            nominal_s=round(s.cycle_s * C.CYCLE_SCALE, 2),
            capacity_uph=round(3600.0 / max(cyc, 1e-6), 1),
            utilisation=round(min(1.0, busy / span) if span > 0 else 0.0, 4),
            blocked_s=round(blocked, 2), starved_s=round(starved, 2),
            trend_s_per_unit=round(slope, 5),
            flow_z=round(float(recent["flow_z"].mean()), 2),
        ))
    return pd.DataFrame(rows)


def forecast(pace: pd.DataFrame, horizon_min: int = HORIZON_MIN) -> dict:
    """Roll capacity forward and report when the constraint changes hands."""
    if pace.empty:
        return dict(current=None, forecast=[], change=None)

    takt_capacity = 3600.0 / C.TAKT_S
    cur = pace.loc[pace["capacity_uph"].idxmin()]
    # cur["name"], not cur.name: on a Series the attribute is the index label,
    # which silently served the row number as the station name.
    current = dict(station_code=cur["station_code"], name=cur["name"],
                   capacity_uph=float(cur["capacity_uph"]),
                   cycle_s=float(cur["cycle_s"]), utilisation=float(cur["utilisation"]))

    units_per_min = min(pace["capacity_uph"].min(), takt_capacity) / 60.0
    steps = []
    for t in range(STEP_MIN, horizon_min + 1, STEP_MIN):
        units_ahead = units_per_min * t
        proj = pace["cycle_s"] + pace["trend_s_per_unit"] * units_ahead
        # a station cannot speed up indefinitely; drift downward is capped
        proj = np.maximum(proj, pace["nominal_s"] * 0.92)
        cap = 3600.0 / proj
        k = int(np.argmin(cap.values))
        steps.append(dict(minute=t, station_code=pace.station_code.iloc[k],
                          capacity_uph=round(float(cap.iloc[k]), 1),
                          cycle_s=round(float(proj.iloc[k]), 2),
                          below_takt=bool(cap.iloc[k] < takt_capacity)))

    change = None
    for st in steps:
        if st["station_code"] != current["station_code"]:
            change = dict(station_code=st["station_code"], in_minutes=st["minute"],
                          capacity_uph=st["capacity_uph"])
            break

    # First moment the projected line capacity drops below takt. If the line is
    # already there, say so plainly rather than reporting "in 10 minutes" -- the
    # advice is different when the loss has started than when it is coming.
    already = current["capacity_uph"] < takt_capacity
    constrained_at = 0 if already else next(
        (st["minute"] for st in steps if st["below_takt"]), None)
    worst = min(steps, key=lambda s: s["capacity_uph"]) if steps else None
    lost = 0.0
    if worst and worst["capacity_uph"] < takt_capacity:
        lost = (takt_capacity - worst["capacity_uph"]) * (horizon_min / 60.0)

    return dict(current=current, forecast=steps, change=change,
                already_constrained=bool(already),
                takt_capacity_uph=round(takt_capacity, 1),
                constrained_in_minutes=constrained_at,
                units_at_risk=round(lost, 1),
                horizon_min=horizon_min)


def rebalance_options(pace: pd.DataFrame, target: str) -> list:
    """Counter-moves for a named constraint, with the arithmetic shown.

    These are levers a supervisor already has -- they need no new hardware and no
    engineering change. The twin's contribution is knowing which station to point
    them at, and how long there is to decide.
    """
    row = pace[pace.station_code == target]
    if row.empty:
        return []
    row = row.iloc[0]
    takt_capacity = 3600.0 / C.TAKT_S
    gap = max(0.0, takt_capacity - row.capacity_uph)
    opts = []
    if gap > 0:
        need_s = 3600.0 / takt_capacity
        opts.append(dict(
            action="Add a floater operator to the station",
            detail=f"Cycle must fall from {row.cycle_s:.1f}s to {need_s:.1f}s to hold takt.",
            recovers_uph=round(gap, 1), effort="immediate"))
        opts.append(dict(
            action="Divert the highest-work-content model away for one hour",
            detail="EV-C carries ~14% more work content than the reference model; "
                   "re-sequencing it out of the next hour buys pace back.",
            recovers_uph=round(gap * 0.45, 1), effort="immediate"))
    opts.append(dict(
        action="Raise the upstream buffer target",
        detail=f"{row.blocked_s:.0f}s mean blocked and {row.starved_s:.0f}s mean "
               "starved at this station; a larger decoupler absorbs the variation.",
        recovers_uph=round(gap * 0.3, 1), effort="shift"))
    return opts
