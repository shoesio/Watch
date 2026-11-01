"""Offline regression checks for real YouTube/iPlayer codec-order differences."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import bridge


class PlaylistSelectionTests(unittest.TestCase):
    def select(self, codecs):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source = root / 'master.m3u8'
            source.write_text('''#EXTM3U
#EXT-X-MEDIA:TYPE=AUDIO,GROUP-ID="chosen",NAME="English",URI="audio.m3u8"
#EXT-X-MEDIA:TYPE=AUDIO,GROUP-ID="other",NAME="Other",URI="other.m3u8"
#EXT-X-STREAM-INF:BANDWIDTH=8000000,CODECS="av01.0.08M.08,mp4a.40.2",RESOLUTION=1280x720,FRAME-RATE=50,AUDIO="other"
av1.m3u8
#EXT-X-STREAM-INF:BANDWIDTH=6000000,CODECS="%s",RESOLUTION=1920x1080,FRAME-RATE=50,AUDIO="chosen"
1080.m3u8
#EXT-X-STREAM-INF:BANDWIDTH=5000000,CODECS="%s",RESOLUTION=1280x720,FRAME-RATE=50,AUDIO="chosen"
720.m3u8
''' % (codecs, codecs))
            with patch.object(bridge, 'ROOT', root), patch.object(bridge, 'MAX_HEIGHT', 720), patch.object(bridge, 'MAX_FPS', 50):
                selected = Path(bridge.select_hls(source.as_uri())).read_text()
            self.assertIn('RESOLUTION=1280x720', selected)
            self.assertIn((root / 'audio.m3u8').as_uri(), selected)
            self.assertIn((root / '720.m3u8').as_uri(), selected)
            self.assertNotIn('1920x1080', selected)
            self.assertNotIn('other.m3u8', selected)
            self.assertNotIn('av1.m3u8', selected)
            return selected

    def test_youtube_video_codec_first(self):
        self.select('avc1.640020,mp4a.40.2')

    def test_iplayer_audio_codec_first(self):
        self.select('mp4a.40.5,avc1.640020')


if __name__ == '__main__':
    unittest.main()
