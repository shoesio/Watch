import time,unittest
from types import SimpleNamespace
from unittest.mock import patch
from native_playback import five_channels,five_guide,bbc_media_url,clear_hls,descriptor
import test_server

class NativeRoutes(unittest.TestCase):
 def test_streamlink_audio_suffix_does_not_outweigh_equal_video(self):
  from quality_policy import video_rank
  self.assertEqual(video_rank('720p+a96k'),video_rank('720p_alt'))
  self.assertGreater(video_rank('1080p'),video_rank('720p+a96k'))
  self.assertGreater(video_rank('720p50'),video_rank('720p25'))

 def test_five_only_standard_live_entries_deduped_in_order(self):
  feed={'filters':{'contents':[{'channel':'C7','title':'5USA','live':True},{'channel':'C5CH02','title':'Police','live':True},{'channel':'C5','title':'Channel 5','live':True},{'channel':'C7','title':'5USA','live':True},{'channel':'C6','title':'5STAR','live':False}]}}
  rows=five_channels(feed)
  self.assertEqual([r['live_channel'] for r in rows],['C5','C7'])
  self.assertEqual(rows[0]['episodes'][0]['provider_episode_id'],'C5')
 def test_now_next_boundaries(self):
  result=five_guide({'schedule':[{'tran_s':200,'title':'Next'},{'tran_s':100,'title':'Current'},{'tran_s':300,'title':'Later'}]},150)
  self.assertEqual(result['now']['title'],'Current');self.assertEqual(result['next']['title'],'Next')
 def test_direct_media_address_restrictions(self):
  for raw in ['http://a.bbci.co.uk/a.m3u8','https://bbci.co.uk.evil.test/a.m3u8','https://user@a.bbci.co.uk/a.m3u8','https://a.bbci.co.uk:444/a.m3u8']:
   self.assertFalse(bbc_media_url(raw))
  self.assertTrue(bbc_media_url('https://a.bbci.co.uk/a.m3u8'))
  self.assertTrue(bbc_media_url('https://a.bbci.co.uk:443/a.m3u8'))
 def test_protected_hls_does_not_enter_clear_bbc_path(self):
  self.assertFalse(clear_hls('#EXTM3U\n#EXT-X-KEY:METHOD=SAMPLE-AES,URI="skd://protected"'))
  self.assertFalse(clear_hls('#EXTM3U\n#EXT-X-SESSION-KEY:METHOD=AES-128,URI="key"'))
  self.assertTrue(clear_hls('#EXTM3U\n#EXTINF:4,\nseg.ts'))
 def test_u_and_itv_native_routes_do_not_send_provider_sessions(self):
  for service,ident,extra in [('u','6368585112112',{}),('itv','ITV',{'playlist_url':'https://simulcast.itv.com/playlist/itvonline/ITV','live':True})]:
   source={'id':'ep','title':'Show','provider_id':service,'provider_episode_id':ident,**extra}
   watch=SimpleNamespace(index={'ep':{'sources':[(source,'U' if service=='u' else 'ITVX')]}},quality=SimpleNamespace(rank=lambda p:1),groups=[{'title':'Show','episodes':[{'id':'ep'}]}],brands=lambda n:[])
   _,route,_=descriptor(SimpleNamespace(watch=watch),'ep')
   self.assertEqual(route['provider'],service);self.assertNotIn('token',route);self.assertNotIn('session',route)
 def test_five_descriptor_contains_no_account_session(self):
  ep={'id':'ep','title':'Example','provider_id':'channel5','provider_episode_id':'123-456','live':False}
  meta={'id':'ep','title':'Example','duration_seconds':600}
  watch=SimpleNamespace(index={'ep':{'sources':[(ep,'Channel 5')]}},quality=SimpleNamespace(rank=lambda p:1),groups=[{'title':'Show','episodes':[meta]}],brands=lambda n:[])
  source,route,result=descriptor(SimpleNamespace(watch=watch),'ep')
  self.assertEqual(route,{'provider':'channel5','id':'123-456','live':False});self.assertEqual(result['start_position'],0)

class NativeGateway(unittest.IsolatedAsyncioTestCase):
 asyncSetUp=test_server.Tests.asyncSetUp
 asyncTearDown=test_server.Tests.asyncTearDown
 idle=test_server.Tests.idle
 async def test_native_progress_stays_shared_and_does_not_expose_media(self):
  token=await test_server.Tests.pair(self);headers={'Authorization':'Bearer '+token}
  import hashlib
  owner=self.gateway.read('devices.json',{})[hashlib.sha256(token.encode()).hexdigest()]
  saved=[]
  self.gateway.bridge.watch=SimpleNamespace(progress=SimpleNamespace(save=lambda *args:saved.append(args)))
  self.gateway.sessions['native-test']={'device':owner,'prepared':{'_watch_meta':{'id':'ep','live':False,'duration_seconds':600},'native':True,'delivery':'native-channel5'},'stream':None,'seen':time.time()}
  response=await self.client.post('/session/native-test',headers=headers,json={'position':120,'state':'playing','metrics':{'video_width':1920,'video_height':1080}})
  self.assertEqual(response.status,200);self.assertEqual(saved,[('ep',120.0,600,False)])
  snapshot=self.gateway.read('playback-status.json',{});self.assertEqual(snapshot['quality'],'HD');self.assertEqual(snapshot['delivery'],'native-channel5')
  response=await self.client.get('/stream/native-test/video.mp4');self.assertEqual(response.status,404)

 async def test_native_five_never_opens_relay_and_has_progress_session(self):
  route={'provider':'channel5','id':'C5','live':True};meta={'id':'ep','title':'Channel 5','live':True,'start_position':0}
  self.gateway.jobs['native']={'state':'preparing','_device':'device','_created':time.time()}
  with patch('native_playback.descriptor',return_value=({},route,meta)):
   await self.gateway.worker('native','ep',0,'device',native=True)
  result=self.gateway.jobs['native'];self.assertEqual(result['state'],'ready');self.assertEqual(result['native'],route)
  self.assertIsNone(result['url']);self.assertIsNone(self.gateway.sessions[result['ticket']]['stream'])
 async def test_native_bbc_resume_is_absolute_no_relay(self):
  route={'provider':'bbc','id':'bbc_ep','live':False};meta={'id':'ep','title':'Show','live':False,'start_position':0}
  self.gateway.jobs['native']={'state':'preparing','_device':'device','_created':time.time()}
  with patch('native_playback.descriptor',return_value=({},route,meta)),patch('native_playback.bbc_direct',return_value='https://a.bbci.co.uk/test.m3u8'):
   await self.gateway.worker('native','ep',180,'device',native=True)
  result=self.gateway.jobs['native'];self.assertEqual(result['initial_seek'],180);self.assertEqual(result['metadata']['start_position'],0)
  self.assertIsNone(self.gateway.sessions[result['ticket']]['stream'])
 async def test_unsupported_bbc_returns_to_existing_route(self):
  route={'provider':'bbc','id':'bbc_ep','live':False};meta={'id':'ep','title':'Show','live':False,'start_position':0}
  self.gateway.bridge.watch=SimpleNamespace(choose=lambda *args:({'live':False,'path':'file','_watch_meta':meta},{}))
  self.gateway.jobs['native']={'state':'preparing','_device':'device','_created':time.time()}
  with patch('native_playback.descriptor',return_value=({},route,meta)),patch('native_playback.bbc_direct',return_value=None):
   await self.gateway.worker('native','ep',180,'device',native=True)
  result=self.gateway.jobs['native'];self.assertNotIn('native',result);self.assertTrue(result['url'].endswith('/video.mp4'))
