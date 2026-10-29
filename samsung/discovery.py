"""Public provider metadata discovery. No playback URLs, DRM or account-list writes."""
import concurrent.futures,hashlib,json,re,time,threading
from pathlib import Path
from urllib.parse import urlencode
import requests
from episode_artwork import bbc_image

PROVIDERS={'itv':('ITVX','itv'),'bbc':('BBC iPlayer','bbc'),'channel4':('Channel 4','channel4'),'u':('U','u'),'channel5':('Channel 5','channel5')}
def normal(text):return re.sub(r'[^\w]+',' ',str(text).casefold()).strip()
def five_genres(item):
 from library_browse import genres
 values=[item.get('genre'),item.get('primary_vod_genre')]+list(item.get('vod_subgenres') or [])
 values=[str(value) for value in values if value]
 canonical=genres(values)
 if any('documentar' in value.casefold() or value.casefold()=='factual' for value in values) and 'Documentaries' not in canonical:canonical.append('Documentaries')
 if item.get('child_directed') and 'Children' not in canonical:canonical.append('Children')
 return list(dict.fromkeys(canonical+values))

def picture(value):
 if isinstance(value,dict):value=next((value[k] for k in ('promotional','standard','url','src') if value.get(k)), '')
 return str(value or '').replace('{recipe}','1280x720').replace('{&resize}','&resize=1280:720')
def bbc_state(html):
 match=re.search(r'window\.__IPLAYER_REDUX_STATE__\s*=\s*(.*?);?\s*</script>',html,re.S)
 if not match:raise ValueError('BBC catalogue unavailable')
 return json.loads(match[1].strip().rstrip(';'))
def c4_state(html):
 match=re.search(r'window\.__PARAMS__\s*=\s*\{\s*"initialData":',html)
 if not match:raise ValueError('Channel 4 catalogue unavailable')
 return json.JSONDecoder().raw_decode(html[match.end():])[0]

class Discovery:
 def __init__(self,root,base):
  self.root=Path(root);self.base=base.rstrip('/');self.cache={};self.previews={};self.lock=threading.Lock();self.recommendation_lock=threading.Lock()
  try:self.imported=json.loads((self.root/'discovery-library.json').read_text())
  except (OSError,ValueError):self.imported={}
  self.itv_enabled=(self.root/'itv-pi-verified.json').exists();self.itv=[]
  try:self.itv_raw=json.loads((self.root/'itv-index.json').read_text())
  except (OSError,ValueError):self.itv_raw={}
  self.alternates={};self.c4=[];self.five=[];self.hot=[];self.suggestions=[];self.status={}
 def get(self,url,**params):
  r=requests.get(url,params=params,timeout=(5,15),headers={'User-Agent':'Mozilla/5.0'});r.raise_for_status();return r
 def preview(self,provider,key,title,description='',image='',genre='',film=False):
  if not re.fullmatch(r'[A-Za-z0-9_-]{1,120}',str(key)):return None
  ref=provider+':'+str(key);ident='discover_'+hashlib.sha256(ref.encode()).hexdigest()[:20]
  name,brand=PROVIDERS[provider]
  row={'id':ident,'discovery_ref':ref,'title':title,'description':description,'artwork':picture(image),'hero':picture(image),'live':False,'film':film,'recent':False,'favourite':False,'genres':[g.strip() for g in genre.split(' · ') if g.strip()],'brands':[{'id':brand,'name':name,'image':self.base+'/static/artwork/brands/'+brand+'.png'}],'episodes':[]}
  self.previews[ref]=row;return row
 def itv_preview(self,p):
  self.itv_raw[p['key']]=p
  return self.preview('itv',p['key'],p['title'],p['description'],p['artwork'],p['genre'],p['film'])
 def itv_search(self,query):
  if not self.itv_enabled:return []
  from itv_catalogue import search
  rows=[self.itv_preview(p) for p in search(query)]
  from tmdb_logos import atomic
  atomic(self.root/'itv-index.json',json.dumps(self.itv_raw).encode())
  return rows
 def warm_itv(self):
  if not self.itv_enabled:return []
  from itv_catalogue import highlights
  try:
   stamp=self.root/'itv-index.json'
   if not self.itv_raw or time.time()-stamp.stat().st_mtime>21600:
    for p in highlights():self.itv_raw[p['key']]=p
    from tmdb_logos import atomic
    atomic(stamp,json.dumps(self.itv_raw).encode())
   self.itv=[self.itv_preview(p) for p in list(self.itv_raw.values())]
   self.status['itv']='ready'
  except Exception:self.status['itv']='temporarily unavailable'
 def load_itv(self,key):
  if not self.itv_enabled:raise ValueError('ITV Pi playback has not been verified.')
  from itv_catalogue import details
  summary=self.itv_raw.get(key)
  if not summary:raise ValueError('Search for this ITV programme again')
  show=details(summary)
  show['episodes']=[dict(ep,kind='provider') for ep in show.get('episodes',[]) if not ep.get('premium')]
  return show
 def bbc_search(self,query):
  state=bbc_state(self.get('https://www.bbc.co.uk/iplayer/search',q=query).text)
  return [self.preview('bbc',p['id'],p['title'],p.get('synopses',{}).get('small',''),p.get('images'),p.get('labels',{}).get('category','')) for p in state.get('entities',{}).get('results',[]) if p.get('type')=='programme' and p.get('initial_children')][:16]
 def u_search(self,query):
  data=self.get('https://vschedules.uktv.co.uk/vod/search/',q=query).json()
  return [self.preview('u',p['slug'],p['name'],p.get('synopsis',''),p.get('img_url',''),p.get('primary_category','')) for p in data if p.get('type')=='BRAND' and p.get('ep_count',0)>0][:16]
 def five_preview(self,p):
  return self.preview('channel5',str(p['id']),p['title'],p.get('m_desc') or p.get('s_desc',''),'https://api-images.channel5.com/otis/images/show/'+str(p['id'])+'/1280x720.jpg',' · '.join(five_genres(p)),p.get('genre')=='Film')
 def five_search(self,query):
  data=self.get('https://corona.channel5.com/shows/search.json',platform='my5desktop',friendly=1,query=query,limit=16).json()
  return [self.five_preview(p) for p in data.get('shows',[])]
 def five_page(self,offset=0):
  data=self.get('https://corona.channel5.com/shows/search.json',platform='my5desktop',friendly=1,offset=offset,limit=200).json()
  return [self.five_preview(p) for p in data.get('shows',[])],int(data.get('total_entries',0))
 def warm_five(self):
  from tmdb_logos import atomic
  cache=self.root/'discovery-five-index.json'
  try:
   if cache.exists() and time.time()-cache.stat().st_mtime<21600:
    self.five=json.loads(cache.read_text())
   else:
    first,total=self.five_page();rows=first
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
     futures=[pool.submit(self.five_page,offset) for offset in range(200,min(total,6000),200)]
     for future in futures:rows.extend(future.result()[0])
    self.five=list({p['discovery_ref']:p for p in rows if p}.values())
    atomic(cache,json.dumps(self.five).encode())
   for p in self.five:self.previews[p['discovery_ref']]=p
   self.status['channel5']='ready'
  except Exception:
   if not self.five and cache.exists():
    try:self.five=json.loads(cache.read_text())
    except (OSError,ValueError):pass
   self.status['channel5']='cached' if self.five else 'temporarily unavailable'
 def c4_page(self,offset=0,category='',order=None):
  data=c4_state(self.get('https://www.channel4.com/categories'+('/'+category if category else ''),offset=offset,sort=order or ('popular' if category else 'az')).text)
  rows=[]
  for p in data.get('brands',{}).get('items',[]):
   detail=p.get('expandedTile',{});row=self.preview('channel4',p['websafeTitle'],p.get('labelText') or detail.get('title',''),detail.get('summary') or p.get('overlayText',''),p.get('imageLink',''),' · '.join(detail.get('genres',[])), 'Film' in detail.get('genres',[]))
   if row:rows.append(row)
  return rows,data.get('noOfShows',len(rows))
 def warm(self):
  try:
   cache=self.root/'discovery-c4-index.json'
   if cache.exists() and time.time()-cache.stat().st_mtime<21600:
    self.c4=json.loads(cache.read_text())
    for p in self.c4:self.previews[p['discovery_ref']]=p
   else:
    first,total=self.c4_page();rows=first
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
     futures=[pool.submit(self.c4_page,offset) for offset in range(60,min(total,3600),60)]
     for f in futures:
      try:rows.extend(f.result()[0])
      except Exception:pass
    self.c4=list({p['discovery_ref']:p for p in rows}.values())
    from tmdb_logos import atomic
    atomic(cache,json.dumps(self.c4).encode())
   self.status['channel4']='ready'
  except Exception:self.status['channel4']='temporarily unavailable'
  self.warm_five()
  self.warm_itv()
  hot=[]
  try:
   data=self.get('https://ibl.api.bbc.co.uk/ibl/v1/groups/popular/episodes',per_page=50).json()['group_episodes']['elements']
   for p in data:
    if p.get('status')!='available' or not p.get('tleo_id'):continue
    row=self.preview('bbc',p['tleo_id'],p['title'],p.get('synopses',{}).get('small',''),p.get('images'),p.get('labels',{}).get('category',''))
    if row:row['recommendation_reason']='Popular today on BBC iPlayer';row['popularity_source']='Popular on BBC iPlayer';hot.append(row)
  except Exception:pass
  try:
   popular,_=self.c4_page(order='popular')
   for p in popular[:20]:p['popularity_source']='Popular on Channel 4';p['recommendation_reason']=p['popularity_source'];hot.append(p)
  except Exception:pass
  self.hot=list({p['discovery_ref']:p for p in hot}.values())[:60]
  try:
   rows,_=self.c4_page(category='comedy');self.suggestions=rows[:24]
   for genre in ('comedy','documentaries'):
    data=self.get('https://ibl.api.bbc.co.uk/ibl/v1/categories/'+genre+'/programmes',per_page=24,page=1).json()['category_programmes']['elements']
    for p in data:
     if p.get('initial_children'):
      row=self.preview('bbc',p['id'],p['title'],p.get('synopses',{}).get('small',''),p.get('images'),p.get('labels',{}).get('category',genre.title()))
      if row:self.suggestions.append(row)
  except Exception:pass
  self.suggestions=list({p['id']:p for p in self.suggestions+[p for p in self.five if not p.get('film')]}.values())
 def genre_candidates(self,genre):
  key='genre:'+genre.casefold();cached=self.cache.get(key)
  if cached and time.time()-cached[0]<1800:return cached[1]
  from recommendations import genre_matches
  rows=[p for p in self.c4+self.five+self.itv if genre_matches(p,genre)]
  mapping={'comedy':'comedy','drama':'drama-and-soaps','documentaries':'documentaries','entertainment':'entertainment','food':'food','history':'history','science':'science-and-nature','nature':'science-and-nature','children':'cbbc'}
  slug=mapping.get(genre.casefold())
  if slug:
   try:
    for page in range(1,21):
     block=self.get('https://ibl.api.bbc.co.uk/ibl/v1/categories/'+slug+'/programmes',per_page=200,page=page).json()['category_programmes']
     data=block.get('elements',[])
     for p in data:
      if not p.get('initial_children'):continue
      row=self.preview('bbc',p['id'],p['title'],p.get('synopses',{}).get('small',''),p.get('images'),genre)
      if row:rows.append(row)
     if not data or page*200>=block.get('count',len(data)):break
   except Exception:pass
  self.cache[key]=(time.time(),rows)
  return rows
 def recommendation_candidates(self,library):
  with self.recommendation_lock:return self.recommendation_candidates_locked(library)
 def recommendation_candidates_locked(self,library):
  from recommendations import taste
  weights,_,_,_=taste(library)
  selected=tuple(g for g,_ in weights.most_common(5)) or ('Comedy','Documentaries','Drama')
  key='recommendation-pool:'+','.join(selected)
  cached=self.cache.get(key)
  if cached and time.time()-cached[0]<1800:return cached[1]+library
  rows=list(self.c4)+list(self.five)+list(self.itv)+list(self.suggestions)
  # A full Five catalogue must compete with full relevant BBC categories and
  # Channel 4's index, rather than just a handful of their home-page picks.
  with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
   for batch in pool.map(self.genre_candidates,selected):rows.extend(batch)
  merged={}
  for p in rows:
   ident=p.get('discovery_ref') or p['id']
   if ident not in merged:merged[ident]=dict(p,genres=list(p.get('genres',[])))
   else:merged[ident]['genres']=list(dict.fromkeys(merged[ident]['genres']+p.get('genres',[])))
  result=list(merged.values());self.cache[key]=(time.time(),result)
  return result+library

 def search(self,query):
  query=' '.join(query.split())[:100];key=query.casefold()
  if len(query)<2:return {'programmes':[],'status':{}}
  cached=self.cache.get(key)
  if cached and time.time()-cached[0]<600:return cached[1]
  rows=[];status={}
  with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
   futures={pool.submit(fn,query):name for name,fn in [('bbc',self.bbc_search),('u',self.u_search),('channel5',self.five_search)]+([('itv',self.itv_search)] if self.itv_enabled else [])}
   for future,name in futures.items():
    try:rows.extend(x for x in future.result() if x);status[name]='ready'
    except Exception:status[name]='temporarily unavailable'
  terms=normal(query).split()
  rows.extend(p for p in self.c4 if all(t in normal(p['title']) for t in terms));status['channel4']=self.status.get('channel4','indexing')
  rows.sort(key=lambda p:(normal(p['title'])!=normal(query),not normal(p['title']).startswith(normal(query)),p['title'].casefold()))
  grouped={}
  for p in rows:
   key=(normal(p['title']),p['film'])
   if key not in grouped:
    grouped[key]=dict(p);self.alternates[p['discovery_ref']]=[p['discovery_ref']]
   else:
    target=grouped[key];self.alternates[target['discovery_ref']].append(p['discovery_ref'])
    target['brands']=list({b['id']:b for b in target['brands']+p['brands']}.values())
  result={'programmes':list(grouped.values())[:64],'status':status}
  if len(self.cache)>100:self.cache.clear()
  self.cache[key]=(time.time(),result);return result
 def import_show(self,ref):
  first=None
  for source in self.alternates.get(ref,[ref])[:4]:
   try:
    programme=self.import_one(source)
    if first is None:first=programme
   except Exception:
    if len(self.alternates.get(ref,[ref]))==1:raise
  if first is None:raise ValueError('No available episodes were found.')
  return first
 def import_one(self,ref):
  provider,key=ref.split(':',1)
  if provider not in PROVIDERS or not re.fullmatch(r'[A-Za-z0-9_-]{1,120}',key):raise ValueError('Invalid programme')
  with self.lock:
   cached=self.imported.get(ref)
   if cached and time.time()-cached['checked_at']<21600:return cached['programme']
   show=getattr(self,'load_'+provider)(key)
   for episode in show.get('episodes',[]):
    if episode.get('kind')=='plugin':episode['quality']='720p50,720p_hls,540p,396p'
   if not show.get('episodes'):raise ValueError('No available episodes were found.')
   show.update(favourite=False,recent=False)
   self.imported[ref]={'checked_at':time.time(),'programme':show}
   self.imported=dict(sorted(self.imported.items(),key=lambda x:x[1]['checked_at'],reverse=True)[:80])
   from tmdb_logos import atomic
   atomic(self.root/'discovery-library.json',json.dumps(self.imported).encode());return show
 def load_bbc(self,key):
  from episode_versions import seconds
  episodes=[];programme={}
  for page in range(1,21):
   data=self.get('https://ibl.api.bbc.co.uk/ibl/v1/programmes/'+key+'/episodes',per_page=200,page=page).json()['programme_episodes'];programme=data.get('programme') or programme
   elements=data.get('elements',[]);episodes.extend(elements)
   if page*200>=data.get('count',len(episodes)) or not elements:break
  p=programme;first=next(iter(episodes),{})
  show={'id':'bbc_'+key,'title':p.get('title') or first.get('title',key),'provider':'BBC iPlayer','provider_id':'bbc','description':p.get('synopses',{}).get('small') or first.get('synopses',{}).get('small',''),'artwork':picture(p.get('images') or first.get('images')),'hero':picture(first.get('images')),'genre':first.get('labels',{}).get('category',''),'episodes':[]}
  for ep in episodes:
   if ep.get('status') not in (None,'available') or ep.get('signed'):continue
   sub=ep.get('subtitle') or 'Episode';match=re.search(r'(?:Series|Season)\s+(\d+)',sub,re.I);num=re.search(r'(?:Episode\s+|:\s*)(\d+)',sub)
   version=next((v for v in ep.get('versions',[]) if v.get('kind') in ('original','editorial')),{});duration=version.get('duration',{})
   show['episodes'].append({'id':'bbc_'+key+'_'+ep['id'],'title':sub,'season':int(match[1]) if match else 'Episodes','episode_number':int(num[1]) if num else ep.get('parent_position',0),'description':ep.get('synopses',{}).get('medium') or ep.get('synopses',{}).get('small',''),'thumbnail':bbc_image(ep.get('images')),'duration_seconds':seconds(duration.get('value') or duration.get('seconds')),'kind':'plugin','url':'https://www.bbc.co.uk/iplayer/episode/'+ep['id'],'quality':'best','delivery':'relay','preserve_timestamps':True,'live':False})
  return show
 def load_channel4(self,key):
  # Reuse the proven metadata-only importer, scoped to exactly one selected title.
  from library_sync import LibrarySync
  class OneShow(LibrarySync):
   def get(inner,session,url,**kwargs):
    if '/my4.json' in url:
     class Reply:
      def json(self):return {'sliceGroups':[{'slices':[{'type':'MYLIST','sliceItems':[{'brand':{'websafeTitle':key}}]}]}]}
     return Reply()
    return super().get(session,url,**kwargs)
  # The source catalogue is configured by the gateway, never supplied by the client.
  sync=OneShow(self.root.parent, self.catalogue_path);sync.films={}
  rows=sync.c4()
  if not rows:raise ValueError('No available episodes were found.')
  return rows[0]
 def load_u(self,key):
  b=self.get('https://vschedules.uktv.co.uk/vod/brand/',slug=key).json();pid='u_'+key
  show={'id':pid,'title':b.get('name') or b.get('brand_name',key),'provider':'U','provider_id':'u','description':b.get('description') or b.get('synopsis',''),'artwork':picture(b.get('image') or b.get('images')),'hero':picture(b.get('hero_image_4k') or b.get('image')),'genre':b.get('primary_category',''),'episodes':[]}
  for series in b.get('series',[])[:30]:
   data=self.get('https://vschedules.uktv.co.uk/vod/series/',id=series['id']).json()
   for ep in data.get('episodes',[]):
    vid=str(ep.get('video_id') or '')
    if not vid:continue
    mins=ep.get('duration') or 0
    try:duration=float(mins)*60
    except (ValueError,TypeError):duration=0
    show['episodes'].append({'id':pid+'_'+vid,'provider_id':'u','provider_episode_id':vid,'kind':'provider','title':ep.get('episode_name') or ep.get('name') or 'Episode','season':ep.get('series_number') or series.get('series_number') or 'Episodes','episode_number':ep.get('episode_number',0),'description':ep.get('synopsis') or ep.get('description',''),'thumbnail':picture(ep.get('image') or ep.get('img_url')),'duration_seconds':duration,'live':False})
  return show
 def load_channel5(self,key):
  b=self.get('https://corona.channel5.com/shows/'+key+'.json',platform='my5desktop',friendly=1).json();slug=b['f_name'];pid='five_'+key
  data=self.get('https://corona.channel5.com/shows/'+slug+'/episodes.json',platform='my5desktop',friendly=1,limit=1000).json()
  show={'id':pid,'title':b['title'],'provider':'Channel 5','provider_id':'channel5','media_type':'movie' if b.get('genre')=='Film' else 'tv','genre':' · '.join(five_genres(b)),'description':b.get('m_desc') or b.get('s_desc',''),'artwork':'https://api-images.channel5.com/otis/images/show/'+key+'/1280x720.jpg','hero':'https://api-images.channel5.com/otis/images/show/'+key+'/1920x1080.jpg','episodes':[]}
  for ep in data.get('episodes',[]):
   if ep.get('vod_s',0)>time.time() or (ep.get('vod_e') and ep['vod_e']<time.time()):continue
   show['episodes'].append({'id':pid+'_'+ep['id'],'provider_id':'channel5','provider_episode_id':ep['id'],'kind':'provider','title':ep.get('title') or 'Episode','season':ep.get('sea_num') or 'Episodes','episode_number':ep.get('ep_num',0),'description':ep.get('m_desc') or ep.get('s_desc',''),'thumbnail':'https://api-images.channel5.com/otis/images/episode/'+ep['id']+'/1280x720.jpg','duration_seconds':ep.get('len',0)/1000,'live':False})
  return show
