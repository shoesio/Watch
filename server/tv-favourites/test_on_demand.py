import base64
import json
import unittest
from unittest.mock import Mock
import requests
from connect_on_demand import manifest_summary, login_u, login_c4, c4_probe

class Checks(unittest.TestCase):
    def test_fairplay(self):
        result = manifest_summary('#EXTM3U\n#EXT-X-KEY:METHOD=SAMPLE-AES,URI="skd://private",KEYFORMAT="com.apple.streamingkeydelivery"\n')
        self.assertTrue(result['encrypted'])
        self.assertNotIn('private', json.dumps(result))

    def test_dash(self):
        result = manifest_summary('<MPD xmlns="urn:mpeg:dash:schema:mpd:2011"><Period><AdaptationSet><ContentProtection schemeIdUri="urn:uuid:edef8ba9-79d6-4ace-a3c8-27dcd51d21ed"/></AdaptationSet></Period></MPD>')
        self.assertTrue(result['encrypted'])

    def test_unknown_not_clear(self):
        self.assertIsNone(manifest_summary('<html>Denied</html>')['encrypted'])
        self.assertFalse(manifest_summary('#EXTM3U\n#EXT-X-KEY:METHOD=NONE\n')['encrypted'])

    def test_u_auth_payload_and_minimal_saved_session(self):
        session = Mock(cookies=requests.cookies.RequestsCookieJar())
        session.post.return_value = Mock(status_code=200, json=lambda: {'accountId': 123, 'sessionToken': 'session', 'email': 'private'})
        auth, status = login_u(session, 'someone', 'password')
        payload = session.post.call_args.kwargs['json']
        self.assertEqual(json.loads(base64.b64decode(payload)), {'email':'someone', 'password':'password', 'code':''})
        self.assertEqual(auth, {'sessionToken':'session', 'accountId':123, 'cookies':{}})

    def test_rejected_auth_not_saved(self):
        session = Mock()
        session.post.return_value = Mock(status_code=401, json=lambda: {'error':'private response'})
        self.assertIsNone(login_c4(session, 'someone', 'password')[0])
        self.assertIsNone(login_u(session, 'someone', 'password')[0])

    def test_authenticated_endpoint_and_redaction(self):
        session = Mock()
        session.get.return_value = Mock(status_code=200, json=lambda: {'videoProfiles':[], 'sensitive':'private'})
        result = c4_probe(session, {'accessToken':'token'})
        self.assertTrue(result['authenticated'])
        self.assertIn('amazonfire-dash',session.get.call_args.args[0])
        self.assertNotIn('token',json.dumps(result))
        self.assertNotIn('private',json.dumps(result))

if __name__ == '__main__':
    unittest.main()
