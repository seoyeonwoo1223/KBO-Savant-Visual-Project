const state = { catalog: null, payload: null };
const $ = selector => document.querySelector(selector);
const thumbnailParams = new URLSearchParams(location.search);
const normalize = value => String(value || "").replace(/\s+/g, "").toLowerCase();
const pct = (numerator, denominator) => denominator ? 100 * numerator / denominator : null;
const fmt = value => value == null ? "—" : `${value.toFixed(1)}%`;
const sum = (rows, index) => rows.reduce((total, row) => total + Number(row[index] || 0), 0);
const metricConfig = {
  swing: { label: "Swing %", numerator: "swings", denominator: "total", maximum: 100, percent: true },
  whiff: { label: "Whiff %", numerator: "whiffs", denominator: "swings", maximum: 100, percent: true },
  avg: { label: "AVG", numerator: "hits", denominator: "atBats", maximum: 1, percent: false },
  contact: { label: "Contact %", numerator: "contacts", denominator: "swings", maximum: 100, percent: true },
  inplay: { label: "In-play %", numerator: "inplay", denominator: "total", maximum: 100, percent: true },
};
const metricValue = (config, numerator, denominator) => denominator ? (config.percent ? 100 * numerator / denominator : numerator / denominator) : null;
const metricLabel = (config, value) => value == null ? "—" : config.percent ? `${value.toFixed(1)}%` : value.toFixed(3).replace(/^0/, "");

const savantBands = [[65,108,176],[101,134,190],[145,169,208],[184,200,224],[217,225,237],[245,245,245],[246,214,216],[240,182,187],[234,144,153],[223,36,51]];
// 비율 지표(Swing·Whiff·Contact·In-play %)는 낮음→높음 한 방향 색, AVG는 리그 수준(.250)을 가운데로 둔 양방향 색.
// 비율 지표의 상한은 보이는 칸의 최댓값을 10%p 단위로 올림해서, 존 밖 0% 칸이 화면을 덮지 않게 합니다.
const sequentialStops = [[245,245,245],[246,214,216],[240,182,187],[234,144,153],[223,36,51]];
const AVG_CENTER = 0.25, AVG_SPAN = 0.25;
const interpolate = (stops, ratio) => {
  const position = Math.max(0, Math.min(1, ratio)) * (stops.length - 1), index = Math.min(stops.length - 2, Math.floor(position)), t = position - index;
  return stops[index].map((channel, i) => Math.round(channel + (stops[index + 1][i] - channel) * t));
};
const colorScale = (config, values) => {
  if (!config.percent) {
    return { rgb: value => savantBands[Math.min(9, Math.max(0, Math.floor((value - (AVG_CENTER - AVG_SPAN)) / (2 * AVG_SPAN) * 10)))],
      ticks: [AVG_CENTER - AVG_SPAN, AVG_CENTER, AVG_CENTER + AVG_SPAN], stops: savantBands };
  }
  const top = Math.max(10, Math.ceil(Math.max(0, ...values) / 10) * 10);
  return { rgb: value => interpolate(sequentialStops, value / top), ticks: [0, top / 2, top], stops: sequentialStops };
};
const rgbText = rgb => `rgb(${rgb.join(",")})`;
// 배경이 진하면 흰 글자 (상대 휘도 기준).
const inkFor = rgb => (0.2126 * rgb[0] + 0.7152 * rgb[1] + 0.0722 * rgb[2]) < 140 ? "#fff" : "#111";
const tickLabel = (config, value) => config.percent ? `${Math.round(value)}%` : value.toFixed(3).replace(/^0/, "");

const columns = () => state.payload?.schema_version >= 2
  ? { pitcherThrows: 2, pitchType: 3, xBin: 4, zBin: 5, values: 6 }
  : { pitcherThrows: null, pitchType: 2, xBin: 3, zBin: 4, values: 5 };

const selectedRows = () => {
  if (!state.payload) return [];
  const pitchType = $("#pitch-type").value;
  const pitcherThrows = $("#pitcher-throws").value;
  const single = $("#count-view").value === "single";
  const balls = $("#balls").value, strikes = $("#strikes").value;
  const layout = columns();
  return state.payload.records.filter(row =>
    (!pitcherThrows || layout.pitcherThrows === null || row[layout.pitcherThrows] === pitcherThrows) &&
    (!pitchType || row[layout.pitchType] === pitchType) &&
    (!single || balls === "" || String(row[0]) === balls) &&
    (!single || strikes === "" || String(row[1]) === strikes)
  );
};

const aggregate = rows => {
  const offset = columns().values;
  return {
    total: sum(rows, offset), swings: sum(rows, offset + 1), whiffs: sum(rows, offset + 2), contacts: sum(rows, offset + 3),
    inplay: sum(rows, offset + 4), veloSum: sum(rows, offset + 5), veloN: sum(rows, offset + 6), zone: sum(rows, offset + 7), pitches: sum(rows, offset + 8),
    atBats: sum(rows, offset + 9), hits: sum(rows, offset + 10),
  };
};

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
  const minimum = Number($("#minimum").value), cells = new Map(), layout = columns();
  rows.forEach(row => {
    const key = `${row[layout.xBin]}-${row[layout.zBin]}`;
    const current = cells.get(key) || [];
    current.push(row); cells.set(key, current);
  });
  const grid = [];
  for (let z = 8; z >= 0; z--) for (let x = 0; x < 8; x++) {
    const cell = aggregate(cells.get(`${x}-${z}`) || []);
    const denominator = cell[config.denominator], numerator = cell[config.numerator];
    // 최소 표본 미만(0구 포함)은 값 없이 회색 칸으로 둡니다. 0구 칸을 0%로 칠하지 않습니다.
    const value = denominator > 0 && denominator >= minimum ? metricValue(config, numerator, denominator) : null;
    grid.push({ value, numerator, denominator, pitches: cell.total });
  }
  const scale = colorScale(config, grid.filter(cell => cell.value != null).map(cell => cell.value));
  $("#legend").innerHTML = `<span class="legend-bar" style="background:linear-gradient(90deg,${scale.stops.map(rgbText).join(",")})"></span>`
    + `<span class="legend-ticks">${scale.ticks.map(tick => `<em>${tickLabel(config, tick)}</em>`).join("")}</span>`;
  $("#zone-grid").innerHTML = grid.map(({ value, numerator, denominator, pitches }) => {
    const title = `${config.label}: ${metricLabel(config, value)} (${numerator}/${denominator}) · 표본 ${pitches}구`;
    if (value == null) return `<div class="cell empty" title="${title}"></div>`;
    const rgb = scale.rgb(value);
    return `<div class="cell" style="background:${rgbText(rgb)};color:${inkFor(rgb)}" title="${title}">${tickLabel(config, value)}</div>`;
  }).join("");
  const coordinates = state.payload.coordinates;
  const zone = state.payload.strike_zone || { left: -1.0, right: 1.0, bottom: 1.5, top: 3.5 };
  const left = 100 * (zone.left - coordinates.x_min) / (coordinates.x_max - coordinates.x_min);
  const width = 100 * (zone.right - zone.left) / (coordinates.x_max - coordinates.x_min);
  const top = 100 * (coordinates.z_max - zone.top) / (coordinates.z_max - coordinates.z_min);
  const height = 100 * (zone.top - zone.bottom) / (coordinates.z_max - coordinates.z_min);
  Object.assign($("#strike-zone").style, { left: `${left}%`, width: `${width}%`, top: `${top}%`, height: `${height}%` });
  const plate = state.payload.home_plate || { width_ft: 17 / 12, gap_ft: 1 / 3 };
  const horizontalRange = coordinates.x_max - coordinates.x_min;
  Object.assign($("#plate").style, {
    width: `${100 * plate.width_ft / horizontalRange}%`,
    marginTop: `${100 * plate.gap_ft / horizontalRange}%`,
  });
  $("#x-ticks").innerHTML = Array.from({length: 9}, (_, index) => (coordinates.x_min + index * coordinates.bucket_size).toFixed(1)).map(value => `<span>${value}</span>`).join("");
  $("#y-ticks").innerHTML = Array.from({length: 10}, (_, index) => (coordinates.z_max - index * coordinates.bucket_size).toFixed(1)).map(value => `<span>${value}</span>`).join("");

  const types = [...new Set(rows.map(row => row[layout.pitchType]))];
  const tableRows = types.map(type => {
    const values = aggregate(rows.filter(row => row[layout.pitchType] === type));
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
  const layout = columns();
  const types = [...new Set(state.payload.records.map(row => row[layout.pitchType]))].sort();
  $("#pitch-type").innerHTML = `<option value="">전체 구종</option>${types.map(type => `<option>${type}</option>`).join("")}`;
  $("#pitcher-throws").value = "";
  $("#pitcher-throws").disabled = layout.pitcherThrows === null;
  ["pitcherThrows", "pitchType", "countView", "balls", "strikes", "metric", "minimum"].forEach(name => {
    const control = $("#" + name.replace(/[A-Z]/g, letter => "-" + letter.toLowerCase()));
    if (control && thumbnailParams.has(name) && [...control.options].some(option => option.value === thumbnailParams.get(name))) control.value = thumbnailParams.get(name);
  });
  if (replaceUrl) history.replaceState(null, "", `?player=${encodeURIComponent(player.id)}&year=${year}&role=${role}`);
  $("#matches").innerHTML = ""; $("#message").textContent = "";
  render();
  const target = $("[data-thumbnail-target]");
  if (target) {
    $("#thumbnail-context").textContent = `${state.payload.player.name} · ${$("#metric").selectedOptions[0].textContent}`;
    target.dataset.thumbnailReady = "true";
  }
}

function search(event) {
  event?.preventDefault();
  const year = $("#year").value, role = $("#role").value, query = normalize($("#query").value);
  const players = state.catalog.players[year]?.[role] || [];
  const matches = players.filter(player => normalize(player.name).includes(query));
  const roleLabel = role === "batter" ? "타자" : "투수";
  if (!query) { $("#message").textContent = `${roleLabel} 이름을 입력해 주세요.`; return; }
  const exact = matches.find(player => normalize(player.name) === query);
  if (exact || matches.length === 1) return openPlayer(exact || matches[0], year, role);
  $("#matches").innerHTML = matches.slice(0, 12).map(player => `<button type="button" data-id="${player.id}">${player.name}</button>`).join("");
  $("#matches").querySelectorAll("button").forEach(button => button.addEventListener("click", () => openPlayer(players.find(player => String(player.id) === button.dataset.id), year, role)));
  $("#message").textContent = matches.length ? `${matches.length}명 중 선택해 주세요.` : `${year} 원데이터에서 해당 ${roleLabel}를 찾지 못했습니다.`;
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
}).catch(() => { $("#message").textContent = "선수 프로필 목록을 불러오지 못했습니다."; });

$("#search-form").addEventListener("submit", search);
$("#year").addEventListener("change", () => { $("#profile").hidden = true; $("#matches").innerHTML = ""; $("#message").textContent = ""; });
$("#role").addEventListener("change", () => { $("#profile").hidden = true; $("#matches").innerHTML = ""; $("#message").textContent = ""; });
$("#count-view").addEventListener("change", event => {
  const enabled = event.target.value === "single";
  $("#balls").disabled = !enabled; $("#strikes").disabled = !enabled; render();
});
["#pitcher-throws", "#pitch-type", "#balls", "#strikes", "#metric", "#minimum"].forEach(selector => $(selector).addEventListener("change", render));
