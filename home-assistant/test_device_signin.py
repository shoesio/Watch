import json
from pathlib import Path
import tempfile
import unittest
from device_signin import DeviceSignIn, SignInError

class PairingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.service = DeviceSignIn(self.root, clock=lambda: 1000)
        self.responses = []
        self.calls = []
        def request(url, params=None):
            self.calls.append((url, params))
            return self.responses.pop(0)
        self.service.request = request

    def test_itv_wait_then_pair_refresh_and_private_storage(self):
        self.responses = [(200, {'code':'123456'}), (404, {}), (200, {'token':'refresh'}),
                          (200, {'access_token':'access', 'refresh_token':'new', 'expires_in':60}),
                          (200, {'access_token':'renewed', 'expires_in':3600})]
        self.assertEqual(self.service.start('itv')['code'], '123456')
        self.assertFalse(self.service.check('itv'))
        self.assertTrue(self.service.check('itv'))
        self.assertFalse(self.service.path('itv', True).exists())
        self.assertEqual(self.service.path('itv').stat().st_mode & 0o777, 0o600)
        self.assertEqual(self.service.itv_access_token(), 'renewed')
        self.assertEqual(json.loads(self.service.path('itv').read_text())['refresh_token'], 'new')

    def test_u_pair_preserves_existing_website_session(self):
        old = self.root/'u-session.json'
        old.write_text('{"cookies":{"saved":"untouched"}}')
        self.responses = [(200, {'code':'ab123','match_code':'12345678-1234-1234-1234-123456789012'}),
                          (404, {'error':'No user details found for code pair'}),
                          (200, {'int_mpp_id':123, 'mpp_session_token':'s'*32,
                                 'long_session_expiry':'2030-01-01T00:00:00Z', 'name':'discard this'})]
        self.assertEqual(self.service.start('u')['code'], 'AB123')
        self.assertFalse(self.service.check('u'))
        self.assertTrue(self.service.check('u'))
        stored = json.loads(self.service.path('u').read_text())
        self.assertNotIn('name', stored)
        self.assertEqual(stored['accountId'], '123')
        self.assertEqual(json.loads(old.read_text())['cookies'], {'saved':'untouched'})

    def test_failed_exchange_keeps_existing_session_and_pending(self):
        self.service.path('itv').write_text('{"existing":true}')
        self.responses = [(200, {'code':'123456'}), (200, {'token':'refresh'}), (401, {})]
        self.service.start('itv')
        with self.assertRaises(SignInError): self.service.check('itv')
        self.assertTrue(json.loads(self.service.path('itv').read_text())['existing'])
        self.assertTrue(self.service.path('itv', True).exists())

    def test_expired_pairing_is_not_checked(self):
        self.responses = [(200, {'code':'123456'})]
        self.service.start('itv')
        self.service.clock = lambda:2000
        with self.assertRaises(SignInError): self.service.check('itv')
        self.assertEqual(len(self.calls), 1)

    def test_invalid_account_responses_never_save(self):
        self.responses = [(200, {'code':'123456'}), (200, {'token':'bad\ncredential'})]
        self.service.start('itv')
        with self.assertRaises(SignInError): self.service.check('itv')
        self.assertFalse(self.service.path('itv').exists())

    def test_redirect_rejected_without_following_or_exposing_url(self):
        class Response:
            status_code = 302
            def __enter__(self):return self
            def __exit__(self,*args):pass
            def iter_content(self,n):return iter([b'{}'])
        class HTTP:
            def get(self,url,**kwargs):
                if kwargs['allow_redirects'] is not False:raise AssertionError()
                return Response()
        service = DeviceSignIn(self.root,session=HTTP())
        with self.assertRaises(SignInError):service.start('itv')

if __name__ == '__main__':unittest.main()
