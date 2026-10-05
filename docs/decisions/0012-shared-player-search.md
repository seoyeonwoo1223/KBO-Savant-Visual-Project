# 0012. 선수 검색 UI를 Swing/Take 형태로 통일

- **상태**: 채택 (2026-10)

## 맥락
선수 검색이 두 형태로 갈려 있었습니다. Zone Profile·Pitch Plot은 라벨이 위에 오는 컨트롤 줄(Pitch Plot은 둥근 카드), Swing/Take는 빨간 밑줄 제목 줄 + "라벨 | 입력 | 버튼" 한 줄이었습니다. Swing/Take 안에서도 인덱스(`styles.css`)와 프로필(`profile.css`)이 같은 규칙을 따로 갖고 있었습니다. Zone Profile 상단의 초록 공식 박스는 다른 도구에 없는 색이라 떠 보였습니다.

## 결정
- Swing/Take 형태를 기준으로 합니다. 제목 줄(`.search-heading`, 빨간 밑줄) 오른쪽에 연도 등 선택칸(`.search-pickers` > `.search-picker`), 아래에 `form.player-search`, 그 아래 `.search-message`.
- 규칙은 `theme.css` 한 곳에 둡니다. 도구 CSS의 `label`·`select`·`input`·`button` 태그 규칙이 새어 들지 않도록 높이·여백·모서리·글꼴을 모두 적습니다.
- 제목은 대상에 맞춥니다: Swing/Take `Batter Search`, Zone Profile `Player Search`(타자·투수), Pitch Plot `Pitcher Search`. 버튼 문구는 페이지 동작에 맞게 둡니다(Swing/Take "프로필 보기", 후보 목록을 먼저 보여 주는 Zone·Pitch Plot "검색").
- Zone Profile의 초록 공식 박스를 없애고, 결과 아래 기존 회색 설명줄(`.method`)에 합칩니다. Swing/Take·Pitch Plot이 공식을 결과 아래 회색 글씨로 두는 방식과 같습니다.
- 요소 `id`는 바꾸지 않아 JS는 그대로입니다.

## 기각한 대안
- Zone Profile 형태(라벨 위 컨트롤 줄)로 통일: 대상 선택칸을 그대로 둘 수 있지만 Swing/Take의 빨간 밑줄 제목 줄이 사라집니다. 사용자가 제목 줄을 유지하기로 했습니다.
- 공식 박스를 색만 바꿔 상단에 유지: 결과가 없을 때도 공식만 떠 있고, 다른 도구는 공식을 결과 아래에 둡니다.
- 페이지별 CSS에 같은 규칙 복사: 이미 Swing/Take 두 파일에서 어긋나고 있었습니다.

## 결과
- 새 도구에 선수 검색이 필요하면 위 클래스를 쓰고 페이지 CSS에 검색 규칙을 새로 만들지 않습니다.
- 검색 패널은 썸네일 모드에서 숨겨지므로 썸네일은 바뀌지 않습니다. 변경 시 썸네일 대상 화면이 같은지 확인합니다.
