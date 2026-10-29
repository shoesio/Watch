import time,unittest
from unittest.mock import patch
from types import SimpleNamespace
import test_server
from recommendations import recommend,personal_shows,featured_shows,genre_order,diverse_rank,ranked_films

def show(n,provider='bbc',**kw):
 return {'id':f'{n:020x}','title':f'Show {n}','genres':['Comedy'],'brands':[{'id':provider,'name':provider}], 'episodes':[],**kw}

class PersonalRanking(unittest.TestCase):
 def test_recent_16_use_actual_actions_not_alphabetical_or_import_time(self):
  library=[show(i,title=f'Programme {30-i}',recent=True,episodes=[{'updated_at':i+1}]) for i in range(20)]
  library.append(show(30,title='AAA newly indexed',added_at=time.time()))
  rows=personal_shows(library)
  self.assertEqual(len(rows),16);self.assertEqual([p['id'] for p in rows],[show(i)['id'] for i in range(19,3,-1)])
 def test_new_local_favourite_precedes_old_play_and_unknown_provider_dates(self):
  rows=personal_shows([show(1,favourite=True),show(2,recent=True,episodes=[{'updated_at':10}]),show(3,favourite=True,favourite_at=20)])
  self.assertEqual([p['id'] for p in rows],[show(3)['id'],show(2)['id'],show(1)['id']])
 def test_genre_personal_has_no_films_or_wrong_genres(self):
  rows=personal_shows([show(1,favourite=True),show(2,favourite=True,genres=['Drama']),show(3,favourite=True,film=True)],genre='Comedy')
  self.assertEqual([p['id'] for p in rows],[show(1)['id']])
 def test_comedy_documentaries_do_not_replace_panel_and_sitcom_taste(self):
  seeds=[show(100,title='Taskmaster',description='A comedy panel quiz',favourite=True),show(101,title='A Sitcom',description='A sitcom',favourite=True)]
  candidates=[show(i,'channel5',title=f'Comedy Legends {i}',description='A documentary about the life of a comedian',genres=['Comedy','Documentaries','Entertainment','Documentary','More Entertainment']) for i in range(12)]
  candidates += [show(30+i,'bbc',title=f'New Panel {i}',description='A panel quiz') for i in range(4)]
  candidates += [show(40+i,'channel4',title=f'New Sitcom {i}',description='A sitcom') for i in range(4)]
  result=recommend(seeds,candidates,12,provider_cap=None)
  self.assertNotEqual(result[0]['brands'][0]['id'],'channel5')
  self.assertLessEqual(sum(p['brands'][0]['id']=='channel5' for p in result[:8]),3)
 def test_unrequested_signed_alternate_does_not_repeat_a_known_show(self):
  seed=show(1,title='Taskmaster',favourite=True)
  result=recommend([seed],[show(2,title='Taskmaster (Signed)')],include_known=True)
  self.assertEqual(result,[])
 def test_ready_library_metadata_wins_over_duplicate_discovery_preview(self):
  original=show(1,title='A Show',episodes=[{'id':'episode'}])
  preview=show(2,title='A Show',discovery_ref='bbc:new')
  result=diverse_rank([(1,original),(2,preview)],24,None)
  self.assertEqual(len(result),1);self.assertEqual(result[0]['id'],original['id'])
 def test_diversity_retains_all_later_provider_titles(self):
  pool=[(1,show(i,'channel5')) for i in range(30)]+[(0.98,show(100+i,'bbc')) for i in range(5)]
  result=diverse_rank(pool,100,None)
  self.assertEqual(len(result),35);self.assertIn('bbc',[p['brands'][0]['id'] for p in result[:8]])
 def test_genres_follow_taste_and_exist_in_library(self):
  library=[show(1,favourite=True,genres=['Comedy']),show(2,genres=['Drama']),show(3,genres=['Horror'])]
  self.assertEqual(genre_order(library)[0],'Comedy');self.assertEqual(set(genre_order(library)),{'Comedy','Drama','Horror'})
 def test_featured_shows_are_six_unique_ready_shows(self):
  library=[show(i,'bbc' if i%2 else 'u',favourite=True,hero='image',episodes=[{'id':str(i),'updated_at':i}]) for i in range(12)]
  library += [show(99,film=True,hero='film',episodes=[{}])]
  result=featured_shows(library)
  self.assertEqual(len(result),6);self.assertEqual(len({p['id'] for p in result}),6);self.assertTrue(all(p['episodes'] and not p.get('film') for p in result))

class FilmRanking(unittest.TestCase):
 def test_taste_beats_alphabetical_and_genre_filter_keeps_order(self):
  seed=show(100,title='Favourite comedy',favourite=True)
  films=[show(1,title='A horror',film=True,genres=['Horror']),show(2,title='Z comedy',film=True),show(3,title='Another comedy',film=True)]
  rows=ranked_films([seed]+films)
  self.assertIn(rows[0]['id'],{show(2)['id'],show(3)['id']})
  self.assertEqual(rows[-1]['id'],show(1)['id'])
  self.assertEqual([p['id'] for p in rows if 'Comedy' in p['genres']], [p['id'] for p in rows[:2]])
 def test_out_of_season_christmas_does_not_dominate_comedy_films(self):
  with patch('recommendations.time.gmtime',return_value=time.struct_time((2026,10,29,0,0,0,0,0,0))):
   films=[show(1,title='A Christmas Comedy',film=True),show(2,title='Another Comedy',film=True)]
   self.assertEqual(ranked_films([show(100,favourite=True)]+films)[0]['id'],show(2)['id'])
 def test_all_films_retained_including_family_and_alternate_editions(self):
  films=[show(1,title='One',film=True,favourite=True),show(2,title='One (Signed)',film=True),show(3,title='Kids',film=True,genres=['Children'])]
  self.assertEqual({p['id'] for p in ranked_films(films)},{p['id'] for p in films})
 def test_resume_first_completed_last_and_stable(self):
  films=[show(1,film=True,episodes=[{'progress':98}]),show(2,film=True),show(3,film=True,resume_episode='e3',episodes=[{'id':'e3','updated_at':10,'progress':40}])]
  rows=ranked_films(films)
  self.assertEqual([p['id'] for p in rows],[show(3)['id'],show(2)['id'],show(1)['id']])
  self.assertEqual(rows,ranked_films(films))

class ShowsAPI(unittest.IsolatedAsyncioTestCase):
 asyncSetUp=test_server.Tests.asyncSetUp
 asyncTearDown=test_server.Tests.asyncTearDown
 idle=test_server.Tests.idle
 async def test_shows_require_pairing(self):
  response=await self.client.get('/shows');self.assertEqual(response.status,401)
 async def test_personal_and_relevance_pages_do_not_overlap(self):
  token=await test_server.Tests.pair(self);headers={'Authorization':'Bearer '+token}
  library=[show(i,favourite=True,episodes=[{'updated_at':100-i}]) for i in range(20)]
  candidates=[show(i,'channel5' if i%2 else 'bbc') for i in range(20,80)]
  self.gateway.discovery=SimpleNamespace(recommendation_candidates=lambda lib:candidates)
  with patch.object(self.gateway,'project',return_value=library):
   response=await self.client.get('/shows',headers=headers);self.assertEqual(response.status,200);first=await response.json()
  self.assertEqual(len(first['personal']),16);self.assertEqual(len(first['programmes']),24)
  self.assertFalse({p['id'] for p in first['personal']} & {p['id'] for p in first['programmes']})
  response=await self.client.get('/shows',params={'cursor':first['next_cursor']},headers=headers);second=await response.json()
  self.assertFalse({p['id'] for p in first['programmes']} & {p['id'] for p in second['programmes']})
