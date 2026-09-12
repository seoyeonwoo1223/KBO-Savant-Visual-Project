"""Report stale production metric state without failing CI."""
import json
from pathlib import Path

from visualbaseball.metric_state import SPECS, _path, metric_input_hash


root = Path(".")
season = 2026
for name in SPECS:
    path = _path(root, season, name)
    if not path.is_file():
        print(f"no state: {name} {season}")
        continue
    try:
        stored = json.loads(path.read_text(encoding="utf-8")).get("input_sha256")
        if stored != metric_input_hash(root, season, name):
            print(f"stale: {name} {season}")
    except (OSError, json.JSONDecodeError) as error:
        print(f"unreadable state: {name} {season}: {error}")
