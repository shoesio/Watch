"""Catalogue-only presentation: genres, films and deterministic newest-first order."""
import re
from datetime import datetime

GENRES = {
 'Comedy': ('comedy','sitcom'), 'Drama': ('drama','soap','biopic'),
 'Crime & thriller': ('crime','thriller','mystery'),
 'Documentaries': ('documentary','factual'), 'Entertainment': ('entertainment','reality','competition','chat show'),
 'Quiz & game shows': ('quiz','game show'), 'Children': ('children','kids','cbeebies','cbbc','animation','milkshake'),
 'Science fiction & fantasy': ('sci-fi','science fiction','fantasy'),
 'History': ('history','historical'), 'Travel': ('travel',), 'Food & lifestyle': ('food','cook','lifestyle','home','garden'),
 'Sport': ('sport',), 'News': ('news','current affairs'), 'Music': ('music',),
 'Action & adventure': ('action','adventure'), 'Romance': ('romance','romantic'), 'Horror': ('horror',)
}

def genres(values):
    text=' '.join(str(v) for v in values if v).casefold()
    return [name for name, terms in GENRES.items() if any(term in text for term in terms)]

def natural(value):
    return tuple((1,int(part)) if part.isdigit() else (0,part.casefold()) for part in re.split(r'(\d+)', str(value)))

def episode_order(episode):
    stamp=episode.get('broadcast_at') or episode.get('first_broadcast') or episode.get('air_date') or ''
    # Date-labelled series (e.g. specials) and numbered/lettered series remain stable.
    season=str(episode.get('season',''))
    numbered = bool(re.search(r'\d|series [a-z]$',season,re.I))
    return (numbered, natural(season), natural(episode.get('episode_number',0)), str(stamp), natural(episode.get('title','')))
