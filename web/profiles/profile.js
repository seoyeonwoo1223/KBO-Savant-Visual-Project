const profile = document.body.dataset.profile || location.pathname.split("/").pop().replace(".html", "");
const number = value => Number(value || 0);
const fixed = value => number(value).toFixed(2);
const signed = value => `${number(value) > 0 ? "+" : ""}${fixed(value)}`;
const pct = value => `${fixed(value)}%`;
const gridOrder = [["0-2", "1-2", "2-2"], ["0-1", "1-1", "2-1"], ["0-0", "1-0", "2-0"]];
fetch(`../data/profiles/${profile}.json`)
  .then(response => {
    if (!response.ok) throw new Error("profile data could not be loaded");
    return response.json();
  })
  .then(data => {
    const { overall, sample, regions, zone_grid: zoneGrid } = data;
    document.querySelector("#player-name").textContent = data.player.name;
    document.title = `${data.player.name} Swing/Take 프로필`;
    document.querySelector("#meta").textContent =
      `${data.season} 정규시즌 · ${sample.eligible_pitches.toLocaleString()}구 · ${(data.source.updated_at || "").slice(0, 10)} 기준${sample.meets_minimum ? "" : " · 표본 미달 (300구 기준)"}`;
    const stats = [
      ["Total Decision Run", signed(overall.decision_run)],
      ["per 100 pitches", signed(overall.decision_run_per_100)],
      ["Pitches", overall.pitches.toLocaleString()],
      ["Swing%", fixed(overall.swing_pct)],
      ["Take%", fixed(overall.take_pct)]
    ];
    document.querySelector("#summary-stats").innerHTML = stats.map(([label, value]) =>
      `<div class="stat"><span class="stat-label">${label}</span><strong class="stat-value">${value}</strong></div>`
    ).join("");
    document.querySelector("#zone-grid").innerHTML = gridOrder.flat().map(key => {
      const cell = zoneGrid[key];
      return `<div class="grid-cell"><span class="grid-pitches">${cell ? cell.pitches : "—"}구</span><strong class="grid-run">${cell ? signed(cell.decision_run) : "—"}</strong><span class="grid-rate">RV/100 ${cell ? fixed(cell.decision_run_per_100) : "—"}</span></div>`;
    }).join("");
    document.querySelector("#regions").innerHTML = Object.entries(regions).map(([name, region]) =>
      `<article class="region-card"><h3>${name}</h3><p class="region-overview">${region.pitches.toLocaleString()}구 · ${pct(region.share_pct)}</p><p class="region-action">Swing ${region.swing.pitches}구 · ${pct(region.swing_pct)} <b>${signed(region.swing.decision_run)}</b></p><p class="region-action">Take ${region.take.pitches}구 · ${pct(region.take_pct)} <b>${signed(region.take.decision_run)}</b></p></article>`
    ).join("");
  })
  .catch(() => { document.querySelector("#meta").textContent = "프로필 데이터를 불러오지 못했습니다."; });
