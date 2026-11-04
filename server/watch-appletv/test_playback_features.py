import unittest,time
from unittest.mock import patch
from types import SimpleNamespace
from playback_features import intervals,series_after,PlaybackFeatures,source_key
import test_server

def library():
 return [{'id':'show','title':'Series','film':False,'live':False,'episodes':[
 {'id':'s2e1','title':'New season','season':'2','episode_number':1},
 {'id':'s1e2','title':'Second','season':'1','episode_number':2},
 {'id':'special','title':'Special','season':'Specials'},
 {'id':'s1e1','title':'First','season':'1','episode_number':1}]}]

class Metadata(unittest.TestCase):
 def test_rejects_untrusted_times_and_deduplicates(self):
  rows=[{'start':0,'end':30,'kind':'intro'},{'start':0,'end':30,'kind':'intro'},{'start':float('nan'),'end':40},{'start':5,'end':4},{'start':True,'end':3},{'start':0,'end':500}]
  self.assertEqual(len(intervals(rows,100,skip=True)),1)
 def test_next_is_chronological_across_seasons_not_display_order(self):
  self.assertEqual([e['id'] for e in series_after(library(),'s1e1')],['s1e2','s2e1'])
  self.assertEqual(series_after(library(),'special'),[])
  self.assertEqual(series_after(library(),'s2e1'),[])
 def test_films_live_and_unknown_do_not_queue(self):
  for field in ['film','live']:
   rows=library();rows[0][field]=True;self.assertEqual(series_after(rows,'s1e1'),[])
  self.assertEqual(series_after(library(),'missing'),[])
 def test_bbc_requires_exact_version_never_first_available(self):
  from pathlib import Path
  f=PlaybackFeatures(Path('/nonexistent'));source={'id':'a','url':'https://www.bbc.co.uk/iplayer/episode/b1234567','duration_seconds':100}
  episode={'versions':[{'id':'v1234567','interactions':[{'type':'skip','subtype':'intro','interaction_points':{'show_from':5,'skip_to':30}}]}]}
  with patch.object(f,'bbc',return_value=episode) as fetch:
   self.assertEqual(f.get(source,'BBC iPlayer')['status'],'version_required');fetch.assert_not_called()
   self.assertEqual(f.get(source,'BBC iPlayer','v7654321')['skip_markers'],[])
   row=f.get(source,'BBC iPlayer','v1234567');self.assertEqual(row['skip_markers'][0]['end'],30)
 def test_source_identity_distinguishes_editions(self):
  self.assertNotEqual(source_key({'id':'one'},'BBC'),source_key({'id':'two'},'BBC'))
 def test_source_ffprobe_chapters_are_normalized(self):
  from pathlib import Path
  f=PlaybackFeatures(Path('/nonexistent'))
  result=f.get({'id':'x'},'Other',prepared={'info':{'chapters':[{'start_time':'1.2','end_time':'12.4','tags':{'title':'Opening'}}]}})
  self.assertEqual(result['chapters'][0]['title'],'Opening');self.assertEqual(result['status'],'available')

class API(unittest.IsolatedAsyncioTestCase):
 asyncSetUp=test_server.Tests.asyncSetUp
 asyncTearDown=test_server.Tests.asyncTearDown
 idle=test_server.Tests.idle
 async def auth(self,code='12345678'):
  token=await test_server.Tests.pair(self,code);return {'Authorization':'Bearer '+token}
 async def test_auth_and_queue_isolation_and_restart_persistence(self):
  self.assertEqual((await self.client.get('/playback/capabilities')).status,401)
  first=await self.auth();second=await self.auth('87654321')
  with patch.object(self.gateway,'project',return_value=library()):
   r=await self.client.post('/playback/queue',headers=first,json={'episode_id':'s1e1','expected_revision':0,'autoplay':True});self.assertEqual(r.status,200)
   d=await r.json();self.assertEqual([e['id'] for e in d['items']],['s1e2','s2e1'])
   self.assertTrue(d['autoplay'])
   r=await self.client.get('/playback/queue',headers=second);self.assertIsNone((await r.json())['current'])
   # File-based state, not an in-memory task or prepared media session.
   self.assertEqual(len(list(self.gateway.root.glob('series-queue-*.json'))),1)
   r=await self.client.get('/playback/queue',headers=first);self.assertEqual((await r.json())['revision'],1)
   self.assertFalse(self.gateway.sessions)
 async def test_advance_conflicts_and_prunes_unavailable(self):
  h=await self.auth()
  with patch.object(self.gateway,'project',return_value=library()):
   await self.client.post('/playback/queue',headers=h,json={'episode_id':'s1e1','expected_revision':0})
  rows=library();rows[0]['episodes']=[e for e in rows[0]['episodes'] if e['id']!='s1e2']
  with patch.object(self.gateway,'project',return_value=rows):
   body={'completed_episode_id':'s1e1','expected_revision':1}
   r=await self.client.post('/playback/queue/advance',headers=h,json=body);d=await r.json()
   self.assertEqual(d['current']['id'],'s2e1');self.assertEqual(d['removed_unavailable'],1)
   self.assertEqual((await self.client.post('/playback/queue/advance',headers=h,json=body)).status,409)
 async def test_up_next_and_missing(self):
  h=await self.auth()
  with patch.object(self.gateway,'project',return_value=library()):
   r=await self.client.get('/playback/up-next',headers=h,params={'episode_id':'s1e1'})
   self.assertEqual((await r.json())['next_episode']['id'],'s1e2')
   self.assertEqual((await self.client.get('/playback/up-next',headers=h,params={'episode_id':'missing'})).status,404)
   self.assertEqual((await self.client.get('/playback/up-next',headers=h,params={'episode_id':'s1e1','limit':'0'})).status,400)
 async def test_queue_requires_revision_and_accepts_clearing(self):
  h=await self.auth()
  with patch.object(self.gateway,'project',return_value=library()):
   r=await self.client.post('/playback/queue',headers=h,json={'episode_id':'s1e1'})
   self.assertEqual(r.status,409)
   r=await self.client.post('/playback/queue',headers=h,json={'episode_id':'s1e1','expected_revision':0})
   self.assertEqual(r.status,200)
   r=await self.client.delete('/playback/queue',headers=h,json={'expected_revision':1})
   self.assertIsNone((await r.json())['current'])
   r=await self.client.post('/playback/queue',headers=h,json=[]);self.assertEqual(r.status,400)

 async def test_concurrent_queue_edits_cannot_both_win(self):
  import asyncio
  h=await self.auth()
  with patch.object(self.gateway,'project',return_value=library()):
   body={'episode_id':'s1e1','expected_revision':0}
   responses=await asyncio.gather(self.client.post('/playback/queue',headers=h,json=body),self.client.post('/playback/queue',headers=h,json=body))
   self.assertEqual(sorted(r.status for r in responses),[200,409])

 async def test_features_does_not_prepare_media(self):
  h=await self.auth();source={'id':'x','chapters':[{'title':'Opening','start':0,'end':20}]}
  self.gateway.bridge.watch=SimpleNamespace(index={'s1e1':{'sources':[(source,'Other')]}},quality=SimpleNamespace(preferred=lambda _: (source,'Other')))
  with patch.object(self.gateway,'project',return_value=library()):
   r=await self.client.get('/playback/features',headers=h,params={'episode_id':'s1e1'})
   self.assertEqual((await r.json())['chapters'][0]['end'],20)
   r=await self.client.get('/playback/features',headers=h,params={'episode_id':'s1e1','source_key':'wrong-source'})
   self.assertEqual(r.status,409)
   self.assertFalse(self.gateway.sessions)
