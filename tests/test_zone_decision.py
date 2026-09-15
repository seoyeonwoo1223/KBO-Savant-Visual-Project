import numpy as np
from visualbaseball.zone_decision import decision_value, region, outcome, RunExpectancy, profile_summary, REGIONS, encode
from visualbaseball.zone_decision import reliable_halves, walk_state, fit_predict, zone_awareness, value_based_zone_awareness, add_dv_plus, EVENTS
from visualbaseball.zone_decision import strikezone_ball_judgment, judgment_accuracy, expected_judgment_accuracy
from visualbaseball.zone_decision import region_weights, add_apr_plus


def test_decision_value_credits_the_actual_choice():
 vs=np.array([-.2,.1,.01]);vt=np.array([-.1,-.1,.009])
 swing=decision_value(1,vs,vt);take=decision_value(0,vs,vt)
 np.testing.assert_allclose(swing,vs-vt)
 np.testing.assert_allclose(take,vt-vs)
 assert take[0]>0 and swing[0]<0


def test_zone_awareness_is_outcome_independent_and_value_version_is_retained():
 items=[{'swing':1,'p_swing':.4,'p_zone':.8,'judgment':.36,'delta_v':.4,'raw_run_value':2},
        {'swing':0,'p_swing':.3,'p_zone':.2,'judgment':.18,'delta_v':-.2,'raw_run_value':-1}]
 assert zone_awareness(items)==27
 changed=[{**r,'delta_v':-99*r['delta_v'],'raw_run_value':999} for r in items]
 assert zone_awareness(changed)==zone_awareness(items)
 assert value_based_zone_awareness(changed)!=value_based_zone_awareness(items)


def test_sa_dv_stay_unchanged_and_dv_plus_is_standardized():
 base={'season':2026,'batter_name':'Test','team':'T','game_id':'20260601A','region':'heart','opposite_support':50,'delta_v':.2,'p_zone':.7,'judgment':.1}
 rows=[{**base,'batter_id':'1','swing':1,'p_swing':.4,'dv':.2},{**base,'batter_id':'1','swing':0,'p_swing':.4,'dv':-.1}]
 summary=profile_summary(rows)
 assert summary['swing_aggression']==10 and summary['raw_dv']==.1 and summary['dv_per_100']==5
 players=[{'qualified_300':True,'dv_per_100':v} for v in (-2,0,4,8)]
 add_dv_plus(players);values=np.array([p['dv_plus'] for p in players])
 assert abs(values.mean()-100)<1e-6 and abs(values.std()-15)<1e-6


def test_five_regions_and_hbp_not_future_pa_result():
 assert [region({'x_relative':d,'z_relative':0}) for d in (.4,.9,1.2,1.8,2.2)]==list(REGIONS)
 assert outcome({'pitch_call_code':'B','pa_result':'사구','is_pa_terminal':False})=='Ball'
 assert outcome({'pitch_call_code':'B','pa_result':'사구','is_pa_terminal':True})=='HBP'


def test_additive_contributions_use_all_pitches():
 rows=[]
 for i,reg in enumerate(REGIONS):
  rows.append({'season':2026,'batter_id':'1','batter_name':'Test','game_id':'20260601OBLG0','inning_half':'top','region':reg,'dv':(i-2)/10,'delta_v':(i-2)/10 or .1,'swing':i%2,'p_swing':.4,'p_zone':.6,'judgment':.1,'opposite_support':25})
 s=profile_summary(rows)
 assert abs(sum(s[r+'_decision_value_per_100'] for r in REGIONS)-s['dv_per_100'])<1e-5
 for reg in REGIONS:
  assert abs(s[reg+'_swing_decision_value_per_100']+s[reg+'_take_decision_value_per_100']-s[reg+'_decision_value_per_100'])<1e-5
 assert abs(s['swing_decision_value_per_100']+s['take_decision_value_per_100']-s['dv_per_100'])<1e-5


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


def _judgment_row(swing, p_swing, p_zone):
 return {'swing':swing,'p_swing':p_swing,'p_zone':p_zone,
   'judgment':(swing-p_swing)*(2*p_zone-1)}


def test_sbj_is_observed_minus_expected_judgment_accuracy():
 items=[_judgment_row(1,.4,.8),_judgment_row(0,.3,.2)]
 # Observed: swing credited p_zone, take credited 1 - p_zone.
 assert judgment_accuracy(items)==100*np.mean([.8,.8])
 # Expected: the same accuracy for a league-average swing policy.
 assert expected_judgment_accuracy(items)==100*np.mean([.4*.8+.6*.2,.3*.2+.7*.8])
 assert strikezone_ball_judgment(items)==round(judgment_accuracy(items)-expected_judgment_accuracy(items),6)


def test_sbj_equals_zone_awareness_and_is_not_independent_evidence():
 # SBJ reduces to (S - p_swing) * (2*p_zone - 1), so it must track za_raw exactly.
 rng=np.random.default_rng(11)
 for _ in range(20):
  items=[_judgment_row(int(rng.integers(0,2)),float(rng.uniform(.05,.95)),float(rng.uniform(.05,.95)))
    for _ in range(rng.integers(5,60))]
  assert strikezone_ball_judgment(items)==zone_awareness(items)


def test_sbj_is_outcome_independent_like_zone_awareness():
 items=[{**_judgment_row(1,.4,.8),'delta_v':.4,'raw_run_value':2},
        {**_judgment_row(0,.3,.2),'delta_v':-.2,'raw_run_value':-1}]
 changed=[{**r,'delta_v':-99*r['delta_v'],'raw_run_value':999} for r in items]
 assert strikezone_ball_judgment(changed)==strikezone_ball_judgment(items)


def _apr_rows(batter_id, per_region):
 rows=[]
 for reg,(count,swing,p_swing,p_zone) in per_region.items():
  for i in range(count):
   rows.append({'season':2026,'batter_id':batter_id,'batter_name':'T'+batter_id,'team':'T','game_id':'20260601OBLG0',
     'region':reg,'dv':.0,'delta_v':.1,'opposite_support':50,
     **_judgment_row(swing,p_swing,p_zone)})
 return rows


def test_apr_uses_league_region_weights_not_the_hitters_own_mix():
 # Same per-region judgment, different region mix: SBJ differs, APR does not.
 shape={'heart':(1,.4,.6),'shadow_in':(1,.4,.6),'shadow_out':(1,.4,.6),'chase':(1,.4,.6),'waste':(1,.4,.6)}
 a=_apr_rows('1',{r:(40 if r=='heart' else 10,*v) for r,v in shape.items()})
 b=_apr_rows('2',{r:(10 if r=='heart' else 40,*v) for r,v in shape.items()})
 players=[profile_summary(a),profile_summary(b)]
 weights=region_weights(players)
 assert abs(sum(weights.values())-1)<1e-12
 add_apr_plus(players,weights)
 # Every region carries the same SBJ here, so APR must agree across the two mixes.
 assert players[0]['apr_raw']==players[1]['apr_raw']


def test_apr_differs_from_sbj_when_region_judgment_varies():
 # Good in the heart, poor on the edges, and a heart-heavy personal mix.
 rows=_apr_rows('1',{'heart':(60,1,.3,.9),'shadow_in':(10,1,.7,.2),'shadow_out':(10,1,.7,.2),
   'chase':(10,1,.7,.2),'waste':(10,1,.7,.2)})
 other=_apr_rows('2',{r:(20,1,.5,.5) for r in REGIONS})
 players=[profile_summary(rows),profile_summary(other)]
 add_apr_plus(players,region_weights(players))
 # League weights down-weight the hitter's oversized heart share, so APR < SBJ.
 assert players[0]['apr_raw']!=players[0]['sbj']
 assert players[0]['apr_raw']<players[0]['sbj']


def test_apr_renormalizes_over_regions_the_hitter_saw():
 seen=_apr_rows('1',{'heart':(20,1,.4,.7),'shadow_in':(20,1,.4,.7)})
 full=_apr_rows('2',{r:(20,1,.4,.7) for r in REGIONS})
 players=[profile_summary(seen),profile_summary(full)]
 add_apr_plus(players,region_weights(players))
 # Unseen regions are dropped, not scored as zero, so equal judgment gives equal APR.
 assert players[0]['apr_raw'] is not None
 assert abs(players[0]['apr_raw']-players[1]['apr_raw'])<1e-6


def test_apr_plus_is_standardized_over_qualified_hitters():
 players=[]
 for i in range(4):
  rows=_apr_rows(str(i),{r:(80,1,.4,.5+.08*i) for r in REGIONS})
  players.append(profile_summary(rows))
 center,spread=add_apr_plus(players,region_weights(players))
 assert all(p['qualified_300'] for p in players)
 for p in players:
  assert abs(p['apr_plus']-(100+15*(p['apr_raw']-center)/spread))<1e-5
