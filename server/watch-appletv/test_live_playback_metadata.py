import unittest
from live_playback_metadata import apply_live_metadata
class LiveMetadata(unittest.TestCase):
 def test_current_show_replaces_duplicate_channel_title(self):
  rows=[{'title':'Channel 5','live':True,'channel_logo':'mark','artwork':'card','guide':{'now':{'title':'Traffic Cops','subtitle':'Police on patrol.','image':'programme-image'}},'episodes':[{'id':'live'}]}]
  meta={'title':'Channel 5','show_title':'Channel 5','live':True}
  apply_live_metadata(meta,rows,'live')
  self.assertEqual(meta['title'],'Traffic Cops');self.assertEqual(meta['show_title'],'Channel 5');self.assertEqual(meta['description'],'Police on patrol.');self.assertEqual(meta['artwork'],'programme-image');self.assertEqual(meta['channel_logo'],'mark')
 def test_missing_programme_uses_channel_fallback_once(self):
  meta={};apply_live_metadata(meta,[{'title':'BBC News','live':True,'artwork':'channel-card','episodes':[{'id':'live'}]}],'live')
  self.assertEqual(meta['title'],'BBC News');self.assertEqual(meta['artwork'],'channel-card');self.assertEqual(meta['description'],'')
 def test_vod_metadata_not_replaced(self):
  meta={'title':'Episode'};apply_live_metadata(meta,[{'title':'Show','live':False,'episodes':[{'id':'ep'}]}],'ep');self.assertEqual(meta,{'title':'Episode'})
