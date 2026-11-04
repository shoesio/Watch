# Shared playback features, version 1

Deployed on the existing Watch gateway, `http://192.168.0.146:8115`, on 4 November 2026. All routes below use its existing Bearer pairing and private-network checks. They do not change the Samsung or HA authentication scheme. A client without a gateway session must pair separately or call through its own authenticated server adapter; never copy another device's token or expose a server credential in public dashboard files. There is no new anonymous API or CORS exemption.

Source: `server/watch-appletv/playback_features.py`, registered in `server.py`. No client UI was added. The module is framework independent except for the BBC metadata fetch; other server adapters can import the normalization/ordering functions.

## Capabilities and metadata

- `GET /playback/capabilities` returns `schema_version:1`, `chapters:true`, `skip_markers:["intro","recap"]`, `series_queue:true`, `marker_timebase:"episode"`, `autoplay_owner:"client"`, `preload_supported:false`. Capability means the API exists; per-episode availability still needs checking.
- `GET /playback/features?episode_id=ENCODED_ID&version_id=EXACT_VERSION_ID` returns the response below. `version_id` is optional for non-BBC sources, required for BBC timing lookup. An optional `source_key` must match the selected source or returns 409. Ready preparation metadata includes the chosen `source_key` when bound successfully. An optional `ticket` restricts metadata lookup to the caller's active playback session and enables embedded chapters from the existing prepared file/info. Wrong-device or wrong-episode tickets return 404. Treat ticket values as secrets.
- A ready `GET /prepare/{job}` response adds relative `metadata.features_url` and `metadata.up_next_url` links. Existing preparation and progress payloads remain backward compatible. Append the actual version and active session ticket to the features URL as appropriate.

```json
{
  "schema_version": 1,
  "episode_id": "canonical_episode_id",
  "source_key": "opaque exact-source SHA256",
  "version_id": "exact_provider_version_or_null",
  "timebase": "episode",
  "status": "available",
  "chapters": [{"id":"stable-id","title":"Opening","kind":"chapter","start":0.0,"end":30.0}],
  "skip_markers": [{"id":"stable-id","title":"Intro","kind":"intro","start":8.0,"end":35.0}],
  "provenance": ["BBC exact version"]
}
```

All times are absolute seconds from the episode beginning, not wall-clock times or positions relative to a relay's segment window. Validate `source_key` and `version_id` against the source actually playing, and fetch again if the source/version changes. For a relay starting at an offset, translate using that offset through the client's existing absolute-seek path. Do not simply seek a rolling HLS item to the absolute episode time.

Statuses: `available`, `unavailable`, `version_required`, `version_not_found`, `temporarily_unavailable`, `not_applicable` (live). Empty arrays are normal. Metadata outages must not block playback. No guessed intro lengths, image matching or automatic timing transfer across providers, editions or versions. Timings must be finite, non-negative, have end > start, and fit the known duration. Only intro/recap types can become skip buttons.

Sources currently wired:

1. Exact-source catalogue `chapters` and `skip_markers` arrays.
2. Active session `prepared.info.chapters` using ffprobe's `start_time`, `end_time` and `tags.title`, when bound to the exact source. Existing local playback files can also be probed for embedded chapters. No network video download is triggered.
3. BBC public IBL `versions[].interactions`, using an explicitly supplied exact version ID and `type:skip`, subtype intro/recap, `interaction_points.show_from/skip_to`. A version is never selected just because it appears first. BBC responses are cached for six hours, at most 100 episodes. Fetching an episode without a known version does not expose guessed markers.
4. Reviewed private sidecar `PRIVATE_ROOT/appletv/playback-markers.json`, keyed by `source_key`, with `verified:true`, exact `version_id` (including null where applicable), `chapters` and `skip_markers`. This is an administrator/provider-import hook, not a public write API. Envied/importer metadata can be normalized into this format; its downloader is not invoked by these endpoints. No general automatic chapter/intro availability is claimed for Channel 4, U, ITV or Five.

## Series ordering and queue

`GET /playback/up-next?episode_id=ENCODED_ID&limit=20` returns `schema_version`, `episode_id`, `order:"chronological"`, `autoplay_owner:"client"`, `next_episode` (object or null), and `items` (up to limit, 1–100).

The order is ascending numeric season then ascending numeric episode, independent of reverse-order catalogue display. It crosses into the next season, uses the canonical merged episode IDs already used for playback, and keeps the existing playback quality selection. Films, live channels, unknown/unnumbered specials and the final numbered episode yield no automatic continuation. Gaps are not invented. Items contain safe episode metadata, programme ID/title, artwork, brands, resume position and duration where available; no media URLs or provider sessions.

Queues persist per paired client, not across all household devices. They are series queues, not arbitrary cross-provider playlists. Queue APIs do not prepare, preload, download or start video, and do not mark progress complete by themselves.

1. `GET /playback/queue` gives `schema_version`, `revision` (initially 0), `autoplay`, `current` (object or null), future `items`, `updated_at`, and `autoplay_owner:"client"`. Each item adds `available`. GET does not alter the queue.
2. `POST /playback/queue` with `{"episode_id":"START_ID","expected_revision":0,"autoplay":true}` seeds the current episode and subsequent numbered episodes (up to 10,000) in the canonical series. `autoplay` defaults to false. Return: updated queue. Existing queues can be replaced only with their current revision.
3. On actual completion, save completion through the existing progress API first. Then `POST /playback/queue/advance` with `{"completed_episode_id":"CURRENT_ID","expected_revision":1}`. Return: updated queue, whose `current` is the next playable catalogue episode, plus `removed_unavailable`. Unavailable future episodes are pruned at advance time. This call does not play anything.
4. `DELETE /playback/queue` with JSON `{"expected_revision":2}` clears it and disables autoplay.

Mutations require the exact integer revision. A stale revision or mismatched completion returns 409, including duplicate completion requests: re-fetch, do not blindly replay the mutation. Updates are serialized within the service event loop after reading request bodies. Separate devices have isolated files. Queue persistence survives service restart; media sessions do not. No completion/advance should run when a user merely presses Back, stops, seeks, buffers or suffers a stream interruption.

**Do not call `/prepare` to preload the next episode while the current one is playing.** Existing preparation replaces that device's active session. “Up next” means metadata/queue readiness, not a warm media stream. Clients may only prepare the successor after confirmed completion or an explicit Play next action.

## Verification and limits

The existing 121-check full gateway run passed; final targeted playback-feature, native-route and server tests also passed (42 checks) after adding concurrent-update coverage and local-file chapter extraction. Tests cover exact-version BBC matching, invalid times, duplicate markers, ordering across seasons, no films/live/special guesses, authentication, device isolation, persistence files, revision conflicts, duplicate completion, expired queue entries, no playback side effects and explicit clearing. Real-catalogue smoke-check details are recorded in the client handover/report. Client controls, autoplay countdowns and device seeking still require client implementation and physical tests.

Real-catalogue smoke check: Taskmaster Bleeped S10E1 correctly yields S10E2, E3 and E4, despite reverse browse ordering. A real BBC exact-version lookup returned no chapters or skip markers for the sampled episode; this is a supported absence, not evidence of an intro. Deployed health returned 200 and an unauthenticated capabilities request returned 401. HA and Samsung services remained active.

## Credits cue convention

The Apple TV build-16 client accepts exact-source chapter intervals with `kind:"credits"` or `kind:"end_credits"` as explicit credits cues. Supply start/end on the same absolute episode clock and through the existing exact-source/version normalization or reviewed sidecar. A title containing "Credits" does not establish a cue. These are chapter metadata, not additional intro/recap skip types: the `skip_markers` capability remains unchanged. Clients may offer a compact successor card during that interval, but must not mark the current episode completed, prepare the successor or start an autoplay countdown merely because credits begin.


## BBC selected-version handover correction

The gateway now retains the BBC VPID that actually produced each Streamlink media-selector result, attaches it to the selected clear HLS result, and includes it as `metadata.version_id` in native BBC preparation. It never chooses a metadata version by list order, title or matching duration. The existing Apple TV feature request already sends this value. Stream resolution and quality selection are unchanged; no media keys are handled or exported by this correction.

Staged verification on 4 November: Doctor Who episode `m00129lb` resolved a native clear HLS stream from exact version `m00129l9`; the marker endpoint returned recap 1–29 seconds and intro 274–306 seconds. Four sampled Doctor Who episodes each contained two skip interactions. Four sampled Have I Got News for You episodes contained none. Matching duration cannot supply a marker that the provider has not published. This correction covers the native clear BBC route; a relayed BBC source without a proven version still withholds version-specific markers.
