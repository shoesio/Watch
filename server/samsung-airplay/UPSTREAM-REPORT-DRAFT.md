Title: BBC iPlayer iOS HLS handoff works through UxPlay callbacks (external Samsung DLNA renderer)

I tested the BBC iPlayer iOS app with UxPlay 1.74 experimental, commit `234b407e2e7a8a9a33adf293f0e56fd539658b1e`, on a Raspberry Pi 500 running 64-bit Debian 13.6.

The iPhone 16e connected to UxPlay's AirPlay video endpoint, established reverse HTTP, and delivered a direct HTTP(S) HLS playlist to `on_video_play`. The tested programme offered 1280×720 at 50fps, H.264 High Level 3.2 and HE-AAC. Video, sound and iPhone transport controls were confirmed on the receiving TV.

There is an important scope distinction: I patched UxPlay's HLS playback/status callbacks to use an external Python/FFmpeg/DLNA adapter and a Samsung T27B551 network player. UxPlay handled the AirPlay session and handoff, while FFmpeg remuxed with codec copy and the Samsung decoded the media. I did **not** test iPlayer with stock UxPlay's local GStreamer renderer. This is evidence that the AirPlay/HLS handoff works for the tested iPlayer programme, rather than a claim of general iPlayer support in unmodified UxPlay.

One integration detail: iPlayer's master playlist lists audio before video in CODECS, for example `CODECS="mp4a.40.5,avc1.640020"`. My own adapter initially rejected it because it assumed the video codec came first. Checking all codec entries fixed that; no UxPlay protocol change was required for this issue.

The adapter maps play, rate, scrub, stop, playlist-removal and playback-info callbacks to the external renderer. Playback-info comes from the TV. The receiver ran with `-hls` and disabled the client-silence reset (`-reset 0`) after the default 15-second watchdog caused resets during the external-renderer experiment. The callback adapter also counts playback-info requests as client activity. I haven't isolated whether that timeout behavior is specific to this integration or reproducible with the stock renderer.

YouTube was also tested successfully through the same adapter at 720p50. Checks covered short playback, sound and phone transport controls. We haven't established prolonged playback, programme changes, advertisements, every iPlayer content type, DRM-protected streams, or stock-renderer compatibility. No DRM functionality was added or bypassed.

Would this be useful as a compatibility note or a starting point for a stock-renderer test? I can supply the small callback patch and a sanitized example of the playlist structure if helpful. No account credentials or signed playback URLs are included in this report.
