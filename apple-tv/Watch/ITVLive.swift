// SPDX-License-Identifier: GPL-3.0-or-later
import Foundation
struct ITVLiveAPI {
    static func endpoint(_ url: URL, channelID: String? = nil) throws -> URL {
        let prefix = "/playlist/itvonline/"
        guard url.scheme == "https", ["simulcast.itv.com", "stream-starter.fastly.ottstream.itv.com"].contains(url.host ?? ""),
              url.user == nil, url.password == nil, url.port == nil, url.query == nil, url.fragment == nil,
              url.path.hasPrefix(prefix) else { throw ITVAccountError.message("Invalid ITV live channel address.") }
        let id = String(url.path.dropFirst(prefix.count))
        guard validID(id), channelID.map({ $0.lowercased() == id.lowercased() }) ?? true else {
            throw ITVAccountError.message("Invalid ITV live channel identifier.")
        }
        return url
    }
    static func validID(_ id: String) -> Bool {
        ["itv", "itv2", "itv3", "itv4", "itvbe"].contains(id.lowercased()) || id.range(of: "^FAST[0-9]{1,3}$", options: [.regularExpression, .caseInsensitive]) != nil
    }
    static func playbackURL(from data: Data) throws -> URL {
        let root = try JSONSerialization.jsonObject(with: data) as? [String: Any]
        let video = (root?["Playlist"] as? [String: Any])?["Video"] as? [String: Any]
        let locations = video?["VideoLocations"] as? [[String: Any]] ?? []
        for location in locations where location["IsDar"] as? Bool != true {
            guard let raw = location["Url"] as? String, let url = URL(string: raw), url.scheme == "https",
                  url.host?.hasSuffix(".content.itv.com") == true, url.user == nil, url.password == nil, url.port == nil,
                  url.path.lowercased().hasSuffix(".m3u8") else { continue }
            return url
        }
        throw ITVAccountError.message("ITV did not return a compatible native live stream. This channel may be unavailable on this device.")
    }
    static func requestBody(token: String, osVersion: String, model: String) -> [String: Any] {
        let features = ["hls", "fairplay"]
        return ["client": ["id": "browser", "service": "itv.x", "version": "4.1"],
            "device": ["manufacturer": "Apple", "model": model, "os": ["name": "tvOS", "version": osVersion, "type": "ctv"], "deviceGroup": "ctv"],
            "user": ["token": token], "variantAvailability": ["player": "hls", "platformTag": "ctv", "featureset": ["min": features, "max": features]]]
    }
}
