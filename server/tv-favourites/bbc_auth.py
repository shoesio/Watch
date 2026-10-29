"""Compatibility adapter for BBC's current username-first JSON sign-in flow.

Uses the same endpoints and fields as BBC's account JavaScript. Does not solve
browser challenges, change credentials, or fall back to a different provider.
"""
import json
import re
from types import MethodType
from urllib.parse import urlsplit, parse_qsl

class BBCLoginError(ValueError):
    pass


def _returned_to(response, destination):
    return any(x.url.rstrip('/') == destination.rstrip('/') for x in [*getattr(response, 'history', []), response])


def current_login(self, destination):
    http = self.session.http
    page = http.get('https://session.bbc.com/session', params={'ptrt': destination})
    if _returned_to(page, destination):
        return True
    if urlsplit(page.url).hostname != 'account.bbc.com':
        raise BBCLoginError('BBC sign-in returned an unexpected destination.')
    match = re.search(r'window\.bbcAccount\.locals\s*=\s*({.*?});', page.text, re.S)
    if not match:
        raise BBCLoginError('BBC requires browser sign-in or its account page has changed.')
    locals_ = json.loads(match[1])
    current_url = locals_.get('currentUrl', page.url)
    if urlsplit(current_url).hostname != 'account.bbc.com':
        raise BBCLoginError('Unexpected BBC account URL.')
    params = dict(parse_qsl(urlsplit(current_url).query))
    headers = {'Origin':'https://account.bbc.com', 'Referer':page.url, 'Accept':'application/json'}

    def post(path, data):
        response = http.post('https://account.bbc.com' + path, params=params, json=data,
                             headers=headers, allow_redirects=False, raise_for_status=False)
        try:
            result = response.json()
        except Exception:
            raise BBCLoginError('BBC needs a normal browser sign-in; the automated login was not accepted.') from None
        if response.status_code in [202, 403, 429]:
            raise BBCLoginError('BBC is requesting a browser/security check. No automatic retries were made.')
        return result

    identifier = post('/auth/identifier/check', {'userIdentifier':self.get_option('username')})
    if identifier.get('message') in ['accountLocked', 'accountLockedPassword']:
        raise BBCLoginError('BBC reports that the account is locked. Use the BBC website to resolve it.')
    result = post('/auth/v2/signin', {'userIdentifier':self.get_option('username'), 'password':self.get_option('password')})
    callback = result.get('sessionUrl')
    if not callback:
        reason = result.get('message')
        if reason == 'accountLocked':
            raise BBCLoginError('BBC reports that the account is locked. Use the BBC website to resolve it.')
        if reason and ('password' in reason.lower() or 'credential' in reason.lower()):
            raise BBCLoginError('BBC did not accept the account details. Nothing was saved.')
        raise BBCLoginError('BBC did not complete sign-in. A browser check or email confirmation may be required.')
    parts = urlsplit(callback)
    if parts.scheme != 'https' or parts.hostname not in ['session.bbc.com','account.bbc.com','www.bbc.co.uk']:
        raise BBCLoginError('BBC supplied an unexpected sign-in callback; it was not opened.')
    complete = http.get(callback)
    return _returned_to(complete, destination)


def adapt(plugin):
    plugin.login = MethodType(current_login, plugin)
    return plugin
