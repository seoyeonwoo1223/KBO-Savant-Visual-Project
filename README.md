# KBO Savant Project

2026 KBO 공개 PBP에서 경기·이벤트·피치 데이터를 증분 수집해, 분석용 Parquet와 다운로드용 Excel, 브라우저용 CSV를 함께 만드는 프로젝트입니다.

## 어디에 무엇이 있나

| 경로 | 용도 |
|---|---|
| `src/visualbaseball/` | 현재 사용 중인 Python 수집기와 검증·내보내기 코드 |
| `data/raw/` | Visual Baseball 게임별 원본 PBP JSON 및 `raw/naver/`의 정규화된 Naver 릴레이 조인 캐시 |
| `data/curated/` | 월별 partition으로 저장한 canonical `games`, `events`, `pitches` Parquet, `partition-index.json`, source manifest/audit |
| `data/metrics/` | Swing/Take, ZA, Blocking, Arm Angle 등 지표별 파생 결과 |
| `data/leaderboards/source/` | 2026 리더보드 계산 원본, 리그 상수, PF 산출 입력 |
| GitHub Release `visualbaseball-data-latest` | 바로 내려받아 열 수 있는 최신 Excel 파일 |
| `exports/plate_discipline_research_2026.csv` | 타자별 선구안 베이스 스탯·회귀 잔차·프로필 클러스터 연구표 |
| `web/` | GitHub Pages 정적 뷰어 (아래 표) |
| `scripts/` | 로컬 프리뷰(`serve_web.py`), 웹 도구 생성·규격 검사, 데이터 감사·보정 스크립트 |

웹 도구 (상단 메뉴 순서):

| 메뉴 | 경로 | 내용 |
|---|---|---|
| Leaderboards | `web/leaderboards/` | 시즌별 타격·투구·수비 지표 검색과 정렬 |
| Zone Profile | `web/zones/` | 타자·투수별 0.5 ft 존 Swing·Whiff·Contact·In-play |
| Swing/Take | `web/swing-take/`, `web/profiles/` | 타자별 Swing/Take Run Value 프로필 (모바일은 이미지로 표시·저장) |
| Approach | `web/zone-awareness/` | APR·ZA·SA 판단 지표와 위치별 Decision Map |
| Pitch Plot | `web/pitch-arsenal/` | 구종 사용률·구속 분포·구장 보정 무브먼트 |
| Movement Zones | `web/movement-zones/` | 팔각도별 기대 무브먼트와 헛스윙률 구역 |
| Conditional Finder | `web/conditional-finder/` | 구종·구속·카운트·이벤트 조건으로 경기·타석·투구 찾기 |
| Blocking | `web/blocking/` | 실험적 Catcher Blocks Above Average |

## GitHub에서 열람·다운로드

최신 Excel은 저장소에 커밋하지 않고 [Latest KBO Savant data 릴리스](https://github.com/seoyeonwoo1223/KBO-Savant-Visual-Project/releases/tag/visualbaseball-data-latest)의 첨부 파일로 제공합니다. 이는 GitHub의 대용량 파일 제한을 피하면서 Git clone과 분석 작업의 불필요한 파일 읽기를 줄입니다. `web/`는 같은 데이터를 표와 무브먼트 산점도로 열람할 GitHub Pages 뷰어입니다. Pages를 한 번 활성화하면 아래 주소에서 볼 수 있습니다.

`https://seoyeonwoo1223.github.io/KBO-Savant-Visual-Project/`

로컬에서 확인할 때는 문서 루트가 `web/`이어야 한다. 페이지가 `../data/...`를 fetch하므로 저장소 루트에서 띄우면 데이터가 전부 404가 된다.

```powershell
python scripts/serve_web.py
```

개인 저장소라면 저장소 권한이 있는 계정으로 로그인해야 Excel과 Pages 데이터를 볼 수 있습니다. 더 큰 분석이나 스프레드시트 작업에는 Excel 파일을 사용하면 됩니다.

## 데이터 갱신 방식

수집기는 시즌 일정에서 **신규·미완료·실패 게임**과 최근 7일의 확정 경기를 다시 확인합니다. canonical 데이터는 월별 Parquet partition으로 저장되며, 변경 게임의 월 partition만 원자적으로 교체합니다. `data/curated/partition-index.json`이 게임·월·테이블 hash를 보유하므로 metric dependency 계산과 도구 탐색은 수천 개의 Parquet 파일을 순회하지 않습니다. metric별 input/code hash가 같으면 해당 metric과 웹·Excel 출력은 건너뜁니다. 세부 schema·hash·복구 계약은 [canonical data 문서](docs/curated-data.md)를 참고하십시오.

```powershell
python -m pip install -r requirements.txt -c constraints-za.txt
$env:PYTHONPATH = "src"
python -m visualbaseball.cli
python -m visualbaseball.build_curated --season 2026 --validate
pytest
```

`--fixture data/raw/2026/20260328HTSK0.json`로 오프라인 수집·내보내기 확인도 가능합니다.

과거 시즌은 원본과 Parquet을 별도 폴더에 두고 같은 Excel 스키마로 내보냅니다.

```powershell
python -m visualbaseball.cli --season 2025 --storage-root seasons/2025
```

이 명령은 `seasons/2025/data/`에 2025 수집 상태를 저장하고, `exports/visualbaseball_savant_2025_latest.xlsx`를 만듭니다.

### 2026 리더보드 계산 원본

`data/leaderboards/source/constants.xlsx`는 2026 KBO 리그 누적 상수와 VB 경기 결과로 계산한 구장 PF를 보관한다. `2026_leaderboard.xlsx`에는 이 상수 시트들을 숨김 시트로 통합했으며 외부 Excel 링크는 없다. 따라서 로컬 파일 경로나 `STATBASE/KBO리그/정규시즌/상수.xlsx` 없이도 수식을 다시 계산할 수 있다.

PF는 주 사용 홈구장을 기준으로 `(해당 팀들의 홈 경기 양 팀 득점/경기) ÷ (같은 팀들의 원정 경기 양 팀 득점/경기)`로 계산한다. 잠실은 LG·두산을 합산하고, 문학은 리더보드의 인천 항목에 연결한다. 사용한 기준일·누적 합계·출처는 `data/leaderboards/source/2026_inputs.json`에 기록한다.

2026 라이브 리더보드는 `PYTHONPATH=src python -m visualbaseball.leaderboard_vb`로 canonical games/pitches shard를 재집계한다. 타자는 200 PA, 투수는 50 IP 이상만 싣는다. 원자료에서 정확히 복원할 수 없는 도루·도실·자책점·승패·세이브·홀드와 타구 유형은 제외한다. `WAR*`는 타자의 수비·주루를 제외한 공격·포지션 보정 추정치와 투수의 FIP 기반 추정치다. 집계 기준일을 검증할 수 없는 2026 OAA 수비 자료는 리더보드에서 제외한다.

### 포수·폭투·포일 보강

`Pitches`에는 VB의 `y0`와 기존 운동학 필드(`x0`, `z0`, `vx0`…`az`)를 그대로 보존한다. Naver Sports 릴레이의 이닝별 투구 ID를 VB의 이닝·공수·타자·투수·투구 순번에 결합해 `catcher_id`, `catcher_name`, `is_wild_pitch`, `is_passed_ball`, `naver_pitch_id`를 추가한다. `naver_match_status=unavailable` 또는 `unmatched`는 **0이 아니라 미확인**이다.

특정 원본 경기를 검증·보강하려면 다음처럼 실행한다. 전체 시즌 재생성은 이닝별 릴레이 호출이 필요한 작업이므로 시즌별로 나누어 실행한다.

```powershell
python -m visualbaseball.cli --rebuild-from-raw --refresh-naver --game-id 20260328KTLG0
```

## Catcher Blocks Above Average

`web/blocking/`은 주자가 있거나 2스트라이크인 비접촉 투구를 블로킹 기회로 정의한다. 5-fold 경기 단위 교차검증 로지스틱 모델이 위치·구속·무브먼트·구종·릴리스 방향·타자 손잡이·주자/카운트 상태로 PB+WP 확률을 추정한다. 투구별 `예상 PB+WP - 실제 PB+WP`를 포수별로 합산한 값이 KBO BAA이며, 블로킹 런은 MLB와 같은 0.25 runs/block로 환산한다.

이 결과는 Baseball Savant의 개념과 표시 방식을 KBO 공개 데이터에 적용한 **실험 지표**다. 공개 원본에 포수의 사전 위치가 없으므로 MLB Statcast 지표와 동일한 모델 또는 상호 비교 가능한 값이 아니다. `data/metrics/blocking/2026/pitches.parquet`에 투구별 예상 확률과 기여도를, `web/data/blocking/2026/leaderboard.json`에 리더보드와 시각화 집계를 저장한다.

## 개발에 참여할 때

사람과 에이전트가 같은 규칙으로 일하도록 하네스를 네 부분으로 나눠 두었습니다.

| 무엇 | 어디 |
|---|---|
| 작업 지침 (에이전트가 작업 전에 읽는 지도) | [AGENTS.md](AGENTS.md) → [docs/conventions.md](docs/conventions.md) |
| 자동으로 막는 검사 | [docs/harness/constraints.md](docs/harness/constraints.md) |
| 결과를 확인하는 순서 (테스트·센서) | [docs/harness/feedback.md](docs/harness/feedback.md) |
| 결정과 이유 | [docs/decisions/](docs/decisions/README.md) |
| 시스템 구조 | [docs/architecture.md](docs/architecture.md) |

새 웹 도구는 `python scripts/new_web_tool.py`로 만들고, `python scripts/web_contract.py`로 규격을 확인합니다. 자세한 내용은 [docs/harness/README.md](docs/harness/README.md)를 참고하십시오.

## 검증 원칙

게임 최종 점수는 공개 PBP 스냅샷뿐 아니라 공식 라인스코어와도 대조합니다. 두 소스가 충돌하면 `SOURCE_SCORE_CONFLICT` 이벤트를 남기고 공식 라인스코어를 최종 기준으로 사용합니다. 공개 PBP가 제공하지 않는 주자 이벤트는 추측하지 않으며 `parse_status=unknown`으로 보존합니다.

SBJ 투구 사건의 신뢰도, 1군 TrackMan 대조 범위, 미매칭 사유를 남기는 한 번의 실행 절차는 [SBJ 데이터 신뢰 감사](docs/sbj-data-quality.md)를 참조하십시오. 감사 플래그는 원본 수정이나 공개 점수 변경이 아닙니다.

## 자동 갱신

`.github/workflows/daily_update.yml`은 한국 시간 매일 00:00에 테스트 후 신규·미완료·최근 7일 확정 경기만 갱신합니다. parser·상태 전이·canonical 변환·Naver 보강 코드를 바꾸는 push는 2026의 보존된 원시 PBP를 다시 파싱하고 Naver 보강도 새로 받습니다. 다른 코드 push는 기존 curated 데이터에서 산출물만 다시 만듭니다. 전체 reconcile은 주간 workflow 또는 수동 요청으로만 실행하며, 수동 `refresh_completed` workflow에서는 2022~2026 중 시즌을 골라 전체 재수집할 수 있습니다. canonical pitch shard가 Swing/Take 프로필의 단일 입력이며, 분석 입력이 바뀌면 프로필 JSON과 `data/metrics/swing_take/2026/decision_pitches.parquet`가 함께 재생성됩니다. 중간 분석 테이블인 Decision Pitches는 Excel에 넣지 않습니다. 분석 hash가 같으면 metric을 다시 만들지 않습니다.

## Swing/Take 프로필 기준

Zone Awareness는 canonical pitch/event shard만 입력으로 받으며 Excel·legacy cache로 fallback하지 않습니다.

프로필은 2026 KBO 정규시즌의 검증된 투구만 사용한다. 스윙은 헛스윙·파울·인플레이, 테이크는 콜드볼·콜드스트라이크와 타석 종료 사구로 분류한다. 최소 표시 기준은 **300 pitches seen**이며, 이 수치는 FanGraphs의 Swing/Take 분석에서 사용된 하한을 따른다. 300구 미만은 수치를 숨기지 않고 표본 미달로 표시한다.

검색 화면에서는 2022~2026 연도를 선택할 수 있다. 각 연도 Run Value와 리그 평균은 해당 시즌 canonical shard만으로 별도 계산하므로 서로 섞이지 않는다.

## Plate Discipline 연구 테이블

`src/visualbaseball/plate_discipline.py`는 Swing/Take 산출 직후 타자별 연구용 데이터를 만든다. `data/metrics/plate_discipline/2026/plate_discipline_pitches.parquet`에는 정규화 좌표와 Heart·Shadow-in·Shadow-out·Chase·Waste 구역, 스윙·컨택·단순 정답 여부를 저장한다. 같은 metric 디렉터리의 batter Parquet과 `exports/plate_discipline_research_2026.csv`에는 Z-Swing%, O-Swing%, 구역별 Swing%, Contact%, 단순 Strikezone Judgment%, Simple SEAGER 기준선, 기존 observed Decision Run, 회귀 잔차와 숫자형 클러스터를 저장한다.

회귀식과 클러스터 중심값·표본 기준·정의는 `data/metrics/plate_discipline/2026/plate_discipline_research.json`에 기록한다. 클러스터 번호는 우열 등급이 아니며, 타구속도·발사각이 없는 현재 원자료로는 PLV처럼 타자별로 좋은 타구가 될 확률까지 분리하지 않는다. 기존 Decision Run은 실제 선택의 결과가 포함된 진단값이므로 counterfactual Decision Value로 부르지 않는다.

## Zone Awareness v7 · 2024–2026

`src/visualbaseball/zone_decision.py`는 날짜 블록 교차적합으로 기대 스윙률과 take-only CalledStrike 대 Ball/HBP 확률을 추정한다. ZA는 `100 × mean((Swing - pSwing) × (2 × pZone - 1))`인 순수 존 판단 지표다. DV와 DV/100은 기존 가치 모델을 유지하며, DV+는 300구 이상 타자 기준 평균 100·표준편차 15로 환산한다.

`web/zone-awareness/`는 SA×ZA 산점도, 순위표, 다섯 구역의 가산 기여도와 위치별 판단 지도를 제공한다. 2022–2023은 개편 전 지표다. 학습·보정·60/20/20 날짜 평가 및 잔여 한계는 [모델 설명](analysis/zone_decision/README.md)에 기록한다. 반대 선택의 실제 결과와 개인별 최적 판단은 관측자료만으로 확정할 수 없다.

## Pitcher Zone Profile

`web/zones/`는 canonical pitch partition에서 타자·투수별 0.5 ft 존 데이터를 생성한다. 연도·구종·볼카운트·스트라이크카운트를 고르고 Swing%, Whiff%, Contact%, In-play%를 볼 수 있으며, 구종별 구사율·평균 구속·존 비율 비교표를 함께 제공한다. 일일 2026 갱신 때 이 프로필도 같은 canonical 입력에서 다시 생성된다.

## Pitch Arsenal

`web/pitch-arsenal/`은 2022~2026 시즌 투수별 구종 사용률, 평균 구속, Horizontal Break와 Induced Vertical Break를 Savant형 화면으로 제공한다. 무브먼트는 `movement_calibration.py`로 보정한다. 탄착 위치에 따른 측정 치우침을 빼고, 투수×구종과 구장×날짜 효과를 함께 추정해 구장·날짜별 편향을 뺀다(TrackMan 2019–2024 투구 단위 대조로 검증, `analysis/movement_calibration/`). 타원의 폭과 높이는 각각 중앙 75%(12.5~87.5 백분위) 범위이고, 원측정값과 보정값은 화면에서 전환할 수 있다. 한 투수가 10구 이하 또는 5% 미만으로 던진 구종은 중앙 구속 5km/h, 보정 HB·IVB 각 8cm, 탄착 중심 1.5ft 안에 드는 주력 구종이 있으면 그 구종에 묶어 보여 주고(표·툴팁에 원래 분류와 개수 표시), 없으면 점선 타원과 `소수 구종` 표시로 따로 둔다. 표시상의 묶음이며 curated `pitch_type`과 ZA/SBJ 입력은 바꾸지 않는다.

## Conditional Finder

`web/conditional-finder/`는 2022–2026 canonical games/events/pitches로 투수·타자의 장면을 검색한다. 구종·구속·투구 전 카운트·Take/Swing·투구 판정·타석 결과·상대 선수/팀·구장·이닝 조건을 조합할 수 있다. 같은 항목의 복수 선택은 OR, 서로 다른 항목은 AND다. 타석 결과를 고르면 기본적으로 마지막 공만 찾으며, 전체 투구 포함을 켜면 그 타석의 각 공에도 나머지 조건을 적용한다.

검색 결과에는 경기 ID, 이닝 내 타석 순서, 타석 내 투구 번호, 선수와 투구 전 상황을 표시한다. 타석을 펼치면 조건에 맞지 않는 공과 교체 투수의 공도 함께 보인다. 투구가 없는 타석은 순서에는 포함하지만 검색 결과에는 넣지 않는다. 날짜별 파일과 선수별 파일 목록으로 필요한 날짜만 읽고, 검색 링크와 장면 정보를 복사할 수 있다. 티빙은 홈 연결만 제공하며 경기 영상 URL이나 재생 시점을 추정하지 않는다.

현재 시즌은 일일 export에서, 완료 시즌은 같은 workflow의 `--only conditional_finder`에서 입력·코드가 바뀐 경우에만 다시 생성한다. 검색 데이터만 로컬에서 만들고 검증하려면:

```bash
PYTHONPATH=src python -m visualbaseball.cli --only conditional_finder --season 2026
PYTHONPATH=src python -m pytest tests/test_conditional_finder.py
node tests/test_conditional_finder.cjs
PYTHONPATH=src python scripts/check_conditional_finder.py
python scripts/generate_visual_thumbnails.py --only conditional-finder
```

브라우저 검사는 Playwright Chromium이 필요하다. 실제 경기의 홈런·전체 타석·0-0 called strike를 canonical과 비교하고, 공유 링크·복사·페이지·시즌 전환·실패/재시도·1440px/390px 폭과 기존 앱의 제목 간격을 확인한다. 결과와 화면은 `.cache/conditional_finder/`에 저장한다.

## Arm Angle Movement Zones

`web/movement-zones/`는 2019–2026 VB와 투구 단위로 매칭한 2019–2024 TrackMan에서 **기대 무브먼트(Dynamic DZ)**와 **헛스윙률 구역**을 별도로 적합한다. −60°~85°를 1°씩 조작하면 해당 손·구종의 기대 중심과 높은/중간/낮은 Whiff 구역이 이동한다. HB는 포수 시점이며 우투 암사이드는 음수, 좌투 암사이드는 양수다. 같은 투구는 한 번만 학습하고 매칭 투구에는 TrackMan 무브먼트(cm)를 쓴다. 나머지는 기존 구장·날짜·탄착 위치 보정 VB를 손·시즌별 강건 선형 회귀로 TrackMan 척도에 맞춘다. TM이 없는 2025–2026은 2022–2024 계수의 매칭 표본 가중 평균을 사용한다. 원자료와 다른 지표의 입력은 바꾸지 않는다.

**실측 팔각도가 아닌 릴리스 위치 대용치**다. 어깨 좌표·선수 신장이 없으므로 `atan2(release_z_55_cm − 130, |release_x_55_cm|)`로 기준 어깨 높이 130cm를 가정한다. 1°는 조작 간격이지 측정 정확도가 아니다. 수평/수직 릴리스 방향 HRA/VRA도 55ft 궤적 속도에서 계산한 대용치이며 실제 공을 놓는 지점의 방향과 다르다. 기존 GY/SW/Slurve를 무브먼트만으로 재분류하지 않고 원자료의 Slider·Sweeper를 쓴다. 누락된 타자 손은 기존 player bio/스위치 타자 매치업 규칙, 이어 안전하게 매칭된 TM의 타자 손으로 보강한다.

시간 환산식은 `M₀.₄ = M × (0.40 / t)²`다. 일정 가속도 가정에서 체공 시간 차이를 줄이기 위한 근사다. VB의 `vy_55`, `ay`로 홈플레이트 앞면까지 걸리는 시간을 풀고, 매칭된 TrackMan 투구에는 익스텐션(m)을 적용해 릴리스부터의 시간을 구한다. 미매칭 투구는 익스텐션을 모르므로 55ft부터의 시간을 쓴다. UI의 HB/IVB와 비교 입력은 모두 0.40초 환산 인치다. 이 값은 VB/TrackMan 무브먼트를 환산한 것으로 원본 DDZ의 릴리스 방향 대비 무브먼트 가속도를 직접 복원한 값이 아니다.

기대 분포는 스윙하지 않은 투구도 포함한 전체 유효 투구에서, 구종·투수 손별 조건부 다변량 정규 모형으로 추정한다. `r = [angle/45, HRA/5, VRA/5, t/0.4]`, `m = [HB₀.₄, IVB₀.₄]`에 대해 다음을 계산한다. `⁺`는 수치적으로 안정적인 의사역행렬이다.

```text
μ(m | r) = μₘ + Σₘᵣ Σᵣᵣ⁺ (r − μᵣ)
S(m | r) = Σₘₘ − Σₘᵣ Σᵣᵣ⁺ Σᵣₘ
DZ Delta = 입력 무브먼트 − μ(m | r)
50% / 80% 범위: (m−μ)ᵀ S⁻¹(m−μ) ≤ −2 ln(1−p)
```

슬라이더 각도는 정확한 선택값을 쓰고 HRA/VRA/체공 시간은 주변 ±5° 관측 투구의 가중 평균을 쓴다. 기대 타원의 50%·80%는 **모형의 명목 확률 범위**이며 낮은 성능 등급이 아니다. 실제 최신 시즌 포함률은 검증표에 따로 기록한다. 150투구·5투수 미만이면 기대 분포를 표시하지 않는다. FF/SI/FC 외 구종은 탐색적 확장이다.

헛스윙률은 유효 스윙에서 ΔHB/ΔIVB의 이차항·각도 상호작용을 넣은 로지스틱 회귀로 추정한다. 구속·탄착 위치·카운트·타자 상대 손·투수 손·시즌·출처·추정 각도·HRA/VRA·체공 시간을 통제한다. 관측 무브먼트 질량을 예측 Whiff로 정렬해 상위 25%/중간 50%/하위 25%로 나눈다. 관측 밀도는 각도 5°·무브먼트 1인치로 평활하고 최고 밀도의 5% 미만인 셀은 제외한다. **성능 구역은 실제 1인치 셀을 그리며, 이전의 Gaussian 요약 타원으로 다른 등급을 덮던 오류를 제거했다.** 150스윙·5투수 미만이면 표시하지 않는다. 위치 중앙·1-1 카운트·상대 손 비율 50%·손별 구속 중앙값·최신 시즌·VB 출처로 통제한 비교이며, 종합 구종 가치나 각도 변경의 인과 효과를 측정하지 않는다.

참고한 공개 산식과 적용 범위:

- [Max Bay Dynamic Dead Zone](https://dynamic-dead-zone.streamlit.app/)의 Mathematical explainer: 조건부 정규 평균·공분산을 KBO에서 다시 적합했다. 원본은 가속도, 실측 어깨 팔각도, 신장 대비 익스텐션 및 FF/SI/FC 혼합 분포를 사용한다. 이 페이지는 선택 구종의 분포를 사용하고, 확보된 KBO 대용치로 조건 변수를 구성한다. MLB 계수·혼합 확률을 가져오지 않았다.
- [Alex Chamberlain Pitch Leaderboard v8](https://public.tableau.com/app/profile/chamb117/viz/PitchLeaderboardv8/Dashboard)의 공개 workbook `AxOE`/`AzOE`: FF/SI/FC에서 실제 `ax`/`az`와 시즌·구종·반올림한 HRA/VRA 그룹의 평균 차이를 계산한다(AxOE는 투수 손도 그룹화). 여기서는 릴리스 방향과 실제−기대 Delta 개념을 반영하고 연속 조건부 기대값을 추정한다. workbook 가속도와 동일한 수치는 아니다.
- [Baseball Savant pitch movement](https://baseballsavant.mlb.com/pitch-movement): 구종·구속·릴리스 조건을 맞춘 비교와 중력 제외 IVB 정의를 참고했다. Savant 전체 무브먼트 비교는 중력을 포함하며, 자체 비교 조건은 ±2mph·익스텐션/릴리스 높이 ±0.5ft다. 이를 단일 공개 Dead Zone 공식으로 간주하지 않는다.
- [야구공작소의 팔각도·무브먼트 설명](https://yagongso.com/이것-없이는-무브먼트도-의미-없다/): 각도 대비 기대 모양, 0.4초 시간 환산과 변화구 확장의 맥락을 참고했다.

최신 시즌 전체를 제외하고 이전 시즌에서 기대 모형과 회귀를 적합한다. 기대 모형은 동일 손·구종의 무조건 평균과 비교하고(HB/IVB RMSE·50%/80% 실제 포함률), 헛스윙 회귀는 동일 통제변수만 쓴 모델과 비교한다(AUC·Log loss·Brier). 화면은 검증 후 전체 시즌으로 재적합한다. 계수·검증값·투구 및 제외 건수·소스 hash·참고 산식 출처를 schema v2의 `web/data/movement_zones/profiles.json`에 저장하고 일일 workflow의 아래 명령으로 갱신한다. 입력/코드 hash가 같으면 재적합을 건너뛴다.

```powershell
$env:PYTHONPATH = "src"
python -m visualbaseball.cli --only movement_zones
python -m pytest tests/test_movement_zones.py
python scripts/check_movement_zones.py
python scripts/check_movement_zones.py --url https://seoyeonwoo1223.github.io/KBO-Savant-Visual-Project/movement-zones/
```

브라우저 검증은 두 모드의 4,672개 손·구종·각도 조합, 기대 중심의 저장 계수 재계산, R/45의 실제 SVG 채움과 셀/조건부 확률식 일치, 1° 조작·자동재생 정지·DZ Delta 입력·모바일 폭·데이터 로드 실패를 확인한다. 공개 URL 검증은 제공 JSON과 현재 생성 artifact의 전체 일치도 요구한다. 증거와 화면은 `.cache/movement_zones/validation*.json`, `preview-*.png`에 저장한다.
