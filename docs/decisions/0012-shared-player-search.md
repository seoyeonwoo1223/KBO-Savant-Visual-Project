# 0012. 선수 검색 UI를 Swing/Take 형태로, 안내문구를 Blocking 카드로 통일

- **상태**: 채택 (2026-10)

## 맥락
선수 검색이 두 형태로 갈려 있었습니다. Zone Profile·Pitch Plot은 라벨이 위에 오는 컨트롤 줄(Pitch Plot은 둥근 카드), Swing/Take는 빨간 밑줄 제목 줄 + "라벨 | 입력 | 버튼" 한 줄이었습니다. Swing/Take 안에서도 인덱스(`styles.css`)와 프로필(`profile.css`)이 같은 규칙을 따로 갖고 있었습니다. Zone Profile 상단의 초록 공식 박스는 다른 도구에 없는 색이라 떠 보였고, 안내문구도 도구마다 회색 작은 글씨(Zone Profile `.method`, Swing/Take `.method-note`, Leaderboards `.source-note`), 옆 패널 상자(Movement Zones `.reading-note`), 3열 카드(Zone Awareness `.method`), Blocking 카드(`.method-card`)로 제각각이었고 Pitch Plot에는 설명이 없었습니다.

## 결정
- Swing/Take 형태를 기준으로 합니다. 제목 줄(`.search-heading`, 빨간 밑줄) 오른쪽에 연도 등 선택칸(`.search-pickers` > `.search-picker`), 아래에 `form.player-search`, 그 아래 `.search-message`.
- 규칙은 `theme.css` 한 곳에 둡니다. 도구 CSS의 `label`·`select`·`input`·`button` 태그 규칙이 새어 들지 않도록 높이·여백·모서리·글꼴을 모두 적습니다.
- 제목은 대상에 맞춥니다: Swing/Take `Batter Search`, Zone Profile `Player Search`(타자·투수), Pitch Plot `Pitcher Search`. 버튼 문구는 페이지 동작에 맞게 둡니다(Swing/Take "프로필 보기", 후보 목록을 먼저 보여 주는 Zone·Pitch Plot "검색").
- Zone Profile의 초록 공식 박스를 없애고 공식을 결과 아래로 옮깁니다.
- 안내문구는 Blocking의 "What is this?" 카드(`.method-card`: 흰 바탕 + 왼쪽 5px 회색 선)로 통일합니다. 규칙은 `theme.css`로 옮기고 모든 도구의 안내문구를 이 카드로 바꿉니다. 자리는 Blocking처럼 본문 맨 아래(선수를 고르기 전에도 보임)입니다. Pitch Plot에는 무브먼트 보정·중앙 75% 범위·표 색(백분위) 기준을 짧게 새로 적었습니다.
- 요소 `id`는 바꾸지 않아 JS는 그대로입니다.

## 기각한 대안
- Zone Profile 형태(라벨 위 컨트롤 줄)로 통일: 대상 선택칸을 그대로 둘 수 있지만 Swing/Take의 빨간 밑줄 제목 줄이 사라집니다. 사용자가 제목 줄을 유지하기로 했습니다.
- 공식 박스를 색만 바꿔 상단에 유지: 결과가 없을 때도 공식만 떠 있습니다.
- 회색 작은 설명줄로 통일: 한 번 시도했지만 사용자가 Blocking 카드 형식을 골랐습니다.
- 페이지별 CSS에 같은 규칙 복사: 이미 Swing/Take 두 파일에서 어긋나고 있었습니다.

## 결과
- 새 도구에 선수 검색이나 안내문구가 필요하면 위 클래스를 쓰고 페이지 CSS에 규칙을 새로 만들지 않습니다.
- Movement Zones의 "읽는 법"은 옆 패널에서 본문 아래 카드로 옮겼습니다. Zone Awareness의 `METHOD · 2019–2026` 머리글과 3열 배치는 카드 형식에 맞춰 없앴습니다.
- Pitch Plot 카드는 `#profile` 밖에 두어 이미지 저장(html2canvas `#profile`)에 들어가지 않습니다.
- 검색 패널과 안내 카드는 썸네일 모드에서 숨깁니다.
- 같은 PR에서 Zone Profile 썸네일을 고쳤습니다(`zone.css`의 thumbnail-mode `.savant-plot`·`.plot-column`).
  - 격자를 카드 가운데로 옮겼습니다. 왼쪽 세로 라벨 열과 같은 폭의 빈 열을 오른쪽에 둡니다.
  - 격자 폭을 385px에서 344px(8칸 × 43px)로 줄여 홈플레이트·축 이름까지 600px 카드 안에 들어오게 했습니다.
