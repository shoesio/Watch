"""Live badge marks are separate assets from landscape fallback cards."""
CHANNEL_LOGOS={'bbcone':'bbcone','bbctwo':'bbctwo','bbcfour':'bbcfour','bbcnews':'bbcnews','C4':'channel4','E4':'e4','M4':'more4','F4':'film4','4S':'4seven','C5':'channel5','C7':'5usa','C6':'5star','C0':'5action','C8':'5drama'}
def apply_channel_logos(programmes,base):
    for p in programmes:
        key=CHANNEL_LOGOS.get(p.get('live_channel'))
        if p.get('live') and key:p['channel_logo']=base.rstrip('/')+'/static/artwork/channel-marks-v2/'+key+'.png'
    return programmes
