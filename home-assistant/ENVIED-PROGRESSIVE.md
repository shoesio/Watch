# Playing while Envied downloads: investigation

The installed Envied contains a useful progressive assembly component, but its ordinary final output is not a ready-to-use streaming endpoint.

## Verified with generated, unencrypted media

The installed `RollingMerge` and `append_segment` code was extracted without importing Envied configuration or running its service/DRM components. Two generated 20-second fragmented MP4 tracks (H.264 video and AAC audio) arrived in deliberately shuffled segment order. Separate ordered byte pipes supplied FFmpeg, which combined the tracks into MPEG-TS using codec copy.

The clean final run produced output after 0.327 seconds. A snapshot of that output decoded successfully while neither producer had finished. The simulated downloads finished after 6.108 and 6.150 seconds. The completed transport stream contained 20 seconds of video and 20.032 seconds of audio. SHA-256 comparisons of the decoded raw video and PCM audio matched the original tracks exactly. No re-encoding occurred. This is a local simulation, not a measured provider startup time or network benchmark. See `envied-progressive-check.json`.

## Findings in installed code

- `core/manifests/dash.py`: `RollingMerge` holds out-of-order segments until every earlier segment is ready, then appends them in order. It can begin writing the initialization segment before the full download finishes.
- Both DASH and HLS parsers contain optional rolling assembly and per-segment processing. The stock configuration defaults those features off.
- `commands/dl.py`: track concurrency defaults to one, so ordinary use may finish video before starting audio. Progressive playback requires both selected tracks to progress concurrently.
- Normal final muxing/repackaging follows the download phase. Waiting for that final file defeats early playback.
- The rolling writer is buffered and has no dedicated streaming consumer contract. A production adapter needs explicit flushes or a segment-ready interface.
- Some manifests collapse byte ranges into a single resource download. Such paths must be assessed independently; rolling segment assembly does not apply automatically.

## Required adapter

`Envied playable ordered segments → separate video/audio waiting readers → FFmpeg codec-copy MPEG-TS → authenticated HA playback request and expiring LAN URL → Samsung DLNA`

The readers must wait at a temporary end of file, accept appended bytes, and close only when the producer has completed or failed. Start after a bounded buffer is available in both tracks. Preserve original audio/video timestamps. Keep final repackaging from replacing files that readers still use. Handle cancellation, source stalls, expired URLs, disk limits and cleanup. Seeking ahead beyond the buffered portion is a separate feature and should not be advertised initially.

## Provider boundary and present status

The controlled experiment does not test Envied's protected-service download or key-handling route. For the selected Channel 4/U episodes, early output is possible only if their service processing yields playable initialization data and segments before the entire track finishes. This has not been established. No content-decryption keys were extracted, no DRM configuration was changed, and no real episode was downloaded by Envied during this investigation.

No installed TwinVine files, HA configuration, running BBC service or TV playback were changed. No progressive Envied provider source has been enabled in the dashboard. The separately tested licensed-browser capture route remains a distinct option; its re-encoding trade-off differs from this codec-copy approach.


## Real U episode proof

A subsequent trial used the installed Envied UKTV adapter on the real Would I Lie to You? Series 16 Episode 1 source. The trial selected a 60-second sample (segment boundaries yielded approximately 66 seconds), concurrent audio/video downloads, ordered segment assembly, and separate waiting readers feeding FFmpeg with `-c copy`.

An early MPEG-TS snapshot at 1.698 seconds decoded both picture and sound successfully while downloading was still active. The Envied run reached final file handling at 4.480 seconds. All 22 ordered segment observations were recorded. The muxer exited successfully and the completed transport stream decoded without errors: H.264 960×540 at 25 fps with AAC, matching audio/video start timestamps of 0.080 seconds. A 0.25-second observation delay per segment was inserted, so these timings are diagnostic measurements rather than expected production startup latency.

Envied's final file handling failed because the installed Mac lacks `libmediainfo`. This occurred after the playable tracks had already fed the progressive stream. Accordingly this is a successful progressive-output proof with a separate final-output dependency failure; it is not a successful unmodified Envied command. The installed application and production services were unchanged. The trial used isolated settings and local tools, not a third-party key vault. Raw logs, private session data and captured media are excluded from deliverables.

See `envied-u-real-progressive-proof.json`. This was a short Mac trial, not a full-episode or Pi performance test. The Samsung was unreachable during the check, so physical TV picture, sound and lip-sync remain unverified. No new provider has been enabled on the production dashboard. Channel 4 has not passed the corresponding progressive Envied test.


### Physical Samsung follow-up

After the user switched on the small Samsung, a temporary expiring LAN URL served the growing real U transport stream from the Mac. The TV requested it and reported PLAYING with position advancing from 2 through 17 seconds while Envied was still downloading. The user confirmed the picture looked good; the initial content was credits, so lip-sync could not be judged. This establishes real provider → progressive processing → LAN → Samsung playback for the short trial. It does not establish full-episode reliability. The first two unknown-length short trials ended early after the file finished arriving; a real-time paced codec-copy trial is being checked separately.


### Confirmed lip-sync correction

The dialogue sample exposed a timing issue in the trial adapter. Original video began at timestamp 180.080 seconds and audio at 178.560 seconds, a 1.520-second difference. The initial FFmpeg command reset each input independently and lost this relationship. Adding `-copyts` preserves the common source timeline. The user then explicitly confirmed: “Yes, in sync now”. No audio or video re-encoding was added.

The reader was also corrected to keep a persistent open file handle, rather than repeatedly reopen the temporary pathname. Envied moves completed tracks during final handling; a persistent handle keeps the remaining bytes readable after that move. The source feed is paced in real time for the old Samsung's unknown-length stream. The full-episode, Pi deployment, Channel 4 progressive path and production dashboard integration remain separate work.

The corrected real-time LAN trial advanced past 62 seconds on the TV and stopped near the end of the approximately 67.5-second transport stream. It continued beyond the final-file handoff without truncating at 20–30 seconds. This completes the short U progressive-playback proof with user-confirmed lip-sync. The equivalent Channel 4 Envied proof has not passed.


## Real Channel 4 progressive proof

Taskmaster Bleeped 80485-001 also passed a short real-provider LAN trial. The first native rolling-merge attempt fetched both complete source tracks before playable output appeared; this was explicitly not counted as progressive proof. The selected Channel 4 representations each consist of a single MP4 resource, so native rolling assembly alone is insufficient.

A separate trial adapter used the installed Envied ALL4 resolver and access processing, then connected a ranged streaming reader directly to FFmpeg. HTTP byte ranges preserve the service's resource encoding and avoid waiting for the entire track. A 65-second excerpt beginning near source timestamp 180 seconds was combined using codec copy, original timestamps and real-time pacing. It produced H.264 1024×576 plus AAC in MPEG-TS. At the first successful partial decode (3.549 seconds), the reader had received 1,572,868 video bytes and 1,376,260 audio bytes from source resources of approximately 543 MB and 47 MB respectively. This establishes that the entire episode was not fetched before playback.

The small Samsung requested the expiring LAN URL and reported advancing playback through 61 seconds before stopping near the end of the 65-second excerpt. The user explicitly confirmed “Yes, all good and in sync”. The completed excerpt decoded without errors. No audio/video re-encoding or browser capture was used in this trial.

This is a custom Envied-assisted streaming adapter, not the unmodified Envied downloader. Trial settings, source resources, session details and raw logs remain private; no production dashboard or existing service was modified. Pi deployment, a full-episode reliability test, cancellation and production packaging remain outstanding. See `envied-channel4-real-progressive-proof.json` for redacted evidence.
