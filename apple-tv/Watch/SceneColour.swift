import Foundation

struct SceneColour:Equatable {
    let hue:Double
    let saturation:Double
    var brightness:Double=100
    static func distance(_ a:Double,_ b:Double)->Double {abs((a-b+540).truncatingRemainder(dividingBy:360)-180)}
    func blended(towards target:SceneColour)->SceneColour {
        if target.saturation==0 {return SceneColour(hue:hue,saturation:0,brightness:target.brightness)}
        if saturation==0 {return target}
        let delta=(target.hue-hue+540).truncatingRemainder(dividingBy:360)-180
        let amount=abs(delta)>95 ? 0.6 : 0.4
        return SceneColour(hue:(hue+delta*amount+360).truncatingRemainder(dividingBy:360),saturation:saturation+(target.saturation-saturation)*0.4,brightness:target.brightness)
    }
    /// Select the largest neighbouring hue cluster by picture area.
    /// Brightness does not give small highlights more votes than dark scenery.
    static func predominant(rgba:[UInt8])->SceneColour? {
        guard rgba.count>=4,rgba.count%4==0 else {return nil}
        var weights=Array(repeating:0.0,count:36),hues=weights,saturations=weights
        var visible=0,coloured=0,opaque=0
        var brightness=0.0
        for i in stride(from:0,to:rgba.count,by:4) {
            guard rgba[i+3]>127 else {continue};opaque+=1
            let r=Double(rgba[i])/255,g=Double(rgba[i+1])/255,b=Double(rgba[i+2])/255
            let high=max(r,g,b),low=min(r,g,b),delta=high-low
            brightness+=high
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
        guard visible>0,Double(coloured)/Double(opaque)>=0.3 else {return SceneColour(hue:0,saturation:0,brightness:100*brightness/Double(opaque))}
        func cluster(_ index:Int)->Double {weights[(index+35)%36]+weights[index]+weights[(index+1)%36]}
        guard let peak=weights.indices.max(by:{cluster($0)<cluster($1)}),cluster(peak)>0 else {return nil}
        var x=0.0,y=0.0,sat=0.0,total=0.0
        for index in [(peak+35)%36,peak,(peak+1)%36] where weights[index]>0 {
            let angle=(hues[index]/weights[index])*Double.pi/180
            x+=cos(angle)*weights[index];y+=sin(angle)*weights[index];sat+=saturations[index];total+=weights[index]
        }
        return SceneColour(hue:(atan2(y,x)*180/Double.pi+360).truncatingRemainder(dividingBy:360),saturation:min(100,100*sat/total),brightness:100*brightness/Double(opaque))
    }
}

struct SceneLightingOptions:Equatable {
    var sampleInterval:Double=2
    var averagingWindow:Double=0
    var fade:Double=3
    var matchSaturation=false
    var matchBrightness=false
    var neutralWhite=true
    var saturation:Double=100
    var lookAhead:Double=0
    static func load(defaults:UserDefaults = .standard)->SceneLightingOptions {
        var value=SceneLightingOptions()
        func choice(_ key:String,_ allowed:[Double],_ fallback:Double)->Double {
            guard defaults.object(forKey:key) != nil else {return fallback}
            let result=defaults.double(forKey:key);return allowed.contains(result) ? result : fallback
        }
        value.matchSaturation=defaults.bool(forKey:"watch.light.matchSaturation")
        value.matchBrightness=defaults.bool(forKey:"watch.light.matchBrightness")
        value.sampleInterval=choice("watch.light.sample",[0.5,1,2,4],2)
        value.averagingWindow=choice("watch.light.window",[0,2,5,10,20],0)
        value.fade=choice("watch.light.fade",[0.5,1,3,5,8],3)
        value.neutralWhite=defaults.object(forKey:"watch.light.neutralWhite") == nil ? true : defaults.bool(forKey:"watch.light.neutralWhite")
        value.saturation=choice("watch.light.saturation",[20,40,60,80,100],100)
        value.lookAhead=choice("watch.light.lookAhead",[0,0.5,1,2,3],0)
        return value
    }
    func save(defaults:UserDefaults = .standard) {
        defaults.set(matchSaturation,forKey:"watch.light.matchSaturation");defaults.set(matchBrightness,forKey:"watch.light.matchBrightness")
        defaults.set(sampleInterval,forKey:"watch.light.sample");defaults.set(averagingWindow,forKey:"watch.light.window")
        defaults.set(fade,forKey:"watch.light.fade");defaults.set(neutralWhite,forKey:"watch.light.neutralWhite")
        defaults.set(saturation,forKey:"watch.light.saturation");defaults.set(lookAhead,forKey:"watch.light.lookAhead")
    }
}

// Temporal area voting: use the most frequent neighbouring hue cluster, never
// average unrelated colours into an invented colour between them.
struct SceneColourWindow {
    private var frames:[(Double,SceneColour)]=[]
    mutating func reset() {frames=[]}
    mutating func append(_ colour:SceneColour,at time:Double,options:SceneLightingOptions)->SceneColour? {
        frames.removeAll{$0.0<time-options.averagingWindow}
        if colour.saturation>0 || options.neutralWhite {frames.append((time,colour))}
        if options.averagingWindow==0 {return colour.saturation==0 && !options.neutralWhite ? nil : colour}
        let neutral=frames.filter{$0.1.saturation==0}.count
        let colours=frames.filter{$0.1.saturation>0}.map(\.1)
        guard !colours.isEmpty else {return neutral>0 ? SceneColour(hue:0,saturation:0,brightness:colour.brightness) : nil}
        var bins=Array(repeating:0,count:36)
        for c in colours {bins[min(35,Int(c.hue/10))]+=1}
        func votes(_ i:Int)->Int {bins[(i+35)%36]+bins[i]+bins[(i+1)%36]}
        let peak=(0..<36).max{votes($0)<votes($1)}!
        if neutral>votes(peak) {return SceneColour(hue:0,saturation:0,brightness:frames.reduce(0){$0+$1.1.brightness}/Double(frames.count))}
        let selected=colours.filter{SceneColour.distance($0.hue,Double(peak)*10+5)<=15}
        guard !selected.isEmpty else {return colours.last}
        let x=selected.reduce(0.0){$0+cos($1.hue*Double.pi/180)},y=selected.reduce(0.0){$0+sin($1.hue*Double.pi/180)}
        return SceneColour(hue:(atan2(y,x)*180/Double.pi+360).truncatingRemainder(dividingBy:360),saturation:selected.reduce(0){$0+$1.saturation}/Double(selected.count),brightness:frames.reduce(0){$0+$1.1.brightness}/Double(frames.count))
    }
}

struct SceneLookAheadClock {
    private var started:Double?
    private var previousPosition:Double?
    private var previousTime:Double?
    mutating func reset() {started=nil;previousPosition=nil;previousTime=nil}
    mutating func lead(at time:Double,position:Double,playing:Bool,target:Double)->Double {
        guard playing,target>0,time.isFinite,position.isFinite else {reset();return 0}
        if let oldPosition=previousPosition,let oldTime=previousTime,abs((position-oldPosition)-(time-oldTime))>1.2 {started=time}
        if started == nil {started=time}
        previousPosition=position;previousTime=time
        return target*min(1,max(0,(time-started!)/8))
    }
}
