#!/usr/bin/env python3
"""Run interactively on the Pi. Credentials never appear in command arguments."""
import getpass
import json
import logging
import os
from pathlib import Path
import tempfile
import streamlink
from bbc_auth import adapt, BBCLoginError

ROOT = Path('/home/jhewes/tv-favourites-private')
SOURCE = 'https://www.bbc.co.uk/iplayer/live/bbcone'

def private_json(path, data):
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix='.bbc-')
    try:
        with os.fdopen(fd, 'w') as out:
            json.dump(data, out, indent=2)
        os.chmod(tmp, 0o600)
        os.replace(tmp, path)
    finally:
        Path(tmp).unlink(missing_ok=True)

def main():
    os.umask(0o077)
    ROOT.mkdir(mode=0o700, exist_ok=True)
    logging.disable(logging.CRITICAL)
    print('Connect BBC iPlayer to the TV dashboard.')
    print('Enter your existing BBC account details here; they will not be shown.')
    print('They are sent only to the BBC for login and saved privately on this Pi.')
    username = getpass.getpass('BBC email or username (hidden): ').strip()
    password = getpass.getpass('BBC password (hidden): ')
    if not username or not password:
        print('Nothing saved: both fields are required.')
        return 1
    session = streamlink.Streamlink()
    session.set_option('http-timeout', 20)
    session.set_option('stream-timeout', 20)
    name, cls, url = session.resolve_url(SOURCE)
    plugin = adapt(cls(session, url, options={'username':username,'password':password}))
    try:
        accepted = plugin.login(SOURCE)
    except BBCLoginError as exc:
        print(str(exc))
        private_json(ROOT/'bbc-connection-result.json', {'login':'not_accepted','reason':str(exc)})
        return 2
    except Exception as exc:
        print('BBC login request failed (' + type(exc).__name__ + '). Nothing saved.')
        private_json(ROOT/'bbc-connection-result.json', {'login':'request_failed','error_type':type(exc).__name__})
        return 2
    if not accepted:
        print('BBC did not accept this Streamlink login. Nothing saved.')
        print('This can mean incorrect details or a BBC login change; it does not prove the password is wrong.')
        private_json(ROOT/'bbc-connection-result.json', {'login':'not_accepted'})
        return 3
    path = ROOT/'streamlink-options.json'
    options = json.loads(path.read_text()) if path.exists() else {}
    options['bbciplayer'] = {'username':username,'password':password}
    private_json(path, options)
    print('BBC login accepted. Account details saved privately.')
    try:
        streams = plugin.streams()
        names = sorted(streams)
        result = {'login':'accepted','live_streams':names}
        print('BBC One stream qualities: ' + (', '.join(names) if names else 'none returned'))
    except Exception as exc:
        result = {'login':'accepted','stream_error_type':type(exc).__name__}
        print('Login worked, but stream discovery needs checking (' + type(exc).__name__ + ').')
    private_json(ROOT/'bbc-connection-result.json', result)
    print('Return to the chat and say "BBC login done" so the sources can be tested and enabled.')
    print('Current TV playback has been left alone.')
    return 0

if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (KeyboardInterrupt, EOFError):
        print('\nCancelled.'); raise SystemExit(1)
