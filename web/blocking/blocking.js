const state = { data: null, player: null, difficulty: "all", pitch: "all" };
const $ = selector => document.querySelector(selector);

function fmt(value, digits = 1, plus = false) {
  const number = Number(value || 0);
  return `${plus && number > 0 ? "+" : ""}${number.toFixed(digits)}`;
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
  const players = state.data.players.filter(player =>
    (qualified === "all" || player.qualified) &&
    (team === "all" || player.team.split("/").includes(team)) &&
    (!query || player.catcher_name.includes(query))
  );
  $("#leaderboard-body").innerHTML = players.map((player, index) => {
    const tone = player.baa > .05 ? "positive" : player.baa < -.05 ? "negative" : "neutral";
    return `<tr data-player="${player.catcher_id}">
      <td>${index + 1}</td><td class="player">${player.catcher_name}</td><td>${player.team}</td>
      <td>${player.opportunities.toLocaleString()}</td><td>${fmt(player.blocking_runs, 1)}</td>
      <td class="baa ${tone}">${fmt(player.baa, 1, true)}</td><td>${player.actual_pbwp}</td><td>${fmt(player.estimated_pbwp, 1)}</td><td>${fmt(player.baa_per_game, 2, true)}</td>
      <td>${fmt(player.difficulty_pct.easy, 1)}%</td><td>${fmt(player.difficulty_pct.medium, 1)}%</td><td>${fmt(player.difficulty_pct.tough, 1)}%</td>
      <td>${fmt(player.difficulty_baa.easy, 1, true)}</td><td>${fmt(player.difficulty_baa.medium, 1, true)}</td><td>${fmt(player.difficulty_baa.tough, 1, true)}</td>
    </tr>`;
  }).join("");
  document.querySelectorAll("tbody tr").forEach(row => row.addEventListener("click", () => {
    state.player = row.dataset.player;
    $("#catcher-select").value = state.player;
    updatePitchOptions(); switchView("map"); renderMap();
  }));
}

function polygonPoints(x, z) {
  const top = 86, bottom = 300, rows = 6, cols = 6;
  const y0 = bottom - z * (bottom - top) / rows, y1 = bottom - (z + 1) * (bottom - top) / rows;
  const bounds = y => { const t = (bottom - y) / (bottom - top); const half = 168 - t * 48; return [500 - half, 500 + half]; };
  const [l0, r0] = bounds(y0), [l1, r1] = bounds(y1);
  const a0 = l0 + (x + 3) * (r0 - l0) / cols, b0 = l0 + (x + 4) * (r0 - l0) / cols;
  const a1 = l1 + (x + 3) * (r1 - l1) / cols, b1 = l1 + (x + 4) * (r1 - l1) / cols;
  return `${a1},${y1} ${b1},${y1} ${b0},${y0} ${a0},${y0}`;
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
    const key = `${cell.x}:${cell.z}`, current = combined.get(key) || { x: cell.x, z: cell.z, baa: 0, opportunities: 0 };
    current.baa += cell.baa; current.opportunities += cell.opportunities; combined.set(key, current);
  });
  const scale = Math.max(.25, ...[...combined.values()].map(cell => Math.abs(cell.baa)));
  const polygons = [];
  for (let z = 0; z < 6; z += 1) for (let x = -3; x < 3; x += 1) {
    const cell = combined.get(`${x}:${z}`) || { baa: 0, opportunities: 0 };
    polygons.push(`<polygon points="${polygonPoints(x, z)}" fill="${cell.opportunities ? color(cell.baa, scale) : "#eee9df"}" fill-opacity="${cell.opportunities ? .96 : .55}" stroke="#173d24" stroke-width="3"><title>BAA ${fmt(cell.baa, 2, true)} · ${cell.opportunities} opportunities</title></polygon>`);
  }
  $("#map-cells").innerHTML = polygons.join("");
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
