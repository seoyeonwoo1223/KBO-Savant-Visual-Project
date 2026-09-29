"""Apply data/corrections/vb_bunt_foul_corrections.json and vb_count_corrections.json to the committed curated partitions.

    PYTHONPATH=src python scripts/apply_call_corrections.py [--check] [seasons...]

Reparsing raw payloads would also pull unrelated parser changes into older curated seasons, so this rewrites
only the games that need it and, inside them, only these plate appearances:

  * a pitch in the table gets code W (Bunt Foul): not a swing, take, contact or in-play pitch;
  * a plate appearance with VB code V (bunt swing-and-miss) is recounted, since V now adds a strike;
  * balls/strikes before/after and re288 state codes of those plate appearances are recomputed with the
    parser's state rules (GameState.apply_non_terminal_pitch; the last pitch ends at 0-0);
  * the pitch event's code and description follow the pitch;
  * a plate appearance in the count table (data/corrections/vb_count_corrections.json) is recounted from its
    `start` count (a count the pinch hitter inherits) with its `inserts` (pitch-clock violations: a ball or
    strike before the listed pitch) when its batter, pitcher and pitch codes still match the table row.

A plate appearance is skipped (and reported) when its stored counts match neither the old rules (V without a
strike) on the stored codes nor the current rules, or when the stored row no longer matches the table (code,
batter, pitcher, velocity). Rows already corrected are left as they are, so a rerun writes nothing.
Games are written through curated.write_game, which keeps the manifest and partition-index digests in step.
write_game rewrites a whole monthly partition (and the partition index) for every game, so games are processed
one month at a time with those writes deferred (BatchedWrites): each monthly file, manifest and the index is
written once per month, after all its games, in the order data -> manifests -> index.
The parser applies the same table (collector.call_corrections), so a later reparse gives the same rows.
"""
from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path

import pyarrow.parquet as pq

from visualbaseball import curated

from visualbaseball.collector import CALL_CORRECTIONS, COUNT_CORRECTIONS
from visualbaseball.curated import load_rows, source_manifest_path, value_sha256
from visualbaseball.parser import _description
from visualbaseball.state_machine import GameState

ROOT = Path(__file__).resolve().parents[1]


def _counts(codes: list[str], v_is_strike: bool = True, fix: dict | None = None) -> list[tuple[int, int, int, int]]:
    """Parser counts for one plate appearance; `fix` is a count-table row (start count and inserted calls)."""
    state, out = GameState(), []
    state.balls, state.strikes = (fix or {}).get("start", (0, 0))
    inserted = {int(i["before_pitch"]): i["code"] for i in (fix or {}).get("inserts", [])}
    for i, code in enumerate(codes):
        if i + 1 in inserted:
            state.apply_non_terminal_pitch(inserted[i + 1])
        before = (state.balls, state.strikes)
        if i == len(codes) - 1:
            state.balls = state.strikes = 0
        elif code != "V" or v_is_strike:
            state.apply_non_terminal_pitch(code)
        out.append((*before, state.balls, state.strikes))
    return out


def _stored(row: dict) -> tuple[int, int, int, int]:
    return (int(row["balls_before"]), int(row["strikes_before"]), int(row["balls_after"]), int(row["strikes_after"]))


def count_fix_matches(fix: dict, rows: list[dict], codes: list[str]) -> bool:
    return str(rows[0]["batter_id"]) == fix["batter_id"] and str(rows[0]["pitcher_id"]) == fix["pitcher_id"] and "".join(codes) == fix["source_codes"]


def correct_game(pitches: list[dict], events: list[dict], fixes: dict[str, dict], count_fixes: dict[str, dict] | None = None) -> tuple[int, int, list[str]]:
    by_pa: dict[str, list[dict]] = {}
    for row in pitches:
        by_pa.setdefault(row["pa_id"], []).append(row)
    event_by_seq = {int(e["event_seq"]): e for e in events if e.get("event_type") == "pitch"}
    applied, recounted, skipped = 0, 0, []
    count_fixes = count_fixes or {}
    touched = {r["pa_id"] for r in pitches if r["pitch_id"] in fixes or str(r.get("pitch_call_code") or "").upper() == "V"
               or r["pa_id"] in count_fixes}
    for pa_id in sorted(touched):
        rows = sorted(by_pa[pa_id], key=lambda r: int(r["pitch_number"]))
        codes = [str(r.get("pitch_call_code") or "").upper() for r in rows]
        stored = [_stored(r) for r in rows]
        count_fix = count_fixes.get(pa_id)
        if stored not in (_counts(codes, v_is_strike=False), _counts(codes), _counts(codes, fix=count_fix)):
            skipped.append(f"{pa_id}: stored counts differ from parser rules")
            continue
        new_codes, targets = list(codes), []
        for i, r in enumerate(rows):
            fix = fixes.get(r["pitch_id"])
            if not fix or codes[i] == fix["code"]:
                continue
            if codes[i] != fix["source_code"] or str(r["batter_id"]) != fix["batter_id"] or str(r["pitcher_id"]) != fix["pitcher_id"] \
                    or float(r["velocity_kmh"]) != float(fix["source_velocity_kmh"]):
                skipped.append(f"{r['pitch_id']}: stored row no longer matches the table")
                continue
            new_codes[i] = fix["code"]; targets.append(i)
        if count_fix and not count_fix_matches(count_fix, rows, new_codes):
            skipped.append(f"{pa_id}: stored plate appearance no longer matches the count table")
            count_fix = None
        counts = _counts(new_codes, fix=count_fix)
        if counts == stored and not targets:
            continue
        recounted += counts != stored
        for i, r in enumerate(rows):
            b0, s0, b1, s1 = counts[i]
            r.update(balls_before=b0, strikes_before=s0, balls_after=b1, strikes_after=s1)
            r["re288_state_code_before"] = (int(r["re24_state_code_before"]) * 4 + b0) * 3 + s0
            r["re288_state_code_after"] = (int(r["re24_state_code_after"]) * 4 + b1) * 3 + s1
        for i in targets:
            r, code = rows[i], new_codes[i]
            text = _description(code, str(r.get("pa_result") or ""))
            r.update(pitch_call_code=code, pitch_result=text, description=text,
                     is_swing=False, is_take=False, is_contact=False, is_in_play=False)
            event = event_by_seq.get(int(r["event_seq"]))
            if event is not None:
                event.update(event_code=code, description=text)
            applied += 1
    return applied, recounted, skipped


def raw_payload_for(root: Path, season: int, game_id: str, manifest: dict) -> tuple[dict | None, str | None]:
    """The raw payload the manifest was built from, or an error when it cannot be found unchanged.

    2025 keeps its raw payloads under seasons/2025 (collected with --storage-root seasons/2025), so both
    locations are tried and the one whose value_sha256 matches the manifest is used.
    """
    if not manifest.get("raw_sha256"):
        return None, None
    candidates = [root / "data" / "raw" / str(season) / f"{game_id}.json",
                  root / "seasons" / str(season) / "data" / "raw" / str(season) / f"{game_id}.json"]
    for path in candidates:
        if path.exists():
            payload = json.loads(path.read_text(encoding="utf-8-sig"))
            if value_sha256(payload) == manifest["raw_sha256"]:
                return payload, None
    return None, f"{game_id}: no raw payload matches the manifest raw_sha256; game not written"


class BatchedWrites:
    """Defer write_game's file writes so each monthly partition is rewritten once, not once per game.

    Inside the block write_game runs unchanged, but its Parquet/JSON writes land in memory and the monthly
    replace works on the cached month. flush() writes data files first, then manifests, then the index.
    """

    def __init__(self, root: Path):
        self.root = root

    def __enter__(self) -> "BatchedWrites":
        self._saved = (curated._atomic_parquet, curated._atomic_json, curated._partition_index, curated._replace_monthly_game)
        self.index = curated._partition_index(self.root)
        self.tables: dict[Path, tuple[list[dict], object]] = {}
        self.dirty: set[Path] = set()
        self.json: dict[Path, object] = {}
        curated._atomic_parquet = self._parquet
        curated._atomic_json = lambda path, value: self.json.__setitem__(Path(path), value)
        curated._partition_index = lambda root: self.index
        curated._replace_monthly_game = self._replace_monthly
        return self

    def __exit__(self, *exc) -> None:
        (curated._atomic_parquet, curated._atomic_json, curated._partition_index, curated._replace_monthly_game) = self._saved

    def month_rows(self, kind: str, season: int, month: str) -> list[dict]:
        path = curated._monthly_path(self.root, kind, season, month)
        if path not in self.tables:
            self.tables[path] = (pq.ParquetFile(path).read().to_pylist() if path.exists() else [], curated.SCHEMAS[kind])
        return self.tables[path][0]

    def _parquet(self, path, rows, schema) -> None:
        self.tables[Path(path)] = (list(rows), schema); self.dirty.add(Path(path))

    def _replace_monthly(self, root, kind, season, month, game_id, rows, schema) -> None:
        old = self.month_rows(kind, season, month)
        self._parquet(curated._monthly_path(root, kind, season, month), [r for r in old if str(r.get("game_id")) != game_id] + rows, schema)

    def flush(self) -> None:
        write_parquet, write_json = self._saved[0], self._saved[1]
        for path in sorted(self.dirty):
            write_parquet(path, *self.tables[path])
        index_path = curated.partition_index_path(self.root)
        for path, value in sorted(self.json.items()):
            if path != index_path:
                write_json(path, value)
        if index_path in self.json:
            write_json(index_path, self.json[index_path])
        self.tables.clear(); self.dirty.clear(); self.json.clear()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("seasons", nargs="*", type=int)
    parser.add_argument("--check", action="store_true", help="report only; write nothing")
    parser.add_argument("--root", type=Path, default=ROOT, help="repository root holding data/curated (default: this checkout)")
    args = parser.parse_args()
    root = args.root
    table = json.loads(CALL_CORRECTIONS.read_text(encoding="utf-8"))["seasons"]
    count_table = json.loads(COUNT_CORRECTIONS.read_text(encoding="utf-8"))["seasons"] if COUNT_CORRECTIONS.exists() else {}
    report = {}
    for season in args.seasons or sorted(int(s) for s in table):
        fixes = {row["pitch_id"]: row for row in table.get(str(season), {}).get("pitches", [])}
        count_fixes = {row["pa_id"]: row for row in count_table.get(str(season), {}).get("pas", [])}
        codes = load_rows(root, "pitches", season, columns=["game_id", "pitch_call_code"])
        games = sorted({pid.split("-")[0] for pid in fixes} | {r["game_id"] for r in codes if r["pitch_call_code"] == "V"}
                       | {pa.split("-")[0] for pa in count_fixes})
        applied, recounted, written, skipped = 0, 0, 0, []
        with BatchedWrites(root) as batch:
            compact = curated._season_is_compact(root, batch.index, season)
            entries = batch.index.get("seasons", {}).get(str(season), {}).get("games", {})
            by_month: dict[str, list[str]] = defaultdict(list)
            for game_id in games:
                by_month[str(entries.get(game_id, {}).get("month") or game_id[4:6]) if compact else ""].append(game_id)
            for month, month_games in sorted(by_month.items()):
                if compact:
                    grouped = {kind: defaultdict(list) for kind in ("games", "events", "pitches")}
                    for kind in grouped:
                        for row in batch.month_rows(kind, season, month):
                            grouped[kind][str(row["game_id"])].append(row)
                for game_id in month_games:
                    if compact:
                        game, events, pitches = (list(grouped[k][game_id]) for k in ("games", "events", "pitches"))
                        if not game:
                            raise FileNotFoundError(f"{game_id} is not in month={month} of season {season}")
                    else:
                        game, events, pitches = (load_rows(root, k, season, game_id=game_id) for k in ("games", "events", "pitches"))
                    n, v, s = correct_game(pitches, events, fixes, count_fixes)
                    skipped += s
                    if not (n or v):
                        continue
                    # Pass the raw payload only when the manifest was built from it, so raw_sha256/raw_pitch_count
                    # provenance stays as recorded; checked in --check too, so a dry run shows what a write would skip.
                    previous = json.loads(source_manifest_path(root, season, game_id).read_text(encoding="utf-8"))
                    payload, error = raw_payload_for(root, season, game_id, previous)
                    if error:
                        skipped.append(error)
                        continue
                    applied += n; recounted += v
                    if not args.check:
                        curated.write_game(root, game[0], events, pitches, raw_payload=payload)
                        written += 1
                if not args.check:
                    batch.flush()
        report[season] = {"table": len(fixes), "count_table": len(count_fixes), "games_checked": len(games), "W_applied": applied,
                          "PA_recounted": recounted, "games_written": written, "skipped": skipped}
        print(season, json.dumps({k: (len(v) if k == "skipped" else v) for k, v in report[season].items()}), flush=True)
    for season, r in report.items():
        for line in r["skipped"]:
            print("  skip", season, line)
    if any(r["skipped"] for r in report.values()):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
