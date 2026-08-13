# KBO Swing/Take Project

2026 KBO 공개 PBP에서 경기·이벤트·피치 데이터를 증분 수집해, 분석용 Parquet와 다운로드용 Excel, 브라우저용 CSV를 함께 만드는 프로젝트입니다.

## 어디에 무엇이 있나

| 경로 | 용도 |
|---|---|
| `src/visualbaseball/` | 현재 사용 중인 Python 수집기와 검증·내보내기 코드 |
| `data/raw/` | 게임별 원본 PBP JSON |
| `data/processed/` | 신뢰 가능한 분석 원본: `games`, `events`, `pitches` Parquet |
| `exports/visualbaseball_savant_2026_latest.xlsx` | 바로 내려받아 열 수 있는 최신 Excel 파일 |
| `web/` | GitHub Pages에서 표와 무브먼트 플롯을 제공할 정적 뷰어 |
| `legacy/vba/` | 보존용 기존 VBA, `.xlsm`, 원본 `.xlsx`, Windows 실행 스크립트 |

## GitHub에서 열람·다운로드

GitHub는 `.xlsx`를 셀 단위로 미리보기하지 않는 바이너리 파일로 취급합니다. 따라서 Excel은 저장소의 [`exports/`](exports/)에서 **Download raw file**로 내려받는 방식이며, 누락된 파일이 아닙니다. `web/`는 같은 데이터를 표와 무브먼트 산점도로 열람할 GitHub Pages 뷰어입니다. Pages를 한 번 활성화하면 아래 주소에서 볼 수 있습니다.

`https://seoyeonwoo1223.github.io/KBO-Swing-Take-Project/`

개인 저장소라면 저장소 권한이 있는 계정으로 로그인해야 Excel과 Pages 데이터를 볼 수 있습니다. 더 큰 분석이나 스프레드시트 작업에는 `web/data/movement.csv`를 내려받거나 Excel을 사용하면 됩니다.

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

## 검증 원칙

게임 최종 점수는 공개 PBP 스냅샷뿐 아니라 공식 라인스코어와도 대조합니다. 두 소스가 충돌하면 `SOURCE_SCORE_CONFLICT` 이벤트를 남기고 공식 라인스코어를 최종 기준으로 사용합니다. 공개 PBP가 제공하지 않는 주자 이벤트는 추측하지 않으며 `parse_status=unknown`으로 보존합니다.

## 자동 갱신

`.github/workflows/daily_update.yml`은 매일 12:07 Asia/Seoul에 테스트 후 수집기를 실행합니다. 최신 Excel의 `Pitches` 시트가 Swing/Take 프로필의 단일 입력이며, Excel이 갱신되면 박준순·홍창기 프로필 JSON과 `data/processed/decision_pitches.parquet`가 함께 재생성됩니다. 중간 분석 테이블인 Decision Pitches는 Excel에 넣지 않습니다. 데이터 내용이 같으면 Excel과 프로필 파일도 바뀌지 않아 커밋하지 않습니다.

## Swing/Take 프로필 기준

프로필은 2026 KBO 정규시즌의 검증된 투구만 사용한다. 스윙은 헛스윙·파울·인플레이, 테이크는 콜드볼·콜드스트라이크와 타석 종료 사구로 분류한다. 최소 표시 기준은 **300 pitches seen**이며, 이 수치는 FanGraphs의 Swing/Take 분석에서 사용된 하한을 따른다. 300구 미만은 수치를 숨기지 않고 표본 미달로 표시한다.

## Pitcher Zone Profile

`web/zones/`는 같은 Excel의 `Pitches` 시트에서 타자·투수별 0.5 ft 존 데이터를 생성한다. 연도·구종·볼카운트·스트라이크카운트를 고르고 Swing%, Whiff%, Contact%, In-play%를 볼 수 있으며, 구종별 구사율·평균 구속·존 비율 비교표를 함께 제공한다. 일일 2026 갱신 때 이 프로필도 같은 Excel에서 다시 생성된다.

## 데스크톱 VBA

기존 Excel 매크로 수집기는 [`legacy/vba/README.md`](legacy/vba/README.md)에 분리해 보존했습니다. 이 경로는 GitHub Actions 수집기와 독립적입니다.
