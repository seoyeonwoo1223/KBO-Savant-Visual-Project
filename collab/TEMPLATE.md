---
id: 0000
from: claude
to: gpt
date: 2026-10-05
type: 요청
re: -
master: 0000000000000000000000000000000000000000
model_version: za7.8-neutral-apr
work: experiment/branch-name@0000000000000000000000000000000000000000
---

<!--
머리말 규칙 (collab/check.py가 검사합니다)
- 파일 이름: messages/NNNN-보낸이-주제.md (주제는 영문 소문자·숫자·하이픈). id·from이 파일 이름과 같아야 합니다.
- from/to: claude, gpt, user. 여럿이면 쉼표로.
- type: 개설 | 요청 | 응답 | 결과 | 정정 | 결정요청
- re: 답하는 앞선 메시지 id (쉼표로 여럿), 없으면 -
- master: 작업 전에 fetch한 origin/master 전체 SHA. model_version: 그때 zone_decision.py의 MODEL_VERSION
- work: 인용하는 작업 브랜치@전체 SHA (쉼표로 여럿), 없으면 -. 모두 원격에 있어야 합니다.
-->

# 제목

## 요약

세 줄 안으로.

## 주장과 판정

상대 주장에 답할 때는 상대의 주장 ID를, 새 주장은 `<메시지 id>-C<번호>`를 씁니다.

| ID | 주장 | 판정 | 근거 (`파일:줄@SHA` 또는 재현 명령·출력 파일) |
|---|---|---|---|
| 0000-C1 | | 동의 / 부분 동의 / 반대 / 판정 불가 | |

## 요청

상대에게 바라는 것. 번호를 붙입니다.

## 사용자 결정 필요

없으면 "없음". 있으면 STATUS.md "사용자 결정 대기"에도 올립니다.

## STATUS.md 변경

이번에 고친 행.

## 다음 차례

- 다음: gpt | claude | user
- 사용자 전달 한 줄: "협업 창구(collab/claude-gpt) 확인하고 차례면 답해줘."
