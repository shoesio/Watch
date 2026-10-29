"""Related-show metadata, verified against the actual supported provider catalogues."""
import collections,concurrent.futures,json,time
from pathlib import Path
from recommendations import recommend,normal_title


def relation_candidates(seed,credits,person_credits,creator_credits,productions):
 """Pure ranking of documented relationships; no provider availability assumptions."""
 rows={};seed_id=seed['id']
 def add(item,score,reason):
  ident=item.get('id');title=item.get('name')
  if not ident or ident==seed_id or not title:return
  entry=rows.setdefault(ident,{'id':ident,'title':title,'score':0,'relations':set()})
  entry['score']+=score;entry['relations'].add(reason)
 for person,data in person_credits:
  for item in data.get('cast',[]):
   # A credited appearance is a relationship, not proof of a starring role.
   add(item,35 if item.get('episode_count',2)>=2 else 8,'Shared cast: '+person['name'])
 for person,data in creator_credits:
  for item in data.get('crew',[]):
   if item.get('job') in ('Creator','Writer','Executive Producer','Director','Producer'):
    add(item,45,'Shared creator/production: '+person['name'])
 for item in productions:add(item,15,'Related production company')
 for kind,score in [('recommendations',20),('similar',12)]:
  for item in seed.get(kind,{}).get('results',[]):add(item,score,'Related programme metadata')
 return sorted(rows.values(),key=lambda r:(-r['score'],r['title'].casefold()))

class RelatedShows:
 def __init__(self,private,root,discovery):
  self.private=Path(private);self.root=Path(root);self.discovery=discovery;self.http_cache={};self.cache={}
  for name,attribute in [('related-tmdb-cache.json','http_cache'),('related-shows-cache-v2.json','cache')]:
   try:setattr(self,attribute,json.loads((self.root/name).read_text()))
   except (OSError,ValueError):pass
 def get(self,client,route,**params):
  key=route+'?'+json.dumps(params,sort_keys=True);cached=self.http_cache.get(key)
  if cached and time.time()-cached['time']<7*86400:return cached['data']
  data=client.get(route,**params);self.http_cache[key]={'time':time.time(),'data':data}
  from tmdb_logos import atomic
  if len(self.http_cache)>160:self.http_cache=dict(list(self.http_cache.items())[-160:])
  atomic(self.root/'related-tmdb-cache.json',json.dumps(self.http_cache).encode());return data
 def relationships(self,programme):
  credential=self.private/'tmdb-token'
  if not credential.exists():return []
  from tmdb_logos import TMDB
  client=TMDB(credential.read_text())
  try:manifest=json.loads((self.private/'tmdb-logo-manifest.json').read_text())
  except (OSError,ValueError):manifest={}
  match=manifest.get(programme['id'],{})
  if not match.get('tmdb_id'):
   details=client.match(programme['title'],'tv')
   if not details or details.get('_media_type')!='tv':return []
   ident=details['id']
  else:
   if match.get('media_type','tv')!='tv':return []
   ident=match['tmdb_id']
  seed=self.get(client,f'tv/{ident}',append_to_response='aggregate_credits,recommendations,similar',language='en-GB')
  credits=seed.get('aggregate_credits',{})
  ranked_cast=sorted(credits.get('cast',[]),key=lambda p:p.get('total_episode_count',0),reverse=True)
  threshold=max(2,(ranked_cast[0].get('total_episode_count',0)*0.1 if ranked_cast else 2))
  cast=[p for p in ranked_cast if p.get('total_episode_count',0)>=threshold][:4]
  people=[];creators=[]
  # Four recurring cast members, rather than every one-episode guest.
  for person in cast:
   try:people.append((person,self.get(client,f"person/{person['id']}/tv_credits",language='en-GB')))
   except Exception:continue
  for person in seed.get('created_by',[])[:2]:
   try:creators.append((person,self.get(client,f"person/{person['id']}/tv_credits",language='en-GB')))
   except Exception:continue
  productions=[]
  for company in seed.get('production_companies',[])[:1]:
   try:productions.extend(self.get(client,'discover/tv',with_companies=company['id'],sort_by='popularity.desc',language='en-GB').get('results',[]))
   except Exception:continue
  return relation_candidates(seed,credits,people,creators,productions)
 def list(self,programme,library):
  cached=self.cache.get(programme['id'])
  if cached and time.time()-cached['time']<6*3600:return cached['items']
  genres=programme.get('genres',[])[:2]
  candidates=list(library)+list(self.discovery.suggestions)
  for genre in genres:
   try:candidates.extend(self.discovery.genre_candidates(genre))
   except Exception:pass
  seed=dict(programme,favourite=True,recent=True)
  fallback=recommend([seed],candidates,2000,genre=genres[0] if genres else None,provider_cap=None)
  try:relations=self.relationships(programme)
  except Exception:relations=[]
  known=collections.defaultdict(list)
  for p in library+list(self.discovery.c4)+list(getattr(self.discovery,'five',[])):
   if not p.get('live') and not p.get('film'):known[normal_title(p['title'])].append(p)
  selected=[];missing=[]
  for item in relations[:28]:
   matches=known.get(normal_title(item['title']),[])
   if matches:
    for p in matches:selected.append((item['score'],dict(p,similarity_reason=' · '.join(sorted(item['relations'])))))
   else:missing.append(item)
  # Only try the strongest unknown relationships; remaining pages broaden into
  # genuinely related formats and themes rather than inventing cast connections.
  def available(item):
   result=self.discovery.search(item['title'])
   return [(item['score'],dict(p,similarity_reason=' · '.join(sorted(item['relations'])))) for p in result['programmes'] if normal_title(p['title'])==normal_title(item['title']) and not p.get('film')]
  with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
   futures=[pool.submit(available,item) for item in missing[:9]]
   for future in futures:
    try:selected.extend(future.result())
    except Exception:pass
  selected.sort(key=lambda pair:(-pair[0],pair[1]['title'].casefold()))
  rows=[];seen={normal_title(programme['title'])}
  # Avoid presenting the same underlying show as its own relation via an edition alias.
  from tmdb_logos import ALIASES
  if programme['title'].casefold() in ALIASES:seen.add(normal_title(ALIASES[programme['title'].casefold()]))
  for p in [p for _,p in selected]+fallback:
   name=normal_title(p['title'])
   if name in seen or p.get('live') or p.get('film'):continue
   seen.add(name);rows.append(p)
  self.cache[programme['id']]={'time':time.time(),'items':rows}
  if len(self.cache)>30:self.cache=dict(list(self.cache.items())[-30:])
  from tmdb_logos import atomic
  atomic(self.root/'related-shows-cache-v2.json',json.dumps(self.cache).encode());return rows
