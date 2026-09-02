const $ = (selector) => document.querySelector(selector);
const state = { season: null, players: [], sort: "zone_awareness_plus", direction: -1, selected: null, profile: null, cell: null };
const fields = ["p_whiff_if_swing","p_contact_if_swing","p_foul_if_swing","p_in_play_if_swing","p_ball_if_take","p_called_strike_if_take","p_hbp_if_take","expected_swing_rv","expected_take_rv"];
const fmt = (value, digits=1) => value == null || !Number.isFinite(+value) ? "—" : (+value).toFixed(digits);
const plusClass = value => value >= 100 ? "good" : "bad";

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
function plusColor(value){return diverge((+value-100)/15,2);}

async function loadSeason(season) {
  state.season=+season; state.profile=null; state.cell=null;
  const data=await fetch(`../data/zone_awareness/${season}/leaderboard.json`).then(r=>r.json());
  state.players=data.players.filter(p=>p.qualified_300);
  $("#qualified-count").textContent=`${data.qualified_batters}명 · 300구 이상`;
  renderLeaderboard(); drawScatter();
  const params=new URLSearchParams(location.search), requested=params.get("player");
  const player=state.players.find(p=>p.batter_id===requested) || [...state.players].sort((a,b)=>b.zone_awareness_plus-a.zone_awareness_plus)[0];
  if(player) selectPlayer(player.batter_id, false);
}

function renderLeaderboard(){
  const query=$("#player-search").value.trim().toLowerCase();
  const rows=state.players.filter(p=>`${p.batter_name} ${p.team}`.toLowerCase().includes(query));
  rows.sort((a,b)=>{
    if(state.sort==="rank") return state.direction*(a.zone_awareness_plus-b.zone_awareness_plus);
    const av=a[state.sort], bv=b[state.sort];
    return typeof av==="string" ? state.direction*av.localeCompare(bv,"ko") : state.direction*((av??-Infinity)-(bv??-Infinity));
  });
  $("#leaderboard").innerHTML=rows.map((p,i)=>`<tr data-id="${p.batter_id}" class="${p.batter_id===state.selected?'selected':''}"><td>${i+1}</td><td><strong>${p.batter_name}</strong><br><small>${p.team}</small></td><td class="${plusClass(p.zone_awareness_plus)}">${fmt(p.zone_awareness_plus,0)}</td><td>${fmt(p.z_zone_awareness_plus,0)}</td><td>${fmt(p.o_zone_awareness_plus,0)}</td><td>${fmt(p.za_with_contact_plus,0)}</td><td>${p.pitches_seen.toLocaleString()}</td></tr>`).join("");
  $("#leaderboard").querySelectorAll("tr").forEach(row=>row.onclick=()=>selectPlayer(row.dataset.id));
}

function drawScatter(){
  const canvas=$("#scatter"), {ctx,width:w,height:h}=canvasContext(canvas), pad={l:58,r:25,t:28,b:48};
  const xs=state.players.map(p=>p.o_zone_awareness_plus), ys=state.players.map(p=>p.z_zone_awareness_plus);
  const lo=Math.floor((Math.min(...xs,...ys,85)-5)/10)*10, hi=Math.ceil((Math.max(...xs,...ys,115)+5)/10)*10;
  const x=v=>pad.l+(v-lo)/(hi-lo)*(w-pad.l-pad.r), y=v=>h-pad.b-(v-lo)/(hi-lo)*(h-pad.t-pad.b);
  ctx.clearRect(0,0,w,h); ctx.fillStyle="#fbfbf9";ctx.fillRect(0,0,w,h);
  ctx.strokeStyle="#d8dddd";ctx.lineWidth=1;ctx.font="11px Arial";ctx.fillStyle="#748084";
  for(let v=Math.ceil(lo/10)*10;v<=hi;v+=10){ctx.beginPath();ctx.moveTo(x(v),pad.t);ctx.lineTo(x(v),h-pad.b);ctx.stroke();ctx.beginPath();ctx.moveTo(pad.l,y(v));ctx.lineTo(w-pad.r,y(v));ctx.stroke();ctx.fillText(v,x(v)-7,h-pad.b+18);ctx.fillText(v,pad.l-28,y(v)+4);}
  ctx.strokeStyle="#56666a";ctx.lineWidth=1.4;ctx.beginPath();ctx.moveTo(x(100),pad.t);ctx.lineTo(x(100),h-pad.b);ctx.moveTo(pad.l,y(100));ctx.lineTo(w-pad.r,y(100));ctx.stroke();
  ctx.fillStyle="#758184";ctx.font="bold 12px Arial";ctx.fillText("oZA+",w-58,h-13);ctx.save();ctx.translate(15,58);ctx.rotate(-Math.PI/2);ctx.fillText("zZA+",0,0);ctx.restore();
  ctx.globalAlpha=.7;ctx.font="bold 11px Arial";ctx.fillText("존 안·밖 모두 우수",w-pad.r-118,pad.t+16);ctx.fillText("존 밖 판단 우수",w-pad.r-102,h-pad.b-12);ctx.fillText("존 안 판단 우수",pad.l+8,pad.t+16);ctx.globalAlpha=1;
  state.scatterPoints=[];
  state.players.forEach(p=>{const px=x(p.o_zone_awareness_plus),py=y(p.z_zone_awareness_plus),r=Math.max(3,Math.min(8,Math.sqrt(p.pitches_seen)/6));ctx.beginPath();ctx.arc(px,py,r,0,Math.PI*2);ctx.fillStyle=plusColor(p.zone_awareness_plus);ctx.fill();ctx.strokeStyle=p.batter_id===state.selected?"#17272c":"#ffffff";ctx.lineWidth=p.batter_id===state.selected?2.4:1;ctx.stroke();state.scatterPoints.push({p,x:px,y:py,r:r+4});});
  canvas._chart={w,h};
}

function pointer(canvas,event){const r=canvas.getBoundingClientRect();return{x:(event.clientX-r.left)*canvas._chart.w/r.width,y:(event.clientY-r.top)*canvas._chart.h/r.height};}
function bindScatter(){const canvas=$("#scatter"),tip=$("#scatter-tip");canvas.onmousemove=e=>{const q=pointer(canvas,e), hit=state.scatterPoints?.find(d=>Math.hypot(q.x-d.x,q.y-d.y)<d.r);if(!hit){tip.style.display="none";canvas.style.cursor="default";return;}canvas.style.cursor="pointer";tip.innerHTML=`<strong>${hit.p.batter_name}</strong> · ${hit.p.team}<br>ZA+ ${fmt(hit.p.zone_awareness_plus,0)} · z ${fmt(hit.p.z_zone_awareness_plus,0)} · o ${fmt(hit.p.o_zone_awareness_plus,0)}`;tip.style.display="block";tip.style.left=`${Math.min(e.offsetX+12,canvas.clientWidth-150)}px`;tip.style.top=`${Math.max(4,e.offsetY-48)}px`;};canvas.onmouseleave=()=>tip.style.display="none";canvas.onclick=e=>{const q=pointer(canvas,e),hit=state.scatterPoints?.find(d=>Math.hypot(q.x-d.x,q.y-d.y)<d.r);if(hit)selectPlayer(hit.p.batter_id);};}

async function selectPlayer(id, update=true){
  state.selected=String(id);const p=state.players.find(x=>x.batter_id===state.selected);if(!p)return;
  renderLeaderboard();drawScatter();
  const shard=/^\d/.test(state.selected)?state.selected[0]:"other";
  const data=await fetch(`../data/zone_awareness/${state.season}/players/${shard}.json`).then(r=>r.json());
  state.profile=data.players[state.selected];state.cell=null;renderPlayer();
  if(update){const u=new URL(location.href);u.searchParams.set("year",state.season);u.searchParams.set("player",state.selected);history.replaceState(null,"",u);$("#player-section").scrollIntoView({behavior:"smooth",block:"start"});}
}

function renderPlayer(){const p=state.profile.summary;$("#player-name").textContent=p.batter_name;$("#player-meta").textContent=`${state.season} · ${p.team} · ${p.pitches_seen.toLocaleString()} PITCHES`;[["#score-za",p.zone_awareness_plus],["#score-z",p.z_zone_awareness_plus],["#score-o",p.o_zone_awareness_plus],["#score-con",p.za_with_contact_plus]].forEach(([s,v])=>{$(s).textContent=fmt(v,0);$(s).className=plusClass(v);});drawRegionMap(p);renderActions(p);drawDecisionMap();renderOutcome();}

function regionData(p){return [
  {name:"Heart",n:p.heart_pitches,swing:p.heart_swing_pct,correct:p.heart_swing_pct},
  {name:"Shadow In",n:p.shadow_in_pitches,swing:p.shadow_in_swing_pct,correct:p.shadow_in_swing_pct},
  {name:"Shadow Out",n:p.shadow_out_pitches,swing:p.shadow_out_swing_pct,correct:100-p.shadow_out_swing_pct},
  {name:"Chase",n:p.chase_pitches,swing:p.chase_swing_pct,correct:100-p.chase_swing_pct},
  {name:"Waste",n:p.waste_pitches,swing:p.waste_swing_pct,correct:100-p.waste_swing_pct},
];}
function drawRegionMap(p){const {ctx,width:w,height:h}=canvasContext($("#region-map")),cx=w/2,cy=h/2,regions=[...regionData(p)].reverse(),sizes=[.92,.736,.49,.368,.245];ctx.fillStyle="#f8f8f5";ctx.fillRect(0,0,w,h);regions.forEach((r,i)=>{const s=Math.min(w,h)*sizes[i];ctx.fillStyle=diverge((r.correct-50)/50,1);ctx.fillRect(cx-s/2,cy-s/2,s,s);ctx.strokeStyle="#fff";ctx.lineWidth=2;ctx.strokeRect(cx-s/2,cy-s/2,s,s);ctx.fillStyle="#26343a";ctx.font="bold 12px Arial";ctx.fillText(`${r.name}  ${fmt(r.correct,0)}%`,cx-s/2+10,cy-s/2+20);});const zone=Math.min(w,h)*.368;ctx.strokeStyle="#176f84";ctx.lineWidth=2;ctx.strokeRect(cx-zone/2,cy-zone/2,zone,zone);ctx.lineWidth=1;for(let i=1;i<3;i++){ctx.beginPath();ctx.moveTo(cx-zone/2+i*zone/3,cy-zone/2);ctx.lineTo(cx-zone/2+i*zone/3,cy+zone/2);ctx.moveTo(cx-zone/2,cy-zone/2+i*zone/3);ctx.lineTo(cx+zone/2,cy-zone/2+i*zone/3);ctx.stroke();}}
function renderActions(p){const values=[{name:"Heart–Chase",v:p.pure_hc_residual_z_adjusted},{name:"Z–O Swing",v:p.pure_zo_residual_z_adjusted}],max=Math.max(.5,...values.map(x=>Math.abs(x.v||0)));$("#cluster-label").textContent=`Approach Cluster ${p.pure_cluster_id ?? '—'} · 조정 비중 50%`;$("#action-bars").innerHTML=values.map(x=>{const width=Math.abs(x.v||0)/max*48,left=x.v>=0?50:50-width;return `<div class="zero-row"><span>${x.name}</span><div class="zero-track"><i class="zero-fill ${x.v<0?'negative':''}" style="left:${left}%;width:${width}%"></i></div><b class="${x.v>=0?'good':'bad'}">${fmt(x.v,2)}z</b></div>`}).join("");$("#region-table").innerHTML=regionData(p).map(r=>`<tr><td>${r.name}</td><td>${r.n.toLocaleString()}</td><td>${fmt(r.swing,1)}%</td><td>${fmt(r.correct,1)}%</td></tr>`).join("");}

function metric(cell){const key=$("#map-metric").value;return key==="swing_gap"?cell.swing_pct-cell.expected_swing_pct:cell[key];}
function drawDecisionMap(){if(!state.profile)return;const canvas=$("#decision-map"),{ctx,width:w,height:h}=canvasContext(canvas),pad=36,size=Math.min(w,h)-pad*2,x=v=>pad+(v+2.75)/5.5*size,y=v=>pad+(2.75-v)/5.5*size,cellSize=size/11;const values=state.profile.grid.map(metric).filter(Number.isFinite),scale=Math.max(.001,...values.map(Math.abs).sort((a,b)=>a-b).slice(0,Math.ceil(values.length*.9)));ctx.fillStyle="#f8f8f5";ctx.fillRect(0,0,w,h);state.mapCells=[];state.profile.grid.forEach(cell=>{const px=x(cell.x)-cellSize/2,py=y(cell.z)-cellSize/2;ctx.fillStyle=diverge(metric(cell),scale);ctx.fillRect(px,py,cellSize+.3,cellSize+.3);if(state.cell===cell){ctx.strokeStyle="#17272c";ctx.lineWidth=3;ctx.strokeRect(px,py,cellSize,cellSize);}state.mapCells.push({cell,x:px,y:py,s:cellSize});});ctx.strokeStyle="#176f84";ctx.lineWidth=2;ctx.strokeRect(x(-1),y(1),x(1)-x(-1),y(-1)-y(1));ctx.lineWidth=.8;for(const v of[-1/3,1/3]){ctx.beginPath();ctx.moveTo(x(v),y(1));ctx.lineTo(x(v),y(-1));ctx.moveTo(x(-1),y(v));ctx.lineTo(x(1),y(v));ctx.stroke();}ctx.fillStyle="#657175";ctx.font="11px Arial";ctx.fillText("포수 시점",pad,h-10);canvas._chart={w,h};}
function bindMap(){const canvas=$("#decision-map"),tip=$("#map-tip");canvas.onmousemove=e=>{const q=pointer(canvas,e),hit=state.mapCells?.find(d=>q.x>=d.x&&q.x<=d.x+d.s&&q.y>=d.y&&q.y<=d.y+d.s);if(!hit){tip.style.display="none";return;}tip.innerHTML=`<strong>${hit.cell.n}구</strong><br>DV/100 ${fmt(hit.cell.dv100,2)}<br>Swing ${fmt(hit.cell.swing_pct,0)}% / 기대 ${fmt(hit.cell.expected_swing_pct,0)}%`;tip.style.display="block";tip.style.left=`${Math.min(e.offsetX+10,canvas.clientWidth-145)}px`;tip.style.top=`${Math.max(4,e.offsetY-58)}px`;};canvas.onmouseleave=()=>tip.style.display="none";canvas.onclick=e=>{const q=pointer(canvas,e),hit=state.mapCells?.find(d=>q.x>=d.x&&q.x<=d.x+d.s&&q.y>=d.y&&q.y<=d.y+d.s);if(hit){state.cell=hit.cell;drawDecisionMap();renderOutcome();activateTab("outcome");}};}

function aggregateGrid(){const cells=state.profile.grid,total=cells.reduce((s,c)=>s+c.n,0),out={n:total,x:0,z:0};for(const f of fields)out[f]=cells.reduce((s,c)=>s+c[f]*c.n,0)/total;return out;}
function pathRows(items){return items.map(([label,value])=>`<div class="path-row"><span>${label}</span><div class="path-track"><i style="width:${Math.max(0,Math.min(100,value||0))}%"></i></div><b>${fmt(value,1)}%</b></div>`).join("");}
function renderOutcome(){if(!state.profile)return;const c=state.cell||aggregateGrid();$("#cell-label").textContent=state.cell?`x ${fmt(c.x,2)} · z ${fmt(c.z,2)} · ${c.n}구`:"맵 전체 평균";$("#swing-path").innerHTML=pathRows([["Whiff",c.p_whiff_if_swing],["Contact",c.p_contact_if_swing],["↳ Foul",c.p_foul_if_swing],["↳ In Play",c.p_in_play_if_swing]]);$("#take-path").innerHTML=pathRows([["Ball",c.p_ball_if_take],["Called Strike",c.p_called_strike_if_take],["HBP",c.p_hbp_if_take]]);$("#swing-rv").textContent=fmt(c.expected_swing_rv,3);$("#take-rv").textContent=fmt(c.expected_take_rv,3);const gap=c.expected_swing_rv-c.expected_take_rv;$("#rv-gap").textContent=`${gap>=0?'+':''}${fmt(gap,3)}`;$("#rv-gap").className=gap>=0?"good":"bad";}
function activateTab(name){document.querySelectorAll(".tabs button").forEach(b=>b.classList.toggle("active",b.dataset.tab===name));document.querySelectorAll(".tab").forEach(t=>t.classList.toggle("active",t.id===`tab-${name}`));if(name==="map")drawDecisionMap();if(name==="profile"&&state.profile)drawRegionMap(state.profile.summary);}

async function init(){const catalog=await fetch("../data/zone_awareness/index.json").then(r=>r.json());const params=new URLSearchParams(location.search),requested=+params.get("year");$("#season").innerHTML=catalog.seasons.map(s=>`<option ${s===(requested||catalog.default_season)?'selected':''}>${s}</option>`).join("");$("#season").onchange=e=>loadSeason(e.target.value);$("#player-search").oninput=renderLeaderboard;document.querySelectorAll("th[data-sort]").forEach(th=>th.onclick=()=>{if(state.sort===th.dataset.sort)state.direction*=-1;else{state.sort=th.dataset.sort;state.direction=th.dataset.sort==="batter_name"?1:-1;}renderLeaderboard();});document.querySelectorAll(".tabs button").forEach(b=>b.onclick=()=>activateTab(b.dataset.tab));$("#map-metric").onchange=drawDecisionMap;$("#reset-cell").onclick=()=>{state.cell=null;renderOutcome();drawDecisionMap();};bindScatter();bindMap();window.addEventListener("resize",()=>{drawScatter();if(state.profile){drawRegionMap(state.profile.summary);drawDecisionMap();}});await loadSeason(requested&&catalog.seasons.includes(requested)?requested:catalog.default_season);}
init().catch(error=>{console.error(error);document.body.insertAdjacentHTML("beforeend",`<p style="padding:20px;color:#a22">데이터를 불러오지 못했습니다: ${error.message}</p>`);});
