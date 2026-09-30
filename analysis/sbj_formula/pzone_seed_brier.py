"""정정 후 p_zone Brier 역전(0.00189 대 0.00238)이 HGB 난수 범위 안인지 확인한다 (읽기 전용).

같은 테이크·같은 3개 날짜 블록에서 운영 p_zone 설정을 random_state만 바꿔 재적합하고,
조기 종료를 끈 적합과 비교한다.  python analysis/sbj_formula/pzone_seed_brier.py 2024
"""
import json
import sys
from pathlib import Path

import numpy as np
import pyarrow.parquet as pq
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.metrics import brier_score_loss, log_loss

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
from visualbaseball.zone_decision import pzone_fields  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
season = int(sys.argv[1]) if len(sys.argv) > 1 else 2024
fields = list(pzone_fields(season))
df = pq.read_table(ROOT / f"data/metrics/zone_awareness/{season}/pitches.parquet",
                   columns=fields + ["game_id", "swing", "event", "fold"]).to_pandas()
tk = df[df.swing == 0].reset_index(drop=True)
X = tk[fields].to_numpy(float); y = (tk.event == "CalledStrike").to_numpy(int); fold = tk.fold.to_numpy()


def oof(seed, early):
    p = np.empty(len(y)); iters = []
    for f in range(3):
        m = HistGradientBoostingClassifier(learning_rate=0.07, max_iter=130, max_leaf_nodes=20, min_samples_leaf=80,
                                           l2_regularization=1.5, random_state=seed, early_stopping=early)
        m.fit(X[fold != f], y[fold != f]); p[fold == f] = m.predict_proba(X[fold == f])[:, 1]; iters.append(int(m.n_iter_))
    p = np.clip(p, 1e-6, 1 - 1e-6)
    return {"seed": seed, "early_stopping": early, "brier": brier_score_loss(y, p), "log_loss": log_loss(y, p), "n_iter": iters}


runs = [oof(s, "auto") for s in range(8)] + [oof(s, False) for s in range(2)]
b = [r["brier"] for r in runs if r["early_stopping"] == "auto"]
out = {"season": season, "takes": len(y), "runs": runs, "auto_brier_range": [min(b), max(b)],
       "note": "OOF over the pitch-evidence fold labels; the take set is the current (post-correction) one."}
dest = Path(__file__).with_name("results"); dest.mkdir(exist_ok=True)
(dest / f"pzone_seed_brier_{season}.json").write_text(json.dumps(out, indent=1) + "\n")
print(json.dumps(out, indent=1))
