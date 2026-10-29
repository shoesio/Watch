import tempfile,unittest
from pathlib import Path
from progress_store import ProgressStore
class ProgressTests(unittest.TestCase):
 def setUp(self):self.tmp=tempfile.TemporaryDirectory();self.path=Path(self.tmp.name)/'progress.json'
 def tearDown(self):self.tmp.cleanup()
 def test_survives_restart_and_rewinds_five_seconds(self):
  ProgressStore(self.path).save('episode',525,1000)
  self.assertEqual(ProgressStore(self.path).resume('episode'),520)
 def test_only_confirmed_completion_clears_resume(self):
  p=ProgressStore(self.path);p.save('a',999,1000);self.assertEqual(p.resume('a'),994)
  p.save('a',500,1000,completed=True);self.assertEqual(p.resume('a'),0)
 def test_invalid_and_tiny_positions(self):
  p=ProgressStore(self.path)
  for value in [-2,float('nan'),float('inf'),90000]:
   with self.assertRaises(ValueError):p.save('a',value)
  p.save('a',5);self.assertEqual(p.resume('a'),0)
 def test_atomic_private_file(self):
  p=ProgressStore(self.path);p.save('a',40)
  self.assertEqual(self.path.stat().st_mode&0o777,0o600);self.assertFalse(self.path.with_suffix('.tmp').exists())
if __name__=='__main__':unittest.main()
