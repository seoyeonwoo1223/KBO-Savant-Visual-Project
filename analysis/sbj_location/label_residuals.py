"""Read-only residual label-noise queue and its concentration — gates N1-N3 in sbj_validation_gates.md.

Per season: cross-fit p_zone with the production location input (2024+ za7.2 B, else reported px/pz A),
same 3 contiguous date blocks and classifier as production. A take is queued when it is > 5 cm from the
nearest zone edge (production representation) and p_zone >= 0.95 but Ball/HBP, or <= 0.05 but CalledStrike.
The queue is for independent review only: nothing is dropped or relabelled.
Usage: label_residuals.py OUT_DIR [season ...]   (OUT_DIR gets the full per-pitch queue CSV)
"""
import json, sys
from pathlib import Path
import numpy as np, pandas as pd
from visualbaseball import zone_decision as zd, plate_decision_v1 as old
from visualbaseball.curated import CM_PER_FOOT

HERE = Path(__file__).resolve().parent; ROOT = HERE.parents[1]
OUT = Path(sys.argv[1]); OUT.mkdir(parents=True, exist_ok=True)
SEASONS = [int(s) for s in sys.argv[2:]] or list(range(2019, 2027))
EDGE_CM, HI, LO, REPS = 5.0, 0.95, 0.05, 1000
HALF_CM = zd.PLATE_HALF_WIDTH_FT * CM_PER_FOOT


def edge_cm(r, abs_season):
    if abs_season:
        return min(abs(abs(r['x_mid_relative']) * HALF_CM - HALF_CM), abs(r['top_gap_cm']), abs(r['bottom_gap_cm']))
    top, bot = float(r['sz_top']) * CM_PER_FOOT, float(r['sz_bottom']) * CM_PER_FOOT
    pz = r['z_relative'] * (top - bot) / 2 + (top + bot) / 2
    return min(abs(abs(r['x_relative']) * HALF_CM - HALF_CM), abs(pz - top), abs(pz - bot))


_movement_adjust = old._movement_adjust
def movement_adjust(rows, root, season):
    # 2019-2021 have no park workbook. Movement only feeds p_swing, never p_zone, so skip it there.
    if not (root / 'data/park_adjustments' / f'{season}_VB_Park_Adjustment_v1.0.xlsx').exists(): return {'skipped': 'no park workbook'}
    return _movement_adjust(rows, root, season)
old._movement_adjust = movement_adjust


def bat_team(r):
    # curated batter_team is mostly null; the batting side follows from the half inning and the game ID.
    return r['game_id'][8:10] if r['inning_half'] == 'top' else r['game_id'][10:12]


def season_frame(season):
    orig = zd.PSWING_CATEGORICAL; zd.PSWING_CATEGORICAL = orig + ('pitch_id',); rows, _ = zd.load_rows(ROOT, season); zd.PSWING_CATEGORICAL = orig
    fields = zd.pzone_fields(season); abs_season = fields == zd.PZONE_ABS
    p = np.empty(len(rows)); dates = np.array(sorted({r['game_id'][:8] for r in rows})); day = np.array([r['game_id'][:8] for r in rows])
    for block in np.array_split(dates, zd.CROSSFIT_FOLDS):
        held = np.isin(day, block)
        p[held] = old.predict_pzone([r for r, h in zip(rows, held) if not h], [r for r, h in zip(rows, held) if h], fields)
    d = pd.DataFrame({'pitch_id': [r['pitch_id'] for r in rows], 'game_id': [r['game_id'] for r in rows],
                      'batter_id': [str(r['batter_id']) for r in rows], 'batter_name': [r['batter_name'] for r in rows],
                      'batter_team': [bat_team(r) for r in rows], 'balls_before': [r.get('balls_before') for r in rows],
                      'strikes_before': [r.get('strikes_before') for r in rows], 'decision_type': [r['decision_type'] for r in rows],
                      'event': [r['event'] for r in rows], 'p_zone': p, 'edge_cm': [edge_cm(r, abs_season) for r in rows]})
    d = d[d.decision_type == 'Take'].drop(columns='decision_type')
    d['season'] = season; d['pzone_input'] = 'B_za72' if abs_season else 'A_reported'
    d['home'] = d.game_id.str[10:12]; d['away'] = d.game_id.str[8:10]
    y = (d.event == 'CalledStrike').to_numpy(); q = np.clip(d.p_zone.to_numpy(), 1e-6, 1 - 1e-6)
    d['ll'] = -(y * np.log(q) + (~y) * np.log(1 - q))
    d['queued'] = (d.edge_cm > EDGE_CM) & (((d.p_zone >= HI) & ~y) | ((d.p_zone <= LO) & y))
    return d


def ratio_ci(d, key, seed=0):
    """Rate of queued takes in each group vs all other groups; game-cluster bootstrap (whole games resampled)."""
    g = d.groupby(['game_id', key]).agg(f=('queued', 'sum'), t=('queued', 'size')).reset_index()
    games = np.array(sorted(d.game_id.unique())); groups = sorted(g[key].dropna().unique())
    gi = pd.Index(games).get_indexer(g.game_id); ki = pd.Index(groups).get_indexer(g[key])
    F = np.zeros((len(games), len(groups))); T = F.copy(); ok = ki >= 0
    np.add.at(F, (gi[ok], ki[ok]), g.f.to_numpy()[ok]); np.add.at(T, (gi[ok], ki[ok]), g.t.to_numpy()[ok])
    W = np.random.default_rng(seed).multinomial(len(games), np.full(len(games), 1 / len(games)), size=REPS)
    def ratios(w):
        f, t = w @ F, w @ T; rest = (f.sum(-1, keepdims=True) - f) / (t.sum(-1, keepdims=True) - t)
        with np.errstate(divide='ignore', invalid='ignore'): return (f / t) / rest
    point = ratios(np.ones(len(games))); boot = ratios(W)
    out = {}
    for j, k in enumerate(groups):
        b = boot[:, j]; b = b[np.isfinite(b)]
        out[k] = {'takes': int(T[:, j].sum()), 'queued': int(F[:, j].sum()), 'per_1000': round(1000 * F[:, j].sum() / T[:, j].sum(), 3),
                  'ratio_vs_rest': round(float(point[j]), 3) if np.isfinite(point[j]) else None,
                  'ci95': [round(float(np.percentile(b, 2.5)), 3), round(float(np.percentile(b, 97.5)), 3)] if len(b) > REPS // 2 else None}
    return out


def flagged(groups):
    return sorted(k for k, v in groups.items() if v['ci95'] and v['ci95'][0] > 1.5)


frames = []; summary = {'definition': {'edge_cm_gt': EDGE_CM, 'p_zone_ball_ge': HI, 'p_zone_strike_le': LO, 'bootstrap_reps': REPS,
                                        'home': 'home team code from game_id (park proxy; second parks not separated)',
                                        'caveat': '2019-2023 are umpire seasons: queued takes mix true misses with record errors; compare teams within those seasons only'},
                         'seasons': {}}
for s in SEASONS:
    d = season_frame(s); frames.append(d); q = d[d.queued]
    summary['seasons'][str(s)] = {'pzone_input': d.pzone_input.iat[0], 'takes': int(len(d)), 'queued': int(len(q)),
                                  'queued_ball_high_p': int((q.event != 'CalledStrike').sum()), 'queued_strike_low_p': int((q.event == 'CalledStrike').sum()),
                                  'per_1000_takes': round(1000 * len(q) / len(d), 3),
                                  'N2_logloss_share': round(float(q.ll.sum() / d.ll.sum()), 4), 'mean_log_loss': round(float(d.ll.mean()), 5),
                                  'N3_by_home': ratio_ci(d, 'home'), 'N3_by_batter_team': ratio_ci(d, 'batter_team')}
    v = summary['seasons'][str(s)]; v['N3_flagged_home'] = flagged(v['N3_by_home']); v['N3_flagged_batter_team'] = flagged(v['N3_by_batter_team'])
    print(s, len(d), len(q), v['N2_logloss_share'], v['N3_flagged_home'], v['N3_flagged_batter_team'], flush=True)
all_ = pd.concat(frames)
for name, span in (('2019_2024_trackman_corrected', range(2019, 2025)), ('2025_2026_naver_corrected', range(2025, 2027))):
    d = all_[all_.season.isin(span)]
    if d.season.nunique() == len(span):
        h = ratio_ci(d, 'home'); summary[f'pooled_{name}'] = {'by_home': h, 'flagged_home': flagged(h), 'HT_home': h.get('HT')}
summary['N2_seasons_over_20pct'] = [s for s, v in summary['seasons'].items() if v['N2_logloss_share'] > 0.20]
summary['N3_any_flag'] = sorted({f'{s}:{k}' for s, v in summary['seasons'].items() for k in v['N3_flagged_home'] + v['N3_flagged_batter_team']})
cols = ['season', 'pitch_id', 'game_id', 'home', 'away', 'batter_team', 'batter_id', 'batter_name', 'balls_before', 'strikes_before', 'event', 'pzone_input', 'p_zone', 'edge_cm']
queue = all_[all_.queued][cols].round({'p_zone': 4, 'edge_cm': 2}).sort_values(['season', 'game_id', 'pitch_id'])
queue.to_csv(OUT / 'label_residual_queue.csv', index=False)
queue[queue.season >= 2024].to_csv(HERE / 'results' / 'label_residual_queue_2024_2026.csv', index=False)
(HERE / 'results' / 'label_residuals.json').write_text(json.dumps(summary, ensure_ascii=False, indent=1))
print(json.dumps({k: summary[k] for k in ('N2_seasons_over_20pct', 'N3_any_flag')}, ensure_ascii=False))
