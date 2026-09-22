# TrackMan tracking raw data

`data/tracking/raw/season=<year>/trackman_history.csv`에는 받은 TrackMan 원본을 시즌별로 나눈 데이터를 둔다. 값은 문자열 그대로 보존하며, `data/tracking/summary.json`에는 원본과 시즌 파일의 SHA-256, 행 수, 컬럼 순서를 기록한다.

선수 조인은 문자열로 변환한 `pitcher_trackman_id → pitcher_id`, `batter_trackman_id → batter_id`를 사용한다. 같은 시즌에 실제로 겹치는 ID 목록과 비율은 `data/tracking/player_id_overlap.json`에 기록한다. ID 값은 변환하지 않는 동등 조인이므로, 이 파일은 조인 가능한 선수만 명시한 필터 역할을 한다.

두 공급자는 공 단위 공통 식별자를 제공하지 않는다. TrackMan의 `trackman_game_id`와 Visual Baseball의 `game_id` 형식도 다르므로, 이 데이터는 선수·시즌·구종 단위의 무브먼트 프로필 및 보정 연구에만 직접 조인한다. 투구 단위 결합은 별도의 경기·타석·투구 순서 검증을 통과한 매핑 없이는 하지 않는다.

TrackMan은 구속, 회전수, 수직·수평 무브먼트, 릴리스 포인트를 제공한다. Visual Baseball canonical pitches는 결과, 카운트, 존 위치(`px`, `pz`), 타구·이벤트 상태를 제공한다. 탄착군과 경기 결과는 Visual Baseball을 기준으로 유지한다.
