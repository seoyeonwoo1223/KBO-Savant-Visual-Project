const categories = [
  {key:'elite',label:'Elite',color:'#df243e',pattern:'elitePattern'},
  {key:'average',label:'Average',color:'#13aa42',pattern:'averagePattern'},
  {key:'dead',label:'Dead Zone',color:'#252525',pattern:'deadPattern'}
];
const angleInput=document.querySelector('#angle'), angleValue=document.querySelector('#angle-value');
const tabs=document.querySelector('#pitch-tabs'), handTabs=document.querySelector('#hand-tabs'), chart=document.querySelector('#movement-chart');
const rangeTable=document.querySelector('#range-table'), playButton=document.querySelector('#play'), status=document.querySelector('#sample-status');
const params=new URLSearchParams(location.search);
let data=null, selected='FF', selectedHand=params.get('hand')==='L'?'L':'R', timer=null;
const fmt=n=>`${n>0?'+':''}${n.toFixed(1)}`.replace('-', '−');
const rangeText=range=>`${fmt(range[0])} ~ ${fmt(range[1])}`;
const sx=x=>92+(x+30)*(616/60), sy=y=>574-(y+25)*(520/55);
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
  for(let x=-30;x<=30;x+=5) out+=`<line x1="${sx(x)}" y1="54" x2="${sx(x)}" y2="574" class="grid ${x===0?'zero':''}"/><text x="${sx(x)}" y="600" text-anchor="middle" class="axis-text">${x}</text>`;
  for(let y=-25;y<=30;y+=5) out+=`<line x1="92" y1="${sy(y)}" x2="708" y2="${sy(y)}" class="grid ${y===0?'zero':''}"/><text x="78" y="${sy(y)+5}" text-anchor="end" class="axis-text">${y}</text>`;
  return `${out}<text x="400" y="34" text-anchor="middle" class="direction-label">3B &lt; MOVES TOWARD &gt; 1B</text><text x="400" y="646" text-anchor="middle" class="axis-title">Horizontal Break (inches) · 포수 시점</text><text x="22" y="314" text-anchor="middle" class="axis-title" transform="rotate(-90 22 314)">Induced Vertical Break (inches)</text>`;
}

function armLine(angle){
  const rad=angle*Math.PI/180, x=25*Math.cos(rad)*handFactor(), y=25*Math.sin(rad);
  return `<line x1="${sx(0)}" y1="${sy(0)}" x2="${sx(x)}" y2="${sy(y)}" class="arm-line"/><text x="${sx(x*.55)}" y="${sy(y*.55)-10}" text-anchor="middle" class="arm-label">${angle}° estimated slot</text>`;
}

function zoneSvg(zone,cat){
  const cx=sx(zone.center[0]*handFactor()), cy=sy(zone.center[1]);
  const xx=zone.covariance[0][0]*(616/60)**2, yy=zone.covariance[1][1]*(520/55)**2;
  const xy=-handFactor()*zone.covariance[0][1]*(616/60)*(520/55);
  const discriminant=Math.hypot(xx-yy,2*xy), radius=Math.sqrt(-2*Math.log(.25));
  const rx=radius*Math.sqrt(Math.max(0,(xx+yy+discriminant)/2)), ry=radius*Math.sqrt(Math.max(0,(xx+yy-discriminant)/2));
  const rotation=Math.atan2(2*xy,xx-yy)*90/Math.PI;
  const rings=[1,.76,.52].map((scale,i)=>`<ellipse cx="0" cy="0" rx="${rx*scale}" ry="${ry*scale}" fill="${i===0?`url(#${cat.pattern})`:'none'}" stroke="${cat.color}" stroke-width="${i===0?2.4:1.25}" stroke-opacity="${i===0?.96:.48}"/>`).join('');
  return `<g class="zone zone-${cat.key}" data-center-hb="${zone.center[0]*handFactor()}" data-center-ivb="${zone.center[1]}" data-whiff="${zone.whiff_pct}" transform="translate(${cx} ${cy}) rotate(${rotation})"><title>${cat.label}: 추정 Whiff ${zone.whiff_pct.toFixed(1)}%</title>${rings}<circle r="3.5" fill="${cat.color}"/></g>`;
}

function render(){
  if(!data) return;
  const angle=Number(angleInput.value), pitch=data.pitches[selected], handLabel=selectedHand==='R'?'RHP':'LHP';
  const hand=pitch.hands[selectedHand], profile=hand.profiles[angle-data.angle_min], zones=profile.zones;
  angleValue.textContent=`${angle}°`;
  angleInput.setAttribute('aria-valuetext',`${angle}도, 릴리스 위치 기반 추정`);
  document.querySelector('#chart-kicker').textContent=`${angle}° · ${handLabel} · ${pitch.name.toUpperCase()}`;
  document.querySelector('#chart-title').textContent=`${pitch.name} Movement Map`;
  handTabs.querySelectorAll('button').forEach(b=>b.setAttribute('aria-pressed',String(b.dataset.hand===selectedHand)));
  tabs.querySelectorAll('button').forEach(b=>b.setAttribute('aria-pressed',String(b.dataset.pitch===selected)));
  rangeTable.innerHTML=zones?categories.map(cat=>{
    const z=viewZone(zones[cat.key]);
    return `<tr><td style="color:${cat.color}">${cat.label}</td><td>${rangeText(z.ivb)}</td><td>${rangeText(z.hb)}</td><td>${z.whiff_pct.toFixed(1)}%</td></tr>`;
  }).join(''):'<tr><td colspan="4">이 각도·손·구종은 표본 부족</td></tr>';
  const validationNote=!pitch.validation?' · 시간 검증 표본 부족 (실험)':pitch.validation.movement.log_loss>=pitch.validation.controls_only.log_loss?' · 최신 시즌 예측 개선 미확인':'';
  status.textContent=`${angle}° ± ${data.window_deg}° · ${profile.swings.toLocaleString('ko-KR')} 스윙 · ${profile.pitchers}명 · 기준 구속 ${hand.velocity_kmh.toFixed(1)} km/h${zones?'':` · 최소 ${data.min_swings}스윙·${data.min_pitchers}명 필요`}${validationNote}`;
  const description=zones?`Elite ${zones.elite.whiff_pct}%, Average ${zones.average.whiff_pct}%, Dead Zone ${zones.dead.whiff_pct}%, 추정 헛스윙률.`:'표본이 부족하여 프로파일을 표시하지 않습니다.';
  chart.innerHTML=`<title id="svg-title">${escapeHtml(pitch.name)} ${angle}도 ${handLabel} 무브먼트 회귀</title><desc id="svg-desc">포수 시점. ${description}</desc>${defs()}${grid()}<g clip-path="url(#plotClip)">${armLine(angle)}${zones?[...categories].reverse().map(cat=>zoneSvg(zones[cat.key],cat)).join(''):''}</g>${zones?'':`<text x="400" y="300" text-anchor="middle" class="empty-chart">이 구간은 관측 표본이 부족합니다</text><text x="400" y="327" text-anchor="middle" class="axis-text">다른 각도·투수 손·구종을 선택하세요</text>`}`;
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
handTabs.querySelectorAll('button').forEach(button=>button.addEventListener('click',()=>{selectedHand=button.dataset.hand;render();}));
document.addEventListener('visibilitychange',()=>{if(document.hidden) stop();});

async function load(){
  playButton.disabled=true;
  try{
    const response=await fetch('../data/movement_zones/profiles.json?v=20261001-1');
    if(!response.ok) throw new Error(`HTTP ${response.status}`);
    data=await response.json();
    if(data.schema_version!==1||!data.pitches.FF) throw new Error('회귀 데이터 형식 오류');
    angleInput.min=data.angle_min;angleInput.max=data.angle_max;
    if(params.has('angle')&&Number.isFinite(Number(params.get('angle')))) angleInput.value=String(Math.max(data.angle_min,Math.min(data.angle_max,Math.round(Number(params.get('angle'))))));
    if(data.pitches[params.get('pitch')]) selected=params.get('pitch');
    renderTabs();render();
    const sources=data.sources.map(s=>`<tr><td>${s.season}</td><td>${s.vb_pitches.toLocaleString('ko-KR')}</td><td>${s.eligible_swings.toLocaleString('ko-KR')}</td><td>${s.trackman_swings.toLocaleString('ko-KR')}</td></tr>`).join('');
    const validation=Object.values(data.pitches).map(p=>{
      const v=p.validation;
      return v?`<tr><td>${escapeHtml(p.name)}</td><td>${v.test_swings.toLocaleString('ko-KR')}</td><td>${v.movement.auc.toFixed(3)}</td><td>${v.movement.log_loss.toFixed(4)}</td><td>${v.controls_only.log_loss.toFixed(4)}</td></tr>`:`<tr><td>${escapeHtml(p.name)}</td><td colspan="4">이전 시즌 표본 부족 · 시간 검증 불가</td></tr>`;
    }).join('');
    document.querySelector('#model-details').innerHTML=`<p>${data.seasons[0]}–${data.seasons.at(-1)} · ${data.swings.toLocaleString('ko-KR')}개 유효 스윙 중 ${data.trackman_swings.toLocaleString('ko-KR')}개에 투구 단위로 매칭한 TrackMan 무브먼트를 사용합니다. 같은 투구는 한 번만 학습합니다. 나머지는 구장·날짜·탄착 위치 보정 VB를 TrackMan 척도로 회귀 변환합니다. 2025 이후 변환 계수는 2022–2024 매칭 자료에서 추정합니다.</p><p>각도·HB·IVB의 이차항과 상호작용을 포함한 로지스틱 회귀입니다. 구속·위치·볼카운트·타자 상대 손·투수 손·시즌·측정 출처를 통제합니다. 각도 5°와 무브먼트 1인치 폭으로 관측 분포를 평활합니다. 각도 1°는 조작 간격이며 추정 정확도 1°를 뜻하지 않습니다.</p><div class="evidence-table"><table><thead><tr><th>시즌</th><th>VB 전체 투구</th><th>유효 스윙</th><th>TM 스윙</th></tr></thead><tbody>${sources}</tbody></table></div><p>${data.seasons.at(-1)}년 전체를 분리한 시간 검증입니다. 표의 값은 이전 시즌으로 학습한 결과이며, 화면은 검증 후 전체 시즌으로 다시 적합했습니다. Log loss는 낮을수록 좋으며, 개선이 없는 구종의 성능 우위는 확정할 수 없습니다.</p><div class="evidence-table"><table><thead><tr><th>구종</th><th>검증 스윙</th><th>AUC</th><th>회귀 Log loss</th><th>통제변수만 Log loss</th></tr></thead><tbody>${validation}</tbody></table></div><p>실측 어깨 좌표가 없고, 미매칭·2군 TrackMan은 학습에 합치지 않습니다. 타자 손·무브먼트·궤적·카운트 누락 및 명시 범위 밖 값도 제외합니다. 모델은 관측 연관성을 보여 주며 팔각도 변경의 인과 효과를 보장하지 않습니다.</p>`;
    angleInput.disabled=false;playButton.disabled=false;
  }catch(error){
    data=null;stop();
    status.textContent=`회귀 데이터를 불러오지 못했습니다: ${error.message}. 페이지를 새로고침해 주세요.`;
    document.querySelector('#model-details').textContent=status.textContent;
  }
}
load();
