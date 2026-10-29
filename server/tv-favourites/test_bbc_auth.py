import json
import unittest
from types import SimpleNamespace
from unittest.mock import Mock
from bbc_auth import adapt, BBCLoginError

URL='https://www.bbc.co.uk/iplayer/live/bbcone'
def response(url, data=None, status=200, text=''):
    r=SimpleNamespace(url=url,history=[],text=text,status_code=status)
    r.json=Mock(return_value=data)
    return r

class LoginTests(unittest.TestCase):
    def plugin(self):
        h=Mock()
        p=SimpleNamespace(session=SimpleNamespace(http=h),get_option=lambda key: {'username':'test-user','password':'test-password'}[key])
        return adapt(p),h

    def initial(self):
        return response('https://account.bbc.com/auth/identifier/signin?nonce=test',text='window.bbcAccount.locals = '+json.dumps({'currentUrl':'https://account.bbc.com/auth/identifier/signin?nonce=test'})+';')

    def test_existing_session_skips_password(self):
        p,h=self.plugin();h.get.return_value=response(URL)
        self.assertTrue(p.login(URL));h.post.assert_not_called()

    def test_current_two_step_flow(self):
        p,h=self.plugin();h.get.side_effect=[self.initial(),response(URL)]
        h.post.side_effect=[response('',{'hasPassword':True}),response('',{'sessionUrl':'https://session.bbc.com/session/callback?test=1'})]
        self.assertTrue(p.login(URL));calls=h.post.call_args_list
        self.assertEqual(calls[0].args[0],'https://account.bbc.com/auth/identifier/check')
        self.assertEqual(calls[1].kwargs['json'],{'userIdentifier':'test-user','password':'test-password'})
        self.assertFalse(calls[1].kwargs['allow_redirects'])

    def test_browser_check_stops_before_password(self):
        p,h=self.plugin();h.get.return_value=self.initial();h.post.return_value=response('',{},403)
        with self.assertRaises(BBCLoginError):p.login(URL)
        self.assertEqual(h.post.call_count,1)

    def test_untrusted_callback_is_not_opened(self):
        p,h=self.plugin();h.get.return_value=self.initial()
        h.post.side_effect=[response('',{}),response('',{'sessionUrl':'https://example.org/callback'})]
        with self.assertRaises(BBCLoginError):p.login(URL)
        self.assertEqual(h.get.call_count,1)

if __name__=='__main__':unittest.main()
