import json,tempfile,unittest
from pathlib import Path
from unittest.mock import AsyncMock
from ha_alignment import augment,Alignment,ACTIONS
class AlignmentTests(unittest.IsolatedAsyncioTestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name);(self.root/'appletv').mkdir()
 def tearDown(self):self.tmp.cleanup()
 def test_augmentation_does_not_replace_existing_or_include_live(self):
  base={'programmes':[{'id':'a','episodes':[{'id':'original'}]}],'endpoints':[]}
  extra={'a':{'programme':{'id':'a','episodes':[{'id':'wrong'}]}},'b':{'programme':{'id':'b','episodes':[{'id':'new'}]}},'c':{'programme':{'id':'c','live_channel':'C5','episodes':[{'id':'live'}]}}}
  (self.root/'appletv/discovery-library.json').write_text(json.dumps(extra))
  result=augment(base,self.root);self.assertEqual(len(result['programmes']),2);self.assertEqual(result['programmes'][0]['episodes'][0]['id'],'original');self.assertEqual(len(base['programmes']),1)
 async def test_public_metadata_enrichment_keeps_ha_source_badge(self):
  a=Alignment(self.root);a.request=AsyncMock(return_value={'programmes':[{'id':'a','content_rating':'15','favourite':True,'episodes':[{'id':'e','brands':[{'id':'bbc'}],'thumbnail_source':'BBC episode still','thumbnail':'bbc-still'}]}]})
  rows=[{'id':'a','episodes':[{'id':'e','brands':[{'id':'u'}],'thumbnail':'u-image'}]}]
  result=await a.enrich(None,rows);self.assertEqual(result[0]['content_rating'],'15');self.assertTrue(result[0]['favourite']);self.assertEqual(result[0]['episodes'][0]['thumbnail'],'u-image')
 async def test_gateway_outage_retains_library(self):
  a=Alignment(self.root);a.request=AsyncMock(side_effect=ValueError());rows=[{'id':'a','episodes':[]}];self.assertEqual(await a.enrich(None,rows),rows)
 async def test_no_arbitrary_endpoint_or_playback_proxy(self):
  a=Alignment(self.root)
  for action in ('prepare','session','http://example.org','../../prepare'):
   with self.assertRaises(ValueError):await a.request(None,action,{})
  self.assertNotIn('prepare',ACTIONS)
 async def test_native_only_results_filtered_from_every_shelf(self):
  from ha_alignment import filter_result
  valid={'id':'bbc','brands':[{'id':'bbc'}]};itv={'id':'itv','discovery_ref':'itv:show','brands':[{'id':'itv'}]};five_live={'id':'five','live_channel':'C5','live':True}
  data={key:[valid,itv,five_live] for key in ('programmes','personal','hot','featured_films','featured_shows')}
  self.assertTrue(all(rows==[valid] for rows in filter_result(data).values()))
 async def test_native_only_import_rejected_before_network(self):
  a=Alignment(self.root);a.token_path.write_text('private-fixture')
  with self.assertRaises(ValueError):await a.request(None,'import',{'ref':'itv:show'})
 async def test_film_rank_enriched_without_reordering_series(self):
  a=Alignment(self.root);a.request=AsyncMock(return_value={'programmes':[{'id':'film','film_rank':7}]})
  rows=[{'id':'series','episodes':[]},{'id':'film','film':True,'episodes':[]}]
  enriched=await a.enrich(None,rows);self.assertEqual(enriched[1]['film_rank'],7);self.assertEqual(enriched[0]['id'],'series')
