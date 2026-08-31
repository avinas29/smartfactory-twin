"""
Feature engineering at the twin's decision point.

The twin scores a unit the moment it clears the body shop (station 14). That
choice does the leakage control structurally rather than by hand:

  * every feature describes something that happened at or before station 14
  * every label describes something that happens at station 24 or later

so there is no window in which a feature could have seen its own outcome. It is
also the operationally useful moment: a body-shop fault found at final assembly
is roughly 100 minutes and 90 vehicles too late, and station 14 is the last point
at which containment is still cheap.

Per-station scores are carried as their own columns rather than collapsed into a
single average. Different stations couple to different failure modes -- a torque
excursion at BODY-08 means something quite different downstream from a thermal
excursion in the paint ovens -- and averaging them away is exactly the
information the traceback later needs.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from twin import config as C

DECISION = C.DECISION_STATION

CONTEXT_FEATURES = [
    "complexity", "crew_id", "shift_id", "hours_into_shift", "units_since_break",
    "lot_incoming_index",
]
# The plant's FMEA already records which station can introduce which failure
# mode. Encoding it turns a diluted "was anything upstream odd" signal into
# "was anything odd at a station that can produce a fault this gate would catch".
# The max over all fourteen body stations is dominated by whichever station
# happened to be noisiest; these are not.
UPSTREAM_MODES = ["GEOM", "TORQUE", "FIT"]
MODE_FEATURES = ([f"max_z_mode_{m}" for m in UPSTREAM_MODES]
                 + [f"sum_z_mode_{m}" for m in UPSTREAM_MODES])

CHANNEL_MAX_FEATURES = [
    "max_z_vibration", "max_z_torque_scatter", "max_z_cycle_norm",
    "max_z_manual_rate", "max_z_temp_adj",
]
AGG_FEATURES = [
    "max_station_z", "mean_station_z", "sum_station_z", "n_stations_alarm",
    "n_stations_drift", "min_data_confidence", "mean_data_confidence",
    "n_dark_stations_alarm", "total_blocked_s", "total_starved_s",
    "total_cycle_dev", "n_manual_flags", "body_gate_fail",
]
STATION_FEATURES = [f"z_st{i:02d}" for i in range(1, DECISION + 1)]
FEATURES = (CONTEXT_FEATURES + CHANNEL_MAX_FEATURES + MODE_FEATURES
            + AGG_FEATURES + STATION_FEATURES)

# What the deployed model actually consumes.
#
# The full set above includes one column per upstream station. Those helped
# nothing and hurt measurably: with roughly 7% positives on a temporal split,
# the extra 14 sparse columns gave every model something to memorise. Dropping
# them lifted out-of-sample PR-AUC from 0.161 to 0.203, and on the subset of
# failures a body-exit model can actually reach, ROC-AUC went from 0.735 to
# 0.816. The per-station scores are still computed and still shown on the line
# view and used by the traceback -- they are simply not model inputs.
MODEL_FEATURES = [
    "sum_z_mode_TORQUE", "max_z_mode_TORQUE", "sum_z_mode_FIT", "max_z_mode_FIT",
    "sum_z_mode_GEOM", "sum_station_z", "n_stations_alarm",
    "max_z_torque_scatter", "max_z_vibration", "max_z_manual_rate",
    "max_z_cycle_norm", "max_z_temp_adj", "complexity", "lot_incoming_index",
    "crew_id", "shift_id", "body_gate_fail", "min_data_confidence",
    "total_cycle_dev", "n_manual_flags", "n_dark_stations_alarm",
]

FEATURE_LABEL = {
    "sum_z_mode_TORQUE": "Torque-mode station anomaly (summed)",
    "max_z_mode_TORQUE": "Worst torque-mode station anomaly",
    "sum_z_mode_FIT": "Fit-mode station anomaly (summed)",
    "max_z_mode_FIT": "Worst fit-mode station anomaly",
    "sum_z_mode_GEOM": "Geometry-mode station anomaly (summed)",
    "sum_station_z": "Total upstream anomaly",
    "n_stations_alarm": "Upstream stations in alarm",
    "max_z_torque_scatter": "Worst torque scatter",
    "max_z_vibration": "Worst vibration deviation",
    "max_z_manual_rate": "Worst checklist flag rate",
    "max_z_cycle_norm": "Worst cycle-time deviation",
    "max_z_temp_adj": "Worst thermal deviation",
    "complexity": "Model build complexity",
    "lot_incoming_index": "Incoming part-lot quality index",
    "crew_id": "Crew",
    "shift_id": "Shift",
    "body_gate_fail": "Failed the BODY-13 geometry gate",
    "min_data_confidence": "Lowest upstream data confidence",
    "total_cycle_dev": "Total cycle-time deviation",
    "n_manual_flags": "Operator checklist flags raised",
    "n_dark_stations_alarm": "Sensor-poor stations in alarm",
}

CREW_ID = {c: i for i, c in enumerate(C.CREWS)}


def build_unit_features(ev: pd.DataFrame, units: pd.DataFrame) -> pd.DataFrame:
    """One row per unit, describing everything the twin knows at body exit."""
    up = ev[ev.station_idx <= DECISION].copy()

    wide = up.pivot(index="unit_row", columns="station_idx", values="station_z_eff")
    wide.columns = [f"z_st{int(c):02d}" for c in wide.columns]

    nominal = {s.idx: s.cycle_s * C.CYCLE_SCALE for s in C.STATIONS}
    up["cycle_dev"] = up["cycle_time"] - up["station_idx"].map(nominal)
    dark = {s.idx: s.tier == "DARK" for s in C.STATIONS}
    up["is_dark"] = up["station_idx"].map(dark)

    g = up.groupby("unit_row")
    agg = pd.DataFrame({
        "max_station_z": g["station_z_eff"].max(),
        "mean_station_z": g["station_z_eff"].mean(),
        "sum_station_z": g["station_z_eff"].sum(),
        "n_stations_alarm": g["station_z_eff"].apply(lambda s: int((s > 3).sum())),
        "n_stations_drift": g["drift"].sum(),
        "min_data_confidence": g["data_confidence"].min(),
        "mean_data_confidence": g["data_confidence"].mean(),
        "total_blocked_s": g["blocked_s"].sum(),
        "total_starved_s": g["starved_s"].sum(),
        "total_cycle_dev": g["cycle_dev"].sum(),
        "n_manual_flags": g["manual_flag"].sum(),
    })
    agg["n_dark_stations_alarm"] = (up.assign(hit=up.is_dark & (up.station_z_eff > 3))
                                    .groupby("unit_row")["hit"].sum())

    for ch in ["z_vibration", "z_torque_scatter", "z_cycle_norm",
               "z_manual_rate", "z_temp_adj"]:
        agg["max_" + ch] = g[ch].max() if ch in up.columns else np.nan

    for mode in UPSTREAM_MODES:
        idxs = [s.idx for s in C.STATIONS
                if s.idx <= DECISION and mode in (s.creates or ())]
        sub = up[up.station_idx.isin(idxs)].groupby("unit_row")["station_z_eff"]
        agg[f"max_z_mode_{mode}"] = sub.max().reindex(agg.index)
        agg[f"sum_z_mode_{mode}"] = sub.sum().reindex(agg.index)

    # The in-line CMM at station 13 sits *before* the decision point, so its
    # verdict is an input, never a target.
    gate = ev[ev.station_idx == 13].set_index("unit_row")
    agg["body_gate_fail"] = gate["gate_fail"].reindex(agg.index).fillna(0).astype(float) \
        if "gate_fail" in gate.columns else 0.0

    u = units.set_index("unit_row") if "unit_row" in units.columns else units.copy()
    u = units.copy()
    u["unit_row"] = np.arange(len(u))
    u = u.set_index("unit_row")
    u["crew_id"] = u["crew"].map(CREW_ID)
    u["shift_id"] = u["shift"].map({"A": 0, "B": 1})
    # position in the shift, in units since the last line stop
    since = u.groupby(["day", "shift"]).cumcount()
    brk = (u["hours_into_shift"] > C.BREAK_AFTER_H).astype(int)
    u["units_since_break"] = np.where(brk == 1,
                                      since - u.groupby(["day", "shift"])["hours_into_shift"]
                                      .transform(lambda s: (s <= C.BREAK_AFTER_H).sum()),
                                      since)

    out = u[["unit_id", "day", "shift", "model", "lot_id", "launch_ts"] + CONTEXT_FEATURES] \
        .join(agg).join(wide)
    out["decision_ts"] = ev[ev.station_idx == DECISION].set_index("unit_row")["depart_ts"] \
        .reindex(out.index)
    for c in FEATURES:
        if c not in out.columns:
            out[c] = np.nan
    return out.reset_index()


def build_labels(units: pd.DataFrame, defects: pd.DataFrame) -> pd.DataFrame:
    """The target: does this unit get flagged at any gate downstream of the decision point.

    Also carries diagnostic columns the metrics report uses to separate what the
    model could in principle have predicted from what it could not: a defect
    created in final assembly is not knowable at body exit under any model, and
    reporting overall recall without that split would overstate the ceiling.
    """
    ds = defects[(~defects.escaped) & (defects.detect_idx.isin(C.DOWNSTREAM_GATES))]
    flagged = ds.groupby("unit_id").agg(
        n_downstream_defects=("mode", "size"),
        first_detect_idx=("detect_idx", "min"),
        first_detect_gate=("detect_gate", "first"),
        origin_min=("origin_idx", "min"),
        modes=("mode", lambda s: ",".join(sorted(set(s)))),
    )
    lab = pd.DataFrame(index=units["unit_id"])
    lab["y"] = lab.index.isin(flagged.index).astype(int)
    lab = lab.join(flagged)
    lab["body_attributable"] = (lab["origin_min"] <= C.DECISION_STATION).fillna(False)
    escaped = defects[defects.escaped].groupby("unit_id").size()
    lab["escaped_defects"] = escaped.reindex(lab.index).fillna(0).astype(int)
    return lab.reset_index()


def split_by_day(df: pd.DataFrame) -> dict:
    """Temporal split. Train strictly precedes validation, which precedes test."""
    return {
        "train": (df.day >= C.TRAIN_DAYS[0]) & (df.day < C.TRAIN_DAYS[1]),
        "val": (df.day >= C.VAL_DAYS[0]) & (df.day < C.VAL_DAYS[1]),
        "test": (df.day >= C.TEST_DAYS[0]) & (df.day < C.TEST_DAYS[1]),
    }
