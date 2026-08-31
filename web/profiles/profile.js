const formatNumber = value => value == null ? "—" : Number(value).toFixed(2);
const formatSigned = value => {
  const number = Number(value);
  return `${number > 0 ? "+" : ""}${formatNumber(number)}`;
};
const escapeHtml = value => String(value).replace(/[&<>"']/g, character => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[character]));
const params = new URLSearchParams(window.location.search);
const playerId = params.get("player");
const profileYearSelect = document.querySelector("#profile-year");
const exportButton = document.querySelector("#export-profile");
const profileExportArea = document.querySelector("#profile-export-area");
const seasonParam = params.get("year") || "2026";
const comparePlayerParam = params.get("comparePlayer");
const compareYearParam = params.get("compareYear");
const SEASONS = ["2022", "2023", "2024", "2025", "2026"];
const REGION_STYLE = {
  Heart: { className: "heart", color: "#b16ab3" },
  Shadow: { className: "shadow", color: "#ec896f" },
  Chase: { className: "chase", color: "#ffe11b" },
  Waste: { className: "waste", color: "#a8a8a8" }
};
const runWidth = (value, maximum) => `${Math.max(1, Math.min(50, Math.abs(Number(value)) / maximum * 50))}%`;
const share = value => Math.max(0, Math.min(100, Number(value)));
const playerShard = id => /^\d/.test(id || "") ? id[0] : "other";
const profileCache = new Map();

const swingTakeSplit = (region, league) => `
  <div class="swing-take-split" aria-label="Swing ${formatNumber(region.swing_pct)}%, Take ${formatNumber(region.take_pct)}%">
    <div class="split-counts">
      <span>${region.swing.pitches.toLocaleString()}</span>
      <span>${region.take.pitches.toLocaleString()}</span>
    </div>
    <div class="split-player" style="--swing-share:${share(region.swing_pct)}%;--take-share:${share(region.take_pct)}%;--region-color:${region.color}">
      <div class="split-half swing"><span>${formatNumber(region.swing_pct)}%</span><i></i></div>
      <i class="split-axis"></i>
      <div class="split-half take"><i></i><span>${formatNumber(region.take_pct)}%</span></div>
    </div>
    ${league ? `<div class="split-league" aria-label="League average: Swing ${formatNumber(league.swing_pct)}%, Take ${formatNumber(league.take_pct)}%" style="--league-swing:${share(league.swing_pct)}%;--league-take:${share(league.take_pct)}%">
      <div class="split-half swing"><span>${formatNumber(league.swing_pct)}%</span><i></i></div>
      <i class="split-axis"></i>
      <div class="split-half take"><i></i><span>${formatNumber(league.take_pct)}%</span></div>
    </div>` : ""}
  </div>`;
const runBar = (value, maximum, label) => {
  const number = Number(value);
  const positive = number >= 0;
  return `<div class="run-bar" aria-label="${label} Run Value ${formatSigned(value)}">
    <div class="run-side left">${positive ? "" : `<span class="run-value">${formatSigned(value)}</span><i class="run-fill ${label.toLowerCase()}" style="--run-width:${runWidth(value, maximum)}"></i>`}</div>
    <i class="run-axis"></i>
    <div class="run-side right">${positive ? `<i class="run-fill ${label.toLowerCase()}" style="--run-width:${runWidth(value, maximum)}"></i><span class="run-value">${formatSigned(value)}</span>` : ""}</div>
  </div>`;
};
const aggregateProfile = payload => {
  const groups = Object.fromEntries(Object.keys(REGION_STYLE).map(name => [name, { Swing: [], Take: [] }]));
  payload.pitches.forEach(pitch => groups[pitch.region][pitch.action].push(Number(pitch.run_value)));
  const aggregate = values => ({
    pitches: values.length,
    decision_run: values.reduce((sum, value) => sum + value, 0),
    decision_run_per_100: values.length ? 100 * values.reduce((sum, value) => sum + value, 0) / values.length : null
  });
  const regions = {};
  Object.entries(groups).forEach(([name, actions]) => {
    const swing = aggregate(actions.Swing);
    const take = aggregate(actions.Take);
    const pitches = swing.pitches + take.pitches;
    regions[name] = {
      pitches,
      share_pct: payload.pitches.length ? 100 * pitches / payload.pitches.length : 0,
      swing_pct: pitches ? 100 * swing.pitches / pitches : 0,
      take_pct: pitches ? 100 * take.pitches / pitches : 0,
      swing,
      take
    };
  });
  return { regions, overall: aggregate(payload.pitches.map(pitch => Number(pitch.run_value))) };
};
const loadProfile = (season, id) => {
  const key = `${season}:${id}`;
  if (!profileCache.has(key)) {
    profileCache.set(key, fetch(`../data/swing_take/${season}/players/${playerShard(id)}.json`)
      .then(response => {
        if (!response.ok) throw new Error("profile data could not be loaded");
        return response.json();
      })
      .then(shard => {
        const payload = shard.players[id];
        if (!payload) throw new Error("profile not found");
        return { shard, payload, ...aggregateProfile(payload) };
      }));
  }
  return profileCache.get(key);
};

const renderMainProfile = ({ shard, payload, overall, regions }) => {
  const { season, source, league } = shard;
  const { player } = payload;
  document.querySelector("#profile-season").textContent = `Visual Baseball ABS · ${season} KBO`;
  const meetsMinimum = payload.pitches.length >= payload.minimum_pitches;
  document.querySelector("#player-name").textContent = player.name;
  document.title = `${player.name} Swing/Take 프로필`;
  const bats = document.querySelector("#bats");
  const hasKnownBats = player.bats && String(player.bats).toLowerCase() !== "unknown";
  bats.textContent = hasKnownBats ? `Bats: ${player.bats}` : "";
  bats.hidden = !hasKnownBats;
  document.querySelector("#meta").textContent =
    `${season} 정규시즌 · ${payload.pitches.length.toLocaleString()}구 · ${(source.updated_at || "").slice(0, 10)} 기준${meetsMinimum ? "" : ` · 표본 미달 (${payload.minimum_pitches}구 기준)`}`;
  document.querySelector("#total-run-value").textContent = formatSigned(overall.decision_run);
  document.querySelector("#score-detail").textContent = `100구당 ${formatSigned(overall.decision_run_per_100)} · 위치·카운트 중립`;
  document.querySelector("#pitch-total").textContent = `${overall.pitches.toLocaleString()} total pitches`;
  const maximumRun = Math.max(1, ...Object.values(regions).flatMap(region => [Math.abs(region.swing.decision_run), Math.abs(region.take.decision_run)]));
  Object.entries(regions).forEach(([name, region]) => {
    const value = Number(region.swing.decision_run || 0) + Number(region.take.decision_run || 0);
    const target = document.querySelector(`#zone-run-${name.toLowerCase()}`);
    if (!target) return;
    target.textContent = `${formatSigned(value)} Runs`;
    target.parentElement.setAttribute("aria-label", `${name} Run Value ${formatSigned(value)}`);
  });
  const leaguePitchTotal = Object.values(league?.regions || {}).reduce((sum, region) => sum + Number(region.pitches || 0), 0);
  document.querySelector("#regions").innerHTML = Object.entries(regions).map(([name, region]) => {
    const style = REGION_STYLE[name];
    const dotSize = Math.max(28, Math.min(58, 22 + Math.sqrt(region.share_pct) * 5));
    const styledRegion = { ...region, color: style.color };
    const leagueRegion = league?.regions?.[name];
    const leagueShare = leaguePitchTotal && leagueRegion ? 100 * Number(leagueRegion.pitches) / leaguePitchTotal : null;
    return `<article class="region-row">
      <div class="region-name ${style.className}">${name}</div>
      <div class="frequency">
        <i class="frequency-dot" style="--dot-size:${dotSize}px;--region-color:${style.color}"></i>
        <div class="frequency-copy"><b>${region.pitches.toLocaleString()}구</b>${formatNumber(region.share_pct)}%${leagueShare == null ? "" : ` (${formatNumber(leagueShare)}%)`}</div>
      </div>
      ${swingTakeSplit(styledRegion, leagueRegion)}
      <div class="run-bars">
        ${runBar(region.swing.decision_run, maximumRun, "Swing")}
        ${runBar(region.take.decision_run, maximumRun, "Take")}
      </div>
    </article>`;
  }).join("");
  const swingTotal = Object.values(regions).reduce((sum, region) => sum + Number(region.swing.decision_run), 0);
  const takeTotal = Object.values(regions).reduce((sum, region) => sum + Number(region.take.decision_run), 0);
  document.querySelector("#run-total").innerHTML = `<span>${formatSigned(swingTotal)} Swing Run</span><strong>${formatSigned(takeTotal)} Take Run</strong>`;
};

async function exportProfileImage() {
  if (typeof html2canvas !== "function" || !playerId) {
    document.querySelector("#meta").textContent = "이미지 저장 기능을 불러오지 못했습니다. 페이지를 새로고침해 주세요.";
    return;
  }
  exportButton.disabled = true;
  const originalLabel = exportButton.textContent;
  exportButton.textContent = "이미지 생성 중…";
  try {
    await document.fonts?.ready;
    const canvas = await html2canvas(profileExportArea, {
      backgroundColor: "#f4f4f2",
      scale: Math.max(2, window.devicePixelRatio || 1),
      useCORS: true,
      logging: false,
      ignoreElements: element => element === exportButton || element.classList?.contains("zone-guide"),
    });
    const playerName = document.querySelector("#player-name").textContent.replace(/[\\/:*?"<>|]+/g, "_");
    const link = document.createElement("a");
    link.download = `${seasonParam}_${playerName}_swing-take.png`;
    link.href = canvas.toDataURL("image/png");
    link.click();
  } catch {
    document.querySelector("#meta").textContent = "프로필 이미지를 만들지 못했습니다. 잠시 후 다시 시도해 주세요.";
  } finally {
    exportButton.disabled = false;
    exportButton.textContent = originalLabel;
  }
}

const comparisonElements = {
  a: { player: document.querySelector("#compare-a-player"), list: document.querySelector("#compare-a-players"), year: document.querySelector("#compare-a-year") },
  b: { player: document.querySelector("#compare-b-player"), list: document.querySelector("#compare-b-players"), year: document.querySelector("#compare-b-year") },
  results: document.querySelector("#comparison-results")
};
const indexPromise = Promise.all(SEASONS.map(season => fetch(`../data/swing_take/${season}/index.json`)
  .then(response => {
    if (!response.ok) throw new Error("comparison index could not be loaded");
    return response.json();
  })))
  .then(indexes => Object.fromEntries(indexes.map(index => [String(index.season), index.players])));

const populateYears = (select, selectedYear) => {
  select.innerHTML = SEASONS.map(year => `<option value="${year}"${year === String(selectedYear) ? " selected" : ""}>${year}</option>`).join("");
};
const populatePlayers = (input, list, players, preferredId) => {
  const sorted = [...players].sort((a, b) => a.name.localeCompare(b.name, "ko"));
  const selected = sorted.find(player => player.id === preferredId) || sorted[0];
  list.innerHTML = sorted.map(player => `<option value="${escapeHtml(player.name)}"></option>`).join("");
  input.value = selected ? selected.name : "";
  input.dataset.playerId = selected ? selected.id : "";
};
const populateSlotPlayers = (slot, indexes, preferredId) => {
  const { player, year } = comparisonElements[slot];
  populatePlayers(player, comparisonElements[slot].list, indexes[year.value] || [], preferredId || player.dataset.playerId);
};
const comparisonCard = ({ payload, overall, regions }, season) => {
  const player = payload.player;
  const rows = Object.entries(regions).map(([name, region]) => {
    const value = Number(region.swing.decision_run) + Number(region.take.decision_run);
    return `<tr class="${REGION_STYLE[name].className}">
      <td>${name}</td><td>${formatSigned(region.swing.decision_run)}</td><td>${formatSigned(region.take.decision_run)}</td><td>${formatSigned(value)}</td>
    </tr>`;
  }).join("");
  return `<article class="compare-profile">
    <header><h3>${escapeHtml(player.name)} <span>${season}</span></h3><p class="compare-total">${formatSigned(overall.decision_run)}</p></header>
    <p class="compare-meta">${overall.pitches.toLocaleString()}구 · 100구당 ${formatSigned(overall.decision_run_per_100)} Run Value</p>
    <table class="compare-table"><thead><tr><th>구획</th><th>Swing</th><th>Take</th><th>합계</th></tr></thead><tbody>${rows}</tbody></table>
  </article>`;
};
let comparisonIndexes = null;
const selectedComparisonId = slot => { const control = comparisonElements[slot]; const player = (comparisonIndexes?.[control.year.value] || []).find(item => item.name === control.player.value); return player ? player.id : control.player.dataset.playerId; };
const renderComparison = async () => {
  const a = comparisonElements.a;
  const b = comparisonElements.b;
  comparisonElements.results.innerHTML = '<p class="comparison-status">비교 프로필을 불러오는 중입니다.</p>';
  try {
    const [profileA, profileB] = await Promise.all([loadProfile(a.year.value, selectedComparisonId("a")), loadProfile(b.year.value, selectedComparisonId("b"))]);
    comparisonElements.results.innerHTML = comparisonCard(profileA, a.year.value) + comparisonCard(profileB, b.year.value);
  } catch {
    comparisonElements.results.innerHTML = '<p class="comparison-status">선택한 선수·시즌의 비교 프로필을 찾을 수 없습니다.</p>';
  }
};
const updateComparisonQuery = () => {
  const url = new URL(window.location.href);
  url.searchParams.set("comparePlayer", selectedComparisonId("b"));
  url.searchParams.set("compareYear", comparisonElements.b.year.value);
  window.history.replaceState(null, "", url);
};
const initializeComparison = async () => {
  try {
    const indexes = await indexPromise;
    comparisonIndexes = indexes;
    const defaultCompareYear = compareYearParam && indexes[compareYearParam] ? compareYearParam : (SEASONS.includes(String(Number(seasonParam) - 1)) ? String(Number(seasonParam) - 1) : seasonParam);
    populateYears(comparisonElements.a.year, seasonParam);
    populateYears(comparisonElements.b.year, defaultCompareYear);
    populateSlotPlayers("a", indexes, playerId);
    populateSlotPlayers("b", indexes, comparePlayerParam || playerId);
    ["a", "b"].forEach(slot => comparisonElements[slot].year.addEventListener("change", () => populateSlotPlayers(slot, indexes)));
    document.querySelector("#compare-button").addEventListener("click", () => {
      updateComparisonQuery();
      renderComparison();
    });
    renderComparison();
  } catch {
    comparisonElements.results.innerHTML = '<p class="comparison-status">비교용 선수 목록을 불러올 수 없습니다.</p>';
  }
};

profileYearSelect.innerHTML = SEASONS.map(year => `<option value="${year}"${year === seasonParam ? " selected" : ""}>${year}</option>`).join("");
profileYearSelect.addEventListener("change", () => { const url = new URL(window.location.href); url.searchParams.set("year", profileYearSelect.value); window.location.href = url; });

loadProfile(seasonParam, playerId)
  .then(renderMainProfile)
  .catch(() => {
    document.querySelector("#meta").textContent = "해당 선수의 ABS 프로필을 찾을 수 없습니다. 선수 검색으로 돌아가 주세요.";
  });
initializeComparison();
exportButton.addEventListener("click", exportProfileImage);