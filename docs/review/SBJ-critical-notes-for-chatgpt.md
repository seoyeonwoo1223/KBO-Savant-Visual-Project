# SBJ 구현 전 비판 메모 (ChatGPT 전달용)

이 문서는 SBJ(Strike Zone Judgment)를 구현하기 전에 **당신(ChatGPT)의 직전 답변과 기존 설계에서 틀렸거나 과했던 부분**을 짚고, 저장소 데이터로 확인된 사실만 남겨 구현 순서를 제시합니다. 칭찬 없이 판정만 적습니다.

| 항목 | 값 |
|---|---|
| 기준 커밋 | `master` `35f1a4bf` (2026-09-23). TrackMan 원본(`data/tracking/`)과 2019–2021 VB backfill 포함 |
| SBJ 코드 | `claude/happy-hopper-g1h339` `ed806226` (**master 미병합**, TrackMan·2019–21 backfill 이전 시점). 인계장: 그 브랜치의 `docs/review/SBJ-APR-handoff-2026.md` |
| 수치 출처 | 이 메모 작성 중 직접 재계산. 핵심 수치는 부록 A 스크립트로 재현됩니다 |
| 작업 규칙 | 각 검증은 **한 번 통과하면 바로 다음 구현 단계로** 넘어갑니다. 같은 검증을 각도만 바꿔 반복하지 마십시오 |
| 2차 개정 | ChatGPT 이견 4건(좌우 판정면, 같은 조건 OOF, 무브먼트 ablation, fold)을 실행해 7절에 반영했습니다. 0·3.2·3.4·5·6절은 그 결과로 고쳤습니다 |
| 3차 개정 | 승인된 항목 1·2를 구현하고 2024–2026년 통과 기준을 확인한 결과(7.4절), 미승인 3번(무브먼트 보정) 구상에 대한 분석(8절)을 추가했습니다 |
| 4차 개정 | 외부 리뷰 반영: 배포 경로 정정(CI는 2026년만 재빌드 → 2024·2025년 산출물을 PR에 포함), 선수 변화의 쌍대 표준오차, fallback 모집단, 무브먼트 관련 표현(8.1)을 고쳤습니다 |

---

## 0. 먼저 읽을 것 — 다섯 줄 요약

1. **ABS 판정면은 좌우 = 중간면, 상단 = 중간면·끝면 중 높은 쪽, 하단 = 두 면 중 낮은 쪽**입니다(내려오는 공이면 상단은 중간면, 하단은 끝면이 제한면). 현재 `px/pz`는 앞면(y = 17/12 ft) 값입니다. 그래서 위치 전용 `p_zone`이 낮은 커브의 스트라이크 확률을 0.537로 예측하지만, 실제 관측값은 0.156입니다(2026).
2. **고치되 크게 투자하지 마십시오.** 같은 HGB·같은 날짜 블록 OOF로 비교하면 판정면 입력은 테이크 log loss를 0.0405→0.0277, 경계 구종별 보정 오차를 최대 0.316→0.013으로 줄입니다. 선수 SBJ 순위 상관은 시즌별 0.995–0.996이고, 변화 크기는 점수 자체의 표준오차(중앙값 약 1.1)보다 작습니다. 다만 같은 경기로 묶은 **차이**의 표준오차(약 0.17)로 보면 시즌마다 5–10%의 선수는 변화가 통계적으로 검출되는 체계적 변화입니다(7.4절).
3. **VB 위치는 믿어도 되고, VB 무브먼트는 믿으면 안 됩니다.** ABS 경계 위치의 구장 간 차이는 0.8cm 이하입니다. 반면 같은 투수·같은 구종의 무브먼트는 구장에 따라 HB 18–22cm, IVB 10–15cm까지 달라집니다(VB 전 투구 기준, 매칭 불필요). TrackMan은 0.9 / 1.4cm입니다. **기존 `data/park_adjustments/` 보정은 HB 편향을 거의 줄이지 못하고, 2025년에는 오히려 키웁니다**(7.3절).
4. **TrackMan 파일에는 위치·판정·스윙이 없습니다.** 따라서 SBJ의 입력이 될 수 없고, 검증 기준으로만 쓸 수 있습니다.
5. **정의부터 정해야 합니다.** SBJ 원점수(정확도)에서 리그 기대 정확도를 빼면 정확히 `za_raw`가 됩니다(대수적 항등식). 사용자 설계식 `(S − q)(2p − 1)`은 `za_raw`와 같은 식입니다. 무엇을 SBJ라고 부를지가 첫 결정입니다(3.1절).

---

## 1. 직전 답변에 대한 판정

| 당신의 주장 | 판정 | 근거 |
|---|---|---|
| 3D 궤적은 우선 `pStrike`에 가치가 있다 | **맞음, 확인됨** | 2.2절. 판정면을 바꾸면 구종 간 경계 차이가 3.2cm에서 0.1cm로 줄어듭니다 |
| 구종 이름을 넣기보다 궤적으로 판정면 좌표를 계산하는 편이 정확하다 | **맞음, 확인됨** | 같은 2.2절. 구종 라벨은 판정면 보정 후 잔차 진단용으로만 쓰십시오 |
| 검토문 수치는 재실행하지 않았으니 "보고된 결과"로 취급한다 | **이제 해당 없음** | 재현했습니다. 2025년 하단 경계에서 포심 0.78, 커브 0.05. 현행 `p_zone`은 커브 예측 0.537, 관측 0.156(2026) |
| 경기 단위 OOF로 **전체 Brier·log loss**를 비교해 채택 여부를 정한다 | **주 지표로는 반대, 보호 지표로는 수용 (2차 개정)** | 경계 투구는 전체의 약 6%뿐이라 전체 지표는 경계에서 먼 투구가 좌우합니다. 주 지표는 **구종별 경계 보정 오차**입니다. 다만 1차 메모의 간이 기하 모델은 전체 log loss를 0.040→0.073으로 악화시켜 제 통과 기준에 스스로 미달했다는 ChatGPT의 지적이 맞습니다. 같은 HGB로 다시 비교하면 판정면 입력은 두 지표를 모두 개선합니다(7.2절) |
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
- 경계 위치: 좌우 ±26.7cm(앞면 기준, `x_relative` 약 1.05. 중간면에서는 ±27.1cm로 좌우 대칭, 7.1절), 상단 +3.4cm(중간면), 하단 −4.9cm(끝면). **2024·2025·2026년이 ±0.1cm 안에서 같습니다.** `x_relative = ±1`을 ABS 경계로 보면 안 됩니다.
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
- 판정면 보정의 영향(간이 6-파라미터 기하 모델, in-sample 적합, 2026년만): 순위 상관 0.9956, |ΔSJ| 중앙값 0.15 / 상위 10% 0.38 / 최대 0.82, 최대 순위 이동 16/166. 판정면 효과만 분리한 값이 아니라 모델 차이 전체가 섞인 **상한값**입니다. 같은 HGB로 판정면 효과만 분리한 OOF 재측정은 7.2절에 있고, 결론은 같습니다.

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
- 입력: `x_mid / (10/12 ft)`, `top_gap = max(z_mid, z_back) − sz_top`, `bot_gap = min(z_mid, z_back) − sz_bottom`. 두 면을 모두 검사하는 계약이고, 계산식은 `curated._at_plane()`과 같습니다(부록 B). 원값 `sz_top/sz_bottom`은 넣지 않습니다. 넣어도 성능이 같아서(7.2절) 타자 식별 단서만 늘어납니다.
- 모델: **기존 HGB 설정 그대로 입력만 교체**합니다. 7.2절의 OOF 비교가 이 형태입니다. 앞서 적은 6-파라미터 기하 모델은 전체 log loss를 악화시켰으므로 쓰지 않습니다.
- `trajectory_status`가 `valid`가 아닌 투구는 삭제하지 말고, 모든 면을 앞면 `px/pz`로 대체한 뒤 플래그와 비율을 기록하십시오. 2026년은 0%, 2019년 3.2%, 2023년 2.0%, 2024년 0.4%입니다.
- **통과 기준 (1회, 시즌별):** ① 구종별 경계 보정 오차 |관측 − 예측| 최대 < 0.05, ② 테이크 전체 log loss가 현행보다 나쁘지 않을 것(보호 지표). 2024·2025·2026년 모두 둘 다 통과했습니다(7.2·7.4절).
- 인계장 6.2의 맥락 모델 우위(테이크 오분류 0.89% 대 1.23%)는 판정면으로 전부 설명됩니다. 판정면 HGB의 오분류는 0.69%입니다(표본이 약간 다르므로 참고값). 맥락 모델을 견고성 진단으로 남길 근거도 약해졌습니다.

### 3.3 인간 심판 시대 (2019–2023)
- 위치 전용 `p`는 카운트 효과(경계에서 0.21–0.23 차이)를 놓칩니다. 규범 존(위치 전용)과 기술 존(카운트·투타 손 포함, 타자가 알 수 있는 심판 성향) 중 무엇을 쓸지 정하십시오. 어느 쪽이든 **시즌별로 따로 적합**해야 합니다(경계가 움직이므로, 2.6절).
- 판정면 보정은 인간 시대에는 효과가 없습니다(2.2절).
- 2019–21년은 SBJ 브랜치 기준 시점 이후에 들어온 시즌이고, `sz` 정의가 2022–23년과 다를 수 있습니다. 한 시대로 묶지 마십시오.
- ABS 시즌과 같은 순위표에 섞지 마십시오. 인계장 13.4의 정책을 따릅니다.

### 3.4 `pSwing`
- **ablation 한 번 (투수 손 추가와 함께):** 무브먼트 변형 세 가지 — ① 제외, ② 현행 `adjusted_hb/ivb`, ③ 구장×시즌 오프셋을 VB 내부에서 재추정한 값 — 로 `pSwing`을 적합하고, OOF log loss·calibration, 구장×구종 잔차, 선수 SJ 변화를 함께 보고합니다. 순위 상관 하나로 결정하지 않습니다(ChatGPT 이견 3 수용).
- ②는 7.3절 결과상 HB 편향이 그대로 남으므로 기준 비교군일 뿐입니다. ③을 만든다면 TrackMan 2022–24로 검증하십시오. 목표는 보정 후 구장 간 범위가 TrackMan 수준(약 2cm 이하)입니다.
- **구장 변수:** 홈경기가 표본의 절반이라 팀 성향을 흡수합니다. 하지만 무브먼트가 보정되지 않은 동안에는 구장 변수가 측정 오차 보정 역할도 합니다. **무브먼트를 보정하거나 뺀 다음에** 구장 변수를 제거하십시오.
- x는 타자 기준 in/out 방향으로 변환하고, **투수 손**과 투수 손 × 타자 손을 추가하십시오. 현재 ZA 입력에는 타자 손(stance)만 있습니다.
- 표본 제외: 번트 시도, 고의4구·피치아웃, 피치클락 자동 판정. HBP를 어떻게 처리할지도 명시하십시오.

### 3.5 교차적합 (fold)
- 현재 fold는 경기나 날짜 블록 단위라서 **타자는 train과 test 양쪽에 들어갑니다.** 2022년 이후 `sz_top/sz_bottom`은 타자별 상수라 사실상 타자 ID이고, 홈구장 × 타자 손도 타자 지문 역할을 합니다. 그래서 모델이 그 타자의 성향을 학습해 SJ를 0 쪽으로 줄일 수 있습니다.
- **pStrike:** 원값 `sz` 대신 `top_gap/bot_gap`을 쓰면 물리적 존 높이는 유지하면서 식별 단서를 구조적으로 없앱니다. 남은 확인은 새 타자(타자 단위 hold-out)에 대한 경계 calibration 한 번입니다.
- **pSwing:** 경기 단위와 타자 단위 fold에서 calibration과 선수 잔차 분산을 비교하십시오. **SD가 커졌다는 사실만으로 더 정확해졌다고 판정하지 않습니다**(ChatGPT 이견 4 수용).

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
3. **`pSwing` 무브먼트 ablation + 투수 손 추가:** 3.4. 구장 변수는 무브먼트 처리를 결정한 뒤에 비교합니다.
4. **fold 비교 1회:** 3.5.
5. **자격선·신뢰도:** 인계장 13.1 절차 그대로, ABS 시즌만, 길이 병기.
6. **인간 시대 정책:** 3.3과 인계장 13.4. 시즌별 적합, 별도 표시, 통합 순위 금지.
7. **공표:** 축소 후 SJ+, 구간 표시.

## 5. 하지 말 것

- 전체 Brier·log loss **만으로** 판정면 보정 채택 여부를 판단하기 (주 지표는 경계 구종별 보정 오차, 전체 지표는 보호 지표)
- 무브먼트 컬럼을 `pStrike`에 넣기 (판정면 위치는 궤적에서 직접 계산되고 구장 편향이 없습니다. 무브먼트 컬럼은 구장 편향만 들여옵니다)
- 구종 라벨을 ABS `p_zone`의 기본 입력으로 넣기
- 판정면 보정을 연구 과제로 키우기 (대부분 선수의 변화가 점수 표준오차보다 작음)
- TrackMan 값으로 VB 입력을 대체하거나, TrackMan만으로 SBJ 만들기
- 지각 오차 σ를 공식값으로 고정하기
- 인간 시대와 ABS 시대 SBJ를 같은 순위표에 넣기
- 통과한 검증을 각도만 바꿔 반복하기

## 6. 확인하지 않은 것 / 한계

- KBO 공식 설명(좌우 중간면, 상하 중간면·끝면)은 ChatGPT가 인용한 것이고 제가 원문을 열어 보지는 않았습니다. 데이터는 그 설명과 일치합니다(7.1절).
- 구장 보정 워크북의 HB 오프셋이 왜 효과가 없는지(부호·시점 규약·산출 방식)는 워크북 원 설계를 보지 않아 확정하지 못했습니다.
- 무브먼트 구장 편향을 VB 쪽 문제로 본 것은 "같은 투수는 구장이 바뀌어도 무브먼트가 같다"는 가정에 기댄 추론입니다.
- TrackMan–VB 매칭은 탐색용이며, 결과를 저장하지 않았습니다.
- 2020–21년 `sz` 정의는 확인하지 않았습니다.
- KBO ABS 규정 원문과 대조하지 않았습니다.
- SJ 신뢰도 0.75는 반분 길이를 기록하지 않았습니다.

---

## 7. 2차 검증 — ChatGPT 이견 4건 실행 결과

ChatGPT가 제기한 네 가지 이견을 논쟁 대신 실행으로 판정했습니다. 재현 코드는 부록 C에 있습니다.

### 7.1 좌우 판정면 — ChatGPT가 맞습니다

ABS 테이크에서 좌우 경계의 50% 지점(cm), 구종 간 퍼짐, 전이 폭(logistic scale)입니다.

| 시즌 | 평가면 | 3루 쪽 / 1루 쪽 경계 | 구종 간 퍼짐 (3루 / 1루) | scale |
|---|---|---|---|---|
| 2025 | 앞면 | 26.86 / 26.59 | 0.81 / 0.27 | 0.84 / 0.82 |
| 2025 | **중간면** | **27.05 / 27.09** | **0.29 / 0.13** | **0.77 / 0.79** |
| 2025 | 끝면 | 27.28 / 27.62 | 0.34 / 0.73 | 0.87 / 0.89 |
| 2026 | 앞면 | 26.98 / 26.48 | 0.95 / 0.71 | 0.84 / 0.77 |
| 2026 | **중간면** | **27.11 / 27.08** | **0.31 / 0.22** | **0.79 / 0.77** |
| 2026 | 끝면 | 27.27 / 27.68 | 0.44 / 0.31 | 0.84 / 0.86 |

- 중간면에서만 좌우가 대칭이 되고(차이 0.03–0.04cm), 구종 간 퍼짐과 전이 폭이 가장 작습니다. 타자 손별 차이는 모든 면에서 0.15cm 이하입니다.
- 경계 ±27.1cm는 10in(플레이트 반폭 + 공 반지름)에 약 1.7cm를 더한 값입니다. `x_relative` 기준으로는 약 1.067입니다.

### 7.2 같은 조건 OOF 비교 — 판정면 채택 (2026)

조건: 기존 `plate_decision_v1._classifier()` HGB 설정, 프로덕션과 같은 연속 날짜 3블록, 테이크로 학습해 해당 블록의 모든 투구를 예측했습니다. ZA 2026 투구 201,666행에 조인했고, 궤적 fallback은 0%입니다.

| 모델 | 테이크 OOF log loss | Brier | 오분류 | 경계 구종별 보정 오차 최대 / 가중평균 (하단 · 상단 · 좌우) |
|---|---|---|---|---|
| 프로덕션 `p_zone` | 0.0400 | 0.00989 | 1.25% | 0.318/0.127 · 0.163/0.081 · 0.020/0.005 |
| A 현행 입력 재현 | 0.0405 | 0.01006 | 1.30% | 0.316/0.126 · 0.158/0.081 · 0.022/0.005 |
| **B 판정면 (x_mid, top_gap, bot_gap)** | **0.0277** | **0.00589** | **0.69%** | **0.013/0.009 · 0.017/0.011 · 0.007/0.003** |
| B + 원값 sz | 0.0273 | 0.00591 | 0.70% | 0.014/0.010 · 0.017/0.009 · 0.008/0.003 |
| B, 좌우만 앞면 x | 0.0372 | 0.00879 | 1.09% | 0.013/0.009 · 0.017/0.011 · 0.036/0.011 |

경계 대역은 판정면 좌표로 정했습니다. 하단은 `bot_gap` −8~−2cm, 상단은 `top_gap` 0.5~6.5cm, 좌우는 |x_mid| 23.7~29.7cm이고, 구종별 n ≥ 100입니다.

- **주 지표(경계 보정)와 보호 지표(전체 log loss)를 모두 통과합니다.** 1차 메모의 간이 기하 모델에서 전체 log loss가 나빠진 것은 모델 형태 때문이었고, 판정면 입력 때문이 아니었습니다. ChatGPT의 지적이 맞았습니다.
- 하단 대역 구종별 (관측 / A / B): 커브 0.564 / 0.880 / 0.562, 포심 0.540 / 0.395 / 0.532, 슬라이더 0.539 / 0.634 / 0.526.
- 원값 sz를 추가해도 차이가 없으므로 넣지 않습니다(3.5절).
- 선수 SJ (적격 166명, 표준오차 중앙값 1.13, A 기준):

| 비교 | Spearman | \|ΔSJ\| 중앙값 / p90 / 최대 | 표준오차 초과 | 최대 순위 이동 |
|---|---|---|---|---|
| A 대 프로덕션 (재현 확인) | 0.9997 | 0.028 / 0.094 / 0.211 | 0 | 4 |
| A 대 B 판정면 | 0.9950 | 0.144 / 0.444 / 0.897 | 0 | 15 |
| A 대 B + sz | 0.9953 | 0.146 / 0.428 / 0.906 | 0 | 14 |

### 7.3 VB 무브먼트 구장 편향 — 매칭 없이 VB 전 투구로 재측정

같은 투수·같은 구종의 중앙값과의 차이를 구장별 중앙값으로 집계했습니다. 표는 구장 간 범위(cm)입니다. "보정"은 프로덕션 `_movement_adjust()`로 `data/park_adjustments/`를 적용한 값이고, 적용률은 98.5–99.7%입니다.

| 시즌 | HB 원값 | HB 보정 | IVB 원값 | IVB 보정 |
|---|---|---|---|---|
| 2024 | 18.5 | 15.9 | 10.1 | **1.6** |
| 2025 | 22.1 | **26.3 (악화)** | 15.0 | 9.0 |
| 2026 | 9.6 | 8.9 | 7.0 | 3.4 |

- 편향은 탐색 매칭의 부산물이 아닙니다. 매칭 없이도 같은 크기로 나타나고, TrackMan에는 같은 비교에서 없습니다(2024년 0.9 / 1.4cm).
- HB 편향은 좌·우투수 모두 같은 방향(포수 시점 고정 오프셋)입니다. 예: 2025년 수원은 좌투 +12.2, 우투 +13.8. 2025년 보정은 두 손 모두에서 편향을 키웁니다(수원 우투 13.8 → 16.4). HB 오프셋의 부호나 시점 규약을 점검해야 합니다.
- 경기 내 잡음은 VB와 TrackMan이 비슷합니다(HB·IVB 모두 약 3–3.5cm). **VB 무브먼트의 문제는 투구 단위 잡음이 아니라 구장×시즌 단위 오프셋이므로 보정으로 고칠 수 있습니다.**
- 이 문제는 SBJ만이 아니라 `pitch_arsenal`(웹 Pitch Arsenal 표시값)에도 영향을 줍니다. 보정을 고치면 화면에 보이는 값이 바뀌므로 별도 작업으로 다루고 사용자 확인을 받으십시오.

### 7.4 구현 결과 (항목 1·2 승인분)

- **SBJ 정의:** 새 산식을 만들지 않았습니다. 공식 순위 점수는 기존 `za_raw` 경로 그대로이고, `CONTRACT`에 "official SBJ ranking score = `zone_judgment_pct` − `expected_zone_judgment_pct`"를 명시했습니다. `zone_judgment_pct`(원점수 정확도)는 "descriptive only and never ranked"로 표기했습니다. 항등식은 `test_official_sbj_is_za_raw_not_a_second_formula`로 고정했습니다.
- **ABS `p_zone`:** `zone_decision.judgment_plane_location()`이 `curated._at_plane()`으로 판정면 좌표를 계산합니다. `pzone_fields(season)`은 2024년 이후에만 `PZONE_ABS`를 반환하고, `plate_decision_v1.predict_pzone(..., fields)`의 기본값은 기존 4개 입력 그대로라 2022–23 legacy 경로는 바뀌지 않습니다. `MODEL_VERSION`은 `za7.1-abs-judgment-plane`입니다.
- **통과 기준 (프로덕션 `load_rows` + `predict_pzone`, `score_crossfit`과 같은 3개 날짜 블록, 테이크 기준):**

| 시즌 | 테이크 | fallback | log loss 현행 → 판정면 | 오분류 | 경계 구종별 오차 최대 (하단 · 상단 · 좌우) | 판정 |
|---|---|---|---|---|---|---|
| 2024 | 121,112 | 0 | 0.0401 → **0.0269** | 1.28% → 0.66% | 0.323 → **0.018** · 0.208 → **0.010** · 0.004 → 0.013 | 통과 |
| 2025 | 119,311 | 0 | 0.0406 → **0.0292** | 1.26% → 0.74% | 0.347 → **0.010** · 0.188 → **0.012** · 0.010 → 0.010 | 통과 |
| 2026 | 112,310 | 0 | 0.0406 → **0.0275** | 1.28% → 0.69% | 0.318 → **0.014** · 0.171 → **0.025** · 0.023 → 0.007 | 통과 |

- **선수 SBJ 변화 (같은 `p_swing`에서 `p_zone`만 교체, 적격 300구 이상):**

| 시즌 | 적격 | Spearman | \|ΔSBJ\| 중앙값 / p90 / 최대 | (a) 점수 SE 중앙값, \|Δ\| > 점수 SE | (b) 차이 SE 중앙값, \|z\| > 1.96 | 최대 순위 이동 |
|---|---|---|---|---|---|---|
| 2024 | 155 | 0.9961 | 0.138 / 0.353 / 0.711 | 0.99, 0명 | 0.169, 15명 (10%) | 15 |
| 2025 | 171 | 0.9945 | 0.135 / 0.354 / 1.097 | 1.14, 0명 | 0.178, 8명 (5%) | 19 |
| 2026 | 166 | 0.9951 | 0.151 / 0.425 / 0.731 | 1.12, 0명 | 0.184, 14명 (8%) | 12 |

  - 두 표준오차는 모두 경기 단위 군집 표준오차입니다. (a)는 기존 점수의 표본 불확실성과 비교한 **실무적 크기**이고, (b)는 같은 투구·같은 경기에서 두 모델 점수의 **차이**를 직접 추정한 것입니다.
  - (b) 기준으로 5–10%의 선수는 두 모델 차이가 검출됩니다(무작위라면 약 5%). 즉 판정면 교체는 "통계적으로 무시할 수 있는 변화"가 아니라, **대다수 선수에게는 작고 일부 선수에게는 체계적인 정확도 수정**입니다. 1차 개정까지의 "표준오차 이내" 표현은 (a)만 본 것이라 이 구분이 빠져 있었습니다.

- **실제 산출 경로:** `python -m visualbaseball.zone_decision --seasons 2024 2025 2026`이 정상 종료했습니다(2026년 118초, 2024+2025년 247초). 판정면 입력과 fallback 수는 `data/metrics/zone_awareness/<season>/report.json`의 `source.pzone_input`에, 모델 버전과 계약은 `web/data/zone_awareness/<season>/leaderboard.json`의 `model_version`·`metric_contract`에 기록됩니다. 선수 값은 같은 파일과 `players/*.json`, `exports/zone_decision_players_<season>.csv`로 나갑니다. `leaderboard.json`의 `pzone_input`에도 fallback 수를 남깁니다(4차 개정).
- **배포 경로 (4차 개정에서 정정):** 3차 개정의 "병합 후 `daily_update`가 다시 만든다"는 설명은 **2026년에만 맞습니다.** `daily_update`는 `--season` 없이 CLI를 부르고 기본 시즌은 2026입니다. 그래서 2024·2025년 `web/data/zone_awareness/<season>/`와 `exports/zone_decision_players_<season>.csv`는 새 코드로 다시 빌드해 이 PR에 넣었습니다. 과거 시즌 산출물을 코드와 함께 커밋해 온 기존 관행(`8c42ec00`)과 같은 방식입니다. 2026년 산출물은 매일 master에 커밋되므로 PR에 넣지 않고 병합 후 CI에 맡깁니다. 같은 이유로, legacy 인간 심판 시즌이 CI에서 재빌드된다는 제 이전 우려도 틀렸습니다.
- **2024년 산출물의 기존 불일치:** 2024년을 다시 빌드하면 SBJ뿐 아니라 DV·SA도 바뀝니다. master 코드로 다시 빌드해도 DV·SA가 똑같이 바뀌므로, 원래 커밋돼 있던 2024년 산출물이 현재 코드·데이터와 어긋나 있던 것이고 이번 변경과는 무관합니다. PR 코드와 master 코드의 차이는 `za_raw`·`za_percentile`뿐입니다. 불일치 크기는 DV/100 변화 중앙값 0.013·최대 0.085, 순위 상관 0.9996이고 투구 수는 같습니다. 2025년은 `za_raw`·`za_percentile`만 바뀝니다.
- **구조 불변 확인:** 2024·2025년 선수 수, 선수 필드, 격자 구조는 그대로입니다. 바뀐 것은 값, `model_version`, `metric_contract`의 설명 항목 3개, `pzone_input`입니다. UI는 여전히 "ZA"로 표기합니다. SBJ 명칭으로 화면을 바꾸는 일은 이번 범위가 아닙니다.
- **fallback 모집단:** 2024년 무효 궤적 858개(2025년 83개, 2026년 86개)는 모두 `px/pz`와 존 경계도 결측이라, fallback 단계 전에 적격 투구에서 빠집니다. 따라서 ABS 시즌의 fallback 0건은 구조적 결과이고, fallback 경로는 그런 결측이 없는 무효 궤적에만 쓰입니다.

---

## 8. 무브먼트 보정 구상 평가 (3번 — 미승인, 분석만)

사용자 구상은 "TrackMan 원값을 외부 기준으로 VB 무브먼트를 회귀 보정하고, 가능하면 궤적 정합성도 높인다"입니다. 코드·데이터·화면 값은 바꾸지 않았고, 아래는 읽기 전용 분석입니다. 재현 스크립트는 부록 D에 있습니다. 표시가 없는 수치는 모두 직접 재현한 것이고, 확인하지 않은 주장은 **(미검증)**으로 표시했습니다.

### 8.1 직접 확인한 사실

1. **VB 무브먼트 컬럼은 궤적 가속도로 계산한 값 그 자체입니다.** `horizontal_movement_cm = ½·ax·t²`, `vertical_movement_cm = ½·(az + g)·t²`이고, t는 y0(50 ft)에서 플레이트 앞면까지의 비행시간입니다. 2024·2025년은 상관 1.0000, 잔차 MAD 0.02cm로 일치합니다. 2026년은 기울기 0.923, 잔차 MAD 약 2cm입니다(y0 55 ft 혼재가 원인일 것으로 봅니다 **(미검증)**).
   - 따라서 구장 편향의 **출처**는 궤적 가속도입니다. 구장 간 범위는 ax 3.7–8.6 ft/s², az 2.7–5.8 ft/s²입니다. 그러나 **파생 무브먼트 컬럼만 보정하는 것은 가속도나 3D 궤적을 보정하는 것과 다릅니다.** 그렇게 하면 보정된 무브먼트와 궤적 계수가 서로 맞지 않게 되고, 이것은 `pStrike` 입력을 지키기 위한 의도된 분리입니다(8.2절). (4차 개정에서 표현 정정)
2. **궤적의 양 끝점에는 큰 편향이 없습니다.** 판정면 위치의 구장 편향은 0.8cm 이하입니다(2.4·7.1절). 2024년 매칭 투구에서 릴리스 쪽 구장 간 범위는 VB x@50ft 4.8cm, z@50ft 7.0cm이고, TrackMan은 rel_side 3.1cm, rel_height 5.3cm입니다.
   - 등가속도 모형에서 두 끝점을 고정하면 가속도와 초기 속도 사이에 관측되지 않는 1자유도가 남습니다. 편향은 이 자유도, 즉 곡률과 초기 방향의 배분에 들어 있는 형태입니다.
3. **VB와 TrackMan의 무브먼트 스케일 차이(2024년 0.84–0.85)는 측정 구간 정의로 거의 설명됩니다.** VB는 50 ft부터, TrackMan은 릴리스부터 플레이트까지를 씁니다(TrackMan 공식 정의). 투구별 extension으로 구간 거리비의 제곱 f = ((50 − 17/12) / (60.5 − extension − 17/12))²(중앙값 0.824)를 곱해 TrackMan 값을 VB 구간으로 바꾸면 회귀 기울기가 IVB 0.847 → 1.028, HB 0.842 → 1.022가 됩니다. 잔차 MAD(3.8 / 5.0cm)는 그대로입니다.
   - 한계: 탐색 매칭(2024년)에서 얻은 결과이고, 시간비가 아니라 거리비로 근사했습니다. "스케일은 정의 차이"는 강한 근거가 있지만, 잔차(투구 단위 불일치)는 이것으로 설명되지 않습니다. **이 스케일을 "오류"로 보고 바로잡으면 안 됩니다.**
4. **기존 워크북의 2025년 HB 오프셋은 부호가 반대인 것으로 진단됩니다.** 서로 다른 두 추정 방식에서 같은 결론이 나왔지만, 워크북 작성 과정을 확인하기 전에는 원인(부호 규약 오류)까지 확정한 것은 아닙니다. 같은 투수·같은 구종 기준으로 잰 실측 구장 편향을 워크북 오프셋에 회귀했습니다. 보정이 제대로 되어 있다면 음의 상관이어야 합니다(오프셋 = −편향).

   | 시즌 | HB 기울기 (우투 / 좌투) | HB 상관 | IVB 기울기 | IVB 상관 |
   |---|---|---|---|---|
   | 2023 | −0.21 / −0.43 | −0.25 / −0.47 | −0.48 / −0.55 | −0.81 / −0.82 |
   | 2024 | −0.24 / −0.42 | −0.27 / −0.45 | −0.61 / −0.56 | −0.92 / −0.88 |
   | 2025 | **+2.15 / +1.92** | **+0.90 / +0.85** | −1.85 / −1.36 | −0.94 / −0.93 |
   | 2026 | −0.23 / −0.26 | −0.16 / −0.18 | −1.01 / −0.94 | −0.93 / −0.83 |

   - 2025년 HB는 강한 양의 상관입니다. 오프셋이 "보정값"이 아니라 "편향값"으로 저장된 것입니다.
   - 다른 해의 HB 오프셋은 편향과 상관이 약해서 편향을 거의 설명하지 못합니다.
   - IVB는 방향은 맞지만 2025년은 크기가 부족합니다.
   - 주의: 위 표의 편향 추정(투수 중앙값을 빼는 방식)은 홈 투수의 중앙값에 홈구장이 섞여 크기가 줄어듭니다. 기울기의 **크기**가 아니라 부호와 상관만 해석하십시오.
   - **2원 고정효과 재추정 (4차 개정):** 투수×구종 효과와 구장×구종 효과를 동시에 추정하는 방식(교대 평균 제거)으로 다시 쟀습니다. 구장 효과 범위는 HB 22–31cm(2023–25) / 12cm(2026), IVB 11–34cm로, 중앙값 방식보다 큽니다(위 주의와 일치). 워크북 오프셋과의 상관은 HB 2023 −0.23, 2024 −0.25, **2025 +0.91**, 2026 −0.16이고, IVB는 −0.62, −0.92(기울기 −0.97), −0.95, −0.95입니다. 2025년 HB의 양의 상관과 2024년 IVB의 정상 보정이 두 방식에서 모두 재현됩니다.
5. **공통 투구 ID 프로토타입 (2019·2024년)**
   - **경기 매핑:** 같은 날짜에서 투수 집합 Jaccard ≥ 0.6이고 2위가 0.3 미만인 경우만 매핑했습니다. TrackMan 1군 686–699경기 중 604–605경기가 매핑됐고, 한 VB 경기에 두 TrackMan 경기가 붙은 경우는 0건입니다.
   - **투구 키:** (경기, 이닝, 초/말, 반이닝 안 타석 순서, 타석 안 투구 번호). 매핑된 경기 안 VB 투구의 99.9%가 키로 맞습니다.
   - **검증:** 타자 ID 일치 90–92%, 투수 ID 일치 79–84%, 카운트·아웃 일치 98.7%입니다. 셋 다 일치하는 투구는 VB 전체 투구의 59–64%입니다.
   - **투수 불일치의 원인 (2024):** 불일치 행에 나오는 TrackMan 투수 ID는 73개(예: 658792)이고, 불일치 행의 99.6%에서 그 ID가 VB ID 체계에 아예 없습니다. 73개 중 85%는 특정 VB ID 하나와 일관되게 대응하므로 **선수 ID 대응표(crosswalk)가 필요합니다.** `docs/tracking-data.md`의 "같은 시즌 문자열 동등 조인"은 이 선수들을 조용히 빼 버립니다. 이들이 외국인 투수라면 **(미검증)** 선발 이닝의 큰 몫이 빠지는 선택편향입니다.
   - 검증 통과 투구와 실패 투구의 구속 차 분포가 같습니다(|차| > 3km/h 비율 9.5% 대 11.3%). 실패는 대부분 ID 문제이지 정렬 오류가 아닙니다.

### 8.2 세 목표는 같은 "무브먼트 보정"이 아닙니다

| 목표 | 필요한 데이터 | 검증 방법 | 공통 투구 ID | 판정면 입력(`pStrike`)에 미치는 영향 |
|---|---|---|---|---|
| 구장×시즌 체계적 오프셋 | VB만으로 추정 가능(투수×구종 효과 + 구장×시즌 효과의 2원 고정효과). TrackMan은 투수·시즌·구종군·구장 집계 수준의 외부 검증 | 보정 후 구장 간 범위, TrackMan hold-out 차이 | 필요 없음(집계 수준). 있으면 검증이 쉬워짐 | 없음. 새 파생 컬럼에만 적용 |
| 투구별 이상값 | 검증된 투구 매핑 + 두 시스템의 잡음 모형 | TrackMan도 경기 내 잡음이 VB와 비슷해서(3–3.5cm), "TrackMan과 다르다"는 VB 오류의 증거가 아닙니다. 같은 투수·경기 안의 강건 z점수로 **탐지만** 하고 값은 바꾸지 않습니다 | 필요 | 없음(플래그만) |
| 궤적 재피팅 | 원 카메라 관측이 없습니다. 가능한 것은 8.1-2의 1자유도를 외부 목표(정의를 변환한 TrackMan 무브먼트)로 정하는 **제약 재매개화**뿐입니다 | 독립 검증이 불가능합니다. TrackMan 목표에 맞춰 만든 것이라 TrackMan과의 일치는 순환 논리입니다 | 필요 | 릴리스 위치와 판정면 위치(중간면 x, 중간·끝면 z)를 제약으로 고정하지 않으면 이동합니다. 예: 앞면을 고정하고 ax를 4 ft/s² 바꾸면 끝면 x가 약 0.3cm 움직입니다(계산값) |

결론: 셋은 서로 다른 작업입니다. 오프셋은 **파생 컬럼 보정**, 이상값은 **데이터 품질 플래그**, 재피팅은 **`pStrike` 입력을 건드릴 수 있는 모델 변경**입니다. 같은 이름으로 묶어 한 번에 하지 마십시오.

### 8.3 매칭 오류·커버리지 공백·분포 차이 다루기

- **투구 매핑:** 타자·투수(대응표 적용 후)·카운트·아웃이 모두 일치하고 구속 차가 허용 범위 안인 것만 "검증된 매핑"으로 인정합니다. 나머지는 쓰지 않습니다. 규칙과 버전을 파일로 남기고 입력 해시로 고정하십시오.
- **오프셋 추정:** VB 내부 데이터로, 광주를 포함한 모든 구장에 대해 추정합니다. TrackMan은 커버된 구장에서만 검증에 씁니다. **TrackMan 결측 구장(광주·울산·청주·포항)에는 TrackMan 기반 회귀 결과를 적용하지 않습니다.** VB 내부 추정치만 쓰고 "TrackMan 미검증" 플래그를 붙입니다.
- **2025–26년:** TrackMan이 없습니다. 2022–24년에 검증된 **방법**만 가져오고, TrackMan 기반 **계수**는 가져오지 않습니다. 구장 편향은 시즌마다 다릅니다(HB 범위: 2025년 22cm, 2026년 9.6cm).
- **분포 차이:**
  - 구종 라벨 체계가 달라서 구종 비교는 공통 구종군(fastball / breaking / offspeed)으로만 합니다.
  - 현재 HB 편향은 좌·우투수 모두 같은 방향(포수 시점 기준 이동)이므로 기준선 모형에 손 상호작용을 넣지 않습니다.
  - 대응표 없이 조인하면 특정 선수군이 빠지므로, 검증 표본의 구성(투수 수, 이닝)을 함께 보고하십시오.

### 8.4 모형 복잡도

- **기준선:** VB 무브먼트 ~ 투수×구종(×시즌) 효과 + 구장×시즌 효과. HB·IVB를 따로 두고 포수 시점으로 적합합니다. "단순 오프셋"이지만 추정은 **2원 고정효과**로 해야 합니다. 중앙값을 빼는 방식은 효과 크기를 줄입니다.
- **확장 조건:** 교차검증 잔차로 판단하고, 문턱은 사전에 고정합니다.
  - (a) 구장×시즌 효과를 뺀 잔차에서 구장×구종군 상호작용이 TrackMan 검증 기준으로 2cm 이상일 때
  - (b) 구장×투수 손 상호작용이 2cm 이상일 때 (현재 증거로는 불필요)
  - (c) 구장 안에서 월별 추세(카메라 재보정 가능성)가 2cm 이상일 때
  - 구속 항은 구장 안에서 잔차와 구속의 상관이 뚜렷할 때만 추가합니다.
- **처음부터 여러 갈래 모형을 만들 때의 위험:**
  - 셀당 표본이 작아 과적합됩니다.
  - 투수 효과와 구장 효과가 겹칩니다(홈 투수는 투구의 절반을 홈구장에서 던짐). 2원 고정효과는 원정 경기 덕분에 둘을 구분할 수 있지만, 상호작용 셀에서는 구분력이 급감합니다. 그 결과 특정 투수의 실제 특이 구종이 "구장 편향"으로 흡수되어 지워지는 **과잉 보정**이 생깁니다.

### 8.5 성공 판정 지표 (서로 섞지 말 것)

1. **구장 간 편향:** 보정 후 구장×시즌 효과의 범위 ≤ 2cm. TrackMan 2024년 수준(0.9 / 1.4cm)을 참고합니다.
2. **외부 오차:** 경기 단위와 투수 단위 hold-out에서, 정의를 변환한 VB와 TrackMan 차이의 구장별 중앙값 |차| ≤ 1cm.
3. **투구별 변화 분포:** 보정량은 구장×시즌 상수여야 하므로 구장마다 한 값(또는 좁은 분포)이어야 합니다. |보정량| > 10cm 비율을 보고하고, 투수 안 구종 순위가 보존되는지(Spearman ≈ 1) 확인합니다.
4. **물리 정합성:** 보정은 파생 컬럼에만 적용하고 ax/az는 바꾸지 않습니다. **판정면 입력(`x_mid_relative`, `top_gap_cm`, `bottom_gap_cm`)이 보정 전후로 완전히 같다는 것을 테스트로 고정**하십시오.
5. **`pSwing` 성능 (4번 승인 후):** OOF log loss·calibration, 구장×구종 잔차.
6. **선수 SBJ 안정성:** 순위 상관, 그리고 7.4절의 두 기준 — 점수 표준오차 대비 크기와, 같은 경기로 묶은 차이의 표준오차 대비 검출 여부.
7. **Pitch Arsenal 표시값 변화:** 투수별 구종 평균 HB/IVB 변화의 분포. 화면이 바뀌는 일이므로 별도 승인 대상입니다.

### 8.6 결론

- **지금 권할 최소안 (승인 시):**
  1. **선수 ID 대응표와 검증된 공통 투구 매핑**을 데이터 계약으로 만듭니다. "공통 투구 ID를 먼저 만들자"는 사용자 의견을 받아들이되, 목적은 보정 입력이 아니라 **검증 인프라**입니다.
  2. VB 내부 2원 고정효과로 구장×시즌 HB/IVB 오프셋을 다시 추정하고, TrackMan 2022–24(가능하면 2019–21도)로 집계 수준에서 검증합니다. 결과는 새 파생 컬럼으로만 두고, 원 컬럼·궤적 계수·기존 워크북·화면 값은 그대로 둡니다.
  3. 2025년 HB 워크북의 부호 반대는 기록만 합니다. 워크북을 교체하면 화면이 바뀌므로 승인이 필요합니다.
- **추가 증거가 있어야 할 확장안:** 구장×구종군·손·월 상호작용, 정의 변환(TrackMan 구간 ↔ VB 구간)에 기반한 스케일 보정, 투구별 이상값 플래그.
- **하지 말아야 할 일:**
  - TrackMan 값으로 VB 값을 대체하기
  - 궤적 계수(ax·az 등) 수정. `pStrike` 입력을 흔들 수 있고 독립 검증이 불가능합니다
  - TrackMan 커버리지 밖(광주 등 구장, 2025–26 시즌)에 TrackMan 회귀 계수 적용
  - 정의 차이인 스케일(약 0.84)을 오류로 보고 "보정"하기
  - 처음부터 여러 갈래 모형 적합
  - 검증되지 않은 매칭 결과 사용

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

## 부록 C. 2차 검증 재현 스크립트

`oof_plane.py`는 7.1·7.2절을 재현합니다. 저장소 루트에서 `PYTHONPATH=src OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2 python oof_plane.py`로 실행하며, `scikit-learn==1.9.0`(`constraints-za.txt`) 기준입니다. `move_park.py`는 7.3절을 재현하고 `openpyxl`이 필요합니다. 둘 다 읽기 전용입니다.

```python
"""ChatGPT 이견 1·2·4 검증: 좌우 판정면, 같은 HGB·같은 3개 날짜 블록 OOF 비교, sz raw 포함 여부."""
import sys, pathlib; sys.path.insert(0, 'src')
import numpy as np, pandas as pd
from scipy.stats import spearmanr
from visualbaseball.curated import load_rows
from visualbaseball.plate_decision_v1 import _classifier
CM = 30.48
def at_y(d, y):
    a, b, c = .5 * d.ay, d.vy0, d.y0 - y
    t = (-b - np.sqrt(b * b - 4 * a * c)) / (2 * a)
    return d.x0 + d.vx0 * t + .5 * d.ax * t * t, d.z0 + d.vz0 * t + .5 * d.az * t * t
def edge(x, y):
    X, b = np.c_[np.ones_like(x), x], np.zeros(2)
    for _ in range(50):
        p = 1 / (1 + np.exp(-X @ b)); w = p * (1 - p) + 1e-9
        b += np.linalg.solve(X.T @ (X * w[:, None]) + 1e-6 * np.eye(2), X.T @ (y - p))
    return -b[0] / b[1], 1 / abs(b[1])

TRAJ = ['x0','y0','z0','vx0','vy0','vz0','ax','ay','az']
# ---- 1. 좌우 판정면 (2025, 2026) -------------------------------------------------
for yr in (2025, 2026):
    d = pd.DataFrame(load_rows(pathlib.Path('.'), 'pitches', yr, columns=['px','sz_top','sz_bottom','pitch_call_code','pitch_type','trajectory_status','batter_stance',*TRAJ]))
    d = d[d.pitch_call_code.isin(['B','T']) & (d.trajectory_status=='valid')].dropna(subset=['sz_top']).copy()
    d['cs'] = (d.pitch_call_code=='T').astype(float)
    _, zm = at_y(d, 8.5/12); _, zb = at_y(d, 0)
    mid = ((np.maximum(zm, zb) - d.sz_top)*CM < -10) & ((np.minimum(zm, zb) - d.sz_bottom)*CM > 10)
    kinds = d.pitch_type.value_counts().index[:5]
    for name, y in (('front', 17/12), ('mid', 8.5/12), ('back', 0.0)):
        x, _ = at_y(d, y); d['xc'] = x*CM
        for side, sel, sgn in (('left(3B)', d.xc.between(-40, -15), -1), ('right(1B)', d.xc.between(15, 40), 1)):
            w = d[mid & sel]; e, s = edge(sgn*w.xc.values, 1-w.cs.values)
            per = {k[:5]: round(edge(sgn*g.xc.values, 1-g.cs.values)[0], 2) for k, g in w[w.pitch_type.isin(kinds)].groupby('pitch_type') if len(g) > 300}
            per_hand = {h: round(edge(sgn*g.xc.values, 1-g.cs.values)[0], 2) for h, g in w.groupby('batter_stance') if len(g) > 300}
            print(f'{yr} x@{name:5s} {side:9s} edge {e:.2f} scale {s:.3f} | type spread {max(per.values())-min(per.values()):.2f} {per} | stance {per_hand}')

# ---- 2. 같은 HGB, 같은 3개 날짜 블록 OOF (2026) -----------------------------------
yr = 2026
C = ['game_id','batter_id','balls_before','strikes_before','outs_before','px','pz','sz_top','sz_bottom','pitch_call_code','pitch_type','trajectory_status',*TRAJ]
v = pd.DataFrame(load_rows(pathlib.Path('.'), 'pitches', yr, columns=C))
ok = v.trajectory_status == 'valid'
xf, zf = at_y(v, 17/12); xm, zm = at_y(v, 8.5/12); _, zb = at_y(v, 0)
# fallback: 궤적 무효 투구는 앞면 px/pz로 모든 면을 대체
xm = np.where(ok, xm, v.px); xf = np.where(ok, xf, v.px); zm = np.where(ok, zm, v.pz); zb = np.where(ok, zb, v.pz)
v['x_mid_rel'] = xm/(10/12); v['x_front_rel'] = xf/(10/12)
v['top_gap'] = (np.maximum(zm, zb) - v.sz_top)*CM; v['bot_gap'] = (np.minimum(zm, zb) - v.sz_bottom)*CM
v['traj_fallback'] = ~ok
za = pd.read_parquet(f'data/metrics/zone_awareness/{yr}/pitches.parquet', columns=['game_id','batter_id','balls_before','strikes_before','outs_before','x_relative','z_relative','swing','p_swing','p_zone','pitch_type'])
v['xk'] = (v.px/(10/12)).round(4); za['xk'] = za.x_relative.round(4)
key = ['game_id','batter_id','balls_before','strikes_before','outs_before','xk']
m = za.drop_duplicates(key, keep=False).merge(v.drop_duplicates(key, keep=False).drop(columns=['pitch_type']), on=key, how='inner')
print(f'\n{yr} joined {len(m)}/{len(za)}; trajectory fallback {m.traj_fallback.mean():.4%}')
m['cs'] = (m.pitch_call_code=='T').astype(int)
FEATS = {'A current (x_rel,z_rel,sz_top,sz_bot)': ['x_relative','z_relative','sz_top','sz_bottom'],
         'B plane (x_mid, top_gap, bot_gap)': ['x_mid_rel','top_gap','bot_gap'],
         'B+sz (plane + sz_top,sz_bot)': ['x_mid_rel','top_gap','bot_gap','sz_top','sz_bottom'],
         'Bf plane but x_front': ['x_front_rel','top_gap','bot_gap']}
dates = np.array(sorted(m.game_id.str[:8].unique())); blocks = np.array_split(dates, 3)
for name, cols in FEATS.items():
    p = np.full(len(m), np.nan)
    for blk in blocks:
        test = m.game_id.str[:8].isin(blk).values; train = ~test & (m.swing.values == 0)
        clf = _classifier().fit(m.loc[train, cols].values, m.loc[train, 'cs'].values)
        p[test] = clf.predict_proba(m.loc[test, cols].values)[:, 1]
    m[name] = np.clip(p, 1e-6, 1-1e-6)
t = m[m.swing == 0]
def ll(p, y): return -np.mean(y*np.log(p)+(1-y)*np.log(1-p))
xa = t.x_mid_rel.abs()*10*2.54
bands = {'bottom': (xa < 18) & t.bot_gap.between(-8, -2), 'top': (xa < 18) & t.top_gap.between(0.5, 6.5),
         'side': (t.top_gap < -10) & (t.bot_gap > 10) & xa.between(23.7, 29.7)}
kinds = ['4-Seam Fastball','Slider','Curveball','Changeup','Forkball','2-Seam Fastball']
print('model | take OOF logloss | Brier | miscls | edge calib: max|obs-pred| by type (bottom/top/side) | weighted mean |obs-pred|')
for name in ['production p_zone'] + list(FEATS):
    col = 'p_zone' if name.startswith('production') else name
    out = []
    for b, sel in bands.items():
        g = t[sel & t.pitch_type.isin(kinds)].groupby('pitch_type').apply(lambda s: pd.Series({'n': len(s), 'err': abs(s.cs.mean()-s[col].mean())}))
        g = g[g.n >= 100]; out.append(f"{b} {g.err.max():.3f}/{(g.err*g.n).sum()/g.n.sum():.3f}")
    print(f'{name:40s} {ll(t[col].values, t.cs.values):.4f} {np.mean((t[col]-t.cs)**2):.5f} {np.mean((t[col]>.5)!=t.cs):.4%} | ' + ' | '.join(out))
# 하단 경계 구종별 상세
sel = bands['bottom'] & t.pitch_type.isin(kinds)
print('\nbottom band obs vs pred:\n', t[sel].groupby('pitch_type').apply(lambda s: pd.Series({'n': len(s), 'obs': s.cs.mean(), 'A': s[list(FEATS)[0]].mean(), 'B': s[list(FEATS)[1]].mean()})).round(3).to_string())
# ---- 선수 SJ ---------------------------------------------------------------------------
def sj(col): return m.assign(j=(m.swing-m.p_swing)*(2*m[col]-1)).groupby('batter_id').j.agg(['size','mean'])
base = sj(list(FEATS)[0]); q = base[base['size'] >= 300].index
se = m[m.batter_id.isin(q)].assign(j=lambda x: (x.swing-x.p_swing)*(2*x[list(FEATS)[0]]-1)).groupby('batter_id').j.agg(lambda s: 100*s.std()/np.sqrt(len(s)))
print(f'\nqualified {len(q)}, median SE {se.median():.2f}')
for other in ['production p_zone'] + list(FEATS)[1:]:
    col = 'p_zone' if other.startswith('production') else other
    a, b = 100*base.loc[q, 'mean'], 100*sj(col).loc[q, 'mean']; dlt = (b-a).abs()
    rk = (a.rank(ascending=False)-b.rank(ascending=False)).abs()
    print(f'A vs {other:34s} Spearman {spearmanr(a, b)[0]:.4f} |dSJ| med {dlt.median():.3f} p90 {dlt.quantile(.9):.3f} max {dlt.max():.3f} (>SE: {(dlt > se.loc[q]).sum()}) max rank shift {rk.max():.0f}')
```

```python
"""VB 무브먼트 구장 편향: 매칭 없이 VB 전 투구로, 원값 vs 기존 park adjustment 적용값."""
import sys, pathlib; sys.path.insert(0, 'src')
import numpy as np, pandas as pd
from visualbaseball.curated import load_rows
from visualbaseball.plate_decision_v1 import _movement_adjust
for yr in (2024, 2025, 2026):
    rows = load_rows(pathlib.Path('.'), 'pitches', yr, columns=['pitch_id','pitch_type_code','pitch_type_kr','pitcher_id','pitch_type','stadium','horizontal_movement_cm','vertical_movement_cm','game_id'])
    info = _movement_adjust(rows, pathlib.Path('.'), yr)
    d = pd.DataFrame(rows)
    out = {}
    for c in ('horizontal_movement_cm', 'adjusted_hb_cm', 'vertical_movement_cm', 'adjusted_ivb_cm'):
        dev = d[c] - d.groupby(['pitcher_id', 'pitch_type'])[c].transform('median')
        out[c] = dev.groupby(d.stadium).median()
    o = pd.DataFrame(out); o = o[d.stadium.value_counts().reindex(o.index) > 3000].round(1)
    print(yr, 'adjust coverage', info.get('adjustment_coverage_pct'), '%'); print(o.T.to_string())
    print('   구장 간 범위(cm)', (o.max() - o.min()).round(1).to_dict())
```

## 부록 D. 항목 1·2 검증과 3번 분석 재현 스크립트

모두 읽기 전용이고, 저장소 루트에서 `PYTHONPATH=src OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2 python <파일> [인자...]`로 실행합니다(Python 3.12, `constraints-za.txt`).

`pzone_gate.py` — 7.4절 통과 기준. 인자로 시즌을 줍니다.

```python
"""ABS p_zone 판정면 입력 통과 기준 확인: 프로덕션 load_rows + predict_pzone, score_crossfit과 같은 3개 날짜 블록."""
import sys, json, pathlib; sys.path.insert(0, 'src')
import numpy as np, pandas as pd
from visualbaseball import zone_decision as zd, plate_decision_v1 as old
root = pathlib.Path('.').resolve()
KINDS = ['4-Seam Fastball', '2-Seam Fastball', 'Slider', 'Curveball', 'Changeup', 'Forkball', 'Cutter', 'Sweeper', 'Splitter']
out = {}
for season in map(int, sys.argv[1:]):
    rows, source = zd.load_rows(root, season)
    dates = np.array(sorted({r['game_id'][:8] for r in rows}))
    pred = {name: np.full(len(rows), np.nan) for name in ('current', 'plane')}
    idx = {id(r): i for i, r in enumerate(rows)}
    for block in np.array_split(dates, zd.CROSSFIT_FOLDS):
        held = set(block); train = [r for r in rows if r['game_id'][:8] not in held]; test = [r for r in rows if r['game_id'][:8] in held]
        where = [idx[id(r)] for r in test]
        pred['current'][where] = old.predict_pzone(train, test)
        pred['plane'][where] = old.predict_pzone(train, test, zd.PZONE_ABS)
    d = pd.DataFrame({'is_take': [r['decision_type'] == 'Take' for r in rows], 'cs': [r['event'] == 'CalledStrike' for r in rows],
                      'pitch_type': [r.get('pitch_type') for r in rows], 'x': [abs(r['x_mid_relative']) * 25.4 for r in rows],
                      'top': [r['top_gap_cm'] for r in rows], 'bot': [r['bottom_gap_cm'] for r in rows], **pred})
    t = d[d.is_take].copy(); y = t.cs.astype(float)
    bands = {'bottom': (t.x < 18) & t.bot.between(-8, -2), 'top': (t.x < 18) & t.top.between(.5, 6.5),
             'side': (t.top < -10) & (t.bot > 10) & t.x.between(23.7, 29.7)}
    res = {'pitches': len(rows), 'takes': len(t), 'pzone_input': source['pzone_input']}
    for name in pred:
        p = t[name].clip(1e-6, 1 - 1e-6)
        m = {'logloss': float(-np.mean(y * np.log(p) + (1 - y) * np.log(1 - p))), 'brier': float(np.mean((p - y) ** 2)), 'misclass_pct': float(100 * np.mean((p > .5) != y))}
        for band, sel in bands.items():
            g = t[sel & t.pitch_type.isin(KINDS)].groupby('pitch_type').apply(lambda s: pd.Series({'n': len(s), 'obs': s.cs.mean(), 'pred': s[name].mean()}), include_groups=False)
            g = g[g.n >= 100]; err = (g.obs - g.pred).abs()
            m[f'{band}_max_abs_err'] = float(err.max()); m[f'{band}_weighted_abs_err'] = float((err * g.n).sum() / g.n.sum())
            m[f'{band}_worst_type'] = str(err.idxmax())
        res[name] = m
    cur, pl = res['current'], res['plane']
    res['gate'] = {'edge_calibration_max_lt_0.05': max(pl[f'{b}_max_abs_err'] for b in bands) < .05,
                   'logloss_not_worse': pl['logloss'] <= cur['logloss']}
    out[season] = res
    print(season, json.dumps(res, ensure_ascii=False, indent=1), flush=True)
```

`isolate.py` — 7.4절 선수 SBJ 변화와 두 표준오차. 해당 시즌 ZA 빌드 후 실행합니다.

```python
"""같은 p_swing에서 p_zone만 현행(앞면) 대 판정면으로 바꿨을 때 선수 SBJ(za_raw) 변화.
두 기준을 따로 보고한다: (a) 변화 크기 대 점수 자체의 경기 군집 표준오차(실무적 크기),
(b) 같은 투구·같은 경기로 묶은 점수 차이의 경기 군집 표준오차(두 모델 차이의 통계적 검출)."""
import sys, pathlib; sys.path.insert(0, 'src')
import numpy as np, pandas as pd
from scipy.stats import spearmanr
from visualbaseball import plate_decision_v1 as old, zone_decision as zd

def cluster_se(x, g):
    """경기 군집 표준오차: sqrt(G/(G-1) * sum_g (sum_i (x_i - mean))^2) / n."""
    dev = pd.Series(x - x.mean()).groupby(g.to_numpy()).sum().to_numpy(); G = len(dev)
    return np.sqrt(G / (G - 1) * np.sum(dev ** 2)) / len(x) if G > 1 else np.nan

for yr in map(int, sys.argv[1:]):
    rows = pd.read_parquet(f'data/metrics/zone_awareness/{yr}/pitches.parquet').to_dict('records')
    dates = np.array(sorted({r['game_id'][:8] for r in rows})); p_old = np.full(len(rows), np.nan)
    for block in np.array_split(dates, zd.CROSSFIT_FOLDS):
        held = set(block); train = [r for r in rows if r['game_id'][:8] not in held]
        test_i = [i for i, r in enumerate(rows) if r['game_id'][:8] in held]
        p_old[test_i] = old.predict_pzone(train, [rows[i] for i in test_i])
    d = pd.DataFrame({'b': [r['batter_id'] for r in rows], 'g': [r['game_id'] for r in rows], 's': [r['swing'] for r in rows],
                      'q': [r['p_swing'] for r in rows], 'p_new': [r['p_zone'] for r in rows], 'p_old': p_old})
    d['j_new'] = 100 * (d.s - d.q) * (2 * d.p_new - 1); d['j_old'] = 100 * (d.s - d.q) * (2 * d.p_old - 1); d['diff'] = d.j_new - d.j_old
    res = []
    for b, x in d.groupby('b'):
        if len(x) < 300: continue
        res.append({'b': b, 'old': x.j_old.mean(), 'new': x.j_new.mean(), 'se_score': cluster_se(x.j_old.to_numpy(), x.g), 'diff': x['diff'].mean(), 'se_diff': cluster_se(x['diff'].to_numpy(), x.g)})
    r = pd.DataFrame(res).set_index('b'); dl = r['diff'].abs(); z = r['diff'] / r.se_diff
    rk = (r.new.rank(ascending=False) - r.old.rank(ascending=False)).abs()
    print(f"{yr}: 적격 {len(r)} | Spearman {spearmanr(r.old, r.new)[0]:.4f} | |ΔSBJ| 중앙값 {dl.median():.3f} p90 {dl.quantile(.9):.3f} 최대 {dl.max():.3f} | "
          f"(a) 점수 SE 중앙값 {r.se_score.median():.2f}, |Δ|>점수 SE {int((dl > r.se_score).sum())}명 | "
          f"(b) 차이 SE 중앙값 {r.se_diff.median():.3f}, |z|>1.96 {int((z.abs() > 1.96).sum())}명 ({100*(z.abs() > 1.96).mean():.0f}%) | 최대 순위 이동 {rk.max():.0f}")
```

`fallback_pop.py` — 7.4절 fallback 모집단. 인자로 시즌을 줍니다.

```python
"""무효 궤적 투구가 전체 → ZA 적격 투구 사이 어느 단계에서 빠지는지 집계 (읽기 전용)."""
import sys, pathlib; sys.path.insert(0, 'src')
from collections import Counter
from visualbaseball.curated import load_rows
from visualbaseball import zone_decision as zd
root = pathlib.Path('.').resolve()
for season in map(int, sys.argv[1:]):
    rows = load_rows(root, 'pitches', season); events = load_rows(root, 'events', season)
    bad = lambda r: not r.get('trajectory_valid')
    print(season, 'curated 전체', len(rows), '무효 궤적', sum(map(bad, rows)), dict(Counter(r.get('trajectory_status') for r in rows if bad(r))))
    kept, _ = zd.reliable_halves(rows, events)
    print('  reliable_halves 후', len(kept), '무효', sum(map(bad, kept)))
    stage = Counter()
    for r in kept:
        if not bad(r): continue
        if r.get('parse_status') != 'ok': stage['parse_status≠ok'] += 1
        elif zd._relative_location(r) is None: stage['위치/존 결측'] += 1
        elif not zd._eligible(r): stage['상태·행동 부적격'] += 1
        elif zd.outcome(r) is None: stage['판정 코드 없음'] += 1
        elif not r.get('batter_id') or not r.get('batter_name'): stage['타자 식별 없음'] += 1
        else: stage['적격 (fallback 대상)'] += 1
    print('  무효 궤적 투구의 탈락 단계', dict(stage))
    miss = Counter(k for r in kept if bad(r) for k in ('px', 'pz', 'sz_top', 'sz_bottom', 'pitch_call_code') if r.get(k) is None)
    print('  무효 궤적 투구의 결측 필드', dict(miss))
```

`wb_sign.py` — 8.1-4 워크북 오프셋 부호 (중앙값 방식).

```python
"""기존 park adjustment HB/IVB 오프셋과 VB 실측 구장 편향(포수 시점, 같은 투수·구종 기준)의 관계를 손별로 본다."""
import sys, pathlib; sys.path.insert(0, 'src')
import numpy as np, pandas as pd
from visualbaseball.curated import load_rows
from visualbaseball.pitch_arsenal import _load_park_factors, _pitch_code, _stadium, _throws, PARK_FACTOR_CODE
root = pathlib.Path('.')
for yr in (2023, 2024, 2025, 2026):
    rows = load_rows(root, 'pitches', yr, columns=['pitch_id','pitch_type_code','pitch_type_kr','pitcher_id','stadium','horizontal_movement_cm','vertical_movement_cm','release_x_50'])
    d = pd.DataFrame(rows)
    d['code'] = [PARK_FACTOR_CODE.get(_pitch_code(r), _pitch_code(r)) for r in rows]; d['park'] = d.stadium.map(_stadium)
    hand = d.groupby('pitcher_id').release_x_50.apply(lambda s: _throws([v for v in s if v == v])); d['throws'] = d.pitcher_id.map(hand)
    f = _load_park_factors(root, yr)
    for comp, col, k in (('HB', 'horizontal_movement_cm', 0), ('IVB', 'vertical_movement_cm', 1)):
        d['dev'] = d[col] - d.groupby(['pitcher_id', 'code'])[col].transform('median')
        g = d.groupby(['park', 'code', 'throws']).dev.agg(['median', 'size']).reset_index(); g = g[(g['size'] >= 300) & g.code.ne('')]
        g['offset'] = [f.get((p, c), (np.nan, np.nan))[k] for p, c in zip(g.park, g.code)]; g = g.dropna(subset=['offset'])
        line = []
        for h in ('R', 'L'):
            s = g[g.throws == h]
            if len(s) > 5:
                slope = np.polyfit(s.offset, s['median'], 1)[0]; r = np.corrcoef(s.offset, s['median'])[0, 1]
                line.append(f"{h}: n={len(s)} slope={slope:+.2f} r={r:+.2f}")
        print(yr, comp, 'measured bias ~ workbook offset |', ' | '.join(line), '(정상 보정이면 slope≈-1, 부호 반대면 +1)')
```

`wb_sign_fe.py` — 8.1-4 워크북 오프셋 부호 (2원 고정효과). 인자로 시즌을 줍니다.

```python
"""2원 고정효과(투수×구종 + 구장×구종)로 구장 효과를 추정하고 워크북 오프셋과 비교 (정상 보정이면 기울기 ≈ −1)."""
import sys, pathlib; sys.path.insert(0, 'src')
import numpy as np, pandas as pd
from visualbaseball.curated import load_rows
from visualbaseball.pitch_arsenal import _load_park_factors, _pitch_code, _stadium, PARK_FACTOR_CODE
root = pathlib.Path('.')
for yr in map(int, sys.argv[1:]):
    rows = load_rows(root, 'pitches', yr, columns=['pitch_id','pitch_type_code','pitch_type_kr','pitcher_id','stadium','horizontal_movement_cm','vertical_movement_cm'])
    d = pd.DataFrame(rows); d['code'] = [PARK_FACTOR_CODE.get(_pitch_code(r), _pitch_code(r)) for r in rows]; d['park'] = d.stadium.map(_stadium)
    d = d[d.code.ne('')].dropna(subset=['horizontal_movement_cm', 'vertical_movement_cm'])
    f = _load_park_factors(root, yr); out = []
    for comp, col, k in (('HB', 'horizontal_movement_cm', 0), ('IVB', 'vertical_movement_cm', 1)):
        y = d[col].to_numpy(float); a = d.groupby(['pitcher_id', 'code']).ngroup().to_numpy(); b = d.groupby(['park', 'code']).ngroup().to_numpy()
        ea = np.zeros(a.max() + 1); eb = np.zeros(b.max() + 1)
        for _ in range(200):
            ea = np.bincount(a, y - eb[b]) / np.bincount(a); eb = np.bincount(b, y - ea[a]) / np.bincount(b)
        keys = d.groupby(['park', 'code']).size().reset_index(name='n'); keys['eff'] = eb   # ngroup()은 정렬된 그룹 순서로 번호를 매기므로 keys 행 순서와 같다
        keys['eff'] = keys['eff'] - keys.groupby('code')['eff'].transform('mean')   # 구종별로 중심화(구장 간 상대 효과)
        keys['off'] = [f.get((p, c), (np.nan, np.nan))[k] for p, c in zip(keys.park, keys.code)]
        keys['off'] = keys['off'] - keys.groupby('code')['off'].transform('mean')
        s = keys[(keys.n >= 300)].dropna()
        slope = np.polyfit(s.eff, s.off, 1)[0]; r = np.corrcoef(s.eff, s.off)[0, 1]
        rng = keys[keys.n >= 300].groupby('park').eff.median()
        out.append(f'{comp}: 구장 효과 범위 {rng.max() - rng.min():.1f}cm, 워크북 오프셋 ~ 추정 효과 기울기 {slope:+.2f}, 상관 {r:+.2f} (n={len(s)})')
    print(yr, ' | '.join(out))
```

`traj_move.py` — 8.1-1 무브먼트와 궤적 가속도.

```python
"""제공 무브먼트 컬럼 대 궤적 계수로 계산한 무브먼트: 관계와 구장 편향 (읽기 전용)."""
import sys, pathlib; sys.path.insert(0, 'src')
import numpy as np, pandas as pd
from visualbaseball.curated import load_rows
G = 32.174; CM = 30.48
for yr in (2024, 2025, 2026):
    d = pd.DataFrame(load_rows(pathlib.Path('.'), 'pitches', yr, columns=['pitcher_id','pitch_type','stadium','horizontal_movement_cm','vertical_movement_cm','trajectory_status','y0','vy0','ay','ax','az','arrival_time_s']))
    d = d[d.trajectory_status == 'valid'].copy()
    a, b, c = .5 * d.ay, d.vy0, d.y0 - 17 / 12
    t = (-b - np.sqrt(b * b - 4 * a * c)) / (2 * a)          # y0(50/55ft) -> 플레이트 앞면
    d['hb_traj'] = .5 * d.ax * t * t * CM; d['ivb_traj'] = .5 * (d.az + G) * t * t * CM
    for prov, traj in (('horizontal_movement_cm', 'hb_traj'), ('vertical_movement_cm', 'ivb_traj')):
        ok = d[[prov, traj]].notna().all(axis=1); s, i = np.polyfit(d.loc[ok, traj], d.loc[ok, prov], 1)
        resid = d.loc[ok, prov] - (s * d.loc[ok, traj] + i)
        print(f'{yr} {prov} = {s:.3f}*{traj} {i:+.2f}  r={d.loc[ok, prov].corr(d.loc[ok, traj]):.4f}  resid MAD {(resid - resid.median()).abs().median():.2f}cm')
    rng = {}
    for c_ in ('horizontal_movement_cm', 'hb_traj', 'vertical_movement_cm', 'ivb_traj', 'ax', 'az'):
        dev = d[c_] - d.groupby(['pitcher_id', 'pitch_type'])[c_].transform('median')
        m = dev.groupby(d.stadium).median(); m = m[d.stadium.value_counts().reindex(m.index) > 3000]
        rng[c_] = round(float(m.max() - m.min()), 2)
    print(f'{yr} 구장 간 범위:', rng, '(ax, az는 ft/s^2)')
```

`defconv.py` — 8.1-3 측정 구간 정의 변환. 부록 A `trackman()`의 매칭 결과 `m`(TrackMan `extension` 포함)을 parquet으로 저장하고 그 경로를 인자로 줍니다.

```python
"""VB(50ft→앞면)와 TrackMan(릴리스→플레이트) 무브먼트 구간 차이를 투구별 extension으로 변환했을 때 스케일이 얼마나 설명되는가 (탐색 매칭 2024)."""
import numpy as np, pandas as pd, sys
m = pd.read_parquet(sys.argv[1]); m['ext'] = pd.to_numeric(m.extension, errors='coerce')
m = m.dropna(subset=['ext', 'vertical_movement_cm', 'induced_vert_break', 'horizontal_movement_cm', 'horz_break'])
m = m[m.ext.between(1.0, 2.6)]
f = ((50 - 17/12) / (60.5 - m.ext * 3.28084 - 17/12)) ** 2
print(f'n={len(m)} 거리비 제곱 f: 중앙값 {f.median():.3f}, 5–95% {f.quantile(.05):.3f}–{f.quantile(.95):.3f}')
for vb, tm, sign in (('vertical_movement_cm', 'induced_vert_break', 1), ('horizontal_movement_cm', 'horz_break', -1)):
    x = sign * m[tm]
    for name, xx in (('원값', x), ('f 변환', f * x)):
        s, i = np.polyfit(xx, m[vb], 1); r = m[vb] - (s * xx + i)
        print(f'  {vb} ~ TM {name}: 기울기 {s:.3f}, 절편 {i:+.2f}, 잔차 MAD {(r - r.median()).abs().median():.2f}')
```

`pitch_id_proto.py` — 8.1-5 공통 투구 ID 프로토타입. 인자로 시즌을 줍니다.

```python
"""공통 투구 ID 프로토타입 (읽기 전용): 경기 매핑 → 반이닝 내 타석 순서 → 타석 내 투구 번호. 저장하지 않는다."""
import sys, pathlib; sys.path.insert(0, 'src')
import numpy as np, pandas as pd
from visualbaseball.curated import load_rows
yr = int(sys.argv[1])
t = pd.read_csv(f'data/tracking/raw/season={yr}/trackman_history.csv', dtype=str)
t = t[~t.pitcher_team.str.startswith('MIN_')].copy()
t['date'] = pd.to_datetime(t.game_date, format='mixed').dt.strftime('%Y%m%d')
for c in ('inning', 'pitch_no', 'pitch_of_pa', 'balls_before', 'strikes_before', 'outs_before'): t[c] = pd.to_numeric(t[c])
t['rel_speed'] = pd.to_numeric(t.rel_speed); t['half'] = np.where(t.top_bottom.str.lower().str.startswith('t'), 'top', 'bottom')
v = pd.DataFrame(load_rows(pathlib.Path('.'), 'pitches', yr, columns=['pitch_id', 'game_id', 'inning', 'inning_half', 'pitcher_id', 'batter_id', 'balls_before', 'strikes_before', 'outs_before', 'velocity_kmh']))
v['date'] = v.game_id.str[:8]; v['half'] = v.inning_half.astype(str).str.lower()
parts = v.pitch_id.str.split('-'); v['pa_seq'] = parts.str[-2].astype(int); v['pitch_in_pa'] = parts.str[-1].astype(int)
for c in ('pitcher_id', 'batter_id'): v[c] = v[c].astype(str)
# 1) 경기 매핑: 같은 날짜에서 투수 집합 Jaccard 최대이며 유일한 경우만
tg = t.groupby('trackman_game_id').agg(date=('date', 'first'), P=('pitcher_trackman_id', lambda s: frozenset(s)))
vg = v.groupby('game_id').agg(date=('date', 'first'), P=('pitcher_id', lambda s: frozenset(s)))
gmap, amb = {}, 0
for gid, row in tg.iterrows():
    cands = vg[vg.date == row.date]
    if cands.empty: continue
    j = cands.P.apply(lambda p: len(p & row.P) / len(p | row.P)).sort_values(ascending=False)
    if j.iloc[0] >= .6 and (len(j) == 1 or j.iloc[1] < .3): gmap[gid] = j.index[0]
    else: amb += 1
dup = pd.Series(gmap).value_counts(); dup = dup[dup > 1]
print(f'{yr} TM 1군 경기 {len(tg)}, 매핑 {len(gmap)}, 모호/실패 {amb}, VB 경기 중복 매핑 {len(dup)}, VB 경기 {len(vg)}')
t = t[t.trackman_game_id.isin(gmap)].copy(); t['game_id'] = t.trackman_game_id.map(gmap)
# 2) 타석: 반이닝 안에서 (타자, 투수) 연속 구간 = 타석, 순서 k
t = t.sort_values(['game_id', 'pitch_no'])
newpa = (t.pitch_of_pa == 1) | (t.batter_trackman_id != t.batter_trackman_id.shift()) | (t.game_id != t.game_id.shift())
t['pa_idx'] = newpa.cumsum(); t['k'] = t.groupby(['game_id', 'inning', 'half']).pa_idx.rank(method='dense').astype(int)
v = v[v.game_id.isin(set(gmap.values()))].copy()
v['k'] = v.groupby(['game_id', 'inning', 'half']).pa_seq.rank(method='dense').astype(int)
key = ['game_id', 'inning', 'half', 'k', 'pitch_in_pa']
t = t.rename(columns={'pitch_of_pa': 'pitch_in_pa'})
m = t.merge(v, on=key, how='inner', suffixes=('_tm', '_vb'))
same_batter = m.batter_trackman_id == m.batter_id; same_pitcher = m.pitcher_trackman_id == m.pitcher_id
same_count = (m.balls_before_tm == m.balls_before_vb) & (m.strikes_before_tm == m.strikes_before_vb) & (m.outs_before_tm == m.outs_before_vb)
ok = same_batter & same_pitcher & same_count
dv = (m.velocity_kmh - m.rel_speed)
mm = m[~same_pitcher & same_count]; pairs = mm.groupby(["pitcher_trackman_id","pitcher_id"]).size()
tm_to_vb = mm.groupby("pitcher_trackman_id").pitcher_id.nunique()
print(f"  투수 불일치 {len(mm)}행: TM ID {mm.pitcher_trackman_id.nunique()}개, (TM,VB) 쌍 {len(pairs)}개, TM ID 하나가 VB ID 하나로만 대응 {100*(tm_to_vb==1).mean():.1f}%, 불일치 TM ID 중 VB에도 존재 {100*mm.pitcher_trackman_id.isin(set(v.pitcher_id)).mean():.1f}%")
print("  예시", pairs.sort_values(ascending=False).head(5).to_dict())
print(f'  키 일치 {len(m)} = VB(매핑 경기) {len(m)/len(v):.3f}; 타자 일치 {same_batter.mean():.4f}, 투수 일치 {same_pitcher.mean():.4f}, 카운트·아웃 일치 {same_count.mean():.4f}, 셋 다 {ok.mean():.4f}')
print(f'  검증 통과 투구 {ok.sum()} = VB 전체 투구 {ok.sum()/len(pd.DataFrame(load_rows(pathlib.Path("."), "pitches", yr, columns=["pitch_id"]))):.3f}')
for name, sel in (('검증 통과', ok), ('검증 실패', ~ok)):
    d = dv[sel]
    if len(d): print(f'  {name}: 구속차 중앙값 {d.median():+.2f}, |차|>3 {100*(d.abs()>3).mean():.2f}%, |차|>8 {100*(d.abs()>8).mean():.2f}%')
```
