"""Private, conservative TMDB clear-logo cache. No credentials reach the TV."""
import contextlib
import fcntl
import difflib
import hashlib
import io
import json
import os
from pathlib import Path
import re
import time
import tempfile
import requests
from PIL import Image

NOTICE = 'This product uses the TMDB API but is not endorsed or certified by TMDB.'
ALIASES = {'taskmaster bleeped': 'Taskmaster', 'qi xl': 'QI',
           'have i got a bit more news for you': 'Have I Got News for You'}

def normal(value):
    value = value.replace('&', ' and ')
    return re.sub(r'[^\w]+', ' ', value.casefold().replace('’', "'")).strip()

def atomic(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix='.tmdb-', dir=path.parent)
    temporary = Path(name)
    try:
        with os.fdopen(fd, 'wb') as target:
            target.write(data)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)

# Reviewed against the provider editions and TMDB search results, not popularity guesses.
REVIEWED = {'bluey': ('tv', 82728), 'doctor who 2005 2022': ('tv', 57243),
    'blankety blank': ('tv', 136009), 'the great british bake off': ('tv', 87012),
    'taskmaster new zealand': ('tv', 111880), 'masterchef junior usa': ('tv', 57755),
    'mr burton': ('movie', 1242454), 'sicario': ('movie', 273481),
    'dave gorman modern life is goodish': ('tv', 59815)}

def is_live(programme):
    return bool(programme.get('live') or programme.get('live_channel') or
                (programme.get('episodes') and all(e.get('live') for e in programme['episodes'])))

def is_film(programme):
    return programme.get('media_type') == 'movie' or bool(re.search(r'\bfilm', str(programme.get('genre', '')), re.I))

class TMDB:
    def __init__(self, token):
        self.token = token.strip()
        self.session = requests.Session()
        self.session.headers['User-Agent'] = 'WatchHome/2 (personal television library)'
        if not re.fullmatch(r'[a-fA-F0-9]{32}', self.token):
            self.session.headers['Authorization'] = 'Bearer ' + self.token

    def get(self, route, **params):
        if re.fullmatch(r'[a-fA-F0-9]{32}', self.token):
            params['api_key'] = self.token
        response = self.session.get('https://api.themoviedb.org/3/' + route,
                                    params=params, timeout=(5, 20))
        if response.status_code != 200:
            raise RuntimeError('TMDB request failed (HTTP %d).' % response.status_code)
        return response.json()

    def match(self, title, media_type='tv'):
        reviewed = REVIEWED.get(normal(title))
        if reviewed:
            kind, ident = reviewed
            item = self.get('%s/%d' % (kind, ident), language='en-GB')
            item['_media_type'] = kind
            return item
        query = ALIASES.get(normal(title), title)
        results = self.get('search/' + media_type, query=query, include_adult='false', language='en-GB')['results']
        def names(r):
            return (normal(r.get('name', r.get('title', ''))), normal(r.get('original_name', r.get('original_title', ''))))
        exact = [r for r in results if normal(query) in names(r)]
        british = [r for r in exact if 'GB' in r.get('origin_country', [])]
        candidates = british or exact
        if len(candidates) != 1 and not exact:
            # Accept only a strong spelling/title variant with a clear lead over alternatives.
            ranked = sorted(((max(difflib.SequenceMatcher(None, normal(query), n).ratio() for n in names(r)), r) for r in results), key=lambda x:x[0], reverse=True)
            candidates = [ranked[0][1]] if ranked and ranked[0][0] >= .93 and (len(ranked) == 1 or ranked[0][0] - ranked[1][0] >= .08) else []
        if len(candidates) != 1:
            return None
        item = self.get('%s/%d' % (media_type, candidates[0]['id']), language='en-GB')
        item['_media_type'] = media_type
        return item

    def logo(self, series_id, media_type="tv"):
        logos = self.get('%s/%d/images' % (media_type, series_id), include_image_language='en,null').get('logos', [])
        logos = [l for l in logos if l.get('iso_639_1') in ('en', None) and
                 re.fullmatch(r'/[A-Za-z0-9]+\.(png|svg)', l.get('file_path', ''))]
        logos.sort(key=lambda l: (l.get('iso_639_1') == 'en', l.get('width', 0), l.get('vote_count', 0)), reverse=True)
        for logo in logos:
            path = re.sub(r'\.svg$', '.png', logo['file_path'])
            # Separate session prevents sending API authentication to the image CDN.
            with requests.get('https://image.tmdb.org/t/p/original' + path, timeout=(5, 20), stream=True) as response:
                if response.status_code != 200:
                    continue
                data = bytearray()
                for chunk in response.iter_content(65536):
                    data.extend(chunk)
                    if len(data) > 10 * 1024 * 1024:
                        raise RuntimeError('TMDB image exceeds cache limit.')
            with Image.open(io.BytesIO(data)) as source:
                if source.width * source.height > 20000000:
                    continue
                image = source.convert('RGBA')
                alpha = image.getchannel('A')
                # Only transparent clear logos; do not put rectangular posters in the hero.
                if alpha.getextrema()[0] == 255 or not alpha.getbbox():
                    continue
                image = image.crop(alpha.getbbox())
                image.thumbnail((1800, 600), Image.Resampling.LANCZOS)
                output = io.BytesIO()
                image.save(output, 'PNG')
                return output.getvalue(), path
        return None, None

def sync(private, programmes, logo_dir=None):
    private = Path(private)
    with (private / 'tmdb-sync.lock').open('a') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return {'connected': (private / 'tmdb-token').exists(), 'downloaded': 0, 'review': 0}
        return _sync(private, programmes, logo_dir)

def _sync(private, programmes, logo_dir=None):
    private = Path(private)
    credential = private / 'tmdb-token'
    if not credential.is_file():
        return {'connected': False, 'downloaded': 0, 'review': 0}
    client = TMDB(credential.read_text())
    manifest_path = private / 'tmdb-logo-manifest.json'
    try:
        manifest = json.loads(manifest_path.read_text())
    except (OSError, ValueError):
        manifest = {}
    downloaded = review = 0
    now = time.time()
    for programme in programmes:
        if is_live(programme) or programme.get('blocked'):
            continue
        title = programme['title']
        group_title = re.sub(r'[^\w]+', ' ', title.casefold().replace('’', "'")).strip()
        ident = hashlib.sha256(group_title.encode()).hexdigest()[:20]
        destination = Path(logo_dir or private / 'show-logos') / (ident + '.png')
        previous = manifest.get(ident, {})
        if is_film(programme) and previous.get('schema') != 2:
            destination.unlink(missing_ok=True)
        interval = 30 * 86400 if destination.exists() else 7 * 86400
        if previous.get('schema') == 2 and now - previous.get('checked_at', 0) < interval:
            continue
        match = client.match(title, 'movie' if is_film(programme) else 'tv')
        record = {'title': title, 'checked_at': now, 'status': 'needs-review', 'schema': 2}
        if match:
            record.update(tmdb_id=match['id'], matched_title=match.get('name', match.get('title')), media_type=match.get('_media_type', 'tv'), genres=[g['name'] for g in match.get('genres', [])], status='no-clear-logo')
            data, path = client.logo(match['id'], match.get('_media_type', 'tv'))
            if data:
                atomic(destination, data)
                downloaded += 1
                record.update(status='downloaded', image_path=path)
        else:
            review += 1
        manifest[ident] = record
        atomic(manifest_path, json.dumps(manifest, indent=2).encode())
    return {'connected': True, 'downloaded': downloaded, 'review': review}
