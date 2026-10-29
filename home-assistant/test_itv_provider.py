import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch
from itv_provider import source

class Response:
    status_code=200
    def json(self):return {'Playlist':{'Video':{'MediaFiles':[{'Href':'https://vod.content.itv.com/video.mpd','KeyServiceUrl':'https://itvpnp.live.ott.irdeto.com/license'}]}}}
class HTTP:
    def __init__(self):self.calls=[]
    def post(self,url,**kw):self.calls.append((url,kw));return Response()
class ITVTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.http=HTTP();self.ep={'playlist_url':'https://magni.itv.com/playlist/itvonline/ITV/1_2_3.1'}
    def test_free_vod_offers_pi_dash_and_checks_both_destinations(self):
        manifest,licence,headers=source(self.temp.name,self.http,self.ep)
        self.assertTrue(manifest.endswith('.mpd'));self.assertIn('irdeto.com',licence)
        self.assertIn('widevine',self.http.calls[0][1]['json']['variantAvailability']['featureset'])
        self.assertFalse(self.http.calls[0][1]['allow_redirects'])
    def test_paired_itv_uses_account_without_returning_token_to_client(self):
        (Path(self.temp.name)/'itv-session.json').write_text('{}')
        with patch('itv_provider.DeviceSignIn.itv_access_token',return_value='private-fixture'):
            result=source(self.temp.name,self.http,self.ep)
        self.assertEqual(self.http.calls[0][1]['json']['user'],{'token':'private-fixture'})
        self.assertNotIn('private-fixture',str(result))
    def test_arbitrary_playlist_and_premium_rejected_before_request(self):
        for url in ('http://magni.itv.com/playlist/itvonline/ITV/1','https://evil.test/playlist/itvonline/ITV/1','https://magni.itv.com/playlist/itvonline/ITV/1?secret=x'):
            with self.assertRaises(ValueError):source(self.temp.name,self.http,{'playlist_url':url})
        with self.assertRaises(ValueError):source(self.temp.name,self.http,dict(self.ep,premium=True))
        self.assertEqual(self.http.calls,[])
    def test_missing_signin_live_cannot_fall_back_to_anonymous(self):
        with self.assertRaises(ValueError):source(self.temp.name,self.http,dict(self.ep,live=True,playlist_url='https://simulcast.itv.com/playlist/itvonline/itv'))
        self.assertEqual(self.http.calls,[])

if __name__=='__main__':unittest.main()
