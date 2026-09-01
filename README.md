# KBO Savant Project

2026 KBO 공개 PBP에서 경기·이벤트·피치 데이터를 증분 수집해, 분석용 Parquet와 다운로드용 Excel, 브라우저용 CSV를 함께 만드는 프로젝트입니다.

## 어디에 무엇이 있나

| 경로 | 용도 |
|---|---|
| `src/visualbaseball/` | 현재 사용 중인 Python 수집기와 검증·내보내기 코드 |
| `data/raw/` | Visual Baseball 게임별 원본 PBP JSON 및 `raw/naver/`의 정규화된 Naver 릴레이 조인 캐시 |
| `data/processed/` | 신뢰 가능한 분석 원본: `games`, `events`, `pitches` Parquet |
| `data/leaderboards/source/` | 2026 리더보드 계산 원본, 리그 상수, PF 산출 입력 |
| `exports/visualbaseball_savant_2026_latest.xlsx` | 바로 내려받아 열 수 있는 최신 Excel 파일 |
| `web/` | GitHub Pages에서 리더보드와 피치 트래킹 시각화를 제공하는 정적 뷰어 |
| `web/blocking/` | 실험적 KBO Catcher Blocks Above Average 리더보드·위치 맵 |
| `exports/plate_discipline_research_2026.csv` | 타자별 선구안 베이스 스탯·회귀 잔차·프로필 클러스터 연구표 |

## GitHub에서 열람·다운로드

GitHub는 `.xlsx`를 셀 단위로 미리보기하지 않는 바이너리 파일로 취급합니다. 따라서 Excel은 저장소의 [`exports/`](exports/)에서 **Download raw file**로 내려받는 방식이며, 누락된 파일이 아닙니다. `web/`는 같은 데이터를 표와 무브먼트 산점도로 열람할 GitHub Pages 뷰어입니다. Pages를 한 번 활성화하면 아래 주소에서 볼 수 있습니다.

`https://seoyeonwoo1223.github.io/KBO-Savant-Visual-Project/`

개인 저장소라면 저장소 권한이 있는 계정으로 로그인해야 Excel과 Pages 데이터를 볼 수 있습니다. 더 큰 분석이나 스프레드시트 작업에는 Excel 파일을 사용하면 됩니다.

## 데이터 갱신 방식

수집기는 시즌 일정에서 **신규·미완료·실패 게임**과 최근 2일의 확정 경기를 다시 확인합니다. 정상 검증된 게임은 기존 Parquet에서 그 게임 ID의 행만 교체합니다. 그 뒤 Excel과 웹 CSV는 전체 검증 Parquet로부터 다시 만들어지므로, Excel은 누적 추가 파일이 아니라 최신 데이터의 재생성본입니다.

```powershell
python -m pip install -r requirements.txt
$env:PYTHONPATH = "src"
python -m visualbaseball.cli
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

2026 라이브 리더보드는 `PYTHONPATH=src python -m visualbaseball.leaderboard_vb`로 Visual Baseball PBP를 직접 재집계한다. 타자는 200 PA, 투수는 50 IP 이상만 싣는다. 원자료에서 정확히 복원할 수 없는 도루·도실·자책점·승패·세이브·홀드와 타구 유형은 제외한다. `WAR*`는 타자의 수비·주루를 제외한 공격·포지션 보정 추정치와 투수의 FIP 기반 추정치다. 집계 기준일을 검증할 수 없는 2026 OAA 수비 자료는 리더보드에서 제외한다.

### 포수·폭투·포일 보강

`Pitches`에는 VB의 `y0`와 기존 운동학 필드(`x0`, `z0`, `vx0`…`az`)를 그대로 보존한다. Naver Sports 릴레이의 이닝별 투구 ID를 VB의 이닝·공수·타자·투수·투구 순번에 결합해 `catcher_id`, `catcher_name`, `is_wild_pitch`, `is_passed_ball`, `naver_pitch_id`를 추가한다. `naver_match_status=unavailable` 또는 `unmatched`는 **0이 아니라 미확인**이다.

특정 원본 경기를 검증·보강하려면 다음처럼 실행한다. 전체 시즌 재생성은 이닝별 릴레이 호출이 필요한 작업이므로 시즌별로 나누어 실행한다.

```powershell
python -m visualbaseball.cli --rebuild-from-raw --refresh-naver --game-id 20260328KTLG0
```

## Catcher Blocks Above Average

`web/blocking/`은 주자가 있거나 2스트라이크인 비접촉 투구를 블로킹 기회로 정의한다. 5-fold 경기 단위 교차검증 로지스틱 모델이 위치·구속·무브먼트·구종·릴리스 방향·타자 손잡이·주자/카운트 상태로 PB+WP 확률을 추정한다. 투구별 `예상 PB+WP - 실제 PB+WP`를 포수별로 합산한 값이 KBO BAA이며, 블로킹 런은 MLB와 같은 0.25 runs/block로 환산한다.

이 결과는 Baseball Savant의 개념과 표시 방식을 KBO 공개 데이터에 적용한 **실험 지표**다. 공개 원본에 포수의 사전 위치가 없으므로 MLB Statcast 지표와 동일한 모델 또는 상호 비교 가능한 값이 아니다. `data/processed/blocking_pitches.parquet`에 투구별 예상 확률과 기여도를, `web/data/blocking/2026/leaderboard.json`에 리더보드와 시각화 집계를 저장한다.

## 검증 원칙

게임 최종 점수는 공개 PBP 스냅샷뿐 아니라 공식 라인스코어와도 대조합니다. 두 소스가 충돌하면 `SOURCE_SCORE_CONFLICT` 이벤트를 남기고 공식 라인스코어를 최종 기준으로 사용합니다. 공개 PBP가 제공하지 않는 주자 이벤트는 추측하지 않으며 `parse_status=unknown`으로 보존합니다.

## 자동 갱신

`.github/workflows/daily_update.yml`은 매일 12:07 Asia/Seoul에 테스트 후 수집기를 실행합니다. 최신 Excel의 `Pitches` 시트가 Swing/Take 프로필의 단일 입력이며, Excel이 갱신되면 박준순·홍창기 프로필 JSON과 `data/processed/decision_pitches.parquet`가 함께 재생성됩니다. 중간 분석 테이블인 Decision Pitches는 Excel에 넣지 않습니다. 데이터 내용이 같으면 Excel과 프로필 파일도 바뀌지 않아 커밋하지 않습니다.

## Swing/Take 프로필 기준

프로필은 2026 KBO 정규시즌의 검증된 투구만 사용한다. 스윙은 헛스윙·파울·인플레이, 테이크는 콜드볼·콜드스트라이크와 타석 종료 사구로 분류한다. 최소 표시 기준은 **300 pitches seen**이며, 이 수치는 FanGraphs의 Swing/Take 분석에서 사용된 하한을 따른다. 300구 미만은 수치를 숨기지 않고 표본 미달로 표시한다.

검색 화면에서는 2022~2026 연도를 선택할 수 있다. 각 연도 Run Value와 리그 평균은 해당 시즌 Excel만으로 별도 계산하므로 서로 섞이지 않는다.

## Plate Discipline 연구 테이블

`src/visualbaseball/plate_discipline.py`는 Swing/Take 산출 직후 타자별 연구용 데이터를 만든다. `data/processed/plate_discipline_pitches.parquet`에는 정규화 좌표와 Heart·Shadow-in·Shadow-out·Chase·Waste 구역, 스윙·컨택·단순 정답 여부를 저장한다. `data/processed/plate_discipline_batters.parquet`와 `exports/plate_discipline_research_2026.csv`에는 Z-Swing%, O-Swing%, 구역별 Swing%, Contact%, 단순 Strikezone Judgment%, Simple SEAGER 기준선, 기존 observed Decision Run, 회귀 잔차와 숫자형 클러스터를 저장한다.

회귀식과 클러스터 중심값·표본 기준·정의는 `data/processed/plate_discipline_research.json`에 기록한다. 클러스터 번호는 우열 등급이 아니며, 타구속도·발사각이 없는 현재 원자료로는 PLV처럼 타자별로 좋은 타구가 될 확률까지 분리하지 않는다. 기존 Decision Run은 실제 선택의 결과가 포함된 진단값이므로 counterfactual Decision Value로 부르지 않는다.

## Pitcher Zone Profile

`web/zones/`는 같은 Excel의 `Pitches` 시트에서 타자·투수별 0.5 ft 존 데이터를 생성한다. 연도·구종·볼카운트·스트라이크카운트를 고르고 Swing%, Whiff%, Contact%, In-play%를 볼 수 있으며, 구종별 구사율·평균 구속·존 비율 비교표를 함께 제공한다. 일일 2026 갱신 때 이 프로필도 같은 Excel에서 다시 생성된다.

## Pitch Arsenal

`web/pitch-arsenal/`은 2022~2026 시즌 투수별 구종 사용률, 평균 구속, Horizontal Break와 Induced Vertical Break를 Savant형 화면으로 제공한다. 무브먼트는 `data/park_adjustments/`의 시즌·구장·구종별 오프셋을 사용해 `보정값 = 측정값 - 오프셋`으로 계산하며, 타원의 폭과 높이는 각각 중앙 75%(12.5~87.5 백분위) 범위다. 보정표에 독립 항목이 없는 투심은 싱커, 스위퍼는 슬라이더 오프셋에 연결한다. 원측정값과 보정값은 화면에서 전환할 수 있다.

## Arm Angle Movement Zones

`web/movement-zones/`는 제공된 팔각도별 범위표를 바탕으로 15°·30°·45°·60°의 구종별 Elite·Average·Dead Zone을 HB×IVB 평면에 표시한다. 슬라이더 또는 자동 재생으로 팔각도에 따른 범위 변화를 비교할 수 있다. HB는 투수 시점이며 양수는 암사이드, 음수는 글러브사이드다.
