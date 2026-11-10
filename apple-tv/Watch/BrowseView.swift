import SwiftUI

enum Section:String,CaseIterable { case home="Home",shows="Shows",films="Films",live="Live TV",favourites="Favourites" }
struct BrowseView:View {
    @EnvironmentObject private var library:LibraryStore
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @Environment(\.watchCardWidth) private var cardWidth
    @Environment(\.watchColumns) private var columnCount
    let section:Section
    private enum BrowseFocus:Hashable {case filter,programme(String),shelfProgramme(String,String)}
    @FocusState private var browseFocus:BrowseFocus?
    @State private var heroFocusRequest=UUID()
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
            case .home:return !p.live && !p.film && (p.recent || p.favourite)
            case .shows:return !p.live && !p.film
            case .films:return p.film && !p.live
            case .live:return p.live
            case .favourites:return !p.live && p.favourite
            }
        }
        if section == .films {return result.sorted {($0.filmRank ?? Int.max)<($1.filmRank ?? Int.max)}}
        return section == .live ? result : BrowseOrdering.personal(result,recommended:library.recommendations)
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
    private var firstHomeShelf:String? {
        if items.contains(where:{$0.resume != nil}) {return "Continue Watching"}
        if library.recommendations.filter({!$0.film && !$0.live}).count>=4 {return "Picked for you"}
        if library.hot.filter({!$0.film && !$0.live}).count>=3 {return "In the spotlight"}
        if items.filter(\.favourite).count>=4 {return "Your favourites"}
        if items.filter(\.recent).count>=4 {return "Recently watched"}
        return nil
    }
    private var editorialPool:[Programme] {
        if section == .films {return filtered}
        var known=Set<String>()
        return (personalShows+genreSuggestions+filtered).filter{!$0.live && !$0.film && known.insert($0.id).inserted}
    }
    private var editorialShelves:[EditorialShelf] {EditorialShelves.make(editorialPool,films:section == .films)}
    private var homeThemes:[EditorialShelf] {
        let pool=BrowseOrdering.personal(library.programmes.filter{!$0.live && !$0.film},recommended:library.recommendations)
        return EditorialShelves.make(library.recommendations.filter{!$0.film && !$0.live}+pool,films:false)
            .filter{!$0.id.hasPrefix("explore-") && $0.id != "personal"}.prefix(8).map{$0}
    }
    var body:some View {
        NavigationStack(path:$path) {
            WatchContentViewport {availableWidth in
            let columns=WatchDesign.gridColumns(availableWidth)
            ScrollViewReader {scroll in
            ScrollView {
                LazyVStack(alignment:.leading,spacing:48) {
                    if section == .home {
                        if library.featuredShows.contains(where:{!$0.film && !$0.live}) {
                            FeaturedSpotlight(programmes:library.featuredShows.filter{!$0.film && !$0.live},tab:.home,focusRequest:heroFocusRequest) { play($0) }.id("hero-top")
                        } else if let hero { Hero(programme:hero,details:false,focusRequest:heroFocusRequest) { play(hero) }.id("hero-top") }
                    }
                    if library.error != nil {
                        Label("The Pi is taking a moment. Your last library is still available.",systemImage:"wifi.exclamationmark")
                            .font(WatchDesign.detail).foregroundStyle(.orange.opacity(0.9)).padding(.horizontal,WatchDesign.inset)
                    }
                    if section == .home {
                        let continuing=items.filter { $0.resume != nil }.sorted { $0.latestProgress > $1.latestProgress }
                        if !continuing.isEmpty { rail("Continue Watching",programmes:continuing,style:.continuing) }
                        if library.recommendations.filter({!$0.film && !$0.live}).count>=4 { rail("Picked for you",programmes:library.recommendations.filter{!$0.film && !$0.live},style:.portrait) }
                        if library.hot.filter({!$0.film && !$0.live}).count>=3 { rail("In the spotlight",programmes:library.hot.filter{!$0.film && !$0.live},style:.showcase) }
                        let favourites=items.filter(\.favourite)
                        if favourites.count>=4 { rail("Your favourites",programmes:favourites,style:.portrait) }
                        let recent=items.filter(\.recent).sorted { $0.latestProgress > $1.latestProgress }
                        if recent.count>=4 { rail("Recently watched",programmes:recent,style:.continuing) }
                        themedRows(homeThemes)
                        let live=library.programmes.filter(\.live)
                        if !live.isEmpty { rail("Live now",programmes:live) }
                        if hero == nil && !library.loading {
                            QuietState(symbol:"heart",title:"Make yourself at home",message:"Favourite a show in your provider accounts and it will appear here after the next sync.")
                        }
                    } else {
                        if section == .films,genre == "All genres",!library.featuredFilms.isEmpty {
                            FeaturedSpotlight(programmes:library.featuredFilms,tab:.films,focusRequest:heroFocusRequest) { play($0) }.id("hero-top")
                        }
                        if section == .films,genre == "All genres" {
                            let continuing=items.filter{$0.resume != nil}.sorted{$0.latestProgress>$1.latestProgress}
                            if !continuing.isEmpty {rail("Continue Watching",programmes:continuing,style:.continuing)}
                        }
                        HStack(alignment:.center,spacing:32) {
                            SectionHeading(title:section.rawValue,subtitle:uhdOnly ? "\(filtered.count) with UHD episodes available" : favouritesOnly ? "\(filtered.count) favourite\(filtered.count == 1 ? "" : "s")" : section == .favourites ? "Your saved shows and films" : section == .live ? "On now and coming up" : (section == .shows ? "Recently watched and favourites first" : "\(filtered.count) films in your library"))
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
                                    if direction == .down {
                                        if !collectionOnly,let row=editorialShelves.first,let first=row.programmes.first {browseFocus = .shelfProgramme(row.id,first.id)}
                                        else if let first=filtered.first {browseFocus = .programme(first.id)}
                                    }
                                }
                                .accessibilityLabel("Filter \(section.rawValue) collection: \(genre)")
                            }
                        }.padding(.horizontal,WatchDesign.inset).focusSection()
                        if (section == .shows || section == .films) && !collectionOnly {
                            themedRows(editorialShelves)
                        } else if section == .favourites {
                            let shows=filtered.filter{!$0.film};let films=filtered.filter(\.film)
                            if !shows.isEmpty {rail("Shows",programmes:shows,style:.portrait)}
                            if !films.isEmpty {rail("Films",programmes:films,style:.portrait)}
                        } else {
                            LazyVGrid(columns:columns,alignment:.leading,spacing:40) {
                                ForEach(Array(filtered.enumerated()),id:\.element.id) { index,programme in gridTile(programme,topRow:index<columns.count) }
                            }.padding(.horizontal,WatchDesign.inset).padding(.top,12)
                        }
                        if section == .shows && !collectionOnly {
                            if loadingSuggestions {ProgressView().frame(maxWidth:.infinity)}
                            if suggestionError {Button("Retry loading more shows") {Task {await fetchSuggestions(genre,generation:suggestionGeneration)}}.padding(.horizontal,WatchDesign.inset)}
                            if nextSuggestionCursor != nil {
                                Color.clear.frame(height:1).onAppear {Task {await fetchSuggestions(genre,generation:suggestionGeneration)}}
                            }
                        }
                        if filtered.isEmpty && !library.loading && (section != .shows || collectionOnly) {
                            QuietState(symbol:favouritesOnly ? "heart" : "line.3.horizontal.decrease",title:uhdOnly ? "No UHD titles available" : favouritesOnly ? "No favourites yet" : "Nothing in this collection yet",message:uhdOnly ? "Titles appear here when the provider lists an available UHD edition. UHD availability may vary by episode." : favouritesOnly ? "Choose Favourite on a \(section == .films ? "film" : "show") to save it here." : "Choose another genre or add favourites in your provider accounts.")
                        }
                    }
                    if library.loading && library.programmes.isEmpty {
                        QuietState(symbol:"tv",title:"Getting your library ready",message:"Your shows, films and live channels will appear here shortly.")
                        ProgressView().frame(maxWidth:.infinity)
                    }
                }.padding(.top,section == .home || section == .films ? 0 : 132).padding(.bottom,72)
            }.contentMargins(.horizontal,0,for:.scrollContent)
            .ignoresSafeArea(.container,edges:section == .home || section == .films ? .top : [])
            .background(WatchDesign.canvas)
            .toolbarBackground(.hidden,for:.navigationBar,.tabBar)
            .navigationDestination(for:String.self) { id in
                let collection=CollectionDestination.parse(id)
                let episode=EpisodeDestination.parse(id)
                if let programme=library.programmes.first(where:{$0.id==(episode?.programmeID ?? collection?.programmeID ?? id)}) {
                    ProgrammeDestination(programme:programme,episodeCollection:collection?.collection,selectedEpisodeID:episode?.episodeID)
                }
            }
            .task { await library.refresh(); applyRoute() }
            .onChange(of:library.routeProgrammeID) { _,_ in applyRoute() }
            .onChange(of:library.tab) { _,tab in applyRoute();if section == .shows && tab == .shows && path.isEmpty { Task { await reloadShows() } } }
            .onChange(of:path) { old,new in if !old.isEmpty && new.isEmpty { library.routeProgrammeID=nil;if section == .shows { Task { await reloadShows() } } } }
            .task(id:genre) { await reloadShows() }
            .animation(reduceMotion ? nil : .easeInOut(duration:0.2),value:genre)
            .onChange(of:heroFocusRequest) {_,_ in
                withAnimation(reduceMotion ? nil : .easeInOut(duration:0.3)) {scroll.scrollTo("hero-top",anchor:.top)}
            }
            }
            }.ignoresSafeArea(.container,edges:section == .home || section == .films ? .top : [])
        }.toolbarBackground(.hidden,for:.navigationBar,.tabBar)
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
        if programme.live {
            if let episode=programme.preferred {library.deepPlay=PlaybackSelection(programme:programme,episode:episode,position:0)}
        } else {path.append(programme.id)}
    }
    private func gridTile(_ programme:Programme,topRow:Bool)->some View {
        tileLink(programme).focused($browseFocus,equals:.programme(programme.id))
            .onMoveCommand {direction in
                if direction == .up,topRow,section == .shows || section == .films {browseFocus = .filter}
            }
    }
    @ViewBuilder private func tileLink(_ programme:Programme,style:BrowseCardStyle = .landscape,shelf:Bool = false,collection:String?=nil) -> some View {
        if programme.live { Button { play(programme) } label:{ Tile(programme:programme) }.buttonStyle(WatchCardButtonStyle()).focusEffectDisabled() }
        else if style == .continuing,let episode=programme.resume ?? programme.preferred {
            NavigationLink(value:EpisodeDestination(programmeID:programme.id,episodeID:episode.id).pathValue) {CinematicProgrammeCard(programme:programme,style:style,shelf:shelf,episodeCollection:collection)}.buttonStyle(WatchCardButtonStyle()).focusEffectDisabled()
        }
        else if let collection {
            NavigationLink(value:CollectionDestination(programmeID:programme.id,collection:collection).pathValue) {CinematicProgrammeCard(programme:programme,style:style,shelf:shelf,episodeCollection:collection)}.buttonStyle(WatchCardButtonStyle()).focusEffectDisabled()
        }
        else { NavigationLink(value:programme.id) { CinematicProgrammeCard(programme:programme,style:style,shelf:shelf) }.buttonStyle(WatchCardButtonStyle()).focusEffectDisabled()
            .contextMenu { FavouriteButton(programme:programme) }
        }
    }
    private func rail(_ title:String,programmes:[Programme],style:BrowseCardStyle = .standard) -> some View {
        let returnToHero=(section == .home && title == firstHomeShelf) || (section == .films && title == "Continue Watching" && genre == "All genres" && !library.featuredFilms.isEmpty)
        let usePosters=style == .portrait || style == .showcase
        let posters=usePosters ? programmes.filter{$0.poster?.isEmpty == false} : []
        let landscape=usePosters ? programmes.filter{$0.poster?.isEmpty != false} : programmes
        let moreTitle=title == "Your favourites" ? "More favourites" : title == "Picked for you" ? "More picks for you" : "More highlights"
        return VStack(alignment:.leading,spacing:44) {
            if usePosters && !posters.isEmpty && !landscape.isEmpty && (posters.count<4 || landscape.count<4) {
                shelf(title,programmes:programmes,style:.landscape,recommendations:title == "Picked for you",returnToHero:returnToHero)
            } else {
                if !posters.isEmpty {shelf(title,programmes:posters,style:style,recommendations:title == "Picked for you",returnToHero:returnToHero)}
                if !landscape.isEmpty {shelf(posters.isEmpty ? title : moreTitle,programmes:landscape,style:usePosters ? .landscape : style,recommendations:title == "Picked for you",returnToHero:returnToHero && posters.isEmpty)}
            }
        }
    }
    private func themedRows(_ rows:[EditorialShelf])->some View {
        LazyVStack(alignment:.leading,spacing:48) {
            ForEach(rows) {row in
                let style:BrowseCardStyle = row.layout == .feature ? .showcase : row.layout == .portrait ? .portrait : .landscape
                shelf(row.title,programmes:row.programmes,style:style,recommendations:false,returnToHero:section == .home && firstHomeShelf == nil && row.id == rows.first?.id,collection:row.episodeCollection,focusRow:row.id,filterAbove:section != .home && row.id==rows.first?.id)
                    .padding(.top,row.title.isEmpty ? -24 : 0)
            }
        }
    }
    private func shelf(_ title:String,programmes:[Programme],style:BrowseCardStyle,recommendations:Bool,returnToHero:Bool,collection:String?=nil,focusRow:String?=nil,filterAbove:Bool=false) -> some View {
        VStack(alignment:.leading,spacing:12) {
            if !title.isEmpty {
                HStack(spacing:16) {
                    if collection == "christmas" {Image(systemName:"sparkles").font(.system(size:30,weight:.light)).foregroundStyle(Color(red:0.9,green:0.73,blue:0.4))}
                    SectionHeading(title:title)
                }.padding(.horizontal,WatchDesign.inset)
            }
            ScrollView(.horizontal) {
                LazyHStack(alignment:.top,spacing:WatchDesign.gap) {
                    if collection == "christmas" {
                        ForEach(EditorialShelves.christmasEpisodes(programmes)) {entry in
                            NavigationLink(value:EpisodeDestination(programmeID:entry.programme.id,episodeID:entry.episode.id).pathValue) {
                                CinematicProgrammeCard(programme:entry.programme,style:.continuing,shelf:true,episodeCollection:"christmas",explicitEpisode:entry.episode)
                            }.buttonStyle(WatchCardButtonStyle()).focusEffectDisabled()
                                .focused($browseFocus,equals:.shelfProgramme(focusRow ?? title,entry.id))
                                .onMoveCommand {direction in
                                    if direction == .up,returnToHero {heroFocusRequest=UUID()}
                                    else if direction == .up,filterAbove {browseFocus = .filter}
                                }
                        }
                    } else {
                    ForEach(Array(programmes.enumerated()),id:\.element.id) { index,programme in
                        tileLink(programme,style:style,shelf:true,collection:collection)
                            .focused($browseFocus,equals:.shelfProgramme(focusRow ?? title,programme.id))
                            .onMoveCommand {direction in
                                if direction == .up,returnToHero {heroFocusRequest=UUID()}
                                else if direction == .up,filterAbove {browseFocus = .filter}
                            }
                            .onAppear {
                            if recommendations,index>=programmes.count-4 {
                                Task { await library.moreRecommendations() }
                            }
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
    var focusRequest:UUID?=nil
    let play:(Programme)->Void
    @State private var index=0
    @State private var heroFocused=false
    @State private var visible=false
    @State private var lastChange=Date()
    @State private var slideDirection=1
    @State private var lastAdvance=Date.distantPast
    private var current:Programme {programmes[min(index,programmes.count-1)]}
    var body:some View {
        // A single action owns focus. Artwork moves; focus never scrolls to a
        // competing off-screen hero and cannot snap the carousel back.
        Hero(programme:current,focusChanged:{heroFocused=$0;lastChange=Date()},previous:{advance(-1)},next:{advance(1)},featureIndex:index,featureCount:programmes.count,slideDirection:slideDirection,focusRequest:focusRequest) {play(current)}
        .onAppear { visible=true;lastChange=Date() }.onDisappear { visible=false }
        .onChange(of:programmes.map(\.id)) { _,_ in index=0;lastChange=Date() }
        .task(id:programmes.map(\.id)) {
            for programme in programmes {
                guard !Task.isCancelled else {return}
                await Artwork.prefetch(programme.hero ?? programme.artwork,maxPixel:2400)
            }
        }
        .task {
            while !Task.isCancelled {
                do { try await Task.sleep(for:.seconds(1)) } catch { return }
                guard visible,scenePhase == .active,library.tab == tab,library.deepPlay == nil,!heroFocused,!reduceMotion,programmes.count>1 else { continue }
                if Date().timeIntervalSince(lastChange)>=18 { advance(1) }
            }
        }
    }
    private func advance(_ direction:Int) {
        guard programmes.count>1,Date().timeIntervalSince(lastAdvance)>0.5 else {return}
        slideDirection=direction;index=(index+direction+programmes.count)%programmes.count
        lastAdvance=Date();lastChange=Date()
    }
}

struct Hero:View {
    @EnvironmentObject private var library:LibraryStore
    @Environment(\.cinemaHeroHeight) private var heroHeight
    let programme:Programme
    var details=false
    var focusChanged:((Bool)->Void)?=nil
    @FocusState private var heroFocus:HeroControl?
    private enum HeroControl:Hashable {case play,details}
    var previous:(()->Void)?=nil
    var next:(()->Void)?=nil
    var featureIndex=0
    var featureCount=0
    var slideDirection=1
    var focusRequest:UUID?=nil
    var primaryTitle:String?=nil
    var play:()->Void
    var body:some View {
        GeometryReader {proxy in
            ZStack(alignment:.bottomLeading) {
                HeroSlideArtwork(source:programme.hero ?? programme.artwork,direction:slideDirection)
                    .frame(width:proxy.size.width,height:heroHeight)
                EllipticalGradient(stops:[.init(color:.black.opacity(0.60),location:0),.init(color:.black.opacity(0.28),location:0.55),.init(color:.clear,location:1)],center:UnitPoint(x:0.16,y:0.68),startRadiusFraction:0,endRadiusFraction:0.55)
                    .allowsHitTesting(false)
                LinearGradient(stops:[.init(color:.clear,location:0),.init(color:.clear,location:0.84),.init(color:.black.opacity(0.7),location:1)],startPoint:.top,endPoint:.bottom)
                VStack(alignment:.leading,spacing:20) {
                    ProgrammeTitle(programme:programme,width:min(580,proxy.size.width*0.46),height:100,maxLogoHeight:170,reserveHeadroom:false,providerEyebrow:true)
                    Text([programme.contentRating,programme.genres.prefix(2).joined(separator:" · "),programme.film ? programme.preferred?.durationText : nil].compactMap{$0}.filter{!$0.isEmpty}.joined(separator:" · "))
                        .font(.system(size:21,weight:.medium)).foregroundStyle(.white.opacity(0.7))
                    Text(programme.description ?? "")
                        .font(.system(size:25)).foregroundStyle(.white.opacity(0.88)).lineLimit(2)
                        .frame(width:min(660,proxy.size.width*0.48),alignment:.leading)
                    HStack(spacing:20) {
                        if details {
                            Button(action:play) {Label(primaryTitle ?? (programme.resume == nil ? "Play" : "Resume"),systemImage:"play.fill")}
                                .buttonStyle(WatchActionButtonStyle(prominent:true)).focusEffectDisabled().focused($heroFocus,equals:.play)
                        }
                        if !details {
                            NavigationLink(value:programme.id) {Label(programme.film ? "View film" : "Explore series",systemImage:programme.film ? "info.circle" : "rectangle.stack")}
                                .buttonStyle(WatchActionButtonStyle(prominent:!programme.film)).focusEffectDisabled().focused($heroFocus,equals:.details)
                        } else {FavouriteButton(programme:programme).buttonStyle(WatchActionButtonStyle()).focusEffectDisabled()}
                    }.font(.system(size:25,weight:.semibold)).padding(.top,10)
                }.padding(.horizontal,WatchDesign.inset).padding(.bottom,48)
                if featureCount>1 {
                    HStack(spacing:10) {
                        ForEach(0..<featureCount,id:\.self) {page in
                            Circle().fill(.white.opacity(page==featureIndex ? 1 : 0.35)).frame(width:page==featureIndex ? 8 : 6,height:page==featureIndex ? 8 : 6)
                        }
                    }.padding(.trailing,WatchDesign.inset).padding(.bottom,62)
                        .frame(maxWidth:.infinity,alignment:.trailing)
                        .accessibilityElement(children:.ignore).accessibilityLabel("Highlight \(featureIndex+1) of \(featureCount)")
                }
            }.frame(width:proxy.size.width,height:heroHeight).clipped()
        }.frame(height:heroHeight).accessibilityElement(children:.contain)
            .onChange(of:heroFocus) {_,control in focusChanged?(control != nil)}
            .onAppear {heroFocus = details ? .play : .details}
            .onChange(of:focusRequest) {_,_ in heroFocus = details ? .play : .details}
            .onMoveCommand {direction in
                guard !details,featureCount>1 else {return}
                if direction == .right {next?()}
                else if direction == .left {previous?()}
            }
    }
}

struct DetailView:View {
    @EnvironmentObject private var library:LibraryStore
    @Environment(\.watchCardWidth) private var cardWidth
    @Environment(\.watchColumns) private var columnCount
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    let programme:Programme
    var episodeCollection:String?=nil
    var selectedEpisodeID:String?=nil
    @State private var appliedInitialEpisode=false
    @State private var season="All series"
    @FocusState private var episodeFocus:String?
    private var current:Programme { library.programmes.first { $0.id==programme.id } ?? programme }
    private var collectionEpisodes:[Episode] {episodeCollection == "christmas" ? current.episodes.filter{EditorialShelves.matchesChristmas(current,$0)} : current.episodes}
    private var seasons:[String] { var seen=Set<String>();return collectionEpisodes.compactMap { seen.insert($0.seasonTitle).inserted ? $0.seasonTitle : nil } }
    private var episodes:[Episode] { collectionEpisodes.filter { season=="All series" || season.isEmpty || $0.seasonTitle==season } }
    private var columns:[GridItem] { Array(repeating:GridItem(.fixed(cardWidth),spacing:WatchDesign.gap,alignment:.topLeading),count:columnCount) }
    var body:some View {
        WatchContentViewport {availableWidth in
        let columns=WatchDesign.gridColumns(availableWidth)
        ScrollViewReader {scroll in
        ScrollView {
            VStack(alignment:.leading,spacing:48) {
                Hero(programme:current,details:true,primaryTitle:current.film ? nil : "Choose episode") {
                    if current.film {if let episode=current.preferred {start(episode,resume:true)}}
                    else {
                        withAnimation(reduceMotion ? nil : .easeInOut(duration:0.25)) {scroll.scrollTo("episode-list",anchor:.top)}
                        Task {@MainActor in await Task.yield();episodeFocus=episodes.first(where:{$0.id==selectedEpisodeID})?.id ?? episodes.first?.id}
                    }
                }
                if !current.film || current.episodes.count>1 {
                    HStack(spacing:32) {
                        SectionHeading(title:episodeCollection == "christmas" ? "Christmas episodes" : "Episodes",subtitle:"\(season=="All series" || season.isEmpty ? "Newest first" : season) · \(episodes.count) available").frame(width:230,alignment:.leading)
                        if seasons.count>1 {
                            Menu {
                                Picker("Series",selection:$season) {
                                    ForEach(seasons,id:\.self) { Text($0).tag($0) }
                                    Text("All series").tag("All series")
                                }
                            } label:{ Label(season.isEmpty ? "All series" : season,systemImage:"rectangle.stack").font(.system(size:23,weight:.medium)) }
                        }
                        Spacer()
                    }.focusSection().padding(.horizontal,WatchDesign.inset).id("episode-list")
                    LazyVGrid(columns:columns,alignment:.leading,spacing:40) {
                        ForEach(episodes) { episode in
                            Button { start(episode,resume:true) } label:{ EpisodeTile(episode:episode,programme:current,showSeries:seasons.count>1 && (season=="All series" || season.isEmpty)) }.id(episode.id).focused($episodeFocus,equals:episode.id).buttonStyle(WatchCardButtonStyle()).focusEffectDisabled()
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
                if !current.film { SimilarShows(programme:current) }
            }.padding(.bottom,72)
        }.contentMargins(.horizontal,0,for:.scrollContent).ignoresSafeArea(.container,edges:.top).background(WatchDesign.canvas)
        .toolbarBackground(.hidden,for:.navigationBar,.tabBar)
        .task {
            if !appliedInitialEpisode,let selectedEpisodeID,episodes.contains(where:{$0.id==selectedEpisodeID}) {
                appliedInitialEpisode=true
                await Task.yield()
                scroll.scrollTo(selectedEpisodeID,anchor:.center)
                await Task.yield()
                episodeFocus=selectedEpisodeID
            }
            await library.refresh()
        }
        .animation(reduceMotion ? nil : .easeInOut(duration:0.2),value:season)
        }
        }.ignoresSafeArea(.container,edges:.top)
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
                    NavigationLink { ProgrammeDestination(programme:item) } label:{ CinematicProgrammeCard(programme:item,style:.landscape) }.buttonStyle(WatchCardButtonStyle()).focusEffectDisabled()
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
            let known=Set(items.map(\.id));items.append(contentsOf:result.programmes.filter { !known.contains($0.id) && $0.film == programme.film && !$0.live })
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
    var episodeCollection:String?=nil
    var selectedEpisodeID:String?=nil
    @State private var resolved:Programme?
    @State private var error:String?
    var body:some View {
        Group {
            if let current=resolved { DetailView(programme:current,episodeCollection:episodeCollection,selectedEpisodeID:selectedEpisodeID) }
            else if programme.discoveryRef == nil { DetailView(programme:programme,episodeCollection:episodeCollection,selectedEpisodeID:selectedEpisodeID) }
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
                            } else { NavigationLink(value:programme.id) { CinematicProgrammeCard(programme:programme,style:.landscape) }.buttonStyle(WatchCardButtonStyle()).focusEffectDisabled() }
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
