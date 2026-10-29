import json,tempfile,time,unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import requests
from episode_artwork import EpisodeArtwork,bbc_image,episode_pid

class EpisodeArtworkTests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.art=EpisodeArtwork(self.temp.name)
 def tearDown(self):self.temp.cleanup()
 def test_episode_still_wins_over_series_promotional_art(self):
  images={'promotional_with_logo':'https://ichef.bbci.co.uk/{recipe}/logo.jpg','promotional':'https://ichef.bbci.co.uk/{recipe}/series.jpg','standard':'https://ichef.bbci.co.uk/{recipe}/episode.jpg'}
  self.assertEqual(bbc_image(images),'https://ichef.bbci.co.uk/960x540/episode.jpg')
 def test_missing_standard_keeps_safe_fallback(self):
  self.assertEqual(bbc_image({'promotional':'https://ichef.bbci.co.uk/{recipe}/series.jpg'}),'https://ichef.bbci.co.uk/960x540/series.jpg')
  self.assertEqual(bbc_image(None),'');self.assertEqual(bbc_image({'standard':'https://example.com/image.jpg'}),'')
 def test_pid_is_exact_episode_not_series_or_arbitrary_source(self):
  self.assertEqual(episode_pid({'url':'https://www.bbc.co.uk/iplayer/episode/m0033khs/name'}),'m0033khs')
  self.assertIsNone(episode_pid({'url':'https://example.com/iplayer/episode/m0033khs'}))
 def test_enrichment_keeps_hero_and_other_provider_art(self):
  self.art.cache={'series':{'images':{'m0033khs':'https://ichef.bbci.co.uk/960x540/still.jpg'}}}
  bbc={'id':'bbc','url':'https://www.bbc.co.uk/iplayer/episode/m0033khs'}
  watch=SimpleNamespace(index={'e1':{'sources':[(bbc,'BBC iPlayer')]},'e2':{'sources':[(bbc,'U')]}},quality=SimpleNamespace(preferred=lambda version:version['sources'][0]))
  programmes=[{'hero':'series-hero','episodes':[{'id':'e1','thumbnail':'shared'},{'id':'e2','thumbnail':'u-image'}]}]
  self.art.enrich(programmes,watch)
  self.assertEqual(programmes[0]['hero'],'series-hero');self.assertEqual(programmes[0]['episodes'][0]['thumbnail'],'https://ichef.bbci.co.uk/960x540/still.jpg');self.assertEqual(programmes[0]['episodes'][1]['thumbnail'],'u-image')
 def test_fetch_follows_pagination_and_stores_only_standard(self):
  def response(e):return SimpleNamespace(raise_for_status=lambda:None,json=lambda:{'programme_episodes':{'count':201,'elements':e}})
  rows=[response([{'id':'m0033khs','images':{'standard':'https://ichef.bbci.co.uk/{recipe}/one.jpg'}}]),response([{'id':'m0033kcj','images':{'standard':'https://ichef.bbci.co.uk/{recipe}/two.jpg'}},{'id':'m0033kcd','images':{'promotional':'https://ichef.bbci.co.uk/{recipe}/series.jpg'}}])]
  with patch('episode_artwork.requests.get',side_effect=rows) as fetch:
   result=self.art.fetch('b094mjv0')
  self.assertEqual(fetch.call_count,2);self.assertEqual(len(result['images']),2);self.assertNotIn('m0033kcd',result['images'])
 def test_refresh_outage_keeps_last_good_cache(self):
  self.art.cache={'b094mjv0':{'checked_at':0,'images':{'m0033khs':'old-still'}}}
  with patch.object(self.art,'fetch',side_effect=requests.ConnectionError()):
   self.assertEqual(self.art.refresh({'programmes':[{'id':'bbc_b094mjv0','provider':'BBC iPlayer'}]}),0)
  self.assertEqual(self.art.cache['b094mjv0']['images']['m0033khs'],'old-still')
 def test_sync_importer_prefers_episode_still(self):
  from library_sync import LibrarySync
  sync=LibrarySync.__new__(LibrarySync)
  self.assertEqual(sync.bbc_episode_pic({'standard':'https://ichef.bbci.co.uk/{recipe}/episode.jpg','promotional_with_logo':'https://ichef.bbci.co.uk/{recipe}/shared.jpg'}),'https://ichef.bbci.co.uk/960x540/episode.jpg')
