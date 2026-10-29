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
                streams=plugin.streams(stream_types=['hls','dash'])
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
