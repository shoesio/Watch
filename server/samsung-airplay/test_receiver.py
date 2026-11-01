#!/usr/bin/env python3
"""Integration test using a synthetic HLS fixture, not a YouTube/iPhone session."""
import json,plistlib,http.client,uuid,sys,time
SESSION=str(uuid.uuid4())
def request(path,data=b''):
    conn=http.client.HTTPConnection('127.0.0.1',7111,timeout=5)
    conn.request('POST' if data else 'GET',path,data,{'X-Apple-Session-ID':SESSION,'Content-Type':'application/x-apple-binary-plist','User-Agent':'MediaControl/1.0'})
    response=conn.getresponse(); body=response.read(int(response.getheader("Content-Length",0)))
    print(path,response.status,body[:1200].decode(errors='replace')); conn.close()
if __name__=='__main__':
    cmd=sys.argv[1]
    if cmd=='play': request('/play',plistlib.dumps({'uuid':str(uuid.uuid4()),'Content-Location':'http://127.0.0.1:18116/test.m3u8','Start-Position-Seconds':0.0},fmt=plistlib.FMT_BINARY))
    elif cmd=='pause': request('/rate?value=0',b'x')
    elif cmd=='resume': request('/rate?value=1',b'x')
    elif cmd=='seek': request('/scrub?position=20',b'x')
    elif cmd=='stop': request('/stop',b'x')
    elif cmd=='status': request('/playback-info')
