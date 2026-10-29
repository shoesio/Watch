"""Shared Watch catalogue projection, artwork, source choice and progress for HA."""
import hashlib,json,re,time
from pathlib import Path
from episode_versions import versions,QualityStore,seconds
from library_browse import genres,episode_order
from tmdb_logos import is_film,atomic
from progress_store import ProgressStore

BRANDS={'BBC iPlayer':'bbc','Channel 4':'channel4','U':'u','Channel 5':'channel5'}
ORDER={'bbcone':1,'bbctwo':2,'C4':3,'bbcfour':4,'E4':5,'M4':6,'F4':7,'4S':8,'bbcnews':9}
CHANNELS={'C4':'channel4','E4':'e4','M4':'more4','F4':'film4','4S':'4seven'}

class DashboardLibrary:
 def __init__(self,private,base):
  self.private=Path(private);self.base=base.rstrip('/')
  self.quality=QualityStore(self.private/'ha-episode-quality.json')
  self.progress=ProgressStore(self.private/'home-assistant-watch-progress.json')
  self.index={};self.groups=[]
 def brands(self,names):return [{'id':BRANDS[n],'name':n,'image':self.base+'/static/artwork/brands/'+BRANDS[n]+'.png'} for n in dict.fromkeys(names) if n in BRANDS]
 def progress_for(self,version):
  record=self.progress.get(version['id'])
  if not record:record=max((self.progress.get(e['id']) for e,_ in version['sources']),key=lambda r:r.get('updated_at',0),default={})
  position=record.get('position',0)
  return {'resume_seconds':max(0,position-5) if position>=10 and not record.get('completed') else 0,'updated_at':record.get('updated_at',0)}
 def project(self,catalogue,guide):
  try:metadata=json.loads((self.private/'tmdb-logo-manifest.json').read_text())
  except (OSError,ValueError):metadata={}
  try:native=json.loads((self.private/'episode-quality.json').read_text())
  except (OSError,ValueError):native={}
  try:own=json.loads(self.quality.path.read_text())
  except (OSError,ValueError):own=self.quality.records
  self.quality.records={**native,**own}
  groups={};self.index={}
  for programme in catalogue['programmes']:
   available=[e for e in programme.get('episodes',[]) if not e.get('blocked')]
   if programme.get('blocked') or not available:continue
   live=bool(programme.get('live_channel') or all(e.get('live') for e in available))
   normal=re.sub(r'[^\w]+',' ',programme['title'].casefold().replace('’',"'")).strip()
   key='live:'+programme['id'] if live else normal
   ident=hashlib.sha256(key.encode()).hexdigest()[:20]
   if key not in groups:groups[key]={'id':ident,'title':programme['title'],'description':programme.get('description',''),'artwork':programme.get('artwork',''),'hero':programme.get('hero') or programme.get('artwork',''),'live':live,'live_channel':programme.get('live_channel'),'favourite':False,'recent':False,'film':False,'genres':[],'_sources':[],'_providers':[]}
   p=groups[key];p['favourite']|=bool(programme.get('favourite'));p['recent']|=bool(programme.get('recent'))
   p['film']|=is_film(programme) or metadata.get(ident,{}).get('media_type')=='movie'
   p['genres']=sorted(set(p['genres']+genres([programme.get('genre','')]+metadata.get(ident,{}).get('genres',[]))))
   p['_sources'].extend((e,programme.get('provider','')) for e in available)
   p['_providers'].append(programme.get('provider',''))
  result=[]
  for p in groups.values():
   p['brands']=self.brands(p.pop('_providers'));p['provider']=' · '.join(b['name'] for b in p['brands'])
   ident=p['id'];logo=self.private/'show-logos'/(ident+'.png')
   if logo.is_file():p['show_logo']=self.base+'/static/show-logos/'+ident+'.png'
   if p['live']:
    channel=p['live_channel'];p['guide']=guide.get(channel) or {}
    p['channel_logo']=self.base+'/static/artwork/channels/'+CHANNELS.get(channel,channel or '')+'.png'
    if p['guide'].get('now',{}):p['artwork']=p['guide']['now'].get('image') or p['artwork']
   eps=[]
   for version in versions(ident,p.pop('_sources')):
    self.index[version['id']]=version
    for source,_ in version['sources']:self.index[source['id']]=version
    source,provider=self.quality.preferred(version)
    fields=('title','subtitle','description','thumbnail','season','episode_number','duration_label','recent','live')
    e={k:source[k] for k in fields if k in source};e.update(id=version['id'],duration_seconds=seconds(source.get('duration_seconds')),brands=self.brands([provider]),**self.progress_for(version))
    quality=self.quality.records.get(source['id'],{})
    if quality.get('height'):e['quality']='HD' if quality['height']>=720 else 'SD'
    if e['duration_seconds']:e['progress']=min(100,100*e['resume_seconds']/e['duration_seconds'])
    eps.append(e)
   p['episodes']=sorted(eps,key=episode_order,reverse=True)
   resumes=[e for e in eps if e['resume_seconds']]
   if resumes:p['resume_episode']=max(resumes,key=lambda e:e['updated_at'])['id'];p['recent']=True
   p['genre']=' · '.join(p['genres']);result.append(p)
  self.groups=result
  return sorted(result,key=lambda p:(p['live'],ORDER.get(p['live_channel'],100) if p['live'] else 0,p['title'].casefold()))
 def choose(self,bridge,ident,position,profile=None):
  version=self.index.get(ident)
  if not version:
   source=bridge.episodes.get(ident)
   if not source or source.get('blocked'):raise ValueError('Choose an available episode.')
   version={'id':ident,'sources':[(source,'')]}
  candidates=sorted(version['sources'],key=self.quality.rank,reverse=True)
  compare=len(candidates)>1 and not all(self.quality.fresh(e['id']) for e,_ in candidates)
  chosen=[]
  from bridge import compatible
  for candidate,provider in candidates:
   episode=dict(candidate)
   if position and not episode.get('live'):episode['_start_offset']=position
   try:
    prepared=bridge.prepare(episode);compatible(prepared['info'],profile)
    self.quality.record(episode['id'],prepared['info']);chosen.append((self.quality.rank((episode,provider)),episode,prepared))
    if not compare:break
   except Exception:self.quality.invalidate(episode['id'])
  if not chosen:raise ValueError('No compatible source could be prepared. Check availability or provider sign-in.')
  _,episode,prepared=max(chosen,key=lambda row:row[0]);group=next((p for p in self.groups if any(e['id']==version['id'] for e in p['episodes'])),{})
  public=next((e for e in group.get('episodes',[]) if e['id']==version['id']),{})
  programme=next((p for p in bridge.catalogue['programmes'] if any(e['id']==episode['id'] for e in p['episodes'])),{})
  video=next(s for s in prepared['info']['streams'] if s.get('codec_type')=='video')
  meta={**public,'id':version['id'],'title':episode['title'],'description':episode.get('description') or group.get('description',''),'show_title':group.get('title',episode['title']),'show_logo':group.get('show_logo'),'brands':self.brands([programme.get('provider','')]),'duration_seconds':seconds(episode.get('duration_seconds')),'start_position':position,'live':bool(episode.get('live')),'quality':'HD' if video.get('height',0)>=720 else 'SD'}
  prepared.update(_watch_id=version['id'],_watch_meta=meta,_watch_position=position,_watch_started=time.time())
  return prepared,episode
