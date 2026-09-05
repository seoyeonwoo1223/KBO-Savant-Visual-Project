import numpy as np
from visualbaseball.zone_decision import decision_value, region, outcome, RunExpectancy, profile_summary, REGIONS, encode


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
