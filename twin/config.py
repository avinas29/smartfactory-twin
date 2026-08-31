"""
SmartFactory Twin — line configuration.

Single source of truth for the simulated vehicle assembly line: station layout,
sensor coverage, buffers, quality gates and the economic constants used by the
business view. Everything downstream (generator, twin state, dashboard) reads
from here so the line can be re-shaped in one place.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
ARTIFACT_DIR = ROOT / "artifacts"

# --------------------------------------------------------------------------
# Production calendar
# --------------------------------------------------------------------------
N_DAYS = 28
DAY_ZERO = "2026-03-02"          # a Monday
SHIFTS = [("A", 6.0, 14.0), ("B", 14.0, 22.0)]   # start/end hour, local
BREAK_AFTER_H = 4.0              # unpaid line stop mid-shift
BREAK_MIN = 30
TAKT_S = 60.0                    # planned line takt

# Global calibration knobs. Nominal cycle times below are written in "work
# content" units; CYCLE_SCALE sets line utilisation, DEFECT_SCALE sets the
# plant's first-time-through quality. Both are tuned to realistic automotive
# figures (~90% utilisation, ~94% FTT) and are checked by tests.
CYCLE_SCALE = 0.845
DEFECT_SCALE = 0.075
# Body-shop faults are the ones that travel: they are created early and found
# late. Weighted so roughly half of all downstream escapes are body-attributable,
# which is where the twin's lead time is worth the most.
ZONE_DEFECT_WEIGHT = {"BODY": 1.55, "PAINT": 0.85, "ASSY": 0.82}

# Temporal split (no leakage: train strictly precedes val, val precedes test)
TRAIN_DAYS = (0, 20)             # days 0..19
VAL_DAYS = (20, 24)              # days 20..23 -> calibration + threshold choice
TEST_DAYS = (24, 28)             # days 24..27 -> reported metrics
DEMO_DAY = 27                    # the day the dashboard replays
APP_WINDOW_DAYS = 9              # how much history the dashboard keeps in memory

# --------------------------------------------------------------------------
# Vehicle models  (mix, work-content multiplier, defect-propensity multiplier)
# --------------------------------------------------------------------------
VEHICLE_MODELS = {
    "SDN-A": dict(share=0.45, work=1.00, complexity=1.00, label="Sedan A"),
    "SUV-B": dict(share=0.40, work=1.09, complexity=1.18, label="SUV B"),
    "EV-C":  dict(share=0.15, work=1.14, complexity=1.32, label="EV C"),
}

CREWS = ["Crew-1", "Crew-2", "Crew-3"]

# --------------------------------------------------------------------------
# Sensor tiers
# --------------------------------------------------------------------------
# Channels available at every station come from MES part-scan timestamps and the
# line-control PLC handshake -- they exist even on 1990s equipment.
ALWAYS_ON = ["cycle_time", "blocked_s", "starved_s"]

TIER_CHANNELS = {
    "FULL":    ["torque", "vibration", "temperature"],
    "PARTIAL": ["temperature"],
    "DARK":    [],
}
TIER_CONFIDENCE = {"FULL": 1.00, "PARTIAL": 0.72, "DARK": 0.45}

DEFECT_MODES = ["GEOM", "TORQUE", "PAINT", "FIT", "ELEC", "SEAL"]

# A fault expresses itself differently depending on what broke. The twin has to
# cope with all three: some faults never move the throughput needle at all.
#   flow  -> how much the fault shows up in cycle time / blocking
#   qual  -> how much it shows up in sensor signatures and defect rate
EPISODE_EXPRESSION = {
    "degradation": dict(flow=0.24, qual=1.00),   # wear: quiet on throughput, loud on quality
    "fixture":     dict(flow=1.00, qual=0.32),   # mechanical: slows the line first
    "operator":    dict(flow=0.60, qual=0.80),   # manual drift: some of both
}

# --------------------------------------------------------------------------
# Station specification
# --------------------------------------------------------------------------
@dataclass
class Station:
    idx: int                      # 1-based position on the line
    code: str
    name: str
    zone: str
    tier: str                     # FULL | PARTIAL | DARK
    cycle_s: float                # nominal cycle time for the reference model
    buffer_out: int = 2           # WIP slots between this station and the next
    has_torque: bool = False      # is torque a physically meaningful channel here
    has_vibration: bool = False
    has_temp: bool = False
    manual: bool = False          # operator completes a checklist entry
    transit_s: float = 0.0        # conveyor / store dwell before the next station
    gate: str | None = None       # quality gate id, if this station inspects
    gate_catches: tuple = ()      # defect modes this gate can detect
    creates: tuple = ()           # defect modes this station can introduce
    base_defect: float = 0.0      # baseline per-unit defect rate when healthy
    label: str = ""


def _s(idx, code, name, zone, tier, cycle_s, **kw) -> Station:
    return Station(idx=idx, code=code, name=name, zone=zone, tier=tier,
                   cycle_s=cycle_s, **kw)


STATIONS: list[Station] = [
    # ---------------- BODY SHOP (1-14) ----------------
    _s(1,  "BODY-01", "Underbody geometry set",        "BODY", "FULL",    54,
       has_torque=True, has_vibration=True, has_temp=True, creates=("GEOM",), base_defect=0.0035),
    _s(2,  "BODY-02", "Front floor weld",              "BODY", "FULL",    56,
       has_vibration=True, has_temp=True, creates=("GEOM",), base_defect=0.0030),
    _s(3,  "BODY-03", "Rear floor weld",               "BODY", "FULL",    55,
       has_vibration=True, has_temp=True, creates=("GEOM",), base_defect=0.0030),
    _s(4,  "BODY-04", "Underbody marriage weld",       "BODY", "FULL",    57,
       has_vibration=True, has_temp=True, creates=("GEOM",), base_defect=0.0040),
    _s(5,  "BODY-05", "Bodyside LH framing",           "BODY", "FULL",    58,
       has_torque=True, has_vibration=True, has_temp=True, creates=("GEOM",), base_defect=0.0038),
    _s(6,  "BODY-06", "Bodyside RH framing",           "BODY", "FULL",    58,
       has_torque=True, has_vibration=True, has_temp=True, creates=("GEOM",), base_defect=0.0038),
    _s(7,  "BODY-07", "Roof laser braze",              "BODY", "FULL",    53,
       has_vibration=True, has_temp=True, creates=("GEOM",), base_defect=0.0028),
    _s(8,  "BODY-08", "Underbody bolting (robotic nutrunner)", "BODY", "FULL", 56,
       has_torque=True, has_vibration=True, has_temp=True,
       creates=("TORQUE",), base_defect=0.0042,
       label="Torque-critical joint. Failure surfaces at the ASSY-27 audit."),
    _s(9,  "BODY-09", "Respot weld cell 1",            "BODY", "PARTIAL", 55,
       has_vibration=True, has_temp=True, creates=("GEOM",), base_defect=0.0026),
    _s(10, "BODY-10", "Respot weld cell 2",            "BODY", "FULL",    55,
       has_vibration=True, has_temp=True, creates=("GEOM",), base_defect=0.0026),
    _s(11, "BODY-11", "Hem & closure assembly",        "BODY", "PARTIAL", 57,
       has_torque=True, has_temp=True, creates=("GEOM", "FIT"), base_defect=0.0044),
    _s(12, "BODY-12", "Metal finish (manual)",         "BODY", "DARK",    59,
       manual=True, creates=("GEOM",), base_defect=0.0032),
    _s(13, "BODY-13", "Geometry gate — in-line CMM",   "BODY", "FULL",    52,
       has_temp=True, gate="G-BODY", gate_catches=("GEOM",),
       label="Upstream gate. Its result is an input to the twin, not a target."),
    _s(14, "BODY-14", "Closure fitment — manual torque wrench", "BODY", "DARK", 58,
       manual=True, creates=("FIT", "TORQUE"), base_defect=0.0050,
       label="No vibration or torque telemetry. Cycle time + checklist only."),

    # ---------------- PAINT SHOP (15-24) ----------------
    _s(15, "PAINT-15", "Pretreatment & e-coat dip",    "PAINT", "PARTIAL", 56,
       has_temp=True, creates=("PAINT",), base_defect=0.0030),
    _s(16, "PAINT-16", "E-coat cure oven",             "PAINT", "FULL",    54,
       has_temp=True, creates=("PAINT",), base_defect=0.0022),
    _s(17, "PAINT-17", "Seam sealer (robot)",          "PAINT", "FULL",    57,
       has_vibration=True, has_temp=True, creates=("SEAL",), base_defect=0.0034),
    _s(18, "PAINT-18", "Sealer manual touch-up",       "PAINT", "DARK",    59,
       manual=True, creates=("SEAL",), base_defect=0.0040),
    _s(19, "PAINT-19", "Primer booth",                 "PAINT", "FULL",    55,
       has_temp=True, creates=("PAINT",), base_defect=0.0030),
    _s(20, "PAINT-20", "Primer cure oven",             "PAINT", "FULL",    53,
       has_temp=True, creates=("PAINT",), base_defect=0.0020),
    _s(21, "PAINT-21", "Base coat booth",              "PAINT", "FULL",    58,
       has_temp=True, creates=("PAINT",), base_defect=0.0036),
    _s(22, "PAINT-22", "Clear coat booth",             "PAINT", "FULL",    58,
       has_temp=True, creates=("PAINT",), base_defect=0.0036),
    _s(23, "PAINT-23", "Clear cure oven",              "PAINT", "FULL",    53,
       has_temp=True, creates=("PAINT",), base_defect=0.0018),
    _s(24, "PAINT-24", "Paint inspection & polish",    "PAINT", "PARTIAL", 60,
       has_temp=True, manual=True, gate="G-PAINT", gate_catches=("PAINT",),
       buffer_out=60, transit_s=3600,
       label="Painted-body store downstream: ~60 bodies of decoupling buffer."),

    # ---------------- FINAL ASSEMBLY (25-42) ----------------
    _s(25, "ASSY-25", "Trim — cockpit module",         "ASSY", "FULL",    57,
       has_torque=True, has_temp=True, creates=("FIT",), base_defect=0.0030),
    _s(26, "ASSY-26", "Trim — harness & headliner",    "ASSY", "PARTIAL", 58,
       has_temp=True, creates=("ELEC", "FIT"), base_defect=0.0038),
    _s(27, "ASSY-27", "Chassis marriage & underbody torque audit", "ASSY", "FULL", 59,
       has_torque=True, has_vibration=True, has_temp=True,
       gate="G-TORQUE", gate_catches=("TORQUE",), creates=("TORQUE",), base_defect=0.0026,
       label="Where an upstream fastening fault finally becomes visible."),
    _s(28, "ASSY-28", "Front suspension & subframe",   "ASSY", "FULL",    58,
       has_torque=True, has_vibration=True, has_temp=True, creates=("TORQUE",), base_defect=0.0032),
    _s(29, "ASSY-29", "Rear suspension",               "ASSY", "FULL",    57,
       has_torque=True, has_vibration=True, has_temp=True, creates=("TORQUE",), base_defect=0.0030),
    _s(30, "ASSY-30", "Exhaust & heat shields",        "ASSY", "DARK",    56,
       manual=True, creates=("FIT",), base_defect=0.0034),
    _s(31, "ASSY-31", "Fuel tank / HV battery install", "ASSY", "FULL",   60,
       has_torque=True, has_vibration=True, has_temp=True,
       creates=("TORQUE", "ELEC"), base_defect=0.0040),
    _s(32, "ASSY-32", "Brake lines & fluid fill",      "ASSY", "FULL",    56,
       has_torque=True, has_temp=True, creates=("SEAL",), base_defect=0.0030),
    _s(33, "ASSY-33", "Steering column & pedal box",   "ASSY", "PARTIAL", 55,
       has_torque=True, creates=("TORQUE",), base_defect=0.0028),
    _s(34, "ASSY-34", "Doors re-fit",                  "ASSY", "DARK",    59,
       manual=True, creates=("FIT",), base_defect=0.0046),
    _s(35, "ASSY-35", "Glass & urethane bonding",      "ASSY", "FULL",    57,
       has_temp=True, has_vibration=True, creates=("SEAL",), base_defect=0.0034),
    _s(36, "ASSY-36", "Seats & interior trim",         "ASSY", "DARK",    58,
       manual=True, creates=("FIT",), base_defect=0.0036),
    _s(37, "ASSY-37", "Wheels & hub torque",           "ASSY", "FULL",    54,
       has_torque=True, has_vibration=True, has_temp=True, creates=("TORQUE",), base_defect=0.0028),
    _s(38, "ASSY-38", "Bumpers & fascia",              "ASSY", "PARTIAL", 55,
       has_torque=True, creates=("FIT",), base_defect=0.0032),
    _s(39, "ASSY-39", "Fluids & first fill",           "ASSY", "FULL",    56,
       has_temp=True, creates=("SEAL",), base_defect=0.0026),
    _s(40, "ASSY-40", "ECU flash & DTC scan",          "ASSY", "FULL",    57,
       has_temp=True, gate="G-ELEC", gate_catches=("ELEC",), creates=("ELEC",), base_defect=0.0022),
    _s(41, "ASSY-41", "Roll & brake test",             "ASSY", "FULL",    60,
       has_vibration=True, has_temp=True, gate="G-DYN", gate_catches=("TORQUE", "SEAL")),
    _s(42, "ASSY-42", "Final inspection & water test", "ASSY", "PARTIAL", 62,
       manual=True, gate="G-EOL", gate_catches=("GEOM", "FIT", "SEAL", "PAINT", "TORQUE")),
]

STATION_BY_CODE = {s.code: s for s in STATIONS}
STATION_BY_IDX = {s.idx: s for s in STATIONS}
N_STATIONS = len(STATIONS)

ZONES = {
    "BODY":  dict(label="Body Construction", first=1,  last=14),
    "PAINT": dict(label="Paint Shop",        first=15, last=24),
    "ASSY":  dict(label="Final Assembly",    first=25, last=42),
}

# The twin scores a unit the moment it clears the body shop. Everything the
# model sees happens at or before this station; every target event happens after.
DECISION_STATION = 14
DOWNSTREAM_GATES = [s.idx for s in STATIONS if s.gate and s.idx > DECISION_STATION]
UPSTREAM_GATES = [s.idx for s in STATIONS if s.gate and s.idx <= DECISION_STATION]

# --------------------------------------------------------------------------
# Gate detection probabilities  gate_id -> {mode: p(detect | defect present)}
# --------------------------------------------------------------------------
GATE_SENSITIVITY = {
    "G-BODY":  {"GEOM": 0.55},
    "G-PAINT": {"PAINT": 0.78},
    "G-TORQUE": {"TORQUE": 0.72},
    "G-ELEC":  {"ELEC": 0.83},
    "G-DYN":   {"TORQUE": 0.22, "SEAL": 0.25},
    "G-EOL":   {"GEOM": 0.52, "FIT": 0.70, "SEAL": 0.68, "PAINT": 0.40, "TORQUE": 0.20},
}

# --------------------------------------------------------------------------
# Scripted degradation episodes.
#
# `hero` episodes are the demo narrative and sit inside the *test* window, so
# nothing about them was memorised during training. Background episodes are
# scattered by the generator across all days to give the model something to
# learn from.
# --------------------------------------------------------------------------
@dataclass
class Episode:
    station: str
    day: int
    start_h: float
    ramp_h: float                 # hours to reach peak severity
    hold_h: float                 # hours held at peak
    peak: float                   # latent condition at peak, 0..1
    kind: str = "degradation"     # degradation | fixture | operator
    hero: bool = False
    title: str = ""
    cause: str = ""

HERO_EPISODES: list[Episode] = [
    Episode(station="BODY-08", day=DEMO_DAY, start_h=7.17, ramp_h=2.6, hold_h=6.0,
            peak=0.92, kind="degradation", hero=True,
            title="Spindle bearing degradation",
            cause="Nutrunner spindle bearing wear — vibration and torque scatter "
                  "climb together while mean torque stays inside the PLC window."),
    Episode(station="BODY-14", day=DEMO_DAY, start_h=13.6, ramp_h=1.8, hold_h=7.0,
            peak=0.95, kind="operator", hero=True,
            title="Manual fitment drift (sensor-poor station)",
            cause="Torque wrench out of calibration on a manual station with no "
                  "vibration or torque telemetry — visible only as cycle-time "
                  "creep and a rising checklist flag rate."),
    Episode(station="ASSY-31", day=DEMO_DAY, start_h=8.6, ramp_h=1.6, hold_h=5.0,
            peak=0.62, kind="fixture", hero=True,
            title="Battery-pack fixture slowdown",
            cause="Lift-table fixture indexing slowly on EV-C builds — the "
                  "station becomes the line constraint before WIP shows it."),
]

# --------------------------------------------------------------------------
# Economics — every number in the business view resolves to these constants.
# All are stated as assumptions in the README, not as measured facts.
# --------------------------------------------------------------------------
ECONOMICS = dict(
    units_per_hour=60,
    production_hours_per_day=16,
    production_days_per_year=240,
    downtime_cost_per_hour=22_000,      # USD, one line fully stopped
    contribution_margin_per_unit=1_150,  # gross margin on one additional vehicle
    rework_cost_in_station=180,         # caught at the originating station
    rework_cost_at_gate=740,            # caught at a downstream gate
    rework_cost_post_eol=2_600,         # caught after final inspection / in yard
    warranty_cost_escaped=5_400,        # field failure, incl. logistics
    inspection_cost_per_unit=26,        # targeted re-inspection of a flagged unit
    inspection_capacity_per_shift=25,   # how many extra inspections the line can absorb
    sensor_retrofit_cost=18_500,        # per station, installed in a maintenance window
    inspection_effectiveness=0.70,      # P(a targeted re-inspection finds the fault)
    platform_cost_year1=520_000,        # build, MES/PLC integration, pilot,
                                        # change management for the first line
    platform_cost_per_line=95_000,      # each additional line, run-rate included
)
