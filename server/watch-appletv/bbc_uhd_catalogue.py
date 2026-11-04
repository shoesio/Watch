"""BBC catalogue UHD flags, independent of playback and account sessions."""
import concurrent.futures,datetime,json,re,time
from pathlib import Path
import requests

def uhd_available(episode,now=None):
 now=time.time() if now is None else now
 for version in episode.get('versions',[]):
  kind=str(version.get('kind','')).lower()
  if version.get('uhd') is not True or 'signed' in kind or 'describ' in kind:continue
  valid=True
  for key in ('start','end'):
   raw=version.get('availability',{}).get(key)
   if not raw:continue
   try:stamp=datetime.datetime.fromisoformat(raw.replace('Z','+00:00')).timestamp()
   except (ValueError,TypeError):valid=False;break
   if (key=='start' and stamp>now) or (key=='end' and stamp<=now):valid=False
  if valid:return True
 return False

def enrich(programmes,records,index=None):
 index=index or {}
 for programme in programmes:
  for episode in programme.get('episodes',[]):
   sources=[episode['id']]+[source['id'] for source,_ in index.get(episode['id'],{}).get('sources',[])]
   known=[records[ident] for ident in sources if ident in records]
   if known:episode['uhd_available']=any(record.get('available') is True for record in known)
   elif any(source.get('uhd_available') is True for source,_ in index.get(episode['id'],{}).get('sources',[])):episode['uhd_available']=True
  programme['uhd_available']=any(e.get('uhd_available') is True for e in programme.get('episodes',[]))
 return programmes

def refresh(catalogue,path):
 path=Path(path)
 try:records=json.loads(path.read_text())
 except (OSError,ValueError):records={}
 targets={}
 for programme in catalogue.get('programmes',[]):
  for episode in programme.get('episodes',[]):
   match=re.fullmatch(r'bbc_([a-z0-9]{8})_([a-z0-9]{8})',episode.get('id',''))
   if match and not episode.get('live'):targets.setdefault(match[1],{})[match[2]]=episode['id']
 now=time.time()
 def fetch(item):
  pid,known=item
  if all(now-records.get(ident,{}).get('checked_at',0)<21600 for ident in known.values()):return {}
  updates={}
  try:
   with requests.Session() as session:
    for page in range(1,31):
     r=session.get('https://ibl.api.bbc.co.uk/ibl/v1/programmes/'+pid+'/episodes',params={'per_page':200,'page':page},timeout=(5,15));r.raise_for_status();data=r.json()['programme_episodes']
     rows=data.get('elements',[])
     for episode in rows:
      if episode.get('id') in known:updates[known[episode['id']]]={'available':uhd_available(episode,now),'checked_at':now}
     if not rows or page*int(data.get('per_page',200))>=int(data.get('count',len(rows))) or len(updates)==len(known):break
  except (requests.RequestException,ValueError,KeyError,TypeError):pass
  return updates
 with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
  for updates in pool.map(fetch,targets.items()):records.update(updates)
 path.parent.mkdir(parents=True,exist_ok=True)
 temporary=path.with_suffix('.tmp');temporary.write_text(json.dumps(records));temporary.chmod(0o600);temporary.replace(path)
 return records

def listed_entries(text):
 """Only programme links inside BBC's UHD article, never surrounding navigation."""
 import html
 from urllib.parse import urljoin,urlsplit
 article=re.search(r'<article\b.*?</article>',text,re.S|re.I)
 if not article:raise ValueError('BBC UHD article unavailable')
 found={}
 for href,label in re.findall(r'<a\b[^>]*href=[\"\x27]([^\"\x27]+)[\"\x27][^>]*>(.*?)</a>',article[0],re.S|re.I):
  url=urlsplit(urljoin('https://www.bbc.co.uk/',html.unescape(href)))
  match=re.match(r'^/iplayer/(episodes?)/([a-z0-9]{8})(?:/|$)',url.path)
  if url.scheme not in ('http','https') or url.hostname not in ('www.bbc.co.uk','bbc.co.uk','www.bbc.com','bbc.com') or not match:continue
  found.setdefault(match[2],{'id':match[2],'single':match[1]=='episode','title':html.unescape(re.sub('<[^>]+>',' ',label)).strip()})
 if not found:raise ValueError('BBC UHD list is empty')
 return list(found.values())

def refresh_discovery(root):
 """Discover outside the saved library; no account or media preparation calls."""
 root=Path(root);stamp=root/'bbc-uhd-discovery-status.json';output=root/'bbc-uhd-programmes.json'
 try:
  if output.exists() and time.time()-json.loads(stamp.read_text()).get('checked_at',0)<21600:return json.loads(output.read_text())
 except (OSError,ValueError):pass
 response=requests.get('https://www.bbc.co.uk/iplayer/help/questions/programme-availability/uhd-content',timeout=(5,20));response.raise_for_status();entries=listed_entries(response.text)
 now=time.time()
 def load(entry):
  try:
   with requests.Session() as session:
    pid=entry['id'];seed=None
    if entry['single']:
     r=session.get('https://ibl.api.bbc.co.uk/ibl/v1/episodes/'+pid,timeout=(5,15));r.raise_for_status();seed=next((e for e in r.json().get('episodes',[]) if e.get('id')==pid),None)
     if not seed:return None
     pid=seed.get('tleo_id') or pid
     if not re.fullmatch('[a-z0-9]{8}',pid):return None
    episodes=[];programme={}
    for page in range(1,31):
     r=session.get('https://ibl.api.bbc.co.uk/ibl/v1/programmes/'+pid+'/episodes',params={'per_page':200,'page':page},timeout=(5,15))
     if r.status_code==404 and seed:episodes=[seed];break
     r.raise_for_status();data=r.json()['programme_episodes'];programme=data.get('programme',programme);rows=data.get('elements',[]);episodes.extend(rows)
     if not rows or page*int(data.get('per_page',200))>=int(data.get('count',len(rows))):break
    episodes=[e for e in episodes if e.get('status') in (None,'available') and uhd_available(e,now)]
    if not episodes:return None
    first=episodes[0];genre=first.get('labels',{}).get('category','');film=genre.lower().startswith('film')
    def picture(images,recipe):return (images or {}).get('standard','').replace('{recipe}',recipe)
    title=programme.get('title') or first.get('title') or entry['title'];ident='bbc_'+pid
    result={'id':ident,'title':title,'provider':'BBC iPlayer','provider_id':'bbc','media_type':'movie' if film else 'tv','favourite':False,'recent':False,'genre':genre,'description':(programme.get('synopses') or first.get('synopses',{})).get('medium') or first.get('synopses',{}).get('small',''),'artwork':picture(programme.get('images') or first.get('images'),'1280x720'),'hero':picture(first.get('images'),'1920x1080'),'episodes':[]}
    for ep in episodes:
     version=next((v for v in ep.get('versions',[]) if uhd_available({'versions':[v]},now)),{})
     duration=version.get('duration',{});subtitle=ep.get('subtitle') or ep.get('title',title);season=re.search(r'(?:Series|Season)\s+(\d+)',subtitle,re.I);number=re.search(r'(?:Episode\s+|:\s*)(\d+)',subtitle)
     result['episodes'].append({'id':ident+'_'+ep['id'],'title':subtitle,'season':'Film' if film else int(season[1]) if season else 'Episodes','episode_number':int(number[1]) if number else ep.get('parent_position',0),'broadcast_at':ep.get('release_date_time',''),'description':ep.get('synopses',{}).get('medium') or ep.get('synopses',{}).get('small',''),'thumbnail':picture(ep.get('images'),'640x360'),'duration_seconds':duration.get('value') or duration.get('seconds') or 0,'kind':'plugin','url':'https://www.bbc.co.uk/iplayer/episode/'+ep['id'],'quality':'best','delivery':'relay','preserve_timestamps':True,'live':False,'uhd_available':True})
    return result
  except (requests.RequestException,ValueError,KeyError,TypeError):return None
 with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:programmes=[p for p in pool.map(load,entries) if p]
 unique={}
 for p in programmes:
  if p['id'] not in unique:unique[p['id']]=p
  else:unique[p['id']]['episodes']=list({e['id']:e for e in unique[p['id']]['episodes']+p['episodes']}.values())
 programmes=list(unique.values())
 if not programmes:raise ValueError('No available BBC UHD programmes returned; preserving previous index')
 def write(path,data):
  temp=path.with_suffix('.tmp');temp.write_text(json.dumps(data));temp.chmod(0o600);temp.replace(path)
 write(output,programmes)
 write(stamp,{'checked_at':now,'listed_titles':len(entries),'available_titles':len(programmes)})
 return programmes
