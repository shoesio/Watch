import Foundation

struct PlaybackCapabilities:Decodable {let schemaVersion:Int;let chapters:Bool;let skipMarkers:[String];let seriesQueue:Bool}
struct PlaybackInterval:Decodable,Identifiable,Equatable {
    let id:String;let title:String;let kind:String;let start:Double;let end:Double
    func valid(duration:Double)->Bool {start.isFinite && end.isFinite && start>=0 && end>start && end<=86400 && (duration<=0 || end<=duration+0.5)}
    func contains(_ position:Double)->Bool {position.isFinite && start<=position && position<end}
}
struct EpisodeFeatures:Decodable {
    let schemaVersion:Int;let episodeId:String;let sourceKey:String;let versionId:String?;let timebase:String;let status:String
    let chapters:[PlaybackInterval];let skipMarkers:[PlaybackInterval]
    func matches(episode:String,source:String,version:String?)->Bool {
        schemaVersion==1 && episodeId==episode && sourceKey==source && versionId==version && timebase=="episode" && status=="available"
    }
}
struct NextEpisode:Decodable,Identifiable {
    let id:String;let title:String;let programmeId:String?;let showTitle:String?;let description:String?;let thumbnail:String?;let artwork:String?
    let season:String?;let episodeNumber:Int?;let durationSeconds:Double?;let available:Bool?
    var caption:String {[season.map {"Series \($0)"},episodeNumber.map {"Episode \($0)"},durationSeconds.flatMap {$0>0 ? "\(Int($0/60)) min" : nil}].compactMap {$0}.joined(separator:" · ")}
}
struct NextEpisodes:Decodable {let schemaVersion:Int;let episodeId:String;let nextEpisode:NextEpisode?;let items:[NextEpisode]}
struct SeriesQueue:Decodable {
    let schemaVersion:Int;let revision:Int;let autoplay:Bool;let current:NextEpisode?;let items:[NextEpisode]
    func successor(of episode:String)->NextEpisode? {current?.id==episode ? items.first(where:{$0.available != false}) : nil}
}
// One terminal event per actual episode. Seek-to-end and short/disconnected
// relay windows must not count as natural completion or start another stream.
struct EpisodeCompletionGate {
    private(set) var completed=false
    private var seekPosition:Double?
    mutating func reset() {completed=false;seekPosition=nil}
    mutating func sought(to position:Double) {seekPosition=position}
    mutating func played(at position:Double) {if let start=seekPosition,position>start+1 {seekPosition=nil}}
    mutating func accept(position:Double,duration:Double,live:Bool,failed:Bool)->Bool {
        guard !completed,!live,!failed,seekPosition == nil,position.isFinite,duration.isFinite,duration>0,position>=duration-1.5 else {return false}
        completed=true;return true
    }
}

// Verified credits retain their source timing. The near-end fallback is explicitly
// labelled separately and never used as a skip/credits marker.
struct CreditsCueState {
    private var offered=Set<String>()
    mutating func reset() {offered=[]}
    mutating func offer(markers:[PlaybackInterval],position:Double,duration:Double,playing:Bool,hasNext:Bool,blocked:Bool)->PlaybackInterval? {
        guard playing,hasNext,!blocked,offered.isEmpty else {return nil}
        let verified=markers.filter {["credits","end_credits"].contains($0.kind) && $0.valid(duration:duration)}
        let fallback=PlaybackInterval(id:"near-end",title:"Up next",kind:"near_end",start:max(0,duration-10),end:duration)
        guard let marker=verified.first(where:{$0.contains(position)}) ?? (verified.isEmpty && duration>10 && fallback.contains(position) ? fallback : nil) else {return nil}
        offered.insert(marker.id);return marker
    }
}
