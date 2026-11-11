"""Samsung-authenticated playback extras; private queue for this single paired TV.
Uses the shared normalization contract without an Apple TV session or media preload.
"""
import asyncio,json,re,time
from pathlib import Path
from urllib.parse import urlencode
from aiohttp import web
from playback_features import PlaybackFeatures,source_key,series_after,episode_row
from tmdb_logos import atomic
from episode_versions import seconds as duration_seconds

class PlaybackAdapter:
    def init_playback_features(self):
        private=Path(self.settings['device_key_file']).parent
        self.features=PlaybackFeatures(private/'appletv')  # shared reviewed source markers, read only
        self.queue_path=private/'samsung-series-queue.json'

    def feature_rows(self):
        rows=[]
        for group in self.library():
            rows.append(dict(group,artwork=group.get('hero'),episodes=[dict(e,duration_seconds=duration_seconds(e.get('duration_seconds')),thumbnail=self.art_id(e.get('thumbnail')),brands=[b for b in group.get('brands',[]) if b.get('name')==p]) for e,p in group['_episodes']]))
        return rows

    @staticmethod
    def public_episode(rows,ident):
        for group in rows:
            for e in group.get('episodes',[]):
                if e['id']==ident:return episode_row(group,e)

    def bind_playback_features(self,prepared,episode,provider):
        source=dict(episode)
        # The original source ID is essential; canonical merged IDs are for progress only.
        key=source_key(source,provider)
        version=prepared.get('version_id')  # only a version reported by the actual resolver
        if not isinstance(version,str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,100}',version):version=None
        prepared['_features']={'source':source,'provider':provider,'source_key':key,'version_id':version}
        return {'source_key':key,'version_id':version,'provider':provider,
                'features_url':'/api/playback/features?'+urlencode({'episode_id':prepared['_episode_id']}),
                'up_next_url':'/api/playback/up-next?'+urlencode({'episode_id':prepared['_episode_id']})}

    async def playback_capabilities(self,request):
        return web.json_response({'schema_version':1,'chapters':True,'skip_markers':['intro','recap'],'series_queue':True,
            'marker_timebase':'episode','autoplay_owner':'client','preload_supported':False})

    async def playback_features(self,request):
        ident=request.query.get('episode_id');token=request.query.get('ticket')
        prepared=self.bridge.tickets.get(token) if token else None
        # Timings are available only when bound to this TV's owned, exact active session.
        if not prepared or token!=self.current_ticket or prepared.get('_episode_id')!=ident:raise web.HTTPNotFound()
        bound=prepared.get('_features')
        if not bound:raise web.HTTPNotFound()
        if request.query.get('source_key')!=bound['source_key']:raise web.HTTPConflict()
        version=request.query.get('version_id') or None
        if version!=bound['version_id']:raise web.HTTPConflict()
        result=await asyncio.to_thread(self.features.get,bound['source'],bound['provider'],version,prepared)
        # Do not return old metadata after a session was replaced during the lookup.
        if token!=self.current_ticket or self.bridge.tickets.get(token) is not prepared:raise web.HTTPConflict()
        return web.json_response(dict(result,episode_id=ident))

    async def up_next(self,request):
        ident=request.query.get('episode_id');rows=self.feature_rows()
        if not self.public_episode(rows,ident):raise web.HTTPNotFound()
        try:limit=int(request.query.get('limit','20'))
        except ValueError:raise web.HTTPBadRequest()
        if not 1<=limit<=100:raise web.HTTPBadRequest()
        items=series_after(rows,ident,limit)
        return web.json_response({'schema_version':1,'episode_id':ident,'order':'chronological','next_episode':items[0] if items else None,'items':items})

    def read_queue(self):
        try:return json.loads(self.queue_path.read_text())
        except (OSError,ValueError):return {}

    def write_queue(self,record):atomic(self.queue_path,json.dumps(record).encode())

    def queue_view(self,record,rows):
        def present(ident):
            row=self.public_episode(rows,ident)
            return dict(row or {'id':ident},available=row is not None)
        ids=record.get('episode_ids',[])
        return {'schema_version':1,'revision':record.get('revision',0),'autoplay':record.get('autoplay',False),
            'current':present(ids[0]) if ids else None,'items':[present(i) for i in ids[1:]],'updated_at':record.get('updated_at'),'autoplay_owner':'client'}

    async def series_queue(self,request):
        if request.method=='GET':return web.json_response(self.queue_view(self.read_queue(),self.feature_rows()))
        data=await request.json()
        if not isinstance(data,dict):raise web.HTTPBadRequest()
        record=self.read_queue()
        if type(data.get('expected_revision')) is not int or data['expected_revision']!=record.get('revision',0):raise web.HTTPConflict()
        rows=self.feature_rows()
        if request.method=='DELETE':ids=[];autoplay=False
        else:
            ident=data.get('episode_id');current=self.public_episode(rows,ident)
            if not current:raise web.HTTPNotFound()
            group=next(p for p in rows if p['id']==current['programme_id'])
            if group.get('live') or group.get('film'):raise web.HTTPBadRequest()
            if not isinstance(data.get('autoplay',False),bool):raise web.HTTPBadRequest()
            ids=[ident]+[e['id'] for e in series_after(rows,ident,10000)];autoplay=data.get('autoplay',False)
        record={'episode_ids':ids,'autoplay':autoplay,'revision':record.get('revision',0)+1,'updated_at':time.time()}
        self.write_queue(record);return web.json_response(self.queue_view(record,rows))

    async def advance_queue(self,request):
        data=await request.json()
        if not isinstance(data,dict):raise web.HTTPBadRequest()
        record=self.read_queue();ids=record.get('episode_ids',[])
        if type(data.get('expected_revision')) is not int or data['expected_revision']!=record.get('revision',0) or not ids or data.get('completed_episode_id')!=ids[0]:raise web.HTTPConflict()
        # The Samsung client must have saved real completion before queue advancement.
        if self.progress_record(ids[0]).get('completed') is not True:raise web.HTTPConflict()
        rows=self.feature_rows();remaining=[i for i in ids[1:] if self.public_episode(rows,i)]
        record.update(episode_ids=remaining,revision=record['revision']+1,updated_at=time.time())
        self.write_queue(record)
        return web.json_response(dict(self.queue_view(record,rows),removed_unavailable=len(ids)-1-len(remaining)))
