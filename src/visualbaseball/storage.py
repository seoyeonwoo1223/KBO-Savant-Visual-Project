from __future__ import annotations

import json
from pathlib import Path

from .curated import audit_raw_replacement, value_sha256, write_game


class Store:
    def __init__(self, root: Path, curated_root: Path | None = None):
        self.root = root
        self.curated_root = curated_root or root
        self.manifest_path = root / "data" / "manifest.json"
        self.raw_root = root / "data" / "raw"

    def manifest(self) -> dict:
        if self.manifest_path.exists(): return json.loads(self.manifest_path.read_text(encoding="utf-8"))
        return {"games": {}}

    def save_manifest(self, manifest: dict) -> None:
        self.manifest_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.manifest_path.with_suffix(".json.tmp")
        temporary.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        temporary.replace(self.manifest_path)

    def raw_path(self, season: int, game_id: str) -> Path:
        return self.raw_root / str(season) / f"{game_id}.json"

    def naver_path(self, season: int, game_id: str) -> Path:
        return self.raw_root / "naver" / str(season) / f"{game_id}.json"

    def write_raw(self, season: int, game_id: str, payload: dict) -> Path:
        path = self.raw_path(season, game_id); path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists():
            previous = json.loads(path.read_text(encoding="utf-8-sig"))
            if value_sha256(previous) == value_sha256(payload):
                return path
            # Audit is durable before the source snapshot is replaced.
            audit_raw_replacement(self.curated_root, season, game_id, previous, payload)
        temporary = path.with_suffix(".json.tmp")
        temporary.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        temporary.replace(path)
        return path

    def write_naver(self, season: int, game_id: str, payload: dict) -> Path:
        path = self.naver_path(season, game_id); path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(".json.tmp")
        temporary.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        temporary.replace(path)
        return path

    def read_naver(self, season: int, game_id: str) -> dict | None:
        path = self.naver_path(season, game_id)
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None

    def should_fetch(self, game_id: str, game_date: str, recheck_days: int = 7) -> bool:
        entry = self.manifest()["games"].get(game_id)
        if not entry or entry.get("status") != "completed":
            return True
        saved_path = Path(entry.get("raw_path", ""))
        raw_path = saved_path if saved_path.is_absolute() else self.root / saved_path
        if not raw_path.exists():
            raw_path = self.raw_path(int(game_date[:4]), game_id)
        if not raw_path.exists():
            return True
        from datetime import date
        return (date.today() - date.fromisoformat(game_date)).days <= recheck_days

    def replace_game(self, game: dict, events: list[dict], pitches: list[dict]) -> int:
        return self.replace_games([game], events, pitches)

    def replace_games(self, games: list[dict], events: list[dict], pitches: list[dict]) -> int:
        if not games:
            return 0
        events_by_game = {game["game_id"]: [] for game in games}
        pitches_by_game = {game["game_id"]: [] for game in games}
        for event in events:
            if event.get("game_id") in events_by_game:
                events_by_game[event["game_id"]].append(event)
        for pitch in pitches:
            if pitch.get("game_id") in pitches_by_game:
                pitches_by_game[pitch["game_id"]].append(pitch)
        changed = 0
        for game in games:
            game_id, season = game["game_id"], int(game["season"])
            raw_path = self.raw_path(season, game_id)
            raw_payload = json.loads(raw_path.read_text(encoding="utf-8-sig")) if raw_path.exists() else None
            result = write_game(
                self.curated_root, game, events_by_game[game_id], pitches_by_game[game_id],
                raw_payload=raw_payload,
                provenance={"type": "visualbaseball_json", "path": raw_path.relative_to(self.root).as_posix()},
            )
            changed += int(result["changed"])
        return changed

    def mark(self, game_id: str, status: str, raw_path: Path | None = None, message: str = "") -> None:
        manifest = self.manifest(); entry = manifest["games"].setdefault(game_id, {})
        relative_path = ""
        if raw_path:
            try:
                relative_path = raw_path.resolve().relative_to(self.root.resolve()).as_posix()
            except ValueError:
                relative_path = str(raw_path)
        entry.update({"status": status, "raw_path": relative_path or entry.get("raw_path", ""), "message": message})
        self.save_manifest(manifest)
