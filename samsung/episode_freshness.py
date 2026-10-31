"""Provider dates and first-seen episode IDs; never treat a catalogue sync as a release."""
import datetime,json,math,time
from pathlib import Path
from tmdb_logos import atomic


def timestamp(value, now=None):
    now=time.time() if now is None else now
    try:
        if isinstance(value,(int,float)):
            stamp=float(value)
            if stamp>100000000000:stamp/=1000
        else:
            date=datetime.datetime.fromisoformat(str(value).replace('Z','+00:00'))
            if date.tzinfo is None:date=date.replace(tzinfo=datetime.timezone.utc)
            stamp=date.timestamp()
        return stamp if math.isfinite(stamp) and 0<stamp<=now else 0
    except (ValueError,TypeError,OverflowError):return 0


def released(episode,now=None):
    return max((timestamp(episode.get(key),now) for key in ('broadcast_at','first_broadcast','air_date','available_at','first_seen_at')),default=0)


class EpisodeFreshness:
    def __init__(self,path):
        self.path=Path(path)
        try:self.records=json.loads(self.path.read_text())
        except (OSError,ValueError):self.records={}
        if not isinstance(self.records,dict):self.records={}

    def enrich(self,programmes,now=None):
        now=time.time() if now is None else now
        changed=False
        for programme in programmes:
            ident=programme['id'];initial=ident not in self.records
            known=self.records.setdefault(ident,{})
            for episode in programme.get('episodes',[]):
                eid=episode.get('id')
                if not eid:continue
                if eid not in known:
                    # Existing programmes establish a baseline without pretending
                    # their whole back catalogue was released just now.
                    known[eid]={'first_seen_at':0 if initial else now};changed=True
                row=known[eid]
                if not isinstance(row,dict):row={'first_seen_at':row};known[eid]=row;changed=True
                for key in ('broadcast_at','available_at'):
                    if episode.get(key):
                        if row.get(key)!=episode[key]:row[key]=episode[key];changed=True
                    elif row.get(key):episode[key]=row[key]
                episode['first_seen_at']=row.get('first_seen_at',0)
        if changed:atomic(self.path,json.dumps(self.records).encode())
        return programmes
