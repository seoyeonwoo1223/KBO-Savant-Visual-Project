# 시스템 구조

"무엇이 어디에 있고 어떻게 흐르는가"를 설명합니다. 작업 규칙은 [conventions.md](conventions.md), 결정의 이유는 [decisions/](decisions/README.md)에 있습니다.

## 데이터 흐름: raw → curated → metric → publication

```
data/raw/<season>/<game_id>.json            Visual Baseball 원본 PBP (+ raw/naver/ 조인 캐시, gitignore)
  ↓ parser.py / collector.py / state_machine.py
data/curated/{pitches,events,games}/season=<year>/<game_id>.parquet   canonical (game shard 레이아웃)
                                     …/month=MM.parquet   compact 후 레이아웃
data/curated/partition-index.json           compact 후에만 존재. 게임 → 월 + 테이블 digest (열지 말 것)
data/curated/summary.json                   사람·에이전트용 요약 (여기부터 읽을 것)
data/curated/schema.json                    테이블별 컬럼·타입 계약
data/curated/sources/…json                  수집·검증 manifest + raw/pitch/schema sha256
data/curated/audit/…jsonl                   raw 변경 이력
  ↓ 각 metric 모듈 (data/metrics/_state/가 metric별 입력·코드 hash 보관)
data/metrics/<metric>/<season>/…parquet|json
  ↓ publication only
web/data/**.json · exports/*.xlsx|csv · GitHub Release
```

- **핵심 계약**: `web/`과 `exports/`는 출력물이며 입력으로 읽지 않습니다([0001](decisions/0001-web-is-output-only.md)). metric은 `curated.load_rows()`로 curated partition만 읽습니다. 유일한 외부 workbook 입력은 `data/park_adjustments/<season>_VB_Park_Adjustment_v1.0.xlsx` 구장 보정표이고, ZA/SBJ의 p_swing 경로(`plate_decision_v1._movement_adjust`)만 읽습니다. Pitch Arsenal은 `movement_calibration.py`(TrackMan으로 검증한 구장×날짜·탄착 위치 보정)를 씁니다. 세부 계약은 [curated-data.md](curated-data.md).
- **재생성 순서**는 `cli._exports()`가 단일 소스입니다: Excel → arm_angle 입력 → swing_take → (plate_discipline, zone_decision) → zone_profile → pitch_arsenal → blocking. `swing_take`의 `decision_pitches.parquet`가 판단 지표 전체의 입력이므로 Swing/Take를 건드리면 하위 metric이 전부 재생성됩니다.
- **증분성**: partition은 원자적으로 교체되고 `pitch_sha256`가 같으면 다시 쓰지 않습니다. provider가 파싱과 무관한 필드를 바꾸면 `raw_sha256`만 바뀝니다. metric은 `metric_state.needs_build()`가 입력·코드·의존 파일 hash로 개별 판정합니다. 중단 후 재실행은 안전합니다.
- **수집 모드**: `recent`는 신규·미완료·실패 게임과 최근 7일 확정 경기, `sample`은 30일 이상 지난 경기 8개를 균등 추출해 schema/y0/pitch hash 변화를 감시, `reconcile`은 전 경기 재수집.

## partition 레이아웃 (시즌별로 다름)

| 시즌 | 레이아웃 | raw 복구 경로 |
|---|---|---|
| 2026 | month (21 partition) | `data/raw/2026` |
| 2025 | month (24 partition) | `seasons/2025` |
| 2022–2024 | **game shard** (각 2,160개) | **없음** |

- 판정은 `curated._season_is_compact()` 하나만 씁니다(디스크에 `month=*.parquet`이 실제로 있는지). `index["layout"]`은 저장소 전역 키라 시즌 판정에 쓸 수 없습니다.
- `partition-index.json`의 `tables` digest는 Parquet에 저장된 내용의 hash이며 `curated.table_digest()` 하나만 씁니다.
- `pq.ParquetFile()` open 성공은 무결성 증거가 아닙니다. 삭제 전 검증은 전체 read-back + digest 대조(`compact_curated.verify_partitions()`).
- game layout 읽기는 `month=*.parquet`을 무시합니다(실패한 마이그레이션 잔여물과 섞이면 행이 두 배).
- 손상·누락 partition은 fail-closed(`FileNotFoundError`).
- 배경: [0002](decisions/0002-curated-partition-layout.md).

## 좌표계

- **`px` / `pz`는 feet**, 홈플레이트 원점. VB `pz`는 모든 시즌 플레이트 앞면(y=17/12 ft) 값이지만 `px`는 **2024부터 중간면(y=8.5/12 ft, ABS 좌우 판정면)** 값입니다(2023까지는 앞면). 2024+에서 궤적으로 다시 계산한 앞면 x와 최대 약 4cm 다른 것이 정상입니다(`analysis/trajectory_audit/`). 플레이트 반폭 `10/12 ft`, 존 상하한은 투구별 `sz_top`/`sz_bottom`. 정규화 좌표는 존 경계가 ±1이고 `d = max(|x|, |z|)`로 Heart ≤2/3, Shadow-in ≤1, Shadow-out ≤4/3, Chase ≤2, Waste >2.
- **저장되는 x 계열은 모두 포수 시점**: `release_x_50`/`release_x_55`(cm), `horizontal_movement_cm`(raw `hMov`), `web/data/**`의 `horizontal_break_in`.
- **Pitch Plot**(`web/pitch-arsenal/`)은 투수 시점이 기본이고 `toPitcherView()`가 `average`를 음수화하며 `low_75`/`high_75`를 맞바꿉니다(구간 뒤집기를 빠뜨리면 타원이 어긋남).
- **Movement Zones**(`web/movement-zones/`)는 포수 시점이 기본입니다. 원본 범위표는 투수 시점이고 `handFactor()`(RHP `-1`, LHP `+1`)를 `viewZone()`에서 HB에 곱합니다. IVB는 뒤집지 않습니다. 숫자 라벨은 `mirroredHbLabel()`이 부호를 다시 씁니다(HB 데이터를 고치면 라벨 함수도 같이). 축 라벨 `3B < MOVES TOWARD > 1B`와 arm angle 보조선도 같은 factor를 씁니다.
- Approach decision map, Zone Profile 0.5 ft 격자는 포수 시점입니다.
- `y0`는 raw 그대로 보존(`source_y0`). 50/55 ft 평면 값은 등가속도 운동학 파생값이며, 해가 없거나 y0가 50/55가 아니면 `trajectory_status`가 `valid`가 아니고 파생 컬럼은 null(행은 지우지 않음).

## 웹

`web/<tool>/{index.html, <tool>.css, <tool>.js}` 한 세트가 한 도구입니다. 빌드·번들러·프레임워크 없이 순수 ES + fetch이고, GitHub Pages가 `web/`을 그대로 루트로 서빙합니다.

| 파일 | 역할 |
|---|---|
| `web/theme.css` | 전 페이지 공통: `--kbo-*` 색 토큰, 2단 헤더, `main.site-main` 폭(1440px)·여백, `.page-title` 제목 블록 |
| `web/site-header.js` | `<body>` 맨 앞에서 로드. 브랜드 줄(스크롤 시 사라짐) + 상단 고정 메뉴 줄. 메뉴 목록 `TOOLS`, 하위 페이지 `ALIASES` |
| `web/<tool>/<tool>.css` | 도구 레이아웃 |
| `web/index.html`, `web/home.css` | 홈. 카드 순서 = `TOOLS` 순서 |
| `web/styles.css` | `swing-take`만 쓰는 구버전 시트 |
| `web/assets/thumbnails/*.webp` | 홈 카드 썸네일 (`scripts/generate_visual_thumbnails.py`) |

| 메뉴 | 경로 | 데이터 |
|---|---|---|
| Leaderboards | `web/leaderboards/` | `web/data/leaderboards/` |
| Zone Profile | `web/zones/` | `web/data/zones/` (리그 칸 집계 `<season>/league/<role>.json`) |
| Swing/Take | `web/swing-take/`, `web/profiles/` | `web/data/swing_take/` |
| Approach | `web/zone-awareness/` | `web/data/zone_awareness/` |
| Pitch Plot | `web/pitch-arsenal/` | `web/data/pitch_arsenal/` |
| Movement Zones | `web/movement-zones/` | `web/data/movement_zones/` |
| Blocking | `web/blocking/` | `web/data/blocking/` |
| Trendline | `web/trendline/` | `web/data/trendline/` (선수 경기별·리그 일자별 카운트) |

배경: [0003](decisions/0003-savant-two-tier-header.md)~[0009](decisions/0009-web-contract-non-blocking.md).

## Python 모듈 지도

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
| `zone_decision.py` | APR · ZA(옛 SBJ) · DV/100 · SA. 지표 수식은 `zone_awareness()`, `decision_value()`, `profile_summary()`, `add_apr()`에만 |
| `plate_decision_v1.py` | zone_decision의 모델 부품: p_swing/p_zone 분류기·RV 회귀기 설정, 특징 인코더, 구장 보정표 경로 |
| `plate_discipline.py` | 구역별 Swing%/Contact%, 회귀 잔차, 클러스터 연구표 |
| `zone_profile.py` | 0.5 ft 존 격자 프로필 |
| `pitch_types.py`, `batter_stance.py`, `teams.py` | 투구 단위 metric 공용: 구종 코드, 타석 방향, 타자 소속 팀 이력 |
| `publish.py` | web/data·report JSON 쓰기, 선수 shard 교체, 시즌 catalog. 바이트 형식이 웹 계약 |
| `pitch_arsenal.py` | 구종 사용률·구속·HB/IVB. 소수 구종은 조건이 맞으면 주력 구종에 묶어 표시(`merged_from`) |
| `movement_calibration.py` | Pitch Arsenal HB/IVB 보정: 투수×구종 + 구장×날짜 고정효과, 탄착 위치항 |
| `movement_zones.py` | 팔각도별 기대 무브먼트(Dynamic DZ)와 헛스윙률 구역 |
| `blocking.py` | Catcher Blocks Above Average (5-fold 경기 단위 CV 로지스틱) |
| `arm_angle.py` | 55 ft 기준 팔각도 입력 준비 |
| `leaderboard_vb.py` | 2026 라이브 리더보드 (CI 밖에서 수동 실행) |
| `export_excel.py` | Excel publication |

## CI

| 워크플로 | 시점 | 하는 일 |
|---|---|---|
| `daily_update.yml` | 매일 15:00 UTC (KST 00:00) + 파이프라인 입력 경로 push | pytest + `.cjs` → 수집 또는 재생성 → Excel을 Release에 업로드 → `data`, `web/data`, `exports/*.csv` 커밋 |
| `sample_reconcile.yml` | 매주 수 04:17 UTC | sample 모드 + `--auto-reconcile` |
| `refresh_completed.yml` | 매주 월 03:37 UTC | 전 경기 reconcile (수동 실행 시 2022–2026 시즌 선택) |
| `rebuild_swing_take.yml` | 수동 | Swing/Take 프로필 강제 재빌드 |
| `deploy-pages.yml` | `web/**` push, daily_update 성공 후 | `web/`을 Pages로 배포 |
| `web_contract.yml` (Harness checks) | `web/**`, 하네스·문서 push·PR | 웹 규격, `.cjs` 전부, 하네스 테스트, 문서 링크. 배포는 막지 않음 |

- **새 경기 수집은 명시적으로 의도한 실행에서만**: 스케줄, `workflow_dispatch`, `.github/refresh-completed-request` 커밋. 일반 파이프라인 코드 push는 `--exports-only`로 산출물만 재생성합니다. 단, parser·상태 전이·canonical 변환·Naver 보강 코드가 바뀌면 2026 원본을 `--rebuild-from-raw --refresh-naver`로 다시 처리합니다.
- `web/**`는 출력물이라 `daily_update` 트리거에 없습니다.
