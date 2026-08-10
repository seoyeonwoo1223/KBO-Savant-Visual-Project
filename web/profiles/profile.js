const fmt = value => value == null ? "—" : Number(value).toFixed(2);
const profile = document.body.dataset.profile;
const cell = (label, value) => `<div class="cell"><span>${label}</span><strong>${fmt(value)}</strong></div>`;
fetch(`../data/profiles/${profile}.json`).then(response => response.json()).then(data => {
  const sample = data.sample;
  document.querySelector("#meta").textContent = `${data.season} 정규시즌 · ${sample.eligible_pitches.toLocaleString()}구 · ${(data.source.updated_at || "입력 Excel").slice(0, 10)} 기준${sample.meets_minimum ? "" : " · 표본 100구 미만"}`;
  document.querySelector("#overall").innerHTML = cell("Total Decision Run", data.overall.decision_run) + cell("per 100 pitches", data.overall.decision_run_per_100) + cell("Pitches", data.overall.pitches);
  document.querySelector("#regions").innerHTML = Object.entries(data.regions).map(([name, value]) => `<article><h3>${name}</h3><p>${value.pitches.toLocaleString()}구 · ${value.share_pct}%</p><div class="split"><span>Swing <b>${fmt(value.swing.decision_run)}</b></span><span>Take <b>${fmt(value.take.decision_run)}</b></span></div></article>`).join("");
  const grid = document.querySelector("#zone-grid");
  for (let y = 2; y >= 0; y--) for (let x = 0; x < 3; x++) {
    const value = data.zone_grid[`${x}-${y}`]; const node = document.createElement("div");
    node.className = "grid-cell"; node.innerHTML = `<small>${value ? value.pitches : 0}구</small><strong>${value ? fmt(value.decision_run_per_100) : "—"}</strong><small>RV/100</small>`; grid.append(node);
  }
});