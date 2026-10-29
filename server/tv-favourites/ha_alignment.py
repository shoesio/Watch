"""HA-authenticated access to Watch's shared discovery and preference service.

The paired companion credential never reaches a browser. Playback stays with HA.
"""
import json,re,time
from pathlib import Path
import aiohttp

ACTIONS={'library':('GET','/library'), 'search':('GET','/search'),
 'discover':('GET','/discover'),'shows':('GET','/shows'),'related':('GET','/related'),
 'import':('POST','/discover/import'),'favourite':('POST','/favourites')}

def read(path,default):
 try:return json.loads(Path(path).read_text())
 except (OSError,ValueError):return default

def supported(p):
 # Native ITV/Five live require device FairPlay; HA has no compatible route.
 if p.get('live_channel') in {'C5','C7','C6','C0','C8','itv','itv2','itv3','itv4','itvbe'}:return False
 if str(p.get('discovery_ref','')).startswith('itv:'):return False
 brands={b.get('id') for b in p.get('brands',[])}
 if brands and brands<={'itv'}:return False
 return p.get('provider_id')!='itv' and p.get('provider')!='ITVX'

def filter_result(value):
 for key in ('programmes','personal','hot','featured_films','featured_shows'):
  if isinstance(value.get(key),list):value[key]=[p for p in value[key] if supported(p)]
 return value

def augment(catalogue,private):
 """Read shared discovery sources without writing the provider-owned catalogue."""
 root=Path(private)/'appletv';rows={p['id']:p for p in catalogue['programmes']}
 extra=[v['programme'] for v in read(root/'discovery-library.json',{}).values() if isinstance(v,dict) and isinstance(v.get('programme'),dict)]
 extra += [p for group in read(root/'favourite-programmes.json',{}).values() for p in group]
 for p in extra:
  if supported(p) and p.get('id') and p.get('episodes') and not p.get('live_channel'):rows.setdefault(p['id'],p)
 return {**catalogue,'programmes':list(rows.values())}

class Alignment:
 def __init__(self,private):
  self.root=Path(private);self.token_path=self.root/'ha-discovery-token';self.cache=[];self.checked=0
 async def request(self,http,action,data):
  if action not in ACTIONS:raise ValueError('Unknown library action.')
  if not self.token_path.exists():raise ValueError('Shared library connection is unavailable.')
  if action=='import' and str(data.get('ref','')).startswith('itv:'):raise ValueError('ITVX requires the native Apple TV player.')
  method,path=ACTIONS[action]
  # Parameters and destination are fixed, never arbitrary URLs supplied by a client.
  params={k:str(data[k]) for k in ('q','genre','cursor','id') if k in data and isinstance(data[k],str) and len(data[k])<=2048}
  body={k:data[k] for k in ('ref','id','favourite') if k in data}
  async with http.request(method,'http://192.168.0.146:8115'+path,params=params if method=='GET' else None,json=body if method=='POST' else None,headers={'Authorization':'Bearer '+self.token_path.read_text().strip()},timeout=aiohttp.ClientTimeout(total=10 if action=='library' else 90)) as r:
   if r.status>=400:raise ValueError('The shared library could not complete this request. Please try again.')
   value=await r.json()
  # Five's FairPlay live channels are Apple-TV-only. No native sessions are requested here.
  return filter_result(value)
 async def enrich(self,http,programmes):
  if time.monotonic()-self.checked>30:
   self.checked=time.monotonic()
   try:self.cache=(await self.request(http,'library',{}))['programmes']
   except Exception:pass
  lookup={p['id']:p for p in self.cache};result=[]
  for p in programmes:
   shared=lookup.get(p['id'])
   if shared:
    for key in ('favourite','favourite_at','provider_favourite','content_rating','rating_source','show_logo','channel_logo','guide','film_rank'):
     if key in shared:p[key]=shared[key]
    eps={e['id']:e for e in shared.get('episodes',[])}
    for e in p['episodes']:
     other=eps.get(e['id'],{})
     # Only take episode stills when both views selected the same provider.
     if other.get('thumbnail_source')=='BBC episode still' and e.get('brands')==other.get('brands'):e['thumbnail']=other['thumbnail']
   result.append(p)
  from live_availability import on_air_channels
  return on_air_channels(result,time.time())
