"""등록 구현 검산과 결과 manifest를 독립 집계한다."""
from pathlib import Path
import json, hashlib, subprocess
import numpy as np
import pandas as pd
from run_b1 import estimate, bootstrap_stats
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]

def main():
    results=json.loads((HERE/'b1_results.json').read_text());sim=pd.read_csv(HERE/'b1_simulation.csv');players=pd.read_csv(HERE/'b1_players_2026.csv')
    assert len(sim)==108 and len(players)==290
    for file,sha in results['files_sha256'].items():
        path=HERE/file if file!='gates.md' else ROOT/'analysis/sbj_formula/gates.md'
        assert hashlib.sha256(path.read_bytes()).hexdigest()==sha
    old=subprocess.check_output(['git','show',results['source_commit']+':analysis/sbj_formula/gates.md'],cwd=ROOT)
    assert (ROOT/'analysis/sbj_formula/gates.md').read_bytes().startswith(old)
    r=np.array([.3,-.2,.8,-.4]);d=np.array([.1,.5,-.3,.6]);cov=np.mean((r-r.mean())*(d-d.mean()));psi=200*((r-r.mean())*(d-d.mean())-cov)
    finite={};complex_errors=[]
    for eps in [1e-4,1e-5,1e-6]:
        vals=[]
        for i in range(4):
            w=np.ones(4);w[i]+=eps;w/=w.sum();b=200*(np.dot(w,r*d)-np.dot(w,r)*np.dot(w,d))
            vals.append(abs((b-200*cov)/eps*4-psi[i]))
        finite[str(eps)]=max(vals)
    for i in range(4):
        w=np.ones(4,complex);w[i]+=1e-20j;w/=w.sum();b=200*(np.dot(w,r*d)-np.dot(w,r)*np.dot(w,d));complex_errors.append(abs(b.imag/1e-20*4-psi[i]))
    assert max(complex_errors)<1e-10
    errors=[]
    for rr,dd in [(np.full(4,.5),d),(r,np.full(4,2.))]:
        a=np.array([[2,rr[:2].sum(),dd[:2].sum(),(rr[:2]*dd[:2]).sum()],[2,rr[2:].sum(),dd[2:].sum(),(rr[2:]*dd[2:]).sum()]])
        bb,ss=bootstrap_stats(a,np.array([[2,0],[1,1],[0,2]]));errors.extend([abs(estimate(rr,dd,np.array([2,2]))[0]),float(np.max(abs(bb))),float(np.var(bb)),float(np.max(abs(ss)))])
    assert max(errors)<1e-10
    q=players[players.qualified];small=sim[~sim.primary]
    out={'manifest_sha_pass':True,'historical_gates_prefix_preserved':True,'RB0_joint_complex_derivative_max_abs_error':float(max(complex_errors)),'RB0_finite_difference_max_errors':finite,'RB0_constant_negative_controls_max_abs_error':float(max(errors)),'simulation_primary_count':int(sim.primary.sum()),'small_G10_coverage_diagnostic_range':[float(small.coverage.min()),float(small.coverage.max())],'player_bootstrap_t_all_finite_share_range':[float(q.bootstrap_t_finite_share.min()),float(q.bootstrap_t_finite_share.max())],'interval_order_all_pass':bool((q.percentile_low<=q.percentile_high).all() and (q.studentized_low<=q.studentized_high).all()),'scope':'등록 구현/manifest/집계 검증. 실제 포함률·전체 재적합·전시즌 검증 아님'}
    (HERE/'b1_validation.json').write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n');print(json.dumps(out,ensure_ascii=False,indent=2))
if __name__=='__main__':main()
