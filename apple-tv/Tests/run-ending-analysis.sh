#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
check_dir=$(mktemp -d)
trap 'rm -rf "$check_dir"' EXIT
python3 - "$check_dir/checks.swift" <<'PY'
import pathlib,sys
s=pathlib.Path('Watch/SceneLightingSampler.swift').read_text()
methods=s[s.index('    nonisolated private static func hasCreditText'):s.index('// Analysis runs on a private')].rsplit('\n}',1)[0]
methods=methods.replace('nonisolated private static','static')
observer=s[s.index('private final class EndingMusicObserver'):]
pathlib.Path(sys.argv[1]).write_text('import Foundation\nimport AVFoundation\nimport CoreImage\nimport Vision\nimport SoundAnalysis\nstruct Detector {\n'+methods+'\n}\n'+observer+'''
@main struct Check {
 static func main()async {
  guard CommandLine.arguments.count==4,let start=Double(CommandLine.arguments[2]),let duration=Double(CommandLine.arguments[3]) else {fatalError("Pass local preview path, episode-relative start, full duration")}
  print("Music windows:",EndingMusicObserver.analyse(URL(fileURLWithPath:CommandLine.arguments[1])))
  let result=await Detector.scanEnding(URL(fileURLWithPath:CommandLine.arguments[1]),start:start,duration:duration)
  print("Detected credits start:",result as Any)
 }
}
''')
PY
xcrun swiftc -parse-as-library Watch/PlaybackExtras.swift "$check_dir/checks.swift" -o "$check_dir/checks"
"$check_dir/checks" "$@"
