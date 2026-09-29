"""Read-only: p_zone A (reported px/pz) vs B (za7.2) before and after the bunt-foul / bunt-miss correction.

Inputs are two pzone_experiment.py + pzone_seed_noise.py work dirs: PRE run on the curated state before
7ffaba32 and POST on the corrected curated. Adds per-boundary-distance A-B log-loss (game bootstrap, same
scheme as pzone_experiment.boot) and player za_raw deltas scaled by seed noise. Writes only under results/.
"""
import json, sys
from pathlib import Path
import numpy as np, pandas as pd
from visualbaseball import zone_decision as zd
from visualbaseball.curated import CM_PER_FOOT

HERE = Path(__file__).resolve().parent
PRE, POST = Path(sys.argv[1]), Path(sys.argv[2]); SEASONS = [int(s) for s in sys.argv[3:]] or [2024, 2025, 2026]
HALF_CM = zd.PLATE_HALF_WIDTH_FT * CM_PER_FOOT
BINS = [(0, 2), (2, 5), (5, 10), (10, 20), (20, None)]   # cm to the nearest zone edge, either representation


def edge_cm(d):
    ex = np.column_stack([(d.x_relative.abs() * HALF_CM - HALF_CM).abs(), (d.x_mid_relative.abs() * HALF_CM - HALF_CM).abs(),
                          d.rep_top_gap_cm.abs(), d.rep_bottom_gap_cm.abs(), d.top_gap_cm.abs(), d.bottom_gap_cm.abs()])
    return ex.min(axis=1)


def boot(d, reps=300, seed=0):
    y = (d.event == 'CalledStrike').astype(int).to_numpy()
    ll = lambda q: -(y * np.log(q) + (1 - y) * np.log(1 - q))
    diff = pd.Series(ll(d.A_reported.to_numpy()) - ll(d.B_za72.to_numpy())).groupby(d.game_id.to_numpy()).agg(['sum', 'size'])
    rng = np.random.default_rng(seed); s, n = diff['sum'].to_numpy(), diff['size'].to_numpy(); vals = []
    for _ in range(reps):
        k = rng.integers(0, len(s), len(s)); vals.append(s[k].sum() / n[k].sum())
    return {'mean': round(float(s.sum() / n.sum()), 6), 'ci95': [round(float(np.percentile(vals, 2.5)), 6), round(float(np.percentile(vals, 97.5)), 6)]}


def ll_brier(d, col):
    y = (d.event == 'CalledStrike').astype(int).to_numpy(); q = d[col].to_numpy()
    return round(float(-(y * np.log(q) + (1 - y) * np.log(1 - q)).mean()), 5), round(float(((q - y) ** 2).mean()), 5)


def by_edge(df):
    t = df[df.swing == 0].assign(edge=lambda d: edge_cm(d)); out = {}
    for lo, hi in BINS:
        d = t[(t.edge >= lo) & ((t.edge < hi) if hi is not None else True)]
        (la, ba), (lb, bb) = ll_brier(d, 'A_reported'), ll_brier(d, 'B_za72')
        out[f'{lo}-{hi}cm' if hi else f'>={lo}cm'] = {'takes': int(len(d)), 'A_log_loss': la, 'B_log_loss': lb, 'A_brier': ba, 'B_brier': bb,
                                                     'logloss_A_minus_B': boot(d)}
    return out


def za(df, col, q):
    return (100 * ((df.swing - df.p_swing) * (2 * df[col] - 1)).groupby(df.batter_id).mean())[q]


def players(df, seed):
    n = df.groupby('batter_id').size(); q = n[n >= 300].index
    b, a = za(df, 'B_za72', q), za(df, 'A_reported', q); shift = (a.rank(ascending=False) - b.rank(ascending=False)).abs(); d = (a - b).abs()
    noise = [v['mean_abs_delta'] for v in seed.values()]; noise_rank = [v['max_rank_shift'] for v in seed.values()]
    return {'qualified_batters': int(len(q)), 'mean_abs_delta_za_raw': round(float(d.mean()), 4), 'max_abs_delta_za_raw': round(float(d.max()), 4),
            'max_rank_shift': int(shift.max()), 'rank_shift_ge5': int((shift >= 5).sum()), 'spearman': round(float(a.corr(b, method='spearman')), 5),
            'seed_noise_mean_abs_delta': [min(noise), max(noise)], 'seed_noise_max_rank_shift': [min(noise_rank), max(noise_rank)],
            'ratio_to_seed_noise': [round(float(d.mean()) / max(noise), 2), round(float(d.mean()) / min(noise), 2)],
            'za_raw_sd_B': round(float(b.std()), 4)}, b


out = {'definition': {'A_reported': 'x_relative, z_relative, sz_top, sz_bottom', 'B_za72': 'x_mid_relative, top_gap_cm, bottom_gap_cm',
                      'target': 'takes only, ABS CalledStrike vs Ball/HBP (call reproduction, not a location validation)',
                      'pre': 'curated before 7ffaba32 (bunt fouls recorded as B, V not counted as a strike)', 'post': 'current curated (92277e1c): 7ffaba32 bunt-foul/V correction plus the 2019-2024 KIA home Naver correction; 2025-2026 rows unchanged since 7ffaba32',
                      'edge_cm': 'min distance to a zone edge over reported and judgment-plane representations',
                      'bootstrap': 'game-cluster, 300 reps, seed 0; positive = B better'}, 'seasons': {}}
for s in SEASONS:
    row = {}; base = {}
    for tag, wd in (('pre', PRE), ('post', POST)):
        df = pd.read_parquet(wd / f'pzone_exp_{s}.parquet'); summ = json.loads((wd / f'pzone_exp_summary_{s}.json').read_text())
        seed = json.loads((wd / f'seed_noise_{s}.json').read_text()); m = summ['metrics']['all']
        p, base[tag] = players(df, seed)
        row[tag] = {'eligible_pitches': summ['eligible_pitches'], 'takes': summ['takes'],
                    'A': {k: m['A_reported'][k] for k in ('log_loss', 'brier', 'misclass_at_0.5')}, 'B': {k: m['B_za72'][k] for k in ('log_loss', 'brier', 'misclass_at_0.5')},
                    'logloss_A_minus_B_all': summ['logloss_diff_vs_B_za72']['all']['A_reported'],   # boot(d, A, B) is already A-B
                    'brier_A_minus_B': round(m['A_reported']['brier'] - m['B_za72']['brier'], 5),
                    'by_edge_distance': by_edge(df), 'players': p}
        base[tag + '_ids'] = set(df.pitch_id)
    common = base['pre'].index.intersection(base['post'].index)
    row['correction_effect'] = {'eligible_pitches_removed': len(base['pre_ids'] - base['post_ids']), 'eligible_pitches_added': len(base['post_ids'] - base['pre_ids']),
                                'B_za_raw_pre_vs_post_mean_abs_delta': round(float((base['post'][common] - base['pre'][common]).abs().mean()), 4),
                                'common_qualified_batters': int(len(common))}
    out['seasons'][str(s)] = row
    print(s, json.dumps({k: row[k] for k in ('correction_effect',)}), flush=True)
(HERE / 'results' / 'pzone_bunt_compare.json').write_text(json.dumps(out, ensure_ascii=False, indent=1))
