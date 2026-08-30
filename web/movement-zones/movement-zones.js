const Z=(ivb,hb,ivbLabel=null,hbLabel=null)=>({ivb,hb,ivbLabel,hbLabel});
const D={
  60:{
    FF:['4-Seam',Z([18,22],[4,8]),Z([15,18],[5,9]),Z([11,14],[6,10])],
    SI:['Sinker',Z([8,11],[14,18]),Z([6,9],[11,14]),Z([10,13],[8,11])],
    FC:['Cutter',Z([10,13],[2,5]),Z([8,11],[0,3]),Z([5,8],[-1,2])],
    GY:['Gyro Slider',Z([1,3],[-5,-2]),Z([2,5],[-7,-4]),Z([5,8],[-10,-7])],
    SW:['Sweeper',Z([-2,1],[-19,-15]),Z([0,3],[-15,-11]),Z([4,7],[-10,-7])],
    CU:['Curveball',Z([-16,-12],[-6,-2]),Z([-12,-9],[-7,-3]),Z([-8,-5],[-6,-3])],
    CH:['Changeup',Z([3,6],[12,16]),Z([5,8],[10,13]),Z([8,11],[7,10])]
  },
  45:{
    FF:['4-Seam',Z([15,19],[5,9]),Z([12,15],[6,10]),Z([9,12],[7,11])],
    SI:['Sinker',Z([6,9],[15,19]),Z([5,8],[12,15]),Z([8,11],[9,12])],
    FC:['Cutter',Z([8,11],[3,6]),Z([6,9],[1,4]),Z([4,7],[-1,2])],
    GY:['Gyro Slider',Z([0,2],[-6,-3]),Z([1,4],[-8,-5]),Z([4,7],[-11,-8])],
    SW:['Sweeper',Z([-3,0],[-20,-16]),Z([-1,2],[-16,-12]),Z([3,6],[-11,-8])],
    CU:['Curveball',Z([-15,-11],[-8,-4]),Z([-11,-8],[-8,-4]),Z([-7,-4],[-7,-4])],
    CH:['Changeup',Z([2,5],[14,18]),Z([4,7],[11,14]),Z([7,10],[8,11])]
  },
  30:{
    FF:['4-Seam',Z([10,14],[8,12]),Z([8,11],[9,13]),Z([5,8],[8,11])],
    SI:['Sinker',Z([4,7],[16,21]),Z([3,6],[13,17]),Z([6,9],[10,13])],
    FC:['Cutter',Z([6,9],[4,7]),Z([4,7],[2,5]),Z([2,5],[0,2])],
    GY:['Gyro Slider',Z([-1,2],[-5,-2]),Z([1,3],[-7,-4]),Z([4,7],[-10,-7])],
    SW:['Sweeper',Z([-4,-1],[-21,-17]),Z([-2,1],[-17,-13]),Z([2,5],[-12,-9])],
    CU:['Curveball',Z([-13,-9],[-10,-6]),Z([-10,-7],[-9,-5]),Z([-6,-3],[-7,-4])],
    CH:['Changeup',Z([1,4],[16,20]),Z([3,6],[13,16]),Z([6,9],[10,13])]
  },
  15:{
    FF:['Fastball / Sinker',Z([-2,2],[18,23],null,'+18~22+'),Z([3,6],[14,17]),Z([7,10],[10,13])],
    FC:['Cutter',Z([0,3],[6,10]),Z([3,5],[3,6]),Z([6,8],[0,2])],
    GY:['Gyro Slider',Z([-1,2],[-5,-2]),Z([2,5],[-7,-4]),Z([6,9],[-10,-7])],
    SW:['Sweeper',Z([-4,0],[-23,-18],null,'−18~−22+'),Z([-1,2],[-16,-13]),Z([3,6],[-10,-7])],
    CH:['Changeup',Z([-3,1],[17,22],null,'+17~21+'),Z([2,5],[13,16]),Z([6,9],[9,12])],
    CU:['Curveball',Z([-8,-5],[-16,-12]),Z([-4,-2],[-11,-8]),Z([1,3],[-7,-4])],
    SL:['Slurve',Z([-3,-1],[-14,-10]),Z([-1,1],[-10,-7]),Z([2,5],[-6,-3])]
  }
};

const angles=[15,30,45,60], categories=[
  {key:'elite',label:'Elite',index:1,color:'#df243e',pattern:'elitePattern'},
  {key:'average',label:'Average',index:2,color:'#13aa42',pattern:'averagePattern'},
  {key:'dead',label:'Dead Zone',index:3,color:'#252525',pattern:'deadPattern'}
];
const pitchOrder=['FF','SI','FC','GY','SW','CU','CH','SL'];
const angleInput=document.querySelector('#angle'), angleValue=document.querySelector('#angle-value');
const tabs=document.querySelector('#pitch-tabs'), chart=document.querySelector('#movement-chart');
const rangeTable=document.querySelector('#range-table'), playButton=document.querySelector('#play');
let selected='FC', timer=null;

const fmt=n=>`${n>0?'+':''}${n}`.replace('-', '−');
const rangeText=(range,label)=>label||`${fmt(range[range[0] < 0 && range[1] < 0 ? 1 : 0])}~${fmt(range[range[0] < 0 && range[1] < 0 ? 0 : 1])}`;
const sx=x=>92+(x+25)*(616/50), sy=y=>574-(y+20)*(520/45);
const escapeHtml=s=>s.replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));

function renderTabs(angle){
  const available=pitchOrder.filter(key=>D[angle][key]);
  if(!available.includes(selected)) selected=available[0];
  tabs.innerHTML=available.map(key=>`<button type="button" role="tab" data-pitch="${key}" aria-selected="${key===selected}">${escapeHtml(D[angle][key][0])}</button>`).join('');
  tabs.querySelectorAll('button').forEach(button=>button.addEventListener('click',()=>{selected=button.dataset.pitch;render();}));
}

function defs(){return `<defs>
  <pattern id="elitePattern" width="8" height="8" patternUnits="userSpaceOnUse" patternTransform="rotate(45)"><rect width="8" height="8" fill="#df243e" fill-opacity=".08"/><line x1="0" y1="0" x2="0" y2="8" stroke="#df243e" stroke-opacity=".35" stroke-width="2"/></pattern>
  <pattern id="averagePattern" width="8" height="8" patternUnits="userSpaceOnUse"><rect width="8" height="8" fill="#13aa42" fill-opacity=".07"/><line x1="0" y1="2" x2="8" y2="2" stroke="#13aa42" stroke-opacity=".3" stroke-width="2"/></pattern>
  <pattern id="deadPattern" width="7" height="7" patternUnits="userSpaceOnUse"><rect width="7" height="7" fill="#252525" fill-opacity=".08"/><circle cx="2" cy="2" r="1" fill="#252525" fill-opacity=".3"/></pattern>
  <filter id="soft"><feGaussianBlur stdDeviation=".22"/></filter>
  </defs>`}

function grid(){
  let out='';
  for(let x=-25;x<=25;x+=5) out+=`<line x1="${sx(x)}" y1="54" x2="${sx(x)}" y2="574" class="grid ${x===0?'zero':''}"/><text x="${sx(x)}" y="600" text-anchor="middle" class="axis-text">${x}</text>`;
  for(let y=-20;y<=25;y+=5) out+=`<line x1="92" y1="${sy(y)}" x2="708" y2="${sy(y)}" class="grid ${y===0?'zero':''}"/><text x="78" y="${sy(y)+5}" text-anchor="end" class="axis-text">${y}</text>`;
  return `${out}<text x="400" y="618" text-anchor="middle" class="direction-label">1B &lt; MOVES TOWARD &gt; 3B</text><text x="400" y="646" text-anchor="middle" class="axis-title">Horizontal Break (inches) · 투수 시점</text><text x="22" y="314" text-anchor="middle" class="axis-title" transform="rotate(-90 22 314)">Induced Vertical Break (inches)</text>`;
}

function armLine(angle){
  const radians=angle*Math.PI/180, xEnd=Math.min(25,25/Math.tan(radians)), yEnd=Math.min(25,25*Math.tan(radians));
  return `<line x1="${sx(0)}" y1="${sy(0)}" x2="${sx(xEnd)}" y2="${sy(yEnd)}" class="arm-line"/><text x="${sx(xEnd*.55)+8}" y="${sy(yEnd*.55)-8}" class="arm-label">${angle}° arm angle</text>`;
}

function zoneSvg(zone,cat){
  const [y0,y1]=zone.ivb,[x0,x1]=zone.hb,cx=(sx(x0)+sx(x1))/2,cy=(sy(y0)+sy(y1))/2;
  const rx=Math.max(13,Math.abs(sx(x1)-sx(x0))/2),ry=Math.max(13,Math.abs(sy(y1)-sy(y0))/2);
  const rings=[1,.76,.52].map((scale,i)=>`<ellipse cx="${cx}" cy="${cy}" rx="${rx*scale}" ry="${ry*scale}" fill="${i===0?`url(#${cat.pattern})`:'none'}" stroke="${cat.color}" stroke-width="${i===0?2.4:1.25}" stroke-opacity="${i===0?.96:.48}"/>`).join('');
  return `<g class="zone zone-${cat.key}" filter="url(#soft)">${rings}<circle cx="${cx}" cy="${cy}" r="3.5" fill="${cat.color}"/></g>`;
}

function render(){
  const angle=angles[Number(angleInput.value)]; renderTabs(angle);
  const pitch=D[angle][selected],name=pitch[0];
  angleValue.textContent=`${angle}°`;
  document.querySelector('#chart-kicker').textContent=`${angle}° · ${name.toUpperCase()}`;
  document.querySelector('#chart-title').textContent=`${name} Movement Map`;
  rangeTable.innerHTML=categories.map(cat=>{const z=pitch[cat.index];return `<tr><td style="color:${cat.color}">${cat.label}</td><td>${rangeText(z.ivb,z.ivbLabel)}</td><td>${rangeText(z.hb,z.hbLabel)}</td></tr>`}).join('');
  chart.innerHTML=`${defs()}<style>.grid{stroke:#d9dddd;stroke-width:1}.grid.zero{stroke:#70787b;stroke-width:1.6}.axis-text{font:12px Arial;fill:#667075}.axis-title{font:700 14px Arial;fill:#343a3d}.direction-label{font:700 11px Arial;letter-spacing:.08em;fill:#737b7e}.arm-line{stroke:#878f92;stroke-width:1.8;stroke-dasharray:7 6}.arm-label{font:italic 12px Arial;fill:#767e82}.zone{transition:opacity .2s}</style>${grid()}${armLine(angle)}${[...categories].reverse().map(cat=>zoneSvg(pitch[cat.index],cat)).join('')}`;
}

function stop(){clearInterval(timer);timer=null;playButton.textContent='▶';playButton.setAttribute('aria-pressed','false');playButton.setAttribute('aria-label','팔각도 자동 재생');}
function play(){timer=setInterval(()=>{angleInput.value=(Number(angleInput.value)+1)%angles.length;render();},1200);playButton.textContent='Ⅱ';playButton.setAttribute('aria-pressed','true');playButton.setAttribute('aria-label','팔각도 자동 재생 정지');}
angleInput.addEventListener('input',()=>{stop();render();});
playButton.addEventListener('click',()=>timer?stop():play());
render();
