"""Explainable local recommendations and sourced UK certifications."""
import collections,json,time,re
from pathlib import Path

def normal_title(value):return re.sub(r'[^\w]+',' ',value.casefold()).strip()

VALID={'U','PG','12','12A','15','18','R18'}
def uk_rating(data,kind):
 if kind=='tv':
  values={r.get('rating','').strip().upper() for r in data.get('results',[]) if r.get('iso_3166_1')=='GB'}
 else:
  releases=[d for r in data.get('results',[]) if r.get('iso_3166_1')=='GB' for d in r.get('release_dates',[])]
  selected=[d for d in releases if d.get('type')==4] or [d for d in releases if d.get('type') in (3,5,6)]
  values={r.get('certification','').strip().upper() for r in selected}
 values=values & VALID
 return next(iter(values)) if len(values)==1 else None

def genre_matches(candidate,genre):
 target=normal_title(genre)
 return any(target==normal_title(g) or target in normal_title(g).split(' and ') for g in candidate.get('genres',[]))

def activity(p):
 return max([float(p.get('favourite_at') or 0)]+[float(e.get('updated_at') or 0) for e in p.get('episodes',[])])


def tags(p):
 from library_browse import GENRES,genres
 values=p.get('genres',[])
 exact={name for name in GENRES if name.casefold() in {str(g).casefold() for g in values}}
 mapped=set(genres(values))
 if any('documentar' in str(g).casefold() for g in values):mapped.add('Documentaries')
 return exact|mapped


def formats(p):
 text=normal_title(p['title']+' '+str(p.get('description') or '')+' '+' '.join(p.get('genres',[])))
 title=normal_title(p['title']);result=set()
 if re.search(r'\b(panel|quiz|game show|gameshow)\b',text) or any(t in title for t in ('taskmaster','would i lie','cats does countdown','have i got news','have i got a bit more news','house of games')) or title in ('qi','qi xl'):result.add('panel')
 if re.search(r'\b(sitcom|sitcoms)\b|comedy (?:series|starring)',text):result.add('sitcom')
 if re.search(r'\bstand up\b|live at the apollo|comedy roadshow',text):result.add('stand-up')
 for name,words in [('travel',('travel','journey','hotels','cruise')),('history',('history','historical','ancient')),('nature',('wildlife','nature','planet earth'))]:
  if any(word in text for word in words):result.add(name)
 if {'Comedy','Documentaries'}<=tags(p) and not result & {'panel','sitcom','stand-up'}:result.add('comedy-documentary')
 return result


def child_title(p):
 text=normal_title(p['title']+' '+' '.join(p.get('genres',[])))
 return 'Children' in tags(p) or bool(re.search(r'\b(children|cbeebies|kids|animation|scooby|peppa|bluey)\b',text))


STOP=set('a an the and or of to for in on with from by at as is it its this that your you their they his her our all new more most very one two three four five series show shows episode episodes programme programmes tv television bbc channel comedy comedians comedian entertainment documentary documentaries film films movie movies starring stars star featuring feature watch world british britain best great greatest years year first last life story stories'.split())
def words(p):
 return {w for w in normal_title(p['title']+' '+str(p.get('description') or '')).split() if len(w)>2 and not w.isdigit() and w not in STOP}


def taste(library,prefer_films=False):
 import math
 weights=collections.Counter();features=collections.Counter();terms=collections.Counter();media=collections.Counter()
 seeds=[p for p in library if not p.get('live') and not child_title(p) and (p.get('favourite') or p.get('recent') or p.get('resume_episode'))]
 # Do not infer interest from catalogue import time or provider catalogue size.
 documents=collections.Counter(w for p in seeds for w in words(p))
 for p in seeds:
  score=(4 if p.get('favourite') else 0)+(1 if p.get('recent') else 0)
  stamp=max([float(e.get('updated_at') or 0) for e in p.get('episodes',[])]+[0])
  if stamp:score+=3*math.exp(-max(0,time.time()-stamp)/(30*86400))
  if not score:continue
  if prefer_films and p.get('film'):score*=4
  media['film' if p.get('film') else 'show']+=score
  for tag in tags(p):weights[tag]+=score
  for feature in formats(p):features[feature]+=score
  for word in words(p):terms[word]+=score*(1+math.log((1+len(seeds))/(1+documents[word])))
 return weights,features,terms,media


def provider(p):return (p.get('brands') or [{}])[0].get('id','unknown')


def diverse_rank(scored,limit,provider_cap=None):
 # Relevance remains primary; a recent window discourages repeated providers and
 # formats without permanently discarding their later pages.
 import hashlib,datetime
 day=datetime.datetime.now(datetime.timezone.utc).date().isoformat()
 def tie(p):return hashlib.sha256((day+normal_title(p['title'])).encode()).hexdigest()
 unique={}
 for score,p in scored:
  key=(normal_title(p['title']),bool(p.get('film')))
  old=unique.get(key)
  if old is None:unique[key]=(score,p)
  else:
   chosen=p if bool(p.get('episodes')) and not bool(old[1].get('episodes')) else old[1]
   unique[key]=(max(score,old[0]),chosen)
 pool=sorted(unique.values(),key=lambda row:(-row[0],tie(row[1])))
 details={id(p):(provider(p),formats(p)) for _,p in pool}
 result=[];counts=collections.Counter();recent=[]
 while pool and len(result)<limit:
  window=pool[:240];best=None;best_value=-1
  recent_providers=collections.Counter(details[id(p)][0] for p in recent[-8:])
  recent_formats=collections.Counter(f for p in recent[-8:] for f in details[id(p)][1])
  for index,(score,p) in enumerate(window):
   service,f=details[id(p)]
   if provider_cap is not None and counts[service]>=provider_cap:continue
   repetition=max((recent_formats[x] for x in f),default=0)
   value=score/(1+0.36*recent_providers[service]+0.12*repetition)
   if value>best_value:best=index;best_value=value
  if best is None:
   # A cap must not let an overfull provider hide the next eligible provider.
   pool=[row for row in pool if counts[provider(row[1])]<provider_cap]
   continue
  _,p=pool.pop(best);result.append(p);counts[provider(p)]+=1;recent.append(p)
 return result


def recommend(library,candidates,limit=16,genre=None,provider_cap=6,include_known=False,include_unmatched=False,prefer_films=False):
 import math
 weights,features,terms,media=taste(library,prefer_films=prefer_films)
 if genre:weights[genre]=max(weights.values(),default=5)
 maximum=max(weights.values(),default=1);feature_max=max(features.values(),default=1);term_max=max(terms.values(),default=1)
 known={normal_title(p['title']) for p in library if p.get('favourite') or p.get('recent')}
 ranked=[]
 for p in candidates:
  base=re.sub(r'\s*\((?:signed|audio described)\)\s*$','',p['title'],flags=re.I)
  if base!=p['title'] and normal_title(base) in known and not p.get('favourite'):continue
  if p.get('live') or (not include_known and normal_title(base) in known):continue
  if genre and not genre_matches(p,genre):continue
  if child_title(p) and not (genre and any(t in genre.casefold() for t in ('children','kids','animation','family'))):continue
  matches=sorted((weights[g]/maximum for g in tags(p) if weights[g]>0),reverse=True)
  if genre and not matches:matches=[weights[genre]/maximum]
  if not matches and not include_unmatched:continue
  score=(matches[0]+sum(matches[1:])*0.035) if matches else 0.12
  form=formats(p)
  affinity=max((features[f]/feature_max for f in form),default=0)
  score+=0.75*affinity
  if 'comedy-documentary' in form and max(features['panel'],features['sitcom'],features['stand-up'])>features['comedy-documentary']*2:score*=0.65
  token_set=words(p)
  text_match=sum(terms[w]/term_max for w in token_set if terms[w]>0)/max(2,math.sqrt(len(token_set)))
  score+=min(0.5,text_match*0.4)
  if p.get('film') and media['show']>=media['film']*1.2:score*=0.25
  if 'Horror' in tags(p) and weights['Horror']<maximum*0.5:score*=0.3
  if prefer_films and time.gmtime().tm_mon not in (11,12) and re.search(r'\b(christmas|festive)\b',normal_title(p['title'])):score*=0.45
  best_genre=next((g for g,_ in weights.most_common() if g in tags(p)),genre)
  row=dict(p);row['recommendation_reason']=p.get('popularity_source') or ('More '+best_genre.lower()+' for you' if best_genre else 'Matches your viewing')
  ranked.append((score,row))
 return diverse_rank(ranked,limit,provider_cap)


def personal_shows(library,genre=None,limit=16):
 candidates=[p for p in library if not p.get('live') and not p.get('film') and (p.get('favourite') or p.get('recent') or activity(p)) and (not genre or genre_matches(p,genre))]
 # Real watch/favourite actions come first. Provider favourites without known
 # dates remain eligible; sync/import timestamps are deliberately ignored.
 relevant=recommend(library,candidates,len(candidates),genre=genre,provider_cap=None,include_known=True,include_unmatched=True)
 order={p['id']:i for i,p in enumerate(relevant)}
 candidates.sort(key=lambda p:(-activity(p),not p.get('favourite'),not p.get('recent'),order.get(p['id'],len(order))))
 return candidates[:limit]


def genre_order(library):
 available={g for p in library if not p.get('live') and not p.get('film') for g in p.get('genres',[])}
 weights,_,_,_=taste(library)
 return sorted(available,key=lambda g:(-weights[g],g.casefold()))


def featured_shows(library,limit=6):
 candidates=[p for p in library if not p.get('live') and not p.get('film') and p.get('episodes') and (p.get('hero') or p.get('artwork')) and not child_title(p)]
 ranked=recommend(library,candidates,120,provider_cap=None,include_known=True,include_unmatched=True)
 # Blend familiar highlights and relevant ready-to-play library discoveries.
 recent=personal_shows(candidates,limit=limit)
 pool=[];seen=set()
 for p in recent[:3]+ranked:
  if p['id'] not in seen:pool.append(p);seen.add(p['id'])
  if len(pool)>=40:break
 # Keep a current highlight first, then vary providers and programme formats.
 if not pool:return []
 rest=diverse_rank([(1-i*0.008,p) for i,p in enumerate(pool[1:])],limit-1,None)
 return pool[:1]+rest

class Ratings:
 def __init__(self,private,root):
  self.private=Path(private);self.path=Path(root)/'uk-ratings.json'
  try:self.cache=json.loads(self.path.read_text())
  except (OSError,ValueError):self.cache={}
 def enrich(self,programmes):
  for p in programmes:
   row=self.cache.get(p['id'],{})
   if row.get('rating'):p.update(content_rating=row['rating'],rating_source='UK certification · TMDB')
  return programmes
 def refresh(self,programmes,limit=35):
  credential=self.private/'tmdb-token'
  if not credential.exists():return
  from tmdb_logos import TMDB,normal,atomic
  client=TMDB(credential.read_text());manifest={}
  try:manifest=json.loads((self.private/'tmdb-logo-manifest.json').read_text())
  except (OSError,ValueError):pass
  items=sorted(programmes,key=lambda p:(not p.get('favourite'),not p.get('recent'),not p.get('film')))
  checked=0
  for p in items:
   if p.get('live') or time.time()-self.cache.get(p['id'],{}).get('checked_at',0)<14*86400:continue
   m=manifest.get(p['id'],{})
   # Do not transfer the original edition's rating to a bleeped/extended version.
   if not m.get('tmdb_id') or normal(m.get('matched_title',''))!=normal(p['title']):continue
   kind=m.get('media_type','tv')
   try:
    data=client.get(f"{kind}/{m['tmdb_id']}/"+('release_dates' if kind=='movie' else 'content_ratings'))
    self.cache[p['id']]={'rating':uk_rating(data,kind),'checked_at':time.time()}
    checked+=1
   except Exception:continue
   if checked>=limit:break
  atomic(self.path,json.dumps(self.cache).encode())


def featured_films(library,day=None,limit=6):
 """Daily, taste-led film picks with varied genres, providers and stable identities."""
 import hashlib,datetime
 day=day or datetime.datetime.now(datetime.timezone.utc).date().isoformat()
 films=[p for p in library if p.get('film') and not p.get('live') and not p.get('recent') and p.get('episodes') and (p.get('hero') or p.get('artwork'))]
 films=[p for p in films if any(3000<=float(e.get('duration_seconds') or 0)<=14400 for e in p['episodes'])]
 preferred=recommend(library,films,limit=80,provider_cap=None)
 pool=preferred[:40] or films
 def day_order(p):return hashlib.sha256((day+p['id']).encode()).hexdigest()
 pool=sorted(pool,key=day_order)
 chosen=[];genres=collections.Counter();providers=collections.Counter();seen=set()
 for relaxed in (False,True):
  for p in pool:
   if p['id'] in seen:continue
   genre=next(iter(p.get('genres',[])),'Other');provider=(p.get('brands') or [{}])[0].get('id','')
   if not relaxed and (genres[genre]>=2 or providers[provider]>=3):continue
   seen.add(p['id']);chosen.append(p);genres[genre]+=1;providers[provider]+=1
   if len(chosen)>=limit:return chosen
 return chosen


def ranked_films(library):
 """Taste-led film shelf; preserve every playable film and stable daily ties."""
 import hashlib,datetime
 films=[p for p in library if p.get('film') and not p.get('live')]
 ranked=recommend(library,films,len(films),provider_cap=None,include_known=True,include_unmatched=True,prefer_films=True)
 by_id={p['id']:p for p in films}
 ranked=[by_id[p['id']] for p in ranked]
 seen={p['id'] for p in ranked}
 day=datetime.datetime.now(datetime.timezone.utc).date().isoformat()
 # Explicit family editions and alternate cuts remain browsable, even when the
 # recommendation engine omits them. Never drop films from their catalogue.
 ranked+=sorted((p for p in films if p['id'] not in seen),key=lambda p:hashlib.sha256((day+p['id']).encode()).hexdigest())
 def completed(p):
  return any(e.get('completed') or float(e.get('progress') or 0)>=95 for e in p.get('episodes',[]))
 continuing=sorted((p for p in ranked if p.get('resume_episode') and not completed(p)),key=activity,reverse=True)[:4]
 seen={p['id'] for p in continuing}
 remaining=[p for p in ranked if p['id'] not in seen]
 return continuing+[p for p in remaining if not completed(p)]+[p for p in remaining if completed(p)]
