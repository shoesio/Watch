import AVFoundation
import CoreImage
import Vision
import SoundAnalysis

/// Samples only frames AVFoundation exposes. Never captures the screen or sends images.
@MainActor final class SceneLightingSampler {
    private let api:WatchAPI
    private weak var item:AVPlayerItem?
    private weak var player:AVPlayer?
    private var output:AVPlayerItemVideoOutput?
    private var task:Task<Void,Never>?
    private var last:SceneColour?
    private var window=SceneColourWindow()
    private var previousOptions:SceneLightingOptions?
    private var ticket:String?
    private var active=false
    private var accessible=false
    private var lookAheadAsset:AVAsset?
    var lookAheadStatusChanged:((String)->Void)?
    private var aheadStatus="Off"
    private func reportAhead(_ status:String) {if aheadStatus != status {aheadStatus=status;lookAheadStatusChanged?(status)}}
    private var aheadPlayer:AVPlayer?
    private var aheadItem:AVPlayerItem?
    private var aheadOutput:AVPlayerItemVideoOutput?
    private var aheadSeeking=false
    private var aheadFailed=false
    private var aheadGeneration=UUID()
    private var lastAheadSeek=Date.distantPast
    private var lookClock=SceneLookAheadClock()
    private let context=CIContext(options:[.cacheIntermediates:false])
    init(api:WatchAPI) {self.api=api}
    func attach(item:AVPlayerItem,player:AVPlayer,ticket:String,accessible:Bool,lookAheadAsset:AVAsset?=nil) {
        stop();self.item=item;self.player=player;self.ticket=ticket;self.accessible=accessible;self.lookAheadAsset=lookAheadAsset
        guard accessible else {return}
        startPolling()
    }
    func settingsChanged() {task?.cancel();window.reset();aheadFailed=false;startPolling()}
    private func startPolling() {
        guard accessible,let ticket,item != nil,player != nil else {return}
        task=Task { [weak self] in
            var first=true
            while !Task.isCancelled {
                let options=SceneLightingOptions.load()
                if !first {do {try await Task.sleep(for:.seconds(options.sampleInterval))} catch {return}}
                first=false
                guard let self,let item=self.item,let player=self.player else {return}
                guard UserDefaults.standard.bool(forKey:"watch.sceneLighting") else {
                    self.detachOutput();self.last=nil
                    if self.active {self.active=false;await self.api.stopSceneLighting(ticket:ticket)}
                    continue
                }
                if self.output==nil {
                    let settings:[String:Any]=[
                        kCVPixelBufferPixelFormatTypeKey as String:kCVPixelFormatType_32BGRA,
                        AVVideoColorPropertiesKey:[AVVideoColorPrimariesKey:AVVideoColorPrimaries_ITU_R_709_2,AVVideoTransferFunctionKey:AVVideoTransferFunction_ITU_R_709_2,AVVideoYCbCrMatrixKey:AVVideoYCbCrMatrix_ITU_R_709_2]
                    ]
                    let output=AVPlayerItemVideoOutput(outputSettings:settings)
                    output.suppressesPlayerRendering=false;item.add(output);self.output=output
                }
                if self.previousOptions != options {
                    self.window.reset()
                    if self.previousOptions?.lookAhead != options.lookAhead {self.lookClock.reset()}
                    self.previousOptions=options
                }
                guard item.status == .readyToPlay else {continue}
                let time=player.currentTime()
                let ahead=self.lookAheadBuffer(item:item,player:player,options:options)
                let current=self.output.flatMap{$0.hasNewPixelBuffer(forItemTime:time) ? $0.copyPixelBuffer(forItemTime:time,itemTimeForDisplay:nil) : nil}
                if player.timeControlStatus == .playing,let buffer=ahead ?? current,let colour=self.colour(buffer) {
                    var windowOptions=options
                    if options.matchBrightness || options.matchSaturation {windowOptions.neutralWhite=true}
                    if var dominant=self.window.append(colour,at:ProcessInfo.processInfo.systemUptime,options:windowOptions) {
                        if !options.neutralWhite && !options.matchSaturation && dominant.saturation==0 {
                            dominant=SceneColour(hue:self.last?.hue ?? 0,saturation:self.last?.saturation ?? 100,brightness:dominant.brightness)
                        }
                        self.last=self.last?.blended(towards:dominant) ?? dominant
                    }
                }
                guard let colour=self.last,!Task.isCancelled else {continue}
                self.active=true
                await self.api.sceneColour(ticket:ticket,colour:SceneColour(hue:HueCalibration.load().corrected(colour.hue),saturation:colour.saturation,brightness:colour.brightness),options:options)
            }
        }
    }
    private func lookAheadBuffer(item:AVPlayerItem,player:AVPlayer,options:SceneLightingOptions)->CVPixelBuffer? {
        let main=player.currentTime().seconds
        let lead=lookClock.lead(at:ProcessInfo.processInfo.systemUptime,position:main,playing:player.timeControlStatus == .playing,target:options.lookAhead)
        guard options.lookAhead>0 else {stopAhead();reportAhead("Off");return nil}
        guard player.timeControlStatus == .playing,main.isFinite,!aheadFailed else {aheadPlayer?.pause();if !aheadFailed {reportAhead("Ramps up on resume")};return nil}
        let buffered=item.loadedTimeRanges.compactMap {range->Double? in
            let value=range.timeRangeValue
            return CMTimeRangeContainsTime(value,time:player.currentTime()) ? max(0,CMTimeRangeGetEnd(value).seconds-main) : nil
        }.max()
        // The companion always yields to the real programme's buffer.
        if let buffered,buffered<6 {aheadPlayer?.pause();reportAhead("Waiting for programme buffer");return nil}
        if aheadPlayer == nil {
            reportAhead("Warming up")
            let copy=AVPlayerItem(asset:lookAheadAsset ?? item.asset)
            copy.preferredMaximumResolution=CGSize(width:320,height:180)
            copy.preferredPeakBitRate=500_000;copy.preferredForwardBufferDuration=5
            let output=AVPlayerItemVideoOutput(outputSettings:[kCVPixelBufferPixelFormatTypeKey as String:kCVPixelFormatType_32BGRA,AVVideoColorPropertiesKey:[AVVideoColorPrimariesKey:AVVideoColorPrimaries_ITU_R_709_2,AVVideoTransferFunctionKey:AVVideoTransferFunction_ITU_R_709_2,AVVideoYCbCrMatrixKey:AVVideoYCbCrMatrix_ITU_R_709_2]])
            output.suppressesPlayerRendering=false;copy.add(output)
            let companion=AVPlayer(playerItem:copy);companion.isMuted=true;companion.volume=0
            companion.allowsExternalPlayback=false;companion.automaticallyWaitsToMinimizeStalling=false
            aheadItem=copy;aheadOutput=output;aheadPlayer=companion
            companion.playImmediately(atRate:1) // Establish the initial seekable range while the muted decoder warms up.
        }
        guard let companion=aheadPlayer,let copy=aheadItem,let output=aheadOutput else {return nil}
        if copy.status == .failed {aheadFailed=true;stopAhead();reportAhead("Unavailable for this stream");return nil}
        guard copy.status == .readyToPlay else {return nil}
        let duration=item.duration.seconds
        let otherDuration=copy.duration.seconds
        if copy.presentationSize.height>1080 || (lookAheadAsset != nil && duration.isFinite && otherDuration.isFinite && duration>0 && otherDuration>0 && abs(duration-otherDuration)>0.5) {
            aheadFailed=true;stopAhead();reportAhead("Unavailable at this stream quality");return nil
        }
        let target=duration.isFinite && duration>0 ? min(duration-0.1,main+lead) : main+lead
        let current=companion.currentTime().seconds
        if !aheadSeeking,(!current.isFinite || abs(current-target)>0.7),Date().timeIntervalSince(lastAheadSeek)>2 {
            let seekTime=CMTime(seconds:max(0,target),preferredTimescale:600)
            guard copy.seekableTimeRanges.contains(where:{CMTimeRangeContainsTime($0.timeRangeValue,time:seekTime)}) else {return nil}
            aheadSeeking=true;lastAheadSeek=Date();let generation=aheadGeneration
            companion.seek(to:seekTime,toleranceBefore:CMTime(seconds:0.15,preferredTimescale:600),toleranceAfter:CMTime(seconds:0.15,preferredTimescale:600)) { [weak self] done in
                Task {@MainActor in
                    guard let self,self.aheadGeneration==generation else {return}
                    self.aheadSeeking=false
                    if done,self.player?.timeControlStatus == .playing {self.aheadPlayer?.playImmediately(atRate:1)}
                }
            }
        } else if !aheadSeeking {companion.playImmediately(atRate:1)}
        guard !aheadSeeking,current.isFinite,current-main>=0.1,current-main<=lead+0.5 else {return nil}
        let time=companion.currentTime();var actual=CMTime.invalid
        guard output.hasNewPixelBuffer(forItemTime:time),let buffer=output.copyPixelBuffer(forItemTime:time,itemTimeForDisplay:&actual),actual.seconds.isFinite,
              actual.seconds-main>=0.1,actual.seconds-main<=lead+0.5 else {return nil}
        reportAhead("Active")
        return buffer
    }
    private func stopAhead() {
        aheadGeneration=UUID();aheadPlayer?.pause();aheadPlayer?.replaceCurrentItem(with:nil)
        if let aheadOutput {aheadItem?.remove(aheadOutput)}
        aheadOutput=nil;aheadItem=nil;aheadPlayer=nil;aheadSeeking=false;lastAheadSeek = .distantPast
    }
    private func colour(_ buffer:CVPixelBuffer)->SceneColour? {
        let image=CIImage(cvPixelBuffer:buffer),extent=image.extent
        guard extent.width>0,extent.height>0 else {return nil}
        let crop=extent.insetBy(dx:extent.width*0.04,dy:extent.height*0.12)
        let thumbnail=image.cropped(to:crop).transformed(by:CGAffineTransform(translationX:-crop.minX,y:-crop.minY)).transformed(by:CGAffineTransform(scaleX:64/crop.width,y:36/crop.height))
        var bytes=[UInt8](repeating:0,count:64*36*4)
        context.render(thumbnail,toBitmap:&bytes,rowBytes:64*4,bounds:CGRect(x:0,y:0,width:64,height:36),format:.RGBA8,colorSpace:CGColorSpace(name:CGColorSpace.sRGB))
        return SceneColour.predominant(rgba:bytes)
    }
    private func detachOutput() {if let output {item?.remove(output)};output=nil;stopAhead();lookClock.reset()}
    func stop() {
        task?.cancel();task=nil;detachOutput();last=nil;window.reset();previousOptions=nil
        if active,let ticket {let api=api;Task {await api.stopSceneLighting(ticket:ticket)}}
        active=false;ticket=nil;item=nil;player=nil;accessible=false;lookAheadAsset=nil;aheadFailed=false;reportAhead("Off")
    }
}

// Separate from scene lighting: this only reads visible, unprotected frames near
// the end. It never prepares media, seeks, skips content or changes the player.
@MainActor final class VisualCreditsSampler {
    private weak var item:AVPlayerItem?
    private var output:AVPlayerItemVideoOutput?
    private var task:Task<Void,Never>?
    private var endingTask:Task<Void,Never>?
    private var evidence=VisualCreditsEvidence()
    func stop() {
        task?.cancel();task=nil;endingTask?.cancel();endingTask=nil
        if let output {item?.remove(output)}
        output=nil;item=nil;evidence.reset()
    }
    func attach(item:AVPlayerItem,player:AVPlayer,offset:Double,duration:@escaping ()->Double,
                cacheKey:String?,api:WatchAPI,ticket:String,version:String?,onDetection:@escaping (PlaybackInterval)->Void) {
        stop();self.item=item
        let output=AVPlayerItemVideoOutput(pixelBufferAttributes:[kCVPixelBufferPixelFormatTypeKey as String:kCVPixelFormatType_32BGRA])
        item.add(output);self.output=output
        endingTask=Task { [weak player] in
            // Wait for stable playback, and yield if the visible programme is short of buffer.
            do {
                await api.reportEnding(ticket:ticket,state:"waiting-for-buffer")
                var stable=false
                for _ in 0..<60 {
                    try await Task.sleep(for:.seconds(3))
                    guard let player,player.currentItem===item else {return}
                    let now=player.currentTime()
                    let buffered=item.loadedTimeRanges.map(\.timeRangeValue).filter{CMTimeRangeContainsTime($0,time:now)}.map{CMTimeRangeGetEnd($0).seconds-now.seconds}.max() ?? 0
                    if player.timeControlStatus == .playing && buffered>=20 {stable=true;break}
                    if Task.isCancelled {return}
                }
                guard stable,let player,player.currentItem===item,player.timeControlStatus == .playing else {return}
                await api.reportEnding(ticket:ticket,state:"fetching-preview")
                guard let (file,start,length)=try await api.endingPreview(ticket:ticket,version:version) else {await api.reportEnding(ticket:ticket,state:"preview-unavailable");return}
                defer {try? FileManager.default.removeItem(at:file)}
                guard abs(length-duration())<0.5 else {await api.reportEnding(ticket:ticket,state:"duration-mismatch",expected:length,actual:duration());return}
                await api.reportEnding(ticket:ticket,state:"analysing")
                let result=await Task.detached(priority:.utility) {await Self.scanEnding(file,start:start,duration:length)}.value
                guard !Task.isCancelled,player.currentItem===item else {return}
                guard let result else {await api.reportEnding(ticket:ticket,state:"no-detection");return}
                await api.reportEnding(ticket:ticket,state:"detected",start:result)
                if let cacheKey {UserDefaults.standard.set(["start":result,"duration":length],forKey:"watch.detectedCredits."+cacheKey)}
                onDetection(PlaybackInterval(id:"analysed-credits",title:"Up next",kind:"detected_credits",start:result,end:length))
            } catch {if !Task.isCancelled {await api.reportEnding(ticket:ticket,state:"analysis-failed")}}
        }
        task=Task { [weak self,weak player,weak item] in
            let context=CIContext(options:[.cacheIntermediates:false])
            while !Task.isCancelled {
                do {try await Task.sleep(for:.seconds(3))} catch {return}
                guard let self,let player,let item,player.currentItem===item else {return}
                guard player.timeControlStatus == .playing else {self.evidence.reset();continue}
                let length=duration(),position=offset+player.currentTime().seconds
                guard length>60,position>=max(length*0.8,length-120),position<length-10 else {self.evidence.reset();continue}
                let key=cacheKey.map{"watch.detectedCredits."+$0}
                if let key,let saved=UserDefaults.standard.dictionary(forKey:key),
                   let end=saved["duration"] as? Double,let start=saved["start"] as? Double,
                   abs(end-length)<0.5,start>=max(length*0.8,length-120),start<length-10 {
                    onDetection(PlaybackInterval(id:"visual-credits",title:"Up next",kind:"detected_credits",start:start,end:length));return
                }
                let time=player.currentTime()
                guard output.hasNewPixelBuffer(forItemTime:time),let buffer=output.copyPixelBuffer(forItemTime:time,itemTimeForDisplay:nil) else {self.evidence.reset();continue}
                let image=CIImage(cvPixelBuffer:buffer)
                let scale=min(1,960/image.extent.width)
                let small=image.transformed(by:CGAffineTransform(scaleX:scale,y:scale))
                guard let cg=context.createCGImage(small,from:small.extent) else {continue}
                let credits=await Task.detached(priority:.utility) {Self.hasCreditText(cg)}.value
                guard !Task.isCancelled else {return}
                if let start=self.evidence.observe(credits:credits,position:position,duration:length) {
                    if let key {UserDefaults.standard.set(["start":start,"duration":length],forKey:key)}
                    onDetection(PlaybackInterval(id:"visual-credits",title:"Up next",kind:"detected_credits",start:start,end:length));return
                }
            }
        }
    }
    nonisolated private static func hasCreditText(_ image:CGImage,relaxed:Bool=false)->Bool {creditTextStrength(image)>=(relaxed ? 1 : 2)}
    nonisolated private static func creditTextStrength(_ image:CGImage)->Int {
        let request=VNRecognizeTextRequest();request.recognitionLevel = .accurate
        request.usesLanguageCorrection=false;request.recognitionLanguages=["en-GB"]
        guard (try? VNImageRequestHandler(cgImage:image).perform([request])) != nil else {return 0}
        let rows=(request.results ?? []).filter {($0.topCandidates(1).first?.confidence ?? 0)>0.65}
        let roles=["producer","director","executive","editor","production","copyright","presented by","written by","starring","camera","lighting","sound","makeup","make up","costume","researcher"]
        let matches=rows.filter {row in
            let text=row.topCandidates(1).first!.string.lowercased()
            return roles.contains {role in text.range(of:"\\b"+NSRegularExpression.escapedPattern(for:role)+"\\b",options:.regularExpression) != nil}
        }
        // Repeated multi-line role layouts reject most subtitles, dialogue,
        // channel bugs and isolated closing captions, including credits on video.
        guard matches.count>=1,rows.count>=2 else {return 0}
        let top=rows.map{$0.boundingBox.maxY}.max() ?? 0
        let bottom=rows.map{$0.boundingBox.minY}.min() ?? 0
        if matches.count>=2,rows.count>=4,top-bottom>0.18 {return 2}
        return top-bottom>0.06 ? 1 : 0
    }
    nonisolated private static func scanEnding(_ file:URL,start:Double,duration:Double)async->Double? {
        let asset=AVURLAsset(url:file)
        guard let actual=try? await asset.load(.duration),abs(actual.seconds-(duration-start))<1.5 else {return nil}
        let music=EndingMusicObserver.analyse(file)
        let generator=AVAssetImageGenerator(asset:asset);generator.maximumSize=CGSize(width:960,height:540);generator.appliesPreferredTrackTransform=true
        generator.requestedTimeToleranceBefore=CMTime(seconds:0.5,preferredTimescale:600);generator.requestedTimeToleranceAfter=CMTime(seconds:0.5,preferredTimescale:600)
        defer {generator.cancelAllCGImageGeneration()}
        var evidence=EndingScanEvidence()
        for second in stride(from:0.0,to:duration-start-5,by:3) {
            guard !Task.isCancelled else {return nil}
            guard let frame=try? await generator.image(at:CMTime(seconds:second,preferredTimescale:600)) else {evidence.reset();continue}
            let strength=creditTextStrength(frame.image),strong=strength==2,weak=strength>=1
            let musical=music.contains{$0.0<=second && second<$0.1}
            if let result=evidence.observe(position:start+second,strongText:strong,weakText:weak,music:musical) {return start+EndingScanEvidence.backdated(textStart:result-start,music:music)}
        }
        return nil
    }

}

// Analysis runs on a private, short local preview. No microphone or audio capture.
private final class EndingMusicObserver:NSObject,SNResultsObserving {
    private var music:[(Double,Double)]=[]
    private let lock=NSLock()
    func request(_ request:SNRequest,didProduce result:SNResult) {
        guard let result=result as? SNClassificationResult,
              (result.classification(forIdentifier:"music")?.confidence ?? 0)>=0.55,
              (result.classification(forIdentifier:"speech")?.confidence ?? 0)<0.6 else {return}
        lock.lock();music.append((result.timeRange.start.seconds,CMTimeRangeGetEnd(result.timeRange).seconds));lock.unlock()
    }
    func request(_ request:SNRequest,didFailWithError error:Error) {}
    func requestDidComplete(_ request:SNRequest) {}
    static func analyse(_ url:URL)->[(Double,Double)] {
        guard let analyzer=try? SNAudioFileAnalyzer(url:url),let request=try? SNClassifySoundRequest(classifierIdentifier:.version1) else {return []}
        let observer=EndingMusicObserver()
        do {try analyzer.add(request,withObserver:observer);analyzer.analyze()} catch {return []}
        observer.lock.lock();defer {observer.lock.unlock()};return observer.music
    }
}
