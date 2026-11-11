"""Paged cinematic shelves for Samsung. Only public cached metadata; never video preparation."""
import hashlib,re,secrets,time
from pathlib import Path
from datetime import datetime
from aiohttp import web
from library_browse import genres
from episode_versions import seconds


def title_key(p):return re.sub(r'[^\w]+',' ',str(p.get('title','')).casefold().replace('’',"'")).strip()

def shelves_for(library,pool,section,genre='',hot=()):
    films=section=='films';known=[p for p in library if not p.get('live') and bool(p.get('film'))==films]
    eligible=[p for p in pool if not p.get('live') and bool(p.get('film'))==films]
    # Prefer the existing imported/favourite version over a discovery preview.
    merged={title_key(p):p for p in eligible}
    merged.update({title_key(p):p for p in reversed(known)})
    eligible=list(merged.values())
    if genre:eligible=[p for p in eligible if genre in p.get('genres',[])];known=[p for p in known if genre in p.get('genres',[])]
    rows=[];used=set()
    def add(ident,title,items,layout=None,all_items=False):
        unique=[];seen=set()
        for p in items:
            key=p.get('home_episode') or p.get('selected_episode_id') or p.get('id')
            if key and key not in seen:seen.add(key);unique.append(p)
        if not unique:return
        if layout is None:
            posters=[p for p in unique if p.get('poster')]
            if len(posters)>=4:unique=posters;layout='portrait'
            else:layout='landscape'
        rows.append({'id':ident,'title':title,'layout':layout,'items':unique if all_items else unique[:24]})
        used.update(p['id'] for p in rows[-1]['items'])
    def continuing(p):
        ep=next((e for e in p.get('episodes',[]) if e['id']==p.get('resume_episode')),None)
        if not ep:return None
        return dict(p,home_episode=ep['id'],episode_id=ep['id'],image=ep.get('thumbnail') or p.get('image'),progress=ep.get('progress',0),caption=' • '.join(x for x in [str(ep.get('season') or ''),('Episode '+str(ep['episode_number'])) if ep.get('episode_number') else '',str(round(seconds(ep.get('duration_seconds'))/60))+' Min' if seconds(ep.get('duration_seconds')) else ''] if x),updated_at=ep.get('updated_at',0))
    continued=[row for p in known if (row:=continuing(p))]
    continued.sort(key=lambda p:p.get('updated_at',0),reverse=True)
    if section=='home':
        from recommendations import home_shows
        add('continue','Continue Watching',continued,'continuing',True)
        add('new','New episodes to watch',home_shows(known),'continuing',True)
        add('personal','Picked for you',eligible[:48])
        add('favourites','Your favourites',[p for p in known if p.get('favourite')],all_items=True)
        add('spotlight','In the spotlight',[p for p in hot if not p.get('film') and not p.get('live')])
    else:
        add('continue','Continue Watching',continued,'continuing',True)
        add('personal','Picked for tonight' if films else 'Your next great watch',eligible[:40])
        add('favourites','Your favourites',[p for p in known if p.get('favourite')],all_items=True)
    # Explicit named episodes, not guessed seasonal programmes or season restrictions.
    if not films and datetime.now().month in (11,12,1):
        festive=[]
        for p in known:
            for e in p.get('episodes',[]):
                if re.search(r'\b(christmas|xmas|yuletide|festive (special|edition))\b',str(e.get('title',''))+' '+str(e.get('description','')),re.I):
                    festive.append(dict(p,home_episode=e['id'],episode_id=e['id'],image=e.get('thumbnail') or p.get('image'),caption=e.get('title'),description=e.get('description') or p.get('description')))
        add('christmas','Christmas Specials',festive,'continuing')
    themes=[('Comedy','Comedy favourites'),('Documentaries','Real lives. Remarkable stories.'),('Crime & thriller','Crime & mystery'),('Drama','Get lost in a great drama'),('Food & lifestyle','Food & good living')]
    for category,title in themes:
        if genre and category!=genre:continue
        group=[p for p in eligible if category in p.get('genres',[])]
        if len(group)>=4:add('genre-'+category,title,group)
    for brand,title in [('bbc','Best of iPlayer'),('channel4','Channel 4 discoveries'),('u','Worth your time on U'),('itv','Discover ITVX'),('channel5','Discover 5')]:
        group=[p for p in eligible if any(b.get('id')==brand for b in p.get('brands',[]))]
        if len(group)>=4:add('provider-'+brand,title,group)
    # No title is lost because it didn't match a theme or lack portrait artwork.
    remaining=[p for p in eligible if p['id'] not in used]
    add('all','More films to explore' if films else 'More shows to discover',remaining,'landscape',True)
    if section=='home':add('live','Live now',[p for p in library if p.get('live')],'live',True)
    return rows

class CinemaAdapter:
    def cinema_present(self,p):
        row=self.discovery_card(p)
        ident=hashlib.sha256(title_key(row).encode()).hexdigest()[:20]
        for kind,url in self.matched_artwork.get(ident,row.get('film')).items():
            if url:row[kind]=self.art_id(url)
        return row

    async def cinema(self,request):
        section=request.query.get('section','home');genre=request.query.get('genre','')[:70]
        if section not in ('home','shows','films'):raise web.HTTPBadRequest()
        # Reuse metadata work across sections until progress/catalogue/preferences
        # change. Calls still refresh the screen; moving focus never rebuilds it.
        paths=[self.progress.path,self.matched_artwork.path,self.discovery_root/'favourites.json',self.discovery_root/'discovery-library.json',Path(self.discovery.catalogue_path)]
        stamp=tuple(p.stat().st_mtime_ns if p.exists() else 0 for p in paths)
        cached_core=getattr(self,'cinema_core',None)
        from recommendations import featured_shows,featured_films,genre_order
        if cached_core and cached_core['stamp']==stamp and time.time()-cached_core['created']<30:
            library,pool=cached_core['library'],cached_core['pool']
        else:
            library=self.suggestion_library()
            cached=list(self.discovery.c4)+list(self.discovery.five)+list(self.discovery.itv)+list(self.discovery.suggestions)
            for key,value in list(self.discovery.cache.items()):
                if key.startswith(('genre:','recommendation-pool:')) and isinstance(value,tuple) and isinstance(value[1],list):cached+=value[1]
            from recommendations import recommend
            discovered=recommend(library,library+cached,3000,include_known=True,include_unmatched=True,provider_cap=None)
            pool=[self.cinema_present(p) for p in discovered]
            library=[dict(self.cinema_present(p),episodes=p.get('episodes',[])) for p in library]
            self.cinema_core={'stamp':stamp,'created':time.time(),'library':library,'pool':pool}
        rows=shelves_for(library,pool,section,genre,[self.cinema_present(p) for p in self.discovery.hot])
        for row in rows:row['items']=[self.public(p) for p in row['items']]
        featured=featured_films(library) if section=='films' else featured_shows(library)
        token=secrets.token_urlsafe(16);now=time.time()
        self.cinema_snapshots={k:v for k,v in getattr(self,'cinema_snapshots',{}).items() if now-v['created']<1800}
        if len(self.cinema_snapshots)>=6:self.cinema_snapshots.pop(next(iter(self.cinema_snapshots)))
        self.cinema_snapshots[token]={'created':now,'rows':rows}
        return web.json_response({'snapshot':token,'section':section,'heroes':[self.public(p) for p in featured[:6]],'genres':genre_order(library+pool),
            'shelves':[{'id':r['id'],'title':r['title'],'layout':r['layout'],'total':len(r['items'])} for r in rows]})

    async def cinema_shelf(self,request):
        record=getattr(self,'cinema_snapshots',{}).get(request.query.get('snapshot'))
        if not record or time.time()-record['created']>1800:raise web.HTTPGone()
        row=next((r for r in record['rows'] if r['id']==request.query.get('id')),None)
        if not row:raise web.HTTPNotFound()
        try:page=max(0,int(request.query.get('page','0')))
        except ValueError:raise web.HTTPBadRequest()
        size=5 if row['layout']=='portrait' else 4;page=min(page,max(0,(len(row['items'])-1)//size))
        return web.json_response({'id':row['id'],'layout':row['layout'],'items':row['items'][page*size:page*size+size],'page':page,'size':size,'total':len(row['items'])})
