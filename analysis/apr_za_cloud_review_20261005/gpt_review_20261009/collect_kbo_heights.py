"""사용자 승인된 KBO 공식 신장 수집. 현재 프로필을 과거 시즌 신장으로 단정하지 않는다."""
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
import subprocess, io, json, hashlib, re, html, time, csv
import pyarrow.parquet as pq
import requests
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
BASE='e48da3a26a617db67fbb51f6b1cbcb072b729eaf'
DATE_KST='2026-10-09'
CACHE=HERE/'profile_cache'

def parse_profile(content, player):
    text=content.decode('utf-8-sig',errors='replace')
    def value(key):
        m=re.search(r'id="[^"]*playerProfile_'+key+r'"[^>]*>(.*?)</span>',text,re.S)
        return html.unescape(re.sub('<[^>]+>','',m.group(1))).strip() if m else ''
    name=value('lblName');raw=value('lblHeightWeight')
    m=re.fullmatch(r'(\d{3})\s*cm\s*/\s*\d{2,3}\s*kg',raw)
    height=int(m.group(1)) if m else None
    status='ok' if name==player['player_name'] and height and 140<=height<=220 else ('name_mismatch' if name and name!=player['player_name'] else 'missing_profile_or_height')
    return {'profile_name':name,'height_cm':height if status=='ok' else None,'source_height_weight_text':raw,'status':status}

def fetch(player):
    pid=player['player_id'];url='https://www.koreabaseball.com/Record/Player/HitterDetail/Basic.aspx?playerId='+pid
    cache=CACHE/(pid+'.json')
    if cache.exists():return json.loads(cache.read_text())
    row={**player,'source_url':url,'retrieved_date_kst':DATE_KST,'profile_effective_date':None,'historical_height_verified':False}
    try:
        response=requests.get(url,timeout=(10,20));row['http_status']=response.status_code;row['final_url']=response.url
        if response.status_code!=200:row.update(status='http_error',height_cm=None)
        else:
            row.update(parse_profile(response.content,player));row['source_html_sha256']=hashlib.sha256(response.content).hexdigest()
    except requests.RequestException as e:row.update(status='request_error',height_cm=None,error_type=type(e).__name__)
    cache.write_text(json.dumps(row,ensure_ascii=False)+'\n');time.sleep(.15)
    return row

def main():
    CACHE.mkdir(exist_ok=True)
    data=subprocess.check_output(['git','show',BASE+':data/curated/players/player_bio.parquet'],cwd=ROOT)
    players=pq.ParquetFile(io.BytesIO(data)).read(columns=['player_id','player_name']).to_pylist()
    assert len({p['player_id'] for p in players})==len(players)
    rows=[]
    with ThreadPoolExecutor(max_workers=4) as ex:
        fs=[ex.submit(fetch,p) for p in players]
        for f in as_completed(fs):
            rows.append(f.result())
            if len(rows)%100==0:print('공식 프로필 조회',len(rows),'/',len(players),flush=True)
    rows.sort(key=lambda r:r['player_id'])
    (HERE/'kbo_heights.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2)+'\n')
    counts={s:sum(r['status']==s for r in rows) for s in sorted({r['status'] for r in rows})}
    result={'source_base':BASE,'bio_sha256':hashlib.sha256(data).hexdigest(),'retrieved_date_kst':DATE_KST,'population':'고정 player_bio의 모든 ID(투수 포함); 판단 적격 타자 포함률은 별도','requested':len(rows),'status_counts':counts,'matching':'공식 페이지 선수명과 저장소 이름의 완전 일치, 별칭/이름 변경은 수동 검토 전 제외','limitations':['현재 프로필 스냅샷이며 과거 시즌 등록 신장의 증거 아님','공식 사이트에 조회되지 않는 은퇴/외국 선수는 미확보','미확보 신장을 미래 ABS 존으로 자동 대체하지 않음']}
    (HERE/'kbo_height_acquisition.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n');print(json.dumps(result,ensure_ascii=False))
if __name__=='__main__':main()
