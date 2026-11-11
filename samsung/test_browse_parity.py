"""Samsung detail navigation, presentation, artwork and chronological continuations."""
import asyncio,json,threading,time,unittest
from pathlib import Path
from PIL import Image
import test_server as fixtures
from playback_features import PlaybackFeatures,series_after,source_key

class BrowseParityTests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp=fixtures.GatewayTests.asyncSetUp
    asyncTearDown=fixtures.GatewayTests.asyncTearDown

    def numbered(self):
        p=self.bridge.catalogue['programmes'][0]
        template=p['episodes'][0]
        p['episodes']=[dict(template,id='ep'+str(i),season=str(1 if i<5 else 2),episode_number=i if i<5 else i-4,duration_seconds=1740,description='Actual episode synopsis') for i in range(1,9)]
        self.bridge.catalogue['programmes']=[p]
        return self.gateway.library()[0]

    async def test_all_series_focus_and_metadata(self):
        group=self.numbered();self.gateway.quality.records['ep1']={'height':720}
        r=await self.client.get('/api/episodes/'+group['id']+'?size=4&season=all&focus_episode=ep1',headers=self.headers)
        d=await r.json();self.assertEqual(d['total'],8);self.assertEqual(d['page'],1);self.assertEqual(d['focus_index'],3)
        self.assertEqual(d['items'][3]['id'],'ep1');self.assertEqual(d['items'][3]['display_title'],'Series 1: Episode 1')
        self.assertEqual(d['items'][3]['meta'],'29 Min • HD');self.assertEqual(d['items'][3]['description'],'Actual episode synopsis')
        self.assertEqual(d['series_count'],2)
        season=self.gateway.season_id({'season':'1'})
        d=await (await self.client.get('/api/episodes/'+group['id']+'?size=4&season='+season,headers=self.headers)).json()
        self.assertEqual(d['total'],4);self.assertEqual(d['items'][-1]['display_title'],'Episode 1')
        self.assertNotIn('SECRET',json.dumps(d))

    async def test_show_details_and_single_series(self):
        group=self.numbered();self.bridge.catalogue['programmes'][0]['episodes']=self.bridge.catalogue['programmes'][0]['episodes'][:4]
        self.assertEqual((await self.client.get('/api/show/'+group['id'])).status,401)
        d=await (await self.client.get('/api/show/'+group['id'],headers=self.headers)).json()
        self.assertEqual(d['title'],'Example Show');self.assertNotIn('_episodes',d)
        d=await (await self.client.get('/api/episodes/'+group['id'],headers=self.headers)).json()
        self.assertEqual(d['series_count'],1);self.assertTrue(all(not e['display_title'].startswith('Series') for e in d['items']))

    async def test_matched_posters_and_no_landscape_substitutes(self):
        group=self.numbered();cache={group['id']+':tv':{'poster_path':'/Abc.jpg','backdrop_path':'/Xyz.jpg'}}
        (self.root/'catalogue-artwork.json').write_text(json.dumps(cache));self.gateway.matched_artwork.checked=0
        p=self.gateway.library()[0];self.assertIn('image.tmdb.org',self.gateway.art[p['poster']]);self.assertEqual(p['hero'],p['card_artwork'])
        Image.new('RGB',(400,600)).save(self.root/'portrait.jpg');Image.new('RGB',(1600,900)).save(self.root/'landscape.jpg')
        self.assertTrue(self.gateway.get_image(self.gateway.art_id('/local/tv-favourites/portrait.jpg'),'poster'))
        with self.assertRaises(ValueError):self.gateway.get_image(self.gateway.art_id('/local/tv-favourites/landscape.jpg'),'poster')

    async def test_artwork_requests_coalesce(self):
        count=[]
        def process(*args):count.append(True);time.sleep(.06);return b'jpeg'
        self.gateway.get_image=process
        replies=await asyncio.gather(*[self.client.get('/art/example?size=thumb',headers=self.headers) for _ in range(4)])
        self.assertTrue(all(r.status==200 for r in replies));self.assertEqual(len(count),1)

    def test_qi_w_to_x_and_no_special_guess(self):
        episodes=[{'id':'w','season':'Series W','episode_number':16},{'id':'x','season':'Series X','episode_number':1},{'id':'special','season':'Christmas','episode_number':1}]
        groups=[{'id':'qi','title':'QI','episodes':episodes}]
        self.assertEqual([e['id'] for e in series_after(groups,'w')],['x']);self.assertEqual(series_after(groups,'special'),[])

    def test_credits_are_verified_cues_never_skip_controls(self):
        source={'id':'ep','url':'https://example.invalid/episode','duration_seconds':100}
        key=source_key(source,'U');root=self.root/'markers';root.mkdir()
        record={'verified':True,'version_id':'edition','duration_seconds':100,'credits':[{'kind':'credits','start':80,'end':100}]}
        (root/'playback-markers.json').write_text(json.dumps({key:record}));features=PlaybackFeatures(root)
        data=features.get(source,'U','edition');self.assertEqual(data['credits'][0]['start'],80);self.assertEqual(data['skip_markers'],[])
        self.assertEqual(features.get(source,'U','other')['credits'],[])
        source['duration_seconds']=120;self.assertEqual(features.get(source,'U','edition')['credits'],[])
