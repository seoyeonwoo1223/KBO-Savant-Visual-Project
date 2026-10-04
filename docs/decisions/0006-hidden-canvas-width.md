# 0006. 숨겨진 탭의 canvas는 직전 CSS 폭으로 그린다

- **상태**: 채택 (PR #49)

## 맥락
아이폰에서 Approach의 Decision Map이 작게 깨졌습니다. 숨겨진 탭의 canvas는 `getBoundingClientRect().width`가 0이라 `canvasContext()`가 장치 픽셀 폭(`canvas.width`)을 대신 썼고, resize가 올 때마다 DPR배씩 커졌습니다(6회에 87040px). iOS Safari는 주소창이 접히고 펴질 때마다 resize를 보내므로 캔버스 한도를 넘었습니다.

## 결정
- 숨겨진 상태에서는 직전 CSS 폭(`_cssWidth`)을 쓰고, 비율은 HTML `width`/`height` 속성에서 처음 한 번만 읽습니다(`_aspect`).

## 기각한 대안
- 숨겨진 canvas는 그리지 않기: 탭 전환 시 그리기 순서를 모두 바꿔야 하고, 썸네일 모드 같은 다른 경로가 영향을 받습니다.

## 결과
- 새 canvas 차트는 같은 패턴(`zone-awareness.js`의 `canvasContext`)을 따릅니다. 모바일 에뮬레이션에서 숨긴 채 resize를 여러 번 보내 크기가 유지되는지 확인합니다.
