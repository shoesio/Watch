import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock,patch
from five_provider import FiveAccount,FiveLoginError

class FiveTests(unittest.TestCase):
    def test_created_session_is_a_success_and_password_is_not_saved(self):
        with tempfile.TemporaryDirectory() as root:
            first=Mock(status_code=200);first.json.return_value={'AuthenticationResult':{'IdToken':'fixture-id','RefreshToken':'fixture-refresh','ExpiresIn':3600}}
            second=Mock(status_code=201);second.json.return_value={'sessionToken':'fixture-session'}
            with patch('five_provider.requests.post',side_effect=[first,second]):
                FiveAccount(root).login('fixture@example.invalid','fixture-password')
            path=Path(root)/'channel5-session.json'
            self.assertEqual(json.loads(path.read_text())['sessionToken'],'fixture-session')
            self.assertNotIn('fixture-password',path.read_text())
            self.assertEqual(path.stat().st_mode & 0o777,0o600)

    def test_safe_stage_error_never_returns_provider_message(self):
        response=Mock(status_code=400)
        response.json.return_value={'__type':'NotAuthorizedException','message':'sensitive fixture'}
        with patch('five_provider.requests.post',return_value=response):
            with self.assertRaisesRegex(FiveLoginError,'Channel 5 sign-in: NotAuthorizedException') as error:
                FiveAccount.authenticate('USER_PASSWORD_AUTH',{'PASSWORD':'private'})
        self.assertNotIn('sensitive',str(error.exception))

if __name__=='__main__':unittest.main()
