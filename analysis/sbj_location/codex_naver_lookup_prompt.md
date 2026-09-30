# 코덱스 작업 지시: 네이버 중계 API로 누락·오류 투구의 위치 찾기

## 배경

저장소 `seoyeonwoo1223/KBO-Savant-Visual-Project`에서 브랜치 `claude/loving-goldberg-r7bmy2`(초안 PR #30)를 기준으로 작업한다. 이 브랜치는 PR #29(`codex/sbj-data-harness`) 위에 있다. 작업 전에 다음 파일을 먼저 읽는다.

- `CLAUDE.md`, `docs/sbj-data-quality.md`
- `analysis/sbj_location/correction_design.md`: 오류 유형 A–F, 필드별 근거 우선순위, 이 작업의 목적(4절)
- `analysis/sbj_location/README.md`의 "캡처 기반 사례 대조 기록"
- `analysis/sbj_location/results/missing_pitch_targets.csv`: 찾아야 할 공 목록
- `analysis/sbj_location/results/game_gap_scan.csv`, `results/case*_correspondence.csv`, `results/kim_lim_20250809_correspondence.csv`
- `src/visualbaseball/naver.py`: 기존 네이버 중계 클라이언트(`NaverRelayClient`)와 경기 ID 규칙

Visual Baseball(VB) 원본에는 공 누락, 타석 분리, 궤적 복제, 구속 표시 밀림, 호출 오류, 경기 구간 누락이 있다. TrackMan(2019–2024, `data/tracking/raw/season=<Y>/trackman_history.csv`)은 순서·카운트·구속·구종을 주지만 **탄착 위치 컬럼이 없다**. 그래서 "원래 있어야 하는 공"의 위치는 네이버 중계 API에 투구 단위 추적 기록이 있을 때만 얻을 수 있다. 사용자가 확인한 바로는 네이버 문자 목록과 VB가 같은 오류를 보이는 경우가 많고, 네이버 "투구 위치 보기" 그림은 중복은 거르지만 누락 공은 그림에도 없었다.

## 대상 경기 (10개)

`20250809OBWO0`, `20240724WOOB0`, `20240404LTHH0`, `20240504OBLG0`, `20260509KTWO0`, `20250614HTNC0`, `20210606HHNC0`, `20210512SSKT0`, `20210828NCHH0`, `20200630LTNC0`

네이버 경기 ID는 `naver.py`의 규칙(`<game_id><season>`, 예: `20250809OBWO02025`)을 따른다. 연장 이닝까지 모두 받는다.

## 할 일

1. **수집(로컬)**: 경기·이닝마다 `/schedule/games/{naver_game_id}/relay?inning={n}` 응답 원문을 저장한다.
   - 위치: `data/raw/naver/relay_raw/<season>/<game_id>/inning_<n>.json`. `data/raw/naver/`는 gitignore 대상이다. 커밋 전에 `git status`로 원문이 추적되지 않는지 확인한다.
   - 요청 간격은 1초 이상으로 한다. 실패하면 재시도는 3회까지만 하고, 실패는 기록한다.
2. **필드 조사**: 응답에서 투구 단위 항목(`textOptions`와 그 밖의 투구 배열이 있다면 그것까지)의 키 이름·자료형·예시값을 전부 목록으로 만든다. 좌표·궤적·존 높이로 보이는 필드는 단위와 기준면 후보도 적는다. **필드 이름을 추측해서 코드를 쓰지 말고, 실제 응답에서 확인한 키만 쓴다.**
3. **투구 단위 정규화**: 한 행이 네이버 투구 기록 하나가 되게 만든다. 열은 다음과 같다.
   - 경기, 이닝, 초/말, 타석 순서, 타자, 투수
   - 네이버 투구 번호(`pitchNum`), 투구 ID(`ptsPitchId` 등 실제 키)
   - 판정 문구, 구속, 구종, 투구 뒤 볼카운트
   - 위치·궤적 필드(있다면)
   - 중계 문장 전체는 저장하지 않는다. 판정·결과 단어만 남긴다.
4. **세 가지 질문에 답한다.**
   - Q1. 투구별 위치·궤적 필드가 있는가? 있다면 무엇이고, 단위·기준면은 무엇인가?
   - Q2. 그 값이 같은 공의 VB 원본(`data/raw/<season>/<game_id>.json` 또는 `seasons/2025/...`의 `px`, `pz`, `x0…az`, `szTop`, `szBot`)과 같은가? 같은 공으로 확실히 대응되는 공(대응표에서 "확정")만 비교한다. 차이의 분포를 보고한다.
   - Q3. 문자 목록에서 두 번 나오는 공(대응표의 "복제", "선행 기록")이 같은 투구 ID를 공유하는가? 추적 기록 배열이 공당 하나인가?
5. **누락 공 찾기**: `missing_pitch_targets.csv`의 각 행에 대해 네이버에서 해당 공을 찾는다.
   - `captured` 행(사용자 확인, 7구): 타석 라벨·투구 순번·카운트·판정·구속으로 찾는다.
   - `half_short` 행(TrackMan 기준, 401구): 이닝·초/말·투수·타자·타석 안 순번으로 찾는다. 2019–2023의 표시 구속은 구장별 측정값이라 연결 조건으로 쓰지 않는다. 구속은 궤적 계수로 계산한 구속을 TrackMan `rel_speed`와 비교하고, 경기별 중앙 오프셋을 뺀 잔차가 ±3km/h 이내인지 본다(`correction_design.md` 9절). **카운트는 대조값으로만 쓰고 연결 조건으로 쓰지 않는다.** 이 행들에는 VB에 이미 있는 공도 섞여 있다. VB 원본에도 있는 공인지를 별도 열로 표시한다.
   - 결과 분류:
     - `found_with_location`: 네이버에 있고 위치 필드도 있음
     - `found_no_location`: 네이버에 있지만 위치 필드가 없음
     - `not_in_naver`: 네이버에 없음
     - `ambiguous`: 후보가 둘 이상
   - 후보가 둘 이상이면 고르지 말고 `ambiguous`로 둔다.
6. **산출물**
   - `analysis/sbj_location/results/naver_pitch_lookup.csv`: 대상 공마다 한 행. 분류, 네이버 투구 ID, 위치 필드, 근거를 넣는다.
   - `analysis/sbj_location/results/naver_relay_fields.md`: Q1–Q3 답, 필드 목록, 대상 경기별 수집 성공·실패, 분류별 건수
   - 수집·정규화·대조 스크립트: `analysis/sbj_location/naver_relay_fetch.py` 등. 기존 `NaverRelayClient`를 재사용해도 된다.

## 지켜야 할 규칙

- `src/`, `data/curated/`, `data/metrics/`, `web/`, `exports/`, VB 원본 JSON은 **수정하지 않는다**. 보정표(`data/corrections/`)도 만들지 않는다. 이번 작업은 조사와 대조까지다.
- 네이버 원본 응답은 커밋하지 않는다. 정규화 CSV에도 중계 문장 전체를 넣지 않는다.
- **없는 좌표를 만들지 않는다.** 네이버에 위치가 없으면 null이다. TrackMan 구속·구종으로 위치를 추정하거나 VB의 다른 행 좌표를 빌려 채우지 않는다. 네이버 "투구 위치 보기" 그림 이미지에서 좌표를 읽지 않는다.
- 네이버와 VB가 같은 공급원일 수 있다. Q2에서 값이 같게 나오더라도 이를 "위치가 독립적으로 검증됐다"고 쓰지 않는다.
- 추정은 추정이라고 적는다. 사용자 캡처·영상으로 확인된 사실(대응표)과 네이버 API 값이 다르면 둘 다 기록하고, 어느 쪽이 맞는지 정하지 않는다.
- 커밋 메시지와 PR 본문에 모델 이름을 적지 않는다. 작업은 새 브랜치에서 하고, `claude/loving-goldberg-r7bmy2`를 베이스로 초안 PR을 연다. 어떤 PR도 병합하지 않는다.

## 보고 형식

Summary / Validation / Issues 순서로, 한국어로 짧게 쓴다.

- **Summary**: Q1–Q3 답, `missing_pitch_targets.csv` 분류별 건수(captured와 half_short를 나눠서)
- **Validation**: 실행한 명령, 종료 코드, 수집 성공 이닝 수, 원문이 추적되지 않음을 확인한 결과
- **Issues**: 수집 실패, 필드 해석이 불확실한 부분, `ambiguous` 목록
