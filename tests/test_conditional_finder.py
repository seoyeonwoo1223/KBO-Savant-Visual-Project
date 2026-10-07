from pathlib import Path
import json

import pytest

from visualbaseball.conditional_finder import build_conditional_finder, outcome
from visualbaseball.curated import write_game
from visualbaseball.metric_state import mark_built, needs_build


@pytest.mark.parametrize('result,expected', [
    ('유내안', 'single'), ('좌중이', 'double'), ('우중삼', 'triple'), ('좌중홈', 'home_run'),
    ('홈런', 'home_run'), ('삼진', 'strikeout'), ('낫아웃', 'strikeout'), ('고의사', 'intentional_walk'),
    ('볼넷', 'walk'), ('사구', 'hbp'), ('유병', 'out'), ('중SF', 'sacrifice'),
    ('투희', 'sacrifice'), ('삼실', 'error'), ('유야선', 'fielders_choice'),
    ('새로운 사건', 'unknown'), (None, 'unknown'),
])
def test_result_classification_keeps_unknown_distinct(result, expected):
    assert outcome(result) == expected


def seed(root):
    game_id = '20260401HTLG0'
    game = {'season': 2026, 'game_id': game_id, 'game_date': '2026-04-01',
            'away_team': 'KIA', 'home_team': 'LG', 'stadium': '잠실'}
    zero_pitch_pa = {'game_id': game_id, 'pa_id': game_id + '-001', 'inning': 1,
                     'inning_half': 'top', 'event_seq': 1, 'event_type': 'plate_appearance'}
    common = {'season': 2026, 'game_id': game_id, 'pa_id': game_id + '-002',
              'batter_id': 'b', 'batter_name': '타자', 'pitcher_id': 'p', 'pitcher_name': '투수',
              'inning': 1, 'inning_half': 'top', 'pitch_type_code': 'FF', 'parse_status': 'ok'}
    rows = [{**common, 'event_seq': 2, 'pitch_id': 'pitch-1', 'pitch_number': 1, 'game_pitch_number': 1,
             'pitch_call_code': 'B', 'is_take': True, 'balls_before': 0, 'strikes_before': 0,
             'is_pa_terminal': False, 'velocity_kmh': None},
            {**common, 'event_seq': 3, 'pitch_id': 'pitch-2', 'pitch_number': 2, 'game_pitch_number': 2,
             'pitcher_id': 'p2', 'pitcher_name': '교체 투수', 'pitch_call_code': 'X', 'is_swing': True,
             'balls_before': 1, 'strikes_before': 0, 'velocity_kmh': 151.2,
             'is_pa_terminal': True, 'pa_result': '좌홈'}]
    write_game(root, game, [zero_pitch_pa], rows)


def test_builder_preserves_pa_context_pitcher_change_and_missing_values(tmp_path):
    seed(tmp_path)
    index = build_conditional_finder(tmp_path)
    base = tmp_path / 'web/data/conditional_finder/2026'
    payload = json.loads((base / 'dates/20260401.json').read_text())
    pa = dict(zip(payload['pa_columns'], payload['pas'][0]))
    rows = [dict(zip(payload['columns'], row)) for row in payload['rows']]
    assert pa['half_pa'] == 2  # 0구 타석도 순서에 포함
    assert pa['outcome'] == 'home_run'  # 마지막 공의 결과를 타석에 연결
    assert pa['result'] == '좌홈'
    assert [row['pitcher'] for row in rows] == ['p', 'p2']
    assert rows[0]['velocity'] is None
    assert rows[0]['balls'] == 0 and rows[0]['strikes'] == 0
    assert rows[0]['terminal'] is False and rows[1]['terminal'] is True
    assert index['coverage']['missing_velocity'] == 1
    assert index['players']['pitcher'][0]['files'] == ['20260401.json']
    assert all(player['teams'] == ['LG'] for player in index['players']['pitcher'])
    assert index['players']['batter'][0]['teams'] == ['KIA']
    assert json.loads((base.parent / 'index.json').read_text())['seasons'] == [2026]


def test_builder_is_deterministic_and_removes_stale_output_shards(tmp_path):
    seed(tmp_path)
    build_conditional_finder(tmp_path)
    base = tmp_path / 'web/data/conditional_finder/2026'
    before = {path.name: path.read_bytes() for path in (base / 'dates').iterdir()}
    stale = base / 'dates/stale.json'
    stale.write_text('{}')
    build_conditional_finder(tmp_path)
    assert not stale.exists()
    assert before == {path.name: path.read_bytes() for path in (base / 'dates').iterdir()}


def test_missing_date_output_triggers_rebuild(tmp_path):
    seed(tmp_path)
    build_conditional_finder(tmp_path)
    mark_built(tmp_path, 2026, 'conditional_finder')
    assert not needs_build(tmp_path, 2026, 'conditional_finder')
    (tmp_path / 'web/data/conditional_finder/2026/dates/20260401.json').unlink()
    assert needs_build(tmp_path, 2026, 'conditional_finder')


def test_cli_finder_only_uses_offline_builder(tmp_path, monkeypatch):
    from visualbaseball import cli
    called = []
    monkeypatch.setattr(cli, 'build_conditional_finder', lambda root, season: called.append((root, season)))
    monkeypatch.setattr(cli, '_build_metric', lambda root, season, name, action: action())
    monkeypatch.setattr('sys.argv', ['cli', '--root', str(tmp_path), '--only', 'conditional_finder', '--season', '2024'])
    cli.main()
    assert called == [(tmp_path, 2024)]


def test_empty_source_is_not_published_as_valid_catalog(tmp_path):
    with pytest.raises(ValueError, match='검색 가능한 투구'):
        build_conditional_finder(tmp_path)
    assert not (tmp_path / 'web/data/conditional_finder/index.json').exists()
