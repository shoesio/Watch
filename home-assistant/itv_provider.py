"""ITVX Pi source requests. Sign-in shares Watch for Apple TV's device-code flow.

Free content only. Provider authorization is required; unavailable licences fail closed.
"""
from urllib.parse import urlsplit
from device_signin import DeviceSignIn


def trusted(url, hosts=(), suffix=None):
    p = urlsplit(str(url))
    return (p.scheme == 'https' and not p.username and not p.password and p.port in (None,443)
            and (p.hostname in hosts or bool(suffix and p.hostname and p.hostname.endswith(suffix))))


def source(private, session, episode):
    if episode.get('premium'):
        raise ValueError('ITVX Premium playback has not been verified on this TV.')
    live = bool(episode.get('live'))
    endpoint = episode.get('playlist_url', '')
    hosts = ('simulcast.itv.com','stream-starter.fastly.ottstream.itv.com') if live else ('magni.itv.com',)
    if not trusted(endpoint, hosts) or not urlsplit(endpoint).path.startswith('/playlist/itvonline/') or urlsplit(endpoint).query or urlsplit(endpoint).fragment:
        raise ValueError('Invalid ITV playlist address.')
    body = {'client':{'id':'lg'}, 'device':{'deviceGroup':'ctv'},
            'variantAvailability':{'player':'dash', 'featureset':['mpeg-dash','widevine','outband-webvtt','hd','single-track'],
                                   'platformTag':'ctv', 'drm':{'system':'widevine','maxSupported':'L3'}}}
    account = DeviceSignIn(private)
    if live or account.path('itv').exists():
        body['user'] = {'token':account.itv_access_token()}
    headers = {'Accept':'application/vnd.itv.online.playlist.sim.v3+json' if live else 'application/vnd.itv.vod.playlist.v4+json',
               'Content-Type':'application/json', 'User-Agent':'okhttp/4.9.3'}
    try:
        response = session.post(endpoint, headers=headers, json=body, timeout=(5,20), allow_redirects=False)
        if response.status_code != 200:
            raise ValueError('ITV did not offer playback (HTTP %s).' % response.status_code)
        video = response.json().get('Playlist',{}).get('Video',{})
        choices = video.get('VideoLocations' if live else 'MediaFiles', [])
        for choice in choices:
            if choice.get('IsDar'):
                continue
            manifest = choice.get('Href') or choice.get('Url')
            licence = choice.get('KeyServiceUrl')
            if trusted(manifest, suffix='.content.itv.com') and '.mpd' in urlsplit(manifest).path.lower() and trusted(licence,('itvpnp.live.ott.irdeto.com','widevine-license.itvx.vudrm.tech')):
                return manifest, licence, {'Referer':'https://www.itv.com/','Origin':'https://www.itv.com'}
    except ValueError:
        raise
    except Exception:
        raise ValueError('ITV could not be reached. Please retry.') from None
    raise ValueError('ITV did not offer a compatible Pi stream.')
