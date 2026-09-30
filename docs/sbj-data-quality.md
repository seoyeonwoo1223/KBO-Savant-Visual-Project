# SBJ 데이터 신뢰 감사: 현재 병목과 재현 절차

이 문서는 PR #28의 여러 실험 메모 대신 **출시 경계와 원본 검증 계약**을 한곳에 둔다. 이 단계는 투구 사건을 고치거나 SBJ를 재학습하지 않는다. 감사 결과가 점수에 영향을 미치려면 별도의 규칙·검증·승인이 필요하다.

## 출시 경계

- 미승인 `za7.3`의 궤적 x/z를 보고 탄착값으로 대체하는 운영 변경은 별도 PR에서 되돌린다. 조사 코드와 2025년 김택연 타석 재감사 기록은 삭제하지 않는다.
- Pitch Arsenal 표시 변경, 선수 ID 대응표, SBJ 점수 변경은 서로 다른 결정이다. 감사 플래그만으로 행 삭제·볼/스트라이크 재분류·점수 가중치 변경을 하지 않는다.
- 2024–2026 공개 SBJ는 승인된 한 버전으로만 재빌드·배포한다. 이 감사 도구는 `src/`의 생산 모델이나 `web/`, `data/curated/`, `data/metrics/`를 쓰지 않는다.

## 실제 병목

VB 원본에는 타석 분리, 종료 뒤 추가 행, 중복·혼합 궤적, 카운트와 타석 결과 불일치가 있다. 김택연–임지열(2025-08-09)은 VB 9행과 중계 7구로 이를 보여 준다. `V` 호출 코드와 존 중심의 `B`도 해석이 불확실하다. TrackMan은 독립적인 비교 자료이지만 2019–2024에만 있고, 경기·투구 공통 ID가 없으며, 일부 1군 경기 자체가 없다. 따라서 **모든 VB 공에 참인 TrackMan 대응을 만드는 것은 불가능**하다. 빠진 자료를 억지로 순서·카운트로 채우면 오염된 타석에서 가짜 확신이 생긴다.

TrackMan 2군 자료는 SBJ 1군 대상에서 제외한다. 투수 **및 타자** 팀 코드가 모두 KBO 1군 구단인 행만 사용한다. 경기 연결은 같은 날짜의 투수 집합을 우선하고, 팀·날짜 조합이 양쪽에서 정확히 한 경기일 때만 보조 연결한다. 더블헤더는 이 보조 규칙으로 연결하지 않는다. 투구 연결은 경기·반이닝·투수·타자 순서, 투구 전 아웃, 시즌 구속 오프셋 ±2km/h를 확인한다. **볼·스트라이크 카운트는 비교 대상이므로 연결 조건으로 사용하지 않는다.** 같은 길이 구간은 개별 공의 실패만 탈락시킨다. 길이가 다른 구간은 유일한 대응만 받는다.

## 한 번에 재현하기

```powershell
$env:PYTHONPATH = "src"
python scripts/build_trackman_id_crosswalk.py --root .
python scripts/audit_sbj_data.py --out ../audit/sbj
```

첫 명령은 선수 단위 대응표를 **2019–2024 전체 시즌**으로 다시 만든다. 둘째 명령은 2019–2026 VB 모든 투구에 대해 `sbj_pitch_quality_<시즌>.csv.gz` 한 행씩과 요약 JSON을 만든다. 2019–2024는 `matched` 또는 사유가 있는 `unmatched`이고, 2025–2026은 `trackman_unavailable`이다. `matched`도 사건의 진실이나 ABS 추적 정확성을 보증하지 않는다. `count_mismatch`는 그 쌍의 카운트 차이이지 VB 오류 확정이 아니다. 미매칭을 분모에서 숨기지 말고 `sbj_data_audit_summary.json`의 `vb_pitches`, `match_status`, `unmatched_reasons`를 함께 보고한다.
`matched` 안에서도 `run_kind=equal_length_partial`은 같은 길이의 구간에서 주변 공의 구속·아웃 검증이 실패한 **낮은 신뢰도의 후보 연결**이다. 엄격한 독립 검증 분모로 쓰려면 이 그룹을 따로 보고하거나 빼야 한다. 투구별 공통 ID가 없으므로 구속·아웃 조건을 통과해도 진짜 동일 투구임이 증명되지는 않는다.
이미 같은 입력으로 두 감사가 끝난 상태에서 결과 병합만 다시 할 때는 `--from-existing`을 추가할 수 있다. 새 원본 감사가 아니므로 입력이나 규칙이 바뀌었으면 이 옵션을 쓰지 않는다.
요약의 시즌별 `call_corrections`는 curated가 정정표(`data/corrections/vb_bunt_foul_corrections.json`)와 맞는지 보여 준다. 항목은 `applied`, `pending`, `stale`, `untracked_W`, `count_errors`다. 한 시즌이라도 `clean`이 아니면 감사가 실패한다. 같은 검사를 따로 돌리려면 `python scripts/check_call_corrections.py`(깨끗하지 않으면 종료 코드 1)를 쓰고, pytest에서는 `test_committed_curated_is_in_step_with_the_correction_table`이 같은 게이트다.
요약에는 코드·curated 투구 shard·선수 대응표 해시를 기록한다. TrackMan 파일 해시는 Windows 체크아웃의 CRLF를 LF로 정규화해 저장된 대응표 해시와 대조하며, 다르면 실패한다.

원본 측 플래그는 `K_CONT`, `BB_CONT`, `X_NONLAST`, `END_MISMATCH`, 타석 분리 등 **구조적 흐름 문제**, 또는 `DUP_*`, `B_NEAR_CENTER`, 판정면과 보고 위치의 불일치 같은 **진단 신호**로 나뉜다. 타석 수준 플래그는 그 타석의 모든 투구에 붙으므로, 플래그 투구 수를 오류 투구 수로 해석하지 않는다. `review_level=structural`도 원인을 확정하지 않으며 투구 삭제 지시가 아니다. `PLATE_X_DISAGREE`는 2024년 이후 VB `px`의 **중간면**과 궤적 중간면을 비교한다. 2023년까지의 앞면 오차를 2024+에 그대로 적용하지 않는다. 1cm 임계값은 검토 후보를 고르는 기준일 뿐이다.

감사 완료의 의미는 `품질 행 수 = VB 투구 수`, `matched + unmatched = VB 투구 수`(TrackMan 시즌), 미매칭 사유 누락 0, 투구 쌍 일대일, 2군 TrackMan 행 0을 실행으로 확인하는 것이다. **카운트 불일치 0이나 전체 공 100% 매칭을 완료 조건으로 삼지 않는다.** 후속 단계에서 원본 중계·영상 표본을 독립 검증하고, 고정된 품질 규칙의 학습/채점 영향을 별도 PR로 실험한다.

2026-09-27 로컬 전수 실행 결과(동일 시즌의 원본이 바뀌면 재실행할 것):

| 시즌 | VB 투구 | 대응 후보 전체 | 그중 주변 공 실패 없는 후보 | 미연결 |
|---|---:|---:|---:|---:|
| 2019 | 211,628 | 160,989 | 130,727 | 50,639 |
| 2020 | 220,863 | 181,307 | 154,202 | 39,556 |
| 2021 | 220,742 | 176,604 | 153,003 | 44,138 |
| 2022 | 217,025 | 166,294 | 142,386 | 50,731 |
| 2023 | 219,839 | 179,793 | 166,267 | 40,046 |
| 2024 | 223,216 | 189,613 | 177,276 | 33,603 |

2024년 1군 TrackMan은 201,117구·647경기이고, 그중 634경기를 VB에 연결했다. 2024년 대응 후보에서 카운트 불일치는 1,634/189,613구(0.86%)이며 **어느 공급자의 오류인지 이 수치만으로 판정할 수 없다.** `equal_length_partial` 12,337구를 포함한 189,613구는 검증 완료된 정답 쌍이 아니다. 2025·2026의 VB 217,852·203,262구에는 TrackMan 비교 자료가 없다.

TrackMan 이력에는 **KIA 홈(광주) 경기가 2019–2024 전 시즌에 한 경기도 없다.** 2024 경기 미연결 26,388구 중 22,457구가 KIA 홈 경기이므로 미연결은 무작위가 아니며, 대응 후보에서 얻은 비율을 KIA 홈 경기나 2025–2026에 그대로 옮길 수 없다. SBJ 위치 입력 비교와 사건 신호의 SBJ 노출 규모는 `analysis/sbj_location/README.md`에 있다.

## 번트 파울·번트 헛스윙 정정

Visual Baseball 원본은 번트 파울을 `B`(볼)로 기록한다. 네이버 중계와 대조한 표본에서 확인됐다. GPT 표본 42구, `analysis/sbj_location`의 네이버 `W/번트파울` 13구다. 이 공들은 존 가운데의 "볼 테이크"로 학습·채점되어, 2024 `p_zone` 손실의 약 54%를 차지했다.

- **대상 선정**(`scripts/build_trackman_bunt_corrections.py` → `data/corrections/vb_bunt_foul_corrections.json`): 세 조건을 모두 만족하는 공을 고른다.
  1. VB `B`이고 타석의 마지막 공이 아니다.
  2. TrackMan과 1:1로 연결된다. 연결은 궤적 구속과 경기 오프셋을 쓰는 H3 방식이다(`analysis/sbj_location/README.md`).
  3. 같은 타석의 다음 VB 공이 다음 TrackMan 공과 연결되고, TrackMan 카운트가 볼은 그대로, 스트라이크는 +1이다.

  2019–2024 대상은 613 / 582 / 617 / 657 / 795 / 596구, 합계 3,860구다.
- **정정 내용**: 대상 공은 코드 `W`(Bunt Foul)가 된다. 스윙·테이크·컨택트가 아니므로 Swing/Take, SBJ, `p_zone` 학습, 블로킹 기회에서 빠진다. 그 타석의 카운트와 `re288` 상태 코드는 스트라이크 +1로 다시 계산된다. 다음 카운트의 스트라이크 증가만으로 번트 파울을 확정할 수는 없다. 아래 네이버 카운트 감사에서 실제 볼인 TrackMan 오정정 7구를 확인해 `W→B`로 되돌렸다.
- **적용 경로**
  - 파서(`collector.call_corrections` → `parse_game(call_corrections=...)`): 원본의 코드·타자·투수·표시 구속이 표와 정확히 같을 때만 적용한다. 원본을 다시 파싱해도 결과가 같다.
  - 커밋된 curated: `scripts/apply_call_corrections.py`로 해당 타석만 고친다. 원본에서 다시 빌드하면 2022–2024에서 이번 정정과 무관한 컬럼까지 바뀌기 때문이다. 기존 카운트가 파서 규칙으로 재현되지 않는 타석은 건너뛴다(`--check`로 먼저 확인).
- **한계**
  - TrackMan이 없는 2025–2026, KIA 홈 경기, TrackMan에 없는 비KIA 경기, 연결되지 않은 공은 이 경로로 정정되지 않는다. 앞의 세 가지는 아래 네이버 경로로 정정했다. TrackMan 경기 안에서 연결되지 않은 공은 남아 있다(`analysis/sbj_location/naver_bunt_extension_design.md` 4절, 6절).
  - 타석 마지막 공인 번트 파울(2스트라이크 번트 파울 삼진)은 다음 공이 없어 고르지 못한다.
  - 번트 인플레이·번트 헛스윙은 대상이 아니다. 이런 공은 네이버 `W` 코드나 중계 문구로 따로 찾아야 한다.
- **2025–2026 (네이버 기준)**: 네이버 중계 전수 조사(PR #32, `bunt_attempts_2025_2026.csv`)에서 `W/번트파울`은 연결된 VB 공 전부가 `B`였다(2025년 756구, 2026년 623구). 같은 정정표에 `source: naver_relay`로 추가했다(`scripts/build_naver_bunt_corrections.py`). 연결 방식이 `matched_id`·`matched_context`인 행만 쓴다. TrackMan 방식과 달리 타석을 끝낸 2스트라이크 번트 파울(2025년 6구, 2026년 5구)도 포함된다.
  - 대응 검증: `W`·`V` 1,629구 중 1,546구는 "VB 투구 전 카운트 + 1스트라이크 = 네이버 투구 후 카운트"가 그대로 맞는다. 틀린 83구 중 82구는 같은 타석 앞쪽에 번트가 있어 VB 카운트가 이미 어긋난 경우다.
  - 새로 수집한 2026 경기는 정정표를 다시 만들어야 반영된다.
  - PR #32에서 연결되지 않은 `W` 6구는 원인을 확인해 `supplements`로 추가했다(`analysis/sbj_location/results/naver_unmatched_W_2025_2026.csv`). 4구는 네이버 투수 ID가 타석 중간에 바뀐 경우라 투수 없는 연결과 카운트 게이트로, 2구는 VB·중계 모두 타석 첫 공 행이 없는 경우라 구속 순서로 사람이 확인했다.
- **2019–2024 KIA 홈 경기 (네이버 기준)**: TrackMan에 KIA 홈 경기가 없어 네이버 중계로 전수 조사했다(`analysis/sbj_location/naver_kia_home_bunts.py`, 432경기, 누락 이닝 0). 네이버 `W` 443구가 모두 VB `B`와 연결됐다.
  - 정정은 타석 단위 카운트 게이트를 통과한 443구 전부다. 게이트는 정정 뒤 VB 카운트가 타석의 모든 공에서 네이버와 같아야 통과한다.
  - 시즌별 76 / 56 / 80 / 73 / 91 / 67구이고, 정정표 해당 시즌에 `supplements`와 행별 `source: naver_relay`로 병합했다. TrackMan 행은 그대로다.
  - 네이버 투수 ID가 타석 중간에 바뀌는 경우가 있어, 투수 없이 연결한 1구는 게이트 통과 시에만 썼다.
  - 연결 키에는 반이닝 안의 타석 순번이 들어간다. 같은 반이닝에 두 번 나온 타자가 다른 타석과 연결되지 않고, 한쪽에서 빠진 타석이 이웃 타석과 짝지어지지 않는다.
  - 합격 기준 K1–K5와 K4 미달(2020·2023) 수용 사유는 `analysis/sbj_location/sbj_validation_gates.md`에 있다.
- **2019–2024 TrackMan 미수록 비KIA 경기 (네이버 기준)**: 홈 코드가 `HT`가 아니고 TrackMan 경기에 매핑되지 않은 67경기(20 / 3 / 1 / 17 / 13 / 13)를 같은 방식으로 조사했다(`analysis/sbj_location/naver_non_tm_bunts.py`, 누락 이닝 0).
  - 네이버 `W` 68구가 모두 VB `B`와 연결됐고, 게이트를 통과한 68구를 모두 정정했다(24 / 2 / 0 / 20 / 12 / 10). 투수 없이 연결한 1구도 게이트를 통과했다.
  - 정정표에는 입력 파일별 `supplements`로 들어간다. `build_naver_bunt_corrections.py`는 같은 입력의 supplement와 그 입력이 다룬 경기의 `naver_relay` 행만 교체한다. 그래서 KIA 홈 입력과 이 입력을 따로, 어떤 순서로 다시 돌려도 서로의 행을 지우지 않는다.
  - 적용 뒤 K5를 다시 확인했다(`sbj_validation_gates.md`).
- **VB `V` = 번트 헛스윙**: 네이버 `V/번트헛스윙`과 VB `V`가 2025년 146/147구, 2026년 104/104구 일치한다. `V`는 원래 스윙·테이크 어느 쪽도 아니라 지표에서는 이미 빠져 있었다. 문제는 카운트였다. 파서가 `V`에 스트라이크를 더하지 않아 뒤 공 카운트가 한 개씩 모자랐다.
  - TrackMan 확인: 2019–2024에 확인 가능한 `V` 685구 전부가 다음 공에서 스트라이크 +1이었다(`analysis/sbj_location/v_code_trackman.py`).
  - 조치: `GameState.apply_non_terminal_pitch`가 `V`를 스트라이크로 센다. `apply_call_corrections.py`는 `V`가 있는 타석의 카운트도 다시 계산한다.
- **적용과 확인 순서**: 정정표를 바꾸면 세 단계를 거친다. 확인이 통과한 상태로만 curated를 커밋한다.
  1. `python scripts/apply_call_corrections.py --check`
  2. `python scripts/apply_call_corrections.py`: 월 파티션을 달마다 한 번만 다시 쓴다. `--root`로 사본에 시험할 수 있다.
  3. `python scripts/check_call_corrections.py`: 전 시즌 `clean: true`여야 한다.
- 번트 인플레이(네이버 `H`, VB `X`)는 아직 지표에 포함돼 있다. 이 공을 빼려면 표시 컬럼이 필요하다(스키마 변경, 별도 승인).

## 카운트 정정 (대타·피치클락)

2026-09-30 적용 결과다. 대상은 `analysis/sbj_location/results/naver_count_audit_games_2019_2026.json`의 **201경기**(2019–2024 91, 2025 60, 2026 50)다. 전 시즌 모두 VB만 보고 카운트 이상이 드러나는 경기만 골랐으며, 전 경기 조사가 아니다. 네이버 전 이닝 수집에서 누락 경기·이닝은 0이었다. 감사 근거는 `naver_count_audit_2019_2026.csv`와 `naver_count_audit_2019_2026_summary.json`이다.

### 원인·규칙·게이트

- **타석 중간 대타**: 새 타자는 기존 카운트를 이어받지만 VB는 새 타석을 0-0으로 시작한다. 네이버 `currentGameState`의 타석 첫 줄 카운트를 시작 카운트로 쓴다.
- **피치클락 위반(2025년부터)**: 투수 위반은 자동 볼, 타자 위반은 자동 스트라이크다. VB에 투구 행이 없으므로 다음 VB 공 앞에 판정만 삽입한다. 실제 투구 행을 만들지는 않는다.
- **판정 정정**: VB `B`·네이버 `W`는 놓친 번트 파울로 `B→W` 정정한다. TrackMan 경로의 `W`를 네이버가 `B`로 기록한 경우는 `W→B`로 되돌린다.
- **연결·게이트**: 네이버 공은 타석 안 실제 투구 순서로 다시 번호를 붙이고 반이닝 타석 순번·타자·투수·순번·구속 ±1km/h로 연결한다. 길이가 같은 한 타석의 모든 공이 연결되고, 시작 카운트·위반·판정 변경을 파서 규칙으로 재생한 결과가 **모든 공의 네이버 투구 전 카운트와 같을 때만 `fix_pass`**다. 다른 코드 불일치나 설명되지 않는 카운트 변화가 있으면 정정하지 않는다.

카운트는 `data/corrections/vb_count_corrections.json`의 `pas`에 시작값(`start`)과 위반 삽입(`inserts`)으로 기록한다. 판정은 `vb_bunt_foul_corrections.json`에 기록한다. 추가 행은 `source: naver_relay`, `match_status: naver_count_audit`와 이 감사 입력의 supplement이고, 되돌린 7구는 `naver_rejected`에 남긴 뒤 source 키 없는 TrackMan 행을 제거했다. 파서와 적용기는 같은 정정표를 읽으며 타자·투수·코드가 일치할 때만 카운트 정정을 적용한다.

### 시즌별 감사·적용 결과

대타·피치클락·B→W·W→B 열은 `fix_pass` **타석 수**이고 종류가 겹칠 수 있다. 판정 적용 구는 두 방향을 합한 실제 변경 구 수(`W_applied` 출력)다. 재계산 타석은 저장 카운트가 실제로 바뀐 타석 수다.

| 시즌 | 대상 경기 | 누락 경기 | 대타 | 피치클락 | B→W | W→B | unexplained | 판정 적용 구 | 재계산 타석 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 2019 | 13 | 0 | 7 | 0 | 6 | 1 | 0 | 7 | 13 |
| 2020 | 19 | 0 | 14 | 0 | 4 | 1 | 0 | 6 | 19 |
| 2021 | 12 | 0 | 4 | 0 | 8 | 2 | 1 | 13 | 12 |
| 2022 | 15 | 0 | 11 | 0 | 7 | 1 | 0 | 8 | 17 |
| 2023 | 17 | 0 | 16 | 0 | 4 | 1 | 0 | 5 | 20 |
| 2024 | 15 | 0 | 11 | 0 | 3 | 0 | 8 | 4 | 13 |
| 2025 | 60 | 0 | 13 | 59 | 0 | 0 | 1 | 0 | 72 |
| 2026 | 50 | 0 | 15 | 34 | 0 | 0 | 2 | 0 | 49 |

게이트를 통과한 타석은 총 221개다. 카운트표는 대타 91·피치클락 93타석, 합계 184타석이고, 판정 정정은 B→W 36구·W→B 7구다. 실제 적용은 판정 43구·카운트 재계산 215타석·184경기 쓰기였으며, skipped는 전 시즌 0이다. 종료 공의 판정만 바뀌어 저장 카운트가 그대로인 타석도 있어 게이트 통과 타석 수와 재계산 타석 수는 다르다.

| 시즌 | length_differs | unjoined | 코드 불일치 B→W (구) | W→B (구) |
|---|---:|---:|---:|---:|
| 2019 | 0 | 0 | 6 | 1 |
| 2020 | 0 | 0 | 5 | 1 |
| 2021 | 0 | 21 | 10 | 3 |
| 2022 | 0 | 0 | 7 | 1 |
| 2023 | 0 | 0 | 4 | 1 |
| 2024 | 10 | 26 | 4 | 0 |
| 2025 | 0 | 0 | 0 | 0 |
| 2026 | 0 | 2 | 0 | 0 |

`unexplained` 12·`length_differs` 10·`unjoined` 49타석은 보고만 하고 정정하지 않았다. 코드 불일치 구 수와 `fix_pass` 종류별 타석 수는 단위가 다르다.

### 보존·적용·재현 순서

1. 번트 정정표 사본을 보관한 뒤 감사 CSV로 `scripts/build_naver_count_corrections.py`를 실행한다. 기존 행·supplement의 JSON 값 보존을 확인한다. 이번 실행에서 기존 2025–2026 PR #32 행과 unmatched 6구 supplement, KIA 홈·비KIA 미수록 supplement는 그대로다. 허용된 변화는 감사 행 36구 추가와 `naver_rejected`에 기록된 TrackMan 행 7구 삭제뿐이었다.
2. `PYTHONPATH=src python scripts/apply_call_corrections.py --check`로 전 시즌 skipped 0을 확인한 뒤 같은 명령을 `--check` 없이 실행한다. curated와 manifest·파티션 digest를 함께 갱신한다. 2025 원본은 `seasons/2025/data/raw/2025`에 있으며 manifest의 `raw_sha256`와 일치하는 사본이 필요하다.
3. `PYTHONPATH=src python scripts/check_call_corrections.py`로 2019–2026 전 시즌 clean을 확인한다. pending·stale·untracked_W·count_stale·count_errors는 모두 0이었다.
4. 감사를 다시 실행하고 정정표를 다시 생성한다. 빌더 수정 `7fd07859`를 반영한 뒤 연속 두 번 생성한 두 정정표는 **바이트 단위 동일**했다. 정정 대상 목록·값은 수정 전과 같고 표 상태에 의존하던 `calls_rejected_trackman_rows` 통계만 제거됐다.
5. `PYTHONPATH=src python -m visualbaseball.cli --exports-only` → 2024·2025 `--only zone_decision` → 2022–2025 `--only pitch_arsenal` 순으로 생성하고 `check_zone_decision_outputs.py`, `check_metric_state.py`, 전체 pytest와 `node tests/test_pitch_arsenal_layout.cjs`를 확인한다. Release 업로드는 하지 않는다.

### 재생성·최종 검증 (2026-09-30)

Python 3.12.10과 `constraints-za.txt` 고정 의존성을 사용했고 Python 실행에는 `PYTHONPATH=src`, 모델 재생성에는 `OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2`를 설정했다. 사용자 허용에 따라 Windows 로컬에서 실행했다.

| 명령·검사 | 종료 코드 | 결과 |
|---|---:|---|
| `naver_relay_fetch.py` (고정 대상 목록) | 0 | 201경기, 누락 0, 요청 간격 1.05초 유지 |
| `naver_count_audit.py`·`build_naver_count_corrections.py` | 0 | 감사·정정표 생성, 재감사 CSV·JSON 동일 |
| `apply_call_corrections.py --check`·실제 적용 | 0 | 전 시즌 skipped 0, 판정 43구·215타석·184경기 적용 |
| `check_call_corrections.py` | 0 | 2019–2026 전 시즌 clean |
| 수정 빌더 연속 두 번 생성·비교 | 0 | 두 정정표 바이트 동일, 정정 목록·값 보존 |
| `visualbaseball.cli --exports-only` | 0 | 2026 파생 산출물 재생성 |
| `visualbaseball.cli --season <2024,2025> --only zone_decision` | 각각 0 | 같은 `za7.2-pswing-pitcher-hand` 모델로 재생성 |
| `visualbaseball.cli --season <2022,2023,2024,2025> --only pitch_arsenal` | 각각 0 | Pitch Plot 재생성 |
| `check_zone_decision_outputs.py` | 0 | 2024–2026 ZA JSON·CSV·입력 상태 일치, 2022–2026 Pitch Plot 스키마 3 일치 |
| `check_metric_state.py` | 0 | 2026 stale 없음; 사용하지 않는 legacy `plate_decision` 상태 없음 알림 |
| `python -m pytest` | 0 | 151 passed (82.55초), 정정 일치·회귀·멱등성 검사 포함 |
| `node tests/test_pitch_arsenal_layout.cjs` | 0 | 구종 수·구사율·차트 경계·빈 데이터 검사 통과 |
| `python -m visualbaseball.dataset_summary` | 0 | 완료된 과거 시즌 재생성 상태까지 요약 갱신 |

ZA report의 채점 투구 수는 2024 **221,551**, 2025 **216,858**, 2026 **202,448**이다. 세 report의 schema hash는 현재 코드와 일치한다. `--exports-only`가 player_bio의 원본 digest도 현재 curated에서 다시 계산하므로 그 파생 파일도 함께 갱신했다. 원본 수집 캐시와 Excel은 커밋하지 않으며 Release 업로드도 하지 않았다.

### 남은 한계

- 모든 시즌에서 VB만 보고 이상이 드러나는 201경기만 조사했다. 목록 작성일 **2026-09-29 이후 경기는 포함하지 않았다**.
- 2025–2026 피치클락 위반은 타석이 인플레이로 끝나면 VB에 흔적이 없다. 대상 선정은 표본 기준 **5/37건, 약 14%**만 잡는다. 위 표의 93타석은 이 제한된 대상의 결과이지 전체 위반 수가 아니다.
- 카운트 사건의 영향은 사건 뒤 같은 타석 몇 구에 국한되고 전체 투구의 약 **0.3–0.4%**로 추정된다. **카운트 정정**은 `p_swing`의 카운트 입력에만 영향이 있고 `p_zone`에는 없다. B→W·W→B **판정 정정**은 테이크 적격성과 `p_zone` 학습 대상도 바꾼다.
- 그 밖 경기의 놓친 번트 파울과 TrackMan 오정정은 남아 있다. 네이버와 VB는 공급원을 공유할 수 있어 네이버는 독립 좌표 측정이 아니라 다른 기록 경로다.

## 정정표 월간 갱신 (2026 시즌 진행 중)

정정표는 만든 날까지의 경기만 담는다. 새 경기는 한 달에 한 번 아래 순서로 반영한다. 모든 명령에 `PYTHONPATH=src`가 필요하다. 네이버 중계 캐시(`data/raw/naver/relay_raw`)는 gitignore라 새 환경에서는 처음부터 받는다(1초당 1요청).

1. **카운트 감사 대상 추가**: `python analysis/sbj_location/count_audit_targets.py analysis/sbj_location/results/naver_count_audit_games_2019_2026.json 2026`
   - 기존 목록에 새 경기만 더하고 아무것도 빼지 않는다. 이미 정정한 경기는 카운트가 맞아 보여 다시 뽑히지 않지만, 빌더가 시즌을 감사 결과로 통째로 다시 만들므로 목록에서 빠지면 정정도 사라진다.
2. **수집**: `python analysis/sbj_location/naver_relay_fetch.py analysis/sbj_location/results/naver_count_audit_games_2019_2026.json` (중단되면 같은 명령으로 이어받음)
3. **감사**: `python analysis/sbj_location/naver_count_audit.py analysis/sbj_location/results/naver_count_audit_games_2019_2026.json` — 전 시즌을 돌린다. 시즌 인자를 주면 결과 CSV가 그 시즌만 남는다.
4. **정정표**: `python scripts/build_naver_count_corrections.py analysis/sbj_location/results/naver_count_audit_2019_2026.csv`
5. **2026 번트 파울(PR #32 경로)**: `python analysis/sbj_location/bunt_relay_fetch.py` → `python analysis/sbj_location/bunt_attempts.py` → `python scripts/build_naver_bunt_corrections.py analysis/sbj_location/results/bunt_attempts_2025_2026.csv 2026`
   - 2025–2026 종료 경기 전부의 중계가 필요하다. 새 환경에서는 수집에 몇 시간이 걸리므로 시즌 종료 후 한 번 해도 된다.
6. **적용과 확인**: 위 "적용과 확인 순서"대로 `apply_call_corrections.py --check` → 적용 → `check_call_corrections.py`(전 시즌 clean). 그 뒤 `--exports-only`, ZA 2024–2025, Pitch Plot 2022–2025를 다시 만들고 `check_zone_decision_outputs.py`, `pytest`를 통과시킨다.
7. 정정표만 커밋하지 않는다. curated와 파생 산출물을 함께 커밋한다.

## SBJ 보고 위치·궤적 불일치 제외

ABS 시즌(2024년부터)에 보고 `px/pz`가 자기 궤적의 보고면 값과 **1cm 넘게** 어긋나는 공은 SBJ 학습·채점에서 제외한다. `px`는 중간면, `pz`는 앞면과 비교한다. 원인을 알 수 없는 기록 혼합이므로 보고 위치나 궤적 중 하나를 대신 믿어 값을 덮어쓰지 않는다.

운영 코드는 `zone_decision.reported_location_disagrees`이며, ZA `data/metrics/zone_awareness/<시즌>/report.json`의 `source.excluded.reported_location_off_trajectory`에 집계된다. 이번 재생성의 제외 결과는 **2025년 6구**, 2024·2026년 0구다. 이 규칙은 이미 있는 운영 경로를 실행한 것이며 이번 작업에서 로직을 바꾸지 않았다.

