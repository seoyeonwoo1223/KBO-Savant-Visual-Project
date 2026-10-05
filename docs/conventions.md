# 작업 컨벤션

[AGENTS.md](../AGENTS.md)가 가리키는 세부 규칙입니다. "어떻게 하는가"만 적고, 이유는 [decisions/](decisions/README.md)에 둡니다.

## 명령

```bash
python -m pip install -r requirements.txt -c constraints-za.txt   # constraints-za.txt: ZA 모델 재현용 고정 버전
export PYTHONPATH=src OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2

# 테스트
python -m pytest tests/test_swing_take.py -k decision -x   # 좁게
python -m pytest                                          # 전체
for t in tests/*.cjs; do node "$t"; done                  # 웹 렌더 함수 (pytest 미수집, 함수 이름이 슬라이스 경계)

# 웹
python scripts/serve_web.py [--port 9000 --open]          # 문서 루트 web/ (VS Code Task "웹 프리뷰 (web/ 루트)"도 같음)
python scripts/web_contract.py
python scripts/generate_visual_thumbnails.py              # 홈 카드 썸네일 (Playwright Chromium)

# 파이프라인
python -m visualbaseball.cli                                         # recent 수집 + 전체 export
python -m visualbaseball.cli --exports-only                          # 수집 없이 산출물만
python -m visualbaseball.cli --fixture data/raw/2026/20260328HTSK0.json
python -m visualbaseball.cli --collection-mode sample --auto-reconcile
python -m visualbaseball.cli --collection-mode reconcile --refresh-workers 3
python -m visualbaseball.cli --rebuild-from-raw --refresh-naver --game-id 20260328KTLG0
python -m visualbaseball.cli --season 2025 --storage-root seasons/2025
python -m visualbaseball.build_curated --season 2026 --validate
python -m visualbaseball.compact_curated --season 2026              # 일회성. 2022–2024에는 쓰지 않음
python -m visualbaseball.dataset_summary
python -m visualbaseball.zone_decision --seasons 2024 2025 2026      # metric 하나만 (__main__ 있는 모듈)
```

## 데이터를 읽는 법 (비용 규칙)

생성 데이터가 커서 탐색 방식이 비용을 지배합니다.

| 알고 싶은 것 | 읽을 것 | 크기 |
|---|---|---|
| 어떤 시즌·월·행수가 있나 | `data/curated/summary.json` | 4KB |
| 컬럼 이름·타입 | `data/curated/schema.json` | 15KB |
| 파이프라인 계약 | [curated-data.md](curated-data.md) | 4KB |
| 모델 근거·한계 | `analysis/zone_decision/README.md` | 8KB |

- 행은 컬럼·경기·선수로 좁혀 읽습니다. pruning은 Arrow에서 일어납니다.
  ```python
  from visualbaseball.curated import load_rows
  load_rows(root, "pitches", 2026, columns=["pitch_id", "px", "pz", "is_swing"])
  load_rows(root, "pitches", 2026, game_id="20260328HTSK0")
  load_rows(root, "pitches", 2026, player_id="12345", player_role="pitcher")
  ```
- 행수만 필요하면 `pq.ParquetFile(path).metadata.num_rows`. 요약 재생성은 `python -m visualbaseball.dataset_summary`.
- **하지 말 것**: `partition-index.json` 열기(MB 단위 무결성 기록), `data/`·`exports/`·`seasons/` glob, Parquet `cat`/`head`, 생성 데이터 `git diff`.

## 코드

- **한 모듈, 한 책임.** metric 모듈은 읽기 → 집계 → 쓰기만 합니다. 여러 metric이 쓰는 helper는 작은 공용 모듈(`pitch_types`, `batter_stance`, `teams`, `publish`)로 옮깁니다. 다른 모듈이 metric 모듈에서 helper를 import하는 의존을 만들지 않습니다.
- **함수는 한 단계만.** 빌더는 단계 함수를 순서대로 부르는 얇은 조립부입니다(`build_pitch_arsenal`, `build_zone_profiles`, `cli.main`). radon 복잡도 D(21) 이상이면 나눕니다.
- **같은 기능은 한 곳에.** 값 정규화는 `curated._number`, JSON 쓰기·shard 교체·시즌 catalog는 `publish.py`. 이름이 같아도 동작이 다른 helper(`blocking._number`는 NaN 반환)는 합치지 않습니다.
- **안 쓰는 코드는 지웁니다.** 프로덕션 경로(`cli._exports()`, `--only`, 워크플로)에서 닿지 않는 함수는 테스트와 함께 제거합니다. 커밋된 산출물은 코드가 사라져도 지우지 않습니다.
- **의존 hash를 같이 고칩니다.** metric 모듈이 새 패키지 모듈을 import하면 `metric_state.CODE`에 추가합니다.
- **리팩터링은 산출물 바이트 동일성으로 검증합니다.** 기준 커밋과 변경 커밋에서 같은 빌더를 강제로 돌려 `web/data`, `data/metrics`, `exports` 파일 hash를 비교합니다. 코드 hash 필드(`report.json`의 `reproducibility.source_sha256`, movement_zones의 `code_sha256`)만 달라야 정상입니다. 기준 커밋을 두 번 돌려 결정성부터 확인합니다.
- **테스트 없는 경로는 현재 동작을 고정하는 테스트를 먼저 씁니다** (`tests/test_cli_collection.py`처럼 가짜 client 사용).
- **커밋되는 산출물에 벽시계 시각을 무조건 쓰지 않습니다.** `last_collected_at`·`revision`처럼 실제로 달라졌을 때만 갱신합니다.
- 이름: Python 모듈·함수는 snake_case. 웹 도구 디렉터리는 kebab-case(`web/strike-zone/`), 파일은 `<tool>.css`·`<tool>.js`.

## 데이터·지표 표현

- **미확인과 0을 구분합니다.** `naver_match_status`가 `unavailable`/`unmatched`면 폭투·포일은 0이 아니라 미확인입니다. 공개 PBP에 없는 주자 이벤트는 `parse_status=unknown`. 파생 컬럼의 null은 "계산 불가", `false`는 "관측된 false".
- **공식 라인스코어가 최종 기준.** PBP와 충돌하면 `SOURCE_SCORE_CONFLICT`를 남기고 라인스코어를 씁니다.
- **표본 미달은 숨기지 않고 표시합니다.** Swing/Take·ZA 300 pitches seen, 리더보드 타자 200 PA / 투수 50 IP.
- **시즌을 섞지 않습니다.** Run Value와 리그 평균은 해당 시즌 canonical shard만으로 계산합니다.
- **지표를 과장하지 않습니다.** BAA는 KBO 공개 데이터 적용 실험 지표이며 MLB Statcast와 비교할 수 없습니다. Decision Run을 counterfactual Decision Value로 부르지 않습니다. plate discipline 클러스터 번호는 등급이 아닙니다.
- **SBJ·TrackMan**: 원본 사건·TrackMan 연결을 고치기 전에 [sbj-data-quality.md](sbj-data-quality.md)를 읽습니다. TrackMan은 양팀 모두 1군 코드인 투구만 쓰고, 카운트는 매칭 조건이 아니라 독립 대조값입니다. 미매칭 공을 억지로 연결하거나 감사 플래그로 자동 재분류·삭제하지 않습니다.
- **좌표계**는 [architecture.md#좌표계](architecture.md#좌표계)를 따릅니다. 저장되는 x 계열은 모두 포수 시점이고, 투수 시점은 화면에서만 뒤집습니다.

## 웹

- **새 도구는 생성 스크립트로 만듭니다.**
  ```bash
  python scripts/new_web_tool.py strike-zone --title "Strike Zone" --eyebrow "Pitching" --subtitle "투수별 스트라이크존 판정"
  #   --nav-label "메뉴 이름"   메뉴 이름을 제목과 다르게
  #   --no-nav                 메뉴에 넣지 않는 하위 페이지 (site-header.js ALIASES에 상위 도구 지정)
  ```
  골격(공통 헤더·`main.site-main`·`.page-title`·캐시 버스터), 메뉴 등록, 같은 순서의 홈 카드(빈 그림), 전 페이지 `site-header.js` 버전 올림까지 합니다.
- **공통 규격은 `theme.css`·`site-header.js`가 정합니다.** 도구 CSS에서 `main`·`header`·`nav`·`h1`을 태그 선택자로 꾸미지 않고 도구 전용 클래스를 씁니다. `theme.css`는 페이지 CSS 뒤에 로드합니다(`movement-zones`만 예외).
- **선수 검색**: `theme.css`의 `.search-heading`·`.search-picker`·`.player-search`·`.search-message`를 씁니다. 페이지 CSS에 검색 규칙을 따로 만들지 않습니다([0012](decisions/0012-shared-player-search.md)).
- **제목 블록**: `<header class="page-title">` 안에 `.eyebrow`(영문 분류) + `<h1>`(영문, 메뉴 이름과 같게) + 한국어 부제 한 줄. 홈만 제목 블록이 없습니다.
- **메뉴·홈 카드·썸네일은 한 몸입니다.** 홈 카드는 `site-header.js`의 `TOOLS`와 같은 순서, 카드 제목은 메뉴 이름과 같습니다. 썸네일은 `scripts/visual_thumbnails.json`에 캡처 설정(`?thumb=1` + `[data-thumbnail-target]`)을 두고 `python scripts/generate_visual_thumbnails.py`로 만듭니다. 썸네일 대상 화면을 바꾸면 다시 만들고 카드 `<img>`의 `?v=`를 올립니다. Blocking 카드만 인라인 SVG입니다.
- **캐시 버스터**: 모든 로컬 `<link>`·`<script>`·카드 `<img>`에 `?v=YYYYMMDD-N`. 고치면 올립니다. `theme.css`·`site-header.js`는 홈 포함 전 페이지에서 한꺼번에.
- **기존 시각화의 형태를 유지합니다.** 데이터·코드 변경이 차트 종류·축·배치·라벨을 바꾸지 않게 하고, 화면 변경이 의도일 때만 최소로 바꿉니다.
- **차트 축 범위는 눈금 간격의 배수로** 잡아 플롯 네 테두리가 라벨 있는 눈금선과 맞게 합니다.
- **모바일**: 숨겨진 탭의 canvas는 폭이 0이므로 직전 CSS 폭을 씁니다(`zone-awareness.js`의 `canvasContext`). html2canvas 캡처 대상에는 `color-mix()` 등 최신 색 함수를 쓰지 않습니다. 390px에서 `document.documentElement.scrollWidth`가 화면 폭과 같은지 확인합니다.
- **데이터 경로**: 페이지 기준 `../data/<metric>/<season>/…`을 fetch합니다. 선수 상세는 `players/<shard>.json`, 시즌 목록은 metric 디렉터리의 `index.json`.
- **로컬 프리뷰**: `python scripts/serve_web.py` (문서 루트가 반드시 `web/`, 응답에 `Cache-Control: no-store`).

## 커밋·PR

- 기본 브랜치 `master`. 작업 브랜치에서 커밋하고 PR은 draft로 엽니다. **병합은 사용자가 요청할 때만** 합니다.
- 커밋 제목: `영역: 무엇을 했는지` (한국어). 영역 예: `웹:`, `문서:`, `ci:`, `refactor:`, `APR:`, `gates:`. 본문은 `- ` 목록으로 이유와 주요 변경.
- PR 본문: `## 요약`(무엇을·왜) → `## 검증`(실제로 돌린 것과 결과) → 필요하면 `## 남은 문제`. 화면 변경은 전후를 비교해 적습니다.
- 생성 데이터 커밋은 CI(`chore: update Visual Baseball data`)가 합니다. 사람이 만든 커밋에 산출물이 섞이면 이유를 PR에 적습니다.
- `.github/refresh-completed-request`를 커밋하면 다음 daily 실행이 전체 재수집합니다. 의도한 경우에만.
- 채택·기각한 대안이 있는 결정은 [decisions/](decisions/README.md)에 기록을 추가합니다.
