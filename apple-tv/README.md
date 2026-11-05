# Watch for Apple TV

Native SwiftUI tvOS app, with AVKit playback on the Apple TV itself. Open **Watch.xcodeproj**, select **Watch → Living Room**, then Run. There are no casting controls or output selectors.

## Included

- For you, Shows, Films, Live TV, Search and Settings.
- Provider favourites and recent programmes from the existing Pi catalogue; background provider sync remains owned by the established HA bridge.
- Clear logos, hero artwork, programme/episode descriptions and provider/channel branding.
- Continue watching, newest-first series/episodes and existing measured-quality duplicate selection.
- Applicable genre filters; series selection within show details.
- Live now/next, with one current image and text-only next programme.
- System typography with consistent 24–25 pt card titles, padded card interiors, native focus lift, rounded artwork and restrained filter transitions; Reduce Motion respected.
- SD/HD/UHD badge based on actual video dimensions: briefly shown at playback start, then coordinated with the system transport controls.
- Matching programme/episode card sizes and top-left provider badges.
- AVKit decoding with native live controls and a full-episode on-demand transport, Siri Remote support, frame-rate matching and metadata. Audio/subtitle choices appear if supplied by the source; this release does not add missing subtitle tracks to the existing relay.
- Progress every five seconds, automatic stall recovery, and Retry/Back actions without returning to the catalogue on a stream error.

## Pairing

The Pi service is `watch-appletv.service` on LAN port **8115**, separate from HA (8109) and Samsung (8113). Provider credentials remain on the Pi. The app stores only a scoped device token in Keychain.

Run **Pair Apple TV.command** and enter its eight-digit code in Watch. Codes expire after ten minutes and are single use; failed attempts are rate limited. The default Pi address is `http://192.168.0.146:8115`, editable on the pairing screen. Allow the local-network prompt.

Pairing and media use the existing trusted home LAN over HTTP. This service is not intended for port forwarding or public exposure. Media URLs are short-lived random session capabilities. Server access logs are disabled so tokens and source URLs are not recorded.

Device tokens are hashed in the private `appletv/devices.json` file. Remove a device's hash there to revoke it. Disconnect in the app clears its local token.

## Playback and seeking

Source preparation uses the existing Pi resolver, with codec-copy HLS packaging and preserved A/V timestamps. No desktop capture or video re-encoding is introduced.

On-demand shows and films have their own **full-episode timeline**, independent of the rolling HLS window. Pause, press Up to focus the timeline, move Left/Right and press OK to commit. Continued presses accelerate from 10 to 30, 60 and 120 seconds. Down cancels the preview. A buffered target seeks locally; an unbuffered target reopens the source at its absolute episode time while keeping the full-screen player and loading spinner. Live channels retain the native live player. The custom on-demand transport currently does not expose native alternate-audio/subtitle or picture-in-picture menus.

The tvOS-specific codec-copy packager starts with at least 12 seconds buffered, retains approximately three minutes of segments, and does not apply a second real-time throttle. A stall gets a 60-second grace period and up to three reconnect attempts. Automatic reconnects preserve the picture/spinner; the initial artwork loading screen is reserved for initial preparation. Long pauses no longer trigger unconditional source restarts. Redacted player buffer/retry metrics and relay status are written in the private `appletv/playback-status.json`.

Streamlink sources use **best**, with a tvOS-specific measured-quality cache. This removes catalogue preferences written for old Samsung TVs; it cannot create unavailable UHD renditions or change provider access restrictions. The existing protected-provider resolver remains unchanged and still has its prior limits. The tested BBC live source exposed 720p50, not UHD. Channel 5 live feeds remain hidden because there is no verified supported direct route.

Progress uses the HA journal, which already reads the native Samsung journal. The running legacy Samsung service must adopt the shared journal helper before immediate HA/Apple-TV-to-Samsung resume can be promised; this app does not restart that service.

## Pi deployment

Copy all Python modules from `Gateway/`, plus `settings.example.json` and `watch-appletv.service` to `/home/jhewes/watch-appletv/`. Copy settings to `settings.json`, install the unit under `/etc/systemd/system/`, and enable it. The service imports the existing `/home/jhewes/tv-favourites` modules and uses its virtual environment. It starts no HA event listener and never calls remote playback endpoints.

Run gateway checks on the Pi:

```sh
cd /home/jhewes/watch-appletv
/home/jhewes/tv-favourites-venv/bin/python -m unittest test_server
```

## Xcode and signing

The project targets tvOS 17+, uses the existing development team, and has no package dependencies. Automatic signing is enabled. The build-13 development profile expires on **4 November 2026**; re-run from Xcode when renewal is needed. For a different account, change Team and Bundle Identifier in Signing & Capabilities.

TMDB attribution is included in Settings. Existing provider and programme artwork is used from the catalogue.

Apple AVKit documentation: https://developer.apple.com/documentation/avkit/avplayerviewcontroller


## Design review — 29 October 2026

Shared four-column sizing, 88 pt content insets, consistent card typography, fixed text slots, downsampled/cached artwork, and dark appearance throughout. All hero views share a 440 pt height with right-flush 16:9 artwork sized from height and a left fade to black. Loading logos use centred alignment. Films have a featured hero and a two-column details area; series open on the newest season, with a series picker. Screenshots of reviewed screens are in `Review/`.


## Discovery and age ratings — Watch 1.2

Search combines the current library with public catalogue metadata from BBC iPlayer, Channel 4, U and Channel 5. The Channel 4 index refreshes every six hours; typed searches are debounced and cached briefly. Partial provider failures are labelled. Exact-title results combine provider badges. Selecting a new result fetches its available episodes into a bounded, separate private discovery cache. This does not change provider favourites/history, the HA catalogue file, or provider playback handling. Episode availability is checked on opening; individual new titles are not all physically playback-tested in advance.

**Picked for you** uses local favourites and actual viewing progress, recency, canonical genres, programme formats and synopsis-word overlap. The candidate pool includes full relevant BBC categories, Channel 4's index, Five's index and the existing library. Comedy documentaries are distinguished from panel shows, sitcoms and stand-up; broad extra collection tags and catalogue import time cannot supply preference boosts. A relevance-weighted recent window discourages runs of one provider/format while retaining later pages. Ready-to-play library metadata wins over duplicate discovery previews. Show-heavy profiles favour series over films; known children's/animation metadata is excluded from adult suggestions. This remains an explainable local heuristic, not collaborative learning or a guarantee of personal taste.

**Hot now** uses BBC's Most Popular Today and Channel 4's actual Popular catalogue ordering, then favours relevant genres. Cards identify their popularity source; it is not presented as an all-service audience chart.

UK age certificates come from TMDB's GB content-ratings/release-dates records, using existing confident title matches. Cards, hero/details and the on-demand transport show the rating where known. Other countries' ratings, ambiguous certificates and unmatched alternate editions are omitted. Ratings are display information, not a parental lock. Enrichment is cached and incremental; newly imported titles are matched for clear logos and ratings in the background.

New private files are confined to `tv-favourites-private/appletv`: catalogue index, bounded discovery library, and UK-rating cache. Provider credentials remain in their existing private locations, never in client responses or source bundles. Search queries are not persisted as a user history.


## Watch favourites

Use the heart on a programme/film detail page, or the card's context menu, to add or remove a Watch favourite. Favourites are persisted on the Pi in `appletv/favourites.json`; explicitly saved programme metadata is retained separately so a saved discovery title survives the bounded discovery-cache eviction. The home favourites row and recommendations use the merged result.

Provider favourites continue to be imported. A Watch override may hide or retain a title independently of its provider list. **No favourites are written back to BBC, Channel 4, U or 5.** The current provider connectors are read-only for account lists. No provider-write API was added or verified in this update.

Hero composition uses provider badges as the eyebrow above programme/film titles throughout the app.


## Genre discovery and descriptive cards

Shows and genre views begin with up to 16 recently watched or favourited programmes, followed by a continuously paginated grid ranked for your viewing. The genre menu orders available genres by your viewing preferences. Recently watched timestamps and locally recorded favourite actions determine the personal opening; provider favourites without dates remain eligible, and import/sync times are not treated as viewing history. Discoveries fetch episode availability on opening.

Cards now show programme/film synopses rather than generic recommendation reasons; continue-watching cards retain their progress and remaining-time information.

Apple TV app Watchlist/Continue Watching sync was researched but is not implemented: no supported public Watchlist write API was verified for this personal app. Apple documents its TV app content integration as a partner-onboarded programme: https://tvpartners.apple.com/support/3660-video-app-integrations-partnership-requirements . Watch's own Pi-backed favourites remain separate.


## Continuous suggestions and rotating film picks

Genre suggestions and the home **Picked for you** row load another 24 entries automatically near the loaded end. The server holds a bounded, paired-device-scoped snapshot of the relevance ranking for up to an hour of inactivity. Page order stays stable even if favourites change while scrolling, duplicates are removed and loading stops at the end of the finite source catalogue. A changed genre starts a fresh ranking. Interrupted loads offer retry without discarding already loaded results. BBC genre metadata now follows catalogue pagination rather than stopping at the first 80 entries.

The films hero uses six daily, taste-led feature picks rather than the first alphabetical title. The selection excludes recently viewed items, very short films, live sources and entries without usable artwork; it prefers personal genre matches and tries to vary providers and genres. Left/right buttons browse the picks. Idle rotation occurs every 18 seconds, pauses when the hero or its arrows have focus, stops while another page/playback is active and is disabled with Reduce Motion.


## Related shows and focus navigation

Non-film detail screens include **Similar shows** beneath episodes. TMDB aggregate credits, creator crew credits, production-company matches and related-show metadata provide relationship candidates. Verified shared cast/creator connections rank ahead of genre/format fallback. Unknown titles must match the supported providers' catalogue metadata before they enter the row; a metadata recommendation alone is not proof of provider availability. Available episode details are loaded on opening as in other discovery views. Original titles and obvious edition aliases are excluded. Results use the same device-scoped, stable 24-item paging snapshots, automatic append and finite-list end state as genre discovery. Relationship metadata and provider checks are cached; the first uncached request can take longer.

The series selector is positioned beside the Episodes heading at the left of its focus section, above the first episode cards, so short rows no longer leave it stranded at the far-right edge. Native left/right/down navigation is retained. Film previous/next controls and their position indicator are now inline with Play/Details in the hero, rather than in a far-right footer; all hero controls pause automatic rotation while focused.


## Channel 5 genre recommendations

Channel 5’s public catalogue now feeds genre discovery, home recommendations and related-show matching, rather than typed search alone. Broad genres and collection/subgenre labels are combined so documentary titles retain the Documentaries category when imported. The paginated index is cached for six hours, retaining the last good catalogue if a refresh fails. Existing paged recommendation snapshots remain stable; change genre away and back to create a new ranking.

Verified against 1,566 Channel 5 catalogue titles: 910 documentary candidates, 713 ranked new documentary suggestions for the current library. Episode metadata for Billy Connolly: In His Own Words loaded successfully (one available episode). This check did not start playback. The gateway suite passes 46 tests. No native app reinstall is required.


## Native playback — Watch 1.3 (build 4)

Channel 5 standard live channels (Channel 5, 5USA, 5STAR, 5ACTION and 5Drama) now use native AVFoundation/FairPlay on Apple TV, as do supported Channel 5 on-demand episodes. Open Settings → Connect Channel 5 and complete the activation code on your phone. The Apple TV account session is kept in a separate device-only Keychain entry; the Pi's existing login is not exported. Native Apple licence processing retains media encryption and sends no media/content keys to the Pi. Provider rights, account, region and licence decisions still apply. The implementation adapts Telly's GPL-3.0-or-later modules; see NOTICE.md and LICENSE.txt.

The Pi still provides catalogue metadata, recommendations, available episode identifiers and shared progress. Channel 5 video and licence traffic go from Apple TV to the provider. Live listings and now/next refresh from public broadcaster metadata every five minutes. This first integration includes the five standard channels; themed FAST feeds are not enabled.

Clear BBC HLS can now play directly from the CDN, with the Pi resolving a fresh URL but no Pi media reader or ffmpeg relay. HLS is selected only when its advertised video resolution/frame-rate rank matches the highest available Streamlink rendition. DASH audio-name bonuses do not count as a higher video resolution. Independent playlist checks confirm no Pi cookies are required; unexpected protected HLS or unsupported sources retain the established route. This is not a new UHD resolver: quality is still whatever the existing BBC discovery exposes. If direct BBC playback fails, Watch retries through the Pi relay. Shared progress and full-episode seek positions work on either path.

Native sources are represented by device-scoped progress sessions, not Pi media capabilities: `/stream/…` cannot expose their media. The existing HA and Samsung services and their playback routes are unchanged. Channel 4 and U retain the established Pi route pending their own native integration.

Verification: signed device build and physical install passed; 56 gateway tests plus 12 native Channel 5 parsing/boundary checks passed. BBC One and BBC Four independently resolved/probed as clear H.264/AAC 1280×720 at 50fps without a relay. An Absolutely Fabulous on-demand episode resolved/probed directly at 960×540/25fps with a 120-second initial seek and no relay (source resolution, not a device claim). Five's five channel listings and now/next were checked. After completing Apple TV sign-in, Channel 5 reports native playback at 1920×1080 with a roughly 19-second buffer, no stalls and no retries. The viewer confirmed Channel 5 picture, sound and lip-sync are all good. 5USA, 5STAR, 5ACTION and 5Drama also reached native 1920×1080 playback with no reported stalls/retries in the short checks; 5Drama required a second launch after the first check did not confirm playback. The viewer picture/sound/sync confirmation applies to Channel 5.

Run native parser checks on macOS with `Tests/run-channel5.sh`; the server suite adds `test_native_playback` to the existing unittest command. No provider credentials are needed for those tests.


## Artwork preload screens — build 6

Playback preparation and episode-discovery loading screens retain crisp programme artwork. A soft radial dark gradient fades out behind the centred logo and text for contrast; the artwork is not blurred. Preload artwork uses the image cache with a 2560-pixel decode cap.


## BBC episode artwork

BBC episode cards now prioritise the episode's `images.standard` still rather than `promotional` or `promotional_with_logo`, which usually contain repeated series/season key art. Programme heroes and clear logos are unchanged. Existing catalogue entries are enriched by a private Pi cache of public BBC episode images, keyed by exact BBC episode PID and applied only when the selected source is BBC. Other providers' episode images are retained. Provider metadata refreshes at most every six hours per programme; new titles are checked in the background and last good stills survive temporary API failures. Missing stills retain the existing image rather than borrowing an unrelated episode.

Both future BBC discovery imports and the shared account-sync importer select the standard image first. The native app requires no rebuild for this metadata correction. Verification found 1,766 BBC stills across 299 catalogue records. House of Games has 133 distinct images for 133 episodes, Doctor Who (2005–2022) has 177 for 177 and Absolutely Fabulous has 39 for 39. QI has 341 distinct images for 342 episodes; an occasional shared BBC image is retained as supplied. The gateway suite passes 63 tests.


## Personal browsing and For You highlights — build 7

The Shows opening contains up to 16 recent/favourited series, also within each genre. The following **More to explore** grid combines other library titles and supported catalogue discoveries, ranks them by relevance and keeps loading in stable 24-item pages. Titles in the personal opening do not repeat in the discovery continuation. Existing paging ownership, expiry and finite-list behavior remain. Favourite actions made inside Watch now record a separate action timestamp; no provider-favourite dates are invented.

The For You hero now has six ready-to-play highlights, with the same inline previous/next controls, position indicator, 18-second idle rotation, focus pause and Reduce Motion behavior as the films hero. Selection combines recent viewing and relevant library highlights. Films retain their existing feature selection. Native screenshots confirm the home hero's 1/6 counter and inline controls.

Verification: signed device build and physical install passed; 74 gateway tests pass, including personal-16 ordering, film/genre exclusion, provider diversity without discarding later results, exact-title deduplication, signed-alternate suppression, six unique playable highlights and separate non-overlapping personal/discovery pages. In the checked profile, the first 24 Picked for You titles changed from 24 Five titles to a mixture of Channel 4, BBC, Five and U. Source-count and relevance metrics are saved in verification.json. Provider accounts and playback routing are unchanged.


## Live channel marks and watched-card descriptions — build 8

All 14 live channel badges now use tightly cropped transparent identification marks rather than landscape channel card artwork. The existing 64×32-point logo frame and badge padding are unchanged. BBC channel badges display just ONE, TWO, FOUR and NEWS, Channel 4 family marks are extracted from the existing vector branding, and Five family marks use the official transparent PNG channel-logo endpoint. Files and source credits are in ChannelLogos/. The gateway points only the Apple TV channel_logo fields at versioned static assets; programme artwork and fallback landscape cards remain separate.

Programme/film tiles now always retain their three-line synopsis (or existing fallback text) even when a resume position exists. A subtle five-point progress bar sits beneath the synopsis, like the episode cards. Unwatched cards reserve the same space with an invisible bar to preserve grid alignment. The previous replacement by remaining-time text is removed. Playback progress data and resume actions are unchanged.

Verification: signed device build passed; 76 gateway checks passed. All 14 marks were rendered and visually reviewed at badge size, and sample BBC, Channel 4 and Five static URLs returned PNGs successfully. Native app updated to build 8.


## Live-card programme synopses — build 9

Live cards show a two-line current-programme synopsis beneath the title, before the channel/time and progress information. Fixed-height synopsis space keeps the grid aligned. The next programme retains title/time only. BBC descriptions and accurate schedule boundaries are fetched from public IBL broadcast metadata every five minutes and selected against current time; Channel 4 uses its existing guide summary. Five's existing programme descriptions are supplemented by exact-title matches in its public catalogue when available. Missing descriptions remain blank; no unrelated or speculative synopsis is inserted. No playback route changes.

Verification: signed build and physical Apple TV install passed; 79 gateway tests passed. Live metadata checked for all BBC feeds and Five's main channel, 5STAR and 5ACTION. Some Five listings (including the checked Law & Order and Columbo titles) have no available description in these metadata sources.

The BBC badge marks were simplified to channel-name-only artwork at the user’s request. Versioned channel-marks-v2 URLs bypass the previous image cache; no app reinstall required.


## Off-air live listings

The Apple TV catalogue hides live channels whose current, time-valid programme is an explicit off-air listing or BBC holding slate (for example This is BBC Four). Normal programme listings reappear on catalogue refresh once the schedule changes. Missing or stale guide data is not treated as proof that a channel is off air. This changes displayed listings only, not provider playback or saved channel configuration. Verified daytime BBC Four is absent while the other 13 live channels remain. 85 gateway tests pass.


## Five live programme artwork

Five family live cards now use current-programme artwork matched against the broadcaster's catalogue by exact normalized title. Missing catalogue entries may use a unique exact-title TMDB series backdrop; ambiguous remakes are left unresolved unless explicitly reviewed (Law & Order is the original US series, TMDB 549, not the 1978 BBC namesake). These are programme/series images, not claims of episode-specific live frames. The schedule's current title selects the artwork at each guide refresh; the channel badge continues using its separate transparent mark. No match keeps the channel card fallback. Artwork results are cached for a day; unresolved titles retry after 15 minutes. Playback is unchanged and no app reinstall is required.

Verified programme images for all five current listings: Bargain Loving Brits in the Sun, Law & Order, Police Interceptors, Traffic Cops and Gilmore Girls. 90 gateway tests pass.


## Live startup presentation and resilience — build 10

Live startup now chooses current-programme/card artwork before channel hero art, and shows a channel mark, current title and synopsis. Native playback metadata uses the same current broadcast details rather than duplicating the channel name. Artwork stays until the player first reaches playing; reconnects after that retain the video frame and spinner.

AVPlayer requests a 45-second forward buffer for live content (30 seconds for VOD), allows live networking while paused, and uses a 30-second live offset where the stream supports it. These are player preferences, not fixed startup waiting periods or guarantees that the broadcaster retains that much media. Automatic stalling minimization remains enabled; highest stream quality policy is unchanged. No background channel switching is added. Native HLS retains its own rendition adaptation; BBC can fall back to the established Pi relay after direct playback failure.

Failed-to-play-to-end notification now triggers recovery, stale failure observers are generation-guarded, and live startup/automatic reconnect preparation failures retry up to six times with bounded 2/5/10-second backoff. Temporary stalls remain in the player. Relayed live inputs that already ended before twelve seconds are no longer advertised ready; short finite clips remain supported. Protected provider resolution is unchanged.

Observed 4seven issue: relay input ended after roughly eight seconds, leaving an ended two-segment playlist. This update rejects that false-ready case and reconnects; it does not establish that broadcaster/source interruptions are eliminated. Short native Five check: 1920×1080 playback, roughly 26–29 seconds buffered, zero stalls/retries. No sustained provider-wide stability claim is made. Signed physical build installed; 95 gateway tests pass.


## Provider accounts — Watch 1.4, build 11

Settings now groups native provider accounts. ITVX and U join Five with QR activation, an alternative provider website/code, connection state, retry/new-code and sign-out. ITVX uses itv.com/pair; U uses u.co.uk/activate. Users complete login on the provider's website. Device sessions are stored in separate Apple TV Keychain namespaces, never in Pi responses or source bundles. Cancellation/sign-out invalidate pending work; ITV supports session renewal through its provider service. Provider accounts on the Pi and provider favourites/history are not written or replaced by these device logins.

Native ITVX support includes the five standard live channels (ITV1, ITV2, ITVBe, ITV3 and ITV4) with public now/next, synopsis, artwork and channel-logo metadata. Search now includes ITVX, and public featured/category metadata feeds recommendation candidates. Selecting a result imports available free episodes into Watch's existing bounded discovery cache. The current catalogue test returned 431 titles; The Chase imported 506 episodes. Provider HTML outages can fall back to the actual latest production ID published by ITV's public search; this is labelled Latest available episode rather than inventing complete season metadata. Premium titles are excluded from these imports. ITVX Premium native playback remains unsupported.

ITV free on-demand and signed-in live playback use Apple's native FairPlay pipeline. U on-demand also uses its native AVContentKeySession route after U sign-in. Provider video/licence traffic stays between Apple TV and provider; no content keys or provider session tokens are relayed through the Pi. BBC and Channel 4 retain their established Pi account connections, and Settings states this explicitly. No working in-app QR connector was verified for those existing routes. Their playback and favourites behavior is unchanged.

Validation: signed device build/install passed; 102 gateway checks passed. Native account tests exercised ITV token parsing, pairing/exchange, persisted state, sign-out, U pairing parsing, host boundaries, and both real provider code-generation endpoints without printing codes/tokens. The existing 12 Five parsing/boundary checks also pass with the expanded native adapters. A native Swift ITV free-VOD probe obtained an allowed HLS source and 1,234-byte FairPlay application certificate. These are not claims of successful protected playback on this Apple TV: ITV/U account completion and viewer picture/sound checks remain pending. Five's previously verified login remains in its separate Keychain namespace.


## Startup and film browsing — Watch 1.4, build 12

Discovery and playback now share a crisp, full-photo startup layout. A lower gradient supports centred clear logos, provider marks, episode/runtime information and a short synopsis, with a compact native spinner. There is no blurred artwork, fabricated percentage or duplicate film title. Live startup uses the current programme photo, channel mark, title and synopsis.

Films have an explicit `film_rank` in the paired library projection. The entire film grid and its genre subsets use that ranking, rather than the alphabetic transport order. The existing taste model uses actual favourites, watched genres/formats and synopsis similarity, with extra weight for film viewing. Up to four unfinished films lead; completed films move down. Provider variety and stable daily ties prevent an alphabetical or single-provider shelf. Seasonal Christmas titles get less emphasis outside November/December. Every film, including family films and alternate editions omitted by recommendations, remains in the catalogue. Current projection: 623 films with 623 distinct ranks, around half a second for the full library projection.

Direct provider VOD now uses AVPlayerViewController's native controls, including its finite-video scrubber and available audio/subtitle menus. The controller switches correctly when preparation resolves a direct route; overlays are installed once and hidden when falling back to a relay. Native position tracking has zero relay offset, and completion uses the actual finite asset duration when available. Pi rolling-HLS VOD retains the existing full-episode timeline, because its short moving window cannot represent the whole programme in AVKit. No provider resolver, quality cap or protected Pi playback path changed.

Validation: signed physical build/install passed, 106 gateway checks passed, and the existing 12 native Five parsing/boundary checks passed. The physical Films grid and Taskmaster Bleeped startup screen were inspected; Five native live playback reached the HD player with native transport. Audio/subtitle availability still depends on each source. ITV/U protected playback still requires the account/viewer checks described above; this update does not claim those checks are complete.


## Pause/resume and Channel 4 live — build 13 (4 November 2026)

Relayed on-demand episodes now retain all of their HLS segments in an EVENT playlist for the session lifetime, instead of deleting the paused position from a three-minute rolling window. The playlist response explicitly declares `EXT-X-START:TIME-OFFSET=0,PRECISE=YES`; EVENT alone still lets AVPlayer choose a position near the growing live edge. Initial on-demand seeks include zero. Pause captures the actual source position, holds saved progress there, and resumes at that anchor through both the in-app transport and system play commands. Live-offset preservation is disabled so an intentional pause is not followed by a catch-up skip. Relayed live channels keep a bounded approximately thirty-minute window; upstream native live DVR limits still apply. Session release/idle cleanup removes the retained episode segments.

Channel 4, E4, More4, Film4 and 4seven have a native Apple FairPlay live route for build-13-capable clients. The Apple TV requests the broadcaster's adaptive, updating HLS stream and licence directly; the Pi provides catalogue metadata and progress only. This avoids the old relayed feed that was observed ending after 24 seconds. Older clients retain their existing route. No protected Pi resolver was modified. The checked Channel 4 master advertised a maximum 1024×576 rendition: native playback improves delivery, but does not invent HD or UHD. Measured quality badges still use decoded video dimensions.

Validation: 109 gateway checks passed before the final playlist-response test was added; the new test and the rest of the targeted native/packager suite passed (18 checks), as did the server suite. Twelve existing Five parsing/boundary checks passed. Channel 4 host/input checks and a real native source probe passed, returning eight adaptive renditions and the FairPlay application certificate. A generated 260-second episode retains segment zero beyond the old rolling-window limit, preserves timestamps and cleans up on release. The macOS AVPlayer integration test (`python3 Tests/run-pause.py`) started at the beginning, held ~3.02 seconds through a twelve-second pause, then reached ~6.04 seconds after three seconds resumed. This test uses synthetic unencrypted media and loopback HTTP. Build 13 was signed and installed on the physical Apple TV; native Channel 4 reached SD playback with approximately 43–48 seconds of buffer and no reported stalls/retries in the sampled interval. This is a short validation, not a guarantee against broadcaster/network outages.

## Playback extras — builds 14–15 (4 November 2026)

The Apple TV client now consumes the authenticated version-1 playback-features API. Build 15 uses the same Watch transport for direct and relayed video. Chapters open a dedicated remote-navigable sheet; Up next, pause, episode details and quality badges share one layout. Live TV uses the matching layout with Live/Go live in place of an episode timeline. Direct provider streams still use AVPlayer and native FairPlay underneath. Skip intro/recap controls appear only within validated exact-source intervals; unknown BBC playback versions keep skip controls hidden. Metadata fetching is asynchronous, generation guarded and cancelled when playback changes. Missing metadata does not hold up playback.

Up next uses the server's chronological per-device series queue, with artwork, synopsis and episode details. It can be opened from the shared Watch transport, and appears at actual completion. Autoplay is off by default, configurable in Settings or the Up next card, and uses a cancellable ten-second countdown. Metadata is fetched ahead, but no successor video is prepared until explicit Play next or completed countdown. Queue conflicts are re-fetched without repeating completion/advance; ambiguous state disables autoplay. A successor is resolved against the current library before starting. Previous episode progress/session is saved/released before resetting the new episode's clock.

Seek-to-end, live EOF, early relay EOF, duplicate end notifications, errors and buffering do not advance a queue. Chapter and skip seeks preserve paused/playing intent and use the existing absolute episode-to-relay-offset translation. Countdown/request tasks are cancelled on exit and source change. A global preference alone cannot autoplay without a coherent server queue and recorded completion.

Checks: `Tests/run-playback-extras.sh` exercises DTO decoding, source/version/stale-episode matching, interval boundaries/nonfinite values, completion guards, duplicate terminal events, expired successors and final queues. The pure model tests run on macOS without accounts or a simulator. Chapter and intro availability remains provider dependent; the API's sampled BBC episode contained no markers, and the client does not infer them from titles or pick a BBC version arbitrarily.

Physical verification: build 15 signed and installed on the living-room Apple TV. The viewer confirmed Channel 4 Taskmaster Play next starts the following episode. Build 14 exposed an AVKit focus trap on BBC; build 15 removed the supplier-dependent control UI, and the viewer confirmed BBC Have I Got News for You Play next works. A real two-episode queue was observed on the Pi with autoplay false, and the final episode's queue contained no successor. Chapter/intro seeking with a real marked episode and the full natural-end autoplay countdown remain unverified on physical hardware. The sampled BBC feature lookup returned `version_required`: the current playback response did not provide an exact version, so no intro timings are inferred or displayed. Build/test checks pass; no client credentials or provider sessions changed. HA/Samsung client sources were not modified by this task.

## Credits Up next — build 16 (4 November 2026)

A compact Up next card can now appear over the closing credits without pausing, hiding or replacing the video. It contains the next episode's artwork/details and Play next/Keep watching actions; Back also dismisses it. The Siri Remote's play/pause command remains available. Dismissal is remembered for the current episode, including recovery and seeks, and reset for the next episode. There is no early autoplay countdown or automatic queue completion: autoplay still waits for actual episode completion.

The cue consumes validated, exact-source `chapters` intervals with `kind:credits` or `kind:end_credits`. A chapter merely titled Credits is insufficient. There is no assumed final-N-seconds trigger. BBC credits cues require the actual version just like intro markers. Provider/importer or reviewed sidecar metadata can already supply these chapter kinds through the version-1 server contract; this client change does not invent missing markers. No cue appears for a final episode, live channel, unknown interval, pause, buffer/reconnect state, or mismatched source/version. Programmes without credits markers retain the end-of-episode Up next card.

The marker-state regression checks passed for explicit-vs-title-only metadata, time boundaries, pause/buffer/UI blocking, final episodes, once-only offering/dismissal and episode reset. Device build/install is recorded separately. A real provider-marked credits interval is still needed to verify automatic appearance and focus on physical hardware; no fake timing metadata was inserted into a user's episode to manufacture that proof.

## BBC actual-version metadata — build 17 and gateway handover fix

The earlier `version_required` result exposed a real integration gap: the selected BBC clear HLS stream's VPID was not forwarded to the Apple TV. The gateway now records the VPID passed to the actual media-selector result for each stream, retains it through quality selection, and returns it as preparation `metadata.version_id`. The existing client sends that version to the features endpoint. Edition timing is not inferred from matching runtime, titles or version-list order. This correction covers native clear BBC HLS; relayed BBC playback without a proven version still withholds version-specific markers.

A real source probe resolved The Vanquishers (Doctor Who episode m00129lb) to VPID m00129l9 and returned recap 1–29 seconds and intro 274–306 seconds. The physical Apple TV reached native BBC HD playback at position 289 seconds with no reported stalls/retries. Build 17 also gives the skip card explicit remote focus, Keep watching/Back dismissal and play/pause support. Viewer confirmation of activating the skip button is still pending. Four sampled Doctor Who episodes had skip interactions; four sampled Have I Got News for You episodes had none, so loosening edition matching would not create skip timings for those episodes. Credits without explicit metadata still use the end-of-episode fallback, not an assumed final-30-seconds trigger.

## Clear-logo proportions — build 18

Programme logos now use a single cached-image layout across the transport, home/film/show heroes and discovery/playback warmup screens. Images preserve their aspect ratio, are horizontally centred and share a bottom baseline. Upright/compact marks can grow above the transport's nominal 380×75 slot to a 150-point maximum; the neighbouring episode information also bottom-aligns. Wide wordmarks use a progressively smaller width allowance. Hero and warmup contexts reserve a constant amount of headroom so taller logos do not overlap provider eyebrows and logo loading/carousel changes do not move the baseline. No logo clipping is applied. Film hero descriptions use two lines to retain space within the common hero height.

Signed device build/install passed. Geometry checks covered upright, compact, wide and extremely wide aspect ratios, verified proportions and size bounds. Physical screenshot review could not be completed because the desktop device-review control timed out; appearance on the TV still needs visual confirmation. Provider/channel badges remain separate from this programme-logo layout.

## Hero alignment and taller logos — build 19

Hero clear logos now bottom-align flush left with the hero text/actions; the transport and warmup contexts retain horizontal centring. Upright show logos can reach 200 points in heroes (previously 140), with 180 points for film heroes and 250 in warmup screens. The transport's upward-overflow ceiling increased from 150 to 200 points. Wide-wordmark width limits and undistorted aspect ratios are unchanged. Hero spacing is twelve points, vertical inset twenty points and descriptions two lines, keeping the shared 440-point hero footprint while making room for the taller artwork.

Signed build/install passed. The physical Apple TV screenshot at 19:51:41 on 4 November shows the Doctor Who home hero with its larger clear logo flush left with the episode text/buttons, and no overlap with the provider badge or lower rail. The shared Hero component also supplies series/film heroes. The new transport height allowance was code-checked; a separate physical transport screenshot was not taken in this pass.


### BBC UHD — build 28

Watch now resolves available BBC UHD editions on Apple TV using its privately provisioned existing TwinVine identity. It requests the current programme editions, including technical replacements, and accepts only a clear on-demand 2160p HEVC DASH presentation whose initialization metadata signals BT.2020 / HLG. A loopback-only HLS bridge converts the manifest and normalizes CMAF fragment padding in memory; video and audio are fetched by the Apple TV, without Pi media relay or video re-encoding. Unsupported/protected/unavailable UHD keeps the existing HD route. A UHD playback failure disables UHD for that playback attempt before retrying HD. The quality badge remains based on actual decoded video dimensions.

Verification: isolated real BBC selector/manifest probe returned 3840×2160 HEVC with HLG for Blue Planet III: Open Ocean, exact version m00343ws. Physical Apple TV build 28 reported native-bbc playback at 3840×2160, about 30 seconds buffered, zero stalls/retries, and an initial episode-relative seek to 30 seconds. The user confirmed the UHD badge, picture and sound on the physical Apple TV. Longer viewing and manual scrubbing remain separate physical checks. Offline UHD tests exercise DASH templates/timelines, audio selection, HLG detection, protection rejection, loopback HLS and byte ranges, fragment normalization, and encoded-sample preservation.

Private setup is staged temporarily in tvOS Caches and imported into Keychain at startup; Documents is unsuitable for this handoff on tvOS. The staged file is removed after import. No setup package is checked into source.


### UHD browse collection — build 29

Films and Shows now offer UHD beside Favourites in their collection menus. Eligibility is per available BBC episode edition, not the TV output resolution or a previously played stream's cached quality. The Pi refreshes public programme metadata in the background, with four concurrent requests and six-hour per-episode caching; it never prepares playback while indexing. Technical replacements are supported, and expired/future/signed/audio-described-only versions are excluded. Canonical episodes combined across providers retain availability from their BBC source. The UHD show list does not mix in ordinary genre recommendations; episode cards identify available UHD editions.

Initial projection verified two UHD films (Mr Burton, The Monkey) and three UHD series (Blue Planet III, Doctor Who 2005–2022, Vigil), covering 25 episodes. Availability can change. Build, 23 gateway/catalogue tests, and the playback-extras suite passed. Build 29 was installed on the physical Apple TV; menu selection with the Siri Remote remains a visual check.


### Wider UHD discovery and collection focus — build 30

UHD now also discovers programmes from the BBC's published UHD article, rather than limiting the filter to the existing saved library. Every listed group/single-episode link is validated against BBC episode metadata; future/expired and accessibility-only editions are excluded. Episode links are resolved to their parent programme to avoid importing only the first episode of a series. Discovery updates in the existing background task with a six-hour cache and never prepares a stream. Existing library records, favourites and progress are retained when a discovered programme is already present.

The initial list contained 95 distinct BBC links; current validation yielded 90 programme entries, projected as 86 show/special tiles and three film tiles after canonical grouping. These are catalogue-verified UHD listings, not a claim that every title was individually playback-tested.

The collection menu is a full-width focus section with explicit Up routing from any first-row grid card and Down routing back to the first result. This removes dependence on having a fourth/rightmost card beneath the menu. Build and 25 catalogue/gateway tests passed; build 30 installed on the physical Apple TV. Short-row Siri Remote focus still requires physical confirmation.


### Scene lighting — build 32

Settings → Scene lighting optionally follows the predominant scene hue on the Home Assistant lamp configured by the host. The current installation targets Behind TV Light. Colourful scenes use 100% saturation; grey, black and white scenes request white (zero saturation). The feature never sends a scene-dependent brightness value: the lamp's starting brightness is preserved. On exit/disable, the prior colour/saturation/on-off state is restored. Manual lamp changes take priority and suspend the effect until a later playback session.

Apple TV samples a small SDR thumbnail from AVFoundation-exposed frames every two seconds, with read-only video output and no display capture or video re-encoding. No frames leave Apple TV. Area-based neighbouring hue clusters choose the dominant colour; bright highlights or a small green subject cannot outweigh a larger dark-blue area. Circular temporal smoothing and three-second lamp transitions soften changes. Neutral scenes remain white; there is no blue-only hue remapping. Fixed lamp brightness means the source's literal darkness cannot be reproduced.

The host accepts hue/neutral updates only from the paired owner of a valid playback ticket, controls only its configured lamp, rate-limits changes, and expires abandoned lighting leases. The Home Assistant credential stays on the Pi. Streams using protected native FairPlay paths are not sampled; unavailable frames leave the lamp alone.

Validation: native build succeeded; colour tests cover mixed/nearby hues, dark sea with a bright turtle, dark red with yellow highlights, neutral scenes, transparent/missing frames and red hue wraparound. Eight lighting/boundary tests plus existing gateway/native/features checks passed (56 total in the targeted host run). The real lamp accepted colour at full saturation and white at zero saturation while remaining at brightness 255, then restored its original [253.701, 67.717] hue/saturation. Initial physical UHD playback with sampling remained 3840×2160 with about 30 seconds buffered and zero stalls/retries; the user confirmed the effect looked good. Build 32 changed hue selection to area voting across the full spectrum and was installed with the programme resumed. Longer viewing and protected-stream behaviour retain the limitations above.


### Scene hue calibration — build 33

Settings → Calibrate scene colours opens a full-screen reference swatch with a compact bottom control panel. Choose Red, Orange, Yellow, Green, Turquoise, Navy, Blue, Purple or Pink, then adjust the real Behind TV lamp using ±1° or ±5° controls. Calibration preview uses full saturation without brightness commands. Match hue rather than the darkness of a reference swatch: a lamp held at fixed brightness cannot reproduce a dark screen's luminance.

Save calibration commits all draft reference adjustments; Cancel/Back discards them. Reset colour and Reset all operate on the draft until Save is chosen. Saved hue offsets are bounded and interpolate circularly between neighbouring references, leaving unrelated references unchanged. Neutral scene white is not affected. Preview ends and restores the prior lamp state on leaving the screen or losing its heartbeat. The pairing-protected host calibration route cannot take over an active playback lease or restore another device's calibration lease. Fine adjustment previews bypass normal scene hysteresis, using short transitions so 1° changes reach the lamp.

Validation: build 33 compiled and installed on physical Apple TV; the full-screen reference/menu/control layout was captured and checked. HA readback confirmed the lamp changed with the reference selection at brightness 255. Calibration identity/interpolation/wraparound/persistence/bounds tests passed, along with 58 targeted host tests including preview ownership and precise 1° updates. Final perceptual matching and Save/Cancel operation with the Siri Remote remain user-operated checks; no subjective calibration values were chosen on the user's behalf.


Scene-light transition update (5 November): playback colour changes and restoration now use three-second Home Assistant fades. Calibration retains 0.4-second preview fades. Manual colour-override checks wait for the requested fade to settle; turning the lamp off or changing brightness still takes priority. Twelve targeted lighting/ownership tests passed, including the three-second duration and in-progress fade handling. No app update or brightness adjustment is required for this host-side timing change.

### Up next (build 34)

The artwork-led Up next card appears at verified credits, or during the final ten
seconds if no valid credits marker is available. The fallback is a near-end cue,
not an inferred credits or skip marker. With Autoplay enabled, the ring counts
down using episode-relative playback time, so pausing and buffering do not run
out a wall-clock timer. Natural completion is still required before automatic
queue advancement. Keep watching cancels automatic continuation for that episode.

Watch fetches the next episode's catalogue entry while the card is visible. It
does not prepare another media session during playback: the host currently
advertises no preloading support and preparing relay media can replace the active
session. Stream preparation therefore starts after natural completion (or an
explicit Play next action); instant playback is not guaranteed.

Build 35 keeps the automatic Up next card compact and content-sized at the bottom
right, without the large image header. During successful automatic handoff it
retains the compact cue rather than mounting the manual queue panel; queue errors
and manual Up next still provide the full panel and recovery controls.

Build 36 restores AVKit's native tvOS transport and Siri Remote seeking, with a
non-interactive show/channel logo and provider overlay that fades with the system
controls. Actual-resolution quality badges remain. Chapters and episode actions
are in the native transport menus. The native seek delegate clears Watch's paused
anchor and records the episode-relative target for completion guards. Native
seeking follows the asset's advertised seekable ranges; growing relays do not gain
full-episode seekability merely by changing their controls.

The compact automatic Up next card includes a fixed-size episode thumbnail beside
the title and caption, with Next and Exit actions. Exit cancels autoplay and returns
to the library; the image does not create a tall empty header.

Build 37 sets AVKit's playback-bar title to the episode title only. The show name
remains in the separate logo area instead of being repeated in the transport.

### Cinematic browsing (build 49)

The `feature/cinematic-browse` branch adds a native collapsible sidebar on tvOS 18+
(with the previous tab navigation retained on tvOS 17), including Favourites.
Home highlights page horizontally with the remote and dot indicators. The hero
occupies about 64% of the measured page height, leaving Continue Watching visible.
Text uses a local scrim; the rest of the hero image stays bright. Show selections
open the series detail page, with the same hero treatment and the existing series
selector, episode playback, favourites and related programmes.

Continue Watching uses landscape episode artwork, a left-aligned show identity in
a shared vertical band, compact season/episode/runtime text, a progress line and
provider branding at bottom right. The identity has explicit aspect-preserving
size bounds and a soft elliptical readability fade. Later unplayed numbered
episodes can receive New episode badges; unknown specials are not guessed.

Home show recommendations exclude films; film continuation is on Films. Favourites
has distinct show and film shelves. Every shelf uses one shape: matched portrait
posters (including larger showcase posters) or a separate landscape fallback row.
Portrait artwork is fitted intact and never synthesized by cropping landscape art.
Finished posters retain their own title design. Landscape artwork uses serial,
off-main text recognition to suppress an extra logo when its title is already
present; detection is conservative but cannot guarantee every stylised font.

`catalogue_artwork.py` resolves portrait and backdrop artwork through the existing
host-only TMDB connection. It reuses conservative title/type matches and existing
clear logos, keeps film and television cache records separate, validates public
image paths, and performs bounded background metadata work. Catalogue reads do
not perform network lookups or prepare playback. New artwork appears on the next
library refresh; unmatched titles remain landscape. No client credentials or
new provider sign-ins are required.

The original deployed build 37 remains at Git tag `checkpoint-appletv-build-37`
on GitHub. Build that tag in a separate checkout to restore the previous interface;
this feature branch does not replace the checkpoint or change playback formats.

Builds 46–49 keep one stable focus target for the hero carousel; only inert image
layers slide, avoiding competition between horizontal scroll position and remote
focus. Adjacent hero photos are warmed independently of playback preparation.
Up from every card in the first shelf explicitly returns focus to the hero and
scrolls it to the top. Hero readability uses a broad elliptical fade rather than
a gradient bounded by the copy's rectangle. Personal shelves use watch/favourite
dates and recommendation order instead of alphabetic ties. Ambiguous editions
(such as QI XL, bleeped Taskmaster and regional/special versions) have edition
badges. The carousel's on-device navigation improvement was viewer-confirmed;
the final return-to-hero and edition changes still require remote verification.
