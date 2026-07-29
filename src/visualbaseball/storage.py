from __future__ import annotations

import json
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq


class Store:
    def __init__(self, root: Path):
        self.root = root
        self.processed = root / "data" / "processed"
        self.manifest_path = root / "data" / "manifest.json"
        self.raw_root = root / "data" / "raw"

    def manifest(self) -> dict:
        if self.manifest_path.exists(): return json.loads(self.manifest_path.read_text(encoding="utf-8"))
        return {"games": {}}

    def save_manifest(self, manifest: dict) -> None:
        self.manifest_path.parent.mkdir(parents=True, exist_ok=True)
        self.manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    def raw_path(self, season: int, game_id: str) -> Path:
        return self.raw_root / str(season) / f"{game_id}.json"

    def write_raw(self, season: int, game_id: str, payload: dict) -> Path:
        path = self.raw_path(season, game_id); path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        return path

    def should_fetch(self, game_id: str, game_date: str, recheck_days: int = 2) -> bool:
        entry = self.manifest()["games"].get(game_id)
        if not entry or entry.get("status") != "completed":
            return True
        saved_path = Path(entry.get("raw_path", ""))
        raw_path = saved_path if saved_path.is_absolute() else self.root / saved_path
        # Older manifests stored a machine-specific absolute path. The repository
        # cache is portable, so recover it by game ID when running in Actions.
        if not raw_path.exists():
            raw_path = self.raw_path(int(game_date[:4]), game_id)
        if not raw_path.exists():
            return True
        # Recent final games are deliberately rechecked because source corrections are possible.
        from datetime import date
        return (date.today() - date.fromisoformat(game_date)).days <= recheck_days

    def replace_game(self, game: dict, events: list[dict], pitches: list[dict]) -> None:
        self.replace_games([game], events, pitches)

    def replace_games(self, games: list[dict], events: list[dict], pitches: list[dict]) -> None:
        if not games:
            return
        self.processed.mkdir(parents=True, exist_ok=True)
        game_ids = {game["game_id"] for game in games}
        for name, rows, key in (("games", games, "game_id"), ("events", events, "game_id"), ("pitches", pitches, "game_id")):
            path = self.processed / f"{name}.parquet"; old = pq.read_table(path).to_pylist() if path.exists() else []
            combined = [row for row in old if row.get(key) not in game_ids] + rows
            pq.write_table(pa.Table.from_pylist(combined), path)

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
