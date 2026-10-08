"""공개 연구 패키지 SHA를 기록/검증한다. 큰 캐시는 포함하지 않는다."""
import argparse
from acquire import HERE, sha, dump
import json

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--verify',action='store_true');args=parser.parse_args()
    files={str(p.relative_to(HERE)):{'sha256':sha(p),'bytes':p.stat().st_size}
           for p in sorted(HERE.rglob('*')) if p.is_file() and p.name!='MANIFEST.json'
           and '__pycache__' not in p.parts and '.pytest_cache' not in p.parts}
    if args.verify:
        assert files==json.loads((HERE/'MANIFEST.json').read_text())['files']
        print('연구 패키지 SHA 검증 통과',len(files),'개')
    else:
        dump(HERE/'MANIFEST.json',{'scope':'EAA-TR1 별도 재생성판','production_changed':False,
             'previous_implementation_identity_verified':False,'external_angle_accuracy_verified':False,'files':files})
        print('연구 패키지 SHA 기록',len(files),'개')

if __name__=='__main__':
    main()
