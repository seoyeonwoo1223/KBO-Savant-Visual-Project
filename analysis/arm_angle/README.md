# TrackMan 팔각도 추정 연구

2019–2024 LG 제공 TrackMan export에서 KBO 1군 투구를 읽어, Savant와 같은 **어깨–공 선의 정면 각도**를 추정한다. 결과는 실측 Statcast 팔각도가 아니다. MLB 기준값으로 평가한 예측 모델을 KBO로 전이한 연구 산출물이며, 기존 웹의 `movement_zones`나 canonical 데이터는 바꾸지 않는다.

## VB 확장 완료

[최신 eAA 정의와 VB 검증](eaa-definition.md)에 연결 모델, 오차범위 계약, 광주·2025–2026·Y2Y 결과와 단일 eAA의 Pitch Plot 적용을 정리했다. 신장 134명을 추가 확인하여 공식 신장 표는 총 736명이며, **2022–2026 투수·시즌 eAA 1,178개**를 생성했다. 아래 내용은 먼저 수행한 **TrackMan 기반 연구**이며, 이후 고정 eAA 모델의 입력·모델 분리·범위 규칙과 구분해서 읽는다. 최신 eAA 주 결과는 `results/eaa_vb_pitcher_seasons_2022_2026.csv`다.

## TrackMan 연구 결과

- 원본 1,793,078구 중 양 팀이 1군 구단인 **1,189,400구**를 사용했다. 2군/군 팀 혼입 603,678구는 제외했다.
- 기존 `player_bio.parquet`의 신장 1,379개가 모두 비어 있었다. KBO 공식 프로필에서 대상 투수 604명 중 **602명**의 신장을 수집해 `data/tracking/player_heights.csv`에 저장했다. 신장·선수 ID·이름·출처 URL·원문 SHA-256·UTC 수집 시점을 포함한다.
- 신장과 유효한 릴리즈 좌표가 있는 **1,179,515구**에 가정 기반 정면 각도와 어깨 위치 민감도 범위를 계산했다. 신장이 없는 유효 투구 5,255구와 릴리즈 결측/범위 이상 4,630구에는 개인별 각도를 만들지 않았다.
- MLB 2020–2024 공식 관측값 **602명·1,295개 투수–시즌**을 이용해 보정 모델을 평가했다. 한 투수의 모든 시즌을 같은 fold에 넣는 5-fold 교차검증이다.
- KBO **1,674개 투수–시즌**에 보정 추정값이 있다. 이 중 313개는 유효 릴리즈 100구 미만이다. 학습 특성 범위를 벗어난 4개 투수–시즌은 최종 보정값을 비워 두었다.

MLB 투수 분리 평가의 평균 절대오차(MAE):

| 방법 | MAE |
|---|---:|
| 릴리즈 위치 + 신장, MLB 보정 모델 | 4.76° |
| 릴리즈 위치만, 동일한 모델 계열 | 5.19° |
| 어깨 높이 130cm 고정 대용치 | 7.80° |
| 임의의 신장 비율로 어깨 높이·좌우 위치 가정 | 12.32° |

신장을 포함하면 MAE가 0.43° 줄었다. 투수 단위 paired cluster bootstrap 2,000회에서 개선량의 95% 구간은 0.24–0.63°다. 이는 **MLB 평가 표본에서의 비교**이며 KBO 오차 구간이 아니다. 신장은 유용한 개인별 입력이지만, 신장만으로 실제 어깨 위치가 결정되지는 않는다. 임의의 인체 비율은 실제 기준값으로 검증하지 않으면 기존 고정 어깨 방식보다도 나빠질 수 있다.

보정 모델의 MLB MAE는 낮은 슬롯(0–20°) 7.00°, 높은 슬롯(60° 이상) 9.48°였다. 언더핸드 기준값은 13개, 높은 슬롯은 28개 투수–시즌뿐이다. 전체 평균 4.76°를 모든 투구폼에 동일하게 적용하면 안 된다. MLB holdout의 절대오차 90백분위는 9.65°이며 이것도 KBO 신뢰구간은 아니다.

## 각도와 좌표

[Savant 공식 Pitcher Arm Angle 페이지](https://baseballsavant.mlb.com/leaderboard/pitcher-arm-angles)는 릴리즈 순간 투구하는 쪽 어깨에서 공으로 향하는 선과 수평선의 각도를 정의한다. 0°는 수평, 90°는 수직 위쪽이다. 그림은 투수의 몸통 중심을 정규화하므로 화면상 모든 투수가 같은 마운드 위치에 서 있다는 뜻이 아니다. 공식 페이지의 `arm_angle`, `release_ball_x`, `release_ball_z`, `relative_release_ball_x`, `relative_shoulder_x`, `shoulder_z`를 직접 확인했다.

공 좌표를 `(x,z)`, 어깨 좌표를 `(sx,sz)`라고 하면 정면 각도는 다음과 같다.

```text
angle_deg = degrees(atan2(z - sz, abs(x - sx)))
```

어깨보다 낮은 릴리즈는 음수다. 어깨–공이 같은 점인 경우는 정의할 수 없으므로 빈값이다. 단위와 좌표 원점을 먼저 맞춰야 한다.

- TrackMan export의 `rel_height`, `rel_side`, `extension`은 m로 해석한다. 기존 매칭 코드와 숫자 규모가 이 해석을 뒷받침한다. 제조사의 해당 export 원점·마운드 높이 계약을 별도로 확보한 것은 아니므로 좌표 datum 검증은 남아 있다.
- TrackMan `rel_side`는 대체로 우투 양수, 좌투 음수다. Savant의 공개 좌우 좌표는 반대 부호라서 MLB 입력을 TrackMan 방향으로 뒤집고 ft→m로 변환했다. 손과 좌우 부호가 어긋나는 3,757구는 감사 플래그로 남겼으며, 마운드 위치 때문에 가능한 경우가 있어 일괄 삭제하지 않았다.
- TrackMan의 릴리즈 높이는 VB의 `release_z_55`(55ft에서의 궤적 좌표)와 동일한 변수가 아니다. 초기 TrackMan 연구는 실제 릴리즈 변수만 사용한다. 후속 VB 연구는 좌표 연결을 거친 뒤 사용하며, 다른 기준면을 그대로 대입하지 않는다.
- 공식 MLB 신장은 [`www.mlb.com/player/<id>`](https://www.mlb.com/player/453286)의 키 항목에서 읽고 ft/in→cm로 변환했다. 프로필 리다이렉트에서도 요청 선수 ID가 유지되는지 검사한다.

## 익스텐션을 어떻게 사용했는가

익스텐션은 투수판에서 공이 앞으로 나온 거리이며 팔 길이가 아니다. 정면 각도 식에는 전후 좌표가 들어가지 않으므로 익스텐션을 정면 각도에 직접 넣지 않았다. 신장 대비 익스텐션과 선수·구종·날짜별 익스텐션 요약을 진단값으로 보존했다. 범위 [.5, 3]m 밖 또는 결측인 4,700구는 익스텐션 진단에서 제외한다. 익스텐션이 잘못됐다는 이유만으로 유효한 정면 릴리즈 각도를 버리지는 않는다.

MLB 관측 팔각도 표와 대응되는 익스텐션 기준값은 이번 수집에서 확보하지 못했다. 따라서 보정 회귀의 입력은 신장, 신장 대비 릴리즈 높이, 신장 대비 팔 쪽 릴리즈 위치, 투구 손이며, 익스텐션은 입력에 포함하지 않았다. 익스텐션의 모델 기여나 필요성을 검증했다고 주장하지 않는다.

3차원 elevation을 원한다면 공의 익스텐션뿐 아니라 어깨의 전후 위치 `shoulder_extension`도 필요하다. 모듈의 `elevation_3d()`는 이를 명시적인 입력으로 요구한다. 익스텐션을 팔 길이로 바꾸거나 어깨의 전진 거리를 관측한 것처럼 대입하지 않는다.

## 모델과 산출물

기하 시나리오의 기본값은 어깨 높이 `0.72 × 신장`, 팔 쪽 어깨 좌우 위치 `0.10 × 신장`이다. 민감도 검사는 높이 비율 0.65–0.80, 어깨 좌우 이동 ±20cm를 훑는다. 이 값들은 **자유롭게 바꿀 탐색 가정**이다. 인체 표준값·추정된 자세·95% 신뢰구간이 아니다. 시나리오 범위는 어깨 위치 사각형의 정확한 기하 극값이며, 어깨와 공이 수직으로 정렬되는 내부 위치도 포함한다.

MLB 보정 모델은 2차 다항 특성, 표준화, `Ridge(alpha=10)`이다. 하이퍼파라미터를 교차검증 결과에 맞춰 탐색하지 않았다. 투수 ID를 통째로 분리하고, 각 fold에서 표준화와 회귀를 학습했다. 모든 MLB 자료로 재학습한 모델 계수와 특성 범위는 `results/calibration_report.json`에 저장했다.

학습 자료가 시즌 평균이므로 **보정 모델을 투구별 실측 추정기라고 부르지 않는다.** KBO에도 유효 투구의 시즌 평균 릴리즈 좌표를 넣는다. 구종별·날짜별·투구별 표는 기하 시나리오 결과이며 보정 모델의 검증 오차를 그대로 붙일 수 없다.

| 파일 | 내용 |
|---|---|
| `results/kbo_calibrated_pitchers.csv` | 주요 결과: MLB 보정에 따른 KBO 투수·시즌 추정 각도, 표본 수, 범위 초과·소표본 플래그 |
| `results/pitchers.csv` | 투수·시즌별 기하 시나리오와 고정 어깨 대용치 |
| `results/pitcher_pitch_types.csv` | 투수·시즌·구종별 기하 시나리오 결과 |
| `results/calibration_report.json` | MLB 투수 분리 평가, 신장 제외 비교, 계수·표준화·출처 해시 |
| `results/quality_report.json` | 원본별 행 수·결측·선수 연결·단위·가정·출처 해시 |
| `results/mlb_reference.csv` | 공식 관측 팔각도·공/어깨 좌표·신장과 출처 |
| `results/mlb_cross_validation.csv` | fold별 holdout 예측값·실제값·오차 |
| `results/height_identity_gaps.json` | 이름이 맞지 않아 신장을 사용하지 않은 선수 |
| `.cache/arm_angle/pitches.parquet` | 1,189,400구의 연구 계산과 품질 플래그; 큰 파일이므로 Git에는 포함하지 않음 |
| `.cache/arm_angle/pitcher_days.parquet` | 투수·시즌·날짜별 기하 시나리오 요약 |
| `.cache/arm_angle/source_cache/` | 실제로 받아서 파싱한 공식 페이지 원문; 모델/신장 입력 행의 해시와 대조 가능 |
| `arm_angle_analysis.ipynb` | 저장된 근거를 다시 검증하는 실행된 노트북과 그림 |

`mlb_calibrated_season_angle_deg`가 주 추정 결과다. `model_raw_prediction_deg`는 범위 밖 예측도 남기는 감사 컬럼이며 신뢰할 수 있는 최종 각도가 아니다. `outside_training_feature_range=True`인 행에서는 최종값을 비웠다. 이 단순 범위 검사는 모든 다변량 분포 차이를 탐지하지는 못한다.

## 재실행

Python 3.12, 저장소의 `requirements.txt`와 `constraints-za.txt`를 사용한다. 기존 checkout에서 실행한다.

```bash
cd /workspace/KBO-Savant-Visual-Project
source .venv/bin/activate
export PYTHONPATH=src OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2

# 이미 수집한 신장으로 오프라인 계산: 원본 데이터·기존 웹 출력은 쓰지 않는다.
python -m visualbaseball.trackman_arm_angle
python -m visualbaseball.arm_angle_calibration \
  --reference analysis/arm_angle/results/mlb_reference.csv

# 명시적으로 신장이나 공식 관측값을 갱신할 때만 네트워크를 사용한다.
python -m visualbaseball.trackman_arm_angle --collect-heights --fetch-reference
python scripts/collect_mlb_arm_angle_reference.py
python -m visualbaseball.arm_angle_calibration

python -m pytest tests/test_trackman_arm_angle.py tests/test_arm_angle_calibration.py -q
```

검증 노트북은 `analysis/arm_angle/requirements-notebook.txt`의 추가 도구가 필요하다. 저장된 결과만 읽고 출처 해시, fold 분리, 오차, KBO 품질 상태를 다시 확인한다. 전체 웹 빌드나 시즌 데이터 재수집은 하지 않는다.

```bash
python -m pip install -r analysis/arm_angle/requirements-notebook.txt
python analysis/arm_angle/run_notebook.py
```

노트북 실행기는 현재 Python 환경을 커널로 등록하고 Jupyter·폰트 캐시를 `.cache/arm_angle/notebook-runtime/`에 둔다. 클라우드의 읽기 전용 홈 디렉터리를 사용하지 않는다. 실행된 노트북과 확인용 `.cache/arm_angle/notebook.html`을 만든다.

## 남은 검증

TrackMan 원본에는 어깨 좌표·몸통 기울기·팔 길이·영상 기준 팔각도가 없으므로 실제 팔각도를 유일하게 역산할 수 없다. KBO 정확도 검증은 영상 또는 독립적인 pose 관측값을 확보한 뒤에 가능하다. 측정 정의, 카메라 보정, 릴리즈 프레임 선택, 투수 단위 분리부터 정해야 한다. MLB에서 관측한 평균 오차를 KBO의 보장 오차로 표현하지 않는다.

신장이 빠진 선수는 `50205` 박웅, `76430` 김상수다. 현재 KBO 프로필에는 각각 박강민, 김태혁으로 나와 이름 대조에서 거절했다. 개명·선수 대응 여부를 확인하기 전 자동으로 합치지 않았다. 그 밖에 시즌 대응표가 해결하지 못한 투구 76구도 이름·신장 없이 유지한다. 신장을 임의로 대체하지 않는다. 현재 공개 프로필 신장은 2019–2024의 시즌별 실측 신장이 아니라 조회 시점의 성인 신장이라는 한계도 있다.

권장 다음 단계는 2024 기준 언더핸드·사이드암·쓰리쿼터·오버핸드에서 대표 투수를 골라, 동일 프레임 정의로 어깨–공 각도를 확보하는 것이다. 먼저 낮은 슬롯과 높은 슬롯을 검증하면 현재 모델에서 오차가 큰 영역을 점검할 수 있다. Pitch Plot에는 명시적인 추정·범위 미확정 표시와 함께 단일 시즌 eAA를 연결했다. 실제 KBO 각도의 검증과 구종별 eAA 확장은 후속 작업이다.
