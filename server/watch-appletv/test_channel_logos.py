import unittest
from channel_logos import CHANNEL_LOGOS,apply_channel_logos
class ChannelLogos(unittest.TestCase):
 def test_all_fourteen_live_channels_use_mark_assets_not_card_art(self):
  rows=[{'live':True,'live_channel':key,'artwork':'programme-still','hero':'landscape-card'} for key in CHANNEL_LOGOS]
  apply_channel_logos(rows,'http://pi:8109/')
  self.assertEqual(len(rows),14)
  self.assertEqual(len({p['channel_logo'] for p in rows}),14)
  for p in rows:
   self.assertIn('/channel-marks-v2/',p['channel_logo']);self.assertEqual(p['artwork'],'programme-still');self.assertEqual(p['hero'],'landscape-card')
 def test_on_demand_and_unknown_channels_keep_existing_art(self):
  rows=[{'live':False,'live_channel':'C5','channel_logo':'original'},{'live':True,'live_channel':'unknown','channel_logo':'fallback'}]
  apply_channel_logos(rows,'http://pi:8109')
  self.assertEqual([p['channel_logo'] for p in rows],['original','fallback'])
