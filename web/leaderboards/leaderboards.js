const $ = selector => document.querySelector(selector);
const thumbnailParams = new URLSearchParams(location.search);
const state = { catalog:null, payload:null, dataset:null, sortKey:null, direction:-1, page:1, pageSize:50 };
const labels = { batting:"타격 · 기본", "batting-advanced":"타격 · 확장", fielding:"수비", pitching:"투수 · 기본", "pitching-advanced":"투수 · 확장", "pitch-value":"투구 지표" };
const coloredMetrics = new Set(["WAR", "oWAR", "OAA"]);
const isColoredColumn = column => coloredMetrics.has(column.key) || /(?:^|\s)OAA$/.test(column.label);
const hiddenColumns = {
  batting: new Set(["whiff%", "chase%", "WPA", "RE24", "REW", "RC27"]),
  "batting-advanced": new Set(["WPA", "RE24", "RC27", "REW", "whiff%", "chase%"]),
};
const normalize = value => String(value ?? "").replace(/\s+/g, "").toLowerCase();
const isNumber = value => typeof value === "number" && Number.isFinite(value);

function formatValue(value, key) {
  if (value === null || value === undefined || value === "") return "—";
  if (!isNumber(value)) return String(value);
  if (["RK", "rk", "Year", "G", "GS", "PA", "AB", "BIP"].includes(key)) return Math.round(value).toLocaleString("ko-KR");
  if (Number.isInteger(value)) return value.toLocaleString("ko-KR");
  return value.toLocaleString("ko-KR", { maximumFractionDigits:3 });
}

// WAR diverging scale: positive=red, negative=blue. Same concept as pitch-arsenal.js's
// PERCENTILE_HIGH/LOW and zone.js's savantBands, each with its own endpoint values — not yet
// unified into one palette.
const WAR_POSITIVE_RGB = [200, 55, 65];
const WAR_NEGATIVE_RGB = [58, 102, 169];

function warColor(value, maximum) {
  const ratio = Math.min(1, Math.abs(value) / maximum);
  const target = value >= 0 ? WAR_POSITIVE_RGB : WAR_NEGATIVE_RGB;
  const channel = index => Math.round(255 + (target[index] - 255) * ratio);
  return `rgb(${channel(0)} ${channel(1)} ${channel(2)})`;
}

function warTextColor(value, maximum) {
  const rgb = warColor(value, maximum).match(/\d+/g).map(Number);
  const linear = channel => channel <= .04045 ? channel / 12.92 : ((channel + .055) / 1.055) ** 2.4;
  const luminance = channels => channels.map(channel => linear(channel / 255)).reduce((sum, channel, index) => sum + channel * [.2126, .7152, .0722][index], 0);
  const background = luminance(rgb);
  const dark = 0;
  return 1.05 / (background + .05) > (background + .05) / (dark + .05) ? "#fff" : "#000";
}

function pageRows(rows, page, pageSize) {
  const pages = Math.max(1, Math.ceil(rows.length / pageSize));
  const current = Math.min(pages, Math.max(1, page));
  const start = (current - 1) * pageSize;
  return { rows:rows.slice(start, start + pageSize), page:current, pages, start };
}

function cellMarkup(row, column, maximumWar) {
  const value = row[column.key];
  const classes = [value == null ? "null" : ""];
  let style = "";
  if (isColoredColumn(column) && maximumWar[column.key] && isNumber(value)) {
    classes.push("war-cell");
    style = ` style="--war-color:${warColor(value, maximumWar[column.key])};--war-text:${warTextColor(value, maximumWar[column.key])}"`;
  }
  const range = column.key === "oWAR" ? row.oWAR_range : null;
  const display = Array.isArray(range) && range[0] !== range[1]
    ? `${formatValue(range[0], column.key)}–${formatValue(range[1], column.key)}`
    : formatValue(value, column.key);
  return `<td class="${classes.join(" ").trim()}"${style}>${display}</td>`;
}

function filteredRows() {
  const query = normalize($("#player-search").value);
  const team = $("#team-select").value;
  const qualifiedOnly = $("#sample-select").value === "qualified";
  const rows = state.dataset.rows.filter(row => (!qualifiedOnly || row.qualified !== false) && (!query || normalize(row.Player).includes(query)) && (!team || row.Team === team));
  const key = state.sortKey;
  if (!key) return rows;
  return [...rows].sort((a,b) => {
    const av=a[key], bv=b[key];
    if (av == null) return 1;
    if (bv == null) return -1;
    return (isNumber(av) && isNumber(bv) ? av-bv : String(av).localeCompare(String(bv), "ko")) * state.direction;
  });
}

function render() {
  const columns = state.dataset.columns.filter(column => !["Year", "Sample"].includes(column.key) && !hiddenColumns[state.dataset.id]?.has(column.key));
  if (["batting", "batting-advanced"].includes(state.dataset.id)) {
    const wrc = columns.find(column => column.key === "wRC+");
    const war = columns.find(column => column.key === "oWAR") || columns.find(column => column.key === "WAR");
    if (wrc && war) {
      columns.splice(columns.indexOf(wrc), 1);
      columns.splice(columns.indexOf(war) + 1, 0, wrc);
    }
  }
  const limit = Number(thumbnailParams.get("limit"));
  const allRows = filteredRows();
  const pagination = pageRows(allRows, state.page, state.pageSize);
  state.page = pagination.page;
  const rows = thumbnailParams.get("thumb") === "1" && Number.isInteger(limit) && limit > 0 ? allRows.slice(0, limit) : pagination.rows;
  const maximumWar = Object.fromEntries(columns.filter(isColoredColumn).map(column => [
    column.key, Math.max(1, ...state.dataset.rows.filter(row => isNumber(row[column.key])).map(row => Math.abs(row[column.key])))
  ]));
  $("#table-title").textContent = `${state.payload.season} ${labels[state.dataset.id] || state.dataset.title}`;
  $("#row-count").textContent = `${allRows.length.toLocaleString("ko-KR")}명`;
  $("#leaderboard-head").innerHTML = `<tr>${columns.map(column => `<th data-key="${column.key}" aria-sort="${state.sortKey===column.key ? (state.direction===1?"ascending":"descending") : "none"}"><button type="button">${column.label}</button></th>`).join("")}</tr>`;
  $("#leaderboard-body").innerHTML = rows.map(row => `<tr>${columns.map(column => cellMarkup(row, column, maximumWar)).join("")}</tr>`).join("");
  $("#status").textContent = rows.length ? "" : "조건에 맞는 선수가 없습니다.";
  $("#page-range").textContent = allRows.length ? `${pagination.start + 1}–${pagination.start + rows.length} / ${allRows.length.toLocaleString("ko-KR")}명` : "0명";
  const pages = Array.from({length:pagination.pages}, (_, index) => index + 1);
  $("#page-buttons").innerHTML = `<button type="button" data-page="${state.page - 1}" aria-label="이전 페이지" ${state.page === 1 ? "disabled" : ""}>‹</button>${pages.map(page => `<button type="button" data-page="${page}" aria-label="${page}페이지" ${page === state.page ? 'aria-current="page"' : ""}>${page}</button>`).join("")}<button type="button" data-page="${state.page + 1}" aria-label="다음 페이지" ${state.page === pagination.pages ? "disabled" : ""}>›</button>`;
  $("#page-buttons").querySelectorAll("button").forEach(button => button.addEventListener("click", () => {
    state.page = Number(button.dataset.page);
    render();
    $("#page-buttons").querySelector('[aria-current="page"]').focus({preventScroll:true});
    $(".table-card").scrollIntoView({block:"start"});
  }));
  const target = $("[data-thumbnail-target]");
  if (target) target.dataset.thumbnailReady = "true";
  $("#leaderboard-head").querySelectorAll("th").forEach(th => th.addEventListener("click", () => {
    const key=th.dataset.key;
    state.direction = state.sortKey===key ? state.direction*-1 : (state.dataset.rows.some(row => isNumber(row[key])) ? -1 : 1);
    state.sortKey=key;
    state.page=1;
    render();
  }));
}

function selectDataset(id) {
  state.page=1;
  state.dataset = state.payload.datasets.find(item => item.id===id) || state.payload.datasets[0];
  const requestedSort = thumbnailParams.get("sort");
  state.sortKey = state.dataset.columns.find(column => column.key === requestedSort)?.key || ["WAR","oWAR","OAA","RK","rk"].find(key => state.dataset.columns.some(column => column.key === key)) || state.dataset.columns[0].key;
  state.direction = thumbnailParams.get("direction") === "asc" ? 1 : state.sortKey.toLowerCase()==="rk" ? 1 : -1;
  const teams=[...new Set(state.dataset.rows.map(row => row.Team).filter(Boolean))].sort((a,b)=>a.localeCompare(b,"ko"));
  $("#team-select").innerHTML=`<option value="">전체</option>${teams.map(team=>`<option>${team}</option>`).join("")}`;
  render();
}

async function loadSeason(season) {
  $("#status").textContent="데이터를 불러오는 중입니다.";
  const response=await fetch(`../data/leaderboards/${season}.json`, { cache:"no-store" });
  if(!response.ok) throw new Error("leaderboard data unavailable");
  state.payload=await response.json();
  const notes=Array.isArray(state.payload.notes) ? state.payload.notes : [];
  $("#source-note").textContent=notes.length
    ? `${state.payload.as_of || season} 기준 · ${notes.join(" ")}`
    : "제공된 시즌별 KBO 통계 자료를 기준으로 표시합니다. 빈 값은 —로 표기합니다.";
  $("#source-note").textContent += " WAR/oWAR/OAA는 0을 흰색, 양수를 빨강, 음수를 파랑으로 표시합니다.";
  $("#dataset-select").innerHTML=state.payload.datasets.map(item=>`<option value="${item.id}">${labels[item.id]||item.title}</option>`).join("");
  if (state.payload.datasets.some(item => item.id === thumbnailParams.get("dataset"))) $("#dataset-select").value = thumbnailParams.get("dataset");
  $("#sample-select").disabled = !state.payload.datasets.some(item => item.rows.some(row => typeof row.qualified === "boolean"));
  if ($("#sample-select").disabled) $("#sample-select").value = "all";
  selectDataset($("#dataset-select").value);
}

fetch("../data/leaderboards/index.json", { cache:"no-store" }).then(response=>response.json()).then(catalog=>{
  state.catalog=catalog;
  $("#season-select").innerHTML=catalog.seasons.map(season=>`<option>${season}</option>`).join("");
  if (catalog.seasons.includes(Number(thumbnailParams.get("season")))) $("#season-select").value = thumbnailParams.get("season");
  return loadSeason($("#season-select").value);
}).catch(()=>{$("#status").textContent="리더보드 데이터를 불러오지 못했습니다.";});

$("#season-select").addEventListener("change", event=>loadSeason(event.target.value));
$("#dataset-select").addEventListener("change", event=>selectDataset(event.target.value));
function resetPage() { state.page=1; render(); }
$("#player-search").addEventListener("input", resetPage);
$("#team-select").addEventListener("change", resetPage);
$("#sample-select").addEventListener("change", resetPage);
$("#page-size").addEventListener("change", event => { state.pageSize=Number(event.target.value); resetPage(); });
