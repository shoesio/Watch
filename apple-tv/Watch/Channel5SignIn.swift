import SwiftUI
import CoreImage.CIFilterBuiltins

@MainActor final class Channel5Login: ObservableObject {
    @Published var signedIn=false
    @Published var pairing:Channel5Pairing?
    @Published var error:String?
    @Published var busy=false
    private var task:Task<Void,Never>?
    func load() async { signedIn=(try? await Channel5AccountService.shared.isSignedIn()) ?? false }
    func start() {
        cancel();busy=true;error=nil
        task=Task {
            defer { busy=false }
            do {
                let value=try await Channel5AccountService.shared.newCode()
                pairing=value
                while !Task.isCancelled {
                    try await Task.sleep(for:.seconds(3))
                    if try await Channel5AccountService.shared.check(value) {
                        signedIn=true;pairing=nil;return
                    }
                }
            } catch is CancellationError { }
            catch { if !Task.isCancelled { self.error=error.localizedDescription } }
        }
    }
    func cancel() {
        task?.cancel();task=nil
        if let pairing { Task { await Channel5AccountService.shared.cancel(pairing) } }
        pairing=nil;busy=false
    }
    func signOut() {
        cancel();Task { do { try await Channel5AccountService.shared.signOut();signedIn=false } catch { self.error=error.localizedDescription } }
    }
}

struct Channel5SignIn:View {
    @StateObject private var login=Channel5Login()
    var onConnected:(()->Void)?
    private func qr(_ value:String)->UIImage? {
        let filter=CIFilter.qrCodeGenerator();filter.message=Data(value.utf8)
        guard let output=filter.outputImage,let cg=CIContext().createCGImage(output.transformed(by:CGAffineTransform(scaleX:8,y:8)),from:output.extent.applying(CGAffineTransform(scaleX:8,y:8))) else { return nil }
        return UIImage(cgImage:cg)
    }
    var body:some View {
        VStack(alignment:.leading,spacing:24) {
            Text("Channel 5").font(.system(size:32,weight:.semibold))
            if login.signedIn {
                Label("Connected for direct playback",systemImage:"checkmark.circle.fill").foregroundStyle(.green)
                if onConnected != nil { Button("Watch now") { onConnected?() } }
                Button("Sign out of Channel 5",role:.destructive) { login.signOut() }
            } else if let pairing=login.pairing {
                HStack(spacing:36) {
                    if let image=qr(pairing.activationURL.absoluteString) {
                        Image(uiImage:image).interpolation(.none).resizable().scaledToFit().frame(width:220,height:220).padding(18).background(.white,in:RoundedRectangle(cornerRadius:14))
                    }
                    VStack(alignment:.leading,spacing:16) {
                        Text("Scan to sign in on your phone").font(.system(size:29,weight:.semibold))
                        Text("Or visit activate.channel5.com and enter").font(.system(size:23))
                        Text(pairing.pin).font(.system(size:48,weight:.semibold,design:.monospaced)).tracking(6)
                        Text("Waiting for Channel 5…").font(.system(size:22)).foregroundStyle(.white.opacity(0.65))
                    }
                }
                Button("Get a new code") { login.start() }
            } else {
                Text("Watch live channels and on-demand programmes directly on Apple TV. Your Channel 5 sign-in is saved in this Apple TV’s Keychain.").font(.system(size:23)).foregroundStyle(.white.opacity(0.75)).fixedSize(horizontal:false,vertical:true)
                if login.busy { ProgressView() } else { Button("Connect Channel 5") { login.start() } }
            }
            if let error=login.error { Text(error).font(.system(size:23)).foregroundStyle(.orange);Button("Try again") { login.start() } }
        }.padding(30).frame(maxWidth:.infinity,alignment:.leading).background(.white.opacity(0.045),in:RoundedRectangle(cornerRadius:22))
        .task { await login.load() }
        .onChange(of:login.signedIn) { _,value in if value { onConnected?() } }
        .onDisappear { login.cancel() }
    }
}
