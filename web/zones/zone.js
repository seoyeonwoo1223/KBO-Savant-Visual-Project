const state = { catalog: null, payload: null, league: null, leagueCache: new Map() };
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

// 각 칸의 리그 값을 흰색으로 두고, 선수가 더 높으면 빨강·낮으면 파랑 (차이 기준, docs/decisions/0013).
const divergingStops = [[65,108,176],[145,169,208],[245,245,245],[234,144,153],[223,36,51]];
const interpolate = (stops, ratio) => {
  const position = Math.max(0, Math.min(1, ratio)) * (stops.length - 1), index = Math.min(stops.length - 2, Math.floor(position)), t = position - index;
  return stops[index].map((channel, i) => Math.round(channel + (stops[index + 1][i] - channel) * t));
};
const diffSpan = config => config.percent ? 20 : 0.1;
const diffColor = (config, diff) => interpolate(divergingStops, (diff + diffSpan(config)) / (2 * diffSpan(config)));
const rgbText = rgb => `rgb(${rgb.join(",")})`;
// 배경이 진하면 흰 글자 (상대 휘도 기준).
const inkFor = rgb => (0.2126 * rgb[0] + 0.7152 * rgb[1] + 0.0722 * rgb[2]) < 140 ? "#fff" : "#111";
const tickLabel = (config, value) => config.percent ? `${Math.round(value)}%` : value.toFixed(3).replace(/^0/, "");
const diffLabel = (config, diff) => {
  if (diff == null) return "—";
  const sign = diff > 0 ? "+" : diff < 0 ? "−" : "";
  return config.percent ? `${sign}${Math.abs(diff).toFixed(1)}%p` : `${sign}${Math.abs(diff).toFixed(3).replace(/^0/, "")}`;
};
const diffTick = (config, diff) => {
  const sign = diff > 0 ? "+" : diff < 0 ? "−" : "";
  return config.percent ? (diff ? `${sign}${Math.abs(diff)}%p` : "0") : (diff ? `${sign}${Math.abs(diff).toFixed(3).replace(/^0/, "")}` : "0");
};

const layoutFor = withThrows => withThrows
  ? { pitcherThrows: 2, pitchType: 3, xBin: 4, zBin: 5, values: 6 }
  : { pitcherThrows: null, pitchType: 2, xBin: 3, zBin: 4, values: 5 };
const columns = () => layoutFor(state.payload?.schema_version >= 2);
const leagueColumns = () => layoutFor(state.league?.columns.includes("pitcher_throws"));

const selectedRows = (records = state.payload?.records, layout = columns()) => {
  if (!records) return [];
  const pitchType = $("#pitch-type").value;
  const pitcherThrows = $("#pitcher-throws").value;
  const single = $("#count-view").value === "single";
  const balls = $("#balls").value, strikes = $("#strikes").value;
  return records.filter(row =>
    (!pitcherThrows || layout.pitcherThrows === null || row[layout.pitcherThrows] === pitcherThrows) &&
    (!pitchType || row[layout.pitchType] === pitchType) &&
    (!single || balls === "" || String(row[0]) === balls) &&
    (!single || strikes === "" || String(row[1]) === strikes)
  );
};

const aggregate = (rows, layout = columns()) => {
  const offset = layout.values;
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
  const minimum = Number($("#minimum").value), layout = columns(), league = state.league ? leagueColumns() : null;
  const binCells = (records, cellLayout) => {
    const cells = new Map();
    records.forEach(row => {
      const key = `${row[cellLayout.xBin]}-${row[cellLayout.zBin]}`;
      const current = cells.get(key) || [];
      current.push(row); cells.set(key, current);
    });
    return cells;
  };
  // 최소 표본 미만(0구 포함)은 값 없이 회색 칸으로 둡니다. 0구 칸을 0%로 칠하지 않습니다.
  const cellValue = cell => cell[config.denominator] > 0 && cell[config.denominator] >= minimum
    ? metricValue(config, cell[config.numerator], cell[config.denominator]) : null;
  const cells = binCells(rows, layout), leagueCells = league ? binCells(selectedRows(state.league.records, league), league) : new Map();
  const grid = [];
  for (let z = 8; z >= 0; z--) for (let x = 0; x < 8; x++) {
    const cell = aggregate(cells.get(`${x}-${z}`) || [], layout);
    const leagueCell = league ? aggregate(leagueCells.get(`${x}-${z}`) || [], league) : null;
    const value = cellValue(cell), leagueValue = leagueCell ? cellValue(leagueCell) : null;
    grid.push({ value, leagueValue, diff: value != null && leagueValue != null ? value - leagueValue : null,
      numerator: cell[config.numerator], denominator: cell[config.denominator], pitches: cell.total, leaguePitches: leagueCell?.total || 0 });
  }
  const span = diffSpan(config);
  $("#legend").innerHTML = `<span class="legend-bar" style="background:linear-gradient(90deg,${divergingStops.map(rgbText).join(",")})"></span>`
    + `<span class="legend-ticks">${[-span, 0, span].map(tick => `<em>${diffTick(config, tick)}</em>`).join("")}</span>`;
  $("#zone-grid").innerHTML = grid.map(({ value, leagueValue, diff, numerator, denominator, pitches, leaguePitches }) => {
    const title = `${config.label} 선수 ${metricLabel(config, value)} (${numerator}/${denominator}) / 리그 ${metricLabel(config, leagueValue)} / 차이 ${diffLabel(config, diff)} · 투구 선수 ${pitches}구 · 리그 ${leaguePitches.toLocaleString()}구`;
    // 선수나 리그 어느 한쪽이라도 표본이 부족하면 비교할 수 없으므로 회색.
    if (diff == null) return `<div class="cell empty" title="${title}"></div>`;
    const rgb = diffColor(config, diff);
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
  const leagueKey = `${year}/${role}`;
  if (!state.leagueCache.has(leagueKey)) {
    state.leagueCache.set(leagueKey, fetch(`../data/zones/${year}/league/${role}.json`).then(r => r.ok ? r.json() : null).catch(() => null));
  }
  state.league = await state.leagueCache.get(leagueKey);
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
