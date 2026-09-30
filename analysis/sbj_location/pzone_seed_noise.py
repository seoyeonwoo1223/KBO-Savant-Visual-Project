"""Noise floor: refit the production za7.2 p_zone (B) with different HGB random_state; same rows/splits.
Also: B trained without the 2025 disagreeing takes but otherwise identical (isolates split noise)."""
import json, sys
from pathlib import Path
import numpy as np, pandas as pd
from visualbaseball import zone_decision as zd, plate_decision_v1 as old
ROOT = Path(__file__).resolve().parents[2]
SEASON = int(sys.argv[1]); OUT = Path(sys.argv[2])   # pzone_experiment.py work dir
orig = zd.PSWING_CATEGORICAL; zd.PSWING_CATEGORICAL = orig + ('pitch_id',); rows, _ = zd.load_rows(ROOT, SEASON); zd.PSWING_CATEGORICAL = orig
exp = pd.read_parquet(OUT / f'pzone_exp_{SEASON}.parquet').set_index('pitch_id')
B = zd.PZONE_ABS; dates = np.array(sorted({r['game_id'][:8] for r in rows}))
alt = {s: {} for s in (1, 2, 3)}
for block in np.array_split(dates, zd.CROSSFIT_FOLDS):
    held = set(block); train = [r for r in rows if r['game_id'][:8] not in held]; test = [r for r in rows if r['game_id'][:8] in held]
    for s in alt:
        old.RANDOM_STATE = s
        p = old.predict_pzone(train, test, B)
        alt[s].update(dict(zip([r['pitch_id'] for r in test], p)))
old.RANDOM_STATE = 42
df = exp.copy(); n = df.groupby('batter_id').size(); q = n[n >= 300].index
za = lambda col: (100 * ((df.swing - df.p_swing) * (2 * col - 1)).groupby(df.batter_id).mean())[q]
base = za(df.B_za72); res = {}
for s, m in alt.items():
    a = za(df.index.map(m).to_series(index=df.index).astype(float)); d = a - base
    res[f'seed_{s}'] = {'mean_abs_delta': round(float(d.abs().mean()), 4), 'max_abs_delta': round(float(d.abs().max()), 4),
                        'max_rank_shift': int((a.rank() - base.rank()).abs().max()), 'spearman': round(float(a.corr(base, method='spearman')), 5)}
print(SEASON, json.dumps(res))
(OUT / f'seed_noise_{SEASON}.json').write_text(json.dumps(res, indent=1))
