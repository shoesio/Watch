"""Bounded HLS packaging for browsers; copies codecs and retains relative A/V timing."""
import asyncio
import contextlib
import re
import shutil
import subprocess
import time
from pathlib import Path
from aiohttp import web


class BrowserStream:
    def __init__(self, directory, source, allow_short=True):
        self.directory = Path(directory)
        self.directory.mkdir(mode=0o700, parents=True)
        self.allow_short = allow_short
        self.source = source
        self.last_access = time.time()
        self.closed = False
        self.log = (self.directory / 'packager.log').open('wb')
        self.process = subprocess.Popen([
            'ffmpeg', '-nostdin', '-v', 'error', '-copyts', '-start_at_zero',
            '-readrate', '1', '-readrate_initial_burst', '12', '-i', 'pipe:0', '-map', '0:v:0', '-map', '0:a:0?', '-c', 'copy',
            '-f', 'hls', '-hls_time', '4', '-hls_list_size', '45',
            '-hls_delete_threshold', '3', '-hls_flags', 'delete_segments+temp_file',
            '-hls_segment_filename', str(self.directory / 'segment%06d.ts'),
            str(self.directory / 'index.m3u8')], stdin=subprocess.PIPE,
            stdout=subprocess.DEVNULL, stderr=self.log)
        self.task = asyncio.create_task(self.feed())

    async def feed(self):
        try:
            while not self.closed:
                chunk = await asyncio.to_thread(self.source.read, 64 * 1024)
                if not chunk:
                    break
                await asyncio.to_thread(self.process.stdin.write, chunk)
        except (OSError, ValueError):
            pass
        finally:
            with contextlib.suppress(OSError, ValueError):
                self.process.stdin.close()
            await asyncio.to_thread(self.source.close)

    async def ready(self):
        for _ in range(240):
            path = self.directory / 'index.m3u8'
            if path.exists():
                playlist=path.read_text()
                buffered=sum(float(v) for v in re.findall(r'#EXTINF:([0-9.]+)',playlist))
                if buffered>=12 or (self.allow_short and '#EXT-X-ENDLIST' in playlist and buffered>0):return
            if self.process.poll() is not None:
                raise ValueError('This programme could not be prepared for browser playback.')
            await asyncio.sleep(0.25)
        raise ValueError('The browser stream took too long to start. Please try again.')

    async def close(self):
        if self.closed:
            return
        self.closed = True
        if self.process.poll() is None:
            self.process.terminate()
        await asyncio.to_thread(self.source.close)
        with contextlib.suppress(subprocess.TimeoutExpired):
            await asyncio.to_thread(self.process.wait, 5)
        if self.process.poll() is None:
            self.process.kill()
            await asyncio.to_thread(self.process.wait)
        self.task.cancel()
        await asyncio.gather(self.task, return_exceptions=True)
        self.log.close()
        shutil.rmtree(self.directory, ignore_errors=True)


async def browser_media(bridge, request):
    ticket = bridge.tickets.get(request.match_info['ticket'])
    if not ticket or not ticket.get('browser') or ticket['expires'] < time.time():
        raise web.HTTPNotFound()
    stream = ticket['browser']
    if request.method == 'POST' and request.match_info['filename']=='progress':
        try:
            data=await request.json();position=float(data.get('position',0))
            import math
            if not math.isfinite(position) or not 0<=position<=86400:raise ValueError()
            if ticket.get('_watch_id') and not ticket.get('_watch_meta',{}).get('live'):
                bridge.watch.progress.save(ticket['_watch_id'],position,ticket['_watch_meta'].get('duration_seconds',0),data.get('completed') is True)
                ticket['_watch_position']=position
            stream.last_access=time.time()
            return web.json_response({'ok':True})
        except (ValueError,TypeError):raise web.HTTPBadRequest()
    if request.method == 'DELETE':
        await stream.close()
        bridge.tickets.pop(request.match_info['ticket'], None)
        return web.Response(status=204)
    name = request.match_info['filename']
    if not re.fullmatch(r'index\.m3u8|segment\d{6}\.ts', name) or stream.closed:
        raise web.HTTPNotFound()
    stream.last_access = time.time()
    path = stream.directory / name
    if not path.is_file():
        raise web.HTTPNotFound()
    return web.FileResponse(path, headers={
        'Content-Type': 'application/vnd.apple.mpegurl' if name.endswith('.m3u8') else 'video/mp2t',
        'Cache-Control': 'no-store'})
