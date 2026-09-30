"""Refit production SBJ (p_swing + za7.2 p_zone) with a set of eligible rows removed; save per-pitch predictions.

    python analysis/sbj_location/hold_refit.py <season> <work dir> target <queue csv> <tag>
    python analysis/sbj_location/hold_refit.py <season> <work dir> control <seed> <tag> <n_take> <n_swing> <exclude queue csv>

`target` removes every eligible row of the listed PAs. `control` removes random eligible rows with the same
take/swing mix, drawn outside the excluded PAs and outside the target batters. Read-only.
"""
import json, sys
from pathlib import Path
import numpy as np, pandas as pd
from visualbaseball import zone_decision as zd, plate_decision_v1 as old

ROOT = Path(__file__).resolve().parents[2]
SEASON, W, MODE = int(sys.argv[1]), Path(sys.argv[2]), sys.argv[3]
orig = zd.PSWING_CATEGORICAL; zd.PSWING_CATEGORICAL = orig + ('pitch_id',)
rows, _ = zd.load_rows(ROOT, SEASON); zd.PSWING_CATEGORICAL = orig
pa_of = lambda r: r['pitch_id'].split('-', 1)[1][:-3]
if MODE == 'target':
    pas = set(pd.read_csv(sys.argv[4], dtype=str).pa_id); tag = sys.argv[5]
    removed = {r['pitch_id'] for r in rows if pa_of(r) in pas}
else:
    seed, tag, n_take, n_swing = int(sys.argv[4]), sys.argv[5], int(sys.argv[6]), int(sys.argv[7])
    excl = pd.read_csv(sys.argv[8], dtype=str); pas = set(excl.pa_id)
    batters = {str(r['batter_id']) for r in rows if pa_of(r) in pas}
    pool = [r for r in rows if pa_of(r) not in pas and str(r['batter_id']) not in batters]
    rng = np.random.default_rng(seed); removed = set()
    for kind, k in (('Take', n_take), ('Swing', n_swing)):
        ids = [r['pitch_id'] for r in pool if r['decision_type'] == kind]
        removed |= set(rng.choice(ids, size=k, replace=False))
kept = [r for r in rows if r['pitch_id'] not in removed]
dates = np.array(sorted({r['game_id'][:8] for r in kept})); out = []
for block in np.array_split(dates, zd.CROSSFIT_FOLDS):
    held = set(block); train = [r for r in kept if r['game_id'][:8] not in held]; test = [r for r in kept if r['game_id'][:8] in held]
    pred = zd.fit_predict(train, test, **zd.SCORE_SETTINGS); pz = old.predict_pzone(train, test, zd.PZONE_ABS)
    out += [{'pitch_id': r['pitch_id'], 'p_swing': float(pred['p'][i]), 'p_zone': float(pz[i])} for i, r in enumerate(test)]
pd.DataFrame(out).to_parquet(W / f'refit_{SEASON}_{tag}.parquet', index=False)
(W / f'refit_{SEASON}_{tag}.removed.json').write_text(json.dumps(sorted(removed)))
print(tag, 'removed', len(removed))
