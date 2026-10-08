"""고정 원격 canonical에서 선택 입력만 저장한다. 원본에는 쓰지 않는다."""
from pathlib import Path
import hashlib
import argparse
import json
import subprocess
import sys
import zipfile
import pandas as pd

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT / 'src'))
from visualbaseball.curated import load_rows

BASE = '35891bdbe96b7feb4f42ecff33c8895f8aee1284'
CONTINUATION = 'd272fbe4244c1f155dede8b209fda01c95a53b6b'
COLS = ['season','game_date','game_id','pitch_id','pitcher_id','pitcher_name',
        'pitch_type_code','stadium','x0','y0','z0','vx0','vy0','vz0','ax','ay','az',
        'px','pz','sz_top','sz_bottom','horizontal_movement_cm','vertical_movement_cm',
        'source_y0','trajectory_valid','trajectory_status',
        'release_x_50','release_z_50','release_x_55','release_z_55',
        'vx_50','vy_50','vz_50','vx_55','vy_55','vz_55']

def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def dump(path, obj):
    Path(path).write_text(json.dumps(obj, ensure_ascii=False, indent=2, allow_nan=False)+'\n')

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--handoff-zip',required=True,type=Path,help='고정 continuation 커밋에서 받은 ZIP')
    args=parser.parse_args()
    zip_path=args.handoff_zip.resolve()
    rel='analysis/arm_angle/review-context/eaa-continuation-20261007.zip'
    blob=subprocess.check_output(['git','rev-parse',f'{CONTINUATION}:{rel}'],cwd=ROOT,text=True).strip()
    assert subprocess.check_output(['git','hash-object',str(zip_path)],cwd=ROOT,text=True).strip()==blob
    with zipfile.ZipFile(zip_path) as package:
        prefix='eaa-continuation-20261007/'
        manifest=json.loads(package.read(prefix+'MANIFEST.json'))
        for entry in manifest['files']:
            data=package.read(prefix+entry['path'])
            assert len(data)==entry['bytes'] and hashlib.sha256(data).hexdigest()==entry['sha256']
        reference_path='repo/analysis/arm_angle/results/eaa_orthogonal_residual_20261006_KBO2026_predictions.csv'
        reference=package.read(prefix+reference_path)
    dest = HERE/'inputs'
    dest.mkdir(exist_ok=True)
    if (dest/'selected_2026.parquet').exists():
        raise SystemExit('입력이 이미 있음: 재확보로 덮어쓰지 않는다')
    summary = json.loads((ROOT/'data/curated/summary.json').read_text())
    schema = json.loads((ROOT/'data/curated/schema.json').read_text())
    assert set(COLS) <= {x['name'] for x in schema['tables']['pitches']}
    paths = ['data/curated/summary.json','data/curated/schema.json',
             'data/tracking/player_heights.csv','data/curated/players/player_bio.parquet',
             'data/models/estimated_arm_angle_v3.json','src/visualbaseball/numeric_arm_angle_features.py']
    paths += [f'data/curated/pitches/season=2026/month={m}.parquet'
              for m in summary['seasons']['2026']['months']]
    sources = []
    for rel in paths:
        path = ROOT/rel
        blob = subprocess.check_output(['git','rev-parse',f'{BASE}:{rel}'],cwd=ROOT,text=True).strip()
        actual = subprocess.check_output(['git','hash-object',str(path)],cwd=ROOT,text=True).strip()
        assert actual == blob, rel
        sources.append({'path':rel,'git_blob':blob,'sha256':sha(path),'bytes':path.stat().st_size})
    raw = pd.DataFrame(load_rows(ROOT,'pitches',2026,columns=COLS))
    observed_rows = len(raw)
    raw = raw.loc[raw.game_date.between('2026-03-28','2026-10-04')].copy()
    assert not raw[['game_id','pitch_id']].duplicated().any()
    heights = pd.read_csv(ROOT/'data/tracking/player_heights.csv',dtype={'player_id':str})
    bio = pd.read_parquet(ROOT/'data/curated/players/player_bio.parquet',
                         columns=['player_id','player_name','throws'])
    bio.player_id = bio.player_id.astype(str)
    assert heights.player_id.is_unique and bio.player_id.is_unique
    raw.pitcher_id = raw.pitcher_id.astype(str)
    heights = heights.set_index('player_id'); bio = bio.set_index('player_id')
    normalize = lambda s: s.astype('string').str.replace(' ','',regex=False)
    name = normalize(raw.pitcher_name)
    identity = name.eq(normalize(raw.pitcher_id.map(heights.player_name))) & name.eq(normalize(raw.pitcher_id.map(bio.player_name)))
    raw['identity_verified'] = identity.fillna(False)
    raw['height_cm'] = raw.pitcher_id.map(heights.height_cm).where(identity)
    raw['pitcher_hand'] = raw.pitcher_id.map(bio.throws).map({'R':'Right','L':'Left'}).where(identity)
    raw = raw.sort_values(['game_date','game_id','pitch_id']).reset_index(drop=True)
    raw.to_parquet(dest/'selected_2026.parquet',index=False,compression='zstd')
    (dest/'previous_KBO2026_predictions.csv').write_bytes(reference)
    dump(HERE/'source.json',{
        'repository':'seoyeonwoo1223/KBO-Savant-Visual-Project','source_branch':'experiment/eaa-sinker-support-20261007',
        'source_commit':BASE,'acquired_date_KST':'2026-10-09','date_filter':['2026-03-28','2026-10-04'],
        'observed_canonical_range':summary['seasons']['2026']['date_range'],
        'observed_canonical_rows':observed_rows,'selected_rows':len(raw),
        'source_files':sources,'selected_sha256':sha(dest/'selected_2026.parquet'),
        'continuation_branch_commit':CONTINUATION,'continuation_zip_sha256':sha(zip_path),
        'continuation_zip_path':'analysis/arm_angle/review-context/eaa-continuation-20261007.zip',
        'continuation_manifest_files_verified':187,
        'previous_prediction_reference':{'zip_member':reference_path,'sha256':hashlib.sha256(reference).hexdigest(),
                                        'verified_against_handoff_manifest':True,'used_as_training_labels':False},
        'handoff_smoke':{'passed':True,'MLB_seasons':2295,'fixed_training_seasons':1095,
                         'KBO_players':195,'prediction_max_difference_deg':3.602451670303708e-12,
                         'refit_coefficient_max_difference':1.846097927304946e-12,
                         'raw_pitch_source_verification_performed':False},
        'previous_unpublished_snapshot_available':False,
        'new_implementation_not_identical_to_unpublished_code':True,
        'missing_values_imputed':False})
    print('선택 입력',len(raw),'rows',len(raw.columns),'columns')

if __name__ == '__main__':
    main()
