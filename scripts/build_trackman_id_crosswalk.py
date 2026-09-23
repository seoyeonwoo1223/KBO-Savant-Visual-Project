"""Derive a TrackMan -> Visual Baseball player ID crosswalk from pitches both sources record.

Some players carry a different ID in TrackMan (six-digit IDs such as 658792), so the
same-season string join in player_id_overlap.json silently drops them. This aligns
pitches game by game and accepts a pair only when the aligned pitches agree on count
and outs (a check that does not use the IDs), the pair has enough support, and it is
one-to-one in both directions. Nothing here rewrites TrackMan or Visual Baseball values.
"""
from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path
from uuid import uuid4

import pandas as pd

from visualbaseball.curated import load_rows

GAME_MIN_JACCARD = 0.6      # same-date pitcher-set overlap needed to pair two games
GAME_MAX_RUNNER_UP = 0.3    # and no second candidate may come close
MIN_SUPPORT = 20            # aligned pitches behind an accepted pair
MIN_SHARE = 0.9             # share of the ID's aligned pitches, checked in both directions
ROLES = {"pitcher": ("pitcher_trackman_id", "pitcher_id"), "batter": ("batter_trackman_id", "batter_id")}


def _write_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + f".{uuid4().hex}.tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def _trackman(root: Path, season: int) -> pd.DataFrame:
    frame = pd.read_csv(root / "data" / "tracking" / "raw" / f"season={season}" / "trackman_history.csv", dtype=str)
    frame = frame[~frame["pitcher_team"].fillna("").str.startswith("MIN_")].copy()  # KBO games only
    frame["date"] = pd.to_datetime(frame["game_date"], format="mixed").dt.strftime("%Y%m%d")  # 2019-21 use MM/DD/YYYY
    frame["half"] = frame["top_bottom"].str.lower().str.startswith("t").map({True: "top", False: "bottom"})
    for column in ("inning", "pitch_no", "pitch_of_pa", "balls_before", "strikes_before", "outs_before"):
        frame[column] = pd.to_numeric(frame[column])
    return frame.dropna(subset=["inning", "pitch_no", "pitch_of_pa"])


def _visualbaseball(root: Path, season: int) -> pd.DataFrame:
    columns = ["pitch_id", "game_id", "inning", "inning_half", "pitcher_id", "pitcher_name", "batter_id",
               "batter_name", "balls_before", "strikes_before", "outs_before"]
    frame = pd.DataFrame(load_rows(root, "pitches", season, columns=columns))
    parts = frame["pitch_id"].astype(str).str.split("-")
    frame["pa_seq"] = pd.to_numeric(parts.str[-2], errors="coerce")
    frame["pitch_of_pa"] = pd.to_numeric(parts.str[-1], errors="coerce")
    frame["date"] = frame["game_id"].str[:8]
    frame["half"] = frame["inning_half"].astype(str).str.lower()
    for column in ("pitcher_id", "batter_id"):
        frame[column] = frame[column].astype(str)
    return frame.dropna(subset=["pa_seq", "pitch_of_pa"])


def map_games(trackman: pd.DataFrame, visualbaseball: pd.DataFrame) -> dict[str, str]:
    """Pair games by same-date pitcher sets; drop ambiguous or doubly claimed games."""
    vb_games = visualbaseball.groupby("game_id").agg(date=("date", "first"), pitchers=("pitcher_id", frozenset))
    by_date = defaultdict(list)
    for game_id, row in vb_games.iterrows():
        by_date[row.date].append((game_id, row.pitchers))
    pairs = {}
    for game_id, rows in trackman.groupby("trackman_game_id"):
        pitchers = frozenset(rows["pitcher_trackman_id"])
        scores = sorted(((len(pitchers & other) / len(pitchers | other), vb_id)
                         for vb_id, other in by_date.get(rows["date"].iat[0], [])), reverse=True)
        if scores and scores[0][0] >= GAME_MIN_JACCARD and (len(scores) == 1 or scores[1][0] < GAME_MAX_RUNNER_UP):
            pairs[game_id] = scores[0][1]
    claimed = pd.Series(pairs).value_counts()
    return {tm: vb for tm, vb in pairs.items() if claimed[vb] == 1}


def align_pitches(trackman: pd.DataFrame, visualbaseball: pd.DataFrame, games: dict[str, str]) -> pd.DataFrame:
    """Match the k-th plate appearance of each half inning and the n-th pitch within it."""
    tm = trackman[trackman["trackman_game_id"].isin(games)].copy()
    tm["game_id"] = tm["trackman_game_id"].map(games)
    tm = tm.sort_values(["game_id", "pitch_no"])
    new_pa = (tm["pitch_of_pa"] == 1) | (tm["batter_trackman_id"] != tm["batter_trackman_id"].shift()) | (tm["game_id"] != tm["game_id"].shift())
    tm["pa_index"] = new_pa.cumsum()
    tm["pa_order"] = tm.groupby(["game_id", "inning", "half"])["pa_index"].rank(method="dense")
    vb = visualbaseball[visualbaseball["game_id"].isin(set(games.values()))].copy()
    vb["pa_order"] = vb.groupby(["game_id", "inning", "half"])["pa_seq"].rank(method="dense")
    key = ["game_id", "inning", "half", "pa_order", "pitch_of_pa"]
    merged = tm.merge(vb, on=key, suffixes=("_tm", "_vb"))
    # The state check uses no IDs, so it can vouch for the alignment independently of the crosswalk.
    state = ["balls_before", "strikes_before", "outs_before"]
    merged["state_agrees"] = (merged[[f"{c}_tm" for c in state]].to_numpy() == merged[[f"{c}_vb" for c in state]].to_numpy()).all(axis=1)
    return merged


def accept_pairs(counts: dict[tuple[str, str], int]) -> tuple[list[dict], list[dict]]:
    """Accept (TrackMan ID, VB ID) pairs that dominate both IDs' aligned pitches."""
    by_tm, by_vb = defaultdict(int), defaultdict(int)
    for (tm, vb), n in counts.items():
        by_tm[tm] += n
        by_vb[vb] += n
    best = {}
    for (tm, vb), n in counts.items():
        if n > best.get(tm, ("", 0))[1]:
            best[tm] = (vb, n)
    accepted, rejected = [], []
    for tm, (vb, n) in sorted(best.items(), key=lambda item: int(item[0]) if item[0].isdigit() else item[0]):
        entry = {"trackman_id": tm, "visualbaseball_id": vb, "support": n,
                 "share": round(n / by_tm[tm], 4), "reverse_share": round(n / by_vb[vb], 4), "same_id": tm == vb}
        reasons = [reason for reason, failed in (("support", n < MIN_SUPPORT), ("share", n / by_tm[tm] < MIN_SHARE),
                                                 ("reverse_share", n / by_vb[vb] < MIN_SHARE)) if failed]
        (rejected if reasons else accepted).append({**entry, **({"reasons": reasons} if reasons else {})})
    # One VB ID may not absorb two TrackMan IDs.
    owners = defaultdict(list)
    for entry in accepted:
        owners[entry["visualbaseball_id"]].append(entry)
    for entries in owners.values():
        if len(entries) > 1:
            for entry in entries:
                accepted.remove(entry)
                rejected.append({**entry, "reasons": ["many_to_one"]})
    return accepted, rejected


def build_season(root: Path, season: int) -> dict:
    trackman, visualbaseball = _trackman(root, season), _visualbaseball(root, season)
    games = map_games(trackman, visualbaseball)
    aligned = align_pitches(trackman, visualbaseball, games)
    trusted = aligned[aligned["state_agrees"]]
    entry = {"trackman_games": int(trackman["trackman_game_id"].nunique()), "mapped_games": len(games),
             "aligned_pitches": len(aligned), "state_agreeing_pitches": len(trusted), "roles": {}}
    for role, (tm_column, vb_column) in ROLES.items():
        counts = trusted.groupby([tm_column, vb_column]).size().to_dict()
        accepted, rejected = accept_pairs({(str(tm), str(vb)): int(n) for (tm, vb), n in counts.items()})
        names = trusted.groupby(vb_column)[f"{role}_name"].agg(lambda s: s.mode().iat[0]).to_dict()
        for item in accepted + rejected:
            item["visualbaseball_name"] = names.get(item["visualbaseball_id"])
        lookup = {item["trackman_id"]: item["visualbaseball_id"] for item in accepted}
        tm_ids = trackman[tm_column].astype(str)
        resolved = tm_ids.map(lookup)
        in_vb = set(visualbaseball[vb_column])
        entry["roles"][role] = {
            "accepted_pairs": len(accepted),
            "accepted_different_id": sum(not item["same_id"] for item in accepted),
            "rejected": len(rejected),
            # Coverage over every KBO TrackMan pitch, not only the aligned ones.
            "trackman_pitches": len(tm_ids),
            "pitches_resolved_by_crosswalk": int(resolved.notna().sum()),
            "pitches_resolved_by_string_equality": int(tm_ids.isin(in_vb).sum()),
            "pitches_where_equality_and_crosswalk_disagree": int(((tm_ids.isin(in_vb)) & resolved.notna() & (resolved != tm_ids)).sum()),
            # Lookup order for consumers: an accepted pair, else same-season string equality.
            "pitches_resolved_by_crosswalk_or_equality": int((resolved.notna() | tm_ids.isin(in_vb)).sum()),
            "pairs": accepted,
            "rejected_pairs": rejected,
        }
    return entry


def build(root: Path, seasons: list[int] | None = None) -> dict:
    summary = json.loads((root / "data" / "tracking" / "summary.json").read_text(encoding="utf-8"))
    seasons = seasons or sorted(int(season) for season in summary["seasons"])
    result = {"schema_version": 1,
              "rule": {"games": f"same date, pitcher-set Jaccard >= {GAME_MIN_JACCARD}, runner-up < {GAME_MAX_RUNNER_UP}, one-to-one",
                       "pitches": "k-th plate appearance of the half inning and n-th pitch of the plate appearance",
                       "trusted_pitches": "balls, strikes and outs before the pitch agree",
                       "pairs": f"support >= {MIN_SUPPORT} and share >= {MIN_SHARE} in both directions, one-to-one"},
              "seasons": {}}
    for season in seasons:
        entry = build_season(root, season)
        entry["trackman_sha256"] = summary["seasons"][str(season)]["sha256"]
        result["seasons"][str(season)] = entry
    _write_json(root / "data" / "tracking" / "player_id_crosswalk.json", result)
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--seasons", nargs="*", type=int)
    args = parser.parse_args()
    result = build(args.root.resolve(), args.seasons)
    for season, entry in result["seasons"].items():
        roles = {role: {k: v for k, v in values.items() if k not in ("pairs", "rejected_pairs")} for role, values in entry["roles"].items()}
        print(season, json.dumps({k: v for k, v in entry.items() if k != "roles"}), json.dumps(roles, ensure_ascii=False))


if __name__ == "__main__":
    main()
