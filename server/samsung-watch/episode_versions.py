"""Conservative episode equivalence and measured source quality; never stores stream URLs."""
import hashlib
import json
import re
import time
from pathlib import Path
from fractions import Fraction
from tmdb_logos import atomic


def seconds(value):
    try:return max(0,float(value or 0))
    except (TypeError,ValueError):
        match=re.fullmatch(r'PT(?:(\d+(?:\.\d+)?)H)?(?:(\d+(?:\.\d+)?)M)?(?:(\d+(?:\.\d+)?)S)?',str(value or ''))
        return sum(float(v or 0)*unit for v,unit in zip(match.groups(),(3600,60,1))) if match else 0


def signature(episode):
    season=str(episode.get('season','')).strip().casefold()
    match=re.fullmatch(r'(?:series\s*|season\s*)?(\d+)',season)
    try:number=int(episode.get('episode_number') or 0)
    except (TypeError,ValueError):number=0
    if match and number>0:
        return '%d:%d' % (int(match[1]),number)
    return None


def versions(group_id,pairs):
    buckets={};result=[]
    for episode,provider in pairs:
        key=signature(episode)
        if key is None:result.append({'id':episode['id'],'sources':[(episode,provider)]});continue
        buckets.setdefault(key,[]).append((episode,provider))
    for key,sources in buckets.items():
        # No speculative title matching for specials, XL/Bleeped editions, or unknown numbering.
        if len({provider for _,provider in sources})<2:
            result.extend({'id':episode['id'],'sources':[(episode,provider)]} for episode,provider in sources)
        else:
            ident='version_'+hashlib.sha256((group_id+':'+key).encode()).hexdigest()[:20]
            result.append({'id':ident,'sources':sources})
    return result


def measurements(info):
    video=next((s for s in info.get('streams',[]) if s.get('codec_type')=='video'),{})
    fps=0
    for value in (video.get('avg_frame_rate'),video.get('r_frame_rate')):
        try:fps=float(Fraction(value or '0'))
        except (ValueError,ZeroDivisionError):continue
        if fps:break
    return {'height':int(video.get('height') or 0),'width':int(video.get('width') or 0),
            'fps':round(fps,3),'bitrate':int(video.get('bit_rate') or info.get('format',{}).get('bit_rate') or 0),'checked_at':time.time()}

class QualityStore:
    def __init__(self,path):
        self.path=Path(path)
        try:self.records=json.loads(self.path.read_text())
        except (OSError,ValueError):self.records={}

    def record(self,ident,info):
        self.records[ident]=measurements(info)
        atomic(self.path,json.dumps(self.records).encode())

    def invalidate(self,ident):
        self.records.pop(ident,None)
        atomic(self.path,json.dumps(self.records).encode())

    def fresh(self,ident):
        return time.time()-self.records.get(ident,{}).get('checked_at',0)<86400

    def rank(self,source):
        episode,provider=source
        spec=self.records.get(episode['id'],{})
        # Actual compatible resolution, then motion, then bitrate. Provider only breaks ties.
        return (spec.get('height',0),spec.get('width',0),spec.get('fps',0),spec.get('bitrate',0),provider=='BBC iPlayer')

    def preferred(self,version):
        return max(version['sources'],key=self.rank)
