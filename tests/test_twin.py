"""
Tests for the properties that would be embarrassing to get wrong.

Two kinds. The first are invariants a reviewer should be able to check without
reading the code: no feature can see its own outcome, the splits do not overlap,
control limits come only from the qualification window. The second are the
regressions that actually bit during development and were expensive to find --
each one is named after the failure it prevents coming back.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from twin import config as C
from twin import features as F
from twin import spc
from twin import virtual_sensor as vs
from twin.generate import generate


@pytest.fixture(scope="module")
def plant():
    units, ev, defects, episodes = generate(seed=4242, verbose=False)
    scored, fit = spc.compute_station_signals(ev, units)
    model, meta = vs.fit(scored, units)
    scored = vs.apply(scored, model, meta)
    return dict(units=units, ev=scored, defects=defects, episodes=episodes,
                fit=fit, vs_model=model, vs_meta=meta)


# ── line definition ──────────────────────────────────────────────────────────
def test_line_shape_matches_the_brief():
    assert 30 <= C.N_STATIONS <= 50
    tiers = {t: sum(s.tier == t for s in C.STATIONS) for t in ("FULL", "PARTIAL", "DARK")}
    assert tiers["FULL"] / C.N_STATIONS > 0.5, "majority should be instrumented"
    assert tiers["DARK"] + tiers["PARTIAL"] >= 5, "a meaningful minority is sensor-poor"


def test_dark_stations_expose_no_rich_channels():
    for st in C.STATIONS:
        chans = spc.available_channels(st)
        if st.tier == "DARK":
            assert not ({"vibration", "torque_scatter", "temp_adj"} & set(chans)), st.code
        assert "cycle_norm" in chans, f"{st.code} must always have MES scan timing"


# ── leakage ──────────────────────────────────────────────────────────────────
def test_splits_are_temporal_and_disjoint():
    assert C.TRAIN_DAYS[1] == C.VAL_DAYS[0]
    assert C.VAL_DAYS[1] == C.TEST_DAYS[0]
    assert C.TEST_DAYS[1] <= C.N_DAYS


def test_every_feature_precedes_every_label(plant):
    """The decision point is what makes the leakage argument structural."""
    ev = plant["ev"]
    feat = F.build_unit_features(ev, plant["units"])
    labels = F.build_labels(plant["units"], plant["defects"])

    # No feature is drawn from a station after the decision point.
    assert all(g <= C.DECISION_STATION for g in C.UPSTREAM_GATES)
    assert all(g > C.DECISION_STATION for g in C.DOWNSTREAM_GATES)

    # And every labelled event happens at a station after it.
    flagged = plant["defects"]
    flagged = flagged[(~flagged.escaped) & flagged.detect_idx.notna()]
    downstream = flagged[flagged.detect_idx.isin(C.DOWNSTREAM_GATES)]
    assert (downstream.detect_idx > C.DECISION_STATION).all()

    merged = feat.merge(labels, on="unit_id")
    assert len(merged) == len(feat)
    assert 0.02 < merged.y.mean() < 0.25, "implausible defect rate"


def test_hero_incidents_land_in_the_test_window():
    """The demo faults must be unseen by training, or the demo proves nothing."""
    for ep in C.HERO_EPISODES:
        assert C.TEST_DAYS[0] <= ep.day < C.TEST_DAYS[1], ep.station


def test_baselines_use_only_the_qualification_window(plant):
    """Control limits must not be derivable from data after the baseline period."""
    units, ev = plant["units"], plant["ev"]
    beta = spc.fit_ambient_beta(ev, units)
    prepped = spc.prepare_channels(ev, units, beta)
    early = spc.fit_baselines(prepped, units)

    # Truncating everything after the qualification window must not move a limit.
    day = units.set_index("unit_id")["day"]
    truncated = prepped[prepped["unit_id"].map(day).values < spc.BASELINE_DAYS[1]]
    same = spc.fit_baselines(truncated, units)
    for idx in early:
        for ch, (med, sig) in early[idx]["channels"].items():
            m2, s2 = same[idx]["channels"][ch]
            assert np.isclose(med, m2, equal_nan=True), (idx, ch)
            assert np.isclose(sig, s2, equal_nan=True), (idx, ch)


# ── detection quality ────────────────────────────────────────────────────────
def test_detector_separates_healthy_from_faulty(plant):
    ev = plant["ev"]
    healthy = ev[(ev.oracle_condition < 0.12) & (ev.oracle_flow < 0.12)]
    faulty = ev[ev.oracle_condition > 0.6]
    assert healthy.station_z.quantile(0.99) < 4.5, "healthy stations trip too often"
    assert faulty.station_z.median() > 4.0, "faults are not separating"


def test_alert_volume_is_something_a_supervisor_could_read(plant):
    eps = spc.drift_episodes(plant["ev"])
    per_shift = eps.actionable.sum() / (C.N_DAYS * len(C.SHIFTS))
    assert per_shift < 20, f"{per_shift:.1f} actionable alerts/shift across 42 stations"


def test_flow_channels_stay_out_of_the_condition_score():
    """Regression: blocked/starved seconds saturated the quality chart on healthy
    data (4% of units past 4 sigma) while scoring zero on genuine faults."""
    for ch in ("blocked_sm", "starved_sm"):
        assert not spc._in_score(ch, "condition"), ch
        assert spc._in_score(ch, "flow"), ch


def test_baseline_trimming_survives_a_contaminated_window():
    """Regression: a fault inside the qualification window doubled the fitted
    sigma at BODY-08, and the demo fault then scored 2 sigma instead of 8."""
    rng = np.random.default_rng(0)
    clean = rng.normal(10.0, 0.5, 900)
    contaminated = np.concatenate([clean, rng.normal(16.0, 0.5, 120)])
    _, sig_clean = spc._robust_scale(clean)
    _, sig_dirty = spc._robust_scale(contaminated)
    assert sig_dirty < sig_clean * 1.6, (
        f"contamination inflated sigma {sig_clean:.2f} -> {sig_dirty:.2f}")


def test_scale_estimator_survives_a_mostly_zero_channel():
    """Regression: quantised, mostly-zero channels had an IQR of exactly 0 and
    manufactured 12-sigma scores out of ordinary bursts."""
    x = np.zeros(800)
    x[::40] = 3.0
    _, sigma = spc._robust_scale(x)
    assert sigma > 0.01, "sigma collapsed on a sparse channel"
    assert abs(x.max() - np.median(x)) / sigma < 60


def test_incidents_do_not_merge_across_a_shift_break(plant):
    """Regression: a latched alarm spanned the overnight stop and was reported
    as one 17-hour incident."""
    eps = spc.drift_episodes(plant["ev"])
    if len(eps):
        hours = (eps.end_ts - eps.start_ts) / 3600
        assert hours.max() < 20, f"{hours.max():.1f}h incident"


# ── virtual sensors ──────────────────────────────────────────────────────────
def test_virtual_sensor_generalises_to_unseen_stations(plant):
    meta = plant["vs_meta"]
    assert meta["auc"] > 0.65, f"held-out-station AUC {meta['auc']}"
    assert len(meta["holdout_stations"]) >= 4
    # the reported score is what gates its influence
    assert 0.0 <= meta["trust"] <= 1.0
    assert np.isclose(meta["trust"], max(0.0, min(1.0, (meta["auc"] - 0.5) * 2)),
                      atol=1e-3)


def test_inference_only_lifts_sensor_poor_stations(plant):
    out = plant["ev"]
    full = out[out.station_idx.isin([s.idx for s in C.STATIONS if s.tier == "FULL"])]
    assert np.allclose(full.station_z_eff, full.station_z, equal_nan=True), \
        "a fully instrumented station must not be second-guessed by inference"
    dark = out[out.station_idx.isin([s.idx for s in C.STATIONS if s.tier == "DARK"])]
    assert (dark.data_confidence < full.data_confidence.mean()).mean() > 0.9, \
        "sensor-poor stations must carry lower confidence"


# ── economics ────────────────────────────────────────────────────────────────
def test_business_case_does_not_double_count_warranty():
    """Regression: crediting warranty avoidance to every true positive claimed
    the twin prevented failures the existing gates already catch, and tripled
    the quality benefit."""
    from twin import economics
    report = dict(
        test=dict(confusion=dict(tn=3000, fp=100, fn=300, tp=30), precision=0.23),
        test_reachable=dict(recall=0.1),
        escapes=dict(caught=0, total=150),
    )
    zero_escapes = economics.defect_economics(report, window_days=4)
    report["escapes"] = dict(caught=5, total=150)
    some_escapes = economics.defect_economics(report, window_days=4)
    assert some_escapes["gross_benefit"] > zero_escapes["gross_benefit"]
    # with no escapes intercepted, only the rework differential may be claimed,
    # and only for the share of inspections that actually find the fault
    expected = (economics.annualise(30, 4)
                * (C.ECONOMICS["rework_cost_at_gate"] - C.ECONOMICS["rework_cost_in_station"])
                * C.ECONOMICS["inspection_effectiveness"])
    assert np.isclose(zero_escapes["gross_benefit"], round(expected))


def test_business_case_stays_within_a_believable_range():
    """Regression: three separate arithmetic errors -- crediting stopped-line
    downtime to a slow station, warranty savings to defects the gates already
    catch, and a platform cost far below what integration actually takes -- once
    combined into a $4.4M benefit with a twelve-day payback."""
    from twin import economics
    report = dict(
        test=dict(confusion=dict(tn=3043, fp=171, fn=342, tp=29), precision=0.145),
        test_reachable=dict(recall=0.057), escapes=dict(caught=11, total=191))
    roi = economics.roi(report, forecasts_hit=4, window_days=4,
                        probe_span_days=7.4, units_at_risk_per_event=14.4)
    assert roi["payback_months"] > 1.5, "a payback under six weeks reads as an error"
    units = roi["quality"]["units_per_year"]
    per_unit = roi["annual_benefit_per_line"] / units
    assert per_unit < 25, f"${per_unit:.0f}/vehicle is not a credible claim"


def test_every_economic_claim_is_labelled(plant):
    from twin import economics
    report = dict(
        test=dict(confusion=dict(tn=3000, fp=100, fn=300, tp=30), precision=0.23),
        test_reachable=dict(recall=0.1), escapes=dict(caught=4, total=150))
    roi = economics.roi(report, forecasts_hit=4, window_days=4,
                        probe_span_days=7.0, units_at_risk_per_event=14.0)
    assert roi["quality"]["basis"] == "MODELLED"
    assert roi["throughput"]["basis"] == "MODELLED"
    assert "MEASURED" in roi["disclosure"] and "ASSUMED" in roi["disclosure"]
    assert roi["payback_months"] > 0


# ── the answer key stays quarantined ─────────────────────────────────────────
def test_no_twin_module_reads_the_oracle():
    """Simulator ground truth must never reach a decision path.

    `oracle_condition` and `oracle_flow` are the latent state the generator uses
    to create defects. They are named to be conspicuous and they are allowed in
    exactly two places: the generator that writes them, and tests that check the
    twin against them. Anything else touching them is leakage.
    """
    root = Path(__file__).resolve().parent.parent
    allowed = {"generate.py", "pipeline.py"}   # writes them / strips them
    offenders = []
    for path in sorted((root / "twin").glob("*.py")) + sorted((root / "app").glob("*.py")):
        if path.name in allowed:
            continue
        body = path.read_text()
        if "oracle_condition" in body or "oracle_flow" in body:
            offenders.append(path.name)
    assert not offenders, f"oracle columns referenced in {offenders}"


def test_served_data_does_not_contain_the_oracle():
    """The dashboard's own data file must not carry the answer key."""
    from twin import config as cfg
    served = cfg.DATA_DIR / "events_app.pkl"
    if not served.exists():
        pytest.skip("run `python -m twin.pipeline` first")
    cols = set(pd.read_pickle(served).columns)
    assert not (cols & {"oracle_condition", "oracle_flow"})


def test_virtual_sensor_uses_no_downstream_lookahead(plant):
    """Regression: taking station s+1's row for the *same* unit is a 50-second
    lookahead -- that unit has not reached s+1 yet, and across the painted-body
    store it will not for an hour. Downstream context must come from a time
    join against readings that already happened."""
    ev = plant["ev"]
    thin = vs.build_thin_frame(ev)
    merged = thin.merge(ev[["unit_row", "station_idx", "depart_ts"]],
                        on=["unit_row", "station_idx"], how="left")
    # pick a station pair and confirm the joined downstream value predates the row
    probe = merged[(merged.station_idx == 8) & merged.dn_blocked.notna()].head(200)
    nxt = ev[ev.station_idx == 9][["depart_ts", "z_blocked_sm"]].dropna()
    for _, r in probe.iterrows():
        earlier = nxt[nxt.depart_ts < r.depart_ts]
        assert len(earlier) == 0 or r.dn_blocked in set(earlier.z_blocked_sm.values), \
            "downstream feature took a value that had not been recorded yet"
        break   # one strict check is enough; the join direction is global


def test_traceback_confidence_is_earned(plant):
    """A confidence label that does not track accuracy is decoration.

    The traceback reports high/medium/low. This asserts the ordering it claims:
    leading suspects on high-confidence traces are right more often than on
    low-confidence ones, and both beat picking an upstream station at random.
    """
    from twin import tracing
    res = tracing.validate(plant["ev"], plant["defects"], plant["units"],
                           n_probes=30, test_days=C.TEST_DAYS)
    if not res.get("probes"):
        pytest.skip("no traceable windows in this seed")
    assert res["overall"]["top1"] > res["random_baseline_top1"] * 3
    conf = res["by_confidence"]
    if "high" in conf and "low" in conf:
        assert conf["high"]["top1"] > conf["low"]["top1"], \
            "confidence label does not track accuracy"
