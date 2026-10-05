"""얼린 파일 제약: 팔각도 모델·검증 결과에 sha256이 고정된 소스는 바뀌면 안 됩니다.

이 파일들이 바뀌면 data/models/estimated_arm_angle_v1.json과 analysis/arm_angle/results/*.json에
기록된 구현 hash와 어긋나 eAA 재현성 근거가 사라집니다(docs/decisions/0010-frozen-files.md).
정말 바꿔야 한다면 모델·결과를 재생성해 hash를 갱신하고 결정 기록을 남깁니다.
"""
import hashlib
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
FROZEN = ["curated.py", "vb_arm_angle.py", "arm_angle_calibration.py", "trackman_arm_angle.py"]
PIN_FILES = [ROOT / "data" / "models" / "estimated_arm_angle_v1.json",
             *sorted((ROOT / "analysis" / "arm_angle" / "results").glob("*.json"))]


def _hashes(path: Path) -> set[str]:
    data = path.read_bytes()
    return {hashlib.sha256(data).hexdigest(), hashlib.sha256(data.replace(b"\r\n", b"\n")).hexdigest()}


@pytest.mark.parametrize("name", FROZEN)
def test_frozen_source_matches_pinned_hash(name):
    pins = "\n".join(path.read_text(encoding="utf-8") for path in PIN_FILES)
    assert any(digest in pins for digest in _hashes(ROOT / "src" / "visualbaseball" / name)), (
        f"얼린 파일 src/visualbaseball/{name}이 바뀌어 팔각도 모델·결과에 고정된 sha256과 다릅니다. "
        "되돌리거나, 의도한 변경이면 모델·결과를 재생성하고 docs/decisions/에 기록하세요.")
