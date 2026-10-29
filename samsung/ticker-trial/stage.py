#!/usr/bin/env python3
"""Stage one controlled ticker trial, retaining the proven app for rollback."""
import argparse
from pathlib import Path
import shutil
import xml.etree.ElementTree as ET
import zipfile

ROOT=Path('/home/jhewes/samsung-home')
BACKUP=Path('/home/jhewes/tv-favourites-private/backups/watch-ticker-0102')
WORKING='SamsungWatch_0.101_Europe_20261028.zip'
TRIAL='SamsungWatch_0.102_Europe_20261028.zip'

def main():
 p=argparse.ArgumentParser();p.add_argument('--restore',action='store_true');args=p.parse_args()
 BACKUP.mkdir(parents=True,exist_ok=True)
 if args.restore:
  if not (BACKUP/'widgetlist.xml').exists():raise SystemExit('No saved installation list.')
  temporary=ROOT/'widgetlist.new'
  shutil.copy2(BACKUP/'widgetlist.xml',temporary);temporary.replace(ROOT/'widgetlist.xml')
  print('Working 0.101 installation restored. Synchronise TV apps to reinstall it.');return
 if not (BACKUP/'widgetlist.xml').exists():shutil.copy2(ROOT/'widgetlist.xml',BACKUP/'widgetlist.xml')
 if not (BACKUP/WORKING).exists():shutil.copy2(ROOT/WORKING,BACKUP/WORKING)
 with zipfile.ZipFile(ROOT/WORKING) as source:
  original=source.read('config.xml');root=ET.fromstring(original)
  assert root.findtext('widgetname')=='SamsungWatch'
  assert root.findtext('ticker')=='n'
  root.find('ver').text='0.102';root.find('ticker').text='y'
  updated=ET.tostring(root,encoding='utf-8',xml_declaration=True)
  with zipfile.ZipFile(ROOT/TRIAL,'w',zipfile.ZIP_DEFLATED) as target:
   for entry in source.infolist():target.writestr(entry,updated if entry.filename=='config.xml' else source.read(entry.filename))
 with zipfile.ZipFile(ROOT/WORKING) as original,zipfile.ZipFile(ROOT/TRIAL) as trial:
  assert trial.testzip() is None
  assert original.namelist()==trial.namelist()
  assert all(original.read(n)==trial.read(n) for n in original.namelist() if n!='config.xml')
  a=ET.fromstring(original.read('config.xml'));b=ET.fromstring(trial.read('config.xml'))
  changes=[e.tag for e,f in zip(a,b) if ET.tostring(e)!=ET.tostring(f)]
  assert changes==['ver','ticker'],changes
  (BACKUP/'trial-config.xml').write_bytes(trial.read('config.xml'))
 listroot=ET.Element('rsp',stat='ok');listing=ET.SubElement(listroot,'list');w=ET.SubElement(listing,'widget',id='SamsungWatch')
 ET.SubElement(w,'title').text='SamsungWatch'
 ET.SubElement(w,'compression',size=str((ROOT/TRIAL).stat().st_size),type='zip')
 ET.SubElement(w,'description').text='SamsungWatch'
 ET.SubElement(w,'download').text='http://192.168.0.146/'+TRIAL
 temporary=ROOT/'widgetlist.new';ET.ElementTree(listroot).write(temporary,encoding='utf-8',xml_declaration=True);temporary.replace(ROOT/'widgetlist.xml')
 print('Trial 0.102 staged alone. Only version and ticker flag changed; all app code is identical to working 0.101.')
 print('Working archive and installation list backed up. No TV commands sent.')

if __name__=='__main__':main()
