"""Use current broadcast presentation for live playback, not duplicate channel titles."""
def apply_live_metadata(meta,programmes,ident):
    group=next((p for p in programmes if p.get('live') and any(e['id']==ident for e in p.get('episodes',[]))),None)
    if not group:return meta
    now=(group.get('guide') or {}).get('now') or {}
    meta.update(title=now.get('title') or group['title'],show_title=group['title'],description=now.get('subtitle') or '',artwork=now.get('image') or group.get('artwork'),channel_logo=group.get('channel_logo'))
    return meta
