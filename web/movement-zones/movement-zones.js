const categories = [
  {key:'high',label:'높은 Whiff',color:'#df243e',pattern:'elitePattern'},
  {key:'average',label:'중간 Whiff',color:'#13aa42',pattern:'averagePattern'},
  {key:'low',label:'낮은 Whiff',color:'#252525',pattern:'deadPattern'}
];
const angleInput=document.querySelector('#angle'), angleValue=document.querySelector('#angle-value');
const tabs=document.querySelector('#pitch-tabs'), handTabs=document.querySelector('#hand-tabs'), chart=document.querySelector('#movement-chart');
const rangeTable=document.querySelector('#range-table'), playButton=document.querySelector('#play'), status=document.querySelector('#sample-status');
const viewInput=document.querySelector('#view'), compareHb=document.querySelector('#compare-hb'), compareIvb=document.querySelector('#compare-ivb'), deltaStatus=document.querySelector('#delta-status');
const params=new URLSearchParams(location.search);
let data=null, selected='FF', selectedHand=params.get('hand')==='L'?'L':'R', timer=null;
viewInput.value=params.get('view')==='whiff'?'whiff':'expected';
if(selectedHand==='L') compareHb.value='10';
const fmt=n=>`${n>0?'+':''}${n.toFixed(1)}`.replace('-', '−');
const rangeText=range=>`${fmt(range[0])} ~ ${fmt(range[1])}`;
// 플롯 영역(92..708 × 54..574)의 네 테두리는 모두 10인치 눈금과 맞아야 합니다(tests/test_movement_zones_layout.cjs).
const AXIS={xMin:-30,xMax:30,yMin:-30,yMax:30,step:10}, PX_X=616/(AXIS.xMax-AXIS.xMin), PX_Y=520/(AXIS.yMax-AXIS.yMin);
const sx=x=>92+(x-AXIS.xMin)*PX_X, sy=y=>574-(y-AXIS.yMin)*PX_Y;
const escapeHtml=s=>String(s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const handFactor=()=>selectedHand==='R'?-1:1;

function viewZone(zone){
  return {...zone,hb:zone.hb.map(x=>x*handFactor()).sort((a,b)=>a-b)};
}

function renderTabs(){
  tabs.innerHTML=Object.entries(data.pitches).map(([key,pitch])=>`<button type="button" data-pitch="${escapeHtml(key)}" aria-pressed="${key===selected}">${escapeHtml(pitch.name)}</button>`).join('');
}

function defs(){
  return `<defs>
  <pattern id="elitePattern" width="8" height="8" patternUnits="userSpaceOnUse" patternTransform="rotate(45)"><rect width="8" height="8" fill="#df243e" fill-opacity=".08"/><line x1="0" y1="0" x2="0" y2="8" stroke="#df243e" stroke-opacity=".35" stroke-width="2"/></pattern>
  <pattern id="averagePattern" width="8" height="8" patternUnits="userSpaceOnUse"><rect width="8" height="8" fill="#13aa42" fill-opacity=".07"/><line x1="0" y1="2" x2="8" y2="2" stroke="#13aa42" stroke-opacity=".3" stroke-width="2"/></pattern>
  <pattern id="deadPattern" width="7" height="7" patternUnits="userSpaceOnUse"><rect width="7" height="7" fill="#252525" fill-opacity=".08"/><circle cx="2" cy="2" r="1" fill="#252525" fill-opacity=".3"/></pattern>
  <clipPath id="plotClip"><rect x="92" y="54" width="616" height="520"/></clipPath>
  </defs>`;
}

function grid(){
  let out='';
  for(let x=AXIS.xMin;x<=AXIS.xMax;x+=AXIS.step) out+=`<line x1="${sx(x)}" y1="54" x2="${sx(x)}" y2="574" class="grid ${x===0?'zero':''}"/><text x="${sx(x)}" y="600" text-anchor="middle" class="axis-text">${x}</text>`;
  for(let y=AXIS.yMin;y<=AXIS.yMax;y+=AXIS.step) out+=`<line x1="92" y1="${sy(y)}" x2="708" y2="${sy(y)}" class="grid ${y===0?'zero':''}"/><text x="78" y="${sy(y)+5}" text-anchor="end" class="axis-text">${y}</text>`;
  return `${out}<text x="400" y="34" text-anchor="middle" class="direction-label">3B &lt; MOVES TOWARD &gt; 1B</text><text x="400" y="646" text-anchor="middle" class="axis-title">Horizontal Break (inches) · 포수 시점</text><text x="22" y="314" text-anchor="middle" class="axis-title" transform="rotate(-90 22 314)">Induced Vertical Break (inches)</text>`;
}

function armLine(angle){
  const rad=angle*Math.PI/180, x=25*Math.cos(rad)*handFactor(), y=25*Math.sin(rad);
  return `<line x1="${sx(0)}" y1="${sy(0)}" x2="${sx(x)}" y2="${sy(y)}" class="arm-line"/><text x="${sx(x*.55)}" y="${sy(y*.55)-10}" text-anchor="middle" class="arm-label">${angle}° estimated slot</text>`;
}

function expectedSvg(zone,level){
  const cx=sx(zone.center[0]*handFactor()), cy=sy(zone.center[1]);
  const xx=zone.covariance[0][0]*PX_X**2, yy=zone.covariance[1][1]*PX_Y**2;
  const xy=-handFactor()*zone.covariance[0][1]*PX_X*PX_Y;
  const discriminant=Math.hypot(xx-yy,2*xy), radius=Math.sqrt(-2*Math.log(1-level));
  const rx=radius*Math.sqrt(Math.max(0,(xx+yy+discriminant)/2)), ry=radius*Math.sqrt(Math.max(0,(xx+yy-discriminant)/2));
  const rotation=Math.atan2(2*xy,xx-yy)*90/Math.PI;
  return `<g class="expected-region expected-${Math.round(level*100)}" data-center-hb="${zone.center[0]*handFactor()}" data-center-ivb="${zone.center[1]}" transform="translate(${cx} ${cy}) rotate(${rotation})"><title>모형 예상 ${Math.round(level*100)}% 확률 범위</title><ellipse cx="0" cy="0" rx="${rx}" ry="${ry}" fill="${level===.5?'url(#deadPattern)':'#edf1f4'}" fill-opacity="${level===.5?1:.5}" stroke="${level===.5?'#252525':'#7c878f'}" stroke-width="${level===.5?2.4:1.6}" ${level===.8?'stroke-dasharray="6 4"':''}/></g>`;
}

function zoneSvg(zone,cat){
  const cells=new Set(zone.cells), size=data.grid.ivb_count;
  let fill='', outline='';
  for(const cell of cells){
    const row=Math.floor(cell/size), col=cell%size, x=data.grid.hb_min+row, y=data.grid.ivb_min+col;
    const l=sx((x-.5)*handFactor()), r=sx((x+.5)*handFactor()), b=sy(y-.5), t=sy(y+.5);
    fill+=`M${l} ${b}L${r} ${b}L${r} ${t}L${l} ${t}Z`;
    if(row===0||!cells.has(cell-size)) outline+=`M${l} ${b}L${l} ${t}`;
    if(row===data.grid.hb_count-1||!cells.has(cell+size)) outline+=`M${r} ${b}L${r} ${t}`;
    if(col===0||!cells.has(cell-1)) outline+=`M${l} ${b}L${r} ${b}`;
    if(col===size-1||!cells.has(cell+1)) outline+=`M${l} ${t}L${r} ${t}`;
  }
  return `<g class="zone zone-${cat.key}" data-cells="${zone.cells.join(',')}" data-center-hb="${zone.center[0]*handFactor()}" data-center-ivb="${zone.center[1]}" data-whiff="${zone.whiff_pct}"><title>${cat.label}: 추정 Whiff ${zone.whiff_pct.toFixed(1)}%</title><path class="zone-fill" d="${fill}" fill="url(#${cat.pattern})"/><path class="zone-boundary" d="${outline}" fill="none" stroke="${cat.color}" stroke-width="1.8"/></g>`;
}

function comparison(expected){
  deltaStatus.removeAttribute('data-delta-hb');deltaStatus.removeAttribute('data-delta-ivb');
  if(!expected){deltaStatus.textContent='기대 무브먼트 표본 부족';return '';}
  if(!compareHb.value||!compareIvb.value||!compareHb.checkValidity()||!compareIvb.checkValidity()){
    deltaStatus.textContent='HB −30~30, IVB −25~30인치 범위의 숫자를 입력하세요.';return '';
  }
  const x=Number(compareHb.value), y=Number(compareIvb.value), h=x*handFactor()-expected.center[0], v=y-expected.center[1];
  const [[xx,xy],[,yy]]=expected.covariance, distance=(yy*h*h-2*xy*h*v+xx*v*v)/(xx*yy-xy*xy);
  deltaStatus.dataset.deltaHb=String(h*handFactor());deltaStatus.dataset.deltaIvb=String(v);
  deltaStatus.textContent=`기대 HB ${fmt(expected.center[0]*handFactor())}, IVB ${fmt(expected.center[1])} · ΔHB ${fmt(h*handFactor())}, ΔIVB ${fmt(v)} · ${distance<=-2*Math.log(.5)?'예상 중심 50% 안':distance<=-2*Math.log(.2)?'예상 80% 안':'예상 80% 밖'}`;
  const cx=sx(expected.center[0]*handFactor()), cy=sy(expected.center[1]);
  return `<path d="M${cx-5} ${cy}h10M${cx} ${cy-5}v10" stroke="#252525" stroke-width="2"/><circle class="comparison-point" cx="${sx(x)}" cy="${sy(y)}" r="5" fill="#145eac" stroke="white" stroke-width="1.5"><title>비교 무브먼트: ΔHB ${fmt(h*handFactor())}, ΔIVB ${fmt(v)}</title></circle>`;
}

function render(){
  if(!data) return;
  const angle=Number(angleInput.value), pitch=data.pitches[selected], handLabel=selectedHand==='R'?'RHP':'LHP';
  const hand=pitch.hands[selectedHand], profile=hand.profiles[angle-data.angle_min], zones=profile.zones;
  const expected=profile.expected, shapeView=viewInput.value==='expected';
  angleValue.textContent=`${angle}°`;
  angleInput.setAttribute('aria-valuetext',`${angle}도, 릴리스 위치 기반 추정`);
  document.querySelector('#chart-kicker').textContent=`${angle}° · ${handLabel} · ${pitch.name.toUpperCase()}`;
  document.querySelector('#chart-title').textContent=`${pitch.name} Movement Map`;
  handTabs.querySelectorAll('button').forEach(b=>b.setAttribute('aria-pressed',String(b.dataset.hand===selectedHand)));
  tabs.querySelectorAll('button').forEach(b=>b.setAttribute('aria-pressed',String(b.dataset.pitch===selected)));
  document.querySelector('#range-heading').innerHTML=`<tr><th>구분</th><th>IVB</th><th>HB</th>${shapeView?'':'<th>Whiff%</th>'}</tr>`;
  document.querySelector('#legend').innerHTML=shapeView?'<div><span class="swatch expected"></span><div><strong>예상 중심 50%</strong><small>Dynamic DZ · 모형 확률 범위</small></div></div><div><span class="swatch outer"></span><div><strong>예상 80%</strong><small>같은 릴리스 조건의 기대 분포</small></div></div><div><span class="swatch point"></span><div><strong>비교 무브먼트</strong><small>입력값 − 기대 중심 = DZ Delta</small></div></div>':categories.map((cat,i)=>`<div><span class="swatch ${['elite','average','dead'][i]}"></span><div><strong>${cat.label}</strong><small>추정 헛스윙률 ${['상위 25%','중간 50%','하위 25%'][i]} · 성능 구역</small></div></div>`).join('');
  rangeTable.innerHTML=shapeView?(expected?data.expected_levels.map(level=>{
    const radius=Math.sqrt(-2*Math.log(1-level)), h=radius*Math.sqrt(expected.covariance[0][0]), v=radius*Math.sqrt(expected.covariance[1][1]);
    const z=viewZone({hb:[expected.center[0]-h,expected.center[0]+h],ivb:[expected.center[1]-v,expected.center[1]+v]});
    return `<tr><td>예상 ${Math.round(level*100)}%</td><td>${rangeText(z.ivb)}</td><td>${rangeText(z.hb)}</td></tr>`;
  }).join(''):'<tr><td colspan="3">기대 무브먼트 표본 부족</td></tr>'):(zones?categories.map(cat=>{
    const z=viewZone(zones[cat.key]);
    return `<tr><td style="color:${cat.color}">${cat.label}</td><td>${rangeText(z.ivb)}</td><td>${rangeText(z.hb)}</td><td>${z.whiff_pct.toFixed(1)}%</td></tr>`;
  }).join(''):'<tr><td colspan="4">이 각도·손·구종은 스윙 표본 부족</td></tr>');
  const sv=pitch.shape_validation[selectedHand], validation=shapeView?sv:pitch.validation;
  const improved=shapeView?sv&&sv.rmse_hb**2+sv.rmse_ivb**2<sv.baseline_rmse_hb**2+sv.baseline_rmse_ivb**2:validation&&validation.movement.log_loss<validation.controls_only.log_loss;
  const validationNote=!validation?' · 시간 검증 표본 부족 (실험)':!improved?' · 최신 시즌 예측 개선 미확인':'';
  const visible=shapeView?expected:zones;
  status.textContent=`${angle}° ± ${data.window_deg}° · ${shapeView?`${profile.shape_pitches.toLocaleString('ko-KR')}구 · ${profile.shape_pitchers}명`:`${profile.swings.toLocaleString('ko-KR')}스윙 · ${profile.pitchers}명`} · 기준 구속 ${hand.velocity_kmh.toFixed(1)} km/h${expected?` · 체공 ${expected.flight.toFixed(3)}초`:''}${visible?'':` · 최소 ${data.min_swings}표본·${data.min_pitchers}명 필요`}${validationNote}${pitch.fastball_reference?'':' · 변화구 기대 모형은 탐색적'}`;
  const description=shapeView?'릴리스 조건부 기대 무브먼트의 모형 50%·80% 확률 범위. 성능 등급이 아닙니다.':zones?`높은 ${zones.high.whiff_pct}%, 중간 ${zones.average.whiff_pct}%, 낮은 ${zones.low.whiff_pct}%, 추정 헛스윙률.`:'스윙 표본 부족.';
  const regions=shapeView?(expected?[...data.expected_levels].reverse().map(level=>expectedSvg(expected,level)).join(''):''):(zones?[...categories].reverse().map(cat=>zoneSvg(zones[cat.key],cat)).join(''):'');
  chart.innerHTML=`<title id="svg-title">${escapeHtml(pitch.name)} ${angle}도 ${handLabel} ${shapeView?'기대 무브먼트':'헛스윙률 구역'}</title><desc id="svg-desc">포수 시점, 0.40초 환산. ${description}</desc>${defs()}${grid()}<g clip-path="url(#plotClip)">${armLine(angle)}${regions}${comparison(expected)}</g>${visible?'':`<text x="400" y="300" text-anchor="middle" class="empty-chart">이 구간은 관측 표본이 부족합니다</text><text x="400" y="327" text-anchor="middle" class="axis-text">다른 각도·투수 손·구종을 선택하세요</text>`}`;
  const target=document.querySelector('[data-thumbnail-target]');
  if(target) target.dataset.thumbnailReady='true';
}

function stop(){clearInterval(timer);timer=null;playButton.textContent='▶';playButton.setAttribute('aria-pressed','false');playButton.setAttribute('aria-label','팔각도 자동 재생');}
function play(){
  if(!data) return;
  timer=setInterval(()=>{angleInput.value=Number(angleInput.value)>=data.angle_max?data.angle_min:Number(angleInput.value)+1;render();},100);
  playButton.textContent='Ⅱ';playButton.setAttribute('aria-pressed','true');playButton.setAttribute('aria-label','팔각도 자동 재생 정지');
}
angleInput.addEventListener('input',()=>{stop();render();});
playButton.addEventListener('click',()=>timer?stop():play());
tabs.addEventListener('click',event=>{const button=event.target.closest('[data-pitch]');if(button){selected=button.dataset.pitch;render();}});
handTabs.querySelectorAll('button').forEach(button=>button.addEventListener('click',()=>{
  if(selectedHand!==button.dataset.hand&&compareHb.value) compareHb.value=String(-Number(compareHb.value));
  selectedHand=button.dataset.hand;render();
}));
viewInput.addEventListener('change',()=>{stop();render();});
[compareHb,compareIvb].forEach(input=>input.addEventListener('input',()=>{stop();render();}));
document.addEventListener('visibilitychange',()=>{if(document.hidden) stop();});

async function load(){
  playButton.disabled=true;
  try{
    const response=await fetch('../data/movement_zones/profiles.json?v=20261001-2');
    if(!response.ok) throw new Error(`HTTP ${response.status}`);
    data=await response.json();
    if(data.schema_version!==2||!data.pitches.FF) throw new Error('회귀 데이터 형식 오류');
    angleInput.min=data.angle_min;angleInput.max=data.angle_max;
    if(params.has('angle')&&Number.isFinite(Number(params.get('angle')))) angleInput.value=String(Math.max(data.angle_min,Math.min(data.angle_max,Math.round(Number(params.get('angle'))))));
    if(data.pitches[params.get('pitch')]) selected=params.get('pitch');
    renderTabs();render();
    const sources=data.sources.map(s=>`<tr><td>${s.season}</td><td>${s.shape_pitches.toLocaleString('ko-KR')}</td><td>${s.eligible_swings.toLocaleString('ko-KR')}</td><td>${s.trackman_shape_pitches.toLocaleString('ko-KR')}</td></tr>`).join('');
    const validation=Object.values(data.pitches).map(p=>{
      const v=p.validation;
      return v?`<tr><td>${escapeHtml(p.name)}</td><td>${v.test_swings.toLocaleString('ko-KR')}</td><td>${v.movement.auc.toFixed(3)}</td><td>${v.movement.log_loss.toFixed(4)}</td><td>${v.controls_only.log_loss.toFixed(4)}</td></tr>`:`<tr><td>${escapeHtml(p.name)}</td><td colspan="4">이전 시즌 표본 부족 · 시간 검증 불가</td></tr>`;
    }).join('');
    const shapeValidation=Object.values(data.pitches).flatMap(p=>['R','L'].map(hand=>{
      const v=p.shape_validation[hand];
      return v?`<tr><td>${escapeHtml(p.name)} ${hand}</td><td>${v.rmse_hb.toFixed(2)} / ${v.rmse_ivb.toFixed(2)}</td><td>${v.baseline_rmse_hb.toFixed(2)} / ${v.baseline_rmse_ivb.toFixed(2)}</td><td>${(100*v.coverage_50).toFixed(1)}% / ${(100*v.coverage_80).toFixed(1)}%</td></tr>`:`<tr><td>${escapeHtml(p.name)} ${hand}</td><td colspan="3">검증 표본 부족</td></tr>`;
    })).join('');
    const references=data.references.map(r=>`<li><a href="${escapeHtml(r.url)}" target="_blank" rel="noopener">${escapeHtml(r.name)}</a>: ${escapeHtml(r.use)}</li>`).join('');
    document.querySelector('#model-details').innerHTML=`<p>${data.seasons[0]}–${data.seasons.at(-1)} · 기대 무브먼트는 ${data.shape_pitches.toLocaleString('ko-KR')}개 유효 투구 전체, 헛스윙률은 ${data.swings.toLocaleString('ko-KR')}개 유효 스윙으로 적합합니다. ${data.trackman_shape_pitches.toLocaleString('ko-KR')}개 투구에는 안전하게 매칭한 TrackMan 무브먼트를 사용합니다. 같은 투구는 한 번만 학습합니다. 나머지는 구장·날짜·탄착 위치 보정 VB를 TrackMan 척도로 회귀 변환하며 2025 이후 계수는 2022–2024 매칭 자료에서 추정합니다.</p><p>시간 환산: M₀.₄ = M × (0.40 / t)². t는 VB의 55ft 속도·가속도로 계산하고, 매칭된 투구는 TrackMan 익스텐션으로 릴리스 지점까지 확장합니다. 나머지는 55ft 기준이므로 실제 릴리스부터의 체공 시간과 차이가 있습니다. 일정 가속도 가정의 근사이며 Magnus 가속도를 직접 복원한 값은 아닙니다. 입력 HB·IVB도 0.40초 환산값을 사용하세요.</p><p>기대 분포: μ = μₘ + ΣₘᵣΣᵣᵣ⁺(r − μᵣ), S = Σₘₘ − ΣₘᵣΣᵣᵣ⁺Σᵣₘ. 구종·투수 손별로 추정하고, r에는 추정 슬롯·55ft 수평/수직 릴리스 방향·체공 시간을 넣습니다. 슬라이더 각도에서 주변 ±5° 투구의 릴리스 조건을 사용합니다. 실제 어깨 팔각도와 신장 대비 익스텐션을 사용하는 원본 DDZ의 KBO 자료용 변형입니다.</p><p>헛스윙률은 ΔHB·ΔIVB의 이차항과 각도 상호작용을 포함한 로지스틱 회귀입니다. 구속·위치·카운트·타자 상대 손·투수 손·시즌·측정 출처·릴리스 방향·체공 시간을 통제합니다. 관측 밀도는 각도 5°·무브먼트 1인치로 평활하고, 밀도가 최고치의 5% 미만인 셀은 제외합니다. 성능 경계는 해당 등급의 실제 1인치 셀을 연결합니다. 각도 1°는 조작 간격이며 측정 정확도가 아닙니다.</p><div class="evidence-table"><table><thead><tr><th>시즌</th><th>기대 모형 투구</th><th>유효 스윙</th><th>TM 투구</th></tr></thead><tbody>${sources}</tbody></table></div><p>${data.seasons.at(-1)}년 전체를 제외하고 이전 시즌에서 기대 분포와 헛스윙률을 적합한 시간 검증입니다. 화면은 검증 후 전체 시즌으로 재적합했습니다. RMSE는 인치 단위로 낮을수록 좋습니다. 50%·80%는 정규 모형의 명목 범위이며 실제 포함률은 아래 검증값과 다를 수 있습니다. 기준선은 같은 손·구종의 무조건 평균입니다.</p><div class="evidence-table"><table><thead><tr><th>구종·손</th><th>HB / IVB RMSE</th><th>기준선 RMSE</th><th>실제 50% / 80% 포함률</th></tr></thead><tbody>${shapeValidation}</tbody></table></div><p>헛스윙률의 Log loss는 낮을수록 좋습니다. 개선이 없는 구종에는 화면에 경고를 표시합니다.</p><div class="evidence-table"><table><thead><tr><th>구종</th><th>검증 스윙</th><th>AUC</th><th>Δ 회귀 Log loss</th><th>통제변수만 Log loss</th></tr></thead><tbody>${validation}</tbody></table></div><p>실측 어깨 좌표·신장이 없고 미매칭·2군 TrackMan은 합치지 않습니다. 누락값 및 명시 범위 밖 값은 제외합니다. FF/SI/FC 외 기대 모형은 탐색적으로 적용합니다. DZ Delta는 기대 모양과의 차이이며 양수·음수만으로 구종의 좋고 나쁨이나 팔각도 변경의 인과 효과를 판단할 수 없습니다.</p><ul>${references}</ul>`;
    [angleInput,playButton,viewInput,compareHb,compareIvb].forEach(input=>input.disabled=false);
  }catch(error){
    data=null;stop();
    [angleInput,playButton,viewInput,compareHb,compareIvb].forEach(input=>input.disabled=true);
    status.textContent=`회귀 데이터를 불러오지 못했습니다: ${error.message}. 페이지를 새로고침해 주세요.`;
    document.querySelector('#model-details').textContent=status.textContent;
  }
}
load();
