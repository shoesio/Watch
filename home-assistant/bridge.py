#!/usr/bin/env python3
"""HA-authorized account library and progressive network playback."""
import argparse
import asyncio
import contextlib
import hashlib
import json
import logging
import math
import os
import re
import secrets
import subprocess
import time
from pathlib import Path
from xml.sax.saxutils import escape
import aiohttp
from aiohttp import web
import streamlink
from streamlink.stream.http import HTTPStream
from bbc_auth import adapt as adapt_bbc_login
from provider_playback import ProviderResolver
from library_sync import LibrarySync
from browser_playback import BrowserStream, browser_media
from tv_guide import GuideSync
from dashboard_library import DashboardLibrary
from live_guide import LiveGuide
from episode_versions import seconds

LOG = logging.getLogger('tv-favourites')
URN = 'urn:schemas-upnp-org:service:AVTransport:1'


def probe(path=None, data=None):
    cmd = ['ffprobe', '-v', 'error', '-show_streams', '-show_format', '-of', 'json', str(path) if path else 'pipe:0']
    r = subprocess.run(cmd, input=data, capture_output=True, timeout=20)
    if r.returncode:
        raise ValueError('The source could not be identified as a compatible video stream.')
    d = json.loads(r.stdout)
    video = next((s for s in d['streams'] if s['codec_type'] == 'video'), None)
    audio = [s for s in d['streams'] if s['codec_type'] == 'audio']
    if not video or video['codec_name'] != 'h264' or any(s['codec_name'] not in ['aac', 'mp3'] for s in audio):
        raise ValueError('This source needs different codecs. This dashboard does not re-encode video or audio.')
    return d


def compatible(info, profile):
    v = next(s for s in info['streams'] if s['codec_type'] == 'video')
    rate = v.get('avg_frame_rate', '0/1').split('/')
    fps = float(rate[0]) / max(float(rate[-1]), 1)
    max_fps = 60.1 if v.get('height', 0) <= 720 and v.get('width', 0) <= 1280 else 30.1
    if profile == 'samsung_legacy' and (v.get('height', 0) > 1080 or v.get('width', 0) > 1920 or fps > max_fps or v.get('level', 0) > 41):
        raise ValueError('Choose H.264 Level 4.1 or lower, up to 720p60 or 1080p30, for this Samsung.')


class Bridge:
    def __init__(self, config):
        self.config = config
        self.catalogue_stamp = None
        self.reload_catalogue()
        self.token = Path(config['ha_token_file']).read_text().strip()
        self.cache = Path(config['cache_dir']); self.cache.mkdir(parents=True, exist_ok=True)
        self.tickets = {}
        self.endpoint_states = {}
        self.message = 'Ready. Choose a programme and output.'
        self.lock = asyncio.Lock()
        self.stream_slots = asyncio.Semaphore(2)
        self.http = None
        self.tasks = []
        self.connected = False
        self.private_root = Path(config.get('private_root', '/home/jhewes/tv-favourites-private'))
        self.provider = ProviderResolver(self.private_root)
        self.library_lock = asyncio.Lock()
        self.watch = DashboardLibrary(self.private_root, config.get('public_base','http://127.0.0.1:8109'))
        self.watch_guide = LiveGuide()
        from ha_alignment import Alignment
        self.alignment = Alignment(self.private_root)

    def reload_catalogue(self):
        path = Path(self.config['catalogue'])
        private=Path(self.config.get('private_root','/home/jhewes/tv-favourites-private'))
        shared=private/'appletv'
        shared_stamp=tuple((shared/name).stat().st_mtime_ns if (shared/name).exists() else 0 for name in ('discovery-library.json','favourite-programmes.json'))
        stamp = path.stat().st_mtime_ns
        if stamp == self.catalogue_stamp and shared_stamp == getattr(self,'shared_catalogue_stamp',None):
            return
        from ha_alignment import augment
        catalogue = augment(json.loads(path.read_text()),private)
        episodes = {e['id']: e for p in catalogue['programmes'] for e in p['episodes']}
        endpoints = {e['id']: e for e in catalogue['endpoints']}
        if len(episodes) != sum(len(p['episodes']) for p in catalogue['programmes']):
            raise ValueError('Episode IDs must be unique.')
        if len(endpoints) != len(catalogue['endpoints']):
            raise ValueError('Endpoint IDs must be unique.')
        self.catalogue, self.episodes, self.endpoints = catalogue, episodes, endpoints
        self.catalogue_stamp = stamp
        self.shared_catalogue_stamp = shared_stamp

    async def api(self, path, data=None):
        async with self.http.request('GET' if data is None else 'POST', self.config['ha_url'] + '/api/' + path,
                                     json=data, headers={'Authorization': 'Bearer ' + self.token},
                                     timeout=aiohttp.ClientTimeout(total=20)) as r:
            if r.status >= 400:
                raise RuntimeError('Home Assistant rejected the request (HTTP %s).' % r.status)
            return await r.json()

    async def publish(self):
        # Only non-secret catalogue data reaches the dashboard.
        guide = GuideSync(self.private_root / 'guide.json').now_next()
        for channel in ('bbcone','bbctwo','bbcfour','bbcnews','C4','E4','M4','F4','4S'):
            current=self.watch_guide.get(channel)
            if current:guide[channel]=current
        programmes = self.watch.project(self.catalogue, guide)
        programmes = await self.alignment.enrich(self.http,programmes)
        for programme in programmes:
            for item in [programme, *programme['episodes']]:
                for key in ('artwork', 'hero', 'thumbnail'):
                    if item.get(key, '').startswith('/local/tv-favourites/'):
                        item[key] = self.config['public_base'].rstrip('/') + '/static/' + item[key].split('/local/tv-favourites/', 1)[1]
        await self.api('states/sensor.tv_favourites', {
            'state': 'preparing' if self.lock.locked() else 'ready',
            'attributes': {'friendly_name': 'TV favourites', 'icon': 'mdi:television-play',
                           'message': self.message, 'programmes': programmes,
                           'endpoints': [{k: e[k] for k in ['id','name','blocked','note'] if k in e} |
                                         self.endpoint_states.get(e['id'], {}) for e in self.endpoints.values()],
                           'guide': guide, 'playback': self.watch_playback(), 'browser_base': self.config['public_base'].rstrip('/'), 'streamlink_version': streamlink.__version__, 'updated_at': time.time(), 'library_updated_at': self.catalogue.get('library_updated_at'), 'provider_status': self.catalogue.get('provider_status', {})}})

    def session_stream(self, episode):
        session = streamlink.Streamlink()
        session.set_option('http-timeout', 15)
        session.set_option('stream-timeout', 20)
        if not episode.get('live'):
            session.set_option('stream-segment-threads', 4)
            if episode.get('_start_offset'):
                session.set_option('hls-start-offset', episode['_start_offset'])
        if episode.get('preserve_timestamps'):
            session.set_option('ffmpeg-copyts', True)
            session.set_option('ffmpeg-start-at-zero', False)
        if episode['kind'] == 'http':
            return session, HTTPStream(session, episode['url'])
        plugin_name, cls, url = session.resolve_url(episode['url'])
        options_file = Path(self.config.get('plugin_options_file', '/nonexistent'))
        all_options = json.loads(options_file.read_text()) if options_file.exists() else {}
        plugin = cls(session, url, options=all_options.get(plugin_name, {}))
        if plugin_name == 'bbciplayer':
            plugin = adapt_bbc_login(plugin)
        streams = plugin.streams()
        for q in episode.get('quality', '720p,480p,worst').split(','):
            if q in streams:
                return session, streams[q]
        raise ValueError('Streamlink found no playable stream. Check service login, availability and selected quality.')

    def prepare(self, episode):
        if episode['kind'] == 'provider':
            resolved = self.provider.resolve(episode)
            with contextlib.closing(self.provider.open(resolved, probe=True)) as fd:
                sample = bytearray()
                while len(sample) < 512 * 1024:
                    chunk = fd.read(min(65536, 512 * 1024 - len(sample)))
                    if not chunk: break
                    sample.extend(chunk)
            info = probe(data=bytes(sample))
            return {'live': True, 'provider': True, 'resolved': resolved, 'episode': episode, 'info': info, 'mime': 'video/mpeg'}
        session, stream = self.session_stream(episode)
        # Unknown-length delivery starts after a short codec probe, for live or catch-up HLS.
        if episode.get('live') or episode.get('delivery') == 'relay':
            with contextlib.closing(stream.open()) as fd:
                chunks = []
                size = 0
                while size < 512 * 1024:
                    chunk = fd.read(min(64 * 1024, 512 * 1024 - size))
                    if not chunk:
                        break
                    chunks.append(chunk)
                    size += len(chunk)
                sample = b''.join(chunks)
            info = probe(data=sample)
            if 'mpegts' not in info.get('format', {}).get('format_name', ''):
                raise ValueError('Streaming playback currently requires MPEG-TS output. Select a compatible HLS rendition.')
            return {'live': True, 'episode': episode, 'info': info, 'mime': 'video/mpeg'}
        key = hashlib.sha256(json.dumps(episode, sort_keys=True).encode()).hexdigest()[:24]
        final = self.cache / (key + '.mp4')
        if not final.exists():
            raw = self.cache / (key + '.part')
            output = self.cache / (key + '.tmp.mp4')
            start = time.monotonic()
            try:
                count = 0
                with contextlib.closing(stream.open()) as fd, raw.open('wb') as target:
                    while True:
                        block = fd.read(256 * 1024)
                        if not block:
                            break
                        count += len(block)
                        if count > episode.get('max_vod_bytes', self.config.get('max_vod_bytes', 1073741824)) or time.monotonic() - start > episode.get('prepare_timeout', self.config.get('prepare_timeout', 240)):
                            raise ValueError('Preparation limit reached. Use a smaller episode or a live source.')
                        target.write(block)
                probe(path=raw)
                # Container remux only. Copy preserves compressed audio and video; no encoding.
                result = subprocess.run(['ffmpeg','-nostdin','-v','error','-y','-i',str(raw),'-map','0:v:0',
                                         '-map','0:a:0?','-c','copy','-movflags','+faststart',str(output)],
                                        capture_output=True, timeout=60)
                if result.returncode:
                    raise ValueError('The source could not be remuxed to MP4 without re-encoding.')
                os.replace(output, final)
            finally:
                raw.unlink(missing_ok=True); output.unlink(missing_ok=True)
        return {'live': False, 'path': final, 'info': probe(path=final), 'mime': 'video/mp4'}

    async def soap(self, endpoint, action, body):
        envelope = ('<s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/"><s:Body><u:' + action +
                    ' xmlns:u="' + URN + '">' + body + '</u:' + action + '></s:Body></s:Envelope>')
        async with self.http.post(endpoint['avtransport_url'], data=envelope.encode(),
                                 headers={'SOAPAction': '"' + URN + '#' + action + '"', 'Content-Type': 'text/xml; charset="utf-8"'},
                                 timeout=aiohttp.ClientTimeout(total=5)) as r:
            text = await r.text()
            if r.status != 200 or '<s:Fault' in text:
                raise ValueError('The Samsung DLNA renderer rejected ' + action + '.')
            return text

    async def endpoint_status(self, e):
        if e.get('blocked'):
            return {'available': False, 'status': e['blocked']}
        try:
            if e['transport'] == 'ha':
                d = await self.api('states/' + e['entity_id'])
                if not d.get('attributes', {}).get('supported_features', 0) & 512:
                    return {'available': False, 'status': 'This entity does not advertise play_media.'}
                state = d['state']
                return {'available': state not in ['unknown','unavailable','off'], 'status': state,
                        'busy': state in ['playing','paused','buffering']}
            xml = await self.soap(e, 'GetTransportInfo', '<InstanceID>0</InstanceID>')
            match = re.search(r'<(?:\w+:)?CurrentTransportState>([^<]+)', xml)
            state = match[1] if match else 'unknown'
            return {'available': True, 'status': state, 'busy': state in ['PLAYING','PAUSED_PLAYBACK','TRANSITIONING']}
        except Exception:
            return {'available': False, 'status': 'Unreachable. Turn on and check the network.'}

    async def sync_library(self):
        if self.library_lock.locked(): return
        async with self.library_lock:
            try:
                await asyncio.to_thread(LibrarySync(self.private_root, self.config['catalogue']).run)
                self.reload_catalogue()
                self.message = 'Your provider library is up to date.'
            except Exception:
                self.message = 'Library refresh is temporarily unavailable. Your saved library is still here.'
                LOG.warning('Library refresh failed; retaining previous catalogue.')
            await self.publish()

    async def periodic_guide(self):
        while True:
            try:
                await asyncio.to_thread(GuideSync(self.private_root / 'guide.json').run)
                await self.publish()
            except Exception:
                LOG.warning('Programme guide refresh unavailable; retaining valid listings.')
            await asyncio.sleep(600)

    async def periodic_library(self):
        while True:
            await asyncio.sleep(600)
            await self.sync_library()

    async def play_browser(self, data):
        request_id = str(data.get('request_id', ''))
        if not re.fullmatch(r'[a-zA-Z0-9_-]{16,80}', request_id):
            return
        result = {'request_id': request_id}
        stream = None
        try:
            if self.lock.locked():
                raise ValueError('Another programme is preparing. Please try again shortly.')
            async with self.lock:
                self.watch.project(self.catalogue,{})
                version=self.watch.index.get(data.get('episode_id'))
                episode = self.watch.quality.preferred(version)[0] if version else self.episodes.get(data.get('episode_id'))
                if not episode or episode.get('blocked'):
                    raise ValueError('Choose an available episode.')
                episode = dict(episode)
                position = float(data.get('start_position') or 0)
                if not math.isfinite(position) or not 0 <= position <= 86400:
                    raise ValueError('Invalid starting position.')
                if position and not episode.get('live'):
                    episode['_start_offset'] = position
                if sum(bool(t.get('browser')) for t in self.tickets.values()) >= 2:
                    raise ValueError('Two browsers are already watching. Close a player first.')
                prepared,episode = await asyncio.to_thread(self.watch.choose,self,data.get('episode_id'),position,locals().get('endpoint',{}).get('profile'))
                ticket = secrets.token_urlsafe(24)
                prepared.update(expires=time.time()+6*3600, endpoint_id='browser')
                base = self.config['public_base'].rstrip('/')
                if prepared['live']:
                    if prepared.get('provider'):
                        fd = await asyncio.to_thread(self.provider.open, prepared['resolved'])
                    else:
                        _, source = await asyncio.to_thread(self.session_stream, episode)
                        fd = await asyncio.to_thread(source.open)
                    stream = BrowserStream(self.private_root / 'browser' / ticket, fd, allow_short=not episode.get('live'))
                    prepared['browser'] = stream
                    self.tickets[ticket] = prepared
                    await stream.ready()
                    result.update(url=base+'/browser/'+ticket+'/index.m3u8', mime='application/vnd.apple.mpegurl', metadata=prepared['_watch_meta'])
                else:
                    self.tickets[ticket] = prepared
                    result.update(url=base+'/media/'+ticket, mime=prepared['mime'], metadata=prepared['_watch_meta'])
        except Exception as exc:
            if stream:
                await stream.close()
            if 'ticket' in locals(): self.tickets.pop(ticket, None)
            result['error'] = str(exc) if isinstance(exc, ValueError) else 'Browser playback could not start. Please try again.'
            LOG.warning('Browser preparation failed: %s', type(exc).__name__)
        await self.api('events/tv_favourites_browser_ready', result)

    async def play(self, data):
        if data.get('endpoint_id') == 'browser':
            await self.play_browser(data)
            return
        if data.get('episode_id') == '__snapshot__' and data.get('endpoint_id') == '__library__':
            self.reload_catalogue();await self.publish();return
        if data.get('episode_id') == '__refresh__' and data.get('endpoint_id') == '__library__':
            self.tasks.append(asyncio.create_task(self.sync_library()))
            return
        if self.lock.locked():
            self.message = 'Another item is preparing. Please wait.'
            await self.publish(); return
        async with self.lock:
            try:
                self.watch.project(self.catalogue,{})
                version=self.watch.index.get(data.get('episode_id'))
                episode = self.watch.quality.preferred(version)[0] if version else self.episodes.get(data.get('episode_id'))
                endpoint = self.endpoints.get(data.get('endpoint_id'))
                if not episode or not endpoint:
                    raise ValueError('Choose an episode and output from the catalogue.')
                if episode.get('blocked'):
                    raise ValueError(episode['blocked'])
                episode = dict(episode)
                position = float(data.get('start_position') or 0)
                if not math.isfinite(position) or not 0 <= position <= 86400:
                    raise ValueError('The starting position must be between 0 and 86400 seconds.')
                if position and episode.get('live'):
                    raise ValueError('Starting positions are available for catch-up episodes only.')
                if position:
                    episode['_start_offset'] = position
                status = await self.endpoint_status(endpoint)
                self.endpoint_states[endpoint['id']] = status
                if not status['available']:
                    raise ValueError(status['status'])
                if status.get('busy') and data.get('replace_current') is not True:
                    raise ValueError('This output is already playing. Confirm replacement in the dashboard.')
                self.message = 'Preparing ' + episode['title'] + '…'
                await self.publish()
                prepared,episode = await asyncio.to_thread(self.watch.choose,self,data.get('episode_id'),position,locals().get('endpoint',{}).get('profile'))
                compatible(prepared['info'], endpoint.get('profile'))
                # Check again after source preparation in case someone started watching meanwhile.
                status = await self.endpoint_status(endpoint)
                if not status['available'] or (status.get('busy') and data.get('replace_current') is not True):
                    raise ValueError('Output changed while preparing. Choose it again to confirm playback.')
                ticket = secrets.token_urlsafe(24)
                prepared['expires'] = time.time() + 6 * 3600
                prepared['endpoint_id'] = endpoint['id']
                self.tickets = {k:v for k,v in self.tickets.items() if v['expires'] > time.time()}
                self.tickets[ticket] = prepared
                url = self.config['public_base'].rstrip('/') + '/media/' + ticket
                if endpoint['transport'] == 'ha':
                    await self.api('services/media_player/play_media', {'entity_id': endpoint['entity_id'],
                                    'media_content_id': url, 'media_content_type': prepared['mime']})
                else:
                    didl = ('<DIDL-Lite xmlns="urn:schemas-upnp-org:metadata-1-0/DIDL-Lite/" '
                            'xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:upnp="urn:schemas-upnp-org:metadata-1-0/upnp/">'
                            '<item id="tv-favourites" parentID="0" restricted="1"><dc:title>' + escape(episode['title']) +
                            '</dc:title><upnp:class>object.item.videoItem</upnp:class><res protocolInfo="http-get:*:' +
                            prepared['mime'] + ':*">' + escape(url) + '</res></item></DIDL-Lite>')
                    if data.get('replace_current') is True and status.get('busy'):
                        await self.soap(endpoint, 'Stop', '<InstanceID>0</InstanceID>')
                        for _ in range(25):
                            stopped = await self.endpoint_status(endpoint)
                            if not stopped.get('available'):
                                raise ValueError('The TV disconnected while stopping its current programme.')
                            if not stopped.get('busy'):
                                break
                            await asyncio.sleep(0.2)
                        else:
                            raise ValueError('The TV has not stopped its current programme yet. Try again shortly.')
                    await self.soap(endpoint, 'SetAVTransportURI', '<InstanceID>0</InstanceID><CurrentURI>' + escape(url) +
                                    '</CurrentURI><CurrentURIMetaData>' + escape(didl) + '</CurrentURIMetaData>')
                    await self.soap(endpoint, 'Play', '<InstanceID>0</InstanceID><Speed>1</Speed>')
                await asyncio.sleep(2)
                status = await self.endpoint_status(endpoint)
                if status.get('status') in ('PLAYING','PAUSED_PLAYBACK','playing','paused'): prepared['_had_playback'] = True
                self.endpoint_states[endpoint['id']] = status
                self.message = ('Playback reported by ' if status.get('busy') else 'Playback requested; not yet confirmed on ') + endpoint['name']
            except Exception as e:
                # Do not expose credential-bearing plugin error strings to logs or HA.
                self.message = str(e) if isinstance(e, ValueError) else 'Playback failed. Check source access and device availability.'
                LOG.warning('Playback request failed: %s', type(e).__name__)
        await self.publish()

    async def media(self, request):
        ticket = self.tickets.get(request.match_info['ticket'])
        if not ticket or ticket['expires'] < time.time():
            raise web.HTTPNotFound()
        headers = {'Content-Type': ticket['mime'], 'transferMode.dlna.org': 'Streaming',
                   'contentFeatures.dlna.org': 'DLNA.ORG_OP=01;DLNA.ORG_CI=0' if not ticket['live'] else 'DLNA.ORG_OP=00;DLNA.ORG_CI=0'}
        if not ticket['live']:
            return web.FileResponse(ticket['path'], headers=headers)
        if request.method == 'HEAD':
            return web.Response(headers=headers)
        if request.headers.get('Range') not in [None, 'bytes=0-']:
            raise web.HTTPRequestRangeNotSatisfiable()
        if self.stream_slots.locked():
            raise web.HTTPServiceUnavailable(text='Both relay slots are in use.')
        async with self.stream_slots:
            fd = None
            try:
                if ticket.get('provider'):
                    fd = await asyncio.to_thread(self.provider.open, ticket['resolved'])
                else:
                    _, stream = await asyncio.to_thread(self.session_stream, ticket['episode'])
                    fd = await asyncio.to_thread(stream.open)
                ticket.setdefault('_active_streams', []).append(fd)
                ticket['_opened_at'] = time.time()
                response = web.StreamResponse(headers=headers)
                await response.prepare(request)
                while True:
                    chunk = await asyncio.to_thread(fd.read, 64 * 1024)
                    if not chunk:
                        break
                    await response.write(chunk)
                await response.write_eof()
                return response
            except (ConnectionError, asyncio.CancelledError, OSError, ValueError):
                return response if 'response' in locals() else web.Response(status=499)
            finally:
                if fd:
                    if fd in ticket.get('_active_streams', []): ticket['_active_streams'].remove(fd)
                    await asyncio.to_thread(fd.close)

    async def release_idle_streams(self):
        for key, ticket in list(self.tickets.items()):
            if ticket.get('browser'):
                stream = ticket['browser']
                if ticket['expires'] <= time.time() or time.time()-stream.last_access > 90:
                    await stream.close()
                    self.tickets.pop(key, None)
                continue
            status = self.endpoint_states.get(ticket.get('endpoint_id'))
            if status and status.get('status') in ('PLAYING','PAUSED_PLAYBACK','playing','paused'):
                ticket['_had_playback'] = True
            age = time.time() - ticket.get('_opened_at', time.time())
            if age < 15: continue
            expired = ticket['expires'] <= time.time()
            idle = status is not None and not status.get('busy')
            # Samsung fetches/preflights before its transport reports PLAYING. Allow
            # startup to complete; an early STOPPED state is not a user stop.
            if not expired and not (idle and (ticket.get('_had_playback') or age > 90)): continue
            for fd in list(ticket.get('_active_streams', [])):
                await asyncio.to_thread(fd.close)
                if fd in ticket['_active_streams']: ticket['_active_streams'].remove(fd)

    def watch_playback(self):
        result={}
        for ticket in sorted(self.tickets.values(),key=lambda t:t.get('_watch_started',0)):
            endpoint=ticket.get('endpoint_id')
            if endpoint=='browser' or not ticket.get('_watch_meta'):continue
            status=self.endpoint_states.get(endpoint,{})
            if not status.get('busy') and ticket.get('_had_playback'):continue
            result[endpoint]={**ticket['_watch_meta'],'position':ticket.get('_watch_position',0),'state':status.get('status','preparing')}
        return result

    async def save_remote_positions(self):
        latest={}
        for ticket in sorted(self.tickets.values(),key=lambda t:t.get('_watch_started',0)):
            if ticket.get('endpoint_id')!='browser' and ticket.get('_watch_id'):latest[ticket.get('endpoint_id')]=ticket
        for ident,ticket in latest.items():
            endpoint=self.endpoints.get(ident);status=self.endpoint_states.get(ident,{})
            if not endpoint or not status.get('busy') or ticket['_watch_meta'].get('live'):continue
            try:
                if endpoint['transport']=='ha':
                    state=await self.api('states/'+endpoint['entity_id']);attrs=state.get('attributes',{})
                    position=float(attrs.get('media_position',0))
                    if state.get('state')=='playing' and attrs.get('media_position_updated_at'):
                        from datetime import datetime
                        position+=max(0,time.time()-datetime.fromisoformat(attrs['media_position_updated_at']).timestamp())
                else:
                    text=await self.soap(endpoint,'GetPositionInfo','<InstanceID>0</InstanceID>')
                    value=re.search(r'<(?:\w+:)?RelTime>([^<]+)',text)
                    if not value:continue
                    parts=value[1].split(':');position=sum(float(v)*factor for v,factor in zip(parts,(3600,60,1)))
                position+=ticket['_watch_meta'].get('start_position',0)
                duration=ticket['_watch_meta'].get('duration_seconds',0)
                if duration:position=min(position,duration)
                ticket['_watch_position']=position
                self.watch.progress.save(ticket['_watch_id'],position,duration)
            except Exception:pass

    async def control(self,data):
        ident=data.get('endpoint_id');action=data.get('action');endpoint=self.endpoints.get(ident)
        candidates=[t for t in self.tickets.values() if t.get('endpoint_id')==ident and t.get('_watch_id')]
        if not endpoint or not candidates or action not in ('pause','resume','stop','seek'):return
        ticket=max(candidates,key=lambda t:t.get('_watch_started',0))
        try:
            await self.save_remote_positions()
            if action=='seek':
                position=float(data.get('position',0))
                if not math.isfinite(position) or not 0<=position<=86400 or ticket['_watch_meta'].get('live'):raise ValueError('Invalid seek position.')
                await self.play({'endpoint_id':ident,'episode_id':ticket['_watch_id'],'start_position':position,'replace_current':True});return
            if endpoint['transport']=='ha':
                service={'pause':'media_pause','resume':'media_play','stop':'media_stop'}[action]
                await self.api('services/media_player/'+service,{'entity_id':endpoint['entity_id']})
            else:
                method={'pause':'Pause','resume':'Play','stop':'Stop'}[action]
                await self.soap(endpoint,method,'<InstanceID>0</InstanceID>'+('<Speed>1</Speed>' if action=='resume' else ''))
            if action=='stop':
                for key,value in list(self.tickets.items()):
                    if value.get('endpoint_id')==ident:
                        for fd in list(value.get('_active_streams',[])):await asyncio.to_thread(fd.close)
                        self.tickets.pop(key,None)
            self.endpoint_states[ident]=await self.endpoint_status(endpoint)
        except Exception:
            self.message='The screen could not complete that control. Check that it is still connected.'
        await self.publish()

    async def monitor(self):
        while True:
            try:
                self.reload_catalogue()
            except Exception:
                LOG.warning('Catalogue update rejected; keeping the last valid library.')
            try:
                pairs = await asyncio.gather(*(self.endpoint_status(e) for e in self.endpoints.values()))
                self.endpoint_states = dict(zip(self.endpoints, pairs))
                await self.save_remote_positions()
                await self.release_idle_streams()
                await self.publish()
            except Exception:
                LOG.warning('Home Assistant status update unavailable.')
            await asyncio.sleep(15)

    async def library_action(self,data):
        request_id=str(data.get('request_id',''))
        if not re.fullmatch(r'[a-zA-Z0-9_-]{16,80}',request_id):return
        result={'request_id':request_id}
        try:
            result.update(await self.alignment.request(self.http,data.get('action'),data))
            if data.get('action') in ('import','favourite'):
                self.reload_catalogue();self.alignment.checked=0
                await self.publish()
        except Exception:result['error']='Library request unavailable. Please try again.'
        await self.api('events/tv_favourites_library_ready',result)

    async def events(self):
        while True:
            try:
                async with self.http.ws_connect(self.config['ha_url'] + '/api/websocket', heartbeat=30) as ws:
                    await ws.receive_json()
                    await ws.send_json({'type':'auth','access_token':self.token})
                    if (await ws.receive_json()).get('type') != 'auth_ok':
                        raise RuntimeError('HA authentication failed')
                    await ws.send_json({'id':1,'type':'subscribe_events','event_type':'tv_favourites_request'})
                    ack = await ws.receive_json()
                    if not ack.get('success'):
                        raise RuntimeError('Event subscription failed')
                    await ws.send_json({'id':2,'type':'subscribe_events','event_type':'tv_favourites_control'})
                    await ws.send_json({'id':3,'type':'subscribe_events','event_type':'tv_favourites_library'})
                    self.connected = True
                    async for msg in ws:
                        if msg.type == aiohttp.WSMsgType.TEXT:
                            event = json.loads(msg.data)
                            if event.get('type') == 'event':
                                # Only requests carrying an authenticated HA user context are accepted.
                                payload = event['event']
                                if payload.get('context', {}).get('user_id'):
                                    handler={'tv_favourites_control':self.control,'tv_favourites_library':self.library_action,'tv_favourites_request':self.play}.get(payload.get('event_type'))
                                    if handler is None:continue
                                    task = asyncio.create_task(handler(payload.get('data', {})))
                                    self.tasks.append(task)
                                    self.tasks = [t for t in self.tasks if not t.done()]
            except Exception:
                LOG.warning('HA event connection unavailable; retrying.')
            finally:
                self.connected = False
            await asyncio.sleep(5)

    async def start(self, app):
        self.http = aiohttp.ClientSession()
        self.tasks.extend([asyncio.create_task(self.watch_guide.run()),asyncio.create_task(self.events()), asyncio.create_task(self.monitor()), asyncio.create_task(self.periodic_library()), asyncio.create_task(self.periodic_guide())])

    async def stop(self, app):
        for ticket in self.tickets.values():
            if ticket.get('browser'): await ticket['browser'].close()
        for t in self.tasks: t.cancel()
        await asyncio.gather(*self.tasks, return_exceptions=True)
        await self.http.close()


def main():
    p = argparse.ArgumentParser(); p.add_argument('--config', default='settings.json'); args = p.parse_args()
    config = json.loads(Path(args.config).read_text())
    logging.basicConfig(level=logging.INFO)
    # Streamlink plugins may include URLs or authentication messages in logs.
    logging.getLogger('streamlink').setLevel(logging.CRITICAL)
    bridge = Bridge(config)
    app = web.Application(); app.router.add_get('/media/{ticket}', bridge.media)
    app.router.add_get('/browser/{ticket}/{filename}', lambda r: browser_media(bridge, r))
    app.router.add_delete('/browser/{ticket}/{filename}', lambda r: browser_media(bridge, r))
    app.router.add_options('/browser/{ticket}/{filename}', lambda r: web.Response(status=204))
    async def show_logo(request):
        ident=request.match_info['image']
        if not re.fullmatch(r'[a-f0-9]{20}\.png',ident):raise web.HTTPNotFound()
        path=bridge.private_root/'show-logos'/ident
        if not path.is_file():raise web.HTTPNotFound()
        return web.FileResponse(path)
    app.router.add_get('/static/show-logos/{image}',show_logo)
    app.router.add_post('/browser/{ticket}/progress',lambda r: browser_media(bridge,r))
    async def card(request):
        return web.FileResponse(Path(__file__).parent / 'tv-favourites-card.js', headers={'Content-Type': 'text/javascript'})
    async def static_headers(request, response):
        if request.path.startswith(('/static/', '/browser/', '/media/')):
            response.headers['Access-Control-Allow-Origin'] = config.get('frontend_origin', 'http://192.168.0.146:8123')
            response.headers['Access-Control-Allow-Methods'] = 'GET, HEAD, POST, DELETE, OPTIONS'
            response.headers['Access-Control-Allow-Headers'] = 'Range, Content-Type'
            response.headers['Vary'] = 'Origin'
    app.router.add_get('/static/tv-favourites-card.js', card)
    app.router.add_get('/static/hls.min.js', lambda r: web.FileResponse(Path(__file__).parent / 'hls.min.js', headers={'Content-Type':'text/javascript'}))
    app.router.add_static('/static/artwork', Path(__file__).parent / 'artwork', show_index=False)
    app.on_response_prepare.append(static_headers)
    app.on_startup.append(bridge.start); app.on_cleanup.append(bridge.stop)
    web.run_app(app, host=config['bind'], port=config['port'], access_log=None, shutdown_timeout=5)

if __name__ == '__main__': main()
