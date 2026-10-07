"""Conditional Finder를 실제 canonical 경기와 비교하고 데스크톱·모바일 화면을 저장합니다.

    PYTHONPATH=src python scripts/check_conditional_finder.py

Playwright Chromium 필요. 결과: .cache/conditional_finder/validation.json, *.png
"""
import json
import sys
import threading
from functools import partial
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlencode

from playwright.sync_api import sync_playwright

ROOT = Path.cwd()
sys.path.insert(0, str(ROOT / 'scripts'))
from serve_web import Handler
from visualbaseball.curated import load_rows
from visualbaseball.conditional_finder import outcome

OUT = ROOT / '.cache/conditional_finder'
OUT.mkdir(parents=True, exist_ok=True)
server = ThreadingHTTPServer(('127.0.0.1', 0), partial(Handler, directory=str(ROOT / 'web')))
threading.Thread(target=server.serve_forever, daemon=True).start()
base = f'http://127.0.0.1:{server.server_address[1]}'
game_id = '20260328KTLG0'
source = load_rows(ROOT, 'pitches', 2026, game_id=game_id, columns=[
    'pitcher_id', 'batter_id', 'pitcher_name', 'batter_name', 'pitch_number', 'pa_id',
    'is_pa_terminal', 'pa_result', 'game_pitch_number', 'pitch_call_code', 'balls_before',
    'strikes_before', 'pitch_type_code', 'velocity_kmh', 'is_take', 'is_swing',
])
homer = next(row for row in source if row['is_pa_terminal'] and outcome(row['pa_result']) == 'home_run')
pa_rows = [row for row in source if row['pa_id'] == homer['pa_id']]
evidence = {'source_game': game_id, 'source_hr_pitcher': homer['pitcher_name'], 'source_hr_batter': homer['batter_name'], 'checks': []}

def record(name, **values):
    evidence['checks'].append({'check': name, **values})
    print('PASS:', name, flush=True)

with sync_playwright() as pw:
    browser = pw.chromium.launch()
    context = browser.new_context(viewport={'width': 1440, 'height': 1100}, permissions=['clipboard-read', 'clipboard-write'])
    page = context.new_page()
    errors = []
    page.on('pageerror', lambda error: errors.append(str(error)))
    requests = []
    page.on('request', lambda req: requests.append(req.url))
    page.goto(base + '/conditional-finder/')
    page.wait_for_function("!document.querySelector('#finder-fields').disabled")
    assert not any('/dates/' in url for url in requests)
    record('initial load only reads catalogs, no pitch shards')

    # 브라우저 실제 입력 → canonical 한 경기의 투구 판정/카운트와 대조
    page.fill('#player', homer['pitcher_name'])
    page.fill('#date-from', '2026-03-28'); page.fill('#date-to', '2026-03-28')
    page.check('input[name="outcome"][value="home_run"]')
    page.click('#search-button')
    page.wait_for_function("!document.querySelector('#results').hidden")
    expected = [row for row in source if row['pitcher_id'] == homer['pitcher_id'] and row['is_pa_terminal'] and outcome(row['pa_result']) == 'home_run']
    assert page.locator('.finder-result-list > article').count() == len(expected)
    assert all('/20260328.json' in url for url in requests if '/dates/' in url)
    summary = page.locator('#result-summary').inner_text()
    record('pitcher HR results equal canonical game', expected=len(expected), summary=summary)
    page.locator('.finder-pa summary').first.click()
    page.wait_for_selector('.finder-pa table')
    card = page.locator('.finder-hit').filter(has_text=homer['batter_name']).first
    if card.locator('table').count() == 0:
        card.locator('summary').click()
    assert card.locator('tbody tr').count() == len(pa_rows)
    record('expanded PA preserves every pitch', expected=len(pa_rows))
    page.locator('[data-copy]').first.click()
    clipboard = page.evaluate('navigator.clipboard.readText()')
    assert game_id in clipboard and '타석 ID' in clipboard and '구째' in clipboard
    record('scene clipboard includes game, PA, pitch sequence')
    page.click('#share')
    link = page.evaluate('navigator.clipboard.readText()')
    assert 'pitcher=' + homer['pitcher_id'] in link and 'outcomes=home_run' in link
    page.goto(link)
    page.wait_for_function("!document.querySelector('#results').hidden")
    assert page.locator('#result-summary').inner_text() == summary
    record('shared URL restores filters and results')

    page.check('#all-pa-pitches'); page.click('#search-button')
    page.wait_for_function("!document.querySelector('#results').hidden")
    expected_all = [row for row in source if row['pitcher_id'] == homer['pitcher_id'] and outcome(row['pa_result']) == 'home_run']
    assert page.locator('.finder-result-list > article').count() == len(expected_all)
    record('all-PA option returns all qualifying pitches', expected=len(expected_all))

    # 0볼/0스트 조건과 투구 판정은 마지막 공이 아닌 개별 공에 적용
    page.click('#reset-filters')
    page.fill('#player', homer['pitcher_name'])
    page.fill('#date-from', '2026-03-28'); page.fill('#date-to', '2026-03-28')
    page.select_option('#balls', '0'); page.select_option('#strikes', '0')
    page.check('input[name="call"][value="T"]'); page.select_option('#action', 'take')
    page.click('#search-button'); page.wait_for_function("!document.querySelector('#results').hidden")
    expected_count = [row for row in source if row['pitcher_id'] == homer['pitcher_id'] and row['balls_before'] == 0 and row['strikes_before'] == 0 and row['pitch_call_code'] == 'T' and row['is_take']]
    assert page.locator('.finder-result-list > article').count() == len(expected_count)
    record('0-0 called strike/take equals canonical', expected=len(expected_count))

    # 타자 탭 + 상대 투수
    page.click('[data-role="batter"]'); page.click('#reset-filters')
    page.fill('#player', homer['batter_name']); page.fill('#opponent', homer['pitcher_name'])
    page.fill('#date-from', '2026-03-28'); page.fill('#date-to', '2026-03-28')
    page.check('input[name="outcome"][value="home_run"]')
    page.click('#search-button'); page.wait_for_function("!document.querySelector('#results').hidden")
    expected_batter = [row for row in expected if row['batter_id'] == homer['batter_id']]
    assert page.locator('.finder-result-list > article').count() == len(expected_batter)
    record('batter + opposing pitcher HR equals canonical', expected=len(expected_batter))

    # source 한 날짜 전체 검색 → 페이지/정렬, 날짜 file 하나만 요청
    page.click('#reset-filters'); page.fill('#date-from', '2026-03-28'); page.fill('#date-to', '2026-03-28')
    page.click('#search-button'); page.wait_for_function("!document.querySelector('#results').hidden")
    assert page.locator('.finder-result-list > article').count() == 20
    assert not page.locator('#next').is_disabled()
    first_page = page.locator('.finder-hit h3').first.inner_text()
    page.click('#next'); assert '2 /' in page.locator('#page-info').inner_text()
    page.click('#previous'); assert '1 /' in page.locator('#page-info').inner_text()
    page.select_option('#sort', 'fastest')
    assert '1 /' in page.locator('#page-info').inner_text()
    record('pagination and speed sorting')

    # 홈 메뉴/새 앱 스크린샷, 기존 Pitch Plot과 제목 위치 비교
    params = {'season': 2026, 'role': 'pitcher', 'pitcher': homer['pitcher_id'], 'outcomes': 'home_run', 'search': '1', 'from': '2026-03-28', 'to': '2026-03-28'}
    for width in (1440, 390):
        page.set_viewport_size({'width': width, 'height': 1100})
        page.goto(base + '/conditional-finder/?' + urlencode(params))
        page.wait_for_function("!document.querySelector('#results').hidden")
        page.locator('.finder-pa summary').first.click()
        page.wait_for_selector('.finder-pa table')
        page.evaluate('window.scrollTo(0, 0)')
        assert page.evaluate('document.documentElement.scrollWidth') == width
        finder_gap = page.evaluate("document.querySelector('.page-title').getBoundingClientRect().top - document.querySelector('.site-nav-bar').getBoundingClientRect().bottom")
        finder_margin = page.locator('.page-title').evaluate("e => getComputedStyle(e).marginTop")
        assert finder_margin == '0px'
        page.screenshot(path=str(OUT / f'finder-{width}.png'), full_page=True)
        page.goto(base + '/pitch-arsenal/')
        page.wait_for_selector('.page-title')
        existing_gap = page.evaluate("document.querySelector('.page-title').getBoundingClientRect().top - document.querySelector('.site-nav-bar').getBoundingClientRect().bottom")
        assert finder_gap == existing_gap, (width, finder_gap, existing_gap)
        page.screenshot(path=str(OUT / f'pitch-plot-{width}.png'), full_page=True)
        page.goto(base + '/'); page.wait_for_load_state('networkidle')
        assert page.locator('a.visual-card[href="conditional-finder/"]').count() == 1
        assert page.evaluate('document.documentElement.scrollWidth') == width
        page.screenshot(path=str(OUT / f'home-{width}.png'), full_page=True)
        record(f'{width}px layout: no overflow, shared title spacing', gap=finder_gap, margin=finder_margin)

    # 시즌 전환 → 각 시즌 데이터 선택 보장
    page.goto(base + '/conditional-finder/')
    page.wait_for_function("!document.querySelector('#finder-fields').disabled")
    for year in ('2022', '2023', '2024', '2025', '2026'):
        page.select_option('#season', year)
        page.wait_for_function("year => document.querySelector('#coverage').textContent.startsWith(year) && !document.querySelector('#finder-fields').disabled", arg=year)
    record('all five season catalogs load')

    # 실패를 부분 결과로 표시하지 않고 재시도 가능
    page.route('**/dates/*.json', lambda route: route.fulfill(status=503, body='temporarily unavailable'))
    page.fill('#date-from', '2026-03-28'); page.fill('#date-to', '2026-03-29')
    page.click('#search-button')
    page.wait_for_function("document.querySelector('#status').textContent.includes('검색을 완료하지 못했습니다')")
    assert page.locator('#results').is_hidden() and not page.locator('#finder-fields').is_disabled()
    record('failed pitch fetch never publishes partial results')
    page.unroute('**/dates/*.json')
    page.click('#search-button'); page.wait_for_function("!document.querySelector('#results').hidden")
    record('search recovers after network failure')

    # 빈 결과와 clipboard fallback
    page.click('#reset-filters'); page.fill('#date-from', '2026-03-28'); page.fill('#date-to', '2026-03-28')
    page.fill('#velocity-min', '199'); page.click('#search-button')
    page.wait_for_selector('.finder-empty')
    assert page.locator('#previous').is_disabled() and page.locator('#next').is_disabled()
    page.evaluate("Object.defineProperty(navigator, 'clipboard', {value: undefined, configurable: true})")
    page.click('#share'); assert page.locator('#copy-fallback').is_visible()
    record('empty results and clipboard fallback')
    assert not errors, errors
    evidence['page_errors'] = errors
    context.close(); browser.close()
server.shutdown(); server.server_close()
(OUT / 'validation.json').write_text(json.dumps(evidence, ensure_ascii=False, indent=2) + '\n')
print('Browser checks complete.')
