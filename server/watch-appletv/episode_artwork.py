"""BBC episode stills, matched by BBC PID, separate from promotional artwork."""
import concurrent.futures,html,json,re,time
from pathlib import Path
from urllib.parse import urlparse
import requests


def bbc_image(images,size='960x540'):
    if isinstance(images,dict):
        images=next((images[k] for k in ('standard','promotional','promotional_with_logo','url','src') if images.get(k)), '')
    if not isinstance(images,str):return ''
    value=html.unescape(images).replace('{recipe}',size)
    parsed=urlparse(value)
    return value if parsed.scheme=='https' and parsed.hostname=='ichef.bbci.co.uk' and not parsed.username and not parsed.password else ''


def episode_pid(source):
    match=re.search(r'^https://www\.bbc\.co\.uk/iplayer/episode/([a-z0-9]{8})(?:[/\?#]|$)',str(source.get('url','')))
    return match[1] if match else None


class EpisodeArtwork:
    def __init__(self,root):
        self.path=Path(root)/'bbc-episode-artwork.json'
        try:self.cache=json.loads(self.path.read_text())
        except (OSError,ValueError):self.cache={}

    def enrich(self,programmes,watch):
        images={pid:url for row in list(self.cache.values()) for pid,url in row.get('images',{}).items()}
        for p in programmes:
            if p.get('live'):continue
            for e in p.get('episodes',[]):
                version=watch.index.get(e['id'])
                if not version:continue
                source,provider=watch.quality.preferred(version)
                if provider!='BBC iPlayer':continue
                url=images.get(episode_pid(source))
                if url:e.update(thumbnail=url,thumbnail_source='BBC episode still')
        return programmes

    def fetch(self,key):
        images={}
        for page in range(1,31):
            response=requests.get('https://ibl.api.bbc.co.uk/ibl/v1/programmes/'+key+'/episodes',params={'per_page':200,'page':page},timeout=(5,20))
            response.raise_for_status();block=response.json()['programme_episodes'];rows=block.get('elements',[])
            for e in rows:
                # A missing standard image is not evidence of a distinct still.
                image=bbc_image({'standard':(e.get('images') or {}).get('standard')})
                if image and re.fullmatch(r'[a-z0-9]{8}',str(e.get('id',''))):images[e['id']]=image
            if not rows or page*200>=block.get('count',len(images)):break
        return {'checked_at':time.time(),'images':images}

    def refresh(self,catalogue,force=False):
        keys=set()
        for p in catalogue.get('programmes',[]):
            if p.get('provider')!='BBC iPlayer' or p.get('live_channel'):continue
            match=re.fullmatch(r'bbc_([a-z0-9]{8})',str(p.get('id','')))
            if match and (force or time.time()-self.cache.get(match[1],{}).get('checked_at',0)>6*3600):keys.add(match[1])
        changed=0
        with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
            futures={pool.submit(self.fetch,key):key for key in keys}
            for future in concurrent.futures.as_completed(futures):
                try:self.cache[futures[future]]=future.result();changed+=1
                except Exception:pass  # Keep last good stills on a metadata outage.
        if changed:
            from tmdb_logos import atomic
            atomic(self.path,json.dumps(self.cache).encode())
        return changed
