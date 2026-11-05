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
    @Published var selection: PlaybackSelection
    let player = AVPlayer()
    @Published var chapters:[PlaybackInterval]=[]
    @Published var skipMarkers:[PlaybackInterval]=[]
    private var dismissedSkipIDs=Set<String>()
    @Published var nextEpisode:NextEpisode?
    @Published var showUpNext=false
    @Published var creditsCue:PlaybackInterval?
    private var creditsState=CreditsCueState()
    @Published var countdown:Int?
    @Published var nextMessage:String?
    @Published var switchingEpisode=false
    @Published var autoplay=UserDefaults.standard.bool(forKey:"watch.autoplayNext")
    private var queueSnapshot:SeriesQueue?
    private var extrasTask:Task<Void,Never>?
    private var planningTask:Task<Void,Never>?
    private var completionTask:Task<Void,Never>?
    private var countdownTask:Task<Void,Never>?
    private var autoplayCancelled=false
    private var catalogueWarmTask:Task<Void,Never>?
    private var warmedNext:PlaybackSelection?
    private var transitionTask:Task<Void,Never>?
    private var completionGate=EpisodeCompletionGate()
    private var playWhenReady=true
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
    private var sceneLighting:SceneLightingSampler?
    private var directBBC=false
    private var uhdActive=false
    private var forceHD=false
    private let bbcUHD=UHDPlaybackAccess()
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
    private var pausedPosition:Double?
    private var offset: Double = 0
    @Published private(set) var position: Double = 0
    @Published var isPlaying=false
    private var retries = 0
    private var closed = false
    private var finished = false
    private var generation = 0
    init(api:WatchAPI, selection:PlaybackSelection) { self.api=api; self.selection=selection; position=selection.position; player.allowsExternalPlayback=false }

    func begin(at requested:Double? = nil, automatic:Bool = false, keepFrame:Bool = false, playWhenReady:Bool = true) {
        guard !closed else { return }
        self.playWhenReady=playWhenReady
        extrasTask?.cancel();planningTask?.cancel();completionTask?.cancel();cancelCountdown()
        chapters=[];skipMarkers=[];nextEpisode=nil;queueSnapshot=nil;showUpNext=false;creditsCue=nil
        completionGate.reset();autoplayCancelled=false;warmedNext=nil;catalogueWarmTask?.cancel()
        finished=false; generation += 1; let mine=generation
        sceneLighting?.stop();sceneLighting=nil
        task?.cancel(); player.pause();bbcUHD.stop();uhdActive=false
        if let ticket { let old=position; Task { await api.progress(ticket:ticket,position:old) } }
        let previous=ticket; ticket=nil; preparing=true; reconnecting=automatic || keepFrame; buffering=true; error=nil
        pausedAt=nil; pausedPosition=nil; waitingSince=nil; stableSince=nil; needsChannel5SignIn=false;signInProvider=nil
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
                guard let ticket=prepared.ticket, var metadata=prepared.metadata else { throw WatchError(message:"The Pi returned an incomplete playback response.") }
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
                } else if let native=prepared.native,native.provider == "channel4" {
                    let source=try await Channel4PlaybackAPI.shared.source(id:native.id,live:true)
                    guard mine==generation,!Task.isCancelled,!closed else {return}
                    guard let config=source.channel4FairPlay,let certificate=source.fairPlayCertificate else {throw WatchError(message:"Channel 4 did not supply Apple TV playback details.")}
                    let asset=AVURLAsset(url:source.url)
                    nextFairPlay=Channel4FairPlaySession(config:config,certificate:certificate) { [weak self] message,failed in
                        guard failed else {return}
                        Task { @MainActor in
                            guard let self,self.generation==mine,!self.closed else {return}
                            self.player.pause();self.buffering=false;self.error=message
                        }
                    }
                    nextFairPlay?.attach(to:asset);item=AVPlayerItem(asset:asset);directBBC=false
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
                    var selectedURL=url
                    if prepared.native?.provider == "bbc" {UHDIdentityVault.diagnostic("bbc-playback")}
                    if let native=prepared.native,native.provider == "bbc",!native.live,!forceHD,UHDIdentityVault.isConfigured {
                        let pid=String(native.id.suffix(8))
                        do {
                            UHDIdentityVault.diagnostic("requesting-uhd")
                            let source=try await bbcUHD.source(for:BBCUHDProgramme(id:pid,version:metadata.versionId ?? ""))
                            guard mine==generation,!Task.isCancelled,!closed else {bbcUHD.stop();return}
                            selectedURL=source.url;metadata.versionId=source.versionID;self.metadata=metadata;uhdActive=true;UHDIdentityVault.diagnostic("uhd-ready")
                        } catch is CancellationError {throw CancellationError()}
                        catch {bbcUHD.stop();UHDIdentityVault.diagnostic("hd-fallback",error:error)} // Keep the verified HD route if BBC offers no compatible UHD.
                    }
                    item=AVPlayerItem(url:selectedURL);directBBC=prepared.native?.provider == "bbc" && !uhdActive
                }
                nativeTransport=prepared.native != nil
                if nativeTransport { self.offset=0 }
                item.preferredForwardBufferDuration=selection.programme.live ? 45 : 30
                item.automaticallyPreservesTimeOffsetFromLive=false
                if selection.programme.live {
                    item.canUseNetworkResourcesForLiveStreamingWhilePaused=true
                    item.configuredTimeOffsetFromLive=CMTime(seconds:30,preferredTimescale:600)
                }
                let previousFairPlay=fairPlay;fairPlay=nextFairPlay;let oldITVHTTP=itvHTTP;itvHTTP=nextITVHTTP
                item.externalMetadata=Self.assetMetadata(metadata)
                attach(item); player.replaceCurrentItem(with:item); previousFairPlay?.stop();oldITVHTTP?.cancel(); player.automaticallyWaitsToMinimizeStalling=true
                let lighting=SceneLightingSampler(api:api);sceneLighting=lighting
                lighting.attach(item:item,player:player,ticket:ticket,accessible:nextFairPlay == nil)
                if let initialSeek=prepared.initialSeek, initialSeek>0 || (!selection.programme.live && !nativeTransport) {
                    await player.seek(to:CMTime(seconds:initialSeek,preferredTimescale:600),toleranceBefore:.zero,toleranceAfter:.zero)
                    guard mine==generation, !closed else { return }
                }
                preparing=false; reconnecting=false; pausedAt=nil; waitingSince=playWhenReady ? Date() : nil
                if playWhenReady {player.play()} else {player.pause();isPlaying=false;buffering=false;pausedPosition=start}
                installObservers()
                loadExtras(generation:mine,ticket:ticket,source:metadata.sourceKey,version:metadata.versionId,bbc:prepared.native?.provider == "bbc" || metadata.brands?.contains(where:{$0.name.localizedCaseInsensitiveContains("iPlayer")}) == true)
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
        let pairs:[(AVMetadataIdentifier,String)] = [(.commonIdentifierTitle,meta.title),(.commonIdentifierDescription,meta.description ?? "")]
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
        ended=NotificationCenter.default.addObserver(forName:.AVPlayerItemDidPlayToEndTime,object:item,queue:.main) { [weak self] _ in Task { @MainActor in guard self?.generation==mine else {return};self?.didEnd() } }
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
                    // System/Control Centre play commands can bypass toggle().
                    // Honour the same paused anchor before advancing progress.
                    if let anchor=self.pausedPosition, self.playWhenReady {
                        self.pausedPosition=nil;self.jump(to:anchor);return
                    }
                    self.playWhenReady=true;self.isPlaying=true;self.hasStarted=true
                    self.pausedAt=nil; self.buffering=false; self.waitingSince=nil; if self.stableSince == nil { self.stableSince=Date() }
                case .paused: if !self.selection.programme.live && self.pausedPosition == nil { self.pausedPosition=self.position }; self.isPlaying=false; self.pausedAt=Date(); self.buffering=false; self.waitingSince=nil
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
        guard !preparing, !closed, !finished, time.seconds.isFinite, pausedPosition == nil else { return }
        if let since=stableSince,Date().timeIntervalSince(since)>90 { retries=0 }
        position=offset+max(0,time.seconds)
        if player.timeControlStatus == .playing {completionGate.played(at:position)}
        if let cue=creditsCue,!cue.contains(position) {creditsCue=nil}
        if creditsCue == nil {
            creditsCue=creditsState.offer(markers:chapters,position:position,duration:duration,
                playing:player.timeControlStatus == .playing,hasNext:nextEpisode != nil,
                blocked:preparing || buffering || reconnecting || showUpNext || finished || error != nil || selection.programme.live)
        }
        if let duration=metadata?.durationSeconds, duration>0 { position=min(duration,position) }
        if !selection.programme.live,nextEpisode != nil,!autoplayCancelled {
            countdown = autoplay && duration>10 && position>=duration-10 && position<duration ? max(1,Int(ceil(duration-position))) : nil
            if creditsCue != nil {warmNextCatalogue()}
        } else {countdown=nil}
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
        if uhdActive { forceHD=true } else if directBBC { forceRelay=true }; retries += 1; begin(automatic:true,playWhenReady:playWhenReady)
    }
    func didEnd() {
        guard !finished,!closed,!preparing else {return}
        sceneLighting?.stop();
        let now=player.currentTime().seconds
        let actual=now.isFinite ? offset+max(0,now) : position
        if completionGate.accept(position:actual,duration:duration,live:selection.programme.live,failed:error != nil || buffering) {
            finished=true;position=duration;isPlaying=false;buffering=false;player.pause()
            completeEpisode()
        } else if !selection.programme.live && actual>=duration-1.5 && duration>0 {
            // A user seek to the end stops here without completing/advancing.
            isPlaying=false;buffering=false;player.pause()
        } else {recover()}
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
    func pause() {
        playWhenReady=false
        if !selection.programme.live {
            let seconds=player.currentTime().seconds
            if seconds.isFinite {position=offset+max(0,seconds)}
            pausedPosition=position
        }
        player.pause(); isPlaying=false
    }
    func toggle() {
        guard !finished else {cancelCountdown();return}
        if isPlaying { pause() }
        else if !preparing {
            playWhenReady=true
            if let anchor=pausedPosition { pausedPosition=nil;jump(to:anchor) }
            else { player.play();isPlaying=true }
        }
    }
    // AVKit performs the actual seek. Clear Watch's paused anchor so the
    // subsequent native play command cannot jump back to the pre-scrub position.
    func nativeSeek(to time:CMTime) {
        guard time.seconds.isFinite,!selection.programme.live else {return}
        let absolute=EpisodeTimeline.clamp(offset+max(0,time.seconds),duration:duration)
        completionGate.sought(to:absolute);pausedPosition=nil;playWhenReady=true
        position=absolute;creditsCue=nil
    }
    func goLive() {
        guard selection.programme.live,!preparing else {return}
        playWhenReady=true
        if let range=player.currentItem?.seekableTimeRanges.last?.timeRangeValue {
            let target=max(range.start.seconds,CMTimeRangeGetEnd(range).seconds-15)
            guard target.isFinite else {return}
            buffering=true
            let mine=generation
            player.seek(to:CMTime(seconds:target,preferredTimescale:600)) { [weak self] _ in
                Task { @MainActor in guard let self,self.generation==mine,!self.closed else {return};self.player.play();self.isPlaying=true }
            }
        } else {begin(keepFrame:true)}
    }
    func jump(to seconds:Double,resume:Bool = true) {
        guard !finished else {return}
        playWhenReady=resume
        pausedPosition=nil
        let absolute=EpisodeTimeline.clamp(seconds,duration:duration)
        completionGate.sought(to:absolute)
        let mine=generation
        let relative=absolute-offset
        let target=CMTime(seconds:relative,preferredTimescale:600)
        let buffered=relative>=0 && (player.currentItem?.seekableTimeRanges.contains { CMTimeRangeContainsTime($0.timeRangeValue,time:target) } ?? false)
        if buffered {
            buffering=true; position=absolute
            player.seek(to:target,toleranceBefore:.zero,toleranceAfter:.zero) { [weak self] done in
                Task { @MainActor in guard let self,!self.closed,self.generation==mine else { return };if done {
                        if resume {self.player.play()} else {self.player.pause();self.pausedPosition=absolute}
                        self.isPlaying=resume;self.buffering=false
                    } else {self.begin(at:absolute,keepFrame:true,playWhenReady:resume);self.completionGate.sought(to:absolute)} }
            }
        } else { retries=0;begin(at:absolute,keepFrame:true,playWhenReady:resume);completionGate.sought(to:absolute) }
    }
    var activeSkip:PlaybackInterval? {
        guard hasStarted,!preparing,!buffering,!reconnecting,!finished,error == nil,!showUpNext,creditsCue == nil else {return nil}
        return skipMarkers.first {$0.contains(position) && !dismissedSkipIDs.contains($0.id)}
    }
    func loadExtras(generation mine:Int,ticket:String,source:String?,version:String?,bbc:Bool) {
        extrasTask?.cancel();planningTask?.cancel()
        chapters=[];skipMarkers=[];nextEpisode=nil;queueSnapshot=nil
        extrasTask=Task { [weak self] in
            guard let self,let source else {return}
            guard let capability=try? await api.playbackCapabilities(),capability.schemaVersion==1,!Task.isCancelled else {return}
            guard let result=try? await api.features(episode:selection.episode.id,source:source,version:version,ticket:ticket),
                  !Task.isCancelled,generation==mine,!closed,result.matches(episode:selection.episode.id,source:source,version:version) else {return}
            chapters=capability.chapters ? result.chapters.filter {$0.valid(duration:duration) && !(bbc && version == nil && ["credits","end_credits"].contains($0.kind))} : []
            skipMarkers = bbc && version == nil ? [] : result.skipMarkers.filter {capability.skipMarkers.contains($0.kind) && $0.valid(duration:duration)}
        }
        guard !selection.programme.live,!selection.programme.film else {return}
        planningTask=Task { [weak self] in
            guard let self else {return}
            do {
                let capability=try await api.playbackCapabilities()
                guard capability.schemaVersion==1,capability.seriesQueue else {return}
                let upcoming=try await api.upNext(episode:selection.episode.id)
                guard !Task.isCancelled,generation==mine,!closed,upcoming.episodeId==selection.episode.id else {return}
                nextEpisode=upcoming.nextEpisode
                var queue=try await api.queue()
                guard !Task.isCancelled,generation==mine,!closed else {return}
                if queue.current?.id != selection.episode.id || queue.autoplay != autoplay {
                    queue=try await api.seedQueue(episode:selection.episode.id,revision:queue.revision,autoplay:autoplay)
                }
                guard !Task.isCancelled,generation==mine,!closed else {return}
                queueSnapshot=queue
                nextEpisode=queue.successor(of:selection.episode.id)
            } catch {
                guard !Task.isCancelled,generation==mine,!closed else {return}
                // Do not replay a conflicting mutation. Metadata alone can still
                // offer an explicit next action; autoplay needs a coherent queue.
                queueSnapshot=nil
                if (error as? WatchHTTPError)?.status==409,
                   let latest=try? await api.queue(),!Task.isCancelled,generation==mine,!closed {
                    if latest.current?.id==selection.episode.id,latest.autoplay==autoplay {queueSnapshot=latest;nextEpisode=latest.successor(of:selection.episode.id)}
                }
            }
        }
    }
    func dismissSkip(_ marker:PlaybackInterval) {dismissedSkipIDs.insert(marker.id);objectWillChange.send()}
    func skip(_ marker:PlaybackInterval) {
        guard skipMarkers.contains(marker),marker.contains(position),marker.valid(duration:duration) else {return}
        jump(to:marker.end,resume:isPlaying)
    }
    func selectChapter(_ chapter:PlaybackInterval) {
        guard chapters.contains(chapter),chapter.valid(duration:duration) else {return}
        jump(to:chapter.start,resume:isPlaying)
    }
    func setAutoplay(_ enabled:Bool) {
        autoplay=enabled;UserDefaults.standard.set(enabled,forKey:"watch.autoplayNext")
        cancelCountdown()
        guard !finished,let queue=queueSnapshot,queue.current?.id==selection.episode.id else {return}
        let mine=generation
        planningTask?.cancel()
        planningTask=Task { [weak self] in
            guard let self else {return}
            do {
                let updated=try await api.seedQueue(episode:selection.episode.id,revision:queue.revision,autoplay:enabled)
                guard !Task.isCancelled,generation==mine,!closed else {return};queueSnapshot=updated
            } catch {
                guard !Task.isCancelled,generation==mine,!closed else {return};queueSnapshot=nil
                if (error as? WatchHTTPError)?.status==409,
                   let latest=try? await api.queue(),!Task.isCancelled,generation==mine,!closed,
                   latest.current?.id==selection.episode.id,latest.autoplay==enabled {queueSnapshot=latest}
            }
        }
    }
    func cancelCountdown() {countdownTask?.cancel();countdownTask=nil;countdown=nil}
    func cancelAutoplay() {autoplayCancelled=true;cancelCountdown()}
    private func warmNextCatalogue() {
        guard catalogueWarmTask == nil,let next=nextEpisode else {return}
        let mine=generation
        catalogueWarmTask=Task { [weak self] in
            guard let self,let library=try? await api.library(),!Task.isCancelled,generation==mine,!closed,
                  let programme=library.first(where:{$0.episodes.contains {$0.id==next.id}}),
                  let episode=programme.episodes.first(where:{$0.id==next.id}) else {return}
            warmedNext=PlaybackSelection(programme:programme,episode:episode,position:0)
        }
    }
    func completeEpisode() {
        // Keep the compact card over the final frame during automatic handoff.
        // Do not briefly mount the manual/full-screen queue panel between episodes.
        let continuing=autoplay && !autoplayCancelled && nextEpisode != nil && queueSnapshot?.autoplay == true
        if !continuing {creditsCue=nil}
        cancelCountdown();planningTask?.cancel();showUpNext = !continuing
        guard let ticket else {showUpNext=true;return}
        let mine=generation;let episode=selection.episode.id;let at=position;let queue=queueSnapshot
        completionTask=Task { [weak self] in
            guard let self else {return}
            do {
                try await api.saveCompletion(ticket:ticket,position:at)
                guard !Task.isCancelled,generation==mine,!closed else {return}
                guard let queue,queue.current?.id==episode else {creditsCue=nil;showUpNext=true;return}
                let updated=try await api.advanceQueue(episode:episode,revision:queue.revision)
                guard !Task.isCancelled,generation==mine,!closed else {return}
                queueSnapshot=updated;nextEpisode=updated.current?.available == false ? nil : updated.current
                if autoplay,!autoplayCancelled,updated.autoplay,nextEpisode != nil {playNext()}
                else {creditsCue=nil;showUpNext=true}
            } catch {
                guard !Task.isCancelled,generation==mine,!closed else {return}
                // A lost response may have advanced on the server. Never repeat
                // the completion mutation automatically or start media on doubt.
                creditsCue=nil;showUpNext=true
                queueSnapshot=nil;nextMessage="Automatic continuation is unavailable. You can choose Play next."
                if (error as? WatchHTTPError)?.status==409,
                   let latest=try? await api.queue(),!Task.isCancelled,generation==mine,!closed {
                    if latest.current?.id != episode {nextEpisode=latest.current?.available == false ? nil : latest.current}
                }
            }
        }
    }
    func openUpNext() {creditsCue=nil;showUpNext=true}
    func dismissCreditsCue() {creditsCue=nil;cancelAutoplay()}
    func hideUpNext() {cancelAutoplay();showUpNext=false}
    func playNext() {
        guard !switchingEpisode,let next=nextEpisode,next.available != false else {return}
        cancelCountdown();switchingEpisode=true;nextMessage=nil
        let mine=generation
        transitionTask=Task { [weak self] in
            guard let self else {return}
            defer {switchingEpisode=false}
            do {
                // Resolve current catalogue membership only on the user's action
                // or completed countdown. This fetch does not prepare any video.
                let library = warmedNext?.episode.id == next.id ? [warmedNext!.programme] : try await api.library()
                guard !Task.isCancelled,generation==mine,!closed else {return}
                guard let programme=library.first(where:{$0.episodes.contains {$0.id==next.id}}),let episode=programme.episodes.first(where:{$0.id==next.id}) else {
                    nextMessage="That episode is no longer available.";nextEpisode=nil;creditsCue=nil;showUpNext=true;return
                }
                if let ticket {
                    await api.progress(ticket:ticket,position:position,completed:finished)
                    await api.release(ticket:ticket)
                }
                guard !Task.isCancelled,generation==mine,!closed else {return}
                ticket=nil
                completionTask?.cancel();selection=PlaybackSelection(programme:programme,episode:episode,position:0)
                position=0;hasStarted=false;showUpNext=false;nextMessage=nil;completionGate.reset();creditsState.reset();dismissedSkipIDs=[]
                begin(at:0)
            } catch {if !Task.isCancelled,generation==mine,!closed {nextMessage="Could not load the next episode. Please try again.";creditsCue=nil;showUpNext=true}}
        }
    }
    func close() {
        guard !closed else { return }; closed=true; generation += 1; task?.cancel(); watchdog?.cancel();catalogueWarmTask?.cancel(); player.pause()
        extrasTask?.cancel();planningTask?.cancel();completionTask?.cancel();transitionTask?.cancel();cancelCountdown()
        if let timeObserver { player.removeTimeObserver(timeObserver) }; timeObserver=nil
        status=nil; itemStatus=nil
        if let ended { NotificationCenter.default.removeObserver(ended) }; if let stalled { NotificationCenter.default.removeObserver(stalled) };if let failedToEnd { NotificationCenter.default.removeObserver(failedToEnd) }
        if let ticket { let final=position; let completed=finished; Task { await api.progress(ticket:ticket,position:final,completed:completed); await api.release(ticket:ticket) } }; ticket=nil
        sceneLighting?.stop();sceneLighting=nil
        bbcUHD.stop();player.replaceCurrentItem(with:nil);fairPlay?.stop();fairPlay=nil;itvHTTP?.cancel();itvHTTP=nil
    }
}

struct NativePlayer: UIViewControllerRepresentable {
    @ObservedObject var model:PlaybackModel
    var customTransport=false
    var close:()->Void = {}
    func makeCoordinator() -> Coordinator { Coordinator(model:model,close:close) }
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
        controller.showsPlaybackControls = !customTransport && !model.showUpNext && model.creditsCue == nil && model.activeSkip == nil
        controller.view.isUserInteractionEnabled = !customTransport && !model.showUpNext && model.creditsCue == nil && model.activeSkip == nil
        // AVKit's transport can retain a UIKit focus item even with hit testing
        // disabled. Remove its view from focus eligibility while our card owns
        // the remote; hiding the view does not pause or replace the stream.
        if controller.view.isHidden != model.showUpNext {
            controller.view.isHidden=model.showUpNext
            controller.setNeedsFocusUpdate()
        }
        controller.contentOverlayView?.isHidden=customTransport
        guard !customTransport else { return }
        context.coordinator.install(in:controller)
        context.coordinator.update(item:model.player.currentItem,metadata:model.metadata,programme:model.selection.programme,episode:model.selection.episode)
        guard !model.selection.programme.live else {controller.transportBarCustomMenuItems=[];return}
        var menus:[UIMenu]=[]
        if !model.chapters.isEmpty {
            let actions=model.chapters.map {chapter in UIAction(title:chapter.title+" · "+EpisodeTimeline.time(chapter.start)) {_ in model.selectChapter(chapter)}}
            menus.append(UIMenu(title:"Chapters",image:UIImage(systemName:"list.bullet"),children:actions))
        }
        var extras:[UIAction]=[]
        if let marker=model.activeSkip {extras.append(UIAction(title:marker.kind == "recap" ? "Skip recap" : "Skip intro",image:UIImage(systemName:"forward.end")) {_ in model.skip(marker)})}
        if model.nextEpisode != nil {extras.append(UIAction(title:"Up next",image:UIImage(systemName:"play.rectangle.on.rectangle")) {_ in model.openUpNext()})}
        if !extras.isEmpty {menus.append(UIMenu(title:"Episode",image:UIImage(systemName:"ellipsis.circle"),children:extras))}
        controller.transportBarCustomMenuItems=menus
    }

    @MainActor final class Coordinator: NSObject, @preconcurrency AVPlayerViewControllerDelegate {
        private weak var model:PlaybackModel?
        private let close:()->Void
        init(model:PlaybackModel,close:@escaping ()->Void) {self.model=model;self.close=close;super.init()}
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
                brandHost.view.topAnchor.constraint(equalTo:overlay.safeAreaLayoutGuide.topAnchor,constant:32),
                brandHost.view.leadingAnchor.constraint(equalTo:overlay.safeAreaLayoutGuide.leadingAnchor,constant:36),
                brandHost.view.widthAnchor.constraint(equalToConstant:460),
                brandHost.view.heightAnchor.constraint(equalToConstant:240)
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
        func update(item:AVPlayerItem?,metadata:PlaybackMetadata?,programme:Programme,episode:Episode) {
            brandHost.rootView=AnyView(PlayerLogoOverlay(programme:programme,episode:episode,metadata:metadata))
            brandHost.view.isHidden=false
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
        func playerViewControllerDidEndDismissalTransition(_ playerViewController:AVPlayerViewController) {close()}
        func playerViewController(_ playerViewController:AVPlayerViewController,timeToSeekAfterUserNavigatedFrom oldTime:CMTime,to targetTime:CMTime)->CMTime {
            model?.nativeSeek(to:targetTime)
            return targetTime
        }
        func playerViewController(_ playerViewController:AVPlayerViewController,willTransitionToVisibilityOfTransportBar visible:Bool,with coordinator:AVPlayerViewControllerAnimationCoordinator) {
            controlsVisible=visible
            coordinator.addCoordinatedAnimations({ self.badge.alpha=visible ? 1 : 0; self.brandHost.view.alpha=visible ? 1 : 0 },completion:nil)
        }
    }
}

// Non-interactive branding stays outside AVKit's remote/focus hierarchy.
private struct PlayerLogoOverlay:View {
    let programme:Programme
    let episode:Episode
    let metadata:PlaybackMetadata?
    var body:some View {
        VStack(alignment:.leading,spacing:12) {
            if programme.live {
                CardBrands(items:metadata?.brands ?? episode.brands)
                Artwork(source:metadata?.channelLogo ?? programme.channelLogo,fit:true,maxPixel:500)
                    .frame(width:240,height:90,alignment:.leading)
            } else {
                ProgrammeTitle(programme:programme,large:false,centered:false,width:400,height:90,maxLogoHeight:160,reserveHeadroom:true,providerEyebrow:true,brandItems:metadata?.brands ?? episode.brands,rating:nil)
            }
            Spacer(minLength:0)
        }.frame(width:440,height:230,alignment:.topLeading)
            .shadow(color:.black.opacity(0.85),radius:12,y:3)
            .allowsHitTesting(false).accessibilityHidden(true)
    }
}

struct PlayerScreen: View {
    @Environment(\.dismiss) private var dismiss
    @StateObject private var model:PlaybackModel
    @State private var showingChapters=false
    init(selection:PlaybackSelection) { _model=StateObject(wrappedValue:PlaybackModel(api:WatchAPI(),selection:selection)) }
    private var startupArtwork:String? {
        if model.selection.programme.live { return model.metadata?.artwork ?? model.selection.programme.guide?.now?.image ?? model.selection.programme.artwork }
        return model.selection.programme.hero ?? model.selection.programme.artwork
    }
    var body: some View {
        ZStack {
            Color.black.ignoresSafeArea()
            NativePlayer(model:model,close:{dismiss()}).ignoresSafeArea()
            if !model.hasStarted && model.error == nil && !model.needsChannel5SignIn && model.signInProvider == nil {
                WarmupScreen(programme:model.selection.programme,episode:model.selection.episode,
                             artwork:startupArtwork,metadata:model.metadata,
                             status:model.reconnecting ? "Reconnecting" : "Starting playback")
            } else if (model.buffering || model.reconnecting) && model.error == nil {
                ProgressView().scaleEffect(1.15).padding(28).background(.ultraThinMaterial,in:RoundedRectangle(cornerRadius:18)).allowsHitTesting(false)
            }
            if let marker=model.activeSkip {
                VStack {Spacer();HStack {Spacer();SkipIntervalCue(model:model,marker:marker)}}
                    .padding(.trailing,88).padding(.bottom,160)
            }
            if model.creditsCue != nil,let next=model.nextEpisode,!model.showUpNext,model.error == nil,!model.buffering {
                VStack {Spacer();HStack {Spacer();CreditsUpNextCard(model:model,next:next,close:{dismiss()})}}
                    .padding(.trailing,88).padding(.bottom,80)
            }
            if model.showUpNext && model.error == nil {
                Color.black.opacity(0.6).ignoresSafeArea()
                EpisodeUpNextPanel(model:model,close:{dismiss()})
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
            .sheet(isPresented:$showingChapters) {EpisodeChapters(model:model,close:{showingChapters=false})}

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
    var chapters:()->Void = {}
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @State private var visible=true
    @State private var preview:Double?
    @State private var repeats=0
    @State private var lastStep=Date.distantPast
    @State private var activity=UUID()
    @FocusState private var focus:Control?
    private enum Control:Hashable { case timeline,play,restart,close,screen,chapters,next }
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
                        Spacer()
                        if let quality=model.quality {
                            Text(quality).font(.system(size:23,weight:.semibold)).padding(.horizontal,15).padding(.vertical,8)
                                .background(.black.opacity(0.6),in:RoundedRectangle(cornerRadius:9))
                        }
                    }
                    Spacer()
                    VStack(alignment:.leading,spacing:16) {
                        HStack(alignment:.bottom,spacing:30) {
                            if selection.live {
                                VStack(spacing:12) {
                                    Brands(items:model.metadata?.brands ?? model.selection.episode.brands)
                                    Artwork(source:model.metadata?.channelLogo ?? selection.channelLogo,fit:true,maxPixel:400).frame(width:160,height:75)
                                }
                            } else {ProgrammeTitle(programme:selection,large:false,centered:true,width:380,height:75,maxLogoHeight:200,reserveHeadroom:false,providerEyebrow:true,brandItems:model.metadata?.brands ?? model.selection.episode.brands,rating:selection.contentRating)}
                            VStack(alignment:.leading,spacing:8) {
                                if selection.live || model.selection.episode.title != selection.title {
                                    Text(selection.live ? (model.metadata?.title ?? selection.guide?.now?.title ?? selection.title) : model.selection.episode.title).font(.system(size:26,weight:.semibold)).lineLimit(1)
                                }
                                Text(selection.live ? (model.metadata?.description ?? selection.guide?.now?.subtitle ?? "") : (model.selection.episode.description ?? selection.description ?? ""))
                                    .font(.system(size:22)).foregroundStyle(.white.opacity(0.75)).lineLimit(2)
                            }.frame(maxWidth:.infinity,alignment:.leading)
                        }
                        if !selection.live {
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
                        } else {
                            HStack(spacing:12) {
                                Circle().fill(.red).frame(width:9,height:9)
                                Text("LIVE").font(.system(size:19,weight:.bold))
                                if !model.isPlaying {Text("Paused").font(WatchDesign.detail).foregroundStyle(WatchDesign.muted)}
                                Spacer()
                                Text(selection.guide?.now?.time ?? "").font(WatchDesign.detail).foregroundStyle(WatchDesign.muted)
                            }.padding(.vertical,12)
                        }
                        HStack(spacing:25) {
                            Button { preview == nil ? model.toggle() : commit();touch() } label:{ Label(model.isPlaying ? "Pause" : "Play",systemImage:model.isPlaying ? "pause.fill" : "play.fill") }
                                .buttonStyle(TransportControlStyle(selected:focus == .play)).focusEffectDisabled().focused($focus,equals:.play)
                            Button { preview=nil;if selection.live {model.goLive()} else {model.jump(to:0)};touch() } label:{ Label(selection.live ? "Go live" : "Start over",systemImage:selection.live ? "dot.radiowaves.left.and.right" : "backward.end") }.buttonStyle(TransportControlStyle(selected:focus == .restart)).focusEffectDisabled().focused($focus,equals:.restart)
                            if !model.chapters.isEmpty {
                                Button("Chapters") {chapters();touch()}.buttonStyle(TransportControlStyle(selected:focus == .chapters)).focusEffectDisabled().focused($focus,equals:.chapters)
                            }
                            if model.nextEpisode != nil {
                                Button("Up next") {model.openUpNext();touch()}.buttonStyle(TransportControlStyle(selected:focus == .next)).focusEffectDisabled().focused($focus,equals:.next)
                            }
                            Spacer()
                            Button("Back to library",action:close).buttonStyle(TransportControlStyle(selected:focus == .close)).focusEffectDisabled().focused($focus,equals:.close)
                        }.font(.system(size:23,weight:.medium))
                            .onMoveCommand { if $0 == .up && !selection.live { model.pause();focus = .timeline;touch() } }
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

struct EpisodeUpNextPanel:View {
    @ObservedObject var model:PlaybackModel
    let close:()->Void
    @FocusState private var focused:Bool
    var body:some View {
        VStack(alignment:.leading,spacing:24) {
            HStack {
                Text(model.countdown.map {"Up next in \($0) seconds"} ?? (model.nextEpisode == nil ? "Episode finished" : "Up next"))
                    .font(.system(size:32,weight:.semibold)).monospacedDigit()
                Spacer()
            }
            if let next=model.nextEpisode {
                HStack(alignment:.top,spacing:30) {
                    Artwork(source:next.thumbnail ?? next.artwork,maxPixel:900).frame(width:470,height:265).clipShape(RoundedRectangle(cornerRadius:18))
                    VStack(alignment:.leading,spacing:12) {
                        Text(next.showTitle ?? model.selection.programme.title).font(.system(size:22)).foregroundStyle(WatchDesign.muted)
                        Text(next.title).font(.system(size:29,weight:.semibold)).lineLimit(2)
                        Text(next.caption).font(.system(size:20)).foregroundStyle(WatchDesign.muted)
                        if let description=next.description {Text(description).font(.system(size:21)).lineLimit(3).foregroundStyle(.white.opacity(0.8))}
                    }
                }
            }
            if let message=model.nextMessage {Text(message).font(WatchDesign.detail).foregroundStyle(WatchDesign.muted)}
            HStack(spacing:25) {
                if model.nextEpisode != nil {
                    Button(model.switchingEpisode ? "Loading…" : "Play next") {model.playNext()}.disabled(model.switchingEpisode).focused($focused)
                }
                if model.countdown != nil {
                    Button("Cancel autoplay") {model.cancelAutoplay()}
                } else {
                    Button("Close") {model.hideUpNext()}
                }
                Spacer()
                Button("Back to library",action:close)
            }.font(.system(size:23,weight:.medium))
            Toggle("Autoplay next episode",isOn:Binding(get:{model.autoplay},set:{model.setAutoplay($0)})).font(.system(size:21))
        }.padding(48).frame(width:1240).background(LinearGradient(colors:[Color(white:0.12),Color(white:0.035)],startPoint:.topLeading,endPoint:.bottomTrailing),in:RoundedRectangle(cornerRadius:30))
            .overlay {RoundedRectangle(cornerRadius:24).strokeBorder(.white.opacity(0.12),lineWidth:1)}
            .focusSection()
            .task {await Task.yield();focused=true}
            .onExitCommand {model.hideUpNext()}
    }
}
struct EpisodeChapters:View {
    @ObservedObject var model:PlaybackModel
    let close:()->Void
    var body:some View {
        ScrollView {
            VStack(alignment:.leading,spacing:20) {
                Text("Chapters").font(WatchDesign.heading).padding(.bottom,12)
                ForEach(model.chapters) {chapter in
                    Button {model.selectChapter(chapter);close()} label:{
                        HStack(spacing:24) {
                            Text(EpisodeTimeline.time(chapter.start)).monospacedDigit().foregroundStyle(WatchDesign.muted)
                            Text(chapter.title).lineLimit(2)
                            Spacer()
                            if chapter.contains(model.position) {Image(systemName:"waveform")}
                        }.font(WatchDesign.body).padding(16).frame(maxWidth:.infinity,alignment:.leading)
                    }
                }
                Button("Close",action:close).padding(.top,12)
            }.padding(64)
        }.frame(width:1100).background(WatchDesign.canvas).onExitCommand(perform:close)
    }
}


struct CreditsUpNextCard:View {
    @ObservedObject var model:PlaybackModel
    let next:NextEpisode
    let close:()->Void
    @FocusState private var playFocused:Bool
    var body:some View {
        VStack(alignment:.leading,spacing:14) {
            HStack(alignment:.center,spacing:18) {
                VStack(alignment:.leading,spacing:6) {
                    Text("UP NEXT").font(.system(size:15,weight:.bold)).tracking(2).foregroundStyle(.white.opacity(0.65))
                    Text(next.showTitle ?? model.selection.programme.title)
                        .font(.system(size:21,weight:.medium)).lineLimit(1)
                }
                Spacer(minLength:12)
                if let seconds=model.countdown {
                    ZStack {
                        Circle().stroke(.white.opacity(0.2),lineWidth:3)
                        Circle().trim(from:0,to:Double(seconds)/10).stroke(.white,lineWidth:3).rotationEffect(.degrees(-90))
                        Text("\(seconds)").font(.system(size:23,weight:.semibold)).monospacedDigit()
                    }.frame(width:50,height:50).accessibilityLabel("Next episode in \(seconds) seconds")
                }
            }
            HStack(alignment:.center,spacing:20) {
                Artwork(source:next.thumbnail ?? next.artwork,maxPixel:500)
                    .frame(width:176,height:99).clipped().clipShape(RoundedRectangle(cornerRadius:12))
                VStack(alignment:.leading,spacing:9) {
                    Text(next.title).font(.system(size:24,weight:.semibold)).lineLimit(2)
                    Text(next.caption).font(.system(size:17)).foregroundStyle(.white.opacity(0.65)).lineLimit(2)
                }.frame(maxWidth:.infinity,alignment:.leading)
            }.fixedSize(horizontal:false,vertical:true)
            HStack(spacing:26) {
                Button(model.switchingEpisode ? "Starting…" : "Next",systemImage:"play.fill") {model.playNext()}
                    .disabled(model.switchingEpisode).focused($playFocused)
                Button("Exit") {model.cancelAutoplay();close()}
            }.font(.system(size:20,weight:.medium)).padding(.top,10)
        }.padding(28).frame(width:610,alignment:.leading).fixedSize(horizontal:false,vertical:true)
            .background(LinearGradient(colors:[Color(white:0.1),Color(white:0.035)],startPoint:.topLeading,endPoint:.bottomTrailing),in:RoundedRectangle(cornerRadius:24))
            .overlay {RoundedRectangle(cornerRadius:24).strokeBorder(.white.opacity(0.14),lineWidth:1)}
            .shadow(color:.black.opacity(0.5),radius:26,y:12)
            .focusSection().task {await Task.yield();playFocused=true}
            .onExitCommand {model.cancelAutoplay();close()}
            .onPlayPauseCommand {model.toggle()}
    }
}

struct SkipIntervalCue:View {
    @ObservedObject var model:PlaybackModel
    let marker:PlaybackInterval
    @FocusState private var focused:Bool
    var body:some View {
        HStack(spacing:24) {
            Button(marker.kind == "recap" ? "Skip recap" : "Skip intro") {model.skip(marker)}.focused($focused)
            Button("Keep watching") {model.dismissSkip(marker)}
        }.font(.system(size:23,weight:.medium)).padding(24)
            .background(Color(white:0.06).opacity(0.95),in:RoundedRectangle(cornerRadius:18))
            .focusSection().task(id:marker.id) {await Task.yield();focused=true}
            .onExitCommand {model.dismissSkip(marker)}
            .onPlayPauseCommand {model.toggle()}
    }
}
