/* Trendline: independent metric widgets with shared dates and cursor. */
const params = new URLSearchParams(location.search);
if (params.get("thumb") === "1") document.documentElement.classList.add("thumbnail-mode");
const M = TrendlineMath;
const $ = selector => document.querySelector(selector);
const escapeHtml = value => String(value ?? "").replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
const state = {role:params.get("role") === "batter" ? "batter" : "pitcher", catalogs:[], people:{pitcher:[],batter:[]}, games:[], widgets:[], models:[], cursor:null, token:0, nextId:1};
const cache = new Map();
const resize = new ResizeObserver(() => drawCharts());
const defaults = {pitcher:["velocity","k","bb"],batter:["o_swing","swing","z_swing","contact"]};

function getJSON(path) {
  if (!cache.has(path)) cache.set(path, fetch(path,{cache:"no-store"}).then(r=>{if(!r.ok) throw new Error(`기록을 불러오지 못했습니다 (${r.status}).`);return r.json();}).catch(error=>{cache.delete(path);throw error;}));
  return cache.get(path);
}
function widget(metric) { return {id:state.nextId++,metric,pitch:["velocity","usage"].includes(metric)?"split":"all",window:5,league:!!M.METRICS[metric].league,hidden:new Set()}; }
function availableMetrics() { return Object.entries(M.METRICS).filter(([,spec])=>spec.roles.includes(state.role)); }
function format(value,unit="%") { return value == null ? "—" : `${value.toFixed(1)}${unit==="%"?"%":" km/h"}`; }
function niceDate(date) { return date.replaceAll("-","."); }
function bounds() { return {start:$("#from").value,end:$("#to").value,mode:$("#view").value}; }
function period(preset) {
  const latest=state.catalog.seasons[0], first=Math.min(...state.catalog.seasons);
  $("#from").value=`${preset==="career"?first:preset==="current"?latest:Math.max(first,latest-2)}-01-01`;
  $("#to").value=state.asOf;
}
function peopleFromCatalogs() {
  for (const role of ["pitcher","batter"]) {
    const people=new Map();
    for (const catalog of state.catalogs) {
      for (const player of catalog.players[role]) {
        if(!people.has(player.id)) people.set(player.id,{...player,seasons:[],files:{},teams:[...player.teams]});
        const person=people.get(player.id);person.seasons.push(catalog.season);person.files[catalog.season]=player.file;
      }
    }
    state.people[role]=[...people.values()].sort((a,b)=>a.name.localeCompare(b.name,"ko")||a.id.localeCompare(b.id));
  }
}
function search() {
  const q=$("#query").value.trim().replaceAll(" ","").toLowerCase();
  const matches=q ? state.people[state.role].filter(p=>p.name.replaceAll(" ","").toLowerCase().includes(q)).slice(0,20) : [];
  $("#matches").innerHTML=matches.map(p=>`<button type="button" data-player="${escapeHtml(p.id)}">${escapeHtml(p.name)}<small>${escapeHtml(p.teams.join(" · "))} · ${Math.min(...p.seasons)}–${Math.max(...p.seasons)}</small></button>`).join("");
  if(q && !matches.length) $("#status").textContent="일치하는 선수가 없습니다. 이름을 확인해 주세요.";
  return matches;
}
async function selectPlayer(id,reset=false) {
  const player=state.people[state.role].find(p=>p.id===id);
  if(!player) { ++state.token;$("#profile").hidden=true;$("#status").textContent="해당 선수 기록을 찾을 수 없습니다. 이름으로 다시 검색해 주세요.";return; }
  const token=++state.token, role=state.role;
  $("#status").textContent=`${player.name}의 경기 기록을 불러오는 중입니다.`;
  $("#profile").hidden=true;$("#matches").innerHTML="";$("#query").value=player.name;
  try {
    const [profiles,league]=await Promise.all([
      Promise.all(player.seasons.map(year=>getJSON(`../data/trendline/${year}/${role}/players/${player.files[year]}`))),
      Promise.all(state.catalog.seasons.map(year=>getJSON(`../data/trendline/${year}/league.json`))),
    ]);
    if(token!==state.token) return;
    state.selected=player;state.games=profiles.flatMap(p=>p.games).sort((a,b)=>a.date.localeCompare(b.date)||a.game_id.localeCompare(b.game_id));
    state.league=M.leagueIndex(league.flatMap(p=>p.days));
    if(reset || !state.widgets.length) state.widgets=defaults[role].map(widget);
    $("#player-name").textContent=player.name;
    $("#player-meta").textContent=`${role==="pitcher"?"투수":"타자"} · ${player.teams.join(" · ")} · ${player.seasons.toSorted((a,b)=>a-b).join(" / ")}`;
    $("#profile").hidden=false;$("#status").textContent=`기준일 ${state.asOf} · ${state.catalog.seasons.at(-1)}–${state.catalog.seasons[0]} KBO 정규시즌`;
    state.cursor=null;renderWidgets();
  } catch(error) { if(token===state.token) $("#status").textContent=error.message; }
}
function pitchCodes() {
  const codes=new Set(state.games.flatMap(g=>Object.keys(g.types)));
  return Object.keys(state.catalog.pitch_names).filter(code=>codes.has(code));
}
function cardMarkup(w) {
  const spec=M.METRICS[w.metric], {mode}=bounds();
  const metrics=availableMetrics().map(([key,s])=>`<option value="${key}" ${key===w.metric?"selected":""}>${s.label}</option>`).join("");
  const pitches=[...(!spec.overall?[ ["all","전체 구종"],["split","구종별 선"] ]:[["all","전체 타석"]]),...(!spec.overall?pitchCodes().map(code=>[code,state.catalog.pitch_names[code]]):[])];
  return `<article class="trend-card" data-id="${w.id}" ${params.get("thumb")==="1" && w===state.widgets[0]?"data-thumbnail-target":""}>
    <div class="trend-card-heading"><h3>${spec.label} <span class="trend-card-period">${mode==="season"?"· 시즌별":mode==="month"?"· 월별":"· 경기별"}</span></h3><button type="button" class="trend-remove" aria-label="${spec.label} 위젯 삭제">×</button></div>
    <div class="trend-options"><label>지표<select data-setting="metric" aria-label="지표">${metrics}</select></label>
    <label>구종<select data-setting="pitch" aria-label="구종" ${spec.overall?"disabled":""}>${pitches.map(([code,label])=>`<option value="${code}" ${code===w.pitch?"selected":""}>${label}</option>`).join("")}</select></label>
    <label>집계<select data-setting="window" aria-label="집계" ${mode!=="game"?"disabled":""}>${mode!=="game"?`<option>${mode==="season"?"시즌 합산":"월 합산"}</option>`:`<option value="1" ${w.window===1?"selected":""}>경기별 원값</option><option value="5" ${w.window===5?"selected":""}>최근 5경기</option><option value="10" ${w.window===10?"selected":""}>최근 10경기</option>`}</select></label></div>
    <div class="trend-chart" tabindex="0" aria-label="${spec.label} 추세선. 좌우 방향키로 값을 확인합니다."></div><div class="trend-legend"></div><div class="trend-detail" aria-live="polite"></div>
    <p class="trend-sample">빈 원: ${spec.sample} ${spec.min}${spec.sample.includes("타석")?"타석":"개"} 미만 · 점선: 동일 기간 리그 평균</p></article>`;
}
function renderWidgets() {
  if(!state.selected) return;
  const {start,end,mode}=bounds();
  if(!start || !end || start>end) { $("#period-note").textContent="시작일이 종료일보다 늦습니다. 기간을 확인해 주세요.";$("#widgets").innerHTML="";state.models=[];return; }
  $("#period-note").textContent=`${niceDate(start)}–${niceDate(end)} · ${mode==="season"?"시즌 합산":mode==="month"?"월 합산":"출전 경기 기준 이동평균 · 시즌 경계에서 초기화"} · 모든 위젯의 기간과 커서를 함께 표시합니다.`;
  resize.disconnect();$("#widgets").innerHTML=state.widgets.map(cardMarkup).join("") || '<p class="trend-empty">위젯을 추가해 지표를 선택하세요.</p>';
  $("#add-widget").disabled=state.widgets.length>=6;
  for(const card of document.querySelectorAll(".trend-card")) {
    const w=state.widgets.find(w=>w.id===Number(card.dataset.id));
    card.querySelector(".trend-remove").addEventListener("click",()=>{state.widgets=state.widgets.filter(v=>v.id!==w.id);renderWidgets();});
    card.querySelectorAll("[data-setting]").forEach(select=>select.addEventListener("change",()=>{
      const key=select.dataset.setting;
      if(key==="metric") { w.metric=select.value;w.pitch=["velocity","usage"].includes(w.metric)?"split":"all";w.league=!!M.METRICS[w.metric].league;w.hidden.clear(); }
      else if(key==="window") w.window=Number(select.value);
      else { w.pitch=select.value;w.hidden.clear(); }
      renderWidgets();
    }));
    const chart=card.querySelector(".trend-chart");
    chart.addEventListener("pointermove",event=>hoverAt(chart,event.clientX));
    chart.addEventListener("pointerleave",()=>{state.cursor=null;updateHover();});
    chart.addEventListener("keydown",event=>{if(!["ArrowLeft","ArrowRight"].includes(event.key))return;event.preventDefault();const model=state.models.find(m=>m.w.id===w.id);if(!model?.bins.length)return;state.cursor=Math.max(0,Math.min(model.bins.length-1,(state.cursor??0)+(event.key==="ArrowRight"?1:-1)));updateHover();});
    resize.observe(chart);
  }
  drawCharts();
}
function modelFor(w,card) {
  const {start,end,mode}=bounds(), bins=M.periodBins(state.games,mode,start,end,mode==="game"?w.window:1);
  const codes=w.pitch==="split"?pitchCodes():[w.pitch];
  const curves=codes.map(code=>({code,label:code==="all"?state.selected.name:state.catalog.pitch_names[code],color:code==="all"?"#ef4654":state.catalog.pitch_colors[code],points:M.series(bins,w.metric,code,state.league)})).filter(c=>w.pitch!=="split" || c.points.some(p=>p.value!==null));
  return {w,card,bins,curves,mode};
}
function pathFor(points,x,y,league,mode) {
  let path="", previous=null;
  for(const point of points) {
    const v=league?point.league.value:point.value;
    if(v===null) {previous=null;continue;}
    const disconnected=!previous || (mode!=="season" && point.end.slice(0,4)!==previous.end.slice(0,4));
    path+=`${disconnected?"M":"L"}${x(point.x).toFixed(2)},${y(v).toFixed(2)} `;previous=point;
  }
  return path;
}
function drawModel(model) {
  const {w,card,curves,bins,mode}=model, spec=M.METRICS[w.metric], chart=card.querySelector(".trend-chart");
  const width=Math.max(270,Math.round(chart.clientWidth)), height=params.get("thumb")==="1"?440:300;
  const left=49,right=20,top=35,bottom=42;
  const active=curves.filter(c=>!w.hidden.has(c.code));
  const values=active.flatMap(c=>c.points.flatMap(p=>[p.value,...(w.league?[p.league.value]:[])]));
  const axis=M.axis(values,spec.unit);
  const first=bins[0]?.x??0,last=bins.at(-1)?.x??1;
  const x=t=>bins.length<=1 || first===last?(left+width-right)/2:left+(t-first)/(last-first)*(width-left-right);
  const y=v=>height-bottom-(v-axis.min)/(axis.max-axis.min)*(height-top-bottom);
  Object.assign(model,{width,height,left,right,x,y});
  let svg=`<svg viewBox="0 0 ${width} ${height}" role="img" aria-label="${escapeHtml(state.selected.name)} ${spec.label} 추세선"><text x="${left}" y="20" fill="#bac3ce" font-size="12">${spec.unit}</text>`;
  for(let tick=axis.min;tick<=axis.max+axis.step/10;tick+=axis.step) svg+=`<line x1="${left}" x2="${width-right}" y1="${y(tick)}" y2="${y(tick)}" stroke="#ffffff17"/><text x="${left-10}" y="${y(tick)+4}" text-anchor="end" fill="#aab3bf" font-size="12">${Number(tick.toFixed(2))}</text>`;
  const stride=Math.max(1,Math.ceil(bins.length/(width<400?3:5)));
  bins.forEach((bin,i)=>{if(i%stride!==0 && i!==bins.length-1)return;const label=mode==="season"?bin.label:mode==="month"?bin.label.replace("-","."):bin.label.slice(5).replace("-",".");svg+=`<text x="${x(bin.x)}" y="${height-15}" text-anchor="${i===0?"start":i===bins.length-1?"end":"middle"}" fill="#aab3bf" font-size="12">${label}</text>`;});
  for(const curve of active) {
    if(w.league) svg+=`<path class="league-line" d="${pathFor(curve.points,x,y,true,mode)}" fill="none" stroke="${active.length>1?curve.color:"#b6c4d3"}" stroke-width="2" stroke-dasharray="6 5" opacity=".8"/>`;
    svg+=`<path class="player-line" d="${pathFor(curve.points,x,y,false,mode)}" fill="none" stroke="${curve.color}" stroke-width="2.8" stroke-linejoin="round"/>`;
    for(const point of curve.points) if(point.value!==null) svg+=`<circle class="trend-point" cx="${x(point.x)}" cy="${y(point.value)}" r="${bins.length>100?2.2:4}" fill="${point.low?"#14191e":curve.color}" stroke="${curve.color}" stroke-width="1.8"/>`;
  }
  if(!values.some(Number.isFinite)) svg+=`<text x="${width/2}" y="${height/2}" text-anchor="middle" fill="#b6c4d3" font-size="13">이 기간에 계산할 기록이 없습니다.</text>`;
  svg+=`<line class="trend-crosshair" x1="0" x2="0" y1="${top}" y2="${height-bottom}" stroke="#ffffff88" stroke-dasharray="3 4" visibility="hidden"/></svg>`;
  chart.innerHTML=svg;
  const legend=card.querySelector(".trend-legend");
  legend.innerHTML=curves.map(c=>`<button type="button" data-series="${c.code}" aria-pressed="${!w.hidden.has(c.code)}"><i class="trend-swatch" style="border-color:${c.color}"></i>${escapeHtml(c.label)}</button>`).join("")+`<label class="trend-league-label"><input type="checkbox" class="league-toggle" ${w.league?"checked":""}><i class="trend-swatch"></i>리그 평균</label>`;
  legend.querySelectorAll("[data-series]").forEach(button=>button.addEventListener("click",()=>{const code=button.dataset.series;w.hidden.has(code)?w.hidden.delete(code):w.hidden.add(code);drawCharts();}));
  legend.querySelector("input").addEventListener("change",event=>{w.league=event.target.checked;drawCharts();});
  if(card.hasAttribute("data-thumbnail-target")) card.dataset.thumbnailReady="true";
}
function drawCharts() {
  if(!state.selected || $("#profile").hidden) return;
  state.models=[...document.querySelectorAll(".trend-card")].map(card=>modelFor(state.widgets.find(w=>w.id===Number(card.dataset.id)),card));
  state.models.forEach(drawModel);updateHover();
}
function hoverAt(chart,clientX) {
  const model=state.models.find(m=>m.card.contains(chart));if(!model?.bins.length)return;
  const pixel=clientX-chart.getBoundingClientRect().left;
  state.cursor=model.bins.reduce((best,bin,i)=>Math.abs(model.x(bin.x)-pixel)<Math.abs(model.x(model.bins[best].x)-pixel)?i:best,0);updateHover();
}
function updateHover() {
  for(const model of state.models) {
    const {w,card,bins,curves}=model, spec=M.METRICS[w.metric];
    const i=state.cursor??bins.length-1, bin=bins[i];
    const cross=card.querySelector(".trend-crosshair");
    if(cross) {cross.setAttribute("visibility",state.cursor===null || !bin?"hidden":"visible");if(bin){cross.setAttribute("x1",model.x(bin.x));cross.setAttribute("x2",model.x(bin.x));}}
    const detail=card.querySelector(".trend-detail");
    if(!bin) {detail.textContent="선택한 기간에 출전 기록이 없습니다.";continue;}
    const title=`<strong>${niceDate(bin.label)}</strong> · ${niceDate(bin.start)}–${niceDate(bin.end)} · ${bin.games}경기`;
    const lines=curves.filter(c=>!w.hidden.has(c.code)).map(c=>{
      const point=c.points[i], delta=point.value!==null && point.league.value!==null?point.value-point.league.value:null;
      return `<span style="color:${c.color}">●</span> ${escapeHtml(c.label)} <strong>${format(point.value,spec.unit)}</strong> · n=${point.n.toLocaleString("ko")} ${point.n && point.low?"(작은 표본)":""}${point.missing?` · 미확인 ${point.missing}타석 제외`:""}`+(w.league?` · 리그 ${format(point.league.value,spec.unit)}${delta!==null?` (${delta>=0?"+":""}${delta.toFixed(1)}${spec.unit==="%"?"%p":" km/h"})`:""}`:"");
    });
    detail.innerHTML=title+"<br>"+lines.join("<br>");
  }
}
async function init() {
  try {
    state.catalog=await getJSON("../data/trendline/index.json");M.setup(state.catalog.fields);
    state.catalogs=await Promise.all(state.catalog.seasons.map(year=>getJSON(`../data/trendline/${year}/index.json`)));
    state.asOf=state.catalogs.map(c=>c.as_of).filter(Boolean).sort().at(-1);
    peopleFromCatalogs();$("#role").value=state.role;
    $("#query").disabled=false;$("#search-form button").disabled=false;
    $("#from").min=`${Math.min(...state.catalog.seasons)}-01-01`;$("#from").max=state.asOf;$("#to").min=$("#from").min;$("#to").max=state.asOf;
    period("recent");
    if(params.get("from")) $("#from").value=params.get("from");if(params.get("to")) $("#to").value=params.get("to");
    if(["season","game","month"].includes(params.get("view"))) $("#view").value=params.get("view");
    await selectPlayer(params.get("player") || (state.role==="pitcher"?"77637":"53123"),true);
  } catch(error) {$("#status").textContent=`${error.message} 새로고침해 다시 시도해 주세요.`;}
}
$("#search-form").addEventListener("submit",event=>{event.preventDefault();const matches=search();if(matches.length===1)selectPlayer(matches[0].id);});
$("#query").addEventListener("input",search);
$("#matches").addEventListener("click",event=>{const button=event.target.closest("[data-player]");if(button)selectPlayer(button.dataset.player);});
$("#role").addEventListener("change",()=>{if(!state.catalog)return;state.role=$("#role").value;state.widgets=[];$("#query").placeholder=state.role==="pitcher"?"예: 양현종":"예: 오스틴";selectPlayer(state.role==="pitcher"?"77637":"53123",true);});
$("#view").addEventListener("change",()=>{if($("#view").value!=="season")period("current");state.cursor=null;renderWidgets();});
for(const id of ["#from","#to"]) $(id).addEventListener("change",()=>{state.cursor=null;renderWidgets();});
for(const button of document.querySelectorAll("[data-period]")) button.addEventListener("click",()=>{period(button.dataset.period);state.cursor=null;renderWidgets();});
$("#add-widget").addEventListener("click",()=>{if(state.widgets.length>=6)return;const metric=availableMetrics().find(([key])=>!state.widgets.some(w=>w.metric===key))?.[0] || defaults[state.role][0];state.widgets.push(widget(metric));renderWidgets();});
init();
