"""
Synthetic plant generator.

This stands in for the MES / PLC / quality-system feed of a real vehicle
assembly line. It is deliberately *not* a toy: the defect label is produced by a
latent causal chain that the twin never observes directly.

    latent station condition  ->  noisy, partially-missing sensor readings
    latent station condition  ->  per-unit defect creation (logistic)
    defect + gate sensitivity ->  detection, many stations downstream, or escape

Everything the model is later allowed to see is an imperfect, lagged view of the
left-hand side. Roughly a third of defects are drawn from causes with no upstream
signature at all, which puts a real ceiling on achievable recall.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from twin import config as C


# ---------------------------------------------------------------------------
# calendar
# ---------------------------------------------------------------------------
def _launch_schedule(rng: np.random.Generator) -> pd.DataFrame:
    """Unit launch times across the production calendar, at takt with jitter."""
    rows = []
    day0 = pd.Timestamp(C.DAY_ZERO)
    for day in range(C.N_DAYS):
        for shift_name, h0, h1 in C.SHIFTS:
            t = day0 + pd.Timedelta(days=day, hours=h0)
            shift_end = day0 + pd.Timedelta(days=day, hours=h1)
            break_at = day0 + pd.Timedelta(days=day, hours=h0 + C.BREAK_AFTER_H)
            break_done = False
            while t < shift_end:
                if not break_done and t >= break_at:
                    t += pd.Timedelta(minutes=C.BREAK_MIN)
                    break_done = True
                    continue
                rows.append((t, day, shift_name,
                             (t - (day0 + pd.Timedelta(days=day, hours=h0))).total_seconds() / 3600.0))
                t += pd.Timedelta(seconds=C.TAKT_S * rng.uniform(0.96, 1.05))
    df = pd.DataFrame(rows, columns=["launch_ts", "day", "shift", "hours_into_shift"])
    df.insert(0, "unit_id", [f"VIN{100000 + i}" for i in range(len(df))])
    df["seq"] = np.arange(len(df))
    return df


def _unit_attributes(units: pd.DataFrame, rng: np.random.Generator) -> pd.DataFrame:
    n = len(units)

    # Mixed-model sequencing: models arrive in short runs, not i.i.d.
    names = list(C.VEHICLE_MODELS)
    probs = np.array([C.VEHICLE_MODELS[m]["share"] for m in names])
    model_seq, i = [], 0
    while i < n:
        m = rng.choice(len(names), p=probs)
        run = int(rng.integers(1, 7))
        model_seq.extend([names[m]] * run)
        i += run
    units["model"] = model_seq[:n]
    units["complexity"] = units["model"].map(lambda m: C.VEHICLE_MODELS[m]["complexity"])
    units["work_mult"] = units["model"].map(lambda m: C.VEHICLE_MODELS[m]["work"])

    # Crew rotates by shift and day
    crew_idx = (units["day"].values + units["shift"].map({"A": 0, "B": 1}).values) % len(C.CREWS)
    units["crew"] = [C.CREWS[i] for i in crew_idx]
    crew_skill = {"Crew-1": 0.00, "Crew-2": 0.07, "Crew-3": -0.05}
    units["crew_penalty"] = units["crew"].map(crew_skill)

    # Fatigue / warm-up within a shift: slower on the first units after a break,
    # slightly more error-prone in the last hour.
    h = units["hours_into_shift"].values
    units["warmup"] = np.exp(-h / 0.4) * 0.06 + np.exp(-np.abs(h - C.BREAK_AFTER_H) / 0.3) * 0.05
    units["fatigue"] = np.clip((h - 6.0) / 2.0, 0, 1) * 0.16

    # Incoming part lots. Quality drifts by lot; a handful of lots are bad.
    lot_size = 260
    lot_id = units["seq"].values // lot_size
    lot_quality = rng.normal(0, 0.45, size=lot_id.max() + 1)
    bad = rng.random(lot_id.max() + 1) < 0.09
    lot_quality[bad] += rng.uniform(0.9, 2.0, size=bad.sum())
    units["lot_id"] = [f"LOT-{i:04d}" for i in lot_id]
    units["lot_penalty"] = lot_quality[lot_id]
    # What the plant actually knows at build time: an incoming-inspection index
    # per lot. A noisy read on the latent quality, not the truth itself -- goods
    # inward measures a sample, not every part.
    lot_measured = lot_quality + rng.normal(0, 0.62, size=len(lot_quality))
    units["lot_incoming_index"] = lot_measured[lot_id]

    # Ambient: diurnal swing plus slow weather drift, shared by the whole plant.
    tod = (units["launch_ts"].dt.hour + units["launch_ts"].dt.minute / 60).values
    weather = np.interp(units["day"].values, np.arange(C.N_DAYS),
                        rng.normal(0, 2.2, C.N_DAYS).cumsum() * 0.15)
    units["ambient_c"] = 21.5 + 3.4 * np.sin((tod - 9) / 24 * 2 * np.pi) + weather
    units["humidity"] = np.clip(48 + 14 * np.sin((tod - 4) / 24 * 2 * np.pi) + rng.normal(0, 4, len(units)), 25, 92)
    return units


# ---------------------------------------------------------------------------
# latent station condition
# ---------------------------------------------------------------------------
def _episode_profile(t_h: np.ndarray, start_h: float, ramp_h: float,
                     hold_h: float, peak: float) -> np.ndarray:
    """Ramp -> hold -> decay severity curve, in absolute hours since day zero."""
    out = np.zeros_like(t_h)
    ramp = (t_h >= start_h) & (t_h < start_h + ramp_h)
    out[ramp] = peak * (t_h[ramp] - start_h) / max(ramp_h, 1e-6)
    hold = (t_h >= start_h + ramp_h) & (t_h < start_h + ramp_h + hold_h)
    out[hold] = peak
    decay_h = 1.5
    dec = (t_h >= start_h + ramp_h + hold_h) & (t_h < start_h + ramp_h + hold_h + decay_h)
    out[dec] = peak * (1 - (t_h[dec] - start_h - ramp_h - hold_h) / decay_h)
    return out


def _build_conditions(rng: np.random.Generator):
    """Per-station latent condition on a 1-minute grid over the whole horizon.

    Two channels, because a fault does not express itself the same way in
    throughput and in quality:
      cond_qual -- sensor signature and defect propensity
      cond_flow -- cycle-time inflation and therefore blocking / starving

    A worn spindle is loud in `qual` and almost silent in `flow`; a sticking
    fixture is the reverse. Both are in [0, 1]. Neither is ever shown to the
    model -- they are the simulator's ground truth.
    """
    total_h = C.N_DAYS * 24
    grid = np.arange(0, total_h, 1 / 60.0)
    qual = {s.code: np.zeros_like(grid) for s in C.STATIONS}
    flow = {s.code: np.zeros_like(grid) for s in C.STATIONS}
    episodes: list[C.Episode] = []

    # Background: a slow wear baseline per station, resetting at maintenance.
    for s in C.STATIONS:
        wear_rate = rng.uniform(0.001, 0.005)      # per hour
        base = (grid % (24 * rng.uniform(2.5, 6.0))) * wear_rate
        base = np.clip(base, 0, 0.10)
        qual[s.code] += base
        flow[s.code] += base * 0.35
        # intermittent short excursions (a few per station over two weeks)
        for _ in range(rng.integers(2, 7)):
            t0 = rng.uniform(0, total_h)
            dur = rng.uniform(0.2, 1.2)
            amp = rng.uniform(0.05, 0.16)
            m = (grid >= t0) & (grid < t0 + dur)
            bump = amp * np.sin(np.pi * (grid[m] - t0) / dur)
            qual[s.code][m] += bump
            flow[s.code][m] += bump * 0.5

    # Background degradation episodes, spread across all days so the model has
    # genuine training signal (not just the scripted demo incidents).
    # Stratified across days on purpose. Drawing the day uniformly at random
    # leaves the train and test windows with materially different fault rates,
    # and a base-rate shift across a temporal split is indistinguishable from a
    # broken model when you read the metrics.
    codes = [s.code for s in C.STATIONS]
    per_day = 9
    for day in range(C.N_DAYS):
        for _ in range(per_day):
            code = codes[rng.integers(0, len(codes))]
            ep = C.Episode(station=code, day=int(day), start_h=float(rng.uniform(6.5, 20.0)),
                           ramp_h=float(rng.uniform(1.0, 4.0)),
                           hold_h=float(rng.uniform(1.0, 6.0)),
                           peak=float(rng.uniform(0.45, 0.95)),
                           kind=str(rng.choice(["degradation", "fixture", "operator"])),
                           title="Background degradation episode")
            episodes.append(ep)

    episodes.extend(C.HERO_EPISODES)

    for ep in episodes:
        abs_start = ep.day * 24 + ep.start_h
        shape = _episode_profile(grid, abs_start, ep.ramp_h, ep.hold_h, ep.peak)
        w = C.EPISODE_EXPRESSION[ep.kind]
        qual[ep.station] += shape * w["qual"]
        flow[ep.station] += shape * w["flow"]

    for code in qual:
        qual[code] = np.clip(qual[code], 0, 1)
        flow[code] = np.clip(flow[code], 0, 1)
    return grid, qual, flow, episodes


# ---------------------------------------------------------------------------
# flow simulation
# ---------------------------------------------------------------------------
def _simulate_flow(units: pd.DataFrame, cycle: np.ndarray):
    """Serial line with finite buffers (blocking-after-service).

    cycle: (n_units, n_stations) service times in seconds.
    Returns arrive / start / depart matrices plus blocked and starved seconds.
    """
    n_u, n_s = cycle.shape
    buf = np.array([s.buffer_out for s in C.STATIONS], dtype=np.int64)
    trans = [s.transit_s for s in C.STATIONS]
    launch = units["launch_ts"].astype("int64").values / 1e9   # epoch seconds

    arrive = np.zeros((n_u, n_s))
    start = np.zeros((n_u, n_s))
    finish = np.zeros((n_u, n_s))
    depart = np.zeros((n_u, n_s))

    cyc = cycle.tolist()
    arr, st, fin, dep = arrive.tolist(), start.tolist(), finish.tolist(), depart.tolist()
    bufl = buf.tolist()

    for u in range(n_u):
        for s in range(n_s):
            a = launch[u] if s == 0 else dep[u][s - 1] + trans[s - 1]
            # the station is free once the previous unit left it
            free = st[u - 1][s] + cyc[u - 1][s] if u > 0 else 0.0
            s0 = a if a > free else free
            f = s0 + cyc[u][s]
            # blocking: cannot release until the downstream buffer has a slot,
            # i.e. until unit (u - buffer) has begun service at the next station
            d = f
            if s < n_s - 1:
                k = u - bufl[s]
                if k >= 0:
                    ds = st[k][s + 1]
                    if ds > d:
                        d = ds
            arr[u][s], st[u][s], fin[u][s], dep[u][s] = a, s0, f, d

    arrive = np.array(arr); start = np.array(st)
    finish = np.array(fin); depart = np.array(dep)
    blocked = depart - finish                      # held by a full downstream buffer
    starved = np.zeros_like(blocked)
    starved[1:] = np.maximum(0.0, arrive[1:] - depart[:-1])   # waited for work
    return arrive, start, finish, depart, blocked, starved


# ---------------------------------------------------------------------------
# main entry point
# ---------------------------------------------------------------------------
def generate(seed: int = 20260302, verbose: bool = True):
    rng = np.random.default_rng(seed)

    units = _launch_schedule(rng)
    units = _unit_attributes(units, rng)
    n_u = len(units)
    n_s = C.N_STATIONS
    if verbose:
        print(f"  units          : {n_u:,}")

    grid, qual_grid, flow_grid, episodes = _build_conditions(rng)

    # --- planned arrival time per station (used only to look up condition) ---
    nominal = np.array([s.cycle_s for s in C.STATIONS]) * C.CYCLE_SCALE
    transit = np.array([s.transit_s for s in C.STATIONS])
    planned_offset = np.concatenate([[0.0], np.cumsum(nominal + transit)[:-1]])

    launch_h = ((units["launch_ts"] - pd.Timestamp(C.DAY_ZERO)).dt.total_seconds() / 3600.0).values
    passage_h = launch_h[:, None] + planned_offset[None, :] / 3600.0

    condition = np.zeros((n_u, n_s))      # quality channel
    cond_flow = np.zeros((n_u, n_s))      # throughput channel
    for j, s in enumerate(C.STATIONS):
        condition[:, j] = np.interp(passage_h[:, j], grid, qual_grid[s.code])
        cond_flow[:, j] = np.interp(passage_h[:, j], grid, flow_grid[s.code])

    # --- cycle times -------------------------------------------------------
    work = units["work_mult"].values[:, None]
    crew = units["crew_penalty"].values[:, None]
    warm = (units["warmup"].values + units["fatigue"].values * 0.4)[:, None]

    # AR(1) noise so consecutive cycles are correlated, as on a real line
    eps = rng.normal(0, 1, (n_u, n_s))
    for u in range(1, n_u):
        eps[u] = 0.45 * eps[u - 1] + np.sqrt(1 - 0.45 ** 2) * eps[u]

    manual = np.array([s.manual for s in C.STATIONS])
    ct_noise_sd = np.where(manual, 0.075, 0.035)        # manual work is more variable
    cycle = nominal[None, :] * work * (1 + crew * manual[None, :] + warm
                                       + 0.46 * cond_flow + ct_noise_sd[None, :] * eps)

    # micro-stops and rarer line stops
    micro = rng.random((n_u, n_s)) < 0.012
    cycle += micro * (15 + rng.exponential(32, (n_u, n_s)))
    stops = rng.random((n_u, n_s)) < 0.00035
    cycle += stops * rng.uniform(180, 900, (n_u, n_s))
    cycle = np.clip(cycle, 12, None)

    arrive, start, finish, depart, blocked, starved = _simulate_flow(units, cycle)
    if verbose:
        print(f"  station events : {n_u * n_s:,}")

    # --- sensor channels ---------------------------------------------------
    amb = units["ambient_c"].values[:, None]
    vib_base = np.array([1.6 + 0.9 * ((s.idx * 7) % 5) / 5 for s in C.STATIONS])
    tq_base = np.array([48 + 18 * ((s.idx * 3) % 7) / 7 for s in C.STATIONS])
    tmp_base = np.array([28 + 22 * ((s.idx * 11) % 6) / 6 for s in C.STATIONS])
    for j, s in enumerate(C.STATIONS):
        if s.zone == "PAINT" and "oven" in s.name.lower():
            tmp_base[j] = 158.0

    vib_eps = rng.normal(0, 1, (n_u, n_s))
    for u in range(1, n_u):
        vib_eps[u] = 0.55 * vib_eps[u - 1] + np.sqrt(1 - 0.55 ** 2) * vib_eps[u]

    vibration = vib_base[None, :] * (1 + 1.85 * condition ** 1.3) + 0.16 * vib_eps
    vibration += rng.normal(0, 0.05, (n_u, n_s))
    vibration = np.clip(vibration, 0.05, None)

    # Mean torque stays inside the PLC acceptance window; it is the *scatter*
    # that grows. This is why the existing PLC limit checks never fire.
    tq_scatter = 1.5 + 4.2 * condition ** 1.6
    torque = tq_base[None, :] + rng.normal(0, 1, (n_u, n_s)) * tq_scatter \
        - 0.9 * condition + 0.35 * units["complexity"].values[:, None]

    temperature = tmp_base[None, :] + 0.42 * (amb - 21.5) + 5.5 * condition \
        + rng.normal(0, 0.55, (n_u, n_s))

    # Operator checklist: at manual stations the operator flags a proportion of
    # genuinely bad units, plus a small false-positive rate. Detection is far
    # from perfect -- that is the point of a sensor-poor station.
    p_flag = 0.018 + 0.30 * condition ** 1.4
    manual_flag = (rng.random((n_u, n_s)) < p_flag) & manual[None, :]

    # --- defect creation ---------------------------------------------------
    ct_dev = (cycle - nominal[None, :] * work) / (nominal[None, :] * work)
    lot = units["lot_penalty"].values[:, None]
    cplx = (units["complexity"].values - 1.0)[:, None]
    crew_pen = units["crew_penalty"].values[:, None]
    fatigue = units["fatigue"].values[:, None]

    defect_rows = []
    creators = [(j, s) for j, s in enumerate(C.STATIONS) if s.creates]
    for j, s in creators:
        base = s.base_defect * C.DEFECT_SCALE * C.ZONE_DEFECT_WEIGHT[s.zone]
        logit = (np.log(base / (1 - base))
                 + 6.40 * condition[:, j]                 # the dominant, learnable cause
                 + 0.95 * lot[:, 0]                       # supplier lot quality
                 + 1.30 * cplx[:, 0]                      # model complexity
                 + 1.80 * crew_pen[:, 0] * (1.0 if s.manual else 0.35)
                 + 1.10 * fatigue[:, 0] * (1.0 if s.manual else 0.4)
                 + 0.85 * np.clip(ct_dev[:, j], -0.4, 0.8)
                 + rng.normal(0, 0.85, n_u))              # irreducible variation
        p = 1 / (1 + np.exp(-logit))
        hit = rng.random(n_u) < p
        idx = np.flatnonzero(hit)
        if len(idx) == 0:
            continue
        modes = rng.choice(list(s.creates), size=len(idx))
        for k, m in zip(idx, modes):
            defect_rows.append((units["unit_id"].values[k], k, s.idx, s.code, m,
                                depart[k, j], float(condition[k, j])))

    defects = pd.DataFrame(defect_rows, columns=[
        "unit_id", "unit_row", "origin_idx", "origin_code", "mode",
        "created_ts", "origin_condition"])
    if verbose:
        print(f"  defects created: {len(defects):,}  ({len(defects)/n_u:.3f} per unit)")

    # --- detection at gates ------------------------------------------------
    gates = [(s.idx, s.gate, s.gate_catches) for s in C.STATIONS if s.gate]
    det_gate, det_idx, det_ts = [], [], []
    rand = rng.random(len(defects))
    for r, (row, origin, mode) in enumerate(zip(defects["unit_row"].values,
                                                defects["origin_idx"].values,
                                                defects["mode"].values)):
        caught_at, caught_gate, caught_ts = None, None, np.nan
        pool = rand[r]
        for gidx, gid, catches in gates:
            if gidx <= origin or mode not in catches:
                continue
            p = C.GATE_SENSITIVITY[gid].get(mode, 0.0)
            if pool < p:
                caught_at, caught_gate = gidx, gid
                caught_ts = depart[row, gidx - 1]
                break
            pool = (pool - p) / max(1e-9, 1 - p)      # renormalise for the next gate
        det_gate.append(caught_gate); det_idx.append(caught_at); det_ts.append(caught_ts)

    defects["detect_gate"] = det_gate
    defects["detect_idx"] = det_idx
    defects["detect_ts"] = det_ts
    defects["escaped"] = defects["detect_idx"].isna()
    defects["detect_lag_stations"] = defects["detect_idx"] - defects["origin_idx"]
    defects["detect_lag_min"] = (defects["detect_ts"] - defects["created_ts"]) / 60.0

    # --- long-format station event table -----------------------------------
    codes = np.array([s.code for s in C.STATIONS])
    ev = pd.DataFrame({
        "unit_id": np.repeat(units["unit_id"].values, n_s),
        "unit_row": np.repeat(np.arange(n_u), n_s),
        "station_idx": np.tile(np.arange(1, n_s + 1), n_u),
        "station_code": np.tile(codes, n_u),
        "arrive_ts": arrive.ravel(),
        "start_ts": start.ravel(),
        "depart_ts": depart.ravel(),
        "cycle_time": cycle.ravel(),
        "blocked_s": blocked.ravel(),
        "starved_s": starved.ravel(),
        "torque": torque.ravel(),
        "vibration": vibration.ravel(),
        "temperature": temperature.ravel(),
        "manual_flag": manual_flag.ravel().astype(float),
        "oracle_condition": condition.ravel(),     # simulator ground truth only
        "oracle_flow": cond_flow.ravel(),          # simulator ground truth only
    })

    # --- apply sensor coverage --------------------------------------------
    tiers = np.array([s.tier for s in C.STATIONS])
    has_tq = np.array([s.has_torque for s in C.STATIONS])
    has_vb = np.array([s.has_vibration for s in C.STATIONS])
    has_tp = np.array([s.has_temp for s in C.STATIONS])
    is_manual = manual

    tq_ok = np.tile(has_tq & (tiers == "FULL"), n_u)
    vb_ok = np.tile(has_vb & (tiers == "FULL"), n_u)
    tp_ok = np.tile(has_tp & np.isin(tiers, ["FULL", "PARTIAL"]), n_u)
    mn_ok = np.tile(is_manual, n_u)

    ev.loc[~tq_ok, "torque"] = np.nan
    ev.loc[~vb_ok, "vibration"] = np.nan
    ev.loc[~tp_ok, "temperature"] = np.nan
    ev.loc[~mn_ok, "manual_flag"] = np.nan

    # random dropouts and multi-hour sensor outages
    for col in ("torque", "vibration", "temperature"):
        drop = rng.random(len(ev)) < 0.014
        ev.loc[drop, col] = np.nan
    outage_rows = []
    for j, s in enumerate(C.STATIONS):
        if s.tier != "FULL":
            continue
        for _ in range(rng.integers(0, 3)):
            u0 = int(rng.integers(0, max(1, n_u - 400)))
            span = int(rng.integers(120, 420))
            ch = str(rng.choice(["vibration", "torque", "temperature"]))
            mask = (ev["unit_row"].values >= u0) & (ev["unit_row"].values < u0 + span) \
                & (ev["station_idx"].values == s.idx)
            ev.loc[mask, ch] = np.nan
            outage_rows.append((s.code, ch, u0, span))

    # Record the gate verdict on the station event itself: the in-line CMM at
    # station 13 is upstream of the decision point, so the twin gets to use it.
    ev["gate_fail"] = 0.0
    det = defects[defects["detect_idx"].notna()]
    if len(det):
        key = set(zip(det["unit_id"], det["detect_idx"].astype(int)))
        pairs = list(zip(ev["unit_id"].values, ev["station_idx"].values))
        ev["gate_fail"] = np.fromiter((1.0 if p in key else 0.0 for p in pairs),
                                      dtype=float, count=len(ev))

    ev["timestamp"] = pd.to_datetime(ev["depart_ts"], unit="s")
    units["launch_epoch"] = units["launch_ts"].astype("int64") / 1e9

    ep_df = pd.DataFrame([dict(station=e.station, day=e.day, start_h=e.start_h,
                               ramp_h=e.ramp_h, hold_h=e.hold_h, peak=e.peak,
                               kind=e.kind, hero=e.hero, title=e.title, cause=e.cause)
                          for e in episodes])

    if verbose:
        esc = defects["escaped"].mean()
        print(f"  escaped to field: {esc:.1%}   sensor outages: {len(outage_rows)}")
    return units, ev, defects, ep_df
