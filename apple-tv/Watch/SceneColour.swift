import Foundation

struct SceneColour:Equatable {
    let hue:Double
    let saturation:Double
    static func distance(_ a:Double,_ b:Double)->Double {abs((a-b+540).truncatingRemainder(dividingBy:360)-180)}
    func blended(towards target:SceneColour)->SceneColour {
        if target.saturation==0 {return SceneColour(hue:hue,saturation:0)}
        if saturation==0 {return target}
        let delta=(target.hue-hue+540).truncatingRemainder(dividingBy:360)-180
        let amount=abs(delta)>95 ? 0.6 : 0.4
        return SceneColour(hue:(hue+delta*amount+360).truncatingRemainder(dividingBy:360),saturation:saturation+(target.saturation-saturation)*0.4)
    }
    /// Select the largest neighbouring hue cluster by picture area.
    /// Brightness does not give small highlights more votes than dark scenery.
    static func predominant(rgba:[UInt8])->SceneColour? {
        guard rgba.count>=4,rgba.count%4==0 else {return nil}
        var weights=Array(repeating:0.0,count:36),hues=weights,saturations=weights
        var visible=0,coloured=0,opaque=0
        for i in stride(from:0,to:rgba.count,by:4) {
            guard rgba[i+3]>127 else {continue};opaque+=1
            let r=Double(rgba[i])/255,g=Double(rgba[i+1])/255,b=Double(rgba[i+2])/255
            let high=max(r,g,b),low=min(r,g,b),delta=high-low
            guard high>0.07 else {continue};visible+=1
            let saturation=delta/high
            guard saturation>0.14,delta>0.04 else {continue};coloured+=1
            var hue:Double
            if high==r {hue=60*((g-b)/delta).truncatingRemainder(dividingBy:6)}
            else if high==g {hue=60*((b-r)/delta+2)} else {hue=60*((r-g)/delta+4)}
            if hue<0 {hue+=360}
            let index=min(35,Int(hue/10)),weight=1.0
            weights[index]+=weight;hues[index]+=hue*weight;saturations[index]+=saturation*weight
        }
        guard opaque>0 else {return nil}
        guard visible>0,Double(coloured)/Double(opaque)>=0.3 else {return SceneColour(hue:0,saturation:0)}
        func cluster(_ index:Int)->Double {weights[(index+35)%36]+weights[index]+weights[(index+1)%36]}
        guard let peak=weights.indices.max(by:{cluster($0)<cluster($1)}),cluster(peak)>0 else {return nil}
        var x=0.0,y=0.0,sat=0.0,total=0.0
        for index in [(peak+35)%36,peak,(peak+1)%36] where weights[index]>0 {
            let angle=(hues[index]/weights[index])*Double.pi/180
            x+=cos(angle)*weights[index];y+=sin(angle)*weights[index];sat+=saturations[index];total+=weights[index]
        }
        return SceneColour(hue:(atan2(y,x)*180/Double.pi+360).truncatingRemainder(dividingBy:360),saturation:min(95,100*sat/total))
    }
}
