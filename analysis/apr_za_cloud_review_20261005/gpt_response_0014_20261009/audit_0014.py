"""원격 동결 입력의 부호·정합·연결을 독립 계산한다. 콜 모형을 적합하지 않는다."""
from pathlib import Path
import hashlib
import io
import json
import subprocess

import numpy as np
import pandas as pd
import pyarrow.parquet as pq
from scipy.special import ndtr

from visualbaseball.curated import _at_plane, load_rows

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
SOURCE = 'e48da3a26a617db67fbb51f6b1cbcb072b729eaf'
REVIEW = '68e35ce1da6f91cd4659493d63b37169364b2240'
CM = 30.48
RATIOS = {2024: (.5635, .2764), 2025: (.5575, .2704), 2026: (.5575, .2704)}
COLS = ['pitch_id', 'game_id', 'game_date', 'batter_id', 'batter_name', 'sz_top', 'sz_bottom', 'trajectory_valid',
        'x0', 'y0', 'z0', 'vx0', 'vy0', 'vz0', 'ax', 'ay', 'az', 'px', 'pz', 'pitch_call_code']


def git(*args):
    return subprocess.check_output(['git', *args], cwd=ROOT)


def at_plane(frame, y):
    """공개 원천 가속도식을 배열로 직접 풀어 운영 helper와 대조한다."""
    y0, vy, ay = (frame[c].to_numpy(float) for c in ('y0', 'vy0', 'ay'))
    with np.errstate(invalid='ignore', divide='ignore'):
        disc = vy * vy - 2 * ay * (y0 - y)
        a, b = (-vy + np.sqrt(disc)) / ay, (-vy - np.sqrt(disc)) / ay
        time = np.where(np.abs(a) <= np.abs(b), a, b)
        time = np.where(np.abs(ay) < 1e-12, (y - y0) / vy, time)
    finite = np.isfinite(frame[['x0', 'y0', 'z0', 'vx0', 'vy0', 'vz0', 'ax', 'ay', 'az']].to_numpy(float)).all(1)
    ok = frame.trajectory_valid.fillna(False).to_numpy(bool) & finite & np.isfinite(time) & (np.abs(time) <= 1)
    x = (frame.x0 + frame.vx0 * time + .5 * frame.ax * time ** 2).to_numpy() * CM
    z = (frame.z0 + frame.vz0 * time + .5 * frame.az * time ** 2).to_numpy() * CM
    x[~ok], z[~ok] = np.nan, np.nan
    return x, z


def shared_probability(x, top, bottom, radius, offsets):
    left, right, upper, lower = offsets
    px = ndtr((23.59 + radius + right - x) / 1.7) - ndtr((-23.59 - radius + left - x) / 1.7)
    pz = np.maximum(0, ndtr((radius + upper - top) / 1.3) - ndtr((-radius + lower - bottom) / 1.3))
    return px * pz


def main():
    summary = json.loads(git('show', SOURCE + ':data/curated/summary.json'))
    schema = json.loads(git('show', SOURCE + ':data/curated/schema.json'))
    assert set(COLS) <= {c['name'] for c in schema['tables']['pitches']}
    claimed = json.loads(git('show', REVIEW + ':analysis/apr_za_cloud_review_20261005/claude_review_20261009/followup_0013.json'))
    trees, files = {}, {}
    for year in range(2019, 2027):
        p = f'data/curated/pitches/season={year}'
        tree = git('rev-parse', SOURCE + ':' + p).decode().strip()
        assert tree == git('rev-parse', 'HEAD:' + p).decode().strip()
        assert tree == claimed['provenance']['curated_pitches_tree_sha_by_season'][str(year)]
        trees[str(year)] = tree
    for year in RATIOS:
        entries = git('ls-tree', '-r', SOURCE, f'data/curated/pitches/season={year}').decode().splitlines()
        for entry in entries:
            header, name = entry.split('\t'); oid = header.split()[-1]
            assert git('hash-object', name).decode().strip() == oid
            files[name] = {'git_blob': oid, 'sha256': hashlib.sha256((ROOT / name).read_bytes()).hexdigest()}
    ignore = subprocess.run(['git', 'check-ignore', '-q', 'data/curated/pitches/season=2024/month=04.parquet'], cwd=ROOT).returncode
    assert ignore == 1
    dependencies = {}
    for name in ('summary.json', 'schema.json', 'partition-index.json'):
        path = 'data/curated/' + name
        oid = git('rev-parse', SOURCE + ':' + path).decode().strip()
        assert git('hash-object', path).decode().strip() == oid
        dependencies[path] = oid
    for path in ('src/visualbaseball/curated.py', 'src/visualbaseball/zone_decision.py', 'src/visualbaseball/swing_take.py'):
        oid = git('rev-parse', SOURCE + ':' + path).decode().strip()
        assert git('hash-object', path).decode().strip() == oid
        dependencies[path] = oid
    out = {'source_commit': SOURCE, 'review_commit_read': REVIEW,
           'curated_tracking_correction': '0013의 curated gitignore 주장은 잘못이었다. 8개 시즌 tree를 원격 고정 커밋과 대조했다.',
           'curated_tree_sha_by_season': trees, 'selected_curated_files': files,
           'loader_and_geometry_dependencies_git_blob': dependencies,
           'metadata_sha256': {n: hashlib.sha256(git('show', SOURCE + ':data/curated/' + n)).hexdigest() for n in ('summary.json', 'schema.json')},
           'seasons': {}}
    candidates = None
    grid_hits = {'.1cm': 0, '1cm': 0}
    grid_expected = {'.1cm': 0., '1cm': 0.}
    grid_total = 0
    for year, (rt, rb) in RATIOS.items():
        df = pd.DataFrame(load_rows(ROOT, 'pitches', year, columns=COLS))
        assert len(df) == summary['seasons'][str(year)]['tables']['pitches']['rows']
        xm, zm = at_plane(df, 8.5 / 12)
        xb, zb = at_plane(df, 0)
        xf, zf = at_plane(df, 17 / 12)
        delta = zm - zb; finite = np.isfinite(delta)
        mismatch = finite & ((np.abs(df.px.to_numpy(float) * CM - xm) > 1) | (np.abs(df.pz.to_numpy(float) * CM - zf) > 1))
        ht, hb = df.sz_top.to_numpy(float) * CM / rt, df.sz_bottom.to_numpy(float) * CM / rb
        hfinite = np.isfinite(ht) & np.isfinite(hb)
        lo = np.maximum((df.sz_top.to_numpy(float) - .0005) * CM / rt, (df.sz_bottom.to_numpy(float) - .0005) * CM / rb)
        hi = np.minimum((df.sz_top.to_numpy(float) + .0005) * CM / rt, (df.sz_bottom.to_numpy(float) + .0005) * CM / rb)
        consistent = hfinite & (lo <= hi)
        negative = df.loc[finite & (delta < 0), ['pitch_id', 'game_id', 'batter_id']].copy()
        negative['delta_cm'] = delta[finite & (delta < 0)]
        err = []
        sample = np.unique(np.r_[np.flatnonzero(finite & (delta < 0)), np.flatnonzero(finite)[::2000]])
        for j in sample:
            row = df.iloc[int(j)].to_dict()
            mid, back = _at_plane(row, 8.5 / 12), _at_plane(row, 0)
            err.append(max(abs(mid[0] - xm[j]), abs(mid[1] - zm[j]), abs(back[1] - zb[j])))
        assert max(err) < 1e-8
        row = {'curated_rows': len(df), 'missing_pitch_id': int(df.pitch_id.isna().sum()), 'duplicate_pitch_id': int(df.pitch_id.duplicated().sum()),
               'both_planes': int(finite.sum()), 'signed_negative': int((delta[finite] < 0).sum()),
               'signed_negative_share_all': float((finite & (delta < 0)).mean()),
               'signed_negative_share_computable': float((delta[finite] < 0).mean()), 'signed_min_cm': float(np.nanmin(delta)),
               'negative_pitch_rows': negative.to_dict('records'), 'reported_location_mismatch': int(mismatch.sum()),
               'sz_missing': int((~hfinite).sum()), 'sz_inconsistent_by_0_1cm': int((hfinite & (np.abs(ht - hb) > .1)).sum()),
               'sz_inconsistent_by_rounding_intersection': int((hfinite & ~consistent).sum()),
               'joint_geometry_and_sz_rows': int((finite & ~mismatch & consistent).sum()), 'helper_sample_max_error_cm': float(max(err))}
        assert row['sz_inconsistent_by_0_1cm'] == claimed['sz_consistency'][str(year)]['inconsistent_pitches']
        assert row['signed_negative'] == round(claimed['planes'][str(year)]['signed_negative_share'] * len(df))
        assert row['missing_pitch_id'] == row['duplicate_pitch_id'] == 0
        out['seasons'][str(year)] = row
        modes = (df.dropna(subset=['sz_top', 'sz_bottom']).groupby(['batter_id', 'sz_top', 'sz_bottom']).size()
                 .reset_index(name='n').sort_values(['n', 'sz_top', 'sz_bottom']).drop_duplicates('batter_id', keep='last'))
        low = np.maximum((modes.sz_top.to_numpy() - .0005) * CM / rt, (modes.sz_bottom.to_numpy() - .0005) * CM / rb)
        high = np.minimum((modes.sz_top.to_numpy() + .0005) * CM / rt, (modes.sz_bottom.to_numpy() + .0005) * CM / rb)
        valid_mode = low <= high
        grid_total += int(valid_mode.sum())
        for label, grid in [('.1cm', .1), ('1cm', 1.)]:
            grid_hits[label] += int((np.floor(high[valid_mode] / grid) * grid >= low[valid_mode]).sum())
            grid_expected[label] += float(np.minimum(1., (high[valid_mode] - low[valid_mode]) / grid).sum())
        if year == 2026:
            candidates = df[['pitch_id', 'game_id', 'batter_id']].copy()
            candidates['delta'] = delta; candidates['consistent_sz'] = consistent
            candidates['kx'] = np.round(xm / 25.4, 6)
            candidates['kt'] = np.round(np.maximum(zm, zb) - df.sz_top.to_numpy(float) * CM, 6)
            candidates['kb'] = np.round(np.minimum(zm, zb) - df.sz_bottom.to_numpy(float) * CM, 6)
        print('입력 검산 완료', year, flush=True)

    data = git('show', SOURCE + ':data/metrics/zone_awareness/2026/pitches.parquet')
    pitch_sha = hashlib.sha256(data).hexdigest()
    assert pitch_sha == 'f754f18cc972775315be87eabd4fc88b3c873c420f8e439c0fea5ad13acdfe5f'
    df = pq.ParquetFile(io.BytesIO(data)).read(columns=['game_id', 'batter_id', 'x_mid_relative', 'top_gap_cm', 'bottom_gap_cm', 'swing']).to_pandas()
    df['kx'], df['kt'], df['kb'] = df.x_mid_relative.round(6), df.top_gap_cm.round(6), df.bottom_gap_cm.round(6)
    key = ['game_id', 'batter_id', 'kx', 'kt', 'kb']
    c = candidates.dropna(subset=['kx', 'kt', 'kb', 'delta'])
    g = c.groupby(key).agg(rows=('pitch_id', 'size'), delta_min=('delta', 'min'), delta_max=('delta', 'max'), consistent_sz=('consistent_sz', 'all')).reset_index()
    merged = df.merge(g, on=key, how='left', validate='many_to_one')
    matched = merged.delta_min.notna() & ((merged.delta_max - merged.delta_min).abs() <= 1e-8)
    d = merged.delta_min.to_numpy()
    st = np.maximum(0, 1.5 - d) - np.maximum(0, -d)
    sb = np.minimum(0, 1.5 - d) - np.minimum(0, -d)
    old = (merged.top_gap_cm <= 0) & (merged.bottom_gap_cm >= 0)
    new = (merged.top_gap_cm + st <= 0) & (merged.bottom_gap_cm + sb >= 0)
    take = (merged.swing == 0) & matched
    horizontal = merged.x_mid_relative.abs() * 25.4 <= 23.59
    dup = merged[(merged.rows > 1) & matched].copy()
    bad = ~merged.consistent_sz.fillna(False).astype(bool)
    exclusions = []
    for pid, f in merged.groupby('batter_id'):
        count = int(bad.loc[f.index].sum())
        if count:
            exclusions.append({'batter_id': str(pid), 'eligible_before_sz_filter': len(f), 'sz_excluded': count, 'sz_excluded_share': count / len(f)})
    out['eligible_2026'] = {'pitches': len(df), 'geometry_matched': int(matched.sum()), 'unresolved_geometry': int((~matched).sum()),
                            'takes_matched': int(take.sum()), 'signed_negative': int((matched & (d < 0)).sum()),
                            'vertical_flips': int(((old != new) & take).sum()), 'full_center_flips': int(((old != new) & horizontal & take).sum()),
                            'duplicate_geometry_candidates_pitch_rows': int(len(dup)), 'duplicate_geometry_delta_spread_cm': float((dup.delta_max - dup.delta_min).abs().max()),
                            'duplicate_geometry_rows': dup[['game_id', 'batter_id', 'swing', 'rows', 'delta_min', 'delta_max']].to_dict('records'),
                            'not_pitch_identity_join': True, 'pitch_sha256': pitch_sha,
                            'sz_inconsistent_pitch_rows': int(bad.sum()), 'sz_exclusions_by_batter': exclusions}
    assert matched.all() and len(df) == 211140
    assert out['eligible_2026']['vertical_flips'] == 1577 and out['eligible_2026']['full_center_flips'] == 848
    # 공 반지름과 자유 경계 오프셋의 정확한 비식별성을 대수 대조한다.
    x = np.array([-27., -23., 0., 23., 27.]); top = np.array([-30., 1., -8., -15., 2.]); bottom = np.array([1., 40., -1., 35., 50.])
    q1 = shared_probability(x, top, bottom, 3.7, [0, 0, 0, 0])
    eta = .02
    q2 = shared_probability(x, top, bottom, 3.7 + eta, [eta, -eta, -eta, eta])
    err = float(np.max(np.abs(q1 - q2)))
    assert err < 1e-14
    out['radius_offset_nonidentifiability'] = {'max_probability_difference': err,
        'identity': 'rho+eta, left+eta, right-eta, upper-eta, lower+eta에서 공유 오차 확률이 같다.',
        'interpretation': '반지름/경계 오프셋을 같이 적합하면 분리할 수 없다. 독립 rho 고정 후에도 무오프셋은 일관성 진단이며 ABS 설정 신장의 직접 증명은 아니다.'}
    out['zero_noise_boundary'] = {'positive_sigma_limit_at_single_exact_contact': float(ndtr(0) - ndtr(-1000)),
                                  'sigma_equal_zero_contact_included': 1,
                                  'interpretation': '경계에서 sigma가 0으로 가는 대칭 정규 극한 .5와 정확히 sigma=0인 규칙 판정1은 다르다.'}
    out['height_grid'] = {'consistent_batter_season_modes': grid_total,
                         **{label: {'observed_share': grid_hits[label] / grid_total, 'uniform_phase_reference': grid_expected[label] / grid_total} for label in grid_hits},
                         'interpretation': '양자화 해상도 정황이다. 실측 정확도·센서 독립 검증 또는 ABS 설정값 직접 연결 증거가 아니다.'}
    out['raw_spot_checks'] = []
    for case in ('2026_56637', '2025_50106'):
        year, pid = case.split('_')
        records = claimed['default_cases'][case]['games']
        chosen = [records[0]]
        if year == '2026':
            chosen.append(next(r for r in records if r['sz_top_ft'] != 3.375 and r['game_date'] >= '2026-09-01'))
        for r in chosen:
            path = f"data/raw/{year}/{r['game_id']}.json"
            content = git('show', SOURCE + ':' + path)
            raw = json.loads(content)
            pairs = {(p.get('szTop'), p.get('szBot')) for half in raw['pbpData'] for pa in half['pas'] if str(pa.get('batterId')) == pid for p in pa['pitches']}
            assert (r['sz_top_ft'], r['sz_bottom_ft']) in pairs
            out['raw_spot_checks'].append({'path': path, 'sha256': hashlib.sha256(content).hexdigest(), 'batter_id': pid, 'sz_pairs_ft': sorted(pairs)})
    out['scope'] = '원격 고정 입력의 독립 배열 계산·보조 함수 대조·대수 검산. 모형 적합/전체 heights 재실행/새 확증 아님.'
    (HERE / 'checks.json').write_text(json.dumps(out, ensure_ascii=False, indent=2, allow_nan=False) + '\n')
    print(json.dumps({'eligible_2026': out['eligible_2026'], 'nonidentifiability': out['radius_offset_nonidentifiability']}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
