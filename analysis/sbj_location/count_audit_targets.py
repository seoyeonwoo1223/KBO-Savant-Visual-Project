"""List the games whose VB counts cannot be right on VB alone, for naver_count_audit.py (read-only).

    PYTHONPATH=src python analysis/sbj_location/count_audit_targets.py OUT_JSON season [season ...]

A game is listed when it holds a plate appearance with any of:
  * a walk whose last pitch is not ball four, or a strikeout whose last pitch is not strike three;
  * a plate appearance that ends mid-count with no result and another batter next in the same half-inning
    (a pinch hitter or other replacement inherits the count);
  * four balls before the last pitch.
Pitch-clock violations inside a plate appearance that ends in play leave no such trace, so they are only found
when the game is listed for another reason (about 14% in a 2025 sample; docs/sbj-data-quality.md).
OUT_JSON has the layout of results/naver_count_audit_games_2019_2026.json. When it already exists the new games are
added to it and none is removed: games corrected earlier no longer look wrong, but scripts/build_naver_count_corrections.py
rebuilds a season from the audit, so a game dropped from the list would lose its corrections.
"""
from __future__ import annotations

import json, sys
from pathlib import Path

import pandas as pd

from visualbaseball.curated import load_rows

ROOT = Path(__file__).resolve().parents[2]
COLUMNS = ["game_id", "pa_id", "inning", "inning_half", "batter_id", "pitch_call_code", "balls_before", "strikes_before",
           "game_pitch_number", "pa_result"]
STRIKES = ["S", "T", "V", "W"]


def season_games(season: int) -> list[str]:
    p = pd.DataFrame(load_rows(ROOT, "pitches", season, columns=COLUMNS)).sort_values(["game_id", "game_pitch_number"])
    p["code"] = p.pitch_call_code.fillna("").str.upper()
    g = p.groupby("pa_id", sort=False)
    last, first = g.tail(1).set_index("pa_id"), g.head(1).set_index("pa_id")
    balls, strikes, code, result = last.balls_before.astype(int), last.strikes_before.astype(int), last.code, last.pa_result.fillna("")
    walk_bad = (result == "볼넷") & ~((code == "B") & (balls == 3))
    strikeout_bad = (result.eq("삼진") | result.str.contains("낫아웃")) & ~(code.isin(STRIKES) & (strikes == 2))
    same_half_next = ((first.game_id.shift(-1) == first.game_id) & (first.inning.shift(-1) == first.inning)
                      & (first.inning_half.shift(-1) == first.inning_half) & (first.batter_id.shift(-1) != first.batter_id))
    can_end = (code == "X") | ((code == "B") & (balls == 3)) | (code.isin(STRIKES) & (strikes == 2))
    handoff = same_half_next.reindex(last.index).fillna(False) & ~can_end & (result == "")
    four_balls = p.assign(ball=p.code == "B").groupby("pa_id").ball.apply(lambda b: b.iloc[:-1].sum() >= 4)
    flagged = set(last.index[walk_bad | strikeout_bad | handoff]) | set(four_balls[four_balls].index)
    return sorted(p[p.pa_id.isin(flagged)].game_id.unique())


def main() -> None:
    out, seasons = Path(sys.argv[1]), [int(s) for s in sys.argv[2:]]
    previous = json.loads(out.read_text(encoding="utf-8")) if out.exists() else {}
    games = dict(previous.get("games", {}))
    for s in seasons:
        games[str(s)] = sorted(set(games.get(str(s), [])) | set(season_games(s)))
    games = dict(sorted(games.items()))
    out.write_text(json.dumps({"definition": previous.get("definition") or {"targets": __doc__.split("\n\n")[1].strip()},
                               "counts": {s: len(g) for s, g in games.items()}, "games": games},
                              ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print({s: len(g) for s, g in games.items()})


if __name__ == "__main__":
    main()
