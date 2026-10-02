"""Resume official, identity-checked pitcher heights for selected VB seasons."""
import argparse
import json
from pathlib import Path

import pandas as pd

from visualbaseball.curated import load_table
from visualbaseball.trackman_arm_angle import collect_heights


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path.cwd())
    parser.add_argument('--seasons', type=int, nargs='+', default=[2025, 2026])
    parser.add_argument('--log', type=Path, default=Path('.cache/arm_angle/vb_height_collection.json'))
    args = parser.parse_args()
    bio = pd.read_parquet(args.root / 'data/curated/players/player_bio.parquet')
    frames = [load_table(args.root, 'pitches', y, columns=['pitcher_id']).to_pandas() for y in args.seasons]
    ids = pd.concat(frames, ignore_index=True).pitcher_id.drop_duplicates()
    players = bio.loc[bio.player_id.isin(ids), ['player_id', 'player_name']]
    events = collect_heights(players, args.root / 'data/tracking/player_heights.csv', bio,
                             args.root / '.cache/arm_angle/source_cache/kbo')
    args.log.parent.mkdir(parents=True, exist_ok=True)
    args.log.write_text(json.dumps(events, ensure_ascii=False, indent=2)+'\n')
    print(pd.Series([e['status'] for e in events], dtype=str).value_counts().to_dict())


if __name__ == '__main__':
    main()
