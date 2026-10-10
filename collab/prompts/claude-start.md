# 새 검토 세션 시작

아래 지시를 그대로 사용한다. 같은 코드·캐시를 직접 확인하고, 상대 결론에 맞추지 않는다.

```text
KBO-Savant-Visual-Project의 eAA 연구 검토를 맡아줘. APR/ZA와 같은 소통 창구지만 eAA 전용 브랜치는 collab/eaa-claude-gpt다. 실험·결과 브랜치는 experiment/eaa-sinker-support-20261007이고 운영 파일을 바꾸는 작업은 승인되지 않았다.

git fetch origin master:refs/remotes/origin/master collab/eaa-claude-gpt:refs/remotes/origin/collab/eaa-claude-gpt experiment/eaa-sinker-support-20261007:refs/remotes/origin/experiment/eaa-sinker-support-20261007
git worktree add ../kbo-eaa-collab origin/collab/eaa-claude-gpt
그 폴더에서 python collab/check.py를 통과한 뒤 RULES.md → STATUS.md → 자신 앞으로 온 최신 메시지 → 원격 인용 SHA의 근거를 읽어줘.

최신 결과 메시지가 있으면 싱커 앵커의 투수 분리·FF100 선택 편향·월 라벨 범위·고슬롯 부재·MLB 직접 성분과 KBO bridge 구분을 확인하고, standalone 지원값 제거/고정 재적합과 full 입력 민감도의 해석을 따로 검토해줘. 확보된 inputs와 frozen_helpers로 run_sinker.py / run_support.py / verify.py를 재현할 수 있다. 과거 전체 원문이 확보됐다고 가정하지 마. 운영 채택·과거 기준의 소급 변경·KBO 참고각도 학습·이미지/Y2Y는 하지 마.

주장별 동의/부분 동의/반대/판정 불가 및 재현 근거를 다음 빈 번호의 collab/messages/NNNN-claude-주제.md로 남겨줘. 기존 메시지와 상대 결과는 고치지 마. 자기 근거는 먼저 연구 브랜치에 새 파일로 푸시하고 원격40자SHA로 인용해줘. STATUS의 열린 스레드·다음 차례를 갱신하고 python collab/check.py 후 창구에 푸시해줘. force push·병합·예약·PR 구독은 하지 마. 결과가 아직 없는 등록 메시지뿐이면 정의 검토만 하고 상대 실행 결과를 기다리는 상태를 남겨줘.
```
