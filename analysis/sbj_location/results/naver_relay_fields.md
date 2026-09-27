# 네이버 relay 투구 단위 조사

## Q1. 위치·궤적

원문 94이닝에서 문자 투구 3295행을 읽었다. `textOptions.ptsPitchId`와 `ptsOptions.pitchId`로 연결한 위치 행은 3293행이다. `ptsOptions`에는 `crossPlateX`, `crossPlateY`, `topSz`, `bottomSz`, `x0/y0/z0`, `vx0/vy0/vz0`, `ax/ay/az`가 있다. 직접적인 `crossPlateZ`/`pz` 필드는 없다.

`crossPlateY`는 위치 좌표의 y 기준면 후보, `crossPlateX`는 그 면의 수평 좌표 후보이다. 궤적 위치·존 높이의 단위는 feet, 속도는 ft/s, 가속도는 ft/s²로 보인다(VB 수치 및 운동학 대조에 근거한 추정). 관측된 `y0`는 50 ft다. `crossPlateY`는 2020–2021년에 1.4167 ft(앞면 17/12 ft), 2024–2026년에 0.7083 ft(중간면 8.5/12 ft)로, VB 시즌별 `px` 평면 규칙과 일치한다. `pz`에 해당하는 직접 필드는 없으며, 앞면 y=17/12 ft에서 궤적 z를 계산한 값만 비교했다. 기준면·단위에 대한 API 공식 정의는 확인하지 못했다.

## Q2. VB 원본과 같은 값인가

대응표의 `mapping`이 `확정`으로 시작하고 VB 단일 행과 네이버 단일 투구 ID가 연결된 82쌍을 비교했다. 제외 사유: {}. 수평 위치 차이 절댓값 0.01 ft 이하는 76/82쌍, 앞면 궤적 z와 VB `pz` 차이 0.01 ft 이하는 73/82쌍이다. 수평 위치 차이 0.1 ft 초과는 6쌍({'20260509KTWO0': 6})이다. 일부 확정 투구의 위치·궤적은 크게 다르다. 네이버와 VB가 같은 공급원을 쓸 수 있으므로 일치해도 독립적인 위치 검증이 아니다.

| 비교(네이버 − VB) | n | 중앙 절댓값 | 95백분위 절댓값 | 최대 절댓값 |
|---|---:|---:|---:|---:|
| `crossPlateX − px` | 82 | 0.00309 | 0.72759 | 2.79028 |
| `topSz − szTop` | 82 | 0.00000 | 0.00000 | 0.00035 |
| `bottomSz − szBot` | 82 | 0.00000 | 0.00000 | 0.00045 |
| `vx0 − vx0` | 82 | 0.00033 | 2.95907 | 8.88976 |
| `vy0 − vy0` | 82 | 0.00000 | 2.21600 | 16.02000 |
| `vz0 − vz0` | 82 | 0.00025 | 2.59120 | 5.77026 |
| `x0 − x0` | 82 | 0.00026 | 0.10425 | 2.54172 |
| `y0 − y0` | 82 | 0.00000 | 0.00000 | 0.00000 |
| `z0 − z0` | 82 | 0.00029 | 0.12007 | 0.56166 |
| `ax − ax` | 82 | 0.00027 | 5.96898 | 21.87350 |
| `ay − ay` | 82 | 0.00030 | 2.64120 | 11.38500 |
| `az − az` | 82 | 0.00022 | 2.04500 | 18.81146 |
| `PTS trajectory z at y=17/12 − VB pz` | 82 | 0.00282 | 1.14475 | 2.40248 |

## Q3. 복제·선행 기록과 투구 ID

동일 경기에서 문자 기록이 반복된 투구 ID는 23개다. 그중 23개는 반복 행 모두 `ptsOptions` 기록도 있다. 동일 카드 안 반복 14개, 카드 사이 반복 9개다. 대응표의 복제·선행 사례(채은성, 노진혁, 허경민, 정수빈, 박해민, 오스틴, 조수행, 김휘집 등)에서도 같은 ID가 반복된다. 따라서 투구 ID는 중복을 묶는 단서지만 응답 전체의 `ptsOptions`가 공당 단 한 행은 아니다. 같은 카드 안이나 복제 카드에 추적 행도 반복된다. UI 그림의 중복 제거 이유는 API만으로 확정할 수 없다.

반례/주의: 2025-08-09 임지열은 현재 API에 같은 7개 ID를 담은 카드 두 장이 있다. 기존 사용자 캡처의 7구 관찰과 카드 수가 다르므로 양쪽을 기록하며 어느 시점의 표시가 맞는지는 정하지 않는다.

## 수집 범위

| 경기 | 예상 이닝 | 성공 이닝 | 실패 이닝 |
|---|---:|---:|---|
| 20250809OBWO0 | 9 | 9 | 없음 |
| 20240724WOOB0 | 9 | 9 | 없음 |
| 20240404LTHH0 | 9 | 9 | 없음 |
| 20240504OBLG0 | 9 | 9 | 없음 |
| 20260509KTWO0 | 11 | 11 | 없음 |
| 20250614HTNC0 | 9 | 9 | 없음 |
| 20210606HHNC0 | 9 | 9 | 없음 |
| 20210512SSKT0 | 9 | 9 | 없음 |
| 20210828NCHH0 | 9 | 9 | 없음 |
| 20200630LTNC0 | 11 | 11 | 없음 |

## 대상 408구 분류

| 출처 | found_with_location | found_no_location | not_in_naver | ambiguous |
|---|---:|---:|---:|---:|
| captured | 0 | 0 | 7 | 0 |
| half_short | 378 | 0 | 23 | 0 |

모호 후보: 없음.

`half_short` 단일 네이버 후보 중 TrackMan−1.5km/h 기준 편차가 ±3km/h를 넘는 행은 8건이다. 카운트 전이 일치 378건(독립 대조값, 연결 조건 아님). VB 원본 별도 검사: {'yes': 134, 'no': 249, 'uncertain_speed_conflict': 18}.

구속 충돌 대상: #33 200630_222543, #34 200630_222601, #149 210606_195520, #154 210606_195742, #183 210606_203040, #243 210606_210809, #248 210606_211243, #393 210828_202637.

`half_short`에는 VB에 이미 있는 공도 포함된다. `vb_already_present`는 같은 반이닝·투수·타자·타석 내 순번과 TrackMan−1.5km/h 기준 구속 ±3km/h로 별도 검사한 결과다. 구조상 VB 후보는 있지만 속도가 어긋나면 `uncertain_speed_conflict`로 남긴다. 네이버 단일 후보도 구속 차이를 별도 열에 기록하고, 카운트는 연결 조건에 쓰지 않았다. 타석 분리·표시 구속 오류 때문에 유일한 구조 후보가 실제 같은 공임을 보장하지는 않는다.

문자·PTS 배열 불일치: 2건 (`ptsPitchId=-1`인 문자 행은 위치 null).

## 투구 항목의 실제 키·자료형·예시

아래 목록은 받은 10경기의 투구 `textOptions`와 `ptsOptions`를 재귀적으로 조사했다. `textOptions.text`의 중계 문장 예시는 저장하지 않았다. 값은 길이를 제한한 예시다.

| 경로 | 관측 자료형 | 예시 |
|---|---|---|
| `ptsOptions.ax` | float | `-0.008311` |
| `ptsOptions.ay` | float | `10.8223` |
| `ptsOptions.az` | float | `-0.478394` |
| `ptsOptions.ballcount` | int | `1` |
| `ptsOptions.bottomSz` | float | `1.1487` |
| `ptsOptions.crossPlateX` | float | `-0.000159` |
| `ptsOptions.crossPlateY` | float | `0.7083` |
| `ptsOptions.inn` | int | `1` |
| `ptsOptions.pitchId` | str | `200630_183049` |
| `ptsOptions.stance` | str | `L` |
| `ptsOptions.topSz` | float | `2.72976` |
| `ptsOptions.vx0` | float | `-0.022311` |
| `ptsOptions.vy0` | float | `-100.138` |
| `ptsOptions.vz0` | float | `-0.001795` |
| `ptsOptions.x0` | float | `-0.006548` |
| `ptsOptions.y0` | float | `50.0` |
| `ptsOptions.z0` | float | `2.86166` |
| `textOptions.batterRecord` | dict | `26개` |
| `textOptions.batterRecord.ab` | int | `1` |
| `textOptions.batterRecord.backnum` | str | `1` |
| `textOptions.batterRecord.batOrder` | int | `1` |
| `textOptions.batterRecord.bb` | int | `0` |
| `textOptions.batterRecord.birth` | str | `19870605` |
| `textOptions.batterRecord.cin` | NoneType, str | `None` |
| `textOptions.batterRecord.cout` | NoneType | `None` |
| `textOptions.batterRecord.hbp` | int | `0` |
| `textOptions.batterRecord.height` | str | `169.0` |
| `textOptions.batterRecord.hit` | int | `0` |
| `textOptions.batterRecord.hitType` | str | `우투우타` |
| `textOptions.batterRecord.hr` | int | `0` |
| `textOptions.batterRecord.name` | str | `강승호` |
| `textOptions.batterRecord.pa` | int | `1` |
| `textOptions.batterRecord.pcode` | str | `50208` |
| `textOptions.batterRecord.pos` | int | `0` |
| `textOptions.batterRecord.posName` | str | `1루수` |
| `textOptions.batterRecord.psHra` | float | `0.0` |
| `textOptions.batterRecord.rbi` | int | `0` |
| `textOptions.batterRecord.run` | int | `0` |
| `textOptions.batterRecord.seasonHra` | float | `0.133` |
| `textOptions.batterRecord.seqno` | int | `1` |
| `textOptions.batterRecord.so` | int | `0` |
| `textOptions.batterRecord.todayHra` | float | `0.0` |
| `textOptions.batterRecord.vsHra` | str | `0.000` |
| `textOptions.batterRecord.weight` | str | `68.0` |
| `textOptions.currentGameState` | dict | `16개` |
| `textOptions.currentGameState.awayBallFour` | str | `0` |
| `textOptions.currentGameState.awayError` | str | `0` |
| `textOptions.currentGameState.awayHit` | str | `0` |
| `textOptions.currentGameState.awayScore` | str | `0` |
| `textOptions.currentGameState.ball` | str | `0` |
| `textOptions.currentGameState.base1` | str | `0` |
| `textOptions.currentGameState.base2` | str | `0` |
| `textOptions.currentGameState.base3` | str | `0` |
| `textOptions.currentGameState.batter` | str | `50150` |
| `textOptions.currentGameState.homeBallFour` | str | `0` |
| `textOptions.currentGameState.homeError` | str | `0` |
| `textOptions.currentGameState.homeHit` | str | `0` |
| `textOptions.currentGameState.homeScore` | str | `0` |
| `textOptions.currentGameState.out` | str | `0` |
| `textOptions.currentGameState.pitcher` | str | `50393` |
| `textOptions.currentGameState.strike` | str | `0` |
| `textOptions.currentPlayersInfo` | dict | `2개` |
| `textOptions.currentPlayersInfo.away` | dict | `6개` |
| `textOptions.currentPlayersInfo.away.currentGamePlayerStats` | dict | `17개` |
| `textOptions.currentPlayersInfo.away.currentGamePlayerStats.ab` | int | `0` |
| `textOptions.currentPlayersInfo.away.currentGamePlayerStats.ballCount` | int | `0` |
| `textOptions.currentPlayersInfo.away.currentGamePlayerStats.batOrder` | int | `0` |
| `textOptions.currentPlayersInfo.away.currentGamePlayerStats.batResult` | NoneType, str | `` |
| `textOptions.currentPlayersInfo.away.currentGamePlayerStats.bb` | int | `0` |
| `textOptions.currentPlayersInfo.away.currentGamePlayerStats.bhome` | int | `0` |
| `textOptions.currentPlayersInfo.away.currentGamePlayerStats.era` | float | `0.0` |
| `textOptions.currentPlayersInfo.away.currentGamePlayerStats.hit` | int | `0` |
| `textOptions.currentPlayersInfo.away.currentGamePlayerStats.hr` | int | `0` |
| `textOptions.currentPlayersInfo.away.currentGamePlayerStats.inn` | NoneType, str | `0.0` |
| `textOptions.currentPlayersInfo.away.currentGamePlayerStats.kk` | int | `0` |
| `textOptions.currentPlayersInfo.away.currentGamePlayerStats.pa` | int | `0` |
| `textOptions.currentPlayersInfo.away.currentGamePlayerStats.rbi` | int | `0` |
| `textOptions.currentPlayersInfo.away.currentGamePlayerStats.run` | int | `0` |
| `textOptions.currentPlayersInfo.away.currentGamePlayerStats.seasonEra` | float | `0.0` |
| `textOptions.currentPlayersInfo.away.currentGamePlayerStats.so` | int | `0` |
| `textOptions.currentPlayersInfo.away.currentGamePlayerStats.strikeCount` | int | `0` |
| `textOptions.currentPlayersInfo.away.currentSeasonStats` | dict | `17개` |
| `textOptions.currentPlayersInfo.away.currentSeasonStats.ab` | int | `0` |
| `textOptions.currentPlayersInfo.away.currentSeasonStats.bb` | int | `0` |
| `textOptions.currentPlayersInfo.away.currentSeasonStats.er` | int | `0` |
| `textOptions.currentPlayersInfo.away.currentSeasonStats.era` | float | `0.0` |
| `textOptions.currentPlayersInfo.away.currentSeasonStats.gameCount` | int | `0` |
| `textOptions.currentPlayersInfo.away.currentSeasonStats.hit` | int | `0` |
| `textOptions.currentPlayersInfo.away.currentSeasonStats.hr` | int | `0` |
| `textOptions.currentPlayersInfo.away.currentSeasonStats.hra` | float | `0.0` |
| `textOptions.currentPlayersInfo.away.currentSeasonStats.inn` | NoneType, str | `10.1` |
| `textOptions.currentPlayersInfo.away.currentSeasonStats.inn2` | NoneType, str | `10 1/3` |
| `textOptions.currentPlayersInfo.away.currentSeasonStats.kk` | int | `0` |
| `textOptions.currentPlayersInfo.away.currentSeasonStats.l` | int | `0` |
| `textOptions.currentPlayersInfo.away.currentSeasonStats.obp` | float | `0.0` |
| `textOptions.currentPlayersInfo.away.currentSeasonStats.rbi` | int | `0` |
| `textOptions.currentPlayersInfo.away.currentSeasonStats.s` | int | `0` |
| `textOptions.currentPlayersInfo.away.currentSeasonStats.w` | int | `0` |
| `textOptions.currentPlayersInfo.away.currentSeasonStats.whip` | float | `0.0` |
| `textOptions.currentPlayersInfo.away.currentSeasonStatsOnOpponents` | dict | `17개` |
| `textOptions.currentPlayersInfo.away.currentSeasonStatsOnOpponents.ab` | int | `0` |
| `textOptions.currentPlayersInfo.away.currentSeasonStatsOnOpponents.bb` | int | `0` |
| `textOptions.currentPlayersInfo.away.currentSeasonStatsOnOpponents.er` | int | `0` |
| `textOptions.currentPlayersInfo.away.currentSeasonStatsOnOpponents.era` | float | `0.0` |
| `textOptions.currentPlayersInfo.away.currentSeasonStatsOnOpponents.gameCount` | int | `0` |
| `textOptions.currentPlayersInfo.away.currentSeasonStatsOnOpponents.hit` | int | `0` |
| `textOptions.currentPlayersInfo.away.currentSeasonStatsOnOpponents.hr` | int | `0` |
| `textOptions.currentPlayersInfo.away.currentSeasonStatsOnOpponents.hra` | float | `0.0` |
| `textOptions.currentPlayersInfo.away.currentSeasonStatsOnOpponents.inn` | NoneType, str | `0` |
| `textOptions.currentPlayersInfo.away.currentSeasonStatsOnOpponents.inn2` | NoneType | `None` |
| `textOptions.currentPlayersInfo.away.currentSeasonStatsOnOpponents.kk` | int | `0` |
| `textOptions.currentPlayersInfo.away.currentSeasonStatsOnOpponents.l` | int | `0` |
| `textOptions.currentPlayersInfo.away.currentSeasonStatsOnOpponents.obp` | float | `0.0` |
| `textOptions.currentPlayersInfo.away.currentSeasonStatsOnOpponents.rbi` | int | `0` |
| `textOptions.currentPlayersInfo.away.currentSeasonStatsOnOpponents.s` | int | `0` |
| `textOptions.currentPlayersInfo.away.currentSeasonStatsOnOpponents.w` | int | `0` |
| `textOptions.currentPlayersInfo.away.currentSeasonStatsOnOpponents.whip` | float | `0.0` |
| `textOptions.currentPlayersInfo.away.monthlyStats` | dict | `17개` |
| `textOptions.currentPlayersInfo.away.monthlyStats.ab` | int | `0` |
| `textOptions.currentPlayersInfo.away.monthlyStats.bb` | int | `0` |
| `textOptions.currentPlayersInfo.away.monthlyStats.er` | int | `0` |
| `textOptions.currentPlayersInfo.away.monthlyStats.era` | float | `0.0` |
| `textOptions.currentPlayersInfo.away.monthlyStats.gameCount` | int | `0` |
| `textOptions.currentPlayersInfo.away.monthlyStats.hit` | int | `0` |
| `textOptions.currentPlayersInfo.away.monthlyStats.hr` | int | `0` |
| `textOptions.currentPlayersInfo.away.monthlyStats.hra` | float | `0.0` |
| `textOptions.currentPlayersInfo.away.monthlyStats.inn` | NoneType, str | `0.1` |
| `textOptions.currentPlayersInfo.away.monthlyStats.inn2` | NoneType | `None` |
| `textOptions.currentPlayersInfo.away.monthlyStats.kk` | int | `0` |
| `textOptions.currentPlayersInfo.away.monthlyStats.l` | int | `0` |
| `textOptions.currentPlayersInfo.away.monthlyStats.obp` | float | `0.0` |
| `textOptions.currentPlayersInfo.away.monthlyStats.rbi` | int | `0` |
| `textOptions.currentPlayersInfo.away.monthlyStats.s` | int | `0` |
| `textOptions.currentPlayersInfo.away.monthlyStats.w` | int | `0` |
| `textOptions.currentPlayersInfo.away.monthlyStats.whip` | float | `0.0` |
| `textOptions.currentPlayersInfo.away.playerType` | str | `batter` |
| `textOptions.currentPlayersInfo.away.totalSeasonStats` | dict | `17개` |
| `textOptions.currentPlayersInfo.away.totalSeasonStats.ab` | int | `0` |
| `textOptions.currentPlayersInfo.away.totalSeasonStats.bb` | int | `0` |
| `textOptions.currentPlayersInfo.away.totalSeasonStats.er` | int | `0` |
| `textOptions.currentPlayersInfo.away.totalSeasonStats.era` | float | `0.0` |
| `textOptions.currentPlayersInfo.away.totalSeasonStats.gameCount` | int | `101` |
| `textOptions.currentPlayersInfo.away.totalSeasonStats.hit` | int | `0` |
| `textOptions.currentPlayersInfo.away.totalSeasonStats.hr` | int | `0` |
| `textOptions.currentPlayersInfo.away.totalSeasonStats.hra` | float | `0.0` |
| `textOptions.currentPlayersInfo.away.totalSeasonStats.inn` | NoneType, str | `11` |
| `textOptions.currentPlayersInfo.away.totalSeasonStats.inn2` | NoneType | `None` |
| `textOptions.currentPlayersInfo.away.totalSeasonStats.kk` | int | `0` |
| `textOptions.currentPlayersInfo.away.totalSeasonStats.l` | int | `0` |
| `textOptions.currentPlayersInfo.away.totalSeasonStats.obp` | float | `0.0` |
| `textOptions.currentPlayersInfo.away.totalSeasonStats.rbi` | int | `0` |
| `textOptions.currentPlayersInfo.away.totalSeasonStats.s` | int | `0` |
| `textOptions.currentPlayersInfo.away.totalSeasonStats.w` | int | `0` |
| `textOptions.currentPlayersInfo.away.totalSeasonStats.whip` | float | `0.0` |
| `textOptions.currentPlayersInfo.home` | dict | `6개` |
| `textOptions.currentPlayersInfo.home.currentGamePlayerStats` | dict | `17개` |
| `textOptions.currentPlayersInfo.home.currentGamePlayerStats.ab` | int | `0` |
| `textOptions.currentPlayersInfo.home.currentGamePlayerStats.ballCount` | int | `0` |
| `textOptions.currentPlayersInfo.home.currentGamePlayerStats.batOrder` | int | `0` |
| `textOptions.currentPlayersInfo.home.currentGamePlayerStats.batResult` | NoneType, str | `` |
| `textOptions.currentPlayersInfo.home.currentGamePlayerStats.bb` | int | `0` |
| `textOptions.currentPlayersInfo.home.currentGamePlayerStats.bhome` | int | `1` |
| `textOptions.currentPlayersInfo.home.currentGamePlayerStats.era` | float | `0.0` |
| `textOptions.currentPlayersInfo.home.currentGamePlayerStats.hit` | int | `0` |
| `textOptions.currentPlayersInfo.home.currentGamePlayerStats.hr` | int | `0` |
| `textOptions.currentPlayersInfo.home.currentGamePlayerStats.inn` | NoneType, str | `0.1` |
| `textOptions.currentPlayersInfo.home.currentGamePlayerStats.kk` | int | `0` |
| `textOptions.currentPlayersInfo.home.currentGamePlayerStats.pa` | int | `0` |
| `textOptions.currentPlayersInfo.home.currentGamePlayerStats.rbi` | int | `0` |
| `textOptions.currentPlayersInfo.home.currentGamePlayerStats.run` | int | `0` |
| `textOptions.currentPlayersInfo.home.currentGamePlayerStats.seasonEra` | float | `0.0` |
| `textOptions.currentPlayersInfo.home.currentGamePlayerStats.so` | int | `0` |
| `textOptions.currentPlayersInfo.home.currentGamePlayerStats.strikeCount` | int | `0` |
| `textOptions.currentPlayersInfo.home.currentSeasonStats` | dict | `17개` |
| `textOptions.currentPlayersInfo.home.currentSeasonStats.ab` | int | `0` |
| `textOptions.currentPlayersInfo.home.currentSeasonStats.bb` | int | `0` |
| `textOptions.currentPlayersInfo.home.currentSeasonStats.er` | int | `0` |
| `textOptions.currentPlayersInfo.home.currentSeasonStats.era` | float | `0.0` |
| `textOptions.currentPlayersInfo.home.currentSeasonStats.gameCount` | int | `0` |
| `textOptions.currentPlayersInfo.home.currentSeasonStats.hit` | int | `0` |
| `textOptions.currentPlayersInfo.home.currentSeasonStats.hr` | int | `0` |
| `textOptions.currentPlayersInfo.home.currentSeasonStats.hra` | float | `0.0` |
| `textOptions.currentPlayersInfo.home.currentSeasonStats.inn` | NoneType, str | `108.0` |
| `textOptions.currentPlayersInfo.home.currentSeasonStats.inn2` | NoneType, str | `108 ` |
| `textOptions.currentPlayersInfo.home.currentSeasonStats.kk` | int | `0` |
| `textOptions.currentPlayersInfo.home.currentSeasonStats.l` | int | `0` |
| `textOptions.currentPlayersInfo.home.currentSeasonStats.obp` | float | `0.0` |
| `textOptions.currentPlayersInfo.home.currentSeasonStats.rbi` | int | `0` |
| `textOptions.currentPlayersInfo.home.currentSeasonStats.s` | int | `0` |
| `textOptions.currentPlayersInfo.home.currentSeasonStats.w` | int | `0` |
| `textOptions.currentPlayersInfo.home.currentSeasonStats.whip` | float | `0.0` |
| `textOptions.currentPlayersInfo.home.currentSeasonStatsOnOpponents` | dict | `17개` |
| `textOptions.currentPlayersInfo.home.currentSeasonStatsOnOpponents.ab` | int | `0` |
| `textOptions.currentPlayersInfo.home.currentSeasonStatsOnOpponents.bb` | int | `0` |
| `textOptions.currentPlayersInfo.home.currentSeasonStatsOnOpponents.er` | int | `0` |
| `textOptions.currentPlayersInfo.home.currentSeasonStatsOnOpponents.era` | float | `0.0` |
| `textOptions.currentPlayersInfo.home.currentSeasonStatsOnOpponents.gameCount` | int | `0` |
| `textOptions.currentPlayersInfo.home.currentSeasonStatsOnOpponents.hit` | int | `0` |
| `textOptions.currentPlayersInfo.home.currentSeasonStatsOnOpponents.hr` | int | `0` |
| `textOptions.currentPlayersInfo.home.currentSeasonStatsOnOpponents.hra` | float | `0.0` |
| `textOptions.currentPlayersInfo.home.currentSeasonStatsOnOpponents.inn` | NoneType, str | `0` |
| `textOptions.currentPlayersInfo.home.currentSeasonStatsOnOpponents.inn2` | NoneType | `None` |
| `textOptions.currentPlayersInfo.home.currentSeasonStatsOnOpponents.kk` | int | `0` |
| `textOptions.currentPlayersInfo.home.currentSeasonStatsOnOpponents.l` | int | `0` |
| `textOptions.currentPlayersInfo.home.currentSeasonStatsOnOpponents.obp` | float | `0.0` |
| `textOptions.currentPlayersInfo.home.currentSeasonStatsOnOpponents.rbi` | int | `0` |
| `textOptions.currentPlayersInfo.home.currentSeasonStatsOnOpponents.s` | int | `0` |
| `textOptions.currentPlayersInfo.home.currentSeasonStatsOnOpponents.w` | int | `0` |
| `textOptions.currentPlayersInfo.home.currentSeasonStatsOnOpponents.whip` | float | `0.0` |
| `textOptions.currentPlayersInfo.home.monthlyStats` | dict | `17개` |
| `textOptions.currentPlayersInfo.home.monthlyStats.ab` | int | `0` |
| `textOptions.currentPlayersInfo.home.monthlyStats.bb` | int | `0` |
| `textOptions.currentPlayersInfo.home.monthlyStats.er` | int | `0` |
| `textOptions.currentPlayersInfo.home.monthlyStats.era` | float | `0.0` |
| `textOptions.currentPlayersInfo.home.monthlyStats.gameCount` | int | `0` |
| `textOptions.currentPlayersInfo.home.monthlyStats.hit` | int | `0` |
| `textOptions.currentPlayersInfo.home.monthlyStats.hr` | int | `0` |
| `textOptions.currentPlayersInfo.home.monthlyStats.hra` | float | `0.0` |
| `textOptions.currentPlayersInfo.home.monthlyStats.inn` | NoneType, str | `0.2` |
| `textOptions.currentPlayersInfo.home.monthlyStats.inn2` | NoneType | `None` |
| `textOptions.currentPlayersInfo.home.monthlyStats.kk` | int | `0` |
| `textOptions.currentPlayersInfo.home.monthlyStats.l` | int | `0` |
| `textOptions.currentPlayersInfo.home.monthlyStats.obp` | float | `0.0` |
| `textOptions.currentPlayersInfo.home.monthlyStats.rbi` | int | `0` |
| `textOptions.currentPlayersInfo.home.monthlyStats.s` | int | `0` |
| `textOptions.currentPlayersInfo.home.monthlyStats.w` | int | `0` |
| `textOptions.currentPlayersInfo.home.monthlyStats.whip` | float | `0.0` |
| `textOptions.currentPlayersInfo.home.playerType` | str | `batter` |
| `textOptions.currentPlayersInfo.home.totalSeasonStats` | dict | `17개` |
| `textOptions.currentPlayersInfo.home.totalSeasonStats.ab` | int | `0` |
| `textOptions.currentPlayersInfo.home.totalSeasonStats.bb` | int | `0` |
| `textOptions.currentPlayersInfo.home.totalSeasonStats.er` | int | `0` |
| `textOptions.currentPlayersInfo.home.totalSeasonStats.era` | float | `0.0` |
| `textOptions.currentPlayersInfo.home.totalSeasonStats.gameCount` | int | `106` |
| `textOptions.currentPlayersInfo.home.totalSeasonStats.hit` | int | `0` |
| `textOptions.currentPlayersInfo.home.totalSeasonStats.hr` | int | `0` |
| `textOptions.currentPlayersInfo.home.totalSeasonStats.hra` | float | `0.0` |
| `textOptions.currentPlayersInfo.home.totalSeasonStats.inn` | NoneType, str | `328.1` |
| `textOptions.currentPlayersInfo.home.totalSeasonStats.inn2` | NoneType | `None` |
| `textOptions.currentPlayersInfo.home.totalSeasonStats.kk` | int | `0` |
| `textOptions.currentPlayersInfo.home.totalSeasonStats.l` | int | `0` |
| `textOptions.currentPlayersInfo.home.totalSeasonStats.obp` | float | `0.0` |
| `textOptions.currentPlayersInfo.home.totalSeasonStats.rbi` | int | `0` |
| `textOptions.currentPlayersInfo.home.totalSeasonStats.s` | int | `0` |
| `textOptions.currentPlayersInfo.home.totalSeasonStats.w` | int | `0` |
| `textOptions.currentPlayersInfo.home.totalSeasonStats.whip` | float | `0.0` |
| `textOptions.pitchNum` | int | `1` |
| `textOptions.pitchResult` | str | `B` |
| `textOptions.ptsPitchId` | str | `-1` |
| `textOptions.seqno` | int | `10` |
| `textOptions.speed` | str | `0` |
| `textOptions.stuff` | str | `` |
| `textOptions.text` | str | `[중계 문장 저장 안 함]` |
| `textOptions.type` | int | `1` |
