# 피드백 루프

작업 결과가 맞는지 **즉시** 알려주는 장치입니다. 가이드는 실수를 예방하고, 센서는 실수를 포착합니다. 피드백이 빠를수록 비용이 적으므로 **빠른 것부터** 돌립니다.

## 가이드 (올바른 방향을 안내)

| 가이드 | 언제 |
|---|---|
| `scripts/new_web_tool.py` | 새 웹 도구. 규격을 지킨 골격·메뉴·홈 카드를 만들어 줍니다 |
| 기존 테스트를 예제로 | 같은 영역의 `tests/test_<영역>.py`가 입력·기대값의 형태를 보여 줍니다. 새 metric은 `tests/test_metric_state.py`, 수집은 `tests/test_cli_collection.py`(가짜 client) |
| 기존 도구 페이지 | `web/blocking/`, `web/zones/`가 가장 단순한 도구 구조입니다 |
| 결정 기록 | [decisions/](../decisions/README.md)의 "기각한 대안"이 다시 가지 말아야 할 길을 알려 줍니다 |

## 센서 (잘못된 결과를 감지) — 빠른 순서

| # | 센서 | 명령 | 시간 | 언제 |
|---|---|---|---|---|
| 1 | 웹 규격 | `python scripts/web_contract.py` | 1초 미만 | `web/` 변경마다 |
| 2 | 웹 렌더 함수 | `for t in tests/*.cjs; do node "$t"; done` | 1초 | 차트 JS 변경 |
| 3 | 하네스·문서 링크 | `python -m pytest tests/test_web_contract.py tests/test_docs_links.py` | 1초 | 하네스·문서 변경 |
| 4 | 영역 테스트 | `PYTHONPATH=src python -m pytest tests/test_<영역>.py` | 수 초 | 코드 변경 |
| 5 | 전체 테스트 | `PYTHONPATH=src python -m pytest` | 수 분 | PR 전 |
| 6 | 화면 확인 | `python scripts/serve_web.py` 후 1440px·390px 전후 스크린샷. 메뉴 하단→제목 블록 시작 간격이 기존 앱과 같은지, `.page-title`의 computed `margin-top`이 0인지 확인. 390px에서 `scrollWidth == innerWidth` | 수 분 | 새 앱 추가·화면 변경 |
| 6a | Swing/Take 이미지 | 390px에서 `html.profile-imaged` 상태의 `#profile-image`와 이미지 저장 PNG 확인. 4개 구역의 Swing·Take League Avg 점선 막대가 모두 보여야 함. CDN·데이터·캡처 지연 중 기존 반응형 화면이 노출되지 않고, 실패 시 로딩이 해제되는지 확인 | 수 분 | Swing/Take 캡처 대상 CSS·JS 변경 |
| 7 | 산출물 동일성 | 기준·변경 커밋에서 같은 빌더 실행 후 `web/data`·`data/metrics`·`exports` hash 비교 | 수 분~ | 리팩터링 |
| 8 | 산출물 게이트 | `PYTHONPATH=src python scripts/check_zone_decision_outputs.py` | 수 초 | 지표 산출물 변경 |
| 9 | 브라우저 검증 | `python scripts/check_movement_zones.py` (Playwright) | 수 분 | Movement Zones 모델·화면 |
| 10 | 썸네일 | `python scripts/generate_visual_thumbnails.py` 후 `git status`로 변경 여부 | 수 분 | 썸네일 대상 화면 변경 |

## CI (자동 센서)

| 워크플로 | 실행 | 센서 |
|---|---|---|
| `Harness checks` (`web_contract.yml`) | `web/**`, 하네스, 문서 push·PR | 1, 2, 3 |
| `daily_update.yml` | 매일 + 파이프라인 입력 push | 5, Pitch Plot `.cjs`, metric state 보고, 8 |
| `deploy-pages.yml` | `web/**` push | 배포 (센서 아님) |

## 센서를 추가할 때

- 같은 실수가 두 번 나오면 센서를 만듭니다. 이번에 추가한 예: Movement Zones 축 하한이 눈금과 어긋난 문제 → `tests/test_movement_zones_layout.cjs`.
- 센서는 실제 실패를 재현해 빨간색이 되는 것을 먼저 확인합니다.
- 실패 메시지는 무엇을 고쳐야 하는지 한국어로 적습니다.
- 새 `.cjs`는 `tests/`에 두면 `Harness checks`가 자동으로 실행합니다.
