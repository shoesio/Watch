import importlib.util,sys,tempfile,unittest,zipfile
from pathlib import Path
from unittest.mock import patch
import xml.etree.ElementTree as ET
spec=importlib.util.spec_from_file_location('stage_probe',Path(__file__).with_name('stage.py'));stage=importlib.util.module_from_spec(spec);spec.loader.exec_module(stage)
class StageTests(unittest.TestCase):
 def test_preserves_paired_connection_assets_ticker_and_installer_backup(self):
  with tempfile.TemporaryDirectory() as directory:
   root=Path(directory);private=root/'backups';package=root/'SamsungWatch_old.zip'
   with zipfile.ZipFile(package,'w') as z:
    for name,content in {'config.xml':'<widget><ver>0.321</ver><ticker>n</ticker></widget>','watch.js':"var buildVersion = '0.321';",'index.html':'<html><head></head><body></body></html>','connection.js':'private fixture','watch.css':'unchanged'}.items():z.writestr(name,content)
   manifest=b'<rsp><list><widget id="SamsungWatch"><compression size="1"/><download>http://192.168.0.146/SamsungWatch_old.zip</download></widget></list></rsp>'
   (root/'widgetlist.xml').write_bytes(manifest)
   with patch.object(stage,'ROOT',root),patch.object(stage,'PRIVATE',private),patch.object(sys,'argv',['stage.py','--version','0.322']):stage.main()
   new=root/ET.parse(root/'widgetlist.xml').findtext('./list/widget/download').rsplit('/',1)[-1]
   with zipfile.ZipFile(new) as z:
    self.assertEqual(z.read('connection.js'),b'private fixture');self.assertEqual(z.read('watch.css'),b'unchanged')
    self.assertIn(b'autoboot-probe.js',z.read('index.html'));self.assertEqual(ET.fromstring(z.read('config.xml')).findtext('ticker'),'n')
   backup=next(private.iterdir());self.assertEqual((backup/'widgetlist.xml').read_bytes(),manifest)
   self.assertEqual(ET.parse(root/'widgetlist.xml').find('./list/widget/compression').get('size'),str(new.stat().st_size))
   for version,extra in [('0.323',['--trial']),('0.324',['--remove-probe'])]:
    with patch.object(stage,'ROOT',root),patch.object(stage,'PRIVATE',private),patch.object(sys,'argv',['stage.py','--version',version]+extra):stage.main()
   clean=root/ET.parse(root/'widgetlist.xml').findtext('./list/widget/download').rsplit('/',1)[-1]
   with zipfile.ZipFile(clean) as z:
    self.assertNotIn('autoboot-probe.js',z.namelist());self.assertNotIn('autoboot-trial.js',z.namelist())
    self.assertNotIn(b'autoboot-',z.read('index.html'));self.assertEqual(z.read('connection.js'),b'private fixture')
    self.assertEqual(z.read('watch.css'),b'unchanged')
   with patch.object(stage,'ROOT',root),patch.object(stage,'PRIVATE',private),patch.object(sys,'argv',['stage.py','--version','0.325','--remove-probe','--presentation']):stage.main()
   trial=root/ET.parse(root/'widgetlist.xml').findtext('./list/widget/download').rsplit('/',1)[-1]
   with zipfile.ZipFile(trial) as z:
    self.assertIn('startup-screen.js',z.namelist());self.assertIn(b'startup-screen.js',z.read('index.html'))
   with patch.object(stage,'ROOT',root),patch.object(stage,'PRIVATE',private),patch.object(sys,'argv',['stage.py','--version','0.326','--remove-probe','--remove-presentation']):stage.main()
   restored=root/ET.parse(root/'widgetlist.xml').findtext('./list/widget/download').rsplit('/',1)[-1]
   with zipfile.ZipFile(restored) as z:
    self.assertNotIn('startup-screen.js',z.namelist());self.assertNotIn(b'startup-screen.js',z.read('index.html'))
    self.assertEqual(z.read('connection.js'),b'private fixture')

if __name__=='__main__':unittest.main()
