// SPDX-License-Identifier: GPL-3.0-or-later
import Foundation
import AVFoundation
#if canImport(UIKit)
import UIKit
#endif
enum NativeDevice {
    static var osVersion:String {
        #if canImport(UIKit)
        return UIDevice.current.systemVersion
        #else
        return "17.0"
        #endif
    }
    static var model:String {
        #if canImport(UIKit)
        return UIDevice.current.model
        #else
        return "Apple TV"
        #endif
    }
}

struct ITVProbeError: LocalizedError, CustomNSError {
    let stage: String
    let detail: String
    var errorDescription: String? { "\(stage): \(detail)" }
    static var errorDomain: String { "Telly.ITVPlayback" }
    var errorCode: Int { 1 }
    var errorUserInfo: [String: Any] { [NSLocalizedDescriptionKey: errorDescription ?? "ITV playback failed."] }
}

/// Public URLs and non-secret wire-format helpers, kept separate for fixture checks.
enum ITVFairPlayWire {
    static let certificateURL = URL(string: "https://fairplay-drm.cloudfront.prd.ottstream.itv.com/cert-FairPlay-itv.der")!
    static let playlistURL = URL(string: "https://magni.itv.com/playlist/itvonline/ITV/10_8290_0001.001")!
    static func licenceURL(_ identifier: String) throws -> URL {
        guard var parts = URLComponents(string: identifier), parts.scheme == "skd",
              parts.user == nil, parts.password == nil, parts.port == nil, parts.fragment == nil else {
            throw ITVProbeError(stage: "FairPlay", detail: "Unexpected content-key endpoint.")
        }
        let irdeto = parts.host == "itvpnp.live.ott.irdeto.com" && ["/Streaming/getckc", "/streaming/getckc"].contains(parts.path)
        let themed = parts.host == "fairplay-license.itvx.vudrm.tech" && parts.path.range(of: "^/v2/license/F[0-9]{2,3}$", options: .regularExpression) != nil
        guard irdeto || themed else { throw ITVProbeError(stage: "FairPlay", detail: "Unsupported ITV licence service.") }
        parts.scheme = "https"
        guard let url = parts.url else { throw ITVProbeError(stage: "FairPlay", detail: "Invalid licence URL.") }
        return url
    }
    // ITV's web player uses the default FairPlay content ID: the SKD query string.
    static func contentID(_ identifier: String) throws -> Data {
        _ = try licenceURL(identifier)
        let parts = URLComponents(string: identifier)!
        if parts.host == "fairplay-license.itvx.vudrm.tech" {
            return Data((parts.path.split(separator: "/").last.map(String.init) ?? "").utf8)
        }
        guard let query = parts.percentEncodedQuery, !query.isEmpty else {
            throw ITVProbeError(stage: "FairPlay", detail: "The content identifier is missing.")
        }
        return Data(query.utf8)
    }
    static func licenceBody(challenge: Data, contentID: Data) -> Data {
        let allowed = CharacterSet(charactersIn: "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-._~")
        func escape(_ text: String) -> String { text.addingPercentEncoding(withAllowedCharacters: allowed)! }
        return Data(("spc=" + escape(challenge.base64EncodedString()) + "&assetId=" + escape(String(decoding: contentID, as: UTF8.self))).utf8)
    }
    static func isThemed(_ endpoint: URL) -> Bool { endpoint.host == "fairplay-license.itvx.vudrm.tech" }
    static func licenceRequest(identifier: String, challenge: Data) throws -> URLRequest {
        let endpoint = try licenceURL(identifier)
        var request = URLRequest(url: endpoint); request.httpMethod = "POST"
        // ITV's registered THEO FairPlay integration forwards the raw SPC with
        // this header. Main-channel Irdeto also accepts the existing form format.
        request.setValue("application/x-www-form-urlencoded", forHTTPHeaderField: "Content-Type")
        request.setValue("https://www.itv.com", forHTTPHeaderField: "Origin")
        request.setValue("https://www.itv.com/", forHTTPHeaderField: "Referer")
        request.httpBody = isThemed(endpoint) ? challenge : licenceBody(challenge: challenge, contentID: try contentID(identifier))
        return request
    }
    static func responseData(_ data: Data, mime: String?, endpoint: URL) throws -> Data {
        if isThemed(endpoint) {
            guard !data.isEmpty, data.count <= 1024 * 1024,
                  mime?.contains("json") != true, mime?.contains("text") != true else {
                throw ITVProbeError(stage: "Themed-channel licence", detail: "ITV returned an invalid binary licence response.")
            }
            return data
        }
        return try decodeLicence(data, mime: mime)
    }
    static func failureMessage(_ error: NSError) -> String {
        if error.domain == ITVProbeError.errorDomain {
            return (error.userInfo[NSLocalizedDescriptionKey] as? String) ?? "The ITV licence request failed before a content-key response was supplied."
        }
        return "FairPlay rejected the content-key response (\(error.domain) \(error.code))."
    }
    static func decodeLicence(_ data: Data, mime: String?) throws -> Data {
        guard !data.isEmpty, data.count <= 1024 * 1024 else {
            throw ITVProbeError(stage: "Licence response", detail: "Empty or oversized response.")
        }
        if let text = String(data: data, encoding: .utf8) {
            var value = text.trimmingCharacters(in: .whitespacesAndNewlines)
            if value.hasPrefix("<ckc>"), value.hasSuffix("</ckc>") { value = String(value.dropFirst(5).dropLast(6)) }
            if let decoded = Data(base64Encoded: value), !decoded.isEmpty { return decoded }
            if mime?.contains("text") == true || mime?.contains("json") == true || value.hasPrefix("<") {
                throw ITVProbeError(stage: "Licence response", detail: "Server returned text instead of a FairPlay licence.")
            }
        }
        return data
    }
}

final class ITVProbeHTTP: NSObject, URLSessionTaskDelegate, @unchecked Sendable {
    private lazy var session: URLSession = {
        let configuration = URLSessionConfiguration.ephemeral
        configuration.timeoutIntervalForRequest = 25
        configuration.timeoutIntervalForResource = 45
        configuration.urlCache = nil
        configuration.httpCookieStorage = nil
        return URLSession(configuration: configuration, delegate: self, delegateQueue: nil)
    }()
    func urlSession(_ session: URLSession, task: URLSessionTask,
                    willPerformHTTPRedirection response: HTTPURLResponse, newRequest request: URLRequest,
                    completionHandler: @escaping (URLRequest?) -> Void) { completionHandler(nil) }
    func fetch(_ request: URLRequest, stage: String, limit: Int = 2 * 1024 * 1024) async throws -> (Data, HTTPURLResponse) {
        let (data, response) = try await session.data(for: request)
        try Task.checkCancellation()
        guard let http = response as? HTTPURLResponse else { throw ITVProbeError(stage: stage, detail: "Missing HTTP response.") }
        guard http.statusCode == 200 else { throw ITVProbeError(stage: stage, detail: "HTTP \(http.statusCode). Playback may require an authorised ITV client or account.") }
        guard !data.isEmpty, data.count <= limit else { throw ITVProbeError(stage: stage, detail: "Empty or oversized response.") }
        return (data, http)
    }
    func cancel() { session.invalidateAndCancel() }
}

final class ITVFairPlaySession: NSObject, AVContentKeySessionDelegate, @unchecked Sendable {
    private let keySession = AVContentKeySession(keySystem: .fairPlayStreaming)
    private let queue = DispatchQueue(label: "org.tellyplayer.itv.fairplay")
    private let certificate: Data
    private let http: ITVProbeHTTP
    private let report: @Sendable (String, Bool) -> Void
    private let lock = NSLock()
    private var tasks = [UUID: Task<Void, Never>]()
    private var active = true
    init(certificate: Data, http: ITVProbeHTTP, report: @escaping @Sendable (String, Bool) -> Void) {
        self.certificate = certificate; self.http = http; self.report = report
        super.init(); keySession.setDelegate(self, queue: queue)
    }
    func attach(to asset: AVURLAsset) { keySession.addContentKeyRecipient(asset) }
    func stop() {
        lock.lock(); active = false; let pending = Array(tasks.values); tasks.removeAll(); lock.unlock()
        pending.forEach { $0.cancel() }; keySession.expire()
    }
    func contentKeySession(_ session: AVContentKeySession, didProvide keyRequest: AVContentKeyRequest) { handle(keyRequest) }
    func contentKeySession(_ session: AVContentKeySession, didProvideRenewingContentKeyRequest keyRequest: AVContentKeyRequest) {
        report("FairPlay renewal requested", false); handle(keyRequest)
    }
    func contentKeySession(_ session: AVContentKeySession, contentKeyRequest: AVContentKeyRequest, didFailWithError err: Error) {
        report(ITVFairPlayWire.failureMessage(err as NSError), true)
    }
    func contentKeySession(_ session: AVContentKeySession, contentKeyRequestDidSucceed keyRequest: AVContentKeyRequest) {
        report("FairPlay accepted the content-key response", false)
    }
    private func removeTask(_ id: UUID) {
        lock.lock(); defer { lock.unlock() }; tasks.removeValue(forKey: id)
    }
    private func handle(_ request: AVContentKeyRequest) {
        let id = UUID()
        lock.lock()
        guard active else { lock.unlock(); return }
        let task = Task { [self] in
            defer { removeTask(id) }
            do {
                let identifier: String
                if let url = request.identifier as? URL { identifier = url.absoluteString }
                else if let text = request.identifier as? String { identifier = text }
                else { throw ITVProbeError(stage: "FairPlay", detail: "Missing key identifier.") }
                let endpoint = try ITVFairPlayWire.licenceURL(identifier)
                let contentID = try ITVFairPlayWire.contentID(identifier)
                report("Generating an Apple TV FairPlay challenge", false)
                let challenge: Data = try await withCheckedThrowingContinuation { continuation in
                    request.makeStreamingContentKeyRequestData(forApp: certificate, contentIdentifier: contentID,
                        options: [AVContentKeyRequestProtocolVersionsKey: [1]]) { data, error in
                        if let data { continuation.resume(returning: data) }
                        else { continuation.resume(throwing: error ?? ITVProbeError(stage: "FairPlay", detail: "Challenge generation failed.")) }
                    }
                }
                try Task.checkCancellation()
                let req = try ITVFairPlayWire.licenceRequest(identifier: identifier, challenge: challenge)
                report("Requesting a licence for this Apple TV", false)
                let (data, response) = try await http.fetch(req, stage: "FairPlay licence", limit: 1024 * 1024)
                let ckc = try ITVFairPlayWire.responseData(data, mime: response.mimeType, endpoint: endpoint)
                try Task.checkCancellation()
                request.processContentKeyResponse(AVContentKeyResponse(fairPlayStreamingKeyResponseData: ckc))
                report("Licence response submitted to AVFoundation", false)
            } catch is CancellationError { }
            catch {
                // URLSession errors can contain signed URLs. Show only the stage/domain/code.
                let message: String
                if let e = error as? ITVProbeError { message = e.localizedDescription }
                else { let e = error as NSError; message = "FairPlay request failed (\(e.domain) \(e.code))." }
                report(message, true)
                request.processContentKeyResponseError(ITVProbeError(stage: "ITV request", detail: message))
            }
        }
        tasks[id] = task; lock.unlock()
    }
}


actor ITVPlaybackAPI {
    static let shared=ITVPlaybackAPI()
    func source(_ native:NativePlayback) async throws -> PlaybackSource {
        let http=ITVProbeHTTP();defer { http.cancel() }
        let url:URL
        if native.live {
            guard let raw=native.playlistUrl,let endpoint=URL(string:raw) else { throw ITVAccountError.message("Missing ITV live address.") }
            url=try await ITVAccountService.shared.liveURL(channel:LiveChannel(id:"itv:"+native.id,itvPlaylistURL:endpoint),osVersion:NativeDevice.osVersion,model:NativeDevice.model)
        } else {
            guard native.premium != true else { throw ITVAccountError.message("ITVX Premium playback is not supported in Watch yet.") }
            guard let raw=native.playlistUrl,let endpoint=URL(string:raw),endpoint.scheme=="https",endpoint.host=="magni.itv.com",endpoint.user==nil,endpoint.password==nil,endpoint.path.hasPrefix("/playlist/itvonline/") else { throw ITVAccountError.message("Invalid ITV episode address.") }
            let features=["hls","fairplay","outband-webvtt","hd","single-track"]
            var request=URLRequest(url:endpoint);request.httpMethod="POST"
            request.setValue("application/vnd.itv.vod.playlist.v2+json",forHTTPHeaderField:"Accept")
            request.setValue("application/json",forHTTPHeaderField:"Content-Type")
            request.httpBody=try JSONSerialization.data(withJSONObject:["client":["id":"browser"],"variantAvailability":["featureset":["min":features,"max":features],"platformTag":"ctv"]])
            let (body,_)=try await http.fetch(request,stage:"ITV episode")
            guard let root=try JSONSerialization.jsonObject(with:body) as? [String:Any],let video=(root["Playlist"] as? [String:Any])?["Video"] as? [String:Any],let files=video["MediaFiles"] as? [[String:Any]],let href=files.first?["Href"] as? String,let base=URL(string:video["Base"] as? String ?? ""),let resolved=URL(string:href,relativeTo:base)?.absoluteURL,resolved.scheme=="https",resolved.host?.hasSuffix(".content.itv.com")==true else { throw ITVAccountError.message("ITV did not offer compatible Apple TV playback.") }
            url=resolved
        }
        let (cert,_)=try await http.fetch(URLRequest(url:ITVFairPlayWire.certificateURL),stage:"ITV certificate",limit:128*1024)
        guard cert.first==0x30 else { throw ITVAccountError.message("ITV returned an invalid playback certificate.") }
        return PlaybackSource(url:url,requested1080:false,fairPlayCertificate:cert)
    }
}
