import json,unittest
import test_server as fixtures
from cinema_browse import shelves_for

class CinemaBrowseTests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp=fixtures.GatewayTests.asyncSetUp
    asyncTearDown=fixtures.GatewayTests.asyncTearDown

    async def test_metadata_only_auth_paged_shelves(self):
        self.assertEqual((await self.client.get('/api/cinema')).status,401)
        def forbidden(*args):raise AssertionError('Browsing must not prepare video')
        self.bridge.prepare=forbidden
        r=await self.client.get('/api/cinema?section=shows',headers=self.headers);self.assertEqual(r.status,200)
        d=await r.json();self.assertTrue(d['shelves']);self.assertNotIn('items',d['shelves'][0]);self.assertLess(len(json.dumps(d)),20000)
        r=await self.client.get('/api/cinema/shelf',params={'snapshot':d['snapshot'],'id':d['shelves'][0]['id']},headers=self.headers)
        row=await r.json();self.assertLessEqual(len(row['items']),5);self.assertNotIn('SECRET',json.dumps(row));self.assertNotIn('signed-secret',json.dumps(row))
        self.assertEqual((await self.client.get('/api/cinema/shelf?snapshot=invalid&id=all',headers=self.headers)).status,410)

    def test_portrait_shelves_are_real_and_all_titles_remain_reachable(self):
        rows=[{'id':str(i),'title':'Show '+str(i),'film':False,'live':False,'genres':['Comedy'],'poster':'poster' if i<5 else None} for i in range(12)]
        shelves=shelves_for(rows,rows,'shows')
        self.assertTrue(any(s['layout']=='portrait' for s in shelves))
        for shelf in shelves:
            if shelf['layout']=='portrait':self.assertTrue(all(p.get('poster') for p in shelf['items']))
        self.assertEqual({p['id'] for s in shelves for p in s['items']},{p['id'] for p in rows})

    def test_continue_and_named_christmas_episode_identity(self):
        p={'id':'show','title':'Show','film':False,'resume_episode':'old','episodes':[{'id':'old','title':'Episode 1','season':'1','episode_number':1,'updated_at':10,'progress':50},{'id':'new','title':'Christmas Special','season':'2','episode_number':2}],'hero':'hero','genres':[]}
        shelves=shelves_for([p],[p],'home');continuing=next(s for s in shelves if s['id']=='continue')['items'][0]
        self.assertEqual(continuing['home_episode'],'old');self.assertEqual(continuing['progress'],50)
        named=next((s for s in shelves if s['id']=='christmas'),None)
        if named:self.assertEqual(named['items'][0]['home_episode'],'new')
