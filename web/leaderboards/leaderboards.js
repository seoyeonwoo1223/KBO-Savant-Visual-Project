const $ = selector => document.querySelector(selector);
const state = { catalog:null, payload:null, dataset:null, sortKey:null, direction:-1 };
const labels = { batting:"타격 · 기본", "batting-advanced":"타격 · 확장", fielding:"수비", pitching:"투수 · 기본", "pitching-advanced":"투수 · 확장", "pitch-value":"구종 가치" };
const normalize = value => String(value ?? "").replace(/\s+/g, "").toLowerCase();
const isNumber = value => typeof value === "number" && Number.isFinite(value);

function formatValue(value, key) {
  if (value === null || value === undefined || value === "") return "—";
  if (!isNumber(value)) return String(value);
  if (["RK", "rk", "Year", "G", "GS", "PA", "AB", "BIP"].includes(key)) return Math.round(value).toLocaleString("ko-KR");
  if (Number.isInteger(value)) return value.toLocaleString("ko-KR");
  return value.toLocaleString("ko-KR", { maximumFractionDigits:3 });
}

function filteredRows() {
  const query = normalize($("#player-search").value);
  const team = $("#team-select").value;
  const rows = state.dataset.rows.filter(row => (!query || normalize(row.Player).includes(query)) && (!team || row.Team === team));
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
  const columns = state.dataset.columns.filter(column => column.key !== "Year");
  const rows = filteredRows();
  $("#table-title").textContent = `${state.payload.season} ${labels[state.dataset.id] || state.dataset.title}`;
  $("#row-count").textContent = `${rows.length.toLocaleString("ko-KR")}명`;
  $("#leaderboard-head").innerHTML = `<tr>${columns.map(column => `<th data-key="${column.key}" aria-sort="${state.sortKey===column.key ? (state.direction===1?"ascending":"descending") : "none"}"><button type="button">${column.label}</button></th>`).join("")}</tr>`;
  $("#leaderboard-body").innerHTML = rows.map(row => `<tr>${columns.map(column => `<td class="${row[column.key] == null ? "null" : ""}">${formatValue(row[column.key], column.key)}</td>`).join("")}</tr>`).join("");
  $("#status").textContent = rows.length ? "" : "조건에 맞는 선수가 없습니다.";
  $("#leaderboard-head").querySelectorAll("th").forEach(th => th.addEventListener("click", () => {
    const key=th.dataset.key;
    state.direction = state.sortKey===key ? state.direction*-1 : (state.dataset.rows.some(row => isNumber(row[key])) ? -1 : 1);
    state.sortKey=key;
    render();
  }));
}

function selectDataset(id) {
  state.dataset = state.payload.datasets.find(item => item.id===id) || state.payload.datasets[0];
  state.sortKey = state.dataset.columns.find(column => ["WAR","OAA","RK","rk"].includes(column.key))?.key || state.dataset.columns[0].key;
  state.direction = state.sortKey.toLowerCase()==="rk" ? 1 : -1;
  const teams=[...new Set(state.dataset.rows.map(row => row.Team).filter(Boolean))].sort((a,b)=>a.localeCompare(b,"ko"));
  $("#team-select").innerHTML=`<option value="">전체</option>${teams.map(team=>`<option>${team}</option>`).join("")}`;
  render();
}

async function loadSeason(season) {
  $("#status").textContent="데이터를 불러오는 중입니다.";
  const response=await fetch(`../data/leaderboards/${season}.json`);
  if(!response.ok) throw new Error("leaderboard data unavailable");
  state.payload=await response.json();
  $("#dataset-select").innerHTML=state.payload.datasets.map(item=>`<option value="${item.id}">${labels[item.id]||item.title}</option>`).join("");
  selectDataset($("#dataset-select").value);
}

fetch("../data/leaderboards/index.json").then(response=>response.json()).then(catalog=>{
  state.catalog=catalog;
  $("#season-select").innerHTML=catalog.seasons.map(season=>`<option>${season}</option>`).join("");
  return loadSeason(catalog.seasons[0]);
}).catch(()=>{$("#status").textContent="리더보드 데이터를 불러오지 못했습니다.";});

$("#season-select").addEventListener("change", event=>loadSeason(event.target.value));
$("#dataset-select").addEventListener("change", event=>selectDataset(event.target.value));
$("#player-search").addEventListener("input", render);
$("#team-select").addEventListener("change", render);
