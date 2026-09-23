# SBJ 구현 전 비판 메모 (ChatGPT 전달용)

이 문서는 SBJ(Strike Zone Judgment)를 구현하기 전에 **당신(ChatGPT)의 직전 답변과 기존 설계에서 틀렸거나 과했던 부분**을 짚고, 저장소 데이터로 확인된 사실만 남겨 구현 순서를 제시합니다. 칭찬 없이 판정만 적습니다.

| 항목 | 값 |
|---|---|
| 기준 커밋 | `master` `35f1a4bf` (2026-09-23). TrackMan 원본(`data/tracking/`)과 2019–2021 VB backfill 포함 |
| SBJ 코드 | `claude/happy-hopper-g1h339` `ed806226` (**master 미병합**, TrackMan·2019–21 backfill 이전 시점). 인계장: 그 브랜치의 `docs/review/SBJ-APR-handoff-2026.md` |
| 수치 출처 | 이 메모 작성 중 직접 재계산. 핵심 수치는 부록 A 스크립트로 재현됩니다 |
| 작업 규칙 | 각 검증은 **한 번 통과하면 바로 다음 구현 단계로** 넘어갑니다. 같은 검증을 각도만 바꿔 반복하지 마십시오 |

---

## 0. 먼저 읽을 것 — 다섯 줄 요약

1. **ABS 판정면은 상단 = 플레이트 중간면, 하단 = 플레이트 끝면**입니다. 현재 `px/pz`는 앞면(y = 17/12 ft) 값입니다. 그래서 위치 전용 `p_zone`이 낮은 커브의 스트라이크 확률을 0.537로 예측하지만, 실제 관측값은 0.156입니다(2026).
2. **고치되 크게 투자하지 마십시오.** 판정면 보정을 해도 적격 타자 166명의 SJ 순위 상관은 0.996, 점수 변화는 최대 0.82입니다. 선수별 표준오차 중앙값(1.13)보다 작습니다.
3. **VB 위치는 믿어도 되고, VB 무브먼트는 믿으면 안 됩니다.** ABS 경계 위치의 구장 간 차이는 0.8cm 이하입니다. 반면 같은 투수·같은 구종군의 무브먼트는 구장에 따라 HB 18cm, IVB 10cm까지 달라집니다. TrackMan은 같은 비교에서 0.9 / 1.4cm입니다.
4. **TrackMan 파일에는 위치·판정·스윙이 없습니다.** 따라서 SBJ의 입력이 될 수 없고, 검증 기준으로만 쓸 수 있습니다.
5. **정의부터 정해야 합니다.** SBJ 원점수(정확도)에서 리그 기대 정확도를 빼면 정확히 `za_raw`가 됩니다(대수적 항등식). 사용자 설계식 `(S − q)(2p − 1)`은 `za_raw`와 같은 식입니다. 무엇을 SBJ라고 부를지가 첫 결정입니다(3.1절).

---

## 1. 직전 답변에 대한 판정

| 당신의 주장 | 판정 | 근거 |
|---|---|---|
| 3D 궤적은 우선 `pStrike`에 가치가 있다 | **맞음, 확인됨** | 2.2절. 판정면을 바꾸면 구종 간 경계 차이가 3.2cm에서 0.1cm로 줄어듭니다 |
| 구종 이름을 넣기보다 궤적으로 판정면 좌표를 계산하는 편이 정확하다 | **맞음, 확인됨** | 같은 2.2절. 구종 라벨은 판정면 보정 후 잔차 진단용으로만 쓰십시오 |
| 검토문 수치는 재실행하지 않았으니 "보고된 결과"로 취급한다 | **이제 해당 없음** | 재현했습니다. 2025년 하단 경계에서 포심 0.78, 커브 0.05. 현행 `p_zone`은 커브 예측 0.537, 관측 0.156(2026) |
| 경기 단위 OOF로 **전체 Brier·log loss**를 비교해 채택 여부를 정한다 | **반대. 판정 기준이 틀렸습니다** | 경계 투구는 전체의 약 6%뿐이라 전체 지표는 경계에서 먼 투구가 좌우합니다. 실제로 간이 기하 모델은 하단 커브 편향을 0.54→0.21로 고치면서도 테이크 전체 log loss는 0.040→0.073으로 나빠졌습니다. 채택 기준은 **구종별 경계 보정 오차**여야 합니다 |
| 릴리스 좌우·접근각을 `pSwing`에 넣고 OOF 성능으로 채택한다 | **우선순위 낮음** | 먼저 무브먼트를 **빼는** 실험을 하십시오(3.4절). VB 무브먼트는 구장 편향이 커서 넣는 쪽이 오히려 위험합니다 |
| 지각 오차 3–5cm를 근거 없이 공식값으로 고정하지 않는다 | **맞음** | 민감도 분석으로만 쓰십시오 |
| 화면의 궤적 곡선이 ABS 판정 좌표와 같다고 볼 수 없다 | **당시엔 정당했던 유보, 이제 해소됨** | VB 위치는 ABS 판정과 약 1cm 수준으로 일치하고 구장 편향도 없습니다(2.3·2.4절) |
| 외부 사이트(kbo-analytics) 확인 | **무관** | SBJ 입력 판단에 쓰지 마십시오 |

---

## 2. 확정된 사실

### 2.1 측정면
- `px/pz`는 궤적을 y ≈ 1.417 ft(플레이트 앞면)에서 평가한 값입니다. 궤적으로 다시 계산했을 때의 오차는 z 기준 중앙값 0.1cm, p99 0.34cm입니다. 즉 "역산 과정에서 정밀도가 떨어진 값"이 아니라 궤적 피팅 결과 그 자체입니다.
- `trajectory_status`가 `valid`가 아닌 비율은 2019년 3.2%(y0 결측), 2023년 2.0%(해 없음), 2024년 0.4%, 2025–26년 약 0%입니다.

### 2.2 ABS 판정면 (2025 테이크, 경계에서 판정 확률 50%가 되는 지점의 구종 간 퍼짐, cm)

| 평가면 | 상단 경계 퍼짐 | 하단 경계 퍼짐 |
|---|---|---|
| 앞면 (현재 `px/pz`) | 2.0 | 3.2 |
| 중간면 (y = 8.5/12 ft) | **0.6** | 1.7 |
| 끝면 (y = 0) | 1.4 | **0.1** |

- 상단은 중간면에서, 하단은 끝면에서 구종 간 차이가 사라집니다. 원인이 구종별 좌표 오차나 표본 구성이라면 특정 면에서 구종 차이가 이렇게 사라질 이유가 없으므로, **판정면 차이로 설명됩니다.** KBO 규정 원문과는 대조하지 않았고, 이 결론은 데이터에 근거합니다.
- **인간 심판 시대(2023)에는 어느 평가면에서도 구종 간 퍼짐이 2.0–5.5cm로 남습니다.** 기하 문제가 아니라 심판의 지각 문제이므로, 판정면 보정으로는 해결되지 않습니다.

### 2.3 ABS 경계 위치와 선명도 (sz 기준, 판정면 적용)
- 경계 위치: 좌우 ±26.7cm(`x_relative` 약 1.05), 상단 +3.4cm(중간면), 하단 −4.9cm(끝면). **2024·2025·2026년이 ±0.1cm 안에서 같습니다.** `x_relative = ±1`을 ABS 경계로 보면 안 됩니다.
- 전이 폭(logistic scale): 좌우 0.83cm, 상단 0.9–1.2cm, 하단 1.2–1.4cm. VB와 ABS의 차이를 표준편차로 환산하면 약 1.5–2.4cm이고, ABS 자체의 오차도 이 안에 포함됩니다.
- 경계에서 5cm 넘게 떨어졌는데 판정과 모순되는 테이크는 0.30–0.34%입니다(2024–26). 이런 투구는 삭제하지 말고, 작은 오류율 ε(약 0.003)을 섞는 방식으로 처리하는 편이 안전합니다.

### 2.4 VB 위치의 구장 편향 없음 (구장별 경계 위치의 범위)
- 2024년: 좌 0.8, 우 0.5, 상 0.3, 하 0.2cm. 2025년: 0.5 / 0.6 / 0.5 / 0.3cm.

### 2.5 ABS 시대 선택편향
- 2026년 경계 테이크에서 (관측 판정 − `p_zone`)을 보면 스트라이크 카운트별 ±0.005, 구장별 ±0.009입니다.
- ABS는 카운트를 모르므로, 카운트별 잔차는 곧 테이크 표본만으로 학습한 데 따른 선택 효과입니다. 현재 해상도에서는 **무시할 수 있는 수준**입니다. IPW나 DR은 공식 모델에 필요하지 않습니다.

### 2.6 인간 심판 시대 (2019–2023)
- 좌우 경계의 50% 지점(`x_relative`)이 시즌마다 움직입니다. 2019년 약 1.25, 2022년 약 1.12, 2023년 약 1.07입니다.
- 카운트 효과가 큽니다. 경계 테이크의 스트라이크 비율(0스트라이크 / 2스트라이크)이 2019년 0.82 / 0.61, 2023년 0.56 / 0.33입니다. ABS인 2024년은 0.50 / 0.50입니다.
- `sz_top/sz_bottom` 정의가 시대 안에서도 다릅니다. 2019년은 투구마다 변하고(타자 내 중앙값 SD 0.09 ft), 2022년 이후는 타자별 상수입니다. 2020–21년은 확인하지 않았습니다.

### 2.7 VB 대 TrackMan (투구 단위 탐색 매칭, 1군 VB 투구의 67–71%)

| 항목 | VB | TrackMan |
|---|---|---|
| 같은 투수·같은 구종군 기준 HB의 구장 간 범위 | **15–18cm** | 2019년 4.8cm / 2024년 0.9cm |
| 같은 기준 IVB의 구장 간 범위 | **약 10cm** | 2019년 4.1cm / 2024년 1.4cm |
| 무브먼트 스케일 (VB를 TrackMan에 회귀한 기울기) | 0.84–0.94 | 기준 |
| 구속 | 정수 km/h로 반올림, TrackMan보다 0.6–1.6km/h 낮음(시즌마다 다름) | 구장 편향 0.5km/h 이하 |
| 릴리스 높이의 경기 내 잡음 | 2.0–2.1cm | 1.1–1.4cm |

위치는 정확하고 무브먼트는 틀어지는 이유: 플레이트 위치는 카메라가 직접 관측한 구간 안에 있어 값이 잘 고정되지만, 무브먼트는 궤적의 가속도(2차 도함수)라서 카메라 보정 오차가 크게 증폭됩니다.

### 2.8 TrackMan 파일 구조와 커버리지
- **있는 것:** 구속, 회전수, IVB/HB, 익스텐션, 릴리스 높이·좌우, zone_speed, 구종, 카운트, 투타 손
- **없는 것:** `px/pz`, 판정 결과, 스윙 여부, 궤적 계수
- 행의 26–39%가 2군(`MIN_*`) 경기입니다.
- **광주(KIA 홈)·울산·청주·포항 경기는 커버리지 0%입니다.** 결측이 특정 구장·팀에 몰려 있습니다.
- 날짜 형식이 2019–21년은 `MM/DD/YYYY`, 2022년 이후는 ISO입니다.
- 공통 투구 ID가 없어서 `docs/tracking-data.md`가 요구하는 "검증된 투구 매핑"은 아직 없습니다. 위 수치는 날짜·투수·이닝·카운트·아웃·순서로 맞춘 **탐색용 매칭** 결과입니다.

### 2.9 현행 지표의 성질 (2026 ZA 투구 산출물, 적격 166명)
- SJ 원점수 SD는 2.91입니다. 그중 공격성 수준항 `mean(S−q)·mean(2p−1)`의 SD는 0.30입니다(`mean(2p−1)` = −0.015).
- corr(SJ, Swing%) = 0.05이므로 공격성이 새어 들어오는 효과는 작습니다.
- split-half 신뢰도(경기 홀짝 반분, Spearman–Brown 보정): SJ 0.75, 타자 내 중심화 SJ 0.754, Swing% 0.89. **반분 길이는 기록하지 않았으므로** ADR-005 규칙상 다른 지표와 비교하는 용도로 쓰면 안 됩니다.
- 판정면 보정의 영향(간이 6-파라미터 기하 모델, in-sample 적합, 2026년만): 순위 상관 0.9956, |ΔSJ| 중앙값 0.15 / 상위 10% 0.38 / 최대 0.82, 최대 순위 이동 16/166. 판정면 효과만 분리한 값이 아니라 모델 차이 전체가 섞인 **상한값**입니다.

---

## 3. 비판 — 구현 전에 결정하거나 고칠 것

### 3.1 [사용자 결정] SBJ의 정의
- 원점수형 SBJ = `za_raw` + 기대 정확도 E입니다. 여기서 `E = mean(q·p + (1−q)(1−p))`는 **타자가 받은 공 구성**(구별하기 쉬운 공의 비율)과 리그 평균 스윙 정책만으로 정해집니다. 타자의 판단은 들어 있지 않습니다. **SBJ와 `za_raw`의 차이는 전부 E에서 나옵니다.**
- 투수는 타자에 따라 공 배합을 바꿉니다(예: 강타자에게는 존을 피함). 그래서 E에는 타자의 평판이 섞일 수 있습니다.
- 인계장 13.5의 공표 기준 1("SBJ와 `za_raw`의 Spearman < 0.90")은 **기준을 통과할수록 공 구성이 더 섞였다는 뜻이 됩니다.** 기준 3(증분 예측력)을 통과하지 못한 채 기준 1만 통과해서는 별도 공표의 근거가 되지 않습니다.
- **권고:** 순위 지표는 기대를 뺀 형태(`za_raw` 형) 하나로 통일하십시오. 원점수 정확도(%)는 설명용 수치로만 병기합니다. ZA와 SBJ를 두 개의 순위 지표로 동시에 공표하지 마십시오. 최종 결정은 사용자가 합니다.
- 항등식을 고정해 둔 기존 테스트(`test_subtracting_the_league_baseline_would_reproduce_zone_awareness`)는 유지하십시오.

### 3.2 [필수·소규모] ABS `p_zone`을 판정면 좌표로 교체
- 이것은 "위치 전용" 원칙과 충돌하지 않습니다. 구종 라벨을 넣는 것이 아니라 **올바른 면에서의 위치**를 넣는 것입니다.
- 인계장 3.4의 "ABS에서 구종은 인과적 역할이 없다"는 문장은 수정해야 합니다. 앞면 좌표를 조건으로 두면 낙하각(구종)이 판정에 영향을 줍니다.
- 입력: `x`(앞면), `z_mid − sz_top`, `z_back − sz_bottom`. 계산식은 `curated._at_plane()`과 같습니다(부록 B).
- 모델: 기존 HGB에 입력만 교체하거나, 6-파라미터 기하 모델을 씁니다. 거리에 대한 단조 제약을 권합니다.
- `trajectory_status`가 `valid`가 아닌 투구는 삭제하지 말고, 앞면 `px/pz` 모델로 대체 계산한 뒤 플래그를 남기십시오.
- **통과 기준 (1회):** 구종별 경계 50% 지점의 퍼짐 < 1cm, 그리고 구종별 경계 보정 오차 |관측 − 예측| < 0.05. 전체 Brier·log loss는 악화되지만 않으면 됩니다.
- **검증할 예측:** 인계장 6.2의 맥락 모델 우위(테이크 오분류 0.89% 대 1.23%)는 대부분 판정면 효과일 것입니다. 교체 후 한 번만 확인하십시오.
- **확인하지 않은 것:** 좌우(x)의 판정면. 앞면만 썼지만 좌우 전이는 이미 0.83cm로 선명합니다.

### 3.3 인간 심판 시대 (2019–2023)
- 위치 전용 `p`는 카운트 효과(경계에서 0.21–0.23 차이)를 놓칩니다. 규범 존(위치 전용)과 기술 존(카운트·투타 손 포함, 타자가 알 수 있는 심판 성향) 중 무엇을 쓸지 정하십시오. 어느 쪽이든 **시즌별로 따로 적합**해야 합니다(경계가 움직이므로, 2.6절).
- 판정면 보정은 인간 시대에는 효과가 없습니다(2.2절).
- 2019–21년은 SBJ 브랜치 기준 시점 이후에 들어온 시즌이고, `sz` 정의가 2022–23년과 다를 수 있습니다. 한 시대로 묶지 마십시오.
- ABS 시즌과 같은 순위표에 섞지 마십시오. 인계장 13.4의 정책을 따릅니다.

### 3.4 `pSwing`
- **실험 한 번:** 무브먼트(와 구장 변수)를 뺀 `pSwing`으로 SJ를 다시 계산해 순위 상관을 보십시오.
  - **0.99 이상이면** 무브먼트를 빼고 끝냅니다. TrackMan 의존성도 함께 사라집니다.
  - **0.99 미만이면** `data/park_adjustments/`의 무브먼트 보정 뒤에 남는 구장 간 범위를 TrackMan 2019–24로 검증하십시오. 목표는 TrackMan 수준(약 2cm 이하)입니다.
- **구장 변수:** 홈경기가 표본의 절반이라 팀 성향을 흡수합니다. 하지만 무브먼트가 보정되지 않은 동안에는 구장 변수가 측정 오차 보정 역할도 합니다. **무브먼트를 보정하거나 뺀 다음에** 구장 변수를 제거하십시오.
- x는 타자 기준 in/out 방향으로 변환하고, **투수 손**과 투수 손 × 타자 손을 추가하십시오. 현재 ZA 입력에는 타자 손(stance)만 있습니다.
- 표본 제외: 번트 시도, 고의4구·피치아웃, 피치클락 자동 판정. HBP를 어떻게 처리할지도 명시하십시오.

### 3.5 교차적합 (fold)
- 현재 fold는 경기나 날짜 블록 단위라서 **타자는 train과 test 양쪽에 들어갑니다.** 2022년 이후 `sz_top/sz_bottom`은 타자별 상수라 사실상 타자 ID이고, 홈구장 × 타자 손도 타자 지문 역할을 합니다. 그래서 모델이 그 타자의 성향을 학습해 SJ를 0 쪽으로 줄일 수 있습니다.
- **1회 비교:** 타자(또는 공격팀) 단위 fold와 현행 fold로 SJ SD와 순위 상관을 비교하십시오. SD가 뚜렷이 커지면 타자 단위 fold를 채택합니다.

### 3.6 산식·표시
- 공격성 누수는 실측상 작습니다(2.9절). 타자 내 중심화는 비용이 없으므로(신뢰도 동일) 채택해도 되지만, 막아야 할 문제는 아닙니다.
- ABS에서 `|2p − 1|`은 경계 1–2cm 띠를 빼면 거의 1입니다. **"경계공은 가중치가 자동으로 줄어든다"는 설명은 인간 시대에만 맞습니다.** ABS 시즌 설명에 쓰지 마십시오.
- SJ+는 **축소(shrinkage) 후 표준화**하십시오. 신뢰도가 약 0.75이면 관측 분산의 약 25%가 잡음이고, 진행 중인 2026 시즌은 그 비율이 더 큽니다.
- Heart/Shadow 구역 경계(±1)는 ABS 경계(x 약 1.05, 상하는 판정면에 따라 비대칭)와 다릅니다. UI에서 "Shadow = 판정 경계"라고 설명하지 마십시오.

### 3.7 TrackMan 사용 정책
- **검증 기준으로만** 쓰십시오. VB 값을 TrackMan 값으로 대체하면 광주 등 결측 구장에서만 다른 측정 체계가 쓰여 팀 편향이 생기고, 2025년에 출처 전환 문제가 새로 생깁니다.
- **TrackMan만으로 2019–24년 SBJ를 만드는 것은 불가능합니다**(위치·판정·스윙이 없음). VB는 2019–2026 전 시즌이 있으므로 단일 출처로 갑니다.

---

## 4. 구현 순서 (각 단계의 통과 기준은 1회만 확인하고 바로 다음으로)

1. **정의 결정 (사용자):** 3.1. 결정 전까지 공표 필드명은 바꾸지 마십시오.
2. **ABS `p_zone` 판정면 교체 + 테스트:** 3.2의 통과 기준.
3. **`pSwing` 무브먼트 제거 실험:** 3.4의 결과에 따라 결정.
4. **fold 비교 1회:** 3.5.
5. **자격선·신뢰도:** 인계장 13.1 절차 그대로, ABS 시즌만, 길이 병기.
6. **인간 시대 정책:** 3.3과 인계장 13.4. 시즌별 적합, 별도 표시, 통합 순위 금지.
7. **공표:** 축소 후 SJ+, 구간 표시.

## 5. 하지 말 것

- 전체 Brier·log loss로 판정면 보정 채택 여부를 판단하기
- 구종 라벨을 ABS `p_zone`의 기본 입력으로 넣기
- 판정면 보정을 연구 과제로 키우기 (영향이 표준오차 이내)
- TrackMan 값으로 VB 입력을 대체하거나, TrackMan만으로 SBJ 만들기
- 지각 오차 σ를 공식값으로 고정하기
- 인간 시대와 ABS 시대 SBJ를 같은 순위표에 넣기
- 통과한 검증을 각도만 바꿔 반복하기

## 6. 확인하지 않은 것 / 한계

- 좌우(x)의 판정면. 앞면 기준으로만 계산했습니다.
- 판정면 보정의 SJ 영향은 in-sample 간이 모델로, 2026년만 측정했습니다(상한값).
- 무브먼트 구장 편향을 VB 쪽 문제로 본 것은 "같은 투수는 구장이 바뀌어도 무브먼트가 같다"는 가정에 기댄 추론입니다.
- TrackMan–VB 매칭은 탐색용이며, 결과를 저장하지 않았습니다.
- 2020–21년 `sz` 정의는 확인하지 않았습니다.
- KBO ABS 규정 원문과 대조하지 않았습니다.
- SJ 신뢰도 0.75는 반분 길이를 기록하지 않았습니다.

---

## 부록 A. 재현 스크립트

저장소 루트에서 `PYTHONPATH=src python sbj_review_checks.py plane|park|trackman`으로 실행합니다. `plane`은 2.2절, `park`는 2.4절(2024), `trackman`은 2.7절(2024)을 재현합니다. 모두 읽기 전용입니다.

```python
"""SBJ 비판 메모의 핵심 수치 재현 (읽기 전용). 저장소 루트에서:
PYTHONPATH=src python sbj_review_checks.py [plane|park|trackman]"""
import sys
from pathlib import Path
import numpy as np, pandas as pd
from visualbaseball.curated import load_rows

ROOT, CM = Path('.'), 30.48
TRAJ = ['x0', 'y0', 'z0', 'vx0', 'vy0', 'vz0', 'ax', 'ay', 'az']


def at_y(d, y):
    """등가속도 궤적을 y(ft, 플레이트 끝점=0, 앞면=17/12)에서 평가한 x, z(ft)."""
    a, b, c = .5 * d.ay, d.vy0, d.y0 - y
    t = (-b - np.sqrt(b * b - 4 * a * c)) / (2 * a)
    return d.x0 + d.vx0 * t + .5 * d.ax * t * t, d.z0 + d.vz0 * t + .5 * d.az * t * t


def edge(x, y):
    """1차원 로지스틱 적합 → (50% 지점 cm, logistic scale cm). y=1이 경계 안쪽."""
    X, b = np.c_[np.ones_like(x), x], np.zeros(2)
    for _ in range(50):
        p = 1 / (1 + np.exp(-X @ b)); w = p * (1 - p) + 1e-9
        b += np.linalg.solve(X.T @ (X * w[:, None]) + 1e-6 * np.eye(2), X.T @ (y - p))
    return -b[0] / b[1], 1 / abs(b[1])


def takes(season, extra=()):
    d = pd.DataFrame(load_rows(ROOT, 'pitches', season, columns=['px', 'sz_top', 'sz_bottom', 'pitch_call_code', 'pitch_type', 'trajectory_status', *TRAJ, *extra]))
    d = d[d.pitch_call_code.isin(['B', 'T']) & (d.trajectory_status == 'valid')].dropna(subset=['sz_top', 'sz_bottom']).copy()
    d['cs'] = (d.pitch_call_code == 'T').astype(float)
    xf, zf = at_y(d, 17 / 12); _, zm = at_y(d, 8.5 / 12); _, zb = at_y(d, 0)
    d['x_cm'] = xf * CM
    for name, z in (('front', zf), ('mid', zm), ('back', zb)):
        d[f'top_{name}'] = (z - d.sz_top) * CM; d[f'bot_{name}'] = (z - d.sz_bottom) * CM
    return d


def plane(season=2025):
    """구종 간 경계 50% 지점의 퍼짐(cm)이 어느 판정면에서 최소가 되는가."""
    d = takes(season); kinds = d.pitch_type.value_counts().index[:5]
    for name in ('front', 'mid', 'back'):
        for side, col, inside in (('top', f'top_{name}', lambda g: 1 - g.cs), ('bottom', f'bot_{name}', lambda g: g.cs)):
            lo, hi = (-12, 18) if side == 'top' else (-15, 15)
            w = d[(d.x_cm.abs() < 18) & d[col].between(lo, hi)]
            per = {k: round(edge(g[col].values, inside(g).values)[0], 1) for k, g in w[w.pitch_type.isin(kinds)].groupby('pitch_type')}
            print(season, name, side, per, 'spread', round(max(per.values()) - min(per.values()), 1))


def park(season=2024):
    """구장별 ABS 경계 위치(cm). 상단=중간면, 하단=끝면."""
    d = takes(season, ['stadium']); out = {}
    for st, g in d.groupby('stadium'):
        if len(g) < 5000: continue
        mid = (g.top_mid < -10) & (g.bot_back > 10)
        L, R = g[mid & g.x_cm.between(-40, -15)], g[mid & g.x_cm.between(15, 40)]
        T = g[(g.x_cm.abs() < 18) & g.top_mid.between(-12, 18)]; B = g[(g.x_cm.abs() < 18) & g.bot_back.between(-15, 15)]
        out[st] = {'left': -edge(-L.x_cm.values, 1 - L.cs.values)[0], 'right': edge(R.x_cm.values, 1 - R.cs.values)[0],
                   'top': edge(T.top_mid.values, 1 - T.cs.values)[0], 'bottom': edge(B.bot_back.values, B.cs.values)[0]}
    o = pd.DataFrame(out).round(1); print(o.to_string()); print('구장 간 범위(cm)', (o.max(axis=1) - o.min(axis=1)).round(1).to_dict())


def trackman(season=2024):
    """TrackMan 1군 투구를 VB와 상태키+순서로 탐색 매칭하고, 같은 투수·구종군 기준 구장 편향을 비교."""
    t = pd.read_csv(f'data/tracking/raw/season={season}/trackman_history.csv', dtype=str)
    t = t[~t.pitcher_team.str.startswith('MIN_')].rename(columns={'pitcher_trackman_id': 'pitcher_id'})
    t['game_date'] = pd.to_datetime(t.game_date, format='mixed').dt.strftime('%Y-%m-%d')  # 2019-21은 MM/DD/YYYY
    t['half'] = np.where(t.top_bottom.str.lower().str.startswith('t'), 'top', 'bottom')
    for c in ('pitch_no', 'rel_speed', 'induced_vert_break', 'horz_break'): t[c] = pd.to_numeric(t[c])
    v = pd.DataFrame(load_rows(ROOT, 'pitches', season, columns=['game_id', 'game_date', 'inning', 'inning_half', 'balls_before', 'strikes_before', 'outs_before', 'pitcher_id', 'stadium', 'velocity_kmh', 'horizontal_movement_cm', 'vertical_movement_cm']))
    v['half'] = v.inning_half.astype(str).str.lower(); v['game_date'] = v.game_date.astype(str).str[:10]; v['pitcher_id'] = v.pitcher_id.astype(str)
    key = ['game_date', 'pitcher_id', 'inning', 'half', 'balls_before', 'strikes_before', 'outs_before']
    for c in key[2:]:
        if c != 'half': t[c] = pd.to_numeric(t[c]).astype('Int64'); v[c] = pd.to_numeric(v[c]).astype('Int64')
    t = t.sort_values(['trackman_game_id', 'pitch_no']); t['k'] = t.groupby(key).cumcount(); v['k'] = v.groupby(key).cumcount()
    m = t.merge(v, on=key + ['k']); m = m[(m.velocity_kmh - m.rel_speed).abs() < 25]
    print(f'matched {len(m)} = {len(m) / len(v):.3f} of VB, games {m.game_id.nunique()}/{v.game_id.nunique()}')
    m['tm_hb'] = -m.horz_break
    dev = {c: (m[c] - m.groupby(['pitcher_id', 'pitch_type_group'])[c].transform('median')).groupby(m.stadium).median()
           for c in ('horizontal_movement_cm', 'tm_hb', 'vertical_movement_cm', 'induced_vert_break')}
    o = pd.DataFrame(dev).round(1); print(o.T.to_string()); print('구장 간 범위(cm)', (o.max() - o.min()).round(1).to_dict())


if __name__ == '__main__':
    {'plane': plane, 'park': park, 'trackman': trackman}[sys.argv[1] if len(sys.argv) > 1 else 'plane']()
```

실행 확인 결과 (2026-09-23, master `35f1a4bf`):

```
2025 front top ... spread 2.0      2025 front bottom ... spread 3.2
2025 mid   top ... spread 0.6      2025 mid   bottom ... spread 1.7
2025 back  top ... spread 1.4      2025 back  bottom ... spread 0.1
park 2024 구장 간 범위(cm) {'left': 0.8, 'right': 0.5, 'top': 0.3, 'bottom': 0.2}
trackman 2024 matched 149445 = 0.670 of VB, games 636/720
  구장 간 범위(cm) {'horizontal_movement_cm': 18.0, 'tm_hb': 0.9, 'vertical_movement_cm': 9.9, 'induced_vert_break': 1.4}
```

## 부록 B. 판정면 좌표

`curated._at_plane()`과 같은 등가속도 식입니다. y는 ft이고, 플레이트 끝점이 0, 앞면이 17/12입니다.

```
t    = (−vy0 − sqrt(vy0² − 4·(ay/2)·(y0 − y))) / (2·(ay/2))
x(y) = x0 + vx0·t + ax·t²/2
z(y) = z0 + vz0·t + az·t²/2
상단 판정: z(8.5/12) − sz_top      하단 판정: z(0) − sz_bottom      좌우: x(17/12)
```
