"""Split the effect of holding rows out of SBJ into direct scoring and refit parts, against random controls.

    python analysis/sbj_location/hold_decompose.py <season> <work dir> <target tag> <control tag>...

za_raw = 100 * mean((swing - p_swing) * (2 p_zone - 1)) per batter (300+ pitches in the baseline).
- direct:  baseline predictions, removed rows dropped from the batter average (no refit)
- refit:   refit predictions on the kept rows minus the direct value (effect of retraining only)
- total:   refit predictions minus baseline
"""
import json, sys
from pathlib import Path
import numpy as np, pandas as pd

SEASON, W, TARGET, CONTROLS = int(sys.argv[1]), Path(sys.argv[2]), sys.argv[3], sys.argv[4:]
base = pd.read_parquet(W / f'pzone_exp_{SEASON}.parquet')[['pitch_id', 'batter_id', 'batter_name', 'swing', 'p_swing', 'B_za72']].rename(columns={'B_za72': 'p_zone'})
n = base.groupby('batter_id').size(); Q = n[n >= 300].index
za = lambda d: (100 * (d.swing - d.p_swing) * (2 * d.p_zone - 1)).groupby(d.batter_id).mean()
z0 = za(base)

def run(tag):
    removed = set(json.loads((W / f'refit_{SEASON}_{tag}.removed.json').read_text()))
    kept = base[~base.pitch_id.isin(removed)]
    refit = kept[['pitch_id', 'batter_id', 'swing']].merge(pd.read_parquet(W / f'refit_{SEASON}_{tag}.parquet'), on='pitch_id', validate='one_to_one')
    zd_, zr = za(kept), za(refit)
    direct, total = (zd_ - z0).reindex(Q), (zr - z0).reindex(Q)
    retrain = total - direct
    touched = sorted(set(base[base.pitch_id.isin(removed)].batter_id) & set(Q))
    pchg = (refit.set_index('pitch_id')[['p_swing', 'p_zone']] - kept.set_index('pitch_id')[['p_swing', 'p_zone']]).abs()
    return {'tag': tag, 'removed_rows': len(removed),
            'prediction_change_on_kept_rows': {'p_swing_mean_abs': round(float(pchg.p_swing.mean()), 5), 'p_zone_mean_abs': round(float(pchg.p_zone.mean()), 5)},
            'league_retrain_mean_abs': round(float(retrain.abs().mean()), 4), 'league_retrain_max_abs': round(float(retrain.abs().max()), 4),
            'league_total_mean_abs': round(float(total.abs().mean()), 4),
            'touched': {b: {'name': base.loc[base.batter_id == b, 'batter_name'].iat[0], 'direct': round(float(direct[b]), 4),
                            'retrain': round(float(retrain[b]), 4), 'total': round(float(total[b]), 4)} for b in touched},
            '_retrain': retrain}

t = run(TARGET); cs = [run(c) for c in CONTROLS]
res = {'season': SEASON, 'target': {k: v for k, v in t.items() if k != '_retrain'},
       'controls': [{k: v for k, v in c.items() if k not in ('_retrain', 'touched')} for c in cs]}
# The target batters' retrain change under each control (where they lose no rows) = pure refit variation for them.
res['target_batters_retrain_under_controls'] = {b: [round(float(c['_retrain'][b]), 4) for c in cs] for b in t['touched']}
lm = [c['league_retrain_mean_abs'] for c in cs]
res['summary'] = {'target_league_retrain_mean_abs': t['league_retrain_mean_abs'], 'controls_league_retrain_mean_abs_range': [min(lm), max(lm)],
                  'controls_league_retrain_mean_abs_mean': round(float(np.mean(lm)), 4)}
out = W / f'hold_decompose_{SEASON}_{TARGET}.json'; out.write_text(json.dumps(res, ensure_ascii=False, indent=1))
print(json.dumps(res, ensure_ascii=False, indent=1))
