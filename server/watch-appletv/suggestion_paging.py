"""Bounded, device-scoped snapshots keep relevance order stable while scrolling."""
import secrets,time

class SuggestionPages:
 def __init__(self,size=24):self.size=size;self.pages={}
 def start(self,items,owner):
  now=time.time();self.pages={k:v for k,v in self.pages.items() if v['expires']>now}
  if len(self.pages)>=24:self.pages.pop(next(iter(self.pages)))
  token=secrets.token_urlsafe(24)
  self.pages[token]={'items':list(items),'owner':owner,'expires':now+3600}
  return self.read(token+'.0',owner)
 def read(self,cursor,owner):
  try:
   token,value=cursor.rsplit('.',1);offset=int(value);page=self.pages[token]
   if offset<0 or offset%self.size or page['expires']<time.time() or page['owner']!=owner:raise ValueError()
  except (ValueError,KeyError,AttributeError):raise ValueError('Suggestion list expired. Choose the genre again to refresh it.')
  page['expires']=time.time()+3600;end=offset+self.size
  return {'programmes':page['items'][offset:end],'next_cursor':token+'.'+str(end) if end<len(page['items']) else None,'total':len(page['items'])}
