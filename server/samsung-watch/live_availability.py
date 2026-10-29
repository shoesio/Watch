"""Hide positively identified off-air listings, without mistaking a guide outage for one."""
import re

def off_air(programme,now):
    if not programme.get('live'):return False
    current=(programme.get('guide') or {}).get('now') or {}
    try:
        if not float(current['start'])<=now<float(current['end']):return False
    except (KeyError,ValueError,TypeError):return False
    title=re.sub(r'[^a-z0-9]+',' ',str(current.get('title') or '').casefold()).strip()
    if title in {'off air','offair','not broadcasting','no programmes','programmes resume later','programmes start at 7pm','programmes start at 7 00pm'}:return True
    # BBC's daytime holding slate is scheduled as a programme of its own.
    return bool(re.fullmatch(r'this is bbc (?:one|two|three|four|news|news channel|parliament|scotland)',title))

def on_air_channels(programmes,now):
    return [p for p in programmes if not off_air(p,now)]
