"""
Build pipeline.

Runs the whole chain once and persists what the dashboard needs:

    generate -> SPC baselines -> virtual sensors -> features -> model
             -> drift episodes -> validation report -> artifacts

Run it directly to rebuild everything and print the metrics:

    python -m twin.pipeline

Everything downstream of `generate` is what would run against a real MES feed;
only `generate` is synthetic. The split is deliberate so the same code path is
exercised in the demo and in a pilot.
"""
from __future__ import annotations

import argparse
import json
import time

import joblib
import numpy as np
import pandas as pd

from twin import config as C
from twin import economics, features as F, flow, model as M, spc, tracing
from twin import virtual_sensor as vs
from twin.generate import generate

# Columns the dashboard actually needs. The full event table is ~1M rows wide
# enough to cost a gigabyte; the app only ever reads these.
# Simulator ground truth. Kept in the full record for tests and validation, and
# stripped from the file the dashboard loads -- the serving path should not be
# able to read the answer key even by accident.
ORACLE_COLS = ["oracle_condition", "oracle_flow"]

KEEP = [
    "unit_id", "unit_row", "station_idx", "station_code", "depart_ts", "arrive_ts",
    "cycle_time", "blocked_s", "starved_s", "torque", "vibration", "temperature",
    "manual_flag", "gate_fail", "station_z", "station_z_eff", "flow_z",
    "station_ewma", "drift", "n_channels", "data_confidence", "virtual_p",
    "virtual_z", "inference_weight", "oracle_condition", "oracle_flow",   # <- ORACLE_COLS
    "z_cycle_norm", "z_vibration", "z_torque_scatter", "z_temp_adj",
    "z_manual_rate", "z_blocked_sm", "z_starved_sm",
]


def _forecast_evaluation(ev: pd.DataFrame, n_probe: int = 40) -> dict:
    """How much warning does the bottleneck forecast actually give?

    Sampled across the test window: at each probe the twin projects two hours
    forward, and we check whether the station it named did become the constraint,
    and how far ahead the call was. Reported honestly, including the misses --
    this is the number the throughput half of the business case rests on, so it
    should not be an assumption.
    """
    test_ev = ev[ev.unit_id.map(lambda _: True)]
    lo = ev[ev.station_idx == 1].depart_ts.quantile(0.72)
    hi = ev[ev.station_idx == 1].depart_ts.max() - 3 * 3600
    if not np.isfinite(lo) or hi <= lo:
        return dict(probes=0, hits=0, span_days=1.0, hit_rate=0.0,
                    median_lead_min=0.0, median_units_at_risk=0.0)

    probes = np.linspace(lo, hi, n_probe)
    span_days = float((hi - lo) / 86400.0)
    hits, leads, calls, at_risk = 0, [], 0, []
    for t in probes:
        pace = flow.station_pace(ev, float(t))
        if pace.empty:
            continue
        fc = flow.forecast(pace)
        ch = fc.get("change")
        if not ch:
            continue
        calls += 1
        at_risk.append(fc.get("units_at_risk", 0.0))
        later = flow.station_pace(ev, float(t) + ch["in_minutes"] * 60)
        if later.empty:
            continue
        actual = later.loc[later["capacity_uph"].idxmin(), "station_code"]
        if actual == ch["station_code"]:
            hits += 1
            leads.append(ch["in_minutes"])
    return dict(
        probes=int(calls),
        hits=int(hits),
        span_days=round(span_days, 2),
        hit_rate=round(hits / calls, 3) if calls else 0.0,
        median_lead_min=round(float(np.median(leads)), 1) if leads else 0.0,
        median_units_at_risk=round(float(np.median(at_risk)), 1) if at_risk else 0.0,
        note="A 'call' is a forecast that the constraint will change hands; a "
             "'hit' is that station actually holding the constraint at the "
             "forecast horizon.",
    )


def _detection_latency(ev: pd.DataFrame) -> list:
    """Warning time on the scripted incidents, measured on rising alarm edges."""
    t0 = pd.Timestamp(C.DAY_ZERO).value / 1e9
    out = []
    for ep in C.HERO_EPISODES:
        onset = (ep.day * 24 + ep.start_h) * 3600 + t0
        g = ev[ev.station_code == ep.station].sort_values("depart_ts")
        dr = g["drift"].values.astype(bool)
        ts = g["depart_ts"].values
        edges = np.flatnonzero(dr[1:] & ~dr[:-1]) + 1
        after = [ts[i] for i in edges if ts[i] >= onset]
        out.append(dict(
            station=ep.station, title=ep.title, kind=ep.kind,
            tier=C.STATION_BY_CODE[ep.station].tier,
            detected_after_min=round((after[0] - onset) / 60.0, 1) if after else None,
            onset_ts=float(onset)))
    return out


def build(seed: int = 20260302, verbose: bool = True) -> dict:
    t_start = time.time()
    C.DATA_DIR.mkdir(exist_ok=True, parents=True)
    C.ARTIFACT_DIR.mkdir(exist_ok=True, parents=True)

    def say(msg):
        if verbose:
            print(msg, flush=True)

    say("[1/6] generating plant data")
    units, ev, defects, episodes_true = generate(seed=seed, verbose=verbose)

    say("[2/6] fitting SPC baselines and scoring stations")
    beta = spc.fit_ambient_beta(ev, units)
    prepped = spc.prepare_channels(ev, units, beta)
    baselines = spc.fit_baselines(prepped, units)
    scored = spc.score(prepped, baselines)
    del prepped

    say("[3/6] training virtual sensors for dark stations")
    # Fitted on the training window only, so the dashboard's inferred readings on
    # the demo day come from a model that never saw that day.
    train_mask = scored["unit_id"].map(units.set_index("unit_id")["day"]) < C.TRAIN_DAYS[1]
    vs_model, vs_meta = vs.fit(scored[train_mask.values], units)
    scored = vs.apply(scored, vs_model, vs_meta)
    say(f"      held-out-station AUC {vs_meta['auc']:.3f} -> trust {vs_meta['trust']:.2f}")

    say("[4/6] engineering features and training the defect-risk model")
    feat = F.build_unit_features(scored, units)
    labels = F.build_labels(units, defects)
    res = M.train(feat, labels, seed=seed % 1000)
    rep = res["report"]
    say(f"      selected {rep['selected_model']}  "
        f"test ROC-AUC {rep['test']['roc_auc']:.3f}  "
        f"reachable ROC-AUC {rep['test_reachable']['roc_auc']:.3f}")

    say("[5/6] extracting drift episodes and validating the forecast")
    episodes = spc.drift_episodes(scored)
    fc_eval = _forecast_evaluation(scored)
    latency = _detection_latency(scored)
    trace_eval = tracing.validate(scored, defects, units, n_probes=60,
                                  test_days=C.TEST_DAYS)
    say(f"      {len(episodes)} episodes, "
        f"{int(episodes.actionable.sum())} actionable "
        f"({episodes.actionable.sum() / (C.N_DAYS * 2):.1f}/shift over 42 stations)")
    say(f"      forecast hit rate {fc_eval['hit_rate']:.0%} "
        f"on {fc_eval['probes']} calls, median lead {fc_eval['median_lead_min']:.0f} min")
    if trace_eval.get("probes"):
        say(f"      traceback top-1 {trace_eval['overall']['top1']:.0%} "
            f"(random {trace_eval['random_baseline_top1']:.0%}) over "
            f"{trace_eval['probes']} probes")

    say("[6/6] writing artifacts")
    window_days = C.TEST_DAYS[1] - C.TEST_DAYS[0]
    roi = economics.roi(rep, forecasts_hit=fc_eval["hits"], window_days=window_days,
                        probe_span_days=fc_eval["span_days"],
                        units_at_risk_per_event=fc_eval["median_units_at_risk"],
                        lead_minutes=fc_eval["median_lead_min"] or 45.0)
    instr = economics.instrumentation_case(episodes)

    slim = scored[[c for c in KEEP if c in scored.columns]].copy()
    slim.to_pickle(C.DATA_DIR / "events.pkl")

    # The dashboard replays the last stretch of the record. Keeping the whole
    # horizon in the app's memory costs ~250 MB for history nothing on screen
    # reaches back to; the traceback looks back 36 hours and the plant trends
    # span a week.
    day_of = units.set_index("unit_id")["day"]
    app_days = slim["unit_id"].map(day_of) >= (C.N_DAYS - C.APP_WINDOW_DAYS)
    served = slim[app_days.values].drop(columns=ORACLE_COLS, errors="ignore")
    served.to_pickle(C.DATA_DIR / "events_app.pkl")
    units.to_pickle(C.DATA_DIR / "units.pkl")
    defects.to_pickle(C.DATA_DIR / "defects.pkl")
    episodes.to_pickle(C.DATA_DIR / "episodes.pkl")
    episodes_true.to_pickle(C.DATA_DIR / "episodes_true.pkl")
    res["scored"].to_pickle(C.DATA_DIR / "risk.pkl")
    feat.to_pickle(C.DATA_DIR / "features.pkl")

    joblib.dump(dict(model=res["model"], pipeline=res["pipeline"],
                     threshold=res["threshold"], vs_model=vs_model),
                C.ARTIFACT_DIR / "models.joblib")

    validation = dict(
        built_at=pd.Timestamp.utcnow().isoformat(),
        seed=seed,
        line=dict(stations=C.N_STATIONS, takt_s=C.TAKT_S,
                  zones={k: v["label"] for k, v in C.ZONES.items()},
                  coverage=_coverage()),
        data=dict(units=int(len(units)), station_events=int(len(scored)),
                  days=C.N_DAYS, defects_created=int(len(defects)),
                  escape_rate=round(float(defects.escaped.mean()), 4),
                  downstream_flag_rate=round(float(labels.y.mean()), 4)),
        spc=dict(baseline_days=list(spc.BASELINE_DAYS),
                 drift_limit=spc.DRIFT_LIMIT, run_rule=[spc.RUN_RULE_N, spc.RUN_RULE_Z],
                 episodes=int(len(episodes)),
                 actionable=int(episodes.actionable.sum()),
                 actionable_per_shift=round(float(episodes.actionable.sum() / (C.N_DAYS * 2)), 2),
                 detection_latency=latency),
        virtual_sensor=vs_meta,
        model=rep,
        forecast=fc_eval,
        traceback=trace_eval,
        economics=roi,
        instrumentation=instr,
    )
    (C.ARTIFACT_DIR / "validation.json").write_text(json.dumps(validation, indent=2, default=str))

    say(f"done in {time.time() - t_start:.0f}s -> {C.ARTIFACT_DIR / 'validation.json'}")
    return validation


def _has_parquet() -> bool:
    try:
        import pyarrow  # noqa: F401
        return True
    except ImportError:
        return False


def _coverage() -> dict:
    from collections import Counter
    c = Counter(s.tier for s in C.STATIONS)
    return {k: dict(stations=v, share=round(v / C.N_STATIONS, 3)) for k, v in c.items()}


def main() -> None:
    ap = argparse.ArgumentParser(description="Build the SmartFactory Twin dataset and models.")
    ap.add_argument("--seed", type=int, default=20260302)
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args()
    v = build(seed=args.seed, verbose=not args.quiet)
    m = v["model"]
    print("\n" + "=" * 72)
    print("MODEL VALIDATION  (temporal split, days "
          f"{m['split']['test_days'][0]}-{m['split']['test_days'][1] - 1} held out)")
    print("=" * 72)
    for name, block in (("all downstream failures", m["test"]),
                        ("reachable failures only", m["test_reachable"])):
        print(f"  {name:26s} ROC-AUC {block['roc_auc']:.3f}  "
              f"PR-AUC {block['pr_auc']:.3f} (base {block['base_rate']:.3f}, "
              f"lift x{block['pr_lift']:.2f})")
        print(f"  {'':26s} precision {block['precision']:.3f}  "
              f"recall {block['recall']:.3f}  F1 {block['f1']:.3f}  "
              f"false-alarm {block['false_alarm_rate']:.3f}")
    print(f"  confusion {m['test']['confusion']}   Brier {m['test']['brier']:.4f}")
    print(f"  operating point: top {m['inspection_capacity_per_shift']} units per shift "
          f"({m['alerts_per_shift']:.0f} flagged/shift of {m['units_per_shift']:.0f} built)")
    print("\n  model selection (validation PR-AUC):")
    for b in m["selection"]:
        print(f"    {'*' if b['selected'] else ' '} {b['name']:22s} "
              f"val PR {b['val_pr_auc']:.4f} | train AUC {b['train_roc_auc']:.3f} "
              f"-> test AUC {b['test_roc_auc']:.3f}")


if __name__ == "__main__":
    main()
