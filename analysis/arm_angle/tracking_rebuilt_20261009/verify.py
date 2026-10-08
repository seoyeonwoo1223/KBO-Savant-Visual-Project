"""독립 scalar root·수치 적분·canonical 기준면·fold를 검산한다."""
from pathlib import Path
import json
import numpy as np
import pandas as pd
from scipy.optimize import brentq
from scipy.integrate import solve_ivp
from acquire import HERE, ROOT, sha, dump
from features import FT, G, PLANES

def main():
    d=pd.read_parquet(HERE/'inputs/selected_2026.parquet')
    cache=ROOT/'.cache/arm_angle/tracking_rebuilt_20261009/derived_pitches.parquet'
    f=pd.read_parquet(cache)
    assert d.pitch_id.equals(f.pitch_id) and d.game_id.equals(f.game_id)
    good=np.flatnonzero(f.basic_valid)
    sample=good[np.linspace(0,len(good)-1,min(512,len(good)),dtype=int)]
    max_pos=max_vel=max_root=max_integral=0.
    for i in sample:
        row=d.iloc[i]; got=f.iloc[i]
        p=row[['x0','y0','z0']].to_numpy(float)*FT
        v=row[['vx0','vy0','vz0']].to_numpy(float)*FT
        a=row[['ax','ay','az']].to_numpy(float)*FT
        for label,y in PLANES.items():
            fn=lambda t:p[1]+v[1]*t+a[1]*t*t/2-y*FT
            t=brentq(fn,-.2,1.2,xtol=1e-14)
            max_root=max(max_root,abs(fn(got[f't{label}_s'])))
            for j,axis in enumerate('xyz'):
                expected=p[j]+v[j]*t+a[j]*t*t/2
                max_pos=max(max_pos,abs(expected-got[f'{axis}{label}_m']))
                max_vel=max(max_vel,abs(v[j]+a[j]*t-got[f'v{axis}{label}_mps']))
            if i in sample[:16]:
                sol=solve_ivp(lambda tt,q:np.r_[q[3:],a],(0.,t),np.r_[p,v],rtol=1e-11,atol=1e-12)
                assert sol.success
                max_integral=max(max_integral,float(abs(sol.y[:3,-1]-[got[f'{axis}{label}_m'] for axis in 'xyz']).max()))
    assert max_root<1e-8 and max_pos<1e-8 and max_vel<1e-8 and max_integral<1e-7
    canonical={}
    for plane in ['50','55']:
        for field,col,scale in [('release_x',f'x{plane}_m',.01),('release_z',f'z{plane}_m',.01),
                                ('vx',f'vx{plane}_mps',FT),('vy',f'vy{plane}_mps',FT),('vz',f'vz{plane}_mps',FT)]:
            old=pd.to_numeric(d[f'{field}_{plane}'],errors='coerce').to_numpy()*scale
            new=f[col].to_numpy(); finite=np.isfinite(old)&np.isfinite(new)
            delta=float(abs(old[finite]-new[finite]).max())
            canonical[f'{field}_{plane}']={'checked_pitches':int(finite.sum()),'max_difference_SI':delta}
            assert delta<1e-8
    assignments=pd.DataFrame({'player':d.pitcher_id,'fold':f.oof_fold})
    assignments=assignments.loc[assignments.fold.ge(0)]
    assert assignments.groupby('player').fold.nunique().eq(1).all()
    quality={}
    for col in ['px_mid_error_cm','pz_front_error_cm','hb_report_error_cm','ivb_report_error_cm']:
        x=f[col].dropna()
        quality[col]={'finite':len(x),'mean_cm':float(x.mean()),'abs_p99_cm':float(x.abs().quantile(.99)),
                      'max_abs_cm':float(x.abs().max()),'above_1cm':int(x.abs().gt(1.).sum())}
    assert sha(ROOT/'data/models/estimated_arm_angle_v3.json')=='484c6de37dc835f7551e69dbaa8550fe54bf6a086ec3483898140eee907ae84b'
    dump(HERE/'results/verification.json',{'passed':True,'independent_scalar_sample_pitches':len(sample),
        'independent_scalar_crossings':len(sample)*len(PLANES),'position_max_difference_m':max_pos,
        'velocity_max_difference_mps':max_vel,'plane_equation_max_residual_m':max_root,
        'scipy_integration_pitches':16,'integration_max_difference_m':max_integral,
        'canonical_plane_agreement':canonical,'report_consistency_distributions':quality,
        'oof_player_overlap':0,'production_model_sha_verified':True,'external_angle_accuracy_verified':False})
    print('독립 수치/단위/좌표 검산 통과',len(sample),'구',len(sample)*5,'면')

if __name__=='__main__':
    main()
