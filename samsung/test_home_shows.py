import tempfile,time,unittest
from pathlib import Path
from episode_freshness import EpisodeFreshness,timestamp,released
from recommendations import home_shows

NOW=time.time()
def programme(n,**kwargs):
 row=dict(id=str(n),title='Show '+str(n),favourite=True,hero='art',genres=['Comedy'],episodes=kwargs.pop('episodes',[]));row.update(kwargs);return row
def episode(n,**kwargs):return dict(id=str(n),title='Episode '+str(n),season=1,episode_number=n,**kwargs)

class HomeShows(unittest.TestCase):
 def test_most_recent_unfinished_ignores_newer_favourite_actions_and_completed(self):
  a=programme(1,episodes=[episode(1,position=100,progress=20,updated_at=NOW-50)])
  b=programme(2,favourite_at=NOW,episodes=[episode(2,position=200,progress=30,updated_at=NOW-10)])
  done=programme(3,episodes=[episode(3,position=900,progress=98,updated_at=NOW)])
  rows=home_shows([a,done,b]);self.assertEqual(rows[0]['id'],'2');self.assertEqual(rows[0]['home_episode'],'2');self.assertEqual(rows[0]['home_reason'],'Continue watching')
 def test_recent_release_follows_resume_and_targets_actual_unwatched_episode(self):
  resume=programme(1,episodes=[episode(1,position=200,progress=20,updated_at=NOW-100)])
  old=programme(2,episodes=[episode(2,available_at=NOW-3000)])
  new=programme(3,episodes=[episode(3,available_at=NOW-1000,completed=True),episode(4,available_at=NOW-1500,thumbnail='episode-still')])
  rows=home_shows([old,new,resume]);self.assertEqual([p['id'] for p in rows],['1','3','2']);self.assertEqual(rows[1]['episode_id'],'4');self.assertEqual(rows[1]['image'],'episode-still')
 def test_sync_and_import_times_do_not_make_old_catalogue_new(self):
  a=programme(1,episodes=[episode(1,broadcast_at=NOW-3000)],added_at=NOW)
  b=programme(2,episodes=[episode(2,broadcast_at=NOW-1000)])
  self.assertEqual(home_shows([a,b])[0]['id'],'2')
 def test_unwatched_source_selection_is_unique_familiar_and_not_a_film_or_live(self):
  watched=programme(1,episodes=[episode(1)])
  stranger=programme(2,favourite=False,episodes=[episode(2,available_at=NOW-1)])
  movie=programme(3,film=True,episodes=[episode(3)])
  live=programme(4,live=True,episodes=[episode(4)])
  self.assertEqual([p['id'] for p in home_shows([watched,stranger,movie,live])],['1'])
 def test_unknown_duration_can_resume_using_saved_position(self):
  p=programme(1,episodes=[episode(1,position=120,updated_at=NOW,progress=0)])
  self.assertEqual(home_shows([p])[0]['home_reason'],'Continue watching')
 def test_initial_import_not_new_later_episode_observed_and_dates_survive_sync(self):
  with tempfile.TemporaryDirectory() as root:
   store=EpisodeFreshness(Path(root)/'seen.json')
   first=store.enrich([programme(1,episodes=[episode(1,broadcast_at=NOW-5000)])],now=NOW-2000)
   self.assertEqual(first[0]['episodes'][0]['first_seen_at'],0)
   store=EpisodeFreshness(Path(root)/'seen.json')
   second=store.enrich([programme(1,episodes=[episode(1),episode(2)])],now=NOW-1000)
   self.assertEqual(second[0]['episodes'][0]['broadcast_at'],NOW-5000)
   self.assertEqual(second[0]['episodes'][1]['first_seen_at'],NOW-1000)
   third=store.enrich([programme(1,episodes=[episode(1),episode(2)])],now=NOW)
   self.assertEqual(third[0]['episodes'][1]['first_seen_at'],NOW-1000)
 def test_dates_accept_iso_epoch_and_milliseconds_but_not_future_or_invalid(self):
  self.assertEqual(timestamp('2026-10-29T20:00:00Z',NOW),1793304000)
  self.assertEqual(timestamp(1793304000000,NOW),1793304000)
  self.assertEqual(released({'broadcast_at':NOW+500,'available_at':NOW-50},NOW),NOW-50)
  for bad in ('garbage',None,float('nan')):self.assertEqual(timestamp(bad,NOW),0)


import test_server
class HomeGateway(unittest.IsolatedAsyncioTestCase):
 asyncSetUp=test_server.GatewayTests.asyncSetUp
 asyncTearDown=test_server.GatewayTests.asyncTearDown
 async def test_home_and_highlights_share_order_and_do_not_expose_source_credentials(self):
  self.gateway.progress.save('c4_ep',120,1000)
  p=next(p for p in self.bridge.catalogue['programmes'] if p['id']=='bleeped')
  p['episodes'][0].update(available_at=NOW-1000,duration_seconds=1000)
  rows=(await (await self.client.get('/api/library?tab=0&size=4',headers=self.headers)).json())['items']
  highlights=(await (await self.client.get('/api/suggestions?mode=highlights&size=8',headers=self.headers)).json())['items']
  self.assertNotIn('episodes',rows[0]);self.assertEqual(rows[0]['home_episode'],'c4_ep');self.assertEqual(rows[1]['home_episode'],'bleeped_ep')
  self.assertEqual([p['home_episode'] for p in rows],[p['home_episode'] for p in highlights])
  import json
  self.assertNotIn('SECRET',json.dumps(rows));self.assertNotIn('private.invalid',json.dumps(rows))

if __name__=='__main__':unittest.main()
