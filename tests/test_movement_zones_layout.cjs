// Movement Zones 차트 축 센서: 플롯 테두리 네 변이 모두 라벨 있는 눈금선과 맞는지 확인합니다.
// 축 범위를 눈금 간격과 어긋나게 바꾸면(예: IVB 하한 -25) 아래쪽 격자가 잘린 것처럼 보입니다.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const source = fs.readFileSync(path.join(__dirname, '../web/movement-zones/movement-zones.js'), 'utf8');
const start = source.indexOf('const AXIS=');
const end = source.indexOf('function armLine(');
assert.ok(start >= 0 && end > start, 'AXIS 상수와 grid()가 armLine() 앞에 있어야 합니다 (테스트 슬라이스 경계)');
const context = vm.createContext({});
vm.runInContext(source.slice(start, end) + ';this.out = {AXIS, sx, sy, grid: grid(), defs: defs()};', context);
const {AXIS, sx, sy, grid, defs} = context.out;

const clip = defs.match(/<clipPath id="plotClip"><rect x="([\d.]+)" y="([\d.]+)" width="([\d.]+)" height="([\d.]+)"/);
assert.ok(clip, 'plotClip 사각형이 있어야 합니다');
const frame = {left: +clip[1], top: +clip[2], right: +clip[1] + +clip[3], bottom: +clip[2] + +clip[4]};

for (const [name, min, max] of [['x', AXIS.xMin, AXIS.xMax], ['y', AXIS.yMin, AXIS.yMax]]) {
  assert.ok(Math.abs(min % AXIS.step) === 0, `${name} 하한 ${min}이 눈금 간격 ${AXIS.step}의 배수가 아닙니다`);
  assert.ok(Math.abs(max % AXIS.step) === 0, `${name} 상한 ${max}이 눈금 간격 ${AXIS.step}의 배수가 아닙니다`);
}
const close = (a, b) => Math.abs(a - b) < 1e-6;
assert.ok(close(sx(AXIS.xMin), frame.left) && close(sx(AXIS.xMax), frame.right), '가로 축 범위가 플롯 좌우 테두리와 맞지 않습니다');
assert.ok(close(sy(AXIS.yMin), frame.bottom) && close(sy(AXIS.yMax), frame.top), '세로 축 범위가 플롯 위아래 테두리와 맞지 않습니다');

// 테두리마다 그 위치에 숫자 라벨이 있는 눈금선이 있어야 합니다.
const labels = [...grid.matchAll(/<text x="([\d.]+)" y="([\d.]+)"[^>]*class="axis-text">(-?\d+)<\/text>/g)].map(m => ({x: +m[1], y: +m[2], value: +m[3]}));
const xLabels = labels.filter(l => close(l.y, 600)).map(l => l.value);
const yLabels = labels.filter(l => close(l.x, 78)).map(l => l.value);
assert.deepEqual(xLabels, [-30, -20, -10, 0, 10, 20, 30]);
assert.ok(yLabels.includes(AXIS.yMin) && yLabels.includes(AXIS.yMax), `세로 축 양 끝에 라벨이 있어야 합니다: ${yLabels}`);
const horizontal = [...grid.matchAll(/<line x1="92" y1="([\d.]+)" x2="708"/g)].map(m => +m[1]);
assert.ok(horizontal.some(y => close(y, frame.bottom)) && horizontal.some(y => close(y, frame.top)), '플롯 위아래 테두리에 격자선이 없습니다');
console.log(`PASS: movement-zones 축 HB ${AXIS.xMin}~${AXIS.xMax}, IVB ${AXIS.yMin}~${AXIS.yMax}, 테두리=눈금`);
