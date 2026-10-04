# 0001. `web/`·`exports/`는 출력물이며 입력으로 읽지 않는다

- **상태**: 채택

## 맥락
웹 JSON과 Excel은 사람이 보기 좋게 반올림·필터링한 결과입니다. 이를 다른 metric의 입력으로 쓰면 반올림 오차와 표시용 필터가 계산에 섞이고, 어떤 산출물이 무엇에서 왔는지 추적할 수 없게 됩니다.

## 결정
- metric은 `curated.load_rows()`로 curated partition만 읽습니다. 유일한 외부 workbook 입력은 구장 보정표(`data/park_adjustments/`)입니다.
- Zone Awareness는 Excel/legacy cache fallback도 쓰지 않습니다.
- `web/**`는 어떤 코드의 입력도 아니므로 `daily_update` 트리거에 없습니다. 뷰만 고치면 파이프라인이 돌지 않습니다.

## 기각한 대안
- 웹 JSON을 다른 도구의 입력으로 재사용: 빠르지만 계산 근거가 표시용 데이터에 묶입니다.

## 결과
- 새 metric은 curated에서 시작합니다. 산출물 형식(`publish.py`의 바이트 형식)은 웹 계약이므로 바꾸면 웹 코드도 같이 봅니다.
