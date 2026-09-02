/*
 * Business proposal deck.
 *
 *   node docs/build_deck.js
 *
 * Figures are read from docs/FACTS.json, which the pipeline writes, so the deck
 * cannot drift from what the prototype actually measured.
 */
const pptxgen = require("pptxgenjs");
const fs = require("fs");
const path = require("path");

const DOCS = __dirname;
const F = JSON.parse(fs.readFileSync(path.join(DOCS, "FACTS.json"), "utf8"));
const { detection: D, model: M, traceback: TB, virtual_sensor: VS,
        forecast: FC, economics: EC, line: LINE } = F;
const Q = EC.quality, TH = EC.throughput;

const img = (n) => path.join(DOCS, "assets", n);
const pc = (x, d = 0) => (100 * x).toFixed(d) + "%";
const usd = (x) => "$" + Math.round(x).toLocaleString("en-US");
const mil = (x) => "$" + (x / 1e6).toFixed(2) + "M";

// Accenture purple, carried through from the Round 1 deck. Dominant deep
// purple, one sharp accent, status colours reserved for status only.
const C = {
  deep: "2B0047", purple: "A100FF", lilac: "D9B3FF",
  ink: "16171C", mid: "4A4F5C", soft: "8A90A0",
  paper: "FFFFFF", wash: "F7F3FC", rule: "E4E1EA",
  ok: "0F8A4A", warn: "B8730A", bad: "C62334",
};
const FONT = "Calibri", HEAD = "Cambria";

const pres = new pptxgen();
pres.layout = "LAYOUT_WIDE";           // 13.3 x 7.5 in
pres.author = "Team PeakBusters";
pres.title = "SmartFactory Twin — Business Proposal";
const W = 13.3, H = 7.5, MX = 0.62;

/* ── helpers ─────────────────────────────────────────────────────────── */
function darkSlide() {
  const s = pres.addSlide();
  s.background = { color: C.deep };
  return s;
}
function lightSlide(title, kicker) {
  const s = pres.addSlide();
  s.background = { color: C.paper };
  if (kicker) s.addText(kicker, {
    x: MX, y: 0.42, w: 8, h: 0.26, isTextBox: true, margin: 0,
    fontFace: FONT, fontSize: 11, bold: true, color: C.purple, charSpacing: 1.2,
  });
  // Keep every title on one line. A wrapped 32pt title drops its second line to
  // within about 0.1" of the content below it, which reads as a collision.
  const size = title.length <= 48 ? 32 : title.length <= 62 ? 27 : 24;
  s.addText(title, {
    x: MX, y: kicker ? 0.70 : 0.52, w: W - 2 * MX, h: 0.72, isTextBox: true, margin: 0,
    fontFace: HEAD, fontSize: size, bold: true, color: C.deep,
  });
  return s;
}
// The repeated motif: a soft-tinted card with a rounded corner. No edge stripes.
function card(s, x, y, w, h, fill) {
  s.addShape(pres.ShapeType.roundRect, {
    x, y, w, h, rectRadius: 0.08,
    fill: { color: fill || C.wash },
    line: { color: C.rule, width: 0.75 },
  });
}
function stat(s, x, y, w, value, label, sub, colour) {
  card(s, x, y, w, 1.42);
  s.addText(value, {
    x: x + 0.18, y: y + 0.14, w: w - 0.36, h: 0.55, isTextBox: true, margin: 0,
    fontFace: HEAD, fontSize: 30, bold: true, color: colour || C.deep,
  });
  s.addText(label, {
    x: x + 0.18, y: y + 0.70, w: w - 0.36, h: 0.26, isTextBox: true, margin: 0,
    fontFace: FONT, fontSize: 11.5, bold: true, color: C.ink,
  });
  if (sub) s.addText(sub, {
    x: x + 0.18, y: y + 0.96, w: w - 0.36, h: 0.36, isTextBox: true, margin: 0,
    fontFace: FONT, fontSize: 9.5, color: C.soft,
  });
}
function body(s, text, x, y, w, h, size) {
  s.addText(text, {
    x, y, w, h, isTextBox: true, margin: 0, fontFace: FONT,
    fontSize: size || 13.5, color: C.mid, lineSpacing: 19,
  });
}
function note(s, rich, x, y, w, h) {
  card(s, x, y, w, h);
  s.addText(rich, {
    x: x + 0.22, y: y + 0.16, w: w - 0.44, h: h - 0.32, isTextBox: true, margin: 0,
    fontFace: FONT, fontSize: 12, color: C.ink, lineSpacing: 18,
  });
}
function table(s, rows, x, y, w, colW, opts = {}) {
  s.addTable(rows, {
    x, y, w, colW, border: { type: "solid", color: C.rule, pt: 0.5 },
    fontFace: FONT, fontSize: opts.fontSize || 11.5, color: C.mid,
    valign: "middle", rowH: opts.rowH || 0.36,
    autoPage: false,
  });
}
const th = (t) => ({ text: t, options: { bold: true, color: "FFFFFF", fill: { color: C.deep }, fontSize: 10.5 } });
const td = (t, o = {}) => ({ text: t, options: { color: o.color || C.mid, bold: !!o.bold, fontSize: o.fontSize || 11.5, italic: !!o.italic } });

/* ── 1. title ────────────────────────────────────────────────────────── */
{
  const s = darkSlide();
  s.addShape(pres.ShapeType.ellipse, {
    x: 9.6, y: -1.5, w: 6.2, h: 6.2, fill: { color: C.purple, transparency: 82 }, line: { width: 0 },
  });
  s.addText("SmartFactory Twin", {
    x: MX, y: 2.0, w: 9.4, h: 1.0, isTextBox: true, margin: 0,
    fontFace: HEAD, fontSize: 52, bold: true, color: "FFFFFF",
  });
  s.addText("Don't wait for the defect.", {
    x: MX, y: 3.05, w: 9.4, h: 0.6, isTextBox: true, margin: 0,
    fontFace: HEAD, fontSize: 27, bold: true, color: C.lilac,
  });
  s.addText(
    "A flow-level digital twin for a vehicle assembly line. It detects a station going bad while it is " +
    "still going bad, traces a late-discovered defect back to the station that most likely caused it, and " +
    "scopes containment to the vehicles actually affected — on a brownfield line where a seventh of the " +
    "stations have no process sensors at all.",
    { x: MX, y: 3.85, w: 8.4, h: 1.3, isTextBox: true, margin: 0,
      fontFace: FONT, fontSize: 14, color: "C9C2D6", lineSpacing: 21 });
  s.addText("Business Proposal   ·   Team PeakBusters   ·   Accenture Innovation Challenge 2026   ·   Problem Track 4, Round 2",
    { x: MX, y: 6.5, w: 11.5, h: 0.3, isTextBox: true, margin: 0,
      fontFace: FONT, fontSize: 11, color: "9B8FAD" });
  s.addNotes("Opening. The line fails in two ways and reports both after the loss is booked. " +
             "This deck is built around one incident and what the twin does about it.");
}

/* ── 2. the problem ──────────────────────────────────────────────────── */
{
  const s = lightSlide("A fault found at the gate is a fault found too late", "THE PROBLEM");
  body(s, "At 07:12 a nutrunner spindle at BODY-08 begins to wear. Mean torque stays inside the PLC " +
          "acceptance window the whole time — only the scatter grows — so every existing limit check " +
          "stays green.", MX, 1.62, 11.9, 0.9);
  const cells = [
    ["07:12", "Spindle begins to wear", "Every PLC limit check green", C.soft],
    ["~09:30", "First body rejected at ASSY-27", "90 minutes and 240 vehicles later", C.bad],
  ];
  cells.forEach(([t, what, sub, col], i) => {
    const x = MX + i * 6.15;
    card(s, x, 2.72, 5.75, 1.28);
    s.addText(t, { x: x + 0.22, y: 2.88, w: 1.5, h: 0.4, isTextBox: true, margin: 0,
      fontFace: HEAD, fontSize: 22, bold: true, color: col });
    s.addText(what, { x: x + 1.85, y: 2.90, w: 3.7, h: 0.34, isTextBox: true, margin: 0,
      fontFace: FONT, fontSize: 13.5, bold: true, color: C.ink });
    s.addText(sub, { x: x + 1.85, y: 3.26, w: 3.7, h: 0.55, isTextBox: true, margin: 0,
      fontFace: FONT, fontSize: 11, color: C.soft });
  });
  s.addText("→", { x: 6.15, y: 3.05, w: 0.5, h: 0.5, isTextBox: true, margin: 0,
    fontFace: FONT, fontSize: 24, bold: true, color: C.purple, align: "center" });
  note(s, [
    { text: "By then the useful question has already changed. ", options: { bold: true, color: C.deep } },
    { text: "It is no longer “what is wrong?” but “how many, and where are they now?”", options: {} },
  ], MX, 4.32, 11.9, 0.78);
  body(s, "One error has become a rework campaign, a containment exercise and warranty exposure — " +
          "and the station that caused it has been running normally on the MES screen all shift.",
       MX, 5.35, 11.9, 0.9);
  s.addNotes("The gap is not sensing. Nobody is modelling each station against its own qualified normal.");
}

/* ── 3. why conventional monitoring fails ────────────────────────────── */
{
  const s = lightSlide("Four systems watch this line. None of them see it.", "WHY IT IS MISSED");
  const rows = [
    [th("Approach"), th("What it misses")],
    [td("PLC limit checks", { bold: true }), td("Watch the mean, not the variance. A worn spindle whose scatter has doubled sits inside every acceptance window.")],
    [td("MES throughput dashboards", { bold: true }), td("Report the constraint after WIP has piled up. A quality fault that does not slow the line is invisible.")],
    [td("End-of-line inspection", { bold: true }), td("Correct but late. It finds the batch, not the cause — and not before the batch exists.")],
    [td("Full-IoT digital twins", { bold: true }), td("Assume complete instrumentation. On a brownfield line the uninstrumented stations are usually the manual ones where errors originate.")],
  ];
  table(s, rows, MX, 1.72, 11.9, [3.5, 8.4], { rowH: 0.62 });
  note(s, [
    { text: "The gap is not sensing. ", options: { bold: true, color: C.deep } },
    { text: "It is that nobody is modelling each station against its own qualified normal, keeping a record " +
            "of which vehicle met which station in which condition, and using that record when a gate " +
            "finally rejects something.", options: {} },
  ], MX, 5.05, 11.9, 0.95);
  s.addNotes("This is the wedge: the data already exists, it is just not being modelled per station.");
}

/* ── 4. the twin ─────────────────────────────────────────────────────── */
{
  const s = lightSlide("A twin of flow and quality — not of geometry", "THE SOLUTION");
  const caps = [
    ["Per-station condition", "Each station charted against its own frozen, qualified baseline.", "Detects a station leaving its envelope while production is still running."],
    ["Unit genealogy", "For every vehicle: which stations it passed, and what condition each was in at that moment.", "Turns a late rejection into ranked suspects and an exact affected-unit list."],
    ["Flow rolled forward", "Station capacities projected two hours ahead.", "Names the station that becomes the constraint, with time to rebalance."],
  ];
  caps.forEach(([t, d, w], i) => {
    const x = MX + i * 4.06;
    card(s, x, 1.68, 3.75, 2.42);
    s.addShape(pres.ShapeType.ellipse, { x: x + 0.22, y: 1.88, w: 0.42, h: 0.42,
      fill: { color: C.purple }, line: { width: 0 } });
    s.addText(String(i + 1), { x: x + 0.22, y: 1.90, w: 0.42, h: 0.38, isTextBox: true, margin: 0,
      fontFace: HEAD, fontSize: 15, bold: true, color: "FFFFFF", align: "center" });
    s.addText(t, { x: x + 0.78, y: 1.90, w: 2.8, h: 0.36, isTextBox: true, margin: 0,
      fontFace: HEAD, fontSize: 15, bold: true, color: C.deep });
    s.addText(d, { x: x + 0.22, y: 2.46, w: 3.32, h: 0.92, isTextBox: true, margin: 0,
      fontFace: FONT, fontSize: 11.5, color: C.mid, lineSpacing: 15 });
    s.addText(w, { x: x + 0.22, y: 3.34, w: 3.32, h: 0.68, isTextBox: true, margin: 0,
      fontFace: FONT, fontSize: 11, bold: true, color: C.purple, lineSpacing: 14 });
  });
  const st = [
    [`${D.body08.toFixed(0)} min`, "Detection", "BODY-08, vs ~90 min to first reject"],
    [`${D.alerts_per_shift}/shift`, "Alert load", `across all ${LINE.stations} stations`],
    [pc(TB.by_confidence.high.top1), "Attribution", "top-1 correct at high confidence"],
    [VS.auc.toFixed(2), "Dark stations", "virtual-sensing AUC, unseen stations"],
  ];
  st.forEach(([v, l, sub], i) => stat(s, MX + i * 3.04, 4.42, 2.8, v, l, sub));
  s.addNotes("Three capabilities a dashboard does not have. The numbers below are all measured on a held-out window.");
}

/* ── 5. architecture ─────────────────────────────────────────────────── */
{
  const s = lightSlide("Read-only in, advisory out", "ARCHITECTURE");
  const band = (y, h, title, sub, fill, txt) => {
    s.addShape(pres.ShapeType.roundRect, { x: MX, y, w: 11.9, h, rectRadius: 0.06,
      fill: { color: fill }, line: { color: C.rule, width: 0.75 } });
    s.addText(title, { x: MX + 0.26, y: y + 0.12, w: 3.4, h: 0.32, isTextBox: true, margin: 0,
      fontFace: HEAD, fontSize: 14, bold: true, color: txt });
    s.addText(sub, { x: MX + 3.8, y: y + 0.13, w: 7.8, h: h - 0.24, isTextBox: true, margin: 0,
      fontFace: FONT, fontSize: 11.5, color: txt === "FFFFFF" ? "D8CFE6" : C.mid, lineSpacing: 15 });
  };
  band(1.68, 0.62, "Plant systems", "MES part scans · PLC handshake · process telemetry · quality gates · operator checklists · ERP lots", C.wash, C.ink);
  s.addText("▼", { x: 6.4, y: 2.34, w: 0.5, h: 0.24, isTextBox: true, margin: 0, fontSize: 12, color: C.purple, align: "center" });
  band(2.60, 0.62, "Digital twin state", "per-station condition · unit genealogy · flow model", C.deep, "FFFFFF");
  s.addText("▼", { x: 6.4, y: 3.26, w: 0.5, h: 0.24, isTextBox: true, margin: 0, fontSize: 12, color: C.purple, align: "center" });
  const eng = [
    ["Anomaly detection", "frozen-baseline SPC + virtual sensors"],
    ["Defect-risk model", "calibrated, capacity-aware"],
    ["Ranked traceback", "genealogy contrast + FMEA prior"],
    ["Flow forecast", "two-hour capacity roll-forward"],
  ];
  eng.forEach(([t, d], i) => {
    const x = MX + i * 3.04;
    card(s, x, 3.52, 2.8, 0.94);
    s.addText(t, { x: x + 0.16, y: 3.62, w: 2.5, h: 0.28, isTextBox: true, margin: 0,
      fontFace: FONT, fontSize: 12, bold: true, color: C.deep });
    s.addText(d, { x: x + 0.16, y: 3.90, w: 2.5, h: 0.48, isTextBox: true, margin: 0,
      fontFace: FONT, fontSize: 10, color: C.soft, lineSpacing: 13 });
  });
  s.addText("▼", { x: 6.4, y: 4.52, w: 0.5, h: 0.24, isTextBox: true, margin: 0, fontSize: 12, color: C.purple, align: "center" });
  band(4.80, 0.62, "Risk & action engine", "four action classes · confidence-gated · human-in-the-loop · every decision logged", C.wash, C.ink);
  note(s, [
    { text: "Nothing is written back to the control system. ", options: { bold: true, color: C.deep } },
    { text: "Every recommendation is an action a human already has the authority to take — which keeps the " +
            "twin outside the safety envelope, and outside the change-control burden that would otherwise " +
            "dominate deployment. Footprint: one process and a browser.", options: {} },
  ], MX, 5.62, 11.9, 0.95);
  s.addNotes("Advisory-only is a deliberate architectural choice, not a limitation of the prototype.");
}

/* ── 6. hero incident ────────────────────────────────────────────────── */
{
  const s = lightSlide("BODY-08: the twin escalates as the evidence accumulates", "HERO INCIDENT");
  const rows = [
    [th("Time"), th("What happens"), th("What the twin does")],
    [td("07:12", { bold: true }), td("Spindle bearing begins to wear. Mean torque still inside the PLC window."), td("Nothing yet — correctly.", { color: C.soft })],
    [td("07:43", { bold: true }), td("Vibration and torque scatter climbing together."), td("Raises MONITOR. Evidence real, not yet worth stopping work.", { color: C.warn, bold: true })],
    [td("07:58", { bold: true }), td("Deviation sustained for 21 cycles."), td("Escalates to IMMEDIATE at 8.0σ, led by vibration at 6.2σ.", { color: C.bad, bold: true })],
    [td("~09:30", { bold: true }), td("First bodies rejected at ASSY-27."), td("Already contained. This is when a conventional line would first react.", { color: C.soft })],
  ];
  table(s, rows, MX, 1.70, 11.9, [1.15, 5.35, 5.4], { rowH: 0.52 });
  s.addImage({ path: img("02-line-escalated.png"), x: MX, y: 4.28, w: 7.4, h: 2.55 });
  note(s, [
    { text: "Nothing was added but fifteen more minutes of evidence.\n", options: { bold: true, color: C.deep } },
    { text: "The card names the station, the evidence, the action, and where the fault will surface if " +
            "ignored — and carries an accept/dismiss decision that is logged.", options: {} },
  ], 8.35, 4.28, 4.17, 1.6);
  s.addNotes("This is the central demo moment. The escalation is driven by accumulated evidence, not by a timer.");
}

/* ── 7. traceback ────────────────────────────────────────────────────── */
{
  const s = lightSlide("When a gate does reject, the twin already knows where to look", "DELAYED DEFECTS");
  s.addImage({ path: img("03-traceback.png"), x: MX, y: 1.68, w: 7.5, h: 4.05 });
  stat(s, 8.42, 1.68, 4.1, "84%", "of the evidence points at BODY-08", "confidence HIGH — a single dominant suspect", C.bad);
  stat(s, 8.42, 3.24, 4.1, "238 units", "passed during 272 min of drift", "86 of them still inside the plant", C.deep);
  note(s, [
    { text: "Ranked attribution, not root-cause prediction. ", options: { bold: true, color: C.deep } },
    { text: "A difference-in-means with a domain prior, presented to an engineer as evidence to check.",
      options: {} },
  ], 8.42, 4.80, 4.1, 0.93);
  body(s, "Containment is scoped to units, not batches — the vehicles that actually passed the station " +
          "while it was out of control.", MX, 5.92, 7.5, 0.6, 12);
  s.addNotes("Round 1 promised containment scoped to units rather than batches. This is it.");
}

/* ── 8. traceback accuracy (the credibility slide) ───────────────────── */
{
  const s = lightSlide("We measured how often the attribution is right", "DOES IT ACTUALLY WORK?");
  body(s, "The simulator records which station actually created every defect. The twin never sees that " +
          "column. Sweeping probe times across the held-out window and comparing the leading suspect " +
          "against the true origin turns “is this causation or correlation?” into a measurement.",
       MX, 1.62, 11.9, 0.85);
  s.addChart(pres.ChartType.bar, [{
    name: "Top-1 correct",
    labels: ["HIGH confidence", "MEDIUM", "LOW", "Random guess"],
    values: [TB.by_confidence.high.top1, TB.by_confidence.medium.top1,
             TB.by_confidence.low.top1, TB.random_baseline_top1],
  }], {
    x: MX, y: 2.62, w: 6.5, h: 3.3, barDir: "bar",
    showTitle: true, title: "Leading suspect correct, by the confidence the twin reported",
    titleFontFace: FONT, titleFontSize: 12, titleColor: C.deep,
    chartColors: [C.purple], showLegend: false,
    showValue: true, dataLabelPosition: "outEnd", dataLabelFormatCode: "0%",
    dataLabelFontFace: FONT, dataLabelFontSize: 11, dataLabelColor: C.ink,
    catAxisLabelFontFace: FONT, catAxisLabelFontSize: 11, catAxisLabelColor: C.mid,
    valAxisLabelFontFace: FONT, valAxisLabelFontSize: 10, valAxisLabelColor: C.soft,
    valAxisMaxVal: 0.8, valAxisLabelFormatCode: "0%",
    valGridLine: { color: C.rule, size: 0.75 }, catGridLine: { style: "none" },
  });
  const rows = [
    [th("Confidence"), th("Windows"), th("Top-1"), th("Top-3")],
    [td("HIGH", { bold: true, color: C.ok }), td(String(TB.by_confidence.high.n)), td(pc(TB.by_confidence.high.top1), { bold: true }), td(pc(TB.by_confidence.high.top3))],
    [td("MEDIUM", { bold: true, color: C.warn }), td(String(TB.by_confidence.medium.n)), td(pc(TB.by_confidence.medium.top1)), td(pc(TB.by_confidence.medium.top3))],
    [td("LOW", { bold: true, color: C.soft }), td(String(TB.by_confidence.low.n)), td(pc(TB.by_confidence.low.top1)), td(pc(TB.by_confidence.low.top3))],
    [td("All windows", { bold: true }), td(String(TB.overall.n)), td(pc(TB.overall.top1), { bold: true }), td(pc(TB.overall.top3))],
    [td("Random station", { italic: true }), td("—"), td(pc(TB.random_baseline_top1), { italic: true }), td("—")],
  ];
  table(s, rows, 7.5, 2.62, 5.02, [1.72, 1.1, 1.1, 1.1], { rowH: 0.42 });
  note(s, [
    { text: "The number that matters is not 46%. ", options: { bold: true, color: C.deep } },
    { text: "It is that accuracy tracks the confidence the twin reported at the time. An attribution engine " +
            "that always names a station will eventually send a crew to a healthy one.", options: {} },
  ], 7.5, 5.42, 5.02, 1.15);
  s.addNotes("This is the single strongest credibility slide. It answers 'how do you know it is not correlation'.");
}

/* ── 9. sensor-poor stations ─────────────────────────────────────────── */
{
  const s = lightSlide("A seventh of the line has no process sensors. It is still covered.", "BROWNFIELD REALITY");
  const rows = [
    [th("Coverage"), th("Stations"), th("What the twin can read")],
    [td("FULL", { bold: true, color: C.ok }), td(`${LINE.coverage.FULL.stations} (${pc(LINE.coverage.FULL.share)})`), td("cycle time, blocking/starving, vibration, torque, temperature")],
    [td("PARTIAL", { bold: true, color: C.warn }), td(`${LINE.coverage.PARTIAL.stations} (${pc(LINE.coverage.PARTIAL.share)})`), td("cycle time, blocking/starving, temperature")],
    [td("DARK", { bold: true, color: C.soft }), td(`${LINE.coverage.DARK.stations} (${pc(LINE.coverage.DARK.share)})`), td("cycle time, blocking/starving, operator checklist")],
  ];
  table(s, rows, MX, 1.70, 11.9, [2.2, 2.2, 7.5], { rowH: 0.46 });
  note(s, [
    { text: "Cycle time and blocking/starving exist on 1990s equipment. ", options: { bold: true, color: C.deep } },
    { text: "They come from MES part-scan timestamps and the line-control PLC handshake. That is the entire " +
            "reason a dark station can be scored at all — and why deployment needs no new hardware.", options: {} },
  ], MX, 3.42, 11.9, 0.86);
  s.addText("Virtual sensing", { x: MX, y: 4.52, w: 6, h: 0.34, isTextBox: true, margin: 0,
    fontFace: HEAD, fontSize: 17, bold: true, color: C.deep });
  body(s, "On instrumented stations we can see both the rich evidence and the thin evidence every station " +
          "produces. So we learn the mapping from thin to rich where both exist, and apply it where only " +
          "the thin half does. Validation holds out whole stations — because that is the deployment question.",
       MX, 4.94, 6.6, 1.3, 12.5);
  const vs = [
    [VS.auc.toFixed(2), "Held-out-station AUC", "stations the model never saw"],
    [VS.ap.toFixed(2), "PR-AUC", `against a ${VS.base.toFixed(2)} base rate`],
    [VS.trust.toFixed(2), "Trust weight", "derived from the validated score"],
  ];
  vs.forEach(([v, l, sub], i) => stat(s, 7.5 + i * 1.72, 4.60, 1.58, v, l, sub));
  s.addNotes("The validated score becomes the blending weight — a mapping that did not generalise cannot raise an alarm.");
}

/* ── 10. confidence ──────────────────────────────────────────────────── */
{
  const s = lightSlide("Strong evidence → act.  Weak evidence → don't overreact.", "TRUST");
  body(s, `BODY-14 is a manual closure-fitment station with no vibration or torque telemetry. It drifts on ` +
          `the same day. The twin detects it — but ${D.body14.toFixed(0)} minutes in rather than ` +
          `${D.body08.toFixed(0)}, and at 43% data confidence.`, MX, 1.62, 11.9, 0.8);
  const comp = [
    ["BODY-08", "FULL coverage", `${D.body08.toFixed(0)} min`, "85% confidence", "IMMEDIATE", C.bad],
    ["BODY-14", "DARK — no process sensors", `${D.body14.toFixed(0)} min`, "43% confidence", "MONITOR", C.warn],
  ];
  comp.forEach(([st_, cov, det, conf, act, col], i) => {
    const x = MX + i * 6.15;
    card(s, x, 2.52, 5.75, 1.95);
    s.addText(st_, { x: x + 0.24, y: 2.68, w: 2.6, h: 0.36, isTextBox: true, margin: 0,
      fontFace: HEAD, fontSize: 19, bold: true, color: C.deep });
    s.addText(cov, { x: x + 0.24, y: 3.06, w: 3.4, h: 0.3, isTextBox: true, margin: 0,
      fontFace: FONT, fontSize: 11.5, color: C.soft });
    s.addText(`Detected ${det}  ·  ${conf}`, { x: x + 0.24, y: 3.44, w: 4.0, h: 0.3, isTextBox: true, margin: 0,
      fontFace: FONT, fontSize: 12, color: C.mid });
    s.addShape(pres.ShapeType.roundRect, { x: x + 0.24, y: 3.86, w: 1.85, h: 0.42, rectRadius: 0.06,
      fill: { color: col }, line: { width: 0 } });
    s.addText(act, { x: x + 0.24, y: 3.90, w: 1.85, h: 0.36, isTextBox: true, margin: 0,
      fontFace: FONT, fontSize: 12, bold: true, color: "FFFFFF", align: "center" });
  });
  note(s, [
    { text: "A sensor-poor station is structurally barred from producing an IMMEDIATE “stop work” " +
            "recommendation, ", options: { bold: true, color: C.deep } },
    { text: "because its evidence cannot carry that cost. It gets a watch item and an instrumentation " +
            "business case instead. The gate is enforced in code, on measured data confidence — not left " +
            "to judgement.", options: {} },
  ], MX, 4.72, 11.9, 1.0);
  body(s, "That asymmetry is the difference between a tool a supervisor keeps using and one they learn to " +
          "ignore. Every recommendation carries an accept/dismiss decision that is logged — over a pilot, " +
          "that ledger is what establishes the real false-alarm rate on the plant's own line.",
       MX, 5.92, 11.9, 0.9, 12.5);
  s.addNotes("This is the trust slide. Knowing when NOT to act is the differentiator.");
}

/* ── 11. integration ─────────────────────────────────────────────────── */
{
  const s = lightSlide("Six tables the plant already has. Nothing written back.", "LEGACY INTEGRATION");
  const rows = [
    [th("Source"), th("Fields"), th("Already exists because")],
    [td("MES part-scan log", { bold: true }), td("unit, station, arrive/depart timestamps"), td("traceability and takt reporting are mandatory")],
    [td("PLC handshake / historian", { bold: true }), td("blocked and starved seconds"), td("the line controller computes these to sequence conveyors")],
    [td("Process telemetry where fitted", { bold: true }), td("torque, vibration, temperature"), td("already historised on modern cells")],
    [td("Quality system", { bold: true }), td("gate results and defect modes"), td("rework and warranty already depend on it")],
    [td("Operator checklist", { bold: true }), td("manual check results"), td("already recorded on paper or tablet")],
    [td("ERP / goods inward", { bold: true }), td("lot id, incoming quality index"), td("supplier quality management already tracks it")],
  ];
  table(s, rows, MX, 1.70, 11.9, [3.2, 3.9, 4.8], { rowH: 0.44 });
  note(s, [
    { text: "No PLC logic change. No new tag on the control network. No modification to any interlock.\n",
      options: { bold: true, color: C.deep } },
    { text: "Transport is an OPC-UA subscription or a historian tap onto a message bus. Where a legacy cell " +
            "has no OPC-UA server at all, the MES scan record alone places that station on the line view " +
            "with cycle-time and flow scoring — degraded, and labelled as degraded.", options: {} },
  ], MX, 4.98, 11.9, 1.15);
  body(s, "If a plant later wants closed-loop action, the natural first step is a supervisory setpoint such " +
          "as inspection sampling rate at a gate — not a control action.", MX, 6.28, 11.9, 0.6, 12);
  s.addNotes("Deployability is the whole reason this is read-only and advisory-only.");
}

/* ── 12. validation ──────────────────────────────────────────────────── */
{
  const s = lightSlide("Measured on a held-out window — including where it is weak", "VALIDATION");
  body(s, `Train days ${M.split.train_days[0]}–${M.split.train_days[1] - 1}, calibrate ` +
          `${M.split.val_days[0]}–${M.split.val_days[1] - 1}, test ${M.split.test_days[0]}–` +
          `${M.split.test_days[1] - 1}. All three demo incidents fall in the test window, so nothing about ` +
          `them was learned. Reproduced by a single command.`, MX, 1.62, 11.9, 0.8);
  const rows = [
    [th("Measure"), th("Result"), th("Read it as")],
    [td("Detection latency, instrumented", { bold: true }), td(`${D.body08.toFixed(0)} min (BODY-08)`), td("vs ~90 min to first downstream reject", { color: C.ok })],
    [td("Detection latency, sensor-poor", { bold: true }), td(`${D.body14.toFixed(0)} min (BODY-14)`), td("later and less confident — stated, not hidden", { color: C.warn })],
    [td("Alert load", { bold: true }), td(`${D.alerts_per_shift} per shift`), td(`across all ${LINE.stations} stations`, { color: C.ok })],
    [td("Attribution, high confidence", { bold: true }), td(pc(TB.by_confidence.high.top1) + " top-1"), td(`vs ${pc(TB.random_baseline_top1)} random`, { color: C.ok })],
    [td("Virtual sensing", { bold: true }), td(VS.auc.toFixed(2) + " AUC"), td("on stations never seen in training", { color: C.ok })],
    [td("Defect-risk model, all failures", { bold: true }), td(M.test.roc_auc.toFixed(2) + " ROC-AUC"), td("modest — and the weakest component", { color: C.warn })],
    [td("…on reachable failures only", { bold: true }), td(M.reachable.roc_auc.toFixed(2) + " ROC-AUC"), td(`lift ×${M.reachable.pr_lift} over base rate`, { color: C.ok })],
    [td("Null model (labels shuffled)", { italic: true }), td(M.null.roc_auc.toFixed(2) + " ROC-AUC", { italic: true }), td("the pipeline finds nothing when there is nothing", { italic: true })],
    [td("False-alarm rate", { bold: true }), td(pc(M.test.false_alarm_rate, 1)), td(`${M.alerts.toFixed(0)} flagged units/shift at capacity ${M.capacity}`, { color: C.ok })],
    [td("Bottleneck forecast", { bold: true }), td(`${pc(FC.hit_rate)} of ${FC.probes} calls`), td(`median ${FC.median_lead_min.toFixed(0)} min lead — small sample`, { color: C.warn })],
  ];
  table(s, rows, MX, 2.52, 11.9, [3.9, 3.0, 5.0], { rowH: 0.355, fontSize: 11 });
  note(s, [
    { text: "Where the ceiling is. ", options: { bold: true, color: C.deep } },
    { text: `Of ${M.ceiling.positives} failures in the test window, ${M.ceiling.downstream_origin} originate ` +
            `after the decision point — unreachable by any body-exit model. The bootstrap 95% interval on ` +
            `test ROC-AUC is [${M.ci.roc_auc_ci[0].toFixed(2)}, ${M.ci.roc_auc_ci[1].toFixed(2)}], which also ` +
            `means the three model families we fitted are statistically indistinguishable. We do not claim ` +
            `the selected one is better.`, options: {} },
  ], MX, 6.42, 11.9, 0.82);
  s.addNotes("Honesty is the point of this slide. Judges trust a deck that names its own weak spots.");
}

/* ── 13. ROI ─────────────────────────────────────────────────────────── */
{
  const s = lightSlide("Every figure traces to a measurement or a stated assumption", "THE BUSINESS CASE");
  stat(s, MX, 1.66, 3.85, mil(EC.annual), "Annual benefit, one line", "after both conservatism haircuts", C.ok);
  stat(s, MX + 4.03, 1.66, 3.85, usd(EC.y1_cost), "Year-1 cost", "build, integration, pilot, change management");
  stat(s, MX + 8.06, 1.66, 3.84, `${EC.payback.toFixed(1)} mo`, "Payback", "on the point estimate", C.deep);
  const rows = [
    [th("Line"), th("Volume"), th("Unit value"), th("Annual")],
    [td("Defects caught at body exit instead of at a gate"), td(Q.defects_caught_early_per_year.toLocaleString() + "/yr"), td("× " + usd(Q.saving_per_catch)), td(usd(Q.defects_caught_early_per_year * Q.saving_per_catch))],
    [td("Escapes intercepted (defects no gate would catch)"), td(Q.escapes_intercepted_per_year.toLocaleString() + "/yr"), td("× " + usd(Q.saving_per_escape)), td(usd(Q.escapes_intercepted_per_year * Q.saving_per_escape))],
    [td("Probability a re-inspection actually finds the fault"), td(""), td("× " + Q.inspection_effectiveness), td(usd(Q.gross_benefit))],
    [td("Cost of the extra inspections this creates"), td(Q.extra_inspections_per_year.toLocaleString() + "/yr"), td("× $26"), td("−" + usd(Q.inspection_cost), { color: C.bad })],
    [td("Realisation haircut on everything modelled"), td(""), td("× " + Q.realisation_factor), td(usd(Q.net_benefit), { bold: true })],
    [td("Throughput recovered from earlier constraint calls"), td(TH.units_recovered_per_year.toLocaleString() + " units/yr"), td("× " + usd(TH.contribution_margin_per_unit)), td(usd(TH.benefit), { bold: true })],
  ];
  table(s, rows, MX, 3.34, 11.9, [5.6, 2.2, 1.9, 2.2], { rowH: 0.4, fontSize: 11 });
  note(s, [
    { text: "The honest weak point. ", options: { bold: true, color: C.deep } },
    { text: `The largest single line rests on ${Q.escapes_intercepted_in_test} intercepted escapes in a ` +
            `${Q.test_window_days}-day window. Its 95% interval puts the quality benefit between ` +
            `${mil(Q.benefit_range.low)} and ${mil(Q.benefit_range.high)} against a ` +
            `${mil(Q.net_benefit)} point estimate. A pilot should measure it before the figure is committed ` +
            `anywhere. Throughput is valued at contribution margin, not at a stopped-line downtime rate.`,
      options: {} },
  ], MX, 6.16, 11.9, 1.05);
  s.addNotes("Two explicit haircuts: 0.70 inspection effectiveness and 0.50 realisation. Both visible in the arithmetic.");
}

/* ── 14. roadmap ─────────────────────────────────────────────────────── */
{
  const s = lightSlide("A pilot designed so that failure is visible early", "ROADMAP");
  const phases = [
    ["1", "Shadow", "Weeks 1–8", "Runs on live data, shows nobody anything. Every alert logged. Limits qualified on this plant's own data.", "PR-AUC lift ≥ 1.5 and ≤ 15 alerts/shift. If not met, stop."],
    ["2", "Advisory", "Weeks 9–20", "Body shop only. Supervisors accept or dismiss each alert. Attribution checked against what maintenance finds.", "≥ 50% of high-confidence attributions confirmed."],
    ["3", "Full line", "Weeks 21–40", "All zones, compared against the same line's prior-year quality and constraint loss.", "Business case restated with the plant's measured effect size."],
    ["4", "Scale", "Month 10+", "Second line, then second plant. Re-qualification per line; the product does not change.", "Per-line integration cost tracking to plan."],
  ];
  phases.forEach(([n, name, when, what, exit], i) => {
    const y = 1.66 + i * 1.30;
    card(s, MX, y, 11.9, 1.16);
    s.addShape(pres.ShapeType.ellipse, { x: MX + 0.24, y: y + 0.30, w: 0.55, h: 0.55,
      fill: { color: i === 0 ? C.purple : C.deep }, line: { width: 0 } });
    s.addText(n, { x: MX + 0.24, y: y + 0.35, w: 0.55, h: 0.46, isTextBox: true, margin: 0,
      fontFace: HEAD, fontSize: 18, bold: true, color: "FFFFFF", align: "center" });
    s.addText(name, { x: MX + 0.95, y: y + 0.17, w: 2.1, h: 0.32, isTextBox: true, margin: 0,
      fontFace: HEAD, fontSize: 16, bold: true, color: C.deep });
    s.addText(when, { x: MX + 0.95, y: y + 0.52, w: 2.1, h: 0.28, isTextBox: true, margin: 0,
      fontFace: FONT, fontSize: 11, color: C.soft });
    s.addText(what, { x: MX + 3.15, y: y + 0.19, w: 5.0, h: 0.82, isTextBox: true, margin: 0,
      fontFace: FONT, fontSize: 11, color: C.mid, lineSpacing: 14 });
    s.addText([{ text: "Exit: ", options: { bold: true, color: C.deep } }, { text: exit, options: {} }],
      { x: MX + 8.35, y: y + 0.19, w: 3.35, h: 0.82, isTextBox: true, margin: 0,
        fontFace: FONT, fontSize: 11, color: C.mid, lineSpacing: 14 });
  });
  s.addText("What would falsify this: alert volume that cannot come under ~15/shift without losing the faults · " +
            "high-confidence attribution no better than a supervisor's first guess · calibration that will not " +
            "hold four weeks · dark-station inference that does not transfer.",
    { x: MX, y: 6.88, w: 11.9, h: 0.45, isTextBox: true, margin: 0,
      fontFace: FONT, fontSize: 10.5, italic: true, color: C.soft, lineSpacing: 13 });
  s.addNotes("A pilot that cannot fail is not a test. The falsification criteria are stated in advance.");
}

/* ── 15. closing ─────────────────────────────────────────────────────── */
{
  const s = darkSlide();
  s.addShape(pres.ShapeType.ellipse, {
    x: -2.2, y: 3.4, w: 6.8, h: 6.8, fill: { color: C.purple, transparency: 86 }, line: { width: 0 },
  });
  s.addText("Don't wait for the defect.", {
    x: MX, y: 0.95, w: 11.9, h: 0.75, isTextBox: true, margin: 0,
    fontFace: HEAD, fontSize: 40, bold: true, color: "FFFFFF",
  });
  s.addText("Round 1 promised a bottleneck forecast rather than a jam alert, defect risk with a traceback " +
            "list rather than an alarm, and virtual sensors so coverage comes from inference rather than new " +
            "hardware. All three are now working code with measured results.",
    { x: MX, y: 1.85, w: 8.6, h: 1.0, isTextBox: true, margin: 0,
      fontFace: FONT, fontSize: 14, color: "C9C2D6", lineSpacing: 21 });
  const cols = [
    ["IMPLEMENTED", C.ok, "SPC and drift detection · virtual sensors · feature pipeline · model training, " +
      "calibration and selection · bottleneck forecast · traceback, containment and its accuracy " +
      "validation · recommendation engine · economics · the full dashboard"],
    ["SIMULATED", C.warn, "The plant itself. Telemetry, defect creation and gate detection come from a " +
      "generator with a latent causal model the twin never sees. Everything downstream would run " +
      "unchanged on a real MES feed."],
    ["PROPOSED", C.soft, "MES / PLC / OPC-UA connectors · multi-plant rollout · model registry and " +
      "retraining schedule · authentication and audit trail for the decision ledger"],
  ];
  cols.forEach(([label, col, txt], i) => {
    const x = MX + i * 4.06;
    s.addShape(pres.ShapeType.roundRect, { x, y: 3.16, w: 3.75, h: 2.5, rectRadius: 0.08,
      fill: { color: "FFFFFF", transparency: 92 }, line: { color: "5A3B7A", width: 0.75 } });
    s.addShape(pres.ShapeType.roundRect, { x: x + 0.22, y: 3.38, w: 1.65, h: 0.34, rectRadius: 0.06,
      fill: { color: col }, line: { width: 0 } });
    s.addText(label, { x: x + 0.22, y: 3.41, w: 1.65, h: 0.3, isTextBox: true, margin: 0,
      fontFace: FONT, fontSize: 10.5, bold: true, color: "FFFFFF", align: "center" });
    s.addText(txt, { x: x + 0.22, y: 3.86, w: 3.32, h: 1.62, isTextBox: true, margin: 0,
      fontFace: FONT, fontSize: 11, color: "D8CFE6", lineSpacing: 15 });
  });
  s.addText("Strong evidence → act.   Weak evidence → don't overreact.", {
    x: MX, y: 6.06, w: 11.9, h: 0.42, isTextBox: true, margin: 0,
    fontFace: HEAD, fontSize: 19, bold: true, color: C.lilac,
  });
  s.addText("Team PeakBusters   ·   github.com/avinas29/smartfactory-twin   ·   python run.py", {
    x: MX, y: 6.72, w: 11.9, h: 0.3, isTextBox: true, margin: 0,
    fontFace: FONT, fontSize: 11, color: "9B8FAD",
  });
  s.addNotes("Close on the asymmetry. It is the sentence we want them to remember.");
}

pres.writeFile({ fileName: path.join(DOCS, "SmartFactory-Twin-Business-Proposal.pptx") })
  .then((f) => console.log("wrote " + f));
