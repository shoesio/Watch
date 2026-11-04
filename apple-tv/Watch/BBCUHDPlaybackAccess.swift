// SPDX-License-Identifier: GPL-3.0-or-later
// BBC client-certificate request flow follows TwinVine's iP service; see NOTICE.md.
import Foundation

@MainActor final class UHDPlaybackAccess {
    private var bridge: LocalHLSServer?
    private let secureFetch: (() throws -> BBCSecureSession)
    private let fetch: (URL) async throws -> Data
    init(secureSession: @escaping () throws -> BBCSecureSession = { try BBCSecureSession.configured() }, fetch: @escaping (URL) async throws -> Data = { try await BBCUHDMetadata.fetch($0) }) {
        secureFetch = secureSession; self.fetch = fetch
    }
    private func manifest(for programme: BBCUHDProgramme) async throws -> (manifest: DASHManifest, versionID: String) {
        let client = try secureFetch(); defer { client.invalidate() }
        let id = try BBCUHDMetadata.pid(programme.id)
        let metadata = try await fetch(URL(string: "https://ibl.api.bbc.co.uk/ibl/v1/episodes/\(id)")!)
        let episode = try BBCUHDMetadata.episodeMetadata(metadata, id: id)
        guard (episode["versions"] as? [[String:Any]] ?? []).contains(where:{$0["uhd"] as? Bool == true}) else {throw BBCUHDError.message("This episode is not listed in UHD.")}
        let ids = BBCUHDMetadata.playbackVersions(episode)
        var last: Error?
        var seen = Set<String>()
        for version in ids where seen.insert(version).inserted {
            try Task.checkCancellation()
            do {
                let id = try BBCUHDMetadata.pid(version)
                let url = URL(string: "https://securegate.iplayer.bbc.co.uk/mediaselector/6/select/version/2.0/vpid/\(id)/format/json/mediaset/iptv-uhd/proto/https")!
                let data = try await client.fetch(url)
                let response = try JSONSerialization.jsonObject(with: data) as? [String: Any] ?? [:]
                let media = response["media"] as? [[String: Any]] ?? []
                for video in media where video["kind"] as? String == "video" {
                    let height = Int(video["height"] as? String ?? "") ?? video["height"] as? Int ?? 0
                    guard height >= 2160 else { continue }
                    let connections = (video["connection"] as? [[String: Any]] ?? []).sorted { (Int($0["priority"] as? String ?? "99") ?? 99) < (Int($1["priority"] as? String ?? "99") ?? 99) }
                    for connection in connections where connection["transferFormat"] as? String == "dash" {
                        guard let href = connection["href"] as? String, let url = URL(string: href), url.scheme == "https" else { continue }
                        do {
                            let manifest = try DASHManifest.parse(await fetch(url), url: url)
                            let initialization = try await fetch(manifest.video.initialization)
                            guard DASHManifest.signalsHLG(initialization) else { throw BBCUHDError.message("The UHD stream does not signal HLG in its video initialization metadata.") }
                            return (manifest, id)
                        } catch { if Task.isCancelled { throw CancellationError() }; last = error }
                    }
                }
            } catch { if Task.isCancelled { throw CancellationError() }; last = error }
        }
        throw BBCUHDError.message(last?.localizedDescription ?? "BBC has not returned a 4K HLG stream for this episode.")
    }
    func probe(_ programme: BBCUHDProgramme) async throws { _ = try await manifest(for: programme) }
    func source(for programme: BBCUHDProgramme) async throws -> BBCUHDSource {
        let result = try await manifest(for: programme)
        let manifest = result.manifest
        try Task.checkCancellation()
        let server = LocalHLSServer(); bridge?.stop(); bridge = server
        let url = try await server.start(playlists: manifest.playlists, media: manifest.mediaResources)
        if Task.isCancelled { server.stop(); throw CancellationError() }
        return BBCUHDSource(url: url, versionID: result.versionID)
    }
    func stop() { bridge?.stop(); bridge = nil }
    deinit { bridge?.stop() }
}
