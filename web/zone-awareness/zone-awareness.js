const $ = (selector) => document.querySelector(selector);
const state = { season: null, players: [], sort: "za_percentile", direction: -1, selected: null, profile: null, cell: null };
const fields = ["swing_pct","expected_swing_pct","p_zone_pct","zone_judgment_pct","expected_zone_judgment_pct","za_raw","expected_swing_rv","expected_take_rv"];
const fmt = (value, digits=1) => value == null || !Number.isFinite(+value) ? "—" : (+value).toFixed(digits);
const signed = (value, digits=1) => value == null || !Number.isFinite(+value) ? "—" : `${+value>0?"+":""}${(+value).toFixed(digits)}`;
const signClass = value => +value >= 0 ? "good" : "bad";

function canvasContext(canvas) {
  const rect = canvas.getBoundingClientRect();
  const width = Math.max(320, rect.width || canvas.width), height = width / (canvas.width / canvas.height);
  const dpr = Math.min(window.devicePixelRatio || 1, 2);
  canvas.width = width * dpr; canvas.height = height * dpr;
  const ctx = canvas.getContext("2d"); ctx.scale(dpr, dpr);
  return {ctx, width, height};
}

function mix(a,b,t){return a.map((v,i)=>Math.round(v+(b[i]-v)*t));}
function diverge(value, scale=1) {
  if (!Number.isFinite(+value)) return "#e7e8e5";
  const neutral=[244,241,232], target=+value>=0?[217,74,86]:[70,120,184];
  const rgb=mix(neutral,target,Math.min(1,Math.abs(+value)/scale));
  return `rgb(${rgb.join(",")})`;
}
function percentileColor(value){return diverge((+value-50)/25,2);}

async function loadSeason(season) {
  state.season=+season; state.profile=null; state.cell=null;
  const [data, teamData]=await Promise.all([
    fetch(`../data/zone_awareness/${season}/leaderboard.json`).then(r=>r.json()),
    fetch(`../data/zone_awareness/${season}/teams.json`).then(r=>r.ok?r.json():{teams:{}}),
  ]);
  state.modern=data.schema_version>=4;
  document.querySelector('th[data-sort="za_raw"]').textContent=state.modern?"ZA / 100":"기존 ZA Raw";
  document.querySelector('.contribution-note').textContent=state.modern?"모든 값은 선수의 전체 투구 100구당 기여도입니다. 존·행동별 값을 합하면 종합 ZA가 됩니다.":"개편 전 시즌입니다. 각 존·행동 100구당 기존 DV이며, 값을 더해 전체 지표를 구할 수 없습니다.";
  $("#season-method").textContent=state.modern ? `이벤트 확률은 Swing·Take 각각의 조건부 확률입니다. 채택 모델: ${data.selected_value_model==="staged"?"이벤트 분해":"직접 행동 가치"}.` : "이 시즌은 개편 전 지표입니다. ZA는 존 판단, 누적 가치는 기존 DV 산식이며 2024–2026과 직접 비교할 수 없습니다.";
  $("#score-za").previousElementSibling.textContent=state.modern?"ZA / 100":"기존 ZA Raw";
  data.players.forEach(player=>{player.team=teamData.teams?.[player.batter_id]||player.team||"—";});
  state.players=data.players.filter(p=>p.qualified_300);
  $("#qualified-count").textContent=`${data.qualified_batters}명 · 300구 이상`;
  renderLeaderboard(); drawScatter();
  const params=new URLSearchParams(location.search), requested=params.get("player");
  const player=state.players.find(p=>p.batter_id===requested) || [...state.players].sort((a,b)=>b.za_percentile-a.za_percentile)[0];
  if(player) selectPlayer(player.batter_id, false);
}

function renderLeaderboard(){
  const query=$("#player-search").value.trim().toLowerCase();
  const rows=state.players.filter(p=>`${p.batter_name} ${p.team}`.toLowerCase().includes(query));
  rows.sort((a,b)=>{
    if(state.sort==="rank") return state.direction*(a.za_percentile-b.za_percentile);
    const av=a[state.sort], bv=b[state.sort];
    return typeof av==="string" ? state.direction*av.localeCompare(bv,"ko") : state.direction*((av??-Infinity)-(bv??-Infinity));
  });
  $("#leaderboard").innerHTML=rows.map((p,i)=>`<tr data-id="${p.batter_id}" class="${p.batter_id===state.selected?'selected':''}"><td>${i+1}</td><td><strong>${p.batter_name}</strong><br><small>${p.team}</small></td><td class="${p.za_percentile>=50?'good':'bad'}">${fmt(p.za_percentile,1)}</td><td>${signed(p.za_raw,2)}</td><td>${signed(p.swing_aggression,2)}</td><td>${fmt(p.raw_dv,2)}</td><td>${signed(p.zone_judgment_raw ?? (state.modern ? null : p.za_raw),2)}</td><td>${p.pitches_seen.toLocaleString()}</td></tr>`).join("");
  $("#leaderboard").querySelectorAll("tr").forEach(row=>row.onclick=()=>selectPlayer(row.dataset.id));
}

function drawScatter(){
  const canvas=$("#scatter"), {ctx,width:w,height:h}=canvasContext(canvas), pad={l:58,r:25,t:28,b:48};
  const xs=state.players.map(p=>p.swing_aggression), ys=state.players.map(p=>p.za_raw);
  const xPad=Math.max(1,(Math.max(...xs)-Math.min(...xs))*.08), yPad=Math.max(.5,(Math.max(...ys)-Math.min(...ys))*.08);
  const xLo=Math.min(...xs)-xPad,xHi=Math.max(...xs)+xPad,yLo=Math.min(...ys)-yPad,yHi=Math.max(...ys)+yPad;
  const x=v=>pad.l+(v-xLo)/(xHi-xLo)*(w-pad.l-pad.r), y=v=>h-pad.b-(v-yLo)/(yHi-yLo)*(h-pad.t-pad.b);
  ctx.clearRect(0,0,w,h); ctx.fillStyle="#fbfbf9";ctx.fillRect(0,0,w,h);
  ctx.strokeStyle="#d8dddd";ctx.lineWidth=1;ctx.font="11px Arial";ctx.fillStyle="#748084";
  const xStep=5,yStep=state.modern?.5:2;
  for(let v=Math.ceil(xLo/xStep)*xStep;v<=xHi;v+=xStep){ctx.beginPath();ctx.moveTo(x(v),pad.t);ctx.lineTo(x(v),h-pad.b);ctx.stroke();ctx.fillText(v,x(v)-7,h-pad.b+18);}
  for(let v=Math.ceil(yLo/yStep)*yStep;v<=yHi;v+=yStep){ctx.beginPath();ctx.moveTo(pad.l,y(v));ctx.lineTo(w-pad.r,y(v));ctx.stroke();ctx.fillText(v,pad.l-31,y(v)+4);}
  ctx.strokeStyle="#56666a";ctx.lineWidth=1.4;ctx.beginPath();ctx.moveTo(x(0),pad.t);ctx.lineTo(x(0),h-pad.b);ctx.moveTo(pad.l,y(0));ctx.lineTo(w-pad.r,y(0));ctx.stroke();
  ctx.fillStyle="#758184";ctx.font="bold 12px Arial";ctx.fillText("Swing Aggression",w-128,h-13);ctx.save();ctx.translate(15,68);ctx.rotate(-Math.PI/2);ctx.fillText(state.modern?"ZA / 100":"기존 ZA Raw",0,0);ctx.restore();
  ctx.globalAlpha=.7;ctx.font="bold 11px Arial";ctx.fillText("소극적 · 높은 ZA",pad.l+8,pad.t+16);ctx.fillText("적극적 · 높은 ZA",w-pad.r-105,pad.t+16);ctx.globalAlpha=1;
  state.scatterPoints=[];
  state.players.forEach(p=>{const px=x(p.swing_aggression),py=y(p.za_raw),r=Math.max(3,Math.min(8,Math.sqrt(p.pitches_seen)/6));ctx.beginPath();ctx.arc(px,py,r,0,Math.PI*2);ctx.fillStyle=percentileColor(p.za_percentile);ctx.fill();ctx.strokeStyle=p.batter_id===state.selected?"#17272c":"#ffffff";ctx.lineWidth=p.batter_id===state.selected?2.4:1;ctx.stroke();state.scatterPoints.push({p,x:px,y:py,r:r+4});});
  canvas._chart={w,h};
}

function pointer(canvas,event){const r=canvas.getBoundingClientRect();return{x:(event.clientX-r.left)*canvas._chart.w/r.width,y:(event.clientY-r.top)*canvas._chart.h/r.height};}
function bindScatter(){const canvas=$("#scatter"),tip=$("#scatter-tip");canvas.onmousemove=e=>{const q=pointer(canvas,e), hit=state.scatterPoints?.find(d=>Math.hypot(q.x-d.x,q.y-d.y)<d.r);if(!hit){tip.style.display="none";canvas.style.cursor="default";return;}canvas.style.cursor="pointer";tip.innerHTML=`<strong>${hit.p.batter_name}</strong> · ${hit.p.team}<br>ZA ${signed(hit.p.za_raw,2)} · ${fmt(hit.p.za_percentile,1)}%ile<br>SA ${signed(hit.p.swing_aggression,2)} · 누적 가치 ${fmt(hit.p.raw_dv,2)}`;tip.style.display="block";tip.style.left=`${Math.min(e.offsetX+12,canvas.clientWidth-170)}px`;tip.style.top=`${Math.max(4,e.offsetY-64)}px`;};canvas.onmouseleave=()=>tip.style.display="none";canvas.onclick=e=>{const q=pointer(canvas,e),hit=state.scatterPoints?.find(d=>Math.hypot(q.x-d.x,q.y-d.y)<d.r);if(hit)selectPlayer(hit.p.batter_id);};}

async function selectPlayer(id, update=true){
  state.selected=String(id);const p=state.players.find(x=>x.batter_id===state.selected);if(!p)return;
  renderLeaderboard();drawScatter();
  const shard=/^\d/.test(state.selected)?state.selected.slice(0,2):"other";
  const data=await fetch(`../data/zone_awareness/${state.season}/players/${shard}.json`).then(r=>r.json());
  state.profile=data.players[state.selected];state.cell=null;renderPlayer();
  if(update){const u=new URL(location.href);u.searchParams.set("year",state.season);u.searchParams.set("player",state.selected);history.replaceState(null,"",u);$("#player-section").scrollIntoView({behavior:"smooth",block:"start"});}
}

function renderPlayer(){const p=state.profile.summary;$("#player-name").textContent=p.batter_name;$("#player-meta").textContent=`${state.season} · ${p.team} · ${p.pitches_seen.toLocaleString()} PITCHES`;$("#score-sa").textContent=signed(p.swing_aggression,2);$("#score-za").textContent=signed(p.za_raw,2);$("#score-percentile").textContent=`${fmt(p.za_percentile,1)}%`;$("#score-dv").textContent=fmt(p.raw_dv,2);$("#score-dv100").textContent=signed(p.zone_judgment_raw ?? (state.modern ? null : p.za_raw),2);$("#score-za").className=signClass(p.za_raw);$("#score-percentile").className=p.za_percentile>=50?"good":"bad";$("#score-dv").className=signClass(p.raw_dv);$("#score-dv100").className=signClass(p.zone_judgment_raw ?? p.za_raw);drawRegionMap(p);renderActions(p);drawDecisionMap();renderOutcome();}

function regionData(p){const entries=state.modern?[["Heart","heart"],["Shadow 안쪽","shadow_in"],["Shadow 바깥","shadow_out"],["Chase","chase"],["Waste","waste"]]:[["Heart","heart"],["Shadow","shadow"],["Chase","chase"],["Waste","waste"]];return entries.map(([name,k])=>({name,n:p[`${k}_pitches`]||0,total:p[`${k}_decision_value_per_100`],swing:p[`${k}_swing_decision_value_per_100`],take:p[`${k}_take_decision_value_per_100`]}));}
function drawRegionMap(p){const {ctx,width:w,height:h}=canvasContext($("#region-map")),cx=w/2,cy=h/2,regions=[...regionData(p)].reverse(),sizes=state.modern?[.94,.76,.507,.38,.253]:[.84,.68,.52,.36];ctx.fillStyle="#f8f8f5";ctx.fillRect(0,0,w,h);const scale=Math.max(...regions.map(r=>Math.abs(r.total||0)),.1);regions.forEach((r,i)=>{const size=Math.min(w,h)*sizes[i];ctx.fillStyle=diverge(r.total,scale);ctx.fillRect(cx-size/2,cy-size/2,size,size);ctx.strokeStyle="#fff";ctx.lineWidth=2;ctx.strokeRect(cx-size/2,cy-size/2,size,size);ctx.fillStyle="#26343a";ctx.font=`bold ${w<400?10:12}px Arial`;ctx.fillText(`${r.name}  ${fmt(r.total,2)}`,cx-size/2+6,cy-size/2+(w<400?13:18));});const zone=Math.min(w,h)*(state.modern?.38:.36);ctx.strokeStyle="#176f84";ctx.lineWidth=2;ctx.setLineDash([4,3]);ctx.strokeRect(cx-zone/2,cy-zone/2,zone,zone);ctx.setLineDash([]);}
function renderActions(p){const values=[{name:"Swing",v:p.swing_decision_value_per_100},{name:"Take",v:p.take_decision_value_per_100}],max=Math.max(.2,...values.map(x=>Math.abs(x.v||0)));$("#action-bars").innerHTML=values.map(x=>{const width=Math.abs(x.v||0)/max*48,left=x.v>=0?50:50-width;return `<div class="zero-row"><span>${x.name}</span><div class="zero-track"><i class="zero-fill ${x.v<0?'negative':''}" style="left:${left}%;width:${width}%"></i></div><b class="${x.v>=0?'good':'bad'}">${fmt(x.v,2)}</b></div>`}).join("");$("#region-table").innerHTML=regionData(p).map(r=>`<tr><td>${r.name}</td><td>${r.n.toLocaleString()}</td><td>${fmt(r.total,2)}</td><td>${fmt(r.swing,2)}</td><td>${fmt(r.take,2)}</td></tr>`).join("");}

function metric(cell){const key=$("#map-metric").value;return key==="swing_gap"?cell.swing_pct-cell.expected_swing_pct:cell[key];}
function drawDecisionMap(){if(!state.profile)return;const canvas=$("#decision-map"),{ctx,width:w,height:h}=canvasContext(canvas),pad=36,size=Math.min(w,h)-pad*2,x=v=>pad+(v+2.75)/5.5*size,y=v=>pad+(2.75-v)/5.5*size,cellSize=size/11;const values=state.profile.grid.map(metric).filter(Number.isFinite),scale=Math.max(.001,...values.map(Math.abs).sort((a,b)=>a-b).slice(0,Math.ceil(values.length*.9)));ctx.fillStyle="#f8f8f5";ctx.fillRect(0,0,w,h);state.mapCells=[];state.profile.grid.forEach(cell=>{const px=x(cell.x)-cellSize/2,py=y(cell.z)-cellSize/2;ctx.fillStyle=diverge(metric(cell),scale);ctx.fillRect(px,py,cellSize+.3,cellSize+.3);if(state.cell===cell){ctx.strokeStyle="#17272c";ctx.lineWidth=3;ctx.strokeRect(px,py,cellSize,cellSize);}state.mapCells.push({cell,x:px,y:py,s:cellSize});});ctx.strokeStyle="#176f84";ctx.lineWidth=2;ctx.strokeRect(x(-1),y(1),x(1)-x(-1),y(-1)-y(1));ctx.lineWidth=.8;for(const v of[-1/3,1/3]){ctx.beginPath();ctx.moveTo(x(v),y(1));ctx.lineTo(x(v),y(-1));ctx.moveTo(x(-1),y(v));ctx.lineTo(x(1),y(v));ctx.stroke();}ctx.fillStyle="#657175";ctx.font="11px Arial";ctx.fillText("포수 시점",pad,h-10);canvas._chart={w,h};}
function bindMap(){const canvas=$("#decision-map"),tip=$("#map-tip");canvas.onmousemove=e=>{const q=pointer(canvas,e),hit=state.mapCells?.find(d=>q.x>=d.x&&q.x<=d.x+d.s&&q.y>=d.y&&q.y<=d.y+d.s);if(!hit){tip.style.display="none";return;}tip.innerHTML=`<strong>${hit.cell.n}구</strong><br>누적 가치 ${fmt(hit.cell.raw_dv,2)} · ZA/100 ${fmt(hit.cell.dv100,2)}<br>ZA ${signed(hit.cell.za_raw,2)}<br>Swing ${fmt(hit.cell.swing_pct,0)}% / 기대 ${fmt(hit.cell.expected_swing_pct,0)}%`;tip.style.display="block";tip.style.left=`${Math.min(e.offsetX+10,canvas.clientWidth-175)}px`;tip.style.top=`${Math.max(4,e.offsetY-78)}px`;};canvas.onmouseleave=()=>tip.style.display="none";canvas.onclick=e=>{const q=pointer(canvas,e),hit=state.mapCells?.find(d=>q.x>=d.x&&q.x<=d.x+d.s&&q.y>=d.y&&q.y<=d.y+d.s);if(hit){state.cell=hit.cell;drawDecisionMap();renderOutcome();activateTab("outcome");}};}

function aggregateGrid(){if(state.profile.overall)return state.profile.overall;const cells=state.profile.grid,total=cells.reduce((s,c)=>s+c.n,0),out={n:total,x:0,z:0};for(const f of fields)out[f]=cells.reduce((s,c)=>s+c[f]*c.n,0)/total;return out;}
function pathRows(items){return items.map(([label,value])=>`<div class="path-row"><span>${label}</span><div class="path-track"><i style="width:${Math.max(0,Math.min(100,value||0))}%"></i></div><b>${fmt(value,1)}%</b></div>`).join("");}
function renderOutcome(){if(!state.profile)return;const c=state.cell||aggregateGrid();$("#cell-label").textContent=state.cell?`x ${fmt(c.x,2)} · z ${fmt(c.z,2)} · ${c.n}구`:state.modern?"전체 투구 평균":"맵 전체 평균";$("#swing-path").innerHTML=pathRows(state.modern?[["헛스윙",c.p_Whiff],["파울",c.p_Foul],["인플레이",c.p_InPlay],["실제 Swing",c.swing_pct],["기대 Swing",c.expected_swing_pct]]:[["Actual Swing",c.swing_pct],["Expected Swing",c.expected_swing_pct]]);$("#take-path").innerHTML=pathRows(state.modern?[["볼",c.p_Ball],["루킹 스트라이크",c.p_CalledStrike],["HBP",c.p_HBP]]:[["pZone",c.p_zone_pct],["Actual Judgment",c.zone_judgment_pct],["Expected Judgment",c.expected_zone_judgment_pct]]);$("#swing-rv").textContent=fmt(c.expected_swing_rv,3);$("#take-rv").textContent=fmt(c.expected_take_rv,3);const gap=c.expected_swing_rv-c.expected_take_rv;$("#rv-gap").textContent=`${gap>=0?'+':''}${fmt(gap,3)}`;$("#rv-gap").className=gap>=0?"good":"bad";}
function activateTab(name){document.querySelectorAll(".tabs button").forEach(b=>b.classList.toggle("active",b.dataset.tab===name));document.querySelectorAll(".tab").forEach(t=>t.classList.toggle("active",t.id===`tab-${name}`));if(name==="map")drawDecisionMap();if(name==="profile"&&state.profile)drawRegionMap(state.profile.summary);}

async function init(){const catalog=await fetch("../data/zone_awareness/index.json").then(r=>r.json());const params=new URLSearchParams(location.search),requested=+params.get("year");$("#season").innerHTML=catalog.seasons.map(s=>`<option ${s===(requested||catalog.default_season)?'selected':''}>${s}</option>`).join("");$("#season").onchange=e=>loadSeason(e.target.value);$("#player-search").oninput=renderLeaderboard;document.querySelectorAll("th[data-sort]").forEach(th=>th.onclick=()=>{if(state.sort===th.dataset.sort)state.direction*=-1;else{state.sort=th.dataset.sort;state.direction=th.dataset.sort==="batter_name"?1:-1;}renderLeaderboard();});document.querySelectorAll(".tabs button").forEach(b=>b.onclick=()=>activateTab(b.dataset.tab));$("#map-metric").onchange=drawDecisionMap;$("#reset-cell").onclick=()=>{state.cell=null;renderOutcome();drawDecisionMap();};bindScatter();bindMap();window.addEventListener("resize",()=>{drawScatter();if(state.profile){drawRegionMap(state.profile.summary);drawDecisionMap();}});await loadSeason(requested&&catalog.seasons.includes(requested)?requested:catalog.default_season);}
init().catch(error=>{console.error(error);document.body.insertAdjacentHTML("beforeend",`<p style="padding:20px;color:#a22">데이터를 불러오지 못했습니다: ${error.message}</p>`);});
