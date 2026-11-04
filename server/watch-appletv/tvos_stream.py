"""Codec-copy HLS buffering for already playable input streams.

Keep timestamp relationships intact. The upstream controls delivery speed; a second
real-time throttle here prevents the player from building a useful safety buffer.
"""
import asyncio,contextlib,subprocess,time
from pathlib import Path
from browser_playback import BrowserStream

class TVStream(BrowserStream):
    def __init__(self,directory,source,allow_short=True,live=True):
        self.directory=Path(directory);self.directory.mkdir(mode=0o700,parents=True)
        self.allow_short=allow_short;self.live=live
        self.source=source;self.last_access=time.time();self.closed=False;self.failure=None
        self.log=(self.directory/'packager.log').open('wb')
        # EVENT keeps the absolute episode timeline from sliding past a paused
        # viewer. Live channels keep a bounded DVR window; all files are removed
        # when this device releases the session.
        playlist_options=(['-hls_list_size','450','-hls_delete_threshold','15',
                           '-hls_flags','delete_segments+temp_file'] if live else
                          ['-hls_list_size','0','-hls_playlist_type','event','-hls_flags','temp_file'])
        self.process=subprocess.Popen([
            'ffmpeg','-nostdin','-v','error','-copyts','-start_at_zero',
            '-i','pipe:0','-map','0:v:0','-map','0:a:0?','-c','copy',
            '-f','hls','-hls_time','4',*playlist_options,
            '-hls_segment_filename',str(self.directory/'segment%06d.ts'),
            str(self.directory/'index.m3u8')],stdin=subprocess.PIPE,stdout=subprocess.DEVNULL,stderr=self.log)
        self.task=asyncio.create_task(self.feed())

    def playlist(self):
        text=(self.directory/'index.m3u8').read_text()
        if not self.live:
            # EVENT alone still defaults AVPlayer to the growing live edge.
            # This is the beginning of the requested episode/source offset.
            text=text.replace('#EXTM3U\n','#EXTM3U\n#EXT-X-START:TIME-OFFSET=0,PRECISE=YES\n',1)
        return text

    def snapshot(self):
        path=self.directory/'index.m3u8'
        if not path.exists():return {'segments':0,'buffer_seconds':0,'ended':False}
        text=path.read_text()
        durations=[float(line.split(':',1)[1].rstrip(',')) for line in text.splitlines() if line.startswith('#EXTINF:')]
        return {'segments':len(durations),'buffer_seconds':round(sum(durations),2),'ended':'#EXT-X-ENDLIST' in text,
                'playlist_age_seconds':round(time.time()-path.stat().st_mtime,1),'packager_running':self.process.poll() is None}

    async def feed(self):
        try:
            while not self.closed:
                chunk=await asyncio.to_thread(self.source.read,64*1024)
                if not chunk:break
                await asyncio.to_thread(self.process.stdin.write,chunk)
        except (OSError,ValueError):self.failure='upstream-interrupted'
        finally:
            with contextlib.suppress(OSError,ValueError):self.process.stdin.close()
            await asyncio.to_thread(self.source.close)

    async def ready(self):
        for _ in range(360):
            state=self.snapshot()
            # Three complete segments give AVPlayer a real startup buffer. Short
            # completed clips may legitimately contain fewer segments.
            if state['buffer_seconds']>=12 or (self.allow_short and state['ended'] and state['segments']):return
            if self.process.poll() is not None:raise ValueError('The video stream ended before its startup buffer was ready.')
            await asyncio.sleep(0.25)
        raise ValueError('The stream took too long to fill its startup buffer.')
