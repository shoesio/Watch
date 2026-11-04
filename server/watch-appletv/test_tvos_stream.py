"""Exercise buffering using a generated, unencrypted video, no provider accounts."""
import asyncio,io,subprocess,tempfile,time,unittest
from pathlib import Path
from tvos_stream import TVStream

class StreamTest(unittest.IsolatedAsyncioTestCase):
 async def test_startup_has_twelve_seconds_and_timestamp_sync(self):
  with tempfile.TemporaryDirectory() as folder:
   path=Path(folder)/'sample.ts'
   result=await asyncio.to_thread(subprocess.run,['ffmpeg','-nostdin','-v','error','-f','lavfi','-i','testsrc2=size=320x180:rate=25','-f','lavfi','-i','sine=frequency=440:sample_rate=48000','-t','20','-c:v','libx264','-preset','ultrafast','-g','50','-c:a','aac','-f','mpegts',str(path)],capture_output=True)
   self.assertEqual(result.returncode,0)
   stream=TVStream(Path(folder)/'hls',path.open('rb'))
   try:
    await stream.ready();snapshot=stream.snapshot()
    self.assertGreaterEqual(snapshot['buffer_seconds'],12)
    self.assertGreaterEqual(snapshot['segments'],3)
    playlist=(stream.directory/'index.m3u8').read_text()
    segment=next(line for line in playlist.splitlines() if line.endswith('.ts'))
    result=await asyncio.to_thread(subprocess.run,['ffprobe','-v','error','-show_entries','stream=codec_name,start_time','-of','json',str(stream.directory/segment)],capture_output=True,text=True)
    import json
    tracks=json.loads(result.stdout)['streams']
    self.assertEqual({t['codec_name'] for t in tracks},{'h264','aac'})
    self.assertLess(abs(float(tracks[0]['start_time'])-float(tracks[1]['start_time'])),0.1)
   finally:await stream.close()
   self.assertFalse(stream.directory.exists())

 async def test_episode_keeps_paused_segments_beyond_the_old_three_minute_window(self):
  with tempfile.TemporaryDirectory() as folder:
   path=Path(folder)/'episode.ts'
   result=await asyncio.to_thread(subprocess.run,['ffmpeg','-nostdin','-v','error','-f','lavfi','-i','testsrc2=size=64x36:rate=5','-t','260','-c:v','libx264','-preset','ultrafast','-g','20','-f','mpegts',str(path)],capture_output=True)
   self.assertEqual(result.returncode,0)
   stream=TVStream(Path(folder)/'hls',path.open('rb'),live=False)
   try:
    await stream.ready()
    await asyncio.wait_for(stream.task,20)
    await asyncio.to_thread(stream.process.wait,10)
    playlist=(stream.directory/'index.m3u8').read_text()
    self.assertIn('#EXT-X-PLAYLIST-TYPE:EVENT',playlist)
    self.assertIn('#EXT-X-START:TIME-OFFSET=0,PRECISE=YES',stream.playlist())
    self.assertIn('#EXT-X-MEDIA-SEQUENCE:0',playlist)
    self.assertIn('segment000000.ts',playlist)
    self.assertTrue((stream.directory/'segment000000.ts').exists())
    self.assertGreaterEqual(stream.snapshot()['buffer_seconds'],260)
    self.assertIn('#EXT-X-ENDLIST',playlist)
   finally:await stream.close()
   self.assertFalse(stream.directory.exists())

 async def test_short_ended_live_input_is_not_reported_ready(self):
  from types import SimpleNamespace
  stream=TVStream.__new__(TVStream);stream.allow_short=False
  stream.snapshot=lambda:{'buffer_seconds':8,'ended':True,'segments':2}
  stream.process=SimpleNamespace(poll=lambda:0)
  with self.assertRaises(ValueError):await stream.ready()

 async def test_short_completed_clip_remains_supported(self):
  from types import SimpleNamespace
  stream=TVStream.__new__(TVStream);stream.allow_short=True
  stream.snapshot=lambda:{'buffer_seconds':8,'ended':True,'segments':2}
  stream.process=SimpleNamespace(poll=lambda:0)
  await stream.ready()

if __name__=='__main__':unittest.main()
