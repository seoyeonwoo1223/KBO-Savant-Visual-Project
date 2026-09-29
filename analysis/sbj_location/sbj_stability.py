"""Read-only SBJ checks N4, N6, N8, N9, N10 in sbj_validation_gates.md (2024-2026, ABS seasons).

Inputs: two pzone_experiment.py work dirs, PRE (curated before the bunt correction, 7ffaba32^) and POST
(current curated). za_raw = 100 * mean((swing - p_swing) * (2 p_zone - 1)), batters with >= 300 pitches.
Writes results/sbj_stability.json and results/sbj_player_ci_<season>.csv.
"""
import json, sys
from pathlib import Path
import numpy as np, pandas as pd
from visualbaseball import zone_decision as zd

HERE = Path(__file__).resolve().parent; ROOT = HERE.parents[1]
PRE, POST = Path(sys.argv[1]), Path(sys.argv[2]); SEASONS = [int(s) for s in sys.argv[3:]] or [2024, 2025, 2026]
MIN_SEEN, REPS, CAL_MIN_TAKES, CAL_TOL = 300, 500, 2000, 0.01


def za(d, pz, ps='p_swing'):
    return 100 * ((d.swing - d[ps]) * (2 * d[pz] - 1)).groupby(d.batter_id).mean()


def ll_brier(d, col):
    y = (d.event == 'CalledStrike').to_numpy(); q = d[col].to_numpy()
    return {'log_loss': round(float(-(y * np.log(q) + (~y) * np.log(1 - q)).mean()), 5), 'brier': round(float(((q - y) ** 2).mean()), 5)}


def decomposition(pre, post, q):
    """N4: pre/post models on the same (post) test set; za_raw change split into row removal and refit."""
    common = pre.loc[post.index]
    assert (common.swing == post.swing).all() and (common.event == post.event).all(), 'labels changed on retained rows'
    takes = post.swing == 0; out = {'retained_takes': int(takes.sum()), 'removed_pitches': int(len(pre) - len(post))}
    for v in ('A_reported', 'B_za72'):
        out[v] = {'pre_model_on_post_takes': ll_brier(common[takes], v), 'post_model_on_post_takes': ll_brier(post[takes], v),
                  'pre_model_on_pre_takes': ll_brier(pre[pre.swing == 0], v)}
    for v in ('A_reported', 'B_za72'):
        full, sub, new = za(pre, v)[q], za(common, v)[q], za(post, v)[q]
        out[f'za_raw_{v}'] = {'row_removal_mean_abs': round(float((sub - full).abs().mean()), 4),
                              'refit_mean_abs': round(float((new - sub).abs().mean()), 4),
                              'total_mean_abs': round(float((new - full).abs().mean()), 4)}
    # Same-test-set A-B: the model comparison with both evaluation sets fixed.
    y = (post[takes].event == 'CalledStrike').to_numpy()
    ll = lambda q_: -(y * np.log(q_) + (~y) * np.log(1 - q_))
    out['A_minus_B_log_loss_post_takes'] = {'pre_models': round(float((ll(common[takes].A_reported.to_numpy()) - ll(common[takes].B_za72.to_numpy())).mean()), 6),
                                            'post_models': round(float((ll(post[takes].A_reported.to_numpy()) - ll(post[takes].B_za72.to_numpy())).mean()), 6)}
    return out


def calibration(t, key, col='B_za72', seed=0):
    """N6: observed CalledStrike rate minus mean p_zone per stratum; game-cluster bootstrap."""
    t = t.assign(y=(t.event == 'CalledStrike').astype(float))
    g = t.groupby(['game_id', key]).agg(y=('y', 'sum'), p=(col, 'sum'), n=('y', 'size')).reset_index()
    games = np.array(sorted(t.game_id.unique())); strata = sorted(g[key].dropna().unique())
    gi = pd.Index(games).get_indexer(g.game_id); ki = pd.Index(strata).get_indexer(g[key]); ok = ki >= 0
    Y, P, N = (np.zeros((len(games), len(strata))) for _ in range(3))
    for M, c in ((Y, 'y'), (P, 'p'), (N, 'n')): np.add.at(M, (gi[ok], ki[ok]), g[c].to_numpy()[ok])
    W = np.random.default_rng(seed).multinomial(len(games), np.full(len(games), 1 / len(games)), size=REPS)
    diff = lambda w: (w @ Y - w @ P) / (w @ N)
    point, boot = diff(np.ones(len(games))), diff(W); out = {}
    for j, s in enumerate(strata):
        lo, hi = np.nanpercentile(boot[:, j], [2.5, 97.5]); n = int(N[:, j].sum())
        out[str(s)] = {'takes': n, 'obs_minus_pred': round(float(point[j]), 5), 'ci95': [round(float(lo), 5), round(float(hi), 5)],
                       'pass': bool(n < CAL_MIN_TAKES or (abs(point[j]) <= CAL_TOL and lo <= 0 <= hi))}
    return out


def split_half(d, q, col):
    """N8: each batter's games alternate between halves in date order; Spearman-Brown corrected Pearson r."""
    g = d[['batter_id', 'game_id']].drop_duplicates().sort_values(['batter_id', 'game_id'])
    g['half'] = g.groupby('batter_id').cumcount() % 2
    h = d.merge(g, on=['batter_id', 'game_id']); j = (h.swing - h.p_swing) * (2 * h[col] - 1)
    halves = (100 * j.groupby([h.batter_id, h.half]).mean()).unstack()[[0, 1]].loc[q].dropna()
    r = float(halves[0].corr(halves[1]))
    return {'batters': int(len(halves)), 'r_half': round(r, 4), 'spearman_brown': round(2 * r / (1 + r), 4)}


def player_ci(d, q, seed=0):
    """N10: game-cluster bootstrap within batter for za_raw (B)."""
    j = (d.swing - d.p_swing) * (2 * d.B_za72 - 1)
    g = pd.DataFrame({'b': d.batter_id, 'g': d.game_id, 'j': j}).groupby(['b', 'g']).j.agg(['sum', 'size']).reset_index()
    rng = np.random.default_rng(seed); rows = []
    for b, x in g[g.b.isin(q)].groupby('b'):
        s, n = x['sum'].to_numpy(), x['size'].to_numpy(); k = rng.integers(0, len(s), (REPS, len(s)))
        vals = 100 * s[k].sum(1) / n[k].sum(1); rows.append((b, *np.percentile(vals, [2.5, 97.5])))
    return pd.DataFrame(rows, columns=['batter_id', 'ci_lo', 'ci_hi']).set_index('batter_id')


out = {'definition': {'min_pitches_seen': MIN_SEEN, 'bootstrap_reps': REPS, 'calibration_min_takes': CAL_MIN_TAKES, 'calibration_tol': CAL_TOL,
                      'pre': 'curated before 7ffaba32', 'post': 'current curated (92277e1c): 7ffaba32 bunt-foul/V correction plus the 2019-2024 KIA home Naver correction; 2025-2026 rows unchanged since 7ffaba32', 'home': 'home team code from game_id (park proxy)'},
       'seasons': {}}
za_b = {}
for s in SEASONS:
    pre = pd.read_parquet(PRE / f'pzone_exp_{s}.parquet').set_index('pitch_id'); post = pd.read_parquet(POST / f'pzone_exp_{s}.parquet').set_index('pitch_id')
    n = post.groupby('batter_id').size(); q = n[n >= MIN_SEEN].index
    orig = zd.PSWING_CATEGORICAL; zd.PSWING_CATEGORICAL = orig + ('pitch_id',); rows, _ = zd.load_rows(ROOT, s); zd.PSWING_CATEGORICAL = orig
    extra = pd.DataFrame([{**{k: r.get(k) for k in ('pitch_id', 'batter_stance', 'sz_top', 'sz_bottom')},   # curated batter_team is mostly null
                           'batter_team': r['game_id'][8:10] if r['inning_half'] == 'top' else r['game_id'][10:12]} for r in rows]).set_index('pitch_id')
    post = post.join(extra); assert post.batter_team.notna().all()
    t = post[post.swing == 0].assign(home=lambda x: x.game_id.str[10:12],
                                      zone_height=lambda x: pd.qcut(x.sz_top - x.sz_bottom, 3, labels=['low', 'mid', 'high']).astype(str))
    cal = {k: calibration(t, k) for k in ('batter_stance', 'zone_height', 'batter_team', 'home')}
    cal_fail = sorted(f'{k}:{s_}' for k, v in cal.items() for s_, x in v.items() if not x['pass'])
    zb, zA = za(post, 'B_za72')[q], za(post, 'A_reported')[q]; za_b[s] = zb
    ci = player_ci(post.reset_index(), q)
    names = post.groupby('batter_id').batter_name.first()
    table = pd.DataFrame({'season': s, 'batter_name': names[q], 'pitches': n[q], 'za_raw_B': zb, 'ci_lo': ci.ci_lo, 'ci_hi': ci.ci_hi,
                          'za_raw_A': zA, 'delta_A_minus_B': zA - zb}).round(4).sort_values('za_raw_B', ascending=False)
    table.index.name = 'batter_id'; table.to_csv(HERE / 'results' / f'sbj_player_ci_{s}.csv')
    width = float((table.ci_hi - table.ci_lo).median()); dab = float(table.delta_A_minus_B.abs().median())
    out['seasons'][str(s)] = {'qualified_batters': int(len(q)), 'N4_decomposition': decomposition(pre, post, q),
                              'N6_calibration': cal, 'N6_failing_strata': cal_fail,
                              'N8_split_half': {'B_za72': split_half(post, q, 'B_za72'), 'A_reported': split_half(post, q, 'A_reported')},
                              'N10_player_ci': {'median_ci95_width': round(width, 4), 'median_abs_delta_A_minus_B': round(dab, 4),
                                                'ratio': round(dab / width, 3), 'small_effect': bool(dab < width / 4)}}
    print(s, cal_fail, out['seasons'][str(s)]['N8_split_half'], out['seasons'][str(s)]['N10_player_ci'], flush=True)
out['N9_year_to_year'] = {}
for a, b in zip(SEASONS, SEASONS[1:]):
    both = za_b[a].index.intersection(za_b[b].index)
    out['N9_year_to_year'][f'{a}->{b}'] = {'batters': int(len(both)), 'pearson': round(float(za_b[a][both].corr(za_b[b][both])), 4)}
(HERE / 'results' / 'sbj_stability.json').write_text(json.dumps(out, ensure_ascii=False, indent=1))
print(json.dumps(out['N9_year_to_year']))
