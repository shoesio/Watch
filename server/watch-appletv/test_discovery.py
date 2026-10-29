import json,tempfile,time,unittest
from pathlib import Path
from unittest.mock import patch
from discovery import Discovery,bbc_state,c4_state,five_genres
from recommendations import uk_rating,recommend

class DiscoveryTests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.discovery=Discovery(self.temp.name,'http://pi:8109')
  self.itv_mock=patch.object(self.discovery,'itv_search',return_value=[]);self.itv_mock.start()
 def tearDown(self):self.itv_mock.stop();self.temp.cleanup()
 def test_preview_has_no_source_or_credentials(self):
  p=self.discovery.preview('bbc','m1234567','New Show','Synopsis',{'standard':'https://ichef.bbci.co.uk/{recipe}/test.jpg'},'Comedy')
  self.assertEqual(p['episodes'],[]);self.assertEqual(p['discovery_ref'],'bbc:m1234567');self.assertNotIn('url',p)
  self.assertEqual(p['artwork'],'https://ichef.bbci.co.uk/1280x720/test.jpg')
 def test_import_rejects_arbitrary_provider_urls(self):
  for ref in ['bbc:http://localhost/secret','other:foo','bbc:../../file']:
   with self.subTest(ref=ref):
    with self.assertRaises(ValueError):self.discovery.import_show(ref)
 def test_empty_import_not_persisted(self):
  with patch.object(self.discovery,'load_bbc',return_value={'episodes':[]}):
   with self.assertRaises(ValueError):self.discovery.import_show('bbc:m1234567')
  self.assertFalse((Path(self.temp.name)/'discovery-library.json').exists())
 def test_import_does_not_favourite_show(self):
  show={'title':'New','episodes':[{'id':'episode'}],'favourite':True,'recent':True}
  with patch.object(self.discovery,'load_bbc',return_value=show):row=self.discovery.import_show('bbc:m1234567')
  self.assertFalse(row['favourite']);self.assertFalse(row['recent'])
 def test_provider_failure_is_partial(self):
  row=self.discovery.preview('bbc','m1234567','New Show')
  with patch.object(self.discovery,'bbc_search',return_value=[row]),patch.object(self.discovery,'u_search',side_effect=ValueError()),patch.object(self.discovery,'five_search',return_value=[]):
   result=self.discovery.search('New')
  self.assertEqual(len(result['programmes']),1);self.assertEqual(result['status']['u'],'temporarily unavailable')
 def test_search_merges_exact_title_providers(self):
  bbc=self.discovery.preview('bbc','m1234567','Ghosts',genre='Comedy')
  other=self.discovery.preview('u','ghosts','Ghosts',genre='Comedy')
  with patch.object(self.discovery,'bbc_search',return_value=[bbc]),patch.object(self.discovery,'u_search',return_value=[other]),patch.object(self.discovery,'five_search',return_value=[]):result=self.discovery.search('Ghosts')
  self.assertEqual(len(result['programmes']),1)
  self.assertEqual(len(result['programmes'][0]['brands']),2)
  self.assertEqual(len(self.discovery.alternates[bbc['discovery_ref']]),2)
 def test_uk_rating_never_uses_us(self):
  self.assertIsNone(uk_rating({'results':[{'iso_3166_1':'US','rating':'TV-MA'}]},'tv'))
  self.assertEqual(uk_rating({'results':[{'iso_3166_1':'GB','rating':'15'}]},'tv'),'15')
 def test_ambiguous_certification_omitted(self):
  data={'results':[{'iso_3166_1':'GB','release_dates':[{'type':4,'certification':'12'},{'type':4,'certification':'15'}]}]}
  self.assertIsNone(uk_rating(data,'movie'))
 def test_digital_uk_rating_preferred(self):
  data={'results':[{'iso_3166_1':'GB','release_dates':[{'type':4,'certification':'PG'},{'type':3,'certification':'12A'}]}]}
  self.assertEqual(uk_rating(data,'movie'),'PG')
 def test_recommendations_use_taste_not_child_history(self):
  library=[{'title':'Taskmaster','genres':['Comedy'],'favourite':True},{'title':'Peppa Pig','genres':['Children'],'recent':True}]
  candidates=[{'title':'New Comedy','genres':['Comedy'],'brands':[{'id':'u'}]},{'title':'Kids Show','genres':['Children']},{'title':'Unrelated Horror','genres':['Horror']}]
  rows=recommend(library,candidates)
  self.assertEqual([p['title'] for p in rows],['New Comedy']);self.assertIn('comedy',rows[0]['recommendation_reason'])
 def test_multi_genre_films_do_not_overwhelm_tv_taste(self):
  library=[{'title':'Taskmaster','genres':['Comedy'],'favourite':True},{'title':'QI','genres':['Comedy'],'favourite':True},{'title':'A Drama','genres':['Drama'],'recent':True}]
  candidates=[{'title':'New Sitcom','genres':['Comedy'],'discovery_ref':'bbc:new','brands':[{'id':'bbc'}]},{'title':'Comedy Drama Film','genres':['Comedy','Drama'],'film':True,'brands':[{'id':'c4'}]},{'title':'Family Cartoon','genres':['Comedy','Animation'],'film':True}]
  rows=recommend(library,candidates)
  self.assertEqual(rows[0]['title'],'New Sitcom');self.assertNotIn('Family Cartoon',[p['title'] for p in rows])
 def test_recommendation_titles_deduplicate_across_services(self):
  library=[{'title':'Taskmaster','genres':['Comedy'],'favourite':True}]
  candidates=[{'title':'New Show','genres':['Comedy'],'brands':[{'id':'bbc'}]},{'title':'New Show','genres':['Comedy'],'brands':[{'id':'u'}]}]
  self.assertEqual(len(recommend(library,candidates)),1)
 def test_genre_recommendations_stay_in_selected_genre(self):
  library=[{'title':'Taskmaster','genres':['Comedy'],'description':'Comedians compete in a panel quiz','favourite':True}]
  candidates=[{'title':'Generic Comedy','genres':['Comedy'],'brands':[{'id':'bbc'}]},{'title':'Panel Show','description':'A panel quiz with comedians','genres':['Comedy'],'brands':[{'id':'c4'}]},{'title':'Drama','genres':['Drama']}]
  rows=recommend(library,candidates,genre='Comedy')
  self.assertEqual(rows[0]['title'],'Panel Show');self.assertNotIn('Drama',[p['title'] for p in rows])
 def test_unwatched_genre_can_still_offer_suggestions(self):
  rows=recommend([], [{'title':'A Documentary','genres':['Documentaries']}],genre='Documentaries')
  self.assertEqual(len(rows),1)
 def test_five_collection_labels_preserve_documentary_genre(self):
  tags=five_genres({'genre':'Documentary','primary_vod_genre':'Inside Crime Collection','vod_subgenres':['True Crime']})
  self.assertIn('Documentaries',tags);self.assertIn('Crime & thriller',tags);self.assertIn('Inside Crime Collection',tags)
 def test_five_plural_documentaries_and_factual_normalise(self):
  self.assertIn('Documentaries',five_genres({'primary_vod_genre':'Documentaries'}))
  self.assertIn('Documentaries',five_genres({'genre':'Factual','primary_vod_genre':'History'}))
 def test_five_index_follows_pagination_and_reuses_cache(self):
  first=self.discovery.five_preview({'id':'1','title':'History Show','genre':'Documentary','primary_vod_genre':'History'})
  second=self.discovery.five_preview({'id':'2','title':'Another Documentary','genre':'Documentary'})
  with patch.object(self.discovery,'five_page',side_effect=[([first],201),([second],201)]) as pages:self.discovery.warm_five()
  self.assertEqual(len(self.discovery.five),2);self.assertEqual(pages.call_count,2)
  with patch.object(self.discovery,'five_page',side_effect=AssertionError('Fresh cache should be used')):self.discovery.warm_five()
  self.assertEqual(self.discovery.status['channel5'],'ready')
 def test_five_documentaries_enter_genre_pool(self):
  self.discovery.five=[self.discovery.five_preview({'id':'1','title':'Real Lives','genre':'Documentary','primary_vod_genre':'Real Lives'})]
  from types import SimpleNamespace
  with patch.object(self.discovery,'get',return_value=SimpleNamespace(json=lambda:{'category_programmes':{'elements':[],'count':0}})):
   rows=self.discovery.genre_candidates('Documentaries')
  self.assertEqual(len(rows),1);self.assertEqual(rows[0]['brands'][0]['id'],'channel5')
 def test_five_imported_genres_do_not_drop_documentary_label(self):
  self.assertIn('Documentaries',self.discovery.five_preview({'id':'1','title':'A Factual Show','genre':'Documentary','primary_vod_genre':'Entertainment'})['genres'])

if __name__=='__main__':unittest.main()
