import Foundation
import AVFoundation
@main struct Test {
 @MainActor static func main() async throws {
  let item=AVPlayerItem(url:URL(string:CommandLine.arguments[1])!)
  let player=AVPlayer(playerItem:item);player.isMuted=true
  player.automaticallyWaitsToMinimizeStalling=true
  item.automaticallyPreservesTimeOffsetFromLive=false
  for _ in 0..<150 {
   if item.status == .readyToPlay {break}
   try await Task.sleep(for:.milliseconds(200))
  }
  let started=await player.seek(to:.zero,toleranceBefore:.zero,toleranceAfter:.zero)
  precondition(started)
  player.play()
  for _ in 0..<150 {
   try await Task.sleep(for:.milliseconds(200))
   if player.currentTime().seconds>3 {break}
   if item.status == .failed {throw item.error!}
  }
  precondition(player.currentTime().seconds>3 && player.currentTime().seconds<8,"Episode did not start at its requested beginning")
  player.pause();let paused=player.currentTime().seconds
  try await Task.sleep(for:.seconds(12))
  let held=player.currentTime().seconds
  precondition(abs(held-paused)<0.25,"Playhead moved while paused")
  let sought=await player.seek(to:CMTime(seconds:paused,preferredTimescale:600),toleranceBefore:.zero,toleranceAfter:.zero)
  precondition(sought)
  player.play();try await Task.sleep(for:.seconds(3))
  let resumed=player.currentTime().seconds
  precondition(resumed-paused>1 && resumed-paused<5,"Resume skipped paused content")
  player.pause()
  print(String(format:"AVPlayer EVENT regression passed: paused %.2fs, held %.2fs, resumed %.2fs after 3s playback",paused,held,resumed))
 }
}
