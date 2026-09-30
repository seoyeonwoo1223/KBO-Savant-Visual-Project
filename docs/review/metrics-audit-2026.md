# SBJ · APR+ · DV 외부 감사 요청서 — 2026 KBO

이 문서는 저장소에 접근할 수 없는 외부 검토자가 **이 문서 하나만 읽고** 판단할 수 있도록 작성되었습니다.
필요한 코드·수치·한계는 전부 본문 안에 인용되어 있습니다. 외부 링크나 저장소 파일 참조로 내용을 대신하지 않았습니다.

대상 지표는 세 개입니다.

- **SBJ** (Strikezone-Ball Judgment) — 스트라이크/볼 판단 정확도의 리그 기준 대비 초과분
- **APR+** (Area-weighted Plate Recognition Plus) — 구역별 SBJ를 **리그 고정 구역 비중**으로 재합성한 뒤 표준화한 값
- **DV / DV+** (Decision Value) — 스윙/테이크 선택의 기대 득점가치 차이를 누적한 별개 지표군

---

## 0. 저장소 상태 (재현 기준점)

| 항목 | 값 |
|---|---|
| 저장소 경로 | `/home/user/KBO-Savant-Visual-Project` |
| 브랜치 | `claude/happy-hopper-g1h339` |
| 기준 커밋 | **`68688f92`** — "APR+: 구역별 판단을 리그 고정 가중치로 재합성" |
| 직전 커밋 | `df345e75` — "SBJ: 기대 대비 스트라이크/볼 판단 정확도를 선수 단위로 노출" |
| 워킹 트리 | 깨끗함 (푸시 완료). 본 문서 작성 시점에 추적 파일 변경 없음 |
| 실행 환경 | Python 3.12, `.venv/`에 `requirements.txt` + `constraints-za.txt` 고정 버전 설치 |
| 고정 패키지 | numpy 2.5.3, pandas 2.3.3, pyarrow 19.0.1, scikit-learn 1.9.0, scipy 1.18.1 |
| 필수 환경변수 | `PYTHONPATH=src` (권장 `OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2`) |

> 이 문서는 커밋 `df345e75` 기준으로 작성된 이전 SBJ 단독 검토 요청서를 흡수·갱신한 것입니다.
> 이전 문서는 저장소에 그대로 남아 있으나, **본 문서는 그것을 읽지 않아도 자립합니다.**
> 이전 문서의 모든 커밋 SHA 표기(`df345e75`)는 본 문서에서 `68688f92` 기준으로 재측정·갱신되었습니다.

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
이 점은 뒤에 나오는 "존 경계 모델의 계통 오차"(10.2절) 쟁점의 전제입니다.

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
| **구역(region)** | 정규화 거리 `d = max(|x_rel|, |z_rel|)` 기준 5개 구간: heart / shadow_in / shadow_out / chase / waste. 정의는 4.1절. |
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

```python
def _relative_location(row):
    px, pz, top, bottom = (_number(row.get(key)) for key in ("px", "pz", "sz_top", "sz_bottom"))
    if None in (px, pz, top, bottom) or top <= bottom:
        return None
    return px / PLATE_HALF_WIDTH_FT, (pz - (top + bottom) / 2) / ((top - bottom) / 2)
```

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
    dates=np.array(sorted({r['game_id'][:8] for r in rows})); result=[]; fold_meta=[]
    for fold,block in enumerate(np.array_split(dates,CROSSFIT_FOLDS)):
        held=set(block)
        train=[r for r in rows if r['game_id'][:8] not in held]
        test =[r for r in rows if r['game_id'][:8] in held]
        pred=fit_predict(train,test,**settings)
        pzone=old.predict_pzone(train,test)
        action=np.array([r['decision_type']=='Swing' for r in test],dtype=int)
        values=pred[selected]; dv=decision_value(action,values[:,1],values[:,0])
        for i,r in enumerate(test):
            r.update({'swing':int(action[i]),'p_swing':float(pred['p'][i]),'p_zone':float(pzone[i]),
                      'judgment':float((action[i]-pred['p'][i])*(2*pzone[i]-1)),
                      'v_swing':float(values[i,1]),'v_take':float(values[i,0]),
                      'delta_v':float(values[i,1]-values[i,0]),'dv':float(dv[i]), ...})
```

**주의**: 블록 제외는 "자기 경기 결과로 자기를 채점하지 않는다"는 보장일 뿐, 다른 블록이 **미래 날짜**일 수 있습니다.
시즌 표시값은 **사후(retrospective) 추정치이지 사전 예측 성능이 아닙니다.**

`support_prior=50`은 `p_zone`/`p_swing`이 아니라 **사건 확률(event probability)과 값 모델**에 적용되는 축소 계수입니다.
표본이 희박한 구간에서 학습 데이터만으로 만든 (카운트 × 구역 × 구종 × 스탠스) 사전분포 쪽으로 `n/(n+50)` 가중으로
당깁니다. 근방(neighborhood)은 정규화 좌표 0.5단위 격자, 볼카운트, 구종, 스탠스, 10 km/h 구속 구간,
10 cm 움직임 구간으로 정의됩니다. SBJ/APR 자체의 계산에는 직접 관여하지 않지만, **DV의 값 모델에는 직접 관여합니다**(5절).

---

## 2. 자격 투구(eligible pitch)의 정의 — 세 지표 공통 분모

세 지표는 모두 같은 투구 집합 위에서 계산됩니다. 그 집합을 결정하는 코드 전문입니다.

```python
def _action(row):
    """Classify the source call once, including terminal HBP as a take."""
    code = str(row.get("pitch_call_code") or "").upper()
    if code in {"S", "F", "X"}:
        return "Swing"
    if code in {"B", "T"} or (row.get("is_pa_terminal") and str(row.get("pa_type") or "").lower() == "hbp"):
        return "Take"
    return None


def _eligible(row):
    if row.get("parse_status") != "ok" or _action(row) is None or _relative_location(row) is None:
        return False
    before, after = _state(row, "before"), _state(row, "after")
    return bool(before and after and before[1] < 3)
```

지표 모듈의 행 적재는 이 함수를 그대로 씁니다.

```python
from .swing_take import _eligible, _relative_location, _state

def load_rows(root, season):
    rows=load_curated_rows(root,'pitches',season)
    events=load_curated_rows(root,'events',season)
    rows,quality=reliable_halves(rows,events)
    valid, excluded = [], Counter()
    for r in rows:
        if not _eligible(r) or not r.get('batter_id') or not r.get('batter_name') or outcome(r) is None:
            excluded['invalid_state_location_action_or_identity'] += 1
            continue
        r['x_relative'], r['z_relative'] = _relative_location(r)
        r['decision_type'] = 'Swing' if outcome(r) in EVENTS[:3] else 'Take'
        r['region'] = region(r)
        valid.append(r)
```

따라서 **자격 투구는 정의상 "스윙 또는 테이크로 분류된 투구"뿐이며 제3의 범주가 존재하지 않습니다.**
`_action()`이 `None`을 반환하는 행은 `_eligible()`에서 이미 탈락합니다. 이 사실은 5.3절의 DV 분모 쟁점에서 결정적입니다.

`reliable_halves()`는 그 위에 한 층을 더 겁니다: 득점 시점이 확정되지 않은 이닝 반쪽을 통째로 제외합니다.
정책 문자열 원문은 `'Unresolved scoring halves are excluded; incomplete innings do not train RE. No invented scoring timestamps.'` 입니다.

---

## 3. SBJ 정의와 산식

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

### 3.1 핵심 쟁점 — SBJ와 `za_raw`의 대수적 동일성

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

**실데이터 확인 (검증됨).** 2026 시즌 전체 자격 투구 **192,526구 / 타자 285명**에 대해 저장된
`p_swing`·`p_zone`·`swing`으로 SBJ와 `za_raw`를 각각 독립 재계산했습니다.

- 보고 정밀도(소수 6자리 반올림) 기준 **max |SBJ − za_raw| = 0.0** (285명 전원)
- 반올림 전 배정도 부동소수 기준 **max |SBJ − za_raw| = 3.02 × 10⁻¹⁴** (부동소수 누산 오차 수준)

**테스트로 고정된 사항.**

```python
def test_sbj_equals_zone_awareness_and_is_not_independent_evidence():
 # SBJ reduces to (S - p_swing) * (2*p_zone - 1), so it must track za_raw exactly.
 rng=np.random.default_rng(11)
 for _ in range(20):
  items=[_judgment_row(int(rng.integers(0,2)),float(rng.uniform(.05,.95)),float(rng.uniform(.05,.95)))
    for _ in range(rng.integers(5,60))]
  assert strikezone_ball_judgment(items)==zone_awareness(items)
```

저장소의 현재 입장은 다음과 같습니다.

> SBJ는 `za_raw`와 대수적으로 동일하다. 별도 필드로 두는 이유는 **구성요소(관측 정확도 68.08%,
> 기대 정확도 68.58%)를 감사 가능하게 분리 노출**하기 위함이며, SBJ와 `za_raw`를 **두 개의 독립 증거로
> 인용하는 것은 금지**한다.

---

## 4. APR+ 정의와 산식 (커밋 `68688f92`에서 신규)

### 4.1 구역 정의

투구 위치의 정규화 거리 `d = max(|x_relative|, |z_relative|)`로 다섯 구역을 나눕니다.
경계는 **하드코딩된 고정 상수**입니다.

```python
REGIONS = ('heart', 'shadow_in', 'shadow_out', 'chase', 'waste')

def region(row):
 d = max(abs(row['x_relative']), abs(row['z_relative']))
 return 'heart' if d <= 2/3 else 'shadow_in' if d <= 1 else 'shadow_out' if d <= 4/3 else 'chase' if d <= 2 else 'waste'
```

| 구역 | 조건 | 의미 |
|---|---|---|
| `heart` | `d ≤ 2/3` | 존 중앙 |
| `shadow_in` | `2/3 < d ≤ 1` | 존 안쪽 가장자리 |
| `shadow_out` | `1 < d ≤ 4/3` | 존 바로 바깥 |
| `chase` | `4/3 < d ≤ 2` | 유인구 영역 |
| `waste` | `d > 2` | 크게 벗어난 공 |

`d ≤ 1`이 존 안쪽입니다. 즉 `heart + shadow_in`이 존, `shadow_out` 이상이 존 밖입니다.

### 4.2 구역별 SBJ와 APR 합성

선수 요약 함수가 구역별로 SBJ를 따로 계산해 `{구역}_sbj` 필드로 남깁니다.

```python
 for reg in REGIONS:
  selected=[r for r in items if r['region']==reg]
  s[reg+'_pitches']=len(selected); s[reg+'_raw_dv']=r6(sum(r['dv'] for r in selected))
  s[reg+'_decision_value_per_100']=r6(100*sum(r['dv'] for r in selected)/n)
  s[reg+'_sbj']=strikezone_ball_judgment(selected)
```

리그 구역 비중은 **모든 자격·비자격 타자의 투구를 합산한 시즌 내부 비율**입니다.

```python
def region_weights(players):
 """League share of eligible pitches per region; the fixed APR weighting."""
 totals={reg:sum(p[reg+'_pitches'] for p in players) for reg in REGIONS}
 grand=sum(totals.values())
 return {reg:(totals[reg]/grand if grand else 0) for reg in REGIONS}
```

APR과 APR+의 합성은 다음과 같습니다 (docstring 포함 전문 인용).

```python
def add_apr_plus(players,weights):
 """APR: region SBJ recombined on league region shares instead of the hitter's own.

 Using the hitter's own shares would reproduce sbj exactly; league shares are
 what make APR a different statistic. Regions the hitter never saw carry no
 SBJ, so the remaining weights are renormalized rather than treated as zero.
 """
 for p in players:
  seen=[reg for reg in REGIONS if p[reg+'_sbj'] is not None]
  total=sum(weights[reg] for reg in seen)
  p['apr_raw']=r6(sum(weights[reg]*p[reg+'_sbj'] for reg in seen)/total) if total else None
 qualified=np.array([p['apr_raw'] for p in players if p['qualified_300'] and p['apr_raw'] is not None],dtype=float)
 center=float(qualified.mean()) if len(qualified) else 0
 spread=float(qualified.std()) if len(qualified) else 0
 for p in players:
  p['apr_plus']=r6(100+15*(p['apr_raw']-center)/spread) if spread and p['apr_raw'] is not None else None
 return center,spread
```

수식으로 쓰면, 타자 $i$가 실제로 본 구역 집합을 $R_i$라 할 때

$$
\mathrm{APR}_i = \frac{\sum_{r \in R_i} w_r \cdot \mathrm{SBJ}_{i,r}}{\sum_{r \in R_i} w_r},
\qquad
\mathrm{APR+}_i = 100 + 15 \cdot \frac{\mathrm{APR}_i - \mu}{\sigma}
$$

- $w_r$ = 리그 구역 비중 (모든 타자에게 동일)
- $\mu, \sigma$ = **자격 타자(300구 이상)** 의 APR 평균과 **모표준편차(`numpy.std` 기본값, ddof=0)**

**중요한 구현 세부 두 가지 (직접 코드로 확인):**

1. **표준편차 자유도는 ddof=0입니다.** `np.ndarray.std()`의 기본값이 `ddof=0`이므로 모표준편차입니다.
   표본표준편차(ddof=1)가 아닙니다. 아래 실측표에서도 두 값을 분리해 실었습니다.
2. **APR+는 자격 타자만으로 중심·산포를 잡지만, 값 자체는 비자격 타자에게도 부여됩니다.**
   `spread`가 0이 아닌 한 `p['apr_plus']`는 `apr_raw`가 있는 모든 선수에게 계산됩니다.
   따라서 "APR+ 100 = 자격 타자 평균"이며 비자격 타자의 APR+는 자격자 분포 위에서 외삽된 값입니다.

### 4.3 핵심 설계 논점 — 왜 리그 가중치여야만 하는가

타자 자신의 구역 비중 $\hat{w}_{i,r} = n_{i,r}/n_i$ 를 쓰면, 구역별 SBJ의 정의상

$$
\sum_r \frac{n_{i,r}}{n_i}\,\mathrm{SBJ}_{i,r} = \mathrm{SBJ}_i
$$

가 **항등적으로** 성립합니다(SBJ가 투구별 항의 단순 평균이므로 구역 분할 후 재가중이 원래 평균을 복원).
즉 **고정 리그 가중치가 APR을 SBJ와 다른 통계량으로 만드는 유일한 요소**입니다.
코드 docstring도 이 점을 명시합니다: *"Using the hitter's own shares would reproduce sbj exactly."*

따라서 APR의 해석은 **"모든 타자를 동일한 투구 위치 분포 위에서 채점한 SBJ"** 입니다.
자기 구역 비중이 리그와 비슷한 타자일수록 APR ≈ SBJ가 되고, 편중된 타자만 갈립니다.
이것이 4.5절에서 corr = 0.995가 나오는 구조적 이유입니다.

### 4.4 계약 문자열 원문

```
'apr_raw': 'sum over the five regions of (league region share) * (that region SBJ for this hitter);
            percentage points. Fixed league weights replace the own region mix of the hitter, so two
            hitters are scored on the same pitch distribution. Weights are renormalized over the regions
            the hitter actually saw. Weighting by the own shares of the hitter would collapse this back to sbj.'
'apr_plus': '100 + 15 * (apr_raw - qualified mean) / qualified population standard deviation'
'region_weights': 'league share of eligible pitches per region for the season; identical for every hitter'
```

### 4.5 테스트로 고정된 사항 — APR 테스트는 **정확히 4개**

`tests/test_zone_decision.py` 안에서 이름에 `apr`가 들어간 테스트는 4개이며, 네 개 모두 APR 값을 직접 단언합니다
(SBJ 때와 달리 "경로만 지나는" 테스트를 세어 4를 맞춘 것이 아닙니다).

```python
def test_apr_uses_league_region_weights_not_the_hitters_own_mix():
 # Same per-region judgment, different region mix: SBJ differs, APR does not.
 shape={'heart':(1,.4,.6),'shadow_in':(1,.4,.6),'shadow_out':(1,.4,.6),'chase':(1,.4,.6),'waste':(1,.4,.6)}
 a=_apr_rows('1',{r:(40 if r=='heart' else 10,*v) for r,v in shape.items()})
 b=_apr_rows('2',{r:(10 if r=='heart' else 40,*v) for r,v in shape.items()})
 players=[profile_summary(a),profile_summary(b)]
 weights=region_weights(players)
 assert abs(sum(weights.values())-1)<1e-12
 add_apr_plus(players,weights)
 # Every region carries the same SBJ here, so APR must agree across the two mixes.
 assert players[0]['apr_raw']==players[1]['apr_raw']


def test_apr_differs_from_sbj_when_region_judgment_varies():
 # Good in the heart, poor on the edges, and a heart-heavy personal mix.
 rows=_apr_rows('1',{'heart':(60,1,.3,.9),'shadow_in':(10,1,.7,.2),'shadow_out':(10,1,.7,.2),
   'chase':(10,1,.7,.2),'waste':(10,1,.7,.2)})
 other=_apr_rows('2',{r:(20,1,.5,.5) for r in REGIONS})
 players=[profile_summary(rows),profile_summary(other)]
 add_apr_plus(players,region_weights(players))
 # League weights down-weight the hitter's oversized heart share, so APR < SBJ.
 assert players[0]['apr_raw']!=players[0]['sbj']
 assert players[0]['apr_raw']<players[0]['sbj']


def test_apr_renormalizes_over_regions_the_hitter_saw():
 seen=_apr_rows('1',{'heart':(20,1,.4,.7),'shadow_in':(20,1,.4,.7)})
 full=_apr_rows('2',{r:(20,1,.4,.7) for r in REGIONS})
 players=[profile_summary(seen),profile_summary(full)]
 add_apr_plus(players,region_weights(players))
 # Unseen regions are dropped, not scored as zero, so equal judgment gives equal APR.
 assert players[0]['apr_raw'] is not None
 assert abs(players[0]['apr_raw']-players[1]['apr_raw'])<1e-6


def test_apr_plus_is_standardized_over_qualified_hitters():
 players=[]
 for i in range(4):
  rows=_apr_rows(str(i),{r:(80,1,.4,.5+.08*i) for r in REGIONS})
  players.append(profile_summary(rows))
 center,spread=add_apr_plus(players,region_weights(players))
 assert all(p['qualified_300'] for p in players)
 for p in players:
  assert abs(p['apr_plus']-(100+15*(p['apr_raw']-center)/spread))<1e-5
```

**이 4개가 고정하는 것 / 고정하지 않는 것**

| 고정하는 것 | 고정하지 않는 것 |
|---|---|
| 리그 가중치 합 = 1 | 실데이터에서 APR과 SBJ의 상관 수준 |
| 구역별 SBJ가 모두 같으면 개인 구역 편중과 무관하게 APR 동일 | 구역 경계 상수(2/3, 1, 4/3, 2)의 타당성 |
| 구역별 SBJ가 다르면 APR ≠ SBJ이고, heart 편중 타자는 APR < SBJ | 재정규화가 리그 평균 대입보다 옳다는 것 |
| 미관측 구역은 0이 아니라 **가중치에서 제외 후 재정규화** | 시즌 간 비교 가능성 |
| APR+ = 100 + 15·(APR − 중심)/산포 가 자격자 기준으로 계산됨 | APR+의 신뢰도·재현성 |

---

## 5. DV / DV+ 정의와 산식

### 5.1 정의

DV는 SBJ·APR과 **완전히 다른 축**입니다. 판단의 "정확도"가 아니라 **선택의 기대 득점가치 차이**를 누적합니다.

```python
def decision_value(swing, swing_value, take_value):
 delta=np.asarray(swing_value)-np.asarray(take_value)
 return np.where(np.asarray(swing),delta,-delta)
```

즉 투구별 DV는

$$
\mathrm{dv} = \begin{cases} V_{\text{swing}} - V_{\text{take}} & \text{스윙했을 때} \\ V_{\text{take}} - V_{\text{swing}} & \text{지켜봤을 때}\end{cases}
$$

"내가 고른 쪽의 기대가치가 고르지 않은 쪽보다 얼마나 높았는가"입니다.
$V_{\text{swing}}, V_{\text{take}}$ 는 선택된 값 모델(`selected='staged'`)의 행동별 기대 득점가치입니다.

`staged` 값 모델은 여섯 사건(Whiff/Foul/InPlay/Ball/CalledStrike/HBP) 확률에 사건별 run value를 곱해 합산합니다.
InPlay(ev==2)만 별도로 카운트·주자아웃 상태 사전분포로 후퇴(back-off)하는 회귀값을 씁니다.

```python
 for ev in indices:
  em = events==ev
  if ev!=2:
   values=np.array([re.event_value(_state(r,'before'),EVENTS[ev]) for r in test])
   staged[:,act]+=probs[:,ev]*values
   continue
  # InPlay: event x count x base/out -> event x count -> event 로 후퇴하는 사전분포와
  # 국소 회귀를 n/(n+50) 가중으로 혼합
  cm={k:(sum(v)+50*global_mean)/(len(v)+50) for k,v in by_count.items()}
  sm={k:(sum(v)+50*cm[k[2:]])/(len(v)+50) for k,v in by_state.items()}
  ...
  staged[:,act]+=probs[:,ev]*values
```

값 모델은 60/20/20 날짜 분할(개발 / 검증 / 최종 미접촉 테스트)로 고정되며,
선택 규칙 원문은 다음과 같습니다.

```
'selection_rule': '60/20/20 dates: development diagnostics, then final evaluation with frozen algorithm.
                   Each fit selects optional calibration using only training-game OOF probabilities.
                   Final 20% never selects settings. Direct and unpooled RVs are diagnostic baselines.'
'counterfactual_validation': 'Observed-action errors and conditional intervals do not identify
                              unobserved opposite-action outcomes.'
```

2026 시즌 산출물에서 `selected = "staged"` 임을 확인했습니다.

### 5.2 선수 단위 집계

```python
 total=sum(r['dv'] for r in items)
 s={... 'dv_per_100':r6(100*total/n),'raw_dv':r6(total), ...}   # n = len(items) = 그 타자의 자격 투구 수


def add_dv_plus(players):
 qualified=np.array([p['dv_per_100'] for p in players if p['qualified_300']],dtype=float)
 center=float(qualified.mean()) if len(qualified) else 0
 spread=float(qualified.std()) if len(qualified) else 0
 for p in players: p['dv_plus']=r6(100+15*(p['dv_per_100']-center)/spread) if spread else (100 if p['qualified_300'] else None)
 return center,spread
```

계약 문자열 원문:

```
'raw_dv': 'sum(V_swing - V_take for swings; sign reversed for takes); cumulative runs'
'dv_per_100': '100 * raw_dv / eligible pitches; runs per 100 pitches'
'dv_plus': '100 + 15 * (dv_per_100 - qualified mean) / qualified population standard deviation'
```

DV+ 역시 **ddof=0 모표준편차**이고, 자격자 기준 중심·산포를 비자격 타자에게도 적용합니다(4.2절과 동일 구조).

### 5.3 DV 분모 쟁점 — 지시된 조정이 **이미 적용된 상태였음**

이 감사 요청의 계기 중 하나는 "DV의 분모를 판단 대상 투구로 좁혀야 한다"는 지적이었습니다.
**코드와 데이터를 대조한 결과 이 조정은 이미 적용되어 있었고, 따라서 코드를 변경하지 않았습니다.** 근거는 셋입니다.

1. `zone_decision.load_rows()`는 `swing_take._eligible()`을 그대로 임포트해 씁니다(2절 인용).
   이 함수는 `_action(row) is not None`을 요구하므로, 스윙/테이크로 분류되지 않는 투구는 애초에 들어오지 않습니다.
2. 2026 ZA 입력 행수 **192,526행** = `data/metrics/swing_take/2026/decision_pitches.parquet`의 **192,526행** (일치).
3. 그 192,526행은 **Swing 86,007 / Take 106,519**로 정확히 양분되며 제3 범주가 0입니다(86,007 + 106,519 = 192,526).

따라서 `dv_per_100 = 100 × raw_dv / n`의 분모 `n`은 **이미 판단 대상 투구 수**입니다.
"모든 투구"와 "판단 대상 투구"가 이 파이프라인에서는 같은 집합이라, 좁힐 여지가 없습니다.

남는 해석 쟁점은 따로 있습니다: 분모에 **테이크도 포함**된다는 점입니다.
즉 `dv_per_100`은 "스윙 결정당 가치"가 아니라 "본 공 100개당 누적 판단 가치"입니다.
공을 많이 보는 타자와 적게 보는 타자의 분모 성격이 같지 않다고 볼 여지가 있으며, 이 점은 검토 질문 Q11에 넣었습니다.

### 5.4 DV를 counterfactual Decision Value로 부르지 않는 이유

이 저장소의 표현 규칙입니다. **기존 Decision Run은 실제 선택 결과가 섞인 진단값이므로
counterfactual Decision Value로 부르지 않습니다.** DV는 관측된 행동의 결과와 모델이 추정한
반대 행동의 기대값을 함께 쓰는데, **반대 행동의 결과는 관측되지 않았고 식별되지도 않습니다.**
모델 자신의 선언 원문:

```
'counterfactual_validation': 'Observed-action errors and conditional intervals do not identify
                              unobserved opposite-action outcomes.'
```

---

## 6. 2026 실측 결과 (검증됨 — 커밋 `68688f92`에서 직접 재계산)

### 6.1 데이터 범위

`data/curated/summary.json` 기준 (2026-09-13 생성, 2026 시즌 진행 중 스냅샷):

| 시즌 | 경기 | pitches 행 | events 행 | 날짜 범위 |
|---|---|---|---|---|
| 2022 | 720 | 217,025 | 273,038 | 2022-04-02 ~ 2022-10-11 |
| 2023 | 720 | 219,839 | 276,161 | 2023-04-01 ~ 2023-10-17 |
| 2024 | 720 | 223,216 | 280,544 | 2024-03-23 ~ 2024-10-01 |
| 2025 | 720 | 217,852 | 277,384 | 2025-03-22 ~ 2025-10-04 |
| **2026** | **626** | **192,712** | 245,246 | 2026-03-28 ~ 2026-09-12 |

**세 지표 계산에 실제로 들어간 것은 2026 시즌뿐**이며, 위 192,712구 중 자격 필터를 통과한
**192,526구 / 타자 285명**입니다(차이 186구는 제외된 이닝 반쪽·자격 미달 투구).

- 자격 기준(300구 이상)을 채운 타자: **163명**
- 행동 분할: Swing **86,007** / Take **106,519**

### 6.2 리그 구역 가중치 (2026 시즌 내부에서 산출)

| 구역 | 투구 수 | 가중치 $w_r$ |
|---|---|---|
| heart | 45,736 | **0.2376** |
| shadow_in | 40,670 | **0.2112** |
| shadow_out | 36,704 | **0.1906** |
| chase | 45,290 | **0.2352** |
| waste | 24,126 | **0.1253** |
| 합 | 192,526 | 1.0000 |

가중치 범위가 **0.125 ~ 0.238**로, 균등(0.2)에서 크게 벗어나지 않습니다.
`waste`만 절반 수준이고 나머지 넷은 0.19~0.24 구간에 몰려 있습니다. 이 사실은 Q12의 근거입니다.

### 6.3 자격 타자 163명 기술통계 — SBJ와 APR 병기

| 값 | SBJ | APR |
|---|---|---|
| 평균 | **−0.4931 pp** | **−0.4427 pp** |
| 표준편차 (모집단, ddof=0 — 표준화에 실제 쓰이는 값) | **2.8890 pp** | **2.8658 pp** |
| 표준편차 (표본, ddof=1 — 참고용) | 2.8979 pp | 2.8746 pp |
| 최솟값 | **−8.338 pp** | **−8.338 pp** |
| 최댓값 | **+5.775 pp** | **+5.868 pp** |

판단 정확도 구성요소 (자격 타자 163명):

| 값 | 결과 |
|---|---|
| 관측 판단 정확도 평균 | **68.08 %** (sd 3.09, ddof=0) |
| 기대 판단 정확도 평균 | **68.58 %** (sd 0.98, ddof=0) |

참고값 (자격 조건 없이):

- 타자 285명 전원 단순평균 SBJ: **−1.2777 pp**, 같은 조건 APR: **−0.9791 pp**
- 투구 가중(192,526구 전체 풀링) SBJ: **−0.2726 pp**

DV (자격 타자 163명, `dv_per_100`, 단위 = 투구 100개당 run):

| 값 | 결과 |
|---|---|
| 평균 | **+6.0288** |
| 표준편차 (ddof=0) | **0.9317** |
| 표준편차 (ddof=1) | 0.9346 |
| 최솟값 / 최댓값 | **+3.588 / +8.028** |
| 투구 가중 전체 풀링 | +6.1273 |
| 285명 전원 단순평균 | +5.7061 |

**DV는 0 중심이 아닙니다.** 자격 타자 전원이 양수이며 평균 +6.03입니다.
이는 DV가 "리그 평균 대비 초과분"이 아니라 **선택한 행동과 반대 행동의 모델 기대값 차이의 누적**이기 때문입니다.
따라서 `dv_per_100`의 절대 수준에는 해석을 걸지 말고 **`dv_plus`(자격자 기준 표준화값)** 로만 비교해야 합니다.

### 6.4 APR과 SBJ의 관계 (핵심 실측)

자격 타자 163명 기준:

| 지표 | 값 |
|---|---|
| Pearson corr(APR, SBJ) | **0.9950** |
| Spearman corr(APR, SBJ) | 0.9958 |
| max &#124;APR − SBJ&#124; | **2.0475 pp** |
| mean &#124;APR − SBJ&#124; | **0.1669 pp** |
| 순위 변동 최대 | **20계단** |
| 순위 변동 평균 | **2.87계단** |
| 순위 무변동 인원 | **23명** / 163 |

즉 **APR은 SBJ와 거의 같은 값을 냅니다.** 대부분의 타자에서 차이는 0.17 pp 수준이고,
자격 타자 SBJ 표준편차(2.889 pp)와 비교하면 평균 차이는 0.06 표준편차에 불과합니다.
차이가 큰 극단 사례만 갈립니다.

APR − SBJ 차이 상위 5명:

| 타자 | APR | SBJ | APR − SBJ | 자격 투구 |
|---|---|---|---|---|
| 아데를린 | −5.157 | −7.205 | **+2.0475** | 464 |
| 홍창기 | +1.863 | +0.764 | +1.0983 | 2,161 |
| 권희동 | −2.402 | −3.339 | +0.9373 | 1,080 |
| 에레디아 | +5.868 | +5.023 | +0.8454 | 1,465 |
| 한석현 | +3.557 | +4.335 | −0.7778 | 486 |

### 6.5 구역별 리그 평균 SBJ (자격 타자 163명, 각 n=163)

| 구역 | 평균 구역 SBJ | sd (ddof=0) |
|---|---|---|
| heart | **+0.161 pp** | 6.925 |
| shadow_in | **−0.310 pp** | 6.500 |
| shadow_out | **−0.292 pp** | 4.765 |
| chase | **−1.133 pp** | 6.955 |
| waste | **−0.745 pp** | 4.215 |

다섯 구역 중 양수는 `heart` 하나뿐이고 `chase`가 가장 음수입니다.
구역 SBJ의 선수 간 산포(sd 4.2~7.0)가 전체 SBJ 산포(2.889)보다 훨씬 큽니다 —
구역별 값이 개별적으로는 매우 잡음이 크며, 합성 과정에서 상쇄된다는 뜻입니다.
**이 잡음 수준이 APR의 신뢰도에 미치는 영향은 측정되지 않았습니다.**

### 6.6 상·하위 표본 (APR 기준 정렬)

아래 선수 이름은 **KBO 공개 중계 데이터에 게재된 공개 정보**에서 온 것이며, 값은 진행 중인 2026 시즌의
부분 표본에 대한 추정치입니다. 순위는 점추정 순서일 뿐 우열이 확립된 것이 아닙니다.

| APR 순위 | 타자 | APR | APR+ | SBJ | SBJ 순위 | 자격 투구 |
|---|---|---|---|---|---|---|
| 1 | 에레디아 | +5.868 | 133.0 | +5.023 | 3 | 1,465 |
| 2 | 박건우 | +5.690 | 132.1 | +5.775 | 1 | 1,730 |
| 3 | 김도영 | +5.620 | 131.7 | +5.611 | 2 | 1,980 |
| 4 | 나성범 | +4.752 | 127.2 | +4.044 | 8 | 1,926 |
| 5 | 오명진 | +4.634 | 126.6 | +4.607 | 4 | 606 |
| … | | | | | | |
| 159 | 심우준 | −7.559 | 62.7 | −7.591 | 159 | 1,636 |
| 160 | 김태군 | −7.709 | 62.0 | −7.723 | 160 | 719 |
| 161 | 이지영 | −7.818 | 61.4 | −7.959 | 162 | 386 |
| 162 | 김동헌 | −7.938 | 60.8 | −7.925 | 161 | 301 |
| 163 | 김헌곤 | −8.338 | 58.7 | −8.338 | 163 | 302 |

상위 5명 중 SBJ 순위와 APR 순위가 어긋나는 사례가 3건 있으나(에레디아 3→1, 나성범 8→4),
하위 5명은 사실상 동일합니다.

### 6.7 반드시 짚어야 할 점 — 왜 자격 타자 평균이 0이 아닌가

`p_swing`이 리그 평균 스윙 정책이라면, 소박한 직관으로는 리그 전체 평균 SBJ가 0 근처여야 합니다.
실제 값은 **자격 타자 평균 −0.4931 pp**, 전체 타자 평균 −1.2777 pp, 투구 가중 −0.2726 pp로
**셋 다 음수이고 서로 다릅니다.** APR도 마찬가지로 −0.4427 / −0.9791 pp입니다.

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
  4. **`p_zone`의 계통 오차**(10.2절) — 존이 실제보다 좁게 추정되면 `q`가 하향 편향되고
     `(2q−1)` 항이 비대칭적으로 이동합니다.
  5. **자격 조건(300구)** 에 의한 선택 편향.

**이 다섯 경로 중 어느 것이 얼마나 기여하는지는 측정하지 않았습니다.** 검토 질문 Q3입니다.

---

## 7. 검증 상태 표

이 표가 이 문서의 핵심입니다. **"미검증" 칸의 항목은 믿으면 안 됩니다.**

### 7.1 검증됨

| 주장 | 검증 방법 | 결과 |
|---|---|---|
| ZA v7 모듈 테스트 통과 | `PYTHONPATH=src python -m pytest tests/test_zone_decision.py -q` (커밋 `68688f92`) | **17 passed** |
| 저장소 전체 테스트 통과 | `PYTHONPATH=src python -m pytest -q` | **110 passed** |
| 웹 레이아웃 테스트 통과 (pytest가 수집하지 않아 별도 실행) | `node tests/test_pitch_arsenal_layout.cjs` | **PASS** |
| SBJ ≡ `za_raw` (기호) | 3.1절 대수 유도 | 항등식 성립 |
| SBJ ≡ `za_raw` (합성 데이터) | `test_sbj_equals_zone_awareness_and_is_not_independent_evidence` — 난수 20세트 | 전부 일치 |
| SBJ ≡ `za_raw` (실데이터) | 2026 285타자 재계산 | 6자리 반올림 기준 **max diff 0.0** (부동소수 원값 3.02e-14) |
| SBJ = 관측 − 기대 정확도 | `test_sbj_is_observed_minus_expected_judgment_accuracy` | 성립 |
| SBJ가 결과(타구가치)에 불변 | `test_sbj_is_outcome_independent_like_zone_awareness` — `delta_v`, `raw_run_value` 변조 후에도 동일 | 성립 |
| APR이 리그 가중치를 쓰고 개인 구역 편중에 불변 | `test_apr_uses_league_region_weights_not_the_hitters_own_mix` | 성립 |
| 구역별 판단이 다르면 APR ≠ SBJ (heart 편중 시 APR < SBJ) | `test_apr_differs_from_sbj_when_region_judgment_varies` | 성립 |
| 미관측 구역은 0 대입이 아니라 가중치 재정규화 | `test_apr_renormalizes_over_regions_the_hitter_saw` | 성립 |
| APR+ = 100 + 15·(APR − 자격자 평균)/자격자 sd | `test_apr_plus_is_standardized_over_qualified_hitters` | 성립 |
| APR+ 표준편차 자유도 = **ddof=0 (모표준편차)** | `np.ndarray.std()` 기본값 직접 확인 | 확인 |
| 2026 리그 구역 가중치 (6.2절) | `data/metrics/zone_awareness/2026/pitches.parquet`에서 직접 재계산 (8.4절 스크립트) | 표대로 |
| 2026 APR/SBJ 기술통계·상관·순위변동 (6.3~6.6절) | 동일 스크립트 | 표대로 |
| 2026 DV 기술통계 (6.3절) | 동일 스크립트 | 표대로 |
| 자격 타자 163명 전원이 다섯 구역을 모두 봄 (재정규화는 비자격 122명 중 20명에만 작동) | 동일 스크립트 | 163/163, 20/122 |
| **DV 분모가 이미 판단 대상 투구임** | `_eligible()` 코드 확인 + ZA 입력 192,526행 = `decision_pitches.parquet` 192,526행 + Swing 86,007/Take 106,519 합 일치 | **이미 적용됨, 변경 불필요** |

> **테스트 개수에 관한 정정.** SBJ 테스트는 이름이 `test_sbj_*`인 것이 **3개**이고, 여기에
> `profile_summary()`의 `sbj`/`judgment_accuracy_pct` 생성 경로를 통과시키는
> `test_sa_dv_stay_unchanged_and_dv_plus_is_standardized`를 더해야 4개가 됩니다(네 번째는 SBJ 값을 단언하지 않음).
> 반면 **APR 테스트는 이름·단언 모두 기준으로 정확히 4개**입니다. 두 경우를 같은 방식으로 세지 마십시오.

### 7.2 미검증 — 빠짐없이

| # | 항목 | 상태 |
|---|---|---|
| U1 | **SBJ의 신뢰도(반분 신뢰도·재현성)를 측정하지 않았다.** | 미측정 |
| U2 | 구두로 전달된 "SBJ 1300구 환산 0.808"의 **산출 근거가 저장소에 없다** | 근거 부재 |
| U3 | ADR-005의 미결 4항목 (아래 7.3) | 미결 |
| U4 | `p_zone` 존 경계 모델의 **계통 오차**와 그 SBJ 전파 (10.2절) | 편향 존재 보고 / 전파 미측정 |
| U5 | 웹 산출물이 아직 SBJ·APR 필드를 포함하지 않음 | 확인됨(아래) |
| U6 | SBJ ↔ DV/DV+ 상관 | 미측정 |
| U7 | 타자 유형별(좌/우, 파워/컨택 등) 편향 | 미측정 |
| U8 | 시즌 간 안정성 (2024·2025 대비) | 미측정 |
| **U9** | **APR+의 신뢰도·재현성** | 미측정 |
| **U10** | **corr(APR, SBJ) = 0.995의 함의 미평가.** APR+가 SBJ 대비 얼마만큼의 독립 정보를 더 주는지 검증되지 않았다. 강한 공선성 하에서 별도 지표로 둘 가치가 있는지가 검토자에게 묻는 핵심 질문이다. | 미평가 |
| **U11** | **리그 구역 가중치를 해당 시즌 자체 데이터에서 뽑으므로 시즌 간 APR 비교 가능성이 보장되지 않는다** (가중치가 시즌마다 달라짐). 2026 이외 시즌의 가중치는 산출조차 되지 않았다. | 미평가 |
| **U12** | **구역 경계(2/3, 1, 4/3, 2)는 고정 상수이며 이 절단점의 타당성은 검증되지 않았다.** 민감도 분석 없음. | 미검증 |
| **U13** | **존 경계 계통 오차(U4)가 구역 배정 자체를 바꾸므로 APR에는 SBJ보다 더 직접적으로 전파될 수 있다.** SBJ는 `p_zone`이라는 연속값을 통해서만 영향을 받지만, APR은 `d` 절단점이 이동하면 투구의 **구역 소속이 이산적으로 바뀌고 리그 가중치까지 함께 바뀝니다.** 미측정. | 미측정 |
| **U14** | APR+/DV+의 **비자격 타자 값**(자격자 분포 위 외삽)의 타당성 | 미검증 |
| **U15** | 구역별 SBJ의 선수 간 sd가 4.2~7.0 pp로 전체 SBJ sd(2.889)보다 크다는 사실이 APR 신뢰도에 주는 영향 | 미측정 |

**U5 보충 — 직접 확인한 사실.** `web/data/zone_awareness/2026/leaderboard.json`의 선수 레코드 키에는
`za_raw`, `swing_aggression`, `dv_per_100`, `dv_plus`, 구역별 `*_decision_value_per_100` 등은 있으나
**`sbj`, `judgment_accuracy_pct`, `expected_judgment_accuracy_pct`, `apr_raw`, `apr_plus`,
`{구역}_sbj`가 전부 없습니다.** 파일 최상위에도 `region_weights` 키가 없고,
`metric_contract`의 키는 `dv_per_100`, `dv_plus`, `raw_dv`, `region_contributions`,
`swing_aggression`, `za_percentile`, `za_raw` 7개뿐입니다(코드의 `CONTRACT`는 13개).
즉 **웹 산출물은 커밋 `df345e75` 이전 실행 결과**이며, 다음 파이프라인 실행에서 재생성됩니다.
본 문서 6절 수치는 웹 JSON이 아니라
**지표 원본 Parquet(`data/metrics/zone_awareness/2026/pitches.parquet`, 2026-09-15 생성)** 에서 계산했습니다.

### 7.3 ADR-005 미결 4항목 (원문 그대로 옮김)

저장소의 아키텍처 결정 기록 ADR-005(상태: **미결**)는 반분 신뢰도 0.568과 기록된 ZA 0.810의 관계를
판정 보류로 남겼습니다. 미결 항목은 다음과 같습니다.

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

### 7.4 신뢰도 수치 대장 — 길이 병기 필수

**신뢰도 값은 측정 길이 없이 기재하지 않습니다. 원값과 환산값을 같은 칸에 넣지 않습니다.**

| 지표 | 원값 (측정 길이) | Spearman-Brown 환산값 (환산 길이) | 환산 배수 k | 산출 근거 |
|---|---|---|---|---|
| ZA 반분 | 0.568 (반쪽 300구) | 0.8099 (972구) | 3.24 | **없음 — 미기록** |
| ZA 반분 (전체길이 보정) | 0.568 (반쪽 300구) | 0.7245 (600구) | 2.00 | ADR-005 계산 |
| ZA (기록값) | 0.810 (**측정 길이 미상**) | — | — | **없음 — 미기록** |
| **SBJ** | **미상 (미측정)** | 0.808 (1300구) | 미상 | **없음 — 미기록** |
| **APR+** | **미상 (미측정)** | 0.783 (1300구) | 미상 | **없음 — 미기록** |
| **DV_avg** | **미상 (미측정)** | 0.787 (1300구) | 미상 | **없음 — 미기록** |
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

**추가 경고 (APR 고유).** APR은 구역별 SBJ 5개를 합성한 값이고, 구역별 SBJ는 각각 전체 SBJ보다
표본이 1/5 수준이며 선수 간 sd가 4.2~7.0 pp로 더 큽니다(6.5절). 전체 SBJ의 신뢰도를
APR의 신뢰도로 대용(proxy)해서는 안 됩니다.

---

## 8. 재현 방법 (저장소 접근자 기준)

검토자는 저장소에 접근할 수 없으므로 이 절은 **저장소 접근자가 6절 수치를 다시 만들 때** 쓰는 절차입니다.
아래 명령은 전부 커밋 `68688f92`에서 실제로 실행해 동작을 확인한 것만 실었습니다.

### 8.1 환경

```bash
cd /home/user/KBO-Savant-Visual-Project
git checkout 68688f92
python -m pip install -r requirements.txt -c constraints-za.txt
export PYTHONPATH=src
export OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2
```

### 8.2 테스트

```bash
PYTHONPATH=src python -m pytest tests/test_zone_decision.py -q   # 17 passed
PYTHONPATH=src python -m pytest -q                               # 110 passed
node tests/test_pitch_arsenal_layout.cjs                         # PASS
```

### 8.3 지표 재빌드 (수 시간 소요, 선택)

```bash
PYTHONPATH=src python -m visualbaseball.zone_decision --seasons 2026
```

### 8.4 6절 수치 재현 스크립트 (실행 확인 완료)

아래 스크립트는 `region_weights()` / `add_apr_plus()` / `strikezone_ball_judgment()`를 저장소 코드와
동일한 식으로 **독립 구현**해 재계산합니다(코드가 스스로를 확인하지 않게 하기 위함).

```python
# 실행: PYTHONPATH=src python this_script.py   (저장소 루트에서)
import collections
import numpy as np
import pyarrow.parquet as pq
from scipy.stats import spearmanr

REGIONS = ('heart', 'shadow_in', 'shadow_out', 'chase', 'waste')
t = pq.read_table('data/metrics/zone_awareness/2026/pitches.parquet',
                  columns=['batter_id', 'batter_name', 'swing', 'p_swing', 'p_zone', 'judgment', 'region'])
d = t.to_pydict(); n = len(d['batter_id'])
g = collections.defaultdict(list)
for i in range(n):
    g[(d['batter_id'][i], d['batter_name'][i])].append(i)
print('pitches', n, 'batters', len(g))          # -> 192526 285
print('swings', sum(d['swing']), 'takes', n - sum(d['swing']))   # -> 86007 106519

def sbj(idx):
    if not idx: return None
    S = np.array([d['swing'][i] for i in idx], float)
    p = np.array([d['p_swing'][i] for i in idx]); q = np.array([d['p_zone'][i] for i in idx])
    obs = np.mean(np.where(S == 1, q, 1 - q)); exp = np.mean(p * q + (1 - p) * (1 - q))
    return round(100 * (obs - exp), 6)

players = []
for (bid, name), idx in g.items():
    rec = {'name': name, 'n': len(idx), 'sbj': sbj(idx), 'q': len(idx) >= 300}
    for reg in REGIONS:
        sel = [i for i in idx if d['region'][i] == reg]
        rec[reg + '_pitches'] = len(sel); rec[reg + '_sbj'] = sbj(sel)
    players.append(rec)

tot = {reg: sum(p[reg + '_pitches'] for p in players) for reg in REGIONS}
grand = sum(tot.values()); w = {reg: tot[reg] / grand for reg in REGIONS}
print('region_weights', {k: round(v, 4) for k, v in w.items()})
#   -> {'heart': 0.2376, 'shadow_in': 0.2112, 'shadow_out': 0.1906, 'chase': 0.2352, 'waste': 0.1253}

for p in players:                                   # add_apr_plus() 와 동일한 재정규화
    seen = [r for r in REGIONS if p[r + '_sbj'] is not None]
    s = sum(w[r] for r in seen)
    p['apr'] = round(sum(w[r] * p[r + '_sbj'] for r in seen) / s, 6) if s else None

Q = [p for p in players if p['q']]
a = np.array([p['apr'] for p in Q]); s = np.array([p['sbj'] for p in Q])
print('qualified', len(Q))                                                     # -> 163
print('APR mean %.4f sd0 %.4f sd1 %.4f min %.3f max %.3f'
      % (a.mean(), a.std(0), a.std(ddof=1), a.min(), a.max()))
#   -> APR mean -0.4427 sd0 2.8658 sd1 2.8746 min -8.338 max 5.868
print('SBJ mean %.4f sd0 %.4f sd1 %.4f min %.3f max %.3f'
      % (s.mean(), s.std(0), s.std(ddof=1), s.min(), s.max()))
#   -> SBJ mean -0.4931 sd0 2.8890 sd1 2.8979 min -8.338 max 5.775
print('corr %.4f  max|d| %.4f  mean|d| %.4f'
      % (np.corrcoef(a, s)[0, 1], np.abs(a - s).max(), np.abs(a - s).mean()))
#   -> corr 0.9950  max|d| 2.0475  mean|d| 0.1669
print('spearman %.4f' % spearmanr(a, s).statistic)                             # -> 0.9958

ra = {p['name']: i for i, p in enumerate(sorted(Q, key=lambda p: -p['apr']))}
rs = {p['name']: i for i, p in enumerate(sorted(Q, key=lambda p: -p['sbj']))}
sh = np.array([abs(ra[p['name']] - rs[p['name']]) for p in Q])
print('rank shift max %d mean %.2f zero %d' % (sh.max(), sh.mean(), (sh == 0).sum()))
#   -> rank shift max 20 mean 2.87 zero 23

for reg in REGIONS:
    v = np.array([p[reg + '_sbj'] for p in Q if p[reg + '_sbj'] is not None])
    print('%-11s n=%d mean %+.3f sd %.3f' % (reg, len(v), v.mean(), v.std(0)))
#   -> heart n=163 mean +0.161 sd 6.925 / shadow_in -0.310 6.500 / shadow_out -0.292 4.765
#      chase -1.133 6.955 / waste -0.745 4.215

c, sp = a.mean(), a.std(0)                       # APR+ = 100 + 15*(APR-c)/sp
print('all-batter APR mean %.4f' % np.mean([p['apr'] for p in players if p['apr'] is not None]))  # -> -0.9791
print('all-batter SBJ mean %.4f' % np.mean([p['sbj'] for p in players]))       # -> -1.2777
print('pitch-weighted SBJ %.4f' % (100 * np.mean(d['judgment'])))              # -> -0.2726
```

DV 기술통계 재현:

```python
import collections, numpy as np, pyarrow.parquet as pq
t = pq.read_table('data/metrics/zone_awareness/2026/pitches.parquet', columns=['batter_id', 'dv'])
d = t.to_pydict(); n = len(d['dv'])
g = collections.defaultdict(list)
for i in range(n): g[d['batter_id'][i]].append(i)
rows = [(len(idx), 100 * sum(d['dv'][i] for i in idx) / len(idx)) for idx in g.values()]
Q = np.array([r[1] for r in rows if r[0] >= 300])
print('qualified', len(Q))                                                     # -> 163
print('dv100 mean %.4f sd0 %.4f sd1 %.4f min %.3f max %.3f'
      % (Q.mean(), Q.std(0), Q.std(ddof=1), Q.min(), Q.max()))
#   -> dv100 mean 6.0288 sd0 0.9317 sd1 0.9346 min 3.588 max 8.028
print('pooled dv100 %.4f' % (100 * np.mean(d['dv'])))                          # -> 6.1273
print('all batters mean %.4f' % np.mean([r[1] for r in rows]))                 # -> 5.7061
```

DV 분모 쟁점(5.3절) 확인:

```python
import pyarrow.parquet as pq
print(pq.ParquetFile('data/metrics/zone_awareness/2026/pitches.parquet').metadata.num_rows)  # -> 192526
print(pq.ParquetFile('data/metrics/swing_take/2026/decision_pitches.parquet').metadata.num_rows)  # -> 192526
```

---

## 9. 검토자에게 묻는 질문

답이 **판단으로 나오는** 형태로만 적었습니다.

### SBJ

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
10.2절에 기술된 편향 — 규칙 기반 존이 실제 ABS 존보다 **좁게** 추정된다는 보고 —
이 SBJ에 전파되는 방향을 예측해 주십시오. 특히 "존 가장자리를 지켜본 타자"와
"존 가장자리에 스윙한 타자" 중 누가 부당하게 손해를 봅니까?
그리고 경험적 버퍼 적합(규칙 명세 미확인)을 `p_zone` 모델에 반영하는 것이 정당합니까,
아니면 **규칙 명세를 확인하기 전까지는 미보정 상태로 두고 한계로만 기록**해야 합니까?

**Q6 (신뢰도 측정 설계).**
SBJ·APR+의 신뢰도는 아직 측정되지 않았습니다(U1, U9). 측정한다면 분할 방식은
odd-even 투구 / 무작위 투구 / 경기 단위 무작위 / 시간순 중 어느 것을 권장합니까?
투구 단위 자기상관(같은 타석·같은 투수)을 고려할 때 Spearman-Brown 환산이 타당합니까,
아니면 경기 단위 클러스터 부트스트랩 같은 다른 방법을 써야 합니까?

**Q7 (동일성 하의 신뢰도 보고).**
SBJ ≡ `za_raw`이므로 두 지표의 신뢰도는 **같은 수치일 수밖에 없습니다.**
그렇다면 7.4절 대장에서 SBJ와 ZA를 별도 행으로 두는 것 자체가 오해를 부릅니까?
두 행을 병합해야 합니까, 아니면 "동일 지표의 두 표기"라는 각주로 충분합니까?

**Q8 (자격 기준).**
자격 기준 300구는 자격 타자 표준편차 2.889 pp에 비해 충분합니까?
최하위 3명(김동헌 301구, 김헌곤 302구, 이지영 386구)은 표본 하한 근처에 몰려 있습니다.
이것이 우연입니까, 아니면 소표본에서 SBJ가 음수로 끌리는 계통적 현상을 시사합니까?
(전체 285명 평균이 −1.28로 자격 타자 평균보다 더 음수라는 사실을 함께 고려해 주십시오.)

### APR+

**Q9 (공선성 — APR+의 존재 이유).**
자격 타자 163명에서 **corr(APR, SBJ) = 0.9950**, Spearman 0.9958, 평균 절대차 0.1669 pp
(SBJ 표준편차 2.889 pp의 약 0.06 표준편차), 순위 변동 평균 2.87계단입니다.
이 공선성 수준에서 APR+를 **SBJ와 별개 지표로 유지하는 것이 정당합니까?**
정당하다면 그 근거는 (a) 극단 사례(최대 차이 2.05 pp, 최대 순위 변동 20계단)의 교정 가치입니까,
(b) "모든 타자를 같은 투구 분포에서 채점한다"는 해석적 명료성입니까,
아니면 (c) 정당화되지 않으며 **폐기하거나 진단 필드로 강등해야** 합니까?
셋 중 하나를 고르고, 유지한다면 **어떤 실증을 추가로 요구하겠습니까?**

**Q10 (미관측 구역 처리).**
타자가 한 번도 보지 못한 구역에 대해 현재 코드는 **그 구역의 가중치를 빼고 나머지를 재정규화**합니다.
대안은 **리그 평균 구역 SBJ를 대입**하는 것입니다.
어느 쪽이 옳습니까? 재정규화는 "미관측 구역에서 이 타자는 자기 평균과 같다"고 가정하는 것이고,
리그 평균 대입은 "리그 평균과 같다"고 가정하는 것입니다. 300구 자격 하에서 어느 가정이 덜 해롭습니까?
(참고 — 직접 확인한 사실: 2026에서 **자격 타자 163명은 전원 다섯 구역을 모두 보았습니다.**
재정규화가 실제로 작동하는 것은 **비자격 타자 122명 중 20명**뿐입니다.
그런데 APR+는 비자격 타자에게도 값을 부여하므로 이 20명의 값이 외삽 위에 다시 가정을 얹습니다 — U14.)

**Q11 (리그 가중치의 출처).**
현재 $w_r$는 **해당 시즌 데이터 안에서** 산출됩니다(2026: 0.2376/0.2112/0.1906/0.2352/0.1253).
따라서 가중치가 시즌마다 달라지고, 2026 APR과 2025 APR은 서로 다른 가중치로 계산된 값입니다(U11).
(a) 시즌 내부 산출을 유지하고 시즌 간 비교를 금지해야 합니까,
(b) 여러 시즌 평균 같은 **고정 상수로 박아** 시즌 간 비교를 가능하게 해야 합니까,
(c) 균등 가중(각 0.2)처럼 데이터와 무관한 값으로 박아야 합니까?
선택과 근거를 주십시오.

**Q12 (가중이 실질적 보정인가).**
2026 구역 가중치는 0.1253 ~ 0.2376 범위로, `waste`를 빼면 네 구역이 0.19~0.24에 몰려 있습니다.
사실상 균등에 가까운 이 가중이 **의미 있는 보정**입니까?
이것이 corr = 0.995의 직접 원인이라면, APR의 설계 목적(개인 구역 편중 제거)을 달성하려면
가중치 자체가 더 불균등해야 하는 것 아닙니까? 아니면 **KBO 투구 분포가 원래 구역 간 균등에 가까워서
교정할 편중이 애초에 크지 않다**는 것이 올바른 결론입니까?

**Q13 (구역 경계 상수).**
구역 경계 `2/3, 1, 4/3, 2`는 코드에 하드코딩된 고정 상수이며 민감도 분석이 없습니다(U12).
이 절단점이 KBO ABS 환경에서 타당합니까? 특히 존 경계 계통 오차(10.2절, 규칙 존이 실제보다 **좁다**)가
있다면 `d ≤ 1` 경계에 놓인 투구들이 잘못된 구역으로 배정됩니다.
이 이산적 오배정이 APR에 미치는 영향이 SBJ에 미치는 영향보다 큽니까(U13)?
그렇다면 APR을 발표하기 전에 **구역 경계 민감도 분석을 선결 조건**으로 걸어야 합니까?

### DV

**Q14 (DV 분모의 성격).**
`dv_per_100`의 분모는 그 타자의 자격 투구 전체(스윙 + 테이크)입니다.
5.3절에서 확인했듯 자격 투구는 이미 "판단 대상 투구"와 동일 집합이므로 더 좁힐 여지가 없습니다.
그런데 이 정의는 "본 공 100개당 누적 판단 가치"이지 "판단 1회당 가치"가 아닙니다.
공을 많이 보는 타자(예: 2,161구)와 적게 보는 타자(301구)를 같은 척도로 비교할 때
이 분모가 적절합니까? **타석당(per PA) 또는 스윙 결정당** 정규화를 추가로 보고해야 합니까?

**Q15 (DV의 비영점 중심).**
자격 타자 163명의 `dv_per_100`은 **전원 양수**이며 평균 **+6.0288 runs/100 pitches**, 범위 +3.588 ~ +8.028입니다.
"모든 타자가 리그 평균보다 좋은 선택을 한다"는 것은 불가능하므로, 이 양수 편향은
DV의 정의(선택한 쪽과 반대 쪽의 **모델 기대값** 차이)에서 나오는 구조적 상수로 보입니다.
이 절대 수준을 **아예 공개하지 않고 `dv_plus`만 노출하는 것**이 옳습니까,
아니면 원값을 노출하되 "0 중심이 아님"을 명시하는 것으로 충분합니까?
또한 이 +6.03이라는 값 자체가 **모델의 기대값 추정 편향을 진단하는 신호**입니까?

**Q16 (표준화 대상 집단).**
APR+와 DV+ 모두 **자격 타자(300구 이상) 163명의 평균·모표준편차(ddof=0)** 로 표준화하지만,
값 자체는 **비자격 타자에게도 부여**됩니다(U14). 자격자 분포 위에서 비자격자를 외삽하는 이 처리가
타당합니까, 아니면 비자격자는 `null`로 두어야 합니까?
또한 표준화에 ddof=0(모표준편차)을 쓰는 것이 163명 유한 표본에서 적절합니까?

---

## 10. 알려진 한계 (과장 금지)

### 10.1 모델이 스스로 선언한 한계 (`LIMITATIONS` 원문)

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
- 득점 시점이 확정되지 않은 이닝 반쪽은 통째로 제외됩니다. 득점 시각을 지어내지 않습니다.

### 10.2 `p_zone` 존 경계 모델의 알려진 계통 오차 — 미검증 항목

다음 수치는 **호출 측이 보고한 진단 결과**이며, **저장소 안에 산출 스크립트나 기록 문서가 없습니다.**
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

**APR 고유의 추가 위험 (U13).** APR의 구역 배정은 `region()`이 **같은 정규화 거리 `d`의 고정 절단점**으로
수행합니다. `p_zone`은 연속 확률이라 존 경계 오차가 부드럽게 흡수되지만, 구역 배정은 **이산적**입니다.
실제 존이 규칙 존보다 넓다면 `shadow_in`이어야 할 투구가 `shadow_out`으로 분류되고,
그 결과 (1) 구역별 SBJ의 분모·분자가 함께 바뀌고 (2) 리그 구역 가중치 $w_r$까지 함께 바뀝니다.
**따라서 존 경계 오차는 SBJ보다 APR에 더 직접적으로 전파될 수 있습니다. 측정되지 않았습니다.**

### 10.3 프로젝트 전반의 표현 규칙 (이 문서도 준수)

- **BAA**(이 저장소의 타구 관련 실험 지표)는 KBO 공개 데이터에 적용한 **실험 지표**이며,
  **MLB Statcast와 상호 비교할 수 없습니다.**
- **기존 Decision Run은 실제 선택 결과가 섞인 진단값**이므로, counterfactual **Decision Value로 부르지 않습니다.**
- **plate discipline 클러스터 번호는 우열 등급이 아닙니다.** 유형 라벨일 뿐입니다.
- **신뢰도 수치는 측정 길이를 반드시 병기**하고, **원값과 환산값을 하나의 숫자로 뭉치지 않습니다**(7.4절).
- 시즌을 섞지 않습니다. 연도별 Run Value와 리그 평균은 해당 시즌 데이터만으로 계산합니다.
- 표본 미달을 숨기지 않고 표시합니다(자격 기준 300구).

### 10.4 이 문서가 주장하지 않는 것

- SBJ가 기존 지표(`za_raw`)보다 **낫다**는 주장을 하지 않습니다. 대수적으로 동일하기 때문입니다.
- APR+가 SBJ보다 **낫다**는 주장을 하지 않습니다. corr = 0.995이며, 추가 정보량은 측정되지 않았습니다(U10).
- 세 지표의 **신뢰도·예측력·상호 우위**를 주장하지 않습니다. 측정하지 않았습니다(U1, U6, U9).
- 6절 상·하위 명단이 **타자 능력의 확정 순위**라는 주장을 하지 않습니다. 진행 중 시즌의 점추정입니다.
- DV가 **counterfactual 인과 효과**라는 주장을 하지 않습니다. 반대 행동은 관측되지 않았고 식별되지 않습니다.
- 2026 시즌은 **2026-09-12까지의 부분 시즌**(626경기)이며 완결된 시즌이 아닙니다.
