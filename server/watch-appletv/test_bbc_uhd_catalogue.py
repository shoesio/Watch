import unittest
from bbc_uhd_catalogue import uhd_available,enrich
class UHDListings(unittest.TestCase):
 def test_replacement_and_availability(self):
  self.assertTrue(uhd_available({'versions':[{'uhd':True,'kind':'technical-replacement'}]}))
  for version in [{'uhd':False},{'uhd':True,'kind':'signed'},{'uhd':True,'kind':'audio-described'},{'uhd':True,'availability':{'end':'2000-01-01T00:00:00Z'}},{'uhd':True,'availability':{'start':'2099-01-01T00:00:00Z'}}]:
   self.assertFalse(uhd_available({'versions':[version]}))
 def test_any_available_episode_makes_show_eligible(self):
  rows=[{'id':'show','episodes':[{'id':'hd'},{'id':'uhd'}]},{'id':'film','episodes':[{'id':'film-ep'}]}]
  enrich(rows,{'uhd':{'available':True},'film-ep':{'available':False}})
  self.assertTrue(rows[0]['uhd_available']);self.assertNotIn('uhd_available',rows[0]['episodes'][0]);self.assertFalse(rows[1]['uhd_available'])

 def test_combined_provider_episode_retains_bbc_uhd_availability(self):
  rows=[{'episodes':[{'id':'version-canonical'}]}]
  enrich(rows,{'bbc-source':{'available':True}},{'version-canonical':{'sources':[({'id':'bbc-source'},'BBC iPlayer'),({'id':'other-source'},'U')]}})
  self.assertTrue(rows[0]['uhd_available'])

 def test_uhd_discovery_is_not_limited_to_library_and_ignores_untrusted_links(self):
  from bbc_uhd_catalogue import listed_entries
  text='<nav><a href="/iplayer/episodes/b1111111">Outside</a></nav><article><a href="/iplayer/episodes/b2222222">New Show</a><a href="https://evil.test/iplayer/episode/b3333333">Wrong host</a><a href="/iplayer/episodes/b2222222">Duplicate</a><a href="/iplayer/episode/b4444444">A Film</a></article>'
  entries=listed_entries(text);self.assertEqual([e['id'] for e in entries],['b2222222','b4444444']);self.assertTrue(entries[1]['single'])

 def test_new_discovered_episode_keeps_current_provider_flag(self):
  rows=[{'episodes':[{'id':'new-uhd'}]}]
  enrich(rows,{}, {'new-uhd':{'sources':[({'id':'new-uhd','uhd_available':True},'BBC iPlayer')]}})
  self.assertTrue(rows[0]['uhd_available'])
