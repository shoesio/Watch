import tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from types import SimpleNamespace
from five_live_artwork import FiveLiveArtwork,exact_programme
class FiveLiveArt(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.art=FiveLiveArtwork(self.temp.name,self.temp.name)
 def tearDown(self):self.temp.cleanup()
 def test_title_punctuation_normalised_but_different_show_rejected(self):
  candidates=[{'title':'Law and Order: Special Victims Unit','artwork':'wrong'},{'title':'Law & Order','artwork':'right'}]
  self.assertEqual(exact_programme('Law and Order',candidates)['artwork'],'right')
  self.assertIsNone(exact_programme('Law & Order: UK',candidates))
 def test_live_now_receives_programme_art_and_synopsis_only(self):
  guide={'now':{'title':'Traffic Cops'},'next':{'title':'Different'}}
  self.art.enrich(guide,[{'title':'Traffic Cops','artwork':'programme-image','description':'Police patrol.'}])
  self.assertEqual(guide['now']['image'],'programme-image');self.assertEqual(guide['now']['subtitle'],'Police patrol.');self.assertNotIn('image',guide['next'])
 def test_cached_fallback_keeps_existing_synopsis(self):
  self.art.cache['gilmore girls']={'image':'series-image','source':'TMDB exact series title','description':'Series summary'}
  guide={'now':{'title':'Gilmore Girls','subtitle':'Episode summary'}};self.art.enrich(guide,[])
  self.assertEqual(guide['now']['image'],'series-image');self.assertEqual(guide['now']['subtitle'],'Episode summary')
 def test_unknown_show_has_no_invented_image(self):
  guide={'now':{'title':'Unknown'}};self.art.enrich(guide,[]);self.assertNotIn('image',guide['now'])
 def test_refresh_uses_exact_official_art_and_caches(self):
  discovery=SimpleNamespace(five=[{'title':'Traffic Cops','artwork':'official','description':'Synopsis'}],five_search=lambda title:self.fail('No search needed'))
  channels=[{'_guide':{'now':{'title':'Traffic Cops'}}}];self.art.refresh(channels,discovery)
  self.assertEqual(self.art.cache['traffic cops']['image'],'official');self.assertTrue(self.art.path.exists())
