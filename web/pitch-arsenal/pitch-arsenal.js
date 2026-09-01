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
const fmt = value => value == null ? "—" : Number(value).toFixed(1);
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

function toPitcherView(horizontal) {
  if (!horizontal) return horizontal;
  return {
    ...horizontal,
    average: -horizontal.average,
    low_75: -horizontal.high_75,
    high_75: -horizontal.low_75,
  };
}

function movementHorizontal(horizontal) {
  return movementView === "pitcher" ? toPitcherView(horizontal) : horizontal;
}

function movementUnitLabel() {
  return movementUnit === "cm" ? "cm" : "in.";
}

function formatMovement(value) {
  if (value == null) return "—";
  return fmt(value * (movementUnit === "cm" ? 2.54 : 1));
}

function renderMovementViewControl() {
  const isPitcherView = movementView === "pitcher";
  movementViewButtons.forEach(button => {
    const selected = button.dataset.movementView === movementView;
    button.setAttribute("aria-pressed", String(selected));
  });
  movementUnitButtons.forEach(button => {
    const selected = button.dataset.movementUnit === movementUnit;
    button.setAttribute("aria-pressed", String(selected));
  });
  document.querySelector("#movement-view-label").textContent = `${isPitcherView ? "투수" : "포수"} 시점 · ${movementUnitLabel()}`;
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
  if (!seasonIndex && seasonLoadPromise) {
    message.textContent = `${yearSelect.value} 선수 목록을 불러오는 중입니다.`;
    try {
      await seasonLoadPromise;
    } catch {
      return;
    }
  }
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
  matches.querySelectorAll("button").forEach(button => button.addEventListener("click", () => openPlayer(button.dataset.id)));
  message.textContent = found.length ? `검색 결과 ${found.length}명${found.length > 12 ? " · 상위 12명 표시" : ""}` : "조건에 맞는 투수를 찾지 못했습니다.";
}

function renderProfile() {
  const player = currentProfile.player;
  profileSection.hidden = false;
  document.querySelector("#profile-season").textContent = `${currentProfile.season} PITCH ARSENAL`;
  document.querySelector("#player-name").textContent = player.name;
  document.querySelector("#profile-meta").textContent = `${player.throws || "?"}HP · ${player.pitches.toLocaleString()} pitches`;
  const adjusted = currentProfile.pitch_types.reduce((sum, pitch) => sum + pitch.movement_n, 0);
  const total = currentProfile.pitch_types.reduce((sum, pitch) => sum + pitch.movement_total_n, 0);
  document.querySelector("#coverage").textContent = `무브먼트 보정 표본 ${adjusted.toLocaleString()} / ${total.toLocaleString()} (${total ? (adjusted / total * 100).toFixed(1) : "0.0"}%)`;
  renderFrequency();
  renderVelocity();
  renderMovement();
  renderTable();
  profileSection.scrollIntoView({behavior: "smooth", block: "start"});
}

function renderFrequency() {
  document.querySelector("#frequency").innerHTML = currentProfile.pitch_types.map(pitch => `
    <div class="metric-row">
      <div class="metric-label"><strong>${escapeHtml(pitch.name)}</strong><span>${pitch.n.toLocaleString()}구</span></div>
      <div class="bar-track"><span class="bar-value">${pitch.usage.toFixed(1)}%</span><div class="bar" style="width:${Math.min(100, pitch.usage * 2)}%;background:${pitch.color}"></div></div>
    </div>`).join("");
}

function renderVelocity() {
  const summaries = currentProfile.pitch_types.map(pitch => pitch.velocity_kmh).filter(Boolean);
  const min = Math.floor(Math.min(...summaries.map(item => item.low_75), 100) / 5) * 5;
  const max = Math.ceil(Math.max(...summaries.map(item => item.high_75), 155) / 5) * 5;
  const position = value => (value - min) / (max - min) * 100;
  document.querySelector("#velocity").innerHTML = currentProfile.pitch_types.map(pitch => {
    const speed = pitch.velocity_kmh;
    if (!speed) return `<div class="metric-row"><div class="metric-label"><strong>${escapeHtml(pitch.name)}</strong></div><div>—</div></div>`;
    return `<div class="metric-row">
      <div class="metric-label"><strong>${escapeHtml(pitch.name)}</strong><span>${fmt(speed.low_75)}–${fmt(speed.high_75)}</span></div>
      <div class="speed-track"><span class="speed-value" style="left:${position(speed.average)}%">${fmt(speed.average)} km/h</span><span class="speed-range" style="left:${position(speed.low_75)}%;width:${position(speed.high_75)-position(speed.low_75)}%;background:${pitch.color}"></span><span class="speed-dot" style="left:${position(speed.average)}%;background:${pitch.color}"></span></div>
    </div>`;
  }).join("");
}

function renderMovement() {
  const svg = document.querySelector("#movement-chart");
  svg.querySelectorAll(":scope > :not(title):not(desc)").forEach(element => element.remove());
  // The plotting area is square, so every inch has identical x/y length on screen.
  const bounds = {left: 70, right: 620, top: 50, bottom: 600, xMin: -30, xMax: 30, yMin: -30, yMax: 30};
  const x = value => bounds.left + (value - bounds.xMin) / (bounds.xMax - bounds.xMin) * (bounds.right - bounds.left);
  const y = value => bounds.bottom - (value - bounds.yMin) / (bounds.yMax - bounds.yMin) * (bounds.bottom - bounds.top);
  for (let value = -30; value <= 30; value += 6) {
    svg.append(svgElement("line", {x1: x(value), x2: x(value), y1: bounds.top, y2: bounds.bottom, class: value === 0 ? "zero-line" : "grid-line"}));
    const label = svgElement("text", {x: x(value), y: 622, "text-anchor": "middle", class: "axis-text"}); label.textContent = formatMovement(value); svg.append(label);
  }
  for (let value = -30; value <= 30; value += 6) {
    svg.append(svgElement("line", {x1: bounds.left, x2: bounds.right, y1: y(value), y2: y(value), class: value === 0 ? "zero-line" : "grid-line"}));
    const label = svgElement("text", {x: 58, y: y(value) + 4, "text-anchor": "end", class: "axis-text"}); label.textContent = formatMovement(value); svg.append(label);
  }
  const direction = movementView === "pitcher" ? "1B < MOVES TOWARD > 3B" : "3B < MOVES TOWARD > 1B";
  const directionTitle = svgElement("text", {x: 345, y: 28, "text-anchor": "middle", class: "axis-direction"}); directionTitle.textContent = direction; svg.append(directionTitle);
  const xTitle = svgElement("text", {x: 345, y: 665, "text-anchor": "middle", class: "axis-title"}); xTitle.textContent = "Horizontal Break"; svg.append(xTitle);
  const yTitle = svgElement("text", {x: 17, y: 325, transform: "rotate(-90 17 325)", "text-anchor": "middle", class: "axis-title"}); yTitle.textContent = "Induced Vertical Break"; svg.append(yTitle);

  const raw = modeSelect.value === "raw";
  const visualOpacity = usage => {
    const scale = Math.min(1, Math.max(0, Number(usage) || 0) / 10);
    // A quadratic curve keeps rare pitches clearly subordinate until they approach 10%.
    const emphasis = scale * scale;
    return {
      fill: 0.02 + 0.25 * emphasis,
      stroke: 0.25 + 0.75 * emphasis,
      dot: 0.22 + 0.78 * emphasis,
    };
  };
  currentProfile.pitch_types.forEach(pitch => {
    const horizontal = movementHorizontal(raw ? pitch.raw_horizontal_break_in : pitch.horizontal_break_in);
    const vertical = raw ? pitch.raw_ivb_in : pitch.ivb_in;
    if (!horizontal || !vertical) return;
    const opacity = visualOpacity(pitch.usage);
    const ellipse = svgElement("ellipse", {
      cx: x(horizontal.average), cy: y(vertical.average),
      rx: Math.max(8, Math.abs(x(horizontal.high_75) - x(horizontal.low_75)) / 2),
      ry: Math.max(8, Math.abs(y(vertical.high_75) - y(vertical.low_75)) / 2),
      fill: pitch.color, "fill-opacity": opacity.fill, stroke: pitch.color, "stroke-opacity": opacity.stroke, "stroke-width": 4, class: "movement-ellipse", tabindex: 0,
      "aria-label": `${pitch.name}, 평균 IVB ${formatMovement(vertical.average)}${movementUnitLabel()}, 평균 HB ${formatMovement(horizontal.average)}${movementUnitLabel()}`,
    });
    const dot = svgElement("circle", {cx: x(horizontal.average), cy: y(vertical.average), r: 3.5, fill: pitch.color, "fill-opacity": opacity.dot});
    const show = event => showTooltip(event, pitch, horizontal, vertical);
    ellipse.addEventListener("mouseenter", show); ellipse.addEventListener("mousemove", show); ellipse.addEventListener("focus", show);
    ellipse.addEventListener("mouseleave", hideTooltip); ellipse.addEventListener("blur", hideTooltip);
    svg.append(ellipse, dot);
  });
}

function showTooltip(event, pitch, horizontal, vertical) {
  const tooltip = document.querySelector("#tooltip");
  tooltip.innerHTML = `<strong>${escapeHtml(pitch.name)}: ${pitch.usage.toFixed(1)}%</strong>
    <p>구속 ${fmt(pitch.velocity_kmh?.average)} km/h · 75% ${fmt(pitch.velocity_kmh?.low_75)}–${fmt(pitch.velocity_kmh?.high_75)}</p>
    <p>IVB ${formatMovement(vertical.average)} ${movementUnitLabel()} · 75% ${formatMovement(vertical.low_75)}–${formatMovement(vertical.high_75)}</p>
    <p>HB ${formatMovement(horizontal.average)} ${movementUnitLabel()} · 75% ${formatMovement(horizontal.low_75)}–${formatMovement(horizontal.high_75)}</p>
    <p>무브먼트 표본 ${pitch.movement_n.toLocaleString()} / ${pitch.movement_total_n.toLocaleString()}</p>`;
  tooltip.hidden = false;
  const panel = document.querySelector(".movement-panel");
  const rect = panel.getBoundingClientRect();
  const clientX = event.clientX || rect.left + rect.width * .55;
  const clientY = event.clientY || rect.top + rect.height * .3;
  tooltip.style.left = `${Math.min(rect.width - 295, Math.max(10, clientX - rect.left + 12))}px`;
  tooltip.style.top = `${Math.max(48, clientY - rect.top + 12)}px`;
}

function hideTooltip() { document.querySelector("#tooltip").hidden = true; }

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
      backgroundColor: "#f4f4f2",
      scale: Math.max(2, window.devicePixelRatio || 1),
      useCORS: true,
      logging: false,
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

function renderTable() {
  const raw = modeSelect.value === "raw";
  document.querySelector("#pitch-table").innerHTML = currentProfile.pitch_types.map(pitch => {
    const horizontal = movementHorizontal(raw ? pitch.raw_horizontal_break_in : pitch.horizontal_break_in);
    const vertical = raw ? pitch.raw_ivb_in : pitch.ivb_in;
    return `<tr><td><span class="pitch-key"><i style="background:${pitch.color}"></i>${escapeHtml(pitch.name)}</span></td><td>${pitch.n.toLocaleString()}</td><td>${pitch.usage.toFixed(1)}%</td><td>${fmt(pitch.velocity_kmh?.average)} km/h</td><td>${formatMovement(vertical?.average)} ${movementUnitLabel()}</td><td>${formatMovement(horizontal?.average)} ${movementUnitLabel()}</td></tr>`;
  }).join("");
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
