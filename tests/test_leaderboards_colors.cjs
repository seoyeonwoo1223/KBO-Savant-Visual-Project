const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const source = fs.readFileSync('web/leaderboards/leaderboards.js', 'utf8');
const context = vm.createContext({document: {querySelector: () => null}, URLSearchParams, location: {search: ''}});
vm.runInContext(source.slice(0, source.indexOf('function filteredRows()')), context);
for (const key of ['WAR', 'oWAR', 'OAA']) {
  const positive = vm.runInContext(`cellMarkup({${key}: 5}, {key: '${key}'}, {${key}: 10})`, context);
  assert.match(positive, /war-cell/);
  assert.match(positive, /rgb\(236 164 168\)/);
  const negative = vm.runInContext(`cellMarkup({${key}: -5}, {key: '${key}'}, {${key}: 10})`, context);
  assert.match(negative, /rgb\(157 179 212\)/);
  assert.doesNotMatch(vm.runInContext(`cellMarkup({${key}: null}, {key: '${key}'}, {${key}: 10})`, context), /war-cell/);
}
assert.equal(vm.runInContext('isColoredColumn({key: "CF", label: "CF OAA"})', context), true);
assert.equal(vm.runInContext('hiddenColumns.batting.has("OAA")', context), false);
console.log('리더보드 WAR/oWAR/OAA 조건부 서식 통과');
