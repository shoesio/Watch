"""Programme artwork for Five's live listings, with exact title matching."""
import json,re,time
from pathlib import Path

# Reviewed original US series shown on 5USA; not the 1978 BBC namesake.
REVIEWED_TV={'law and order':549}

def title_key(title):
    return re.sub(r'[^\w]+',' ',str(title).casefold().replace('&',' and ')).strip()

def exact_programme(title,candidates):
    matches=[p for p in candidates if title_key(p.get('title',''))==title_key(title)]
    return next((p for p in matches if p.get('artwork')),None)

class FiveLiveArtwork:
    def __init__(self,private,root):
        self.private=Path(private);self.path=Path(root)/'five-live-artwork.json'
        try:self.cache=json.loads(self.path.read_text())
        except (OSError,ValueError):self.cache={}

    def refresh(self,channels,discovery):
        titles={p.get('_guide',{}).get('now',{}).get('title') for p in channels}
        token=self.private/'tmdb-token';client=None;changed=False
        for title in filter(None,titles):
            key=title_key(title)
            previous=self.cache.get(key,{})
            if time.time()-previous.get('checked_at',0)<(86400 if previous.get('image') else 900) and not (key in REVIEWED_TV and not previous.get('image')):continue
            candidates=list(discovery.five)
            match=exact_programme(title,candidates)
            if not match:
                try:match=exact_programme(title,discovery.five_search(title))
                except Exception:continue
            record={'checked_at':time.time(),'title':title}
            if match:
                record.update(image=match['artwork'],description=match.get('description',''),source='Channel 5 programme catalogue')
            elif token.exists():
                # Native schedule feed has names but no artwork IDs. TMDB can
                # supply series key art for unavailable catch-up titles, only
                # on an exact title match (never an arbitrary search result).
                try:
                    from tmdb_logos import TMDB
                    if client is None:client=TMDB(token.read_text())
                    results=[client.get('tv/'+str(REVIEWED_TV[key]),language='en-GB')] if key in REVIEWED_TV else client.get('search/tv',query=title,language='en-GB',include_adult='false').get('results',[])
                    exact=[p for p in results if title_key(p.get('name',''))==key or title_key(p.get('original_name',''))==key]
                    # Ambiguous remakes are not guessed.
                    if len(exact)==1:
                        p=exact[0];image=p.get('backdrop_path')
                        if image and re.fullmatch(r'/[A-Za-z0-9_.-]+',image):record.update(image='https://image.tmdb.org/t/p/w780'+image,description=p.get('overview',''),source='TMDB exact series title',tmdb_id=p['id'])
                except Exception:continue
            self.cache[key]=record;changed=True
        if changed:
            from tmdb_logos import atomic
            atomic(self.path,json.dumps(self.cache).encode())

    def enrich(self,guide,candidates):
        now=guide.get('now') or {}
        title=now.get('title')
        if not title:return
        match=exact_programme(title,candidates)
        record={'image':match['artwork'],'description':match.get('description',''),'source':'Channel 5 programme catalogue'} if match else self.cache.get(title_key(title),{})
        if record.get('image'):
            now['image']=record['image'];now['image_source']=record['source']
        if not now.get('subtitle') and record.get('description'):now['subtitle']=record['description']
