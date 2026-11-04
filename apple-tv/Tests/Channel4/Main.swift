import Foundation
@main struct Checks {
 static func main() async throws {
  for raw in ["http://www.channel4.com/simulcast/channels/C4","https://user@www.channel4.com/a","https://c4assets.com.evil.test/a","https://evil.test/a","https://www.channel4.com:444/a"] {
   precondition(!Channel4HTTP.allowed(URL(string:raw)!))
  }
  precondition(Channel4HTTP.allowed(URL(string:"https://www.channel4.com/simulcast/channels/C4")!))
  precondition(Channel4HTTP.allowed(URL(string:"https://live.c4assets.com/master.m3u8")!))
  do {_ = try await Channel4PlaybackAPI.shared.source(id:"untrusted/path",live:true);fatalError("Invalid channel accepted")}
  catch is Channel4Error { }
  print("Channel 4 native address and input checks passed")
  if CommandLine.arguments.contains("--source-probe") {
   let source=try await Channel4PlaybackAPI.shared.source(id:"C4",live:true)
   precondition(source.channel4FairPlay?.live == true)
   precondition((source.fairPlayCertificate?.count ?? 0)>0)
   let data=try await Channel4HTTP.shared.data(source.url)
   let playlist=String(decoding:data,as:UTF8.self)
   precondition(playlist.hasPrefix("#EXTM3U"))
   let variants=playlist.components(separatedBy:.newlines).filter {$0.hasPrefix("#EXT-X-STREAM-INF:")}
   print("Channel 4 native source: HLS master received; \(variants.count) adaptive renditions; FairPlay certificate received")
   for line in variants {
    if let range=line.range(of:#"RESOLUTION=[0-9]+x[0-9]+"#,options:.regularExpression) {print(String(line[range]))}
   }
  }
 }
}
