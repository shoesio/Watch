#!/usr/bin/env python3
"""UxPlay callback adapter to the previously identified T27B551 DLNA renderer."""
import concurrent.futures, http.server, json, logging, os, re, secrets, socketserver, subprocess, threading, time, urllib.request
from urllib.parse import urljoin
import xml.etree.ElementTree as ET
from pathlib import Path
from xml.sax.saxutils import escape
TV='192.168.0.123'; PI='192.168.0.146'; PORT=8116
MAX_HEIGHT=int(os.environ.get('SAMSUNG_MAX_HEIGHT','1080'))
MAX_FPS=float(os.environ.get('SAMSUNG_MAX_FPS','30'))
ROOT=Path(__file__).resolve().parent
SOCKET=str(ROOT/'bridge.sock')
lock=threading.RLock(); jobs=concurrent.futures.ThreadPoolExecutor(max_workers=1)
state=dict(duration=0.,position=0.,rate=0.,ready=0,empty=1,full=0,error=None)
current=None

def soap(action, **values):
    body=''.join('<%s>%s</%s>'%(k,escape(str(v)),k) for k,v in dict(InstanceID=0,**values).items())
    data=('<s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/"><s:Body><u:'+action+' xmlns:u="urn:schemas-upnp-org:service:AVTransport:1">'+body+'</u:'+action+'></s:Body></s:Envelope>').encode()
    req=urllib.request.Request('http://'+TV+':7676/smp_26_',data,{'Content-Type':'text/xml; charset="utf-8"','SOAPACTION':'"urn:schemas-upnp-org:service:AVTransport:1#'+action+'"','User-Agent':'SEC_HHP_[TV]'})
    with urllib.request.urlopen(req,timeout=3) as r: root=ET.fromstring(r.read())
    return {el.tag.split('}')[-1]:el.text for el in root.iter() if len(el)==0}

def seconds(text):
    try:
        h,m,s=map(float,text.split(':')); return h*3600+m*60+s
    except (ValueError,AttributeError): return 0.

HLS_OPTIONS=['-protocol_whitelist','file,http,https,tcp,tls,crypto','-allowed_extensions','ALL','-allowed_segment_extensions','ALL','-extension_picky','0']

def select_hls(url):
    with urllib.request.urlopen(url,timeout=8) as r: manifest=r.read(2_000_000).decode()
    (ROOT/'last-source.m3u8').write_text(manifest)
    if '#EXT-X-STREAM-INF:' not in manifest: return url
    lines=manifest.splitlines()
    def attrs(line):
        return {k:v.strip('"') for k,v in re.findall(r'([A-Z0-9-]+)=("[^"\n]*"|[^,\n]*)',line)}
    choices=[]
    for i,line in enumerate(lines[:-1]):
        if not line.startswith('#EXT-X-STREAM-INF:'): continue
        a=attrs(line)
        if not any(c.strip().lower().startswith(('avc1','avc3')) for c in a.get('CODECS','').split(',')): continue
        w,h=map(int,a.get('RESOLUTION','0x0').split('x')); fps=float(a.get('FRAME-RATE',0))
        if 0<w<=1920 and 0<h<=MAX_HEIGHT and 0<fps<=MAX_FPS+0.1:
            choices.append((h,int(a.get('BANDWIDTH',0)),i,a))
    if not choices: raise ValueError('No H.264 HLS variant within configured resolution/frame-rate limits')
    h,_,i,a=max(choices)
    result=['#EXTM3U','#EXT-X-VERSION:3']
    for line in lines:
        if line.startswith('#EXT-X-MEDIA:'):
            info=attrs(line)
            if info.get('TYPE')=='AUDIO' and info.get('GROUP-ID')==a.get('AUDIO'):
                result.append(re.sub(r'URI="([^"]+)"',lambda m:'URI="'+urljoin(url,m[1])+'"',line))
    result.extend([lines[i],urljoin(url,lines[i+1])])
    target=ROOT/('selected-'+secrets.token_hex(8)+'.m3u8')
    target.write_text('\n'.join(result)+'\n')
    logging.info('selected HLS %s, %s fps, codecs %s',a.get('RESOLUTION'),a.get('FRAME-RATE'),a.get('CODECS'))
    return str(target)

def probe(url):
    data=json.loads(subprocess.check_output(['ffprobe','-v','error',*HLS_OPTIONS,'-show_streams','-show_format','-of','json',url],timeout=35))
    candidates=[]
    for s in data['streams']:
        n,d=map(int,s.get('avg_frame_rate','0/1').split('/')); fps=n/d if d else 0
        if s.get('codec_name')=='h264' and s.get('width',9999)<=1920 and s.get('height',9999)<=MAX_HEIGHT and 0<fps<=MAX_FPS+0.1 and s.get('level',99)<=41:
            candidates.append(s)
    audios=[s for s in data['streams'] if s.get('codec_name')=='aac' and s.get('channels',99)<=2]
    if not candidates or not audios: raise ValueError('No H.264 Level4.1 / stereo AAC tracks within configured limits; transcoding is disabled')
    video=max(candidates,key=lambda s:(s['height'],int(s.get('bit_rate',0))))
    # Same HLS program when program IDs are available is selected by ffmpeg's stream indices.
    return video['index'],audios[0]['index'],float(data.get('format',{}).get('duration',0))

def begin(url,offset):
    global current
    (ROOT/'last-input.json').write_text(json.dumps({'url':url,'offset':offset}))
    if not url.startswith(('http://','https://')): raise ValueError('Expected HTTP HLS URL')
    url=select_hls(url)
    video,audio,duration=probe(url)
    with lock:
        current=dict(url=url,offset=max(0,offset),video=video,audio=audio,token=secrets.token_hex(16),process=None)
        state.update(duration=duration,position=offset,ready=0,empty=1,error=None)
    play_current()

def play_current():
    with lock:
        session=current
        if not session: return
        media=f'http://{PI}:{PORT}/stream/{session["token"]}.ts'
    metadata='<DIDL-Lite xmlns="urn:schemas-upnp-org:metadata-1-0/DIDL-Lite/" xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:upnp="urn:schemas-upnp-org:metadata-1-0/upnp/"><item id="airplay" parentID="0" restricted="1"><dc:title>YouTube AirPlay</dc:title><upnp:class>object.item.videoItem</upnp:class><res protocolInfo="http-get:*:video/mpeg:*">'+escape(media)+'</res></item></DIDL-Lite>'
    soap('SetAVTransportURI',CurrentURI=media,CurrentURIMetaData=metadata); soap('Play',Speed=1)
    with lock: state.update(rate=1,ready=1,empty=0)

def action(cmd,value,url=''):
    global current
    try:
        if cmd=='play':
            stop_process(); begin(url,value)
        elif cmd=='stop':
            with lock: active=current is not None
            if active: soap('Stop')
            stop_process()
            with lock: current=None; state.update(rate=0,ready=0,empty=1)
        elif cmd=='rate':
            with lock: active=current is not None
            if active:
                desired='PAUSED_PLAYBACK' if value==0 else 'PLAYING'
                for attempt in range(5):
                    try:
                        if soap('GetTransportInfo').get('CurrentTransportState')!=desired:
                            soap('Pause') if value==0 else soap('Play',Speed=1)
                        with lock: state['rate']=int(value==1)
                        break
                    except Exception:
                        if attempt==4: raise
                        time.sleep(.6)
        elif cmd=='seek':
            with lock: session=current
            if session:
                soap('Stop'); stop_process()
                with lock: session.update(offset=max(0,min(value,state['duration'] or value)),token=secrets.token_hex(16)); state['position']=session['offset']
                play_current()
        logging.info('command %s completed',cmd)
    except Exception as e:
        with lock:
            state['error']=str(e)
            if cmd in ('play','seek'): state.update(ready=0,empty=1,rate=0)
        logging.error('%s failed: %s',cmd,e)

def stop_process():
    with lock: proc=current.get('process') if current else None
    if proc and proc.poll() is None:
        proc.terminate()
        try: proc.wait(timeout=3)
        except subprocess.TimeoutExpired: proc.kill(); proc.wait()

class RPC(socketserver.StreamRequestHandler):
    def handle(self):
        try:
            fields=self.rfile.readline(65537).decode().strip().split(' ',2)
            cmd,value=fields[:2]; value=float(value)
            if cmd!='status':
                if cmd not in ('play','stop','seek','rate'): raise ValueError('Unknown command')
                url=bytes.fromhex(fields[2]).decode() if len(fields)>2 else ''
                jobs.submit(action,cmd,value,url)
            with lock: result='{duration} {position} {rate} {ready} {empty} {full}\n'.format(**state)
            self.wfile.write(result.encode())
        except Exception: self.wfile.write(b'0 0 0 0 1 0\n')

class Media(http.server.BaseHTTPRequestHandler):
    def do_HEAD(self):
        with lock: session=current.copy() if current else None
        if self.client_address[0] not in (TV,'127.0.0.1',PI) or not session or self.path!=f'/stream/{session["token"]}.ts':
            self.send_error(404); return
        self.send_response(200); self.send_header('Content-Type','video/mpeg'); self.send_header('Connection','close'); self.send_header('contentFeatures.dlna.org','DLNA.ORG_OP=00;DLNA.ORG_CI=0'); self.send_header('transferMode.dlna.org','Streaming'); self.end_headers()
    def do_GET(self):
        with lock: session=current.copy() if current else None
        if self.client_address[0] not in (TV,'127.0.0.1',PI) or not session or self.path!=f'/stream/{session["token"]}.ts':
            self.send_error(404); return
        with lock:
            if current['process'] and current['process'].poll() is None: self.send_error(409); return
            args=['ffmpeg','-nostdin','-v','error','-rw_timeout','15000000',*HLS_OPTIONS,'-ss',str(session['offset']),'-i',session['url'],'-map',f'0:{session["video"]}','-map',f'0:{session["audio"]}','-c','copy','-bsf:v','h264_mp4toannexb','-f','mpegts','-mpegts_flags','+resend_headers','pipe:1']
            proc=subprocess.Popen(args,stdout=subprocess.PIPE,stderr=open(ROOT/'remux.log','ab')); current['process']=proc
        self.send_response(200); self.send_header('Content-Type','video/mpeg'); self.send_header('Connection','close'); self.send_header('contentFeatures.dlna.org','DLNA.ORG_OP=00;DLNA.ORG_CI=0'); self.send_header('transferMode.dlna.org','Streaming'); self.end_headers()
        try:
            while chunk:=proc.stdout.read(188*128): self.wfile.write(chunk)
        except (BrokenPipeError,ConnectionResetError): pass
        finally:
            if proc.poll() is None: proc.terminate()
            try: proc.wait(timeout=3)
            except subprocess.TimeoutExpired: proc.kill(); proc.wait()
            proc.stdout.close()
    def log_message(self,fmt,*args): logging.info(fmt,*args)

def poll():
    while True:
        time.sleep(1)
        with lock: session=current; active=state['ready']
        if not session: continue
        try:
            pos=soap('GetPositionInfo'); transport=soap('GetTransportInfo')
            with lock:
                if current is session:
                    state['position']=session['offset']+seconds(pos.get('RelTime'))
                    status=transport.get('CurrentTransportState')
                    state['rate']=int(status=='PLAYING')
                    state['ready']=int(status in ('PLAYING','PAUSED_PLAYBACK'))
                    state['empty']=int(status=='TRANSITIONING')
                    state['error']=None if transport.get('CurrentTransportStatus')=='OK' else 'Samsung transport error'
        except Exception as e:
            with lock: state.update(error=str(e),ready=0,empty=1,rate=0)

if __name__=='__main__':
    os.umask(0o077); logging.basicConfig(level=logging.INFO,format='%(asctime)s %(message)s')
    Path(SOCKET).unlink(missing_ok=True)
    rpc=socketserver.ThreadingUnixStreamServer(SOCKET,RPC)
    threading.Thread(target=rpc.serve_forever,daemon=True).start(); threading.Thread(target=poll,daemon=True).start()
    http.server.ThreadingHTTPServer((PI,PORT),Media).serve_forever()
