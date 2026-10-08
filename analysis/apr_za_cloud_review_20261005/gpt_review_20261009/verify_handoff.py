"""0009의 고정 입력 결측과 정확성 대수만 독립 확인한다. 모형을 적합하지 않는다."""
from pathlib import Path
import subprocess, io, hashlib, json
import numpy as np
import pyarrow.parquet as pq
ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent
BASE = 'e48da3a26a617db67fbb51f6b1cbcb072b729eaf'

def main():
    path = 'data/curated/players/player_bio.parquet'
    blob = subprocess.check_output(['git', 'show', f'{BASE}:{path}'], cwd=ROOT)
    tab = pq.read_table(io.BytesIO(blob), columns=['height_cm','weight_kg','birth_date','source_name'])
    q = np.array([.1,.3,.7,.9]); s = np.array([0.,1.,0.,1.]); p = np.array([.2,.4,.6,.8])
    a = s*q+(1-s)*(1-q); expected = p*q+(1-p)*(1-q)
    errors = {'accuracy_residual_identity': float(np.max(np.abs(a-expected-(s-p)*(2*q-1)))),
              'accuracy_decomposition': float(abs(a.mean()-((1-q.mean())+s.mean()*(2*q.mean()-1)+np.mean((s-s.mean())*((2*q-1)-(2*q-1).mean())))))}
    # 동일 q 구간 안에서도 q 구성 차이가 남는 반례. 둘 다 q<0.1이고 전부 Take다.
    within_bin = {'same_bin_all_take_q_001_accuracy': .99, 'same_bin_all_take_q_009_accuracy': .91}
    out = {'base':BASE,'bio_path':path,'bio_sha256':hashlib.sha256(blob).hexdigest(),'bio_rows':tab.num_rows,
           'non_null':{c:tab.num_rows-tab[c].null_count for c in ['height_cm','weight_kg','birth_date']},
           'source_names':sorted(set(tab['source_name'].to_pylist())), 'algebra_max_abs_errors':errors,
           'A1_within_bin_counterexample':within_bin,
           'scope':'player_bio 결측만 독립 확인. 전체 시즌 존 감사·63~91% 포함률은 재실행하지 않음. 대수 검산은 성능 증거 아님.'}
    assert max(errors.values())<1e-12
    (HERE/'handoff_checks.json').write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(out,ensure_ascii=False,indent=2))
if __name__=='__main__':main()
