"""Small, read-only programme guide from the BBC and Channel 4's own listings."""
import concurrent.futures
import datetime as dt
import json
import re
import time
from pathlib import Path
from zoneinfo import ZoneInfo
import requests

BBC = {'bbcone':'bbc_one_london', 'bbctwo':'bbc_two_england',
       'bbcnews':'bbc_news24', 'bbcfour':'bbc_four'}


def timestamp(value):
    return dt.datetime.fromisoformat(value.replace('Z','+00:00')).timestamp()


def initial_data(html):
    match = re.search(r'var initialData\s*=\s*', html)
    if not match:
        raise ValueError('Programme guide data is unavailable.')
    return json.JSONDecoder().raw_decode(html[match.end():])[0]


class GuideSync:
    def __init__(self, path):
        self.path = Path(path)

    def read(self):
        try:
            return json.loads(self.path.read_text())
        except (OSError, ValueError):
            return {'channels':{}}

    def bbc(self, slug, channel, dates):
        slots = []
        for day in dates:
            r = requests.get('https://ibl.api.bbci.co.uk/ibl/v1/channels/'+channel+'/schedule/'+day, timeout=20)
            r.raise_for_status()
            for item in r.json()['schedule']['elements']:
                episode = item.get('episode', {})
                slots.append({'title':episode.get('title', 'Programme'),
                    'subtitle':episode.get('subtitle', ''),
                    'description':episode.get('synopses', {}).get('small', ''),
                    'start':timestamp(item['scheduled_start']), 'end':timestamp(item['scheduled_end'])})
        return {slug:slots}

    def channel4(self, dates):
        channels = {}
        for day in dates:
            r = requests.get('https://www.channel4.com/tv-guide/'+day, timeout=20)
            r.raise_for_status()
            for code, channel in initial_data(r.text)['channels'].items():
                if code not in ('C4','E4','M4','F4','4S'):
                    continue
                slots = channels.setdefault(code, [])
                for item in channel.get('programmes', []):
                    slots.append({'title':item.get('brandTitle') or item['title'],
                        'subtitle':item.get('title', ''), 'description':item.get('summary', ''),
                        'start':timestamp(item['startDate']), 'end':timestamp(item['endDate'])})
        return channels

    def run(self):
        today = dt.datetime.now(ZoneInfo('Europe/London')).date()
        dates = [(today+dt.timedelta(days=i)).isoformat() for i in (-1,0,1)]
        data = self.read()
        channels = data.setdefault('channels', {})
        jobs = [lambda slug=k, channel=v:self.bbc(slug, channel, dates) for k,v in BBC.items()]
        jobs.append(lambda:self.channel4(dates))
        statuses = []
        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as pool:
            futures = [pool.submit(job) for job in jobs]
            for future in futures:
                try:
                    for channel, slots in future.result().items():
                        unique = {(s['start'],s['end']):s for s in slots}
                        channels[channel] = {'updated_at':time.time(),
                            'programmes':sorted(unique.values(), key=lambda s:s['start'])}
                    statuses.append(True)
                except (requests.RequestException, ValueError, KeyError):
                    statuses.append(False)
        data['updated_at'] = time.time()
        self.path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        temporary = self.path.with_suffix('.tmp')
        temporary.write_text(json.dumps(data))
        temporary.replace(self.path)
        return data

    def now_next(self):
        now = time.time()
        result = {}
        for channel, data in self.read().get('channels', {}).items():
            # Never present an old listing as currently on air.
            if now-data.get('updated_at',0) > 86400:
                continue
            slots = data.get('programmes', [])
            current = next((s for s in slots if s['start'] <= now < s['end']), None)
            following = next((s for s in slots if s['start'] > now), None)
            result[channel] = {'now':current, 'next':following, 'updated_at':data['updated_at']}
        return result
