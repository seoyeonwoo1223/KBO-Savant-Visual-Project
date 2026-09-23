# TrackMan tracking raw data

`data/tracking/raw/season=<year>/trackman_history.csv`에는 받은 TrackMan 원본을 시즌별로 나눈 데이터를 둔다. 값은 문자열 그대로 보존하며, `data/tracking/summary.json`에는 원본과 시즌 파일의 SHA-256, 행 수, 컬럼 순서를 기록한다.

선수 조인은 문자열로 변환한 `pitcher_trackman_id → pitcher_id`, `batter_trackman_id → batter_id`를 사용한다. 같은 시즌에 실제로 겹치는 ID 목록과 비율은 `data/tracking/player_id_overlap.json`에 기록한다. ID 값은 변환하지 않는 동등 조인이므로, 이 파일은 조인 가능한 선수만 명시한 필터 역할을 한다.

동등 조인은 외국인 선수를 조용히 뺀다. TrackMan은 이들에게 6자리 MLB식 ID(예: 윌커슨 `658792`)를 쓰고 Visual Baseball은 KBO ID(`53546`)를 쓰기 때문이다. 2019–2024 KBO 경기 TrackMan 투구 중 투수 ID가 동등 조인으로 연결되는 비율은 75–81%뿐이다. `scripts/build_trackman_id_crosswalk.py`가 만드는 `data/tracking/player_id_crosswalk.json`이 시즌·역할(투수/타자)별 대응표이며, 규칙은 다음과 같다.

- 경기: 같은 날짜에서 투수 ID 집합의 Jaccard가 0.6 이상이고 2위가 0.3 미만인 경우만 짝짓고, 한 VB 경기를 두 TrackMan 경기가 가리키면 둘 다 버린다.
- 투구: 반이닝 안 타석 순서와 타석 안 투구 번호로 맞추고, ID를 쓰지 않는 검증(투구 전 볼·스트라이크·아웃 일치)을 통과한 투구만 쓴다.
- 쌍: 그 투구들에서 (TrackMan ID, VB ID)가 20구 이상이고, 양방향 모두 해당 ID 투구의 90% 이상을 차지하며, 일대일인 경우만 받아들인다. 거부된 쌍과 사유(`support`, `share`, `reverse_share`, `many_to_one`)도 함께 기록한다.

조회 순서는 대응표의 받아들인 쌍, 그다음 같은 시즌 문자열 동등이다. 이렇게 하면 투수 기준 97.9–98.6%, 타자 기준 98.9–99.4%의 TrackMan 투구가 VB 선수로 연결되고, 두 방식이 서로 다른 VB ID를 내는 경우는 0건이다. 대응표는 선수 단위 산출물이며 투구 단위 매핑을 공개하지 않는다. 아래의 투구 단위 결합 제한은 그대로다.

두 공급자는 공 단위 공통 식별자를 제공하지 않는다. TrackMan의 `trackman_game_id`와 Visual Baseball의 `game_id` 형식도 다르므로, 이 데이터는 선수·시즌·구종 단위의 무브먼트 프로필 및 보정 연구에만 직접 조인한다. 투구 단위 결합은 별도의 경기·타석·투구 순서 검증을 통과한 매핑 없이는 하지 않는다.

TrackMan은 구속, 회전수, 수직·수평 무브먼트, 릴리스 포인트를 제공한다. Visual Baseball canonical pitches는 결과, 카운트, 존 위치(`px`, `pz`), 타구·이벤트 상태를 제공한다. 탄착군과 경기 결과는 Visual Baseball을 기준으로 유지한다.
