"""Read-only SBJ p_zone location-input experiment (2024-2026). Nothing under data/ or web/ is written.

Same eligible pitches (production zone_decision.load_rows), same 3 date-block cross-fit split as
score_crossfit, same classifier (plate_decision_v1._classifier), same take-only target
(CalledStrike vs Ball/HBP). p_swing is computed once per fold with production fit_predict and
shared by every variant, so SBJ differences come only from p_zone.
"""
import json, sys, time
from pathlib import Path
import numpy as np, pandas as pd
from sklearn.metrics import log_loss, brier_score_loss, roc_auc_score
from sklearn.linear_model import LogisticRegression
from visualbaseball import zone_decision as zd, plate_decision_v1 as old
from visualbaseball.curated import _at_plane, CM_PER_FOOT

ROOT = Path(__file__).resolve().parents[2]
SEASON = int(sys.argv[1]); OUT = Path(sys.argv[2]); OUT.mkdir(parents=True, exist_ok=True)   # work dir (per-pitch parquet stays outside the repo)
TOL_CM = 1.0; EDGE_CM = 5.0; HALF_CM = zd.PLATE_HALF_WIDTH_FT * CM_PER_FOOT
FRONT = 17 / 12

_orig_jpl = zd.judgment_plane_location
def jpl(row):
    out = _orig_jpl(row)
    ok = bool(row.get('trajectory_valid')) and not out['plane_fallback']
    xd = zd_ = zf = np.nan
    if ok:
        mid = _at_plane(row, zd.PLANE_Y_FT['mid']); front = _at_plane(row, FRONT)
        if mid is not None and front is not None:
            xd = mid[0] - float(row['px']) * CM_PER_FOOT; zf = front[1]; zd_ = zf - float(row['pz']) * CM_PER_FOOT
    out.update({'ext_traj_ok': ok, 'ext_x_dis_cm': xd, 'ext_z_dis_cm': zd_})
    return out
zd.judgment_plane_location = jpl
EXTRA = ('pitch_id', 'ext_traj_ok', 'ext_x_dis_cm', 'ext_z_dis_cm')
orig_cat = zd.PSWING_CATEGORICAL
zd.PSWING_CATEGORICAL = orig_cat + EXTRA          # only widens load_rows' keep set
rows, source = zd.load_rows(ROOT, SEASON)
zd.PSWING_CATEGORICAL = orig_cat
assert zd.pzone_fields(SEASON) == zd.PZONE_ABS
t0 = time.time()

# Derived columns for variants / strata.
for r in rows:
    ok = bool(r.get('ext_traj_ok'))
    dis = ok and (abs(r['ext_x_dis_cm']) > TOL_CM or abs(r['ext_z_dis_cm']) > TOL_CM)
    r['s_fallback'] = int(not ok); r['s_disagree'] = int(bool(dis))
    top, bot = float(r['sz_top']) * CM_PER_FOOT, float(r['sz_bottom']) * CM_PER_FOOT
    pz = (r['z_relative'] * (top - bot) / 2 + (top + bot) / 2)
    r['rep_top_gap_cm'] = pz - top; r['rep_bottom_gap_cm'] = pz - bot
    ex = [abs(abs(r['x_relative']) * HALF_CM - HALF_CM), abs(abs(r['x_mid_relative']) * HALF_CM - HALF_CM),
          abs(r['rep_top_gap_cm']), abs(r['rep_bottom_gap_cm']), abs(r['top_gap_cm']), abs(r['bottom_gap_cm'])]
    r['s_boundary'] = int(min(ex) <= EDGE_CM)
    r['flag_fallback'] = float(r['s_fallback'])

A = old.PZONE_NUMERIC                                    # reported px/pz + zone height
B = zd.PZONE_ABS                                         # za7.2
D = zd.PZONE_ABS + ('z_relative',)                       # diagnostic: add front-plane pz
C1 = zd.PZONE_ABS + ('flag_fallback',)                   # za7.2 + explicit fallback flag

def fit(train, fields, mask=None):
    take = [r for r in train if r['decision_type'] == 'Take' and (mask is None or mask(r))]
    y = np.array([r['event'] == 'CalledStrike' for r in take], dtype=int)
    return old._classifier().fit(old._encode_numeric(take, fields), y)

def score(model, test, fields):
    return np.clip(model.predict_proba(old._encode_numeric(test, fields))[:, list(model.classes_).index(1)], 1e-6, 1 - 1e-6)

dates = np.array(sorted({r['game_id'][:8] for r in rows})); result = []
for fold, block in enumerate(np.array_split(dates, zd.CROSSFIT_FOLDS)):
    held = set(block); train = [r for r in rows if r['game_id'][:8] not in held]; test = [r for r in rows if r['game_id'][:8] in held]
    pred = zd.fit_predict(train, test, **zd.SCORE_SETTINGS)
    p = {'A_reported': score(fit(train, A), test, A), 'B_za72': score(fit(train, B), test, B),
         'C1_za72_flag': score(fit(train, C1), test, C1), 'D_za72_plus_front_pz': score(fit(train, D), test, D)}
    # C2 (experiment definition only): train trajectory model only on trajectory-ok, non-disagreeing takes;
    # score those with it and every fallback/disagreeing pitch with the reported-location model A.
    clean = score(fit(train, B, lambda r: not r['s_fallback'] and not r['s_disagree']), test, B)
    special = np.array([bool(r['s_fallback'] or r['s_disagree']) for r in test])
    p['C2_split'] = np.where(special, p['A_reported'], clean)
    assert np.allclose(p['B_za72'], old.predict_pzone(train, test, B))   # same as production p_zone
    for i, r in enumerate(test):
        result.append({'pitch_id': r['pitch_id'], 'game_id': r['game_id'], 'batter_id': str(r['batter_id']), 'batter_name': r['batter_name'],
                       'fold': fold, 'swing': int(r['decision_type'] == 'Swing'), 'event': r['event'], 'p_swing': float(pred['p'][i]),
                       **{k: float(v[i]) for k, v in p.items()},
                       **{k: r[k] for k in ('s_fallback', 's_disagree', 's_boundary', 'x_relative', 'z_relative', 'x_mid_relative',
                                            'top_gap_cm', 'bottom_gap_cm', 'rep_top_gap_cm', 'rep_bottom_gap_cm', 'ext_x_dis_cm', 'ext_z_dis_cm')}})
    print(SEASON, 'fold', fold, len(test), round(time.time() - t0), 's', flush=True)
df = pd.DataFrame(result)
df.to_parquet(OUT / f'pzone_exp_{SEASON}.parquet', index=False)
VARS = ['A_reported', 'B_za72', 'C1_za72_flag', 'C2_split', 'D_za72_plus_front_pz']

def metrics(d):
    y = (d.event == 'CalledStrike').astype(int).to_numpy(); out = {'takes': int(len(d)), 'called_strike_rate': round(float(y.mean()), 4) if len(d) else None}
    if len(d) < 20 or y.min() == y.max(): return out
    for v in VARS:
        q = d[v].to_numpy(); lg = np.log(q / (1 - q)).reshape(-1, 1)
        cal = LogisticRegression(C=1e6).fit(lg, y)
        bins = np.minimum((q * 10).astype(int), 9); ece = sum(abs(y[bins == b].mean() - q[bins == b].mean()) * (bins == b).mean() for b in range(10) if (bins == b).any())
        out[v] = {'log_loss': round(log_loss(y, q, labels=[0, 1]), 5), 'brier': round(brier_score_loss(y, q), 5), 'auc': round(roc_auc_score(y, q), 5),
                  'cal_slope': round(float(cal.coef_[0, 0]), 3), 'cal_intercept': round(float(cal.intercept_[0]), 3), 'ece': round(float(ece), 5),
                  'misclass_at_0.5': int(((q >= .5) != y).sum())}
    return out

def boot(d, a, b, reps=300, seed=0):
    """Game-cluster bootstrap of mean log-loss difference a-b on takes (negative favours a)."""
    y = (d.event == 'CalledStrike').astype(int).to_numpy()
    ll = lambda q: -(y * np.log(q) + (1 - y) * np.log(1 - q))
    diff = pd.Series(ll(d[a].to_numpy()) - ll(d[b].to_numpy())).groupby(d.game_id.to_numpy()).agg(['sum', 'size'])
    rng = np.random.default_rng(seed); s, n = diff['sum'].to_numpy(), diff['size'].to_numpy(); vals = []
    for _ in range(reps):
        k = rng.integers(0, len(s), len(s)); vals.append(s[k].sum() / n[k].sum())
    return {'mean': round(float(s.sum() / n.sum()), 6), 'ci95': [round(float(np.percentile(vals, 2.5)), 6), round(float(np.percentile(vals, 97.5)), 6)]}

takes = df[df.swing == 0]
strata = {'all': takes, 'trajectory_ok': takes[takes.s_fallback == 0], 'trajectory_missing_fallback': takes[takes.s_fallback == 1],
          'reported_vs_trajectory_disagree_gt1cm': takes[takes.s_disagree == 1], 'boundary_within_5cm': takes[takes.s_boundary == 1],
          'non_boundary': takes[takes.s_boundary == 0]}
summary = {'season': SEASON, 'eligible_pitches': int(len(df)), 'takes': int(len(takes)),
           'strata_counts_all_pitches': {'fallback': int(df.s_fallback.sum()), 'disagree_gt1cm': int(df.s_disagree.sum()), 'boundary_within_5cm': int(df.s_boundary.sum())},
           'metrics': {k: metrics(v) for k, v in strata.items()},
           'logloss_diff_vs_B_za72': {k: {v: boot(d, v, 'B_za72') for v in VARS if v != 'B_za72'} for k, d in (('all', takes), ('boundary_within_5cm', strata['boundary_within_5cm']))}}
# Player SBJ sensitivity: za_raw = 100 * mean((swing - p_swing) * (2 p_zone - 1)).
players = {}
for v in VARS:
    j = (df.swing - df.p_swing) * (2 * df[v] - 1)
    players[v] = (100 * j.groupby(df.batter_id).mean())
n_seen = df.groupby('batter_id').size(); q = n_seen[n_seen >= 300].index
sens = {'qualified_batters': int(len(q))}
base = players['B_za72'][q]; base_rank = base.rank(ascending=False)
for v in VARS:
    if v == 'B_za72': continue
    alt = players[v][q]; alt_rank = alt.rank(ascending=False); d = alt - base
    sens[v] = {'spearman_vs_B': round(float(base.corr(alt, method='spearman')), 5), 'mean_abs_delta_za_raw': round(float(d.abs().mean()), 4),
               'max_abs_delta_za_raw': round(float(d.abs().max()), 4), 'max_rank_shift': int((alt_rank - base_rank).abs().max()),
               'rank_shift_ge5': int(((alt_rank - base_rank).abs() >= 5).sum()),
               'top10_overlap': int(len(set(base.nlargest(10).index) & set(alt.nlargest(10).index))),
               'largest_changes': [{'batter_id': b, 'name': df.loc[df.batter_id == b, 'batter_name'].iat[0], 'za_B': round(float(base[b]), 3), 'za_alt': round(float(alt[b]), 3)}
                                   for b in d.abs().nlargest(3).index]}
summary['player_sbj_sensitivity'] = sens
summary['za_raw_sd_qualified_B'] = round(float(base.std()), 4)
# Error cases: takes where A and B disagree by > 0.4.
t = takes.assign(gap=(takes.A_reported - takes.B_za72))
big = t[t.gap.abs() > 0.4]
summary['A_vs_B_disagreement_takes_gt0.4'] = {'n': int(len(big)), 'called_strike': int((big.event == 'CalledStrike').sum()),
    'A_closer': int(((big.event == 'CalledStrike') == (big.A_reported > big.B_za72)).sum()),
    'where_A_higher': int((big.gap > 0).sum()), 'fallback': int(big.s_fallback.sum()), 'boundary': int(big.s_boundary.sum())}
cols = ['pitch_id', 'event', 'A_reported', 'B_za72', 'x_relative', 'x_mid_relative', 'rep_top_gap_cm', 'top_gap_cm', 'rep_bottom_gap_cm', 'bottom_gap_cm', 's_fallback']
big.reindex(big.gap.abs().sort_values(ascending=False).index)[cols].head(40).round(3).to_csv(OUT / f'pzone_error_cases_{SEASON}.csv', index=False)
(OUT / f'pzone_exp_summary_{SEASON}.json').write_text(json.dumps(summary, ensure_ascii=False, indent=1))
print(json.dumps(summary, ensure_ascii=False)[:3000])
