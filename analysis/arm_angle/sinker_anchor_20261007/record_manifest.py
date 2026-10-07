"""이번 연구 폴더의 SHA 목록을 생성하거나 읽기 검증한다."""
import argparse
import hashlib
import json
from pathlib import Path

OUT=Path(__file__).resolve().parent
FILE=OUT/"RESULTS-MANIFEST.json"


def current():
    result={}
    for p in sorted(OUT.rglob("*")):
        if not p.is_file() or p==FILE or "__pycache__" in p.parts or ".pytest_cache" in p.parts:continue
        result[str(p.relative_to(OUT))]={"sha256":hashlib.sha256(p.read_bytes()).hexdigest(),"bytes":p.stat().st_size}
    return result


def main():
    parser=argparse.ArgumentParser();parser.add_argument("--verify",action="store_true");args=parser.parse_args()
    files=current()
    if args.verify:
        assert files==json.loads(FILE.read_text())["files"]
        print("SHA_VERIFIED",len(files))
    else:
        FILE.write_text(json.dumps({"scope":"EAA-SI1/EAA-SUP1 고정 재사용 진단","production_changed":False,
            "new_confirmation":False,"candidate_selected":False,"KBO_accuracy_verified":False,"files":files},ensure_ascii=False,indent=2)+"\n")
        print("SHA_RECORDED",len(files))


if __name__=="__main__":main()
