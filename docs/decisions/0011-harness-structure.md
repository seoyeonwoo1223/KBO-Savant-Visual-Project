# 0011. 하네스를 4개 구성요소로 나누고 AGENTS.md는 지도로 유지

- **상태**: 채택 (2026-10)

## 맥락
에이전트 규칙, 구조 설명, 검사 목록, 결정 배경이 모두 `CLAUDE.md`(250줄 이상)와 README에 섞여 있었습니다. 에이전트는 매 세션 이 전체를 읽어야 했고, 규칙의 이유와 강제 여부를 구분하기 어려웠습니다.

## 결정
하네스를 네 부분으로 나눕니다([../harness/README.md](../harness/README.md)).
1. **지시 문서**: `AGENTS.md`(약 100줄 지도) + `docs/conventions.md`(세부 규칙). `CLAUDE.md`는 `@AGENTS.md`만 불러옵니다.
2. **아키텍처 제약**: 기계 검사로 막는 것. `docs/harness/constraints.md`에 목록.
3. **피드백 루프**: 가이드와 센서를 빠른 순서로. `docs/harness/feedback.md`.
4. **지식 저장소**: `docs/decisions/`(이 목록), `docs/architecture.md`, `analysis/`.

## 기각한 대안
- `CLAUDE.md` 하나에 모두 유지: 길어질수록 매 세션 비용이 커지고, 다른 에이전트(Codex 등)가 읽는 `AGENTS.md`와 내용이 갈라집니다.
- `AGENTS.md`와 `CLAUDE.md`를 각각 유지: 두 사본이 서로 어긋납니다.

## 결과
- 문서 링크는 `tests/test_docs_links.py`가 검사합니다.
- 반복되는 실수는 지시 문서가 아니라 제약·센서로 옮깁니다.
