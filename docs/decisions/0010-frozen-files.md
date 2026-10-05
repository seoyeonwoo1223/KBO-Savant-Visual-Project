# 0010. 얼린 파일과 그 이유

- **상태**: 채택

## 맥락
일부 소스는 내용이 바뀌는 것 자체가 부작용을 냅니다.

## 결정
| 파일 | 이유 | 강제 수단 |
|---|---|---|
| `parser.py`, `state_machine.py`, `validation.py`, `collector.py`, `storage.py`, `curated.py`, `naver.py` | push하면 `daily_update`가 2026 원본 전체를 `--rebuild-from-raw --refresh-naver`로 네트워크 재처리 | 지시 문서 (사전 차단 없음) |
| `curated.py`, `vb_arm_angle.py`, `arm_angle_calibration.py`, `trackman_arm_angle.py` | 구현 sha256이 `data/models/estimated_arm_angle_v1.json`, `analysis/arm_angle/results/*.json`에 고정되어 eAA 재현성 근거가 됨 | `tests/test_frozen_files.py` |

- private helper가 필요하면 고치지 않고 import합니다(`curated._number`).

## 기각한 대안
- 필요할 때마다 수정하고 결과를 다시 만들기: 네트워크 재수집 비용과 모델 재현성 근거 상실이 큽니다.

## 결과
- 정말 바꿔야 하면 재처리·재학습을 계획하고 hash를 갱신한 뒤 이 기록을 고칩니다.
