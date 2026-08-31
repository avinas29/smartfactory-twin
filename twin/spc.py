"""
Statistical process control — the twin's eyes.

Two rules govern this module.

**Baselines are fitted, then frozen.** Control limits come from a qualification
window at the start of the record and are then held. This is deliberate. A
continuously self-updating baseline is the classic way to build a drift detector
that cannot detect drift: a fault that holds for six hours sits inside any
trailing window short enough to be responsive, and the limits quietly re-centre
on the fault until it reads as normal. Real SPC freezes limits and re-qualifies
under change control; so does this. (`refit_days` documents the cadence.)

**The score the operator sees is the score the model eats.** `station_z` is
computed once, here, and flows to both the dashboard and the defect-risk model.
There is no separate offline definition of "anomalous" behind the UI.
"""
from __future__ import annotations

import json

import numpy as np
import pandas as pd

from twin import config as C

BASELINE_DAYS = (0, 3)   # qualification window: the twin's "known-good" period
REFIT_DAYS = 7           # documented re-qualification cadence in production
MIN_HISTORY = 150        # a station needs this many baseline units to be scored
EWMA_ALPHA = 0.14        # drift detector smoothing
DRIFT_LIMIT = 3.0        # EWMA control limit, in robust sigma
RESET_LIMIT = 1.3        # alarm clears only below this -- see hysteresis note
RUN_RULE_N = 10          # consecutive points above RUN_RULE_Z that also count as drift
RUN_RULE_Z = 1.6         # a run rule at 1.0 sigma fires constantly: station_z is
                         # autocorrelated, so healthy stations produce long mild runs

# The twin keeps two separate scores, because the line fails in two ways and the
# evidence for each is different.
#
#   CONDITION  -- is this station degrading?  Feeds defect risk and maintenance.
#   FLOW       -- is this station constraining the line?  Feeds the bottleneck view.
#
# Mixing them was a real failure mode during development: blocked/starved seconds
# are mostly zero with occasional bursts, so on a quality chart they saturate on
# healthy data (4% of units above 4 sigma) while contributing nothing at all on
# genuinely faulty ones (median z of 0). They are strong flow evidence and pure
# noise as condition evidence. Separating them cut false alarms by an order of
# magnitude without costing any detection.
CHANNEL_SPEC = {
    "cycle_norm":     dict(sided="high", weight=1.00, score="both"),
    "vibration":      dict(sided="high", weight=1.30, score="condition"),
    "torque_scatter": dict(sided="high", weight=1.20, score="condition"),
    "temp_adj":       dict(sided="abs",  weight=0.70, score="condition"),
    "manual_rate":    dict(sided="high", weight=1.15, score="condition"),
    "blocked_sm":     dict(sided="high", weight=1.00, score="flow"),
    "starved_sm":     dict(sided="high", weight=0.80, score="flow"),
}

def _in_score(ch: str, which: str) -> bool:
    s = CHANNEL_SPEC[ch]["score"]
    return s == which or s == "both"

CHANNEL_LABEL = {
    "cycle_norm": "Cycle time (model-normalised)",
    "vibration": "Vibration RMS",
    "torque_scatter": "Torque scatter (25-unit σ)",
    "temp_adj": "Temperature (ambient-adjusted)",
    "manual_rate": "Operator checklist flag rate",
    "blocked_sm": "Blocked seconds",
    "starved_sm": "Starved seconds",
}


def available_channels(st: C.Station) -> list[str]:
    """What this station can actually produce, given its instrumentation."""
    ch = ["cycle_norm", "blocked_sm", "starved_sm"]   # from MES scans: always there
    if st.tier == "FULL":
        if st.has_vibration:
            ch.append("vibration")
        if st.has_torque:
            ch.append("torque_scatter")
    if st.tier in ("FULL", "PARTIAL") and st.has_temp:
        ch.append("temp_adj")
    if st.manual:
        ch.append("manual_rate")
    return ch


TRIM_PASSES = 2
TRIM_SIGMA = 3.5
TRIM_FLOOR = 0.5   # limits may never shrink below half the untrimmed robust scale


def _scale_once(x: np.ndarray, robust_only: bool = False) -> tuple[float, float]:
    """Centre and scale. `robust_only` uses the IQR alone -- see _robust_scale."""
    med = float(np.median(x))
    iqr = float(np.percentile(x, 75) - np.percentile(x, 25))
    if robust_only:
        return med, max(iqr / 1.349, 1e-6)
    sd = float(np.std(x))
    # The p90 term is what keeps skewed, mostly-zero channels honest: their IQR
    # can be exactly 0 for long stretches, and dividing by that turns ordinary
    # bursts into 12-sigma events.
    upper = float(np.percentile(x, 90) - med) / 1.282
    sigma = max(iqr / 1.349, 0.60 * sd, upper, 0.01 * abs(med), 1e-6)
    return med, sigma


def _robust_scale(x: np.ndarray) -> tuple[float, float]:
    """Median and sigma for a channel, estimated by iterative trimming.

    Phase-I control limits have to be fitted on in-control data, and no real
    qualification window is guaranteed clean -- a station can be degrading during
    the very days you chose to learn its normal behaviour. Here that happened on
    BODY-08: a background fault inside the window pushed the fitted vibration
    sigma to 1.26 against a true in-control 0.61, and the eventual demo fault
    scored 2 sigma instead of 6. It was invisible because the limits had already
    swallowed a fault.

    So limits are re-estimated with points beyond three sigma removed, repeated a
    few times -- the standard Phase-I procedure for screening assignable causes
    out of the baseline. Note that the median/IQR alone did not save us: the
    `0.60 * sd` floor is not robust, and it was the term the contamination
    inflated.
    """
    x = x[np.isfinite(x)]
    if len(x) < MIN_HISTORY:
        return float("nan"), float("nan")
    # Seed the trim from the IQR alone. The floors in the full estimator exist to
    # stop quantised channels dividing by zero, but on a contaminated window they
    # do the opposite: the `0.60 * sd` term absorbs the excursion, widens the trim
    # band past it, and the contamination survives every pass. The IQR is
    # unaffected by a minority of extreme points, so it is the right thing to
    # measure the window *with* before deciding what to throw out of it.
    med, sigma0 = _scale_once(x, robust_only=True)

    # A channel whose middle 50% is a single value has no robust scale to trim
    # against: the seed collapses to the epsilon floor, the trim band closes to
    # nothing, and every non-zero reading is thrown away as an outlier. That is
    # exactly the shape of blocked-seconds and checklist flag rates -- mostly
    # zero with occasional bursts -- and it drove sigma to 1e-6, turning ordinary
    # bursts into million-sigma events. Where the IQR is degenerate, skip the
    # trim entirely and let the floors in the full estimator do the work.
    if sigma0 <= 1e-3 * (abs(med) + 1.0):
        return _scale_once(x)

    sigma = sigma0
    for _ in range(TRIM_PASSES):
        keep = np.abs(x - med) <= TRIM_SIGMA * sigma
        if keep.sum() < MIN_HISTORY or keep.all():
            break
        x = x[keep]
        med, sigma = _scale_once(x, robust_only=True)

    # Trimming to convergence is its own failure. Each pass shrinks sigma, which
    # trims more, which shrinks it further: on BODY-08 that ran the fitted
    # vibration sigma down to 0.13 against a true in-control 0.61, leaving limits
    # so tight that ordinary variation tripped them and alerts tripled. Common-
    # cause variation on a real station includes mild condition drift, not just
    # instrument noise, so the trimmed estimate is floored against the untrimmed
    # robust one.
    med_f, sigma_f = _scale_once(x)
    return med_f, max(sigma_f, TRIM_FLOOR * sigma0)


# SPC subgroup sizes. Charting individual cycles is a mistake here: about 1.2%
# of cycles carry a micro-stop, and on a one-sided chart every one of those is a
# 10-sigma point. Subgrouping is the textbook answer -- a sustained shift still
# moves the subgroup statistic, an isolated stoppage does not.
SUBGROUP = {"cycle_norm": 9, "vibration": 5, "temp_adj": 5}


def prepare_channels(events: pd.DataFrame, units: pd.DataFrame,
                     ambient_beta: dict | None = None) -> pd.DataFrame:
    """Derive the seven scoreable channels from raw station events.

    `ambient_beta` maps station_idx -> the station's fitted sensitivity to plant
    ambient temperature. Passing None leaves temperature uncorrected; the fitted
    values come out of `fit_ambient_beta` on the qualification window.
    """
    u = units.set_index("unit_id")
    ev = events.sort_values(["station_idx", "depart_ts"]).copy()
    ev["cycle_norm"] = ev["cycle_time"] / ev["unit_id"].map(u["work_mult"]).values
    ev["ambient_c"] = ev["unit_id"].map(u["ambient_c"]).values

    parts = []
    for idx, g in ev.groupby("station_idx", sort=True):
        g = g.copy()
        beta = (ambient_beta or {}).get(int(idx), 0.0)
        g["temp_adj"] = g["temperature"] - beta * g["ambient_c"]
        g["torque_scatter"] = g["torque"].rolling(25, min_periods=8).std()
        g["manual_rate"] = g["manual_flag"].rolling(40, min_periods=12).mean()
        g["blocked_sm"] = g["blocked_s"].rolling(30, min_periods=10).mean()
        g["starved_sm"] = g["starved_s"].rolling(30, min_periods=10).mean()
        for ch, n in SUBGROUP.items():
            if ch == "cycle_norm":
                g[ch] = g[ch].rolling(n, min_periods=3).median()
            else:
                g[ch] = g[ch].rolling(n, min_periods=2).mean()
        parts.append(g)
    return pd.concat(parts)


def fit_ambient_beta(events: pd.DataFrame, units: pd.DataFrame) -> dict:
    """Least-squares sensitivity of each station's temperature to plant ambient.

    Fitted on the qualification window only. A hand-assumed coefficient of 1.0
    would over-correct: an oven barely follows ambient, a body-shop weld cell
    partly does, and over-subtracting injects a diurnal swing that was not there.
    """
    day = units.set_index("unit_id")["day"]
    amb = units.set_index("unit_id")["ambient_c"]
    ev = events.copy()
    ev["_day"] = ev["unit_id"].map(day).values
    ev["_amb"] = ev["unit_id"].map(amb).values
    win = ev[(ev["_day"] >= BASELINE_DAYS[0]) & (ev["_day"] < BASELINE_DAYS[1])]
    out = {}
    for idx, g in win.groupby("station_idx", sort=True):
        m = g["temperature"].notna() & g["_amb"].notna()
        if m.sum() < MIN_HISTORY:
            out[int(idx)] = 0.0
            continue
        x, y = g.loc[m, "_amb"].values, g.loc[m, "temperature"].values
        vx = x.var()
        out[int(idx)] = float(np.cov(x, y)[0, 1] / vx) if vx > 1e-9 else 0.0
    return out


Z_CLIP = 8.0


def _channel_z(g: pd.DataFrame, chans: list[str], base: dict) -> None:
    """Write per-channel z columns onto g, in place."""
    for ch in chans:
        spec = CHANNEL_SPEC[ch]
        med, sigma = base[ch]
        if not np.isfinite(sigma):
            g["z_" + ch] = np.nan
            continue
        z = (g[ch].values - med) / sigma
        z = np.abs(z) if spec["sided"] == "abs" else np.clip(z, 0, None)
        g["z_" + ch] = np.clip(z, 0, Z_CLIP)


def _composite(g: pd.DataFrame, chans: list[str], which: str) -> tuple[np.ndarray, np.ndarray]:
    """Weighted max/mean blend over the channels belonging to one score."""
    zs, ws = [], []
    for ch in chans:
        if not _in_score(ch, which) or ("z_" + ch) not in g:
            continue
        z = g["z_" + ch].values
        ok = np.isfinite(z)
        w = CHANNEL_SPEC[ch]["weight"]
        zs.append(np.where(ok, z, 0.0) * w)
        ws.append(np.where(ok, w, 0.0))
    if not zs:
        return np.zeros(len(g)), np.zeros(len(g))
    Z, W = np.vstack(zs), np.vstack(ws)
    wsum = W.sum(axis=0)
    mean_z = np.divide(Z.sum(axis=0), np.where(wsum > 0, wsum, 1), where=wsum > 0)
    # max over *weighted* contributions, so a low-trust channel can never drive
    # the score on its own
    max_z = np.where(wsum > 0, Z.max(axis=0), 0.0)
    return 0.60 * max_z + 0.40 * mean_z, (W > 0).sum(axis=0)


def fit_baselines(ev: pd.DataFrame, units: pd.DataFrame) -> dict:
    """Fit control limits on the qualification window only.

    Two passes: per-channel limits first, then the in-control distribution of the
    composite itself. The second pass matters because the raw composite's resting
    level depends on how many channels a station has -- a max over five draws is
    larger than a max over three -- and without it a well-instrumented station
    would look permanently worse than a dark one.
    """
    day = units.set_index("unit_id")["day"]
    ev = ev.copy()
    ev["_day"] = ev["unit_id"].map(day).values
    win = ev[(ev["_day"] >= BASELINE_DAYS[0]) & (ev["_day"] < BASELINE_DAYS[1])]

    out = {}
    for idx, g in win.groupby("station_idx", sort=True):
        st = C.STATION_BY_IDX[idx]
        chans = available_channels(st)
        base = {ch: _robust_scale(g[ch].values) for ch in chans}
        gg = g.copy()
        _channel_z(gg, chans, base)
        cond_raw, _ = _composite(gg, chans, "condition")
        flow_raw, _ = _composite(gg, chans, "flow")
        out[int(idx)] = dict(channels={k: list(v) for k, v in base.items()},
                             composite=list(_robust_scale(cond_raw)),
                             composite_flow=list(_robust_scale(flow_raw)),
                             n_baseline=int(len(g)))
    return out


def score(ev: pd.DataFrame, baselines: dict) -> pd.DataFrame:
    """Apply frozen limits to every station-visit. Adds z_*, station_z, drift."""
    parts = []
    for idx, g in ev.groupby("station_idx", sort=True):
        st = C.STATION_BY_IDX[idx]
        b = baselines[int(idx)]
        base = {k: tuple(v) for k, v in b["channels"].items()}
        g = g.copy()
        chans = list(base)
        _channel_z(g, chans, base)
        cond_raw, nch = _composite(g, chans, "condition")
        flow_raw, nflow = _composite(g, chans, "flow")
        cmed, csig = b["composite"]
        fmed, fsig = b["composite_flow"]
        g["station_z"] = np.clip((cond_raw - cmed) / csig, 0, Z_CLIP) if np.isfinite(csig) else 0.0
        g["flow_z"] = np.clip((flow_raw - fmed) / fsig, 0, Z_CLIP) if np.isfinite(fsig) else 0.0
        g["n_channels"] = nch
        g["sensor_tier"] = st.tier
        g["station_ewma"] = pd.Series(g["station_z"]).ewm(alpha=EWMA_ALPHA, adjust=False).mean().values
        run = (g["station_z"] > RUN_RULE_Z).astype(int)
        run_len = run.groupby((run != run.shift()).cumsum()).cumsum()
        trip = ((g["station_ewma"] > DRIFT_LIMIT) | (run_len >= RUN_RULE_N)).values
        g["drift"] = _hysteresis(trip, g["station_ewma"].values)
        parts.append(g)
    res = pd.concat(parts).sort_values(["unit_row", "station_idx"])
    return res


def compute_station_signals(events: pd.DataFrame, units: pd.DataFrame):
    """Convenience: fit ambient -> prepare -> fit limits -> score.

    Returns (scored_events, fit) where `fit` carries everything needed to score
    live data later, exactly as the running twin does.
    """
    beta = fit_ambient_beta(events, units)
    prepped = prepare_channels(events, units, beta)
    baselines = fit_baselines(prepped, units)
    fit = dict(baselines=baselines, ambient_beta=beta)
    return score(prepped, baselines), fit


def _hysteresis(trip: np.ndarray, ewma: np.ndarray) -> np.ndarray:
    """Latch an alarm on, and clear it only once the process is properly back.

    Without this a single fault fragments into dozens of alerts: the EWMA
    dithers around the control limit for hours, and every crossing looks like a
    fresh incident. A supervisor reading twenty-five alerts for one worn spindle
    stops reading alerts. Enter on the trip condition, leave only below
    RESET_LIMIT -- the standard alarm deadband.
    """
    out = np.zeros(len(trip), dtype=bool)
    on = False
    for i in range(len(trip)):
        if on:
            if ewma[i] < RESET_LIMIT:
                on = False
        elif trip[i]:
            on = True
        out[i] = on
    return out


MERGE_GAP = 40           # visits; alarms this close on one station are one incident
MERGE_GAP_S = 1200       # ...and only within 20 min of clock time, so the
                         # 30-minute mid-shift break always ends an incident
ACTIONABLE_Z = 3.5       # severity bar for an alert a supervisor is asked to act on
ACTIONABLE_MEAN_Z = 1.5  # ...sustained, not one spike inside a quiet window
ACTIONABLE_UNITS = 25    # ...and persisting at least this long


def drift_episodes(ev: pd.DataFrame, min_units: int = 12,
                   merge_gap: int = MERGE_GAP) -> pd.DataFrame:
    """Collapse the per-unit drift flag into incidents.

    Each row reads "station X was in drift from t0 to t1; N units passed
    through" -- which is exactly the containment list the traceback needs.

    Two passes. First contiguous runs, then a coalescing pass: a degrading
    station does not alarm in one clean block, it dithers, and a supervisor
    shown twenty-seven alerts for one drifting station has been shown noise.
    `severity` then grades what survives, so the UI can rank rather than dump.
    """
    rows = []
    for idx, g in ev.sort_values(["station_idx", "depart_ts"]).groupby("station_idx"):
        d = g["drift"].fillna(False).values.astype(bool)
        if not d.any():
            continue
        change = np.flatnonzero(np.diff(d.astype(int)) != 0) + 1
        bounds = np.concatenate([[0], change, [len(d)]])
        spans = [(a, b) for a, b in zip(bounds[:-1], bounds[1:]) if d[a]]

        ts = g["depart_ts"].values

        # Split a run wherever the clock jumps. A latched alarm carries across a
        # shift break and an overnight stop, which produced single "incidents"
        # 19 hours long. The station really was still in alarm when the line
        # restarted, but that is a new shift's problem, reported as such.
        split = []
        for a, b in spans:
            start = a
            for i in range(a + 1, b):
                if ts[i] - ts[i - 1] > MERGE_GAP_S:
                    split.append((start, i))
                    start = i
            split.append((start, b))
        spans = split

        merged = []
        for a, b in spans:
            # Merge only across a real gap in units *and* in time. Without the
            # time test an alarm before a shift break and one after it become a
            # single "17-hour" incident, which is not something a supervisor can
            # act on or believe.
            close_in_units = merged and a - merged[-1][1] <= merge_gap
            close_in_time = merged and (ts[a] - ts[merged[-1][1] - 1]) <= MERGE_GAP_S
            if close_in_units and close_in_time:
                merged[-1] = (merged[-1][0], b)
            else:
                merged.append((a, b))

        for a, b in merged:
            if (b - a) < min_units:
                continue
            seg = g.iloc[a:b]
            peak = float(seg["station_z"].max())
            rows.append(dict(
                station_idx=int(idx),
                station_code=C.STATION_BY_IDX[idx].code,
                start_ts=float(seg["depart_ts"].iloc[0]),
                end_ts=float(seg["depart_ts"].iloc[-1]),
                n_units=int(b - a),
                peak_z=peak,
                mean_z=float(seg["station_z"].mean()),
                peak_flow_z=float(seg["flow_z"].max()),
                actionable=bool(peak >= ACTIONABLE_Z
                                and float(seg["station_z"].mean()) >= ACTIONABLE_MEAN_Z
                                and (b - a) >= ACTIONABLE_UNITS),
            ))
    df = pd.DataFrame(rows)
    if len(df):
        df["severity"] = np.where(df.peak_z >= 6, "high",
                          np.where(df.peak_z >= ACTIONABLE_Z, "medium", "low"))
    return df
