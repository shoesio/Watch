import Foundation

func expect(_ value: @autoclosure () -> Bool, _ label:String) {
    guard value() else { fatalError(label) }
}
func rejects(_ label:String,_ action:() throws -> Void) {
    do { try action();fatalError(label) } catch {}
}
expect(try! Channel5PairingResponse.session(from:Channel5Response(data:Data(),status:204)) == nil,"Waiting is not a login")
expect(try! Channel5PairingResponse.session(from:Channel5Response(data:Data("{\"sessionId\":\"test-account-session\"}".utf8),status:201)) == "test-account-session","Accept HTTP201 account session")
rejects("Reject malformed success") { _ = try Channel5PairingResponse.session(from:Channel5Response(data:Data("{}".utf8),status:201)) }
rejects("Expired code") { _ = try Channel5PairingResponse.session(from:Channel5Response(data:Data(),status:410)) }
expect(!Channel5HTTP.allowed(URL(string:"https://cassie.channel5.com.evil.test/path")!),"Service host boundary")
expect(!Channel5HTTP.allowed(URL(string:"http://cassie.channel5.com/path")!),"HTTPS required")
expect(!Channel5Wire.licenceAllowed(URL(string:"https://example.com/api/v2/licences/fairplay/a")!),"Licence host boundary")
expect(try! Channel5Wire.fairPlayContentID("skd://abc-123") == "abc-123","Native content identifier")
rejects("Reject arbitrary content identifier") { _ = try Channel5Wire.fairPlayContentID("https://example.com/a") }
rejects("Reject request injection") { _ = try Channel5Wire.fairPlayContentID("skd://abc&extra=true") }
let sample:[String:Any]=["assets":[["drm":"fairplay","keyserver":"https://cassie.channel5.com/api/v2/licences/fairplay/test","renditions":[["renditionid":1,"url":"https://example.akamaized.net/test.m3u8"]]]]]
expect(try! Channel5PlaybackAPI.fairPlay(sample).0.path == "/test.m3u8","Supported Apple stream selected")
rejects("Unsupported protected stream") { _ = try Channel5PlaybackAPI.fairPlay(["assets":[["drm":"widevine"]]]) }
print("12 native Channel 5 parsing and boundary checks passed")
