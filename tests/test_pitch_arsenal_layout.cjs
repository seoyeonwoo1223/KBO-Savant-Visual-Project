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
    const centerLine = frequency.children.find(e => e.class === 'frequency-center');
    if (split) assert.ok(frequency.children.indexOf(centerLine) > Math.max(...bars.map(bar => frequency.children.indexOf(bar))), 'center line must be drawn over the bars');
    assert.ok(bars.every(b => b.y >= 43 && b.y + b.height <= 384));
    assert.ok(bars.at(-1).y + bars.at(-1).height > 350, 'last row must fill the panel');
    assert.ok(Math.abs(bars[0].width - (split ? 134 : 270) / count) < 1e-8, 'usage scale preserved');
    if (split) { assert.ok(bars[0].height < previousBarHeight); previousBarHeight = bars[0].height; }
    const paths = velocity.children.filter(e => e.class === 'velocity-area');
    assert.equal(paths.length, count);
    assert.ok(paths.every(p => !/NaN|Infinity/.test(p.d)));
    const labels = velocity.children.filter(e => e.class === 'chart-row-label');
    assert.equal(labels.length, 0, 'velocity rows carry no pitch-name labels; the plot fills the card');
    const averages = velocity.children.filter(e => e.class === 'velocity-average');
    assert.ok(averages.every(e => e.y1 >= 22 && e.y2 <= 386));
    assert.ok(averages.at(-1).y2 > 320);
  }
}
context.currentProfile = {player: {}, pitch_types: []};
vm.runInContext('renderVelocity(); renderFrequency();', context);
assert.ok(charts['#velocity-chart'].children.some(e => e.class === 'empty-chart'));
context.currentProfile = {
  player: {},
  pitch_types: [{name: '체인지업', color: '#4bb783', usage: 100,
    velocity_kmh: {average: 135, low_75: 133, high_75: 138},
    velocity_distribution_kmh: {start: 105, step: 1, counts: [1, ...Array(20).fill(0), 1, 4, 8, 17, 30]},
  }, {name: '커브', color: '#76c8c5', usage: 1,
    velocity_kmh: {average: 122, low_75: 118, high_75: 127},
    velocity_distribution_kmh: {start: 113, step: 1, counts: [3, 8, 22, 29, 28]},
  }],
};
vm.runInContext('renderVelocity();', context);
const anomalyPath = charts['#velocity-chart'].children.find(e => e.class === 'velocity-area');
assert.ok(Number(anomalyPath.d.match(/^M ([\d.]+)/)[1]) > 61, 'zero-count bins must not drag the distribution to the axis edge');
console.log('PASS: 1/2/4/5/6/9 pitches, split/overall usage, proportional bars, chart bounds, empty data');

// eAA remains one season value; reference envelopes and unavailable bounds stay distinct.
vm.runInContext(source.slice(source.indexOf('function eaaDisplay('),source.indexOf('function movementPoint(')),context);
context.fmt=(value,digits=1)=>value==null?'—':Number(value).toFixed(digits);
context.eaa={status:'estimated_KBO_angle_unvalidated',angle_deg:0,n:120,
  range:{status:'reference_only_KBO_angle_unvalidated',low_deg:-14.23,high_deg:14.23}};
let display=vm.runInContext('eaaDisplay(eaa)',context);
assert.equal(display.value,'eAA 0°','horizontal slot must not disappear as a falsy zero');
assert.ok(display.rangeText.includes('-14.2°–14.2°'));
context.eaa.range={status:'unavailable_unseen_stadium_bias',low_deg:null,high_deg:null};
assert.equal(vm.runInContext('eaaDisplay(eaa).rangeText',context),'오차범위: 미확정');
context.eaa.status='withheld_small_sample';
assert.equal(vm.runInContext('eaaDisplay(eaa).value',context),'eAA —');
assert.equal(vm.runInContext('eaaDisplay(null).value',context),'eAA —');
for (const angle of [-30,0,41,90]) {
  const right=vm.runInContext(`eaaRay(${angle},'R','pitcher')`,context);
  const left=vm.runInContext(`eaaRay(${angle},'L','pitcher')`,context);
  const catcher=vm.runInContext(`eaaRay(${angle},'R','catcher')`,context);
  assert.ok(right.every(Number.isFinite));
  assert.ok(Math.abs(right[0]+left[0])<1e-8 && Math.abs(right[1]-left[1])<1e-8);
  assert.ok(Math.abs(right[0]+catcher[0])<1e-8 && Math.abs(right[1]-catcher[1])<1e-8);
  assert.ok(right.every(v=>Math.abs(v)<=30+1e-8));
}
assert.equal(vm.runInContext('eaaRay(null,"R","pitcher")',context),null);
context.eaa={model_id:'eAA-v2',status:'estimated_KBO_angle_unvalidated',angle_deg:70.9,n:916,
  range:{status:'reference_only_extrapolation_sensitivity_KBO_unvalidated',low_deg:62.7,high_deg:79.6},
  flags:{source_transition_span:true,outside_MLB_training_features:['ff_movement_size_m']}};
display=vm.runInContext('eaaDisplay(eaa)',context);
assert.ok(display.rangeText.startsWith('추정 범위 (모델 참고):'));
assert.ok(display.description.includes('측정 방식 변경 전후'));
assert.ok(display.description.includes('외삽 오차의 상한을 보장하지 않습니다'));
context.eaa.model_id='eAA-v3';
context.eaa.range.shape='global_asymmetric_reference';
context.eaa.flags.high_angle_calibration_sparse=true;
display=vm.runInContext('eaaDisplay(eaa)',context);
assert.ok(display.rangeText.startsWith('추정 범위 (모델 참고):'));
assert.ok(display.description.includes('비대칭 모델 참고 범위'));
assert.ok(display.description.includes('높은 eAA 구간의 참고 표본이 적습니다'));
context.eaa={model_id:'eAA-v2',status:'withheld_numeric_quality',angle_deg:null,n:0};
assert.equal(vm.runInContext('eaaDisplay(eaa).value',context),'eAA —');
console.log('PASS: eAA zero/missing/withheld values, separate ranges, hand/view mirroring and underhand/vertical rays');
