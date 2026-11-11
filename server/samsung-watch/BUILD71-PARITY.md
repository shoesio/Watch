# Samsung 0.340 — Apple TV build 71 parity

## Scope and navigation

This is a Samsung Orsay update only. It retains the four-card hero pages, eight-card library grids, paging, live guide, discovery, search, Similar, Featured, favourites, saved playback positions and existing provider delivery. Visible pages are loaded on demand; shelves are not removed to conceal cost.

Show cards open their detail page, directly in **All series**, newest first. Continue Watching/named cards pass the exact episode ID to an authenticated page lookup; the server selects its page and the remote focuses its card. Opening a show does not prepare playback. **Choose episode** returns focus to that episode. **All series** opens the retained series selector. Episode selection is the explicit playback action. Films open a detail hero with **Play**; live channels tune directly. Explicit main section selections return to that section's root. There is no show-page Start over action; the existing playback transport can still restart an episode.

Episode cards show an episode heading, description and runtime/known SD or HD, without another episode/title line. Series prefixes appear only in a mixed All series list. Provider badges remain separate. Runtime/quality are not guessed when missing. Show-page stills use a 16:9 frame, the title-to-description gap is four source pixels, and progress rails have clear bottom/caption spacing.

## Presentation and performance

- The established 1920×1080 package and source scaling are retained. Dimensions are assigned before image requests; bitmap aspect ratios are preserved. Hero crop offsets align the image's upper third with the frame's upper third.
- Private matched TMDB artwork metadata already produced by the household's catalogue refresh is read without credentials or another client's pairing. It refreshes locally at most every 30 seconds. A portrait row is used only when every visible Featured card has a real matched poster; the image service rejects landscape substitutes in poster mode. Other rows stay consistently landscape. Hero/card backdrops reuse the cache.
- Images are resized into bounded hero, thumbnail, card and poster caches. Concurrent requests for the same processed image share one worker. Remote focus changes do not reload the current hero or rebuild its cards. Extras controls rebuild only when their contents/focus change.
- Focus uses a modest 3.5% 2D enlargement, shadow, subtle border and small badge depth. Only entering/leaving focused cards animate. Unsupported transforms retain a static border; reduced motion disables movement. There is no continuous parallax, blur or backdrop filter. Physical Orsay responsiveness remains to be checked.
- Genuine portrait posters have no separate show-logo overlay. Explicit artwork-title metadata suppresses hero logos; ordinary landscape cards retain captions outside the picture and do not stamp a second logo on the artwork. Apple Vision's automatic title OCR is not available on Orsay/Pi, so there is no claim of equivalent automatic recognition of every title-bearing hero.

## Up next and safety

The compact bottom-right card is independent of ordinary transport visibility: full-image background, local gradient, provider badge, episode title, series/episode/runtime, **Next episode** and **Exit**. There is no manual Up next/Play next action in ordinary transport. Autoplay remains an optional persistent transport setting.

An exact-source/version validated credits cue can offer it early. Without usable credits timing, it appears in the final ten seconds. That fallback is not labelled as detected credits. When autoplay is enabled, the remaining seconds appear inside Next episode. Reaching zero does not prepare video: only natural completion, successful progress persistence and a successful revisioned queue advance can auto-start the next stream. Autoplay is suppressed if no cue was offered, on cancellation, conflicts, errors or reduced motion. Back/Up dismisses the early card and cancels autoplay for this episode; Exit returns to browsing. Final episodes return without an empty panel. Explicit Next episode may switch immediately at the user's request.

QI's single-letter seasons and `Series W`/`Series X` use the shared chronological fix; named specials are not guessed into order. Chapter/skip seeks remain episode-relative through relay offsets. Paused seeks, pause-position reopening, buffering recovery, ownership, source/version validation and completion guards are retained. Reviewed credits cues also require matching duration and never become skip controls.

## Credits detection investigation (separate work)

Apple TV builds 60–63 use **Apple Vision and Sound Analysis on tvOS**, not a general Pi detector. The shared ending-preview builder creates a bounded private clear-video sample; it does not itself detect credits. Samsung's current gateway does not expose or use Apple TV's preview endpoints, tokens or detection cache.

Inspection on this Pi found ffmpeg, but no installed Tesseract OCR executable or deployed equivalent music/text analysis model. Most Samsung provider/Streamlink sessions deliver a rolling relay. The Samsung resolver also does not currently report an exact BBC version ID. Copying an Apple TV session/preview or applying a different edition's results would not satisfy source/version/duration binding.

A safe later implementation could analyse an **existing complete clear local file**, or an already resolved clear source with an explicitly known version, through this Samsung's own ticket. It would need separate low-priority bounded extraction and OCR/music workers, strict ownership/source/version/duration checks, cancellation and a private cache. It must not prepare another stream or analyse a rolling partial relay as a complete programme. That is substantial separate work and is not enabled here. Verified provider/reviewed cues and the correctly identified near-end fallback are implemented now.

## Build, rollback and verification

The source checkpoint is `checkpoint-samsung-0.335-before-build71-parity`. Private Pi backups preserve the previous paired ZIP/install list and changed gateway files. The installer stages `SamsungWatch_0.340_Europe_20261111.zip` under the unchanged SamsungWatch identity. Connection, volume plugin, assets, native autostart profiles and provider sessions are preserved. Only the Samsung gateway was restarted, after checking for connections, preparation/stream children and recent progress; the other services were not restarted.

Automated checks: 160 backend cases and ten client scripts cover navigation/focus, All series/filtering, metadata, portrait validation/cache coalescing, W→X ordering, verified credit binding, offsets, pause/recovery, countdown cancellation, natural-only continuation, queue conflicts, final episodes, stale/missing metadata and audio fallback. The staged package is read back over HTTP and checked for ZIP integrity and unchanged pairing/assets.

Physical installation is confirmed: the TV fetched the 0.340 ZIP and opened it; its session reports 1920×1080. Viewer confirmation remains pending for remote focus, crop/headroom, typography, static/moving focus, episode selection and real end-to-next playback. Installation/session telemetry is not treated as visual or playback verification.
