import numpy as np
from visualbaseball.zone_decision import decision_value, region, outcome, RunExpectancy, profile_summary, REGIONS, encode
from visualbaseball.zone_decision import reliable_halves, walk_state, fit_predict, zone_awareness, value_based_zone_awareness, add_dv_plus, EVENTS
from visualbaseball.zone_decision import strikezone_ball_judgment, expected_judgment_accuracy, add_sbj_plus
from visualbaseball.zone_decision import seager_quadrants, selection_tendency, hittable_take_rate, approach_rating, add_apr_plus


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
 base={'season':2026,'batter_name':'Test','team':'T','game_id':'20260601A','region':'heart','opposite_support':50,'delta_v':.2,'p_zone':.7,'p_CalledStrike':.7,'p_Ball':.3,'p_HBP':.0,'judgment':.1}
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
  rows.append({'season':2026,'batter_id':'1','batter_name':'Test','game_id':'20260601OBLG0','inning_half':'top','region':reg,'dv':(i-2)/10,'delta_v':(i-2)/10 or .1,'swing':i%2,'p_swing':.4,'p_zone':.6,'p_CalledStrike':.6,'p_Ball':.4,'p_HBP':.0,'judgment':.1,'opposite_support':25})
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


def _judgment_row(swing, p_swing, p_zone, p_cs=None, p_hbp=.0):
 # p_cs defaults to p_zone only so older DV fixtures keep their shape; SBJ reads p_cs.
 p_cs=p_zone if p_cs is None else p_cs
 return {'swing':swing,'p_swing':p_swing,'p_zone':p_zone,
   'p_CalledStrike':p_cs,'p_HBP':p_hbp,'p_Ball':1-p_cs-p_hbp,
   'judgment':(swing-p_swing)*(2*p_zone-1)}


def test_sbj_credits_called_strike_chance_on_swings_and_ball_chance_on_takes():
 # PLV Strikezone Judgement: swing -> p_CalledStrike, take -> p_Ball + p_HBP.
 items=[_judgment_row(1,.4,.5,p_cs=.9),_judgment_row(0,.3,.5,p_cs=.2,p_hbp=.05)]
 assert strikezone_ball_judgment(items)==round(100*np.mean([.9,.75+.05]),6)


def test_sbj_follows_the_full_call_model_not_the_positional_one():
 # p_zone is also a called-strike model, but a four-feature positional one.
 # Hold it fixed and move the full call model: SBJ must react, za_raw must not.
 base=[_judgment_row(1,.4,.6,p_cs=.6),_judgment_row(1,.4,.6,p_cs=.6)]
 shifted=[{**r,'p_CalledStrike':.2,'p_Ball':.8} for r in base]
 assert strikezone_ball_judgment(shifted)!=strikezone_ball_judgment(base)
 assert zone_awareness(shifted)==zone_awareness(base)


def test_sbj_no_longer_collapses_onto_zone_awareness():
 # Subtracting the league baseline is what produced the za_raw identity; SBJ does not.
 rng=np.random.default_rng(11)
 items=[_judgment_row(int(rng.integers(0,2)),float(rng.uniform(.05,.95)),
   float(rng.uniform(.05,.95)),p_cs=float(rng.uniform(.05,.95))) for _ in range(60)]
 assert strikezone_ball_judgment(items)!=zone_awareness(items)
 observed=strikezone_ball_judgment(items)
 assert 0<=observed<=100


def test_sbj_is_outcome_independent_like_zone_awareness():
 items=[{**_judgment_row(1,.4,.8,p_cs=.8),'delta_v':.4,'raw_run_value':2},
        {**_judgment_row(0,.3,.2,p_cs=.2),'delta_v':-.2,'raw_run_value':-1}]
 changed=[{**r,'delta_v':-99*r['delta_v'],'raw_run_value':999} for r in items]
 assert strikezone_ball_judgment(changed)==strikezone_ball_judgment(items)


def test_expected_judgment_is_a_diagnostic_not_subtracted_from_sbj():
 items=[_judgment_row(1,.4,.5,p_cs=.9),_judgment_row(0,.3,.5,p_cs=.2)]
 assert expected_judgment_accuracy(items)==round(100*np.mean(
   [.4*.9+.6*.1, .3*.2+.7*.8]),6)
 assert strikezone_ball_judgment(items)!=round(
   strikezone_ball_judgment(items)-expected_judgment_accuracy(items),6)


def test_sbj_plus_is_standardized_over_qualified_hitters():
 players=[]
 for i in range(4):
  rows=_apr_rows(str(i),{r:(80,1,.4,.5) for r in REGIONS},p_cs=.5+.1*i)
  players.append(profile_summary(rows))
 center,spread=add_sbj_plus(players)
 assert all(p['qualified_300'] for p in players)
 for p in players:
  assert abs(p['sbj_plus']-(100+15*(p['sbj_raw']-center)/spread))<1e-5


def _apr_rows(batter_id, per_region, p_cs=None):
 rows=[]
 for reg,(count,swing,p_swing,p_zone) in per_region.items():
  for i in range(count):
   rows.append({'season':2026,'batter_id':batter_id,'batter_name':'T'+batter_id,'team':'T','game_id':'20260601OBLG0',
     'region':reg,'dv':.0,'delta_v':.1,'opposite_support':50,
     **_judgment_row(swing,p_swing,p_zone,p_cs=p_cs)})
 return rows


def _decision(swing, delta_v):
 return {'season':2026,'batter_id':'1','batter_name':'T','team':'T','game_id':'20260601OBLG0',
   'region':'heart','dv':.0,'delta_v':delta_v,'opposite_support':50,
   **_judgment_row(swing,.4,.6,p_cs=.6)}


def test_seager_quadrants_partition_every_pitch():
 rows=[_decision(1,.2),_decision(1,-.2),_decision(0,.2),_decision(0,-.2),_decision(0,0.)]
 counts=seager_quadrants(rows)
 assert counts=={'A':1,'B':1,'C':1,'D':2}          # delta_v == 0 is non-hittable
 assert sum(counts.values())==len(rows)


def test_seager_uses_run_value_not_zone_membership():
 # Same location and zone probability, opposite delta_v sign.
 hittable=[_decision(1,.2)]; avoidable=[{**_decision(1,-.2)}]
 assert seager_quadrants(hittable)=={'A':1,'B':0,'C':0,'D':0}
 assert seager_quadrants(avoidable)=={'A':0,'B':1,'C':0,'D':0}


def test_selection_tendency_and_hittable_takes_follow_the_repo_formula():
 counts={'A':3,'B':7,'C':2,'D':6}
 assert selection_tendency(counts)==round(100*6/(3+6),6)
 assert hittable_take_rate(counts)==round(100*2/(2+6),6)
 assert approach_rating(counts)==round(selection_tendency(counts)-hittable_take_rate(counts),6)


def test_apr_direction_rewards_taking_bad_pitches_and_punishes_passing_good_ones():
 base={'A':5,'B':5,'C':5,'D':5}
 # Taking a non-hittable pitch raises selection tendency -> APR up.
 assert approach_rating({**base,'D':base['D']+5})>approach_rating(base)
 # Passing on a hittable pitch raises hittable-take rate -> APR down.
 assert approach_rating({**base,'C':base['C']+5})<approach_rating(base)
 # Swinging at a non-hittable pitch enters B, which neither ratio uses.
 assert approach_rating({**base,'B':base['B']+5})==approach_rating(base)


def test_apr_is_none_when_a_ratio_has_no_denominator():
 assert approach_rating({'A':0,'B':4,'C':0,'D':0}) is None
 assert selection_tendency({'A':0,'B':4,'C':0,'D':0}) is None


def test_apr_plus_is_standardized_over_qualified_hitters():
 players=[]
 for i in range(4):
  rows=[_decision(1,.2) for _ in range(60+10*i)]+[_decision(0,-.2) for _ in range(240-10*i)]
  for r in rows: r['batter_id']=str(i); r['batter_name']='T'+str(i)
  players.append(profile_summary(rows))
 center,spread=add_apr_plus(players)
 assert all(p['qualified_300'] for p in players)
 for p in players:
  assert abs(p['apr_plus']-(100+15*(p['apr_raw']-center)/spread))<1e-5


def test_profile_summary_exposes_seager_quadrants_summing_to_pitches_seen():
 rows=[_decision(1,.2),_decision(1,-.2),_decision(0,.2),_decision(0,-.2)]
 s=profile_summary(rows)
 assert s['seager_a']+s['seager_b']+s['seager_c']+s['seager_d']==s['pitches_seen']
 assert s['apr_raw']==round(s['selection_tendency_pct']-s['hittable_take_pct'],6)


def test_plus_scores_are_withheld_below_the_qualification_minimum():
 # + scores are standardized on the qualified distribution, so extending them
 # to small samples would inflate sampling error onto a 15-point scale.
 qualified=[]
 for i in range(4):
  rows=[_decision(1,.2) for _ in range(60+10*i)]+[_decision(0,-.2) for _ in range(240-10*i)]
  for r in rows: r['batter_id']=str(i)
  qualified.append(profile_summary(rows))
 small=[_decision(1,.2) for _ in range(10)]
 for r in small: r['batter_id']='tiny'
 players=qualified+[profile_summary(small)]
 add_sbj_plus(players); add_apr_plus(players); add_dv_plus(players)
 tiny=players[-1]
 assert tiny['qualified_300'] is False
 assert tiny['sbj_plus'] is None and tiny['apr_plus'] is None and tiny['dv_plus'] is None
 # Raw components stay available for diagnostics.
 assert tiny['sbj_raw'] is not None and tiny['pitches_seen']==10
 assert all(p['sbj_plus'] is not None for p in qualified)
