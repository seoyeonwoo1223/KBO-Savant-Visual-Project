# TrackMan tracking raw data

`data/tracking/raw/season=<year>/trackman_history.csv`에는 받은 TrackMan 원본을 시즌별로 나눈 데이터를 둔다. 값은 문자열 그대로 보존하며, `data/tracking/summary.json`에는 원본과 시즌 파일의 SHA-256, 행 수, 컬럼 순서를 기록한다.
Windows에서 Git이 CSV를 CRLF로 체크아웃하면 파일 바이트 해시는 저장된 LF 원본 해시와 달라진다. SBJ 감사 하네스는 CRLF를 LF로 정규화한 해시를 대응표의 시즌 해시와 대조한다. 행 값은 이 줄바꿈 차이로 바뀌지 않는다.

선수 조인은 문자열로 변환한 `pitcher_trackman_id → pitcher_id`, `batter_trackman_id → batter_id`를 사용한다. 같은 시즌에 실제로 겹치는 ID 목록과 비율은 `data/tracking/player_id_overlap.json`에 기록한다. ID 값은 변환하지 않는 동등 조인이므로, 이 파일은 조인 가능한 선수만 명시한 필터 역할을 한다.

동등 조인은 일부 선수를 조용히 뺀다. TrackMan이 6자리 MLB식 ID(예: 윌커슨 `658792`)를 쓰는 선수가 있고, Visual Baseball은 같은 선수에게 KBO ID(`53546`)를 쓰기 때문이다. 현재 2019–2024 대응표에서 다른 ID로 연결된 149개의 TrackMan ID는 모두 6자리다. 대부분 외국인 선수이고, 류현진·추신수·이대호·이대은·권광민·남태혁·문찬종·정수민·진우영 9명은 한국 선수다(미국 프로야구 경력이 공통점으로 보이나 전수 확인은 하지 않았다). 2019–2024 1군 경기 TrackMan 투구 중 투수 ID가 동등 조인으로 연결되는 비율은 약 76–83%뿐이다. `scripts/build_trackman_id_crosswalk.py`가 만드는 `data/tracking/player_id_crosswalk.json`이 시즌·역할(투수/타자)별 대응표이며, 규칙은 다음과 같다.

- 범위: 투수·타자 양쪽 팀 코드가 모두 1군 KBO 구단인 TrackMan 행만 쓴다. 투수팀만 `MIN_*`이 아닌 행에도 2군 상대 타자가 섞이므로 한쪽만 검사하면 안 된다.
- 경기: 같은 날짜에서 투수 ID 집합의 Jaccard가 0.6 이상이고 2위가 0.3 미만인 경우를 우선 짝짓는다. 남은 경기는 날짜와 양 팀이 양쪽 자료에서 정확히 한 경기씩인 경우만 보조 연결한다. 더블헤더 등 복수 후보를 추측하지 않고, 한 VB 경기를 두 TrackMan 경기가 가리키면 버린다.
- 투구: 반이닝 안 타석 순서와 타석 안 투구 번호로 맞추고, ID를 쓰지 않는 검증(투구 전 볼·스트라이크·아웃 일치)을 통과한 투구만 쓴다.
- 쌍: 그 투구들에서 (TrackMan ID, VB ID)가 20구 이상이고, 양방향 모두 해당 ID 투구의 90% 이상을 차지하며, 일대일인 경우만 받아들인다. 거부된 쌍과 사유(`support`, `share`, `reverse_share`, `many_to_one`)도 함께 기록한다.

조회 순서는 대응표의 받아들인 쌍, 그다음 같은 시즌 문자열 동등이다. 수치는 두 종류로 나눠 읽어야 한다.

- **선수 연결률** (`pitches_resolved_*`): 1군 양 팀 TrackMan 행 중 투수·타자 ID가 VB 선수로 연결되는 비율이다. 2024년에는 투수·타자 모두 201,117/201,117구이고, 투수 6시즌 범위는 99.98–100%이다. 대응표와 문자열 동등이 서로 다른 VB ID를 가리키는 경우는 0건이다. 이것은 **투구끼리 짝지어졌다는 뜻이 아니다.**
- **학습 투구 내 ID 일치** (`in_sample_id_consistent_pitches`): 경기·순서·카운트·아웃이 맞고, 조회 후 투수와 타자 ID까지 모두 맞는 투구다. VB 전체 투구의 85.7–88.3%이다(2024년 193,763구, 86.8%). 대응표를 만든 바로 그 투구에서 다시 센 **내부 일치율**이고 구속 조건도 없으므로, 최종 투구 매핑률이 아니다. 경기 매핑이 되지 않은 경기와 TrackMan 자체가 없는 경기는 여기서 빠진다.
- **남은 ID 불일치** (`state_agreeing_pitches_with_id_mismatch`): 카운트·아웃이 맞은 투구 중 조회 후에도 ID가 다른 투구다. 2024년 투수 170구, 타자 240구이다. 정렬 오류이거나, 표본이 부족해 대응표에 들어가지 못한 선수일 수 있다.

대응표는 선수 단위 산출물이다. 현재 `src/`의 생산 코드에서는 읽지 않고, 연구용 `analysis/movement_calibration/match_trackman.py`와 `analysis/trajectory_audit/pa_flow_strict.py`가 읽는다. 앞 스크립트는 경기·순서·카운트·아웃·조회 후 ID가 모두 맞고, VB 구속과 TM 릴리스 구속의 차이가 시즌 중앙값 ±3km/h 안인 투구만 짝짓는다. 과거 78.6–83.3% 수치는 변경 전 2군 혼입 집합에서 얻었으므로 현행 1군 매칭률로 재사용하지 않는다. 뒤 스크립트는 카운트를 연결 조건에서 빼고 불일치 자체를 검사한다. 빌드는 `summary.json`의 모든 시즌을 매번 다시 만들고(시즌 일부만 다시 쓰는 옵션은 없다), 시즌마다 TrackMan 파일 해시와 VB 입력 해시(`visualbaseball_sha256`)를 기록한다. VB 해시는 스크립트가 읽는 모든 컬럼(선수 이름 포함)을 덮으며, 컬럼 목록은 파일의 `rule.visualbaseball_sha256`에 적혀 있다.

두 공급자는 공 단위 공통 식별자를 제공하지 않는다. TrackMan의 `trackman_game_id`와 Visual Baseball의 `game_id` 형식도 다르므로, 이 데이터는 선수·시즌·구종 단위의 무브먼트 프로필 및 보정 연구에만 직접 조인한다. 투구 단위 결합은 위와 같은 경기·타석·투구 순서·구속 검증을 통과한 매핑으로만 한다.

SBJ용 1군 투구 전수 대조는 [SBJ 데이터 신뢰 감사](sbj-data-quality.md)의 읽기 전용 하네스를 사용한다. 이 하네스는 카운트를 연결 조건에서 빼고, 매칭 실패 사유와 사건 품질 플래그를 VB 투구마다 남긴다. 2025–2026에는 TrackMan 자료가 없어 `trackman_unavailable`로 표시한다.

TrackMan은 구속, 회전수, 수직·수평 무브먼트, 릴리스 포인트를 제공한다. Visual Baseball canonical pitches는 결과, 카운트, 존 위치(`px`, `pz`), 타구·이벤트 상태를 제공한다. 탄착군과 경기 결과는 Visual Baseball을 기준으로 유지한다.
