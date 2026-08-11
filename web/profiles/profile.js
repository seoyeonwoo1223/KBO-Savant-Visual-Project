const formatNumber = value => value == null ? "—" : Number(value).toFixed(2);
const formatSigned = value => {
  const number = Number(value);
  return `${number > 0 ? "+" : ""}${formatNumber(number)}`;
};
const profile = document.body.dataset.profile;
const REGION_STYLE = {
  Heart: { className: "heart", color: "#b16ab3" },
  Shadow: { className: "shadow", color: "#ec896f" },
  Chase: { className: "chase", color: "#ffe11b" },
  Waste: { className: "waste", color: "#a8a8a8" }
};
const runWidth = (value, maximum) => `${Math.max(2, Math.min(100, Math.abs(Number(value)) / maximum * 100))}%`;
const actionLine = (label, count, pct, type) => `
  <div class="action-line ${type}">
    <span class="label">${label}</span>
    <span class="action-bar"><i class="action-fill" style="--share:${Math.max(0, Math.min(100, Number(pct)))}%"></i></span>
    <span class="count">${Number(count).toLocaleString()} · ${formatNumber(pct)}%</span>
  </div>`;
const runBar = (value, maximum, type) => {
  const positive = Number(value) >= 0;
  return `<div class="run-bar">
    <i class="run-axis"></i>
    <i class="run-fill ${positive ? "positive" : "negative"}" style="--run-width:${runWidth(value, maximum)}"></i>
    <span class="run-value ${positive ? "positive" : "negative"}">${formatSigned(value)}</span>
  </div>`;
};
fetch(`../data/profiles/${profile}.json`)
  .then(response => {
    if (!response.ok) throw new Error("profile data could not be loaded");
    return response.json();
  })
  .then(data => {
    const { sample, overall, regions } = data;
    document.querySelector("#player-name").textContent = data.player.name;
    document.title = `${data.player.name} Swing/Take 프로필`;
    document.querySelector("#meta").textContent =
      `${data.season} 정규시즌 · ${sample.eligible_pitches.toLocaleString()}구 · ${(data.source.updated_at || "").slice(0, 10)} 기준${sample.meets_minimum ? "" : " · 표본 미달 (300구 기준)"}`;
    document.querySelector("#total-decision-run").textContent = formatSigned(overall.decision_run);
    document.querySelector("#score-detail").textContent = `100구당 ${formatSigned(overall.decision_run_per_100)} · 위치·카운트 중립`;
    document.querySelector("#pitch-total").textContent = `${overall.pitches.toLocaleString()} total pitches`;
    const maximumRun = Math.max(
      1,
      ...Object.values(regions).flatMap(region => [Math.abs(region.swing.decision_run), Math.abs(region.take.decision_run)])
    );
    document.querySelector("#regions").innerHTML = Object.entries(regions).map(([name, region]) => {
      const style = REGION_STYLE[name];
      const dotSize = Math.max(28, Math.min(58, 22 + Math.sqrt(region.share_pct) * 5));
      return `<article class="region-row">
        <div class="region-name ${style.className}">${name}</div>
        <div class="frequency">
          <i class="frequency-dot" style="--dot-size:${dotSize}px;--region-color:${style.color}"></i>
          <div class="frequency-copy"><b>${region.pitches.toLocaleString()}구</b>${formatNumber(region.share_pct)}% of pitches</div>
        </div>
        <div class="decision-split" style="--region-color:${style.color}">
          ${actionLine("Swing", region.swing.pitches, region.swing_pct, "swing")}
          ${actionLine("Take", region.take.pitches, region.take_pct, "take")}
        </div>
        <div class="run-bars">
          ${runBar(region.swing.decision_run, maximumRun, "swing")}
          ${runBar(region.take.decision_run, maximumRun, "take")}
        </div>
      </article>`;
    }).join("");
  })
  .catch(() => {
    document.querySelector("#meta").textContent = "프로필 데이터를 불러오지 못했습니다.";
  });
