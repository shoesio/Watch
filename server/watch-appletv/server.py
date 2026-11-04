"""Isolated, paired tvOS API. Never sends commands to network playback endpoints."""
import argparse, asyncio, contextlib, hashlib, hmac, ipaddress, json, logging, math, os, secrets, sys, time
from pathlib import Path
from aiohttp import web

def stream_quality(width, height):
    if not (width or height): return None
    if width >= 3840 or height >= 2160: return 'UHD'
    if width >= 1280 or height >= 720: return 'HD'
    return 'SD'

class Gateway:
    def __init__(self, settings, bridge):
        self.settings, self.bridge = settings, bridge
        self.root = Path(settings['private_root']) / 'appletv'
        self.root.mkdir(mode=0o700, parents=True, exist_ok=True)
        self.jobs, self.sessions, self.tasks, self.attempts = {}, {}, set(), {}
        self.preparing = asyncio.Lock()
        from playback_features import PlaybackFeatures
        self.features=PlaybackFeatures(self.root)
        from suggestion_paging import SuggestionPages
        self.suggestion_pages=SuggestionPages()
        self.guide = bridge.watch_guide
        if hasattr(bridge,'watch'):
            from episode_versions import QualityStore
            bridge.watch.quality=QualityStore(self.root/'stream-quality.json')
            original_brands=bridge.watch.brands
            bridge.watch.brands=lambda names:original_brands(names)+([{'id':'itv','name':'ITVX','image':bridge.config['public_base']+'/static/artwork/brands/itv.png'}] if 'ITVX' in names else [])
            from discovery import Discovery
            from recommendations import Ratings
            self.discovery=Discovery(self.root,bridge.config['public_base'])
            self.discovery.catalogue_path=bridge.config['catalogue']
            from episode_artwork import EpisodeArtwork
            self.episode_artwork=EpisodeArtwork(self.root)
            from five_live_artwork import FiveLiveArtwork
            self.five_live_artwork=FiveLiveArtwork(Path(settings['private_root']),self.root)
            self.ratings=Ratings(Path(settings['private_root']),self.root)
            from related import RelatedShows
            self.related_shows=RelatedShows(Path(settings['private_root']),self.root,self.discovery)

    def read(self, name, default):
        try: return json.loads((self.root/name).read_text())
        except (OSError, ValueError): return default

    def write(self, name, value):
        path = self.root/name
        temporary = path.with_suffix('.tmp')
        temporary.write_text(json.dumps(value)); temporary.chmod(0o600); temporary.replace(path)

    def paired(self, request):
        token = request.headers.get('Authorization', '').removeprefix('Bearer ')
        return self.read('devices.json', {}).get(hashlib.sha256(token.encode()).hexdigest()) if len(token) >= 32 else None

    async def pair(self, request):
        now = time.time(); attempts = self.attempts.setdefault(request.remote, [])
        attempts[:] = [t for t in attempts if now-t < 60]
        if len(attempts) >= 5: return web.json_response({'error':'Please wait a minute before trying again.'}, status=429)
        attempts.append(now)
        data = await request.json(); code = str(data.get('code', ''))
        record = self.read('pairing.json', {})
        if record.get('expires', 0) < now or not hmac.compare_digest(record.get('hash', ''), hashlib.sha256(code.encode()).hexdigest()):
            return web.json_response({'error':'That pairing code has expired or is incorrect.'}, status=401)
        self.write('pairing.json', {})
        token = secrets.token_urlsafe(40); device = secrets.token_urlsafe(12)
        devices = self.read('devices.json', {}); devices[hashlib.sha256(token.encode()).hexdigest()] = device
        self.write('devices.json', devices)
        return web.json_response({'token':token})

    def project(self):
        self.bridge.reload_catalogue()
        guide = {}
        for channel in ('bbcone','bbctwo','bbcfour','bbcnews','C4','E4','M4','F4','4S'):
            value = self.guide.get(channel)
            if value: guide[channel] = value
        from live_descriptions import current
        for key,value in self.read('live-bbc-descriptions.json',{}).items():
            fresh=current(value,time.time())
            if fresh.get('now'):guide[key]=fresh
        catalogue=dict(self.bridge.catalogue)
        catalogue['programmes']=[*catalogue['programmes'],*self.read('five-live.json',[]),*self.read('itv-live.json',[])]
        for p in self.read('itv-live.json',[]):guide[p['live_channel']]=p.get('_guide',{})
        for p in self.read('five-live.json',[]):
            guide[p['live_channel']]=p.get('_guide',{})
            from live_descriptions import five_synopsis
            five_synopsis(guide[p['live_channel']],self.discovery.five)
            self.five_live_artwork.enrich(guide[p['live_channel']],self.discovery.five)
        original={p['id']:p for p in catalogue['programmes']}
        for p in self.read('bbc-uhd-programmes.json',[]):
            if p['id'] not in original:original[p['id']]=p
        saved=[p for rows in self.read('favourite-programmes.json',{}).values() for p in rows]
        for value in list(self.discovery.imported.values())+ [{'programme':p} for p in saved]:
            p=value['programme']
            if p['id'] not in original:original[p['id']]=p
        catalogue['programmes']=list(original.values())
        self.bridge.catalogue=catalogue
        self.bridge.episodes={e['id']:e for p in catalogue['programmes'] for e in p['episodes']}
        programmes = self.ratings.enrich(self.bridge.watch.project(catalogue, guide))
        programmes = self.episode_artwork.enrich(programmes,self.bridge.watch)
        from bbc_uhd_catalogue import enrich as enrich_uhd
        enrich_uhd(programmes,self.read('bbc-uhd-catalogue.json',{}),getattr(self.bridge.watch,'index',{}))
        favourites=self.read('favourites.json',{})
        favourite_dates=self.read('favourite-updated.json',{})
        for programme in programmes:
            programme['provider_favourite']=bool(programme.get('favourite'))
            if programme['id'] in favourites:programme['favourite']=favourites[programme['id']]
            programme['favourite_at']=favourite_dates.get(programme['id'],0)
            for episode in programme['episodes']:
                if episode.get('season') is not None: episode['season'] = str(episode['season'])
        from recommendations import ranked_films
        film_order={p['id']:i for i,p in enumerate(ranked_films(programmes))}
        for p in programmes:
            if p['id'] in film_order:p['film_rank']=film_order[p['id']]
        from channel_logos import apply_channel_logos
        apply_channel_logos(programmes,self.bridge.config['public_base'])
        itv_logos={p['live_channel']:p.get('_channel_logo') for p in self.read('itv-live.json',[])}
        for p in programmes:
            if p.get('live_channel') in itv_logos:p['channel_logo']=itv_logos[p['live_channel']]
        order={'itv':3,'itv2':15,'itv3':16,'itv4':17,'itvbe':18,'bbcone':1,'bbctwo':2,'C4':4,'C5':5,'bbcfour':9,'bbcnews':10,'E4':11,'M4':12,'F4':13,'4S':14,'C7':20,'C6':21,'C0':22,'C8':23}
        programmes.sort(key=lambda p:(p.get('live',False),order.get(p.get('live_channel'),100) if p.get('live') else 0,p['title'].casefold()))
        # Do not reuse a Samsung's measured rendition when comparing tvOS sources.
        self.bridge.watch.quality.records=self.read('stream-quality.json',{})
        from live_availability import on_air_channels
        return on_air_channels(programmes,time.time())

    def bind_source_key(self,meta,source):
        from playback_features import source_key
        version=getattr(getattr(self.bridge,'watch',None),'index',{}).get(meta.get('id'),{})
        for candidate,provider in version.get('sources',[]):
            if candidate.get('id')==source.get('id'):
                meta['source_key']=source_key(candidate,provider);break

    async def playback_capabilities(self,request):
        return web.json_response({'schema_version':1,'chapters':True,'skip_markers':['intro','recap'],
            'series_queue':True,'marker_timebase':'episode','autoplay_owner':'client','preload_supported':False})

    def public_episode(self,rows,ident):
        from playback_features import episode_row
        for p in rows:
            for e in p.get('episodes',[]):
                if e['id']==ident:return episode_row(p,e)
        return None

    async def playback_features(self,request):
        ident=request.query.get('episode_id');version_id=request.query.get('version_id')
        if version_id is not None and not __import__('re').fullmatch('[A-Za-z0-9_-]{1,100}',version_id):raise web.HTTPBadRequest()
        self.project();version=self.bridge.watch.index.get(ident)
        if not version:raise web.HTTPNotFound()
        source,provider=self.bridge.watch.quality.preferred(version)
        prepared=None
        if request.query.get('ticket'):
            session=self.sessions.get(request.query['ticket'])
            if not session or session['device']!=self.paired(request) or session['prepared'].get('_watch_meta',{}).get('id')!=ident:raise web.HTTPNotFound()
            prepared=session['prepared']
            actual=prepared.get('episode')
            if actual:
                pair=next(((s,p) for s,p in version.get('sources',[]) if s.get('id')==actual.get('id')),None)
                if pair:source,provider=pair
                else:prepared=None  # Cannot bind these timings to the selected edition.
            else:prepared=None
        from playback_features import source_key
        expected=request.query.get('source_key')
        if expected and expected!=source_key(source,provider):raise web.HTTPConflict(reason='Playback source changed; refresh features')
        result=await asyncio.to_thread(self.features.get,source,provider,version_id,prepared)
        return web.json_response({'episode_id':ident,**result},headers={'Cache-Control':'no-store'})

    async def up_next(self,request):
        ident=request.query.get('episode_id');rows=self.project()
        if not self.public_episode(rows,ident):raise web.HTTPNotFound()
        try:limit=int(request.query.get('limit','20'))
        except ValueError:raise web.HTTPBadRequest()
        if not 1<=limit<=100:raise web.HTTPBadRequest()
        from playback_features import series_after
        items=series_after(rows,ident,limit)
        return web.json_response({'schema_version':1,'episode_id':ident,'items':items,'next_episode':items[0] if items else None,'order':'chronological','autoplay_owner':'client'})

    def queue_file(self,request):
        return 'series-queue-'+hashlib.sha256(self.paired(request).encode()).hexdigest()+'.json'

    def queue_view(self,record,rows):
        def present(ident):
            row=self.public_episode(rows,ident)
            return {**(row or {'id':ident}),'available':row is not None}
        ids=record.get('episode_ids',[])
        return {'schema_version':1,'revision':record.get('revision',0),'autoplay':record.get('autoplay',False),
                'current':present(ids[0]) if ids else None,'items':[present(i) for i in ids[1:]],'updated_at':record.get('updated_at'),
                'autoplay_owner':'client'}

    async def series_queue(self,request):
        name=self.queue_file(request);record=self.read(name,{})
        rows=self.project()
        if request.method=='GET':return web.json_response(self.queue_view(record,rows),headers={'Cache-Control':'no-store'})
        data=await request.json()
        if not isinstance(data,dict):raise web.HTTPBadRequest()
        record=self.read(name,{})  # Re-read after awaiting the body: concurrent requests must conflict.
        if type(data.get('expected_revision')) is not int:raise web.HTTPConflict()
        if request.method=='DELETE':ids=[];autoplay=False
        else:
            ident=data.get('episode_id');current=self.public_episode(rows,ident)
            if not current:raise web.HTTPNotFound()
            group=next(p for p in rows if p['id']==current['programme_id'])
            if group.get('live') or group.get('film'):raise web.HTTPBadRequest(reason='Series episodes only')
            if not isinstance(data.get('autoplay',False),bool):raise web.HTTPBadRequest()
            from playback_features import series_after
            ids=[ident]+[e['id'] for e in series_after(rows,ident,10000)]
            autoplay=data.get('autoplay',False)
        if data.get('expected_revision')!=record.get('revision',0):raise web.HTTPConflict(reason='Queue changed; fetch it again')
        record={'episode_ids':ids,'autoplay':autoplay,'revision':record.get('revision',0)+1,'updated_at':time.time()}
        self.write(name,record)
        return web.json_response(self.queue_view(record,rows))

    async def advance_queue(self,request):
        name=self.queue_file(request);record=self.read(name,{})
        data=await request.json()
        if not isinstance(data,dict):raise web.HTTPBadRequest()
        record=self.read(name,{})
        if type(data.get('expected_revision')) is not int:raise web.HTTPConflict()
        ids=record.get('episode_ids',[])
        if data.get('expected_revision')!=record.get('revision',0) or not ids or data.get('completed_episode_id')!=ids[0]:
            raise web.HTTPConflict(reason='Queue changed; fetch it again')
        rows=self.project();remaining=[ident for ident in ids[1:] if self.public_episode(rows,ident)]
        record.update(episode_ids=remaining,revision=record.get('revision',0)+1,updated_at=time.time())
        self.write(name,record)
        return web.json_response({**self.queue_view(record,rows),'removed_unavailable':len(ids)-1-len(remaining)})

    async def library(self, request):
        return web.json_response({'programmes': self.project(), 'updated_at':time.time()})

    async def favourite(self,request):
        data=await request.json();ident=data.get('id');value=data.get('favourite')
        if not isinstance(ident,str) or not __import__('re').fullmatch(r'[a-f0-9]{20}',ident) or not isinstance(value,bool):raise web.HTTPBadRequest()
        programme=next((p for p in self.project() if p['id']==ident and not p.get('live')),None)
        if not programme:raise web.HTTPNotFound()
        favourites=self.read('favourites.json',{});favourites[ident]=value
        self.write('favourites.json',favourites)
        updated=self.read('favourite-updated.json',{});updated[ident]=time.time() if value else 0
        self.write('favourite-updated.json',updated)
        saved=self.read('favourite-programmes.json',{})
        if value:
            sources=set()
            for episode in programme.get('episodes',[]):
                version=getattr(self.bridge.watch,'index',{}).get(episode['id'],{})
                sources.update(e['id'] for e,_ in version.get('sources',[]))
            saved[ident]=[p for p in self.bridge.catalogue['programmes'] if any(e['id'] in sources for e in p['episodes'])]
        else:saved.pop(ident,None)
        self.write('favourite-programmes.json',saved)
        return web.json_response({'programmes':self.project()})

    async def search(self,request):
        query=request.query.get('q','')
        if len(query)>100:raise web.HTTPBadRequest()
        result=await asyncio.to_thread(self.discovery.search,query)
        return web.json_response(result)

    async def discover(self,request):
        from recommendations import recommend,featured_films,featured_shows
        if request.query.get('cursor'):
            try:return web.json_response(self.suggestion_pages.read(request.query['cursor'],self.paired(request)))
            except ValueError:return web.json_response({'error':'Suggestions expired. Choose this genre again to refresh.'},status=410)
        library=self.project()
        genre=request.query.get('genre','').strip()
        if len(genre)>70:raise web.HTTPBadRequest()
        if genre:
            candidates=await asyncio.to_thread(self.discovery.genre_candidates,genre)
            candidates=[p for p in candidates if not p.get('film')]
            # A genre's suggestions should discover something outside the existing library.
            known={p['title'].casefold() for p in library if not p.get('discovery_ref')}
            candidates=[p for p in candidates if p['title'].casefold() not in known]
            suggestions=recommend(library,candidates,2000,genre=genre,provider_cap=None)
            return web.json_response(self.suggestion_pages.start(suggestions,self.paired(request)))
        else:
            candidates=await asyncio.to_thread(self.discovery.recommendation_candidates,library)
            suggestions=await asyncio.to_thread(recommend,library,candidates,2000,provider_cap=None)
        page=self.suggestion_pages.start(suggestions,self.paired(request))
        return web.json_response({**page,'hot':(recommend(library,self.discovery.hot,12) or self.discovery.hot[:12]),'status':self.discovery.status,'featured_films':featured_films(library),'featured_shows':featured_shows(library)})

    async def shows(self,request):
        from recommendations import recommend,personal_shows,genre_order,normal_title
        if request.query.get('cursor'):
            try:return web.json_response(self.suggestion_pages.read(request.query['cursor'],self.paired(request)))
            except ValueError:return web.json_response({'error':'Shows expired. Choose the genre again to refresh.'},status=410)
        genre=request.query.get('genre','').strip()
        if len(genre)>70:raise web.HTTPBadRequest()
        library=self.project()
        personal=personal_shows(library,genre=genre or None,limit=16)
        candidates=await asyncio.to_thread(self.discovery.genre_candidates,genre) if genre else await asyncio.to_thread(self.discovery.recommendation_candidates,library)
        exclude={normal_title(p['title']) for p in personal}
        candidates=[p for p in candidates+library if not p.get('film') and normal_title(p['title']) not in exclude]
        rows=await asyncio.to_thread(recommend,library,candidates,3000,genre=genre or None,provider_cap=None,include_known=True,include_unmatched=True)
        page=self.suggestion_pages.start(rows,self.paired(request))
        return web.json_response({**page,'personal':personal,'genres':genre_order(library)})

    async def related(self,request):
        cursor=request.query.get('cursor')
        if cursor:
            try:return web.json_response(self.suggestion_pages.read(cursor,self.paired(request)))
            except ValueError:return web.json_response({'error':'Related suggestions expired. Reopen this show to refresh them.'},status=410)
        ident=request.query.get('id','')
        if not __import__('re').fullmatch(r'[a-f0-9]{20}',ident):raise web.HTTPBadRequest()
        library=self.project();programme=next((p for p in library if p['id']==ident and not p.get('film') and not p.get('live')),None)
        if not programme:raise web.HTTPNotFound()
        rows=await asyncio.to_thread(self.related_shows.list,programme,library)
        return web.json_response(self.suggestion_pages.start(rows,self.paired(request)))

    async def import_discovery(self,request):
        data=await request.json();ref=data.get('ref','')
        if not isinstance(ref,str) or len(ref)>150:raise web.HTTPBadRequest()
        try:raw=await asyncio.to_thread(self.discovery.import_show,ref)
        except Exception:return web.json_response({'error':'Episode availability could not be checked. Please try this title later.'},status=422)
        programmes=self.project()
        # Resolve projected group by the raw source IDs, so cross-provider editions merge.
        raw_ids={e['id'] for e in raw['episodes']}
        for p in programmes:
            for episode in p['episodes']:
                version=self.bridge.watch.index.get(episode['id'],{})
                if any(e['id'] in raw_ids for e,_ in version.get('sources',[])):return web.json_response({'programmes':[p]})
        return web.json_response({'error':'No currently available episodes were found.'},status=422)

    async def discovery_background(self):
        while True:
            await asyncio.to_thread(self.discovery.warm)
            await asyncio.sleep(21600)

    async def uhd_catalogue_background(self):
        from bbc_uhd_catalogue import refresh,refresh_discovery
        while True:
            try:
                self.project()
                await asyncio.to_thread(refresh_discovery,self.root)
                self.project()
                await asyncio.to_thread(refresh,self.bridge.catalogue,self.root/'bbc-uhd-catalogue.json')
            except Exception:pass
            await asyncio.sleep(900)

    async def rating_background(self):
        while True:
            try:
                imported=[row['programme'] for row in list(self.discovery.imported.values())]
                if imported:
                    from tmdb_logos import sync
                    await asyncio.to_thread(sync,self.root.parent,imported)
                await asyncio.to_thread(self.ratings.refresh,self.project())
            except Exception:pass
            await asyncio.sleep(120)

    async def episode_artwork_background(self):
        while True:
            try:
                self.project()
                await asyncio.to_thread(self.episode_artwork.refresh,self.bridge.catalogue)
            except Exception:pass
            await asyncio.sleep(300)

    async def itv_live_background(self):
        from itv_catalogue import live
        while True:
            try:self.write('itv-live.json',await asyncio.to_thread(live))
            except Exception:pass
            await asyncio.sleep(120)

    async def live_description_background(self):
        from live_descriptions import fetch_bbc
        while True:
            try:
                rows=await asyncio.to_thread(fetch_bbc)
                if rows:self.write('live-bbc-descriptions.json',{**self.read('live-bbc-descriptions.json',{}),**rows})
            except Exception:pass
            await asyncio.sleep(300)

    async def five_live_background(self):
        from native_playback import refresh_five
        while True:
            try:
                channels=await asyncio.to_thread(refresh_five)
                self.write('five-live.json',channels)
                await asyncio.to_thread(self.five_live_artwork.refresh,channels,self.discovery)
            except Exception:pass  # Retain the previous public listings on refresh failure.
            await asyncio.sleep(300)

    async def prepare(self, request):
        data = await request.json(); ident = data.get('episode_id'); self.project()
        if ident not in self.bridge.watch.index: raise web.HTTPBadRequest()
        position = float(data.get('position', 0))
        if not math.isfinite(position) or not 0 <= position <= 86400: raise web.HTTPBadRequest()
        if len(self.jobs) >= 8: return web.json_response({'error':'Too many requests. Close the player and try again.'}, status=429)
        job = secrets.token_urlsafe(24); device = self.paired(request)
        self.jobs[job] = {'state':'preparing', '_device':device, '_created':time.time()}
        self.write('request-status.json', {'state':'preparing','episode':ident,'position':position,'updated_at':time.time()})
        task = asyncio.create_task(self.worker(job, ident, position, device, native=data.get('native_playback') is True, prefer_direct=data.get('prefer_direct') is not False, channel4_live=data.get('native_channel4_live') is True)); self.tasks.add(task); task.add_done_callback(self.tasks.discard)
        return web.json_response({'job':job}, status=202)

    async def worker(self, job, ident, position, device, native=False, prefer_direct=True, channel4_live=False):
        stream = None; ticket = None
        try:
            async with self.preparing:
                if job not in self.jobs: return
                if native:
                    from native_playback import descriptor,bbc_direct
                    choice=descriptor(self.bridge,ident,channel4_live=channel4_live)
                    if choice:
                        episode,route,meta=choice;url=None
                        self.bind_source_key(meta,episode)
                        from live_playback_metadata import apply_live_metadata
                        apply_live_metadata(meta,getattr(getattr(self.bridge,'watch',None),'groups',[]),ident)
                        if route['provider']=='bbc' and prefer_direct:
                            try:
                                url=await asyncio.to_thread(bbc_direct,self.bridge,episode)
                                if getattr(url,'version_id',None):meta['version_id']=url.version_id
                            except Exception:pass  # Resolve/compatibility failure falls back to the relay.
                        if route['provider'] in ('channel5','u','itv','channel4') or url:
                            if job not in self.jobs:return
                            ticket=secrets.token_urlsafe(32)
                            for old,value in list(self.sessions.items()):
                                if value['device']==device:await self.release(old)
                            self.sessions[ticket]={'device':device,'prepared':{'_watch_meta':meta,'native':True,'delivery':'native-'+route['provider']},'stream':None,'seen':time.time()}
                            self.jobs[job].update(state='ready',ticket=ticket,url=url,native=route,metadata=meta,initial_seek=0 if route['live'] else position)
                            self.write('request-status.json',{'state':'ready','episode':ident,'delivery':'native-'+route['provider'],'updated_at':time.time()})
                            return
                prepared, episode = await asyncio.to_thread(self.bridge.watch.choose, self.bridge, ident, position, None)
                if job not in self.jobs: return
                ticket = secrets.token_urlsafe(32)
                meta = prepared['_watch_meta']
                self.bind_source_key(meta,episode)
                from live_playback_metadata import apply_live_metadata
                apply_live_metadata(meta,getattr(getattr(self.bridge,'watch',None),'groups',[]),ident) if meta.get('live') else None
                video = next((s for s in prepared.get('info',{}).get('streams',[]) if s.get('codec_type') == 'video'), {})
                width, height = int(video.get('width') or 0), int(video.get('height') or 0)
                meta.update(stream_width=width, stream_height=height)
                meta['quality'] = stream_quality(width,height) or meta.get('quality')
                if prepared['live']:
                    if prepared.get('provider'): source = await asyncio.to_thread(self.bridge.provider.open, prepared['resolved'])
                    else:
                        _, source_stream = await asyncio.to_thread(self.bridge.session_stream, episode)
                        source = await asyncio.to_thread(source_stream.open)
                    from tvos_stream import TVStream
                    # Keep the proven timestamp-preserving codec-copy packager. Native AVPlayer
                    # manages stalls; arbitrary VOD jumps reopen at the requested absolute offset.
                    stream = TVStream(self.root/'streams'/ticket, source,allow_short=not meta.get('live'),live=bool(meta.get('live')))
                    await stream.ready()
                    url = self.settings['public_base']+'/stream/'+ticket+'/index.m3u8'
                else:
                    url = self.settings['public_base']+'/stream/'+ticket+'/video.mp4'
                    meta['start_position'] = 0
                if job not in self.jobs:
                    if stream: await stream.close()
                    return
                # Supersede only this app's own session, never another device's playback.
                for old, value in list(self.sessions.items()):
                    if value['device'] == device: await self.release(old)
                self.sessions[ticket] = {'device':device,'prepared':prepared,'stream':stream,'seen':time.time()}
                self.jobs[job].update(state='ready', ticket=ticket, url=url, metadata=meta, initial_seek=position if not prepared['live'] else 0)
                self.write('request-status.json', {'state':'ready','episode':ident,'quality':meta.get('quality'),'updated_at':time.time()})
        except Exception:
            if stream: await stream.close()
            self.write('request-status.json', {'state':'failed','episode':ident,'updated_at':time.time()})
            if job in self.jobs: self.jobs[job].update(state='failed', error='This source could not be prepared. Check provider sign-in or try another episode.')

    async def poll(self, request):
        job = self.jobs.get(request.match_info['job'])
        if not job or job['_device'] != self.paired(request): raise web.HTTPNotFound()
        result={k:v for k,v in job.items() if not k.startswith('_')}
        if result.get('state')=='ready' and result.get('metadata'):
            from urllib.parse import quote
            meta=dict(result['metadata']);ident=quote(meta['id'],safe='')
            meta.update(features_url='/playback/features?episode_id='+ident,up_next_url='/playback/up-next?episode_id='+ident)
            result['metadata']=meta
        return web.json_response(result)

    async def cancel(self, request):
        job = self.jobs.get(request.match_info['job'])
        if job and job['_device'] == self.paired(request):
            self.jobs.pop(request.match_info['job'], None)
            if job.get('ticket'): await self.release(job['ticket'])
        return web.Response(status=204)

    async def release(self, ticket):
        value = self.sessions.pop(ticket, None)
        if value and value['stream']: await value['stream'].close()

    async def session(self, request):
        ticket = request.match_info['ticket']; value = self.sessions.get(ticket)
        if not value or value['device'] != self.paired(request): raise web.HTTPNotFound()
        if request.method == 'DELETE':
            await self.release(ticket); return web.Response(status=204)
        data = await request.json(); position = float(data.get('position', 0)); meta = value['prepared']['_watch_meta']
        if not math.isfinite(position) or not 0 <= position <= 86400: raise web.HTTPBadRequest()
        if not meta.get('live'): self.bridge.watch.progress.save(meta['id'], position, meta.get('duration_seconds',0), data.get('completed') is True)
        value['seen'] = time.time()
        state = data.get('state')
        if state in ('playing','paused','buffering'):
            snapshot = value['stream'].snapshot() if value['stream'] and hasattr(value['stream'],'snapshot') else {}
            metrics = data.get('metrics',{})
            safe_metrics = {k:v for k,v in metrics.items() if k in ('buffer_seconds','stalls','retries','video_width','video_height') and isinstance(v,(int,float)) and math.isfinite(v)} if isinstance(metrics,dict) else {}
            if value['prepared'].get('native'):
                width,height=safe_metrics.get('video_width',0),safe_metrics.get('video_height',0)
                if width and height:meta['quality']=stream_quality(width,height)
            self.write('playback-status.json', {'delivery':value['prepared'].get('delivery','pi-relay'),'state':state,'episode':meta['id'],'position':position,'quality':meta.get('quality'),'relay':snapshot,'player':safe_metrics,'updated_at':time.time()})
        return web.json_response({'ok':True})

    async def media(self, request):
        value = self.sessions.get(request.match_info['ticket'])
        if not value: raise web.HTTPNotFound()
        value['seen'] = time.time(); name = request.match_info['name']; stream = value['stream']
        if stream:
            import re
            if not re.fullmatch(r'index\.m3u8|segment\d{6}\.ts', name) or stream.closed: raise web.HTTPNotFound()
            path = stream.directory/name
            if not path.is_file(): raise web.HTTPNotFound()
            if name=='index.m3u8' and not stream.live:
                return web.Response(text=stream.playlist(),content_type='application/vnd.apple.mpegurl',headers={'Cache-Control':'no-store'})
            return web.FileResponse(path, headers={'Content-Type':'application/vnd.apple.mpegurl' if name.endswith('m3u8') else 'video/mp2t','Cache-Control':'no-store'})
        if value['prepared'].get('native') or name != 'video.mp4': raise web.HTTPNotFound()
        return web.FileResponse(value['prepared']['path'], headers={'Content-Type':'video/mp4'})

    async def maintenance(self):
        while True:
            await asyncio.sleep(15)
            now = time.time()
            for ticket, value in list(self.sessions.items()):
                if now-value['seen'] > 120: await self.release(ticket)
            for job, value in list(self.jobs.items()):
                if now-value['_created'] > 300: self.jobs.pop(job, None)

    async def start(self, app):
        self.background = [asyncio.create_task(self.guide.run()), asyncio.create_task(self.maintenance())]
        if hasattr(self,'discovery'):
            self.background.extend([asyncio.create_task(self.discovery_background()),asyncio.create_task(self.uhd_catalogue_background()),asyncio.create_task(self.rating_background()),asyncio.create_task(self.five_live_background()),asyncio.create_task(self.episode_artwork_background()),asyncio.create_task(self.live_description_background()),asyncio.create_task(self.itv_live_background())])

    async def stop(self, app):
        for job in list(self.jobs): self.jobs.pop(job, None)
        for task in self.background: task.cancel()
        # Let threaded provider preparation finish before closing resources.
        for task in self.tasks: task.cancel()
        await asyncio.gather(*self.background, *self.tasks, return_exceptions=True)
        for ticket in list(self.sessions): await self.release(ticket)

    def app(self):
        @web.middleware
        async def auth(request, handler):
            try:
                if not ipaddress.ip_address(request.remote).is_private: raise web.HTTPForbidden()
                if request.path not in ('/pair','/health') and not request.path.startswith('/stream/') and not self.paired(request):
                    return web.json_response({'error':'Pair this Apple TV to continue.'}, status=401)
                return await handler(request)
            except (ValueError, TypeError): return web.json_response({'error':'Invalid request.'}, status=400)
        app = web.Application(middlewares=[auth], client_max_size=4096)
        app.router.add_get('/health', lambda r:web.json_response({'ok':True,'version':'1.0'}))
        app.router.add_post('/pair', self.pair)
        app.router.add_get('/library', self.library)
        app.router.add_get('/playback/capabilities',self.playback_capabilities)
        app.router.add_get('/playback/features',self.playback_features)
        app.router.add_get('/playback/up-next',self.up_next)
        app.router.add_get('/playback/queue',self.series_queue)
        app.router.add_post('/playback/queue',self.series_queue)
        app.router.add_delete('/playback/queue',self.series_queue)
        app.router.add_post('/playback/queue/advance',self.advance_queue)
        app.router.add_post('/favourites',self.favourite)
        app.router.add_get('/search',self.search)
        app.router.add_get('/discover',self.discover)
        app.router.add_get('/shows',self.shows)
        app.router.add_get('/related',self.related)
        app.router.add_post('/discover/import',self.import_discovery)
        app.router.add_post('/prepare', self.prepare)
        app.router.add_get('/prepare/{job}', self.poll)
        app.router.add_delete('/prepare/{job}', self.cancel)
        app.router.add_post('/session/{ticket}', self.session)
        app.router.add_delete('/session/{ticket}', self.session)
        app.router.add_get('/stream/{ticket}/{name}', self.media)
        app.on_startup.append(self.start); app.on_cleanup.append(self.stop)
        return app

def main():
    parser=argparse.ArgumentParser(); parser.add_argument('--config',required=True); args=parser.parse_args()
    settings=json.loads(Path(args.config).read_text()); sys.path.insert(0,settings['bridge_root']); os.chdir(settings['bridge_root'])
    from bridge import Bridge
    config=json.loads(Path(settings['bridge_config']).read_text())
    # Assets remain on the established public image server; the new service owns only its streams.
    from quality_policy import configure_bridge
    bridge=configure_bridge(Bridge)(config)
    logging.basicConfig(level=logging.CRITICAL)
    gateway=Gateway(settings,bridge)
    web.run_app(gateway.app(),host=settings['bind'],port=settings['port'],access_log=None,shutdown_timeout=10)

if __name__=='__main__': main()
