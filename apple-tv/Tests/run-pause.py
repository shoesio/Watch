#!/usr/bin/env python3
"""macOS AVPlayer integration: growing EVENT playlist, pause hold and exact resume.
Uses synthetic unencrypted media, loopback HTTP, no provider accounts or TV.
Requires ffmpeg and Xcode command-line tools. Takes about twenty seconds.
"""
import functools,http.server,subprocess,tempfile,threading
from pathlib import Path

class QuietHTTP(http.server.SimpleHTTPRequestHandler):
    def log_message(self,*args):pass

root=Path(__file__).resolve().parent
with tempfile.TemporaryDirectory(prefix='watch-pause-') as folder:
    folder=Path(folder)
    subprocess.run(['ffmpeg','-nostdin','-v','error','-f','lavfi','-i','testsrc2=size=160x90:rate=25','-f','lavfi','-i','sine=frequency=440:sample_rate=48000','-t','260','-c:v','libx264','-preset','ultrafast','-g','100','-c:a','aac','-f','hls','-hls_time','4','-hls_playlist_type','event','-hls_list_size','0',str(folder/'index.m3u8')],check=True)
    playlist=folder/'index.m3u8'
    playlist.write_text(playlist.read_text().replace('#EXT-X-ENDLIST\n','').replace('#EXTM3U\n','#EXTM3U\n#EXT-X-START:TIME-OFFSET=0,PRECISE=YES\n',1))
    subprocess.run(['xcrun','swiftc','-parse-as-library',str(root/'PlaybackPause/Main.swift'),'-o',str(folder/'test')],check=True)
    server=http.server.ThreadingHTTPServer(('127.0.0.1',0),functools.partial(QuietHTTP,directory=str(folder)))
    threading.Thread(target=server.serve_forever,daemon=True).start()
    try:subprocess.run([str(folder/'test'),f'http://127.0.0.1:{server.server_port}/index.m3u8'],check=True,timeout=65)
    finally:server.shutdown();server.server_close()
