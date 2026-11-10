import Foundation
import CryptoKit

struct Library: Decodable { let programmes: [Programme] }
struct Brand: Decodable, Identifiable { let id: String; let name: String; let image: String }
struct Broadcast: Decodable { let title: String?; let subtitle: String?; let image: String?; let start: Double?; let end: Double?; let time: String? }
struct Guide: Decodable { let now: Broadcast?; let next: Broadcast? }
struct Programme: Decodable, Identifiable {
    let id: String
    let title: String
    let description: String?
    let artwork: String?
    let hero: String?
    let poster:String?
    let cardArtwork:String?
    let archiveYear:Int?
    let showLogo: String?
    let channelLogo: String?
    let live: Bool
    let uhdAvailable:Bool?
    let film: Bool
    let filmRank:Int?
    let recent: Bool
    let favourite: Bool
    let favouriteAt:Double?
    let genres: [String]
    let brands: [Brand]
    let episodes: [Episode]
    let resumeEpisode: String?
    let discoveryRef:String?
    let recommendationReason:String?
    let contentRating:String?
    let ratingSource:String?
    let guide: Guide?
    var editionLabel:String? {
        let name=title.lowercased()
        if name == "qi xl" {return "QI XL · Extended"}
        if name.contains("bleeped") {return "Bleeped"}
        if name.contains("a bit more news") {return "Extended edition"}
        if name.contains("taskmaster") {
            if name.contains("new zealand") {return "New Zealand"}
            if name.contains("australia") {return "Australia"}
            if name.contains("champion of champions") {return "Champion of Champions"}
            if name.contains("new year") {return "New Year Treat"}
            if name.contains("junior") {return "Junior Taskmaster"}
        }
        return nil
    }
    // Discovery previews can reuse a clear logo already cached for the same
    // title without waiting for the programme to be imported into the library.
    var logoSource:String? {
        if let showLogo,!showLogo.isEmpty {return showLogo}
        guard !live,let brand=brands.first,let url=URL(string:brand.image),
              ["http","https"].contains(url.scheme),url.path.contains("/static/artwork/brands/"),
              var parts=URLComponents(url:url,resolvingAgainstBaseURL:false) else {return nil}
        let key=title.lowercased().replacingOccurrences(of:"’",with:"'").replacingOccurrences(of:"[^\\w]+",with:" ",options:.regularExpression).trimmingCharacters(in:.whitespacesAndNewlines)
        let hash=SHA256.hash(data:Data(key.utf8)).map{String(format:"%02x",$0)}.joined().prefix(20)
        parts.path="/static/show-logos/\(hash).png";parts.query=nil;parts.fragment=nil
        return parts.url?.absoluteString
    }
    // A new-episode badge needs an explicitly later numbered edition than the
    // last watched episode. Unknown seasons/specials are never guessed as new.
    var hasNewEpisode:Bool {
        guard !film,!live,let watched=episodes.filter({($0.updatedAt ?? 0)>0}).max(by:{($0.updatedAt ?? 0)<($1.updatedAt ?? 0)}),
              let oldSeason=watched.seasonNumber,let oldNumber=watched.episodeNumber else {return false}
        return episodes.contains {episode in
            guard (episode.updatedAt ?? 0)==0,(episode.resumeSeconds ?? 0)==0,let season=episode.seasonNumber,let number=episode.episodeNumber else {return false}
            return season>oldSeason || (season==oldSeason && number>oldNumber)
        }
    }
    var resume: Episode? { episodes.first { $0.id == resumeEpisode } }
    var preferred: Episode? { resume ?? episodes.first }
    var latestProgress: Double { episodes.map { $0.updatedAt ?? 0 }.max() ?? 0 }
}
struct Episode: Decodable, Identifiable {
    let id: String
    let title: String
    let subtitle: String?
    let description: String?
    let thumbnail: String?
    let season: String?
    let episodeNumber: Int?
    let durationSeconds: Double?
    let resumeSeconds: Double?
    let updatedAt: Double?
    let progress: Double?
    let quality: String?
    let uhdAvailable:Bool?
    let brands: [Brand]
    var seasonNumber:Int? {
        guard let value=season?.trimmingCharacters(in:.whitespacesAndNewlines),
              let range=value.range(of:"^(?:(?:series|season|s)\\s*)?[0-9]+$",options:[.regularExpression,.caseInsensitive]) else {return nil}
        return Int(value[range].filter(\.isNumber))
    }
    var seasonTitle: String {
        guard let season, !season.isEmpty else { return "Episodes" }
        return Int(season) != nil ? "Series \(season)" : season
    }
    var caption: String {
        [episodeNumber.map { "Episode \($0)" }, durationSeconds.flatMap { $0 > 0 ? "\(Int($0 / 60)) min" : nil }, uhdAvailable == true ? "UHD" : quality].compactMap { $0 }.joined(separator: " · ")
    }
}
struct PlaybackMetadata: Decodable {
    let id: String
    let title: String
    let description: String?
    let showTitle: String?
    let showLogo: String?
    let brands: [Brand]?
    let durationSeconds: Double?
    let startPosition: Double?
    let live: Bool
    let quality: String?
    let streamWidth: Double?
    let streamHeight: Double?
    let artwork:String?
    let channelLogo:String?
    let sourceKey:String?
    var versionId:String?
}
struct Prepared: Decodable {
    let state: String
    let job: String?
    let ticket: String?
    let url: String?
    let metadata: PlaybackMetadata?
    let native: NativePlayback?
    let initialSeek: Double?
    let error: String?
}
struct PairResponse: Decodable { let token: String }
struct APIError: Decodable { let error: String }
struct WatchHTTPError:LocalizedError {let status:Int;let message:String;var errorDescription:String? {message}}
struct WatchError: LocalizedError { let message: String; var errorDescription: String? { message } }

extension JSONDecoder {
    static var watch: JSONDecoder { let decoder = JSONDecoder(); decoder.keyDecodingStrategy = .convertFromSnakeCase; return decoder }
}

// Encoded video dimensions, never the television's output/display resolution.
enum StreamQuality {
    static func label(width:Double,height:Double) -> String? {
        guard width.isFinite, height.isFinite, width>0 || height>0 else { return nil }
        if width>=3840 || height>=2160 { return "UHD" }
        if width>=1280 || height>=720 { return "HD" }
        return "SD"
    }
}

extension Episode {
    var durationText:String? { durationSeconds.flatMap { $0>0 ? "\(Int($0/60)) min" : nil } }
    var remainingLabel:String {
        guard let duration=durationSeconds, duration>0, let resume=resumeSeconds, resume>0 else { return "Continue watching" }
        return "\(max(1,Int(ceil((duration-resume)/60)))) min remaining"
    }
    func cardHeading(showSeries:Bool)->String {
        var name=title.trimmingCharacters(in:.whitespacesAndNewlines)
        let series=seasonTitle
        if name.hasPrefix(series+": ") {name=String(name.dropFirst(series.count+2))}
        let heading=episodeNumber.flatMap {$0>0 ? "Episode \($0)" : nil} ?? name
        return showSeries && series != "Episodes" ? series+": "+heading : heading
    }
    var cardDetails:String {
        [durationSeconds.flatMap {$0>0 ? "\(Int($0/60)) Min" : nil},uhdAvailable == true ? "UHD" : quality].compactMap{$0}.joined(separator:" • ")
    }
    var compactCaption:String {
        [episodeNumber.map { "Episode \($0)" },durationText,uhdAvailable == true ? "UHD" : quality].compactMap { $0 }.joined(separator:" · ")
    }
}
extension Programme {
    var episodeCountLabel:String { "\(episodes.count) episode\(episodes.count == 1 ? "" : "s")" }
}

// Full-episode seek math is independent of the rolling HLS window.
enum EpisodeTimeline {
    static func clamp(_ position:Double,duration:Double) -> Double {
        guard position.isFinite,duration.isFinite,duration>0 else { return 0 }
        return min(max(0,position),max(0,duration-1))
    }
    static func step(repeats:Int) -> Double { repeats>=12 ? 120 : (repeats>=7 ? 60 : (repeats>=3 ? 30 : 10)) }
    static func time(_ seconds:Double) -> String {
        let value=Int(max(0,seconds.isFinite ? seconds : 0))
        return value>=3600 ? String(format:"%d:%02d:%02d",value/3600,(value/60)%60,value%60) : String(format:"%d:%02d",value/60,value%60)
    }
}

struct DiscoveryResponse:Decodable {
    let programmes:[Programme]
    let hot:[Programme]?
    let status:[String:String]?
    let featuredFilms:[Programme]?
    let featuredShows:[Programme]?
    let nextCursor:String?
    let total:Int?
}

struct NativePlayback: Decodable { let provider:String; let id:String; let live:Bool;let playlistUrl:String?;let premium:Bool? }

struct ShowsResponse:Decodable {
    let programmes:[Programme]
    let personal:[Programme]?
    let genres:[String]?
    let nextCursor:String?
    let total:Int?
}

// Preserve editorial order on ties rather than silently using the title. This
// also gives favourites without watch history their actual favourite date.
enum BrowseOrdering {
    static func personal(_ programmes:[Programme],recommended:[Programme])->[Programme] {
        let ranks=Dictionary(recommended.enumerated().map{($0.element.id,$0.offset)},uniquingKeysWith:min)
        return programmes.enumerated().sorted {left,right in
            let a=left.element,b=right.element
            let aDate=max(a.latestProgress,a.favouriteAt ?? 0),bDate=max(b.latestProgress,b.favouriteAt ?? 0)
            if aDate != bDate {return aDate>bDate}
            if a.recent != b.recent {return a.recent}
            if a.favourite != b.favourite {return a.favourite}
            let ar=ranks[a.id] ?? Int.max,br=ranks[b.id] ?? Int.max
            return ar != br ? ar<br : left.offset<right.offset
        }.map(\.element)
    }
}

struct EditorialShelf:Identifiable {
    enum Layout {case landscape,portrait,feature}
    let id:String
    let title:String
    var programmes:[Programme]
    let layout:Layout
    var episodeCollection:String?=nil
}
struct EpisodeDestination:Hashable {
    let programmeID:String
    let episodeID:String
    var pathValue:String {"episode:"+(try! JSONEncoder().encode([programmeID,episodeID])).base64EncodedString()}
    static func parse(_ value:String)->EpisodeDestination? {
        guard value.hasPrefix("episode:"),value.count<4096,
              let data=Data(base64Encoded:String(value.dropFirst(8))),
              let ids=try? JSONDecoder().decode([String].self,from:data),ids.count==2,ids.allSatisfy({!$0.isEmpty}) else {return nil}
        return EpisodeDestination(programmeID:ids[0],episodeID:ids[1])
    }
}

struct CollectionDestination:Hashable {
    let programmeID:String
    let collection:String
    var pathValue:String {"collection:"+collection+":"+programmeID}
    static func parse(_ value:String)->CollectionDestination? {
        let parts=value.split(separator:":",maxSplits:2).map(String.init)
        guard parts.count==3,parts[0]=="collection",parts[1]=="christmas",!parts[2].isEmpty else {return nil}
        return CollectionDestination(programmeID:parts[2],collection:parts[1])
    }
}
struct CuratedEpisode:Identifiable {
    let programme:Programme
    let episode:Episode
    var id:String {episode.id}
}
enum EditorialShelves {
    static func christmasEpisodes(_ programmes:[Programme])->[CuratedEpisode] {
        let groups=programmes.map{p in p.episodes.filter{matchesChristmas(p,$0)}.map{CuratedEpisode(programme:p,episode:$0)}}
        var output:[CuratedEpisode]=[];var seen=Set<String>();var index=0
        while groups.contains(where:{$0.count>index}) && output.count<48 {
            for group in groups where group.count>index {
                let entry=group[index]
                if seen.insert(entry.id).inserted {output.append(entry)}
            }
            index+=1
        }
        return Array(output.prefix(48))
    }
    static func christmas(_ title:String)->Bool {
        title.range(of:"\\b(christmas(?:sy)?|xmas|yuletide|festive (?:special|edition))\\b",options:[.regularExpression,.caseInsensitive]) != nil
    }
    static func matchesChristmas(_ programme:Programme,_ episode:Episode)->Bool {
        christmas(programme.title) || christmas(episode.title) || (episode.description ?? "").range(of:"\\b(christmas|festive) (special|edition)\\b",options:[.regularExpression,.caseInsensitive]) != nil
    }
    static func make(_ candidates:[Programme],films:Bool,year:Int=Calendar.current.component(.year,from:Date()),rotationDay:Int?=nil)->[EditorialShelf] {
        func titleKey(_ p:Programme)->String {p.title.folding(options:[.diacriticInsensitive,.caseInsensitive],locale:Locale(identifier:"en_GB")).replacingOccurrences(of:"[^\\w]+",with:" ",options:.regularExpression).trimmingCharacters(in:.whitespacesAndNewlines)}
        let eligible=candidates.filter{!$0.live && $0.film==films}
        var preferred:[String:Programme]=[:]
        func familiarity(_ p:Programme)->Int {(p.recent || p.latestProgress>0 ? 4 : 0)+(p.favourite ? 2 : 0)+(p.discoveryRef == nil ? 1 : 0)}
        for p in eligible {let key=titleKey(p);if preferred[key] == nil || familiarity(p)>familiarity(preferred[key]!) {preferred[key]=p}}
        var known=Set<String>()
        let source=eligible.compactMap{p->Programme? in let key=titleKey(p);return known.insert(key).inserted ? preferred[key] : nil}
        guard !source.isEmpty else {return []}
        let now=Date();let calendar=Calendar.current
        let day=rotationDay ?? Int(calendar.startOfDay(for:now).timeIntervalSince1970/86400)
        func rank(_ key:String)->String {SHA256.hash(data:Data("\(day):\(key)".utf8)).map{String(format:"%02x",$0)}.joined()}
        var result:[EditorialShelf]=[];var uses:[String:Int]=[:]
        func add(_ key:String,_ title:String,_ input:[Programme],feature:Bool=false,collection:String?=nil,explore:Bool=false) {
            let eligible=input.filter{uses[$0.id,default:0]<2}
            let posters=eligible.filter{$0.poster?.isEmpty == false}
            let minimum=feature ? 3 : 4
            let portrait=collection == nil && posters.count>=minimum
            let candidates=portrait ? posters : eligible
            let limit=feature ? 8 : 16
            let selected:[Programme]
            if explore {
                let fresh=Array(candidates.filter{!$0.favourite && !$0.recent && $0.latestProgress==0}.prefix(64))
                let close=Array(fresh.prefix(2))
                let broader=fresh.dropFirst(2).sorted{rank(key+":"+$0.id)<rank(key+":"+$1.id)}
                let newCount=max(2,Int(ceil(Double(limit)*0.75)))
                let discoveries=Array((close+broader).prefix(newCount))
                let selectedIDs=Set(discoveries.map(\.id))
                let familiar=candidates.filter{!selectedIDs.contains($0.id)}
                selected=Array((discoveries+familiar).prefix(limit))
            } else {selected=Array(candidates.prefix(limit))}
            let cardCount=collection == "christmas" ? christmasEpisodes(selected).count : selected.count
            guard cardCount>=minimum || result.isEmpty else {return}
            let ids=Set(selected.map(\.id))
            guard !result.contains(where:{row in row.episodeCollection == collection && Double(ids.intersection(row.programmes.map(\.id)).count)/Double(max(1,ids.union(row.programmes.map(\.id)).count))>0.8}) else {return}
            result.append(EditorialShelf(id:key,title:title,programmes:selected,layout:portrait ? (feature ? .feature : .portrait) : .landscape,episodeCollection:collection))
            for p in selected {uses[p.id,default:0]+=1}
        }
        add("personal",films ? "Picked for tonight" : "Your next great watch",Array(source.prefix(20)))
        let festive=source.filter{p in !p.episodes.isEmpty && p.episodes.contains{matchesChristmas(p,$0)}}
        let month=calendar.component(.month,from:now),date=calendar.component(.day,from:now)
        if month>=11 || (month==1 && date<=6) {add("christmas","Christmas Specials",festive,collection:"christmas")}
        var themes:[(String,String,[Programme],Bool)]=[("archive","From the Archive",source.filter{($0.archiveYear ?? Int.max)<=year-15},true)]
        func provider(_ p:Programme,_ key:String)->Bool {p.brands.contains{$0.id.lowercased()==key || (key=="bbc" && $0.name.localizedCaseInsensitiveContains("iplayer"))}}
        themes.append(("iplayer","Best of iPlayer",source.filter{provider($0,"bbc")},true))
        let categories:[(String,String,[String])]=films ? [
            ("comedy","A night of laughs",["comedy"]),("crime","Crime & suspense",["crime","thriller","mystery"]),
            ("true","True stories",["documentar","factual"]),("adventure","Escape into adventure",["adventure","action","fantasy","science fiction"]),
            ("drama","Stories that stay with you",["drama"]),("family","Family film night",["family","children","animation"])
        ] : [
            ("comedy","Comedy favourites",["comedy"]),("true","Real lives. Remarkable stories.",["documentar","factual"]),
            ("crime","Crime & mystery",["crime","mystery","thriller"]),("adventure","Extraordinary worlds",["nature","science","adventure","fantasy"]),
            ("drama","Get lost in a great drama",["drama"]),("entertainment","Something to make you smile",["entertainment","talk"])
        ]
        for (key,title,genres) in categories {
            themes.append((key,title,source.filter{p in p.genres.contains{g in genres.contains{g.localizedCaseInsensitiveContains($0)}}},key=="adventure"))
        }
        for (key,title) in [("channel4","Channel 4 discoveries"),("u","Worth your time on U"),("itv","Discover ITVX"),("channel5","Discover 5")] {
            themes.append((key,title,source.filter{provider($0,key)},false))
        }
        for (key,title,rows,feature) in themes.sorted(by:{if ($0.0=="archive") != ($1.0=="archive") {return $0.0=="archive"};return rank($0.0)<rank($1.0)}) {add(key,title,rows,feature:feature,explore:true)}
        // Every remaining title is reachable. Merge a short tail into the last
        // row instead of generating a lonely row of one or two cards.
        var remaining=source.filter{uses[$0.id,default:0]==0}
        var page=0
        while !remaining.isEmpty {
            let count=remaining.count<=15 ? remaining.count : 12
            var chunk=Array(remaining.prefix(count));remaining.removeFirst(count)
            if chunk.count<4,result.count>0 {
                if let index=result.lastIndex(where:{$0.layout == .landscape}) {result[index].programmes.append(contentsOf:chunk);break}
                let existing=Set(chunk.map(\.id));chunk.append(contentsOf:source.filter{!existing.contains($0.id)}.prefix(8-chunk.count))
            }
            result.append(EditorialShelf(id:"explore-\(page)",title:page==0 ? (films ? "More films to explore" : "More shows to discover") : "",programmes:chunk,layout:chunk.count>=4 && chunk.allSatisfy{$0.poster?.isEmpty == false} ? .portrait : .landscape))
            page+=1
        }
        return result
    }
}
