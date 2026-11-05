#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
check_dir=$(mktemp -d)
trap 'rm -rf "$check_dir"' EXIT
python3 - "$check_dir/checks.swift" <<'PY'
import sys,pathlib
source=pathlib.Path('Watch/Artwork.swift').read_text()
a=source.index('private actor ArtworkTitleAnalysis {');b=source.index('private struct ContinueWatchingIdentity',a)
tests='''
@main struct Checks {
 static func image(_ text:String)->CGImage {
  let context=CGContext(data:nil,width:800,height:450,bitsPerComponent:8,bytesPerRow:3200,space:CGColorSpaceCreateDeviceRGB(),bitmapInfo:CGImageAlphaInfo.premultipliedLast.rawValue)!
  context.setFillColor(CGColor(gray:0.15,alpha:1));context.fill(CGRect(x:0,y:0,width:800,height:450))
  let string=NSAttributedString(string:text,attributes:[NSAttributedString.Key(kCTFontAttributeName as String):CTFontCreateWithName("Helvetica-Bold" as CFString,36,nil),NSAttributedString.Key(kCTForegroundColorAttributeName as String):CGColor(gray:1,alpha:1)])
  context.textPosition=CGPoint(x:25,y:200);CTLineDraw(CTLineCreateWithAttributedString(string),context)
  return context.makeImage()!
 }
 static func main()async {
  let title="Have I Got a Bit More News for You"
  let printed=await ArtworkTitleAnalysis.shared.containsTitle(image("Have I Got News For You"),title:title)
  let blank=await ArtworkTitleAnalysis.shared.containsTitle(image(""),title:title)
  let different=await ArtworkTitleAnalysis.shared.containsTitle(image("Doctor Who"),title:title)
  precondition(printed,"A printed programme title would be duplicated")
  precondition(!blank && !different,"Untitled or unrelated artwork lost its identity overlay")
  print("Artwork label checks passed: printed title suppression, blank artwork and unrelated titles")
 }
}
'''
pathlib.Path(sys.argv[1]).write_text('import Foundation\nimport Vision\nimport CoreText\n'+source[a:b]+tests)
PY
xcrun swiftc -parse-as-library "$check_dir/checks.swift" -o "$check_dir/checks"
"$check_dir/checks"
