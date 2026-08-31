"""
Virtual sensors for dark stations.

Round 1 claimed that an uninstrumented station still leaves a signature in data
the plant already has. This module is that claim, made testable.

On well-instrumented stations we can see both halves of the picture: the *rich*
evidence (vibration, torque scatter, thermal drift) and the *thin* evidence every
station produces regardless of its age -- cycle-time deviation from MES part
scans, blocking and starving against its neighbours, and the operator's checklist
where one exists. So learn the mapping

    thin evidence  ->  "the rich channels would be calling a fault"

on the stations that have both, then apply it to the stations that only have the
thin half. No new hardware: the inference is trained on the plant's own
instrumented population and transferred to its dark one.

Two things keep this honest.

*Held-out stations, not held-out rows.* The deployment question is whether the
mapping survives being pointed at a station the model has never seen. A random
row split lets it memorise each station's quirks and report a score it cannot
reproduce.

*The validated score becomes a confidence multiplier.* A dark station's inferred
condition is a worse estimate than a measured one, and the twin says so rather
than pretending a paper checklist is a vibration sensor.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.metrics import average_precision_score, roc_auc_score

from twin import config as C
from twin import spc

# What a dark station can always produce, plus what its neighbours reveal,
# plus static descriptors so the model knows what kind of station it is scoring.
THIN_FEATURES = [
    "z_cycle_norm", "z_manual_rate", "z_blocked_sm", "z_starved_sm",
    "up_blocked", "up_starved", "dn_blocked", "dn_starved",
    "cycle_ratio_up", "cycle_ratio_dn",
    "n_rich_channels", "zone_id", "is_manual",
]
# The channels a dark station is missing.
RICH_CHANNELS = ["z_vibration", "z_torque_scatter", "z_temp_adj"]
RICH_ALARM_Z = 3.0       # the level at which measured rich channels call a fault

ZONE_ID = {"BODY": 0, "PAINT": 1, "ASSY": 2}


def _add_station_context(df: pd.DataFrame) -> None:
    """Static station descriptors, added in place."""
    n_rich = {s.idx: float(sum([s.has_vibration and s.tier == "FULL",
                                s.has_torque and s.tier == "FULL",
                                s.has_temp and s.tier in ("FULL", "PARTIAL")]))
              for s in C.STATIONS}
    df["n_rich_channels"] = df["station_idx"].map(n_rich).astype(float)
    df["zone_id"] = df["station_idx"].map(
        {s.idx: float(ZONE_ID[s.zone]) for s in C.STATIONS}).astype(float)
    df["is_manual"] = df["station_idx"].map(
        {s.idx: float(s.manual) for s in C.STATIONS}).astype(float)


def _downstream_asof(ev: pd.DataFrame, cols: list[str]) -> pd.DataFrame:
    """Downstream-neighbour context, as of the moment the unit left this station.

    This one has to be a time join, not a shift across the station axis.

    Taking station s+1's row *for the same unit* looks natural and is a 50-second
    lookahead: that unit has not reached s+1 yet when it leaves s, and across the
    painted-body store it will not reach it for an hour. A live twin scoring a
    station now can only see what the next station has already done for *earlier*
    units. So for every departure from station s at time T, join the most recent
    reading at station s+1 with a departure at or before T.

    The distinction turned out to be nearly free: the lookahead version scored
    0.9307 held-out-station AUC and this one scores essentially the same, because
    the downstream features carry very little on their own (0.562 alone). Worth
    knowing, and worth not shipping.
    """
    frames = []
    for s in range(1, C.N_STATIONS):
        left = (ev.loc[ev.station_idx == s, ["unit_row", "depart_ts"]]
                .sort_values("depart_ts"))
        right = (ev.loc[ev.station_idx == s + 1, ["depart_ts"] + cols]
                 .sort_values("depart_ts")
                 .rename(columns={c: "dn_" + c for c in cols}))
        if left.empty or right.empty:
            continue
        m = pd.merge_asof(left, right, on="depart_ts", direction="backward",
                          allow_exact_matches=False)
        m["station_idx"] = s
        frames.append(m.drop(columns=["depart_ts"]))
    if not frames:
        return pd.DataFrame(columns=["unit_row", "station_idx"] + ["dn_" + c for c in cols])
    return pd.concat(frames, ignore_index=True)


def build_thin_frame(ev: pd.DataFrame) -> pd.DataFrame:
    """Assemble the thin-evidence feature frame, including neighbour context."""
    cols = ["unit_row", "station_idx", "depart_ts", "z_cycle_norm", "z_manual_rate",
            "z_blocked_sm", "z_starved_sm", "cycle_norm"]
    d = ev[[c for c in cols if c in ev.columns]].copy()
    for c in cols:
        if c not in d:
            d[c] = np.nan

    wide_b = d.pivot(index="unit_row", columns="station_idx", values="z_blocked_sm")
    wide_s = d.pivot(index="unit_row", columns="station_idx", values="z_starved_sm")
    wide_c = d.pivot(index="unit_row", columns="station_idx", values="cycle_norm")
    idx = sorted(wide_b.columns)

    # A station slowing down is visible from either side: it blocks the station
    # feeding it and starves the one it feeds. That is the whole trick.
    #
    # Upstream context is the same unit's own record at station s-1, which it
    # cleared about a minute ago -- already in the past, so a plain shift across
    # the station axis is causal here.
    derived = {
        "up_blocked": wide_b.shift(1, axis=1),
        "up_starved": wide_s.shift(1, axis=1),
        "cycle_ratio_up": wide_c / wide_c.shift(1, axis=1),
    }

    out = d.drop(columns=["cycle_norm"])
    for name, w in derived.items():
        m = (w.reindex(columns=idx).reset_index()
             .melt(id_vars="unit_row", var_name="station_idx", value_name=name))
        out = out.merge(m, on=["unit_row", "station_idx"], how="left")

    # Downstream context needs the time join -- see _downstream_asof.
    dn = _downstream_asof(d, ["z_blocked_sm", "z_starved_sm", "cycle_norm"])
    out = out.merge(dn, on=["unit_row", "station_idx"], how="left")
    out = out.rename(columns={"dn_z_blocked_sm": "dn_blocked",
                              "dn_z_starved_sm": "dn_starved"})
    own = out["unit_row"].map(d.set_index("unit_row")["cycle_norm"].groupby(level=0).first())
    out["cycle_ratio_dn"] = np.nan
    if "dn_cycle_norm" in out.columns:
        cyc = d.set_index(["unit_row", "station_idx"])["cycle_norm"]
        key = pd.MultiIndex.from_arrays([out["unit_row"], out["station_idx"]])
        out["cycle_ratio_dn"] = cyc.reindex(key).values / out["dn_cycle_norm"].values
        out = out.drop(columns=["dn_cycle_norm"])
    out = out.drop(columns=[c for c in ("depart_ts",) if c in out.columns])
    _add_station_context(out)
    return out


def _rich_alarm(ev: pd.DataFrame) -> np.ndarray:
    """Did the channels a dark station lacks indicate an abnormal condition?

    Framed as a label rather than a regression target on purpose. The rich score
    is a clipped max -- near zero almost always, occasionally large -- so squared
    error is dominated by a handful of extreme points, and R^2 came out negative
    even while the ranking was informative (measured: R^2 -0.03, correlation
    0.35). The operational question is binary anyway: is this station in a bad
    state right now?
    """
    present = [c for c in RICH_CHANNELS if c in ev.columns]
    if not present:
        return np.zeros(len(ev), dtype=int)
    return (ev[present].max(axis=1).fillna(0) >= RICH_ALARM_Z).values.astype(int)


def fit(ev: pd.DataFrame, units: pd.DataFrame, seed: int = 7):
    """Train thin -> rich-alarm on FULL stations, holding out whole stations."""
    thin = build_thin_frame(ev)
    thin["target"] = _rich_alarm(ev)
    thin["tier"] = thin["station_idx"].map({s.idx: s.tier for s in C.STATIONS})

    full_idx = [s.idx for s in C.STATIONS if s.tier == "FULL"]
    rng = np.random.default_rng(seed)
    holdout = set(int(x) for x in rng.choice(full_idx, size=max(4, len(full_idx) // 4),
                                             replace=False))
    train = thin[(thin.tier == "FULL") & (~thin.station_idx.isin(holdout))]
    test = thin[(thin.tier == "FULL") & (thin.station_idx.isin(holdout))]

    model = HistGradientBoostingClassifier(
        max_depth=5, max_iter=200, learning_rate=0.07, random_state=seed)
    model.fit(train[THIN_FEATURES].astype(float), train["target"].values)

    p = model.predict_proba(test[THIN_FEATURES].astype(float))[:, 1]
    y = test["target"].values
    auc = float(roc_auc_score(y, p)) if 0 < y.mean() < 1 else 0.5
    ap = float(average_precision_score(y, p)) if 0 < y.mean() < 1 else 0.0
    meta = dict(auc=round(auc, 4), ap=round(ap, 4),
                base_rate=round(float(y.mean()), 4),
                trust=round(max(0.0, min(1.0, (auc - 0.5) * 2)), 4),
                holdout_stations=sorted(holdout), n_train=int(len(train)),
                n_test=int(len(test)), features=THIN_FEATURES, alarm_z=RICH_ALARM_Z)
    return model, meta


def apply(ev: pd.DataFrame, model, meta: dict) -> pd.DataFrame:
    """Add the inferred condition estimate and a data-confidence column.

    `station_z_eff` is what the rest of the twin consumes. On a FULL station it
    is the measured score, untouched. On a PARTIAL or DARK station the measured
    score can be raised toward the inferred one -- but only in proportion to how
    far above chance the inference validated on held-out stations. A mapping that
    did not generalise cannot manufacture an alarm.
    """
    thin = build_thin_frame(ev)
    prob = model.predict_proba(thin[THIN_FEATURES].astype(float))[:, 1]

    out = ev.copy()
    key = thin[["unit_row", "station_idx"]].copy()
    key["virtual_p"] = prob
    out = out.merge(key, on=["unit_row", "station_idx"], how="left")
    out["virtual_p"] = out["virtual_p"].fillna(0.0)
    # express the probability on the same sigma scale the rest of the UI speaks
    out["virtual_z"] = out["virtual_p"] * spc.Z_CLIP

    tier = out["station_idx"].map({s.idx: s.tier for s in C.STATIONS})
    trust = float(meta.get("trust", 0.0))
    blend = tier.map({"FULL": 0.0, "PARTIAL": 0.45, "DARK": 0.75}).astype(float) * trust

    out["station_z_eff"] = (1 - blend) * out["station_z"] + blend * np.maximum(
        out["station_z"], out["virtual_z"])
    out["inference_weight"] = blend

    # Data confidence: instrumentation tier, discounted by how many channels
    # actually reported (a dead sensor lowers confidence even on a FULL station),
    # and lifted a little where the virtual sensor carries real information.
    tier_conf = tier.map(C.TIER_CONFIDENCE).astype(float)
    expected = out["station_idx"].map(
        {s.idx: max(1, len(spc.available_channels(s))) for s in C.STATIONS})
    reported = (out["n_channels"] / expected).clip(0, 1)
    out["data_confidence"] = (tier_conf * (0.55 + 0.45 * reported)
                              + blend * 0.12).clip(0.15, 1.0)
    return out
