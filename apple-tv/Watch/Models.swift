import Foundation

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
    let showLogo: String?
    let channelLogo: String?
    let live: Bool
    let uhdAvailable:Bool?
    let film: Bool
    let filmRank:Int?
    let recent: Bool
    let favourite: Bool
    let genres: [String]
    let brands: [Brand]
    let episodes: [Episode]
    let resumeEpisode: String?
    let discoveryRef:String?
    let recommendationReason:String?
    let contentRating:String?
    let ratingSource:String?
    let guide: Guide?
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
