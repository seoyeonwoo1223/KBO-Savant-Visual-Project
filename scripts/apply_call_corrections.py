"""Apply data/corrections/vb_bunt_foul_corrections.json to the committed curated partitions.

    PYTHONPATH=src python scripts/apply_call_corrections.py [--check] [seasons...]

Reparsing raw payloads would also pull unrelated parser changes into older curated seasons, so this rewrites
only the games that need it and, inside them, only these plate appearances:

  * a pitch in the table gets code W (Bunt Foul): not a swing, take, contact or in-play pitch;
  * a plate appearance with VB code V (bunt swing-and-miss) is recounted, since V now adds a strike;
  * balls/strikes before/after and re288 state codes of those plate appearances are recomputed with the
    parser's state rules (GameState.apply_non_terminal_pitch; the last pitch ends at 0-0);
  * the pitch event's code and description follow the pitch.

A plate appearance is skipped (and reported) when its stored counts match neither the old rules (V without a
strike) on the stored codes nor the current rules, or when the stored row no longer matches the table (code,
batter, pitcher, velocity). Rows already corrected are left as they are, so a rerun writes nothing.
Games are written through curated.write_game, which keeps the manifest and partition-index digests in step.
The parser applies the same table (collector.call_corrections), so a later reparse gives the same rows.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from visualbaseball.collector import CALL_CORRECTIONS
from visualbaseball.curated import load_rows, source_manifest_path, value_sha256, write_game
from visualbaseball.parser import _description
from visualbaseball.state_machine import GameState

ROOT = Path(__file__).resolve().parents[1]


def _counts(codes: list[str], v_is_strike: bool = True) -> list[tuple[int, int, int, int]]:
    state, out = GameState(), []
    for i, code in enumerate(codes):
        before = (state.balls, state.strikes)
        if i == len(codes) - 1:
            state.balls = state.strikes = 0
        elif code != "V" or v_is_strike:
            state.apply_non_terminal_pitch(code)
        out.append((*before, state.balls, state.strikes))
    return out


def _stored(row: dict) -> tuple[int, int, int, int]:
    return (int(row["balls_before"]), int(row["strikes_before"]), int(row["balls_after"]), int(row["strikes_after"]))


def correct_game(pitches: list[dict], events: list[dict], fixes: dict[str, dict]) -> tuple[int, int, list[str]]:
    by_pa: dict[str, list[dict]] = {}
    for row in pitches:
        by_pa.setdefault(row["pa_id"], []).append(row)
    event_by_seq = {int(e["event_seq"]): e for e in events if e.get("event_type") == "pitch"}
    applied, recounted, skipped = 0, 0, []
    touched = {r["pa_id"] for r in pitches if r["pitch_id"] in fixes or str(r.get("pitch_call_code") or "").upper() == "V"}
    for pa_id in sorted(touched):
        rows = sorted(by_pa[pa_id], key=lambda r: int(r["pitch_number"]))
        codes = [str(r.get("pitch_call_code") or "").upper() for r in rows]
        stored = [_stored(r) for r in rows]
        if stored != _counts(codes, v_is_strike=False) and stored != _counts(codes):
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
        counts = _counts(new_codes)
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


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("seasons", nargs="*", type=int)
    parser.add_argument("--check", action="store_true", help="report only; write nothing")
    args = parser.parse_args()
    table = json.loads(CALL_CORRECTIONS.read_text(encoding="utf-8"))["seasons"]
    report = {}
    for season in args.seasons or sorted(int(s) for s in table):
        fixes = {row["pitch_id"]: row for row in table.get(str(season), {}).get("pitches", [])}
        codes = load_rows(ROOT, "pitches", season, columns=["game_id", "pitch_call_code"])
        games = sorted({pid.split("-")[0] for pid in fixes} | {r["game_id"] for r in codes if r["pitch_call_code"] == "V"})
        applied, recounted, written, skipped = 0, 0, 0, []
        for game_id in games:
            game = load_rows(ROOT, "games", season, game_id=game_id)
            events = load_rows(ROOT, "events", season, game_id=game_id)
            pitches = load_rows(ROOT, "pitches", season, game_id=game_id)
            n, v, s = correct_game(pitches, events, fixes)
            applied += n; recounted += v; skipped += s
            if (n or v) and not args.check:
                # Pass the raw payload only when the manifest was built from it, so raw_sha256/raw_pitch_count
                # provenance stays as recorded; a raw file that no longer hashes the same is not trusted.
                previous = json.loads(source_manifest_path(ROOT, season, game_id).read_text(encoding="utf-8"))
                payload = None
                if previous.get("raw_sha256"):
                    raw = ROOT / "data" / "raw" / str(season) / f"{game_id}.json"
                    payload = json.loads(raw.read_text(encoding="utf-8-sig")) if raw.exists() else None
                    if payload is None or value_sha256(payload) != previous["raw_sha256"]:
                        skipped.append(f"{game_id}: raw payload differs from the manifest; game not written")
                        applied -= n; recounted -= v
                        continue
                write_game(ROOT, game[0], events, pitches, raw_payload=payload)
                written += 1
        report[season] = {"table": len(fixes), "games_checked": len(games), "W_applied": applied,
                          "PA_recounted": recounted, "games_written": written, "skipped": skipped}
        print(season, json.dumps({k: (len(v) if k == "skipped" else v) for k, v in report[season].items()}), flush=True)
    for season, r in report.items():
        for line in r["skipped"]:
            print("  skip", season, line)


if __name__ == "__main__":
    main()
