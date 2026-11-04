"""Public ITVX catalogue/live metadata. Account and licence traffic stays on Apple TV."""
import concurrent.futures,datetime,html,json,re,time
from urllib.parse import urlparse
from zoneinfo import ZoneInfo
import requests

def get(url,**params):
 r=requests.get(url,params=params,timeout=(5,8),headers={'User-Agent':'WatchHome/1.4 (personal TV metadata)'});r.raise_for_status();return r

def image(value):
 if not isinstance(value,str):return ''
 for key,replacement in {'width':'960','height':'540','quality':'80','blur':'0','bg':'false','class':'04_DesktopCTV_RailTileLandscape','aspect_ratio':'16x9','distributionPartner':'itv_hub','treatment':'title','fallback':'standard','image_format':'png'}.items():value=value.replace('{'+key+'}',replacement)
 p=urlparse(value)
 return value if p.scheme=='https' and not p.username and not p.password and p.hostname and (p.hostname.endswith('.itv.com') or p.hostname.endswith('.ctfassets.net')) and '{' not in value else ''

def playlist(url,live=False):
 p=urlparse(str(url))
 return p.scheme=='https' and not p.username and not p.password and not p.query and not p.fragment and p.port is None and p.hostname in (('simulcast.itv.com','stream-starter.fastly.ottstream.itv.com') if live else ('magni.itv.com',)) and p.path.startswith('/playlist/itvonline/')

def props(text):
 m=re.search(r'<script\b[^>]*\bid=["\']__NEXT_DATA__["\'][^>]*>([\s\S]*?)</script>',text)
 if not m:raise ValueError('ITV metadata unavailable')
 return json.loads(m[1])['props']['pageProps']

def show(row):
 if row.get('contentType')=='collection' or row.get('collectionId'):return None
 key=(row.get('encodedProgrammeId') or {}).get('letterA') or row.get('programmeId') or (row.get('legacyId') or {}).get('apiEncoded')
 if not key:return None
 key=str(key).replace('/','a').replace('_','a')
 if not re.fullmatch(r'[A-Za-z0-9]{1,128}',key):return None
 title=row.get('title') or row.get('programmeTitle') or row.get('filmTitle') or row.get('specialTitle')
 if not isinstance(title,str) or not title.strip():return None
 tier=row.get('tier');premium=row.get('isPaid') or (isinstance(tier,str) and tier!='FREE') or (isinstance(tier,list) and 'FREE' not in tier)
 if premium:return None
 slug=row.get('titleSlug') or re.sub(r'[^a-z0-9]+','-',title.lower()).strip('-')
 if not re.fullmatch(r'[A-Za-z0-9-]+',slug):return None
 genres=row.get('genres') or row.get('genre') or []
 genres=[g.get('name','') if isinstance(g,dict) else str(g) for g in genres]
 latest=row.get('latestAvailableEpisode') or {}
 return {'key':key,'title':title.strip(),'description':row.get('longDescription') or row.get('descriptionEpg') or row.get('description') or row.get('synopsis') or '',
  'artwork':image(row.get('image') or row.get('imageTemplate') or row.get('imageUrl') or row.get('imageHref') or latest.get('imageHref')),
  'production_id':row.get('productionId'),'genre':' · '.join(genres),'film':is_film(row),'page':'https://www.itv.com/watch/'+slug+'/'+key}

def search(query):
 data=get('https://textsearch.prd.oasvc.itv.com/search',broadcaster='itv',featureSet='hls,fairplay,hd',onlyFree='true',platform='dotcom',query=query).json()
 return [s for r in data.get('results',[]) if (s:=show(r.get('data') or {}))]

def highlights():
 pages=['/watch','/watch/categories/comedy','/watch/categories/drama-soaps','/watch/categories/factual','/watch/categories/films']
 def fetch(path):
  try:
   data=props(get('https://www.itv.com'+path).text);rows=[]
   def walk(value):
    if isinstance(value,dict):
     s=show(value)
     if s:rows.append(s)
     for key,v in value.items():
      if key not in ('config','navAdServerParams'):walk(v)
    elif isinstance(value,list):
     for v in value:walk(v)
   walk(data);return rows
  except Exception:return []
 with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:rows=[s for batch in pool.map(fetch,pages) for s in batch]
 if not rows:
  # Public search remains available if the website's HTML endpoint times out.
  # Seed a small transparent starter set, not a claim of a full ITV index.
  def query(term):
   try:return search(term)
   except requests.RequestException:return []
  with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:rows=[s for batch in pool.map(query,['The Chase','The 1% Club','Vera','Unforgotten','The Assembly','The Jonathan Ross Show']) for s in batch]
 return list({s['key']:s for s in rows}.values())

def is_film(row):
 if row.get('contentType')=='film':return True
 genres=row.get('genres') or row.get('genre') or []
 if isinstance(genres,str):genres=[genres]
 return any(str(g.get('id') or g.get('name') or '').casefold() in ('film','films') if isinstance(g,dict) else str(g).casefold() in ('film','films') for g in genres)

def duration(value):
 if isinstance(value,(int,float)):return float(value)
 text=str(value or '').strip()
 m=re.fullmatch(r'PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?',text,re.I)
 if m:return sum(int(v or 0)*unit for v,unit in zip(m.groups(),[3600,60,1]))
 parts=re.findall(r'(\d+)\s*(hours?|hrs?|h|minutes?|mins?|m|seconds?|secs?|s)\b',text,re.I)
 return sum(int(number)*(3600 if unit.lower().startswith('h') else 60 if unit.lower().startswith('m') else 1) for number,unit in parts)

def details(summary):
 url=summary['page'];p=urlparse(url)
 if p.scheme!='https' or p.hostname!='www.itv.com' or not re.fullmatch(r'/watch/[a-zA-Z0-9-]+/[A-Za-z0-9]+',p.path):raise ValueError('Invalid ITV programme')
 try:data=props(get(url).text)
 except (requests.RequestException,ValueError,KeyError):return latest_details(summary)
 film=summary['film'] or is_film(data.get('programme') or {})
 episodes=[]
 groups=data.get('seriesList') or ([{'titles':[data['episode']],'seriesLabel':'Episodes'}] if isinstance(data.get('episode'),dict) else [])
 for group in groups:
  for ep in group.get('titles',[]):
   film=film or is_film(ep)
   endpoint=ep.get('playlistUrl');ident=ep.get('productionId') or ep.get('episodeId')
   tier=ep.get('tier') or []
   if not ident or not playlist(endpoint) or ep.get('premium') or (tier and 'FREE' not in tier):continue
   now=time.time()
   def stamp(v):
    try:return datetime.datetime.fromisoformat(v.replace('Z','+00:00')).timestamp()
    except (ValueError,AttributeError):return None
   start,end=stamp(ep.get('availabilityFrom')),stamp(ep.get('availabilityUntil'))
   if (start and start>now) or (end and end<=now):continue
   season=ep.get('series') or ep.get('seriesNumber') or re.sub(r'^(?:Series|Season)\s+','',group.get('seriesLabel') or 'Episodes',flags=re.I)
   episodes.append({'id':'itv_'+str(ident),'provider_id':'itv','provider_episode_id':str(ident),'kind':'native','playlist_url':endpoint,'title':ep.get('episodeTitle') or 'Episode','season':season,'episode_number':ep.get('episode') or 0,'description':ep.get('longDescription') or ep.get('description') or '', 'thumbnail':image(ep.get('image') or ep.get('imageUrl')) or summary['artwork'],'duration_seconds':duration(ep.get('duration')),'live':False,'premium':False})
 return {'id':'itv_'+summary['key'],'title':summary['title'],'provider':'ITVX','provider_id':'itv','description':summary['description'],'genre':summary['genre'],'media_type':'movie' if film else 'tv','artwork':summary['artwork'],'hero':summary['artwork'],'episodes':list({e['id']:e for e in episodes}.values())}

def live():
 rows=[]
 for channel in get('https://nownext.oasvc.itv.com/channels').json().get('channels',[]):
  key=str(channel.get('id','')).lower();endpoint=channel.get('streamUrl') or channel.get('playlistUrl')
  if key not in ('itv','itv2','itv3','itv4','itvbe') or not playlist(endpoint,True):continue
  guide={};logo=image((channel.get('images') or {}).get('logo'))
  for name,slot in (channel.get('slots') or {}).items():
   if name not in ('now','next'):continue
   try:start=datetime.datetime.fromisoformat(slot['start'].replace('Z','+00:00')).timestamp();end=datetime.datetime.fromisoformat(slot['end'].replace('Z','+00:00')).timestamp()
   except (ValueError,KeyError):continue
   art=image(slot.get('image'))
   if not art and re.fullmatch(r'[A-Za-z0-9]{5,24}',str(slot.get('brandId',''))):art='https://ovp.itv.com/images/programme/'+slot['brandId']+'/itv_hub/04_DesktopCTV_RailTileLandscape/16x9?distributionPartner=itv_hub&treatment=title&w=960&h=540&q=80&fallback=standard'
   guide[name]={'title':slot.get('displayTitle') or slot.get('brandTitle') or slot.get('title'),'subtitle':slot.get('shortSynopsis') or slot.get('detailedDisplayTitle') or '', 'start':start,'end':end,'time':datetime.datetime.fromtimestamp(start,ZoneInfo('Europe/London')).strftime('%H:%M'),'image':art}
  rows.append({'id':'itv_live_'+key,'title':channel['name'],'provider':'ITVX','provider_id':'itv','live_channel':key,'artwork':logo,'hero':logo,'_guide':guide,'_channel_logo':logo,'episodes':[{'id':'itv_live_'+key,'title':channel['name'],'provider_id':'itv','provider_episode_id':key,'kind':'native','playlist_url':endpoint,'live':True}]})
 return rows


def latest_details(summary):
 # Search publishes the actual latest production ID. Retain a useful exact
 # episode when ITV's HTML programme page is unavailable, without claiming a
 # complete archive or inventing episode numbering.
 production=summary.get('production_id') or ''
 if not re.fullmatch(r'[0-9]+/[0-9]+/[0-9]+#[0-9]+',production):raise ValueError('ITV episode details temporarily unavailable')
 path=production.replace('/','_').replace('#','.')
 episode={'id':'itv_'+path,'provider_id':'itv','provider_episode_id':production,'kind':'native','playlist_url':'https://magni.itv.com/playlist/itvonline/ITV/'+path,'title':'Latest available episode','season':'Latest episode','episode_number':0,'description':summary['description'],'thumbnail':summary['artwork'],'duration_seconds':0,'live':False,'premium':False}
 return {'id':'itv_'+summary['key'],'title':summary['title'],'provider':'ITVX','provider_id':'itv','description':summary['description'],'genre':summary['genre'],'media_type':'movie' if summary['film'] else 'tv','artwork':summary['artwork'],'hero':summary['artwork'],'episodes':[episode]}
