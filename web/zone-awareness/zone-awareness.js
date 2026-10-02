// APR (wRC+-style decision value) leads; ZA (formerly SBJ) is the zone-only judgment score. za7.6, published from 2019.
// Before the 2024 ABS season p_zone learns the umpire's calls, not the ABS planes.
const SBJ_FIRST_SEASON=2019,ABS_FIRST_SEASON=2024;
const $ = (selector) => document.querySelector(selector);
const thumbnailMode = new URLSearchParams(location.search).get("thumb") === "1";
const state = { season: null, players: [], sort: "apr_percentile", direction: -1, selected: null, profile: null, cell: null };
const fields = ["swing_pct","expected_swing_pct","p_zone_pct","zone_judgment_pct","expected_zone_judgment_pct","za_raw","expected_swing_rv","expected_take_rv"];
const fmt = (value, digits=1) => value == null || !Number.isFinite(+value) ? "—" : (+value).toFixed(digits);
const signed = (value, digits=1) => value == null || !Number.isFinite(+value) ? "—" : `${+value>0?"+":""}${(+value).toFixed(digits)}`;
const signClass = value => +value >= 0 ? "good" : "bad";

function canvasContext(canvas) {
  const rect = canvas.getBoundingClientRect();
  const width = Math.max(320, rect.width || canvas.width), height = thumbnailMode && canvas.id === "scatter" ? (rect.height || width) : width / (canvas.width / canvas.height);
  const dpr = Math.min(window.devicePixelRatio || 1, 2);
  canvas.width = width * dpr; canvas.height = height * dpr;
  const ctx = canvas.getContext("2d"); ctx.scale(dpr, dpr);
  return {ctx, width, height};
}

function mix(a,b,t){return a.map((v,i)=>Math.round(v+(b[i]-v)*t));}
function diverge(value, scale=1) {
  if (!Number.isFinite(+value)) return "#e7e8e5";
  const neutral=[222,226,227], target=+value>=0?[217,74,86]:[70,120,184];
  const rgb=mix(neutral,target,Math.min(1,Math.abs(+value)/scale));
  return `rgb(${rgb.join(",")})`;
}
// Scatter only: same poles, grey midpoint so league-average hitters stay visible on the light canvas.
// Full-cell percentile fill in the Leaderboards WAR palette: white at the 50th percentile, red toward 100, blue toward 0.
function pctStyle(value){if(!Number.isFinite(+value))return "";const t=Math.min(1,Math.abs(+value-50)/50),rgb=mix([255,255,255],+value>=50?[216,73,81]:[58,102,169],t);return `--pct-color:rgb(${rgb.join(",")})`;}
function scatterColor(value){if(!Number.isFinite(+value))return "#aab3b6";const t=Math.min(1,Math.abs(+value-50)/50),rgb=mix([170,179,182],+value>=50?[217,74,86]:[70,120,184],t);return `rgb(${rgb.join(",")})`;}

async function loadSeason(season) {
  state.season=+season; state.profile=null; state.cell=null;
  const [data, teamData]=await Promise.all([
    fetch(`../data/zone_awareness/${season}/leaderboard.json`).then(r=>r.json()),
    fetch(`../data/zone_awareness/${season}/teams.json`).then(r=>r.ok?r.json():{teams:{}}),
  ]);
  state.modern=data.schema_version>=4;
  $("#season-method").textContent=state.modern ? `이벤트 확률은 Swing·Take 각각의 조건부 확률입니다. 채택 모델: ${data.selected_value_model==="staged"?"이벤트 분해":"직접 행동 가치"}.` : "이 시즌은 개편 전 지표입니다. ZA는 존 판단, 누적 가치는 기존 DV 산식이며 2024–2026과 직접 비교할 수 없습니다.";
  if(data.schema_version>=5){
    const q=data.data_quality;
    $("#season-method").textContent=`APR·ZA · 득점 시점을 확정할 수 없는 ${q.excluded_halves.toLocaleString()}개 공격 이닝, ${q.excluded_pitches.toLocaleString()}구를 제외했습니다. 비투구 사건의 확인된 ${fmt(q.included_timed_nonpitch_runs,0)}득점은 이닝 잔여 득점에 반영했습니다. 일반 볼·스트라이크·파울은 규칙에 따른 상태 전이로 계산하고, 스윙 표본이 적으면 더 넓은 조건의 결과 분포를 함께 사용합니다. 순위는 추정값의 순서이며 선수 간 우열이 확정되었다는 뜻은 아닙니다.`+(state.season<ABS_FIRST_SEASON?` ${state.season}년은 ABS 도입 전이라 스트라이크 확률을 구심 판정으로 학습했고, 구심의 존이 카운트에 따라 달라지므로 볼·스트라이크 카운트를 함께 반영했습니다. 판정 기준이 달라 2024년 이후 ZA와 직접 비교할 수 없습니다.${state.season<2022?' 이 시즌은 구장 보정표가 없어 스윙 기대치의 무브먼트에 TrackMan으로 검증한 구장·날짜 보정(Pitch Plot과 같은 방식)을 썼습니다.':''}`:'');
  }
  data.players.forEach(player=>{player.team=teamData.teams?.[player.batter_id]||player.team||"—";});
  // Savant-style: every hitter has an APR percentile against qualified hitters; ranks and the chart use qualified hitters only.
  state.allPlayers=data.players; state.players=data.players.filter(p=>p.qualified_300);
  [...state.players].sort((a,b)=>b.apr-a.apr).forEach((p,i)=>p.rank=i+1);
  $("#qualified-count").textContent=`${data.qualified_batters}명 · 300구 이상`;
  renderLeaderboard(); drawScatter();
  const params=new URLSearchParams(location.search), requested=params.get("player");
  const player=state.allPlayers.find(p=>p.batter_id===requested) || [...state.players].sort((a,b)=>b.apr_percentile-a.apr_percentile)[0];
  if(player) await selectPlayer(player.batter_id, false);
  const target = $("[data-thumbnail-target]");
  if (target) target.dataset.thumbnailReady = "true";
}

function renderLeaderboard(){
  const query=$("#player-search").value.trim().toLowerCase();
  // Searching also finds hitters under 300 pitches; they are listed grey and unranked.
  const pool=query?state.allPlayers:state.players;
  const rows=pool.filter(p=>`${p.batter_name} ${p.team}`.toLowerCase().includes(query));
  rows.sort((a,b)=>{
    if(state.sort==="rank") return state.direction*(a.apr_percentile-b.apr_percentile);
    const av=a[state.sort], bv=b[state.sort];
    return typeof av==="string" ? state.direction*av.localeCompare(bv,"ko") : state.direction*((av??-Infinity)-(bv??-Infinity));
  });
  $("#leaderboard").innerHTML=rows.map(p=>{const q=p.qualified_300;return `<tr data-id="${p.batter_id}" class="${p.batter_id===state.selected?'selected':''}${q?'':' unqualified'}"><td>${q?p.rank:'—'}</td><td><strong>${p.batter_name}</strong><br><small>${p.team}${q?'':' · 자격 미달'}</small></td><td class="pct-cell" style="${q?pctStyle(p.apr_percentile):''}" title="${q?`${fmt(p.apr_percentile,0)}번째 백분위`:'자격 미달'}">${fmt(p.apr,0)}</td><td class="pct-cell" style="${q?pctStyle(p.za_percentile):''}" title="${q?`${fmt(p.za_percentile,0)}번째 백분위`:'자격 미달'}">${fmt(p.za_plus,0)}</td><td class="sa-cell">${signed(p.swing_aggression,2)}</td><td>${Number.isFinite(+p.pa)?(+p.pa).toLocaleString():"—"}</td></tr>`}).join("");
  $("#leaderboard").querySelectorAll("tr").forEach(row=>row.onclick=()=>selectPlayer(row.dataset.id));
  // The default APR-percentile order is the APR column's order.
  const active=state.sort==="apr_percentile"?"apr":state.sort;document.querySelectorAll(".leaderboard-card th[data-sort]").forEach(th=>{if(th.dataset.sort===active)th.setAttribute("aria-sort",state.direction>0?"ascending":"descending");else th.removeAttribute("aria-sort");});
}

function drawScatter(){
  const canvas=$("#scatter"), {ctx,width:w,height:h}=canvasContext(canvas), pad={l:58,r:25,t:28,b:48};
  const xs=state.players.map(p=>p.swing_aggression), ys=state.players.map(p=>p.apr);
  const xPad=Math.max(1,(Math.max(...xs)-Math.min(...xs))*.08), yPad=Math.max(2,(Math.max(...ys)-Math.min(...ys))*.08);
  const xStep=5,yStep=10,plotW=w-pad.l-pad.r,plotH=h-pad.t-pad.b;
  // Square grid cells: one 5-SA by 10-APR cell takes the same pixels both ways; the tighter axis sets the size and the other widens around its centre.
  let xLo=Math.min(...xs)-xPad,xHi=Math.max(...xs)+xPad,yLo=Math.min(...ys)-yPad,yHi=Math.max(...ys)+yPad;
  const cell=Math.min(plotW/(xHi-xLo)*xStep,plotH/(yHi-yLo)*yStep),xMid=(xLo+xHi)/2,yMid=(yLo+yHi)/2,xHalf=plotW/cell*xStep/2,yHalf=plotH/cell*yStep/2;
  xLo=xMid-xHalf;xHi=xMid+xHalf;yLo=yMid-yHalf;yHi=yMid+yHalf;
  const x=v=>pad.l+(v-xLo)/(xHi-xLo)*plotW, y=v=>h-pad.b-(v-yLo)/(yHi-yLo)*plotH;
  ctx.clearRect(0,0,w,h); ctx.fillStyle="#ffffff";ctx.fillRect(0,0,w,h);
  ctx.strokeStyle="#d8dddd";ctx.lineWidth=1;ctx.font="11px Arial";ctx.fillStyle="#748084";
  for(let v=Math.ceil(xLo/xStep)*xStep;v<=xHi;v+=xStep){ctx.beginPath();ctx.moveTo(x(v),pad.t);ctx.lineTo(x(v),h-pad.b);ctx.stroke();ctx.fillText(v,x(v)-7,h-pad.b+18);}
  for(let v=Math.ceil(yLo/yStep)*yStep;v<=yHi;v+=yStep){ctx.beginPath();ctx.moveTo(pad.l,y(v));ctx.lineTo(w-pad.r,y(v));ctx.stroke();ctx.fillText(v,pad.l-31,y(v)+4);}
  ctx.strokeStyle="#9aa6a9";ctx.lineWidth=1;ctx.beginPath();ctx.moveTo(x(0),pad.t);ctx.lineTo(x(0),h-pad.b);ctx.moveTo(pad.l,y(100));ctx.lineTo(w-pad.r,y(100));ctx.stroke();
  ctx.fillStyle="#758184";ctx.font="bold 12px Arial";ctx.fillText("Swing Aggression",w-128,h-13);ctx.save();ctx.translate(15,68);ctx.rotate(-Math.PI/2);ctx.fillText("APR",0,0);ctx.restore();
  ctx.font="bold 11px Arial";ctx.lineWidth=4;ctx.strokeStyle="#ffffff";ctx.lineJoin="round";[["소극적 · 높은 APR",pad.l+8,"left"],["적극적 · 높은 APR",w-pad.r-8,"right"]].forEach(([t,lx,al])=>{ctx.textAlign=al;ctx.strokeText(t,lx,pad.t-9);ctx.fillStyle="#8b9699";ctx.fillText(t,lx,pad.t-9);});ctx.textAlign="start";
  // Uniform marks (pitches are already in the shrinkage); stronger APR drawn last so it sits on top.
  state.scatterPoints=[];
  const dot=(p,r,fill)=>{const px=x(p.swing_aggression),py=y(p.apr);ctx.beginPath();ctx.arc(px,py,r,0,Math.PI*2);if(fill){ctx.fillStyle=scatterColor(p.apr_percentile);ctx.fill();ctx.strokeStyle="#ffffff";ctx.lineWidth=1.5;}else{ctx.fillStyle="#ffffff";ctx.fill();ctx.strokeStyle="#7d898c";ctx.lineWidth=1.5;}ctx.stroke();state.scatterPoints.push({p,x:px,y:py,r:r+4});return{px,py};};
  [...state.players].filter(p=>p.batter_id!==state.selected).sort((a,b)=>Math.abs(a.apr_percentile-50)-Math.abs(b.apr_percentile-50)).forEach(p=>dot(p,5,true));
  const sel=state.allPlayers?.find(p=>p.batter_id===state.selected);
  if(sel&&sel.swing_aggression>=xLo&&sel.swing_aggression<=xHi&&sel.apr>=yLo&&sel.apr<=yHi){
    const {px,py}=dot(sel,7,sel.qualified_300);ctx.beginPath();ctx.arc(px,py,7,0,Math.PI*2);ctx.strokeStyle="#17272c";ctx.lineWidth=2.4;ctx.stroke();
    ctx.font="bold 12px Arial";const label=sel.batter_name,tw=ctx.measureText(label).width,lx=px+12+tw>w-pad.r?px-12-tw:px+12,ly=Math.max(pad.t+12,py+4);
    ctx.lineWidth=4;ctx.strokeStyle="rgba(255,255,255,.95)";ctx.strokeText(label,lx,ly);ctx.fillStyle="#17272c";ctx.fillText(label,lx,ly);
  }
  canvas._chart={w,h};
}

function pointer(canvas,event){const r=canvas.getBoundingClientRect();return{x:(event.clientX-r.left)*canvas._chart.w/r.width,y:(event.clientY-r.top)*canvas._chart.h/r.height};}
function bindScatter(){const canvas=$("#scatter"),tip=$("#scatter-tip");canvas.onmousemove=e=>{const q=pointer(canvas,e), hit=state.scatterPoints?.find(d=>Math.hypot(q.x-d.x,q.y-d.y)<d.r);if(!hit){tip.style.display="none";canvas.style.cursor="default";return;}canvas.style.cursor="pointer";tip.innerHTML=`<strong>${hit.p.batter_name}</strong> · ${hit.p.team}<br>APR ${fmt(hit.p.apr,0)} · ${fmt(hit.p.apr_percentile,0)}%ile<br>ZA ${fmt(hit.p.za_plus,0)} · SA ${signed(hit.p.swing_aggression,2)}`;tip.style.display="block";tip.style.left=`${Math.min(e.offsetX+12,canvas.clientWidth-170)}px`;tip.style.top=`${Math.max(4,e.offsetY-64)}px`;};canvas.onmouseleave=()=>tip.style.display="none";canvas.onclick=e=>{const q=pointer(canvas,e),hit=state.scatterPoints?.find(d=>Math.hypot(q.x-d.x,q.y-d.y)<d.r);if(hit)selectPlayer(hit.p.batter_id);};}

async function selectPlayer(id, update=true){
  state.selected=String(id);const p=state.allPlayers.find(x=>x.batter_id===state.selected);if(!p)return;
  renderLeaderboard();drawScatter();
  const shard=/^\d/.test(state.selected)?state.selected.slice(0,2):"other";
  const data=await fetch(`../data/zone_awareness/${state.season}/players/${shard}.json`).then(r=>r.json());
  state.profile=data.players[state.selected];state.cell=null;renderPlayer();
  if(update){const u=new URL(location.href);u.searchParams.set("year",state.season);u.searchParams.set("player",state.selected);history.replaceState(null,"",u);$("#player-section").scrollIntoView({behavior:"smooth",block:"start"});}
}

function renderPlayer(){const p=state.profile.summary,q=p.qualified_300;$("#player-name").textContent=p.batter_name;$("#player-meta").textContent=`${state.season} · ${p.team} · ${p.pitches_seen.toLocaleString()} PITCHES${q?'':' · 300구 미만 자격 미달'}`;$("#score-apr").textContent=fmt(p.apr,0);$("#score-apr").className=q?(p.apr>=100?"good":"bad"):"muted";$("#score-apr-percentile").textContent=`${fmt(p.apr_percentile,0)}%`;$("#score-apr-percentile").className=q?(p.apr_percentile>=50?"good":"bad"):"muted";$("#score-sa").textContent=signed(p.swing_aggression,2);$("#score-za").textContent=fmt(p.za_plus,0);$("#score-percentile").textContent=q?`${fmt(p.za_percentile,0)}%`:"—";$("#score-za").className=q?(p.za_plus>=100?"good":"bad"):"muted";$("#score-percentile").className=q?(p.za_percentile>=50?"good":"bad"):"muted";drawRegionMap(p);renderActions(p);drawDecisionMap();renderOutcome();}

function regionData(p){const entries=state.modern?[["Heart","heart"],["Shadow 안쪽","shadow_in"],["Shadow 바깥","shadow_out"],["Chase","chase"],["Waste","waste"]]:[["Heart","heart"],["Shadow","shadow"],["Chase","chase"],["Waste","waste"]];return entries.map(([name,k])=>({name,n:p[`${k}_pitches`]||0,total:p[`${k}_jdv_per_100`],swingPct:p[`${k}_swing_pct`],expected:p[`${k}_expected_swing_pct`]}));}
function drawRegionMap(p){const {ctx,width:w,height:h}=canvasContext($("#region-map")),cx=w/2,cy=h/2,regions=[...regionData(p)].reverse(),sizes=state.modern?[.94,.76,.507,.38,.253]:[.84,.68,.52,.36],side=Math.min(w,h);ctx.fillStyle="#ffffff";ctx.fillRect(0,0,w,h);const scale=Math.max(...regions.map(r=>Math.abs(r.total||0)),.1);regions.forEach((r,i)=>{const size=side*sizes[i];ctx.fillStyle=diverge(r.total,scale);ctx.fillRect(cx-size/2,cy-size/2,size,size);ctx.strokeStyle="#fff";ctx.lineWidth=2;ctx.strokeRect(cx-size/2,cy-size/2,size,size);});
 const zone=side*(state.modern?.38:.36);ctx.strokeStyle="#176f84";ctx.lineWidth=2;ctx.strokeRect(cx-zone/2,cy-zone/2,zone,zone);
 // Label each ring in the middle of its top band (the innermost region at the centre); white ink on strong fills.
 ctx.font=`bold ${w<400?10:12}px Arial`;ctx.textAlign="center";ctx.textBaseline="middle";regions.forEach((r,i)=>{const outer=side*sizes[i]/2,inner=i+1<sizes.length?side*sizes[i+1]/2:0,ly=inner?cy-(outer+inner)/2:cy;ctx.fillStyle=Math.abs(r.total||0)/scale>.6?"#ffffff":"#26343a";ctx.fillText(`${r.name}  ${signed(r.total,2)}`,cx,ly);});ctx.textAlign="start";ctx.textBaseline="alphabetic";}
function renderActions(p){const values=[{name:"Swing",v:p.swing_jdv_per_100},{name:"Take",v:p.take_jdv_per_100}],max=Math.max(.2,...values.map(x=>Math.abs(x.v||0)));$("#action-bars").innerHTML=values.map(x=>{const width=Math.abs(x.v||0)/max*48,left=x.v>=0?50:50-width;return `<div class="zero-row"><span>${x.name}</span><div class="zero-track"><i class="zero-fill ${x.v<0?'negative':''}" style="left:${left}%;width:${width}%"></i></div><b class="${x.v>=0?'good':'bad'}">${signed(x.v,2)}</b></div>`}).join("");$("#region-table").innerHTML=regionData(p).map(r=>{const gap=Number.isFinite(+r.swingPct)&&Number.isFinite(+r.expected)?r.swingPct-r.expected:null;return `<tr><td>${r.name}</td><td>${r.n.toLocaleString()}</td><td class="${r.total>=0?'good':'bad'}">${signed(r.total,2)}</td><td>${fmt(r.swingPct,0)}%</td><td>${fmt(r.expected,0)}%</td><td>${signed(gap,0)}%p</td></tr>`}).join("");}

function metric(cell){const key=$("#map-metric").value;return key==="swing_gap"?cell.swing_pct-cell.expected_swing_pct:cell[key];}
const MAP_MIN_N=10, MAP_LEGEND={za_raw:["판정과 반대로 선택","판정에 맞게 선택",1,"%p"],delta:["테이크가 유리","스윙이 유리",3,""],swing_gap:["기대보다 덜 스윙","기대보다 더 스윙",0,"%p"]};
function drawDecisionMap(){if(!state.profile)return;const canvas=$("#decision-map"),{ctx,width:w,height:h}=canvasContext(canvas),pad=36,size=Math.min(w,h)-pad*2,x=v=>pad+(v+2.75)/5.5*size,y=v=>pad+(2.75-v)/5.5*size,cellSize=size/11,gap=2;
 // Cells under MAP_MIN_N pitches are noise for one hitter: outline only, still hoverable; they also stay out of the colour scale.
 const values=state.profile.grid.filter(c=>c.n>=MAP_MIN_N).map(metric).filter(Number.isFinite),scale=Math.max(.001,...values.map(Math.abs).sort((a,b)=>a-b).slice(0,Math.ceil(values.length*.9)));
 ctx.fillStyle="#ffffff";ctx.fillRect(0,0,w,h);state.mapCells=[];
 state.profile.grid.forEach(cell=>{const px=x(cell.x)-cellSize/2,py=y(cell.z)-cellSize/2,v=metric(cell);if(cell.n>=MAP_MIN_N&&Number.isFinite(v)){ctx.fillStyle=diverge(v,scale);ctx.fillRect(px+gap/2,py+gap/2,cellSize-gap,cellSize-gap);}else{ctx.strokeStyle="#d5dadb";ctx.lineWidth=1;ctx.strokeRect(px+gap/2+.5,py+gap/2+.5,cellSize-gap-1,cellSize-gap-1);}state.mapCells.push({cell,x:px,y:py,s:cellSize});});
 ctx.strokeStyle="#176f84";ctx.lineWidth=2;ctx.strokeRect(x(-1),y(1),x(1)-x(-1),y(-1)-y(1));ctx.lineWidth=.8;for(const v of[-1/3,1/3]){ctx.beginPath();ctx.moveTo(x(v),y(1));ctx.lineTo(x(v),y(-1));ctx.moveTo(x(-1),y(v));ctx.lineTo(x(1),y(v));ctx.stroke();}
 if(state.cell){const c=state.cell;ctx.strokeStyle="#17272c";ctx.lineWidth=3;ctx.strokeRect(x(c.x)-cellSize/2,y(c.z)-cellSize/2,cellSize,cellSize);}
 ctx.fillStyle="#657175";ctx.font="11px Arial";ctx.fillText("포수 시점",pad,h-10);
 const [lo,hi,digits,unit]=MAP_LEGEND[$("#map-metric").value]||MAP_LEGEND.za_raw;$("#grad-lo").textContent=`−${fmt(scale,digits)}${unit}`;$("#grad-hi").textContent=`+${fmt(scale,digits)}${unit}`;$("#grad-lo-label").textContent=lo;$("#grad-hi-label").textContent=hi;
 canvas._chart={w,h};}
function bindMap(){const canvas=$("#decision-map"),tip=$("#map-tip");canvas.onmousemove=e=>{const q=pointer(canvas,e),hit=state.mapCells?.find(d=>q.x>=d.x&&q.x<=d.x+d.s&&q.y>=d.y&&q.y<=d.y+d.s);if(!hit){tip.style.display="none";return;}tip.innerHTML=`<strong>${hit.cell.n}구</strong><br>ZA ${signed(hit.cell.za_raw,2)}%p<br>Swing ${fmt(hit.cell.swing_pct,0)}% / 기대 ${fmt(hit.cell.expected_swing_pct,0)}%`;tip.style.display="block";tip.style.left=`${Math.min(e.offsetX+10,canvas.clientWidth-175)}px`;tip.style.top=`${Math.max(4,e.offsetY-78)}px`;};canvas.onmouseleave=()=>tip.style.display="none";canvas.onclick=e=>{const q=pointer(canvas,e),hit=state.mapCells?.find(d=>q.x>=d.x&&q.x<=d.x+d.s&&q.y>=d.y&&q.y<=d.y+d.s);if(hit){state.cell=hit.cell;drawDecisionMap();renderOutcome();activateTab("outcome");}};}

function aggregateGrid(){if(state.profile.overall)return state.profile.overall;const cells=state.profile.grid,total=cells.reduce((s,c)=>s+c.n,0),out={n:total,x:0,z:0};for(const f of fields)out[f]=cells.reduce((s,c)=>s+c[f]*c.n,0)/total;return out;}
function pathRows(items){return items.map(([label,value])=>`<div class="path-row"><span>${label}</span><div class="path-track"><i style="width:${Math.max(0,Math.min(100,value||0))}%"></i></div><b>${fmt(value,1)}%</b></div>`).join("");}
function renderOutcome(){if(!state.profile)return;const c=state.cell||aggregateGrid();$("#cell-label").textContent=state.cell?`x ${fmt(c.x,2)} · z ${fmt(c.z,2)} · ${c.n}구`:state.modern?"전체 투구 평균":"맵 전체 평균";$("#swing-path").innerHTML=pathRows(state.modern?[["헛스윙",c.p_Whiff],["파울",c.p_Foul],["인플레이",c.p_InPlay],["실제 Swing",c.swing_pct],["기대 Swing",c.expected_swing_pct]]:[["Actual Swing",c.swing_pct],["Expected Swing",c.expected_swing_pct]]);$("#take-path").innerHTML=pathRows(state.modern?[["볼",c.p_Ball],["루킹 스트라이크",c.p_CalledStrike],["HBP",c.p_HBP]]:[["pZone",c.p_zone_pct],["Actual Judgment",c.zone_judgment_pct],["Expected Judgment",c.expected_zone_judgment_pct]]);$("#swing-rv").textContent=fmt(c.expected_swing_rv,3);$("#take-rv").textContent=fmt(c.expected_take_rv,3);const gap=c.expected_swing_rv-c.expected_take_rv;$("#rv-gap").textContent=`${gap>=0?'+':''}${fmt(gap,3)}`;$("#rv-gap").className=gap>=0?"good":"bad";}
function activateTab(name){document.querySelectorAll(".tabs button").forEach(b=>b.classList.toggle("active",b.dataset.tab===name));document.querySelectorAll(".tab").forEach(t=>t.classList.toggle("active",t.id===`tab-${name}`));if(name==="map")drawDecisionMap();if(name==="profile"&&state.profile)drawRegionMap(state.profile.summary);}

async function init(){const catalog=await fetch("../data/zone_awareness/index.json").then(r=>r.json());const seasons=catalog.seasons.filter(s=>s>=SBJ_FIRST_SEASON),params=new URLSearchParams(location.search),requested=+params.get("year"),selected=seasons.includes(requested)?requested:seasons.includes(catalog.default_season)?catalog.default_season:seasons[0];$("#season").innerHTML=seasons.map(s=>`<option ${s===selected?'selected':''}>${s}</option>`).join("");$("#season").onchange=e=>loadSeason(e.target.value);$("#player-search").oninput=renderLeaderboard;document.querySelectorAll("th[data-sort]").forEach(th=>th.onclick=()=>{if(state.sort===th.dataset.sort)state.direction*=-1;else{state.sort=th.dataset.sort;state.direction=th.dataset.sort==="batter_name"?1:-1;}renderLeaderboard();});document.querySelectorAll(".tabs button").forEach(b=>b.onclick=()=>activateTab(b.dataset.tab));$("#map-metric").onchange=drawDecisionMap;$("#reset-cell").onclick=()=>{state.cell=null;renderOutcome();drawDecisionMap();};bindScatter();bindMap();window.addEventListener("resize",()=>{drawScatter();if(state.profile){drawRegionMap(state.profile.summary);drawDecisionMap();}});await loadSeason(selected);}
init().catch(error=>{console.error(error);document.body.insertAdjacentHTML("beforeend",`<p style="padding:20px;color:#a22">데이터를 불러오지 못했습니다: ${error.message}</p>`);});
