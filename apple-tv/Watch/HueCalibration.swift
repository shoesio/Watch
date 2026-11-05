import Foundation

struct HueReference:Identifiable {
    let id:String
    let title:String
    let hue:Double
    let saturation:Double
    let value:Double
    static let colours:[HueReference]=[
        .init(id:"red",title:"Red",hue:0,saturation:1,value:0.85),
        .init(id:"orange",title:"Orange",hue:30,saturation:1,value:0.9),
        .init(id:"yellow",title:"Yellow",hue:60,saturation:1,value:0.9),
        .init(id:"green",title:"Green",hue:120,saturation:1,value:0.75),
        .init(id:"turquoise",title:"Turquoise",hue:180,saturation:1,value:0.75),
        .init(id:"navy",title:"Navy",hue:220,saturation:0.9,value:0.28),
        .init(id:"blue",title:"Blue",hue:240,saturation:1,value:0.8),
        .init(id:"purple",title:"Purple",hue:280,saturation:1,value:0.75),
        .init(id:"pink",title:"Pink",hue:320,saturation:1,value:0.85)
    ]
}
struct HueCalibration:Codable,Equatable {
    var offsets:[String:Double]=[:]
    static let key="watch.sceneHueCalibration.v1"
    func offset(for reference:HueReference)->Double {
        let value=offsets[reference.id] ?? 0
        return value.isFinite ? min(60,max(-60,value)) : 0
    }
    mutating func adjust(_ reference:HueReference,by amount:Double) {
        guard amount.isFinite else {return};offsets[reference.id]=min(60,max(-60,offset(for:reference)+amount))
    }
    func corrected(_ hue:Double)->Double {
        guard hue.isFinite else {return 0}
        let input=(hue.truncatingRemainder(dividingBy:360)+360).truncatingRemainder(dividingBy:360)
        let references=HueReference.colours
        let lower=references.lastIndex(where:{$0.hue<=input}) ?? references.count-1
        let upper=(lower+1)%references.count
        let start=references[lower].hue,end=upper==0 ? 360 : references[upper].hue
        let fraction=(input-start)/(end-start)
        let correction=offset(for:references[lower])*(1-fraction)+offset(for:references[upper])*fraction
        return (input+correction+360).truncatingRemainder(dividingBy:360)
    }
    static func load(defaults:UserDefaults = .standard)->HueCalibration {
        guard let data=defaults.data(forKey:key),let value=try? JSONDecoder().decode(Self.self,from:data) else {return .init()};return value
    }
    func save(defaults:UserDefaults = .standard)throws {defaults.set(try JSONEncoder().encode(self),forKey:Self.key)}
}
