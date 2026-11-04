"""Authenticated Samsung adapter: exact session binding and private revisioned queues."""
import asyncio,json,unittest
from unittest.mock import Mock
import test_server as fixtures
from playback_features import source_key

class PlaybackAdapterTests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp=fixtures.GatewayTests.asyncSetUp
    asyncTearDown=fixtures.GatewayTests.asyncTearDown

    def numbered(self):
        programmes=self.bridge.catalogue['programmes']
        programmes[0]['episodes']=[dict(programmes[0]['episodes'][0],id='one',season='1',episode_number=1,duration_seconds=600,skip_markers=[{'kind':'intro','start':10,'end':30}]),
            dict(programmes[0]['episodes'][0],id='two',season='1',episode_number=2),
            dict(programmes[0]['episodes'][0],id='three',season='2',episode_number=1)]
        self.bridge.catalogue['programmes']=[programmes[0]]
        rows=self.gateway.feature_rows()
        return rows

    async def get(self,path):return await self.client.get('/api/playback/'+path,headers=self.headers)
    async def post(self,path,data):return await self.client.post('/api/playback/'+path,headers=self.headers,json=data)

    async def test_authentication_and_safe_metadata_no_preparation(self):
        self.numbered();self.bridge.prepare=Mock(side_effect=AssertionError('No preparation'))
        for path in ['capabilities','up-next?episode_id=one','queue','features?episode_id=one']:
            self.assertEqual((await self.client.get('/api/playback/'+path)).status,401)
        data=await (await self.get('up-next?episode_id=one')).json()
        self.assertEqual([e['id'] for e in data['items']],['two','three'])
        self.assertNotIn('SECRET',json.dumps(data));self.assertNotIn('signed-secret',json.dumps(data))
        self.assertTrue(data['items'][0]['thumbnail'] in self.gateway.art)
        self.bridge.prepare.assert_not_called()
        self.assertEqual((await self.get('up-next?episode_id=three')).status,200)
        self.assertIsNone((await (await self.get('up-next?episode_id=three')).json())['next_episode'])

    async def test_owned_exact_source_ticket_and_version_binding(self):
        self.numbered();source=self.bridge.catalogue['programmes'][0]['episodes'][0]
        prepared={'info':{},'_episode_id':'one'}
        meta=self.gateway.bind_playback_features(prepared,source,'Channel 4')
        self.bridge.tickets['owned']=prepared;self.gateway.current_ticket='owned'
        path='features?episode_id=one&ticket=owned&source_key='+meta['source_key']
        self.assertEqual((await self.get(path)).status,200)
        data=await (await self.get(path)).json();self.assertEqual(data['skip_markers'][0]['end'],30)
        self.assertEqual((await self.get(path+'&version_id=guessed')).status,409)
        self.assertEqual((await self.get(path.replace(meta['source_key'],'wrong'))).status,409)
        self.assertEqual((await self.get(path.replace('ticket=owned','ticket=other'))).status,404)
        self.assertEqual((await self.get(path.replace('episode_id=one','episode_id=two'))).status,404)
        self.assertEqual((await self.get('features?episode_id=one')).status,404)
        self.assertNotIn('SECRET',json.dumps(data));self.assertNotIn('signed-secret',json.dumps(data))

    async def test_queue_persistence_completion_conflicts_and_unavailable(self):
        self.numbered()
        q=await (await self.post('queue',{'episode_id':'one','expected_revision':0,'autoplay':True})).json()
        self.assertEqual(q['revision'],1);self.assertEqual([e['id'] for e in q['items']],['two','three'])
        self.assertEqual(self.gateway.queue_path.stat().st_mode&0o777,0o600)
        self.assertEqual((await self.post('queue/advance',{'completed_episode_id':'one','expected_revision':1})).status,409)
        self.gateway.progress.save('one',600,600,True)
        # A successor disappears before completion; advance must prune it.
        self.bridge.catalogue['programmes'][0]['episodes']=[e for e in self.bridge.catalogue['programmes'][0]['episodes'] if e['id']!='two']
        data={'completed_episode_id':'one','expected_revision':1}
        results=await asyncio.gather(self.post('queue/advance',data),self.post('queue/advance',data))
        self.assertEqual(sorted(r.status for r in results),[200,409])
        q=await (await self.get('queue')).json();self.assertEqual(q['current']['id'],'three')
        self.assertEqual(q['revision'],2);self.assertTrue(q['autoplay'])
        self.assertEqual((await self.post('queue',{'episode_id':'one','expected_revision':1})).status,409)
        self.gateway.progress.save('three',600,600,True)
        q=await (await self.post('queue/advance',{'completed_episode_id':'three','expected_revision':2})).json()
        self.assertIsNone(q['current']);self.assertEqual(q['items'],[])

    async def test_new_source_clears_old_feature_lookup(self):
        self.numbered();source=self.bridge.catalogue['programmes'][0]['episodes'][0]
        prepared={'info':{},'_episode_id':'one'};meta=self.gateway.bind_playback_features(prepared,source,'Channel 4')
        self.bridge.tickets['owned']=prepared;self.gateway.current_ticket='owned'
        def replace(*args):
            self.gateway.current_ticket=None
            return {'status':'available','skip_markers':[],'chapters':[]}
        self.gateway.features.get=replace
        self.assertEqual((await self.get('features?episode_id=one&ticket=owned&source_key='+meta['source_key'])).status,409)
