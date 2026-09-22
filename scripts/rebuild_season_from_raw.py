"""시즌 전체를 retained raw에서 다시 만드는 일회성 스크립트.

`build_curated`의 경기 단위 경로와 같은 `prepare_game` → `write_game` 조합을 쓰되,
월 단위로 `curated.batch_writes()`를 걸어 partition과 index를 월당 한 번만 씁니다.
결과는 경기 단위 실행과 같아야 하며, 검증은 `--verify`가 합니다.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from visualbaseball.collector import prepare_game
from visualbaseball.curated import batch_writes, write_game
from visualbaseball.naver import NaverEnrichment



def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--storage-root", type=Path)
    parser.add_argument("--season", type=int, required=True)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    root = args.root.resolve()
    storage_root = (args.storage_root or args.root).resolve()
    raw_root = storage_root / "data" / "raw" / str(args.season)
    paths = sorted(raw_root.glob("*.json"))
    if not paths:
        raise FileNotFoundError(f"no raw JSON found below {raw_root}")

    by_month: dict[str, list[Path]] = {}
    for path in paths:
        by_month.setdefault(path.stem[4:6], []).append(path)

    changed = pitches = games = 0
    for month in sorted(by_month):
        with batch_writes(root):
            for path in by_month[month]:
                payload = json.loads(path.read_text(encoding="utf-8-sig"))
                game_id = str(payload.get("gameData", {}).get("gameId") or path.stem)
                naver_path = storage_root / "data" / "raw" / "naver" / str(args.season) / f"{game_id}.json"
                enrichment = (NaverEnrichment.from_dict(json.loads(naver_path.read_text(encoding="utf-8")))
                              if naver_path.exists() else None)
                prepared = prepare_game(payload, season=args.season, naver_enrichment=enrichment)
                if not prepared.valid:
                    print(f"skip {game_id}: {prepared.message}")
                    continue
                result = write_game(
                    root, prepared.game, prepared.events, prepared.pitches, raw_payload=payload,
                    provenance={"type": "visualbaseball_json", "path": path.relative_to(storage_root).as_posix()},
                    force=args.force,
                )
                changed += int(result["changed"]); pitches += len(prepared.pitches); games += 1
        print(f"month={month}: {len(by_month[month])} games written", flush=True)
    print(f"rebuilt {games} games, {changed} changed, {pitches} pitches")


if __name__ == "__main__":
    main()
