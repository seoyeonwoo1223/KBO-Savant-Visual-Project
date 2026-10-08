# EAA-TR1 검토 검산 (Claude)

`tracking_rebuilt_20261009/`(ff8e75edb559f8469bd00d63f86e8848c54c29a8)는 읽기만 했다. 그 README의 재현 명령을 먼저 실행해 로컬 캐시를 만든 뒤 아래를 실행한다. 등록 실험·새 후보·각도 계산이 아니라 게시 패키지의 좌표·산식·잔차 해석 검산이다.

```bash
export PYTHONPATH=src OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2
python analysis/arm_angle/claude_review_tr1_20261009/review_tr1.py   # review_tr1.json
```

- 좌표 부호: FF 우투/좌투 모두 팔쪽 위치·팔쪽 HB 양수. `armside_vx55_over_minus_vy`도 양 손 양수지만 우투 `vx55`가 +1.59m/s(포수 시점 오른쪽=글러브 쪽)라 실제로는 **플레이트 쪽(안쪽) 횡속도 비율**이다. 기존 eAA 특성과 같은 부호 규약이며 이름만 오해 소지가 있다.
- 비행시간 정규화: 9계수 등가속도에서 `movement_k/Δt_k²`가 55/50/23.8/10면 모두 `movement_over_dt2`(=½|a_eff|)와 최대 1.8e−15로 같다. 구간 선택과 무관한 가속도 자체다.
- 구종별 잔차 중심: SI 표시 입력이 있어도 투수 동일가중 IVB 잔차 평균이 FF −0.87cm, SI +2.50cm, HB 잔차 FF +0.19, SI −1.31cm. 공통26명 SI−FF +5.655cm에는 이 모델 중심 차이가 섞인다.
- 위치 기여: 같은 파이프라인 재구현(차이 0.0)에서 px·pz를 빼면 투수 동일가중 OOF MAE가 HB 9.782→9.828, IVB 8.340→8.372cm로 거의 같다. FF 투구 단위 상관도 px–HB 0.016, pz–IVB −0.043. 잔차는 사실상 속력·신장·손·SI 조건부 움직임 편차이며, 위치가 움직임을 포함하는 구조적 중복은 수치상 작다.
