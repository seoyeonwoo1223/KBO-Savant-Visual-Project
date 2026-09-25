import inspect
import numpy as np
from visualbaseball.zone_decision import decision_value, region, outcome, RunExpectancy, profile_summary, REGIONS, encode
from visualbaseball.zone_decision import reliable_halves, walk_state, fit_predict, zone_awareness, value_based_zone_awareness, add_dv_plus, EVENTS
from visualbaseball.zone_decision import cell_summary, judgment_plane_location, pzone_fields, PZONE_ABS, pitcher_throws
from visualbaseball.curated import CM_PER_FOOT, _at_plane
from visualbaseball import plate_decision_v1 as old


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
  rows.append({'season':2026,'batter_id':'1','batter_name':'Test','game_id':'20260601OBLG0','inning_half':'top','region':reg,'dv':(i-2)/10,'delta_v':(i-2)/10 or .1,'swing':i%2,'p_swing':.4,'judgment':.1,'opposite_support':25})
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


def _decision_rows():
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
 return train


def test_actual_fitted_predictions_ignore_held_out_results():
 train=_decision_rows()
 test=[{**r,'game_id':'20260501A'} for r in train[:12]]
 changed=[{**r,'event':'InPlay','runs_on_pitch':99,'_runs_to_end':99,'outs_after':3} for r in test]
 first=fit_predict(train,test);second=fit_predict(train,changed)
 for name in ('p','probs','staged','direct'):
  np.testing.assert_allclose(first[name],second[name],atol=1e-12)
 assert not np.allclose(first['target'],second['target'])
 np.testing.assert_allclose(first['probs'][:,:3].sum(axis=1),1)
 np.testing.assert_allclose(first['probs'][:,3:].sum(axis=1),1)


def test_official_sbj_is_za_raw_not_a_second_formula():
 # SBJ ranks by za_raw; raw accuracy minus league-policy accuracy is that same number.
 rng=np.random.default_rng(5)
 items=[]
 for _ in range(200):
  swing,p_swing,p_zone=int(rng.integers(0,2)),float(rng.uniform(.05,.95)),float(rng.uniform(.05,.95))
  items.append({'swing':swing,'p_swing':p_swing,'p_zone':p_zone,'judgment':(swing-p_swing)*(2*p_zone-1),'opposite_support':50,'dv':0.,'delta_v':0.,'v_swing':0.,'v_take':0.,**{f'p_{e}':0. for e in EVENTS}})
 s=cell_summary(items)
 assert abs(s['zone_judgment_pct']-s['expected_zone_judgment_pct']-s['za_raw'])<1e-5


def _pitch(**changes):
 # Falling pitch released at 50 ft; y is feet from the back tip of home plate. Unless given,
 # px/pz are where VB reports them in ABS seasons: x at the middle plane, z at the front plane.
 row={'x0':-1.8,'y0':50.,'z0':5.8,'vx0':5.,'vy0':-128.,'vz0':-4.,'ax':-9.,'ay':26.,'az':-18.,
      'sz_top':3.4,'sz_bottom':1.6,'trajectory_valid':True}
 row.update(changes)
 if 'px' not in changes and _at_plane(row,8.5/12): row['px']=_at_plane(row,8.5/12)[0]/CM_PER_FOOT
 if 'pz' not in changes and _at_plane(row,17/12): row['pz']=_at_plane(row,17/12)[1]/CM_PER_FOOT
 return row


def test_abs_plane_inputs_use_middle_x_and_both_height_planes():
 row=_pitch();mid,back=_at_plane(row,8.5/12),_at_plane(row,0.)
 got=judgment_plane_location(row)
 assert not got['plane_fallback']
 assert abs(got['x_mid_relative']-mid[0]/CM_PER_FOOT/(10/12))<1e-9
 # Falling: the middle plane is higher, so it limits the top; the back plane limits the bottom.
 assert mid[1]>back[1]
 assert abs(got['top_gap_cm']-(mid[1]-3.4*CM_PER_FOOT))<1e-9
 assert abs(got['bottom_gap_cm']-(back[1]-1.6*CM_PER_FOOT))<1e-9
 rising=_pitch(az=40.)
 mid,back=_at_plane(rising,8.5/12),_at_plane(rising,0.);got=judgment_plane_location(rising)
 assert back[1]>mid[1]
 assert abs(got['top_gap_cm']-(back[1]-3.4*CM_PER_FOOT))<1e-9
 assert abs(got['bottom_gap_cm']-(mid[1]-1.6*CM_PER_FOOT))<1e-9


def test_invalid_trajectory_falls_back_to_front_plane_location():
 for row in (_pitch(trajectory_valid=False,px=.4,pz=2.3),_pitch(vy0=None,px=.4,pz=2.3)):
  got=judgment_plane_location(row)
  assert got['plane_fallback']
  assert abs(got['x_mid_relative']-.4/(10/12))<1e-9
  assert abs(got['top_gap_cm']-(2.3-3.4)*CM_PER_FOOT)<1e-9
  assert abs(got['bottom_gap_cm']-(2.3-1.6)*CM_PER_FOOT)<1e-9


def test_only_abs_seasons_read_judgment_planes():
 assert pzone_fields(2023)==old.PZONE_NUMERIC
 # Legacy human-umpire builds call predict_pzone without fields and keep the four front-plane inputs.
 assert inspect.signature(old.predict_pzone).parameters['fields'].default==old.PZONE_NUMERIC
 assert all(pzone_fields(season)==PZONE_ABS for season in (2024,2025,2026))


def test_pitcher_hand_comes_from_player_bio_then_release_side():
 hands={'1':'L','2':''}
 assert pitcher_throws({'pitcher_id':'1','release_x_50':-60.},hands)=='L'
 # Catcher view: a left-hander releases on the positive x side.
 assert pitcher_throws({'pitcher_id':'2','release_x_50':55.},hands)=='L'
 assert pitcher_throws({'pitcher_id':'3','release_x_50':-55.},hands)=='R'
 assert pitcher_throws({'pitcher_id':'3','release_x_50':None},hands)==''


def test_only_swing_propensity_reads_pitcher_hand():
 train=_decision_rows()
 for r in train: r['pitcher_throws']='R' if r['decision_type']=='Swing' else 'L'
 test=[{**r,'game_id':'20260501A'} for r in train[:12]]
 flipped=[{**r,'pitcher_throws':'L' if r['pitcher_throws']=='R' else 'R'} for r in test]
 first=fit_predict(train,test,calibration=False);second=fit_predict(train,flipped,calibration=False)
 assert not np.allclose(first['raw_p'],second['raw_p'])
 # Event and value models keep old.CATEGORICAL, so Decision Value inputs do not move.
 for name in ('probs','staged','direct'):
  np.testing.assert_allclose(first[name],second[name],atol=1e-12)


def test_trajectory_component_that_misses_reported_location_is_replaced():
 good=judgment_plane_location(_pitch())
 assert not (good['plane_x_replaced'] or good['plane_z_replaced'])
 # x fit misses px (2025 tracking glitch pattern: x off by metres, z intact) -> x from px only.
 row=_pitch(); row['px']+=0.5
 got=judgment_plane_location(row)
 assert got['plane_x_replaced'] and not got['plane_z_replaced'] and not got['plane_fallback']
 assert abs(got['x_mid_relative']-row['px']/(10/12))<1e-9
 assert got['top_gap_cm']==good['top_gap_cm'] and got['bottom_gap_cm']==good['bottom_gap_cm']
 # A 0.5 cm disagreement is rounding (px/pz carry 0.01 ft), not a broken fit.
 near=_pitch(); near['px']+=0.5/CM_PER_FOOT
 assert not judgment_plane_location(near)['plane_x_replaced']
 # z fit misses pz -> both heights from pz, x still from the trajectory.
 row=_pitch(); row['pz']+=0.2
 got=judgment_plane_location(row)
 assert got['plane_z_replaced'] and not got['plane_x_replaced']
 assert abs(got['top_gap_cm']-(row['pz']-3.4)*CM_PER_FOOT)<1e-9 and abs(got['bottom_gap_cm']-(row['pz']-1.6)*CM_PER_FOOT)<1e-9
 assert got['x_mid_relative']==good['x_mid_relative']
