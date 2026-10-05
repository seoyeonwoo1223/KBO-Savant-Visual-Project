# 0002. 시즌별 partition 레이아웃 공존, 2022–2024 game shard 유지

- **상태**: 채택 (세부 계약: [../curated-data.md](../curated-data.md))

## 맥락
경기 단위 Parquet(game shard)은 파일 수가 시즌마다 2천 개가 넘어 탐색·hash 계산이 느립니다. 월별 partition으로 합치면(compact) 빨라지지만, 마이그레이션은 시즌 단위 일회성입니다. 2022–2024는 raw JSON이 없어 curated가 유일한 사본입니다.

## 결정
- 2025·2026은 month 레이아웃, 2022–2024는 game shard로 둡니다.
- 레이아웃 판정은 `curated._season_is_compact()`(디스크에 `month=*.parquet`이 있는지) 하나만 씁니다.
- 삭제 전 검증은 전체 read-back + digest 대조. 손상·누락 partition은 fail-closed.

## 기각한 대안
- 2022–2024도 compact: 실패하면 복구 경로가 git 이력뿐입니다. 이력 재작성(`filter-repo`) 계획이 있으면 그 전에 compact하지 않습니다.
- `index["layout"]`으로 시즌 판정: 저장소 전역 키라 시즌별 판정에 틀립니다.
- `pq.ParquetFile()` open 성공을 무결성 증거로 사용: footer만 읽어 데이터 페이지 손상을 놓칩니다.

## 결과
- 2022–2024 curated를 지우거나 다시 쓰는 작업은 하지 않습니다([AGENTS.md](../../AGENTS.md)).
