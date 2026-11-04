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
 def test_channel4_live_requires_client_capability_and_never_routes_vod(self):
  for live,ident in [(True,'C4'),(False,'80485-008'),(True,'invalid')]:
   source={'id':'ep','title':'Four','provider_id':'channel4','provider_episode_id':ident,'live':live}
   watch=SimpleNamespace(index={'ep':{'sources':[(source,'Channel 4')]}},quality=SimpleNamespace(rank=lambda p:1),groups=[{'title':'Four','episodes':[{'id':'ep'}]}],brands=lambda n:[])
   bridge=SimpleNamespace(watch=watch)
   self.assertIsNone(descriptor(bridge,'ep'))
   result=descriptor(bridge,'ep',channel4_live=True)
   if live and ident=='C4':self.assertEqual(result[1],{'provider':'channel4','id':'C4','live':True})
   else:self.assertIsNone(result)
 def test_five_descriptor_contains_no_account_session(self):
  ep={'id':'ep','title':'Example','provider_id':'channel5','provider_episode_id':'123-456','live':False}
  meta={'id':'ep','title':'Example','duration_seconds':600}
  watch=SimpleNamespace(index={'ep':{'sources':[(ep,'Channel 5')]}},quality=SimpleNamespace(rank=lambda p:1),groups=[{'title':'Show','episodes':[meta]}],brands=lambda n:[])
  source,route,result=descriptor(SimpleNamespace(watch=watch),'ep')
  self.assertEqual(route,{'provider':'channel5','id':'123-456','live':False});self.assertEqual(result['start_position'],0)

class BBCVersionBinding(unittest.TestCase):
 def test_actual_mediaselector_version_follows_each_stream(self):
  from quality_policy import bbc_streams_with_versions
  class Plugin:
   def mediaselector(self,pid):yield pid,SimpleNamespace()
   def streams(self,**kwargs):return dict([*self.mediaselector('b1234567'),*self.mediaselector('b7654321')])
  plugin=Plugin();original=plugin.mediaselector
  streams=bbc_streams_with_versions(plugin)
  self.assertEqual(streams['b1234567']._watch_version_id,'b1234567')
  self.assertEqual(streams['b7654321']._watch_version_id,'b7654321')
  self.assertEqual(plugin.mediaselector,original)
 def test_immutable_stream_values_do_not_break_resolution(self):
  from quality_policy import bbc_streams_with_versions
  class Plugin:
   def mediaselector(self,pid):yield 'alias','unchanged'
   def streams(self,**kwargs):return dict(self.mediaselector('b1234567'))
  self.assertEqual(bbc_streams_with_versions(Plugin()),{'alias':'unchanged'})
 def test_invalid_versions_and_url_string_compatibility(self):
  from native_playback import BBCDirectURL
  value=BBCDirectURL('https://a.bbci.co.uk/test.m3u8','b1234567')
  self.assertEqual(str(value),'https://a.bbci.co.uk/test.m3u8');self.assertEqual(value.version_id,'b1234567')
  self.assertIsNone(BBCDirectURL('https://a.bbci.co.uk/test.m3u8','bad/id').version_id)

class BBCPublicMetadata(unittest.TestCase):
 def test_current_replacement_used_without_account_login(self):
  from quality_policy import bbc_public_streams
  from unittest.mock import Mock
  row={'episodes':[{'id':'m0032vwc','versions':[{'id':'m00343ws','kind':'technical-replacement','uhd':True},{'id':'p0plby39','kind':'audio-described'},{'id':'m0033tcl','kind':'signed'}]}]}
  response=Mock();response.json.return_value=row
  plugin=Mock();plugin.session.http.get.return_value=response;stream=SimpleNamespace();plugin.mediaselector.return_value=[('720p50',stream)]
  result=bbc_public_streams(plugin,{'url':'https://www.bbc.co.uk/iplayer/episode/m0032vwc'})
  self.assertEqual(result['720p50']._watch_version_id,'m00343ws');plugin.mediaselector.assert_called_once_with('m00343ws');plugin.login.assert_not_called();plugin.streams.assert_not_called()
 def test_expired_future_and_accessibility_versions_not_selected(self):
  from quality_policy import bbc_public_streams
  from unittest.mock import Mock
  versions=[{'id':'b1234567','availability':{'end':'2000-01-01T00:00:00Z'}},{'id':'b2345678','availability':{'start':'2099-01-01T00:00:00Z'}},{'id':'b3456789','kind':'signed'},{'id':'b4567890','kind':'audio-described'}]
  response=Mock();response.json.return_value={'episodes':[{'id':'m0032vwc','versions':versions}]};plugin=Mock();plugin.session.http.get.return_value=response
  self.assertEqual(bbc_public_streams(plugin,{'url':'https://www.bbc.co.uk/iplayer/episode/m0032vwc'}),{});plugin.mediaselector.assert_not_called()
 def test_non_bbc_or_live_keeps_existing_route(self):
  from quality_policy import bbc_public_streams
  from unittest.mock import Mock
  for episode in [{'url':'https://evil.test/iplayer/episode/m0032vwc'},{'url':'https://www.bbc.co.uk/iplayer/live/bbcone','live':True}]:
   plugin=Mock();self.assertIsNone(bbc_public_streams(plugin,episode));plugin.session.http.get.assert_not_called()

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
 async def test_episode_playlist_response_explicitly_starts_at_requested_origin(self):
  from pathlib import Path
  from tvos_stream import TVStream
  stream=TVStream.__new__(TVStream);stream.live=False;stream.closed=False;stream.directory=Path(self.temp.name)/'episode';stream.directory.mkdir()
  (stream.directory/'index.m3u8').write_text('#EXTM3U\n#EXT-X-PLAYLIST-TYPE:EVENT\n#EXTINF:4,\nsegment000000.ts\n')
  self.gateway.sessions['episode-test']={'device':'d','prepared':{},'stream':stream,'seen':time.time()}
  response=await self.client.get('/stream/episode-test/index.m3u8')
  self.assertEqual(response.status,200);self.assertIn('#EXT-X-START:TIME-OFFSET=0,PRECISE=YES',await response.text())
  self.assertEqual(response.headers['Cache-Control'],'no-store')
  self.gateway.sessions.pop('episode-test')

 async def test_native_four_does_not_open_the_pi_relay(self):
  route={'provider':'channel4','id':'C4','live':True};meta={'id':'ep','title':'Four','live':True,'start_position':0}
  self.gateway.jobs['native']={'state':'preparing','_device':'device','_created':time.time()}
  with patch('native_playback.descriptor',return_value=({},route,meta)) as route_call:
   await self.gateway.worker('native','ep',0,'device',native=True,channel4_live=True)
   route_call.assert_called_once_with(self.gateway.bridge,'ep',channel4_live=True)
  result=self.gateway.jobs['native'];self.assertEqual(result['native'],route)
  self.assertIsNone(self.gateway.sessions[result['ticket']]['stream'])

 async def test_native_bbc_resume_is_absolute_no_relay(self):
  route={'provider':'bbc','id':'bbc_ep','live':False};meta={'id':'ep','title':'Show','live':False,'start_position':0}
  self.gateway.jobs['native']={'state':'preparing','_device':'device','_created':time.time()}
  with patch('native_playback.descriptor',return_value=({},route,meta)),patch('native_playback.bbc_direct',return_value=__import__('native_playback').BBCDirectURL('https://a.bbci.co.uk/test.m3u8','b1234567')):
   await self.gateway.worker('native','ep',180,'device',native=True)
  result=self.gateway.jobs['native'];self.assertEqual(result['metadata']['version_id'],'b1234567');self.assertEqual(result['initial_seek'],180);self.assertEqual(result['metadata']['start_position'],0)
  self.assertIsNone(self.gateway.sessions[result['ticket']]['stream'])
 async def test_unsupported_bbc_returns_to_existing_route(self):
  route={'provider':'bbc','id':'bbc_ep','live':False};meta={'id':'ep','title':'Show','live':False,'start_position':0}
  self.gateway.bridge.watch=SimpleNamespace(choose=lambda *args:({'live':False,'path':'file','_watch_meta':meta},{}))
  self.gateway.jobs['native']={'state':'preparing','_device':'device','_created':time.time()}
  with patch('native_playback.descriptor',return_value=({},route,meta)),patch('native_playback.bbc_direct',return_value=None):
   await self.gateway.worker('native','ep',180,'device',native=True)
  result=self.gateway.jobs['native'];self.assertNotIn('native',result);self.assertTrue(result['url'].endswith('/video.mp4'))
