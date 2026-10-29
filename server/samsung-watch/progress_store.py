"""Small, atomic, private per-episode progress store for this household TV."""
import json,math,os,time
from pathlib import Path

class ProgressStore:
 def __init__(self,path):
  self.path=Path(path);self.records={}
  try:self.records=json.loads(self.path.read_text())
  except (OSError,ValueError):pass
 def get(self,episode):return self.records.get(episode,{})
 def save(self,episode,position,duration=0,completed=False):
  position=float(position);duration=float(duration or 0)
  if not math.isfinite(position) or not 0<=position<=86400:raise ValueError('Invalid playback position.')
  if not math.isfinite(duration) or not 0<=duration<=86400:duration=0
  if duration:position=min(position,duration)
  record={'position':round(position,1),'duration':duration,'completed':bool(completed),'updated_at':time.time()}
  self.records[episode]=record
  self.records=dict(sorted(self.records.items(),key=lambda p:p[1].get('updated_at',0),reverse=True)[:2000])
  self.path.parent.mkdir(parents=True,exist_ok=True)
  temporary=self.path.with_suffix('.tmp');temporary.write_text(json.dumps(self.records));temporary.chmod(0o600);os.replace(temporary,self.path)
  return record
 def resume(self,episode):
  r=self.get(episode);position=r.get('position',0)
  if r.get('completed') or position<10:return 0
  duration=r.get('duration',0)
  return max(0,position-5)
