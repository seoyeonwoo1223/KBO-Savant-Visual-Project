"""저장 결과로 싱커 앵커·지원값 진단 그림을 만든다."""
import json
import os
import tempfile
from pathlib import Path

os.environ.setdefault("MPLCONFIGDIR",str(Path(tempfile.gettempdir())/"eaa-plot-cache"))
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from common import OUT


def save_figure(fig,name):
    for suffix in ["png","svg"]:
        path=OUT/(name+"."+suffix)
        kwargs={"metadata":{"Date":None}} if suffix=="svg" else {}
        fig.savefig(path,dpi=180,bbox_inches="tight",**kwargs)
        if suffix=="svg":path.write_text("\n".join(line.rstrip() for line in path.read_text().splitlines())+"\n")
    plt.close(fig)


def main():
    plt.rcParams.update({"font.size":10,"axes.spines.top":False,"axes.spines.right":False,"svg.fonttype":"none","svg.hashsalt":"eaa-sinker-support-20261007"})
    historical=json.loads((OUT/"MLB_OOF_reused_sinker_scores.json").read_text())
    monthly=json.loads((OUT/"MayJuly2025_reused_sinker_scores.json").read_text())
    rows=[(historical,"SI_geometry","Geometry: historical (115 pitchers)"),
          (historical,"SI_physics","Physics: historical (115)"),
          (monthly,"SI_geometry","Geometry: May/July (47)"),
          (monthly,"SI_physics","Physics: May/July (47)")]
    fig,axes=plt.subplots(1,2,figsize=(11.6,4.2),sharey=True)
    for ax,key,title in zip(axes,["MAE_gain","downside_gain"],["Absolute error gain","Negative error gain"]):
        for y,(score,model,label) in enumerate(rows):
            record=score["paired_vs_reference"][model]["all"][key]
            center=record["mean"];lo,hi=record["bootstrap95"]
            ax.errorbar(center,y,xerr=[[center-lo],[hi-center]],fmt="o" if model=="SI_physics" else "s",
                        color="#176b85" if model=="SI_physics" else "#c15c30",capsize=3)
        ax.axvline(0,color="#777",ls="--",lw=1)
        ax.set_title(title)
        ax.set_xlabel("Gain vs cohort reference (degrees)\nPositive = less error")
        ax.grid(axis="x",alpha=.18)
    axes[0].set_yticks(range(4),[r[2] for r in rows]);axes[0].invert_yaxis()
    fig.suptitle("Sinker-only anchors: error objectives and cohorts differ",y=1.04)
    fig.text(.01,-.06,"Historical reference: FF anchor OOF. Monthly reference: v1 MLB direct component. SI >=100 pitches.\nReused data; paired pitcher bootstrap 95%; high-slot SI protection unavailable.",fontsize=9)
    fig.tight_layout();save_figure(fig,"sinker_tradeoffs")

    support=json.loads((OUT/"MLB_OOF_reused_support_scores.json").read_text())
    groups=["FF","SI","matched_low_IVB","high60"]
    labels=["FF (747 pitchers)","SI (115)","Matched low IVB (454)","Observed >=60 deg (35)"]
    fig,axes=plt.subplots(1,2,figsize=(10.7,3.8),sharey=True)
    for ax,key,title in zip(axes,["MAE_gain","downside_gain"],["Absolute error gain","Negative error gain"]):
        for y,group in enumerate(groups):
            record=support["paired_vs_full"]["drop_support"][group][key]
            center=record["mean"];lo,hi=record["bootstrap95"]
            ax.errorbar(center,y,xerr=[[center-lo],[hi-center]],fmt="o",color="#176b85",capsize=3)
        ax.axvline(0,color="#777",ls="--",lw=1);ax.set_title(title)
        ax.set_xlabel("Gain after removing support vs full (degrees)");ax.grid(axis="x",alpha=.18)
    axes[0].set_yticks(range(4),labels);axes[0].invert_yaxis()
    fig.suptitle("Removing standalone support: small, uncertain group changes",y=1.04)
    fig.text(.01,-.04,"Reused MLB OOF. Same training scope; paired pitcher bootstrap 95%; other game support weighting retained.",fontsize=9)
    fig.tight_layout();save_figure(fig,"support_group_tradeoffs")

    k=pd.read_csv(OUT/"KBO_focus_support.csv",float_precision="round_trip").set_index("name")
    k=k.loc[["전준표","박준현","안우진","손주영","문동주"]]
    fig,ax=plt.subplots(figsize=(10.2,4.3))
    y=np.arange(5)
    ax.hlines(y,k.support_q10_delta_vs_anchor,k.support_q90_delta_vs_anchor,color="#b8b8b8",lw=5,label="Frozen full: support q10/q90 scenarios")
    ax.scatter(k.full_delta_vs_anchor,y-.11,color="#176b85",marker="o",s=48,label="Historical full delta")
    ax.scatter(k.drop_support_delta_vs_anchor,y+.11,color="#c15c30",marker="D",s=45,label="Support removed and refitted")
    ax.axvline(0,color="#777",ls="--",lw=1)
    ax.set_yticks(y,["Jeon Jun-pyo","Park Jun-hyun","An Woo-jin","Son Ju-young","Moon Dong-ju"])
    ax.invert_yaxis();ax.set_xlabel("Research candidate minus FF anchor (degrees)")
    ax.set_title("KBO focus: candidate response depends on sample support")
    ax.grid(axis="x",alpha=.18);ax.legend(loc="upper left",bbox_to_anchor=(1.02,1),frameon=False)
    fig.text(.01,-.05,"Gray bars: standalone input scenarios with other inputs fixed. Refit removal is a separate comparison.\nNo KBO accuracy labels; support is a game x pitch-type count summary.",fontsize=9)
    fig.tight_layout();save_figure(fig,"KBO_support_response")
    print("FIGURES_SAVED",3)


if __name__=="__main__":main()
