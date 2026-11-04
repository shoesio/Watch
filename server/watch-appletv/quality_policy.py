"""tvOS selection policy for streams normally exposed by Streamlink.

Provider restrictions and DRM handling are not changed here. Legacy device
preferences stay in the original catalogue and original bridge processes.
"""
def apple_episode(episode):
    result=dict(episode)
    if result.get('kind') == 'plugin':result['quality']='best'
    return result


def video_rank(label):
    # Streamlink weights add an audio bonus to DASH's "720p+a96k" name;
    # that is not a higher video resolution than the same HLS rendition.
    import re
    match=re.match(r'^(\d+)p(?:(\d+))?',label)
    return (int(match[1]),int(match[2] or 0)) if match else (0,0)


def bbc_streams_with_versions(plugin):
    """Keep the VPID that actually produced each stream, not a guessed edition."""
    import re
    original=plugin.mediaselector
    def selected(vpid):
        for name,stream in original(vpid):
            if re.fullmatch('[a-z0-9]{8}',str(vpid)):
                try:stream._watch_version_id=vpid
                except (AttributeError,TypeError):pass  # Metadata support must not break playback.
            yield name,stream
    plugin.mediaselector=selected
    try:return plugin.streams(stream_types=['hls','dash'])
    finally:plugin.mediaselector=original


def bbc_public_streams(plugin,episode):
    """Resolve publicly offered BBC renditions using current episode metadata.

    No account requests, cookies, client identities or protected-media handling.
    Availability and the exact selected edition stay attached to every stream.
    """
    import datetime,re,time
    from urllib.parse import urlsplit
    parts=urlsplit(episode.get('url',''))
    match=re.fullmatch(r'/iplayer/episode/([a-z0-9]{8})(?:/[^/]*)?/?',parts.path)
    if parts.scheme!='https' or parts.hostname not in ('www.bbc.co.uk','bbc.co.uk') or not match or episode.get('live'):return None
    pid=match[1]
    response=plugin.session.http.get('https://ibl.api.bbc.co.uk/ibl/v1/episodes/'+pid)
    response.raise_for_status()
    data=response.json()
    row=next((e for e in data.get('episodes',[]) if e.get('id')==pid),{})
    def available(version):
        if not re.fullmatch('[a-z0-9]{8}',str(version.get('id',''))):return False
        if any(word in str(version.get('kind','')).lower() for word in ('signed','describ')):return False
        for key in ('start','end'):
            raw=version.get('availability',{}).get(key)
            if not raw:continue
            try:stamp=datetime.datetime.fromisoformat(raw.replace('Z','+00:00')).timestamp()
            except (ValueError,TypeError):return False
            if (key=='start' and stamp>time.time()) or (key=='end' and stamp<=time.time()):return False
        return True
    versions=[v for v in row.get('versions',[]) if available(v)]
    versions.sort(key=lambda v:bool(v.get('uhd')),reverse=True)
    for version in versions:
        streams={}
        for name,stream in plugin.mediaselector(version['id']):
            try:stream._watch_version_id=version['id']
            except (AttributeError,TypeError):pass
            streams[name]=stream
        if streams:return streams
    return {}


def configure_bridge(base_class):
    class AppleTVBridge(base_class):
        def session_hls(self,episode):
            # Native routing can prefer HLS when its advertised quality matches
            # the best DASH rendition. Never downgrade resolution to avoid a relay.
            import json,streamlink
            from pathlib import Path
            from streamlink.stream.hls import HLSStream
            from bbc_auth import adapt
            session=streamlink.Streamlink()
            session.set_option('http-timeout',15)
            try:
                name,cls,url=session.resolve_url(episode['url'])
                if name!='bbciplayer':return session,None
                path=Path(self.config.get('plugin_options_file','/nonexistent'))
                options=json.loads(path.read_text()).get(name,{}) if path.exists() else {}
                plugin=adapt(cls(session,url,options=options))
                streams=bbc_public_streams(plugin,episode)
                if streams is None:streams=bbc_streams_with_versions(plugin)
                named=[(label,stream) for label,stream in streams.items() if label not in ('best','worst')]
                hls=[pair for pair in named if isinstance(pair[1],HLSStream)]
                if not hls:return session,None
                best=max(hls,key=lambda pair:(video_rank(pair[0]),str(pair[1].url).startswith('https://')))
                if video_rank(best[0])<max(video_rank(label) for label,_ in named):return session,None
                return session,best[1]
            except Exception:
                session.http.close();raise

        def session_stream(self,episode):
            return super().session_stream(apple_episode(episode))
    return AppleTVBridge
