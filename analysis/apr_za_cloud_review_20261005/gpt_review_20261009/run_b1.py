"""사전등록한 예측 고정 공분산 SE의 합성 포함률·선수별 경기 bootstrap을 검증한다."""
from pathlib import Path
import hashlib, io, json, subprocess, platform, importlib.metadata, itertools
import numpy as np
import pandas as pd
import pyarrow.parquet as pq
from scipy.stats import t, norm, spearmanr
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
DESIGN=json.loads((HERE/'b1_design.json').read_text())

def sizes(n,unequal):
    g=n//10
    if not unequal:return np.full(g,10,dtype=int)
    w=np.resize(np.array([1,2,3]),g);v=np.floor(n*w/w.sum()).astype(int);v[:n-v.sum()]+=1;return v

def estimate(r,d,counts):
    rc=r-r.mean(axis=-1,keepdims=True);dc=d-d.mean(axis=-1,keepdims=True)
    cov=(rc*dc).mean(axis=-1);psi=200*(rc*dc-cov[...,None])
    starts=np.r_[0,np.cumsum(counts)[:-1]];u=np.add.reduceat(psi,starts,axis=-1)
    g=len(counts);se=np.sqrt(g/(g-1)*np.sum(u*u,axis=-1))/r.shape[-1]
    return 200*cov,se

def bootstrap_stats(a,k):
    # 열: 경기 n, sum(r), sum(d), sum(rd). 복제 경기는 U²에 빈도만 곱한다.
    nn=k@a[:,0];m=(k@a[:,1])/nn;mu=(k@a[:,2])/nn;cov=(k@a[:,3])/nn-m*mu
    u=200*(a[None,:,3]-m[:,None]*a[None,:,2]-mu[:,None]*a[None,:,1]+(m*mu-cov)[:,None]*a[None,:,0])
    g=k.sum(axis=1);se=np.sqrt(g/(g-1)*np.sum(k*u*u,axis=1))/nn
    return 200*cov,se

def wilson(p,n):
    z=norm.ppf(.975);den=1+z*z/n;centre=(p+z*z/(2*n))/den;half=z*np.sqrt(p*(1-p)/n+z*z/(4*n*n))/den
    return [float(centre-half),float(centre+half)]

def synthetic():
    rows=[];grid=DESIGN['grid'];reps=DESIGN['replications_per_cell']
    cells=itertools.product(grid['families'],grid['n'],grid['icc'],grid['association'],grid['cluster_sizes'])
    for j,(fam,n,h,c,shape) in enumerate(cells):
        rng=np.random.default_rng(np.random.SeedSequence([DESIGN['seed'],j]));cnt=sizes(n,shape=='unequal');g=len(cnt);gi=np.repeat(np.arange(g),cnt)
        z1=rng.standard_normal((reps,g));z2=rng.standard_normal((reps,g));e1=rng.standard_normal((reps,n));e2=rng.standard_normal((reps,n))
        if fam=='gaussian':
            r=.1+np.sqrt(h)*z1[:,gi]+np.sqrt(1-h)*e1
            d=.2+np.sqrt(h)*(c*z1[:,gi]+np.sqrt(1-c*c)*z2[:,gi])+np.sqrt(1-h)*(c*e1+np.sqrt(1-c*c)*e2)
            truth=200*c;ref_sd=60.
        else:
            common=rng.choice([-1.,1.],size=(reps,g));individual=rng.choice([-1.,1.],size=(reps,n))
            x=np.where(rng.random((reps,n))<np.sqrt(h),common[:,gi],individual)
            r=.5*x;d=.2+c*x+np.sqrt(1-c*c)*(np.sqrt(h)*z2[:,gi]+np.sqrt(1-h)*e2);truth=100*c;ref_sd=30.
        b,se=estimate(r,d,cnt);p=float(np.mean(np.abs(b-truth)<=DESIGN['critical_value']*se));bias=float(b.mean()-truth)
        rows.append({'cell':j,'family':fam,'n':n,'G':g,'icc':h,'association':c,'size_design':shape,'min_game_n':int(cnt.min()),'max_game_n':int(cnt.max()),'true_B':truth,'mean_B':float(b.mean()),'bias':bias,'true_player_sd':ref_sd,'coverage':p,'coverage_mcse':float(np.sqrt(p*(1-p)/reps)),'coverage_wilson_low':wilson(p,reps)[0],'coverage_wilson_high':wilson(p,reps)[1],'coverage_t_diagnostic':float(np.mean(np.abs(b-truth)<=t.ppf(.975,g-1)*se)),'primary':g>=20,'coverage_pass':.92<=p<=.98 if g>=20 else None,'bias_pass':abs(bias)<=.05*ref_sd if n>=300 else None})
        if (j+1)%18==0:print('모의실험 완료 셀',j+1,flush=True)
    pd.DataFrame(rows).to_csv(HERE/'b1_simulation.csv',index=False)
    primary=[r for r in rows if r['primary']];fails=[r['cell'] for r in primary if not r['coverage_pass']]
    return {'cells':len(rows),'replications_per_cell':reps,'primary_cells':len(primary),'coverage_failed_cells':fails,'coverage_range':[min(r['coverage'] for r in primary),max(r['coverage'] for r in primary)],'bias_failed_cells':[r['cell'] for r in rows if r['bias_pass'] is False],'RB1_primary_pass':not fails}

def index_independent(rows,se_key,level,league):
    n=np.array([r['n'] for r in rows],float);q=n>=300;b=np.round([r['B'] for r in rows],6);se=np.round([r[se_key] for r in rows],6)
    sigma=np.median(se[q]**2*n[q]);tau=np.var(b[q]-league,ddof=1)-np.mean(se[q]**2);k=sigma/tau if tau>0 else np.inf
    adj=n/(n+k)*(b-league);adj-=np.average(adj,weights=n)
    return k,100*(level+adj)/level

def empirical():
    blob=subprocess.check_output(['git','show',DESIGN['source_commit']+':'+DESIGN['pitch_path']],cwd=ROOT)
    assert hashlib.sha256(blob).hexdigest()==DESIGN['pitch_sha256']
    df=pq.ParquetFile(io.BytesIO(blob)).read(columns=['batter_id','game_id','swing','p_swing','delta_v','dv']).to_pandas()
    assert len(df)==211140
    assert np.isfinite(df[['swing','p_swing','delta_v','dv']].to_numpy()).all()
    rows=[]
    for j,(pid,f) in enumerate(df.groupby('batter_id',sort=True)):
        r=(f.swing-f.p_swing).to_numpy();d=f.delta_v.to_numpy();n=len(r);games=np.unique(f.game_id);g=len(games)
        agg=pd.DataFrame({'game':f.game_id.to_numpy(),'n':np.ones(n),'r':r,'d':d,'rd':r*d}).groupby('game',sort=True)[['n','r','d','rd']].sum().to_numpy()
        cov=np.mean((r-r.mean())*(d-d.mean()));b=200*cov
        psi=200*((r-r.mean())*(d-d.mean())-cov);naive=200*((r-r.mean())*d-cov)
        by=pd.DataFrame({'game':f.game_id.to_numpy(),'psi':psi,'naive':naive}).groupby('game')[['psi','naive']].sum()
        raw_if=np.sqrt(np.sum(by.psi.to_numpy()**2))/n;cur=np.sqrt(np.sum(by.naive.to_numpy()**2))/n
        se_if=raw_if*np.sqrt(g/(g-1)) if g>1 else np.nan
        row={'batter_id':str(pid),'n':n,'G':g,'B':float(b),'SA':float(100*r.mean()),'se_current':float(cur),'se_if_uncorrected':float(raw_if),'se_if_corrected':float(se_if),'qualified':n>=300 and g>=20,'bootstrap_se':None,'ratio_if_over_bootstrap':None,'bootstrap_t_finite_share':None,'percentile_low':None,'percentile_high':None,'studentized_low':None,'studentized_high':None}
        if n>=300 and g>=20:
            rng=np.random.default_rng(np.random.SeedSequence([DESIGN['seed'],999,j]));k=rng.multinomial(g,np.full(g,1/g),size=DESIGN['bootstrap_per_player'])
            bb,ss=bootstrap_stats(agg,k);boot=float(bb.std(ddof=1));row['bootstrap_se']=boot;row['ratio_if_over_bootstrap']=float(se_if/boot) if boot>0 else None
            lo,hi=np.quantile(bb,[.025,.975]);row['percentile_low']=float(lo);row['percentile_high']=float(hi)
            ok=np.isfinite(ss)&(ss>0);share=float(ok.mean());row['bootstrap_t_finite_share']=share
            if share>=.95:
                tl,th=np.quantile((bb[ok]-b)/ss[ok],[.025,.975]);row['studentized_low']=float(b-th*se_if);row['studentized_high']=float(b-tl*se_if)
        rows.append(row)
    pd.DataFrame(rows).to_csv(HERE/'b1_players_2026.csv',index=False)
    ratios=np.array([r['ratio_if_over_bootstrap'] for r in rows if r['qualified'] and r['ratio_if_over_bootstrap'] is not None]);q=np.array([r['n']>=300 for r in rows]);v=np.quantile(ratios,[.05,.5,.95])
    level=100*float(df.dv.mean());league=np.average(np.round([r['B'] for r in rows],6),weights=[r['n'] for r in rows]);kcur,acur=index_independent(rows,'se_current',level,league);kif,aif=index_independent(rows,'se_if_uncorrected',level,league);kifg,aifg=index_independent(rows,'se_if_corrected',level,league)
    assert abs(kcur-723.540432)<1e-3
    low=np.array([100<=r['n']<300 for r in rows]);raw_ratio=np.array([r['se_current']/r['se_if_uncorrected'] for r in rows if r['n']>=300])
    return {'input_sha256':hashlib.sha256(blob).hexdigest(),'pitches':len(df),'players':len(rows),'qualified_300':int(q.sum()),'qualified_300_G20':sum(r['qualified'] for r in rows),'paired_bootstrap_players':len(ratios),'IF_over_bootstrap_p05_median_p95':v.tolist(),'RB3_pass':bool(.90<=v[1]<=1.10 and v[0]>=.75 and v[2]<=1.25),'current_over_uncorrected_IF_median':float(np.median(raw_ratio)),'k_current':float(kcur),'k_IF_uncorrected':float(kif),'k_IF_corrected':float(kifg),'APR_sd_current_IF_uncorrected':[float(acur[q].std(ddof=1)),float(aif[q].std(ddof=1))],'APR_rank_spearman_current_IF_uncorrected':float(spearmanr(acur[q],aif[q]).statistic),'APR_max_abs_change_uncorrected':float(np.max(np.abs(acur[q]-aif[q]))),'players_100_299':int(low.sum()),'APR_mean_100_299_current_IF':[float(acur[low].mean()),float(aif[low].mean())],'limitations':'선수별 예측 고정 bootstrap. 시즌 공동 지수 bootstrap·전시즌·전체 모형 재적합 미실행.'}

def main():
    subprocess.run(['git','diff','--exit-code','--','analysis/sbj_formula/gates.md'],cwd=ROOT,check=True,stdout=subprocess.DEVNULL)
    registration=subprocess.check_output(['git','log','-1','--format=%H','--','analysis/sbj_formula/gates.md'],cwd=ROOT,text=True).strip()
    out={'registration_commit':registration,'source_commit':DESIGN['source_commit'],'seed':DESIGN['seed'],'python':platform.python_version(),'versions':{x:importlib.metadata.version(x) for x in ['numpy','pandas','pyarrow','scipy']},'synthetic':synthetic(),'empirical':empirical(),'overall':'조건부 범위 검증이며 B1 전체 통과·운영 채택 판정 아님'}
    out['files_sha256']={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in [HERE/'b1_design.json',HERE/'run_b1.py',ROOT/'analysis/sbj_formula/gates.md',HERE/'b1_simulation.csv',HERE/'b1_players_2026.csv']}
    (HERE/'b1_results.json').write_text(json.dumps(out,ensure_ascii=False,indent=2,allow_nan=False)+'\n');print(json.dumps(out,ensure_ascii=False,indent=2))
if __name__=='__main__':main()
