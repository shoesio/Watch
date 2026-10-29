import copy,json,tempfile,time,unittest
from pathlib import Path
from unittest.mock import AsyncMock
from dashboard_library import DashboardLibrary
from progress_store import ProgressStore
from bridge import Bridge

class ProjectionTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
  a={'id':'bbc','title':'Series 69: Episode 10','season':69,'episode_number':10,'duration_seconds':'PT44M','url':'https://private.invalid/token','kind':'plugin'}
  self.cat={'programmes':[{'id':'bbc-show','title':'Show','provider':'BBC iPlayer','genre':'Comedy','favourite':True,'episodes':[a]}, {'id':'u-show','title':'Show!','provider':'U','episodes':[dict(a,id='u')]}]}
  self.library=DashboardLibrary(self.root,'http://pi')
 def tearDown(self):self.tmp.cleanup()
 def test_deduplication_order_brands_and_credentials(self):
  p=self.library.project(self.cat,{})[0]
  self.assertEqual(len(p['episodes']),1);self.assertEqual(p['genres'],['Comedy'])
  self.assertEqual(p['episodes'][0]['duration_seconds'],2640)
  self.assertEqual(p['episodes'][0]['brands'][0]['id'],'bbc')
  self.assertNotIn('private.invalid',json.dumps(p));self.assertNotIn('url',p['episodes'][0])
 def test_cross_client_progress_is_reloaded_and_records_are_merged(self):
  path=self.root/'samsung-watch-progress.json';first=ProgressStore(path);second=ProgressStore(path)
  first.save('bbc',125,2640);second.save('other',200,500)
  self.assertEqual(first.resume('other'),195)
  p=self.library.project(self.cat,{})[0];self.assertEqual(p['episodes'][0]['resume_seconds'],120)
  self.assertTrue(p['resume_episode'].startswith('version_'))
 def test_films_not_favourited_and_live_guide_artwork(self):
  self.cat['programmes'].append({'id':'film','title':'Film','provider':'Channel 5','genre':'Film - Drama','episodes':[{'id':'film','title':'Film'}]})
  self.cat['programmes'].append({'id':'live','title':'Channel 4','provider':'Channel 4','live_channel':'C4','episodes':[{'id':'live','title':'Channel 4','live':True}]})
  data=self.library.project(self.cat,{'C4':{'now':{'title':'Current programme','image':'https://ic.c4assets.com/current.jpg'}}})
  film=next(p for p in data if p['title']=='Film');self.assertTrue(film['film']);self.assertFalse(film['favourite'])
  live=next(p for p in data if p['live']);self.assertEqual(live['guide']['now']['title'],'Current programme');self.assertTrue(live['channel_logo'].endswith('/channel4.png'))

class ControlTests(unittest.IsolatedAsyncioTestCase):
 async def test_control_requires_our_active_ticket_and_targets_only_selected_tv(self):
  bridge=object.__new__(Bridge)
  bridge.endpoints={'tv':{'id':'tv','transport':'dlna'}};bridge.endpoint_states={};bridge.tickets={};bridge.soap=AsyncMock();bridge.publish=AsyncMock();bridge.save_remote_positions=AsyncMock();bridge.endpoint_status=AsyncMock(return_value={'busy':True,'status':'PAUSED_PLAYBACK'})
  await bridge.control({'endpoint_id':'tv','action':'pause'});bridge.soap.assert_not_called()
  bridge.tickets={'ticket':{'endpoint_id':'tv','_watch_id':'episode','_watch_started':time.time(),'_watch_meta':{'live':False}}}
  await bridge.control({'endpoint_id':'tv','action':'pause'});self.assertEqual(bridge.soap.call_args.args[1],'Pause')
  await bridge.control({'endpoint_id':'other','action':'stop'});self.assertEqual(bridge.soap.call_count,1)
  bridge.play=AsyncMock();await bridge.control({'endpoint_id':'tv','action':'seek','position':400})
  self.assertEqual(bridge.play.call_args.args[0]['episode_id'],'episode');self.assertEqual(bridge.play.call_args.args[0]['start_position'],400)
