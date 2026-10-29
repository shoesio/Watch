"""Provider resolution and progressive codec-copy delivery. Private data stays server-side."""
import base64,copy,contextlib,http.client,json,os,re,subprocess,tempfile,threading
from pathlib import Path
from urllib.parse import urljoin,urlsplit
import xml.etree.ElementTree as ET
import requests
import select
from uuid import UUID
from Crypto.Cipher import AES
from Crypto.Util.Padding import unpad
from pywidevine.cdm import Cdm
from pywidevine.device import Device
from pywidevine.pssh import PSSH

NS={'m':'urn:mpeg:dash:schema:mpd:2011','c':'urn:mpeg:cenc:2013'}
ET.register_namespace('',NS['m']);ET.register_namespace('cenc',NS['c'])
CLIENT='Basic eUExTHB6dGtHZUhaRDZuU2E3QzFBQUY2dkhwelZOblU6UXFFbUVnVVVVT1hUa3piNg=='
UA='Mozilla/5.0 (X11; Linux aarch64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/151.0.0.0 Safari/537.36'
C4_LICENSE='https://c4.eme.lp.aws.redbeemedia.com/wvlicenceproxy-service/widevine/acquire'

class ProviderResolver:
 def __init__(self,root):
  self.root=Path(root);self.work=self.root/'playback';self.work.mkdir(mode=0o700,exist_ok=True);self.lock=threading.Lock()
 def session(self):
  s=requests.Session();s.headers['User-Agent']=UA;return s
 def channel4_token(self):
  with self.lock:
   p=self.root/'channel4-session.json';a=json.loads(p.read_text())
   import time
   expired=int(a.get('issuedAt',0))/1000+int(a.get('expiresIn',0))<time.time()+90
   if expired:
    with self.session() as s:
     r=s.post('https://api.channel4.com/online/v2/auth/token',headers={'Authorization':CLIENT},data={'grant_type':'refresh_token','refresh_token':a['refreshToken']},timeout=25);r.raise_for_status();a=r.json()
    tmp=p.with_suffix('.tmp');tmp.write_text(json.dumps(a));os.chmod(tmp,0o600);tmp.replace(p)
   return a['accessToken']
 def get(self,url,headers=None):
  # Keep signed resource URLs byte-for-byte; generic URL canonicalization breaks C4 signatures.
  u=urlsplit(url)
  if u.scheme not in ('http','https'):raise ValueError('Unsupported provider source.')
  conn=(http.client.HTTPSConnection if u.scheme=='https' else http.client.HTTPConnection)(u.hostname,timeout=25)
  try:
   conn.request('GET',u.path+('?' +u.query if u.query else ''),headers={'User-Agent':UA,**(headers or {})});r=conn.getresponse()
   if r.status!=200:raise ValueError('The provider source is temporarily unavailable.')
   data=r.read(4*1024*1024+1)
   if len(data)>4*1024*1024:raise ValueError('Provider manifest is too large.')
   return data
  finally:conn.close()
 def resolve(self,episode):
  provider=episode['provider_id'];s=self.session()
  try:
   if provider=='channel4' and episode.get('live'):
    channel=episode['provider_episode_id'];r=s.get('https://www.channel4.com/simulcast/channels/'+channel,timeout=25);r.raise_for_status();meta=r.json()
    profile=next(p for p in meta['channelInfo']['videoProfiles'] if p['name']=='dashwv-live-stream-iso-dash-sp-tl');src=profile['streams'][0];manifest=src['uri']
    decoded=unpad(AES.new(b'n9cLieYkqwzNCqvi',AES.MODE_CBC,b'odzcU3WdUiXLucVd').decrypt(base64.b64decode(src['token'])),16).decode()
    authorization=decoded.split('&t=',1)[1]
    def licence(challenge):
     r=s.post(C4_LICENSE,json={'token':authorization,'video':{'type':'simulcast','url':manifest},'message':base64.b64encode(challenge).decode()},headers={'Origin':'https://www.channel4.com','Referer':'https://www.channel4.com/'},timeout=25);r.raise_for_status();return base64.b64decode(r.json()['license'])
    headers={'Origin':'https://www.channel4.com','Referer':'https://www.channel4.com/'}
   elif provider=='channel4':
    pid=episode['provider_episode_id'];r=s.get('https://api.channel4.com/online/v1/vod/stream/'+pid,params={'client':'amazonfire-dash'},headers={'Authorization':'Bearer '+self.channel4_token()},timeout=25);r.raise_for_status();meta=r.json()
    profile=next(p for p in meta['videoProfiles'] if 'dashwv' in p['name']);src=profile['streams'][0];manifest=src['uri']
    authorization=unpad(AES.new(b'K2C8Q09D7HJ385AB',AES.MODE_CBC,b'B3LKVU05F3IDLVME').decrypt(base64.b64decode(src['token'])),16).decode().split('|')[1]
    def licence(challenge):
     r=s.post(C4_LICENSE,json={'request_id':episode['asset_id'],'token':authorization,'video':{'type':'ondemand','url':manifest},'message':base64.b64encode(challenge).decode()},headers={'Origin':'https://www.channel4.com','Referer':'https://www.channel4.com/'},timeout=25);r.raise_for_status();return base64.b64decode(r.json()['license'])
    headers={'Origin':'https://www.channel4.com','Referer':'https://www.channel4.com/'}
   elif provider=='channel5':
    from five_provider import media
    asset=media(self.root,episode['provider_episode_id'],bool(episode.get('live')))
    manifest=asset['renditions'][0].get('fallbackurl') if episode.get('live') else None
    manifest=manifest or asset['renditions'][0]['url']
    if not episode.get('live'):
     parsed=urlsplit(manifest);parts=parsed.path.split('/');parts[-1]=parts[-1].split('-')[0].split('_')[0]
     path='/'.join(parts)
     if not path.endswith('.mpd'):path+='.mpd'
     manifest=parsed._replace(path=path).geturl()
    license_url=asset['keyserver']
    def licence(challenge):
     r=s.post(license_url,data=challenge,timeout=25);r.raise_for_status();return r.content
    headers={'Referer':'https://www.channel5.com/'}
   elif provider=='u':
    vid=episode['provider_episode_id'];player='https://players.brightcove.net/1242911124001/0RyQs9qPh_default/index.html?videoId='+vid
    r=s.get(player,timeout=25);r.raise_for_status();policy=re.search(r'''policyKey\s*:\s*['"]([\w-]+)''',r.text)[1]
    r=s.get('https://edge.api.brightcove.com/playback/v1/accounts/1242911124001/videos/'+vid,headers={'Accept':'application/json;pk='+policy,'Referer':player},timeout=25);r.raise_for_status();meta=r.json()
    src=next(x for x in meta['sources'] if x.get('type')=='application/dash+xml' and x.get('src','').startswith('https:') and 'com.widevine.alpha' in x.get('key_systems',{}));manifest=src['src'];license_url=src['key_systems']['com.widevine.alpha']['license_url']
    def licence(challenge):
     r=s.post(license_url,data=challenge,timeout=25);r.raise_for_status();return r.content
    headers={'Referer':'https://u.co.uk/'}
   else:raise ValueError('Unsupported provider.')
   if provider=='channel5':
    response=s.get(manifest,headers=headers,timeout=25);response.raise_for_status();manifest_data=response.content
   else:manifest_data=self.get(manifest,headers)
   root=ET.fromstring(manifest_data);selected=[]
   if provider=='channel5':
    definitions={cp.get('refId'):cp for cp in root.findall('.//m:ContentProtection',NS) if cp.get('refId')}
    for cp in root.findall('.//m:ContentProtection',NS):
     definition=definitions.get(cp.get('ref'))
     if definition is not None:
      cp.attrib.update({k:v for k,v in definition.attrib.items() if k not in ('ref','refId')})
      for child in definition:cp.append(copy.deepcopy(child))
   for kind in ('video','audio'):
    candidates=[]
    for period in root.findall('m:Period',NS):
     for ad in period.findall('m:AdaptationSet',NS):
      role=' '.join(e.get('value','') for e in ad.findall('m:Role',NS))
      if kind=='audio' and ('description' in role or 'alternate' in role):continue
      for rep in ad.findall('m:Representation',NS):
       mime=rep.get('mimeType',ad.get('mimeType',''));ct=ad.get('contentType','')
       if kind not in mime and ct!=kind:continue
       if kind=='video' and (int(rep.get('height','0'))>720 or not rep.get('codecs',ad.get('codecs','avc1')).startswith(('avc','h264'))):continue
       if kind=='audio' and not rep.get('codecs',ad.get('codecs','mp4a')).startswith('mp4a'):continue
       candidates.append((int(rep.get('bandwidth','0')),period,ad,rep))
    if not candidates:raise ValueError('No compatible H.264/AAC source is available.')
    _,period,ad,rep=max(candidates,key=lambda x:x[0]);selected.append((kind,period,ad,rep))
   cd=Cdm.from_device(Device.load(self.root/'device.wvd'));keys={}
   for kind,period,ad,rep in selected:
    protections=rep.findall('m:ContentProtection',NS)+ad.findall('m:ContentProtection',NS)
    pssh=next((x.text for cp in protections if 'edef8ba9' in cp.get('schemeIdUri','').lower() for x in cp.findall('c:pssh',NS)),None)
    if not pssh:
     kk=next((cp.get('{'+NS['c']+'}default_KID','') for cp in protections if cp.get('{'+NS['c']+'}default_KID')),None)
     if not kk:raise ValueError('The provider returned an unsupported licence format.')
     pssh=PSSH.new(system_id=PSSH.SystemId.Widevine,key_ids=[UUID(kk)]).dumps()
    session=cd.open()
    try:
     cd.parse_license(session,licence(cd.get_license_challenge(session,PSSH(pssh))))
     keys.update({k.kid.hex:k.key.hex() for k in cd.get_keys(session) if k.type=='CONTENT'})
    finally:cd.close(session)
   tracks=[]
   for kind,period,ad,rep in selected:
    protections=rep.findall('m:ContentProtection',NS)+ad.findall('m:ContentProtection',NS)
    kid=next((cp.get('{'+NS['c']+'}default_KID','').replace('-','') for cp in protections if cp.get('{'+NS['c']+'}default_KID')),None)
    key=keys.get(kid) or (next(iter(keys.values())) if len(keys)==1 else None)
    if not key:raise ValueError('The provider did not authorize the selected track.')
    base=manifest
    for node in (root,period,ad,rep):
     e=node.find('m:BaseURL',NS)
     if e is not None and e.text:base=urljoin(base,e.text)
    template=next((node.find('m:SegmentTemplate',NS) for node in (rep,ad,period) if node.find('m:SegmentTemplate',NS) is not None),None)
    if template is None and base!=manifest:
     tracks.append({'kind':kind,'url':base,'key':key,'dash':False})
    else:
     filtered=copy.deepcopy(root)
     for pp in list(filtered.findall('m:Period',NS)):
      for aa in list(pp.findall('m:AdaptationSet',NS)):
       if aa.get('id')!=ad.get('id') or aa.get('mimeType')!=ad.get('mimeType'):pp.remove(aa);continue
       for rr in list(aa.findall('m:Representation',NS)):
        if rr.get('id')!=rep.get('id'):aa.remove(rr)
     e=filtered.find('m:BaseURL',NS)
     if e is None:e=ET.Element('{'+NS['m']+'}BaseURL');filtered.insert(0,e)
     e.text=urljoin(manifest,e.text or '.')
     tracks.append({'kind':kind,'mpd':ET.tostring(filtered,encoding='utf-8'),'key':key,'dash':True})
   return {'tracks':tracks,'headers':headers,'episode':episode}
  finally:s.close()
 def open(self,resolved,probe=False):return ProviderStream(self,resolved,probe)

class ProviderStream:
 def __init__(self,resolver,resolved,probe=False):
  self.resolver=resolver;self.directory=Path(tempfile.mkdtemp(prefix='stream-',dir=resolver.work));self.log=(self.directory/'ffmpeg.log').open('wb');cmd=['ffmpeg','-nostdin','-v','error','-copyts']
  position=float(resolved['episode'].get('_start_offset',0))
  for i,t in enumerate(resolved['tracks']):
   if i==0 and not probe:cmd+=['-readrate','1']
   cmd+=['-protocol_whitelist','file,http,https,tcp,tls,crypto']
   if t['dash']:
    p=self.directory/(t['kind']+'.mpd');p.write_bytes(t['mpd']);cmd+=['-cenc_decryption_key',t['key']];url=str(p)
   else:cmd+=['-decryption_key',t['key']];url=t['url']
   if position:cmd+=['-ss',str(position)]
   if not t['dash']:cmd+=['-user_agent',UA]
   cmd+=['-i',url]
  cmd+=['-map','0:v:0','-map','1:a:0','-c','copy','-mpegts_copyts','1','-muxdelay','0','-flush_packets','1','-f','mpegts','pipe:1']
  self.process=subprocess.Popen(cmd,stdout=subprocess.PIPE,stderr=self.log,bufsize=0);self.closed=False
 def read(self,size):
  if not select.select([self.process.stdout],[],[],30)[0]:raise ValueError('The provider stream stalled. Please try again.')
  return self.process.stdout.read(size)
 def close(self):
  if self.closed:return
  self.closed=True
  if self.process.poll() is None:self.process.terminate()
  with contextlib.suppress(subprocess.TimeoutExpired):self.process.wait(timeout=5)
  if self.process.poll() is None:self.process.kill();self.process.wait()
  self.process.stdout.close();self.log.close()
  import shutil
  shutil.copyfile(self.directory/'ffmpeg.log',self.resolver.root/'last-provider-ffmpeg.log')
  import shutil
  shutil.rmtree(self.directory,ignore_errors=True)
