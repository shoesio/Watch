"""Available provider film catalogues, independent of personal favourites."""
import json
import re
import time
from pathlib import Path
import requests


def film_selections(root):
    path=Path(root)/'film-selections.json'
    try:
        cached=json.loads(path.read_text())
        if time.time()-cached['updated_at']<21600:return cached
    except (OSError,ValueError,KeyError):cached={}
    result={'updated_at':time.time(),'bbc':[],'channel4':[]}
    with requests.Session() as session:
        for page in range(1,10):
            r=session.get('https://ibl.api.bbc.co.uk/ibl/v1/categories/films/programmes',params={'per_page':200,'page':page},timeout=25);r.raise_for_status()
            data=r.json()['category_programmes'];result['bbc'].extend(data.get('elements',[]))
            if page*200>=data['count']:break
        offset=0
        while offset<2000:
            r=session.get('https://www.channel4.com/categories/film',params={'sort':'az','offset':offset},timeout=25);r.raise_for_status()
            match=re.search(r'window\.__PARAMS__\s*=\s*\{\s*"initialData":',r.text)
            if not match:raise RuntimeError('Channel 4 film catalogue format changed.')
            data=json.JSONDecoder().raw_decode(r.text[match.end():])[0]
            added=0
            for item in data.get('brands',{}).get('items',[]):
                slug=item.get('websafeTitle')
                if slug and slug not in result['channel4']:
                    result['channel4'].append(slug);added+=1
            if not added or len(result['channel4'])>=data.get('noOfShows',0):break
            offset+=60
    temporary=path.with_suffix('.tmp');temporary.write_text(json.dumps(result));temporary.chmod(0o600);temporary.replace(path)
    return result


def bbc_films(sync, elements):
    result=[]
    for programme in elements:
        episodes=[]
        pid='bbc_'+programme['id']
        for ep in programme.get('initial_children',[]):
            if ep.get('status')!='available' or ep.get('signed'):continue
            versions=ep.get('versions',[])
            version=next((v for v in versions if v.get('kind') in ('editorial','original')), next(iter(versions),{}))
            duration=version.get('duration',{})
            episodes.append({'id':pid+'_'+ep['id'],'title':ep.get('subtitle') or ep.get('title',programme['title']),'season':'Film','episode_number':0,'description':ep.get('synopses',{}).get('medium',''),'thumbnail':sync.pic(ep.get('images'),'640x360'),'duration_seconds':duration.get('value') or duration.get('seconds') or 0,'duration_label':duration.get('text',''),'kind':'plugin','url':'https://www.bbc.co.uk/iplayer/episode/'+ep['id'],'quality':'720p50,720p_hls,540p,396p','delivery':'relay','preserve_timestamps':True,'live':False})
        if not episodes:continue
        result.append({'id':pid,'title':programme['title'],'provider':'BBC iPlayer','provider_id':'bbc','media_type':'movie','genre':programme.get('labels',{}).get('category','Films'),'favourite':False,'recent':False,'description':programme.get('synopses',{}).get('medium',''),'artwork':sync.pic(programme.get('images')),'hero':sync.pic(programme.get('images')),'episodes':episodes})
    return result
