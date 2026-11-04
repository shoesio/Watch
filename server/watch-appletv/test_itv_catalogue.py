import unittest
from types import SimpleNamespace
from unittest.mock import patch
from itv_catalogue import show,latest_details,details,live,playlist,props,duration
class ITVCatalogue(unittest.TestCase):
 def summary(self):
  return show({'programmeTitle':'The Chase','legacyId':{'apiEncoded':'1_7842'},'productionId':'1/7842/2535#001','synopsis':'Quiz','genre':['ENTERTAINMENT'],'tier':'FREE'})
 def test_search_summary_preserves_exact_provider_identity(self):
  p=self.summary();self.assertEqual(p['key'],'1a7842');self.assertEqual(p['production_id'],'1/7842/2535#001')
 def test_premium_excluded_and_collections_not_episodes(self):
  self.assertIsNone(show({'title':'Premium','programmeId':'1/2','tier':'PAID'}));self.assertIsNone(show({'contentType':'collection','programmeId':'1/2','title':'Collection'}))
 def test_latest_fallback_uses_published_production_not_invented_numbering(self):
  p=latest_details(self.summary());e=p['episodes'][0];self.assertEqual(e['playlist_url'],'https://magni.itv.com/playlist/itvonline/ITV/1_7842_2535.001');self.assertEqual(e['episode_number'],0)
 def test_playlist_allowlist(self):
  self.assertTrue(playlist('https://magni.itv.com/playlist/itvonline/ITV/1_2_3.001'))
  self.assertFalse(playlist('https://evil.test/playlist/itvonline/ITV/a'));self.assertFalse(playlist('https://magni.itv.com/playlist/itvonline/x?token=secret'))
 def test_episode_import_omits_paid_and_expired_episodes(self):
  root={'programme':{},'seriesList':[{'seriesLabel':'Series 2','titles':[{'productionId':'1/2/3#001','episodeTitle':'A Quiz','episode':3,'playlistUrl':'https://magni.itv.com/playlist/itvonline/ITV/1_2_3.001','duration':'PT45M','tier':['FREE']},{'productionId':'paid','premium':True,'playlistUrl':'https://magni.itv.com/playlist/itvonline/ITV/paid'},{'productionId':'old','availabilityUntil':'2020-01-01T00:00:00Z','playlistUrl':'https://magni.itv.com/playlist/itvonline/ITV/old'}]}]}
  with patch('itv_catalogue.get',return_value=SimpleNamespace(text='')),patch('itv_catalogue.props',return_value=root):p=details(self.summary())
  self.assertEqual(len(p['episodes']),1);self.assertEqual(p['episodes'][0]['duration_seconds'],2700)
 def test_live_guide_has_real_synopsis_image_and_native_endpoint(self):
  channel={'id':'ITV','name':'ITV1','streamUrl':'https://simulcast.itv.com/playlist/itvonline/ITV','images':{'logo':'https://images.ctfassets.net/logo.png'},'slots':{'now':{'start':'2026-10-29T16:00:00Z','end':'2026-10-29T17:00:00Z','displayTitle':'Deal or No Deal','shortSynopsis':'Kev faces the Banker.','brandId':'123abcd'}}}
  with patch('itv_catalogue.get',return_value=SimpleNamespace(json=lambda:{'channels':[channel]})):rows=live()
  self.assertEqual(len(rows),1);self.assertEqual(rows[0]['_guide']['now']['subtitle'],'Kev faces the Banker.');self.assertTrue(rows[0]['_guide']['now']['image'].startswith('https://ovp.itv.com/'));self.assertEqual(rows[0]['episodes'][0]['kind'],'native')

 def test_human_runtime_keeps_hours_and_minutes(self):
  for value,expected in [('1h 22m',4920),('2 hours 5 minutes',7500),('PT1H22M',4920),('45 mins',2700),('1h',3600),('unknown',0)]:
   with self.subTest(value=value):self.assertEqual(duration(value),expected)
 def test_programme_page_corrects_search_film_classification(self):
  summary=self.summary();summary['film']=False
  root={'programme':{'genres':[{'id':'FILM','name':'Film'}]},'seriesList':[{'titles':[{'productionId':'1/2/3#001','playlistUrl':'https://magni.itv.com/playlist/itvonline/ITV/1_2_3.001','duration':'1h 22m','contentType':'film'}]}]}
  with patch('itv_catalogue.get',return_value=SimpleNamespace(text='')),patch('itv_catalogue.props',return_value=root):p=details(summary)
  self.assertEqual(p['media_type'],'movie');self.assertEqual(p['episodes'][0]['duration_seconds'],4920)
  self.assertEqual(p['id'],'itv_'+summary['key'])
