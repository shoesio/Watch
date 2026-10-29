import json,time,unittest
from live_guide import parse_page,parse_channel4_page,LiveGuide
class GuideTests(unittest.TestCase):
 def page(self,items):return '<script>window.__IPLAYER_REDUX_STATE__ = '+json.dumps({'broadcasts':{'items':items}})+';</script>'
 def test_now_next_times_and_no_private_fields(self):
  now=1793219400
  data=parse_page(self.page([{'title':'Current programme','scheduledStart':1793217600,'endTime':'21:00','image':'https://ichef.bbci.co.uk/images/ic/{recipe}/a.jpg','events':[{'secret':'excluded'}]},{'title':'Next programme','scheduledStart':1793221200,'endTime':'22:00'}]),now)
  self.assertEqual(data['now']['title'],'Current programme');self.assertEqual(data['next']['title'],'Next programme')
  self.assertEqual(data['next']['time'],'21:00');self.assertNotIn('secret',json.dumps(data))
 def test_overnight_programme(self):
  data=parse_page(self.page([{'title':'Late show','scheduledStart':1793228400,'endTime':'00:30'}]),1793230200)
  self.assertEqual(data['now']['title'],'Late show')
 def test_bbc_next_promotes_to_now_at_changeover_without_refetch(self):
  now=1793219400
  data=parse_page(self.page([{'title':'Current programme','scheduledStart':1793217600,'endTime':'21:00'},
      {'title':'Following programme','scheduledStart':1793221200,'endTime':'22:00','image':'https://ichef.bbci.co.uk/images/ic/{recipe}/next.jpg'}]),now)
  from unittest.mock import patch
  g=LiveGuide();g.channels['bbcone']=data
  with patch('live_guide.time.time',return_value=1793221201):
   data['checked_at']=1793221190
   promoted=g.get('bbcone')['now']
   self.assertEqual(promoted['title'],'Following programme')
   self.assertIn('640x360',promoted['image'])
 def test_expired_metadata_is_hidden(self):
  g=LiveGuide();g.channels['bbcone']={'checked_at':time.time()-301,'now':{'title':'Old'}}
  self.assertEqual(g.get('bbcone'),{})
 def test_invalid_provider_page_does_not_invent_guide(self):
  with self.assertRaises(ValueError):parse_page('<html>Unavailable</html>',time.time())
 def test_channel4_schedule_has_titles_times_and_artwork(self):
  p={'startDate':'2026-10-28T20:00:00.000Z','endDate':'2026-10-28T21:00:00.000Z','title':'Current C4 show','image':{'url':'https://ic.c4assets.com/test.jpg{&resize}'}}
  html='<script id="initialData">var initialData = '+json.dumps({'channels':{'C4':{'programmes':[p]}}})+';</script>'
  now=1793219400;channels=parse_channel4_page(html,now)
  self.assertEqual(channels['C4']['_schedule'][0]['title'],'Current C4 show')
  self.assertNotIn('{',channels['C4']['_schedule'][0]['image'])
  g=LiveGuide();channels['C4']['checked_at']=time.time();g.channels=channels
  self.assertEqual(len(channels),5)
if __name__=='__main__':unittest.main()
