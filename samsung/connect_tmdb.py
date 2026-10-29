#!/usr/bin/env python3
"""Run through an interactive SSH terminal; never pass a credential as an argument."""
import getpass
import json
from pathlib import Path
from tmdb_logos import TMDB, atomic, sync

private = Path('/home/jhewes/tv-favourites-private')
print('Connect TMDB to Watch\nFind your API Read Access Token under TMDB > Settings > API.\nPaste it below: input is hidden and stays on the Pi.\n')
try:
    token = getpass.getpass('TMDB read access token (or v3 API key): ').strip()
    if not token:
        raise RuntimeError('No credential entered; nothing changed.')
    TMDB(token).get('configuration')
    atomic(private / 'tmdb-token', token.encode())
    catalogue = json.loads(Path('/home/jhewes/tv-favourites/catalogue.json').read_text())
    result = sync(private, catalogue['programmes'])
    print('Connected. Downloaded %d clear logos; %d shows need a closer match.' % (result['downloaded'], result['review']))
    print('Refresh Watch to see the logos. New shows will be checked automatically.')
except KeyboardInterrupt:
    print('\nCancelled.')
except Exception:
    print('Connection or import could not finish. Check the credential and network, then try again.\nExisting logos and playback are unchanged.')
