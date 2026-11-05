import Foundation
@main struct Check {
 static func main() {
  func colour(_ r:UInt8,_ g:UInt8,_ b:UInt8,_ count:Int)->[UInt8] {Array(repeating:[r,g,b,255],count:count).flatMap {$0}}
  let red=SceneColour.predominant(rgba:colour(255,0,0,60)+colour(0,0,255,30)+colour(255,255,255,10))!
  precondition(SceneColour.distance(red.hue,0)<1,"Predominant colour wins instead of averaging red and blue into purple")
  for rgb in [(UInt8(0),UInt8(0),UInt8(0)),(255,255,255),(90,90,90)] {
   precondition(SceneColour.predominant(rgba:colour(rgb.0,rgb.1,rgb.2,100))?.saturation==0,"Neutral scenes use white")
  }
  precondition(SceneColour.predominant(rgba:colour(130,130,130,95)+colour(255,0,0,5))?.saturation==0,"A small coloured logo does not dominate a neutral scene")
  precondition(SceneColour.predominant(rgba:[0,0,0,0])==nil,"Missing transparent frame is not a black scene")
  let darkSea=SceneColour.predominant(rgba:colour(0,20,50,80)+colour(0,255,0,20))!
  precondition(SceneColour.distance(darkSea.hue,216)<3,"A small bright turtle cannot outweigh the larger dark sea")
  let darkRed=SceneColour.predominant(rgba:colour(55,0,10,80)+colour(255,255,0,20))!
  precondition(SceneColour.distance(darkRed.hue,349)<3,"Area voting applies to the whole spectrum, not only blue")
  let variedSea=SceneColour.predominant(rgba:colour(0,36,60,25)+colour(0,24,60,25)+colour(0,12,60,25)+colour(0,255,0,25))!
  precondition(SceneColour.distance(variedSea.hue,216)<15,"Nearby sea shades count as one dominant group")
  let wrap=SceneColour(hue:359,saturation:80).blended(towards:SceneColour(hue:1,saturation:80))
  precondition(SceneColour.distance(wrap.hue,0)<2,"Hue smoothing follows the short path across red")
  precondition(red.blended(towards:SceneColour(hue:0,saturation:0)).saturation==0,"Neutral scene requests white without intermediate colour bias")
  var profile=HueCalibration()
  for hue in stride(from:0.0,to:360,by:5) {precondition(SceneColour.distance(profile.corrected(hue),hue)<0.001,"Uncalibrated colours stay unchanged")}
  let navy=HueReference.colours.first {$0.id=="navy"}!
  profile.adjust(navy,by:20)
  precondition(SceneColour.distance(profile.corrected(220),240)<0.001,"Saved navy reference maps directly to the adjusted lamp hue")
  precondition(SceneColour.distance(profile.corrected(200),210)<0.001,"Corrections blend smoothly between nearby references")
  precondition(SceneColour.distance(profile.corrected(120),120)<0.001,"A navy correction leaves unrelated green unchanged")
  let redReference=HueReference.colours.first {$0.id=="red"}!
  profile.adjust(redReference,by:20)
  precondition(SceneColour.distance(profile.corrected(359),profile.corrected(0))<2,"Calibration is continuous across hue wraparound")
  profile.adjust(navy,by:1000);precondition(profile.offset(for:navy)==60,"Adjustments stay bounded")
  let suite="watch.scene.tests."+UUID().uuidString,defaults=UserDefaults(suiteName:suite)!
  defer {defaults.removePersistentDomain(forName:suite)}
  try! profile.save(defaults:defaults)
  precondition(HueCalibration.load(defaults:defaults)==profile,"Calibration round trips through preferences")
  print("Scene hue checks passed: dominant colour, neutral/black/white scenes, logo rejection, missing frames and circular smoothing")
 }
}
