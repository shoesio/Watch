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
    let brands:[Brand]?;let showLogo:String?
    var displayTitle:String {
        var result=title
        if let season {
            let label=season.lowercased().hasPrefix("series ") ? season : "Series "+season
            if result.hasPrefix(label+": ") {result=String(result.dropFirst(label.count+2))}
        }
        if let episodeNumber,result.hasPrefix("\(episodeNumber). ") {result=String(result.dropFirst(String(episodeNumber).count+2))}
        return result.isEmpty ? title : result
    }
    var caption:String {[season.map {$0.lowercased().hasPrefix("series ") ? $0 : "Series \($0)"},episodeNumber.map {"Episode \($0)"},durationSeconds.flatMap {$0>0 ? "\(Int($0/60)) min" : nil}].compactMap {$0}.joined(separator:" · ")}
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
    mutating func offer(markers:[PlaybackInterval],position:Double,duration:Double,playing:Bool,hasNext:Bool,blocked:Bool,detected:PlaybackInterval?=nil)->PlaybackInterval? {
        guard playing,hasNext,!blocked,offered.isEmpty else {return nil}
        let verified=markers.filter {["credits","end_credits"].contains($0.kind) && $0.valid(duration:duration)}
        let fallback=PlaybackInterval(id:"near-end",title:"Up next",kind:"near_end",start:max(0,duration-10),end:duration)
        guard let marker=verified.first(where:{$0.contains(position)}) ?? (verified.isEmpty && detected?.valid(duration:duration)==true && detected?.contains(position)==true ? detected : nil) ?? (verified.isEmpty && duration>10 && fallback.contains(position) ? fallback : nil) else {return nil}
        offered.insert(marker.id);return marker
    }
}

// Conservative visual evidence, independent of provider chapter markers. A seek,
// gap or ordinary dialogue frame breaks the run; no single title card is enough.
struct VisualCreditsEvidence {
    private var first:Double?
    private var previous:Double?
    private var hits=0
    mutating func observe(credits:Bool,position:Double,duration:Double)->Double? {
        guard position.isFinite,duration.isFinite,duration>60,
              position>=max(duration*0.8,duration-120),position<duration-10 else {reset();return nil}
        if let previous,position<=previous || position-previous>5 {reset()}
        previous=position
        guard credits else {first=nil;hits=0;return nil}
        if first == nil {first=position}
        hits+=1
        return hits>=3 && position-first!>=5 ? first : nil
    }
    mutating func reset() {first=nil;previous=nil;hits=0}
}

// Ahead-of-time scans can backdate a confirmed cue, so the visible player does
// not have to wait for OCR confirmation. Music never triggers without text.
struct EndingScanEvidence {
    static func backdated(textStart:Double,music:[(Double,Double)])->Double {
        var runs:[(Double,Double)]=[]
        for interval in music.sorted(by:{$0.0<$1.0}) where interval.0.isFinite && interval.1.isFinite && interval.1>interval.0 {
            if let last=runs.last,interval.0<=last.1+1 {runs[runs.count-1].1=max(last.1,interval.1)}
            else {runs.append(interval)}
        }
        return runs.last(where:{$0.1-$0.0>=6 && $0.0>=textStart-20 && $0.0<=textStart && $0.1>=textStart})?.0 ?? textStart
    }
    private var first:Double?
    private var previous:Double?
    private var hits=0
    mutating func reset() {first=nil;previous=nil;hits=0}
    mutating func observe(position:Double,strongText:Bool,weakText:Bool,music:Bool)->Double? {
        guard position.isFinite else {reset();return nil}
        if let previous,position<=previous || position-previous>3 {reset()}
        previous=position
        guard strongText || (weakText && music) else {first=nil;hits=0;return nil}
        if first == nil {first=position}
        hits+=1
        return hits>=2 ? first : nil
    }
}
