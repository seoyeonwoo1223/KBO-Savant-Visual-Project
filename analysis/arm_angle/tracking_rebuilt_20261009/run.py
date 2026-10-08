"""동일 선택 입력으로 재실행 가능한 작은 요약과 큰 로컬 캐시를 만든다."""
from pathlib import Path
import importlib.metadata
import json
import sys
import numpy as np
import pandas as pd

from acquire import HERE, ROOT, sha, dump
from features import derive, location_oof
sys.path.insert(0,str(ROOT/'src'))
from visualbaseball.numeric_arm_angle_features import pitch_features, quality_mask

FOCUS = ['54362','56318','68341','67143','52701']

def write_csv(d,path):
    d.to_csv(path,index=False,float_format='%.12g',lineterminator='\n')

def main():
    dest = HERE/'results';dest.mkdir(exist_ok=True)
    cache = ROOT/'.cache/arm_angle/tracking_rebuilt_20261009';cache.mkdir(parents=True,exist_ok=True)
    source = json.loads((HERE/'source.json').read_text())
    path = HERE/'inputs/selected_2026.parquet'
    assert sha(path)==source['selected_sha256']
    d = pd.read_parquet(path)
    f,valid,families = derive(d)
    f,fold,fold_reports = location_oof(d,f,valid)
    families['location_oof'] = ['location_oof_hb_arm_residual_cm','location_oof_ivb_residual_cm']
    assert len(families)==12 and len(set(sum(families.values(),[])))==len(f.columns)
    # Raw movement inputs here: these are not the operational park/epoch-adjusted eAA inputs.
    old = pitch_features(d)
    numeric = (old.numeric_valid & quality_mask(d)).to_numpy()
    kind = d.pitch_type_code.replace({'FT':'SI'})
    result = pd.concat([d[['pitch_id','game_id','pitcher_id']],pd.DataFrame({'basic_valid':valid,'eaa_raw_numeric_valid':numeric,'oof_fold':fold}),f],axis=1)
    result.to_parquet(cache/'derived_pitches.parquet',index=False,compression='zstd')
    counts = d.assign(kind=kind,basic_valid=valid,eaa_raw_numeric_valid=numeric,oof_eligible=fold>=0).groupby(['pitcher_id','kind'],dropna=False).agg(
        pitcher_name=('pitcher_name','first'),pitches=('pitch_id','size'),games=('game_id','nunique'),
        basic_valid=('basic_valid','sum'),eaa_raw_numeric_valid=('eaa_raw_numeric_valid','sum'),oof_eligible=('oof_eligible','sum')).reset_index()
    mean = f.assign(pitcher_id=d.pitcher_id,kind=kind).groupby(['pitcher_id','kind'],dropna=False).mean().reset_index()
    table = counts.merge(mean,on=['pitcher_id','kind'],validate='one_to_one')
    table['comparison_eligible100'] = table.basic_valid.ge(100)
    write_csv(table,dest/'pitcher_type_means.csv')
    # Per-feature coverage and quantiles prevent means from hiding missingness.
    long=[]
    for col in f:
        x=f[col].dropna()
        long.append({'feature':col,'finite_pitches':len(x),'mean':x.mean(),'p10':x.quantile(.1),'p50':x.quantile(.5),'p90':x.quantile(.9)})
    write_csv(pd.DataFrame(long),dest/'feature_coverage.csv')
    selected = ['speed55_mps','z55_over_height','armside55_over_height','hb50_cm','ivb50_cm',
                'movement_over_dt2_mps2','location_oof_hb_arm_residual_cm','location_oof_ivb_residual_cm']
    pair = table.loc[table.kind.isin(['FF','SI'])&table.comparison_eligible100]
    ff=pair.loc[pair.kind.eq('FF')].set_index('pitcher_id');si=pair.loc[pair.kind.eq('SI')].set_index('pitcher_id')
    shared=sorted(set(ff.index)&set(si.index)); paired=[]
    for player in shared:
        row={'pitcher_id':player,'pitcher_name':ff.loc[player,'pitcher_name'],'FF_n':int(ff.loc[player,'basic_valid']),'SI_n':int(si.loc[player,'basic_valid'])}
        row.update({col+'_SI_minus_FF':si.loc[player,col]-ff.loc[player,col] for col in selected})
        paired.append(row)
    write_csv(pd.DataFrame(paired,columns=['pitcher_id','pitcher_name','FF_n','SI_n']+[c+'_SI_minus_FF' for c in selected]),dest/'paired_FF_SI.csv')
    focus = table.loc[table.pitcher_id.isin(FOCUS)&table.kind.isin(['FF','SI']),
                      ['pitcher_id','pitcher_name','kind','pitches','basic_valid','oof_eligible','comparison_eligible100']+selected]
    benchmark = pd.read_csv(HERE/'inputs/previous_KBO2026_predictions.csv',dtype={'pitcher_id':str})
    ref = benchmark[['pitcher_id','baseline','combined_full']].rename(columns={'baseline':'previous_operating_v3_deg','combined_full':'previous_unadopted_combined1_deg'})
    focus = focus.merge(ref,on='pitcher_id',how='left',validate='many_to_one')
    write_csv(focus,dest/'focus_players.csv')
    assignment = pd.DataFrame({'pitcher_id':d.pitcher_id,'fold':fold}).loc[fold>=0]
    assert assignment.groupby('pitcher_id').fold.nunique().eq(1).all()
    write_csv(assignment.groupby(['pitcher_id','fold']).size().rename('pitches').reset_index(),dest/'oof_player_folds.csv')
    per = pd.DataFrame({'pitcher_id':d.pitcher_id,'hb':f.location_oof_hb_arm_residual_cm,'ivb':f.location_oof_ivb_residual_cm}).dropna()
    residual_metrics = {}
    for col in ['hb','ivb']:
        by=per.assign(abs_error=per[col].abs(),negative=(-per[col]).clip(lower=0)).groupby('pitcher_id')
        residual_metrics[col]={'player_equal_mean_cm':float(by[col].mean().mean()),'player_equal_MAE_cm':float(by.abs_error.mean().mean()),
                               'player_equal_negative_amount_cm':float(by.negative.mean().mean())}
    dump(dest/'summary.json',{
        'source_selected_rows':len(d),'players':int(d.pitcher_id.nunique()),'games':int(d.game_id.nunique()),
        'dates':[d.game_date.min(),d.game_date.max()], 'basic_valid_pitches':int(valid.sum()),
        'raw_eaa_numeric_and_quality_pitches':int(numeric.sum()),'identity_unverified_pitches':int((~d.identity_verified).sum()),
        'missing_height_pitches':int(d.height_cm.isna().sum()),'missing_hand_pitches':int(d.pitcher_hand.isna().sum()),
        'source_y0_counts':{str(k):int(v) for k,v in d.y0.value_counts(dropna=False).items()},
        'families':len(families),'derived_columns':len(f.columns),'deterministic_columns':len(f.columns)-2,'fitted_oof_columns':2,
        'oof_pitches':int((fold>=0).sum()),'oof_players':int(d.loc[fold>=0,'pitcher_id'].nunique()),
        'FF_SI_paired_players100':len(shared),'oof_movement_residual_metrics_not_angle_errors':residual_metrics,
        'previous_record_difference':{'rows':len(d)-213628,'players':int(d.pitcher_id.nunique())-293,'games':int(d.game_id.nunique())-694,
                                      'basic_valid':int(valid.sum())-213540,'derived_columns':len(f.columns)-209,
                                      'input_byte_identity_proven':False,'implementation_identity_proven':False},
        'pitch_cache_sha256':sha(cache/'derived_pitches.parquet'),'pitch_cache_bytes':(cache/'derived_pitches.parquet').stat().st_size,
        'production_changed':False,'KBO_angle_accuracy_measured':False,'new_unused_period_test':False})
    dump(dest/'fold_verification.json',fold_reports)
    dump(HERE/'columns.json',families)
    dump(HERE/'environment.json',{'python':sys.version.split()[0],**{p:importlib.metadata.version(p) for p in ['numpy','pandas','pyarrow','scikit-learn','scipy']}})
    print(json.dumps(json.loads((dest/'summary.json').read_text()),ensure_ascii=False,indent=2))

if __name__=='__main__':
    main()
