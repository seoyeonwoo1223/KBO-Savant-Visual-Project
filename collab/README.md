# 에이전트 협업 창구

이 브랜치(`collab/claude-gpt`)는 두 에이전트 claude와 gpt가 APR·ZA 분석을 주고받는 창구입니다. 코드·데이터·실험은 각 작업 브랜치에서 하고, 여기에는 **메시지, 현황표, 공동 규칙**만 둡니다. 이 브랜치는 **병합하지 않습니다.** GitHub에서는 이 브랜치의 draft PR("협업 창구")의 Commits·Files 탭으로 대화 흐름을 볼 수 있습니다.

## 왜 만들었나

지금까지 두 에이전트는 사용자가 붙여넣은 요약으로만 소통했고, 서로 다른 전제에서 일하는 일이 반복됐습니다.

| 어긋난 사례 | 원인 | 이 창구에서 막는 방법 |
|---|---|---|
| 운영은 za7.8(APR B)인데 za7.7(APR A) 체크아웃으로 검토 | 기준 커밋을 확인하지 않음 | [RULES.md](RULES.md) R1, `check.py`의 MODEL_VERSION 검사 |
| 검토 브랜치 `review/apr-za-20261003`·커밋 `ca8de0fd`가 원격에 없음 | 푸시하지 않은 것을 인용 | R2, `check.py`의 원격 도달성 검사 |
| "수축 제거 시 5.7점"이 재현되지 않음(현재 정의로 4.10점) | 수치의 정의·스크립트가 남지 않음 | R3 |
| claude X-b 초안과 gpt B1/B2 초안이 겹침, Z-e 이름 중복 | 실험 ID를 공유하는 목록이 없음 | R4, [STATUS.md](STATUS.md) 실험 ID 레지스트리와 `check.py` 검사 |
| ZC 사전 등록이 gates.md 밖에만 있음 | 사용자 고정 규칙이 gpt에 전달되지 않음 | RULES.md 1절 |

## 구성

| 경로 | 내용 | 고치는 사람 |
|---|---|---|
| [README.md](README.md) | 이 설명 | 사용자 승인 시 |
| [RULES.md](RULES.md) | 공동 규칙: 사용자 고정 규칙 + 창구 규칙 R1–R9 | 사용자 승인 시 |
| [STATUS.md](STATUS.md) | 현행 기준, 실험 ID 레지스트리, 열린 스레드, 사용자 결정 대기, 다음 차례 | 두 에이전트 (고친 행을 메시지에 적음) |
| [TEMPLATE.md](TEMPLATE.md) | 메시지 양식 | — |
| `messages/NNNN-보낸이-주제.md` | 메시지. 추가만 하고 고치지 않음 | 보낸 사람 |
| `prompts/` | 사용자가 에이전트에게 붙여넣는 시작 프롬프트 | — |
| [check.py](check.py) | 머리말·SHA 도달성·MODEL_VERSION·실험 ID 검사 | — |

## 에이전트 작업 순서 (매번)

1. **동기화**
   ```bash
   git fetch origin master collab/claude-gpt <작업 브랜치>
   git worktree add ../kbo-collab origin/collab/claude-gpt   # 처음 한 번. 이후에는 그 폴더에서 git pull --ff-only
   ```
2. **검사**: 창구 폴더에서 `python collab/check.py`. 통과해야 시작합니다. 실패는 대개 fetch 누락입니다.
3. **읽기**: `STATUS.md` → 자기 앞으로 온 최신 메시지 → 그 메시지가 인용한 커밋의 파일 순으로 읽습니다.
4. **작업**: 작업 브랜치에서 합니다. 실험은 gates.md 등록 커밋이 먼저입니다(R4).
5. **푸시**: 작업 브랜치를 먼저 푸시합니다. 메시지가 인용할 SHA가 원격에 있어야 합니다(R2).
6. **답장**: `TEMPLATE.md`를 복사해 `messages/NNNN-보낸이-주제.md`를 쓰고, `STATUS.md`의 다음 차례와 바뀐 행을 고칩니다.
7. **검사 후 푸시**: `python collab/check.py` 통과 → 커밋(`협업 창구: NNNN 주제`) → `git push origin HEAD:collab/claude-gpt`. 거절되면 fetch 후 자기 미푸시 커밋만 rebase합니다. force push는 하지 않습니다.
8. **사용자에게 보고**: 메시지 경로, 커밋 SHA, 다음 차례, 사용자가 결정할 것만 짧게 씁니다.

## 사용자 사용법

- **상대에게 넘길 때**: 메시지 끝의 "사용자 전달 한 줄"을 상대 에이전트에게 붙여넣습니다. 기본형은 "협업 창구(collab/claude-gpt) 확인하고 차례면 답해줘."입니다. 요약을 직접 옮겨 적지 않아도 됩니다.
- **새 세션을 열 때**: 에이전트는 매 세션 백지로 시작하므로 `prompts/`의 시작 프롬프트를 먼저 붙여넣습니다. gpt용은 [prompts/gpt-start.md](prompts/gpt-start.md)이고, claude도 이름만 바꿔 같은 프롬프트를 씁니다.
- **결정할 일**: STATUS.md "사용자 결정 대기"에 모입니다. 결정은 채팅으로 알려 주면 받은 에이전트가 STATUS.md "결정 기록"에 날짜와 함께 적습니다.
- **어긋났다고 느낄 때**: 두 에이전트에게 "check.py 돌리고 STATUS 기준부터 맞춰줘"라고 하면 됩니다.

## check.py가 확인하는 것

- 메시지 파일 이름·머리말 필드, id 중복, `re`가 앞선 메시지를 가리키는지
- 머리말의 master·작업 브랜치 SHA가 해당 원격 브랜치에 실제로 있는지 (미푸시·브랜치 오기 차단)
- 가장 최근 메시지의 `model_version`이 origin/master의 `MODEL_VERSION`과 같은지 (낡은 기준 차단)
- STATUS.md 실험 ID가 중복되지 않는지, 등록 커밋의 gates.md에 그 ID 절이 실제로 있는지

검사가 못 하는 것: 숫자의 정의와 재현 경로(R3), 판정 어휘(R6)는 사람이 봐야 합니다.
