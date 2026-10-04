# 0009. 웹 규격 검사는 배포를 막지 않는 별도 체크

- **상태**: 채택 (PR #57)

## 맥락
웹 규격 검사를 Pages 배포 앞에 두면, 매일 데이터 갱신 후 배포까지 규격 위반 하나로 멈출 수 있습니다. 데이터 공개는 화면 규격보다 우선입니다.

## 결정
- `Harness checks`(`.github/workflows/web_contract.yml`)를 별도 워크플로로 두고 `web/**`·하네스·문서 변경의 push·PR에서 실행합니다. 실패하면 체크만 빨간색이 됩니다.
- 같은 검사를 로컬(`python scripts/web_contract.py`)과 pytest(`tests/test_web_contract.py`)에서 돌릴 수 있게 합니다.

## 기각한 대안
- `deploy-pages.yml`에 검사 단계 추가: 데이터 배포까지 막힙니다.
- `daily_update.yml`에 추가: 이 파일을 고치면 daily 파이프라인이 실행됩니다.

## 결과
- PR에서 빨간 체크가 보이면 병합 전에 고칩니다.
