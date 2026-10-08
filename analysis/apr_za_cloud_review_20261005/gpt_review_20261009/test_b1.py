"""평균 공동 추정과 중복 경기 복원의 독립 검산."""
import numpy as np
from run_b1 import estimate, bootstrap_stats, sizes

def test_weight_derivative_matches_joint_if():
    r=np.array([.3,-.2,.8,-.4]);d=np.array([.1,.5,-.3,.6]);c=np.mean((r-r.mean())*(d-d.mean()));psi=200*((r-r.mean())*(d-d.mean())-c)
    for i in range(len(r)):
        w=np.ones(len(r),complex);w[i]+=1e-20j;w/=w.sum()
        val=200*(np.sum(w*r*d)-np.sum(w*r)*np.sum(w*d))
        assert abs(val.imag/1e-20*len(r)-psi[i])<1e-10

def test_constants_and_shifts():
    r=np.array([.3,-.2,.8,-.4]);d=np.array([.1,.5,-.3,.6]);n=np.array([2,2])
    np.testing.assert_allclose(estimate(r,d,n),estimate(r+3,d-2,n),atol=1e-10)
    for rr,dd in [(np.full(4,.5),d),(r,np.full(4,2.))]:
        np.testing.assert_allclose(estimate(rr,dd,n),(0,0),atol=1e-10)

def test_duplicate_games_are_independent_replicas():
    r=np.array([.3,-.2,.8,-.4]);d=np.array([.1,.5,-.3,.6]);a=np.array([[2,r[:2].sum(),d[:2].sum(),(r[:2]*d[:2]).sum()],[2,r[2:].sum(),d[2:].sum(),(r[2:]*d[2:]).sum()]])
    k=np.array([[2,1]]);bb,ss=bootstrap_stats(a,k)
    direct=estimate(np.r_[r[:2],r[:2],r[2:]],np.r_[d[:2],d[:2],d[2:]],np.array([2,2,2]))
    np.testing.assert_allclose([bb[0],ss[0]],direct,atol=1e-10)

def test_sizes_keep_fixed_total():
    for n in [100,300,1000]:
        for unequal in [False,True]:
            v=sizes(n,unequal);assert len(v)==n//10 and v.sum()==n and (v>0).all()
