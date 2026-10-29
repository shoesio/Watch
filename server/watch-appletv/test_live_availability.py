import unittest
from live_availability import off_air,on_air_channels
class Availability(unittest.TestCase):
 def channel(self,title,**kw):return {'live':True,'guide':{'now':{'title':title,'start':100,'end':200}},**kw}
 def test_bbc_daytime_holding_slate_hidden(self):
  self.assertTrue(off_air(self.channel('This is BBC Four'),150))
 def test_normal_broadcast_returns_after_holding_slate(self):
  self.assertFalse(off_air(self.channel('The Sky at Night'),150))
 def test_explicit_offair_hidden_for_any_provider(self):
  for title in ['Off Air','Not broadcasting','No programmes']:
   self.assertTrue(off_air(self.channel(title),150))
 def test_missing_or_stale_guide_is_not_evidence_of_offair(self):
  self.assertFalse(off_air({'live':True},150));self.assertFalse(off_air(self.channel('This is BBC Four'),250))
 def test_nonlive_and_real_titles_preserved(self):
  self.assertFalse(off_air(self.channel('This is BBC Four',live=False),150))
  self.assertFalse(off_air(self.channel('Off Air with Jane and Fi'),150))
 def test_only_offair_channel_removed(self):
  rows=[self.channel('This is BBC Four'),self.channel('BBC News'),{'title':'Film','live':False}]
  self.assertEqual(on_air_channels(rows,150),rows[1:])
