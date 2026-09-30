"""Hold listed plate appearances out of SBJ training AND scoring (read-only experiment).

    python analysis/sbj_location/hold_pa_experiment.py <season> <work dir> <queue csv>

The queue CSV needs a `pa_id` column (e.g. split_dup_queue.csv). Everything else follows
pzone_experiment.py: production eligibility, 3 date-block cross-fit, production fit_predict for
p_swing and production p_zone (za7.2). The baseline is pzone_exp_<season>.parquet from that script.
"""
import json, sys
from pathlib import Path
import numpy as np, pandas as pd
from visualbaseball import zone_decision as zd, plate_decision_v1 as old

ROOT = Path(__file__).resolve().parents[2]
SEASON, W, QUEUE = int(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3])
held_pas = set(pd.read_csv(QUEUE, dtype=str).pa_id)
orig = zd.PSWING_CATEGORICAL; zd.PSWING_CATEGORICAL = orig + ('pitch_id',)
rows, _ = zd.load_rows(ROOT, SEASON); zd.PSWING_CATEGORICAL = orig
pa_of = lambda r: r['pitch_id'].split('-', 1)[1][:-3]
held_rows = [r for r in rows if pa_of(r) in held_pas]
rows = [r for r in rows if pa_of(r) not in held_pas]
dates = np.array(sorted({r['game_id'][:8] for r in rows})); out = []
for block in np.array_split(dates, zd.CROSSFIT_FOLDS):
    held = set(block); train = [r for r in rows if r['game_id'][:8] not in held]; test = [r for r in rows if r['game_id'][:8] in held]
    pred = zd.fit_predict(train, test, **zd.SCORE_SETTINGS)
    pz = old.predict_pzone(train, test, zd.PZONE_ABS)
    out += [{'pitch_id': r['pitch_id'], 'batter_id': str(r['batter_id']), 'swing': int(r['decision_type'] == 'Swing'),
             'p_swing': float(pred['p'][i]), 'p_zone': float(pz[i])} for i, r in enumerate(test)]
new = pd.DataFrame(out)
base = pd.read_parquet(W / f'pzone_exp_{SEASON}.parquet')
za = lambda d, pz: 100 * ((d.swing - d.p_swing) * (2 * d[pz] - 1)).groupby(d.batter_id).mean()
n = base.groupby('batter_id').size(); q = n[n >= 300].index
b, h = za(base, 'B_za72')[q], za(new, 'p_zone').reindex(q); d = h - b
touched = sorted({str(r['batter_id']) for r in held_rows})
res = {'season': SEASON, 'held_pas': len({pa_of(r) for r in held_rows}), 'held_eligible_pitches': len(held_rows),
       'held_takes': sum(r['decision_type'] == 'Take' for r in held_rows), 'qualified_batters': int(len(q)),
       'all_qualified': {'mean_abs_delta': round(float(d.abs().mean()), 4), 'max_abs_delta': round(float(d.abs().max()), 4),
                         'max_rank_shift': int((h.rank() - b.rank()).abs().max()), 'spearman': round(float(b.corr(h, method='spearman')), 5)},
       'touched_batters': [{'batter_id': t, 'name': base.loc[base.batter_id == t, 'batter_name'].iat[0] if (base.batter_id == t).any() else None,
                            'pitches_base': int(n.get(t, 0)), 'za_base': round(float(za(base, 'B_za72').get(t, np.nan)), 4),
                            'za_held': round(float(za(new, 'p_zone').get(t, np.nan)), 4)} for t in touched]}
(W / f'hold_pa_{SEASON}.json').write_text(json.dumps(res, ensure_ascii=False, indent=1))
print(json.dumps(res, ensure_ascii=False, indent=1))
