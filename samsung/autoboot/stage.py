#!/usr/bin/env python3
"""Add startup diagnostics or an explicit remote-button trial to the CURRENT Pi Watch package.
Run on Pi. Creates a backup and changes only the app installation list/package.
No changes to firmware, root filesystem, gateway, remote launcher or boot settings.
"""
import argparse,datetime,json,os,re,shutil,zipfile
from pathlib import Path
import xml.etree.ElementTree as ET

ROOT=Path('/home/jhewes/samsung-home')
PRIVATE=Path('/home/jhewes/tv-favourites-private/backups')

def main():
 parser=argparse.ArgumentParser(description=__doc__)
 parser.add_argument('--version',required=True)
 display=parser.add_mutually_exclusive_group()
 display.add_argument('--presentation',action='store_true',help='Claim full-screen mode and suppress channel banners while Watch runs.')
 display.add_argument('--remove-presentation',action='store_true',help='Remove the full-screen startup helper.')
 parser.add_argument('--trial',action='store_true',help='Include the explicit RED/GREEN startup setting trial.')
 parser.add_argument('--remove-probe',action='store_true',help='Publish a higher-version package with the diagnostic removed.')
 args=parser.parse_args()
 if not re.fullmatch(r'\d+\.\d+',args.version):raise SystemExit('Invalid version.')
 os.umask(0o077)
 manifest=ROOT/'widgetlist.xml';original_manifest=manifest.read_bytes();tree=ET.ElementTree(ET.fromstring(original_manifest))
 widgets=tree.findall('./list/widget')
 if len(widgets)!=1 or widgets[0].get('id')!='SamsungWatch':raise SystemExit('Expected the single existing Watch entry.')
 widget=widgets[0]
 from urllib.parse import urlsplit,unquote
 href=urlsplit(widget.findtext('download'))
 filename=unquote(href.path).lstrip('/')
 if '/' in filename or not filename.endswith('.zip'):raise SystemExit('Unexpected package path.')
 original=ROOT/filename
 stamp=datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%d-%H%M%S-%f')
 backup=PRIVATE/('autoboot-readonly-'+stamp);backup.mkdir(parents=True,mode=0o700)
 shutil.copy2(manifest,backup/'widgetlist.xml');shutil.copy2(original,backup/original.name)
 version=args.version
 output=ROOT/('SamsungWatch_'+version+'_Europe_'+datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%d')+'.zip')
 if output.exists():raise SystemExit('Package version already exists; choose a new version.')
 probe=Path(__file__).with_name('probe.js').read_bytes()
 with zipfile.ZipFile(original) as before:
  config=ET.fromstring(before.read('config.xml'))
  previous=config.findtext('ver')
  if tuple(map(int,version.split('.'))) <= tuple(map(int,previous.split('.'))):raise SystemExit('Diagnostic version must increase.')
  if config.findtext('ticker')!='n':raise SystemExit('Current package is not an ordinary Watch widget.')
  with zipfile.ZipFile(output,'x',zipfile.ZIP_DEFLATED) as after:
   for entry in before.infolist():
    content=before.read(entry.filename)
    if entry.filename=='config.xml':
     config.find('ver').text=version;content=ET.tostring(config,encoding='utf-8',xml_declaration=True)
    elif entry.filename=='watch.js':
     content=re.sub(rb"var buildVersion = '[^']+'",("var buildVersion = '"+version+"'").encode(),content)
    elif entry.filename=='index.html':
     content=content.replace(b'<script src="autoboot-probe.js"></script>',b'')
     if not args.remove_probe:
      scripts=b'<script src="autoboot-probe.js"></script>'
      if args.trial:scripts+=b'<script src="autoboot-trial.js"></script>'
      content=content.replace(b'<script src="autoboot-trial.js"></script>',b'').replace(b'</head>',scripts+b'</head>')
     else:content=content.replace(b'<script src="autoboot-trial.js"></script>',b'')
     if args.remove_presentation:content=content.replace(b'<script src="startup-screen.js"></script>',b'')
     if args.presentation:content=content.replace(b'<script src="startup-screen.js"></script>',b'').replace(b'</head>',b'<script src="startup-screen.js"></script></head>')
    elif entry.filename in ('autoboot-probe.js','autoboot-trial.js') or ((args.presentation or args.remove_presentation) and entry.filename=='startup-screen.js'):continue
    after.writestr(entry.filename,content)
   if not args.remove_probe:
    after.writestr('autoboot-probe.js',probe)
    if args.trial:after.writestr('autoboot-trial.js',Path(__file__).with_name('trial.js').read_bytes())
   if args.presentation:after.writestr('startup-screen.js',Path(__file__).with_name('presentation.js').read_bytes())
 with zipfile.ZipFile(output) as check,zipfile.ZipFile(original) as before:
  assert check.testzip() is None
  assert check.read('connection.js')==before.read('connection.js')
  assert ET.fromstring(check.read('config.xml')).findtext('ticker')=='n'
  for name in before.namelist():
   if name not in ('config.xml','watch.js','index.html','autoboot-probe.js','autoboot-trial.js','startup-screen.js'):assert before.read(name)==check.read(name),name
 widget.find('compression').set('size',str(output.stat().st_size))
 widget.find('download').text='http://192.168.0.146/'+output.name
 if manifest.read_bytes()!=original_manifest:raise SystemExit('Installer changed during packaging; package saved but installer left untouched.')
 staged=manifest.with_suffix('.tmp');tree.write(staged,encoding='utf-8',xml_declaration=True);os.chmod(staged,0o644);staged.replace(manifest)
 os.chmod(output,0o644)
 (backup/'trial.json').write_text(json.dumps({'previous':previous,'trial':version,'package':output.name,'mode':'presentation' if args.presentation else 'removed' if args.remove_probe else 'explicit-trial' if args.trial else 'read-only'}))
 print(('Startup screen trial Watch ' if args.presentation else 'Diagnostic removed in Watch ' if args.remove_probe else 'Remote-button trial Watch ' if args.trial else 'Read-only Watch ')+version+' staged. Previous installer backup: '+str(backup))

if __name__=='__main__':main()
