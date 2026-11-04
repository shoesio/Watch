// BBC catalogue selection follows Telly/Beeb (GPL-3.0-or-later); see NOTICE.md.
import Foundation

enum BBCUHDError:LocalizedError {
    case message(String)
    var errorDescription:String? {if case .message(let value)=self {return value};return nil}
}
struct BBCUHDProgramme {let id:String;let version:String}
struct BBCUHDSource {let url:URL;let versionID:String}
enum BBCUHDMetadata {
    static func pid(_ value:String)throws->String {
        guard value.range(of:"^[a-z0-9]{8}$",options:.regularExpression) != nil else {throw BBCUHDError.message("Invalid BBC episode.")};return value
    }
    static func mediaAllowed(_ url:URL)->Bool {
        guard url.scheme == "https",url.user == nil,url.password == nil,url.port == nil || url.port == 443,let host=url.host else {return false}
        return host.hasSuffix(".bbci.co.uk") || host.hasSuffix(".bbc.co.uk") || host.hasSuffix(".akamaized.net") || host.hasSuffix(".akamaihd.net")
    }
    static func fetch(_ url:URL)async throws->Data {
        guard mediaAllowed(url) else {throw BBCUHDError.message("Unexpected BBC media address.")}
        var request=URLRequest(url:url);request.timeoutInterval=20
        let (data,response)=try await URLSession.shared.data(for:request)
        guard let http=response as? HTTPURLResponse,http.statusCode == 200,let final=http.url,mediaAllowed(final),data.count<16_000_000 else {throw BBCUHDError.message("BBC UHD media is currently unavailable.")}
        return data
    }
    static func episodeMetadata(_ data:Data,id:String)throws->[String:Any] {
        let root=try JSONSerialization.jsonObject(with:data) as? [String:Any]
        guard let episode=(root?["episodes"] as? [[String:Any]])?.first(where:{$0["id"] as? String == id}) else {throw BBCUHDError.message("BBC episode details are unavailable.")};return episode
    }
    static func playbackVersions(_ episode:[String:Any],now:Date=Date())->[String] {
        let versions=(episode["versions"] as? [[String:Any]] ?? []).filter {v in
            let kind=(v["kind"] as? String ?? "").lowercased()
            guard !kind.contains("signed"),!kind.contains("describ"),let id=v["id"] as? String,(try? pid(id)) != nil else {return false}
            let availability=v["availability"] as? [String:Any] ?? [:]
            for key in ["start","end"] {
                if let raw=availability[key] as? String {
                    let f=ISO8601DateFormatter();f.formatOptions=[.withInternetDateTime,.withFractionalSeconds]
                    guard let date=f.date(from:raw) ?? ISO8601DateFormatter().date(from:raw) else {return false}
                    if key == "start" && date>now || key == "end" && date<=now {return false}
                }
            };return true
        }
        return (versions.filter {$0["uhd"] as? Bool == true}+versions.filter {$0["uhd"] as? Bool != true}).compactMap {$0["id"] as? String}
    }
    static func programme(_ id:String)async throws->BBCUHDProgramme {
        let id=try pid(id),episode=try episodeMetadata(await fetch(URL(string:"https://ibl.api.bbc.co.uk/ibl/v1/episodes/"+id)!),id:id)
        guard let version=playbackVersions(episode).first else {throw BBCUHDError.message("No available BBC edition.")}
        return BBCUHDProgramme(id:id,version:version)
    }
    static func resolve(_ reference:String,base:URL)->URL? {
        guard let url=URL(string:reference,relativeTo:base)?.absoluteURL,mediaAllowed(url) else {return nil}
        guard url.host == base.host,var parts=URLComponents(url:url,resolvingAgainstBaseURL:true),let query=URLComponents(url:base,resolvingAgainstBaseURL:true)?.percentEncodedQuery else {return url}
        parts.percentEncodedQuery=parts.percentEncodedQuery.map {query+"&"+$0} ?? query;return parts.url
    }
}
