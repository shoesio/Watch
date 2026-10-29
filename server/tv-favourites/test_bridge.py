"""Playback guards and real media HTTP behaviour; does not control a physical TV."""
import copy
import io
from types import SimpleNamespace
import json
import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch
from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer
from bridge import Bridge, compatible

class GuardTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        (root/'token').write_text('test-only')
        catalogue = {'programmes':[{'id':'fixture','title':'Test programme','episodes':[{'id':'reference_40s','title':'Reference','kind':'http','url':'https://example.invalid/test.mp4'},{'id':'graham_s34e05','title':'Catch-up','kind':'plugin','url':'https://www.bbc.co.uk/iplayer/episode/m00336tm'}]}], 'endpoints':[{'id':'small_samsung','name':'Test Samsung','transport':'dlna','profile':'samsung_legacy','avtransport_url':'http://127.0.0.1/test'},{'id':'apple_tv','name':'Test output','transport':'ha','entity_id':'media_player.test','profile':'h264'}]}
        (root/'catalogue.json').write_text(json.dumps(catalogue))
        self.bridge = Bridge({'catalogue':str(root/'catalogue.json'),'cache_dir':str(root/'cache'),
                              'ha_token_file':str(root/'token'),'private_root':str(root)})
        self.bridge.publish = AsyncMock()
        self.bridge.prepare = lambda _: self.fail('Preparation must not start for rejected requests')
    def tearDown(self): self.tmp.cleanup()

    def test_catalogue_reload_adds_episode_without_restart(self):
        path = Path(self.bridge.config['catalogue'])
        data = json.loads(path.read_text())
        data['programmes'][0]['episodes'].append(dict(data['programmes'][0]['episodes'][0], id='new_episode'))
        path.write_text(json.dumps(data))
        os.utime(path, ns=(path.stat().st_atime_ns, self.bridge.catalogue_stamp+1000000))
        self.bridge.reload_catalogue()
        self.assertIn('new_episode',self.bridge.episodes)

    def test_invalid_catalogue_reload_preserves_existing_library(self):
        path = Path(self.bridge.config['catalogue'])
        data = json.loads(path.read_text())
        data['programmes'][0]['episodes'].append(data['programmes'][0]['episodes'][0])
        path.write_text(json.dumps(data))
        os.utime(path, ns=(path.stat().st_atime_ns, self.bridge.catalogue_stamp+1000000))
        before = self.bridge.catalogue
        with self.assertRaises(ValueError):self.bridge.reload_catalogue()
        self.assertIs(self.bridge.catalogue,before)

    async def test_streaming_episode_reads_only_probe_buffer(self):
        class Source(io.BytesIO):
            consumed = 0
            def read(self, size=-1):
                data = super().read(size)
                self.consumed += len(data)
                return data
        source = Source(b'x' * (2 * 1024 * 1024))
        self.bridge.session_stream = lambda _: (None, SimpleNamespace(open=lambda:source))
        episode = dict(self.bridge.episodes['reference_40s'], delivery='relay')
        with patch('bridge.probe', return_value={'format':{'format_name':'mpegts'}}):
            result = Bridge.prepare(self.bridge, episode)
        self.assertTrue(result['live'])
        self.assertEqual(source.consumed, 512 * 1024)
        self.assertEqual(list(self.bridge.cache.iterdir()), [])

    async def test_provider_preparation_is_bounded_and_private(self):
        source = io.BytesIO(b'x' * (2 * 1024 * 1024))
        resolved = {'private_authorization': 'not-for-ha'}
        self.bridge.provider = SimpleNamespace(resolve=lambda _: resolved, open=lambda *args, **kwargs: source)
        with patch('bridge.probe', return_value={'format':{'format_name':'mpegts'}}):
            result = Bridge.prepare(self.bridge, {'id':'provider_episode','kind':'provider'})
        self.assertTrue(result['provider'])
        self.assertIs(result['resolved'], resolved)
        self.assertTrue(source.closed)
        self.assertEqual(list(self.bridge.cache.iterdir()), [])

    async def test_catalogue_publish_excludes_source_credentials(self):
        self.bridge.config['public_base'] = 'http://127.0.0.1:8109'
        self.bridge.episodes['reference_40s']['secret'] = 'never-publish'
        self.bridge.api = AsyncMock()
        await Bridge.publish(self.bridge)
        public = self.bridge.api.call_args.args[1]
        self.assertNotIn('never-publish',json.dumps(public))
        self.assertNotIn('https://example.invalid',json.dumps(public))

    async def test_stopped_tv_releases_only_its_relay(self):
        stopped = SimpleNamespace(close=lambda: None)
        watching = SimpleNamespace(close=lambda: self.fail('An active output must be left alone'))
        self.bridge.tickets = {'one':{'expires':time.time()+60,'endpoint_id':'small_samsung','_opened_at':time.time()-20,'_had_playback':True,'_active_streams':[stopped]},'two':{'expires':time.time()+60,'endpoint_id':'apple_tv','_opened_at':time.time()-20,'_had_playback':True,'_active_streams':[watching]}}
        self.bridge.endpoint_states = {'small_samsung':{'busy':False},'apple_tv':{'busy':True}}
        await self.bridge.release_idle_streams()
        self.assertEqual(self.bridge.tickets['one']['_active_streams'], [])
        self.assertEqual(self.bridge.tickets['two']['_active_streams'], [watching])

    async def test_samsung_preflight_is_not_treated_as_a_stop(self):
        pending = SimpleNamespace(close=lambda: self.fail('Preflight must not interrupt startup'))
        self.bridge.tickets = {'pending':{'expires':time.time()+60,'endpoint_id':'small_samsung','_opened_at':time.time()-20,'_active_streams':[pending]}}
        self.bridge.endpoint_states = {'small_samsung':{'busy':False,'status':'STOPPED'}}
        await self.bridge.release_idle_streams()
        self.assertEqual(self.bridge.tickets['pending']['_active_streams'],[pending])

    async def test_invalid_start_position_does_not_prepare(self):
        await self.bridge.play({'episode_id':'reference_40s','endpoint_id':'small_samsung','start_position':-5})
        self.assertIn('starting position',self.bridge.message)

    async def test_unknown_episode_does_not_prepare(self):
        await self.bridge.play({'episode_id':'bogus','endpoint_id':'apple_tv'})
        self.assertIn('Choose an episode', self.bridge.message)

    async def test_busy_output_requires_confirmation(self):
        self.bridge.endpoint_status = AsyncMock(return_value={'available':True,'busy':True})
        await self.bridge.play({'episode_id':'reference_40s','endpoint_id':'apple_tv','replace_current':False})
        self.assertIn('already playing', self.bridge.message)

    async def test_confirmed_dlna_replacement_stops_before_setting_uri(self):
        self.bridge.config['public_base'] = 'http://127.0.0.1:8109'
        self.bridge.endpoint_status = AsyncMock(side_effect=[
            {'available':True,'busy':True,'status':'PLAYING'},
            {'available':True,'busy':True,'status':'PLAYING'},
            {'available':True,'busy':False,'status':'STOPPED'},
            {'available':True,'busy':True,'status':'PLAYING'}])
        self.bridge.prepare = lambda _: {'live':False,'mime':'video/mp4','info':{'streams':[
            {'codec_type':'video','codec_name':'h264','width':960,'height':540,'level':31,'avg_frame_rate':'25/1'}]}}
        self.bridge.soap = AsyncMock(return_value='')
        with patch('bridge.asyncio.sleep', new=AsyncMock()):
            await self.bridge.play({'episode_id':'reference_40s','endpoint_id':'small_samsung','replace_current':True})
        self.assertEqual([c.args[1] for c in self.bridge.soap.call_args_list], ['Stop','SetAVTransportURI','Play'])
        self.assertIn('Playback reported',self.bridge.message)

    async def test_unavailable_output_does_not_prepare(self):
        self.bridge.endpoint_status = AsyncMock(return_value={'available':False,'status':'unreachable'})
        await self.bridge.play({'episode_id':'reference_40s','endpoint_id':'small_samsung'})
        self.assertEqual(self.bridge.message, 'unreachable')

    async def test_blocked_source_does_not_prepare(self):
        self.bridge.episodes['graham_s34e05']['blocked'] = 'Connect your BBC account first.'
        await self.bridge.play({'episode_id':'graham_s34e05','endpoint_id':'apple_tv'})
        self.assertIn('BBC account', self.bridge.message)

    async def test_media_head_range_and_expiry(self):
        path = Path(self.tmp.name)/'reference.mp4';path.write_bytes(b'0123456789')
        self.bridge.tickets['valid']={'path':path,'live':False,'mime':'video/mp4','expires':time.time()+60}
        self.bridge.tickets['expired']={'expires':time.time()-1}
        app=web.Application();app.router.add_get('/media/{ticket}',self.bridge.media)
        async with TestClient(TestServer(app)) as client:
            r=await client.head('/media/valid');self.assertEqual(r.status,200);self.assertEqual(r.headers['Content-Length'],'10');self.assertEqual(await r.read(),b'')
            r=await client.get('/media/valid',headers={'Range':'bytes=3-6'});self.assertEqual(r.status,206);self.assertEqual(r.headers['Content-Range'],'bytes 3-6/10');self.assertEqual(await r.read(),b'3456')
            self.assertEqual((await client.get('/media/expired')).status,404)
            self.assertEqual((await client.get('/media/unknown')).status,404)

    def test_legacy_profile_rejects_4k_and_60fps(self):
        info={'streams':[{'codec_type':'video','width':1920,'height':1080,'avg_frame_rate':'30/1','level':41}]}
        compatible(info,'samsung_legacy')
        compatible({'streams':[{'codec_type':'video','width':1280,'height':720,'avg_frame_rate':'50/1','level':32}]},'samsung_legacy')
        for patch in [{'height':2160},{'avg_frame_rate':'60/1'},{'level':51}]:
            bad=copy.deepcopy(info);bad['streams'][0].update(patch)
            with self.assertRaises(ValueError):compatible(bad,'samsung_legacy')

if __name__=='__main__': unittest.main()
