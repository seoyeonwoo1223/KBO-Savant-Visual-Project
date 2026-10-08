"""0008 기존 주장 검산과 실제 원본 가용성 조사. 새 각도 후보는 계산하지 않는다."""
import argparse
import hashlib
import itertools
import json
from pathlib import Path
import numpy as np
import pandas as pd
import pyarrow.parquet as pq
from sklearn.model_selection import GroupKFold

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
PACKAGE=ROOT/'analysis/arm_angle/tracking_rebuilt_20261009'

def sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for b in iter(lambda:f.read(8*1024*1024),b''):h.update(b)
    return h.hexdigest()

def dump(path,data):
    Path(path).write_text(json.dumps(data,ensure_ascii=False,indent=2,allow_nan=False)+'\n')

def independent_oof(x,y,groups):
    # sklearn PolynomialFeatures/Ridge/StandardScaler와 독립적인 전개·가중 정상방정식.
    basis=np.column_stack([x]+[x[:,i]*x[:,j] for i,j in itertools.combinations_with_replacement(range(x.shape[1]),2)])
    residual=np.full_like(y,np.nan)
    for tr,te in GroupKFold(5).split(x,groups=groups):
        assert not set(groups[tr])&set(groups[te])
        n=pd.Series(groups[tr]).value_counts()
        w=np.array([1/n[g] for g in groups[tr]]);w/=w.mean()
        mu=np.average(basis[tr],axis=0,weights=w)
        sd=np.sqrt(np.average((basis[tr]-mu)**2,axis=0,weights=w));sd[sd==0]=1.
        btr=np.column_stack([np.ones(len(tr)),(basis[tr]-mu)/sd])
        bte=np.column_stack([np.ones(len(te)),(basis[te]-mu)/sd])
        penalty=np.diag(np.r_[0.,np.full(basis.shape[1],100.)])
        coef=np.linalg.solve(btr.T@(w[:,None]*btr)+penalty,btr.T@(w[:,None]*y[tr]))
        residual[te]=y[te]-bte@coef
    mae=pd.DataFrame({'player':groups,'hb':abs(residual[:,0]),'ivb':abs(residual[:,1])}).groupby('player').mean().mean()
    return residual,mae.to_dict()

def check_review(cache):
    d=pd.read_parquet(PACKAGE/'inputs/selected_2026.parquet')
    summary=json.loads((PACKAGE/'results/summary.json').read_text())
    assert sha(cache)==summary['pitch_cache_sha256']
    fields=['pitch_id','game_id','oof_fold','speed55_mps','hb50_cm','ivb50_cm','movement_over_dt2_mps2','tfront_s']
    fields += [f'{prefix}{plane}{suffix}' for plane in ['55','50','238','10'] for prefix,suffix in [('t','_s'),('movement','_cm')]]
    f=pd.read_parquet(cache,columns=fields+['location_oof_hb_arm_residual_cm','location_oof_ivb_residual_cm'])
    assert d.pitch_id.equals(f.pitch_id) and d.game_id.equals(f.game_id)
    hand=d.pitcher_hand.map({'Right':1.,'Left':-1.}).to_numpy(float)
    idx=np.flatnonzero(f.oof_fold.ge(0)); groups=d.pitcher_id.to_numpy()[idx]
    top,bot=d.sz_top.to_numpy(float),d.sz_bottom.to_numpy(float)
    with np.errstate(invalid='ignore',divide='ignore'):
        x=np.column_stack([-hand*d.px.to_numpy(float)*.3048,
                           (d.pz.to_numpy(float)-(top+bot)/2)/((top-bot)/2),
                           f.speed55_mps,d.height_cm.to_numpy(float)/100,(hand<0).astype(float),
                           d.pitch_type_code.isin(['FT','SI']).to_numpy(float)])[idx]
    y=np.column_stack([-hand*f.hb50_cm,f.ivb50_cm])[idx]
    full,mae=independent_oof(x,y,groups)
    _,noloc=independent_oof(x[:,2:],y,groups)
    published=f[['location_oof_hb_arm_residual_cm','location_oof_ivb_residual_cm']].to_numpy()[idx]
    error=float(abs(full-published).max());assert error<1e-7
    counterpart=json.loads((ROOT/'analysis/arm_angle/claude_review_tr1_20261009/review_tr1.json').read_text())
    for key,col in [('hb','hb_arm_MAE_cm'),('ivb','ivb_MAE_cm')]:
        assert abs(mae[key]-counterpart['location_contribution']['with_location'][col])<1e-9
        assert abs(noloc[key]-counterpart['location_contribution']['without_px_pz'][col])<1e-9
    kind=d.pitch_type_code.replace({'FT':'SI'}).to_numpy()[idx]
    residual=pd.DataFrame({'player':groups,'kind':kind,'hb':full[:,0],'ivb':full[:,1]})
    centers={}
    for k in ['FF','SI']:
        q=residual.loc[residual.kind.eq(k)].groupby('player')[['hb','ivb']].mean()
        centers[k]={'pitches':int((kind==k).sum()),'players':len(q),'hb_mean_cm':float(q.hb.mean()),'ivb_mean_cm':float(q.ivb.mean())}
    pairs=pd.read_csv(PACKAGE/'results/paired_FF_SI.csv',dtype={'pitcher_id':str})
    report=pairs[['pitcher_id','pitcher_name','FF_n','SI_n']].copy()
    for key,col in [('hb','location_oof_hb_arm_residual_cm_SI_minus_FF'),('ivb','location_oof_ivb_residual_cm_SI_minus_FF')]:
        report[key+'_raw_difference_cm']=pairs[col]
        report[key+'_global_type_center_difference_cm']=centers['SI'][key+'_mean_cm']-centers['FF'][key+'_mean_cm']
        report[key+'_descriptive_centered_difference_cm']=report[key+'_raw_difference_cm']-report[key+'_global_type_center_difference_cm']
    report.to_csv(HERE/'descriptive_centered_pairs.csv',index=False,float_format='%.12g')
    counts=pd.Series(groups).value_counts();w=np.array([1/counts[g] for g in groups])
    identities={p:float(abs(f[f'movement{p}_cm']/100/(f.tfront_s-f[f't{p}_s'])**2-f.movement_over_dt2_mps2).max()) for p in ['55','50','238','10']}
    assert max(identities.values())<1e-12
    dump(HERE/'verification.json',{'source_research_commit':'1e24467c4a6016583bc91178f14abc65026ee8f4',
         'verified_cache_sha256':sha(cache),'independent_equation_prediction_max_difference_cm':error,
         'with_location_player_equal_MAE_cm':mae,'without_location_player_equal_MAE_cm':noloc,
         'location_MAE_reduction_cm':{k:noloc[k]-mae[k] for k in mae},
         'residual_centers_type_specific_player_populations':centers,
         'FF_SI_equal_player_paired_count':len(report),
         'paired_means_cm':report.select_dtypes('number').drop(columns=['FF_n','SI_n']).mean().to_dict(),
         'whole_cohort_exposure_weight_FF_share':float(w[kind=='FF'].sum()/w.sum()),
         'flight_normalization_identity_max_difference_mps2':identities,
         'centering_is_posthoc_descriptive_not_honest_predictive_transform':True,
         'type_center_causes_not_identified':True,'new_angle_candidate':False,'angle_accuracy_evaluated':False})
    print('0008 C3/C5/C6 검산 통과')

def inventory(local_root,handoff_root):
    # 알려진 인계 manifest의 10개 정확한 경로만 검사한다. 디렉터리 glob 없음.
    manifest=handoff_root/'repo/.cache/arm_angle/pitch_joint_20261006/mlb_manifest.json'
    package_manifest=json.loads((handoff_root/'MANIFEST.json').read_text())
    rel=str(manifest.relative_to(handoff_root))
    record=next(x for x in package_manifest['files'] if x['path']==rel)
    assert sha(manifest)==record['sha256']
    sources=json.loads(manifest.read_text())['inputs']['sources']
    fields=['ax','ay','az','vx0','vy0','vz0','release_pos_x','release_pos_y','release_pos_z']
    reports=[];samples=[]
    for rel,wanted in sources.items():
        path=local_root/rel
        digest=sha(path);assert digest==wanted,rel
        pf=pq.ParquetFile(path);assert set(fields)<=set(pf.schema_arrow.names)
        count_axaz=count_all=0; sample_taken=False
        for batch in pf.iter_batches(batch_size=65536,columns=fields+['game_year','game_date','game_pk','at_bat_number','pitch_number','pitcher','pitch_type']):
            q=batch.to_pandas(); count_axaz+=int(np.isfinite(q[['ax','az']].to_numpy(float)).all(axis=1).sum())
            finite=np.isfinite(q[fields].to_numpy(float)).all(axis=1);count_all+=int(finite.sum())
            if not sample_taken and finite.any():
                small=q.loc[finite].head(5).copy();small['source_path']=rel;samples.append(small);sample_taken=True
        reports.append({'path':rel,'sha256':digest,'matches_remote_handoff_manifest':True,
                        'bytes':path.stat().st_size,'rows':pf.metadata.num_rows,'finite_ax_az_rows':count_axaz,
                        'finite_9_available_fields_rows':count_all,'available_fields':fields,
                        'literal_x0_y0_z0_present':{k:k in pf.schema_arrow.names for k in ['x0','y0','z0']}})
    pd.concat(samples,ignore_index=True).to_csv(HERE/'MLB_acceleration_samples.csv',index=False,float_format='%.12g')
    dump(HERE/'MLB_availability.json',{'source':'existing local original Parquet, SHA-linked to remote continuation ZIP',
        'handoff_commit':'d272fbe4244c1f155dede8b209fda01c95a53b6b','source_manifest_sha256':sha(manifest),
        'files_verified':len(reports),'files':reports,'rows':sum(x['rows'] for x in reports),
        'finite_ax_az_rows':sum(x['finite_ax_az_rows'] for x in reports),
        'full_original_data_published':False,'sample_rows_published':sum(len(s) for s in samples),
        'acceleration_available_locally':True,'literal_9_coefficient_reference_plane_audited':False,
        'release_positions_not_assumed_to_be_x0_y0_z0':True,'labels_read':False,
        'deduplication_cohort_and_selection_for_new_experiment_performed':False})
    print('MLB 원본 SHA/ax·az 확인',len(reports),'files',sum(x['rows'] for x in reports),'rows')

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--derived-cache',type=Path,required=True)
    parser.add_argument('--local-original-root',type=Path,required=True)
    parser.add_argument('--handoff-root',type=Path,required=True)
    args=parser.parse_args()
    check_review(args.derived_cache)
    inventory(args.local_original_root,args.handoff_root)

if __name__=='__main__':main()
