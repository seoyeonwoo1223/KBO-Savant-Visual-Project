const yearSelect = document.querySelector("#year");
const throwsSelect = document.querySelector("#throws");
const searchForm = document.querySelector("#search-form");
const queryInput = document.querySelector("#query");
const searchButton = searchForm.querySelector('button[type="submit"]');
const matches = document.querySelector("#matches");
const message = document.querySelector("#message");
const profileSection = document.querySelector("#profile");
const modeSelect = document.querySelector("#movement-mode");
const movementViewButtons = document.querySelectorAll("[data-movement-view]");
const movementUnitButtons = document.querySelectorAll("[data-movement-unit]");
const exportButton = document.querySelector("#export-profile");
const SVG_NS = "http://www.w3.org/2000/svg";
const normalize = value => String(value || "").replace(/\s+/g, "").toLowerCase();
const fmt = (value, digits = 1) => value == null ? "—" : Number(value).toFixed(digits);
const escapeHtml = value => String(value).replace(/[&<>'"]/g, character => ({"&":"&amp;","<":"&lt;",">":"&gt;","'":"&#39;",'"':"&quot;"}[character]));

let seasonIndex = null;
let currentProfile = null;
let seasonLoadPromise = null;
let movementView = "pitcher";
let movementUnit = "in";

function svgElement(name, attributes = {}) {
  const element = document.createElementNS(SVG_NS, name);
  Object.entries(attributes).forEach(([key, value]) => element.setAttribute(key, value));
  return element;
}

function svgText(svg, text, attributes = {}) {
  const element = svgElement("text", attributes);
  element.textContent = text;
  svg.append(element);
  return element;
}

function clearSvg(svg) {
  svg.querySelectorAll(":scope > :not(title):not(desc)").forEach(element => element.remove());
}

function toPitcherView(horizontal) {
  if (!horizontal) return horizontal;
  return {...horizontal, average: -horizontal.average, low_75: -horizontal.high_75, high_75: -horizontal.low_75};
}

function movementHorizontal(horizontal) {
  return movementView === "pitcher" ? toPitcherView(horizontal) : horizontal;
}

function movementUnitLabel() {
  return movementUnit === "cm" ? "cm" : "in.";
}

function formatMovement(value) {
  return value == null ? "—" : fmt(value * (movementUnit === "cm" ? 2.54 : 1));
}

function renderMovementViewControl() {
  movementViewButtons.forEach(button => button.setAttribute("aria-pressed", String(button.dataset.movementView === movementView)));
  movementUnitButtons.forEach(button => button.setAttribute("aria-pressed", String(button.dataset.movementUnit === movementUnit)));
  document.querySelector("#movement-view-label").textContent = `${movementView === "pitcher" ? "투수" : "포수"} 시점 · ${movementUnitLabel()}`;
}

async function loadSeason(year) {
  seasonIndex = null;
  searchButton.disabled = true;
  searchForm.setAttribute("aria-busy", "true");
  message.textContent = `${year} 선수 목록을 불러오는 중입니다.`;
  try {
    const response = await fetch(`../data/pitch_arsenal/${year}/index.json`);
    if (!response.ok) throw new Error("season index unavailable");
    seasonIndex = await response.json();
    matches.innerHTML = "";
    message.textContent = "";
    const params = new URLSearchParams(location.search);
    if (params.get("year") === String(year) && params.get("player")) await openPlayer(params.get("player"), false);
  } finally {
    searchButton.disabled = false;
    searchForm.removeAttribute("aria-busy");
  }
}

function beginSeasonLoad(year) {
  seasonLoadPromise = loadSeason(year).catch(() => {
    message.textContent = "Pitch Arsenal 데이터를 불러오지 못했습니다. 잠시 후 다시 시도해 주세요.";
    return null;
  });
  return seasonLoadPromise;
}

async function openPlayer(playerId, updateUrl = true) {
  const player = seasonIndex.players.find(item => String(item.id) === String(playerId));
  if (!player) return;
  const response = await fetch(`../data/pitch_arsenal/${yearSelect.value}/${player.file}`);
  if (!response.ok) throw new Error("profile unavailable");
  const shard = await response.json();
  currentProfile = shard.players[String(player.id)];
  if (!currentProfile) throw new Error("profile unavailable");
  if (updateUrl) history.replaceState(null, "", `?player=${encodeURIComponent(player.id)}&year=${yearSelect.value}`);
  renderProfile();
}

function filteredPlayers() {
  const hand = throwsSelect.value;
  const term = normalize(queryInput.value);
  return (seasonIndex?.players || []).filter(player => (!hand || player.throws === hand) && (!term || normalize(player.name).includes(term)));
}

async function handleSearch(event) {
  event?.preventDefault();
  if (!seasonIndex && seasonLoadPromise) await seasonLoadPromise;
  if (!seasonIndex) {
    message.textContent = "선수 목록을 불러오지 못했습니다. 연도를 다시 선택해 주세요.";
    return;
  }
  const found = filteredPlayers();
  const exact = found.find(player => normalize(player.name) === normalize(queryInput.value));
  if (exact || found.length === 1) {
    message.textContent = "선수 정보를 불러오는 중입니다.";
    try {
      await openPlayer((exact || found[0]).id);
      message.textContent = "";
    } catch {
      message.textContent = "선수 정보를 불러오지 못했습니다. 잠시 후 다시 시도해 주세요.";
    }
    return;
  }
  matches.innerHTML = found.slice(0, 12).map(player => `<button type="button" data-id="${escapeHtml(player.id)}">${escapeHtml(player.name)} · ${player.throws || "?"}HP</button>`).join("");
  matches.querySelectorAll("button").forEach(button => button.addEventListener("click", async () => {
    await openPlayer(button.dataset.id);
    message.textContent = "";
  }));
  message.textContent = found.length ? `검색 결과 ${found.length}명${found.length > 12 ? " · 상위 12명 표시" : ""}` : "조건에 맞는 투수를 찾지 못했습니다.";
}

function renderProfile() {
  const player = currentProfile.player;
  const overall = currentProfile.overall || {};
  profileSection.hidden = false;
  document.querySelector("#profile-season").textContent = `${currentProfile.season} KBO SEASON`;
  document.querySelector("#player-name").textContent = player.name;
  document.querySelector("#profile-meta").textContent = `${player.throws || "?"}HP · ${currentProfile.pitch_types.length} PITCH TYPES`;
  document.querySelector("#summary-hand").textContent = `${player.throws || "?"}HP`;
  document.querySelector("#summary-pitches").textContent = player.pitches.toLocaleString();
  document.querySelector("#summary-vrel").textContent = `${fmt(overall.release?.v_rel_ft?.average, 2)} ft`;
  document.querySelector("#summary-hrel").textContent = `${fmt(overall.release?.h_rel_ft?.average, 2)} ft`;
  const adjusted = currentProfile.pitch_types.reduce((sum, pitch) => sum + pitch.movement_n, 0);
  const total = currentProfile.pitch_types.reduce((sum, pitch) => sum + pitch.movement_total_n, 0);
  document.querySelector("#coverage").textContent = `보정 무브먼트 ${adjusted.toLocaleString()} / ${total.toLocaleString()} (${total ? (adjusted / total * 100).toFixed(1) : "0.0"}%)`;
  renderVelocity();
  renderMovement();
  renderFrequency();
  renderLegend();
  renderTable();
  profileSection.scrollIntoView({behavior: "smooth", block: "start"});
}

function renderVelocity() {
  const svg = document.querySelector("#velocity-chart");
  clearSvg(svg);
  const pitches = currentProfile.pitch_types.filter(pitch => pitch.velocity_distribution_kmh?.counts?.length);
  const width = 420;
  const rowHeight = 50;
  const height = Math.max(270, 60 + pitches.length * rowHeight);
  svg.setAttribute("viewBox", `0 0 ${width} ${height}`);
  if (!pitches.length) {
    svgText(svg, "구속 분포 자료가 없습니다.", {x: width / 2, y: height / 2, "text-anchor": "middle", class: "empty-chart"});
    return;
  }
  const minValue = Math.floor(Math.min(...pitches.map(pitch => pitch.velocity_distribution_kmh.start)) / 5) * 5;
  const maxValue = Math.ceil(Math.max(...pitches.map(pitch => pitch.velocity_distribution_kmh.start + (pitch.velocity_distribution_kmh.counts.length - 1) * pitch.velocity_distribution_kmh.step)) / 5) * 5;
  const bounds = {left: 61, right: 405, top: 22, bottom: height - 34};
  const x = value => bounds.left + (value - minValue) / Math.max(1, maxValue - minValue) * (bounds.right - bounds.left);
  for (let value = minValue; value <= maxValue; value += 5) {
    svg.append(svgElement("line", {x1: x(value), x2: x(value), y1: bounds.top, y2: bounds.bottom, class: "chart-grid-line"}));
    svgText(svg, String(value), {x: x(value), y: height - 14, "text-anchor": "middle", class: "chart-axis-text"});
  }
  pitches.forEach((pitch, index) => {
    const histogram = pitch.velocity_distribution_kmh;
    const smooth = histogram.counts.map((count, bin) => ((histogram.counts[bin - 1] || 0) + count * 2 + (histogram.counts[bin + 1] || 0)) / 4);
    const peak = Math.max(...smooth, 1);
    const baseline = 45 + index * rowHeight;
    const points = smooth.map((count, bin) => [x(histogram.start + bin * histogram.step), baseline - count / peak * 31]);
    const pathData = [`M ${points[0][0]} ${baseline}`, ...points.map(point => `L ${point[0]} ${point[1]}`), `L ${points.at(-1)[0]} ${baseline}`, "Z"].join(" ");
    svg.append(svgElement("path", {d: pathData, fill: pitch.color, "fill-opacity": .26, stroke: pitch.color, class: "velocity-area"}));
    const averageX = x(pitch.velocity_kmh.average);
    svg.append(svgElement("line", {x1: averageX, x2: averageX, y1: baseline - 35, y2: baseline + 2, stroke: pitch.color, class: "velocity-average"}));
    svgText(svg, pitch.name, {x: 3, y: baseline - 12, class: "chart-row-label"});
    svgText(svg, `${fmt(pitch.velocity_kmh.average)} km/h`, {x: 3, y: baseline + 5, class: "chart-row-sub"});
    if (index < pitches.length - 1) svg.append(svgElement("line", {x1: bounds.left, x2: bounds.right, y1: baseline + 17, y2: baseline + 17, class: "chart-grid-line"}));
  });
}

function movementPoint(pair) {
  const horizontal = movementView === "pitcher" ? -pair[0] : pair[0];
  return [horizontal, pair[1]];
}

function renderMovement() {
  const svg = document.querySelector("#movement-chart");
  clearSvg(svg);
  const bounds = {left: 58, right: 592, top: 42, bottom: 558, xMin: -30, xMax: 30, yMin: -30, yMax: 30};
  const x = value => bounds.left + (value - bounds.xMin) / (bounds.xMax - bounds.xMin) * (bounds.right - bounds.left);
  const y = value => bounds.bottom - (value - bounds.yMin) / (bounds.yMax - bounds.yMin) * (bounds.bottom - bounds.top);
  for (let value = -30; value <= 30; value += 10) {
    svg.append(svgElement("line", {x1: x(value), x2: x(value), y1: bounds.top, y2: bounds.bottom, class: value === 0 ? "chart-zero-line" : "chart-grid-line"}));
    svgText(svg, formatMovement(value), {x: x(value), y: 579, "text-anchor": "middle", class: "chart-axis-text"});
    svg.append(svgElement("line", {x1: bounds.left, x2: bounds.right, y1: y(value), y2: y(value), class: value === 0 ? "chart-zero-line" : "chart-grid-line"}));
    svgText(svg, formatMovement(value), {x: 49, y: y(value) + 4, "text-anchor": "end", class: "chart-axis-text"});
  }
  svg.append(svgElement("rect", {x: bounds.left, y: bounds.top, width: bounds.right - bounds.left, height: bounds.bottom - bounds.top, class: "chart-border"}));
  svgText(svg, movementView === "pitcher" ? "1B  ←  MOVES TOWARD  →  3B" : "3B  ←  MOVES TOWARD  →  1B", {x: 325, y: 21, "text-anchor": "middle", class: "chart-direction"});
  svgText(svg, "Horizontal Break", {x: 325, y: 611, "text-anchor": "middle", class: "chart-axis-title"});
  svgText(svg, "Induced Vertical Break", {x: 14, y: 300, transform: "rotate(-90 14 300)", "text-anchor": "middle", class: "chart-axis-title"});

  const raw = modeSelect.value === "raw";
  currentProfile.pitch_types.forEach(pitch => {
    const horizontal = movementHorizontal(raw ? pitch.raw_horizontal_break_in : pitch.horizontal_break_in);
    const vertical = raw ? pitch.raw_ivb_in : pitch.ivb_in;
    if (!horizontal || !vertical) return;
    const usageScale = Math.min(1, Math.max(.18, pitch.usage / 10));
    const pointSet = pitch.movement_points_in?.[raw ? "raw" : "adjusted"] || [];
    pointSet.forEach(pair => {
      const point = movementPoint(pair);
      if (point[0] < -30 || point[0] > 30 || point[1] < -30 || point[1] > 30) return;
      svg.append(svgElement("circle", {cx: x(point[0]), cy: y(point[1]), r: 2.15, fill: pitch.color, "fill-opacity": .18 + .28 * usageScale, class: "movement-point"}));
    });
    const ellipse = svgElement("ellipse", {
      cx: x(horizontal.average), cy: y(vertical.average),
      rx: Math.max(6, Math.abs(x(horizontal.high_75) - x(horizontal.low_75)) / 2),
      ry: Math.max(6, Math.abs(y(vertical.high_75) - y(vertical.low_75)) / 2),
      fill: pitch.color, "fill-opacity": .045 + .06 * usageScale, stroke: pitch.color,
      "stroke-opacity": .45 + .45 * usageScale, "stroke-width": 2.5, class: "movement-ellipse", tabindex: 0,
      "aria-label": `${pitch.name}, 평균 IVB ${formatMovement(vertical.average)} ${movementUnitLabel()}, 평균 HB ${formatMovement(horizontal.average)} ${movementUnitLabel()}`,
    });
    const show = event => showTooltip(event, pitch, horizontal, vertical);
    ellipse.addEventListener("mouseenter", show);
    ellipse.addEventListener("mousemove", show);
    ellipse.addEventListener("focus", show);
    ellipse.addEventListener("mouseleave", hideTooltip);
    ellipse.addEventListener("blur", hideTooltip);
    svg.append(ellipse);
    svg.append(svgElement("circle", {cx: x(horizontal.average), cy: y(vertical.average), r: 5, fill: pitch.color, stroke: "#fff", "stroke-width": 1.8}));
  });
}

function renderFrequency() {
  const svg = document.querySelector("#frequency-chart");
  clearSvg(svg);
  const pitches = currentProfile.pitch_types;
  const sideTotals = currentProfile.player.batter_side_pitches || {L: 0, R: 0};
  const hasSplit = sideTotals.L + sideTotals.R > 0;
  const width = 400;
  const rowHeight = 50;
  const height = Math.max(270, 62 + pitches.length * rowHeight);
  const center = width / 2;
  const halfWidth = 134;
  svg.setAttribute("viewBox", `0 0 ${width} ${height}`);
  document.querySelector("#frequency-sample").textContent = hasSplit ? `L ${sideTotals.L.toLocaleString()} · R ${sideTotals.R.toLocaleString()}` : "전체 구사율";
  if (hasSplit) {
    svgText(svg, "vs LHH", {x: center - halfWidth, y: 19, "text-anchor": "middle", class: "chart-row-label"});
    svgText(svg, "vs RHH", {x: center + halfWidth, y: 19, "text-anchor": "middle", class: "chart-row-label"});
    for (const tick of [0, 50, 100]) {
      svgText(svg, `${tick}%`, {x: center - tick / 100 * halfWidth, y: 39, "text-anchor": "middle", class: "chart-axis-text"});
      if (tick) svgText(svg, `${tick}%`, {x: center + tick / 100 * halfWidth, y: 39, "text-anchor": "middle", class: "chart-axis-text"});
    }
    svg.append(svgElement("line", {x1: center, x2: center, y1: 45, y2: height - 16, class: "frequency-center"}));
    pitches.forEach((pitch, index) => {
      const y = 53 + index * rowHeight;
      const left = pitch.usage_by_batter?.L || {n: 0, usage: null};
      const right = pitch.usage_by_batter?.R || {n: 0, usage: null};
      const leftWidth = (left.usage || 0) / 100 * halfWidth;
      const rightWidth = (right.usage || 0) / 100 * halfWidth;
      svgText(svg, pitch.name, {x: center, y: y - 8, "text-anchor": "middle", class: "chart-row-label"});
      svg.append(svgElement("rect", {x: center - leftWidth, y, width: leftWidth, height: 22, rx: 2, fill: pitch.color, class: "frequency-bar"}));
      svg.append(svgElement("rect", {x: center, y, width: rightWidth, height: 22, rx: 2, fill: pitch.color, class: "frequency-bar"}));
      svgText(svg, `${fmt(left.usage)}%`, {x: Math.max(5, center - leftWidth - 5), y: y + 10, "text-anchor": "end", class: "frequency-label"});
      svgText(svg, `${left.n.toLocaleString()}구`, {x: Math.max(5, center - leftWidth - 5), y: y + 22, "text-anchor": "end", class: "frequency-count"});
      svgText(svg, `${fmt(right.usage)}%`, {x: Math.min(width - 5, center + rightWidth + 5), y: y + 10, class: "frequency-label"});
      svgText(svg, `${right.n.toLocaleString()}구`, {x: Math.min(width - 5, center + rightWidth + 5), y: y + 22, class: "frequency-count"});
    });
  } else {
    svgText(svg, "해당 연도는 타자 손 데이터가 없어 전체 구사율로 표시", {x: width / 2, y: 25, "text-anchor": "middle", class: "chart-row-sub"});
    const left = 80;
    const chartWidth = 270;
    for (const tick of [0, 25, 50, 75, 100]) {
      const tickX = left + tick / 100 * chartWidth;
      svg.append(svgElement("line", {x1: tickX, x2: tickX, y1: 43, y2: height - 18, class: "chart-grid-line"}));
      svgText(svg, `${tick}%`, {x: tickX, y: 39, "text-anchor": "middle", class: "chart-axis-text"});
    }
    pitches.forEach((pitch, index) => {
      const y = 51 + index * rowHeight;
      svgText(svg, pitch.name, {x: 5, y: y + 14, class: "chart-row-label"});
      svg.append(svgElement("rect", {x: left, y, width: pitch.usage / 100 * chartWidth, height: 22, rx: 2, fill: pitch.color, class: "frequency-bar"}));
      svgText(svg, `${fmt(pitch.usage)}%`, {x: Math.min(width - 4, left + pitch.usage / 100 * chartWidth + 5), y: y + 14, class: "frequency-label"});
    });
  }
}

function renderLegend() {
  document.querySelector("#pitch-legend").innerHTML = currentProfile.pitch_types.map(pitch => `<span><i style="background:${pitch.color}"></i>${escapeHtml(pitch.name)}</span>`).join("");
}

function showTooltip(event, pitch, horizontal, vertical) {
  const tooltip = document.querySelector("#tooltip");
  tooltip.innerHTML = `<strong>${escapeHtml(pitch.name)} · ${pitch.usage.toFixed(1)}%</strong>
    <p>구속 ${fmt(pitch.velocity_kmh?.average)} km/h · 75% ${fmt(pitch.velocity_kmh?.low_75)}–${fmt(pitch.velocity_kmh?.high_75)}</p>
    <p>IVB ${formatMovement(vertical.average)} ${movementUnitLabel()} · 75% ${formatMovement(vertical.low_75)}–${formatMovement(vertical.high_75)}</p>
    <p>HB ${formatMovement(horizontal.average)} ${movementUnitLabel()} · 75% ${formatMovement(horizontal.low_75)}–${formatMovement(horizontal.high_75)}</p>
    <p>보정 표본 ${pitch.movement_n.toLocaleString()} / ${pitch.movement_total_n.toLocaleString()}</p>`;
  tooltip.hidden = false;
  const panel = document.querySelector(".movement-card");
  const rect = panel.getBoundingClientRect();
  const clientX = event.clientX || rect.left + rect.width * .55;
  const clientY = event.clientY || rect.top + rect.height * .3;
  tooltip.style.left = `${Math.min(rect.width - 284, Math.max(10, clientX - rect.left + 12))}px`;
  tooltip.style.top = `${Math.max(52, clientY - rect.top + 12)}px`;
}

function hideTooltip() {
  document.querySelector("#tooltip").hidden = true;
}

function mixColor(from, to, ratio) {
  const parse = color => color.match(/\w\w/g).map(value => parseInt(value, 16));
  const first = parse(from);
  const second = parse(to);
  return `#${first.map((value, index) => Math.round(value + (second[index] - value) * ratio).toString(16).padStart(2, "0")).join("")}`;
}

function metricCell(value, percentile, qualified = true) {
  if (value == null) return '<td class="metric-cell"><span>—</span><small>자료 없음</small></td>';
  if (!qualified || percentile == null) return `<td class="metric-cell"><span>${fmt(value)}%</span><small>100구 미만</small></td>`;
  const endpoint = percentile >= 50 ? "#c83249" : "#3474b8";
  const strength = Math.abs(percentile - 50) / 50 * .9;
  const background = mixColor("#f7f8fa", endpoint, strength);
  const ink = percentile <= 12 || percentile >= 88 ? "#ffffff" : "#1d3148";
  return `<td class="metric-cell" style="--metric-bg:${background};--metric-ink:${ink}"><span>${fmt(value)}%</span><small>P${percentile}</small></td>`;
}

function renderTable() {
  const raw = modeSelect.value === "raw";
  const pitchRows = currentProfile.pitch_types.map(pitch => {
    const horizontal = movementHorizontal(raw ? pitch.raw_horizontal_break_in : pitch.horizontal_break_in);
    const vertical = raw ? pitch.raw_ivb_in : pitch.ivb_in;
    return `<tr>
      <td><span class="pitch-key"><i style="background:${pitch.color}"></i>${escapeHtml(pitch.name)}</span></td>
      <td>${pitch.n.toLocaleString()}</td><td>${pitch.usage.toFixed(1)}%</td><td>${fmt(pitch.velocity_kmh?.average)} km/h</td>
      <td>${formatMovement(vertical?.average)} ${movementUnitLabel()}</td><td>${formatMovement(horizontal?.average)} ${movementUnitLabel()}</td>
      <td>${fmt(pitch.release?.v_rel_ft?.average, 2)} ft</td><td>${fmt(pitch.release?.h_rel_ft?.average, 2)} ft</td>
      ${metricCell(pitch.rates?.zone_pct, pitch.percentiles?.zone_pct, pitch.percentile_qualified)}
      ${metricCell(pitch.rates?.chase_pct, pitch.percentiles?.chase_pct, pitch.percentile_qualified)}
      ${metricCell(pitch.rates?.swstr_pct, pitch.percentiles?.swstr_pct, pitch.percentile_qualified)}
    </tr>`;
  }).join("");
  const overall = currentProfile.overall || {};
  const overallRow = `<tr class="overall-row">
    <td>전체</td><td>${currentProfile.player.pitches.toLocaleString()}</td><td>100.0%</td><td>${fmt(overall.velocity_kmh?.average)} km/h</td>
    <td>—</td><td>—</td><td>${fmt(overall.release?.v_rel_ft?.average, 2)} ft</td><td>${fmt(overall.release?.h_rel_ft?.average, 2)} ft</td>
    ${metricCell(overall.rates?.zone_pct, overall.percentiles?.zone_pct, overall.percentile_qualified)}
    ${metricCell(overall.rates?.chase_pct, overall.percentiles?.chase_pct, overall.percentile_qualified)}
    ${metricCell(overall.rates?.swstr_pct, overall.percentiles?.swstr_pct, overall.percentile_qualified)}
  </tr>`;
  document.querySelector("#pitch-table").innerHTML = pitchRows + overallRow;
}

async function exportProfileImage() {
  if (!currentProfile || typeof html2canvas !== "function") {
    message.textContent = "이미지 저장 기능을 불러오지 못했습니다. 페이지를 새로고침해 주세요.";
    return;
  }
  exportButton.disabled = true;
  const originalLabel = exportButton.textContent;
  exportButton.textContent = "이미지 생성 중…";
  hideTooltip();
  try {
    await document.fonts?.ready;
    const canvas = await html2canvas(profileSection, {
      backgroundColor: "#edf2f7", scale: Math.max(2, window.devicePixelRatio || 1),
      useCORS: true, logging: false,
      ignoreElements: element => element === exportButton || element.id === "tooltip",
    });
    const playerName = currentProfile.player.name.replace(/[\\/:*?"<>|]+/g, "_");
    const link = document.createElement("a");
    link.download = `${currentProfile.season}_${playerName}_pitch-arsenal.png`;
    link.href = canvas.toDataURL("image/png");
    link.click();
  } catch {
    message.textContent = "프로필 이미지를 만들지 못했습니다. 잠시 후 다시 시도해 주세요.";
  } finally {
    exportButton.disabled = false;
    exportButton.textContent = originalLabel;
  }
}

fetch("../data/pitch_arsenal/index.json").then(response => response.json()).then(catalog => {
  yearSelect.innerHTML = catalog.seasons.map(year => `<option>${year}</option>`).join("");
  const requested = Number(new URLSearchParams(location.search).get("year"));
  if (catalog.seasons.includes(requested)) yearSelect.value = requested;
  return beginSeasonLoad(yearSelect.value);
}).catch(() => { message.textContent = "Pitch Arsenal 데이터를 불러오지 못했습니다."; });

yearSelect.addEventListener("change", () => {
  currentProfile = null;
  profileSection.hidden = true;
  history.replaceState(null, "", `?year=${yearSelect.value}`);
  beginSeasonLoad(yearSelect.value);
});
throwsSelect.addEventListener("change", handleSearch);
searchForm.addEventListener("submit", handleSearch);
modeSelect.addEventListener("change", () => { if (currentProfile) { renderMovement(); renderTable(); } });
movementViewButtons.forEach(button => button.addEventListener("click", () => {
  movementView = button.dataset.movementView;
  renderMovementViewControl();
  if (currentProfile) { renderMovement(); renderTable(); }
}));
movementUnitButtons.forEach(button => button.addEventListener("click", () => {
  movementUnit = button.dataset.movementUnit;
  renderMovementViewControl();
  if (currentProfile) { renderMovement(); renderTable(); }
}));
renderMovementViewControl();
exportButton.addEventListener("click", exportProfileImage);
