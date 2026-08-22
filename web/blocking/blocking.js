const state = { data: null, player: null, difficulty: "all", pitch: "all" };
const $ = selector => document.querySelector(selector);

function fmt(value, digits = 1, plus = false) {
  const number = Number(value || 0);
  return `${plus && number > 0 ? "+" : ""}${number.toFixed(digits)}`;
}

function interpolateColor(from, to, amount) {
  const start = from.match(/\w\w/g).map(value => parseInt(value, 16));
  const end = to.match(/\w\w/g).map(value => parseInt(value, 16));
  return `#${start.map((value, index) => Math.round(value + (end[index] - value) * amount).toString(16).padStart(2, "0")).join("")}`;
}

function baaCellStyle(value, scale) {
  const ratio = Math.min(1, Math.abs(Number(value || 0)) / Math.max(scale, .01));
  const amount = Math.pow(ratio, .58);
  const endpoint = value < 0 ? "0b4f82" : value > 0 ? "e32635" : "f4f2ee";
  return `--baa-color:${interpolateColor("f7f6f3", endpoint, amount)};--baa-text:${amount > .56 ? "#fff" : "#1f2a33"}`;
}

function color(value, scale) {
  const amount = Math.max(-1, Math.min(1, value / Math.max(scale, .01)));
  if (amount < -.5) return "#174f83";
  if (amount < -.08) return "#74b5d2";
  if (amount <= .08) return "#e7e5dd";
  if (amount <= .5) return "#e78268";
  return "#8a001d";
}

function renderTable() {
  const qualified = $("#qualified-filter").value;
  const team = $("#team-filter").value;
  const query = $("#name-filter").value.trim();
  const scale = Math.max(1, ...state.data.players.map(player => Math.abs(Number(player.baa) || 0)));
  const players = state.data.players.filter(player =>
    (qualified === "all" || player.qualified) &&
    (team === "all" || player.team.split("/").includes(team)) &&
    (!query || player.catcher_name.includes(query))
  );
  $("#leaderboard-body").innerHTML = players.map((player, index) => `<tr data-player="${player.catcher_id}">
    <td>${index + 1}</td><td class="player">${player.catcher_name}</td><td>${player.team}</td>
    <td>${player.opportunities.toLocaleString()}</td><td>${fmt(player.blocking_runs, 1)}</td>
    <td class="baa" style="${baaCellStyle(player.baa, scale)}">${fmt(player.baa, 1, true)}</td><td>${player.actual_pbwp}</td><td>${fmt(player.estimated_pbwp, 1)}</td><td>${fmt(player.baa_per_game, 2, true)}</td>
    <td>${fmt(player.difficulty_pct.easy, 1)}%</td><td>${fmt(player.difficulty_pct.medium, 1)}%</td><td>${fmt(player.difficulty_pct.tough, 1)}%</td>
    <td>${fmt(player.difficulty_baa.easy, 1, true)}</td><td>${fmt(player.difficulty_baa.medium, 1, true)}</td><td>${fmt(player.difficulty_baa.tough, 1, true)}</td>
  </tr>`).join("");
  document.querySelectorAll("tbody tr").forEach(row => row.addEventListener("click", () => {
    state.player = row.dataset.player;
    $("#catcher-select").value = state.player;
    updatePitchOptions(); switchView("map"); renderMap();
  }));
}

// Front-facing pitch coordinates. The source grid is 6 inches wide by 9 inches high.
// Diagram reference: strike zone ±10 in / 18–42 in; Heart ±6.7 in / 22–38 in;
// Chase boundary ±13.3 in / 14–46 in; Waste begins outside that boundary.
const MAP = { left: 155, top: 42, width: 420, height: 504, xMin: -24, xMax: 24, zMin: 0, zMax: 60 };
const sx = inches => MAP.left + (inches - MAP.xMin) / (MAP.xMax - MAP.xMin) * MAP.width;
const sy = inches => MAP.top + (MAP.zMax - inches) / (MAP.zMax - MAP.zMin) * MAP.height;

function rectFor(x0, z0, x1, z1) {
  return { x: sx(x0), y: sy(z1), width: sx(x1) - sx(x0), height: sy(z0) - sy(z1) };
}

function gridCell(x, z) {
  // x bins: -18..18 inches, z bins: 0..54 inches.
  return rectFor(x * 6, z * 9, (x + 1) * 6, (z + 1) * 9);
}

function renderMap() {
  const player = state.data.players.find(item => item.catcher_id === state.player) || state.data.players[0];
  if (!player) return;
  state.player = player.catcher_id;
  const detail = state.data.details[player.catcher_id];
  const cells = detail.cells.filter(cell =>
    (state.difficulty === "all" || cell.difficulty === state.difficulty) &&
    (state.pitch === "all" || cell.pitch_type === state.pitch)
  );
  const combined = new Map();
  cells.forEach(cell => {
    const key = `${cell.x}:${cell.z}`;
    const current = combined.get(key) || { x: cell.x, z: cell.z, baa: 0, opportunities: 0 };
    current.baa += cell.baa;
    current.opportunities += cell.opportunities;
    combined.set(key, current);
  });
  const scale = Math.max(.25, ...[...combined.values()].map(cell => Math.abs(cell.baa)));
  const cellsSvg = [];
  for (let z = 0; z < 6; z += 1) for (let x = -3; x < 3; x += 1) {
    const cell = combined.get(`${x}:${z}`) || { baa: 0, opportunities: 0 };
    const box = gridCell(x, z);
    cellsSvg.push(`<g><rect x="${box.x}" y="${box.y}" width="${box.width}" height="${box.height}" fill="${cell.opportunities ? color(cell.baa, scale) : "#eee9df"}" fill-opacity="${cell.opportunities ? .94 : .48}" stroke="#fff" stroke-opacity=".42" stroke-width="1"/><text x="${box.x + box.width / 2}" y="${box.y + box.height / 2 - 2}" class="cell-value">${cell.opportunities ? fmt(cell.baa, 2, true) : "–"}</text><text x="${box.x + box.width / 2}" y="${box.y + box.height / 2 + 15}" class="cell-count">${cell.opportunities ? cell.opportunities : ""}</text><title>BAA ${fmt(cell.baa, 2, true)} · ${cell.opportunities} opportunities</title></g>`);
  }
  $("#map-cells").innerHTML = cellsSvg.join("");
  $("#player-summary").innerHTML = `<h2>${player.catcher_name} · ${player.team}</h2><div class="summary-grid">
    <div><strong>${player.opportunities.toLocaleString()}</strong><span>Block Opportunities</span></div>
    <div><strong>${fmt(player.baa, 1, true)}</strong><span>Blocks Above Avg</span></div>
    <div><strong>${player.actual_pbwp}</strong><span>Actual PB + WP</span></div>
    <div><strong>${fmt(player.estimated_pbwp, 1)}</strong><span>Estimated PB + WP</span></div></div>`;
}

function updatePitchOptions() {
  const detail = state.data?.details?.[state.player];
  const previous = state.pitch;
  const pitchTypes = detail?.pitch_types || [];
  $("#pitch-select").innerHTML = `<option value="all">전체</option>${pitchTypes.map(type => `<option value="${type}">${type}</option>`).join("")}`;
  state.pitch = pitchTypes.includes(previous) ? previous : "all";
  $("#pitch-select").value = state.pitch;
}

function switchView(name) {
  document.querySelectorAll(".tab").forEach(tab => { const active = tab.dataset.view === name; tab.classList.toggle("active", active); tab.setAttribute("aria-selected", active); });
  document.querySelectorAll(".view").forEach(view => { const active = view.id === `${name}-view`; view.classList.toggle("active", active); view.hidden = !active; });
}

async function init() {
  try {
    const response = await fetch("../data/blocking/2026/leaderboard.json");
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    state.data = await response.json();
    if (state.data.status === "unavailable" || !state.data.players.length) throw new Error("BAA 데이터가 아직 생성되지 않았습니다.");
    const teams = [...new Set(state.data.players.flatMap(player => player.team.split("/")))].filter(Boolean).sort();
    $("#team-filter").insertAdjacentHTML("beforeend", teams.map(team => `<option>${team}</option>`).join(""));
    $("#catcher-select").innerHTML = state.data.players.map(player => `<option value="${player.catcher_id}">${player.catcher_name} · ${player.team}</option>`).join("");
    state.player = state.data.players[0].catcher_id;
    updatePitchOptions();
    $("#method-note").textContent = `규정 표본 ${state.data.method.qualified_opportunities}회. Easy/Medium/Tough는 각각 블록 성공확률 95% 이상, 85–95%, 85% 미만입니다. 포수의 사전 위치 정보는 공개 원본에 없어 모델에 포함되지 않았습니다.`;
    renderTable(); renderMap();
  } catch (error) { $("#status").textContent = error.message; }
}

document.querySelectorAll(".tab").forEach(tab => tab.addEventListener("click", () => switchView(tab.dataset.view)));
[$("#qualified-filter"), $("#team-filter"), $("#name-filter")].forEach(input => input.addEventListener("input", renderTable));
$("#catcher-select").addEventListener("change", event => { state.player = event.target.value; updatePitchOptions(); renderMap(); });
$("#difficulty-select").addEventListener("change", event => { state.difficulty = event.target.value; renderMap(); });
$("#pitch-select").addEventListener("change", event => { state.pitch = event.target.value; renderMap(); });
init();
