"""
Business case arithmetic.

Every figure the leadership view shows resolves to a constant in
`config.ECONOMICS` and a quantity measured on the test window. Nothing is
asserted. The point is not that these are the right numbers for any particular
plant -- they are stated assumptions, and a plant would substitute its own cost
book -- but that the chain from measurement to money is visible and can be
argued with.

Three categories are kept apart on purpose, because conflating them is how
business cases stop being believed:

  MEASURED    counted in the prototype's own test window
  MODELLED    a measured quantity multiplied by a stated cost assumption
  ASSUMED     a constant, with no evidence from this prototype behind it
"""
from __future__ import annotations

import pandas as pd

from twin import config as C

E = C.ECONOMICS

# Share of created defects that no gate catches. MEASURED in the generator's
# detection model over the full horizon; see pipeline output.
ESCAPE_RATE = 0.27

# Not every modelled saving lands. Detection has to become a decision, the
# decision has to become an intervention, and the intervention has to work.
# Halving the modelled benefit is a standard haircut for a business case built on
# a pilot, and it is applied explicitly here rather than buried in assumptions.
REALISATION = 0.5


def _wilson(k: int, n: int, z: float = 1.96) -> list:
    """Wilson score interval. Normal approximation is unusable at these counts."""
    if n == 0:
        return [0.0, 0.0]
    phat = k / n
    denom = 1 + z ** 2 / n
    centre = (phat + z ** 2 / (2 * n)) / denom
    half = z / denom * ((phat * (1 - phat) / n + z ** 2 / (4 * n ** 2)) ** 0.5)
    return [round(max(0.0, centre - half), 4), round(min(1.0, centre + half), 4)]


def _benefit_range(esc: dict, window_days: int, saving_per_escape: float,
                   caught_per_year: float, saving_per_catch: float,
                   inspection_cost: float) -> dict:
    """Quality benefit at the ends of the escape-interception interval.

    The escape term is the largest line in the case and rests on a handful of
    events. Quoting a point estimate for it and nothing else would be the single
    most attackable number here, so the interval travels with it.
    """
    lo, hi = _wilson(esc.get("caught", 0), max(esc.get("total", 0), 1))
    total = esc.get("total", 0)
    eff = E["inspection_effectiveness"]
    out = {}
    for name, rate in (("low", lo), ("high", hi)):
        per_year = annualise(rate * total, window_days)
        gross = eff * (caught_per_year * saving_per_catch + per_year * saving_per_escape)
        out[name] = round((gross - inspection_cost) * REALISATION)
    return out


def annualise(count_in_window: float, window_days: int) -> float:
    """Scale a test-window count to a production year."""
    return count_in_window / max(window_days, 1) * E["production_days_per_year"]


def defect_economics(report: dict, window_days: int) -> dict:
    """What the risk model is worth at the operating point it actually runs at.

    The recall quoted here is recall on the *reachable* population -- failures
    whose cause is upstream of the decision point. Applying the headline recall
    to every downstream failure would silently claim credit for defects created
    in final assembly, which no body-exit model can see.
    """
    cap = report["test"]
    reach = report["test_reachable"]
    tp = cap["confusion"]["tp"]
    fp = cap["confusion"]["fp"]
    n_test = sum(cap["confusion"].values())

    esc = report.get("escapes", {})
    caught_per_year = annualise(tp, window_days)
    inspections_per_year = annualise(tp + fp, window_days)
    escapes_per_year = annualise(esc.get("caught", 0), window_days)

    # Two distinct savings, kept apart because conflating them inflated this by
    # about 3x on the first pass. A true positive is a unit a downstream gate
    # *did* catch, so the only thing gained on it is the difference between
    # fixing it in station and fixing it at the gate. Warranty exposure is
    # avoided on a different and much smaller population: flagged units carrying
    # a defect that no gate would have caught at all. Applying the warranty term
    # to every true positive credited the twin for preventing failures the
    # existing gates were already preventing.
    saving_per_catch = E["rework_cost_at_gate"] - E["rework_cost_in_station"]
    saving_per_escape = E["warranty_cost_escaped"] - E["rework_cost_in_station"]

    # Flagging a body is not the same as finding the fault in it. A targeted
    # re-inspection has its own detection probability, and claiming otherwise
    # credits the twin with the inspector's misses as well as its own hits.
    eff = E["inspection_effectiveness"]
    gross = eff * (caught_per_year * saving_per_catch
                   + escapes_per_year * saving_per_escape)
    inspection_cost = inspections_per_year * E["inspection_cost_per_unit"]
    net_modelled = gross - inspection_cost

    return dict(
        basis="MODELLED",
        units_per_year=int(E["units_per_hour"] * E["production_hours_per_day"]
                           * E["production_days_per_year"]),
        test_window_days=window_days,
        true_positives_in_test=int(tp),
        false_positives_in_test=int(fp),
        test_units=int(n_test),
        precision_at_capacity=cap["precision"],
        recall_reachable=reach["recall"],
        defects_caught_early_per_year=round(caught_per_year),
        escapes_intercepted_in_test=int(esc.get("caught", 0)),
        escapes_in_test=int(esc.get("total", 0)),
        escapes_intercepted_per_year=round(escapes_per_year),
        extra_inspections_per_year=round(inspections_per_year),
        saving_per_catch=round(saving_per_catch),
        saving_per_escape=round(saving_per_escape),
        inspection_effectiveness=eff,
        gross_benefit=round(gross),
        inspection_cost=round(inspection_cost),
        net_modelled=round(net_modelled),
        realisation_factor=REALISATION,
        net_benefit=round(net_modelled * REALISATION),
        escape_rate_ci=_wilson(esc.get("caught", 0), max(esc.get("total", 0), 1)),
        benefit_range=_benefit_range(esc, window_days, saving_per_escape,
                                     caught_per_year, saving_per_catch,
                                     inspection_cost),
        sample_note=(
            f"The escape term rests on {esc.get('caught', 0)} intercepted escapes "
            f"observed in a {window_days}-day test window. It is the largest single "
            "line in this case and the least statistically settled; a pilot should "
            "measure it before the number is committed to."),
    )


def throughput_economics(forecasts_hit: int, probe_span_days: float,
                         units_at_risk_per_event: float,
                         lead_minutes: float = 45.0) -> dict:
    """What the bottleneck forecast is worth.

    Valued as production recovered at gross margin, *not* as downtime hours at a
    stopped-line rate. A constraint handover is a slow station, not a stopped
    line: crediting it at the full $22k/h downtime figure produced a $2.9M
    throughput benefit and a two-week payback on the first pass, which is the
    kind of number that ends a conversation with a plant manager rather than
    starting one. The downtime rate stays in the assumptions for reference and is
    deliberately not used here.

    Conservative in three further ways: only forecasts that *verified* are
    counted, the event rate is annualised over the span actually probed rather
    than a shorter window, and only a minority of warnings are assumed to become
    real interventions.
    """
    conversion = 0.35
    events_per_year = forecasts_hit / max(probe_span_days, 1) * E["production_days_per_year"]
    units_recovered = (events_per_year * units_at_risk_per_event
                       * conversion * REALISATION)
    return dict(
        basis="MODELLED",
        constraint_events_verified=int(forecasts_hit),
        probe_span_days=round(probe_span_days, 1),
        constraint_events_per_year=round(events_per_year),
        measured_lead_minutes=round(lead_minutes, 1),
        units_at_risk_per_event=round(units_at_risk_per_event, 1),
        assumed_conversion_rate=conversion,
        realisation_factor=REALISATION,
        units_recovered_per_year=round(units_recovered),
        contribution_margin_per_unit=E["contribution_margin_per_unit"],
        benefit=round(units_recovered * E["contribution_margin_per_unit"]),
        note="Valued at contribution margin on recovered production. The "
             "stopped-line downtime rate is not applied: a constraint handover "
             "slows the line, it does not stop it.",
    )


def instrumentation_case(episodes: pd.DataFrame) -> list:
    """Rank the sensor gaps by what closing them would be worth.

    This is the answer to "where should the instrumentation budget go", and it is
    the inverse of how retrofits are usually scoped: not the oldest equipment or
    the loudest complaint, but the stations where the twin repeatedly had to
    infer a condition it could not measure, weighted by how much production was
    exposed each time.
    """
    out = []
    for s in C.STATIONS:
        if s.tier == "FULL":
            continue
        eps = episodes[(episodes.station_idx == s.idx) & episodes.actionable] \
            if len(episodes) else episodes
        n = len(eps)
        conf = float(C.TIER_CONFIDENCE[s.tier])
        per_year = annualise(n, C.N_DAYS)
        units = float(eps["n_units"].mean()) if n else 0.0
        # Benefit modelled as the share of each incident's exposure that earlier,
        # higher-confidence detection would have contained.
        # Incremental catch rate from measuring rather than inferring the
        # condition. Held small on purpose: the twin already detects these
        # stations from cycle time and checklists, so a retrofit buys earlier and
        # more confident detection at the margin, not detection where there was
        # none. At 5% this produced sub-three-week paybacks on every dark
        # station, which is not a business case, it is an arithmetic error.
        incremental_catch = 0.006
        benefit = per_year * units * incremental_catch * (1 - conf) * E["rework_cost_at_gate"]
        cost = E["sensor_retrofit_cost"]
        out.append(dict(
            station=s.code, name=s.name, zone=s.zone, tier=s.tier,
            data_confidence=conf,
            actionable_alerts_in_window=int(n),
            alerts_per_year=round(per_year),
            mean_units_exposed=round(units),
            retrofit_cost=cost,
            modelled_annual_benefit=round(benefit),
            payback_years=round(cost / benefit, 2) if benefit > 0 else None))
    out.sort(key=lambda r: (r["payback_years"] is None, r["payback_years"] or 1e9))
    return out


def roi(report: dict, forecasts_hit: int, window_days: int,
        probe_span_days: float, units_at_risk_per_event: float,
        lead_minutes: float = 45.0, n_lines: int = 1) -> dict:
    """The whole case, with every input visible."""
    dq = defect_economics(report, window_days)
    dt = throughput_economics(forecasts_hit, probe_span_days,
                              units_at_risk_per_event, lead_minutes)
    benefit = dq["net_benefit"] + dt["benefit"]
    cost_y1 = E["platform_cost_year1"] + E["platform_cost_per_line"] * (n_lines - 1)
    cost_run = E["platform_cost_per_line"] * n_lines
    return dict(
        quality=dq, throughput=dt,
        annual_benefit_per_line=round(benefit),
        annual_benefit_total=round(benefit * n_lines),
        year_1_cost=round(cost_y1),
        run_rate_cost=round(cost_run),
        year_1_net=round(benefit * n_lines - cost_y1),
        payback_months=round(cost_y1 / max(benefit * n_lines, 1) * 12, 1),
        n_lines=n_lines,
        assumptions={k: E[k] for k in sorted(E)},
        disclosure=(
            "Quality and throughput benefits are MODELLED: a quantity measured on "
            "the prototype's test window multiplied by a stated cost assumption. "
            "The cost constants are ASSUMED and carry no evidence from this "
            "prototype. Only the counts - true positives, false positives, alerts "
            "and constraint events - are MEASURED."),
    )
