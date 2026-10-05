"""Verify and unpack the 2026-10-05 nonimage snapshot with Python stdlib only."""

from pathlib import Path, PurePosixPath
import hashlib
import json
import re
import shutil
import stat
import tempfile
import zipfile


ARCHIVE_NAME = "eaa-nonimage-review-context-20261005.zip"
ARCHIVE_SHA256 = "8d8714ab398fbf0767b33b98570f7f928d3c25a739e4fc1658d1a017cd3313ad"
MANIFEST_NAME = "SNAPSHOT_SHA256.json"
README_NAME = "REVIEW_CONTEXT_README.md"
REPORT_NAME = "analysis/arm_angle/nonimage-expansion-study-20261005.md"
VERIFICATION_NAME = "analysis/arm_angle/results/expanded_nonimage_verification.json"
MAX_UNPACKED_BYTES = 64 * 1024 * 1024
MAX_ENTRIES = 512


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"Duplicate JSON key: {key}")
        result[key] = value
    return result


def verified_payloads(archive, expected_sha256=ARCHIVE_SHA256):
    """Read and verify everything before creating an extraction directory."""
    if hashlib.sha256(archive.read_bytes()).hexdigest() != expected_sha256:
        raise ValueError("Review ZIP SHA-256 does not match the verified snapshot")
    with zipfile.ZipFile(archive) as zipped:
        entries = zipped.infolist()
        names = [entry.filename for entry in entries]
        if not entries or len(entries) > MAX_ENTRIES or len(names) != len(set(names)):
            raise ValueError("Invalid entry count or duplicate ZIP entries")
        if sum(entry.file_size for entry in entries) > MAX_UNPACKED_BYTES:
            raise ValueError("Review ZIP exceeds the extraction size limit")
        for entry in entries:
            name = entry.filename
            relative = PurePosixPath(name)
            mode = entry.external_attr >> 16
            if (
                not name
                or relative.is_absolute()
                or ".." in relative.parts
                or "\\" in name
                or ":" in name
                or str(relative) != name
                or entry.is_dir()
                or stat.S_ISLNK(mode)
                or entry.flag_bits & 1
            ):
                raise ValueError(f"Unsafe ZIP entry: {name}")
        manifest = json.loads(zipped.read(MANIFEST_NAME), object_pairs_hook=unique_object)
        if not isinstance(manifest, dict) or not manifest:
            raise ValueError("Invalid snapshot hash manifest")
        if any(
            not isinstance(digest, str) or re.fullmatch(r"[0-9a-f]{64}", digest) is None
            for digest in manifest.values()
        ):
            raise ValueError("Invalid manifest SHA-256 value")
        if MANIFEST_NAME in manifest or README_NAME in manifest:
            raise ValueError("Metadata entries must be outside the content manifest")
        if set(names) != set(manifest) | {MANIFEST_NAME, README_NAME}:
            raise ValueError("Missing or unexpected ZIP entries")
        if REPORT_NAME not in manifest or VERIFICATION_NAME not in manifest:
            raise ValueError("Missing required review report or verification results")
        payloads = {}
        for name in names:
            data = zipped.read(name)  # zipfile also verifies each entry's CRC.
            if name in manifest and hashlib.sha256(data).hexdigest() != manifest[name]:
                raise ValueError(f"Review entry hash mismatch: {name}")
            payloads[name] = data
    return manifest, payloads


def unpack_verified(archive):
    manifest, payloads = verified_payloads(archive)
    destination = Path(tempfile.mkdtemp(prefix="eaa-nonimage-review-20261005-"))
    try:
        for name, data in payloads.items():
            path = destination / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
        for name, digest in manifest.items():
            if hashlib.sha256((destination / name).read_bytes()).hexdigest() != digest:
                raise ValueError(f"Extracted file hash mismatch: {name}")
    except Exception:
        shutil.rmtree(destination)
        raise
    return destination, len(manifest), len(payloads)


def main():
    packet_dir = Path(__file__).resolve().parent
    destination, content_count, entry_count = unpack_verified(packet_dir / ARCHIVE_NAME)
    print(json.dumps({
        "review_root": str(destination),
        "prompt_path": str(packet_dir.parent / "claude-nonimage-review-prompt-20261005.md"),
        "report_path": str(destination / REPORT_NAME),
        "verification_path": str(destination / VERIFICATION_NAME),
        "manifest_path": str(destination / MANIFEST_NAME),
        "content_files_verified": content_count,
        "entries_extracted": entry_count,
        "archive_sha256": ARCHIVE_SHA256,
        "scope": "Independent review of selected numeric results; full raw pitch and TrackMan caches omitted",
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
