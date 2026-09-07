const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const source = fs.readFileSync(path.join(__dirname, '../web/pitch-arsenal/pitch-arsenal.js'), 'utf8');
const charts = {};
const context = vm.createContext({
  document: {querySelector: id => charts[id] ||= {children: [], setAttribute(k, v) { this[k] = v; }, append(e) { this.children.push(e); }}},
  clearSvg: svg => { svg.children = []; },
  svgElement: (tag, attributes) => ({tag, ...attributes}),
  svgText: (svg, text, attributes) => svg.append({tag: 'text', text, ...attributes}),
  fmt: value => value == null ? '—' : value.toFixed(1),
});
vm.runInContext(source.slice(source.indexOf('function renderVelocity()'), source.indexOf('function movementPoint(')) + source.slice(source.indexOf('function renderFrequency()'), source.indexOf('function showTooltip(')), context);
let previousBarHeight = Infinity;
for (const count of [1, 2, 4, 5, 6, 9]) {
  for (const split of [true, false]) {
    context.currentProfile = {
      player: {batter_side_pitches: {L: split ? 100 : 0, R: 0}},
      pitch_types: Array.from({length: count}, () => ({name: 'Pitch', color: '#c00', usage: 100 / count,
        velocity_kmh: {average: 145, low_75: 140, high_75: 150},
        velocity_distribution_kmh: {start: 140, step: 5, counts: [1, 4, 1]},
        usage_by_batter: {L: {usage: 100 / count}, R: {usage: 0}},
      })),
    };
    vm.runInContext('renderVelocity(); renderFrequency();', context);
    const velocity = charts['#velocity-chart'];
    const frequency = charts['#frequency-chart'];
    assert.equal(velocity.viewBox, '0 0 420 420');
    assert.equal(frequency.viewBox, '0 0 400 400');
    const bars = frequency.children.filter(e => e.class === 'frequency-bar');
    assert.equal(bars.length, count * (split ? 2 : 1));
    assert.ok(bars.every(b => b.y >= 43 && b.y + b.height <= 384));
    assert.ok(bars.at(-1).y + bars.at(-1).height > 350, 'last row must fill the panel');
    assert.ok(Math.abs(bars[0].width - (split ? 134 : 270) / count) < 1e-8, 'usage scale preserved');
    if (split) { assert.ok(bars[0].height < previousBarHeight); previousBarHeight = bars[0].height; }
    const paths = velocity.children.filter(e => e.class === 'velocity-area');
    assert.equal(paths.length, count);
    assert.ok(paths.every(p => !/NaN|Infinity/.test(p.d)));
    const averages = velocity.children.filter(e => e.class === 'velocity-average');
    assert.ok(averages.every(e => e.y1 >= 22 && e.y2 <= 386));
    assert.ok(averages.at(-1).y2 > 320);
  }
}
context.currentProfile = {player: {}, pitch_types: []};
vm.runInContext('renderVelocity(); renderFrequency();', context);
assert.ok(charts['#velocity-chart'].children.some(e => e.class === 'empty-chart'));
console.log('PASS: 1/2/4/5/6/9 pitches, split/overall usage, proportional bars, chart bounds, empty data');
