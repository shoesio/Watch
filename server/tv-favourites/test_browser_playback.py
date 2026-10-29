"""Browser media capability checks and real codec-copy packaging."""
import asyncio
import io
import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock
from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer
from browser_playback import BrowserStream, browser_media


class BrowserMediaTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.directory = Path(self.temp.name)
        (self.directory/'index.m3u8').write_text('#EXTM3U\n#EXTINF:4,\nsegment000000.ts\n')
        (self.directory/'segment000000.ts').write_bytes(b'test segment')
        self.stream = SimpleNamespace(directory=self.directory, closed=False,
                                      last_access=0, close=AsyncMock())
        self.bridge = SimpleNamespace(tickets={'valid': {'expires':time.time()+60, 'browser':self.stream},
                                               'expired': {'expires':0, 'browser':self.stream}})
        app = web.Application()
        app.router.add_route('*', '/browser/{ticket}/{filename}', lambda r: browser_media(self.bridge, r))
        self.client = TestClient(TestServer(app))
        await self.client.start_server()

    async def asyncTearDown(self):
        await self.client.close()
        self.temp.cleanup()

    async def test_only_valid_unexpired_capability_can_read_media(self):
        for ticket in ('missing', 'expired'):
            r = await self.client.get('/browser/'+ticket+'/index.m3u8')
            self.assertEqual(r.status, 404)
        r = await self.client.get('/browser/valid/index.m3u8')
        self.assertEqual(r.status, 200)
        self.assertIn('#EXTM3U', await r.text())
        self.assertGreater(self.stream.last_access, 0)

    async def test_private_files_and_nonmedia_names_are_inaccessible(self):
        for name in ('packager.log','token','segment1.ts','index.m3u8.tmp'):
            r = await self.client.get('/browser/valid/'+name)
            self.assertEqual(r.status, 404)

    async def test_closing_player_revokes_stream(self):
        r = await self.client.delete('/browser/valid/index.m3u8')
        self.assertEqual(r.status, 204)
        self.stream.close.assert_awaited_once()
        r = await self.client.get('/browser/valid/index.m3u8')
        self.assertEqual(r.status, 404)

    async def test_invalid_input_fails_and_packager_is_removed(self):
        path = self.directory/'broken-stream'
        stream = BrowserStream(path, io.BytesIO(b'invalid video'))
        with self.assertRaises(ValueError):
            await stream.ready()
        await stream.close()
        self.assertIsNotNone(stream.process.poll())
        self.assertFalse(path.exists())


if __name__ == '__main__':
    unittest.main()
