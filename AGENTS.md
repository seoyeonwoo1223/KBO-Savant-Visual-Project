# AGENTS.md

이 저장소에서 일하는 에이전트(Claude Code, Codex 등)가 작업 전에 읽는 **지도**입니다.
2026 KBO 공개 PBP(Visual Baseball)를 증분 수집해 canonical Parquet으로 정규화하고, 파생 metric·Excel·GitHub Pages 정적 뷰어(`web/`)를 만듭니다. 문서·UI·커밋 메시지는 한국어로 씁니다.

여기에는 지켜야 할 핵심과 "어디를 볼지"만 둡니다. 세부 규칙·구조·이유는 아래 문서에 있습니다.

## 문서 지도

| 알고 싶은 것 | 문서 |
|---|---|
| 작업 규칙 전체 (데이터 읽기, 코드, 지표 표현, 웹, 커밋·PR) | [docs/conventions.md](docs/conventions.md) |
| 시스템 구조 (데이터 흐름, partition 레이아웃, 좌표계, 모듈 지도, CI) | [docs/architecture.md](docs/architecture.md) |
| 왜 이렇게 되어 있나 (결정·기각한 대안) | [docs/decisions/](docs/decisions/README.md) |
| 무엇이 자동으로 막고 확인하나 (하네스) | [docs/harness/](docs/harness/README.md) |
| curated 데이터 계약 | [docs/curated-data.md](docs/curated-data.md) |
| SBJ·TrackMan 데이터 신뢰 감사 | [docs/sbj-data-quality.md](docs/sbj-data-quality.md) |
| 지표 수식 근거·한계 | `analysis/zone_decision/README.md`, `analysis/plate_decision_v1/` |

## 작업 순서

1. 작업 영역의 문서를 위 지도에서 하나 골라 읽습니다. 지표 수식을 바꾸기 전에는 `analysis/` 근거 문서를, SBJ 원본 사건·TrackMan 연결을 고치기 전에는 SBJ 감사 문서를 반드시 읽습니다.
2. [docs/decisions/](docs/decisions/README.md) 목록에서 관련 결정을 확인합니다. 기각된 대안을 다시 시도하지 않습니다.
3. 변경은 요청 범위만, 기존 시각화 형태(차트 종류·축·배치·라벨)는 유지합니다.
4. [docs/harness/feedback.md](docs/harness/feedback.md)의 검사를 빠른 것부터 돌리고, 결과를 PR `## 검증`에 적습니다.

## 반드시 지킬 것

- **데이터는 싸게 읽습니다.** `data/curated/summary.json` → `schema.json` → `curated.load_rows()`로 필요한 행만. `partition-index.json` 열기, `data/`·`exports/`·`seasons/` glob, Parquet `cat`, 생성 데이터 `git diff`는 하지 않습니다.
- **얼린 파일을 고치지 않습니다.** `parser.py`, `state_machine.py`, `validation.py`, `collector.py`, `storage.py`, `curated.py`, `naver.py`(push하면 2026 원본 전체 네트워크 재처리), `vb_arm_angle.py`, `arm_angle_calibration.py`, `trackman_arm_angle.py`(sha256 고정). private helper가 필요하면 import합니다.
- **2022–2024 curated는 유일한 사본입니다.** 삭제·compact·이력 재작성 금지.
- **`web/`·`exports/`는 출력물입니다.** 어떤 코드도 입력으로 읽지 않습니다.
- **미확인 ≠ 0, 라인스코어가 최종 기준, 표본 미달은 표시, 시즌을 섞지 않음, 지표를 과장하지 않음.** (세부: conventions)
- **커밋되는 산출물에 벽시계 시각을 무조건 쓰지 않습니다.**
- **웹 도구는 `scripts/new_web_tool.py`로 만들고**, 도구 CSS에서 `main`·`header`·`nav`·`h1` 태그를 꾸미지 않습니다. 메뉴·홈 카드·썸네일은 순서·이름이 같아야 합니다. CSS/JS를 고치면 `?v=`를 올립니다.
- **병합은 사용자가 요청할 때만** 합니다. PR은 draft로 엽니다.

## 자주 쓰는 명령

```bash
python -m pip install -r requirements.txt -c constraints-za.txt   # ZA 재현 고정 버전
export PYTHONPATH=src OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2

python -m pytest tests/test_<영역>.py              # 좁게 먼저, 마지막에 python -m pytest
for t in tests/*.cjs; do node "$t"; done           # 웹 렌더 함수 테스트 (pytest 미수집)
python scripts/web_contract.py                     # 웹 페이지 규격
python scripts/serve_web.py                        # 웹 프리뷰 (문서 루트 web/)

python -m visualbaseball.cli --exports-only        # 수집 없이 산출물만 재생성
python -m visualbaseball.cli --fixture data/raw/2026/20260328HTSK0.json   # 네트워크 없이 확인
```

## 커밋·PR 형식

- 커밋 제목 `영역: 무엇을 했는지` (예: `웹:`, `문서:`, `ci:`, `refactor:`), 본문은 `- ` 목록으로 이유와 변경.
- PR 본문 `## 요약` → `## 검증`(실제로 돌린 것) → 필요하면 `## 남은 문제`. 화면 변경은 1440px·390px 전후 비교.
- 채택·기각한 대안이 있는 결정을 했다면 [docs/decisions/](docs/decisions/README.md)에 기록을 추가합니다.
