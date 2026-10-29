import asyncio,json,pathlib,sys
import aiohttp
ROOT=pathlib.Path(__file__).resolve().parent
SETTINGS=json.loads((ROOT/'settings.json').read_text())
TOKEN=pathlib.Path(SETTINGS['ha_token_file']).read_text().strip()
BASE=SETTINGS['ha_url'].rstrip('/')
async def main():
 async with aiohttp.ClientSession(headers={'Authorization':'Bearer '+TOKEN}) as s:
  async with s.ws_connect(BASE+'/api/websocket') as w:
   await w.receive_json();await w.send_json({'type':'auth','access_token':TOKEN});assert (await w.receive_json())['type']=='auth_ok'
   n=0
   async def call(msg):
    nonlocal n;n+=1;await w.send_json(dict(msg,id=n))
    while True:
     r=await w.receive_json()
     if r.get('id')==n:
      if not r.get('success'):raise RuntimeError(str(r.get('error')))
      return r.get('result')
   if sys.argv[1]=='inspect':
    for name,msg in [('dashboards',{'type':'lovelace/dashboards/list'}),('resources',{'type':'lovelace/resources'})]:
     print(name,json.dumps(await call(msg)))
   elif sys.argv[1]=='deploy':
    import yaml,datetime
    dashboards=await call({'type':'lovelace/dashboards/list'})
    resources=await call({'type':'lovelace/resources'})
    backup=ROOT/'backup';backup.mkdir(exist_ok=True)
    stamp=datetime.datetime.now().strftime('%Y%m%d-%H%M%S')
    (backup/(stamp+'-dashboards.json')).write_text(json.dumps(dashboards))
    (backup/(stamp+'-resources.json')).write_text(json.dumps(resources))
    if any(x['url_path']=='tv-favourites' for x in dashboards):
     raise RuntimeError('Dashboard already exists; inspect before modifying.')
    script=yaml.safe_load((ROOT/'script.yaml').read_text())
    async with s.get(BASE+'/api/config/script/config/tv_favourites_play') as r:
     if r.status==200:raise RuntimeError('Script name already exists; inspect before modifying.')
     if r.status!=404:raise RuntimeError('Unexpected script lookup response '+str(r.status))
    async with s.post(BASE+'/api/config/script/config/tv_favourites_play',json=script) as r:
     print('script',r.status);assert r.status==200
    if not any(x['url_path']=='tv-favourites' for x in dashboards):
     await call({'type':'lovelace/dashboards/create','url_path':'tv-favourites','title':'TV favourites','icon':'mdi:television-play','show_in_sidebar':True,'require_admin':False})
    else:raise RuntimeError('Dashboard already exists; inspect before modifying.')
    if not any('/tv-favourites-card.js' in x['url'] for x in resources):
     await call({'type':'lovelace/resources/create','res_type':'module','url':SETTINGS['public_base'].rstrip('/')+'/static/tv-favourites-card.js?v=3'})
    config=yaml.safe_load((ROOT/'dashboard.yaml').read_text())
    await call({'type':'lovelace/config/save','url_path':'tv-favourites','config':config})
    print('New dashboard saved; existing dashboards preserved.')
   elif sys.argv[1]=='verify':
    config=await call({'type':'lovelace/config','url_path':'tv-favourites'})
    print('dashboard',json.dumps(config))
    async with s.get(BASE+'/api/states/sensor.tv_favourites') as r:
     data=await r.json();print('sensor',json.dumps(data))
   elif sys.argv[1]=='event-test':
    async with s.post(BASE+'/api/services/script/tv_favourites_play',json={'episode_id':'invalid_test','endpoint_id':'invalid_test'}) as r:
     print('Invalid selection script response:',r.status)
    await asyncio.sleep(1)
    async with s.get(BASE+'/api/states/sensor.tv_favourites') as r:
     print('Bridge response:',(await r.json())['attributes']['message'])
asyncio.run(main())
