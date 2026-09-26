# SBJ(Strikezone/Ball Judgment) 구조 교차검증 요청서

> 이 문서는 자립형입니다. 외부 검토자는 이 저장소에 접근할 수 없다고 가정하고, 판정에 필요한 코드·수식·실측치를 전부 본문에 인용했습니다.

---

## 0. 검토자에게 주는 지시문

당신은 **SBJ라는 야구 타자 판단력 지표의 구조적 타당성을 판정**합니다.

- 동의/비동의만 말하지 마십시오. **각 쟁점마다 (a) 판정, (b) 그 판정을 뒤집을 수 있는 반증 가능한 검증 설계, (c) 현재 산식이 틀렸다고 보면 대안 산식**을 제시하십시오.
- "더 많은 데이터가 필요하다" 류의 유보는 답이 아닙니다. 지금 주어진 수치만으로 내릴 수 있는 잠정 판정을 먼저 내리고, 그 판정의 신뢰도를 따로 적으십시오.
- 본 문서가 "미측정"이라고 표시한 항목을 근거로 삼지 마십시오. 그 항목이 판정에 필수라면, **그것을 측정하는 구체적 절차**(어떤 통계량을, 어떤 표본 분할로, 어떤 임계값으로)를 답으로 주십시오.
- 야구 도메인 관례("Statcast는 이렇게 한다")를 인용할 때는 그것이 **이 데이터에서도 성립하는 이유**를 함께 적으십시오. 이 프로젝트는 한국 KBO 리그의 공개 중계 데이터를 쓰며, MLB Statcast의 측정 장비·파이프라인과 동일하지 않습니다.

답변 형식 권장: 쟁점별 `판정 / 근거 / 반증 설계 / 대안` 4줄 블록 + 마지막에 "가장 먼저 고쳐야 할 것 3가지" 순위.

---

## 1. 최소 배경 (야구·프로젝트 용어 풀이)

야구에서 투수가 던진 공 하나(이하 **투구**)에 대해 타자는 **스윙(swing)** 하거나 **테이크(take, 그냥 지켜봄)** 합니다.

- 테이크하면 심판(또는 자동 판정 시스템)이 **스트라이크(called strike)** 또는 **볼(ball)** 을 선언합니다. 몸에 맞으면 **HBP(사구)** 입니다.
- 스윙하면 **콜이 존재하지 않습니다.** 헛스윙(Whiff)·파울(Foul)·인플레이(InPlay) 중 하나가 됩니다.

즉 **"이 공이 스트라이크였는가"는 테이크한 공에서만 관측됩니다.** 이 비대칭이 이 문서 전체의 핵심입니다.

이 프로젝트에서 쓰는 용어:

| 용어 | 뜻 |
|---|---|
| curated | 중계사 공개 PBP(play-by-play) 원본 JSON을 정규화해 저장한 Parquet 테이블 (pitches / events / games) |
| decision pitch (eligible pitch) | 판단 지표의 분석 대상 투구. 파싱 상태 정상, 스윙/테이크가 확정, 좌표 정규화 가능, 이닝 상태 전이 정상인 투구만 |
| ZA v7 | 이 저장소의 7세대 판단 지표 모듈(`zone_decision.py`)의 내부 명칭. ZA = Zone Awareness |
| `za_raw` | 기존 판단 지표. 아래 §4에 수식 있음 |
| DV / `dv_per_100` | Decision Value. 스윙/테이크 각각의 기대 득점가치 차이를 실제 선택에 부호를 붙여 합산한 값 |
| SBJ | 이번 검토 대상. Strikezone/Ball Judgment |

**좌표계**: `x_relative`, `z_relative`는 스트라이크존 경계가 ±1이 되도록 정규화한 좌표입니다(포수 시점). `d = max(|x|,|z|)`로 구역을 나눕니다 — Heart `d ≤ 2/3`, Shadow-in `≤ 1`, Shadow-out `≤ 4/3`, Chase `≤ 2`, Waste `> 2`. 존 상하한은 투구별로 기록된 `sz_top`/`sz_bottom`입니다.

**PLV 관련 고지**: SBJ는 공개 분석 커뮤니티의 PLV(Pitch Level Value) 계열 지표 중 "Strikezone Judgement"라는 **개념**(스윙은 스트라이크였을 확률만큼, 테이크는 볼이었을 확률만큼 정답으로 친다)을 참고해 만든 **자체 변형**입니다. PLV의 정확한 복제품이 아니며, 원 구현의 모델·특징·보정 절차를 알지 못한 상태에서 이 저장소의 교차적합 콜 확률 모델로 구현했습니다. PLV의 수치와 상호 비교할 수 없습니다.

---

## 2. 저장소 상태와 데이터 범위

| 항목 | 값 |
|---|---|
| 저장소 경로 | `/home/user/KBO-Savant-Visual-Project` (비공개) |
| 브랜치 | `claude/happy-hopper-g1h339` |
| 기준 커밋 | `e4a89cbc` ("APR을 구역 가중합에서 가치 기반 SEAGER로 교체") |
| 워킹 트리 | 깨끗함 (`git status --porcelain` 무출력), 푸시 완료 |
| 실행 환경 | Python 3.12.3, numpy 2.5.3, scipy 1.18.1, scikit-learn 1.9.0 (모델 재현용 고정 버전 파일로 설치) |

데이터 범위 (`data/curated/summary.json` 기준):

| 시즌 | 경기 | pitches 행 | 기간 |
|---|---|---|---|
| 2026 | 626 | 192,712 | 2026-03-28 ~ 2026-09-12 |

이 중 **decision pitch 192,526투구**가 SBJ 계산 대상입니다(186투구는 eligibility 또는 이닝 득점 정합성 필터에서 제외). 2026 시즌은 진행 중이며 완결 시즌이 아닙니다.

타자 수: 전체 **285명**, 300투구 이상 자격자 **163명**.

---

## 3. SBJ의 정의 (검증됨)

```
SBJ_raw = 100 × mean( 스윙이면 p_CalledStrike,  테이크면 p_Ball + p_HBP )

SBJ+    = 100 + 15 × (SBJ_raw − 자격자 평균) / 자격자 모표준편차(ddof=0)
```

기준선을 **빼지 않는 순수 정확도(%)** 입니다. 실제 코드(`src/visualbaseball/zone_decision.py`):

```python
def _correct_share(row):
    """Share of this pitch the hitter judged correctly, PLV Strikezone Judgement style."""
    return row['p_CalledStrike'] if row['swing'] else row['p_Ball'] + row['p_HBP']


def _league_correct_share(row):
    # The same pitch judged by a league-average swing policy instead of this hitter.
    taken = row['p_Ball'] + row['p_HBP']
    return row['p_swing'] * row['p_CalledStrike'] + (1 - row['p_swing']) * taken


def expected_judgment_accuracy(items):
    """League-average-policy accuracy on this pitch mix; a difficulty baseline.
    Diagnostic only - SBJ does not subtract it."""
    return r6(100 * np.mean([_league_correct_share(r) for r in items])) if items else None


def strikezone_ball_judgment(items):
    """SBJ: PLV-style strike/ball judgment accuracy, in percent."""
    return r6(100 * np.mean([_correct_share(r) for r in items])) if items else None


def add_sbj_plus(players):
    """SBJ+ on the repo scale: 100 + 15 * z against the qualified population."""
    qualified = np.array([p['sbj_raw'] for p in players
                          if p['qualified_300'] and p['sbj_raw'] is not None], dtype=float)
    center = float(qualified.mean()) if len(qualified) else 0
    spread = float(qualified.std()) if len(qualified) else 0   # ddof=0 (모표준편차)
    for p in players:
        p['sbj_plus'] = r6(100 + 15 * (p['sbj_raw'] - center) / spread) \
                        if spread and p['sbj_raw'] is not None else None
    return center, spread
```

계약 문자열(`CONTRACT`)에 실린 정의:

```
'sbj_raw': '100 * mean(p_CalledStrike if swing else p_Ball + p_HBP); percent. ...
            Uses the take-conditional call model (EVENTS[3:6], fit on takes only),
            not zone membership, and subtracts no baseline.'
'sbj_plus': '100 + 15 * (sbj_raw - qualified mean) / qualified population standard deviation'
'expected_judgment_accuracy_pct':
            '100 * mean(p_swing*p_CalledStrike + (1-p_swing)*(p_Ball + p_HBP)); percent.
             Accuracy a league-average swing policy would post on this pitch mix.
             Difficulty diagnostic only - sbj_raw does not subtract it.'
```

`sbj_raw`는 구역별로도 계산됩니다(`heart_sbj`, `shadow_in_sbj`, `shadow_out_sbj`, `chase_sbj`, `waste_sbj`). 구역 분해값은 이번 검토의 주 대상은 아닙니다.

---

## 4. 확률 `p_CalledStrike`가 만들어지는 구조

### 4.1 이벤트 6종과 행동별 분리 학습

```python
EVENTS = ('Whiff', 'Foul', 'InPlay', 'Ball', 'CalledStrike', 'HBP')
```

앞 3개는 **스윙했을 때만** 관측되고, 뒤 3개(`EVENTS[3:6]`)는 **테이크했을 때만** 관측됩니다.

`fit_predict()`의 핵심 루프입니다.

```python
actions = np.array([r['decision_type'] == 'Swing' for r in train], dtype=int)
events  = np.array([EVENTS.index(r['event']) for r in train])
...
for act, indices in ((0, range(3, 6)), (1, range(3))):
    mask = actions == act
    direct[:, act] = fit_model(old._regressor(len(NUMERIC)), a[mask], target[mask]).predict(b)
    clf  = fit_model(old._classifier(len(NUMERIC)), a[mask], events[mask])
    pred = clf.predict_proba(b)                     # ← 전체 test에 predict
    for i, label in enumerate(clf.classes_):
        probs[:, int(label)] = pred[:, i]
    raw_probs = probs[:, list(indices)].copy()
    if act == 1 and support_prior:                  # ← 스윙 블록에만 prior
        weight = detailed[:, act] / (detailed[:, act] + support_prior)
        prior  = probability_prior(train, test, actions, events, act, indices)
        probs[:, list(indices)] = weight[:, None] * raw_probs + (1 - weight[:, None]) * prior
    ...
```

읽어야 할 세 가지:

1. **`act == 0`(테이크) 행만으로 `{Ball, CalledStrike, HBP}` 3-클래스 분류기를 학습**합니다 (`a[mask]`, `events[mask]`).
2. 그 분류기를 **`b`(= test 전체)** 에 predict합니다. 즉 **스윙한 투구에도 "탔다면 어떤 콜이 나왔을까"의 확률이 부여**됩니다. 이것이 SBJ의 반사실(counterfactual) "탔다면" 질문과 대응하는 구조적 근거입니다.
3. **`support_prior = 50`은 `act == 1`(스윙 이벤트 블록)에만 적용**됩니다. 따라서 **`p_Ball`/`p_CalledStrike`/`p_HBP`에는 표본 부족 축소(shrinkage)가 전혀 걸려 있지 않습니다.** SBJ가 쓰는 것은 모델의 원 출력입니다.

세 확률의 합은 1입니다 (3-클래스 softmax). 2026 192,526투구에서 `max |p_Ball + p_CalledStrike + p_HBP − 1| = 3.33e-16` — **검증됨**.

### 4.2 모델의 특징(features)

```python
BASE_NUMERIC     = ("x_relative", "z_relative", "balls_before", "strikes_before",
                    "outs_before", "base_state_code_before", "velocity_kmh", "release_height_cm")
MOVEMENT_NUMERIC = ("adjusted_hb_cm", "adjusted_ivb_cm")
CATEGORICAL      = ("pitch_type", "batter_stance", "stadium")
NUMERIC          = BASE_NUMERIC + MOVEMENT_NUMERIC
```

분류기는 `HistGradientBoostingClassifier`입니다. 주목할 점:

- **타자 ID는 특징이 아닙니다.** 타자별 정보는 `batter_stance`(좌/우타)만 들어갑니다.
- **심판 ID는 데이터에 없습니다.** 콜 성향의 대리변수는 `stadium`뿐입니다.
- **구종·구속·무브먼트가 특징에 포함**됩니다. 즉 같은 위치라도 구종이 다르면 `p_CalledStrike`가 달라질 수 있습니다.
- **볼카운트(`balls_before`, `strikes_before`)와 주자·아웃 상태가 특징에 포함**됩니다. 즉 같은 위치라도 카운트가 다르면 `p_CalledStrike`가 달라집니다.

### 4.3 교차적합 (cross-fit)

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
        values = pred[selected]; dv = decision_value(action, values[:, 1], values[:, 0])
        for i, r in enumerate(test):
            r.update({'swing': int(action[i]), 'p_swing': float(pred['p'][i]),
                      'p_zone': float(pzone[i]), ...})
            for j, e in enumerate(EVENTS):
                r[f'p_{e}'] = float(pred['probs'][i, j])
```

- **날짜 블록 3-fold**입니다. 시즌 날짜를 3등분하고, 각 블록의 투구는 나머지 두 블록으로 학습한 모델로 점수를 매깁니다.
- 이는 자기 경기 결과 누출은 막지만, **한 블록을 채점할 때 시간상 미래인 다른 블록을 학습에 씁니다.** 순수한 사전 예측 성능이 아닙니다(저장소 한계 목록에 명시됨).
- `calibration=True`는 **`p_swing`(스윙 성향 확률)에만** 적용되는 isotonic 보정입니다. 학습 내부 GroupKFold OOF 예측으로 보정기를 적합하고, 날짜 기준 80% 지점으로 자른 홀드아웃에서 **log loss와 Brier score가 둘 다 개선될 때만** 채택합니다. **`p_CalledStrike`에는 보정이 걸리지 않습니다.**

```python
calibration_applied = (log_loss(truth, corrected, labels=[0,1]) < log_loss(truth, oof[held_mask], labels=[0,1])
                       and brier_score_loss(truth, corrected) <= brier_score_loss(truth, oof[held_mask]))
```

`p_swing`은 SBJ 자체에는 들어가지 않고, 진단용 `expected_judgment_accuracy_pct`에만 들어갑니다.

---

## 5. 쟁점 1 — 이전 SBJ 정의는 왜 무너졌는가

### 5.1 이전 정의

```
old_SBJ = 100 × [ mean(정답비율) − mean(리그평균정책 기대정답비율) ]
   정답비율          = q      (스윙)  /  1 − q  (테이크)
   리그평균정책 기대  = p_swing·q + (1 − p_swing)·(1 − q)
   q = p_zone
```

### 5.2 대수적 항등

`S ∈ {0,1}`를 실제 스윙 여부라 하면

```
정답비율 = S·q + (1−S)(1−q) = (1−q) + S(2q−1)
리그기대 = p_swing·q + (1−p_swing)(1−q) = (1−q) + p_swing(2q−1)
차이     = (S − p_swing)(2q − 1)
```

그런데 저장소의 기존 지표 `za_raw`가 바로 그 값입니다.

```python
CONTRACT['za_raw'] = '100 * mean((S - p_swing) * (2*p_zone - 1)); percentage points'
# score_crossfit 안:
'judgment': float((action[i] - pred['p'][i]) * (2 * pzone[i] - 1))
```

즉 **이전 SBJ는 `za_raw`와 투구 단위로 대수적 항등**이었고, 새 지표가 아니라 같은 수를 다른 이름으로 부른 것이었습니다.

**실측 검증(2026, 285명 전원)**: `max |old_SBJ − za_raw| = 0.0` (소수점 6자리 반올림 기준). 항등이 이론만이 아니라 실제 산출물에서도 완전히 성립했습니다.

### 5.3 새 정의가 함정을 피하는 방식

두 가지를 동시에 바꿨습니다.

1. **기준선을 빼지 않습니다.** 위 유도에서 붕괴를 일으킨 것은 `− 리그기대` 항입니다. 빼는 순간 `(1−q)` 항이 소거되고 `(S − p_swing)(2q−1)`만 남습니다. 빼지 않으면 `(1−q) + S(2q−1)`의 **`(1−q)` 항, 즉 투구 난이도 수준 자체가 지표에 남습니다.**
2. **`q`를 `p_zone`에서 3-클래스 콜 모델의 `p_CalledStrike`로 바꿨습니다.**

테스트가 이 두 가지를 고정합니다(`tests/test_zone_decision.py`):

```python
def test_sbj_no_longer_collapses_onto_zone_awareness():
    # Subtracting the league baseline is what produced the za_raw identity; SBJ does not.
    ...
    assert strikezone_ball_judgment(items) != zone_awareness(items)

def test_expected_judgment_is_a_diagnostic_not_subtracted_from_sbj():
    assert strikezone_ball_judgment(items) != round(
        strikezone_ball_judgment(items) - expected_judgment_accuracy(items), 6)
```

**판정 요청 Q1.** 기준선을 빼면 기존 지표로 붕괴하고, 빼지 않으면 난이도가 섞인다 — 이 딜레마에서 "빼지 않는다"가 옳은 선택입니까? 아니면 붕괴를 피하면서 난이도를 보정하는 제3의 형태(비율, 잔차, 다른 기준 정책)가 구조적으로 더 낫습니까? 대안을 제시하고, 그 대안이 `za_raw`와 항등이 되지 않음을 **대수적으로** 보이십시오.

---

## 6. 쟁점 2 — `p_CalledStrike` vs `p_zone` (가장 중요)

### 6.1 먼저 사실관계 정정

이 검토를 준비하며 `p_zone`의 실제 구현을 확인한 결과, **`p_zone`은 "존 소속 확률"이 아닙니다.** 그것도 테이크 전용 콜 모델입니다.

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

따라서 두 확률의 실제 차이는 **"존 소속 vs 콜"이 아니라, 같은 질문("탔다면 스트라이크 콜이 나왔겠는가")에 대한 두 모델의 차이**입니다.

| | `p_zone` | `p_CalledStrike` |
|---|---|---|
| 학습 표본 | 테이크 투구만 | 테이크 투구만 |
| 목표 | 2-클래스 (CalledStrike vs 그 외) | 3-클래스 (Ball / CalledStrike / HBP) |
| 특징 | 위치 4개: `x_relative`, `z_relative`, `sz_top`, `sz_bottom` | 위치 + 카운트 + 아웃/주자 + 구속 + 릴리스높이 + HB/IVB + 구종 + 스탠스 + 구장 (총 13개) |
| HBP 처리 | 스트라이크가 아닌 쪽에 묻힘 | 별도 클래스로 분리 |
| 평활화 | 없음 (1e-6 클리핑만) | 없음 (`support_prior`는 스윙 블록 전용) |
| 보정 | 없음 | 없음 |

**즉 이번 변경의 실질은 "맥락 변수를 콜 확률에 넣을 것인가"입니다.** 존 소속 여부라는 물리적 사실 대신 "이 카운트에서, 이 구장에서, 이 구종으로 이 위치에 왔을 때 스트라이크가 불릴 확률"을 기준으로 삼습니다.

### 6.2 실측 대조 (2026, 192,526투구 — 검증됨)

| 통계량 | 값 |
|---|---|
| `corr(p_CalledStrike, p_zone)` | **0.9914** |
| `mean p_CalledStrike` | 0.4910 |
| `mean p_zone` | 0.4931 |
| `max |p_CalledStrike − p_zone|` | **0.9330** |
| `p_Ball + p_CalledStrike + p_HBP` 합의 최대 오차 | 3.33e-16 |
| 스윙 비율 | 0.4467 |
| 스윙 투구의 평균 `p_CalledStrike` | 0.6934 |
| 테이크 투구의 평균 `p_CalledStrike` | 0.3275 |

전체 상관은 0.99지만 **개별 투구에서는 최대 0.93 어긋납니다.** 평균은 거의 같은데 꼬리가 크게 다른 분포입니다.

테스트가 이 구분을 고정합니다.

```python
def test_sbj_reads_call_probabilities_not_zone_membership():
    # Same p_zone, different call model: SBJ must move, za_raw must not.
    base = [_judgment_row(1, .4, .6, p_cs=.6), _judgment_row(1, .4, .6, p_cs=.6)]
    ...
    assert strikezone_ball_judgment(shifted) != strikezone_ball_judgment(base)
```

### 6.3 무엇이 걸려 있는가

"스트라이크로 불렸겠는가"를 분모로 삼으면 **심판(또는 자동 판정 시스템)의 콜 성향이 타자의 판단력 점수에 흡수**됩니다. 구체적으로:

- **카운트 효과**: 3-0에서 존 가장자리는 스트라이크로 잘 불리고, 0-2에서는 잘 안 불립니다. `balls_before`/`strikes_before`가 특징이므로 이 성향이 `p_CalledStrike`에 반영됩니다. 그 결과 SBJ는 "실제로 불릴 콜"에 맞춰 판단한 타자를 보상합니다.
- **구장 효과**: `stadium`이 특징이므로 구장별 콜 성향 차이가 부분적으로 통제됩니다.
- **구종 효과**: 같은 위치의 패스트볼과 커브가 다른 `p_CalledStrike`를 받습니다. 프레이밍·궤적 착시 때문에 실제로 콜이 다를 수 있지만, **타자의 판단력 측정에 이것이 들어가야 하는지는 자명하지 않습니다.**
- **심판 ID는 없습니다.** 개별 심판 성향은 통제되지 않고 잔차로 남습니다.

**판정 요청 Q2-a.** 타자 판단력의 정답 기준으로 (i) 물리적 존 소속, (ii) 위치만 조건으로 한 콜 확률(= `p_zone`), (iii) 카운트·구종·구장까지 조건으로 한 콜 확률(= 현재 `p_CalledStrike`) 중 무엇이 옳습니까? 셋을 우열 순으로 정렬하고 각 순위의 근거를 대십시오.

**판정 요청 Q2-b.** 카운트를 콜 확률의 조건으로 넣는 것은 "타자가 실전에서 마주하는 확률"을 정확히 반영하는 개선입니까, 아니면 타자가 통제할 수 없는 심판 성향을 지표에 주입하는 오염입니까? 이 둘을 실증적으로 구분할 수 있는 검증을 설계하십시오.

**판정 요청 Q2-c.** `corr = 0.9914`인데 `max|Δ| = 0.9330`입니다. 전체 상관이 이렇게 높은데도 모델을 교체할 가치가 있다고 보십니까? 가치를 판정하려면 상관 대신 어떤 통계량을 봐야 합니까?

---

## 7. 쟁점 3 — 기준선을 빼지 않는 선택과 난이도 보정

현재 SBJ에는 **난이도 보정이 없습니다.** 타자마다 마주하는 투구 구성(존 안 비율, 카운트 분포, 상대 투수 수준)이 다른데 그 차이를 보정하지 않습니다. `expected_judgment_accuracy_pct`는 계산해서 **진단용으로만** 남겨두었습니다.

**2026 자격자 163명 실측 — 검증됨:**

| | 평균 | 모표준편차(ddof=0) | 범위 |
|---|---|---|---|
| `SBJ_raw` (관측 정확도, %) | 67.8586 | **3.0940** | 56.9975 ~ 73.9939 |
| `expected_judgment_accuracy_pct` (기대 정확도, %) | 68.3917 | **1.0188** | (미기재) |

즉 **타석 구성 차이가 만들어내는 변동(sd 1.0188)은 관측 변동(sd 3.0940)의 약 1/3** 수준입니다. 두 sd의 비는 약 0.329이고, 분산 비로는 약 0.108입니다.

딜레마: §5에서 보았듯 **기대치를 빼면 `za_raw`로 붕괴하므로 뺄 수 없습니다.**

**판정 요청 Q3-a.** sd 1.02(퍼센트포인트)의 난이도 변동은 무시 가능한 수준입니까, 아니면 반드시 제거해야 하는 수준입니까? 무시 가능/불가능의 판정 임계값을 수치로 제시하고 그 임계값의 근거를 대십시오.

**판정 요청 Q3-b.** 차분(`관측 − 기대`)이 붕괴를 일으킨다면, **비율(`관측 / 기대`)** 이나 **회귀 잔차(`관측 ~ 기대`의 잔차)** 는 붕괴를 피합니까? 비율 형태가 `za_raw`와 항등이 되지 않음을 대수적으로 확인해 주십시오. 비율·잔차 각각의 해석상 결함(예: 기대치가 낮은 타자의 분모 불안정)도 함께 적으십시오.

**판정 요청 Q3-c.** 보정을 포기한다면, `expected_judgment_accuracy_pct`를 나란히 공표하는 것만으로 사용자의 오독을 막을 수 있습니까? 아니면 보정되지 않은 지표를 리더보드에 올리는 것 자체가 부적절합니까?

---

## 8. 쟁점 4 — 반사실 추정의 신뢰성 (스윙 투구에 콜 모델을 외삽)

SBJ의 스윙 항 `p_CalledStrike`는 **정의상 콜이 관측되지 않는 투구에 대한 외삽**입니다.

```
학습 표본: decision_type == 'Take' 인 투구만        (actions == 0)
적용 대상: test 전체 — 스윙 투구 포함
```

선택 편향의 경로:

1. **타자는 무작위로 스윙하지 않습니다.** 스윙한 공은 애초에 "칠 만해 보인" 공이고, 그것은 존 안일 확률과 상관됩니다. 실측상 스윙 투구의 평균 `p_CalledStrike`는 0.6934, 테이크 투구는 0.3275입니다 — **두 집합의 위치 분포가 크게 다릅니다.**
2. 따라서 모델은 **테이크 분포에서 학습해 스윙 분포로 covariate shift를 건너뜁니다.** 두 분포가 겹치는 영역(존 가장자리)에서는 문제가 작지만, 스윙이 집중되는 존 한가운데는 테이크 표본이 상대적으로 희박합니다.
3. 게다가 **`p_CalledStrike`에는 표본 부족 축소가 걸려 있지 않습니다**(§4.1). `support_prior=50`은 스윙 이벤트 블록 전용입니다.
4. 콜 모델에는 **타자 ID가 없으므로**, 특정 타자가 유난히 존 밖에 스윙하는 경향이 있어도 그 타자용으로 보정되지 않습니다. 이것은 편향이 아니라 오히려 지표가 성립하기 위한 조건으로 볼 수도 있습니다.

교차적합은 **자기 경기의 결과 누출**만 막습니다. 선택 편향은 교차적합으로 해결되지 않습니다.

**판정 요청 Q4-a.** 이 외삽은 타당합니까? "타당/조건부 타당/부당" 중 하나로 판정하고, 조건부라면 성립 조건(overlap/positivity 가정 등)을 명시하십시오.

**판정 요청 Q4-b.** 외삽 품질을 측정할 구체적 절차를 제시하십시오. 예컨대 propensity overlap 진단, 테이크 표본을 스윙 분포로 재가중한 평가, 존 중심부 구간별 테이크 표본 밀도 보고 중 무엇을, 어떤 임계값으로 봐야 합니까?

**판정 요청 Q4-c.** `p_CalledStrike`에 `support_prior` 같은 축소를 걸지 않은 것이 결함입니까? 걸어야 한다면 어떤 계층(카운트 × 구역 × 구종?)으로 back-off해야 합니까? 축소를 걸면 SBJ의 타자 간 변별력이 인위적으로 줄어드는 대가가 있는데, 그 trade-off를 어떻게 잡아야 합니까?

---

## 9. 쟁점 5 — SBJ+ 표준화 정책

```python
qualified = [p['sbj_raw'] for p in players if p['qualified_300'] and p['sbj_raw'] is not None]
center = qualified.mean()
spread = qualified.std()          # ddof=0, 모표준편차
for p in players:                 # ← 비자격 타자에게도 값을 부여
    p['sbj_plus'] = 100 + 15 * (p['sbj_raw'] - center) / spread
```

정책 요소 네 가지:

1. **자격 기준 300 decision pitch.** 2026 기준 285명 중 163명 통과.
2. **모표준편차(ddof=0)** 로 표준화. 자격자 집단을 표본이 아니라 모집단으로 취급합니다.
3. **자격자 분포로 중심·산포를 잡되, 비자격 타자에게도 `sbj_plus`를 부여**합니다.
4. 스케일은 평균 100, 표준편차 15입니다(IQ 스케일 관행).

비자격 타자를 포함하면 어떤 일이 생기는지 보여주는 실측: **전체 285명의 `SBJ_raw` 범위는 31.7023 ~ 99.7768**입니다(자격자 163명은 56.9975 ~ 73.9939). 즉 **소표본 타자의 값이 자격자 sd 3.0940 기준으로 환산되면 SBJ+가 대략 100 ± 180 범위까지 벌어집니다.** 이 값들은 실력 차이가 아니라 표본 잡음입니다.

**판정 요청 Q5-a.** 자격자 sd로 표준화한 값을 비자격 타자에게 부여하는 것이 정당합니까? 부여하되 표시하지 않는 것, 아예 null로 두는 것, 축소 추정치(empirical Bayes)를 주는 것 중 무엇이 옳습니까?

**판정 요청 Q5-b.** ddof=0 vs ddof=1 선택이 실질적으로 중요합니까(n=163)? 중요하지 않다면 그 근거를, 중요하다면 어느 쪽이 옳은지 판정하십시오.

**판정 요청 Q5-c.** 300 decision pitch라는 자격선이 SBJ의 안정성 기준으로 적절합니까? 적절성을 판정하는 절차를 제시하십시오. (주의: 아래 §11에서 밝히듯 SBJ의 신뢰도는 **미측정**입니다. 신뢰도 수치를 전제하지 마십시오.)

---

## 10. 쟁점 6 — 자격자 평균이 리그 평균 정책보다 낮다

가장 설명되지 않은 실측입니다.

```
자격자 163명 평균 SBJ_raw               = 67.8586 %
자격자 163명 평균 기대 정확도            = 68.3917 %
차                                      = −0.5331 퍼센트포인트
```

**자격을 갖춘(= 출장이 많은) 타자 집단이, 리그 평균 스윙 정책이 같은 투구를 받았을 때 얻을 정확도보다 낮은 정확도를 기록합니다.**

가능한 설명 후보(모두 **미평가**):

1. **교차적합의 구조적 효과.** `p_CalledStrike`는 홀드아웃 예측이지만 `p_swing`(기대치 계산에 들어감)도 홀드아웃 예측입니다. 두 확률의 오차가 상관되어 기대치가 체계적으로 높게 나올 가능성.
2. **`p_swing`의 isotonic 보정 효과.** 보정은 `p_swing`에만 걸립니다. 보정된 `p_swing`이 극단으로 덜 가면(중앙으로 수축되면) 기대 정확도 `p·q + (1−p)(1−q)`가 어느 방향으로 움직이는지 부호가 자명하지 않습니다.
3. **자격 조건의 선택 효과.** 300투구 이상 타자는 리그 전체와 투구 구성이 다릅니다. 기대치는 리그 평균 정책으로 계산되는데, 자격자만 평균 내면 가중이 달라집니다.
4. **실제 신호.** 젠슨 부등식 관점에서, 기대 정확도는 `p_swing`에 대해 선형이므로 확률적 정책이 결정적 정책보다 반드시 나쁘지는 않습니다. 오히려 `q`가 0.5에서 먼 투구에서 리그 평균 정책이 개별 타자보다 잘 맞을 수 있습니다.

### 10.1 대수 분해 (검증됨)

`p_Ball + p_CalledStrike + p_HBP = 1`이므로 테이크 항은 `1 − p_CS`입니다. 따라서 `q = p_CalledStrike`로 두면

```
정답비율 = S·q + (1−S)(1−q) = (1−q) + S(2q−1)
기대치   = p_swing·q + (1−p_swing)(1−q) = (1−q) + p_swing(2q−1)
차이     = (S − p_swing)(2q − 1)          ← q = p_CalledStrike
```

**실측 확인(192,526투구)**: `max |(정답비율 − 기대치) − (S − p_swing)(2·p_CS − 1)| = 3.33e-16`.

**주의 — 이것은 `za_raw`와 같은 값이 아닙니다.** `za_raw`는 같은 형태를 `p_zone`으로 계산한 값입니다. 자격자 163명 평균으로:

| 양 | 값 (퍼센트포인트) |
|---|---|
| `mean(SBJ_raw) − mean(expected)` | **−0.5331** |
| `100 · mean((S − p_swing)(2·p_CalledStrike − 1))` | **−0.5331** (위와 일치) |
| `za_raw` 평균 = `100 · mean((S − p_swing)(2·p_zone − 1))` | **−0.4931** |

즉 자격자 집단은 **두 콜 모델 어느 쪽으로 계산해도 "리그 평균 스윙 정책보다 판단이 나쁜" 쪽으로 음수**입니다.

**판정 요청 Q6.** 이 −0.5331퍼센트포인트는 버그의 징후입니까, 모델 아티팩트입니까, 실제 신호입니까? 세 가설을 구분할 최소 검증 세 가지를 순서대로 제시하십시오. 특히 위 분해가 보여주듯 이 값은 `mean((S − p_swing)(2q − 1))`이고, 자격자 평균이 음수라는 것은 **"출장 많은 타자일수록 자신의 스윙 성향 예측 대비 존 인식이 나쁘다"** 는 해석을 낳습니다. 이 해석이 성립합니까, 아니면 `p_swing` 모델(자격자 표본이 학습을 지배함)의 과적합·수축이 만들어낸 부호입니까? 비자격자까지 포함하면 이 값이 어떻게 움직여야 논리적으로 일관됩니까?

---

## 11. 2026 실측 종합 (전부 직접 재현해 확인함)

기준 커밋 `e4a89cbc`, `data/metrics/zone_awareness/2026/pitches.parquet` (192,526행, 교차적합 산출물)에서 재계산했습니다.

| 항목 | 값 |
|---|---|
| decision pitch | 192,526 |
| 전체 타자 | 285명 |
| 자격자(≥300 pitch) | 163명 |
| `SBJ_raw` 평균 | 67.8586 % |
| `SBJ_raw` 모표준편차(ddof=0) | 3.0940 |
| `SBJ_raw` 범위(자격자) | 56.9975 ~ 73.9939 % |
| `SBJ_raw` 범위(전체 285명) | 31.7023 ~ 99.7768 % |
| 기대 정확도 평균 | 68.3917 % |
| 기대 정확도 모표준편차(ddof=0) | 1.0188 |
| `corr(SBJ_raw, za_raw)` | **0.9427** (이전 정의에서는 1.0000 항등) |
| SBJ 순위 vs ZA 순위 변동 (자격자 163명) | 최대 **61계단**, 평균 **12.66계단**, 무변동 **5명** |
| `corr(SBJ_raw, dv_per_100)` | 0.6455 |
| `corr(SBJ_raw, apr_raw)` (커밋 `e4a89cbc`의 가치 기반 SEAGER APR) | 0.6083 |
| `max |old_SBJ − za_raw|` (이전 정의 항등 확인) | **0.0** |

`corr(SBJ, za_raw) = 0.9427`은 "항등은 깨졌지만 여전히 강하게 같이 움직인다"는 뜻입니다. 순위 변동 평균 12.66계단은 163명 중 약 7.8%에 해당합니다.

**판정 요청 Q7.** 상관 0.9427, 평균 순위 변동 12.66계단(163명 중)은 **별도 지표로 공표할 만한 독립성**입니까, 아니면 `za_raw`의 재포장입니까? 독립성의 판정 임계값을 제시하십시오.

---

## 12. 검증 상태 표

### 검증됨

| 주장 | 검증 방법 |
|---|---|
| 전체 테스트 116개 통과 | `PYTHONPATH=src python -m pytest -q` → `116 passed in 18.05s` (커밋 `e4a89cbc`) |
| `tests/test_zone_decision.py` 23개 통과 | 위 실행에 포함. 파일 내 `def test_` 개수 23개 확인 |
| SBJ 전용 테스트 6개 존재 | `test_sbj_credits_called_strike_chance_on_swings_and_ball_chance_on_takes`, `test_sbj_reads_call_probabilities_not_zone_membership`, `test_sbj_no_longer_collapses_onto_zone_awareness`, `test_sbj_is_outcome_independent_like_zone_awareness`, `test_expected_judgment_is_a_diagnostic_not_subtracted_from_sbj`, `test_sbj_plus_is_standardized_over_qualified_hitters` |
| 웹 레이아웃 테스트 통과 | `node tests/test_pitch_arsenal_layout.cjs` → PASS |
| §11 실측치 전부 | `data/metrics/zone_awareness/2026/pitches.parquet` 직접 재집계 |
| `p_Ball+p_CalledStrike+p_HBP = 1` | 192,526행 최대 오차 3.33e-16 |
| 이전 SBJ ≡ `za_raw` | 285명 전원 최대 차이 0.0 (6자리 반올림), 대수 유도와 일치 |
| `SBJ+`가 모표준편차(ddof=0) 사용 | `add_sbj_plus`의 `qualified.std()` — numpy 기본 ddof=0 |
| `support_prior`가 `act==1`에만 적용 | `fit_predict`의 `if act == 1 and support_prior:` |
| 콜 모델이 테이크 행만으로 학습 | `mask = actions == act`, `act=0`이 Take, `indices=range(3,6)`가 `EVENTS[3:6]` |
| `p_zone`도 테이크 전용 콜 모델 | `predict_pzone` 본문 — 특징이 위치 4개로 제한된 2-클래스 판본 |
| 웹·CSV 산출물에 SBJ 미반영 | `web/data/zone_awareness/2026/leaderboard.json`의 285명 선수 레코드에 `sbj_raw`/`sbj_plus` 키 없음(`za_raw`, `dv_per_100`, `dv_plus`, 구역별 DV만 존재). `exports/kbo_zone_awareness_v2_*.csv` 헤더에도 `sbj` 컬럼 0개 |

### 미검증 (검토자는 아래를 사실로 전제하지 마십시오)

| 항목 | 상태 |
|---|---|
| **SBJ 신뢰도(반분 상관·재현성)** | **미측정.** 구두로 오간 "1300구 환산 0.808" 같은 수치는 **이 저장소에 근거가 없습니다.** 어떤 길이에서 측정한 원값도, 그 환산값도 존재하지 않습니다. |
| 존 경계 모델의 계통 오차 전파 | 2026 무작위 40경기의 called ball/strike 6,945개에서 `d ≤ 1` **규칙** 기준 잔차 4.87%, 잔차 338건 중 **298건(88.2%)** 이 "규칙은 볼, 실제는 콜 스트라이크" — 즉 규칙 존이 실제보다 좁습니다. 그러나 이는 `p_zone` 계열 진단이며, **`p_CalledStrike`로 바뀐 지금 SBJ에 어떻게 전파되는지 미측정**입니다. 콜 확률을 직접 학습하면 이 편향이 줄어든다는 **가설도 미검증**입니다. |
| 자격자 평균(67.86%)이 기대치(68.39%)보다 낮은 **이유** | **미평가** (§10). 대수 분해 자체는 검증됨(§10.1)이나 원인 규명은 안 됨 |
| 시즌 간 안정성 (2022~2025 재계산, year-to-year 상관) | **미측정** |
| 타자 유형별 편향 (좌/우, 파워/컨택, 스윙률 극단) | **미측정** |
| 차년도 BB%·chase%·삼진률 등 외부 지표와의 예측 관계 | **미측정** |
| `p_CalledStrike`의 보정 품질 (reliability diagram, Brier) | **미측정.** 보정 검사는 `p_swing`에만 적용됩니다 |
| 스윙 분포로의 외삽 품질 (covariate shift 진단) | **미측정** (§8) |
| 심판·자동판정 성향의 지표 흡수량 | **미측정.** 심판 ID가 데이터에 없습니다 |
| 구역별 `sbj`(heart/shadow/chase/waste 분해)의 타당성 | **미평가** |

### 반증됨

| 주장 | 반증 내용 |
|---|---|
| "이전 SBJ는 `za_raw`와 다른 지표다" | 대수적 항등이며 285명 전원 최대 차이 0.0 |
| "`p_zone`은 존 소속 확률이다" | `predict_pzone`은 테이크 전용 called-strike 확률 모델입니다. 코드 주석(`_correct_share`의 docstring)이 `p_zone`을 "was it in the zone"으로 설명하는 것은 **부정확**합니다 (§6.1) |

---

## 13. 재현 방법

저장소 접근이 없는 검토자는 이 절을 실행할 수 없습니다. 판정에 필요한 수치는 §6·§7·§11에 모두 실었습니다. 아래는 저장소 보유자용 재현 절차입니다.

```bash
export PYTHONPATH=src
export OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2
python -m pip install -r requirements.txt -c constraints-za.txt

# 테스트
python -m pytest -q
python -m pytest tests/test_zone_decision.py -q
node tests/test_pitch_arsenal_layout.cjs

# 교차적합 산출물 재생성 (수 시간 소요)
python -m visualbaseball.zone_decision --seasons 2026

# 본 문서의 실측치 재집계 (교차적합 산출물에서 직접)
PYTHONPATH=src python - <<'PY'
import numpy as np, pyarrow.parquet as pq, collections
t = pq.read_table('data/metrics/zone_awareness/2026/pitches.parquet',
                  columns=['batter_id','swing','p_swing','p_zone','judgment','dv',
                           'p_Ball','p_CalledStrike','p_HBP'])
d = {n: t[n].to_numpy(zero_copy_only=False) for n in t.schema.names}
sw = d['swing'].astype(bool)
correct = np.where(sw, d['p_CalledStrike'], d['p_Ball'] + d['p_HBP'])
league  = d['p_swing']*d['p_CalledStrike'] + (1-d['p_swing'])*(d['p_Ball']+d['p_HBP'])
idx = collections.defaultdict(list)
for i, b in enumerate(d['batter_id'].astype(str)): idx[b].append(i)
q = [(np.array(ii),) for ii in idx.values() if len(ii) >= 300]
sbj = np.array([100*correct[ii].mean() for (ii,) in q])
exp = np.array([100*league[ii].mean() for (ii,) in q])
za  = np.array([100*d['judgment'][ii].mean() for (ii,) in q])
print(len(q), sbj.mean(), sbj.std(), exp.mean(), exp.std(), np.corrcoef(sbj, za)[0,1])
PY
```

---

## 14. 알려진 한계 (지표 해석 범위)

- **SBJ는 실험 지표입니다.** KBO 공개 중계 PBP 데이터에 적용한 자체 구현이며, MLB Statcast 계열 지표나 PLV 계열 지표의 수치와 **상호 비교할 수 없습니다.** 같은 이유로 이 프로젝트의 BAA(타구 기반 지표)도 KBO 공개 데이터 적용 실험 지표이며 MLB Statcast와 상호 비교 불가입니다.
- **SBJ는 판단의 정확도이지 가치가 아닙니다.** 존 한가운데를 그냥 지켜본 것과 존 밖 30cm를 지켜본 것이 득점가치에서는 전혀 다르지만, SBJ에서는 둘 다 "콜 확률만큼 틀림/맞음"으로만 세어집니다.
- **기존 Decision Run은 실제 선택 결과가 섞인 진단값이며 counterfactual Decision Value가 아닙니다.** SBJ와 나란히 놓고 읽을 때 이 구분을 유지해야 합니다.
- **이 프로젝트의 plate discipline 클러스터 번호는 우열 등급이 아닙니다.** 유형 라벨일 뿐입니다.
- **시즌 표시값은 날짜 블록 교차적합**으로 해당 경기 결과를 제외하지만 다른 블록의 미래 경기를 학습에 씁니다. 순수한 사전 예측 성능이 아닙니다.
- **표본 미달을 숨기지 않습니다.** 300 decision pitch 미만 타자에게도 값이 부여되므로(§9), 표시할 때 자격 여부를 함께 보여야 합니다.
- 2026 시즌은 **진행 중**(2026-03-28 ~ 2026-09-12, 626경기)이며 완결 시즌이 아닙니다.

---

## 15. 판정 요청 목록 (요약)

| # | 질문 |
|---|---|
| Q1 | 기준선을 빼면 기존 지표로 붕괴, 빼지 않으면 난이도 혼입 — "빼지 않는다"가 옳은가? 붕괴하지 않으면서 보정하는 대안을 대수적으로 제시하라 |
| Q2-a | 판단 정확도의 정답 기준: 물리적 존 소속 / 위치만 조건인 콜 확률 / 맥락 포함 콜 확률 — 셋을 우열 순으로 정렬하라 |
| Q2-b | 카운트를 콜 확률의 조건으로 넣는 것은 개선인가 오염인가? 둘을 구분할 검증을 설계하라 |
| Q2-c | `corr=0.9914`, `max|Δ|=0.9330` — 모델 교체 가치를 판정할 통계량은 무엇인가? |
| Q3-a | 기대 정확도 sd 1.0188 vs 관측 sd 3.0940 — 난이도 보정 없이 가도 되는가? 임계값을 수치로 제시하라 |
| Q3-b | 비율(관측/기대) 또는 회귀 잔차가 `za_raw` 붕괴를 피하는가? 대수적으로 확인하고 결함을 적으라 |
| Q3-c | 보정 없이 공표할 때 기대치 병기만으로 충분한가? |
| Q4-a | 테이크 전용 학습 모델을 스윙 투구에 외삽하는 것은 타당한가? (타당/조건부/부당) |
| Q4-b | 외삽 품질을 측정할 구체 절차와 임계값은? |
| Q4-c | `p_CalledStrike`에 축소가 없는 것이 결함인가? 걸어야 한다면 어떤 계층으로? |
| Q5-a | 자격자 sd로 표준화한 값을 비자격 타자(전체 SBJ 범위 31.70~99.78%)에게 부여해도 되는가? |
| Q5-b | n=163에서 ddof=0 vs ddof=1이 실질적으로 중요한가? |
| Q5-c | 300 decision pitch 자격선의 적절성을 어떻게 판정하는가? (신뢰도는 미측정이므로 전제 금지) |
| Q6 | 자격자 평균이 리그 평균 정책보다 0.5331퍼센트포인트 낮다 — 버그/아티팩트/신호 중 무엇인가? 차이가 `mean((S−p_swing)(2·p_CS−1))`로 분해되고 `za_raw` 평균(−0.4931)도 음수라는 사실에서 무엇이 따라 나오는가? |
| Q7 | `corr(SBJ, za_raw)=0.9427`, 평균 순위 변동 12.66/163계단 — 별도 지표로 공표할 독립성인가? |

---

## 16. 검토자에게 특히 부탁하는 것

1. **§6.1의 사실관계 정정을 반영해서 답해 주십시오.** 이 변경은 "존 소속 vs 콜"의 대립이 아니라 "위치만 쓰는 콜 모델 vs 맥락까지 쓰는 콜 모델"의 대립입니다.
2. **§10.1의 대수 분해를 검산해 주십시오.** `mean(SBJ) − mean(expected) = mean((S − p_swing)(2·p_CalledStrike − 1))`이며(실측 오차 3.33e-16), 이는 `za_raw`(같은 형태를 `p_zone`으로 계산)와 **같은 값이 아닙니다**(−0.5331 vs −0.4931). 자격자 평균이 두 경우 모두 음수라는 사실이 무엇을 뜻하는지 판정해 주십시오.
3. **미측정 항목을 사실로 채우지 마십시오.** 특히 신뢰도(반분 상관)는 이 저장소에 어떤 측정값도 없습니다. 필요하다면 **측정 길이(투구 수)를 명시한 측정 설계**를 답으로 주십시오 — 원값과 스피어만-브라운 환산값을 뭉치지 말고 둘 다 라벨과 함께 보고하는 형식을 전제로.
