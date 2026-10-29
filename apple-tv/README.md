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

The project targets tvOS 17+, uses the existing development team, and has no package dependencies. Automatic signing is enabled. The currently installed development profile expires on **4 November 2026**; re-run from Xcode when renewal is needed. For a different account, change Team and Bundle Identifier in Signing & Capabilities.

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
