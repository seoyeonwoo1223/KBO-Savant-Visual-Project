const formatNumber = value => value == null ? "—" : Number(value).toFixed(2);
const formatSigned = value => {
  const number = Number(value);
  return `${number > 0 ? "+" : ""}${formatNumber(number)}`;
};
const playerId = new URLSearchParams(window.location.search).get("player");
const REGION_STYLE = {
  Heart: { className: "heart", color: "#b16ab3" },
  Shadow: { className: "shadow", color: "#ec896f" },
  Chase: { className: "chase", color: "#ffe11b" },
  Waste: { className: "waste", color: "#a8a8a8" }
};
const runWidth = (value, maximum) => `${Math.max(1, Math.min(50, Math.abs(Number(value)) / maximum * 50))}%`;
const share = value => Math.max(0, Math.min(100, Number(value)));
const swingTakeSplit = (region, league) => `
  <div class="swing-take-split" aria-label="Swing ${formatNumber(region.swing_pct)}%, Take ${formatNumber(region.take_pct)}%">
    <div class="split-counts">
      <span>${region.swing.pitches.toLocaleString()}</span>
      <span>${region.take.pitches.toLocaleString()}</span>
    </div>
    <div class="split-player" style="--swing-share:${share(region.swing_pct)}%;--take-share:${share(region.take_pct)}%;--region-color:${region.color}">
      <div class="split-half swing"><i></i><span>${formatNumber(region.swing_pct)}%</span></div>
      <i class="split-axis"></i>
      <div class="split-half take"><i></i><span>${formatNumber(region.take_pct)}%</span></div>
    </div>
    ${league ? `<div class="split-league" aria-label="2026 KBO league average: Swing ${formatNumber(league.swing_pct)}%, Take ${formatNumber(league.take_pct)}%" style="--league-swing:${share(league.swing_pct)}%;--league-take:${share(league.take_pct)}%">
      <div class="split-half swing"><i></i><span>${formatNumber(league.swing_pct)}%</span></div>
      <i class="split-axis"></i>
      <div class="split-half take"><i></i><span>${formatNumber(league.take_pct)}%</span></div>
    </div>` : ""}
  </div>`;
const runBar = (value, maximum, label) => {
  const number = Number(value);
  const positive = number >= 0;
  return `<div class="run-bar" aria-label="${label} Run Value ${formatSigned(value)}">
    <i class="run-axis"></i>
    <i class="run-fill ${label.toLowerCase()} ${positive ? "right" : "left"}" style="--run-width:${runWidth(value, maximum)}"></i>
    <span class="run-value ${positive ? "right" : "left"}">${formatSigned(value)}</span>
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

const playerShard = /^\d/.test(playerId || "") ? playerId[0] : "other";
fetch(`../data/players/${playerShard}.json`)
  .then(response => {
    if (!response.ok) throw new Error("profile data could not be loaded");
    return response.json();
  })
  .then(shard => {
    const payload = shard.players[playerId];
    if (!payload) throw new Error("profile not found");
    const { overall, regions } = aggregateProfile(payload);
    const { season, source, league } = shard;
    const { player } = payload;
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
    const maximumRun = Math.max(
      1,
      ...Object.values(regions).flatMap(region => [Math.abs(region.swing.decision_run), Math.abs(region.take.decision_run)])
    );
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
  })
  .catch(() => {
    document.querySelector("#meta").textContent = "해당 선수의 ABS 프로필을 찾을 수 없습니다. 선수 검색으로 돌아가 주세요.";
  });
