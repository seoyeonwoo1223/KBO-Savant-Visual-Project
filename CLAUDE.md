# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

2026 KBO 공개 PBP(Visual Baseball)를 증분 수집해 canonical Parquet으로 정규화하고, 거기서 파생 metric·Excel·GitHub Pages 정적 뷰어를 생성하는 프로젝트입니다. 문서와 UI 텍스트는 한국어로 작성합니다.

## 환경과 명령

Python 3.12 기준입니다. `PYTHONPATH=src`가 항상 필요합니다.

```bash
python -m pip install -r requirements.txt -c constraints-za.txt
export PYTHONPATH=src
export OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2   # ZA 재현 환경 기준
```

`constraints-za.txt`는 ZA 모델 재현용 고정 버전입니다. 모델 결과가 달라지면 안 되는 작업에서는 반드시 `-c`로 함께 설치합니다.

### 테스트

```bash
python -m pytest                               # 전체
python -m pytest tests/test_zone_decision.py   # 파일 단위
python -m pytest tests/test_swing_take.py -k decision -x   # 단일 테스트
node tests/test_pitch_arsenal_layout.cjs       # 웹 레이아웃 테스트 (pytest가 수집하지 않음)
```

`.cjs` 테스트는 `web/pitch-arsenal/pitch-arsenal.js`의 렌더 함수를 `vm`으로 잘라서 실행합니다. 함수 이름(`renderVelocity`, `renderFrequency`, `movementPoint`, `showTooltip`)이 슬라이스 경계이므로 이름을 바꾸면 테스트가 조용히 깨집니다. pytest가 수집하지 않으므로 5개 워크플로(`web_contract.yml` 포함)에서 별도 스텝으로 실행합니다.

### 웹 로컬 프리뷰

페이지들이 `../data/...`를 fetch하므로 서버 루트는 반드시 `web/`이어야 합니다. 저장소 루트에서 띄우면 모든 데이터가 404가 되고 도구가 빈 화면으로 뜹니다. 루트를 실수할 여지를 없애려면 스크립트를 쓰십시오 — 자기 파일 위치에서 저장소 루트를 찾으므로 어느 디렉터리에서 실행해도 됩니다.

```bash
python scripts/serve_web.py            # http://localhost:8000/
python scripts/serve_web.py --port 9000 --open
```

VS Code에서는 `Ctrl+Shift+P` → `Tasks: Run Task` → **웹 프리뷰 (web/ 루트)** 로도 실행됩니다. 로컬 응답에는 `Cache-Control: no-store`가 붙으므로 `?v=` 캐시 버스터를 올리지 않아도 새로고침이면 최신 파일이 뜹니다 (배포용 버전 올리기는 여전히 필요).

`python -m http.server 8000 --directory web`로 직접 띄워도 동일합니다.

빌드 단계는 없습니다. `web/`은 순수 정적 파일이고 GitHub Pages가 `web/`을 그대로 루트로 서빙합니다.

### 데이터 파이프라인

```bash
python -m visualbaseball.cli                                    # 기본 recent 모드 수집 + 전체 export
python -m visualbaseball.cli --fixture data/raw/2026/20260328HTSK0.json   # 네트워크 없이 오프라인 확인
python -m visualbaseball.cli --collection-mode sample --auto-reconcile
python -m visualbaseball.cli --collection-mode reconcile --refresh-workers 3
python -m visualbaseball.cli --rebuild-from-raw --refresh-naver --game-id 20260328KTLG0
python -m visualbaseball.cli --exports-only                     # 수집 없이 curated에서 산출물만 재생성
python -m visualbaseball.cli --season 2025 --storage-root seasons/2025   # 과거 시즌
python -m visualbaseball.build_curated --season 2026 --validate
python -m visualbaseball.compact_curated --season 2026   # game shard → 월별 partition (일회성)
python -m visualbaseball.dataset_summary                 # summary.json 갱신
```

수집 모드: `recent`는 신규·미완료·실패 게임과 최근 7일 확정 경기, `sample`은 30일 이상 지난 경기 8개를 균등 추출해 schema/y0/pitch hash 변화를 감시, `reconcile`은 전 경기 재수집입니다.

개별 metric만 다시 만들 때는 해당 모듈을 직접 실행합니다. `__main__`이 있는 모듈: `build_curated`, `cli`, `leaderboard_vb`, `movement_zones`, `pitch_arsenal`, `plate_discipline`, `zone_decision`, `zone_profile`.

```bash
python -m visualbaseball.zone_decision --seasons 2024 2025 2026
python -m visualbaseball.leaderboard_vb
```

## 아키텍처

### 데이터 흐름: raw → curated → metric → publication

```
data/raw/<season>/<game_id>.json            Visual Baseball 원본 PBP (+ raw/naver/ 조인 캐시, gitignore)
  ↓ parser.py / collector.py / state_machine.py
data/curated/{pitches,events,games}/season=<year>/<game_id>.parquet   canonical (현재 커밋 상태)
                                     …/month=MM.parquet   compact 후 레이아웃
data/curated/partition-index.json           compact 후에만 존재. 게임 → 월 + 테이블 digest (1.5MB, 열어보지 말 것)
data/curated/summary.json                   사람·에이전트용 요약 (4KB, 여기부터 읽을 것)
data/curated/schema.json                    테이블별 컬럼·타입 계약
data/curated/sources/…json                  수집·검증 manifest + raw/pitch/schema sha256
data/curated/audit/…jsonl                   raw 변경 이력
  ↓ 각 metric 모듈 (data/metrics/_state/가 metric별 입력·코드 hash 보관)
data/metrics/<metric>/<season>/…parquet|json
  ↓ publication only
web/data/**.json · exports/*.xlsx|csv · GitHub Release
```

**핵심 계약**: `web/`과 `exports/`는 출력물일 뿐이며 어떤 코드도 이것을 입력으로 읽지 않습니다. metric은 `curated.load_rows()`로 curated partition만 읽습니다 (Zone Awareness는 Excel/legacy cache fallback이 금지되어 있습니다). 유일한 외부 workbook 입력은 `data/park_adjustments/<season>_VB_Park_Adjustment_v1.0.xlsx` 구장 보정표이며, 지금은 ZA/SBJ의 p_swing 경로(`plate_decision_v1._movement_adjust`)만 읽습니다. Pitch Arsenal은 이 표 대신 `movement_calibration.py`(TrackMan으로 검증한 구장×날짜·탄착 위치 보정, `analysis/movement_calibration/`)를 씁니다. 세부 계약은 `docs/curated-data.md`에 있습니다.

**재생성 순서**는 `cli._exports()`가 단일 소스입니다. Excel → arm_angle 입력 → swing_take → (plate_discipline, zone_decision) → zone_profile → pitch_arsenal → blocking. `swing_take`가 만드는 `data/metrics/swing_take/<season>/decision_pitches.parquet`가 그 뒤 판단 지표 전체의 입력이므로, Swing/Take를 건드리면 하위 metric이 전부 함께 재생성되어야 합니다.

**증분성**: partition은 원자적으로 교체되고, `pitch_sha256`가 같으면 다시 쓰지 않습니다. provider가 파싱과 무관한 필드를 바꾸면 `raw_sha256`만 바뀌고 partition은 그대로입니다. metric은 `metric_state.needs_build()`가 입력·코드·의존 파일 hash로 개별 판정하므로, 하나가 바뀌어도 나머지는 건너뜁니다. 중단 후 재실행은 안전합니다.

**레이아웃은 시즌별로 다릅니다.** 마이그레이션이 시즌 단위 일회성이라 두 레이아웃이 공존합니다.

| 시즌 | 레이아웃 | raw 복구 경로 |
|---|---|---|
| 2026 | month (21 partition) | `data/raw/2026` |
| 2025 | month (24 partition) | `seasons/2025` |
| 2022–2024 | **game shard** (각 2,160개) | **없음** |

2022–2024는 raw JSON이 전무해서 curated가 유일한 사본입니다. 유일한 복구 경로가 git 이력이므로, 이력 재작성(`filter-repo`) 계획이 있으면 그 전에 compact하지 마십시오.

`index["layout"]`은 **저장소 전역 키라 시즌 판정에 쓸 수 없습니다.** `write_game()`이 레이아웃과 무관하게 모든 게임을 index에 기록하므로 index 항목 유무도 근거가 못 됩니다. 판정은 `curated._season_is_compact()` 하나만 쓰십시오 — 디스크에 `month=*.parquet`이 실제로 있는지로 답합니다. 실패한 마이그레이션은 월 파일을 남기면서 index는 `game`으로 두므로, 전역 플래그가 그 조합을 game으로 되돌리는 역할을 합니다.

**월별 partition 계약** (`docs/curated-data.md`가 원본):

- `partition-index.json`의 `tables` digest는 **Parquet에 저장된 내용의 hash**입니다. `curated.table_digest()` 하나만 쓰고, 쓰기 경로와 읽기 경로가 같은 값을 내야 합니다. 새 쓰기 경로를 만들면 이 함수를 통과시키십시오.
- **`pq.ParquetFile()` open 성공과 schema 일치는 무결성 증거가 아닙니다.** footer만 읽기 때문에 데이터 페이지가 깨진 파일도 통과합니다. 파일을 지우기 전 검증은 반드시 전체 read-back + digest 대조(`compact_curated.verify_partitions()`)여야 합니다.
- game layout 읽기는 `month=*.parquet`을 무시합니다. 실패한 마이그레이션이 남긴 월 파일과 legacy shard를 함께 읽으면 행이 조용히 두 배가 됩니다.
- 손상·누락 partition은 fail-closed입니다. 부분 데이터를 반환하지 않고 `FileNotFoundError`를 냅니다.
- **2022–2024는 raw JSON이 없습니다.** 이 시즌의 curated를 잃으면 복구 경로가 없습니다. 삭제를 수반하는 작업은 특히 보수적으로 다루십시오.

### 데이터를 싸게 읽는 법 (에이전트용)

이 저장소는 생성 데이터가 커서 **탐색 방식이 비용을 지배합니다.** 아래 순서를 지키면 대부분의 질문이 수 KB 안에서 끝납니다.

| 알고 싶은 것 | 읽을 것 | 크기 |
|---|---|---|
| 어떤 시즌·월·행수가 있나 | `data/curated/summary.json` | 4KB |
| 컬럼 이름·타입 | `data/curated/schema.json` | 15KB |
| 파이프라인 계약 | `docs/curated-data.md` | 4KB |
| 모델 근거·한계 | `analysis/zone_decision/README.md` | 8KB |

**하지 말 것**

- `partition-index.json`을 열지 마십시오 (compact 후에만 존재). 경기 × 3테이블 digest라 MB 단위이고, 무결성 기록이지 목록이 아닙니다. "무슨 데이터가 있나"의 답은 `summary.json`에 있습니다.
- `data/`, `exports/`, `seasons/`를 glob으로 훑지 마십시오. 추적 파일이 15,000개대이고 생성 데이터가 대부분입니다.
- Parquet을 `cat`/`head`로 열지 마십시오. 바이너리라 컨텍스트만 태웁니다.
- 생성 데이터의 `git diff`를 읽지 마십시오. `.gitattributes`가 `-diff`로 막아두었지만, 경로를 직접 지정하면 여전히 나옵니다.

**행이 실제로 필요할 때**는 전체를 읽지 말고 컬럼·게임·선수로 좁힙니다. pruning은 Arrow에서 일어나므로 파일 전체를 메모리에 올리지 않습니다.

```python
from visualbaseball.curated import load_rows
load_rows(root, "pitches", 2026, columns=["pitch_id", "px", "pz", "is_swing"])
load_rows(root, "pitches", 2026, game_id="20260328HTSK0")      # 해당 경기(또는 월) 파일 1개만 open
load_rows(root, "pitches", 2026, player_id="12345", player_role="pitcher")
```

행수·크기만 필요하면 footer만 읽습니다. 이미 집계된 값은 `summary.json`에 있으니 그걸 먼저 보십시오.

```python
import pyarrow.parquet as pq
pq.ParquetFile(path).metadata.num_rows
```

요약본을 다시 만들려면 `python -m visualbaseball.dataset_summary`이며, `cli._exports()` 끝에서도 자동으로 갱신됩니다.

### 좌표계 규칙 (헷갈리기 쉬움)

SBJ 원본 사건·TrackMan 연결을 고치기 전에는 `docs/sbj-data-quality.md`의 출시 경계와 전수 감사 절차를 읽는다. TrackMan은 양팀 모두 1군 코드인 투구만 쓰고, 카운트는 매칭 조건이 아니라 독립 대조값이다. 미매칭 공을 억지로 연결하거나 감사 플래그로 자동 재분류·삭제하지 않는다.

- **`px` / `pz`는 feet**, 홈플레이트 원점 기준입니다. VB `pz`는 모든 시즌 플레이트 앞면(y=17/12 ft) 값이지만 `px`는 **2024부터 중간면(y=8.5/12 ft, ABS 좌우 판정면)** 값입니다(2023까지는 앞면). 궤적으로 앞면 x를 다시 계산하면 2024+에서는 `px`와 최대 약 4cm 다른 것이 정상입니다(`analysis/trajectory_audit/`). 플레이트 반폭은 `10/12 ft`, 존 상하한은 투구별 `sz_top`/`sz_bottom`입니다. 정규화 좌표는 존 경계가 ±1이 되도록 맞춘 값이고, `d = max(|x|, |z|)`로 Heart ≤2/3, Shadow-in ≤1, Shadow-out ≤4/3, Chase ≤2, Waste >2 구역을 나눕니다.
- **저장되는 x 계열은 모두 포수 시점(catcher view)** 입니다. `release_x_50` / `release_x_55`(cm), `horizontal_movement_cm`(raw `hMov`), `web/data/**`의 `horizontal_break_in` 전부 포수 시점입니다.
- **투수 시점은 화면에서만 부호를 뒤집습니다.** `web/pitch-arsenal/pitch-arsenal.js`의 `toPitcherView()`가 `average`를 음수화하고 `low_75`/`high_75`를 서로 맞바꿉니다(구간 뒤집기를 빠뜨리면 타원이 어긋납니다). 이 페이지의 기본값은 투수 시점입니다.
- **`web/movement-zones/`는 반대로 포수 시점이 기본**입니다. 원본 범위표는 투수 시점이고, `handFactor()`(RHP `-1`, LHP `+1`)를 `viewZone()`에서 HB에 곱해 미러링합니다. IVB는 절대 뒤집지 않습니다. 숫자 범위 라벨은 `mirroredHbLabel()`이 부호 문자를 따로 다시 씁니다 — HB 데이터를 고칠 때 라벨 함수도 같이 손봐야 합니다. 축 라벨 `3B < MOVES TOWARD > 1B`와 arm angle 보조선 방향도 같은 factor를 씁니다.
- `web/zone-awareness/`의 decision map, `web/zones/`의 0.5 ft 존 격자는 포수 시점입니다.
- `y0`는 raw 그대로 보존하고 `source_y0`로도 노출합니다. 50 ft / 55 ft 평면 값은 등가속도 운동학으로 재계산한 파생값이며, 해가 없거나 y0가 50/55가 아니면 `trajectory_status`가 `valid`가 아니고 파생 컬럼은 null로 남습니다(행을 지우지 않습니다).

### 웹 페이지 구조

`web/<tool>/{index.html, <tool>.css, <tool>.js}` 한 세트가 한 도구입니다. 빌드·번들러·프레임워크 없이 순수 ES + fetch입니다. 데이터는 페이지 기준 `../data/<metric>/<season>/…`을 fetch합니다. 선수 단위 상세는 `players/<shard>.json`으로 샤딩되어 있고 시즌 목록은 각 metric 디렉터리의 `index.json`에 있습니다.

**공통 파일**

| 파일 | 역할 |
|---|---|
| `web/theme.css` | 전 페이지 공통. `--kbo-*` 색 토큰, 2단 헤더, `main.site-main` 폭(1440px)·여백, `.page-title` 제목 블록. **페이지 전용 CSS 뒤에 로드**합니다(`movement-zones`만 예외) |
| `web/site-header.js` | `<body>` 맨 앞에서 로드. 브랜드 줄(KBO Savant, 스크롤 시 사라짐) + 상단 고정 메뉴 줄을 삽입. 메뉴 목록은 `TOOLS`(홈 카드 순서와 같게), 하위 페이지는 `ALIASES` |
| `web/<tool>/<tool>.css` | 도구 레이아웃만. `main`·`header`·`nav`·`h1` 같은 bare 태그 선택자로 폭·여백을 꾸미지 않습니다(공통 헤더까지 바뀝니다) |
| `web/styles.css`, `web/home.css` | `styles.css`는 `swing-take`만 쓰는 구버전 시트, `home.css`는 홈 전용. 새 도구는 쓰지 않습니다 |

**페이지 마크업 규격**: `<main class="site-main">` 하나, 그 안 첫 블록은 `<header class="page-title">`에 `.eyebrow`(영문 분류) + `<h1>`(영문, 메뉴 이름과 맞춤) + 한국어 부제 한 줄. 홈만 제목 블록이 없습니다.

**캐시 버스터**: 모든 로컬 `<link>`·`<script>`에 `?v=YYYYMMDD-N`. CSS/JS를 고치면 그 값을 올려야 Pages 캐시가 갱신됩니다. `theme.css`·`site-header.js`는 홈 포함 전 페이지에 들어 있으므로 버전을 한꺼번에 바꿉니다.

**모바일 주의점**

- 숨겨진 탭의 canvas는 폭이 0이므로 직전 CSS 폭을 씁니다(`zone-awareness.js`의 `canvasContext`). 장치 픽셀 폭을 쓰면 iOS Safari에서 주소창이 움직일 때마다(resize) 캔버스가 커져 깨집니다.
- 넓은 시각화는 반쪽 영역 밖으로 라벨이 나가 가로 스크롤을 만들기 쉽습니다. 390px에서 `document.documentElement.scrollWidth`가 화면 폭과 같은지 확인합니다.
- Swing/Take 프로필은 830px 이하에서 데스크톱 레이아웃을 이미지로 보여줍니다(`profile.js`, 화면 밖 1440px iframe에서 html2canvas 캡처). html2canvas 1.4.1은 `color-mix()` 등 최신 CSS 색 함수를 읽지 못하므로 캡처 대상에는 쓰지 않습니다.

#### 웹 도구 하네스

새 도구는 손으로 복사하지 말고 생성 스크립트로 만듭니다. 규격이 들어간 골격을 만들고, 메뉴(`TOOLS`) 등록, 같은 이름·순서의 홈 카드(그림은 빈 자리) 추가, 전 페이지 `site-header.js` 버전 올림까지 합니다. 썸네일만 직접 만듭니다.

**메뉴·홈 카드·썸네일은 한 몸입니다.** 홈 카드(`web/index.html` `.visual-card`)는 `TOOLS`와 같은 순서, 카드 제목은 메뉴 이름과 같아야 합니다. 썸네일은 `scripts/visual_thumbnails.json`에 캡처 설정(페이지의 `?thumb=1` + `[data-thumbnail-target]`)을 두고 `python scripts/generate_visual_thumbnails.py`로 600×600(@2x) WebP를 만듭니다. 썸네일 대상 화면을 바꾸면 다시 생성하고, 카드 `<img>`의 `?v=`를 올립니다. Blocking 카드만 인라인 SVG입니다.

```bash
python scripts/new_web_tool.py strike-zone --title "Strike Zone" --eyebrow "Pitching" --subtitle "투수별 스트라이크존 판정"
#   --nav-label "메뉴 이름"   메뉴 이름을 제목과 다르게
#   --no-nav                 메뉴에 넣지 않는 하위 페이지 (site-header.js ALIASES에 상위 도구를 직접 지정)
python scripts/web_contract.py     # 전 페이지 규격 검사. 위반이 있으면 목록 출력 후 exit 1
```

| 구성 | 역할 |
|---|---|
| `scripts/new_web_tool.py` | 새 도구 골격 생성 + 메뉴 등록 + 홈 카드 추가 + `site-header.js` 버전 올림 |
| `scripts/web_contract.py` | 규격 검사: body 첫 요소 `site-header.js`, `main.site-main` 하나, `.page-title`(eyebrow·h1), theme.css 마지막 로드, 캐시 버스터, `theme.css`·`site-header.js` 버전 일치, `TOOLS`/`ALIASES`와 디렉터리 일치, 홈 카드 순서·제목이 메뉴와 같고 썸네일 파일 존재·`?v=` |
| `tests/test_web_contract.py` | 현재 페이지·생성 도구 통과, 흔한 실수·카드 불일치 감지 (pytest가 수집) |
| `scripts/generate_visual_thumbnails.py` + `visual_thumbnails.json` | 홈 카드 썸네일 캡처 (Playwright Chromium 필요) |
| `.github/workflows/web_contract.yml` | `web/**` push·PR에서 같은 검사 + `.cjs` 레이아웃 테스트. 배포는 막지 않음 |

규격 자체를 바꿀 때는 `theme.css`·`site-header.js`를 고치고 `web_contract.py`의 검사와 생성 템플릿(`new_web_tool.py`)을 같이 맞춥니다. 화면 변경은 1440px·390px 스크린샷으로 기존 도구와 비교합니다.

### Python 모듈 지도

| 모듈 | 역할 |
|---|---|
| `http_client.py`, `naver.py` | VB API, Naver 릴레이 클라이언트 |
| `collector.py`, `parser.py`, `state_machine.py` | raw 페이로드 → games/events/pitches 행, 주자·득점 상태 전이 |
| `curated.py` | Parquet schema, 좌표 정규화, `table_digest`, 원자적 partition 교체, fail-closed 읽기 |
| `build_curated.py` | curated 재빌드·검증 진입점 |
| `compact_curated.py` | 일회성 월별 partition 마이그레이션. legacy 삭제 전 read-back 검증 2회 |
| `metric_state.py` | metric별 입력·코드·의존 hash로 빌드 필요 여부 판정 |
| `dataset_summary.py` | `data/curated/summary.json` 생성 (footer만 읽음) |
| `storage.py`, `validation.py` | 수집 manifest, 라인스코어 대조 |
| `swing_take.py` | Swing/Take 분류와 decision pitch 테이블 (하위 metric 공통 입력) |
| `zone_decision.py` | APR(wRC+형 판단 가치) · ZA(존 판단, 옛 SBJ) · DV/100 · SA. 지표 수식은 `zone_awareness()`, `decision_value()`, `profile_summary()`, `add_apr()`에만 둡니다 |
| `plate_decision_v1.py` | zone_decision이 쓰는 모델 부품: p_swing/p_zone 분류기·RV 회귀기 설정, 특징 인코더, 구장 보정표 경로(`_movement_adjust`). 옛 v1 파이프라인 자체는 제거됨 |
| `plate_discipline.py` | 구역별 Swing%/Contact%, 회귀 잔차, 클러스터 연구표 |
| `zone_profile.py` | 0.5 ft 존 격자 프로필 |
| `pitch_types.py`, `batter_stance.py`, `teams.py` | 투구 단위 metric이 공유하는 구종 코드, 타석 방향, 타자 소속 팀 이력 |
| `publish.py` | web/data·report JSON 쓰기, 선수 shard 교체, 시즌 catalog 갱신. 바이트 형식(구분자·들여쓰기·끝 줄바꿈)이 웹 계약입니다 |
| `pitch_arsenal.py` | 구종 사용률·구속·HB/IVB. 10구 이하·구사율 5% 미만 구종은 구속·무브먼트·탄착이 같으면 주력 구종에 묶어 표시(원 라벨은 `merged_from`) |
| `movement_calibration.py` | Pitch Arsenal HB/IVB 보정: 투수×구종 + 구장×날짜 고정효과, 탄착 위치항, 이상치 재적합·수축 |
| `blocking.py` | Catcher Blocks Above Average (5-fold 경기 단위 CV 로지스틱) |
| `arm_angle.py` | 55 ft 기준 팔각도 입력 준비 |
| `leaderboard_vb.py` | 2026 라이브 리더보드 (CI 밖에서 수동 실행) |
| `export_excel.py` | Excel publication |

모델 설계 근거와 한계는 `analysis/zone_decision/README.md`, `analysis/plate_decision_v1/`에 있습니다. 지표 수식을 바꾸기 전에 읽습니다.

### 모듈 코딩 원칙

리팩터링·기능 추가 모두 이 원칙을 따릅니다. 목적은 산출물을 바꾸지 않으면서 읽고 고치기 쉬운 코드를 유지하는 것입니다.

- **한 모듈, 한 책임.** metric 모듈은 "읽기 → 집계 → 산출물 쓰기"만 합니다. 다른 metric이 가져다 쓰는 helper가 생기면 그 metric 모듈에 두지 말고 작은 공용 모듈(`pitch_types`, `batter_stance`, `teams`, `publish`처럼)로 옮깁니다. 다른 모듈이 `pitch_arsenal`에서 구종 코드를 import하던 식의 의존이 다시 생기면 안 됩니다.
- **함수는 한 단계만.** 빌더 함수는 단계 함수를 순서대로 부르는 얇은 조립부로 둡니다(`build_pitch_arsenal`, `build_zone_profiles`, `cli.main` 참고). 한 함수가 로딩·누적·지표 계산·파일 쓰기를 모두 하면 단계별로 나눕니다. radon 복잡도 D(21) 이상이 신호입니다.
- **같은 기능은 한 곳에만.** 값 정규화는 `curated._number`, JSON 쓰기·shard 교체·시즌 catalog는 `publish.py`를 씁니다. 새로 복사본을 만들지 말고 import합니다. 이름은 같은데 동작이 다른 helper(예: `blocking._number`는 NaN 반환)는 합치지 않습니다.
- **안 쓰는 코드는 지웁니다.** 프로덕션 경로(`cli._exports()`, `--only`, 워크플로)에서 닿지 않고 테스트만 부르는 함수·모듈은 테스트와 함께 제거합니다. 커밋된 산출물(`exports/`, `web/data/`)은 코드가 사라져도 지우지 않습니다 — 데이터 삭제는 별도 결정입니다.
- **의존 hash를 같이 고칩니다.** metric 모듈이 새 패키지 모듈을 import하면 `metric_state.CODE`에 그 파일을 추가합니다. `tests/test_metric_state.py`가 import 폐포가 `CODE`에 포함되는지 검사합니다.
- **얼린 파일은 리팩터링하지 않습니다.** 다음 파일은 내용 변경 자체가 부작용을 냅니다.
  - `parser.py`, `state_machine.py`, `validation.py`, `collector.py`, `storage.py`, `curated.py`, `naver.py`: push하면 `daily_update`가 2026 원본 전체를 `--rebuild-from-raw --refresh-naver`로 네트워크 재처리합니다.
  - `curated.py`, `vb_arm_angle.py`, `arm_angle_calibration.py`, `trackman_arm_angle.py`: sha256이 `data/models/estimated_arm_angle_v1.json`과 `analysis/arm_angle/results/*.json`에 고정되어 있습니다.
  - 이 파일들의 private helper가 필요하면 고치지 말고 import합니다(`curated._number`처럼).
- **리팩터링은 산출물 바이트 동일성으로 검증합니다.** 테스트 통과만으로는 부족합니다. 기준 커밋과 변경 커밋에서 같은 빌더를 강제로 실행해 `web/data`, `data/metrics`, `exports` 파일 hash를 비교합니다. 코드 hash를 기록하는 필드(`report.json`의 `reproducibility.source_sha256`, movement_zones의 `code_sha256`)만 달라야 정상입니다. 같은 기준 커밋을 두 번 돌려 결정성부터 확인합니다.
- **테스트 없는 경로는 먼저 테스트를 씁니다.** 네트워크 수집처럼 테스트가 없는 코드를 나눌 때는 가짜 client로 현재 동작을 고정하는 테스트(`tests/test_cli_collection.py`)를 먼저 통과시킨 뒤 나눕니다.

## 작업 시 지켜야 할 규칙

- **미확인과 0을 구분합니다.** `naver_match_status`가 `unavailable`/`unmatched`이면 폭투·포일이 0이 아니라 미확인입니다. 공개 PBP에 없는 주자 이벤트는 추측하지 않고 `parse_status=unknown`으로 둡니다. 파생 컬럼의 null은 "계산 불가"이고 `false`는 "관측된 false"입니다.
- **공식 라인스코어가 최종 기준**입니다. PBP 스냅샷과 충돌하면 `SOURCE_SCORE_CONFLICT`를 남기고 라인스코어를 씁니다.
- **표본 미달은 숨기지 말고 표시**합니다. Swing/Take·ZA는 300 pitches seen, 리더보드는 타자 200 PA / 투수 50 IP가 기준선입니다.
- **시즌을 섞지 않습니다.** 연도별 Run Value와 리그 평균은 해당 시즌 canonical shard만으로 계산합니다.
- **지표 표현을 과장하지 않습니다.** BAA는 KBO 공개 데이터 적용 실험 지표이며 MLB Statcast와 상호 비교 가능하지 않습니다. 기존 Decision Run은 실제 선택 결과가 섞인 진단값이라 counterfactual Decision Value로 부르지 않습니다. plate discipline 클러스터 번호는 우열 등급이 아닙니다.
- `exports/visualbaseball_savant_2026_latest.xlsx`는 커밋하지 않습니다. GitHub Release `visualbaseball-data-latest`로 배포합니다. `data/raw/naver/`, `data/pending/`도 gitignore 대상입니다.
- 탐색 비용은 위의 **데이터를 싸게 읽는 법**을 따릅니다. `summary.json` → `schema.json` → 필요한 행만.

## CI

| 워크플로 | 시점 | 하는 일 |
|---|---|---|
| `daily_update.yml` | 매일 15:00 UTC (KST 00:00) + 파이프라인 입력 경로 push | pytest + `.cjs` 레이아웃 테스트 → 수집 또는 재생성 → Excel을 Release에 업로드 → `data`, `web/data`, `exports/*.csv` 커밋 |
| `sample_reconcile.yml` | 매주 수 04:17 UTC | sample 모드 + `--auto-reconcile` |
| `refresh_completed.yml` | 매주 월 03:37 UTC | 전 경기 reconcile |
| `rebuild_swing_take.yml` | 수동 | Swing/Take 프로필 강제 재빌드 |
| `deploy-pages.yml` | `web/**` push, daily_update 성공 후 | `web/`을 Pages로 배포 |
| `web_contract.yml` | `web/**` push·PR | 페이지 공통 규격 검사(`scripts/web_contract.py`) + `.cjs` 레이아웃 테스트. 배포는 막지 않음 |

**새 경기 수집은 명시적으로 의도한 실행에서만 합니다.** 스케줄, 수동 실행(`workflow_dispatch`), `.github/refresh-completed-request` 커밋 세 가지입니다. 일반 파이프라인 코드 push는 네트워크를 타지 않고 `--exports-only`로 이미 있는 curated 데이터에서 산출물만 다시 만듭니다. 단, parser·상태 전이·canonical 변환·Naver 보강 코드가 바뀌면 `daily_update`가 2026의 보존된 원시 PBP를 `--rebuild-from-raw --refresh-naver`로 다시 처리한다. 2022~2025 전체 원본 재수집은 `refresh_completed` 수동 실행에서 시즌을 선택해 수행한다. `web/**`는 출력물이라 어떤 코드도 입력으로 읽지 않으므로 트리거에 없습니다 — 뷰만 고치면 이 워크플로가 돌지 않습니다.

**커밋되는 산출물에 벽시계 시각을 무조건 쓰지 마십시오.** 내용이 같은 재실행이 파일을 바꿔 놓으면 워크플로의 `git diff --cached --quiet` 가드가 무력화되고 빈 데이터 커밋이 쌓입니다. 시각 필드는 `last_collected_at`·`revision`처럼 **무언가 실제로 달라졌을 때만** 갱신합니다 (`curated.write_game`의 `last_checked_at`, `dataset_summary`의 `generated_at`이 이 규칙을 따릅니다). `pitch_sha256`이 `fetched_at`·`source_url`·`source_hash`를 digest에서 제외하는 것도 같은 이유입니다.

기본 브랜치는 `master`입니다. `.github/refresh-completed-request` 파일을 커밋하면 다음 daily 실행이 전체 재수집으로 동작하고, 실행 후 워크플로가 그 파일을 지웁니다.
