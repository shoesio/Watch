#!/usr/bin/env python3
"""Private account and manifest diagnostics. Does not change HA or TV playback.

U login follows the current u.co.uk web client. Channel 4's OAuth endpoint
and public client identifier are documented by Catch-up TV & More's adapter.
No DRM keys, licence requests, or media decryption are implemented here.
"""
import argparse
import base64
import getpass
import json
import os
from pathlib import Path
import re
import tempfile
from urllib.parse import urljoin, urlparse
import xml.etree.ElementTree as ET
import requests

ROOT = Path('/home/jhewes/tv-favourites-private')
C4_AUTH = 'https://api.channel4.com/online/v2/auth/token'
C4_CLIENT = 'Basic eUExTHB6dGtHZUhaRDZuU2E3QzFBQUY2dkhwelZOblU6UXFFbUVnVVVVT1hUa3piNg=='
U_PLAYER = 'https://players.brightcove.net/1242911124001/0RyQs9qPh_default/index.html?videoId=6363937269112'
UA = 'Mozilla/5.0 (X11; Linux aarch64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36'


def save_private(path, data):
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix='.ondemand-')
    try:
        with os.fdopen(fd, 'w') as out:
            json.dump(data, out, indent=2)
        os.chmod(tmp, 0o600)
        os.replace(tmp, path)
    finally:
        Path(tmp).unlink(missing_ok=True)


def manifest_summary(text):
    """Return only protection identifiers, never signed URIs or licence data."""
    if text.lstrip().startswith('#EXTM3U'):
        keys = re.findall(r'^#EXT-X-(?:SESSION-)?KEY:(.*)$', text, re.M)
        methods = sorted(set(re.findall(r'METHOD=([^,\r\n]+)', '\n'.join(keys))) - {'NONE'})
        formats = sorted(set(re.findall(r'KEYFORMAT="([^"]+)"', '\n'.join(keys))))
        return {'format': 'hls', 'protection_methods': methods, 'key_formats': formats,
                'encrypted': bool(methods), 'is_master': '#EXT-X-STREAM-INF:' in text}
    try:
        root = ET.fromstring(text)
    except ET.ParseError:
        return {'format': 'unknown', 'encrypted': None}
    if root.tag.rsplit('}', 1)[-1] != 'MPD':
        return {'format': 'unknown', 'encrypted': None}
    schemes = sorted({e.attrib.get('schemeIdUri', '') for e in root.iter()
                      if e.tag.rsplit('}', 1)[-1] == 'ContentProtection'})
    return {'format': 'dash', 'protection_schemes': schemes, 'encrypted': bool(schemes)}


def inspect_manifest(session, url, headers=None, depth=0):
    if urlparse(url).scheme != 'https':
        return {'status': 'unsupported_url_scheme'}
    # Supply bearer tokens only to the account API, never to CDN requests.
    with session.get(url, headers=headers or {}, timeout=25, stream=True) as response:
        if response.status_code != 200:
            return {'http_status': response.status_code}
        data = bytearray()
        for chunk in response.iter_content(16384):
            data.extend(chunk)
            if len(data) > 1024 * 1024:
                return {'status': 'manifest_size_limit'}
        text = data.decode('utf-8', errors='replace')
    result = {'http_status': 200, **manifest_summary(text)}
    if result.get('is_master') and depth < 1:
        variants = re.findall(r'^#EXT-X-STREAM-INF:[^\n]*\n([^#\s][^\r\n]*)', text, re.M)
        result['sample_variant'] = inspect_manifest(session, urljoin(url, variants[-1]), headers, depth + 1) if variants else {}
        if result['sample_variant'].get('encrypted'):
            result['encrypted'] = True
    return result


def c4_probe(session, auth=None):
    headers = {'Authorization': 'Bearer ' + auth['accessToken']} if auth else {}
    url = ('https://api.channel4.com/online/v1/vod/stream/80485-001?client=amazonfire-dash'
           if auth else 'https://www.channel4.com/vod/stream/80485-001')
    response = session.get(url, headers=headers, timeout=25)
    result = {'episode': '80485-001', 'playback_http_status': response.status_code,
              'authenticated': bool(auth), 'profiles': []}
    if response.status_code != 200:
        return result
    for profile in response.json().get('videoProfiles', []):
        item = {'name': profile.get('name'), 'manifests': []}
        for stream in profile.get('streams', [])[:1]:
            uri = stream.get('uri')
            if uri:
                item['manifests'].append(inspect_manifest(session, uri, {'Origin': 'https://www.channel4.com', 'Referer': 'https://www.channel4.com/'}))
        result['profiles'].append(item)
    return result


def u_probe(session):
    page = session.get(U_PLAYER, timeout=25)
    page.raise_for_status()
    match = re.search(r'''policyKey\s*:\s*['"]([\w-]+)''', page.text)
    if not match:
        return {'status': 'player_policy_not_found'}
    response = session.get('https://edge.api.brightcove.com/playback/v1/accounts/1242911124001/videos/6363937269112',
                           headers={'Accept': 'application/json;pk=' + match[1], 'Referer': U_PLAYER}, timeout=25)
    result = {'episode': 'Would I Lie to You? S16E1', 'playback_http_status': response.status_code, 'sources': []}
    if response.status_code != 200:
        return result
    for source in response.json().get('sources', []):
        item = {'type': source.get('type'), 'key_systems': sorted(source.get('key_systems', {}))}
        if source.get('src') and source.get('type') in ('application/x-mpegURL', 'application/dash+xml'):
            item['manifest'] = inspect_manifest(session, source['src'], {'Referer': 'https://u.co.uk/'})
        result['sources'].append(item)
    return result


def login_u(session, email, password):
    session.get('https://u.co.uk/account/login', timeout=25).raise_for_status()
    payload = base64.b64encode(json.dumps({'email': email, 'password': password, 'code': ''}).encode()).decode()
    response = session.post('https://u.co.uk/api/account/authenticate-user', json=payload,
                            headers={'Origin': 'https://u.co.uk', 'Referer': 'https://u.co.uk/account/login'}, timeout=25)
    data = response.json() if response.status_code == 200 else {}
    if not isinstance(data, dict) or not data.get('sessionToken') or not data.get('accountId'):
        return None, response.status_code
    return {'sessionToken': data['sessionToken'], 'accountId': data['accountId'],
            'cookies': requests.utils.dict_from_cookiejar(session.cookies)}, response.status_code


def login_c4(session, email, password):
    response = session.post(C4_AUTH, data={'grant_type': 'password', 'username': email, 'password': password},
                            headers={'Authorization': C4_CLIENT}, timeout=25)
    data = response.json() if response.status_code == 200 else {}
    if not data.get('accessToken'):
        return None, response.status_code
    return {key: data[key] for key in ('accessToken', 'refreshToken', 'issuedAt', 'expiresIn') if key in data}, response.status_code


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--public-only', action='store_true')
    parser.add_argument('--service', choices=['u', 'channel4', 'both'], default='both')
    args = parser.parse_args()
    os.umask(0o077)
    print('Channel 4 and U: account and on-demand stream check. TV playback is left alone.')
    print('Details go only to the selected service over HTTPS. Only accepted session tokens are saved privately on the Pi.')
    results = {}
    for name in (['channel4', 'u'] if args.service == 'both' else [args.service]):
        session = requests.Session()
        session.headers.update({'User-Agent': UA})
        result = {'login': 'not_attempted'}
        try:
            auth = None
            if not args.public_only:
                print('\n' + ('Channel 4' if name == 'channel4' else 'U') + ' account (leave email blank to skip).')
                email = getpass.getpass('Email (hidden): ').strip()
                if not email:
                    result['login'] = 'skipped'
                    results[name] = result
                    continue
                password = getpass.getpass('Password (hidden): ')
                auth, status = (login_c4 if name == 'channel4' else login_u)(session, email, password)
                del email, password
                result.update(login='accepted' if auth else 'not_accepted', login_http_status=status)
                if not auth:
                    print('Login was not accepted. No details saved; this may also mean a changed login flow.')
                    results[name] = result
                    continue
                save_private(ROOT / (name + '-session.json'), auth)
                print('Login accepted; checking the episode manifest.')
            result['stream_check'] = c4_probe(session, auth) if name == 'channel4' else u_probe(session)
            if name == 'u':
                result['stream_check']['website_login_accepted'] = bool(auth)
                result['stream_check']['authentication_scope'] = 'U website session; standard public Brightcove player metadata path'
            print(json.dumps(result['stream_check'], indent=2))
        except Exception as exc:
            result['error_type'] = type(exc).__name__
            print('Check needs attention (' + type(exc).__name__ + '). No private response text is printed.')
        finally:
            session.close()
            results[name] = result
            save_private(ROOT / 'on-demand-connection-result.json', results)
    print('\nReturn to the chat and say "on-demand login done". This check does not enable unverified sources.')


if __name__ == '__main__':
    try:
        main()
    except (KeyboardInterrupt, EOFError):
        print('\nCancelled.')
