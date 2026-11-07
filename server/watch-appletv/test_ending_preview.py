import asyncio,json,tempfile,unittest
from pathlib import Path
from ending_preview import EndingPreviews
import test_server

class Preview(unittest.IsolatedAsyncioTestCase):
 async def asyncSetUp(self):
  self.temp=tempfile.TemporaryDirectory();self.preview=EndingPreviews(self.temp.name)
 async def asyncTearDown(self):
  await self.preview.close();self.temp.cleanup()
 async def test_rejects_live_missing_duration_and_partial_sources(self):
  for prepared in [{},{'_watch_meta':{'duration_seconds':True}}, {'_watch_meta':{'duration_seconds':1000,'live':True},'_ending_url':'https://unused'}]:
   self.assertEqual((await self.preview.get(prepared))['state'],'unavailable')
 async def test_real_ffmpeg_tail_is_bounded_and_cached(self):
  source=Path(self.temp.name)/'source.mp4'
  p=await asyncio.create_subprocess_exec('ffmpeg','-nostdin','-v','error','-f','lavfi','-i','color=c=blue:s=320x180:r=1:d=125','-f','lavfi','-i','sine=frequency=440:duration=125','-c:v','libx264','-threads','1','-preset','ultrafast','-c:a','aac','-shortest','-y',str(source))
  self.assertEqual(await p.wait(),0)
  prepared={'path':source,'_watch_meta':{'id':'episode','source_key':'source','version_id':'v1','duration_seconds':125,'start_position':0}}
  first=await self.preview.get(prepared);self.assertEqual(first['state'],'analysing')
  await asyncio.gather(*self.preview.jobs.values())
  result=await self.preview.get(prepared);self.assertEqual(result['state'],'ready');self.assertEqual(result['start'],35)
  p=await asyncio.create_subprocess_exec('ffprobe','-v','error','-show_entries','format=duration','-of','json',str(result['path']),stdout=asyncio.subprocess.PIPE)
  out,_=await p.communicate();self.assertAlmostEqual(float(json.loads(out)['format']['duration']),90,delta=1)
  self.assertLess(result['path'].stat().st_size,12000000)
  prepared['_watch_meta']['start_position']=30
  self.assertEqual((await self.preview.get(prepared))['state'],'unavailable')

class Boundary(unittest.IsolatedAsyncioTestCase):
 asyncSetUp=test_server.Tests.asyncSetUp
 asyncTearDown=test_server.Tests.asyncTearDown
 idle=test_server.Tests.idle
 async def test_requires_pairing_session_ownership_and_matching_version(self):
  self.assertEqual((await self.client.get('/playback/ending?ticket=a')).status,401)
  token=await test_server.Tests.pair(self);headers={'Authorization':'Bearer '+token}
  self.assertEqual((await self.client.get('/playback/ending?ticket=a',headers=headers)).status,404)
  self.gateway.sessions['a']={'device':'someone-else','prepared':{},'stream':None}
  self.assertEqual((await self.client.get('/playback/ending/file?ticket=a',headers=headers)).status,404)
  import hashlib
  owner=self.gateway.read('devices.json',{})[hashlib.sha256(token.encode()).hexdigest()]
  self.gateway.sessions['a']={'device':owner,'prepared':{'_watch_meta':{'version_id':'correct'}},'stream':None}
  r=await self.client.get('/playback/ending?ticket=a&version_id=wrong',headers=headers)
  self.assertEqual((await r.json())['state'],'unavailable');self.assertFalse(self.gateway.ending_previews.jobs)

 async def test_diagnostic_is_owned_bounded_and_excludes_secrets(self):
  token=await test_server.Tests.pair(self);headers={'Authorization':'Bearer '+token}
  import hashlib
  owner=self.gateway.read('devices.json',{})[hashlib.sha256(token.encode()).hexdigest()]
  self.gateway.sessions['a']={'device':owner,'prepared':{'_watch_meta':{'id':'episode'}},'stream':None}
  r=await self.client.post('/playback/ending/report',headers=headers,json={'ticket':'a','state':'detected','start':1720,'secret':'not-saved'})
  self.assertEqual(r.status,200)
  record=self.gateway.read('ending-analysis-status.json',{})
  self.assertEqual(record['start'],1720);self.assertNotIn('ticket',record);self.assertNotIn('secret',record)
  r=await self.client.post('/playback/ending/report',headers=headers,json={'ticket':'a','state':'invented'})
  self.assertEqual(r.status,400)
  r=await self.client.post('/playback/ending/report',json={'ticket':'a','state':'detected'})
  self.assertEqual(r.status,401)
