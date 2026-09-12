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

`.cjs` 테스트는 `web/pitch-arsenal/pitch-arsenal.js`의 렌더 함수를 `vm`으로 잘라서 실행합니다. 함수 이름(`renderVelocity`, `renderFrequency`, `movementPoint`, `showTooltip`)이 슬라이스 경계이므로 이름을 바꾸면 테스트가 조용히 깨집니다. pytest가 수집하지 않으므로 4개 워크플로에서 별도 스텝으로 실행합니다.

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
python -m visualbaseball.cli --season 2025 --storage-root seasons/2025   # 과거 시즌
python -m visualbaseball.build_curated --season 2026 --validate
python -m visualbaseball.compact_curated --season 2026   # game shard → 월별 partition (일회성)
python -m visualbaseball.dataset_summary                 # summary.json 갱신
```

수집 모드: `recent`는 신규·미완료·실패 게임과 최근 7일 확정 경기, `sample`은 30일 이상 지난 경기 8개를 균등 추출해 schema/y0/pitch hash 변화를 감시, `reconcile`은 전 경기 재수집입니다.

개별 metric만 다시 만들 때는 해당 모듈을 직접 실행합니다. `__main__`이 있는 모듈: `build_curated`, `cli`, `leaderboard_vb`, `pitch_arsenal`, `plate_decision_v1`, `plate_discipline`, `zone_awareness_v2`, `zone_decision`, `zone_profile`.

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

**핵심 계약**: `web/`과 `exports/`는 출력물일 뿐이며 어떤 코드도 이것을 입력으로 읽지 않습니다. metric은 `curated.load_rows()`로 curated partition만 읽습니다 (Zone Awareness는 Excel/legacy cache fallback이 금지되어 있습니다). 유일한 외부 workbook 입력은 `pitch_arsenal`이 읽는 `data/park_adjustments/<season>_VB_Park_Adjustment_v1.0.xlsx` 구장 보정표입니다. 세부 계약은 `docs/curated-data.md`에 있습니다.

**재생성 순서**는 `cli._exports()`가 단일 소스입니다. Excel → arm_angle 입력 → swing_take → (plate_discipline, zone_decision 또는 plate_decision_v1) → zone_profile → pitch_arsenal → blocking. `swing_take`가 만드는 `data/metrics/swing_take/<season>/decision_pitches.parquet`가 그 뒤 판단 지표 전체의 입력이므로, Swing/Take를 건드리면 하위 metric이 전부 함께 재생성되어야 합니다.

**증분성**: partition은 원자적으로 교체되고, `pitch_sha256`가 같으면 다시 쓰지 않습니다. provider가 파싱과 무관한 필드를 바꾸면 `raw_sha256`만 바뀌고 partition은 그대로입니다. metric은 `metric_state.needs_build()`가 입력·코드·의존 파일 hash로 개별 판정하므로, 하나가 바뀌어도 나머지는 건너뜁니다. 중단 후 재실행은 안전합니다.

**레이아웃은 두 가지이고 코드가 둘 다 지원합니다.** 커밋된 데이터는 아직 경기별 shard(game layout)이고, `python -m visualbaseball.compact_curated --season YYYY`를 돌리면 월별 partition(month layout)으로 바뀝니다. 마이그레이션은 시즌별 일회성이며 아직 실행되지 않았습니다. `summary.json`의 `layout` 필드가 현재 상태를 알려줍니다.

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

- **`px` / `pz`는 feet**, 홈플레이트 원점 기준입니다. 플레이트 반폭은 `10/12 ft`, 존 상하한은 투구별 `sz_top`/`sz_bottom`입니다. 정규화 좌표는 존 경계가 ±1이 되도록 맞춘 값이고, `d = max(|x|, |z|)`로 Heart ≤2/3, Shadow-in ≤1, Shadow-out ≤4/3, Chase ≤2, Waste >2 구역을 나눕니다.
- **저장되는 x 계열은 모두 포수 시점(catcher view)** 입니다. `release_x_50` / `release_x_55`(cm), `horizontal_movement_cm`(raw `hMov`), `web/data/**`의 `horizontal_break_in` 전부 포수 시점입니다.
- **투수 시점은 화면에서만 부호를 뒤집습니다.** `web/pitch-arsenal/pitch-arsenal.js`의 `toPitcherView()`가 `average`를 음수화하고 `low_75`/`high_75`를 서로 맞바꿉니다(구간 뒤집기를 빠뜨리면 타원이 어긋납니다). 이 페이지의 기본값은 투수 시점입니다.
- **`web/movement-zones/`는 반대로 포수 시점이 기본**입니다. 원본 범위표는 투수 시점이고, `handFactor()`(RHP `-1`, LHP `+1`)를 `viewZone()`에서 HB에 곱해 미러링합니다. IVB는 절대 뒤집지 않습니다. 숫자 범위 라벨은 `mirroredHbLabel()`이 부호 문자를 따로 다시 씁니다 — HB 데이터를 고칠 때 라벨 함수도 같이 손봐야 합니다. 축 라벨 `3B < MOVES TOWARD > 1B`와 arm angle 보조선 방향도 같은 factor를 씁니다.
- `web/zone-awareness/`의 decision map, `web/zones/`의 0.5 ft 존 격자는 포수 시점입니다.
- `y0`는 raw 그대로 보존하고 `source_y0`로도 노출합니다. 50 ft / 55 ft 평면 값은 등가속도 운동학으로 재계산한 파생값이며, 해가 없거나 y0가 50/55가 아니면 `trajectory_status`가 `valid`가 아니고 파생 컬럼은 null로 남습니다(행을 지우지 않습니다).

### 웹 페이지 구조

`web/<tool>/{index.html, <tool>.css, <tool>.js}` 한 세트가 한 도구입니다. 빌드·번들러·프레임워크 없이 순수 ES + fetch입니다.

CSS는 **두 층**입니다.

- `theme.css` — 전 페이지 공통. `--kbo-*` 색 토큰, 흰 배경, 링크·입력·테이블 테두리 색을 정의합니다. **반드시 페이지 전용 CSS 뒤에 로드**해서 마지막에 덮어쓰게 합니다 (`movement-zones`만 순서가 반대이니 그 페이지 색을 손볼 땐 주의).
- `<tool>.css` — 해당 도구 레이아웃. `styles.css`는 홈과 `swing-take`만 쓰는 구버전 공통 시트이고, `home.css`는 홈 전용입니다. 새 도구는 `styles.css`를 끌어오지 말고 전용 CSS + `theme.css` 조합을 따릅니다.

모든 `<link>`에 `?v=YYYYMMDD-N` 캐시 버스터가 붙어 있습니다. **CSS를 고치면 해당 쿼리 값을 올려야** Pages 캐시가 갱신됩니다. `theme.css` 버전은 8개 페이지에 전부 들어 있으므로 한꺼번에 바꿔야 합니다.

데이터는 페이지 기준 `../data/<metric>/<season>/…`을 fetch합니다. 선수 단위 상세는 `players/<shard>.json`으로 샤딩되어 있고 시즌 목록은 각 metric 디렉터리의 `index.json`에 있습니다.

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
| `zone_decision.py` | ZA v7 · DV / DV+ / SA. 지표 수식은 `zone_awareness()`, `decision_value()`, `profile_summary()`에만 둡니다 |
| `zone_awareness_v2.py`, `plate_decision_v1.py` | 이전 세대 모델. 2022–2023 legacy 시즌과 팀 이력 조회에 계속 쓰입니다 |
| `plate_discipline.py` | 구역별 Swing%/Contact%, 회귀 잔차, 클러스터 연구표 |
| `zone_profile.py` | 0.5 ft 존 격자 프로필 |
| `pitch_arsenal.py` | 구종 사용률·구속·HB/IVB, `data/park_adjustments/` 오프셋 적용 |
| `blocking.py` | Catcher Blocks Above Average (5-fold 경기 단위 CV 로지스틱) |
| `arm_angle.py` | 55 ft 기준 팔각도 입력 준비 |
| `leaderboard_vb.py`, `leaderboard_park_factor.py` | 2026 라이브 리더보드, 구장 PF |
| `export_excel.py` | Excel publication |

모델 설계 근거와 한계는 `analysis/zone_decision/README.md`, `analysis/plate_decision_v1/`에 있습니다. 지표 수식을 바꾸기 전에 읽습니다.

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
| `daily_update.yml` | 매일 15:00 UTC (KST 00:00) + 관련 경로 push | pytest + `.cjs` 레이아웃 테스트 → `cli` recent 수집 → Excel을 Release에 업로드 → `data`, `web/data`, `exports/*.csv` 커밋 |
| `sample_reconcile.yml` | 매주 수 04:17 UTC | sample 모드 + `--auto-reconcile` |
| `refresh_completed.yml` | 매주 월 03:37 UTC | 전 경기 reconcile |
| `rebuild_swing_take.yml` | 수동 | Swing/Take 프로필 강제 재빌드 |
| `deploy-pages.yml` | `web/**` push, daily_update 성공 후 | `web/`을 Pages로 배포 |

기본 브랜치는 `master`입니다. `.github/refresh-completed-request` 파일을 커밋하면 다음 daily 실행이 전체 재수집으로 동작하고, 실행 후 워크플로가 그 파일을 지웁니다.
