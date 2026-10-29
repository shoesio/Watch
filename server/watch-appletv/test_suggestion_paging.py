import unittest,time
from suggestion_paging import SuggestionPages
from recommendations import featured_films

class PagingTests(unittest.TestCase):
 def test_pages_are_stable_complete_and_do_not_repeat(self):
  p=SuggestionPages(size=4);items=[{'id':str(i)} for i in range(11)]
  first=p.start(items,'device');items.reverse()
  second=p.read(first['next_cursor'],'device');third=p.read(second['next_cursor'],'device')
  self.assertEqual([x['id'] for row in [first,second,third] for x in row['programmes']],[str(i) for i in range(11)])
  self.assertIsNone(third['next_cursor']);self.assertEqual(third['total'],11)
 def test_owner_and_cursor_validation(self):
  p=SuggestionPages(size=2);first=p.start([{}, {}, {}],'one');cursor=first['next_cursor']
  for value,owner in [(cursor,'two'),('bad','one'),(cursor.rsplit('.',1)[0]+'.-2','one'),(cursor.rsplit('.',1)[0]+'.1','one')]:
   with self.subTest(value=value,owner=owner):
    with self.assertRaises(ValueError):p.read(value,owner)
 def test_empty_list_has_no_next_page(self):
  self.assertIsNone(SuggestionPages().start([],'device')['next_cursor'])
 def test_expired_cursor(self):
  p=SuggestionPages(size=1);first=p.start([{},{}],'one');token=first['next_cursor'].split('.')[0];p.pages[token]['expires']=0
  with self.assertRaises(ValueError):p.read(first['next_cursor'],'one')
 def test_featured_films_are_daily_varied_real_films(self):
  films=[{'id':str(i),'title':'Film '+str(i),'film':True,'genres':['Comedy' if i%2 else 'Drama'],'episodes':[{'duration_seconds':6000}],'hero':'image','brands':[{'id':'bbc' if i%3 else 'c4'}]} for i in range(20)]
  films += [{'id':'short','title':'Short','film':True,'episodes':[{'duration_seconds':120}],'hero':'image'}, {'id':'seen','title':'Seen','film':True,'recent':True,'episodes':[{'duration_seconds':6000}],'hero':'image'}]
  a=featured_films(films,day='2026-10-29');b=featured_films(films,day='2026-10-30')
  self.assertEqual(len(a),6);self.assertEqual(len({p['id'] for p in a}),6)
  self.assertEqual(a,featured_films(films,day='2026-10-29'));self.assertNotEqual(a,b)
  self.assertFalse(any(p['id'] in ('seen','short') for p in a))

if __name__=='__main__':unittest.main()
