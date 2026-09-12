# KBO Savant — 남은 작업 순차 플랜

Codex에 붙여넣는 용도. **위에서 아래로 순서대로.** 각 단계의 "완료 조건"을 통과하지 못하면 다음 단계로 넘어가지 마십시오.

---

## 공통 전제

```bash
# Python 3.12 필수 (constraints-za.txt가 numpy==2.5.3을 핀하고, 그건 >=3.12 요구)
python -m pip install -r requirements.txt -c constraints-za.txt
export PYTHONPATH=src
export OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2
```

저장소 규칙은 `CLAUDE.md`에 있습니다. **작업 시작 전에 반드시 읽으십시오.** 특히:

- 생성 데이터(`data/`, `web/data/`, `exports/`, `seasons/`)는 **손으로 머지하지 마십시오.** 저장소 도구로 재생성합니다.
- `exports/visualbaseball_savant_*_latest.xlsx`는 커밋하지 않습니다 (gitignore).
- `data/curated/partition-index.json`을 열지 마십시오. 무결성 기록이고 MB 단위입니다. "무슨 데이터가 있나"는 `data/curated/summary.json`(5KB)에 있습니다.
- 테스트는 `python -m pytest` **그리고** `node tests/test_pitch_arsenal_layout.cjs` 둘 다입니다. pytest는 `.cjs`를 수집하지 않습니다.

### 현재 상태 (기준: master `f91cd358`)

| 시즌 | 레이아웃 | 파일 수 | raw 복구 경로 |
|---|---|---|---|
| 2026 | month | 7 | `data/raw/2026` |
| 2025 | month | 8 | `seasons/2025` |
| 2024 | **game** | 720 | **없음** |
| 2023 | **game** | 720 | **없음** |
| 2022 | **game** | 720 | **없음** |

curated parquet 총 6,526개. 이 중 6,480개가 2022–2024입니다.

---

## 1단계 — 2022–2024 compaction

**목표**: curated parquet 6,526 → 112.

### 왜 조심해야 하는가

2022–2024는 **raw JSON이 전무합니다.** curated partition이 유일한 사본이고, 복구 경로는 **git 이력뿐**입니다. 반면 `compact_curated`는 삭제 전에 전체 read-back + digest 대조를 2회 수행하므로, 검증을 통과했다면 내용은 보존된 것입니다.

`docs/curated-data.md`에 기록된 추가 사실: 2022–2024는 `y0` 컬럼이 없고 x0/z0가 50ft 평면이라는 것이 **문서화된 가정**입니다. 측정값이 아닙니다.

### 실행

시즌당 약 6분 걸립니다. **한 시즌씩** 하고 매번 검증하십시오.

```bash
# 1) 사전 행수 기록 (summary.json에 이미 집계되어 있음)
python -c "
import json
d=json.load(open('data/curated/summary.json'))
for y in ('2022','2023','2024'):
    print(y, d['seasons'][y]['tables'])
"

# 2) 한 시즌 compact
python -m visualbaseball.compact_curated --season 2022

# 3) 즉시 검증: 3테이블 행수가 사전 값과 정확히 일치해야 함
python -c "
from pathlib import Path
from visualbaseball.curated import load_rows
for k in ('pitches','events','games'):
    print(k, len(load_rows(Path('.'), k, 2022, columns=['game_id'])))
"

# 4) 전 시즌 읽기가 여전히 되는지 (부분 마이그레이션 회귀 방지)
python -c "
from pathlib import Path
from visualbaseball.curated import load_rows
for y in (2022,2023,2024,2025,2026):
    print(y, len(load_rows(Path('.'),'pitches',y,columns=['pitch_id'])))
"

# 5) 통과했으면 2023, 2024 반복
```

### 완료 조건

- 세 시즌 각각 3테이블 행수가 compaction 전후 **정확히 일치**
- 5시즌 전부 `load_rows` 성공 (하나라도 `FileNotFoundError`면 중단하고 롤백)
- `python -m visualbaseball.dataset_summary` 실행 후 `summary.json`의 `layout`이 `month`, 각 시즌 `months`가 채워짐
- `python -m pytest` 100 passed, `node tests/test_pitch_arsenal_layout.cjs` PASS
- `find data/curated -name '*.parquet' | wc -l` → **112**

### 실패 시 롤백

```bash
git checkout f91cd358 -- data/curated
```

`compact()`는 검증 실패 시 legacy shard를 보존하고 중단하므로, 정상적으로는 롤백이 필요 없습니다.

### 커밋

`summary.json`을 갱신한 뒤 함께 커밋합니다. 커밋 메시지에 시즌별 사전/사후 행수를 적어 두십시오.

---

## 2단계 — CI 구멍 2개 막기

### 2-1. `sample_reconcile.yml`에 테스트 추가

이 워크플로만 **테스트 없이 데이터를 커밋합니다.** 나머지 3개(`daily_update`, `refresh_completed`, `rebuild_swing_take`)는 `pytest`를 돕니다.

`.github/workflows/sample_reconcile.yml`의 `pip install` 다음에 추가:

```yaml
      - run: python -m pytest
```

`node tests/test_pitch_arsenal_layout.cjs`는 이미 있습니다.

### 2-2. `_state` 스테일 감지

**문제**: `data/metrics/_state/<season>/*.json`은 metric의 입력·코드 해시를 담습니다. 코드를 고친 뒤 빌드를 돌리지 않고 커밋하면 state가 커밋 시점부터 스테일이 되고, 이후 모든 프로덕션 실행이 metric 9개를 전부 리빌드합니다. 실제로 `codex/pipeline-compaction`에서 이 일이 발생했습니다 — `_state`와 `curated.py`가 같은 커밋에 들어갔는데 해시가 맞지 않았습니다.

동작은 올바릅니다(스테일 → 리빌드). 문제는 **조용하다**는 점입니다.

`tests/`에 스테일을 드러내는 테스트를 추가하십시오. 실패시키지 말고 **경고로 보고**하는 편이 낫습니다 — 정상적인 데이터 갱신 후에도 스테일이 될 수 있으므로 hard fail은 CI를 계속 깨뜨립니다.

권장 형태: `scripts/check_metric_state.py`를 만들어 각 metric의 저장된 해시와 현재 해시를 비교하고, 불일치 목록을 stdout에 출력한 뒤 **exit 0**으로 끝냅니다. `daily_update.yml`에서 빌드 **전에** 한 번 실행해 로그에 남깁니다.

```python
# 뼈대
from pathlib import Path
from visualbaseball.metric_state import SPECS, metric_input_hash, _path
import json, sys

root = Path(".")
for season in (2026,):
    for name in SPECS:
        p = _path(root, season, name)
        if not p.is_file():
            print(f"no state: {name} {season}"); continue
        stored = json.loads(p.read_text()).get("input_sha256")
        if stored != metric_input_hash(root, season, name):
            print(f"stale: {name} {season}")
```

### 완료 조건

- `sample_reconcile.yml`에 `python -m pytest` 존재
- 체크 스크립트가 로컬에서 실행되고 현재 스테일 metric 목록을 출력
- `python -m pytest` + `.cjs` 통과

---

## 3단계 — `data/processed` 추적 해제 검토

33개 파일 / 33MB가 추적되고 있습니다. `.gitignore`에는 일부 패턴만 있습니다.

```bash
git ls-files data/processed
grep processed .gitignore
```

**판단 기준**: 어떤 코드가 `data/processed`를 **읽는지** 확인하십시오.

```bash
grep -rn "data/processed\|processed/" src/ | grep -v "\.pyc"
```

- 읽는 코드가 없다면 → 추적 해제 (`git rm --cached` + gitignore)
- 읽는 코드가 있다면 → **그대로 두십시오.** 33MB는 위험을 감수할 크기가 아닙니다.

`zone_awareness_v2.py`와 `plate_decision_v1.py`가 legacy 시즌용으로 참조할 가능성이 있으니 반드시 확인하십시오.

---

## 4단계 — no-op 스킵 정착 확인

**배경**: `metric_state.needs_build()`가 metric별로 리빌드 필요 여부를 판정합니다. 이게 작동하면 데이터가 안 바뀐 metric은 건너뜁니다.

측정된 사실:
- CI 예열 직후: **7/9 no-op** (작동 확인)
- compaction 후: **0/9** — `metric_input_hash`의 지문이 index의 *모든* 경기 digest인데, compaction이 index를 완전하게 만들면서 지문이 바뀜. 데이터가 변한 게 아니라 지문이 완전해진 것. **1회성 리셋.**

1단계(2022–2024 compaction)도 같은 리셋을 유발합니다.

### 실행

1단계~3단계를 푸시한 뒤 **daily 워크플로가 1회 실행되기를 기다립니다** (매일 15:00 UTC = KST 00:00, 또는 `workflow_dispatch`로 수동 실행).

그 실행이 끝난 뒤:

```bash
git pull origin master
python -c "
from pathlib import Path
from visualbaseball.metric_state import SPECS, needs_build
r=Path('.')
inactive={'plate_decision'}   # 2026에서는 zone_decision이 대신 실행됨
res={n: needs_build(r,2026,n) for n in SPECS if n not in inactive}
for n,v in res.items(): print(f'{n:18} needs_build={v}')
print('no-op:', sum(1 for v in res.values() if not v), '/', len(res))
"
```

### 완료 조건

- `excel`을 제외한 나머지가 전부 `needs_build=False`
- `excel`은 **항상 True**입니다 — 출력(`exports/visualbaseball_savant_2026_latest.xlsx`)이 gitignore이고 Release로만 배포되므로 clean checkout에서는 구조적으로 리빌드됩니다. 이건 버그가 아닙니다.

이 조건을 만족하지 못하면 어떤 성분이 달라졌는지 분해해 보고하십시오 (`metric_input_hash`의 `source` / `code` / `extras` / `schema_sha256`).

---

## 5단계 — 방치 브랜치 3개 정리 판단

다음 브랜치들은 **미머지 코드**를 들고 있고 CI가 실패 상태입니다. 삭제 전에 그 코드가 여전히 필요한지 판단이 필요합니다.

| 브랜치 | 미머지 코드 파일 | CI |
|---|---|---|
| `codex/za-deploy` | 38 | ✗ 0/1 |
| `codex/implement-phased-changes-for-output-management` | 17 | ✗ 0/1 |
| `chore/blue-pitch-plot-theme` | 12 | ✗ 0/1 |

각 브랜치에 대해 **생성 데이터를 제외한** 변경만 보십시오.

```bash
for b in codex/za-deploy codex/implement-phased-changes-for-output-management chore/blue-pitch-plot-theme; do
  echo "### $b"
  git diff --stat master...origin/$b -- src tests scripts docs .github 'web/*.css' 'web/*/*.js' 'web/*/*.css' 'web/*/*.html'
done
```

각각에 대해 **요약 + 권고**를 사람에게 보고하십시오: (a) 살릴 가치가 있으니 PR로 정리, (b) master가 이미 대체했으니 삭제 가능, (c) 판단 불가.

**브랜치 삭제는 직접 하지 마십시오.** 사람이 GitHub 웹에서 처리합니다.

---

## 6단계 — 이력 재작성 (사람이 직접, Codex 금지)

> **이 단계는 에이전트가 실행하면 안 됩니다.** 모든 커밋 SHA가 바뀌고 force-push가 필요합니다.

### 왜

`.git`이 2.9GB인데 원인이 명확합니다 (이력 전체 blob 집계):

| 경로 | 누적 | blob 수 |
|---|---|---|
| `exports/` | **4,027 MB** | 125 |
| `web/data/` | 1,598 MB | 1,175 |
| `data/processed/` | 955 MB | 262 |
| `data/curated/` | 537 MB | 14,278 |

단일 최대 원인: **`exports/visualbaseball_savant_2026_latest.xlsx` 55개 버전 = 3,580MB.** 이 파일은 **이미 gitignore이고 현재 트리에 없습니다.** 완전한 죽은 무게입니다. xlsx는 zip이라 git이 델타를 못 만들어 매 버전이 통째로 쌓였습니다.

### 중요: curated 이력은 건드리지 않습니다

`exports/*.xlsx`만 제거하면 `data/curated/**`의 이력 blob은 보존됩니다. 즉 **1단계에서 compact한 2022–2024의 복구 경로(git 이력)가 유지됩니다.** 두 작업은 충돌하지 않습니다.

### 전제조건

1. **PR #6 (`feature/pickoff-runner-pitches`, 열린 draft) 처리** — 머지하거나 닫기. 열린 PR은 force-push로 깨집니다.
2. 5단계 브랜치 판단 완료
3. 백업 클론 확보: `git clone --mirror <url> backup.git`
4. 협업자 없음 확인 (있으면 전원 재클론 필요)

### 절차

```bash
pip install git-filter-repo
git clone --mirror https://github.com/seoyeonwoo1223/KBO-Savant-Visual-Project rewrite.git
cd rewrite.git
git filter-repo --path-glob 'exports/visualbaseball_savant_*_latest.xlsx' --invert-paths
git count-objects -vH          # 축소 확인
git push --force --all
git push --force --tags
```

이후 모든 로컬 클론은 버리고 다시 클론해야 합니다. GitHub 원격 용량은 즉시 줄지 않고 자체 GC 일정을 따릅니다 — 필요하면 GitHub Support에 GC를 요청하십시오.

### 기대 효과

비압축 기준 약 4GB 제거. 이후 `web/data/`(1,598MB)가 최대 원인이 되지만, 그건 Pages가 서빙해야 하는 현재 데이터라 구조적입니다.

---

## 7단계 — 웹/시각화 수정 (요구사항 미정)

사람이 "시각화·웹 디자인에 문제가 많다"고 했으나 구체 항목이 아직 없습니다. **이 단계는 문제 목록을 받기 전까지 착수하지 마십시오.**

작업할 때 반드시 지켜야 할 것 (`CLAUDE.md` 원문 참조):

- **CSS 2층**: `theme.css`(전역 토큰)는 **페이지 전용 CSS 뒤에** 로드되어야 합니다. `movement-zones`만 순서가 반대입니다.
- **캐시 버스터**: CSS/JS를 고치면 `<link>`/`<script>`의 `?v=YYYYMMDD-N`을 올려야 Pages 캐시가 갱신됩니다. `theme.css` 버전은 8개 페이지에 전부 들어 있어 한꺼번에 바꿔야 합니다.
- **좌표계 부호**: 저장된 x 계열은 전부 **포수 시점**. `pitch-arsenal`은 기본이 투수 시점으로 `toPitcherView()`가 부호를 뒤집고 `low_75`/`high_75`를 **맞바꿉니다**(구간 뒤집기를 빠뜨리면 타원이 어긋남). `movement-zones`는 반대로 포수 시점이 기본이고 `handFactor()`를 HB에만 곱하며 **IVB는 절대 뒤집지 않습니다**. HB 데이터를 고치면 `mirroredHbLabel()`도 같이 손봐야 합니다.
- **프리뷰**: `python scripts/serve_web.py` (문서 루트가 `web/`이어야 함. 저장소 루트에서 띄우면 데이터가 전부 404).
- **레이아웃 테스트**: `pitch-arsenal.js`의 함수 이름(`renderVelocity`, `renderFrequency`, `movementPoint`, `showTooltip`)이 `.cjs` 테스트의 슬라이스 경계입니다. 이름을 바꾸면 테스트가 **조용히** 깨집니다.

---

## 요약 체크리스트

- [ ] 1. 2022–2024 compaction → curated 112 files, 행수 일치, 5시즌 읽기 OK
- [ ] 2. `sample_reconcile.yml`에 pytest + `_state` 스테일 체크 스크립트
- [ ] 3. `data/processed` 참조 여부 확인 후 추적 해제 판단
- [ ] 4. daily 1회 후 no-op 정착 확인 (excel 제외 전부 False)
- [ ] 5. 방치 브랜치 3개 코드 요약 + 권고 보고
- [ ] 6. 이력 재작성 — **사람이 직접**, PR #6 처리 후
- [ ] 7. 웹/시각화 — 문제 목록 수령 후
