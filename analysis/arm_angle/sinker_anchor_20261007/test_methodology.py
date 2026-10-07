"""지원 조건·예측 라벨 차단·상수 대조에 실제로 실패할 수 있는 검사."""
import sys
import pickle
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0,str(Path(__file__).resolve().parent))
from common import OUT, SI_PHYSICS, eligible_si
import run_sinker
import run_support


def test_SI100_support_and_missing_features_are_not_filled_to_qualify():
    d=pd.DataFrame({c:[1.,1.,1.] for c in SI_PHYSICS})
    d["primary4"]=["SI","SI","SI"];d["type_SI_count"]=[100,99,100];d["n"]=[200,200,200]
    d.loc[2,"type_SI_ivb_in"]=np.nan
    assert eligible_si(d).tolist()==[True,False,False]


def test_arm_angle_cannot_enter_either_prediction_function():
    d=pd.DataFrame({"arm_angle":[40.]})
    with pytest.raises(AssertionError):run_sinker.predict(None,d,SI_PHYSICS)
    with pytest.raises(AssertionError):run_support.predict(None,d)


def test_constant_support_is_projected_out_in_every_fitted_model():
    with (OUT/"support_models.pkl").open("rb") as f:models=pickle.load(f)
    for variants in list(models["outer"].values())+[models["fixed"]]:
        model=variants["constant_support"]
        position=model["indices"].index(run_support.SUPPORT)
        assert not model["projection"]["keep"][position]
        assert run_support.SUPPORT not in variants["drop_support"]["indices"]


def test_support_quantile_scenario_matches_exact_full_model_when_input_already_constant():
    from common import legacy_helpers,load
    run_support.RIDGE_FIT,run_support.WEIGHTS,run_support.BASE,run_support.FIT_PROJECTION,run_support.APPLY_PROJECTION=legacy_helpers()
    with (OUT/"support_models.pkl").open("rb") as f:model=pickle.load(f)["fixed"]["full"]
    d=load("KBO_FF100").iloc[:5].copy()
    d["game_pair_support"]=model["quantiles"]["support_q50"]
    p=run_support.predict(model,d)[0]
    np.testing.assert_array_equal(p,run_support.predict(model,d,"support_q50")[0])
