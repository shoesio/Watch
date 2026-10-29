"""Private cross-process Watch progress shared by the dashboard and Samsung app."""
import fcntl,json,math,os,tempfile,time
from pathlib import Path

class ProgressStore:
 def __init__(self,path):
  self.path=Path(path);self.records={};self.stamp=None;self.reload()
 def reload(self):
  names={'samsung-watch-progress.json':'home-assistant-watch-progress.json','home-assistant-watch-progress.json':'samsung-watch-progress.json'}
  paths=[self.path]
  if self.path.name in names:paths.append(self.path.with_name(names[self.path.name]))
  stamps=[]
  for path in paths:
   try:stamps.append(path.stat().st_mtime_ns)
   except OSError:stamps.append(None)
  stamp=tuple(stamps)
  if stamp==self.stamp:return
  records={}
  for path in paths:
   try:
    for ident,record in json.loads(path.read_text()).items():
     if record.get('updated_at',0)>=records.get(ident,{}).get('updated_at',0):records[ident]=record
   except (OSError,ValueError):pass
  self.records=records;self.stamp=stamp
 def get(self,episode):self.reload();return self.records.get(episode,{})
 def save(self,episode,position,duration=0,completed=False):
  position=float(position);duration=float(duration or 0)
  if not math.isfinite(position) or not 0<=position<=86400:raise ValueError('Invalid playback position.')
  if not math.isfinite(duration) or not 0<=duration<=86400:duration=0
  if duration:position=min(position,duration)
  record={'position':round(position,1),'duration':duration,'completed':bool(completed),'updated_at':time.time()}
  self.path.parent.mkdir(parents=True,exist_ok=True)
  with self.path.with_suffix('.lock').open('a') as lock:
   fcntl.flock(lock,fcntl.LOCK_EX);self.reload();self.records[episode]=record
   self.records=dict(sorted(self.records.items(),key=lambda p:p[1].get('updated_at',0),reverse=True)[:2000])
   fd,name=tempfile.mkstemp(prefix='.progress-',dir=self.path.parent)
   try:
    with os.fdopen(fd,'w') as output:json.dump(self.records,output)
    os.replace(name,self.path);self.stamp=None;self.reload()
   finally:Path(name).unlink(missing_ok=True)
  return record
 def resume(self,episode):
  r=self.get(episode);position=r.get('position',0)
  return max(0,position-5) if not r.get('completed') and position>=10 else 0
