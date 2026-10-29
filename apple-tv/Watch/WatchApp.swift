import SwiftUI
import AVFoundation

@main struct WatchApp: App {
    @StateObject private var library = LibraryStore()
    init() { try? AVAudioSession.sharedInstance().setCategory(.playback, mode: .moviePlayback); try? AVAudioSession.sharedInstance().setActive(true) }
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
        .task { await library.refresh() }
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

struct SettingsView:View {
    @EnvironmentObject private var library:LibraryStore
    @State private var confirm=false
    private var shows:Int { library.programmes.filter { !$0.live && !$0.film && $0.discoveryRef == nil }.count }
    private var films:Int { library.programmes.filter { $0.film && $0.discoveryRef == nil }.count }
    private var channels:Int { library.programmes.filter(\.live).count }
    private var brands:[Brand] { var seen=Set<String>();return library.programmes.flatMap(\.brands).filter { seen.insert($0.id).inserted }.sorted { $0.name<$1.name } }
    var body:some View {
        ScrollView {
            VStack(alignment:.leading,spacing:36) {
                SectionHeading(title:"Your home library",subtitle:"Connected to the Pi. Playback stays on this Apple TV.")
                HStack(alignment:.top,spacing:36) {
                    VStack(alignment:.leading,spacing:28) {
                        Text("All together").font(.system(size:27,weight:.semibold))
                        HStack(spacing:18) {
                            statistic(shows,"Shows");statistic(films,"Films");statistic(channels,"Live channels")
                        }
                        Divider().overlay(.white.opacity(0.12))
                        Brands(items:brands)
                        HStack(spacing:10) {
                            Circle().fill(library.error == nil ? Color.green : .orange).frame(width:9,height:9)
                            Text(library.error == nil ? "Library connected" : "Waiting for the library").font(WatchDesign.body)
                        }
                        if let updated=library.lastUpdated { Text("Updated \(updated,style:.relative) ago").font(WatchDesign.detail).foregroundStyle(WatchDesign.muted) }
                    }.padding(30).frame(maxWidth:.infinity,alignment:.topLeading).background(.white.opacity(0.045),in:RoundedRectangle(cornerRadius:22))
                    VStack(alignment:.leading,spacing:25) {
                        Text("Made for this screen").font(.system(size:27,weight:.semibold))
                        Label("Native Siri Remote controls",systemImage:"appletvremote.gen4").font(WatchDesign.body)
                        Label("Continue where you left off",systemImage:"clock.arrow.circlepath").font(WatchDesign.body)
                        Label("Stream quality shown during playback",systemImage:"4k.tv").font(WatchDesign.body)
                        Divider().overlay(.white.opacity(0.12))
                        Image("tmdb").resizable().scaledToFit().frame(width:135,height:35)
                        Text("This product uses the TMDB API but is not endorsed or certified by TMDB.").font(WatchDesign.detail).foregroundStyle(WatchDesign.muted).fixedSize(horizontal:false,vertical:true)
                    }.padding(30).frame(maxWidth:.infinity,alignment:.topLeading).background(.white.opacity(0.045),in:RoundedRectangle(cornerRadius:22))
                }
                SectionHeading(title:"Provider accounts",subtitle:"Scan a code to sign in on the provider’s website. Sessions stay in this Apple TV’s Keychain.")
                ProviderSignIn(provider:.itv)
                ProviderSignIn(provider:.u)
                Channel5SignIn()
                Text("BBC iPlayer and Channel 4 use the existing Pi connections. These Apple TV sign-ins do not change provider favourites or the Pi’s saved account sessions.")
                    .font(WatchDesign.detail).foregroundStyle(WatchDesign.muted)
                HStack {
                    Text("Watch · 1.4").font(WatchDesign.detail).foregroundStyle(WatchDesign.muted)
                    Spacer()
                    Button("Disconnect this Apple TV",role:.destructive) { confirm=true }.font(.system(size:23))
                        .confirmationDialog("Disconnect this Apple TV?",isPresented:$confirm) {
                            Button("Disconnect",role:.destructive) { try? PairingStore.save(nil);library.api.token=nil;library.connected=false }
                            Button("Cancel",role:.cancel) {}
                        }
                }.padding(.top,8)
            }.padding(.horizontal,WatchDesign.inset).padding(.top,38).padding(.bottom,72)
        }.background(WatchDesign.canvas)
    }
    private func statistic(_ count:Int,_ label:String) -> some View {
        VStack(alignment:.leading,spacing:5) {
            Text(count.formatted()).font(.system(size:38,weight:.semibold,design:.rounded)).monospacedDigit()
            Text(label).font(WatchDesign.detail).foregroundStyle(WatchDesign.muted)
        }.frame(maxWidth:.infinity,alignment:.leading)
    }
}
