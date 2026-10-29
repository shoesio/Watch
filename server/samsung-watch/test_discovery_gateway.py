import json
from unittest.mock import patch
from test_server import GatewayTests

class DiscoveryGatewayTests(GatewayTests):
 async def test_private_favourites_do_not_write_provider_catalogue(self):
  group=self.gateway.library()[0]
  response=await self.client.post('/api/favourite',headers=self.headers,json={'id':group['id'],'favourite':False})
  self.assertEqual(response.status,200)
  self.assertFalse(self.gateway.library()[0]['favourite'])
  self.assertTrue(self.bridge.catalogue['programmes'][0]['favourite'])
  self.assertEqual((await self.client.post('/api/favourite',json={'id':group['id'],'favourite':True})).status,401)

 async def test_search_result_import_preserves_samsung_quality_and_is_playable(self):
  raw={'id':'discovered','title':'New Programme','provider':'BBC iPlayer','provider_id':'bbc','episodes':[{'id':'new_ep','title':'Episode','kind':'plugin','quality':'best','season':1,'episode_number':1}]}
  def load(ref):self.gateway.discovery.imported[ref]={'programme':raw,'checked_at':1};return raw
  with patch.object(self.gateway.discovery,'import_show',side_effect=load):
   response=await self.client.post('/api/import',headers=self.headers,json={'ref':'bbc:abc'})
  self.assertEqual(response.status,200);data=await response.json()
  self.assertIn('new_ep',self.bridge.episodes)
  self.assertNotEqual(self.bridge.episodes['new_ep']['quality'],'best')
  episodes=await (await self.client.get('/api/episodes/'+data['id'],headers=self.headers)).json()
  self.assertEqual(episodes['total'],1)
  await self.client.post('/api/favourite',headers=self.headers,json={'id':data['id'],'favourite':True})
  self.gateway.discovery.imported={}
  self.assertTrue(any(p['title']=='New Programme' for p in self.gateway.library()))

 async def test_search_snapshot_is_stable_and_local_title_wins(self):
  remote={'id':'discover_abc','discovery_ref':'bbc:abc','title':'Found','description':'Synopsis','artwork':'https://ichef.bbci.co.uk/image.jpg','brands':[{'id':'bbc','name':'BBC iPlayer'}],'genres':['Comedy']}
  with patch.object(self.gateway.discovery,'search',return_value={'programmes':[remote],'status':{}}):
   response=await self.client.get('/api/suggestions?mode=search&q=Found&size=4',headers=self.headers)
  data=await response.json();self.assertNotIn('SECRET',json.dumps(data));self.assertEqual(data['total'],1);self.assertTrue(data['items'][0]['image'])
  with patch.object(self.gateway.discovery,'search',side_effect=AssertionError('Must reuse snapshot')):
   again=await (await self.client.get('/api/suggestions?snapshot='+data['snapshot']+'&size=4',headers=self.headers)).json()
  self.assertEqual(data['items'],again['items'])

 async def test_off_air_only_hides_time_valid_holding_slate(self):
  import time
  now=time.time();self.gateway.bbc_schedules={'bbcone':{'_schedule':[{'title':'This is BBC One','start':now-10,'end':now+60}]}}
  items=self.gateway.library()
  self.assertFalse(any(p['title']=='BBC One' for p in items))
  self.gateway.bbc_schedules={'bbcone':{'_schedule':[{'title':'This is BBC One','start':now-100,'end':now-50}]}}
  self.assertTrue(any(p['title']=='BBC One' for p in self.gateway.library()))

 async def test_progress_keeps_description_and_personal_timestamp(self):
  p=self.bridge.catalogue['programmes'][0];p['description']='Real synopsis';p['episodes'][0]['duration_seconds']=1000
  self.gateway.progress.save('c4_ep',200,1000)
  group=next(g for g in self.gateway.library() if g['title']=='Example Show')
  self.assertEqual(group['description'],'Real synopsis');self.assertEqual(group['progress'],20)
  self.assertGreater(group['updated_at'],0)
