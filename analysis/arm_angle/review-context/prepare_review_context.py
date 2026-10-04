"""Verify and unpack the selected eAA review snapshot using only Python stdlib."""
from pathlib import Path, PurePosixPath
import hashlib
import json
import tempfile
import zipfile

ARCHIVE_NAME = "eaa-claude-review-context-20261003.zip"
ARCHIVE_SHA256 = "aa5a482059a238b56b4cf6000ff2b49f738c87dab8b99ba5673d4e44d14dbcee"


def main():
    archive = Path(__file__).resolve().parent / ARCHIVE_NAME
    if hashlib.sha256(archive.read_bytes()).hexdigest() != ARCHIVE_SHA256:
        raise ValueError("Review ZIP SHA-256 does not match the verified snapshot")
    with zipfile.ZipFile(archive) as zipped:
        if zipped.testzip() is not None:
            raise ValueError("Corrupt review ZIP")
        manifest = json.loads(zipped.read("review-manifest.json"))
        expected = set(manifest["files"]) | {"review-manifest.json"}
        names = zipped.namelist()
        if len(names) != len(expected) or set(names) != expected:
            raise ValueError("Unexpected or duplicate ZIP entries")
        payloads = {}
        for name in names:
            relative = PurePosixPath(name)
            if relative.is_absolute() or ".." in relative.parts or "\\" in name:
                raise ValueError("Unsafe ZIP path")
            data = zipped.read(name)
            if name != "review-manifest.json":
                entry = manifest["files"][name]
                if len(data) != entry["bytes"] or hashlib.sha256(data).hexdigest() != entry["sha256"]:
                    raise ValueError(f"Review entry hash mismatch: {name}")
            payloads[name] = data
    destination = Path(tempfile.mkdtemp(prefix="eaa-claude-review-"))
    for name, data in payloads.items():
        path = destination / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    for name, entry in manifest["files"].items():
        if hashlib.sha256((destination / name).read_bytes()).hexdigest() != entry["sha256"]:
            raise ValueError(f"Extracted file hash mismatch: {name}")
    print(json.dumps({
        "review_root": str(destination),
        "prompt_path": str(destination / "analysis/arm_angle/claude-cross-check-prompt.md"),
        "manifest_path": str(destination / "review-manifest.json"),
        "files_verified": len(payloads),
        "archive_sha256": ARCHIVE_SHA256,
        "scope": "Selected review snapshot; full raw data, original videos and runtime dependencies omitted",
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
