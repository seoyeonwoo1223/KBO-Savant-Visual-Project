# 아키텍처 제약

에이전트가 규칙을 몰라도 잘못된 결과가 **저장·병합·배포되지 못하게** 막는 장치입니다. 규칙을 지시 문서에만 적지 말고, 기계로 판정할 수 있으면 여기에 검사로 둡니다.

## 웹

| 제약 | 막는 것 | 위치 |
|---|---|---|
| 페이지 규격 | `<body>` 첫 요소가 `site-header.js`가 아님, `main.site-main` 누락·중복, `.page-title`(eyebrow·h1) 누락, `theme.css`를 마지막에 로드하지 않음(`movement-zones`만 예외) | `scripts/web_contract.py` |
| 공통 태그 덮어쓰기 금지 | 새 도구 CSS가 `main`·`header`·`nav`·`h1`을 태그 선택자로 꾸밈 (기존 7개 도구는 `LEGACY_BARE_SELECTOR_TOOLS`로 예외 — 목록에 추가하지 않음) | `scripts/web_contract.py` |
| 캐시 버스터 | 로컬 CSS·JS·카드 썸네일에 `?v=YYYYMMDD-N` 없음, `theme.css`·`site-header.js` 버전이 페이지마다 다름 | `scripts/web_contract.py` |
| Swing/Take 캡처 배경 | 반복 그라디언트 때문에 모바일·다운로드 이미지에서 League Avg 막대가 사라짐 | `scripts/web_contract.py`, `tests/test_web_contract.py` |
| 메뉴·홈·디렉터리 일치 | `TOOLS`에 있는데 페이지가 없음, 페이지가 있는데 메뉴(`ALIASES`)에 없음, 홈 카드 순서·제목이 메뉴와 다름, 썸네일 파일 없음 | `scripts/web_contract.py` |
| 생성기 템플릿 | 새 도구를 손으로 복사해 규격을 빠뜨림 → 골격·메뉴·홈 카드·버전 올림을 한 번에 생성 | `scripts/new_web_tool.py` |
| 차트 축 정렬 | Movement Zones 축 범위가 눈금 간격의 배수가 아니어서 플롯 테두리가 잘림 | `tests/test_movement_zones_layout.cjs` |
| 렌더 함수 계약 | Pitch Plot 구속·구사율 차트의 범위·비율·빈 데이터 처리 회귀 | `tests/test_pitch_arsenal_layout.cjs` (함수 이름이 슬라이스 경계) |

`Harness checks` 워크플로(`.github/workflows/web_contract.yml`)가 `web/**`·하네스·문서 변경마다 실행합니다. 배포는 막지 않습니다([0009](../decisions/0009-web-contract-non-blocking.md)).

## 데이터·파이프라인

| 제약 | 막는 것 | 위치 |
|---|---|---|
| 의존 hash 폐포 | metric 모듈이 새 모듈을 import했는데 `metric_state.CODE`에 없어 코드 변경 후 재빌드가 안 됨 | `tests/test_metric_state.py::test_code_hash_covers_every_imported_package_module` |
| 산출물 게이트 | SBJ 시즌 산출물이 현재 코드와 다르거나 시즌끼리 어긋난 채 Release·데이터 커밋·Pages로 나감 | `scripts/check_zone_decision_outputs.py` (`daily_update`가 게시 전에 실행) |
| 얼린 파일 (sha 고정) | `curated.py`, `vb_arm_angle.py`, `arm_angle_calibration.py`, `trackman_arm_angle.py`가 바뀌어 팔각도 모델·결과에 고정된 구현 sha256과 어긋남 | `tests/test_frozen_files.py` (`daily_update`의 전체 pytest에서도 실행) |
| fail-closed 읽기 | 손상·누락 partition에서 부분 데이터를 반환 | `curated.load_rows()` (`FileNotFoundError`) |
| 생성 데이터 diff 차단 | 수천 줄 생성 데이터 diff가 리뷰·컨텍스트를 덮음 | `.gitattributes` (`-diff`, `linguist-generated`) |
| 커밋 금지 파일 | 최신 Excel, Naver 캐시, pending 데이터 커밋 | `.gitignore` |
| 변경 없는 재실행 가드 | 같은 내용의 재실행이 빈 데이터 커밋을 만듦 | `daily_update`의 `git diff --cached --quiet` (+ 벽시계 시각을 쓰지 않는 규칙) |

## 아직 지시 문서에만 있는 규칙

아래는 기계 검사가 없어 [AGENTS.md](../../AGENTS.md)·[conventions.md](../conventions.md)에만 있습니다. 위반이 반복되면 검사로 옮깁니다.

- 수집 경로 얼린 파일(`parser.py`, `state_machine.py`, `validation.py`, `collector.py`, `storage.py`, `naver.py`) 수정 금지 — sha 고정이 없어 사전 차단은 없고, 수정하면 `daily_update`가 2026 원본 전체를 네트워크 재처리합니다([0010](../decisions/0010-frozen-files.md)).
- 2022–2024 curated 삭제·compact 금지.
- 미확인과 0 구분, 지표 표현 과장 금지.
- 기존 시각화 형태 유지(차트 종류·축·배치).
