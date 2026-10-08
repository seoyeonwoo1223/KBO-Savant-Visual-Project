# 2026 KBO 궤적 파생 연구: 별도 재생성판

**2026-03-28~10-04의 213,628구·293명·694경기에서 기본 유효213,540구를 확인하고 12군·109개 파생 열을 산출했다.** 107개는 같은 궤적의 결정적 변환, 2개는 투수 분리 위치 조건부 움직임 잔차다. 이전 미게시 코드·스냅샷을 확보하지 못했으므로 새 구현이며 이전209열 구현과 같다고 주장하지 않는다. 수량 일치는 입력 바이트 동일성이나 eAA 정확도 개선을 뜻하지 않는다. 운영 eAA-v3·참고 범위는 유지한다.

## 실제 확보한 자료와 이전 기록의 차이

Git HTTPS/`gh` REST API로 세 원격 브랜치와 PR #69를 조회했다. 이 세션에는 GitHub 앱 도구/검색 도구가 노출되지 않았지만 서버 인증/원격 읽기는 정상이다. 플러그인 재연결은 요청하지 않았다.

- continuation `d272fbe4244c1f155dede8b209fda01c95a53b6b`: `continuation-prompt-20261007.md`와 인계 ZIP. CONTINUE 읽기 → MANIFEST 187파일 SHA 확인 → 경량 smoke 순으로 진행했다. MLB2,295시즌·고정학습1,095행·KBO195명 예측/잔차계수 재현 최대차3.60e−12°/1.85e−12. 이 smoke는 전체 원본 감사가 아니다.
- 연구 `35891bdbe96b7feb4f42ecff33c8895f8aee1284`: 기존 SI1/SUP1/CL1 결과와 **2026 canonical 월 파일**. 해당 브랜치 canonical은10월5일까지215,083구이며 선택 입력은10월4일까지다. master 확인 SHA `235e6f91c84e586c09c07f20badd9ec451e305c6`의 범위는10월7일까지이나 이번 입력으로 사용하지 않았다.
- 소통 `ec3443501f09deea5d0b8d18b6bddeb09c52473b`: 메시지0001–0006, Claude 최신0005 및 인계 응답0006. PR은 open/draft/미병합이며 조회 시 댓글/리뷰/리뷰댓글0개다.
- 기존 싱커 패키지의 최신 HEAD manifest는 `gates.md` 추가 때문에 불일치한다. 과거 gates를 고치지 않고 Claude가 안내한 `661a5c0229f6b6f274458221d6230b22bfa700b9`를 별도 폴더에 읽어72파일 SHA 검증을 통과했다.
- 원격에는 `tracking_derived_20261008/`와 이전 tracking 답변/등록 파일이 없다. 두 미게시 커밋 API는422였다. portable ZIP은 없으며, 별도 복원이나 이전 결과를 확보했다고 주장하지 않는다.

인계의189,687구 투구 캐시는 기하·속도·무브먼트 특징만 담고 원시9계수·pitch_id가 없어 원래 면 계산으로 되돌릴 수 없다. 이번에는 실제 원격 canonical에서 필요한39열을 선택했고, 각 원본 파일이 고정 커밋의 Git blob과 일치함을 확인했다. [source.json](source.json)에 조회일·커밋·기간·원본SHA·선택입력SHA·인계 출처를 기록했다. [선택 입력](inputs/selected_2026.parquet)은 약19MiB이며 대형 파생 캐시/venv는 게시하지 않는다.

| 항목 | 이전 참고 기록 | 이번 재생성판 |
|---|---:|---:|
| 투구/투수/경기 | 213,628 / 293 / 694 | 213,628 / 293 / 694 |
| 기본 유효 | 213,540 | 213,540 |
| 파생 지표군/열 | 12 / 209 | 12 / 109 |
| 결정적 변환/평가 잔차 | 207 / 2 | 107 / 2 |

입력 전체213,628행을 보존했다. y0=50ft130,150구·55ft83,390구·결측88구다. 결측을 채우지 않았다. raw eAA 수치·품질 적격은213,536구로 기본 유효와4구 다르다. 이는 공원/측정기간 상대 보정을 적용한 운영 입력 재생성이 아니다. FF와 FT/SI 통합 SI의 위치 OOF 잔차는103,216구/292명에 있고 다른 구종은 결측이다.

## 산식과 해석

계산 전 [gates.md](gates.md)를 커밋 `779bf48f112b52e5254677e42398c3b90b8a3d95`에 고정하고 별도 EAA-TR1 등록 경로를 선언했다. 과거 SI1/SUP1/CL1 gates/실패 판정을 수정하지 않았다. [features.py](features.py)와 [columns.json](columns.json)이 정확한 열 목록이다.

입력 ft/ft·s⁻¹/ft·s⁻²를 SI로 변환한다. `p(t)=p0+v0t+at²/2`, `v(t)=v0+at`, y면의 홈 방향 근을 사용한다. 55/50/23.8/10ft/앞면17÷12ft를 계산한다. 55면 역외삽은 실제 릴리즈/익스텐션이 아니다. 2026 px는 중간면8.5÷12ft, pz는 앞면이며 둘 다 ft다. 포수 시점 x와 손 부호를 명시했다.

중력 제거 `HB=.5axΔt²`, `IVB=.5(az+g)Δt²`는 동일 가속도의 결정적 변환이다. 비행시간 정규화는 **투구별로** 계산한 뒤 평균한다. `mean(M/Δt²)`를 `mean(M)/mean(Δt)²`로 바꾸지 않는다. 50/55ft 구간은 별도 열이다. 이 비행시간 정규화는0005 제안의 기술적 변환 범위이며 새 각도 후보 시험/CL2 실행이 아니다.

| 군 | 열 수 |
|---|---:|
| 면 위치·속도 | 15 + 15 |
| 비행시간/구간·속력·진입각 | 9 + 5 + 10 |
| 신장/손 정규화·곡률/접선가속도 | 10 + 10 |
| 중력 제거 움직임·가속도 분해 | 16 + 9 |
| 보고값 일관성·비행시간 정규화 | 4 + 4 |
| 위치 조건부 OOF 잔차 | 2 |

OOF 목표는50ft→앞면 팔 쪽HB/IVB(cm), 입력은 팔 쪽px(m)·존 정규화pz·55면 속력·신장·손·SI 여부다. 고정2차 다항→학습fold 가중표준화→Ridgeα100, 투수 노출 역수 가중, GroupKFold5를 사용한다. 같은 투수는 한 평가fold이며 선수/각도 ID를 예측 입력으로 넣지 않는다. 선수 참고각도는 어디에도 정답으로 쓰지 않는다. 잔차는 기술적 연관이며 위치 인과효과·실제 팔각도 오차가 아니다.

## FF/SI 및 관심 선수 진단

두 구종 각각 기본유효100구 이상인 공통26명의 투수 동일가중 SI−FF 평균 IVB 차이는−10.344cm, `movement/Δt²` 차이는−0.200m/s²다. 위치 조건부 OOF IVB 잔차 차이는+5.655cm다. [paired_FF_SI.csv](results/paired_FF_SI.csv)는 동일 투수 시즌 내 구종 평균의 차이이며 동일 투구 대응이나 외부 정답 개선량이 아니다. raw HB 열은 포수 시점이므로 손이 다른 집단의 raw 부호 평균을 팔 쪽 편향으로 해석하지 않는다.

| 선수 | FF구수 | SI구수 | FF OOF IVB 잔차(cm) | 인계 운영v3 / 미채택결합1(°) |
|---|---:|---:|---:|---:|
| 전준표 | 798 | 0 | +0.738 | 40.822 / 43.901 |
| 박준현 | 912 | 0 | +3.151 | 46.276 / 50.195 |
| 안우진 | 804 | 11 | +5.016 | 43.059 / 46.661 |
| 손주영 | 379 | 6 | −3.898 | 50.791 / 50.457 |
| 문동주 | 240 | 0 | +0.495 | 50.765 / 48.975 |

전준표·박준현·안우진의 기존 미채택 후보 상승과 손주영·문동주의 부재/하락을 함께 보존했다. 오른쪽 값은 ZIP에서 확보하고 smoke 검증한 **이전 연구값**이며 이번 raw 특징으로 새로 맞춘 각도가 아니다. 대상5명은 SI100 비교에 들어갈 수 없다. SI0은 이 선택 입력에서 해당 구종 행이 없다는 뜻이며 실제 선수의 전체 능력/다른 출처 표본을 뜻하지 않는다. [focus_players.csv](results/focus_players.csv)에 부족 표본을 표시했다.

위치 모델의 투수 동일가중 HB/IVB OOF MAE는9.782/8.340cm다. 평균잔차가 거의0이어도 큰 잔여 변동이 남는다. 이는 움직임 예측의 오차이며 eAA 오차가 아니다. 입력부터 같은 궤적에서 나온 열이므로 새 독립 동작 측정·KBO 고슬롯 정확도 증거를 만들지 않는다. 실제 암슬롯·광학축·RPM·효율·gyro·SSW·익스텐션은 측정하지 않았다.

## 이번 검증

- 합성 사례7개 통과: 단위·직선·중력낙하·좌우대칭·기준면변환·결측/역진행·곡률.
- 독립 scalar root512구×5면=2,560면. 위치 최대차9.64e−14m, 속도2.84e−14m/s, 면 방정식 잔차4.72e−15m.
- SciPy ODE 적분16구×5면: 최대차7.30e−14m. canonical50/55면10필드×213,540구 대조 최대차3.08e−14SI.
- 원시 보고 px/pz/HB/IVB와 파생값은 각각 실제 지정면에서 대조했다. 최대절대차0.174/0.177/0.053/0.053cm, >1cm0건. 반올림 차이가 남으므로 원시 보고값을 바꾸지 않았다.
- OOF 투수 교집합0. 독립 가중 정상방정식과 sklearn 예측 최대차7.33e−12cm.
- 동일 선택 입력 재실행: 연구 산출물11개(큰 캐시 포함)의 byte SHA 동일.
- 인계 잔차 테스트8개 통과. 이번 연구 worktree 전체 pytest257개 및 별도 합성7개 통과. 창구 테스트9개 통과. [verification.json](results/verification.json), [fold_verification.json](results/fold_verification.json), [reproducibility.json](reproducibility.json)을 함께 남겼다.

수치 일관성은 검증된 범위 내에서 공유할 수 있다. 외부 각도 정확도는 미검증이다. 2024/2025년5~9월은 재사용이며 실제 미사용 기간 평가를 실행하지 않았다. 이번 입력에는 KBO 실측AA가 없으므로 전체 평균오차·낮은IVB 음의오차·집단편향·고슬롯 보호의 **각도 성과는 모두 판정 불가**다. 후속 검토 기준은 gates에 분리 선언했고 과거 채택 한도를 낮추지 않았다. 새 각도 후보·커터 앵커·운영 업데이트는 없다.

## 재현

Python3.12.14 및 [environment.json](environment.json)의 실제 버전/[requirements-research.txt](requirements-research.txt)를 사용했다. 저장소 루트에서 실행한다. 선택 입력이 포함되므로 원본 월 파일이나 인계 ZIP을 다시 수집할 필요 없이 같은 연구 결과를 만들 수 있다.

```bash
export PYTHONPATH=src OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2
python analysis/arm_angle/tracking_rebuilt_20261009/record_manifest.py --verify
python -m pytest analysis/arm_angle/tracking_rebuilt_20261009/test_features.py -q
python analysis/arm_angle/tracking_rebuilt_20261009/run.py
python analysis/arm_angle/tracking_rebuilt_20261009/verify.py
python analysis/arm_angle/tracking_rebuilt_20261009/reproduce.py
```

약182MB의 전체109열 pitch 파생표는 `.cache/arm_angle/tracking_rebuilt_20261009/derived_pitches.parquet`에 재생성되며 게시하지 않는다. SHA는 [summary.json](results/summary.json)에 있다. 결과 캐시가 없는 새 환경에서는 run/verify 후 reproduce를 실행한다. MANIFEST는 먼저 검사하며 새 환경의 버전/직렬화가 다르면 차이를 기록하고 manifest를 덮어쓰지 않는다.

원본 확보 단계만 다시 수행할 때는 새 폴더·고정 소스커밋·정상 fetch refs를 사용하고 `acquire.py --handoff-zip <확보한 ZIP>`를 실행한다. 기존 선택 입력은 덮어쓰지 않는다. 공개 연구 파일 SHA는 [MANIFEST.json](MANIFEST.json)에 기록하며 인계 ZIP은 고정 continuation 브랜치에서 확보할 수 있다.
