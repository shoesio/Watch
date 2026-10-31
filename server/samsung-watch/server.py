#!/usr/bin/env python3
"""Isolated Orsay client gateway. Never launches or stops another TV/app."""
import argparse
import asyncio
import collections
import contextlib
import hashlib
import hmac
import io
import json
import logging
import math
import os
from pathlib import Path
import re
import secrets
import sys
import time
from urllib.parse import urlsplit

from aiohttp import web
import requests
from PIL import Image, ImageDraw, ImageOps
from live_guide import LiveGuide
from progress_store import ProgressStore
from tmdb_logos import sync as sync_logos, is_film
from library_browse import genres, episode_order, natural
from episode_versions import versions, QualityStore, seconds

ART_HOSTS = {'ichef.bbci.co.uk', 'ic.c4assets.com', 'uktv-res.cloudinary.com', 'api-images.channel5.com','ovp.itv.com'}
LIVE_ORDER = {'bbc one':1,'bbc two':2,'channel 4':3,'bbc four':4,'e4':5,'more4':6,'film4':7,'4seven':8,'bbc news':9}
CHANNEL_ART = {'bbc one':'bbcone','bbc two':'bbctwo','bbc four':'bbcfour','bbc news':'bbcnews',
               'channel 4':'channel4','e4':'e4','more4':'more4','film4':'film4','4seven':'4seven'}
GUIDE_KEY = {'channel4':'C4','e4':'E4','more4':'M4','film4':'F4','4seven':'4S'}

def provider_brands(names):
    mapping = {'BBC iPlayer': 'bbc', 'Channel 4': 'channel4', 'U': 'u', 'Channel 5': 'channel5', 'ITVX':'itv'}
    return [{'id': mapping[n], 'name': n} for n in names if n in mapping]

def stream_spec(info):
    video = next((s for s in info.get('streams', []) if s.get('codec_type') == 'video'), {})
    height = int(video.get('height') or 0)
    return {'quality': ('HD' if height >= 720 else 'SD') if height else None,
            'width': int(video.get('width') or 0), 'height': height}


def group_key(programme):
    # Exact title equivalence only: never conflate Bleeped, XL, or extended editions.
    title = programme['title'].casefold().replace('’', "'")
    title = re.sub(r'[^\w]+', ' ', title).strip()
    return ('live:' + programme['id']) if programme.get('live') else title


class Gateway:
    def __init__(self, settings, bridge):
        self.settings, self.bridge = settings, bridge
        self.key = Path(settings['device_key_file']).read_text().strip()
        if len(self.key) < 32:
            raise ValueError('Generate a random device key before starting.')
        self.art = {}
        self.images = collections.OrderedDict()
        self.jobs = {}
        self.current_job = None
        self.current_ticket = None
        self.worker = None
        self.janitor = None
        self.workers = set()
        self.guide = LiveGuide()
        self.guide_task = None
        self.logo_task = None
        self.version_sources = {}
        self.quality = QualityStore(Path(settings['device_key_file']).parent / 'episode-quality.json')
        self.progress = ProgressStore(settings.get('progress_file', str(Path(settings['device_key_file']).parent / 'samsung-watch-progress.json')))
        self.show_logo_dir = Path(settings.get('show_logo_dir', str(Path(settings['device_key_file']).parent / 'show-logos')))

        self.discovery_task = None
        private=Path(settings['device_key_file']).parent
        self.discovery_root=private/'samsung-discovery';self.discovery_root.mkdir(exist_ok=True,mode=0o700)
        from discovery import Discovery
        from recommendations import Ratings
        from related import RelatedShows
        self.discovery=Discovery(self.discovery_root,settings['public_base'])
        self.discovery.catalogue_path=getattr(bridge,'config',{}).get('catalogue',str(Path(settings['bridge_root'])/'catalogue.json'))
        self.ratings=Ratings(private,self.discovery_root)
        self.related=RelatedShows(private,self.discovery_root,self.discovery)
        from episode_artwork import EpisodeArtwork
        self.episode_artwork=EpisodeArtwork(self.discovery_root)
        self.bbc_schedules={}
        self.metadata_task=None
        try:self.favourite_dates=json.loads((self.discovery_root/'favourite-dates.json').read_text())
        except (OSError,ValueError):self.favourite_dates={}
        from episode_freshness import EpisodeFreshness
        self.episode_freshness=EpisodeFreshness(self.discovery_root/'episode-first-seen.json')
        self.result_lists={}
        try:self.favourites=json.loads((self.discovery_root/'favourites.json').read_text())
        except (OSError,ValueError):self.favourites={}
        try:self.saved_sources=json.loads((self.discovery_root/'saved-programmes.json').read_text())
        except (OSError,ValueError):self.saved_sources={}

    def art_id(self, url):
        if not url:
            return None
        key = hashlib.sha256(url.encode()).hexdigest()[:24]
        self.art[key] = url
        return key

    def library(self):
        self.bridge.reload_catalogue()
        grouped = {}
        try:
            logo_meta = json.loads((Path(self.settings['device_key_file']).parent / 'tmdb-logo-manifest.json').read_text())
        except (OSError, ValueError):
            logo_meta = {}
        originals={p['id']:p for p in self.bridge.catalogue['programmes']}
        for raw in self.saved_sources.values():
            if raw['id'] not in originals:originals[raw['id']]=raw
        for record in list(self.discovery.imported.values()):
            raw=record['programme']
            if raw['id'] not in originals:originals[raw['id']]=raw
        for raw in originals.values():
            for e in raw['episodes']:
                if raw.get('provider_id')=='bbc' and e.get('kind')=='plugin':e['quality']='720p50,720p_hls,540p,396p'
        self.bridge.episodes.update({e['id']:e for p in originals.values() for e in p['episodes']})
        for p in originals.values():
            episodes = [e for e in p['episodes'] if not e.get('blocked')]
            if p.get('blocked') or not episodes:
                continue
            key = group_key(p)
            if key not in grouped:
                grouped[key] = {'id': hashlib.sha256(key.encode()).hexdigest()[:20],
                    'title': p['title'], 'description': p.get('description', ''),
                    'image': self.art_id(p.get('artwork')), 'hero': self.art_id(p.get('hero') or p.get('artwork')),
                    'live': bool(p.get('live') or all(e.get('live') for e in episodes)),
                    'recent': False, 'favourite': False, 'film': is_film(p), 'genres': [], '_providers': [], '_episodes': []}
            item = grouped[key]
            item['genres'] = sorted(set(item['genres'] + genres([p.get('genre', '')] + logo_meta.get(item['id'], {}).get('genres', []))))
            item['film'] |= is_film(p) or logo_meta.get(item['id'], {}).get('media_type') == 'movie'
            item['recent'] |= bool(p.get('recent'))
            item['favourite'] |= bool(p.get('favourite'))
            if p.get('provider', '') not in item['_providers']:
                item['_providers'].append(p.get('provider', ''))
            item['_episodes'].extend((e, p.get('provider', '')) for e in episodes)
        episode_images={pid:url for row in list(self.episode_artwork.cache.values()) for pid,url in row.get('images',{}).items()}
        from episode_artwork import episode_pid
        for item in grouped.values():
            item['_versions'] = versions(item['id'], item['_episodes'])
            for version in item['_versions']:
                self.version_sources[version['id']] = [e['id'] for e,_ in version['sources']]
            item['_all_episodes'] = item['_episodes']
            item['_episodes'] = [(dict(self.quality.preferred(v)[0], id=v['id']), self.quality.preferred(v)[1]) for v in item['_versions']]
            for e,provider in item['_episodes']:
                version=next((v for v in item['_versions'] if v['id']==e['id']),None)
                if version:
                    raw,chosen_provider=self.quality.preferred(version)
                    still=episode_images.get(episode_pid(raw))
                    if chosen_provider=='BBC iPlayer' and still:e['thumbnail']=still
            latest=max((self.progress_record(e['id']).get('updated_at',0) for e,_ in item['_episodes']),default=0)
            item['updated_at']=latest
            item['favourite_at']=self.favourite_dates.get(item['id'],0)
            resumes=[(self.progress_record(e['id']),e) for e,_ in item['_episodes'] if self.version_resume(e['id'])]
            if resumes:
                record,e=max(resumes,key=lambda pair:pair[0].get('updated_at',0))
                length=seconds(record.get('duration') or e.get('duration_seconds'))
                item['progress']=min(100,record.get('position',0)/length*100) if length else 0
            if (self.show_logo_dir / (item['id'] + '.png')).is_file(): item['show_logo'] = item['id']; item['show_title'] = item['title']
            recent = [(self.progress_record(e['id']).get('updated_at', 0), e['id']) for e, _ in item['_episodes'] if self.version_resume(e['id'])]
            if recent:
                _, item['resume_episode'] = max(recent)
                item['recent'] = True
            if item['film'] and len(item['_episodes']) == 1:
                item['episode_id'] = item['_episodes'][0][0]['id']
            item['brands'] = provider_brands(item['_providers'])
            item['meta'] = ' · '.join(item['_providers']) + (' · LIVE' if item['live'] else ' · %d episodes' % len(item['_episodes']))
            if item['live']:
                item['episode_id'] = item['_episodes'][0][0]['id']
                item['channel_brand'] = CHANNEL_ART.get(item['title'].casefold())
                guide = self.guide.get(GUIDE_KEY.get(item['channel_brand'],item['channel_brand']))
                if item['channel_brand'] in self.bbc_schedules:
                    from live_descriptions import current
                    fresh=current(self.bbc_schedules[item['channel_brand']],time.time())
                    if fresh.get('now'):guide=fresh
                item['guide'] = {k: dict(v) if isinstance(v,dict) else v for k,v in guide.items()}
                if item['guide'].get('now',{}):
                    item['guide']['now']['art'] = self.art_id(item['guide']['now'].get('image'))
        result=list(grouped.values())
        for item in result:
            if item['id'] in self.favourites:item['favourite']=self.favourites[item['id']]
        from live_availability import on_air_channels
        return self.ratings.enrich(on_air_channels(result,time.time()))

    @staticmethod
    def public(item):
        return {k: v for k, v in item.items() if not k.startswith('_') and k != 'episodes'}

    def suggestion_library(self):
        result=[]
        for p in self.library():
            episodes=[]
            for e,provider in p['_episodes']:
                record=self.progress_record(e['id']);duration=seconds(record.get('duration') or e.get('duration_seconds'))
                episodes.append({**{key:e.get(key) for key in ('id','title','season','episode_number','description','broadcast_at','available_at')},
                    'thumbnail':self.art_id(e.get('thumbnail')),'duration_seconds':duration,'updated_at':record.get('updated_at',0),
                    'position':record.get('position',0),'completed':record.get('completed',False),
                    'progress':(record.get('position',0)/duration*100) if duration else 0})
            result.append(dict(self.public(p),artwork=p.get('hero') or p.get('image'),episodes=episodes))
        return self.episode_freshness.enrich(result)

    def discovery_card(self,p):
        if not p.get('discovery_ref'):return self.public(p)
        return dict(p,image=self.art_id(p.get('artwork')),hero=self.art_id(p.get('hero')),meta=' · '.join(b['name'] for b in p.get('brands',[])))

    async def browse_suggestions(self,request):
        mode=request.query.get('mode','recommend');query=request.query.get('q','')[:100];genre=request.query.get('genre','')[:70];ident=request.query.get('id','')
        token=request.query.get('snapshot')
        library=self.suggestion_library()
        if token:
            record=self.result_lists.get(token)
            if not record or time.time()-record['created']>3600:return web.json_response({'error':'Reopen this section to refresh the suggestions.'},status=410)
            items=record['items']
        else:
            from recommendations import recommend,featured_films,featured_shows,personal_shows,normal_title,genre_order
            if mode=='search':
                result=await asyncio.to_thread(self.discovery.search,query)
                local=[p for p in library if query.casefold() in p['title'].casefold() and not p.get('live')]
                items=local+result['programmes'] if len(query)>=2 else []
            elif mode=='related':
                programme=next((p for p in library if p['id']==ident and not p.get('live')),None)
                if not programme:raise web.HTTPNotFound()
                items=await asyncio.to_thread(self.related.list,programme,library)
            elif mode=='featured':items=featured_films(library)
            elif mode=='highlights':items=featured_shows(library)
            elif mode=='shows':
                personal=personal_shows(library,genre or None,16)
                exclude={normal_title(p['title']) for p in personal}
                candidates=await asyncio.to_thread(self.discovery.genre_candidates,genre) if genre else await asyncio.to_thread(self.discovery.recommendation_candidates,library)
                candidates=[p for p in candidates+library if not p.get('film') and not p.get('live') and normal_title(p['title']) not in exclude]
                items=personal+await asyncio.to_thread(recommend,library,candidates,3000,genre=genre or None,provider_cap=None,include_known=True,include_unmatched=True)
            else:
                candidates=await asyncio.to_thread(self.discovery.genre_candidates,genre) if genre else await asyncio.to_thread(self.discovery.recommendation_candidates,library)
                items=recommend(library,candidates,2000,genre=genre or None,provider_cap=None)
            seen=set();unique=[]
            for item in items:
                key=re.sub(r'[^\w]+',' ',item['title'].casefold()).strip()
                if key not in seen:seen.add(key);unique.append(self.discovery_card(item))
            items=unique;token=secrets.token_urlsafe(16)
            self.result_lists={k:v for k,v in self.result_lists.items() if time.time()-v['created']<3600}
            if len(self.result_lists)>=16:self.result_lists.pop(next(iter(self.result_lists)))
            self.result_lists[token]={'created':time.time(),'items':items}
        from recommendations import genre_order
        choices=genre_order(library)
        choices += sorted({g for item in items for g in genres(item.get('genres',[]))}-set(choices))
        return self.page(request,items,snapshot=token,genres=choices)

    async def import_show(self,request):
        data=await request.json();ref=data.get('ref','')
        if not isinstance(ref,str) or not re.fullmatch(r'(bbc|channel4|u|channel5|itv):[A-Za-z0-9_-]{1,120}',ref):raise web.HTTPBadRequest()
        try:
            raw=await asyncio.to_thread(self.discovery.import_show,ref)
            # Retain the Samsung's proven compatible rendition policy.
            for record in self.discovery.imported.values():
                for episode in record['programme']['episodes']:
                    if episode.get('kind')=='plugin':episode['quality']='720p50,720p_hls,540p,396p'
            group=next(p for p in self.library() if any(e['id'] in {x['id'] for x in raw['episodes']} for e,_ in p['_all_episodes']))
            return web.json_response(self.public(group))
        except Exception:return web.json_response({'error':'Available episodes could not be loaded. Try this title later.'},status=422)

    async def favourite(self,request):
        data=await request.json();ident=data.get('id');value=data.get('favourite')
        if not isinstance(value,bool) or not isinstance(ident,str):raise web.HTTPBadRequest()
        group=next((p for p in self.library() if p['id']==ident and not p['live']),None)
        if not group:raise web.HTTPNotFound()
        source_ids={e['id'] for e,_ in group['_all_episodes']}
        if value:
            for record in self.discovery.imported.values():
                raw=record['programme']
                if any(e['id'] in source_ids for e in raw['episodes']):self.saved_sources[raw['id']]=raw
        self.favourites[ident]=value
        if value:self.favourite_dates[ident]=time.time()
        from tmdb_logos import atomic
        atomic(self.discovery_root/'favourites.json',json.dumps(self.favourites).encode())
        atomic(self.discovery_root/'favourite-dates.json',json.dumps(self.favourite_dates).encode())
        atomic(self.discovery_root/'saved-programmes.json',json.dumps(self.saved_sources).encode())
        return web.json_response({'ok':True,'favourite':value})

    async def metadata_loop(self):
        while True:
            try:
                from live_descriptions import fetch_bbc
                self.bbc_schedules=await asyncio.to_thread(fetch_bbc)
                catalogue=dict(self.bridge.catalogue)
                catalogue['programmes']=catalogue['programmes']+[r['programme'] for r in self.discovery.imported.values()]
                await asyncio.to_thread(self.episode_artwork.refresh,catalogue)
            except Exception:logging.warning('Samsung artwork/guide refresh deferred.')
            await asyncio.sleep(300)

    async def discovery_loop(self):
        while True:
            try:
                await asyncio.to_thread(self.discovery.warm)
                await asyncio.to_thread(self.ratings.refresh,self.suggestion_library())
            except Exception:logging.warning('Samsung discovery refresh deferred.')
            await asyncio.sleep(21600)

    async def library_api(self, request):
        tab = request.query.get('tab', '0')
        items = self.library()
        items = [p for p in items if p['live'] == (tab == '2')]
        if tab == '0':
            from recommendations import home_shows
            items=home_shows(self.suggestion_library())
        film_order={}
        if tab == '3':
            from recommendations import ranked_films
            film_order={p['id']:i for i,p in enumerate(ranked_films(self.suggestion_library()))}
            items = [dict(p,film_rank=film_order.get(p['id'],99999)) for p in items if p['film']]
        elif tab in ('0','1'):
            items = [p for p in items if not p['film'] or (tab == '0' and (p['recent'] or p['favourite']))]
        from recommendations import genre_order
        available={g for p in items for g in p['genres']}
        choices=[g for g in genre_order(self.suggestion_library()) if g in available]
        choices+=sorted(available-set(choices))
        selected_genre = request.query.get('genre', '')
        if selected_genre:
            items = [p for p in items if selected_genre in p['genres']]
        if tab == '0':
            pass  # home_shows already applies continue-watching and release-date order.
        elif tab == '3':
            items.sort(key=lambda p:p['film_rank'])
        elif tab == '2':
            items.sort(key=lambda p: (LIVE_ORDER.get(p['title'].casefold(), 1000), p['title'].casefold()))
        else:
            items.sort(key=lambda p: p['title'].casefold())
        return self.page(request, [self.public(p) for p in items], genres=choices)

    def page(self, request, items, **extra):
        try:
            page = max(0, int(request.query.get('page', '0')))
        except ValueError:
            raise web.HTTPBadRequest()
        size = 4 if request.query.get('size') == '4' else 8
        page = min(page, max(0, (len(items) - 1) // size))
        return web.json_response({'page': page, 'total': len(items), 'items': items[page * size:page * size + size], **extra})

    async def episodes_api(self, request):
        group = next((p for p in self.library() if p['id'] == request.match_info['group']), None)
        if not group:
            raise web.HTTPNotFound()
        items = []
        for episode, provider in sorted(group['_episodes'], key=lambda pair: episode_order(pair[0]), reverse=True):
            selected = request.query.get('season', 'all')
            if selected != 'all' and self.season_id(episode) != selected:
                continue
            items.append({k: episode[k] for k in ('id', 'title', 'description', 'live') if k in episode} |
                {'show_logo':group.get('show_logo'), 'show_title':group['title'],
                 'resume_seconds': self.version_resume(episode['id']), 'progress':min(100,self.progress_record(episode['id']).get('position',0)/seconds(episode.get('duration_seconds'))*100) if seconds(episode.get('duration_seconds')) else 0, 'duration_seconds': seconds(episode.get('duration_seconds', 0)),
                 'brands': provider_brands([provider]), 'image': self.art_id(episode.get('thumbnail')), 'meta': ' · '.join(filter(None,
                    [('Resume %d:%02d' % (self.version_resume(episode['id']) // 60, self.version_resume(episode['id']) % 60)) if self.version_resume(episode['id']) else '', provider, episode.get('duration_label'), 'Recently watched' if episode.get('recent') else '']))})
        return self.page(request, items)

    def find_version(self, ident):
        for group in self.library():
            for version in group['_versions']:
                if version['id'] == ident or any(e['id'] == ident for e, _ in version['sources']):
                    return version
        return None

    def progress_record(self, ident):
        record=self.progress.get(ident)
        if record:return record
        return max((self.progress.get(source) for source in self.version_sources.get(ident,[])),key=lambda r:r.get('updated_at',0),default={})

    def version_resume(self, ident):
        record=self.progress_record(ident)
        return max(0,record.get('position',0)-5) if not record.get('completed') and record.get('position',0)>=10 else 0

    @staticmethod
    def season_id(episode):
        return hashlib.sha256(str(episode.get('season', 'Episodes')).encode()).hexdigest()[:16]

    async def seasons_api(self, request):
        group = next((p for p in self.library() if p['id'] == request.match_info['group']), None)
        if not group:
            raise web.HTTPNotFound()
        seasons = {}
        for episode, provider in sorted(group['_episodes'], key=lambda pair: episode_order(pair[0]), reverse=True):
            key = self.season_id(episode)
            label = str(episode.get('season', 'Episodes'))
            if label.isdigit():
                label = 'Series ' + label
            if key not in seasons:
                seasons[key] = {'id': key, 'title': label, 'image': self.art_id(episode.get('thumbnail')),
                    'description': group['title'], '_count': 0, '_providers': []}
            seasons[key]['_count'] += 1
            if provider not in seasons[key]['_providers']:
                seasons[key]['_providers'].append(provider)
        items = [{'id': 'all', 'title': 'All episodes', 'image': group['image'], 'brands': group['brands'],
                  'description': group['description'], 'meta': group['meta']}]
        for season in seasons.values():
            season['brands'] = provider_brands(season['_providers'])
            season['meta'] = '%d episodes' % season['_count']
            items.append(self.public(season))
        if group.get('show_logo'):
            for item in items:
                item['show_logo']=group['show_logo'];item['show_title']=group['title']
        return self.page(request, items)

    async def prepare(self, request):
        data = await request.json()
        self.bridge.reload_catalogue()
        requested_id = data.get('episode_id')
        version = self.find_version(requested_id)
        episode = self.quality.preferred(version)[0] if version else self.bridge.episodes.get(requested_id)
        if not episode or episode.get('blocked'):
            return web.json_response({'error': 'Choose an available episode.'}, status=400)
        if self.worker and not self.worker.done():
            return web.json_response({'error': 'Another episode is preparing. Please wait.'}, status=409)
        if self.current_ticket:
            return web.json_response({'error': 'Stop the current episode before starting another.'}, status=409)
        episode = dict(episode)
        progress_id = version['id'] if version else episode['id']
        if version and not self.progress.get(progress_id):
            old = max((self.progress.get(e['id']) for e, _ in version['sources']), key=lambda r:r.get('updated_at',0), default={})
            if old:
                self.progress.save(progress_id,old['position'],old.get('duration',0),old.get('completed',False))
        try:
            position = float(data['start_position']) if 'start_position' in data else self.version_resume(progress_id)
            if not math.isfinite(position) or not 0 <= position <= 86400: raise ValueError()
            if episode.get('live') and position: raise ValueError()
        except (TypeError, ValueError):
            return web.json_response({'error': 'Invalid starting position.'}, status=400)
        if position: episode['_start_offset'] = position
        episode['_progress_id'] = progress_id
        if version:episode['_source_variants'] = version['sources']
        # One physical app, one prepared source. No external player control occurs here.
        job = secrets.token_urlsafe(24)
        self.current_job = job
        self.jobs = {job: {'state': 'preparing'}}
        self.worker = asyncio.create_task(self.prepare_worker(job, dict(episode)))
        self.workers.add(self.worker)
        self.worker.add_done_callback(self.workers.discard)
        return web.json_response({'job': job}, status=202)

    async def reconnect(self, request):
        # There is only one physical paired app. Reopening after a crash releases
        # its old relay immediately, while saved progress remains intact.
        self.current_job = None
        if self.current_ticket: await self.release(self.current_ticket)
        if request.can_read_body:
            data = await request.json()
            dimensions = {k: data[k] for k in ('viewport_width','viewport_height','screen_width','screen_height')
                          if isinstance(data.get(k), (int, float)) and 0 < data[k] <= 8192}
            if isinstance(data.get('app_version'),str) and re.fullmatch(r'\d+\.\d+',data['app_version']):
                dimensions['app_version']=data['app_version']
            if dimensions:
                dimensions['reported_at'] = time.time()
                path = self.progress.path.parent / 'watch-display-report.json'
                path.write_text(json.dumps(dimensions)); path.chmod(0o600)
        return web.json_response({'ok': True})

    async def prepare_worker(self, job, episode):
        try:
            from bridge import compatible
            candidates = episode.pop('_source_variants', [(episode, '')])
            candidates = sorted(candidates, key=self.quality.rank, reverse=True)
            compare = len(candidates)>1 and not all(self.quality.fresh(e['id']) for e,_ in candidates)
            chosen = []
            for candidate, provider in candidates:
                if self.current_job != job:return
                source = dict(candidate, _progress_id=episode.get('_progress_id', episode['id']))
                if episode.get('_start_offset'):source['_start_offset']=episode['_start_offset']
                try:
                    prepared = await asyncio.to_thread(self.bridge.prepare, source)
                    compatible(prepared['info'], 'samsung_legacy')
                    self.quality.record(source['id'], prepared['info'])
                    chosen.append((self.quality.rank((source,provider)), source, prepared))
                    if not compare:break
                except Exception:
                    self.quality.invalidate(source['id'])
                    continue
            if not chosen:raise ValueError('No compatible episode source available.')
            _, episode, prepared = max(chosen, key=lambda entry:entry[0])
            if self.current_job != job:
                return
            ticket = secrets.token_urlsafe(24)
            duration = seconds(episode.get('duration_seconds'))
            prepared.update(expires=time.time() + 21600, _last_seen=time.time(), endpoint_id='native_samsung',
                _episode_id=episode.get('_progress_id',episode['id']), _duration=duration, _is_live=bool(episode.get('live')))
            self.bridge.tickets[ticket] = prepared
            self.current_ticket = ticket
            raw_programmes=list(self.bridge.catalogue['programmes'])+list(self.saved_sources.values())+[r['programme'] for r in self.discovery.imported.values()]
            programme = next((p for p in raw_programmes if any(e['id'] == episode['id'] for e in p['episodes'])), {})
            logo_id = hashlib.sha256(group_key(programme).encode()).hexdigest()[:20] if programme else None
            self.jobs[job] = {'state': 'ready', 'ticket': ticket, 'title': episode['title'],
                'episode_id': episode.get('_progress_id',episode['id']), 'start_position': episode.get('_start_offset', 0), 'duration_seconds': duration,
                'brands': provider_brands([programme.get('provider','')]),
                'show_title': programme.get('title', episode['title']),
                'art':self.art_id(episode.get('thumbnail') or programme.get('hero') or programme.get('artwork')),
                'description': episode.get('description') or programme.get('description', ''),
                'season': str(episode.get('season') or ''), 'episode_number': episode.get('episode_number', 0),
                'show_logo': logo_id if logo_id and (self.show_logo_dir / (logo_id + '.png')).is_file() else None,
                'spec': stream_spec(prepared['info']),
                'url': self.settings['public_base'].rstrip('/') + '/media/' + ticket + ('/stream.ts' if prepared['live'] else '/stream.mp4'),
                'live': bool(episode.get('live'))}
            if episode.get('live'):
                channel=next((p for p in self.library() if p.get('episode_id')==episode['id']),None)
                if channel:
                    now=channel.get('guide',{}).get('now') or {}
                    self.jobs[job].update(title=now.get('title') or channel['title'],show_title=channel['title'],description=now.get('subtitle') or now.get('description') or '',channel_brand=channel.get('channel_brand'),art=now.get('art') or channel.get('hero') or channel.get('image'))
        except Exception:
            # Provider exceptions may contain signed URLs or private credentials.
            if self.current_job == job:
                self.jobs[job] = {'state': 'failed', 'error': 'This source could not be prepared. Try another episode or check the provider login.'}

    async def poll(self, request):
        job = self.jobs.get(request.match_info['job'])
        if not job:
            raise web.HTTPNotFound()
        return web.json_response(job)

    async def cancel(self, request):
        if request.match_info['job'] == self.current_job:
            self.current_job = None
            self.jobs.pop(request.match_info['job'], None)
            if self.current_ticket:
                await self.release(self.current_ticket)
        return web.json_response({'ok': True})

    async def diagnostic(self, request):
        data=await request.json()
        if data.get('event') not in ('seek','hold-player','close-player','stop-source','begin','ended','back'):
            raise web.HTTPBadRequest()
        record={k:data[k] for k in ('playing','waiting','seeking') if isinstance(data.get(k),bool)}
        record['event']=data['event'];record['reported_at']=time.time()
        if isinstance(data.get('position'),(int,float)) and math.isfinite(data['position']) and 0<=data['position']<=86400:record['position']=data['position']
        if isinstance(data.get('app_version'),str) and re.fullmatch(r'\d+\.\d+',data['app_version']):record['app_version']=data['app_version']
        path=self.progress.path.parent/'watch-client-events.json'
        try:records=json.loads(path.read_text())
        except (OSError,ValueError):records=[]
        records=(records+[record])[-50:]
        from tmdb_logos import atomic
        atomic(path,json.dumps(records).encode())
        return web.json_response({'ok':True})

    async def release(self, token):
        ticket = self.bridge.tickets.pop(token, None)
        if ticket:
            for fd in list(ticket.get('_active_streams', [])):
                await asyncio.to_thread(fd.close)
        if self.current_ticket == token:
            self.current_ticket = None

    async def delete(self, request):
        if request.can_read_body:
            data = await request.json()
            self.remember(request.match_info['ticket'], data)
        await self.release(request.match_info['ticket'])
        return web.json_response({'ok': True})

    async def heartbeat(self, request):
        ticket = self.bridge.tickets.get(request.match_info['ticket'])
        if not ticket:
            raise web.HTTPNotFound()
        ticket['_last_seen'] = time.time()
        if request.can_read_body:
            self.remember(request.match_info['ticket'], await request.json())
        return web.json_response({'ok': True})

    def remember(self, token, data):
        ticket = self.bridge.tickets.get(token)
        if not ticket or ticket.get('_is_live') or not ticket.get('_episode_id') or 'position' not in data: return
        try:
            self.progress.save(ticket['_episode_id'], data['position'], ticket.get('_duration', 0), data.get('completed') is True)
        except (ValueError, TypeError):
            raise web.HTTPBadRequest()

    async def media(self, request):
        ticket = self.bridge.tickets.get(request.match_info['ticket'])
        if ticket and ticket['live'] and 'Range' in request.headers:
            # A streaming response may legally ignore Range. A finite MP4 still
            # uses FileResponse and supports the TV's exact byte-range probes.
            headers = dict(request.headers)
            headers.pop('Range', None)
            request = request.clone(headers=headers)
        return await self.bridge.media(request)

    def get_image(self, image_id, variant='hero'):
        cache_key = image_id + ':' + variant
        if cache_key in self.images:
            self.images.move_to_end(cache_key)
            return self.images[cache_key]
        url = self.art.get(image_id, '')
        image = None
        if url.startswith('/local/tv-favourites/'):
            path = Path(self.settings['bridge_root']) / url.removeprefix('/local/tv-favourites/')
            if path.resolve().is_relative_to(Path(self.settings['bridge_root']).resolve()) and path.suffix.lower() in ('.jpg', '.jpeg', '.png'):
                image = Image.open(path)
        elif urlsplit(url).scheme == 'https' and urlsplit(url).hostname in ART_HOSTS:
            with requests.get(url, timeout=12, stream=True, allow_redirects=False) as response:
                response.raise_for_status()
                data = bytearray()
                for chunk in response.iter_content(65536):
                    data.extend(chunk)
                    if len(data) > 8 * 1024 * 1024:
                        raise ValueError('Artwork is too large.')
                image = Image.open(io.BytesIO(data))
        if image is None:
            image = Image.new('RGB', (640, 360), '#23394c')
            ImageDraw.Draw(image).text((35, 160), 'WATCH  /  LIVE TV', fill='#9cffe3')
        image = image.convert('RGB')
        if variant == 'thumb':
            image = ImageOps.fit(image, (480, 270), method=Image.Resampling.LANCZOS)
        else:
            image.thumbnail((1280, 720), Image.Resampling.LANCZOS)
        data = io.BytesIO()
        image.save(data, 'JPEG', quality=82)
        self.images[cache_key] = data.getvalue()
        while len(self.images) > 180:
            self.images.popitem(last=False)
        return self.images[cache_key]

    async def artwork(self, request):
        if request.match_info['image'] not in self.art:
            self.library()
        try:
            if request.query.get('size') == 'thumb':
                data = await asyncio.to_thread(self.get_image, request.match_info['image'], 'thumb')
            else:
                data = await asyncio.to_thread(self.get_image, request.match_info['image'])
        except Exception:
            raise web.HTTPNotFound()
        return web.Response(body=data, content_type='image/jpeg', headers={'Cache-Control': 'private, max-age=1800'})

    async def show_logo(self, request):
        ident = request.match_info['group']
        if not re.fullmatch(r'[a-f0-9]{20}', ident): raise web.HTTPNotFound()
        path = self.show_logo_dir / (ident + '.png')
        if not path.is_file(): raise web.HTTPNotFound()
        return web.FileResponse(path, headers={'Content-Type':'image/png', 'Cache-Control':'private, max-age=1800'})

    async def cleanup_loop(self):
        while True:
            await asyncio.sleep(15)
            for token, ticket in list(self.bridge.tickets.items()):
                if time.time() - ticket['_last_seen'] > 90 or ticket['expires'] < time.time():
                    await self.release(token)

    async def logo_loop(self):
        while True:
            try:
                self.bridge.reload_catalogue()
                programmes = list(self.bridge.catalogue['programmes'])+[r['programme'] for r in self.discovery.imported.values()]
                await asyncio.to_thread(sync_logos, Path(self.settings['device_key_file']).parent, programmes, self.show_logo_dir)
            except Exception:
                logging.warning('TMDB logo refresh deferred; existing artwork retained.')
            await asyncio.sleep(600)

    async def start(self, app):
        self.janitor = asyncio.create_task(self.cleanup_loop())
        self.logo_task = asyncio.create_task(self.logo_loop())
        if self.settings.get('discovery_enabled', True):
            self.discovery_task=asyncio.create_task(self.discovery_loop())
            self.metadata_task=asyncio.create_task(self.metadata_loop())
        if self.settings.get('guide_enabled', True):
            self.guide_task = asyncio.create_task(self.guide.run())

    async def stop(self, app):
        self.current_job = None
        for token in list(self.bridge.tickets):
            await self.release(token)
        self.janitor.cancel()
        await asyncio.gather(self.janitor, return_exceptions=True)
        if self.guide_task:
            self.guide_task.cancel()
            await asyncio.gather(self.guide_task, return_exceptions=True)
        if self.logo_task:
            self.logo_task.cancel()
            await asyncio.gather(self.logo_task, return_exceptions=True)
        if self.metadata_task:
            self.metadata_task.cancel()
            await asyncio.gather(self.metadata_task,return_exceptions=True)
        if self.discovery_task:
            self.discovery_task.cancel()
            await asyncio.gather(self.discovery_task,return_exceptions=True)
        if self.workers:
            await asyncio.gather(*self.workers, return_exceptions=True)

    def app(self):
        @web.middleware
        async def authorize(request, handler):
            if request.remote not in self.settings['allowed_clients']:
                return web.json_response({'error': 'This app is paired to another TV.'}, status=403)
            if request.method == 'OPTIONS':
                return web.Response(status=204)
            if not request.path.startswith('/media/'):
                supplied = request.headers.get('X-Watch-Key', '')
                if request.path.startswith(('/art/', '/show-logo/')):
                    supplied = request.query.get('key', supplied)
                if not hmac.compare_digest(supplied, self.key):
                    return web.json_response({'error': 'Reinstall the paired Watch app.'}, status=401)
            try:
                return await handler(request)
            except web.HTTPException as error:
                if request.path.startswith('/api/'):
                    return web.json_response({'error': 'This item is no longer available. Refresh the library.'}, status=error.status)
                raise

        app = web.Application(middlewares=[authorize], client_max_size=4096)
        async def cors(request, response):
            response.headers['Access-Control-Allow-Origin'] = '*'
            response.headers['Access-Control-Allow-Headers'] = 'X-Watch-Key, Content-Type'
            response.headers['Access-Control-Allow-Methods'] = 'GET, POST, DELETE, OPTIONS'
            if request.path.startswith('/api/'):
                response.headers['Cache-Control'] = 'no-store'
        app.on_response_prepare.append(cors)
        async def options(request):
            return web.Response(status=204)
        app.router.add_route('OPTIONS', '/{path:.*}', options)
        app.router.add_get('/api/library', self.library_api)
        app.router.add_get('/api/suggestions', self.browse_suggestions)
        app.router.add_post('/api/import', self.import_show)
        app.router.add_post('/api/favourite', self.favourite)
        app.router.add_get('/api/episodes/{group}', self.episodes_api)
        app.router.add_get('/api/seasons/{group}', self.seasons_api)
        app.router.add_post('/api/prepare', self.prepare)
        app.router.add_post('/api/session', self.reconnect)
        app.router.add_post('/api/diagnostic', self.diagnostic)
        app.router.add_get('/api/prepare/{job}', self.poll)
        app.router.add_delete('/api/prepare/{job}', self.cancel)
        app.router.add_delete('/api/play/{ticket}', self.delete)
        app.router.add_post('/api/play/{ticket}/heartbeat', self.heartbeat)
        app.router.add_get('/art/{image}', self.artwork)
        app.router.add_get('/show-logo/{group}', self.show_logo)
        app.router.add_get('/media/{ticket}', self.media)
        app.router.add_get('/media/{ticket}/{filename:stream\\.(?:ts|mp4)}', self.media)
        app.on_startup.append(self.start)
        app.on_cleanup.append(self.stop)
        return app


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--config', required=True)
    args = parser.parse_args()
    settings = json.loads(Path(args.config).read_text())
    sys.path.insert(0, settings['bridge_root'])
    os.chdir(settings['bridge_root'])
    from bridge import Bridge
    config = json.loads(Path(settings['bridge_config']).read_text())
    config['public_base'] = settings['public_base']
    bridge = Bridge(config)
    logging.basicConfig(level=logging.WARNING)
    logging.getLogger('streamlink').setLevel(logging.CRITICAL)
    gateway = Gateway(settings, bridge)
    web.run_app(gateway.app(), host=settings['bind'], port=settings['port'], access_log=None, shutdown_timeout=5)


if __name__ == '__main__':
    main()
