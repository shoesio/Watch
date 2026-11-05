import Foundation
@main struct Checks {
 static func main() throws {
  var gate=EpisodeCompletionGate()
  precondition(!gate.accept(position:40,duration:120,live:false,failed:false),"A short relay window completed an episode")
  precondition(!gate.accept(position:120,duration:120,live:true,failed:false))
  precondition(!gate.accept(position:120,duration:120,live:false,failed:true))
  gate.sought(to:120)
  precondition(!gate.accept(position:120,duration:120,live:false,failed:false),"Seek to end autoplayed")
  gate.reset();gate.sought(to:30);gate.played(at:31.5)
  precondition(gate.accept(position:119.5,duration:120,live:false,failed:false))
  precondition(!gate.accept(position:120,duration:120,live:false,failed:false),"Duplicate end advanced twice")
  let marker=PlaybackInterval(id:"intro",title:"Intro",kind:"intro",start:10,end:40)
  precondition(marker.valid(duration:120) && marker.contains(10) && !marker.contains(40) && !marker.contains(.nan))
  precondition(!PlaybackInterval(id:"bad",title:"Bad",kind:"intro",start:0,end:.infinity).valid(duration:120))
  precondition(!marker.valid(duration:30))
  // A relay beginning at 25 seconds must seek intro-end to relative 15,
  // preserving the caller's paused/playing intent in PlaybackModel.jump.
  precondition(marker.end-25==15)
  let json="""
  {"schema_version":1,"episode_id":"ep/1#cut","source_key":"source-a","version_id":"v1234567","timebase":"episode","status":"available","chapters":[],"skip_markers":[{"id":"intro","title":"Intro","kind":"intro","start":10,"end":40}]}
  """
  let extras=try JSONDecoder.watch.decode(EpisodeFeatures.self,from:Data(json.utf8))
  precondition(extras.matches(episode:"ep/1#cut",source:"source-a",version:"v1234567"))
  precondition(!extras.matches(episode:"new",source:"source-a",version:"v1234567"),"Stale episode accepted")
  precondition(!extras.matches(episode:"ep/1#cut",source:"source-b",version:"v1234567"),"Different provider source accepted")
  precondition(!extras.matches(episode:"ep/1#cut",source:"source-a",version:nil),"Unknown version accepted")
  let queueJSON="""
  {"schema_version":1,"revision":3,"autoplay":true,"current":{"id":"ep1","title":"First","available":true},"items":[{"id":"gone","title":"Expired","available":false},{"id":"ep2","title":"Second","available":true}]}
  """
  let queue=try JSONDecoder.watch.decode(SeriesQueue.self,from:Data(queueJSON.utf8))
  precondition(queue.successor(of:"ep1")?.id=="ep2")
  precondition(queue.successor(of:"different")==nil)
  let final=SeriesQueue(schemaVersion:1,revision:4,autoplay:true,current:queue.items.last,items:[])
  precondition(final.successor(of:"ep2")==nil,"Final episode invented a successor")
  var credits=CreditsCueState()
  let cue=PlaybackInterval(id:"credits",title:"Credits",kind:"credits",start:100,end:120)
  let fake=PlaybackInterval(id:"fake",title:"Credits",kind:"chapter",start:100,end:120)
  precondition(credits.offer(markers:[fake],position:105,duration:120,playing:true,hasNext:true,blocked:false)==nil,"A title was mistaken for a marker")
  precondition(credits.offer(markers:[cue],position:99,duration:120,playing:true,hasNext:true,blocked:false)==nil)
  precondition(credits.offer(markers:[cue],position:105,duration:120,playing:false,hasNext:true,blocked:false)==nil)
  precondition(credits.offer(markers:[cue],position:105,duration:120,playing:true,hasNext:false,blocked:false)==nil)
  precondition(credits.offer(markers:[cue],position:105,duration:120,playing:true,hasNext:true,blocked:true)==nil)
  precondition(credits.offer(markers:[cue],position:105,duration:120,playing:true,hasNext:true,blocked:false)==cue)
  precondition(credits.offer(markers:[cue],position:106,duration:120,playing:true,hasNext:true,blocked:false)==nil,"Dismissed card reappeared")
  credits.reset()
  precondition(credits.offer(markers:[cue],position:120,duration:120,playing:true,hasNext:true,blocked:false)==nil)
  precondition(credits.offer(markers:[cue],position:105,duration:120,playing:true,hasNext:true,blocked:false)==cue)
  credits.reset()
  precondition(credits.offer(markers:[],position:109.9,duration:120,playing:true,hasNext:true,blocked:false)==nil)
  let fallback=credits.offer(markers:[],position:110,duration:120,playing:true,hasNext:true,blocked:false)
  precondition(fallback?.kind=="near_end" && fallback?.start==110)
  precondition(credits.offer(markers:[],position:111,duration:120,playing:true,hasNext:true,blocked:false)==nil)
  credits.reset()
  precondition(credits.offer(markers:[],position:120,duration:120,playing:true,hasNext:true,blocked:false)==nil)
  precondition(credits.offer(markers:[],position:115,duration:120,playing:false,hasNext:true,blocked:false)==nil)
  precondition(credits.offer(markers:[],position:115,duration:120,playing:true,hasNext:true,blocked:true)==nil)
  print("Playback extras checks passed: timing/source/version validation, stale metadata, completion guards, duplicate ends, expired/final queue entries, DTO decoding and credits-cue guards")
 }
}
