const state = { catalog: null, payload: null };
const $ = selector => document.querySelector(selector);
const normalize = value => String(value || "").replace(/\s+/g, "").toLowerCase();
const pct = (numerator, denominator) => denominator ? 100 * numerator / denominator : null;
const fmt = value => value == null ? "—" : `${value.toFixed(1)}%`;
const sum = (rows, index) => rows.reduce((total, row) => total + Number(row[index] || 0), 0);
const metricConfig = {
  swing: { label: "Swing %", numerator: "swings", denominator: "total", maximum: 100, percent: true },
  whiff: { label: "Whiff %", numerator: "whiffs", denominator: "swings", maximum: 60, percent: true },
  avg: { label: "AVG", numerator: "hits", denominator: "atBats", maximum: .5, percent: false },
  contact: { label: "Contact %", numerator: "contacts", denominator: "swings", maximum: 100, percent: true },
  inplay: { label: "In-play %", numerator: "inplay", denominator: "total", maximum: 50, percent: true },
};
const metricValue = (config, numerator, denominator) => denominator ? (config.percent ? 100 * numerator / denominator : numerator / denominator) : null;
const metricLabel = (config, value) => value == null ? "—" : config.percent ? `${value.toFixed(1)}%` : value.toFixed(3).replace(/^0/, "");

const color = (value, maximum) => {
  if (value == null) return "#ededed";
  const ratio = Math.max(0, Math.min(1, value / maximum));
  const stops = [[42,91,158],[117,153,202],[221,231,244],[251,229,227],[231,126,128],[204,39,56]];
  const scaled = ratio * (stops.length - 1), left = Math.floor(scaled), right = Math.min(stops.length - 1, left + 1), mix = scaled - left;
  return `rgb(${stops[left].map((channel, index) => Math.round(channel + (stops[right][index] - channel) * mix)).join(",")})`;
};

const selectedRows = () => {
  if (!state.payload) return [];
  const pitchType = $("#pitch-type").value;
  const single = $("#count-view").value === "single";
  const balls = $("#balls").value, strikes = $("#strikes").value;
  return state.payload.records.filter(row =>
    (!pitchType || row[2] === pitchType) &&
    (!single || balls === "" || String(row[0]) === balls) &&
    (!single || strikes === "" || String(row[1]) === strikes)
  );
};

const aggregate = rows => ({
  total: sum(rows, 5), swings: sum(rows, 6), whiffs: sum(rows, 7), contacts: sum(rows, 8),
  inplay: sum(rows, 9), veloSum: sum(rows, 10), veloN: sum(rows, 11), zone: sum(rows, 12), pitches: sum(rows, 13),
  atBats: sum(rows, 14), hits: sum(rows, 15),
});

function render() {
  const rows = selectedRows(), totals = aggregate(rows), config = metricConfig[$("#metric").value];
  $("#summary").innerHTML = [
    ["Pitches", totals.total.toLocaleString()], ["Swing %", fmt(pct(totals.swings, totals.total))],
    ["Whiff %", fmt(pct(totals.whiffs, totals.swings))], ["Zone %", fmt(pct(totals.zone, totals.pitches))],
    ["AVG", totals.atBats ? (totals.hits / totals.atBats).toFixed(3).replace(/^0/, "") : "—"],
    ["Avg Velo", totals.veloN ? `${(totals.veloSum / totals.veloN).toFixed(1)} km/h` : "—"],
  ].map(([label, value]) => `<div><span>${label}</span><strong>${value}</strong></div>`).join("");
  $("#chart-title").textContent = config.label;
  $("#chart-subtitle").textContent = `${$("#pitch-type").value || "전체 구종"} · ${totals.total.toLocaleString()}구`;
  $("#legend").innerHTML = Array.from({length: 6}, (_, index) => `<i style="background:${color(index * config.maximum / 5, config.maximum)}"></i>`).join("");

  const minimum = Number($("#minimum").value), cells = new Map();
  rows.forEach(row => {
    const key = `${row[3]}-${row[4]}`;
    const current = cells.get(key) || [];
    current.push(row); cells.set(key, current);
  });
  const html = [];
  for (let z = 8; z >= 0; z--) for (let x = 0; x < 8; x++) {
    const cellRows = cells.get(`${x}-${z}`) || [], cell = aggregate(cellRows);
    const denominator = cell[config.denominator], numerator = cell[config.numerator];
    const value = denominator >= minimum ? metricValue(config, numerator, denominator) : null;
    const title = `${config.label}: ${metricLabel(config, value)} (${numerator}/${denominator})`;
    html.push(`<div class="cell ${value == null ? "empty" : ""}" style="background:${color(value, config.maximum)}" title="${title}">${value == null ? "" : config.percent ? `${Math.round(value)}%` : value.toFixed(3).replace(/^0/, "")}</div>`);
  }
  $("#zone-grid").innerHTML = html.join("");
  const coordinates = state.payload.coordinates, zone = state.payload.strike_zone;
  const left = 100 * (zone.left - coordinates.x_min) / (coordinates.x_max - coordinates.x_min);
  const width = 100 * (zone.right - zone.left) / (coordinates.x_max - coordinates.x_min);
  const top = 100 * (coordinates.z_max - zone.top) / (coordinates.z_max - coordinates.z_min);
  const height = 100 * (zone.top - zone.bottom) / (coordinates.z_max - coordinates.z_min);
  Object.assign($("#strike-zone").style, { left: `${left}%`, width: `${width}%`, top: `${top}%`, height: `${height}%` });

  const types = [...new Set(rows.map(row => row[2]))];
  const tableRows = types.map(type => {
    const values = aggregate(rows.filter(row => row[2] === type));
    return { type, ...values };
  }).sort((a, b) => b.total - a.total);
  $("#pitch-table").innerHTML = tableRows.map(row => `<tr><td>${row.type}</td><td>${fmt(pct(row.total, totals.total))}</td><td>${row.veloN ? (row.veloSum / row.veloN).toFixed(1) : "—"}</td><td>${fmt(pct(row.swings, row.total))}</td><td>${fmt(pct(row.whiffs, row.swings))}</td><td>${row.atBats ? (row.hits / row.atBats).toFixed(3).replace(/^0/, "") : "—"}</td><td>${fmt(pct(row.zone, row.pitches))}</td></tr>`).join("") || `<tr><td colspan="7">선택 조건의 투구가 없습니다.</td></tr>`;
}

async function openPlayer(player, year, role, replaceUrl = true) {
  const response = await fetch(`../data/zones/${year}/${role}/${player.file}`);
  if (!response.ok) throw new Error("profile could not be loaded");
  const shard = await response.json();
  state.payload = shard.players[String(player.id)];
  if (!state.payload) throw new Error("profile was not found in its shard");
  $("#profile").hidden = false;
  $("#player-name").textContent = state.payload.player.name;
  $("#profile-season").textContent = `${year} KBO · ${role === "batter" ? "BATTER" : "PITCHER"}`;
  $("#profile-meta").textContent = `${player.pitches.toLocaleString()}개 위치 표본 · ${state.payload.source}`;
  const types = [...new Set(state.payload.records.map(row => row[2]))].sort();
  $("#pitch-type").innerHTML = `<option value="">전체 구종</option>${types.map(type => `<option>${type}</option>`).join("")}`;
  if (replaceUrl) history.replaceState(null, "", `?player=${encodeURIComponent(player.id)}&year=${year}&role=${role}`);
  $("#matches").innerHTML = ""; $("#message").textContent = "";
  render();
}

function search(event) {
  event?.preventDefault();
  const year = $("#year").value, role = $("#role").value, query = normalize($("#query").value);
  const players = state.catalog.players[year]?.[role] || [];
  const matches = players.filter(player => normalize(player.name).includes(query));
  if (!query) { $("#message").textContent = "투수 이름을 입력해 주세요."; return; }
  const exact = matches.find(player => normalize(player.name) === query);
  if (exact || matches.length === 1) return openPlayer(exact || matches[0], year, role);
  $("#matches").innerHTML = matches.slice(0, 12).map(player => `<button type="button" data-id="${player.id}">${player.name}</button>`).join("");
  $("#matches").querySelectorAll("button").forEach(button => button.addEventListener("click", () => openPlayer(players.find(player => String(player.id) === button.dataset.id), year, role)));
  $("#message").textContent = matches.length ? `${matches.length}명 중 선택해 주세요.` : `${year} 원데이터에서 해당 투수를 찾지 못했습니다.`;
}

fetch("../data/zones/index.json").then(response => response.json()).then(async catalog => {
  state.catalog = catalog;
  $("#year").innerHTML = catalog.seasons.map(year => `<option>${year}</option>`).join("");
  const params = new URLSearchParams(location.search), year = params.get("year"), playerId = params.get("player"), role = params.get("role");
  if (year && catalog.seasons.includes(Number(year))) $("#year").value = year;
  if (["batter", "pitcher"].includes(role)) $("#role").value = role;
  if (playerId) {
    const player = (catalog.players[$("#year").value]?.[$("#role").value] || []).find(item => String(item.id) === playerId);
    if (player) await openPlayer(player, $("#year").value, $("#role").value, false);
  }
}).catch(() => { $("#message").textContent = "투수 프로필 목록을 불러오지 못했습니다."; });

$("#search-form").addEventListener("submit", search);
$("#year").addEventListener("change", () => { $("#profile").hidden = true; $("#matches").innerHTML = ""; $("#message").textContent = ""; });
$("#role").addEventListener("change", () => { $("#profile").hidden = true; $("#matches").innerHTML = ""; $("#message").textContent = ""; });
$("#count-view").addEventListener("change", event => {
  const enabled = event.target.value === "single";
  $("#balls").disabled = !enabled; $("#strikes").disabled = !enabled; render();
});
["#pitch-type", "#balls", "#strikes", "#metric", "#minimum"].forEach(selector => $(selector).addEventListener("change", render));
