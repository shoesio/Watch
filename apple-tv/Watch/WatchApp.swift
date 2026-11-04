import SwiftUI
import AVFoundation

@main struct WatchApp: App {
    @StateObject private var library = LibraryStore()
    init() {
        do {try UHDIdentityVault.importStagedSetup();UHDIdentityVault.diagnostic("startup")} catch {UHDIdentityVault.diagnostic("setup-failed",error:error)}
        try? AVAudioSession.sharedInstance().setCategory(.playback, mode: .moviePlayback); try? AVAudioSession.sharedInstance().setActive(true) }
    var body: some Scene {
        WindowGroup {
            RootView().environmentObject(library).tint(.white).preferredColorScheme(.dark)
                .onOpenURL { url in
                    guard url.scheme == "homewatch", let parts = URLComponents(url: url, resolvingAgainstBaseURL: false) else { return }
                    if url.host == "pair", let code=parts.queryItems?.first(where:{$0.name=="code"})?.value { Task { await library.pair(code) } }
                    if url.host == "play",let id=parts.queryItems?.first(where:{$0.name=="episode"})?.value {
                        let position=Double(parts.queryItems?.first(where:{$0.name=="position"})?.value ?? "")
                        Task { await library.openEpisode(id,position:position) }
                    }
                    if url.host == "browse",let section=parts.queryItems?.first(where:{$0.name=="section"})?.value,let tab=AppTab(rawValue:section) { library.tab=tab }
                    if url.host == "show",let id=parts.queryItems?.first(where:{$0.name=="programme"})?.value {
                        library.tab = .shows
                        library.routeProgrammeID=id
                    }
                    if url.host == "search" {
                        library.searchQuery=parts.queryItems?.first(where:{$0.name=="q"})?.value ?? ""
                        library.tab = .search
                    }
                }
        }
    }
}

enum AppTab:String { case home,shows,films,live,search,settings }

@MainActor final class LibraryStore: ObservableObject {
    let api = WatchAPI()
    @Published var programmes: [Programme] = []
    @Published var connected = false
    @Published var loading = false
    @Published var error: String?
    @Published var lastUpdated: Date?
    @Published var deepPlay: PlaybackSelection?
    @Published var tab:AppTab = .home
    @Published var searchQuery=""
    @Published var routeProgrammeID:String?
    @Published var recommendations:[Programme]=[]
    @Published var recommendationCursor:String?
    private var loadingRecommendations=false
    private var recommendationGeneration=UUID()
    @Published var hot:[Programme]=[]
    @Published var featuredFilms:[Programme]=[]
    @Published var featuredShows:[Programme]=[]
    init() { connected = api.token != nil }
    func refresh() async {
        guard api.token != nil else { connected = false; return }
        guard !loading else { return }
        loading = true; defer { loading = false }
        do {
            let previews=programmes.filter { $0.discoveryRef != nil }
            programmes = try await api.library()
            merge(previews)
            connected = true; lastUpdated = Date(); error = nil
            if let discovery=try? await api.discover() {
                recommendations=discovery.programmes;recommendationCursor=discovery.nextCursor;recommendationGeneration=UUID();hot=discovery.hot ?? [];featuredFilms=discovery.featuredFilms ?? [];featuredShows=discovery.featuredShows ?? []
                merge(recommendations+hot)
            }
        }
        catch { if api.token == nil { connected = false }; self.error = error.localizedDescription }
    }
    func moreRecommendations() async {
        guard !loadingRecommendations,let cursor=recommendationCursor else { return }
        let generation=recommendationGeneration;loadingRecommendations=true
        defer { loadingRecommendations=false }
        do {
            let response=try await api.discover(cursor:cursor)
            guard generation==recommendationGeneration else { return }
            let known=Set(recommendations.map(\.id))
            recommendations.append(contentsOf:response.programmes.filter { !known.contains($0.id) })
            recommendationCursor=response.nextCursor;merge(response.programmes)
        } catch { /* Keep the loaded row; a later appearance retries without losing position. */ }
    }
    func merge(_ incoming:[Programme]) {
        for item in incoming {
            if let index=programmes.firstIndex(where:{$0.id==item.id}) {
                if item.discoveryRef == nil || programmes[index].discoveryRef != nil { programmes[index]=item }
            } else { programmes.append(item) }
        }
    }
    func setFavourite(_ programme:Programme,value:Bool) async throws {
        let target=try await resolve(programme)
        let updated=try await api.favourite(id:target.id,value:value)
        let previews=programmes.filter { $0.discoveryRef != nil }
        programmes=updated;merge(previews)
    }
    func resolve(_ programme:Programme) async throws -> Programme {
        guard let ref=programme.discoveryRef else { return programme }
        let imported=try await api.importProgramme(ref)
        merge([imported]);return imported
    }
    func openEpisode(_ id: String, position: Double?) async {
        // A launch URL can arrive while the initial catalogue refresh is still running.
        for _ in 0..<100 {
            if !loading { break }
            try? await Task.sleep(for: .milliseconds(100))
        }
        if programmes.isEmpty { await refresh() }
        guard let programme = programmes.first(where: { $0.episodes.contains(where: { $0.id == id }) }), let episode = programme.episodes.first(where: { $0.id == id }) else { return }
        deepPlay = PlaybackSelection(programme: programme, episode: episode, position: programme.live ? 0 : max(0, min(86400, position ?? episode.resumeSeconds ?? 0)))
    }
    func pair(_ code: String) async {
        loading = true; error = nil
        do { try await api.pair(code: code); connected = true; loading = false; await refresh() }
        catch { self.error = error.localizedDescription; loading = false }
    }
}

struct RootView:View {
    @EnvironmentObject private var library:LibraryStore
    @Environment(\.scenePhase) private var scenePhase
    var body:some View {
        GeometryReader { geometry in
            Group {
                if library.connected {
                    TabView(selection:$library.tab) {
                        BrowseView(section:.home).tabItem { Label("For you",systemImage:"house") }.tag(AppTab.home)
                        BrowseView(section:.shows).tabItem { Label { Text("Shows") } icon: { Image(systemName:"rectangle.stack").renderingMode(.template).symbolRenderingMode(.monochrome) } }.tag(AppTab.shows)
                        BrowseView(section:.films).tabItem { Label("Films",systemImage:"film") }.tag(AppTab.films)
                        BrowseView(section:.live).tabItem { Label("Live TV",systemImage:"dot.radiowaves.left.and.right") }.tag(AppTab.live)
                        SearchView().tabItem { Label("Search",systemImage:"magnifyingglass") }.tag(AppTab.search)
                        SettingsView().tabItem { Label("Settings",systemImage:"gearshape") }.tag(AppTab.settings)
                    }
                } else { PairView() }
            }
            .environment(\.watchCardWidth,WatchDesign.cardWidth(geometry.size.width))
            .environment(\.watchColumns,WatchDesign.columns(geometry.size.width))
        }.ignoresSafeArea(.container,edges:.horizontal).background(WatchDesign.canvas.ignoresSafeArea())
        .task { try? UHDIdentityVault.importStagedSetup();await library.refresh() }
        .fullScreenCover(item:$library.deepPlay,onDismiss:{ Task { await library.refresh() } }) { PlayerScreen(selection:$0).id($0.id) }
        .onChange(of:scenePhase) { _,phase in if phase == .active { Task { await library.refresh() } } }
    }
}

struct PairView:View {
    @EnvironmentObject private var library:LibraryStore
    @State private var code=""
    @AppStorage("server") private var server="http://192.168.0.146:8115"
    var body:some View {
        ZStack {
            LinearGradient(colors:[Color(red:0.045,green:0.09,blue:0.14),WatchDesign.canvas],startPoint:.topLeading,endPoint:.bottomTrailing).ignoresSafeArea()
            VStack(spacing:24) {
                Image(systemName:"play.rectangle").font(.system(size:64,weight:.ultraLight)).foregroundStyle(.white.opacity(0.8)).padding(.bottom,10)
                Text("Connect your library").font(.system(size:40,weight:.semibold))
                Text("Your favourite television, ready on Apple TV.").font(WatchDesign.body).foregroundStyle(WatchDesign.muted)
                VStack(alignment:.leading,spacing:18) {
                    Text("Home library address").font(WatchDesign.detail).foregroundStyle(WatchDesign.muted)
                    TextField("Pi address",text:$server).font(.system(size:25)).textInputAutocapitalization(.never).autocorrectionDisabled()
                    Text("Pairing code").font(WatchDesign.detail).foregroundStyle(WatchDesign.muted).padding(.top,5)
                    TextField("8-digit code",text:$code).keyboardType(.numberPad).font(.system(size:28,weight:.medium,design:.monospaced))
                }.frame(width:640).padding(.top,16)
                Button { Task { await library.pair(code) } } label:{
                    HStack(spacing:14) { if library.loading { ProgressView() };Text(library.loading ? "Connecting…" : "Connect").font(.system(size:25,weight:.semibold)) }
                }.buttonStyle(.borderedProminent).disabled(code.filter(\.isNumber).count != 8 || library.loading).padding(.top,8)
                Text("Open Pair Apple TV on your Mac for a one-time code.").font(WatchDesign.detail).foregroundStyle(WatchDesign.muted)
                if let error=library.error { Text(error).font(WatchDesign.detail).foregroundStyle(.orange).multilineTextAlignment(.center).frame(maxWidth:760) }
            }.padding(50)
        }
    }
}

enum SettingsProvider:String,CaseIterable,Identifiable {
    case bbc,channel4,itv,u,channel5
    var id:String {rawValue}
    var title:String {
        switch self {case .bbc:return "BBC iPlayer";case .channel4:return "Channel 4";case .itv:return "ITVX";case .u:return "U";case .channel5:return "Channel 5"}
    }
    var localAccount:Bool {self == .itv || self == .u || self == .channel5}
}

struct SettingsView:View {
    @EnvironmentObject private var library:LibraryStore
    @AppStorage("watch.autoplayNext") private var autoplayNext=false
    @State private var connected:Set<SettingsProvider>=[]
    var body:some View {
        NavigationStack {
            ScrollView {
                VStack(alignment:.leading,spacing:28) {
                    Text("Settings").font(.system(size:42,weight:.bold)).padding(.bottom,8)
                    Text("Accounts").font(WatchDesign.heading)
                    VStack(spacing:10) {
                        ForEach(SettingsProvider.allCases) {provider in
                            NavigationLink {
                                ProviderSettingsPage(provider:provider)
                            } label: {
                                HStack(spacing:24) {
                                    Artwork(source:brand(provider),fit:true,maxPixel:200).frame(width:88,height:46)
                                    Text(provider.title).font(.system(size:26,weight:.medium))
                                    Spacer()
                                    Text(provider.localAccount ? (connected.contains(provider) ? "Connected" : "Not connected") : "Managed on Pi")
                                        .font(WatchDesign.detail).opacity(0.65)
                                    Image(systemName:"chevron.right").font(.system(size:19,weight:.semibold)).opacity(0.5)
                                }.frame(maxWidth:.infinity,minHeight:56)
                            }.buttonStyle(WatchActionButtonStyle()).focusEffectDisabled()
                        }
                    }
                    Text("Playback").font(WatchDesign.heading).padding(.top,12)
                    Toggle(isOn:$autoplayNext) {
                        VStack(alignment:.leading,spacing:6) {
                            Text("Autoplay next episode").font(.system(size:26,weight:.medium))
                            Text("A ten-second countdown lets you cancel.").font(WatchDesign.detail).foregroundStyle(WatchDesign.muted)
                        }
                    }.padding(24).background(.white.opacity(0.055),in:RoundedRectangle(cornerRadius:18))
                    NavigationLink { HostSettingsPage() } label: {
                        HStack {Label("Library connection",systemImage:"network");Spacer();Image(systemName:"chevron.right")}.font(WatchDesign.body).frame(maxWidth:.infinity)
                    }.buttonStyle(WatchActionButtonStyle()).focusEffectDisabled().padding(.top,12)
                }.frame(maxWidth:1160).padding(.horizontal,WatchDesign.inset).padding(.top,38).padding(.bottom,72).frame(maxWidth:.infinity)
            }.background(WatchDesign.canvas)
            .task {
                var accounts=Set<SettingsProvider>()
                if (try? await ITVAccountService.shared.isSignedIn()) == true {accounts.insert(.itv)}
                if (try? await UAccountService.shared.isSignedIn()) == true {accounts.insert(.u)}
                if (try? await Channel5AccountService.shared.isSignedIn()) == true {accounts.insert(.channel5)}
                connected=accounts
            }
        }
    }
    private func brand(_ provider:SettingsProvider)->String? {
        library.programmes.flatMap(\.brands).first {$0.id==provider.rawValue}?.image
            ?? "http://192.168.0.146:8109/static/artwork/brands/\(provider.rawValue).png"
    }
}

private struct ProviderSettingsPage:View {
    let provider:SettingsProvider
    var body:some View {
        ScrollView {
            VStack(alignment:.leading,spacing:28) {
                switch provider {
                case .itv:ProviderSignIn(provider:.itv)
                case .u:ProviderSignIn(provider:.u)
                case .channel5:Channel5SignIn()
                case .bbc,.channel4:
                    VStack(alignment:.leading,spacing:22) {
                        Text(provider.title).font(.system(size:36,weight:.semibold))
                        Label("Managed on your Pi",systemImage:"network").font(WatchDesign.body)
                        Text(provider == .bbc ? "BBC programmes play directly on this Apple TV. UHD is attempted automatically when this device is configured and BBC offers a compatible stream." : "Channel 4 on-demand uses the Pi connection. Live channels play directly on Apple TV. QR sign-in for Watch is not available yet.")
                            .font(WatchDesign.body).foregroundStyle(WatchDesign.muted).fixedSize(horizontal:false,vertical:true)
                    }.padding(32).frame(maxWidth:.infinity,alignment:.leading).background(.white.opacity(0.045),in:RoundedRectangle(cornerRadius:22))
                }
            }.frame(maxWidth:1080).padding(WatchDesign.inset).frame(maxWidth:.infinity)
        }.background(WatchDesign.canvas)
    }
}

private struct HostSettingsPage:View {
    @EnvironmentObject private var library:LibraryStore
    @State private var confirm=false
    var body:some View {
        ScrollView {
            VStack(alignment:.leading,spacing:28) {
                Text("Library connection").font(.system(size:36,weight:.semibold))
                Label(library.error == nil ? "Connected to your Pi" : "Waiting for your Pi",systemImage:library.error == nil ? "checkmark.circle" : "wifi.exclamationmark").font(WatchDesign.body)
                Text(library.api.base).font(WatchDesign.detail).foregroundStyle(WatchDesign.muted)
                Button("Disconnect this Apple TV",role:.destructive) {confirm=true}
                    .buttonStyle(WatchActionButtonStyle()).focusEffectDisabled()
                    .confirmationDialog("Disconnect this Apple TV?",isPresented:$confirm) {
                        Button("Disconnect",role:.destructive) {try? PairingStore.save(nil);library.api.token=nil;library.connected=false}
                        Button("Cancel",role:.cancel) {}
                    }
                Divider().padding(.vertical,12)
                Image("tmdb").resizable().scaledToFit().frame(width:120,height:30)
                Text("This product uses the TMDB API but is not endorsed or certified by TMDB.").font(.system(size:17)).foregroundStyle(WatchDesign.muted)
            }.frame(maxWidth:1080,alignment:.leading).padding(WatchDesign.inset).frame(maxWidth:.infinity)
        }.background(WatchDesign.canvas)
    }
}
