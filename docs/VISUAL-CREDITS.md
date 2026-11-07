# Visual credits detection — Apple TV build 60

Watch samples the playing, unprotected video every three seconds in the final two minutes (and final 20%) of an on-demand episode. Apple Vision recognises text on reduced-size local frames. Multiple recognised credit-role lines in a multi-line layout must persist for three samples spanning at least five seconds. Dialogue, single captions and black frames alone do not qualify. Missing frames, pauses, seeks and gaps break the evidence sequence.

Provider credits markers take priority. A visual detection may bring up Up next early; it never skips content or starts autoplay before natural completion. The final-ten-seconds fallback remains. The detector does not prepare or download another stream and is independent of scene-lighting settings.

Results are cached on this Apple TV only, keyed by episode, source and exact provider version, with a matching-duration check. Unknown versions are analysed anew. Detections are not published as verified provider chapters or skip markers. Protected streams without exposed frames use provider markers or the fallback. Films and live channels are excluded.

This initial conservative recogniser targets English role-and-name credit layouts, including overlaid credits. Sparse credits, other languages, very fast scrolls and picture squeezes may be missed. Physical-device accuracy remains to be evaluated on real episodes. Tests cover sustained evidence, seek/dialogue rejection, provider precedence and synthetic OCR credit/dialogue/black frames.

## Build 61: ahead-of-time music and picture-text analysis

For an existing clear BBC direct source, or a complete finite relay file beginning at episode zero, Watch requests a private 90-second ending preview after playback has a healthy buffer. This reuses the current session: it never prepares the next episode or replaces the visible source. It does not fetch protected material or bypass DRM. Exact provider-version checks reject a preview from a different rendition/version; partial relay files and mismatched preview durations are rejected.

The Pi makes a 640-pixel, one-frame-per-second MP4 with mono audio. Remote input is paced at twice real time, one worker runs at a time, at most two analyses can be pending, each process has a 90-second limit, and previews are bounded to 12 MB with a 24-file private cache. Playback delivery itself is unchanged. Apple TV downloads the authorised preview, analyses it locally using Vision and Sound Analysis, then deletes its temporary copy.

Ahead analysis requires either strong multi-line credit-role text, or weaker credit-role text supported by music in two consecutive sampled frames. Music alone never triggers. Once text confirms credits, a continuous music run of at least six seconds may backdate the cue by up to twenty seconds, provided that run reaches the text evidence. An earlier musical passage separated by dialogue does not qualify. This is general music classification, not recognition of a learned programme-specific theme.

The actual QI Series W episode “Weaponry” preview produced a cue at 1735.22 seconds of 1763.72 (28.5 seconds before the end), compared with 1751.72 from text alone. This was an offline run of the production Apple analysis on the real preview; on-TV card timing remains to be verified. Test runners: `run-ending-analysis.sh <private-preview.mp4> <episode-start> <duration>`, `run-credits-vision.sh`, `run-playback-extras.sh`, and server `test_ending_preview` (including real ffmpeg timing and API ownership checks).

Paired APIs: `GET /playback/ending?ticket=…&version_id=…` returns `state` (`analysing`, `ready`, `unavailable`), `version_id`, and ready `start`/`duration` in episode seconds. `GET /playback/ending/file?ticket=…` returns the preview only to the current session owner. These endpoints accept no media URL or filesystem path from a caller. Unsupported sources retain live visual analysis, provider markers and the ten-second fallback. Near-end starts may not leave enough time for first-time ahead analysis.
