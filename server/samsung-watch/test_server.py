"""Gateway authentication, redaction, grouping and cancellation regression checks."""
import asyncio
import copy
import json
import tempfile
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock
from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer
from server import Gateway, stream_spec

class GatewayTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.key = 'test-device-scoped-key-' + 'x' * 32
        (self.root / 'key').write_text(self.key)
        e = {'id':'c4_ep', 'title':'Series 1: Episode 1', 'kind':'provider', 'provider_token':'SECRET',
             'url':'https://private.invalid/signed-secret', 'thumbnail':'https://ic.c4assets.com/image.jpg'}
        p = {'id':'c4_show', 'title':'Example Show', 'provider':'Channel 4', 'favourite':True,
             'artwork':'https://ic.c4assets.com/show.jpg', 'episodes':[e]}
        p2 = copy.deepcopy(p); p2.update(id='u_show', provider='U', title='Example Show!')
        p2['episodes'] = [dict(e, id='u_ep')]
        p3 = copy.deepcopy(p); p3.update(id='bleeped', title='Example Show Bleeped')
        p3['episodes'] = [dict(e, id='bleeped_ep')]
        live = {'id':'bbc_live', 'title':'BBC One', 'provider':'BBC iPlayer', 'episodes':[dict(e,id='live',live=True)]}
        blocked = {'id':'blocked','title':'Blocked','episodes':[dict(e,id='no',blocked='Unavailable')]}
        cat = {'programmes':[p,p2,p3,live,blocked]}
        self.bridge = SimpleNamespace(catalogue=cat, reload_catalogue=lambda:None, tickets={},
            episodes={e['id']:e for p in cat['programmes'] for e in p['episodes']}, media=AsyncMock(side_effect=lambda request:web.Response(text='stream')))
        self.gateway = Gateway({'device_key_file':str(self.root/'key'), 'allowed_clients':['127.0.0.1'], 'guide_enabled':False, 'discovery_enabled':False,
            'public_base':'http://pi:8113', 'bridge_root':str(self.root)}, self.bridge)
        self.client = TestClient(TestServer(self.gateway.app()))
        await self.client.start_server()
        self.headers = {'X-Watch-Key':self.key}
    async def asyncTearDown(self):
        await self.client.close()
        self.tmp.cleanup()
    async def test_client_diagnostics_keep_only_safe_fields(self):
        response=await self.client.post('/api/diagnostic',headers=self.headers,json={'event':'seek','app_version':'0.272','position':120,'playing':True,'waiting':False,'seeking':True,'token':'SECRET','url':'https://private.invalid/signed-secret'})
        self.assertEqual(response.status,200)
        saved=(self.root/'watch-client-events.json').read_text()
        self.assertNotIn('SECRET',saved);self.assertNotIn('private.invalid',saved)
        self.assertEqual(json.loads(saved)[-1]['app_version'],'0.272')
        self.assertEqual((await self.client.post('/api/diagnostic',headers=self.headers,json={'event':'unknown'})).status,400)

    async def test_key_and_tv_address_both_required(self):
        self.assertEqual((await self.client.get('/api/library')).status,401)
        self.assertEqual((await self.client.get('/api/library',headers=self.headers)).status,200)
        self.gateway.settings['allowed_clients'] = ['192.0.2.1']
        self.assertEqual((await self.client.get('/api/library',headers=self.headers)).status,403)
    async def test_artwork_accepts_header_or_image_tag_key(self):
        self.gateway.get_image = lambda image_id,variant='hero':b'jpeg-fixture'
        self.assertEqual((await self.client.get('/art/example',headers=self.headers)).status,200)
        self.assertEqual((await self.client.get('/art/example?key='+self.key)).status,200)
        self.assertEqual((await self.client.get('/art/example')).status,401)
    def test_thumbnail_variant_has_fixed_small_dimensions_and_separate_cache(self):
        from PIL import Image
        import io
        Image.new('RGB',(1600,900),'#456789').save(self.root/'large.png')
        ident=self.gateway.art_id('/local/tv-favourites/large.png')
        thumb=Image.open(io.BytesIO(self.gateway.get_image(ident,'thumb')))
        hero=Image.open(io.BytesIO(self.gateway.get_image(ident)))
        self.assertEqual(thumb.size,(480,270))
        self.assertEqual(hero.size,(1280,720))
    async def test_grouping_and_edition_boundaries(self):
        r = await self.client.get('/api/library?tab=1',headers=self.headers)
        data = await r.json()
        self.assertEqual(data['total'],2)
        self.assertIn('2 episodes', data['items'][0]['meta'])
        self.assertIn('Bleeped',data['items'][1]['title'])
        self.assertNotIn('SECRET',json.dumps(data))
        self.assertNotIn('signed-secret',json.dumps(data))
        group = data['items'][0]['id']
        r = await self.client.get('/api/episodes/'+group,headers=self.headers)
        data = await r.json()
        self.assertEqual(data['total'],2)
        self.assertEqual([e['brands'][0]['name'] for e in data['items']],['Channel 4','U'])
        self.assertNotIn('private.invalid',json.dumps(data))
    async def test_live_and_blocked_items(self):
        data = await (await self.client.get('/api/library?tab=2',headers=self.headers)).json()
        self.assertEqual(data['total'],1)
        self.assertEqual(data['items'][0]['episode_id'],'live')
        self.assertEqual((await self.client.post('/api/prepare',json={'episode_id':'no'},headers=self.headers)).status,400)
    async def test_live_channel_order_and_branding(self):
        original = self.bridge.catalogue['programmes'][3]
        for title in ['BBC News', 'BBC Four', 'BBC Two']:
            self.bridge.catalogue['programmes'].append(dict(original,id=title,title=title))
        data = await (await self.client.get('/api/library?tab=2&size=4',headers=self.headers)).json()
        self.assertEqual([x['title'] for x in data['items']],['BBC One','BBC Two','BBC Four','BBC News'])
        self.assertEqual([x['channel_brand'] for x in data['items']],['bbcone','bbctwo','bbcfour','bbcnews'])
        self.assertTrue(all(x['brands'][0]['id']=='bbc' for x in data['items']))
    async def test_all_channel4_channels_map_to_existing_artwork_and_guide(self):
        original=self.bridge.catalogue['programmes'][3]
        for title in ['Channel 4','E4','More4','Film4','4seven']:
            self.bridge.catalogue['programmes'].append(dict(original,id=title,title=title,provider='Channel 4'))
        self.gateway.guide.get=lambda key:{'now':{'title':'Current '+str(key),'image':'https://ic.c4assets.com/image.jpg'},'next':{'title':'Next show','time':'21:00'}}
        data=await (await self.client.get('/api/library?tab=2',headers=self.headers)).json()
        items=[x for x in data['items'] if x['title']!='BBC One']
        self.assertEqual(len(items),5)
        self.assertTrue(all(x['channel_brand'] and x['guide']['now']['art'] for x in items))
    def test_quality_comes_from_actual_video_dimensions(self):
        self.assertEqual(stream_spec({'streams':[{'codec_type':'video','height':720}]})['quality'],'HD')
        self.assertEqual(stream_spec({'streams':[{'codec_type':'video','height':1080}]})['quality'],'HD')
        self.assertEqual(stream_spec({'streams':[{'codec_type':'video','height':576}]})['quality'],'SD')
        self.assertIsNone(stream_spec({'streams':[]})['quality'])
    async def test_brands_follow_provider_on_each_episode_and_series(self):
        data = await (await self.client.get('/api/library?tab=1',headers=self.headers)).json()
        group=data['items'][0]
        self.assertEqual([b['id'] for b in group['brands']],['channel4','u'])
        episodes = await (await self.client.get('/api/episodes/'+group['id'],headers=self.headers)).json()
        self.assertEqual([e['brands'][0]['id'] for e in episodes['items']],['channel4','u'])
        seasons = await (await self.client.get('/api/seasons/'+group['id'],headers=self.headers)).json()
        self.assertTrue(all(s['brands']==group['brands'] for s in seasons['items']))
    async def test_duplicate_episode_uses_measured_winner_and_shared_resume(self):
        p,p2=self.bridge.catalogue['programmes'][:2]
        for programme in (p,p2):
            programme['episodes'][0].update(season=69,episode_number=1,duration_seconds='PT44M')
        self.gateway.progress.save('c4_ep',125,2640)
        group=self.gateway.library()[0]
        listed=await (await self.client.get('/api/episodes/'+group['id'],headers=self.headers)).json()
        self.assertEqual(listed['total'],1)
        ident=listed['items'][0]['id']
        self.assertTrue(ident.startswith('version_'))
        self.assertEqual(listed['items'][0]['resume_seconds'],120)
        calls=[]
        def prepare(episode):
            calls.append(episode)
            height=720 if episode['id']=='u_ep' else 540
            return {'live':True,'info':{'streams':[{'codec_type':'video','height':height,'width':1280,'level':40,'avg_frame_rate':'25/1'}]}}
        self.bridge.prepare=prepare
        job=await (await self.client.post('/api/prepare',json={'episode_id':ident},headers=self.headers)).json()
        await self.gateway.worker
        ready=self.gateway.jobs[job['job']]
        self.assertEqual(len(calls),2)
        self.assertEqual(ready['brands'][0]['id'],'u')
        self.assertEqual(ready['episode_id'],ident)
        self.assertEqual(ready['start_position'],120)
        self.assertEqual(ready['duration_seconds'],2640)
        self.assertEqual(self.bridge.tickets[ready['ticket']]['_episode_id'],ident)
        await self.client.delete('/api/play/'+ready['ticket'],headers=self.headers)
        calls.clear()
        job=await (await self.client.post('/api/prepare',json={'episode_id':ident},headers=self.headers)).json()
        await self.gateway.worker
        self.assertEqual(len(calls),1)
        self.assertEqual(calls[0]['id'],'u_ep')

    async def test_latest_first_and_season_provider_badges(self):
        p,p2=self.bridge.catalogue['programmes'][:2]
        p['episodes']=[dict(p['episodes'][0],id='old',season=2,episode_number=2),dict(p['episodes'][0],id='new',season=12,episode_number=10)]
        p2['episodes']=[dict(p2['episodes'][0],id='u_only',season=1,episode_number=1)]
        group=self.gateway.library()[0]['id']
        data=await (await self.client.get('/api/episodes/'+group,headers=self.headers)).json()
        self.assertEqual([e['id'] for e in data['items']],['new','old','u_only'])
        data=await (await self.client.get('/api/seasons/'+group,headers=self.headers)).json()
        self.assertEqual([e['title'] for e in data['items']],['All series','Series 12','Series 2','Series 1'])
        self.assertEqual([b['id'] for b in data['items'][1]['brands']],['channel4'])
        self.assertEqual([b['id'] for b in data['items'][3]['brands']],['u'])

    async def test_genres_only_contain_populated_sections_and_films_are_independent(self):
        p=self.bridge.catalogue['programmes'][0]
        p['genre']='Comedy'
        film=dict(p,id='film',title='Available Film',genre='Film - Action',favourite=False,recent=False,episodes=[dict(p['episodes'][0],id='film_ep')])
        self.bridge.catalogue['programmes'].append(film)
        data=await (await self.client.get('/api/library?tab=1',headers=self.headers)).json()
        self.assertEqual(data['genres'],['Comedy'])
        data=await (await self.client.get('/api/library?tab=1&genre=Comedy',headers=self.headers)).json()
        self.assertEqual(data['total'],1)
        data=await (await self.client.get('/api/library?tab=3',headers=self.headers)).json()
        self.assertEqual(data['items'][0]['title'],'Available Film')
        self.assertEqual(data['genres'],['Action & adventure'])

    async def test_playback_response_includes_episode_details_and_show_logo(self):
        p=self.bridge.catalogue['programmes'][0]
        episode=p['episodes'][0]
        episode.update(description='Episode synopsis',season=3,episode_number=4)
        self.gateway.show_logo_dir.mkdir()
        group=self.gateway.library()[0]['id']
        (self.gateway.show_logo_dir/(group+'.png')).write_bytes(b'fixture')
        self.bridge.prepare=lambda episode: {'live':True,'info':{'streams':[{'codec_type':'video','height':720,'width':1280,'level':40,'avg_frame_rate':'25/1'}]}}
        job=await (await self.client.post('/api/prepare',json={'episode_id':episode['id']},headers=self.headers)).json()
        await self.gateway.worker
        ready=self.gateway.jobs[job['job']]
        self.assertEqual(ready['description'],'Episode synopsis')
        self.assertEqual(ready['show_title'],'Example Show')
        self.assertEqual(ready['show_logo'],group)
        self.assertEqual(ready['episode_number'],4)
        self.assertNotIn('SECRET',json.dumps(ready))

    async def test_season_selection_filters_episodes(self):
        p = self.bridge.catalogue['programmes'][0]
        p['episodes'][0]['season'] = 1
        p['episodes'].append(dict(p['episodes'][0],id='second',season=2))
        group = (await (await self.client.get('/api/library?tab=1',headers=self.headers)).json())['items'][0]['id']
        seasons = await (await self.client.get('/api/seasons/'+group,headers=self.headers)).json()
        series2 = next(s for s in seasons['items'] if s['title']=='Series 2')
        data = await (await self.client.get('/api/episodes/'+group+'?season='+series2['id'],headers=self.headers)).json()
        self.assertEqual([e['id'] for e in data['items']],['second'])
    async def test_cancelling_inflight_preparation_never_publishes_ticket(self):
        started, finish = threading.Event(), threading.Event()
        def prepare(episode):
            started.set(); finish.wait(5)
            return {'live':True,'info':{'streams':[{'codec_type':'video','codec_name':'h264','height':720,'width':1280,'level':40,'avg_frame_rate':'25/1'}]}}
        self.bridge.prepare = prepare
        data = await (await self.client.post('/api/prepare',json={'episode_id':'c4_ep'},headers=self.headers)).json()
        await asyncio.to_thread(started.wait,2)
        await self.client.delete('/api/prepare/'+data['job'],headers=self.headers)
        finish.set(); await self.gateway.worker
        self.assertEqual(self.bridge.tickets,{})
    async def test_ticket_release_closes_source_and_heartbeat_is_scoped(self):
        closed = threading.Event()
        self.bridge.tickets['own-ticket']={'_active_streams':[SimpleNamespace(close=closed.set)], '_last_seen':0}
        self.gateway.current_ticket = 'own-ticket'
        await self.client.post('/api/play/own-ticket/heartbeat',json={},headers=self.headers)
        self.assertGreater(self.bridge.tickets['own-ticket']['_last_seen'],0)
        await self.client.delete('/api/play/own-ticket',headers=self.headers)
        self.assertTrue(closed.is_set()); self.assertIsNone(self.gateway.current_ticket)
    async def test_playback_resume_heartbeat_and_stop_persist(self):
        from progress_store import ProgressStore
        self.gateway.progress.save('c4_ep',500,1000)
        captured=[]
        def prepare(episode):
            captured.append(episode)
            return {'live':True,'info':{'streams':[{'codec_type':'video','height':720,'width':1280,'level':40,'avg_frame_rate':'25/1'}]}}
        self.bridge.episodes['c4_ep']['duration_seconds']=1000
        self.bridge.prepare=prepare
        job=await (await self.client.post('/api/prepare',json={'episode_id':'c4_ep'},headers=self.headers)).json()
        await self.gateway.worker
        ready=await (await self.client.get('/api/prepare/'+job['job'],headers=self.headers)).json()
        self.assertEqual(captured[0]['_start_offset'],495)
        self.assertEqual(ready['start_position'],495)
        token=ready['ticket']
        await self.client.post('/api/play/'+token+'/heartbeat',json={'position':520},headers=self.headers)
        await self.client.delete('/api/play/'+token,json={'position':525},headers=self.headers)
        self.assertEqual(ProgressStore(self.gateway.progress.path).resume('c4_ep'),520)
    async def test_explicit_restart_and_live_progress_rejection(self):
        for position in [-2,90000,'not a number']:
            r=await self.client.post('/api/prepare',json={'episode_id':'c4_ep','start_position':position},headers=self.headers)
            self.assertEqual(r.status,400)
        r=await self.client.post('/api/prepare',json={'episode_id':'live','start_position':10},headers=self.headers)
        self.assertEqual(r.status,400)
    async def test_reopening_after_crash_releases_old_slot_and_retains_progress(self):
        self.gateway.progress.save('c4_ep',310,1000)
        self.bridge.tickets['old']={'_active_streams':[]}
        self.gateway.current_ticket='old'
        r=await self.client.post('/api/session',json={},headers=self.headers)
        self.assertEqual(r.status,200)
        self.assertIsNone(self.gateway.current_ticket)
        self.assertEqual(self.gateway.progress.resume('c4_ep'),305)
    async def test_progressive_byte_probe_is_ignored_but_finite_range_preserved(self):
        self.bridge.tickets['stream']={'live':True}
        await self.client.get('/media/stream/stream.ts',headers={'Range':'bytes=0-1'})
        self.assertNotIn('Range',self.bridge.media.call_args.args[0].headers)
        self.bridge.tickets['file']={'live':False}
        await self.client.get('/media/file/stream.mp4',headers={'Range':'bytes=100-200'})
        self.assertEqual(self.bridge.media.call_args.args[0].headers['Range'],'bytes=100-200')
        self.bridge.tickets.clear()

if __name__ == '__main__': unittest.main()
