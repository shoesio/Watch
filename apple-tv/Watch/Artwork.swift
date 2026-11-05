import SwiftUI
import ImageIO
import Vision

// A single television layout scale, shared by every catalogue and detail screen.
enum WatchDesign {
    static let canvas=Color.black
    static let inset:CGFloat=64
    static let gap:CGFloat=40
    static let cardInset:CGFloat=16
    static let radius:CGFloat=20
    static let heroHeight:CGFloat=440
    static let heroArtworkHeight:CGFloat=560
    static let heading:Font = .system(size:34,weight:.semibold)
    static let title:Font = .system(size:24,weight:.semibold)
    static let body:Font = .system(size:23)
    static let detail:Font = .system(size:20)
    static let muted=Color.white.opacity(0.65)
    static func columns(_ width:CGFloat) -> Int { width>=1600 ? 4 : (width>=1100 ? 3 : 2) }
    static func cardWidth(_ width:CGFloat) -> CGFloat {
        floor(max(1,width-inset*2-gap*CGFloat(columns(width)-1))/CGFloat(columns(width)))
    }
    static func gridColumns(_ width:CGFloat)->[GridItem] {
        Array(repeating:GridItem(.fixed(cardWidth(width)),spacing:gap,alignment:.topLeading),count:columns(width))
    }
}
private struct CinemaHeroHeightKey:EnvironmentKey {static let defaultValue:CGFloat=820}
private struct CardWidthKey:EnvironmentKey { static let defaultValue:CGFloat=409 }
private struct CardColumnsKey:EnvironmentKey { static let defaultValue=4 }
extension EnvironmentValues {
    var cinemaHeroHeight:CGFloat {get {self[CinemaHeroHeightKey.self]} set {self[CinemaHeroHeightKey.self]=newValue}}
    var watchCardWidth:CGFloat { get { self[CardWidthKey.self] } set { self[CardWidthKey.self]=newValue } }
    var watchColumns:Int { get { self[CardColumnsKey.self] } set { self[CardColumnsKey.self]=newValue } }
}

// Measure inside each navigation page. Tab/navigation safe areas can make a
// page narrower than the TV; full-screen dimensions must not size its cards.
struct WatchContentViewport<Content:View>:View {
    let content:(CGFloat)->Content
    init(@ViewBuilder content:@escaping(CGFloat)->Content) {self.content=content}
    var body:some View {
        GeometryReader {proxy in
            content(proxy.size.width)
                .frame(width:proxy.size.width,height:proxy.size.height,alignment:.topLeading)
                .environment(\.cinemaHeroHeight,max(460,proxy.size.height*0.64))
                .environment(\.watchCardWidth,WatchDesign.cardWidth(proxy.size.width))
                .environment(\.watchColumns,WatchDesign.columns(proxy.size.width))
        }
    }
}
struct WatchCardButtonStyle:ButtonStyle {
    @Environment(\.isFocused) private var focused
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    func makeBody(configuration:Configuration)->some View {
        configuration.label
            .overlay {RoundedRectangle(cornerRadius:WatchDesign.radius).strokeBorder(.white.opacity(focused ? 0.9 : 0),lineWidth:3)}
            .scaleEffect(configuration.isPressed ? 0.985 : (focused ? 1.025 : 1))
            .shadow(color:.black.opacity(focused ? 0.4 : 0),radius:16,y:8)
            .animation(reduceMotion ? nil : .easeOut(duration:0.16),value:focused)
            .animation(reduceMotion ? nil : .easeOut(duration:0.12),value:configuration.isPressed)
    }
}
struct WatchActionButtonStyle:ButtonStyle {
    @Environment(\.isFocused) private var focused
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    var prominent=false
    func makeBody(configuration:Configuration)->some View {
        configuration.label
            .foregroundStyle(focused ? Color.black : Color.white)
            .padding(.horizontal,24).padding(.vertical,15)
            .background(focused ? Color.white : Color.white.opacity(prominent ? 0.20 : 0.10),in:RoundedRectangle(cornerRadius:14))
            .overlay {RoundedRectangle(cornerRadius:14).strokeBorder(.white.opacity(focused ? 1 : 0.12),lineWidth:1)}
            .scaleEffect(configuration.isPressed ? 0.97 : 1)
            .animation(reduceMotion ? nil : .easeOut(duration:0.16),value:focused)
    }
}

// Downsample before displaying; moving focus should not decode full-size hero images.
private actor ArtworkCache {
    static let shared=ArtworkCache()
    private let cache=NSCache<NSString,UIImage>()
    private var pending:[String:Task<UIImage?,Never>]=[:]
    private var titleChecks:[String:Bool]=[:]
    private let session:URLSession
    init() {
        cache.totalCostLimit=70*1024*1024
        let config=URLSessionConfiguration.default
        config.urlCache=URLCache(memoryCapacity:12*1024*1024,diskCapacity:100*1024*1024)
        config.timeoutIntervalForRequest=20
        session=URLSession(configuration:config)
    }
    func containsTitle(_ source:String,title:String) async -> Bool {
        let key=source+"#title#"+title
        if let value=titleChecks[key] {return value}
        guard let bitmap=await image(source,maxPixel:800)?.cgImage else {return true}
        let result=await ArtworkTitleAnalysis.shared.containsTitle(bitmap,title:title)
        if titleChecks.count>1000 {titleChecks.removeAll()}
        titleChecks[key]=result;return result
    }
    func image(_ source:String,maxPixel:Int) async -> UIImage? {
        let key=source+"#\(maxPixel)"
        if let image=cache.object(forKey:key as NSString) { return image }
        if let task=pending[key] { return await task.value }
        let session=self.session
        let task=Task<UIImage?,Never> {
            guard let url=URL(string:source), ["https","http"].contains(url.scheme) else { return nil }
            do {
                let (data,response)=try await session.data(from:url)
                guard let response=response as? HTTPURLResponse,(200..<300).contains(response.statusCode),data.count<12*1024*1024,
                      let original=CGImageSourceCreateWithData(data as CFData,nil),
                      let bitmap=CGImageSourceCreateThumbnailAtIndex(original,0,[kCGImageSourceCreateThumbnailFromImageAlways:true,kCGImageSourceThumbnailMaxPixelSize:maxPixel,kCGImageSourceCreateThumbnailWithTransform:true,kCGImageSourceShouldCacheImmediately:true] as CFDictionary) else { return nil }
                return UIImage(cgImage:bitmap)
            } catch { return nil }
        }
        pending[key]=task
        let image=await task.value;pending[key]=nil
        if let image { cache.setObject(image,forKey:key as NSString,cost:Int(image.size.width*image.size.height*4)) }
        return image
    }
}
// Serial, off-main analysis avoids stamping a second wordmark on provider
// artwork. A failed image/read keeps the finished artwork intact.
private actor ArtworkTitleAnalysis {
    static let shared=ArtworkTitleAnalysis()
    func containsTitle(_ image:CGImage,title:String)->Bool {
        let request=VNRecognizeTextRequest();request.recognitionLevel = .accurate;request.usesLanguageCorrection=false
        do {
            try VNImageRequestHandler(cgImage:image,options:[:]).perform([request])
            let text=(request.results ?? []).compactMap{$0.topCandidates(1).first?.string}.joined(separator:" ")
            func words(_ value:String)->Set<String> {
                Set(value.folding(options:[.diacriticInsensitive,.caseInsensitive],locale:Locale(identifier:"en_GB")).components(separatedBy:CharacterSet.alphanumerics.inverted).filter{!$0.isEmpty})
            }
            let stop:Set<String>=["the","a","an","and","of","for","with","on","to","is","at","or","bbc","bleeped"]
            let expected=words(title).subtracting(stop);let actual=words(text)
            guard !expected.isEmpty else {return !text.isEmpty}
            let hits=expected.intersection(actual).count
            return hits>=max(1,Int(ceil(Double(expected.count)*0.5)))
        } catch {return true}
    }
}

private struct ContinueWatchingIdentity:View {
    let programme:Programme
    let width:CGFloat
    @State private var logo:UIImage?
    var body:some View {
        Group {
            if let logo {
                let scale=min(width/max(1,logo.size.width),56/max(1,logo.size.height))
                Image(uiImage:logo).resizable().interpolation(.high)
                    .frame(width:logo.size.width*scale,height:logo.size.height*scale)
            } else {
                Text(programme.title).font(.system(size:22,weight:.semibold)).lineLimit(2)
            }
        }.frame(width:width,height:72,alignment:.leading)
            .shadow(color:.black.opacity(0.65),radius:2,y:1)
            .task(id:programme.logoSource) {
                logo=nil
                if let source=programme.logoSource {logo=await ArtworkCache.shared.image(source,maxPixel:700)}
            }
    }
}

struct Artwork: View {
    static func prefetch(_ source:String?,maxPixel:Int)async {
        if let source {_ = await ArtworkCache.shared.image(source,maxPixel:maxPixel)}
    }
    let source:String?
    var fit=false
    var maxPixel=900
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @State private var image:UIImage?
    var body:some View {
        GeometryReader { proxy in
            ZStack {
                if !fit { LinearGradient(colors:[Color(white:0.15),Color(white:0.07)],startPoint:.topLeading,endPoint:.bottomTrailing) }
                if let image {
                    Image(uiImage:image).resizable().aspectRatio(contentMode:fit ? .fit : .fill)
                        .frame(width:proxy.size.width,height:proxy.size.height,alignment:.center).transition(.opacity)
                }
            }.frame(width:proxy.size.width,height:proxy.size.height).clipped()
        }.clipped().accessibilityHidden(true)
        .task(id:(source ?? "")+"#\(maxPixel)") {
            image=nil
            guard let source,!source.isEmpty else { return }
            let loaded=await ArtworkCache.shared.image(source,maxPixel:maxPixel)
            guard !Task.isCancelled else { return }
            withAnimation(reduceMotion ? nil : .easeOut(duration:0.2)) { image=loaded }
        }
    }
}
// The focused action remains in Hero. These two inert image layers animate
// independently of tvOS's focus engine and keep the old photo during a fetch.
struct HeroSlideArtwork:View {
    let source:String?
    var direction=1
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @State private var image:UIImage?
    @State private var outgoing:UIImage?
    @State private var incomingOffset:CGFloat=0
    @State private var outgoingOffset:CGFloat=0
    var body:some View {
        GeometryReader {proxy in
            ZStack {
                Color.black
                if let outgoing {photo(outgoing,size:proxy.size).offset(x:outgoingOffset)}
                if let image {photo(image,size:proxy.size).offset(x:incomingOffset)}
            }.frame(width:proxy.size.width,height:proxy.size.height).clipped()
                .task(id:source) {
                    guard let source else {image=nil;outgoing=nil;return}
                    guard let loaded=await ArtworkCache.shared.image(source,maxPixel:2400),!Task.isCancelled else {return}
                    guard image != nil,!reduceMotion else {image=loaded;outgoing=nil;incomingOffset=0;return}
                    let width=proxy.size.width*CGFloat(direction)
                    outgoing=image;outgoingOffset=0;incomingOffset=width;image=loaded
                    do {try await Task.sleep(for:.milliseconds(20))} catch {return}
                    withAnimation(.easeInOut(duration:0.44)) {incomingOffset=0;outgoingOffset = -width}
                    do {try await Task.sleep(for:.milliseconds(460))} catch {return}
                    outgoing=nil
                }
        }.allowsHitTesting(false).accessibilityHidden(true)
    }
    private func photo(_ image:UIImage,size:CGSize)->some View {
        Image(uiImage:image).resizable().aspectRatio(contentMode:.fill)
            .frame(width:size.width,height:size.height).clipped()
    }
}

struct Brands:View {
    let items:[Brand]
    var body:some View {
        HStack(spacing:18) {
            ForEach(items) { brand in Artwork(source:brand.image,fit:true,maxPixel:180).frame(width:56,height:30) }
        }.accessibilityElement(children:.ignore).accessibilityLabel(items.map(\.name).joined(separator:", "))
    }
}
struct CardBrands:View {
    let items:[Brand]
    var body:some View {
        HStack(spacing:6) {
            ForEach(items) { brand in Artwork(source:brand.image,fit:true,maxPixel:140).frame(width:40,height:28) }
        }.padding(.horizontal,8).padding(.vertical,6)
        .background(.black.opacity(0.68),in:RoundedRectangle(cornerRadius:9))
        .accessibilityElement(children:.ignore).accessibilityLabel(items.map(\.name).joined(separator:", "))
    }
}
struct ProgrammeTitle:View {
    let programme:Programme
    var large=true
    var titleFont:Font?=nil
    var titleLineLimit:Int?=nil
    var centered=false
    var width:CGFloat=520
    var height:CGFloat=100
    var maxLogoHeight:CGFloat=140
    var reserveHeadroom=true
    var providerEyebrow=false
    var brandItems:[Brand]?=nil
    var rating:String?=nil
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @State private var logo:UIImage?
    private var brands:[Brand] {brandItems ?? programme.brands}
    private var hasEyebrow:Bool {providerEyebrow && (!brands.isEmpty || rating != nil)}
    private var size:CGSize {logo.map {ClearLogoLayout.size(image:$0.size,width:width,maxHeight:maxLogoHeight)} ?? .zero}
    var body:some View {
        Group {
            if let logo {
                VStack(alignment:centered ? .center : .leading,spacing:12) {
                    if hasEyebrow { eyebrow }
                    Image(uiImage:logo).resizable().interpolation(.high)
                        .frame(width:size.width,height:size.height)
                }
                .fixedSize(horizontal:false,vertical:true)
                .frame(width:width,height:height+(hasEyebrow ? 44 : 0),alignment:centered ? .bottom : .bottomLeading)
                .padding(.top,reserveHeadroom ? max(0,maxLogoHeight-height) : 0)
            } else {
                VStack(alignment:centered ? .center : .leading,spacing:12) {
                    if hasEyebrow { eyebrow }
                    Text(programme.title).font(titleFont ?? .system(size:large ? 46 : 36,weight:.bold)).lineLimit(titleLineLimit)
                        .multilineTextAlignment(centered ? .center : .leading)
                        .fixedSize(horizontal:false,vertical:true)
                }
                .frame(width:width,alignment:centered ? .center : .leading)
                .frame(minHeight:height+(hasEyebrow ? 44 : 0),alignment:centered ? .bottom : .bottomLeading)
            }
        }
            .accessibilityLabel(programme.title)
            .task(id:programme.logoSource) {
                logo=nil
                guard let source=programme.logoSource else {return}
                let loaded=await ArtworkCache.shared.image(source,maxPixel:1400)
                guard !Task.isCancelled else {return}
                withAnimation(reduceMotion ? nil : .easeOut(duration:0.18)) {logo=loaded}
            }
    }
    private var eyebrow:some View {
        HStack(spacing:20) {
            Brands(items:brands)
            if let rating {RatingBadge(rating:rating)}
        }.frame(height:32)
    }

}
struct HeroArtwork:View {
    let source:String?
    var height:CGFloat=WatchDesign.heroHeight
    var body:some View {
        GeometryReader {proxy in
            let imageHeight=max(height,WatchDesign.heroArtworkHeight)
            ZStack(alignment:.topTrailing) {
                Color.black
                Artwork(source:source,maxPixel:2400)
                    .frame(width:imageHeight*16/9,height:imageHeight)
                    .overlay {
                        LinearGradient(stops:[.init(color:.black,location:0),.init(color:.black.opacity(0.45),location:0.25),.init(color:.clear,location:0.5)],startPoint:.leading,endPoint:.trailing)
                    }
                LinearGradient(stops:[.init(color:.clear,location:0.65),.init(color:.black,location:1)],startPoint:.top,endPoint:.bottom)
                    .frame(height:height)
            }.frame(width:proxy.size.width,height:height,alignment:.topTrailing).clipped()
        }.frame(height:height)
    }
}
struct CardSurface<Content:View>:View {
    @Environment(\.watchCardWidth) private var width
    @ViewBuilder let content:Content
    var body:some View {
        content.frame(width:width-WatchDesign.cardInset*2,alignment:.topLeading)
            .padding(WatchDesign.cardInset)
            .frame(width:width,alignment:.topLeading)
            .background(.white.opacity(0.055),in:RoundedRectangle(cornerRadius:WatchDesign.radius))
            .multilineTextAlignment(.leading)
    }
}
struct Tile:View {
    let programme:Programme
    @Environment(\.watchCardWidth) private var width
    private var imageWidth:CGFloat { width-WatchDesign.cardInset*2 }
    private var liveProgress:Double {
        guard let now=programme.guide?.now,let start=now.start,let end=now.end,end>start else { return 0 }
        return min(1,max(0,(Date().timeIntervalSince1970-start)/(end-start)))
    }
    var body:some View {
        CardSurface {
            VStack(alignment:.leading,spacing:12) {
                Artwork(source:programme.artwork).frame(width:imageWidth,height:imageWidth*9/16)
                    .overlay(alignment:.topLeading) {
                        if programme.live {
                            HStack(alignment:.top) {
                                Artwork(source:programme.channelLogo,fit:true,maxPixel:180).frame(width:64,height:32).padding(8).background(.black.opacity(0.68),in:RoundedRectangle(cornerRadius:9))
                                Spacer()
                                Text("LIVE").font(.system(size:15,weight:.bold)).tracking(0.5).padding(.horizontal,9).padding(.vertical,7).background(.red.opacity(0.9),in:Capsule())
                            }.padding(12)
                        } else if !programme.brands.isEmpty { CardBrands(items:programme.brands).padding(12) }
                    }.clipShape(RoundedRectangle(cornerRadius:12))
                Text(programme.live ? (programme.guide?.now?.title ?? programme.title) : programme.title)
                    .font(WatchDesign.title).foregroundStyle(.white).lineLimit(2).frame(height:58,alignment:.topLeading)
                if programme.live {
                    Text(programme.guide?.now?.subtitle ?? "")
                        .font(WatchDesign.detail).foregroundStyle(WatchDesign.muted)
                        .lineLimit(2).frame(height:50,alignment:.topLeading)
                    HStack { Text(programme.title); Spacer(); Text(programme.guide?.now?.time ?? "") }.font(WatchDesign.detail).foregroundStyle(WatchDesign.muted)
                    ProgressView(value:liveProgress).tint(.white).frame(height:5).accessibilityLabel("Current programme progress")
                    Text(programme.guide?.next.map { "Next  \($0.time ?? "")  \($0.title ?? "")" } ?? "Programme guide is updating")
                        .font(WatchDesign.detail).foregroundStyle(WatchDesign.muted).lineLimit(2).frame(height:50,alignment:.topLeading)
                } else {
                    Text(programme.description?.isEmpty == false ? programme.description! : (programme.discoveryRef != nil ? "Explore episodes" : (programme.film ? programme.preferred?.durationText ?? "Film" : programme.episodeCountLabel)))
                        .font(WatchDesign.detail).foregroundStyle(WatchDesign.muted).lineLimit(2)
                        .frame(height:50,alignment:.topLeading)
                    ProgressView(value:min(1,(programme.resume?.progress ?? 0)/100))
                        .tint(.white).opacity((programme.resume?.resumeSeconds ?? 0)>0 ? 1 : 0)
                        .frame(height:5)

                }
            }
        }.overlay(alignment:.topTrailing) {
            if let rating=programme.contentRating { RatingBadge(rating:rating).padding(25) }
        }.accessibilityElement(children:.combine)
    }
}
struct RatingBadge:View {
    let rating:String
    var body:some View {
        Text(rating).font(.system(size:18,weight:.bold)).padding(.horizontal,8).padding(.vertical,5)
            .background(.black.opacity(0.8),in:RoundedRectangle(cornerRadius:6))
            .overlay { RoundedRectangle(cornerRadius:6).strokeBorder(.white.opacity(0.6),lineWidth:1) }
            .foregroundStyle(.white).accessibilityLabel("UK age rating \(rating)")
    }
}
struct EpisodeTile:View {
    let episode:Episode
    let programme:Programme
    @Environment(\.watchCardWidth) private var width
    var body:some View {
        VStack(alignment:.leading,spacing:12) {
            Artwork(source:episode.thumbnail ?? programme.artwork).frame(width:width,height:width*9/16)
                .overlay(alignment:.bottomTrailing) {if !episode.brands.isEmpty {CardBrands(items:episode.brands).padding(12)}}
                .clipShape(RoundedRectangle(cornerRadius:WatchDesign.radius))
            VStack(alignment:.leading,spacing:10) {
                Text(episode.title).font(WatchDesign.title).lineLimit(2).frame(height:58,alignment:.topLeading)
                Text(episode.compactCaption).font(WatchDesign.detail).foregroundStyle(WatchDesign.muted).lineLimit(1)
                Text(episode.description ?? "").font(WatchDesign.detail).foregroundStyle(WatchDesign.muted).lineLimit(2).frame(height:50,alignment:.topLeading)
                ProgressView(value:min(1,(episode.progress ?? 0)/100)).tint(.white).opacity((episode.resumeSeconds ?? 0)>0 ? 1 : 0).frame(height:4)
            }.padding(.horizontal,6)
        }.frame(width:width,alignment:.topLeading).accessibilityElement(children:.combine)
    }
}

struct SectionHeading:View {
    let title:String
    var subtitle:String?=nil
    var body:some View {
        VStack(alignment:.leading,spacing:7) {
            Text(title).font(WatchDesign.heading).foregroundStyle(.white)
            if let subtitle { Text(subtitle).font(WatchDesign.detail).foregroundStyle(WatchDesign.muted) }
        }
    }
}
struct QuietState:View {
    let symbol:String
    let title:String
    let message:String
    var body:some View {
        VStack(spacing:18) {
            Image(systemName:symbol).font(.system(size:42,weight:.light)).foregroundStyle(.white.opacity(0.45))
            Text(title).font(.system(size:30,weight:.semibold))
            Text(message).font(WatchDesign.body).foregroundStyle(WatchDesign.muted).multilineTextAlignment(.center).frame(maxWidth:760)
        }.frame(maxWidth:.infinity,minHeight:280).padding(40)
    }
}

// Preserve the full, crisp photograph; contrast is local to the lower caption.
struct PreloadBackground:View {
    var artwork:String? = nil
    var body:some View {
        GeometryReader { geometry in
            ZStack {
                Artwork(source:artwork,maxPixel:2560)
                LinearGradient(stops:[.init(color:.clear,location:0),
                                      .init(color:.black.opacity(0.12),location:0.30),
                                      .init(color:.black.opacity(0.78),location:0.67),
                                      .init(color:.black.opacity(0.96),location:1)],
                               startPoint:.top,endPoint:.bottom)
            }.frame(width:geometry.size.width,height:geometry.size.height)
        }.ignoresSafeArea()
    }
}

// Shared by discovery and playback: no fabricated progress, no blurred artwork.
struct WarmupScreen:View {
    let programme:Programme
    var episode:Episode? = nil
    var artwork:String? = nil
    var metadata:PlaybackMetadata? = nil
    var status:String
    var failed=false
    private var title:String {
        if programme.live { return metadata?.title ?? programme.guide?.now?.title ?? programme.title }
        if programme.film,episode?.title == programme.title { return "" }
        return episode?.title ?? ""
    }
    private var synopsis:String {
        if programme.live { return metadata?.description ?? programme.guide?.now?.subtitle ?? "" }
        return episode?.description ?? programme.description ?? ""
    }
    var body:some View {
        ZStack(alignment:.bottom) {
            PreloadBackground(artwork:artwork ?? programme.hero ?? programme.artwork)
            VStack(spacing:18) {
                if programme.live {
                    Artwork(source:metadata?.channelLogo ?? programme.channelLogo,fit:true,maxPixel:480)
                        .frame(width:160,height:64)
                } else {
                    ProgrammeTitle(programme:programme,centered:true,width:540,height:120,maxLogoHeight:250,providerEyebrow:true)
                }
                if !title.isEmpty {
                    Text(title).font(.system(size:programme.live ? 36 : 27,weight:.semibold))
                        .lineLimit(2).multilineTextAlignment(.center).frame(maxWidth:850)
                }
                if let episode,!programme.live,!episode.caption.isEmpty {
                    Text(episode.caption).font(.system(size:19,weight:.medium)).foregroundStyle(.white.opacity(0.65))
                }
                if !synopsis.isEmpty {
                    Text(synopsis).font(.system(size:22)).foregroundStyle(.white.opacity(0.80))
                        .lineLimit(2).multilineTextAlignment(.center).frame(maxWidth:820)
                }
                HStack(spacing:14) {
                    if !failed { ProgressView().controlSize(.small) }
                    Text(status).font(.system(size:19,weight:.medium)).foregroundStyle(.white.opacity(0.65))
                        .lineLimit(3).multilineTextAlignment(.center)
                }.frame(minHeight:30).padding(.top,14)
            }.padding(.horizontal,88).padding(.bottom,82)
                .frame(maxWidth:.infinity).allowsHitTesting(false)
        }.frame(maxWidth:.infinity,maxHeight:.infinity).accessibilityElement(children:.combine)
    }
}

// Shelf dimensions share the same artwork, focus treatment and baseline. Only
// editorial prominence changes; no recommendation ordering is invented here.
enum BrowseCardStyle {case standard,continuing,landscape,portrait,showcase}
struct CinematicProgrammeCard:View {
    let programme:Programme
    var style:BrowseCardStyle = .portrait
    var shelf=false
    var episodeCollection:String?=nil
    var explicitEpisode:Episode?=nil
    @Environment(\.watchCardWidth) private var availableWidth
    @State private var artworkHasTitle=true
    private var editorial:Bool {style == .portrait || style == .showcase || style == .landscape}
    private var portrait:Bool {(style == .portrait || style == .showcase) && programme.poster?.isEmpty == false}
    private var width:CGFloat {shelf ? (style == .showcase ? 480 : portrait ? 310 : 440) : availableWidth}
    private var height:CGFloat {portrait ? width*1.5 : width*9/16}
    private var episode:Episode? {if let explicitEpisode {return explicitEpisode};return episodeCollection == "christmas" ? programme.episodes.first{EditorialShelves.matchesChristmas(programme,$0)} : programme.resume ?? programme.preferred}
    private var source:String? {if episodeCollection == "christmas" {return episode?.thumbnail ?? programme.artwork};return portrait ? programme.poster : (editorial ? programme.cardArtwork ?? programme.hero ?? programme.artwork : episode?.thumbnail ?? programme.artwork)}
    private var caption:String {
        guard let episode else {return ""}
        var parts:[String]=[]
        if !programme.film {
            if let season=episode.seasonNumber {parts.append("S\(season)")}
            if let number=episode.episodeNumber,number>0 {parts.append("E\(number)")}
        }
        let identity=parts.joined(separator:", ")
        return [episodeCollection == "christmas" ? programme.editionLabel ?? "" : "",identity,episode.durationSeconds.flatMap {$0>0 ? "\(Int(($0/60).rounded()))m" : nil} ?? ""].filter{!$0.isEmpty}.joined(separator:" • ")
    }
    var body:some View {
        ZStack(alignment:.bottomLeading) {
            Artwork(source:source,fit:portrait,maxPixel:style == .showcase ? 1400 : 900)
                .frame(width:width,height:height)
            if !portrait {LinearGradient(colors:[.clear,.black.opacity(0.82)],startPoint:.center,endPoint:.bottom)}
            // A finished portrait poster already contains its title treatment.
            // Keep it intact instead of stamping a second logo over the first.
            if editorial && !portrait && !artworkHasTitle {
                VStack(spacing:12) {
                    ProgrammeTitle(programme:programme,large:false,titleFont:.system(size:style == .showcase ? 34 : 27,weight:.bold),titleLineLimit:3,centered:true,width:width-44,height:70,maxLogoHeight:portrait ? (style == .showcase ? 155 : 115) : 85,reserveHeadroom:portrait)
                }.padding(22).frame(width:width,alignment:.bottom)
            } else if !editorial && !portrait {
                HStack(alignment:.bottom,spacing:12) {
                    VStack(alignment:.leading,spacing:5) {
                        if episodeCollection == "christmas",let episode {Text(episode.title).font(.system(size:20,weight:.semibold)).lineLimit(1)}
                        Text(caption.isEmpty ? programme.title : caption)
                            .font(.system(size:episodeCollection == "christmas" ? 18 : 21,weight:.medium)).lineLimit(1)
                    }
                    Spacer(minLength:0)
                    Brands(items:episode?.brands.isEmpty == false ? episode!.brands : programme.brands)
                }.padding(.horizontal,22).padding(.bottom,22)
                if let episode,(episode.resumeSeconds ?? 0)>0 {
                    GeometryReader {proxy in
                        Capsule().fill(.white.opacity(0.3))
                            .overlay(alignment:.leading) {Capsule().fill(.white).frame(width:proxy.size.width*min(1,max(0,(episode.progress ?? ((episode.resumeSeconds ?? 0)/max(1,episode.durationSeconds ?? 1)*100))/100)))}
                    }.frame(height:4).padding(.horizontal,22).padding(.bottom,9)
                }
            }
            if style == .continuing {
                ZStack(alignment:.topLeading) {
                    EllipticalGradient(stops:[.init(color:.black.opacity(0.56),location:0),.init(color:.black.opacity(0.3),location:0.45),.init(color:.clear,location:1)],center:UnitPoint(x:0.18,y:0.22),startRadiusFraction:0,endRadiusFraction:0.85)
                        .frame(width:width,height:height)
                    ContinueWatchingIdentity(programme:programme,width:min(220,width*0.53))
                        .padding(.top,28).padding(.leading,22)
                }.frame(width:width,height:height,alignment:.topLeading)
            }
            if editorial,let edition=programme.editionLabel {
                VStack {Spacer();HStack {Text(edition).font(.system(size:17,weight:.semibold)).padding(.horizontal,12).padding(.vertical,7).background(.black.opacity(0.78),in:Capsule());Spacer()}}
                    .padding(.horizontal,16).padding(.bottom,16)
            }
            if programme.hasNewEpisode && episodeCollection == nil {
                VStack {HStack {if style == .continuing {Spacer()};Text("New episode").font(.system(size:17,weight:.semibold)).foregroundStyle(.black).padding(.horizontal,12).padding(.vertical,7).background(.white,in:RoundedRectangle(cornerRadius:6));if style != .continuing {Spacer()}};Spacer()}.padding(16)
            }
        }.frame(width:width,height:height).clipShape(RoundedRectangle(cornerRadius:WatchDesign.radius))
            .task(id:(source ?? "")+programme.title) {
                artworkHasTitle=true
                if editorial,!portrait,let source {artworkHasTitle=await ArtworkCache.shared.containsTitle(source,title:programme.title)}
            }
            .accessibilityElement(children:.ignore)
            .accessibilityLabel([programme.title,portrait ? nil : episode?.title,portrait ? nil : caption,programme.hasNewEpisode ? "New episode" : nil].compactMap{$0}.joined(separator:", "))
    }
}
