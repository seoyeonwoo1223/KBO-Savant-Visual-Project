// ABS Zone Explorer 계산부. DOM·네트워크 없음 (tests/test_abs_zone_math.cjs).
const AbsZoneMath = (() => {
  const MIN_CELL_TAKES = 15;

  // zone_map_<season>.json의 filters["stance|count|group"] → Map(cell → {n, k, p})
  function decode(grid, key) {
    const cells = new Map();
    for (const row of (grid.filters[key] || [])) {
      cells.set(row[0], {n: row[1], k: row[2], p: row.length > 3 ? row[3] : null});
    }
    return cells;
  }

  function cellCenter(grid, cell) {
    const nz = grid.z_share.bins;
    const ix = Math.floor(cell / nz), iz = cell % nz;
    return {ix, iz, x: grid.x.start + (ix + .5) * grid.x.step, z: grid.z_share.start + (iz + .5) * grid.z_share.step};
  }

  // rate: 판정 스트라이크율. umpire: 실제 − 심판 모형 예상. vs2023: 실제 − 2023 같은 칸 실제.
  function cellValue(mode, cell, reference) {
    if (!cell || cell.n < MIN_CELL_TAKES) return null;
    const rate = cell.k / cell.n;
    if (mode === "rate") return rate;
    if (mode === "umpire") return cell.p == null ? null : rate - cell.p / cell.n;
    if (mode === "vs2023") {
      if (!reference || reference.n < MIN_CELL_TAKES) return null;
      return rate - reference.k / reference.n;
    }
    return null;
  }

  function totals(cells) {
    let n = 0, k = 0, p = 0, hasP = false;
    for (const c of cells.values()) {
      n += c.n; k += c.k;
      if (c.p != null) { p += c.p; hasP = true; }
    }
    return {n, rate: n ? k / n : null, expected: hasP && n ? p / n : null};
  }

  // 0..1 비율(t)을 세 색 사이에서 선형 보간. colors = [낮음, 중간, 높음] "#rrggbb"
  function mix(colors, t) {
    const clamp = Math.max(0, Math.min(1, t));
    const [a, b, u] = clamp < .5 ? [colors[0], colors[1], clamp * 2] : [colors[1], colors[2], (clamp - .5) * 2];
    const ch = (hex, i) => parseInt(hex.slice(1 + 2 * i, 3 + 2 * i), 16);
    const out = [0, 1, 2].map((i) => Math.round(ch(a, i) + (ch(b, i) - ch(a, i)) * u).toString(16).padStart(2, "0"));
    return `#${out.join("")}`;
  }

  function colorFor(mode, value, colors) {
    if (value == null) return null;
    return mode === "rate" ? mix(colors, value) : mix(colors, .5 + value / .6);
  }

  // 중간면 판정 경계 (cm, 신장 비율)
  function zoneOutline(rule, radius) {
    const half = rule.width_cm / 2;
    return {half, halfWithBall: half + radius, top: rule.top_ratio, bottom: rule.bottom_ratio};
  }

  function filterPlayers(players, {qualified, search, sort}) {
    const term = (search || "").trim();
    const rows = players.filter((p) => (!qualified || p.qualified) && (!term || p.name.includes(term)));
    return rows.sort((a, b) => (b[sort] - a[sort]) || (b.takes - a.takes));
  }

  function ciExcludesZero(low, high) {
    return (low > 0 && high > 0) || (low < 0 && high < 0);
  }

  return {MIN_CELL_TAKES, decode, cellCenter, cellValue, totals, mix, colorFor, zoneOutline, filterPlayers, ciExcludesZero};
})();
