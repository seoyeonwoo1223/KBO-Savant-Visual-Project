const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const context = vm.createContext({});
vm.runInContext(fs.readFileSync('web/abs-zone/abs-zone-math.js', 'utf8'), context);
const M = vm.runInContext('AbsZoneMath', context);

const grid = {x: {start: -60, step: 6, bins: 20}, z_share: {start: .1, step: .03, bins: 22},
  filters: {'all|all|all': [[0, 20, 5, 4.5], [23, 10, 9, 8.0], [45, 40, 30, 20.0]]}};
const cells = M.decode(grid, 'all|all|all');
assert.equal(cells.size, 3);
assert.equal(JSON.stringify(M.cellCenter(grid, 23)), JSON.stringify({ix: 1, iz: 1, x: -51, z: .1 + 1.5 * .03}));

// 칸당 15구 미만은 값이 없습니다.
assert.equal(M.cellValue('rate', cells.get(23)), null);
assert.equal(M.cellValue('rate', cells.get(0)), .25);
assert.equal(M.cellValue('umpire', cells.get(45)), 30 / 40 - 20 / 40);
assert.equal(M.cellValue('vs2023', cells.get(45), {n: 50, k: 25}), .25);
assert.equal(M.cellValue('vs2023', cells.get(45), {n: 5, k: 5}), null);
assert.equal(M.cellValue('umpire', {n: 30, k: 3, p: null}), null);

const t = M.totals(cells);
assert.equal(t.n, 70);
assert.equal(t.rate, 44 / 70);
assert.equal(t.expected, 32.5 / 70);
assert.equal(M.totals(M.decode({filters: {}}, 'x')).rate, null);

const colors = ['#0f4471', '#f6f6f6', '#fc3c3c'];
assert.equal(M.mix(colors, 0), '#0f4471');
assert.equal(M.mix(colors, .5), '#f6f6f6');
assert.equal(M.mix(colors, 1), '#fc3c3c');
assert.equal(M.mix(colors, 2), '#fc3c3c', '범위 밖은 끝 색으로 고정');
assert.equal(M.colorFor('umpire', 0, colors), '#f6f6f6', '차이 0은 중립색');
assert.equal(M.colorFor('rate', null, colors), null);

const outline = M.zoneOutline({width_cm: 47.18, top_ratio: .5575, bottom_ratio: .2704}, 3.62);
assert.equal(outline.half, 23.59);
assert.ok(Math.abs(outline.halfWithBall - 27.21) < 1e-9);

const players = [
  {name: '가', qualified: true, relative_rv: 3, takes: 900},
  {name: '나', qualified: false, relative_rv: 9, takes: 120},
  {name: '다', qualified: true, relative_rv: -2, takes: 800},
];
assert.equal(M.filterPlayers(players, {qualified: true, search: '', sort: 'relative_rv'}).map((p) => p.name).join(), '가,다');
assert.equal(M.filterPlayers(players, {qualified: false, search: '나', sort: 'relative_rv'}).map((p) => p.name).join(), '나');
assert.equal(M.ciExcludesZero(.1, 2), true);
assert.equal(M.ciExcludesZero(-1, 2), false);
assert.equal(M.ciExcludesZero(-3, -1), true);
console.log('abs-zone math ok');
