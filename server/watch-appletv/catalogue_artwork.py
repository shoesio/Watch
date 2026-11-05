"""Matched portrait artwork for Watch. Credentials stay on the host.

Catalogue responses only read the cache and enqueue metadata work. TMDB lookups
run separately from playback preparation and never create a media session.
"""
import hashlib
import json
import re
import threading
import time
from pathlib import Path


def identity(title):
    key = re.sub(r'[^\w]+', ' ', title.casefold().replace('’', "'")).strip()
    return hashlib.sha256(key.encode()).hexdigest()[:20]


def poster_url(path):
    return 'https://image.tmdb.org/t/p/w780' + path if isinstance(path, str) and re.fullmatch(r'/[A-Za-z0-9]+\.jpg', path) else None


class CatalogueArtwork:
    def __init__(self, private, base):
        self.private = Path(private)
        self.base = base.rstrip('/')
        self.path = self.private / 'catalogue-artwork.json'
        try:
            self.cache = json.loads(self.path.read_text())
        except (OSError, ValueError):
            self.cache = {}
        self.pending = {}
        self.lock = threading.Lock()

    def enrich(self, value, priority=3):
        if isinstance(value, list):
            for item in value:
                self.enrich(item, priority)
        elif isinstance(value, dict):
            if all(k in value for k in ('id', 'title', 'live', 'film')) and not value['live']:
                ident = identity(value['title'])
                kind = 'movie' if value['film'] else 'tv'
                row = self.cache.get(ident + ':' + kind, {})
                url = poster_url(row.get('poster_path'))
                if url:
                    value['poster'] = url
                archive=row.get('archive_year')
                if isinstance(archive,int) and 1888<=archive<=time.gmtime().tm_year:
                    value['archive_year']=archive
                backdrop=poster_url(row.get('backdrop_path'))
                if backdrop:
                    value['card_artwork']=backdrop.replace('/w780/','/w1280/')
                if (self.private / 'show-logos' / (ident + '.png')).is_file():
                    value['show_logo'] = self.base + '/static/show-logos/' + ident + '.png'
                rank = 0 if value.get('recent') or value.get('favourite') else priority
                with self.lock:
                    key = ident + ':' + kind
                    old = self.pending.get(key)
                    if old is None or rank < old[0]:
                        self.pending[key] = (rank, value['title'], kind)
            else:
                for key, item in value.items():
                    self.enrich(item, 1 if key.startswith('featured') else 2 if key in ('hot', 'personal') else priority)
        return value

    def refresh(self, limit=12, client=None):
        credential = self.private / 'tmdb-token'
        if client is None:
            if not credential.is_file():
                return
            from tmdb_logos import TMDB
            client = TMDB(credential.read_text())
        from tmdb_logos import atomic
        try:
            manifest = json.loads((self.private / 'tmdb-logo-manifest.json').read_text())
        except (OSError, ValueError):
            manifest = {}
        with self.lock:
            candidates = sorted(self.pending.items(), key=lambda pair: pair[1][0])
        checked = 0
        for key, (_, title, kind) in candidates:
            if self.cache.get(key, {}).get('editorial_schema') == 1 and self.cache.get(key, {}).get('backdrop_checked') and time.time() - self.cache.get(key, {}).get('checked_at', 0) < 14 * 86400:
                continue
            ident = identity(title)
            known = manifest.get(ident, {})
            if not known.get('tmdb_id'):known=self.cache.get(key,{})
            try:
                if known.get('tmdb_id') and known.get('media_type') == kind:
                    match = client.get(f"{kind}/{int(known['tmdb_id'])}", language='en-GB')
                else:
                    match = client.match(title, kind)
                    if match and match.get('_media_type', kind) != kind:
                        match = None
                row = {'checked_at': time.time(), 'title': title, 'media_type': kind, 'backdrop_checked':True,'editorial_schema':1}
                if match:
                    row['tmdb_id'] = match['id']
                    date=match.get('release_date') if kind=='movie' else match.get('last_air_date') if match.get('status') in ('Ended','Canceled') else None
                    if isinstance(date,str) and re.fullmatch(r'[0-9]{4}-[0-9]{2}-[0-9]{2}',date):
                        year=int(date[:4])
                        if 1888<=year<=time.gmtime().tm_year:row['archive_year']=year
                    if poster_url(match.get('backdrop_path')):row['backdrop_path']=match['backdrop_path']
                    if poster_url(match.get('poster_path')):
                        row['poster_path'] = match['poster_path']
                    logo = self.private / 'show-logos' / (ident + '.png')
                    if not logo.is_file():
                        data, _ = client.logo(match['id'], kind)
                        if data:
                            atomic(logo, data)
                self.cache[key] = row
                atomic(self.path, json.dumps(self.cache).encode())
            except Exception:
                # A failed lookup must not delay a catalogue request or expose
                # authenticated URLs in logs. Leave it eligible for a retry.
                pass
            checked += 1
            if checked >= limit:
                break
