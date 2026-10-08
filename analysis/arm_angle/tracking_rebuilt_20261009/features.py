"""등가속도 궤적의 기술적 변환. 광학/스핀/어깨 관측이 아니다."""
import numpy as np
import pandas as pd

FT = .3048
G = 9.80665
PLANES = {'55':55.,'50':50.,'238':23.8,'10':10.,'front':17/12}

def crossing(y, vy, ay, target):
    y, vy, ay = [np.asarray(a,float) for a in (y,vy,ay)]
    disc = vy*vy-2*ay*(y-target)
    with np.errstate(invalid='ignore',divide='ignore'):
        sq = np.sqrt(disc)
        # stable quadratic root; the other root follows the product relation
        q = -.5*(vy+np.copysign(sq,vy))
        r1 = q/(.5*ay)
        r2 = (y-target)/q
        t = np.where(abs(r1)<abs(r2),r1,r2)
        t = np.where(abs(ay)<1e-12,(target-y)/vy,t)
    return np.where(np.isfinite(t)&(vy+ay*t<0),t,np.nan)

def derive(d):
    p = d[['x0','y0','z0']].to_numpy(float)*FT
    v = d[['vx0','vy0','vz0']].to_numpy(float)*FT
    a = d[['ax','ay','az']].to_numpy(float)*FT
    hand = d.pitcher_hand.map({'Right':1.,'Left':-1.}).to_numpy(float)
    height = d.height_cm.to_numpy(float)/100
    height = np.where((height>=1.4)&(height<=2.2),height,np.nan)
    time = {k:crossing(p[:,1],v[:,1],a[:,1],y*FT) for k,y in PLANES.items()}
    pos = {k:p+v*time[k][:,None]+.5*a*time[k][:,None]**2 for k in PLANES}
    vel = {k:v+a*time[k][:,None] for k in PLANES}
    valid = np.isfinite(np.column_stack([p,v,a])).all(axis=1)&d.y0.isin([50.,55.]).to_numpy()
    valid &= d.trajectory_valid.fillna(False).to_numpy(bool)
    valid &= np.isfinite(np.column_stack(list(time.values()))).all(axis=1)
    valid &= (np.diff(np.column_stack(list(time.values())),axis=1)>0).all(axis=1)
    cols, families = {}, {}

    def add(family,name,value):
        cols[name] = np.where(valid,np.asarray(value,float),np.nan)
        families.setdefault(family,[]).append(name)

    speed = {k:np.linalg.norm(vel[k],axis=1) for k in PLANES}
    with np.errstate(invalid='ignore',divide='ignore'):
        for k in PLANES:
            for j,axis in enumerate('xyz'):
                add('plane_position',f'{axis}{k}_m',pos[k][:,j])
                add('plane_velocity',f'v{axis}{k}_mps',vel[k][:,j])
            add('flight_time',f't{k}_s',time[k])
            add('plane_speed',f'speed{k}_mps',speed[k])
            add('approach_angles',f'yaw{k}_deg',np.degrees(np.arctan2(vel[k][:,0],-vel[k][:,1])))
            add('approach_angles',f'pitch{k}_deg',np.degrees(np.arctan2(vel[k][:,2],np.hypot(vel[k][:,0],vel[k][:,1]))))
            add('normalized_geometry',f'armside{k}_over_height',-hand*pos[k][:,0]/height)
            add('normalized_geometry',f'z{k}_over_height',pos[k][:,2]/height)
            add('curvature',f'curvature{k}_per_m',np.linalg.norm(np.cross(vel[k],a),axis=1)/speed[k]**3)
            add('curvature',f'tangent_accel{k}_mps2',(vel[k]*a).sum(axis=1)/speed[k])
        keys = list(PLANES)
        for lo,hi in zip(keys[:-1],keys[1:]):
            add('flight_time',f'dt_{lo}_{hi}_s',time[hi]-time[lo])
        for k in keys[:-1]:
            dt = time['front']-time[k]
            hb = .5*a[:,0]*dt**2
            ivb = .5*(a[:,2]+G)*dt**2
            add('gravity_removed_movement',f'hb{k}_cm',hb*100)
            add('gravity_removed_movement',f'ivb{k}_cm',ivb*100)
            add('gravity_removed_movement',f'movement{k}_cm',np.hypot(hb,ivb)*100)
            add('gravity_removed_movement',f'movement_arm_axis{k}_deg',np.where(np.hypot(hb,ivb)>0,np.degrees(np.arctan2(-hand*hb,ivb)),np.nan))
        tangent = vel['55']/speed['55'][:,None]
        along = (a*tangent).sum(axis=1)
        transverse = a-tangent*along[:,None]
        effective = a.copy(); effective[:,2] += G
        add('acceleration_decomposition','acceleration_mps2',np.linalg.norm(a,axis=1))
        add('acceleration_decomposition','along_accel55_mps2',along)
        for j,axis in enumerate('xyz'):
            add('acceleration_decomposition',f'transverse_{axis}55_mps2',transverse[:,j])
            add('acceleration_decomposition',f'gravity_removed_a{axis}_mps2',effective[:,j])
        add('acceleration_decomposition','transverse_accel55_mps2',np.linalg.norm(transverse,axis=1))
        mid = crossing(p[:,1],v[:,1],a[:,1],8.5/12*FT)
        xm = p[:,0]+v[:,0]*mid+.5*a[:,0]*mid**2
        add('report_consistency','px_mid_error_cm',(xm-d.px.to_numpy(float)*FT)*100)
        add('report_consistency','pz_front_error_cm',(pos['front'][:,2]-d.pz.to_numpy(float)*FT)*100)
        add('report_consistency','hb_report_error_cm',d.horizontal_movement_cm.to_numpy(float)-cols['hb50_cm'])
        add('report_consistency','ivb_report_error_cm',d.vertical_movement_cm.to_numpy(float)-cols['ivb50_cm'])
        add('flight_normalization','hb_arm_over_dt2_mps2',-.5*hand*a[:,0])
        add('flight_normalization','ivb_over_dt2_mps2',.5*(a[:,2]+G))
        add('flight_normalization','movement_over_dt2_mps2',.5*np.hypot(a[:,0],a[:,2]+G))
        add('flight_normalization','armside_vx55_over_minus_vy',hand*vel['55'][:,0]/(-vel['55'][:,1]))
    return pd.DataFrame(cols,index=d.index), valid, families

def location_oof(d,f,valid):
    from sklearn.model_selection import GroupKFold
    from sklearn.preprocessing import PolynomialFeatures, StandardScaler
    from sklearn.linear_model import Ridge
    hand = d.pitcher_hand.map({'Right':1.,'Left':-1.}).to_numpy(float)
    top,bottom = d.sz_top.to_numpy(float),d.sz_bottom.to_numpy(float)
    with np.errstate(divide='ignore',invalid='ignore'):
        x = np.column_stack([-hand*d.px.to_numpy(float)*FT,
                             (d.pz.to_numpy(float)-(top+bottom)/2)/((top-bottom)/2),
                             f.speed55_mps,d.height_cm.to_numpy(float)/100,
                             (hand<0).astype(float),d.pitch_type_code.isin(['FT','SI']).to_numpy(float)])
    y = np.column_stack([-hand*f.hb50_cm,f.ivb50_cm])
    eligible = valid & d.pitch_type_code.isin(['FF','FT','SI']).to_numpy() & (top>bottom)
    eligible &= np.isfinite(x).all(axis=1)&np.isfinite(y).all(axis=1)&np.isfinite(hand)
    idx = np.flatnonzero(eligible)
    groups = d.pitcher_id.to_numpy()[idx]
    residual = np.full((len(d),2),np.nan); folds = np.full(len(d),-1,int)
    poly = PolynomialFeatures(2,include_bias=False)
    basis = poly.fit_transform(x[idx]) # fixed algebra; no fitted data statistics
    fold_reports = []
    for fold,(tr,te) in enumerate(GroupKFold(5).split(basis,groups=groups)):
        assert not set(groups[tr])&set(groups[te])
        counts = pd.Series(groups[tr]).value_counts()
        weights = np.array([1/counts[g] for g in groups[tr]]); weights /= weights.mean()
        scaler = StandardScaler().fit(basis[tr],sample_weight=weights)
        btr = scaler.transform(basis[tr]); bte = scaler.transform(basis[te])
        model = Ridge(alpha=100).fit(btr,y[idx[tr]],sample_weight=weights)
        pred = model.predict(bte)
        residual[idx[te]] = y[idx[te]]-pred
        folds[idx[te]] = fold
        # independent augmented weighted normal equations, including free intercept
        design = np.column_stack([np.ones(len(tr)),btr])
        penalty = np.diag(np.r_[0.,np.full(btr.shape[1],100.)])
        coef = np.linalg.solve(design.T@(weights[:,None]*design)+penalty,design.T@(weights[:,None]*y[idx[tr]]))
        delta = float(np.max(abs(np.column_stack([np.ones(len(te)),bte])@coef-pred)))
        assert delta<1e-7
        fold_reports.append({'fold':fold,'train_pitches':len(tr),'test_pitches':len(te),
                             'train_players':len(set(groups[tr])),'test_players':len(set(groups[te])),
                             'player_overlap':0,'independent_normal_equation_max_difference_cm':delta})
    f = f.copy()
    f['location_oof_hb_arm_residual_cm'] = residual[:,0]
    f['location_oof_ivb_residual_cm'] = residual[:,1]
    return f,folds,fold_reports
