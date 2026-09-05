"""League-execution ZA: (actual swing - expected swing) * (swing RV - take RV).

One chronological holdout selects direct vs event-decomposed action values.
Three date-block cross-fits score every pitch without its own game's outcomes.
RE tables, models, event priors and support counts are fitted on training only.
"""
from __future__ import annotations
from collections import Counter, defaultdict
import argparse
import json
from pathlib import Path
import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq
from sklearn.metrics import log_loss, brier_score_loss
from . import plate_decision_v1 as old
from .pitch_arsenal import _load_batter_hands, _resolved_batter_stance
from .swing_take import _excel_rows, _eligible, _relative_location, _action, _state
from .zone_awareness_v2 import _team_history

REGIONS = ('heart', 'shadow_in', 'shadow_out', 'chase', 'waste')
EVENTS = ('Whiff', 'Foul', 'InPlay', 'Ball', 'CalledStrike', 'HBP')
NUMERIC = old.BASE_NUMERIC + old.MOVEMENT_NUMERIC
CONTRACT = {
 'za_raw': '100 * mean((S - p_swing) * (V_swing - V_take)); runs per 100 pitches',
 'raw_dv': 'sum((S - p_swing) * (V_swing - V_take)); cumulative runs',
 'dv_per_100': 'same as za_raw; retained for backward-compatible consumers',
 'zone_judgment_raw': '100 * mean((S - p_swing) * (2*p_called_strike_if_take - 1)); percentage points',
 'swing_aggression': '100 * mean(S - p_swing); percentage points, tendency only',
 'za_percentile': 'midrank percentile among season hitters with at least 300 eligible pitches',
 'region_contributions': '100 * sum(D in region/action) / ALL eligible player pitches; additive',
}
LIMITATIONS = [
 '리그 평균 실행 능력을 기준으로 추정한 의사결정 가치이며 개인별 최적 판단의 정답이 아닙니다.',
 '관측하지 못한 반대 행동과 누락된 투구 특성에 따른 선택 편향이 남습니다. 실제 타구속도·발사각·해당 투구의 안타/홈런은 판단 점수의 입력이 아닙니다.',
 '시즌 표시값은 날짜 블록 교차적합으로 해당 경기 결과를 제외하지만 다른 블록의 미래 경기를 사용할 수 있습니다. 순수한 사전 예측 성능은 별도 시간 분리 평가에서 확인합니다.',
]


def decision_value(swing, probability, swing_value, take_value):
 return (np.asarray(swing) - np.asarray(probability)) * (np.asarray(swing_value) - np.asarray(take_value))


def region(row):
 d = max(abs(row['x_relative']), abs(row['z_relative']))
 return 'heart' if d <= 2/3 else 'shadow_in' if d <= 1 else 'shadow_out' if d <= 4/3 else 'chase' if d <= 2 else 'waste'


def outcome(row):
 # Classify by this pitch's call, never a nonterminal pitch's eventual PA result.
 code = str(row.get('pitch_call_code') or '').upper()
 if row.get('is_pa_terminal') and (str(row.get('pa_type') or '').lower() == 'hbp' or row.get('pa_result') == '사구'):
  return 'HBP'
 return {'S':'Whiff', 'F':'Foul', 'X':'InPlay', 'B':'Ball', 'T':'CalledStrike'}.get(code)


def load_rows(root, season):
 cache = root / '.cache' / f'za_source_{season}.parquet'
 source = root / 'data/processed/pitches.parquet'
 if season == 2026:
  rows = pq.read_table(source).to_pylist()
 elif cache.exists() and cache.stat().st_mtime >= (root/'exports'/f'visualbaseball_savant_{season}_latest.xlsx').stat().st_mtime:
  rows = pq.read_table(cache).to_pylist()
 else:
  rows = _excel_rows(root/'exports'/f'visualbaseball_savant_{season}_latest.xlsx', season)
  cache.parent.mkdir(exist_ok=True)
  pq.write_table(pa.Table.from_pylist(rows), cache)
 # Include all recorded pitches in inning run totals, including nondecision rows.
 halves = defaultdict(list)
 for r in rows:
  halves[(r['game_id'], r['inning'], r['inning_half'])].append(r)
 for items in halves.values():
  remaining = 0.
  for r in sorted(items, key=lambda r:r['event_seq'], reverse=True):
   remaining += float(r.get('runs_on_pitch') or 0)
   r['_runs_to_end'] = remaining
 hands = _load_batter_hands(root, season)
 valid, excluded = [], Counter()
 for r in rows:
  if not _eligible(r) or not r.get('batter_id') or not r.get('batter_name') or outcome(r) is None:
   excluded['invalid_state_location_action_or_identity'] += 1
   continue
  r['x_relative'], r['z_relative'] = _relative_location(r)
  r['decision_type'] = 'Swing' if outcome(r) in EVENTS[:3] else 'Take'
  r['batter_stance'] = _resolved_batter_stance(r, hands)
  r['event'] = outcome(r)
  r['region'] = region(r)
  valid.append(r)
 movement = old._movement_adjust(valid, root, season)
 # Retain pre-pitch features, transitions, identity and training target only.
 keep = set(NUMERIC + old.CATEGORICAL + ('game_id','game_date','season','batter_id','batter_name','batter_team','inning_half','event','region','decision_type','_runs_to_end','runs_on_pitch'))
 keep.update(f'{k}_{w}' for k in ('base_state_code','outs','balls','strikes') for w in ('before','after'))
 valid = [{k:v for k,v in r.items() if k in keep} for r in valid]
 return sorted(valid, key=lambda r:r['game_id']), {'source':str(source.relative_to(root)) if season==2026 else f'exports/visualbaseball_savant_{season}_latest.xlsx', 'excluded':dict(excluded), 'movement':movement, 'unknown_stance':sum(not r['batter_stance'] for r in valid)}


class RunExpectancy:
 def __init__(self, rows):
  full, base, outs = defaultdict(list), defaultdict(list), defaultdict(list)
  for r in rows:
   s = _state(r, 'before'); v = r['_runs_to_end']
   full[s].append(v); base[s[:2]].append(v); outs[s[1]].append(v)
  self.outs = {k:float(np.mean(v)) for k,v in outs.items()}
  self.base = {k:(sum(v)+50*self.outs[k[1]])/(len(v)+50) for k,v in base.items()}
  self.full = {k:(sum(v)+50*self.base[k[:2]])/(len(v)+50) for k,v in full.items()}
 def value(self, s):
  if s[1] >= 3: return 0.
  return self.full.get(s, self.base.get(s[:2], self.outs.get(s[1], 0.)))
 def target(self, rows):
  return np.array([float(r.get('runs_on_pitch') or 0)+self.value(_state(r,'after'))-self.value(_state(r,'before')) for r in rows])


def encode(train, test):
 # Unknown categories are missing, never mapped to another known category.
 cols_a, cols_b = [], []
 for f in NUMERIC:
  cols_a.append([old._safe_float(r.get(f)) for r in train]); cols_b.append([old._safe_float(r.get(f)) for r in test])
 for f in old.CATEGORICAL:
  mapping = {v:i for i,v in enumerate(sorted({str(r.get(f) or '') for r in train}))}
  cols_a.append([mapping[str(r.get(f) or '')] for r in train]); cols_b.append([mapping.get(str(r.get(f) or ''),np.nan) for r in test])
 return np.column_stack(cols_a), np.column_stack(cols_b)


def support_key(r):
 return (round(r['x_relative']*2),round(r['z_relative']*2),r['balls_before'],r['strikes_before'])


def fit_predict(train, test, candidate=True):
 a,b = encode(train,test)
 re = RunExpectancy(train); target = re.target(train)
 actions = np.array([r['decision_type']=='Swing' for r in train],dtype=int)
 events = np.array([EVENTS.index(r['event']) for r in train])
 propensity = old._classifier(len(NUMERIC)).fit(a,actions)
 p = propensity.predict_proba(b)[:,list(propensity.classes_).index(1)]
 probs = np.zeros((len(test),6)); direct=np.zeros((len(test),2)); staged=direct.copy()
 counts = Counter((support_key(r),r['decision_type']) for r in train)
 support = np.array([[counts[(support_key(r),action)] for action in ('Take','Swing')] for r in test])
 for act, indices in ((0,range(3,6)),(1,range(3))):
  mask = actions==act
  direct[:,act] = old._regressor(len(NUMERIC)).fit(a[mask],target[mask]).predict(b)
  clf = old._classifier(len(NUMERIC)).fit(a[mask],events[mask])
  pred = clf.predict_proba(b)
  for i,label in enumerate(clf.classes_): probs[:,int(label)]=pred[:,i]
  if not candidate: continue
  # Event RV priors back off event x count x base/out -> event x count -> event.
  for ev in indices:
   em = events==ev
   global_mean = float(np.mean(target[em])) if em.any() else float(np.mean(target[mask]))
   by_count, by_state = defaultdict(list), defaultdict(list)
   for j in np.flatnonzero(em):
    r=train[j]; by_count[(r['balls_before'],r['strikes_before'])].append(target[j]); by_state[_state(r,'before')].append(target[j])
   cm={k:(sum(v)+50*global_mean)/(len(v)+50) for k,v in by_count.items()}
   sm={k:(sum(v)+50*cm[k[2:]])/(len(v)+50) for k,v in by_state.items()}
   prior=np.array([sm.get(_state(r,'before'),cm.get(_state(r,'before')[2:],global_mean)) for r in test])
   values=prior
   if ev==2 and em.sum()>=160:
    model=old._regressor(len(NUMERIC)).fit(a[em],target[em])
    local=Counter(support_key(train[j]) for j in np.flatnonzero(em))
    n=np.array([local[support_key(r)] for r in test]); weight=n/(n+50.)
    values=weight*model.predict(b)+(1-weight)*prior
   staged[:,act]+=probs[:,ev]*values
 return {'p':p,'direct':direct,'staged':staged,'probs':probs,'support':support,'target':re.target(test)}


def temporal_evaluation(rows):
 dates=sorted({r['game_id'][:8] for r in rows}); cutoff=dates[int(len(dates)*.7)]
 train=[r for r in rows if r['game_id'][:8]<cutoff]; test=[r for r in rows if r['game_id'][:8]>=cutoff]
 print('  Temporal holdout',cutoff,len(train),len(test),flush=True)
 pred=fit_predict(train,test)
 action=np.array([r['decision_type']=='Swing' for r in test],dtype=int); idx=np.arange(len(test))
 metrics={}
 for name in ('direct','staged'):
  errors=(pred[name][idx,action]-pred['target'])**2
  metrics[name]={'mse':float(errors.mean()),'swing_mse':float(errors[action==1].mean()),'take_mse':float(errors[action==0].mean())}
 # Fixed gate: aggregate improvement, neither action deteriorates >2%.
 accepted=(metrics['staged']['mse']<metrics['direct']['mse'] and all(metrics['staged'][f'{s}_mse']<=metrics['direct'][f'{s}_mse']*1.02 for s in ('swing','take')))
 event_metrics={}
 labels=np.array([EVENTS.index(r['event']) for r in test])
 for name,act,inds in (('swing',1,list(range(3))),('take',0,list(range(3,6)))):
  mask=action==act
  event_metrics[name+'_log_loss']=float(log_loss(labels[mask],pred['probs'][mask][:,inds],labels=inds))
 return {'split_date':cutoff,'train_pitches':len(train),'test_pitches':len(test),'swing_log_loss':float(log_loss(action,pred['p'])),'swing_brier':float(brier_score_loss(action,pred['p'])),'action_value':metrics,'event_probability':event_metrics,'selected':'staged' if accepted else 'direct','selection_rule':'lower held-out observed-action MSE, neither swing nor take MSE worse by more than 2%; player ranks and SA correlation are not selection targets','counterfactual_validation':'unobserved opposite actions cannot be directly validated'}


def r6(x): return round(float(x),6)
def mean(items,key,scale=1): return r6(scale*np.mean([r[key] for r in items])) if items else None


def profile_summary(items):
 n=len(items); first=items[0]
 total=sum(r['dv'] for r in items)
 s={'season':first['season'],'batter_id':str(first['batter_id']),'batter_name':first['batter_name'],'team':_team_history(items),'pitches_seen':n,'qualified_300':n>=300,'za_raw':r6(100*total/n),'dv_per_100':r6(100*total/n),'raw_dv':r6(total),'swing_aggression':r6(100*np.mean([r['swing']-r['p_swing'] for r in items])),'zone_judgment_raw':mean(items,'judgment',100),'za_percentile':None,'low_opposite_support_pitches':sum(r['opposite_support']<30 for r in items)}
 for action in ('swing','take'):
  selected=[r for r in items if r['swing']==(action=='swing')]
  s[action+'_pitches']=len(selected)
  s[action+'_decision_value_per_100']=r6(100*sum(r['dv'] for r in selected)/n)
 for reg in REGIONS:
  selected=[r for r in items if r['region']==reg]
  s[reg+'_pitches']=len(selected); s[reg+'_raw_dv']=r6(sum(r['dv'] for r in selected))
  s[reg+'_decision_value_per_100']=r6(100*sum(r['dv'] for r in selected)/n)
  for action in ('swing','take'):
   value=sum(r['dv'] for r in selected if r['swing']==(action=='swing'))
   s[f'{reg}_{action}_decision_value_per_100']=r6(100*value/n)
 return s


def cell_summary(items):
 return {'n':len(items),'raw_dv':r6(sum(r['dv'] for r in items)),'dv100':mean(items,'dv',100),'za_raw':mean(items,'dv',100),'delta':mean(items,'delta_v'),'swing_pct':mean(items,'swing',100),'expected_swing_pct':mean(items,'p_swing',100),'p_zone_pct':mean(items,'p_zone',100),'zone_judgment_pct':r6(100*np.mean([r['p_zone'] if r['swing'] else 1-r['p_zone'] for r in items])),'expected_zone_judgment_pct':r6(100*np.mean([r['p_swing']*r['p_zone']+(1-r['p_swing'])*(1-r['p_zone']) for r in items])),'expected_swing_rv':mean(items,'v_swing'),'expected_take_rv':mean(items,'v_take'),**{f'p_{e}':mean(items,f'p_{e}',100) for e in EVENTS}}


def write_web(root,season,pitches,report):
 dest=root/'web/data/zone_awareness'/str(season); dest.mkdir(parents=True,exist_ok=True)
 by_batter=defaultdict(list)
 for r in pitches: by_batter[str(r['batter_id'])].append(r)
 players=[profile_summary(items) for items in by_batter.values()]
 scores=np.array([p['za_raw'] for p in players if p['qualified_300']])
 for p in players: p['za_percentile']=r6(100*(np.sum(scores<p['za_raw'])+.5*np.sum(scores==p['za_raw']))/len(scores)) if len(scores) else None
 def dump(path,payload): path.write_text(json.dumps(payload,ensure_ascii=False,separators=(',',':'),allow_nan=False)+'\n',encoding='utf-8')
 dump(dest/'leaderboard.json',{'schema_version':4,'season':season,'minimum_pitches':300,'qualified_batters':len(scores),'players':players,'metric_contract':CONTRACT,'selected_value_model':report['validation']['selected']})
 dump(dest/'teams.json',{'season':season,'teams':{p['batter_id']:p['team'] for p in players}})
 shards=defaultdict(dict)
 for p in players:
  bid=p['batter_id']; items=by_batter[bid]; cells=defaultdict(list)
  for r in items:
   x,z=r['x_relative'],r['z_relative']
   if abs(x)<=2.5 and abs(z)<=2.5: cells[(round(x/.5)*.5,round(z/.5)*.5)].append(r)
  shards[bid[:2] if bid[0].isdigit() else 'other'][bid]={'summary':p,'overall':cell_summary(items),'grid':[{'x':x,'z':z,**cell_summary(rs)} for (x,z),rs in sorted(cells.items())]}
 pd=dest/'players';pd.mkdir(exist_ok=True)
 for path in pd.glob('*.json'): path.unlink()
 for shard,entries in shards.items(): dump(pd/f'{shard}.json',{'schema_version':4,'season':season,'players':entries})
 catalog=root/'web/data/zone_awareness/index.json'
 previous=json.loads(catalog.read_text()) if catalog.exists() else {'seasons':[]}
 previous.update({'schema_version':4,'seasons':sorted(set(previous['seasons'])|{season},reverse=True)})
 previous['default_season']=max(previous['seasons']);dump(catalog,previous)
 old._write_csv(root/'exports'/f'zone_decision_players_{season}.csv',players)
 return players


def build_zone_decision(root,season=2026):
 print('ZA season',season,flush=True)
 rows,source=load_rows(root,season)
 validation=temporal_evaluation(rows)
 selected=validation['selected'];print('  Selected:',selected,flush=True)
 dates=np.array(sorted({r['game_id'][:8] for r in rows})); result=[]; fold_meta=[]
 for fold,block in enumerate(np.array_split(dates,3)):
  held=set(block);train=[r for r in rows if r['game_id'][:8] not in held];test=[r for r in rows if r['game_id'][:8] in held]
  print('  Scoring block',fold+1,len(test),flush=True)
  pred=fit_predict(train,test,candidate=selected=='staged')
  action=np.array([r['decision_type']=='Swing' for r in test],dtype=int)
  values=pred[selected]; dv=decision_value(action,pred['p'],values[:,1],values[:,0])
  for i,r in enumerate(test):
   pzone=pred['probs'][i,4]
   r.update({'swing':int(action[i]),'p_swing':float(pred['p'][i]),'p_zone':float(pzone),'judgment':float((action[i]-pred['p'][i])*(2*pzone-1)),'v_swing':float(values[i,1]),'v_take':float(values[i,0]),'delta_v':float(values[i,1]-values[i,0]),'dv':float(dv[i]),'opposite_support':int(pred['support'][i,1-action[i]]),'fold':fold})
   for j,e in enumerate(EVENTS): r[f'p_{e}']=float(pred['probs'][i,j])
  result.extend(test);fold_meta.append({'start':str(block[0]),'end':str(block[-1]),'pitches':len(test)})
 # One report: observed fit, period reproducibility and opposite-action support.
 periods=defaultdict(lambda:defaultdict(list))
 for r in result: periods[r['fold']][str(r['batter_id'])].append(r['dv'])
 stability=[]
 for a,b in ((0,1),(1,2)):
  ids=[k for k,v in periods[a].items() if len(v)>=150 and len(periods[b].get(k,[]))>=150]
  x=[np.mean(periods[a][k]) for k in ids];y=[np.mean(periods[b][k]) for k in ids]
  corr=float(np.corrcoef(x,y)[0,1]) if len(ids)>2 and np.std(x)>0 and np.std(y)>0 else None
  stability.append({'blocks':[a+1,b+1],'batters_150_pitches_each':len(ids),'pearson_r':corr,'interpretation':'descriptive repeatability; cross-fit training overlaps, not independent prospective validation'})
 support={reg:{'pitches':sum(r['region']==reg for r in result),'opposite_action_under_30':sum(r['region']==reg and r['opposite_support']<30 for r in result)} for reg in REGIONS}
 report={'schema_version':4,'season':season,'source':source,'pitches':len(result),'validation':validation,'period_reproducibility':stability,'opposite_action_support':support,'support_definition':'training pitches for opposite action in normalized 0.5 location cell x count; under 30 flagged, not removed or score-clipped','crossfit_blocks':fold_meta,'metric_contract':CONTRACT,'shrinkage':'RE state -> base/out -> outs; event RV state -> event/count -> event, 50 prior pitches; InPlay regression blends toward event/state prior with n/(n+50) local InPlay support','limitations':LIMITATIONS}
 players=write_web(root,season,result,report)
 report['batters']=len(players)
 path=root/'data/processed'/f'zone_decision_report_{season}.json';path.parent.mkdir(parents=True,exist_ok=True)
 path.write_text(json.dumps(report,ensure_ascii=False,indent=2,allow_nan=False)+'\n')
 # Compact pitch evidence is reproducible; not committed as a large binary.
 pq.write_table(pa.Table.from_pylist([{k:v for k,v in r.items() if k not in ('adjusted_hb_cm','adjusted_ivb_cm')} for r in result]),root/'.cache'/f'zone_decision_pitches_{season}.parquet')
 return report

if __name__=='__main__':
 parser=argparse.ArgumentParser();parser.add_argument('--root',default='.');parser.add_argument('--seasons',nargs='+',type=int,default=[2024,2025,2026]);args=parser.parse_args()
 for year in args.seasons: build_zone_decision(Path(args.root).resolve(),year)
