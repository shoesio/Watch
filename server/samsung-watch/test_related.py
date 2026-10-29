import tempfile,unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from related import RelatedShows,relation_candidates

class RelatedTests(unittest.TestCase):
 def test_verified_shared_cast_ranks_before_generic_similarity(self):
  seed={'id':1,'recommendations':{'results':[{'id':3,'name':'Generic'}]},'similar':{'results':[{'id':1,'name':'Original'}]}}
  rows=relation_candidates(seed,{},[({'name':'Actor'},{'cast':[{'id':2,'name':'Shared cast show','episode_count':12}]})],[],[])
  self.assertEqual(rows[0]['title'],'Shared cast show');self.assertIn('Shared cast: Actor',rows[0]['relations'])
  self.assertFalse(any(p['id']==1 for p in rows))
 def test_one_episode_guest_does_not_outrank_regular(self):
  rows=relation_candidates({'id':1},{},[({'name':'Actor'},{'cast':[{'id':2,'name':'Guest','episode_count':1},{'id':3,'name':'Regular','episode_count':20}]})],[],[])
  self.assertEqual(rows[0]['title'],'Regular')
 def test_creator_credit_requires_a_relevant_job(self):
  rows=relation_candidates({'id':1},{},[],[({'name':'Creator'},{'crew':[{'id':2,'name':'Created show','job':'Creator'},{'id':3,'name':'Unrelated','job':'Thanks'}]})],[])
  self.assertEqual([p['title'] for p in rows],['Created show'])
 def test_unavailable_or_wrong_title_not_returned(self):
  with tempfile.TemporaryDirectory() as folder:
   discovery=SimpleNamespace(suggestions=[],c4=[],genre_candidates=lambda g:[],search=lambda title:{'programmes':[{'id':'wrong','title':'Wrong title','film':False}]})
   service=RelatedShows(folder,folder,discovery)
   programme={'id':'original','title':'Original','genres':['Comedy']}
   with patch.object(service,'relationships',return_value=[{'title':'Missing','score':50,'relations':{'Shared cast'}}]):rows=service.list(programme,[programme])
   self.assertEqual(rows,[])
 def test_cached_related_list_keeps_descriptions_and_excludes_original(self):
  with tempfile.TemporaryDirectory() as folder:
   show={'id':'other','title':'Other','genres':['Comedy'],'description':'The actual synopsis','brands':[]}
   discovery=SimpleNamespace(suggestions=[],c4=[],genre_candidates=lambda g:[show])
   service=RelatedShows(folder,folder,discovery)
   original={'id':'original','title':'Original','genres':['Comedy']}
   with patch.object(service,'relationships',return_value=[]):
    rows=service.list(original,[original]);self.assertEqual(rows[0]['description'],'The actual synopsis')
    self.assertEqual(rows,service.list(original,[original]))

if __name__=='__main__':unittest.main()
