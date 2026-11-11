"""Samsung presentation helpers; cached matched artwork only, no provider/pairing calls."""
import json,re,time
from pathlib import Path
from library_browse import natural
from episode_versions import seconds

class MatchedArtwork:
    def __init__(self,private):self.path=Path(private)/'catalogue-artwork.json';self.checked=0;self.rows={}
    def get(self,ident,film):
        if time.monotonic()-self.checked>30:
            self.checked=time.monotonic()
            try:self.rows=json.loads(self.path.read_text())
            except (OSError,ValueError):self.rows={}
        row=self.rows.get(ident+(':'+('movie' if film else 'tv')),{})
        def url(key,size):
            path=row.get(key)
            return 'https://image.tmdb.org/t/p/'+size+path if isinstance(path,str) and re.fullmatch(r'/[A-Za-z0-9]+\.jpg',path) else None
        return {'poster':url('poster_path','w500'),'card_artwork':url('backdrop_path','w1280')}

def episode_heading(episode,mixed):
    number=episode.get('episode_number');season=str(episode.get('season') or '').strip()
    if number:
        prefix=(season if re.match(r'^(Series|Season)\s',season,re.I) else 'Series '+season)+': ' if mixed and season else ''
        return prefix+'Episode '+str(number)
    return str(episode.get('title') or 'Episode')

def episode_caption(duration,quality):
    return ' • '.join(part for part in [str(int(seconds(duration)//60))+' Min' if seconds(duration)>0 else '',quality or ''] if part)
