/* SmartFactory Twin — dashboard.
   No framework and no build step: the whole client is this file plus a
   stylesheet, so the demo has nothing to install and nothing to fetch from a
   CDN. Charts are hand-drawn SVG for the same reason. */

const $  = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => [...r.querySelectorAll(s)];
const fmt = (n, d = 0) => n == null || !isFinite(n) ? '—'
  : n.toLocaleString('en-US', { minimumFractionDigits: d, maximumFractionDigits: d });
const money = n => n == null ? '—' : '$' + Math.round(n).toLocaleString('en-US');
const pct = (n, d = 0) => n == null ? '—' : (100 * n).toFixed(d) + '%';
const esc = s => String(s ?? '').replace(/[&<>"]/g, c =>
  ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
const hhmm = ts => new Date(ts * 1000).toISOString().slice(11, 16);

const S = {
  meta: null, t: 0, playing: false, view: 'line',
  station: null, gate: 27, decisions: {}, lastState: null, timer: null,
};

/* ───────────────────────── boot ───────────────────────── */
async function boot() {
  S.meta = await (await fetch('/api/meta')).json();
  const c = S.meta.clock;
  S.t = S.meta.bookmarks[0]?.t ?? c.min;
  $('#scrub').min = c.min; $('#scrub').max = c.max; $('#scrub').value = S.t;

  $('#bookmarks').innerHTML = S.meta.bookmarks.map((b, i) =>
    `<button class="bm" data-t="${b.t}" data-i="${i}" title="${esc(b.blurb)}">${esc(b.label)}</button>`
  ).join('');
  $$('.bm').forEach(b => b.onclick = () => {
    setTime(+b.dataset.t); pause();
    $$('.bm').forEach(x => x.classList.remove('on')); b.classList.add('on');
    toast(S.meta.bookmarks[+b.dataset.i].blurb);
  });

  $$('.views button').forEach(b => b.onclick = () => switchView(b.dataset.view));
  $('#scrub').oninput = e => { pause(); setTime(+e.target.value); };
  $('#btn-play').onclick = () => S.playing ? pause() : play();
  $('#detail-close').onclick = () => { S.station = null; $('#detail-panel').hidden = true; };
  $('#lines').oninput = e => { $('#lines-n').textContent = e.target.value; loadBusiness(); };

  $('#legend').innerHTML = [
    ['var(--ok)', 'Nominal'], ['var(--warn)', 'Deviation'], ['var(--alarm)', 'In alarm'],
    ['var(--info)', 'Quality gate'],
  ].map(([c, l]) => `<span><i style="background:${c}"></i>${l}</span>`).join('')
    + `<span><svg width="11" height="11" style="vertical-align:-1px"><rect width="11" height="11" rx="2" fill="none" stroke="var(--dark-station)" stroke-width="1.4" stroke-dasharray="2.5 2"/></svg> Sensor-poor</span>`;

  // Deep-linkable state: ?t=<epoch>&view=<name>&station=<code>&gate=<idx>.
  // Lets a demo return to an exact moment instead of hunting for it live, and
  // makes the screenshots in the written submission reproducible.
  const q = new URLSearchParams(location.search);
  if (q.has('t')) S.t = Math.max(c.min, Math.min(c.max, +q.get('t')));
  if (q.has('gate')) S.gate = +q.get('gate');
  setTime(S.t);
  const activeMark = S.meta.bookmarks.findIndex(b => Math.abs(b.t - S.t) < 60);
  $$('.bm')[activeMark >= 0 ? activeMark : 0]?.classList.add('on');
  if (q.has('view')) switchView(q.get('view'));
  await refresh();
  if (q.has('station')) await openStation(q.get('station'), true);
  setInterval(() => { if (S.playing) step(); }, 1000);
}

function play() { S.playing = true; $('#btn-play').textContent = '❚❚'; $('#btn-play').classList.add('on'); }
function pause() { S.playing = false; $('#btn-play').textContent = '▶'; $('#btn-play').classList.remove('on'); }
function step() {
  const nt = S.t + (+$('#speed').value);
  if (nt >= S.meta.clock.max) { pause(); return; }
  setTime(nt);
}
function setTime(t) {
  S.t = t; $('#scrub').value = t;
  $('#clock-time').textContent = hhmm(t);
  $('#clock-date').textContent = new Date(t * 1000).toISOString().slice(0, 10) + ' · Shift '
    + (new Date(t * 1000).getUTCHours() < 14 ? 'A' : 'B');
  clearTimeout(S.timer);
  S.timer = setTimeout(refresh, 90);
}
function switchView(v) {
  S.view = v;
  $$('.views button').forEach(b => b.classList.toggle('active', b.dataset.view === v));
  $$('.view').forEach(s => s.classList.toggle('active', s.id === 'view-' + v));
  refresh();
}
function toast(msg) {
  const el = $('#toast'); el.textContent = msg; el.hidden = false;
  clearTimeout(toast._t); toast._t = setTimeout(() => el.hidden = true, 4200);
}

async function refresh() {
  setTime.lastRendered = S.t;
  if (S.view === 'line') await loadLine();
  else if (S.view === 'trace') await loadTrace();
  else if (S.view === 'plant') await loadPlant();
  else if (S.view === 'business') await loadBusiness();
  else if (S.view === 'validation') await loadValidation();
}

/* ───────────────────────── line view ───────────────────────── */
async function loadLine() {
  const d = await (await fetch(`/api/state?t=${S.t}`)).json();
  S.lastState = d;
  const s = d.summary;

  $('#kpis').innerHTML = [
    { k: 'Stations in alarm', v: s.in_alarm, s: `${s.in_warning} showing deviation`,
      c: s.in_alarm ? 'alarm' : 'ok' },
    { k: 'Line constraint', v: s.constraint ?? '—',
      s: `${fmt(s.constraint_capacity, 0)} of ${fmt(s.takt_capacity, 0)} units/h`,
      c: s.constraint_capacity < s.takt_capacity ? 'warn' : 'ok', small: true },
    { k: 'Mean defect risk', v: pct(s.mean_risk, 1), s: 'units in line, scored at body exit' },
    { k: 'Built today', v: fmt(s.units_built_today), s: 'through final inspection' },
  ].map(x => `<div class="kpi ${x.c || ''}">
      <div class="k">${x.k}</div>
      <div class="v" ${x.small ? 'style="font-size:19px"' : ''}>${esc(String(x.v))}</div>
      <div class="s">${esc(x.s)}</div></div>`).join('');

  $('#line-svg').innerHTML = lineSVG(d.stations);
  $$('.st').forEach(g => g.onclick = () => openStation(g.dataset.code));

  const f = d.forecast;
  $('#constraint').innerHTML = !f.current ? '<div class="empty">No data yet</div>' : `
    <div class="panel-body">
      <div style="font:600 21px var(--mono)">${esc(f.current.station_code)}</div>
      <div class="muted small" style="margin-bottom:10px">${esc(f.current.name)}</div>
      <div class="detail-grid" style="grid-template-columns:1fr 1fr;margin-bottom:12px">
        <div class="dstat"><div class="k">Capacity</div><div class="v">${fmt(f.current.capacity_uph, 1)}<span style="font-size:11px;color:var(--text-3)"> u/h</span></div></div>
        <div class="dstat"><div class="k">Utilisation</div><div class="v">${pct(f.current.utilisation)}</div></div>
      </div>
      ${f.change ? `<div class="verdict medium" style="margin:0">
          <b>${esc(f.change.station_code)}</b> takes over as the constraint in
          <b>~${f.change.in_minutes} min</b> at ${fmt(f.change.capacity_uph, 0)} u/h.
          <div class="muted small" style="margin-top:6px">${fmt(f.units_at_risk, 0)} units at risk over the ${f.horizon_min}-minute horizon.</div>
        </div>`
      : `<div class="muted small">Constraint stable across the ${f.horizon_min}-minute horizon.</div>`}
    </div>`;

  const recs = d.recommendations;
  $('#rec-count').textContent = recs.length;
  $('#recs').innerHTML = recs.length ? `<div class="list">${recs.map(recCard).join('')}</div>`
    : '<div class="empty">No open recommendations. Every station inside its control limits.</div>';
  $$('[data-rec]').forEach(b => b.onclick = () => decide(b.dataset.rec, b.dataset.verdict));

  $('#at-risk').innerHTML = d.at_risk.length ? `<div class="list">${d.at_risk.map(u => `
      <div class="rec" style="padding:10px 16px">
        <div class="rec-top">
          <span class="mono" style="font-size:12.5px">${esc(u.unit_id)}</span>
          <span class="pill ${u.risk > .3 ? 'on' : ''}">${pct(u.risk, 1)}</span>
          <span class="muted small">${esc(u.model)} · at ${esc(u.station)}</span>
        </div>
        <div class="suspect-why">${u.evidence.map(e =>
          `${esc(e.station_code)} <span class="mono">${e.station_z.toFixed(1)}σ</span>${e.inferred ? ' <span class="chip DARK">inferred</span>' : ''}`
        ).join(' · ')}</div>
      </div>`).join('')}</div>`
    : '<div class="empty">No units above baseline risk.</div>';

  if (S.station) openStation(S.station, true);
}

function recCard(r) {
  const decided = S.decisions[r.id];
  return `<div class="rec">
    <div class="rec-top">
      <span class="tag ${r.cls}">${r.cls}</span>
      <span class="mono small">${esc(r.station)}</span>
    </div>
    <h3>${esc(r.title)}</h3>
    <p>${esc(r.evidence)}</p>
    <p class="action">${esc(r.action)}</p>
    <p class="muted small">${esc(r.why_now)}</p>
    <div class="rec-meta">
      <span>Confidence <b class="mono">${pct(r.confidence)}</b></span>
      <span>Severity <b class="mono">${r.severity.toFixed(1)}σ</b></span>
      ${r.units_affected ? `<span>Units <b class="mono">${fmt(r.units_affected)}</b></span>` : ''}
      <span>${esc(r.owner)}</span>
    </div>
    ${decided ? `<div class="decided">${decided === 'accepted' ? '✓ Accepted' : '✕ Dismissed'} — logged to the trust ledger</div>`
      : `<div class="rec-actions">
          <button class="btn accept" data-rec="${r.id}" data-verdict="accepted">Accept</button>
          <button class="btn dismiss" data-rec="${r.id}" data-verdict="dismissed">Dismiss</button>
        </div>`}
  </div>`;
}

async function decide(id, verdict) {
  const r = (S.lastState?.recommendations || []).find(x => x.id === id);
  if (!r) return;
  S.decisions[id] = verdict;
  await fetch('/api/decision', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ rec_id: id, station: r.station, action: r.title, verdict, t: S.t }),
  });
  toast(`${verdict === 'accepted' ? 'Accepted' : 'Dismissed'} — ${r.station}. Logged for validation.`);
  loadLine();
}

/* ───────────────── line diagram (SVG) ───────────────── */
function lineSVG(stations) {
  const zones = S.meta.zones;
  const W = 40, H = 40, GAP = 5, PADL = 16, ROWY = 76;
  const rows = [];
  Object.entries(zones).forEach(([z, meta]) => {
    rows.push({ zone: z, label: meta.label, items: stations.filter(s => s.zone === z) });
  });
  const maxN = Math.max(...rows.map(r => r.items.length));
  const width = PADL * 2 + maxN * (W + GAP) + 190;
  const height = rows.length * ROWY + 52;

  const colour = s => s.status === 'alarm' ? 'var(--alarm)'
    : s.status === 'warn' ? 'var(--warn)' : 'var(--ok)';

  let svg = `<svg viewBox="0 0 ${width} ${height}" role="img" aria-label="Assembly line state">
    <defs>
      <linearGradient id="conv" x1="0" x2="1">
        <stop offset="0" stop-color="#2a2f3c"/><stop offset="1" stop-color="#1b1f28"/>
      </linearGradient>
      <filter id="glow" x="-60%" y="-60%" width="220%" height="220%">
        <feGaussianBlur stdDeviation="3.2" result="b"/>
        <feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge>
      </filter>
    </defs>`;

  rows.forEach((row, ri) => {
    const y = 34 + ri * ROWY;
    svg += `<text class="zone-label" x="${PADL}" y="${y - 11}">${esc(row.label)}</text>`;
    svg += `<rect x="${PADL}" y="${y + H / 2 - 2}" width="${row.items.length * (W + GAP) - GAP}" height="4" fill="url(#conv)" rx="2"/>`;

    row.items.forEach((s, i) => {
      const x = PADL + i * (W + GAP);
      const c = colour(s);
      const dark = s.tier === 'DARK';
      const partial = s.tier === 'PARTIAL';
      svg += `<g class="st" data-code="${s.code}">`;
      // risk halo for stations in alarm
      if (s.status === 'alarm')
        svg += `<rect x="${x - 2}" y="${y - 2}" width="${W + 4}" height="${H + 4}" rx="6"
                 fill="none" stroke="${c}" stroke-width="1.4" opacity=".55" filter="url(#glow)"/>`;
      svg += `<rect class="st-box" x="${x}" y="${y}" width="${W}" height="${H}" rx="5"
               fill="${s.status === 'ok' ? 'var(--bg-3)' : c}" fill-opacity="${s.status === 'ok' ? 1 : .22}"
               stroke="${dark ? 'var(--dark-station)' : c}" stroke-width="${dark ? 1.4 : 1.1}"
               ${dark ? 'stroke-dasharray="2.5 2"' : partial ? 'stroke-dasharray="6 2"' : ''}/>`;
      // condition bar: how far above baseline this station is running
      const h = Math.max(2, Math.min(1, (s.peak_z ?? s.station_z) / 8) * (H - 10));
      svg += `<rect x="${x + 3.5}" y="${y + H - 5 - h}" width="4" height="${h}" rx="2" fill="${c}"/>`;
      // sensor coverage: one pip per reporting channel
      for (let k = 0; k < s.n_channels; k++)
        svg += `<circle cx="${x + W - 5.5}" cy="${y + 6 + k * 4.6}" r="1.5"
                 fill="${dark ? 'var(--dark-station)' : 'var(--text-3)'}"/>`;
      if (s.gate)
        svg += `<circle cx="${x + W / 2}" cy="${y - 6}" r="3.4" fill="var(--info)"/>`;
      if (s.inferred)
        svg += `<text x="${x + 4.5}" y="${y + 11}" style="font:700 8px var(--mono);fill:#c77dff">i</text>`;
      svg += `<text class="st-code" x="${x + W / 2}" y="${y + H / 2 + 3}" text-anchor="middle">${esc(s.code.split('-')[1])}</text>`;
      svg += `<text class="st-num" x="${x + W / 2}" y="${y + H + 11}" text-anchor="middle">${s.cycle_s.toFixed(0)}s</text>`;
      svg += `<title>${esc(s.code)} — ${esc(s.name)}
${s.tier} coverage · ${s.n_channels} channels · confidence ${pct(s.data_confidence)}
cycle ${s.cycle_s}s (nominal ${s.nominal_s}s) · condition ${s.station_z.toFixed(1)}σ mean, ${(s.peak_z ?? s.station_z).toFixed(1)}σ peak${s.inferred ? ' (partly inferred)' : ''}</title>`;
      svg += `</g>`;
    });

    // buffer marker into the next zone
    const last = row.items[row.items.length - 1];
    if (last && last.code === 'PAINT-24') {
      const x = PADL + row.items.length * (W + GAP) + 4;
      svg += `<text class="st-num" x="${x}" y="${y + H / 2 + 3}">▸ painted-body store · 60 bodies · ~60 min</text>`;
    }
  });
  return svg + '</svg>';
}

/* ───────────────── station detail ───────────────── */
async function openStation(code, quiet) {
  S.station = code;
  const d = await (await fetch(`/api/station/${code}?t=${S.t}`)).json();
  const st = d.station, cv = d.coverage;
  $('#detail-title').textContent = `${st.code} — ${st.name}`;
  $('#detail-panel').hidden = false;

  const missing = d.missing_channels.length
    ? `<div class="verdict low" style="margin:0 0 14px">
        <b>Sensor-poor station.</b> No ${d.missing_channels.map(m => ({
          vibration: 'vibration sensor', torque_scatter: 'torque telemetry',
          temp_adj: 'temperature probe' }[m] || m)).join(', ')}.
        The twin scores it from ${d.channels.map(c => c.label.toLowerCase()).join(', ')},
        plus a virtual sensor trained on instrumented stations
        (held-out-station AUC ${S.meta.virtual_sensor.auc.toFixed(3)}).
        Current inferred fault probability <b class="mono">${pct(cv.virtual_p, 0)}</b>,
        blended at weight <b class="mono">${cv.inference_weight.toFixed(2)}</b>.
        Data confidence is discounted to <b class="mono">${pct(cv.data_confidence)}</b> accordingly.
      </div>` : '';

  $('#detail-body').innerHTML = `
    ${missing}
    <div class="detail-grid">
      <div class="dstat"><div class="k">Condition</div><div class="v">${d.series.station_z.at(-1)?.toFixed(1) ?? '—'}σ</div></div>
      <div class="dstat"><div class="k">Cycle time</div><div class="v">${d.series.cycle_time.at(-1)?.toFixed(1) ?? '—'}s<span style="font-size:11px;color:var(--text-3)"> / ${st.nominal_s}s</span></div></div>
      <div class="dstat"><div class="k">Coverage</div><div class="v" style="font-size:15px"><span class="chip ${st.tier}">${st.tier}</span> ${cv.n_channels} ch</div></div>
      <div class="dstat"><div class="k">Data confidence</div><div class="v">${pct(cv.data_confidence)}</div></div>
    </div>
    ${st.note ? `<p class="muted small" style="margin:-4px 0 14px">${esc(st.note)}</p>` : ''}
    <div class="chart-title"><span>Composite condition score (σ above qualified baseline)</span>
      <span class="muted">alarm at ${d.drift_limit}σ EWMA</span></div>
    ${sparkline(d.series.ts, d.series.station_z, { limit: d.actionable_z, drift: d.series.drift, h: 92 })}
    ${['z_vibration', 'z_torque_scatter', 'z_cycle_norm', 'z_manual_rate', 'z_temp_adj']
      .filter(k => d.series[k]).map(k => `
      <div class="chart-title"><span>${esc((d.channels.find(c => 'z_' + c.key === k) || {}).label || k)}</span>
        <span class="muted mono">${(d.series[k].filter(Number.isFinite).at(-1) ?? 0).toFixed(1)}σ</span></div>
      ${sparkline(d.series.ts, d.series[k], { h: 46 })}`).join('')}
    ${st.creates.length ? `<p class="muted small" style="margin-top:14px">
      FMEA: this station can introduce <b>${st.creates.join(', ')}</b> defects, caught downstream at
      ${gatesFor(st.creates).join(', ') || 'no gate'}.</p>` : ''}`;
  if (!quiet) $('#detail-panel').scrollIntoView({ behavior: 'smooth', block: 'nearest' });
}

function gatesFor(modes) {
  return S.meta.stations.filter(s => s.gate).filter(s => {
    const catches = { 'G-BODY': ['GEOM'], 'G-PAINT': ['PAINT'], 'G-TORQUE': ['TORQUE'],
      'G-ELEC': ['ELEC'], 'G-DYN': ['TORQUE', 'SEAL'],
      'G-EOL': ['GEOM', 'FIT', 'SEAL', 'PAINT', 'TORQUE'] }[s.gate] || [];
    return modes.some(m => catches.includes(m));
  }).map(s => s.code);
}

/* ───────────────── charts ───────────────── */
function sparkline(ts, vals, o = {}) {
  const h = o.h || 60, w = 800, pad = 3;
  const v = vals.map(x => (x == null || !isFinite(x)) ? null : x);
  const nums = v.filter(x => x != null);
  if (!nums.length) return '<div class="empty small">no data</div>';
  const lo = Math.min(0, ...nums), hi = Math.max(...nums, o.limit ?? 0, 1);
  const X = i => pad + i * (w - 2 * pad) / Math.max(v.length - 1, 1);
  const Y = x => h - pad - (x - lo) / (hi - lo || 1) * (h - 2 * pad);

  let path = '', open = false;
  v.forEach((x, i) => {
    if (x == null) { open = false; return; }
    path += (open ? 'L' : 'M') + X(i).toFixed(1) + ' ' + Y(x).toFixed(1) + ' ';
    open = true;
  });
  let bands = '';
  if (o.drift) {
    let start = null;
    o.drift.forEach((dd, i) => {
      if (dd && start === null) start = i;
      if ((!dd || i === o.drift.length - 1) && start !== null) {
        bands += `<rect x="${X(start)}" y="0" width="${Math.max(1, X(i) - X(start))}" height="${h}"
                   fill="var(--alarm)" opacity=".10"/>`;
        start = null;
      }
    });
  }
  const limit = o.limit != null
    ? `<line x1="${pad}" x2="${w - pad}" y1="${Y(o.limit)}" y2="${Y(o.limit)}"
        stroke="var(--warn)" stroke-width="1" stroke-dasharray="4 3" opacity=".65"/>` : '';
  return `<div class="chart"><svg viewBox="0 0 ${w} ${h}" preserveAspectRatio="none">
    ${bands}${limit}
    <path d="${path}" fill="none" stroke="var(--purple)" stroke-width="1.6"
      vector-effect="non-scaling-stroke" stroke-linejoin="round"/>
  </svg></div>`;
}

function barRows(items, valKey, labelKey, o = {}) {
  const max = Math.max(...items.map(x => x[valKey]), 1);
  return items.map(x => `<div style="margin-bottom:9px">
    <div class="suspect-top"><span>${esc(x[labelKey])} ${x.tier ? `<span class="chip ${x.tier}">${x.tier}</span>` : ''}</span>
      <span class="mono">${o.fmt ? o.fmt(x[valKey]) : fmt(x[valKey])}</span></div>
    <div class="bar"><div style="width:${100 * x[valKey] / max}%"></div></div></div>`).join('');
}

/* ───────────────── traceback ───────────────── */
async function loadTrace() {
  const sel = $('#gate-select');
  const d = await (await fetch(`/api/trace?gate=${S.gate}&t=${S.t}`)).json();
  if (!sel.options.length) {
    sel.innerHTML = d.gates.map(g =>
      `<option value="${g.idx}" ${g.idx === S.gate ? 'selected' : ''}>${g.code} — ${g.gate}</option>`).join('');
    sel.onchange = () => { S.gate = +sel.value; loadTrace(); };
  }
  const t = d.trace, c = d.containment;
  const conf = t.confidence || 'low';

  $('#trace-body').innerHTML = `<div class="trace-grid">
    <div>
      <div class="verdict ${conf}">
        <b>${t.n_failed} rejects</b> at ${esc(t.gate_station)} in the last ${t.window_h}h
        (${t.n_passed} passed). Attribution confidence: <b>${conf.toUpperCase()}</b> —
        ${esc(t.verdict || 'not enough rejects yet to form a contrast')}.
      </div>
      ${t.suspects.length ? t.suspects.map((s, i) => `
        <div class="suspect ${i === 0 && conf !== 'low' ? 'lead' : ''}">
          <div class="suspect-top">
            <span><b class="mono">${esc(s.station_code)}</b> <span class="chip ${s.tier}">${s.tier}</span>
              <span class="muted">${esc(s.name)}</span></span>
            <span class="mono">${pct(s.share)}</span>
          </div>
          <div class="suspect-bar"><div style="width:${Math.max(6, 100 * s.share)}%">${pct(s.share)}</div></div>
          <div class="suspect-why">
            Rejected units met it at <b class="mono">${s.mean_z_failed.toFixed(1)}σ</b> versus
            <b class="mono">${s.mean_z_passed.toFixed(1)}σ</b> for units that passed, against
            <b class="mono">${s.mean_z_yesterday.toFixed(1)}σ</b> a day earlier.
            ${pct(s.share_alarm_failed)} of rejects passed it while in alarm vs ${pct(s.share_alarm_passed)}
            (lift ×${s.alarm_lift.toFixed(1)}). Data confidence ${pct(s.data_confidence)}.
          </div>
        </div>`).join('')
      : '<div class="empty">Not enough rejects in this window to attribute.</div>'}
    </div>
    <div>
      <h3 style="font-size:13px;text-transform:uppercase;letter-spacing:.06em;color:var(--text-2);margin-bottom:10px">Containment</h3>
      ${c && c.n_units ? `
        <p class="muted small" style="margin-bottom:12px">
          <b class="mono">${c.n_units}</b> units passed <b>${esc(c.station_code)}</b> during
          <b class="mono">${fmt(c.drift_minutes)} min</b> of drift.
          <b class="mono">${c.still_recoverable}</b> are still inside the plant.</p>
        ${barRows(Object.entries(c.by_location).map(([k, v]) => ({ loc: k, n: v })), 'n', 'loc')}
        <p class="muted small" style="margin-top:12px">Scope containment to these units, not to the shift's build.</p>`
      : '<div class="empty">No active drift window on the leading suspect.</div>'}

      <h3 style="font-size:13px;text-transform:uppercase;letter-spacing:.06em;color:var(--text-2);margin:18px 0 8px">Recent rejects</h3>
      <div class="list"><table><thead><tr><th>Unit</th><th>Time</th><th>Mode</th><th class="num">Lag</th></tr></thead>
        <tbody>${d.rejects.slice().reverse().map(r => `<tr>
          <td class="mono">${esc(r.unit_id)}</td><td class="mono">${hhmm(r.ts)}</td>
          <td>${r.modes.join(', ')}</td>
          <td class="num">${r.lag_min ? fmt(r.lag_min) + ' min' : '—'}</td></tr>`).join('')
        || '<tr><td colspan="4" class="empty">none in window</td></tr>'}</tbody></table></div>
    </div>
  </div>
  <div class="note"><b>How this works.</b> The twin keeps a genealogy for every vehicle: which stations it
    passed and what condition each was in at that moment. Attribution contrasts the rejected units'
    experience of each upstream station against the units that passed the same gate, and against the same
    station a day earlier, weighted by the plant's FMEA station-to-failure-mode map. It is evidence for an
    engineer to check, not a verdict — and where the evidence does not separate, the twin says so.</div>`;
}

/* ───────────────── plant ───────────────── */
async function loadPlant() {
  const d = await (await fetch(`/api/plant?t=${S.t}`)).json();
  const cov = d.coverage;
  $('#plant-body').innerHTML = `
    <div class="panel"><div class="panel-head"><h2>Most alerted stations</h2></div>
      <div class="panel-body">${barRows(d.top_stations, 'alerts', 'station', { fmt: v => v + ' alerts' })}</div></div>

    <div class="panel"><div class="panel-head"><h2>Detection latency on seeded faults</h2></div>
      <div class="panel-body"><table><thead><tr><th>Station</th><th>Fault</th><th>Coverage</th><th class="num">Detected after</th></tr></thead>
        <tbody>${d.detection_latency.map(x => `<tr>
          <td class="mono">${esc(x.station)}</td><td>${esc(x.title)}</td>
          <td><span class="chip ${x.tier}">${x.tier}</span></td>
          <td class="num">${x.detected_after_min ? fmt(x.detected_after_min) + ' min' : 'missed'}</td></tr>`).join('')}
        </tbody></table>
        <p class="muted small" style="margin-top:12px">Sensor-poor stations are detected later and with lower
          confidence — the twin does not claim parity with instrumented ones.</p></div></div>

    <div class="panel"><div class="panel-head"><h2>Sensor coverage</h2></div>
      <div class="panel-body"><table><thead><tr><th>Tier</th><th class="num">Stations</th><th class="num">Mean confidence</th><th class="num">Actionable alerts</th></tr></thead>
        <tbody>${Object.entries(cov).map(([k, v]) => `<tr>
          <td><span class="chip ${k}">${k}</span></td><td class="num">${v.stations}</td>
          <td class="num">${pct(v.mean_confidence)}</td><td class="num">${v.alerts}</td></tr>`).join('')}
        </tbody></table>
        <p class="muted small" style="margin-top:12px">Alert load: <b class="mono">${d.alerts_per_shift}</b> actionable
          alerts per shift across all 42 stations.</p></div></div>

    <div class="panel"><div class="panel-head"><h2>End-of-line reject rate by day</h2></div>
      <div class="panel-body">
        ${sparkline(d.gate_trend.map(x => x.day), d.gate_trend.map(x => x.reject_rate), { h: 80 })}
        <div class="row" style="justify-content:space-between;margin-top:6px" class="muted small">
          <span class="muted small">day ${d.gate_trend[0]?.day ?? ''}</span>
          <span class="muted small">day ${d.gate_trend.at(-1)?.day ?? ''}</span></div>
        <div class="chart-title"><span>Mean predicted defect risk</span></div>
        ${sparkline(d.risk_trend.map(x => x.day), d.risk_trend.map(x => x.mean_risk), { h: 60 })}
      </div></div>

    <div class="panel"><div class="panel-head"><h2>Flow constraint exposure</h2></div>
      <div class="panel-body">${d.bottleneck_frequency.length
        ? barRows(d.bottleneck_frequency, 'minutes', 'station', { fmt: v => fmt(v) + ' units' })
        : '<div class="empty">No sustained flow constraints in this window.</div>'}</div></div>`;
}

/* ───────────────── business ───────────────── */
async function loadBusiness() {
  const n = +$('#lines').value;
  const d = await (await fetch(`/api/business?lines=${n}`)).json();
  const r = d.roi, q = r.quality, t = r.throughput;

  $('#business-body').innerHTML = `
    <div class="panel-body">
      <div class="kpis" style="margin-bottom:18px">
        <div class="kpi ok"><div class="k">Annual benefit</div><div class="v">${money(r.annual_benefit_total)}</div><div class="s">${n} line${n > 1 ? 's' : ''}, after realisation haircut</div></div>
        <div class="kpi"><div class="k">Year-1 cost</div><div class="v">${money(r.year_1_cost)}</div><div class="s">build, integration, run rate</div></div>
        <div class="kpi ok"><div class="k">Year-1 net</div><div class="v">${money(r.year_1_net)}</div><div class="s">payback ${r.payback_months} months</div></div>
      </div>

      <h3 style="font-size:13px;margin-bottom:8px">Quality benefit <span class="basis MODELLED">MODELLED</span></h3>
      <table><tbody>
        <tr><td>Defects caught at body exit instead of at a gate</td><td class="num">${fmt(q.defects_caught_early_per_year)}/yr</td><td class="num">× ${money(q.saving_per_catch)}</td><td class="num">${money(q.defects_caught_early_per_year * q.saving_per_catch)}</td></tr>
        <tr><td>Escapes intercepted (defects no gate would catch)</td><td class="num">${fmt(q.escapes_intercepted_per_year)}/yr</td><td class="num">× ${money(q.saving_per_escape)}</td><td class="num">${money(q.escapes_intercepted_per_year * q.saving_per_escape)}</td></tr>
        <tr><td>Probability a targeted re-inspection finds the fault</td><td></td><td class="num">× ${q.inspection_effectiveness}</td><td class="num">${money(q.gross_benefit)}</td></tr>
        <tr><td>Cost of the extra inspections this creates</td><td class="num">${fmt(q.extra_inspections_per_year)}/yr</td><td class="num">× ${money(r.assumptions.inspection_cost_per_unit)}</td><td class="num" style="color:var(--alarm)">−${money(q.inspection_cost)}</td></tr>
        <tr><td>Modelled net, before haircut</td><td></td><td></td><td class="num">${money(q.net_modelled)}</td></tr>
        <tr><td><b>After realisation haircut</b></td><td></td><td class="num">× ${q.realisation_factor}</td><td class="num"><b>${money(q.net_benefit)}</b></td></tr>
      </tbody></table>
      <p class="muted small" style="margin:10px 0 20px">
${esc(q.sample_note)}
        ${q.benefit_range ? ` Interception rate ${pct(q.escapes_intercepted_in_test / Math.max(q.escapes_in_test, 1), 1)}
        (95% CI ${pct(q.escape_rate_ci[0], 1)}–${pct(q.escape_rate_ci[1], 1)}), which puts the quality benefit
        between <b class="mono">${money(q.benefit_range.low)}</b> and
        <b class="mono">${money(q.benefit_range.high)}</b> against a
        ${money(q.net_benefit)} point estimate.` : ''}</p>
      <p class="muted small" style="margin:6px 0 20px">
        Measured on the held-out test window: <b class="mono">${q.true_positives_in_test}</b> true positives and
        <b class="mono">${q.escapes_intercepted_in_test}</b> of <b class="mono">${q.escapes_in_test}</b> escapes intercepted
        across <b class="mono">${fmt(q.test_units)}</b> units in ${q.test_window_days} days, at
        ${pct(q.precision_at_capacity)} precision. Everything else on this row is a stated cost assumption.</p>

      <h3 style="font-size:13px;margin-bottom:8px">Throughput benefit <span class="basis MODELLED">MODELLED</span></h3>
      <table><tbody>
        <tr><td>Constraint handovers the forecast called correctly</td><td class="num">${t.constraint_events_verified} in ${t.probe_span_days}d</td><td class="num">→ ${fmt(t.constraint_events_per_year)}/yr</td><td></td></tr>
        <tr><td>Units at risk per event × conversion × realisation</td><td class="num">${t.units_at_risk_per_event}</td><td class="num">× ${t.assumed_conversion_rate} × ${t.realisation_factor}</td><td class="num">${fmt(t.units_recovered_per_year)} units/yr</td></tr>
        <tr><td>Valued at contribution margin</td><td></td><td class="num">× ${money(t.contribution_margin_per_unit)}</td><td class="num"><b>${money(t.benefit)}</b></td></tr>
      </tbody></table>
      <p class="muted small" style="margin:10px 0 20px">${esc(t.note)}
        Median warning ahead of the handover: <b class="mono">${t.measured_lead_minutes} min</b>.</p>

      <h3 style="font-size:13px;margin-bottom:8px">Where the instrumentation budget should go</h3>
      <table><thead><tr><th>Station</th><th>Coverage</th><th class="num">Alerts/yr</th><th class="num">Units exposed</th><th class="num">Retrofit</th><th class="num">Payback</th></tr></thead>
        <tbody>${d.instrumentation.map(i => `<tr>
          <td class="mono">${esc(i.station)}</td><td><span class="chip ${i.tier}">${i.tier}</span></td>
          <td class="num">${fmt(i.alerts_per_year)}</td><td class="num">${fmt(i.mean_units_exposed)}</td>
          <td class="num">${money(i.retrofit_cost)}</td>
          <td class="num">${i.payback_years ? i.payback_years + ' yr' : '—'}</td></tr>`).join('')}</tbody></table>
    </div>
    <div class="note"><b>${esc(r.disclosure)}</b></div>`;
}

/* ───────────────── validation ───────────────── */
async function loadValidation() {
  const v = await (await fetch('/api/validation')).json();
  const m = v.model, T = m.test, R = m.test_reachable, C_ = m.test.confusion;

  $('#validation-body').innerHTML = `
    <div class="grid-2">
      <div class="panel"><div class="panel-head"><h2>Defect-risk model — held-out test window</h2>
        <span class="pill on">${esc(m.selected_model)}</span></div>
        <div class="panel-body">
          <p class="muted small" style="margin-top:0">Temporal split — train days ${m.split.train_days[0]}–${m.split.train_days[1] - 1}
            (${fmt(m.split.train)} units), calibrate ${m.split.val_days[0]}–${m.split.val_days[1] - 1} (${fmt(m.split.val)}),
            test ${m.split.test_days[0]}–${m.split.test_days[1] - 1} (${fmt(m.split.test)}). The seeded incidents fall in the
            test window, so nothing about them was learned.</p>
          <table><thead><tr><th>Population</th><th class="num">ROC-AUC</th><th class="num">PR-AUC</th><th class="num">Base</th><th class="num">Lift</th><th class="num">Precision</th><th class="num">Recall</th><th class="num">F1</th></tr></thead>
            <tbody>
              <tr><td>All downstream failures</td><td class="num">${T.roc_auc}</td><td class="num">${T.pr_auc}</td><td class="num">${T.base_rate}</td><td class="num">×${T.pr_lift}</td><td class="num">${T.precision}</td><td class="num">${T.recall}</td><td class="num">${T.f1}</td></tr>
              <tr><td><b>Reachable failures only</b></td><td class="num"><b>${R.roc_auc}</b></td><td class="num">${R.pr_auc}</td><td class="num">${R.base_rate}</td><td class="num">×${R.pr_lift}</td><td class="num">${R.precision}</td><td class="num">${R.recall}</td><td class="num">${R.f1}</td></tr>
              ${m.null_model ? `<tr style="color:var(--text-3)"><td>Null model — labels shuffled in train</td><td class="num">${m.null_model.roc_auc}</td><td class="num">${m.null_model.pr_auc}</td><td class="num">${m.null_model.base_rate}</td><td class="num">×${(m.null_model.pr_auc / m.null_model.base_rate).toFixed(2)}</td><td class="num">—</td><td class="num">—</td><td class="num">—</td></tr>` : ''}
            </tbody></table>
          ${m.test_ci ? `<p class="muted small">Bootstrap 95% interval on the test window:
            ROC-AUC <b class="mono">[${m.test_ci.roc_auc_ci[0]}, ${m.test_ci.roc_auc_ci[1]}]</b>,
            PR-AUC <b class="mono">[${m.test_ci.pr_auc_ci[0]}, ${m.test_ci.pr_auc_ci[1]}]</b>.
            The PR interval clears the ${m.test.base_rate} base rate, so the lift is not noise —
            but the three model families all sit inside the ROC interval, so the gap between them is.</p>` : ''}
          ${m.null_model ? `<p class="muted small">The null row is the same family, features and split with
            training labels shuffled. It lands at ${m.null_model.roc_auc}, i.e. no better than chance — the
            pipeline finds nothing when there is nothing to find.</p>` : ''}
          <p class="muted small">Of ${m.ceiling.positives} failures in the test window, ${m.ceiling.body_attributable}
            originate upstream of the decision point and ${m.ceiling.downstream_origin} originate after it.
            The second group cannot be predicted at body exit by any model — that is a ceiling, not a modelling gap,
            so both numbers are reported.</p>

          <div class="detail-grid" style="margin-top:14px">
            <div class="dstat"><div class="k">False-alarm rate</div><div class="v">${pct(T.false_alarm_rate, 1)}</div></div>
            <div class="dstat"><div class="k">Brier score</div><div class="v">${T.brier}</div></div>
            <div class="dstat"><div class="k">Alerts / shift</div><div class="v">${m.alerts_per_shift}</div></div>
            <div class="dstat"><div class="k">Train→test AUC</div><div class="v" style="font-size:15px">${m.train_roc_auc} → ${T.roc_auc}</div></div>
          </div>
          <div class="chart-title"><span>Confusion matrix at ${m.inspection_capacity_per_shift} inspections/shift</span></div>
          <table><thead><tr><th></th><th class="num">Predicted pass</th><th class="num">Predicted fail</th></tr></thead>
            <tbody>
              <tr><td>Actually passed</td><td class="num">${fmt(C_.tn)}</td><td class="num" style="color:var(--warn)">${fmt(C_.fp)}</td></tr>
              <tr><td>Actually failed</td><td class="num" style="color:var(--alarm)">${fmt(C_.fn)}</td><td class="num" style="color:var(--ok)">${fmt(C_.tp)}</td></tr>
            </tbody></table>
        </div></div>

      <div class="panel"><div class="panel-head"><h2>Model selection</h2></div>
        <div class="panel-body">
          <table><thead><tr><th></th><th>Family</th><th class="num">Val PR-AUC</th><th class="num">Train AUC</th><th class="num">Test AUC</th></tr></thead>
            <tbody>${m.selection.map(s => `<tr>
              <td>${s.selected ? '<span class="pill on">used</span>' : ''}</td>
              <td>${esc(s.name)}</td><td class="num">${s.val_pr_auc}</td>
              <td class="num">${s.train_roc_auc}</td><td class="num">${s.test_roc_auc}</td></tr>`).join('')}
            </tbody></table>
          <p class="muted small">All three are fitted on every build and the winner is chosen on validation
            PR-AUC, never on the test window. The train-versus-test gap is the reason: with ~7% positives and a
            temporal split, the flexible families spend capacity on structure that does not survive to the next week.</p>

          <div class="chart-title"><span>Reliability — predicted vs observed</span><span class="muted">isotonic, calibrated on validation</span></div>
          ${reliabilityChart(m.reliability)}
          <p class="muted small">A risk score shown to an operator has to mean what it says. Points on the diagonal
            mean 20% risk really does fail one time in five.</p>

          <div class="chart-title"><span>Precision and recall vs inspection capacity</span></div>
          <table><thead><tr><th class="num">Top-K / shift</th><th class="num">Share flagged</th><th class="num">Precision</th><th class="num">Recall</th></tr></thead>
            <tbody>${m.capacity_curve.map(c => `<tr${c.k === m.inspection_capacity_per_shift ? ' style="background:var(--bg-2)"' : ''}>
              <td class="num">${c.k}</td><td class="num">${pct(c.flagged_share, 1)}</td>
              <td class="num">${c.precision.toFixed(3)}</td><td class="num">${c.recall.toFixed(3)}</td></tr>`).join('')}
            </tbody></table>
        </div></div>

      <div class="panel"><div class="panel-head"><h2>Anomaly detection (SPC)</h2></div>
        <div class="panel-body">
          <div class="detail-grid">
            <div class="dstat"><div class="k">Actionable alerts</div><div class="v">${v.spc.actionable_per_shift}<span style="font-size:11px;color:var(--text-3)">/shift</span></div></div>
            <div class="dstat"><div class="k">Across</div><div class="v">${v.line.stations}<span style="font-size:11px;color:var(--text-3)"> stations</span></div></div>
            <div class="dstat"><div class="k">EWMA limit</div><div class="v">${v.spc.drift_limit}σ</div></div>
            <div class="dstat"><div class="k">Baseline</div><div class="v" style="font-size:15px">days ${v.spc.baseline_days[0]}–${v.spc.baseline_days[1] - 1}</div></div>
          </div>
          <p class="muted small">Control limits are fitted on a qualification window and then frozen, with
            assignable-cause points trimmed out of the baseline. A continuously self-updating baseline is how you
            build a drift detector that cannot detect drift — it re-centres on the fault.</p>
          <table><thead><tr><th>Seeded fault</th><th>Coverage</th><th class="num">Detected after</th></tr></thead>
            <tbody>${v.spc.detection_latency.map(x => `<tr>
              <td><b class="mono">${esc(x.station)}</b> — ${esc(x.title)}</td>
              <td><span class="chip ${x.tier}">${x.tier}</span></td>
              <td class="num">${x.detected_after_min ? fmt(x.detected_after_min) + ' min' : 'missed'}</td></tr>`).join('')}
            </tbody></table>
        </div></div>

      ${v.traceback && v.traceback.probes ? `
      <div class="panel"><div class="panel-head"><h2>Traceback accuracy vs. ground truth</h2>
        <span class="pill on">${v.traceback.probes} probes</span></div>
        <div class="panel-body">
          <p class="muted small" style="margin-top:0">The simulator records which station actually created every
            defect. The twin never sees that column. Sweeping probe times across the held-out window and comparing
            the leading suspect against the true modal origin turns "is this causation or correlation?" into a
            measurement.</p>
          <table><thead><tr><th>Reported confidence</th><th class="num">Windows</th><th class="num">Top-1 correct</th><th class="num">Top-3 correct</th></tr></thead>
            <tbody>
              ${['high','medium','low'].filter(k => v.traceback.by_confidence[k]).map(k => {
                const b = v.traceback.by_confidence[k];
                return `<tr><td><span class="chip ${k === 'high' ? 'FULL' : k === 'medium' ? 'PARTIAL' : 'DARK'}">${k.toUpperCase()}</span></td>
                  <td class="num">${b.n}</td><td class="num"><b>${pct(b.top1)}</b></td><td class="num">${pct(b.top3)}</td></tr>`;
              }).join('')}
              <tr><td><b>All windows</b></td><td class="num">${v.traceback.overall.n}</td>
                <td class="num"><b>${pct(v.traceback.overall.top1)}</b></td><td class="num">${pct(v.traceback.overall.top3)}</td></tr>
              <tr style="color:var(--text-3)"><td>Random upstream station</td><td class="num">—</td>
                <td class="num">${pct(v.traceback.random_baseline_top1)}</td><td class="num">—</td></tr>
            </tbody></table>
          <p class="muted small">Accuracy tracks the confidence the twin reported at the time. That is the point:
            the twin is not always right about root cause, but it knows when it is guessing, and it says so rather
            than promoting whichever candidate won by a nose.</p>
        </div></div>` : ''}

      <div class="panel"><div class="panel-head"><h2>Virtual sensors for dark stations</h2></div>
        <div class="panel-body">
          <div class="detail-grid">
            <div class="dstat"><div class="k">Held-out-station AUC</div><div class="v">${v.virtual_sensor.auc}</div></div>
            <div class="dstat"><div class="k">PR-AUC</div><div class="v">${v.virtual_sensor.ap}<span style="font-size:11px;color:var(--text-3)"> base ${v.virtual_sensor.base_rate}</span></div></div>
            <div class="dstat"><div class="k">Trust weight</div><div class="v">${v.virtual_sensor.trust}</div></div>
            <div class="dstat"><div class="k">Held-out stations</div><div class="v" style="font-size:15px">${v.virtual_sensor.holdout_stations.join(', ')}</div></div>
          </div>
          <p class="muted small">Trained to predict what vibration and torque channels <i>would</i> be saying, using
            only signals every station produces: cycle-time deviation from MES part scans, blocking and starving
            against neighbours, and the operator checklist. Validated by holding out whole stations, because that is
            the actual deployment question — will this transfer to a station it has never seen. The measured score
            becomes the weight: a mapping that did not generalise cannot raise an alarm.</p>
          <p class="muted small">Data confidence by tier —
            ${Object.entries(v.line.coverage).map(([k, c]) => `<span class="chip ${k}">${k}</span> ${c.stations} stations`).join(' · ')}</p>
        </div></div>
    </div>
    <div class="note" style="margin-top:16px">
      <b>What is real and what is simulated.</b> The plant itself is synthetic — a generator produces station
      telemetry, defect creation and gate detection from a latent causal model the twin never sees. Everything
      downstream of that is a genuine implementation: the SPC baselines, the virtual sensors, the feature pipeline,
      the model selection and calibration, the traceback and the economics all run on that record exactly as they
      would on an MES feed. Metrics on this page are computed on a held-out temporal split, not asserted.</div>`;
}

function reliabilityChart(pts) {
  if (!pts || !pts.length) return '<div class="empty small">not enough test points</div>';
  const w = 300, h = 190, pad = 30;
  const hi = Math.max(...pts.map(p => Math.max(p.predicted, p.observed)), 0.05) * 1.15;
  const X = v => pad + v / hi * (w - pad - 8);
  const Y = v => h - pad - v / hi * (h - pad - 12);
  return `<div class="chart"><svg viewBox="0 0 ${w} ${h}" style="max-width:330px">
    <line x1="${X(0)}" y1="${Y(0)}" x2="${X(hi)}" y2="${Y(hi)}" stroke="var(--line-2)" stroke-dasharray="4 3"/>
    <line x1="${pad}" y1="${Y(0)}" x2="${w - 8}" y2="${Y(0)}" stroke="var(--line)"/>
    <line x1="${pad}" y1="${Y(0)}" x2="${pad}" y2="12" stroke="var(--line)"/>
    <polyline fill="none" stroke="var(--purple)" stroke-width="1.6"
      points="${pts.map(p => `${X(p.predicted)},${Y(p.observed)}`).join(' ')}"/>
    ${pts.map(p => `<circle cx="${X(p.predicted)}" cy="${Y(p.observed)}" r="3" fill="var(--purple)"/>`).join('')}
    <text x="${pad}" y="${h - 8}" style="font:9px var(--mono);fill:var(--text-3)">0</text>
    <text x="${w - 30}" y="${h - 8}" style="font:9px var(--mono);fill:var(--text-3)">${pct(hi, 0)}</text>
    <text x="4" y="16" style="font:9px var(--mono);fill:var(--text-3)">observed</text>
    <text x="${w - 60}" y="${h - 20}" style="font:9px var(--mono);fill:var(--text-3)">predicted</text>
  </svg></div>`;
}

boot();
