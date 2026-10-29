import unittest
from launch import PowerCycle
class PowerTests(unittest.TestCase):
 def test_never_launches_on_start_or_brief_network_loss(self):
  p=PowerCycle()
  self.assertFalse(p.update(True,0))
  self.assertFalse(p.update(False,5))
  self.assertFalse(p.update(True,12))
  self.assertFalse(p.update(True,100))
 def test_once_after_sustained_off_and_ready(self):
  p=PowerCycle()
  for online,now in [(False,0),(False,20),(True,22),(True,40)]:self.assertFalse(p.update(online,now))
  self.assertTrue(p.update(True,47))
  self.assertFalse(p.update(True,100))
 def test_unstable_boot_resets_wait(self):
  p=PowerCycle()
  for online,now in [(False,0),(False,20),(True,25),(False,40),(True,44),(True,68)]:self.assertFalse(p.update(online,now))
  self.assertTrue(p.update(True,69))
if __name__=='__main__':unittest.main()
