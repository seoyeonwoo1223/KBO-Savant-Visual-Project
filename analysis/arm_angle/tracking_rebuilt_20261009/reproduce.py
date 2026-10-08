"""같은 선택 입력으로 run/verify 전체 산출물의 byte 결정성을 검증한다."""
import subprocess
import sys
from acquire import HERE, ROOT, sha, dump

def snapshot():
    paths = sorted((HERE/'results').glob('*'))+[HERE/'columns.json',HERE/'environment.json',
            ROOT/'.cache/arm_angle/tracking_rebuilt_20261009/derived_pitches.parquet']
    return {str(p.relative_to(ROOT)):sha(p) for p in paths if p.is_file()}

def main():
    before=snapshot()
    for name in ['run.py','verify.py']:
        subprocess.run([sys.executable,str(HERE/name)],check=True,cwd=ROOT)
    after=snapshot()
    assert before==after, {k:(before.get(k),after.get(k)) for k in before.keys()|after.keys() if before.get(k)!=after.get(k)}
    dump(HERE/'reproducibility.json',{'passed':True,'same_selected_input':True,
         'compared_artifacts':len(before),'byte_sha_identical':True,'artifact_sha256':before,
         'raw_source_reread_performed':False})
    print('동일 입력 byte 재실행 검증 통과',len(before),'개')

if __name__=='__main__':
    main()
