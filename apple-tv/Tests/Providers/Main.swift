import Foundation

func check(_ value:@autoclosure ()->Bool,_ message:String) {if !value() {fatalError(message)}}
func rejects(_ action:()throws->Void) {do {try action();fatalError("Expected rejection")}catch{}}
final class Memory:@unchecked Sendable {
 let lock=NSLock();private var value:ITVCredentials?
 func get()->ITVCredentials? {lock.lock();defer{lock.unlock()};return value}
 func put(_ item:ITVCredentials) {lock.lock();value=item;lock.unlock()}
 func remove() {lock.lock();value=nil;lock.unlock()}
}
@main struct Tests {
 static func main() async throws {
  let now=Date();let credentials=try ITVCredentials.parse(Data("{\"access_token\":\"test-access\",\"refresh_token\":\"test-refresh\",\"expires_in\":3600}".utf8),now:now)
  check(credentials.expiresAt>now,"ITV expiry")
  rejects {_ = try ITVCredentials.parse(Data("{}".utf8))}
  rejects {_ = try ITVLiveAPI.endpoint(URL(string:"https://evil.test/playlist/itvonline/ITV")!)}
  rejects {_ = try ITVLiveAPI.endpoint(URL(string:"https://simulcast.itv.com/playlist/itvonline/ITV?token=bad")!)}
  let endpoint=try ITVLiveAPI.endpoint(URL(string:"https://simulcast.itv.com/playlist/itvonline/ITV")!,channelID:"itv");check(endpoint.host == "simulcast.itv.com","ITV endpoint")
  let memory=Memory();let vault=ITVAccountVault(read:{memory.get()},write:{memory.put($0)},remove:{memory.remove()})
  let service=ITVAccountService(transport:{ request in
   let path=request.url!.path
   if path=="/generate/code" {return ITVHTTPResponse(data:Data("{\"code\":\"123456\"}".utf8),status:200)}
   if path=="/verify/123456" {return ITVHTTPResponse(data:Data("{\"token\":\"test-refresh\"}".utf8),status:200)}
   return ITVHTTPResponse(data:Data("{\"access_token\":\"test-access\",\"refresh_token\":\"test-refresh\",\"expires_in\":3600}".utf8),status:200)
  },vault:vault)
  let code=try await service.newCode();check(code=="123456","ITV code")
  let paired=try await service.checkCode(code);check(paired,"ITV pairing completes")
  let signed=try await service.isSignedIn();check(signed,"ITV persisted")
  try await service.signOut();check(memory.get()==nil,"ITV signout")
  let u=try UPairing.parse(Data("{\"code\":\"abc12\",\"match_code\":\"11111111-1111-4111-8111-111111111111\"}".utf8),revision:UUID())
  check(u.code=="ABC12","U code normalized");check(u.activationURL.host=="u.co.uk","U provider QR destination")
  rejects {_ = try UPairing.parse(Data("{\"code\":\"../../\",\"match_code\":\"bad\"}".utf8),revision:UUID())}
  check(!UHTTP.allowed(URL(string:"https://tvlogin.uktvapi.co.uk.evil.test/get_code")!),"U host boundary")
  check(UHTTP.allowed(URL(string:"https://tvlogin.uktvapi.co.uk/get_code")!),"U activation endpoint")
  rejects {_ = try UCredentials.parse(Data("{}".utf8))}
  let response=try await ITVAccountHTTP().send(ITVAccountService.request(URL(string:"https://auth.prd.user.itv.com/generate/code")!))
  check(response.status==200,"Live ITV code endpoint")
  let uresponse=try await UHTTP.shared.send(URL(string:"https://tvlogin.uktvapi.co.uk/get_code")!)
  check(uresponse.status==200,"Live U code endpoint")
  print("Provider account parsing, pairing, sign-out, boundary and live code checks passed (no codes or credentials printed)")
 }
}
