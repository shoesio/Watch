import tempfile
import unittest
from pathlib import Path
from episode_versions import versions,seconds,QualityStore

class VersionsTests(unittest.TestCase):
 def test_numbered_cross_provider_duplicates_only(self):
  a={'id':'bbc','season':69,'episode_number':1}
  b={'id':'u','season':'69','episode_number':1}
  groups=versions('show',[(a,'BBC iPlayer'),(b,'U')])
  self.assertEqual(len(groups),1);self.assertEqual(len(groups[0]['sources']),2)
  self.assertEqual(len(versions('show',[(a,'U'),(b,'U')])),2)
  self.assertNotEqual(groups[0]['id'],versions('bleeped',[(a,'BBC iPlayer'),(b,'U')])[0]['id'])
  self.assertEqual(len(versions('show',[(dict(a,episode_number=0),'BBC iPlayer'),(dict(b,episode_number=0),'U')])),2)

 def test_measured_quality_beats_provider_then_prefers_motion(self):
  with tempfile.TemporaryDirectory() as root:
   store=QualityStore(Path(root)/'quality.json')
   a=({'id':'bbc'},'BBC iPlayer');b=({'id':'u'},'U');v={'sources':[a,b]}
   def info(height,fps):return {'streams':[{'codec_type':'video','height':height,'width':1280,'avg_frame_rate':fps}]}
   store.record('bbc',info(540,'50/1'));store.record('u',info(720,'25/1'))
   self.assertEqual(store.preferred(v),b)
   store.record('bbc',info(720,'50/1'))
   self.assertEqual(store.preferred(v),a)
   self.assertTrue(store.fresh('bbc'))
   self.assertNotIn('url',store.path.read_text())

 def test_provider_duration_formats(self):
  self.assertAlmostEqual(seconds('PT43M39.818666S'),2619.818666)
  self.assertEqual(seconds('PT1H2M3S'),3723)
  self.assertEqual(seconds('invalid'),0)
