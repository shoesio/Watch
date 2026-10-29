import Foundation
enum NativeProvider {case itv}
struct LiveChannel {let id:String;let itvPlaylistURL:URL?;var provider:NativeProvider {.itv}}
enum UCatalogueAPI {
 static func stringID(_ value:Any?)->String? {
  let s=(value as? String) ?? (value as? NSNumber)?.stringValue
  return s.flatMap {$0.range(of:#"^[0-9]{1,20}$"#,options:.regularExpression) != nil ? $0 : nil}
 }
}
struct UFairPlayConfig {let licence:URL;let videoID:String;let created:Date}
