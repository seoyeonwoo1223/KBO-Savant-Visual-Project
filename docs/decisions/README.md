# 결정 기록

사람이 내린 결정, 채택한 이유, 포기한 대안을 남깁니다. 에이전트는 매 세션 백지로 시작하므로, "왜 이렇게 되어 있나"는 여기서 찾습니다. 기각된 대안을 다시 시도하기 전에 해당 기록을 읽습니다.

## 쓰는 법

- 파일 이름 `NNNN-짧은-영문-이름.md`, 번호는 이어서 붙입니다. 한 결정에 한 파일.
- 형식: **상태**(채택/대체됨) · **맥락**(무슨 문제였나) · **결정** · **기각한 대안**(왜 안 했나) · **결과**(지켜야 할 것, 관련 검사).
- 결정을 뒤집으면 기존 파일을 지우지 말고 상태를 `대체됨 → NNNN`으로 바꾸고 새 기록을 씁니다.
- 지표·모델 결정은 근거가 길어서 `analysis/*/README.md`, `analysis/sbj_formula/gates.md` 등에 있습니다. 아래 목록에서 링크합니다.

## 목록

| # | 결정 | 영역 |
|---|---|---|
| [0001](0001-web-is-output-only.md) | `web/`·`exports/`는 출력물이며 입력으로 읽지 않는다 | 데이터 |
| [0002](0002-curated-partition-layout.md) | 시즌별 partition 레이아웃 공존, 2022–2024 game shard 유지 | 데이터 |
| [0003](0003-savant-two-tier-header.md) | Baseball Savant식 2단 헤더와 단일 페이지 폭 1440px | 웹 |
| [0004](0004-swing-take-mobile-image.md) | 모바일 Swing/Take 프로필은 데스크톱 레이아웃 이미지로 표시 | 웹 |
| [0005](0005-no-modern-css-color-in-capture.md) | html2canvas 캡처 대상에 `color-mix()` 등 최신 색 함수 금지 | 웹 |
| [0006](0006-hidden-canvas-width.md) | 숨겨진 탭의 canvas는 직전 CSS 폭으로 그린다 | 웹 |
| [0007](0007-velocity-chart-without-labels.md) | Pitch Plot 구속 분포에서 구종 이름 열 제거 | 웹 |
| [0008](0008-chart-axis-on-ticks.md) | 차트 축 범위는 눈금 간격의 배수 | 웹 |
| [0009](0009-web-contract-non-blocking.md) | 웹 규격 검사는 배포를 막지 않는 별도 체크 | 하네스 |
| [0010](0010-frozen-files.md) | 얼린 파일과 그 이유 | 하네스 |
| [0011](0011-harness-structure.md) | 하네스를 4개 구성요소로 나누고 AGENTS.md는 지도로 유지 | 하네스 |
| [0012](0012-zone-profile-color-scale.md) | ~~Zone Profile 색: 비율은 한 방향 색, AVG는 .250 중심, 기본 최소 표본 5구~~ (대체됨 → 0015) | 웹 |
| [0012](0012-shared-player-search.md) | 선수 검색은 Swing/Take 형태, 안내문구는 Blocking 카드로 통일 (`theme.css` 공통 클래스) | 웹 |
| [0013](0013-estimated-arm-angle-v3.md) | 고슬롯 가중 eAA-v3와 별도 비대칭 모델 참고 범위 | 지표·웹 |

| [0014](0014-current-leaderboard-refresh.md) | 현재 시즌 리더보드 자동 갱신·공식 주루 연결·OAA 조건부 서식 | 지표·웹 |
| [0015](0015-zone-profile-league-relative.md) | Zone Profile 색은 칸별 리그 평균 대비 차이 (리그 = 흰색) | 지표·웹 |

| [0015](0015-position-exposure-adjustment.md) | 포지션별 공식 수비이닝과 DH 타석 분리 보정 | 지표 |
| [0016](0016-naver-dh-verification.md) | 복합 DH 표기를 네이버 타석별 포지션으로 재검증 | 지표 |
| [0017](0017-unused-web-code.md) | 미사용 웹 코드만 참조·화면 동일성 확인 후 제거 | 웹·하네스 |
| [0018](0018-swing-take-capture-background.md) | Swing/Take 모바일·저장 이미지의 League Avg 점선 배경 | 웹·하네스 |
| [0019](0019-swing-take-mobile-loading.md) | 모바일 Swing/Take 로딩 표시에서 완성 이미지로 전환 | 웹·하네스 |

| [0020](0020-leaderboard-pagination.md) | 리더보드 열 정렬·번호 페이지·색 대비 | 웹 |

### 다른 곳에 있는 결정·근거

| 주제 | 문서 |
|---|---|
| ZA/APR 모델 설계·한계 | `analysis/zone_decision/README.md` |
| 공격성 중립 APR(B) 운영 반영 게이트 | `analysis/sbj_formula/gates.md` |
| 이전 세대 모델과 2022–2025 이력 | `analysis/plate_decision_v1/` |
| 무브먼트 보정(TrackMan 검증) | `analysis/movement_calibration/README.md` |
| 팔각도(eAA) 정의 | `analysis/arm_angle/eaa-definition.md` |
| 궤적·px 기준면 감사 | `analysis/trajectory_audit/README.md` |
| curated 계약 | [../curated-data.md](../curated-data.md) |
| SBJ 데이터 신뢰 감사 | [../sbj-data-quality.md](../sbj-data-quality.md) |
