"""One configured HA lamp, owned by a short-lived playback lease; no frame data."""
import asyncio,math,re,time
import aiohttp

class SceneLight:
 def __init__(self,entity,ha_url,token,clock=time.monotonic,request=None):
  self.entity=entity if isinstance(entity,str) and re.fullmatch(r'light\.[a-z0-9_]+',entity) else None
  self.url=ha_url.rstrip('/');self.token=token;self.clock=clock;self.request_override=request
  self.http=None;self.lock=asyncio.Lock();self.owner=None;self.original=None;self.last=None;self.seen=0;self.sent=0;self.checked=0;self.yielded=None;self.brightness=None;self.transition=3.0;self.expected_off=False;self.matching_brightness=False
 async def request(self,path,data=None):
  if self.request_override:return await self.request_override(path,data)
  if self.http is None:self.http=aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=5))
  async with self.http.request('GET' if data is None else 'POST',self.url+'/api/'+path,json=data,headers={'Authorization':'Bearer '+self.token}) as response:
   response.raise_for_status();return await response.json()
 def status(self):return {'configured':bool(self.entity),'active':self.owner is not None,'manual_override':self.yielded is not None}
 @staticmethod
 def distance(a,b):return abs((a-b+180)%360-180)
 def changed(self,state,check_colour=True):
  if not self.last:return False
  a=state.get('attributes',{});hs=a.get('hs_color')
  return (check_colour and state.get('state')!=('off' if self.expected_off else 'on')) or (not self.expected_off and check_colour and hs and ((min(float(hs[1]),self.last[1])>5 and self.distance(float(hs[0]),self.last[0])>15) or abs(float(hs[1])-self.last[1])>12)) or (not self.expected_off and check_colour and a.get('brightness') is not None and self.brightness is not None and abs(a['brightness']-self.brightness)>8)
 async def colour(self,ticket,hue,white=False,precise=False,saturation=100,transition=3,brightness=-1):
  if not isinstance(white,bool):raise ValueError("Invalid neutral flag")
  if isinstance(transition,bool) or not isinstance(transition,(int,float)) or not math.isfinite(transition) or not 0<=transition<=10:raise ValueError('Invalid transition')
  if isinstance(brightness,bool) or not isinstance(brightness,(int,float)) or not math.isfinite(brightness) or not (brightness==-1 or 0<=brightness<=100):raise ValueError("Invalid brightness")
  requested_transition=0.4 if precise else float(transition)
  if isinstance(hue,bool) or isinstance(saturation,bool) or not isinstance(hue,(int,float)) or not isinstance(saturation,(int,float)) or not math.isfinite(hue) or not math.isfinite(saturation) or not 0<=hue<=360 or not 0<=saturation<=100:raise ValueError('Invalid scene colour')
  saturation=0 if white else saturation
  if not self.entity:return self.status()
  async with self.lock:
   if self.yielded==ticket:return self.status()
   now=self.clock()
   if self.owner is not None and self.owner!=ticket:return self.status()
   if self.owner is None:
    state=await self.request('states/'+self.entity)
    if state.get('state') not in ('on','off') or not set(state.get('attributes',{}).get('supported_color_modes',[]))&{'hs','xy','rgb','rgbw','rgbww'}:return self.status()
    self.expected_off=False;self.matching_brightness=False
    self.owner=ticket;self.original=state;self.last=None;self.checked=now;self.yielded=None;self.brightness=state.get('attributes',{}).get('brightness') if state['state']=='on' else None
   self.seen=now
   if now-self.checked>=5 and self.last:
    state=await self.request('states/'+self.entity);self.checked=now
    if self.changed(state,check_colour=now-self.sent>=self.transition+0.5):self.yielded=ticket;self.owner=None;self.original=None;self.last=None;return self.status()
    if self.brightness is None:self.brightness=state.get('attributes',{}).get('brightness')
   target_brightness=round(brightness*255/100) if brightness>=0 else (self.original.get("attributes",{}).get("brightness",255) if self.matching_brightness else self.brightness)
   target_off=brightness==0
   brightness_changed=target_off!=self.expected_off or (target_brightness is not None and self.brightness!=target_brightness)
   if self.last and (now-self.sent<(0.25 if precise else 0.4) or (self.distance(hue,self.last[0])<(0.2 if precise else 5) and abs(saturation-self.last[1])<5 and self.transition==requested_transition and not brightness_changed)):return self.status()
   self.transition=requested_transition
   data={'entity_id':self.entity,'transition':self.transition}
   if not target_off:
    data['hs_color']=[round(hue%360,1),round(saturation,1)]
    if brightness>=0 or self.matching_brightness:data['brightness']=max(1,target_brightness or 255)
   await self.request('services/light/'+('turn_off' if target_off else 'turn_on'),data)
   self.expected_off=target_off
   if target_brightness is not None:self.brightness=target_brightness
   self.matching_brightness=brightness>=0
   self.last=(hue%360,saturation);self.sent=now;return self.status()
 async def restore(self,ticket=None):
  async with self.lock:
   if ticket is not None and ticket!=self.owner:
    if ticket==self.yielded:self.yielded=None
    return
   if self.owner is None:return
   state=await self.request('states/'+self.entity)
   original=self.original
   if self.changed(state,check_colour=self.clock()-self.sent>=self.transition+0.5):self.owner=None;self.original=None;self.last=None;return
   attrs=original.get('attributes',{});data={'entity_id':self.entity,'transition':3.0}
   if original['state']=='off':service='turn_off'
   else:
    service='turn_on'
    if attrs.get('brightness') is not None:data['brightness']=attrs['brightness']
    mode=attrs.get('color_mode');key='color_temp_kelvin' if mode=='color_temp' else 'xy_color' if mode=='xy' else 'hs_color'
    if attrs.get(key) is not None:data[key]=attrs[key]
   await self.request('services/light/'+service,data)
   self.owner=None;self.original=None;self.last=None
 async def expire(self):
  if self.owner is not None and self.clock()-self.seen>12:await self.restore()
 async def close(self):
  try:await self.restore()
  finally:
   if self.http:await self.http.close();self.http=None
