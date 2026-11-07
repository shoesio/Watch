#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
check_dir=$(mktemp -d)
trap 'rm -rf "$check_dir"' EXIT
python3 - "$check_dir/checks.swift" <<'PY'
import pathlib,sys
source=pathlib.Path('Watch/SceneLightingSampler.swift').read_text()
method=source[source.index('    nonisolated private static func hasCreditText'):source.index('    nonisolated private static func scanEnding')]
method=method.replace('nonisolated private static','static')
pathlib.Path(sys.argv[1]).write_text('''import Vision
import CoreText
import Foundation
struct Detector {
'''+method+'''
}
@main struct Checks {
 static func image(_ lines:[String])->CGImage {
  let c=CGContext(data:nil,width:960,height:540,bitsPerComponent:8,bytesPerRow:3840,space:CGColorSpaceCreateDeviceRGB(),bitmapInfo:CGImageAlphaInfo.premultipliedLast.rawValue)!
  c.setFillColor(CGColor(gray:0.02,alpha:1));c.fill(CGRect(x:0,y:0,width:960,height:540))
  for (i,text) in lines.enumerated() {
   let string=NSAttributedString(string:text,attributes:[NSAttributedString.Key(kCTFontAttributeName as String):CTFontCreateWithName("Helvetica" as CFString,28,nil),NSAttributedString.Key(kCTForegroundColorAttributeName as String):CGColor(gray:1,alpha:1)])
   c.textPosition=CGPoint(x:220,y:440-i*55);CTLineDraw(CTLineCreateWithAttributedString(string),c)
  }
  return c.makeImage()!
 }
 static func main() {
  precondition(Detector.hasCreditText(image(["Executive Producer","Jane Smith","Director","John Brown","Production","Example Television"])),"Credit roles and names should be recognised")
  precondition(!Detector.hasCreditText(image(["What did the producer say?","I think we should go home."])),"Ordinary dialogue should not count as credits")
  precondition(!Detector.hasCreditText(image([])),"Black frames are not credits")
  print("Credits vision checks passed: role layout, dialogue rejection and black-frame rejection")
 }
}
''')
PY
xcrun swiftc -parse-as-library "$check_dir/checks.swift" -o "$check_dir/checks"
"$check_dir/checks"
