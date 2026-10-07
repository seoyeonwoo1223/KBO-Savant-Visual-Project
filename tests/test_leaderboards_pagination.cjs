const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const source = fs.readFileSync('web/leaderboards/leaderboards.js', 'utf8');
const context = vm.createContext({document:{querySelector:()=>null}, URLSearchParams, location:{search:''}});
vm.runInContext(source.slice(0, source.indexOf('function filteredRows()')), context);
const evaluate = expression => JSON.parse(JSON.stringify(vm.runInContext(expression, context)));
const rows = Array.from({length:201}, (_, index)=>index+1);
context.rows=rows;
assert.deepEqual(evaluate('pageRows(rows, 1, 50).rows'), rows.slice(0,50));
assert.deepEqual(evaluate('pageRows(rows, 2, 50).rows'), rows.slice(50,100));
assert.deepEqual(evaluate('pageRows(rows, 5, 50)'), {rows:[201],page:5,pages:5,start:200});
assert.deepEqual(evaluate('pageRows(rows.slice(0, 2), 5, 50)'), {rows:[1,2],page:1,pages:1,start:0});
assert.deepEqual(evaluate('pageRows([], 3, 50)'), {rows:[],page:1,pages:1,start:0});
assert.deepEqual(evaluate('pageRows(rows, 3, 100).rows'), [201]);
function luminance(rgb) {
  return rgb.map(value=>{value/=255;return value<=.04045?value/12.92:((value+.055)/1.055)**2.4;}).reduce((sum,value,index)=>sum+value*[.2126,.7152,.0722][index],0);
}
for (let value=-100;value<=100;value++) {
  const background=evaluate(`warColor(${value},100)`).match(/\d+/g).map(Number);
  const text=evaluate(`warTextColor(${value},100)`);
  const a=luminance(background),b=luminance(text==='#fff'?[255,255,255]:[0,0,0]);
  assert.ok((Math.max(a,b)+.05)/(Math.min(a,b)+.05)>=4.5, `${value}: 글자 대비 4.5:1 미달`);
}
assert.equal(evaluate('warTextColor(100,100)'), '#fff');
assert.equal(evaluate('warTextColor(-100,100)'), '#fff');
assert.equal(evaluate('warTextColor(0,100)'), '#000');
console.log('리더보드 페이지 경계·필터 축소·빈 결과·색 대비 통과');
