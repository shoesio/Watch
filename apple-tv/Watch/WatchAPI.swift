import Foundation
import Security

// Pi pairing and native Channel 5 sign-in use separate device-only Keychain records.
enum PairingStore {
    private static let service = "home.watch.tvos"
    static func read() -> String? {
        let query: [String: Any] = [kSecClass as String: kSecClassGenericPassword, kSecAttrService as String: service, kSecAttrAccount as String: "device", kSecReturnData as String: true, kSecMatchLimit as String: kSecMatchLimitOne]
        var result: CFTypeRef?
        guard SecItemCopyMatching(query as CFDictionary, &result) == errSecSuccess, let data = result as? Data else { return nil }
        return String(data: data, encoding: .utf8)
    }
    static func save(_ token: String?) throws {
        let query: [String: Any] = [kSecClass as String: kSecClassGenericPassword, kSecAttrService as String: service, kSecAttrAccount as String: "device"]
        SecItemDelete(query as CFDictionary)
        if let token {
            var values = query; values[kSecValueData as String] = Data(token.utf8); values[kSecAttrAccessible as String] = kSecAttrAccessibleAfterFirstUnlockThisDeviceOnly
            guard SecItemAdd(values as CFDictionary, nil) == errSecSuccess else { throw WatchError(message: "Could not save pairing securely. Please try again.") }
        }
    }
}

@MainActor final class WatchAPI {
    var base: String { UserDefaults.standard.string(forKey: "server") ?? "http://192.168.0.146:8115" }
    var token: String?
    init() { token = PairingStore.read() }
    func request<T: Decodable>(_ path: String, method: String = "GET", body: [String: Any]? = nil) async throws -> T {
        guard let url = URL(string: base + path), ["http", "https"].contains(url.scheme) else { throw WatchError(message: "Check the Pi address in Settings.") }
        var request = URLRequest(url: url); request.httpMethod = method; request.timeoutInterval = ["/related","/shows","/discover"].contains(where:{path.hasPrefix($0)}) ? 90 : 30
        if let token { request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization") }
        if let body { request.httpBody = try JSONSerialization.data(withJSONObject: body); request.setValue("application/json", forHTTPHeaderField: "Content-Type") }
        let (data, response) = try await URLSession.shared.data(for: request)
        guard let response = response as? HTTPURLResponse, (200..<300).contains(response.statusCode) else {
            if (response as? HTTPURLResponse)?.statusCode == 401 { token = nil; try? PairingStore.save(nil) }
            throw WatchHTTPError(status:(response as? HTTPURLResponse)?.statusCode ?? 0,message:(try? JSONDecoder().decode(APIError.self, from:data).error) ?? "The Pi could not complete that request.")
        }
        if T.self == Empty.self { return Empty() as! T }
        return try JSONDecoder.watch.decode(T.self, from: data)
    }
    func pair(code: String) async throws {
        let result: PairResponse = try await request("/pair", method: "POST", body: ["code": code.filter(\.isNumber)])
        try PairingStore.save(result.token); token = result.token
    }
    func library() async throws -> [Programme] { let result: Library = try await request("/library"); return result.programmes }
    func favourite(id:String,value:Bool) async throws -> [Programme] {
        let result:Library=try await request("/favourites",method:"POST",body:["id":id,"favourite":value])
        return result.programmes
    }
    func search(_ query:String) async throws -> DiscoveryResponse {
        let encoded=query.addingPercentEncoding(withAllowedCharacters:.urlQueryAllowed.subtracting(CharacterSet(charactersIn:"&+#=?"))) ?? ""
        return try await request("/search?q="+encoded)
    }
    func shows(genre:String? = nil,cursor:String? = nil) async throws -> ShowsResponse {
        var parts=URLComponents();parts.queryItems=[]
        if let genre { parts.queryItems?.append(URLQueryItem(name:"genre",value:genre)) }
        if let cursor { parts.queryItems?.append(URLQueryItem(name:"cursor",value:cursor)) }
        return try await request("/shows"+(parts.percentEncodedQuery.map { "?"+$0 } ?? ""))
    }
    func discover(genre:String? = nil,cursor:String? = nil) async throws -> DiscoveryResponse {
        var path="/discover"
        if let genre { path+="?genre="+(genre.addingPercentEncoding(withAllowedCharacters:.urlQueryAllowed.subtracting(CharacterSet(charactersIn:"&+#=?"))) ?? "") }
        if let cursor { path+=(path.contains("?") ? "&" : "?")+"cursor="+(cursor.addingPercentEncoding(withAllowedCharacters:.urlQueryAllowed.subtracting(CharacterSet(charactersIn:"&+#=?"))) ?? "") }
        return try await request(path)
    }
    func related(id:String,cursor:String? = nil) async throws -> DiscoveryResponse {
        var path="/related?id="+id
        if let cursor { path+="&cursor="+(cursor.addingPercentEncoding(withAllowedCharacters:.urlQueryAllowed.subtracting(CharacterSet(charactersIn:"&+#=?"))) ?? "") }
        return try await request(path)
    }
    func importProgramme(_ ref:String) async throws -> Programme {
        let result:Library=try await request("/discover/import",method:"POST",body:["ref":ref])
        guard let programme=result.programmes.first else { throw WatchError(message:"No available episodes were found.") }
        return programme
    }
    func prepare(id: String, position: Double, preferDirect:Bool = true) async throws -> Prepared {
        struct Job: Decodable { let job: String }
        let result: Job = try await request("/prepare", method: "POST", body: ["episode_id": id, "position": position, "native_playback":true, "native_channel4_live":true, "prefer_direct":preferDirect])
        do {
            for _ in 0..<180 {
                try Task.checkCancellation()
                let state: Prepared = try await request("/prepare/\(result.job)")
                if state.state == "ready" { return state }
                if state.state == "failed" { throw WatchError(message: state.error ?? "Could not prepare this episode.") }
                try await Task.sleep(for: .seconds(1))
            }
            throw WatchError(message: "This source is taking too long. Try again shortly.")
        } catch {
            // Cancellation must revoke a pending preparation rather than leaving a stream behind.
            let _: Empty? = try? await request("/prepare/\(result.job)", method: "DELETE")
            throw error
        }
    }
    func playbackCapabilities() async throws -> PlaybackCapabilities {try await request("/playback/capabilities")}
    private func playbackQuery(_ path:String,_ pairs:[String:String])->String {
        var parts=URLComponents();parts.queryItems=pairs.sorted {$0.key<$1.key}.map {URLQueryItem(name:$0.key,value:$0.value)}
        return path+"?"+(parts.percentEncodedQuery ?? "")
    }
    func features(episode:String,source:String,version:String?,ticket:String) async throws -> EpisodeFeatures {
        var pairs=["episode_id":episode,"source_key":source,"ticket":ticket]
        if let version {pairs["version_id"]=version}
        return try await request(playbackQuery("/playback/features",pairs))
    }
    func reportEnding(ticket:String,state:String,start:Double?=nil,expected:Double?=nil,actual:Double?=nil)async {
        var body:[String:Any]=["ticket":ticket,"state":state]
        if let start {body["start"]=start};if let expected {body["expected"]=expected};if let actual {body["actual"]=actual}
        let _:Empty?=try? await request("/playback/ending/report",method:"POST",body:body)
    }
    struct EndingPreview:Decodable {let state:String;let start:Double?;let duration:Double?;let versionId:String?}
    func endingPreview(ticket:String,version:String?)async throws->(URL,Double,Double)? {
        let query=playbackQuery("/playback/ending",["ticket":ticket,"version_id":version ?? ""])
        for _ in 0..<32 {
            try Task.checkCancellation()
            let status:EndingPreview=try await request(query)
            if status.state=="unavailable" || status.versionId != version {return nil}
            if status.state=="ready",let start=status.start,let duration=status.duration {
                var request=URLRequest(url:URL(string:base+playbackQuery("/playback/ending/file",["ticket":ticket]))!)
                if let token {request.setValue("Bearer \(token)",forHTTPHeaderField:"Authorization")}
                let (data,response)=try await URLSession.shared.data(for:request)
                guard (response as? HTTPURLResponse)?.statusCode==200,data.count<12_000_000 else {return nil}
                let file=FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString+".mp4")
                try data.write(to:file,options:.atomic);return (file,start,duration)
            }
            try await Task.sleep(for:.seconds(3))
        }
        return nil
    }
    func upNext(episode:String) async throws -> NextEpisodes {try await request(playbackQuery("/playback/up-next",["episode_id":episode]))}
    func queue() async throws -> SeriesQueue {try await request("/playback/queue")}
    func seedQueue(episode:String,revision:Int,autoplay:Bool) async throws -> SeriesQueue {
        try await request("/playback/queue",method:"POST",body:["episode_id":episode,"expected_revision":revision,"autoplay":autoplay])
    }
    func advanceQueue(episode:String,revision:Int) async throws -> SeriesQueue {
        try await request("/playback/queue/advance",method:"POST",body:["completed_episode_id":episode,"expected_revision":revision])
    }
    func saveCompletion(ticket:String,position:Double) async throws {
        let _:Empty=try await request("/session/"+ticket,method:"POST",body:["position":position,"completed":true])
    }
    func progress(ticket: String, position: Double, completed: Bool = false, state: String? = nil, metrics:[String:Double] = [:]) async {
        let _: Empty? = try? await request("/session/\(ticket)", method: "POST", body: ["position": max(0, position.isFinite ? position : 0), "completed": completed, "state": state ?? "unknown", "metrics":metrics])
    }
    func previewSceneCalibration(hue:Double)async throws {
        let _:Empty=try await request("/scene-light/calibration",method:"POST",body:["hue":hue])
    }
    func endSceneCalibration()async {
        let _:Empty?=try? await request("/scene-light/calibration",method:"DELETE")
    }
    func sceneColour(ticket:String,colour:SceneColour,options:SceneLightingOptions = .init())async {
        let _:Empty?=try? await request("/scene-light",method:"POST",body:["ticket":ticket,"hue":colour.hue,"white":colour.saturation==0,"saturation":options.matchSaturation ? colour.saturation : options.saturation,"brightness":options.matchBrightness ? (colour.brightness<3 ? 0 : colour.brightness) : -1,"transition":options.fade])
    }
    func stopSceneLighting(ticket:String)async {
        let _:Empty?=try? await request("/scene-light",method:"DELETE",body:["ticket":ticket])
    }
    func release(ticket: String) async { let _: Empty? = try? await request("/session/\(ticket)", method: "DELETE") }
}
struct Empty: Decodable {}
