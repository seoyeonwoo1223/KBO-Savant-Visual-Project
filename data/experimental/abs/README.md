# ABS 연구 산출물 (실험)

`python -m visualbaseball.abs_explorer`가 만든다. 방법·한계는 [analysis/abs/README.md](../../../analysis/abs/README.md). production 지표가 아니며 공식 리더보드 입력으로 쓰지 않는다.

| 파일 | 내용 |
|---|---|
| `data_audit.json` | ABS 시즌 `sz` 비율과 규정 비율, 역산 신장의 시즌 내·시즌 간 안정성 |
| `reconstruction.json` | VB 궤적+규정 재구성 판정 vs 공식 판정: 시즌·경계·구종·구장·월별 일치율, 프로빗 편향·σ, 공 반지름 스캔, 2025 규정 하향 효과 |
| `reconstruction_mismatches.csv` | 불일치 테이크 전체. `far_from_boundary=True`(경계 2cm 밖)는 기록 검토 후보 |
| `umpire_model.json` | 2022–2023 심판 모형 검증(경기 단위 5-fold, 시계열, 기준선, calibration), 학습 범위, 시즌별 RE288 진단 |
| `abs_rv_summary.json` | 시즌별 리그 ABS RV와 분해, 신뢰도(홀짝 경기, 연도 간, 기준 연도 민감도, 심판 시대 편차 상관) |
| `abs_rv_{batter,pitcher}_{2024,2025,2026,2024-2026}.csv` | 선수별 ABS RV(원값·리그 대비), 90% 구간, 판정 기대 개수, 가정 오차 시나리오 |
| `tracking_audit.json` | TrackMan vs PTS 무브먼트(관측), 보고 위치 vs 궤적(내부 일관성), 가정 오차 민감도 |
| `naver_crosscheck.csv`, `naver_crosscheck.json` | 재구성 불일치 투구를 네이버 문자중계 판정·PTS 기록과 대조한 결과 (`analysis/abs/naver_crosscheck.py`) |
