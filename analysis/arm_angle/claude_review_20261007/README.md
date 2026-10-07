# EAA-CL1 검토 측 진단: 낮게 나오는 편향과 추가 변인

등록: [gates.md](gates.md)(결과 전 `7afecdf91ecfe893e04dfda70ce3f4e6f566ccdc`), 공용 등록 절 `6c71a73f7f0819a996d545cc01dd16edb8ae5c19`. 탐색 진단이며 후보 선택·운영 변경이 아니다. 오차=예측−관측(°), 투수 내 평균 후 투수 동일가중, paired 투수 bootstrap2,000회. 자료는 MLB 캐시2,295시즌/963명(전부 n_ff≥100)과 재사용 2025년5·7월(FF100·label95, 253행/179명)이다.

## A. 고슬롯·상단의 저평가는 주로 평균 회귀다

| 기준 FF 앵커 OOF | 값 |
|---|---|
| 투수 평균 관측~예측 기울기 | 0.964 [0.934, 0.997] (압축 없음, 상단 예측이 약간 넓음) |
| 관측 5분위 bias | +2.80, +1.18, +0.49, −0.34, −2.27 |
| 예측 5분위 bias | +0.05, −0.43, +0.44, +0.89, +0.92 |
| fold 정직 선형 재보정(b=0.999–1.012) | 전체 MAE 3.888→3.899, 이득 −0.011 [−0.018, −0.006] |

관측 기준으로 보면 높을수록 낮게 나오지만, 예측 기준으로는 상단이 오히려 +0.9° 높다. 등록 해석 규칙의 두 경우(기울기 구간이1 포함·예측분위 ±0.5 안 / 하한>1) 모두에 해당하지 않으며, 압축은 없다. 관측60° 이상의 −4.3°는 전역 재보정·늘이기로 고칠 수 없는 평균 회귀 성분이 크다. 재사용 월 기울기도 0.989 [0.926, 1.057]이다.

SI는 기울기 0.955 [0.898, 1.020]이고 예측5분위 bias가 −1.06, −1.94, −0.56, −1.90, +0.28이다. SI의 저평가는 기울기가 아니라 **집단 수준 오프셋**이다.

## B. 추가 변인16개 단일 추가: 등록 신호 0개

[CL1_variable_screen.csv](CL1_variable_screen.csv). 전체 MAE 이득 최대는 `primary_minus_FF_hb_arm_in` 0.041 [0.010, 0.073], `primary_hb_arm_in` 0.038 [0.008, 0.070]로 0.05 조건 미달, Bonferroni 하한은 0 미만이다. 두 변인은 SI에서 bias −1.04→−0.32/−0.50, 음의오차 이득 0.45 [0.35, 0.55]/0.35 [0.27, 0.44]로 SI 오프셋을 설명하지만, 같은 계열 특성이 이미 과거 R2 full에 있고(SI bias +0.10) R2 실패 판정은 유지된다. 새 발견이 아니라 기존 R2 방향의 재확인이다. 재사용 월에서는 +0.009/+0.017로 구간이 0을 포함한다. 관측60° 이상 MAE 이득은 모든 변인에서 ≤0.11°다.

## 등록 외 기술 통계: KBO 입력의 MLB 범위 이탈

[KBO_FF_input_shift.csv](KBO_FF_input_shift.csv), [KBO_clip_sensitivity.json](KBO_clip_sensitivity.json). KBO 라벨·참고각도는 쓰지 않았다. KBO FF100 195명 중 `ff_movement_size_m` 38.5%가 MLB 99분위 초과, `ff_speed55` 9.7%가 1분위 미만, `ff_flight55_to_plate` 9.2%가 99분위 초과다. 전체 MLB로 고정한 FF 앵커에서 movement size만 MLB 1–99분위로 자르면 바뀐 75명 평균 −1.87°다(외삽이 예측을 **올리는** 방향). speed나 flight 한 축만 자르면 평균 −7.8°/+9.7°로 반대로 크게 흔들려, 두 공선 축의 가장자리에서 2차 다항이 불안정하다. 이 민감도는 정확도·편향 추정이 아니며 KBO 편향의 원인을 식별하지 않는다.

## 재현

```bash
OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2 python analysis/arm_angle/claude_review_20261007/run_cl1.py   # CL1_DONE 2295 963 253 0.0
OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2 python analysis/arm_angle/claude_review_20261007/kbo_input_shift.py
```

상대 연구 폴더의 커밋된 입력과 frozen helper만 사용한다. 앵커 재적합은 기존 OOF를 최대차 0.0으로 재현했다.
