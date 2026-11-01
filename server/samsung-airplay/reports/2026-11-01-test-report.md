# YouTube and BBC iPlayer AirPlay bridge test — 1 November 2026

## Target hardware and purpose

The receiver host was a **Raspberry Pi 500 Rev 1.0**, running 64-bit Debian 13.6, Python 3.13.5 and FFmpeg 7.1.5. The AirPlay sender was an **iPhone 16e**. The exact iOS and app versions were not recorded.

The destination was a **Samsung T27B551 / LT27B551EW, a 27-inch early-2010s Smart Hub/Orsay-generation TV monitor, predating Tizen**. Samsung's [model support page](https://www.samsung.com/uk/support/model/LT27B551EW/EN/) identifies the 27-inch model and provides its 2012/2013 manuals. The aim was to give this older television an AirPlay route using its built-in DLNA network video player, without an HDMI connection or replacing its Smart Hub software.

The Pi receives the AirPlay session and remuxes compressed media. The television fetches an HTTP MPEG-TS stream and decodes picture and sound itself. DLNA AVTransport supplies the TV playback controls; the bridge translates the iPhone's commands and reports TV position back to UxPlay. A separate Pi 2B surround installation was left untouched.

## Software and scope

- UxPlay 1.74 experimental, upstream commit `234b407e2e7a8a9a33adf293f0e56fd539658b1e`.
- A small callback patch redirects play, rate, scrub, stop, playlist-removal and playback-info to an external adapter. AirPlay/HLS protocol handling remains in UxPlay.
- The Python adapter selects an H.264/AAC rendition, FFmpeg uses `-c copy`, and the TV plays the resulting MPEG-TS over HTTP.
- The installed experiment permits up to 720p50. The TV's manual table specifies 30fps; 50fps was tried at the user's request and worked for these samples. This is measured compatibility for this television and tested streams, not a revised specification or a claim about every older Samsung.
- UxPlay's local GStreamer video/audio sinks are fakesinks in this setup. **Stock UxPlay local rendering of iPlayer was not tested.**

## Observed results

| Test | Observation |
| --- | --- |
| Synthetic 720p25 H.264/AAC HLS through binary-plist AirPlay `/play`, callback adapter and DLNA | User confirmed moving test picture and tone on the actual TV. |
| Synthetic transport commands | Pause yielded PAUSED_PLAYBACK; resume yielded PLAYING; a seek to 20 seconds reopened the stream and appeared in AirPlay playback-info; stop yielded STOPPED. |
| Remux verification | Complete synthetic output decoded without errors; all 1,500 decoded video-frame hashes matched the source. |
| Incompatible codec | A VP9-only fixture was rejected rather than transcoded. |
| YouTube iPhone app | iPhone established AirPlay/reverse HTTP; UxPlay processed the YouTube playlists, including condensed media playlists. H.264 High Level 3.2 / AAC at 1280×720, 50fps was selected. TV playback position advanced beyond 36 seconds and matched bridge status. User confirmed picture, sound, pause/resume and seeking. |
| BBC iPlayer iPhone app | iPlayer delivered a direct HLS master playlist through UxPlay's play callback. H.264 High Level 3.2 / HE-AAC at 1280×720, 50fps was selected. TV fetched the remuxed stream; the user confirmed video, sound and transport controls. |
| Codec-order regression | Tests using captured playlist structures and offline fixtures passed for YouTube's video-first CODECS and iPlayer's audio-first CODECS. |
| Services | Receiver and adapter were running and enabled for the Pi user's normal login. Full Pi reboot was not tested. |

## Integration fixes and qualifications

1. Samsung probes the media URL with HEAD before GET. Implementing HEAD resolved an initial unsupported-file message.
2. YouTube segment URLs did not have conventional file extensions. The adapter enables the corresponding FFmpeg HLS extension options for this input path.
3. iPlayer used audio-first CODECS, for example `mp4a.40.5,avc1.640020`. A video-first assumption in **our adapter** caused the initial rejection; checking every codec entry fixed it. This was not a UxPlay codec-parsing bug.
4. Startup transport commands can arrive while the TV is opening media. The adapter retries transient failures and polls the TV independently instead of treating every control error as failed playback.
5. UxPlay's default 15-second client-silence watchdog reset the connection during this external-renderer experiment. The final service uses `-reset 0`; playback-info callbacks also count as activity. Whether this behavior is specific to the adapter or occurs with stock rendering was not isolated.

We did not test prolonged playback, all programme/video changes, advertisements, overnight operation, every content type, or stock UxPlay rendering. No DRM functionality was added or bypassed, and this test does not establish protected-content compatibility.

## Sanitised evidence and reproduction

- [YouTube master-playlist excerpt](youtube-master.sanitised.m3u8)
- [BBC iPlayer master-playlist excerpt](iplayer-master.sanitised.m3u8)
- [Adapter, callback patch, service examples and rebuild instructions](../README.md)
- [Recorded source hashes and environment](../snapshot.json)

The playlist excerpts preserve the captured H.264 variants' CODECS values and ordering, bandwidth, resolution and frame rate. All media hosts, paths, query strings, audio labels and group identifiers were replaced. They are structural examples, not playable fixtures. No account credentials, receiver keys, signed playback URLs or broadcaster media are included. Raw logs and source URLs remain private to the original Pi.
