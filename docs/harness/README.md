# 하네스

이 저장소에서 에이전트가 올바르게 일하도록 만든 환경입니다. 하네스는 네 부분으로 나뉘고, 한 문서(CLAUDE.md나 README)에 몰아두지 않습니다.

| 구성요소 | 역할 | 이 저장소에서 |
|---|---|---|
| 1. 지시 문서 | 에이전트가 **어떻게 할지** 알려줍니다 | [AGENTS.md](../../AGENTS.md)(약 100줄 지도) → [conventions.md](../conventions.md)(세부 규칙). `CLAUDE.md`는 `AGENTS.md`를 불러오기만 합니다 |
| 2. 아키텍처 제약 | 잘못된 방향으로 가면 **구조적으로 통과하지 못하게** 막습니다 | [constraints.md](constraints.md): 웹 규격 검사, import 폐포 검사, 산출물 게이트, 생성기 템플릿, gitattributes·gitignore |
| 3. 피드백 루프 | 결과가 맞는지 **즉시** 알려줍니다 (가이드 + 센서) | [feedback.md](feedback.md): 빠른 것부터 도는 검사 순서와 CI |
| 4. 지식 저장소 | **왜 이렇게 하는지** 남깁니다 | [decisions/](../decisions/README.md)(결정·기각한 대안), [architecture.md](../architecture.md), [curated-data.md](../curated-data.md), `analysis/*/README.md` |

## 어떻게 쓰나

1. 작업 전: `AGENTS.md`의 지도에서 영역 문서 하나와 관련 결정 기록을 읽습니다.
2. 작업 중: 생성기·예제 테스트(가이드)를 따릅니다. 규칙을 몰라도 제약이 잘못된 결과를 막습니다.
3. 작업 후: [feedback.md](feedback.md)의 센서를 빠른 것부터 돌립니다. CI(`Harness checks`)가 같은 검사를 다시 합니다.
4. 새 결정을 했으면 [decisions/](../decisions/README.md)에 기록합니다. 같은 실수가 두 번 나오면 센서나 제약으로 바꿉니다.

## 하네스를 고칠 때

- 규칙을 추가하면 **어디에 둘지**부터 정합니다: 행동 지침이면 conventions.md, 기계로 막을 수 있으면 constraints.md에 검사로, 이유는 decisions/에.
- 지시 문서에만 적힌 규칙은 지켜지지 않을 수 있습니다. 반복되는 실수는 검사(제약·센서)로 옮깁니다.
- `AGENTS.md`는 지도 역할만 하도록 짧게 유지합니다. 세부 내용이 쌓이면 docs/로 내립니다.
- 문서 사이 상대 링크는 `tests/test_docs_links.py`가 검사합니다.
