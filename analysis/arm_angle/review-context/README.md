# 다른 클라우드 세션으로 eAA 검토 자료 전달

프롬프트와 연구 ZIP은 처음에는 Codex 컨테이너에만 저장되어 다른 Claude 컨테이너나 GitHub의 master에서 보이지 않았다. 이 전달 브랜치에는 필요한 파일 네 개를 포함한다.

1. `analysis/arm_angle/claude-cross-check-prompt.md` — 전체 목표·진행 내용·병목·검토 요청
2. 이 README — 전달·검증 방법
3. `prepare_review_context.py` — Python 표준 라이브러리로 ZIP과 모든 첨부의 SHA-256을 검증하고 새 임시 폴더에 추출
4. `eaa-claude-review-context-20261003.zip` — 84개 파일·14,073,114바이트 연구 스냅샷

ZIP SHA-256: `aa5a482059a238b56b4cf6000ff2b49f738c87dab8b99ba5673d4e44d14dbcee`

## 현재 checkout을 유지하고 가져오기

저장소에서 실행한다. `git archive`는 현재 작업 파일이나 브랜치를 바꾸지 않는다.

```bash
git fetch origin codex/eaa-claude-review-20261005
review_delivery_dir=$(mktemp -d /tmp/eaa-review-delivery.XXXXXX)
git archive FETCH_HEAD \
  analysis/arm_angle/claude-cross-check-prompt.md \
  analysis/arm_angle/review-context | tar -x -C "$review_delivery_dir"
python3 "$review_delivery_dir/analysis/arm_angle/review-context/prepare_review_context.py"
```

출력의 `review_root`를 근거의 루트로 삼고 `prompt_path`를 읽어 교차 점검한다. 새 검토 브랜치를 이미 checkout했다면 아래 한 줄로 준비할 수 있다.

```bash
python3 analysis/arm_angle/review-context/prepare_review_context.py
```

## 스냅샷 범위

연구 문서·선택 코드·CSV/JSON·모델·신장표·전준표 2026 선택 canonical 1,163구를 포함한다. 전준표 158/159, 이강준 50/51, 김광현 89/90, 윤현 106/107의 무표시 디코딩 PNG 8개와 이전 관절점/공 표시 JPG 4개, 선택 pose와 해시 manifest도 포함한다.

스냅샷은 `c363d008a`의 생산 eAA-v1과 당시 미커밋 연구를 기준으로 만들었다. 현재 master의 최신 데이터·코드와 같다고 가정하지 않는다. 압축을 푼 프롬프트는 10월 3일 생성 원문이고, 전달 브랜치의 바깥 프롬프트에는 이번 전달 경로를 추가했다.

전체 canonical, 원본 영상 전체, TM/Statcast 원문 전체, 학습 캐시, 설치된 의존성은 생략했다. 일부 보고서의 `/workspace/...` 경로는 원래 Codex 컨테이너의 출처 기록이며 다른 컨테이너에서 존재한다고 가정하지 않는다. 따라서 이 묶음은 독립 검토에 필요한 선택 근거이며 전체 파이프라인을 바로 실행하는 환경은 아니다.

검토 중 생산 모델·공식 신장·canonical·웹 출력은 수정하거나 배포하지 않는다. 전달 브랜치를 master에 병합할 필요는 없다.
