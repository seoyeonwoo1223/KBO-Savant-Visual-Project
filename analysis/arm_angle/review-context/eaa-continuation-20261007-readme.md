# eAA 연구 인계 자료

로컬 클라우드 경로를 다른 스레드와 공유할 수 없어, 인계 ZIP과 프롬프트를 별도 브랜치에 저장했습니다.

- 인계 ZIP: `analysis/arm_angle/review-context/eaa-continuation-20261007.zip`
- ZIP SHA: `analysis/arm_angle/review-context/eaa-continuation-20261007.zip.sha256.txt`
- 프롬프트: `analysis/arm_angle/continuation-prompt-20261007.md`

ZIP 안 `CONTINUE.md`와 `PACKAGE-README.md`를 먼저 읽고, `verify-package.py`로 파일 SHA를 확인하세요. ZIP은 전체 저장소나 원본 데이터 전체가 아닌 연구용 경량 snapshot입니다. 새 스레드에서는 이 브랜치에서 ZIP을 직접 가져오면 됩니다. 최신 연구 코드는 ZIP 안에 포함되어 있습니다.

```bash
git fetch origin codex/eaa-continuation-20261007
git show FETCH_HEAD:analysis/arm_angle/review-context/eaa-continuation-20261007.zip > /tmp/eaa-continuation-20261007.zip
```

사용자 작업 트리를 덮어쓰지 않고 별도 폴더에서 인계 묶음을 확인하세요. 운영은 eAA-v3이며 최신 잔차 후보는 미채택 상태입니다. 원래 저장소에서 실행한 전체 검산과 경량 묶음에서 가능한 재현 검증을 구분하세요.
