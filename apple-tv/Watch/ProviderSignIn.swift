import SwiftUI
import CoreImage.CIFilterBuiltins

enum SignInProvider:String,Identifiable {
    case itv,u
    var id:String { rawValue }
    var title:String { self == .itv ? "ITVX" : "U" }
    var website:String { self == .itv ? "itv.com/pair" : "u.co.uk/activate" }
}
@MainActor final class ProviderLogin:ObservableObject {
    let provider:SignInProvider
    @Published var signedIn=false
    @Published var code:String?
    @Published var activationURL:String?
    @Published var error:String?
    @Published var busy=false
    private var task:Task<Void,Never>?
    private var pairing:UPairing?
    private var generation=UUID()
    init(_ provider:SignInProvider) { self.provider=provider }
    func load() async {
        do { signedIn = provider == .itv ? try await ITVAccountService.shared.isSignedIn() : try await UAccountService.shared.isSignedIn() }
        catch { self.error=error.localizedDescription }
    }
    func start() {
        cancel();let mine=generation;busy=true;error=nil
        task=Task {
            defer { if generation==mine {busy=false} }
            do {
                let expiry:Date
                if provider == .itv {
                    let value=try await ITVAccountService.shared.newCode();try Task.checkCancellation()
                    code=value;activationURL="https://www.itv.com/watch/pair?loginCode="+value;expiry=Date().addingTimeInterval(3600)
                } else {
                    let value=try await UAccountService.shared.newCode();try Task.checkCancellation()
                    pairing=value;code=value.code;activationURL=value.activationURL.absoluteString;expiry=value.expiresAt
                }
                var failures=0
                while Date()<expiry {
                    try await Task.sleep(for:.seconds(5))
                    do {
                        let connected:Bool
                        if provider == .itv { connected=try await ITVAccountService.shared.checkCode(code!) }
                        else { connected=try await UAccountService.shared.check(pairing!) }
                        try Task.checkCancellation();guard generation==mine else {return}
                        if connected { signedIn=true;code=nil;activationURL=nil;return }
                        failures=0
                    } catch is CancellationError { throw CancellationError() }
                    catch {failures += 1;if failures>=3 {throw error} }
                }
                throw WatchError(message:"This sign-in code has expired. Get a new code.")
            } catch is CancellationError {} catch {if generation==mine {self.error=error.localizedDescription}}
        }
    }
    func cancel() {
        generation=UUID();task?.cancel();task=nil;code=nil;activationURL=nil;busy=false
        if let pairing {Task {await UAccountService.shared.cancel(pairing)}};pairing=nil
    }
    func signOut() {
        cancel();Task {
            do {if provider == .itv {try await ITVAccountService.shared.signOut()} else {try await UAccountService.shared.signOut()};signedIn=false}
            catch {self.error=error.localizedDescription}
        }
    }
}
struct ProviderSignIn:View {
    let provider:SignInProvider
    var onConnected:(()->Void)?
    @StateObject private var login:ProviderLogin
    init(provider:SignInProvider,onConnected:(()->Void)? = nil) {self.provider=provider;self.onConnected=onConnected;_login=StateObject(wrappedValue:ProviderLogin(provider))}
    private func qr(_ value:String)->UIImage? {
        let f=CIFilter.qrCodeGenerator();f.message=Data(value.utf8)
        guard let output=f.outputImage?.transformed(by:CGAffineTransform(scaleX:8,y:8)),let cg=CIContext().createCGImage(output,from:output.extent) else {return nil};return UIImage(cgImage:cg)
    }
    var body:some View {
        VStack(alignment:.leading,spacing:24) {
            Text(provider.title).font(.system(size:32,weight:.semibold))
            if login.signedIn {
                Label("Connected on this Apple TV",systemImage:"checkmark.circle.fill").foregroundStyle(.green)
                if onConnected != nil {Button("Watch now") {onConnected?()}}
                Button("Sign out of "+provider.title,role:.destructive) {login.signOut()}
            } else if let code=login.code,let url=login.activationURL {
                HStack(spacing:36) {
                    if let image=qr(url) {Image(uiImage:image).interpolation(.none).resizable().scaledToFit().frame(width:220,height:220).padding(18).background(.white,in:RoundedRectangle(cornerRadius:14))}
                    VStack(alignment:.leading,spacing:16) {
                        Text("Scan to sign in on your phone").font(.system(size:29,weight:.semibold))
                        Text("Or visit "+provider.website).font(.system(size:23))
                        Text(code).font(.system(size:48,weight:.semibold,design:.monospaced)).tracking(6)
                        Text("Waiting for "+provider.title+"…").font(.system(size:22)).foregroundStyle(WatchDesign.muted)
                    }
                }
                Button("Get a new code") {login.start()}
            } else {
                Text(provider == .itv ? "Connect your ITVX account for live channels. Supported free on-demand programmes play directly; ITVX Premium playback is not supported yet." : "Connect U for native on-demand playback on this Apple TV.")
                    .font(.system(size:23)).foregroundStyle(WatchDesign.muted).fixedSize(horizontal:false,vertical:true)
                if login.busy {ProgressView()} else {Button("Connect "+provider.title) {login.start()}}
            }
            if let error=login.error {Text(error).font(.system(size:23)).foregroundStyle(.orange);Button("Try again") {login.start()}}
        }.padding(30).frame(maxWidth:.infinity,alignment:.leading).background(.white.opacity(0.045),in:RoundedRectangle(cornerRadius:22))
        .task {await login.load()}.onDisappear {login.cancel()}
        .onChange(of:login.signedIn) {_,value in if value {onConnected?()}}
    }
}
