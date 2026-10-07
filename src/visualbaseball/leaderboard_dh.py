"""Verify mixed Visual Baseball DH labels against per-PA Naver snapshots."""

from __future__ import annotations

import argparse
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path

from .curated import load_rows
from .naver import NaverSportsClient
from .publish import write_json


POSITION_CODES = {0: "DH", 1: "P", 2: "C", 3: "1B", 4: "2B", 5: "3B",
                  6: "SS", 7: "LF", 8: "CF", 9: "RF"}
COLUMNS = ["game_id", "inning", "inning_half", "batter_id", "batter_name",
           "batter_position", "is_pa_terminal", "pa_id", "event_seq"]


def mixed_dh(position):
    return "지" in str(position or "") and position != "지"


def _group_key(row):
    return int(row["inning"]), row["inning_half"], str(row["batter_id"])


def _fingerprint(rows):
    ordered = sorted(({key: row[key] for key in COLUMNS} for row in rows),
                     key=lambda r: (r["inning_half"], r["event_seq"]))
    return hashlib.sha256(json.dumps(ordered, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def _relay_snapshots(relay, inning):
    snapshots = defaultdict(dict)
    options_by_half = defaultdict(dict)
    for pa in relay.get("textRelays") or []:
        if int(pa.get("inn") or 0) != inning or str(pa.get("homeOrAway")) not in {"0", "1"}:
            continue
        half = "top" if str(pa["homeOrAway"]) == "0" else "bottom"
        for option in pa.get("textOptions") or []:
            options_by_half[half][option["seqno"]] = option
    for half, options in options_by_half.items():
        pending = None
        for seq, option in sorted(options.items()):
            if option.get("ptsPitchId") or option.get("type") in {1, 13}:
                pending = None
            record = option.get("batterRecord") or {}
            # 이닝 시작 문구에도 batterRecord가 붙으므로 타자 소개만 사용합니다.
            if option.get("type") != 8 or not record.get("pcode"):
                continue
            key = inning, half, str(record["pcode"])
            # 수비 교체 뒤 첫 투구 전에 같은 타자 소개가 재방송되는 경우가 있습니다.
            if pending and pending[0] == key:
                previous = snapshots[key][pending[1]]
                if previous.get("name") == record.get("name") and previous.get("pos") == record.get("pos"):
                    del snapshots[key][pending[1]]
            snapshots[key][seq] = record
            pending = key, seq
    return snapshots


def verify_inning(rows, payload, game_id, season, inning):
    """Pair only complete same-batter/half groups; never guess missing PA order."""
    relay = (payload.get("result") or {}).get("textRelayData") or {}
    if relay.get("gameId") != f"{game_id}{season}":
        raise ValueError("네이버 경기 ID가 요청과 다릅니다.")
    snapshots = _relay_snapshots(relay, inning)
    grouped = defaultdict(list)
    for row in rows:
        grouped[_group_key(row)].append(row)
    result = []
    for key, group in sorted(grouped.items()):
        records = [record for _, record in sorted(snapshots[key].items())]
        complete = len(records) == len(group)
        for index, row in enumerate(sorted(group, key=lambda r: r["event_seq"])):
            if not mixed_dh(row["batter_position"]):
                continue
            record = records[index] if complete else {}
            position = POSITION_CODES.get(record.get("pos"))
            status = "matched"
            if not complete:
                status = "pa_count_mismatch"
            elif record.get("name") != row["batter_name"]:
                status = "identity_mismatch"
            elif position is None:
                status = "position_unavailable"
            result.append({"pa_id": row["pa_id"], "player_id": str(row["batter_id"]),
                           "name": row["batter_name"], "vb_position": row["batter_position"],
                           "inning": inning, "half": key[1], "status": status,
                           "position": position if status == "matched" else None,
                           "naver_position": record.get("posName"),
                           "vb_pa_count": len(group), "naver_pa_count": len(records)})
    return result


def refresh_dh(root, season=2026, workers=4, force=False):
    rows = [row for row in load_rows(root, "pitches", season, columns=COLUMNS) if row["is_pa_terminal"]]
    targets = {(r["game_id"], int(r["inning"])) for r in rows if mixed_dh(r["batter_position"])}
    grouped = defaultdict(list)
    for row in rows:
        key = row["game_id"], int(row["inning"])
        if key in targets:
            grouped[key].append(row)
    path = root / "data/leaderboards/source" / f"{season}_dh.json"
    old = json.loads(path.read_text()) if path.exists() else {}
    if old and old.get("season") != season:
        raise ValueError("DH 입력 시즌이 일치하지 않습니다.")
    cached = old.get("innings", {})

    def fetch(item):
        (game_id, inning), group = item
        key = f"{game_id}:{inning}"
        group = sorted(group, key=lambda r: (r["inning_half"], r["event_seq"]))
        fingerprint = _fingerprint(group)
        prior = cached.get(key, {})
        if not force and prior.get("input_sha256") == fingerprint and all(r["status"] == "matched" for r in prior["records"]):
            return key, prior
        endpoint = f"/schedule/games/{game_id}{season}/relay?inning={inning}"
        try:
            client = NaverSportsClient()
            payload = client.get_json(endpoint)
            records = verify_inning(group, payload, game_id, season, inning)
        except (RuntimeError, ValueError) as error:
            print(f"DH 확인 실패 {key}: {error}", flush=True)
            records = [{"pa_id": row["pa_id"], "player_id": str(row["batter_id"]),
                        "name": row["batter_name"], "vb_position": row["batter_position"],
                        "inning": inning, "half": row["inning_half"],
                        "status": "unavailable", "position": None}
                       for row in group if mixed_dh(row["batter_position"])]
        return key, {"input_sha256": fingerprint, "source_url": NaverSportsClient.base_url + endpoint,
                     "records": records}

    with ThreadPoolExecutor(max_workers=workers) as pool:
        innings = dict(pool.map(fetch, sorted(grouped.items())))
    path.parent.mkdir(parents=True, exist_ok=True)
    write_json(path, {"schema_version": 1, "season": season, "scope": "vb_mixed_dh",
                      "innings": dict(sorted(innings.items()))}, compact=False)
    return path


def load_verifications(root, season, terminal_rows=None):
    path = root / "data/leaderboards/source" / f"{season}_dh.json"
    if not path.exists():
        return {}
    payload = json.loads(path.read_text())
    if payload.get("season") != season or payload.get("scope") != "vb_mixed_dh":
        raise ValueError("DH 입력의 시즌·검증 범위가 일치하지 않습니다.")
    result = {}
    grouped = defaultdict(list)
    if terminal_rows is not None:
        for row in terminal_rows:
            grouped[f"{row['game_id']}:{int(row['inning'])}"].append(row)
    for key, entry in payload["innings"].items():
        if terminal_rows is not None and _fingerprint(grouped[key]) != entry["input_sha256"]:
            continue
        for row in entry["records"]:
            if row["pa_id"] in result:
                raise ValueError("DH 입력 타석이 중복되었습니다.")
            result[row["pa_id"]] = row
    return result


def confirmed_position(row, verification):
    if not verification or verification.get("status") != "matched":
        return None
    expected = {"player_id": str(row.batter_id), "name": row.batter_name,
                "vb_position": row.batter_position, "inning": int(row.inning), "half": row.inning_half}
    if any(verification.get(key) != value for key, value in expected.items()):
        return None
    return verification.get("position")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--season", type=int, default=2026)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    print(refresh_dh(args.root, args.season, args.workers, args.force))


if __name__ == "__main__":
    main()
