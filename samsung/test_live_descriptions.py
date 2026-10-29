import unittest
from live_descriptions import bbc_schedule,current,five_synopsis
class LiveDescriptions(unittest.TestCase):
 def test_bbc_synopsis_and_exact_schedule(self):
  data={'broadcasts':{'elements':[{'scheduled_start':'2026-10-29T16:00:00Z','scheduled_end':'2026-10-29T17:00:00Z','episode':{'title':'Quiz','subtitle':'Episode 2','synopses':{'small':'Four friends face a quiz.'},'images':{'standard':'https://ichef.bbci.co.uk/{recipe}/still.jpg'}}}]}}
  schedule=bbc_schedule(data);row=current(schedule,1793290200)['now']
  self.assertEqual(row['subtitle'],'Four friends face a quiz.');self.assertEqual(row['time'],'16:00');self.assertIn('640x360',row['image'])
  self.assertIsNone(current(schedule,0)['now'])
 def test_five_only_exact_title_fallback(self):
  guide={'now':{'title':'A Show'}}
  five_synopsis(guide,[{'title':'A Show Extra','description':'Wrong'},{'title':'A Show','description':'Correct synopsis'}])
  self.assertEqual(guide['now']['subtitle'],'Correct synopsis')
  five_synopsis(guide,[{'title':'A Show','description':'Different'}]);self.assertEqual(guide['now']['subtitle'],'Correct synopsis')
 def test_invalid_and_blanked_broadcasts_skipped(self):
  self.assertEqual(bbc_schedule({'broadcasts':{'elements':[{'scheduled_start':'bad'}]}}),{'_schedule':[]})
