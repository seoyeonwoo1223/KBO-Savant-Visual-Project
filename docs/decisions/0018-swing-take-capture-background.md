# 0018. Swing/Take League Avg 점선은 캡처 가능한 배경 타일로 표시

- **상태**: 채택 (2026-10)

## 맥락
League Avg의 Swing·Take 막대는 CSS `repeating-linear-gradient`로 그렸습니다. 브라우저 DOM에서는 보이지만 html2canvas 1.4.1은 반복 그라디언트를 그리지 못합니다. 모바일의 데스크톱 iframe 캡처와 다운로드 PNG에 숫자만 남고 막대가 사라졌습니다. 라이브러리를 실제로 로드하고 `html.profile-imaged` 상태에서 재현했습니다.

## 결정
- 일반 `linear-gradient`로 9px 회색 + 3px 투명 타일을 만들고, `background-size: 12px 100%`·`background-repeat: repeat-x`로 반복합니다.
- 색·투명도·막대 비율·라벨·데스크톱 레이아웃과 [모바일 이미지 방식](0004-swing-take-mobile-image.md)은 유지합니다.
- `scripts/web_contract.py`가 Swing/Take 프로필 CSS의 반복 그라디언트를 거부합니다. 전용 캡처가 없는 페이지에는 이 제약을 적용하지 않습니다.
- 화면 검사에는 `#profile-image`가 실제 생성된 상태와 "프로필 이미지 저장" PNG를 포함합니다. CDN 라이브러리가 로드되지 않아 반응형 DOM fallback만 보이는 상태를 모바일 캡처 통과로 판단하지 않습니다.

## 기각한 대안
- 모바일 이미지를 반응형 DOM으로 대체: 사용자가 정한 한 장짜리 프로필 형태와 저장 동작을 바꿉니다.
- html2canvas 교체: 배경 표현만 바꾸면 기존 형태를 유지하면서 고칠 수 있습니다([0005](0005-no-modern-css-color-in-capture.md)).

## 결과
- 4개 구역의 League Avg Swing·Take 막대 8개가 모바일·저장 이미지에 표시됩니다.
- 회귀 검사는 `tests/test_web_contract.py`의 캡처 배경 검사와 [피드백 루프](../harness/feedback.md)의 Swing/Take 이미지 확인 항목입니다.
