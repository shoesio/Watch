import Foundation

// Keep the visible baseline fixed; wide wordmarks use less horizontal space,
// while upright marks get more vertical room without stretching their artwork.
enum ClearLogoLayout {
    static func size(image:CGSize,width:CGFloat,maxHeight:CGFloat)->CGSize {
        guard image.width>0,image.height>0,width>0,maxHeight>0 else {return CGSize(width:0,height:0)}
        let ratio=image.width/image.height
        let widthFraction=min(CGFloat(0.90),max(CGFloat(0.65),0.98-ratio*0.045))
        let resultWidth=min(width*widthFraction,maxHeight*ratio)
        return CGSize(width:resultWidth,height:resultWidth/ratio)
    }
}
