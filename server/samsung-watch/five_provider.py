"""Channel 5 account access through its web client's Cognito/user-service APIs."""
import json
import time
from pathlib import Path
import requests
import os

def atomic(path, data):
    path=Path(path);temporary=path.with_suffix('.tmp')
    fd=os.open(temporary,os.O_WRONLY|os.O_CREAT|os.O_TRUNC,0o600)
    with os.fdopen(fd,'wb') as output:output.write(data)
    temporary.replace(path)

CLIENT='10ap8l6jp0vhreaac79c3qr1lq'
COGNITO='https://cognito-idp.eu-west-2.amazonaws.com/'
USER='https://userservice-api.channel5.com/'

class FiveLoginError(RuntimeError):
    def __init__(self, stage, code):
        import re
        safe = code if re.fullmatch(r'[A-Za-z0-9_-]{1,80}', str(code)) else 'UnexpectedResponse'
        super().__init__('Channel 5 %s: %s' % (stage, safe))

class FiveAccount:
    def __init__(self, private):
        self.path=Path(private)/'channel5-session.json'

    @staticmethod
    def authenticate(flow, parameters):
        response=requests.post(COGNITO,headers={'X-Amz-Target':'AWSCognitoIdentityProviderService.InitiateAuth','Content-Type':'application/x-amz-json-1.1'},json={'AuthFlow':flow,'ClientId':CLIENT,'AuthParameters':parameters},timeout=25)
        if response.status_code!=200 or not response.json().get('AuthenticationResult'):
            raise FiveLoginError('sign-in', response.json().get('__type', '').split('#')[-1] or response.json().get('ChallengeName') or 'NoAuthenticationResult')
        auth=response.json()['AuthenticationResult']
        response=requests.post(USER+'user/validateCognitoToken',json={'cognitoIdToken':auth['IdToken']},timeout=25)
        if not 200 <= response.status_code < 300:
            raise FiveLoginError('account session', 'HTTP%d' % response.status_code)
        data=response.json()
        token=data.get('sessionToken') or data.get('data',{}).get('sessionToken')
        if not token: raise FiveLoginError('account session', 'MissingSessionToken')
        return {'sessionToken':token,'refreshToken':auth.get('RefreshToken'),'expires_at':time.time()+int(auth.get('ExpiresIn',3600))-120}

    def login(self,email,password):
        session=self.authenticate('USER_PASSWORD_AUTH',{'USERNAME':email.lower().strip(),'PASSWORD':password})
        atomic(self.path,json.dumps(session).encode())

    def session(self):
        saved=json.loads(self.path.read_text())
        if saved['expires_at']<time.time():
            refreshed=self.authenticate('REFRESH_TOKEN_AUTH',{'REFRESH_TOKEN':saved['refreshToken']})
            refreshed['refreshToken']=refreshed.get('refreshToken') or saved['refreshToken']
            atomic(self.path,json.dumps(refreshed).encode());saved=refreshed
        session=requests.Session();session.headers['Authorization']='Bearer '+saved['sessionToken']
        return session

    def lists(self):
        selected={}
        with self.session() as session:
            for route,flag in [('favourites','favourite'),('resumePoints','recent')]:
                for offset in range(0,1000,100):
                    r=session.get(USER+route,params={'limit':100,'offset':offset},timeout=25)
                    if r.status_code!=200:raise RuntimeError('Channel 5 account list could not be read.')
                    data=r.json();items=data.get('results',[]) if isinstance(data,dict) else data
                    for item in items:
                        ident=item.get('showId')
                        if ident: selected.setdefault(str(ident),{'favourite':False,'recent':False})[flag]=True
                    if len(items)<100:break
        return selected

class LegacyClientTLS(requests.adapters.HTTPAdapter):
    """Legacy client certificate compatibility, scoped only to the Channel 5 auth host."""
    def init_poolmanager(self,*args,**kwargs):
        import ssl
        context=ssl.create_default_context()
        context.set_ciphers('DEFAULT:@SECLEVEL=0')
        kwargs['ssl_context']=context
        return super().init_poolmanager(*args,**kwargs)

def media(private, asset_id, live=False):
    import re
    if not re.fullmatch(r'[A-Za-z0-9_-]+',asset_id):raise ValueError('Invalid Channel 5 media ID.')
    with requests.Session() as session:
        session.mount('https://cassie-auth.channel5.com/',LegacyClientTLS())
        route='live_media' if live else 'media'
        r=session.get('https://cassie-auth.channel5.com/api/v2/'+route+'/my5androidhydradash/'+asset_id+'.json',cert=str(Path(private)/'channel5-client.pem'),timeout=25)
        if r.status_code!=200:raise RuntimeError('Channel 5 source unavailable.')
        assets=r.json().get('assets',[])
        asset=next((a for a in assets if a.get('drm')=='widevine'),None)
        if not asset:raise RuntimeError('No compatible Channel 5 source.')
        return asset

def catalogue(private):
    """Read favourites/recent titles; expose only sources that passed the compatibility probe."""
    private=Path(private)
    if not (private/'channel5-session.json').exists():return []
    check=json.loads((private/'channel5-playback-check.json').read_text())
    if not any(s.get('codec_name')=='h264' for s in check.get('streams',[])):return []
    selected=FiveAccount(private).lists()
    cache_path=private/'channel5-catalogue-cache.json'
    try:cache=json.loads(cache_path.read_text())
    except (OSError,ValueError):cache={}
    shows=[]
    # Account bearer credentials are never sent to the public catalogue/image hosts.
    with requests.Session() as session:
        film_url='https://corona.channel5.com/shows/search.json'
        params={'platform':'my5desktop','friendly':1,'limit':1000,'vod_subgenres[]':['6100117389032','6100117390032','6100117391032']}
        films=session.get(film_url,params=params,timeout=25)
        summaries={}
        if films.status_code==200:
            for film in films.json().get('shows',[]):
                ident=str(film['id']);summaries[ident]=film
                selected.setdefault(ident,{'favourite':False,'recent':False})
        for ident, flags in selected.items():
            record=cache.get(ident,{})
            if time.time()-record.get('updated_at',0)<21600:
                show=record['show'];raw_episodes=record['episodes']
            else:
                show=summaries.get(ident)
                if not show:
                    r=session.get('https://corona.channel5.com/shows/'+ident+'.json',params={'platform':'my5desktop','friendly':1},timeout=25)
                    if r.status_code!=200:continue
                    show=r.json()
                slug=show.get('f_name')
                if not slug:continue
                r=session.get('https://corona.channel5.com/shows/'+slug+'/episodes.json',params={'platform':'my5desktop','friendly':1,'limit':1000},timeout=25)
                if r.status_code!=200:continue
                raw_episodes=r.json().get('episodes',[])
                cache[ident]={'updated_at':time.time(),'show':show,'episodes':raw_episodes}
                atomic(cache_path,json.dumps(cache).encode())
            episodes=[];now=time.time();pid='five_'+ident
            for ep in raw_episodes:
                if ep.get('vod_s',0)>now or (ep.get('vod_e') and ep['vod_e']<now):continue
                episodes.append({'id':pid+'_'+ep['id'],'provider_id':'channel5','provider_episode_id':ep['id'],'available_at':ep.get('vod_s',0),'kind':'provider','title':ep.get('title') or 'Episode','season':ep.get('sea_num') or 'Episodes','episode_number':ep.get('ep_num',0),'description':ep.get('m_desc') or ep.get('s_desc',''),'thumbnail':'https://api-images.channel5.com/otis/images/episode/'+ep['id']+'/1280x720.jpg','duration_seconds':ep.get('len',0)/1000,'live':False})
            if episodes:
                shows.append({'id':pid,'title':show['title'],'provider':'Channel 5','provider_id':'channel5','genre':' · '.join(str(v) for v in [show.get('genre'),show.get('primary_vod_genre')]+show.get('vod_subgenres',[]) if v),'media_type':'movie' if show.get('genre')=='Film' else 'tv','description':show.get('m_desc') or show.get('s_desc',''),'artwork':'https://api-images.channel5.com/otis/images/show/'+ident+'/1280x720.jpg','hero':'https://api-images.channel5.com/otis/images/show/'+ident+'/1920x1080.jpg','episodes':episodes,**flags})
    return shows
