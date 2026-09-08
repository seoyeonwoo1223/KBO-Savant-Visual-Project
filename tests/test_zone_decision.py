import numpy as np
from visualbaseball.zone_decision import decision_value, region, outcome, RunExpectancy, profile_summary, REGIONS, encode
from visualbaseball.zone_decision import reliable_halves, walk_state, fit_predict, EVENTS


def test_expected_policy_is_neutral_and_take_can_beat_called_strike():
 # Same offered pitch: averaging the two decisions using league p gives zero.
 p=np.array([.2,.7,.95]);vs=np.array([-.2,.1,.01]);vt=np.array([-.1,-.1,.009])
 swing=decision_value(1,p,vs,vt);take=decision_value(0,p,vs,vt)
 np.testing.assert_allclose(p*swing+(1-p)*take,0,atol=1e-15)
 assert take[0]>0 and swing[0]<0
 assert abs(take[2])<abs(take[1])


def test_five_regions_and_hbp_not_future_pa_result():
 assert [region({'x_relative':d,'z_relative':0}) for d in (.4,.9,1.2,1.8,2.2)]==list(REGIONS)
 assert outcome({'pitch_call_code':'B','pa_result':'사구','is_pa_terminal':False})=='Ball'
 assert outcome({'pitch_call_code':'B','pa_result':'사구','is_pa_terminal':True})=='HBP'


def test_additive_contributions_use_all_pitches():
 rows=[]
 for i,reg in enumerate(REGIONS):
  rows.append({'season':2026,'batter_id':'1','batter_name':'Test','game_id':'20260601OBLG0','inning_half':'top','region':reg,'dv':(i-2)/10,'swing':i%2,'p_swing':.4,'judgment':.1,'opposite_support':25})
 s=profile_summary(rows)
 assert abs(sum(s[r+'_decision_value_per_100'] for r in REGIONS)-s['za_raw'])<1e-5
 for reg in REGIONS:
  assert abs(s[reg+'_swing_decision_value_per_100']+s[reg+'_take_decision_value_per_100']-s[reg+'_decision_value_per_100'])<1e-5
 assert abs(s['swing_decision_value_per_100']+s['take_decision_value_per_100']-s['za_raw'])<1e-5


def test_target_events_are_not_model_features():
 row={'x_relative':.3,'z_relative':.1,'pitch_type':'FF','batter_stance':'R','stadium':'A','raw_run_value':9,'pa_result':'홈런','event':'InPlay','_runs_to_end':9}
 changed={**row,'raw_run_value':-8,'pa_result':'삼진','event':'Whiff','_runs_to_end':0}
 a,b=encode([row],[changed]);np.testing.assert_allclose(a,b,equal_nan=True)


def test_re_table_is_training_only_and_terminal_state_zero():
 row={'base_state_code_before':0,'outs_before':0,'balls_before':0,'strikes_before':0,'_runs_to_end':2}
 re=RunExpectancy([row]);row['_runs_to_end']=999
 assert re.value((0,0,0,0))==2
 assert re.value((7,3,0,0))==0
 assert np.isfinite(re.value((7,2,3,2)))


def test_score_repairs_are_not_fabricated_pitch_runs():
 common={'game_id':'20260401A','inning':1,'inning_half':'top','runs_on_pitch':0,
         'away_score_before':0,'away_score_after':0,'home_score_before':0,'home_score_after':0,'outs_after':0}
 rows=[{**common,'event_seq':1},{**common,'event_seq':3,'away_score_before':1,'away_score_after':1,'outs_after':3}]
 event={**common,'event_seq':2,'event_type':'runner','event_code':'known','parse_status':'ok',
        'runs_on_event':1,'away_score_after':1}
 accepted,quality=reliable_halves(rows,[event])
 assert [r['_runs_to_end'] for r in accepted]==[1,0]
 assert quality['included_timed_nonpitch_runs']==1
 assert all(r['runs_on_pitch']==0 for r in rows)
 repair={**event,'event_code':'OFFICIAL_LINESCORE_RECONCILIATION','parse_status':'source_limited'}
 rejected,quality=reliable_halves(rows,[repair])
 assert rejected==[] and quality['excluded_halves']==1 and quality['excluded_pitches']==2


def test_constrained_re_preserves_ordinary_baseball_transitions():
 rng=np.random.default_rng(42)
 rows=[{'base_state_code_before':b,'outs_before':o,'balls_before':ball,'strikes_before':strike,
        '_runs_to_end':float(rng.uniform(0,3))} for b in range(8) for o in range(3) for ball in range(4) for strike in range(3)]
 re=RunExpectancy(rows)
 for s in re.full:
  assert re.event_value(s,'Ball')>=-1e-7
  assert re.event_value(s,'HBP')>=-1e-7
  assert re.event_value(s,'CalledStrike')<=1e-7
  assert re.event_value(s,'Whiff')==re.event_value(s,'CalledStrike')
  if s[3]==2:assert re.event_value(s,'Foul')==0
 assert walk_state((5,1,3,2))==((7,1,0,0),0)
 assert walk_state((7,1,3,2))==((7,1,0,0),1)
 assert re.diagnostics['weighted_adjustment_rmse']>0


def test_actual_fitted_predictions_ignore_held_out_results():
 rng=np.random.default_rng(8);train=[]
 for i in range(720):
  event=EVENTS[i%6];balls=(i//6)%4;strikes=(i//24)%3
  ball=event=='Ball';strike=event in ('Whiff','CalledStrike')
  terminal=event in ('InPlay','HBP') or (ball and balls==3) or (strike and strikes==2)
  r={'game_id':f'202604{i//60+1:02d}A','batter_id':'1','batter_name':'Test','season':2026,'inning_half':'top',
    'event':event,'decision_type':'Swing' if i%6<3 else 'Take','region':'heart',
    'x_relative':float(rng.uniform(-1,1)),'z_relative':float(rng.uniform(-1,1)),
    'pitch_type':'FF','batter_stance':'R','stadium':'A','velocity_kmh':145,
    'base_state_code_before':0,'outs_before':0,'balls_before':balls,'strikes_before':strikes,
    'base_state_code_after':int(event=='HBP' or (ball and balls==3)),
    'outs_after':int(event=='InPlay' or (strike and strikes==2)),
    'balls_after':0 if terminal else balls+int(ball),
    'strikes_after':0 if terminal else min(2,strikes+int(strike or event=='Foul')),
    'runs_on_pitch':0,'_runs_to_end':float(1+balls*.1-strikes*.1)}
  train.append(r)
 test=[{**r,'game_id':'20260501A'} for r in train[:12]]
 changed=[{**r,'event':'InPlay','runs_on_pitch':99,'_runs_to_end':99,'outs_after':3} for r in test]
 first=fit_predict(train,test);second=fit_predict(train,changed)
 for name in ('p','probs','staged','direct'):
  np.testing.assert_allclose(first[name],second[name],atol=1e-12)
 assert not np.allclose(first['target'],second['target'])
 np.testing.assert_allclose(first['probs'][:,:3].sum(axis=1),1)
 np.testing.assert_allclose(first['probs'][:,3:].sum(axis=1),1)
