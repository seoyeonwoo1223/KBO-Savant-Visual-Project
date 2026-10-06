# eAA 연구 인계 프롬프트 — 2026-10-07 한국시간 기준

아래 내용을 이전 작업의 인계사항으로 삼아, 자료 확인부터 실제 후속 실험까지 이어가라. 처음부터 같은 실험을 반복하거나 이미 실패한 모델을 다시 운영에 넣지 말라. 사용자는 계획만 제시하는 것보다 실행과 검증을 원한다.

## 1. 목표와 사용자 의도

저장소는 `seoyeonwoo1223/KBO-Savant-Visual-Project`다. LG TrackMan과 2025–2026 Visual Baseball(VB) 궤적 자료로 **eAA(estimated Arm Slot)**를 추정하고 Pitch Plot에 표시하는 프로젝트다.

- 실제 팔각도나 실제 Y2Y 변화를 측정하는 지표를 만들려는 것이 아니다. 언제까지나 추정치다.
- 화면에는 투수별 단일 시즌 대표 eAA를 쓰고, 오차 참고 범위는 별도로 표시한다. 범위의 중간값을 점 추정으로 쓰지 않는다.
- Savant의 정면 투영 어깨–공 방향과 지면 수평의 각도에 맞춘다. 수평0°, 수직90°. 3차원 고도각·몸통 상대각·회전축과 혼동하지 않는다.
- 선수별 영상·이미지를 전수 수작업으로 처리하는 모델은 피하고 싶다. 이미지가 없다는 이유로 수치 추정 연구 전체를 불가능하다고 결론 내리지 않는다.
- 현재 후속 실험의 KBO 범위는 **2026만**이다. MLB 학습·검증에서 과거 시즌을 쓰는 것은 가능하다.
- 핵심 문제는 포심 IVB가 낮거나 회전 특성이 전형적이지 않은 투수의 eAA 저평가다. 손주영·문동주·전준표·박준현·안우진을 살펴보되 다른 슬롯 성능도 지켜야 한다.
- 토큰·계산을 절약하고 기존 캐시를 재사용한다. 선수 이름이나 사용자 참고 각도를 맞추는 개별 상수 보정은 하지 않는다.

## 2. 파일 접근과 작업 상태를 먼저 확인

이전 환경의 실제 체크아웃은 `/workspace/KBO-Savant-Visual-Project`, 작업 브랜치는 `work`, HEAD는 `15a9abc87a7c30b71ea40e97f31e996372c033e0`이었다. 이 경로가 새 스레드에도 존재한다고 가정하지 말라.

**새 연구 코드·문서·산출물 상당수는 미추적 파일이며 원격에 커밋되지 않았다.** 원격 master만 받아서는 최신 작업을 모두 얻을 수 없다. 과거 다른 스레드/Claude에서 ZIP이나 프롬프트를 읽지 못했던 원인도 로컬 경로만 전달했기 때문이다. 저장소 연결 여부, 파일 존재, 실제 업로드 첨부를 구분하라.

동반 `eaa-continuation-20261007.zip`을 받았다면 압축 안 `CONTINUE.md`, `MANIFEST.json`, `PACKAGE-README.md`를 먼저 읽고 `verify-package.py`로 SHA를 확인하라. 새 checkout에 무조건 덮어쓰지 말고 별도 디렉터리에서 연구용 snapshot을 사용하거나 필요한 파일만 비교·반영하라. 압축은 필요한 코드·결과·학습/2026 입력 캐시를 담은 경량 묶음이다. 전체 MLB 원본과 2025 일별 CSV, 전체 curated 원자료, 영상은 포함하지 않는다. 일부 충분통계 캐시는 잔차 연구에 필요한 배열만 남긴 동등 입력 사본이며 이 변환을 manifest에 명시했다.

자료가 없다면 우선 확보된 내용으로 상태와 필요한 파일을 특정하라. 파일을 확인하지 않고 이전 실험을 재현했다고 말하거나, 존재하지 않는 ZIP/경로를 원격에 있다고 주장하지 말라.

## 3. 저장소 규칙과 실행 환경

먼저 `AGENTS.md`, `docs/conventions.md`, `docs/harness/feedback.md`, `docs/decisions/README.md`를 읽어라. 환경 설정은 사용 가능한 `cloud-environment-onboarding:setup`과 클라우드 런타임 스킬을 따른다. 기존 checkout·venv를 우선 사용한다. 사용자가 요청하지 않은 worktree는 만들지 않는다.

- Python은 기존 `.venv/bin/python`; 실제 실행 환경은 Python3.12였다.
- `PYTHONPATH=src:analysis/arm_angle OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2`.
- 데이터는 `data/curated/summary.json` → `schema.json` → `curated.load_rows(columns=...)` 순서로 읽는다.
- `partition-index.json` 열기, `data/`·`exports/`·`seasons/` glob, Parquet cat, 생성 데이터 git diff 금지.
- `web/`·`exports/`는 출력물이다. 분석 입력으로 읽지 않는다.
- 얼린 `parser.py`, `state_machine.py`, `validation.py`, `collector.py`, `storage.py`, `curated.py`, `naver.py`, `vb_arm_angle.py`, `arm_angle_calibration.py`, `trackman_arm_angle.py`를 고치지 않는다.
- 2022–2024 curated 유일 사본을 삭제·재작성하지 않는다. 기존 dirty/untracked 연구를 reset·stash·일괄 덮어쓰기하지 않는다.
- 문서·UI·커밋은 한국어. 실제로 실행한 검사와 미실행 검사를 구분한다.
- 새 연구를 운영 반영할 때 모델·metric_state·범위·웹 출력을 일관되게 검증한다. 사용자 요청 없이 병합하지 않는다. PR을 만들면 draft로 만들고 현재 작업에 첨부한다.

## 4. 현재 운영과 지표 정의

현재 배포된 Pitch Plot은 `https://seoyeonwoo1223.github.io/KBO-Savant-Visual-Project/pitch-arsenal/`이며 운영은 **eAA-v3**다. 후속 연구 후보는 아직 배포하지 않았다.

`data/models/estimated_arm_angle_v3.json` SHA256:
`484c6de37dc835f7551e69dbaa8550fe54bf6a086ec3483898140eee907ae84b`

v3는 확인된 신장·투구 손, 55ft 기준 기하/속도/진행 방향/비행 시간, 50ft 기준 무브먼트 방향·크기로 구성한 포심 시즌 입력11개를 쓴다.

```text
height_m
left_hand
z55_over_height
side55_over_height
ff_speed55
ff_armside_vx_over_minus_vy
ff_vz_over_minus_vy
ff_flight55_to_plate
ff_movement_axis_arm_sin
ff_movement_axis_up_cos
ff_movement_size_m
```

특징별 상하10% 절사평균, 2차 Polynomial+StandardScaler+Ridge α100. 학습 가중치는 선수별 시즌 노출 역수×관측 AA≥60° 표본4배이며 평균1로 정규화한다. 포심 부족 시 v1 fallback 등의 품질 상태가 있다. 정의·범위·운영 상세는 `eaa-definition.md`, 결정0013을 읽어라.

범위는 MLB 잔차와 입력 시나리오에 기반한 모델 참고 범위다. KBO 신뢰구간·보장 오차·외삽 상한이라고 부르지 않는다. 2026 구장 및 7월16일 측정 전환 상대 보정은 VB 상대 차이를 줄이는 것이지 SSG TrackMan의 절대 척도에 맞추는 보정이 아니다.

2026 VB에는 독립적인 RPM·실제 익스텐션·팔 길이 관측이 없다. `y0=50/55ft`는 궤적 기준면이지 익스텐션이 아니다. 신장만으로 릴리즈 어깨 위치를 확정하지 않는다. 무브먼트/flight time/RPM으로 역산한 유효회전·힘 방향은 실제 3차원 회전벡터·광학 회전축·효율의 독립 측정과 구별한다. gyro·SSW·계수 가정 때문에 유일한 역산이라고 주장하지 않는다.

## 5. 진행 궤적과 이미 확인한 방향

1. **기초 기하와 신장**: 릴리즈 위치·신장만으로 실제 어깨 위치/몸통 기울기가 결정되지 않음을 확인했다. 영상 일부와 선수 참고값은 비교 자료로만 썼다.
2. **회전축·유효회전·ODE·MLB/KBO 전이**: 실제 MLB 광학 입력과 실제 익스텐션은 개선 가능성을 보였지만 VB에서 예측·역산한 대용치는 같은 효과를 재현하지 못했다. 예측 회전을 독립 입력인 것처럼 쓰지 않는다.
3. **고슬롯 가중·집계·연속성**: 단일 시즌 eAA-v3와 별도 비대칭 범위를 배포했다. 중앙값·경기 가중평균을 일괄 적용하는 것은 뚜렷한 개선이 없었다.
4. **낮은 IVB·다구종 전문가·조건부 혼합**(0014–0015): 일부 선수와 평균 편향은 개선됐지만 범위·별도 평가·소표본 문제가 남았다. 30구의 전문가 활성 경계는 연속 수축으로 완화했다. 양의 보정만 허용하는 접근은 전체 해법이 아니었다.
5. **MAE 선택·구종별 정답·단일 비포심 신뢰도**(0016): 구종별 모델과 새로운 2025년6월 평가를 했지만 운영 교체 근거가 부족했다.
6. **전구종 투구별 공동 회귀·KBO 입력 분포 가중**(0017): 포심 기준 정보가 약해지고 슬롯이 가운데로 압축됐다. 새 기간에서 v3 MAE3.933°보다 공동 회귀4.607°·분포 가중4.622°로 악화했다. 리그 분포 분류 OOF AUC0.945는 입력 분포 차이의 진단이지 특정 센서 원인의 증거가 아니다.
7. **포심 앵커+직교 입력 잔차**(0018, 최신): 기존 포심 회귀를 유지하고 신규 입력의 잔차 성분만 쓰자 평균오차 개선이 나왔다. 그러나 낮은 IVB 평균 저평가 편향은 거의 남아 운영 전환은 보류했다.

기각한 대안을 똑같이 반복하지 말라. 특히 기존 `crossfit_expert_residual`은 각도 전문가들을 meta 다항식으로 조합했고, 최신 직교 잔차는 입력 자체를 포심 공간에서 분리하는 방식이므로 구별해야 한다.

## 6. 학습·검증 분리와 통계 함정

공동 MLB 모집단: 2020–2024년 2,295시즌·963명. 외부5/내부3 GroupKFold, SEED20261006. 고정 학습1,095시즌·518명은 **2023년까지**이며 2024 학습 행이 없다. 보정152명, 고정2024 평가196명은 학습/보정과 투수 단위로 분리했다.

낮은 IVB 평가군: 관측35≤AA<60°, 5° 슬롯 셀×1m/s 구속 셀, 셀 표본≥4, FF IVB≤셀 중앙값. 전체 OOF 모집단에서는812시즌·454명이다. 이것은 평가용 정의이며 KBO에 실제 AA가 있다고 가정하는 분류가 아니다.

기존 선택 목적은 낮은 IVB **투수별 MAE**+0.25×전체 투수별MAE다. 조건은 낮은IVB 절대 편향≥0.30° 개선, 투수별MAE≥0.05° 개선, 전체/35–60°/60°이상/20°미만 악화 한도0.15/0.05/0.25/0.50°다. 외부 bootstrap·고정2024·기간 전이 조건도 별도로 둔다.

- 시즌별 MAE와 투수별 MAE를 섞지 않는다. 여러 시즌을 가진 선수는 선수 안에서 먼저 평균한다.
- bootstrap은 선수 단위로 묶는다. 후보별 사후 진단 구간을 다중 선택과 전이까지 해결한 확증 구간이라고 부르지 않는다.
- **2024와 2025년6월·8월·9월은 이제 이미 확인한 재사용 평가다.** 새 실험에서 새 독립 검증이라고 쓰지 않는다.
- 2025년6월126명/참조 신규19명, 8월147명/신규28명, 9월139명/신규29명, 8–9월 합산289명/신규61명이었다. 합산 코호트는 두 달 합쳐 표본 조건을 적용한 것으로 월별 평균과 다르다.
- 신장/투구 손은 공식 profile을 대조했고 switch handed profile은 실제 투구 손R/L을 쓴다. 결측과0을 구별한다.
- 관측 AA를 입력·feature 생성·검증 투수 변환 학습에 넣지 않는다. 학습 가중치의 고슬롯 기준에 학습 정답을 쓰는 것은 v3의 사전 고정 규칙이며 평가 라벨 누수와 구별한다.

## 7. 최신 직교 잔차 연구의 정확한 상태

입력 공간 X는 포심11개 변수의 2차77항+상수다. 추가 입력 Z는:

- type: 기존 구종 간 기하/운동/무브먼트 차이와 표본 수 연속 수축.
- moment: 입력만의 투구별 basis 시즌 평균90항. 구종 구성, 비선형 평균, 경기·구종 내부 관계를 포함한다.
- combined: 두 묶음.

현재 학습 자료에서만 가중 SVD로 `E=Z−XΓ`를 적합·표준화한다. 잔차SD/표준화 원입력SD가1e−7 이하인 항을 제외한다. E로 학습 내3투수분할 OOF 포심 오차를 Ridge α300에 적합한다. 잔차 절편0, 보정 `강도×5×tanh(raw/5)`, 강도0.5/1. baseline 포함7후보다. 보정 방향을 위쪽으로만 제한하지 않았다.

| 지표 | v3 | 미채택 combined 1 |
|---|---:|---:|
| OOF 전체 투수별 MAE | 3.888° | 3.540° |
| OOF 낮은IVB 투수별 MAE | 3.710° | 3.357° |
| OOF 낮은IVB 편향(추정−관측) | −1.734° | −1.650° |
| OOF 고슬롯 투수별 MAE | 5.766° | 5.157° |
| 고정2024 전체 MAE | 3.691° | 3.353° |
| 고정2024 낮은IVB MAE | 3.580° | 3.599° |
| 재사용2025년8–9월 전체 MAE | 3.933° | 3.628° |
| 동기간 참조 신규61명 MAE | 3.350° | 3.237° |

**모든 외부 폴드와 고정 학습은 baseline을 선택했다.** 새 후보의 낮은IVB 평균 편향 개선이0.30°에 못 미쳤기 때문이다. MAE가 개선됐다는 것과 기존 채택 조건을 통과했다는 것은 다르다. 결과를 보고 조건을 소급 낮추지 않았다.

8–9월 결합 후보 평균 개선0.305°의 선수 bootstrap95% 진단 구간은[0.093°,0.506°]다. 반면8월 신규28명은2.660°→3.000°로 악화됐다. 재사용·소집단 변동성을 함께 기록했다.

입력 직교성 검산 통과. 다만 OOF→전체 재적합 포심 예측 차이 성분이 새 보정에 남을 수 있어 따로 분해했다. 결합 학습 원시 보정RMS2.279°, 차이 성분0.213°; KBO3.239°/0.423°. 진단 계수는 운영 예측에 적용하지 않는다.

학습 원시 보정 평균은 약0이지만 tanh 이후·새 리그에서는0을 보장하지 않는다. 결합 후보의 KBO 최대 표준화좌표 p95는14.75, 학습7.62/고정2024 8.24로 일부 외삽이 더 크다.

실제 비포심29/30/31구 중첩 재표집의 결합 후보 최대 인접 변화0.047°로 경계는 매끄럽다. 그러나 IVB0.25인치당 최대 민감도는0.559°→0.515°로 크게 줄지 않았다. 실제 슬롯/Y2Y 검증으로 부르지 않는다.

신규8개 포함 **전체337개 테스트 통과**. 기존 상수 fixture 경고4개. 독립 검산2,699개 지표값, 실제 학습 OLS/Ridge, KBO195명 계수 재계산, 원본91CSV, 실제 투구 재표집·IVB 시나리오·투영 진단까지 통과했다. 연구 후보는 저장했지만 운영v3·참고범위·웹은 변경하지 않았다.

## 8. 2026 선수별 비교와 참고값

| 선수/ID | 운영v3 | 미채택 combined 1 |
|---|---:|---:|
| 전준표54362 | 40.822° | 43.901° |
| 박준현56318 | 46.276° | 50.195° |
| 안우진68341 | 43.059° | 46.661° |
| 손주영67143 | 50.791° | 50.457° |
| 문동주52701 | 50.765° | 48.975° |
| 곽빈68220 | 57.234° | 57.051° |
| 박영현52060 | 54.717° | 55.201° |
| 조병현51897 | 76.883° | 79.029° |

문동주는 moment 단독52.380°인데 combined에서는 낮아졌다. 특정 선수만 골라 유리한 후보를 적용하지 않는다. 운영 값과 연구 값을 명확히 분리하라.

사용자가 제공한 독립 미검증 참고값: 전준표2026 SSG약47–53°(후에47° 언급), 안우진약56°/>50°(기간 미확인), 조병현SSG약77°와99+%/12시(2024–2026 추정), 박영현53–60°/>60°·효율99%·12시~12시15분·익스텐션약2m, 손주영WBC 무브먼트 자료 기반효율약80%(광학 직접 측정 여부 미확인), 문동주>50° 추정. 이들은 모델 학습 정답이 아니다.

박영현2026 IVB19.8–20.9인치라는 선수 참고값은 약7월28일까지/장비·집계 기간이 불완전하다. LG와SSG 동일 투구 대응값이 없으므로 절대 센서 보정 기준으로 쓰지 않는다.

문동주 서울시리즈2024-03-17/game764836 공개38구의 실제AA는 결측이었다. RPM 추가 진단값 상승은 있었으나 실제 정답 검증 또는2026 개인 보정으로 쓰지 않는다. 손주영WBC45구 같은 표본의 관측AA54.32°/v3약52.8°와 RPM 추가 시악화48.09° 사례도 있다. WBC 효율80%를 모든KBO 포심의 알려진 효율처럼 대입하지 않는다.

## 9. 먼저 읽을 파일과 재현 명령

작업 기준 문서:

```text
analysis/arm_angle/eaa-definition.md
analysis/arm_angle/eaa-2026-orthogonal-residual-plan.md
analysis/arm_angle/eaa-2026-orthogonal-residual-study.md
docs/decisions/0013-estimated-arm-angle-v3.md
docs/decisions/0014-low-ivb-eaa-research.md
docs/decisions/0015-continuous-eaa-research.md
docs/decisions/0016-type-target-eaa-research.md
docs/decisions/0017-pitch-joint-eaa-research.md
docs/decisions/0018-orthogonal-residual-eaa-research.md
```

최신 코드:

```text
analysis/arm_angle/orthogonal_residual_eaa_models.py
analysis/arm_angle/run_eaa_orthogonal_residual_20261006.py
analysis/arm_angle/audit_eaa_orthogonal_residual_20261006.py
analysis/arm_angle/verify_eaa_orthogonal_residual_20261006.py
analysis/arm_angle/pitch_joint_eaa_features.py
analysis/arm_angle/multi_pitch_eaa_features.py
analysis/arm_angle/multi_pitch_eaa_models.py
analysis/arm_angle/continuous_eaa_models.py
tests/test_orthogonal_residual_eaa.py
```

최신 산출물은 `analysis/arm_angle/results/eaa_orthogonal_residual_20261006_*`다. 특히 `model_report.json`, `candidate_models.json`, `completion_audit.json`, `verification.json`, `reused2025_report.json`, `KBO2026_predictions.csv`, `KBO2026_focus.csv`를 읽어라. 이전 단계는 `eaa_pitch_joint_20261006_*`, `eaa_type_targets_20261006_*`, `eaa_continuous_20261006_*`다.

원 환경 캐시:

```text
.cache/arm_angle/low_ivb_20261006/type_targets/mlb.parquet
.cache/arm_angle/low_ivb_20261006/kbo_multi.parquet
.cache/arm_angle/pitch_joint_20261006/mlb_moments.npz
.cache/arm_angle/pitch_joint_20261006/kbo_moments.npz
.cache/arm_angle/pitch_joint_20261006/kbo_pitches.parquet
.cache/arm_angle/orthogonal_residual_20261006/fixed_models.pkl
```

실행 순서:

```bash
export PYTHONPATH=src:analysis/arm_angle OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2
.venv/bin/python analysis/arm_angle/run_eaa_orthogonal_residual_20261006.py
.venv/bin/python analysis/arm_angle/audit_eaa_orthogonal_residual_20261006.py
.venv/bin/python analysis/arm_angle/verify_eaa_orthogonal_residual_20261006.py
.venv/bin/python -m pytest tests/test_orthogonal_residual_eaa.py -q
```

경량 인계 묶음에서는 runner의 학습/선택/2026 추론과 신규 테스트, 경량 smoke를 재현할 수 있다. `audit`의2025 원본 재평가 및 `verify`의원본 투구 재검산은 생략한 원본이 필요하다. 이것을 테스트 실패나 새 환경의 접근 차단으로 혼동하지 말고, 원본 검산의 기존 저장 결과와 경량 재현 결과를 구별하라.

## 10. 다음 작업 요청

다음 순서로 실제 작업해라. 환경이나 첨부 확인만 하고 멈추지 말고 독립적으로 가능한 작업을 진행한다.

1. **인계 정합성 확인**: 최신 파일·운영SHA·캐시 값과 현재 상태를 확인하고, 최신 후보 추정과 운영v3가 다른 사실을 보존한다. warm smoke를 실행한다. 전체 원본이 없는 경우 검증 가능한 범위를 명시한다.
2. **새 평가 목적 사전 선언**: 최신 잔차 구조를 기본 후보로 유지하되 평균오차·낮은IVB 음의오차/꼬리·집단 편향·고슬롯 보호를 분리해서 선택 규칙을 설계한다. 기존0.30° 편향 조건이 개선된 후보를 제외했다는 사실을 진단하되 과거 결과를 소급 채택하지 않는다. 후보 수는 작게 유지한다.
3. **훈련 안에서만 선택**: 투수 분리 nested CV에서 새 선택 규칙을 시험한다. type/moment/combined 및 보정 강도 선택을 후보 정답/신규 기간/KBO 참고값과 분리한다. 필요하다면 OOF→재적합 차이 또는 새 입력 외삽에 대한 연속 수축을 별도 제한된 대조로 선언한다. 결과 후 규칙을 바꾸지 않는다.
4. **미사용 기간 검증**: 기존 출처·평가 기록을 대조해 사용하지 않은 MLB 기간을 사전에 확정하고, 모델·선택을 고정한 뒤 라벨을 열어 평가한다. 2024와2025년6/8/9월을 새 확증이라고 다시 사용하지 않는다. 신규 기간 수집은 TLS/원본 해시·일별행수 상한·공식신장·투구손·같은 코호트 대조를 지킨다.
5. **KBO2026 선수별 진단**: 전준표·박준현·안우진의 상승과 손주영·문동주 개선 부재를 함께 보고한다. 포심과 다른 구종의 차이, 부족한 표본, 입력 외삽, 원시/제한 보정, 새 입력에서 남은IVB 민감도를 비교한다. 원인을 실제 몸통/어깨/효율 문제라고 확정하지 않는다.
6. **범위·운영 판단**: 실제 오차 감소·중간/고슬롯 보호·새 기간 전이가 재현되면 운영 반영 후보와 참고 범위 변경을 검증한다. KBO 자체의 포함률 보장이 없음을 유지한다. 개선이 부족하면 운영v3를 유지하고 어떤 기준에서 실패했는지 구체적으로 남긴다.

사용자는 비영상 **추정**의 실용성을 원한다. 변수 이름을 더 넣거나 선수 기대값에 맞추는 작업보다, 지금 확보한 평균오차 개선을 재현하고 공통 저평가가 남는 이유를 분리하는 것을 우선하라. 결과는 한국어로 짧게 요약하고, 재현 코드·출처·검증 결과를 남겨라.
