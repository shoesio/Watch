"""Bounded, private ending previews; never prepares/replaces a playback session."""
import asyncio,hashlib,json,math,time
from pathlib import Path

class EndingPreviews:
 def __init__(self,root):
  self.root=Path(root)/'ending-previews';self.root.mkdir(exist_ok=True,mode=0o700)
  self.jobs={};self.lock=asyncio.Semaphore(1)
 def source(self,prepared):
  meta=prepared.get('_watch_meta',{})
  duration=meta.get('duration_seconds',0)
  if isinstance(duration,bool) or not isinstance(duration,(int,float)) or not math.isfinite(duration) or not 120<duration<14400 or meta.get('live'):return None
  source=prepared.get('_ending_url')
  if not source:
   path=prepared.get('path')
   if prepared.get('live') or meta.get('start_position',0)!=0 or not path or not Path(path).is_file():return None
   source=str(path)
  key=hashlib.sha256(json.dumps([meta.get('id'),meta.get('source_key'),meta.get('version_id'),duration,source if not meta.get('version_id') else ''],sort_keys=True).encode()).hexdigest()
  return source,float(duration),key
 async def get(self,prepared):
  source=self.source(prepared)
  if not source:return {'state':'unavailable'}
  url,duration,key=source;path=self.root/(key+'.mp4')
  if path.is_file() and path.stat().st_size>1000:return {'state':'ready','start':max(0,duration-90),'duration':duration,'path':path}
  if key not in self.jobs:
   if sum(not task.done() for task in self.jobs.values())>=2:return {'state':'unavailable'}
   if len(self.jobs)>32:self.jobs={k:v for k,v in self.jobs.items() if not v.done()}
   self.jobs[key]=asyncio.create_task(self.build(url,duration,path))
  job=self.jobs[key]
  if job.done():return {'state':'unavailable'}
  return {'state':'analysing'}
 async def build(self,source,duration,path):
  temp=path.with_suffix('.part.mp4');process=None
  try:
   async with self.lock:
    process=await asyncio.create_subprocess_exec('ffmpeg','-nostdin','-v','error','-rw_timeout','10000000',*(['-readrate','2'] if source.startswith(('https://','http://')) else []),'-ss',str(max(0,duration-90)),'-i',source,'-t','90','-map','0:v:0','-map','0:a:0?','-vf','fps=1,scale=640:-2','-c:v','libx264','-threads','1','-preset','ultrafast','-crf','30','-c:a','aac','-ac','1','-ar','16000','-b:a','32k','-movflags','+faststart','-y',str(temp),stdout=asyncio.subprocess.DEVNULL,stderr=asyncio.subprocess.DEVNULL)
    await asyncio.wait_for(process.wait(),90)
    if process.returncode or not temp.exists() or not 1000<temp.stat().st_size<12000000:return
    temp.chmod(0o600);temp.replace(path)
    for old in sorted(self.root.glob('*.mp4'),key=lambda p:p.stat().st_mtime,reverse=True)[24:]:old.unlink(missing_ok=True)
  except (OSError,asyncio.TimeoutError,asyncio.CancelledError):pass
  finally:
   if process and process.returncode is None:process.kill();await process.wait()
   temp.unlink(missing_ok=True)
 async def close(self):
  for job in self.jobs.values():job.cancel()
  await asyncio.gather(*self.jobs.values(),return_exceptions=True)
