"""Now/next from the broadcaster's public live pages, refreshed in background."""
import asyncio
from datetime import datetime,timedelta
import json
import re
import time
from zoneinfo import ZoneInfo
import requests

CHANNELS={'bbcone':'BBC One','bbctwo':'BBC Two','bbcfour':'BBC Four','bbcnews':'BBC News'}

def parse_channel4_page(html, now):
    match = re.search(r'<script[^>]*id="initialData"[^>]*>\s*var initialData\s*=\s*(.*?)</script>', html, re.S)
    if not match: raise ValueError('Channel 4 guide data not found')
    data = json.loads(match[1].strip().rstrip(';'))
    channels = {}
    for key in ('C4','E4','M4','F4','4S'):
        items = []
        for p in data.get('channels', {}).get(key, {}).get('programmes', []):
            try:
                start = datetime.fromisoformat(p['startDate'].replace('Z','+00:00')).timestamp()
                end = datetime.fromisoformat(p['endDate'].replace('Z','+00:00')).timestamp()
            except (KeyError, ValueError): continue
            items.append({'title':p.get('title') or p.get('brandTitle',''), 'subtitle':p.get('summary',''),
                'start':start,'end':end,'time':datetime.fromtimestamp(start,ZoneInfo('Europe/London')).strftime('%H:%M'),
                'image':(p.get('image') or {}).get('url','').replace('{&resize}','&resize=640:360')})
        items.sort(key=lambda x:x['start'])
        channels[key] = {'_schedule':items, 'checked_at':now}
    return channels

def parse_page(html,now):
    match=re.search(r'window\.__IPLAYER_REDUX_STATE__\s*=\s*(.*?);?\s*</script>',html,re.S)
    if not match:raise ValueError('Guide data not found')
    state=json.loads(match[1].rstrip(';'))
    items=state.get('broadcasts',{}).get('items',[])
    result=[]
    for item in items:
        start=float(item.get('scheduledStart') or 0)
        if not start:continue
        local=datetime.fromtimestamp(start,ZoneInfo('Europe/London'))
        try:
            hour,minute=map(int,item['endTime'].split(':'))
            end=local.replace(hour=hour,minute=minute,second=0)
            if end.timestamp()<=start:end+=timedelta(days=1)
        except (KeyError,ValueError):continue
        title=item.get('title','')
        if not title:continue
        result.append({'title':title,'subtitle':item.get('subtitle',''),'start':start,'end':end.timestamp(),
            'time':local.strftime('%H:%M'),'image':item.get('image','').replace('{recipe}','640x360')})
    result.sort(key=lambda x:x['start'])
    current=next((x for x in result if x['start']<=now<x['end']),None)
    next_item=next((x for x in result if x['start']>now),None)
    return {'now':current,'next':next_item,'_schedule':result,'checked_at':now}

class LiveGuide:
    def __init__(self):self.channels={}
    def fetch(self,slug):
        r=requests.get('https://www.bbc.co.uk/iplayer/live/'+slug,timeout=15,headers={'User-Agent':'Mozilla/5.0'})
        r.raise_for_status();return parse_page(r.text,time.time())
    async def refresh(self):
        async def one(slug):
            try:self.channels[slug]=await asyncio.to_thread(self.fetch,slug)
            except Exception:pass
        async def c4():
            try:
                def fetch():
                    r=requests.get('https://www.channel4.com/tv-guide',timeout=15);r.raise_for_status()
                    return parse_channel4_page(r.text,time.time())
                self.channels.update(await asyncio.to_thread(fetch))
            except Exception:pass
        await asyncio.gather(*(one(s) for s in CHANNELS), c4())
    async def run(self):
        while True:
            await self.refresh();await asyncio.sleep(120)
    def get(self,slug):
        data=self.channels.get(slug,{})
        if time.time()-data.get('checked_at',0)>300:return {}
        now=time.time();current=data.get('now');nxt=data.get('next')
        if '_schedule' in data:
            current=next((x for x in data['_schedule'] if x['start']<=now<x['end']),None)
            nxt=next((x for x in data['_schedule'] if x['start']>now),None)
        if current and not current['start']<=now<current['end']:current=None
        if nxt and not nxt['start']>now:nxt=None
        return {'now':current,'next':nxt}
