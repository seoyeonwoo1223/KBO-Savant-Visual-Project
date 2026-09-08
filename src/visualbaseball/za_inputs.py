"""Select and verify the input used by the production Zone Awareness job."""
from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from pathlib import Path

INPUT_MODES = ("legacy", "curated")


@dataclass(frozen=True)
class ZAInput:
    mode: str
    path: Path
    version: str | None
    sha256: str | None


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _safe_version(value: str) -> str:
    if not value or value in {".", ".."} or Path(value).name != value:
        raise ValueError("ZA curated version must be one path-safe directory name")
    return value


def resolve_za_input(root: Path, season: int, mode: str | None = None,
                     version: str | None = None, storage_root: Path | None = None) -> ZAInput:
    """Resolve a ZA input; curated selection is validated and fail-closed."""
    selected = (mode or os.environ.get("ZA_INPUT_MODE") or "legacy").lower()
    if selected not in INPUT_MODES:
        raise ValueError(f"ZA input mode must be one of {INPUT_MODES}, got {selected!r}")
    if selected == "legacy":
        path = ((storage_root or root) / "data/processed/pitches.parquet" if season == 2026 else
                root / "exports" / f"visualbaseball_savant_{season}_latest.xlsx")
        return ZAInput(selected, path, None, None)

    selected_version = _safe_version(version or os.environ.get("ZA_CURATED_VERSION", ""))
    version_root = root / "data/curated/zone_awareness" / selected_version
    manifest_path = version_root / "manifest.json"
    if not manifest_path.is_file():
        raise FileNotFoundError(f"curated ZA manifest is required: {manifest_path}")
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        entry = manifest["seasons"][str(season)]
        relative = Path(entry["path"])
        expected = entry["sha256"].lower()
    except (json.JSONDecodeError, KeyError, TypeError, AttributeError) as error:
        raise ValueError(f"invalid curated ZA manifest: {manifest_path}") from error
    if relative.is_absolute() or ".." in relative.parts:
        raise ValueError("curated manifest input path must remain inside its version directory")
    path = version_root / relative
    if not path.is_file():
        raise FileNotFoundError(f"curated ZA input is missing: {path}")
    actual = _sha256(path)
    if len(expected) != 64 or actual != expected:
        raise ValueError(f"curated ZA checksum mismatch for {path}: expected {expected}, got {actual}")
    return ZAInput(selected, path, selected_version, actual)
