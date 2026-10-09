// ABS Zone Explorer. 데이터는 ../data/abs/ (python -m visualbaseball.abs_explorer 산출물)을 fetch합니다.
(function () {
  const M = AbsZoneMath;
  const DATA = "../data/abs/";
  const params = new URLSearchParams(location.search);
  const $ = (id) => document.getElementById(id);
  const status = $("status");
  const css = getComputedStyle(document.documentElement);
  const token = (name, fallback) => (css.getPropertyValue(name).trim() || fallback);
  const COLORS = [token("--kbo-diverge-negative", "#0f4471"), token("--kbo-diverge-neutral", "#f6f6f6"), token("--kbo-diverge-positive", "#fc3c3c")];
  const NAVY = token("--kbo-navy", "#083358"), MUTED = token("--kbo-muted", "#5d6b7d");
  const PITCH = {FF: "포심", FT: "투심", SI: "싱커", FC: "커터", SL: "슬라이더", ST: "스위퍼", CH: "체인지업", CU: "커브", FS: "포크"};
  const GROUP = {fastball: "직구 계열", breaking: "브레이킹", offspeed: "오프스피드", other: "기타"};
  const REGION = {heart: "존 안쪽 5cm+", edge_in: "경계 안 0–5cm", edge_out: "경계 밖 0–5cm", out: "경계 밖 5cm+"};
  const EDGE = {side: "좌우", top: "상단", bottom: "하단"};
  const ROLE = {batter: "타자", pitcher: "투수"};
  const cache = new Map();
  let index = null, tracking = null;

  const fmt = (v, d = 1) => (v == null || Number.isNaN(v) ? "–" : Number(v).toFixed(d));
  const pct = (v, d = 1) => (v == null ? "–" : `${(100 * v).toFixed(d)}%`);
  const signed = (v, d = 2) => (v == null ? "–" : `${v > 0 ? "+" : ""}${Number(v).toFixed(d)}`);
  const esc = (s) => String(s).replace(/[&<>"]/g, (c) => ({"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;"}[c]));

  async function load(name) {
    if (!cache.has(name)) {
      cache.set(name, fetch(DATA + name).then((r) => {
        if (!r.ok) throw new Error(`${name} ${r.status}`);
        return r.json();
      }));
    }
    return cache.get(name);
  }

  function setOptions(select, values, labels, selected) {
    select.innerHTML = values.map((v) => `<option value="${esc(v)}">${esc(labels ? labels(v) : v)}</option>`).join("");
    if (selected != null && values.map(String).includes(String(selected))) select.value = selected;
  }

  // ── 화면 전환 ─────────────────────────────────────────────
  const views = ["map", "audit", "players"];
  function showView(view) {
    for (const v of views) {
      $(`view-${v}`).hidden = v !== view;
      document.querySelector(`[data-view="${v}"]`).setAttribute("aria-pressed", String(v === view));
    }
    if (view === "audit") renderAudit();
    if (view === "players") renderPlayers();
  }
  document.querySelectorAll("[data-view]").forEach((b) => b.addEventListener("click", () => showView(b.dataset.view)));

  // ── Zone Map ───────────────────────────────────────────────
  const PLOT = {left: 58, top: 16, width: 440, height: 480};
  function sx(grid, x) { return PLOT.left + (x - grid.x.start) / (grid.x.step * grid.x.bins) * PLOT.width; }
  function sy(grid, z) { return PLOT.top + PLOT.height - (z - grid.z_share.start) / (grid.z_share.step * grid.z_share.bins) * PLOT.height; }

  async function renderMap() {
    const season = Number($("map-season").value);
    const isAbs = index.abs_seasons.includes(season);
    const modeSelect = $("map-mode");
    for (const option of modeSelect.options) option.disabled = option.value !== "rate" && !isAbs;
    if (!isAbs) modeSelect.value = "rate";
    const mode = modeSelect.value;
    const key = [$("map-stance").value, $("map-count").value, $("map-group").value].join("|");
    const grid = await load(`zone_map_${season}.json`);
    const cells = M.decode(grid, key);
    const reference = mode === "vs2023" ? M.decode(await load("zone_map_2023.json"), key) : null;
    const nz = grid.z_share.bins, nx = grid.x.bins;
    const w = PLOT.width / nx, h = PLOT.height / nz;
    const parts = [`<rect x="${PLOT.left}" y="${PLOT.top}" width="${PLOT.width}" height="${PLOT.height}" fill="#fff" stroke="${token("--kbo-line", "#dde3ea")}"/>`];
    for (const [cell, value] of cells) {
      const v = M.cellValue(mode, value, reference && reference.get(cell));
      const color = M.colorFor(mode, v, COLORS);
      if (!color) continue;
      const c = M.cellCenter(grid, cell);
      parts.push(`<rect class="cell" shape-rendering="crispEdges" data-cell="${cell}" x="${(PLOT.left + c.ix * w).toFixed(1)}" y="${(PLOT.top + PLOT.height - (c.iz + 1) * h).toFixed(1)}" width="${w.toFixed(2)}" height="${h.toFixed(2)}" fill="${color}"/>`);
    }
    const ruleSeason = isAbs ? season : 2024;
    const outline = M.zoneOutline(index.rules[ruleSeason], index.ball_radius_cm);
    const rStroke = isAbs ? NAVY : MUTED;
    const ballShare = index.ball_radius_cm / 180;
    parts.push(`<rect x="${sx(grid, -outline.half)}" y="${sy(grid, outline.top)}" width="${sx(grid, outline.half) - sx(grid, -outline.half)}" height="${sy(grid, outline.bottom) - sy(grid, outline.top)}" fill="none" stroke="${rStroke}" stroke-width="2.5" ${isAbs ? "" : 'stroke-dasharray="6 4"'}/>`);
    parts.push(`<rect x="${sx(grid, -outline.halfWithBall)}" y="${sy(grid, outline.top + ballShare)}" width="${sx(grid, outline.halfWithBall) - sx(grid, -outline.halfWithBall)}" height="${sy(grid, outline.bottom - ballShare) - sy(grid, outline.top + ballShare)}" fill="none" stroke="${rStroke}" stroke-width="1.2" stroke-dasharray="3 3"/>`);
    for (let x = -60; x <= 60; x += 20) {
      parts.push(`<line x1="${sx(grid, x)}" x2="${sx(grid, x)}" y1="${PLOT.top + PLOT.height}" y2="${PLOT.top + PLOT.height + 5}" stroke="${MUTED}"/><text class="axis" x="${sx(grid, x)}" y="${PLOT.top + PLOT.height + 18}" text-anchor="middle">${x}</text>`);
    }
    for (let z = 0.1; z <= 0.76; z += 0.1) {
      parts.push(`<line x1="${PLOT.left - 5}" x2="${PLOT.left}" y1="${sy(grid, z)}" y2="${sy(grid, z)}" stroke="${MUTED}"/><text class="axis" x="${PLOT.left - 8}" y="${sy(grid, z) + 4}" text-anchor="end">${z.toFixed(1)}</text>`);
    }
    parts.push(`<text class="axis-title" x="${PLOT.left + PLOT.width / 2}" y="${PLOT.top + PLOT.height + 38}" text-anchor="middle">중간면 x (cm, 포수 시점)</text>`);
    parts.push(`<text class="axis-title" transform="translate(14 ${PLOT.top + PLOT.height / 2}) rotate(-90)" text-anchor="middle">중간면 높이 / 신장</text>`);
    $("zone-map").innerHTML = parts.join("");
    attachMapTooltip(grid, cells, reference, mode);

    const modeLabel = {rate: "판정 스트라이크율", umpire: "ABS 판정 − 2023 심판 모형 예상", vs2023: "판정 스트라이크율 차이 (해당 시즌 − 2023)"}[mode];
    $("map-title").textContent = `${season} ${modeLabel}${isAbs ? "" : " · 심판 판정 (참고 점선: 2024 ABS 존)"}`;
    $("map-legend").innerHTML = mode === "rate"
      ? `<span>0%</span><i style="background:linear-gradient(90deg,${COLORS.join(",")})"></i><span>100%</span>`
      : `<span>−30%p</span><i style="background:linear-gradient(90deg,${COLORS.join(",")})"></i><span>+30%p</span>`;
    const t = M.totals(cells);
    const rule = index.rules[ruleSeason];
    const stats = [
      ["테이크", t.n.toLocaleString()],
      ["판정 스트라이크율", pct(t.rate)],
      ["심판 모형 예상", isAbs ? pct(t.expected) : "–"],
      ["존 규정", isAbs ? `${(rule.top_ratio * 100).toFixed(2)}% / ${(rule.bottom_ratio * 100).toFixed(2)}%` : "심판 (ABS 이전)"],
    ];
    $("map-summary").innerHTML = stats.map(([k, v]) => `<div><dt>${k}</dt><dd>${v}</dd></div>`).join("");
    syncUrl({view: "map", season});
    const card = document.querySelector("[data-thumbnail-target]");
    if (card) card.dataset.thumbnailReady = "true";
  }

  function attachMapTooltip(grid, cells, reference, mode) {
    const svg = $("zone-map"), tip = $("map-tooltip");
    svg.onpointermove = (event) => {
      const target = event.target.closest(".cell");
      if (!target) { tip.hidden = true; return; }
      const cell = Number(target.dataset.cell), c = cells.get(cell), center = M.cellCenter(grid, cell);
      const ref = reference && reference.get(cell);
      const lines = [`x ${fmt(center.x - grid.x.step / 2, 0)}~${fmt(center.x + grid.x.step / 2, 0)}cm · 높이/신장 ${fmt(center.z - grid.z_share.step / 2, 2)}~${fmt(center.z + grid.z_share.step / 2, 2)}`,
        `테이크 ${c.n} · 스트라이크 ${pct(c.k / c.n)}`];
      if (c.p != null) lines.push(`심판 모형 예상 ${pct(c.p / c.n)}`);
      if (mode === "vs2023" && ref) lines.push(`2023 같은 칸 ${pct(ref.k / ref.n)} (n=${ref.n})`);
      tip.innerHTML = lines.map(esc).join("<br>");
      const box = svg.getBoundingClientRect();
      tip.style.left = `${Math.min(event.clientX - box.left + 12, box.width - 200)}px`;
      tip.style.top = `${event.clientY - box.top + 12}px`;
      tip.hidden = false;
    };
    svg.onpointerleave = () => { tip.hidden = true; };
  }

  // ── Tracking Audit ─────────────────────────────────────────
  function table(el, head, rows) {
    el.innerHTML = `<thead><tr>${head.map((h) => `<th>${h}</th>`).join("")}</tr></thead><tbody>${rows.map((r) => `<tr>${r.map((c) => `<td>${c}</td>`).join("")}</tr>`).join("")}</tbody>`;
  }
  const reconRow = (label, r) => [esc(label), r.takes.toLocaleString(), pct(r.agreement, 2), r.mismatches, r.mismatches_beyond_2cm, r.boundary_takes.toLocaleString(), pct(r.boundary_agreement, 2), fmt(r.bias_cm, 2), fmt(r.sigma_cm, 2)];
  const RECON_HEAD = ["구분", "테이크", "일치율", "불일치", "경계 2cm 밖 불일치", "경계 10cm 이내", "경계 일치율", "편향 cm", "σ cm"];

  async function renderAudit() {
    if (!tracking) tracking = await load("tracking.json");
    const recon = tracking.reconstruction, pooled = recon.pooled.overall;
    const tmSeasons = Object.keys(tracking.trackman_vs_pts);
    const tmPairs = tmSeasons.reduce((s, k) => s + tracking.trackman_vs_pts[k].pairs, 0);
    $("audit-cards").innerHTML = [
      ["재구성 일치율 (2024–2026)", pct(pooled.agreement, 2), `${pooled.takes.toLocaleString()} 테이크 중 불일치 ${pooled.mismatches}`],
      ["경계 불일치 폭 σ", `${fmt(pooled.sigma_cm, 2)} cm`, "VB 재구성 좌표와 공식 판정 사이 (내부 일관성)"],
      ["2025 규정 하향 효과", pct(recon.seasons["2025"].rule_change_vs_2024 && recon.seasons["2025"].rule_change_vs_2024.share, 2), "2024 규정이면 판정이 달라지는 2025 테이크"],
      ["TrackMan 대조 투구", tmPairs.toLocaleString(), `${tmSeasons.join("·")} · 위치 없음, 무브먼트만`],
    ].map(([a, b, c]) => `<div><span>${a}</span><strong>${b}</strong><small>${c}</small></div>`).join("");
    table($("recon-seasons"), RECON_HEAD, Object.entries(recon.seasons).map(([s, v]) => reconRow(s, v.overall)).concat([reconRow("합계", pooled)]));
    table($("recon-pitch"), RECON_HEAD, recon.pooled.by_pitch_code.map((r) => reconRow(PITCH[r.group] || r.group, r)));
    table($("recon-stadium"), RECON_HEAD, recon.pooled.by_stadium.map((r) => reconRow(r.group, r)));

    setOptions($("tm-season"), tmSeasons, null, $("tm-season").value || tmSeasons[tmSeasons.length - 1]);
    setOptions($("sens-season"), Object.keys(tracking.sensitivity), null, $("sens-season").value || "2025");
    renderTrackman();
    renderSensitivity();
    renderSsw();
  }

  function renderTrackman() {
    const entry = tracking.trackman_vs_pts[$("tm-season").value];
    if (!entry) return;
    const comp = entry.scaled_residual[$("tm-component").value];
    const rows = comp.by_group;
    const span = Math.max(4, ...rows.map((r) => Math.max(Math.abs(r.ci90_low), Math.abs(r.ci90_high))));
    const at = (v) => `${50 + v / span * 50}%`;
    $("tm-chart").innerHTML = rows.map((r) => {
      const low = Math.min(0, r.mean), high = Math.max(0, r.mean);
      const ssw = r.group === "SSW 문헌 구종" || r.group === "기타 구종";
      return `<div class="abs-bar-row${ssw ? " ssw" : ""}"><span>${esc(PITCH[r.group] || r.group)}</span>` +
        `<div class="abs-bar-track"><i class="zero" style="left:50%"></i><i class="fill" style="left:${at(low)};width:${(high - low) / span * 50}%;background:${r.mean >= 0 ? COLORS[2] : COLORS[0]}"></i>` +
        `<i class="ci" style="left:${at(r.ci90_low)};width:${(r.ci90_high - r.ci90_low) / span * 50}%"></i></div>` +
        `<span>${signed(r.mean, 2)} cm</span></div>`;
    }).join("") + `<p class="abs-note">기울기 ${fmt(comp.slope, 3)} (VB ≈ ${fmt(comp.slope, 2)} × TM + ${fmt(comp.intercept, 1)}cm), 잔차 SD ${fmt(comp.residual_sd, 1)}cm. 굵은 줄은 SSW 문헌 구종(투심·싱커·체인지업·포크·스위퍼) 묶음과 나머지 — 가설 라벨이며 실제 SSW 측정이 아닙니다.</p>`;
    const o = entry.overall;
    table($("tm-overall"), ["항목 (VB − TM)", "투구", "중앙값", "MAD", "|차이| 90%"], [
      ["수평 무브먼트 cm (포수 시점)", o.d_hb.n, fmt(o.d_hb.median, 2), fmt(o.d_hb.mad, 2), fmt(o.d_hb.p90_abs, 1)],
      ["수직 무브먼트 cm", o.d_ivb.n, fmt(o.d_ivb.median, 2), fmt(o.d_ivb.mad, 2), fmt(o.d_ivb.p90_abs, 1)],
      ["구속 km/h", o.d_speed.n, fmt(o.d_speed.median, 2), fmt(o.d_speed.mad, 2), fmt(o.d_speed.p90_abs, 1)],
      ["릴리스 높이 cm", o.d_rel_height.n, fmt(o.d_rel_height.median, 2), fmt(o.d_rel_height.mad, 2), fmt(o.d_rel_height.p90_abs, 1)],
    ]);
  }

  function renderSensitivity() {
    const s = tracking.sensitivity[$("sens-season").value];
    if (!s) return;
    const sigmas = Object.keys(s);
    const codes = Object.keys(s[sigmas[0]].by_pitch_code);
    const rows = [["전체 (독립 오차)", ...sigmas.map((k) => pct(s[k].expected_flip_share, 2))],
      ["경계 전체가 안쪽으로 (계통)", ...sigmas.map((k) => pct(s[k].systematic_inward_share, 2))],
      ["경계 전체가 바깥쪽으로 (계통)", ...sigmas.map((k) => pct(s[k].systematic_outward_share, 2))]];
    for (const e of Object.keys(s[sigmas[0]].by_edge)) rows.push([`경계: ${EDGE[e] || e}`, ...sigmas.map((k) => pct(s[k].by_edge[e], 2))]);
    for (const c of codes) rows.push([`구종: ${PITCH[c] || c}`, ...sigmas.map((k) => pct(s[k].by_pitch_code[c], 2))]);
    table($("sens-table"), ["시나리오", ...sigmas.map((k) => `가정 σ ${k}cm`)], rows);
  }

  function renderSsw() {
    const pooled = tracking.reconstruction.pooled;
    const sigma = (code) => (pooled.by_pitch_code.find((r) => r.group === code) || {}).sigma_cm;
    $("ssw-list").innerHTML = [
      "<strong>H1 (SSW 구종에서 궤적 추정 오차 증가)</strong>: 검증 불가. PTS 원시 추적점, 회전축·회전 효율, 독립 탄착 좌표가 모두 없습니다. VB 궤적은 등가속도(9-parameter) 적합이라 시간에 따라 변하는 SSW 힘을 표현하지 못하지만, 그 적합이 실제 탄착과 얼마나 다른지는 독립 좌표 없이 알 수 없습니다.",
      `<strong>H2 (특정 구종의 체계적 차이)</strong>: 부분 확인(무브먼트, 독립 장비). TrackMan 대비 잔차는 커브·슬라이더·커터(글러브쪽 브레이킹)에서 크고, SSW 문헌 구종 묶음은 나머지보다 크지 않습니다. 측정 구간 정의 차이로 설명될 수 있어 SSW 근거로 보지 않습니다.`,
      `<strong>H3 (경계 판정 차이)</strong>: 공식 판정과 VB 재구성의 불일치 폭 σ는 구종별로 ${["FT", "CH", "FS", "ST"].map((c) => `${PITCH[c]} ${fmt(sigma(c), 2)}cm`).join(", ")} / 포심 ${fmt(sigma("FF"), 2)}cm로 모두 0.2cm 이하입니다. 같은 계통 자료끼리의 비교라 실제 측정 오차가 아니며, 구종별로 판정을 바꿀 만한 차이는 보이지 않습니다.`,
      "실제 측정 오차의 크기는 ‘가정’ 시나리오로만 보여 줍니다. 독립 탄착 좌표(Hawk-Eye·TrackMan 위치, 또는 PTS 원시 자료)를 확보하기 전에는 정확도 결과를 산출하지 않습니다.",
    ].map((t) => `<li>${t}</li>`).join("");
  }

  // ── Winners & Losers ───────────────────────────────────────
  let selectedPlayer = null;
  async function renderPlayers() {
    const scope = $("pl-scope").value, role = $("pl-role").value;
    const data = await load(`players_${role}_${scope}.json`);
    const summary = scope.includes("-") ? null : index.season_summary[scope];
    const rows = M.filterPlayers(data.players, {qualified: $("pl-qualified").value === "qualified", search: $("pl-search").value, sort: $("pl-sort").value});
    const league = summary ? `${scope} 리그 전체: 테이크 ${summary.takes.toLocaleString()} · 판정 스트라이크율 ${pct(summary.recorded_strike_rate)} vs 2023 심판 모형 예상 ${pct(summary.umpire_expected_strike_rate)} · 타자 ABS RV ${signed(summary.league_abs_rv_batter_per_1000, 2)}점/1000 테이크. ` : "";
    $("pl-league").textContent = `${league}‘리그 대비’는 이 리그 평균 이동을 뺀 값입니다. ${ROLE[role]} 기준 + 는 유리한 판정, 규정 표본 ${index.qualified_takes[role]} 테이크.`;
    const head = ["#", `<span>${ROLE[role]}</span>`, "판정 기회", "리그 대비<br>ABS RV", "90% 구간", "리그 대비<br>/1000", "ABS RV<br>(원값)", "유리<br>판정", "불리<br>판정", "1cm 오차<br>SD (가정)"];
    $("pl-table").innerHTML = `<thead><tr>${head.map((h, i) => `<th class="${i === 1 ? "name" : ""}">${h}</th>`).join("")}</tr></thead><tbody>${rows.map((p, i) => {
      const sure = M.ciExcludesZero(p.relative_ci90_low, p.relative_ci90_high);
      const cls = sure ? (p.relative_rv > 0 ? "abs-pos" : "abs-neg") : "abs-uncertain";
      return `<tr data-id="${esc(p.id)}" class="${p.id === selectedPlayer ? "selected" : ""}"><td>${i + 1}</td><td class="name">${esc(p.name)}</td><td>${p.takes.toLocaleString()}</td>` +
        `<td class="value ${cls}">${signed(p.relative_rv)}</td><td class="abs-ci">${signed(p.relative_ci90_low, 1)} ~ ${signed(p.relative_ci90_high, 1)}</td>` +
        `<td>${signed(p.relative_per_1000)}</td><td>${signed(p.abs_rv)}</td><td>${fmt(p.favorable_calls)}</td><td>${fmt(p.unfavorable_calls)}</td><td>±${fmt(p.noise_sd_1cm, 2)}</td></tr>`;
    }).join("")}</tbody>`;
    $("pl-table").querySelectorAll("tbody tr").forEach((tr) => tr.addEventListener("click", () => {
      selectedPlayer = tr.dataset.id;
      renderPlayers();
    }));
    renderDetail(data, role);
    renderNotes();
    syncUrl({view: "players", scope, role});
  }

  function renderDetail(data, role) {
    const panel = $("pl-detail");
    const player = data.players.find((p) => p.id === selectedPlayer);
    if (!player) { panel.hidden = true; return; }
    const detail = data.details[player.id];
    const block = (title, rows, labels) => {
      if (!rows || !rows.length) return "";
      const span = Math.max(.5, ...rows.map((r) => Math.abs(r.abs_rv)));
      return `<section><h3>${title}</h3><div class="abs-bars">${rows.slice(0, 12).map((r) => `<div class="abs-bar-row"><span>${esc(labels ? (labels[r.group] || r.group) : r.group)}</span>` +
        `<div class="abs-bar-track"><i class="zero" style="left:50%"></i><i class="fill" style="left:${50 + Math.min(0, r.abs_rv) / span * 50}%;width:${Math.abs(r.abs_rv) / span * 50}%;background:${r.abs_rv >= 0 ? COLORS[2] : COLORS[0]}"></i></div>` +
        `<span>${signed(r.abs_rv)} · ${r.takes}</span></div>`).join("")}</div></section>`;
    };
    panel.hidden = false;
    panel.innerHTML = `<h2>${esc(player.name)} · ${ROLE[role]} 세부 (${esc($("pl-scope").value)})</h2>` +
      `<p class="abs-note">ABS RV ${signed(player.abs_rv)}점 (90% 구간 ${signed(player.ci90_low, 1)} ~ ${signed(player.ci90_high, 1)}), 리그 대비 ${signed(player.relative_rv)}점. 기대 판정 차이 순합 ${signed(player.net_calls, 1)}개. ` +
      `가정 시나리오: 모든 경계가 1cm 안쪽이면 ${signed(player.shift_in_1cm)}점, 바깥쪽이면 ${signed(player.shift_out_1cm)}점 바뀝니다. 아래 막대는 원값(리그 평균 미차감) 기여, 오른쪽 숫자는 득점·테이크 수입니다.</p>` +
      (detail ? `<div class="abs-detail-grid">${block("구종", detail.pitch_group, GROUP)}${block("카운트 (볼-스트라이크)", detail.count)}${block("경계 거리", detail.region, REGION)}${block("경계 방향", detail.edge, EDGE)}${block("구장", detail.stadium)}</div>` : `<p class="abs-note">테이크 150개 미만이라 세부 분해를 만들지 않았습니다.</p>`);
  }

  function renderNotes() {
    const rel = index.reliability;
    const role = $("pl-role").value;
    const scope = $("pl-scope").value;
    const split = rel[`${scope}|${role}`] || {};
    const yoy = rel[`2024_to_2025|${role}`] || {};
    const alt = rel[`umpire_2022_vs_2023|${role}`] || {};
    const items = [
      "ABS RV = (2023 심판 모형의 스트라이크 확률 − 실제 ABS 판정) × (볼과 루킹 스트라이크의 RE288 득점 차). 타자는 그대로, 투수는 부호를 뒤집습니다.",
      `신뢰도: 이 기간 홀짝 경기 분할 상관 r=${fmt(split.pearson_r, 2)} (선수 ${split.players || 0}명), 2024→2025 상관 r=${fmt(yoy.pearson_r, 2)}. 한 시즌 값은 잡음이 크므로 순위를 확정적으로 읽지 마십시오.`,
      `기준 심판 연도 민감도: 2022 심판 기준으로 다시 계산한 선수 값과의 상관 r=${fmt(alt.pearson_r, 2)}. 리그 전체 이동은 기준 연도에 따라 크게 달라집니다(분석 문서 참조).`,
      "90% 구간은 경기 단위 부트스트랩으로 표본 변동만 반영합니다. 심판 모형 자체의 불확실성, 심판·포수 개인 효과, ABS 시대의 타자·투수 행동 변화(테이크 선택)는 포함하지 않습니다. 구간이 0을 지나면 회색으로 표시합니다.",
      "‘1cm 오차 SD’는 ABS 좌표에 독립적인 1cm 오차가 있다고 가정했을 때의 변동이며, 관측된 추적 오차가 아닙니다. ABS 도입 효과(이 표)와 PTS 측정 오류 효과(가정 시나리오)는 별개입니다.",
    ];
    $("pl-notes").innerHTML = items.map((t) => `<li>${esc(t)}</li>`).join("");
  }

  function syncUrl(state) {
    if (params.get("thumb") === "1") return;
    const next = new URLSearchParams(state);
    history.replaceState(null, "", `${location.pathname}?${next}`);
  }

  // ── 시작 ───────────────────────────────────────────────────
  async function start() {
    index = await load("index.json");
    const seasons = index.seasons.map(String);
    setOptions($("map-season"), seasons, (s) => (index.abs_seasons.includes(Number(s)) ? `${s} (ABS)` : `${s} (심판)`), params.get("season") || seasons[seasons.length - 2]);
    setOptions($("pl-scope"), index.scopes, (s) => (s.includes("-") ? `${s} 합계` : s), params.get("scope") || "2024-2026");
    if (params.get("role")) $("pl-role").value = params.get("role");
    for (const id of ["map-season", "map-mode", "map-stance", "map-count", "map-group"]) $(id).addEventListener("change", () => renderMap().catch(fail));
    for (const id of ["pl-scope", "pl-role", "pl-qualified", "pl-sort"]) $(id).addEventListener("change", () => { if (id !== "pl-sort") selectedPlayer = null; renderPlayers().catch(fail); });
    $("pl-search").addEventListener("input", () => renderPlayers().catch(fail));
    $("tm-season").addEventListener("change", renderTrackman);
    $("tm-component").addEventListener("change", renderTrackman);
    $("sens-season").addEventListener("change", renderSensitivity);
    await renderMap();
    status.textContent = "";
    const view = params.get("view");
    if (views.includes(view) && view !== "map") showView(view);
  }

  function fail(error) {
    status.textContent = `데이터를 불러오지 못했습니다: ${error.message}`;
  }

  start().catch(fail);
})();
