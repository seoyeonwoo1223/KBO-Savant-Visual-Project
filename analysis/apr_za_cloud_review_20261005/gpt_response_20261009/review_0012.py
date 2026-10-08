"""0012의 동결 결과를 재집계하고 입력·단위·대수를 확인한다. 새 모형을 적합하지 않는다."""
from pathlib import Path
import hashlib
import io
import json
import subprocess
import sys

import numpy as np
import pandas as pd
import pyarrow.parquet as pq
from scipy.stats import norm

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
RESEARCH = '135c220da604abcfdd9537d4670794ebf17a5d2c'
SOURCE = 'e48da3a26a617db67fbb51f6b1cbcb072b729eaf'
BASE = 'analysis/apr_za_cloud_review_20261005/'
EXPECTED_PITCH_SHA = 'f754f18cc972775315be87eabd4fc88b3c873c420f8e439c0fea5ad13acdfe5f'


def blob(commit, path):
    return subprocess.check_output(['git', 'show', commit + ':' + path], cwd=ROOT)


def quantiles(values):
    return [float(x) for x in np.quantile(values, [.05, .5, .95])]


def rb3(values):
    lo, med, hi = quantiles(values)
    return bool(lo >= .75 and .90 <= med <= 1.10 and hi <= 1.25)


def main():
    inputs = {}

    def read(path, kind):
        data = blob(RESEARCH, BASE + path)
        inputs[path] = hashlib.sha256(data).hexdigest()
        return json.loads(data) if kind == 'json' else pd.read_csv(io.BytesIO(data), dtype={'batter_id': str})

    original = read('gpt_review_20261009/b1_simulation.csv', 'csv')
    independent = read('claude_review_20261009/b1_synthetic_replication.csv', 'csv')
    empirical = read('claude_review_20261009/b1_empirical_crosscheck.csv', 'csv')
    claimed = read('claude_review_20261009/cross_check.json', 'json')
    heights = read('gpt_review_20261009/kbo_heights.json', 'json')
    primary = independent[independent.G >= 20]
    failed = primary.loc[(primary.coverage < .92) | (primary.coverage > .98), 'cell'].tolist()
    assert len(original) == len(independent) == 108
    assert len(primary) == 72 and failed == [30]
    assert original[original.G >= 20].coverage.between(.92, .98).all()
    assert failed == claimed['b1_synthetic']['primary_cells_outside_92_98']
    expected = []
    for row in independent.itertuples():
        g = row.G
        m = np.full(g, 10) if row.size_design == 'equal' else np.floor(row.n * np.resize([1, 2, 3], g) / np.resize([1, 2, 3], g).sum()).astype(int)
        m[:row.n - int(m.sum())] += 1
        expected.append(row.true_B * (1 - (1 - row.icc) / row.n - row.icc * np.sum(m * m) / row.n ** 2))
    bias_error = float(np.max(np.abs(independent.expected_B_analytic - expected)))
    assert bias_error < 1e-12
    by_g = {str(g): {'original_mean': float(original[original.G == g].coverage.mean()),
                     'independent_mean': float(f.coverage.mean())} for g, f in independent.groupby('G')}
    z = norm.ppf(.975)
    cell = independent[independent.cell == 30].iloc[0]
    cp, reps = float(cell.coverage), 2000
    den = 1 + z * z / reps
    centre = (cp + z * z / (2 * reps)) / den
    half = z * np.sqrt(cp * (1 - cp) / reps + z * z / (4 * reps ** 2)) / den
    b1 = {'original_72_cells_registered_pass_preserved': True, 'independent_failed_cells': failed,
          'mean_coverage_by_G': by_g, 'cell_30_coverage': cp,
          'cell_30_wilson_95': [float(centre - half), float(centre + half)],
          'analytic_expectation_max_error': bias_error,
          'players': len(empirical), 'G_min_median_max': [int(empirical.G.min()), float(empirical.G.median()), int(empirical.G.max())],
          'IF_g_over_independent_bootstrap_quantiles': quantiles(empirical.se_if_g / empirical.boot_se),
          'current_over_independent_bootstrap_quantiles': quantiles(empirical.se_current_gpt / empirical.boot_se),
          'RB3_IF_pass': rb3(empirical.se_if_g / empirical.boot_se),
          'RB3_current_pass': rb3(empirical.se_current_gpt / empirical.boot_se),
          'bootstrap_implementation_record_max_relative_error': float(empirical.boot_star_max_rel_diff_vs_gpt_fn.max()),
          'scope': '동결 CSV·JSON 재집계와 기대값 대수 검산. 108셀 모의실험·166명 bootstrap 전 러너는 이번에 재실행하지 않았다.'}
    assert b1['RB3_IF_pass'] and b1['RB3_current_pass'] and len(empirical) == 166

    data = blob(SOURCE, 'data/metrics/zone_awareness/2026/pitches.parquet')
    sha = hashlib.sha256(data).hexdigest()
    assert sha == EXPECTED_PITCH_SHA
    pf = pq.ParquetFile(io.BytesIO(data))
    columns = ['batter_id', 'batter_name', 'sz_top', 'sz_bottom', 'swing', 'top_gap_cm', 'bottom_gap_cm', 'x_mid_relative', 'plane_fallback']
    assert all(c in pf.schema_arrow.names for c in columns)
    df = pf.read(columns=columns).to_pandas()
    assert len(df) == 211140 and df.batter_id.nunique() == 290
    profile = {r['player_id']: r['height_cm'] for r in heights if r['status'] == 'ok'}
    grouped = df.groupby('batter_id')
    med = grouped[['sz_top', 'sz_bottom']].median() * 30.48
    ht, hb = med.sz_top / .5575, med.sz_bottom / .2704
    diff = ht - pd.Series(profile).reindex(ht.index)
    mismatches = []
    for pid in ht.index[(ht - hb).abs() > 1]:
        f = df[df.batter_id == pid]
        pairs = [{'sz_top_ft': float(t), 'sz_bottom_ft': float(b), 'pitches': int(n)}
                 for (t, b), n in f.groupby(['sz_top', 'sz_bottom']).size().items()]
        mismatches.append({'batter_id': pid, 'batter_name': str(f.batter_name.iloc[0]), 'pitches': len(f),
                           'top_implied_cm': float(ht[pid]), 'bottom_implied_cm': float(hb[pid]), 'pairs': pairs})
    h = {'sample': '2026-10-03까지 고정 판단 적격 예측 파일. 전체 curated와 다른 분모.',
         'pitches': len(df), 'batters': int(len(ht)), 'profile_pitch_coverage': float(df.batter_id.isin(profile).mean()),
         'top_implied_minus_profile_p05_p50_p95_cm': quantiles(diff),
         'share_abs_difference_le_1cm': float((diff.abs() <= 1).mean()),
         'difference_sd_cm': float(diff.std()), 'top_bottom_max_difference_cm': float((ht - hb).abs().max()),
         'top_bottom_median_disagreement_over_1cm': mismatches,
         'all_season_curated_rerun': False,
         'curated_provenance_limit': '0012의 heights()는 실행 시 ROOT의 gitignore curated를 읽는다. SOURCE·pitch_sha256은 예측 파일만 고정하며 2019–2025 curated 입력 해시가 없다.'}
    assert np.allclose(h['top_implied_minus_profile_p05_p50_p95_cm'], claimed['heights']['abs_implied']['2026']['diff_p05_p50_p95_cm'])
    assert np.isclose(h['share_abs_difference_le_1cm'], claimed['heights']['abs_implied']['2026']['share_abs_diff_le_1cm'])
    assert mismatches[0]['batter_id'] == '56637'

    assert not df.plane_fallback.any()
    absolute_drop = df.top_gap_cm + df.sz_top * 30.48 - df.bottom_gap_cm - df.sz_bottom * 30.48
    # 기존 gap은 max/min만 보존한다. 부호 있는 중간면−끝면과 구별한다.
    dt, db = np.maximum(0, 1.5 - absolute_drop), np.minimum(absolute_drop, 1.5)
    top, bottom = df.top_gap_cm + dt, df.bottom_gap_cm + db
    old_vertical = (df.top_gap_cm <= 0) & (df.bottom_gap_cm >= 0)
    new_vertical = (top <= 0) & (bottom >= 0)
    # 원격 소스의 좌표 척도를 확인한다. x_mid_relative의 1은 25.4cm다.
    scale_source = blob(SOURCE, 'src/visualbaseball/swing_take.py')
    assert b'PLATE_HALF_WIDTH_FT = 10 / 12' in scale_source
    inputs['swing_take.py@' + SOURCE] = hashlib.sha256(scale_source).hexdigest()
    horizontal = df.x_mid_relative.abs() * 25.4 <= 23.59
    take = df.swing == 0
    boundary_flips = int(((old_vertical != new_vertical) & take).sum())
    whole_flips = int(((old_vertical != new_vertical) & horizontal & take).sum())
    geometry = {'interpretation': '하강 궤적 가정·공 반지름 0의 입력 기하 진단. 부호는 예측 파일의 max/min에서 확인 불가. 실제 콜/정확성 개선 아님.',
                'unsigned_plane_difference_min_cm': float(absolute_drop.min()), 'fallback_share': 0.0,
                'takes': int(take.sum()), 'vertical_only_flip_takes': boundary_flips,
                'full_center_geometry_flip_takes_conditional_on_descent': whole_flips,
                'full_center_geometry_flip_share_conditional_on_descent': whole_flips / int(take.sum()),
                'x_mid_relative_scale_cm': 25.4, 'official_horizontal_half_width_cm': 23.59,
                'general_top_shift': 'max(0,1.5-delta)-max(0,-delta)',
                'general_bottom_shift': 'min(0,1.5-delta)-min(0,-delta)',
                'delta_definition': 'signed z_mid-z_back (cm)'}
    assert boundary_flips == 1577 and whole_flips == 848
    # 임의의 두 높이에 대해 부호 있는 일반식을 직접 max/min 차와 대조한다.
    delta = np.array([-4., -.5, 0., .5, 1.5, 4.])
    assert np.allclose(np.maximum(delta, 1.5) - np.maximum(delta, 0), np.maximum(0, 1.5 - delta) - np.maximum(0, -delta))
    assert np.allclose(np.minimum(delta, 1.5) - np.minimum(delta, 0), np.minimum(0, 1.5 - delta) - np.minimum(0, -delta))

    aliases = json.loads((HERE / 'official_alias_review.json').read_text())
    assert {a['player_id'] for a in aliases} == {'50205', '76430'}
    out = {'source_commit': SOURCE, 'research_commit_read': RESEARCH, 'pitch_sha256': sha,
           'python': sys.version.split()[0], 'versions': {'numpy': np.__version__, 'pandas': pd.__version__},
           'inputs_sha256': inputs, 'B1': b1, 'height_2026_frozen_predictions': h, 'geometry_2026': geometry,
           'alias_supplement': {'exact_name_original': 1373, 'official_search_alias_verified': len(aliases),
                                'combined_confirmed_ids': 1375, 'still_missing_height': 4,
                                'alias_ids_in_2026_eligible_batters': sorted(set(df.batter_id) & {a['player_id'] for a in aliases}),
                                'historical_height_effect': '과거 시점 신장·ABS 입력 신장은 미확인'}}
    (HERE / 'checks.json').write_text(json.dumps(out, ensure_ascii=False, indent=2, allow_nan=False) + '\n')
    manifest = {name: {'sha256': hashlib.sha256((HERE / name).read_bytes()).hexdigest(), 'bytes': (HERE / name).stat().st_size}
                for name in ['review_0012.py', 'official_alias_review.json', 'README.md', 'checks.json']}
    (HERE / 'MANIFEST.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({'B1': b1, 'height': h, 'geometry': geometry}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
