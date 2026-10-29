"""Password-free Pi pairing, using the same provider flows as Watch for Apple TV.

Account credentials stay in owner-only files. No Apple TV Keychain extraction.
This module handles account sign-in only; playback capability is checked separately.
"""
import argparse
import base64
import datetime as dt
import json
import os
from pathlib import Path
import re
import tempfile
import time
import uuid

import requests

DEFAULT_ROOT = Path('/home/jhewes/tv-favourites-private')
HOSTS = {'auth.prd.user.itv.com', 'tvlogin.uktvapi.co.uk'}

class SignInError(ValueError):
    pass


def private_save(path, value):
    path = Path(path)
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix='.' + path.name + '-', dir=path.parent)
    try:
        with os.fdopen(fd, 'w') as output:
            json.dump(value, output)
        os.replace(name, path)
    finally:
        Path(name).unlink(missing_ok=True)


def token(value, minimum=1):
    if not isinstance(value, str) or not minimum <= len(value) <= 32768 or '\r' in value or '\n' in value:
        raise SignInError('The provider returned an incomplete account session. Please pair again.')
    return value


class DeviceSignIn:
    def __init__(self, root=DEFAULT_ROOT, session=None, clock=time.time):
        self.root = Path(root)
        self.http = session or requests.Session()
        self.clock = clock

    def path(self, provider, pending=False):
        if provider not in ('itv', 'u'):
            raise SignInError('Unsupported sign-in service.')
        return self.root / (provider + ('-pairing.json' if pending else '-device-session.json' if provider == 'u' else '-session.json'))

    def request(self, path, params=None):
        from urllib.parse import urlsplit
        url = urlsplit(path)
        if url.scheme != 'https' or url.hostname not in HOSTS or url.username or url.password or url.port:
            raise SignInError('Unexpected account destination.')
        headers = {'Accept': 'application/vnd.user.auth.v2+json', 'Referer': 'https://app.10ft.itv.com/'} if url.hostname == 'auth.prd.user.itv.com' else {'Accept': 'application/json'}
        try:
            response = self.http.get(path, params=params, headers=headers, timeout=(5, 18), allow_redirects=False, stream=True)
            with response:
                body = bytearray()
                for chunk in response.iter_content(16384):
                    body.extend(chunk)
                    if len(body) > 256000:
                        raise SignInError('The provider returned an oversized account response.')
                status = response.status_code
                try:
                    data = json.loads(body) if body else {}
                except (ValueError, UnicodeError):
                    raise SignInError('The provider returned an unreadable account response.') from None
                if not isinstance(data, dict):
                    raise SignInError('The provider returned an unexpected account response.')
                return status, data
        except requests.RequestException:
            # Requests exception text may contain refresh credentials in the URL.
            raise SignInError('Could not reach the provider. Please retry.') from None

    def start(self, provider):
        self.path(provider)
        if provider == 'itv':
            status, data = self.request('https://auth.prd.user.itv.com/generate/code')
            code = str(data.get('code', ''))
            if status != 200 or not re.fullmatch(r'[0-9]{6,10}', code):
                raise SignInError('ITV could not issue a sign-in code (HTTP %s).' % status)
            pending = {'code': code, 'expires_at': self.clock() + 600}
        else:
            status, data = self.request('https://tvlogin.uktvapi.co.uk/get_code')
            code = str(data.get('code', ''))
            try:
                match = str(uuid.UUID(data.get('match_code', '')))
            except (ValueError, TypeError, AttributeError):
                match = ''
            if status != 200 or not re.fullmatch(r'[A-Za-z0-9]{5}', code) or not match:
                raise SignInError('U could not issue a sign-in code (HTTP %s).' % status)
            pending = {'code': code.upper(), 'match_code': match, 'expires_at': self.clock() + 1800}
        private_save(self.path(provider, True), pending)
        return {'provider': provider, 'code': pending['code'], 'activation_url': 'https://www.itv.com/watch/pair' if provider == 'itv' else 'https://u.co.uk/activate?code=' + pending['code']}

    def exchange_itv(self, refresh):
        status, data = self.request('https://auth.prd.user.itv.com/token', {'refresh': token(refresh)})
        if status != 200:
            raise SignInError('ITV account renewal needs attention (HTTP %s). Please pair again.' % status)
        access = token(data.get('access_token'))
        expiry = self.clock() + 900
        try:
            payload = access.split('.')[1]
            claims = json.loads(base64.urlsafe_b64decode(payload + '=' * (-len(payload) % 4)))
            expiry = float(claims['exp'])
        except (ValueError, KeyError, IndexError, TypeError):
            try:
                expiry = self.clock() + float(data.get('expires_in', 900))
            except (ValueError, TypeError):
                pass
        if expiry <= self.clock():
            raise SignInError('ITV returned an expired session. Please pair again.')
        return {'access_token': access, 'refresh_token': token(data.get('refresh_token') or refresh), 'expires_at': expiry}

    def check(self, provider):
        path = self.path(provider, True)
        if not path.exists():
            raise SignInError('No pending code. Start sign-in first.')
        pending = json.loads(path.read_text())
        if pending.get('expires_at', 0) <= self.clock():
            path.unlink(missing_ok=True)
            raise SignInError('This code has expired. Get a new code.')
        code = pending['code']
        if provider == 'itv':
            if not re.fullmatch(r'[0-9]{6,10}', code):
                raise SignInError('Invalid pending ITV code.')
            status, data = self.request('https://auth.prd.user.itv.com/verify/' + code)
            if status in (204, 404):
                return False
            if status != 200:
                raise SignInError('ITV could not check the code (HTTP %s).' % status)
            credentials = self.exchange_itv(data.get('token'))
        else:
            status, data = self.request('https://tvlogin.uktvapi.co.uk/check_code', {'code': code, 'match_code': pending['match_code']})
            if status == 404 and data.get('error') == 'No user details found for code pair':
                return False
            if status != 200:
                raise SignInError('U could not check the code (HTTP %s).' % status)
            try:
                expiry = dt.datetime.fromisoformat(data['long_session_expiry'].replace('Z', '+00:00')).timestamp()
                account = str(data['int_mpp_id'])
                if not re.fullmatch(r'[0-9]{1,32}', account) or expiry <= self.clock():
                    raise ValueError()
            except (KeyError, TypeError, ValueError, AttributeError):
                raise SignInError('U returned an incomplete or expired session. Please pair again.') from None
            credentials = {'sessionToken': token(data.get('mpp_session_token'), 16), 'accountId': account, 'expires_at': expiry}
        private_save(self.path(provider), credentials)
        path.unlink(missing_ok=True)
        return True

    def itv_access_token(self):
        path = self.path('itv')
        if not path.exists():
            raise SignInError('Connect ITV on the Pi first.')
        data = json.loads(path.read_text())
        if float(data.get('expires_at', 0)) <= self.clock() + 90:
            data = self.exchange_itv(data.get('refresh_token'))
            private_save(path, data)
        return token(data.get('access_token'))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('provider', choices=['itv', 'u'])
    parser.add_argument('--root', type=Path, default=DEFAULT_ROOT)
    action = parser.add_mutually_exclusive_group()
    action.add_argument('--start', action='store_true')
    action.add_argument('--check', action='store_true')
    args = parser.parse_args()
    service = DeviceSignIn(args.root)
    try:
        if args.check:
            print('Connected.' if service.check(args.provider) else 'Waiting for activation.')
            return
        info = service.start(args.provider)
        print('Open ' + info['activation_url'])
        print('Enter code: ' + info['code'])
        print('This connects the Pi; playback support is checked separately.')
        if args.start:
            return
        deadline = time.monotonic() + 600
        while time.monotonic() < deadline:
            time.sleep(5)
            if service.check(args.provider):
                print('Connected. Account session saved privately on the Pi.')
                return
        print('Sign-in timed out. Run this connector again for a new code.')
    except (SignInError, OSError, ValueError) as error:
        print(str(error) if isinstance(error, SignInError) else 'Could not read or save the private sign-in session. Please retry.')
        raise SystemExit(1) from None
    except (KeyboardInterrupt, EOFError):
        print('\nCancelled. Existing connections were kept.')

if __name__ == '__main__':
    main()
