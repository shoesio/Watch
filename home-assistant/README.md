# Watch — Home Assistant streaming library

Deployed dashboard: **[Open Watch](http://192.168.0.146:8123/tv-favourites/watch)**. Refresh the browser once to load resource version `7-chrome-player`.

## Everyday use

- **For you** features account favourites, continue-watching episodes, recently watched shows and live TV.
- **Your library** includes provider filters and programme/episode search. Open a show for its description, series selector, episode thumbnails and summaries; select an episode to play it.
- **Live TV** includes BBC One, BBC Two, BBC News, BBC Four, Channel 4, E4, More4, Film4 and 4seven, with channel logos and coloured backgrounds. A basic now/next guide shows programme titles, descriptions and local start/end times. Listings come from the providers and refresh every ten minutes. Missing or stale listings are labelled rather than invented.
- Select **This device · browser** to watch on the Mac or another device running the dashboard. Safari uses native HLS; Chrome/Edge use the bundled hls.js player. Closing the player stops its stream, and inactive browser streams are reclaimed. This is local playback in that browser, not remote control of a sleeping Mac.
- Choose the output with **Watch on**. Unavailable or unsupported outputs are hidden. Replacing an active programme requires confirmation. A busy Apple TV is not chosen automatically.
- Add new favourites using the BBC iPlayer Watchlist, Channel 4 My4 or U My List. The provider links are in the footer. Account lists refresh every ten minutes, or use **Refresh library**. Provider watchlists/history are read only; the dashboard does not modify those lists.
- Colours follow the active Home Assistant theme. The layout adapts to narrow screens and supports keyboard focus, native selection controls and reduced motion.

YouTube and reference films have been removed from the production library. A programme previously selected manually is not automatically retained if it is absent from account favourites/history.

U currently states that live streaming has been withdrawn from its apps. U on-demand remains available; no unavailable U live channels are displayed.

## Current account connections

BBC favourites and continue watching are read from authenticated BBC website responses, after completing the normal BBC `.co.uk` session handoff. Public BBC episode metadata provides the available catalogue. Channel 4 uses its authenticated My4 favourites, continue-watching and history lists. U uses its authenticated My List and Watching pages, with UKTV programme/series metadata. Every show retains a provider label, real artwork and its available episodes.

The initial connected catalogue contains 28 on-demand shows, 1,894 on-demand episodes and nine live channels. Counts change with account activity and provider availability. Metadata availability does not guarantee every episode indefinitely; expired rights, provider changes or a new format can still cause an individual playback request to fail. Failed refreshes preserve the last known catalogue for the affected provider. Episodes whose metadata marks them unavailable are excluded.

BBC's `signed` metadata flag indicates an accessible version may exist; it must not hide an otherwise available episode. Default editorial/original playback remains selected.

## Playback on the Pi

The bridge runs as `tv-favourites.service` at `/home/jhewes/tv-favourites`, with its Python environment at `/home/jhewes/tv-favourites-venv` and its LAN media/static listener on port 8109.

- BBC uses the already-connected Streamlink path, selecting compatible H.264/AAC, short-buffer delivery and original timestamp preservation.
- Channel 4 and U use `provider_playback.py`: provider account/source resolution and the installed private playback setup, followed by FFmpeg reading the selected source progressively. Audio/video are copied into MPEG-TS without re-encoding. No browser or desktop capture runs in production.
- Original audio/video timestamps are preserved; independently resetting each track caused lip-sync errors during the earlier trial. The first track is paced at normal playback speed for Samsung's unknown-length streaming path.
- Preparation reads only a bounded 512 KiB sample for codec/profile validation. It does not download a whole episode.
- The TV fetches an expiring random LAN media URL. Control requests require authenticated HA context through `script.tv_favourites_play`. Resolved signed URLs, playback authorization and private data are never published in the catalogue or HA status.
- Legacy Samsung filtering accepts H.264 up to Level 4.1, 720p60 or 1080p30 with AAC/MP3. There are at most two concurrent relay connections. The working Samsung is the LT27B551 at `192.168.0.123`; the large Samsung's display-only MDC integration is hidden from playback selection.
- Relays are released when their output has stopped or disconnected. A grace period permits the Samsung's preflight/buffering phase before it reports PLAYING. New streams are not closed simply because the transport initially reports STOPPED.

Unknown-length streaming does not expose arbitrary HTTP range seeking. Provider resume positions can be supplied when playback starts, but a general in-player seek bar has not been added. The dashboard shows provider history/resume data; playback reporting back to all provider accounts is not implemented.

## Files

| File | Purpose |
|---|---|
| `tv-favourites-card.js` | Theme-aware streaming interface |
| `bridge.py` | HA events, output availability, source preparation and LAN playback |
| `library_sync.py` | Account list discovery and complete catalogue refresh |
| `provider_playback.py` | Channel 4/U progressive source resolution and codec-copy streaming |
| `bbc_auth.py` | BBC sign-in compatibility adapter |
| `catalogue.json` | Account-derived public metadata snapshot, refreshed automatically |
| `dashboard.yaml`, `script.yaml` | Home Assistant configuration |
| `settings.example.json`, `tv-favourites.service`, `requirements.txt` | Runtime configuration and dependencies |
| `test_bridge.py`, `test_bbc_auth.py`, `test_on_demand.py` | Backend regression checks |

## Validation and limits

- 32 backend tests pass, covering playback guards, timestamp/profile constraints, bounded preparation, HTTP behaviour, source-data exclusion, catalogue reloads and stopped-output cleanup with startup grace.
- The isolated component tests pass for account-library rails, programme and series navigation, episode selection, search, safe text rendering, unavailable-output hiding, replacement confirmation and offline-playback guards.
- Deployed Pi source probes passed for Channel 4 and U at 720p H.264/AAC. BBC Two, News and Four passed compatible live-source probes; BBC One already had physical playback confirmation.
- Real playback requests through Home Assistant on the deployed Pi produced advancing Samsung playback for both Taskmaster Bleeped and Would I Lie to You?. The earlier Mac progressive trials included user-confirmed correct picture, sound and lip-sync. See the redacted platform/progressive proof reports.
- Browser delivery was tested end to end through the HA script for Channel 4 and U episodes, all five Channel 4 live channels and BBC Four, including H.264/AAC segments and player-stop revocation. Physical Mac playback and a full-episode browser soak remain unconfirmed. Functional and API checks were performed. The current user's open HA tab could not be visually inspected because local browser control is disabled in Work settings. No claim of a completed visual review is made.
- Full-episode soak tests on the deployed Pi remain outstanding. The library is based on the connected services' current account lists, not a universal search across every streaming service.

## Recovery and redeployment

The existing deployed service is already configured. Do not replace its private data from this public bundle. Current credentials, session cookies, account tokens, HA token, private playback device and temporary source files live under `/home/jhewes/tv-favourites-private`; they are excluded here. Installation on a different machine needs its own permitted account/playback setup and an HA token.

1. Back up the existing application/config and HA resource/dashboard metadata. The deployment backup for this change is `/home/jhewes/tv-favourites-private/backups/platform-redesign`.
2. Install dependencies from `requirements.txt` in the dedicated environment; ensure FFmpeg/ffprobe are present.
3. Copy application files and configure `settings.json` from the example. Keep the existing private root and restrictive permissions. The systemd service permits writes to the application/private runtime paths so atomic account/catalogue refreshes can complete.
4. Restore/configure the HA script and panel dashboard using the YAML files. Register the module resource at `http://192.168.0.146:8109/static/tv-favourites-card.js?v=7-chrome-player` for this LAN setup.
5. Run `python library_sync.py` from the application directory, then restart only `tv-favourites.service`. No HA restart is required. Avoid restarting during active playback.
6. Test an idle output and refresh the browser. Production catalogue changes are automatically reloaded within 15 seconds.

The supplied HTTP asset/media addresses are intended for the user's HTTP LAN HA address. Remote HTTPS access needs matching HTTPS/same-origin hosting to avoid mixed-content blocking.

Rollback: restore the backed-up bridge, card, catalogue, settings and HA resource/dashboard configuration, then restart `tv-favourites.service` while outputs are idle. The existing BBC login helper and other unrelated HA services are preserved.

## Chrome player repair

The browser player now prefers hls.js whenever MediaSource playback is supported, even if Chrome reports native HLS support. Playback starts after the manifest is parsed. Closing clears previous media handlers; media-error recovery is attempted once and further errors show the precise failure. Safe playback diagnostics are sent as authenticated HA events without stream URLs or credentials. `test-browser-player.cjs` exercises native-HLS misdetection, manifest readiness, bounded recovery and player cleanup.

## Home Assistant Watch v8.1

The HA dashboard now uses the current provider catalogue with For you, Shows, Films and Live TV. It follows HA light/dark colours, uses Helvetica-style typography, proportionate artwork, clear show logos in heroes/details, and BBC/Channel 4/U/Channel 5 branding. The genre selector contains only populated genres and is hidden for live/series/episode contexts. Sections fetch the latest HA catalogue snapshot when opened; provider-account refresh remains in the background.

`dashboard_library.py` projects only public catalogue metadata. It shares numbered episode equivalence and measured source-quality rules with Samsung Watch. Duplicate episode cards have stable identities; actual compatible resolution/frame rate/bitrate determines playback source, with provider preference only breaking ties. Seasons/episodes are newest first, and episode/selected-season badges reflect their actual providers. Films include available titles independently of favourites. BBC and Channel 4 now/next, images and channel logos come from `live_guide.py`; unverified Channel 5 live streams remain absent.

The in-dashboard player has programme/episode descriptions, clear/provider logos, an SD/HD badge, pause/play, start over and a full episode timeline. Mouse/touch seeking and Pause → Up → Left/Right → Enter work through source reopening, with a spinner and the player retained. Metadata/specification fade together during playback. Buffering and source failures retry in place (three attempts, then explicit Retry/Close). HLS remuxing is paced at real time, uses codec copy, and retains A/V timing.

Browser progress is saved through the stream's unguessable capability URL and survives closing/reopening. HA progress is written to the private `home-assistant-watch-progress.json`; current Samsung progress is read as an additional resume source. This avoids modifying a running Samsung service's progress journal. The supplied cross-process `progress_store.py` can also be used by Samsung Watch at a later safe service restart for both journals to be read there.

Selected network outputs expose Pause/Play/Stop and episode-position controls when supported. Commands travel through authenticated HA events, require an active stream owned by this bridge, and target only the selected endpoint. Endpoint availability and confirmation before replacing unrelated playback are retained. Actual TV transport support determines which controls succeed; position updates follow the 15-second monitor cadence. No Apple TV playback testing was performed.

Deployment retains the existing HA dashboard/card/entity/script. The resource URL is cache-busted to `tv-favourites-card.js?v=8.1-watch-parity`. Account credentials, media licence data and native Samsung pairing keys remain private on the Pi. Static show-logo routes accept only hashed PNG filenames. TMDB attribution is available in the small About footer dialog.

Validation: 33 backend tests, catalogue and browser-player DOM suites, production HA sensor and asset checks, and a real HA browser request for Horror Express at 300 seconds. The returned HLS segment was verified as H.264/AAC 1280×720 at 50 fps and the capability was revoked afterwards. UI/transport behaviour was tested with simulated players; no physical TV playback was started by these checks.


### HA Watch v8.2 live-card refinement

Live channels now mirror the Samsung presentation: one 16:9 on-now image, a channel logo in the corner, LIVE badge, current programme details, and a separate text-only Next section. The dedicated Live TV view uses a responsive card grid; the home screen uses compact horizontal cards. Scrolling rows start at the same 5% left content margin as the headings and remain open to the right edge. Static grids retain normal content margins. The module resource is `tv-favourites-card.js?v=8.2-live-cards`; reload HA once if an older module is already loaded.

HA Watch v8.3 aligns tiles and their contents to the top across scrolling rows, programme grids, episode lists and live channels, including when neighbouring captions have different heights.


## HA Watch 9 — aligned with Apple TV (29 October 2026)

The HA card now shares Apple TV Watch's discovery/catalogue service, recommendations,
related shows, UK certificates and Pi-backed Watch favourites. It retains HA's theme
and available network output selector. The Apple TV and Samsung apps are not rebuilt
or restarted by this deployment.

- For You has up to six rotating highlights, Picked for you and broadcaster-sourced
  Hot now; Films has daily taste-led highlights. Rotation pauses on focus/hover,
  details and browser playback, and respects Reduce Motion.
- Shows/genres begin with up to 16 recent/favourite titles, followed by stable pages
  of 24 suggestions. Additional pages load on approach, with an explicit More button
  as a fallback. Search includes supported providers; discovery titles check episode
  availability on opening. New titles are not all physically playback-tested.
- Programme and film cards retain a three-line synopsis, rating where known, and a
  reserved progress-bar slot. All cards stay top aligned. Provider badges remain
  above titles; the series picker sits alongside Episodes.
- Save/remove a Watch favourite from details. These preferences are shared with the
  Apple TV app, with no writes to provider account favourites. Provider imports remain.
- Similar shows uses the existing shared relationship metadata, with paged More.
- Existing BBC still enrichment, transparent live channel marks, current programme
  descriptions and positive off-air filtering are reused. Live cards keep one current
  image; next remains text only.
- Browser preparation shows programme artwork. Waiting and seeks retain the player;
  a spinner has no redundant Buffering label. Buffered seeks are local. HLS keeps
  about three minutes of segments, bursts an initial 12 seconds then reads at real
  time, and requires a 12-second startup buffer (or a completed shorter clip). Codec
  copy and original relative A/V timestamps are preserved. Browser HLS requests up
  to 90 seconds buffered and gives stalls 60 seconds before bounded recovery.

`ha_alignment.py` proxies only library/search/discovery/related/favourite actions
through authenticated HA events. An internal paired companion credential lives at
`tv-favourites-private/ha-discovery-token`; it is never sent to the frontend. The
existing `watch-appletv.service` on port 8115 supplies metadata. If it is unavailable,
HA retains its existing library and offers retry for discovery. Cached raw discovery
and saved-favourite programmes are read into HA in memory without rewriting the
provider-owned catalogue. Existing HA source resolution and endpoint compatibility
checks continue to select playback sources.

Apple TV-specific FairPlay/Channel 5 live playback, AVKit/Siri focus, frame-rate
matching and direct-CDN native playback are not enabled on HA or old Samsung TVs.
Five live channels remain hidden here. Channel 5 on-demand retains the established
compatible Pi route. Device-specific player rendering and focus animations differ.

Deployment: copy bridge.py, browser_playback.py, ha_alignment.py, live_availability.py
and tv-favourites-card.js to the existing HA bridge directory. The shared service
must already be deployed and a separate companion paired token registered privately.
Use the shared static channel-marks-v2 assets. Restart the HA bridge when its playback
is idle, then change the existing Lovelace module resource to `?v=9.0-shared-watch`.
Rollback copies for this installation are in the private backups/ha-watch-v9 directory.

Verification: 37 Pi backend tests; three DOM/player suites; authenticated HA search
returned 12 Taskmaster matches. Comedy browsing returned 16 personal items plus a
24-item page from 601 suggestions, and a second page without duplicates. Deployed
sensor: 681 programmes, 155 UK ratings, 8 currently on-air supported live channels,
1,631 BBC episode stills. Synthetic H.264/AAC packaging proved 12 seconds of startup
buffer without reencoding. No physical TV playback was started for these checks.


## HA Watch 9.1 — latest Apple TV presentation and film shelf

The film grid and every film genre subset now follow the shared `film_rank` values,
including resumed films and the taste-led daily ordering. All available films remain
browsable. Playback and discovery preparation share crisp full-photo screens, lower
contrast gradients, centred programme logos/marks, synopsis and runtime information.
Live startup prefers the current programme artwork and description. Artwork remains
until first playback; subsequent reconnects preserve the video frame with a spinner.
Live reconnection/preparation failures allow six bounded attempts; on-demand retains
three. Manual Retry works for live sources too. Ended live relays shorter than the
12-second startup buffer are rejected rather than appearing ready.

The Pi's U resolver remains enabled. The new ITV code on the Pi supplies catalogue
metadata and a native playback descriptor to Apple TV; the installed generic HA Pi
resolver has branches for U, Channel 4 and Five, and no ITV media resolver. Until a
compatible ITV media path is verified, ITV-only discoveries and native live entries
are excluded from all HA shelves/imports. Device provider QR sessions and AVKit menus
are not copied into HA. Provider credentials and the established Pi routes are unchanged.

Validation: 41 backend tests, three DOM/player suites, including film ordering,
native-route filtering, short-ended-live rejection, and existing seek/buffer behavior.
Resource version is `?v=9.1-film-startup`. Rollback copies are private under
backups/ha-watch-v91. No Samsung or Apple TV service restart is required.
