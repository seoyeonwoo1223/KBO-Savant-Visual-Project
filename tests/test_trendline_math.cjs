const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const context = vm.createContext({});
vm.runInContext(fs.readFileSync('web/trendline/trendline-math.js','utf8'),context);
const M=vm.runInContext('TrendlineMath',context);
const fields=['pitches','velocity_sum','velocity_n','swing_n','swings','contact_n','contacts','location_n','in_zone','z_n','z_swings','o_n','o_swings','swstr_n','whiffs','pa','k','bb'];
M.setup(fields);
function counts(values) { return fields.map(k=>values[k]||0); }
function game(id,date,values,types={}) { return {game_id:id,date,counts:counts(values),types}; }
const games=[game('a','2025-12-30',{swing_n:2,swings:1,pa:2,k:1}),game('b','2026-04-01',{swing_n:10,swings:9,pa:10,k:2}),game('c','2026-04-03',{swing_n:100,swings:20,pa:20,k:3})];
assert.equal(M.value(M.sum(games.slice(1)),'swing').value,29/110*100);
assert.equal(M.value(M.zero(),'swing').value,null);
const bins=M.periodBins(games,'game','2025-01-01','2026-12-31',5);
assert.equal(bins[1].rows.length,1,'rolling resets at the season boundary');
assert.equal(bins[2].rows.length,2);
const league=M.leagueIndex([
 {date:'2026-03-31',counts:counts({swing_n:20,swings:20}),types:{}},
 {date:'2026-04-01',counts:counts({swing_n:100,swings:40}),types:{}},
 {date:'2026-04-02',counts:counts({swing_n:1000,swings:500}),types:{}},
 {date:'2026-04-03',counts:counts({swing_n:10,swings:5}),types:{}},
]);
const points=M.series(bins,'swing','all',league);
assert.equal(points[2].league.value,545/1110*100,'league pools every game in the player window dates');
assert.equal(points[1].league.value,40,'range endpoints are inclusive');
assert.equal(M.value(counts({pitches:20}),'usage',counts({pitches:100})).value,20);
const months=M.periodBins([games[1]],'month','2026-04-01','2026-06-30');
assert.equal(months.length,3);assert.equal(M.value(M.sum(months[1].rows),'swing').value,null,'missing month is a gap, not zero');
const axis=M.axis([143,149,150],'km/h');assert.equal(axis.min%axis.step,0);assert.equal(axis.max%axis.step,0);
console.log('PASS: Trendline weighted rates, league date windows, missing values, season reset, usage, tick bounds');
