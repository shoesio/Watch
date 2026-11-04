import SwiftUI

enum Section:String,CaseIterable { case home="For you",shows="Shows",films="Films",live="Live TV" }
struct BrowseView:View {
    @EnvironmentObject private var library:LibraryStore
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @Environment(\.watchCardWidth) private var cardWidth
    @Environment(\.watchColumns) private var columnCount
    let section:Section
    private enum BrowseFocus:Hashable {case filter,programme(String)}
    @FocusState private var browseFocus:BrowseFocus?
    @State private var genre="All genres"
    @State private var path:[String]=[]
    @State private var genreSuggestions:[Programme]=[]
    @State private var personalShows:[Programme]=[]
    @State private var genreOrder:[String]=[]
    @State private var loadingSuggestions=false
    @State private var suggestionError=false
    @State private var nextSuggestionCursor:String?
    @State private var suggestionTotal=0
    @State private var suggestionGeneration=UUID()
    private var columns:[GridItem] { Array(repeating:GridItem(.fixed(cardWidth),spacing:WatchDesign.gap,alignment:.topLeading),count:columnCount) }
    private var items:[Programme] {
        let result=library.programmes.filter { p in
            guard p.discoveryRef == nil else { return false }
            switch section {
            case .home:return !p.live && (p.recent || p.favourite)
            case .shows:return !p.live && !p.film
            case .films:return p.film && !p.live
            case .live:return p.live
            }
        }
        return section == .films ? result.sorted { ($0.filmRank ?? Int.max) < ($1.filmRank ?? Int.max) } : result
    }
    private var favouritesOnly:Bool { genre == "Favourites" }
    private var uhdOnly:Bool { genre == "UHD" }
    private var collectionOnly:Bool { favouritesOnly || uhdOnly }
    private var filtered:[Programme] {
        if favouritesOnly { return items.filter(\.favourite) }
        if uhdOnly {return items.filter {$0.uhdAvailable == true}}
        return genre == "All genres" ? items : items.filter { $0.genres.contains(genre) }
    }
    private var genres:[String] {
        let available=Set(items.flatMap(\.genres))
        if section == .shows && !genreOrder.isEmpty { return genreOrder.filter { available.contains($0) } }
        return Array(available).sorted()
    }
    private var hero:Programme? { items.sorted { $0.latestProgress > $1.latestProgress }.first }
    var body:some View {
        NavigationStack(path:$path) {
            WatchContentViewport {availableWidth in
            let columns=WatchDesign.gridColumns(availableWidth)
            ScrollView {
                VStack(alignment:.leading,spacing:32) {
                    if section == .home {
                        if !library.featuredShows.isEmpty {
                            FeaturedSpotlight(programmes:library.featuredShows,tab:.home) { play($0) }
                        } else if let hero { Hero(programme:hero,details:false) { play(hero) } }
                    }
                    if library.error != nil {
                        Label("The Pi is taking a moment. Your last library is still available.",systemImage:"wifi.exclamationmark")
                            .font(WatchDesign.detail).foregroundStyle(.orange.opacity(0.9)).padding(.horizontal,WatchDesign.inset)
                    }
                    if section == .home {
                        let continuing=items.filter { $0.resume != nil }.sorted { $0.latestProgress > $1.latestProgress }
                        if !continuing.isEmpty { rail("Continue watching",programmes:continuing) }
                        if !library.recommendations.isEmpty { rail("Picked for you",programmes:library.recommendations) }
                        if !library.hot.isEmpty { rail("Hot now",programmes:library.hot) }
                        let favourites=items.filter(\.favourite)
                        if !favourites.isEmpty { rail("Your favourites",programmes:favourites) }
                        let recent=items.filter(\.recent).sorted { $0.latestProgress > $1.latestProgress }
                        if !recent.isEmpty { rail("Recently watched",programmes:recent) }
                        let live=library.programmes.filter(\.live)
                        if !live.isEmpty { rail("Live now",programmes:live) }
                        if hero == nil && !library.loading {
                            QuietState(symbol:"heart",title:"Make yourself at home",message:"Favourite a show in your provider accounts and it will appear here after the next sync.")
                        }
                    } else {
                        if section == .films,genre == "All genres",!library.featuredFilms.isEmpty {
                            FeaturedSpotlight(programmes:library.featuredFilms,tab:.films) { play($0) }
                        }
                        HStack(alignment:.center,spacing:32) {
                            SectionHeading(title:section.rawValue,subtitle:uhdOnly ? "\(filtered.count) with UHD episodes available" : favouritesOnly ? "\(filtered.count) favourite\(filtered.count == 1 ? "" : "s")" : section == .live ? "On now and coming up" : (section == .shows ? "Recently watched and favourites first" : "\(filtered.count) films in your library"))
                            Spacer(minLength:30)
                            if section == .shows || section == .films {
                                Menu {
                                    Picker("Collection",selection:$genre) {
                                        Text("All genres").tag("All genres")
                                        Label("Favourites",systemImage:"heart.fill").tag("Favourites")
                                        Label("UHD",systemImage:"4k.tv").tag("UHD")
                                        ForEach(genres,id:\.self) { Text($0).tag($0) }
                                    }
                                } label: {
                                    Label(genre,systemImage:favouritesOnly ? "heart.fill" : "line.3.horizontal.decrease").font(.system(size:23,weight:.medium)).lineLimit(1)
                                }.focused($browseFocus,equals:.filter)
                                .onMoveCommand {direction in
                                    if direction == .down,let first=(section == .shows && !collectionOnly ? personalShows.first ?? genreSuggestions.first : filtered.first) {browseFocus = .programme(first.id)}
                                }
                                .accessibilityLabel("Filter \(section.rawValue) collection: \(genre)")
                            }
                        }.padding(.horizontal,WatchDesign.inset).focusSection()
                        if section == .shows && !collectionOnly {
                            if !personalShows.isEmpty {
                                LazyVGrid(columns:columns,alignment:.leading,spacing:40) {
                                    ForEach(Array(personalShows.enumerated()),id:\.element.id) { index,programme in gridTile(programme,topRow:index<columns.count) }
                                }.padding(.horizontal,WatchDesign.inset).padding(.top,12)
                            }
                        } else {
                            LazyVGrid(columns:columns,alignment:.leading,spacing:40) {
                                ForEach(Array(filtered.enumerated()),id:\.element.id) { index,programme in gridTile(programme,topRow:index<columns.count) }
                            }.padding(.horizontal,WatchDesign.inset).padding(.top,12)
                        }
                        if section == .shows && !collectionOnly {
                            VStack(alignment:.leading,spacing:24) {
                                HStack {
                                    SectionHeading(title:personalShows.isEmpty ? "Explore shows" : "More to explore",subtitle:"Ranked for your viewing")
                                    Spacer()
                                    if loadingSuggestions { ProgressView() }
                                }
                                LazyVGrid(columns:columns,alignment:.leading,spacing:40) {
                                    ForEach(Array(genreSuggestions.enumerated()),id:\.element.id) { index,programme in
                                        gridTile(programme,topRow:personalShows.isEmpty && index<columns.count).onAppear {
                                            if index>=genreSuggestions.count-8,nextSuggestionCursor != nil {
                                                Task { await fetchSuggestions(genre,generation:suggestionGeneration) }
                                            }
                                        }
                                    }
                                }.padding(.top,10)
                                if suggestionError {
                                    Button("Retry loading more suggestions") { Task { await fetchSuggestions(genre,generation:suggestionGeneration) } }.font(WatchDesign.detail)
                                } else if !loadingSuggestions && nextSuggestionCursor == nil && !genreSuggestions.isEmpty {
                                    Text("All \(genreSuggestions.count) suggestions shown").font(WatchDesign.detail).foregroundStyle(WatchDesign.muted)
                                }
                            }.padding(.horizontal,WatchDesign.inset).padding(.top,16)
                        }
                        if filtered.isEmpty && !library.loading && (section != .shows || collectionOnly) {
                            QuietState(symbol:favouritesOnly ? "heart" : "line.3.horizontal.decrease",title:uhdOnly ? "No UHD titles available" : favouritesOnly ? "No favourites yet" : "Nothing in this collection yet",message:uhdOnly ? "Titles appear here when the provider lists an available UHD edition. UHD availability may vary by episode." : favouritesOnly ? "Choose Favourite on a \(section == .films ? "film" : "show") to save it here." : "Choose another genre or add favourites in your provider accounts.")
                        }
                    }
                    if library.loading && library.programmes.isEmpty {
                        QuietState(symbol:"tv",title:"Getting your library ready",message:"Your shows, films and live channels will appear here shortly.")
                        ProgressView().frame(maxWidth:.infinity)
                    }
                }.padding(.top,section == .home || section == .films ? 0 : 38).padding(.bottom,72)
            }.contentMargins(.horizontal,0,for:.scrollContent).background(WatchDesign.canvas)
            .navigationDestination(for:String.self) { id in
                if let programme=library.programmes.first(where:{$0.id==id}) { ProgrammeDestination(programme:programme) }
            }
            .task { await library.refresh(); applyRoute() }
            .onChange(of:library.routeProgrammeID) { _,_ in applyRoute() }
            .onChange(of:library.tab) { _,tab in applyRoute();if section == .shows && tab == .shows && path.isEmpty { Task { await reloadShows() } } }
            .onChange(of:path) { old,new in if !old.isEmpty && new.isEmpty { library.routeProgrammeID=nil;if section == .shows { Task { await reloadShows() } } } }
            .task(id:genre) { await reloadShows() }
            .animation(reduceMotion ? nil : .easeInOut(duration:0.2),value:genre)
            }
        }
    }
    @MainActor private func reloadShows() async {
        guard section == .shows else { return }
        genreSuggestions=[];personalShows=[];suggestionError=false;nextSuggestionCursor=nil;suggestionTotal=0
        suggestionGeneration=UUID();loadingSuggestions=false
        guard !collectionOnly else { return }
        await fetchSuggestions(genre,generation:suggestionGeneration)
    }
    @MainActor private func fetchSuggestions(_ selected:String,generation:UUID) async {
        guard selected != "Favourites",selected != "UHD",!loadingSuggestions,generation==suggestionGeneration,selected==genre else { return }
        loadingSuggestions=true;suggestionError=false
        do {
            let result=try await library.api.shows(genre:selected == "All genres" ? nil : selected,cursor:nextSuggestionCursor)
            try Task.checkCancellation()
            guard generation==suggestionGeneration,selected==genre else { return }
            if let personal=result.personal { personalShows=personal;library.merge(personal) }
            if let order=result.genres { genreOrder=order }
            let known=Set(genreSuggestions.map(\.id)+personalShows.map(\.id))
            genreSuggestions.append(contentsOf:result.programmes.filter { !known.contains($0.id) })
            nextSuggestionCursor=result.nextCursor;suggestionTotal=result.total ?? genreSuggestions.count
            library.merge(result.programmes);loadingSuggestions=false
        } catch {
            guard generation==suggestionGeneration,selected==genre else { return }
            loadingSuggestions=false
            if !Task.isCancelled {
                if error.localizedDescription.lowercased().contains("expired") { nextSuggestionCursor=nil;genreSuggestions=[] }
                suggestionError=true
            }
        }
    }
    private func applyRoute() {
        guard section == .shows,library.tab == .shows,let id=library.routeProgrammeID else { return }
        if path != [id] { path=[id] }
    }
    private func play(_ programme:Programme) {
        if let episode=programme.preferred { library.deepPlay=PlaybackSelection(programme:programme,episode:episode,position:programme.live ? 0 : episode.resumeSeconds ?? 0) }
    }
    private func gridTile(_ programme:Programme,topRow:Bool)->some View {
        tileLink(programme).focused($browseFocus,equals:.programme(programme.id))
            .onMoveCommand {direction in
                if direction == .up,topRow,section == .shows || section == .films {browseFocus = .filter}
            }
    }
    @ViewBuilder private func tileLink(_ programme:Programme) -> some View {
        if programme.live { Button { play(programme) } label:{ Tile(programme:programme) }.buttonStyle(WatchCardButtonStyle()).focusEffectDisabled() }
        else { NavigationLink(value:programme.id) { Tile(programme:programme) }.buttonStyle(WatchCardButtonStyle()).focusEffectDisabled()
            .contextMenu { FavouriteButton(programme:programme) }
        }
    }
    private func rail(_ title:String,programmes:[Programme]) -> some View {
        VStack(alignment:.leading,spacing:12) {
            SectionHeading(title:title).padding(.horizontal,WatchDesign.inset)
            ScrollView(.horizontal) {
                LazyHStack(alignment:.top,spacing:WatchDesign.gap) {
                    ForEach(Array(programmes.enumerated()),id:\.element.id) { index,programme in
                        tileLink(programme).onAppear {
                            if title == "Picked for you",index>=programmes.count-8 {
                                Task { await library.moreRecommendations() }
                            }
                        }
                    }
                }.scrollTargetLayout().padding(.horizontal,WatchDesign.inset).padding(.vertical,24)
            }.contentMargins(.horizontal,0,for:.scrollContent).scrollTargetBehavior(.viewAligned).scrollClipDisabled().focusSection()
        }
    }
}

struct FeaturedSpotlight:View {
    @EnvironmentObject private var library:LibraryStore
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @Environment(\.scenePhase) private var scenePhase
    let programmes:[Programme]
    let tab:AppTab
    let play:(Programme)->Void
    @State private var index=0
    @State private var heroFocused=false
    @State private var visible=false
    @State private var lastChange=Date()
    private var current:Programme { programmes[min(index,programmes.count-1)] }
    var body:some View {
        Hero(programme:current,focusChanged:{ heroFocused=$0;lastChange=Date() },previous:{ advance(-1) },next:{ advance(1) },featurePosition:"\(min(index+1,programmes.count)) / \(programmes.count)") { play(current) }
        .onAppear { visible=true;lastChange=Date() }.onDisappear { visible=false }
        .onChange(of:programmes.map(\.id)) { _,_ in index=0;lastChange=Date() }
        .task {
            while !Task.isCancelled {
                do { try await Task.sleep(for:.seconds(1)) } catch { return }
                guard visible,scenePhase == .active,library.tab == tab,library.deepPlay == nil,!heroFocused,!reduceMotion,programmes.count>1 else { continue }
                if Date().timeIntervalSince(lastChange)>=18 { advance(1) }
            }
        }
        .animation(reduceMotion ? nil : .easeInOut(duration:0.45),value:index)
    }
    private func advance(_ direction:Int) {
        guard !programmes.isEmpty else { return }
        index=(index+direction+programmes.count)%programmes.count;lastChange=Date()
    }
}

struct Hero:View {
    @EnvironmentObject private var library:LibraryStore
    let programme:Programme
    var details=false
    var focusChanged:((Bool)->Void)?=nil
    @FocusState private var heroFocus:HeroControl?
    private enum HeroControl:Hashable { case play,details,previous,next }
    var previous:(()->Void)?=nil
    var next:(()->Void)?=nil
    var featurePosition:String?=nil
    var play:()->Void
    var body:some View {
        ZStack(alignment:.leading) {
            HeroArtwork(source:programme.hero,height:WatchDesign.heroHeight)
            VStack(alignment:.leading,spacing:12) {
                ProgrammeTitle(programme:programme,width:520,height:100,maxLogoHeight:programme.film ? 180 : 200,reserveHeadroom:false,providerEyebrow:true,rating:programme.contentRating)
                if programme.film {
                    Text([programme.preferred?.durationText,programme.genres.first].compactMap{$0}.joined(separator:" · "))
                        .font(WatchDesign.detail).foregroundStyle(WatchDesign.muted)
                }
                Text(details ? (programme.description ?? "") : (programme.resume?.title ?? programme.description ?? ""))
                    .font(WatchDesign.body).foregroundStyle(.white.opacity(0.82)).lineLimit(2)
                    .frame(width:600,height:56,alignment:.topLeading)
                HStack(spacing:24) {
                    Button(action:play) { Label(programme.resume == nil ? "Play" : "Resume",systemImage:"play.fill").font(.system(size:24,weight:.semibold)) }.buttonStyle(WatchActionButtonStyle(prominent:true)).focusEffectDisabled().focused($heroFocus,equals:.play)
                    if !details { NavigationLink(value:programme.id) { Text("Details").font(.system(size:24,weight:.medium)) }.focused($heroFocus,equals:.details) }
                    if details { FavouriteButton(programme:programme) }
                    if let previous,let next {
                        Button(action:previous) { Image(systemName:"chevron.left").font(.system(size:22,weight:.semibold)).frame(width:18) }
                            .focused($heroFocus,equals:.previous).accessibilityLabel("Previous highlight")
                        Text(featurePosition ?? "").font(.system(size:20)).foregroundStyle(WatchDesign.muted).monospacedDigit()
                        Button(action:next) { Image(systemName:"chevron.right").font(.system(size:22,weight:.semibold)).frame(width:18) }
                            .focused($heroFocus,equals:.next).accessibilityLabel("Next highlight")
                    }
                }.padding(.top,4)
            }.padding(.horizontal,WatchDesign.inset).padding(.bottom,32)
                .frame(maxWidth:.infinity,maxHeight:.infinity,alignment:.bottomLeading)
                .buttonStyle(WatchActionButtonStyle()).focusEffectDisabled()
        }.frame(height:WatchDesign.heroHeight).clipped().accessibilityElement(children:.contain)
        .onChange(of:heroFocus) { _,control in focusChanged?(control != nil) }
    }
}

struct DetailView:View {
    @EnvironmentObject private var library:LibraryStore
    @Environment(\.watchCardWidth) private var cardWidth
    @Environment(\.watchColumns) private var columnCount
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    let programme:Programme
    @State private var season=""
    private var current:Programme { library.programmes.first { $0.id==programme.id } ?? programme }
    private var seasons:[String] { var seen=Set<String>();return current.episodes.compactMap { seen.insert($0.seasonTitle).inserted ? $0.seasonTitle : nil } }
    private var episodes:[Episode] { current.episodes.filter { season=="All episodes" || season.isEmpty || $0.seasonTitle==season } }
    private var columns:[GridItem] { Array(repeating:GridItem(.fixed(cardWidth),spacing:WatchDesign.gap,alignment:.topLeading),count:columnCount) }
    var body:some View {
        WatchContentViewport {availableWidth in
        let columns=WatchDesign.gridColumns(availableWidth)
        ScrollView {
            VStack(alignment:.leading,spacing:32) {
                Hero(programme:current,details:true) { if let episode=current.preferred { start(episode,resume:true) } }
                if !current.film || current.episodes.count>1 {
                    HStack(spacing:32) {
                        SectionHeading(title:"Episodes",subtitle:"\(season=="All episodes" || season.isEmpty ? "Newest first" : season) · \(episodes.count) available").frame(width:230,alignment:.leading)
                        if seasons.count>1 {
                            Menu {
                                Picker("Series",selection:$season) {
                                    ForEach(seasons,id:\.self) { Text($0).tag($0) }
                                    Text("All episodes").tag("All episodes")
                                }
                            } label:{ Label(season.isEmpty ? "Series" : season,systemImage:"rectangle.stack").font(.system(size:23,weight:.medium)) }
                        }
                        Spacer()
                    }.focusSection().padding(.horizontal,WatchDesign.inset)
                    LazyVGrid(columns:columns,alignment:.leading,spacing:40) {
                        ForEach(episodes) { episode in
                            Button { start(episode,resume:true) } label:{ EpisodeTile(episode:episode,programme:current) }.buttonStyle(WatchCardButtonStyle()).focusEffectDisabled()
                        }
                    }.padding(.horizontal,WatchDesign.inset).padding(.top,12)
                } else {
                    HStack(alignment:.top,spacing:60) {
                        VStack(alignment:.leading,spacing:16) {
                            SectionHeading(title:"About the film")
                            Text(current.description ?? current.preferred?.description ?? "")
                                .font(WatchDesign.body).foregroundStyle(WatchDesign.muted)
                                .fixedSize(horizontal:false,vertical:true).frame(maxWidth:900,alignment:.leading)
                        }.frame(maxWidth:.infinity,alignment:.leading)
                        VStack(alignment:.leading,spacing:20) {
                            Text("Details").font(.system(size:26,weight:.semibold))
                            if let duration=current.preferred?.durationText { Label(duration,systemImage:"clock").font(WatchDesign.body) }
                            if !current.genres.isEmpty { Text(current.genres.prefix(3).joined(separator:" · ")).font(WatchDesign.body) }
                            Brands(items:current.brands)
                        }.foregroundStyle(WatchDesign.muted).frame(width:380,alignment:.leading)
                    }.padding(.horizontal,WatchDesign.inset).padding(.top,8)
                }
                if let episode=current.preferred,(episode.resumeSeconds ?? 0)>0 {
                    Button { start(episode,resume:false) } label:{ Label("Start over",systemImage:"backward.end").font(.system(size:23,weight:.medium)) }.padding(.horizontal,WatchDesign.inset)
                }
                if !current.film { SimilarShows(programme:current) }
            }.padding(.bottom,72)
        }.contentMargins(.horizontal,0,for:.scrollContent).background(WatchDesign.canvas)
        .task { await library.refresh(); if season.isEmpty { season=seasons.first ?? "All episodes" } }
        .animation(reduceMotion ? nil : .easeInOut(duration:0.2),value:season)
        }
    }
    private func start(_ episode:Episode,resume:Bool) { library.deepPlay=PlaybackSelection(programme:current,episode:episode,position:resume ? episode.resumeSeconds ?? 0 : 0) }
}

struct SimilarShows:View {
    @EnvironmentObject private var library:LibraryStore
    @Environment(\.watchCardWidth) private var cardWidth
    @Environment(\.watchColumns) private var columnCount
    let programme:Programme
    @State private var items:[Programme]=[]
    @State private var cursor:String?
    @State private var loading=false
    @State private var error=false
    @State private var generation=UUID()
    private var columns:[GridItem] { Array(repeating:GridItem(.fixed(cardWidth),spacing:WatchDesign.gap,alignment:.topLeading),count:columnCount) }
    var body:some View {
        VStack(alignment:.leading,spacing:24) {
            HStack {
                SectionHeading(title:"Similar shows",subtitle:"Shared cast, creators and related themes")
                Spacer()
                if loading { ProgressView() }
            }
            LazyVGrid(columns:columns,alignment:.leading,spacing:40) {
                ForEach(Array(items.enumerated()),id:\.element.id) { index,item in
                    NavigationLink { ProgrammeDestination(programme:item) } label:{ Tile(programme:item) }.buttonStyle(WatchCardButtonStyle()).focusEffectDisabled()
                        .contextMenu { FavouriteButton(programme:item) }
                        .onAppear {
                            if index>=items.count-8,cursor != nil { Task { await load(generation:generation) } }
                        }
                }
            }.padding(.top,10)
            if error { Button("Retry similar shows") { Task { await load(generation:generation) } }.font(WatchDesign.detail) }
            else if !loading && items.isEmpty { Text("No related shows are available from your supported services right now.").font(WatchDesign.detail).foregroundStyle(WatchDesign.muted) }
            else if !loading && cursor == nil { Text("All related suggestions shown").font(WatchDesign.detail).foregroundStyle(WatchDesign.muted) }
        }.padding(.horizontal,WatchDesign.inset).padding(.top,20)
        .task(id:programme.id) {
            items=[];cursor=nil;loading=false;error=false;generation=UUID()
            await load(generation:generation)
        }
    }
    @MainActor private func load(generation request:UUID) async {
        guard !loading,request==generation else { return }
        loading=true;error=false
        do {
            let result=try await library.api.related(id:programme.id,cursor:cursor)
            try Task.checkCancellation()
            guard request==generation else { return }
            let known=Set(items.map(\.id));items.append(contentsOf:result.programmes.filter { !known.contains($0.id) })
            cursor=result.nextCursor;library.merge(result.programmes);loading=false
        } catch {
            guard request==generation else { return }
            loading=false
            if !Task.isCancelled { self.error=true }
        }
    }
}

struct FavouriteButton:View {
    @EnvironmentObject private var library:LibraryStore
    let programme:Programme
    @State private var saving=false
    @State private var error:String?
    private var selected:Bool { (library.programmes.first(where:{$0.id==programme.id}) ?? programme).favourite }
    var body:some View {
        Button {
            saving=true
            Task {
                do { try await library.setFavourite(programme,value:!selected) }
                catch { self.error=error.localizedDescription }
                saving=false
            }
        } label:{
            Label(saving ? "Saving…" : (selected ? "Favourited" : "Favourite"),systemImage:selected ? "heart.fill" : "heart")
                .font(.system(size:24,weight:.medium))
        }.disabled(saving)
        .accessibilityHint("Changes your Watch favourites only. Provider lists stay unchanged.")
        .alert("Could not update favourite",isPresented:Binding(get:{error != nil},set:{if !$0 {error=nil}})) { Button("OK",role:.cancel) { error=nil } } message:{Text(error ?? "")}
    }
}

struct ProgrammeDestination:View {
    @EnvironmentObject private var library:LibraryStore
    let programme:Programme
    @State private var resolved:Programme?
    @State private var error:String?
    var body:some View {
        Group {
            if let current=resolved { DetailView(programme:current) }
            else if programme.discoveryRef == nil { DetailView(programme:programme) }
            else {
                WarmupScreen(programme:programme,status:error ?? "Finding episodes",failed:error != nil)
            }
        }.task(id:programme.id) {
            guard programme.discoveryRef != nil else { return }
            do { resolved=try await library.resolve(programme) }
            catch { self.error=error.localizedDescription }
        }
    }
}
struct SearchView:View {
    @EnvironmentObject private var library:LibraryStore
    @Environment(\.watchCardWidth) private var cardWidth
    @Environment(\.watchColumns) private var columnCount
    @State private var path:[String]=[]
    @State private var remote:[Programme]=[]
    @State private var searching=false
    @State private var failed=false
    @State private var partial=false
    private var query:String { library.searchQuery.trimmingCharacters(in:.whitespacesAndNewlines) }
    private var local:[Programme] { query.isEmpty ? [] : library.programmes.filter { $0.discoveryRef == nil && $0.title.localizedCaseInsensitiveContains(query) } }
    private var results:[Programme] {
        let known=Set(local.map { $0.title.lowercased() })
        return local+remote.filter { !known.contains($0.title.lowercased()) }
    }
    private var recent:[Programme] { Array(library.programmes.filter { !$0.live && $0.discoveryRef == nil && $0.resume != nil }.sorted { $0.latestProgress>$1.latestProgress }.prefix(8)) }
    private var columns:[GridItem] { Array(repeating:GridItem(.fixed(cardWidth),spacing:WatchDesign.gap,alignment:.topLeading),count:columnCount) }
    var body:some View {
        NavigationStack(path:$path) {
            WatchContentViewport {availableWidth in
            let columns=WatchDesign.gridColumns(availableWidth)
            ScrollView {
                VStack(alignment:.leading,spacing:30) {
                    HStack {
                        SectionHeading(title:query.isEmpty ? "Discover something new" : "Search all services",subtitle:query.isEmpty ? "Search beyond your favourites on BBC iPlayer, Channel 4, U and 5." : "\(results.count) result\(results.count == 1 ? "" : "s") · Your library and provider catalogues")
                        Spacer()
                        if searching { ProgressView() }
                    }
                    if failed || partial {
                        Text(failed ? "Provider search is temporarily unavailable. Your library results are still shown." : "Some providers are taking longer to respond. Available results are shown below.")
                            .font(WatchDesign.detail).foregroundStyle(.orange.opacity(0.85))
                    }
                    LazyVGrid(columns:columns,alignment:.leading,spacing:40) {
                        ForEach(query.isEmpty ? recent : results) { programme in
                            if programme.live {
                                Button { if let episode=programme.preferred { library.deepPlay=PlaybackSelection(programme:programme,episode:episode,position:0) } } label:{ Tile(programme:programme) }.buttonStyle(WatchCardButtonStyle()).focusEffectDisabled()
                            } else { NavigationLink(value:programme.id) { Tile(programme:programme) }.buttonStyle(WatchCardButtonStyle()).focusEffectDisabled() }
                        }
                    }.padding(.top,12)
                    if !query.isEmpty && results.isEmpty && !searching { QuietState(symbol:"magnifyingglass",title:"No matches yet",message:"Try a shorter title or another spelling.") }
                    if query.isEmpty && recent.isEmpty { QuietState(symbol:"magnifyingglass",title:"Something good is waiting",message:"Search a title using your remote, voice or iPhone keyboard.") }
                }.padding(.horizontal,WatchDesign.inset).padding(.top,38).padding(.bottom,72)
            }.contentMargins(.horizontal,0,for:.scrollContent).searchable(text:$library.searchQuery,prompt:"Search all supported services")
                .background(WatchDesign.canvas)
                .navigationDestination(for:String.self) { id in if let programme=library.programmes.first(where:{$0.id==id}) { ProgrammeDestination(programme:programme) } }
                .task { await library.refresh() }
                .task(id:query) {
                    remote=[];failed=false;partial=false
                    guard query.count>=2 else { searching=false;return }
                    searching=true
                    do {
                        try await Task.sleep(for:.milliseconds(450))
                        let response=try await library.api.search(query)
                        try Task.checkCancellation()
                        remote=response.programmes;library.merge(remote)
                        partial=response.status?.values.contains(where:{$0 != "ready"}) ?? false
                        searching=false
                    } catch {
                        guard !Task.isCancelled else { return }
                        failed=true;searching=false
                    }
                }
            }
        }
    }
}
