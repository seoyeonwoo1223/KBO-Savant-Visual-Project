# 0005. html2canvas 캡처 대상에 `color-mix()` 등 최신 색 함수 금지

- **상태**: 채택 (PR #44)

## 맥락
Take 막대 색에 `color-mix(in srgb, color 56%, white)`를 쓰고 있었습니다. Chrome은 이를 `color(srgb …)`로 계산하는데, html2canvas 1.4.1은 이 형식을 읽지 못해 예외를 냅니다. 그 결과 데스크톱 "프로필 이미지 저장"도 조용히 실패하고 있었습니다(재현함).

## 결정
- 같은 섞임 값을 JS에서 hex로 계산해 CSS 변수(`--take-color`)로 넘깁니다. Chrome `color-mix` 결과와 4색 모두 같습니다.
- 캡처 대상 요소에는 `color-mix()`, `oklch()`, `lab()`, `color()` 같은 색 함수를 쓰지 않습니다.

## 기각한 대안
- html2canvas 교체·업그레이드: 1.4.1이 최신 배포판이고, 다른 라이브러리는 의존성과 결과 차이 검증이 필요합니다.

## 결과
- 캡처를 쓰는 페이지(현재 `web/profiles/`)를 고칠 때 이미지 저장을 실제로 눌러 확인합니다.
