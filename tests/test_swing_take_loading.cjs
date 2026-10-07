const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const root = path.join(__dirname, '..');
const source = fs.readFileSync(path.join(root, 'web/profiles/profile.js'), 'utf8');
const html = fs.readFileSync(path.join(root, 'web/profiles/index.html'), 'utf8');
const initialScript = html.match(/<script>([\s\S]*?)<\/script>/)[1];
const updateScript = source.slice(source.indexOf('async function updateProfileImage()'), source.indexOf('compactProfileQuery.addEventListener'));
const classes = () => {
  const values = new Set();
  return { add: (...names) => names.forEach(n => values.add(n)), remove: (...names) => names.forEach(n => values.delete(n)), contains: n => values.has(n) };
};
const deferred = () => { let resolve, reject; const promise = new Promise((a, b) => { resolve = a; reject = b; }); return {promise, resolve, reject}; };
function setup({width = 390, query = '?player=66108', rendered = true, library = true} = {}) {
  const classList = classes(), capture = deferred(), decode = deferred();
  const context = vm.createContext({
    URLSearchParams, location: {search: query}, matchMedia: () => ({matches: width <= 830}),
    document: {documentElement: {classList}, querySelector: () => ({textContent: '홍창기'})},
    profileRendered: rendered, profileImageToken: 0, compactProfileQuery: {matches: width <= 830},
    profileImage: {src: '', decode: () => decode.promise},
    captureDesktop: () => capture.promise,
    URL: {createObjectURL: () => 'blob:profile', revokeObjectURL: () => {}},
    ...(library ? {html2canvas: () => {}} : {}),
  });
  vm.runInContext(initialScript + updateScript, context);
  return {context, classList, capture, decode, update: () => vm.runInContext('updateProfileImage()', context)};
}
(async () => {
  for (const [options, loading] of [[{}, true], [{width: 1440}, false], [{query: '?player=66108&thumb=1'}, false], [{query: ''}, false]]) {
    assert.equal(setup(options).classList.contains('profile-loading'), loading, '본문 표시 전 모바일 선수 프로필만 로딩 상태여야 합니다');
  }
  const success = setup();
  const pending = success.update();
  assert(success.classList.contains('profile-loading'), '캡처 중 기존 화면을 가려야 합니다');
  success.capture.resolve({toBlob: callback => callback({})});
  await new Promise(resolve => setImmediate(resolve));
  assert(success.classList.contains('profile-loading'), '디코딩 중에도 로딩 표시를 유지해야 합니다');
  assert(!success.classList.contains('profile-imaged'));
  success.decode.resolve();
  await pending;
  assert(success.classList.contains('profile-imaged'));
  assert(!success.classList.contains('profile-loading'));

  for (const failure of ['capture', 'blob', 'decode']) {
    const test = setup(), pending = test.update();
    if (failure === 'capture') test.capture.reject(new Error('capture failed'));
    else {
      test.capture.resolve({toBlob: callback => callback(failure === 'blob' ? null : {})});
      if (failure === 'decode') test.decode.reject(new Error('decode failed'));
    }
    await pending;
    assert(!test.classList.contains('profile-loading'), `${failure} 실패 후 로딩에 갇히면 안 됩니다`);
    assert(!test.classList.contains('profile-imaged'));
  }
  const missing = setup({library: false});
  await missing.update();
  assert(!missing.classList.contains('profile-loading'), '라이브러리가 없으면 DOM fallback을 표시해야 합니다');
  const data = setup({rendered: false});
  await data.update();
  assert(data.classList.contains('profile-loading'), '데이터를 기다리는 동안 모바일 DOM을 노출하면 안 됩니다');

  const resized = setup(), oldCapture = resized.update();
  resized.context.compactProfileQuery.matches = false;
  await resized.update();
  resized.capture.resolve({toBlob: callback => callback({})});
  await oldCapture;
  assert(!resized.classList.contains('profile-loading'));
  assert(!resized.classList.contains('profile-imaged'), '늦게 끝난 모바일 캡처가 데스크톱 상태를 덮어쓰면 안 됩니다');
  console.log('Swing/Take 초기 로딩·디코딩·실패 fallback·화면 전환 통과');
})().catch(error => { console.error(error); process.exitCode = 1; });
