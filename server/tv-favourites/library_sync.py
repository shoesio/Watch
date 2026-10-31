"""Read-only provider account catalogue sync. No watchlist or history writes."""
import concurrent.futures,html,json,logging,os,re,time,fcntl,tempfile
from pathlib import Path
from urllib.parse import urlsplit
import requests
from provider_playback import ProviderResolver
from film_catalogue import film_selections, bbc_films
from five_provider import catalogue as five_catalogue

class LibrarySync:
 def __init__(self,root,catalogue):self.root=Path(root);self.path=Path(catalogue);self.resolver=ProviderResolver(root);self.status={};self.previous=json.loads(self.path.read_text())
 def session(self):
  s=requests.Session();s.headers['User-Agent']='Mozilla/5.0';return s
 def get(self,s,url,**kw):
  r=s.get(url,timeout=25,**kw);r.raise_for_status();return r
 def pic(self,x,size='1280x720'):
  if isinstance(x,str):return html.unescape(x).replace('{recipe}',size).replace('{&resize}','&resize=1280px:*')
  if isinstance(x,dict):
   for k in ('promotional_with_logo','promotional','standard','href','src','image','thirdlight_hero_url','thirdlight_image','url'):
    if x.get(k):return self.pic(x[k],size)
  return ''
 def bbc_episode_pic(self,images,size='960x540'):
  # Episode cards need the programme still, not the shared promotional key art.
  if isinstance(images,dict):images=images.get('standard') or images
  return self.pic(images,size)
 def atomic(self,path,data):
  fd,name=tempfile.mkstemp(prefix='.library-',dir=path.parent)
  try:
   with os.fdopen(fd,'w') as output:json.dump(data,output,ensure_ascii=False,indent=2)
   os.replace(name,path)
  finally:Path(name).unlink(missing_ok=True)
 def bbc_session(self):
  s=self.session();p=self.root/'bbc-cookies-private.json'
  if p.exists():
   for c in json.loads(p.read_text()):s.cookies.set(c['name'],c['value'],domain=c['domain'],path='/')
  r=self.get(s,'https://session.bbc.co.uk/session',params={'ptrt':'https://www.bbc.co.uk/iplayer/watchlist'})
  if 'account.bbc.com' in r.url:
   import streamlink
   from bbc_auth import adapt
   sl=streamlink.Streamlink();_,cls,u=sl.resolve_url('https://www.bbc.co.uk/iplayer/live/bbcone');opts=json.loads((self.root/'streamlink-options.json').read_text())['bbciplayer'];adapt(cls(sl,u,options=opts)).login(u)
   s.cookies.update(sl.http.cookies);self.get(s,'https://session.bbc.co.uk/session',params={'ptrt':'https://www.bbc.co.uk/iplayer/watchlist'})
  self.atomic(p,[{'name':c.name,'value':c.value,'domain':c.domain} for c in s.cookies]);return s
 def bbc(self):
  s=self.bbc_session();selected={}
  for mode in ('watchlist','continue-watching'):
   text=self.get(s,'https://www.bbc.co.uk/iplayer/'+mode).text;m=re.search(r'window\.__IPLAYER_REDUX_STATE__\s*=\s*(.*?);?\s*</script>',text,re.S)
   if not m:raise ValueError('BBC list response changed')
   data=json.loads(m[1].strip().rstrip(';'))
   for item in data.get('items',{}).get('elements',[]):
    p=item.get('programme',{});id=p.get('id')
    if not id:continue
    selected.setdefault(id,{'id':id,'favourite':False,'recent':False})
    if mode=='watchlist':selected[id].update(favourite=True,summary=p)
    else:selected[id].update(recent=True,resume=item)
  shows=[]
  for id,info in selected.items():
   try:
    episodes=[];programme={};page=1
    while page<=30:
     d=self.get(s,'https://ibl.api.bbc.co.uk/ibl/v1/programmes/'+id+'/episodes',params={'per_page':200,'page':page}).json()['programme_episodes'];programme=d.get('programme',programme);elements=d.get('elements',[])
     if not elements:break
     episodes.extend(elements)
     if page*int(d.get('per_page',200))>=int(d.get('count',len(episodes))):break
     page+=1
    if not episodes:continue
    summary=info.get('summary',{});first=episodes[0];title=programme.get('title') or summary.get('title') or first['title'];pid='bbc_'+id
    show={'id':pid,'title':title,'provider':'BBC iPlayer','provider_id':'bbc','favourite':info['favourite'],'recent':info['recent'],'description':(summary.get('synopses') or first.get('synopses',{})).get('programme_small') or (summary.get('synopses') or first.get('synopses',{})).get('small',''),'artwork':self.pic(summary.get('images') or programme.get('images') or first.get('images')),'hero':self.pic(first.get('images')),'genre':first.get('labels',{}).get('category',''),'episodes':[]}
    resume=info.get('resume',{});rid=resume.get('episode',{}).get('id');progress=resume.get('progress',0);remaining=resume.get('remaining',0)
    for ep in episodes:
     if ep.get('status') not in (None,'available'):continue
     sub=ep.get('subtitle') or ep.get('editorial_title') or 'Episode';season=re.search(r'(?:Series|Season)\s+(\d+)',sub,re.I);season=int(season[1]) if season else sub.split(':')[0] if ':' in sub else 'Episodes';num=re.search(r'(?:Episode\s+|:\s*)(\d+)',sub)
     version=next((v for v in ep.get('versions',[]) if v.get('kind') in ('editorial','original')),next(iter(ep.get('versions',[])),{}));duration=version.get('duration',{});secs=duration.get('value') or duration.get('seconds') or 0
     entry={'id':pid+'_'+ep['id'],'title':sub,'season':season,'episode_number':int(num[1]) if num else ep.get('parent_position',0),'broadcast_at':ep.get('release_date_time',''),'description':ep.get('synopses',{}).get('medium') or ep.get('synopses',{}).get('small',''),'thumbnail':self.bbc_episode_pic(ep.get('images')),'duration_label':duration.get('text',''),'duration_seconds':secs,'kind':'plugin','url':'https://www.bbc.co.uk/iplayer/episode/'+ep['id'],'quality':'720p50,720p_hls,540p,396p','delivery':'relay','preserve_timestamps':True,'live':False}
     if ep['id']==rid:entry.update(resume_seconds=progress,progress=round(100*progress/(progress+remaining)) if progress+remaining else 0,recent=True);show['resume_episode']=entry['id']
     show['episodes'].append(entry)
    if show['episodes']:shows.append(show)
   except Exception:self.status.setdefault('bbc_partial',0);self.status['bbc_partial']+=1
  s.close();return shows
 def c4(self):
  s=self.session();h={'Authorization':'Bearer '+self.resolver.channel4_token()};params={'client':'amazonfire-dash'};data=self.get(s,'https://api.channel4.com/online/v1/views/my4.json',params=params,headers=h).json();selected={}
  for typ in ('MYLIST','CONTINUE_WATCHING','HISTORY'):
   for g in data.get('sliceGroups',[]):
    for sl in g.get('slices',[]):
     if sl.get('type')!=typ:continue
     for item in sl.get('sliceItems',[]):
      b=item.get('brand',{});slug=b.get('websafeTitle')
      if not slug:continue
      v=selected.setdefault(slug,{'favourite':False,'recent':False,'summary':b})
      if typ=='MYLIST':v['favourite']=True
      else:v['recent']=True
      if typ=='CONTINUE_WATCHING' and not v.get('resume'):v['resume']=item.get('episode',{})
  for slug in getattr(self, 'films', {}).get('channel4', []):
   selected.setdefault(slug, {'favourite':False,'recent':False,'summary':{},'film':True})
  shows=[]
  for slug,info in selected.items():
   try:
    b=self.get(s,'https://api.channel4.com/online/v1/views/content-hubs/'+slug+'.json',params={**params,'include':'extended-restart'},headers=h).json()['brand'];pid='c4_'+slug;show={'id':pid,'title':b['title'],'provider':'Channel 4','provider_id':'channel4','favourite':info['favourite'],'recent':info['recent'],'description':b.get('summary',''),'artwork':self.pic(b.get('image') or info['summary'].get('image')),'hero':self.pic(b.get('image') or info['summary'].get('image')),'genre':' · '.join(b.get('categories',[])[:2]),'episodes':[]}
    resume=info.get('resume',{});rid=resume.get('programmeId','').replace('/','-')
    for ep in b.get('episodes',[]):
     a=ep.get('assetInfo',{}).get('streaming');eid=ep.get('programmeId','').replace('/','-')
     if not a or not eid or a.get('startDate','')>time.strftime('%Y-%m-%dT%H:%M:%S') or (a.get('endDate') and a['endDate']<time.strftime('%Y-%m-%dT%H:%M:%S')):continue
     entry={'id':pid+'_'+eid,'provider_id':'channel4','provider_episode_id':eid,'asset_id':str(a['assetId']),'broadcast_at':ep.get('firstTXDate',''),'available_at':a.get('startDate',''),'title':ep.get('secondaryTitle') or ep.get('originalTitle') or ep.get('title') or 'Episode','subtitle':ep.get('title',''),'description':ep.get('summary',''),'season':ep.get('seriesNumber') or 'Episodes','episode_number':ep.get('episodeNumber',0),'thumbnail':self.pic(ep.get('image')),'duration_seconds':a.get('duration',0),'duration_label':a.get('durationLabel',''),'kind':'provider','live':False}
     visible=ep.get('secondaryTitle') or ep.get('title','');order=re.search(r'(?:Series|Season)\s+(\d+)\s*[:·-]?\s*Episode\s+(\d+)',visible,re.I)
     if order:entry.update(season=int(order[1]),episode_number=int(order[2]))
     if rid==eid:
      rs=resume.get('resume') or ep.get('resume') or {};secs=rs.get('seconds',0);entry.update(resume_seconds=secs,progress=round(100*secs/max(1,a.get('duration',1))),recent=True);show['resume_episode']=entry['id']
     show['episodes'].append(entry)
    if info.get('film') or 'film' in show.get('genre','').casefold():show['media_type']='movie'
    if show['episodes']:shows.append(show)
   except Exception:self.status.setdefault('channel4_partial',0);self.status['channel4_partial']+=1
  s.close();return shows
 def u(self):
  s=self.session();a=json.loads((self.root/'u-session.json').read_text());s.cookies.update(a['cookies']);selected={}
  for path in ('my-list','watching'):
   t=self.get(s,'https://u.co.uk/'+path).text
   if '\\"isLoggedIn\\":true' not in t and '"isLoggedIn":true' not in t:raise ValueError('U session needs reconnecting')
   for slug in dict.fromkeys(re.findall(r'/shows/([a-z0-9-]+)',t)):
    v=selected.setdefault(slug,{'favourite':False,'recent':False});v['favourite' if path=='my-list' else 'recent']=True
    if path=='watching':
     match=re.search(r'/shows/'+re.escape(slug)+r'/series-\d+/episode-\d+/(\d+)',t)
     if match:v['resume_id']=match[1]
  shows=[]
  for slug,info in selected.items():
   try:
    b=self.get(s,'https://vschedules.uktv.co.uk/vod/brand/',params={'slug':slug}).json();pid='u_'+slug;show={'id':pid,'title':b.get('name') or b.get('brand_name') or slug.replace('-',' ').title(),'provider':'U','provider_id':'u','favourite':info['favourite'],'recent':info['recent'],'description':b.get('description') or b.get('synopsis',''),'artwork':self.pic(b.get('image') or b.get('images') or b),'hero':self.pic(b.get('hero_image_4k') or b.get('image')),'episodes':[]}
    for series in b.get('series',[]):
     data=self.get(s,'https://vschedules.uktv.co.uk/vod/series/',params={'id':series['id']}).json()
     for ep in data.get('episodes',[]):
      vid=str(ep.get('video_id',''))
      if not vid or vid=='None':continue
      entry={'id':pid+'_'+vid,'provider_id':'u','provider_episode_id':vid,'available_at':ep.get('available_start') or ep.get('available_start_unix') or '','title':ep.get('episode_name') or ep.get('name') or 'Episode '+str(ep.get('episode_number','')),'season':ep.get('series_number') or series.get('series_number') or 'Episodes','episode_number':ep.get('episode_number',0),'description':ep.get('synopsis') or ep.get('description',''),'thumbnail':self.pic(ep.get('image') or ep),'duration_label':str(ep.get('duration','')),'kind':'provider','live':False}
      if entry['title'].casefold()==show['title'].casefold():entry['title']='Episode '+str(entry['episode_number'])
      entry['subtitle']='Series '+str(entry['season'])+' · Episode '+str(entry['episode_number'])
      if entry['duration_label']:entry['duration_label']+=' min'
      if vid==info.get('resume_id'):entry['recent']=True;show['resume_episode']=entry['id']
      show['episodes'].append(entry)
    if show['episodes']:
     if not show['artwork']:show['artwork']=show['episodes'][0].get('thumbnail','')
     show['hero']=show.get('hero') or show['artwork'];shows.append(show)
   except Exception:self.status.setdefault('u_partial',0);self.status['u_partial']+=1
  s.close();return shows
 def run(self):
  with (self.root/'library-sync.lock').open('a') as lock:
   fcntl.flock(lock,fcntl.LOCK_EX)
   return self.run_locked()
 def run_locked(self):
  logging.getLogger('streamlink').setLevel(logging.CRITICAL);old=json.loads(self.path.read_text());programmes=[];self.status={}
  try:self.films=film_selections(self.root)
  except Exception:self.films={};self.status['films']='refresh_deferred'
  jobs={'bbc':self.bbc,'channel4':self.c4,'u':self.u}
  if (self.root/'channel5-session.json').exists():jobs['channel5']=lambda:five_catalogue(self.root)
  else:self.status['channel5']={'status':'awaiting_login','shows':0}
  with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
   futures={pool.submit(fn):provider for provider,fn in jobs.items()}
   for f in concurrent.futures.as_completed(futures):
    provider=futures[f]
    try:
     shows=f.result();programmes.extend(shows);self.status[provider]={'status':'connected','shows':len(shows)}
    except Exception as exc:
     retained=[p for p in old['programmes'] if p.get('provider_id')==provider and not p.get('live_channel')];programmes.extend(retained);self.status[provider]={'status':'refresh_failed','error_type':type(exc).__name__,'retained_shows':len(retained)}
  discovered=bbc_films(self,self.films.get('bbc',[]))
  known={p['id'] for p in programmes}
  programmes.extend(p for p in discovered if p['id'] not in known)
  # Only previously verified live sources are carried forward. YouTube/reference material is removed.
  for p in old['programmes']:
   if p.get('live_channel') or p['id']=='bbc_live':
    if p.get('provider_id') not in (None,'bbc'):
     programmes.append(p);continue
    name=p.get('title','BBC One');slug=p.get('live_channel','bbcone');p.update(provider='BBC iPlayer',provider_id='bbc',live_channel=slug,description='Watch '+name+' live.',artwork='/local/tv-favourites/artwork/'+slug+'.svg')
    for e in p['episodes']:e.update(thumbnail=p['artwork'],title=name,description='Live television from '+name+'.')
    programmes.append(p)
  programmes.sort(key=lambda p:(not p.get('favourite'),not p.get('recent'),p.get('provider',''),p['title']))
  data={**old,'programmes':programmes,'library_updated_at':time.time(),'provider_status':self.status}
  # Save an atomic, complete catalogue only. Source URLs/tokens from stream resolution never enter it.
  if not any(p.get('favourite') or p.get('recent') for p in programmes):raise ValueError('No account lists could be read; preserving the previous catalogue.')
  self.atomic(self.path,data);self.atomic(self.root/'library-sync-result.json',{'updated_at':time.time(),'providers':self.status,'shows':len(programmes),'episodes':sum(len(p['episodes']) for p in programmes)})
  return data

if __name__=='__main__':
 import argparse
 p=argparse.ArgumentParser();p.add_argument('--root',default='/home/jhewes/tv-favourites-private');p.add_argument('--catalogue',default='/home/jhewes/tv-favourites/catalogue.json');a=p.parse_args()
 result=LibrarySync(a.root,a.catalogue).run();print(json.dumps({'shows':len(result['programmes']),'episodes':sum(len(p['episodes']) for p in result['programmes']),'providers':result['provider_status']}))
