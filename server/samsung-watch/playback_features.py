"""Provider-timed playback extras and chronological series queues, independent of clients.
No media/key processing and no preparation/preloading as a side effect.
"""
import hashlib,math,re,time
from pathlib import Path
import requests

SCHEMA=1

def seconds(value):
    if isinstance(value,bool):return None
    try:value=float(value)
    except (TypeError,ValueError):return None
    return value if math.isfinite(value) and 0<=value<=86400 else None

def intervals(rows,duration=0,skip=False):
    result=[];seen=set()
    for row in rows if isinstance(rows,list) else []:
        if not isinstance(row,dict):continue
        start=seconds(row.get('start',row.get('start_time')));end=seconds(row.get('end',row.get('end_time')))
        kind=row.get('kind','chapter')
        if start is None or end is None or end<=start or (duration and end>duration+0.5):continue
        if skip and kind not in ('intro','recap'):continue
        key=(kind,start,end)
        if key in seen:continue
        seen.add(key)
        title=row.get('title') or (row.get('tags') or {}).get('title') or {'intro':'Intro','recap':'Recap'}.get(kind,'Chapter')
        result.append({'id':hashlib.sha256(str(key).encode()).hexdigest()[:16],'title':str(title)[:200],'kind':kind,'start':start,'end':end})
    return sorted(result,key=lambda r:(r['start'],r['end']))[:500]

def source_key(source,provider):
    # Exact edition/source; programme title is deliberately never a timing key.
    identity=[provider,source.get('id'),source.get('provider_episode_id'),source.get('url')]
    return hashlib.sha256(repr(identity).encode()).hexdigest()

def episode_row(group,episode):
    return {k:v for k,v in {**{k:group.get(k) for k in ('artwork','show_logo','brands')},**episode,
            'programme_id':group['id'],'show_title':group['title']}.items()
            if k in ('id','title','description','thumbnail','season','episode_number','duration_seconds','resume_seconds','progress','quality','brands','programme_id','show_title','artwork','show_logo')}

def series_after(programmes,ident,limit=20):
    group=next((p for p in programmes if any(e['id']==ident for e in p.get('episodes',[]))),None)
    if not group or group.get('live') or group.get('film'):return []
    def order(e):
        season=str(e.get('season','')).strip()
        # QI uses alphabetic series (Series W, Series X). Accept explicit
        # single-letter seasons, without interpreting named specials as seasons.
        letter=re.fullmatch(r'(?:Series\s+)?([A-Z])',season,re.IGNORECASE)
        numeric=re.fullmatch(r'(?:Series\s+)?([0-9]+)',season,re.IGNORECASE)
        season_number=ord(letter[1].upper())-ord('A')+1 if letter else int(numeric[1]) if numeric else 0
        number=e.get('episode_number')
        if season_number<=0 or isinstance(number,bool):return None
        try:number=int(number)
        except (ValueError,TypeError):return None
        return (season_number,number) if number>0 else None
    current=next(e for e in group['episodes'] if e['id']==ident);key=order(current)
    # Unnumbered specials are not guessed into the story's sequence.
    if key is None:return []
    rows=[e for e in group['episodes'] if order(e) is not None and order(e)>key]
    rows.sort(key=lambda e:(order(e),e['id']))
    return [episode_row(group,e) for e in rows[:limit]]

class PlaybackFeatures:
    def __init__(self,root):self.root=root;self.bbc_cache={}
    def bbc(self,pid):
        old=self.bbc_cache.get(pid)
        if old and time.time()-old[0]<21600:return old[1]
        response=requests.get('https://ibl.api.bbc.co.uk/ibl/v1/episodes/'+pid,timeout=(3,8),allow_redirects=False)
        response.raise_for_status()
        if len(response.content)>2000000:raise ValueError('Metadata too large')
        data=response.json();episode=next((e for e in data.get('episodes',[]) if e.get('id')==pid),{})
        self.bbc_cache[pid]=(time.time(),episode)
        if len(self.bbc_cache)>100:self.bbc_cache.pop(next(iter(self.bbc_cache)))
        return episode
    def get(self,source,provider,version_id=None,prepared=None):
        duration=seconds(source.get('duration_seconds')) or 0
        key=source_key(source,provider)
        result={'schema_version':SCHEMA,'source_key':key,'timebase':'episode','version_id':version_id,
                'chapters':[],'skip_markers':[],'credits':[],'status':'unavailable','provenance':[]}
        if source.get('live'):result['status']='not_applicable';return result
        # Existing resolver/catalogue output may already carry exact-source chapters.
        info=dict((prepared or {}).get('info',{}))
        # Read chapters from an existing local playback file only. Never launch
        # a downloader or ask ffprobe to access a remote provider URL.
        path=(prepared or {}).get('path')
        if not info.get('chapters') and isinstance(path,str) and Path(path).is_file():
            import json,subprocess
            try:
                output=subprocess.run(['ffprobe','-v','error','-show_chapters','-of','json',path],capture_output=True,timeout=8,check=True)
                if len(output.stdout)<2000000:info['chapters']=json.loads(output.stdout).get('chapters',[])
            except (OSError,ValueError,subprocess.SubprocessError):pass
        chapters=intervals(source.get('chapters') or info.get('chapters'),duration)
        markers=intervals(source.get('skip_markers'),duration,skip=True)
        credits=[c for c in intervals(source.get('credits'),duration) if c['kind'] in ('credits','end_credits')]
        if chapters or markers or credits:result['provenance'].append('source_metadata')
        # Reviewed local additions are keyed by exact source AND rendition version.
        import json
        try:reviewed=json.loads((self.root/'playback-markers.json').read_text()).get(key,{})
        except (OSError,ValueError):reviewed={}
        if reviewed.get('verified') is True and reviewed.get('version_id')==version_id:
            chapters=intervals(reviewed.get('chapters'),duration) or chapters
            markers=intervals(reviewed.get('skip_markers'),duration,skip=True) or markers
            # Credits are cues only, never skip controls. Reviewed cues also bind duration.
            if duration and seconds(reviewed.get('duration_seconds')) and abs(seconds(reviewed['duration_seconds'])-duration)<=0.5:
                credits=[c for c in intervals(reviewed.get('credits'),duration) if c['kind'] in ('credits','end_credits')] or credits
            result['provenance'].append('reviewed_metadata')
        match=re.fullmatch(r'https://www\.bbc\.co\.uk/iplayer/episode/([a-z0-9]{8})(?:[/\?#].*)?',str(source.get('url','')))
        if provider=='BBC iPlayer' and match:
            if not version_id:result['status']='version_required'
            elif re.fullmatch('[a-z0-9]{8}',version_id):
                try:
                    episode=self.bbc(match[1]);version=next((v for v in episode.get('versions',[]) if v.get('id')==version_id),None)
                    if version is None:result['status']='version_not_found'
                    else:
                        raw=[]
                        for row in version.get('interactions',[]):
                            if row.get('type')!='skip':continue
                            points=row.get('interaction_points') or {}
                            raw.append({'kind':row.get('subtype'),'start':points.get('show_from'),'end':points.get('skip_to')})
                        markers=intervals(raw,duration,skip=True) or markers
                        chapters=intervals(version.get('chapters'),duration) or chapters
                        result['provenance'].append('BBC exact version')
                except (requests.RequestException,ValueError,TypeError):result['status']='temporarily_unavailable'
        result.update(chapters=chapters,skip_markers=markers,credits=credits)
        if chapters or markers or credits:result['status']='available'
        return result
