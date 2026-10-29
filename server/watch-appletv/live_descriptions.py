"""Public current-programme synopses for native live cards."""
import concurrent.futures
from datetime import datetime
from zoneinfo import ZoneInfo
import requests
BBC={'bbcone':'bbc_one_london','bbctwo':'bbc_two_england','bbcfour':'bbc_four','bbcnews':'bbc_news24'}

def bbc_schedule(data):
    rows=[]
    for item in data.get('broadcasts',{}).get('elements',[]):
        try:
            start=datetime.fromisoformat(item['scheduled_start'].replace('Z','+00:00')).timestamp()
            end=datetime.fromisoformat(item['scheduled_end'].replace('Z','+00:00')).timestamp()
        except (KeyError,ValueError):continue
        ep=item.get('episode',{});syn=ep.get('synopses') or {}
        if not ep.get('title') or item.get('blanked'):continue
        rows.append({'title':ep['title'],'subtitle':syn.get('small') or syn.get('medium') or ep.get('subtitle',''),
            'start':start,'end':end,'time':datetime.fromtimestamp(start,ZoneInfo('Europe/London')).strftime('%H:%M'),
            'image':((ep.get('images') or {}).get('standard') or '').replace('{recipe}','640x360')})
    return {'_schedule':sorted(rows,key=lambda r:r['start'])}

def fetch_bbc():
    def fetch(pair):
        key,service=pair
        try:
            r=requests.get('https://ibl.api.bbc.co.uk/ibl/v1/channels/'+service+'/broadcasts',params={'per_page':20},timeout=(5,15));r.raise_for_status()
            return key,bbc_schedule(r.json())
        except requests.RequestException:return key,None
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:return dict((key,value) for key,value in pool.map(fetch,BBC.items()) if value)

def current(schedule,now):
    rows=schedule.get('_schedule',[])
    return {'now':next((r for r in rows if r['start']<=now<r['end']),None),'next':next((r for r in rows if r['start']>now),None)}

def five_synopsis(guide,candidates):
    from recommendations import normal_title
    now=guide.get('now') or {}
    if now.get('subtitle') or not now.get('title'):return
    title=normal_title(now['title'])
    matches=[p for p in candidates if normal_title(p['title'])==title and p.get('description')]
    if matches:now['subtitle']=matches[0]['description']
