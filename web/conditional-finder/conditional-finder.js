/* Canonical 날짜별 검색 데이터. 조건과 판정은 화면/Node 테스트가 같은 함수를 사용합니다. */
(function () {
  'use strict';
  const HIT_OUTCOMES = new Set(['single', 'double', 'triple', 'home_run']);
  const CALL_NAMES = {B: '볼', T: 'Called strike · 루킹', S: 'Swing strike · 헛스윙', F: '파울', W: '번트 파울', X: '인플레이'};
  const OUTCOME_NAMES = {single: '단타', double: '2루타', triple: '3루타', home_run: '홈런', strikeout: '삼진', walk: '볼넷', intentional_walk: '고의사', hbp: '사구', out: '아웃', error: '실책', fielders_choice: '야수선택', sacrifice: '희생타', unknown: '결과 미확인', hit: '안타 전체'};
  const otherRole = role => role === 'pitcher' ? 'batter' : 'pitcher';
  const numeric = value => typeof value === 'number' && Number.isFinite(value);
  const escapeHTML = value => String(value ?? '—').replace(/[&<>"']/g, char => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[char]));
  const fmt = value => numeric(value) ? value.toFixed(1) : '미확인';
  const textValue = value => value == null || value === '' ? '미확인' : String(value);
  const callName = call => CALL_NAMES[call] || `미확인${call ? ` (${call})` : ''}`;
  const halfName = half => half === 'top' ? '초' : half === 'bottom' ? '말' : ' (초·말 미확인)';

  function decode(payload) {
    if (payload.schema_version !== 1 || !Array.isArray(payload.columns) || !Array.isArray(payload.pa_columns) || !Array.isArray(payload.pas) || !Array.isArray(payload.rows)) throw new Error('검색 데이터 형식을 확인할 수 없습니다.');
    const pas = payload.pas.map(values => {
      const pa = Object.fromEntries(payload.pa_columns.map((name, index) => [name, values[index]]));
      pa.game = payload.games[pa.game];
      if (!pa.game) throw new Error('경기 정보가 누락되었습니다.');
      pa.pitches = [];
      return pa;
    });
    return payload.rows.map(values => {
      if (values.length !== payload.columns.length) throw new Error('투구 정보가 누락되었습니다.');
      const pitch = Object.fromEntries(payload.columns.map((name, index) => [name, values[index]]));
      pitch.pa = pas[pitch.pa];
      if (!pitch.pa) throw new Error('타석 정보가 누락되었습니다.');
      pitch.pa.pitches.push(pitch);
      return pitch;
    });
  }

  function pitchMatches(pitch, filters) {
    const pa = pitch.pa, game = pa.game;
    if (filters.player && pitch[filters.role] !== filters.player) return false;
    if (filters.opponent && pitch[otherRole(filters.role)] !== filters.opponent) return false;
    if (filters.from && game.game_date < filters.from || filters.to && game.game_date > filters.to) return false;
    if (filters.types.length && !filters.types.includes(pitch.type)) return false;
    if (filters.min != null && (!numeric(pitch.velocity) || pitch.velocity < filters.min)) return false;
    if (filters.max != null && (!numeric(pitch.velocity) || pitch.velocity > filters.max)) return false;
    if (filters.balls != null && pitch.balls !== filters.balls || filters.strikes != null && pitch.strikes !== filters.strikes) return false;
    if (filters.action && pitch.action !== filters.action) return false;
    if (filters.calls.length && !filters.calls.includes(pitch.call)) return false;
    if (filters.outcomes.length) {
      if (!filters.outcomes.some(value => value === pa.outcome || value === 'hit' && HIT_OUTCOMES.has(pa.outcome))) return false;
      if (!filters.allPA && pitch.terminal !== true) return false;
    }
    if (filters.stadium && game.stadium !== filters.stadium) return false;
    if (filters.inning != null && pa.inning !== filters.inning || filters.half && pa.half !== filters.half) return false;
    if (filters.team) {
      if (!['top', 'bottom'].includes(pa.half)) return false;
      const homeOpponent = filters.role === 'batter' ? pa.half === 'top' : pa.half === 'bottom';
      if (game[homeOpponent ? 'home_team' : 'away_team'] !== filters.team) return false;
    }
    return true;
  }

  function selectFiles(index, filters) {
    const player = index.players[filters.role].find(player => player.id === filters.player);
    const opponent = index.players[otherRole(filters.role)].find(player => player.id === filters.opponent);
    if (filters.player && !player || filters.opponent && !opponent) return [];
    const primaryFiles = player ? new Set(player.files) : null;
    const opponentFiles = opponent ? new Set(opponent.files) : null;
    return index.files.filter(entry => (!filters.from || entry.date >= filters.from) && (!filters.to || entry.date <= filters.to) && (!primaryFiles || primaryFiles.has(entry.file)) && (!opponentFiles || opponentFiles.has(entry.file)));
  }

  function sortPitches(pitches, order) {
    const newest = (a, b) => b.pa.game.game_date.localeCompare(a.pa.game.game_date) || b.pa.game.game_id.localeCompare(a.pa.game.game_id) || (b.game_number ?? 0) - (a.game_number ?? 0);
    return pitches.sort((a, b) => {
      if (order === 'oldest') return -newest(a, b);
      if (order === 'fastest' || order === 'slowest') {
        if (numeric(a.velocity) !== numeric(b.velocity)) return numeric(a.velocity) ? -1 : 1;
        if (numeric(a.velocity) && a.velocity !== b.velocity) return (a.velocity - b.velocity) * (order === 'fastest' ? -1 : 1);
      }
      return newest(a, b);
    });
  }

  const labelPlayer = player => `${player.name} · ${player.teams.join(' / ') || '팀 미확인'} (${player.id})`;
  function resolvePlayer(value, players) {
    value = value.trim();
    if (!value) return '';
    const exact = players.filter(player => labelPlayer(player) === value || player.name === value || player.id === value);
    if (exact.length === 1) return exact[0].id;
    throw new Error(exact.length > 1 ? '동명이인이 있습니다. 선수 목록에서 팀과 ID를 확인해 선택하세요.' : '선수 목록에서 이름을 선택하세요. 전체 검색은 이름을 비워두세요.');
  }

  const core = {decode, pitchMatches, selectFiles, sortPitches, resolvePlayer, labelPlayer};
  if (typeof module !== 'undefined' && module.exports) { module.exports = core; return; }

  const $ = selector => document.querySelector(selector);
  const $$ = selector => [...document.querySelectorAll(selector)];
  const nf = new Intl.NumberFormat('ko-KR');
  const initial = new URLSearchParams(location.search);
  const pageSize = 20;
  const state = {role: initial.get('role') === 'batter' ? 'batter' : 'pitcher', season: '', index: null, lookup: {}, cache: new Map(), matches: [], filters: null, page: 1, controller: null, revision: 0};
  const valueFields = {from: 'date-from', to: 'date-to', min: 'velocity-min', max: 'velocity-max', balls: 'balls', strikes: 'strikes', action: 'action', team: 'team', stadium: 'stadium', inning: 'inning', half: 'half', sort: 'sort'};

  function setStatus(message) { $('#status').textContent = message; }
  function setBusy(busy) {
    $('#finder-form').setAttribute('aria-busy', String(busy));
    $('#finder-fields').disabled = busy || !state.index;
    $('#cancel').hidden = !busy || !state.index;
    $$('[data-role]').forEach(button => { button.disabled = !state.index; });
  }
  function cancelWork() {
    state.controller?.abort();
    state.revision += 1;
    setBusy(false);
  }
  function clearResults() {
    $('#results').hidden = true;
    $('#result-list').replaceChildren();
    state.matches = []; state.filters = null;
    $('#copy-status').textContent = ''; $('#copy-fallback').hidden = true;
  }
  function updateRole() {
    const pitcher = state.role === 'pitcher';
    $('#finder-search-title').textContent = pitcher ? 'Pitcher Search' : 'Batter Search';
    $('#player-label').textContent = pitcher ? '투수 이름' : '타자 이름';
    $('#opponent-label').textContent = pitcher ? '상대 타자' : '상대 투수';
    $$('[data-role]').forEach(button => button.setAttribute('aria-pressed', String(button.dataset.role === state.role)));
    if (state.index) {
      $('#player-options').innerHTML = state.index.players[state.role].map(player => `<option value="${escapeHTML(labelPlayer(player))}"></option>`).join('');
      $('#opponent-options').innerHTML = state.index.players[otherRole(state.role)].map(player => `<option value="${escapeHTML(labelPlayer(player))}"></option>`).join('');
    }
  }
  async function fetchJSON(url, signal) {
    const response = await fetch(url, {signal});
    if (!response.ok) throw new Error(`데이터 요청 실패 (${response.status}).`);
    return response.json();
  }
  function applyParams(params) {
    updateRole();
    for (const role of ['pitcher', 'batter']) {
      const player = state.lookup[role].get(params.get(role));
      $(role === state.role ? '#player' : '#opponent').value = player ? labelPlayer(player) : '';
      if (params.has(role) && !player) throw new Error('공유 링크의 선수가 이 시즌 목록에 없습니다.');
    }
    for (const [key, id] of Object.entries(valueFields)) if (params.has(key)) $(`#${id}`).value = params.get(key);
    for (const [param, name] of [['types', 'type'], ['calls', 'call'], ['outcomes', 'outcome']]) {
      const values = (params.get(param) || '').split(',');
      $$(`input[name="${name}"]`).forEach(input => { input.checked = values.includes(input.value); });
    }
    $('#all-pa-pitches').checked = params.get('allPA') === '1';
  }

  async function loadSeason(params = new URLSearchParams()) {
    cancelWork(); clearResults(); state.index = null; state.cache.clear();
    state.season = $('#season').value;
    const revision = state.revision;
    state.controller = new AbortController();
    setBusy(true); $('#retry').hidden = true; setStatus(`${state.season} 시즌 선수 목록을 불러오는 중입니다.`);
    try {
      const index = await fetchJSON(`../data/conditional_finder/${state.season}/index.json`, state.controller.signal);
      if (revision !== state.revision) return;
      if (index.schema_version !== 1 || !index.players || !Array.isArray(index.files)) throw new Error('시즌 목록 형식을 확인할 수 없습니다.');
      state.index = index;
      state.lookup = Object.fromEntries(['pitcher', 'batter'].map(role => [role, new Map(index.players[role].map(player => [player.id, player]))]));
      $('#pitch-types').innerHTML = index.pitch_types.map(type => `<label><input type="checkbox" name="type" value="${escapeHTML(type.id)}"><span>${escapeHTML(type.name)}</span></label>`).join('');
      for (const [id, values] of [['stadium', index.stadiums], ['team', index.teams]]) $(`#${id}`).innerHTML = '<option value="">전체</option>' + values.map(value => `<option value="${escapeHTML(value)}">${escapeHTML(value)}</option>`).join('');
      for (const id of ['date-from', 'date-to']) { $(`#${id}`).min = index.date_range[0]; $(`#${id}`).max = index.date_range[1]; }
      $('#finder-form').reset();
      $('#sort').value = 'newest';
      $('#coverage').textContent = `${state.season} · ${index.date_range.join(' ~ ')} · ${nf.format(index.games)}경기 · ${nf.format(index.pitches)}구 · 구속 미확인 ${nf.format(index.coverage.missing_velocity)}구 · 구종 미확인 ${nf.format(index.coverage.missing_pitch_type)}구`;
      applyParams(params); setBusy(false); setStatus('조건을 선택하고 검색하세요.');
      if (params.get('search') === '1') await search();
    } catch (error) {
      if (revision !== state.revision || error.name === 'AbortError') return;
      setBusy(false); setStatus(`${error.message} 다시 불러오거나 조건을 확인하세요.`); $('#retry').hidden = false;
    }
  }

  function readFilters() {
    const numberValue = id => $(`#${id}`).value === '' ? null : Number($(`#${id}`).value);
    const checked = name => $$(`input[name="${name}"]:checked`).map(input => input.value);
    const filters = {role: state.role, player: resolvePlayer($('#player').value, state.index.players[state.role]), opponent: resolvePlayer($('#opponent').value, state.index.players[otherRole(state.role)]), from: $('#date-from').value, to: $('#date-to').value, min: numberValue('velocity-min'), max: numberValue('velocity-max'), balls: numberValue('balls'), strikes: numberValue('strikes'), action: $('#action').value, types: checked('type'), calls: checked('call'), outcomes: checked('outcome'), allPA: $('#all-pa-pitches').checked, team: $('#team').value, stadium: $('#stadium').value, inning: numberValue('inning'), half: $('#half').value, sort: $('#sort').value};
    if (filters.from && filters.to && filters.from > filters.to) throw new Error('시작일은 종료일보다 늦을 수 없습니다.');
    if (filters.min != null && filters.max != null && filters.min > filters.max) throw new Error('최소 구속은 최대 구속보다 클 수 없습니다.');
    return filters;
  }
  function paramsFor(filters) {
    const params = new URLSearchParams({season: state.season, role: filters.role, search: '1'});
    if (filters.player) params.set(filters.role, filters.player);
    if (filters.opponent) params.set(otherRole(filters.role), filters.opponent);
    for (const key of Object.keys(valueFields)) if (filters[key] != null && filters[key] !== '') params.set(key, filters[key]);
    for (const key of ['types', 'calls', 'outcomes']) if (filters[key].length) params.set(key, filters[key].join(','));
    if (filters.allPA) params.set('allPA', '1');
    return params;
  }
  async function loadDate(entry, signal) {
    if (state.cache.has(entry.file)) return state.cache.get(entry.file);
    const payload = await fetchJSON(`../data/conditional_finder/${state.season}/dates/${entry.file}`, signal);
    const rows = decode(payload);
    state.cache.set(entry.file, rows);
    if (state.cache.size > 24) state.cache.delete(state.cache.keys().next().value);
    return rows;
  }
  async function search() {
    if (!state.index || !$('#finder-form').reportValidity()) return;
    let filters;
    try { filters = readFilters(); } catch (error) { setStatus(error.message); return; }
    cancelWork(); clearResults(); setBusy(true); $('#retry').hidden = true;
    const revision = state.revision;
    state.controller = new AbortController();
    const signal = state.controller.signal;
    const files = selectFiles(state.index, filters), matches = [];
    let nextFile = 0, completed = 0;
    setStatus(`검색할 ${files.length}일의 데이터를 불러오는 중입니다.`);
    try {
      async function worker() {
        while (nextFile < files.length) {
          const entry = files[nextFile++];
          const rows = await loadDate(entry, signal);
          if (revision !== state.revision) return;
          for (const pitch of rows) if (pitchMatches(pitch, filters)) matches.push(pitch);
          completed += 1; setStatus(`${completed} / ${files.length}일 검색 중 · ${nf.format(matches.length)}구 발견`);
        }
      }
      await Promise.all(Array.from({length: Math.min(6, files.length)}, worker));
      if (revision !== state.revision) return;
      state.matches = sortPitches(matches, filters.sort); state.filters = filters; state.page = 1;
      setBusy(false); setStatus(`${nf.format(matches.length)}구를 찾았습니다.`);
      history.replaceState(null, '', `${location.pathname}?${paramsFor(filters)}`);
      renderResults(); renderThumbnail();
    } catch (error) {
      if (revision !== state.revision || error.name === 'AbortError') return;
      cancelWork();
      setStatus(`${error.message} 검색을 완료하지 못했습니다. 조건 검색을 다시 눌러주세요.`);
      // 일부 날짜만 성공한 목록을 전체 결과로 보여 주지 않습니다.
      clearResults();
    }
  }

  function playerName(role, id) { return state.lookup[role].get(id)?.name || id || '선수 미확인'; }
  function typeName(type) { return state.index.pitch_types.find(item => item.id === type)?.name || type || '구종 미확인'; }
  function locationText(pitch) { const pa = pitch.pa; return `${textValue(pa.inning)}회${halfName(pa.half)} · 이닝 내 ${textValue(pa.half_pa)}번째 타석 · ${textValue(pitch.number)}구째`; }
  function resultName(pa) { return `${OUTCOME_NAMES[pa.outcome] || '결과 미확인'}${pa.result ? ` · ${pa.result}` : ''}`; }
  function filterSummary(filters) {
    const parts = [`${state.season} 시즌`, filters.role === 'pitcher' ? '투수 기준' : '타자 기준'];
    if (filters.player) parts.push(playerName(filters.role, filters.player));
    if (filters.opponent) parts.push(`상대 ${playerName(otherRole(filters.role), filters.opponent)}`);
    if (filters.from || filters.to) parts.push(`${filters.from || '시즌 시작'} ~ ${filters.to || '시즌 끝'}`);
    if (filters.types.length) parts.push(filters.types.map(typeName).join(' / '));
    if (filters.min != null || filters.max != null) parts.push(`구속 ${filters.min ?? '제한 없음'} ~ ${filters.max ?? '제한 없음'} km/h`);
    if (filters.balls != null) parts.push(`${filters.balls}볼`);
    if (filters.strikes != null) parts.push(`${filters.strikes}스트라이크`);
    if (filters.action) parts.push(filters.action === 'take' ? 'Take' : 'Swing');
    if (filters.calls.length) parts.push(filters.calls.map(callName).join(' / '));
    if (filters.outcomes.length) parts.push(filters.outcomes.map(value => OUTCOME_NAMES[value]).join(' / '), filters.allPA ? '타석 전체 투구' : '결과를 만든 공');
    if (filters.team) parts.push(`상대 ${filters.team}`);
    if (filters.stadium) parts.push(filters.stadium);
    if (filters.inning != null || filters.half) parts.push(`${filters.inning ?? '모든 '}회${filters.half ? halfName(filters.half) : ''}`);
    return parts.join(' · ');
  }
  function cardBody(pitch) {
    const game = pitch.pa.game;
    return `<div class="finder-hit-top"><p class="finder-game">${escapeHTML(game.game_date)} · ${escapeHTML(game.away_team)} vs ${escapeHTML(game.home_team)} · ${escapeHTML(game.stadium || '구장 미확인')}</p><span class="finder-outcome finder-outcome--${escapeHTML(pitch.pa.outcome)}">${escapeHTML(resultName(pitch.pa))}</span></div>
      <h3>${escapeHTML(playerName('pitcher', pitch.pitcher))} → ${escapeHTML(playerName('batter', pitch.batter))}</h3>
      <p class="finder-pitch-line">${escapeHTML(locationText(pitch))}<br><strong>${escapeHTML(typeName(pitch.type))} · ${fmt(pitch.velocity)}${numeric(pitch.velocity) ? ' km/h' : ''}</strong> · 투구 전 ${textValue(pitch.balls)}볼 ${textValue(pitch.strikes)}스트라이크 · ${escapeHTML(callName(pitch.call))}</p>`;
  }
  function renderResults() {
    const filters = state.filters, total = state.matches.length;
    $('#results').hidden = false;
    $('#result-summary').textContent = `${nf.format(total)}구 · ${nf.format(new Set(state.matches.map(pitch => `${pitch.pa.game.game_id}/${pitch.pa.id}`)).size)}타석 · ${nf.format(new Set(state.matches.map(pitch => pitch.pa.game.game_id)).size)}경기`;
    $('#active-filters').textContent = filterSummary(filters);
    const first = (state.page - 1) * pageSize;
    $('#result-list').innerHTML = state.matches.slice(first, first + pageSize).map((pitch, offset) => {
      const game = pitch.pa.game;
      return `<article class="finder-hit">${cardBody(pitch)}
        <p class="finder-situation">${textValue(pitch.outs)}아웃 · 주자 ${escapeHTML(pitch.bases == null ? '미확인' : pitch.bases === '---' ? '없음' : pitch.bases)} · 투구 전 점수 ${escapeHTML(game.away_team)} ${textValue(pitch.away_score)} : ${textValue(pitch.home_score)} ${escapeHTML(game.home_team)}${pitch.status !== 'ok' ? ` · 원자료 상태 ${escapeHTML(pitch.status || '미확인')}` : ''}</p>
        <div class="finder-hit-actions"><button type="button" class="finder-button" data-copy="${first + offset}">장면 정보 복사</button><a href="${escapeHTML(tvingURL(game.game_id))}" target="_blank" rel="noopener noreferrer">티빙 경기 영상 ↗</a></div>
        <details class="finder-pa" data-pitch="${first + offset}"><summary>타석 전체 투구 보기 (${pitch.pa.pitches.length}구)</summary><div class="finder-pa-content"></div></details></article>`;
    }).join('') || '<p class="finder-empty">조건에 맞는 공이 없습니다.<br>구속 범위를 넓히거나 판정·타석 결과 조건을 줄여보세요.</p>';
    const pages = Math.max(1, Math.ceil(total / pageSize));
    $('#page-info').textContent = `${state.page} / ${pages} 페이지`;
    $('#previous').disabled = state.page <= 1; $('#next').disabled = state.page >= pages;
    $$('[data-copy]').forEach(button => button.addEventListener('click', () => copyText(sceneText(state.matches[Number(button.dataset.copy)]), '장면 정보를 복사했습니다. 티빙 경기 영상에서 해당 이닝을 찾아보세요.')));
    $$('[data-pitch]').forEach(details => details.addEventListener('toggle', () => {
      if (details.open && !details.dataset.rendered) {
        details.querySelector('.finder-pa-content').innerHTML = paTable(state.matches[Number(details.dataset.pitch)], filters);
        details.dataset.rendered = 'true';
      }
    }));
  }
  // 티빙 경기 페이지 주소는 경기 ID 뒤에 시즌 연도를 붙인 형태입니다 (예: 20261005LTKT0 → 20261005LTKT02026).
  function tvingURL(gameId) {
    return /^\d{8}[A-Z]{4}\d$/.test(gameId || '') ? `https://www.tving.com/sports/game/${gameId}${gameId.slice(0, 4)}/video` : 'https://www.tving.com/';
  }
  function paTable(selected, filters) {
    const rows = [...selected.pa.pitches].sort((a, b) => (a.game_number ?? a.number ?? 0) - (b.game_number ?? b.number ?? 0));
    return `<p class="finder-pa-caption">경기 ID ${escapeHTML(selected.pa.game.game_id)} · 타석 ID ${escapeHTML(selected.pa.id)} · 경기 내 ${textValue(selected.game_number)}번째 공</p><div class="finder-table-wrap"><table><thead><tr><th>공</th><th>투수 → 타자</th><th>구종</th><th>km/h</th><th>볼–스트</th><th>판정</th><th>조건</th></tr></thead><tbody>${rows.map(pitch => `<tr data-selected="${pitch === selected}" data-match="${pitchMatches(pitch, filters)}"><td>${textValue(pitch.number)}</td><td>${escapeHTML(playerName('pitcher', pitch.pitcher))} → ${escapeHTML(playerName('batter', pitch.batter))}</td><td>${escapeHTML(typeName(pitch.type))}</td><td>${fmt(pitch.velocity)}</td><td>${textValue(pitch.balls)}–${textValue(pitch.strikes)}</td><td>${escapeHTML(callName(pitch.call))}${pitch.terminal ? ` · ${escapeHTML(resultName(pitch.pa))}` : ''}</td><td>${pitch === selected ? '선택한 공' : pitchMatches(pitch, filters) ? '일치' : '—'}</td></tr>`).join('')}</tbody></table></div>`;
  }
  function sceneText(pitch) {
    const game = pitch.pa.game;
    return `${game.game_date} · ${game.away_team} vs ${game.home_team} · ${game.stadium || '구장 미확인'}\n${locationText(pitch)}\n${playerName('pitcher', pitch.pitcher)} → ${playerName('batter', pitch.batter)}\n${typeName(pitch.type)} · ${fmt(pitch.velocity)}${numeric(pitch.velocity) ? ' km/h' : ''} · 투구 전 ${textValue(pitch.balls)}볼 ${textValue(pitch.strikes)}스트라이크\n${callName(pitch.call)} · 타석 결과 ${resultName(pitch.pa)}\n경기 ID ${game.game_id} · 타석 ID ${pitch.pa.id} · 경기 내 ${textValue(pitch.game_number)}번째 공`;
  }
  async function copyText(text, message) {
    $('#copy-fallback').hidden = true;
    try {
      if (!navigator.clipboard?.writeText) throw new Error('clipboard unavailable');
      await navigator.clipboard.writeText(text); $('#copy-status').textContent = message;
    } catch {
      const fallback = $('#copy-fallback'); fallback.value = text; fallback.hidden = false; fallback.focus(); fallback.select();
      $('#copy-status').textContent = '자동 복사를 사용할 수 없습니다. 아래 선택된 내용을 복사하세요.';
    }
  }
  function renderThumbnail() {
    if (!document.documentElement.classList.contains('thumbnail-mode')) return;
    const target = $('[data-thumbnail-target]');
    target.innerHTML = `<p class="eyebrow">PITCH &amp; PLATE APPEARANCE SEARCH</p><h2>Conditional Finder</h2><p class="finder-thumb-condition">${escapeHTML(filterSummary(state.filters))}</p>${state.matches.slice(0, 2).map(pitch => `<article class="finder-hit">${cardBody(pitch)}</article>`).join('')}`;
    target.dataset.thumbnailReady = 'true';
  }

  $('#finder-form').addEventListener('submit', event => { event.preventDefault(); search(); });
  $('#season').addEventListener('change', () => { history.replaceState(null, '', location.pathname); loadSeason(); });
  $$('[data-role]').forEach(button => button.addEventListener('click', () => {
    if (button.dataset.role === state.role) return;
    cancelWork(); clearResults(); state.role = button.dataset.role; $('#player').value = ''; $('#opponent').value = ''; updateRole();
    history.replaceState(null, '', location.pathname); setStatus('조건을 선택하고 검색하세요.');
  }));
  $('#cancel').addEventListener('click', () => { cancelWork(); setStatus('검색을 취소했습니다. 조건을 바꿔 다시 검색하세요.'); });
  $('#reset-filters').addEventListener('click', () => {
    cancelWork(); $('#finder-form').reset(); $('#sort').value = 'newest'; clearResults();
    history.replaceState(null, '', location.pathname); setStatus('조건을 초기화했습니다.');
  });
  $('#retry').addEventListener('click', () => state.index ? search() : boot());
  $('#previous').addEventListener('click', () => { state.page -= 1; renderResults(); $('#results').scrollIntoView({block: 'start'}); });
  $('#next').addEventListener('click', () => { state.page += 1; renderResults(); $('#results').scrollIntoView({block: 'start'}); });
  $('#sort').addEventListener('change', () => {
    if (!state.filters) return;
    state.filters.sort = $('#sort').value; sortPitches(state.matches, state.filters.sort); state.page = 1; renderResults();
    history.replaceState(null, '', `${location.pathname}?${paramsFor(state.filters)}`);
  });
  $('#share').addEventListener('click', () => {
    if (state.filters) copyText(new URL(`?${paramsFor(state.filters)}`, location.href).href, '검색 링크를 복사했습니다.');
  });
  async function boot() {
    setBusy(true);
    $('#retry').hidden = true;
    try {
      const catalog = await fetchJSON('../data/conditional_finder/index.json');
      if (!Array.isArray(catalog.seasons) || !catalog.seasons.length) throw new Error('검색 가능한 시즌이 없습니다.');
      $('#season').innerHTML = catalog.seasons.map(season => `<option value="${Number(season)}">${Number(season)}</option>`).join('');
      $('#season').value = catalog.seasons.map(String).includes(initial.get('season')) ? initial.get('season') : String(catalog.seasons[0]);
      $('#season').disabled = false;
      await loadSeason(initial);
    } catch (error) { setStatus(`${error.message} 다시 불러오기를 눌러주세요.`); $('#retry').hidden = false; }
  }
  updateRole(); boot();
})();
