## Samsung remote volume and mute 0.330

Load Samsung's legacy Common/API/Plugin.js and enable the native volume banner through NNAVI SetBannerState(1). On the capital-S window.onShow lifecycle, unregister only KEY_VOL_UP, KEY_VOL_DOWN and KEY_MUTE from app interception, using Common.API.Plugin.unregistKey. This is deliberately after sendReadyEvent, as required by the 2012 platform. Any pre-existing onShow handler is preserved.

If volume/mute key events still reach Watch, return before blockNavigation, preventDefault, dialogs or playback handlers. These buttons no longer become generic playback/navigation events or Escape. No volume is changed at startup and no custom software volume is applied. Autostart profiles and playback services are unchanged.

Six widget checks cover lifecycle ordering, three-key scope, SDK key values/fallbacks, modal pass-through and existing playback/browsing. The installer offers 0.330; synchronise and reopen Watch, then check volume up/down and mute on the real TV. Physical confirmation remains pending.

References: [Samsung legacy TV functionalities](https://developer.samsung.com/smarttv/legacy/development-guides/tv-functionalities.html), specifically its native Volume OSD, 2012 Volume UI and key registration guides; [Samsung Application Development Guide 1.20](https://freethetv2011.s3.amazonaws.com/App_Development_Guide_for_Samsung_Smart_TV%5BV1.20%5D%5B1%5D.pdf) for Common.API.Plugin, unregistKey and required plugin object IDs. SDK manuals are not committed.

## Topical home row and consistent BBC badges 0.329

The For You card row and hero now share a deterministic order: the most recently watched unfinished TV episode first, then the newest unwatched episodes from favourite/recent/watched shows. Completed episodes and films do not displace that lead TV slot. Choosing a home tile starts its exact episode; the first tile retains the existing saved-position/rewind behaviour. The Shows section still provides ordinary series/episode browsing.

Release/availability dates are retained from BBC metadata, Channel 4 first transmission/stream availability, U availability and Five VOD metadata. A private episode baseline records later genuinely added episode IDs, without treating an initial catalogue import or every sync as a new release. Dates are cached so an older importer cannot erase known release ordering; unsupported/missing dates are not invented. Unknown-date episodes use within-show season/episode order and familiar-show history as a fallback.

BBC channel marks use one smaller 14px source-layout height with proportional width, rather than one fixed width. This keeps ONE, TWO, FOUR and NEWS lettering consistent while retaining the centred dark badges. The taller card artwork from 0.328 is preserved.

150 backend tests and five widget checks pass, including ranking, completion, date parsing, first-seen baselines, redaction and direct home-tile resume. The Pi home API returned Continue watching followed by three Newly available tiles, matching its hero order. No TV playback was started in verification. The installer offers 0.329; synchronise from 192.168.0.146 and reopen Watch. The app identity and native autostart profiles are unchanged.

## Card artwork and channel badges 0.328

Channel logos, including the shorter BBC marks, now centre vertically and horizontally in their existing dark badges. The badge's line height matches its padded interior, with a zero-size text strut to avoid a font-baseline offset. Existing BBC PNGs have no asymmetric transparent padding.

Four-card screens use 124px-high artwork (previously 100px) in 240px cards; library grids use 140px-high artwork (previously 116px) in 256px cards, with a 12px row gap. Image crops use the matching dimensions before loading, retain aspect ratio, and leave room for titles, descriptions, metadata, progress and the footer. These are 1280px source-layout dimensions; packaging scales them to 1080p as before.

All four widget checks and the computed layout/badge checks pass. The installer at 192.168.0.146 offers 0.328. Packaging used 0.327 as its base and preserved every other asset, paired connection and app identity; startup profiles and running services were not changed. Synchronise and reopen Watch for the TV visual check.

For the confirmed native startup method, see the [Auto Ticker setup and recovery guide](../../samsung/AUTOSTART.md).

## Playback polish 0.327

The owner traced the pale video to an LCD setting on the TV. Remove the temporary opaque panels and their added padding, restore the soft playback gradient, and remove the Info-button graphics diagnostic. Native playback, resume and autostart registration are unchanged.

Playback information and the transport return to their original safe-area edges. The startup heading, logo and brand row share the screen centre; fixed text widths no longer overflow a padded parent. Provider marks have a matching row height/line height, trailing logo/button margins are removed, and transport labels have an explicit line height and vertical alignment.

Four widget checks pass. A computed-style check verifies transparent panels, no padding offsets and a shared central axis. The Pi installer offers 0.327, built from the deployed 0.325 package with all assets outside playback code/styles/markup and version preserved byte-for-byte. App identity remains SamsungWatch; startup profiles were not changed and no playback services were restarted. Synchronise user applications from 192.168.0.146 and reopen Watch for the physical visual check.

## Playback graphics test 0.322

The user confirmed that 0.321 did not resolve the pale picture. Version 0.322 removes the full-screen playback shade element entirely, clears startup artwork before invoking native Play, explicitly clears root backgrounds and uses dark panels only behind controls and programme information.

During playback, Info toggles the HTML graphics surface to zero opacity without stopping or seeking the source; Info again or another playback key restores it. This is a physical-TV diagnostic to distinguish the graphics surface from the video source/TV rendering. Return still closes normally. Four widget checks pass, including removal of the shade and the Info toggle preserving native playback calls and position. The installer at 192.168.0.146 offers 0.322. Physical confirmation remains necessary; 0.321 is retained as a rollback.

## Playback overlay update 0.321

The startup image is removed as soon as the native player reports buffering complete, with playback-time updates retained as a fallback. Clearing artwork detaches the image element, removes its source and load handlers, and replaces it with an empty hidden element so a late load cannot restore the old graphic over video. Closing playback clears the image as well; reconnecting still holds the native video frame.

Four widget checks passed, including a regression check for image removal and late image callbacks. The Pi installation server offers 0.321 at 1080p. Synchronise user applications from 192.168.0.146 and reopen Watch to install. The pale-overlay fix still needs confirmation on the physical Samsung. Publishing the package did not restart playback services.

# SamsungWatch 2.3 · release 0.230

The installer at 192.168.0.146 now offers the 1080p 0.230 update. Synchronise user applications and reopen SamsungWatch. The user confirmed that the previous 1080p build looks excellent; this release retains that drawing mode.

- Thumbnail dimensions and loading handlers are set before the image source. A picture remains hidden until its final proportional crop is calculated. The hero follows the same sequence and avoids reloading the same image on incidental focus updates.
- Grid images use a 480×270 JPEG variant, cached separately from the larger hero image (up to 1280×720), reducing network traffic and decoded image memory on the TV.
- BBC live guide data keeps both programme records as a schedule, so “next” becomes “now” at the boundary without a refetch gap. Real current titles and image responses were verified for BBC One, Two, Four and News.
- Clear-logo hero space is enlarged while keeping aspect ratio, title fallback and series/episode context. A downloaded logo replaces the programme title instead of duplicating it. No automatic logo-provider connection is configured yet.

26 backend tests and the component checks pass. The no-flash behaviour still needs physical verification after installation. The previous 0.221 package/list and source snapshot are under /home/jhewes/tv-favourites-private/backups/watch-v23.

For automatic clear logos, TMDB can search titles and return TV-series logo images (https://developer.themoviedb.org/reference/tv-series-images). Match and cache the correct UK show once, then cache a high-resolution English/neutral transparent PNG locally. fanart.tv can fill gaps using TMDB/TheTVDB IDs and a separate API key (https://api.fanart.tv/). Metadata should refresh periodically rather than on remote navigation. Edition labels such as Bleeped must remain visible even where the parent brand logo is shared. Account/API setup remains the next step; do not put a private API token in the TV widget or chat.

# SamsungWatch 2.2 — controls, resume and recovery

The installer at **192.168.0.146** currently offers **0.221**, a 1080p drawing-mode trial. Log into Smart Hub as `develop`, open Tools → Settings → Development, set the server IP, synchronise user applications and reopen SamsungWatch.

The equivalent 720p build is 0.220. A higher-version 720p recovery package, 0.222, is already on the Pi if the TV rejects, clips or slows down at 1080p. App code is otherwise the same. No firmware, region, ticker settings or other TV services are changed by this update. The button-sequence startup service remains disabled.

## Playback controls

- OK toggles pause/play when information is hidden. When controls are visible, Left/Right selects a button and OK activates it.
- The on-screen buttons are back 30 seconds, pause/play, forward 30 seconds, start over and stop.
- The remote's FF/Rewind buttons skip 30 seconds directly. Seeking in these progressive on-demand sources reopens the source near the requested position; a brief rebuffer and an earlier keyframe are normal. Live TV does not offer seeking or episode resume.
- Return stops, saves position and returns to the library. Exit closes the app. The SD/HD badge hides with playback information and reappears with it.

Positions are reported by the TV's player, sent to the Pi every five seconds and sent again on a normal Stop/Return. They survive closing the app, a Pi service restart or coming back another day. The private atomic file is `/home/jhewes/tv-favourites-private/samsung-watch-progress.json`; no provider account history is modified. Resume rewinds five seconds for context. Completed episodes restart at the beginning; unconfirmed/early endings retain progress.

Select the same episode to resume automatically. Its metadata shows the resume time. At programme level, the Play remote button resumes the most recently saved episode where available; OK still opens the show's series/episode list. Start Over in the transport controls explicitly starts at zero.

Reopening after a crash releases that physical app's stale relay so it does not remain blocked as already playing. An abrupt power loss may lose the most recent few seconds since the last heartbeat.

## Buffering and recovery

A normal buffering notification keeps the player open and shows buffering status. Supported legacy player buffering options are requested, with defaults retained when unavailable. Buffering gets up to 45 seconds before recovery.

A connection/render failure, live stream ending, or known-duration episode ending more than five seconds early triggers recovery. The app releases its old relay and retries up to three times, waiting 2, 5 and 10 seconds. Episodes reconnect just before the last reported position; live TV reconnects at the live edge. Return cancels pending recovery. After three unsuccessful attempts it stops retrying and retains progress for later. Thirty seconds of stable playback resets the retry allowance. These changes address transient interruptions; they cannot guarantee recovery from provider expiry, unavailable sources or persistent network failure.

## Live channels and branding

The app now maps all nine existing live channels: BBC One, BBC Two, Channel 4, BBC Four, E4, More4, Film4, 4seven and BBC News. Channel logos reuse the shared catalogue's artwork, rasterised as local PNGs. Channel 4/U provider logos and the pink iPlayer symbol are also bundled. Asset attribution accompanies the BBC symbol.

BBC now/next comes from the broadcaster's live pages. The five Channel 4 schedules come from Channel 4's TV-guide page. Programme pictures appear on live cards and in the hero, with the channel's badge retained. The gateway refreshes in the background every two minutes; the live view refreshes every minute. Missing or expired guide data is labelled unavailable. The local file preview uses a clearly labelled sample snapshot rather than a live feed.

## Show-title logos

Transparent programme-title artwork is often called a **clear logo**. TheTVDB documents this artwork category: https://support.thetvdb.com/kb/faq.php?id=96 . Its API access needs an appropriate account/key arrangement: https://thetvdb.com/api-information . Automatic catalogue downloads are **not connected** in this build, and no credentials are bundled or assumed.

The display/cache path is ready: PNGs in `/home/jhewes/tv-favourites-private/show-logos/<group-id>.png` appear in the programme detail hero; unavailable logos fall back to the normal title. Group IDs are stable hashes of the normalized show title used by the app. Logo images are served only through the existing TV-scoped gateway. This is display support, not a claim that logos have been downloaded for every show.

## Rendering

Both 720p and 1080p builds declare matching config.xml, viewport, widget.info and CSS drawing dimensions. They render at those requested sizes without a CSS zoom/transform. Higher-resolution PNGs are reduced to display size; the iPlayer symbol is a transparent rasterisation of its vector asset. Font-smoothing settings are best-effort: the TV's old renderer may ignore them, and actual framebuffer resolution is not yet physically confirmed. The app privately reports its viewport/screen dimensions on startup to help verification; that report alone does not prove the framebuffer mode.

## Verification

24 backend tests pass, including persistent progress, resume/restart, completion, stale-session recovery, guide parsing and channel art mapping. Component tests cover skip offsets, progress reporting, controls, overlay fade, buffering without immediate exit, reconnect/early-end handling and cancellation, plus grid navigation.

All nine real guide feeds were checked. All five Channel 4 current-programme pictures were decoded as JPEGs. A real Taskmaster Bleeped source opened at a requested 90-second offset as 1280×720 H.264 without video re-encoding; codec-copy output began at an earlier keyframe around 84 seconds.

Physical transport behaviour, interruption recovery and the 1080p drawing mode remain to be confirmed on the Samsung after installation. Browser visual review of file URLs is blocked by the browser tool; logo assets were visually inspected separately. Previous 0.210 package, installation list and sources are backed up under `/home/jhewes/tv-favourites-private/backups/watch-v22`.

## Runtime and rebuild

The app gateway runs as `samsung-watch.service` on port 8113. It imports the existing Pi bridge/resolver, leaving `tv-favourites.service` and the HA dashboard configuration intact. API access remains restricted to the paired TV and localhost, with a device-scoped key. HA/provider credentials stay on the Pi.

```sh
cd /home/jhewes/samsung-watch
/home/jhewes/tv-favourites-venv/bin/python build.py \
  --key-file /home/jhewes/tv-favourites-private/samsung-watch-key \
  --resolution 1080 --version 0.221 \
  --output /home/jhewes/samsung-home/SamsungWatch_0.221_Europe_20261028.zip
```

Use `--resolution 720` for the conservative drawing mode. Source packages contain a placeholder device key and cannot control a TV until packaged with its actual scoped key. Retain the supplied font licence and asset attribution files.


TMDB clear logos (0.240)
-----------------------
Run `Connect TMDB.command` on the Mac. The hidden terminal prompt validates a TMDB Read Access Token (or v3 API key) before saving it with owner-only permissions on the Pi. No TMDB credentials are included in the TV package or browser.

`tmdb_logos.py` matches exact series titles, preferring a unique British match. Taskmaster Bleeped, QI XL and Have I Got a Bit More News for You use the parent series logo while retaining their edition labels. Ambiguous matches are skipped. The private `tmdb-logo-manifest.json` records matches and missing logos for review. Cached transparent PNGs are served through the existing paired image route; new library shows are checked every ten minutes, missing logos weekly, existing logos monthly. Refresh Watch to display new images. The Credits menu contains TMDB attribution. Availability depends on TMDB having a suitable clear logo.


Watch 0.251
-----------
Sync SamsungWatch in the TV developer menu to install the 1080p update. Show logos are limited to half the screen width and retain their proportions, including in series/episode screens. Pause shows programme branding, the show logo where available, episode information, synopsis, progress and remaining time. Buffering keeps the player visible with a spinner. Reconnection holds the native frame when possible; failed retries offer OK to retry or Return to save and close.

Genres sits next to All shows and only lists populated genres. Films browses the available BBC, Channel 4 and Channel 5 catalogues independently of account favourites. Seasons and episodes sort newest first by numeric series/episode position; season badges are derived only from providers with episodes in that season.

Channel 5 account connection uses Connect Channel 5.command. Passwords are not saved. The connector accepts the provider's 201 Created session response and stores only session/refresh tokens privately. The provider importer reads favourites/recent items and available films; expired episodes are omitted. On-demand format was verified as 720p H.264/AAC using the existing progressive LAN relay. Channel 5 live was investigated but failed track authorisation checks and is intentionally absent. Existing BBC and Channel 4 live channels remain. Channel 5 branding uses the official app mark on show/season/episode/player elements.

The Channel 5 legacy media client certificate is stored only on the existing Pi, outside this source bundle. TLS compatibility is scoped to the Channel 5 media-auth host and retains server certificate verification. No account/provider secrets are bundled.


Watch 0.260
-----------
Episode synopsis is visible whenever the transport overlay is visible. Pause, then Up focuses the timeline. Left/Right adjusts a preview marker in increasing steps (10, 30, 60, then 120 seconds); no stream is reopened while scrubbing. OK commits and resumes from the selected time. Down or Return cancels scrubbing and stays paused.

Numbered episodes shared across providers are presented once within the same show edition. Specials with unknown numbering are kept separate. On first play the gateway samples the compatible sources and chooses by measured resolution, frame rate, then available bitrate; BBC is only the final tie breaker. Source quality is cached privately for a day. Failure of a candidate falls back to another compatible source. A stable episode identity preserves progress across provider changes and adopts historical source-specific progress.

A real Have I Got a Bit More News for You comparison measured BBC at 1280x720/50 fps and U at 1280x720/25 fps; BBC was selected. Source checking happens on demand, not for every episode during browsing.

The genre filter is anchored at the far right, labelled Genre: All (or the chosen genre), and names the current section in its chooser. BBC ISO 8601 durations are parsed before preparation and display; Horror Express, Sicario and Mr Burton were verified as compatible 1280x720/50 fps H.264/AAC sources.


Watch 0.270
-----------
Navigation contains For you, Shows, Films and Live TV. Genre is a section filter and is hidden in series/episode views or sections without genres. Each opened screen/page fetches the current catalogue; account refresh remains a background task. Previous/Next/Refresh/Credits navigation, the main Watch wordmark and strapline, and the +/-30 second onscreen buttons are removed. TMDB attribution is available via the remote Info button while browsing.

Up at a grid's top pages backward, Down at its bottom pages forward, and Left/Right at row edges page across results while retaining the row/column where possible. At the first page, Up opens navigation. Return from a top-level results grid also opens navigation from any page.

Transport retains Play/Pause, Start over and Stop. Normal state messages above SD/HD are hidden; buffering retains its spinner and unrecoverable connection errors remain actionable. Episode numbering is presented once, with a distinct episode title only when available.


Watch 0.271
-----------
Committing a timeline seek (also Start over or a remote FF/RW skip) now uses the same in-player waiting path as reconnection. The app requests a frozen native frame, displays the buffering spinner and prepares the new position without exposing the library. Preparation failures retry in place; Return cancels and prevents late preparation responses from starting playback.


Watch 0.272
-----------
The timeline has an explicit circular playhead that follows playback and scrubbing. Buffering shows only the animated ring. A body-level player state prevents the library from painting during an active player transition. Late native completion callbacks are ignored during seeks until new playback advances. Startup version reporting and a small private, bounded event trace help distinguish an old installation from a native callback issue; only event names, version, booleans and numeric position are retained. No signed media URLs, provider credentials or tokens enter the trace. Info shows the installed build version.


Watch 0.273
-----------
Up focuses the on-demand timeline during playback as well as when paused. Video continues while the preview marker is adjusted; OK buffers and plays from the selected position. Down or Return cancels timeline editing without changing the prior playing/paused state. The onscreen Stop button is removed; Return outside timeline editing saves the position and closes playback. The remote hardware Stop key remains supported.


Watch 0.300 — Apple TV features for Orsay
---------------------------------------
Search uses an arrow/OK keyboard and public BBC, Channel 4, U and Channel 5 metadata. Select Search on the keyboard to run the query. Selecting a discovered programme verifies available episodes and imports them into the Samsung library; the existing H.264/AAC LAN delivery and duplicate-episode quality selection remain in use. Search imports always apply the Samsung rendition policy rather than Apple TV's best-resolution policy.

Discover ranks new programmes using local favourite/recent genres and source-labelled popularity. Its genre selector only lists populated categories. Similar is available when a show is open; documented cast, creator and production connections precede broader genre matches, and suggestions must match provider catalogue metadata. Results are stable for an hour, paged via the existing remote edge navigation. The public Channel 4 and Channel 5 catalogue indexes are cached separately under tv-favourites-private/samsung-discovery. No Apple TV tokens or provider-account sessions are copied.

Favourite/Unfavourite while a show is open stores a durable Pi-local override; the yellow remote key provides the same action. Provider account watchlists are not modified. Source metadata for discovered favourites is retained when transient search caches expire. Shows and For you reflect local overrides. UK certification badges are shown only for sourced, unambiguous GB values. Missing ratings are omitted.

Films has a Featured action: six daily picks, varied by genre/provider and local taste. The hero moves gently between the visible picks after 18 seconds without input; any remote input or focus in navigation suspends it. Reduce Motion is respected where the old browser exposes that preference.

Playback preparation and discovered-episode loading use the sharp programme photo with a subtle dark gradient behind the logo/text. Images keep their proportions; no blur is used. The text-free spinner, timeline dot, scrubbing during playback, pause metadata and simplified navigation remain.

Native Apple TV FairPlay/AVPlayer playback is not portable to the 2012 Orsay player. Channel 5 live remains omitted on Samsung because its existing route failed verification. Samsung playback stays at verified compatible quality, separate from Apple TV's direct/native route.

Validated: 110 backend test invocations, three remote-widget suites, real Ghosts search/import (34 BBC episodes), 611 comedy recommendations, Taskmaster related titles, daily featured film picks and sourced GB ratings. New Samsung UI still requires the TV's developer sync.


Watch 0.310 — latest Apple TV browsing and artwork
------------------------------------------------
Shows and genre-filtered Shows begin with up to 16 recent/favourited series, then continue through stable pages ranked by relevance. Actual saved watch positions and new local favourite-action dates drive personal order; catalogue import times are not treated as watch history. The candidate pool now uses full relevant BBC genres and the Channel 4/Five indexes, with format-aware scoring and provider diversification. Discover uses the same improved ranking.

For You has six ready-to-open highlights, inline arrows/Open and a position counter. Up from navigation reaches the hero controls; Play also opens the highlighted show. Rotation occurs only after 18 idle seconds and pauses while navigation or another screen is active. Sharp photographs and subtle gradients remain; no blur is introduced.

Cards retain their synopsis alongside a thin progress bar. Artwork boxes reserve a consistent size. Live cards show the current broadcaster synopsis where supplied, retain next/time metadata, and use transparent channel marks separate from fallback channel cards. BBC marks display ONE, TWO, FOUR and NEWS without BBC blocks. All logos preserve proportions.

Time-valid explicit off-air/holding listings are hidden until schedules resume; missing guide data alone never hides a channel. Current BBC descriptions and schedules refresh every five minutes. Exact BBC episode PID stills are cached privately and used only for the selected BBC source, preserving other providers' artwork. Public artwork cache data was copied from the Apple TV project; no Apple TV credentials/session data were copied.

Verification: 137 backend test invocations and four widget suites pass. Real metadata showed 6,328 recommendation candidates; first 24 provider counts were Channel 4 10, BBC 8, Five 5, U 1. Personal opening had 16 entries; highlights had 6. The copied cache held 1,775 BBC episode stills. Daytime BBC Four was hidden while the eight other supported Samsung channels remained. Five live remains unavailable on this legacy playback route; its Apple TV native route was not ported.
