import tempfile,unittest,json
from pathlib import Path
from catalogue_artwork import CatalogueArtwork,identity,poster_url
class Client:
 def __init__(self):self.calls=[]
 def match(self,title,kind):self.calls.append((title,kind));return {'id':12,'_media_type':kind,'poster_path':'/Abc123.jpg','backdrop_path':'/Scene456.jpg'}
 def logo(self,ident,kind):return None,None
class Tests(unittest.TestCase):
 def setUp(self):self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name);self.art=CatalogueArtwork(self.root,'http://host:8109')
 def tearDown(self):self.tmp.cleanup()
 def row(self,film=False):return {'id':'one','title':'Same Title','live':False,'film':film}
 def test_cache_only_response_and_movie_tv_isolation(self):
  row=self.row();self.art.enrich({'programmes':[row]});self.assertNotIn('poster',row)
  client=Client();self.art.refresh(client=client);self.assertEqual(client.calls,[('Same Title','tv')])
  self.art.enrich(row);self.assertEqual(row['poster'],'https://image.tmdb.org/t/p/w780/Abc123.jpg');self.assertEqual(row['card_artwork'],'https://image.tmdb.org/t/p/w1280/Scene456.jpg')
  movie=self.row(True);self.art.enrich(movie);self.assertNotIn('poster',movie)
  self.art.refresh(client=client);self.assertEqual(client.calls[-1],('Same Title','movie'))
 def test_live_not_queued_and_bounded_work(self):
  live={**self.row(),'live':True};self.art.enrich(live);self.assertEqual(self.art.pending,{})
  self.art.enrich([{**self.row(),'title':str(i)} for i in range(8)])
  client=Client();self.art.refresh(limit=2,client=client);self.assertEqual(len(client.calls),2)
 def test_negative_cache_does_not_invent_poster(self):
  self.art.enrich(self.row());client=Client();client.match=lambda *args:None
  self.art.refresh(client=client);row=self.row();self.art.enrich(row);self.assertNotIn('poster',row)
 def test_cached_logo_and_no_private_fields(self):
  directory=self.root/'show-logos';directory.mkdir();(directory/(identity('Same Title')+'.png')).write_bytes(b'logo')
  row=self.art.enrich(self.row());self.assertTrue(row['show_logo'].startswith('http://host:8109/static/show-logos/'));self.assertNotIn('token',json.dumps(row))
 def test_poster_path_allowlist(self):
  for path in ('https://evil/test.jpg','/../key.jpg','/x.png','/x.jpg?token=a',None):self.assertIsNone(poster_url(path))
