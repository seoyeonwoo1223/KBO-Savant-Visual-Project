# SBJ (Strikezone-Ball Judgment) 외부 교차검증 요청서 — 2026 KBO

이 문서는 저장소에 접근할 수 없는 외부 검토자가 **이 문서 하나만 읽고** 판단할 수 있도록 작성되었습니다.
필요한 코드·수치·한계는 전부 본문 안에 인용되어 있습니다. 외부 링크나 저장소 파일 참조로 내용을 대신하지 않았습니다.

---

## 0. 저장소 상태 (재현 기준점)

| 항목 | 값 |
|---|---|
| 저장소 경로 | `/home/user/KBO-Savant-Visual-Project` |
| 브랜치 | `claude/happy-hopper-g1h339` |
| 기준 커밋 | `df345e75` — "SBJ: 기대 대비 스트라이크/볼 판단 정확도를 선수 단위로 노출" |
| 워킹 트리 | 깨끗함 (푸시 완료). 본 문서 작성 시점에 추적 파일 변경 없음 |
| 실행 환경 | Python 3.12, `.venv/`에 `requirements.txt` + `constraints-za.txt` 고정 버전 설치 |
| 고정 패키지 | numpy 2.5.3, pandas 2.3.3, pyarrow 19.0.1, scikit-learn 1.9.0, scipy 1.18.1 |
| 필수 환경변수 | `PYTHONPATH=src` (권장 `OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2`) |

---

## 1. 검토자용 배경

### 1.1 무엇에 대한 프로젝트인가

한국 프로야구(KBO) 경기의 **공개 투구 단위 중계 데이터(PBP, play-by-play)** 를 수집해 정규화하고,
거기서 파생 지표를 계산해 웹 뷰어와 스프레드시트로 공개하는 개인 프로젝트입니다.
MLB의 Baseball Savant와 비슷한 성격의 뷰어를 KBO 공개 데이터로 만드는 작업입니다.

데이터 제공처는 투구별로 다음을 공개합니다: 홈플레이트 통과 좌표, 구속, 구종, 움직임(수평/수직 변화량),
볼카운트, 주자·아웃 상태, 그리고 **그 투구에 대한 심판/시스템의 판정 코드**(볼 `B`, 콜 스트라이크 `T`,
헛스윙 `S`, 파울 `F`, 인플레이 `X`).

2026 시즌 KBO는 **ABS(Automatic Ball-Strike System, 자동 볼판정 시스템)** 환경입니다.
즉 콜 스트라이크/볼 판정은 심판 재량이 아니라 트래킹 기반 규칙으로 내려집니다.
이 점은 뒤에 나오는 "존 경계 모델의 계통 오차"(6.3절) 쟁점의 전제입니다.

### 1.2 저장소 용어 — 전부 풀어서 정의

검토자가 알 필요가 없는 내부 용어를 이 문서에서는 다음과 같이 씁니다.

| 저장소 용어 | 뜻 |
|---|---|
| **curated** | 원본 JSON을 정규화해 저장한 canonical 테이블(Parquet). `pitches`(투구), `events`(사건), `games`(경기) 세 테이블. 모든 지표는 여기서만 읽습니다. |
| **decision_pitches** | "타자가 스윙할지 말지를 실제로 선택한 상황"만 남긴 투구 부분집합. 번트 시도, 판정 불명, 좌표 결측 등은 제외됩니다. 이후 모든 판단 지표의 공통 입력입니다. 본 문서에서는 **"자격 투구(eligible pitch)"** 로 부릅니다. |
| **ZA v7** | Zone Awareness 모델의 7번째 세대. 본 문서에서 다루는 코드 모듈(`zone_decision.py`)의 버전 이름이며, 모델 식별자는 `za7-strikezone-judgment`입니다. |
| **`p_zone`** | 해당 투구가 스트라이크 존을 통과할 추정 확률 (0~1). 아래 1.3에서 추정 방법을 설명합니다. |
| **`p_swing`** | **리그 평균 타자**가 그 투구에 스윙할 추정 확률 (0~1). 타자 개인 정체성은 입력에 들어가지 않습니다. |
| **`S`** | 그 투구에 대한 **실제** 스윙 여부. 스윙이면 1, 지켜봤으면(take) 0. |
| **`za_raw`** | 기존 지표. `100 × mean((S − p_swing) × (2·p_zone − 1))`, 단위 percentage point. |
| **DV / DV+** | Decision Value. 스윙/테이크 선택의 기대 득점가치 차이를 누적한 별개 지표군. 본 문서의 주제는 아니지만 5절 한계에서 언급합니다. |
| **자격 타자 (qualified)** | 해당 시즌 자격 투구 **300구 이상**을 본 타자. |

### 1.3 `p_zone`과 `p_swing`이 어떻게 만들어지는가 — 검토자가 가장 먼저 의심할 지점

두 확률 모두 **gradient boosting 분류기**(scikit-learn `HistGradientBoostingClassifier`,
`learning_rate=0.07, max_iter=130, max_leaf_nodes=20, min_samples_leaf=80, l2_regularization=1.5`)로 적합됩니다.
둘 다 **교차적합(cross-fit)** 으로 산출되어, 어떤 투구도 자기 자신이 포함된 학습 데이터로 채점되지 않습니다.

#### (a) `p_zone` — 존 통과 확률

```python
PZONE_NUMERIC = ("x_relative", "z_relative", "sz_top", "sz_bottom")

def predict_pzone(train, test):
    """Fit the take-only CalledStrike vs Ball/HBP model and score held-out pitches."""
    take = [row for row in train if row["decision_type"] == "Take"]
    target = np.array([str(row.get("pitch_call_code") or "").upper() == "T"
                       or row.get("event") == "CalledStrike" for row in take], dtype=int)
    model = _classifier().fit(_encode_numeric(take, PZONE_NUMERIC), target)
    probability = model.predict_proba(_encode_numeric(test, PZONE_NUMERIC))[:, list(model.classes_).index(1)]
    return np.clip(probability, 1e-6, 1 - 1e-6)
```

핵심 성질 세 가지입니다.

1. **학습 표본이 테이크(take) 투구뿐입니다.** 스윙한 투구는 판정이 관측되지 않으므로(헛스윙/파울/인플레이가 됨)
   라벨이 없습니다. 따라서 모델은 "지켜봤을 때 콜 스트라이크가 되었는가"를 학습하고, 그 함수를
   **스윙한 투구에도 외삽**합니다. 스윙 투구의 위치 분포는 테이크 투구와 다르므로 이는 공변량 이동(covariate shift)입니다.
2. **입력은 위치 4개뿐**입니다: 정규화 좌표 `x_relative`, `z_relative`와 그 투구의 존 상·하한 `sz_top`, `sz_bottom`.
   구속·구종·움직임·카운트는 `p_zone`에 들어가지 않습니다(존 통과 여부는 위치만의 함수라는 설계).
3. 좌표 규약: `x_relative`, `z_relative`는 존 경계가 ±1이 되도록 정규화한 값입니다.
   원좌표 `px`/`pz`는 feet, 홈플레이트 원점 기준이고 플레이트 반폭은 `10/12 ft`입니다.
   저장된 x 계열은 모두 **포수 시점(catcher view)** 입니다.

#### (b) `p_swing` — 리그 평균 스윙 확률

동일 계열 분류기이며 **타자 ID를 feature로 쓰지 않습니다.** 사용 feature는 다음과 같습니다.

```python
BASE_NUMERIC = ("x_relative", "z_relative", "balls_before", "strikes_before", "outs_before",
                "base_state_code_before", "velocity_kmh", "release_height_cm")
MOVEMENT_NUMERIC = ("adjusted_hb_cm", "adjusted_ivb_cm")   # 구장 보정 적용된 수평/수직 변화량
CATEGORICAL = ("pitch_type", "batter_stance", "stadium")
```

즉 위치·볼카운트·주자아웃 상태·구속·릴리스 높이·움직임·구종·타석 좌우·구장까지 쓰되,
**"누가 타석에 있는가"는 쓰지 않습니다.** 그래서 `p_swing`이 "리그 평균 타자의 스윙 성향"으로 해석됩니다.

추가로 **isotonic calibration**이 조건부로 적용됩니다. 학습 세트 안에서만 게임 단위 그룹 K-fold(최대 3)로
out-of-fold 확률을 만들고, 학습 날짜 80/20 분할에서 **log loss가 개선되고 Brier score가 나빠지지 않을 때만**
채택해 전체 학습 OOF에 다시 적합합니다. 채점 대상 경기의 결과는 이 게이트에 들어가지 않습니다.
채택 여부는 fold별로 기록됩니다.

```python
calibration_applied = (log_loss(truth, corrected, labels=[0,1]) < log_loss(truth, oof[held_mask], labels=[0,1])
                       and brier_score_loss(truth, corrected) <= brier_score_loss(truth, oof[held_mask]))
```

#### (c) 교차적합 구조

시즌 전체 날짜를 **연속된 3개 날짜 블록**으로 나누고, 각 블록을 채점할 때 그 블록을 학습에서 제외합니다.

```python
CROSSFIT_FOLDS = 3
SCORE_SETTINGS = {'calibration': True, 'support_prior': 50}

def score_crossfit(rows, selected, settings=SCORE_SETTINGS):
    """Score every pitch with a model that excludes its date block."""
    dates = np.array(sorted({r['game_id'][:8] for r in rows}))
    for fold, block in enumerate(np.array_split(dates, CROSSFIT_FOLDS)):
        held = set(block)
        train = [r for r in rows if r['game_id'][:8] not in held]
        test  = [r for r in rows if r['game_id'][:8] in held]
        pred  = fit_predict(train, test, **settings)
        pzone = old.predict_pzone(train, test)
        action = np.array([r['decision_type'] == 'Swing' for r in test], dtype=int)
        ...
        r.update({'swing': int(action[i]), 'p_swing': float(pred['p'][i]),
                  'p_zone': float(pzone[i]),
                  'judgment': float((action[i] - pred['p'][i]) * (2*pzone[i] - 1)), ...})
```

**주의**: 블록 제외는 "자기 경기 결과로 자기를 채점하지 않는다"는 보장일 뿐, 다른 블록이 **미래 날짜**일 수 있습니다.
시즌 표시값은 **사후(retrospective) 추정치이지 사전 예측 성능이 아닙니다.**

`support_prior=50`은 `p_zone`/`p_swing`이 아니라 **사건 확률(event probability)과 값 모델**에 적용되는 축소 계수입니다.
표본이 희박한 구간에서 학습 데이터만으로 만든 (카운트 × 구역 × 구종 × 스탠스) 사전분포 쪽으로 `n/(n+50)` 가중으로
당깁니다. 근방(neighborhood)은 정규화 좌표 0.5단위 격자, 볼카운트, 구종, 스탠스, 10 km/h 구속 구간,
10 cm 움직임 구간으로 정의됩니다. SBJ 자체의 계산에는 직접 관여하지 않지만, 같은 적합 호출 안에서 산출됩니다.

---

## 2. SBJ 정의와 산식

**SBJ (Strikezone-Ball Judgment)** 는 타자가 "칠 공과 안 칠 공"을 리그 평균 대비 얼마나 잘 갈랐는지를
**percentage point** 단위로 나타내는 값입니다.

$$
\mathrm{SBJ} = 100 \times \Big[\underbrace{\overline{\big(S\,q + (1-S)(1-q)\big)}}_{\text{관측 판단 정확도}} - \underbrace{\overline{\big(p\,q + (1-p)(1-q)\big)}}_{\text{기대 판단 정확도}}\Big]
$$

- $q = $ `p_zone` (그 투구가 존을 통과할 확률)
- $p = $ `p_swing` (리그 평균 타자가 스윙할 확률)
- $S \in \{0,1\}$ = 실제 스윙 여부
- 평균은 그 타자의 자격 투구 전체에 대한 단순 평균

해석: 스윙은 `p_zone`만큼, 테이크는 `1 − p_zone`만큼 "옳았다"고 인정합니다.
기대값은 같은 투구 구성을 **리그 평균 스윙 정책**이 상대했을 때의 같은 양입니다.

구현 (전문 인용):

```python
def _judgment_accuracy(items):
 # Swings are correct in proportion to p_zone, takes to 1 - p_zone.
 return np.mean([r['p_zone'] if r['swing'] else 1-r['p_zone'] for r in items])


def _expected_judgment_accuracy(items):
 return np.mean([r['p_swing']*r['p_zone']+(1-r['p_swing'])*(1-r['p_zone']) for r in items])


def judgment_accuracy(items):
 """Observed strike/ball judgment accuracy, in percent."""
 return r6(100*_judgment_accuracy(items)) if items else None


def expected_judgment_accuracy(items):
 """Same accuracy for a league-average swing policy on this pitch mix; the SBJ baseline."""
 return r6(100*_expected_judgment_accuracy(items)) if items else None


def strikezone_ball_judgment(items):
 """SBJ: judgment accuracy above the league-average baseline, in percentage points.

 Identical to zone_awareness() by algebra - the per-pitch difference
 (S*q + (1-S)*(1-q)) - (p*q + (1-p)*(1-q)) reduces to (S - p) * (2q - 1),
 which is the 'judgment' term. Kept as its own function so the observed and
 expected components stay reportable; never cite SBJ and za_raw as two
 independent measurements.
 """
 return r6(100*(_judgment_accuracy(items)-_expected_judgment_accuracy(items))) if items else None
```

선수 단위 출력에 노출되는 필드(계약 문자열 원문):

```
'sbj': '100 * (mean(p_zone if swing else 1 - p_zone) - mean(p_swing*p_zone + (1-p_swing)*(1-p_zone)));
        percentage points. Observed strike/ball judgment accuracy minus league-expected accuracy.
        Algebraically identical to za_raw: the per-pitch difference reduces to (S - p_swing) * (2*p_zone - 1).
        Reported as a separate field for its auditable components, NOT as independent evidence from za_raw.'
'judgment_accuracy_pct': '100 * mean(p_zone if swing else 1 - p_zone); percent.'
'expected_judgment_accuracy_pct': '100 * mean(p_swing*p_zone + (1-p_swing)*(1-p_zone)); percent. ... the SBJ baseline.'
'za_raw': '100 * mean((S - p_swing) * (2*p_zone - 1)); percentage points'
'swing_aggression': '100 * mean(S - p_swing); percentage points, tendency only'
```

---

## 3. 핵심 쟁점 — SBJ와 `za_raw`의 대수적 동일성

이 문서에서 검토자에게 가장 묻고 싶은 것입니다.

### 3.1 기호 유도

투구 하나의 관측 정확도에서 기대 정확도를 뺀 값은

$$
\begin{aligned}
&\big(Sq + (1-S)(1-q)\big) - \big(pq + (1-p)(1-q)\big) \\
&= \big[(1-q) + S(2q-1)\big] - \big[(1-q) + p(2q-1)\big] \\
&= (S - p)(2q - 1)
\end{aligned}
$$

즉 투구별 차이는 정확히 `(S − p_swing) × (2·p_zone − 1)`이고, 이것은 코드에 `judgment`로 저장되는
per-pitch 항 그대로입니다. 평균은 선형이므로

$$
\mathrm{SBJ} = 100 \times \overline{(S-p)(2q-1)} = \texttt{za\_raw}
$$

가 **모든 데이터에서 항등적으로** 성립합니다. 근사가 아니라 항등식입니다.

### 3.2 실데이터 확인 (검증됨)

2026 시즌 전체 자격 투구 **192,526구 / 타자 285명**에 대해, 저장된 `p_swing`·`p_zone`·`swing`으로
SBJ와 `za_raw`를 각각 독립 재계산했습니다.

- 보고 정밀도(소수 6자리 반올림) 기준 **max |SBJ − za_raw| = 0.0** (285명 전원)
- 반올림 전 배정도 부동소수 기준 **max |SBJ − za_raw| = 3.02 × 10⁻¹⁴** (부동소수 누산 오차 수준)

### 3.3 테스트로 고정된 사항

```python
def test_sbj_equals_zone_awareness_and_is_not_independent_evidence():
 # SBJ reduces to (S - p_swing) * (2*p_zone - 1), so it must track za_raw exactly.
 rng=np.random.default_rng(11)
 for _ in range(20):
  items=[_judgment_row(int(rng.integers(0,2)),float(rng.uniform(.05,.95)),float(rng.uniform(.05,.95)))
    for _ in range(rng.integers(5,60))]
  assert strikezone_ball_judgment(items)==zone_awareness(items)
```

### 3.4 검토자에게 묻는 것

현재 저장소의 입장은 다음과 같습니다.

> SBJ는 `za_raw`와 대수적으로 동일하다. 별도 필드로 두는 이유는 **구성요소(관측 정확도 68.08%,
> 기대 정확도 68.58%)를 감사 가능하게 분리 노출**하기 위함이며, SBJ와 `za_raw`를 **두 개의 독립 증거로
> 인용하는 것은 금지**한다.

**질문은 7절에 정리되어 있습니다.** 요약하면: 이 상황에서 SBJ를 별도 지표로 두는 것이 정당한가,
아니면 사실상 `za_raw`의 재명명(rename)인가.

---

## 4. 2026 실측 결과 (검증됨)

### 4.1 데이터 범위

`data/curated/summary.json` 기준 (2026-09-13 생성, 2026 시즌 진행 중 스냅샷):

| 시즌 | 경기 | pitches 행 | events 행 | 날짜 범위 |
|---|---|---|---|---|
| 2022 | 720 | 217,025 | 273,038 | 2022-04-02 ~ 2022-10-11 |
| 2023 | 720 | 219,839 | 276,161 | 2023-04-01 ~ 2023-10-17 |
| 2024 | 720 | 223,216 | 280,544 | 2024-03-23 ~ 2024-10-01 |
| 2025 | 720 | 217,852 | 277,384 | 2025-03-22 ~ 2025-10-04 |
| **2026** | **626** | **192,712** | 245,246 | 2026-03-28 ~ 2026-09-12 |

**SBJ 계산에 실제로 들어간 것은 2026 시즌뿐**이며, 위 192,712구 중 자격 필터를 통과한
**192,526구 / 타자 285명**입니다(차이 186구는 제외된 이닝·자격 미달 투구).

- 자격 기준(300구 이상)을 채운 타자: **163명**

### 4.2 자격 타자 163명 기술통계

| 값 | 결과 |
|---|---|
| SBJ 평균 | **−0.4931 pp** |
| SBJ 표준편차 (모집단, ddof=0) | **2.8890 pp** |
| SBJ 표준편차 (표본, ddof=1) | 2.8979 pp |
| SBJ 최솟값 | **−8.338 pp** |
| SBJ 최댓값 | **+5.775 pp** |
| 관측 판단 정확도 평균 | **68.08 %** (sd 3.09, ddof=0) |
| 기대 판단 정확도 평균 | **68.58 %** (sd 0.98, ddof=0) |

참고값 (자격 조건 없이):

- 타자 285명 전원 단순평균 SBJ: **−1.2777 pp**
- 투구 가중(192,526구 전체 풀링) SBJ: **−0.2726 pp**

### 4.3 상·하위 표본

아래 선수 이름은 **KBO 공개 중계 데이터에 게재된 공개 정보**에서 온 것이며, 값은 진행 중인 2026 시즌의
부분 표본에 대한 추정치입니다. 순위는 점추정 순서일 뿐 우열이 확립된 것이 아닙니다.

| 상위 5 | SBJ (pp) | 자격 투구 |
|---|---|---|
| 박건우 | +5.775 | 1,730 |
| 김도영 | +5.611 | 1,980 |
| 에레디아 | +5.023 | 1,465 |
| 오명진 | +4.607 | 606 |
| 한석현 | +4.335 | 486 |

| 하위 5 | SBJ (pp) | 자격 투구 |
|---|---|---|
| 심우준 | −7.591 | 1,636 |
| 김태군 | −7.723 | 719 |
| 김동헌 | −7.925 | 301 |
| 이지영 | −7.959 | 386 |
| 김헌곤 | −8.338 | 302 |

### 4.4 반드시 짚어야 할 점 — 왜 자격 타자 평균이 0이 아닌가

`p_swing`이 리그 평균 스윙 정책이라면, 소박한 직관으로는 리그 전체 평균 SBJ가 0 근처여야 합니다.
실제 값은 **자격 타자 평균 −0.4931 pp**, 전체 타자 평균 −1.2777 pp, 투구 가중 −0.2726 pp로
**셋 다 음수이고 서로 다릅니다.**

저장소에서 확인된 사실만 적으면:

- 세 평균이 다르다는 것 자체는 **가중치 차이**로 설명됩니다(타자 단순평균 vs 투구 가중평균).
  자격 미달 타자(투구 수 적음)가 더 음수이므로, 이들을 빼면 −1.28 → −0.49로 올라갑니다.
- 그러나 **투구 가중 평균조차 −0.2726 pp로 0이 아닙니다.** 즉 가중치만으로는 전부 설명되지 않습니다.
- 0이 아닐 수 있는 후보 경로(**어느 것도 저장소에서 측정되지 않음**):
  1. **교차적합**: 각 블록은 자기를 제외한 날짜로 학습되므로, `mean(p_swing)`이 그 블록의
     실제 `mean(S)`와 일치할 이유가 없습니다. `mean(S − p_swing) ≠ 0`이면 SBJ의 기댓값도 0이 아닙니다.
  2. **isotonic calibration**: 조건부로만 적용되고, 적용되더라도 학습 분포 기준이므로 held-out 블록에서
     평균 보존이 보장되지 않습니다.
  3. **`(2q−1)` 가중**: SBJ는 `mean(S−p)`가 아니라 `mean((S−p)(2q−1))`입니다.
     스윙 초과/미달이 `q`와 상관되어 있으면(예: 존 밖에서 과잉 스윙) 평균이 0에서 벗어납니다.
  4. **`p_zone`의 계통 오차**(6.3절) — 존이 실제보다 좁게 추정되면 `q`가 하향 편향되고
     `(2q−1)` 항이 비대칭적으로 이동합니다.
  5. **자격 조건(300구)** 에 의한 선택 편향.

**이 다섯 경로 중 어느 것이 얼마나 기여하는지는 측정하지 않았습니다.** 이것이 검토자에게 묻는 핵심 질문입니다(7절 Q3).

---

## 5. 검증 상태 표

이 표가 이 문서의 핵심입니다. **"미검증" 칸의 항목은 믿으면 안 됩니다.**

### 5.1 검증됨

| 주장 | 검증 방법 | 결과 |
|---|---|---|
| ZA v7 모듈 테스트 통과 | `PYTHONPATH=src python -m pytest tests/test_zone_decision.py -q` (커밋 `df345e75`) | **13 passed** |
| 저장소 전체 테스트 통과 | `PYTHONPATH=src python -m pytest -q` | **106 passed** |
| 웹 레이아웃 테스트 통과 (pytest가 수집하지 않아 별도 실행) | `node tests/test_pitch_arsenal_layout.cjs` | **PASS** |
| SBJ ≡ `za_raw` (기호) | 3.1절 대수 유도 | 항등식 성립 |
| SBJ ≡ `za_raw` (합성 데이터) | `test_sbj_equals_zone_awareness_and_is_not_independent_evidence` — 난수 20세트 | 전부 일치 |
| SBJ ≡ `za_raw` (실데이터) | 2026 285타자 재계산 | 6자리 반올림 기준 **max diff 0.0** (부동소수 원값 3.02e-14) |
| SBJ = 관측 − 기대 정확도 | `test_sbj_is_observed_minus_expected_judgment_accuracy` | 성립 |
| SBJ가 결과(타구가치)에 불변 | `test_sbj_is_outcome_independent_like_zone_awareness` — `delta_v`, `raw_run_value` 변조 후에도 동일 | 성립 |
| 4절 기술통계 | `data/metrics/zone_awareness/2026/pitches.parquet`에서 직접 재계산 (6절 스크립트) | 표대로 |

> SBJ 관련 테스트는 `tests/test_zone_decision.py` 안에서 이름이 `test_sbj_*`인 것이 **3개**이고,
> 여기에 `profile_summary()`가 `sbj`/`judgment_accuracy_pct` 필드를 만드는 경로를 통과시키는
> `test_sa_dv_stay_unchanged_and_dv_plus_is_standardized`를 더하면 4개가 SBJ 경로를 지납니다.
> 다만 네 번째 테스트는 SBJ 값 자체를 단언(assert)하지 않습니다.

### 5.2 미검증 — 빠짐없이

| # | 항목 | 상태 |
|---|---|---|
| U1 | **SBJ의 신뢰도(반분 신뢰도·재현성)를 측정하지 않았다.** | 미측정 |
| U2 | 구두로 전달된 "SBJ 1300구 환산 0.808"의 **산출 근거가 저장소에 없다** | 근거 부재 |
| U3 | ADR-005의 미결 4항목 (아래 5.3) | 미결 |
| U4 | `p_zone` 존 경계 모델의 **계통 오차**와 그 SBJ 전파 (아래 6.3) | 편향 존재 보고 / 전파 미측정 |
| U5 | 웹 산출물이 아직 SBJ 필드를 포함하지 않음 | 확인됨(아래) |
| U6 | SBJ ↔ 기존 DV/DV+ 상관 | 미측정 |
| U7 | 타자 유형별(좌/우, 파워/컨택 등) 편향 | 미측정 |
| U8 | 시즌 간 안정성 (2024·2025 대비) | 미측정 |

U5 보충 — 직접 확인한 사실: `web/data/zone_awareness/2026/leaderboard.json`의 선수 레코드 키에는
`za_raw`, `swing_aggression`, `dv_per_100`, `dv_plus` 등은 있으나 **`sbj`,
`judgment_accuracy_pct`, `expected_judgment_accuracy_pct`가 없습니다.** 파일 내
`metric_contract`에도 `sbj` 키가 없습니다. 즉 웹 산출물은 커밋 `df345e75` 이전 실행 결과이며,
다음 파이프라인 실행에서 재생성됩니다. 4절 수치는 웹 JSON이 아니라
**지표 원본 Parquet(`data/metrics/zone_awareness/2026/pitches.parquet`, 2026-09-15 생성)** 에서 계산했습니다.

### 5.3 ADR-005 미결 4항목 (원문 그대로 옮김)

저장소의 `docs/adr/ADR-005-split-half-reliability-length.md`(상태: **미결**, 작성 기준 커밋 `2b175409`)는
반분 신뢰도 0.568과 기록된 ZA 0.810의 관계를 판정 보류로 남겼습니다. 미결 항목은 다음과 같습니다.

> 1. **0.568이 Spearman-Brown 보정 전 반쪽-반쪽 원상관인지 확인되지 않았다.**
>    실무에서 "split-half reliability"로 보고되는 값은 이미 전체길이로 보정된 경우가 흔하다.
>    0.568이 이미 600구 값이라면 972구 환산값은 **0.6807**이며 0.810과 정면으로 모순된다.
>    주장은 보정 전 값임을 암묵 전제하나 그 전제가 기록되어 있지 않다.
> 2. **ZA 0.810의 측정 길이가 기록되어 있지 않다.** k=3.24는 0.810을 목표로 역산된 값으로 보인다.
>    ZA 0.810이 실제로 약 973구 길이에서 측정됐다는 독립 근거가 없다면, 길이를 가정해
>    길이 차이를 설명하는 순환 논증이 된다.
> 3. **0.568과 0.810이 동일 분할 절차로 산출됐는지 확인 불가.** 분할 방식(odd-even / 무작위 /
>    시간순)이 다르면 두 값은 애초에 직접 비교 대상이 아니다.
> 4. **SBJ · APR+ · DV_avg · Task 5 잔차의 기준 측정 길이가 모두 미상**이라 상호 비교가 불가능하다.
>    또한 이들이 ZA와 동일한 반쪽 분할 절차로 산출됐다는 근거도 없다.

### 5.4 신뢰도 수치 대장 — 길이 병기 필수

**신뢰도 값은 측정 길이 없이 기재하지 않습니다. 원값과 환산값을 같은 칸에 넣지 않습니다.**

| 지표 | 원값 (측정 길이) | Spearman-Brown 환산값 (환산 길이) | 환산 배수 k | 산출 근거 |
|---|---|---|---|---|
| ZA 반분 | 0.568 (반쪽 300구) | 0.8099 (972구) | 3.24 | **없음 — 미기록** |
| ZA 반분 (전체길이 보정) | 0.568 (반쪽 300구) | 0.7245 (600구) | 2.00 | ADR-005 계산 |
| ZA (기록값) | 0.810 (**측정 길이 미상**) | — | — | **없음 — 미기록** |
| **SBJ** | **미상 (미측정)** | 0.808 (1300구) | 미상 | **없음 — 미기록** |
| APR+ | **미상** | 0.783 (1300구) | 미상 | **없음 — 미기록** |
| DV_avg | **미상** | 0.787 (1300구) | 미상 | **없음 — 미기록** |
| Task 5 잔차 | 0.659 (**측정 길이 미상**) | 환산 불가 (기준 길이 미상) | — | **없음 — 미기록** |

기준 길이를 가정했을 때의 조건부 역산값입니다. **기준 길이가 확정되기 전까지 단독 인용 금지**입니다.

| 지표 | 1300구 환산값 | 기준 300구 가정 시 원값 | 기준 600구 가정 시 원값 |
|---|---|---|---|
| SBJ | 0.808 | 0.4927 | 0.6601 |
| APR+ | 0.783 | 0.4544 | 0.6248 |
| DV_avg | 0.787 | 0.4602 | 0.6304 |

Spearman-Brown 적용의 전제가 투구 단위 시계열에서 깨지는 경로 (ADR-005 기록):

| 경로 | 위반 전제 | 효과 |
|---|---|---|
| 타석·경기 단위 자기상관 | 오차 독립성 | 유효 표본수 < 명목 투구수 → 신뢰도 과대추정 |
| 상대 투수 구성 변화 | 항목 등가성(τ-등가) | 항목 이질 → 환산값 과대추정 |
| 시간순(전반기/후반기) 분할 | 반쪽 교환 가능성 | 기량 변동이 r을 눌러 환산 자체가 무효 |

따라서 환산값은 **"달성값"이 아니라 상한(upper bound) 추정치**로만 인용합니다.

---

## 6. 재현 방법 (저장소 접근자 기준)

검토자는 저장소에 접근할 수 없으므로 이 절은 **저장소 접근자가 4절 수치를 다시 만들 때** 쓰는 절차입니다.
아래 명령은 전부 커밋 `df345e75`에서 실제로 실행해 동작을 확인한 것만 실었습니다.

### 6.1 환경

```bash
cd /home/user/KBO-Savant-Visual-Project
git checkout df345e75
python -m pip install -r requirements.txt -c constraints-za.txt
export PYTHONPATH=src
export OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2
```

### 6.2 테스트

```bash
PYTHONPATH=src python -m pytest tests/test_zone_decision.py -q   # 13 passed
PYTHONPATH=src python -m pytest -q                               # 106 passed
node tests/test_pitch_arsenal_layout.cjs                         # PASS
```

### 6.3 지표 재빌드 (수 시간 소요, 선택)

```bash
PYTHONPATH=src python -m visualbaseball.zone_decision --seasons 2026
```

### 6.4 4절 기술통계 재현 스크립트 (실행 확인 완료)

```python
# 실행: PYTHONPATH=src python this_script.py   (저장소 루트에서)
import collections
import numpy as np
import pyarrow.parquet as pq

table = pq.read_table(
    'data/metrics/zone_awareness/2026/pitches.parquet',
    columns=['batter_id', 'batter_name', 'swing', 'p_swing', 'p_zone', 'judgment'])
d = table.to_pydict()
n = len(d['batter_id'])

groups = collections.defaultdict(list)
for i in range(n):
    groups[(d['batter_id'][i], d['batter_name'][i])].append(i)
print('pitches', n, 'batters', len(groups))          # -> 192526 285

rows, max_diff = [], 0.0
for (bid, name), idx in groups.items():
    S = np.array([d['swing'][i] for i in idx], float)
    p = np.array([d['p_swing'][i] for i in idx])
    q = np.array([d['p_zone'][i] for i in idx])
    J = np.array([d['judgment'][i] for i in idx])
    obs = np.mean(np.where(S == 1, q, 1 - q))
    exp = np.mean(p * q + (1 - p) * (1 - q))
    sbj = round(100 * (obs - exp), 6)                 # strikezone_ball_judgment()
    za  = round(100 * J.mean(), 6)                    # zone_awareness()
    max_diff = max(max_diff, abs(sbj - za))
    rows.append((name, len(idx), sbj, za, 100 * obs, 100 * exp))

print('max |SBJ - za_raw| @6dp', max_diff)            # -> 0.0

q300 = [r for r in rows if r[1] >= 300]
s = np.array([r[2] for r in q300])
o = np.array([r[4] for r in q300])
e = np.array([r[5] for r in q300])
print('qualified', len(q300))                         # -> 163
print('SBJ mean %.4f  sd(pop) %.4f  sd(sample) %.4f  min %.3f  max %.3f'
      % (s.mean(), s.std(ddof=0), s.std(ddof=1), s.min(), s.max()))
#   -> SBJ mean -0.4931  sd(pop) 2.8890  sd(sample) 2.8979  min -8.338  max 5.775
print('observed %.2f (sd %.2f) / expected %.2f (sd %.2f)'
      % (o.mean(), o.std(ddof=0), e.mean(), e.std(ddof=0)))
#   -> observed 68.08 (sd 3.09) / expected 68.58 (sd 0.98)

q300.sort(key=lambda r: -r[2])
print('TOP5', [(r[0], r[2], r[1]) for r in q300[:5]])
print('BOT5', [(r[0], r[2], r[1]) for r in q300[-5:]])
print('all-batter mean SBJ %.4f' % np.mean([r[2] for r in rows]))   # -> -1.2777
```

---

## 7. 검토자에게 묻는 질문

답이 **판단으로 나오는** 형태로만 적었습니다.

**Q1 (동일성 — 가장 중요).**
SBJ는 `za_raw`와 대수적으로 동일함이 증명·실측되었습니다(max diff 0.0). 그럼에도 `sbj`,
`judgment_accuracy_pct`(68.08%), `expected_judgment_accuracy_pct`(68.58%)를 별도 필드로 노출하는 것이
정당합니까, 아니면 `za_raw`의 재명명에 불과하므로 **SBJ 필드를 삭제하고 두 구성요소만 노출**해야 합니까?
둘 중 하나를 고르고 근거를 주십시오.

**Q2 (구성요소의 독립 가치).**
동일한 SBJ = −0.5 pp를 가진 두 타자가 (관측 65% / 기대 65.5%)와 (관측 72% / 기대 72.5%)로 갈릴 때,
이 분해가 야구 해석상 **실제로 의미 있는 추가 정보**입니까? 아니면 기대 정확도는 상대 투수의
투구 구성(pitch mix)만 반영하므로 타자 평가에는 잡음입니까?

**Q3 (평균이 0이 아닌 문제).**
자격 타자 163명 평균 SBJ = **−0.4931 pp**, 전체 285명 평균 −1.2777 pp, 투구 가중 −0.2726 pp입니다.
`p_swing`이 리그 평균 정책이라면 이 중 어느 값이 0이어야 한다고 보십니까?
그리고 투구 가중조차 0이 아닌 것이 (a) 3-블록 날짜 교차적합의 **정상적 귀결**입니까,
(b) isotonic calibration의 부작용입니까, (c) `(2q−1)` 가중과 스윙 편차의 상관 때문입니까,
(d) `p_zone`의 하향 편향(Q5) 때문입니까, 아니면 (e) **버그를 의심해야 하는 신호**입니까?
검증 우선순위를 매겨 주십시오.

**Q4 (`p_zone`의 외삽).**
`p_zone`은 **테이크 투구만으로 학습**되어 스윙 투구에 외삽됩니다. 스윙 투구는 존 중앙에 치우쳐 분포하므로
공변량 이동이 있습니다. 이 외삽이 SBJ를 체계적으로 왜곡합니까? 왜곡한다면 방향(스윙 잘하는 타자에게 유리/불리)은
어느 쪽입니까? 그리고 이를 교정할 실무적 대안(예: 규칙 기반 기하학적 존, propensity weighting, 판정이
관측된 표본으로의 제한)이 있습니까?

**Q5 (존 경계 계통 오차의 전파).**
아래 8.2절에 기술된 편향 — 규칙 기반 존이 실제 ABS 존보다 **좁게** 추정된다는 보고 —
이 SBJ에 전파되는 방향을 예측해 주십시오. 특히 "존 가장자리를 지켜본 타자"와
"존 가장자리에 스윙한 타자" 중 누가 부당하게 손해를 봅니까?
그리고 경험적 버퍼 적합(규칙 명세 미확인)을 `p_zone` 모델에 반영하는 것이 정당합니까,
아니면 **규칙 명세를 확인하기 전까지는 미보정 상태로 두고 한계로만 기록**해야 합니까?

**Q6 (신뢰도 측정 설계).**
SBJ의 신뢰도는 아직 측정되지 않았습니다(U1). 측정한다면 분할 방식은
odd-even 투구 / 무작위 투구 / 경기 단위 무작위 / 시간순 중 어느 것을 권장합니까?
투구 단위 자기상관(같은 타석·같은 투수)을 고려할 때 Spearman-Brown 환산이 타당합니까,
아니면 경기 단위 클러스터 부트스트랩 같은 다른 방법을 써야 합니까?

**Q7 (동일성 하의 신뢰도 보고).**
SBJ ≡ `za_raw`이므로 두 지표의 신뢰도는 **같은 수치일 수밖에 없습니다.**
그렇다면 5.4절 대장에서 SBJ와 ZA를 별도 행으로 두는 것 자체가 오해를 부릅니까?
두 행을 병합해야 합니까, 아니면 "동일 지표의 두 표기"라는 각주로 충분합니까?

**Q8 (자격 기준).**
자격 기준 300구는 자격 타자 표준편차 2.889 pp에 비해 충분합니까?
최하위 3명(김동헌 301구, 김헌곤 302구, 이지영 386구)은 표본 하한 근처에 몰려 있습니다.
이것이 우연입니까, 아니면 소표본에서 SBJ가 음수로 끌리는 계통적 현상을 시사합니까?
(전체 285명 평균이 −1.28로 자격 타자 평균보다 더 음수라는 사실을 함께 고려해 주십시오.)

---

## 8. 알려진 한계 (과장 금지)

### 8.1 모델이 스스로 선언한 한계 (`LIMITATIONS` 원문)

```
1. 리그 평균 실행 능력을 기준으로 추정한 의사결정 가치이며 개인별 최적 판단의 정답이 아닙니다.
2. 관측하지 못한 반대 행동과 누락된 투구 특성에 따른 선택 편향이 남습니다. 실제 타구속도·발사각·
   해당 투구의 안타/홈런은 판단 점수의 입력이 아닙니다.
3. 시즌 표시값은 날짜 블록 교차적합으로 해당 경기 결과를 제외하지만 다른 블록의 미래 경기를 사용할 수
   있습니다. 순수한 사전 예측 성능은 별도 시간 분리 평가에서 확인합니다.
4. 표본 부족 구간은 상위 조건의 결과 분포로 완화합니다. 반대 선택의 정확성과 누락된 실행 능력·
   번트 의도의 영향까지 검증된 것은 아닙니다.
```

추가로 모델 문서에 기록된 사항:

- 여섯 사건 분류(Whiff/Foul/InPlay/Ball/CalledStrike/HBP)로는 **낫아웃(dropped third strike),
  번트 파울, 비접촉 투구에서의 주자 이동, 기록되지 않은 의도**를 완전히 구분할 수 없습니다.
- 자격 타자의 95% 구간은 **예측값을 고정한 채** 1,000회 경기 단위 클러스터 부트스트랩으로 만듭니다.
  모델 불확실성과 식별되지 않은 counterfactual 편향은 포함되지 않습니다.
- 순위는 **점추정 순서**이며 우월성이 확립된 것이 아닙니다.
- 고정 버전(`constraints-za.txt`)은 drift를 줄이지만 **플랫폼 간 비트 단위 동일성은 보장하지 않습니다.**

### 8.2 `p_zone` 존 경계 모델의 알려진 계통 오차 — 미검증 항목

다음 수치는 **호출 측이 보고한 진단 결과**이며, **저장소 안에 산출 스크립트나 기록 문서가 없습니다.**
(본 문서 작성 중 `analysis/`, `docs/`, `data/processed/`를 검색해 해당 수치의 기록을 찾지 못했습니다.)
따라서 아래는 **미검증 보고**로 읽어야 합니다.

- 2026 무작위 40경기의 콜 볼/스트라이크 **6,945개**에 대해, 정규화 거리 `d = max(|x|,|z|) ≤ 1`
  규칙으로 존 통과를 판정했을 때 **잔차(불일치) 4.87%**.
- 잔차 **338건 중 298건(88.2%)** 이 "규칙은 볼인데 실제는 콜 스트라이크" 방향
  → **규칙 존이 실제보다 좁습니다.**
- 3-파라미터 버퍼 적합(x 방향 +0.05 ft, 상한 +0.12 ft, 하한 +0.02 ft)으로 잔차 **1.77%** 까지 감소.
- 그러나 **실제 KBO ABS 규칙 명세**(공 반지름 버퍼를 적용하는지, 상·하한을 무엇으로 정의하는지)를
  저장소에서 확인할 수 없습니다. 따라서 이 버퍼는 **경험적 최적화이지 규칙 재현이 아닙니다.**
- **이 편향이 SBJ 값에 어떻게 전파되는지는 측정하지 않았습니다.**

참고로 `p_zone`은 위 `d ≤ 1` 규칙을 직접 쓰지 않고 학습된 분류기입니다. 학습 라벨이 실제 콜이므로
분류기는 원리적으로 실제 존을 학습할 수 있습니다. 다만 입력 좌표가 `d ≤ 1`을 전제로 정규화된 값이고,
스윙 투구에는 외삽이 일어나므로(Q4) 편향이 사라진다는 보장은 없습니다. **측정되지 않았습니다.**

### 8.3 프로젝트 전반의 표현 규칙 (이 문서도 준수)

- **BAA**(이 저장소의 타구 관련 실험 지표)는 KBO 공개 데이터에 적용한 **실험 지표**이며,
  **MLB Statcast와 상호 비교할 수 없습니다.**
- **기존 Decision Run**은 실제 선택 결과가 섞인 **진단값**이므로, counterfactual **Decision Value로 부르지 않습니다.**
- **plate discipline 클러스터 번호는 우열 등급이 아닙니다.** 유형 라벨일 뿐입니다.
- **신뢰도 수치는 측정 길이를 반드시 병기**하고, **원값과 환산값을 하나의 숫자로 뭉치지 않습니다**(5.4절).
- 시즌을 섞지 않습니다. 연도별 Run Value와 리그 평균은 해당 시즌 데이터만으로 계산합니다.
- 표본 미달을 숨기지 않고 표시합니다(자격 기준 300구).

### 8.4 이 문서가 주장하지 않는 것

- SBJ가 기존 지표보다 **낫다**는 주장을 하지 않습니다. 대수적으로 동일하기 때문입니다.
- SBJ의 **신뢰도·예측력·타 지표 대비 우위**를 주장하지 않습니다. 측정하지 않았습니다.
- 4절 상·하위 명단이 **타자 능력의 확정 순위**라는 주장을 하지 않습니다. 진행 중 시즌의 점추정입니다.
- 2026 시즌은 **2026-09-12까지의 부분 시즌**(626경기)이며 완결된 시즌이 아닙니다.
