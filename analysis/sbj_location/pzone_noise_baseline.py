"""Read-only noise floor for player SBJ (za_raw) — gate N5 in sbj_validation_gates.md.

Base = pzone_experiment.py output (production seed, 3 contiguous date blocks). Noise runs:
  pzone_seed_<s>   refit p_zone A and B with HGB random_state s; p_swing fixed at base
  pswing_seed_<s>  refit p_swing with random_state s; p_zone B fixed at base
  split_<s>        dates assigned to 3 folds at random (seed s); p_swing, A and B all refit
za_raw = 100 * mean((swing - p_swing) * (2 p_zone - 1)) over batters with >= 300 eligible pitches.
Writes results/noise_baseline_<season>.json and per-player run values to the work dir.
"""
import json, sys, time
from pathlib import Path
import numpy as np, pandas as pd
from visualbaseball import zone_decision as zd, plate_decision_v1 as old

HERE = Path(__file__).resolve().parent; ROOT = HERE.parents[1]
SEASON = int(sys.argv[1]); WORK = Path(sys.argv[2])
PZONE_SEEDS = range(1, 11); PSWING_SEEDS = range(1, 6); SPLIT_SEEDS = range(1, 6)
BASE_STATE = old.RANDOM_STATE
A, B = old.PZONE_NUMERIC, zd.PZONE_ABS

orig = zd.PSWING_CATEGORICAL; zd.PSWING_CATEGORICAL = orig + ('pitch_id',); rows, _ = zd.load_rows(ROOT, SEASON); zd.PSWING_CATEGORICAL = orig
base = pd.read_parquet(WORK / f'pzone_exp_{SEASON}.parquet').set_index('pitch_id')
ids = [r['pitch_id'] for r in rows]; assert set(ids) == set(base.index), 'work dir does not match current curated'
base = base.loc[ids]
swing = base.swing.to_numpy(); batter = base.batter_id.to_numpy()
n_seen = pd.Series(1, index=batter).groupby(level=0).size(); Q = n_seen[n_seen >= 300].index
dates = np.array(sorted({r['game_id'][:8] for r in rows})); day = np.array([r['game_id'][:8] for r in rows])
t0 = time.time()


def za(p_swing, p_zone):
    return (100 * pd.Series((swing - p_swing) * (2 * p_zone - 1)).groupby(batter).mean())[Q]


def folds(assign):
    for k in range(zd.CROSSFIT_FOLDS):
        test_idx = np.flatnonzero(assign == k); train_idx = np.flatnonzero(assign != k)
        yield [rows[i] for i in train_idx], [rows[i] for i in test_idx], test_idx


def contiguous():
    assign = np.empty(len(rows), int)
    for k, block in enumerate(np.array_split(dates, zd.CROSSFIT_FOLDS)): assign[np.isin(day, block)] = k
    return assign


def refit(assign, pzone_state=BASE_STATE, pswing_state=None, fields=(A, B)):
    """Returns p_swing (None if pswing_state is None) and {fields: p_zone} for every row."""
    ps = np.full(len(rows), np.nan) if pswing_state is not None else None; pz = {f: np.full(len(rows), np.nan) for f in fields}
    for train, test, idx in folds(assign):
        if pswing_state is not None:
            old.RANDOM_STATE = pswing_state; ps[idx] = zd.fit_predict(train, test, **zd.SCORE_SETTINGS)['p']
        old.RANDOM_STATE = pzone_state
        for f in fields: pz[f][idx] = old.predict_pzone(train, test, f)
    old.RANDOM_STATE = BASE_STATE
    return ps, pz


# Sanity: the base contiguous refit reproduces the work-dir p_zone.
_, chk = refit(contiguous(), fields=(B,)); assert np.allclose(chk[B], base.B_za72.to_numpy()), 'base p_zone not reproduced'
zb, za_a = za(base.p_swing.to_numpy(), base.B_za72.to_numpy()), za(base.p_swing.to_numpy(), base.A_reported.to_numpy())
runs = {}; per_player = {'base_B': zb, 'base_A': za_a}
for s in PZONE_SEEDS:
    _, pz = refit(contiguous(), pzone_state=s)
    per_player[f'pzone_seed_{s}_B'] = za(base.p_swing.to_numpy(), pz[B]); per_player[f'pzone_seed_{s}_A'] = za(base.p_swing.to_numpy(), pz[A])
    runs[f'pzone_seed_{s}'] = 'B'
    print(SEASON, 'pzone seed', s, round(time.time() - t0), 's', flush=True)
for s in PSWING_SEEDS:
    ps, _ = refit(contiguous(), pswing_state=s, fields=())
    per_player[f'pswing_seed_{s}_B'] = za(ps, base.B_za72.to_numpy()); runs[f'pswing_seed_{s}'] = 'B'
    print(SEASON, 'pswing seed', s, round(time.time() - t0), 's', flush=True)
for s in SPLIT_SEEDS:
    rng = np.random.default_rng(s); fold_of = dict(zip(dates, rng.permutation(np.arange(len(dates)) % zd.CROSSFIT_FOLDS)))
    ps, pz = refit(np.array([fold_of[d] for d in day]), pswing_state=BASE_STATE)
    per_player[f'split_{s}_B'] = za(ps, pz[B]); per_player[f'split_{s}_A'] = za(ps, pz[A]); runs[f'split_{s}'] = 'B'
    print(SEASON, 'split', s, round(time.time() - t0), 's', flush=True)

P = pd.DataFrame(per_player); P.index.name = 'batter_id'; P.to_parquet(WORK / f'noise_players_{SEASON}.parquet')


def delta(a, b):
    d = (a - b); shift = (a.rank(ascending=False) - b.rank(ascending=False)).abs()
    return {'mean_abs_delta': round(float(d.abs().mean()), 4), 'max_abs_delta': round(float(d.abs().max()), 4),
            'max_rank_shift': int(shift.max()), 'rank_shift_ge5': int((shift >= 5).sum())}


noise_cols = [f'{r}_B' for r in runs]
run_stats = {r: delta(P[f'{r}_B'], P.base_B) for r in runs}
env = float(np.percentile([v['mean_abs_delta'] for v in run_stats.values()], 95))
ab = delta(P.base_A, P.base_B)
player_env = (P[noise_cols].sub(P.base_B, axis=0)).abs().quantile(0.95, axis=1)   # each player's own 95th pct noise
outside = ((P.base_A - P.base_B).abs() > player_env)
# A<->B difference re-measured inside each refit that has both inputs (is the A/B gap itself stable?).
ab_within = {r: delta(P[f'{r}_A'], P[f'{r}_B']) for r in runs if f'{r}_A' in P}
groups = {g: [v['mean_abs_delta'] for r, v in run_stats.items() if r.startswith(g)] for g in ('pzone_seed', 'pswing_seed', 'split')}
out = {'season': SEASON, 'eligible_pitches': int(len(rows)), 'qualified_batters': int(len(Q)), 'runs': run_stats,
       'noise_mean_abs_delta_by_source': {g: {'min': min(v), 'median': round(float(np.median(v)), 4), 'max': max(v)} for g, v in groups.items()},
       'noise_envelope_p95_mean_abs_delta': round(env, 4),
       'A_vs_B_base': ab, 'A_vs_B_over_envelope': round(ab['mean_abs_delta'] / env, 2),
       'A_vs_B_outside_envelope': bool(ab['mean_abs_delta'] > env),
       'players_A_vs_B_outside_own_noise_p95': int(outside.sum()),
       'player_noise_p95_median': round(float(player_env.median()), 4),
       'A_vs_B_within_each_refit': {'mean_abs_delta_min': min(v['mean_abs_delta'] for v in ab_within.values()),
                                    'mean_abs_delta_max': max(v['mean_abs_delta'] for v in ab_within.values())},
       'note': 'split runs assign whole dates to folds at random; base uses contiguous date blocks'}
(HERE / 'results' / f'noise_baseline_{SEASON}.json').write_text(json.dumps(out, ensure_ascii=False, indent=1))
print(json.dumps({k: out[k] for k in ('noise_mean_abs_delta_by_source', 'noise_envelope_p95_mean_abs_delta', 'A_vs_B_over_envelope', 'players_A_vs_B_outside_own_noise_p95')}))
