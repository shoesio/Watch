# Samsung YouTube AirPlay bridge — 1 November 2026

Installed for testing on **Raspberry Pi 500 Rev 1.0**, Debian 13.6 arm64, `192.168.0.146`, user `jhewes`. Targets only the small **Samsung LT27B551**, `192.168.0.123:7676`.

The Pi 2B surround system was not connected to or changed. Existing Pi 500 SamsungWatch, Home Assistant, audio, desktop and TV widget services were not edited or restarted.

## Pipeline

YouTube iPhone AirPlay → patched UxPlay HLS callback → private Unix socket → Python adapter → FFmpeg `-c copy` MPEG-TS over HTTP → Samsung DLNA AVTransport.

UxPlay upstream: https://github.com/FDH2/UxPlay ; pinned commit `234b407e2e7a8a9a33adf293f0e56fd539658b1e`, version 1.74 experimental. Upstream supports YouTube iOS HLS and expands its condensed playlists through a localhost server. The callback patch replaces local HLS rendering only when `SAMSUNG_BRIDGE_SOCKET` is set. Mirroring/audio sinks are fakesinks; this is a YouTube video receiver experiment, not a general mirroring or audio receiver.

The bridge filters the HLS master playlist before probing, selects a matching AAC audio group, and permits YouTube’s extensionless segment URLs in FFmpeg. It uses H.264 Level 4.1 or below with stereo AAC. At the user’s request, the active service is configured for **up to 1280×720 at 50fps**, exceeding the manual’s 30fps limit as an explicit compatibility experiment. The first real video offered 720p50 and 1080p50, with 480p25 as its highest <=30fps H.264 choice. Defaults in the Python adapter remain 1080p30 when service environment overrides are absent. Incompatible sources fail explicitly. No transcoding fallback is enabled. Phone seek reopens a fresh codec-copy stream at the requested offset; it can start at an earlier keyframe and rebuffer. Pause/resume uses the TV's native DLNA transport. Status comes from TV position/transport polling, with the remux offset added.

## Runtime

Pi source and runtime: `/home/jhewes/samsung-airplay-uxplay`.

User services: `samsung-airplay-bridge.service` and `samsung-airplay-receiver.service`. Receiver requires and starts the bridge. Both services are **running and enabled for the Pi user’s normal login** after real iPhone/YouTube acceptance. A full Pi reboot was not tested.

- AirPlay name: `Samsung YouTube@raspberrypi` (UxPlay appends the hostname).
- AirPlay port: TCP 7111; reserved receiver base port: 7110.
- Media HTTP: `192.168.0.146:8116`, TV/Pi clients only and session-specific paths.
- Unix socket: runtime directory `bridge.sock`, owner access only.
- Logs: runtime directory `receiver.log`, `bridge.log`, `remux.log`. Keep them private because upstream diagnostics can include playback URLs.
- Private receiver key: runtime directory `receiver.pem`, not included here.

One command to start:

```sh
ssh jhewes@192.168.0.146 'systemctl --user start samsung-airplay-receiver'
```

One command to stop both:

```sh
ssh jhewes@192.168.0.146 'systemctl --user stop samsung-airplay-receiver samsung-airplay-bridge'
```

Full modified UxPlay source remains on the Pi. This deliverable contains the callback header, upstream patch, bridge, service definitions and synthetic protocol test client. To rebuild from the pinned upstream source, apply `uxplay.patch`, copy `samsung_bridge.h` into its root, then use `cmake -S . -B build -DNO_X11_DEPS=ON` and `cmake --build build -j3`.

Added build packages on the Pi: CMake, GStreamer development packages and their dependencies. Existing FFmpeg, OpenSSL and libplist were used. No existing UxPlay binary was replaced; the new executable stays in the dedicated runtime directory.

## Verified so far

- SSH target model/OS verified before changes.
- TV's existing AVTransport endpoint `/smp_26_` responds to GetTransportInfo/GetPositionInfo.
- Patched UxPlay compiles successfully on the actual Pi 500.
- Mac Bonjour discovery sees `Samsung YouTube@raspberrypi`.
- A synthetic **60-second 1280×720 25fps H.264 Level 3.1 / stereo AAC HLS** source passed through an actual binary-plist AirPlay HTTP `/play` request, callback adapter, codec-copy MPEG-TS relay and TV native player. The user confirmed moving picture and steady tone.
- TV requests HEAD before GET. Initial missing HEAD support produced “selected file is not currently supported”; implementing HEAD resolved it.
- AirPlay HTTP `/rate?value=0` produced TV `PAUSED_PLAYBACK`; resume produced `PLAYING`. `/scrub?position=20` reopened the stream and `/playback-info` reported position 20 seconds. This verifies generated protocol requests, not yet phone controls.
- `/stop` produced TV `STOPPED`; temporary fixture HTTP server stopped after the integration test.
- A real VP9-only WebM fixture was rejected by the track compatibility probe.
- Complete remuxed output decoded without errors. All **1,500 decoded video-frame hashes matched** the HLS source, confirming unchanged decoded pictures in that test.
- Initial test-client errors (header case, invalid session UUID length) were corrected. The invalid UUID triggered an upstream assertion and automatic receiver restart; valid UUID requests work.

## Real YouTube test progress

The iPhone 16e connected over IPv6, established reverse HTTP, supplied a YouTube master playlist and condensed media playlists, and reached the bridge callback. The first probe failed because of FFmpeg segment extension restrictions; those were fixed. Filtering before probing now restricts FFmpeg to one chosen video/audio rendition.

At the user’s request, real **1280×720 / 50fps H.264 High Level 3.2 with AAC** was selected, remuxed without encoding and fetched by the TV. DLNA reported PLAYING and advancing position beyond 36 seconds, matching the bridge status. The user explicitly confirmed smooth picture/sound and working iPhone pause/resume/seeking (“Yeah all seems fine to me”). Rate and seek callbacks, fresh stream requests after seeking, and advancing TV/bridge positions were also observed. Startup transport command failures no longer override independently polled TV playback status; transient controls retry and redundant controls are avoided.

The receiver service definition now disables UxPlay’s default 15-second client-silence watchdog using `-reset 0`, since HLS client silence was triggering resets during active streaming. The final setting was applied by restarting the receiver at 11:31:36 GMT. Both services were then verified active and enabled; the actual running command contains `-reset 0`. Re-select the receiver in the iPhone AirPlay list following this final restart. Playback-status callbacks also count as activity.

## Outstanding acceptance test

Advertisements, next-video changes, prolonged playback, end-of-video, overnight behavior and full Pi reboot still require testing. Real iPhone pause/resume/seek and a short playback run are accepted. The real session/playlist/codec path has now reached the TV as described above. Do not describe those as verified until separately observed. No claim is made that the experimental adapter handles every lifecycle case.

## Disable automatic start

```sh
ssh jhewes@192.168.0.146 'systemctl --user disable --now samsung-airplay-receiver samsung-airplay-bridge'
```

The 720p50 result applies to this tested video and television; it does not establish compatibility with every YouTube codec, video, or frame rate. No Apple account, YouTube credentials, or Pi 2B changes were needed.

## iPlayer experiment — 1 November 2026

The iPhone iPlayer app connected through the existing AirPlay receiver and supplied a direct HLS master playlist. The first attempt was rejected by a bridge selection bug: iPlayer lists AAC before H.264 in CODECS, whereas the original selector assumed the video codec came first. The selector now checks every codec entry, case-insensitively.

The actual playlist offered 1280×720 at 50fps with H.264 High Level 3.2 and HE-AAC audio. The bridge selected that rendition, FFprobe accepted it, the codec-copy remuxer ran, and the Samsung fetched the stream with successful HEAD/GET requests. The TV initially reported PAUSED_PLAYBACK with status OK. The user first observed a still image, then confirmed “we got video” after playback controls were tried. **The user confirmed iPlayer video, sound and transport controls work.** This result covers the tested programme; it does not establish compatibility with all iPlayer streams or protected content.

A regression check against both actual saved master manifests passed: H.264-first YouTube and AAC-first iPlayer each selected their 1280×720 / 50fps variant under the active settings. The updated adapter is running on the Pi; neither receiver naming nor the existing user-service startup settings changed.

Private diagnostics `last-input.json` and `last-source.m3u8` remain only in the Pi runtime directory with owner-only access; they can contain temporary playback URLs and are excluded from this deliverable.

## Recreating this snapshot

Install CMake, a C/C++ compiler, Git, pkg-config, libssl-dev, libplist-dev, libgstreamer1.0-dev and libgstreamer-plugins-base1.0-dev, with GStreamer runtime plugins and FFmpeg appropriate to the host. The tested runtime used Python 3.13.5 and FFmpeg 7.1.5-0+deb13u1+rpt2.

From this folder run `./prepare-uxplay.sh /path/to/new/uxplay-src`. The script fetches the exact upstream commit, applies the callback patch, copies the header and builds the executable. It refuses to overwrite an existing destination and does not install or start services. Service paths, IP addresses, ports and settings must match the destination installation before installing the example units.

Run the offline codec-order regression checks with `python3 -m unittest -v test_selector.py`. The actual end-to-end checks are documented above; these offline tests do not substitute for physical TV tests. `test_receiver.py` expects the dedicated synthetic fixture server used during development and is not a general unattended acceptance test.

The archived adapter and callback header were compared by SHA-256 with the files installed on the Pi. The patched uxplay.cpp also matched the Pi source exactly. See `snapshot.json` for hashes. No running services were changed while recording this in GitHub.
