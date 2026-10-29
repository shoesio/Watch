"""Native tvOS routing. No provider credentials or media keys cross the Pi API."""
import hashlib,re,time
from urllib.parse import urlparse
from concurrent.futures import ThreadPoolExecutor
import requests

FIVE_STANDARD=('C5','C7','C6','C0','C8')

def five_channels(feed):
    rows=(feed.get('filters') or {}).get('contents') or []
    found={}
    for row in rows:
        key=row.get('channel')
        if row.get('live') is True and key in FIVE_STANDARD and row.get('title'):
            found[key]={'id':'appletv_five_'+key,'title':row['title'].strip(),'provider':'Channel 5','provider_id':'channel5','live_channel':key,
                'genre':'Live TV','description':'Watch '+row['title'].strip()+' live.',
                'artwork':f'https://api-images.channel5.com/otis/images/channel/{key}/640x360.jpg',
                'episodes':[{'id':'appletv_five_live_'+key,'provider_id':'channel5','provider_episode_id':key,'kind':'provider','title':row['title'].strip(),'live':True}]}
    return [found[key] for key in FIVE_STANDARD if key in found]

def five_guide(data,now):
    rows=sorted([r for r in data.get('schedule',[]) if isinstance(r.get('tran_s'),(float,int))],key=lambda r:r['tran_s'])
    result={}
    for i,row in enumerate(rows):
        start=row['tran_s'];end=rows[i+1]['tran_s'] if i+1<len(rows) else start+float(row.get('duration') or 0)
        value={'title':row.get('title',''),'subtitle':row.get('s_desc') or row.get('description',''),'start':start,'end':end}
        if start<=now<end:result['now']=value
        elif start>now and 'next' not in result:result['next']=value
    return result

def refresh_five():
    response=requests.get('https://feeds-api.channel5.com/collections/PLC_5LiveTVPageSubNav/concise.json',params={'vod_available':'my5desktop'},timeout=15)
    response.raise_for_status();channels=five_channels(response.json())
    if not channels:raise ValueError('No supported Channel 5 channels')
    def guide(p):
        try:
            r=requests.get('https://feeds-api.channel5.com/feed/now-next/'+p['live_channel']+'.json',timeout=10);r.raise_for_status()
            p['_guide']=five_guide(r.json(),time.time())
        except requests.RequestException:pass
        return p
    with ThreadPoolExecutor(max_workers=3) as pool:return list(pool.map(guide,channels))

def descriptor(bridge,ident):
    version=getattr(bridge.watch,'index',{}).get(ident)
    if not version:return None
    pairs=version.get('sources',[])
    if not pairs:return None
    # Preserve the existing measured-quality source ordering across providers.
    source,provider=max(pairs,key=bridge.watch.quality.rank)
    provider_id=source.get('provider_id')
    if provider_id=='channel5' and re.fullmatch(r'[A-Za-z0-9-]{1,80}',str(source.get('provider_episode_id',''))):
        route={'provider':'channel5','id':source['provider_episode_id'],'live':bool(source.get('live'))}
    elif provider_id=='u' and re.fullmatch(r'[0-9]{1,20}',str(source.get('provider_episode_id',''))):
        route={'provider':'u','id':source['provider_episode_id'],'live':False}
    elif provider_id=='itv':
        from itv_catalogue import playlist
        if not playlist(source.get('playlist_url'),bool(source.get('live'))):return None
        route={'provider':'itv','id':source['provider_episode_id'],'live':bool(source.get('live')),'playlist_url':source['playlist_url'],'premium':source.get('premium',False)}
    elif provider=='BBC iPlayer' and source.get('kind')=='plugin':
        route={'provider':'bbc','id':source['id'],'live':bool(source.get('live'))}
    else:return None
    group=next((p for p in bridge.watch.groups if any(e['id']==ident for e in p['episodes'])),None)
    if not group:return None
    public=next(e for e in group['episodes'] if e['id']==ident)
    meta={**public,'id':ident,'title':source['title'],'description':source.get('description') or group.get('description',''),
        'show_title':group['title'],'show_logo':group.get('show_logo'),'brands':bridge.watch.brands([provider]),
        'duration_seconds':public.get('duration_seconds',0),'start_position':0,'live':route['live'],'quality':None}
    return source,route,meta

def bbc_media_url(url):
    p=urlparse(url)
    return p.scheme=='https' and not p.username and not p.password and p.port in (None,443) and bool(p.hostname) and any(p.hostname.endswith('.'+host) or p.hostname==host for host in ('bbci.co.uk','bbc.co.uk','akamaized.net','akamaihd.net','bidi.net.uk'))

def clear_hls(text):
    if not text.startswith('#EXTM3U'):return False
    return not any(line.startswith(('#EXT-X-KEY:','#EXT-X-SESSION-KEY:')) and 'METHOD=NONE' not in line for line in text.splitlines())

def bbc_direct(bridge,source):
    """Resolve only clear BBC HLS; native AVPlayer downloads all media itself.

    Unsupported muxed/DASH streams or request-bound streams retain the relay.
    Never opens a media reader, launches ffmpeg or touches a protected resolver.
    """
    from streamlink.stream.hls import HLSStream
    session=None
    try:
        resolver=getattr(bridge,'session_hls',bridge.session_stream)
        session,stream=resolver({k:v for k,v in source.items() if k!='_start_offset'})
        if not isinstance(stream,HLSStream):return None
        url=stream.url
        # Some selector entries advertise HTTP even when the same BBC CDN
        # endpoint serves HTTPS. Verify HTTPS rather than accepting clear HTTP.
        if urlparse(url).scheme=='http':url=urlparse(url)._replace(scheme='https').geturl()
        if not bbc_media_url(url):return None
        args=getattr(stream,'args',{}) or {}
        headers=args.get('headers') or {}
        if args.get('cookies') or any(k.lower() in ('authorization','cookie') for k in headers):return None
        # Fetch independently of the signed-in Streamlink session: this confirms
        # Apple TV does not need a Pi cookie/header to read the selected playlist.
        r=requests.get(url,timeout=15,allow_redirects=False)
        if r.status_code!=200 or len(r.content)>2_000_000 or not clear_hls(r.text):return None
        # HLSStream normally already identifies a media playlist, not a master.
        # Keep unexpected master/codec selection on the established relay route.
        if '#EXT-X-STREAM-INF:' in r.text or '#EXTINF:' not in r.text:return None
        return url
    finally:
        if session is not None:
            close=getattr(getattr(session,'http',None),'close',None)
            if close:close()
