// Count-based aggregation shared by every widget. No DOM or network work here.
const TrendlineMath = (() => {
  let fields = [], index = {};
  const METRICS = {
    velocity: {label:"평균 구속", unit:"km/h", numerator:"velocity_sum", denominator:"velocity_n", scale:1, min:50, sample:"유효 구속", roles:["pitcher"]},
    hb: {label:"HB", unit:"in", numerator:"hb_sum", denominator:"hb_n", scale:1, min:50, sample:"무브먼트 측정 투구", roles:["pitcher"], byType:true, noLeague:true},
    ivb: {label:"IVB", unit:"in", numerator:"ivb_sum", denominator:"ivb_n", scale:1, min:50, sample:"무브먼트 측정 투구", roles:["pitcher"], byType:true},
    usage: {label:"구종 사용률", unit:"%", numerator:"pitches", denominator:"pitches", scale:100, min:50, sample:"투구", roles:["pitcher"]},
    k: {label:"K%", unit:"%", numerator:"k", denominator:"pa", scale:100, min:30, sample:"결과 확인 타석", roles:["pitcher","batter"], overall:true},
    bb: {label:"BB%", unit:"%", numerator:"bb", denominator:"pa", scale:100, min:30, sample:"결과 확인 타석", roles:["pitcher","batter"], overall:true},
    swing: {label:"Swing%", unit:"%", numerator:"swings", denominator:"swing_n", scale:100, min:50, sample:"스윙 확인 투구", roles:["pitcher","batter"], league:true},
    o_swing: {label:"O-Swing%", unit:"%", numerator:"o_swings", denominator:"o_n", scale:100, min:50, sample:"존 밖 투구", roles:["pitcher","batter"], league:true},
    z_swing: {label:"Z-Swing%", unit:"%", numerator:"z_swings", denominator:"z_n", scale:100, min:50, sample:"존 안 투구", roles:["pitcher","batter"], league:true},
    contact: {label:"Contact%", unit:"%", numerator:"contacts", denominator:"contact_n", scale:100, min:30, sample:"접촉 확인 스윙", roles:["pitcher","batter"]},
    whiff: {label:"Whiff%", unit:"%", numerator:"whiffs", denominator:"contact_n", scale:100, min:30, sample:"접촉 확인 스윙", roles:["pitcher","batter"]},
    swstr: {label:"SwStr%", unit:"%", numerator:"whiffs", denominator:"swstr_n", scale:100, min:50, sample:"헛스윙 확인 투구", roles:["pitcher","batter"]},
    zone: {label:"Zone%", unit:"%", numerator:"in_zone", denominator:"location_n", scale:100, min:50, sample:"위치 확인 투구", roles:["pitcher","batter"]},
  };
  function setup(names) { fields = names; index = Object.fromEntries(names.map((name,i)=>[name,i])); }
  function zero() { return fields.map(()=>0); }
  function sum(rows, code="all") {
    const result=zero();
    for (const row of rows) {
      const values=code==="all" ? row.counts : row.types?.[code];
      if (values) values.forEach((v,i)=>result[i]+=v);
    }
    return result;
  }
  function value(counts, metric, overall=counts) {
    const spec=METRICS[metric];
    const n=(metric==="usage" ? overall : counts)?.[index[spec.denominator]] || 0;
    const numerator=counts?.[index[spec.numerator]] || 0;
    return {value:n ? numerator/n*spec.scale : null, n, numerator, low:n<spec.min, missing:spec.overall?(counts?.[index.pa_unknown]||0):0};
  }
  function periodBins(games, mode, start, end, window=1) {
    const filtered=games.filter(g=>g.date>=start && g.date<=end).sort((a,b)=>a.date.localeCompare(b.date)||a.game_id.localeCompare(b.game_id));
    if (mode==="game") {
      let queue=[], season="";
      return filtered.map(game=>{
        const year=game.date.slice(0,4);
        if (year!==season) { queue=[]; season=year; }
        queue.push(game); if (queue.length>window) queue.shift();
        return {key:game.game_id, label:game.date, x:Date.parse(`${game.date}T00:00:00Z`), start:queue[0].date, end:game.date, rows:[...queue], games:queue.length};
      });
    }
    const bins=new Map();
    const cursor=new Date(`${start.slice(0,7)}-01T00:00:00Z`);
    while (cursor.toISOString().slice(0,10)<=end) {
      const date=cursor.toISOString().slice(0,10), key=date.slice(0,mode==="season"?4:7);
      if (!bins.has(key)) {
        const last=mode==="season" ? `${key}-12-31` : new Date(Date.UTC(cursor.getUTCFullYear(),cursor.getUTCMonth()+1,0)).toISOString().slice(0,10);
        const first=mode==="season" ? `${key}-01-01` : `${key}-01`;
        bins.set(key,{key,label:key,x:mode==="season"?Number(key):Date.parse(`${first}T00:00:00Z`),start:first<start?start:first,end:last>end?end:last,rows:[],games:0});
      }
      cursor.setUTCMonth(cursor.getUTCMonth()+1);
    }
    for (const game of filtered) {
      const bin=bins.get(game.date.slice(0,mode==="season"?4:7));
      bin.rows.push(game); bin.games++;
    }
    return [...bins.values()];
  }
  function leagueIndex(days) {
    const sorted=[...days].sort((a,b)=>a.date.localeCompare(b.date));
    const codes=["all",...new Set(sorted.flatMap(d=>Object.keys(d.types||{})))];
    const totals=Object.fromEntries(codes.map(c=>[c,[zero()]]));
    for (const day of sorted) {
      for (const code of codes) {
        const next=[...totals[code].at(-1)], values=code==="all"?day.counts:day.types?.[code];
        if (values) values.forEach((v,i)=>next[i]+=v);
        totals[code].push(next);
      }
    }
    return {dates:sorted.map(d=>d.date), totals};
  }
  function lowerBound(dates,date,after=false) {
    let low=0,high=dates.length;
    while(low<high) { const mid=(low+high)>>1; if(dates[mid]<date || (after && dates[mid]===date)) low=mid+1; else high=mid; }
    return low;
  }
  function leagueRange(league,start,end,code="all") {
    const totals=league.totals[code]; if(!totals) return zero();
    const a=lowerBound(league.dates,start), b=lowerBound(league.dates,end,true);
    return totals[b].map((v,i)=>v-totals[a][i]);
  }
  function series(bins,metric,code,league) {
    return bins.map(bin=>{
      const counts=sum(bin.rows,code), overall=sum(bin.rows);
      const baseline=leagueRange(league,bin.start,bin.end,code), leagueAll=leagueRange(league,bin.start,bin.end);
      return {...bin, ...value(counts,metric,overall), league:value(baseline,metric,leagueAll)};
    });
  }
  function axis(values,unit) {
    const valid=values.filter(Number.isFinite); if(!valid.length) return {min:0,max:100,step:20};
    const low=Math.min(...valid), high=Math.max(...valid), spread=Math.max(high-low,unit==="%"?8:4);
    const target=spread/4, power=10**Math.floor(Math.log10(target));
    const step=[1,2,5,10].map(v=>v*power).find(v=>v>=target);
    let min=Math.floor((low-spread*.12)/step)*step, max=Math.ceil((high+spread*.12)/step)*step;
    if(unit==="%") { min=Math.max(0,min); max=Math.min(100,max); }
    if(max<=min) max=min+step;
    return {min,max,step};
  }
  return {METRICS,setup,zero,sum,value,periodBins,leagueIndex,leagueRange,series,axis};
})();
