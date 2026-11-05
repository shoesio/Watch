import AVFoundation
import CoreImage

/// Samples only frames AVFoundation exposes. Never captures the screen or sends images.
@MainActor final class SceneLightingSampler {
    private let api:WatchAPI
    private weak var item:AVPlayerItem?
    private weak var player:AVPlayer?
    private var output:AVPlayerItemVideoOutput?
    private var task:Task<Void,Never>?
    private var last:SceneColour?
    private var ticket:String?
    private var active=false
    private let context=CIContext(options:[.cacheIntermediates:false])
    init(api:WatchAPI) {self.api=api}
    func attach(item:AVPlayerItem,player:AVPlayer,ticket:String,accessible:Bool) {
        stop();self.item=item;self.player=player;self.ticket=ticket
        guard accessible else {return}
        task=Task { [weak self] in
            while !Task.isCancelled {
                do {try await Task.sleep(for:.seconds(2))} catch {return}
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
                guard item.status == .readyToPlay else {continue}
                let time=player.currentTime()
                if let output=self.output,output.hasNewPixelBuffer(forItemTime:time),let buffer=output.copyPixelBuffer(forItemTime:time,itemTimeForDisplay:nil),let colour=self.colour(buffer) {
                    self.last=self.last?.blended(towards:colour) ?? colour
                }
                guard let colour=self.last,!Task.isCancelled else {continue}
                self.active=true
                await self.api.sceneColour(ticket:ticket,colour:SceneColour(hue:HueCalibration.load().corrected(colour.hue),saturation:colour.saturation))
            }
        }
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
    private func detachOutput() {if let output {item?.remove(output)};output=nil}
    func stop() {
        task?.cancel();task=nil;detachOutput();last=nil
        if active,let ticket {let api=api;Task {await api.stopSceneLighting(ticket:ticket)}}
        active=false;ticket=nil;item=nil;player=nil
    }
}
