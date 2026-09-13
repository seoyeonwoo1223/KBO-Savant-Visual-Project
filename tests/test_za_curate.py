import json
from pathlib import Path

from visualbaseball.build_curated import build_curated
from visualbaseball.curated import load_table


ROOT = Path(__file__).parents[1]


def test_raw_build_creates_game_shards_and_provenance(tmp_path):
    raw = tmp_path / "storage/data/raw/2026/20260328HTSK0.json"
    raw.parent.mkdir(parents=True)
    raw.write_bytes((ROOT / "data/raw/2026/20260328HTSK0.json").read_bytes())
    result = build_curated(tmp_path, 2026, storage_root=tmp_path / "storage", validate=True)
    assert result["games"] == result["changed"] == 1
    assert result["pitches"] == 338
    assert load_table(tmp_path, "pitches", 2026).num_rows == 338
    manifest = json.loads((tmp_path / "data/curated/sources/season=2026/20260328HTSK0.json").read_text(encoding="utf-8"))
    assert manifest["raw_pitch_count"] == manifest["curated_pitch_count"] == 338
    assert len(manifest["raw_sha256"]) == len(manifest["pitch_sha256"]) == len(manifest["schema_sha256"]) == 64


def test_unchanged_build_is_a_noop(tmp_path):
    raw = tmp_path / "data/raw/2026/20260328HTSK0.json"
    raw.parent.mkdir(parents=True)
    raw.write_bytes((ROOT / "data/raw/2026/20260328HTSK0.json").read_bytes())
    assert build_curated(tmp_path, 2026)["changed"] == 1
    shard = tmp_path / "data/curated/pitches/season=2026/20260328HTSK0.parquet"
    before = shard.read_bytes()
    assert build_curated(tmp_path, 2026)["changed"] == 0
    assert shard.read_bytes() == before


def _advancing_clock(monkeypatch, module):
    """벽시계를 호출마다 다른 값으로 고정합니다.

    두 실행이 같은 초에 끝나면 타임스탬프가 우연히 같아져 churn이 드러나지 않습니다.
    실제 CI는 몇 시간 간격이므로, 시각이 반드시 달라지는 상황을 만들어 검사합니다.
    """
    stamps = iter(f"2026-09-{day:02d}T00:00:00+00:00" for day in range(1, 28))
    monkeypatch.setattr(module, "utc_now", lambda: next(stamps))


def test_unchanged_build_does_not_rewrite_the_source_manifest(tmp_path, monkeypatch):
    """재수집이 아무것도 바꾸지 않았으면 매니페스트 파일도 그대로여야 합니다.

    last_checked_at만 매번 now로 쓰이던 탓에, 내용이 같은 재수집도 매니페스트를
    바꿔 놓아 CI에 빈 데이터 커밋이 쌓였습니다(옆의 last_collected_at·revision은
    이미 '바뀐 경우에만' 규칙을 지키고 있었습니다).
    """
    from visualbaseball import curated

    _advancing_clock(monkeypatch, curated)
    raw = tmp_path / "data/raw/2026/20260328HTSK0.json"
    raw.parent.mkdir(parents=True)
    raw.write_bytes((ROOT / "data/raw/2026/20260328HTSK0.json").read_bytes())
    assert build_curated(tmp_path, 2026)["changed"] == 1
    manifest = tmp_path / "data/curated/sources/season=2026/20260328HTSK0.json"
    before = manifest.read_bytes()
    assert build_curated(tmp_path, 2026)["changed"] == 0
    assert manifest.read_bytes() == before


def test_unchanged_summary_keeps_its_generated_at(tmp_path, monkeypatch):
    """내용이 같은 요약은 generated_at만 달라져 파일이 바뀌는 일이 없어야 합니다."""
    from visualbaseball import dataset_summary
    from visualbaseball.dataset_summary import build_summary

    raw = tmp_path / "data/raw/2026/20260328HTSK0.json"
    raw.parent.mkdir(parents=True)
    raw.write_bytes((ROOT / "data/raw/2026/20260328HTSK0.json").read_bytes())
    build_curated(tmp_path, 2026)
    _advancing_clock(monkeypatch, dataset_summary)
    summary = build_summary(tmp_path)
    before = summary.read_bytes()
    assert build_summary(tmp_path).read_bytes() == before
