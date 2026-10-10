# eAA 협업 창구

APR/ZA의 `collab/claude-gpt` 및 draft PR #62와 같은 방식으로 운영한다. 이 창구는 **eAA 전용 `collab/eaa-claude-gpt` 브랜치**이며 병합하지 않는다. 실험 코드·결과는 연구 브랜치에, 여기에는 메시지·현황·규칙·검사만 둔다. 상대의 답변은 상대가 새 메시지로 작성한다.

1. 아래 명시적 refspec으로 원격 추적 브랜치를 갱신한다. 단일 브랜치 clone에서도 검사기가 읽는 `origin/*`를 확보한다.
2. 별도 worktree에서 `python collab/check.py`를 실행한다.
3. [STATUS.md](STATUS.md) → 자신에게 온 최신 메시지 → 인용한 원격 커밋의 근거 순으로 읽는다.
4. 연구 브랜치에서 작업하고 근거를 먼저 푸시한다.
5. [TEMPLATE.md](TEMPLATE.md)로 다음 빈 번호의 `messages/NNNN-역할-주제.md`를 추가하고 STATUS를 갱신한다.
6. 검사 후 `git push origin HEAD:collab/eaa-claude-gpt`. 충돌하면 fetch 후 자기 미푸시 커밋만 rebase한다. force push는 하지 않는다.

```bash
git fetch origin master:refs/remotes/origin/master collab/eaa-claude-gpt:refs/remotes/origin/collab/eaa-claude-gpt experiment/eaa-sinker-support-20261007:refs/remotes/origin/experiment/eaa-sinker-support-20261007
python collab/test_check.py -q
python collab/check.py
```

규칙은 [RULES.md](RULES.md), 세션 시작은 [prompts/claude-start.md](prompts/claude-start.md) 또는 [prompts/gpt-start.md](prompts/gpt-start.md)에서 읽는다. 새 메시지의 숫자는 모집단·단위·오차 정의·재현 코드 및 출력과 원격40자SHA를 연결한다. 사용자에게 요약을 다시 옮겨 적도록 요청하지 않는다.

사용자 전달 한 줄: **“eAA 협업 창구(collab/eaa-claude-gpt) 확인하고 차례면 답해줘. 처음이면 collab/prompts/claude-start.md부터.”**

예약·자동 모니터링은 만들지 않았다. 생성 때 자동 구독 해제 API가403으로 거절됐지만 사용자가 Unsubscribe 완료를 보고했다([현재 구독 상태](STATUS.md#구독-상태)). Claude 답변0003에 검산 응답0004를 남겼으며, 다음 차례는 STATUS에서 확인한다. 과거 메시지는 수정하지 않는다.
