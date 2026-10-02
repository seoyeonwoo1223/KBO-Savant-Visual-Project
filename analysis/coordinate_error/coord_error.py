"""ABS coordinate-error diagnostics (tests 1-4)."""
import json, glob, numpy as np, pyarrow as pa, pyarrow.dataset as ds
from collections import Counter, defaultdict

PLATE_DEPTH=17/12; MID=PLATE_DEPTH/2
COLS=['px','pz','sz_top','sz_bottom','pitch_call_code','parse_status','x0','y0','z0',
      'vx0','vy0','vz0','ax','ay','az','pitch_type','velocity_kmh','vertical_movement_cm',
      'horizontal_movement_cm','stadium','batter_stance','batter_id','game_id','season']

def load(seasons):
    T=[ds.dataset(sorted(glob.glob(f'data/curated/pitches/season={s}/*.parquet')),format='parquet').to_table(columns=COLS) for s in seasons]
    return pa.concat_tables(T)

t=load([2026])
col=lambda k:t[k].to_pylist()
num=lambda k:np.asarray([np.nan if v is None else float(v) for v in col(k)])
g={k:num(k) for k in ('px','pz','sz_top','sz_bottom','x0','y0','z0','vx0','vy0','vz0','ax','ay','az','velocity_kmh','vertical_movement_cm','horizontal_movement_cm')}
call=np.array([str(c or '') for c in col('pitch_call_code')])
ps=np.array([str(c or '') for c in col('parse_status')])
ptype=np.array([str(c or '') for c in col('pitch_type')])
park=np.array([str(c or '') for c in col('stadium')])
stance=np.array([str(c or '') for c in col('batter_stance')])
take=np.isin(call,['B','T'])&(ps=='ok')
fin=np.all([np.isfinite(g[k]) for k in ('px','pz','sz_top','sz_bottom','x0','y0','z0','vx0','vy0','vz0','ax','ay','az')],axis=0)&(g['sz_top']>g['sz_bottom'])
m=take&fin
G={k:v[m] for k,v in g.items()}
st=(call[m]=='T'); PT=ptype[m]; PARK=park[m]; ST=stance[m]
print('takes:',m.sum())

def cross(y):
    a=.5*G['ay']; b=G['vy0']; c=G['y0']-y
    disc=np.maximum(b*b-4*a*c,0); r=np.sqrt(disc)
    t1=(-b-r)/(2*a); t2=(-b+r)/(2*a)
    tt=np.where(t1>0,t1,t2)
    return (G['x0']+G['vx0']*tt+.5*G['ax']*tt**2,
            G['z0']+G['vz0']*tt+.5*G['az']*tt**2,
            G['vz0']+G['az']*tt, G['vx0']+G['ax']*tt, G['vy0']+G['ay']*tt)
X,Z,VZ,VX,VY=cross(MID)
TOP,BOT=G['sz_top'],G['sz_bottom']
VAA=np.degrees(np.arctan2(VZ,np.sqrt(VX**2+VY**2)))

def inside(w,p,d,dx=0.0):
    return (np.abs(X-dx)<=w)&(Z<=TOP+p+d)&(Z>=BOT-p+d)
def agree(w,p,d,dx=0.0,mask=None):
    ins=inside(w,p,d,dx); k=slice(None) if mask is None else mask
    return float((ins[k]==st[k]).mean())

out={}
# --- TEST 1: reparameterise (p, delta) --------------------------------------
best=None
for w in np.arange(0.86,0.921,0.0025):
    for p in np.arange(0.06,0.161,0.0025):
        for d in np.arange(-0.04,0.0601,0.0025):
            a=agree(w,p,d)
            if best is None or a>best[0]: best=(a,w,p,d)
A,W,P,D=best
out['test1']={'agreement':round(A,5),'half_w_ft':round(W,4),'pad_p_ft':round(P,4),'offset_delta_ft':round(D,4),
              'pad_p_cm':round(P*30.48,3),'offset_delta_in':round(D*12,4),
              'implied_top':round(P+D,4),'implied_bottom':round(P-D,4),'ball_radius_cm':3.66}
print('TEST1',out['test1'],flush=True)

# --- TEST 2: free left/right edges ------------------------------------------
best2=None
for lo in np.arange(-0.95,-0.83,0.005):
    for hi in np.arange(0.83,0.951,0.005):
        ins=(X>=lo)&(X<=hi)&(Z<=TOP+P+D)&(Z>=BOT-P+D)
        a=float((ins==st).mean())
        if best2 is None or a>best2[0]: best2=(a,lo,hi)
A2,LO,HI=best2
out['test2']={'agreement':round(A2,5),'x_low_ft':round(LO,4),'x_high_ft':round(HI,4),
              'half_width_ft':round((HI-LO)/2,4),'x_offset_ft':round((HI+LO)/2,4),
              'x_offset_in':round((HI+LO)/2*12,4),'gain_over_symmetric':round(A2-A,5)}
print('TEST2',out['test2'],flush=True)

# --- measurement-error sd from the transition width (probit on the margin) ---
margin=np.minimum.reduce([W-np.abs(X-0.0), (TOP+P+D)-Z, Z-(BOT-P+D)])
from scipy.stats import norm
from scipy.optimize import minimize_scalar
def nll(sigma):
    pr=np.clip(norm.cdf(margin/sigma),1e-9,1-1e-9)
    return -np.sum(st*np.log(pr)+(1-st)*np.log(1-pr))
r=minimize_scalar(nll,bounds=(0.005,0.35),method='bounded')
SIGMA=float(r.x)
out['sigma']={'ft':round(SIGMA,5),'inch':round(SIGMA*12,4),'cm':round(SIGMA*30.48,3),
              'note':'sd of a probit fitted to the signed margin; mixes coordinate error with any real call noise'}
print('SIGMA',out['sigma'],flush=True)

# --- TEST 3: what is delta a function of? -----------------------------------
def fit_delta(mask,grid=np.arange(-0.10,0.1001,0.0025)):
    if mask.sum()<400: return None
    vals=[(agree(W,P,d,mask=mask),d) for d in grid]
    a,d=max(vals)
    return {'n':int(mask.sum()),'delta_ft':round(float(d),4),'delta_in':round(float(d)*12,3),'agreement':round(a,5)}
groups={}
groups['pitch_type']={k:fit_delta(PT==k) for k,n in Counter(PT).most_common(8) if n>=1500}
groups['park']={k:fit_delta(PARK==k) for k,n in Counter(PARK).most_common(12) if n>=1500}
groups['stance']={k:fit_delta(ST==k) for k,n in Counter(ST).most_common(3) if n>=1500}
def bins(v,name,edges):
    d={}
    for lo,hi in zip(edges,edges[1:]):
        d[f'{lo}~{hi}']=fit_delta(np.isfinite(v)&(v>=lo)&(v<hi))
    return d
groups['vertical_movement_cm']=bins(G['vertical_movement_cm'],'vmov',[-60,-20,0,20,40,60,90])
groups['vaa_deg']=bins(VAA,'vaa',[-12,-9,-7.5,-6,-4.5,-3,0])
groups['velocity_kmh']=bins(G['velocity_kmh'],'velo',[100,120,130,135,140,145,150,165])
height=TOP/0.5575
groups['batter_height_ft']=bins(height,'h',[5.0,5.7,5.85,6.0,6.15,7.0])
out['test3']={k:{kk:vv for kk,vv in v.items() if vv} for k,v in groups.items()}
for k,v in out['test3'].items():
    print('TEST3',k,{kk:(vv['delta_in'],vv['n']) for kk,vv in v.items()},flush=True)

# --- S->B : B->S ratio by pitch type ----------------------------------------
ins=inside(W,P,D)
ratio={}
for k,n in Counter(PT).most_common(10):
    if n<800: continue
    q=PT==k
    sb=int((ins[q]&~st[q]).sum()); bs=int((~ins[q]&st[q]).sum())
    ratio[k]={'n':int(n),'rule_strike_called_ball':sb,'rule_ball_called_strike':bs,
              'ratio':round(sb/bs,3) if bs else None,
              'mean_vertical_movement_cm':round(float(np.nanmean(G['vertical_movement_cm'][q])),2)}
out['sb_bs_ratio_by_pitch_type']=ratio
print('RATIO',json.dumps(ratio,ensure_ascii=False),flush=True)

# --- TEST 4: deep residuals at a measurement-scale threshold -----------------
deep={}
for thr in (0.1,0.125,2*SIGMA,3*SIGMA):
    unambiguous=np.abs(margin)>=thr
    wrong=(ins!=st)&unambiguous
    by_type=Counter(PT[wrong]); tot=Counter(PT[unambiguous])
    deep[round(float(thr),4)]={
        'threshold_in':round(float(thr)*12,3),
        'unambiguous_pitches':int(unambiguous.sum()),
        'residual_pitches':int(wrong.sum()),
        'residual_rate':round(float(wrong.sum()/max(1,unambiguous.sum())),5),
        'by_pitch_type':{k:{'residual':by_type[k],'pitches':tot[k],
                            'rate':round(by_type[k]/tot[k],5)} for k,_ in Counter(PT).most_common(6) if tot[k]},
        'mean_vertical_movement_cm_of_residuals':round(float(np.nanmean(G['vertical_movement_cm'][wrong])),2) if wrong.any() else None,
        'mean_vaa_of_residuals':round(float(np.nanmean(VAA[wrong])),3) if wrong.any() else None,
        'mean_vertical_movement_cm_overall':round(float(np.nanmean(G['vertical_movement_cm'])),2),
        'mean_vaa_overall':round(float(np.nanmean(VAA)),3),
    }
out['test4']=deep
for k,v in deep.items(): print('TEST4 thr=%.4f ft (%.2f in) residual=%d/%d = %.4f%%'%(k,v['threshold_in'],v['residual_pitches'],v['unambiguous_pitches'],100*v['residual_rate']),flush=True)
json.dump(out,open('/tmp/claude-0/-home-user-KBO-Savant-Visual-Project/70fe0bf4-a38d-57df-89e7-81f908ed9207/scratchpad/coord_error.json','w'),ensure_ascii=False,indent=1)
print('WROTE coord_error.json')
