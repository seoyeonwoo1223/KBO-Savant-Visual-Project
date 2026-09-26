# SBJ · APR 인계장 + 검증 요청서 (2026 시즌, 기준 커밋 `ed806226`)

이 문서는 **인계장이면서 검증 요청서**입니다. 감사 요청서가 아닙니다.
읽는 분(ChatGPT)이 이 문서 하나만으로 (a) 직전 감사 이후 무엇이 바뀌었는지 알고,
(b) 그게 맞는지 직접 재계산해 대조하고, (c) 남아 있는 작업을 바로 이어서 시작할 수 있도록
필요한 코드·수치·절차를 문서 안에 모두 옮겨 실었습니다. 저장소 파일 참조로 내용을 대신하지 않았습니다.

---

## 0. 검토자에게 — 먼저 읽을 것

### 0.1 당신의 직전 판정 중 하나가 뒤집혔습니다 (Q1)

직전 감사(기준 커밋 `07f76ed1`)에서 당신은 Q1에 대해 **"SBJ와 `za_raw`의 동일성 딜레마는 거짓 딜레마"**
라고 판정했습니다. 그 판정은 **그 시점 코드에 대해서는 옳았습니다.** 당시 SBJ는 맥락 포함 콜 모델
`p_CalledStrike`를 읽고 있었고, 기준선(`expected_judgment_accuracy`)은 다른 확률 `p_zone`을 읽고
있었으므로, 기준선을 빼도 `za_raw`가 되지 않았습니다. 두 항의 확률이 달랐기 때문입니다.

**현재 커밋 `ed806226`에서는 딜레마가 실재합니다.** SBJ를 위치 전용 모델 `p_zone`으로 되돌렸고,
기준선도 같은 `p_zone`을 읽도록 맞췄기 때문에, 이제 기준선을 빼면 **정확히 `za_raw`가 됩니다.**
2026 실데이터에서 `max |(SBJ − 기대정확도) − za_raw| = 1.0000000133e-06` (반올림 6자리 때문에 남는
잔차이며 대수적으로는 0).

즉 **기준선 미차감은 이제 설계 선택이 아니라 구조적 제약입니다.** "난이도 보정을 하려면 빼면 되지 않나"
라는 제안은 현재 정의에서 `za_raw`를 다른 이름으로 다시 만드는 일이 됩니다. 이 점을 전제로 Q1을
다시 판정해 주십시오. 재판정이 필요한 것은 "딜레마의 실재 여부"가 아니라 **"동일성이 실재하는
상태에서 SBJ를 `za_raw`와 별도로 공표할 근거가 있는가"** 입니다.

### 0.2 대조해 주실 것

1. 5절 2026 실측치 — 재현 스크립트가 10절에 있습니다. 저장소 접근이 없다면 표 내부 정합성
   (예: `A+B+C+D = pitches_seen`, 상관과 순위 변동의 방향 일관성)만이라도 확인해 주십시오.
2. 6절 ABS 근거 — `sz_top`/`sz_bottom`이 타자당 상수라는 사실, 그리고 그로부터 "투구별 심판 판단
   존은 데이터에 담긴 적이 없다"는 추론이 성립하는지.
3. 6.3절 **철회되는 진단** — 이전 감사 문서에 있던 "`d ≤ 1` 규칙 잔차 4.87%, 그 중 88.2%가
   한 방향 → 존이 실제보다 좁다"는 결론의 철회 범위가 적절한지. 산술은 살아 있고 해석만
   철회한다는 이 문서의 입장을 검토해 주십시오.
4. 7절 심판 효과 상한 — 결론("2024년 이전 SJ에 심판 ID 크롤링은 불필요")이 제시된 수치로
   지지되는지. **주의: 이 표의 유의성 판정은 구현 세부에 민감합니다** (7.3절에 재현 결과와
   인계값의 차이를 그대로 실었습니다).
5. 12절에 열거된 미검증 항목 중, 산출물 공표를 막아야 할 만큼 심각한 것이 있는지.

### 0.3 이어서 해 주실 것

13절 "남은 작업" 5개 항목입니다. 1번(300구 자격선 재도출)과 2번(`p_zone` 외삽 진단)이 당신이
직전 감사에서 제시한 절차를 그대로 실행하는 일이며, 우선순위가 가장 높습니다.

---

## 1. 저장소 상태 (재현 기준점)

| 항목 | 값 |
|---|---|
| 저장소 경로 | `/home/user/KBO-Savant-Visual-Project` |
| 브랜치 | `claude/happy-hopper-g1h339` |
| 기준 커밋 (HEAD) | `ed806226388fcf186bc8f4ce574d7826cbc40f87` (`ed806226`) |
| 커밋 시각 | 2026-09-21 10:49:55 +0000 |
| 워킹 트리 | 깨끗함 (`git status --porcelain` 출력 없음), 원격 푸시 완료 |
| Python | 3.12. 가상환경 `.venv/`, 패키지는 `constraints-za.txt` 고정 버전 |
| 필수 환경변수 | `PYTHONPATH=src` |

### 1.1 직전 감사 이후 커밋 2개

당신의 직전 감사 기준 커밋은 `07f76ed1`이었습니다. 그 뒤 아래 2개가 추가되었습니다.

| 커밋 | 제목 | 변경 파일 |
|---|---|---|
| `c232584c` | 외부 감사 1·3번 반영: 거짓 딜레마 제거와 + 점수 공표 제한 | `src/visualbaseball/zone_decision.py` (+25/−9 라인), `tests/test_zone_decision.py` (+20) |
| `ed806226` | SBJ를 위치 전용 ABS 존 모델로 되돌리고 맥락 모델은 진단으로 격하 | `src/visualbaseball/zone_decision.py` (+59), `tests/test_zone_decision.py` (+51/−44) |

`07f76ed1..ed806226` 전체 변경은 **이 2개 파일뿐**입니다 (총 +97/−48 라인). 모델 적합 경로
(`score_crossfit`, `fit_predict`, `predict_pzone`, `_crossfit_action_values`)는 **한 줄도 바뀌지
않았습니다.** 확인 방법:

```bash
git diff 07f76ed1..ed806226 -- src/visualbaseball/zone_decision.py \
  | grep '^[-+]' | grep -v '^[-+][-+]' \
  | grep -E 'fit_predict|score_crossfit|predict_pzone|_crossfit'
# 출력: 주석·계약 문자열 3줄만. 함수 본문 변경 없음.
```

이 사실이 중요한 이유: 두 커밋은 **투구 단위 모델 출력을 바꾸지 않고 집계만 바꿨습니다.** 따라서
이전 실행에서 캐시된 투구 단위 채점 결과로 현재 지표를 재현할 수 있고, 5절 실측치는 실제로 그렇게
재현했습니다 (10절 스크립트 참조).

---

## 2. 용어 — 저장소 내부 용어를 전부 풀어서 정의

| 저장소 용어 | 뜻 |
|---|---|
| **curated** | 원본 공개 PBP JSON을 정규화해 저장한 canonical Parquet 테이블. `pitches`(투구), `events`(사건), `games`(경기) 세 테이블. 모든 지표는 여기서만 읽습니다. |
| **decision_pitches** | "타자가 스윙할지 말지를 실제로 선택한 상황"만 남긴 투구 부분집합. 번트 시도, 판정 불명, 좌표 결측, 타자 신원 불명은 제외됩니다. 이후 모든 판단 지표의 공통 입력입니다. **이 문서에서는 "자격 투구(eligible pitch)"** 로 부릅니다. |
| **ZA v7** | Zone Awareness 모델의 7번째 세대. 이 문서가 다루는 코드 모듈 `src/visualbaseball/zone_decision.py`의 버전 이름이며, 산출물에 기록되는 모델 식별자는 `za7-strikezone-judgment`입니다. |
| **자격 타자 (qualified)** | 해당 시즌 자격 투구 **300구 이상**을 본 타자. 코드 필드명 `qualified_300`. |
| **`S`** | 그 투구에 대한 **실제** 행동. 스윙이면 1, 지켜봤으면(take) 0. |
| **`p_swing`** | **리그 평균 타자**가 그 투구에 스윙할 추정 확률. 타자 개인 정체성은 입력에 들어가지 않습니다. 교차적합. |
| **`p_zone`** | **이름이 오해를 부르는 필드입니다.** 존 통과 확률이 아니라, **테이크 투구만으로 적합한 "콜 스트라이크 vs 볼/HBP" 2-클래스 모델의 예측 확률**입니다. 특징은 위치 4개뿐(`x_relative`, `z_relative`, `sz_top`, `sz_bottom`). 실질 이름은 `p_called_strike_position`입니다. 필드명을 유지하는 이유는 3.3절에 있습니다. |
| **`p_CalledStrike`** | 같은 목표를 **전체 특징**(카운트, 구속, 무브먼트, 구종, 스탠스, 구장 포함)으로 적합한 3-클래스 모델의 콜 스트라이크 확률. HBP를 분리합니다. |
| **`x_relative` / `z_relative`** | 해당 타자의 존 사각형 경계가 ±1이 되도록 정규화한 좌표. 포수 시점. **타자 신장 보정이 이미 내장되어 있습니다.** |
| **`d`** | `max(|x_relative|, |z_relative|)`. 이 저장소의 구역 분류에 쓰는 max-norm 거리. `d ≤ 2/3` Heart, `≤1` Shadow-in, `≤4/3` Shadow-out, `≤2` Chase, `>2` Waste. |
| **`za_raw`** | 기존 지표. `100 × mean((S − p_swing) × (2·p_zone − 1))`, 단위 percentage point. |
| **DV / `dv_per_100`** | Decision Value. 교차적합된 스윙 가치 `v_swing`과 테이크 가치 `v_take`의 차이를 실제 선택 방향으로 누적한 값. 100구당 득점(run). |
| **`delta_v`** | `v_swing − v_take`. 그 투구에서 "스윙이 테이크보다 득점가치상 얼마나 나은가". |
| **ABS** | Automated Ball-Strike system. KBO는 2024 시즌부터 전 경기 적용. |
| **`?v=` 캐시 버스터** | 정적 웹 페이지의 `<link>`/`<script>` URL에 붙는 쿼리 문자열. GitHub Pages 캐시 갱신을 강제하는 수단. |

---

## 3. 바뀐 것 — 4가지

### 3.1 SBJ가 위치 전용 ABS 존 모델로 확정

```
SBJ_raw = 100 × mean( 스윙이면 p_zone, 테이크이면 1 − p_zone )     [단위: %]
SBJ+    = 100 + 15 × (SBJ_raw − 자격자 평균) / 자격자 모표준편차(ddof=0)
          단, 자격 투구 300구 미만 타자는 null
```

코드 원문 (`src/visualbaseball/zone_decision.py`, 들여쓰기는 저장소 그대로 1-스페이스):

```python
def _correct_share(row):
 """Share of this pitch the hitter judged correctly, PLV Strikezone Judgement style.
 ...
 """
 return row['p_zone'] if row['swing'] else 1-row['p_zone']


def _league_correct_share(row):
 # The same pitch judged by a league-average swing policy instead of this hitter.
 return row['p_swing']*row['p_zone']+(1-row['p_swing'])*(1-row['p_zone'])


def strikezone_ball_judgment(items):
 """SBJ: PLV-style strike/ball judgment accuracy against the ABS zone, in percent.

 Raw accuracy, with no expectation subtracted. Subtracting the league-average
 policy gives mean((S - p_swing) * (2*p_zone - 1)), which IS za_raw - that
 identity is why the baseline stays out, and it is a real constraint here
 because SBJ now reads the same p_zone that za_raw does.
 """
 return r6(100*np.mean([_correct_share(r) for r in items])) if items else None


def add_sbj_plus(players):
 """SBJ+ on the repo scale: 100 + 15 * z against the qualified population."""
 qualified=np.array([p['sbj_raw'] for p in players if p['qualified_300'] and p['sbj_raw'] is not None],dtype=float)
 center=float(qualified.mean()) if len(qualified) else 0
 spread=float(qualified.std()) if len(qualified) else 0
 for p in players:
  # Standardized on the qualified distribution, so only qualified hitters carry it.
  p['sbj_plus']=r6(100+15*(p['sbj_raw']-center)/spread) if spread and p['qualified_300'] and p['sbj_raw'] is not None else None
 return center,spread
```

`np.std`는 기본 `ddof=0`이므로 **모표준편차**입니다. 이 문서의 모든 sd 표기는 `ddof=0`입니다.

**직전 감사 시점(`07f76ed1`)과의 차이**: 당시 `_correct_share`는 `p_CalledStrike`(맥락 포함)를
읽고 있었습니다. 되돌린 이유는 6절 ABS 근거입니다.

#### 3.1.1 동일성 — 기준선을 빼면 정확히 `za_raw`

대수 유도:

```
SBJ/100   = mean( S·q + (1−S)·(1−q) )                q = p_zone, S ∈ {0,1}
기대/100  = mean( p·q + (1−p)·(1−q) )                p = p_swing
차이      = mean( (S−p)·q + (p−S)·(1−q) )
          = mean( (S−p)·(2q−1) )                     = za_raw/100
```

실데이터 확인 (2026 전체 285명): `max |(SBJ − 기대정확도) − za_raw| = 1.0000000133236764e-06`.
남은 1e-06은 세 값이 각각 소수 6자리로 반올림되기 때문이며, 대수적으로는 0입니다.

이 동일성을 고정하는 테스트가 있습니다. 원문:

```python
def test_subtracting_the_league_baseline_would_reproduce_zone_awareness():
 # This identity is the reason SBJ subtracts no baseline. Pin it so nobody
 # "adds difficulty adjustment" by subtraction and silently recreates za_raw.
 rng=np.random.default_rng(5)
 items=[_judgment_row(int(rng.integers(0,2)),float(rng.uniform(.05,.95)),
   float(rng.uniform(.05,.95))) for _ in range(200)]
 difference=strikezone_ball_judgment(items)-expected_judgment_accuracy(items)
 assert abs(difference-zone_awareness(items))<1e-4
```

이 테스트의 목적은 동일성을 **자랑하는 것이 아니라 봉인하는 것**입니다. 누군가 나중에 "난이도
보정"을 차감으로 추가하면 `za_raw`가 조용히 재생산되므로, 그 변경이 테스트 실패로 드러나게
해 두었습니다.

#### 3.1.2 맥락 버전은 진단으로 격하

```python
def _contextual_correct_share(row):
 # Same question asked of the full call model: count, movement, park included.
 return row['p_CalledStrike'] if row['swing'] else row['p_Ball']+row['p_HBP']
```

`sbj_raw_contextual`로 산출물에 남지만 **공표 지표가 아닙니다.** 2026에서 `sbj_raw`와 상관
+0.9976, 순위 변동 평균 3.08계단 / 최대 17계단이므로 선수 수준의 두 번째 측정이 아니라 콜 모델
견고성 점검값입니다.

#### 3.1.3 PLV / Strikezone Judgement와의 관계 — 복제가 아닙니다

SBJ는 PLV(Pitch Level Value) 계열의 Strikezone Judgement와 **같은 질문 형태**를 씁니다:
"이 투구를 지켜봤다면 스트라이크로 선언됐을 확률에 비례해 스윙을 옳다고 본다."

그러나 **정확한 복제품이 아니며, 그렇게 주장하지 않습니다.** 사람 심판 리그에서 PLV 계열 콜
확률에는 심판 성향 성분이 섞여 있고, 그것이 지표의 일부입니다. ABS 리그에서는 그 성분이 **존재
자체를 하지 않습니다.** 따라서 위치 전용 모델이 ABS 환경에서 PLV의 *의도*(타자가 존을 얼마나
정확히 읽었는가)에 더 가깝다는 것이 우리 논지이며, 구현·특징집합·보정 절차가 PLV와 같다는
주장은 하지 않습니다. 외부 지표와의 수치 상호 비교도 하지 않습니다.

### 3.2 APR이 가치 기반 SEAGER로 교체

```
hittable  := delta_v > 0        (교차적합 모델이 "스윙이 테이크보다 득점가치상 낫다"고 본 투구)
A = hittable 스윙,  B = non-hittable 스윙,  C = hittable 테이크,  D = non-hittable 테이크
ST  (selection_tendency_pct) = 100 × D / (A + D)
HPT (hittable_take_pct)      = 100 × C / (C + D)
APR_raw = ST − HPT
APR+    = 100 + 15 × z (자격자 분포, ddof=0). 300구 미만 null
```

코드 원문:

```python
def seager_quadrants(items):
 """Split decisions into SEAGER's A/B/C/D on run value rather than zone membership.

 A pitch is hittable when delta_v > 0, i.e. the cross-fit models expect swinging
 to be worth more runs than taking. That makes the split count-aware: the same
 location can be hittable at 3-1 and not at 0-2. delta_v <= 0 is non-hittable,
 so every eligible pitch lands in exactly one quadrant.
 """
 counts={'A':0,'B':0,'C':0,'D':0}
 for r in items:
  hittable=r['delta_v']>0
  if r['swing']: counts['A' if hittable else 'B']+=1
  else: counts['C' if hittable else 'D']+=1
 return counts


def selection_tendency(counts):
 """Share of correct decisions that were takes: D / (A + D)."""
 total=counts['A']+counts['D']
 return r6(100*counts['D']/total) if total else None


def hittable_take_rate(counts):
 """Share of takes that passed on a hittable pitch: C / (C + D)."""
 total=counts['C']+counts['D']
 return r6(100*counts['C']/total) if total else None


def approach_rating(counts):
 """APR: value-based SEAGER, selection tendency minus hittable takes."""
 tendency,given_up=selection_tendency(counts),hittable_take_rate(counts)
 return r6(tendency-given_up) if tendency is not None and given_up is not None else None
```

- `plate_discipline.simple_seager`의 산식을 그대로 따르고, **hittable 정의만** 존 소속에서
  `delta_v > 0`으로 바꿨습니다. 그래서 **카운트 인식적**입니다: 같은 위치가 3-1에서는 hittable,
  0-2에서는 아닐 수 있습니다.
- 새 모델을 만들지 않았습니다. 이미 교차적합된 `v_swing`/`v_take`를 재사용합니다.
- 이전 세대의 구역 가중 APR(SBJ와 상관 0.98로 사실상 중복)은 **제거**했고, 구역별 SBJ
  (`heart_sbj`, `shadow_in_sbj`, …)만 진단용으로 남겼습니다.
- `delta_v <= 0`이 non-hittable이므로 모든 자격 투구가 정확히 한 사분면에 들어갑니다
  (`A+B+C+D == pitches_seen`, 2026 285명 전원 성립 — 5.4절).
- APR은 **선택적 공격성의 균형**을 재는 지표이며 득점 이득의 크기가 아닙니다. 크기는
  `dv_per_100`입니다.

### 3.3 공표 정책 — `+` 점수와 필드명

**(a) 300구 미만 타자에게 `+` 점수를 주지 않습니다.** `sbj_plus`, `apr_plus`, `dv_plus` 모두
null입니다. 자격자 분포로 표준화한 값을 소표본에 적용하면 표본오차가 15점 스케일로 증폭되기
때문입니다. 원시 구성요소(`sbj_raw`, `apr_raw`, `dv_per_100`, 사분면 개수 등)는 진단용으로 계속
제공합니다.

`dv_plus`는 **직전 감사 시점에 전원에게 값을 주고 있었습니다.** 현재 코드:

```python
def add_dv_plus(players):
 qualified=np.array([p['dv_per_100'] for p in players if p['qualified_300']],dtype=float)
 center=float(qualified.mean()) if len(qualified) else 0
 spread=float(qualified.std()) if len(qualified) else 0
 # Standardized on the qualified distribution, so only qualified hitters carry it.
 for p in players: p['dv_plus']=r6(100+15*(p['dv_per_100']-center)/spread) if spread and p['qualified_300'] else (100 if p['qualified_300'] else None)
 return center,spread
```

실측: 2026 비자격 타자 **122명 전원**이 `sbj_plus`/`apr_plus`/`dv_plus` 모두 null
(재현 확인, 10.2절 스크립트 출력 `unqualified with any + score: 0`).

대조용으로, **현재 커밋된 산출물**(`web/data/zone_awareness/2026/leaderboard.json`, 이전 실행물)
에서는 비자격 122명이 `dv_plus` 값을 가지고 있으며 `-59.85`, `-51.77`, `-37.91` 같은 값이
들어 있습니다. 즉 커밋된 산출물은 이 정책 변경 이전 상태이며, 재생성이 필요합니다(13.3절).

**(b) `p_zone`이 존 소속 확률이 아니라는 사실을 계약(`CONTRACT`)에 명시했습니다.** 필드명은
유지했습니다. 이유는 `web/zone-awareness/zone-awareness.js`가 이 이름을 읽기 때문입니다. 해당
라인 원문:

```javascript
const fields = ["swing_pct","expected_swing_pct","p_zone_pct","zone_judgment_pct",
                "expected_zone_judgment_pct","za_raw","expected_swing_rv","expected_take_rv"];
```

계약 문자열 원문:

```python
'p_zone': 'MISNOMER kept for payload compatibility. Not zone membership: predict_pzone fits a
 take-only CalledStrike vs Ball/HBP model on four positional features (x_relative, z_relative,
 sz_top, sz_bottom) in two classes. Read it as p_called_strike_position. p_CalledStrike is the
 same target with the full feature set in three classes.',
```

모델 본체 (`src/visualbaseball/plate_decision_v1.py`):

```python
PZONE_NUMERIC = ("x_relative", "z_relative", "sz_top", "sz_bottom")

def predict_pzone(train: list[dict], test: list[dict]) -> np.ndarray:
    """Fit the take-only CalledStrike vs Ball/HBP model and score held-out pitches."""
    take = [row for row in train if row["decision_type"] == "Take"]
    target = np.array([str(row.get("pitch_call_code") or "").upper() == "T"
                       or row.get("event") == "CalledStrike" for row in take], dtype=int)
    model = _classifier().fit(_encode_numeric(take, PZONE_NUMERIC), target)
    probability = model.predict_proba(_encode_numeric(test, PZONE_NUMERIC))[:, list(model.classes_).index(1)]
    return np.clip(probability, 1e-6, 1 - 1e-6)
```

`_classifier()`는 `HistGradientBoostingClassifier(learning_rate=0.07, max_iter=130,
max_leaf_nodes=20, min_samples_leaf=80, l2_regularization=1.5, random_state=고정)`입니다.
교차적합은 날짜 3블록(`CROSSFIT_FOLDS = 3`)으로, 어떤 투구도 자기 경기 날짜 블록이 포함된
학습 데이터로 채점되지 않습니다.

**여기서 미해결로 남는 것**: 이 모델은 **테이크 투구만으로** 적합되고, **스윙 투구에도 적용**됩니다.
즉 반사실 외삽이며, 그 품질은 미검증입니다(13.2절, 12절 U-항목).

### 3.4 ABS 근거 — 왜 위치 전용으로 되돌렸는가

6절 전체가 이 근거입니다. 요약하면:

1. 제공 데이터의 존 경계(`sz_top`/`sz_bottom`)는 **타자당 상수**입니다. 사람 심판 시절
   (2022–2023)에도 마찬가지였습니다. 즉 **투구별 심판 판단 존은 이 데이터에 담긴 적이 없습니다.**
2. KBO는 2024부터 ABS를 씁니다. 자동 판정에는 카운트·구종·구장이 인과적 역할을 하지 않습니다.
3. 맥락 모델이 관측 콜을 더 잘 맞히는 것은 사실입니다(2026 테이크 오분류 1.23% → 0.89%).
   그러나 그 0.34%p는 **카운트·구종·구장을 판단력 지표에 끌어들이는 대가**로 사는 것이고,
   선수 수준 차이는 상관 0.9976 / 순위 평균 3.08계단으로 미미하므로 거래가 성립하지 않습니다.

코드 주석에 이 논지를 그대로 박아 두었습니다(`_correct_share` docstring, 3.1절 인용 참조).

---

## 4. 데이터 범위

출처는 `data/curated/summary.json`(4KB 요약본)과 각 시즌 자격 투구 재계산입니다.

| 시즌 | curated `pitches` 행수 | 경기 | 자격 투구(eligible) | 자격 타자(300구+) | 테이크 | 판정 체계 |
|---|---|---|---|---|---|---|
| 2022 | 217,025 | 720 | 214,637 | 163 | 116,066 | 사람 심판 |
| 2023 | 219,839 | 720 | 215,392 | 173 | 118,573 | 사람 심판 |
| 2024 | (summary.json 참조) | 720 | 222,225 | 155 | 121,112 | ABS |
| 2025 | (summary.json 참조) | 720 | 217,623 | 171 | 119,311 | ABS |
| 2026 | (진행 중) | 626 (자격 투구 기준) | **192,526** | **163** | 106,519 | ABS |

- curated 레이아웃은 2025·2026이 월별 partition, 2022–2024가 경기 단위 shard입니다.
  2022–2024는 원본 JSON이 남아 있지 않아 curated가 유일한 사본입니다(삭제 금지).
- 2026은 시즌 진행 중이므로 경기 수가 적습니다. 자격 투구에 등장하는 경기는 626개입니다.
- "자격 투구"는 2절 정의(`decision_pitches`)입니다. 번트·판정 불명·좌표 결측·신원 불명 제외,
  그리고 득점 타임라인이 검증되지 않은 이닝 반쪽(`reliable_halves`)도 제외됩니다.
- **시즌을 섞지 않습니다.** 연도별 득점가치와 리그 평균은 해당 시즌 데이터만으로 계산합니다.

---

## 5. 2026 실측 (검증됨 — 이 문서 작성 중 직접 재현)

전부 커밋 `ed806226`의 코드로 재현했습니다. 재현 스크립트는 10.2절에 있습니다.

전체 타자 **285명**, 자격 타자 **163명**, 자격 투구 **192,526구**.

### 5.1 자격 타자 163명 기술통계 (sd는 ddof=0)

| 지표 | mean | sd | 최솟값 | 최댓값 |
|---|---|---|---|---|
| `sbj_raw` (%) | +68.0844 | 3.0928 | +56.83 | +74.29 |
| `sbj_raw_contextual` (%) | +67.8586 | 3.0940 | +57.00 | +73.99 |
| `expected_judgment_accuracy_pct` (%) | +68.5775 | 0.9809 | +64.75 | +71.04 |
| `za_raw` (pp) | −0.4931 | 2.8890 | −8.34 | +5.78 |
| `apr_raw` (pp) | +23.4932 | 5.2423 | +5.93 | +34.95 |
| `dv_per_100` (runs/100) | +6.0288 | 0.9317 | +3.59 | +8.03 |

**짚어야 할 점**: `expected_judgment_accuracy_pct` 평균(68.5775)이 `sbj_raw` 평균(68.0844)보다
**높습니다.** 즉 자격 타자 평균 `za_raw`가 0이 아니라 −0.4931입니다. 리그 평균 스윙 정책이
실제 타자 평균보다 판정 정확도가 높게 나온다는 뜻이고, 이는 표면상 역설입니다. 원인은
**미검증**입니다(12절 U-2 참조).

### 5.2 상관 / 순위 변동 (자격 타자 163명)

순위는 각 지표 내림차순 midrank 없이 `argsort` 기준, 변동은 절대값입니다.

| 쌍 | Pearson corr | 순위 변동 평균 | 최대 |
|---|---|---|---|
| SBJ ↔ contextual SBJ | +0.9976 | 3.08 | 17 |
| SBJ ↔ `za_raw` | +0.9485 | 12.05 | 52 |
| SBJ ↔ APR | +0.6018 | 33.47 | 127 |
| SBJ ↔ DV/100 | +0.6340 | 31.91 | 123 |
| APR ↔ DV/100 | +0.5776 | 33.55 | 122 |
| APR ↔ `za_raw` | +0.5435 | 36.75 | 133 |

해석 요지: SBJ와 `za_raw`는 상관 0.9485인데 순위 최대 변동이 52계단입니다. 3.1.1절의 동일성이
있으므로 두 지표의 차이는 **전적으로 기대정확도(난이도) 항**에서 나옵니다. SBJ와 APR은 상관
0.60으로 분리된 정보를 담고 있습니다.

### 5.3 SEAGER 사분면

**주의 — 두 집계 범위를 구분합니다.** 이 문서에 인계된 원 수치는 자격자 163명 합계였으므로
아래에 둘 다 싣습니다(14절 참조).

| 범위 | A (hittable 스윙) | B (non-hit 스윙) | C (hittable 테이크) | D (non-hit 테이크) | 합계 | hittable 비중 |
|---|---|---|---|---|---|---|
| **자격자 163명** | 55,351 | 25,279 | 31,719 | 68,874 | 181,223 | 48.0458% |
| **전체 285명 (리그)** | 59,001 | 27,006 | 33,614 | 72,905 | 192,526 | 48.1052% |

- `A + B + C + D == pitches_seen`이 **285명 전원**에서 성립합니다 (재현 확인).
- 자격자 평균 ST = 55.0396%, 자격자 평균 HPT = 31.5463%. 차이 23.49pp가 5.1절 `apr_raw` 평균과
  일치합니다(선수별 평균이므로 리그 합계 비율과는 다릅니다).

### 5.4 테스트 (검증됨 — 실행함)

| 명령 | 결과 |
|---|---|
| `PYTHONPATH=src python -m pytest -q` | **118 passed** (12.88s) |
| `tests/test_zone_decision.py` 내 테스트 함수 | **25개** (`grep -c '^def test_'`) |
| `node tests/test_pitch_arsenal_layout.cjs` | **PASS** (`1/2/4/5/6/9 pitches, split/overall usage, proportional bars, chart bounds, empty data`) |

`tests/test_zone_decision.py`의 25개 테스트 목록 (이름이 곧 명세입니다):

```
test_decision_value_credits_the_actual_choice
test_zone_awareness_is_outcome_independent_and_value_version_is_retained
test_sa_dv_stay_unchanged_and_dv_plus_is_standardized
test_five_regions_and_hbp_not_future_pa_result
test_additive_contributions_use_all_pitches
test_target_events_are_not_model_features
test_re_table_is_training_only_and_terminal_state_zero
test_score_repairs_are_not_fabricated_pitch_runs
test_constrained_re_preserves_ordinary_baseball_transitions
test_actual_fitted_predictions_ignore_held_out_results
test_sbj_credits_zone_chance_on_swings_and_its_complement_on_takes
test_sbj_reads_the_positional_zone_model_not_the_contextual_one
test_sbj_is_not_zone_awareness_even_though_both_read_p_zone
test_subtracting_the_league_baseline_would_reproduce_zone_awareness
test_sbj_is_outcome_independent_like_zone_awareness
test_expected_judgment_baseline_uses_the_same_zone_model_as_sbj
test_sbj_plus_is_standardized_over_qualified_hitters
test_seager_quadrants_partition_every_pitch
test_seager_uses_run_value_not_zone_membership
test_selection_tendency_and_hittable_takes_follow_the_repo_formula
test_apr_direction_rewards_taking_bad_pitches_and_punishes_passing_good_ones
test_apr_is_none_when_a_ratio_has_no_denominator
test_apr_plus_is_standardized_over_qualified_hitters
test_profile_summary_exposes_seager_quadrants_summing_to_pitches_seen
test_plus_scores_are_withheld_below_the_qualification_minimum
```

주의: 이 25개는 **단위 테스트**입니다. 합성 행(`_judgment_row`)으로 산식·경계·표준화·공표 정책을
고정하며, 모델 품질이나 지표 타당성을 검증하지 않습니다.

---

## 6. ABS 근거와 철회되는 진단 (이 문서의 핵심)

### 6.1 `sz_top` / `sz_bottom`은 타자당 상수다 (검증됨 — 5시즌 전부 재현)

각 시즌 자격 투구에서 300구 이상 본 타자만 대상. "고유값 개수"는 해당 타자의 모든 투구에서
`sz_top`(또는 `sz_bottom`)이 취하는 서로 다른 값의 개수입니다.

| 시즌 | 자격 타자 | 고유값 개수 중앙값 | 타자 내 sd 중앙값 | 고유값 1개인 타자 (`sz_top`) | 고유값 1개 (`sz_bottom`) | 리그 전체 고유값 `sz_top` | `sz_bottom` |
|---|---|---|---|---|---|---|---|
| 2022 | 163 | 1 | 0.00000 ft | 160 | 159 | 166 | 156 |
| **2023** | **173** | **1** | **0.00000 ft** | **162** | **160** | **187** | **168** |
| 2024 | 155 | 1 | 0.00000 ft | 149 | 150 | 161 | 151 |
| 2025 | 171 | 1 | 0.00000 ft | 166 | 166 | 160 | 144 |
| **2026** | **163** | **1** | **0.00000 ft** | **156** | **155** | **146** | **135** |

읽는 법:

- 리그 전체 고유값이 140~190개 수준이고 타자 수가 155~173명입니다. 즉 **값의 개수 ≈ 타자의 수**
  입니다. 존 경계는 타자별로 하나씩 부여된 상수입니다.
- 타자 내 sd 중앙값이 정확히 0입니다. 고유값이 2개 이상인 소수의 타자는 시즌 중 신장·자세
  정보가 갱신된 경우로 보이며, 투구별 변동이 아닙니다.
- **2023(사람 심판)도 2026(ABS)과 완전히 같은 구조입니다.** 따라서 **투구별 심판 판단 존이
  이 데이터에 담긴 적은 한 번도 없습니다.** 사람 심판 시절에도 제공 데이터는 신장 기반 사각형
  이었습니다.
- `x_relative`/`z_relative`는 그 타자 자신의 사각형으로 정규화된 값입니다. 즉 **타자 신장 보정이
  이미 좌표에 내장**되어 있고, 위치 전용 모델에 `sz_top`/`sz_bottom`을 넣는 것은 사각형 크기
  정보를 한 번 더 주는 것입니다.

### 6.2 관측 테이크의 콜 예측 비교 (2026, 검증됨)

대상: 2026 자격 투구 중 테이크 **106,519개**(경기 626개). 목표는 `event == 'CalledStrike'`.

| 방식 | 오분류 | log loss | Brier |
|---|---|---|---|
| 기하 `d ≤ 1` 경성 규칙 | **5.4497%** | — (확률 아님) | — |
| 기하 + 배율 fold 외 적합 | **3.56%** (아래 주 참조) | 0.11384 ※ | 0.030240 ※ |
| `p_zone` (위치 전용, 특징 4개) | **1.2289%** | **0.03968** | **0.009801** |
| `p_CalledStrike` (맥락 전체) | **0.8909%** | **0.02813** | **0.007156** |

- 1·3·4행은 정확히 재현했습니다.
- 2행 "기하 + 배율 fold 외 적합"의 **오분류 3.56%는 두 가지 구현에서 모두 재현**됩니다:
  `d` 한 개를 특징으로 한 날짜 3블록 교차적합 로지스틱 회귀 → 3.5599%, `d ≤ a`의 임계값 `a`를
  fold 밖에서 격자 탐색해 적용 → 3.5637%.
- ※ **2행의 log loss / Brier는 인계된 값(0.11033 / 0.028145)과 일치하지 않습니다.** 위에 실은
  0.11384 / 0.030240은 이 문서 작성 중 "로지스틱(특징 `d` 1개), 날짜 3블록 교차적합" 구현으로
  얻은 값입니다. 원래 산출에 쓰인 정확한 명세가 저장소에 스크립트로 남아 있지 않아 재현할 수
  없었습니다. **이 행의 확률 지표는 재현 미완으로 취급하십시오** (14절).

### 6.3 철회되는 진단 — "존이 실제보다 좁다"

이전 감사 문서 `docs/review/metrics-audit-2026.md`와
`docs/review/SBJ-structure-crossvalidation.md`에 다음 진단이 실려 있었습니다 (원문 요지):

> 2026 무작위 40경기의 called ball/strike 6,945개에서 `d ≤ 1` 규칙 기준 잔차 4.87%,
> 잔차 338건 중 298건(88.2%)이 "규칙은 볼, 실제는 콜 스트라이크" — 즉 규칙 존이 실제보다 좁다.

해당 항목은 그 두 문서에서 **U4 / U13 계열**로 등록되어 있습니다. **이 문서로 대체됩니다.**

철회의 정확한 범위를 구분해 적습니다.

**(a) 산술은 살아 있습니다.** 리그 전체로 다시 재면 `d ≤ 1` 경성 규칙의 오분류는 5.4497%
(잔차 5,805건)이고, 그 중 **5,111건(88.0%)** 이 "규칙은 볼, 실제는 콜 스트라이크" 방향입니다.
40경기 표본의 4.87% / 88.2%는 리그 전체 값과 사실상 같습니다. 즉 숫자 자체가 틀렸다는 뜻이
아닙니다.

**(b) 철회되는 것은 해석입니다.** "존이 실제보다 좁다 / 좌표 또는 존 경계 데이터 품질 문제"라는
결론은 **`d = max(|x_relative|, |z_relative|)`로 사각형을 1차원으로 뭉갠 요약이 만든 착시**였습니다.
`d`는 **어느 축에서 벗어났는지와 부호를 버립니다.** 같은 데이터를 2차원(`x_relative`,
`z_relative`)으로 다루면 오분류가 **1.23%** 로 떨어집니다(6.2절). 데이터가 재현할 수 없는
판정을 담고 있는 것이 아니라, **max-norm 정사각형 경성 규칙이 틀린 함수 형태**였던 것입니다.
따라서:

- 좌표 품질 문제가 아닙니다.
- 존 경계 계통 오차를 SBJ 전파 경로로 다룰 근거가 약해졌습니다(U4).
- 구역 절단점 이동이 APR에 이산적으로 전파된다는 U13의 전제도, APR이 이제 구역 소속을 쓰지 않고
  `delta_v > 0`을 쓰므로(3.2절) **대상이 사라졌습니다.**
- 남는 진짜 위험은 존 경계가 아니라 **`p_zone`의 테이크 → 스윙 외삽**입니다(13.2절).

---

## 7. 심판 효과 상한 측정

### 7.1 설계

경기마다 주심은 1명입니다. 따라서 **경기 효과의 크기는 심판 효과의 상한**입니다(경기 효과에는
심판 외에 구장·날씨·트래킹 상태 등도 섞이므로 상한입니다).

절차:

1. 각 시즌 테이크 투구에서, 날짜 3블록 교차적합으로 **위치만 쓰는 0.05 단위 2D 격자 모델**을
   적합해 콜 스트라이크 확률을 예측한다 (자기 날짜 블록 제외).
2. 잔차 `residual = 실제 콜(0/1) − 예측 확률`을 만든다.
3. **경기 안에서** 잔차를 무작위로 반으로 나누고, 두 반쪽 평균의 경기 간 상관을 낸다.
   잡음이 이항 잡음뿐이라면 이 상관의 기대값은 **0**이다. 0보다 크면 경기 단위로 공유되는
   체계적 성분(= 심판 효과의 상한)이 있다는 뜻이다.
4. 경기 단위 부트스트랩 2,000회로 95% CI를 낸다.

### 7.2 인계된 표 (원래 산출값)

| 시즌 | 테이크 | 경기 | 위치모델 오분류 | 경기 내 반분 잔차 상관 (95% CI) |
|---|---|---|---|---|
| 2022 | 116,066 | 714 | 9.42% | +0.1197 [+0.0425, +0.1949] |
| 2023 | 118,574 | 708 | 9.21% | +0.0765 [−0.0014, +0.1544] |
| 2024 | 121,112 | 718 | 1.49% | +0.0107 [−0.0638, +0.0817] |
| 2025 | 119,311 | 720 | 1.51% | −0.0253 [−0.1042, +0.0537] |
| 2026 | 106,519 | 626 | 1.49% | −0.0362 [−0.1204, +0.0538] |

### 7.3 이 문서 작성 중 재현한 표 (독립 재구현, 검증 결과)

원래 산출에 쓰인 격자 모델 스크립트가 저장소에 없어, 위 설계 설명대로 **독립적으로 다시
구현**했습니다(셀 평균에 사전확률 10구 shrinkage, 난수 시드 0, 부트스트랩 2,000회).

| 시즌 | 테이크 (재현) | 경기 (재현) | 격자모델 오분류 (재구현) | 경기 내 반분 잔차 상관 (95% CI, 재구현) |
|---|---|---|---|---|
| 2022 | 116,066 ✓ | 714 ✓ | 9.604% | **+0.0724 [−0.0018, +0.1536]** |
| 2023 | 118,573 (인계값 118,574) | 708 ✓ | 9.195% | **+0.0702 [+0.0041, +0.1531]** |
| 2024 | 121,112 ✓ | 718 ✓ | 1.856% | −0.0190 [−0.0522, +0.0884] |
| 2025 | 119,311 ✓ | 720 ✓ | 1.942% | +0.0055 [−0.0753, +0.0770] |
| 2026 | 106,519 ✓ | 626 ✓ | 1.903% | −0.0452 [−0.1253, +0.0384] |

**일치하는 것**

- 테이크·경기 수는 2023에서 1구 차이를 빼면 전부 일치합니다.
- **정성적 패턴이 그대로 재현됩니다**: 사람 심판 시즌(2022–23)은 오분류가 9%대이고 경기 내
  반분 잔차 상관이 작은 양수, ABS 시즌(2024–26)은 오분류가 2% 미만이고 상관이 0 근처
  (부호는 시즌마다 오락가락).

**일치하지 않는 것 — 검토자가 반드시 볼 부분**

- 재구현 격자 모델의 오분류가 ABS 시즌에서 1.49~1.51% 대신 1.86~1.94%로 높습니다. shrinkage와
  미관측 셀 대체 방식 차이로 보입니다. (동일 시즌 GBM `p_zone`은 1.23%입니다 — 6.2절.)
- **"유의한 시즌"이 바뀝니다.** 인계값에서는 2022만 CI가 0을 넘지 않았고(+0.0425 하한),
  재구현에서는 **2022의 CI가 0을 포함**하고(−0.0018) 대신 **2023이 0을 넘습니다**(+0.0041).
  두 결과 모두 "작은 양의 경기 효과가 사람 심판 시즌에 있다"는 방향은 같지만, **어느 시즌이
  통계적 유의선을 넘는지는 구현 세부에 민감**합니다.

### 7.4 시즌 합산 희석

심판(경기) 효과가 경기 간 독립이라면, 한 타자의 시즌 합산 지표에서 그 성분은 `1/√(경기 수)`로
희석됩니다.

| 시즌 | 자격 타자 | 타자당 경기 수 중앙값 | 최소 | 최대 | 희석 배수 `1/√중앙값` |
|---|---|---|---|---|---|
| 2023 | 173 | **86** (전 투구) / 84 (좌표 non-null 필터) | 22 | 142 | **0.1078** / 0.1091 |
| 2026 | 163 | **75** | 24 | 128 | **0.1155** (인계값 0.115) |

(2023 중앙값 86과 84의 차이는 행 필터 때문입니다. 86은 `pitches` 전 행 기준, 84는 `px`/`pz`/`sz_*`가 모두 non-null인 행만 남긴 뒤의 값입니다. 어느 쪽도 오류가 아니며, 희석 배수는 0.108~0.109로 결론에 영향이 없습니다 — 14절 D2~D4.)

### 7.5 결론 (우리 판단 — 검토 대상입니다)

**2024년 이전 시즌의 판정 지표를 구할 때 심판 ID를 크롤링할 필요가 없다.** 근거:

- (a) 경기 효과는 사람 심판 시즌에서만 나타나고 크기가 작습니다 (r ≈ 0.07~0.12). 상한 해석이므로
  순수 심판 효과는 이보다 작습니다.
- (b) 2022–23의 9% 미설명 콜은 대부분 **투구 단위 잡음**(좌표 오차, 프레이밍, 같은 심판의 경기 내
  비일관성)이며, 심판 ID를 알아도 고칠 수 없는 성분입니다. 심판 ID로 설명될 수 있는 최대치는
  경기 효과 크기로 제한됩니다.
- (c) 시즌 합산 지표에서는 그 성분이 `1/√84 ≈ 0.109`배로 희석됩니다.
- 리그 전체 존 형태의 시즌 간 차이는 **콜 모델을 시즌별로 그 시즌 데이터에만 적합**시키면
  흡수됩니다. 현재 코드가 이미 그렇게 합니다 (`build_zone_decision(root, season)`이 시즌마다
  독립 실행).

**단, 2022–23 SBJ는 ABS 시즌과 비교 가능하지 않습니다.** 위치 모델의 미설명 콜이 1.5% 대 9.2%로
약 6배입니다. 측정 잡음의 크기가 다르므로 통합 리더보드나 시즌 간 순위 비교에 섞으면 안 됩니다.
**이것은 심판 보정으로 해결되는 문제가 아닙니다.** 데이터 생성 과정(사람 판정 vs 자동 판정)이
다르기 때문에 생기는 문제입니다. 처리 방침 확정은 13.4절 과제입니다.

---

## 8. 직전 감사 3대 권고 처리 현황

| # | 직전 권고 | 상태 | 내용 |
|---|---|---|---|
| 1 | Q1 거짓 딜레마 제거 + `p_zone` 이름 정리 | **처리 (단, 전제가 뒤집힘)** | `p_zone`이 존 소속 확률이 아니라는 사실을 `CONTRACT`·docstring·테스트에 명시. 필드명은 웹 호환 때문에 유지. **그러나 SBJ를 `p_zone`으로 되돌린 결과, 현재 정의에서는 동일성 딜레마가 실재합니다** (0.1절·3.1.1절). "거짓 딜레마"라는 판정 자체가 현재 코드에는 적용되지 않습니다. |
| 2 | 반사실 외삽 검증 + 저지원 `p_CalledStrike` 축소 | **보류** | SBJ가 더 이상 `p_CalledStrike`를 쓰지 않으므로 이 권고의 **직접 대상이 사라졌습니다.** 다만 **`p_zone`에 대한 외삽 문제는 그대로 남아 있고 미검증**입니다(테이크 전용 모델을 스윙 투구에 적용). 직전 감사가 제시한 overlap 진단값(스윙 투구 중 `p_swing ≥ 0.90` 비율 25.8%, clipped IPW 유효표본 8,044 등)은 **`p_CalledStrike` 기준으로 계산된 값이므로, `p_zone` 기준으로 다시 재야 합니다.** → 13.2절 |
| 3 | 공표 정책 | **부분 처리** | `+` 점수(`sbj_plus`/`apr_plus`/`dv_plus`)를 300구 미만 타자에게 주지 않도록 완료 (실측: 비자격 122명 전원 null). **300구 기준선 자체의 재도출은 미착수** → 13.1절 |

---

## 9. 검증 상태 표

### 9.1 검증됨 — 무엇으로 검증했는지 병기

| # | 주장 | 검증 방법 | 결과 |
|---|---|---|---|
| V1 | 기준 커밋 `ed806226`, 브랜치 `claude/happy-hopper-g1h339`, 워킹 트리 깨끗 | `git log`, `git status --porcelain`, `git rev-parse` | 일치 |
| V2 | 직전 감사 이후 변경이 `zone_decision.py` + `test_zone_decision.py` 2개 파일뿐이고 모델 적합 경로는 불변 | `git diff 07f76ed1..ed806226 --stat` 및 함수명 grep | 일치 (1.1절) |
| V3 | 전체 테스트 118개 통과 | `PYTHONPATH=src python -m pytest -q` 실행 | `118 passed` |
| V4 | `tests/test_zone_decision.py` 25개 | `grep -c '^def test_'` | 25 |
| V5 | 웹 레이아웃 테스트 통과 | `node tests/test_pitch_arsenal_layout.cjs` 실행 | PASS |
| V6 | 2026 전체 285명 / 자격 163명 / 자격 투구 192,526 | 캐시된 투구 단위 채점표 + 현재 코드로 `profile_summary` 재실행 | 일치 |
| V7 | 5.1절 기술통계 6개 지표의 mean/sd/범위 | 동일 재실행 | 전부 일치 |
| V8 | 5.2절 상관·순위 변동 6쌍 | 동일 재실행 | 전부 일치 |
| V9 | 기준선 차감 동일성 | 285명 실데이터에서 `max|(SBJ−기대)−za_raw|` 계산 | 1.0000000133e-06 |
| V10 | `A+B+C+D == pitches_seen` 전원 성립 | 285명 전수 확인 | True |
| V11 | SEAGER 사분면 합계 (자격자·전체 두 범위) | 동일 재실행 | 5.3절 표 |
| V12 | 비자격 122명 전원 `+` 점수 null | 동일 재실행 (`any(... is not None)` 합계 0) | 0명 |
| V13 | `sz_top`/`sz_bottom` 타자당 상수 (5시즌) | 시즌별 자격 투구에서 타자별 고유값·sd 재계산 | 6.1절 표 |
| V14 | 2026 테이크 106,519 / 경기 626 | 재계산 | 일치 |
| V15 | 콜 예측 비교 중 `d ≤ 1` 5.4497%, `p_zone` 1.2289%/0.03968/0.009801, `p_CalledStrike` 0.8909%/0.02813/0.007156 | 재계산 | 일치 |
| V16 | `d ≤ 1` 잔차 방향 비대칭 | 리그 전체 재계산 | 잔차 5,805건 중 5,111건(88.0%)이 "규칙 볼 / 실제 콜 스트라이크" |
| V17 | 시즌별 테이크·경기 수 (5시즌) | 재계산 | 2023만 1구 차이, 나머지 일치 |
| V18 | 커밋된 산출물에 SBJ·APR 필드가 전혀 없음 | `leaderboard.json`·`report.json` 키 열거 | 확인 (13.3절) |
| V19 | 커밋된 산출물의 `dv_plus`가 비자격 타자에게도 값을 부여 | `leaderboard.json` 비자격 122명 값 확인 | 확인 (−59.85 등) |

### 9.2 미검증 — 빠짐없이

| # | 항목 | 상태 |
|---|---|---|
| U1 | **SBJ·APR의 신뢰도(반분·재현성) 측정이 전무합니다.** 구두로 오간 "1300구 환산 0.808 / 0.783 / 0.787"(SBJ / APR+ / DV_avg)은 **저장소에 산출 근거가 없습니다.** 인용 금지 | 미측정 |
| U2 | `expected_judgment_accuracy` 평균(68.5775)이 `sbj_raw` 평균(68.0844)보다 높은 현상의 원인. 직전 감사는 `p_swing` isotonic 보정 아티팩트로 판정하고 `raw_p_swing`으로는 부호가 뒤집힌다고 보고했으나, **그 계산은 `p_CalledStrike` 기준이었으므로 `p_zone` 기준으로 재확인 필요** | 미검증 |
| U3 | `p_zone`의 **테이크 → 스윙 외삽 품질**. 테이크만으로 적합한 모델을 스윙 투구에 적용하는 반사실 외삽. overlap·가중치 진단 전부 `p_zone` 기준으로 미실시 | 미검증 |
| U4 | **300구 자격선의 근거가 없습니다.** 신뢰도 기반으로 도출된 값이 아닙니다 | 근거 부재 |
| U5 | APR의 **시즌 간 안정성**, 타자 유형별 편향(공격형/선구형), 차년도 예측력 | 미측정 |
| U6 | SBJ·APR의 `za_raw`·DV 대비 **증분 예측력** | 미측정 |
| U7 | 2022–23과 ABS 시즌의 비교 가능성 처리 방침 | 미확정 |
| U8 | **산출물·UI 미반영.** SBJ·APR·SEAGER 필드가 `web/data/**`, `exports/*.csv`, `report.json`, 웹 페이지에 전혀 들어가 있지 않습니다 | 미착수 |
| U9 | 6.2절 "기하 + 배율" 행의 log loss / Brier 정확한 산출 명세 (오분류 3.56%는 재현됨) | 재현 미완 |
| U10 | 7절 격자 모델의 정확한 명세. 독립 재구현으로 정성적 패턴은 재현되나 오분류 수준과 유의 시즌이 다름 | 재현 부분 일치 |
| U11 | ADR-005 미결 4항목 (전문 11.2절) | 미결 |

### 9.3 반증됨 / 철회됨

| # | 항목 | 처리 |
|---|---|---|
| R1 | "`d ≤ 1` 규칙 잔차 4.87%, 잔차 338건 중 298건(88.2%)이 한 방향 → **존이 실제보다 좁다 / 좌표 품질 문제**" (이전 감사 문서의 U4/U13 계열) | **해석 철회.** 산술은 리그 전체에서도 재현되지만(5.4497%, 88.0%), 결론은 `d`로 사각형을 1차원 요약한 데서 온 착시. 2차원으로 다루면 1.23% (6.3절) |
| R2 | 구역 절단점 이동이 APR에 이산적으로 전파된다는 위험(U13) | **대상 소멸.** APR이 구역 소속을 쓰지 않고 `delta_v > 0`을 씀 (3.2절) |
| R3 | "SBJ와 `za_raw`의 동일성 딜레마는 거짓 딜레마" (직전 감사 Q1 판정) | **현재 커밋에는 적용되지 않음.** `q = p_CalledStrike`였던 `07f76ed1` 시점에는 옳았으나, `q = p_zone`으로 되돌린 `ed806226`에서는 동일성이 실재 (0.1절) |

---

## 10. 재현 방법

### 10.1 환경

```bash
cd /home/user/KBO-Savant-Visual-Project
python -m pip install -r requirements.txt -c constraints-za.txt   # ZA 재현용 고정 버전
export PYTHONPATH=src
export OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2

# 테스트
PYTHONPATH=src python -m pytest -q                        # 118 passed
PYTHONPATH=src python -m pytest tests/test_zone_decision.py -q
node tests/test_pitch_arsenal_layout.cjs                  # pytest가 수집하지 않음
```

### 10.2 5절 실측치 재현 스크립트 (실행 확인 완료)

투구 단위 채점표가 `data/metrics/zone_awareness/2026/pitches.parquet`(192,526행)에 캐시되어
있습니다. 1.1절에서 확인한 대로 최근 두 커밋이 모델 적합 경로를 바꾸지 않았으므로, 이 캐시로
현재 지표를 그대로 재현할 수 있습니다.

```python
# PYTHONPATH=src python this.py   (저장소 루트에서)
import numpy as np, pyarrow.parquet as pq
from collections import defaultdict
from visualbaseball import zone_decision as zd

rows = pq.read_table('data/metrics/zone_awareness/2026/pitches.parquet').to_pylist()
print('pitches', len(rows))                      # 192526
by = defaultdict(list)
for r in rows: by[str(r['batter_id'])].append(r)
players = [zd.profile_summary(v) for v in by.values()]
zd.add_dv_plus(players); zd.add_sbj_plus(players); zd.add_apr_plus(players)
q  = [p for p in players if p['qualified_300']]
nq = [p for p in players if not p['qualified_300']]
print('players', len(players), 'qualified', len(q), 'unqualified', len(nq))   # 285 163 122
print('unqualified with any + score:',
      sum(any(p[k] is not None for k in ('sbj_plus','apr_plus','dv_plus')) for p in nq))  # 0

for k in ('sbj_raw','sbj_raw_contextual','expected_judgment_accuracy_pct',
          'za_raw','apr_raw','dv_per_100'):
    v = np.array([p[k] for p in q], float)
    print(f'{k:36s} mean={v.mean():+.4f} sd(ddof=0)={v.std():.4f} '
          f'min={v.min():+.2f} max={v.max():+.2f}')

def ranks(v): return np.argsort(np.argsort(-np.asarray(v, float)))
for an,ak,bn,bk in [('SBJ','sbj_raw','contextual','sbj_raw_contextual'),
                    ('SBJ','sbj_raw','za_raw','za_raw'),
                    ('SBJ','sbj_raw','APR','apr_raw'),
                    ('SBJ','sbj_raw','DV/100','dv_per_100'),
                    ('APR','apr_raw','DV/100','dv_per_100'),
                    ('APR','apr_raw','za_raw','za_raw')]:
    a = np.array([p[ak] for p in q], float); b = np.array([p[bk] for p in q], float)
    d = np.abs(ranks(a) - ranks(b))
    print(f'{an} <-> {bn}: corr={np.corrcoef(a,b)[0,1]:+.4f} '
          f'rank_mean={d.mean():.2f} rank_max={d.max()}')

# 기준선 차감 동일성
diff = np.array([p['sbj_raw'] - p['expected_judgment_accuracy_pct'] for p in players], float)
za   = np.array([p['za_raw'] for p in players], float)
print('max |(SBJ - expected) - za_raw| =', np.abs(diff - za).max())   # 1.0000000133e-06

# SEAGER — 두 집계 범위를 구분해서 출력
for label, sel in (('all', players), ('qualified', q)):
    tot = {k: sum(p['seager_'+k.lower()] for p in sel) for k in 'ABCD'}
    s = sum(tot.values())
    print(label, tot, 'sum', s, 'hittable %.4f%%' % (100*(tot['A']+tot['C'])/s))
print('partition holds:', all(sum(p['seager_'+k.lower()] for k in 'ABCD') == p['pitches_seen']
                              for p in players))
st  = np.array([p['selection_tendency_pct'] for p in q], float)
hpt = np.array([p['hittable_take_pct'] for p in q], float)
print('ST mean %.4f  HPT mean %.4f' % (st.mean(), hpt.mean()))
```

### 10.3 6.2절 콜 예측 비교 재현 (실행 확인 완료)

```python
import numpy as np, pyarrow.parquet as pq
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import log_loss, brier_score_loss

rows  = pq.read_table('data/metrics/zone_awareness/2026/pitches.parquet').to_pylist()
takes = [r for r in rows if r['decision_type'] == 'Take']
print('takes', len(takes), 'games', len({r['game_id'] for r in takes}))   # 106519 626
y = np.array([r['event'] == 'CalledStrike' for r in takes], int)
x = np.array([r['x_relative'] for r in takes]); z = np.array([r['z_relative'] for r in takes])
d = np.maximum(np.abs(x), np.abs(z))

hard = (d <= 1).astype(int)
print('hard rule d<=1 misclass %.4f%%' % (100*np.mean(hard != y)))        # 5.4497
res = hard != y
print('  residuals %d, rule=ball/actual=strike %d (%.1f%%)'
      % (res.sum(), ((hard==0)&(y==1)).sum(), 100*((hard==0)&(y==1)).sum()/res.sum()))
                                                                          # 5805, 5111 (88.0%)
for name in ('p_zone', 'p_CalledStrike'):
    p = np.clip(np.array([r[name] for r in takes]), 1e-6, 1-1e-6)
    print('%-16s misclass %.4f%% logloss %.5f brier %.6f'
          % (name, 100*np.mean((p >= .5).astype(int) != y), log_loss(y, p),
             brier_score_loss(y, p)))
# p_zone         1.2289% 0.03968 0.009801
# p_CalledStrike 0.8909% 0.02813 0.007156

# 기하 + 배율 fold 외 적합 (오분류만 재현, 확률 지표는 원 명세 불명 — 6.2절 ※)
dates  = np.array([r['game_id'][:8] for r in takes])
blocks = np.array_split(np.array(sorted(set(dates))), 3)
p = np.zeros(len(y)); F = d[:, None]
for b in blocks:
    te = np.isin(dates, list(b)); tr = ~te
    p[te] = LogisticRegression(max_iter=1000).fit(F[tr], y[tr]).predict_proba(F[te])[:, 1]
p = np.clip(p, 1e-6, 1-1e-6)
print('geom+scale misclass %.4f%% logloss %.5f brier %.6f'
      % (100*np.mean((p >= .5).astype(int) != y), log_loss(y, p), brier_score_loss(y, p)))
# 3.5599% 0.11384 0.030240
```

### 10.4 6.1절 존 경계 상수성 + 7.3절 심판 효과 상한 재현 (실행 확인 완료)

시즌 인자를 바꿔 5회 실행합니다. 시즌당 수 분 걸립니다 (모델 적합 없이 격자 평균만 씁니다).

```python
# PYTHONPATH=src python this.py <season>
import sys, json, numpy as np
from pathlib import Path
from collections import defaultdict
from visualbaseball import zone_decision as zd

root, season = Path('.').resolve(), int(sys.argv[1])
rows, _ = zd.load_rows(root, season)       # 자격 투구 로드 (curated에서만 읽음)
out = {'season': season, 'eligible_pitches': len(rows)}
by = defaultdict(list)
for r in rows: by[str(r['batter_id'])].append(r)
qual = {k: v for k, v in by.items() if len(v) >= 300}
out['qualified_300'] = len(qual)
for col in ('sz_top', 'sz_bottom'):
    uniq = [len({round(float(r[col]), 6) for r in v}) for v in qual.values()]
    sds  = [float(np.std([float(r[col]) for r in v])) for v in qual.values()]
    out[col] = {'unique_median': float(np.median(uniq)),
                'single_value_batters': int(sum(u == 1 for u in uniq)),
                'within_batter_sd_median': round(float(np.median(sds)), 8),
                'league_unique': len({round(float(r[col]), 6) for r in rows})}
gp = [len({r['game_id'] for r in v}) for v in qual.values()]
out['games_per_qualified'] = {'median': float(np.median(gp)), 'min': int(min(gp)),
                              'max': int(max(gp)),
                              'dilution_1_over_sqrt_median': round(float(1/np.sqrt(np.median(gp))), 4)}

takes = [r for r in rows if r['decision_type'] == 'Take']
y  = np.array([r['event'] == 'CalledStrike' for r in takes], int)
gx = np.floor(np.array([r['x_relative'] for r in takes]) / 0.05).astype(int)
gz = np.floor(np.array([r['z_relative'] for r in takes]) / 0.05).astype(int)
cells = np.array([hash((a, b)) for a, b in zip(gx, gz)])
dates = np.array([r['game_id'][:8] for r in takes])
games = np.array([r['game_id'] for r in takes])
blocks = np.array_split(np.array(sorted(set(dates))), 3)
pred = np.full(len(y), np.nan)
for b in blocks:                                  # 날짜 3블록 교차적합
    te = np.isin(dates, list(b)); tr = ~te
    s, n = defaultdict(float), defaultdict(int)
    for c, t in zip(cells[tr], y[tr]): s[c] += t; n[c] += 1
    prior = y[tr].mean()
    pred[te] = [(s[c] + prior*10) / (n[c] + 10) for c in cells[te]]      # shrinkage 10구
out['takes'] = len(takes); out['games'] = int(len(set(games)))
out['grid_misclass_pct'] = round(float(100*np.mean((pred >= .5).astype(int) != y)), 4)

resid = y - pred
rng = np.random.default_rng(0)
gi = defaultdict(list)
for i, g in enumerate(games): gi[g].append(i)
gkeys = sorted(gi)
def halves_corr(keys):                            # 경기 안에서 잔차 무작위 반분
    a, b = [], []
    for g in keys:
        idx = np.array(gi[g])
        if len(idx) < 4: continue
        perm = rng.permutation(len(idx)); h = len(idx)//2
        a.append(resid[idx[perm[:h]]].mean()); b.append(resid[idx[perm[h:2*h]]].mean())
    a, b = np.array(a), np.array(b)
    return float(np.corrcoef(a, b)[0, 1]) if len(a) > 2 else float('nan')
point = halves_corr(gkeys)
boot = [halves_corr([gkeys[j] for j in rng.integers(0, len(gkeys), len(gkeys))])
        for _ in range(2000)]                     # 경기 단위 부트스트랩 2,000회
lo, hi = np.quantile(boot, [0.025, 0.975])
out['within_game_split_half_resid_corr'] = {'point': round(point, 4),
                                            'ci95': [round(float(lo), 4), round(float(hi), 4)]}
print(json.dumps(out, ensure_ascii=False))
```

### 10.5 지표 전체 재빌드 (수 시간 소요)

```bash
PYTHONPATH=src python -m visualbaseball.zone_decision --seasons 2024 2025 2026
# 또는 파이프라인 전체 산출물만 재생성 (네트워크 수집 없음)
PYTHONPATH=src python -m visualbaseball.cli --exports-only
```

재생성 순서는 `cli._exports()`가 단일 소스이고, `swing_take`가 만드는 자격 투구 테이블이
하위 판단 지표 전체의 입력입니다. Swing/Take를 건드리면 하위 지표가 전부 함께 재생성되어야
합니다.

### 10.6 웹 로컬 프리뷰

페이지들이 `../data/...`를 fetch하므로 **서버 루트는 반드시 `web/`** 여야 합니다. 저장소 루트에서
띄우면 모든 데이터가 404가 되고 도구가 빈 화면으로 뜹니다.

```bash
python scripts/serve_web.py            # http://localhost:8000/
python -m http.server 8000 --directory web   # 동일
```

빌드 단계는 없습니다. `web/`은 순수 정적 ES + fetch이고 GitHub Pages가 `web/`을 그대로 루트로
서빙합니다.

---

## 11. 신뢰도 수치 — 길이 병기 필수

**규칙: 신뢰도 값은 측정 길이 없이 기재하지 않습니다. 원값과 Spearman-Brown 환산값을 한 칸에
뭉치지 않고 각각 라벨과 함께 싣습니다.**

### 11.1 현재 대장

| 지표 | 원값 (측정 길이) | SB 환산값 (환산 길이) | 환산 배수 k | 산출 근거 |
|---|---|---|---|---|
| `za_raw` 반분 | 0.568 (반쪽 300구) | 0.8099 (972구) | 3.24 | **없음 — 미기록** |
| `za_raw` 반분 (전체길이 보정) | 0.568 (반쪽 300구) | 0.7245 (600구) | 2.00 | ADR-005 본문 계산 |
| `za_raw` (기록값) | 0.810 (**측정 길이 미상**) | — | — | **없음 — 미기록** |
| **SBJ** | **미측정** | 0.808 (1300구) | 미상 | **없음 — 인용 금지** |
| **APR+** | **미측정** | 0.783 (1300구) | 미상 | **없음 — 인용 금지** |
| **DV_avg** | **미측정** | 0.787 (1300구) | 미상 | **없음 — 인용 금지** |
| Task 5 잔차 | 0.659 (**측정 길이 미상**) | 환산 불가 | — | **없음 — 미기록** |

Spearman-Brown: `r_k = k·r / (1 + (k−1)·r)`.

세 비교 지표를 반분 표준 기준(반쪽 길이)으로 역산한 **조건부** 값입니다. 기준 길이가 확정되기
전까지 단독 인용을 금지합니다.

| 지표 | 1300구 환산값 | 기준 300구 가정 시 원값 | 기준 600구 가정 시 원값 |
|---|---|---|---|
| SBJ | 0.808 | 0.4927 | 0.6601 |
| APR+ | 0.783 | 0.4544 | 0.6248 |
| DV_avg | 0.787 | 0.4602 | 0.6304 |

**Spearman-Brown 적용 시 필수 병기.** 투구 단위 시계열에서는 아래 경로로 SB의 전제가 깨집니다.

| 경로 | 위반 전제 | 효과 |
|---|---|---|
| 타석·경기 단위 자기상관 | 오차 독립성 | 유효 표본수 < 명목 투구수 → 신뢰도 과대추정 |
| 상대 투수 구성 변화 | 항목 등가성(τ-등가) | 항목 이질 → 환산값 과대추정 |
| 시간순(전반기/후반기) 분할 | 반쪽 교환 가능성 | 기량 변동이 r을 눌러 환산 자체가 무효 |

통상적 위반 방향에서 **SB 환산값은 상한(upper bound)** 입니다. "0.568을 늘리면 0.810이 나온다"가
아니라 **"최대 0.810까지 나올 수 있다"** 가 정확한 표현입니다.

### 11.2 ADR-005 미결 4항목 (원문 그대로 옮김)

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

ADR-005의 해소 조건 (전부 충족되면 확정 상태로 갱신):

- [ ] 0.568의 산출 스크립트·노트북과 분할 방식(odd-even / 무작위 / 시간순) 기록
- [ ] 0.568이 Spearman-Brown 보정 전 값임을 명시
- [ ] ZA 0.810의 측정 길이(투구수) 기록
- [ ] SBJ · APR+ · DV_avg · Task 5 잔차의 기준 측정 길이 기록
- [ ] 위 지표들이 ZA와 동일 분할 절차로 산출됐음을 확인

ADR-005의 현재 결정은 **판정 보류**입니다. 0.568과 0.810이 산술적으로 모순이 아니라는 점만
확인되었고, 숫자 자체의 진위는 검증되지 않았습니다.

---

## 12. 알려진 한계 — 과장하지 않습니다

### 12.1 모델이 스스로 선언한 한계 (`LIMITATIONS` 원문)

> - 리그 평균 실행 능력을 기준으로 추정한 의사결정 가치이며 개인별 최적 판단의 정답이 아닙니다.
> - 관측하지 못한 반대 행동과 누락된 투구 특성에 따른 선택 편향이 남습니다. 실제 타구속도·발사각·
>   해당 투구의 안타/홈런은 판단 점수의 입력이 아닙니다.
> - 시즌 표시값은 날짜 블록 교차적합으로 해당 경기 결과를 제외하지만 다른 블록의 미래 경기를
>   사용할 수 있습니다. 순수한 사전 예측 성능은 별도 시간 분리 평가에서 확인합니다.
> - 표본 부족 구간은 상위 조건의 결과 분포로 완화합니다. 반대 선택의 정확성과 누락된 실행 능력·
>   번트 의도의 영향까지 검증된 것은 아닙니다.

### 12.2 SBJ · APR에 특히 적용되는 해석 범위

- **SBJ는 `za_raw`와 대수적으로 연결되어 있습니다**(3.1.1절). 난이도 보정판이 아니라 **보정을
  하지 않은 원 정확도**이며, 보정하면 `za_raw`가 됩니다. "SBJ는 `za_raw`보다 개선된 지표"라고
  쓰지 마십시오. 둘은 같은 확률에서 갈라진 두 표현입니다.
- **SBJ는 심판 성향을 재지 않습니다.** ABS에는 그 성분이 없습니다. 위치 전용 모델은 존만
  잽니다.
- **APR은 득점 이득의 크기가 아니라 선택적 공격성의 균형**입니다. 크기는 `dv_per_100`입니다.
- **2022–23은 ABS 시즌과 비교 가능하지 않습니다**(7.5절). 측정 잡음이 약 6배입니다.
- **PLV / Strikezone Judgement의 복제품이 아닙니다**(3.1.3절).

### 12.3 프로젝트 전반의 표현 규칙 (이 문서도 준수)

- **BAA는 KBO 공개 데이터에 적용한 실험 지표이며 MLB Statcast와 상호 비교 가능하지 않습니다.**
- **기존 Decision Run은 실제 선택 결과가 섞인 진단값이므로 counterfactual Decision Value로
  부르지 않습니다.**
- **plate discipline 클러스터 번호는 우열 등급이 아닙니다.**
- **미확인과 0을 구분합니다.** 파생 컬럼의 null은 "계산 불가"이고 `false`는 "관측된 false"입니다.
- **표본 미달은 숨기지 않고 표시합니다.** Swing/Take·ZA는 자격 투구 300구, 리더보드는 타자
  200 PA / 투수 50 IP가 기준선입니다.

---

## 13. 남은 작업 — 검토자가 이어서 할 것

우선순위 순입니다. 각 항목에 입력·산출물·통과 기준을 적었습니다.

### 13.1 [최우선] 300구 자격선 재도출

**왜**: 현재 300구에는 신뢰도 근거가 없습니다(U4). `+` 점수 공표 여부가 이 값에 달려 있습니다.

**절차 (직전 감사가 제시한 것을 그대로 옮김)**

1. **경기 단위 비중첩 반분.** 같은 경기의 투구가 두 반쪽에 나뉘지 않게 경기 단위로 분할합니다
   (투구 단위 무작위 분할은 경기·타석 자기상관 때문에 신뢰도를 과대추정합니다).
2. 반쪽 길이 **N ∈ {100, 200, 300, 500, 750, 1000, 1500}** 각각에 대해 반분 상관을 냅니다.
3. **Spearman-Brown 환산값과 반분 원값을 분리해 보고**합니다. 같은 칸에 뭉치지 않고,
   각각 "원값 (반쪽 N구)" / "환산값 (2N구)"로 길이 라벨을 붙입니다(11절 규칙).
4. 부트스트랩으로 신뢰도의 95% CI를 냅니다.
5. **통과 기준: Spearman-Brown 환산 신뢰도의 95% CI 하한 ≥ 0.70** 을 만족하는 최소 N을 자격선
   후보로 삼습니다.

**대상**: SBJ, APR, DV **셋 다**.

**입력**: 시즌별 자격 투구 + 투구 단위 채점표. 2026은
`data/metrics/zone_awareness/2026/pitches.parquet`(192,526행)로 바로 가능하고, 다른 시즌은
`PYTHONPATH=src python -m visualbaseball.zone_decision --seasons <year>` 재빌드가 필요합니다.
**ABS 시즌(2024–2026)만 사용하십시오** — 2022–23은 잡음 구조가 다릅니다(7.5절).

**산출물**: 신뢰도 대장 표(길이 병기), 자격선 권고값, 산출 스크립트. 스크립트를 반드시 남기십시오
— ADR-005 미결 4항목이 전부 "스크립트가 없어서" 생긴 문제입니다(11.2절).

**통과 기준**: 위 5번 + 결과가 300과 다르면 코드의 `qualified_300` 임계값과 필드명 변경 범위를
함께 제시.

### 13.2 [우선] `p_zone` 외삽 진단

**왜**: `p_zone`은 **테이크 투구만으로** 적합되고 **스윙 투구에도 적용**됩니다(3.3절). 직전 감사의
2번 권고는 `p_CalledStrike`를 대상으로 했으나 SBJ가 그 모델을 더 이상 쓰지 않으므로, 같은 진단을
`p_zone` 기준으로 다시 해야 합니다.

**반드시 다시 재야 하는 값** (직전 감사가 `p_CalledStrike` 기준으로 낸 값은 그대로 쓸 수 없습니다):

- 스윙 투구 중 `p_swing ≥ 0.90`인 비율 — 직전 감사값 **25.8%** (`p_CalledStrike` 기준)
- clipped IPW 유효표본수(ESS) — 직전 감사값 **8,044** (`p_CalledStrike` 기준)
- 그 외 overlap / positivity 진단 전부

**산출물**: `p_zone` 기준 overlap 진단표, 외삽이 심한 영역의 SBJ 기여도, 필요 시 저지원 구간
축소(shrinkage) 방안.

**통과 기준**: 외삽 영역이 SBJ 선수 순위에 미치는 영향의 크기를 수치로 제시하고, 공표 가능 여부
판정.

### 13.3 산출물·UI 연결

**현재 상태 (직접 확인함 — 검증됨)**: **커밋된 산출물에 SBJ·APR·SEAGER 필드가 전혀 없습니다.**

- `web/data/zone_awareness/2026/leaderboard.json`: `schema_version` 5, `model_version`
  `za7-strikezone-judgment`, 자격 163명 / 전체 285명. 선수 레코드 키 44개 중 `sbj_*`, `apr_*`,
  `seager_*`, `selection_tendency_pct`, `hittable_take_pct`, `expected_judgment_accuracy_pct`가
  **하나도 없습니다.** 있는 것은 `za_raw`, `za_percentile`, `dv_per_100`, `dv_plus`,
  `raw_dv`, `swing_aggression`, 구역별 DV 계열입니다.
- 같은 파일의 `metric_contract` 키는 7개(`za_raw`, `raw_dv`, `dv_per_100`, `dv_plus`,
  `swing_aggression`, `za_percentile`, `region_contributions`)뿐입니다. 현재 코드의 `CONTRACT`는
  16개입니다.
- `data/metrics/zone_awareness/2026/report.json`: `sbj_raw` 문자열 출현 횟수 **0**.
- 비자격 122명에게 `dv_plus`가 값으로 들어가 있습니다(3.3절). 즉 **공표 정책 변경 이전 산출물**입니다.
- `exports/kbo_zone_awareness_v2_*.csv`는 **다른 모듈**(`zone_awareness_v2.py`)이 만드는
  이전 세대 산출물입니다. 현재 ZA v7의 CSV 공표 경로는 없습니다. 새 CSV를 만들 것인지, ZA v7
  전용 경로를 신설할 것인지 결정이 필요합니다.

**해야 할 일**

1. `web/data/zone_awareness/<season>/leaderboard.json`, `players/<shard>.json`,
   `data/metrics/zone_awareness/<season>/report.json`에 다음을 추가:
   `sbj_raw`, `sbj_plus`, `sbj_raw_contextual`, `expected_judgment_accuracy_pct`,
   `apr_raw`, `apr_plus`, `seager_a`/`seager_b`/`seager_c`/`seager_d`,
   `selection_tendency_pct`, `hittable_take_pct`. (`profile_summary`가 이미 전부 만들고 있으므로
   재빌드만으로 payload에 들어갑니다 — 직렬화 경로 확인 필요.)
2. `web/zone-awareness/index.html`·`zone-awareness.js`에 컬럼·정렬·선수 카드 연결.
3. **2024–2026 재생성**: `PYTHONPATH=src python -m visualbaseball.zone_decision --seasons 2024 2025 2026`.

**옮겨 적는 저장소 규칙 (반드시 지킬 것)**

- **`web/`과 `exports/`는 출력물일 뿐입니다. 어떤 코드도 이것을 입력으로 읽지 않습니다.** 지표는
  curated partition만 읽습니다. 산출물을 손으로 고쳐 넣지 마십시오 — 다음 재생성에서 사라집니다.
- **CSS/JS를 고치면 `?v=YYYYMMDD-N` 캐시 버스터 값을 올려야** GitHub Pages 캐시가 갱신됩니다.
  현재 `web/zone-awareness/index.html`의 값은
  `zone-awareness.css?v=20260909-za7`, `../theme.css?v=20260913-4`,
  `../site-header.js?v=20260913-4`, `zone-awareness.js?v=20260913-za8`입니다.
  **`theme.css` 버전은 8개 페이지에 전부 들어 있으므로 한꺼번에 바꿔야 합니다.**
- **CSS는 두 층입니다.** `theme.css`(전 페이지 공통 색 토큰)는 **반드시 페이지 전용 CSS 뒤에**
  로드해 마지막에 덮어쓰게 합니다. `movement-zones`만 순서가 반대입니다.
- **`schema_version` 취급**: 현재 5입니다. 웹 JS가 이 값으로 렌더 분기를 합니다 —
  `state.modern = data.schema_version >= 4`, 그리고 `if(data.schema_version >= 5){...}`.
  **필드를 추가만 하고 기존 필드의 의미를 바꾸지 않으면 5를 유지**하고, 기존 필드의 의미나 타입을
  바꾸면 올린 뒤 JS 분기를 함께 고쳐야 합니다. `leaderboard.json`, 선수 shard, `index.json`
  세 곳 모두 같은 값을 씁니다.
- **`.cjs` 웹 레이아웃 테스트는 pytest가 수집하지 않습니다.** `node tests/test_pitch_arsenal_layout.cjs`를
  별도로 돌려야 하고, 이 테스트는 `web/pitch-arsenal/pitch-arsenal.js`의 함수 이름
  (`renderVelocity`, `renderFrequency`, `movementPoint`, `showTooltip`)을 슬라이스 경계로 쓰므로
  **이름을 바꾸면 테스트가 조용히 깨집니다.**
- **커밋되는 산출물에 벽시계 시각을 무조건 쓰지 마십시오.** 내용이 같은 재실행이 파일을 바꾸면
  워크플로의 `git diff --cached --quiet` 가드가 무력화되고 빈 데이터 커밋이 쌓입니다. 시각 필드는
  실제로 무언가 달라졌을 때만 갱신합니다.
- **웹 로컬 프리뷰 루트는 `web/`** 입니다(10.6절).

**통과 기준**: 재생성 후 `leaderboard.json`에 위 필드가 전부 존재하고, 비자격 타자의
`sbj_plus`/`apr_plus`/`dv_plus`가 모두 null이며, `pytest` 118개 + `.cjs` 테스트가 계속 통과하고,
웹 페이지가 `web/` 루트 프리뷰에서 정상 렌더될 것.

### 13.4 시즌 간 비교 정책 확정

**왜**: 2022–23은 위치 모델 미설명 콜이 9%대, ABS 시즌은 1.5~2%대입니다(7절). 측정 잡음이 약
6배 다르므로 같은 표에 섞으면 안 됩니다. 심판 보정으로 해결되는 문제가 아닙니다.

**결정할 것**

- 통합 리더보드에서 2022–23을 어떻게 분리 표시할지 (별도 탭 / 경고 배지 / 아예 SBJ 미공표).
- 시즌 간 비교·차년도 예측 분석에서 2022–23을 어떤 조건으로 쓸지.
- 산출물(`index.json`의 시즌 목록)과 UI에서의 표기 문구.

**산출물**: 정책 문서 + 산출물/UI 반영안. **통과 기준**: 사용자가 두 체계의 값을 나란히 비교하도록
유도되지 않을 것.

### 13.5 신뢰도·증분 예측력 측정 — 독립 공표 기준

직전 감사가 Q7에 적은 **독립 공표 기준을 그대로 옮깁니다.** SBJ를 `za_raw`와 별도 지표로 공표하려면
아래를 만족해야 합니다.

1. **`za_raw`와의 구별**: 시즌별 Spearman 상관 **< 0.90** 또는 `r²` **< 0.80**.
   (현재 2026 Pearson은 +0.9485이므로 `r² ≈ 0.90`입니다. 이 기준을 그대로 적용하면 **현재 상태는
   기준 미달**입니다 — 5.2절.)
2. **`za_raw` 제거 잔차의 신뢰도**: SBJ에서 `za_raw`를 회귀로 제거한 잔차의 반분 신뢰도
   **95% CI 하한 ≥ 0.50**.
3. **증분 예측력**: 차년도 BB% / chase% / K% / DV 예측에서, `za_raw`(및 기타 기존 지표)를 이미
   넣은 모형 대비 **incremental out-of-sample R² ≥ 0.02**.

**대상**: SBJ 우선, APR도 같은 틀로 (U5·U6).

**입력**: 2024–2026 시즌별 선수 단위 지표 + 차년도 성적. **산출물**: 기준 충족/미충족 판정표와
산출 스크립트. **통과 기준**: 세 기준 중 어느 것을 충족·미충족했는지 명시하고, 미충족 시
"진단용으로만 제공" 결정까지 함께 기록.

---

## 14. 이 문서를 쓰는 동안 인계값과 달랐던 사실

인계받은 수치를 전부 직접 재현했고, 아래 항목만 달랐습니다. **문서 본문에는 재현한 값을
싣고 인계값을 병기**했습니다.

| # | 항목 | 인계값 | 재현값 | 비고 |
|---|---|---|---|---|
| D1 | SEAGER 사분면 합계의 집계 범위 | "**리그 합계** A 55,351 / B 25,279 / C 31,719 / D 68,874, hittable 48.05%" | 그 값은 **자격자 163명 합계**(181,223구)입니다. 전체 285명(192,526구)은 A 59,001 / B 27,006 / C 33,614 / D 72,905, hittable 48.1052% | 인계값 자체는 정확하나 라벨이 틀렸습니다. 인계값 합계가 181,223으로 192,526과 맞지 않아 발견. 5.3절에 두 범위를 분리해 실었습니다 |
| D2~D4 | 2023의 `sz_top` 고유값(188 vs 187), 테이크 수(118,574 vs 118,573), 자격 타자당 경기 수 중앙값(86 vs 84) | 전 행 기준 | 좌표 non-null 필터 적용 후 | **둘 다 정확하며 행 필터 차이입니다.** 인계값은 `pitches` 전 행, 재현값은 `px`/`pz`/`sz_top`/`sz_bottom`이 모두 non-null인 행 기준입니다. 재검산에서 전 행 기준 값(188 / 중앙값 86)이 확인됐습니다. 희석 배수는 0.108~0.109로 7.5절 결론에 영향이 없습니다 |
| D5 | "기하 + 배율 fold 외 적합"의 log loss / Brier | 0.11033 / 0.028145 | **재현 불가.** 오분류 3.56%는 두 구현에서 재현(3.5599%, 3.5637%)되나 확률 지표는 0.11384 / 0.030240 | 원 산출 스크립트가 저장소에 없어 정확한 명세를 복원할 수 없었습니다. 6.2절 ※로 표기 |
| D6 | 심판 효과 상한 표의 격자모델 오분류 | 9.42 / 9.21 / 1.49 / 1.51 / 1.49 % | 9.604 / 9.195 / 1.856 / 1.942 / 1.903 % | 독립 재구현(shrinkage·미관측 셀 처리 차이). 7.3절 |
| D7 | 심판 효과 상한 표의 유의 시즌 | **2022만 유의** (+0.1197 [+0.0425, +0.1949]) | **2022는 CI가 0을 포함**(+0.0724 [−0.0018, +0.1536]), 대신 **2023이 0을 넘음**(+0.0702 [+0.0041, +0.1531]) | 정성적 패턴(사람 심판 시즌 작은 양수, ABS 시즌 0 근처)은 재현되지만 **유의 시즌은 구현 세부에 민감**합니다. 7.3절에 두 표를 나란히 실었습니다. 7.5절 결론 (a)의 "2022에서만 유의"는 이 민감성을 감수한 서술입니다 |
| D8 | 철회 진단의 철회 범위 | "이전 결론은 1차원 요약이 만든 착시" | **산술은 리그 전체에서도 재현됩니다** (경성 규칙 5.4497%, 잔차 5,805건 중 5,111건 = 88.0%가 같은 방향). 착시인 것은 "존이 실제보다 좁다 / 좌표 품질 문제"라는 **해석**입니다 | 6.3절에서 (a) 산술 존속 / (b) 해석 철회로 나눠 적었습니다 |
| D9 | "`CLAUDE.md`의 시각화 안정성 규칙" | 그 이름의 규칙 절을 옮기라는 지시 | **`CLAUDE.md`에 그 제목의 절은 없습니다.** 관련 실제 규칙(웹은 출력물 전용, `?v=` 캐시 버스터, `theme.css` 로드 순서, `.cjs` 테스트 슬라이스 경계, 벽시계 시각 금지, 프리뷰 루트)을 13.3절에 옮겨 적었습니다 | — |
| D10 | 직전 감사 GPT 답변의 출처 | 절차·기준을 "그대로 옮겨라" | **GPT의 감사 답변 원문은 저장소에 없습니다.** `docs/review/`에는 우리가 보낸 질의서(`SBJ-external-review-2026.md`)와 이전 감사 문서만 있습니다. 13.1·13.2·13.5절의 절차·기준·수치(25.8%, ESS 8,044, N 격자, CI 하한 0.70/0.50, R² 0.02 등)는 **인계 지시문에 적힌 대로 전사**했으며 저장소로 대조 검증하지 못했습니다 | 검토자가 자기 이전 답변과 대조해 주십시오 |

---

## 15. 이 문서가 주장하지 않는 것

- SBJ가 `za_raw`보다 개선된 지표라고 주장하지 않습니다. 대수적으로 연결되어 있습니다.
- SBJ·APR이 신뢰할 만한 수준의 재현성을 갖는다고 주장하지 않습니다. **측정된 바 없습니다**(U1).
- 300구 자격선이 적절하다고 주장하지 않습니다. **근거가 없습니다**(U4).
- `p_zone`의 스윙 투구 외삽이 타당하다고 주장하지 않습니다. **미검증입니다**(U3).
- PLV / Strikezone Judgement의 복제라고 주장하지 않습니다.
- 심판 효과가 0이라고 주장하지 않습니다. 작고, 사람 심판 시즌에 국한되며, 시즌 합산에서 희석되므로
  **심판 ID 크롤링의 우선순위가 낮다**는 것이 우리 판단이고, 그 판단 자체가 검토 대상입니다.
- 2022–23 SBJ가 ABS 시즌과 비교 가능하다고 주장하지 않습니다. 비교 불가입니다.
