import SwiftUI
import AVKit

struct PlaybackSelection: Identifiable {
    let id = UUID()
    let programme: Programme
    let episode: Episode
    let position: Double
}

@MainActor final class PlaybackModel: ObservableObject {
    let api: WatchAPI
    let selection: PlaybackSelection
    let player = AVPlayer()
    @Published var nativeTransport=false
    @Published var preparing = true
    @Published var hasStarted=false
    @Published var reconnecting=false
    private var stalls=0
    private var stableSince:Date?
    @Published var buffering = true
    @Published var error: String?
    @Published var metadata: PlaybackMetadata?
    @Published var needsChannel5SignIn=false
    private var fairPlay:(any NativeKeySession)?
    private var itvHTTP:ITVProbeHTTP?
    @Published var signInProvider:SignInProvider?
    private var directBBC=false
    private var forceRelay=false
    private var ticket: String?
    private var task: Task<Void, Never>?
    private var timeObserver: Any?
    private var status: NSKeyValueObservation?
    private var itemStatus: NSKeyValueObservation?
    private var ended: NSObjectProtocol?
    private var failedToEnd:NSObjectProtocol?
    private var stalled: NSObjectProtocol?
    private var watchdog: Task<Void, Never>?
    private var savedAt = Date.distantPast
    private var waitingSince: Date?
    private var pausedAt: Date?
    private var offset: Double = 0
    @Published private(set) var position: Double = 0
    @Published var isPlaying=false
    private var retries = 0
    private var closed = false
    private var finished = false
    private var generation = 0
    init(api:WatchAPI, selection:PlaybackSelection) { self.api=api; self.selection=selection; position=selection.position; player.allowsExternalPlayback=false }

    func begin(at requested:Double? = nil, automatic:Bool = false, keepFrame:Bool = false) {
        guard !closed else { return }
        finished=false; generation += 1; let mine=generation
        task?.cancel(); player.pause()
        if let ticket { let old=position; Task { await api.progress(ticket:ticket,position:old) } }
        let previous=ticket; ticket=nil; preparing=true; reconnecting=automatic || keepFrame; buffering=true; error=nil
        pausedAt=nil; waitingSince=nil; stableSince=nil; needsChannel5SignIn=false;signInProvider=nil
        let start=selection.programme.live ? 0 : max(0,requested ?? position)
        position=start
        task=Task {
            if let previous { await api.release(ticket:previous) }
            do {
                if automatic { try await Task.sleep(for:.seconds([2,5,10][min(max(retries-1,0),2)])) }
                let prepared=try await api.prepare(id:selection.episode.id,position:start,preferDirect:!forceRelay)
                guard mine==generation, !Task.isCancelled, !closed else {
                    if let ticket=prepared.ticket { Task { await api.release(ticket:ticket) } }; return
                }
                guard let ticket=prepared.ticket, let metadata=prepared.metadata else { throw WatchError(message:"The Pi returned an incomplete playback response.") }
                self.ticket=ticket; self.metadata=metadata; self.offset=metadata.startPosition ?? start
                let item:AVPlayerItem
                var nextFairPlay:(any NativeKeySession)?
                var nextITVHTTP:ITVProbeHTTP?
                if let native=prepared.native, native.provider == "channel5" {
                    let source=try await Channel5PlaybackAPI.shared.source(id:native.id,live:native.live)
                    guard mine==generation, !Task.isCancelled, !closed else { return }
                    guard let config=source.channel5FairPlay,let certificate=source.fairPlayCertificate else { throw WatchError(message:"Channel 5 did not provide Apple TV playback details.") }
                    let asset=AVURLAsset(url:source.url)
                    let keys=Channel5FairPlaySession(config:config,certificate:certificate) { [weak self] message,failed in
                        guard failed else { return }
                        Task { @MainActor in
                            guard let self,self.generation==mine,!self.closed else { return }
                            self.player.pause();self.buffering=false;self.error=message
                        }
                    }
                    keys.attach(to:asset);nextFairPlay=keys;item=AVPlayerItem(asset:asset);directBBC=false
                } else if let native=prepared.native,native.provider == "u" || native.provider == "itv" {
                    let source = native.provider == "u" ? try await UPlaybackAPI.shared.source(id:native.id) : try await ITVPlaybackAPI.shared.source(native)
                    guard mine==generation,!Task.isCancelled,!closed else {return}
                    guard let certificate=source.fairPlayCertificate else {throw WatchError(message:"The provider did not supply Apple TV playback details.")}
                    let asset=AVURLAsset(url:source.url)
                    let report:@Sendable (String,Bool)->Void = { [weak self] message,failed in
                        guard failed else {return};Task {@MainActor in guard let self,self.generation==mine,!self.closed else {return};self.player.pause();self.buffering=false;self.error=message}
                    }
                    if native.provider == "u",let config=source.uFairPlay {nextFairPlay=UFairPlaySession(config:config,certificate:certificate,report:report)}
                    else {let http=ITVProbeHTTP();nextITVHTTP=http;nextFairPlay=ITVFairPlaySession(certificate:certificate,http:http,report:report)}
                    nextFairPlay?.attach(to:asset);item=AVPlayerItem(asset:asset);directBBC=false
                } else {
                    guard let raw=prepared.url,let url=URL(string:raw) else { throw WatchError(message:"The playback address is missing.") }
                    item=AVPlayerItem(url:url);directBBC=prepared.native?.provider == "bbc"
                }
                nativeTransport=prepared.native != nil
                if nativeTransport { self.offset=0 }
                item.preferredForwardBufferDuration=selection.programme.live ? 45 : 30
                if selection.programme.live {
                    item.canUseNetworkResourcesForLiveStreamingWhilePaused=true
                    item.configuredTimeOffsetFromLive=CMTime(seconds:30,preferredTimescale:600)
                    item.automaticallyPreservesTimeOffsetFromLive=true
                }
                let previousFairPlay=fairPlay;fairPlay=nextFairPlay;let oldITVHTTP=itvHTTP;itvHTTP=nextITVHTTP
                item.externalMetadata=Self.assetMetadata(metadata)
                attach(item); player.replaceCurrentItem(with:item); previousFairPlay?.stop();oldITVHTTP?.cancel(); player.automaticallyWaitsToMinimizeStalling=true
                if let initialSeek=prepared.initialSeek, initialSeek>0 {
                    await player.seek(to:CMTime(seconds:initialSeek,preferredTimescale:600),toleranceBefore:.zero,toleranceAfter:.zero)
                    guard mine==generation, !closed else { return }
                }
                preparing=false; reconnecting=false; pausedAt=nil; waitingSince=Date(); player.play(); installObservers()
            } catch {
                guard mine==generation, !Task.isCancelled, !closed else { return }
                preparing=false; reconnecting=false; buffering=false
                if case Channel5Error.signInRequired = error { needsChannel5SignIn=true }
                else if case ITVAccountError.signInRequired = error {signInProvider = .itv}
                else if case UError.signInRequired = error {signInProvider = .u}
                else if (automatic || selection.programme.live) && retries<6 {
                    retries += 1;begin(automatic:true,keepFrame:true)
                } else { self.error=error.localizedDescription }
            }
        }
    }
    static func assetMetadata(_ meta:PlaybackMetadata) -> [AVMetadataItem] {
        let pairs:[(AVMetadataIdentifier,String)] = [(.commonIdentifierTitle,meta.showTitle == meta.title ? meta.title : "\(meta.showTitle ?? "") · \(meta.title)"),(.commonIdentifierDescription,meta.description ?? "")]
        return pairs.filter { !$0.1.isEmpty }.map { identifier,value in let item=AVMutableMetadataItem(); item.identifier=identifier; item.value=value as NSString; item.extendedLanguageTag="en"; return item }
    }
    func attach(_ item:AVPlayerItem) {
        if let ended { NotificationCenter.default.removeObserver(ended) }
        if let stalled { NotificationCenter.default.removeObserver(stalled) }
        if let failedToEnd { NotificationCenter.default.removeObserver(failedToEnd) }
        let mine=generation
        itemStatus=item.observe(\.status,options:[.new]) { [weak self] item,_ in
            if item.status == .failed { Task { @MainActor in guard self?.generation==mine else { return };self?.recover() } }
        }
        ended=NotificationCenter.default.addObserver(forName:.AVPlayerItemDidPlayToEndTime,object:item,queue:.main) { [weak self] _ in Task { @MainActor in self?.didEnd() } }
        failedToEnd=NotificationCenter.default.addObserver(forName:.AVPlayerItemFailedToPlayToEndTime,object:item,queue:.main) { [weak self] _ in
            Task { @MainActor in guard self?.generation==mine else { return };self?.recover() }
        }
        stalled=NotificationCenter.default.addObserver(forName:.AVPlayerItemPlaybackStalled,object:item,queue:.main) { [weak self] _ in Task { @MainActor in if self?.waitingSince == nil { self?.waitingSince=Date() }; self?.stalls += 1; self?.buffering=true } }
    }
    func installObservers() {
        guard timeObserver == nil else { return }
        timeObserver=player.addPeriodicTimeObserver(forInterval:CMTime(seconds:1,preferredTimescale:600),queue:.main) { [weak self] time in Task { @MainActor in self?.tick(time) } }
        status=player.observe(\.timeControlStatus,options:[.initial,.new]) { [weak self] player,_ in
            Task { @MainActor in
                guard let self, !self.preparing, !self.closed else { return }
                switch player.timeControlStatus {
                case .waitingToPlayAtSpecifiedRate: self.isPlaying=true; self.stableSince=nil; self.buffering=true; if self.waitingSince == nil { self.waitingSince=Date() }
                case .playing:
                    self.isPlaying=true;self.hasStarted=true
                    self.pausedAt=nil; self.buffering=false; self.waitingSince=nil; if self.stableSince == nil { self.stableSince=Date() }
                case .paused: self.isPlaying=false; self.pausedAt=Date(); self.buffering=false; self.waitingSince=nil
                @unknown default: break
                }
            }
        }
        watchdog=Task { [weak self] in
            while !Task.isCancelled {
                do { try await Task.sleep(for:.seconds(5)) } catch { return }
                guard let self, !self.closed else { return }
                if let since=self.waitingSince, Date().timeIntervalSince(since)>60, !self.preparing { self.recover() }
                if let ticket=self.ticket { await self.api.progress(ticket:ticket,position:self.position,completed:self.finished,state:self.player.timeControlStatus == .playing ? "playing" : (self.buffering ? "buffering" : "paused"),metrics:self.metrics) }
            }
        }
    }
    func tick(_ time:CMTime) {
        guard !preparing, !closed, !finished, time.seconds.isFinite else { return }
        if let since=stableSince,Date().timeIntervalSince(since)>90 { retries=0 }
        position=offset+max(0,time.seconds)
        if let duration=metadata?.durationSeconds, duration>0 { position=min(duration,position) }
        if player.timeControlStatus == .playing, Date().timeIntervalSince(savedAt)>10 {
            savedAt=Date(); if let ticket { let current=position; Task { await api.progress(ticket:ticket,position:current) } }
        }
    }
    private var metrics:[String:Double] {
        let current=player.currentTime().seconds
        let buffer=player.currentItem?.loadedTimeRanges.compactMap { value -> Double? in
            let range=value.timeRangeValue
            guard current.isFinite,CMTimeRangeContainsTime(range,time:player.currentTime()) else { return nil }
            return max(0,CMTimeRangeGetEnd(range).seconds-current)
        }.max() ?? 0
        let size=player.currentItem?.presentationSize ?? .zero
        return ["buffer_seconds":buffer,"stalls":Double(stalls),"retries":Double(retries),"video_width":size.width,"video_height":size.height]
    }
    func recover() {
        guard !preparing, !closed, error == nil else { return }
        if retries>=6 { player.pause(); buffering=false; error="Playback is having trouble reconnecting. Your position has been saved."; return }
        if directBBC { forceRelay=true }; retries += 1; begin(automatic:true)
    }
    func didEnd() {
        let duration=self.duration
        if !selection.programme.live && duration>0 && position>=duration-12 {
            finished=true; position=duration
            if let ticket { Task { await api.progress(ticket:ticket,position:duration,completed:true) } }
            buffering=false
        } else { recover() }
    }
    func retry() { retries=0; begin() }
    var duration:Double {
        let nativeDuration=player.currentItem?.duration.seconds ?? 0
        if nativeTransport,nativeDuration.isFinite,nativeDuration>0 { return nativeDuration }
        return metadata?.durationSeconds ?? selection.episode.durationSeconds ?? 0
    }
    var quality:String? {
        let size=player.currentItem?.presentationSize ?? .zero
        return StreamQuality.label(width:size.width,height:size.height) ?? metadata?.quality
    }
    func pause() { player.pause(); isPlaying=false }
    func toggle() {
        if isPlaying { pause() } else if !preparing { player.play();isPlaying=true }
    }
    func jump(to seconds:Double) {
        let absolute=EpisodeTimeline.clamp(seconds,duration:duration)
        let relative=absolute-offset
        let target=CMTime(seconds:relative,preferredTimescale:600)
        let buffered=relative>=0 && (player.currentItem?.seekableTimeRanges.contains { CMTimeRangeContainsTime($0.timeRangeValue,time:target) } ?? false)
        if buffered {
            buffering=true; position=absolute
            player.seek(to:target,toleranceBefore:.zero,toleranceAfter:.zero) { [weak self] done in
                Task { @MainActor in guard let self,!self.closed else { return };if done { self.player.play();self.isPlaying=true;self.buffering=false } else { self.begin(at:absolute,keepFrame:true) } }
            }
        } else { retries=0;begin(at:absolute,keepFrame:true) }
    }
    func close() {
        guard !closed else { return }; closed=true; generation += 1; task?.cancel(); watchdog?.cancel(); player.pause()
        if let timeObserver { player.removeTimeObserver(timeObserver) }; timeObserver=nil
        status=nil; itemStatus=nil
        if let ended { NotificationCenter.default.removeObserver(ended) }; if let stalled { NotificationCenter.default.removeObserver(stalled) };if let failedToEnd { NotificationCenter.default.removeObserver(failedToEnd) }
        if let ticket { let final=position; let completed=finished; Task { await api.progress(ticket:ticket,position:final,completed:completed); await api.release(ticket:ticket) } }; ticket=nil
        player.replaceCurrentItem(with:nil);fairPlay?.stop();fairPlay=nil;itvHTTP?.cancel();itvHTTP=nil
    }
}

struct NativePlayer: UIViewControllerRepresentable {
    @ObservedObject var model:PlaybackModel
    var customTransport=false
    func makeCoordinator() -> Coordinator { Coordinator() }
    func makeUIViewController(context:Context) -> AVPlayerViewController {
        let controller=AVPlayerViewController(); controller.player=model.player
        controller.showsPlaybackControls = !customTransport; controller.view.isUserInteractionEnabled = !customTransport; controller.transportBarIncludesTitleView=true
        controller.appliesPreferredDisplayCriteriaAutomatically=true
        controller.allowsPictureInPicturePlayback=true
        controller.playbackControlsIncludeInfoViews=true
        controller.delegate=context.coordinator
        controller.loadViewIfNeeded()
        if !customTransport { context.coordinator.install(in:controller) }
        return controller
    }
    func updateUIViewController(_ controller:AVPlayerViewController,context:Context) {
        controller.showsPlaybackControls = !customTransport
        controller.view.isUserInteractionEnabled = !customTransport
        controller.contentOverlayView?.isHidden=customTransport
        guard !customTransport else { return }
        context.coordinator.install(in:controller)
        context.coordinator.update(item:model.player.currentItem,metadata:model.metadata)
        guard !model.selection.programme.live && !model.nativeTransport else { controller.transportBarCustomMenuItems=[]; return }
        var actions=[UIAction(title:"Start over",image:UIImage(systemName:"backward.end.fill")) { _ in model.jump(to:0) }]
        let duration=model.metadata?.durationSeconds ?? model.selection.episode.durationSeconds ?? 0
        if duration>0 {
            for second in stride(from:300,to:Int(duration),by:300) {
                actions.append(UIAction(title:String(format:"%d:%02d",second/60,second%60)) { _ in model.jump(to:Double(second)) })
            }
        }
        controller.transportBarCustomMenuItems=[UIMenu(title:"Go to…",image:UIImage(systemName:"clock.arrow.circlepath"),children:actions)]
    }
    @MainActor final class Coordinator: NSObject, @preconcurrency AVPlayerViewControllerDelegate {
        private var installed=false
        private let badge=UIVisualEffectView(effect:UIBlurEffect(style:.dark))
        private let label=UILabel()
        private let brandHost=UIHostingController(rootView:AnyView(EmptyView()))
        private var item:AVPlayerItem?
        private var dimensions:NSKeyValueObservation?
        private var fallback:String?
        private var controlsVisible=false
        private var announced=false
        private var announcement:Task<Void,Never>?
        func install(in controller:AVPlayerViewController) {
            guard !installed,let overlay=controller.contentOverlayView else { return }
            installed=true
            badge.translatesAutoresizingMaskIntoConstraints=false
            badge.isUserInteractionEnabled=false; badge.layer.cornerRadius=9; badge.clipsToBounds=true; badge.isHidden=true
            label.translatesAutoresizingMaskIntoConstraints=false; label.font = .systemFont(ofSize:23,weight:.semibold)
            label.textColor = .white; label.textAlignment = .center
            badge.contentView.addSubview(label); overlay.addSubview(badge)
            controller.addChild(brandHost)
            brandHost.view.backgroundColor = .clear; brandHost.view.isUserInteractionEnabled=false
            brandHost.view.translatesAutoresizingMaskIntoConstraints=false
            overlay.addSubview(brandHost.view); brandHost.didMove(toParent:controller)
            NSLayoutConstraint.activate([
                brandHost.view.topAnchor.constraint(equalTo:badge.topAnchor),
                brandHost.view.leadingAnchor.constraint(equalTo:overlay.safeAreaLayoutGuide.leadingAnchor,constant:36),
                brandHost.view.widthAnchor.constraint(equalToConstant:240),
                brandHost.view.heightAnchor.constraint(equalToConstant:46)
            ])
            NSLayoutConstraint.activate([
                badge.topAnchor.constraint(equalTo:overlay.safeAreaLayoutGuide.topAnchor,constant:22),
                badge.trailingAnchor.constraint(equalTo:overlay.safeAreaLayoutGuide.trailingAnchor,constant:-36),
                label.leadingAnchor.constraint(equalTo:badge.contentView.leadingAnchor,constant:14),
                label.trailingAnchor.constraint(equalTo:badge.contentView.trailingAnchor,constant:-14),
                label.topAnchor.constraint(equalTo:badge.contentView.topAnchor,constant:8),
                label.bottomAnchor.constraint(equalTo:badge.contentView.bottomAnchor,constant:-8)
            ])
        }
        func update(item:AVPlayerItem?,metadata:PlaybackMetadata?) {
            let brands=metadata?.brands ?? []
            brandHost.rootView=AnyView(CardBrands(items:brands).frame(maxWidth:.infinity,alignment:.leading))
            brandHost.view.isHidden=brands.isEmpty
            fallback=metadata.flatMap { StreamQuality.label(width:$0.streamWidth ?? 0,height:$0.streamHeight ?? 0) ?? $0.quality }
            if self.item !== item {
                self.item=item; announced=false; announcement?.cancel()
                dimensions=item?.observe(\.presentationSize,options:[.initial,.new]) { [weak self] _,_ in
                    Task { @MainActor in self?.refresh() }
                }
            }
            refresh()
        }
        private func refresh() {
            let size=item?.presentationSize ?? .zero
            let quality=StreamQuality.label(width:size.width,height:size.height) ?? fallback
            label.text=quality; badge.isHidden=quality == nil
            badge.accessibilityLabel=quality.map { "Stream quality: \($0)" }
            if !announced, size.width>0, size.height>0, quality != nil {
                announced=true; badge.alpha=1; brandHost.view.alpha=1
                announcement=Task { [weak self] in
                    do { try await Task.sleep(for:.seconds(5)) } catch { return }
                    guard let self, !self.controlsVisible else { return }
                    UIView.animate(withDuration:UIAccessibility.isReduceMotionEnabled ? 0 : 0.25) { self.badge.alpha=0; self.brandHost.view.alpha=0 }
                }
            }
        }
        func playerViewController(_ playerViewController:AVPlayerViewController,willTransitionToVisibilityOfTransportBar visible:Bool,with coordinator:AVPlayerViewControllerAnimationCoordinator) {
            controlsVisible=visible
            coordinator.addCoordinatedAnimations({ self.badge.alpha=visible ? 1 : 0; self.brandHost.view.alpha=visible ? 1 : 0 },completion:nil)
        }
    }
}

struct PlayerScreen: View {
    @Environment(\.dismiss) private var dismiss
    @StateObject private var model:PlaybackModel
    init(selection:PlaybackSelection) { _model=StateObject(wrappedValue:PlaybackModel(api:WatchAPI(),selection:selection)) }
    private var startupArtwork:String? {
        if model.selection.programme.live { return model.metadata?.artwork ?? model.selection.programme.guide?.now?.image ?? model.selection.programme.artwork }
        return model.selection.programme.hero ?? model.selection.programme.artwork
    }
    var body: some View {
        ZStack {
            Color.black.ignoresSafeArea()
            NativePlayer(model:model,customTransport:!model.selection.programme.live && !model.nativeTransport).ignoresSafeArea()
            if !model.selection.programme.live && !model.nativeTransport && model.error == nil && !model.needsChannel5SignIn && model.signInProvider == nil {
                EpisodeTransport(model:model,close:{ dismiss() })
            }
            if !model.hasStarted && model.error == nil && !model.needsChannel5SignIn && model.signInProvider == nil {
                WarmupScreen(programme:model.selection.programme,episode:model.selection.episode,
                             artwork:startupArtwork,metadata:model.metadata,
                             status:model.reconnecting ? "Reconnecting" : "Starting playback")
            } else if (model.buffering || model.reconnecting) && model.error == nil {
                ProgressView().scaleEffect(1.15).padding(28).background(.ultraThinMaterial,in:RoundedRectangle(cornerRadius:18)).allowsHitTesting(false)
            }
            if let provider=model.signInProvider {ProviderSignIn(provider:provider,onConnected:{model.retry()}).frame(width:1050).background(.black)}
            if model.needsChannel5SignIn {
                Channel5SignIn(onConnected:{ model.retry() }).frame(width:1050).background(.black)
            }
            if let error=model.error {
                VStack(spacing:24) {
                    Image(systemName:"wifi.exclamationmark").font(.system(size:38,weight:.light)).foregroundStyle(.white.opacity(0.7))
                    Text("Let’s pick up where you were").font(.system(size:30,weight:.semibold))
                    Text(error).font(.system(size:23)).foregroundStyle(WatchDesign.muted).multilineTextAlignment(.center).frame(width:680)
                    HStack(spacing:28) {
                        Button("Retry") { model.retry() }.buttonStyle(.borderedProminent)
                        Button("Back to library") { dismiss() }
                    }.font(.system(size:24,weight:.medium)).padding(.top,8)
                }.padding(44).background(.regularMaterial,in:RoundedRectangle(cornerRadius:24))
            }
        }.task { model.begin() }.onDisappear { model.close() }
    }
}

// The standard tvOS plain-button focus effect draws a filled plate over the
// label's bounds. Full-screen reveal and timeline controls must never use it.
private struct TransportBareButtonStyle:ButtonStyle {
    func makeBody(configuration:Configuration) -> some View { configuration.label }
}
private struct TransportControlStyle:ButtonStyle {
    let selected:Bool
    func makeBody(configuration:Configuration) -> some View {
        configuration.label
            .foregroundStyle(.white)
            .padding(.horizontal,22).padding(.vertical,14)
            .background(.white.opacity(selected ? 0.18 : 0.055),in:RoundedRectangle(cornerRadius:12))
            .overlay { RoundedRectangle(cornerRadius:12).strokeBorder(.white.opacity(selected ? 0.8 : 0),lineWidth:2) }
            .opacity(configuration.isPressed ? 0.75 : 1)
            .fixedSize(horizontal:true,vertical:true)
    }
}

// tvOS's live HLS scrubber only knows the rolling window. This transport uses the
// episode duration and absolute source position while preserving the native decoder.
struct EpisodeTransport:View {
    @ObservedObject var model:PlaybackModel
    let close:()->Void
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @State private var visible=true
    @State private var preview:Double?
    @State private var repeats=0
    @State private var lastStep=Date.distantPast
    @State private var activity=UUID()
    @FocusState private var focus:Control?
    private enum Control:Hashable { case timeline,play,restart,close,screen }
    private var selection:Programme { model.selection.programme }
    private var shown:Double { preview ?? model.position }
    private var fraction:Double { model.duration>0 ? min(1,max(0,shown/model.duration)) : 0 }
    var body:some View {
        ZStack {
            if !visible {
                Button { reveal() } label:{ Color.clear.frame(maxWidth:.infinity,maxHeight:.infinity).contentShape(Rectangle()) }
                    .buttonStyle(TransportBareButtonStyle()).focusEffectDisabled().focused($focus,equals:.screen).accessibilityLabel("Show playback controls")
                    .onMoveCommand { _ in reveal() }
            }
            if visible {
                VStack(alignment:.leading) {
                    HStack(alignment:.top) {
                        CardBrands(items:model.metadata?.brands ?? model.selection.episode.brands)
                        if let rating=selection.contentRating { RatingBadge(rating:rating) }
                        Spacer()
                        if let quality=model.quality {
                            Text(quality).font(.system(size:23,weight:.semibold)).padding(.horizontal,15).padding(.vertical,8)
                                .background(.black.opacity(0.6),in:RoundedRectangle(cornerRadius:9))
                        }
                    }
                    Spacer()
                    VStack(alignment:.leading,spacing:16) {
                        HStack(alignment:.center,spacing:30) {
                            ProgrammeTitle(programme:selection,large:false).frame(width:380,height:75,alignment:.leading)
                            VStack(alignment:.leading,spacing:8) {
                                if model.selection.episode.title != selection.title {
                                    Text(model.selection.episode.title).font(.system(size:26,weight:.semibold)).lineLimit(1)
                                }
                                Text(model.selection.episode.description ?? selection.description ?? "")
                                    .font(.system(size:22)).foregroundStyle(.white.opacity(0.75)).lineLimit(2)
                            }.frame(maxWidth:.infinity,alignment:.leading)
                        }
                        Button { commit() } label:{
                            VStack(spacing:12) {
                                GeometryReader { proxy in
                                    ZStack(alignment:.leading) {
                                        Capsule().fill(.white.opacity(0.25))
                                        Capsule().fill(.white).frame(width:max(0,proxy.size.width*fraction))
                                        Circle().fill(.white).frame(width:focus == .timeline ? 22 : 13,height:focus == .timeline ? 22 : 13)
                                            .offset(x:min(max(0,proxy.size.width*fraction-7),proxy.size.width-14))
                                    }.frame(height:6).frame(maxHeight:.infinity)
                                }.frame(height:24)
                                HStack {
                                    Text(EpisodeTimeline.time(shown)).monospacedDigit()
                                    Spacer()
                                    Text(preview == nil ? (focus == .timeline ? "Left / right to seek" : "Pause, then press up to seek") : "Press OK to play from here")
                                    Spacer()
                                    Text(EpisodeTimeline.time(model.duration)).monospacedDigit()
                                }.font(.system(size:20)).foregroundStyle(.white.opacity(0.8))
                            }.padding(.vertical,8).padding(.horizontal,12)
                                .background(focus == .timeline ? .white.opacity(0.10) : .clear,in:RoundedRectangle(cornerRadius:12))
                        }.buttonStyle(TransportBareButtonStyle()).focusEffectDisabled().focused($focus,equals:.timeline)
                            .accessibilityLabel("Episode timeline").accessibilityValue("\(EpisodeTimeline.time(shown)) of \(EpisodeTimeline.time(model.duration))")
                            .onMoveCommand { direction in
                                if direction == .left { move(-1) }
                                else if direction == .right { move(1) }
                                else if direction == .down { cancelPreview();focus = .play }
                            }
                        HStack(spacing:25) {
                            Button { preview == nil ? model.toggle() : commit();touch() } label:{ Label(model.isPlaying ? "Pause" : "Play",systemImage:model.isPlaying ? "pause.fill" : "play.fill") }
                                .buttonStyle(TransportControlStyle(selected:focus == .play)).focusEffectDisabled().focused($focus,equals:.play)
                            Button { preview=nil;model.jump(to:0);touch() } label:{ Label("Start over",systemImage:"backward.end") }.buttonStyle(TransportControlStyle(selected:focus == .restart)).focusEffectDisabled().focused($focus,equals:.restart)
                            Spacer()
                            Button("Back to library",action:close).buttonStyle(TransportControlStyle(selected:focus == .close)).focusEffectDisabled().focused($focus,equals:.close)
                        }.font(.system(size:23,weight:.medium))
                            .onMoveCommand { if $0 == .up { model.pause();focus = .timeline;touch() } }
                    }
                }.padding(.horizontal,88).padding(.vertical,60)
                    .background(LinearGradient(stops:[.init(color:.black.opacity(0.45),location:0),.init(color:.clear,location:0.2),.init(color:.clear,location:0.42),.init(color:.black.opacity(0.93),location:0.83),.init(color:.black,location:1)],startPoint:.top,endPoint:.bottom))
                    .transition(.opacity)
            }
        }
        .onPlayPauseCommand { if preview != nil { commit() } else { model.toggle();reveal() } }
        .onExitCommand {
            if preview != nil { cancelPreview();focus = .play }
            else if visible && model.isPlaying { hide() }
            else { close() }
        }
        .onChange(of:model.isPlaying) { _,playing in if !playing && preview == nil && focus != .timeline { reveal() };touch() }
        .onChange(of:focus) { _,_ in touch() }
        .task(id:activity) {
            guard model.isPlaying,preview == nil,visible else { return }
            do { try await Task.sleep(for:.seconds(6)) } catch { return }
            guard model.isPlaying,preview == nil else { return };hide()
        }
        .onAppear { focus = .play }
    }
    private func touch() { activity=UUID() }
    private func reveal() { withAnimation(reduceMotion ? nil : .easeOut(duration:0.2)) { visible=true };focus = .play;touch() }
    private func hide() { withAnimation(reduceMotion ? nil : .easeOut(duration:0.2)) { visible=false };focus = .screen }
    private func move(_ direction:Double) {
        model.pause()
        repeats=Date().timeIntervalSince(lastStep)<0.75 ? repeats+1 : 0;lastStep=Date()
        preview=EpisodeTimeline.clamp(shown+direction*EpisodeTimeline.step(repeats:repeats),duration:model.duration)
        touch()
    }
    private func commit() {
        if let preview { model.jump(to:preview);self.preview=nil;repeats=0 }
        else if !model.isPlaying { model.toggle() }
        focus = .play;touch()
    }
    private func cancelPreview() { preview=nil;repeats=0;touch() }
}
