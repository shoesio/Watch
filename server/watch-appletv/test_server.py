import asyncio,hashlib,json,tempfile,time,unittest
from pathlib import Path
from types import SimpleNamespace
from aiohttp.test_utils import TestClient,TestServer
from server import Gateway,stream_quality
from quality_policy import apple_episode,configure_bridge

class Tests(unittest.IsolatedAsyncioTestCase):
 async def asyncSetUp(self):
  self.temp=tempfile.TemporaryDirectory()
  self.gateway=Gateway({'private_root':self.temp.name,'public_base':'http://127.0.0.1:8115'},SimpleNamespace(watch_guide=SimpleNamespace(run=self.idle)))
  self.client=TestClient(TestServer(self.gateway.app()));await self.client.start_server()
 async def idle(self):await asyncio.Future()
 async def asyncTearDown(self):await self.client.close();self.temp.cleanup()
 async def pair(self,code='12345678'):
  self.gateway.write('pairing.json',{'hash':hashlib.sha256(code.encode()).hexdigest(),'expires':time.time()+60})
  response=await self.client.post('/pair',json={'code':code});return (await response.json())['token']
 async def test_requires_pairing(self):
  r=await self.client.get('/library');self.assertEqual(r.status,401)
 async def test_pair_is_single_use(self):
  token=await self.pair();self.assertGreater(len(token),32)
  r=await self.client.post('/pair',json={'code':'12345678'});self.assertEqual(r.status,401)
  self.assertNotIn(token,(self.gateway.root/'devices.json').read_text())
 async def test_expired_code(self):
  self.gateway.write('pairing.json',{'hash':hashlib.sha256(b'12345678').hexdigest(),'expires':0})
  r=await self.client.post('/pair',json={'code':'12345678'});self.assertEqual(r.status,401)
 async def test_pair_rate_limit(self):
  for _ in range(5):await self.client.post('/pair',json={'code':'bad'})
  r=await self.client.post('/pair',json={'code':'bad'});self.assertEqual(r.status,429)
 async def test_device_owns_job(self):
  first=await self.pair();second=await self.pair('87654321')
  owner=self.gateway.read('devices.json',{})[hashlib.sha256(first.encode()).hexdigest()]
  self.gateway.jobs['sample']={'state':'preparing','_device':owner,'_created':time.time()}
  r=await self.client.get('/prepare/sample',headers={'Authorization':'Bearer '+second});self.assertEqual(r.status,404)
  r=await self.client.delete('/prepare/sample',headers={'Authorization':'Bearer '+second});self.assertEqual(r.status,204);self.assertIn('sample',self.gateway.jobs)
  r=await self.client.get('/prepare/sample',headers={'Authorization':'Bearer '+first});self.assertEqual(await r.json(),{'state':'preparing'})
 async def test_unknown_stream_is_not_available(self):
  r=await self.client.get('/stream/unknown/index.m3u8');self.assertEqual(r.status,404)
 async def test_invalid_position_never_saved(self):
  token=await self.pair();device=self.gateway.read('devices.json',{})[hashlib.sha256(token.encode()).hexdigest()]
  self.gateway.sessions['test']={'device':device,'prepared':{'_watch_meta':{'live':False}},'stream':None,'seen':time.time()}
  r=await self.client.post('/session/test',headers={'Authorization':'Bearer '+token},json={'position':-1});self.assertEqual(r.status,400)

 async def test_finite_source_resume_uses_native_seek(self):
  meta={'id':'episode','live':False,'start_position':180,'duration_seconds':600,'quality':'HD'}
  prepared={'live':False,'path':Path(self.temp.name)/'video.mp4','_watch_meta':meta}
  self.gateway.bridge.watch=SimpleNamespace(choose=lambda *args:(prepared,{}))
  self.gateway.jobs['job']={'state':'preparing','_device':'test','_created':time.time()}
  await self.gateway.worker('job','episode',180,'test')
  result=self.gateway.jobs['job']
  self.assertEqual(result['state'],'ready');self.assertEqual(result['initial_seek'],180)
  self.assertEqual(result['metadata']['start_position'],0)
  self.assertEqual(len(self.gateway.sessions),1)
 async def test_cancelled_job_does_not_create_session(self):
  self.gateway.bridge.watch=SimpleNamespace(choose=lambda *args: self.fail('Cancelled job should not prepare'))
  await self.gateway.worker('absent','episode',180,'test')
  self.assertEqual(self.gateway.sessions,{})

 async def test_stream_resolution_labels(self):
  for width,height,expected in [(720,576,'SD'),(1024,576,'SD'),(1280,544,'HD'),(1280,720,'HD'),(1920,1080,'HD'),(2560,1440,'HD'),(3840,1600,'UHD'),(3840,2160,'UHD'),(0,0,None)]:
   with self.subTest(width=width,height=height):self.assertEqual(stream_quality(width,height),expected)
 async def test_quality_uses_probed_stream_not_library_label(self):
  meta={'id':'episode','live':False,'quality':'HD'}
  prepared={'live':False,'path':Path(self.temp.name)/'video.mp4','_watch_meta':meta,'info':{'streams':[{'codec_type':'video','width':3840,'height':2160}]}}
  self.gateway.bridge.watch=SimpleNamespace(choose=lambda *args:(prepared,{}))
  self.gateway.jobs['job']={'state':'preparing','_device':'test','_created':time.time()}
  await self.gateway.worker('job','episode',0,'test')
  result=self.gateway.jobs['job']['metadata']
  self.assertEqual(result['quality'],'UHD');self.assertEqual(result['stream_width'],3840);self.assertEqual(result['stream_height'],2160)

 async def test_apple_streamlink_policy_leaves_catalogue_intact(self):
  original={'kind':'plugin','quality':'720p,480p','id':'sample'}
  self.assertEqual(apple_episode(original)['quality'],'best')
  self.assertEqual(original['quality'],'720p,480p')
  self.assertEqual(apple_episode({'kind':'provider','quality':'720p'})['quality'],'720p')
 async def test_policy_calls_original_streamlink_with_best(self):
  class Base:
   def session_stream(self,episode):return episode['quality']
  tv=configure_bridge(Base)()
  self.assertEqual(tv.session_stream({'kind':'plugin','quality':'720p'}),'best')

 async def test_favourites_require_pairing(self):
  response=await self.client.post('/favourites',json={'id':'a'*20,'favourite':True})
  self.assertEqual(response.status,401)
 async def test_favourite_is_local_persistent_override(self):
  from unittest.mock import patch
  token=await self.pair();headers={'Authorization':'Bearer '+token}
  self.gateway.bridge=SimpleNamespace(watch=SimpleNamespace(index={}),catalogue={'programmes':[]})
  def projected():return [{'id':'a'*20,'title':'Show','live':False,'episodes':[],'provider_favourite':True,'favourite':self.gateway.read('favourites.json',{}).get('a'*20,True)}]
  with patch.object(self.gateway,'project',side_effect=projected):
   response=await self.client.post('/favourites',json={'id':'a'*20,'favourite':False},headers=headers)
   self.assertEqual(response.status,200);p=(await response.json())['programmes'][0]
   self.assertFalse(p['favourite']);self.assertTrue(p['provider_favourite'])
   self.assertIs(self.gateway.read('favourites.json',{})['a'*20],False)
   response=await self.client.post('/favourites',json={'id':'a'*20,'favourite':True},headers=headers)
   self.assertEqual(response.status,200);self.assertTrue((await response.json())['programmes'][0]['favourite'])
 async def test_favourite_rejects_invalid_value_and_unknown_title(self):
  from unittest.mock import patch
  token=await self.pair();headers={'Authorization':'Bearer '+token}
  response=await self.client.post('/favourites',json={'id':'a'*20,'favourite':'yes'},headers=headers)
  self.assertEqual(response.status,400)
  with patch.object(self.gateway,'project',return_value=[]):
   response=await self.client.post('/favourites',json={'id':'a'*20,'favourite':True},headers=headers)
   self.assertEqual(response.status,404)
  self.assertFalse((self.gateway.root/'favourites.json').exists())

if __name__=='__main__':unittest.main()
